"""R4 HTTP SEARCH mapping: ordinary vs challenge vs rate-limit (RED first).

Real legacy goat_search route plus real registered JSON handler from a freshly
built bundle; only fake HTTP transports are injected. Ordinary 403/404/503 ->
HTTP_ERROR+typed status; real 403 structural challenge -> PROVIDER_BLOCKED
code-only; 429 -> RATE_LIMITED+status+valid retry_after; both no leaked body.
Existing 202 structural bot parser and legitimate empty SERP stay correct.
No DNS/network.
"""

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

EXACT_LEGACY_HTTP = {"error": {"code": "HTTP_ERROR"}}
EXACT_LEGACY_RATE = {"error": {"code": "RATE_LIMITED"}}
EXACT_LEGACY_BLOCKED = {"error": {"code": "PROVIDER_BLOCKED"}}

ORDINARY_403_HTML = (
    "<html><head><title>Forbidden</title></head>"
    "<body><p>ordinary-403-forbidden-secret-xyz</p></body></html>"
)
ORDINARY_404_HTML = (
    "<html><head><title>Not Found</title></head>"
    "<body><p>ordinary-404-missing-secret-xyz</p></body></html>"
)
ORDINARY_503_HTML = (
    "<html><head><title>Unavailable</title></head>"
    "<body><p>ordinary-503-unavailable-secret-xyz</p></body></html>"
)
CHALLENGE_403_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><head><title>Just a moment...</title></head><body>'
    '<form id="challenge-form" action="/challenge?token=synthetic-secret-xyz" method="post">'
    '<div class="anomaly-modal__form"><button type="submit">Verify</button></div>'
    "</form></body></html>"
)
NORMAL_429_HTML = (
    "<html><head><title>Too Many Requests</title></head>"
    "<body><p>ordinary-429-slowdown-secret-xyz</p></body></html>"
)
DDG_ANOMALY_202_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><body>'
    '<form id="challenge-form" action="//duckduckgo.com/anomaly.js?challenge=synthetic123" method="post">'
    '<div class="anomaly-modal__form"><button type="submit">Confirm</button></div>'
    "</form></body></html>"
)
EMPTY_NO_RESULTS_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><body><form action="/html/" method="post">'
    '<input name="q" value="zxqy offline"/></form>'
    '<div class="no-results"><h1>No results found</h1></div></body></html>'
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


class HttpSearchMappingTests(OfflineRecordingTestCase):
    def test_search_http_status_mapping(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_search"]["handler"]
        query = "offline query"
        # Ordinary 403/404/503 -> HTTP_ERROR+typed status, no leak, one call.
        for status, body in ((403, ORDINARY_403_HTML), (404, ORDINARY_404_HTML), (503, ORDINARY_503_HTML)):
            with self.subTest(kind="ordinary", status=status):
                calls = []
                def _t(u, _s=status, _b=body, _c=calls):
                    _c.append(u)
                    return {"status": _s, "body": _b}
                raw = goat_tools.goat_search(query, transport=_t)
                self.assertEqual(raw.get("error"), {"code": "HTTP_ERROR"})
                self.assertEqual(raw.get("status"), status)
                self.assertIs(type(raw.get("status")), int)
                self.assertEqual(calls, [calls[0]])
                self.assertIn("html.duckduckgo.com", calls[0])
                text = json.dumps(raw)
                self.assertNotIn("ordinary-%d" % status, text)
                self.assertNotIn("secret-xyz", text)
                self.assertNotIn("<p", text)
                with mock.patch.object(goat_tools, "pinned_fetch", _t):
                    payload = json.loads(handler({"query": query}))
                self.assertFalse(payload.get("ok"))
                self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
                self.assertEqual(payload.get("status"), status)
                self.assertNotIn("secret-xyz", json.dumps(payload))
        # Real 403 structural challenge -> PROVIDER_BLOCKED code-only, no leak.
        with self.subTest(kind="challenge-403"):
            calls = []
            def _tc(u, _c=calls):
                _c.append(u)
                return {"status": 403, "body": CHALLENGE_403_HTML}
            raw = goat_tools.goat_search(query, transport=_tc)
            self.assertEqual(raw, EXACT_LEGACY_BLOCKED)
            self.assertNotIn("challenge-form", json.dumps(raw))
            self.assertNotIn("secret-xyz", json.dumps(raw))
            self.assertNotIn("status", json.dumps(raw))
            self.assertEqual(len(calls), 1)
            with mock.patch.object(goat_tools, "pinned_fetch", _tc):
                payload = json.loads(handler({"query": query}))
            self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}})
            self.assertNotIn("challenge-form", json.dumps(payload))
            self.assertNotIn("status", json.dumps(payload))
        # 429 -> RATE_LIMITED+status+valid retry_after, no leak.
        with self.subTest(kind="ratelimit"):
            calls = []
            def _tr(u, _c=calls):
                _c.append(u)
                return {"status": 429, "body": NORMAL_429_HTML, "headers": {"Retry-After": "120"}}
            raw = goat_tools.goat_search(query, transport=_tr)
            self.assertEqual(raw.get("error"), {"code": "RATE_LIMITED"})
            self.assertEqual(raw.get("status"), 429)
            self.assertEqual(raw.get("retry_after"), 120)
            self.assertNotIn("slowdown-secret", json.dumps(raw))
            self.assertEqual(len(calls), 1)
            with mock.patch.object(goat_tools, "pinned_fetch", _tr):
                payload = json.loads(handler({"query": query}))
            self.assertEqual(payload.get("error"), {"code": "RATE_LIMITED"})
            self.assertEqual(payload.get("status"), 429)
            self.assertEqual(payload.get("retry_after"), 120)
        # Existing 202 structural bot parser stays PROVIDER_BLOCKED.
        with self.subTest(kind="anomaly-202"):
            def _ta(u):
                return {"status": 202, "body": DDG_ANOMALY_202_HTML}
            raw = goat_tools.goat_search(query, transport=_ta)
            self.assertEqual(raw, EXACT_LEGACY_BLOCKED)
            with mock.patch.object(goat_tools, "pinned_fetch", _ta):
                payload = json.loads(handler({"query": query}))
            self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}})
        # Legitimate empty SERP stays success.
        with self.subTest(kind="empty-serp"):
            def _te(u):
                return {"status": 200, "body": EMPTY_NO_RESULTS_HTML}
            raw = goat_tools.goat_search("zxqy offline", transport=_te)
            self.assertEqual(raw, {"results": []})
            with mock.patch.object(goat_tools, "pinned_fetch", _te):
                payload = json.loads(handler({"query": "zxqy offline"}))
            self.assertEqual(payload, {"ok": True, "results": []})
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
