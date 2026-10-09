"""Fake-only tests for browser_tier; no browser or network access is used."""

import json
import unittest
from urllib.parse import urlencode

from browser_tier import (
    BrowserTier,
    WAYBACK_AVAILABLE,
    cloudflare_bypass,
    recover_blocked_page,
    render_js,
)
from url_gate import REDIRECT_BLOCKED, URL_BLOCKED, URLGateError, check_url


class FakeTransport:
    def __init__(self, routes=None, default=None):
        self.routes = dict(routes or {})
        self.default = default if default is not None else {"status": 404, "body": "not found"}
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        value = self.routes.get(url, self.default)
        if isinstance(value, Exception):
            raise value
        return value(url) if callable(value) else value


class FakeBrowser:
    def __init__(self, *, body="<html>rendered page content</html>", final_url=None, action=None):
        self.body = body
        self.final_url = final_url
        self.action = action
        self.calls = []

    def __call__(self, url, *, request_gate):
        self.calls.append(url)
        if self.action is not None:
            return self.action(url, request_gate)
        request_gate(url)
        return {
            "status": 200,
            "body": self.body,
            "url": self.final_url or url,
            "requests": [url],
        }


class BrowserTierTests(unittest.TestCase):
    def test_rejects_bad_start_url_before_transport(self):
        transport = FakeTransport()
        result = BrowserTier(transport=transport).fetch("http://example.com/")
        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(transport.calls, [])

    def test_redirect_to_private_target_is_blocked_before_second_fetch(self):
        start = "https://example.com/start"
        transport = FakeTransport({
            start: {"status": 302, "headers": {"Location": "http://127.0.0.1/admin"}},
        })
        result = BrowserTier(transport=transport).fetch(start)
        self.assertEqual(result, {"ok": False, "error": REDIRECT_BLOCKED})
        self.assertEqual(transport.calls, [start])

    def test_follows_two_explicit_public_redirects_through_gate(self):
        start = "https://example.com/start"
        middle = "https://example.com/middle"
        end = "https://www.example.net/end"
        transport = FakeTransport({
            start: {"status": 302, "headers": {"location": "/middle"}},
            middle: {"status": 307, "headers": {"location": end}},
            end: {"status": 200, "body": "public content"},
        })
        result = BrowserTier(transport=transport).fetch(start)
        self.assertTrue(result["ok"])
        self.assertEqual(result["url"], end)
        self.assertEqual(transport.calls, [start, middle, end])
        self.assertTrue(all(check_url(url)[0] for url in transport.calls))

    def test_blocks_third_redirect_hop(self):
        start = "https://example.com/0"
        one = "https://example.com/1"
        two = "https://example.com/2"
        transport = FakeTransport({
            start: {"status": 302, "headers": {"location": "/1"}},
            one: {"status": 302, "headers": {"location": "/2"}},
            two: {"status": 302, "headers": {"location": "/3"}},
        })
        result = BrowserTier(transport=transport).fetch(start)
        self.assertEqual(result, {"ok": False, "error": REDIRECT_BLOCKED})
        self.assertEqual(transport.calls, [start, one, two])

    def test_rejects_transport_that_hides_auto_followed_redirect(self):
        start = "https://example.com/start"
        transport = FakeTransport({
            start: {"status": 200, "url": "https://other.example/end", "body": "hidden redirect"},
        })
        result = BrowserTier(transport=transport).fetch(start)
        self.assertEqual(result, {"ok": False, "error": REDIRECT_BLOCKED})
        self.assertEqual(transport.calls, [start])

    def test_js_render_passes_gate_to_injected_cdp_callable(self):
        browser = FakeBrowser()
        result = render_js("https://example.com/app", browser)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "browser_js")
        self.assertEqual(browser.calls, ["https://example.com/app"])

    def test_js_render_blocks_private_subresource_from_gate(self):
        def action(url, request_gate):
            request_gate("https://127.0.0.1/private.js")
            return {"status": 200, "body": "should not be reached", "url": url}

        browser = FakeBrowser(action=action)
        result = render_js("https://example.com/app", browser)
        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})

    def test_js_render_blocks_private_redirect(self):
        def action(url, request_gate):
            request_gate("http://127.0.0.1/private", redirect_from=url, redirect_hops=0)
            return {"status": 200, "body": "unreachable", "url": url}

        result = render_js("https://example.com/app", FakeBrowser(action=action))
        self.assertEqual(result, {"ok": False, "error": REDIRECT_BLOCKED})

    def test_js_render_requires_redirect_evidence_for_changed_final_url(self):
        browser = FakeBrowser(final_url="https://other.example/landing")
        result = render_js("https://example.com/app", browser)
        self.assertEqual(result, {"ok": False, "error": REDIRECT_BLOCKED})

    def test_browser_request_log_is_checked(self):
        def action(url, request_gate):
            request_gate(url)
            return {
                "status": 200,
                "body": "content",
                "url": url,
                "requests": [url, "https://[::1]/private.js"],
            }

        result = render_js("https://example.com/app", FakeBrowser(action=action))
        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})

    def test_cloudflare_callable_runs_only_for_non_captcha_challenge(self):
        start = "https://example.com/article"
        transport = FakeTransport({
            start: {"status": 403, "body": "<title>Just a moment...</title>"},
        })
        browser = FakeBrowser(body="<html>article rendered after challenge</html>")
        result = cloudflare_bypass(start, transport, browser)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "cloudflare_bypass")
        self.assertEqual(browser.calls, [start])
        self.assertEqual(transport.calls, [start])

    def test_cloudflare_callable_is_not_used_for_captcha(self):
        start = "https://example.com/article"
        transport = FakeTransport({
            start: {"status": 403, "body": '<div class="cf-turnstile"></div>'},
        })
        browser = FakeBrowser()
        result = cloudflare_bypass(start, transport, browser)
        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertEqual(browser.calls, [])

    def test_recovery_returns_direct_success_without_fallback(self):
        url = "https://example.com/article"
        transport = FakeTransport({url: {"status": 200, "body": "article content"}})
        result = recover_blocked_page(url, transport=transport)
        self.assertEqual(result["source"], "transport")
        self.assertEqual(transport.calls, [url])

    def test_recovery_uses_wayback_snapshot_and_preserves_date(self):
        url = "https://example.com/article"
        lookup = WAYBACK_AVAILABLE + "?" + urlencode({"url": url})
        snapshot_url = "https://web.archive.org/web/20260102030405/https://example.com/article"
        page = "<html><title>Archived article</title><body>Saved public article text with enough content.</body></html>"
        transport = FakeTransport({
            url: {"status": 403, "body": "origin blocked"},
            lookup: {
                "status": 200,
                "body": json.dumps({"archived_snapshots": {"closest": {
                    "url": snapshot_url,
                    "timestamp": "20260102030405",
                }}}),
            },
            snapshot_url: {"status": 200, "body": page},
        })
        result = BrowserTier(transport=transport, archive_domains=()).recover(url)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "snapshot")
        self.assertEqual(result["snapshot_date"], "20260102030405")
        self.assertEqual(result["url"], snapshot_url)
        self.assertEqual(transport.calls, [url, lookup, snapshot_url])

    def test_recovery_uses_browser_last_and_gates_all_transport_urls(self):
        url = "https://example.com/app"
        transport = FakeTransport({url: {"status": 403, "body": "forbidden"}})
        browser = FakeBrowser()
        result = BrowserTier(
            transport=transport,
            browser_callable=browser,
            archive_domains=(),
        ).recover(url)
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "browser_js")
        self.assertEqual(browser.calls, [url])
        self.assertTrue(all(check_url(item)[0] for item in transport.calls))

    def test_recovery_stops_on_unsafe_origin_redirect(self):
        url = "https://example.com/article"
        transport = FakeTransport({
            url: {"status": 302, "headers": {"location": "http://169.254.169.254/latest/meta-data/"}},
        })
        browser = FakeBrowser()
        result = BrowserTier(transport=transport, browser_callable=browser).recover(url)
        self.assertEqual(result, {"ok": False, "error": REDIRECT_BLOCKED})
        self.assertEqual(transport.calls, [url])
        self.assertEqual(browser.calls, [])

    def test_recovery_api_candidates_are_gated(self):
        url = "https://example.com/article"
        api_url = "https://example.com/api/article"
        body = "API response with enough public article data."
        transport = FakeTransport({
            url: {"status": 403, "body": "forbidden"},
            api_url: {"status": 200, "body": body},
        })
        # Skip archives by providing an empty domain list; the Wayback lookup
        # returns the fake transport's ordinary 404 response.
        result = BrowserTier(transport=transport, archive_domains=()).recover(
            url,
            api_candidates=(api_url,),
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "api")
        self.assertEqual(result["url"], api_url)
        self.assertTrue(all(check_url(item)[0] for item in transport.calls))

    def test_transport_exceptions_map_to_public_url_blocked(self):
        url = "https://example.com/article"
        transport = FakeTransport({url: RuntimeError("internal diagnostic")})
        result = BrowserTier(transport=transport).fetch(url)
        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})
        self.assertNotIn("internal diagnostic", repr(result))

    def test_browser_url_gate_exception_maps_only_public_error_codes(self):
        def action(url, request_gate):
            raise URLGateError("PRIVATE_HOST")

        result = render_js("https://example.com/app", FakeBrowser(action=action))
        self.assertEqual(result, {"ok": False, "error": URL_BLOCKED})


if __name__ == "__main__":
    unittest.main()
