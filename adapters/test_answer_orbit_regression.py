import re
import unittest

import answer_synth
from answer_synth import goat_answer


def _res(query, extract):
    def fake_search(_q):
        return {"ok": True, "results": [
            {"title": "Evidence", "url": "https://example.com/e1",
             "extract": extract}
        ]}
    return answer_synth.goat_answer.__wrapped__(query, search=fake_search)


class OrbitRegressionTests(unittest.TestCase):
    def test_who_discovered_penicillin_positive(self):
        raw = _res("Who discovered penicillin?",
                   "Alexander Fleming discovered penicillin.")
        self.assertIn("answer", raw, raw)
        self.assertIn("Fleming", raw.get("answer", ""))
        self.assertRegex(raw.get("answer", ""), r"\[\d+\]")
        self.assertTrue(raw.get("sources"), raw)
        decorated = goat_answer(
            "Who discovered penicillin?",
            search=lambda _q: {"ok": True, "results": [
                {"title": "Evidence", "url": "https://example.com/e1",
                 "extract": "Alexander Fleming discovered penicillin."}
            ]},
        )
        self.assertIn("Fleming", decorated.get("answer", ""))

    def test_what_does_moon_orbit_positive(self):
        raw = _res("What does the Moon orbit?",
                   "The Moon orbits the Earth.")
        self.assertIn("answer", raw, raw)
        self.assertIn("Earth", raw.get("answer", ""))
        self.assertRegex(raw.get("answer", ""), r"\[\d+\]")
        self.assertTrue(raw.get("sources"), raw)
        # Complete sentence + citation grounding preserved.
        for line in raw.get("answer", "").splitlines():
            if line.strip():
                self.assertRegex(line, r"\[\d+\]")
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", raw.get("answer", ""))}
        self.assertTrue(cited)
        self.assertTrue(cited <= {s["index"] for s in raw.get("sources", [])})

    def test_unrelated_evidence_still_insufficient(self):
        cases = [
            ("What does the Moon orbit?",
             "Alexander Fleming discovered penicillin."),
            ("Who discovered penicillin?",
             "The Moon orbits the Earth."),
            ("What does the Moon orbit?",
             "The Moon orbits the Earth"),
            ("What does the Moon orbit?",
             "The Moon does not orbit the Earth."),
        ]
        for query, extract in cases:
            with self.subTest(query=query, extract=extract):
                raw = _res(query, extract)
                self.assertEqual(
                    raw.get("error", {}).get("code"),
                    "INSUFFICIENT_EVIDENCE", raw)
                self.assertNotIn("answer", raw)
                self.assertNotIn("sources", raw)


if __name__ == "__main__":
    unittest.main()
