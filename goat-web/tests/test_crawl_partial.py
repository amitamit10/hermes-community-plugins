"""STAGE 1 RED: V5 crawl partial-progress regression (goat_crawl).

Root links to 2 same-origin children; child-1 is good HTML, child-2 is an
EMPTY body ("") with status 200. Current BFS returns an error-only shape
with NO pages key, discarding child-1's collected page. RED asserts the
collected page survives (partial progress) via the real function and the
real registered dispatch.

Strictly offline: socket resolution/connectors raise AssertionError at
import time and per-test; only deterministic fake transports are used.
Fixtures are all https://example.com/* (same-origin, SSRF semantics kept).
"""

import importlib
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

# --- module-level offline block: `python3 -B <this file>` alone is offline.
_BLOCKED_SOCKET_ATTRS = (
    "getaddrinfo",
    "gethostbyname",
    "gethostbyname_ex",
    "gethostbyaddr",
    "getnameinfo",
    "create_connection",
)
_BLOCKED_SOCK_METHODS = ("connect", "connect_ex", "sendto", "sendmsg")


def _offline_denied(name):
    def _denied(*args, **kwargs):
        raise AssertionError("network disabled: %s" % name)

    return _denied


for _name in _BLOCKED_SOCKET_ATTRS:
    try:
        setattr(socket, _name, _offline_denied(_name))
    except Exception:
        pass
for _mname in _BLOCKED_SOCK_METHODS:
    try:
        if hasattr(socket.socket, _mname):
            setattr(socket.socket, _mname, _offline_denied("socket." + _mname))
    except Exception:
        pass

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import test_plugin_wiring as _wiring  # noqa: E402

ROOT = "https://example.com/"
CHILD1 = "https://example.com/c1"
CHILD2 = "https://example.com/c2"

ROOT_HTML = (
    "<html><head><title>Root</title></head><body>"
    "<main><p>Root page text content here.</p>"
    '<a href="/c1">child one</a><a href="/c2">child two</a></main></body></html>'
)
CHILD1_HTML = (
    "<html><head><title>Child One</title></head><body>"
    "<main><p>Child one collected text content here.</p></main></body></html>"
)


def _partial_transport(url):
    if url == ROOT:
        return {"status": 200, "body": ROOT_HTML}
    if url == CHILD1:
        return {"status": 200, "body": CHILD1_HTML}
    if url == CHILD2:
        return {"status": 200, "body": ""}
    raise AssertionError("unexpected fetch " + url)


SINGLE = "https://example.com/start"
CHILD3 = "https://example.com/c3"
SAME_CHILD = "https://example.com/same"
XORIGIN_CHILD = "https://other.example/x"

CLEAN_CHILD2_HTML = (
    "<html><head><title>Child Two</title></head><body>"
    "<main><p>Child two collected text content here.</p></main></body></html>"
)


def _single_empty_transport(url):
    if url == SINGLE:
        return {"status": 200, "body": ""}
    raise AssertionError("unexpected fetch " + url)


def _clean_transport(url):
    if url == ROOT:
        return {"status": 200, "body": ROOT_HTML}
    if url == CHILD1:
        return {"status": 200, "body": CHILD1_HTML}
    if url == CHILD2:
        return {"status": 200, "body": CLEAN_CHILD2_HTML}
    raise AssertionError("unexpected fetch " + url)


def _capped_skip_transport(url):
    if url == ROOT:
        return {
            "status": 200,
            "body": (
                "<html><head><title>Root</title></head><body>"
                "<main><p>Root page text content here.</p>"
                '<a href="/c1">bad first</a><a href="/c2">good</a>'
                '<a href="/c3">extra</a></main></body></html>'
            ),
        }
    if url == CHILD1:
        return {"status": 200, "body": ""}
    if url == CHILD2:
        return {"status": 200, "body": CHILD1_HTML}
    if url == CHILD3:
        return {"status": 200, "body": CLEAN_CHILD2_HTML}
    raise AssertionError("unexpected fetch " + url)


class OfflineRecordingTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.network_attempts = []
        self._saved = {n: getattr(socket, n) for n in _BLOCKED_SOCKET_ATTRS}
        for name in _BLOCKED_SOCKET_ATTRS:
            setattr(socket, name, self._deny(name))
        self._saved_methods = {}
        for name in _BLOCKED_SOCK_METHODS:
            if hasattr(socket.socket, name):
                self._saved_methods[name] = getattr(socket.socket, name)
                setattr(socket.socket, name, self._deny("socket." + name))
        self.addCleanup(self._restore_and_assert_no_network)

    def _deny(self, name):
        def _denied(*a, **k):
            self.network_attempts.append((name, a, k))
            raise AssertionError("network disabled: %s" % name)

        return _denied

    def _restore_and_assert_no_network(self):
        for name, fn in self._saved.items():
            setattr(socket, name, fn)
        for name, fn in self._saved_methods.items():
            setattr(socket.socket, name, fn)
        self.assertEqual(self.network_attempts, [])

    def assertNoNetwork(self):
        self.assertEqual(self.network_attempts, [])


class CrawlPartialProgressTests(OfflineRecordingTestCase):
    def test_mid_bfs_empty_page_keeps_collected_pages(self):
        """RED: mid-BFS empty-body child must not discard child-1/root pages."""
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_crawl"]["handler"]
        # Real function path keeps depth/page limits and same-origin scope.
        raw = goat_tools.goat_crawl(
            ROOT, transport=_partial_transport, max_depth=1, max_pages=10
        )
        self.assertIn(
            "pages", raw, "mid-BFS empty page discarded collected pages: %r" % (raw,)
        )
        urls = [p["url"] for p in raw["pages"]]
        self.assertIn(ROOT, urls)
        self.assertIn(CHILD1, urls, "child-1 page lost: %r" % (raw,))
        # Real registered dispatch path preserves the same partial progress.
        with mock.patch.object(goat_tools, "pinned_fetch", _partial_transport):
            payload = json.loads(
                handler({"url": ROOT, "max_depth": 1, "max_pages": 10})
            )
        self.assertIn(
            "pages", payload, "dispatch discarded collected pages: %r" % (payload,)
        )
        durls = [p["url"] for p in payload["pages"]]
        self.assertIn(CHILD1, durls, "dispatch lost child-1: %r" % (payload,))
        self.assertNoNetwork()

    def test_single_empty_page_stays_error_only(self):
        """All-fail: single empty page keeps fail-closed error-only, no pages."""
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_crawl"]["handler"]
        raw = goat_tools.goat_crawl(
            SINGLE, transport=_single_empty_transport, max_depth=0, max_pages=1
        )
        self.assertNotIn("pages", raw)
        self.assertEqual(raw.get("error"), {"code": "HTTP_ERROR"})
        self.assertEqual(raw.get("status"), 200)
        with mock.patch.object(goat_tools, "pinned_fetch", _single_empty_transport):
            payload = json.loads(
                handler({"url": SINGLE, "max_depth": 0, "max_pages": 1})
            )
        self.assertFalse(payload.get("ok"))
        self.assertNotIn("pages", payload)
        self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
        self.assertEqual(payload.get("status"), 200)
        self.assertNoNetwork()

    def test_clean_crawl_has_no_skipped_key(self):
        """Clean crawls stay exactly {pages} with no skipped key."""
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_crawl"]["handler"]
        raw = goat_tools.goat_crawl(
            ROOT, transport=_clean_transport, max_depth=1, max_pages=10
        )
        self.assertEqual(set(raw), {"pages"})
        self.assertNotIn("skipped", raw)
        self.assertNotIn("error", raw)
        with mock.patch.object(goat_tools, "pinned_fetch", _clean_transport):
            payload = json.loads(
                handler({"url": ROOT, "max_depth": 1, "max_pages": 10})
            )
        self.assertTrue(payload.get("ok"))
        self.assertNotIn("skipped", payload)
        self.assertNotIn("error", payload)
        self.assertEqual(
            [p["url"] for p in payload["pages"]], [ROOT, CHILD1, CHILD2]
        )
        self.assertNoNetwork()

    def test_page_limit_caps_pages_with_skip_recorded(self):
        """max_pages still caps pages while the bad child is recorded skipped."""
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_crawl"]["handler"]
        raw = goat_tools.goat_crawl(
            ROOT, transport=_capped_skip_transport, max_depth=1, max_pages=2
        )
        self.assertIn("pages", raw)
        self.assertEqual(len(raw["pages"]), 2)
        self.assertIn("skipped", raw)
        self.assertTrue(raw["skipped"], "skip not recorded: %r" % (raw,))
        self.assertNotIn("error", raw)
        with mock.patch.object(goat_tools, "pinned_fetch", _capped_skip_transport):
            payload = json.loads(
                handler({"url": ROOT, "max_depth": 1, "max_pages": 2})
            )
        self.assertTrue(payload.get("ok"))
        self.assertEqual(len(payload["pages"]), 2)
        self.assertTrue(payload.get("skipped"))
        self.assertNotIn("error", payload)
        self.assertNoNetwork()

    def test_cross_origin_child_never_fetched(self):
        """Cross-origin links are never fetched; same-origin pages are kept."""
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_crawl"]["handler"]
        root_html = (
            "<html><head><title>Root</title></head><body>"
            "<main><p>Root page text content here.</p>"
            '<a href="/same">same</a>'
            '<a href="https://other.example/x">cross</a></main></body></html>'
        )
        same_html = (
            "<html><head><title>Same</title></head><body>"
            "<main><p>Same origin child text here.</p></main></body></html>"
        )
        calls = []

        def _transport(url):
            calls.append(url)
            if url == ROOT:
                return {"status": 200, "body": root_html}
            if url == SAME_CHILD:
                return {"status": 200, "body": same_html}
            raise AssertionError("must never fetch " + url)

        raw = goat_tools.goat_crawl(
            ROOT, transport=_transport, max_depth=1, max_pages=10
        )
        self.assertEqual(calls, [ROOT, SAME_CHILD])
        self.assertEqual([p["url"] for p in raw["pages"]], [ROOT, SAME_CHILD])
        with mock.patch.object(goat_tools, "pinned_fetch", _transport):
            payload = json.loads(
                handler({"url": ROOT, "max_depth": 1, "max_pages": 10})
            )
        self.assertEqual([p["url"] for p in payload["pages"]], [ROOT, SAME_CHILD])
        self.assertNotIn(XORIGIN_CHILD, calls)
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
