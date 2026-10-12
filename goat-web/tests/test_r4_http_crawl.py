"""R4 Cycle C: crawl fail-consistency with extract; never follow links from failed page."""

import importlib
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import test_plugin_wiring as _wiring  # noqa: E402

CHALLENGE_HTML = (
    "<html><head><title>Just a moment...</title></head><body>"
    '<form id="challenge-form" action="/challenge?token=synX" method="post">'
    '<div class="anomaly-modal__form"><button type="submit">Verify</button></div>'
    "</form></body></html>"
)

ORDINARY_404_HTML = (
    "<html><head><title>Not Found</title></head><body><p>gone</p></body></html>"
)

ROOT_HTML = (
    "<html><head><title>Home</title></head><body>"
    "<main><p>Home page text.</p>"
    '<a href="/child">child</a></main></body></html>'
)

FAILED_CHILD_WITH_LINKS = (
    "<html><head><title>Not Found</title></head><body><p>gone</p>"
    '<a href="/grandchild">grandchild</a></body></html>'
)

FAILED_CHALLENGE_WITH_LINKS = (
    "<html><head><title>Just a moment...</title></head><body>"
    '<form id="challenge-form" action="/c?token=synY" method="post">'
    '<div class="anomaly-modal__form"><button type="submit">V</button></div>'
    "</form>"
    '<a href="/grandchild">grandchild</a></body></html>'
)

CHILD_HTML = (
    "<html><head><title>Child</title></head><body>"
    "<main><p>Child page text.</p></main></body></html>"
)


class OfflineRecordingTestCase(unittest.TestCase):
    RESOLVER_NAMES = ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo", "create_connection")
    TCP_NAMES = ("connect", "connect_ex", "sendto", "sendmsg")

    def setUp(self):
        super().setUp()
        self.network_attempts = []
        self._saved_socket = {n: getattr(socket, n) for n in self.RESOLVER_NAMES}
        for name in self.RESOLVER_NAMES:
            setattr(socket, name, self._deny(name))
        self._saved_sock_methods = {}
        for name in self.TCP_NAMES:
            if hasattr(socket.socket, name):
                self._saved_sock_methods[name] = getattr(socket.socket, name)
                setattr(socket.socket, name, self._deny("socket." + name))
        self.addCleanup(self._restore_and_assert_no_network)

    def _deny(self, name):
        def _denied(*a, **k):
            self.network_attempts.append((name, a, k))
            raise AssertionError("network disabled: %s" % name)
        return _denied

    def _restore_and_assert_no_network(self):
        for name, fn in self._saved_socket.items():
            setattr(socket, name, fn)
        for name, fn in self._saved_sock_methods.items():
            setattr(socket.socket, name, fn)
        self.assertEqual(self.network_attempts, [])

    def assertNoNetwork(self):
        self.assertEqual(self.network_attempts, [])


class CrawlFailConsistencyTests(OfflineRecordingTestCase):
    def test_crawl_failures_match_extract_and_never_follow_failed_page(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_crawl"]["handler"]
        root = "https://example.com/"
        child = "https://example.com/child"
        grandchild = "https://example.com/grandchild"
        # --- root challenge403 -> PROVIDER_BLOCKED, calls root only ---
        for run in ("raw", "json"):
            calls = []
            def _t(u, _c=calls):
                _c.append(u)
                return {"status": 403, "body": CHALLENGE_HTML}
            if run == "raw":
                res = goat_tools.goat_crawl(root, transport=_t)
                self.assertEqual(res, {"error": {"code": "PROVIDER_BLOCKED"}})
            else:
                with mock.patch.object(goat_tools, "pinned_fetch", _t):
                    res = json.loads(handler({"url": root}))
                self.assertEqual(res, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}})
            self.assertEqual(calls, [root])
        # --- root ordinary404 -> HTTP_ERROR+404, calls root only ---
        for run in ("raw", "json"):
            calls = []
            def _t2(u, _c=calls):
                _c.append(u)
                return {"status": 404, "body": ORDINARY_404_HTML}
            if run == "raw":
                res = goat_tools.goat_crawl(root, transport=_t2)
                self.assertEqual(res.get("error"), {"code": "HTTP_ERROR"})
                self.assertIs(type(res.get("status")), int)
                self.assertEqual(res.get("status"), 404)
            else:
                with mock.patch.object(goat_tools, "pinned_fetch", _t2):
                    res = json.loads(handler({"url": root}))
                self.assertFalse(res.get("ok"))
                self.assertEqual(res.get("error"), {"code": "HTTP_ERROR"})
                self.assertEqual(res.get("status"), 404)
            self.assertEqual(calls, [root])
        # --- root ok, child 404-with-links -> HTTP_ERROR, never grandchild ---
        for child_body, code in ((FAILED_CHILD_WITH_LINKS, "HTTP_ERROR"), (FAILED_CHALLENGE_WITH_LINKS, "PROVIDER_BLOCKED")):
            with self.subTest(child_code=code):
                for run in ("raw", "json"):
                    calls = []
                    def _t3(u, _c=calls, _b=child_body):
                        _c.append(u)
                        if u == root:
                            return {"status": 200, "body": ROOT_HTML}
                        if u == child:
                            st = 404 if _b is FAILED_CHILD_WITH_LINKS else 403
                            return {"status": st, "body": _b}
                        raise AssertionError("must never fetch " + u)
                    if run == "raw":
                        res = goat_tools.goat_crawl(root, transport=_t3)
                    else:
                        with mock.patch.object(goat_tools, "pinned_fetch", _t3):
                            res = json.loads(handler({"url": root}))
                    if code == "HTTP_ERROR":
                        self.assertEqual(res.get("error"), {"code": "HTTP_ERROR"})
                        self.assertEqual(res.get("status"), 404)
                        if run == "json":
                            self.assertFalse(res.get("ok"))
                    else:
                        if run == "raw":
                            self.assertEqual(res, {"error": {"code": "PROVIDER_BLOCKED"}})
                        else:
                            self.assertEqual(res, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}})
                    self.assertEqual(calls, [root, child])
                    self.assertNotIn(grandchild, calls)
        # --- successful crawl still BFS bounded ---
        def _ok(u):
            if u == root:
                return {"status": 200, "body": ROOT_HTML}
            if u == child:
                return {"status": 200, "body": CHILD_HTML}
            raise AssertionError("unexpected " + u)
        ok = goat_tools.goat_crawl(root, transport=_ok)
        self.assertEqual([p["url"] for p in ok["pages"]], [root, child])
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
