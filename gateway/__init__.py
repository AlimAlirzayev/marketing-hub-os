"""Xalq Insurance Digital OS - Gateway: the autonomous background task runtime.

This package is the missing link that turns Xalq Insurance Digital OS from a set of skeleton
pieces into a real "throw a task, it executes in the background" agent, like
Manus / Hermes / OpenClaw -- but self-hosted, zero-budget and firewall-safe.

Pieces:
    queue.py     durable SQLite job queue (submit / claim / complete)
    llm.py       lightweight provider calls (Gemini live; others pluggable)
    executor.py  the brain: task -> route -> LLM (+ future tools) -> result
    worker.py    daemon loop: pull job, execute, store result, notify
    submit.py    CLI front-end (works today, no external setup)
    bot.py       Telegram long-poll front-end (activates when token is set)

All front-ends write to the same queue; the worker is the single executor.
"""
