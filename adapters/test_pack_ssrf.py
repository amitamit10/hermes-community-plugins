"""Offline regression tests for the pack-level SSRF boundary."""

import runpy
import socket
import unittest
from unittest import mock

import ssrf_guard
import browser_tier as browser_tier_module
import free_search as free_search_module
from anysearch_adapter import AnySearchClient
from browser_tier import render_js
from firecrawl_adapter import SCRAPE_ENDPOINT, FirecrawlClient
from free_search import MAX_RESPONSE_BYTES, duckduckgo_search
from native_tier import NativeTier, native_extract
from rss_watcher import RSSWatcher
from ssrf_guard import (
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    GuardError,
    check_url,
    pinned_fetch,
    resolve_and_validate,
)
from tavily_adapter import TavilyClient


class FakeResponse:
    def __init__(self, status=200, body=b"ok", headers=()):
        self.status = status
        self._body = body
        self._headers = list(headers)

    def read(self, size=-1):
        return self._body if size < 0 else self._body[:size]

    def getheaders(self):
        return self._headers


class FakeConnection:
    def __init__(self, host, address, response, opened):
        self.host = host
        self.address = address
        self.response = response
        self.opened = opened

    def request(self, method, path, headers):
        self.opened.append((self.host, self.address, method, path, headers))

    def getresponse(self):
        return self.response

    def close(self):
        pass


class CallLog:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"ok": True, "data": "unused"}


class PackSSRFGateTests(unittest.TestCase):
    def test_import_does_not_resolve_dns(self):
        with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS during import")) as lookup:
            runpy.run_path(ssrf_guard.__file__)
        lookup.assert_not_called()

    def test_url_policy_requires_https_default_port_and_public_hosts(self):
        self.assertTrue(check_url("https://www.example.test/page")[0])
        for url in (
            "http://www.example.test/",
            "https://www.example.test:8443/",
            "https://127.0.0.1/",
            "https://[::1]/",
            "https://169.254.169.254/latest/meta-data/",
            "https://localhost/",
        ):
            with self.subTest(url=url):
                self.assertFalse(check_url(url)[0])

    def test_dns_private_answer_is_rejected(self):
        resolver = lambda host, port, **kwargs: ["10.0.0.7"]
        with self.assertRaises(GuardError):
            resolve_and_validate("public.example", resolver=resolver)

    def test_dns_mixed_public_and_private_answers_fail_closed(self):
        resolver = lambda host, port, **kwargs: ["93.184.216.34", "192.168.1.2"]
        with self.assertRaises(GuardError):
            resolve_and_validate("public.example", resolver=resolver)

    def test_pinned_fetch_connects_to_the_resolved_address(self):
        opened = []
        resolver = lambda host, port, **kwargs: ["93.184.216.34"]

        def connection_factory(host, address, timeout):
            return FakeConnection(host, address, FakeResponse(), opened)

        response = pinned_fetch(
            "https://www.example.test/page",
            resolver=resolver,
            connection_factory=connection_factory,
        )

        self.assertEqual(response["body"], b"ok")
        self.assertEqual(opened[0][1], "93.184.216.34")
        self.assertEqual(opened[0][2:4], ("GET", "/page"))

    def test_dns_rebinding_is_rechecked_and_private_answer_never_connects(self):
        answers = iter((["93.184.216.34"], ["127.0.0.1"]))
        resolver = lambda host, port, **kwargs: next(answers)
        opened = []

        def connection_factory(host, address, timeout):
            return FakeConnection(host, address, FakeResponse(), opened)

        pinned_fetch("https://rebind.example.test/", resolver=resolver,
                     connection_factory=connection_factory)
        with self.assertRaises(GuardError):
            pinned_fetch("https://rebind.example.test/", resolver=resolver,
                         connection_factory=connection_factory)

        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0][1], "93.184.216.34")

    def test_private_redirect_is_rejected_before_private_connection(self):
        opened = []
        resolver = lambda host, port, **kwargs: ["93.184.216.34"]

        def connection_factory(host, address, timeout):
            response = FakeResponse(
                status=302,
                body=b"",
                headers=[("Location", "https://169.254.169.254/latest/meta-data/")],
            )
            return FakeConnection(host, address, response, opened)

        with self.assertRaises(GuardError) as caught:
            pinned_fetch(
                "https://public.example.test/",
                resolver=resolver,
                connection_factory=connection_factory,
            )

        self.assertEqual(caught.exception.code, REDIRECT_BLOCKED)
        self.assertEqual(len(opened), 1)

    def test_free_search_default_fetch_uses_pinned_transport(self):
        url = "https://html.duckduckgo.com/html/?q=query"
        with mock.patch.object(
            free_search_module,
            "pinned_fetch",
            return_value={"status": 200, "body": b"", "url": url},
        ) as fetch:
            result = duckduckgo_search("query")

        self.assertTrue(result["ok"])
        fetch.assert_called_once_with(url, max_response_bytes=MAX_RESPONSE_BYTES)

    def test_browser_default_fetch_uses_pinned_transport(self):
        url = "https://public.example.test/page"
        with mock.patch.object(
            browser_tier_module,
            "pinned_fetch",
            return_value={"status": 200, "body": b"public article content", "headers": {}, "url": url},
        ) as fetch:
            result = browser_tier_module.BrowserTier().fetch(url)

        self.assertTrue(result["ok"])
        fetch.assert_called_once_with(url, resolver=None, max_redirects=0)

    def test_free_search_caps_injected_response_bytes(self):
        calls = []

        def transport(url):
            calls.append(url)
            return b"x" * (MAX_RESPONSE_BYTES + 1)

        result = duckduckgo_search("query", transport=transport)

        self.assertEqual(result, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(len(calls), 1)

    def test_free_search_dns_preflight_blocks_private_answer_before_transport(self):
        calls = []
        result = duckduckgo_search(
            "query",
            transport=lambda url: calls.append(url),
            resolver=lambda host, port, **kwargs: ["10.20.30.40"],
        )

        self.assertEqual(result, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(calls, [])

    def test_rss_watcher_rejects_oversized_feed_before_xml_parse(self):
        watcher = RSSWatcher(lambda url: {"status": 200, "body": b" " * (MAX_RESPONSE_BYTES + 1)})

        with self.assertRaisesRegex(ValueError, "byte limit"):
            watcher.poll("https://feed.example.test/rss")

    def test_native_extract_rejects_loopback_before_callable(self):
        tool = CallLog()

        result = native_extract("https://127.0.0.1/private", tool)

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(tool.calls, [])

    def test_native_extract_rejects_private_dns_before_callable(self):
        tool = CallLog()
        tier = NativeTier(web_extract=tool, resolver=lambda host, port, **kwargs: ["10.1.2.3"])

        result = tier.extract("https://public.example.test/page")

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(tool.calls, [])

    def test_browser_rejects_callable_bypass_without_gate_or_request_logs(self):
        def bypass(url, *, request_gate):
            return {"status": 200, "body": "private fetch happened", "url": url}

        result = render_js("https://public.example.test/page", bypass)

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})

    def test_browser_dns_private_address_is_blocked_before_callable(self):
        calls = []

        def browser(url, *, request_gate):
            calls.append(url)
            request_gate(url)
            return {"status": 200, "body": "content", "url": url}

        result = render_js(
            "https://public.example.test/page",
            browser,
            resolver=lambda host, port, **kwargs: ["172.16.0.4"],
        )

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(calls, [])

    def test_provider_extract_and_crawl_block_unsafe_urls_without_remote_posts(self):
        any_transport = CallLog()
        tavily_transport = CallLog()
        firecrawl_transport = CallLog()
        any_client = AnySearchClient(transport=any_transport)
        tavily_client = TavilyClient(api_key="key", transport=tavily_transport)
        firecrawl_client = FirecrawlClient("key", firecrawl_transport)

        results = (
            any_client.extract("http://example.com/"),
            tavily_client.extract(["https://example.com/", "https://127.0.0.1/actually-private"]),
            tavily_client.crawl("https://example.com:8443/"),
            firecrawl_client.scrape("https://[::1]/"),
            firecrawl_client.crawl("http://example.com/"),
        )

        self.assertEqual(results, ({"error": {"code": URL_BLOCKED}},) * 5)
        self.assertEqual(any_transport.calls, [])
        self.assertEqual(tavily_transport.calls, [])
        self.assertEqual(firecrawl_transport.calls, [])

    def test_firecrawl_options_cannot_override_validated_target(self):
        transport = CallLog()
        client = FirecrawlClient("key", transport)
        target = "https://public.example.test/article"

        result = client._post(SCRAPE_ENDPOINT, target, {"url": "https://127.0.0.1/private"})

        self.assertTrue(result["ok"])
        self.assertEqual(transport.calls[0][1]["json"]["url"], target)

    def test_provider_dns_private_answers_block_requests(self):
        resolver = lambda host, port, **kwargs: ["100.64.0.9"]
        any_transport = CallLog()
        tavily_transport = CallLog()
        firecrawl_transport = CallLog()

        results = (
            AnySearchClient(transport=any_transport, resolver=resolver).extract("https://public.example.test/"),
            TavilyClient(api_key="key", transport=tavily_transport, resolver=resolver).crawl("https://public.example.test/"),
            FirecrawlClient("key", firecrawl_transport, resolver=resolver).scrape("https://public.example.test/"),
        )

        self.assertEqual(results, ({"error": {"code": URL_BLOCKED}},) * 3)
        self.assertEqual(any_transport.calls, [])
        self.assertEqual(tavily_transport.calls, [])
        self.assertEqual(firecrawl_transport.calls, [])


if __name__ == "__main__":
    unittest.main()
