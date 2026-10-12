"""R4 E1 probe: HTTP correctness with typed status+host provenance (RED first).

Real raw goat_probe plus real registered JSON handler from a freshly built
bundle; only fake HTTP transports are injected. No live network.
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

ORDINARY_403_HTML = "<html><head><title>Forbidden</title></head><body><p>ordinary-403-marker</p></body></html>"
ORDINARY_404_HTML = "<html><head><title>Not Found</title></head><body><p>ordinary-404-marker</p></body></html>"
ORDINARY_503_HTML = "<html><head><title>Unavailable</title></head><body><p>ordinary-503-marker</p></body></html>"
NORMAL_200_HTML = "<html><head><title>Example</title></head><body><p>probe-ok-body-marker</p></body></html>"
NORMAL_204_BODY = ""
CHALLENGE_200_HTML = (
    "<html><head><title>Just a moment...</title>"
    '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    "</head><body>"
    '<form id="challenge-form" action="/cdn-cgi/challenge?tok=synB" method="post">'
    '<div class="cf-turnstile" data-sitekey="synB-site"></div>'
    '<div class="anomaly-modal__form"><button type="submit">Verify</button></div>'
    "</form></body></html>"
)
CHALLENGE_202_HTML = (
    "<html><head><title>Verify you are human</title></head><body>"
    '<form id="captcha-form" action="/captcha?tok=synC" method="post">'
    '<input type="hidden" name="tok" value="synC-secret"/>'
    '<div class="cf-turnstile" data-sitekey="synC-site"></div>'
    "</form></body></html>"
)
CHALLENGE_403_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><head><title>Just a moment...</title></head><body>'
    '<form id="challenge-form" action="/challenge?token=synthetic-secret-xyz" method="post">'
    '<div class="anomaly-modal__form"><button type="submit">Verify</button></div>'
    "</form></body></html>"
)
NORMAL_429_HTML = "<html><head><title>Too Many Requests</title></head><body><p>slow-down-marker</p></body></html>"


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


class ProbeHttpCorrectnessTests(OfflineRecordingTestCase):
    def test_probe_http_correctness_preserves_typed_diagnostics(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_probe"]["handler"]
        url = "https://example.com/article"
        # --- ordinary 403/404/503 => ok:false HTTP_ERROR + typed status + exact host ---
        for status, body, marker in (
            (403, ORDINARY_403_HTML, "ordinary-403-marker"),
            (404, ORDINARY_404_HTML, "ordinary-404-marker"),
            (503, ORDINARY_503_HTML, "ordinary-503-marker"),
        ):
            with self.subTest(kind="ordinary", status=status):
                def _t(req, _s=status, _b=body):
                    return {"status": _s, "body": _b}
                raw_calls = []
                def raw_tr(req, _f=_t, _c=raw_calls):
                    _c.append(req)
                    return _f(req)
                raw = goat_tools.goat_probe(url, transport=raw_tr)
                self.assertIs(raw.get("ok"), False)
                self.assertEqual(raw.get("error"), {"code": "HTTP_ERROR"})
                self.assertIs(type(raw.get("status")), int)
                self.assertEqual(raw.get("status"), status)
                self.assertEqual(raw.get("host"), "example.com")
                self.assertEqual(raw_calls, [url])
                raw_text = json.dumps(raw)
                self.assertNotIn(marker, raw_text)
                for absent in ("body", "text", "title", "results", "content", "exception", "provider"):
                    self.assertNotIn(absent, raw)
                with mock.patch.object(goat_tools, "pinned_fetch", _t):
                    payload = json.loads(handler({"url": url}))
                self.assertIs(payload.get("ok"), False)
                self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
                self.assertIs(type(payload.get("status")), int)
                self.assertEqual(payload.get("status"), status)
                self.assertEqual(payload.get("host"), "example.com")
                self.assertNotIn(marker, json.dumps(payload))
        # --- structural 200/202/403 challenge => PROVIDER_BLOCKED + status + host ---
        for status, body in ((200, CHALLENGE_200_HTML), (202, CHALLENGE_202_HTML), (403, CHALLENGE_403_HTML)):
            with self.subTest(kind="challenge", status=status):
                def _tc(req, _s=status, _b=body):
                    return {"status": _s, "body": _b}
                raw = goat_tools.goat_probe(url, transport=_tc)
                self.assertIs(raw.get("ok"), False)
                self.assertEqual(raw.get("error"), {"code": "PROVIDER_BLOCKED"})
                self.assertIs(type(raw.get("status")), int)
                self.assertEqual(raw.get("status"), status)
                self.assertEqual(raw.get("host"), "example.com")
                raw_text = json.dumps(raw)
                for leak in ("challenge-form", "captcha-form", "cf-turnstile", "challenge-platform", "synthetic-secret-xyz", "Just a moment"):
                    self.assertNotIn(leak, raw_text)
                with mock.patch.object(goat_tools, "pinned_fetch", _tc):
                    payload = json.loads(handler({"url": url}))
                self.assertIs(payload.get("ok"), False)
                self.assertEqual(payload.get("error"), {"code": "PROVIDER_BLOCKED"})
                self.assertEqual(payload.get("status"), status)
                self.assertEqual(payload.get("host"), "example.com")
        # --- 429 => RATE_LIMITED + status + host + safe Retry-After ---
        def _t429(req):
            return {"status": 429, "body": NORMAL_429_HTML, "headers": {"Retry-After": "120"}}
        raw = goat_tools.goat_probe(url, transport=_t429)
        self.assertIs(raw.get("ok"), False)
        self.assertEqual(raw.get("error"), {"code": "RATE_LIMITED"})
        self.assertEqual(raw.get("status"), 429)
        self.assertIs(type(raw.get("status")), int)
        self.assertEqual(raw.get("host"), "example.com")
        self.assertEqual(raw.get("retry_after"), 120)
        self.assertNotIn("slow-down-marker", json.dumps(raw))
        with mock.patch.object(goat_tools, "pinned_fetch", _t429):
            payload = json.loads(handler({"url": url}))
        self.assertIs(payload.get("ok"), False)
        self.assertEqual(payload.get("error"), {"code": "RATE_LIMITED"})
        self.assertEqual(payload.get("status"), 429)
        self.assertEqual(payload.get("host"), "example.com")
        self.assertEqual(payload.get("retry_after"), 120)
        for bad in ("not-a-number", "-5", "99999999", "12.5", "120; url=x"):
            with self.subTest(bad_retry=bad):
                def _tb(req, _v=bad):
                    return {"status": 429, "body": NORMAL_429_HTML, "headers": {"Retry-After": _v}}
                raw_b = goat_tools.goat_probe(url, transport=_tb)
                self.assertEqual(raw_b.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(raw_b.get("status"), 429)
                self.assertEqual(raw_b.get("host"), "example.com")
                self.assertNotIn("retry_after", raw_b)
                with mock.patch.object(goat_tools, "pinned_fetch", _tb):
                    payload_b = json.loads(handler({"url": url}))
                self.assertEqual(payload_b.get("error"), {"code": "RATE_LIMITED"})
                self.assertEqual(payload_b.get("status"), 429)
                self.assertNotIn("retry_after", payload_b)
                self.assertNotIn(bad, json.dumps(payload_b))
        # --- normal 200/204 => EXACT old success shape ---
        for status, body in ((200, NORMAL_200_HTML), (204, NORMAL_204_BODY)):
            with self.subTest(kind="success", status=status):
                def _tok(req, _s=status, _b=body):
                    return {"status": _s, "body": _b}
                raw_ok = goat_tools.goat_probe(url, transport=_tok)
                self.assertEqual(raw_ok, {"ok": True, "status": status, "host": "example.com"})
                with mock.patch.object(goat_tools, "pinned_fetch", _tok):
                    payload_ok = json.loads(handler({"url": url}))
                self.assertEqual(payload_ok, {"ok": True, "status": status, "host": "example.com"})
        # --- invalid statuses never success, no body/exception metadata ---
        for bad_status in (True, False, "200", 200.0, None, 99, 600, 0, -1, 1000):
            with self.subTest(bad_status=repr(bad_status)):
                def _tbad(req, _s=bad_status):
                    return {"status": _s, "body": NORMAL_200_HTML}
                raw_bad = goat_tools.goat_probe(url, transport=_tbad)
                self.assertIsNot(raw_bad.get("ok"), True)
                self.assertEqual(raw_bad.get("error"), {"code": "URL_BLOCKED"})
                if "status" in raw_bad:
                    self.assertIs(type(raw_bad["status"]), int)
                    self.assertTrue(100 <= raw_bad["status"] <= 599)
                self.assertNotIn("probe-ok-body-marker", json.dumps(raw_bad))
                for absent in ("body", "text", "title", "exception", "provider"):
                    self.assertNotIn(absent, raw_bad)
                with mock.patch.object(goat_tools, "pinned_fetch", _tbad):
                    payload_bad = json.loads(handler({"url": url}))
                self.assertIs(payload_bad.get("ok"), False)
                self.assertEqual(payload_bad.get("error"), {"code": "URL_BLOCKED"})
        # --- transport exception sanitized, bad URL/config stay legacy code-only ---
        def _boom(_u):
            raise RuntimeError("boom-secret-xyz")
        raw_exc = goat_tools.goat_probe(url, transport=_boom)
        self.assertIsNot(raw_exc.get("ok"), True)
        self.assertEqual(raw_exc.get("error"), {"code": "URL_BLOCKED"})
        self.assertNotIn("boom-secret-xyz", json.dumps(raw_exc))
        with mock.patch.object(goat_tools, "pinned_fetch", _boom):
            payload_exc = json.loads(handler({"url": url}))
        self.assertEqual(payload_exc, {"ok": False, "error": {"code": "URL_BLOCKED"}})
        self.assertNotIn("boom-secret-xyz", json.dumps(payload_exc))
        bad_raw = goat_tools.goat_probe("https://127.0.0.1/private", transport=lambda _u: {"status": 200, "body": NORMAL_200_HTML})
        self.assertEqual(bad_raw, {"error": {"code": "URL_BLOCKED"}})
        cfg_raw = goat_tools.goat_probe(url, transport=lambda _u: {"status": 200, "body": NORMAL_200_HTML}, provider_config=None)
        self.assertEqual(cfg_raw, {"error": {"code": "MISSING_CONFIG"}})
        self.assertNoNetwork()


class ProbePrivateRedirectTests(OfflineRecordingTestCase):
    """E2: private redirect keeps observed 302 + original public host, never dials private."""

    def test_probe_private_redirect_blocked_preserves_public_provenance(self):
        import socket as _socket

        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        url_gate = importlib.import_module(mod_name + ".url_gate")
        handler = _wiring._registered_tools(mod)["goat_probe"]["handler"]
        url = "https://example.com/start"

        def _gai(address):
            return (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (address, 443))

        # --- Case A: 302 Location is a literal private IP; never connect there ---
        for run in ("raw", "json"):
            resolver_calls, made, requested, closed, transport_calls = [], [], [], [], []

            def fake_resolver(host, port, type=0):
                resolver_calls.append((host, port))
                return [_gai("8.8.8.8")]

            class FakeConnection:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address))

                def request(self, *args, **kwargs):
                    requested.append((args, kwargs))

                def getresponse(self):
                    from types import SimpleNamespace

                    return SimpleNamespace(
                        status=302,
                        read=lambda _l: b"redirect-body-secret",
                        getheaders=lambda: [("Location", "https://127.0.0.1/private")],
                    )

                def close(self):
                    closed.append(True)

            def transport(requested_url, *a, **k):
                transport_calls.append(requested_url)
                return url_gate.pinned_fetch(requested_url, resolver=fake_resolver)

            with mock.patch.object(url_gate, "_PinnedHTTPSConnection", FakeConnection):
                if run == "raw":
                    res = goat_tools.goat_probe(url, transport=transport)
                    raw_text = json.dumps(res)
                else:
                    with mock.patch.object(goat_tools, "pinned_fetch", transport):
                        raw_json = handler({"url": url})
                    res = json.loads(raw_json)
                    raw_text = raw_json
            self.assertIs(res.get("ok"), False)
            self.assertEqual(res.get("error"), {"code": "REDIRECT_BLOCKED"})
            self.assertIs(type(res.get("status")), int)
            self.assertEqual(res.get("status"), 302)
            self.assertEqual(res.get("host"), "example.com")
            for absent in ("body", "text", "title", "results", "content", "exception", "provider"):
                self.assertNotIn(absent, res)
            self.assertNotIn("127.0.0.1", raw_text)
            self.assertNotIn("/private", raw_text)
            self.assertNotIn("redirect-body-secret", raw_text)
            self.assertEqual(transport_calls, [url])
            self.assertEqual(resolver_calls, [("example.com", 443)])
            self.assertEqual(len(made), 1)
            self.assertEqual(made[0], ("example.com", "8.8.8.8"))
            self.assertEqual(len(requested), 1)
            self.assertEqual(len(closed), 1)
            for _h, _addr in made:
                self.assertNotEqual(_addr, "127.0.0.1")

        # --- Case B: public redirect target whose DNS mixes private => blocked, same provenance ---
        for run in ("raw", "json"):
            resolver_calls, made, requested, closed, transport_calls = [], [], [], [], []

            def fake_resolver2(host, port, type=0):
                resolver_calls.append((host, port))
                if host == "example.com":
                    return [_gai("8.8.8.8")]
                return [_gai("8.8.8.8"), _gai("127.0.0.1")]

            class FakeConnection2:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address))

                def request(self, *args, **kwargs):
                    requested.append((args, kwargs))

                def getresponse(self):
                    from types import SimpleNamespace

                    return SimpleNamespace(
                        status=302,
                        read=lambda _l: b"redirect-body-secret",
                        getheaders=lambda: [("Location", "https://other.example/next")],
                    )

                def close(self):
                    closed.append(True)

            def transport2(requested_url, *a, **k):
                transport_calls.append(requested_url)
                return url_gate.pinned_fetch(requested_url, resolver=fake_resolver2)

            with mock.patch.object(url_gate, "_PinnedHTTPSConnection", FakeConnection2):
                if run == "raw":
                    res = goat_tools.goat_probe(url, transport=transport2)
                    raw_text = json.dumps(res)
                else:
                    with mock.patch.object(goat_tools, "pinned_fetch", transport2):
                        raw_json = handler({"url": url})
                    res = json.loads(raw_json)
                    raw_text = raw_json
            self.assertIs(res.get("ok"), False)
            self.assertEqual(res.get("error"), {"code": "REDIRECT_BLOCKED"})
            self.assertEqual(res.get("status"), 302)
            self.assertIs(type(res.get("status")), int)
            self.assertEqual(res.get("host"), "example.com")
            self.assertNotIn("127.0.0.1", raw_text)
            self.assertNotIn("redirect-body-secret", raw_text)
            self.assertEqual(transport_calls, [url])
            self.assertEqual(resolver_calls, [("example.com", 443), ("other.example", 443)])
            self.assertEqual(made, [("example.com", "8.8.8.8")])
            self.assertEqual(len(requested), 1)
            self.assertEqual(len(closed), 1)

        # --- _fetch injection: fake transport reports private final_url; keep observed 302 + public host ---
        def _priv_final(_u):
            return {"status": 302, "body": "injection-body-secret", "url": "https://127.0.0.1/private"}

        raw_priv = goat_tools.goat_probe(url, transport=_priv_final)
        self.assertIs(raw_priv.get("ok"), False)
        self.assertEqual(raw_priv.get("error"), {"code": "REDIRECT_BLOCKED"})
        self.assertEqual(raw_priv.get("status"), 302)
        self.assertEqual(raw_priv.get("host"), "example.com")
        self.assertNotIn("127.0.0.1", json.dumps(raw_priv))
        with mock.patch.object(goat_tools, "pinned_fetch", _priv_final):
            payload_priv = json.loads(handler({"url": url}))
        self.assertIs(payload_priv.get("ok"), False)
        self.assertEqual(payload_priv.get("error"), {"code": "REDIRECT_BLOCKED"})
        self.assertEqual(payload_priv.get("status"), 302)
        self.assertEqual(payload_priv.get("host"), "example.com")
        self.assertNotIn("127.0.0.1", json.dumps(payload_priv))

        # --- pre-fetch SSRF rejection carries no fake status ---
        pre = goat_tools.goat_probe("https://127.0.0.1/private", transport=lambda _u: {"status": 302, "body": "x"})
        self.assertEqual(pre, {"error": {"code": "URL_BLOCKED"}})
        self.assertNoNetwork()


class ProbePublicIdnTests(OfflineRecordingTestCase):
    """Public IDN accepted by check_url keeps canonical ASCII host in probe."""

    def test_probe_public_idn_uses_canonical_ascii_host(self):
        from urllib.parse import urlsplit as _urlsplit

        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        url_gate = importlib.import_module(mod_name + ".url_gate")
        handler = _wiring._registered_tools(mod)["goat_probe"]["handler"]
        url = "https://m\u00fcnchen.example/article"
        allowed, _code = url_gate.check_url(url)
        self.assertTrue(allowed)
        expected = _urlsplit(url).hostname.encode("idna").decode("ascii").lower().rstrip(".")
        self.assertIn("xn--", expected)
        # --- normal 200 stays success with canonical host, exact source URL ---
        for run in ("raw", "json"):
            requested = []

            def _t200(req, _c=requested):
                _c.append(req)
                return {"status": 200, "body": NORMAL_200_HTML}

            if run == "raw":
                res = goat_tools.goat_probe(url, transport=_t200)
            else:
                with mock.patch.object(goat_tools, "pinned_fetch", _t200):
                    res = json.loads(handler({"url": url}))
            self.assertEqual(res, {"ok": True, "status": 200, "host": expected})
            self.assertEqual(requested, [url])
        # --- ordinary 404 stays HTTP_ERROR with same validated host, exact URL ---
        for run in ("raw", "json"):
            requested = []

            def _t404(req, _c=requested):
                _c.append(req)
                return {"status": 404, "body": ORDINARY_404_HTML}

            if run == "raw":
                res = goat_tools.goat_probe(url, transport=_t404)
            else:
                with mock.patch.object(goat_tools, "pinned_fetch", _t404):
                    res = json.loads(handler({"url": url}))
            self.assertIs(res.get("ok"), False)
            self.assertEqual(res.get("error"), {"code": "HTTP_ERROR"})
            self.assertEqual(res.get("status"), 404)
            self.assertIs(type(res.get("status")), int)
            self.assertEqual(res.get("host"), expected)
            self.assertNotIn("ordinary-404-marker", json.dumps(res))
            self.assertEqual(requested, [url])
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
