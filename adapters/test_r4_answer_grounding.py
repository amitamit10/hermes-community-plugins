import unittest

import answer_synth
import result_contract
from answer_synth import goat_answer


class AnswerGroundingTests(unittest.TestCase):
    def test_subject_must_be_bound_to_the_requested_relation(self):
        cases = [
            (
                "What is the capital of France?",
                "France-Germany relations",
                "https://en.wikipedia.org/wiki/France",
                "France has close relations with Germany, whose largest city Berlin is the capital of Germany.",
            ),
            (
                "Who discovered penicillin?",
                "Radium discovery",
                "https://en.wikipedia.org/wiki/Radium",
                "Smith discovered radium after reading about penicillin.",
            ),
        ]
        for query, title, url, extract in cases:
            with self.subTest(query=query):

                def fake_search(_q, _title=title, _url=url, _extract=extract):
                    return {
                        "ok": True,
                        "results": [
                            {
                                "title": _title,
                                "url": _url,
                                "extract": _extract,
                            }
                        ],
                    }

                raw = answer_synth.goat_answer.__wrapped__(
                    query, search=fake_search
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(query, search=fake_search)
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

    def test_negated_uncertain_evidence_is_insufficient(self):
        cases = [
            (
                "Who discovered penicillin?",
                "Penicillin",
                "https://en.wikipedia.org/wiki/Penicillin",
                "Fleming never discovered penicillin.",
            ),
            (
                "What is the capital of France?",
                "France",
                "https://en.wikipedia.org/wiki/France",
                "It is a myth that Paris is the capital of France.",
            ),
            (
                "What is the capital of France?",
                "France",
                "https://en.wikipedia.org/wiki/Lyon",
                "Some sources speculate that Lyon is the capital of France.",
            ),
        ]
        for query, title, url, extract in cases:
            with self.subTest(query=query, extract=extract):

                def fake_search(_q, _title=title, _url=url, _extract=extract):
                    return {
                        "ok": True,
                        "results": [
                            {
                                "title": _title,
                                "url": _url,
                                "extract": _extract,
                            }
                        ],
                    }

                raw = answer_synth.goat_answer.__wrapped__(
                    query, search=fake_search
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(query, search=fake_search)
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

    def test_conflicting_evidence_is_insufficient(self):
        cases = [
            {
                "query": "What is the capital of France?",
                "max_results": 1,
                "results": [
                    {
                        "title": "Paris",
                        "url": "https://en.wikipedia.org/wiki/Paris",
                        "extract": "Paris is the capital of France.",
                    },
                    {
                        "title": "Lyon",
                        "url": "https://en.wikipedia.org/wiki/Lyon",
                        "extract": "Lyon is the capital of France.",
                    },
                ],
            },
            {
                "query": "Who discovered penicillin?",
                "max_results": 5,
                "results": [
                    {
                        "title": "Alexander Fleming",
                        "url": "https://en.wikipedia.org/wiki/Alexander_Fleming",
                        "extract": "Alexander Fleming discovered penicillin.",
                    },
                    {
                        "title": "Penicillin",
                        "url": "https://en.wikipedia.org/wiki/Penicillin",
                        "extract": "Alexander Fleming never discovered penicillin.",
                    },
                ],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "France",
                        "url": "https://en.wikipedia.org/wiki/France",
                        "extract": "Paris is the capital of France. Lyon is the capital of France.",
                    },
                ],
            },
        ]
        for case in cases:
            with self.subTest(query=case["query"], results=case["results"]):

                def fake_search(_q, _results=case["results"]):
                    return {"ok": True, "results": list(_results)}

                raw = answer_synth.goat_answer.__wrapped__(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

    def test_fragmentary_truncated_evidence_is_insufficient(self):
        overlong_padding = "Note " * 2000
        overlong_capital = (
            overlong_padding + "Paris is the capital of France."
        )
        self.assertGreater(len(overlong_capital), 8000)
        cases = [
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "France",
                        "url": "https://en.wikipedia.org/wiki/France",
                        "extract": "Paris is the capital of France...",
                    },
                ],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "France",
                        "url": "https://en.wikipedia.org/wiki/France",
                        "extract": "Paris is the capital of France…",
                    },
                ],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "France",
                        "url": "https://en.wikipedia.org/wiki/France",
                        "extract": "Paris is the capital of",
                    },
                ],
            },
            {
                "query": "Who discovered penicillin?",
                "max_results": 5,
                "results": [
                    {
                        "title": "Penicillin",
                        "url": "https://en.wikipedia.org/wiki/Penicillin",
                        "extract": "Alexander Fleming discovered...",
                    },
                ],
            },
            {
                "query": "Who discovered penicillin?",
                "max_results": 5,
                "results": [
                    {
                        "title": "Penicillin",
                        "url": "https://en.wikipedia.org/wiki/Penicillin",
                        "extract": "Alexander Fleming discovered penicillin",
                    },
                ],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "Part one",
                        "url": "https://en.wikipedia.org/wiki/Paris",
                        "extract": "Paris is the",
                    },
                    {
                        "title": "Part two",
                        "url": "https://en.wikipedia.org/wiki/France",
                        "extract": "capital of France.",
                    },
                ],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "France",
                        "url": "https://en.wikipedia.org/wiki/France",
                        "extract": overlong_capital,
                    },
                ],
            },
        ]
        for case in cases:
            with self.subTest(query=case["query"], results=case["results"]):

                def fake_search(_q, _results=case["results"]):
                    return {"ok": True, "results": list(_results)}

                raw = answer_synth.goat_answer.__wrapped__(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

    def test_keyword_requires_complete_sentence_token_coverage(self):
        cases = [
            {
                "query": "solar farms energy policy",
                "max_results": 5,
                "results": [
                    {
                        "title": "Solar news",
                        "url": "https://example.com/solar",
                        "snippet": "The city will build solar farms in 2027.",
                    },
                ],
            },
            {
                "query": "solar farms energy policy",
                "max_results": 5,
                "results": [
                    {
                        "title": "Part one",
                        "url": "https://example.com/part-one",
                        "snippet": "Solar farms are popular",
                    },
                    {
                        "title": "Part two",
                        "url": "https://example.com/part-two",
                        "snippet": "energy policy changes daily",
                    },
                ],
            },
            {
                "query": "fission energy",
                "max_results": 5,
                "results": [
                    {
                        "title": "Fission",
                        "url": "https://example.com/fission",
                        "snippet": "Fission energy evidence here",
                    },
                ],
            },
            {
                "query": "fission energy",
                "max_results": 5,
                "results": [
                    {
                        "title": "Fission",
                        "url": "https://example.com/fission",
                        "extract": "Fission energy " + ("detail " * 1500) + "here.",
                    },
                ],
            },
        ]
        for case in cases:
            with self.subTest(query=case["query"], results=case["results"]):

                def fake_search(_q, _results=case["results"]):
                    return {"ok": True, "results": list(_results)}

                raw = answer_synth.goat_answer.__wrapped__(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

    def test_supported_fact_found_among_five_with_cap_one(self):
        import re as _re
        cases = [
            {
                "query": "What is the capital of France?",
                "expected_sentence": "Paris is the capital of France.",
                "expected_url": "https://example.com/paris",
                "wrong_fragment": "France is a country in Europe",
                "results": [
                    {
                        "title": "France capital history",
                        "url": "https://example.com/wrong",
                        "extract": "France is a country in Europe.",
                    },
                    {
                        "title": "Paris",
                        "url": "https://example.com/paris",
                        "extract": "Paris is the capital of France.",
                    },
                    {
                        "title": "Lyon",
                        "url": "https://example.com/lyon",
                        "extract": "Lyon is a city in France.",
                    },
                    {
                        "title": "Marseille",
                        "url": "https://example.com/marseille",
                        "extract": "Marseille is a port city.",
                    },
                    {
                        "title": "Nice",
                        "url": "https://example.com/nice",
                        "extract": "Nice is near the Alps.",
                    },
                ],
            },
            {
                "query": "Who discovered penicillin?",
                "expected_sentence": "Alexander Fleming discovered penicillin.",
                "expected_url": "https://example.com/fleming",
                "wrong_fragment": "Penicillin is an antibiotic",
                "results": [
                    {
                        "title": "Penicillin discovered history",
                        "url": "https://example.com/wrong",
                        "extract": "Penicillin is an antibiotic.",
                    },
                    {
                        "title": "Alexander Fleming",
                        "url": "https://example.com/fleming",
                        "extract": "Alexander Fleming discovered penicillin.",
                    },
                    {
                        "title": "Alexander Fleming duplicate",
                        "url": "https://example.com/fleming-two",
                        "extract": "Alexander Fleming discovered penicillin.",
                    },
                    {
                        "title": "Mould",
                        "url": "https://example.com/mould",
                        "extract": "Moulds grow in damp places.",
                    },
                    {
                        "title": "Lab",
                        "url": "https://example.com/lab",
                        "extract": "The lab was in London.",
                    },
                ],
            },
            {
                "query": "nuclear fission energy",
                "expected_sentence": "Nuclear fission releases energy here today.",
                "expected_url": "https://example.com/good",
                "wrong_fragment": "Nuclear history is long",
                "results": [
                    {
                        "title": "nuclear fission energy history",
                        "url": "https://example.com/wrong",
                        "snippet": "Nuclear history is long and storied.",
                    },
                    {
                        "title": "Good one",
                        "url": "https://example.com/good",
                        "snippet": "Nuclear fission releases energy here today.",
                    },
                    {
                        "title": "Good two",
                        "url": "https://example.com/good-two",
                        "snippet": "Nuclear fission releases energy here today.",
                    },
                    {
                        "title": "Other",
                        "url": "https://example.com/other",
                        "snippet": "Other details follow soon.",
                    },
                    {
                        "title": "More",
                        "url": "https://example.com/more",
                        "snippet": "More context is available.",
                    },
                ],
            },
        ]
        for case in cases:
            with self.subTest(query=case["query"]):

                def fake_search(_q, _results=case["results"]):
                    return {"ok": True, "results": list(_results)}

                raw = answer_synth.goat_answer.__wrapped__(
                    case["query"], search=fake_search, max_results=1
                )
                self.assertIn("answer", raw, raw)
                self.assertIn("sources", raw, raw)
                answer = raw.get("answer", "")
                sources = raw.get("sources", [])
                self.assertIn(case["expected_sentence"], answer)
                self.assertNotIn(case["wrong_fragment"], answer)
                self.assertNotIn(case["wrong_fragment"], str(sources))
                self.assertLessEqual(len(sources), 1)
                self.assertEqual(len(sources), 1)
                self.assertEqual(sources[0]["index"], 1)
                self.assertEqual(sources[0]["url"], case["expected_url"])
                self.assertLessEqual(len(answer), 8000)
                cited = {int(n) for n in _re.findall(r"\[(\d+)\]", answer)}
                self.assertTrue(cited)
                self.assertTrue(cited <= {item["index"] for item in sources})
                self.assertEqual(
                    {item["index"] for item in sources}, cited
                )
                for line in answer.splitlines():
                    if line.strip():
                        self.assertRegex(line, r"\[\d+\]")
                # Every listed source sentence appears identically in answer.
                for src in sources:
                    self.assertIn(case["expected_sentence"], answer)

    def test_capital_descriptor_adjectives_are_grounded(self):
        positives = [
            (
                "What is the capital of France?",
                "Paris is the capital and largest city of France.",
                "https://example.com/paris",
                "Paris",
            ),
            (
                "What is the capital of Japan?",
                "Tokyo is the capital and most populous city of Japan.",
                "https://example.com/tokyo",
                "Tokyo",
            ),
            (
                "What is the capital of Australia?",
                "Canberra is the capital city of Australia.",
                "https://example.com/canberra",
                "Canberra",
            ),
        ]
        for query, sentence, url, city in positives:
            with self.subTest(query=query, sentence=sentence):

                def fake_search(_q, _s=sentence, _u=url):
                    return {"ok": True, "results": [
                        {"title": "T", "url": _u, "extract": _s}
                    ]}

                raw = answer_synth.goat_answer.__wrapped__(
                    query, search=fake_search, max_results=5
                )
                self.assertIn("answer", raw, raw)
                self.assertIn(sentence, raw.get("answer", ""))
                self.assertIn(city, raw.get("answer", ""))

    def test_embedded_clause_actor_is_insufficient(self):
        insuff = [
            "John knew that Mary discovered penicillin.",
            "John heard Mary discovered penicillin.",
            "Mary, who studied chemistry, discovered penicillin.",
            "John said Mary discovered penicillin.",
            "According to Bob, Alice discovered penicillin.",
            "France denies that Paris is the capital of France.",
        ]
        for sentence in insuff:
            with self.subTest(sentence=sentence):
                q = "Who discovered penicillin?" if "penicillin" in sentence.casefold() or "Mary" in sentence or "Alice" in sentence or "Bob" in sentence else "What is the capital of France?"
                if "capital" in sentence.casefold():
                    q = "What is the capital of France?"

                def fake_search(_q, _s=sentence):
                    return {"ok": True, "results": [
                        {"title": "T", "url": "https://example.com/t",
                         "extract": _s}
                    ]}

                raw = answer_synth.goat_answer.__wrapped__(
                    q, search=fake_search, max_results=5
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
        with self.subTest(check="direct-actor-stays-green"):

            def good_search(_q):
                return {"ok": True, "results": [
                    {"title": "T", "url": "https://example.com/f",
                     "extract": "Alexander Fleming discovered penicillin."}
                ]}

            raw = answer_synth.goat_answer.__wrapped__(
                "Who discovered penicillin?", search=good_search,
                max_results=5,
            )
            self.assertIn("answer", raw, raw)
            self.assertIn("Alexander Fleming discovered penicillin.",
                          raw.get("answer", ""))

    def test_who_wrote_hamlet_grounded(self):
        query = "Who wrote Hamlet?"
        results = [
            {
                "title": "Hamlet",
                "url": "https://example.com/hamlet",
                "extract": "Hamlet is a tragedy by Shakespeare. William Shakespeare wrote Hamlet.",
            },
            {
                "title": "Other",
                "url": "https://example.com/other",
                "extract": "Someone wrote Macbeth yesterday.",
            },
        ]

        def fake_search(_q):
            return {"ok": True, "results": list(results)}

        raw = answer_synth.goat_answer.__wrapped__(
            query, search=fake_search, max_results=5
        )
        self.assertIn("answer", raw, raw)
        self.assertIn("sources", raw, raw)
        answer = raw.get("answer", "")
        self.assertIn("William Shakespeare wrote Hamlet.", answer)
        self.assertNotIn("Macbeth", answer)
        self.assertNotIn("tragedy by Shakespeare", answer)

    def test_supplementary_bounded_facts_stay_green(self):
        positives = [
            {
                "query": "What is the capital of Canada?",
                "sentence": "Ottawa is the capital of Canada.",
                "url": "https://example.com/ottawa",
            },
            {
                "query": "Who discovered radium?",
                "sentence": "Radium was discovered in 1898 by Marie Curie.",
                "url": "https://example.com/curie",
            },
        ]
        for case in positives:
            with self.subTest(query=case["query"]):

                def fake_search(_q, _c=case):
                    return {"ok": True, "results": [
                        {"title": "T", "url": _c["url"],
                         "extract": _c["sentence"]}
                    ]}

                raw = answer_synth.goat_answer.__wrapped__(
                    case["query"], search=fake_search, max_results=5
                )
                self.assertIn("answer", raw, raw)
                self.assertIn(case["sentence"], raw.get("answer", ""))

        with self.subTest(check="equivalent-phrasing-not-conflict"):

            def equiv_search(_q):
                return {"ok": True, "results": [
                    {"title": "A", "url": "https://example.com/a",
                     "extract": "Marie Curie discovered radium."},
                    {"title": "B", "url": "https://example.com/b",
                     "extract": "Radium was discovered in 1898 by Marie Curie."},
                ]}

            raw = answer_synth.goat_answer.__wrapped__(
                "Who discovered radium?", search=equiv_search, max_results=5
            )
            self.assertIn("answer", raw, raw)
            self.assertIn("Marie Curie", raw.get("answer", ""))

        for query in (
            "Who painted Hamlet?",
            "Who invented the device used by the scientist who discovered radium?",
        ):
            with self.subTest(query=query):

                def fake_search(_q):
                    return {"ok": True, "results": [
                        {"title": "T", "url": "https://example.com/t",
                         "extract": "Someone painted something."}
                    ]}

                raw = answer_synth.goat_answer.__wrapped__(
                    query, search=fake_search, max_results=5
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )

    def test_incomplete_ambiguous_answer_slot_is_insufficient(self):
        pronoun_cases = [
            (
                "Who discovered penicillin?",
                "Alexander Fleming",
                "https://example.com/fleming",
                "He discovered penicillin.",
            ),
            (
                "What is the capital of France?",
                "France",
                "https://example.com/france",
                "It is the capital of France.",
            ),
        ]
        for query, title, url, extract in pronoun_cases:
            with self.subTest(slot="pronoun", query=query, extract=extract):

                def fake_search(_q, _title=title, _url=url, _extract=extract):
                    return {
                        "ok": True,
                        "results": [
                            {
                                "title": _title,
                                "url": _url,
                                "extract": _extract,
                            }
                        ],
                    }

                raw = answer_synth.goat_answer.__wrapped__(
                    query, search=fake_search
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(query, search=fake_search)
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

        with self.subTest(slot="suffix-alias-distinct"):

            def alias_search(_q):
                return {"ok": True, "results": [
                    {"title": "Paris", "url": "https://example.com/paris",
                     "extract": "Paris is the capital of France."},
                    {"title": "New Paris", "url": "https://example.com/new-paris",
                     "extract": "New Paris is the capital of France."},
                ]}

            raw = answer_synth.goat_answer.__wrapped__(
                "What is the capital of France?", search=alias_search,
                max_results=5,
            )
            self.assertEqual(
                raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
            )
            self.assertNotIn("answer", raw)
            self.assertNotIn("sources", raw)

        with self.subTest(slot="date-adjunct-equivalence-green"):

            def date_search(_q):
                return {"ok": True, "results": [
                    {"title": "A", "url": "https://example.com/a",
                     "extract": "In 1928, Alexander Fleming discovered penicillin."},
                    {"title": "B", "url": "https://example.com/b",
                     "extract": "Alexander Fleming discovered penicillin."},
                ]}

            raw = answer_synth.goat_answer.__wrapped__(
                "Who discovered penicillin?", search=date_search, max_results=5
            )
            self.assertIn("answer", raw, raw)
            self.assertIn("Alexander Fleming", raw.get("answer", ""))

        with self.subTest(slot="same-named-different-wording-green"):

            def equiv_search(_q):
                return {"ok": True, "results": [
                    {"title": "A", "url": "https://example.com/a",
                     "extract": "Marie Curie discovered radium."},
                    {"title": "B", "url": "https://example.com/b",
                     "extract": "Radium was discovered in 1898 by Marie Curie."},
                ]}

            raw = answer_synth.goat_answer.__wrapped__(
                "Who discovered radium?", search=equiv_search, max_results=5
            )
            self.assertIn("answer", raw, raw)
            self.assertIn("Marie Curie", raw.get("answer", ""))

    def test_unsupported_query_polarity_or_relation_is_insufficient(self):
        cases = [
            (
                "What is not the capital of France?",
                "Paris is the capital of France.",
            ),
            (
                "Who discovered the capital of France?",
                "Paris is the capital of France.",
            ),
        ]
        for query, extract in cases:
            with self.subTest(query=query):

                def fake_search(_q, _extract=extract):
                    return {
                        "ok": True,
                        "results": [
                            {
                                "title": "France",
                                "url": "https://en.wikipedia.org/wiki/France",
                                "extract": _extract,
                            }
                        ],
                    }

                raw = answer_synth.goat_answer.__wrapped__(
                    query, search=fake_search
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(query, search=fake_search)
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

    def test_direct_negation_conflicts_are_insufficient(self):
        cases = [
            {
                "query": "What is the capital of France?",
                "max_results": 1,
                "results": [
                    {
                        "title": "Paris",
                        "url": "https://example.com/paris",
                        "extract": "Paris is the capital of France.",
                    },
                    {
                        "title": "Paris negative",
                        "url": "https://example.com/paris-negative",
                        "extract": "Paris is not the capital of France.",
                    },
                ],
            },
            {
                "query": "Who discovered penicillin?",
                "max_results": 1,
                "results": [
                    {
                        "title": "Alexander Fleming",
                        "url": "https://example.com/fleming",
                        "extract": "Alexander Fleming discovered penicillin.",
                    },
                    {
                        "title": "Penicillin negative",
                        "url": "https://example.com/penicillin-negative",
                        "extract": "Alexander Fleming did not discover penicillin.",
                    },
                ],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 1,
                "results": [
                    {
                        "title": "France",
                        "url": "https://example.com/france",
                        "extract": "Paris is the capital of France. Paris is not the capital of France.",
                    },
                ],
            },
            {
                "query": "Who discovered penicillin?",
                "max_results": 1,
                "results": [
                    {
                        "title": "Penicillin",
                        "url": "https://example.com/penicillin",
                        "extract": "Alexander Fleming discovered penicillin. Alexander Fleming did not discover penicillin.",
                    },
                ],
            },
        ]
        for case in cases:
            with self.subTest(query=case["query"], results=case["results"]):

                def fake_search(_q, _results=case["results"]):
                    return {"ok": True, "results": list(_results)}

                raw = answer_synth.goat_answer.__wrapped__(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )

    def test_empty_unknown_multihop_is_insufficient(self):
        cases = [
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "France",
                        "url": "https://en.wikipedia.org/wiki/France",
                    },
                ],
            },
            {
                "query": "Who discovered penicillin?",
                "max_results": 5,
                "results": [
                    {
                        "title": "Penicillin",
                        "url": "https://en.wikipedia.org/wiki/Penicillin",
                        "extract": "",
                    },
                ],
            },
            {
                "query": "What is the capital of France?",
                "max_results": 5,
                "results": [
                    {
                        "title": "Canada",
                        "url": "https://en.wikipedia.org/wiki/Canada",
                        "extract": "Ottawa is the capital of Canada.",
                    },
                ],
            },
            {
                "query": "Who invented the device used by the scientist who discovered radium?",
                "max_results": 5,
                "results": [
                    {
                        "title": "Marie Curie",
                        "url": "https://en.wikipedia.org/wiki/Marie_Curie",
                        "extract": "Marie Curie discovered radium.",
                    },
                ],
            },
        ]
        for case in cases:
            with self.subTest(query=case["query"], results=case["results"]):

                def fake_search(_q, _results=case["results"]):
                    return {"ok": True, "results": list(_results)}

                raw = answer_synth.goat_answer.__wrapped__(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE"
                )
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)
                decorated = goat_answer(
                    case["query"],
                    search=fake_search,
                    max_results=case["max_results"],
                )
                self.assertEqual(
                    decorated.get("error", {}).get("code"),
                    result_contract.public_error_code("INSUFFICIENT_EVIDENCE"),
                )
        with self.subTest(check="missing-callable-only-missing-config"):
            raw = answer_synth.goat_answer.__wrapped__(
                "What is the capital of France?", search=None
            )
            self.assertEqual(
                raw.get("error", {}).get("code"), "MISSING_CONFIG"
            )
        with self.subTest(check="malformed-still-url-blocked"):

            def bad_search(_q):
                return {"ok": True, "results": "not-a-list"}

            raw = answer_synth.goat_answer.__wrapped__(
                "What is the capital of France?", search=bad_search
            )
            self.assertEqual(
                raw.get("error", {}).get("code"), "URL_BLOCKED"
            )


if __name__ == "__main__":
    unittest.main()
