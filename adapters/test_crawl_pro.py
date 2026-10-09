import socket
import unittest
from unittest import mock
from urllib.parse import urlsplit

from crawl_pro import crawl_pro


BASE = "https://example.test"


class FakeTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.responses.get(url, {"status": 404, "body": ""})


def html_links(*paths):
    return "".join(f'<a href="{path}">link</a>' for path in paths)


def xml_urlset(*paths):
    entries = "".join(f'<url><loc>{BASE}{path}</loc></url>' for path in paths)
    return f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'


class CrawlProTests(unittest.TestCase):
    def test_fake_transport_does_not_trigger_system_dns(self):
        start = f"{BASE}/start"
        transport = FakeTransport({start: {"status": 200, "body": "article"}})

        with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("unexpected DNS")):
            result = crawl_pro(start, transport, respect_robots=False)

        self.assertEqual([page["url"] for page in result["pages"]], [start])
        self.assertEqual(transport.calls, [f"{BASE}/sitemap.xml", start])

    def test_crawls_same_origin_urls_listed_in_sitemap(self):
        transport = FakeTransport({
            f"{BASE}/robots.txt": {"status": 200, "body": "User-agent: *\nDisallow: /blocked"},
            f"{BASE}/sitemap.xml": {"status": 200, "body": xml_urlset("/from-sitemap")},
            f"{BASE}/start": {"status": 200, "body": html_links("/from-link", "https://elsewhere.test/nope")},
            f"{BASE}/from-sitemap": {"status": 200, "body": "<title>Map page</title>"},
            f"{BASE}/from-link": {"status": 200, "body": "<title>Linked page</title>"},
        })

        result = crawl_pro(f"{BASE}/start", transport)

        paths = {urlsplit(page["url"]).path for page in result["pages"]}
        self.assertEqual(paths, {"/start", "/from-sitemap", "/from-link"})
        self.assertEqual(result["requests_by_host"], {"example.test": len(transport.calls)})
        self.assertIn(f"{BASE}/sitemap.xml", transport.calls)
        self.assertNotIn("https://elsewhere.test/nope", transport.calls)

    def test_robots_disallow_prevents_fetching_matching_page(self):
        transport = FakeTransport({
            f"{BASE}/robots.txt": {"status": 200, "body": "User-agent: *\nDisallow: /private"},
            f"{BASE}/sitemap.xml": {"status": 200, "body": xml_urlset("/private")},
        })

        result = crawl_pro(f"{BASE}/private", transport)

        self.assertEqual(result["pages"], [])
        self.assertNotIn(f"{BASE}/private", transport.calls)
        self.assertIn(f"{BASE}/robots.txt", transport.calls)

    def test_robots_respect_flag_can_disable_robots_fetch(self):
        transport = FakeTransport({
            f"{BASE}/robots.txt": {"status": 200, "body": "User-agent: *\nDisallow: /private"},
            f"{BASE}/private": {"status": 200, "body": "private"},
        })

        result = crawl_pro(f"{BASE}/private", transport, respect_robots=False)

        self.assertEqual([page["url"] for page in result["pages"]], [f"{BASE}/private"])
        self.assertNotIn(f"{BASE}/robots.txt", transport.calls)

    def test_depth_and_page_limits_are_capped_at_three_and_twenty_five(self):
        responses = {
            f"{BASE}/robots.txt": {"status": 404, "body": ""},
            f"{BASE}/sitemap.xml": {"status": 404, "body": ""},
        }
        responses[f"{BASE}/start"] = {"status": 200, "body": html_links(*(f"/a{i}" for i in range(4)))}
        for i in range(4):
            responses[f"{BASE}/a{i}"] = {"status": 200, "body": html_links(*(f"/b{i}_{j}" for j in range(4)))}
            for j in range(4):
                responses[f"{BASE}/b{i}_{j}"] = {"status": 200, "body": html_links(f"/c{i}_{j}_0", f"/c{i}_{j}_1")}
                for k in range(2):
                    responses[f"{BASE}/c{i}_{j}_{k}"] = {"status": 200, "body": html_links("/too-deep")}

        transport = FakeTransport(responses)
        result = crawl_pro(f"{BASE}/start", transport, max_depth=99, max_pages=99)

        self.assertEqual(len(result["pages"]), 25)
        self.assertEqual(max(page["depth"] for page in result["pages"]), 3)
        self.assertNotIn(f"{BASE}/too-deep", transport.calls)
        self.assertEqual(result["requests_by_host"], {"example.test": len(transport.calls)})


if __name__ == "__main__":
    unittest.main()
