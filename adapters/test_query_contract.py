"""Free-query result-boundary tests (offline, fakes only)."""

import json
import socket
import unittest
from unittest import mock

import answer_synth
import deep_verticals as dv
import free_search as fs
import free_stack as fst
import free_verticals as fv
from search_filters import with_search_filters


PUBLIC_CODES = frozenset(("URL_BLOCKED", "REDIRECT_BLOCKED", "MISSING_CONFIG"))


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        response = self.responses.pop(0) if self.responses else {"status": 404, "body": "x"}
        if isinstance(response, BaseException):
            raise response
        return response


def assert_nested(testcase, result, expected):
    testcase.assertIsInstance(result, dict)
    testcase.assertIs(result.get("ok"), False)
    testcase.assertEqual(result.get("error"), {"code": expected})
    testcase.assertIn(expected, PUBLIC_CODES)


class QueryContractTests(unittest.TestCase):
    def setUp(self):
        self._dns = mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("no DNS"))
        self._conn = mock.patch.object(socket, "create_connection", side_effect=AssertionError("no connect"))
        self._dns.start()
        self._conn.start()
        self.addCleanup(self._dns.stop)
        self.addCleanup(self._conn.stop)

    def test_free_query_success_preserves_ok_and_fields(self):
        ddg_body = '<a class="result__a" href="https://results.example.org/cats">Cats</a>'
        wiki_body = json.dumps(["q", ["T"], ["S"], ["https://en.wikipedia.org/wiki/T"]])
        image_payload = {"query": {"pages": [{"pageid": 1, "title": "File:X.jpg", "imageinfo": [{"url": "https://upload.wikimedia.org/x.jpg", "extmetadata": {"LicenseShortName": {"value": "CC-BY"}}}]}]}}
        cases = [
            ("free_search.duckduckgo_search", lambda: fs.duckduckgo_search("cats", transport=FakeTransport({"status": 200, "body": ddg_body}))),
            ("free_search.ddg_search", lambda: fs.ddg_search("cats", transport=FakeTransport({"status": 200, "body": ddg_body}))),
            ("free_search.wikipedia_search", lambda: fs.wikipedia_search("cats", transport=FakeTransport({"status": 200, "body": wiki_body}))),
            ("free_search.wikipedia_opensearch_search", lambda: fs.wikipedia_opensearch_search("cats", transport=FakeTransport({"status": 200, "body": wiki_body}))),
            ("free_stack.duckduckgo_search", lambda: fst.duckduckgo_search("cats", transport=FakeTransport('<a class="result__a" href="https://d.example/">D</a>'))),
            ("free_stack.ddg_search", lambda: fst.ddg_search("cats", transport=FakeTransport('<a class="result__a" href="https://d.example/">D</a>'))),
            ("free_stack.wikipedia_search", lambda: fst.wikipedia_search("cats", transport=FakeTransport('{"query": {"search": [{"title": "W", "snippet": "s"}]}}'))),
            ("free_stack.wikipedia_action_search", lambda: fst.wikipedia_action_search("cats", transport=FakeTransport('{"query": {"search": [{"title": "W", "snippet": "s"}]}}'))),
            ("free_verticals.scholar_search", lambda: fv.scholar_search("ml", transport=FakeTransport({"body": json.dumps({"message": {"items": [{"DOI": "10.1000/demo", "title": ["T"], "URL": "https://doi.org/10.1000/demo"}]}})}))),
            ("free_verticals.news_search", lambda: fv.news_search("topic", transport=FakeTransport({"body": json.dumps({"articles": [{"title": "H", "url": "https://news.example.org/s"}]})}))),
            ("free_verticals.image_search", lambda: fv.image_search("cats", transport=FakeTransport({"body": json.dumps(image_payload)}))),
            ("deep_verticals.stooq_daily", lambda: dv.stooq_daily("aapl.us", transport=FakeTransport("Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,0.5,1.5,100\n"))),
            ("deep_verticals.nvd_cve_lookup", lambda: dv.nvd_cve_lookup("CVE-2024-12345", transport=FakeTransport({"totalResults": 1, "vulnerabilities": [{"cve": {"id": "CVE-2024-12345", "descriptions": [{"lang": "en", "value": "v"}]}}]}))),
            ("deep_verticals.crossref_doi_lookup", lambda: dv.crossref_doi_lookup("10.1000/demo", transport=FakeTransport({"message": {"DOI": "10.1000/demo", "title": ["T"]}}))),
            ("deep_verticals.open_meteo_forecast", lambda: dv.open_meteo_forecast(52.5, 13.4, transport=FakeTransport(json.dumps({"latitude": 52.5, "longitude": 13.4, "timezone": "UTC", "current": {"temperature_2m": 20.0}})))),
            ("deep_verticals.frankfurter_rates", lambda: dv.frankfurter_rates("EUR", ["USD"], transport=FakeTransport(json.dumps([{"date": "2024-01-02", "base": "EUR", "quote": "USD", "rate": 1.1}])))),
        ]
        for name, call in cases:
            with self.subTest(op=name):
                result = call()
                self.assertIs(result.get("ok"), True)
                # Preserve existing payload keys without replacement.
                preserved = any(k in result for k in ("results", "prices", "work", "rates", "current", "cve", "answer", "sources", "symbol", "doi", "cve_id"))
                self.assertTrue(preserved, name)

    def test_free_query_errors_are_nested_public(self):
        cases = [
            ("free_search.duckduckgo_search", lambda: fs.duckduckgo_search("", transport=FakeTransport({"status": 200, "body": "x"}))),
            ("free_search.ddg_search", lambda: fs.ddg_search("", transport=FakeTransport({"status": 200, "body": "x"}))),
            ("free_search.wikipedia_search", lambda: fs.wikipedia_search("", transport=FakeTransport({"status": 200, "body": "x"}))),
            ("free_search.wikipedia_opensearch_search", lambda: fs.wikipedia_opensearch_search("", transport=FakeTransport({"status": 200, "body": "x"}))),
            ("free_search.searxng_search", lambda: fs.searxng_search("q", provider_config=None, transport=FakeTransport({"status": 200, "body": "x"}))),
            ("free_stack.duckduckgo_search", lambda: fst.duckduckgo_search("", transport=FakeTransport("x"))),
            ("free_stack.ddg_search", lambda: fst.ddg_search("", transport=FakeTransport("x"))),
            ("free_stack.wikipedia_search", lambda: fst.wikipedia_search("", transport=FakeTransport("x"))),
            ("free_stack.wikipedia_action_search", lambda: fst.wikipedia_action_search("", transport=FakeTransport("x"))),
            ("free_stack.searxng_search", lambda: fst.searxng_search("q", instance_url=None, transport=FakeTransport("x"))),
            ("free_verticals.scholar_search", lambda: fv.scholar_search("", transport=FakeTransport({"body": "{}"}))),
            ("free_verticals.news_search", lambda: fv.news_search("", transport=FakeTransport({"body": "{}"}))),
            ("free_verticals.image_search", lambda: fv.image_search("", transport=FakeTransport({"body": "{}"}))),
            ("deep_verticals.stooq_daily", lambda: dv.stooq_daily("bad symbol!", transport=FakeTransport("x"))),
            ("deep_verticals.nvd_cve_lookup", lambda: dv.nvd_cve_lookup("not-a-cve", transport=FakeTransport({}))),
            ("deep_verticals.crossref_doi_lookup", lambda: dv.crossref_doi_lookup("bad", transport=FakeTransport({}))),
            ("deep_verticals.open_meteo_forecast", lambda: dv.open_meteo_forecast("x", "y", transport=FakeTransport({}))),
            ("deep_verticals.frankfurter_rates", lambda: dv.frankfurter_rates("", [], transport=FakeTransport({}))),
        ]
        for name, call in cases:
            with self.subTest(op=name):
                result = call()
                self.assertIs(result.get("ok"), False)
                self.assertIsInstance(result.get("error"), dict)
                self.assertIn(result["error"].get("code"), PUBLIC_CODES)

    def test_fallback_chain_source_transitions_and_missing_stops(self):
        # MISSING_CONFIG always stops even with fallback allowed.
        result = fst.fallback_chain(
            "topic", instance_url=None, allow_fallback=True,
            searxng_transport=FakeTransport('{"results": []}'),
            wikipedia_transport=FakeTransport('{"query": {"search": [{"title": "W"}]}}'),
            ddg_transport=FakeTransport('<a href="https://d.example/">D</a>'),
        )
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("error"), {"code": "MISSING_CONFIG"})
        self.assertEqual(result.get("source"), "searxng")
        # Error preserves source/transitions, no paid providers.
        result = fst.fallback_chain(
            "topic", allow_fallback=False,
            searxng_transport=FakeTransport('{"unexpected": []}'),
            wikipedia_transport=FakeTransport('{"query": {"search": [{"title": "W"}]}}'),
            ddg_transport=FakeTransport('<a href="https://d.example/">D</a>'),
        )
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("error"), {"code": "URL_BLOCKED"})
        self.assertEqual(result.get("source"), "searxng")
        self.assertNotIn("paid", json.dumps(result).lower())
        # Success preserves source/transitions.
        result = fst.fallback_chain(
            "topic", allow_fallback=True,
            searxng_transport=FakeTransport('{"unexpected": []}'),
            wikipedia_transport=FakeTransport('{"query": {"search": [{"title": "W", "snippet": "s"}]}}'),
            ddg_transport=FakeTransport('<a href="https://d.example/">D</a>'),
        )
        self.assertIs(result.get("ok"), True)
        self.assertEqual(result.get("source"), "wikipedia")
        self.assertEqual(result.get("transitions"), [{"from": "searxng", "to": "wikipedia", "reason": "URL_BLOCKED"}])

    def test_search_filters_normalizes_legacy_and_errors(self):
        def fake_success(query, **kwargs):
            return {"results": [{"title": "t", "url": "https://example.com/a", "snippet": "s"}], "source": "fake", "transitions": ["t0"]}

        wrapped = with_search_filters(fake_success)
        self.assertTrue(callable(wrapped))
        out = wrapped("q")
        self.assertIs(out.get("ok"), True)
        self.assertEqual(out.get("source"), "fake")
        self.assertEqual(out.get("transitions"), ["t0"])

        def fake_raw_error(query, **kwargs):
            return {"error": "PROVIDER_ERROR", "source": "fake", "transitions": ["t0"], "provider": "secret"}

        out = with_search_filters(fake_raw_error)("q")
        self.assertIs(out.get("ok"), False)
        self.assertEqual(out.get("error"), {"code": "URL_BLOCKED"})
        self.assertEqual(out.get("source"), "fake")
        self.assertEqual(out.get("transitions"), ["t0"])
        self.assertNotIn("provider", out)

        payload = {"error": {"code": "REDIRECT_BLOCKED"}, "source": "fake"}
        snapshot = dict(payload)
        out = with_search_filters(lambda q, **k: payload)("q")
        self.assertEqual(out.get("error"), {"code": "REDIRECT_BLOCKED"})
        self.assertIs(out.get("ok"), False)
        self.assertEqual(payload, snapshot)

    def test_goat_answer_does_not_synthesize_from_failure(self):
        def upstream_ok_false(query):
            return {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}, "results": [
                {"title": "T", "url": "https://example.com/a", "snippet": "text here"}]}

        result = answer_synth.goat_answer("query", search=upstream_ok_false)
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("error"), {"code": "REDIRECT_BLOCKED"})
        self.assertNotIn("answer", result)

        def upstream_ok_false_results_only(query):
            return {"ok": False, "results": [
                {"title": "T", "url": "https://example.com/a", "snippet": "text here"}]}

        result = answer_synth.goat_answer("query", search=upstream_ok_false_results_only)
        self.assertIs(result.get("ok"), False)
        self.assertEqual(result.get("error"), {"code": "URL_BLOCKED"})
        self.assertNotIn("answer", result)

        def upstream_results(query):
            return {"results": [
                {"title": "Solar plan", "url": "https://news.example/solar", "snippet": "The city will build solar farms in 2027."}]}

        result = answer_synth.goat_answer("solar farms", search=upstream_results)
        self.assertIs(result.get("ok"), True)
        self.assertIn("answer", result)
        self.assertIn("sources", result)


if __name__ == "__main__":
    unittest.main()
