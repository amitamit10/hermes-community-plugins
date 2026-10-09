import socket
import unittest
from unittest import mock

from native_tier import (
    MAX_CONTENT_CHARS,
    MAX_RESULTS,
    MISSING_CONFIG,
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    NativeTier,
)


class FakeSearch:
    def __init__(self, response=None, error=None):
        self.response = error if error is not None else response
        self.calls = []

    def __call__(self, query, *, limit):
        self.calls.append((query, limit))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class FakeExtract:
    def __init__(self, response=None, error=None):
        self.response = error if error is not None else response
        self.calls = []

    def __call__(self, *, urls, char_limit):
        self.calls.append((list(urls), char_limit))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class NativeTierTests(unittest.TestCase):
    def test_missing_native_callables_return_missing_config(self):
        tier = NativeTier()

        self.assertEqual(tier.search("topic"), {"ok": False, "error": MISSING_CONFIG})
        self.assertEqual(
            tier.extract("https://example.test/page"),
            {"ok": False, "error": MISSING_CONFIG},
        )

    def test_search_clamps_result_count_and_normalizes_native_results(self):
        raw_results = [
            {"title": f"Title {index}", "url": f"https://example.test/{index}", "description": f"Desc {index}"}
            for index in range(7)
        ]
        search = FakeSearch({"data": {"web": raw_results}})
        tier = NativeTier(web_search=search)

        result = tier.search("  cats  ", max_results=99)

        self.assertEqual(search.calls, [("cats", MAX_RESULTS)])
        self.assertEqual(len(result["results"]), MAX_RESULTS)
        self.assertEqual(result["results"][0], {
            "title": "Title 0",
            "url": "https://example.test/0",
            "snippet": "Desc 0",
        })
        self.assertTrue(result["truncated"])

    def test_search_fake_results_do_not_trigger_system_dns(self):
        search = FakeSearch({"data": {"web": [{
            "title": "Offline result",
            "url": "https://example.test/",
            "description": "Fixture",
        }]}})
        tier = NativeTier(web_search=search)

        with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("unexpected DNS")):
            result = tier.search("topic")

        self.assertEqual(result["results"], [{
            "title": "Offline result",
            "url": "https://example.test/",
            "snippet": "Fixture",
        }])

    def test_search_truncates_long_titles_and_snippets_at_goat_limit(self):
        search = FakeSearch({"data": {"web": [{
            "title": "t" * (MAX_CONTENT_CHARS + 1),
            "url": "https://example.test/",
            "description": "s" * (MAX_CONTENT_CHARS + 1),
        }]}})
        tier = NativeTier(web_search=search)

        result = tier.search("topic")

        item = result["results"][0]
        self.assertEqual(len(item["title"]), MAX_CONTENT_CHARS)
        self.assertEqual(len(item["snippet"]), MAX_CONTENT_CHARS)
        self.assertTrue(result["truncated"])

    def test_search_zero_limit_is_bounded_and_marks_omitted_results(self):
        search = FakeSearch({"data": {"web": [{"title": "A", "url": "https://example.test"}]}})
        tier = NativeTier(web_search=search)

        result = tier.search("topic", max_results=-3)

        self.assertEqual(search.calls, [("topic", 0)])
        self.assertEqual(result, {"ok": True, "results": [], "truncated": True})

    def test_search_rejects_empty_query_without_calling_native_tool(self):
        search = FakeSearch({"data": {"web": []}})
        tier = NativeTier(web_search=search)

        self.assertEqual(tier.search("  "), {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(search.calls, [])

    def test_search_maps_provider_errors_to_public_codes(self):
        cases = (
            ({"error": "MISSING_PROVIDER_CONFIG"}, MISSING_CONFIG),
            ({"ok": False, "error": "TOO_MANY_REDIRECTS"}, REDIRECT_BLOCKED),
            (RuntimeError("private diagnostic"), URL_BLOCKED),
        )
        for response, expected in cases:
            with self.subTest(expected=expected):
                if isinstance(response, Exception):
                    search = FakeSearch(error=response)
                else:
                    search = FakeSearch(response)
                tier = NativeTier(web_search=search)
                self.assertEqual(tier.search("topic"), {"ok": False, "error": expected})

    def test_extract_passes_one_url_and_character_cap_and_truncates_content(self):
        url = "https://example.test/page"
        extract = FakeExtract({"results": [{"url": url, "content": "x" * (MAX_CONTENT_CHARS + 20)}]})
        tier = NativeTier(web_extract=extract)

        result = tier.extract(url)

        self.assertEqual(extract.calls, [([url], MAX_CONTENT_CHARS)])
        self.assertEqual(result["url"], url)
        self.assertEqual(len(result["content"]), MAX_CONTENT_CHARS)
        self.assertTrue(result["truncated"])

    def test_extract_returns_short_content_without_truncation(self):
        url = "https://example.test/page"
        extract = FakeExtract({"results": [{"url": url, "content": "Readable text"}]})
        tier = NativeTier(web_extract=extract)

        self.assertEqual(tier.extract(url), {
            "ok": True,
            "url": url,
            "content": "Readable text",
            "truncated": False,
        })

    def test_extract_rejects_invalid_url_before_calling_native_tool(self):
        extract = FakeExtract({"results": []})
        tier = NativeTier(web_extract=extract)

        self.assertEqual(tier.extract("file:///etc/passwd"), {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(extract.calls, [])

    def test_extract_maps_native_error_and_exception(self):
        url = "https://example.test/page"
        tier = NativeTier(web_extract=FakeExtract({"results": [{"url": url, "error": "REDIRECT_FAILED"}]}))
        self.assertEqual(tier.extract(url), {"ok": False, "error": REDIRECT_BLOCKED})

        tier = NativeTier(web_extract=FakeExtract(error=RuntimeError("private diagnostic")))
        self.assertEqual(tier.extract(url), {"ok": False, "error": URL_BLOCKED})


if __name__ == "__main__":
    unittest.main()
