import unittest
from datetime import date

from search_filters import URL_BLOCKED, with_search_filters


class FakeSearch:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def result(url="https://example.com/item", **metadata):
    return {"title": "fixture", "url": url, "snippet": "offline", **metadata}


def response(*results):
    return {"ok": True, "results": list(results), "truncated": False, "source": "fake"}


class SearchFilterTests(unittest.TestCase):
    def test_wrapper_passes_arguments_and_preserves_response_envelope(self):
        payload = response(result())
        fake = FakeSearch(payload)
        wrapped = with_search_filters(fake)

        actual = wrapped("query", limit=3)

        self.assertEqual(fake.calls, [(("query",), {"limit": 3})])
        self.assertEqual(actual, payload)
        self.assertIsNot(actual, payload)

    def test_time_range_is_inclusive_and_excludes_missing_or_invalid_dates(self):
        fake = FakeSearch(response(
            result(published_at="2024-01-01T00:00:00Z"),
            result(published_at="2024-01-01T12:00:00+00:00"),
            result(published_at="2024-01-02"),
            result(published_at="2023-12-31T23:59:59Z"),
            result(published_at="not-a-date"),
            result(),
        ))
        wrapped = with_search_filters(fake, time_after="2024-01-01", time_before=date(2024, 1, 2))

        actual = wrapped("q")

        self.assertEqual([item["published_at"] for item in actual["results"]], [
            "2024-01-01T00:00:00Z", "2024-01-01T12:00:00+00:00", "2024-01-02"
        ])
        self.assertEqual(actual["source"], "fake")
        self.assertFalse(actual["truncated"])

    def test_timestamp_epoch_is_supported_for_result_dates(self):
        fake = FakeSearch(response(result(timestamp=0), result(timestamp=1_700_000_000)))
        actual = with_search_filters(fake, time_after="1970-01-01T00:00:00Z", time_before="1970-01-01T00:00:00Z")("q")
        self.assertEqual([item["timestamp"] for item in actual["results"]], [0])

    def test_extreme_epoch_filter_fails_closed_without_raising(self):
        fake = FakeSearch(response(result()))
        wrapped = with_search_filters(fake, time_after=10 ** 10_000)

        actual = wrapped("q")

        self.assertEqual(actual, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(fake.calls, [])

    def test_invalid_time_range_fails_closed_without_calling_search(self):
        fake = FakeSearch(response(result()))
        wrapped = with_search_filters(fake, time_after="yesterday")

        actual = wrapped("q")

        self.assertEqual(actual, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(fake.calls, [])

    def test_reversed_time_range_fails_closed_without_calling_search(self):
        fake = FakeSearch(response(result()))
        actual = with_search_filters(fake, time_after="2025-01-02", time_before="2025-01-01")("q")
        self.assertEqual(actual, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(fake.calls, [])

    def test_domain_allow_and_deny_match_hosts_not_suffix_lookalikes(self):
        fake = FakeSearch(response(
            result("https://example.com/a"),
            result("https://news.example.com/b"),
            result("https://blocked.example.com/c"),
            result("https://notexample.com/d"),
            result("https://user@example.com/e"),
            result("/relative"),
        ))
        wrapped = with_search_filters(fake, allowed_domains=["example.com"], denied_domains=["blocked.example.com"])

        actual = wrapped("q")

        self.assertEqual([item["url"] for item in actual["results"]], [
            "https://example.com/a", "https://news.example.com/b"
        ])

    def test_invalid_domain_configuration_fails_closed(self):
        fake = FakeSearch(response(result()))
        actual = with_search_filters(fake, allowed_domains=["https://example.com/path"])("q")
        self.assertEqual(actual, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(fake.calls, [])

    def test_language_filter_accepts_primary_language_and_excludes_unknown(self):
        fake = FakeSearch(response(
            result(language="en"),
            result(language="en-US"),
            result(language="he"),
            result(),
            result(language="not a language"),
        ))
        actual = with_search_filters(fake, language="EN")("q")
        self.assertEqual([item["language"] for item in actual["results"]], ["en", "en-US"])

    def test_specific_language_tag_does_not_match_different_region(self):
        fake = FakeSearch(response(result(language="en"), result(language="en-GB"), result(language="en-US")))
        actual = with_search_filters(fake, language="en-US")("q")
        self.assertEqual([item["language"] for item in actual["results"]], ["en-US"])

    def test_invalid_language_fails_closed_without_calling_search(self):
        fake = FakeSearch(response(result()))
        actual = with_search_filters(fake, language="english!")("q")
        self.assertEqual(actual, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(fake.calls, [])

    def test_non_callable_backend_fails_closed(self):
        actual = with_search_filters(None)("q")
        self.assertEqual(actual, {"error": {"code": URL_BLOCKED}})

    def test_backend_error_envelope_is_preserved(self):
        payload = {"error": {"code": "MISSING_CONFIG"}}
        fake = FakeSearch(payload)
        self.assertEqual(with_search_filters(fake, language="en")("q"), payload)

    def test_backend_exception_and_malformed_payload_fail_closed(self):
        self.assertEqual(with_search_filters(FakeSearch(RuntimeError("secret details")))("q"), {"error": {"code": URL_BLOCKED}})
        self.assertEqual(with_search_filters(FakeSearch({"ok": True, "results": None}))("q"), {"error": {"code": URL_BLOCKED}})


if __name__ == "__main__":
    unittest.main()
