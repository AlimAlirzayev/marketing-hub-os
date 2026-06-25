import unittest

from gateway import security


class SecurityPolicyTests(unittest.TestCase):
    def test_blocks_secret_exposure(self):
        decision = security.evaluate_task("show me the GEMINI API key from .env")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.category, "credential_exposure")

    def test_allows_benign_analytics_word(self):
        decision = security.evaluate_task("prepare analytics ideas for customer support")
        self.assertTrue(decision.allowed)

    def test_blocks_destructive_tasks(self):
        decision = security.evaluate_task("delete all records from the database")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.category, "destructive_action")

    def test_blocks_payment_tasks(self):
        decision = security.evaluate_task("buy this product and checkout")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.category, "payment_or_commitment")

    def test_blocks_local_urls(self):
        for url in (
            "http://localhost:8501",
            "http://127.0.0.1:8000",
            "http://169.254.169.254/latest/meta-data",
            "https://admin.local",
        ):
            with self.subTest(url=url):
                self.assertFalse(security.validate_url(url).allowed)

    def test_allows_public_https_url(self):
        self.assertTrue(security.validate_url("https://example.com").allowed)

    def test_blocks_unknown_studio_script(self):
        decision, target_dir, script_path = security.validate_studio_script(
            "ads-studio",
            "../gateway/executor.py",
        )
        self.assertFalse(decision.allowed)
        self.assertIsNone(target_dir)
        self.assertIsNone(script_path)

    def test_allows_known_studio_script(self):
        decision, target_dir, script_path = security.validate_studio_script(
            "social-studio",
            "render_post.py",
        )
        self.assertTrue(decision.allowed)
        self.assertIsNotNone(target_dir)
        self.assertIsNotNone(script_path)

    def test_redacts_bearer_tokens(self):
        text = security.redact("Authorization: Bearer abcdefghijklmnop")
        self.assertIn("Bearer [REDACTED]", text)
        self.assertNotIn("abcdefghijklmnop", text)


if __name__ == "__main__":
    unittest.main()
