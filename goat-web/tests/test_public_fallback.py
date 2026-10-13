"""STAGE 1 RED: P0 public allow_fallback gap (goat_search).

Proves via the REAL register/dispatch path (real built bundle, real
validate_args + operation(**validated) through _json_handler) that the
public goat_search schema rejects allow_fallback while the internal
goat_search(..., allow_fallback=True) with the SAME fake transport DOES
fall back with source/transitions provenance.

Strictly offline: socket resolution/connectors raise AssertionError at
import time and per-test; only injected fake transports are used.
"""

import importlib
import json
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

# --- module-level offline block: `python3 -B <this file>` alone is offline.
_BLOCKED_SOCKET_ATTRS = (
    "getaddrinfo",
    "gethostbyname",
    "gethostbyname_ex",
    "gethostbyaddr",
    "getnameinfo",
    "create_connection",
)
_BLOCKED_SOCK_METHODS = ("connect", "connect_ex", "sendto", "sendmsg")


def _offline_denied(name):
    def _denied(*args, **kwargs):
        raise AssertionError("network disabled: %s" % name)

    return _denied


for _name in _BLOCKED_SOCKET_ATTRS:
    try:
        setattr(socket, _name, _offline_denied(_name))
    except Exception:
        pass
for _mname in _BLOCKED_SOCK_METHODS:
    try:
        if hasattr(socket.socket, _mname):
            setattr(socket.socket, _mname, _offline_denied("socket." + _mname))
    except Exception:
        pass

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
import test_plugin_wiring as _wiring  # noqa: E402

DDG_OK_HTML = (
    '<html><body><a class="result__a" href="https://example.com/a">Title A</a>'
    '<div class="result__snippet">Snippet A</div></body></html>'
)
DDG_FAIL_HTML = (
    "<html><head><title>Error</title></head>"
    "<body><p>ordinary-500-boom</p></body></html>"
)
DDG_DUP_HTML = (
    '<html><body><a class="result__a" href="https://example.com/a">Title A</a>'
    '<div class="result__snippet">Snippet A</div>'
    '<a class="result__a" href="https://example.com/dup">Title Dup</a>'
    '<div class="result__snippet">Snippet Dup</div></body></html>'
)
DDG_TWO_HTML = (
    '<html><body><a class="result__a" href="https://example.com/a">Title A</a>'
    '<div class="result__snippet">Snippet A</div>'
    '<a class="result__a" href="https://example.com/b">Title B</a>'
    '<div class="result__snippet">Snippet B</div></body></html>'
)
WIKI_OK_BODY = json.dumps(
    ["x", ["Wiki Title"], ["Wiki desc"], ["https://example.com/wiki/X"]]
)
WIKI_DUP_BODY = json.dumps(
    [
        "x",
        ["Dup Wiki", "Wiki C"],
        ["Dup desc", "C desc"],
        ["https://example.com/dup", "https://example.com/c"],
    ]
)
WIKI_TWO_BODY = json.dumps(
    [
        "x",
        ["Wiki One", "Wiki Two"],
        ["One desc", "Two desc"],
        ["https://example.com/wiki/One", "https://example.com/wiki/Two"],
    ]
)


def _ddg_ok_transport(url):
    assert "html.duckduckgo.com" in url, "unexpected " + url
    return {"status": 200, "body": DDG_OK_HTML}


def _failover_transport(url):
    if "html.duckduckgo.com" in url:
        return {"status": 500, "body": DDG_FAIL_HTML}
    if "en.wikipedia.org" in url:
        return {"status": 200, "body": WIKI_OK_BODY}
    raise AssertionError("unexpected fetch " + url)


def _dedup_transport(url):
    if "html.duckduckgo.com" in url:
        return {"status": 200, "body": DDG_DUP_HTML}
    if "en.wikipedia.org" in url:
        return {"status": 200, "body": WIKI_DUP_BODY}
    raise AssertionError("unexpected fetch " + url)


def _both_fail_transport(url):
    if "html.duckduckgo.com" in url:
        return {"status": 500, "body": DDG_FAIL_HTML}
    if "en.wikipedia.org" in url:
        return {"status": 500, "body": DDG_FAIL_HTML}
    raise AssertionError("unexpected fetch " + url)


def _two_each_transport(url):
    if "html.duckduckgo.com" in url:
        return {"status": 200, "body": DDG_TWO_HTML}
    if "en.wikipedia.org" in url:
        return {"status": 200, "body": WIKI_TWO_BODY}
    raise AssertionError("unexpected fetch " + url)


class OfflineRecordingTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.network_attempts = []
        self._saved = {n: getattr(socket, n) for n in _BLOCKED_SOCKET_ATTRS}
        for name in _BLOCKED_SOCKET_ATTRS:
            setattr(socket, name, self._deny(name))
        self._saved_methods = {}
        for name in _BLOCKED_SOCK_METHODS:
            if hasattr(socket.socket, name):
                self._saved_methods[name] = getattr(socket.socket, name)
                setattr(socket.socket, name, self._deny("socket." + name))
        self.addCleanup(self._restore_and_assert_no_network)

    def _deny(self, name):
        def _denied(*a, **k):
            self.network_attempts.append((name, a, k))
            raise AssertionError("network disabled: %s" % name)

        return _denied

    def _restore_and_assert_no_network(self):
        for name, fn in self._saved.items():
            setattr(socket, name, fn)
        for name, fn in self._saved_methods.items():
            setattr(socket.socket, name, fn)
        self.assertEqual(self.network_attempts, [])

    def assertNoNetwork(self):
        self.assertEqual(self.network_attempts, [])


class PublicFallbackTests(OfflineRecordingTestCase):
    def _load(self):
        bundle = _wiring._build_fresh_bundle(self)
        mod_name, mod = _wiring._load_built_package(bundle)
        self.addCleanup(_wiring._unload_built_package, mod_name)
        goat_tools = importlib.import_module(mod_name + ".goat_tools")
        tool_schemas = importlib.import_module(mod_name + ".tool_schemas")
        tools = _wiring._registered_tools(mod)
        return goat_tools, tool_schemas, tools

    def test_backward_compat_absent_flag_still_works(self):
        """Passing control: absent flag keeps single-provider success."""
        goat_tools, _schemas, tools = self._load()
        handler = tools["goat_search"]["handler"]
        raw = goat_tools.goat_search("x", transport=_ddg_ok_transport)
        self.assertIn("results", raw)
        self.assertNotIn("transitions", raw)
        with mock.patch.object(goat_tools, "pinned_fetch", _ddg_ok_transport):
            payload = json.loads(handler({"query": "x"}))
        self.assertTrue(payload.get("ok"))
        self.assertIn("results", payload)
        self.assertNoNetwork()

    def test_absent_or_false_never_triggers_fallback(self):
        """Opt-in expectation: absent/False never produces fallback hops."""
        goat_tools, _schemas, tools = self._load()
        handler = tools["goat_search"]["handler"]
        raw_default = goat_tools.goat_search("x", transport=_failover_transport)
        self.assertEqual(raw_default.get("error"), {"code": "HTTP_ERROR"})
        self.assertNotIn("transitions", raw_default)
        raw_false = goat_tools.goat_search(
            "x", transport=_failover_transport, allow_fallback=False
        )
        self.assertEqual(raw_false.get("error"), {"code": "HTTP_ERROR"})
        self.assertNotIn("transitions", raw_false)
        with mock.patch.object(goat_tools, "pinned_fetch", _failover_transport):
            payload = json.loads(handler({"query": "x"}))
        self.assertFalse(payload.get("ok"))
        self.assertNotIn("transitions", payload)
        self.assertNoNetwork()

    def test_public_allow_fallback_triggers_fallback(self):
        """RED: public path must honour allow_fallback=True (currently rejects)."""
        goat_tools, tool_schemas, tools = self._load()
        handler = tools["goat_search"]["handler"]
        parameters = tools["goat_search"]["schema"]["parameters"]
        # Internal opt-in path DOES fall back with provenance (control assert).
        direct = goat_tools.goat_search(
            "x", transport=_failover_transport, allow_fallback=True
        )
        self.assertIn("results", direct, "internal fallback must succeed: %r" % (direct,))
        self.assertTrue(direct["results"], "internal fallback must yield results")
        self.assertEqual(direct.get("source"), "wikipedia")
        self.assertTrue(direct.get("transitions"), "fallback must stamp transitions")
        # Public schema must accept the flag (RED: currently False -> additionalProperties).
        ok, validated = tool_schemas.validate_args(
            parameters, {"query": "x", "allow_fallback": True}
        )
        self.assertTrue(ok, "public schema rejects allow_fallback (P0 gap)")
        self.assertTrue(validated.get("allow_fallback") is True)
        # Public dispatch must fall back with provenance (RED: currently URL_BLOCKED).
        with mock.patch.object(goat_tools, "pinned_fetch", _failover_transport):
            payload = json.loads(handler({"query": "x", "allow_fallback": True}))
        self.assertTrue(payload.get("ok"), "public fallback dropped: %r" % (payload,))
        self.assertTrue(payload.get("results"))
        self.assertTrue(
            payload.get("transitions"), "public fallback lacks transitions: %r" % (payload,)
        )
        self.assertNoNetwork()

    def test_strict_bool_rejects_non_bool_flags(self):
        """Non-bool allow_fallback values are rejected, never fall back."""
        _goat_tools, tool_schemas, tools = self._load()
        handler = tools["goat_search"]["handler"]
        parameters = tools["goat_search"]["schema"]["parameters"]
        for bad in (1, "true", 0):
            with self.subTest(flag=repr(bad)):
                ok, validated = tool_schemas.validate_args(
                    parameters, {"query": "x", "allow_fallback": bad}
                )
                self.assertFalse(ok, "non-bool accepted: %r" % (bad,))
                self.assertIsNone(validated)
                calls = []

                def _recording(url):
                    calls.append(url)
                    return _failover_transport(url)

                with mock.patch.object(_goat_tools, "pinned_fetch", _recording):
                    payload = json.loads(
                        handler({"query": "x", "allow_fallback": bad})
                    )
                self.assertFalse(payload.get("ok"))
                self.assertEqual(payload.get("error"), {"code": "URL_BLOCKED"})
                self.assertNotIn("transitions", payload)
                self.assertEqual(calls, [])
        self.assertNoNetwork()

    def test_merged_duplicates_appear_once(self):
        """DDG/Wikipedia overlap merges to one entry with both contributors."""
        goat_tools, _schemas, tools = self._load()
        handler = tools["goat_search"]["handler"]
        with mock.patch.object(goat_tools, "pinned_fetch", _dedup_transport):
            payload = json.loads(handler({"query": "x", "allow_fallback": True}))
        self.assertTrue(payload.get("ok"), "dedup merge dropped: %r" % (payload,))
        urls = [item["url"] for item in payload["results"]]
        self.assertEqual(len(urls), len(set(urls)), "duplicate kept: %r" % (payload,))
        self.assertEqual(urls.count("https://example.com/dup"), 1)
        sources = set(payload.get("sources", []))
        self.assertIn("ddg", sources, "ddg missing: %r" % (payload,))
        self.assertIn("wikipedia", sources, "wikipedia missing: %r" % (payload,))
        self.assertTrue(payload.get("transitions"), "merge lacks hops: %r" % (payload,))
        self.assertNoNetwork()

    def test_all_providers_fail_preserves_last_error(self):
        """DDG 500 + Wikipedia 500 keeps last HTTP_ERROR verbatim + chain."""
        goat_tools, _schemas, tools = self._load()
        handler = tools["goat_search"]["handler"]
        raw = goat_tools.goat_search(
            "x", transport=_both_fail_transport, allow_fallback=True
        )
        self.assertEqual(raw.get("error"), {"code": "HTTP_ERROR"})
        self.assertEqual(raw.get("status"), 500)
        self.assertEqual(raw.get("source"), "wikipedia")
        self.assertEqual(
            raw.get("transitions"),
            [{"from": "ddg", "to": "wikipedia", "reason": "HTTP_ERROR"}],
        )
        with mock.patch.object(goat_tools, "pinned_fetch", _both_fail_transport):
            payload = json.loads(handler({"query": "x", "allow_fallback": True}))
        self.assertFalse(payload.get("ok"))
        self.assertEqual(payload.get("error"), {"code": "HTTP_ERROR"})
        self.assertEqual(payload.get("status"), 500)
        self.assertNoNetwork()

    def test_max_results_caps_merged_output(self):
        """max_results=1 caps merged output even when both providers return more."""
        goat_tools, _schemas, tools = self._load()
        handler = tools["goat_search"]["handler"]
        with mock.patch.object(goat_tools, "pinned_fetch", _two_each_transport):
            payload = json.loads(
                handler({"query": "x", "allow_fallback": True, "max_results": 1})
            )
        self.assertTrue(payload.get("ok"), "capped merge dropped: %r" % (payload,))
        self.assertEqual(len(payload.get("results", [])), 1)
        self.assertNoNetwork()


if __name__ == "__main__":
    unittest.main()
