"""R4 Cycle D: 429 -> RATE_LIMITED extract/crawl raw+JSON; 503 stays HTTP_ERROR."""

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

CHALLENGE_429_HTML = (
    "<html><head><title>Just a moment...</title></head><body>"
    '<form id="challenge-form" action="/c?tok=r429" method="post">'
    '<div class="anomaly-modal__form"><button type="submit">V</button></div>'
    "</form></body></html>"
)

NORMAL_429_HTML = (
    "<html><head><title>Too Many Requests</title></head><body><p>slow down</p></body></html>"
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


class RateLimitedTests(OfflineRecordingTestCase):
    def test_extract_and_crawl_429_is_rate_limited_with_safe_retry_after(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        ex_handler = _wiring._registered_tools(mod)["goat_extract"]["handler"]
        crawl_handler = _wiring._registered_tools(mod)["goat_crawl"]["handler"]
        url = "https://example.com/article"
        root = "https://example.com/"
        # --- extract 429 normal + valid Retry-After -> RATE_LIMITED+retry_after, single call ---
        for body in (NORMAL_429_HTML, CHALLENGE_429_HTML):
            with self.subTest(body=body[:20]):
                calls = []
                def _t(u, _c=calls, _b=body):
                    _c.append(u)
                    return {"status": 429, "body": _b, "headers": {"Retry-After": "120"}}
                raw = goat_tools.goat_extract(url, transport=_t)
                self.assertEqual(raw.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(raw.get("status"), 429)
                self.assertIs(type(raw.get("status")), int)
                self.assertEqual(raw.get("retry_after"), 120)
                self.assertEqual(calls, [url])
                self.assertNotIn("slow down", json.dumps(raw))
                self.assertNotIn("challenge-form", json.dumps(raw))
                with mock.patch.object(goat_tools, "pinned_fetch", _t):
                    payload = json.loads(ex_handler({"url": url}))
                self.assertFalse(payload.get("ok"))
                self.assertEqual(payload.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(payload.get("status"), 429)
                self.assertEqual(payload.get("retry_after"), 120)
        # --- extract 429 bad Retry-After -> RATE_LIMITED, no retry_after, no leak/break ---
        for bad in ("not-a-number", "-5", "99999999", "12.5", "120; url=x"):
            with self.subTest(bad=bad):
                def _tb(u, _v=bad):
                    return {"status": 429, "body": NORMAL_429_HTML, "headers": {"Retry-After": _v}}
                raw = goat_tools.goat_extract(url, transport=_tb)
                self.assertEqual(raw.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(raw.get("status"), 429)
                self.assertNotIn("retry_after", raw)
                with mock.patch.object(goat_tools, "pinned_fetch", _tb):
                    payload = json.loads(ex_handler({"url": url}))
                self.assertEqual(payload.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(payload.get("status"), 429)
                self.assertNotIn("retry_after", payload)
                self.assertNotIn(bad, json.dumps(payload))
        # --- 503 stays HTTP_ERROR, not rate-limit ---
        raw503 = goat_tools.goat_extract(url, transport=lambda _r: {"status": 503, "body": "<html><head><title>Down</title></head><body><p>x</p></body></html>"})
        self.assertEqual(raw503.get("error"), {"code": "HTTP_ERROR"})
        self.assertEqual(raw503.get("status"), 503)
        self.assertNotIn("retry_after", raw503)
        # --- crawl 429 -> RATE_LIMITED raw+JSON, single call ---
        for run in ("raw", "json"):
            calls = []
            def _tc(u, _c=calls):
                _c.append(u)
                return {"status": 429, "body": NORMAL_429_HTML, "headers": {"Retry-After": "30"}}
            if run == "raw":
                res = goat_tools.goat_crawl(root, transport=_tc)
                self.assertEqual(res.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(res.get("status"), 429)
                self.assertEqual(res.get("retry_after"), 30)
            else:
                with mock.patch.object(goat_tools, "pinned_fetch", _tc):
                    res = json.loads(crawl_handler({"url": root}))
                self.assertFalse(res.get("ok"))
                self.assertEqual(res.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(res.get("status"), 429)
                self.assertEqual(res.get("retry_after"), 30)
            self.assertEqual(calls, [root])
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
