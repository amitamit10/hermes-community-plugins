"""R4 F1 transport taxonomy: DNS failures map to DNS_ERROR (RED first).

Real guards only (vendored ssrf_guard/url_gate via a freshly built bundle);
fake resolvers raise socket.gaierror or return empty answers -- no real DNS.
Covers raw goat_extract/goat_crawl/goat_probe, shared normalization and the
registered JSON news vertical. DNS_ERROR stays distinct from policy
URL_BLOCKED; DNS failure on a PUBLIC redirect retains DNS_ERROR while
private/mixed-address targets stay REDIRECT_BLOCKED before connection.
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


class TransportDnsTaxonomyTests(OfflineRecordingTestCase):
    def test_dns_failures_are_dns_error_not_policy(self):
        import socket as _socket

        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        url_gate = importlib.import_module(mod_name + ".url_gate")
        wiring = importlib.import_module(mod_name + ".v3_wiring")
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        probe_handler = _wiring._registered_tools(mod)["goat_probe"]["handler"]
        url = "https://example.com/article"

        def _gai(address):
            return (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (address, 443))

        def raising_resolver(host, port, type=0):
            raise _socket.gaierror(-2, "dns-boom-secret-xyz")

        def dns_transport(requested_url):
            return url_gate.pinned_fetch(requested_url, resolver=raising_resolver)

        with self.subTest(kind="raw-extract"):
            raw = goat_tools.goat_extract(url, transport=dns_transport)
            self.assertEqual(raw, {"error": {"code": "DNS_ERROR"}})
            self.assertNotIn("dns-boom-secret-xyz", json.dumps(raw))
        with self.subTest(kind="raw-crawl"):
            raw = goat_tools.goat_crawl(url, transport=dns_transport)
            self.assertEqual(raw, {"error": {"code": "DNS_ERROR"}})
            self.assertNotIn("dns-boom-secret-xyz", json.dumps(raw))
        with self.subTest(kind="raw-probe"):
            raw = goat_tools.goat_probe(url, transport=dns_transport)
            self.assertEqual(raw, {"error": {"code": "DNS_ERROR"}})
            self.assertNotIn("dns-boom-secret-xyz", json.dumps(raw))
        with self.subTest(kind="json-probe"):
            with mock.patch.object(goat_tools, "pinned_fetch", dns_transport):
                payload = json.loads(probe_handler({"url": url}))
            self.assertEqual(payload, {"ok": False, "error": {"code": "DNS_ERROR"}})
            self.assertNotIn("dns-boom-secret-xyz", json.dumps(payload))
        with self.subTest(kind="shared-normalization"):
            self.assertEqual(vendor_contract.public_error_code(_socket.gaierror(-2, "dns-boom-secret-xyz")), "DNS_ERROR")
            normalized = vendor_contract.normalize_result(
                {"ok": False, "error": _socket.gaierror(-2, "dns-boom-secret-xyz"), "message": "dns-boom-secret-xyz", "results": [1]}
            )
            self.assertEqual(normalized, {"ok": False, "error": {"code": "DNS_ERROR"}})
            self.assertNotIn("dns-boom-secret-xyz", json.dumps(normalized))
        with self.subTest(kind="json-news-vertical"):
            deps = wiring.default_dependencies(_resolver=raising_resolver)
            tools = _wiring._registered_tools(mod, deps=deps)
            payload = json.loads(tools["goat_vertical_search"]["handler"]({"vertical": "news", "query": "synthetic offline check"}))
            self.assertIs(payload.get("ok"), False)
            self.assertEqual(payload.get("error"), {"code": "DNS_ERROR"})
            self.assertNotIn("dns-boom-secret-xyz", json.dumps(payload))
        def empty_resolver(host, port, type=0):
            return []

        def empty_transport(requested_url):
            return url_gate.pinned_fetch(requested_url, resolver=empty_resolver)

        with self.subTest(kind="empty-dns"):
            raw = goat_tools.goat_probe(url, transport=empty_transport)
            self.assertEqual(raw, {"error": {"code": "DNS_ERROR"}})
        with self.subTest(kind="malformed-dns-stays-policy"):
            def malformed_resolver(host, port, type=0):
                return ["not-an-address!!"]

            def malformed_transport(requested_url):
                return url_gate.pinned_fetch(requested_url, resolver=malformed_resolver)

            raw = goat_tools.goat_probe(url, transport=malformed_transport)
            self.assertEqual(raw, {"error": {"code": "URL_BLOCKED"}})
        for run in ("raw", "json"):
            with self.subTest(kind="public-redirect-dns", run=run):
                resolver_calls, made, closed = [], [], []

                def split_resolver(host, port, type=0):
                    resolver_calls.append((host, port))
                    if host == "example.com":
                        return [_gai("8.8.8.8")]
                    raise _socket.gaierror(-2, "dns-boom-secret-xyz")

                class RedirectConnection:
                    def __init__(self, hostname, address, timeout=10):
                        made.append((hostname, address))

                    def request(self, *args, **kwargs):
                        pass

                    def getresponse(self):
                        from types import SimpleNamespace

                        return SimpleNamespace(
                            status=302,
                            read=lambda _l: b"redirect-body-secret",
                            getheaders=lambda: [("Location", "https://other.example/next")],
                        )

                    def close(self):
                        closed.append(True)

                def redirect_transport(requested_url):
                    return url_gate.pinned_fetch(requested_url, resolver=split_resolver)

                with mock.patch.object(url_gate, "_PinnedHTTPSConnection", RedirectConnection):
                    if run == "raw":
                        res = goat_tools.goat_probe(url, transport=redirect_transport)
                        text = json.dumps(res)
                    else:
                        with mock.patch.object(goat_tools, "pinned_fetch", redirect_transport):
                            text = probe_handler({"url": url})
                        res = json.loads(text)
                if run == "raw":
                    self.assertEqual(res, {"error": {"code": "DNS_ERROR"}})
                else:
                    self.assertEqual(res, {"ok": False, "error": {"code": "DNS_ERROR"}})
                self.assertNotIn("dns-boom-secret-xyz", text)
                self.assertNotIn("redirect-body-secret", text)
                self.assertEqual(resolver_calls, [("example.com", 443), ("other.example", 443)])
                self.assertEqual(made, [("example.com", "8.8.8.8")])
                self.assertEqual(len(closed), 1)
        with self.subTest(kind="private-redirect-stays-policy"):
            made = []

            def public_resolver(host, port, type=0):
                return [_gai("8.8.8.8")]

            class PrivateRedirectConnection:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address))

                def request(self, *args, **kwargs):
                    pass

                def getresponse(self):
                    from types import SimpleNamespace

                    return SimpleNamespace(
                        status=302,
                        read=lambda _l: b"redirect-body-secret",
                        getheaders=lambda: [("Location", "https://127.0.0.1/private")],
                    )

                def close(self):
                    closed.append(True)

            closed = []

            def private_transport(requested_url):
                return url_gate.pinned_fetch(requested_url, resolver=public_resolver)

            with mock.patch.object(url_gate, "_PinnedHTTPSConnection", PrivateRedirectConnection):
                res = goat_tools.goat_probe(url, transport=private_transport)
            self.assertEqual(
                res,
                {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}, "status": 302, "host": "example.com"},
            )
            self.assertNotIn("127.0.0.1", json.dumps(res))
            self.assertEqual(made, [("example.com", "8.8.8.8")])
        with self.subTest(kind="mixed-redirect-stays-policy"):
            resolver_calls, made, closed = [], [], []

            def mixed_resolver(host, port, type=0):
                resolver_calls.append((host, port))
                if host == "example.com":
                    return [_gai("8.8.8.8")]
                return [_gai("8.8.8.8"), _gai("127.0.0.1")]

            class MixedRedirectConnection:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address))

                def request(self, *args, **kwargs):
                    pass

                def getresponse(self):
                    from types import SimpleNamespace

                    return SimpleNamespace(
                        status=302,
                        read=lambda _l: b"redirect-body-secret",
                        getheaders=lambda: [("Location", "https://other.example/next")],
                    )

                def close(self):
                    closed.append(True)

            def mixed_transport(requested_url):
                return url_gate.pinned_fetch(requested_url, resolver=mixed_resolver)

            with mock.patch.object(url_gate, "_PinnedHTTPSConnection", MixedRedirectConnection):
                res = goat_tools.goat_probe(url, transport=mixed_transport)
            self.assertEqual(
                res,
                {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}, "status": 302, "host": "example.com"},
            )
            self.assertNotIn("127.0.0.1", json.dumps(res))
            self.assertEqual(made, [("example.com", "8.8.8.8")])
            self.assertEqual(len(closed), 1)
        self.assertNoNetwork()


class TransportTimeoutTaxonomyTests(OfflineRecordingTestCase):
    def test_timeout_failures_are_upstream_timeout_not_policy(self):
        import socket as _socket

        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        url_gate = importlib.import_module(mod_name + ".url_gate")
        wiring = importlib.import_module(mod_name + ".v3_wiring")
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        vendor_verticals = importlib.import_module(mod_name + "._goat_v3_vendor.free_verticals")
        probe_handler = _wiring._registered_tools(mod)["goat_probe"]["handler"]
        url = "https://example.com/article"

        def _gai(address):
            return (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (address, 443))

        def public_resolver(host, port, type=0):
            return [_gai("8.8.8.8")]

        def timeout_transport(stage):
            def _transport(requested_url):
                return url_gate.pinned_fetch(requested_url, resolver=public_resolver)
            return _transport, stage

        def make_timeout_connection(stage, made, requested, closed):
            class TimeoutConnection:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address, timeout))

                def request(self, *args, **kwargs):
                    requested.append("request")
                    if stage == "request":
                        raise TimeoutError("timeout-boom-secret-xyz")

                def getresponse(self):
                    requested.append("getresponse")
                    if stage == "getresponse":
                        raise _socket.timeout("timeout-boom-secret-xyz")
                    from types import SimpleNamespace

                    class BoomReader:
                        def read(self, _n):
                            raise TimeoutError("timeout-boom-secret-xyz")

                        def getheaders(self):
                            return []

                    if stage == "read":
                        return SimpleNamespace(status=200, read=BoomReader().read, getheaders=lambda: [])
                    return SimpleNamespace(status=200, read=lambda _n: b"ok-body", getheaders=lambda: [])

                def close(self):
                    closed.append(True)

            return TimeoutConnection

        # --- TimeoutError/socket.timeout at request/getresponse/read stages ---
        for stage in ("request", "getresponse", "read"):
            with self.subTest(kind="raw-probe-timeout", stage=stage):
                made, requested, closed = [], [], []
                transport, _ = timeout_transport(stage)

                def _t(u, _tr=transport):
                    return _tr(u)

                with mock.patch.object(url_gate, "_PinnedHTTPSConnection", make_timeout_connection(stage, made, requested, closed)):
                    raw = goat_tools.goat_probe(url, transport=_t)
                    text = json.dumps(raw)
                self.assertEqual(raw, {"error": {"code": "UPSTREAM_TIMEOUT"}})
                self.assertNotIn("timeout-boom-secret-xyz", text)
                self.assertEqual(made, [("example.com", "8.8.8.8", 10)])
                self.assertEqual(len(closed), 1)
            with self.subTest(kind="json-probe-timeout", stage=stage):
                made, requested, closed = [], [], []
                transport, _ = timeout_transport(stage)
                with mock.patch.object(url_gate, "_PinnedHTTPSConnection", make_timeout_connection(stage, made, requested, closed)):
                    with mock.patch.object(goat_tools, "pinned_fetch", transport):
                        payload = json.loads(probe_handler({"url": url}))
                self.assertEqual(payload, {"ok": False, "error": {"code": "UPSTREAM_TIMEOUT"}})
                self.assertNotIn("timeout-boom-secret-xyz", json.dumps(payload))
        # --- typed literal survives free_verticals + shared normalization ---
        with self.subTest(kind="shared-normalization"):
            self.assertEqual(vendor_contract.public_error_code(TimeoutError("timeout-boom-secret-xyz")), "UPSTREAM_TIMEOUT")
            self.assertEqual(vendor_verticals.map_error(TimeoutError("timeout-boom-secret-xyz")), "UPSTREAM_TIMEOUT")
            normalized = vendor_contract.normalize_result(
                {"ok": False, "error": TimeoutError("timeout-boom-secret-xyz"), "message": "timeout-boom-secret-xyz"}
            )
            self.assertEqual(normalized, {"ok": False, "error": {"code": "UPSTREAM_TIMEOUT"}})
            self.assertNotIn("timeout-boom-secret-xyz", json.dumps(normalized))
            self.assertEqual(vendor_contract.public_error_code(RuntimeError("boom-secret")), "URL_BLOCKED")
            self.assertEqual(vendor_verticals.map_error(ValueError("boom-secret")), "URL_BLOCKED")
            self.assertEqual(vendor_verticals.map_error(None), "MISSING_CONFIG")
        # --- registered DEFAULT news vertical (GDELT) via real default_dependencies ---
        with self.subTest(kind="json-news-vertical-timeout"):
            made, closed = [], []

            class NewsTimeoutConnection:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address, timeout))

                def request(self, *args, **kwargs):
                    raise TimeoutError("timeout-boom-secret-xyz")

                def getresponse(self):
                    raise AssertionError("must not reach getresponse")

                def close(self):
                    closed.append(True)

            def timeout_factory(hostname, address, timeout=10):
                return NewsTimeoutConnection(hostname, address, timeout=timeout)

            deps = wiring.default_dependencies(_resolver=public_resolver, _connection_factory=timeout_factory)
            tools = _wiring._registered_tools(mod, deps=deps)
            payload = json.loads(tools["goat_vertical_search"]["handler"]({"vertical": "news", "query": "synthetic offline check"}))
            self.assertIs(payload.get("ok"), False)
            self.assertEqual(payload.get("error"), {"code": "UPSTREAM_TIMEOUT"})
            self.assertNotIn("timeout-boom-secret-xyz", json.dumps(payload))
            self.assertEqual(made, [("api.gdeltproject.org", "8.8.8.8", 10)])
            self.assertEqual(len(closed), 1)
        # --- timeout after a PUBLIC redirect retains UPSTREAM_TIMEOUT ---
        with self.subTest(kind="public-redirect-timeout"):
            resolver_calls, made, closed, calls = [], [], [], []

            def split_resolver(host, port, type=0):
                resolver_calls.append((host, port))
                return [_gai("8.8.8.8")]

            class RedirectTimeoutConnection:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address))
                    calls.append(hostname)

                def request(self, *args, **kwargs):
                    if len(calls) > 1:
                        raise TimeoutError("timeout-boom-secret-xyz")

                def getresponse(self):
                    from types import SimpleNamespace

                    if len(calls) == 1:
                        return SimpleNamespace(
                            status=302,
                            read=lambda _l: b"redirect-body-secret",
                            getheaders=lambda: [("Location", "https://other.example/next")],
                        )
                    raise AssertionError("must not reach second getresponse")

                def close(self):
                    closed.append(True)

            def redirect_transport(requested_url):
                return url_gate.pinned_fetch(requested_url, resolver=split_resolver)

            with mock.patch.object(url_gate, "_PinnedHTTPSConnection", RedirectTimeoutConnection):
                res = goat_tools.goat_probe(url, transport=redirect_transport)
            self.assertEqual(res, {"error": {"code": "UPSTREAM_TIMEOUT"}})
            self.assertNotIn("timeout-boom-secret-xyz", json.dumps(res))
            self.assertEqual(resolver_calls, [("example.com", 443), ("other.example", 443)])
            self.assertEqual(made, [("example.com", "8.8.8.8"), ("other.example", "8.8.8.8")])
            self.assertEqual(len(closed), 2)
        # --- arbitrary errors stay legacy policy ---
        with self.subTest(kind="arbitrary-stays-policy"):
            def _boom(_u):
                raise RuntimeError("boom-secret-xyz")

            raw = goat_tools.goat_probe(url, transport=_boom)
            self.assertEqual(raw, {"error": {"code": "URL_BLOCKED"}})
            self.assertNotIn("boom-secret-xyz", json.dumps(raw))
        self.assertNoNetwork()

class TransportConnectionTaxonomyTests(OfflineRecordingTestCase):
    def test_connection_failures_are_connection_error_not_policy(self):
        import http.client as _http_client
        import socket as _socket
        import ssl as _ssl

        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        url_gate = importlib.import_module(mod_name + ".url_gate")
        wiring = importlib.import_module(mod_name + ".v3_wiring")
        vendor_contract = importlib.import_module(mod_name + "._goat_v3_vendor.result_contract")
        vendor_guard = importlib.import_module(mod_name + "._goat_v3_vendor.ssrf_guard")
        vendor_verticals = importlib.import_module(mod_name + "._goat_v3_vendor.free_verticals")
        probe_handler = _wiring._registered_tools(mod)["goat_probe"]["handler"]
        url = "https://example.com/article"

        def _gai(address):
            return (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (address, 443))

        def public_resolver(host, port, type=0):
            return [_gai("8.8.8.8")]

        failures = {
            "refused": ConnectionRefusedError("conn-boom-secret-xyz"),
            "tls": _ssl.SSLError("conn-boom-secret-xyz"),
            "protocol": _http_client.RemoteDisconnected("conn-boom-secret-xyz"),
        }
        for kind, failure in failures.items():
            with self.subTest(stage="request", kind=kind):
                made, closed = [], []

                class RefusingConnection:
                    def __init__(self, hostname, address, timeout=10):
                        made.append((hostname, address, timeout))

                    def request(self, *args, **kwargs):
                        raise failure

                    def getresponse(self):
                        raise AssertionError("must not reach getresponse")

                    def close(self):
                        closed.append(True)

                def refusing_transport(requested_url):
                    return url_gate.pinned_fetch(requested_url, resolver=public_resolver)

                with mock.patch.object(url_gate, "_PinnedHTTPSConnection", RefusingConnection):
                    raw = goat_tools.goat_probe(url, transport=refusing_transport)
                    self.assertEqual(raw, {"error": {"code": "CONNECTION_ERROR"}})
                    self.assertNotIn("conn-boom-secret-xyz", json.dumps(raw))
                with mock.patch.object(url_gate, "_PinnedHTTPSConnection", RefusingConnection):
                    raw_extract = goat_tools.goat_extract(url, transport=refusing_transport)
                    self.assertEqual(raw_extract, {"error": {"code": "CONNECTION_ERROR"}})
                    self.assertNotIn("conn-boom-secret-xyz", json.dumps(raw_extract))
                with mock.patch.object(url_gate, "_PinnedHTTPSConnection", RefusingConnection):
                    with mock.patch.object(goat_tools, "pinned_fetch", refusing_transport):
                        payload = json.loads(probe_handler({"url": url}))
                    self.assertEqual(payload, {"ok": False, "error": {"code": "CONNECTION_ERROR"}})
                    self.assertNotIn("conn-boom-secret-xyz", json.dumps(payload))
                self.assertEqual(made, [("example.com", "8.8.8.8", 10)] * 3)
                self.assertEqual(len(closed), 3)
        with self.subTest(kind="shared-normalization"):
            self.assertEqual(vendor_contract.public_error_code(OSError("dns")), "CONNECTION_ERROR")
            self.assertEqual(vendor_contract.public_error_code(ConnectionRefusedError("x")), "CONNECTION_ERROR")
            self.assertEqual(vendor_contract.public_error_code(_ssl.SSLError("x")), "CONNECTION_ERROR")
            self.assertEqual(vendor_contract.public_error_code(_http_client.RemoteDisconnected("x")), "CONNECTION_ERROR")
            self.assertEqual(vendor_verticals.map_error(OSError("dns")), "CONNECTION_ERROR")
            normalized = vendor_contract.normalize_result(
                {"ok": False, "error": ConnectionRefusedError("conn-boom-secret-xyz"), "message": "conn-boom-secret-xyz"}
            )
            self.assertEqual(normalized, {"ok": False, "error": {"code": "CONNECTION_ERROR"}})
            self.assertNotIn("conn-boom-secret-xyz", json.dumps(normalized))
            # policy-coded failures keep policy precedence over transport types
            self.assertEqual(vendor_contract.public_error_code(vendor_guard.GuardError(vendor_guard.PRIVATE_HOST)), "URL_BLOCKED")
            self.assertEqual(vendor_verticals.map_error(vendor_guard.GuardError(vendor_guard.PRIVATE_HOST)), "URL_BLOCKED")
            # earlier taxonomy literals stay distinct
            self.assertEqual(vendor_contract.public_error_code(_socket.gaierror(-2, "x")), "DNS_ERROR")
            self.assertEqual(vendor_contract.public_error_code(TimeoutError("x")), "UPSTREAM_TIMEOUT")
        with self.subTest(kind="json-news-vertical-connection"):
            def refusing_factory(hostname, address, timeout=10):
                raise ConnectionRefusedError("conn-boom-secret-xyz")

            deps = wiring.default_dependencies(_resolver=public_resolver, _connection_factory=refusing_factory)
            tools = _wiring._registered_tools(mod, deps=deps)
            payload = json.loads(tools["goat_vertical_search"]["handler"]({"vertical": "news", "query": "synthetic offline check"}))
            self.assertIs(payload.get("ok"), False)
            self.assertEqual(payload.get("error"), {"code": "CONNECTION_ERROR"})
            self.assertNotIn("conn-boom-secret-xyz", json.dumps(payload))
        with self.subTest(kind="public-redirect-connection"):
            resolver_calls, made, closed, calls = [], [], [], []

            def split_resolver(host, port, type=0):
                resolver_calls.append((host, port))
                return [_gai("8.8.8.8")]

            class RedirectRefusingConnection:
                def __init__(self, hostname, address, timeout=10):
                    made.append((hostname, address))
                    calls.append(hostname)

                def request(self, *args, **kwargs):
                    if len(calls) > 1:
                        raise ConnectionRefusedError("conn-boom-secret-xyz")

                def getresponse(self):
                    from types import SimpleNamespace

                    if len(calls) == 1:
                        return SimpleNamespace(
                            status=302,
                            read=lambda _l: b"redirect-body-secret",
                            getheaders=lambda: [("Location", "https://other.example/next")],
                        )
                    raise AssertionError("must not reach second getresponse")

                def close(self):
                    closed.append(True)

            def redirect_transport(requested_url):
                return url_gate.pinned_fetch(requested_url, resolver=split_resolver)

            with mock.patch.object(url_gate, "_PinnedHTTPSConnection", RedirectRefusingConnection):
                res = goat_tools.goat_probe(url, transport=redirect_transport)
            self.assertEqual(res, {"error": {"code": "CONNECTION_ERROR"}})
            self.assertNotIn("conn-boom-secret-xyz", json.dumps(res))
            self.assertEqual(resolver_calls, [("example.com", 443), ("other.example", 443)])
            self.assertEqual(made, [("example.com", "8.8.8.8"), ("other.example", "8.8.8.8")])
            self.assertEqual(len(closed), 2)
        self.assertNoNetwork()


class ResolverStageTaxonomyEdgeTests(OfflineRecordingTestCase):
    def test_resolver_timeout_and_oserror_taxonomy_in_both_guards(self):
        import importlib.util as _ilu
        import socket as _socket
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        url_gate = importlib.import_module(mod_name + ".url_gate")
        pack_path = Path(__file__).resolve().parents[2] / "adapters" / "ssrf_guard.py"
        spec = _ilu.spec_from_file_location("edge_pack_ssrf_guard", str(pack_path))
        pack_guard = _ilu.module_from_spec(spec)
        spec.loader.exec_module(pack_guard)
        url = "https://example.com/article"
        def _gai(addr):
            return (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (addr, 443))
        def _code(mod, fn, *args, **kwargs):
            try:
                fn(*args, **kwargs)
                return ("ok", None)
            except Exception as exc:
                return ("err", getattr(exc, "code", None))
        # Direct resolver stage in BOTH guards.
        for mod, label in ((pack_guard, "pack"), (url_gate, "plugin")):
            with self.subTest(guard=label, stage="timeout"):
                kind, code = _code(mod, mod.resolve_and_validate, "example.com",
                                   resolver=lambda h, p, type=0: (_ for _ in ()).throw(TimeoutError("edge-timeout-secret-xyz")))
                self.assertEqual((kind, code), ("err", "UPSTREAM_TIMEOUT"))
            for name, exc in (("oserror", OSError("edge-os-secret-xyz")),
                              ("herror", _socket.herror(1, "edge-herror-secret-xyz"))):
                with self.subTest(guard=label, stage=name):
                    def _raising(h, p, type=0, _e=exc):
                        raise _e
                    kind, code = _code(mod, mod.resolve_and_validate, "example.com", resolver=_raising)
                    self.assertEqual((kind, code), ("err", "DNS_ERROR"))
        # After a PUBLIC redirect the taxonomy is preserved (not REDIRECT_BLOCKED).
        for mod, label in ((pack_guard, "pack"), (url_gate, "plugin")):
            for name, exc, expected in (("timeout", TimeoutError("edge-timeout-secret-xyz"), "UPSTREAM_TIMEOUT"),
                                        ("oserror", OSError("edge-os-secret-xyz"), "DNS_ERROR"),
                                        ("herror", _socket.herror(1, "edge-herror-secret-xyz"), "DNS_ERROR")):
                with self.subTest(guard=label, redirect=name):
                    def _split(h, p, type=0, _e=exc):
                        if h == "example.com":
                            return [_gai("8.8.8.8")]
                        raise _e
                    class _Redir:
                        def __init__(self, hostname, address, timeout=10):
                            pass
                        def request(self, *a, **k):
                            pass
                        def getresponse(self):
                            from types import SimpleNamespace
                            return SimpleNamespace(status=302, read=lambda _l: b"redirect-body-secret",
                                                   getheaders=lambda: [("Location", "https://other.example/next")])
                        def close(self):
                            pass
                    orig = mod._PinnedHTTPSConnection
                    mod._PinnedHTTPSConnection = _Redir
                    try:
                        kind, code = _code(mod, mod.pinned_fetch, url, resolver=_split)
                    finally:
                        mod._PinnedHTTPSConnection = orig
                    self.assertEqual((kind, code), ("err", expected))
        # Private/mixed policy stays block on BOTH guards (no weakening).
        for mod, label in ((pack_guard, "pack"), (url_gate, "plugin")):
            with self.subTest(guard=label, policy="private-direct"):
                kind, code = _code(mod, mod.resolve_and_validate, "example.com",
                                   resolver=lambda h, p, type=0: [_gai("127.0.0.1")])
                self.assertEqual((kind, code), ("err", "PRIVATE_HOST"))
            with self.subTest(guard=label, policy="mixed-direct"):
                kind, code = _code(mod, mod.resolve_and_validate, "example.com",
                                   resolver=lambda h, p, type=0: [_gai("8.8.8.8"), _gai("127.0.0.1")])
                self.assertEqual((kind, code), ("err", "PRIVATE_HOST"))
            with self.subTest(guard=label, policy="private-redirect"):
                class _Priv:
                    def __init__(self, hostname, address, timeout=10):
                        pass
                    def request(self, *a, **k):
                        pass
                    def getresponse(self):
                        from types import SimpleNamespace
                        return SimpleNamespace(status=302, read=lambda _l: b"x",
                                               getheaders=lambda: [("Location", "https://127.0.0.1/private")])
                    def close(self):
                        pass
                orig = mod._PinnedHTTPSConnection
                mod._PinnedHTTPSConnection = _Priv
                try:
                    kind, code = _code(mod, mod.pinned_fetch, url,
                                       resolver=lambda h, p, type=0: [_gai("8.8.8.8")])
                finally:
                    mod._PinnedHTTPSConnection = orig
                self.assertEqual((kind, code), ("err", "REDIRECT_BLOCKED"))
        self.assertNoNetwork()

if __name__ == "__main__":
    unittest.main()
