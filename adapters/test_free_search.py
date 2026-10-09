import json
import unittest
from urllib.parse import parse_qs, urlsplit

from free_search import (
    MAX_CONTENT_CHARS,
    MAX_RESULTS,
    MISSING_CONFIG,
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    duckduckgo_search,
    searxng_search,
    wikipedia_search,
)


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FreeSearchTests(unittest.TestCase):
    def test_duckduckgo_uses_keyless_html_endpoint_and_normalizes_results(self):
        body = '''
        <a class="result__a" href="https://results.example.org/cats">Cats &amp; Kittens</a>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fresults.example.org%2Fdogs">Dogs</a>
        <a class="result__a" href="javascript:alert(1)">Unsafe</a>
        <a class="result__a" href="https://duckduckgo.com.evil.example/redirect">Impostor</a>
        <div class="result__snippet"> First   feline snippet </div>
        <div class="result__snippet">Dog snippet</div>
        '''
        transport = FakeTransport({"status": 200, "body": body})

        result = duckduckgo_search("  cats & dogs  ", transport=transport)

        self.assertTrue(result["ok"])
        self.assertEqual(result["results"], [
            {"title": "Cats & Kittens", "url": "https://results.example.org/cats", "snippet": "First feline snippet"},
            {"title": "Dogs", "url": "https://results.example.org/dogs", "snippet": "Dog snippet"},
            {"title": "Impostor", "url": "https://duckduckgo.com.evil.example/redirect", "snippet": ""},
        ])
        self.assertFalse(result["truncated"])
        request = urlsplit(transport.calls[0])
        self.assertEqual(request.scheme, "https")
        self.assertEqual(request.netloc, "html.duckduckgo.com")
        self.assertEqual(request.path, "/html/")
        self.assertEqual(parse_qs(request.query), {"q": ["cats & dogs"]})

    def test_duckduckgo_clamps_results_and_truncates_text_at_goat_bounds(self):
        anchors = "".join(
            f'<a class="result__a" href="https://results.example.org/{i}">{"t" * (MAX_CONTENT_CHARS + 1)}</a>'
            for i in range(7)
        )
        snippets = "".join(
            f'<div class="result__snippet">{"s" * (MAX_CONTENT_CHARS + 1)}</div>'
            for _ in range(7)
        )
        transport = FakeTransport(anchors + snippets)

        result = duckduckgo_search("topic", transport=transport, max_results=999)

        self.assertEqual(len(result["results"]), MAX_RESULTS)
        self.assertEqual(len(result["results"][0]["title"]), MAX_CONTENT_CHARS)
        self.assertEqual(len(result["results"][0]["snippet"]), MAX_CONTENT_CHARS)
        self.assertTrue(result["truncated"])

    def test_duckduckgo_zero_limit_and_invalid_query_are_bounded(self):
        transport = FakeTransport('<a class="result__a" href="https://example.org">One</a>')

        result = duckduckgo_search("topic", transport=transport, max_results=-4)
        invalid = duckduckgo_search("  ", transport=transport)

        self.assertEqual(result, {"ok": True, "results": [], "truncated": True})
        self.assertEqual(invalid, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(len(transport.calls), 1)

    def test_wikipedia_uses_opensearch_api_and_normalizes_records(self):
        payload = [
            "weather in Paris",
            ["Paris", "Paris Agreement"],
            ["Capital city of France", "Climate accord"],
            ["https://en.wikipedia.org/wiki/Paris", "https://en.wikipedia.org/wiki/Paris_Agreement"],
        ]
        transport = FakeTransport({"status": 200, "body": json.dumps(payload)})

        result = wikipedia_search(" weather in Paris ", transport=transport)

        self.assertEqual(result, {
            "ok": True,
            "results": [
                {"title": "Paris", "url": "https://en.wikipedia.org/wiki/Paris", "snippet": "Capital city of France"},
                {"title": "Paris Agreement", "url": "https://en.wikipedia.org/wiki/Paris_Agreement", "snippet": "Climate accord"},
            ],
            "truncated": False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual(request.netloc, "en.wikipedia.org")
        self.assertEqual(request.path, "/w/api.php")
        self.assertEqual(parse_qs(request.query), {
            "action": ["opensearch"],
            "search": ["weather in Paris"],
            "limit": [str(MAX_RESULTS)],
            "namespace": ["0"],
            "format": ["json"],
        })

    def test_wikipedia_clamps_limit_and_rejects_malformed_response(self):
        payload = ["q", [f"title-{i}" for i in range(8)], [], [f"https://en.wikipedia.org/wiki/{i}" for i in range(8)]]
        transport = FakeTransport(json.dumps(payload), "not-json")

        result = wikipedia_search("q", transport=transport, max_results=100)
        malformed = wikipedia_search("q", transport=transport)

        self.assertEqual(len(result["results"]), MAX_RESULTS)
        self.assertTrue(result["truncated"])
        self.assertEqual(malformed, {"error": {"code": URL_BLOCKED}})

    def test_searxng_fails_closed_without_config_and_uses_injected_base_url(self):
        unconfigured_transport = FakeTransport({"results": []})
        missing = searxng_search("query")
        missing_with_transport = searxng_search("query", transport=unconfigured_transport)
        self.assertEqual(missing, {"error": {"code": MISSING_CONFIG}})
        self.assertEqual(missing_with_transport, {"error": {"code": MISSING_CONFIG}})
        self.assertEqual(unconfigured_transport.calls, [])

        transport = FakeTransport({"status": 200, "body": json.dumps({"results": [
            {"title": "Result", "url": "https://docs.example.org/page", "content": "Summary"},
        ]})})
        result = searxng_search("  query terms ", base_url="https://search.example/", transport=transport)

        self.assertEqual(result, {
            "ok": True,
            "results": [{"title": "Result", "url": "https://docs.example.org/page", "snippet": "Summary"}],
            "truncated": False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual(request.scheme, "https")
        self.assertEqual(request.netloc, "search.example")
        self.assertEqual(request.path, "/search")
        self.assertEqual(parse_qs(request.query), {"q": ["query terms"], "format": ["json"]})

    def test_searxng_reads_provider_config_and_clamps_results(self):
        payload = {"results": [
            {"title": f"Title {index}", "url": f"https://docs.example.org/{index}", "content": f"Summary {index}"}
            for index in range(8)
        ]}
        transport = FakeTransport({"body": json.dumps(payload)})

        result = searxng_search("topic", transport=transport, provider_config={"base_url": "https://search.example"}, max_results=100)

        self.assertEqual(len(result["results"]), MAX_RESULTS)
        self.assertTrue(result["truncated"])
        self.assertTrue(transport.calls[0].startswith("https://search.example/search?"))

    def test_errors_follow_goat_public_codes_and_redirects_fail_closed(self):
        missing_provider = duckduckgo_search("q", transport=FakeTransport("unused"), provider_config=None)
        bad_transport = wikipedia_search("q", transport=object())
        provider_error = duckduckgo_search("q", transport=FakeTransport(RuntimeError("private diagnostic")))
        redirected = wikipedia_search("q", transport=FakeTransport({
            "body": json.dumps(["q", [], [], []]),
            "url": "http://127.0.0.1/private",
        }))

        self.assertEqual(missing_provider, {"error": {"code": MISSING_CONFIG}})
        self.assertEqual(bad_transport, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(provider_error, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(redirected, {"error": {"code": REDIRECT_BLOCKED}})

    def test_searxng_rejects_unsafe_and_malformed_base_urls(self):
        for base_url in ("http://127.0.0.1:8080", "https://user:pass@search.example", "file:///etc"):
            with self.subTest(base_url=base_url):
                transport = FakeTransport({"results": []})
                result = searxng_search("q", base_url=base_url, transport=transport)
                self.assertEqual(result, {"error": {"code": URL_BLOCKED}})
                self.assertEqual(transport.calls, [])

    def test_searxng_rejects_empty_query(self):
        transport = FakeTransport({"results": []})

        result = searxng_search(" ", base_url="https://search.example", transport=transport)

        self.assertEqual(result, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(transport.calls, [])


if __name__ == "__main__":
    unittest.main()
