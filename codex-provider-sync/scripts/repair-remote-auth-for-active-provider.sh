#!/usr/bin/env bash
set -euo pipefail

EXECUTE=0
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
HOSTS=(tx-server zactest zaclin zacbot)

usage() {
  cat <<'USAGE'
Usage:
  repair-remote-auth-for-active-provider.sh [--execute] [host...]

Default is dry-run. For each host, finds the CC Switch Codex provider whose
config matches the active ~/.codex/config.toml model_provider and base_url,
then updates ~/.codex/auth.json from that provider only when --execute is used.

This does not modify history and does not run codex-provider sync.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      HOSTS=("$@")
      break
      ;;
    -*)
      printf 'error: unknown option: %s\n' "$1" >&2
      exit 2
      ;;
    *)
      HOSTS=("$@")
      break
      ;;
  esac
done

remote_script() {
  cat <<'REMOTE'
set -euo pipefail

execute=__EXECUTE__

log() {
  printf '[remote:%s] %s\n' "$(hostname 2>/dev/null || printf unknown)" "$*"
}

changed_file="$(mktemp)"
trap 'rm -f "$changed_file"' EXIT

python3 - "$execute" "$changed_file" <<'PY'
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import time

execute = sys.argv[1] == "1"
changed_file = Path(sys.argv[2])
home = Path.home()
config_path = home / ".codex/config.toml"
auth_path = home / ".codex/auth.json"
cc_path = home / ".cc-switch/cc-switch.db"

def parse_config(text):
    root = {}
    tables = {}
    current_table = None
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("[") and s.endswith("]"):
            current_table = s.strip("[]")
            tables.setdefault(current_table, {})
            continue
        if "=" not in s:
            continue
        key, value = [x.strip() for x in s.split("=", 1)]
        value = value.strip('"')
        if current_table is None:
            root[key] = value
        else:
            tables[current_table][key] = value
    return root, tables

def key_label(value):
    if not value:
        return "none"
    if value.startswith("ko_"):
        return "ko_" + value[-5:]
    if value.startswith("sk-"):
        return "sk-" + value[-5:]
    return "other-" + value[-5:]

if not config_path.exists():
    raise SystemExit(f"missing config: {config_path}")
if not cc_path.exists():
    raise SystemExit(f"missing CC Switch DB: {cc_path}")

root, tables = parse_config(config_path.read_text(errors="ignore"))
active_provider = root.get("model_provider")
active_table = tables.get(f"model_providers.{active_provider}", {})
active_base = active_table.get("base_url", "")
if not active_provider or not active_base:
    raise SystemExit("cannot determine active provider/base_url")

current_auth = {}
if auth_path.exists():
    current_auth = json.loads(auth_path.read_text())
current_key = current_auth.get("OPENAI_API_KEY") or ""

con = sqlite3.connect(cc_path)
con.row_factory = sqlite3.Row
matches = []
for row in con.execute("select name, settings_config from providers where app_type='codex'"):
    settings = json.loads(row["settings_config"])
    cfg_root, cfg_tables = parse_config(settings.get("config") or "")
    cfg_provider = cfg_root.get("model_provider")
    cfg_base = cfg_tables.get(f"model_providers.{cfg_provider}", {}).get("base_url", "")
    if cfg_provider == active_provider and cfg_base == active_base:
        auth = settings.get("auth") or {}
        key = auth.get("OPENAI_API_KEY") or ""
        matches.append((row["name"], auth, key))
con.close()

if not matches:
    raise SystemExit(f"no matching CC Switch provider for {active_provider} {active_base}")

exact = [(name, auth, key) for name, auth, key in matches if key and key == current_key]
if exact:
    print(f"auth_match=ok provider={exact[0][0]} key={key_label(current_key)}")
    raise SystemExit(0)

if len(matches) != 1:
    expected = ", ".join(f"{name}:{key_label(key)}" for name, _, key in matches)
    raise SystemExit(f"ambiguous matching providers: {expected}")

name, auth, key = matches[0]
if not key:
    raise SystemExit(f"matching provider {name} has no OPENAI_API_KEY")

print(f"auth_match=mismatch current={key_label(current_key)} expected_provider={name} expected={key_label(key)}")

if not execute:
    print("dry_run=would update auth.json and restart app-server/proxy")
    raise SystemExit(0)

stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
backup = None
if auth_path.exists():
    backup = auth_path.with_name(f"auth.json.before-active-provider-auth-repair.{stamp}")
    backup.write_text(auth_path.read_text())
    os.chmod(backup, 0o600)
auth_path.parent.mkdir(parents=True, exist_ok=True)
auth_path.write_text(json.dumps(auth, indent=2) + "\n")
os.chmod(auth_path, 0o600)
changed_file.write_text("1")
print(f"updated_auth_from_provider={name}")
print(f"backup={backup if backup else 'none'}")
PY

if [ "$execute" -eq 1 ] && [ -s "$changed_file" ]; then
  python3 - <<'PY'
import os
import signal
import subprocess
import time

me = os.getpid()
parent = os.getppid()
ps = subprocess.run(["ps", "-eo", "pid=,args="], text=True, capture_output=True, check=True).stdout.splitlines()
targets = []
for line in ps:
    line = line.strip()
    if not line:
        continue
    pid_s, _, args = line.partition(" ")
    try:
        pid = int(pid_s)
    except ValueError:
        continue
    if pid in {me, parent}:
        continue
    if "codex" in args and "app-server" in args:
        targets.append((pid, args))

for pid, args in targets:
    print(f"app_server_target={pid} {args}")
for pid, _ in targets:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
time.sleep(2)
remaining = []
for pid, args in targets:
    try:
        os.kill(pid, 0)
        remaining.append((pid, args))
    except ProcessLookupError:
        pass
for pid, _ in remaining:
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
print(f"terminated={len(targets)} sigkilled={len(remaining)}")
PY
fi

log "auth repair check completed"
REMOTE
}

for host in "${HOSTS[@]}"; do
  printf '\n==> %s\n' "$host"
  script="$(remote_script)"
  script="${script//__EXECUTE__/$EXECUTE}"
  if ! ssh "${SSH_OPTS[@]}" "$host" "bash -s" <<<"$script"; then
    printf 'error: host failed: %s\n' "$host" >&2
    exit 1
  fi
done

printf '\nrepair-remote-auth-for-active-provider completed (%s).\n' "$([ "$EXECUTE" -eq 1 ] && printf execute || printf dry-run)"
