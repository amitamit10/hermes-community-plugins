import unittest

from anysearch_adapter import (
    ENDPOINT,
    MISSING_CONFIG,
    MISSING_REQUIRED_PARAMS,
    URL_BLOCKED,
    AnySearchClient,
)


def rpc_text(text):
    return {
        "status": 200,
        "body": {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": text}]},
        },
    }


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, *, method, headers, json):
        self.calls.append({
            "url": url,
            "method": method,
            "headers": dict(headers),
            "json": json,
        })
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AnySearchAdapterTests(unittest.TestCase):
    def test_anonymous_search_omits_authorization_and_uses_rpc_tool_call(self):
        transport = FakeTransport(rpc_text("results"))
        client = AnySearchClient(transport=transport)

        result = client.search("  climate  ", max_results=4)

        self.assertEqual(result, {"ok": True, "data": "results"})
        self.assertEqual(len(transport.calls), 1)
        call = transport.calls[0]
        self.assertEqual(call["url"], ENDPOINT)
        self.assertEqual(call["method"], "POST")
        self.assertEqual(call["headers"], {"Content-Type": "application/json"})
        self.assertEqual(call["json"]["method"], "tools/call")
        self.assertEqual(call["json"]["params"], {
            "name": "search",
            "arguments": {"query": "climate", "max_results": 4},
        })
        self.assertFalse(client.requires_key)

    def test_optional_api_key_uses_bearer_authorization(self):
        transport = FakeTransport(rpc_text("keyed"))
        client = AnySearchClient(transport=transport, api_key=" test-key ")

        result = client.search("query")

        self.assertTrue(result["ok"])
        self.assertEqual(transport.calls[0]["headers"], {
            "Content-Type": "application/json",
            "Authorization": "Bearer test-key",
        })

    def test_batch_search_and_extract_dispatch_to_expected_tools(self):
        transport = FakeTransport(rpc_text("batch"), rpc_text("markdown"))
        client = AnySearchClient(transport=transport)

        batch = client.batch_search([{"query": "one"}, {"query": "two", "max_results": 2}])
        extracted = client.extract("https://example.com/article")

        self.assertEqual(batch, {"ok": True, "data": "batch"})
        self.assertEqual(extracted, {"ok": True, "data": "markdown"})
        self.assertEqual(transport.calls[0]["json"]["params"], {
            "name": "batch_search",
            "arguments": {"queries": [
                {"query": "one"},
                {"query": "two", "max_results": 2},
            ]},
        })
        self.assertEqual(transport.calls[1]["json"]["params"], {
            "name": "extract",
            "arguments": {"url": "https://example.com/article"},
        })

    def test_vertical_discovery_enforces_required_params_but_accepts_empty_value(self):
        table = (
            "| domain | sub_domain | description | query_format | params_schema | zone |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| finance | finance.us_stock | US stocks | ticker | ticker (required) | US |"
        )
        transport = FakeTransport(rpc_text(table), rpc_text("stock results"))
        client = AnySearchClient(transport=transport)

        discovered = client.vertical_discover(domain="finance")
        missing = client.search("TSLA", domain="finance", sub_domain="finance.us_stock")
        searched = client.search(
            "TSLA",
            domain="finance",
            sub_domain="finance.us_stock",
            sub_domain_params={"ticker": ""},
        )

        self.assertTrue(discovered["ok"])
        self.assertEqual(missing, {
            "ok": False,
            "error": MISSING_REQUIRED_PARAMS,
            "missing": ["ticker"],
        })
        self.assertEqual(searched, {"ok": True, "data": "stock results"})
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(transport.calls[0]["json"]["params"], {
            "name": "get_sub_domains",
            "arguments": {"domain": "finance"},
        })
        self.assertEqual(transport.calls[1]["json"]["params"]["arguments"], {
            "query": "TSLA",
            "domain": "finance",
            "sub_domain": "finance.us_stock",
            "sub_domain_params": {"ticker": ""},
        })

    def test_vertical_search_requires_discovery_first(self):
        transport = FakeTransport(rpc_text("unused"))
        client = AnySearchClient(transport=transport)

        result = client.search("AAPL", domain="finance", sub_domain="finance.us_stock")

        self.assertEqual(result, {"ok": False, "error": "VERTICAL_DISCOVERY_REQUIRED"})
        self.assertEqual(transport.calls, [])

    def test_quota_http_response_maps_to_url_blocked_without_retry(self):
        transport = FakeTransport({"status": 429, "body": {"error": "quota exceeded"}})
        client = AnySearchClient(transport=transport)

        result = client.search("query")

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(len(transport.calls), 1)

    def test_network_failure_maps_to_url_blocked_without_fallback(self):
        transport = FakeTransport(ConnectionError("offline"))
        client = AnySearchClient(transport=transport)

        result = client.search("query")

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(len(transport.calls), 1)

    def test_missing_transport_returns_missing_config_without_network_fallback(self):
        client = AnySearchClient()

        self.assertEqual(client.search("query"), {"ok": False, "error": MISSING_CONFIG})


if __name__ == "__main__":
    unittest.main()
