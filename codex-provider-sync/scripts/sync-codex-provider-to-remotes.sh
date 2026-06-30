#!/usr/bin/env bash
set -euo pipefail

SOURCE="active-files"
PROVIDER_NAME=""
PROVIDER_ID=""
CC_SWITCH_DB="${HOME}/.cc-switch/cc-switch.db"
CODEX_HOME_LOCAL="${HOME}/.codex"
REMOTE_CODEX_HOME=".codex"
REMOTE_CC_SWITCH_DB=".cc-switch/cc-switch.db"
HOST_FILE=""
LIST_PROVIDERS=0
DRY_RUN=0
SYNC_HISTORY=1
SYNC_CC_SWITCH_DB=0
RESTART_CODEX=0
INSTALL_PROVIDER_SYNC=0
SSH_OPTS=()
HOSTS=()

usage() {
  cat <<'USAGE'
Usage:
  ./sync-codex-provider-to-remotes.sh --list-providers
  ./sync-codex-provider-to-remotes.sh host1 host2
  ./sync-codex-provider-to-remotes.sh --source cc-switch --provider-name "DeepSeek" host1 host2

Purpose:
  Sync the local Codex provider state to remote machines after switching provider
  locally with CC Switch.

Default source:
  active-files
    Reads local ~/.codex/config.toml and ~/.codex/auth.json, extracts only the
    active provider settings and auth, and merges them into the remote Codex
    config/auth. This is the recommended path after CC Switch already changed
    your local Codex provider.

Alternative source:
  cc-switch
    Reads provider config/auth from ~/.cc-switch/cc-switch.db. Use
    --provider-name or --provider-id to choose one of the stored Codex providers.
    If omitted, the current CC Switch Codex provider is used.

What changes on each remote:
  - Backs up ~/.codex/config.toml and ~/.codex/auth.json when present.
  - Updates root provider keys such as model_provider, model, reasoning effort.
  - Updates only the active [model_providers.<name>] table when needed.
  - Writes ~/.codex/auth.json from the selected local provider auth.
  - With --sync-cc-switch-db, also mirrors local CC Switch Codex providers into
    the remote ~/.cc-switch/cc-switch.db providers-related tables.
  - Runs codex-provider sync by default to sync provider-bucket thread history.

Options:
  --list-providers             List local CC Switch Codex providers without secrets.
  --source active-files|cc-switch
  --provider-name NAME         CC Switch provider name, e.g. "DeepSeek".
  --provider-id ID             CC Switch provider id.
  --cc-switch-db PATH          Default: ~/.cc-switch/cc-switch.db.
  --codex-home PATH            Local Codex home. Default: ~/.codex.
  --remote-codex-home PATH     Remote Codex home. Default: ~/.codex.
  --remote-cc-switch-db PATH   Remote CC Switch DB. Default: ~/.cc-switch/cc-switch.db.
  --sync-cc-switch-db          Mirror local CC Switch Codex provider rows to remote CC Switch DB.
  --hosts-file PATH            SSH hosts, one per line. # comments allowed.
  --no-sync-history            Do not run codex-provider sync on remotes.
  --restart-codex              On desktop remotes, quit/kill Codex, sync, then codex app.
  --install-provider-sync      If missing remotely, install codex-provider-sync from GitHub with npm.
  --ssh-option OPT             Extra ssh option. Repeatable. Example: --ssh-option BatchMode=yes
  --dry-run                    Show selected provider and remote planned changes only.
  -h, --help                   Show this help.

Security:
  Secrets are never printed and are not passed as command-line arguments.
  Auth JSON is streamed over SSH stdin and written only to remote auth.json.
  CC Switch provider auth is included only when --sync-cc-switch-db is used.
USAGE
}

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

read_hosts_file() {
  local file="$1"
  [[ -f "$file" ]] || die "hosts file not found: $file"
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" ]] && HOSTS+=("$line")
  done < "$file"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --list-providers)
      LIST_PROVIDERS=1; shift ;;
    --source)
      SOURCE="${2:-}"; shift 2 ;;
    --provider-name)
      PROVIDER_NAME="${2:-}"; shift 2 ;;
    --provider-id)
      PROVIDER_ID="${2:-}"; shift 2 ;;
    --cc-switch-db)
      CC_SWITCH_DB="${2:-}"; shift 2 ;;
    --codex-home)
      CODEX_HOME_LOCAL="${2:-}"; shift 2 ;;
    --remote-codex-home)
      REMOTE_CODEX_HOME="${2:-}"; shift 2 ;;
    --remote-cc-switch-db)
      REMOTE_CC_SWITCH_DB="${2:-}"; shift 2 ;;
    --sync-cc-switch-db)
      SYNC_CC_SWITCH_DB=1; shift ;;
    --hosts-file)
      HOST_FILE="${2:-}"; shift 2 ;;
    --no-sync-history)
      SYNC_HISTORY=0; shift ;;
    --restart-codex)
      RESTART_CODEX=1; SYNC_HISTORY=1; shift ;;
    --install-provider-sync)
      INSTALL_PROVIDER_SYNC=1; shift ;;
    --ssh-option)
      SSH_OPTS+=("-o" "${2:-}"); shift 2 ;;
    --dry-run)
      DRY_RUN=1; shift ;;
    -h|--help)
      usage; exit 0 ;;
    --)
      shift; while [[ $# -gt 0 ]]; do HOSTS+=("$1"); shift; done ;;
    -*)
      die "unknown option: $1" ;;
    *)
      HOSTS+=("$1"); shift ;;
  esac
done

need_cmd ssh
need_cmd python3

case "$SOURCE" in
  active-files|cc-switch) ;;
  *) die "--source must be active-files or cc-switch" ;;
esac

if [[ -n "$HOST_FILE" ]]; then
  read_hosts_file "$HOST_FILE"
fi

local_payload() {
  python3 - "$SOURCE" "$CC_SWITCH_DB" "$CODEX_HOME_LOCAL" "$PROVIDER_NAME" "$PROVIDER_ID" "$DRY_RUN" "$SYNC_CC_SWITCH_DB" <<'PY'
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

source, db_path, codex_home, provider_name, provider_id, dry_run, sync_cc_switch_db = sys.argv[1:]
dry_run = dry_run == "1"
sync_cc_switch_db = sync_cc_switch_db == "1"
codex_home = Path(codex_home).expanduser()

ROOT_KEYS = {
    "model_provider",
    "model",
    "model_reasoning_effort",
    "disable_response_storage",
}

SENSITIVE_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|auth|authorization|bearer)", re.I)

def parse_root_keys(text):
    values = {}
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_table = True
            continue
        if in_table or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key in ROOT_KEYS:
            values[key] = line.split("=", 1)[1].strip()
    return values

def extract_table(text, header):
    lines = text.splitlines()
    out = []
    collecting = False
    for line in lines:
        stripped = line.strip()
        if stripped == header:
            collecting = True
            out.append(line)
            continue
        if collecting and stripped.startswith("[") and stripped.endswith("]"):
            break
        if collecting:
            out.append(line)
    return "\n".join(out).rstrip() + ("\n" if out else "")

def scrub_auth_shape(auth):
    if not isinstance(auth, dict):
        return {}
    return {k: ("<redacted>" if SENSITIVE_KEY_RE.search(k) else type(v).__name__) for k, v in auth.items()}

def strip_env_key_lines(text):
    out = []
    removed = 0
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("env_key") and "=" in stripped:
            removed += 1
            continue
        out.append(line)
    return "\n".join(out).rstrip() + ("\n" if out else ""), removed

def auth_has_api_key(auth):
    return isinstance(auth, dict) and any("key" in str(k).lower() for k in auth.keys())

def sanitize_provider_table_for_remote(table, auth):
    if not auth_has_api_key(auth):
        return table, 0
    return strip_env_key_lines(table)

def sanitize_cc_switch_provider_row(row):
    row = dict(row)
    try:
        settings = json.loads(row.get("settings_config") or "{}")
    except Exception:
        return row, 0
    if not auth_has_api_key(settings.get("auth")):
        return row, 0
    config, removed = strip_env_key_lines(settings.get("config") or "")
    if removed:
        settings["config"] = config
        row["settings_config"] = json.dumps(settings, ensure_ascii=False)
    return row, removed

def load_cc_provider():
    path = Path(db_path).expanduser()
    if not path.exists():
        raise SystemExit(f"CC Switch DB not found: {path}")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    where = "app_type='codex'"
    args = []
    if provider_id:
        where += " and id=?"
        args.append(provider_id)
    elif provider_name:
        where += " and name=?"
        args.append(provider_name)
    else:
        where += " and is_current=1"
    rows = list(con.execute(f"select id,name,is_current,settings_config from providers where {where}", args))
    if len(rows) != 1:
        raise SystemExit(f"expected one CC Switch provider, found {len(rows)}")
    row = rows[0]
    settings = json.loads(row["settings_config"])
    config_text = settings.get("config") or ""
    auth = settings.get("auth") or {}
    return {
        "source": "cc-switch",
        "provider_id": row["id"],
        "provider_name": row["name"],
        "is_current": bool(row["is_current"]),
        "config_text": config_text,
        "auth": None if dry_run else auth,
        "auth_shape": scrub_auth_shape(auth),
    }

def load_cc_switch_rows():
    if not sync_cc_switch_db:
        return None
    path = Path(db_path).expanduser()
    if not path.exists():
        raise SystemExit(f"CC Switch DB not found: {path}")
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    providers = []
    removed_env_keys = 0
    for row in con.execute("select * from providers where app_type='codex'"):
        sanitized, removed = sanitize_cc_switch_provider_row(dict(row))
        providers.append(sanitized)
        removed_env_keys += removed
    endpoints = [dict(row) for row in con.execute("select * from provider_endpoints where app_type='codex'")]
    health = [dict(row) for row in con.execute("select * from provider_health where app_type='codex'")]
    settings = [dict(row) for row in con.execute("select * from settings where key like 'codex%' or key like '%codex%'")]
    return {
        "providers": providers if not dry_run else [
            {k: ("<redacted-settings_config>" if k == "settings_config" else v) for k, v in row.items()}
            for row in providers
        ],
        "provider_endpoints": endpoints,
        "provider_health": health,
        "settings": settings,
        "counts": {
            "providers": len(providers),
            "provider_endpoints": len(endpoints),
            "provider_health": len(health),
            "settings": len(settings),
            "removed_env_key_lines": removed_env_keys,
        },
    }

def load_active_files():
    config_path = codex_home / "config.toml"
    auth_path = codex_home / "auth.json"
    if not config_path.exists():
        raise SystemExit(f"local config not found: {config_path}")
    config_text = config_path.read_text()
    if not auth_path.exists():
        raise SystemExit(f"local auth not found: {auth_path}")
    auth = json.loads(auth_path.read_text())
    return {
        "source": "active-files",
        "provider_id": None,
        "provider_name": "active local ~/.codex",
        "is_current": True,
        "config_text": config_text,
        "auth": None if dry_run else auth,
        "auth_shape": scrub_auth_shape(auth),
    }

selected = load_cc_provider() if source == "cc-switch" else load_active_files()
config_text = selected["config_text"]
root = parse_root_keys(config_text)
provider_expr = root.get("model_provider")
provider_key = None
if provider_expr and len(provider_expr) >= 2 and provider_expr[0] == provider_expr[-1] == '"':
    provider_key = provider_expr[1:-1]
provider_table = extract_table(config_text, f"[model_providers.{provider_key}]") if provider_key else ""
provider_table, provider_table_removed_env_keys = sanitize_provider_table_for_remote(
    provider_table,
    selected["auth"] or selected["auth_shape"] or {},
)

payload = {
    "source": selected["source"],
    "provider_id": selected["provider_id"],
    "provider_name": selected["provider_name"],
    "is_current": selected["is_current"],
    "root_keys": root,
    "provider_key": provider_key,
    "provider_table": provider_table,
    "provider_table_removed_env_keys": provider_table_removed_env_keys,
    "auth": selected["auth"],
    "auth_shape": selected["auth_shape"],
    "cc_switch": load_cc_switch_rows(),
}
print(json.dumps(payload, ensure_ascii=False))
PY
}

list_providers() {
  python3 - "$CC_SWITCH_DB" <<'PY'
import json
import sqlite3
import sys
from pathlib import Path
path = Path(sys.argv[1]).expanduser()
if not path.exists():
    raise SystemExit(f"CC Switch DB not found: {path}")
con = sqlite3.connect(path)
con.row_factory = sqlite3.Row
rows = list(con.execute("select id,name,is_current,settings_config from providers where app_type='codex' order by is_current desc, name"))
for row in rows:
    settings = json.loads(row["settings_config"])
    config = settings.get("config", "")
    model_provider = ""
    model = ""
    for line in config.splitlines():
        stripped = line.strip()
        if stripped.startswith("model_provider"):
            model_provider = stripped.split("=", 1)[1].strip().strip('"')
        elif stripped.startswith("model ") or stripped.startswith("model="):
            model = stripped.split("=", 1)[1].strip().strip('"')
    marker = "*" if row["is_current"] else " "
    print(f"{marker} {row['name']}  id={row['id']}  model_provider={model_provider}  model={model}")
PY
}

if [[ "$LIST_PROVIDERS" -eq 1 ]]; then
  list_providers
  exit 0
fi

[[ ${#HOSTS[@]} -gt 0 ]] || die "provide at least one host, --hosts-file, or use --list-providers"

remote_script() {
  cat <<'REMOTE'
set -euo pipefail

remote_codex_home=__REMOTE_CODEX_HOME_JSON__
remote_cc_switch_db=__REMOTE_CC_SWITCH_DB_JSON__
sync_history=__SYNC_HISTORY__
sync_cc_switch_db=__SYNC_CC_SWITCH_DB__
restart_codex=__RESTART_CODEX__
install_provider_sync=__INSTALL_PROVIDER_SYNC__
dry_run=__DRY_RUN__

log() {
  printf '[remote:%s] %s\n' "$(hostname 2>/dev/null || printf unknown)" "$*"
}

export PATH="${CODEX_INSTALL_DIR:-$HOME/.local/bin}:$HOME/.local/bin:$HOME/.npm-global/bin:$PATH"
for candidate in \
  "$HOME/.local/bin/codex" \
  "$HOME/.nvm/versions/node/"*/bin/codex \
  "/opt/homebrew/bin/codex" \
  "/usr/local/bin/codex" \
  "/usr/bin/codex"
do
  if [[ -x "$candidate" ]]; then
    export PATH="$(dirname "$candidate"):$PATH"
    break
  fi
done
for candidate in \
  "$HOME/.local/bin/codex-provider" \
  "$HOME/.nvm/versions/node/"*/bin/codex-provider \
  "/opt/homebrew/bin/codex-provider" \
  "/usr/local/bin/codex-provider" \
  "/usr/bin/codex-provider"
do
  if [[ -x "$candidate" ]]; then
    export PATH="$(dirname "$candidate"):$PATH"
    break
  fi
done

payload_file="$(mktemp)"
trap 'rm -f "$payload_file"' EXIT
cat > "$payload_file"

python3 - "$payload_file" "$remote_codex_home" "$dry_run" "$sync_cc_switch_db" "$remote_cc_switch_db" <<'PY'
from pathlib import Path
import json
import os
import sqlite3
import sys
import time

payload = json.loads(Path(sys.argv[1]).read_text())
codex_home_arg = sys.argv[2]
dry_run = sys.argv[3] == "1"
sync_cc_switch_db = sys.argv[4] == "1"
remote_cc_switch_db = sys.argv[5]
codex_home = Path(codex_home_arg.replace("~", str(Path.home()), 1)).expanduser()
cc_switch_db = Path(remote_cc_switch_db.replace("~", str(Path.home()), 1)).expanduser()
config_path = codex_home / "config.toml"
auth_path = codex_home / "auth.json"

def replace_or_append_root(text, key, value_expr):
    lines = text.splitlines()
    out = []
    replaced = False
    in_table = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if not replaced:
                out.append(f"{key} = {value_expr}")
                replaced = True
            in_table = True
        if not in_table and "=" in stripped and stripped.split("=", 1)[0].strip() == key:
            if not replaced:
                out.append(f"{key} = {value_expr}")
                replaced = True
            continue
        out.append(line)
    if not replaced:
        out.append(f"{key} = {value_expr}")
    return "\n".join(out).rstrip() + "\n"

def replace_table(text, header, block):
    if not block:
        return text.rstrip() + "\n"
    lines = text.splitlines()
    out = []
    i = 0
    replaced = False
    while i < len(lines):
        if lines[i].strip() == header:
            if out and out[-1].strip():
                out.append("")
            out.extend(block.rstrip().splitlines())
            replaced = True
            i += 1
            while i < len(lines):
                stripped = lines[i].strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    if not replaced:
        if out and out[-1].strip():
            out.append("")
        out.extend(block.rstrip().splitlines())
    return "\n".join(out).rstrip() + "\n"

summary = {
    "source": payload["source"],
    "provider_name": payload["provider_name"],
    "provider_id": payload["provider_id"],
    "provider_key": payload["provider_key"],
    "root_keys": payload["root_keys"],
    "auth_keys": sorted((payload.get("auth_shape") or {}).keys()),
    "provider_table_removed_env_keys": payload.get("provider_table_removed_env_keys", 0),
    "cc_switch_counts": (payload.get("cc_switch") or {}).get("counts"),
}
print(json.dumps({"selected": summary}, ensure_ascii=False))

if dry_run:
    print("dry-run: no remote files changed")
    raise SystemExit(0)

codex_home.mkdir(parents=True, exist_ok=True)
os.chmod(codex_home, 0o700)
existing = config_path.read_text() if config_path.exists() else ""
updated = existing
for key, value_expr in payload["root_keys"].items():
    updated = replace_or_append_root(updated, key, value_expr)
if payload.get("provider_key") and payload.get("provider_table"):
    updated = replace_table(updated, f"[model_providers.{payload['provider_key']}]", payload["provider_table"])

stamp = time.strftime("%Y%m%d-%H%M%S")
if config_path.exists():
    config_path.with_name(f"config.toml.bak.provider-sync-{stamp}").write_text(existing)
config_path.write_text(updated)
os.chmod(config_path, 0o600)

auth = payload.get("auth")
if not isinstance(auth, dict) or not auth:
    raise SystemExit("payload auth is empty or invalid")
if auth_path.exists():
    auth_path.with_name(f"auth.json.bak.provider-sync-{stamp}").write_text(auth_path.read_text())
auth_path.write_text(json.dumps(auth, indent=2) + "\n")
os.chmod(auth_path, 0o600)
print(f"updated {config_path} and {auth_path}")

def ensure_cc_switch_schema(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id TEXT NOT NULL,
            app_type TEXT NOT NULL,
            name TEXT NOT NULL,
            settings_config TEXT NOT NULL,
            website_url TEXT,
            category TEXT,
            created_at INTEGER,
            sort_index INTEGER,
            notes TEXT,
            icon TEXT,
            icon_color TEXT,
            meta TEXT NOT NULL DEFAULT '{}',
            is_current BOOLEAN NOT NULL DEFAULT 0,
            in_failover_queue BOOLEAN NOT NULL DEFAULT 0,
            cost_multiplier TEXT NOT NULL DEFAULT '1.0',
            limit_daily_usd TEXT,
            limit_monthly_usd TEXT,
            provider_type TEXT,
            PRIMARY KEY (id, app_type)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS provider_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id TEXT NOT NULL,
            app_type TEXT NOT NULL,
            url TEXT NOT NULL,
            added_at INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS provider_health (
            provider_id TEXT NOT NULL,
            app_type TEXT NOT NULL,
            is_healthy INTEGER NOT NULL DEFAULT 1,
            consecutive_failures INTEGER NOT NULL DEFAULT 0,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_error TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (provider_id, app_type)
        )
    """)
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

def sync_table_rows(con, table, rows, key_cols):
    if not rows:
        return 0
    cols = list(rows[0].keys())
    placeholders = ", ".join(["?"] * len(cols))
    quoted_cols = ", ".join(cols)
    update_cols = [c for c in cols if c not in key_cols]
    update_expr = ", ".join([f"{c}=excluded.{c}" for c in update_cols])
    sql = f"INSERT INTO {table} ({quoted_cols}) VALUES ({placeholders}) ON CONFLICT({', '.join(key_cols)}) DO UPDATE SET {update_expr}"
    for row in rows:
        con.execute(sql, [row.get(c) for c in cols])
    return len(rows)

if sync_cc_switch_db:
    cc_payload = payload.get("cc_switch")
    if not cc_payload:
        raise SystemExit("--sync-cc-switch-db requested but payload has no cc_switch data")
    cc_switch_db.parent.mkdir(parents=True, exist_ok=True)
    if cc_switch_db.exists():
        backup = cc_switch_db.with_name(f"cc-switch.db.bak.provider-sync-{stamp}")
        backup.write_bytes(cc_switch_db.read_bytes())
    con = sqlite3.connect(cc_switch_db)
    try:
        ensure_cc_switch_schema(con)
        con.execute("delete from providers where app_type='codex'")
        con.execute("delete from provider_endpoints where app_type='codex'")
        con.execute("delete from provider_health where app_type='codex'")
        con.executemany(
            """
            INSERT INTO providers (
                id, app_type, name, settings_config, website_url, category,
                created_at, sort_index, notes, icon, icon_color, meta,
                is_current, in_failover_queue, cost_multiplier, limit_daily_usd,
                limit_monthly_usd, provider_type
            ) VALUES (
                :id, :app_type, :name, :settings_config, :website_url, :category,
                :created_at, :sort_index, :notes, :icon, :icon_color, :meta,
                :is_current, :in_failover_queue, :cost_multiplier, :limit_daily_usd,
                :limit_monthly_usd, :provider_type
            )
            """,
            cc_payload.get("providers") or [],
        )
        endpoints = cc_payload.get("provider_endpoints") or []
        for row in endpoints:
            con.execute(
                "insert into provider_endpoints (provider_id, app_type, url, added_at) values (?, ?, ?, ?)",
                [row.get("provider_id"), row.get("app_type"), row.get("url"), row.get("added_at")],
            )
        sync_table_rows(con, "provider_health", cc_payload.get("provider_health") or [], ["provider_id", "app_type"])
        sync_table_rows(con, "settings", cc_payload.get("settings") or [], ["key"])
        con.commit()
    finally:
        con.close()
    os.chmod(cc_switch_db, 0o600)
    print(f"updated {cc_switch_db} codex providers={len(cc_payload.get('providers') or [])}")
PY

  if [[ "$dry_run" -eq 1 ]]; then
  if [[ "$sync_cc_switch_db" -eq 1 ]]; then
    log "dry-run: would mirror local CC Switch Codex providers to $remote_cc_switch_db"
  fi
  if [[ "$sync_history" -eq 1 ]]; then
    if [[ "$restart_codex" -eq 1 ]]; then
      log "dry-run: would quit/kill Codex, run codex-provider sync, then codex app"
    else
      log "dry-run: would run codex-provider sync"
    fi
  fi
  exit 0
fi

if [[ "$sync_history" -eq 1 ]]; then
  if ! command -v codex-provider >/dev/null 2>&1; then
    if [[ "$install_provider_sync" -eq 1 ]]; then
      if ! command -v npm >/dev/null 2>&1; then
        printf 'codex-provider missing and npm not found; cannot install codex-provider-sync\n' >&2
        exit 127
      fi
      npm install -g git+https://github.com/Dailin521/codex-provider-sync.git >/dev/null
    else
      printf 'codex-provider missing; rerun with --install-provider-sync or install codex-provider-sync first\n' >&2
      exit 127
    fi
  fi

  if [[ "$restart_codex" -eq 1 ]]; then
    osascript -e 'quit app "Codex"' >/dev/null 2>&1 || true
    pkill -f 'app-server' >/dev/null 2>&1 || true
    pkill -f 'Codex.app' >/dev/null 2>&1 || true
    codex-provider sync --codex-home "$remote_codex_home"
    nohup codex app >/tmp/codex-app-restart.log 2>&1 &
    log "codex-provider sync ran and codex app restart was requested"
  else
    codex-provider sync --codex-home "$remote_codex_home"
    log "codex-provider sync ran"
  fi
fi

if command -v codex >/dev/null 2>&1; then
  codex --version >/dev/null || true
fi
log "provider sync completed"
REMOTE
}

json_quote() {
  python3 - "$1" <<'PY'
import json, sys
print(json.dumps(sys.argv[1]))
PY
}

build_remote_script() {
  local remote_home_json
  local remote_cc_switch_db_json
  remote_home_json="$(json_quote "$REMOTE_CODEX_HOME")"
  remote_cc_switch_db_json="$(json_quote "$REMOTE_CC_SWITCH_DB")"
  remote_script \
    | sed "s|__REMOTE_CODEX_HOME_JSON__|$remote_home_json|g" \
    | sed "s|__REMOTE_CC_SWITCH_DB_JSON__|$remote_cc_switch_db_json|g" \
    | sed "s|__SYNC_HISTORY__|$SYNC_HISTORY|g" \
    | sed "s|__SYNC_CC_SWITCH_DB__|$SYNC_CC_SWITCH_DB|g" \
    | sed "s|__RESTART_CODEX__|$RESTART_CODEX|g" \
    | sed "s|__INSTALL_PROVIDER_SYNC__|$INSTALL_PROVIDER_SYNC|g" \
    | sed "s|__DRY_RUN__|$DRY_RUN|g"
}

failures=0
script="$(build_remote_script)"
for host in "${HOSTS[@]}"; do
  printf '\n==> %s\n' "$host"
  remote_tmp=""
  if ! remote_tmp="$(ssh "${SSH_OPTS[@]}" "$host" "mktemp /tmp/codex-provider-sync.XXXXXX.sh")"; then
    printf 'FAILED: %s (could not create remote temp script)\n' "$host" >&2
    failures=$((failures + 1))
    continue
  fi
  if ! ssh "${SSH_OPTS[@]}" "$host" "cat > '$remote_tmp' && chmod 700 '$remote_tmp'" <<<"$script"; then
    printf 'FAILED: %s (could not upload remote temp script)\n' "$host" >&2
    ssh "${SSH_OPTS[@]}" "$host" "rm -f '$remote_tmp'" >/dev/null 2>&1 || true
    failures=$((failures + 1))
    continue
  fi
  if ! local_payload | ssh "${SSH_OPTS[@]}" "$host" "bash '$remote_tmp'; rc=\$?; rm -f '$remote_tmp'; exit \$rc"; then
    printf 'FAILED: %s\n' "$host" >&2
    failures=$((failures + 1))
  fi
done

if [[ "$failures" -gt 0 ]]; then
  die "$failures host(s) failed"
fi

printf '\nAll hosts synced successfully.\n'
