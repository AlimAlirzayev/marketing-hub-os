# Channels — how intake/delivery is abstracted (and how to add one)

**Honest finding:** the channel abstraction substantially **already exists** — it
is the queue's `source` + `chat_id` model. The agent core does not care which
channel a task came from; a channel is just two small adapters.

```
intake  ──► queue.submit(task, source="<channel>", chat_id="<addr>")
                         │
                    worker executes (council + security + memory + browser)
                         │
delivery ◄── worker._notify(job, text)   # dispatch by job.source
```

## Live channels
| Channel | Intake | Delivery | Status |
|---|---|---|---|
| **Telegram** | `gateway/bot.py` (restart-safe long-poll + native callbacks) | `gateway/telegram` typed adapter | ✅ owner-only, idempotent, live progress, native approval |

Telegram persists handled `update_id` values in the durable queue database and
binds queued work to a unique ingress key. A restart or Telegram replay therefore
returns the original job instead of running the same request twice. The adapter
subscribes only to `message`, `edited_message`, and `callback_query`, honors Bot API
`parameters.retry_after`, retries transient network/5xx failures within a bounded
budget, and exposes secret-free transport health through the existing Hub pulse.
Ingress uses one bounded long-poll attempt per supervised loop and records poll
start/completion freshness, so Workdesk can distinguish “configured” from
“actually polling” instead of showing a false-green token check.

For long-running work the bot creates one editable status card, persists its
Telegram `message_id` with the job, edits it when execution starts, and removes
it after the final answer arrives. Risky actions turn that same card into native
`Təsdiqlə / İmtina` buttons; `/approve N` and `/reject N` remain deterministic
fallbacks. `Ləğv et` only cancels queued/parked work. A running synchronous tool
call receives a durable cooperative-cancel request and stops at the next
governed checkpoint; it is never falsely labelled cancelled while still active.

Executor progress is a typed in-process event stream, not model-generated
chatter. Job-scoped stages (preflight, live research, browser, Crew, planner
steps, builder fallback, verification and delivery) are debounced into the same
Telegram card at most once per 2.5 seconds. The current stage is also persisted
on the job for Workdesk.

Approvals expire after 30 minutes. The worker closes expired cards without
executing the action. Poison Telegram updates enter a durable Workdesk
dead-letter view after three attempts. Raw Telegram JSON is never retained:
only chat id, redacted replay-safe task text, masked error class and attempt
metadata are stored. A Workdesk retry is atomic and exactly-once; sensitive or
non-replayable events can only be dismissed.

This deliberately adopts the strongest OpenClaw Telegram UX patterns—always-on
gateway, progress drafts, native approvals, durable ingress and dead-letter-like
quarantine—without importing OpenClaw's broader plugin/runtime trust surface.
The Ramin-OS supervisor remains the one daemon, and Claude router → summon →
production CrewAI remains the execution authority.

On Windows, `scripts/supervisor_task.ps1` installs one current-user, at-logon
`Ramin-OS-Supervisor` task. It uses the repo virtualenv and working directory,
retries a failed start three times, and remains protected by the supervisor's
localhost singleton lock. `Status` is read-only and `Uninstall` removes only
that exact task.

### Live benchmark evidence (2026-07-24)

- Telegram Bot API: `https://core.telegram.org/bots/api`
- OpenClaw Telegram runtime and approvals:
  `https://docs.openclaw.ai/channels/telegram`
- OpenClaw progress-draft behavior:
  `https://docs.openclaw.ai/concepts/progress-drafts`
- OpenClaw daemon/service lifecycle:
  `https://docs.openclaw.ai/cli/daemon`
- User-reported silent polling regressions considered in our design:
  `https://github.com/openclaw/openclaw/issues/59833` and
  `https://github.com/openclaw/openclaw/issues/73323`

Secrets never enter this channel. `/setkey` and `/setfile` are permanently
fail-closed; use `SECURE_KEY.bat KEY_NAME` (or
`python scripts/secure_key.py KEY_NAME`) on the local host.
| **CLI** | `gateway/submit.py` | DB read (`submit --status`) | ✅ live |
| **Schedule** | `gateway/scheduler.py` (cron) | inherits the task's own `chat_id` | ✅ live |

## Add a new channel (≈2 small adapters, no core change)
1. **Intake:** a small loop/webhook that, on a new message, calls
   `queue.submit(text, source="whatsapp", chat_id=<addr>)`.
2. **Delivery:** add a branch to `worker._notify` (or a sender registry) that, for
   `job.source == "whatsapp"`, sends `text` back to `chat_id`.

## Why WhatsApp / Slack / email are NOT pre-built here
Each needs **credentials/approval we don't have yet** (WhatsApp Cloud API number +
token; Slack app + bot token; an SMTP/IMAP mailbox). Building them blind would be
untested dead code — the same lesson as the Meta connector and `doit`. The
**architecture is ready**; adding a channel is a credential + ~30-line adapter
task, done per channel when its credential exists. Telegram already proves the
contract end to end.
