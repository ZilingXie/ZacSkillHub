#!/usr/bin/env bash
set -euo pipefail

EXECUTE=0
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10)
HOSTS=(tx-server zactest zaclin zacbot)

usage() {
  cat <<'USAGE'
Usage:
  migrate-remote-history-to-active-provider.sh [--execute] [host...]

Default is dry-run. For each host, reads the active ~/.codex/config.toml
model_provider, then runs codex-provider sync --provider <active-provider> only
when --execute is used.

Use when thread files still exist but the UI only shows a small subset because
older threads are in another provider bucket.
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

active_provider="$(
python3 - <<'PY'
from pathlib import Path

p = Path.home() / ".codex/config.toml"
text = p.read_text(errors="ignore")
for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("["):
        break
    if stripped.startswith("model_provider"):
        print(stripped.split("=", 1)[1].strip().strip('"'))
        raise SystemExit(0)
raise SystemExit("cannot determine active model_provider")
PY
)"

log "active provider: $active_provider"

echo '=== before ==='
codex-provider status --codex-home "$HOME/.codex" 2>&1 || true

python3 - <<'PY'
from pathlib import Path
import sqlite3

p = Path.home() / ".codex/state_5.sqlite"
con = sqlite3.connect(p)
con.row_factory = sqlite3.Row
print("sqlite_counts_before=")
for row in con.execute("select model_provider, archived, count(*) c from threads group by model_provider, archived order by model_provider, archived"):
    print(dict(row))
con.close()
PY

if [ "$execute" -ne 1 ]; then
  log "dry-run: would stop app-server/proxy and run codex-provider sync --provider $active_provider"
  exit 0
fi

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

codex-provider sync --provider "$active_provider" --codex-home "$HOME/.codex"

echo '=== after ==='
codex-provider status --codex-home "$HOME/.codex" 2>&1 || true
log "history migrated to active provider"
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

printf '\nmigrate-remote-history-to-active-provider completed (%s).\n' "$([ "$EXECUTE" -eq 1 ] && printf execute || printf dry-run)"
