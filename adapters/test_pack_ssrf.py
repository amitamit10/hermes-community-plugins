"""Offline regression tests for the pack-level SSRF boundary."""

import runpy
import socket
import unittest
from unittest import mock

import ssrf_guard
import browser_tier as browser_tier_module
import crawl_pro as crawl_pro_module
import free_search as free_search_module
import native_tier as native_tier_module
from anysearch_adapter import AnySearchClient
from browser_tier import render_js
from crawl_pro import crawl_pro
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

    def test_native_extract_passes_pinned_fetch_to_capable_adapter(self):
        url = "https://native.example.test/article"
        fetch_calls = []

        def fake_pinned_fetch(target, **kwargs):
            fetch_calls.append((target, kwargs))
            return {"body": b"pinned body"}

        def extract(*, urls, char_limit, pinned_fetch, resolved_addresses):
            self.assertEqual(resolved_addresses, ("93.184.216.34",))
            fetched = pinned_fetch(urls[0])
            return {"results": [{"url": urls[0], "content": fetched["body"].decode()}]}

        with mock.patch.object(native_tier_module, "pinned_fetch", side_effect=fake_pinned_fetch):
            result = native_extract(
                url,
                extract,
                resolver=lambda host, port, **kwargs: ["93.184.216.34"],
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["content"], "pinned body")
        self.assertEqual(fetch_calls[0][0], url)
        self.assertEqual(fetch_calls[0][1]["resolver"]("native.example.test", 443), ["93.184.216.34"])

    def test_native_extract_blocks_private_dns_with_injected_resolver(self):
        url = "https://private-dns.example.test/page"
        calls = []

        def extract(*, urls, char_limit):
            calls.append((urls, char_limit))
            return {"results": [{"url": url, "content": "must not be fetched"}]}

        resolver_calls = []

        def resolver(host, port, **kwargs):
            resolver_calls.append((host, port))
            return ["10.1.2.3"]

        result = native_extract(url, extract, resolver=resolver)

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(calls, [])
        self.assertEqual(resolver_calls, [("private-dns.example.test", 443)])

    def test_browser_default_path_blocks_private_dns_with_fake_resolver(self):
        url = "https://private-dns.example.test/page"
        resolver_calls = []

        def resolver(host, port, **kwargs):
            resolver_calls.append((host, port))
            return ["10.20.30.40"]

        with mock.patch.object(
            browser_tier_module, "validate_public_url", side_effect=AssertionError("wrapper DNS preflight")
        ) as wrapper_validation:
            with mock.patch.object(socket, "create_connection", side_effect=AssertionError("private connect")) as connect:
                with mock.patch.object(
                    browser_tier_module, "pinned_fetch", wraps=browser_tier_module.pinned_fetch
                ) as fetch:
                    result = browser_tier_module.BrowserTier(resolver=resolver).fetch(url)

        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        wrapper_validation.assert_not_called()
        fetch.assert_called_once_with(url, resolver=resolver, max_redirects=0)
        self.assertEqual(resolver_calls, [("private-dns.example.test", 443)])
        connect.assert_not_called()

    def test_browser_http_and_js_paths_block_private_dns_with_injected_resolver(self):
        url = "https://private-dns.example.test/page"
        transport_calls = []
        browser_calls = []
        resolver = lambda host, port, **kwargs: ["172.16.0.4"]

        def transport(target):
            transport_calls.append(target)
            return {"status": 200, "body": "public article content"}

        def browser(target, *, request_gate):
            browser_calls.append(target)
            request_gate(target)
            return {"status": 200, "body": "rendered content", "url": target}

        http_result = browser_tier_module.BrowserTier(transport=transport, resolver=resolver).fetch(url)
        js_result = render_js(url, browser, resolver=resolver)

        self.assertEqual(http_result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(js_result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(transport_calls, [])
        self.assertEqual(browser_calls, [])

    def test_browser_redirect_to_dns_private_host_is_blocked_before_second_fetch(self):
        start = "https://public.example.test/start"
        redirect = "https://private.example.test/secret"
        calls = []

        def transport(url):
            calls.append(url)
            if url == start:
                return {"status": 302, "headers": {"Location": redirect}}
            return {"status": 200, "body": "private"}

        def lookup(host, port, **kwargs):
            return ["10.8.0.9" if host == "private.example.test" else "93.184.216.34"]

        result = browser_tier_module.BrowserTier(transport=transport, resolver=lookup).fetch(start)

        self.assertEqual(result, {"ok": False, "error": REDIRECT_BLOCKED})
        self.assertEqual(calls, [start])

    def test_browser_gate_exposes_the_verified_connection_addresses(self):
        url = "https://browser.example.test/page"
        gated = []

        def browser(target, *, request_gate):
            pinned_target = request_gate(target)
            gated.append((str(pinned_target), pinned_target.addresses))
            return {"status": 200, "body": "rendered content", "url": target}

        result = render_js(
            url,
            browser,
            resolver=lambda host, port, **kwargs: ["93.184.216.34"],
        )

        self.assertTrue(result["ok"])
        self.assertIn((url, ("93.184.216.34",)), gated)

    def test_browser_pinning_transport_receives_verified_addresses(self):
        url = "https://transport.example.test/page"
        calls = []

        class PinAwareTransport:
            def fetch_pinned(self, target, *, pinned_addresses):
                calls.append((target, pinned_addresses))
                return {"status": 200, "body": "public article content"}

        result = browser_tier_module.BrowserTier(
            transport=PinAwareTransport(),
            resolver=lambda host, port, **kwargs: ["93.184.216.34"],
        ).fetch(url)

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [(url, ("93.184.216.34",))])

    def test_crawl_skips_same_origin_link_that_resolves_private(self):
        start = "https://crawl.example.test/start"
        secret = "https://crawl.example.test/secret"
        calls = []
        lookups = 0

        def transport(url):
            calls.append(url)
            if url.endswith("/sitemap.xml"):
                return {"status": 404, "body": ""}
            if url == start:
                return {"status": 200, "body": '<a href="/secret">secret</a>'}
            return {"status": 200, "body": "must not be fetched"}

        def lookup(host, port, **kwargs):
            nonlocal lookups
            lookups += 1
            address = "93.184.216.34" if lookups <= 2 else "10.20.30.40"
            return [address]

        result = crawl_pro(start, transport, respect_robots=False, resolver=lookup)

        self.assertTrue(result["ok"])
        self.assertNotIn(secret, calls)
        self.assertNotIn(secret, [page["url"] for page in result["pages"]])
        self.assertEqual(calls, ["https://crawl.example.test/sitemap.xml", start])

    def test_crawl_dns_private_redirect_blocked_before_second_fetch(self):
        start = "https://crawl.example.test/start"
        calls = []
        lookups = 0

        def transport(url):
            calls.append(url)
            if url.endswith("/sitemap.xml"):
                return {"status": 404, "body": ""}
            return {"status": 302, "headers": {"Location": "/private"}}

        def lookup(host, port, **kwargs):
            nonlocal lookups
            lookups += 1
            address = "93.184.216.34" if lookups <= 2 else "10.20.30.40"
            return [address]

        with self.assertRaisesRegex(ValueError, "not publicly fetchable"):
            crawl_pro(start, transport, respect_robots=False, resolver=lookup)

        self.assertEqual(calls, ["https://crawl.example.test/sitemap.xml", start])

    def test_crawl_redirect_to_private_target_never_fetches_it(self):
        start = "https://crawl.example.test/start"
        private = "https://10.0.0.7/private"
        calls = []

        def transport(url):
            calls.append(url)
            if url.endswith("/sitemap.xml"):
                return {"status": 404, "body": ""}
            return {"status": 302, "headers": {"Location": private}}

        with self.assertRaisesRegex(ValueError, "outside the starting origin"):
            crawl_pro(
                start,
                transport,
                respect_robots=False,
                resolver=lambda host, port, **kwargs: ["93.184.216.34"],
            )

        self.assertEqual(calls, ["https://crawl.example.test/sitemap.xml", start])

    def test_crawl_default_transport_uses_pinned_fetch_per_hop(self):
        start = "https://crawl.example.test/start"
        calls = []
        resolver = lambda host, port, **kwargs: ["93.184.216.34"]

        def fake_pinned_fetch(url, *, resolver, max_redirects):
            calls.append((url, resolver, max_redirects))
            status = 404 if url.endswith("/sitemap.xml") else 200
            return {"status": status, "body": "article", "headers": {}, "url": url}

        with mock.patch.object(crawl_pro_module, "pinned_fetch", side_effect=fake_pinned_fetch):
            result = crawl_pro(start, respect_robots=False, resolver=resolver)

        self.assertTrue(result["ok"])
        self.assertEqual(
            [item[0] for item in calls],
            ["https://crawl.example.test/sitemap.xml", start],
        )
        self.assertTrue(all(item[1] is resolver and item[2] == 0 for item in calls))

    def test_crawl_pinning_transport_receives_verified_addresses(self):
        start = "https://crawl.example.test/start"
        calls = []

        class PinAwareTransport:
            def fetch_pinned(self, url, *, pinned_addresses):
                calls.append((url, pinned_addresses))
                if url.endswith("/sitemap.xml"):
                    return {"status": 404, "body": ""}
                return {"status": 200, "body": "article"}

        result = crawl_pro(
            start,
            PinAwareTransport(),
            respect_robots=False,
            resolver=lambda host, port, **kwargs: ["93.184.216.34"],
        )

        self.assertTrue(result["ok"])
        self.assertEqual(calls, [
            ("https://crawl.example.test/sitemap.xml", ("93.184.216.34",)),
            (start, ("93.184.216.34",)),
        ])

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

        result = render_js(
            "https://public.example.test/page", bypass,
            resolver=lambda host, port, **kwargs: ["93.184.216.34"],
        )

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
        resolver = lambda host, port, **kwargs: ["93.184.216.34"]
        client = FirecrawlClient("key", transport, resolver=resolver)
        target = "https://public.example.test/article"

        result = client._post(SCRAPE_ENDPOINT, target, {"url": "https://127.0.0.1/private"})

        self.assertTrue(result["ok"])
        self.assertEqual(transport.calls[0][1]["json"]["url"], target)

    def test_tavily_fake_transport_does_not_trigger_system_dns(self):
        transport = CallLog()
        client = TavilyClient(api_key="key", transport=transport)

        with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("unexpected DNS")):
            result = client.extract("https://example.test/article")

        self.assertTrue(result["ok"])
        self.assertEqual(transport.calls[0][0], ("https://api.tavily.com/extract",))

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
