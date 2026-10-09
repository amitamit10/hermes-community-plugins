import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import urlsplit


PLUGIN_DIR = Path(__file__).parent.parent / "plugins" / "goat-web"
sys.path.insert(0, str(PLUGIN_DIR))

import goat_tools  # noqa: E402

from goat_tools import (  # noqa: E402
    MISSING_CONFIG,
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    goat_crawl,
    goat_extract,
    goat_probe,
    goat_search,
    map_error,
)
from url_gate import (  # noqa: E402
    PRIVATE_HOST,
    REDIRECT_BLOCKED as INTERNAL_REDIRECT_BLOCKED,
    URLGateError,
    _PinnedHTTPSConnection,
    pinned_fetch,
    resolve_and_validate,
)


def _gai(address):
    return (2, 1, 6, "", (address, 443))


class GoatToolsTests(unittest.TestCase):
    def test_mixed_public_and_private_dns_answers_are_rejected(self):
        calls = []

        def resolver(host, port, type=0):
            calls.append((host, port, type))
            return [_gai("8.8.8.8"), _gai("127.0.0.1")]

        with self.assertRaises(URLGateError) as raised:
            resolve_and_validate("example.com", resolver=resolver)
        self.assertEqual(raised.exception.code, PRIVATE_HOST)
        self.assertEqual(len(calls), 1)

    def test_pinned_connection_dials_ip_but_uses_hostname_for_tls(self):
        raw_socket = Mock()
        tls_socket = Mock()
        context = Mock()
        context.wrap_socket.return_value = tls_socket
        connection = _PinnedHTTPSConnection("example.com", "8.8.8.8", timeout=7)
        connection._context = context
        with patch("url_gate.socket.create_connection", return_value=raw_socket) as create:
            connection.connect()
        create.assert_called_once_with(("8.8.8.8", 443), 7, None)
        context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="example.com")
        self.assertIs(connection.sock, tls_socket)

    def test_pinned_fetch_resolves_each_redirect_host_and_preserves_host_header(self):
        responses = [
            (302, [("Location", "https://other.example/next")]),
            (200, []),
        ]
        requests = []

        class FakeResponse:
            def __init__(self, status, headers):
                self.status = status
                self._headers = headers

            def read(self, _limit):
                return b"ok"

            def getheaders(self):
                return self._headers

        class FakeConnection:
            def __init__(self, hostname, address, timeout=10):
                self.hostname = hostname
                self.address = address

            def request(self, method, path, headers):
                requests.append((self.hostname, self.address, method, path, headers))

            def getresponse(self):
                return FakeResponse(*responses.pop(0))

            def close(self):
                pass

        resolver_hosts = []

        def resolver(host, port, type=0):
            resolver_hosts.append(host)
            address = "8.8.8.8" if host == "example.com" else "1.1.1.1"
            return [_gai(address)]

        with patch("url_gate._PinnedHTTPSConnection", FakeConnection):
            result = pinned_fetch("https://example.com/start", resolver=resolver)
        self.assertEqual(result["url"], "https://other.example/next")
        self.assertEqual(resolver_hosts, ["example.com", "other.example"])
        self.assertEqual([request[4]["Host"] for request in requests], ["example.com", "other.example"])
        self.assertEqual([request[1] for request in requests], ["8.8.8.8", "1.1.1.1"])

    def test_private_dns_on_a_redirect_maps_to_redirect_blocked(self):
        resolver_hosts = []

        class FakeResponse:
            status = 302

            def read(self, _limit):
                return b""

            def getheaders(self):
                return [("Location", "https://other.example/next")]

        class FakeConnection:
            def __init__(self, _hostname, _address, timeout=10):
                pass

            def request(self, *_args, **_kwargs):
                pass

            def getresponse(self):
                return FakeResponse()

            def close(self):
                pass

        def resolver(host, port, type=0):
            resolver_hosts.append(host)
            return [_gai("8.8.8.8" if host == "example.com" else "127.0.0.1")]

        with patch("url_gate._PinnedHTTPSConnection", FakeConnection):
            with self.assertRaises(URLGateError) as raised:
                pinned_fetch("https://example.com/start", resolver=resolver)
        self.assertEqual(raised.exception.code, INTERNAL_REDIRECT_BLOCKED)
        self.assertEqual(resolver_hosts, ["example.com", "other.example"])

    def test_pinned_fetch_stops_after_two_redirect_hops(self):
        requests = []

        class FakeResponse:
            status = 302

            def __init__(self, index):
                self.location = f"/hop{index}"

            def read(self, _limit):
                return b""

            def getheaders(self):
                return [("Location", self.location)]

        class FakeConnection:
            def __init__(self, _hostname, _address, timeout=10):
                pass

            def request(self, _method, path, headers):
                requests.append(path)

            def getresponse(self):
                return FakeResponse(len(requests))

            def close(self):
                pass

        resolver_calls = []

        def resolver(host, port, type=0):
            resolver_calls.append(host)
            return [_gai("8.8.8.8")]

        with patch("url_gate._PinnedHTTPSConnection", FakeConnection):
            with self.assertRaises(URLGateError) as raised:
                pinned_fetch("https://example.com/start", resolver=resolver)
        self.assertEqual(raised.exception.code, INTERNAL_REDIRECT_BLOCKED)
        self.assertEqual(len(requests), 3)
        self.assertEqual(len(resolver_calls), 3)

    def test_register_exposes_all_public_tool_handlers(self):
        handlers = goat_tools.register()
        self.assertEqual(
            set(handlers),
            {"goat_search", "goat_extract", "goat_crawl", "goat_probe"},
        )
        self.assertIs(handlers["goat_search"], goat_search)
        self.assertIs(handlers["goat_extract"], goat_extract)
        self.assertIs(handlers["goat_crawl"], goat_crawl)
        self.assertIs(handlers["goat_probe"], goat_probe)

    def test_error_mapping_exposes_only_public_codes(self):
        for internal in (
            "BAD_SCHEME",
            "CREDENTIALS_IN_URL",
            "BAD_PORT",
            "PRIVATE_HOST",
            "URL_BLOCKED",
        ):
            with self.subTest(internal=internal):
                self.assertEqual(map_error(internal), URL_BLOCKED)
        self.assertEqual(map_error("REDIRECT_BLOCKED"), REDIRECT_BLOCKED)
        self.assertEqual(map_error("MISSING_CONFIG"), MISSING_CONFIG)
        self.assertEqual(map_error(None), MISSING_CONFIG)
        self.assertEqual(map_error("arbitrary internal diagnostic"), URL_BLOCKED)
        self.assertEqual({map_error(code) for code in ("BAD_SCHEME", "REDIRECT_BLOCKED", "MISSING_CONFIG")},
                         {URL_BLOCKED, REDIRECT_BLOCKED, MISSING_CONFIG})

    def test_search_caps_results_and_extract_truncates_content(self):
        search_html = "".join(
            '<a class="result__a" href="https://example.com/%d">Title %d</a>'
            '<div class="result__snippet">snippet %d</div>' % (index, index, index)
            for index in range(8)
        )
        search_calls = []

        def search_transport(url):
            search_calls.append(url)
            return {"status": 200, "body": search_html}

        search_result = goat_search("bounded query", transport=search_transport, max_results=5)
        self.assertEqual(set(search_result), {"results"})
        self.assertEqual(len(search_result["results"]), 5)
        self.assertEqual(len(search_calls), 1)

        large_body = "x" * 9001
        extract_result = goat_extract(
            "https://example.com/article",
            transport=lambda _url: {"status": 200, "body": large_body},
        )
        self.assertEqual(
            set(extract_result),
            {"url", "final_url", "status", "title", "text", "truncated"},
        )
        self.assertEqual(extract_result["url"], "https://example.com/article")
        self.assertEqual(extract_result["final_url"], "https://example.com/article")
        self.assertEqual(len(extract_result["text"]), 8000)
        self.assertTrue(extract_result["truncated"])

    def test_search_non_integer_max_results_uses_default_and_integer_range_is_enforced(self):
        search_html = "".join(
            f'<a class="result__a" href="https://example.com/{index}">Title {index}</a>'
            f'<div class="result__snippet">snippet {index}</div>'
            for index in range(7)
        )
        transport = lambda _url: {"status": 200, "body": search_html}

        coerced = goat_search("query", transport=transport, max_results="2")
        self.assertEqual(len(coerced["results"]), 5)
        for invalid in (0, 6):
            with self.subTest(max_results=invalid):
                self.assertEqual(
                    goat_search("query", transport=transport, max_results=invalid),
                    {"error": {"code": URL_BLOCKED}},
                )

    def test_extract_returns_documented_metadata_and_readable_text(self):
        requested_url = "https://example.com/start"
        final_url = "https://example.com/final"
        html = (
            "<html><head><title>  A &amp; B  </title></head>"
            "<body><nav>menu</nav><main><h1>Welcome</h1>"
            "<p>Readable page text.</p><script>not visible</script></main></body></html>"
        )
        result = goat_extract(
            requested_url,
            transport=lambda _url: {"status": 200, "body": html, "url": final_url},
        )
        self.assertEqual(
            result,
            {
                "url": requested_url,
                "final_url": final_url,
                "status": 200,
                "title": "A & B",
                "text": "Welcome Readable page text.",
                "truncated": False,
            },
        )

    def test_crawl_is_breadth_first_same_origin_and_bounded(self):
        pages = {"https://example.com/": []}
        for branch in "abc":
            pages[f"https://example.com/{branch}"] = []
            for child in range(1, 6):
                pages[f"https://example.com/{branch}/{child}"] = []
        pages["https://example.com/"] = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
            "https://other.example/outside",
        ]
        pages["https://example.com/a"] = ["/a/1", "/a/2", "/a/3"]
        pages["https://example.com/b"] = ["/b/1", "/b/2", "/b/3"]
        pages["https://example.com/c"] = ["/c/1", "/c/2", "/c/3"]
        calls = []

        def transport(url):
            calls.append(url)
            links = "".join(f'<a href="{link}">next</a>' for link in pages.get(url, []))
            return {"status": 200, "body": links}

        result = goat_crawl("https://example.com/", transport=transport)
        self.assertEqual(set(result), {"pages"})
        self.assertEqual(len(result["pages"]), 10)
        self.assertEqual(len(calls), 10)
        self.assertEqual(result["pages"][0]["url"], "https://example.com/")
        self.assertEqual(result["pages"][1]["url"], "https://example.com/a")
        self.assertEqual(result["pages"][2]["url"], "https://example.com/b")
        self.assertEqual([page["depth"] for page in result["pages"]], [0, 1, 1, 1, 2, 2, 2, 2, 2, 2])
        self.assertTrue(all(
            set(page) == {"url", "depth", "status", "title", "text", "truncated"}
            for page in result["pages"]
        ))
        self.assertTrue(any(url.count("/") >= 4 for url in calls))
        self.assertTrue(all(urlsplit(url).netloc == "example.com" for url in calls))

    def test_crawl_returns_schema_fields_and_applies_requested_bounds(self):
        root = "https://example.com/docs"
        bodies = {
            root: (
                "<html><head><title>Docs home</title></head><body><nav>menu</nav>"
                '<main><p>Start page.</p><a href="/guide">guide</a> '
                '<a href="/faq">faq</a></main></body></html>'
            ),
            "https://example.com/guide": (
                "<html><head><title>Guide</title></head><body><article>Guide text.</article></body></html>"
            ),
        }
        calls = []

        def transport(url):
            calls.append(url)
            return {"status": 200, "body": bodies[url], "url": url}

        result = goat_crawl(root, transport=transport, max_depth=1, max_pages=2)
        self.assertEqual(set(result), {"pages"})
        self.assertEqual(calls, [root, "https://example.com/guide"])
        self.assertEqual(
            result["pages"],
            [
                {
                    "url": root,
                    "depth": 0,
                    "status": 200,
                    "title": "Docs home",
                    "text": "Start page. guide faq",
                    "truncated": False,
                },
                {
                    "url": "https://example.com/guide",
                    "depth": 1,
                    "status": 200,
                    "title": "Guide",
                    "text": "Guide text.",
                    "truncated": False,
                },
            ],
        )

    def test_missing_provider_config_is_public_and_probe_has_fixed_fields(self):
        calls = []

        def transport(url):
            calls.append(url)
            return {"status": 204, "body": ""}

        expected_error = {"error": {"code": MISSING_CONFIG}}
        missing_results = (
            goat_search("query", transport=transport, provider_config=None),
            goat_extract("https://example.com/", transport=transport, provider_config=None),
            goat_crawl("https://example.com/", transport=transport, provider_config=None),
            goat_probe("https://example.com/", transport=transport, provider_config=None),
        )
        for result in missing_results:
            self.assertEqual(result, expected_error)
        self.assertEqual(calls, [])

        probe = goat_probe("https://example.com/", transport=transport)
        self.assertEqual(set(probe), {"ok", "status", "host"})
        self.assertEqual(probe, {"ok": True, "status": 204, "host": "example.com"})


if __name__ == "__main__":
    unittest.main()
