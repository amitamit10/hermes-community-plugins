import unittest

from tavily_adapter import MISSING_CONFIG, TavilyAdapter, TavilyClient


class FakeTransport:
    def __init__(self, response=None):
        self.calls = []
        self.response = {"ok": True, "results": []} if response is None else response

    def __call__(self, url, *, method, headers, json):
        self.calls.append({"url": url, "method": method, "headers": headers, "json": json})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class TavilyAdapterTests(unittest.TestCase):
    def test_client_name_and_adapter_alias_are_consistent(self):
        self.assertIs(TavilyAdapter, TavilyClient)
        self.assertTrue(TavilyClient.requires_key)

    def test_requires_key_and_missing_key_fails_before_transport(self):
        transport = FakeTransport()
        client = TavilyClient(api_key="  ", transport=transport)

        self.assertTrue(client.requires_key)
        self.assertEqual(client.search("cats"), {"ok": False, "error": MISSING_CONFIG})
        self.assertEqual(transport.calls, [])

    def test_search_posts_query_and_options_with_bearer_auth(self):
        response = {"results": [{"title": "Example"}]}
        transport = FakeTransport(response)
        client = TavilyClient(api_key="test-key", transport=transport)

        result = client.search("cats", search_depth="advanced", max_results=3)

        self.assertEqual(result, {"ok": True, "data": response})
        self.assertEqual(transport.calls, [{
            "url": "https://api.tavily.com/search",
            "method": "POST",
            "headers": {
                "Authorization": "Bearer test-key",
                "Content-Type": "application/json",
            },
            "json": {"query": "cats", "search_depth": "advanced", "max_results": 3},
        }])

    def test_extract_wraps_a_single_url_and_passes_options(self):
        transport = FakeTransport({"results": []})
        client = TavilyClient(api_key="test-key", transport=transport)

        client.extract("https://example.test/article", extract_depth="advanced")

        self.assertEqual(transport.calls[0]["url"], "https://api.tavily.com/extract")
        self.assertEqual(transport.calls[0]["json"], {
            "urls": ["https://example.test/article"],
            "extract_depth": "advanced",
        })

    def test_extract_preserves_a_batch_of_urls(self):
        transport = FakeTransport()
        client = TavilyClient(api_key="test-key", transport=transport)
        urls = ["https://example.test/a", "https://example.test/b"]

        client.extract(urls)

        self.assertEqual(transport.calls[0]["json"], {"urls": urls})

    def test_crawl_posts_url_and_options(self):
        transport = FakeTransport({"results": []})
        client = TavilyClient(api_key="test-key", transport=transport)

        client.crawl("https://example.test", max_depth=2, limit=4)

        self.assertEqual(transport.calls[0]["url"], "https://api.tavily.com/crawl")
        self.assertEqual(transport.calls[0]["json"], {
            "url": "https://example.test",
            "max_depth": 2,
            "limit": 4,
        })

    def test_missing_key_blocks_every_endpoint(self):
        transport = FakeTransport()
        client = TavilyClient(api_key=None, transport=transport)

        results = [client.search("cats"), client.extract("https://example.test"), client.crawl("https://example.test")]

        self.assertEqual(results, [{"ok": False, "error": MISSING_CONFIG}] * 3)
        self.assertEqual(transport.calls, [])

    def test_extract_parses_response_envelope_json_body(self):
        expected = {"results": [{"url": "https://example.test"}]}
        transport = FakeTransport({"status": 200, "body": expected})
        client = TavilyClient(api_key="test-key", transport=transport)

        result = client.extract("https://example.test")

        self.assertEqual(result, {"ok": True, "data": expected})

    def test_missing_transport_returns_missing_config_without_default_network(self):
        client = TavilyClient(api_key="test-key")

        self.assertEqual(client.search("cats"), {"ok": False, "error": MISSING_CONFIG})

    def test_transport_exception_returns_sanitized_error(self):
        transport = FakeTransport(RuntimeError("offline diagnostic"))
        client = TavilyClient(api_key="test-key", transport=transport)

        result = client.crawl("https://example.test")

        self.assertEqual(result, {"ok": False, "error": "TRANSPORT_ERROR"})
        self.assertNotIn("offline diagnostic", repr(result))



if __name__ == "__main__":
    unittest.main()
