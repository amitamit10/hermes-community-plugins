"""V4 post-QA offline real-guard contract for legacy extract/crawl/probe.

Real built bundle + real legacy url_gate.pinned_fetch with real check_url,
resolve_and_validate, serializers and classifiers. Only seams are the fake
DNS resolver via the default socket.getaddrinfo and the fake factory at the
built legacy url_gate._PinnedHTTPSConnection constructor. Real URL/DNS
validation and redirect handling run unchanged. Offline only, no live network.

Covers B3 JSON-data discrimination, B4 empty-body handling, structural
HTML challenge positives/negatives, Content-Type irrelevance, ordinary /
rate-limit / invalid-status mapping, native DNS/transport errors, private
literals, private/mixed DNS rejection before connect, and unsafe-redirect
blocking. Production is frozen; failures must be reported, not fixed here.

Genuine SSRF proof lives here. The injected-guard-error cases in
test_r4_public_http_contract.py test only public error mapping, not actual
rejection.
"""

import http.client
import importlib
import json
import socket
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import test_plugin_wiring as _wiring  # noqa: E402  (established wiring fixture imports only)

PINNED_IP = "93.184.216.34"
READ_BOUND = 1048577
EXPECTED_ACCEPT = "text/html,text/plain,application/json;q=0.9,*/*;q=0.5"

FORM_MARK = "<form id='challenge-form'>"
TURN_MARK = "<div class='cf-turnstile'>"
SCRIPT_MARK = "<script src='/cdn-cgi/challenge-platform/h.js'></script>"
TITLE_MARK = "<title>Just a moment...</title>"


def _json_object_body(sentinel):
    return "  " + json.dumps({"article": sentinel + " " + FORM_MARK + " " + TURN_MARK + " " + SCRIPT_MARK + " " + TITLE_MARK, "title": "Readable title"}) + "\n"


def _json_array_body(sentinel):
    return "  " + json.dumps([sentinel + " " + FORM_MARK + " " + TURN_MARK + " " + SCRIPT_MARK + " " + TITLE_MARK]) + "\n"


def _json_string_body(sentinel):
    return "  " + json.dumps(sentinel + " " + FORM_MARK + " " + TURN_MARK + " " + SCRIPT_MARK + " " + TITLE_MARK) + "\n"


def _public_answer(ip=PINNED_IP):
    if ":" in ip:
        return (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 443, 0, 0))
    return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))


def _private_v4_answer(ip="10.0.0.5"):
    return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))


def _private_v6_answer(ip="fd00::1"):
    return (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 443, 0, 0))


class RealGuardHarness(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.resolver_calls = []
        self.factory_calls = []
        self.request_calls = []
        self.read_bounds = []
        self.close_calls = []
        self.outside_attempts = []
        self.audit_attempts = []
        self._current_status = 200
        self._current_body = b""
        self._response_headers = [("Content-Type", "application/json")]
        self._dns_map = {}
        self._dns_errors = {}
        self._factory_error = None
        self._request_error = None
        self._response_error = None
        self._read_error = None
        self._expected_host = None
        self._audit_active = True

        self._saved = {}
        for name in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo", "create_connection"):
            self._saved[name] = getattr(socket, name, None)
        self._saved_sock = {}
        for name in ("connect", "connect_ex", "sendto", "sendmsg", "__new__"):
            self._saved_sock[name] = getattr(socket.socket, name, None)

        test = self

        def fake_resolver(host, port, *args, **kwargs):
            if kwargs.get("type") is not None:
                typ = kwargs.get("type")
            elif args:
                typ = args[0]
            else:
                typ = None
            test.resolver_calls.append((host, port, typ))
            assert port == 443, port
            assert typ == socket.SOCK_STREAM, typ
            if host in test._dns_errors:
                raise test._dns_errors[host]
            if host in test._dns_map:
                return test._dns_map[host]
            assert host == test._expected_host, (host, test._expected_host)
            assert test._expected_host is not None
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PINNED_IP, 443))]

        self._fake_resolver = fake_resolver
        socket.getaddrinfo = fake_resolver

        def _deny(name):
            def _denied(*a, **k):
                test.outside_attempts.append((name, a, k))
                raise AssertionError("egress denied: %s" % name)
            return _denied

        for name in ("gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo", "create_connection"):
            setattr(socket, name, _deny("socket." + name))
        for name in ("connect", "connect_ex", "sendto", "sendmsg"):
            if hasattr(socket.socket, name):
                setattr(socket.socket, name, _deny("socket.socket." + name))

        def _hook(event, args):
            if not test._audit_active:
                return
            if event == "socket.__new__" or event == "socket.connect" or event.startswith("socket.get") or event in ("socket.bind", "socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex", "socket.getnameinfo"):
                test.audit_attempts.append((event, args))
                raise RuntimeError("egress denied: %s" % event)

        sys.addaudithook(_hook)
        self.addCleanup(self._restore_and_assert_no_egress)

    def _restore_and_assert_no_egress(self):
        self._audit_active = False
        for name, fn in self._saved.items():
            if fn is None:
                try:
                    delattr(socket, name)
                except AttributeError:
                    pass
            else:
                setattr(socket, name, fn)
        for name, fn in self._saved_sock.items():
            if fn is None:
                continue
            try:
                setattr(socket.socket, name, fn)
            except Exception:
                pass
        self.assertEqual(self.outside_attempts, [])
        self.assertEqual(self.audit_attempts, [])

    def _load_real_tools(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        url_gate = importlib.import_module(mod_name + ".url_gate")
        self.assertIs(goat_tools.pinned_fetch, url_gate.pinned_fetch)
        test = self

        class FakeResponse:
            def __init__(self, status, body, headers):
                self.status = status
                self._body = body
                self._headers = headers

            def read(self, bound):
                test.read_bounds.append(bound)
                if test._read_error is not None:
                    raise test._read_error
                return self._body

            def getheaders(self):
                return list(self._headers)

        class FakeConnection:
            def __init__(self, hostname, address, timeout=10):
                test.factory_calls.append((hostname, address, timeout))
                if test._factory_error is not None:
                    raise test._factory_error
                assert address == PINNED_IP, address
                assert timeout == 10, timeout
                self.hostname = hostname
                self._path = ""

            def request(self, method, path, headers=None):
                if test._request_error is not None:
                    test.request_calls.append((method, self.hostname, path, dict(headers or {})))
                    raise test._request_error
                test.request_calls.append((method, self.hostname, path, dict(headers or {})))
                assert method == "GET", method
                hdrs = headers or {}
                assert hdrs.get("Host") == self.hostname, hdrs
                assert hdrs.get("Accept") == EXPECTED_ACCEPT, hdrs
                assert hdrs.get("Connection") == "close", hdrs
                for key in hdrs:
                    assert "proxy" not in key.lower(), hdrs
                assert path.startswith("/"), path
                self._path = path

            def getresponse(self):
                if test._response_error is not None:
                    raise test._response_error
                return FakeResponse(test._current_status, test._current_body, list(test._response_headers))

            def close(self):
                test.close_calls.append(True)

        orig = url_gate._PinnedHTTPSConnection
        url_gate._PinnedHTTPSConnection = FakeConnection
        self.addCleanup(setattr, url_gate, "_PinnedHTTPSConnection", orig)
        tools = _wiring._registered_tools(mod)
        # Import/default register must not touch network; reset must not conceal it.
        self.assertEqual(self.resolver_calls, [])
        self.assertEqual(self.factory_calls, [])
        self.assertEqual(self.request_calls, [])
        self.assertEqual(self.read_bounds, [])
        self.assertEqual(self.close_calls, [])
        return mod, tools

    def _reset_counts(self):
        del self.resolver_calls[:]
        del self.factory_calls[:]
        del self.request_calls[:]
        del self.read_bounds[:]
        del self.close_calls[:]

    def _assert_transport_counts(self, expected_path):
        self.assertEqual(len(self.resolver_calls), 1)
        self.assertEqual(len(self.factory_calls), 1)
        self.assertEqual(len(self.request_calls), 1)
        self.assertEqual(len(self.read_bounds), 1)
        self.assertEqual(len(self.close_calls), 1)
        host, port, typ = self.resolver_calls[0]
        self.assertEqual(host, self._expected_host)
        self.assertEqual(port, 443)
        self.assertEqual(typ, socket.SOCK_STREAM)
        hostname, address, timeout = self.factory_calls[0]
        self.assertEqual(hostname, self._expected_host)
        self.assertEqual(address, PINNED_IP)
        self.assertEqual(timeout, 10)
        method, req_host, path, headers = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(req_host, self._expected_host)
        self.assertEqual(path, expected_path)
        self.assertEqual(headers.get("Host"), self._expected_host)
        self.assertEqual(headers.get("Accept"), EXPECTED_ACCEPT)
        self.assertEqual(headers.get("Connection"), "close")
        self.assertEqual(self.read_bounds[0], READ_BOUND)

    def _assert_first_fetch_pinned(self, expected_host, expected_path):
        self.assertEqual(len(self.factory_calls), 1)
        self.assertEqual(len(self.request_calls), 1)
        self.assertEqual(len(self.read_bounds), 1)
        self.assertEqual(len(self.close_calls), 1)
        hostname, address, timeout = self.factory_calls[0]
        self.assertEqual(hostname, expected_host)
        self.assertEqual(address, PINNED_IP)
        self.assertEqual(timeout, 10)
        method, req_host, path, headers = self.request_calls[0]
        self.assertEqual(method, "GET")
        self.assertEqual(req_host, expected_host)
        self.assertEqual(path, expected_path)
        self.assertEqual(headers.get("Host"), expected_host)
        self.assertEqual(headers.get("Accept"), EXPECTED_ACCEPT)
        self.assertEqual(headers.get("Connection"), "close")
        for key in headers:
            self.assertNotIn("proxy", key.lower())
        self.assertEqual(self.read_bounds[0], READ_BOUND)

    def _assert_zero_factory(self):
        self.assertEqual(self.factory_calls, [])
        self.assertEqual(self.request_calls, [])
        self.assertEqual(self.read_bounds, [])
        self.assertEqual(self.close_calls, [])


class ExtractRealGuardTests(RealGuardHarness):
    def test_goat_extract_json_data_not_blocked(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_extract"]["handler"]
        url = "https://example.com/article"
        shapes = (
            ("object", _json_object_body),
            ("array", _json_array_body),
            ("string", _json_string_body),
        )
        for shape, maker in shapes:
            for status in (200, 202, 403):
                with self.subTest(shape=shape, status=status):
                    sentinel = "SENTINEL-EXTRACT-%s-READABLE-%d" % (shape.upper(), status)
                    self._current_status = status
                    self._current_body = maker(sentinel).encode("utf-8")
                    self._reset_counts()
                    payload = json.loads(handler({"url": url}))
                    self._assert_transport_counts("/article")
                    if status in (200, 202):
                        self.assertTrue(payload.get("ok"), payload)
                        self.assertEqual(payload.get("url"), url)
                        self.assertEqual(payload.get("status"), status)
                        self.assertIn(sentinel, payload.get("text", ""))
                        self.assertTrue(payload.get("text", ""))
                        self.assertIs(payload.get("truncated"), False)
                    else:
                        self.assertIs(payload.get("ok"), False)
                        self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
                        self.assertEqual(payload.get("status"), 403)
                        dumped = json.dumps(payload)
                        self.assertNotIn(sentinel, dumped)
                        self.assertNotIn("challenge-form", dumped)
                        self.assertNotIn("cf-turnstile", dumped)
                        self.assertNotIn("<form", dumped)


class CrawlRealGuardTests(RealGuardHarness):
    def test_goat_crawl_json_data_not_blocked(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_crawl"]["handler"]
        url = "https://example.com/start"
        shapes = (
            ("object", _json_object_body),
            ("array", _json_array_body),
            ("string", _json_string_body),
        )
        for shape, maker in shapes:
            for status in (200, 202, 403):
                with self.subTest(shape=shape, status=status):
                    sentinel = "SENTINEL-CRAWL-%s-READABLE-%d" % (shape.upper(), status)
                    self._current_status = status
                    self._current_body = maker(sentinel).encode("utf-8")
                    self._reset_counts()
                    payload = json.loads(handler({"url": url, "max_depth": 0, "max_pages": 1}))
                    self._assert_transport_counts("/start")
                    if status in (200, 202):
                        self.assertTrue(payload.get("ok"), payload)
                        pages = payload.get("pages", [])
                        self.assertEqual(len(pages), 1)
                        self.assertEqual(pages[0].get("url"), url)
                        self.assertEqual(pages[0].get("status"), status)
                        self.assertIn(sentinel, pages[0].get("text", ""))
                        self.assertTrue(pages[0].get("text", ""))
                        self.assertIs(pages[0].get("truncated"), False)
                    else:
                        self.assertIs(payload.get("ok"), False)
                        self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
                        self.assertEqual(payload.get("status"), 403)
                        dumped = json.dumps(payload)
                        self.assertNotIn(sentinel, dumped)
                        self.assertNotIn("challenge-form", dumped)
                        self.assertNotIn("cf-turnstile", dumped)
                        self.assertNotIn("<form", dumped)


class ProbeRealGuardTests(RealGuardHarness):
    def test_goat_probe_json_data_not_blocked(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_probe"]["handler"]
        url = "https://example.com/probe"
        shapes = (
            ("object", _json_object_body),
            ("array", _json_array_body),
            ("string", _json_string_body),
        )
        for shape, maker in shapes:
            for status in (200, 202, 403):
                with self.subTest(shape=shape, status=status):
                    sentinel = "SENTINEL-PROBE-%s-READABLE-%d" % (shape.upper(), status)
                    self._current_status = status
                    self._current_body = maker(sentinel).encode("utf-8")
                    self._reset_counts()
                    payload = json.loads(handler({"url": url}))
                    self._assert_transport_counts("/probe")
                    if status in (200, 202):
                        self.assertEqual(payload, {"ok": True, "status": status, "host": "example.com"})
                    else:
                        self.assertIs(payload.get("ok"), False)
                        self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
                        self.assertEqual(payload.get("status"), 403)
                        self.assertEqual(payload.get("host"), "example.com")
                        dumped = json.dumps(payload)
                        self.assertNotIn(sentinel, dumped)
                        self.assertNotIn("challenge-form", dumped)
                        self.assertNotIn("cf-turnstile", dumped)
                        self.assertNotIn("<form", dumped)


class ExtractB4EmptyBodyTests(RealGuardHarness):
    def test_goat_extract_empty_body_is_http_error(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_extract"]["handler"]
        url = "https://example.com/article"
        empty_bodies = (b"", b"   ", b"\t \n\r\n\t ", b" \t\r\n ")
        for status in (202, 200):
            for body in empty_bodies:
                with self.subTest(status=status, body=body):
                    self._current_status = status
                    self._current_body = body
                    self._reset_counts()
                    payload = json.loads(handler({"url": url}))
                    self._assert_transport_counts("/article")
                    self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": status})
                    self.assertNotIn("text", payload)
                    self.assertNotIn("pages", payload)

    def test_goat_extract_nonempty_body_not_mistaken_for_empty(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_extract"]["handler"]
        url = "https://example.com/article"
        sentinel = "SENTINEL-EXTRACT-B4-CONTROL-READABLE"
        cases = (
            ("html", ("<html><head><title>Readable title</title></head><body><p>" + sentinel + " readable article content.</p></body></html>").encode("utf-8")),
            ("json-object-articles", b'{"articles": []}'),
            ("json-array-empty", b"[]"),
            ("json-string", json.dumps(sentinel + " readable").encode("utf-8")),
        )
        for label, body in cases:
            with self.subTest(case=label):
                self._current_status = 202
                self._current_body = body
                self._reset_counts()
                payload = json.loads(handler({"url": url}))
                self._assert_transport_counts("/article")
                self.assertTrue(payload.get("ok"), payload)
                self.assertEqual(payload.get("url"), url)
                self.assertEqual(payload.get("status"), 202)
                self.assertTrue(payload.get("text", ""))
                if label in ("html", "json-string"):
                    self.assertIn(sentinel, payload.get("text", ""))


class CrawlB4EmptyBodyTests(RealGuardHarness):
    def test_goat_crawl_empty_body_is_http_error(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_crawl"]["handler"]
        url = "https://example.com/start"
        empty_bodies = (b"", b"   ", b"\t \n\r\n\t ", b" \t\r\n ")
        for status in (202, 200):
            for body in empty_bodies:
                with self.subTest(status=status, body=body):
                    self._current_status = status
                    self._current_body = body
                    self._reset_counts()
                    payload = json.loads(handler({"url": url, "max_depth": 0, "max_pages": 1}))
                    self._assert_transport_counts("/start")
                    self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": status})
                    self.assertNotIn("text", payload)
                    self.assertNotIn("pages", payload)

    def test_goat_crawl_nonempty_body_not_mistaken_for_empty(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_crawl"]["handler"]
        url = "https://example.com/start"
        sentinel = "SENTINEL-CRAWL-B4-CONTROL-READABLE"
        cases = (
            ("html", ("<html><head><title>Readable title</title></head><body><p>" + sentinel + " readable article content.</p></body></html>").encode("utf-8")),
            ("json-object-articles", b'{"articles": []}'),
            ("json-array-empty", b"[]"),
            ("json-string", json.dumps(sentinel + " readable").encode("utf-8")),
        )
        for label, body in cases:
            with self.subTest(case=label):
                self._current_status = 202
                self._current_body = body
                self._reset_counts()
                payload = json.loads(handler({"url": url, "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/start")
                self.assertTrue(payload.get("ok"), payload)
                pages = payload.get("pages", [])
                self.assertEqual(len(pages), 1)
                self.assertEqual(pages[0].get("url"), url)
                self.assertEqual(pages[0].get("status"), 202)
                self.assertTrue(pages[0].get("text", ""))
                if label in ("html", "json-string"):
                    self.assertIn(sentinel, pages[0].get("text", ""))


class ProbeB4EmptyReachabilityTests(RealGuardHarness):
    def test_goat_probe_empty_body_stays_reachable(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        handler = tools["goat_probe"]["handler"]
        url = "https://example.com/probe"
        empty_bodies = (b"", b"   ", b"\t \n\r\n\t ", b" \t\r\n ")
        for body in empty_bodies:
            with self.subTest(body=body):
                self._current_status = 202
                self._current_body = body
                self._reset_counts()
                payload = json.loads(handler({"url": url}))
                self._assert_transport_counts("/probe")
                self.assertEqual(payload, {"ok": True, "status": 202, "host": "example.com"})


class ChallengePositiveTests(RealGuardHarness):
    def test_structural_challenges_block_all_tools(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        challenges = (
            ("form", b'<html><head><title>Verify you are human</title></head><body><form id="challenge-form" action="/challenge"><input type="hidden" name="c" value="secret-xyz"></form></body></html>'),
            ("captcha", b'<html><head><title>Verify you are human</title></head><body><form id="captcha-form"><input name="c" value="secret-xyz"></form></body></html>'),
            ("turnstile", b'<html><head><title>Attention required</title></head><body><div class="cf-turnstile" data-sitekey="secret-xyz"></div></body></html>'),
            ("title-script", b'<html><head><title>Just a moment...</title></head><body><script src="/cdn-cgi/challenge-platform/h.js"></script><p>secret-xyz</p></body></html>'),
        )
        for shape, body in challenges:
            for status in (200, 403):
                with self.subTest(shape=shape, status=status):
                    self._current_status = status
                    self._current_body = body
                    self._response_headers = [("Content-Type", "text/html")]
                    self._reset_counts()
                    payload = json.loads(extract({"url": "https://example.com/article"}))
                    self._assert_transport_counts("/article")
                    self.assertIs(payload.get("ok"), False, payload)
                    self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}, payload)
                    self.assertNotIn("secret-xyz", json.dumps(payload))
                    self._reset_counts()
                    payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                    self._assert_transport_counts("/article")
                    self.assertIs(payload.get("ok"), False, payload)
                    self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}, payload)
                    self.assertNotIn("secret-xyz", json.dumps(payload))
                    self._reset_counts()
                    payload = json.loads(probe({"url": "https://example.com/article"}))
                    self._assert_transport_counts("/article")
                    self.assertIs(payload.get("ok"), False, payload)
                    self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}, "status": status, "host": "example.com"}, payload)
                    self.assertNotIn("secret-xyz", json.dumps(payload))


class LookalikeNegativeTests(RealGuardHarness):
    def _lookalikes(self, sentinel):
        return (
            ("prose", ("<html><head><title>Readable title</title></head><body><p>" + sentinel + " article about CAPTCHA and challenge-form and Cloudflare, no widget.</p></body></html>").encode("utf-8")),
            ("escaped", ("<html><head><title>Readable</title></head><body><p>" + sentinel + " escaped &lt;form id='challenge-form'&gt; and &lt;div class='cf-turnstile'&gt; text.</p></body></html>").encode("utf-8")),
            ("comment", ("<html><head><title>T</title></head><body><!-- <form id='challenge-form'> --><p>" + sentinel + " readable</p></body></html>").encode("utf-8")),
            ("script-quoted", ("<html><head><title>Readable</title></head><body><script>var x=\"<form id='challenge-form'>\";</script><p>" + sentinel + " readable</p></body></html>").encode("utf-8")),
            ("title-only", ("<html><head><title>Just a moment...</title></head><body><p>" + sentinel + " readable, title only, no script.</p></body></html>").encode("utf-8")),
            ("script-only", ("<html><head><title>Readable title</title></head><body><script src='/cdn-cgi/challenge-platform/h.js'></script><p>" + sentinel + " readable, script only.</p></body></html>").encode("utf-8")),
            ("inert-pre", ("<html><head><title>T</title></head><body><pre><form id='challenge-form'></form></pre><p>" + sentinel + " readable</p></body></html>").encode("utf-8")),
            ("inert-code", ("<html><head><title>T</title></head><body><code><div class='cf-turnstile'></div></code><p>" + sentinel + " readable</p></body></html>").encode("utf-8")),
            ("inert-textarea", ("<html><head><title>T</title></head><body><textarea><form id='challenge-form'></form></textarea><p>" + sentinel + " readable</p></body></html>").encode("utf-8")),
            ("inert-template", ("<html><head><title>T</title></head><body><template><form id='challenge-form'></form></template><p>" + sentinel + " readable</p></body></html>").encode("utf-8")),
        )

    def test_lookalike_html_200_succeeds_all_tools(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        for label, body in self._lookalikes("SENTINEL-LOOKALIKE-READABLE"):
            with self.subTest(case=label):
                self._current_status = 200
                self._current_body = body
                self._response_headers = [("Content-Type", "text/html")]
                self._reset_counts()
                payload = json.loads(extract({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertTrue(payload.get("ok"), payload)
                self.assertEqual(payload.get("status"), 200)
                self.assertIn("SENTINEL-LOOKALIKE-READABLE", payload.get("text", ""))
                self._reset_counts()
                payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/article")
                self.assertTrue(payload.get("ok"), payload)
                pages = payload.get("pages", [])
                self.assertEqual(len(pages), 1)
                self.assertIn("SENTINEL-LOOKALIKE-READABLE", pages[0].get("text", ""))
                self._reset_counts()
                payload = json.loads(probe({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": True, "status": 200, "host": "example.com"}, payload)

    def test_lookalike_html_ordinary_403_is_http_error(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        for label, body in self._lookalikes("SENTINEL-LOOKALIKE-403"):
            with self.subTest(case=label):
                self._current_status = 403
                self._current_body = body
                self._response_headers = [("Content-Type", "text/html")]
                self._reset_counts()
                payload = json.loads(extract({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": 403}, payload)
                self.assertNotIn("SENTINEL-LOOKALIKE-403", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": 403}, payload)
                self.assertNotIn("SENTINEL-LOOKALIKE-403", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(probe({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": 403, "host": "example.com"}, payload)
                self.assertNotIn("SENTINEL-LOOKALIKE-403", json.dumps(payload))


class ContentTypeDiscriminationTests(RealGuardHarness):
    def test_content_type_does_not_spoof_json_or_html(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        makers = (
            ("object", _json_object_body),
            ("array", _json_array_body),
            ("string", _json_string_body),
        )
        for shape, maker in makers:
            with self.subTest(kind="json-with-text-html", shape=shape):
                sentinel = "SENTINEL-CONTENTTYPE-JSON-%s" % shape.upper()
                self._current_status = 200
                self._current_body = maker(sentinel).encode("utf-8")
                self._response_headers = [("Content-Type", "text/html")]
                self._reset_counts()
                payload = json.loads(extract({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertTrue(payload.get("ok"), payload)
                self.assertIn(sentinel, payload.get("text", ""))
                self._reset_counts()
                payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/article")
                self.assertTrue(payload.get("ok"), payload)
                self.assertIn(sentinel, payload.get("pages", [{}])[0].get("text", ""))
                self._reset_counts()
                payload = json.loads(probe({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": True, "status": 200, "host": "example.com"}, payload)
        html_challenge = b'<html><head><title>Verify you are human</title></head><body><form id="challenge-form"><input value="secret-xyz"></form></body></html>'
        for status in (200, 403):
            with self.subTest(kind="html-with-application-json", status=status):
                self._current_status = status
                self._current_body = html_challenge
                self._response_headers = [("Content-Type", "application/json")]
                self._reset_counts()
                payload = json.loads(extract({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}}, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(probe({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}, "status": status, "host": "example.com"}, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))


class OrdinaryHttpErrorTests(RealGuardHarness):
    def test_ordinary_http_errors_are_http_error(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        cases = (
            (403, b"<html><head><title>Forbidden</title></head><body><p>ordinary forbidden secret-xyz</p></body></html>"),
            (404, b"<html><head><title>Not Found</title></head><body><p>ordinary missing secret-xyz</p></body></html>"),
            (500, b"<html><head><title>Server Error</title></head><body><p>ordinary upstream secret-xyz</p></body></html>"),
        )
        for status, body in cases:
            with self.subTest(status=status):
                self._current_status = status
                self._current_body = body
                self._response_headers = [("Content-Type", "text/html")]
                self._reset_counts()
                payload = json.loads(extract({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": status}, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": status}, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(probe({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "HTTP_ERROR"}, "status": status, "host": "example.com"}, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))

    def test_rate_limited_preserves_retry_after(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        challenge_body = b'<html><head><title>Attention required</title></head><body><div class="cf-turnstile"></div><p>secret-xyz</p></body></html>'
        header_cases = (
            ("valid", [("Content-Type", "text/html"), ("Retry-After", "120")], 120),
            ("missing", [("Content-Type", "text/html")], None),
            ("invalid", [("Content-Type", "text/html"), ("Retry-After", "bogus-secret")], None),
        )
        for label, headers, expected_retry in header_cases:
            with self.subTest(case=label):
                self._current_status = 429
                self._current_body = challenge_body
                self._response_headers = headers
                self._reset_counts()
                payload = json.loads(extract({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertIs(payload.get("ok"), False, payload)
                self.assertEqual(payload.get("error"), {"code": "RATE_LIMITED"}, payload)
                self.assertEqual(payload.get("status"), 429, payload)
                if expected_retry is None:
                    self.assertNotIn("retry_after", payload, payload)
                else:
                    self.assertEqual(payload.get("retry_after"), expected_retry, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))
                self.assertNotIn("cf-turnstile", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload.get("error"), {"code": "RATE_LIMITED"}, payload)
                self.assertEqual(payload.get("status"), 429, payload)
                if expected_retry is None:
                    self.assertNotIn("retry_after", payload, payload)
                else:
                    self.assertEqual(payload.get("retry_after"), expected_retry, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))
                self._reset_counts()
                payload = json.loads(probe({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload.get("error"), {"code": "RATE_LIMITED"}, payload)
                self.assertEqual(payload.get("status"), 429, payload)
                self.assertEqual(payload.get("host"), "example.com", payload)
                if expected_retry is None:
                    self.assertNotIn("retry_after", payload, payload)
                else:
                    self.assertEqual(payload.get("retry_after"), expected_retry, payload)
                self.assertNotIn("secret-xyz", json.dumps(payload))

    def test_invalid_status_types_are_url_blocked(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        invalid = (True, False, "200", 200.0, None, 99, 600)
        for bad in invalid:
            with self.subTest(status=repr(bad)):
                self._current_status = bad
                self._current_body = b'{"article": "valid nonchallenge data"}'
                self._response_headers = [("Content-Type", "application/json")]
                self._reset_counts()
                payload = json.loads(extract({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}, payload)
                self._reset_counts()
                payload = json.loads(crawl({"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}, payload)
                self._reset_counts()
                payload = json.loads(probe({"url": "https://example.com/article"}))
                self._assert_transport_counts("/article")
                self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}, payload)


class DnsAndTransportErrorTests(RealGuardHarness):
    def test_dns_gaierror_is_dns_error(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        self._dns_errors["example.com"] = socket.gaierror(socket.EAI_NONAME, "mock dns failure secret-xyz")
        try:
            for tool_name, args in (
                ("extract", {"url": "https://example.com/article"}),
                ("crawl", {"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}),
                ("probe", {"url": "https://example.com/article"}),
            ):
                with self.subTest(tool=tool_name):
                    self._reset_counts()
                    handler = {"extract": extract, "crawl": crawl, "probe": probe}[tool_name]
                    payload = json.loads(handler(args))
                    self.assertEqual(len(self.resolver_calls), 1)
                    self.assertEqual(self.resolver_calls[0][0], "example.com")
                    self._assert_zero_factory()
                    self.assertEqual(payload, {"ok": False, "error": {"code": "DNS_ERROR"}}, payload)
                    self.assertNotIn("secret-xyz", json.dumps(payload))
        finally:
            del self._dns_errors["example.com"]

    def test_native_transport_errors_map(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        handlers = {"extract": extract, "crawl": crawl, "probe": probe}
        cases = (
            ("factory-timeout", {"factory": TimeoutError("mock upstream timeout secret-xyz")}, "UPSTREAM_TIMEOUT", (1, 1, 0, 0, 0)),
            ("factory-oserror", {"factory": OSError("mock connection failure secret-xyz")}, "CONNECTION_ERROR", (1, 1, 0, 0, 0)),
            ("request-oserror", {"request": OSError("mock connection failure secret-xyz")}, "CONNECTION_ERROR", (1, 1, 1, 0, 1)),
            ("response-httpexception", {"response": http.client.HTTPException("mock response failure secret-xyz")}, "CONNECTION_ERROR", (1, 1, 1, 0, 1)),
            ("read-timeout", {"read": TimeoutError("mock read timeout secret-xyz")}, "UPSTREAM_TIMEOUT", (1, 1, 1, 1, 1)),
        )
        for label, errors, expected_code, (n_resolver, n_factory, n_request, n_read, n_close) in cases:
            for tool_name in ("extract", "crawl", "probe"):
                with self.subTest(case=label, tool=tool_name):
                    self._factory_error = errors.get("factory")
                    self._request_error = errors.get("request")
                    self._response_error = errors.get("response")
                    self._read_error = errors.get("read")
                    self._current_status = 200
                    self._current_body = b"ordinary body secret-xyz"
                    self._response_headers = [("Content-Type", "text/html")]
                    try:
                        self._reset_counts()
                        args = {"url": "https://example.com/article"}
                        if tool_name == "crawl":
                            args = {"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}
                        payload = json.loads(handlers[tool_name](args))
                        self.assertEqual(len(self.resolver_calls), n_resolver, payload)
                        self.assertEqual(len(self.factory_calls), n_factory, payload)
                        self.assertEqual(len(self.request_calls), n_request, payload)
                        self.assertEqual(len(self.read_bounds), n_read, payload)
                        self.assertEqual(len(self.close_calls), n_close, payload)
                        self.assertIs(payload.get("ok"), False, payload)
                        self.assertEqual(payload.get("error"), {"code": expected_code}, payload)
                        self.assertNotIn("secret-xyz", json.dumps(payload))
                        self.assertNotIn("Traceback", json.dumps(payload))
                    finally:
                        self._factory_error = None
                        self._request_error = None
                        self._response_error = None
                        self._read_error = None


class PrivateLiteralTests(RealGuardHarness):
    def test_private_literals_blocked_without_egress(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        urls = (
            "https://127.0.0.1/",
            "https://10.0.0.5/a",
            "https://[::1]/",
            "https://[fd00::1]/x",
        )
        for url in urls:
            for tool_name, args in (
                ("extract", {"url": url}),
                ("crawl", {"url": url, "max_depth": 0, "max_pages": 1}),
                ("probe", {"url": url}),
            ):
                with self.subTest(url=url, tool=tool_name):
                    self._reset_counts()
                    handler = {"extract": extract, "crawl": crawl, "probe": probe}[tool_name]
                    payload = json.loads(handler(args))
                    self.assertEqual(self.resolver_calls, [], payload)
                    self._assert_zero_factory()
                    self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}, payload)


class PrivateDnsTests(RealGuardHarness):
    def test_private_and_mixed_dns_rejected_before_connect(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        handlers = {"extract": extract, "crawl": crawl, "probe": probe}
        cases = (
            ("private-v4", [_private_v4_answer("10.0.0.5")]),
            ("private-v6", [_private_v6_answer("fd00::1")]),
            ("mixed-pub-priv", [_public_answer(), _private_v4_answer("192.168.1.1")]),
            ("mixed-priv-pub", [_private_v4_answer("192.168.1.1"), _public_answer()]),
            ("mixed-pub-priv6", [_public_answer(), _private_v6_answer("fd00::2")]),
            ("mixed-priv6-pub", [_private_v6_answer("fd00::2"), _public_answer()]),
        )
        for label, answers in cases:
            for tool_name in ("extract", "crawl", "probe"):
                with self.subTest(case=label, tool=tool_name):
                    self._dns_map["example.com"] = answers
                    try:
                        self._reset_counts()
                        args = {"url": "https://example.com/article"}
                        if tool_name == "crawl":
                            args = {"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}
                        payload = json.loads(handlers[tool_name](args))
                        self.assertEqual(len(self.resolver_calls), 1, payload)
                        self.assertEqual(self.resolver_calls[0][0], "example.com", payload)
                        self._assert_zero_factory()
                        self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}, payload)
                    finally:
                        del self._dns_map["example.com"]


class RedirectInvalidTargetTests(RealGuardHarness):
    def test_redirect_to_private_or_http_blocked_after_first_fetch(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        handlers = {"extract": extract, "crawl": crawl, "probe": probe}
        locations = (
            ("private-literal", "https://10.0.0.5/secret"),
            ("private-ipv6", "https://[fd00::1]/secret"),
            ("http-public", "http://example.com/other"),
        )
        for label, location in locations:
            for tool_name in ("extract", "crawl", "probe"):
                with self.subTest(target=label, tool=tool_name):
                    self._current_status = 302
                    self._current_body = b"ordinary redirect secret-xyz"
                    self._response_headers = [("Content-Type", "text/html"), ("Location", location)]
                    self._reset_counts()
                    args = {"url": "https://example.com/article"}
                    if tool_name == "crawl":
                        args = {"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}
                    payload = json.loads(handlers[tool_name](args))
                    self.assertEqual(len(self.resolver_calls), 1, payload)
                    self._assert_first_fetch_pinned("example.com", "/article")
                    if tool_name == "probe":
                        self.assertEqual(payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}, "status": 302, "host": "example.com"}, payload)
                    else:
                        self.assertEqual(payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}, payload)
                    dumped = json.dumps(payload)
                    self.assertNotIn("secret-xyz", dumped)
                    self.assertNotIn("10.0.0.5", dumped)
                    self.assertNotIn("fd00::1", dumped)


class RedirectPrivateDnsTests(RealGuardHarness):
    def test_redirect_to_private_dns_blocked_without_second_connection(self):
        self._expected_host = "example.com"
        _, tools = self._load_real_tools()
        extract = tools["goat_extract"]["handler"]
        crawl = tools["goat_crawl"]["handler"]
        probe = tools["goat_probe"]["handler"]
        handlers = {"extract": extract, "crawl": crawl, "probe": probe}
        cases = (
            ("private", [_private_v4_answer("192.168.1.1")]),
            ("mixed-pub-priv", [_public_answer(), _private_v4_answer("10.0.0.5")]),
            ("mixed-priv-pub", [_private_v4_answer("10.0.0.5"), _public_answer()]),
            ("mixed-pub-priv6", [_public_answer(), _private_v6_answer("fd00::9")]),
        )
        for label, target_answers in cases:
            for tool_name in ("extract", "crawl", "probe"):
                with self.subTest(case=label, tool=tool_name):
                    self._dns_map["evil.example"] = target_answers
                    try:
                        self._current_status = 302
                        self._current_body = b"ordinary redirect secret-xyz"
                        self._response_headers = [("Content-Type", "text/html"), ("Location", "https://evil.example/other")]
                        self._reset_counts()
                        args = {"url": "https://example.com/article"}
                        if tool_name == "crawl":
                            args = {"url": "https://example.com/article", "max_depth": 0, "max_pages": 1}
                        payload = json.loads(handlers[tool_name](args))
                        self.assertEqual(len(self.resolver_calls), 2, payload)
                        self.assertEqual(self.resolver_calls[0][0], "example.com", payload)
                        self.assertEqual(self.resolver_calls[1][0], "evil.example", payload)
                        self._assert_first_fetch_pinned("example.com", "/article")
                        if tool_name == "probe":
                            self.assertEqual(payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}, "status": 302, "host": "example.com"}, payload)
                        else:
                            self.assertEqual(payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}, payload)
                        dumped = json.dumps(payload)
                        self.assertNotIn("secret-xyz", dumped)
                        self.assertNotIn("evil.example", dumped)
                        self.assertNotIn("192.168.1.1", dumped)
                        self.assertNotIn("10.0.0.5", dumped)
                    finally:
                        del self._dns_map["evil.example"]


if __name__ == "__main__":
    unittest.main()
