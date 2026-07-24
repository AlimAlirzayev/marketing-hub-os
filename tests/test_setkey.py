"""/setkey is permanently blocked; secrets are entered only on the local host."""

from __future__ import annotations

from unittest import mock


class TestSetKeyCommand:
    def setup_method(self):
        from gateway import bot

        self.bot = bot
        self.sent: list[str] = []
        self.deleted: list[tuple[int, int]] = []
        self.patches = [
            mock.patch.object(
                bot.telegram,
                "send_message",
                side_effect=lambda chat, text: self.sent.append(text),
            ),
            mock.patch.object(
                bot.telegram,
                "delete_message",
                side_effect=lambda chat, message: self.deleted.append((chat, message)),
            ),
            mock.patch.object(bot.sense, "emit"),
            mock.patch.dict(
                "os.environ",
                {"TELEGRAM_OWNER_CHAT_ID": "42", "ALLOW_TELEGRAM_SETKEY": "1"},
            ),
        ]
        for patcher in self.patches:
            patcher.start()

    def teardown_method(self):
        for patcher in reversed(self.patches):
            patcher.stop()

    @staticmethod
    def _msg(text: str, chat: int = 42, message_id: int = 7):
        return {"chat": {"id": chat}, "text": text, "message_id": message_id}

    def test_owner_secret_is_never_written_even_with_legacy_override(self, monkeypatch):
        wrote = []
        monkeypatch.setattr(self.bot.keyvault, "put", lambda *args: wrote.append(args))

        self.bot._handle_message(
            self._msg("/setkey RAPIDAPI_KEY supersecretvalue")
        )

        assert wrote == []
        assert self.deleted == [(42, 7)]
        assert all("supersecretvalue" not in reply for reply in self.sent)
        assert any("SECURE_KEY" in reply for reply in self.sent)

    def test_non_owner_is_rejected_before_secret_handler(self):
        self.bot._handle_message(self._msg("/setkey X_KEY value", chat=999))
        assert self.deleted == []
        assert any("Unauthorized" in reply for reply in self.sent)

    def test_keys_command_remains_owner_only_and_masked(self):
        self.bot._handle_message(self._msg("/keys", chat=999))
        assert any("Unauthorized" in reply for reply in self.sent)
        self.sent.clear()
        with mock.patch.object(
            self.bot.sense,
            "env_status",
            return_value={"GEMINI_API_KEY": "SET (len=39, …5UD0)"},
        ):
            self.bot._handle_message(self._msg("/keys"))
        assert any("maskalı" in reply for reply in self.sent)
