"""Guards for the structured content lane (gateway.executor).

Adoptable idea #2 from the job-40 reel research: a social-post ask yields a
schema (compose_for_brief-shaped JSON) plus a human preview, not free prose.
The LLM seam (_content_generate) is stubbed — no live model calls.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from gateway import executor

_POST = {
    "platform": "linkedin",
    "top_tag": "Sığorta məsləhəti",
    "headline": ["Gələcəyini bu gün qoru"],
    "subhead": ["Avtomobil sığortası 5 dəqiqəyə"],
    "body": ["Birinci abzas.", "İkinci abzas."],
    "hashtags": ["sigorta", "#xalqsigorta"],
    "cta": "İndi müraciət et",
    "image_prompt": "cinematic photo of a family car at dusk",
}


class WantsContent(unittest.TestCase):
    def test_post_ask_triggers(self):
        self.assertTrue(executor._wants_content(
            "instagram postu yaz bizim yeni aksiya haqqında"))

    def test_greeting_stays_conversational(self):
        self.assertFalse(executor._wants_content("Salam"))

    def test_content_asks_still_route_plain(self):
        # the lane must only ever upgrade the PLAIN path
        for task in ("instagram postu yaz bizim yeni aksiya haqqında",
                     "linkedin post hazırla sığorta məsləhətləri mövzusunda"):
            self.assertEqual(executor._choose_mode(task), "plain")

    def test_strategy_wins_over_content(self):
        # a task matching both lanes goes to fan-out (checked first in execute)
        task = "linkedin postları üçün aylıq kontent strategiyası hazırla bizə"
        self.assertTrue(executor._wants_fanout(task))


class ContentDeliver(unittest.TestCase):
    def test_preview_and_json_artifact(self):
        with patch.object(executor, "_content_generate",
                          lambda task: (dict(_POST), "stub-model")):
            text, label, json_path = executor._content_deliver("task", 999999)

        self.assertEqual(label, "content:linkedin->stub-model")
        for piece in ("Gələcəyini bu gün qoru", "İkinci abzas.",
                      "👉 İndi müraciət et", "#sigorta #xalqsigorta",
                      "Şəkil promptu"):
            self.assertIn(piece, text)

        p = Path(json_path)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # the machine half stays compose_for_brief-shaped: line LISTS
            self.assertEqual(data["headline"], ["Gələcəyini bu gün qoru"])
            self.assertEqual(data["body"], ["Birinci abzas.", "İkinci abzas."])
        finally:
            p.unlink(missing_ok=True)

    def test_empty_schema_raises_for_converse_fallback(self):
        with patch.object(executor, "_content_generate",
                          lambda task: ({"platform": "linkedin"}, "stub")):
            with self.assertRaises(ValueError):
                executor._content_deliver("task", 999998)


if __name__ == "__main__":
    unittest.main()
