import os
import shutil
import tempfile
import unittest

from brain import embeddings, store


class BrainEmbeddingProviderTests(unittest.TestCase):
    def setUp(self):
        self._env_keys = [
            "BRAIN_EMBEDDINGS",
            "BRAIN_EMBED_PROVIDER",
            "BRAIN_EMBED_ENDPOINT",
            "BRAIN_EMBED_MODEL",
            "BRAIN_EMBED_ALLOW_EXTERNAL",
            "BRAIN_EMBED_AUTH_TOKEN",
            "BRAIN_EMBED_TIMEOUT_SECONDS",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        ]
        self._saved_env = {key: os.environ.get(key) for key in self._env_keys}
        for key in self._env_keys:
            os.environ.pop(key, None)

        self._tmp = tempfile.mkdtemp(prefix="brain_embed_")
        self._store_paths = (store.STORE_DIR, store.PENDING_DIR, store.INDEX_FILE)
        store.STORE_DIR = type(store.STORE_DIR)(self._tmp)
        store.PENDING_DIR = store.STORE_DIR / "_pending"
        store.INDEX_FILE = store.STORE_DIR / "INDEX.md"

        self._cache = embeddings._cache
        self._cache_path = embeddings._cache_path
        embeddings._cache = None
        embeddings._cache_path = None
        self._post_json = embeddings._post_json

    def tearDown(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        store.STORE_DIR, store.PENDING_DIR, store.INDEX_FILE = self._store_paths
        embeddings._cache = self._cache
        embeddings._cache_path = self._cache_path
        embeddings._post_json = self._post_json
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_embeddings_disabled_returns_none(self):
        self.assertIsNone(embeddings.embed("KASKO policy"))

    def test_gemini_is_blocked_without_explicit_external_approval(self):
        from unittest import mock

        os.environ["BRAIN_EMBEDDINGS"] = "1"
        os.environ["BRAIN_EMBED_PROVIDER"] = "gemini"
        os.environ["BRAIN_EMBED_ALLOW_EXTERNAL"] = "0"
        os.environ["GEMINI_API_KEY"] = "test-key"
        with mock.patch.object(embeddings, "_embed_gemini") as hosted:
            self.assertIsNone(embeddings.embed("internal policy", use_cache=False))
        hosted.assert_not_called()

    def test_local_tei_endpoint_parses_and_caches_vector(self):
        os.environ["BRAIN_EMBEDDINGS"] = "1"
        os.environ["BRAIN_EMBED_PROVIDER"] = "tei"
        os.environ["BRAIN_EMBED_ENDPOINT"] = "http://127.0.0.1:8080/embed"
        calls = []

        def fake_post(url, payload, headers, timeout):
            calls.append((url, payload, headers, timeout))
            return [[0.1, 0.2, 0.3]]

        embeddings._post_json = fake_post
        self.assertEqual(embeddings.embed("KASKO policy"), [0.1, 0.2, 0.3])
        self.assertEqual(embeddings.embed("KASKO policy"), [0.1, 0.2, 0.3])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], {"inputs": "KASKO policy"})

    def test_openai_compatible_endpoint_shape(self):
        os.environ["BRAIN_EMBEDDINGS"] = "1"
        os.environ["BRAIN_EMBED_PROVIDER"] = "openai"
        os.environ["BRAIN_EMBED_MODEL"] = "local-embed"
        os.environ["BRAIN_EMBED_ENDPOINT"] = "http://127.0.0.1:8080/v1/embeddings"
        calls = []

        def fake_post(url, payload, headers, timeout):
            calls.append(payload)
            return {"data": [{"embedding": [1, 2, 3]}]}

        embeddings._post_json = fake_post
        self.assertEqual(embeddings.embed("internal docs"), [1.0, 2.0, 3.0])
        self.assertEqual(calls[0], {"model": "local-embed", "input": "internal docs"})

    def test_external_endpoint_blocked_by_default(self):
        os.environ["BRAIN_EMBEDDINGS"] = "1"
        os.environ["BRAIN_EMBED_PROVIDER"] = "tei"
        os.environ["BRAIN_EMBED_ENDPOINT"] = "https://api.example.com/embed"

        def fake_post(url, payload, headers, timeout):
            raise AssertionError("external endpoint should not be called")

        embeddings._post_json = fake_post
        self.assertIsNone(embeddings.embed("customer data"))

    def test_provider_info_redacts_endpoint_credentials(self):
        os.environ["BRAIN_EMBED_PROVIDER"] = "tei"
        os.environ["BRAIN_EMBED_ENDPOINT"] = "http://user:pass@127.0.0.1:8080/embed"
        info = embeddings.provider_info()
        self.assertEqual(info["endpoint"], "http://127.0.0.1:8080/embed")
        self.assertTrue(info["endpoint_private"])


if __name__ == "__main__":
    unittest.main()
