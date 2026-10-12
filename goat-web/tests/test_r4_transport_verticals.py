"""R4 free-vertical HTTP classification: ordinary vs challenge vs success.

Direct free_verticals.news_search/scholar/image with fake transports plus the
real registered goat_vertical_search (DEFAULT registration). Ordinary
403/404/503 -> HTTP_ERROR; 429 -> RATE_LIMITED; structural challenge
200/202/403 -> PROVIDER_BLOCKED; valid JSON 200 / empty articles -> success.
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

CHALLENGE_FORM = (
    '<html><head><title>Verify you are human</title></head><body>'
    '<form id="challenge-form" action="/challenge">'
    '<input type="hidden" name="c" value="secret-xyz"></form></body></html>'
)
CHALLENGE_TURNSTILE = (
    '<html><head><title>Attention required</title></head><body>'
    '<div class="cf-turnstile" data-sitekey="secret-xyz"></div></body></html>'
)
CHALLENGE_SCRIPT = (
    '<html><head><title>Just a moment, please</title>'
    '<script src="/cdn-cgi/challenge-platform/h/b/scripts/jsd/test.js"></script>'
    '</head><body><p>checking secret-xyz</p></body></html>'
)
COMMENT_ONLY = (
    '<!-- <form id="challenge-form" action="/x"></form>'
    '<script src="/cdn-cgi/challenge-platform/x.js"></script> -->'
    '<html><head><title>Normal</title></head><body>ok</body></html>'
)
SCRIPT_QUOTED = (
    '<html><head><title>Research notes</title></head><body>'
    '<script>var s = "<form id=\\"challenge-form\\">";</script>'
    '<p>captcha article secret-xyz</p></body></html>'
)
ESCAPED_MARKUP = '<p>&lt;form id="challenge-form"&gt; captcha discussion</p>'

NEWS_OK = {"articles": [{
    "title": "Headline", "url": "https://news.example.org/story",
    "snippet": "An article about captcha verification systems secret-xyz",
    "seendate": "20261009T120000Z", "domain": "news.example.org",
    "language": "English", "sourcecountry": "United States",
}]}
NEWS_EMPTY = {"articles": []}
SCHOLAR_OK = {"message": {"items": [{
    "DOI": "10.1000/demo", "title": ["A useful paper"],
    "author": [{"given": "Ada", "family": "Lovelace"}],
    "published-print": {"date-parts": [[2024, 2, 3]]},
    "container-title": ["Journal of Examples"],
    "URL": "https://doi.org/10.1000/demo",
}]}}
IMAGE_OK = {"query": {"pages": [{
    "title": "File:Example.jpg",
    "imageinfo": [{
        "url": "https://upload.wikimedia.org/wikipedia/commons/e/example.jpg",
        "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/example.jpg/800px-example.jpg",
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "extmetadata": {
            "ImageDescription": {"value": "<p>A scenic view</p>"},
            "Artist": {"value": "A. Artist"},
            "LicenseShortName": {"value": "CC BY-SA 4.0"},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
        },
    }],
}]}}


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


class FreeVerticalHttpTests(OfflineRecordingTestCase):
    def test_free_vertical_http_failures_classify(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_verticals = importlib.import_module(mod_name + "._goat_v3_vendor.free_verticals")
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        vendor_guard = importlib.import_module(mod_name + "._goat_v3_vendor.ssrf_guard")
        plugin_pkg = importlib.import_module(mod_name)
        wiring = importlib.import_module(mod_name + ".v3_wiring")

        def _direct(search, status, body):
            calls = []

            def _transport(url):
                calls.append(url)
                return {"status": status, "body": body}

            result = search("synthetic offline check", transport=_transport)
            return result, calls

        searches = (
            ("news", vendor_verticals.news_search),
            ("scholar", vendor_verticals.scholar_search),
            ("image", vendor_verticals.image_search),
        )
        for name, search in searches:
            for status in (403, 404, 503):
                with self.subTest(kind="direct-ordinary", search=name, status=status):
                    result, calls = _direct(search, status, "ordinary provider failure secret-xyz")
                    self.assertEqual(result, {"ok": False, "error": {"code": "HTTP_ERROR"}})
                    self.assertNotIn("secret-xyz", json.dumps(result))
                    self.assertEqual(len(calls), 1)
            with self.subTest(kind="direct-ratelimit", search=name):
                result, calls = _direct(search, 429, "ordinary rate limit secret-xyz")
                self.assertEqual(result, {"ok": False, "error": {"code": "RATE_LIMITED"}})
                self.assertNotIn("secret-xyz", json.dumps(result))
                self.assertEqual(len(calls), 1)
            for status, body in ((200, CHALLENGE_FORM), (202, CHALLENGE_TURNSTILE), (403, CHALLENGE_SCRIPT)):
                with self.subTest(kind="direct-challenge", search=name, status=status):
                    result, calls = _direct(search, status, body)
                    self.assertEqual(result, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}})
                    self.assertNotIn("secret-xyz", json.dumps(result))
                    self.assertEqual(len(calls), 1)
        with self.subTest(kind="direct-news-success"):
            result, _ = _direct(vendor_verticals.news_search, 200, json.dumps(NEWS_OK))
            self.assertIs(result.get("ok"), True)
            self.assertEqual(len(result["results"]), 1)
            self.assertNotIn("captcha-form", json.dumps(result))
        with self.subTest(kind="direct-news-empty-success"):
            result, _ = _direct(vendor_verticals.news_search, 200, json.dumps(NEWS_EMPTY))
            self.assertEqual(result, {"ok": True, "results": [], "truncated": False})
        with self.subTest(kind="direct-scholar-success"):
            result, _ = _direct(vendor_verticals.scholar_search, 200, json.dumps(SCHOLAR_OK))
            self.assertIs(result.get("ok"), True)
        with self.subTest(kind="direct-image-success"):
            result, _ = _direct(vendor_verticals.image_search, 200, json.dumps(IMAGE_OK))
            self.assertIs(result.get("ok"), True)
        with self.subTest(kind="shared-error-code-matrix"):
            self.assertEqual(vendor_contract.http_error_code(429, CHALLENGE_FORM), "RATE_LIMITED")
            self.assertEqual(vendor_contract.http_error_code(200, CHALLENGE_FORM), "PROVIDER_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(202, CHALLENGE_TURNSTILE), "PROVIDER_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(403, CHALLENGE_SCRIPT), "PROVIDER_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(503, "ordinary secret-xyz"), "HTTP_ERROR")
            self.assertIs(vendor_contract.http_error_code(200, "ordinary secret-xyz"), None)
            self.assertIs(vendor_contract.http_error_code(302, "ordinary"), None)
            self.assertEqual(vendor_contract.http_error_code("503", "ordinary"), "URL_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(True, "ordinary"), "URL_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(200.0, "ordinary"), "URL_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(99, "ordinary"), "URL_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(600, "ordinary"), "URL_BLOCKED")
            self.assertEqual(vendor_contract.http_error_code(None, "ordinary"), "URL_BLOCKED")
            self.assertIs(vendor_contract.http_error_code(200, COMMENT_ONLY), None)
            self.assertIs(vendor_contract.http_error_code(200, SCRIPT_QUOTED), None)
            self.assertIs(vendor_contract.http_error_code(200, ESCAPED_MARKUP), None)
        with self.subTest(kind="shared-map-error-compat"):
            self.assertEqual(vendor_verticals.map_error(None), "MISSING_CONFIG")
            self.assertEqual(vendor_verticals.map_error(vendor_guard.GuardError(vendor_guard.HTTP_ERROR)), "HTTP_ERROR")
            self.assertEqual(vendor_verticals.map_error(vendor_guard.GuardError(vendor_guard.RATE_LIMITED)), "RATE_LIMITED")
            self.assertEqual(vendor_verticals.map_error(vendor_guard.GuardError(vendor_guard.PROVIDER_BLOCKED)), "PROVIDER_BLOCKED")
            self.assertEqual(vendor_verticals.map_error(RuntimeError("boom-secret-xyz")), "URL_BLOCKED")

        tools = _wiring._registered_tools(mod)
        handler = tools["goat_vertical_search"]["handler"]

        def _registered(body, status=200):
            calls = []

            def _fake_pinned(url, *, timeout=10, max_response_bytes=1048576,
                             max_redirects=0, resolver=None, connection_factory=None):
                calls.append({"url": url, "timeout": timeout,
                              "max_response_bytes": max_response_bytes,
                              "max_redirects": max_redirects, "resolver": resolver,
                              "connection_factory": connection_factory})
                return {"status": status, "body": body}

            with mock.patch.object(vendor_guard, "pinned_fetch", _fake_pinned):
                payload = json.loads(handler({"vertical": "news", "query": "synthetic offline check"}))
            return payload, calls

        with self.subTest(kind="registered-default-ordinary-403"):
            payload, calls = _registered("ordinary provider failure secret-xyz", status=403)
            self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}})
            self.assertNotIn("secret-xyz", json.dumps(payload))
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0]["url"].startswith("https://api.gdeltproject.org/api/v2/doc/doc?"))
            self.assertEqual(calls[0]["timeout"], wiring._PINNED_TIMEOUT)
            self.assertEqual(calls[0]["max_response_bytes"], wiring._PINNED_MAX_BYTES)
            self.assertEqual(calls[0]["max_redirects"], wiring._PINNED_MAX_REDIRECTS)
            self.assertIs(calls[0]["resolver"], None)
            self.assertIs(calls[0]["connection_factory"], None)
        with self.subTest(kind="registered-default-429"):
            payload, calls = _registered("ordinary rate limit secret-xyz", status=429)
            self.assertEqual(payload, {"ok": False, "error": {"code": "RATE_LIMITED"}})
            self.assertNotIn("secret-xyz", json.dumps(payload))
            self.assertEqual(len(calls), 1)
        with self.subTest(kind="registered-default-challenge-200"):
            payload, calls = _registered(CHALLENGE_FORM, status=200)
            self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}})
            self.assertNotIn("secret-xyz", json.dumps(payload))
            self.assertEqual(len(calls), 1)
        with self.subTest(kind="registered-default-genuine-2xx-success"):
            payload, calls = _registered(json.dumps(NEWS_OK), status=200)
            self.assertIs(payload.get("ok"), True)
            self.assertEqual(payload.get("vertical"), "news")
            self.assertEqual(len(payload["results"]), 1)
            self.assertEqual(len(calls), 1)
        with self.subTest(kind="endpoint-check-precedes-transport"):
            calls = []

            def _recording(url, **kwargs):
                calls.append(url)
                return {"status": 200, "body": json.dumps(NEWS_EMPTY)}

            transports = wiring.make_vertical_transports(_fetch=plugin_pkg.checked_fetch)
            with mock.patch.object(vendor_guard, "pinned_fetch", _recording):
                with self.assertRaises(vendor_guard.GuardError):
                    transports["news"]("https://evil.example/x")
            self.assertEqual(calls, [])
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
