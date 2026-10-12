"""R4 transport contract: strict diagnostic validation + failure normalization.

Real shared result_contract validators (via a freshly built bundle) and the
built actual _json_handler. Evidenced bug: _validated_host strips [ ] then
accepts bracketed DNS (e.g. [example.com]); brackets are IPv6-only.
"""

import copy
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


class TransportContractTests(OfflineRecordingTestCase):
    def test_diagnostic_validation_strict_and_bracketed_dns_rejected(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        plugin_pkg = importlib.import_module(mod_name)
        codes = ("HTTP_ERROR", "RATE_LIMITED", "PROVIDER_BLOCKED", "REDIRECT_BLOCKED")
        for code in codes:
            with self.subTest(kind="valid-diagnostics", code=code):
                normalized = vendor_contract.normalize_result(
                    {"ok": False, "error": {"code": code}, "status": 503,
                     "host": "example.com", "retry_after": "5"}
                )
                self.assertEqual(
                    normalized,
                    {"ok": False, "error": {"code": code}, "status": 503,
                     "host": "example.com", "retry_after": 5},
                )
            for bad_status in (True, False, "503", 503.0, 99, 600, None):
                with self.subTest(kind="bad-status-dropped", code=code, status=repr(bad_status)):
                    normalized = vendor_contract.normalize_result(
                        {"ok": False, "error": {"code": code}, "status": bad_status,
                         "host": "example.com"}
                    )
                    self.assertEqual(normalized, {"ok": False, "error": {"code": code}, "host": "example.com"})
            for bad_host in ("[example.com]", "[8.8.8.8]", "user@example.com",
                             "example.com:8080", "example.com/path", "exa mple.com",
                             "example.com\n", "\x01example.com", "", "a" * 254):
                with self.subTest(kind="bad-host-dropped", code=code, host=repr(bad_host)):
                    normalized = vendor_contract.normalize_result(
                        {"ok": False, "error": {"code": code}, "status": 503, "host": bad_host}
                    )
                    self.assertEqual(
                        normalized, {"ok": False, "error": {"code": code}, "status": 503}
                    )
                    self.assertNotIn("user", json.dumps(normalized))
            for good_host in ("example.com", "8.8.8.8", "::1", "[::1]", "[2001:db8::1]"):
                with self.subTest(kind="good-host-kept", code=code, host=good_host):
                    normalized = vendor_contract.normalize_result(
                        {"ok": False, "error": {"code": code}, "status": 503, "host": good_host}
                    )
                    self.assertEqual(
                        normalized,
                        {"ok": False, "error": {"code": code}, "status": 503, "host": good_host},
                    )
            for bad_retry in (True, False, 1.5, -1, -0.5, "abc", "5s", "99999999", "", None):
                with self.subTest(kind="bad-retry-dropped", code=code, retry=repr(bad_retry)):
                    normalized = vendor_contract.normalize_result(
                        {"ok": False, "error": {"code": code}, "status": 503,
                         "host": "example.com", "retry_after": bad_retry}
                    )
                    self.assertEqual(
                        normalized,
                        {"ok": False, "error": {"code": code}, "status": 503, "host": "example.com"},
                    )
        with self.subTest(kind="json-bracketed-dns-dropped"):
            def _op():
                return {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": 503,
                        "host": "[example.com]", "body": "body-secret-xyz"}

            handler = plugin_pkg._json_handler(_op, {"type": "object", "properties": {}})
            payload = json.loads(handler({}))
            self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": 503})
            self.assertNotIn("body-secret-xyz", json.dumps(payload))
        with self.subTest(kind="json-valid-diagnostics-kept"):
            def _op2():
                return {"ok": False, "error": {"code": "RATE_LIMITED"}, "status": 429,
                        "host": "example.com", "retry_after": "5"}

            handler = plugin_pkg._json_handler(_op2, {"type": "object", "properties": {}})
            payload = json.loads(handler({}))
            self.assertEqual(
                payload,
                {"ok": False, "error": {"code": "RATE_LIMITED"}, "status": 429,
                 "host": "example.com", "retry_after": 5},
            )
        self.assertNoNetwork()

    def test_hostile_mapping_failure_stays_sanitized_http_error(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        plugin_pkg = importlib.import_module(mod_name)
        from collections.abc import Mapping as _Mapping

        _SECRET = "secret-bearing-hostile-XYZ-123"

        class _HostileMapping(_Mapping):
            def __init__(self, data):
                self._data = dict(data)

            def __getitem__(self, key):
                if key in ("status", "host", "retry_after"):
                    raise RuntimeError(_SECRET + "-getitem-" + str(key))
                return self._data[key]

            def __contains__(self, key):
                if key in ("status", "host", "retry_after"):
                    raise RuntimeError(_SECRET + "-contains-" + str(key))
                return key in self._data

            def __iter__(self):
                return iter(self._data)

            def __len__(self):
                return len(self._data)

            def get(self, key, default=None):
                try:
                    return self._data[key]
                except KeyError:
                    return default

        hostile = _HostileMapping({"ok": False, "error": {"code": "HTTP_ERROR"}})
        try:
            normalized = vendor_contract.normalize_result(hostile)
        except Exception as exc:
            self.fail("normalize_result escaped hostile exception: %r" % (exc,))
        self.assertEqual(normalized, {"ok": False, "error": {"code": "HTTP_ERROR"}})
        self.assertNotIn("secret-bearing", json.dumps(normalized))
        self.assertNotIn("XYZ-123", json.dumps(normalized))

        @vendor_contract.result_operation
        def _hostile_op():
            return hostile

        try:
            wrapped = _hostile_op()
        except Exception as exc:
            self.fail("result_operation escaped hostile exception: %r" % (exc,))
        self.assertEqual(wrapped, {"ok": False, "error": {"code": "HTTP_ERROR"}})
        self.assertNotIn("secret-bearing", json.dumps(wrapped))
        self.assertNotIn("XYZ-123", json.dumps(wrapped))

        def _hostile_op2():
            return hostile

        handler = plugin_pkg._json_handler(_hostile_op2, {"type": "object", "properties": {}})
        payload = json.loads(handler({}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}})
        self.assertNotIn("secret-bearing", json.dumps(payload))
        self.assertNotIn("XYZ-123", json.dumps(payload))
        self.assertNoNetwork()

    def test_http_error_code_invalid_status_fail_closed_before_challenge(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        challenge = "<form id=\"challenge-form\"><input type=\"text\"></form>"
        ordinary = "<p>ordinary article hello</p>"
        for bad in (600, 0, -1, True, "403", None):
            with self.subTest(status=repr(bad)):
                self.assertEqual(vendor_contract.http_error_code(bad, challenge), "URL_BLOCKED")
        with self.subTest(kind="valid-challenge-provider"):
            for good in (200, 202, 403):
                with self.subTest(status=good):
                    self.assertEqual(vendor_contract.http_error_code(good, challenge), "PROVIDER_BLOCKED")
        with self.subTest(kind="valid-429-rate"):
            self.assertEqual(vendor_contract.http_error_code(429, ordinary), "RATE_LIMITED")
            self.assertEqual(vendor_contract.http_error_code(429, challenge), "RATE_LIMITED")
        with self.subTest(kind="valid-ordinary-http"):
            for code in (403, 404, 503):
                with self.subTest(status=code):
                    self.assertEqual(vendor_contract.http_error_code(code, ordinary), "HTTP_ERROR")
        with self.subTest(kind="valid-2xx-none"):
            for code in (200, 202):
                with self.subTest(status=code):
                    self.assertIsNone(vendor_contract.http_error_code(code, ordinary))
        with self.subTest(kind="valid-3xx-none"):
            for code in (301, 302):
                with self.subTest(status=code):
                    self.assertIsNone(vendor_contract.http_error_code(code, ordinary))
        self.assertNoNetwork()

    def test_failure_normalization_strips_unknown_fields(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        plugin_pkg = importlib.import_module(mod_name)
        with self.subTest(kind="normalize-strips"):
            raw = {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": 503,
                   "host": "example.com", "message": "msg-secret-xyz",
                   "results": [{"t": 1}], "body": "body-secret-xyz", "bogus": "x"}
            snapshot = copy.deepcopy(raw)
            normalized = vendor_contract.normalize_result(raw)
            self.assertEqual(
                normalized,
                {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": 503, "host": "example.com"},
            )
            self.assertNotIn("msg-secret-xyz", json.dumps(normalized))
            self.assertNotIn("body-secret-xyz", json.dumps(normalized))
            self.assertEqual(raw, snapshot)
        with self.subTest(kind="json-strips-and-suppresses-provenance"):
            def _op():
                return {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}, "status": 403,
                        "host": "example.com", "message": "msg-secret-xyz",
                        "results": [1], "body": "body-secret-xyz",
                        "source": "arbitrary-source", "transitions": ["x"], "truncated": True}

            handler = plugin_pkg._json_handler(_op, {"type": "object", "properties": {}})
            payload = json.loads(handler({}))
            self.assertEqual(
                payload,
                {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}, "status": 403, "host": "example.com"},
            )
            self.assertNotIn("msg-secret-xyz", json.dumps(payload))
            self.assertNotIn("arbitrary-source", json.dumps(payload))
        with self.subTest(kind="cycle-safe-and-unmutated"):
            cyclic = {}
            cyclic["code"] = cyclic
            self.assertEqual(vendor_contract.public_error_code(cyclic), "URL_BLOCKED")
            nested = {"error": cyclic}
            self.assertEqual(vendor_contract.public_error_code(nested), "URL_BLOCKED")
            raw_ok = {"ok": True, "data": [1, 2]}
            snapshot_ok = copy.deepcopy(raw_ok)
            self.assertEqual(vendor_contract.normalize_result(raw_ok)["ok"], True)
            self.assertEqual(raw_ok, snapshot_ok)
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
