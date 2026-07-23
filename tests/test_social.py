"""Guards for the social-content lane (gateway.social).

All offline: _fetch (network) and brain.answer (LLM) are patched, so no HTTP and
no cap dependency. These lock in the 2026-07-22 fix — a social link must produce
a grounded Azerbaijani deliverable, never the old English persona-refusal.
"""

import unittest
from unittest.mock import patch

from gateway import social


class Detection(unittest.TestCase):
    def test_find_urls_trims_trailing_punctuation(self):
        self.assertEqual(
            social.find_urls("bax bura https://youtu.be/abcDEFghij1, gözəldir."),
            ["https://youtu.be/abcDEFghij1"])

    def test_platform_mapping(self):
        self.assertEqual(social.platform_of("https://www.instagram.com/reel/X/"), "Instagram")
        self.assertEqual(social.platform_of("https://youtu.be/abc"), "YouTube")
        self.assertEqual(social.platform_of("https://www.tiktok.com/@x/video/1"), "TikTok")
        self.assertIsNone(social.platform_of("https://example.com/page"))

    def test_is_social_url(self):
        self.assertTrue(social.is_social_url("https://www.instagram.com/reel/Da-07K-H53z/"))
        self.assertFalse(social.is_social_url("Xalq Sığorta üçün post hazırla"))
        self.assertFalse(social.is_social_url("https://example.com bax"))

    def test_youtube_id(self):
        self.assertEqual(social._youtube_id("https://youtu.be/abcDEFghij1"), "abcDEFghij1")
        self.assertEqual(social._youtube_id("https://www.youtube.com/watch?v=abcDEFghij1"), "abcDEFghij1")
        self.assertIsNone(social._youtube_id("https://www.youtube.com/"))


class MetaParsing(unittest.TestCase):
    PAGE = (
        '<meta property="og:title" content="Mohsin Ali on Instagram" />'
        '<meta property="og:description" content="6,597 likes - #AI #YOLOv8" />'
        '<meta property="og:image" content="https://cdn/thumb.jpg" />'
    )

    def test_meta_reads_property_and_content(self):
        self.assertEqual(social._meta(self.PAGE, "og:title"), "Mohsin Ali on Instagram")
        self.assertIn("YOLOv8", social._meta(self.PAGE, "og:description"))
        self.assertEqual(social._meta(self.PAGE, "og:image"), "https://cdn/thumb.jpg")

    def test_meta_missing_is_empty(self):
        self.assertEqual(social._meta(self.PAGE, "og:video"), "")


class Extract(unittest.TestCase):
    def setUp(self):
        # Force the OG/oEmbed fallback path so these stay offline + deterministic
        # (yt-dlp would otherwise make a real network call).
        p = patch.object(social, "_extract_ytdlp", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_extract_og_pulls_caption(self):
        page = ('<meta property="og:title" content="Author on Instagram">'
                '<meta property="og:description" content="a nice reel caption">')
        with patch.object(social, "_fetch", return_value=page):
            ref = social.extract("https://www.instagram.com/reel/ABC/")
        self.assertEqual(ref["platform"], "Instagram")
        self.assertEqual(ref["caption"], "a nice reel caption")

    def test_extract_never_raises_on_network_error(self):
        with patch.object(social, "_fetch", side_effect=OSError("timeout")):
            ref = social.extract("https://www.instagram.com/reel/ABC/")
        self.assertEqual(ref["platform"], "Instagram")
        self.assertIn("error", ref)


class Handle(unittest.TestCase):
    def setUp(self):
        p = patch.object(social, "_extract_ytdlp", return_value=None)
        p.start()
        self.addCleanup(p.stop)

    def test_handle_grounds_prompt_in_caption_and_returns_az(self):
        page = ('<meta property="og:title" content="mohcinale on Instagram">'
                '<meta property="og:description" content="#SpeedTracking #YOLOv8 #AI">')
        captured = {}

        def fake_answer(prompt, system=None, prefer="claude", timeout=120):
            captured["prompt"] = prompt
            captured["system"] = system
            return ("Bu bir texniki reel-dir. Xalq Sığorta üçün belə edərdim...", "claude:sonnet-5")

        with patch.object(social, "_fetch", return_value=page), \
             patch.object(social.brain, "answer", side_effect=fake_answer):
            text, label = social.handle(
                "https://www.instagram.com/reel/Da-07K-H53z/")
        # the real caption reached the brain (grounded, not hallucinated)
        self.assertIn("YOLOv8", captured["prompt"])
        self.assertTrue(label.startswith("social:"))
        self.assertIn("Xalq Sığorta", text)

    def test_handle_passes_instruction_when_present(self):
        page = '<meta property="og:description" content="ref caption">'
        captured = {}

        def fake_answer(prompt, system=None, prefer="claude", timeout=120):
            captured["prompt"] = prompt
            captured["system"] = system
            return ("hazırdır", "claude:sonnet-5")

        with patch.object(social, "_fetch", return_value=page), \
             patch.object(social.brain, "answer", side_effect=fake_answer):
            social.handle("Xalq Sığorta üçün belə video hazırla https://www.instagram.com/p/ABC/")
        self.assertIn("belə video hazırla", captured["prompt"])
        self.assertNotIn("just the link", captured["system"])  # instruction path

    def test_handle_bare_link_uses_bare_hint(self):
        page = '<meta property="og:description" content="ref">'
        captured = {}

        def fake_answer(prompt, system=None, prefer="claude", timeout=120):
            captured["system"] = system
            return ("qısa oxunuş", "claude:sonnet-5")

        with patch.object(social, "_fetch", return_value=page), \
             patch.object(social.brain, "answer", side_effect=fake_answer):
            social.handle("https://www.instagram.com/reel/ABC/")
        self.assertIn("only the link", captured["system"])

    def test_handle_flags_unreadable_link_for_honesty(self):
        # A login-wall page with no OG tags -> empty caption. The prompt MUST tell
        # the brain the link was unreadable, so it never fakes having watched it.
        captured = {}

        def fake_answer(prompt, system=None, prefer="claude", timeout=120):
            captured["prompt"] = prompt
            return ("Linki aça bilmədim, caption-u ata bilərsən?", "claude:sonnet-5")

        with patch.object(social, "_fetch", return_value="<html>login wall</html>"), \
             patch.object(social.brain, "answer", side_effect=fake_answer):
            social.handle("Xalq Sığorta üçün belə video hazırla "
                          "https://www.instagram.com/reel/ABC/")
        self.assertIn("could NOT be read", captured["prompt"])
        self.assertIn("none of the links could be read", captured["prompt"])

    def test_handle_falls_back_honestly_on_brain_error(self):
        page = '<meta property="og:description" content="ref caption text">'
        with patch.object(social, "_fetch", return_value=page), \
             patch.object(social.brain, "answer", return_value=("[brain error] X: y", "none")):
            text, label = social.handle("https://www.instagram.com/reel/ABC/")
        # honest AZ fallback, not an English refusal or a stack trace
        self.assertIn("ref caption text", text)
        self.assertNotIn("[brain error]", text)


class YtDlp(unittest.TestCase):
    def test_extract_prefers_ytdlp_when_it_reads(self):
        rich = {"platform": "Instagram", "url": "u", "author": "mohcinale",
                "title": "", "caption": "real reel caption via cookies",
                "engagement": "6,597 views"}
        with patch.object(social, "_extract_ytdlp", return_value=rich), \
             patch.object(social, "_fetch", side_effect=AssertionError("OG must NOT be hit")):
            ref = social.extract("https://www.instagram.com/reel/ABC/")
        self.assertEqual(ref["caption"], "real reel caption via cookies")
        self.assertEqual(ref["engagement"], "6,597 views")

    def test_extract_falls_back_to_og_when_ytdlp_blocked(self):
        page = '<meta property="og:description" content="og fallback caption">'
        with patch.object(social, "_extract_ytdlp", return_value=None), \
             patch.object(social, "_fetch", return_value=page):
            ref = social.extract("https://www.instagram.com/reel/ABC/")
        self.assertEqual(ref["caption"], "og fallback caption")

    def test_ytdlp_opts_adds_cookies_only_when_file_present(self):
        with patch.object(social.os.path, "exists", return_value=True):
            self.assertIn("cookiefile",
                          social._ytdlp_opts("https://www.instagram.com/reel/ABC/"))
        with patch.object(social.os.path, "exists", return_value=False):
            self.assertNotIn("cookiefile",
                             social._ytdlp_opts("https://www.instagram.com/reel/ABC/"))
        # a YouTube URL never attaches IG cookies
        with patch.object(social.os.path, "exists", return_value=True):
            self.assertNotIn("cookiefile",
                             social._ytdlp_opts("https://youtu.be/abcDEFghij1"))


if __name__ == "__main__":
    unittest.main()
