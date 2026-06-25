# Creative Learning Loop

This folder is for closing the loop between generated outputs, audit metrics,
and real taste decisions.

## Principle

Do not treat a high automated score as taste. Save human or vision-LLM feedback
after each serious attempt. Over time, the dataset should show which prompts,
models, compositions, and brand rules actually produce better work.

## Feedback Record

Each record should include:

- campaign and asset path
- prompt or prompt version
- automated audit report path
- creative review JSON path
- accepted/rejected decision
- why it was accepted or rejected
- prompt patch for the next attempt

Use `record_feedback.py` to append a compact JSONL record.
