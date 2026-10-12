"""R4 F4 shared answer support: INSUFFICIENT_EVIDENCE preserved code-only.

Real shared public_error_code + normalize_result and the built actual
_json_handler from a freshly built bundle. No answer behavior implemented.
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


class TransportAnswerSupportTests(OfflineRecordingTestCase):
    def test_insufficient_evidence_literal_preserved_code_only(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        plugin_pkg = importlib.import_module(mod_name)
        with self.subTest(kind="shared-public-code"):
            self.assertEqual(vendor_contract.public_error_code("INSUFFICIENT_EVIDENCE"), "INSUFFICIENT_EVIDENCE")
            self.assertEqual(
                vendor_contract.public_error_code({"code": "INSUFFICIENT_EVIDENCE"}),
                "INSUFFICIENT_EVIDENCE",
            )
        with self.subTest(kind="shared-normalization"):
            normalized = vendor_contract.normalize_result(
                {
                    "ok": False,
                    "error": {"code": "INSUFFICIENT_EVIDENCE"},
                    "message": "evidence-boom-secret-xyz",
                    "results": [{"title": "t"}],
                    "status": 200,
                    "host": "example.com",
                }
            )
            self.assertEqual(normalized, {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}})
            self.assertNotIn("evidence-boom-secret-xyz", json.dumps(normalized))
        with self.subTest(kind="json-handler"):
            def _op():
                return {
                    "ok": False,
                    "error": {"code": "INSUFFICIENT_EVIDENCE"},
                    "message": "evidence-boom-secret-xyz",
                    "results": [{"title": "t"}],
                }

            handler = plugin_pkg._json_handler(_op, {"type": "object", "properties": {}})
            payload = json.loads(handler({}))
            self.assertEqual(payload, {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}})
            self.assertNotIn("evidence-boom-secret-xyz", json.dumps(payload))
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
