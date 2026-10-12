"""R4 public HTTP contract via real plugin registration/dispatch.

Real registered goat_answer / goat_filtered_search / goat_vertical_search
(DEFAULT registration) with mocked pinned_fetch. Offline deterministic
fixtures, no live network. Covers 12 HTTP scenarios per tool:

- 200 valid JSON (success)
- 202 empty/anomalous (error, not success)
- 403 ordinary forbidden => HTTP_ERROR
- 403 Cloudflare challenge => PROVIDER_BLOCKED
- 404 not found => HTTP_ERROR
- 429 rate limited => RATE_LIMITED
- 500 internal error => HTTP_ERROR
- TimeoutError => UPSTREAM_TIMEOUT
- OSError => CONNECTION_ERROR
- socket.gaierror => DNS_ERROR
- GuardError (private URL) => URL_BLOCKED
- 302 with Location => REDIRECT_BLOCKED
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

ORDINARY_403 = (
    "<html><head><title>Forbidden</title></head><body>"
    "<p>ordinary forbidden failure secret-xyz</p></body></html>"
)
ORDINARY_404 = (
    "<html><head><title>Not Found</title></head><body>"
    "<p>ordinary missing page secret-xyz</p></body></html>"
)
ORDINARY_500 = (
    "<html><head><title>Server Error</title></head><body>"
    "<p>ordinary upstream failure secret-xyz</p></body></html>"
)
ORDINARY_429 = (
    "<html><head><title>Too Many Requests</title></head><body>"
    "<p>ordinary slowdown secret-xyz</p></body></html>"
)
EMPTY_202 = ""
REDIRECT_BODY = "ordinary redirect secret-xyz"

WIKI_SEARCH_OK = {
    "query": {
        "search": [
            {"title": "France", "pageid": 111, "snippet": "France clipped ..."},
            {"title": "Paris", "pageid": 222, "snippet": "Paris clipped ..."},
        ]
    }
}
WIKI_EXTRACTS_OK = {
    "query": {
        "pages": [
            {
                "pageid": 111,
                "ns": 0,
                "title": "France",
                "extract": "France is a country in western Europe.",
            },
            {
                "pageid": 222,
                "ns": 0,
                "title": "Paris",
                "extract": "Paris is the capital and most populous city of France.",
            },
        ]
    }
}
FILTER_SEARCH_OK = {
    "query": {
        "search": [
            {
                "title": "Machine learning",
                "pageid": 555,
                "snippet": "Machine learning is a field of study in artificial intelligence.",
            }
        ]
    }
}
NEWS_OK = {"articles": [{
    "title": "Headline", "url": "https://news.example.org/story",
    "snippet": "A calm offline article about civic events.",
    "seendate": "20261009T120000Z", "domain": "news.example.org",
    "language": "English", "sourcecountry": "United States",
}]}
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


class PublicHttpContractTests(OfflineRecordingTestCase):
    def test_public_tools_http_contract(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_guard = importlib.import_module(mod_name + "._goat_v3_vendor.ssrf_guard")
        wiring = importlib.import_module(mod_name + ".v3_wiring")

        tools = _wiring._registered_tools(mod)
        answer_handler = tools["goat_answer"]["handler"]
        filtered_handler = tools["goat_filtered_search"]["handler"]
        vertical_handler = tools["goat_vertical_search"]["handler"]

        answer_args = {"query": "What is the capital of France?"}
        filtered_args = {"query": "machine learning"}
        vertical_args = {"vertical": "news", "query": "offline civic events"}

        def _dispatch(handler, args, fake):
            calls = []

            def _wrapped(url, *, timeout=10, max_response_bytes=1048576,
                         max_redirects=0, resolver=None, connection_factory=None):
                calls.append(url)
                return fake(url)

            with mock.patch.object(vendor_guard, "pinned_fetch", _wrapped):
                payload = json.loads(handler(dict(args)))
            return payload, calls

        def _static(status, body, headers=None):
            hdrs = dict(headers or {})

            def _fake(url):
                return {"status": status, "body": body, "headers": dict(hdrs), "url": url}
            return _fake

        def _raising(exc):
            def _fake(url):
                raise exc
            return _fake

        def _answer_success_fake(url):
            if "extracts" in url:
                return {"status": 200, "body": json.dumps(WIKI_EXTRACTS_OK),
                        "headers": {}, "url": url}
            return {"status": 200, "body": json.dumps(WIKI_SEARCH_OK),
                    "headers": {}, "url": url}

        def _filtered_success_fake(url):
            return {"status": 200, "body": json.dumps(FILTER_SEARCH_OK),
                    "headers": {}, "url": url}

        def _vertical_success_fake(body):
            def _fake(url):
                return {"status": 200, "body": json.dumps(body),
                        "headers": {}, "url": url}
            return _fake

        # ---- goat_answer: 12 scenarios ----
        answer_cases = [
            ("200-valid-json", _answer_success_fake, True, None),
            ("202-empty", _static(202, EMPTY_202), False, "HTTP_ERROR"),
            ("403-ordinary", _static(403, ORDINARY_403), False, "HTTP_ERROR"),
            ("403-challenge-form", _static(403, CHALLENGE_FORM), False, "PROVIDER_BLOCKED"),
            ("404", _static(404, ORDINARY_404), False, "HTTP_ERROR"),
            ("429", _static(429, ORDINARY_429), False, "RATE_LIMITED"),
            ("500", _static(500, ORDINARY_500), False, "HTTP_ERROR"),
            ("timeout", _raising(TimeoutError("mock upstream timeout secret-xyz")), False, "UPSTREAM_TIMEOUT"),
            ("connection", _raising(OSError("mock connection failure secret-xyz")), False, "CONNECTION_ERROR"),
            ("dns", _raising(socket.gaierror(socket.EAI_NONAME, "mock dns failure secret-xyz")), False, "DNS_ERROR"),
            ("private-ip", _raising(vendor_guard.GuardError(vendor_guard.URL_BLOCKED)), False, "URL_BLOCKED"),
            ("redirect-302", _static(302, REDIRECT_BODY, {"location": "https://example.com/other"}), False, "REDIRECT_BLOCKED"),
        ]
        for name, fake, expect_ok, expect_code in answer_cases:
            with self.subTest(tool="goat_answer", scenario=name):
                payload, calls = _dispatch(answer_handler, answer_args, fake)
                if expect_ok:
                    self.assertIs(payload.get("ok"), True, payload)
                    self.assertIn("answer", payload)
                    self.assertTrue(payload.get("sources"), payload)
                    self.assertEqual(len(calls), 2, payload)
                    for url in calls:
                        self.assertTrue(url.startswith(wiring.WIKIPEDIA_ACTION_ENDPOINT + "?"), url)
                else:
                    self.assertIs(payload.get("ok"), False, payload)
                    self.assertIsInstance(payload.get("error"), dict, payload)
                    self.assertEqual(payload.get("error").get("code"), expect_code, payload)
                    self.assertNotIn("secret-xyz", json.dumps(payload))
                    self.assertGreaterEqual(len(calls), 1, payload)

        # ---- goat_filtered_search: 12 scenarios ----
        filtered_cases = [
            ("200-valid-json", _filtered_success_fake, True, None),
            ("202-empty", _static(202, EMPTY_202), False, "HTTP_ERROR"),
            ("403-ordinary", _static(403, ORDINARY_403), False, "HTTP_ERROR"),
            ("403-challenge-form", _static(403, CHALLENGE_FORM), False, "PROVIDER_BLOCKED"),
            ("404", _static(404, ORDINARY_404), False, "HTTP_ERROR"),
            ("429", _static(429, ORDINARY_429), False, "RATE_LIMITED"),
            ("500", _static(500, ORDINARY_500), False, "HTTP_ERROR"),
            ("timeout", _raising(TimeoutError("mock upstream timeout secret-xyz")), False, "UPSTREAM_TIMEOUT"),
            ("connection", _raising(OSError("mock connection failure secret-xyz")), False, "CONNECTION_ERROR"),
            ("dns", _raising(socket.gaierror(socket.EAI_NONAME, "mock dns failure secret-xyz")), False, "DNS_ERROR"),
            ("private-ip", _raising(vendor_guard.GuardError(vendor_guard.URL_BLOCKED)), False, "URL_BLOCKED"),
            ("redirect-302", _static(302, REDIRECT_BODY, {"location": "https://example.com/other"}), False, "REDIRECT_BLOCKED"),
        ]
        for name, fake, expect_ok, expect_code in filtered_cases:
            with self.subTest(tool="goat_filtered_search", scenario=name):
                payload, calls = _dispatch(filtered_handler, filtered_args, fake)
                if expect_ok:
                    self.assertIs(payload.get("ok"), True, payload)
                    self.assertEqual(len(payload.get("results", [])), 1, payload)
                    self.assertEqual(len(calls), 1, payload)
                    self.assertTrue(calls[0].startswith(wiring.WIKIPEDIA_ACTION_ENDPOINT + "?"), calls[0])
                else:
                    self.assertIs(payload.get("ok"), False, payload)
                    self.assertIsInstance(payload.get("error"), dict, payload)
                    self.assertEqual(payload.get("error").get("code"), expect_code, payload)
                    self.assertNotIn("secret-xyz", json.dumps(payload))
                    self.assertGreaterEqual(len(calls), 1, payload)

        # ---- goat_vertical_search (news): 12 scenarios ----
        vertical_cases = [
            ("200-valid-json", _vertical_success_fake(NEWS_OK), True, None),
            ("202-empty", _static(202, EMPTY_202), False, "HTTP_ERROR"),
            ("403-ordinary", _static(403, ORDINARY_403), False, "HTTP_ERROR"),
            ("403-challenge-turnstile", _static(403, CHALLENGE_TURNSTILE), False, "PROVIDER_BLOCKED"),
            ("404", _static(404, ORDINARY_404), False, "HTTP_ERROR"),
            ("429", _static(429, ORDINARY_429), False, "RATE_LIMITED"),
            ("500", _static(500, ORDINARY_500), False, "HTTP_ERROR"),
            ("timeout", _raising(TimeoutError("mock upstream timeout secret-xyz")), False, "UPSTREAM_TIMEOUT"),
            ("connection", _raising(OSError("mock connection failure secret-xyz")), False, "CONNECTION_ERROR"),
            ("dns", _raising(socket.gaierror(socket.EAI_NONAME, "mock dns failure secret-xyz")), False, "DNS_ERROR"),
            ("private-ip", _raising(vendor_guard.GuardError(vendor_guard.URL_BLOCKED)), False, "URL_BLOCKED"),
            ("redirect-302", _static(302, REDIRECT_BODY, {"location": "https://example.com/other"}), False, "REDIRECT_BLOCKED"),
        ]
        for name, fake, expect_ok, expect_code in vertical_cases:
            with self.subTest(tool="goat_vertical_search", scenario=name):
                payload, calls = _dispatch(vertical_handler, vertical_args, fake)
                if expect_ok:
                    self.assertIs(payload.get("ok"), True, payload)
                    self.assertEqual(payload.get("vertical"), "news", payload)
                    self.assertEqual(len(payload.get("results", [])), 1, payload)
                    self.assertEqual(len(calls), 1, payload)
                    self.assertTrue(calls[0].startswith(wiring.GDELT_ENDPOINT + "?"), calls[0])
                else:
                    self.assertIs(payload.get("ok"), False, payload)
                    self.assertIsInstance(payload.get("error"), dict, payload)
                    self.assertEqual(payload.get("error").get("code"), expect_code, payload)
                    self.assertNotIn("secret-xyz", json.dumps(payload))
                    self.assertGreaterEqual(len(calls), 1, payload)

        # ---- vertical success per provider (Crossref / GDELT / Commons) ----
        for vertical, query, body, endpoint in (
            ("scholar", "offline research", SCHOLAR_OK, wiring.CROSSREF_ENDPOINT),
            ("news", "offline civic events", NEWS_OK, wiring.GDELT_ENDPOINT),
            ("images", "offline scenery", IMAGE_OK, wiring.COMMONS_ENDPOINT),
        ):
            with self.subTest(tool="goat_vertical_search", scenario="200-valid-" + vertical):
                payload, calls = _dispatch(
                    vertical_handler,
                    {"vertical": vertical, "query": query},
                    _vertical_success_fake(body),
                )
                self.assertIs(payload.get("ok"), True, payload)
                self.assertEqual(payload.get("vertical"), vertical, payload)
                self.assertTrue(payload.get("results"), payload)
                self.assertEqual(len(calls), 1, payload)
                self.assertTrue(calls[0].startswith(endpoint + "?"), calls[0])

        # ---- challenge variant on answer must also be PROVIDER_BLOCKED ----
        with self.subTest(tool="goat_answer", scenario="403-challenge-turnstile"):
            payload, _ = _dispatch(answer_handler, answer_args, _static(403, CHALLENGE_TURNSTILE))
            self.assertIs(payload.get("ok"), False, payload)
            self.assertEqual(payload.get("error", {}).get("code"), "PROVIDER_BLOCKED", payload)
            self.assertNotIn("secret-xyz", json.dumps(payload))

        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
