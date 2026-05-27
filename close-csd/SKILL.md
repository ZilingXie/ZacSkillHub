---
name: close-csd
description: Use when resolving existing Jira CSD issues through Agora Lab OAuth-backed APIs and you want to pass CSD keys or browse URLs, dry-run the workflow first, and return direct Jira links for each issue.
---

# Close CSD

Use this skill when the task is to batch resolve existing Jira CSD issues through the Agora Lab APIs.

## First Step

Copy [`./.env.example`](./.env.example) to `./.env`, fill in the OAuth credentials, then run:

```bash
python3 scripts/get_access_token.py
```

The script prints the `access_token` only, so it can be reused directly in the next API step.

## Jira GET Check

To verify Jira Basic Auth plus `accessToken`, run:

```bash
python3 scripts/jira_get.py /rest/api/2/issue/CSD-77806
```

Jira REST calls must use the shared Python request layer that preserves the exact `accessToken` header casing. Do not use `urllib.request` for Jira API calls.

## Jira Resolve CSD

Use the resolve flow to plan or execute batch resolution for existing CSD issues:

```bash
python3 scripts/jira_resolve_csd.py \
  https://jira.agoralab.co/browse/CSD-77806 \
  https://jira.agoralab.co/browse/CSD-77807
```

That command is dry-run only and prints the planned actions for each issue. To actually resolve them:

```bash
python3 scripts/jira_resolve_csd.py \
  https://jira.agoralab.co/browse/CSD-77806 \
  https://jira.agoralab.co/browse/CSD-77807 \
  --root-cause 'Remote video decoding finished early, but setupRemoteVideoEx was invoked several seconds later.' \
  --solution 'Move setupRemoteVideoEx earlier and bind the remote view before or immediately after onUserJoined.' \
  --resolve
```

Version 1 resolves issues to `RESOLVED` with resolution `Done`, not `Closed`. It accepts either Jira browse URLs or bare `CSD-xxxxx` keys and returns the full Jira browse link for each issue. Real resolution requires explicit `--root-cause` and `--solution` inputs; the script no longer uses placeholder RCA text.
