import re
import unittest

from answer_synth import MAX_ANSWER_CHARS, MAX_RESULTS, MISSING_CONFIG, goat_answer


class FakeSearch:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, query):
        self.calls.append(query)
        return self.response


class AnswerSynthTests(unittest.TestCase):
    def test_ranks_results_and_cites_each_extracted_claim(self):
        search = FakeSearch({
            "results": [
                {
                    "title": "Weather report",
                    "url": "https://news.example/weather",
                    "snippet": "The city recorded rain last week.",
                },
                {
                    "title": "Solar energy plan",
                    "url": "https://news.example/solar",
                    "snippet": "The city will build solar farms in 2027.",
                },
            ]
        })

        result = goat_answer("solar farms energy policy", search=search)

        self.assertEqual(search.calls, ["solar farms energy policy"])
        self.assertEqual(result["sources"][0]["url"], "https://news.example/solar")
        self.assertIn("The city will build solar farms in 2027. [1]", result["answer"])
        claims = [line for line in result["answer"].splitlines() if line]
        self.assertTrue(claims)
        for claim in claims:
            self.assertRegex(claim, r"\[[1-5]\]$")
            for citation in re.findall(r"\[(\d+)\]", claim):
                self.assertLessEqual(int(citation), len(result["sources"]))

    def test_answer_and_source_count_are_bounded(self):
        search = FakeSearch({
            "results": [
                {
                    "title": f"Boundary {index}",
                    "url": f"https://news.example/{index}",
                    "snippet": "Boundary evidence. " + ("additional details " * 700),
                }
                for index in range(MAX_RESULTS + 3)
            ]
        })

        result = goat_answer("boundary evidence", search=search)

        self.assertLessEqual(len(result["answer"]), MAX_ANSWER_CHARS)
        self.assertLessEqual(len(result["sources"]), MAX_RESULTS)
        self.assertTrue(result["answer"].endswith("]"))
        for line in result["answer"].splitlines():
            cited = re.findall(r"\[(\d+)\]", line)
            self.assertTrue(cited, f"uncited claim: {line!r}")
            self.assertTrue(all(1 <= int(index) <= len(result["sources"]) for index in cited))

    def test_empty_results_return_missing_config_error(self):
        search = FakeSearch({"results": []})

        result = goat_answer("nothing found", search=search)

        self.assertEqual(result, {"error": {"code": MISSING_CONFIG}})
        self.assertEqual(search.calls, ["nothing found"])


if __name__ == "__main__":
    unittest.main()
