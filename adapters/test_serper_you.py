import unittest

from serper_you_adapter import MISSING_CONFIG, SerperClient, YouClient


class FakeTransport:
    def __init__(self, response=None):
        self.calls = []
        self.response = {"ok": True} if response is None else response

    def __call__(self, *, method, url, headers, json):
        self.calls.append({
            "method": method,
            "url": url,
            "headers": dict(headers),
            "json": dict(json),
        })
        return self.response


class AdapterTests(unittest.TestCase):
    def test_missing_key_returns_missing_config_without_transport_call(self):
        for client_type in (SerperClient, YouClient):
            with self.subTest(client=client_type.__name__):
                transport = FakeTransport()
                client = client_type(transport=transport)
                result = client.search("example", api_key=None)

                self.assertEqual(result.status, MISSING_CONFIG)
                self.assertEqual(transport.calls, [])

    def test_serper_is_marked_experimental_and_unverified(self):
        self.assertTrue(SerperClient.requires_key)
        self.assertTrue(SerperClient.experimental)
        self.assertFalse(SerperClient.verified)
        self.assertEqual(SerperClient.verification_status, "experimental/unverified")

    def test_serper_requires_explicit_endpoint_auth_and_payload_schema(self):
        transport = FakeTransport()
        client = SerperClient(transport=transport)

        result = client.search("example", api_key="test-key")

        self.assertEqual(result.status, "UNVERIFIED_CONFIG")
        self.assertEqual(transport.calls, [])

    def test_serper_sends_only_explicitly_configured_request_details(self):
        transport = FakeTransport({"organic": []})
        client = SerperClient(
            transport=transport,
            endpoint="https://serper.invalid/search",
            auth_header="X-Test-Key",
            payload_builder=lambda query: {"q": query},
        )

        result = client.search("example query", api_key="test-key")

        self.assertEqual(result.status, "OK")
        self.assertEqual(result.data, {"organic": []})
        self.assertEqual(transport.calls, [{
            "method": "POST",
            "url": "https://serper.invalid/search",
            "headers": {"X-Test-Key": "test-key", "Content-Type": "application/json"},
            "json": {"q": "example query"},
        }])

    def test_you_search_uses_verified_endpoint_and_keyed_post(self):
        transport = FakeTransport({"results": [{"title": "Example"}]})
        client = YouClient(transport=transport)

        result = client.search("example query", api_key="test-key")

        self.assertEqual(result.status, "OK")
        self.assertEqual(result.data, {"results": [{"title": "Example"}]})
        self.assertEqual(transport.calls, [{
            "method": "POST",
            "url": "https://ydc-index.io/v1/search",
            "headers": {"X-API-Key": "test-key", "Content-Type": "application/json"},
            "json": {"query": "example query"},
        }])


if __name__ == "__main__":
    unittest.main()
