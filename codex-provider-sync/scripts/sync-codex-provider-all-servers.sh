#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_HISTORY_SCRIPT="${SCRIPT_DIR}/sync-local-codex-history.sh"
SYNC_SCRIPT="${SCRIPT_DIR}/sync-codex-provider-to-remotes.sh"
REPORT_SCRIPT="${SCRIPT_DIR}/report-codex-provider-status.py"
RUN_LOCAL_HISTORY_SYNC=1
OPEN_CODEX=1
DRY_RUN=0
SYNC_REMOTES=0
REMOTE_ARGS=()

HOSTS=(
  tx-server
  zactest
  zaclin
  zacbot
)

if [[ ! -x "$SYNC_SCRIPT" ]]; then
  printf 'error: sync script not found or not executable: %s\n' "$SYNC_SCRIPT" >&2
  exit 127
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      REMOTE_ARGS+=("$1")
      shift
      ;;
    --skip-local-history-sync)
      RUN_LOCAL_HISTORY_SYNC=0
      shift
      ;;
    --no-open-codex)
      OPEN_CODEX=0
      shift
      ;;
    --sync-remotes)
      SYNC_REMOTES=1
      shift
      ;;
    *)
      REMOTE_ARGS+=("$1")
      shift
      ;;
  esac
done

LOCAL_HISTORY_ARGS=()
if [[ "$RUN_LOCAL_HISTORY_SYNC" -eq 1 ]]; then
  if [[ ! -x "$LOCAL_HISTORY_SCRIPT" ]]; then
    printf 'error: local history sync script not found or not executable: %s\n' "$LOCAL_HISTORY_SCRIPT" >&2
    exit 127
  fi
  [[ "$DRY_RUN" -eq 1 ]] && LOCAL_HISTORY_ARGS+=(--dry-run)
  [[ "$OPEN_CODEX" -eq 0 ]] && LOCAL_HISTORY_ARGS+=(--no-open-codex)
  if [[ ${#LOCAL_HISTORY_ARGS[@]} -gt 0 ]]; then
    "$LOCAL_HISTORY_SCRIPT" "${LOCAL_HISTORY_ARGS[@]}"
  else
    "$LOCAL_HISTORY_SCRIPT"
  fi
fi

if [[ "$SYNC_REMOTES" -eq 1 ]]; then
  SYNC_CMD=("$SYNC_SCRIPT" --sync-cc-switch-db --no-sync-history --ssh-option BatchMode=yes)
  [[ ${#REMOTE_ARGS[@]} -gt 0 ]] && SYNC_CMD+=("${REMOTE_ARGS[@]}")
  SYNC_CMD+=("${HOSTS[@]}")
  "${SYNC_CMD[@]}"
else
  printf '[local-sync] completed or planned above. Default mode does not modify remote files.\n'
  printf '[remote-sync] skipped by default; pass --sync-remotes only when remote provider/config/auth sync is explicitly requested. Remote history sync remains disabled.\n'
fi

if [[ -x "$REPORT_SCRIPT" ]]; then
  "$REPORT_SCRIPT"
else
  printf 'warning: report script not found or not executable: %s\n' "$REPORT_SCRIPT" >&2
fi

printf '\nsync-codex-provider-all-servers completed.\n'
