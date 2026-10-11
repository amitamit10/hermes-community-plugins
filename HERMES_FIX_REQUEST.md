# Handoff to Hermes — Round 3: live benchmark findings (commit `163c2d9`, 2026-10-11)

Live run succeeded (public DNS, direct TLS, GOAT preflight passed, SSRF intact). Full detail: `FAILURE_ANALYSIS.md`, `GOAT_BENCHMARK_RESULTS.md`. Priorities:

1. **FA-1 (P1)** `goat_extract`/`goat_crawl` must not return `ok:true` on HTTP 403/429 block pages → `PROVIDER_BLOCKED`; 4xx/5xx not success. Acceptance: 403 fixture test; rerun `python3 -B benchmarks/live/scrape_eval.py $BUNDLE <csv> 30 0 out.json` → 0 ok-with-status≥400.
2. **FA-3 (P1)** `goat_answer("What is the capital of France?")` must contain Paris; `"Who discovered penicillin?"` must name Fleming; return low-confidence failure otherwise.
3. **FA-4 (P2)** `goat_filtered_search{query:"machine learning",allowed_domains:["en.wikipedia.org"],language:"en"}` must return ≥1 result.
4. **FA-5 (P2)** distinct public code (or documented mapping) for upstream timeout; `news` vertical timed out at 10.1 s as `URL_BLOCKED`.
5. **FA-2/FA-6 (P2, quality)** multi-hop retrieval (FRAMES proxy 10.7%/21.4%) and extraction truth-hit 36.7%.
6. **FA-7 (P3)** probe should report status for 4xx.

Rerun after fixes: `benchmarks/live/smoke.py`, `retrieval_eval.py` (SimpleQA/FRAMES n=30 seed 0), `scrape_eval.py` (n=30 seed 0). Official LLM-judged scores still require an authorised evaluator key.

Tester rules respected: no production code modified, no security control weakened, no paid calls.

---

# Handoff to Hermes — Prioritized Fix Requests (from independent QA, 2026-10-11)

## Verification round 2 — commit `1311d89` (2026-10-11 ~17:05, fresh clone)

Re-ran Hermes's exact commands from repo root on a fresh clone:
- `python3 -B -m unittest discover -s adapters` → **218/218 OK** (previously 122/127; the 5 DNS-caused firecrawl/anysearch failures no longer reproduce)
- `python3 -B -m unittest discover -s goat-web/tests` → **178 collected, 6 skipped, 0 failed** — the 6 skips are exactly the `test_hermes_registration.py` native-gate tests, skipping cleanly with messages naming the missing env vars (`GOAT_HERMES_SOURCE_ROOT` / `GOAT_HERMES_RUNTIME_PYTHON`)
- `python3 -B -m unittest discover -s goat-ultimate/tests` → **26/26 OK**
- `test_portable_bundle` → 27/27 OK (approved-bundle test self-builds the dir)

**Marked verified:** P2-1 (test importability/portability on fresh clones). Total: 422 collected, 416 passed, 6 skipped, 0 failed.
**Still open:** P1-1 (`benchmarks/` still missing; `bench_gate.py` still references nonexistent `goat-browser-staging/` path), P1-2 (silent empty search on provider blocks), P1-3 (deployment contract docs), P3-1 (stale README counts — recount now: suites total 422, update claims accordingly).

Rules respected: no production code modified, no security protections disabled,
no scores fabricated. Each item is reproducible with the commands shown.

## P1-1. Commit or officially retire the `benchmarks/` system

- **Problem:** `benchmarks/` is missing; `adapters/bench_gate.py` references a
  nonexistent `goat-browser-staging/` path (`FileNotFoundError`). Live-score
  claims are unverifiable (FAILURE_ANALYSIS.md F3).
- **Repro:** `ls benchmarks` → missing; `python3 adapters/bench_gate.py` → `FileNotFoundError`.
- **Fix:** either commit the real benchmark suite (queries, datasets, runner,
  expected outputs) or delete `bench_gate.py` and remove benchmark claims.
- **Acceptance:** `python3 adapters/bench_gate.py` runs clean from a fresh
  clone, or the file and its claims are gone.

## P1-2. `goat_search`: stop returning silent empty success on provider blocks

- **Problem:** DDG HTTP 202 bot-challenge page → `{"results": []}`, no error
  (FAILURE_ANALYSIS.md F2). Indistinguishable from "no results".
- **Repro:** with any transport returning the 202 anomaly page,
  `goat_search("anything", transport)` → `{"results": []}`.
- **Fix:** detect challenge markers / zero-result-with-200 anomalies and return
  a distinct public error, e.g. `{"error": {"code": "PROVIDER_BLOCKED"}}`;
  document it in `references/tool-schemas.md` and `SECURITY.md`.
- **Acceptance:** unit test with a 202 anomaly-page fixture asserts
  `PROVIDER_BLOCKED`; a genuine zero-result SERP still returns
  `{"results": []}`.

## P1-3. Document the deployment contract for `pinned_fetch` (proxied/NAT envs)

- **Problem:** in any proxied or NAT-DNS environment GOAT is silently 100%
  non-functional (`URL_BLOCKED` on every call), with no documented requirement
  and no auditable opt-in (FAILURE_ANALYSIS.md F1).
- **Fix:** document in `SECURITY.md`/`QUICKSTART.md` that production use
  requires direct egress + public DNS; add a startup self-check
  (`goat_probe("https://example.com")` via `pinned_fetch`) that logs a clear
  diagnostic when the environment can't support it. Do **not** silently fall
  back to proxies.
- **Acceptance:** fresh-clone operator reading the docs knows the network
  requirements before first run; a blocked environment yields one clear
  diagnostic instead of per-call `URL_BLOCKED` mysteries.

## P2-1. Make adapter tests importable without manual `PYTHONPATH`

- **Problem:** `test_browser_tier`, `test_pack_ssrf` → `ModuleNotFoundError:
  No module named 'url_gate'` (FAILURE_ANALYSIS.md F5).
- **Fix:** add `adapters/conftest.py` inserting
  `../goat-web/plugins/goat-web` into `sys.path`, or document the exact
  invocation in `QUICKSTART.md`.
- **Acceptance:** `cd adapters && python3 -m unittest discover -p 'test_*.py'`
  collects all 18 modules with zero import errors on a fresh clone.

## P2-2. Remove live-DNS dependency from fake-transport adapter tests

- **Problem:** `test_firecrawl` (4) + `test_anysearch` (1) fail wherever DNS
  doesn't return public IPs, because `validate_public_url` uses the system
  resolver (FAILURE_ANALYSIS.md F4).
- **Fix:** thread an injectable `resolver` through the adapter clients (as
  `resolve_and_validate` already supports) and use a fixed public-IP resolver
  in tests — same pattern as `bench_modules.py`'s `PUBLIC_IP`.
- **Acceptance:** the 5 tests pass with networking fully disabled
  (e.g. `unshare -n` or DNS blackholed).

## P3-1. Fix stale counts in READMEs

- **Problem:** root README "96/96 green" vs. 127 actual tests; goat-web README
  "56 unit tests" vs. 61 actual (FAILURE_ANALYSIS.md F7).
- **Acceptance:** counts match `unittest` output, or are replaced with a
  pointer to CI.

## Suggested verification order for Hermes

1. P1-1 (unblocks all future benchmarking), 2. P1-2 (correctness signal),
3. P2-2 + P2-1 (portable green suite), 4. P1-3 (docs), 5. P3-1.

## QA artifacts (all under `~/workspace/goat-qa/`)

- `harness.py` — independent benchmark harness (test-only injected transport;
  not part of GOAT, does not modify it)
- `results/live_bench_20261011T034518Z.json` — raw live tool-logic results
- `results/bench_modules_20261011.txt` — synthetic module benchmark output
- `BENCHMARK_REPORT.md`, `GOAT_LEADERBOARD.md`, `FAILURE_ANALYSIS.md`, this file
