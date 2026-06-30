#!/usr/bin/env bash
set -euo pipefail

EXECUTE=0
BACKUP_NAME=""
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
HOSTS=(tx-server zactest zaclin zacbot)

usage() {
  cat <<'USAGE'
Usage:
  restore-remote-codex-history.sh [--execute] [--backup TIMESTAMP] [host...]

Default is dry-run. It discovers the newest provider-sync backup on each host
whose SQLite threads.model_provider contains "default".

Options:
  --execute           Actually restore remote history to provider bucket "default".
  --backup TIMESTAMP  Use a specific provider-sync backup directory name.
  -h, --help          Show help.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute)
      EXECUTE=1
      shift
      ;;
    --backup)
      BACKUP_NAME="${2:-}"
      shift 2
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
backup_name=__BACKUP_NAME_JSON__

export NVM_DIR="$HOME/.nvm"
if [ -s "$NVM_DIR/nvm.sh" ]; then . "$NVM_DIR/nvm.sh"; fi
nvm use 24.12.0 >/dev/null 2>&1 || true

log() {
  printf '[remote:%s] %s\n' "$(hostname 2>/dev/null || printf unknown)" "$*"
}

export PATH="${CODEX_INSTALL_DIR:-$HOME/.local/bin}:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
for candidate in "$HOME/.local/bin/codex-provider" "$HOME/.nvm/versions/node/"*/bin/codex-provider /usr/local/bin/codex-provider /usr/bin/codex-provider; do
  if [ -x "$candidate" ]; then
    export PATH="$(dirname "$candidate"):$PATH"
    break
  fi
done

if ! command -v codex-provider >/dev/null 2>&1; then
  printf 'codex-provider missing\n' >&2
  exit 127
fi

if [ -n "$backup_name" ]; then
  backup="$HOME/.codex/backups_state/provider-sync/$backup_name"
  [ -d "$backup" ] || { log "specified backup not found: $backup"; exit 3; }
else
  backup="$(
python3 - <<'PY'
from pathlib import Path
import sqlite3

root = Path.home() / ".codex/backups_state/provider-sync"
if not root.exists():
    raise SystemExit("")

def has_default_provider(db):
    if not db.exists():
        return False
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "select model_provider, count(*) from threads group by model_provider"
        ).fetchall()
        con.close()
    except Exception:
        return False
    return any(row[0] == "default" and row[1] > 0 for row in rows)

for backup in sorted([p for p in root.iterdir() if p.is_dir()], reverse=True):
    if has_default_provider(backup / "db/state_5.sqlite"):
        print(backup)
        raise SystemExit(0)
raise SystemExit("")
PY
)"
fi

if [ -z "$backup" ]; then
  log "no restorable provider-sync backup found with threads.model_provider=default"
  exit 3
fi

log "selected backup: $backup"

python3 - "$backup" <<'PY'
from pathlib import Path
import sqlite3
import sys

backup = Path(sys.argv[1])
db = backup / "db/state_5.sqlite"
con = sqlite3.connect(db)
rows = con.execute("select model_provider, count(*) from threads group by model_provider").fetchall()
con.close()
print("backup_threads=" + ", ".join(f"{provider}:{count}" for provider, count in rows))
cfg = backup / "config.toml"
if cfg.exists():
    text = cfg.read_text(errors="ignore")
    for key in ["model_provider", "model", "disable_response_storage"]:
        val = "UNSET"
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                break
            if stripped.startswith(key):
                val = stripped.split("=", 1)[1].strip()
                break
        print(f"backup_{key}={val}")
PY

if [ "$execute" -ne 1 ]; then
  log "dry-run: would restore backup, set root model_provider=default, sync provider default, and restart app-server/proxy"
  codex-provider status --codex-home "$HOME/.codex" 2>&1 || true
  exit 0
fi

codex-provider restore "$backup" --no-config --codex-home "$HOME/.codex"

python3 - <<'PY'
from pathlib import Path

p = Path.home() / ".codex/config.toml"
text = p.read_text(errors="ignore")
lines = []
in_table = False
changed = 0
for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        in_table = True
    if not in_table and stripped.startswith("model_provider"):
        lines.append('model_provider = "default"')
        changed += 1
    else:
        lines.append(line)

if changed == 0:
    out = []
    inserted = False
    for line in lines:
        if not inserted and line.strip().startswith("["):
            out.append('model_provider = "default"')
            inserted = True
        out.append(line)
    if not inserted:
        out.append('model_provider = "default"')
    lines = out

p.write_text("\n".join(lines) + "\n")
PY
chmod 600 "$HOME/.codex/config.toml"

codex-provider sync --provider default --codex-home "$HOME/.codex"

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

print("app_server_targets=")
for pid, args in targets:
    print(f"{pid} {args}")

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

codex-provider status --codex-home "$HOME/.codex" 2>&1 || true
log "restore completed"
REMOTE
}

for host in "${HOSTS[@]}"; do
  printf '\n==> %s\n' "$host"
  script="$(remote_script)"
  script="${script//__EXECUTE__/$EXECUTE}"
  backup_name_json="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$BACKUP_NAME")"
  script="${script//__BACKUP_NAME_JSON__/$backup_name_json}"
  if ! ssh "${SSH_OPTS[@]}" "$host" "bash -s" <<<"$script"; then
    printf 'error: host failed: %s\n' "$host" >&2
    exit 1
  fi
done

printf '\nrestore-remote-codex-history completed (%s).\n' "$([ "$EXECUTE" -eq 1 ] && printf execute || printf dry-run)"
