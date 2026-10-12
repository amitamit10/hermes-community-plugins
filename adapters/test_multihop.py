import re
import socket
import unittest

import answer_synth
import result_contract
from answer_synth import MAX_ANSWER_CHARS, MAX_RESULTS, MISSING_CONFIG, goat_answer

QUESTION = "Where was the author of Hamlet born?"

HOP1_RESULTS = [
    {
        "title": "Hamlet",
        "url": "https://example.com/hamlet",
        "extract": "William Shakespeare wrote Hamlet.",
    }
]

HOP2_RESULTS = [
    {
        "title": "Shakespeare",
        "url": "https://example.com/shakespeare",
        "extract": "William Shakespeare was born in Stratford-upon-Avon.",
    }
]


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        self._getaddrinfo = socket.getaddrinfo
        self._create_connection = socket.create_connection

        def _blocked(*args, **kwargs):
            raise AssertionError("network disabled during offline test")

        socket.getaddrinfo = _blocked
        socket.create_connection = _blocked
        self.addCleanup(setattr, socket, "getaddrinfo", self._getaddrinfo)
        self.addCleanup(setattr, socket, "create_connection", self._create_connection)


class MultiHopTests(OfflineTestCase):
    def test_bridge_hop_names_bridge_and_cites_final(self):
        plan = answer_synth.decompose_query(QUESTION)
        self.assertEqual(plan, ["Who wrote Hamlet?", "{bridge} born"])

        def fake_hop1(_q):
            return {"ok": True, "results": list(HOP1_RESULTS)}

        hop1_raw = answer_synth.goat_answer.__wrapped__(
            plan[0], search=fake_hop1
        )
        hop1_answer = hop1_raw.get("answer", "")
        self.assertIn("William Shakespeare wrote Hamlet.", hop1_answer)

        bridge = answer_synth.extract_bridge_entity(hop1_answer)
        self.assertEqual(bridge, "William Shakespeare")

        hop2q = plan[1].format(bridge=bridge)

        def fake_hop2(_q):
            return {"ok": True, "results": list(HOP2_RESULTS)}

        hop2_raw = answer_synth.goat_answer.__wrapped__(
            hop2q, search=fake_hop2
        )
        self.assertIn(
            "William Shakespeare was born in Stratford-upon-Avon.",
            hop2_raw.get("answer", ""),
        )
        self.assertIn(
            "https://example.com/shakespeare",
            str(hop2_raw.get("sources", [])),
        )
        cited = {
            int(n) for n in re.findall(r"\[(\d+)\]", hop2_raw.get("answer", ""))
        }
        self.assertTrue(cited)
        self.assertTrue(cited <= {s["index"] for s in hop2_raw.get("sources", [])})

    def test_unresolvable_second_hop_abstains(self):
        def fake_empty(_q):
            return {"ok": True, "results": []}

        result = answer_synth.goat_answer.__wrapped__(
            "William Shakespeare born", search=fake_empty
        )
        self.assertEqual(result, {"error": {"code": "INSUFFICIENT_EVIDENCE"}})
        self.assertNotIn("answer", result)

    def test_conflicting_hop_evidence_suppresses(self):
        def fake_conflict(_q):
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Shakespeare",
                        "url": "https://example.com/shakespeare",
                        "extract": (
                            "William Shakespeare was born in "
                            "Stratford-upon-Avon."
                        ),
                    },
                    {
                        "title": "Shakespeare negative",
                        "url": "https://example.com/shakespeare-negative",
                        "extract": (
                            "William Shakespeare was not born in "
                            "Stratford-upon-Avon."
                        ),
                    },
                ],
            }

        result = answer_synth.goat_answer.__wrapped__(
            "William Shakespeare born", search=fake_conflict
        )
        self.assertEqual(result, {"error": {"code": "INSUFFICIENT_EVIDENCE"}})
        self.assertNotIn("answer", result)

    def test_single_hop_query_does_not_decompose(self):
        plan = answer_synth.decompose_query("What is the capital of Canada?")
        self.assertEqual(plan, ["What is the capital of Canada?"])


if __name__ == "__main__":
    unittest.main()
