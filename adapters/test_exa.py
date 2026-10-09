import json as jsonlib
import unittest

from exa_adapter import ExaClient, MISSING_CONFIG


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, *, method, headers, json):
        self.calls.append({"url": url, "method": method, "headers": headers, "json": json})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ExaClientTests(unittest.TestCase):
    def test_requires_key_returns_missing_config_without_transport_call(self):
        transport = FakeTransport({"status": 200, "body": "{}"})
        client = ExaClient(api_key=None, transport=transport)

        result = client.search("test")

        self.assertEqual(result, {"ok": False, "error": MISSING_CONFIG})
        self.assertEqual(transport.calls, [])
        self.assertTrue(client.requires_key)

    def test_search_posts_exa_payload_and_parses_transport_response(self):
        expected = {"results": [{"title": "A", "url": "https://example.com"}]}
        transport = FakeTransport({"status": 200, "body": jsonlib.dumps(expected)})
        client = ExaClient(api_key="test-key", transport=transport)

        result = client.search("climate", num_results=3, search_type="neural")

        self.assertEqual(result, {"ok": True, "data": expected})
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["url"], "https://api.exa.ai/search")
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["headers"]["x-api-key"], "test-key")
        self.assertEqual(call["headers"]["Content-Type"], "application/json")
        self.assertEqual(call["json"], {"query": "climate", "numResults": 3, "type": "neural"})

    def test_search_includes_optional_contents_options(self):
        transport = FakeTransport({"status": 200, "body": "{}"})
        client = ExaClient(api_key="key", transport=transport)

        result = client.search("topic", contents={"text": True})

        self.assertTrue(result["ok"])
        self.assertEqual(transport.calls[0]["json"]["contents"], {"text": True})

    def test_contents_posts_ids_and_options(self):
        expected = {"results": [{"id": "https://example.com"}]}
        transport = FakeTransport({"status": 200, "body": jsonlib.dumps(expected)})
        client = ExaClient(api_key="key", transport=transport)

        result = client.contents(["https://example.com"], text=True)

        self.assertEqual(result, {"ok": True, "data": expected})
        self.assertEqual(transport.calls[0]["url"], "https://api.exa.ai/contents")
        self.assertEqual(transport.calls[0]["json"], {"ids": ["https://example.com"], "text": True})

    def test_contents_accepts_single_id(self):
        transport = FakeTransport({"status": 200, "body": "{}"})
        client = ExaClient(api_key="key", transport=transport)

        client.contents("https://example.com")

        self.assertEqual(transport.calls[0]["json"]["ids"], ["https://example.com"])

    def test_http_error_is_not_reported_as_success(self):
        transport = FakeTransport({"status": 429, "body": "rate limited"})
        client = ExaClient(api_key="key", transport=transport)

        result = client.search("topic")

        self.assertEqual(result, {"ok": False, "error": "HTTP_ERROR", "status": 429, "body": "rate limited"})
        self.assertEqual(len(transport.calls), 1)

    def test_transport_exception_propagates_without_retry_or_fallback(self):
        error = RuntimeError("offline")
        transport = FakeTransport(error)
        client = ExaClient(api_key="key", transport=transport)

        with self.assertRaisesRegex(RuntimeError, "offline"):
            client.search("topic")

        self.assertEqual(len(transport.calls), 1)

    def test_missing_transport_does_not_create_a_default_network_transport(self):
        client = ExaClient(api_key="key", transport=None)

        self.assertEqual(client.search("topic"), {"ok": False, "error": MISSING_CONFIG})


if __name__ == "__main__":
    unittest.main()
