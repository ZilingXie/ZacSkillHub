---
name: add-comments
description: Use when adding Jira comments to an existing CSD issue through Agora Lab OAuth-backed APIs and you need optional local attachments such as screenshots, logs, or archives.
---

# Add Comments

Use this skill when the task is to add a Jira comment to a single existing CSD issue and optionally upload local attachments.

## First Step

Copy [`./.env.example`](./.env.example) to `./.env`, fill in the OAuth credentials, then run:

```bash
python3 scripts/get_access_token.py
```

## Jira GET Check

To verify Jira Basic Auth plus `accessToken`, run:

```bash
python3 scripts/jira_get.py /rest/api/2/issue/CSD-77810
```

Jira REST calls must use the shared Python request layer that preserves the exact `accessToken` header casing. Do not use `urllib.request` for Jira API calls.

## Jira Add Comment

Dry-run a comment update:

```bash
python3 scripts/jira_add_comment.py CSD-77810 --body 'investigation update'
```

Add a real comment with local attachments:

```bash
python3 scripts/jira_add_comment.py \
  https://jira.agoralab.co/browse/CSD-77810 \
  --body-file ./comment.txt \
  --file ./screen.png \
  --file ./agora.log \
  --add
```

Version 1 only supports a single issue, local file paths, and raw Jira comment bodies. Images can be inlined with `{{image:filename}}`; non-image files stay as attachments.
