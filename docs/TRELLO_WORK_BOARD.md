# Xalq Insurance Trello Work Board

Ramin-OS is wired for the Xalq Insurance board:

- Board: <https://trello.com/b/RRlLCaSG/xalg-insurance>
- Allowlisted short-link: `RRlLCaSG`
- Connector: `gateway/trello.py`
- Governance: `config/agent_permissions.json` entry `trello_work_board`

## What it can manage

After Trello authorization, Ramin-OS can read lists and open cards, summarize
workload and due dates, and prepare card changes. These writes are supported
only after review of an exact saved plan:

- create a card;
- move a card to another list;
- update card name, description, due date, or due-complete state;
- add a card comment.

Deletion, board/list closure, member invitations/removals, visibility changes,
and cross-board access are blocked.

## One-time human authorization

Trello's official API flow uses an API key plus a user token. A token can read
and write according to the scope granted to it and must be treated as a secret.
Create or select the Ramin-OS Power-Up at <https://trello.com/apps/admin>, open
its **API Key** tab, generate an API key, then follow the **Token** link and
grant the narrowest practical scope. Start read-only; expand to write only when
the snapshot is verified and write management is wanted.

Set the values only in the local terminal/session or an approved secret store.
Do not paste them into chat and do not commit them:

```powershell
$env:TRELLO_API_KEY = Read-Host "Trello API key"
$secure = Read-Host "Trello token" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $env:TRELLO_API_TOKEN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
```

These values last only for the current PowerShell process. Ramin-OS diagnostics
do not inspect or print their values.

## Verify read access

```powershell
python -m gateway.trello doctor
python -m gateway.trello report
python -m gateway.trello connection-check
python -m gateway.trello snapshot
```

`connection-check` is the quiet/background-safe first live check. It never
opens or focuses a browser, never writes to Trello, and reads only the current
member ID plus minimal metadata for the allowlisted board. It writes a
secret-free machine status to `output/trello/connection_status.json` and an
operator report to `output/trello/connection_status.md`. A non-zero exit means
authorization or board access is still blocked; the report contains the safe
next action.

`snapshot` is the first live check. It reads the allowlisted board and makes no
change. If Trello returns `401`, re-check the human authorization and token
scope without sharing the credential.

## Governed write example

First create a reviewable plan. The list/card identifiers come from `snapshot`.

```powershell
python -m gateway.trello plan create_card --changes-json '{"name":"Yeni iş","idList":"LIST_ID","desc":"Təsdiqlənmiş iş təsviri"}'
```

The command shows the full target and changes, saves the plan under
`data/trello/pending/`, and returns a 12-character approval code. Review the
plan. Only then apply that exact plan:

```powershell
python -m gateway.trello apply APPROVAL_CODE
```

Changing any operation, target, or field changes the approval code and blocks
the old approval. The audit entry contains board reference, operation, and
approval code only; it never contains credentials or card text.

Other plan shapes:

```powershell
python -m gateway.trello plan move_card --target-id CARD_ID --changes-json '{"idList":"LIST_ID"}'
python -m gateway.trello plan update_card --target-id CARD_ID --changes-json '{"due":"2026-08-01T14:00:00.000Z"}'
python -m gateway.trello plan comment_card --target-id CARD_ID --changes-json '{"text":"Təsdiqlənmiş qeyd"}'
```

## Official references

- [Trello API introduction](https://developer.atlassian.com/cloud/trello/guides/rest-api/api-introduction/)
- [Authorization](https://developer.atlassian.com/cloud/trello/guides/rest-api/authorization/)
- [Board REST resources](https://developer.atlassian.com/cloud/trello/rest/api-group-boards/)
- [Rate limits](https://developer.atlassian.com/cloud/trello/guides/rest-api/rate-limits/)

Trello does not document a service-account bypass for this flow. Both the
direct token route and OAuth 1.0 require a Trello user authorization step, so a
background agent can monitor and use an existing authorization but cannot grant
consent on the user's behalf.
