---
name: jira-csd
description: Use when creating, reading, commenting on, attaching files to, or resolving Jira CSD issues through Agora Lab OAuth-backed APIs, including CSD keys or Jira browse URLs, dry-run previews, and direct Jira links.
---

# Jira CSD

Use this skill for the CSD issue lifecycle through the Agora Lab APIs: create, read, add comments or attachments, and resolve issues.

## First Step

Copy [`./.env.example`](./.env.example) to `./.env`, fill in the OAuth and Jira credentials, then run:

```bash
python3 scripts/get_access_token.py
```

The script prints the `access_token` only, so it can be reused directly in API debugging.

Jira REST calls must use the shared Python request layer in `scripts/jira_request.py`, which preserves the exact `accessToken` header casing. Do not use `urllib.request` for Jira API calls.

## Read CSD

Read one issue by key or REST path:

```bash
python3 scripts/jira_get.py /rest/api/2/issue/CSD-77810
```

Send query parameters by repeating `--query`:

```bash
python3 scripts/jira_get.py /rest/api/2/search \
  --query 'jql=project = CSD' \
  --query 'fields=summary,status,description,assignee,comment'
```

## Create CSD

Preview the template-based CSD `Bug` payload:

```bash
python3 scripts/jira_create_bug.py \
  --summary 'Slow first remote video rendering caused by late setupRemoteVideoEx' \
  --customer 'Knowmerece' \
  --cid '1436734' \
  --vid '1649426'
```

Create the real issue only when the user explicitly asks:

```bash
python3 scripts/jira_create_bug.py \
  --summary 'Slow first remote video rendering caused by late setupRemoteVideoEx' \
  --customer 'Knowmerece' \
  --cid '1436734' \
  --vid '1649426' \
  --create
```

Version 1 only supports template-based CSD `Bug` creation. The default template uses `Business Line = US/ROW`. When `--customer` is provided, the summary is normalized to `[Customer] issue`. Customer `VID` is mandatory for dry-run previews and real issue creation; do not use synthetic or test `VID`s. If `--description` is omitted, the script builds a customer-oriented description from the customer, CID, VID, and problem summary. After a successful create, the script automatically assigns the issue to `xieziling@agora.io`, runs `Start Progress`, and returns the Jira browse link.

## Add Comment

Dry-run a comment update:

```bash
python3 scripts/jira_add_comment.py CSD-77810 --body 'investigation update'
```

Add a real comment with local attachments only when the user explicitly asks:

```bash
python3 scripts/jira_add_comment.py \
  https://jira.agoralab.co/browse/CSD-77810 \
  --body-file ./comment.txt \
  --file ./screen.png \
  --file ./agora.log \
  --add
```

Version 1 supports a single issue, local file paths, and raw Jira comment bodies. Images can be inlined with `{{image:filename}}`; non-image files stay as attachments.

## Resolve CSD

Preview resolution for one or more CSD issues:

```bash
python3 scripts/jira_resolve_csd.py \
  https://jira.agoralab.co/browse/CSD-77806 \
  https://jira.agoralab.co/browse/CSD-77807
```

Resolve the real issues only when the user explicitly asks and provides root cause plus solution:

```bash
python3 scripts/jira_resolve_csd.py \
  https://jira.agoralab.co/browse/CSD-77806 \
  https://jira.agoralab.co/browse/CSD-77807 \
  --root-cause 'Remote video decoding finished early, but setupRemoteVideoEx was invoked several seconds later.' \
  --solution 'Move setupRemoteVideoEx earlier and bind the remote view before or immediately after onUserJoined.' \
  --resolve
```

Version 1 resolves issues to `RESOLVED` with resolution `Done`, not Jira `Closed`. It accepts Jira browse URLs or bare `CSD-xxxxx` keys and returns the Jira browse link for each issue. Real resolution requires explicit `--root-cause` and `--solution`; do not use placeholder RCA text.
