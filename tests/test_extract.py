"""Guards for the unified extraction tool (gateway.tools.extract).

Network is stubbed — these pin the LOGIC (escalation decision, content
cleaning, PDF/OCR routing), not live sites.
"""

import unittest
from unittest.mock import patch

from gateway.tools import extract


class ThinDetection(unittest.TestCase):
    def test_spa_shell_is_thin(self):
        # big inline JS, almost no visible text -> must escalate
        html = "<html><body><div id='root'></div>" + "<script>var x=1;" + "a" * 5000 + "</script></body></html>"
        self.assertTrue(extract._looks_thin(html))

    def test_content_page_is_not_thin(self):
        html = "<html><body><article>" + ("Bu real məzmundur. " * 60) + "</article></body></html>"
        self.assertFalse(extract._looks_thin(html))


class Fetch(unittest.TestCase):
    def test_requests_first_when_content_is_rich(self):
        rich = "<html><body><main>" + ("word " * 200) + "</main></body></html>"

        class R:
            status_code = 200
            text = rich

        with patch.object(extract.requests, "get", return_value=R()) as g, \
             patch.object(extract, "_fetch_browser") as browser:
            html, method = extract.fetch("https://site.test")

        self.assertEqual(method, "requests")
        browser.assert_not_called()
        g.assert_called_once()

    def test_escalates_to_browser_when_thin(self):
        class R:
            status_code = 200
            text = "<html><body><div id='app'></div></body></html>"

        with patch.object(extract.requests, "get", return_value=R()), \
             patch.object(extract, "_fetch_browser", return_value="<html><body><main>"
                          + ("real " * 200) + "</main></body></html>") as browser:
            html, method = extract.fetch("https://spa.test")

        self.assertEqual(method, "browser")
        browser.assert_called_once()

    def test_render_false_never_escalates(self):
        class R:
            status_code = 200
            text = "<html><body></body></html>"  # thin

        with patch.object(extract.requests, "get", return_value=R()), \
             patch.object(extract, "_fetch_browser") as browser:
            html, method = extract.fetch("https://x.test", render=False)

        self.assertEqual(method, "requests")
        browser.assert_not_called()


class ParserFallback(unittest.TestCase):
    """Without lxml the module used to raise inside fetch(), get swallowed by the
    escalation try/except, and silently send EVERY page down the slow browser
    path. It must degrade to the stdlib parser instead of misrouting."""

    def test_thin_check_still_correct_when_lxml_missing(self):
        import bs4
        real = bs4.BeautifulSoup

        def no_lxml(markup, features=None, *a, **kw):
            if features == "lxml":
                raise bs4.FeatureNotFound("lxml not installed")
            return real(markup, features, *a, **kw)

        rich = "<html><body><main>" + ("word " * 200) + "</main></body></html>"
        with patch.object(bs4, "BeautifulSoup", side_effect=no_lxml):
            self.assertFalse(extract._looks_thin(rich))     # rich stays rich
            self.assertTrue(extract._looks_thin("<html><body></body></html>"))

    def test_fast_path_survives_missing_lxml(self):
        import bs4
        real = bs4.BeautifulSoup

        def no_lxml(markup, features=None, *a, **kw):
            if features == "lxml":
                raise bs4.FeatureNotFound("lxml not installed")
            return real(markup, features, *a, **kw)

        class R:
            status_code = 200
            text = "<html><body><main>" + ("word " * 200) + "</main></body></html>"

        with patch.object(bs4, "BeautifulSoup", side_effect=no_lxml), \
             patch.object(extract.requests, "get", return_value=R()), \
             patch.object(extract, "_fetch_browser") as browser:
            _html, method = extract.fetch("https://site.test")

        self.assertEqual(method, "requests")   # NOT silently escalated
        browser.assert_not_called()


class Clean(unittest.TestCase):
    def test_strips_chrome_and_keeps_article(self):
        html = ("<html><body><nav>MENU</nav><script>junk()</script>"
                "<article><h1>Başlıq</h1><p>Mətn burada.</p></article>"
                "<footer>alt</footer></body></html>")
        text = extract.clean_text(html)
        self.assertIn("Başlıq", text)
        self.assertIn("Mətn burada.", text)
        self.assertNotIn("MENU", text)
        self.assertNotIn("junk", text)

    def test_scrape_routes_pdf_by_extension(self):
        with patch.object(extract, "read_pdf", return_value="PDF TEXT") as rp:
            r = extract.scrape("https://x.test/file.PDF")
        self.assertEqual(r["method"], "pdf")
        self.assertEqual(r["text"], "PDF TEXT")
        rp.assert_called_once()

    def test_scrape_never_raises(self):
        with patch.object(extract, "fetch", side_effect=RuntimeError("boom")):
            r = extract.scrape("https://x.test")
        self.assertFalse(r["ok"])
        self.assertIn("boom", r["error"])


if __name__ == "__main__":
    unittest.main()
