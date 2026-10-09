import unittest

from firecrawl_adapter import CRAWL_ENDPOINT, SCRAPE_ENDPOINT, FirecrawlClient, MISSING_CONFIG


class FakeTransport:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def __call__(self, url, *, method, headers, json):
        self.calls.append({"url": url, "method": method, "headers": headers, "json": json})
        if self.error is not None:
            raise self.error
        return self.response


class FirecrawlClientTests(unittest.TestCase):
    def test_scrape_posts_authenticated_payload_and_returns_provider_data(self):
        transport = FakeTransport({"status": 200, "body": {"success": True, "data": {"markdown": "hello"}}})
        client = FirecrawlClient("test-key", transport)

        result = client.scrape("https://example.com", formats=["markdown"], onlyMainContent=True)

        self.assertEqual(result, {"ok": True, "data": {"markdown": "hello"}})
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["url"], SCRAPE_ENDPOINT)
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["headers"], {"Authorization": "Bearer test-key", "Content-Type": "application/json"})
        self.assertEqual(call["json"], {"url": "https://example.com", "formats": ["markdown"], "onlyMainContent": True})

    def test_crawl_posts_to_crawl_endpoint_with_options(self):
        transport = FakeTransport({"status": 200, "body": {"success": True, "id": "crawl-1"}})
        client = FirecrawlClient("test-key", transport)

        result = client.crawl("https://example.com/docs", limit=25, maxDepth=2)

        self.assertEqual(result, {"ok": True, "data": {"id": "crawl-1"}})
        self.assertEqual(transport.calls[0]["url"], CRAWL_ENDPOINT)
        self.assertEqual(transport.calls[0]["json"], {"url": "https://example.com/docs", "limit": 25, "maxDepth": 2})

    def test_required_missing_key_returns_missing_config_without_calling_transport(self):
        transport = FakeTransport({"status": 200, "body": {"success": True}})
        client = FirecrawlClient(None, transport)

        result = client.scrape("https://example.com")

        self.assertTrue(FirecrawlClient.requires_key)
        self.assertEqual(result, {"ok": False, "error": MISSING_CONFIG})
        self.assertEqual(transport.calls, [])

    def test_http_error_returns_status_without_exposing_response_body(self):
        transport = FakeTransport({"status": 429, "body": {"error": "private provider detail"}})
        client = FirecrawlClient("test-key", transport)

        result = client.crawl("https://example.com")

        self.assertEqual(result, {"ok": False, "error": "HTTP_ERROR", "status": 429})

    def test_transport_exception_is_reported_without_leaking_exception_text(self):
        transport = FakeTransport(error=RuntimeError("secret diagnostic"))
        client = FirecrawlClient("test-key", transport)

        result = client.scrape("https://example.com")

        self.assertEqual(result, {"ok": False, "error": "TRANSPORT_ERROR"})
        self.assertNotIn("secret diagnostic", repr(result))


if __name__ == "__main__":
    unittest.main()
