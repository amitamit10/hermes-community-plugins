"""Retrieval-boundary contract tests (offline, fakes only)."""

import json
import socket
import unittest
from unittest import mock
from urllib.parse import urlencode

from browser_tier import (
    BrowserTier,
    WAYBACK_AVAILABLE,
    cloudflare_bypass,
    js_render,
    recover_blocked_page,
    render_js,
)
from native_tier import NativeTier, native_extract, native_search


PUBLIC_RESOLVER = lambda host, port, **kwargs: ["93.184.216.34"]  # noqa: E731
PUBLIC_CODES = frozenset(("URL_BLOCKED", "REDIRECT_BLOCKED", "MISSING_CONFIG"))


class FakeSearch:
    def __init__(self, response=None, error=None):
        self.response = error if error is not None else response
        self.calls = []

    def __call__(self, query, *, limit):
        self.calls.append((query, limit))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeExtract:
    def __init__(self, response=None, error=None):
        self.response = error if error is not None else response
        self.calls = []

    def __call__(self, *, urls, char_limit):
        self.calls.append((list(urls), char_limit))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeTransport:
    def __init__(self, routes=None, default=None):
        self.routes = dict(routes or {})
        self.default = default if default is not None else {"status": 404, "body": "not found"}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        value = self.routes.get(url, self.default)
        if isinstance(value, Exception):
            raise value
        return value(url) if callable(value) else value


class FakeBrowser:
    def __init__(self, *, body="<html>rendered page content</html>", final_url=None, action=None):
        self.body = body
        self.final_url = final_url
        self.action = action
        self.calls = []

    def __call__(self, url, *, request_gate):
        self.calls.append(url)
        if self.action is not None:
            return self.action(url, request_gate)
        request_gate(url)
        return {
            "status": 200,
            "body": self.body,
            "url": self.final_url or url,
            "requests": [url],
        }


def assert_nested_error(testcase, result, expected):
    testcase.assertIsInstance(result, dict)
    testcase.assertIs(result.get("ok"), False)
    testcase.assertEqual(result.get("error"), {"code": expected})
    testcase.assertIn(expected, PUBLIC_CODES)


class RetrievalContractTests(unittest.TestCase):
    def setUp(self):
        self._dns = mock.patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("unexpected DNS")
        )
        self._conn = mock.patch.object(
            socket, "create_connection", side_effect=AssertionError("unexpected connect")
        )
        self._dns.start()
        self._conn.start()
        self.addCleanup(self._dns.stop)
        self.addCleanup(self._conn.stop)

    def test_native_entrypoints_nested_errors(self):
        # Invalid / private starts -> exact nested URL_BLOCKED.
        invalid_cases = [
            ("native_search_empty", lambda: native_search("  ", web_search=FakeSearch({"data": {"web": []}}))),
            ("NativeTier.search_empty", lambda: NativeTier(web_search=FakeSearch({"data": {"web": []}})).search("  ")),
            ("native_extract_http", lambda: native_extract("http://example.com/", web_extract=FakeExtract({"results": []}))),
            ("native_extract_private", lambda: native_extract("https://127.0.0.1/private", web_extract=FakeExtract({"results": []}))),
            ("NativeTier.extract_private", lambda: NativeTier(web_extract=FakeExtract({"results": []})).extract("https://127.0.0.1/private")),
        ]
        for name, call in invalid_cases:
            with self.subTest(entrypoint=name):
                assert_nested_error(self, call(), "URL_BLOCKED")

        # Explicitly blocked redirect target -> exact nested REDIRECT_BLOCKED.
        redirect_cases = [
            ("native_extract_changed_private", lambda: NativeTier(
                web_extract=FakeExtract({"results": [{"url": "https://127.0.0.1/private", "content": "x"}]})
            ).extract("https://example.test/page")),
        ]
        for name, call in redirect_cases:
            with self.subTest(entrypoint=name):
                assert_nested_error(self, call(), "REDIRECT_BLOCKED")

        # Missing callables -> nested MISSING_CONFIG.
        with self.subTest(entrypoint="native_search_missing"):
            assert_nested_error(self, native_search("topic"), "MISSING_CONFIG")
        with self.subTest(entrypoint="native_extract_missing"):
            assert_nested_error(self, native_extract("https://example.test/page"), "MISSING_CONFIG")
        with self.subTest(entrypoint="NativeTier.search_missing"):
            assert_nested_error(self, NativeTier().search("topic"), "MISSING_CONFIG")
        with self.subTest(entrypoint="NativeTier.extract_missing"):
            assert_nested_error(self, NativeTier().extract("https://example.test/page"), "MISSING_CONFIG")

        # Nested upstream REDIRECT_BLOCKED must not degrade to URL_BLOCKED.
        nested = {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}
        upstream_cases = [
            ("native_search_nested", lambda: native_search("topic", web_search=FakeSearch(nested))),
            ("NativeTier.search_nested", lambda: NativeTier(web_search=FakeSearch(nested)).search("topic")),
            ("native_extract_nested", lambda: native_extract(
                "https://example.test/page", web_extract=FakeExtract(nested))),
            ("NativeTier.extract_nested", lambda: NativeTier(web_extract=FakeExtract(nested)).extract(
                "https://example.test/page")),
        ]
        for name, call in upstream_cases:
            with self.subTest(entrypoint=name):
                assert_nested_error(self, call(), "REDIRECT_BLOCKED")

    def test_browser_entrypoints_nested_errors(self):
        bad_start = "http://example.com/"
        private_start = "https://127.0.0.1/private"
        redirect_transport = FakeTransport({
            "https://example.com/start": {"status": 302, "headers": {"Location": "http://127.0.0.1/admin"}},
        })

        def private_redirect_action(url, request_gate):
            request_gate("http://127.0.0.1/private", redirect_from=url, redirect_hops=0)
            return {"status": 200, "body": "unreachable", "url": url}

        # Invalid / private starts -> exact nested URL_BLOCKED for every entrypoint.
        for name, call in [
            ("BrowserTier.fetch_bad", lambda: BrowserTier(transport=FakeTransport()).fetch(bad_start)),
            ("BrowserTier.fetch_private", lambda: BrowserTier(transport=FakeTransport()).fetch(private_start)),
            ("BrowserTier.render_js_bad", lambda: BrowserTier(browser_callable=FakeBrowser(), resolver=PUBLIC_RESOLVER).render_js(bad_start)),
            ("render_js_bad", lambda: render_js(bad_start, FakeBrowser(), resolver=PUBLIC_RESOLVER)),
            ("js_render_bad", lambda: js_render(bad_start, FakeBrowser(), resolver=PUBLIC_RESOLVER)),
            ("BrowserTier.cloudflare_bad", lambda: BrowserTier(transport=FakeTransport(), cloudflare_callable=FakeBrowser()).cloudflare_bypass(bad_start)),
            ("cloudflare_bypass_bad", lambda: cloudflare_bypass(bad_start, FakeTransport(), FakeBrowser(), resolver=PUBLIC_RESOLVER)),
            ("BrowserTier.recover_bad", lambda: BrowserTier(transport=FakeTransport(), browser_callable=FakeBrowser()).recover(bad_start)),
            ("BrowserTier.recover_blocked_page_bad", lambda: BrowserTier(transport=FakeTransport()).recover_blocked_page(bad_start)),
            ("recover_blocked_page_bad", lambda: recover_blocked_page(bad_start, transport=FakeTransport())),
        ]:
            with self.subTest(entrypoint=name):
                assert_nested_error(self, call(), "URL_BLOCKED")

        # Explicitly blocked redirects -> exact nested REDIRECT_BLOCKED.
        for name, call in [
            ("BrowserTier.fetch_redirect", lambda: BrowserTier(transport=redirect_transport).fetch("https://example.com/start")),
            ("render_js_redirect", lambda: render_js(
                "https://example.com/app", FakeBrowser(action=private_redirect_action), resolver=PUBLIC_RESOLVER)),
            ("js_render_redirect", lambda: js_render(
                "https://example.com/app", FakeBrowser(action=private_redirect_action), resolver=PUBLIC_RESOLVER)),
            ("BrowserTier.render_js_redirect", lambda: BrowserTier(
                browser_callable=FakeBrowser(action=private_redirect_action), resolver=PUBLIC_RESOLVER).render_js("https://example.com/app")),
        ]:
            with self.subTest(entrypoint=name):
                assert_nested_error(self, call(), "REDIRECT_BLOCKED")

        # Recover ending in browser redirect failure -> REDIRECT_BLOCKED.
        def recover_redirect_browser(url, request_gate):
            request_gate(url)
            return {"status": 200, "body": "content", "url": "https://other.example/landing"}

        for name, call in [
            ("BrowserTier.recover_browser_redirect", lambda: BrowserTier(
                transport=FakeTransport({"https://example.com/app": {"status": 403, "body": "forbidden"}}),
                browser_callable=FakeBrowser(action=recover_redirect_browser),
                archive_domains=(),
                resolver=PUBLIC_RESOLVER,
            ).recover("https://example.com/app")),
            ("recover_blocked_page_browser_redirect", lambda: recover_blocked_page(
                "https://example.com/app",
                transport=FakeTransport({"https://example.com/app": {"status": 403, "body": "forbidden"}}),
                browser_callable=FakeBrowser(action=recover_redirect_browser),
                archive_domains=(),
                resolver=PUBLIC_RESOLVER,
            )),
            ("BrowserTier.recover_alias_redirect", lambda: BrowserTier(
                transport=FakeTransport({"https://example.com/app": {"status": 403, "body": "forbidden"}}),
                browser_callable=FakeBrowser(action=recover_redirect_browser),
                archive_domains=(),
                resolver=PUBLIC_RESOLVER,
            ).recover_blocked_page("https://example.com/app")),
        ]:
            with self.subTest(entrypoint=name):
                assert_nested_error(self, call(), "REDIRECT_BLOCKED")

        # Nested upstream REDIRECT_BLOCKED must not degrade.
        def nested_browser(url, *, request_gate):
            request_gate(url)
            return {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}

        for name, call in [
            ("render_js_nested", lambda: render_js("https://example.com/app", nested_browser, resolver=PUBLIC_RESOLVER)),
            ("js_render_nested", lambda: js_render("https://example.com/app", nested_browser, resolver=PUBLIC_RESOLVER)),
            ("BrowserTier.render_js_nested", lambda: BrowserTier(
                browser_callable=nested_browser, resolver=PUBLIC_RESOLVER).render_js("https://example.com/app")),
        ]:
            with self.subTest(entrypoint=name):
                assert_nested_error(self, call(), "REDIRECT_BLOCKED")

    def test_success_regressions_preserve_bounded_fields(self):
        # Native search success preserves results/truncated.
        search = FakeSearch({"data": {"web": [{
            "title": "Offline result",
            "url": "https://example.test/",
            "description": "Fixture",
        }]}})
        for name, result in [
            ("native_search", native_search("topic", web_search=search)),
            ("NativeTier.search", NativeTier(web_search=FakeSearch({"data": {"web": [{
                "title": "Offline result", "url": "https://example.test/", "description": "Fixture"}]}})).search("topic")),
        ]:
            with self.subTest(entrypoint=name):
                self.assertIs(result.get("ok"), True)
                self.assertEqual(result["results"], [{
                    "title": "Offline result", "url": "https://example.test/", "snippet": "Fixture"}])
                self.assertIn("truncated", result)
                self.assertIsInstance(result["truncated"], bool)

        # Native extract success preserves url/content/truncated.
        url = "https://example.test/page"
        for name, result in [
            ("native_extract", native_extract(url, web_extract=FakeExtract(
                {"results": [{"url": url, "content": "Readable text"}]}))),
            ("NativeTier.extract", NativeTier(web_extract=FakeExtract(
                {"results": [{"url": url, "content": "Readable text"}]})).extract(url)),
        ]:
            with self.subTest(entrypoint=name):
                self.assertIs(result.get("ok"), True)
                self.assertEqual(result["url"], url)
                self.assertEqual(result["content"], "Readable text")
                self.assertIs(result["truncated"], False)

        # Browser fetch success preserves url/content/source/truncated.
        fetch_url = "https://example.test/article"
        fetch_result = BrowserTier(
            transport=FakeTransport({fetch_url: {"status": 200, "body": "public article content"}})
        ).fetch(fetch_url)
        self.assertIs(fetch_result.get("ok"), True)
        self.assertEqual(fetch_result["url"], fetch_url)
        self.assertEqual(fetch_result["content"], "public article content")
        self.assertEqual(fetch_result["source"], "transport")
        self.assertIn("truncated", fetch_result)

        # JS render success preserves url/source.
        browser = FakeBrowser()
        for name, result in [
            ("render_js", render_js("https://example.com/app", browser, resolver=PUBLIC_RESOLVER)),
            ("js_render", js_render("https://example.com/app", FakeBrowser(), resolver=PUBLIC_RESOLVER)),
            ("BrowserTier.render_js", BrowserTier(
                browser_callable=FakeBrowser(), resolver=PUBLIC_RESOLVER).render_js("https://example.com/app")),
        ]:
            with self.subTest(entrypoint=name):
                self.assertIs(result.get("ok"), True)
                self.assertEqual(result["source"], "browser_js")
                self.assertEqual(result["url"], "https://example.com/app")

        # Cloudflare bypass success preserves source.
        start = "https://example.com/article"
        cf_transport = FakeTransport({start: {"status": 403, "body": "<title>Just a moment...</title>"}})
        cf_browser = FakeBrowser(body="<html>article rendered after challenge</html>")
        for name, result in [
            ("cloudflare_bypass", cloudflare_bypass(start, cf_transport, cf_browser, resolver=PUBLIC_RESOLVER)),
            ("BrowserTier.cloudflare_bypass", BrowserTier(
                transport=FakeTransport({start: {"status": 403, "body": "<title>Just a moment...</title>"}}),
                cloudflare_callable=FakeBrowser(body="<html>article rendered after challenge</html>"),
                resolver=PUBLIC_RESOLVER).cloudflare_bypass(start)),
        ]:
            with self.subTest(entrypoint=name):
                self.assertIs(result.get("ok"), True)
                self.assertEqual(result["source"], "cloudflare_bypass")

        # Recovery preserves snapshot_date/source/url on existing wayback fixture.
        article = "https://example.com/article"
        lookup = WAYBACK_AVAILABLE + "?" + urlencode({"url": article})
        snapshot_url = "https://web.archive.org/web/20260102030405/https://example.com/article"
        page = "<html><title>Archived article</title><body>Saved public article text with enough content.</body></html>"
        snapshot_transport = FakeTransport({
            article: {"status": 403, "body": "origin blocked"},
            lookup: {"status": 200, "body": json.dumps({"archived_snapshots": {"closest": {
                "url": snapshot_url, "timestamp": "20260102030405"}}})},
            snapshot_url: {"status": 200, "body": page},
        })
        snapshot_result = BrowserTier(transport=snapshot_transport, archive_domains=()).recover(article)
        self.assertIs(snapshot_result.get("ok"), True)
        self.assertEqual(snapshot_result["source"], "snapshot")
        self.assertEqual(snapshot_result["snapshot_date"], "20260102030405")
        self.assertEqual(snapshot_result["url"], snapshot_url)

        # Recovery direct/api/browser successes preserve url/source.
        direct = BrowserTier(
            transport=FakeTransport({article: {"status": 200, "body": "article content"}})
        ).recover(article)
        self.assertIs(direct.get("ok"), True)
        self.assertEqual(direct["source"], "transport")


if __name__ == "__main__":
    unittest.main()
