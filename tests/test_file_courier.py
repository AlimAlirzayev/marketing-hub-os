"""Guard tests for the Telegram secure FILE courier (/setfile).

It carries whole-file secrets (e.g. ~/.codex/auth.json) that /setkey cannot. The
guarantees that matter: only a well-formed owner request stages anything, the bytes
land locked and off-git, and the carrying message is scrubbed from the chat.
"""
from __future__ import annotations

import os

import pytest

from gateway import bot


@pytest.fixture
def wired(monkeypatch, tmp_path):
    sent: list[str] = []
    deleted: list[int] = []
    monkeypatch.setattr(bot, "_COURIER_DIR", tmp_path)
    monkeypatch.setattr(bot.telegram, "send_message", lambda cid, txt, **k: sent.append(txt))
    monkeypatch.setattr(bot.telegram, "delete_message", lambda cid, mid: deleted.append(mid))
    monkeypatch.setattr(bot.telegram, "download_file_by_id", lambda fid: b'{"tokens":{"refresh_token":"x"}}')
    monkeypatch.setattr(bot.sense, "emit", lambda *a, **k: None)
    return sent, deleted, tmp_path


def _doc(msg_extra=None, **doc):
    d = {"file_id": "F1", "file_name": "auth.json", "file_size": 30}
    d.update(doc)
    msg = {"chat": {"id": 1}, "message_id": 55, "document": d}
    if msg_extra:
        msg.update(msg_extra)
    return msg, d


def test_valid_setfile_stages_locked_and_scrubs_the_message(wired):
    sent, deleted, tmp = wired
    msg, doc = _doc({"caption": "/setfile CODEX_AUTH"})
    bot._handle_couriered_file(1, msg, doc)

    dest = tmp / "CODEX_AUTH"
    assert dest.exists() and dest.read_bytes().startswith(b"{")
    assert oct(os.stat(dest).st_mode)[-3:] == "600", "secret must be owner-only on disk"
    assert deleted == [55], "the carrying message must be deleted"
    assert any("alındı" in s for s in sent)


def test_missing_caption_explains_how_instead_of_staging(wired):
    sent, deleted, tmp = wired
    msg, doc = _doc()                      # no caption
    bot._handle_couriered_file(1, msg, doc)
    assert list(tmp.iterdir()) == [], "nothing should be staged without /setfile"
    assert any("/setfile" in s for s in sent)


def test_bad_name_is_rejected(wired):
    sent, deleted, tmp = wired
    msg, doc = _doc({"caption": "/setfile not-a-key"})
    bot._handle_couriered_file(1, msg, doc)
    assert list(tmp.iterdir()) == []


def test_oversized_file_is_refused(wired):
    sent, deleted, tmp = wired
    msg, doc = _doc({"caption": "/setfile CODEX_AUTH"}, file_size=bot._COURIER_MAX_BYTES + 1)
    bot._handle_couriered_file(1, msg, doc)
    assert list(tmp.iterdir()) == []
    assert any("böyük" in s for s in sent)


def test_download_failure_stages_nothing(wired, monkeypatch):
    sent, deleted, tmp = wired
    monkeypatch.setattr(bot.telegram, "download_file_by_id", lambda fid: None)
    msg, doc = _doc({"caption": "/setfile CODEX_AUTH"})
    bot._handle_couriered_file(1, msg, doc)
    assert list(tmp.iterdir()) == []


def test_a_document_is_routed_to_the_courier_not_the_task_path(wired, monkeypatch):
    """A file upload must be intercepted before task extraction, which would
    otherwise reject it as 'send text or voice'."""
    routed = {}
    monkeypatch.setattr(bot, "_is_owner", lambda cid: True)
    monkeypatch.setattr(bot, "_handle_couriered_file",
                        lambda cid, m, d: routed.setdefault("hit", d))
    called = {"extract": False}
    monkeypatch.setattr(bot, "_extract_task",
                        lambda m: (called.__setitem__("extract", True), (None, False))[1])
    msg, doc = _doc({"caption": "/setfile CODEX_AUTH"})
    bot._handle_message(msg)
    assert routed.get("hit") == doc
    assert called["extract"] is False, "documents must not fall through to task extraction"
