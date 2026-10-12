"""Slice 1: pluggable search backend with ordered fallback (offline TDD).

Real goat_search route plus real register() dispatch; only fake HTTP
transports are injected. Fake resolver/TCP denial proves no network.
No live benchmarks, no paid APIs, no new dependencies.
"""

import json
import socket
import sys
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "plugins" / "goat-web"
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import goat_tools  # noqa: E402
import search_providers  # noqa: E402


def _ddg_html(items):
    parts = []
    for title, url, snippet in items:
        parts.append(
            '<a class="result__a" href="%s">%s</a>'
            '<div class="result__snippet">%s</div>' % (url, title, snippet)
        )
    return "".join(parts)


DDG_TWO = _ddg_html(
    [
        ("Alpha Title", "https://example.com/a", "Alpha snippet words."),
        ("Beta Title", "https://example.com/b", "Beta snippet words."),
    ]
)

DDG_CHALLENGE_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><body><form id="challenge-form" action="/c" method="post">'
    "verify you are human</form></body></html>"
)

EMPTY_NO_RESULTS_HTML = (
    "<!-- synthetic, not live-captured -->"
    '<html><body><form action="/html/" method="post">'
    '<input name="q" value="zxqy offline"/></form>'
    '<div class="no-results"><h1>No results found</h1></div></body></html>'
)

ORDINARY_503_HTML = (
    "<html><head><title>Unavailable</title></head>"
    "<body><p>ordinary outage</p></body></html>"
)


def _wiki_body(titles, descriptions, urls, query="offline query"):
    return json.dumps([query, titles, descriptions, urls])


WIKI_TWO_BODY = _wiki_body(
    ["Wiki Title One", "Wiki Title Two"],
    ["First description.", "Second description."],
    ["https://en.wikipedia.org/wiki/One", "https://en.wikipedia.org/wiki/Two"],
)


def _router(calls, *, ddg=None, ddg_exc=None, wiki=None, wiki_exc=None):
    def _transport(url):
        calls.append(url)
        if "html.duckduckgo.com" in url:
            if ddg_exc is not None:
                raise ddg_exc
            return dict(ddg)
        if "wikipedia.org" in url:
            if wiki_exc is not None:
                raise wiki_exc
            return dict(wiki)
        raise AssertionError("unexpected url: %s" % url)

    return _transport


class OfflineRecordingTestCase(unittest.TestCase):
    RESOLVER_NAMES = (
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
        "gethostbyaddr",
        "getnameinfo",
        "create_connection",
    )
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


class FallbackTransitionTests(OfflineRecordingTestCase):
    def test_a_primary_provider_blocked_falls_back_with_transitions(self):
        calls = []
        transport = _router(
            calls,
            ddg={"status": 200, "body": DDG_CHALLENGE_HTML},
            wiki={"status": 200, "body": WIKI_TWO_BODY},
        )
        raw = goat_tools.goat_search(
            "offline query", transport=transport, allow_fallback=True
        )
        self.assertEqual(
            raw.get("results"),
            [
                {
                    "title": "Wiki Title One",
                    "url": "https://en.wikipedia.org/wiki/One",
                    "snippet": "First description.",
                },
                {
                    "title": "Wiki Title Two",
                    "url": "https://en.wikipedia.org/wiki/Two",
                    "snippet": "Second description.",
                },
            ],
        )
        self.assertEqual(raw.get("source"), "wikipedia")
        self.assertEqual(
            raw.get("transitions"),
            [{"from": "ddg", "to": "wikipedia", "reason": "PROVIDER_BLOCKED"}],
        )
        self.assertEqual(len(calls), 2)
        self.assertIn("html.duckduckgo.com", calls[0])
        self.assertIn("wikipedia.org", calls[1])
        # Same behavior through the real register() dispatch path.
        calls2 = []
        handler = goat_tools.register()["goat_search"]
        via_dispatch = handler(
            "offline query",
            transport=_router(
                calls2,
                ddg={"status": 200, "body": DDG_CHALLENGE_HTML},
                wiki={"status": 200, "body": WIKI_TWO_BODY},
            ),
            allow_fallback=True,
        )
        self.assertEqual(via_dispatch, raw)
        self.assertEqual(self.network_attempts, [])


class AllFailChainTests(OfflineRecordingTestCase):
    def test_b_all_providers_fail_preserves_last_error_with_full_chain(self):
        calls = []
        raw = goat_tools.goat_search(
            "offline query",
            transport=_router(
                calls,
                ddg={"status": 200, "body": DDG_CHALLENGE_HTML},
                wiki={"status": 503, "body": ORDINARY_503_HTML},
            ),
            allow_fallback=True,
        )
        self.assertEqual(
            raw,
            {
                "error": {"code": "HTTP_ERROR"},
                "status": 503,
                "source": "wikipedia",
                "transitions": [
                    {"from": "ddg", "to": "wikipedia", "reason": "PROVIDER_BLOCKED"}
                ],
            },
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.network_attempts, [])

    def test_b_missing_config_stops_chain_immediately(self):
        second_calls = []

        def _first(_query, *, transport, max_results):
            return {"error": {"code": "MISSING_CONFIG"}}

        def _second(_query, *, transport, max_results):
            second_calls.append(transport)
            return {"results": []}

        search_providers.register_provider("first", _first)
        search_providers.register_provider("second", _second)
        self.addCleanup(search_providers.reset_registry)
        out = search_providers.search_with_fallback(
            "offline query",
            transport=_router([], ddg={"status": 200, "body": DDG_TWO}),
            providers=["first", "second"],
        )
        self.assertEqual(out, {"error": {"code": "MISSING_CONFIG"}, "source": "first"})
        self.assertEqual(second_calls, [])


class MergeDedupCapTests(OfflineRecordingTestCase):
    def test_c_cross_provider_duplicates_deduped_with_cap_kept(self):
        calls = []
        wiki_body = _wiki_body(
            ["Dup B", "Wiki C", "Wiki D", "Wiki E", "Wiki F"],
            ["dup snippet", "c snippet", "d snippet", "e snippet", "f snippet"],
            [
                "https://example.com/b",
                "https://en.wikipedia.org/wiki/C",
                "https://en.wikipedia.org/wiki/D",
                "https://en.wikipedia.org/wiki/E",
                "https://en.wikipedia.org/wiki/F",
            ],
        )
        raw = goat_tools.goat_search(
            "offline query",
            transport=_router(
                calls,
                ddg={"status": 200, "body": DDG_TWO},
                wiki={"status": 200, "body": wiki_body},
            ),
            allow_fallback=True,
        )
        self.assertEqual(
            raw.get("results"),
            [
                {
                    "title": "Alpha Title",
                    "url": "https://example.com/a",
                    "snippet": "Alpha snippet words.",
                },
                {
                    "title": "Beta Title",
                    "url": "https://example.com/b",
                    "snippet": "Beta snippet words.",
                },
                {
                    "title": "Wiki C",
                    "url": "https://en.wikipedia.org/wiki/C",
                    "snippet": "c snippet",
                },
                {
                    "title": "Wiki D",
                    "url": "https://en.wikipedia.org/wiki/D",
                    "snippet": "d snippet",
                },
                {
                    "title": "Wiki E",
                    "url": "https://en.wikipedia.org/wiki/E",
                    "snippet": "e snippet",
                },
            ],
        )
        self.assertEqual(raw.get("source"), "ddg")
        self.assertEqual(raw.get("sources"), ["ddg", "wikipedia"])
        self.assertEqual(
            raw.get("transitions"),
            [{"from": "ddg", "to": "wikipedia", "reason": "PARTIAL_RESULTS"}],
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.network_attempts, [])

    def test_c_empty_primary_continues_with_no_results_reason(self):
        calls = []
        raw = goat_tools.goat_search(
            "offline query",
            transport=_router(
                calls,
                ddg={"status": 200, "body": EMPTY_NO_RESULTS_HTML},
                wiki={"status": 200, "body": WIKI_TWO_BODY},
            ),
            allow_fallback=True,
        )
        self.assertEqual(len(raw.get("results")), 2)
        self.assertEqual(raw.get("source"), "wikipedia")
        self.assertEqual(
            raw.get("transitions"),
            [{"from": "ddg", "to": "wikipedia", "reason": "NO_RESULTS"}],
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.network_attempts, [])


class AvailabilityAndRetryTests(OfflineRecordingTestCase):
    def test_e_unavailable_provider_skipped_without_transport_call(self):
        calls = []

        def _down(_query, *, transport, max_results):
            calls.append("down")
            return {"error": {"code": "HTTP_ERROR"}, "status": 500}

        def _up(_query, *, transport, max_results):
            calls.append("up")
            return {
                "results": [
                    {
                        "title": "Up Title",
                        "url": "https://example.com/up",
                        "snippet": "up snippet",
                    }
                ]
            }

        search_providers.register_provider(
            "down", _down, available=lambda _config=None: False
        )
        search_providers.register_provider("up", _up)
        self.addCleanup(search_providers.reset_registry)
        out = search_providers.search_with_fallback(
            "offline query",
            transport=_router([], ddg={"status": 200, "body": DDG_TWO}),
            providers=["down", "up"],
        )
        self.assertEqual(calls, ["up"])
        self.assertEqual(
            out,
            {
                "results": [
                    {
                        "title": "Up Title",
                        "url": "https://example.com/up",
                        "snippet": "up snippet",
                    }
                ],
                "source": "up",
                "sources": ["up"],
            },
        )
        self.assertEqual(self.network_attempts, [])

    def test_e_disabled_provider_config_empties_chain_fail_closed(self):
        calls = []
        out = search_providers.search_with_fallback(
            "offline query",
            transport=_router(
                calls, wiki={"status": 200, "body": WIKI_TWO_BODY}
            ),
            providers=["wikipedia"],
            provider_config={"disabled": ["wikipedia"]},
        )
        self.assertEqual(out, {"error": {"code": "URL_BLOCKED"}, "source": None})
        self.assertEqual(calls, [])

    def test_f_transient_errors_retry_bounded_then_fail_over(self):
        attempts = []
        sleeps = []

        def _flaky(_query, *, transport, max_results):
            attempts.append(transport)
            return {"error": {"code": "CONNECTION_ERROR"}}

        def _ok(_query, *, transport, max_results):
            return {
                "results": [
                    {
                        "title": "Ok Title",
                        "url": "https://example.com/ok",
                        "snippet": "ok snippet",
                    }
                ]
            }

        search_providers.register_provider("flaky", _flaky)
        search_providers.register_provider("ok", _ok)
        self.addCleanup(search_providers.reset_registry)
        out = search_providers.search_with_fallback(
            "offline query",
            transport=_router([], ddg={"status": 200, "body": DDG_TWO}),
            providers=["flaky", "ok"],
            max_attempts=2,
            sleep=sleeps.append,
        )
        self.assertEqual(len(attempts), 2)
        self.assertEqual(sleeps, [0.05])
        self.assertEqual(out.get("source"), "ok")
        self.assertEqual(
            out.get("transitions"),
            [{"from": "flaky", "to": "ok", "reason": "CONNECTION_ERROR"}],
        )
        self.assertEqual(self.network_attempts, [])

    def test_f_transient_recovery_with_exponential_backoff_schedule(self):
        calls = []
        sleeps = []
        state = {"n": 0}

        def _recovering(_query, *, transport, max_results):
            calls.append(transport)
            state["n"] += 1
            if state["n"] < 3:
                return {"error": {"code": "RATE_LIMITED"}, "status": 429}
            return {
                "results": [
                    {
                        "title": "Recovered",
                        "url": "https://example.com/recovered",
                        "snippet": "recovered snippet",
                    }
                ]
            }

        search_providers.register_provider("recovering", _recovering)
        self.addCleanup(search_providers.reset_registry)
        out = search_providers.search_with_fallback(
            "offline query",
            transport=_router([], ddg={"status": 200, "body": DDG_TWO}),
            providers=["recovering"],
            max_attempts=3,
            sleep=sleeps.append,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.05, 0.1])
        self.assertEqual(out.get("source"), "recovering")
        self.assertNotIn("transitions", out)
        self.assertEqual(self.network_attempts, [])

    def test_f_non_transient_errors_fail_over_without_retry(self):
        attempts = []
        sleeps = []

        def _blocked(_query, *, transport, max_results):
            attempts.append(transport)
            return {"error": {"code": "PROVIDER_BLOCKED"}}

        def _ok(_query, *, transport, max_results):
            return {
                "results": [
                    {
                        "title": "Ok Title",
                        "url": "https://example.com/ok",
                        "snippet": "ok snippet",
                    }
                ]
            }

        search_providers.register_provider("blocked", _blocked)
        search_providers.register_provider("ok", _ok)
        self.addCleanup(search_providers.reset_registry)
        out = search_providers.search_with_fallback(
            "offline query",
            transport=_router([], ddg={"status": 200, "body": DDG_TWO}),
            providers=["blocked", "ok"],
            max_attempts=3,
            sleep=sleeps.append,
        )
        self.assertEqual(len(attempts), 1)
        self.assertEqual(sleeps, [])
        self.assertEqual(out.get("source"), "ok")


class BaselineRegressionPinTests(OfflineRecordingTestCase):
    def test_d_fallback_disabled_matches_baseline_exactly(self):
        for flag in (None, False):
            with self.subTest(flag=flag):
                kwargs = {} if flag is None else {"allow_fallback": False}
                # Success shape: exact dict, no provenance keys, one call.
                calls = []
                raw = goat_tools.goat_search(
                    "offline query",
                    transport=_router(calls, ddg={"status": 200, "body": DDG_TWO}),
                    **kwargs,
                )
                self.assertEqual(
                    raw,
                    {
                        "results": [
                            {
                                "title": "Alpha Title",
                                "url": "https://example.com/a",
                                "snippet": "Alpha snippet words.",
                            },
                            {
                                "title": "Beta Title",
                                "url": "https://example.com/b",
                                "snippet": "Beta snippet words.",
                            },
                        ]
                    },
                )
                self.assertEqual(len(calls), 1)
                # Provider challenge: exact baseline error, one call, no failover.
                calls = []
                raw = goat_tools.goat_search(
                    "offline query",
                    transport=_router(
                        calls, ddg={"status": 200, "body": DDG_CHALLENGE_HTML}
                    ),
                    **kwargs,
                )
                self.assertEqual(raw, {"error": {"code": "PROVIDER_BLOCKED"}})
                self.assertEqual(len(calls), 1)
                # Rate limit keeps typed diagnostics, no failover.
                calls = []
                raw = goat_tools.goat_search(
                    "offline query",
                    transport=_router(
                        calls,
                        ddg={
                            "status": 429,
                            "body": "slow",
                            "headers": {"Retry-After": "2"},
                        },
                    ),
                    **kwargs,
                )
                self.assertEqual(
                    raw,
                    {
                        "error": {"code": "RATE_LIMITED"},
                        "status": 429,
                        "retry_after": 2,
                    },
                )
                self.assertEqual(len(calls), 1)
                # Ordinary non-2xx keeps HTTP_ERROR, no failover.
                calls = []
                raw = goat_tools.goat_search(
                    "offline query",
                    transport=_router(
                        calls, ddg={"status": 503, "body": ORDINARY_503_HTML}
                    ),
                    **kwargs,
                )
                self.assertEqual(
                    raw, {"error": {"code": "HTTP_ERROR"}, "status": 503}
                )
                self.assertEqual(len(calls), 1)
                # Legitimate empty SERP stays an empty success, no failover.
                calls = []
                raw = goat_tools.goat_search(
                    "offline query",
                    transport=_router(
                        calls, ddg={"status": 200, "body": EMPTY_NO_RESULTS_HTML}
                    ),
                    **kwargs,
                )
                self.assertEqual(raw, {"results": []})
                self.assertEqual(len(calls), 1)
                self.assertEqual(self.network_attempts, [])


if __name__ == "__main__":
    unittest.main()
