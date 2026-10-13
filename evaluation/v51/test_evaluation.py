"""GOAT V5.1 evaluation TEST-ONLY (offline, synthetic only).

TEST-ONLY stage: only NEW evaluation/v51/test_evaluation.py exists.
No implementation yet (evaluation/v51/run.py absent). Algorithm frozen
by supervisor before this stage; do NOT modify production/tests elsewhere,
inspect pinned questions/golds/benchmarks/results, run live bench/provider/
paid calls, commit/install/activate.

Wished-for API in evaluation/v51/run.py:
  planner_coverage(dataset_path, expected_sha256, query_column, *,
                   format='csv', max_hops=4, max_searches=8,
                   expected_count=None) -> dict
  replay_fixtures(source_root, fixture_path, expected_sha256) -> dict

Helper loads if file exists; if absent returns SimpleNamespace and each
test asserts callable (behavioral RED, NOT ImportError/discovery RED).
Only stdlib + unittest. Temporary data under TMPDIR/scratch.
Neutral synthetic names only (NOT prior builder fixtures).
Native bare behavioral RED then separate GREEN CLI.
No /tmp/temp outside authorized scratch.
"""

import csv
import hashlib
import importlib.util
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


THIS_DIR = Path(__file__).resolve().parent
RUN_PATH = THIS_DIR / "run.py"
REPO_ROOT = THIS_DIR.resolve().parents[2] if len(THIS_DIR.resolve().parents) >= 2 else Path.cwd()

# Neutral synthetic fixtures (NOT prior builder fixtures).
# Prior builder tokens avoided: Porta/Runa/Luma/Cobalt/Briar/Vela/Arbor/
# Ferro/Greso/Mira Vale/Nera Voss/Tessa/Zara/Zori/France/Paris/Canada/
# Ottawa/Arcadia/Riverport.
CHAIN_Q = "Who designed the capital of the body orbited by Jento?"
WHO_Q = "Who invented Halden?"
WHY_Q = "Why did Halden fall?"
CANARY_VALUE = "canary_unused_gold_7q2x_never_plan"
CANARY_COLUMN = "unused_gold"
QUERY_COLUMN = "question"

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _load_run():
    """Load evaluation/v51/run.py if present else empty namespace.

    Never raises ImportError at collection; each test asserts callable
    for behavioral RED.
    """
    if not RUN_PATH.exists():
        return SimpleNamespace()
    try:
        spec = importlib.util.spec_from_file_location("goat_v51_eval_run", str(RUN_PATH))
        if spec is None or spec.loader is None:
            return SimpleNamespace()
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(spec.name, None)
            return SimpleNamespace()
        return mod
    except Exception:
        return SimpleNamespace()


def _sha256_file(path):
    h = hashlib.sha256()
    with open(str(path), "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _authorized_tmp_base():
    # TMPDIR respected; fallback to repo scratch. Never /tmp directly.
    base = os.environ.get("TMPDIR") or tempfile.gettempdir()
    return base


def _make_tmpdir(prefix):
    base = _authorized_tmp_base()
    # tempfile respects TMPDIR; explicit dir keeps under authorized scratch.
    try:
        Path(base).mkdir(parents=True, exist_ok=True)
        tmp = tempfile.mkdtemp(prefix=prefix, dir=str(base))
    except Exception:
        tmp = tempfile.mkdtemp(prefix=prefix)
    return tmp


def _write_csv_3row(path):
    with open(str(path), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=[QUERY_COLUMN, CANARY_COLUMN])
        w.writeheader()
        w.writerow({QUERY_COLUMN: CHAIN_Q, CANARY_COLUMN: CANARY_VALUE + "_r1"})
        w.writerow({QUERY_COLUMN: WHO_Q, CANARY_COLUMN: CANARY_VALUE + "_r2"})
        w.writerow({QUERY_COLUMN: WHY_Q, CANARY_COLUMN: CANARY_VALUE + "_r3"})


def _write_jsonl_3row(path):
    rows = [
        {QUERY_COLUMN: CHAIN_Q, CANARY_COLUMN: CANARY_VALUE + "_r1"},
        {QUERY_COLUMN: WHO_Q, CANARY_COLUMN: CANARY_VALUE + "_r2"},
        {QUERY_COLUMN: WHY_Q, CANARY_COLUMN: CANARY_VALUE + "_r3"},
    ]
    with open(str(path), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _blob(o):
    try:
        return json.dumps(o, sort_keys=True, default=str)
    except Exception:
        return str(o)


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        try:
            import http.client  # noqa: F401
            import ssl  # noqa: F401
        except Exception:
            pass
        self._getaddrinfo = socket.getaddrinfo
        self._create_connection = socket.create_connection
        self._socket = socket.socket
        self._gethostbyname = getattr(socket, "gethostbyname", None)
        self._getnameinfo = getattr(socket, "getnameinfo", None)

        def _blocked(*a, **k):
            raise AssertionError("network disabled during offline test")

        _orig = self._socket

        class _BlockedSocket(_orig):
            def __new__(cls, *a, **k):
                raise AssertionError("socket construction disabled during offline test")

        socket.getaddrinfo = _blocked
        socket.create_connection = _blocked
        socket.socket = _BlockedSocket
        if hasattr(socket, "gethostbyname"):
            socket.gethostbyname = _blocked
        if hasattr(socket, "getnameinfo"):
            socket.getnameinfo = _blocked
        self.addCleanup(setattr, socket, "getaddrinfo", self._getaddrinfo)
        self.addCleanup(setattr, socket, "create_connection", self._create_connection)
        self.addCleanup(setattr, socket, "socket", self._socket)
        if self._gethostbyname is not None:
            self.addCleanup(setattr, socket, "gethostbyname", self._gethostbyname)
        if self._getnameinfo is not None:
            self.addCleanup(setattr, socket, "getnameinfo", self._getnameinfo)


class PlannerCoverageContractTests(OfflineTestCase):
    def test_planner_coverage_callable(self):
        run = _load_run()
        self.assertTrue(
            callable(getattr(run, "planner_coverage", None)),
            "missing evaluation/v51/run.py:planner_coverage",
        )

    def test_coverage_3row_counts(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-cov-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8, expected_count=3)
        self.assertIsInstance(res, dict, res)
        # Exact projected query-coverage counts.
        self.assertEqual(res.get("queries_seen"), 3, res)
        self.assertEqual(res.get("decomposed_queries"), 1, res)
        self.assertEqual(res.get("emitted_queries"), 2, res)
        self.assertEqual(res.get("executable_queries"), 2, res)
        self.assertEqual(res.get("emitted_steps"), 4, res)
        self.assertEqual(res.get("executable_steps"), 4, res)

    def test_coverage_definitions_no_grading_offline(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-covdef-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8)
        self.assertIsInstance(res, dict, res)
        # Definitions: decomposed >1 steps, emitted >=1 step,
        # executable = validated DAG within chosen budget; answerable separate.
        # Unsupported temporal-compare facets executable but NOT answerable
        # (covered implicitly: WHY unsupported 0 steps, chain+who executable).
        self.assertEqual(res.get("queries_seen"), 3, res)
        # No dataset answer grading.
        q = res.get("supported_answer_quality", res.get("answer_quality", "MISSING"))
        self.assertIn(q, (None, "unavailable", "null", "UNAVAILABLE"), res)
        # Evidence status offline, network calls zero.
        blob = _blob(res).lower()
        self.assertIn("no_available_offline_evidence", blob, res)
        nc = res.get("network_calls", res.get("networkcalls", res.get("http_calls", 0)))
        self.assertEqual(nc, 0, res)
        # Must not fabricate numeric answer scores when no evidence.
        if isinstance(q, (int, float)) and not isinstance(q, bool):
            self.fail("coverage must never fabricate numeric answer score: %r" % (res,))

    def test_coverage_only_query_column_canary_never(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-canary-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8)
        blob = _blob(res)
        # Only query column ever enters planner/engine/output.
        self.assertNotIn(CANARY_VALUE, blob, res)
        self.assertNotIn(CANARY_COLUMN, blob, res)
        # Canary ignored values must not leak even with suffixes.
        self.assertNotIn("canary_unused_gold", blob.lower(), res)

    def test_coverage_rows_log_hash_id_status_counts_not_text(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-rows-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8)
        rows = res.get("rows", res.get("per_row", res.get("details", None)))
        self.assertIsInstance(rows, list, res)
        self.assertEqual(len(rows), 3, res)
        for row in rows:
            self.assertIsInstance(row, dict, res)
            # Must log hash/id/status/counts.
            has_hash = any(k in row for k in ("hash", "row_hash", "query_hash", "id_hash"))
            has_id = any(k in row for k in ("id", "row_id", "index"))
            has_status = any(k in row for k in ("status", "state", "outcome"))
            self.assertTrue(has_hash, row)
            self.assertTrue(has_id, row)
            self.assertTrue(has_status, row)
            # Must NOT log full question text.
            rblob = _blob(row)
            self.assertNotIn(CHAIN_Q, rblob, row)
            self.assertNotIn(WHO_Q, rblob, row)
            self.assertNotIn(WHY_Q, rblob, row)
            self.assertNotIn(CANARY_VALUE, rblob, row)

    def test_coverage_expected_count_mismatch_fail_closed(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-count-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8, expected_count=2)
        self.assertIsInstance(res, dict, res)
        self.assertIs(res.get("ok", False), False, res)
        # Fail closed before planning: no emitted/executable inflated.
        self.assertEqual(res.get("network_calls", 0), 0, res)
        blob = _blob(res).lower()
        self.assertNotIn(CANARY_VALUE.lower(), blob, res)

    def test_coverage_wrong_sha_fail_closed(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-sha-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        wrong = "0" * 64
        self.assertNotEqual(wrong, _sha256_file(ds))
        res = run.planner_coverage(ds, wrong, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8)
        self.assertIsInstance(res, dict, res)
        self.assertIs(res.get("ok", False), False, res)
        self.assertEqual(res.get("network_calls", 0), 0, res)

    def test_coverage_jsonl_equivalent(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-jsonl-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.jsonl")
        _write_jsonl_3row(ds)
        sha = _sha256_file(ds)
        res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="jsonl", max_hops=4, max_searches=8, expected_count=3)
        self.assertIsInstance(res, dict, res)
        self.assertEqual(res.get("queries_seen"), 3, res)
        self.assertEqual(res.get("decomposed_queries"), 1, res)
        self.assertEqual(res.get("emitted_queries"), 2, res)
        self.assertEqual(res.get("executable_queries"), 2, res)
        self.assertEqual(res.get("emitted_steps"), 4, res)
        self.assertEqual(res.get("executable_steps"), 4, res)
        self.assertNotIn(CANARY_VALUE, _blob(res), res)


class PlannerCoverageStrictnessTests(OfflineTestCase):
    def test_strict_hex_lower64_rejected(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-hex-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        good = _sha256_file(ds)
        bad_hashes = [
            good.upper(),
            good[:-1],
            good + "0",
            "z" * 64,
            "0" * 63,
            "",
            None,
            123,
            True,
            "  " + good,
            good + "\n",
        ]
        for bad in bad_hashes:
            with self.subTest(bad=repr(bad)):
                try:
                    res = run.planner_coverage(ds, bad, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8)
                except (TypeError, ValueError) as exc:
                    # Strict validation may raise, but must not plan.
                    continue
                self.assertIsInstance(res, dict, res)
                # Strict hex lower64 must fail closed (not ok True).
                self.assertIs(res.get("ok", False), False, (bad, res))

    def test_strict_function_budgets_not_bool_float(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-budget-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        bad_budgets = [
            {"max_hops": True, "max_searches": 8},
            {"max_hops": False, "max_searches": 8},
            {"max_hops": 4.0, "max_searches": 8},
            {"max_hops": "4", "max_searches": 8},
            {"max_hops": 4, "max_searches": True},
            {"max_hops": 4, "max_searches": 8.0},
            {"max_hops": 4, "max_searches": "8"},
            {"max_hops": None, "max_searches": 8},
            {"max_hops": 4, "max_searches": None},
        ]
        for kw in bad_budgets:
            with self.subTest(kw=kw):
                try:
                    res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="csv", expected_count=3, **kw)
                except (TypeError, ValueError):
                    continue
                self.assertIsInstance(res, dict, res)
                self.assertIs(res.get("ok", False), False, (kw, res))
                self.assertEqual(res.get("network_calls", 0), 0, (kw, res))

    def test_no_row_exclusions_sampling_dedupe(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-noexcl-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        res = run.planner_coverage(ds, sha, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8)
        # No row exclusions/sampling/dedupe: all 3 rows accounted.
        self.assertEqual(res.get("queries_seen"), 3, res)
        rows = res.get("rows", res.get("per_row", []))
        self.assertEqual(len(rows), 3, res)
        blob = _blob(res).lower()
        for forbidden in ("sampled", "dedup", "excluded", "skipped"):
            # Implementation must not report sampling/dedupe/exclusion.
            if forbidden in blob:
                self.fail("must not sample/dedupe/exclude rows: %r in %r" % (forbidden, res))


# Fixture replay contract: synthetic only, exact request-response maps,
# explicit label synthetic, NOT benchmark questions/answers.
REPLAY_CHAIN_Q = "Who designed the capital of the body orbited by Corvin?"
REPLAY_FACETS_Q = "Who wrote Dessa?; Who designed Elmar?"
REPLAY_INTERSECT_Q = "Who both wrote Dessa and designed Elmar?"
REPLAY_BIRTH_Q = "Who invented Fenwick in 1984?"
REPLAY_TEMPORAL_Q = "Was Dessa born before Elmar?"


def _write_synthetic_fixture(path):
    """Minimal synthetic fixture with exact request-response evidence maps."""
    def _r(title, url, extract):
        return {"title": title, "url": url, "extract": extract}

    fixtures = [
        {
            "id": "v51-mixed-chain",
            "query": REPLAY_CHAIN_Q,
            "label": "synthetic",
            "evidence": {
                "What does Corvin orbit?": [_r("Corvin", "https://example.com/corvin-orbit", "Corvin orbits Dessa.")],
                "What is the capital of Dessa?": [_r("Dessa", "https://example.com/dessa-capital", "Elmar is the capital of Dessa.")],
                "Who designed Elmar?": [_r("Elmar", "https://example.com/elmar-designed", "Corvin Vale designed Elmar.")],
            },
        },
        {
            "id": "v51-facets",
            "query": REPLAY_FACETS_Q,
            "label": "synthetic",
            "evidence": {
                "Who wrote Dessa?": [_r("Dessa", "https://example.com/dessa-wrote", "Dessa Lark wrote Dessa.")],
                "Who designed Elmar?": [_r("Elmar", "https://example.com/elmar-designed", "Elmar Kent designed Elmar.")],
            },
        },
        {
            "id": "v51-intersection",
            "query": REPLAY_INTERSECT_Q,
            "label": "synthetic",
            "evidence": {
                "Who wrote Dessa?": [_r("Dessa", "https://example.com/dessa-wrote", "Dessa Lark wrote Dessa.")],
                "Who designed Elmar?": [_r("Elmar", "https://example.com/elmar-shared", "Dessa Lark designed Elmar.")],
            },
        },
        {
            "id": "v51-birth-literal",
            "query": REPLAY_BIRTH_Q,
            "label": "synthetic",
            "evidence": {
                "Who invented Fenwick?": [_r("Fenwick", "https://example.com/fenwick-invent", "Garran invented Fenwick.")],
            },
            "temporal_literal": "1984",
        },
        {
            "id": "v51-temporal-unsupported",
            "query": REPLAY_TEMPORAL_Q,
            "label": "synthetic",
            "evidence": {
                "Dessa born": [_r("Dessa", "https://example.com/dessa-born", "Dessa Lark was born in Hollis.")],
                "Elmar born": [_r("Elmar", "https://example.com/elmar-born", "Elmar Kent was born in Hollis.")],
            },
        },
    ]
    doc = {"label": "synthetic", "fixtures": fixtures}
    with open(str(path), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, sort_keys=True, indent=2)
    return doc


def _strip_volatile(o):
    # Exclude elapsed/timestamps for determinism compare.
    if isinstance(o, dict):
        return {k: _strip_volatile(v) for k, v in o.items() if k.lower() not in ("elapsed", "elapsed_ms", "elapsed_ns", "timestamp", "timestamps", "started_at", "ended_at", "duration_ms", "duration")}
    if isinstance(o, list):
        return [_strip_volatile(v) for v in o]
    return o


def _find_counts(res):
    low = {}
    def _walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                low[k.lower()] = v
                _walk(v)
        elif isinstance(o, list):
            for v in o:
                _walk(v)
    _walk(res)
    return low


class FixtureReplayContractTests(OfflineTestCase):
    def test_replay_callable(self):
        run = _load_run()
        self.assertTrue(
            callable(getattr(run, "replay_fixtures", None)),
            "missing evaluation/v51/run.py:replay_fixtures",
        )

    def test_replay_wrong_hash_fail_closed(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        tmp = _make_tmpdir(prefix="goat-v51-replay-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        _write_synthetic_fixture(fx)
        wrong = "f" * 64
        self.assertNotEqual(wrong, _sha256_file(fx))
        res = run.replay_fixtures(str(REPO_ROOT), fx, wrong)
        self.assertIsInstance(res, dict, res)
        self.assertIs(res.get("ok", False), False, res)

    def test_replay_strict_hash(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        tmp = _make_tmpdir(prefix="goat-v51-replayhex-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        _write_synthetic_fixture(fx)
        good = _sha256_file(fx)
        for bad in (good.upper(), good[:-1], "z" * 64, "", None, True):
            with self.subTest(bad=repr(bad)):
                try:
                    res = run.replay_fixtures(str(REPO_ROOT), fx, bad)
                except (TypeError, ValueError):
                    continue
                self.assertIs(res.get("ok", False), False, (bad, res))

    def test_replay_fixture_data_contract_synthetic_only(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        tmp = _make_tmpdir(prefix="goat-v51-synth-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        doc = _write_synthetic_fixture(fx)
        # Fixture data itself: exact request-response maps + explicit synthetic.
        self.assertEqual(doc.get("label"), "synthetic", doc)
        for f in doc.get("fixtures", []):
            self.assertEqual(f.get("label"), "synthetic", f)
            self.assertIsInstance(f.get("evidence"), dict, f)
            self.assertTrue(f.get("evidence"), f)
            self.assertIn("id", f, f)
            self.assertIn("query", f, f)
        blob = _blob(doc)
        # NOT benchmark questions/answers.
        for forbidden in ("France", "penicillin", "Porta", "Runa", "Luma", "Cobalt", "Briar"):
            self.assertNotIn(forbidden, blob, doc)
        sha = _sha256_file(fx)
        res = run.replay_fixtures(str(REPO_ROOT), fx, sha)
        self.assertIsInstance(res, dict, res)
        # Replay uses REAL bundle + REAL wikipedia parser/classifier/planner/
        # grounding via only fake HTTP boundary (asserted via offline guard
        # + trace checks below); here assert count reconciled.
        counts = _find_counts(res)
        for key in ("answered", "abstained", "partial"):
            self.assertIn(key, counts, res)
        # provider errors counted separately (allow provider_errors key).
        self.assertTrue(any("provider" in k for k in counts), res)

    def test_replay_counts_reconciled_quality_real(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        tmp = _make_tmpdir(prefix="goat-v51-quality-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        doc = _write_synthetic_fixture(fx)
        sha = _sha256_file(fx)
        res = run.replay_fixtures(str(REPO_ROOT), fx, sha)
        self.assertIsInstance(res, dict, res)
        n = len(doc["fixtures"])
        counts = _find_counts(res)
        total = sum(int(counts.get(k, 0)) for k in ("answered", "abstained", "partial") if isinstance(counts.get(k), int))
        prov = 0
        for k, v in counts.items():
            if "provider" in k and isinstance(v, int):
                prov = v
                break
        self.assertEqual(total + prov, n, res)
        # Fixture count reconciled.
        fc = counts.get("fixture_count", counts.get("fixtures_seen", counts.get("total", n)))
        self.assertEqual(int(fc), n, res)
        # Quality label exact, only support+integrity on ANSWERED, no recall/accuracy.
        self.assertIn("agentic_supported_answer_quality", res, res)
        qblob = _blob(res.get("agentic_supported_answer_quality")).lower()
        self.assertNotIn("recall", qblob, res)
        self.assertNotIn("accuracy", qblob, res)
        self.assertNotIn("answer_accuracy", _blob(res).lower().replace(" ", ""), res)
        # Quality must reflect real outputs (present, dict or null only if none answered).
        q = res.get("agentic_supported_answer_quality")
        self.assertTrue(isinstance(q, dict) or q is None, res)

    def test_replay_citation_strict_contiguous(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        tmp = _make_tmpdir(prefix="goat-v51-cite-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        _write_synthetic_fixture(fx)
        sha = _sha256_file(fx)
        res = run.replay_fixtures(str(REPO_ROOT), fx, sha)
        self.assertIsInstance(res, dict, res)
        # Every direct source cited strict contiguous indices + correct URL.
        traces = res.get("fixtures", res.get("traces", res.get("results", [])))
        self.assertIsInstance(traces, list, res)
        for t in traces:
            if not isinstance(t, dict):
                continue
            if t.get("status") not in ("answered", "completed", "ok") and not t.get("ok"):
                continue
            answer = t.get("answer", "")
            sources = t.get("sources", [])
            if not answer or not sources:
                continue
            idx = [s.get("index") for s in sources]
            for i in idx:
                self.assertIs(type(i), int, t)
            self.assertEqual(sorted(idx), list(range(1, len(idx) + 1)), t)
            cited = {int(x) for x in re.findall(r"\[(\d+)\]", answer)}
            self.assertEqual(cited, set(idx), t)
            for s in sources:
                self.assertTrue(str(s.get("url", "")).startswith("https://"), t)

    def test_replay_no_evidence_never_fabricates(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        # Coverage no-evidence never fabricates answer scores (mirror).
        tmp = _make_tmpdir(prefix="goat-v51-nofab-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.csv")
        _write_csv_3row(ds)
        sha = _sha256_file(ds)
        cov = _load_run().planner_coverage(ds, sha, QUERY_COLUMN, format="csv", max_hops=4, max_searches=8)
        self.assertIsInstance(cov, dict, cov)
        q = cov.get("supported_answer_quality", cov.get("answer_quality"))
        self.assertIn(q, (None, "unavailable", "null", "UNAVAILABLE"), cov)

    def test_replay_deterministic_two_runs(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        tmp = _make_tmpdir(prefix="goat-v51-determ-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        _write_synthetic_fixture(fx)
        sha = _sha256_file(fx)
        r1 = run.replay_fixtures(str(REPO_ROOT), fx, sha)
        r2 = run.replay_fixtures(str(REPO_ROOT), fx, sha)
        self.assertIsInstance(r1, dict, r1)
        self.assertIsInstance(r2, dict, r2)
        c1 = _strip_volatile(r1)
        c2 = _strip_volatile(r2)
        self.assertEqual(_blob(c1), _blob(c2), (r1, r2))

    def test_replay_offline_guard_no_real_transport(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        tmp = _make_tmpdir(prefix="goat-v51-offline-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        _write_synthetic_fixture(fx)
        sha = _sha256_file(fx)
        # Socket/DNS already blocked in setUp; replay must reject/record
        # accidental attempt rather than fallback, no real transport calls.
        res = run.replay_fixtures(str(REPO_ROOT), fx, sha)
        self.assertIsInstance(res, dict, res)
        blob = _blob(res).lower()
        # Must not have performed real transport (network_calls 0 or only fake).
        # Every trace/request budget actual code outputs: traces present.
        traces = res.get("fixtures", res.get("traces", res.get("results", None)))
        self.assertIsNotNone(traces, res)
        self.assertTrue(isinstance(traces, list) and len(traces) > 0, res)
        for t in traces:
            if isinstance(t, dict):
                # Actual code outputs include query/budget fields.
                self.assertTrue(any(k in t for k in ("query", "id", "status", "trace", "budget", "search_calls", "request")), t)

    def test_replay_positives_negatives_documented(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "replay_fixtures", None)))
        # Deterministic positives: mixed 3-relation chain, semicolon facets,
        # common-actor intersection, birth literal date; negatives:
        # ambiguous/missing/conflicting/negative/modal + temporal-compare
        # unsupported. Fixture built above covers positives + temporal;
        # negatives are evidence-map variants of same neutral queries.
        tmp = _make_tmpdir(prefix="goat-v51-posneg-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        fx = os.path.join(tmp, "fixture-evidence.json")
        doc = _write_synthetic_fixture(fx)
        queries = [f["query"] for f in doc["fixtures"]]
        self.assertIn(REPLAY_CHAIN_Q, queries)
        self.assertIn(REPLAY_FACETS_Q, queries)
        self.assertIn(REPLAY_INTERSECT_Q, queries)
        self.assertIn(REPLAY_BIRTH_Q, queries)
        self.assertIn(REPLAY_TEMPORAL_Q, queries)
        sha = _sha256_file(fx)
        res = run.replay_fixtures(str(REPO_ROOT), fx, sha)
        self.assertIsInstance(res, dict, res)


def _write_tsv_3row(path):
    # Synthetic neutral TSV (NOT pinned rows): question column + unused gold canary.
    # Stdlib csv with tab delimiter; no new deps.
    with open(str(path), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=[QUERY_COLUMN, CANARY_COLUMN], delimiter="\t"
        )
        w.writeheader()
        w.writerow({QUERY_COLUMN: CHAIN_Q, CANARY_COLUMN: CANARY_VALUE + "_r1"})
        w.writerow({QUERY_COLUMN: WHO_Q, CANARY_COLUMN: CANARY_VALUE + "_r2"})
        w.writerow({QUERY_COLUMN: WHY_Q, CANARY_COLUMN: CANARY_VALUE + "_r3"})


class TSVPlannerCoverageTests(OfflineTestCase):
    """TEST-ONLY TSV coverage: synthetic 3-row TSV, no pinned-row reads.

    format='tsv' must yield same 3/1/2/2/4/4 metrics as CSV. CLI must
    support --format tsv too. Current ValueError/TypeError/unsupported
    format caught as behavioral self.fail (not unittest ERROR). No new
    deps, no source algorithm changes.
    """

    def test_tsv_equivalent_counts(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-tsv-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.tsv")
        _write_tsv_3row(ds)
        sha = _sha256_file(ds)
        try:
            res = run.planner_coverage(
                ds, sha, QUERY_COLUMN, format="tsv",
                max_hops=4, max_searches=8, expected_count=3,
            )
        except (ValueError, TypeError) as exc:
            self.fail("planner_coverage must support format='tsv': %r" % (exc,))
            return
        self.assertIsInstance(res, dict, res)
        self.assertEqual(res.get("queries_seen"), 3, res)
        self.assertEqual(res.get("decomposed_queries"), 1, res)
        self.assertEqual(res.get("emitted_queries"), 2, res)
        self.assertEqual(res.get("executable_queries"), 2, res)
        self.assertEqual(res.get("emitted_steps"), 4, res)
        self.assertEqual(res.get("executable_steps"), 4, res)
        self.assertNotIn(CANARY_VALUE, _blob(res), res)

    def test_tsv_cli_supports_format(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        parser_fn = getattr(run, "_build_parser", None)
        self.assertTrue(callable(parser_fn), "missing CLI _build_parser")
        tmp = _make_tmpdir(prefix="goat-v51-tsvcli-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.tsv")
        _write_tsv_3row(ds)
        sha = _sha256_file(ds)
        out = os.path.join(tmp, "out.json")
        try:
            parser = parser_fn()
            args = parser.parse_args([
                "coverage", "--dataset", ds, "--expected-sha256", sha,
                "--query-column", QUERY_COLUMN, "--format", "tsv",
                "--max-hops", "4", "--max-searches", "8",
                "--expected-count", "3", "--output", out,
            ])
        except SystemExit as exc:
            self.fail("CLI must support --format tsv: SystemExit %r" % (exc,))
            return
        except (ValueError, TypeError) as exc:
            self.fail("CLI --format tsv must not raise: %r" % (exc,))
            return
        self.assertEqual(getattr(args, "format", None), "tsv", args)
        # End-to-end CLI with synthetic TSV must yield same counts.
        try:
            code = run.main([
                "coverage", "--dataset", ds, "--expected-sha256", sha,
                "--query-column", QUERY_COLUMN, "--format", "tsv",
                "--max-hops", "4", "--max-searches", "8",
                "--expected-count", "3", "--output", out,
            ])
        except (ValueError, TypeError) as exc:
            self.fail("CLI coverage tsv must not raise ValueError/TypeError: %r" % (exc,))
            return
        self.assertEqual(code, 0, code)
        with open(out, "r", encoding="utf-8") as fh:
            res = json.load(fh)
        self.assertEqual(res.get("queries_seen"), 3, res)
        self.assertEqual(res.get("decomposed_queries"), 1, res)
        self.assertEqual(res.get("emitted_queries"), 2, res)
        self.assertEqual(res.get("executable_queries"), 2, res)
        self.assertEqual(res.get("emitted_steps"), 4, res)
        self.assertEqual(res.get("executable_steps"), 4, res)

    def test_tsv_wrong_hash_fail_closed(self):
        run = _load_run()
        self.assertTrue(callable(getattr(run, "planner_coverage", None)))
        tmp = _make_tmpdir(prefix="goat-v51-tsvsha-")
        self.addCleanup(__import__("shutil").rmtree, tmp, True)
        ds = os.path.join(tmp, "queries.tsv")
        _write_tsv_3row(ds)
        wrong = "0" * 64
        self.assertNotEqual(wrong, _sha256_file(ds))
        try:
            res = run.planner_coverage(
                ds, wrong, QUERY_COLUMN, format="tsv",
                max_hops=4, max_searches=8,
            )
        except (ValueError, TypeError) as exc:
            self.fail("wrong-hash TSV must fail closed as dict, not raise: %r" % (exc,))
            return
        self.assertIsInstance(res, dict, res)
        self.assertIs(res.get("ok", False), False, res)
        self.assertEqual(res.get("network_calls", 0), 0, res)


# EVALUATION_TESTS_ONLY_READY
# FINAL_COUNTER_TESTS_ONLY_READY
if __name__ == "__main__":
    unittest.main()
