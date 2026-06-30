#!/usr/bin/env python3
import json
import subprocess
import sys


HOSTS = [
    ("tx-server", "tx-server"),
    ("vpn", "zactest"),
    ("n8n", "zaclin"),
    ("supportportal", "zacbot"),
]


REMOTE = r'''
set -eu
python3 - <<'RPT'
from pathlib import Path
import json
import os
import shutil
import sqlite3
import subprocess

home = Path.home()
result = {}
result["error"] = ""
result["hostname"] = subprocess.run(["hostname"], text=True, capture_output=True).stdout.strip()

config = home / ".codex/config.toml"
auth = home / ".codex/auth.json"
root = {}
tables = {}
if config.exists():
    current_table = None
    for line in config.read_text().splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            current_table = s.strip("[]")
            tables.setdefault(current_table, {})
            continue
        if current_table is None and "=" in s and not s.startswith("#"):
            key, value = [x.strip() for x in s.split("=", 1)]
            if key in {"model_provider", "model", "model_reasoning_effort"}:
                root[key] = value.strip('"')
        elif current_table and "=" in s and not s.startswith("#"):
            key, value = [x.strip() for x in s.split("=", 1)]
            tables[current_table][key] = value.strip('"')
result["codex_provider"] = root.get("model_provider", "unknown")
provider_table = tables.get(f"model_providers.{result['codex_provider']}", {})
result["provider_base_url"] = provider_table.get("base_url", "")
env_key = provider_table.get("env_key")
if env_key:
    result["env_key_status"] = f"{env_key} set" if os.environ.get(env_key) else f"{env_key} missing"
else:
    result["env_key_status"] = "none"

auth_obj = {}
auth_key = ""
if auth.exists():
    try:
        auth_obj = json.loads(auth.read_text())
        auth_key = auth_obj.get("OPENAI_API_KEY") or ""
    except Exception:
        auth_obj = {}
        auth_key = ""

def key_label(value):
    if not value:
        return "none"
    if value.startswith("ko_"):
        return "ko_" + value[-5:]
    if value.startswith("sk-"):
        return "sk-" + value[-5:]
    return "other-" + value[-5:]

result["auth_key_label"] = key_label(auth_key)

paths = os.environ.get("PATH", "").split(":")
for candidate in (
    [home / ".local/bin/codex"]
    + list((home / ".nvm/versions/node").glob("*/bin/codex"))
    + [Path("/opt/homebrew/bin/codex"), Path("/usr/local/bin/codex"), Path("/usr/bin/codex")]
):
    if candidate.exists() and os.access(candidate, os.X_OK):
        paths.insert(0, str(candidate.parent))
        break
os.environ["PATH"] = ":".join(map(str, paths))

codex = shutil.which("codex")
result["codex_cli"] = "missing"
result["login_status"] = "codex missing"
if codex:
    version = subprocess.run([codex, "--version"], text=True, capture_output=True, timeout=20)
    result["codex_cli"] = (version.stdout or version.stderr).strip() or codex
    status = subprocess.run([codex, "login", "status"], text=True, capture_output=True, timeout=20)
    raw = (status.stdout or status.stderr).strip()
    if status.returncode == 0 and "Logged in using an API key" in raw:
        result["login_status"] = "API key 登录成功: " + raw.split(" - ", 1)[-1]
    elif status.returncode == 0:
        result["login_status"] = raw or "logged in"
    else:
        result["login_status"] = "失败: " + (raw or f"exit {status.returncode}")

cc = home / ".cc-switch/cc-switch.db"
result["cc_switch_provider"] = "missing"
result["auth_match"] = "unknown"
if cc.exists():
    con = sqlite3.connect(cc)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "select name from providers where app_type='codex' and is_current=1 limit 1"
    ).fetchone()
    if row:
        result["cc_switch_provider"] = row["name"]
    else:
        result["cc_switch_provider"] = "no current provider"
    candidates = []
    rows = con.execute("select name, settings_config from providers where app_type='codex'").fetchall()
    for provider_row in rows:
        try:
            settings = json.loads(provider_row["settings_config"])
        except Exception:
            continue
        cfg = settings.get("config") or ""
        cfg_root = {}
        cfg_tables = {}
        current_table = None
        for line in cfg.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if s.startswith("[") and s.endswith("]"):
                current_table = s.strip("[]")
                cfg_tables.setdefault(current_table, {})
                continue
            if "=" not in s:
                continue
            key, value = [x.strip() for x in s.split("=", 1)]
            value = value.strip('"')
            if current_table is None:
                cfg_root[key] = value
            else:
                cfg_tables[current_table][key] = value
        cfg_provider = cfg_root.get("model_provider")
        cfg_provider_table = cfg_tables.get(f"model_providers.{cfg_provider}", {})
        cfg_base_url = cfg_provider_table.get("base_url", "")
        if cfg_provider == result["codex_provider"] and cfg_base_url == result["provider_base_url"]:
            provider_auth = settings.get("auth") or {}
            provider_key = provider_auth.get("OPENAI_API_KEY") or ""
            candidates.append((provider_row["name"], provider_key))
    if not candidates:
        result["auth_match"] = "no matching CC Switch provider"
    elif any(provider_key == auth_key and auth_key for _, provider_key in candidates):
        names = [name for name, provider_key in candidates if provider_key == auth_key]
        result["auth_match"] = "ok: " + ",".join(names)
    else:
        expected = ",".join(f"{name}:{key_label(provider_key)}" for name, provider_key in candidates)
        result["auth_match"] = f"mismatch: got {key_label(auth_key)} expected {expected}"
    con.close()

print(json.dumps(result, ensure_ascii=False))
RPT
'''


def code(value: str) -> str:
    value = value or ""
    return "`" + value.replace("`", "\\`") + "`"


def collect(host_alias: str) -> dict:
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host_alias, REMOTE]
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=45)
    except Exception as exc:
        return {"error": str(exc)}
    if proc.returncode != 0:
        return {"error": (proc.stderr or proc.stdout).strip() or f"ssh exit {proc.returncode}"}
    try:
        return json.loads(proc.stdout)
    except Exception as exc:
        return {"error": f"parse error: {exc}; output={proc.stdout[:300]}"}


def main() -> int:
    rows = []
    for server, alias in HOSTS:
        data = collect(alias)
        if data.get("error"):
            rows.append([server, alias, "error", data["error"], "unknown", "unknown", "unknown", "unknown"])
        else:
            rows.append([
                server,
                alias,
                data.get("codex_cli", "unknown"),
                data.get("login_status", "unknown"),
                data.get("codex_provider", "unknown"),
                data.get("env_key_status", "unknown"),
                data.get("auth_match", "unknown"),
                data.get("cc_switch_provider", "unknown"),
            ])

    print()
    print("| Server | SSH alias | Codex CLI | `codex login status` | Codex provider | Provider env_key | Auth match | CC Switch 当前 provider |")
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        print("| " + " | ".join(code(cell) for cell in row) + " |")
    return 1 if any(row[2] == "error" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
