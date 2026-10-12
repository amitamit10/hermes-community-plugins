"""V4 review HTTP F10: JSON DATA markup is not a structural challenge (registered)."""
import importlib.util
import json
import shutil
import unittest
from pathlib import Path
from urllib.parse import urlsplit

_SPEC = importlib.util.spec_from_file_location(
    "test_v3_wiring", Path(__file__).with_name("test_v3_wiring.py")
)
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)

OfflineTestCase = _mod.OfflineTestCase
build_fixture_package = _mod.build_fixture_package
load_fixture_package = _mod.load_fixture_package
unload_fixture_package = _mod.unload_fixture_package
RecordingContext = _mod.RecordingContext

NEWS_JSON_BODY = json.dumps({
    "articles": [{
        "title": "Article",
        "url": "https://example.com/article",
        "seendate": "20261012T000000Z",
        "domain": "example.com",
        "language": "English",
        "snippet": "This code example uses <form id='challenge-form'> as plain text.",
    }]
})


class ReviewF10RegisteredTests(OfflineTestCase):
    def test_f10_registered_news_json_data_succeeds(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        wiring = module.v3_wiring
        calls = []

        def fake_fetch(url, **kwargs):
            calls.append((url, kwargs))
            self.assertEqual(kwargs.get("timeout"), 10)
            self.assertEqual(kwargs.get("max_response_bytes"), 1048576)
            self.assertEqual(kwargs.get("max_redirects"), 0)
            return {"status": 200, "headers": {}, "body": NEWS_JSON_BODY, "url": url}

        deps = wiring.default_dependencies(_fetch=fake_fetch)
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_vertical_search"]["handler"]
        payload = json.loads(handler({"vertical": "news", "query": "offline check"}))
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(len(payload.get("results", [])), 1)
        self.assertEqual(payload["results"][0]["url"], "https://example.com/article")
        self.assertEqual(len(calls), 1)
        for url, _kw in calls:
            self.assertTrue(url.startswith("https://api.gdeltproject.org/api/v2/doc/doc?"), url)


class ReviewF11RegisteredTests(OfflineTestCase):
    def test_f11_answer_http_classifier(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        vendor_stack = module.v3_wiring._vendor_stack
        for status, expected in ((403, "HTTP_ERROR"), (429, "RATE_LIMITED"), (503, "HTTP_ERROR")):
            with self.subTest(status=status):
                def fake(url, _s=status):
                    return {"status": _s, "body": "ordinary error", "url": url, "headers": {}}
                raw = vendor_stack.wikipedia_answer_search("capital Arcadia", transport=fake)
                self.assertEqual(raw.get("error", {}).get("code"), expected, raw)
        with self.subTest(case="second-request-403"):
            search_body = json.dumps({"query": {"search": [{"title": "Arcadia", "pageid": 1}]}})
            calls = []

            def fake_two(url):
                calls.append(url)
                if len(calls) == 1:
                    return {"status": 200, "body": search_body, "url": url, "headers": {}}
                return {"status": 403, "body": "ordinary error", "url": url, "headers": {}}

            raw = vendor_stack.wikipedia_answer_search("capital Arcadia", transport=fake_two)
            self.assertEqual(raw.get("error", {}).get("code"), "HTTP_ERROR", raw)
            self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
