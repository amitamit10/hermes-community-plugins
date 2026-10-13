"""V52 evidence-graph vertical RED tracer (TEST-ONLY, offline)."""
import unittest

import answer_synth


QUERY = "Who designed the device created by Mira?"
CREATION_URL = "https://evidence.example/creation"
DESIGN_URL = "https://evidence.example/design"
DISTRACTOR_URL = "https://evidence.example/distractor"
SENTENCE_A1 = "Mira created the device Beacon."
SENTENCE_A2 = "Tavi designed Beacon."


class EvidenceGraphTests(unittest.TestCase):
    def test_direction_preserving_two_atom_chain(self):
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(
            callable(plan_fn),
            "missing answer_synth.plan_evidence_query direction-preserving planner",
        )
        validate_fn = getattr(answer_synth, "validate_evidence_query_plan", None)
        self.assertTrue(
            callable(validate_fn),
            "missing answer_synth.validate_evidence_query_plan strict validator",
        )
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(
            callable(ground_fn),
            "missing answer_synth.ground_evidence_atom extract-only grounder",
        )
        compose_fn = getattr(answer_synth, "compose_evidence_query_plan", None)
        self.assertTrue(
            callable(compose_fn),
            "missing answer_synth.compose_evidence_query_plan composer",
        )

        plan = plan_fn(QUERY, max_hops=2, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        atoms = plan.get("atoms")
        self.assertIsInstance(atoms, list, plan)
        self.assertEqual(len(atoms), 2, plan)
        self.assertEqual([a.get("id") for a in atoms], ["a1", "a2"], plan)
        self.assertEqual(plan.get("output"), "v2", plan)

        # a1 directed triple: literal Mira --created--> variable v1 (binds Beacon).
        a1 = atoms[0]
        self.assertEqual(a1.get("id"), "a1", plan)
        subj1 = a1.get("subject")
        self.assertIsInstance(subj1, dict, plan)
        self.assertEqual(subj1.get("kind"), "literal", plan)
        self.assertEqual(subj1.get("text"), "Mira", plan)
        obj1 = a1.get("object")
        self.assertIsInstance(obj1, dict, plan)
        self.assertEqual(obj1.get("kind"), "variable", plan)
        self.assertEqual(obj1.get("id"), "v1", plan)
        self.assertEqual(a1.get("output"), "v1", plan)
        self.assertEqual(a1.get("depends_on"), [], plan)
        # a2 directed triple: variable v2 --designed--> variable v1 (binds Tavi).
        a2 = atoms[1]
        self.assertEqual(a2.get("id"), "a2", plan)
        subj2 = a2.get("subject")
        self.assertIsInstance(subj2, dict, plan)
        self.assertEqual(subj2.get("kind"), "variable", plan)
        self.assertEqual(subj2.get("id"), "v2", plan)
        obj2 = a2.get("object")
        self.assertIsInstance(obj2, dict, plan)
        self.assertEqual(obj2.get("kind"), "variable", plan)
        self.assertEqual(obj2.get("id"), "v1", plan)
        self.assertEqual(a2.get("output"), "v2", plan)
        self.assertEqual(a2.get("depends_on"), ["a1"], plan)

        # Typed terms use kind literal/variable only.
        for term in (subj1, obj1, subj2, obj2):
            self.assertIn(term.get("kind"), ("literal", "variable"), plan)

        # Relation keeps original verb plus span; retrieval_query is retrieval only.
        rel1 = a1.get("relation")
        self.assertIsInstance(rel1, dict, plan)
        self.assertEqual(rel1.get("surface"), "created", plan)
        span1 = rel1.get("span")
        self.assertIsInstance(span1, (list, tuple), plan)
        self.assertEqual(len(span1), 2, plan)
        self.assertTrue(all(isinstance(x, int) for x in span1), plan)
        self.assertEqual(QUERY[span1[0]:span1[1]].casefold(), "created", plan)
        rq1 = a1.get("retrieval_query")
        self.assertIsInstance(rq1, str, plan)
        self.assertTrue(rq1.strip(), plan)
        self.assertIn("created", rq1.casefold(), plan)

        rel2 = a2.get("relation")
        self.assertIsInstance(rel2, dict, plan)
        self.assertEqual(rel2.get("surface"), "designed", plan)
        span2 = rel2.get("span")
        self.assertIsInstance(span2, (list, tuple), plan)
        self.assertEqual(len(span2), 2, plan)
        self.assertTrue(all(isinstance(x, int) for x in span2), plan)
        self.assertEqual(QUERY[span2[0]:span2[1]].casefold(), "designed", plan)
        rq2 = a2.get("retrieval_query")
        self.assertIsInstance(rq2, str, plan)
        self.assertTrue(rq2.strip(), plan)
        self.assertIn("designed", rq2.casefold(), plan)

        # Inner noun preserved as constraint, not dropped or rewritten.
        cons1 = a1.get("constraints")
        self.assertIsInstance(cons1, dict, plan)
        self.assertEqual(cons1.get("object_type"), "device", plan)

        # Validator is strict bool and tied to the exact original query.
        self.assertIs(validate_fn(plan, QUERY), True, plan)
        self.assertIs(
            validate_fn(plan, "Who designed the device created by Nera?"),
            False,
            plan,
        )

        first_batch = [
            {"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1},
            {
                "title": "Distractor",
                "url": DISTRACTOR_URL,
                "extract": "Nera created Mira.",
            },
        ]
        second_batch = [
            {"title": "Design", "url": DESIGN_URL, "extract": SENTENCE_A2},
            {
                "title": "Distractor",
                "url": DISTRACTOR_URL,
                "extract": "Kora designed Nera.",
            },
        ]

        # Ground a1 from empty bindings; only body-extract sentence may bind.
        first = ground_fn(a1, {}, first_batch, query=QUERY)
        self.assertIsInstance(first, dict, first)
        self.assertEqual(first.get("status"), "grounded", first)
        self.assertEqual(first.get("binding"), "Beacon", first)
        proof1 = first.get("proof")
        self.assertIsInstance(proof1, dict, first)
        self.assertIn(SENTENCE_A1, str(proof1), first)

        # Chain with opaque native proof object, not a scalar/serialized answer.
        second = ground_fn(a2, {"a1": proof1}, second_batch, query=QUERY)
        self.assertIsInstance(second, dict, second)
        self.assertEqual(second.get("status"), "grounded", second)
        self.assertEqual(second.get("binding"), "Tavi", second)
        proof2 = second.get("proof")
        self.assertIsInstance(proof2, dict, second)
        self.assertIn(SENTENCE_A2, str(proof2), second)

        composed = compose_fn(
            plan, {"a1": proof1, "a2": proof2}, QUERY,
            max_sources=5, max_answer_chars=8000,
        )
        self.assertIsInstance(composed, dict, composed)
        self.assertEqual(composed.get("binding"), "Tavi", composed)
        answer = composed.get("answer")
        self.assertIsInstance(answer, str, composed)
        # Both verbatim proof sentences with separate citations.
        self.assertIn(SENTENCE_A1, answer, composed)
        self.assertIn(SENTENCE_A2, answer, composed)
        self.assertIn("[1]", answer, composed)
        self.assertIn("[2]", answer, composed)
        sources = composed.get("sources")
        self.assertIsInstance(sources, list, composed)
        self.assertEqual(len(sources), 2, composed)
        urls = [s.get("url") for s in sources if isinstance(s, dict)]
        self.assertEqual(set(urls), {CREATION_URL, DESIGN_URL}, composed)
        # Distractors never leak into the composed answer.
        self.assertNotIn("Nera", answer, composed)
        self.assertNotIn("Kora", answer, composed)
        self.assertNotIn("distractor", answer.casefold(), composed)

    def test_ambiguous_body_bindings_preserve_unresolved_provenance(self):
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        plan = plan_fn(QUERY, max_hops=2, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        atoms = plan.get("atoms")
        self.assertIsInstance(atoms, list, plan)
        self.assertEqual(len(atoms), 2, plan)
        a1 = atoms[0]
        a2 = atoms[1]
        alt_url = "https://evidence.example/alternate"
        sent_beacon = "Mira created the device Beacon."
        sent_lattice = "Mira created the device Lattice."
        cands = [
            {"title": "Creation", "url": CREATION_URL, "extract": sent_beacon},
            {"title": "Alternate", "url": alt_url, "extract": sent_lattice},
        ]
        res = ground_fn(a1, {}, cands, query=QUERY)
        self.assertIsInstance(res, dict, res)
        self.assertEqual(res.get("status"), "ungrounded", res)
        self.assertNotIn("binding", res, res)
        self.assertNotIn("proof", res, res)
        self.assertEqual(res.get("reason"), "ambiguous_binding", res)
        srcs = res.get("intermediate_sources")
        self.assertIsInstance(srcs, list, res)
        self.assertEqual(len(srcs), 2, res)
        self.assertLessEqual(len(srcs), 5, res)
        urls = set()
        for s in srcs:
            self.assertIsInstance(s, dict, res)
            self.assertEqual(set(s.keys()), {"url", "title"}, res)
            u = s.get("url")
            t = s.get("title")
            self.assertIsInstance(u, str, res)
            self.assertIsInstance(t, str, res)
            self.assertTrue(t.strip(), res)
            self.assertTrue(u.startswith("https://"), res)
            self.assertNotIn(" ", u, res)
            self.assertLessEqual(len(u), 2048, res)
            urls.add(u)
        self.assertEqual(urls, {CREATION_URL, alt_url}, res)
        # Reversing candidate order must still abstain with same URL set.
        rev = ground_fn(a1, {}, list(reversed(cands)), query=QUERY)
        self.assertIsInstance(rev, dict, rev)
        self.assertEqual(rev.get("status"), "ungrounded", rev)
        self.assertNotIn("binding", rev, rev)
        self.assertNotIn("proof", rev, rev)
        self.assertEqual(rev.get("reason"), "ambiguous_binding", rev)
        rsrcs = rev.get("intermediate_sources")
        self.assertIsInstance(rsrcs, list, rev)
        self.assertEqual(len(rsrcs), 2, rev)
        rurls = {s.get("url") for s in rsrcs if isinstance(s, dict)}
        self.assertEqual(rurls, {CREATION_URL, alt_url}, rev)
        self.assertEqual(rurls, urls, rev)
        # Downstream cannot ground from unresolved ambiguity state.
        down_cands = [
            {"title": "Design", "url": DESIGN_URL, "extract": SENTENCE_A2},
        ]
        second = ground_fn(a2, {"a1": res}, down_cands, query=QUERY)
        self.assertIsInstance(second, dict, second)
        self.assertEqual(second.get("status"), "ungrounded", second)
        self.assertNotIn("binding", second, second)
        self.assertNotIn("proof", second, second)
        # Plain scalar / plain dict ambiguity state must never fill variable.
        for fake in (
            "Beacon",
            {"binding": "Beacon", "sentence": sent_beacon},
            {"status": "ungrounded", "reason": "ambiguous_binding"},
            dict(res),
        ):
            nxt = ground_fn(a2, {"a1": fake}, down_cands, query=QUERY)
            self.assertIsInstance(nxt, dict, nxt)
            self.assertEqual(nxt.get("status"), "ungrounded", nxt)
            self.assertNotIn("binding", nxt, nxt)
            self.assertNotIn("proof", nxt, nxt)

    def test_original_question_binding_rejects_forged_atom_direction(self):
        import copy
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        validate_fn = getattr(answer_synth, "validate_evidence_query_plan", None)
        self.assertTrue(callable(validate_fn), "missing validator")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        plan = plan_fn(QUERY, max_hops=2, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        self.assertIs(validate_fn(plan, QUERY), True, plan)
        canon_a1 = plan.get("atoms", [{}])[0]
        orig_span = list(canon_a1.get("subject", {}).get("span", []))
        self.assertEqual(len(orig_span), 2, plan)
        forged = copy.deepcopy(plan)
        forged_a1 = forged.get("atoms", [{}])[0]
        forged_a1["subject"] = {"kind": "variable", "id": "v1"}
        forged_a1["object"] = {"kind": "literal", "text": "Mira", "span": list(orig_span)}
        forged_a1["constraints"] = {}
        self.assertEqual(forged_a1.get("output"), "v1", forged)
        self.assertIs(validate_fn(forged, QUERY), False, forged)
        forged_cands = [
            {"title": "Distractor", "url": DISTRACTOR_URL, "extract": "Nera created Mira."},
        ]
        forged_res = ground_fn(forged_a1, {}, forged_cands, query=QUERY)
        self.assertIsInstance(forged_res, dict, forged_res)
        self.assertEqual(forged_res.get("status"), "ungrounded", forged_res)
        self.assertNotIn("binding", forged_res, forged_res)
        self.assertNotIn("proof", forged_res, forged_res)
        with self.subTest(kind="bool-depth"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["depth"] = True
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            res = ground_fn(
                mutated["atoms"][0], {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertIsInstance(res, dict, res)
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="bool-relation-span"):
            mutated = copy.deepcopy(plan)
            span = mutated["atoms"][0]["relation"]["span"]
            if span[0] == 1 or span[1] == 1:
                mutated["atoms"][0]["relation"]["span"] = [
                    True if x == 1 else x for x in span
                ]
            else:
                mutated["atoms"][0]["relation"]["span"] = [True, span[1]]
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            res = ground_fn(
                mutated["atoms"][0], {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertIsInstance(res, dict, res)
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="missing-field"):
            mutated = copy.deepcopy(plan)
            del mutated["atoms"][0]["retrieval_query"]
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            broken = copy.deepcopy(plan["atoms"][0])
            del broken["retrieval_query"]
            res = ground_fn(
                broken, {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="foreign-grounding-template"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["grounding_template"] = "Who created Mira?"
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            broken = copy.deepcopy(plan["atoms"][0])
            broken["grounding_template"] = "Who created Mira?"
            res = ground_fn(
                broken, {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="object-type-erased"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["constraints"] = {}
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            res = ground_fn(
                mutated["atoms"][0], {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="span-drift"):
            mutated = copy.deepcopy(plan)
            drifted = [orig_span[0] + 1, orig_span[1] + 1]
            mutated["atoms"][0]["subject"]["span"] = drifted
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            res = ground_fn(
                mutated["atoms"][0], {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="self-loop"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["depends_on"] = ["a1"]
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            res = ground_fn(
                mutated["atoms"][0], {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="future-dependency"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["depends_on"] = ["a2"]
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            res = ground_fn(
                mutated["atoms"][0], {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="changed-literal"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["subject"]["text"] = "Nera"
            self.assertIs(validate_fn(mutated, QUERY), False, mutated)
            res = ground_fn(
                mutated["atoms"][0], {},
                [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
                query=QUERY,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="mismatched-query"):
            self.assertIs(
                validate_fn(plan, "Who designed the device created by Nera?"),
                False,
                plan,
            )
        with self.subTest(kind="budget-max-hops-bool"):
            self.assertIs(validate_fn(plan, QUERY, max_hops=True), False, plan)
        with self.subTest(kind="budget-max-searches-bool"):
            self.assertIs(validate_fn(plan, QUERY, max_searches=True), False, plan)

    def test_same_binding_contradiction_blocks_chain(self):
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        plan = plan_fn(QUERY, max_hops=2, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        atoms = plan.get("atoms")
        self.assertIsInstance(atoms, list, plan)
        self.assertEqual(len(atoms), 2, plan)
        a1 = atoms[0]
        a2 = atoms[1]
        DENIAL_URL = "https://evidence.example/denial"
        POS = "Mira created the device Beacon."
        NEG = "Mira did not create the device Beacon."
        cands = [
            {"title": "Creation", "url": CREATION_URL, "extract": POS},
            {"title": "Denial", "url": DENIAL_URL, "extract": NEG},
        ]
        res = ground_fn(a1, {}, cands, query=QUERY)
        self.assertIsInstance(res, dict, res)
        self.assertEqual(res.get("status"), "ungrounded", res)
        self.assertNotIn("binding", res, res)
        self.assertNotIn("proof", res, res)
        rev = ground_fn(a1, {}, list(reversed(cands)), query=QUERY)
        self.assertIsInstance(rev, dict, rev)
        self.assertEqual(rev.get("status"), "ungrounded", rev)
        self.assertNotIn("binding", rev, rev)
        self.assertNotIn("proof", rev, rev)
        # Contradicted a1 must block downstream chaining.
        down_cands = [
            {"title": "Design", "url": DESIGN_URL, "extract": SENTENCE_A2},
        ]
        second = ground_fn(a2, {"a1": res}, down_cands, query=QUERY)
        self.assertIsInstance(second, dict, second)
        self.assertEqual(second.get("status"), "ungrounded", second)
        self.assertNotIn("binding", second, second)
        self.assertNotIn("proof", second, second)
        variants = [
            "Mira never created the device Beacon.",
            "Mira did not create the device Beacon.",
            "Mira didn't create the device Beacon.",
            "The device Beacon was not created by Mira.",
            "The device Beacon wasn't created by Mira.",
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                paired = [
                    {"title": "Creation", "url": CREATION_URL, "extract": POS},
                    {"title": "Denial", "url": DENIAL_URL, "extract": variant},
                ]
                got = ground_fn(a1, {}, paired, query=QUERY)
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), "ungrounded", got)
                self.assertNotIn("binding", got, got)
                self.assertNotIn("proof", got, got)
                flipped = ground_fn(a1, {}, list(reversed(paired)), query=QUERY)
                self.assertIsInstance(flipped, dict, flipped)
                self.assertEqual(flipped.get("status"), "ungrounded", flipped)
                self.assertNotIn("binding", flipped, flipped)
                self.assertNotIn("proof", flipped, flipped)
        with self.subTest(kind="unrelated-actor-negative"):
            unrelated = [
                {"title": "Creation", "url": CREATION_URL, "extract": POS},
                {
                    "title": "Denial",
                    "url": DENIAL_URL,
                    "extract": "Nera did not create the device Beacon.",
                },
            ]
            got = ground_fn(a1, {}, unrelated, query=QUERY)
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "grounded", got)
            self.assertEqual(got.get("binding"), "Beacon", got)
            self.assertIn(POS, str(got.get("proof")), got)
        with self.subTest(kind="type-mismatch-negative"):
            mismatched = [
                {"title": "Creation", "url": CREATION_URL, "extract": POS},
                {
                    "title": "Denial",
                    "url": DENIAL_URL,
                    "extract": "Mira did not create the engine Beacon.",
                },
            ]
            got = ground_fn(a1, {}, mismatched, query=QUERY)
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "grounded", got)
            self.assertEqual(got.get("binding"), "Beacon", got)
            self.assertIn(POS, str(got.get("proof")), got)
        with self.subTest(kind="snippet-only"):
            got = ground_fn(
                a1, {},
                [{"title": "Creation", "url": CREATION_URL, "snippet": POS}],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="title-only"):
            got = ground_fn(
                a1, {},
                [{"title": POS, "url": CREATION_URL, "extract": ""}],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="wrong-type"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Creation",
                        "url": CREATION_URL,
                        "extract": "Mira created the engine Beacon.",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="mixed-relation"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Creation",
                        "url": CREATION_URL,
                        "extract": "Mira created the device. Beacon was polished by Tavi.",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="source-question"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Creation",
                        "url": CREATION_URL,
                        "extract": "Did Mira create the device Beacon?",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="hedge"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Creation",
                        "url": CREATION_URL,
                        "extract": "Mira allegedly created the device Beacon.",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="reported"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Creation",
                        "url": CREATION_URL,
                        "extract": "Mira said she created the device Beacon.",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="context"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Creation",
                        "url": CREATION_URL,
                        "extract": "According to critics, Mira created the device Beacon.",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="wrong-direction-active"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Distractor",
                        "url": DISTRACTOR_URL,
                        "extract": "Beacon created the device Mira.",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="wrong-direction-passive"):
            got = ground_fn(
                a1, {},
                [
                    {
                        "title": "Distractor",
                        "url": DISTRACTOR_URL,
                        "extract": "Mira was created by Beacon.",
                    }
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)
        with self.subTest(kind="negative-title-only-grounds"):
            got = ground_fn(
                a1, {},
                [
                    {"title": "Creation", "url": CREATION_URL, "extract": POS},
                    {
                        "title": NEG,
                        "url": DENIAL_URL,
                        "extract": "Beacon was polished by Tavi.",
                    },
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "grounded", got)
            self.assertEqual(got.get("binding"), "Beacon", got)
            self.assertIn(POS, str(got.get("proof")), got)
        with self.subTest(kind="negative-snippet-only-grounds"):
            got = ground_fn(
                a1, {},
                [
                    {"title": "Creation", "url": CREATION_URL, "extract": POS},
                    {
                        "title": "Denial",
                        "url": DENIAL_URL,
                        "extract": "Beacon was polished by Tavi.",
                        "snippet": NEG,
                    },
                ],
                query=QUERY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "grounded", got)
            self.assertEqual(got.get("binding"), "Beacon", got)
            self.assertIn(POS, str(got.get("proof")), got)


    def test_open_relation_nested_clauses_share_typed_grammar(self):
        import copy
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        validate_fn = getattr(answer_synth, "validate_evidence_query_plan", None)
        self.assertTrue(callable(validate_fn), "missing validator")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        compose_fn = getattr(answer_synth, "compose_evidence_query_plan", None)
        self.assertTrue(callable(compose_fn), "missing composer")

        # Regression control (guard): open relation 2-hop already supported.
        Q2 = "Who polished the component assembled by Arin?"
        S2_A1 = "Arin assembled the component Quartz."
        S2_A2 = "Vale polished Quartz."
        U2_A1 = "https://evidence.example/assemble-quartz"
        U2_A2 = "https://evidence.example/polish-quartz"
        plan2 = plan_fn(Q2, max_hops=2, max_searches=4)
        self.assertIsInstance(plan2, dict, plan2)
        self.assertEqual(len(plan2.get("atoms", [])), 2, plan2)
        self.assertEqual(plan2.get("output"), "v2", plan2)
        self.assertIs(validate_fn(plan2, Q2), True, plan2)
        c2a1 = plan2["atoms"][0]
        self.assertEqual(c2a1.get("subject", {}).get("kind"), "literal", plan2)
        self.assertEqual(c2a1.get("subject", {}).get("text"), "Arin", plan2)
        self.assertEqual(c2a1.get("object", {}).get("id"), "v1", plan2)
        self.assertEqual(c2a1.get("relation", {}).get("surface"), "assembled", plan2)
        self.assertEqual(c2a1.get("constraints", {}).get("object_type"), "component", plan2)
        self.assertEqual(c2a1.get("depends_on"), [], plan2)
        self.assertEqual(c2a1.get("output"), "v1", plan2)
        c2a2 = plan2["atoms"][1]
        self.assertEqual(c2a2.get("subject", {}).get("id"), "v2", plan2)
        self.assertEqual(c2a2.get("object", {}).get("id"), "v1", plan2)
        self.assertEqual(c2a2.get("relation", {}).get("surface"), "polished", plan2)
        self.assertEqual(c2a2.get("depends_on"), ["a1"], plan2)
        self.assertEqual(c2a2.get("output"), "v2", plan2)
        g2a = ground_fn(
            c2a1, {},
            [{"title": "Assemble", "url": U2_A1, "extract": S2_A1}],
            query=Q2,
        )
        self.assertEqual(g2a.get("status"), "grounded", g2a)
        self.assertEqual(g2a.get("binding"), "Quartz", g2a)
        self.assertIn(S2_A1, str(g2a.get("proof")), g2a)
        g2b = ground_fn(
            c2a2, {"a1": g2a.get("proof")},
            [{"title": "Polish", "url": U2_A2, "extract": S2_A2}],
            query=Q2,
        )
        self.assertEqual(g2b.get("status"), "grounded", g2b)
        self.assertEqual(g2b.get("binding"), "Vale", g2b)
        self.assertIn(S2_A2, str(g2b.get("proof")), g2b)
        comp2 = compose_fn(
            plan2, {"a1": g2a.get("proof"), "a2": g2b.get("proof")}, Q2,
            max_sources=5, max_answer_chars=8000,
        )
        self.assertEqual(comp2.get("binding"), "Vale", comp2)
        self.assertIn(S2_A1, comp2.get("answer", ""), comp2)
        self.assertIn(S2_A2, comp2.get("answer", ""), comp2)
        self.assertIn("[1]", comp2.get("answer", ""), comp2)
        self.assertIn("[2]", comp2.get("answer", ""), comp2)
        self.assertEqual(len(comp2.get("sources", [])), 2, comp2)

        # New behavior: recursive NP 'the N PAST by NP', 3-hop nested.
        Q3 = "Who polished the component assembled by the unit calibrated by Arin?"
        S3_A1 = "Arin calibrated the unit Quartz."
        S3_A2 = "Quartz assembled the component Lumen."
        S3_A3 = "Vale polished Lumen."
        U3_A1 = "https://evidence.example/calibrate-quartz"
        U3_A2 = "https://evidence.example/assemble-lumen"
        U3_A3 = "https://evidence.example/polish-lumen"
        plan3 = plan_fn(Q3, max_hops=3, max_searches=4)
        self.assertIsInstance(plan3, dict, plan3)
        atoms3 = plan3.get("atoms")
        self.assertIsInstance(atoms3, list, plan3)
        self.assertEqual(len(atoms3), 3, plan3)
        self.assertEqual([a.get("id") for a in atoms3], ["a1", "a2", "a3"], plan3)
        self.assertEqual(plan3.get("output"), "v3", plan3)
        self.assertEqual(plan3.get("query"), Q3, plan3)
        self.assertEqual(plan3.get("max_hops"), 3, plan3)
        self.assertEqual(plan3.get("max_searches"), 4, plan3)
        a1, a2, a3 = atoms3
        # Explicit subject/object roles.
        self.assertEqual(a1.get("subject", {}).get("kind"), "literal", plan3)
        self.assertEqual(a1.get("subject", {}).get("text"), "Arin", plan3)
        self.assertEqual(a1.get("object", {}).get("kind"), "variable", plan3)
        self.assertEqual(a1.get("object", {}).get("id"), "v1", plan3)
        self.assertEqual(a2.get("subject", {}).get("kind"), "variable", plan3)
        self.assertEqual(a2.get("subject", {}).get("id"), "v1", plan3)
        self.assertEqual(a2.get("object", {}).get("kind"), "variable", plan3)
        self.assertEqual(a2.get("object", {}).get("id"), "v2", plan3)
        self.assertEqual(a3.get("subject", {}).get("kind"), "variable", plan3)
        self.assertEqual(a3.get("subject", {}).get("id"), "v3", plan3)
        self.assertEqual(a3.get("object", {}).get("kind"), "variable", plan3)
        self.assertEqual(a3.get("object", {}).get("id"), "v2", plan3)
        for term in (
            a1.get("subject"), a1.get("object"),
            a2.get("subject"), a2.get("object"),
            a3.get("subject"), a3.get("object"),
        ):
            self.assertIn(term.get("kind"), ("literal", "variable"), plan3)
            self.assertNotEqual(term.get("kind"), "entity", plan3)
        self.assertNotIn("entity", str(atoms3).casefold(), plan3)
        self.assertEqual(a1.get("depends_on"), [], plan3)
        self.assertEqual(a2.get("depends_on"), ["a1"], plan3)
        self.assertEqual(a3.get("depends_on"), ["a2"], plan3)
        self.assertEqual(a1.get("output"), "v1", plan3)
        self.assertEqual(a2.get("output"), "v2", plan3)
        self.assertEqual(a3.get("output"), "v3", plan3)
        # Typed nouns, no literal/entity exception.
        self.assertEqual(a1.get("constraints", {}).get("object_type"), "unit", plan3)
        self.assertEqual(a2.get("constraints", {}).get("object_type"), "component", plan3)
        self.assertEqual(a3.get("constraints", {}), {}, plan3)
        # Relation surfaces exact verb-span slices.
        for atom, verb in ((a1, "calibrated"), (a2, "assembled"), (a3, "polished")):
            rel = atom.get("relation")
            self.assertIsInstance(rel, dict, plan3)
            self.assertEqual(rel.get("surface"), verb, plan3)
            span = rel.get("span")
            self.assertIsInstance(span, (list, tuple), plan3)
            self.assertEqual(len(span), 2, plan3)
            self.assertTrue(all(type(x) is int for x in span), plan3)
            self.assertEqual(Q3[span[0]:span[1]].casefold(), verb, plan3)
        # Each atom query_surface is the exact original slice from clause_span.
        for atom in atoms3:
            qs = atom.get("query_surface")
            cs = atom.get("clause_span")
            self.assertIsInstance(qs, str, plan3)
            self.assertTrue(qs.strip(), plan3)
            self.assertIsInstance(cs, (list, tuple), plan3)
            self.assertEqual(len(cs), 2, plan3)
            self.assertTrue(all(type(x) is int for x in cs), plan3)
            self.assertTrue(0 <= cs[0] < cs[1] <= len(Q3), plan3)
            self.assertEqual(qs, Q3[cs[0]:cs[1]], plan3)
            rsp = atom.get("relation", {}).get("span")
            self.assertTrue(cs[0] <= rsp[0] and rsp[1] <= cs[1], plan3)
        self.assertIn("Arin", a1.get("query_surface", ""), plan3)
        self.assertIn("calibrated", a1.get("query_surface", "").casefold(), plan3)
        self.assertIn("unit", a1.get("query_surface", "").casefold(), plan3)
        self.assertIn("assembled", a2.get("query_surface", "").casefold(), plan3)
        self.assertIn("polished", a3.get("query_surface", "").casefold(), plan3)
        # Retrieval queries: dependent atoms reference v1/v2; first keeps type/root.
        rq1 = a1.get("retrieval_query")
        rq2 = a2.get("retrieval_query")
        rq3 = a3.get("retrieval_query")
        for rq, verb in ((rq1, "calibrated"), (rq2, "assembled"), (rq3, "polished")):
            self.assertIsInstance(rq, str, plan3)
            self.assertTrue(rq.strip(), plan3)
            self.assertIn(verb, rq.casefold(), plan3)
        self.assertIn("Arin", rq1, plan3)
        self.assertIn("unit", rq1.casefold(), plan3)
        self.assertNotEqual(rq1, "Who calibrated Arin?", plan3)
        self.assertNotIn("Who calibrated Arin?", rq1, plan3)
        self.assertIn("v1", rq2, plan3)
        self.assertIn("v2", rq3, plan3)
        self.assertIs(validate_fn(plan3, Q3), True, plan3)
        self.assertIs(validate_fn(plan3, Q3, max_hops=3, max_searches=4), True, plan3)
        # Ground through native producer proofs only.
        r1 = ground_fn(
            a1, {},
            [{"title": "Calibrate", "url": U3_A1, "extract": S3_A1}],
            query=Q3,
        )
        self.assertEqual(r1.get("status"), "grounded", r1)
        self.assertEqual(r1.get("binding"), "Quartz", r1)
        self.assertIn(S3_A1, str(r1.get("proof")), r1)
        r2 = ground_fn(
            a2, {"a1": r1.get("proof")},
            [{"title": "Assemble", "url": U3_A2, "extract": S3_A2}],
            query=Q3,
        )
        self.assertEqual(r2.get("status"), "grounded", r2)
        self.assertEqual(r2.get("binding"), "Lumen", r2)
        self.assertIn(S3_A2, str(r2.get("proof")), r2)
        # Canonical explicit joins: ground bindings only immediate declared deps.
        r3 = ground_fn(
            a3, {"a2": r2.get("proof")},
            [{"title": "Polish", "url": U3_A3, "extract": S3_A3}],
            query=Q3,
        )
        self.assertEqual(r3.get("status"), "grounded", r3)
        self.assertEqual(r3.get("binding"), "Vale", r3)
        self.assertIn(S3_A3, str(r3.get("proof")), r3)
        superset = ground_fn(
            a3, {"a1": r1.get("proof"), "a2": r2.get("proof")},
            [{"title": "Polish", "url": U3_A3, "extract": S3_A3}],
            query=Q3,
        )
        self.assertEqual(superset.get("status"), "ungrounded", superset)
        self.assertNotIn("binding", superset, superset)
        self.assertNotIn("proof", superset, superset)
        for fake in ("Vale", {"binding": "Vale", "sentence": S3_A3}):
            bad = ground_fn(
                a3, {"a2": fake},
                [{"title": "Polish", "url": U3_A3, "extract": S3_A3}],
                query=Q3,
            )
            self.assertEqual(bad.get("status"), "ungrounded", bad)
        # Compose includes ALL 3 proofs and sources, binding Vale.
        comp3 = compose_fn(
            plan3,
            {"a1": r1.get("proof"), "a2": r2.get("proof"), "a3": r3.get("proof")},
            Q3, max_sources=5, max_answer_chars=8000,
        )
        self.assertIsInstance(comp3, dict, comp3)
        self.assertEqual(comp3.get("binding"), "Vale", comp3)
        ans3 = comp3.get("answer")
        self.assertIsInstance(ans3, str, comp3)
        self.assertIn(S3_A1, ans3, comp3)
        self.assertIn(S3_A2, ans3, comp3)
        self.assertIn(S3_A3, ans3, comp3)
        self.assertIn("[1]", ans3, comp3)
        self.assertIn("[2]", ans3, comp3)
        self.assertIn("[3]", ans3, comp3)
        srcs3 = comp3.get("sources")
        self.assertIsInstance(srcs3, list, comp3)
        self.assertEqual(len(srcs3), 3, comp3)
        self.assertEqual(
            {s.get("url") for s in srcs3 if isinstance(s, dict)},
            {U3_A1, U3_A2, U3_A3}, comp3,
        )

        # 4-hop generated structurally from the same recursive grammar.
        Q4 = "Who polished the component assembled by the unit calibrated by the module coated by Arin?"
        plan4 = plan_fn(Q4, max_hops=4, max_searches=4)
        self.assertIsInstance(plan4, dict, plan4)
        atoms4 = plan4.get("atoms")
        self.assertIsInstance(atoms4, list, plan4)
        self.assertEqual(len(atoms4), 4, plan4)
        self.assertEqual([a.get("id") for a in atoms4], ["a1", "a2", "a3", "a4"], plan4)
        self.assertEqual(plan4.get("output"), "v4", plan4)
        self.assertIs(validate_fn(plan4, Q4), True, plan4)
        self.assertEqual(
            [a.get("depends_on") for a in atoms4], [[], ["a1"], ["a2"], ["a3"]], plan4
        )
        self.assertEqual(
            [a.get("output") for a in atoms4], ["v1", "v2", "v3", "v4"], plan4
        )
        self.assertEqual(
            [a.get("relation", {}).get("surface") for a in atoms4],
            ["coated", "calibrated", "assembled", "polished"], plan4,
        )
        for atom in atoms4:
            qs = atom.get("query_surface")
            cs = atom.get("clause_span")
            self.assertIsInstance(qs, str, plan4)
            self.assertIsInstance(cs, (list, tuple), plan4)
            self.assertEqual(len(cs), 2, plan4)
            self.assertTrue(all(type(x) is int for x in cs), plan4)
            self.assertEqual(qs, Q4[cs[0]:cs[1]], plan4)
            rel = atom.get("relation", {})
            self.assertEqual(Q4[rel["span"][0]:rel["span"][1]].casefold(), rel["surface"].casefold(), plan4)
        # Same 4-hop query under tighter budgets rejected: no atoms.
        short4 = plan_fn(Q4, max_hops=3, max_searches=4)
        self.assertIsInstance(short4, dict, short4)
        self.assertEqual(short4.get("atoms"), [], short4)
        self.assertEqual(short4.get("output"), "", short4)
        self.assertIs(validate_fn(short4, Q4), False, short4)
        # 5 nested atoms with max 4 rejected: no atoms, no recursion leak.
        Q5 = "Who polished the component assembled by the unit calibrated by the module coated by the part primed by Arin?"
        plan5 = plan_fn(Q5, max_hops=4, max_searches=4)
        self.assertIsInstance(plan5, dict, plan5)
        self.assertEqual(plan5.get("atoms"), [], plan5)
        self.assertEqual(plan5.get("output"), "", plan5)
        self.assertIs(validate_fn(plan5, Q5), False, plan5)
        # Noun deletion and surface/span mutations validate false.
        with self.subTest(kind="noun-deletion"):
            mutated = copy.deepcopy(plan3)
            del mutated["atoms"][0]["constraints"]["object_type"]
            self.assertIs(validate_fn(mutated, Q3), False, mutated)
            res = ground_fn(
                copy.deepcopy(mutated["atoms"][0]), {},
                [{"title": "Calibrate", "url": U3_A1, "extract": S3_A1}],
                query=Q3,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)
        with self.subTest(kind="query-surface-mutation"):
            mutated = copy.deepcopy(plan3)
            mutated["atoms"][1]["query_surface"] = mutated["atoms"][1]["query_surface"] + "!"
            self.assertIs(validate_fn(mutated, Q3), False, mutated)
        with self.subTest(kind="clause-span-mutation"):
            mutated = copy.deepcopy(plan3)
            cs = list(mutated["atoms"][2]["clause_span"])
            mutated["atoms"][2]["clause_span"] = [cs[0] + 1, cs[1] + 1]
            self.assertIs(validate_fn(mutated, Q3), False, mutated)
            res = ground_fn(
                copy.deepcopy(mutated["atoms"][2]), {"a2": r2.get("proof")},
                [{"title": "Polish", "url": U3_A3, "extract": S3_A3}],
                query=Q3,
            )
            self.assertEqual(res.get("status"), "ungrounded", res)


    def test_year_constraint_requires_same_sentence_exact_year(self):
        import copy
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        validate_fn = getattr(answer_synth, "validate_evidence_query_plan", None)
        self.assertTrue(callable(validate_fn), "missing validator")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        compose_fn = getattr(answer_synth, "compose_evidence_query_plan", None)
        self.assertTrue(callable(compose_fn), "missing composer")

        QY = "Who polished Quartz in 2019?"
        YEAR = "2019"
        YSENT = "Vale polished Quartz in 2019."
        YURL = "https://evidence.example/polish-quartz-2019"
        YTITLE = "Polish Quartz 2019"
        plan = plan_fn(QY, max_hops=2, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        atoms = plan.get("atoms")
        self.assertIsInstance(atoms, list, plan)
        # Year constraint inspected first for clean RED (no IndexError).
        self.assertEqual(len(atoms), 1, plan)
        self.assertEqual(plan.get("output"), "v1", plan)
        self.assertEqual(plan.get("query"), QY, plan)
        self.assertEqual(plan.get("max_hops"), 2, plan)
        self.assertEqual(plan.get("max_searches"), 4, plan)
        # status/reason optional but if introduced must be closed-schema valid.
        if "status" in plan:
            self.assertEqual(plan.get("status"), "planned", plan)
        if "reason" in plan:
            self.assertEqual(plan.get("reason"), "planned", plan)

        a1 = atoms[0]
        self.assertEqual(a1.get("id"), "a1", plan)
        self.assertEqual(a1.get("output"), "v1", plan)
        self.assertEqual(a1.get("depends_on"), [], plan)
        subj = a1.get("subject")
        self.assertIsInstance(subj, dict, plan)
        self.assertEqual(subj.get("kind"), "variable", plan)
        self.assertEqual(subj.get("id"), "v1", plan)
        obj = a1.get("object")
        self.assertIsInstance(obj, dict, plan)
        self.assertEqual(obj.get("kind"), "literal", plan)
        self.assertEqual(obj.get("text"), "Quartz", plan)
        ospan = obj.get("span")
        self.assertIsInstance(ospan, (list, tuple), plan)
        self.assertEqual(len(ospan), 2, plan)
        self.assertTrue(all(type(x) is int for x in ospan), plan)
        self.assertEqual(QY[ospan[0]:ospan[1]], "Quartz", plan)
        rel = a1.get("relation")
        self.assertIsInstance(rel, dict, plan)
        self.assertEqual(rel.get("surface"), "polished", plan)
        rspan = rel.get("span")
        self.assertIsInstance(rspan, (list, tuple), plan)
        self.assertEqual(len(rspan), 2, plan)
        self.assertTrue(all(type(x) is int for x in rspan), plan)
        self.assertEqual(QY[rspan[0]:rspan[1]].casefold(), "polished", plan)
        cons = a1.get("constraints")
        self.assertIsInstance(cons, dict, plan)
        self.assertIs(type(cons.get("year")), str, plan)
        self.assertEqual(cons.get("year"), YEAR, plan)
        yspan = cons.get("year_span")
        self.assertIsInstance(yspan, (list, tuple), plan)
        self.assertEqual(len(yspan), 2, plan)
        self.assertTrue(all(type(x) is int for x in yspan), plan)
        self.assertEqual(QY[yspan[0]:yspan[1]], YEAR, plan)
        exp_s = QY.index(YEAR)
        self.assertEqual(list(yspan), [exp_s, exp_s + 4], plan)
        # Clause/retrieval stay exact-original slices; retrieval never invents.
        cs = a1.get("clause_span")
        self.assertIsInstance(cs, (list, tuple), plan)
        self.assertEqual(len(cs), 2, plan)
        self.assertTrue(all(type(x) is int for x in cs), plan)
        self.assertEqual(a1.get("query_surface"), QY[cs[0]:cs[1]], plan)
        self.assertTrue(cs[0] <= rspan[0] and rspan[1] <= cs[1], plan)
        self.assertTrue(cs[0] <= yspan[0] and yspan[1] <= cs[1], plan)
        rq = a1.get("retrieval_query")
        self.assertIsInstance(rq, str, plan)
        self.assertTrue(rq.strip(), plan)
        self.assertIn("polished", rq.casefold(), plan)
        self.assertIs(validate_fn(plan, QY), True, plan)
        self.assertIs(validate_fn(plan, QY, max_hops=2, max_searches=4), True, plan)

        # Ground: same-sentence exact year only binds.
        pos = ground_fn(
            a1, {},
            [{"title": YTITLE, "url": YURL, "extract": YSENT}],
            query=QY,
        )
        self.assertIsInstance(pos, dict, pos)
        self.assertEqual(pos.get("status"), "grounded", pos)
        self.assertEqual(pos.get("binding"), "Vale", pos)
        self.assertIn(YSENT, str(pos.get("proof")), pos)
        comp = compose_fn(plan, {"a1": pos.get("proof")}, QY,
                           max_sources=5, max_answer_chars=8000)
        self.assertIsInstance(comp, dict, comp)
        self.assertEqual(comp.get("binding"), "Vale", comp)
        ans = comp.get("answer")
        self.assertIsInstance(ans, str, comp)
        self.assertIn(YSENT, ans, comp)
        self.assertIn("[1]", ans, comp)
        srcs = comp.get("sources")
        self.assertIsInstance(srcs, list, comp)
        self.assertEqual(len(srcs), 1, comp)
        self.assertEqual(srcs[0].get("url"), YURL, comp)

        # Missing/wrong/split-sentence year never satisfies 2019.
        for bad in (
            "Vale polished Quartz.",
            "Vale polished Quartz in 2018.",
            "Vale polished Quartz. The year was 2019.",
        ):
            with self.subTest(bad=bad):
                got = ground_fn(
                    a1, {},
                    [{"title": YTITLE, "url": YURL, "extract": bad}],
                    query=QY,
                )
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), "ungrounded", got)
                self.assertNotIn("binding", got, got)
                self.assertNotIn("proof", got, got)
        with self.subTest(kind="title-year-only"):
            got = ground_fn(
                a1, {},
                [{"title": "Vale polished Quartz in 2019",
                  "url": YURL,
                  "extract": "Vale polished Quartz in 2018."}],
                query=QY,
            )
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)

        # Matching-year denial contradicts; different-year denial does not.
        DENY = "Vale did not polish Quartz in 2019."
        DENY_URL = "https://evidence.example/deny-quartz-2019"
        paired = [
            {"title": YTITLE, "url": YURL, "extract": YSENT},
            {"title": "Denial", "url": DENY_URL, "extract": DENY},
        ]
        for cands in (paired, list(reversed(paired))):
            with self.subTest(kind="matching-denial"):
                got = ground_fn(a1, {}, cands, query=QY)
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), "ungrounded", got)
                self.assertNotIn("binding", got, got)
                self.assertNotIn("proof", got, got)
        with self.subTest(kind="different-year-denial-grounds"):
            got = ground_fn(
                a1, {},
                [{"title": YTITLE, "url": YURL, "extract": YSENT},
                 {"title": "Denial", "url": DENY_URL,
                  "extract": "Vale did not polish Quartz in 2018."}],
                query=QY,
            )
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "grounded", got)
            self.assertEqual(got.get("binding"), "Vale", got)
            self.assertIn(YSENT, str(got.get("proof")), got)

        # Validator: erased/changed/non-string year or bool/drift span rejected.
        with self.subTest(kind="year-erased"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["constraints"] = {}
            self.assertIs(validate_fn(mutated, QY), False, mutated)
            res = ground_fn(copy.deepcopy(mutated["atoms"][0]), {},
                            [{"title": YTITLE, "url": YURL, "extract": YSENT}],
                            query=QY)
            self.assertEqual(res.get("status"), "ungrounded", res)
            self.assertNotIn("binding", res, res)
            self.assertNotIn("proof", res, res)
        with self.subTest(kind="year-changed"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["constraints"]["year"] = "2018"
            self.assertIs(validate_fn(mutated, QY), False, mutated)
            res = ground_fn(copy.deepcopy(mutated["atoms"][0]), {},
                            [{"title": YTITLE, "url": YURL, "extract": YSENT}],
                            query=QY)
            self.assertEqual(res.get("status"), "ungrounded", res)
        with self.subTest(kind="year-non-string"):
            mutated = copy.deepcopy(plan)
            mutated["atoms"][0]["constraints"]["year"] = 2019
            self.assertIs(validate_fn(mutated, QY), False, mutated)
            res = ground_fn(copy.deepcopy(mutated["atoms"][0]), {},
                            [{"title": YTITLE, "url": YURL, "extract": YSENT}],
                            query=QY)
            self.assertEqual(res.get("status"), "ungrounded", res)
        with self.subTest(kind="year-span-bool"):
            mutated = copy.deepcopy(plan)
            ys = list(mutated["atoms"][0]["constraints"]["year_span"])
            mutated["atoms"][0]["constraints"]["year_span"] = [True, ys[1]]
            self.assertIs(validate_fn(mutated, QY), False, mutated)
            res = ground_fn(copy.deepcopy(mutated["atoms"][0]), {},
                            [{"title": YTITLE, "url": YURL, "extract": YSENT}],
                            query=QY)
            self.assertEqual(res.get("status"), "ungrounded", res)
        with self.subTest(kind="year-span-drift"):
            mutated = copy.deepcopy(plan)
            ys = list(mutated["atoms"][0]["constraints"]["year_span"])
            mutated["atoms"][0]["constraints"]["year_span"] = [ys[0] + 1, ys[1] + 1]
            self.assertIs(validate_fn(mutated, QY), False, mutated)
            res = ground_fn(copy.deepcopy(mutated["atoms"][0]), {},
                            [{"title": YTITLE, "url": YURL, "extract": YSENT}],
                            query=QY)
            self.assertEqual(res.get("status"), "ungrounded", res)
        with self.subTest(kind="query-without-year"):
            self.assertIs(validate_fn(plan, "Who polished Quartz?"), False, plan)
            self.assertIs(validate_fn(plan, "Who polished Quartz in 2018?"), False, plan)

        # Ambiguous nested year suffix explicitly unsupported (no dropping).
        with self.subTest(kind="ambiguous-nested-suffix"):
            QA = "Who polished the component assembled by Arin in 2019?"
            pa = plan_fn(QA, max_hops=3, max_searches=4)
            self.assertIsInstance(pa, dict, pa)
            self.assertEqual(pa.get("atoms"), [], pa)
            self.assertEqual(pa.get("output"), "", pa)
            self.assertIs(validate_fn(pa, QA), False, pa)
            ca = compose_fn(pa, {}, QA, max_sources=5, max_answer_chars=8000)
            self.assertIn("error", ca, ca)

        # Unsupported arithmetic: generic operator semantics, no entity exception.
        with self.subTest(kind="unsupported-arithmetic"):
            QB = "How many years between the births of Arin and Vale?"
            pb = plan_fn(QB, max_hops=2, max_searches=4)
            self.assertIsInstance(pb, dict, pb)
            self.assertEqual(pb.get("atoms"), [], pb)
            self.assertEqual(pb.get("output"), "", pb)
            self.assertEqual(pb.get("reason"), "unsupported_arithmetic", pb)
            self.assertNotIn("Arin", str(pb.get("reason")), pb)
            self.assertNotIn("Vale", str(pb.get("reason")), pb)
            self.assertIs(validate_fn(pb, QB), False, pb)
            cb = compose_fn(pb, {}, QB, max_sources=5, max_answer_chars=8000)
            self.assertIn("error", cb, cb)
            # No arithmetic provider/runtime calls: static candidates only.

        # Aliases/opaque/pronouns/conjunctions similarly no plan.
        for qx in (
            "Who polished it in 2019?",
            "Who polished Quartz and Lumen in 2019?",
            "Who polished Quartz or Lumen in 2019?",
            "Who polished Quartz's component in 2019?",
        ):
            with self.subTest(qx=qx):
                px = plan_fn(qx, max_hops=2, max_searches=4)
                self.assertIsInstance(px, dict, px)
                self.assertEqual(px.get("atoms"), [], px)
                self.assertEqual(px.get("output"), "", px)
                self.assertIs(validate_fn(px, qx), False, px)

        # Overlong original question invalid; must not echo overlong query.
        with self.subTest(kind="overlong"):
            QLONG = QY + " " + ("X" * 2005)
            self.assertTrue(len(QLONG) > 2000, QLONG[:64])
            pl = plan_fn(QLONG, max_hops=2, max_searches=4)
            self.assertIsInstance(pl, dict, pl)
            self.assertEqual(pl.get("atoms"), [], pl)
            self.assertEqual(pl.get("output"), "", pl)
            self.assertIs(validate_fn(pl, QLONG), False, pl)
            self.assertEqual(pl.get("query"), "", pl)
            cl = compose_fn(pl, {}, QLONG, max_sources=5, max_answer_chars=8000)
            self.assertIn("error", cl, cl)


    def test_bounded_scan_does_not_hide_late_ambiguity_or_contradiction(self):
        import copy
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        validate_fn = getattr(answer_synth, "validate_evidence_query_plan", None)
        self.assertTrue(callable(validate_fn), "missing validator")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        compose_fn = getattr(answer_synth, "compose_evidence_query_plan", None)
        self.assertTrue(callable(compose_fn), "missing composer")
        plan = plan_fn(QUERY, max_hops=2, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        self.assertIs(validate_fn(plan, QUERY), True, plan)
        atoms = plan.get("atoms")
        self.assertIsInstance(atoms, list, plan)
        self.assertEqual(len(atoms), 2, plan)
        a1 = atoms[0]
        a2 = atoms[1]
        LATE = "Mira created the device Lattice."
        DENIAL = "Mira did not create the device Beacon."
        EVIL_URL = "https://evil.example/phish"
        ALT_URL = "https://evidence.example/alternate"

        # Bounded single-extract late ambiguity: 10x Beacon then Lattice, well below 8000.
        ext_amb = " ".join([SENTENCE_A1] * 10 + [LATE])
        self.assertLess(len(ext_amb), 8000, ext_amb)
        res = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": ext_amb}], query=QUERY)
        self.assertIsInstance(res, dict, res)
        self.assertEqual(res.get("status"), "ungrounded", res)
        self.assertEqual(res.get("reason"), "ambiguous_binding", res)
        self.assertNotIn("binding", res, res)
        self.assertNotIn("proof", res, res)
        srcs = res.get("intermediate_sources")
        self.assertIsInstance(srcs, list, res)
        self.assertTrue(any(isinstance(s, dict) and s.get("url") == CREATION_URL for s in srcs), res)

        # Reverse sentence order preserves unresolved ambiguity.
        ext_rev = " ".join([LATE] + [SENTENCE_A1] * 10)
        rev = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": ext_rev}], query=QUERY)
        self.assertIsInstance(rev, dict, rev)
        self.assertEqual(rev.get("status"), "ungrounded", rev)
        self.assertEqual(rev.get("reason"), "ambiguous_binding", rev)
        self.assertNotIn("binding", rev, rev)
        self.assertNotIn("proof", rev, rev)

        # Duplicate positives alone ground uniquely, not raw-count ambiguity.
        dup = " ".join([SENTENCE_A1] * 10)
        got_dup = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": dup}], query=QUERY)
        self.assertIsInstance(got_dup, dict, got_dup)
        self.assertEqual(got_dup.get("status"), "grounded", got_dup)
        self.assertEqual(got_dup.get("binding"), "Beacon", got_dup)
        self.assertIn(SENTENCE_A1, str(got_dup.get("proof")), got_dup)

        # Exhaustive across all allowed <=5 candidates: late in 5th still ambiguous.
        cands5 = [
            {"title": "C0", "url": "https://evidence.example/c0", "extract": " ".join([SENTENCE_A1] * 2)},
            {"title": "C1", "url": "https://evidence.example/c1", "extract": " ".join([SENTENCE_A1] * 2)},
            {"title": "C2", "url": "https://evidence.example/c2", "extract": " ".join([SENTENCE_A1] * 2)},
            {"title": "C3", "url": "https://evidence.example/c3", "extract": " ".join([SENTENCE_A1] * 2)},
            {"title": "Late", "url": ALT_URL, "extract": LATE},
        ]
        res5 = ground_fn(a1, {}, cands5, query=QUERY)
        self.assertIsInstance(res5, dict, res5)
        self.assertEqual(res5.get("status"), "ungrounded", res5)
        self.assertEqual(res5.get("reason"), "ambiguous_binding", res5)
        self.assertNotIn("binding", res5, res5)
        self.assertNotIn("proof", res5, res5)
        urls5 = {s.get("url") for s in res5.get("intermediate_sources", []) if isinstance(s, dict)}
        self.assertIn(ALT_URL, urls5, res5)
        rev5 = ground_fn(a1, {}, list(reversed(cands5)), query=QUERY)
        self.assertIsInstance(rev5, dict, rev5)
        self.assertEqual(rev5.get("status"), "ungrounded", rev5)
        self.assertEqual(rev5.get("reason"), "ambiguous_binding", rev5)
        self.assertNotIn("binding", rev5, rev5)
        self.assertNotIn("proof", rev5, rev5)
        rurls = {s.get("url") for s in rev5.get("intermediate_sources", []) if isinstance(s, dict)}
        self.assertEqual(rurls, urls5, rev5)

        # Early-break must not hide late alternative: 9 pos + 9 neg + late must stay ambiguous.
        ext_hide = " ".join([SENTENCE_A1] * 9 + [DENIAL] * 9 + [LATE])
        hid = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": ext_hide}], query=QUERY)
        self.assertIsInstance(hid, dict, hid)
        self.assertEqual(hid.get("status"), "ungrounded", hid)
        self.assertEqual(hid.get("reason"), "ambiguous_binding", hid)
        self.assertNotIn("binding", hid, hid)
        self.assertNotIn("proof", hid, hid)

        # Late same-binding contradiction: 10x Beacon then denial blocks.
        ext_contra = " ".join([SENTENCE_A1] * 10 + [DENIAL])
        self.assertLess(len(ext_contra), 8000, ext_contra)
        rc = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": ext_contra}], query=QUERY)
        self.assertIsInstance(rc, dict, rc)
        self.assertEqual(rc.get("status"), "ungrounded", rc)
        self.assertEqual(rc.get("reason"), "contradiction", rc)
        self.assertNotIn("binding", rc, rc)
        self.assertNotIn("proof", rc, rc)
        rc_rev = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": " ".join([DENIAL] + [SENTENCE_A1] * 10)}], query=QUERY)
        self.assertIsInstance(rc_rev, dict, rc_rev)
        self.assertEqual(rc_rev.get("status"), "ungrounded", rc_rev)
        self.assertEqual(rc_rev.get("reason"), "contradiction", rc_rev)
        self.assertNotIn("binding", rc_rev, rc_rev)
        self.assertNotIn("proof", rc_rev, rc_rev)

        # Proof-retention boundaries: >8000 must fail closed, not partial truncation.
        pad = " ".join(["Padding."] * 2000)
        big_ext = SENTENCE_A1 + " " + pad + " " + LATE
        self.assertGreater(len(big_ext), 8000, len(big_ext))
        big = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": big_ext}], query=QUERY)
        self.assertIsInstance(big, dict, big)
        self.assertEqual(big.get("status"), "ungrounded", big)
        self.assertNotIn("binding", big, big)
        self.assertNotIn("proof", big, big)

        # >5 candidates must abstain.
        many = [{"title": "T%d" % i, "url": "https://evidence.example/x%d" % i, "extract": SENTENCE_A1} for i in range(6)]
        got_many = ground_fn(a1, {}, many, query=QUERY)
        self.assertIsInstance(got_many, dict, got_many)
        self.assertEqual(got_many.get("status"), "ungrounded", got_many)
        self.assertNotIn("binding", got_many, got_many)
        self.assertNotIn("proof", got_many, got_many)

        # Leading/trailing whitespace URL rejected AS GIVEN, not strip-repaired.
        for bad_url in (" " + CREATION_URL, CREATION_URL + " ", " " + CREATION_URL + " "):
            with self.subTest(bad_url=repr(bad_url)):
                got = ground_fn(a1, {}, [{"title": "Creation", "url": bad_url, "extract": SENTENCE_A1}], query=QUERY)
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), "ungrounded", got)
                self.assertNotIn("binding", got, got)
                self.assertNotIn("proof", got, got)

        # Control-bearing title sanitized: never include controls in output.
        ctrl_cands = [
            {"title": "Bad\x00Title", "url": CREATION_URL, "extract": SENTENCE_A1},
            {"title": "Alt", "url": ALT_URL, "extract": LATE},
        ]
        ctrl = ground_fn(a1, {}, ctrl_cands, query=QUERY)
        self.assertIsInstance(ctrl, dict, ctrl)
        self.assertEqual(ctrl.get("status"), "ungrounded", ctrl)
        self.assertEqual(ctrl.get("reason"), "ambiguous_binding", ctrl)
        for s in ctrl.get("intermediate_sources", []):
            self.assertIsInstance(s, dict, ctrl)
            self.assertNotIn("\x00", str(s.get("title", "")), ctrl)
            self.assertNotIn("\x00", str(s.get("url", "")), ctrl)

        # Title/snippet/citation/binding/source keys never authoritative.
        forged = {
            "title": LATE,
            "url": CREATION_URL,
            "extract": SENTENCE_A1,
            "snippet": DENIAL,
            "citation": "[99]",
            "binding": "Lattice",
            "source": {"url": EVIL_URL},
            "modelanswer": "Lattice",
            "modelbinding": "Lattice",
            "modelcitation": "[99]",
        }
        got_forged = ground_fn(a1, {}, [forged], query=QUERY)
        self.assertIsInstance(got_forged, dict, got_forged)
        self.assertEqual(got_forged.get("status"), "grounded", got_forged)
        self.assertEqual(got_forged.get("binding"), "Beacon", got_forged)
        self.assertIn(SENTENCE_A1, str(got_forged.get("proof")), got_forged)
        self.assertNotIn(EVIL_URL, str(got_forged.get("proof")), got_forged)
        self.assertNotIn("[99]", str(got_forged.get("proof")), got_forged)

        # Valid 2-proof chain then composer boundary guards.
        r1 = ground_fn(a1, {}, [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}], query=QUERY)
        self.assertEqual(r1.get("status"), "grounded", r1)
        p1 = r1.get("proof")
        r2 = ground_fn(a2, {"a1": p1}, [{"title": "Design", "url": DESIGN_URL, "extract": SENTENCE_A2}], query=QUERY)
        self.assertEqual(r2.get("status"), "grounded", r2)
        p2 = r2.get("proof")
        full = compose_fn(plan, {"a1": p1, "a2": p2}, QUERY, max_sources=5, max_answer_chars=8000)
        self.assertIsInstance(full, dict, full)
        self.assertEqual(full.get("binding"), "Tavi", full)
        self.assertIn(SENTENCE_A1, full.get("answer", ""), full)
        self.assertIn(SENTENCE_A2, full.get("answer", ""), full)
        for missing in ({"a2": p2}, {"a1": p1}, {}):
            with self.subTest(missing=tuple(sorted(missing.keys()))):
                got = compose_fn(plan, missing, QUERY, max_sources=5, max_answer_chars=8000)
                self.assertIn("error", got, got)
                self.assertIn("INSUFFICIENT_EVIDENCE", str(got), got)
        got = compose_fn(plan, {"a1": p1, "a2": p2}, QUERY, max_sources=1, max_answer_chars=8000)
        self.assertIn("error", got, got)
        tiny = len(SENTENCE_A2 + " [2]")
        got = compose_fn(plan, {"a1": p1, "a2": p2}, QUERY, max_sources=5, max_answer_chars=tiny)
        self.assertIn("error", got, got)
        for bad_max in (True, False, 0, 6, "5"):
            with self.subTest(bad_max=repr(bad_max)):
                got = compose_fn(plan, {"a1": p1, "a2": p2}, QUERY, max_sources=bad_max, max_answer_chars=8000)
                self.assertIn("error", got, got)
        for bad_chars in (True, False, 0, 8001, "8000"):
            with self.subTest(bad_chars=repr(bad_chars)):
                got = compose_fn(plan, {"a1": p1, "a2": p2}, QUERY, max_sources=5, max_answer_chars=bad_chars)
                self.assertIn("error", got, got)
        for fake in ("Tavi", {"binding": "Tavi"}, dict(p2)):
            with self.subTest(fake=str(fake)[:32]):
                bad = ground_fn(a2, {"a1": fake}, [{"title": "Design", "url": DESIGN_URL, "extract": SENTENCE_A2}], query=QUERY)
                self.assertEqual(bad.get("status"), "ungrounded", bad)
                self.assertNotIn("binding", bad, bad)
                self.assertNotIn("proof", bad, bad)
                cgot = compose_fn(plan, {"a1": fake, "a2": p2}, QUERY, max_sources=5, max_answer_chars=8000)
                self.assertIn("error", cgot, cgot)
        mutated = copy.deepcopy(p1)
        # Exposed dict mutation must never become authoritative.
        try:
            mutated["binding"] = "Lattice"
            mutated["source"] = {"url": EVIL_URL, "title": "Evil"}
        except Exception:
            pass
        cgot = compose_fn(plan, {"a1": mutated, "a2": p2}, QUERY, max_sources=5, max_answer_chars=8000)
        self.assertIsInstance(cgot, dict, cgot)
        if "binding" in cgot:
            self.assertNotEqual(cgot.get("binding"), "Lattice", cgot)
            self.assertEqual(cgot.get("binding"), "Beacon" if "Beacon" in str(cgot) else cgot.get("binding"), cgot)
        self.assertNotIn(EVIL_URL, str(cgot), cgot)
        self.assertNotIn("Lattice", str(cgot.get("answer", "")), cgot)
        got = compose_fn(plan, {"a1": p1, "a2": p2}, "Who designed the device created by Nera?", max_sources=5, max_answer_chars=8000)
        self.assertIn("error", got, got)

        # Closed IR arrays are strict lists, not tuples.
        mut_span = copy.deepcopy(plan)
        mut_span["atoms"][0]["relation"]["span"] = tuple(mut_span["atoms"][0]["relation"]["span"])
        self.assertIs(validate_fn(mut_span, QUERY), False, mut_span)
        res_span = ground_fn(mut_span["atoms"][0], {}, [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}], query=QUERY)
        self.assertEqual(res_span.get("status"), "ungrounded", res_span)
        self.assertNotIn("binding", res_span, res_span)
        self.assertNotIn("proof", res_span, res_span)
        mut_dep = copy.deepcopy(plan)
        mut_dep["atoms"][1]["depends_on"] = tuple(mut_dep["atoms"][1]["depends_on"])
        self.assertIs(validate_fn(mut_dep, QUERY), False, mut_dep)
        res_dep = ground_fn(a2, {"a1": p1}, [{"title": "Design", "url": DESIGN_URL, "extract": SENTENCE_A2}], query=QUERY)
        # Sanity: valid list deps still ground; tuple plan itself must not validate.
        self.assertEqual(res_dep.get("status"), "grounded", res_dep)

        # Original questions with controls must abstain, not collapse.
        for bad_q in (
            QUERY.replace("Mira", "Mi\nra"),
            QUERY.replace("Mira", "Mi\tra"),
            QUERY.replace("Mira", "Mira\x00"),
            "Who designed the device created by\nMira?",
            "Who designed the device created by\tMira?",
        ):
            with self.subTest(bad_q=repr(bad_q)):
                pq = plan_fn(bad_q, max_hops=2, max_searches=4)
                self.assertIsInstance(pq, dict, pq)
                self.assertEqual(pq.get("atoms"), [], pq)
                self.assertEqual(pq.get("output"), "", pq)
                self.assertIs(validate_fn(pq, bad_q), False, pq)
        for bad_q in (
            "Who designed the device created by 'Mira'?",
            "Who designed the device created by \"Mira\"?",
            "Who designed the device created by Mira,?",
        ):
            with self.subTest(bad_q=bad_q):
                pq = plan_fn(bad_q, max_hops=2, max_searches=4)
                self.assertIsInstance(pq, dict, pq)
                self.assertEqual(pq.get("atoms"), [], pq)
                self.assertEqual(pq.get("output"), "", pq)
                self.assertIs(validate_fn(pq, bad_q), False, pq)

    def test_oversized_extract_is_rejected_before_binding(self):
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        plan = plan_fn(QUERY, max_hops=2, max_searches=4)
        a1 = plan.get("atoms")[0]
        ctrl = ground_fn(
            a1, {},
            [{"title": "Creation", "url": CREATION_URL,
              "extract": "Mira created the device Beacon."}],
            query=QUERY,
        )
        self.assertEqual(ctrl.get("status"), "grounded", ctrl)
        self.assertEqual(ctrl.get("binding"), "Beacon", ctrl)
        big = SENTENCE_A1 + " " + ("Padding. " * 1200)
        self.assertGreater(len(big), 8000, len(big))
        res = ground_fn(
            a1, {},
            [{"title": "Creation", "url": CREATION_URL, "extract": big}],
            query=QUERY,
        )
        self.assertEqual(res.get("status"), "ungrounded", res)
        self.assertNotIn("binding", res, res)
        self.assertNotIn("proof", res, res)
        pad = "Padding. " * 1200
        self.assertGreater(len(pad), 8000, len(pad))
        batch = [
            {"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1},
            {"title": "Distractor", "url": DISTRACTOR_URL, "extract": pad},
        ]
        got = ground_fn(a1, {}, batch, query=QUERY)
        self.assertEqual(got.get("status"), "ungrounded", got)
        self.assertNotIn("binding", got, got)
        self.assertNotIn("proof", got, got)
        rev = ground_fn(a1, {}, list(reversed(batch)), query=QUERY)
        self.assertEqual(rev.get("status"), "ungrounded", rev)
        self.assertNotIn("binding", rev, rev)
        self.assertNotIn("proof", rev, rev)

    def test_scalar_binding_rejects_entity_lists(self):
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        plan = plan_fn(QUERY, max_hops=2, max_searches=4)
        a1 = plan.get("atoms")[0]
        ctrl = ground_fn(
            a1, {},
            [{"title": "Creation", "url": CREATION_URL, "extract": SENTENCE_A1}],
            query=QUERY,
        )
        self.assertEqual(ctrl.get("status"), "grounded", ctrl)
        self.assertEqual(ctrl.get("binding"), "Beacon", ctrl)
        for bad in (
            "Mira created the device Beacon, Lattice.",
            "Mira created the device Beacon & Lattice.",
            "Mira created the device Beacon; Lattice.",
        ):
            with self.subTest(bad=bad):
                got = ground_fn(
                    a1, {},
                    [{"title": "Creation", "url": CREATION_URL, "extract": bad}],
                    query=QUERY,
                )
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), "ungrounded", got)
                self.assertNotIn("binding", got, got)
                self.assertNotIn("proof", got, got)


    def test_named_identity_preserves_hyphens_and_apostrophes(self):
        Q1 = "Who designed the device created by Mira-Dawn?"
        P1 = "Mira-Dawn created the device Beacon."
        W1 = "Mira Dawn created the device Beacon."
        Q2 = "Who designed the device created by O'Neil?"
        P2 = "O'Neil created the device Beacon."
        W2 = "O Neil created the device Beacon."
        U1 = "https://evidence.example/creation-hyphen"
        U2 = "https://evidence.example/creation-spaced"
        U3 = "https://evidence.example/creation-apos"
        U4 = "https://evidence.example/creation-plain"
        for kind, qq, sent, url, exp in (
            ("hyphen-pos", Q1, P1, U1, "grounded"),
            ("hyphen-neg", Q1, W1, U2, "ungrounded"),
            ("apos-pos", Q2, P2, U3, "grounded"),
            ("apos-neg", Q2, W2, U4, "ungrounded"),
        ):
            with self.subTest(kind=kind):
                plan_fn = getattr(answer_synth, "plan_evidence_query", None)
                self.assertTrue(callable(plan_fn), kind)
                validate_fn = getattr(answer_synth, "validate_evidence_query_plan", None)
                self.assertTrue(callable(validate_fn), kind)
                ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
                self.assertTrue(callable(ground_fn), kind)
                plan = plan_fn(qq, max_hops=2, max_searches=4)
                self.assertIsInstance(plan, dict, kind)
                self.assertEqual(len(plan.get("atoms", [])), 2, kind)
                self.assertEqual(plan.get("output"), "v2", kind)
                self.assertIs(validate_fn(plan, qq), True, kind)
                a1 = plan["atoms"][0]
                got = ground_fn(a1, {}, [{"title": "Creation", "url": url, "extract": sent}], query=qq)
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), exp, got)
                if exp == "grounded":
                    self.assertEqual(got.get("binding"), "Beacon", got)
                    self.assertIn(sent, str(got.get("proof")), got)
                else:
                    self.assertNotIn("binding", got, got)
                    self.assertNotIn("proof", got, got)
        for kind, s_a, s_b, u_a, u_b in (
            ("hyphen-var", "Mira created the device Mary-Jane.", "Mira created the device Mary Jane.", "https://evidence.example/mary-hyphen", "https://evidence.example/mary-space"),
            ("apos-var", "Mira created the device O'Neil.", "Mira created the device O Neil.", "https://evidence.example/oneil-apos", "https://evidence.example/oneil-space"),
        ):
            for tag, cands in (("fwd", [{"title": "A", "url": u_a, "extract": s_a}, {"title": "B", "url": u_b, "extract": s_b}]), ("rev", [{"title": "B", "url": u_b, "extract": s_b}, {"title": "A", "url": u_a, "extract": s_a}])):
                with self.subTest(kind=kind + "-" + tag):
                    plan_fn = getattr(answer_synth, "plan_evidence_query", None)
                    self.assertTrue(callable(plan_fn), kind)
                    ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
                    self.assertTrue(callable(ground_fn), kind)
                    plan = plan_fn(QUERY, max_hops=2, max_searches=4)
                    a1 = plan.get("atoms", [{}])[0]
                    got = ground_fn(a1, {}, cands, query=QUERY)
                    self.assertIsInstance(got, dict, got)
                    self.assertEqual(got.get("status"), "ungrounded", got)
                    self.assertEqual(got.get("reason"), "ambiguous_binding", got)
                    self.assertNotIn("binding", got, got)
                    self.assertNotIn("proof", got, got)
                    srcs = got.get("intermediate_sources")
                    self.assertIsInstance(srcs, list, got)
                    self.assertEqual(len(srcs), 2, got)
                    self.assertEqual({s.get("url") for s in srcs if isinstance(s, dict)}, {u_a, u_b}, got)
        with self.subTest(kind="hyphen-cross-denial-grounds"):
            plan_fn = getattr(answer_synth, "plan_evidence_query", None)
            self.assertTrue(callable(plan_fn))
            ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
            self.assertTrue(callable(ground_fn))
            plan = plan_fn(QUERY, max_hops=2, max_searches=4)
            a1 = plan.get("atoms", [{}])[0]
            pos = "Mira created the device Mary-Jane."
            cands = [{"title": "A", "url": "https://evidence.example/mary-hyphen", "extract": pos}, {"title": "D", "url": "https://evidence.example/denial-space", "extract": "Mira did not create the device Mary Jane."}]
            got = ground_fn(a1, {}, cands, query=QUERY)
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "grounded", got)
            self.assertEqual(got.get("binding"), "Mary-Jane", got)
            self.assertIn(pos, str(got.get("proof")), got)
        with self.subTest(kind="hyphen-same-denial-contradiction"):
            plan_fn = getattr(answer_synth, "plan_evidence_query", None)
            self.assertTrue(callable(plan_fn))
            ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
            self.assertTrue(callable(ground_fn))
            plan = plan_fn(QUERY, max_hops=2, max_searches=4)
            a1 = plan.get("atoms", [{}])[0]
            pos = "Mira created the device Mary-Jane."
            cands = [{"title": "A", "url": "https://evidence.example/mary-hyphen", "extract": pos}, {"title": "D", "url": "https://evidence.example/denial-hyphen", "extract": "Mira did not create the device Mary-Jane."}]
            got = ground_fn(a1, {}, cands, query=QUERY)
            self.assertIsInstance(got, dict, got)
            self.assertEqual(got.get("status"), "ungrounded", got)
            self.assertNotIn("binding", got, got)
            self.assertNotIn("proof", got, got)


    def test_regular_past_denials_preserve_morphology(self):
        plan_fn = getattr(answer_synth, "plan_evidence_query", None)
        self.assertTrue(callable(plan_fn), "missing planner")
        validate_fn = getattr(answer_synth, "validate_evidence_query_plan", None)
        self.assertTrue(callable(validate_fn), "missing validator")
        ground_fn = getattr(answer_synth, "ground_evidence_atom", None)
        self.assertTrue(callable(ground_fn), "missing grounder")
        for past, base in (("carried", "carry"), ("stopped", "stop")):
            qq = "Who designed the device " + past + " by Mira?"
            pos = "Mira " + past + " the device Beacon."
            with self.subTest(kind="positive-" + past):
                plan = plan_fn(qq, max_hops=2, max_searches=4)
                self.assertIsInstance(plan, dict, qq)
                self.assertIs(validate_fn(plan, qq), True, plan)
                a1 = plan.get("atoms", [{}])[0]
                got = ground_fn(
                    a1, {},
                    [{"title": "Creation", "url": CREATION_URL, "extract": pos}],
                    query=qq,
                )
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), "grounded", got)
                self.assertEqual(got.get("binding"), "Beacon", got)
                self.assertIn(pos, str(got.get("proof")), got)
            with self.subTest(kind="denial-" + past):
                plan = plan_fn(qq, max_hops=2, max_searches=4)
                a1 = plan.get("atoms", [{}])[0]
                neg = "Mira did not " + base + " the device Beacon."
                cands = [
                    {"title": "Creation", "url": CREATION_URL, "extract": pos},
                    {"title": "Denial", "url": "https://evidence.example/denial", "extract": neg},
                ]
                for ordered in (cands, list(reversed(cands))):
                    got = ground_fn(a1, {}, ordered, query=qq)
                    self.assertIsInstance(got, dict, got)
                    self.assertEqual(got.get("status"), "ungrounded", got)
                    self.assertEqual(got.get("reason"), "contradiction", got)
                    self.assertNotIn("binding", got, got)
                    self.assertNotIn("proof", got, got)
            with self.subTest(kind="contraction-" + past):
                plan = plan_fn(qq, max_hops=2, max_searches=4)
                a1 = plan.get("atoms", [{}])[0]
                neg = "Mira didn't " + base + " the device Beacon."
                cands = [
                    {"title": "Creation", "url": CREATION_URL, "extract": pos},
                    {"title": "Denial", "url": "https://evidence.example/denial", "extract": neg},
                ]
                for ordered in (cands, list(reversed(cands))):
                    got = ground_fn(a1, {}, ordered, query=qq)
                    self.assertIsInstance(got, dict, got)
                    self.assertEqual(got.get("status"), "ungrounded", got)
                    self.assertEqual(got.get("reason"), "contradiction", got)
                    self.assertNotIn("binding", got, got)
                    self.assertNotIn("proof", got, got)
            with self.subTest(kind="scope-" + past):
                plan = plan_fn(qq, max_hops=2, max_searches=4)
                a1 = plan.get("atoms", [{}])[0]
                cands = [
                    {"title": "Creation", "url": CREATION_URL, "extract": pos},
                    {"title": "Denial", "url": "https://evidence.example/denial", "extract": "Nera did not " + base + " the device Beacon."},
                ]
                got = ground_fn(a1, {}, cands, query=qq)
                self.assertIsInstance(got, dict, got)
                self.assertEqual(got.get("status"), "grounded", got)
                self.assertEqual(got.get("binding"), "Beacon", got)
                self.assertIn(pos, str(got.get("proof")), got)


if __name__ == "__main__":
    unittest.main()
