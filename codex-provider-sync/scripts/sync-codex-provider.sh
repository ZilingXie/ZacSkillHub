#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_HISTORY="${SCRIPT_DIR}/sync-local-codex-history.sh"
SYNC_REMOTES="${SCRIPT_DIR}/sync-codex-provider-to-remotes.sh"
REPORT="${SCRIPT_DIR}/report-codex-provider-status.py"
RESTORE="${SCRIPT_DIR}/restore-remote-codex-history.sh"
MIGRATE="${SCRIPT_DIR}/migrate-remote-history-to-active-provider.sh"

HOSTS=(tx-server zactest zaclin zacbot)

DRY_RUN=0
OPEN_CODEX=1
SYNC_HISTORY=1
STATUS_ONLY=0
RESTORE_MODE=0
MIGRATE_MODE=0
RESTORE_BACKUP=""
RESTORE_TARGET=""

usage() {
  cat <<'USAGE'
Usage:
  sync-codex-provider.sh                          # default: local + remote config + remote history sync
  sync-codex-provider.sh --dry-run                # preview only
  sync-codex-provider.sh --no-open-codex          # skip reopening Codex after local sync
  sync-codex-provider.sh --no-sync-history        # skip remote history sync (config only)
  sync-codex-provider.sh --status-only            # report status only, no changes
  sync-codex-provider.sh --restore [--backup ID] [host]   # restore remote history from backup
  sync-codex-provider.sh --migrate-to-active [host]        # migrate remote history to active provider

Default flow:
  1. Quit Codex → codex-provider sync → reopen Codex
  2. Sync remote provider config + auth + CC Switch DB
  3. Sync remote thread history (codex-provider sync on remotes)
  4. Print status table

Pass --no-sync-history to skip remote history sync.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)      DRY_RUN=1; shift ;;
    --no-open-codex) OPEN_CODEX=0; shift ;;
    --no-sync-history) SYNC_HISTORY=0; shift ;;
    --sync-history)    SYNC_HISTORY=1; shift ;;  # kept for backward compat
    --status-only)   STATUS_ONLY=1; shift ;;
    --restore)       RESTORE_MODE=1; shift ;;
    --migrate-to-active) MIGRATE_MODE=1; shift ;;
    --backup)        RESTORE_BACKUP="${2:-}"; shift 2 ;;
    -h|--help)       usage; exit 0 ;;
    *)
      if [[ "$RESTORE_MODE" -eq 1 || "$MIGRATE_MODE" -eq 1 ]]; then
        RESTORE_TARGET="$1"
      fi
      shift
      ;;
  esac
done

die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# --- Status-only mode ---
if [[ "$STATUS_ONLY" -eq 1 ]]; then
  [[ -x "$REPORT" ]] || die "report script not found: $REPORT"
  exec "$REPORT"
fi

# --- Restore mode ---
if [[ "$RESTORE_MODE" -eq 1 ]]; then
  [[ -x "$RESTORE" ]] || die "restore script not found: $RESTORE"
  RESTORE_ARGS=()
  [[ "$DRY_RUN" -eq 1 ]] && RESTORE_ARGS+=(--dry-run)
  [[ -n "$RESTORE_BACKUP" ]] && RESTORE_ARGS+=(--backup "$RESTORE_BACKUP")
  if [[ -n "$RESTORE_TARGET" ]]; then
    RESTORE_ARGS+=("$RESTORE_TARGET")
  fi
  exec "$RESTORE" "${RESTORE_ARGS[@]}"
fi

# --- Migrate mode ---
if [[ "$MIGRATE_MODE" -eq 1 ]]; then
  [[ -x "$MIGRATE" ]] || die "migrate script not found: $MIGRATE"
  MIGRATE_ARGS=()
  [[ "$DRY_RUN" -eq 1 ]] && MIGRATE_ARGS+=(--dry-run)
  [[ -n "$RESTORE_TARGET" ]] && MIGRATE_ARGS+=("$RESTORE_TARGET")
  exec "$MIGRATE" "${MIGRATE_ARGS[@]}"
fi

# === Default flow: local sync + remote config sync ===

# Step 1: Local history sync
if [[ ! -x "$LOCAL_HISTORY" ]]; then
  die "local history script not found: $LOCAL_HISTORY"
fi

LOCAL_ARGS=()
[[ "$DRY_RUN" -eq 1 ]] && LOCAL_ARGS+=(--dry-run)
[[ "$OPEN_CODEX" -eq 0 ]] && LOCAL_ARGS+=(--no-open-codex)

printf '=== Step 1/3: Local history sync ===\n'
if [[ ${#LOCAL_ARGS[@]} -gt 0 ]]; then
  "$LOCAL_HISTORY" "${LOCAL_ARGS[@]}"
else
  "$LOCAL_HISTORY"
fi

# Step 2: Remote provider config sync only
if [[ ! -x "$SYNC_REMOTES" ]]; then
  die "remote sync script not found: $SYNC_REMOTES"
fi

REMOTE_ARGS=(--sync-cc-switch-db --no-sync-history --ssh-option BatchMode=yes)
[[ "$DRY_RUN" -eq 1 ]] && REMOTE_ARGS+=(--dry-run)
REMOTE_ARGS+=("${HOSTS[@]}")

printf '\n=== Step 2/3: Remote provider config sync ===\n'
"$SYNC_REMOTES" "${REMOTE_ARGS[@]}"

# Step 3: Remote history sync (default on; --no-sync-history skips)
if [[ "$SYNC_HISTORY" -eq 1 ]]; then
  printf '\n=== Step 3/4: Remote history sync ===\n'
  # sync-codex-provider-to-remotes.sh defaults SYNC_HISTORY=1,
  # so we omit --no-sync-history to let it run remote codex-provider sync.
  REMOTE_HISTORY_ARGS=(--sync-cc-switch-db --restart-codex --ssh-option BatchMode=yes)
  [[ "$DRY_RUN" -eq 1 ]] && REMOTE_HISTORY_ARGS+=(--dry-run)
  REMOTE_HISTORY_ARGS+=("${HOSTS[@]}")
  "$SYNC_REMOTES" "${REMOTE_HISTORY_ARGS[@]}"
else
  printf '\n=== Step 3/4: Remote history sync SKIPPED (--no-sync-history) ===\n'
fi

# Report
if [[ -x "$REPORT" ]]; then
  "$REPORT"
else
  printf 'warning: report script not found: %s\n' "$REPORT" >&2
fi

printf '\nsync-codex-provider completed.\n'
