#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import re
import sys
from pathlib import Path
from typing import Callable, TextIO
from urllib.parse import urlsplit


DEFAULT_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
JIRA_REQUEST_MODULE_PATH = Path(__file__).with_name("jira_request.py")
ISSUE_KEY_PATTERN = re.compile(r"^CSD-\d+$", re.IGNORECASE)
IMAGE_PLACEHOLDER_PATTERN = re.compile(r"\{\{image:([^}]+)\}\}")
JIRA_BROWSE_URL_TEMPLATE = "https://jira.agoralab.co/browse/{issue_key}"
COMMENT_URL_TEMPLATE = (
    "https://jira.agoralab.co/browse/{issue_key}"
    "?focusedCommentId={comment_id}#comment-{comment_id}"
)
COMMON_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}


def load_jira_request_module():
    spec = importlib.util.spec_from_file_location(
        "jira_request_for_jira_add_comment",
        JIRA_REQUEST_MODULE_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def default_upload_attachments(
    issue_key: str,
    file_paths: list[Path],
    *,
    env_path: Path = DEFAULT_ENV_PATH,
):
    return load_jira_request_module().upload_jira_attachments(
        issue_key,
        file_paths,
        env_path=env_path,
    )


def default_create_comment(
    issue_key: str,
    body: str,
    *,
    env_path: Path = DEFAULT_ENV_PATH,
):
    return load_jira_request_module().request_jira_json(
        "POST",
        f"/rest/api/2/issue/{issue_key}/comment",
        json_body={"body": body},
        env_path=env_path,
    )


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


def build_issue_url(issue_key: str) -> str:
    return JIRA_BROWSE_URL_TEMPLATE.format(issue_key=issue_key)


def build_comment_url(issue_key: str, comment_id: str) -> str:
    return COMMENT_URL_TEMPLATE.format(issue_key=issue_key, comment_id=comment_id)


def resolve_body_text(body: str | None, body_file: str | None) -> str:
    if not body and not body_file:
        raise ValueError("Provide exactly one of --body or --body-file.")
    if body and body_file:
        raise ValueError("Choose exactly one of --body or --body-file.")

    if body_file:
        body_text = Path(body_file).read_text(encoding="utf-8")
    else:
        body_text = body or ""

    if not body_text.strip():
        raise ValueError("Comment body must not be empty.")

    return body_text


def is_image_attachment(file_path: Path) -> bool:
    guessed_type, _ = mimetypes.guess_type(file_path.name)
    if guessed_type and guessed_type.startswith("image/"):
        return True
    return file_path.suffix.lower() in COMMON_IMAGE_EXTENSIONS


def collect_attachment_infos(file_items: list[str]) -> list[dict]:
    attachments = []
    by_basename: dict[str, Path] = {}
    for file_item in file_items:
        file_path = Path(file_item)
        if not file_path.exists() or not file_path.is_file():
            raise ValueError(f"Attachment file not found: {file_item}")
        basename = file_path.name
        if basename in by_basename:
            raise ValueError(
                f"Duplicate attachment basename: {basename}. Use unique file names per request."
            )
        by_basename[basename] = file_path
        attachments.append(
            {
                "path": file_path,
                "basename": basename,
                "is_image": is_image_attachment(file_path),
            }
        )
    return attachments


def build_comment_body(body: str, attachments: list[dict]) -> tuple[str, list[str]]:
    attachments_by_basename = {
        attachment["basename"]: attachment for attachment in attachments
    }
    referenced_images: list[str] = []

    def replace_placeholder(match: re.Match[str]) -> str:
        basename = match.group(1).strip()
        attachment = attachments_by_basename.get(basename)
        if attachment is None:
            raise ValueError(f"Placeholder image not found: {basename}")
        if not attachment["is_image"]:
            raise ValueError(f"Placeholder target {basename} is not an image attachment.")
        referenced_images.append(basename)
        return f"!{basename}!"

    final_body = IMAGE_PLACEHOLDER_PATTERN.sub(replace_placeholder, body)

    appended_sections = []
    appended_images = [
        attachment["basename"]
        for attachment in attachments
        if attachment["is_image"] and attachment["basename"] not in referenced_images
    ]
    if appended_images:
        appended_sections.append("\n".join(f"!{basename}!" for basename in appended_images))

    attached_files = [
        attachment["basename"]
        for attachment in attachments
        if not attachment["is_image"]
    ]
    if attached_files:
        appended_sections.append("Attached files: " + ", ".join(attached_files))

    if appended_sections:
        final_body = f"{final_body}\n\n" + "\n\n".join(appended_sections)

    inlined_images = list(dict.fromkeys(referenced_images + appended_images))
    return final_body, inlined_images


def main(
    argv: list[str] | None = None,
    *,
    env_path: Path = DEFAULT_ENV_PATH,
    upload_attachments_func: Callable[..., list] = default_upload_attachments,
    create_comment_func: Callable[..., dict] = default_create_comment,
    stdout: TextIO = sys.stdout,
):
    parser = argparse.ArgumentParser(
        description="Dry-run or add a Jira comment with optional attachments."
    )
    parser.add_argument("issue_or_url", help="CSD key or Jira browse URL.")
    parser.add_argument("--body", help="Raw Jira comment body.")
    parser.add_argument(
        "--body-file",
        help="Path to a text file whose contents will be used as the raw Jira comment body.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Local file path to upload as an attachment. Repeat for multiple files.",
    )
    parser.add_argument(
        "--add",
        action="store_true",
        help="Actually upload attachments and add the Jira comment.",
    )
    args = parser.parse_args(argv)

    issue_key = normalize_issue_input(args.issue_or_url)
    issue_url = build_issue_url(issue_key)
    comment_source = resolve_body_text(args.body, args.body_file)
    attachments = collect_attachment_infos(args.file)
    comment_body, inlined_images = build_comment_body(comment_source, attachments)
    attachment_names = [attachment["basename"] for attachment in attachments]

    result = {
        "key": issue_key,
        "issue_url": issue_url,
        "comment_body": comment_body,
        "comment_id": None,
        "comment_url": None,
        "attachments": attachment_names,
        "inlined_images": inlined_images,
        "dry_run": not args.add,
    }

    if not args.add:
        print(json.dumps(result, ensure_ascii=False, indent=2), file=stdout)
        print("Dry run only. Re-run with --add to add the Jira comment.", file=stdout)
        return result

    uploaded_attachments = attachment_names
    if attachments:
        try:
            upload_result = upload_attachments_func(
                issue_key,
                [attachment["path"] for attachment in attachments],
                env_path=env_path,
            )
            if upload_result:
                uploaded_attachments = [
                    item.get("filename", attachment["basename"])
                    for item, attachment in zip(upload_result, attachments)
                ]
        except Exception as exc:
            raise RuntimeError(
                f"Failed to upload attachments to {issue_url}: {exc}"
            ) from exc

    try:
        comment_response = create_comment_func(
            issue_key,
            comment_body,
            env_path=env_path,
        )
    except Exception as exc:
        if uploaded_attachments:
            raise RuntimeError(
                f"Uploaded attachments to {issue_url} but failed to add comment. "
                f"Uploaded: {', '.join(uploaded_attachments)}. Error: {exc}"
            ) from exc
        raise RuntimeError(f"Failed to add comment to {issue_url}: {exc}") from exc

    comment_id = str(comment_response.get("id", "")).strip()
    if not comment_id:
        raise RuntimeError("Jira comment response did not include an id.")

    result["comment_id"] = comment_id
    result["comment_url"] = build_comment_url(issue_key, comment_id)
    result["attachments"] = uploaded_attachments
    result["dry_run"] = False
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
