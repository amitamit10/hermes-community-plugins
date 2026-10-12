"""V4 review grounding regressions (wave A F01-F09) via built default register() JSON handler."""
import importlib.util
import json
import shutil
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

_SPEC = importlib.util.spec_from_file_location(
    "test_v3_wiring", Path(__file__).with_name("test_v3_wiring.py")
)
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)

OfflineTestCase = _mod.OfflineTestCase
RecordingContext = _mod.RecordingContext
build_fixture_package = _mod.build_fixture_package
load_fixture_package = _mod.load_fixture_package
unload_fixture_package = _mod.unload_fixture_package

FIXED_ENDPOINT = "https://en.wikipedia.org/w/api.php"


def _search_body(titles):
    items = [{"title": t, "pageid": 100 + i} for i, t in enumerate(titles)]
    return json.dumps({"query": {"search": items}}).encode("utf-8")


def _extracts_body(pairs):
    pages = [
        {"pageid": 100 + i, "ns": 0, "title": t, "extract": e}
        for i, (t, e) in enumerate(pairs)
    ]
    return json.dumps({"query": {"pages": pages}}).encode("utf-8")


def _run_multi(testcase, query, extracts, expect_ok, expect_sub=None, max_results=5):
    """extracts: list of extract strings -> Evidence1..n pages; 2 fixed API responses."""
    tmp, pkgdir = build_fixture_package()
    testcase.addCleanup(shutil.rmtree, tmp, True)
    module_name, module = load_fixture_package(pkgdir)
    testcase.addCleanup(unload_fixture_package, module_name)
    wiring = module.v3_wiring
    calls = []
    titles = ["Evidence%d" % (i + 1) for i in range(len(extracts))]

    def fake_fetch(url, **kwargs):
        calls.append((url, kwargs))
        testcase.assertEqual(kwargs.get("timeout"), 10)
        testcase.assertEqual(kwargs.get("max_response_bytes"), 1048576)
        testcase.assertEqual(kwargs.get("max_redirects"), 0)
        parsed = urlsplit(url)
        testcase.assertEqual(
            parsed.scheme + "://" + parsed.netloc + parsed.path,
            FIXED_ENDPOINT,
        )
        params = parse_qs(parsed.query)
        if params.get("prop") == ["extracts"]:
            return {
                "status": 200,
                "headers": {},
                "body": _extracts_body(list(zip(titles, extracts))),
                "url": url,
            }
        return {
            "status": 200,
            "headers": {},
            "body": _search_body(titles),
            "url": url,
        }

    deps = wiring.default_dependencies(_fetch=fake_fetch)
    ctx = RecordingContext()
    module.register(ctx, deps=deps)
    handler = ctx.tools["goat_answer"]["handler"]
    args = {"query": query}
    if max_results != 5:
        args["max_results"] = max_results
    payload = json.loads(handler(args))
    if expect_ok:
        testcase.assertTrue(payload.get("ok"), payload)
        if expect_sub:
            testcase.assertIn(expect_sub, payload.get("answer", ""))
    else:
        testcase.assertEqual(set(payload) - {"source", "source_url", "truncated", "transitions", "metadata", "provenance"}, {"ok", "error"}, payload)
        testcase.assertFalse(payload.get("ok"))
        code = payload.get("error", {}).get("code", "")
        testcase.assertIn("INSUFFICIENT", code, payload)
        testcase.assertNotIn("answer", payload)
    testcase.assertLessEqual(len(calls), 2)
    testcase.assertGreaterEqual(len(calls), 1)
    for url, _kw in calls:
        testcase.assertTrue(url.startswith(FIXED_ENDPOINT + "?"), url)
    return payload


def _run_queries(testcase, cases):
    """cases: list of (query, extract_text, expect_ok, expect_substr_or_None)."""
    tmp, pkgdir = build_fixture_package()
    testcase.addCleanup(shutil.rmtree, tmp, True)
    module_name, module = load_fixture_package(pkgdir)
    testcase.addCleanup(unload_fixture_package, module_name)
    wiring = module.v3_wiring
    # Group extracts by query? Each case gets its own fixture run to stay isolated.
    for query, extract, expect_ok, expect_sub in cases:
        calls = []

        def fake_fetch(url, **kwargs):
            calls.append((url, kwargs))
            testcase.assertEqual(kwargs.get("timeout"), 10)
            testcase.assertEqual(kwargs.get("max_response_bytes"), 1048576)
            testcase.assertEqual(kwargs.get("max_redirects"), 0)
            parsed = urlsplit(url)
            testcase.assertEqual(
                parsed.scheme + "://" + parsed.netloc + parsed.path,
                FIXED_ENDPOINT,
            )
            params = parse_qs(parsed.query)
            if params.get("prop") == ["extracts"]:
                return {
                    "status": 200,
                    "headers": {},
                    "body": _extracts_body([("Evidence1", extract)]),
                    "url": url,
                }
            return {
                "status": 200,
                "headers": {},
                "body": _search_body(["Evidence1"]),
                "url": url,
            }

        deps = wiring.default_dependencies(_fetch=fake_fetch)
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_answer"]["handler"]
        payload = json.loads(handler({"query": query}))
        with testcase.subTest(query=query, extract=extract):
            if expect_ok:
                testcase.assertTrue(payload.get("ok"), payload)
                testcase.assertIn(expect_sub, payload.get("answer", ""))
            else:
                testcase.assertEqual(
                    set(payload), {"ok", "error"}, payload
                )
                testcase.assertFalse(payload.get("ok"))
                code = payload.get("error", {}).get("code", "")
                # Public INSUFFICIENT code via contract mapping.
                testcase.assertIn("INSUFFICIENT", code, payload)
                testcase.assertNotIn("answer", payload)
        testcase.assertLessEqual(len(calls), 2)
        testcase.assertGreaterEqual(len(calls), 1)
        for url, _kw in calls:
            testcase.assertTrue(url.startswith(FIXED_ENDPOINT + "?"), url)


class ReviewF01AnchoredSubjectTests(OfflineTestCase):
    def test_f01_anchored_subject_identity(self):
        _run_queries(self, [
            ("Who founded Harbor?", "New Harbor was founded by Ada.", False, None),
            ("What is the capital of Arcadia?", "Outer Arcadia's capital is Riverport.", False, None),
            ("Who founded Harbor?", "Harbor was founded by Ada.", True, "Harbor was founded by Ada."),
            ("What is the capital of Arcadia?", "Arcadia's capital is Riverport.", True, "Arcadia's capital is Riverport."),
            ("Who discovered cobalt?", "Ada discovered cobalt.", True, "Ada discovered cobalt."),
            ("What is the capital of France?", "Paris is the capital of France.", True, "Paris is the capital of France."),
        ])


class ReviewF02UnresolvedActorTests(OfflineTestCase):
    def test_f02_unresolved_actor_with_modifiers(self):
        _run_queries(self, [
            ("Who discovered cobalt?", "He also discovered cobalt.", False, None),
            ("Who discovered cobalt?", "She first discovered cobalt.", False, None),
            ("Who discovered cobalt?", "They jointly discovered cobalt.", False, None),
            ("Who discovered cobalt?", "He and Alice likewise discovered cobalt.", False, None),
            ("Who discovered cobalt?", "Alice and Bob discovered cobalt.", True, "Alice and Bob discovered cobalt."),
            ("Who discovered penicillin?", "Alexander Fleming discovered penicillin.", True, "Alexander Fleming discovered penicillin."),
        ])


class ReviewF03AssertiveActorTests(OfflineTestCase):
    def test_f03_assertive_direct_actor_grammar(self):
        _run_queries(self, [
            ("Who invented the telegraph?", "Alice could have invented the telegraph.", False, None),
            ("Who invented the telegraph?", "Alice almost invented the telegraph.", False, None),
            ("Who discovered cobalt?", "Before Alice discovered cobalt.", False, None),
            ("Who invented the telegraph?", "Alice invented the telegraph.", True, "Alice invented the telegraph."),
            ("Who discovered cobalt?", "In 1928, Alexander Fleming discovered penicillin.", False, None),
            ("Who discovered penicillin?", "In 1928, Alexander Fleming discovered penicillin.", True, "In 1928, Alexander Fleming discovered penicillin."),
        ])

    def test_f03_proper_case_named_slots(self):
        _run_queries(self, [
            ("Who invented the telegraph?", "Alice ostensibly invented the telegraph.", False, None),
            ("Who invented the telegraph?", "Alice apparently invented the telegraph.", False, None),
            ("Who invented the telegraph?", "John observed Mary invented the telegraph.", False, None),
            ("Who invented the telegraph?", "Alice invented the telegraph.", True, "Alice invented the telegraph."),
        ])


class ReviewF04BoundaryTests(OfflineTestCase):
    def test_f04_sentence_boundaries_abbreviations(self):
        _run_queries(self, [
            ("Who discovered cobalt?", "Neither Prof. Alice nor Prof. Bob discovered cobalt.", False, None),
            ("Who discovered cobalt?", "Prof. Alice discovered cobalt.", True, "Prof. Alice discovered cobalt."),
        ])


class ReviewF05ContractedConflictTests(OfflineTestCase):
    def test_f05_contracted_conflicts(self):
        with self.subTest(case="discovery-ascii-max1"):
            _run_multi(self, "Who discovered cobalt?",
                       ["Ada discovered cobalt.", "Ada didn't discover cobalt."],
                       False, None, max_results=1)
        with self.subTest(case="discovery-curly-samepage"):
            _run_multi(self, "Who discovered cobalt?",
                       ["Ada discovered cobalt. Ada didn\u2019t discover cobalt."],
                       False, None, max_results=5)
        with self.subTest(case="capital-ascii"):
            _run_multi(self, "What is the capital of Arcadia?",
                       ["Riverport is the capital of Arcadia.", "Riverport isn't the capital of Arcadia."],
                       False, None, max_results=5)
        with self.subTest(case="capital-curly-samepage"):
            _run_multi(self, "What is the capital of Arcadia?",
                       ["Riverport is the capital of Arcadia. Riverport isn\u2019t the capital of Arcadia."],
                       False, None, max_results=5)
        with self.subTest(case="unrelated-negative-kept"):
            _run_multi(self, "Who discovered cobalt?",
                       ["Ada discovered cobalt.", "Bob did not discover iron."],
                       True, "Ada discovered cobalt.", max_results=5)


class ReviewF06ClippedTailTests(OfflineTestCase):
    def test_f06_clipped_tail_false_fact(self):
        target = "Ada discovered cobalt."
        pad = 8000 - len(target)
        reps = (pad - 4) // 9
        rem = pad - reps * 9 - 2
        prefix = "Padding. " * reps + "X" * rem + ". "
        original = prefix + "Ada discovered cobalt... trailing fragment"
        self.assertEqual(len(prefix), pad)
        self.assertEqual(len(original), 8020)
        self.assertEqual(original[:8000][-len(target):], target)
        # clipped tail must not become a bare complete fact
        _run_multi(self, "Who discovered cobalt?", [original], False, None, max_results=5)
        # complete earlier genuine sentences within limit remain usable is covered
        # by prior positives; never the clipped tail.


class ReviewF06OrdinarySnippetTests(OfflineTestCase):
    def test_f06_ordinary_snippet_bounded_and_clipped_not_grounded(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "adapters"))
        try:
            import free_stack
            import importlib
            importlib.reload(free_stack)
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
            # Clipped ordinary tail must not become a bare fact via default answers.
            target = "Ada discovered cobalt."
            pad = 8000 - len(target)
            reps = (pad - 4) // 9
            rem = pad - reps * 9 - 2
            prefix = "Padding. " * reps + "X" * rem + ". "
            original = prefix + "Ada discovered cobalt... trailing fragment"
            self.assertEqual(len(original), 8020)
            _run_multi(self, "Who discovered cobalt?", [original], False, None, max_results=5)
            _run_multi(self, "nuclear fission energy",
                       ["Nuclear fission releases energy."], True,
                       "Nuclear fission releases energy.", max_results=5)
        finally:
            try:
                sys.path.remove(str(Path(__file__).resolve().parents[2] / "adapters"))
            except ValueError:
                pass


class ReviewF07KeywordPredicateTests(OfflineTestCase):
    def test_f07_keyword_complete_declarative_claim(self):
        with self.subTest(case="heading-insuff"):
            _run_multi(self, "cobalt discovery", ["Cobalt discovery."], False, None, max_results=5)
        with self.subTest(case="fission-positive"):
            _run_multi(self, "nuclear fission energy",
                       ["Nuclear fission releases energy."], True,
                       "Nuclear fission releases energy.", max_results=5)
        with self.subTest(case="solar-positive"):
            _run_multi(self, "solar farms energy policy",
                       ["Solar farms shape energy policy."], True,
                       "Solar farms shape energy policy.", max_results=5)


class ReviewF08QueryPolarityTests(OfflineTestCase):
    def test_f08_query_polarity_before_stopwords(self):
        with self.subTest(case="keyword-not"):
            _run_multi(self, "fission not energy",
                       ["Nuclear fission releases energy."], False, None, max_results=5)
        with self.subTest(case="keyword-no"):
            _run_multi(self, "fission no energy",
                       ["Nuclear fission releases energy."], False, None, max_results=1)
        with self.subTest(case="keyword-contracted"):
            _run_multi(self, "fission don\u2019t energy",
                       ["Nuclear fission releases energy."], False, None, max_results=5)
        with self.subTest(case="capital-not"):
            _run_multi(self, "What is not the capital of France?",
                       ["Paris is the capital of France."], False, None, max_results=5)
        with self.subTest(case="positive-control"):
            _run_multi(self, "fission energy",
                       ["Nuclear fission releases energy."], True,
                       "Nuclear fission releases energy.", max_results=5)


class ReviewF09KeywordConflictTests(OfflineTestCase):
    def test_f09_keyword_contradiction(self):
        with self.subTest(case="two-source"):
            _run_multi(self, "ziron stability",
                       ["Ziron has stability.", "Ziron has no stability."],
                       False, None, max_results=5)
        with self.subTest(case="before-cap-max1"):
            _run_multi(self, "ziron stability",
                       ["Ziron has stability.", "Ziron has no stability."],
                       False, None, max_results=1)
        with self.subTest(case="same-page"):
            _run_multi(self, "ziron stability",
                       ["Ziron has stability. Ziron has no stability."],
                       False, None, max_results=5)
        with self.subTest(case="unrelated-kept"):
            _run_multi(self, "ziron stability",
                       ["Ziron has stability.", "Iron has no energy."],
                       True, "Ziron has stability.", max_results=5)


if __name__ == "__main__":
    unittest.main()
