import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "idea-studio" / "adsworld.py"
SPEC = importlib.util.spec_from_file_location("adsworld", MODULE_PATH)
adsworld = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(adsworld)


# Trimmed real markup from adsoftheworld.com/industries/insurance (2026-07-16).
LISTING_FIXTURE = """
<div class='flex-none text-right hidden md:block'><p class='text-dark'>435 Campaigns</p></div>
<div class='col-span-1 ...' id='campaign_card_120194'>
<a href="/campaigns/it-s-ok-i-m-with-the-aa"><picture>
<img alt="It&#39;s OK" src="https://image.adsoftheworld.com/e86i85a8qwmpvjd6p1dzqmqnluqk" />
</picture></a>
<div class='text-sm'><a class="hover:text-primary" href="/brands/the-aa">The AA</a></div>
<div class='karlasemibold text-lg leading-tight'><a class="hover:text-primary" href="/campaigns/it-s-ok-i-m-with-the-aa"><p>It&#39;s OK, I&#39;m with The AA</p></a></div>
<div class='text-sm mt-4'><a class="hover:text-primary" href="/agencies/the7stars">Agency: the7stars</a></div>
</div>
<div class='col-span-1 ...' id='campaign_card_120165'>
<a href="/campaigns/honesty-is-our-policy"><picture>
<img alt="Honesty" src="https://image.adsoftheworld.com/y4n2c0fhw0qeq6uqkofddm88vn7r" />
</picture></a>
<div class='text-sm'><a class="hover:text-primary" href="/brands/farmers-insurance">Farmers Insurance</a></div>
<div class='karlasemibold text-lg leading-tight'><a class="hover:text-primary" href="/campaigns/honesty-is-our-policy"><p>Honesty Is Our Policy</p></a></div>
<div class='text-sm mt-4'><a class="hover:text-primary" href="/agencies/dentsu-creative">Agency: Dentsu Creative</a></div>
</div>
<a href="/industries/insurance?page=2">2</a>
<a href="/industries/insurance?page=8">Last</a>
"""

CAMPAIGN_FIXTURE = """
<video controls="controls" poster="https://image.adsoftheworld.com/x" src="https://video.adsoftheworld.com/2uonwx7rjppymtptysz8jfmg46ua.mp4"></video>
<p class='text-grey text-sm mb-2'>Description</p>
<div class='mb-4 whitespace-pre-line flex flex-col gap-4'><p>Insurance is everywhere.</p>
<p>The hero :30 speaks directly to the audience.</p></div>
<p class="mb-6 text-sm">This  professional campaign titled 'Honesty Is Our Policy' was published in United States in July, 2026. It was created for the brand: Farmers Insurance, by ad agency: Dentsu Creative. This Digital, Experiential, and Film media campaign is related to the Insurance industry and contains 1 media asset. It was submitted 1 day ago.</p>
<p class='text-grey text-sm mb-2'>Credits</p>
<div class='mb-4'><p>Farmers Insurance:<br />Eleanor Solomon, Head of Creative</p></div>
"""


class ParseListingTests(unittest.TestCase):
    def test_parses_cards_total_and_pagination(self):
        parsed = adsworld.parse_listing(LISTING_FIXTURE)
        self.assertEqual(parsed["total_campaigns"], 435)
        self.assertEqual(parsed["last_page"], 8)
        self.assertEqual(len(parsed["campaigns"]), 2)
        first = parsed["campaigns"][0]
        self.assertEqual(first["title"], "It's OK, I'm with The AA")
        self.assertEqual(first["brand"], "The AA")
        self.assertEqual(first["agency"], "the7stars")
        self.assertEqual(first["slug"], "it-s-ok-i-m-with-the-aa")
        self.assertTrue(first["url"].startswith("https://www.adsoftheworld.com/campaigns/"))
        self.assertTrue(first["image"].startswith("https://image.adsoftheworld.com/"))

    def test_empty_page_yields_no_campaigns(self):
        parsed = adsworld.parse_listing("<html><body>nothing here</body></html>")
        self.assertEqual(parsed["campaigns"], [])
        self.assertIsNone(parsed["total_campaigns"])
        self.assertEqual(parsed["last_page"], 1)


class ParseCampaignTests(unittest.TestCase):
    def test_parses_summary_media_description_credits_video(self):
        detail = adsworld.parse_campaign(CAMPAIGN_FIXTURE)
        self.assertEqual(detail["title"], "Honesty Is Our Policy")
        self.assertEqual(detail["country"], "United States")
        self.assertEqual(detail["published"], "July 2026")
        self.assertEqual(detail["brands"], ["Farmers Insurance"])
        self.assertEqual(detail["agencies"], ["Dentsu Creative"])
        self.assertEqual(detail["media_types"], ["Digital", "Experiential", "Film"])
        self.assertEqual(detail["industries"], ["Insurance"])
        self.assertIn("Insurance is everywhere.", detail["description"])
        self.assertIn("hero :30", detail["description"])
        self.assertIn("Eleanor Solomon", detail["credits"])
        self.assertEqual(
            detail["video"],
            "https://video.adsoftheworld.com/2uonwx7rjppymtptysz8jfmg46ua.mp4",
        )

    def test_media_types_do_not_swallow_summary_sentence(self):
        detail = adsworld.parse_campaign(CAMPAIGN_FIXTURE)
        for media_type in detail["media_types"]:
            self.assertNotIn("campaign titled", media_type)
            self.assertNotIn("published", media_type)

    def test_apostrophe_title_in_summary(self):
        fixture = (
            "<p>This professional campaign titled 'It's OK, I'm with The AA' was "
            "published in United Kingdom in July, 2026. It was created for the "
            "brands: Sony Pictures and The AA, by ad agency: the7stars.</p>"
        )
        detail = adsworld.parse_campaign(fixture)
        self.assertEqual(detail["title"], "It's OK, I'm with The AA")
        self.assertEqual(detail["brands"], ["Sony Pictures", "The AA"])


class CacheAndGuardTests(unittest.TestCase):
    def test_is_fresh_window(self):
        now = datetime.now(timezone.utc)
        fresh = {"fetched_at": (now - timedelta(days=2)).isoformat(timespec="seconds")}
        stale = {"fetched_at": (now - timedelta(days=9)).isoformat(timespec="seconds")}
        self.assertTrue(adsworld.is_fresh(fresh, now=now))
        self.assertFalse(adsworld.is_fresh(stale, now=now))
        self.assertFalse(adsworld.is_fresh({}, now=now))
        self.assertFalse(adsworld.is_fresh({"fetched_at": "not-a-date"}, now=now))

    def test_http_get_refuses_foreign_hosts(self):
        with self.assertRaises(ValueError):
            adsworld.http_get("https://evil.example.com/industries/insurance")
        with self.assertRaises(ValueError):
            adsworld.http_get("http://localhost:8000/x")

    def test_download_media_refuses_foreign_hosts(self):
        for url in (
            "https://evil.example.com/video.mp4",
            "http://video.adsoftheworld.com/x.mp4",  # http, not https
            "https://www.adsoftheworld.com/campaigns/x",  # page, not CDN
        ):
            with self.assertRaises(ValueError):
                adsworld.download_media(url, Path("unused.mp4"))

    def test_extract_frames_degrades_without_ffmpeg(self):
        original = adsworld.FFMPEG_TOOLS_GLOB
        adsworld.FFMPEG_TOOLS_GLOB = "no-such-dir/*/bin"
        try:
            frames, notes = adsworld.extract_frames(Path("v.mp4"), Path("."))
        finally:
            adsworld.FFMPEG_TOOLS_GLOB = original
        self.assertEqual(frames, [])
        self.assertTrue(any("frames skipped" in note for note in notes))


class ExecutorRailTests(unittest.TestCase):
    """The swipe rail's cue matching (gateway/executor.py)."""

    @classmethod
    def setUpClass(cls):
        import sys

        sys.path.insert(0, str(ROOT))
        from gateway import executor

        cls.executor = executor

    def test_swipe_cues_match(self):
        for task in ("swipe həftəlik", "Swipe heftelik", "/swipe insurance", "adsworld refresh"):
            self.assertTrue(self.executor._is_swipe(task), task)

    def test_ordinary_tasks_do_not_match(self):
        for task in ("Publish the article", "radar həftəlik", "qiymət nədir?", ""):
            self.assertFalse(self.executor._is_swipe(task), task)


class DigestTests(unittest.TestCase):
    def payload(self):
        return {
            "schema_version": 1,
            "source": "https://www.adsoftheworld.com/industries/insurance",
            "industry": "insurance",
            "label": "DEMO",
            "fetched_at": "2026-07-16T10:00:00+00:00",
            "pages_fetched": 1,
            "total_campaigns_on_site": 435,
            "campaigns": [
                {
                    "slug": "honesty-is-our-policy",
                    "url": "https://www.adsoftheworld.com/campaigns/honesty-is-our-policy",
                    "title": "Honesty Is Our Policy",
                    "brand": "Farmers Insurance",
                    "agency": "Dentsu Creative",
                    "image": None,
                    "detail": {
                        "country": "United States",
                        "published": "July 2026",
                        "media_types": ["Film"],
                        "description": "Insurance is everywhere.",
                    },
                }
            ],
            "errors": [{"url": "https://www.adsoftheworld.com/industries/insurance?page=2", "error": "HTTP 500"}],
        }

    def test_digest_carries_label_errors_and_facts(self):
        digest = adsworld.render_digest(self.payload())
        self.assertIn("label: DEMO", digest)
        self.assertIn("Fetch errors (not silently dropped)", digest)
        self.assertIn("HTTP 500", digest)
        self.assertIn("### Honesty Is Our Policy — Farmers Insurance", digest)
        self.assertIn("United States · July 2026 · Film", digest)
        self.assertIn("Insurance is everywhere.", digest)
        self.assertIn("--industry insurance --fresh", digest)


if __name__ == "__main__":
    unittest.main()
