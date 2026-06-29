---
name: zendesk-ticket
description: Use when the user asks to read, inspect, fetch, summarize, or search Zendesk tickets using local Zendesk credentials, including ticket IDs, ticket URLs, status searches, requester searches, subject searches, or support case investigation. This skill is read-only and must not create, update, comment on, assign, or close tickets.
---

# Zendesk Ticket

Use this skill to read and search Zendesk tickets through the Zendesk REST API.

## First Step

Copy [`./.env.example`](./.env.example) to `./.env`, then fill in the Zendesk subdomain and an agent/admin account:

```bash
cp .env.example .env
```

The scripts use Basic Auth with `ZENDESK_USERNAME` and `ZENDESK_PASSWORD`. If Zendesk returns `401`, check the account credentials, ticket permissions, and whether the Zendesk instance still allows password-based Basic Auth.

## Read Ticket

Fetch a ticket by id:

```bash
python3 scripts/zendesk_get_ticket.py 12345
```

Print the raw Zendesk response:

```bash
python3 scripts/zendesk_get_ticket.py 12345 --raw
```

## Search Tickets

Search tickets with Zendesk search syntax. The script automatically adds `type:ticket` when it is missing:

```bash
python3 scripts/zendesk_search_tickets.py 'status:open requester:user@example.com'
python3 scripts/zendesk_search_tickets.py 'subject:"login failed"' --limit 20
```

Print the raw Zendesk response:

```bash
python3 scripts/zendesk_search_tickets.py 'status:open' --raw
```

## Read-Only Rule

Only use the bundled scripts for read-only GET requests. Do not create, update, comment on, assign, solve, close, or delete Zendesk tickets with this skill.
