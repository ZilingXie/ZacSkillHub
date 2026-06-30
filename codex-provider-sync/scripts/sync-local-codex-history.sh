#!/usr/bin/env bash
set -euo pipefail

DRY_RUN=0
OPEN_CODEX=1
CODEX_HOME_ARG="${CODEX_HOME:-$HOME/.codex}"

usage() {
  cat <<'USAGE'
Usage:
  sync-local-codex-history.sh [--dry-run] [--no-open-codex] [--codex-home PATH]

Runs the local Codex provider history sync flow after switching provider:
  osascript -e 'quit app "Codex"'
  pkill -f 'app-server'
  pkill -f 'Codex.app'
  codex-provider sync
  codex app
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1; shift ;;
    --no-open-codex)
      OPEN_CODEX=0; shift ;;
    --codex-home)
      CODEX_HOME_ARG="${2:-}"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      printf 'error: unknown option: %s\n' "$1" >&2
      exit 2 ;;
  esac
done

find_codex_provider() {
  if [[ -n "${CODEX_PROVIDER_BIN:-}" && -x "${CODEX_PROVIDER_BIN}" ]]; then
    printf '%s\n' "$CODEX_PROVIDER_BIN"
    return 0
  fi
  if command -v codex-provider >/dev/null 2>&1; then
    command -v codex-provider
    return 0
  fi
  local known="$HOME/.nvm/versions/node/v24.12.0/bin/codex-provider"
  if [[ -x "$known" ]]; then
    printf '%s\n' "$known"
    return 0
  fi
  return 1
}

find_codex() {
  if command -v codex >/dev/null 2>&1; then
    command -v codex
    return 0
  fi
  local app_codex="/Applications/Codex.app/Contents/Resources/codex"
  if [[ -x "$app_codex" ]]; then
    printf '%s\n' "$app_codex"
    return 0
  fi
  return 1
}

CODEX_PROVIDER="$(find_codex_provider || true)"
if [[ -z "$CODEX_PROVIDER" ]]; then
  printf 'error: codex-provider not found. Install Dailin521/codex-provider-sync first.\n' >&2
  exit 127
fi

export PATH="$(dirname "$CODEX_PROVIDER"):$PATH"
CODEX_BIN="$(find_codex || true)"

printf '[local-history-sync] codex-provider=%s\n' "$CODEX_PROVIDER"
printf '[local-history-sync] codex-home=%s\n' "$CODEX_HOME_ARG"

if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '[local-history-sync] dry-run: would quit Codex, kill app-server/Codex.app, run codex-provider sync, and %s Codex app\n' \
    "$([[ "$OPEN_CODEX" -eq 1 ]] && printf open || printf not-open)"
  "$CODEX_PROVIDER" status --codex-home "$CODEX_HOME_ARG" >/dev/null || true
  exit 0
fi

osascript -e 'quit app "Codex"' >/dev/null 2>&1 || true
pkill -f 'app-server' >/dev/null 2>&1 || true
pkill -f 'Codex.app' >/dev/null 2>&1 || true

"$CODEX_PROVIDER" sync --codex-home "$CODEX_HOME_ARG"

if [[ "$OPEN_CODEX" -eq 1 ]]; then
  if [[ -z "$CODEX_BIN" ]]; then
    printf 'warning: codex CLI not found; skipped reopening Codex app\n' >&2
  else
    nohup "$CODEX_BIN" app >/tmp/codex-app-restart.log 2>&1 &
    printf '[local-history-sync] requested Codex app restart\n'
  fi
else
  printf '[local-history-sync] skipped Codex app restart by request\n'
fi
