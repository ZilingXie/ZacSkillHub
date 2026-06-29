#!/usr/bin/env python3

from __future__ import annotations

import base64
import http.client
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
REQUIRED_ENV_VARS = (
    "ZENDESK_SUBDOMAIN",
    "ZENDESK_USERNAME",
    "ZENDESK_PASSWORD",
)


def parse_env_file(env_path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    if not env_path.exists():
        raise ValueError(
            f"Missing {env_path}. Copy .env.example to .env and fill in Zendesk credentials."
        )

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(env_path.read_text().splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Invalid line {line_number} in {env_path}: expected KEY=VALUE."
            )
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_env(env_path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    values = parse_env_file(env_path)
    missing = [key for key in REQUIRED_ENV_VARS if not values.get(key)]
    if missing:
        raise ValueError("Missing required env vars: " + ", ".join(missing))
    return values


def build_base_url(subdomain: str) -> str:
    normalized = subdomain.strip()
    if not normalized:
        raise ValueError("ZENDESK_SUBDOMAIN must not be empty.")
    if normalized.startswith(("http://", "https://")):
        parsed = urlsplit(normalized)
        if not parsed.netloc:
            raise ValueError("ZENDESK_SUBDOMAIN URL is invalid.")
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    if normalized.endswith(".zendesk.com"):
        return f"https://{normalized}"
    return f"https://{normalized}.zendesk.com"


def build_basic_auth_header(username: str, password: str) -> str:
    encoded = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


def build_url(
    path_or_url: str,
    query_params: dict[str, str | int] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
) -> str:
    env = load_env(env_path)
    base_url = build_base_url(env["ZENDESK_SUBDOMAIN"])
    if path_or_url.startswith(("http://", "https://")):
        url = path_or_url
    else:
        url = f"{base_url.rstrip('/')}/{path_or_url.lstrip('/')}"

    if not query_params:
        return url
    separator = "&" if urlsplit(url).query else "?"
    return f"{url}{separator}{urlencode(query_params)}"


def build_request_target(request_url: str) -> tuple[str, str]:
    parsed = urlsplit(request_url)
    if parsed.scheme != "https":
        raise ValueError("Zendesk requests must use HTTPS.")
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return parsed.netloc, request_target


def explain_http_error(status: int, body: str) -> str:
    detail = body.strip()
    if status == 401:
        hint = (
            "Unauthorized. Check ZENDESK_USERNAME, ZENDESK_PASSWORD, account permissions, "
            "and whether password-based Basic Auth is enabled for this Zendesk instance."
        )
    elif status == 403:
        hint = "Forbidden. The account is authenticated but does not have permission for this resource."
    elif status == 404:
        hint = "Not found. The ticket or resource does not exist, or this account cannot see it."
    elif status == 429:
        hint = "Rate limited. Wait before retrying."
    else:
        hint = "Zendesk request failed."

    if detail:
        return f"{hint} Response body: {detail}"
    return hint


def request_zendesk_json(
    method: str,
    path_or_url: str,
    *,
    query_params: dict[str, str | int] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    connection_factory=http.client.HTTPSConnection,
) -> Any:
    method = method.upper()
    if method != "GET":
        raise ValueError("zendesk-ticket is read-only and only allows GET requests.")

    env = load_env(env_path)
    request_url = build_url(path_or_url, query_params=query_params, env_path=env_path)
    host, request_target = build_request_target(request_url)

    connection = connection_factory(host, timeout=30)
    try:
        connection.putrequest(method, request_target)
        connection.putheader("Accept", "application/json")
        connection.putheader(
            "Authorization",
            build_basic_auth_header(env["ZENDESK_USERNAME"], env["ZENDESK_PASSWORD"]),
        )
        connection.endheaders()
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
    finally:
        connection.close()

    if response.status >= 400:
        raise RuntimeError(
            f"Zendesk GET request failed with HTTP {response.status}: "
            f"{explain_http_error(response.status, body)}"
        )

    if not body.strip():
        raise RuntimeError("Zendesk GET response was empty.")

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Zendesk GET response was not valid JSON.") from exc


def fetch_zendesk_json(
    path_or_url: str,
    query_params: dict[str, str | int] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    connection_factory=http.client.HTTPSConnection,
) -> Any:
    return request_zendesk_json(
        "GET",
        path_or_url,
        query_params=query_params,
        env_path=env_path,
        connection_factory=connection_factory,
    )
