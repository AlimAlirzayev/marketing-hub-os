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
| **Telegram** | `gateway/bot.py` (long-poll) | `gateway/telegram.send_message` | ✅ live (`TELEGRAM_BOT_TOKEN` set) |
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
