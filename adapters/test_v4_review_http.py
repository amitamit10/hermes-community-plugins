import json
import unittest

import free_stack
import free_verticals
import result_contract


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


class ReviewF10Tests(unittest.TestCase):
    def test_f10_json_data_markup_is_data_not_challenge(self):
        with self.subTest(seam="shared-classifier"):
            self.assertIsNone(result_contract.http_error_code(200, NEWS_JSON_BODY))
        with self.subTest(seam="scalar-json-string"):
            scalar = json.dumps("<form id='challenge-form'> as plain text.")
            self.assertIsNone(result_contract.http_error_code(200, scalar))
        with self.subTest(seam="direct-news"):
            def fake_transport(url):
                return {"status": 200, "body": NEWS_JSON_BODY, "url": url, "headers": {}}
            raw = free_verticals.news_search("offline check", transport=fake_transport)
            self.assertTrue(raw.get("ok"), raw)
            self.assertEqual(len(raw.get("results", [])), 1)
            self.assertEqual(raw["results"][0]["url"], "https://example.com/article")


class ReviewF11Tests(unittest.TestCase):
    def test_f11_answer_http_classifier(self):
        for status, expected in ((403, "HTTP_ERROR"), (429, "RATE_LIMITED"), (503, "HTTP_ERROR")):
            with self.subTest(seam="direct-first", status=status):
                def fake(url, _s=status):
                    return {"status": _s, "body": "ordinary error", "url": url, "headers": {}}
                raw = free_stack.wikipedia_answer_search("capital Arcadia", transport=fake)
                self.assertEqual(raw.get("error", {}).get("code"), expected, raw)
        with self.subTest(seam="direct-second-403"):
            search_body = json.dumps({"query": {"search": [{"title": "Arcadia", "pageid": 1}]}})
            calls = []

            def fake_two(url, _calls=calls):
                _calls.append(url)
                if len(_calls) == 1:
                    return {"status": 200, "body": search_body, "url": url, "headers": {}}
                return {"status": 403, "body": "ordinary error", "url": url, "headers": {}}

            raw = free_stack.wikipedia_answer_search("capital Arcadia", transport=fake_two)
            self.assertEqual(raw.get("error", {}).get("code"), "HTTP_ERROR", raw)
            self.assertEqual(len(calls), 2)
        with self.subTest(seam="challenge-2xx"):
            def fake_ch(url):
                return {"status": 200, "body": "<html><head><title>Just a moment...</title><script src=\"/cdn-cgi/challenge-platform/x.js\"></script></head><body><form id=\"challenge-form\"></form></body></html>", "url": url, "headers": {}}
            raw = free_stack.wikipedia_answer_search("capital Arcadia", transport=fake_ch)
            self.assertEqual(raw.get("error", {}).get("code"), "PROVIDER_BLOCKED", raw)
        with self.subTest(seam="redirect-3xx"):
            def fake_redir(url):
                return {"status": 302, "body": "moved", "url": url, "headers": {"location": "https://en.wikipedia.org/w/api.php?x=1"}}
            raw = free_stack.wikipedia_answer_search("capital Arcadia", transport=fake_redir)
            self.assertEqual(raw.get("error", {}).get("code"), "REDIRECT_BLOCKED", raw)
        with self.subTest(seam="malformed-string-status"):
            valid_search = json.dumps({"query": {"search": [{"title": "Arcadia", "pageid": 1}]}})
            valid_extracts = json.dumps({"query": {"pages": [{"pageid": 1, "title": "Arcadia", "extract": "Arcadia intro."}]}})

            def fake_str(url):
                body = valid_search if "list" in url or "srsearch" in url else valid_extracts
                return {"status": "200", "body": body, "url": url, "headers": {}}

            raw = free_stack.wikipedia_answer_search("capital Arcadia", transport=fake_str)
            self.assertEqual(raw.get("error", {}).get("code"), "URL_BLOCKED", raw)
        with self.subTest(seam="malformed-float-status"):
            def fake_float(url):
                return {"status": 200.0, "body": "ordinary error", "url": url, "headers": {}}
            raw = free_stack.wikipedia_answer_search("capital Arcadia", transport=fake_float)
            self.assertEqual(raw.get("error", {}).get("code"), "URL_BLOCKED", raw)


if __name__ == "__main__":
    unittest.main()
