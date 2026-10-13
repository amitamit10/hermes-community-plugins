"""Cycle3 vertical TDD: compositional research planner RED tests (offline, TEST-ONLY).

Synthetic grammar only; no benchmark questions/golds inspected.
"""
import random
import re
import socket
import string
import unittest

import answer_synth


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


QUERY = "Who designed the capital of the body orbited by Runa?"


class ResearchPlannerTests(OfflineTestCase):
    def test_plan_research_query_emits_three_step_chain(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(
            callable(plan_fn),
            "missing answer_synth.plan_research_query compositional planner",
        )
        plan = plan_fn(QUERY, max_hops=3, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "compositional", plan)
        steps = plan.get("steps")
        self.assertIsInstance(steps, list, plan)
        self.assertEqual(len(steps), 3, plan)
        ids = [s.get("id") for s in steps]
        self.assertEqual(ids, ["s1", "s2", "s3"], plan)
        self.assertEqual(steps[0].get("depends_on"), [], plan)
        self.assertEqual(steps[1].get("depends_on"), ["s1"], plan)
        self.assertEqual(steps[2].get("depends_on"), ["s2"], plan)
        self.assertEqual(
            [s.get("depth") for s in steps], [1, 2, 3], plan
        )
        self.assertEqual(
            steps[0].get("query_template"), "What does Runa orbit?", plan
        )
        self.assertEqual(
            steps[1].get("query_template"),
            "What is the capital of {s1}?",
            plan,
        )
        self.assertEqual(
            steps[2].get("query_template"), "Who designed {s2}?", plan
        )
        # Grounding templates must reference the same bindings.
        for step, placeholder in (("s2", "{s1}"), ("s3", "{s2}")):
            row = next(s for s in steps if s.get("id") == step)
            grounding = row.get("grounding_template", row.get("query_template"))
            self.assertIn(placeholder, row.get("query_template", ""), plan)
            self.assertIn(placeholder, grounding, plan)
        self.assertNotIn("{", steps[0].get("query_template", ""), plan)
        emits = [s.get("emit") for s in steps]
        self.assertEqual(emits, [False, False, True], plan)

    def test_planner_has_no_entities_hardcoded(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(
            callable(plan_fn),
            "missing answer_synth.plan_research_query compositional planner",
        )
        rnd = random.Random(20261012)
        def _neutral():
            return "".join(
                rnd.choice(string.ascii_lowercase) for _ in range(5)
            ).capitalize()
        leaf = _neutral()
        # Seeded neutral leaf; same grammar, no benchmark entities.
        self.assertNotIn(leaf, ("Runa", "Porta", "Luma"))
        q = "Who designed the capital of the body orbited by %s?" % leaf
        plan = plan_fn(q, max_hops=3, max_searches=4)
        self.assertEqual(plan.get("status"), "planned", plan)
        steps = plan.get("steps")
        self.assertEqual(len(steps), 3, plan)
        self.assertEqual(
            steps[0].get("query_template"),
            "What does %s orbit?" % leaf,
            plan,
        )
        self.assertEqual(
            steps[1].get("query_template"),
            "What is the capital of {s1}?",
            plan,
        )
        self.assertEqual(
            steps[2].get("query_template"), "Who designed {s2}?", plan
        )
        blob = str(plan)
        self.assertNotIn("Runa", blob)
        self.assertNotIn("Porta", blob)
        self.assertNotIn("Luma", blob)

    def test_validate_research_plan_api_exists(self):
        validate_fn = getattr(answer_synth, "validate_research_plan", None)
        self.assertTrue(
            callable(validate_fn),
            "missing answer_synth.validate_research_plan validator",
        )


class FacetPlanTests(OfflineTestCase):
    FACETS_QUERY = "Who wrote Cobalt?; Who designed Briar?"

    def test_facets_two_independent_terminal_steps(self):
        plan = answer_synth.plan_research_query(
            self.FACETS_QUERY, max_hops=1, max_searches=2
        )
        self.assertIsInstance(plan, dict, plan)
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "facets", plan)
        steps = plan.get("steps")
        self.assertIsInstance(steps, list, plan)
        self.assertEqual(len(steps), 2, plan)
        self.assertEqual([s.get("id") for s in steps], ["s1", "s2"], plan)
        self.assertEqual(steps[0].get("depends_on"), [], plan)
        self.assertEqual(steps[1].get("depends_on"), [], plan)
        self.assertEqual([s.get("depth") for s in steps], [1, 1], plan)
        self.assertEqual(steps[0].get("query_template"), "Who wrote Cobalt?", plan)
        self.assertEqual(steps[1].get("query_template"), "Who designed Briar?", plan)
        self.assertEqual(
            steps[0].get("grounding_template"), "Who wrote Cobalt?", plan
        )
        self.assertEqual(
            steps[1].get("grounding_template"), "Who designed Briar?", plan
        )
        self.assertEqual(
            steps[0].get("relation"), {"kind": "generic", "base": "write"}, plan
        )
        self.assertEqual(
            steps[1].get("relation"), {"kind": "generic", "base": "design"}, plan
        )
        self.assertEqual([s.get("emit") for s in steps], [True, True], plan)
        validate_fn = getattr(answer_synth, "validate_research_plan", None)
        self.assertTrue(callable(validate_fn))
        self.assertIs(validate_fn(plan), True, plan)

    def test_bare_conjunction_not_split(self):
        plan = answer_synth.plan_research_query(
            "Who wrote Cobalt and Briar?", max_hops=1, max_searches=2
        )
        self.assertEqual(plan.get("status"), "unsupported", plan)
        self.assertEqual(plan.get("steps"), [], plan)

    def test_facets_require_all_full_questions(self):
        for bad in (
            "Who wrote Cobalt?; nonsense fragment",
            "Who wrote Cobalt?;",
            "; Who designed Briar?",
            "Who wrote Cobalt?",
        ):
            with self.subTest(bad=bad):
                plan = answer_synth.plan_research_query(
                    bad, max_hops=1, max_searches=2
                )
                if bad == "Who wrote Cobalt?":
                    # Single supported question plans compositionally, not facets.
                    self.assertEqual(plan.get("status"), "planned", plan)
                    self.assertNotEqual(plan.get("chain_kind"), "facets", plan)
                else:
                    self.assertEqual(plan.get("status"), "unsupported", plan)

    def test_facets_bound_two_to_four(self):
        five = "; ".join(["Who wrote Cobalt?"] * 5)
        plan = answer_synth.plan_research_query(five, max_hops=1, max_searches=8)
        self.assertEqual(plan.get("status"), "unsupported", plan)

    def test_validator_dag_depth_rule(self):
        plan = answer_synth.plan_research_query(
            self.FACETS_QUERY, max_hops=1, max_searches=2
        )
        self.assertEqual(plan.get("status"), "planned", plan)
        validate_fn = answer_synth.validate_research_plan
        self.assertIs(validate_fn(plan), True, plan)
        import copy

        tampered = copy.deepcopy(plan)
        tampered["steps"][1]["depth"] = 2
        self.assertIs(validate_fn(tampered), False, tampered)


class PlannerHygieneTests(OfflineTestCase):
    def test_no_fixture_tokens_in_planner_production(self):
        import pathlib

        src = pathlib.Path(answer_synth.__file__).read_text(encoding="utf-8")
        # Planner must use symbolic validation; no synthetic entity literals.
        for token in ("Porta", "Runa", "Luma", "Cobalt", "Briar", "Vela", "Arbor"):
            self.assertNotIn(token, src, token)

    def test_default_max_hops_aligns_public_two(self):
        import inspect

        sig = inspect.signature(answer_synth.plan_research_query)
        self.assertEqual(sig.parameters["max_hops"].default, 2)


class ComparisonPlanTests(OfflineTestCase):
    def test_plural_capitals_plan(self):
        plan = answer_synth.plan_research_query(
            "What are the capitals of Porta and Vela?", max_hops=1, max_searches=2
        )
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "comparison", plan)
        steps = plan.get("steps")
        self.assertEqual(len(steps), 2, plan)
        self.assertEqual([s.get("id") for s in steps], ["s1", "s2"], plan)
        self.assertEqual([s.get("depth") for s in steps], [1, 1], plan)
        self.assertEqual(
            steps[0].get("query_template"), "What is the capital of Porta?", plan
        )
        self.assertEqual(
            steps[1].get("query_template"), "What is the capital of Vela?", plan
        )
        self.assertEqual([s.get("emit") for s in steps], [True, True], plan)
        self.assertIs(answer_synth.validate_research_plan(plan), True, plan)

    def test_compare_capitals_plan(self):
        plan = answer_synth.plan_research_query(
            "Compare the capitals of Porta and Vela.", max_hops=1, max_searches=2
        )
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "comparison", plan)
        steps = plan.get("steps")
        self.assertEqual(len(steps), 2, plan)
        self.assertIs(answer_synth.validate_research_plan(plan), True, plan)

    def test_bare_singular_conjunction_unsupported(self):
        plan = answer_synth.plan_research_query(
            "What is the capital of Porta and Vela?", max_hops=1, max_searches=2
        )
        self.assertEqual(plan.get("status"), "unsupported", plan)


class IntersectionPlanTests(OfflineTestCase):
    def test_author_intersection_plan(self):
        plan = answer_synth.plan_research_query(
            "Who both wrote Cobalt and designed Briar?",
            max_hops=1,
            max_searches=2,
        )
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "intersection", plan)
        steps = plan.get("steps")
        self.assertEqual(len(steps), 2, plan)
        self.assertEqual([s.get("id") for s in steps], ["s1", "s2"], plan)
        self.assertEqual([s.get("depth") for s in steps], [1, 1], plan)
        self.assertEqual(steps[0].get("query_template"), "Who wrote Cobalt?", plan)
        self.assertEqual(steps[1].get("query_template"), "Who designed Briar?", plan)
        self.assertEqual([s.get("emit") for s in steps], [True, True], plan)
        self.assertIs(answer_synth.validate_research_plan(plan), True, plan)

    def test_capital_intersection_plan(self):
        plan = answer_synth.plan_research_query(
            "Which city is the capital of both Porta and Vela?",
            max_hops=1,
            max_searches=2,
        )
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "intersection", plan)
        steps = plan.get("steps")
        self.assertEqual(len(steps), 2, plan)
        self.assertIs(answer_synth.validate_research_plan(plan), True, plan)


class TemporalPlannerTests(OfflineTestCase):
    WHEN_Q = "When was the inventor of Cobalt born?"
    WHERE_Q = "Where was the inventor of Cobalt born?"
    YEAR_Q = "Who invented Cobalt in 1984?"
    BEFORE_Q = "Was Mira Vale born before Nera Voss?"
    BETWEEN_Q = "How many years between the births of Mira Vale and Nera Voss?"
    PRONOUN_Q = "Which of those was earlier?"

    def test_when_born_chain_compiles_to_unchanged_grounding(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(
            callable(plan_fn),
            "missing answer_synth.plan_research_query compositional planner",
        )
        plan = plan_fn(self.WHEN_Q, max_hops=2, max_searches=4)
        self.assertIsInstance(plan, dict, plan)
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "compositional", plan)
        steps = plan.get("steps")
        self.assertIsInstance(steps, list, plan)
        self.assertEqual(len(steps), 2, plan)
        self.assertEqual([s.get("id") for s in steps], ["s1", "s2"], plan)
        self.assertEqual([s.get("depth") for s in steps], [1, 2], plan)
        self.assertEqual(steps[0].get("query_template"), "Who invented Cobalt?", plan)
        self.assertEqual(
            steps[0].get("grounding_template"), "Who invented Cobalt?", plan
        )
        self.assertEqual(
            steps[0].get("relation"), {"kind": "generic", "base": "invent"}, plan
        )
        # Terminal birth facet retrieves with bound subject, grounds on
        # unchanged keyword/relation shape plus strict subject-specific born.
        q2 = steps[1].get("query_template", "")
        g2 = steps[1].get("grounding_template", steps[1].get("query_template", ""))
        self.assertIn("{s1}", q2, plan)
        self.assertIn("born", q2.casefold(), plan)
        self.assertIn("{s1}", g2, plan)
        self.assertIn("born", g2.casefold(), plan)
        rel2 = steps[1].get("relation", {})
        self.assertIsInstance(rel2, dict, plan)
        blob2 = str(rel2).casefold() + " " + str(g2).casefold()
        self.assertIn("born", blob2, plan)
        self.assertEqual([s.get("emit") for s in steps], [False, True], plan)
        validate_fn = getattr(answer_synth, "validate_research_plan", None)
        self.assertTrue(callable(validate_fn))
        self.assertIs(validate_fn(plan), True, plan)

    def test_where_vs_when_strict_born_predicate(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        for q in (self.WHEN_Q, self.WHERE_Q):
            with self.subTest(q=q):
                plan = plan_fn(q, max_hops=2, max_searches=4)
                self.assertEqual(plan.get("status"), "planned", plan)
                steps = plan.get("steps")
                self.assertEqual(len(steps), 2, plan)
                # Predicate remains original keyword PLUS strict born shape.
                g2 = steps[1].get(
                    "grounding_template", steps[1].get("query_template", "")
                )
                self.assertIn("born", g2.casefold(), plan)
                rel2 = steps[1].get("relation", {})
                self.assertIn("born", str(rel2).casefold() + " " + g2.casefold(), plan)
                # Terminal grounding must stay subject-specific, not loosened
                # to a bare year or bare place token.
                self.assertIn("{s1}", g2, plan)

    def test_temporal_qualifier_year_templates(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(self.YEAR_Q, max_hops=1, max_searches=2)
        self.assertIsInstance(plan, dict, plan)
        self.assertEqual(plan.get("status"), "planned", plan)
        steps = plan.get("steps")
        self.assertIsInstance(steps, list, plan)
        self.assertEqual(len(steps), 1, plan)
        step = steps[0]
        retrieval = step.get("retrieval_template", step.get("query_template", ""))
        grounding = step.get("grounding_template", "")
        self.assertIn("1984", retrieval, plan)
        self.assertEqual(grounding, "Who invented Cobalt?", plan)
        cond = step.get("temporal_condition", plan.get("temporal_condition", None))
        self.assertIsNotNone(cond, plan)
        self.assertIn("1984", str(cond), plan)
        # No timestamp fabrication: plan records literal year only.
        self.assertNotIn("1985", str(plan), plan)

    def test_temporal_compare_emits_two_date_facets_unsupported(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(self.BEFORE_Q, max_hops=1, max_searches=2)
        self.assertIsInstance(plan, dict, plan)
        # Pure planner emits executable facets with answerable:false and a
        # stable unsupported-computation reason, not a random split.
        steps = plan.get("steps")
        self.assertIsInstance(steps, list, plan)
        self.assertEqual(len(steps), 2, plan)
        blob = str(steps)
        self.assertIn("Mira Vale", blob, plan)
        self.assertIn("Nera Voss", blob, plan)
        for row in steps:
            self.assertIn("born", str(row.get("query_template", "")).casefold(), plan)
        self.assertIs(plan.get("answerable"), False, plan)
        self.assertIn(
            str(plan.get("reason", "")), ("unsupported_temporal_compare",), plan
        )

    def test_arithmetic_between_unsupported_stable_reason(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(self.BETWEEN_Q, max_hops=1, max_searches=2)
        self.assertIsInstance(plan, dict, plan)
        self.assertEqual(plan.get("status"), "unsupported", plan)
        self.assertIs(plan.get("answerable", False), False, plan)
        self.assertIn(
            str(plan.get("reason", "")), ("unsupported_arithmetic",), plan
        )

    def test_pronoun_scope_unsupported(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(self.PRONOUN_Q, max_hops=1, max_searches=2)
        self.assertEqual(plan.get("status"), "unsupported", plan)
        self.assertEqual(plan.get("steps"), [], plan)


class ExecutionReceiptPlannerTests(OfflineTestCase):
    """Cycle6a TEST-ONLY planner receipt guards (offline, no benchmark reads)."""

    def test_credential_url_not_echoed(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        cred = "https://user:secret@example.com/foo"
        q = "Who designed %s?" % cred
        plan = plan_fn(q, max_hops=2, max_searches=2)
        self.assertEqual(plan.get("status"), "unsupported", plan)
        self.assertEqual(plan.get("steps"), [], plan)
        blob = str(plan)
        self.assertNotIn("user:secret", blob, plan)
        self.assertNotIn("secret@example", blob, plan)

    def test_control_chars_not_echoed(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        for q in ("Who designed Briar?\x00", "Who designed Briar\x1f?"):
            with self.subTest(q=repr(q)):
                plan = plan_fn(q, max_hops=1, max_searches=2)
                self.assertEqual(plan.get("status"), "unsupported", plan)
                blob = str(plan)
                self.assertNotIn("\x00", blob, plan)
                self.assertNotIn("\x1f", blob, plan)

    def test_aggregate_candidates_recorded(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(
            "Who designed the capital of the body orbited by Zori?",
            max_hops=3,
            max_searches=8,
        )
        self.assertEqual(plan.get("status"), "planned", plan)
        steps = plan.get("steps")
        self.assertEqual(len(steps), 3, plan)
        per_call = plan.get("max_candidates_per_call", plan.get("candidates_per_call", None))
        total = plan.get("max_candidates_total", plan.get("candidates_total", None))
        self.assertIsNotNone(per_call, plan)
        self.assertIsNotNone(total, plan)
        self.assertLessEqual(int(per_call), 5, plan)
        self.assertLessEqual(int(total), 40, plan)


class PlanBoundsTests(OfflineTestCase):
    QUERY_3HOP = "Who designed the capital of the body orbited by Runa?"
    FACETS_QUERY = "Who wrote Cobalt?; Who designed Briar?"
    SELF_LOOP_QUERY = "What is the capital of the capital of Porta?"

    def test_validate_mutations_reject(self):
        import copy

        plan_fn = getattr(answer_synth, "plan_research_query", None)
        validate_fn = getattr(answer_synth, "validate_research_plan", None)
        self.assertTrue(callable(plan_fn))
        self.assertTrue(callable(validate_fn))
        plan = plan_fn(self.QUERY_3HOP, max_hops=3, max_searches=4)
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertIs(validate_fn(plan), True, plan)
        # Dependency cycle: first step depends forward on terminal.
        tampered = copy.deepcopy(plan)
        tampered["steps"][0]["depends_on"] = ["s3"]
        self.assertIs(validate_fn(tampered), False, tampered)
        # Self-cycle.
        tampered = copy.deepcopy(plan)
        tampered["steps"][1]["depends_on"] = ["s2"]
        tampered["steps"][1]["depth"] = 2
        self.assertIs(validate_fn(tampered), False, tampered)
        # Forward reference.
        tampered = copy.deepcopy(plan)
        tampered["steps"][0]["depends_on"] = ["s2"]
        self.assertIs(validate_fn(tampered), False, tampered)
        # Bad template longer than 2000 chars.
        tampered = copy.deepcopy(plan)
        tampered["steps"][0]["query_template"] = "x" * 2001
        tampered["steps"][0]["grounding_template"] = "x" * 2001
        self.assertIs(validate_fn(tampered), False, tampered)
        # Binding longer than 512 chars.
        tampered = copy.deepcopy(plan)
        long_q = "What does %s orbit?" % ("A" * 600)
        tampered["steps"][0]["query_template"] = long_q
        tampered["steps"][0]["grounding_template"] = long_q
        self.assertIs(validate_fn(tampered), False, tampered)
        # Mismatched integer budgets.
        self.assertIs(validate_fn(plan, max_hops=2), False, plan)
        self.assertIs(validate_fn(plan, max_searches=2), False, plan)
        # External budget type strictness: bool/float/string reject.
        for bad_hops in (True, False, 3.0, "3"):
            with self.subTest(bad_hops=repr(bad_hops)):
                try:
                    result = validate_fn(plan, max_hops=bad_hops)
                except TypeError as exc:
                    self.fail("validate must not raise TypeError: %r" % (exc,))
                    continue
                self.assertIs(result, False, (plan, bad_hops))
        for bad_searches in (True, False, 4.0, "4"):
            with self.subTest(bad_searches=repr(bad_searches)):
                try:
                    result = validate_fn(plan, max_searches=bad_searches)
                except TypeError as exc:
                    self.fail("validate must not raise TypeError: %r" % (exc,))
                    continue
                self.assertIs(result, False, (plan, bad_searches))

    def test_validate_external_budget_bool_strict(self):
        # Even True == 1 in Python, strict bool must still reject.
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        validate_fn = getattr(answer_synth, "validate_research_plan", None)
        self.assertTrue(callable(plan_fn))
        self.assertTrue(callable(validate_fn))
        plan = plan_fn(self.FACETS_QUERY, max_hops=1, max_searches=2)
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertIs(validate_fn(plan), True, plan)
        for kwargs in (
            {"max_hops": True},
            {"max_hops": False},
            {"max_hops": 1.0},
            {"max_hops": "1"},
            {"max_searches": True},
            {"max_searches": False},
            {"max_searches": 2.0},
            {"max_searches": "2"},
        ):
            with self.subTest(kwargs=kwargs):
                try:
                    result = validate_fn(plan, **kwargs)
                except TypeError as exc:
                    self.fail("validate must not raise TypeError: %r" % (exc,))
                    continue
                self.assertIs(result, False, (plan, kwargs))

    def _load_public_tools(self, fake):
        import importlib.util
        import shutil
        import sys
        import tempfile
        import uuid
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent
        build_script = repo_root / "goat-web" / "scripts" / "build_plugin_bundle.py"
        build_root = repo_root.parent / "artifacts" / "wiring-build"
        build_root.mkdir(parents=True, exist_ok=True)
        spec = importlib.util.spec_from_file_location(
            "goat_v51_bundle_builder_planbounds", str(build_script)
        )
        self.assertIsNotNone(spec, "missing bundle builder spec")
        self.assertIsNotNone(spec.loader, "missing bundle builder loader")
        module_builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module_builder
        try:
            spec.loader.exec_module(module_builder)
        except Exception:
            sys.modules.pop(spec.name, None)
            raise
        tmp = tempfile.mkdtemp(prefix="goat-planbounds-", dir=str(build_root))
        self.addCleanup(shutil.rmtree, tmp, True)
        pkgdir = Path(tmp) / "hermes-goat-web"
        module_builder.build_bundle(repo_root, pkgdir)
        mod_name = "goat_answer_pkg_planbounds_" + uuid.uuid4().hex
        pspec = importlib.util.spec_from_file_location(
            mod_name, pkgdir / "__init__.py",
            submodule_search_locations=[str(pkgdir)],
        )
        self.assertIsNotNone(pspec, "missing fixture package spec")
        self.assertIsNotNone(pspec.loader, "missing fixture package loader")
        pkg = importlib.util.module_from_spec(pspec)
        sys.modules[mod_name] = pkg
        try:
            pspec.loader.exec_module(pkg)
        except Exception:
            sys.modules.pop(mod_name, None)
            raise
        self.addCleanup(
            lambda: [sys.modules.pop(n, None) for n in list(sys.modules) if n == mod_name or n.startswith(mod_name + ".")]
        )
        wiring = pkg.v3_wiring
        deps = wiring.WiringDependencies(
            search=fake, answer_search=fake, vertical_transports=None
        )

        class _Ctx:
            def __init__(self):
                self.tools = {}

            def register_tool(self, **kwargs):
                self.tools[kwargs["name"]] = kwargs

        ctx = _Ctx()
        pkg.register(ctx, deps=deps)
        return ctx.tools

    def test_three_hop_budget_exhaustion_before_calls(self):
        import json

        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        # Real planner emits the full bounded chain; public dispatch must
        # explicitly exhaust the budget before any retrieval call.
        for budgets in ({"max_hops": 2, "max_searches": 4}, {"max_hops": 3, "max_searches": 2}):
            with self.subTest(budgets=budgets):
                plan = plan_fn(self.QUERY_3HOP, max_hops=3, max_searches=4)
                self.assertEqual(plan.get("status"), "planned", plan)
                self.assertEqual(len(plan.get("steps", [])), 3, plan)
                calls = []

                def fake(query, *, max_results=5):
                    calls.append((query, max_results))
                    return {"ok": True, "results": []}

                tools = self._load_public_tools(fake)
                handler = tools["goat_answer"]["handler"]
                args = {"query": self.QUERY_3HOP, "research": True}
                args.update(budgets)
                payload = json.loads(handler(args))
                self.assertEqual(calls, [], payload)
                self.assertIs(payload.get("ok"), False, payload)
                self.assertEqual(
                    payload.get("error", {}).get("code"),
                    "INSUFFICIENT_EVIDENCE",
                    payload,
                )
                research = payload.get("metadata", {}).get("research", {})
                self.assertEqual(research.get("status"), "budget_exhausted", payload)
                self.assertNotIn("answer", payload, payload)

    def test_self_loop_repeated_query_stops(self):
        import json

        # Public real planner with no planner/classifier mocking; only the
        # search callable is faked. Self-loop source repeats the query.
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(self.SELF_LOOP_QUERY, max_hops=2, max_searches=4)
        self.assertEqual(plan.get("status"), "planned", plan)
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == "What is the capital of Porta?":
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Porta",
                            "url": "https://example.com/porta",
                            "extract": "Porta is the capital of Porta.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        tools = self._load_public_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.SELF_LOOP_QUERY,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertEqual(len(calls), 1, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertIn(
            research.get("status"), ("partial", "budget_exhausted", "abstained"), payload
        )
        self.assertIn(
            str(research.get("reason", "")), ("cycle", "repeated_query"), payload
        )


class TraceDepthPlanTests(OfflineTestCase):
    """REAL 4-facet-of-2-step planner shape (8 steps, depth 2, no mocks)."""

    FACETS_QUERY = "; ".join(
        "When was the inventor of %s born?" % s
        for s in ("Cobalt", "Briar", "Ferro", "Greso")
    )

    def test_four_facets_eight_steps_depth_two_real(self):
        plan_fn = getattr(answer_synth, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(self.FACETS_QUERY, max_hops=2, max_searches=8)
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "facets", plan)
        steps = plan.get("steps")
        self.assertIsInstance(steps, list, plan)
        self.assertEqual(len(steps), 8, plan)
        self.assertEqual(
            [s.get("id") for s in steps],
            ["s%d" % i for i in range(1, 9)],
            plan,
        )
        self.assertEqual(
            [s.get("depth") for s in steps], [1, 2, 1, 2, 1, 2, 1, 2], plan
        )
        for s in steps:
            self.assertLessEqual(len(s.get("query_template", "")), 2000, plan)
            self.assertLessEqual(len(s.get("grounding_template", "")), 2000, plan)
        validate_fn = getattr(answer_synth, "validate_research_plan", None)
        self.assertTrue(callable(validate_fn))
        self.assertIs(validate_fn(plan), True, plan)
        self.assertIs(validate_fn(plan, max_hops=2, max_searches=8), True, plan)
        terminals = [s for s in steps if s.get("emit") is True]
        self.assertEqual(len(terminals), 4, plan)
        self.assertEqual(
            [s.get("id") for s in terminals], ["s2", "s4", "s6", "s8"], plan
        )


# TESTS_ONLY_EXECUTION_READY
# TESTS_ONLY_BOUNDS_READY
# TESTS_ONLY_FINAL_ANCHORS_READY
if __name__ == "__main__":
    unittest.main()
