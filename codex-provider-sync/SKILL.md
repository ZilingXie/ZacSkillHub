---
name: codex-provider-sync
description: After switching Codex provider in CC Switch, syncs local history + remote provider config + remote thread history. Use --no-sync-history to skip remote history. Also covers remote history restore/migrate.
---

# Codex Provider Sync

## Overview

Unified skill — the single entry point for all Codex provider sync, config, and history operations.

**Default flow**: local history sync → remote provider config sync → remote thread history sync → status report. Pass `--no-sync-history` to skip remote history.

## Servers

| Server | SSH alias |
|---|---|
| tx-server | `tx-server` |
| vpn | `zactest` |
| n8n | `zaclin` |
| supportportal | `zacbot` |

## Workflow

Execution rule: set Bash timeout to at least 600000 ms.

### 1. Default: local + remote config + remote history sync

```bash
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh
```

This runs four steps:
1. Quit Codex → `codex-provider sync` → reopen Codex
2. Sync remote `~/.codex/config.toml`, `~/.codex/auth.json`, `~/.cc-switch/cc-switch.db` to all four servers
3. Run remote `codex-provider sync` on all four servers
4. Print status table

### 2. Dry-run (preview only)

```bash
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh --dry-run
```

### 3. Without remote history sync (config only)

```bash
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh --no-sync-history
```

### 4. Status only

```bash
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh --status-only
```

### 5. Restore remote history from backup

```bash
# Dry-run first
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh --restore

# Execute (after user confirms)
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh --restore --backup 20260605T071117898Z tx-server
```

### 6. Migrate remote history to active provider

```bash
# Dry-run first
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh --migrate-to-active tx-server

# Execute (after user confirms)
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider.sh --migrate-to-active tx-server --execute
```

### 7. Single-server config sync

```bash
~/.claude/skills/codex-provider-sync/scripts/sync-codex-provider-to-remotes.sh \
  --sync-cc-switch-db --no-sync-history --ssh-option BatchMode=yes zaclin
```

## Options

| Flag | Effect |
|---|---|
| `--dry-run` | Preview only, no changes |
| `--no-open-codex` | Skip reopening Codex after local sync |
| `--no-sync-history` | Skip remote `codex-provider sync` (default runs it) |
| `--sync-history` | Explicitly run remote history sync (same as default; kept for backward compat) |
| `--status-only` | Print status table only, no changes |
| `--restore` | Restore remote history from backup (requires confirmation) |
| `--migrate-to-active` | Migrate remote history to active provider (requires confirmation) |
| `--backup ID` | Specify backup ID for restore (e.g. `20260605T071117898Z`) |

## What Each Step Changes

### Local history sync
- Quits Codex app, kills app-server/Codex.app processes
- Runs `codex-provider sync` to move rollout files + SQLite to the active provider bucket
- Reopens Codex app (unless `--no-open-codex`)

### Remote provider config sync
- Updates remote `~/.codex/config.toml` root provider keys and active provider table
- Updates remote `~/.codex/auth.json`
- Mirrors local CC Switch Codex provider rows into remote `~/.cc-switch/cc-switch.db`
- Strips `env_key = "..."` from synced configs when API key is present
- Does NOT run remote `codex-provider sync` (history is handled in the next step)

### Remote history sync (default on)
- Runs `codex-provider sync` on all four remote servers
- Moves remote rollout files + SQLite to the active provider bucket
- Skip with `--no-sync-history`
- WARNING: encrypted-content threads from other providers may become uncontinuable

## Success Criteria

For the default flow, output must include:
- `Synchronized provider: <name>` from local sync
- `All hosts synced successfully.` from remote config sync
- `codex-provider sync ran` for each host from remote history sync
- Status table showing all four hosts with matching provider and `Auth match: ok`
- `sync-codex-provider completed.`

## Safety Rules

- Never run restore/migrate `--execute` without user confirmation
- Do not use while remote Codex is actively doing work
- Keep secrets masked in output
- If `Auth match` shows `mismatch`, do not claim success; run repair
