#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Mapping, TextIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen as default_urlopen


OAUTH_TOKEN_URL = "https://oauth.agoralab.co/oauth/token"
DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
ENV_KEY_MAP = {
    "JIRA_OAUTH_CLIENT_ID": "client_id",
    "JIRA_OAUTH_CLIENT_SECRET": "client_secret",
    "JIRA_OAUTH_USERNAME": "username",
    "JIRA_OAUTH_PASSWORD": "password",
}


def parse_env_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        raise ValueError(f"Missing env file: {env_path}")

    raw_values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            raise ValueError(f"Invalid env line: {raw_line}")

        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        raw_values[key.strip()] = value

    return raw_values


def load_env(env_path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    raw_values = parse_env_file(env_path)
    missing = [key for key in ENV_KEY_MAP if not raw_values.get(key)]
    if missing:
        raise ValueError(
            "Missing required env vars: " + ", ".join(missing)
        )

    return {
        target_key: raw_values[source_key]
        for source_key, target_key in ENV_KEY_MAP.items()
    }


def fetch_access_token(
    config: Mapping[str, str],
    urlopen=default_urlopen,
) -> str:
    request = Request(
        OAUTH_TOKEN_URL,
        data=urlencode(
            {
                "grant_type": "password",
                "client_id": config["client_id"],
                "client_secret": config["client_secret"],
                "username": config["username"],
                "password": config["password"],
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        message = detail or exc.reason
        raise RuntimeError(
            f"OAuth token request failed with HTTP {exc.code}: {message}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"OAuth token request failed: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("OAuth token response was not valid JSON.") from exc

    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError("OAuth token response did not include access_token.")

    return access_token


def main(
    env_path: Path = DEFAULT_ENV_PATH,
    urlopen=default_urlopen,
    stdout: TextIO = sys.stdout,
) -> str:
    access_token = fetch_access_token(load_env(env_path), urlopen=urlopen)
    print(access_token, file=stdout)
    return access_token


def cli() -> int:
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
