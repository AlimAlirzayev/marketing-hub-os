"""Tests for the read-only Public Signal Radar loop."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from gateway import signal_radar


HTML = """
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="perplexity/1045">
  <div class="tgme_widget_message_text js-message_text" dir="auto"><b>💼 OpenAI Releases GPT-5.6 and ChatGPT Work</b><br/><br/>OpenAI has announced ChatGPT Work.<br/><a href="https://learn.chatgpt.com/docs/get-started-with-work">here</a></div>
  <a class="tgme_widget_message_date" href="https://t.me/perplexity/1045"><time datetime="2026-07-09T17:57:24+00:00" class="time">17:57</time></a>
</div>
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="perplexity/1034">
  <div class="tgme_widget_message_text js-message_text" dir="auto"><b>📸 Parents Warned Not to Post Children's Photos Online</b><br/><br/>This can lead to AI fakes.</div>
  <a class="tgme_widget_message_date" href="https://t.me/perplexity/1034"><time datetime="2026-07-03T12:15:33+00:00" class="time">12:15</time></a>
</div>
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="perplexity/1046">
  <div class="tgme_widget_message_text js-message_text" dir="auto"><b>🌟 Naruto: Global Casting Hunt Begins</b></div>
  <a class="tgme_widget_message_date" href="https://t.me/perplexity/1046"><time datetime="2026-07-10T06:57:07+00:00" class="time">06:57</time></a>
</div>
"""


class SignalRadarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.saved = (
            signal_radar.DATA_DIR,
            signal_radar.OUTPUT_DIR,
            signal_radar.LAB_KNOWLEDGE,
            signal_radar.LAB_PROTOTYPES,
            signal_radar.STATE_PATH,
            signal_radar.LEDGER_PATH,
        )
        signal_radar.DATA_DIR = self.root / "data" / "signal_radar"
        signal_radar.OUTPUT_DIR = self.root / "output" / "signal-radar"
        signal_radar.LAB_KNOWLEDGE = self.root / "lab" / "knowledge"
        signal_radar.LAB_PROTOTYPES = self.root / "lab" / "prototypes"
        signal_radar.STATE_PATH = signal_radar.DATA_DIR / "state.json"
        signal_radar.LEDGER_PATH = signal_radar.DATA_DIR / "public_signals.jsonl"

    def tearDown(self):
        (
            signal_radar.DATA_DIR,
            signal_radar.OUTPUT_DIR,
            signal_radar.LAB_KNOWLEDGE,
            signal_radar.LAB_PROTOTYPES,
            signal_radar.STATE_PATH,
            signal_radar.LEDGER_PATH,
        ) = self.saved
        self.tmp.cleanup()

    def test_url_guard_blocks_private_targets(self):
        self.assertFalse(signal_radar.is_public_http_url("http://127.0.0.1:8000"))
        self.assertFalse(signal_radar.is_public_http_url("https://user:pass@example.com/x"))
        self.assertFalse(signal_radar.is_public_http_url("http://service.internal/x"))
        self.assertTrue(signal_radar.is_public_http_url("https://t.me/s/perplexity"))

    def test_parse_and_evaluate_messages(self):
        source = {"name": "Perplexity", "url": "https://t.me/s/perplexity"}
        messages = signal_radar.parse_telegram_public_html(HTML, source)
        self.assertEqual(len(messages), 3)

        findings = [signal_radar.evaluate_message(m) for m in messages]
        by_post = {f.post_url.rsplit("/", 1)[-1]: f for f in findings}
        self.assertEqual(by_post["1045"].status, "do-now")
        self.assertEqual(by_post["1045"].prototype_id, "chatgpt-work-operating-pattern")
        self.assertEqual(by_post["1034"].prototype_id, "publisher-privacy-guard")
        self.assertEqual(by_post["1046"].status, "skip")

    def test_run_once_writes_lab_report_and_prototypes(self):
        now = dt.datetime(2026, 7, 10, 9, 0, tzinfo=dt.timezone.utc)
        summary = signal_radar.run_once(
            now=now,
            sources=[{"name": "Perplexity", "url": "https://t.me/s/perplexity"}],
            fetcher=lambda url: HTML,
        )

        self.assertEqual(summary["new_signals"], 3)
        self.assertEqual(summary["kept"], 2)
        self.assertTrue((signal_radar.LAB_KNOWLEDGE / "INDEX.md").exists())
        self.assertTrue((signal_radar.LAB_PROTOTYPES / "backlog.json").exists())
        self.assertTrue((self.root / summary["report"]).exists())
        self.assertIn("publisher-privacy-guard", summary["prototype_updates"])

    def test_run_if_due_skips_until_interval_passes(self):
        now = dt.datetime(2026, 7, 10, 9, 0, tzinfo=dt.timezone.utc)
        signal_radar.run_once(
            now=now,
            sources=[{"name": "Perplexity", "url": "https://t.me/s/perplexity"}],
            fetcher=lambda url: HTML,
        )
        out = signal_radar.run_if_due(
            now=now + dt.timedelta(hours=1),
            interval_hours=24,
            fetcher=lambda url: HTML,
        )
        self.assertEqual(out["skipped"], "not_due")


if __name__ == "__main__":
    unittest.main()
