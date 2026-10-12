import json
import unittest
from urllib.parse import urlsplit

import answer_synth
import free_stack
import result_contract


class _TypedError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class AnswerSourcesTests(unittest.TestCase):
    def test_provider_blocked_preserved_without_evidence(self):
        def bad_search(_query):
            raise _TypedError("PROVIDER_BLOCKED")

        def bad_transport(_url):
            raise _TypedError("PROVIDER_BLOCKED")

        decorated_answer = answer_synth.goat_answer(
            "solar farms energy policy", search=bad_search
        )
        self.assertEqual(
            decorated_answer.get("error", {}).get("code"), "PROVIDER_BLOCKED"
        )
        self.assertNotIn("answer", decorated_answer)
        self.assertNotIn("sources", decorated_answer)

        decorated_wiki = free_stack.wikipedia_answer_search(
            "solar farms energy policy", transport=bad_transport
        )
        self.assertEqual(
            decorated_wiki.get("error", {}).get("code"), "PROVIDER_BLOCKED"
        )
        self.assertEqual(decorated_wiki.get("ok"), False)
        self.assertNotIn("results", decorated_wiki)

    def test_upstream_literals_follow_shared_contract(self):
        # Dependency: expected value is result_contract.public_error_code(code).
        # Currently those five map to URL_BLOCKED; a future predecessor patch
        # may accept them as distinct literals. Do not claim support here.
        for code in (
            "RATE_LIMITED",
            "HTTP_ERROR",
            "DNS_ERROR",
            "CONNECTION_ERROR",
            "UPSTREAM_TIMEOUT",
        ):
            with self.subTest(code=code):
                expected = result_contract.public_error_code(code)

                def bad_search(_query, _code=code):
                    raise _TypedError(_code)

                def bad_transport(_url, _code=code):
                    raise _TypedError(_code)

                decorated_answer = answer_synth.goat_answer(
                    "solar farms energy policy", search=bad_search
                )
                self.assertEqual(
                    decorated_answer.get("error", {}).get("code"), expected
                )
                self.assertNotIn("answer", decorated_answer)

                decorated_wiki = free_stack.wikipedia_answer_search(
                    "solar farms energy policy", transport=bad_transport
                )
                self.assertEqual(
                    decorated_wiki.get("error", {}).get("code"), expected
                )
                self.assertEqual(decorated_wiki.get("ok"), False)

    def test_fixed_source_redirect_blocked_without_followup(self):
        for variant in ("redirect", "foreign_final_url"):
            with self.subTest(variant=variant):
                calls = []

                def fake_transport(url, _variant=variant):
                    calls.append(url)
                    if _variant == "redirect":
                        return {
                            "status": 302,
                            "headers": {
                                "Location": "https://elsewhere.example/w/api.php"
                            },
                            "body": "",
                            "url": url,
                        }
                    return {
                        "status": 200,
                        "headers": {},
                        "body": json.dumps({"query": {"search": []}}),
                        "final_url": "https://elsewhere.example/w/api.php",
                    }

                result = free_stack.wikipedia_answer_search(
                    "solar farms energy policy", transport=fake_transport
                )
                self.assertEqual(
                    result.get("error", {}).get("code"), "REDIRECT_BLOCKED"
                )
                self.assertEqual(result.get("ok"), False)
                self.assertNotIn("results", result)
                self.assertEqual(len(calls), 1)
                parsed = urlsplit(calls[0])
                self.assertEqual(parsed.scheme, "https")
                self.assertEqual(
                    (parsed.hostname or "").lower(), "en.wikipedia.org"
                )
                self.assertEqual(parsed.path, "/w/api.php")

    def test_trusted_source_untrusted_strings_stay_bounded(self):
        # A. All-invalid search titles -> empty evidence, single request.
        invalid_calls = []

        def invalid_transport(url):
            invalid_calls.append(url)
            return {
                "status": 200,
                "headers": {},
                "body": json.dumps({
                    "query": {"search": [
                        {"title": "A|B|C|D|E|F|G", "pageid": 1},
                        {"title": "X" * 600, "pageid": 2},
                        {"title": "", "pageid": 3},
                        {"title": 12345, "pageid": -5},
                        {"title": "Bad\x01Title", "pageid": True},
                    ]},
                }),
                "url": url,
            }

        invalid_result = free_stack.wikipedia_answer_search(
            "bounded query", transport=invalid_transport
        )
        self.assertEqual(invalid_result.get("ok"), True)
        self.assertEqual(invalid_result.get("results"), [])
        self.assertEqual(len(invalid_calls), 1)

        # B. Unrequested + ambiguous pages never become evidence; canonical only.
        bounded_calls = []

        def bounded_transport(url):
            bounded_calls.append(url)
            if len(bounded_calls) == 1:
                return {
                    "status": 200,
                    "headers": {},
                    "body": json.dumps({
                        "query": {"search": [
                            {"title": "Paris", "pageid": 101},
                        ]},
                    }),
                    "url": url,
                }
            return {
                "status": 200,
                "headers": {},
                "body": json.dumps({
                    "query": {"pages": [
                        {
                            "pageid": 101,
                            "title": "Paris",
                            "extract": "Paris is the capital of France.",
                        },
                        {
                            "pageid": 999,
                            "title": "Lyon",
                            "extract": "Lyon is the capital of France.",
                        },
                        {
                            "pageid": 102,
                            "title": "Mercury",
                            "extract": "Mercury may refer to: a planet, a metal.",
                        },
                    ]},
                }),
                "url": url,
            }

        bounded = free_stack.wikipedia_answer_search(
            "Paris capital", transport=bounded_transport
        )
        self.assertEqual(bounded.get("ok"), True)
        results = bounded.get("results", [])
        self.assertLessEqual(len(results), 5)
        for item in results:
            self.assertLessEqual(len(item.get("extract", "")), 8000)
            self.assertEqual(
                set(item.keys()), {"title", "url", "extract", "language"}
            )
            self.assertNotIn("published_at", item)
            parsed = urlsplit(item["url"])
            self.assertEqual(parsed.scheme, "https")
            self.assertEqual(
                (parsed.hostname or "").lower(), "en.wikipedia.org"
            )
            self.assertFalse(parsed.fragment)
        total = sum(len(item.get("extract", "")) for item in results)
        self.assertLessEqual(total, 40000)
        titles = [item["title"] for item in results]
        self.assertIn("Paris", titles)
        self.assertNotIn("Lyon", titles)
        self.assertNotIn("Mercury", titles)
        urls = [item["url"] for item in results]
        self.assertIn("https://en.wikipedia.org/wiki/Paris", urls)
        self.assertEqual(len(bounded_calls), 2)
        extracts_url = bounded_calls[1]
        self.assertIn("prop=extracts", extracts_url)
        self.assertNotIn("continue", extracts_url.lower())

        # C. Query and max_results validated before any transport.
        for bad_query in ("x" * 2001,):
            pre_calls = []

            def never_transport(url):
                pre_calls.append(url)
                return {"status": 200, "headers": {}, "body": "{}", "url": url}

            bad = free_stack.wikipedia_answer_search(
                bad_query, transport=never_transport
            )
            self.assertEqual(
                bad.get("error", {}).get("code"), "URL_BLOCKED"
            )
            self.assertEqual(pre_calls, [])
        for bad_max in (0, 6, "5", True, None, 5.0):
            pre_calls = []

            def never_transport2(url):
                pre_calls.append(url)
                return {"status": 200, "headers": {}, "body": "{}", "url": url}

            bad = free_stack.wikipedia_answer_search(
                "Paris", transport=never_transport2, max_results=bad_max
            )
            self.assertEqual(
                bad.get("error", {}).get("code"), "URL_BLOCKED"
            )
            self.assertEqual(pre_calls, [])

    def test_foreign_endpoint_provenance_never_labels_english(self):
        body = json.dumps({
            "query": {"search": [
                {"title": "Paris",
                 "fullurl": "https://en.wikipedia.org/wiki/Paris",
                 "snippet": "Paris snippet."},
            ]},
        })

        def foreign_transport(url):
            return {
                "status": 200,
                "headers": {},
                "body": body,
                "final_url": "https://fr.wikipedia.org/w/api.php",
            }

        result = free_stack.wikipedia_search(
            "Paris", transport=foreign_transport
        )
        self.assertEqual(result.get("ok"), True)
        results = result.get("results", [])
        self.assertGreaterEqual(len(results), 1)
        for item in results:
            self.assertNotEqual((item.get("language") or "").lower(), "en")
            self.assertFalse(
                (item.get("language") or "").lower().startswith("en-")
            )


if __name__ == "__main__":
    unittest.main()
