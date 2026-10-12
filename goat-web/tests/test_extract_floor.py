"""Slice 3 extract floor (RED): empty-JS-shell must not be success + boilerplate floor.

Real legacy goat_extract route plus real registered JSON handler from a
freshly built bundle; only fake HTTP transports are injected. No live
network, no new deps.
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
import test_plugin_wiring as _wiring  # noqa: E402  (read-only fresh-bundle helpers)

EXACT_RAW_HTTP_202 = {"error": {"code": "HTTP_ERROR"}, "status": 202}
EXACT_RAW_PROVIDER_BLOCKED = {"error": {"code": "PROVIDER_BLOCKED"}}
EXACT_JSON_PROVIDER_BLOCKED = {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}

# (a) ESPN-class JS shell: nonempty HTML, zero readable text (script-only + empty divs).
JS_SHELL_202_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><head><title>ESPN Shell</title>'
    '<script>window.__STATE__={"app":"synthetic-js-shell-xyz","data":[1,2,3]};</script>'
    '<script src="/static/app-bundle-synthetic-xyz.js"></script>'
    "</head><body>"
    '<div id="app"></div><div class="root"></div><div id="__next"></div>'
    '<script>document.getElementById("app").innerHTML="loading";</script>'
    "</body></html>"
)

# (b) Boilerplate-heavy fixture: nav+footer+cookie/promo divs plus article/main.
BOILERPLATE_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><head><title>Boilerplate Article</title></head><body>'
    "<nav><ul><li>nav-boilerplate-phrase-xyz Home</li><li>nav-boilerplate-phrase-xyz Scores</li></ul></nav>"
    '<div class="cookie-banner">cookie-banner-phrase-xyz We use cookies to improve your experience</div>'
    '<div class="promo">promo-phrase-xyz Subscribe to our newsletter for exclusive offers</div>'
    "<main><article><h1>Widget Triumph</h1>"
    "<p>main-article-body-phrase-xyz Widgets spin quietly at dawn over the harbor.</p>"
    "</article></main>"
    "<footer>footer-boilerplate-phrase-xyz All rights reserved synthetic footer</footer>"
    "</body></html>"
)

# (c) Genuine short-but-real single sentence.
SHORT_REAL_HTML = (
    '<html><head><title>Short Article</title></head><body>'
    "<main><p>Widgets spin quietly at dawn.</p></main></body></html>"
)

# (e) Genuine 403 challenge (same shape as R4 vertical slice, synthetic).
CHALLENGE_403_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><head><title>Just a moment...</title></head><body>'
    '<form id="challenge-form" action="/challenge?token=synthetic-secret-xyz" method="post">'
    '<input type="hidden" name="challenge" value="synthetic-secret-xyz"/>'
    '<div class="anomaly-modal__title">Verify you are human</div>'
    '<div class="anomaly-modal__form"><button type="submit">Verify</button></div>'
    "</form></body></html>"
)


def _long_article_html(words=3000):
    body = " ".join("lorem-word-xyz-%d" % i for i in range(words))
    return (
        "<html><head><title>Long Article</title></head><body>"
        "<main><article><p>" + body + "</p></article></main></body></html>"
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
        def _denied(*args, **kwargs):
            self.network_attempts.append((name, args, kwargs))
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


class ExtractFloorTests(OfflineRecordingTestCase):
    def _fresh_extract(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_extract"]["handler"]
        return goat_tools, handler

    def test_a_empty_js_shell_202_is_http_error(self):
        goat_tools, handler = self._fresh_extract()
        url = "https://example.com/js-shell"

        def shell_transport(requested):
            return {"status": 202, "body": JS_SHELL_202_HTML}

        raw = goat_tools.goat_extract(url, transport=shell_transport)
        self.assertEqual(raw, EXACT_RAW_HTTP_202)

        def fake_pinned_fetch(requested):
            return {"status": 202, "body": JS_SHELL_202_HTML}

        with mock.patch.object(goat_tools, "pinned_fetch", fake_pinned_fetch):
            payload = json.loads(handler({"url": url}))
        self.assertTrue(payload.get("ok") is False)
        self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
        self.assertEqual(payload.get("status"), 202)
        self.assertNoNetwork()

    def test_b_boilerplate_filtered_main_preserved(self):
        goat_tools, handler = self._fresh_extract()
        url = "https://example.com/boilerplate"

        def bp_transport(requested):
            return {"status": 200, "body": BOILERPLATE_HTML}

        raw = goat_tools.goat_extract(url, transport=bp_transport)
        text = raw.get("text", "")
        self.assertIn("main-article-body-phrase-xyz", text)
        for phrase in (
            "cookie-banner-phrase-xyz",
            "promo-phrase-xyz",
            "nav-boilerplate-phrase-xyz",
            "footer-boilerplate-phrase-xyz",
        ):
            self.assertNotIn(phrase, text)

        with mock.patch.object(goat_tools, "pinned_fetch", lambda _u: {"status": 200, "body": BOILERPLATE_HTML}):
            payload = json.loads(handler({"url": url}))
        self.assertTrue(payload.get("ok") is True)
        htext = payload.get("text", "")
        self.assertIn("main-article-body-phrase-xyz", htext)
        for phrase in (
            "cookie-banner-phrase-xyz",
            "promo-phrase-xyz",
            "nav-boilerplate-phrase-xyz",
            "footer-boilerplate-phrase-xyz",
        ):
            self.assertNotIn(phrase, htext)
        self.assertNoNetwork()

    def test_c_short_real_single_sentence_succeeds(self):
        goat_tools, handler = self._fresh_extract()
        url = "https://example.com/short"

        def short_transport(requested):
            return {"status": 200, "body": SHORT_REAL_HTML}

        raw = goat_tools.goat_extract(url, transport=short_transport)
        self.assertEqual(raw.get("title"), "Short Article")
        self.assertIn("Widgets spin quietly at dawn.", raw.get("text", ""))
        self.assertEqual(raw.get("status"), 200)

        with mock.patch.object(goat_tools, "pinned_fetch", lambda _u: {"status": 200, "body": SHORT_REAL_HTML}):
            payload = json.loads(handler({"url": url}))
        self.assertTrue(payload.get("ok") is True)
        self.assertIn("Widgets spin quietly at dawn.", payload.get("text", ""))
        self.assertNoNetwork()

    def test_d_truncation_at_8000_unchanged(self):
        goat_tools, handler = self._fresh_extract()
        url = "https://example.com/long"
        long_html = _long_article_html()

        def long_transport(requested):
            return {"status": 200, "body": long_html}

        raw = goat_tools.goat_extract(url, transport=long_transport)
        self.assertTrue(raw.get("truncated") is True)
        self.assertLessEqual(len(raw.get("text", "")), 8000)
        self.assertIn("lorem-word-xyz-0", raw.get("text", ""))

        with mock.patch.object(goat_tools, "pinned_fetch", lambda _u: {"status": 200, "body": long_html}):
            payload = json.loads(handler({"url": url}))
        self.assertTrue(payload.get("ok") is True)
        self.assertTrue(payload.get("truncated") is True)
        self.assertLessEqual(len(payload.get("text", "")), 8000)
        self.assertNoNetwork()

    def test_e_genuine_403_challenge_still_provider_blocked(self):
        goat_tools, handler = self._fresh_extract()
        url = "https://example.com/article"

        def challenge_transport(requested):
            return {"status": 403, "body": CHALLENGE_403_HTML}

        raw = goat_tools.goat_extract(url, transport=challenge_transport)
        self.assertEqual(raw, EXACT_RAW_PROVIDER_BLOCKED)

        def fake_pinned_fetch(requested):
            return {"status": 403, "body": CHALLENGE_403_HTML}

        with mock.patch.object(goat_tools, "pinned_fetch", fake_pinned_fetch):
            payload = json.loads(handler({"url": url}))
        self.assertEqual(payload, EXACT_JSON_PROVIDER_BLOCKED)
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
