#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Callable, TextIO


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
JIRA_REQUEST_MODULE_PATH = Path(__file__).with_name("jira_request.py")


def load_jira_request_module():
    spec = importlib.util.spec_from_file_location(
        "jira_request_for_jira_get",
        JIRA_REQUEST_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_basic_auth_credentials(
    env_path: Path = DEFAULT_ENV_PATH,
) -> tuple[str, str]:
    return load_jira_request_module().load_basic_auth_credentials(env_path)


def fetch_jira_json(
    path_or_url: str,
    query_params: dict[str, str] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    token_fetcher: Callable[[Path], str] | None = None,
    connection_factory=None,
):
    jira_request = load_jira_request_module()
    if token_fetcher is None:
        token_fetcher = jira_request.default_token_fetcher
    if connection_factory is None:
        connection_factory = jira_request.http.client.HTTPSConnection
    return jira_request.fetch_jira_json(
        path_or_url,
        query_params=query_params,
        env_path=env_path,
        token_fetcher=token_fetcher,
        connection_factory=connection_factory,
    )


def parse_query_args(items: list[str] | None) -> dict[str, str]:
    if not items:
        return {}

    query_params = {}
    for item in items:
        if "=" not in item:
            raise ValueError(
                f"Invalid query parameter {item!r}. Expected name=value."
            )
        name, value = item.split("=", 1)
        query_params[name] = value
    return query_params


def main(
    argv: list[str] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    token_fetcher: Callable[[Path], str] | None = None,
    connection_factory=None,
    stdout: TextIO = sys.stdout,
):
    parser = argparse.ArgumentParser(
        description="GET a Jira REST API resource using Basic Auth and accessToken."
    )
    parser.add_argument(
        "path_or_url",
        help="Absolute Jira URL or REST path, for example /rest/api/2/issue/942266",
    )
    parser.add_argument(
        "--query",
        action="append",
        metavar="NAME=VALUE",
        help="Optional query parameter. Repeat for multiple values.",
    )
    args = parser.parse_args(argv)

    payload = fetch_jira_json(
        args.path_or_url,
        query_params=parse_query_args(args.query),
        env_path=env_path,
        token_fetcher=token_fetcher,
        connection_factory=connection_factory,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
    return payload


def cli() -> int:
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
