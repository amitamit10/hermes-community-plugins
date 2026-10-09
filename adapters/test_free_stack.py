import json
import unittest
from urllib.parse import parse_qs, urlsplit

from free_stack import (
    DEFAULT_SEARXNG_URL,
    MISSING_CONFIG,
    URL_BLOCKED,
    ddg_search,
    fallback_chain,
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
        if isinstance(response, BaseException):
            raise response
        return response


class FreeStackTests(unittest.TestCase):
    def test_ddg_parses_html_lite_and_decodes_redirects(self):
        fixture = '''
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fcats">Cats &amp; Kittens</a>
          <div class="result__snippet">A <b>short</b> feline summary.</div>
          <a class="result__a" href="https://example.net/dogs">Dogs</a>
          <div class="result__snippet">Canine summary</div>
          <a class="result__a" href="javascript:alert(1)">Unsafe</a>
        '''
        transport = FakeTransport(fixture)

        result = ddg_search("cats & dogs", transport=transport)

        self.assertEqual(result, {
            "ok": True,
            "results": [
                {"title": "Cats & Kittens", "url": "https://example.org/cats", "snippet": "A short feline summary."},
                {"title": "Dogs", "url": "https://example.net/dogs", "snippet": "Canine summary"},
            ],
            "truncated": False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual(request.netloc, "html.duckduckgo.com")
        self.assertEqual(request.path, "/html/")
        self.assertEqual(parse_qs(request.query), {"q": ["cats & dogs"]})

    def test_ddg_clamps_result_count_and_rejects_non_http_urls(self):
        fixture = "".join(
            f'<a class="result__a" href="https://example.org/{i}">Result {i}</a>'
            for i in range(7)
        ) + '<a class="result__a" href="javascript:alert(1)">Bad</a>'
        transport = FakeTransport(fixture)

        result = ddg_search("topic", transport=transport, max_results=500)

        self.assertEqual(len(result["results"]), 5)
        self.assertTrue(result["truncated"])
        self.assertTrue(all(item["url"].startswith("https://") for item in result["results"]))

    def test_wikipedia_uses_action_api_and_normalizes_search_results(self):
        fixture = {"query": {"search": [
            {
                "title": "Python (programming language)",
                "pageid": 23862,
                "snippet": "A <span class=\"searchmatch\">programming</span> language.",
            },
            {"title": "Monty Python", "pageid": 6130, "snippet": "British comedy group."},
        ]}}
        transport = FakeTransport(json.dumps(fixture))

        result = wikipedia_search("Python language", transport=transport)

        self.assertEqual(result, {
            "ok": True,
            "results": [
                {
                    "title": "Python (programming language)",
                    "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
                    "snippet": "A programming language.",
                },
                {
                    "title": "Monty Python",
                    "url": "https://en.wikipedia.org/wiki/Monty_Python",
                    "snippet": "British comedy group.",
                },
            ],
            "truncated": False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual(request.path, "/w/api.php")
        self.assertEqual(parse_qs(request.query), {
            "action": ["query"],
            "list": ["search"],
            "srsearch": ["Python language"],
            "srlimit": ["5"],
            "format": ["json"],
            "formatversion": ["2"],
        })

    def test_wikipedia_malformed_payload_returns_public_error_envelope(self):
        result = wikipedia_search("topic", transport=FakeTransport('{"query": {}}'))
        self.assertEqual(result, {"error": {"code": URL_BLOCKED}})

    def test_searxng_uses_configured_local_instance(self):
        fixture = {"results": [
            {"title": "Local result", "url": "https://docs.example.org/page", "content": "A summary"}
        ]}
        transport = FakeTransport(json.dumps(fixture))

        result = searxng_search("  local topic  ", instance_url="http://localhost:8888/", transport=transport)

        self.assertEqual(result, {
            "ok": True,
            "results": [{"title": "Local result", "url": "https://docs.example.org/page", "snippet": "A summary"}],
            "truncated": False,
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.scheme, request.netloc, request.path), ("http", "localhost:8888", "/search"))
        self.assertEqual(parse_qs(request.query), {"q": ["local topic"], "format": ["json"]})

    def test_searxng_defaults_to_localhost(self):
        transport = FakeTransport('{"results": []}')

        result = searxng_search("topic", transport=transport)

        self.assertEqual(result, {"ok": True, "results": [], "truncated": False})
        request = urlsplit(transport.calls[0])
        self.assertTrue(transport.calls[0].startswith(DEFAULT_SEARXNG_URL))
        self.assertEqual(request.path, "/search")

    def test_searxng_unset_instance_is_missing_config_without_fetch(self):
        transport = FakeTransport('{"results": []}')

        result = searxng_search("topic", instance_url=None, transport=transport)

        self.assertEqual(result, {"error": {"code": MISSING_CONFIG}})
        self.assertEqual(transport.calls, [])

    def test_searxng_unreachable_instance_is_missing_config(self):
        transport = FakeTransport(OSError("connection refused"))

        result = searxng_search("topic", instance_url="http://localhost:9999", transport=transport)

        self.assertEqual(result, {"error": {"code": MISSING_CONFIG}})

    def test_searxng_rejects_non_local_http_instance_without_fetch(self):
        transport = FakeTransport('{"results": []}')

        result = searxng_search("topic", instance_url="http://search.example.org", transport=transport)

        self.assertEqual(result, {"error": {"code": URL_BLOCKED}})
        self.assertEqual(transport.calls, [])

    def test_keyless_clients_convert_requires_key_errors_instead_of_raising(self):
        class RequiresKeyError(Exception):
            code = "requires_key"

        result = wikipedia_search("topic", transport=FakeTransport(RequiresKeyError()))

        self.assertEqual(result, {"error": {"code": URL_BLOCKED}})
        self.assertNotIn("requires_key", json.dumps(result))

    def test_fallback_chain_returns_first_nonempty_provider_in_order(self):
        searx = FakeTransport('{"results": [{"title": "S", "url": "https://s.example/", "content": ""}]}')
        wiki = FakeTransport('{"query": {"search": [{"title": "W", "snippet": ""}]}}')
        ddg = FakeTransport('<a class="result__a" href="https://d.example/">D</a>')

        result = fallback_chain(
            "topic",
            instance_url="http://localhost:8888",
            searxng_transport=searx,
            wikipedia_transport=wiki,
            ddg_transport=ddg,
        )

        self.assertEqual(result["source"], "searxng")
        self.assertEqual([len(searx.calls), len(wiki.calls), len(ddg.calls)], [1, 0, 0])
        self.assertEqual(result["results"][0]["title"], "S")

    def test_fallback_chain_uses_wikipedia_when_searxng_has_no_results(self):
        searx = FakeTransport('{"results": []}')
        wiki = FakeTransport('{"query": {"search": [{"title": "W", "snippet": "summary"}]}}')
        ddg = FakeTransport('<a class="result__a" href="https://d.example/">D</a>')

        result = fallback_chain(
            "topic",
            allow_fallback=True,
            searxng_transport=searx,
            wikipedia_transport=wiki,
            ddg_transport=ddg,
        )

        self.assertEqual(result["source"], "wikipedia")
        self.assertEqual(result["results"][0]["title"], "W")
        self.assertEqual([len(searx.calls), len(wiki.calls), len(ddg.calls)], [1, 1, 0])

    def test_fallback_chain_continues_after_transport_errors_to_ddg(self):
        searx = FakeTransport('{"unexpected": []}')
        wiki = FakeTransport(RuntimeError("temporary API failure"))
        ddg = FakeTransport('<a class="result__a" href="https://d.example/">D</a>')

        result = fallback_chain(
            "topic",
            allow_fallback=True,
            searxng_transport=searx,
            wikipedia_transport=wiki,
            ddg_transport=ddg,
        )

        self.assertEqual(result["ok"], True)
        self.assertEqual(result["source"], "ddg")
        self.assertEqual(result["results"][0]["title"], "D")
        self.assertEqual([len(searx.calls), len(wiki.calls), len(ddg.calls)], [1, 1, 1])


    def test_fallback_chain_missing_config_stops_even_when_fallback_is_allowed(self):
        searx = FakeTransport('{"results": []}')
        wiki = FakeTransport('{"query": {"search": [{"title": "W"}]}}')
        ddg = FakeTransport('<a class="result__a" href="https://d.example/">D</a>')

        result = fallback_chain(
            "topic",
            instance_url=None,
            allow_fallback=True,
            searxng_transport=searx,
            wikipedia_transport=wiki,
            ddg_transport=ddg,
        )

        self.assertEqual(result, {"error": {"code": MISSING_CONFIG}, "source": "searxng"})
        self.assertEqual([len(searx.calls), len(wiki.calls), len(ddg.calls)], [0, 0, 0])

    def test_fallback_chain_does_not_fallback_on_error_by_default(self):
        searx = FakeTransport('{"unexpected": []}')
        wiki = FakeTransport('{"query": {"search": [{"title": "W"}]}}')
        ddg = FakeTransport('<a class="result__a" href="https://d.example/">D</a>')

        result = fallback_chain(
            "topic",
            searxng_transport=searx,
            wikipedia_transport=wiki,
            ddg_transport=ddg,
        )

        self.assertEqual(result, {"error": {"code": URL_BLOCKED}, "source": "searxng"})
        self.assertEqual([len(searx.calls), len(wiki.calls), len(ddg.calls)], [1, 0, 0])

    def test_fallback_chain_records_error_reason_in_transition(self):
        searx = FakeTransport('{"unexpected": []}')
        wiki = FakeTransport('{"query": {"search": [{"title": "W", "snippet": "summary"}]}}')
        ddg = FakeTransport('<a class="result__a" href="https://d.example/">D</a>')

        result = fallback_chain(
            "topic",
            allow_fallback=True,
            searxng_transport=searx,
            wikipedia_transport=wiki,
            ddg_transport=ddg,
        )

        self.assertEqual(result["source"], "wikipedia")
        self.assertEqual(result["transitions"], [
            {"from": "searxng", "to": "wikipedia", "reason": URL_BLOCKED},
        ])
        self.assertEqual([len(searx.calls), len(wiki.calls), len(ddg.calls)], [1, 1, 0])

    def test_fallback_chain_records_each_empty_result_transition(self):
        searx = FakeTransport('{"results": []}')
        wiki = FakeTransport('{"query": {"search": []}}')
        ddg = FakeTransport('<a class="result__a" href="https://d.example/">D</a>')

        result = fallback_chain(
            "topic",
            allow_fallback=True,
            searxng_transport=searx,
            wikipedia_transport=wiki,
            ddg_transport=ddg,
        )

        self.assertEqual(result["source"], "ddg")
        self.assertEqual(result["transitions"], [
            {"from": "searxng", "to": "wikipedia", "reason": "NO_RESULTS"},
            {"from": "wikipedia", "to": "ddg", "reason": "NO_RESULTS"},
        ])
        self.assertEqual([len(searx.calls), len(wiki.calls), len(ddg.calls)], [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
