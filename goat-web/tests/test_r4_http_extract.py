"""R4 extract vertical slice 1 (RED): 403 challenge must not be success.

Real legacy goat_extract route plus real registered JSON handler from a
freshly built bundle; only fake HTTP transports are injected. A realistic
synthetic 403 challenge form must return public PROVIDER_BLOCKED with no
block-page text or secret; a normal 200 control in the same vertical path
must preserve successful extraction. No other HTTP taxonomy is demanded yet.
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

EXACT_LEGACY_PROVIDER_BLOCKED = {"error": {"code": "PROVIDER_BLOCKED"}}
EXACT_JSON_PROVIDER_BLOCKED = {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}

# Realistic synthetic 403 bot-challenge page (not live-captured).
CHALLENGE_403_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><head><title>Just a moment...</title></head><body>'
    '<form id="challenge-form" action="/challenge?token=synthetic-secret-xyz" method="post">'
    '<input type="hidden" name="challenge" value="synthetic-secret-xyz"/>'
    '<div class="anomaly-modal__title">Verify you are human</div>'
    '<div class="anomaly-modal__form"><button type="submit">Verify</button></div>'
    "</form></body></html>"
)

NORMAL_200_HTML = (
    "<html><head><title>Example Article</title></head>"
    "<body><main><h1>Example Heading</h1>"
    "<p>Readable article text about widgets.</p></main></body></html>"
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


class ExtractChallengeVerticalTests(OfflineRecordingTestCase):
    def test_extract_403_challenge_is_provider_blocked_and_200_control_stays_success(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_extract"]["handler"]

        url = "https://example.com/article"

        # --- raw 403 challenge -> PROVIDER_BLOCKED, no leakage ---
        raw_calls = []

        def challenge_transport(requested):
            raw_calls.append(requested)
            return {"status": 403, "body": CHALLENGE_403_HTML}

        raw = goat_tools.goat_extract(url, transport=challenge_transport)
        raw_text = json.dumps(raw)
        self.assertEqual(raw, EXACT_LEGACY_PROVIDER_BLOCKED)
        self.assertEqual(raw_calls, [url])
        for leak in ("challenge-form", "anomaly-modal", "synthetic-secret-xyz", "<form", "Just a moment", "text", "status"):
            self.assertNotIn(leak, raw_text)

        # --- registered JSON 403 challenge -> PROVIDER_BLOCKED, no leakage ---
        json_calls = []

        def fake_pinned_fetch(requested):
            json_calls.append(requested)
            return {"status": 403, "body": CHALLENGE_403_HTML}

        with mock.patch.object(goat_tools, "pinned_fetch", fake_pinned_fetch):
            raw_json = handler({"url": url})
        payload = json.loads(raw_json)
        self.assertEqual(payload, EXACT_JSON_PROVIDER_BLOCKED)
        self.assertEqual(json_calls, [url])
        for leak in ("challenge-form", "anomaly-modal", "synthetic-secret-xyz", "<form", "Just a moment", "status", "secret"):
            self.assertNotIn(leak, raw_json)

        # --- normal 200 control stays success on both routes ---
        def ok_transport(requested):
            return {"status": 200, "body": NORMAL_200_HTML}

        ok_raw = goat_tools.goat_extract(url, transport=ok_transport)
        self.assertEqual(ok_raw["title"], "Example Article")
        self.assertIn("Readable article text", ok_raw["text"])
        self.assertEqual(ok_raw["status"], 200)

        with mock.patch.object(goat_tools, "pinned_fetch", lambda _u: {"status": 200, "body": NORMAL_200_HTML}):
            ok_json_raw = handler({"url": url})
        ok_payload = json.loads(ok_json_raw)
        self.assertTrue(ok_payload.get("ok") is True)
        self.assertIn("Readable article text", ok_payload.get("text", ""))
        self.assertNoNetwork()

    def test_extract_ordinary_http_errors_are_http_error_with_typed_status(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        handler = _wiring._registered_tools(mod)["goat_extract"]["handler"]
        url = "https://example.com/article"
        cases = (
            (403, "<html><head><title>Forbidden</title></head><body><p>ordinary-403-forbidden-body</p></body></html>"),
            (404, "<html><head><title>Not Found</title></head><body><p>ordinary-404-missing-body</p></body></html>"),
            (503, "<html><head><title>Unavailable</title></head><body><p>ordinary-503-unavailable-body</p></body></html>"),
        )
        for status, body in cases:
            with self.subTest(status=status):
                raw_calls = []
                def raw_transport(requested, _s=status, _b=body):
                    raw_calls.append(requested)
                    return {"status": _s, "body": _b}
                raw = goat_tools.goat_extract(url, transport=raw_transport)
                self.assertEqual(raw.get("error"), {"code": "HTTP_ERROR"})
                self.assertIs(type(raw.get("status")), int)
                self.assertTrue(100 <= raw["status"] <= 599)
                self.assertEqual(raw["status"], status)
                self.assertEqual(raw_calls, [url])
                raw_text = json.dumps(raw)
                for leak in ("ordinary-%d" % status, "forbidden-body", "missing-body", "unavailable-body", "<p", "Forbidden", "Not Found"):
                    self.assertNotIn(leak, raw_text)
                for absent in ("text", "title", "results", "content", "exception", "body"):
                    self.assertNotIn(absent, raw)
                json_calls = []
                def fake_pinned_fetch(requested, _s=status, _b=body):
                    json_calls.append(requested)
                    return {"status": _s, "body": _b}
                with mock.patch.object(goat_tools, "pinned_fetch", fake_pinned_fetch):
                    raw_json = handler({"url": url})
                payload = json.loads(raw_json)
                self.assertTrue(payload.get("ok") is False)
                self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
                self.assertIs(type(payload.get("status")), int)
                self.assertTrue(100 <= payload["status"] <= 599)
                self.assertEqual(payload["status"], status)
                self.assertEqual(json_calls, [url])
                for leak in ("ordinary-%d" % status, "forbidden-body", "missing-body", "unavailable-body", "<p", "secret"):
                    self.assertNotIn(leak, raw_json)
                for absent in ("text", "title", "results", "content", "exception", "body"):
                    self.assertNotIn(absent, payload)
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
