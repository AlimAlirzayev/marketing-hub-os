import unittest

from brain import embeddings
from gateway import rag


class GatewayRagEmbeddingTests(unittest.TestCase):
    def test_rag_uses_shared_embedding_adapter(self):
        calls = []
        old = embeddings.embed

        def fake_embed(text, *, use_cache=True, require_enabled=True):
            calls.append((text, require_enabled))
            return [0.4, 0.5]

        try:
            embeddings.embed = fake_embed
            self.assertEqual(rag._get_embedding("policy"), [0.4, 0.5])
        finally:
            embeddings.embed = old

        self.assertEqual(calls, [("policy", False)])

    def test_rag_fails_clearly_when_no_embedding_provider_available(self):
        old = embeddings.embed
        try:
            embeddings.embed = lambda *args, **kwargs: None
            with self.assertRaisesRegex(RuntimeError, "No embedding provider"):
                rag._get_embedding("policy")
        finally:
            embeddings.embed = old


if __name__ == "__main__":
    unittest.main()
