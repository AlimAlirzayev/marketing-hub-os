"""Guards for the voice I/O module (gateway.voice)."""

import unittest
from unittest.mock import patch

from gateway import voice


class SttCascade(unittest.TestCase):
    def test_returns_first_success_and_skips_rest(self):
        calls = []

        def ok(a):
            calls.append("el")
            return "salam dünya"

        def boom(a):
            calls.append("groq")
            raise RuntimeError("should not reach")

        with patch.object(voice, "_STT_CHAIN", (("el", ok), ("groq", boom))):
            self.assertEqual(voice.transcribe(b"audio"), "salam dünya")
        self.assertEqual(calls, ["el"])  # stopped at first success

    def test_falls_through_on_failure(self):
        def boom(a):
            raise RuntimeError("down")

        def ok(a):
            return "nəticə"

        with patch.object(voice, "_STT_CHAIN", (("a", boom), ("b", ok))):
            self.assertEqual(voice.transcribe(b"x"), "nəticə")

    def test_empty_audio_is_none(self):
        self.assertIsNone(voice.transcribe(b""))


class Despeechify(unittest.TestCase):
    def test_strips_markdown_tag_and_urls(self):
        raw = "_[chat:groq]_\n\n**Salam** Alim, bax: https://x.az/y — necəsən?"
        out = voice._despeechify(raw)
        self.assertNotIn("_[chat", out)
        self.assertNotIn("**", out)
        self.assertNotIn("http", out)
        self.assertIn("Salam", out)

    def test_trims_to_max(self):
        with patch.object(voice, "_TTS_MAX_CHARS", 20):
            out = voice._despeechify("a" * 200)
            self.assertLessEqual(len(out), 21)


class RepliesGate(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("VOICE_REPLIES", None)
            self.assertFalse(voice.replies_enabled())
            self.assertIsNone(voice.synthesize("salam"))

    def test_enabled_flag(self):
        import os
        with patch.dict(os.environ, {"VOICE_REPLIES": "1"}):
            self.assertTrue(voice.replies_enabled())


class VoiceJobRegistry(unittest.TestCase):
    def test_mark_and_take_once(self):
        voice.mark_voice_job(4242)
        self.assertTrue(voice.take_voice_job(4242))
        self.assertFalse(voice.take_voice_job(4242))  # consumed

    def test_unmarked_is_false(self):
        self.assertFalse(voice.take_voice_job(999999))


if __name__ == "__main__":
    unittest.main()
