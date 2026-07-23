"""Guards for the knowledge-graph first slice (gateway.knowledge_graph).

Logic tests run on a synthetic in-memory graph (no files); one smoke test builds
from the real corpus to confirm it parses what we actually own.
"""

import unittest

from gateway import knowledge_graph as kg


class Extraction(unittest.TestCase):
    def test_terms_in_matches_lexicon_and_wikilinks(self):
        terms = kg._terms_in("We moved the floor to gpt-oss on Groq. See [[voice-fix]].")
        self.assertIn("gpt-oss", terms)
        self.assertIn("groq", terms)
        self.assertIn("floor", terms)
        self.assertIn("voice-fix", terms)  # from the wikilink

    def test_terms_in_ignores_absent(self):
        self.assertNotIn("kubernetes", kg._terms_in("a plain instagram caption"))


class GraphLogic(unittest.TestCase):
    def _graph(self):
        g = kg.Graph()
        # two entries sharing the tag 'instagram' + a term
        g.add_entry("dec:0", "social lane refuses IG links", "instagram reel refusal",
                    kind="decision", ts=100, tags=["instagram", "social"])
        g.add_entry("dec:1", "yt-dlp + IG cookies", "instagram cookies via yt-dlp",
                    kind="decision", ts=200, tags=["instagram", "cookies"])
        # an unrelated entry
        g.add_entry("dec:2", "gpt-oss floor", "groq gpt-oss brain floor",
                    kind="decision", ts=300, tags=["brain", "floor"])
        return g

    def test_add_entry_creates_tag_and_term_links(self):
        g = self._graph()
        self.assertEqual(g.entry_count(), 3)
        self.assertIn("tag:instagram", g.nodes)
        self.assertIn("term:instagram", g.nodes)  # 'instagram' is in the lexicon
        # dec:0 is linked to the instagram tag
        self.assertIn(("tag:instagram", "HAS_TAG"), g.adj["dec:0"])

    def test_related_connects_via_shared_tag(self):
        g = self._graph()
        kg._CACHE, kg._CACHE_AT = g, kg.time.time()  # inject synthetic graph
        try:
            hits = kg.related("instagram", limit=10)
            labels = [h["label"] for h in hits]
            self.assertIn("social lane refuses IG links", labels)
            self.assertIn("yt-dlp + IG cookies", labels)
            # the unrelated brain/floor entry should NOT be pulled in by 'instagram'
            self.assertNotIn("gpt-oss floor", labels)
        finally:
            kg._CACHE = None

    def test_related_empty_for_unknown(self):
        g = self._graph()
        kg._CACHE, kg._CACHE_AT = g, kg.time.time()
        try:
            self.assertEqual(kg.related("kubernetes helm istio"), [])
        finally:
            kg._CACHE = None

    def test_graph_recall_formats_hits(self):
        g = self._graph()
        kg._CACHE, kg._CACHE_AT = g, kg.time.time()
        try:
            out = kg.graph_recall("instagram")
            self.assertIn("Bilik qrafı", out)
            self.assertIn("yt-dlp + IG cookies", out)
        finally:
            kg._CACHE = None


class RealCorpusSmoke(unittest.TestCase):
    def test_build_reads_real_corpus(self):
        g = kg.build(force=True)
        # the real corpus has hundreds of decisions + lessons; just prove it parsed
        self.assertGreater(g.entry_count(), 20)
        s = kg.stats()
        self.assertGreater(s["tags"], 0)
        self.assertGreaterEqual(s["edges"], s["entries"])


if __name__ == "__main__":
    unittest.main()
