"""R4 Cycle B: structural challenge at 200/202 -> PROVIDER_BLOCKED, FP controls stay success."""

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

EXACT_LEGACY = {"error": {"code": "PROVIDER_BLOCKED"}}
EXACT_JSON = {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}

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

ARTICLE_HTML = (
    "<html><head><title>CAPTCHA Research: Measuring Bots</title></head>"
    "<body><main><h1>CAPTCHA Research</h1>"
    "<p>Discussion of CAPTCHA, bot detection, and the phrase Just a moment in research.</p>"
    "<p>Readable article text about widgets.</p></main></body></html>"
)

ESCAPED_HTML = (
    "<html><head><title>Example Article</title></head><body>"
    "<p>Example: &lt;form id=&quot;challenge-form&quot;&gt; escaped markup.</p>"
    "<p>Readable article text about widgets.</p></body></html>"
)

COMMENT_HTML = (
    "<html><head><title>Example Article</title></head><body>"
    '<!-- <form id="challenge-form" action="/x"><input name="a"/></form> -->'
    "<p>Readable article text about widgets.</p></body></html>"
)

SCRIPT_QUOTED_HTML = (
    "<html><head><title>Example Article</title></head><body>"
    '<script>var s = "<form id=\'challenge-form\'>";</script>'
    '<script src="/app.js"></script>'
    "<p>Readable article text about widgets.</p></body></html>"
)

UNRELATED_FORM_HTML = (
    "<html><head><title>Example Article</title></head><body>"
    '<form id="search-form" action="/search"><input name="q"/></form>'
    "<p>Readable article text about widgets.</p></body></html>"
)

ORDINARY_202_HTML = (
    "<html><head><title>Accepted</title></head><body>"
    "<p>Readable article text about widgets, accepted for processing.</p></body></html>"
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


class ChallengeStructuralTests(OfflineRecordingTestCase):
    def test_structural_challenge_200_202_blocked_and_lookalikes_stay_success(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_extract"]["handler"]
        url = "https://example.com/article"
        for status, body in ((200, CHALLENGE_200_HTML), (202, CHALLENGE_202_HTML)):
            with self.subTest(challenge=status):
                def _t(req, _s=status, _b=body):
                    return {"status": _s, "body": _b}
                raw = goat_tools.goat_extract(url, transport=_t)
                self.assertEqual(raw, EXACT_LEGACY)
                for leak in ("challenge-form", "captcha-form", "cf-turnstile", "challenge-platform", "Just a moment", "secret", "status", "text"):
                    self.assertNotIn(leak, json.dumps(raw))
                with mock.patch.object(goat_tools, "pinned_fetch", _t):
                    payload = json.loads(handler({"url": url}))
                self.assertEqual(payload, EXACT_JSON)
                for leak in ("challenge-form", "captcha-form", "cf-turnstile", "challenge-platform", "Just a moment", "secret", "status"):
                    self.assertNotIn(leak, json.dumps(payload))
        lookalikes = (ARTICLE_HTML, ESCAPED_HTML, COMMENT_HTML, SCRIPT_QUOTED_HTML, UNRELATED_FORM_HTML, ORDINARY_202_HTML)
        for idx, body in enumerate(lookalikes):
            with self.subTest(lookalike=idx):
                raw = goat_tools.goat_extract(url, transport=lambda _r, _b=body: {"status": 200, "body": _b})
                self.assertIn("text", raw)
                self.assertNotIn("error", raw)
                with mock.patch.object(goat_tools, "pinned_fetch", lambda _r, _b=body: {"status": 200, "body": _b}):
                    payload = json.loads(handler({"url": url}))
                self.assertTrue(payload.get("ok") is True)
                self.assertIn("text", payload)
        ok202 = goat_tools.goat_extract(url, transport=lambda _r: {"status": 202, "body": ORDINARY_202_HTML})
        self.assertNotIn("error", ok202)
        self.assertIn("text", ok202)
        ord403 = goat_tools.goat_extract(url, transport=lambda _r: {"status": 403, "body": "<html><head><title>Forbidden</title></head><body><p>no</p></body></html>"})
        self.assertEqual(ord403.get("error"), {"code": "HTTP_ERROR"})
        self.assertEqual(ord403.get("status"), 403)
        self.assertNoNetwork()

    def test_quoted_challenge_markup_inside_inert_containers_stays_success(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_extract"]["handler"]
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        url = "https://example.com/article"
        quoted = (
            "<html><head><title>CAPTCHA Research Notes</title></head><body>"
            "<main><article><h1>Measuring CAPTCHAs</h1>"
            "<p>Readable article text about widgets.</p>"
            "<pre>&lt;form id=&quot;challenge-form&quot;&gt;demo&lt;/form&gt;"
            '<form id="challenge-form">quoted demo inside pre</form></pre>'
            '<code><div class="cf-turnstile" data-sitekey="demo-key">quoted</div></code>'
            '<textarea><form id="captcha-form">quoted demo</form></textarea>'
            '<template><form class="anomaly-modal__form">quoted demo</form></template>'
            "</article></main></body></html>"
        )
        # Quoted/demo widgets inside inert containers must NOT block (extract+shared).
        raw = goat_tools.goat_extract(url, transport=lambda _r: {"status": 200, "body": quoted})
        self.assertIn("text", raw)
        self.assertNotIn("error", raw)
        self.assertIn("Readable article text", raw.get("text", ""))
        self.assertIs(vendor_contract.http_error_code(200, quoted), None)
        with mock.patch.object(goat_tools, "pinned_fetch", lambda _r: {"status": 200, "body": quoted}):
            payload = json.loads(handler({"url": url}))
        self.assertTrue(payload.get("ok") is True)
        self.assertIn("text", payload)
        # Same widgets OUTSIDE quoted context must still block (no <article> blanket exempt).
        for body in (
            '<html><head><title>Just a moment...</title></head><body><form id="challenge-form">real</form></body></html>',
            '<html><head><title>Page</title></head><body><article><form id="challenge-form">real inside article</form></article></body></html>',
            '<html><head><title>Page</title></head><body><div class="cf-turnstile" data-sitekey="real-key"></div></body></html>',
        ):
            with self.subTest(real=body[:40]):
                raw_real = goat_tools.goat_extract(url, transport=lambda _r, _b=body: {"status": 200, "body": _b})
                self.assertEqual(raw_real, EXACT_LEGACY)
                self.assertIs(vendor_contract.http_error_code(200, body), "PROVIDER_BLOCKED")
                with mock.patch.object(goat_tools, "pinned_fetch", lambda _r, _b=body: {"status": 200, "body": _b}):
                    payload_real = json.loads(handler({"url": url}))
                self.assertEqual(payload_real, EXACT_JSON)
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
