import sys
import unittest
from pathlib import Path


PLUGIN_DIR = Path(__file__).parent.parent / "plugins" / "goat-web"
sys.path.insert(0, str(PLUGIN_DIR))

from adapters import (  # noqa: E402
    MAX_CRAWL_DEPTH,
    MAX_CRAWL_PAGES,
    SAMPLE_RSS_FEED,
    crawl_frontier,
    rss_parse,
    trafilatura_like_extract,
)


class AdapterSpikeTests(unittest.TestCase):
    def test_readable_text_placeholder_strips_boilerplate_and_normalizes_text(self):
        result = trafilatura_like_extract(
            "<html><head><title>Hidden title</title></head>"
            "<body><nav>Menu</nav><article><h1>  Hello &amp; world </h1>"
            "<p>One\n   readable paragraph.</p><script>secret()</script>"
            "<style>.x { display:none }</style></article></body></html>"
        )
        self.assertEqual(result, "Hello & world One readable paragraph.")

    def test_crawl_deduplicates_filters_origin_and_clamps_depth(self):
        root = "https://example.test/"
        fixtures = {
            root: (
                '<a href="/alpha#top">alpha</a>'
                '<a href="/alpha#again">duplicate</a>'
                '<a href="/beta">beta</a>'
                '<a href="https://outside.test/page">external</a>'
                '<a href="http://example.test/insecure">different scheme</a>'
            ),
            "https://example.test/alpha": '<a href="/alpha/deep">deep</a>',
            "https://example.test/beta": '<a href="/beta/deep">deep</a>',
            "https://example.test/alpha/deep": '<a href="/too-deep">stop</a>',
            "https://example.test/beta/deep": "done",
        }
        calls = []

        def fake_transport(url):
            calls.append(url)
            return {
                "status": 202 if url.endswith("/alpha") else 200,
                "body": fixtures[url],
                "url": url,
            }

        result = crawl_frontier(root, fake_transport, max_depth=99, max_pages=99)
        self.assertTrue(result["ok"])
        self.assertEqual(
            calls,
            [
                root,
                "https://example.test/alpha",
                "https://example.test/beta",
                "https://example.test/alpha/deep",
                "https://example.test/beta/deep",
            ],
        )
        self.assertEqual(len(result["pages"]), 5)
        self.assertEqual(result["pages"][1]["status"], 202)
        self.assertEqual([page["depth"] for page in result["pages"]], [0, 1, 1, 2, 2])
        self.assertTrue(all(page["depth"] <= MAX_CRAWL_DEPTH for page in result["pages"]))
        self.assertLessEqual(len(result["pages"]), MAX_CRAWL_PAGES)
        self.assertTrue(result["truncated"])

    def test_crawl_enforces_page_limit_even_when_requested_limit_is_higher(self):
        root = "https://example.test/"
        body = "".join(f'<a href="/page-{index}">next</a>' for index in range(12))
        calls = []

        def fake_transport(url):
            calls.append(url)
            return {"status": 200, "body": body if url == root else "done"}

        result = crawl_frontier(root, fake_transport, max_pages=MAX_CRAWL_PAGES + 100)
        self.assertEqual(len(result["pages"]), MAX_CRAWL_PAGES)
        self.assertEqual(len(calls), MAX_CRAWL_PAGES)
        self.assertTrue(result["truncated"])

    def test_crawl_resolves_relative_links_against_transport_final_url(self):
        start = "https://example.test/start"
        calls = []

        def fake_transport(url):
            calls.append(url)
            if url == start:
                return {
                    "status": 200,
                    "body": '<a href="article">article</a>',
                    "final_url": "https://example.test/section/index",
                }
            return {"status": 200, "body": "article text"}

        result = crawl_frontier(start, fake_transport, max_depth=1)
        self.assertEqual(calls, [start, "https://example.test/section/article"])
        self.assertEqual(result["pages"][1]["content"], "article text")

    def test_crawl_rejects_non_callable_transport(self):
        with self.assertRaisesRegex(TypeError, "transport must be callable"):
            crawl_frontier("https://example.test/", None)

    def test_rss_sample_maps_feed_fields_to_stable_keys(self):
        self.assertEqual(
            rss_parse(SAMPLE_RSS_FEED),
            [
                {
                    "title": "Sample article",
                    "url": "https://example.com/articles/sample",
                    "summary": "A short sample summary.",
                    "published": "Fri, 09 Oct 2026 08:00:00 GMT",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
