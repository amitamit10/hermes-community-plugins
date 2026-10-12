"""Injected-provider result-boundary tests (offline, fakes only)."""

import socket
import unittest
from unittest import mock

from anysearch_adapter import AnySearchClient
from donsetch_adapter import DonsetchAdapter
from exa_adapter import ExaClient
from firecrawl_adapter import FirecrawlClient
from serper_you_adapter import AdapterResult, SerperClient, YouClient
from tavily_adapter import TavilyClient


PUBLIC_RESOLVER = lambda host, port, **kwargs: ["93.184.216.34"]  # noqa: E731
PUBLIC_CODES = frozenset(("URL_BLOCKED", "REDIRECT_BLOCKED", "MISSING_CONFIG"))


def rpc_text(text):
    return {"status": 200, "body": {"jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text", "text": text}]}}}


class RpcTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, *, method, headers, json):
        self.calls.append({"url": url, "method": method})
        response = self.responses.pop(0) if self.responses else {"status": 200, "body": {}}
        if isinstance(response, BaseException):
            raise response
        return response


class JsonTransport:
    def __init__(self, response=None):
        self.calls = []
        self.response = {"ok": True, "results": []} if response is None else response

    def __call__(self, url, *, method, headers, json):
        self.calls.append(url)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class PostTransport:
    def __init__(self, response=None):
        self.calls = []
        self.response = {"organic": []} if response is None else response

    def __call__(self, *, method, url, headers, json):
        self.calls.append(url)
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def assert_nested(testcase, result, expected):
    testcase.assertIsInstance(result, dict)
    testcase.assertIs(result.get("ok"), False)
    testcase.assertEqual(result.get("error"), {"code": expected})


class ProviderContractTests(unittest.TestCase):
    def setUp(self):
        self._dns = mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("no DNS"))
        self._conn = mock.patch.object(socket, "create_connection", side_effect=AssertionError("no connect"))
        self._dns.start()
        self._conn.start()
        self.addCleanup(self._dns.stop)
        self.addCleanup(self._conn.stop)

    def test_tavily_success_missing_invalid_and_redirect(self):
        transport = JsonTransport({"results": [{"title": "T"}]})
        client = TavilyClient(api_key="k", transport=transport, resolver=PUBLIC_RESOLVER)
        for name, call in [
            ("search", lambda: client.search("cats")),
            ("extract", lambda: client.extract("https://example.test/a")),
            ("crawl", lambda: client.crawl("https://example.test")),
        ]:
            with self.subTest(op=name):
                result = call()
                self.assertIs(result.get("ok"), True)
                self.assertIn("data", result)
        self.assertEqual(len(transport.calls), 3)

        missing = TavilyClient(api_key=None, transport=JsonTransport())
        for name, call in [("search", lambda: missing.search("q")), ("extract", lambda: missing.extract("https://example.test")), ("crawl", lambda: missing.crawl("https://example.test"))]:
            with self.subTest(op="missing-" + name):
                assert_nested(self, call(), "MISSING_CONFIG")
        self.assertEqual(missing._transport.calls if hasattr(missing, "_transport") else [], [])

        bad = TavilyClient(api_key="k", transport=JsonTransport({"ok": True}))
        assert_nested(self, bad.search(""), "URL_BLOCKED")

        class RedirectErr(Exception):
            code = "REDIRECT_BLOCKED"
        red = TavilyClient(api_key="k", transport=JsonTransport(RedirectErr("secret_redirect_diagnostic")))
        result = red.search("cats")
        assert_nested(self, result, "REDIRECT_BLOCKED")
        self.assertNotIn("secret_redirect_diagnostic", repr(result))

    def test_exa_success_missing_invalid_and_sanitized(self):
        transport = JsonTransport({"status": 200, "body": {"results": [{"id": "1"}]}})
        client = ExaClient(api_key="k", transport=transport)
        result = client.search("topic")
        self.assertIs(result.get("ok"), True)
        self.assertIn("data", result)
        self.assertEqual(len(transport.calls), 1)

        result = client.contents(["https://example.test/a"])
        self.assertIs(result.get("ok"), True)

        assert_nested(self, ExaClient(api_key=None, transport=JsonTransport()).search("q"), "MISSING_CONFIG")
        assert_nested(self, client.search(""), "URL_BLOCKED")
        err = ExaClient(api_key="k", transport=JsonTransport(RuntimeError("secret-body")))
        result = err.search("topic")
        assert_nested(self, result, "URL_BLOCKED")
        self.assertNotIn("secret-body", repr(result))

    def test_firecrawl_missing_transport_before_dns_and_sanitized(self):
        spy = mock.Mock(side_effect=AssertionError("resolver must not run for missing transport"))
        client = FirecrawlClient("k", None, resolver=spy)
        for name, call in [("scrape", lambda: client.scrape("https://example.test")), ("crawl", lambda: client.crawl("https://example.test"))]:
            with self.subTest(op=name):
                assert_nested(self, call(), "MISSING_CONFIG")
        spy.assert_not_called()

        transport = JsonTransport({"status": 200, "body": {"success": True, "data": {"markdown": "hi"}}})
        client = FirecrawlClient("k", transport, resolver=PUBLIC_RESOLVER)
        result = client.scrape("https://example.test")
        self.assertIs(result.get("ok"), True)
        self.assertEqual(len(transport.calls), 1)

        bad = FirecrawlClient("k", JsonTransport(RuntimeError("leak-status")), resolver=PUBLIC_RESOLVER)
        result = bad.scrape("https://example.test")
        assert_nested(self, result, "URL_BLOCKED")
        self.assertNotIn("leak", repr(result))

    def test_anysearch_success_missing_batch_discovery_and_redirect(self):
        transport = RpcTransport(rpc_text("results"))
        client = AnySearchClient(transport=transport, resolver=PUBLIC_RESOLVER)
        result = client.search("climate")
        self.assertIs(result.get("ok"), True)
        self.assertEqual(len(transport.calls), 1)

        transport = RpcTransport(rpc_text("b"), rpc_text("m"), rpc_text("m"))
        client = AnySearchClient(transport=transport, resolver=PUBLIC_RESOLVER)
        self.assertIs(client.batch_search([{"query": "one"}, {"query": "two", "max_results": 2}]).get("ok"), True)
        self.assertIs(client.extract("https://example.com/a").get("ok"), True)

        assert_nested(self, AnySearchClient(transport=None).search("q"), "MISSING_CONFIG")
        assert_nested(self, AnySearchClient(transport=RpcTransport(rpc_text("x"))).batch_search("bad"), "URL_BLOCKED")
        assert_nested(self, AnySearchClient(transport=RpcTransport(rpc_text("x"))).extract("http://bad"), "URL_BLOCKED")

        table = "| domain | sub_domain | description | query_format | params_schema | zone |\n| --- | --- | --- | --- | --- | --- |\n| finance | finance.us_stock | s | ticker | ticker (required) | US |"
        transport = RpcTransport(rpc_text(table), rpc_text("stocks"))
        client = AnySearchClient(transport=transport, resolver=PUBLIC_RESOLVER)
        disc = client.vertical_discover("finance")
        self.assertIs(disc.get("ok"), True)
        alias = client.get_sub_domains("finance")
        self.assertIs(alias.get("ok"), True)

        class RedirectErr(Exception):
            code = "REDIRECT_BLOCKED"
        red = AnySearchClient(transport=RpcTransport(RedirectErr("nested-detail")))
        assert_nested(self, red.search("q"), "REDIRECT_BLOCKED")

    def test_serper_you_mappings_and_missing_config(self):
        self.assertIn("status", AdapterResult.__dataclass_fields__)
        serper_transport = PostTransport({"organic": [{"title": "T"}]})
        serper = SerperClient(transport=serper_transport, endpoint="https://serper.invalid/search",
                              auth_header="X-K", payload_builder=lambda q: {"q": q})
        result = serper.search("query", api_key="k")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("status"), "OK")
        self.assertEqual(result.get("data"), {"organic": [{"title": "T"}]})
        self.assertEqual(len(serper_transport.calls), 1)

        you_transport = PostTransport({"results": [{"title": "Y"}]})
        you = YouClient(transport=you_transport)
        result = you.search("query", api_key="k")
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get("status"), "OK")

        assert_nested(self, SerperClient(transport=PostTransport()).search("q", api_key=None), "MISSING_CONFIG")
        assert_nested(self, YouClient(transport=PostTransport()).search("q", api_key=" "), "MISSING_CONFIG")
        assert_nested(self, SerperClient(transport=PostTransport()).search("q", api_key="k"), "MISSING_CONFIG")
        assert_nested(self, serper.search("", api_key="k"), "URL_BLOCKED")

    def test_provider_http_429_and_nested_redirect_boundaries(self):
        tavily_transport = JsonTransport({"status": 429, "body": {"message": "rate-limited-secret"}})
        result = TavilyClient(api_key="k", transport=tavily_transport, resolver=PUBLIC_RESOLVER).search("cats")
        assert_nested(self, result, "HTTP_ERROR")
        self.assertEqual(result.get("status"), 429)
        self.assertNotIn("rate-limited-secret", repr(result))
        self.assertEqual(len(tavily_transport.calls), 1)

        exa_transport = JsonTransport({"status": 429, "body": "rate-limited-secret"})
        result = ExaClient(api_key="k", transport=exa_transport).search("topic")
        assert_nested(self, result, "HTTP_ERROR")
        self.assertEqual(result.get("status"), 429)
        self.assertNotIn("rate-limited-secret", repr(result))
        self.assertEqual(len(exa_transport.calls), 1)

        fire_transport = JsonTransport({"status": 429, "body": {"error": "rate-limited-secret"}})
        result = FirecrawlClient("k", fire_transport, resolver=PUBLIC_RESOLVER).scrape("https://example.test")
        assert_nested(self, result, "HTTP_ERROR")
        self.assertEqual(result.get("status"), 429)
        self.assertNotIn("rate-limited-secret", repr(result))
        self.assertEqual(len(fire_transport.calls), 1)

        serper_transport = PostTransport({"status": 429, "error": "rate-limited-secret"})
        serper = SerperClient(transport=serper_transport, endpoint="https://serper.invalid/search",
                              auth_header="X-K", payload_builder=lambda q: {"q": q})
        result = serper.search("query", api_key="k")
        assert_nested(self, result, "HTTP_ERROR")
        self.assertNotIn("status", result)
        self.assertNotIn("rate-limited-secret", repr(result))
        self.assertEqual(len(serper_transport.calls), 1)

        you_transport = PostTransport({"status": 429, "error": "rate-limited-secret"})
        result = YouClient(transport=you_transport).search("query", api_key="k")
        assert_nested(self, result, "HTTP_ERROR")
        self.assertNotIn("status", result)
        self.assertNotIn("rate-limited-secret", repr(result))
        self.assertEqual(len(you_transport.calls), 1)

        nested_transport = RpcTransport({"ok": False, "error": {"code": "REDIRECT_BLOCKED"}})
        result = AnySearchClient(transport=nested_transport, resolver=PUBLIC_RESOLVER).search("q")
        assert_nested(self, result, "REDIRECT_BLOCKED")
        self.assertEqual(len(nested_transport.calls), 1)

    def test_serper_you_unconfigured_transport_is_missing_config(self):
        for name, make in [
            ("serper-none", lambda: SerperClient(transport=None, endpoint="https://serper.invalid/search",
                                                 auth_header="X-K", payload_builder=lambda q: {"q": q}).search("q", api_key="k")),
            ("serper-noncallable", lambda: SerperClient(transport=object(), endpoint="https://serper.invalid/search",
                                                        auth_header="X-K", payload_builder=lambda q: {"q": q}).search("q", api_key="k")),
            ("you-none", lambda: YouClient(transport=None).search("q", api_key="k")),
            ("you-noncallable", lambda: YouClient(transport=object()).search("q", api_key="k")),
        ]:
            with self.subTest(op=name):
                assert_nested(self, make(), "MISSING_CONFIG")

    def test_donsetch_fail_closed_and_unavailable_normalizes_missing(self):
        missing = DonsetchAdapter(binary_checker=lambda path: False).check()
        assert_nested(self, missing, "MISSING_CONFIG")
        self.assertNotIn("explanation", missing)

        broken = DonsetchAdapter(binary_checker=lambda path: True).check()
        assert_nested(self, broken, "MISSING_CONFIG")
        self.assertNotIn("explanation", broken)
        self.assertNotIn("GLIBC", repr(broken))


if __name__ == "__main__":
    unittest.main()
