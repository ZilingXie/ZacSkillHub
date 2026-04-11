#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Callable, TextIO
from urllib.parse import urlsplit


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
JIRA_REQUEST_MODULE_PATH = Path(__file__).with_name("jira_request.py")
JIRA_BROWSE_URL_TEMPLATE = "https://jira.agoralab.co/browse/{issue_key}"
ISSUE_PATH_TEMPLATE = "/rest/api/2/issue/{issue_key}"
TRANSITIONS_PATH_TEMPLATE = "/rest/api/2/issue/{issue_key}/transitions"
ISSUE_KEY_PATTERN = re.compile(r"^CSD-\d+$", re.IGNORECASE)
DONE_STATUS_CATEGORY_KEY = "done"
START_PROGRESS_TRANSITION_NAME = "Start Progress"
RESOLVE_ISSUE_TRANSITION_NAME = "Resolve Issue"
START_PROGRESS_CREATE_QUALITY_ID = "12611"
RESOLVE_ISSUE_RESOLUTION_ID = "13000"
RESOLVE_ISSUE_RESOLUTION_NAME = "Done"
RESOLVE_ISSUE_QUALIFIED_TO_ESCALATE_ID = "15003"
RESOLVE_ISSUE_QUALIFICATION_REASON = "Enough information to troubleshoot"
RESOLVE_ISSUE_KEY_CHECK_ITEM_ID = "16203"
RESOLVE_ISSUE_ACTION_LIST_ID = "13500"
RESOLVE_ISSUE_ACTUAL_WORKLOAD = "1"
RESOLVE_ISSUE_DEFAULT_FIX_VERSION_ID = "22241"
RESOLVE_ISSUE_FINAL_RESOLVED_COMPONENT_ID = "11227"
RESOLVE_ISSUE_ROOT_CAUSE_ABSTRACT_PARENT_ID = "11202"
RESOLVE_ISSUE_ROOT_CAUSE_ABSTRACT_CHILD_ID = "11271"
RESOLVE_ISSUE_SOLUTION = "Resolved during close-csd skill verification and test issue cleanup."
RESOLVE_ISSUE_ROOT_CAUSE = (
    "Issue was created for skill validation and is being resolved after the workflow check."
)
RESOLVE_ISSUE_SUGGESTED_TEST_SCOPE = "Smoke check the Jira workflow only."
RESOLVE_ISSUE_MERGED_BRANCH = "N/A"
SUPPORTED_ACTIVE_STATUSES = {"new", "inprogress"}


def load_jira_request_module():
    spec = importlib.util.spec_from_file_location(
        "jira_request_for_jira_resolve_csd",
        JIRA_REQUEST_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def default_request_func(method: str, path_or_url: str, **kwargs):
    return load_jira_request_module().request_jira_json(method, path_or_url, **kwargs)


def normalize_issue_input(issue_or_url: str) -> str:
    raw_value = issue_or_url.strip()
    if ISSUE_KEY_PATTERN.fullmatch(raw_value):
        return raw_value.upper()

    parsed = urlsplit(raw_value)
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 2 and path_parts[0] == "browse":
        candidate = path_parts[1]
        if ISSUE_KEY_PATTERN.fullmatch(candidate):
            return candidate.upper()

    raise ValueError(
        f"Invalid CSD issue input: {issue_or_url!r}. Expected a CSD key or Jira browse URL."
    )


def build_browse_url(issue_key: str) -> str:
    return JIRA_BROWSE_URL_TEMPLATE.format(issue_key=issue_key)


def build_start_progress_payload(transition_id: str) -> dict:
    return {
        "transition": {"id": transition_id},
        "fields": {
            "customfield_13903": {"id": START_PROGRESS_CREATE_QUALITY_ID},
        },
    }


def build_fix_versions(issue_payload: dict) -> list[dict]:
    version_ids = [
        version["id"]
        for version in issue_payload["fields"].get("versions", [])
        if version.get("id")
    ]
    if not version_ids:
        version_ids = [RESOLVE_ISSUE_DEFAULT_FIX_VERSION_ID]
    return [{"id": version_id} for version_id in version_ids]


def build_resolve_issue_payload(transition_id: str, fix_versions: list[dict]) -> dict:
    return {
        "transition": {"id": transition_id},
        "fields": {
            "resolution": {"id": RESOLVE_ISSUE_RESOLUTION_ID},
            "customfield_16704": {"id": RESOLVE_ISSUE_QUALIFIED_TO_ESCALATE_ID},
            "customfield_16901": RESOLVE_ISSUE_QUALIFICATION_REASON,
            "customfield_18000": [{"id": RESOLVE_ISSUE_KEY_CHECK_ITEM_ID}],
            "customfield_14600": [{"id": RESOLVE_ISSUE_ACTION_LIST_ID}],
            "customfield_12404": RESOLVE_ISSUE_ACTUAL_WORKLOAD,
            "customfield_12107": {"id": RESOLVE_ISSUE_FINAL_RESOLVED_COMPONENT_ID},
            "customfield_13701": RESOLVE_ISSUE_SOLUTION,
            "customfield_13704": [RESOLVE_ISSUE_MERGED_BRANCH],
            "customfield_13703": RESOLVE_ISSUE_SUGGESTED_TEST_SCOPE,
            "customfield_11708": RESOLVE_ISSUE_ROOT_CAUSE,
            "customfield_12100": {
                "id": RESOLVE_ISSUE_ROOT_CAUSE_ABSTRACT_PARENT_ID,
                "child": {"id": RESOLVE_ISSUE_ROOT_CAUSE_ABSTRACT_CHILD_ID},
            },
            "fixVersions": fix_versions,
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


def fetch_issue_details(
    request_func: Callable[..., dict],
    issue_key: str,
    env_path: Path,
) -> dict:
    return request_func(
        "GET",
        ISSUE_PATH_TEMPLATE.format(issue_key=issue_key),
        query_params={"fields": "status,resolution,versions"},
        env_path=env_path,
    )


def fetch_transitions(
    request_func: Callable[..., dict],
    issue_key: str,
    env_path: Path,
) -> dict:
    return request_func(
        "GET",
        TRANSITIONS_PATH_TEMPLATE.format(issue_key=issue_key),
        query_params={"expand": "transitions.fields"},
        env_path=env_path,
    )


def transition_issue(
    request_func: Callable[..., dict],
    issue_key: str,
    payload: dict,
    env_path: Path,
):
    return request_func(
        "POST",
        TRANSITIONS_PATH_TEMPLATE.format(issue_key=issue_key),
        json_body=payload,
        expect_json=False,
        env_path=env_path,
    )


def extract_issue_state(issue_payload: dict) -> tuple[str, str | None, str]:
    fields = issue_payload["fields"]
    status = fields["status"]
    resolution = fields.get("resolution") or {}
    return (
        status["name"],
        resolution.get("name"),
        status["statusCategory"]["key"],
    )


def safe_refresh_state(
    request_func: Callable[..., dict],
    issue_key: str | None,
    env_path: Path,
    current_status: str | None,
    current_resolution: str | None,
) -> tuple[str | None, str | None]:
    if not issue_key:
        return current_status, current_resolution

    try:
        issue_payload = fetch_issue_details(request_func, issue_key, env_path)
    except Exception:
        return current_status, current_resolution

    refreshed_status, refreshed_resolution, _ = extract_issue_state(issue_payload)
    return refreshed_status, refreshed_resolution


def process_issue(
    issue_or_url: str,
    *,
    resolve: bool,
    request_func: Callable[..., dict],
    env_path: Path,
) -> dict:
    issue_key = None
    before_status = None
    actions: list[str] = []
    current_status = None
    current_resolution = None

    result = {
        "input": issue_or_url,
        "key": None,
        "url": None,
        "before_status": None,
        "actions": [],
        "result": None,
        "status": None,
        "resolution": None,
        "dry_run": not resolve,
    }

    try:
        issue_key = normalize_issue_input(issue_or_url)
        result["key"] = issue_key
        result["url"] = build_browse_url(issue_key)

        issue_payload = fetch_issue_details(request_func, issue_key, env_path)
        before_status, current_resolution, status_category = extract_issue_state(
            issue_payload
        )
        fix_versions = build_fix_versions(issue_payload)
        current_status = before_status
        result["before_status"] = before_status

        if status_category == DONE_STATUS_CATEGORY_KEY:
            result["actions"] = []
            result["result"] = "skipped"
            result["status"] = current_status
            result["resolution"] = current_resolution
            return result

        normalized_status = before_status.casefold()
        if normalized_status == "new":
            actions = [START_PROGRESS_TRANSITION_NAME, RESOLVE_ISSUE_TRANSITION_NAME]
        elif normalized_status == "inprogress":
            actions = [RESOLVE_ISSUE_TRANSITION_NAME]
        else:
            raise RuntimeError(
                f"{issue_key} has unsupported active status {before_status!r}. "
                f"Expected one of: {', '.join(sorted(SUPPORTED_ACTIVE_STATUSES))}."
            )

        result["actions"] = actions

        if not resolve:
            result["result"] = "resolved"
            result["status"] = "RESOLVED"
            result["resolution"] = RESOLVE_ISSUE_RESOLUTION_NAME
            return result

        if START_PROGRESS_TRANSITION_NAME in actions:
            transitions_response = fetch_transitions(request_func, issue_key, env_path)
            start_transition = find_transition_by_name(
                transitions_response,
                START_PROGRESS_TRANSITION_NAME,
                issue_key,
            )
            transition_issue(
                request_func,
                issue_key,
                build_start_progress_payload(start_transition["id"]),
                env_path,
            )
            current_status = start_transition["to"]["name"]

        transitions_response = fetch_transitions(request_func, issue_key, env_path)
        resolve_transition = find_transition_by_name(
            transitions_response,
            RESOLVE_ISSUE_TRANSITION_NAME,
            issue_key,
        )
        transition_issue(
            request_func,
            issue_key,
            build_resolve_issue_payload(resolve_transition["id"], fix_versions),
            env_path,
        )
        current_status = resolve_transition["to"]["name"]
        current_resolution = RESOLVE_ISSUE_RESOLUTION_NAME

        final_issue = fetch_issue_details(request_func, issue_key, env_path)
        current_status, current_resolution, _ = extract_issue_state(final_issue)

        result["result"] = "resolved"
        result["status"] = current_status
        result["resolution"] = current_resolution
        return result
    except Exception as exc:
        current_status, current_resolution = safe_refresh_state(
            request_func,
            issue_key,
            env_path,
            current_status,
            current_resolution,
        )
        result["actions"] = actions
        result["result"] = "error"
        result["status"] = current_status
        result["resolution"] = current_resolution
        result["error"] = str(exc)
        return result


def main(
    argv: list[str] | None = None,
    *,
    env_path: Path = DEFAULT_ENV_PATH,
    request_func: Callable[..., dict] = default_request_func,
    stdout: TextIO = sys.stdout,
):
    parser = argparse.ArgumentParser(
        description="Dry-run or resolve Jira CSD issues to RESOLVED."
    )
    parser.add_argument(
        "issues",
        nargs="+",
        help="One or more Jira browse URLs or CSD-xxxxx keys.",
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Actually resolve the issues. Without this flag the command is dry-run only.",
    )
    args = parser.parse_args(argv)

    results = [
        process_issue(
            issue_or_url,
            resolve=args.resolve,
            request_func=request_func,
            env_path=env_path,
        )
        for issue_or_url in args.issues
    ]
    print(json.dumps(results, ensure_ascii=False, indent=2), file=stdout)
    return results


def cli() -> int:
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
