"""Restart-safe Telegram ingress and queue idempotency."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from gateway import mic, queue


@pytest.fixture
def isolated_queue(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(queue, "_DB_PATH", tmp_path / "jobs.sqlite")
    queue.init_db()
    return queue


def test_same_update_creates_exactly_one_job(isolated_queue, monkeypatch):
    monkeypatch.setattr(mic.sense, "emit", lambda *args, **kwargs: None)

    first_id, first_created = mic.speak_once(
        "hesabat hazırla",
        source="telegram",
        chat_id="42",
        ingress_key="telegram:1001",
    )
    second_id, second_created = mic.speak_once(
        "hesabat hazırla",
        source="telegram",
        chat_id="42",
        ingress_key="telegram:1001",
    )

    assert first_created is True
    assert second_created is False
    assert second_id == first_id
    assert len(isolated_queue.list_jobs()) == 1


def test_processed_cursor_survives_restart_boundary(isolated_queue):
    assert isolated_queue.last_ingress_event("telegram") is None
    isolated_queue.mark_ingress_processed("telegram", 10)
    isolated_queue.mark_ingress_processed("telegram", 12)

    assert isolated_queue.ingress_processed("telegram", 10)
    assert not isolated_queue.ingress_processed("telegram", 11)
    assert isolated_queue.last_ingress_event("telegram") == 12


def test_poison_update_attempts_are_durable(isolated_queue):
    assert isolated_queue.record_ingress_failure("telegram", 77, "bad payload") == 1
    assert isolated_queue.record_ingress_failure("telegram", 77, "bad payload") == 2
    assert isolated_queue.record_ingress_failure("telegram", 77, "bad payload") == 3


def test_channel_health_is_shared_through_sqlite(isolated_queue):
    isolated_queue.update_channel_health(
        "telegram",
        last_poll_started_at=10.0,
        last_poll_completed_at=11.0,
        last_error=None,
    )
    health = isolated_queue.channel_health("telegram")
    assert health["last_poll_started_at"] == 10.0
    assert health["last_poll_completed_at"] == 11.0
    assert health["last_error"] is None


def test_running_cancel_is_cooperative_and_committed_at_checkpoint(isolated_queue):
    job_id = isolated_queue.submit("uzun iş", source="telegram", chat_id="42")
    isolated_queue.claim_next()

    assert isolated_queue.request_cancel(job_id) == "requested"
    assert isolated_queue.get(job_id).status == "running"
    assert isolated_queue.get(job_id).cancel_requested is True
    assert isolated_queue.complete(job_id, "gecikmiş nəticə") is False
    with pytest.raises(isolated_queue.JobCancelled):
        isolated_queue.cancellation_checkpoint(job_id)

    assert isolated_queue.mark_cancelled(job_id) is True
    assert isolated_queue.get(job_id).status == "cancelled"


def test_approval_expires_and_cannot_be_approved(isolated_queue):
    job_id = isolated_queue.submit("paylaş", source="telegram", chat_id="42")
    isolated_queue.claim_next()
    isolated_queue.park_for_approval(job_id, ttl_seconds=60)
    expires = isolated_queue.get(job_id).approval_expires_at

    assert isolated_queue.expire_approvals(now=expires + 1) == [job_id]
    assert isolated_queue.approve(job_id) is False
    assert isolated_queue.get(job_id).status == "cancelled"
    assert isolated_queue.get(job_id).error == "approval expired"


def test_dead_letter_replay_is_atomic_and_exactly_once(isolated_queue):
    isolated_queue.quarantine_ingress(
        "telegram",
        700,
        chat_id="42",
        task="hesabatı yenidən hazırla",
        attempts=3,
        error="ValueError",
    )
    rows = isolated_queue.list_dead_letters()
    assert len(rows) == 1
    assert rows[0]["task"] == "hesabatı yenidən hazırla"

    job_id = isolated_queue.resubmit_dead_letter("telegram", 700)
    assert job_id is not None
    assert isolated_queue.get(job_id).task == "hesabatı yenidən hazırla"
    assert isolated_queue.resubmit_dead_letter("telegram", 700) is None


def test_existing_jobs_database_migrates_without_data_loss(monkeypatch, tmp_path):
    old_db = tmp_path / "old-jobs.sqlite"
    with sqlite3.connect(old_db) as conn:
        conn.execute(
            "CREATE TABLE jobs ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, "
            "chat_id TEXT, task TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued', "
            "result TEXT, error TEXT, artifacts TEXT NOT NULL DEFAULT '[]', "
            "approved INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, "
            "started_at REAL, finished_at REAL)"
        )
        conn.execute(
            "INSERT INTO jobs (source, chat_id, task, created_at) VALUES (?,?,?,?)",
            ("telegram", "42", "köhnə iş", 1.0),
        )
    monkeypatch.setattr(queue, "_DB_PATH", old_db)

    queue.init_db()

    assert queue.get(1).task == "köhnə iş"
    job_id, created = queue.submit_once(
        "yeni iş",
        source="telegram",
        chat_id="42",
        ingress_key="telegram:2",
    )
    assert created is True
    assert queue.get(job_id).ingress_key == "telegram:2"
