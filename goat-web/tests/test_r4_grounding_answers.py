"""R4 capital grounding regression (cycle02, single vertical tracer)."""
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
DIRECT_SENTENCE = "Paris is the capital and most populous city of France."
FRANCE_SENTENCE = "France is a country in western Europe."
SECOND_PARIS = "It is a major centre of finance and culture."


def _wrong_search_body():
    return json.dumps({
        "query": {"search": [
            {"title": "Capital punishment in the United States",
             "snippet": "In the United States, capital punishment is legal in 27 states and the federal government have no executions recorded here."},
            {"title": "Closed-ended question",
             "snippet": "On what day were you born? What is the capital of France? Paris is mentioned as an example question fragment here."},
            {"title": "What Is a Nation?",
             "snippet": "What Is a Nation? is an essay about what defines a nation and the spirit of peoples."},
            {"title": "Capital punishment",
             "snippet": "Capital punishment is a legal penalty involving the death penalty and the law of states."},
            {"title": "Das Kapital",
             "snippet": "Das Kapital is a work about capital and the critique of political economy."},
        ]}
    }).encode("utf-8")


def _stripped_search_body():
    return json.dumps({
        "query": {"search": [
            {"title": "France", "pageid": 111,
             "snippet": "France clipped ..."},
            {"title": "Paris", "pageid": 222,
             "snippet": "Paris clipped ..."},
        ]}
    }).encode("utf-8")


def _extracts_body():
    return json.dumps({
        "query": {"pages": [
            {"pageid": 111, "ns": 0, "title": "France",
             "extract": FRANCE_SENTENCE + " It has many regions."},
            {"pageid": 222, "ns": 0, "title": "Paris",
             "extract": DIRECT_SENTENCE + " " + SECOND_PARIS},
        ]}
    }).encode("utf-8")


class CapitalGroundingTests(OfflineTestCase):
    def test_capital_france_uses_batched_intro_extract(self):
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
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme + "://" + parsed.netloc + parsed.path,
                             FIXED_ENDPOINT)
            params = parse_qs(parsed.query)
            if params.get("prop") == ["extracts"]:
                titles = params.get("titles", [""])[0].split("|") if "titles" in params else []
                pageids = params.get("pageids", [""])[0].split("|") if "pageids" in params else []
                count = len([t for t in titles if t] + [p for p in pageids if p])
                self.assertLessEqual(count, 5)
                self.assertGreater(count, 0)
                return {"status": 200, "headers": {}, "body": _extracts_body(), "url": url}
            srsearch = params.get("srsearch", [""])[0]
            low = srsearch.casefold()
            words = set(low.split())
            if "what" in words:
                return {"status": 200, "headers": {}, "body": _wrong_search_body(), "url": url}
            self.assertIn("capital", low)
            self.assertIn("france", low)
            for fw in ("what", "is", "the", "of"):
                self.assertNotIn(fw, words)
            return {"status": 200, "headers": {}, "body": _stripped_search_body(), "url": url}

        # Old interface fallback: semantic failure, not AttributeError.
        deps = wiring.default_dependencies(_fetch=fake_fetch)
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_answer"]["handler"]
        payload = json.loads(handler({"query": "What is the capital of France?"}))
        self.assertTrue(payload.get("ok"), payload)
        answer = payload.get("answer", "")
        self.assertIn("Paris", answer)
        self.assertIn(DIRECT_SENTENCE, answer)
        self.assertLessEqual(len(answer), 8000)
        sources = payload.get("sources", [])
        self.assertLessEqual(len(sources), 5)
        self.assertTrue(sources)
        urls = [s.get("url", "") for s in sources]
        self.assertIn("https://en.wikipedia.org/wiki/Paris", urls)
        for u in urls:
            self.assertTrue(u.startswith("https://en.wikipedia.org/wiki/"))
        raw = json.dumps(payload)
        self.assertNotIn(FRANCE_SENTENCE, answer)
        self.assertNotIn("finance", answer)
        self.assertNotIn("culture", answer)
        self.assertNotIn("capital punishment", answer.lower())
        self.assertNotIn("Closed-ended", raw)
        self.assertNotIn("What Is a Nation?", raw)
        self.assertNotIn("Das Kapital", raw)
        self.assertNotIn("27 states", raw)
        # Only fixed endpoint, bounded two requests.
        self.assertLessEqual(len(calls), 2)
        self.assertGreaterEqual(len(calls), 1)
        for url, _kw in calls:
            self.assertTrue(url.startswith(FIXED_ENDPOINT + "?"), url)


DIRECT_DISCOVERY_SENTENCE = "In 1928, Alexander Fleming discovered penicillin."
FLEMING_URL = "https://en.wikipedia.org/wiki/Alexander_Fleming"


def _discovery_original_search_body():
    return json.dumps({
        "query": {"search": [
            {"title": "Penicillin", "pageid": 101,
             "snippet": "penicillins have been discovered, but only two purified compounds are in clinical use: penicillin G and penicillin"},
            {"title": "Discovery of penicillin", "pageid": 102,
             "snippet": "The discovery of penicillin was one of the most important scientific discoveries in the history of medicine. Ancient societies used moulds to treat infections"},
            {"title": "Alexander Fleming", "pageid": 103,
             "snippet": "the discovery of penicillin and its curative effect in various infectious diseases. This was the first antibiotic substance discovered. His discovery in"},
        ]}
    }).encode("utf-8")


def _discovery_keyword_search_body():
    return json.dumps({
        "query": {"search": [
            {"title": "Penicillin", "pageid": 101,
             "snippet": "Penicillin keyword clipped ..."},
            {"title": "Discovery of penicillin", "pageid": 102,
             "snippet": "Discovery keyword clipped ..."},
            {"title": "Alexander Fleming", "pageid": 103,
             "snippet": "Fleming keyword clipped ..."},
        ]}
    }).encode("utf-8")


def _discovery_extracts_body():
    return json.dumps({
        "query": {"pages": [
            {"pageid": 101, "ns": 0, "title": "Penicillin",
             "extract": "Penicillin is a group of antibiotics originally obtained from Penicillium moulds."},
            {"pageid": 102, "ns": 0, "title": "Discovery of penicillin",
             "extract": "Discovery is the act of finding something new. History is the study of past events."},
            {"pageid": 103, "ns": 0, "title": "Alexander Fleming",
             "extract": "Alexander Fleming was a Scottish physician and microbiologist. In 1928, Alexander Fleming discovered penicillin. His laboratory was in London."},
        ]}
    }).encode("utf-8")


class DiscoveryGroundingTests(OfflineTestCase):
    def test_who_discovered_penicillin_uses_direct_sentence_only(self):
        import re as _re
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
            parsed = urlsplit(url)
            self.assertEqual(parsed.scheme + "://" + parsed.netloc + parsed.path,
                             FIXED_ENDPOINT)
            params = parse_qs(parsed.query)
            if params.get("prop") == ["extracts"]:
                titles = params.get("titles", [""])[0].split("|") if "titles" in params else []
                pageids = params.get("pageids", [""])[0].split("|") if "pageids" in params else []
                count = len([t for t in titles if t] + [p for p in pageids if p])
                self.assertLessEqual(count, 5)
                self.assertGreater(count, 0)
                return {"status": 200, "headers": {}, "body": _discovery_extracts_body(), "url": url}
            srsearch = params.get("srsearch", [""])[0]
            low = srsearch.casefold()
            words = set(low.split())
            if "who" in words:
                return {"status": 200, "headers": {}, "body": _discovery_original_search_body(), "url": url}
            self.assertIn("discovered", low)
            self.assertIn("penicillin", low)
            self.assertNotIn("who", words)
            return {"status": 200, "headers": {}, "body": _discovery_keyword_search_body(), "url": url}

        deps = wiring.default_dependencies(_fetch=fake_fetch)
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        handler = ctx.tools["goat_answer"]["handler"]
        payload = json.loads(handler({"query": "Who discovered penicillin?"}))
        self.assertTrue(payload.get("ok"), payload)
        answer = payload.get("answer", "")
        self.assertIn(DIRECT_DISCOVERY_SENTENCE, answer)
        self.assertIn("Alexander Fleming", answer)
        self.assertLessEqual(len(answer), 8000)
        # Only the direct discovery sentence plus citation(s).
        stripped = _re.sub(r"\[\d+\]", "", answer).strip()
        self.assertEqual(stripped, DIRECT_DISCOVERY_SENTENCE)
        for fragment in (
            "only two purified compounds",
            "most important scientific discoveries",
            "Ancient societies used moulds",
            "curative effect in various infectious diseases",
            "first antibiotic substance discovered",
            "His discovery in",
            "group of antibiotics",
            "Penicillium",
            "moulds",
            "Scottish",
            "physician",
            "microbiologist",
            "laboratory",
            "London",
            "act of finding something new",
            "study of past events",
        ):
            self.assertNotIn(fragment.lower(), answer.lower())
        raw = json.dumps(payload)
        self.assertNotIn("only two purified compounds", raw)
        sources = payload.get("sources", [])
        self.assertEqual([s.get("url", "") for s in sources], [FLEMING_URL])
        for u in [s.get("url", "") for s in sources]:
            self.assertTrue(u.startswith("https://en.wikipedia.org/wiki/"))
        cited = {int(n) for n in _re.findall(r"\[(\d+)\]", answer)}
        self.assertEqual(cited, {1})
        for line in answer.split("\n"):
            self.assertRegex(line, r"\[\d+\]")
        self.assertLessEqual(len(calls), 2)
        self.assertGreaterEqual(len(calls), 1)
        for url, _kw in calls:
            self.assertTrue(url.startswith(FIXED_ENDPOINT + "?"), url)


if __name__ == "__main__":
    unittest.main()
