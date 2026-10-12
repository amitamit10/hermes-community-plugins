import unittest
import answer_synth


def _res(query, extract):
    def fake_search(_q):
        return {"ok": True, "results": [
            {"title": "Evidence1", "url": "https://example.com/e1",
             "extract": extract}
        ]}
    return answer_synth.goat_answer.__wrapped__(query, search=fake_search)


class ReviewF01Tests(unittest.TestCase):
    def test_f01_anchored_subject_identity(self):
        insuff = [
            ("Who founded Harbor?", "New Harbor was founded by Ada."),
            ("What is the capital of Arcadia?", "Outer Arcadia's capital is Riverport."),
        ]
        for q, e in insuff:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE")
                self.assertNotIn("answer", raw)
        positives = [
            ("Who founded Harbor?", "Harbor was founded by Ada.", "Harbor was founded by Ada."),
            ("What is the capital of Arcadia?", "Arcadia's capital is Riverport.", "Arcadia's capital is Riverport."),
            ("Who discovered cobalt?", "Ada discovered cobalt.", "Ada discovered cobalt."),
            ("What is the capital of France?", "Paris is the capital of France.", "Paris is the capital of France."),
        ]
        for q, e, sub in positives:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertIn("answer", raw, raw)
                self.assertIn(sub, raw.get("answer", ""))


class ReviewF02Tests(unittest.TestCase):
    def test_f02_unresolved_actor_with_modifiers(self):
        insuff = [
            ("Who discovered cobalt?", "He also discovered cobalt."),
            ("Who discovered cobalt?", "She first discovered cobalt."),
            ("Who discovered cobalt?", "They jointly discovered cobalt."),
            ("Who discovered cobalt?", "He and Alice likewise discovered cobalt."),
        ]
        for q, e in insuff:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
                self.assertNotIn("answer", raw)
        positives = [
            ("Who discovered cobalt?", "Alice and Bob discovered cobalt.", "Alice and Bob discovered cobalt."),
            ("Who discovered penicillin?", "Alexander Fleming discovered penicillin.", "Alexander Fleming discovered penicillin."),
        ]
        for q, e, sub in positives:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertIn("answer", raw, raw)
                self.assertIn(sub, raw.get("answer", ""))


class ReviewF03Tests(unittest.TestCase):
    def test_f03_assertive_direct_actor_grammar(self):
        insuff = [
            ("Who invented the telegraph?", "Alice could have invented the telegraph."),
            ("Who invented the telegraph?", "Alice almost invented the telegraph."),
            ("Who discovered cobalt?", "Before Alice discovered cobalt."),
        ]
        for q, e in insuff:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
                self.assertNotIn("answer", raw)
        positives = [
            ("Who invented the telegraph?", "Alice invented the telegraph.", "Alice invented the telegraph."),
            ("Who discovered penicillin?", "In 1928, Alexander Fleming discovered penicillin.", "Alexander Fleming discovered penicillin."),
        ]
        for q, e, sub in positives:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertIn("answer", raw, raw)
                self.assertIn(sub, raw.get("answer", ""))

    def test_f03_proper_case_named_slots(self):
        insuff = [
            ("Who invented the telegraph?", "Alice ostensibly invented the telegraph."),
            ("Who invented the telegraph?", "Alice apparently invented the telegraph."),
            ("Who invented the telegraph?", "John observed Mary invented the telegraph."),
        ]
        for q, e in insuff:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
                self.assertNotIn("answer", raw)
        raw = _res("Who invented the telegraph?", "Alice invented the telegraph.")
        self.assertIn("answer", raw, raw)
        self.assertIn("Alice invented the telegraph.", raw.get("answer", ""))


class ReviewF04Tests(unittest.TestCase):
    def test_f04_sentence_boundaries_abbreviations(self):
        insuff = [
            ("Who discovered cobalt?", "Neither Prof. Alice nor Prof. Bob discovered cobalt."),
        ]
        for q, e in insuff:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
                self.assertNotIn("answer", raw)
        positives = [
            ("Who discovered cobalt?", "Prof. Alice discovered cobalt.", "Prof. Alice discovered cobalt."),
        ]
        for q, e, sub in positives:
            with self.subTest(query=q, extract=e):
                raw = _res(q, e)
                self.assertIn("answer", raw, raw)
                self.assertIn(sub, raw.get("answer", ""))


def _res_multi(query, extracts, max_results=5):
    def fake_search(_q, _ex=extracts):
        return {"ok": True, "results": [
            {"title": "Evidence%d" % (i + 1), "url": "https://example.com/e%d" % (i + 1),
             "extract": e}
            for i, e in enumerate(_ex)
        ]}
    return answer_synth.goat_answer.__wrapped__(query, search=fake_search, max_results=max_results)


class ReviewF05Tests(unittest.TestCase):
    def test_f05_contracted_conflicts(self):
        with self.subTest(case="discovery-ascii-max1"):
            raw = _res_multi("Who discovered cobalt?",
                             ["Ada discovered cobalt.", "Ada didn't discover cobalt."],
                             max_results=1)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="discovery-curly-samepage"):
            raw = _res_multi("Who discovered cobalt?",
                             ["Ada discovered cobalt. Ada didn\u2019t discover cobalt."],
                             max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="capital-ascii"):
            raw = _res_multi("What is the capital of Arcadia?",
                             ["Riverport is the capital of Arcadia.", "Riverport isn't the capital of Arcadia."],
                             max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="capital-curly-samepage"):
            raw = _res_multi("What is the capital of Arcadia?",
                             ["Riverport is the capital of Arcadia. Riverport isn\u2019t the capital of Arcadia."],
                             max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="unrelated-negative-kept"):
            raw = _res_multi("Who discovered cobalt?",
                             ["Ada discovered cobalt.", "Bob did not discover iron."],
                             max_results=5)
            self.assertIn("answer", raw, raw)
            self.assertIn("Ada discovered cobalt.", raw.get("answer", ""))


class ReviewF06Tests(unittest.TestCase):
    def test_f06_clipped_tail_false_fact(self):
        import free_stack
        target = "Ada discovered cobalt."
        pad = 8000 - len(target)
        reps = (pad - 4) // 9
        rem = pad - reps * 9 - 2
        prefix = "Padding. " * reps + "X" * rem + ". "
        original = prefix + "Ada discovered cobalt... trailing fragment"
        self.assertEqual(len(prefix), pad)
        self.assertEqual(len(original), 8020)
        self.assertEqual(original[:8000][-len(target):], target)
        # answer-evidence truncation must cut at verified boundary and keep flag
        truncated, flag = free_stack._truncate_answer_extract(original)
        self.assertTrue(flag)
        self.assertNotIn("Ada discovered cobalt.", truncated)
        # answer layer must not publish clipped tail as bare fact
        raw = _res_multi("Who discovered cobalt?", [original], max_results=5)
        self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
        self.assertNotIn("answer", raw)


class ReviewF06OrdinarySnippetTests(unittest.TestCase):
    def test_f06_ordinary_snippet_bounded_and_clipped_not_grounded(self):
        import json
        import free_stack
        url = "https://en.wikipedia.org/w/api.php"
        fake = lambda u: {
            "status": 200,
            "body": json.dumps({"query": {"search": [
                {"title": "Long page", "snippet": "x" * 9000},
            ]}}),
            "url": url,
        }
        res = free_stack.wikipedia_search.__wrapped__("topic", transport=fake)
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(len(res["results"][0]["snippet"]), 8000)
        self.assertTrue(res.get("truncated"))
        self.assertTrue(res["results"][0].get("snippet_cut") is True)
        # Clipped ordinary tail must not ground as a complete fact.
        target = "Ada discovered cobalt."
        pad = 8000 - len(target)
        reps = (pad - 4) // 9
        rem = pad - reps * 9 - 2
        prefix = "Padding. " * reps + "X" * rem + ". "
        original = prefix + "Ada discovered cobalt... trailing fragment"
        self.assertEqual(len(original), 8020)
        fake2 = lambda u: {
            "status": 200,
            "body": json.dumps({"query": {"search": [
                {"title": "Long page", "snippet": original},
            ]}}),
            "url": url,
        }
        res2 = free_stack.wikipedia_search.__wrapped__("topic", transport=fake2)
        self.assertEqual(len(res2["results"][0]["snippet"]), 8000)
        self.assertTrue(res2["results"][0].get("snippet_cut") is True)
        clipped = dict(res2["results"][0])
        clipped["url"] = "https://en.wikipedia.org/wiki/Long_page"
        raw = answer_synth.goat_answer.__wrapped__(
            "Who discovered cobalt?",
            search=lambda _q: {"ok": True, "results": [clipped]},
        )
        self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
        self.assertNotIn("answer", raw)
        # Control: uncut trusted fission statement still answers.
        raw2 = _res_multi("nuclear fission energy", ["Nuclear fission releases energy."])
        self.assertIn("Nuclear fission releases energy.", raw2.get("answer", ""))


class ReviewF07Tests(unittest.TestCase):
    def test_f07_keyword_complete_declarative_claim(self):
        with self.subTest(case="heading-insuff"):
            raw = _res_multi("cobalt discovery", ["Cobalt discovery."], max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="fission-positive"):
            raw = _res_multi("nuclear fission energy", ["Nuclear fission releases energy."], max_results=5)
            self.assertIn("answer", raw, raw)
            self.assertIn("Nuclear fission releases energy.", raw.get("answer", ""))
        with self.subTest(case="solar-positive"):
            raw = _res_multi("solar farms energy policy", ["Solar farms shape energy policy."], max_results=5)
            self.assertIn("answer", raw, raw)
            self.assertIn("Solar farms shape energy policy.", raw.get("answer", ""))


class ReviewF08Tests(unittest.TestCase):
    def test_f08_query_polarity_before_stopwords(self):
        with self.subTest(case="keyword-not"):
            raw = _res_multi("fission not energy", ["Nuclear fission releases energy."], max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="keyword-no"):
            raw = _res_multi("fission no energy", ["Nuclear fission releases energy."], max_results=1)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="keyword-contracted"):
            raw = _res_multi("fission don\u2019t energy", ["Nuclear fission releases energy."], max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="capital-not"):
            raw = _res_multi("What is not the capital of France?", ["Paris is the capital of France."], max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="positive-control"):
            raw = _res_multi("fission energy", ["Nuclear fission releases energy."], max_results=5)
            self.assertIn("answer", raw, raw)
            self.assertIn("Nuclear fission releases energy.", raw.get("answer", ""))


class ReviewF09Tests(unittest.TestCase):
    def test_f09_keyword_contradiction(self):
        with self.subTest(case="two-source"):
            raw = _res_multi("ziron stability",
                             ["Ziron has stability.", "Ziron has no stability."],
                             max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="before-cap-max1"):
            raw = _res_multi("ziron stability",
                             ["Ziron has stability.", "Ziron has no stability."],
                             max_results=1)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="same-page"):
            raw = _res_multi("ziron stability",
                             ["Ziron has stability. Ziron has no stability."],
                             max_results=5)
            self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
            self.assertNotIn("answer", raw)
        with self.subTest(case="unrelated-kept"):
            raw = _res_multi("ziron stability",
                             ["Ziron has stability.", "Iron has no energy."],
                             max_results=5)
            self.assertIn("answer", raw, raw)
            self.assertIn("Ziron has stability.", raw.get("answer", ""))


class ReviewF06OwnedProducerTests(unittest.TestCase):
    def test_f06_searx_ddg_clipped_owned_producer_not_grounded(self):
        import json
        import free_stack
        target = "Nuclear fission releases energy."
        pad = 8000 - len(target)
        reps = (pad - 4) // 9
        rem = pad - reps * 9 - 2
        prefix = "Padding. " * reps + "X" * rem + ". "
        text = prefix + "Nuclear fission releases energy... trailing fragment"
        self.assertEqual(len(prefix), pad)
        self.assertEqual(text[:8000][-len(target):], target)
        self.assertTrue(len(text) > 8000)
        # Searx owned-producer seam: char-clipped snippet must carry known flag.
        def fake_searx(u):
            return {
                "status": 200,
                "body": json.dumps({"results": [
                    {"title": "Evidence", "url": "https://example.com/evidence",
                     "content": text},
                ]}),
                "url": u,
            }
        sres = free_stack.searxng_search.__wrapped__("fission energy", transport=fake_searx)
        self.assertTrue(sres.get("ok"), sres)
        self.assertEqual(len(sres["results"][0]["snippet"]), 8000)
        self.assertEqual(sres["results"][0]["snippet"], text[:8000])
        self.assertTrue(sres.get("truncated"))
        self.assertTrue(sres["results"][0].get("snippet_cut") is True)
        raw = answer_synth.goat_answer.__wrapped__(
            "fission energy",
            search=lambda _q: {"ok": True, "results": [dict(sres["results"][0])]},
        )
        self.assertEqual(raw.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw)
        self.assertNotIn("answer", raw)
        # DDG analogous seam with the same owned character-clip.
        html = (
            '<a class="result__a" href="https://example.com/evidence">Evidence</a>'
            '<div class="result__snippet">' + text + "</div>"
        )
        dres = free_stack.duckduckgo_search.__wrapped__("fission energy", transport=lambda u: html)
        self.assertTrue(dres.get("ok"), dres)
        self.assertEqual(len(dres["results"][0]["snippet"]), 8000)
        self.assertEqual(dres["results"][0]["snippet"], text[:8000])
        self.assertTrue(dres.get("truncated"))
        self.assertTrue(dres["results"][0].get("snippet_cut") is True)
        raw_ddg = answer_synth.goat_answer.__wrapped__(
            "fission energy",
            search=lambda _q: {"ok": True, "results": [dict(dres["results"][0])]},
        )
        self.assertEqual(raw_ddg.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", raw_ddg)
        self.assertNotIn("answer", raw_ddg)
        # Uncut ordinary records keep exact dict without the flag.
        def fake_short(u):
            return {
                "status": 200,
                "body": json.dumps({"results": [
                    {"title": "Evidence", "url": "https://example.com/evidence",
                     "content": "Nuclear fission releases energy."},
                ]}),
                "url": u,
            }
        ures = free_stack.searxng_search.__wrapped__("fission energy", transport=fake_short)
        self.assertEqual(ures, {
            "ok": True,
            "results": [{"title": "Evidence", "url": "https://example.com/evidence",
                         "snippet": "Nuclear fission releases energy."}],
            "truncated": False,
        })
        self.assertNotIn("snippet_cut", ures["results"][0])
        raw_pos = answer_synth.goat_answer.__wrapped__(
            "fission energy",
            search=lambda _q: {"ok": True, "results": [dict(ures["results"][0])]},
        )
        self.assertIn("Nuclear fission releases energy.", raw_pos.get("answer", ""))
        # Undelimited 9k ordinary snippet stays bounded at 8000 with known flag.
        def fake_long(u):
            return {
                "status": 200,
                "body": json.dumps({"results": [
                    {"title": "Long", "url": "https://example.com/long",
                     "content": "x" * 9000},
                ]}),
                "url": u,
            }
        lres = free_stack.searxng_search.__wrapped__("topic", transport=fake_long)
        self.assertEqual(len(lres["results"][0]["snippet"]), 8000)
        self.assertTrue(lres["results"][0].get("snippet_cut") is True)


if __name__ == "__main__":
    unittest.main()
