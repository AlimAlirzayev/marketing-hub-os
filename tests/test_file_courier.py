"""Telegram must never be a credential or auth-file courier."""

from __future__ import annotations

from gateway import bot


def _wire(monkeypatch):
    sent: list[str] = []
    deleted: list[int] = []
    downloaded: list[str] = []
    monkeypatch.setattr(bot, "_is_owner", lambda cid: True)
    monkeypatch.setattr(
        bot.telegram, "send_message", lambda cid, text, **kwargs: sent.append(text)
    )
    monkeypatch.setattr(
        bot.telegram, "delete_message", lambda cid, mid: deleted.append(mid)
    )
    monkeypatch.setattr(
        bot.telegram,
        "download_file_by_id",
        lambda fid: downloaded.append(fid) or b"must-not-be-read",
    )
    monkeypatch.setattr(bot.sense, "emit", lambda *args, **kwargs: None)
    return sent, deleted, downloaded


def _document(caption: str | None):
    msg = {
        "chat": {"id": 1},
        "message_id": 55,
        "document": {
            "file_id": "F1",
            "file_name": "auth.json",
            "file_size": 30,
        },
    }
    if caption is not None:
        msg["caption"] = caption
    return msg


def test_setfile_is_deleted_without_download_or_staging(monkeypatch):
    sent, deleted, downloaded = _wire(monkeypatch)
    bot._handle_message(_document("/setfile CODEX_AUTH"))

    assert downloaded == [], "blocked secret files must never be downloaded"
    assert deleted == [55], "best-effort deletion reduces chat-history exposure"
    assert any("tam bağlıdır" in reply for reply in sent)
    assert any("SECURE_KEY" in reply for reply in sent)


def test_setfile_has_no_environment_override(monkeypatch):
    sent, deleted, downloaded = _wire(monkeypatch)
    monkeypatch.setenv("ALLOW_TELEGRAM_SETFILE", "1")
    bot._handle_message(_document("/setfile CODEX_AUTH"))

    assert downloaded == []
    assert deleted == [55]
    assert any("tam bağlıdır" in reply for reply in sent)


def test_ordinary_document_is_not_misrepresented_as_secure_courier(monkeypatch):
    sent, deleted, downloaded = _wire(monkeypatch)
    bot._handle_message(_document("bu sənədi təhlil et"))

    assert downloaded == []
    assert deleted == []
    assert any("Sənəd qəbulu" in reply for reply in sent)
