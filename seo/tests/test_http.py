"""Network-free tests for the hardened fetch (seo/http.py).

Both recoveries were proven live on xalqsigorta.az: a cert chain that only
strict-verifies via the OS store is retried unverified (so the on-page audit
still runs, flagged), and a dead apex is retried via www. Here requests.request
is mocked so the fallbacks are exercised deterministically, no internet.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from seo import http


class _Resp:
    """Minimal stand-in for a streamed requests.Response."""

    def __init__(self, url="https://www.site.az/", status=200, body=b"<html><title>ok</title></html>"):
        self.url = url
        self.status_code = status
        self.ok = 200 <= status < 400
        self.encoding = "utf-8"
        self.headers = {"Content-Type": "text/html; charset=utf-8"}
        self._body = body

    def iter_content(self, n):
        yield self._body


class SslFallback(unittest.TestCase):
    def test_ssl_error_retries_unverified_and_flags_chain(self):
        calls = []

        def fake(method, url, **kw):
            calls.append(kw.get("verify", True))
            if kw.get("verify", True):
                raise requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED")
            return _Resp(url=url)

        with patch.object(http.requests, "request", side_effect=fake):
            f = http.fetch("https://site.az")

        self.assertTrue(f.ok)
        self.assertTrue(f.html)               # page still read
        self.assertFalse(f.ssl_verified)      # defect recorded, not hidden
        self.assertIn("CERTIFICATE", f.ssl_error)
        self.assertEqual(calls, [True, False])  # verified try, then unverified retry

    def test_double_ssl_failure_reports_error(self):
        with patch.object(http.requests, "request",
                          side_effect=requests.exceptions.SSLError("boom")):
            f = http.fetch("https://site.az")
        self.assertFalse(f.ok)
        self.assertFalse(f.ssl_verified)
        self.assertTrue(f.error)


class ApexFallback(unittest.TestCase):
    def test_dead_apex_falls_back_to_www_and_flags(self):
        def fake(method, url, **kw):
            if "www." not in url:               # apex times out
                raise requests.exceptions.ConnectionError("timed out")
            return _Resp(url="https://www.site.az/")

        with patch.object(http.requests, "request", side_effect=fake):
            f = http.fetch("https://site.az")

        self.assertTrue(f.ok)
        self.assertTrue(f.apex_unreachable)
        self.assertEqual(f.requested_url, "https://site.az")   # remembers the ask
        self.assertIn("www.", f.url)
        self.assertIn("www.", f.www_fallback_url)

    def test_www_host_does_not_double_fall_back(self):
        # a request that already targets www must not recurse into www.www
        seen = []

        def fake(method, url, **kw):
            seen.append(url)
            raise requests.exceptions.ConnectionError("timed out")

        with patch.object(http.requests, "request", side_effect=fake):
            f = http.fetch("https://www.site.az")

        self.assertFalse(f.ok)
        self.assertFalse(f.apex_unreachable)
        self.assertEqual(len(seen), 1)  # no www fallback attempt


class HappyPath(unittest.TestCase):
    def test_clean_fetch_is_verified_and_reachable(self):
        with patch.object(http.requests, "request", return_value=_Resp()):
            f = http.fetch("https://www.site.az")
        self.assertTrue(f.ok and f.html)
        self.assertTrue(f.ssl_verified)
        self.assertFalse(f.apex_unreachable)


if __name__ == "__main__":
    unittest.main()
