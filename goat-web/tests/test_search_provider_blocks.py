"""Offline regression: provider challenge-form blocks and success shapes.

Real legacy goat_search route plus real registered JSON handler; only fake
HTTP transports are injected (plus fake resolver/connection for the real
pinned_fetch test). 403/429 and explicit challenge forms plus anomalous
non-empty no-SERP 200/202 map to PROVIDER_BLOCKED with no leakage and one
transport call; generic other HTTP errors and ordinary transport exceptions
remain URL_BLOCKED. Near misses and legitimate empty responses keep exact
success shapes. All fixtures are synthetic offline markup.
"""

import importlib, json, socket, sys, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import test_plugin_wiring as _wiring  # noqa: E402  (read-only fresh-bundle helpers)

EXACT_LEGACY_BLOCKED = {"error": {"code": "URL_BLOCKED"}}
EXACT_JSON_BLOCKED = {"ok": False, "error": {"code": "URL_BLOCKED"}}
EXACT_LEGACY_PROVIDER_BLOCKED = {"error": {"code": "PROVIDER_BLOCKED"}}
EXACT_JSON_PROVIDER_BLOCKED = {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}

# Synthetic offline fixtures (not captured live pages).
VALID_HTML = ('<a class="result__a" href="https://example.com/a">Alpha Title</a>'
              '<div class="result__snippet">Alpha snippet words.</div>'
              '<a class="result__a" href="https://example.com/b">Beta Title</a>'
              '<div class="result__snippet">Beta snippet words.</div>')
EXPECTED_VALID = [{"title": "Alpha Title", "url": "https://example.com/a", "snippet": "Alpha snippet words."},
                  {"title": "Beta Title", "url": "https://example.com/b", "snippet": "Beta snippet words."}]
UNICODE_HTML = ('<a class="result__a" href="https://example.com/caf%C3%A9">Caf\u00e9 na\u00efve</a>'
                '<div class="result__snippet">Caf\u00e9 fission \u00e9nergie.</div>')
EXPECTED_UNICODE = [{"title": "Caf\u00e9 na\u00efve", "url": "https://example.com/caf%C3%A9", "snippet": "Caf\u00e9 fission \u00e9nergie."}]
EMPTY_NO_RESULTS_HTML = ("<!-- synthetic, not live-captured -->" '<html><body><form action="/html/" method="post">'
    '<input name="q" value="zxqy offline"/></form><div class="result results_links results_links_deep web-result result--no-result">'
    '<div class="no-results"><div class="no-results__message"><h1>No results found for <strong>zxqy offline</strong></h1>'
    '<p>Check spelling or try different keywords.</p></div></div></div></body></html>')
EMPTY_KEYWORD_HTML = ("<!-- synthetic, not live-captured -->" '<html><body><form action="/html/" method="post">'
    '<input name="q" value="CAPTCHA challenge-form"/></form><div class="no-results">'
    '<h1>No results found for CAPTCHA challenge-form</h1><p>Check spelling for challenge-form anomaly-modal__form.</p></div></body></html>')
CONVINCING_HTML = ('<a class="result__a" href="https://example.com/evil">Convincing Title</a>'
                   '<div class="result__snippet">Convincing snippet that looks legitimate.</div>')
CHALLENGE_EXACT = '<form id="challenge-form">Please complete this CAPTCHA</form>'
CAPTCHA_EXACT = '<form id="captcha-form">Please complete this CAPTCHA</form>'
ANOMALY_EXACT = '<form class="anomaly-modal__form" action="/verify">prove human</form>'
# Realistic synthetic DDG HTTP202 bot-anomaly page (not live-captured).
DDG_ANOMALY_HTML = ("<!-- synthetic, not live-captured -->"
    '<html><body>'
    '<form id="img-form" action="//duckduckgo.com/anomaly.js?challenge=synthetic123" method="post">'
    '<input type="hidden" name="challenge" value="synthetic-challenge-token"/>'
    '<input type="hidden" name="response" value=""/>'
    '</form>'
    '<form id="challenge-form" action="//duckduckgo.com/anomaly.js?challenge=synthetic123" method="post">'
    '<input type="hidden" name="challenge" value="synthetic-challenge-token"/>'
    '<input type="hidden" name="token" value="synthetic-token"/>'
    '<div class="anomaly-modal__title">An automated system detected unusual activity from your device. Please confirm you are a human.</div>'
    '<div class="anomaly-modal__form"><button type="submit">Confirm you are a human</button></div>'
    '</form>'
    '</body></html>')
# Non-empty anomalous 200 bodies with no result anchors and no semantic
# no-results indicator (generic provider outage / unknown landing).
GENERIC_OUTAGE_HTML = ("<!-- synthetic, not live-captured -->"
    '<html><body><h1>Service maintenance</h1><p>Provider outage, please try later.</p></body></html>')
PLAIN_OUTAGE_TEXT = "Service temporarily unavailable, please try later -- synthetic outage probe"

CHALLENGE_CASES = [
    ("exact-challenge-form", CHALLENGE_EXACT), ("exact-captcha-form", CAPTCHA_EXACT), ("exact-anomaly-class", ANOMALY_EXACT),
    ("upper-form-id", '<FORM ID="challenge-form">Please complete this CAPTCHA</FORM>'), ("upper-captcha-id", '<form ID="captcha-form">verify</form>'),
    ("single-quotes", "<form id='challenge-form'>Please complete this CAPTCHA</form>"), ("attr-order", '<form method="post" action="/c" id="captcha-form">verify</form>'),
    ("whitespace", '<form  \n  id  =  "challenge-form" >Please complete this CAPTCHA</form>'), ("multi-class", '<form class="foo  anomaly-modal__form  bar" action="/c">x</form>'),
    ("single-quote-class", "<form class='anomaly-modal__form'>x</form>"), ("results-then-challenge", VALID_HTML + CHALLENGE_EXACT),
    ("challenge-then-results", CHALLENGE_EXACT + VALID_HTML), ("convincing-then-captcha", CONVINCING_HTML + CAPTCHA_EXACT),
    ("anomaly-then-results", ANOMALY_EXACT + VALID_HTML),
]
NEAR_MISS_CASES = [
    ("keyword-title", VALID_HTML.replace("Alpha Title", "CAPTCHA research guide")),
    ("keyword-snippet", VALID_HTML.replace("Alpha snippet words.", "Please complete this CAPTCHA tutorial.")),
    ("denied-snippet", VALID_HTML.replace("Beta snippet words.", "Access denied report summary.")),
    ("marker-word-snippet", VALID_HTML.replace("Beta snippet words.", "notes on challenge-form markup history.")),
    ("class-word-snippet", VALID_HTML.replace("Beta snippet words.", "notes on anomaly-modal__form history.")),
    ("escaped-marker", VALID_HTML.replace("Alpha snippet words.", "&lt;form id=&quot;challenge-form&quot;&gt; quoted example")),
    ("comment-marker", '<!-- <form id="challenge-form"> -->' + VALID_HTML),
    ("js-string-marker", '<script>var s = "<form id=\\"challenge-form\\">";</script>' + VALID_HTML),
    ("div-not-form", '<div id="challenge-form">not a form</div>' + VALID_HTML),
    ("guide-suffix-id", '<form id="challenge-form-guide">guide</form>' + VALID_HTML),
    ("guide-suffix-class", '<form class="anomaly-modal__form-guide">guide</form>' + VALID_HTML),
    ("unrelated-attr", '<form data-example="challenge-form">other</form>' + VALID_HTML),
    ("nested-quoted-in-snippet", '<a class="result__a" href="https://example.com/a">Alpha Title</a><div class="result__snippet">Alpha snippet.</div>'
     '<a class="result__a" href="https://example.com/b">Beta Title</a><div class="result__snippet">quoted example: <form id="challenge-form">quoted</form> end.</div>'),
    ("bot-word-title", VALID_HTML.replace("Alpha Title", "bot detection research guide")),
    ("anomaly-word-snippet", VALID_HTML.replace("Beta snippet words.", "notes on anomaly detection history.")),
    ("captcha-word-snippet", VALID_HTML.replace("Beta snippet words.", "CAPTCHA tutorial notes.")),
    ("no-results-word-snippet", VALID_HTML.replace("Beta snippet words.", "notes on no-results history.")),
    ("result-no-result-class-snippet", VALID_HTML.replace("Beta snippet words.", "notes on result--no-result history.")),
    ("no-results-message-snippet", VALID_HTML.replace("Beta snippet words.", "notes on no-results__message history.")),
]


def _exact_fake(response, exception, calls):
    def fake(url, *args, **kwargs):
        calls.append(url)
        if exception is not None:
            raise exception
        return response  # exact object: dict/str/bytes/SimpleNamespace
    return fake


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


class _SharedSearchCases:
    """Response assertions run on BOTH routes (legacy raw + registered JSON)."""

    EXPECTED_BLOCKED = None
    EXPECTED_PROVIDER_BLOCKED = None
    BLOCKED_LEAKS = ("<form", "challenge-form", "captcha-form", "anomaly-modal", "anomaly.js", "img-form", "anomaly-modal__title",
        "anomaly-modal__form", "Please complete", "CAPTCHA", "Access denied", "Rate limited", "Convincing", "example.com/evil", "results", "status", "secret")

    def _call(self, response=None, exception=None, query="offline query", **kwargs):
        raise NotImplementedError
    def _call_status(self, status, body, query="offline query", **kwargs):
        return self._call({"status": status, "body": body}, query=query, **kwargs)

    def _assert_code(self, payload, raw, calls, expected):
        self.assertEqual(payload, expected)
        self.assertEqual(len(calls), 1)
        self.assertIn("html.duckduckgo.com", calls[0])
        for leak in self.BLOCKED_LEAKS:
            self.assertNotIn(leak, raw)

    def assertBlocked(self, payload, raw, calls):
        self._assert_code(payload, raw, calls, self.EXPECTED_BLOCKED)

    def assertProviderBlocked(self, payload, raw, calls):
        self._assert_code(payload, raw, calls, self.EXPECTED_PROVIDER_BLOCKED)

    def assertSuccess(self, payload, expected):
        raise NotImplementedError
    def test_http_errors_are_blocked(self):
        # 403/429 are provider denials -> literal PROVIDER_BLOCKED.
        denied_bodies = {403: "Access denied", 429: "Rate limited"}
        for status in (403, 429):
            with self.subTest(status=status):
                self.assertProviderBlocked(*self._call_status(status, denied_bodies[status]))
        # Generic other HTTP errors remain URL_BLOCKED.
        generic_bodies = {302: "redirect without location"}
        for status in (100, 302, 400, 401, 404, 500, 503, 600, 0, "invalid"):
            with self.subTest(status=status):
                self.assertBlocked(*self._call_status(status, generic_bodies.get(status, "error body")))
        self.assertNoNetwork()

    def test_http_error_with_results_still_blocked(self):
        for status in (403, 429):
            with self.subTest(status=status):
                self.assertProviderBlocked(*self._call_status(status, CONVINCING_HTML))
        for status in (500,):
            with self.subTest(status=status):
                self.assertBlocked(*self._call_status(status, CONVINCING_HTML))
        self.assertNoNetwork()

    def test_transport_exceptions_are_sanitized(self):
        for exc in (RuntimeError("boom-secret-xyz"), OSError("dns-failure-secret"), ValueError("provider exploded secret body")):
            with self.subTest(exc=type(exc).__name__):
                payload, raw, calls = self._call(exception=exc)
                self.assertEqual(payload, self.EXPECTED_BLOCKED)
                self.assertEqual(len(calls), 1)
                for leak in ("boom-secret-xyz", "dns-failure-secret", "exploded", "secret"):
                    self.assertNotIn(leak, raw)
        self.assertNoNetwork()

    def test_challenge_forms_on_200_are_blocked(self):
        kinds = (("text", lambda h: {"status": 200, "body": h}), ("bytes", lambda h: {"status": 200, "body": h.encode()}),
                 ("object", lambda h: SimpleNamespace(status=200, body=h)))
        for name, html in CHALLENGE_CASES:
            for kind, build in kinds:
                with self.subTest(case=name, kind=kind):
                    self.assertProviderBlocked(*self._call(build(html)))
        self.assertNoNetwork()

    def test_ddg_anomaly_202_and_200_are_provider_blocked(self):
        # Same synthetic anomaly marker page must block on 202 and 200,
        # through dict/bytes/object adapters and raw str/bytes shapes.
        for status in (202, 200):
            with self.subTest(status=status):
                self.assertProviderBlocked(*self._call_status(status, DDG_ANOMALY_HTML))
                self.assertProviderBlocked(*self._call_status(status, DDG_ANOMALY_HTML.encode()))
                self.assertProviderBlocked(*self._call(SimpleNamespace(status=status, body=DDG_ANOMALY_HTML)))
                self.assertProviderBlocked(*self._call(SimpleNamespace(status=status, body=DDG_ANOMALY_HTML.encode())))
        for response in (DDG_ANOMALY_HTML, DDG_ANOMALY_HTML.encode(),
                         SimpleNamespace(status=200, body=DDG_ANOMALY_HTML),
                         SimpleNamespace(status=202, body=DDG_ANOMALY_HTML)):
            with self.subTest(kind=type(response).__name__ + repr(getattr(response, "status", ""))):
                payload, raw, calls = self._call(response)
                self.assertEqual(payload, self.EXPECTED_PROVIDER_BLOCKED)
                self.assertEqual(len(calls), 1)
                self.assertIn("html.duckduckgo.com", calls[0])
                for leak in ("anomaly.js", "img-form", "challenge-form", "anomaly-modal",
                             "synthetic-challenge-token", "synthetic-token", "<form", "status", "secret"):
                    self.assertNotIn(leak, raw)
        self.assertNoNetwork()

    def test_nonempty_no_serp_200_is_provider_blocked(self):
        # Non-empty 200 with no result anchors and no semantic no-results
        # indicator is an anomaly, not a legitimate empty SERP.
        spurious_no_results_text = ("<!-- synthetic, not live-captured -->"
            '<html><body><p>discussion of no-results and result--no-result without anchors</p></body></html>')
        for body in (GENERIC_OUTAGE_HTML, PLAIN_OUTAGE_TEXT, spurious_no_results_text):
            with self.subTest(body=repr(body)[:40]):
                payload, raw, calls = self._call_status(200, body)
                self.assertEqual(payload, self.EXPECTED_PROVIDER_BLOCKED)
                self.assertEqual(len(calls), 1)
                self.assertIn("html.duckduckgo.com", calls[0])
                for leak in ("maintenance", "outage", "unavailable", "<h1", "<form",
                             "challenge-form", "anomaly-modal", "status", "secret"):
                    self.assertNotIn(leak, raw)
        # Blank transport fixtures stay success (existing compatibility),
        # non-empty variants must not be treated as blank.
        self.assertProviderBlocked(*self._call_status(200, GENERIC_OUTAGE_HTML.encode()))
        self.assertProviderBlocked(*self._call(SimpleNamespace(status=200, body=GENERIC_OUTAGE_HTML)))
        self.assertNoNetwork()

    def test_challenge_near_misses_stay_success(self):
        for name, html in NEAR_MISS_CASES:
            with self.subTest(case=name):
                payload, raw, calls = self._call_status(200, html)
                self.assertEqual(len(calls), 1)
                self.assertSuccess(payload, payload["results"])
                self.assertEqual(len(payload["results"]), 2)
                for leak in ("URL_BLOCKED", '"ok": false', '"ok": False'):
                    self.assertNotIn(leak, raw)
        self.assertNoNetwork()

    def test_valid_results_capping_and_unicode(self):
        big = "".join('<a class="result__a" href="https://example.com/%d">Title %d</a><div class="result__snippet">Snippet %d</div>' % (i, i, i) for i in range(8))
        capped = [{"title": "Title %d" % i, "url": "https://example.com/%d" % i, "snippet": "Snippet %d" % i} for i in range(5)]
        payload, _raw, calls = self._call_status(200, big, query="bounded", max_results=5)
        self.assertEqual(len(calls), 1)
        self.assertSuccess(payload, capped)
        payload, _raw, calls = self._call_status(200, UNICODE_HTML, query="caf\u00e9")
        self.assertEqual(len(calls), 1)
        self.assertSuccess(payload, EXPECTED_UNICODE)
        self.assertSuccess(self._call_status(200, VALID_HTML)[0], EXPECTED_VALID)
        self.assertNoNetwork()

    def test_raw_str_bytes_object_bodies(self):
        for response in (VALID_HTML, VALID_HTML.encode(), SimpleNamespace(status=200, body=VALID_HTML)):
            with self.subTest(kind=type(response).__name__):
                payload, _raw, calls = self._call(response)
                self.assertEqual(len(calls), 1)
                self.assertSuccess(payload, EXPECTED_VALID)
        self.assertNoNetwork()

    def test_legitimate_empty_responses(self):
        payload, _raw, calls = self._call_status(200, EMPTY_NO_RESULTS_HTML, query="zxqy offline")
        self.assertEqual(len(calls), 1)
        self.assertSuccess(payload, [])
        for response in ({"status": 200, "body": ""}, "", b"", SimpleNamespace(status=200, body=""), {"status": 204, "body": ""}):
            with self.subTest(response=repr(response)[:40]):
                payload, _raw, calls = self._call(response, query="zxqy offline")
                self.assertEqual(len(calls), 1)
                self.assertSuccess(payload, [])
        payload, _raw, calls = self._call_status(200, EMPTY_KEYWORD_HTML, query="CAPTCHA challenge-form")
        self.assertEqual(len(calls), 1)
        self.assertSuccess(payload, [])
        self.assertNoNetwork()


class LegacySearchTests(_SharedSearchCases, OfflineRecordingTestCase):
    EXPECTED_BLOCKED = EXACT_LEGACY_BLOCKED
    EXPECTED_PROVIDER_BLOCKED = EXACT_LEGACY_PROVIDER_BLOCKED

    def setUp(self):
        super().setUp()
        bundle = _wiring._build_fresh_bundle(self)
        self.mod_name, _mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, self.mod_name)
        self.goat_tools = importlib.import_module(self.mod_name + ".goat_tools")

    def _call(self, response=None, exception=None, query="offline query", **kwargs):
        calls = []
        result = self.goat_tools.goat_search(query, transport=_exact_fake(response, exception, calls), **kwargs)
        return result, json.dumps(result), calls
    def assertSuccess(self, payload, expected):
        self.assertEqual(payload, {"results": expected})


class RegisteredSearchTests(_SharedSearchCases, OfflineRecordingTestCase):
    EXPECTED_BLOCKED = EXACT_JSON_BLOCKED
    EXPECTED_PROVIDER_BLOCKED = EXACT_JSON_PROVIDER_BLOCKED

    def setUp(self):
        super().setUp()
        bundle = _wiring._build_fresh_bundle(self)
        self.mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, self.mod_name)
        self.goat_tools = importlib.import_module(self.mod_name + ".goat_tools")
        self.handler = _wiring._registered_tools(mod)["goat_search"]["handler"]

    def _call(self, response=None, exception=None, query="offline query", **kwargs):
        calls = []
        args = {"query": query}
        args.update(kwargs)
        with mock.patch.object(self.goat_tools, "pinned_fetch", _exact_fake(response, exception, calls)):
            raw = self.handler(args)
        return json.loads(raw), raw, calls
    def assertSuccess(self, payload, expected):
        self.assertEqual(payload, {"ok": True, "results": expected})


class RealPinnedFetchTransportTests(OfflineRecordingTestCase):
    """Focused injection: goat_search over the REAL url_gate.pinned_fetch."""

    def setUp(self):
        super().setUp()
        bundle = _wiring._build_fresh_bundle(self)
        self.mod_name, _mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, self.mod_name)
        self.goat_tools = importlib.import_module(self.mod_name + ".goat_tools")
        self.url_gate = importlib.import_module(self.mod_name + ".url_gate")

    def test_goat_search_over_real_pinned_fetch_blocks_403_and_429(self):
        for status in (403, 429):
            with self.subTest(status=status):
                resolver_calls, made, requested, closed, transport_calls = [], [], [], [], []

                def fake_resolver(host, port, type=0):
                    resolver_calls.append((host, port))
                    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]

                class FakeConnection:
                    def __init__(self, hostname, address, timeout=10):
                        made.append((hostname, address))
                    def request(self, *args, **kwargs):
                        requested.append((args, kwargs))
                    def getresponse(self):
                        return SimpleNamespace(status=status, read=lambda _l: b"challenge probe secret-body", getheaders=lambda: [])
                    def close(self):
                        closed.append(True)

                def transport(url, *args, **kwargs):
                    transport_calls.append(url)
                    return self.url_gate.pinned_fetch(url, resolver=fake_resolver)

                with mock.patch.object(self.url_gate, "_PinnedHTTPSConnection", FakeConnection):
                    result = self.goat_tools.goat_search("offline query", transport=transport)
                self.assertEqual(result, EXACT_LEGACY_PROVIDER_BLOCKED)
                self.assertEqual(len(transport_calls), 1)
                self.assertIn("html.duckduckgo.com", transport_calls[0])
                self.assertEqual(resolver_calls, [("html.duckduckgo.com", 443)])
                self.assertEqual((len(made), len(requested), len(closed)), (1, 1, 1))
                self.assertNotIn("secret-body", json.dumps(result))
                self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
