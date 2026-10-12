"""R4 regression: valid JSON containing markup-like text is data, not a challenge.

A 200 JSON article whose snippet literally contains
"<form id='challenge-form'> as plain text." must succeed (ok true),
not PROVIDER_BLOCKED. result_contract._has_structural_challenge already
returns False for valid JSON; this locks free_stack and free_verticals
against double-flagging. Offline only, no network.
"""

import importlib
import json
import socket
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import test_plugin_wiring as _wiring  # noqa: E402

MARKUP_SNIPPET = "<form id='challenge-form'> as plain text."

WIKI_MARKUP = {
    "query": {
        "search": [
            {"title": "Article", "pageid": 1,
             "snippet": "This code example uses %s" % MARKUP_SNIPPET},
        ]
    }
}
NEWS_MARKUP = {"articles": [{
    "title": "Article", "url": "https://example.com/article",
    "snippet": "This code example uses %s" % MARKUP_SNIPPET,
    "seendate": "20261009T120000Z", "domain": "example.com",
    "language": "English", "sourcecountry": "United States",
}]}


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


class JsonMarkupRegressionTests(OfflineRecordingTestCase):
    def test_json_markup_is_data_not_challenge(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        vendor_stack = importlib.import_module(mod_name + "._goat_v3_vendor.free_stack")
        vendor_verticals = importlib.import_module(mod_name + "._goat_v3_vendor.free_verticals")

        wiki_body = json.dumps(WIKI_MARKUP)
        news_body = json.dumps(NEWS_MARKUP)

        with self.subTest(seam="shared-classifier"):
            self.assertIsNone(vendor_contract.http_error_code(200, wiki_body))
            self.assertIsNone(vendor_contract.http_error_code(200, news_body))

        with self.subTest(seam="wikipedia-search"):
            raw = vendor_stack.wikipedia_search.__wrapped__(
                "markup check",
                transport=lambda u: {"status": 200, "body": wiki_body, "url": u},
            )
            self.assertTrue(raw.get("ok"), raw)
            self.assertEqual(len(raw.get("results", [])), 1, raw)
            self.assertNotEqual(raw.get("error", {}).get("code"), "PROVIDER_BLOCKED")

        with self.subTest(seam="news-search"):
            raw = vendor_verticals.news_search.__wrapped__(
                "markup check",
                transport=lambda u: {"status": 200, "body": news_body, "url": u},
            )
            self.assertTrue(raw.get("ok"), raw)
            self.assertEqual(len(raw.get("results", [])), 1, raw)
            self.assertNotEqual(raw.get("error", {}).get("code"), "PROVIDER_BLOCKED")

        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
