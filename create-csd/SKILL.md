---
name: create-csd
description: Use when creating Jira CSD bugs through Agora Lab OAuth-backed APIs and you want the new issue automatically assigned, moved to In Progress, and returned with a direct Jira link.
---

# Create CSD

Use this skill when the task is to create a Jira CSD issue through the Agora Lab APIs.

## First Step

Copy [`./.env.example`](./.env.example) to `./.env`, fill in the OAuth credentials, then run:

```bash
python3 scripts/get_access_token.py
```

The script prints the `access_token` only, so it can be reused directly in the next API step.

## Jira GET Check

To verify Jira Basic Auth plus `accessToken`, run:

```bash
python3 scripts/jira_get.py /rest/api/2/issue/942266
```

To send query parameters, repeat `--query`:

```bash
python3 scripts/jira_get.py /rest/api/2/search \
  --query 'jql=project = CSD' \
  --query 'fields=description,assignee,comment'
```

Jira REST calls must use the shared Python request layer that preserves the exact `accessToken` header casing. Do not use `urllib.request` for Jira API calls.

## Jira Create Bug

Use the template-based create flow to verify POST without hand-crafting a request body:

```bash
python3 scripts/jira_create_bug.py \
  --summary 'Slow first remote video rendering caused by late setupRemoteVideoEx' \
  --customer 'Knowmerece' \
  --cid '1436734' \
  --vid '1649426'
```

That command is dry-run only and prints the final payload. To create a real issue:

```bash
python3 scripts/jira_create_bug.py \
  --summary 'Slow first remote video rendering caused by late setupRemoteVideoEx' \
  --customer 'Knowmerece' \
  --cid '1436734' \
  --vid '1649426' \
  --create
```

Version 1 only supports template-based CSD `Bug` creation.
The default template currently uses `Business Line = US/ROW`.
When `--customer` is provided, the summary is normalized to `[Customer] issue`.
Customer `VID` is mandatory for both dry-run preview and real issue creation. Do not use synthetic or test `VID`s in this workflow.
If `--description` is omitted, the script builds a customer-oriented description from the customer, CID, VID, and problem summary.
After a successful create, the script automatically assigns the new issue to `xieziling@agora.io`, runs `Start Progress`, and returns the full Jira browse link.
