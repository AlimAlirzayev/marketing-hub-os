"""/setkey — the owner-courier path for API keys (keys never travel via git).

The contract under test: only the owner can use it, the secret value is written
to .env and NEVER echoed anywhere, and the carrying Telegram message is deleted.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class SetEnvKey(unittest.TestCase):
    def setUp(self):
        from gateway import bot
        self.bot = bot
        self.env = Path(tempfile.mkdtemp()) / ".env"

    def test_appends_new_key(self):
        self.env.write_text("EXISTING=1\n", encoding="utf-8")
        replaced = self.bot._set_env_key("NEW_KEY", "secret123", self.env)
        self.assertFalse(replaced)
        text = self.env.read_text(encoding="utf-8")
        self.assertIn("EXISTING=1", text)
        self.assertIn("NEW_KEY=secret123", text)
        self.assertEqual(os.environ.get("NEW_KEY"), "secret123")

    def test_updates_existing_key_in_place(self):
        self.env.write_text("A=1\nMY_KEY=old\nB=2\n", encoding="utf-8")
        replaced = self.bot._set_env_key("MY_KEY", "newvalue", self.env)
        self.assertTrue(replaced)
        lines = self.env.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines, ["A=1", "MY_KEY=newvalue", "B=2"])

    def test_creates_env_when_missing(self):
        self.bot._set_env_key("FRESH_KEY", "v", self.env)
        self.assertIn("FRESH_KEY=v", self.env.read_text(encoding="utf-8"))


class SetKeyCommand(unittest.TestCase):
    def setUp(self):
        from gateway import bot
        self.bot = bot
        self.env = Path(tempfile.mkdtemp()) / ".env"
        self.sent: list[str] = []
        self.deleted: list[tuple] = []
        self._patches = [
            mock.patch.object(bot, "_ENV_PATH", self.env),
            mock.patch.object(bot.telegram, "send_message",
                              side_effect=lambda c, t: self.sent.append(t)),
            mock.patch.object(bot.telegram, "delete_message",
                              side_effect=lambda c, m: self.deleted.append((c, m))),
            mock.patch.object(bot.sense, "emit"),
            # CRITICAL isolation: without this, running the suite on a machine
            # whose real KEY_VAULT_SECRET is set writes the TEST value into the
            # REAL vault and auto-pushes it — which actually happened (the
            # tripwire's post-pull test run poisoned RAPIDAPI_KEY on 2026-07-10).
            mock.patch.object(bot.keyvault, "enabled", return_value=False),
            mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def _msg(self, text, chat=42, message_id=7):
        return {"chat": {"id": chat}, "text": text, "message_id": message_id}

    def test_owner_sets_key_value_never_echoed_message_deleted(self):
        self.bot._handle_message(self._msg("/setkey RAPIDAPI_KEY supersecretvalue"))
        self.assertIn("RAPIDAPI_KEY=supersecretvalue", self.env.read_text(encoding="utf-8"))
        self.assertEqual(self.deleted, [(42, 7)])          # secret scrubbed from chat
        for reply in self.sent:                            # masked confirmation only
            self.assertNotIn("supersecretvalue", reply)
        self.assertTrue(any("RAPIDAPI_KEY" in r for r in self.sent))

    def test_non_owner_is_refused(self):
        self.bot._handle_message(self._msg("/setkey X_KEY val", chat=999))
        self.assertFalse(self.env.exists())
        self.assertTrue(any("Unauthorized" in r for r in self.sent))

    def test_bad_key_name_gets_usage_not_write(self):
        self.bot._handle_message(self._msg("/setkey lower-case val"))
        self.assertFalse(self.env.exists())
        self.assertTrue(any("İstifadə" in r for r in self.sent))

    def test_keys_command_is_owner_only_and_masked(self):
        self.bot._handle_message(self._msg("/keys", chat=999))
        self.assertTrue(any("Unauthorized" in r for r in self.sent))
        self.sent.clear()
        with mock.patch.object(self.bot.sense, "env_status",
                               return_value={"GEMINI_API_KEY": "SET (len=39, …5UD0)"}):
            self.bot._handle_message(self._msg("/keys"))
        self.assertTrue(any("maskalı" in r for r in self.sent))


if __name__ == "__main__":
    unittest.main()
