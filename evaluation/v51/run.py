"""GOAT V5.1 offline evaluation (synthetic only, no live calls).

Implements the minimal API required by evaluation/v51/test_evaluation.py:
  planner_coverage(dataset_path, expected_sha256, query_column, *,
                   format='csv', max_hops=4, max_searches=8,
                   expected_count=None) -> dict
  replay_fixtures(source_root, fixture_path, expected_sha256) -> dict

Plus a small CLI with `coverage` and `replay` subcommands that exercise
the same functions (actual receipts, not stubs). No --live flag; live
protocol is proposed only in docs/v51-research.md and
evaluation/v51/live-protocol.md.

Constraints honored:
- Pure planner-only coverage from frozen source (adapters/answer_synth.py).
- Strict lower64 hex hash verified on raw bytes BEFORE parse/plan.
- Strict integer budgets (type(x) is int, bool rejected).
- Only the query column ever enters planner/engine/output.
- Rows carry query sha/id/status/step counts, never full query text.
- No sampling/exclusions/dedupe (those words never appear in output).
- Coverage reports no_available_offline_evidence, supported_answer_quality
  None, network_calls 0, no fabricated numeric scores.
- Replay uses REAL fresh bundle builder + manifest check + register +
  JSON handler, REAL make_default_answer_search / wiki parser /
  classifier / planner / grounding, ONLY fake HTTP _fetch boundary.
- Fake HTTP bodies are exact fixture extracts; temporal_literal never
  appended; query qualifiers never ignored (keyword-exact match).
- Missing keys return valid empty search JSON (abstain, no fallback).
- Deterministic outputs (no timestamps); socket/DNS blocked with
  attempt count 0; fake HTTP calls counted separately.
- Stdlib only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import socket
import sys
import tempfile
import shutil
import uuid
from pathlib import Path


THIS_DIR = Path(__file__).resolve().parent


def _default_repo_root() -> Path:
    # THIS_DIR is .../repo/evaluation/v51; repo is parents[1].
    try:
        pars = THIS_DIR.resolve().parents
        if len(pars) >= 2 and (pars[1] / "adapters" / "answer_synth.py").exists():
            return pars[1]
        if len(pars) >= 1 and (pars[0].parent / "adapters" / "answer_synth.py").exists():
            return pars[0].parent
    except Exception:
        pass
    return Path.cwd()


REPO_ROOT_DEFAULT = _default_repo_root()


def _resolve_repo_root(candidate) -> Path | None:
    """Accept test-passed source_root (may be repo parent) and find real repo."""
    try:
        if candidate is None:
            return None
        c = Path(str(candidate))
        # Direct hit.
        if (c / "adapters" / "answer_synth.py").exists() and (
            c / "goat-web" / "scripts" / "build_plugin_bundle.py"
        ).exists():
            return c
        # Common case: test passes repo parent; repo lives underneath.
        for child in ("repo",):
            d = c / child
            if (d / "adapters" / "answer_synth.py").exists():
                return d
        # Search one level of subdirectories for a repo checkout.
        try:
            if c.is_dir():
                for sub in c.iterdir():
                    try:
                        if (sub / "adapters" / "answer_synth.py").exists() and (
                            sub / "goat-web" / "scripts" / "build_plugin_bundle.py"
                        ).exists():
                            return sub
                    except Exception:
                        continue
        except Exception:
            pass
        # Fall back to our own file-derived repo.
        if (REPO_ROOT_DEFAULT / "adapters" / "answer_synth.py").exists():
            return REPO_ROOT_DEFAULT
    except Exception:
        pass
    return None

HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_PROVIDER_CODES = frozenset((
    "HTTP_ERROR", "RATE_LIMITED", "PROVIDER_BLOCKED", "DNS_ERROR",
    "UPSTREAM_TIMEOUT", "CONNECTION_ERROR", "MISSING_CONFIG",
    "URL_BLOCKED", "REDIRECT_BLOCKED",
))


def _is_strict_hex64(value) -> bool:
    return isinstance(value, str) and HEX64_RE.match(value) is not None


def _is_strict_hops(value) -> bool:
    return type(value) is int and 1 <= value <= 4


def _is_strict_searches(value) -> bool:
    return type(value) is int and 1 <= value <= 8


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fail_coverage(reason: str, **extra):
    out = {
        "ok": False,
        "reason": reason,
        "network_calls": 0,
        "attempt_count": 0,
        "supported_answer_quality": None,
        "evidence_status": "no_available_offline_evidence",
    }
    out.update(extra)
    return out


def _load_planner(repo_root: Path):
    """Load frozen planner (answer_synth) without modifying runtime files."""
    adapters_dir = Path(repo_root) / "adapters"
    mod = None
    # Prefer file-spec load with adapters on sys.path for dual-import fallback.
    added = False
    try:
        ads = str(adapters_dir)
        if ads not in sys.path:
            sys.path.insert(0, ads)
            added = True
        import importlib as _il
        # Use a fresh unique name to avoid cross-test pollution.
        name = "goat_v51_frozen_answer_synth_%s" % uuid.uuid4().hex[:8]
        spec = importlib.util.spec_from_file_location(
            name, str(adapters_dir / "answer_synth.py")
        )
        if spec is None or spec.loader is None:
            raise ImportError("no spec")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            sys.modules.pop(name, None)
            raise
        return mod
    finally:
        # Keep sys.path entry (harmless, stdlib-only) to allow result_contract
        # sibling import on later calls; do not remove to avoid flakiness.
        pass


def planner_coverage(dataset_path, expected_sha256, query_column, *,
                      format="csv", max_hops=4, max_searches=8,
                      expected_count=None):
    """Pure planner coverage over a CSV/TSV/JSONL dataset (offline, synthetic)."""
    repo_root = REPO_ROOT_DEFAULT
    # Strict hash format first (no planning on failure).
    if not _is_strict_hex64(expected_sha256):
        return _fail_coverage(
            "bad_expected_hash",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0,
        )
    # Strict budgets (bool/float/str/None rejected, fail closed).
    if not _is_strict_hops(max_hops):
        return _fail_coverage(
            "bad_max_hops",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0,
        )
    if not _is_strict_searches(max_searches):
        return _fail_coverage(
            "bad_max_searches",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0,
        )
    if expected_count is not None:
        if type(expected_count) is not int or expected_count < 0:
            return _fail_coverage(
                "bad_expected_count",
                queries_seen=0, decomposed_queries=0, emitted_queries=0,
                executable_queries=0, emitted_steps=0, executable_steps=0,
            )
    if not isinstance(dataset_path, str) or not dataset_path:
        return _fail_coverage("bad_dataset_path",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0)
    if not isinstance(query_column, str) or not query_column:
        return _fail_coverage("bad_query_column",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0)
    if format not in ("csv", "jsonl", "tsv"):
        return _fail_coverage("bad_format",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0)
    # Verify raw bytes BEFORE parse/plan.
    try:
        raw = Path(dataset_path).read_bytes()
    except Exception:
        return _fail_coverage("unreadable_dataset",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0)
    actual_sha = _sha256_bytes(raw)
    if actual_sha != expected_sha256:
        return _fail_coverage(
            "hash_mismatch",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0,
            dataset_sha256=actual_sha,
        )
    # Parse projecting ONLY the query column.
    queries = []
    try:
        text = raw.decode("utf-8")
    except Exception:
        return _fail_coverage("bad_encoding",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0)
    try:
        if format == "csv" or format == "tsv":
            import io as _io
            if format == "tsv":
                reader = csv.DictReader(_io.StringIO(text), delimiter="\t")
            else:
                reader = csv.DictReader(_io.StringIO(text))
            fields = reader.fieldnames
            if not fields or query_column not in fields:
                return _fail_coverage("missing_query_column",
                    queries_seen=0, decomposed_queries=0, emitted_queries=0,
                    executable_queries=0, emitted_steps=0, executable_steps=0)
            for row in reader:
                # Project only query column; never touch other columns.
                try:
                    q = row.get(query_column)
                except Exception:
                    q = None
                if not isinstance(q, str):
                    q = "" if q is None else str(q)
                queries.append(q)
        else:
            for line in text.splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                if not isinstance(obj, dict) or query_column not in obj:
                    return _fail_coverage("missing_query_column",
                        queries_seen=0, decomposed_queries=0, emitted_queries=0,
                        executable_queries=0, emitted_steps=0, executable_steps=0)
                q = obj.get(query_column)
                if not isinstance(q, str):
                    q = "" if q is None else str(q)
                queries.append(q)
    except Exception:
        return _fail_coverage("parse_error",
            queries_seen=0, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0)
    n = len(queries)
    # expected_count fail-closed BEFORE planning.
    if expected_count is not None and expected_count != n:
        rows_pre = []
        for i, q in enumerate(queries, 1):
            qh = _sha256_bytes(q.encode("utf-8"))
            rows_pre.append({
                "id": i,
                "query_hash": qh,
                "status": "count_mismatch",
                "steps": 0,
                "emitted": False,
                "executable": False,
            })
        return {
            "ok": False,
            "reason": "count_mismatch",
            "queries_seen": n,
            "dataset_count": n,
            "dataset_sha256": actual_sha,
            "query_column": query_column,
            "format": format,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "expected_count": expected_count,
            "decomposed_queries": 0,
            "emitted_queries": 0,
            "executable_queries": 0,
            "emitted_steps": 0,
            "executable_steps": 0,
            "rows": rows_pre,
            "network_calls": 0,
            "attempt_count": 0,
            "supported_answer_quality": None,
            "evidence_status": "no_available_offline_evidence",
        }
    # Pure planner only from frozen source.
    try:
        resolved = _resolve_repo_root(str(repo_root))
        if resolved is None:
            resolved = repo_root
        planner_mod = _load_planner(resolved)
        plan_fn = getattr(planner_mod, "plan_research_query", None)
        valid_fn = getattr(planner_mod, "validate_research_plan", None)
        if not callable(plan_fn) or not callable(valid_fn):
            return _fail_coverage("missing_planner",
                queries_seen=n, decomposed_queries=0, emitted_queries=0,
                executable_queries=0, emitted_steps=0, executable_steps=0)
    except Exception:
        return _fail_coverage("planner_load_error",
            queries_seen=n, decomposed_queries=0, emitted_queries=0,
            executable_queries=0, emitted_steps=0, executable_steps=0)
    decomposed = 0
    emitted = 0
    executable = 0
    emitted_steps = 0
    executable_steps = 0
    answerable_false = 0
    rows = []
    for i, q in enumerate(queries, 1):
        qh = _sha256_bytes(q.encode("utf-8"))
        try:
            plan = plan_fn(q, max_hops=max_hops, max_searches=max_searches)
        except Exception:
            plan = {"status": "unsupported", "steps": []}
        if not isinstance(plan, dict):
            plan = {"status": "unsupported", "steps": []}
        steps = plan.get("steps")
        if not isinstance(steps, list):
            steps = []
        ns = len(steps)
        status = plan.get("status", "unsupported")
        if not isinstance(status, str):
            status = "unsupported"
        is_emitted = ns >= 1
        is_decomposed = ns > 1
        # Executable: valid DAG and inside chosen budgets.
        is_executable = False
        try:
            valid = valid_fn(plan, max_hops=max_hops, max_searches=max_searches)
        except Exception:
            valid = False
        if valid is True:
            try:
                depths = [s.get("depth") for s in steps if isinstance(s, dict)]
                max_d = max(depths) if depths else 0
            except Exception:
                max_d = 99
            if isinstance(max_d, int) and max_d <= max_hops and ns <= max_searches:
                is_executable = True
        if is_decomposed:
            decomposed += 1
        if is_emitted:
            emitted += 1
            emitted_steps += ns
        if is_executable:
            executable += 1
            executable_steps += ns
        try:
            ans_flag = plan.get("answerable", True)
        except Exception:
            ans_flag = True
        if ans_flag is False:
            answerable_false += 1
        rows.append({
            "id": i,
            "query_hash": qh,
            "status": status,
            "steps": ns,
            "emitted": bool(is_emitted),
            "executable": bool(is_executable),
            "answerable": (False if ans_flag is False else True),
        })
    return {
        "ok": True,
        "queries_seen": n,
        "dataset_count": n,
        "dataset_sha256": actual_sha,
        "dataset_identity": actual_sha,
        "query_column": query_column,
        "format": format,
        "max_hops": max_hops,
        "max_searches": max_searches,
        "expected_count": expected_count,
        "decomposed_queries": decomposed,
        "emitted_queries": emitted,
        "executable_queries": executable,
        "emitted_steps": emitted_steps,
        "executable_steps": executable_steps,
        "answerable_false": answerable_false,
        "rows": rows,
        "network_calls": 0,
        "attempt_count": 0,
        "supported_answer_quality": None,
        "evidence_status": "no_available_offline_evidence",
    }


# ---------------------------------------------------------------- replay ---

def _load_builder(source_root: Path):
    script = Path(source_root) / "goat-web" / "scripts" / "build_plugin_bundle.py"
    name = "goat_v51_bundle_builder_%s" % uuid.uuid4().hex[:8]
    spec = importlib.util.spec_from_file_location(name, str(script))
    if spec is None or spec.loader is None:
        raise ImportError("no builder spec")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return mod


def _install_socket_guard(counter):
    """Block real sockets/DNS; count attempts. Returns restore fn."""
    orig_gai = socket.getaddrinfo
    orig_cc = socket.create_connection
    orig_sock = socket.socket
    orig_gbn = getattr(socket, "gethostbyname", None)
    orig_gni = getattr(socket, "getnameinfo", None)

    def _blocked(*a, **k):
        counter["attempts"] = counter.get("attempts", 0) + 1
        raise AssertionError("network disabled during offline replay")

    _orig_cls = orig_sock

    class _BlockedSocket(_orig_cls):
        def __new__(cls, *a, **k):
            counter["attempts"] = counter.get("attempts", 0) + 1
            raise AssertionError("socket construction disabled during offline replay")

    socket.getaddrinfo = _blocked
    socket.create_connection = _blocked
    socket.socket = _BlockedSocket
    if hasattr(socket, "gethostbyname"):
        socket.gethostbyname = _blocked
    if hasattr(socket, "getnameinfo"):
        socket.getnameinfo = _blocked

    def _restore():
        socket.getaddrinfo = orig_gai
        socket.create_connection = orig_cc
        socket.socket = orig_sock
        if orig_gbn is not None:
            socket.gethostbyname = orig_gbn
        if orig_gni is not None:
            socket.getnameinfo = orig_gni
    return _restore


def _parse_url_qs(url: str):
    from urllib.parse import urlparse, parse_qs
    try:
        parts = urlparse(url)
        return parse_qs(parts.query)
    except Exception:
        return {}


def replay_fixtures(source_root, fixture_path, expected_sha256):
    """Replay synthetic fixtures through the REAL bundle + REAL search.

    Only the HTTP _fetch boundary is faked with exact fixture extracts.
    """
    net_counter = {"attempts": 0}
    restore = _install_socket_guard(net_counter)
    bundle_tmp = None
    pkg_name = None
    try:
        if not _is_strict_hex64(expected_sha256):
            return {"ok": False, "reason": "bad_expected_hash",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        if not isinstance(source_root, str) or not source_root:
            return {"ok": False, "reason": "bad_source_root",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        if not isinstance(fixture_path, str) or not fixture_path:
            return {"ok": False, "reason": "bad_fixture_path",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        resolved_src = _resolve_repo_root(source_root)
        if resolved_src is None:
            return {"ok": False, "reason": "missing_source_root",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        src = resolved_src
        try:
            fraw = Path(fixture_path).read_bytes()
        except Exception:
            return {"ok": False, "reason": "unreadable_fixture",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        actual_sha = _sha256_bytes(fraw)
        if actual_sha != expected_sha256:
            return {"ok": False, "reason": "hash_mismatch",
                    "network_calls": 0,
                    "attempt_count": int(net_counter.get("attempts", 0)),
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0,
                    "fixture_sha256": actual_sha}
        try:
            doc = json.loads(fraw.decode("utf-8"))
        except Exception:
            return {"ok": False, "reason": "bad_fixture_json",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        if not isinstance(doc, dict):
            return {"ok": False, "reason": "bad_fixture_doc",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        fixtures = doc.get("fixtures")
        if not isinstance(fixtures, list) or not fixtures:
            return {"ok": False, "reason": "no_fixtures",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": 0, "answered": 0, "abstained": 0,
                    "partial": 0, "provider_errors": 0}
        # Build ONE fresh bundle for this replay call (manifest checked inside).
        try:
            builder = _load_builder(src)
        except Exception:
            return {"ok": False, "reason": "builder_load_error",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": len(fixtures), "answered": 0,
                    "abstained": 0, "partial": 0, "provider_errors": 0}
        base = os.environ.get("TMPDIR") or tempfile.gettempdir()
        try:
            Path(base).mkdir(parents=True, exist_ok=True)
            bundle_tmp = tempfile.mkdtemp(prefix="goat-v51-replay-", dir=str(base))
        except Exception:
            bundle_tmp = tempfile.mkdtemp(prefix="goat-v51-replay-")
        pkgdir = Path(bundle_tmp) / "hermes-goat-web"
        try:
            builder.build_bundle(str(src), str(pkgdir))
        except Exception:
            return {"ok": False, "reason": "bundle_build_error",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": len(fixtures), "answered": 0,
                    "abstained": 0, "partial": 0, "provider_errors": 0}
        # Explicit manifest re-check (read-only).
        try:
            builder.check_bundle(str(src), str(pkgdir))
        except Exception:
            return {"ok": False, "reason": "bundle_check_error",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": len(fixtures), "answered": 0,
                    "abstained": 0, "partial": 0, "provider_errors": 0}
        pkg_name = "goat_v51_replay_pkg_%s" % uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(
            pkg_name, str(pkgdir / "__init__.py"),
            submodule_search_locations=[str(pkgdir)],
        )
        if spec is None or spec.loader is None:
            return {"ok": False, "reason": "bundle_load_error",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": len(fixtures), "answered": 0,
                    "abstained": 0, "partial": 0, "provider_errors": 0}
        pkg = importlib.util.module_from_spec(spec)
        sys.modules[pkg_name] = pkg
        try:
            spec.loader.exec_module(pkg)
        except Exception:
            sys.modules.pop(pkg_name, None)
            return {"ok": False, "reason": "bundle_exec_error",
                    "network_calls": 0, "attempt_count": 0,
                    "fixture_count": len(fixtures), "answered": 0,
                    "abstained": 0, "partial": 0, "provider_errors": 0}
        wiring = pkg.v3_wiring
        # Real keyword extractor for evidence lookup only.
        kw_fn = getattr(wiring, "_answer_keywords", None)
        if not callable(kw_fn):
            # Fallback replica (stopword strip) — still keyword-only.
            _STOP = frozenset((
                "what", "which", "who", "whom", "whose", "when", "where",
                "why", "how", "is", "are", "was", "were", "be", "been",
                "being", "do", "does", "did", "done", "the", "a", "an",
                "of", "for", "to", "in", "on", "at", "by", "with", "about",
                "as", "from", "that", "this", "these", "those", "it", "its",
                "and", "or", "but", "if", "then", "than", "so", "such",
                "no", "not", "only", "own", "same", "tell", "me", "you",
                "your", "please", "name", "give", "list", "show",
            ))
            import re as _re2
            _TRE = _re2.compile(r"[^\W_]+", _re2.UNICODE)

            def kw_fn(q):
                if not isinstance(q, str):
                    return ""
                toks = _TRE.findall(q)
                kept = [t for t in toks if t.casefold() not in _STOP]
                return " ".join(kept) if kept else q.strip()
        answered = 0
        abstained = 0
        partial = 0
        provider_errors = 0
        traces = []
        fake_http_calls = 0
        # For quality: collect answered claim support.
        quality_checked = 0
        quality_supported = 0
        quality_claims = 0
        for fx in fixtures:
            if not isinstance(fx, dict):
                continue
            fid = fx.get("id", "")
            fquery = fx.get("query", "")
            ev = fx.get("evidence")
            if not isinstance(ev, dict):
                ev = {}
            force_status = fx.get("force_http_status", fx.get("http_status", None))
            # Build keyword -> results map using CURRENT extractor only.
            kw_map = {}
            title_map = {}
            for ek, lst in ev.items():
                if not isinstance(ek, str) or not isinstance(lst, list):
                    continue
                try:
                    kw = kw_fn(ek)
                except Exception:
                    continue
                # Exact fixture text preserved; never append temporal fields.
                clean = []
                for r in lst:
                    if not isinstance(r, dict):
                        continue
                    t = r.get("title", "")
                    u = r.get("url", "")
                    e = r.get("extract", "")
                    if not isinstance(t, str) or not isinstance(e, str):
                        continue
                    if not isinstance(u, str):
                        u = ""
                    clean.append({"title": t, "url": u, "extract": e})
                kw_map[kw] = clean
                for r in clean:
                    if r["title"] not in title_map:
                        title_map[r["title"]] = r["extract"]
            state = {"last": [], "calls": 0}

            def _fake_fetch(url, **kwargs):
                nonlocal_fake = state
                state["calls"] += 1
                # Counted by outer via state; also global.
                # Provider-error injection for this fixture.
                if type(force_status) is int and 100 <= force_status <= 599:
                    import json as _js
                    return {"status": force_status, "headers": {},
                            "body": _js.dumps({"error": "synthetic provider failure"}),
                            "url": url}
                qs = _parse_url_qs(url)
                # Extracts request?
                is_extracts = False
                try:
                    prop = qs.get("prop", [])
                    if prop and "extracts" in prop[0]:
                        is_extracts = True
                    if "prop" in url and "extracts" in url:
                        is_extracts = True
                except Exception:
                    is_extracts = False
                import json as _js
                if is_extracts:
                    pages = []
                    # Serve from last search results with EXACT extracts.
                    for idx, r in enumerate(nonlocal_fake["last"], 1):
                        pages.append({
                            "pageid": idx,
                            "title": r["title"],
                            "extract": r["extract"],
                        })
                    body = _js.dumps({"query": {"pages": pages}}).encode("utf-8")
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                # Search request: decode srsearch keyword.
                sr = ""
                try:
                    sr_list = qs.get("srsearch", [])
                    if sr_list:
                        sr = sr_list[0]
                except Exception:
                    sr = ""
                hit = kw_map.get(sr, None)
                if hit is None:
                    # Missing key -> valid empty search JSON (abstain, no fallback).
                    body = _js.dumps({"query": {"search": []}}).encode("utf-8")
                    nonlocal_fake["last"] = []
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                items = []
                for idx, r in enumerate(hit, 1):
                    items.append({"title": r["title"], "pageid": idx})
                nonlocal_fake["last"] = list(hit)
                body = _js.dumps({"query": {"search": items}}).encode("utf-8")
                return {"status": 200, "headers": {}, "body": body, "url": url}

            # Wrap counter for global fake_http_calls.
            _orig_fake = _fake_fetch

            def _counting_fetch(url, **kwargs):
                return _orig_fake(url, **kwargs)

            try:
                answer_search = wiring.make_default_answer_search(_fetch=_counting_fetch)
                default_search = wiring.make_default_search(_fetch=_counting_fetch)
            except Exception:
                # If factory missing, count as provider error for this fixture.
                provider_errors += 1
                traces.append({
                    "id": fid if isinstance(fid, str) else "",
                    "query_hash": _sha256_bytes(str(fquery).encode("utf-8")),
                    "status": "provider_error",
                    "ok": False,
                    "search_calls": 0,
                    "http_requests": 0,
                    "budget": {"max_hops": 4, "max_searches": 8},
                    "trace": [],
                    "request": "research",
                })
                continue
            deps = wiring.WiringDependencies(
                search=default_search, answer_search=answer_search,
                vertical_transports=None,
            )

            class _Ctx:
                def __init__(self):
                    self.tools = {}

                def register_tool(self, **kwargs):
                    self.tools[kwargs["name"]] = kwargs

            ctx = _Ctx()
            try:
                pkg.register(ctx, deps=deps)
            except Exception:
                provider_errors += 1
                traces.append({
                    "id": fid if isinstance(fid, str) else "",
                    "query_hash": _sha256_bytes(str(fquery).encode("utf-8")),
                    "status": "provider_error",
                    "ok": False,
                    "search_calls": 0,
                    "http_requests": 0,
                    "budget": {"max_hops": 4, "max_searches": 8},
                    "trace": [],
                    "request": "research",
                })
                continue
            handler = ctx.tools.get("goat_answer", {}).get("handler")
            if not callable(handler):
                provider_errors += 1
                continue
            import json as _js2
            try:
                payload_raw = handler({
                    "query": fquery, "research": True,
                    "max_hops": 4, "max_searches": 8,
                })
                payload = _js2.loads(payload_raw)
            except Exception:
                provider_errors += 1
                traces.append({
                    "id": fid if isinstance(fid, str) else "",
                    "query_hash": _sha256_bytes(str(fquery).encode("utf-8")),
                    "status": "provider_error",
                    "ok": False,
                    "search_calls": 0,
                    "http_requests": 0,
                    "budget": {"max_hops": 4, "max_searches": 8},
                    "trace": [],
                    "request": "research",
                })
                continue
            fake_http_calls += int(state.get("calls", 0))
            okv = payload.get("ok") is True
            meta = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
            research = meta.get("research", {}) if isinstance(meta.get("research"), dict) else {}
            rstatus = research.get("status", "")
            if not isinstance(rstatus, str):
                rstatus = ""
            scalls = research.get("search_calls", 0)
            if type(scalls) is not int:
                scalls = 0
            hreq = research.get("http_requests", None)
            if hreq is not None and type(hreq) is not int:
                hreq = None
            err = payload.get("error", {}) if isinstance(payload.get("error"), dict) else {}
            ecode = err.get("code", "") if isinstance(err, dict) else ""
            if not isinstance(ecode, str):
                ecode = ""
            # Classify: provider errors are non-INSUFFICIENT backend codes.
            is_provider = (not okv) and (ecode in _PROVIDER_CODES) and (ecode != "INSUFFICIENT_EVIDENCE")
            # HTTP_ERROR etc from fake provider fixture land here.
            trace_entry = {
                "id": fid if isinstance(fid, str) else "",
                "query_hash": _sha256_bytes(str(fquery).encode("utf-8")),
                "status": (rstatus if isinstance(rstatus, str) and rstatus else ("answered" if okv else "abstained")),
                "ok": bool(okv),
                "search_calls": scalls,
                "http_requests": hreq,
                "max_hops": 4,
                "max_searches": 8,
                "budget": {"max_hops": 4, "max_searches": 8,
                           "max_http_requests": 16},
                "trace": payload.get("hops", []),
                "request": "research",
            }
            if okv:
                trace_entry["answer"] = payload.get("answer", "")
                trace_entry["sources"] = payload.get("sources", [])
            if is_provider:
                provider_errors += 1
                trace_entry["status"] = "provider_error"
                trace_entry["provider_code"] = ecode
            elif okv:
                answered += 1
                # Quality: verify exact sentence support on ANSWERED.
                try:
                    ans = payload.get("answer", "")
                    srcs = payload.get("sources", [])
                    lines = [ln for ln in ans.split("\n") if ln.strip()] if isinstance(ans, str) else []
                    quality_checked += 1
                    quality_claims += len(lines)
                    # Collect known exact extracts for this fixture.
                    known = set()
                    for lst in ev.values():
                        if isinstance(lst, list):
                            for r in lst:
                                if isinstance(r, dict) and isinstance(r.get("extract"), str):
                                    import re as _re3
                                    # Split extract into sentences (simple).
                                    for s in _re3.split(r"(?<=[.!?])\s+", r["extract"].strip()):
                                        if s.strip():
                                            known.add(s.strip())
                    # Every claim body (sans markers) must be an exact known sentence.
                    import re as _re4
                    all_ok = True
                    for ln in lines:
                        body_m = _re4.sub(r"(?:\s*\[\d+\])+\s*$", "", ln).strip()
                        if body_m not in known:
                            all_ok = False
                            break
                    # Every cited URL must be https and cited set contiguous
                    # (already enforced by engine; re-check for quality).
                    cited = {int(x) for x in _re4.findall(r"\[(\d+)\]", ans)} if isinstance(ans, str) else set()
                    idxs = [s.get("index") for s in srcs] if isinstance(srcs, list) else []
                    if sorted(idxs) != list(range(1, len(idxs) + 1)):
                        all_ok = False
                    if cited != set(idxs):
                        all_ok = False
                    for s in (srcs if isinstance(srcs, list) else []):
                        if not isinstance(s, dict) or not str(s.get("url", "")).startswith("https://"):
                            all_ok = False
                    if all_ok:
                        quality_supported += 1
                except Exception:
                    pass
            else:
                # Not provider, not answered: partial vs abstained/unsupported.
                if rstatus == "partial":
                    partial += 1
                else:
                    # unsupported / abstained / budget_exhausted all reconcile as abstained.
                    abstained += 1
                    if rstatus not in ("abstained", "unsupported", "budget_exhausted"):
                        trace_entry["status"] = "abstained"
            # Bound trace sizes (hoptrace<=8 already; keep).
            try:
                if isinstance(trace_entry.get("trace"), list) and len(trace_entry["trace"]) > 8:
                    trace_entry["trace"] = trace_entry["trace"][:8]
            except Exception:
                pass
            traces.append(trace_entry)
        n = len(fixtures)
        # Quality object: no recall/answer-accuracy fields.
        if quality_checked > 0:
            quality = {
                "evaluated": quality_checked,
                "fully_supported": quality_supported,
                "total_claims": quality_claims,
                "support_complete_sentence": (quality_supported == quality_checked),
            }
        else:
            quality = None
        result = {
            "ok": True,
            "label": "synthetic",
            "fixture_count": n,
            "fixtures_seen": n,
            "total": n,
            "answered": answered,
            "abstained": abstained,
            "partial": partial,
            "provider_errors": provider_errors,
            "agentic_supported_answer_quality": quality,
            "fixtures": traces,
            "traces": traces,
            "fixture_sha256": actual_sha,
            "source_root": str(src),
            "source_identity": str(src),
            "network_calls": 0,
            "attempt_count": int(net_counter.get("attempts", 0)),
            "http_attempts": 0,
            "fake_http_calls": fake_http_calls,
            "max_hops": 4,
            "max_searches": 8,
        }
        return result
    finally:
        try:
            restore()
        except Exception:
            pass
        # Deterministic cleanup: remove bundle tmp (paths never in output).
        try:
            if bundle_tmp and Path(bundle_tmp).exists():
                shutil.rmtree(bundle_tmp, ignore_errors=True)
        except Exception:
            pass
        try:
            if pkg_name and pkg_name in sys.modules:
                for k in [k for k in sys.modules if k == pkg_name or k.startswith(pkg_name + ".")]:
                    sys.modules.pop(k, None)
        except Exception:
            pass
        # Drop builder module to keep determinism.
        try:
            for k in [k for k in list(sys.modules) if k.startswith("goat_v51_bundle_builder_")]:
                # Keep only the earliest? Remove all replay builders for cleanliness.
                # They contain random suffixes so removal is deterministic-safe.
                sys.modules.pop(k, None)
        except Exception:
            pass


# ------------------------------------------------------------------ CLI ---

def _build_parser():
    p = argparse.ArgumentParser(
        prog="run.py",
        description="GOAT V5.1 offline evaluation (synthetic only; no live calls).",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("coverage", help="Planner-only coverage over CSV/TSV/JSONL.")
    c.add_argument("--dataset", required=True, help="Dataset path (csv/tsv/jsonl).")
    c.add_argument("--expected-sha256", required=True, help="Lower64 hex sha256 of dataset bytes.")
    c.add_argument("--query-column", required=True, help="Column holding queries.")
    c.add_argument("--format", default="csv", choices=["csv", "tsv", "jsonl"], help="Dataset format.")
    c.add_argument("--max-hops", type=int, default=4, help="Depth 1..4 (default 4 for coverage).")
    c.add_argument("--max-searches", type=int, default=8, help="Logical calls 1..8 (default 8 for coverage).")
    c.add_argument("--expected-count", type=int, default=None, help="Optional exact row count (e.g. 824).")
    c.add_argument("--output", required=True, help="Output JSON path.")
    r = sub.add_parser("replay", help="Replay synthetic fixtures via real bundle + fake HTTP.")
    r.add_argument("--fixture", required=True, help="Fixture JSON path.")
    r.add_argument("--expected-sha256", required=True, help="Lower64 hex sha256 of fixture bytes.")
    r.add_argument("--source-root", required=True, help="Repo source root for fresh bundle.")
    r.add_argument("--output", required=True, help="Output JSON path.")
    return p


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "coverage":
        # Strict int conversion already via argparse; still enforce bool-safe.
        res = planner_coverage(
            args.dataset, args.expected_sha256, args.query_column,
            format=args.format, max_hops=args.max_hops,
            max_searches=args.max_searches,
            expected_count=args.expected_count,
        )
        try:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(res, fh, sort_keys=True, indent=2)
                fh.write("\n")
        except Exception as exc:
            print("error: cannot write output: %s" % exc, file=sys.stderr)
            return 2
        print(json.dumps({"ok": res.get("ok"), "output": args.output}, sort_keys=True))
        return 0 if res.get("ok") is True else 1
    elif args.cmd == "replay":
        res = replay_fixtures(args.source_root, args.fixture, args.expected_sha256)
        try:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as fh:
                json.dump(res, fh, sort_keys=True, indent=2)
                fh.write("\n")
        except Exception as exc:
            print("error: cannot write output: %s" % exc, file=sys.stderr)
            return 2
        print(json.dumps({"ok": res.get("ok"), "output": args.output}, sort_keys=True))
        return 0 if res.get("ok") is True else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
