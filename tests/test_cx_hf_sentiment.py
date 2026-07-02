import importlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CX_DIR = ROOT / "cx-command-center"


class CxHfSentimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_path = list(sys.path)
        sys.path.insert(0, str(CX_DIR))
        for name in ("config", "sentiment_hf", "triage"):
            sys.modules.pop(name, None)
        cls.config = importlib.import_module("config")
        cls.sentiment_hf = importlib.import_module("sentiment_hf")
        cls.triage = importlib.import_module("triage")

    @classmethod
    def tearDownClass(cls):
        sys.path[:] = cls._old_path

    def setUp(self):
        self._saved = {
            "enabled": self.config.HF_SENTIMENT_ENABLED,
            "endpoint": self.config.HF_SENTIMENT_ENDPOINT,
            "model": self.config.HF_SENTIMENT_MODEL,
            "allow_external": self.config.HF_SENTIMENT_ALLOW_EXTERNAL,
            "min_confidence": self.config.HF_SENTIMENT_MIN_CONFIDENCE,
            "ai_enabled": self.config.AI_ENABLED,
        }
        self._post = self.sentiment_hf._post
        self._urlopen = self.sentiment_hf.urlopen
        self._classify = self.triage.sentiment_hf.classify
        self.config.HF_SENTIMENT_ENABLED = True
        self.config.HF_SENTIMENT_ENDPOINT = "http://127.0.0.1:8815/sentiment"
        self.config.HF_SENTIMENT_MODEL = "local-hf-sentiment"
        self.config.HF_SENTIMENT_ALLOW_EXTERNAL = False
        self.config.HF_SENTIMENT_MIN_CONFIDENCE = 0.7
        self.config.AI_ENABLED = False

    def tearDown(self):
        self.config.HF_SENTIMENT_ENABLED = self._saved["enabled"]
        self.config.HF_SENTIMENT_ENDPOINT = self._saved["endpoint"]
        self.config.HF_SENTIMENT_MODEL = self._saved["model"]
        self.config.HF_SENTIMENT_ALLOW_EXTERNAL = self._saved["allow_external"]
        self.config.HF_SENTIMENT_MIN_CONFIDENCE = self._saved["min_confidence"]
        self.config.AI_ENABLED = self._saved["ai_enabled"]
        self.sentiment_hf._post = self._post
        self.sentiment_hf.urlopen = self._urlopen
        self.triage.sentiment_hf.classify = self._classify

    def test_hf_style_output_is_parsed(self):
        self.sentiment_hf._post = lambda text: [{"label": "NEGATIVE", "score": 0.96}]
        signal = self.sentiment_hf.classify("no response")
        self.assertIsNotNone(signal)
        self.assertEqual(signal.sentiment, "negative")
        self.assertEqual(signal.model, "local-hf-sentiment")

    def test_external_endpoint_blocked_by_default(self):
        self.config.HF_SENTIMENT_ENDPOINT = "https://api.example.com/models/sentiment"

        def fail(*_args, **_kwargs):
            raise AssertionError("external endpoint should not be reached")

        self.sentiment_hf.urlopen = fail
        self.assertFalse(self.sentiment_hf.status()["endpoint_private"])
        self.assertIsNone(self.sentiment_hf.classify("customer complaint"))

    def test_hf_negative_signal_elevates_public_triage(self):
        signal = self.sentiment_hf.SentimentSignal(
            sentiment="negative",
            confidence=0.95,
            label="NEGATIVE",
            model="local-hf-sentiment",
        )
        self.triage.sentiment_hf.classify = lambda text: signal
        out = self.triage.triage_message(
            {"channel": "instagram_comment", "text": "Please help with my policy", "_skip_ai": True}
        )
        self.assertEqual(out["sentiment"], "very_negative")
        self.assertEqual(out["severity"], "high")
        self.assertEqual(out["sentiment_source"], "rules+hf_local")
        self.assertEqual(out["hf_sentiment_label"], "NEGATIVE")

    def test_hf_positive_signal_does_not_downgrade_rule_risk(self):
        signal = self.sentiment_hf.SentimentSignal(
            sentiment="positive",
            confidence=0.99,
            label="POSITIVE",
            model="local-hf-sentiment",
        )
        self.triage.sentiment_hf.classify = lambda text: signal
        out = self.triage.triage_message(
            {"channel": "instagram_comment", "text": "complaint: no response, terrible delay", "_skip_ai": True}
        )
        self.assertIn(out["sentiment"], {"negative", "very_negative"})
        self.assertIn(out["severity"], {"high", "critical"})


if __name__ == "__main__":
    unittest.main()
