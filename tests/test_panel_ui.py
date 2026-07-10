"""Guards for the panel front office UI (v3.1) — the features live inside the
_HTML literal, so these checks keep a refactor from silently dropping them."""

import unittest

from gateway import panel


class PanelUIFeatures(unittest.TestCase):
    def test_voice_input_present(self):
        # mic button + Web Speech wiring (az-AZ) — the dashboard half of voice control
        self.assertIn('id="micBtn"', panel._HTML)
        self.assertIn('az-AZ', panel._HTML)
        self.assertIn('webkitSpeechRecognition', panel._HTML)

    def test_markdown_renderer_present_and_escape_survived(self):
        self.assertIn("function md(", panel._HTML)
        # regex must reach the browser as \n — if a Python edit un-escapes it to a
        # real newline the JS breaks; this is the canary
        self.assertIn(r"[^`\n]", panel._HTML)
        self.assertNotIn("[^`\n]", panel._HTML)

    def test_gallery_search_present(self):
        self.assertIn('id="gq"', panel._HTML)
        self.assertIn("function setQuery", panel._HTML)

    def test_chat_copy_and_expand_present(self):
        self.assertIn("copyBub", panel._HTML)
        self.assertIn("toggleMore", panel._HTML)


if __name__ == "__main__":
    unittest.main()
