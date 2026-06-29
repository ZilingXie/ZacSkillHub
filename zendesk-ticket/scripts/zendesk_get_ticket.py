#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import urlsplit

from zendesk_client import DEFAULT_ENV_PATH, fetch_zendesk_json


TICKET_URL_RE = re.compile(r"/tickets/(\d+)(?:\.json)?(?:$|[/?#])")


def extract_ticket_id(ticket_id_or_url: str) -> str:
    if ticket_id_or_url.isdigit():
        return ticket_id_or_url

    parsed = urlsplit(ticket_id_or_url)
    match = TICKET_URL_RE.search(parsed.path)
    if match:
        return match.group(1)

    raise ValueError(
        "Expected a numeric Zendesk ticket id or a Zendesk ticket URL."
    )


def summarize_ticket(payload: dict[str, Any]) -> dict[str, Any]:
    ticket = payload.get("ticket")
    if not isinstance(ticket, dict):
        raise RuntimeError("Zendesk response did not contain a ticket object.")

    return {
        "id": ticket.get("id"),
        "subject": ticket.get("subject"),
        "status": ticket.get("status"),
        "priority": ticket.get("priority"),
        "type": ticket.get("type"),
        "requester_id": ticket.get("requester_id"),
        "submitter_id": ticket.get("submitter_id"),
        "assignee_id": ticket.get("assignee_id"),
        "organization_id": ticket.get("organization_id"),
        "created_at": ticket.get("created_at"),
        "updated_at": ticket.get("updated_at"),
        "tags": ticket.get("tags", []),
        "description": ticket.get("description"),
    }


def main(
    argv: list[str] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    stdout: TextIO = sys.stdout,
) -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Read a Zendesk ticket by id or ticket URL."
    )
    parser.add_argument("ticket", help="Zendesk ticket id or ticket URL.")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Print the raw Zendesk API response instead of a compact summary.",
    )
    args = parser.parse_args(argv)

    ticket_id = extract_ticket_id(args.ticket)
    payload = fetch_zendesk_json(
        f"/api/v2/tickets/{ticket_id}.json",
        env_path=env_path,
    )
    output = payload if args.raw else summarize_ticket(payload)
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
