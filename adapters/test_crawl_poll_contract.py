"""Crawl + single-shot RSS poll boundary tests (offline, fakes only)."""

import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawl_pro import crawl_pro
from rss_watcher import MAX_FEED_BYTES, RSSWatcher, parse_feed


BASE = "https://example.test"
PUBLIC_RESOLVER = lambda host, port, **kwargs: ["93.184.216.34"]  # noqa: E731
PUBLIC_CODES = frozenset(("URL_BLOCKED", "REDIRECT_BLOCKED"))


class FakeTransport:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.responses.get(url, {"status": 404, "body": ""})


def html_links(*paths):
    return "".join(f'<a href="{path}">link</a>' for path in paths)


FEED_AB = """<rss version="2.0"><channel>
<item><guid>a</guid><title>Alpha</title><link>https://example.test/a</link></item>
<item><guid>b</guid><title>Beta</title><link>https://example.test/b</link></item>
</channel></rss>"""


def assert_url_blocked(testcase, result):
    testcase.assertIsInstance(result, dict)
    testcase.assertIs(result.get("ok"), False)
    testcase.assertEqual(result.get("error"), {"code": "URL_BLOCKED"})


def assert_redirect_blocked(testcase, result):
    testcase.assertIsInstance(result, dict)
    testcase.assertIs(result.get("ok"), False)
    testcase.assertEqual(result.get("error"), {"code": "REDIRECT_BLOCKED"})


class CrawlPollContractTests(unittest.TestCase):
    def setUp(self):
        self._dns = mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("no DNS"))
        self._conn = mock.patch.object(socket, "create_connection", side_effect=AssertionError("no connect"))
        self._dns.start()
        self._conn.start()
        self.addCleanup(self._dns.stop)
        self.addCleanup(self._conn.stop)

    def test_crawl_success_regression_preserves_payload(self):
        start = f"{BASE}/start"
        transport = FakeTransport({start: {"status": 200, "body": "article"}})
        result = crawl_pro(start, transport, respect_robots=False)
        self.assertIs(result.get("ok"), True)
        self.assertEqual([page["url"] for page in result["pages"]], [start])
        self.assertIn("truncated", result)
        self.assertIn("requests_by_host", result)
        self.assertEqual(result["requests_by_host"], {"example.test": len(transport.calls)})

    def test_crawl_invalid_starts_return_url_blocked_without_transport(self):
        for respect in (False, True):
            for start in ["", "not-a-url", "file:///etc/passwd", "http://example.com/", "https://127.0.0.1/private", "https://[::1]/x"]:
                with self.subTest(start=start, respect_robots=respect):
                    transport = FakeTransport({})
                    result = crawl_pro(start, transport, respect_robots=respect)
                    assert_url_blocked(self, result)
                    self.assertEqual(transport.calls, [])

    def test_crawl_redirects_return_redirect_blocked(self):
        start = f"{BASE}/start"
        cases = [
            ("unsafe-scheme", {"status": 302, "headers": {"Location": "http://127.0.0.1/admin"}}),
            ("cross-origin", {"status": 302, "headers": {"Location": "https://other.test/nope"}}),
            ("hidden", {"status": 200, "url": "https://other.test/hidden", "body": "x"}),
        ]
        for name, route in cases:
            with self.subTest(redirect=name):
                transport = FakeTransport({start: route})
                result = crawl_pro(start, transport, respect_robots=False, resolver=PUBLIC_RESOLVER)
                assert_redirect_blocked(self, result)
                self.assertNotIn("https://other.test/hidden", transport.calls)
        # Over-limit: three hops exceeds MAX_REDIRECTS=2.
        transport = FakeTransport({
            f"{BASE}/0": {"status": 302, "headers": {"Location": "/1"}},
            f"{BASE}/1": {"status": 302, "headers": {"Location": "/2"}},
            f"{BASE}/2": {"status": 302, "headers": {"Location": "/3"}},
        })
        result = crawl_pro(f"{BASE}/0", transport, respect_robots=False, resolver=PUBLIC_RESOLVER)
        assert_redirect_blocked(self, result)
        # DNS-private AFTER redirect (same origin): safe start fetched, private target never fetched.
        resolutions = []
        def lookup(host, port, **kwargs):
            resolutions.append(host)
            if len(resolutions) <= 2:
                return ["93.184.216.34"]
            return ["10.8.0.9"]
        transport = FakeTransport({start: {"status": 302, "headers": {"Location": "/private"}}})
        result = crawl_pro(start, transport, respect_robots=False, resolver=lookup)
        assert_redirect_blocked(self, result)
        self.assertEqual(transport.calls, [f"{BASE}/sitemap.xml", start])

    def test_crawl_transport_raises_maps_url_blocked(self):
        def boom(url):
            raise RuntimeError("secret-transport-detail")
        result = crawl_pro(f"{BASE}/start", boom, respect_robots=False)
        assert_url_blocked(self, result)
        self.assertNotIn("secret-transport-detail", repr(result))

    def test_rss_poll_success_normalizes_items(self):
        transport = FakeTransport({f"{BASE}/feed": {"status": 200, "body": FEED_AB}})
        watcher = RSSWatcher(transport)
        result = watcher.poll(f"{BASE}/feed")
        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), True)
        items = result.get("items")
        self.assertEqual([item["id"] for item in items], ["a", "b"])
        for item in items:
            for key in ("id", "title", "url", "summary", "published"):
                self.assertIn(key, item)
        self.assertEqual(items[0]["title"], "Alpha")
        # Dedup watermark preserved: second poll sees nothing new.
        second = watcher.poll(f"{BASE}/feed")
        self.assertIs(second.get("ok"), True)
        self.assertEqual(second.get("items"), [])
        # Single-shot temp dirs live under TMPDIR.
        tmpdir = os.environ.get("TMPDIR", tempfile.gettempdir())
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(str(Path(directory).resolve()).startswith(str(Path(tmpdir).resolve())))

    def test_rss_poll_errors_normalize_url_blocked(self):
        cases = [
            ("empty-url", "   ", {"status": 200, "body": FEED_AB}),
            ("http-status", f"{BASE}/feed", {"status": 503, "body": FEED_AB}),
            ("oversized", f"{BASE}/feed", {"status": 200, "body": "x" * (MAX_FEED_BYTES + 1)}),
            ("malformed", f"{BASE}/feed", {"status": 200, "body": "<rss><bad"}),
        ]
        for name, url, response in cases:
            with self.subTest(error=name):
                watcher = RSSWatcher(FakeTransport({url: response}))
                result = watcher.poll(url)
                assert_url_blocked(self, result)
                self.assertEqual(watcher.seen_ids, ())

        def boom(url):
            raise RuntimeError("secret-fetch-detail")
        result = RSSWatcher(boom).poll(f"{BASE}/feed")
        assert_url_blocked(self, result)
        self.assertNotIn("secret-fetch-detail", repr(result))

        class RedirectErr(Exception):
            code = "REDIRECT_BLOCKED"
        def red(url):
            raise RedirectErr("red")
        result = RSSWatcher(red).poll(f"{BASE}/feed")
        self.assertIsInstance(result, dict)
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("error"), {"code": "REDIRECT_BLOCKED"})

    def test_rss_raw_apis_remain_unchanged(self):
        items = parse_feed(FEED_AB.encode("utf-8"))
        self.assertIsInstance(items, list)
        self.assertEqual([item["id"] for item in items], ["a", "b"])
        watcher = RSSWatcher(FakeTransport({}))
        self.assertIsInstance(watcher.seen_ids, tuple)
        with self.assertRaises(TypeError):
            RSSWatcher(None)


if __name__ == "__main__":
    unittest.main()
