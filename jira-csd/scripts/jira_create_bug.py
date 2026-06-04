#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
JIRA_REQUEST_MODULE_PATH = Path(__file__).with_name("jira_request.py")
CREATE_ISSUE_PATH = "/rest/api/2/issue"
CREATE_ISSUE_URL = "https://jira.agoralab.co/rest/api/2/issue"
BROWSE_ISSUE_URL_TEMPLATE = "https://jira.agoralab.co/browse/{issue_key}"
TRANSITIONS_PATH_TEMPLATE = "/rest/api/2/issue/{issue_key}/transitions"
DEFAULT_ASSIGNEE = "xieziling@agora.io"
START_PROGRESS_TRANSITION_NAME = "Start Progress"
START_PROGRESS_CREATE_QUALITY_ID = "12611"


def load_jira_request_module():
    spec = importlib.util.spec_from_file_location(
        "jira_request_for_jira_create_bug",
        JIRA_REQUEST_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def normalize_summary(summary: str, customer: str | None = None) -> str:
    cleaned_summary = summary.strip()
    if not cleaned_summary:
        raise ValueError("Issue summary text cannot be empty.")

    cleaned_customer = (customer or "").strip()
    if not cleaned_customer:
        return cleaned_summary

    customer_prefix = f"[{cleaned_customer}] "
    if cleaned_summary.startswith(customer_prefix):
        return cleaned_summary
    return f"{customer_prefix}{cleaned_summary}"


def build_default_description(
    now: datetime,
    summary: str,
    vid: str,
    customer: str | None = None,
    cid: str | None = None,
) -> str:
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    if customer:
        lines.append(f"Customer: {customer}")
    if cid:
        lines.append(f"CID: {cid}")
    lines.append(f"VID: {vid}")
    lines.append("")
    lines.append("Problem Description:")
    lines.append(summary.strip())
    lines.append("")
    lines.append(f"Created at: {timestamp}")
    return "\n".join(lines)


def normalize_vid(vid: str | None) -> str:
    cleaned_vid = (vid or "").strip()
    if not cleaned_vid:
        raise ValueError("--vid is required and must be the real customer VID.")
    return cleaned_vid


def build_assignee_payload(assignee: str = DEFAULT_ASSIGNEE):
    return {"name": assignee}


def build_browse_url(issue_key: str) -> str:
    return BROWSE_ISSUE_URL_TEMPLATE.format(issue_key=issue_key)


def build_transition_payload(transition_id: str):
    return {
        "transition": {"id": transition_id},
        "fields": {
            "customfield_13903": {"id": START_PROGRESS_CREATE_QUALITY_ID},
        },
    }


def find_transition_by_name(
    transitions_response: dict,
    transition_name: str,
    issue_key: str,
):
    for transition in transitions_response.get("transitions", []):
        if transition.get("name", "").casefold() == transition_name.casefold():
            return transition

    available_transitions = ", ".join(
        transition.get("name", "<unknown>")
        for transition in transitions_response.get("transitions", [])
    ) or "none"
    raise RuntimeError(
        f'{issue_key} does not have a "{transition_name}" transition. '
        f"Available transitions: {available_transitions}"
    )


def build_issue_payload(
    summary: str,
    description: str | None,
    vid: str | None = None,
    customer: str | None = None,
    cid: str | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    now: datetime | None = None,
):
    jira_request = load_jira_request_module()
    reporter_name, _ = jira_request.load_basic_auth_credentials(env_path)
    now = now or datetime.now()
    normalized_summary = normalize_summary(summary, customer=customer)
    effective_vid = normalize_vid(vid)
    return {
        "fields": {
            "project": {"key": "CSD"},
            "issuetype": {"id": "10004"},
            "summary": normalized_summary,
            "description": description
            or build_default_description(
                now,
                summary=summary,
                vid=effective_vid,
                customer=customer,
                cid=cid,
            ),
            "components": [{"id": "25502"}],
            "versions": [{"id": "43913"}],
            "priority": {"id": "2"},
            "reporter": {"name": reporter_name},
            "customfield_10700": [
                {"id": "10200"},
                {"id": "10201"},
                {"id": "10207"},
            ],
            "customfield_11621": {"id": "11265"},
            "customfield_12110": {"id": "11261"},
            "customfield_12600": effective_vid,
            "customfield_13006": {
                "id": "11810",
                "child": {"id": "11818"},
            },
            "customfield_13206": {"id": "12001"},
            "customfield_13915": {
                "id": "12636",
                "child": {"id": "12642"},
            },
            "customfield_18003": {"id": "16209"},
            "customfield_23600": {"id": "21401"},
        }
    }


def default_request_func(method: str, path_or_url: str, **kwargs):
    return load_jira_request_module().request_jira_json(method, path_or_url, **kwargs)


def main(
    argv: list[str] | None = None,
    env_path: Path = DEFAULT_ENV_PATH,
    now_provider: Callable[[], datetime] = datetime.now,
    request_func: Callable[..., dict] = default_request_func,
    stdout: TextIO = sys.stdout,
):
    parser = argparse.ArgumentParser(
        description="Build or create a template CSD Bug issue."
    )
    parser.add_argument("--summary", required=True, help="Issue summary text.")
    parser.add_argument(
        "--customer",
        help="Optional customer name used to normalize the summary as [Customer] issue.",
    )
    parser.add_argument(
        "--cid",
        help="Optional customer CID for the default description template.",
    )
    parser.add_argument(
        "--vid",
        help="Customer VID. Required for all customer-ticket payloads, including dry-run preview.",
    )
    parser.add_argument(
        "--description",
        help="Optional issue description. If omitted, a customer-oriented template is generated.",
    )
    parser.add_argument(
        "--create",
        action="store_true",
        help="Actually create the Jira issue. Without this flag the command is dry-run only.",
    )
    args = parser.parse_args(argv)

    payload = build_issue_payload(
        summary=args.summary,
        description=args.description,
        vid=args.vid,
        customer=args.customer,
        cid=args.cid,
        env_path=env_path,
        now=now_provider(),
    )

    if not args.create:
        print(f"POST {CREATE_ISSUE_URL}", file=stdout)
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        print(
            f"Post-create action: assign the new issue to {DEFAULT_ASSIGNEE}.",
            file=stdout,
        )
        print(
            f"Post-create action: transition the new issue with '{START_PROGRESS_TRANSITION_NAME}'.",
            file=stdout,
        )
        print(
            f"Post-create result: include the full Jira link {build_browse_url('<new-key>')}.",
            file=stdout,
        )
        print(
            "Dry run only. Re-run with --create to create the Jira issue.",
            file=stdout,
        )
        return payload

    response = request_func(
        "POST",
        CREATE_ISSUE_PATH,
        json_body=payload,
        env_path=env_path,
    )
    issue_key = response.get("key")
    if not issue_key:
        raise RuntimeError("Jira create response did not include an issue key.")
    try:
        request_func(
            "PUT",
            f"/rest/api/2/issue/{issue_key}/assignee",
            json_body=build_assignee_payload(),
            expect_json=False,
            env_path=env_path,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Created {issue_key} but failed to assign it to {DEFAULT_ASSIGNEE}: {exc}"
        ) from exc

    try:
        transitions_path = TRANSITIONS_PATH_TEMPLATE.format(issue_key=issue_key)
        transitions_response = request_func(
            "GET",
            transitions_path,
            env_path=env_path,
        )
        transition = find_transition_by_name(
            transitions_response,
            START_PROGRESS_TRANSITION_NAME,
            issue_key,
        )
        request_func(
            "POST",
            transitions_path,
            json_body=build_transition_payload(transition["id"]),
            expect_json=False,
            env_path=env_path,
        )
    except Exception as exc:
        raise RuntimeError(
            f"Created {issue_key} and assigned it to {DEFAULT_ASSIGNEE}, "
            f"but failed to start progress: {exc}"
        ) from exc

    result = {key: response[key] for key in ("id", "key", "self") if key in response}
    result["assignee"] = DEFAULT_ASSIGNEE
    result["status"] = transition["to"]["name"]
    result["url"] = build_browse_url(issue_key)
    print(json.dumps(result, ensure_ascii=False, indent=2), file=stdout)
    return result


def cli() -> int:
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
