#!/usr/bin/env python3

from __future__ import annotations

import base64
import http.client
import importlib.util
import json
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode, urlsplit


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
JIRA_BASE_URL = "https://jira.agoralab.co"
ACCESS_TOKEN_MODULE_PATH = Path(__file__).with_name("get_access_token.py")


def load_access_token_module():
    spec = importlib.util.spec_from_file_location(
        "get_access_token_for_jira_request",
        ACCESS_TOKEN_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_basic_auth_credentials(
    env_path: Path = DEFAULT_ENV_PATH,
) -> tuple[str, str]:
    token_module = load_access_token_module()
    raw_env = token_module.parse_env_file(env_path)
    username = raw_env.get("jira_user")
    password = raw_env.get("jira_pwd")
    missing = [
        key
        for key, value in (("jira_user", username), ("jira_pwd", password))
        if not value
    ]
    if missing:
        raise ValueError(
            "Missing required env vars: " + ", ".join(missing)
        )
    return username, password


def build_basic_auth_header(username: str, password: str) -> str:
    encoded = base64.b64encode(
        f"{username}:{password}".encode("utf-8")
    ).decode("ascii")
    return f"Basic {encoded}"


def build_url(path_or_url: str, query_params: dict[str, str] | None) -> str:
    if path_or_url.startswith(("http://", "https://")):
        url = path_or_url
    else:
        url = f"{JIRA_BASE_URL.rstrip('/')}/{path_or_url.lstrip('/')}"

    if not query_params:
        return url
    return f"{url}?{urlencode(query_params)}"


def default_token_fetcher(env_path: Path) -> str:
    token_module = load_access_token_module()
    return token_module.fetch_access_token(token_module.load_env(env_path))


def build_request_target(request_url: str) -> tuple[str, str]:
    parsed = urlsplit(request_url)
    request_target = parsed.path or "/"
    if parsed.query:
        request_target = f"{request_target}?{parsed.query}"
    return parsed.netloc, request_target


def request_jira_json(
    method: str,
    path_or_url: str,
    *,
    query_params: dict[str, str] | None = None,
    json_body: dict | None = None,
    expect_json: bool = True,
    env_path: Path = DEFAULT_ENV_PATH,
    token_fetcher: Callable[[Path], str] = default_token_fetcher,
    connection_factory=http.client.HTTPSConnection,
):
    username, password = load_basic_auth_credentials(env_path)
    access_token = token_fetcher(env_path)
    request_url = build_url(path_or_url, query_params)
    host, request_target = build_request_target(request_url)
    method = method.upper()
    body_bytes = None
    if json_body is not None:
        body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")

    connection = connection_factory(host, timeout=30)
    try:
        connection.putrequest(method, request_target)
        connection.putheader("Accept", "application/json")
        connection.putheader("Content-Type", "application/json")
        connection.putheader(
            "Authorization",
            build_basic_auth_header(username, password),
        )
        # urllib rewrites this header to Accesstoken, which Jira rejects.
        connection.putheader("accessToken", access_token)
        if body_bytes is not None:
            connection.putheader("Content-Length", str(len(body_bytes)))
        connection.endheaders()
        if body_bytes is not None:
            connection.send(body_bytes)
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
    finally:
        connection.close()

    if response.status >= 400:
        detail = body.strip() or getattr(response, "reason", "Unknown error")
        raise RuntimeError(
            f"Jira {method} request failed with HTTP {response.status}: {detail}"
        )

    if not body.strip():
        if expect_json:
            raise RuntimeError(f"Jira {method} response was empty.")
        return None

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        if not expect_json:
            return body
        raise RuntimeError(
            f"Jira {method} response was not valid JSON."
        ) from exc


def fetch_jira_json(
    path_or_url: str,
    query_params: dict[str, str] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    token_fetcher: Callable[[Path], str] = default_token_fetcher,
    connection_factory=http.client.HTTPSConnection,
):
    return request_jira_json(
        "GET",
        path_or_url,
        query_params=query_params,
        env_path=env_path,
        token_fetcher=token_fetcher,
        connection_factory=connection_factory,
    )
