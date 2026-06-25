---
description: Generate a morning briefing from n8n logs, email, and calendar
---

# /briefing

Produce a concise morning briefing for the user.

## Steps

1. Use the `n8n-mcp` server to fetch the last 24 hours of workflow executions.
   Summarize successes, failures, and anything that needs attention.
2. Use the email/calendar MCP integration (when configured) to list:
   - unread important emails
   - today's calendar events
3. Use the `memory` server to recall any open follow-ups from previous sessions.
4. Output a single short briefing with three sections:
   - **Overnight** - what the automation did
   - **Today** - meetings and deadlines
   - **Needs you** - items requiring a human decision

## Notes

- Keep the briefing under 200 words.
- If a data source is unavailable, say so explicitly instead of guessing.
