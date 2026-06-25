---
description: Trigger the marketing crew to plan and draft a new campaign
argument-hint: <campaign topic or goal>
---

# /new-campaign

Kick off the marketing domain crew for the campaign described in `$ARGUMENTS`.

## Steps

1. Treat `$ARGUMENTS` as the campaign brief (topic, audience, or goal).
   If it is empty, ask the user for the campaign goal first.
2. Invoke the marketing crew defined in
   `orchestrator/crews/marketing_crew.py` with the brief as input.
   The crew runs: Trend Researcher -> Content Writer -> Visual Creator ->
   Social Scheduler -> Analytics Tracker -> Email Campaign.
3. Collect the crew output and present:
   - 3 content drafts
   - a proposed publishing schedule
   - the metrics the Analytics Tracker will watch
4. Ask the user to approve before anything is published through n8n.

## Notes

- Nothing is published automatically; publishing is a separate explicit step.
- Use Gemini for trend research (free, high volume) and Claude for copy.
