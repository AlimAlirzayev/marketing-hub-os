"""Encrypted key vault — keys travel via git ONLY as ciphertext.

Contract under test: roundtrip with the right passphrase, fail-closed with the
wrong one, machine-identity keys never sync, apply merges into .env without
touching unrelated lines, and /setkey mails the encrypted key automatically.
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class _VaultSandbox(unittest.TestCase):
    """Isolated vault + .env + unlocked passphrase for each test."""

    def setUp(self):
        from gateway import keyvault
        self.kv = keyvault
        d = Path(tempfile.mkdtemp())
        self._patches = [
            mock.patch.object(keyvault, "VAULT_PATH", d / "keys.vault"),
            mock.patch.object(keyvault, "ENV_PATH", d / ".env"),
            mock.patch.dict(os.environ, {"KEY_VAULT_SECRET": "test-master-pass"}),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])


class VaultCrypto(_VaultSandbox):
    def test_roundtrip(self):
        self.assertTrue(self.kv.put("RAPIDAPI_KEY", "secret-value-123"))
        self.assertEqual(self.kv.load()["RAPIDAPI_KEY"]["v"], "secret-value-123")
        self.assertEqual(self.kv.names(), ["RAPIDAPI_KEY"])

    def test_ciphertext_never_contains_the_value(self):
        self.kv.put("RAPIDAPI_KEY", "secret-value-123")
        raw = self.kv.VAULT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("secret-value-123", raw)
        self.assertNotIn("RAPIDAPI_KEY", raw)  # even names are inside the blob

    def test_wrong_passphrase_fails_closed(self):
        self.kv.put("RAPIDAPI_KEY", "secret-value-123")
        with mock.patch.dict(os.environ, {"KEY_VAULT_SECRET": "WRONG"}):
            self.assertEqual(self.kv.load(), {})

    def test_locked_vault_refuses_writes(self):
        with mock.patch.dict(os.environ, {"KEY_VAULT_SECRET": ""}):
            self.assertFalse(self.kv.enabled())
            self.assertFalse(self.kv.put("X_KEY", "v"))


class DropKey(_VaultSandbox):
    def test_drop_removes_a_poisoned_entry(self):
        self.kv.put("BAD_KEY", "leaked-test-value")
        self.assertTrue(self.kv.drop("BAD_KEY"))
        self.assertNotIn("BAD_KEY", self.kv.load())

    def test_drop_missing_is_false(self):
        self.assertFalse(self.kv.drop("NO_SUCH_KEY"))


class NeverSync(_VaultSandbox):
    def test_machine_identity_keys_do_not_travel(self):
        for key in ("KEY_VAULT_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_OWNER_CHAT_ID"):
            self.assertFalse(self.kv.syncable(key), key)
            self.assertFalse(self.kv.put(key, "v"), key)
        self.assertTrue(self.kv.syncable("GEMINI_API_KEY"))


class ApplyToEnv(_VaultSandbox):
    def test_apply_adds_and_updates_without_touching_others(self):
        self.kv.ENV_PATH.write_text("KEEP_ME=1\nOLD_KEY=stale\n", encoding="utf-8")
        self.kv.put("OLD_KEY", "fresh")
        self.kv.put("NEW_KEY", "brand-new")

        applied = self.kv.apply_to_env()
        self.assertEqual(sorted(applied), ["NEW_KEY", "OLD_KEY"])
        text = self.kv.ENV_PATH.read_text(encoding="utf-8")
        self.assertIn("KEEP_ME=1", text)
        self.assertIn("OLD_KEY=fresh", text)
        self.assertIn("NEW_KEY=brand-new", text)
        self.assertEqual(os.environ["NEW_KEY"], "brand-new")

    def test_second_apply_is_a_noop(self):
        self.kv.put("A_KEY", "v1")
        self.kv.apply_to_env()
        self.assertEqual(self.kv.apply_to_env(), [])

    def test_locked_apply_does_nothing(self):
        self.kv.put("A_KEY", "v1")
        with mock.patch.dict(os.environ, {"KEY_VAULT_SECRET": ""}):
            self.assertEqual(self.kv.apply_to_env(), [])


class SetkeyMailsTheVault(_VaultSandbox):
    """The bot side: /setkey should encrypt + push automatically."""

    def setUp(self):
        super().setUp()
        from gateway import bot
        self.bot = bot
        d = Path(tempfile.mkdtemp())
        self.sent: list[str] = []
        more = [
            mock.patch.object(bot, "_ENV_PATH", d / ".env"),
            mock.patch.object(bot.telegram, "send_message",
                              side_effect=lambda c, t: self.sent.append(t)),
            mock.patch.object(bot.telegram, "delete_message"),
            mock.patch.object(bot.sense, "emit"),
            mock.patch.object(self.kv, "commit_and_push", return_value=True),
            mock.patch.dict(os.environ, {"TELEGRAM_OWNER_CHAT_ID": "42"}),
        ]
        for p in more:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in more])

    def _msg(self, text):
        return {"chat": {"id": 42}, "text": text, "message_id": 7}

    def test_synced_key_lands_in_vault_and_gets_pushed(self):
        self.bot._handle_message(self._msg("/setkey RAPIDAPI_KEY topsecret99"))
        self.assertEqual(self.kv.load()["RAPIDAPI_KEY"]["v"], "topsecret99")
        self.kv.commit_and_push.assert_called_once()
        self.assertTrue(any("poçta göndərildi" in r for r in self.sent))
        for r in self.sent:
            self.assertNotIn("topsecret99", r)

    def test_master_pass_unlocks_but_never_travels(self):
        self.bot._handle_message(self._msg("/setkey KEY_VAULT_SECRET new-master"))
        self.assertNotIn("KEY_VAULT_SECRET", self.kv.load())
        self.assertTrue(any("Seyf AÇILDI" in r for r in self.sent))

    def test_locked_vault_warns_key_stays_local(self):
        with mock.patch.dict(os.environ, {"KEY_VAULT_SECRET": ""}):
            self.bot._handle_message(self._msg("/setkey SOME_KEY val123"))
        self.assertTrue(any("Seyf bağlıdır" in r for r in self.sent))


if __name__ == "__main__":
    unittest.main()
