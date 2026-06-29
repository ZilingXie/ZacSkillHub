#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO

from zendesk_client import DEFAULT_ENV_PATH, fetch_zendesk_json


TYPE_TICKET_RE = re.compile(r"(^|\s)type\s*:\s*ticket(\s|$)", re.IGNORECASE)


def normalize_query(query: str) -> str:
    stripped = query.strip()
    if not stripped:
        raise ValueError("Search query must not be empty.")
    if TYPE_TICKET_RE.search(stripped):
        return stripped
    return f"type:ticket {stripped}"


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": result.get("id"),
        "subject": result.get("subject"),
        "status": result.get("status"),
        "priority": result.get("priority"),
        "type": result.get("type"),
        "requester_id": result.get("requester_id"),
        "assignee_id": result.get("assignee_id"),
        "created_at": result.get("created_at"),
        "updated_at": result.get("updated_at"),
        "url": result.get("url"),
    }


def summarize_search(payload: dict[str, Any], limit: int) -> dict[str, Any]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise RuntimeError("Zendesk response did not contain a results list.")

    return {
        "count": payload.get("count"),
        "next_page": payload.get("next_page"),
        "previous_page": payload.get("previous_page"),
        "results": [summarize_result(result) for result in results[:limit]],
    }


def parse_limit(raw_limit: int) -> int:
    if raw_limit < 1:
        raise ValueError("--limit must be at least 1.")
    return min(raw_limit, 100)


def main(
    argv: list[str] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    stdout: TextIO = sys.stdout,
) -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Search Zendesk tickets with Zendesk search syntax."
    )
    parser.add_argument("query", help="Zendesk search query.")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum results to request and print. Defaults to 20, max 100.",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the raw Zendesk API response instead of a compact summary.",
    )
    args = parser.parse_args(argv)

    limit = parse_limit(args.limit)
    query = normalize_query(args.query)
    payload = fetch_zendesk_json(
        "/api/v2/search.json",
        query_params={"query": query, "per_page": limit},
        env_path=env_path,
    )
    output = payload if args.raw else summarize_search(payload, limit)
    print(json.dumps(output, ensure_ascii=False, indent=2), file=stdout)
    return output


def cli() -> int:
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
