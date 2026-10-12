# GOAT V5 Engineering Report and QA Handoff

Stacked candidate on `engineering/goat-v5-extract`, consolidating slices 1–3
on top of the V4-verified baseline. All work offline and local-only; no
merge, push, deploy, install, tag, or visibility change was performed.

## 1. Commit SHA chain (exact, oldest first)

| # | SHA (full) | Subject |
|---|------------|---------|
| 0 (base) | `1ea1decfc79f90f780dfc269ece30c485261a6bc` | `fix(goat): close V4 JSON markup and empty-body regressions` (V4 verified) |
| 1 (slice 1) | `34c5148e98eb8267c2f05b3e0e4e5fbf9588a29c` | `feat(goat-v5): pluggable search backend with fallback` |
| 1b (slice 1b) | `3686cf299bf85fa7a780df9987418d5f27ab06e4` | `test(goat-v5): align bundle inventory expectations with search_providers` |
| 2 (slice 2) | `d3aa586fc234d0a3dcea808e979efec1df49379f` | `feat(goat-v5): bounded two-hop retrieval with per-hop citations` |
| 3 (slice 3) | `74b0415ef84f3cfc2499cab0fa8a1bb3d4218ef4` | `feat(goat-v5): extraction usable-content floor and main-content scoring` |
| 4 (this report) | `git rev-parse HEAD` at QA time (`docs(goat-v5): engineering report and QA handoff`) |

HEAD at gate time: `74b0415ef84f3cfc2499cab0fa8a1bb3d4218ef4`.
Cumulative scope: `git diff 1ea1decfc79f90f780dfc269ece30c485261a6bc --stat` =
12 files, 2417 insertions, 47 deletions (see §2).

## 2. Architecture changes per slice

### Slice 1 — pluggable search backend with fallback (`34c5148`)

- NEW `goat-web/plugins/goat-web/search_providers.py` (504 lines, stdlib
  only: `http.client`, `json`, `socket`, `time`, `collections.abc`,
  `urllib.parse`). Ordered provider registry: DDG HTML first, Wikipedia
  OpenSearch second. `search_with_fallback` tries providers in order within
  budget; first success wins; errors fail over with a stamped
  `{from, to, reason}` entry in `transitions` (`transitions` omitted when no
  hop occurred); `MISSING_CONFIG` stops the chain immediately; when every
  provider fails the last error is preserved verbatim with the full chain.
  Every success stamps `source` (first contributing provider) and `sources`
  (plural contributor list). Dedup is exact-URL string match, cap 5 kept.
- `goat_tools.goat_search` gains opt-in `allow_fallback=False`. Unset (any
  value other than literal `True`) keeps the single-provider baseline path
  untouched; `True` registers the live DDG closure and dispatches through the
  registry. Default behavior is byte-identical to baseline (pinned by test).
- `build_plugin_bundle.py`: one-line allowlist addition so the new module
  ships (`PLUGIN_FILES += search_providers.py`).
- NEW `goat-web/tests/test_search_providers.py` (564 lines, 11 tests):
  fallback on `PROVIDER_BLOCKED`, last-error preservation, exact-URL dedup
  with cap 5, single-provider byte-identity pin, all offline via injected
  `transport(url)` fakes plus fake resolver/TCP denial.

### Slice 1b — bundle inventory alignment (`3686cf2`)

- Test-only: `test_plugin_wiring.py` and `test_portable_bundle.py` expected
  file sets gain `search_providers.py`. No production code touched.

### Slice 2 — bounded two-hop retrieval with per-hop citations (`d3aa586`)

- `adapters/answer_synth.py`: NEW planner-only additions (74 lines);
  evidence predicates untouched. `decompose_query` (one bridge family only —
  see §5), `extract_bridge_entity` (verb-pattern bridge extraction with
  1–6 capitalized-token guard), `MAX_HOPS = 2` /
  `MAX_CANDIDATES_PER_HOP = MAX_RESULTS` exported but **not referenced by any
  caller** (unused constants, see §5). Added to `__all__`.
- `goat-web/plugins/goat-web/v3_wiring.py` (`_make_answer_operation`):
  decompose → if not a 2-item plan, the original single-hop path runs with
  identical observable behavior; if 2-hop, hop 1 answers, bridge extracted,
  `{bridge}` substituted into hop-2 template, hop 2 answers, citations
  merged with hop-1 sources stamped `hop: 1` (indices kept) and hop-2
  sources renumbered by `+len(hop1_sources)` with `hop: 2`, hop-2 `[n]`
  references shifted by the same offset, plus a `hops` array. Unresolvable
  bridge or second hop → `INSUFFICIENT_EVIDENCE` (no guessing); detected
  bridge-token negation conflict in hop-2 evidence → suppress to
  `INSUFFICIENT_EVIDENCE`. All failure branches map through
  `public_error_code` / `_failure`, same as baseline. Cap: max 2 hops, max 5
  candidates/hop (via `_CANDIDATE_CAP`).
- NEW `adapters/test_multihop.py` (127 lines) and
  `goat-web/tests/test_v3_multihop.py` (245 lines, 4 tests): bridge-entity
  fixture (Hamlet → Shakespeare → Stratford-upon-Avon), unresolvable-hop
  abstention, conflict suppression, all offline with injected fakes.

### Slice 3 — extraction usable-content floor + main-content scoring (`74b0415`)

- `goat-web/plugins/goat-web/adapters.py` (`trafilatura_like_extract`):
  `_ReadableTextParser` rewritten from flat text join to scored segments
  (`_score_segment`: tag base + article/main ancestry bonus + length bonus −
  boilerplate class/id penalty − 3× link ratio). Segments with score > 0 win
  when any exist; otherwise all segments join (previous behavior preserved
  for pages with no positive signal). 8000-char contract and `truncated`
  semantics unchanged.
- `goat_tools.goat_extract` / `goat_crawl`: post-extract
  `if not text.strip(): return _http_error_result(status)` floor. Empty
  content maps to the existing `HTTP_ERROR` code — **no contract change**,
  no `EMPTY_CONTENT` addition (the recommended option from the arch audit).
- NEW `goat-web/tests/test_extract_floor.py` (230 lines, 5 tests): 202
  JS-shell → `HTTP_ERROR`; boilerplate-heavy fixture → main content wins;
  genuine short content still `ok`; truncation semantics unchanged. GREEN 5/5.

## 3. Full gate table (all `python3 -B`, real exits, receipts in `evidence/consolidation/`)

Runner workspace: `/opt/data/cache/scratch/goat-v5-slice3-20261012`
(`repo/` + `evidence/consolidation/`). HEAD `74b0415` at gate time.

| Suite | Command | Collected / passed / failed / skipped | Exit |
|-------|---------|----------------------------------------|------|
| adapters (full) | `python3 -B -m unittest discover -s adapters` | 264 / 264 / 0 / 0 | 0 |
| goat-web/tests (full) | `python3 -B -m unittest discover -s goat-web/tests` | 295 / 295 / 0 / 0 | 0 |
| goat-ultimate/tests | `python3 -B -m unittest discover -s goat-ultimate/tests -v` | 26 / 26 / 0 / 0 | 0 |
| native registration | `discover -s goat-web/tests -p test_hermes_registration.py -v` with `GOAT_HERMES_SOURCE_ROOT=/srv/media-ingest/hermes-service-home/hermes-agent-src` + `GOAT_HERMES_RUNTIME_PYTHON=/opt/data/installs/7e7873c79b16436d/environments/6e58e8c283ae4457a5cef422e9cd58e5/venv/bin/python` (both paths present; NOT blocked) | 8 / 8 / 0 / 0 | 0 |
| security: ssrf | `-p test_ssrf_block.py` | 10 / 10 / 0 / 0 | 0 |
| security: redirect | `-p test_redirect_gate.py` | 7 / 7 / 0 / 0 | 0 |
| security: traversal | `-p test_traversal.py` | 6 / 6 / 0 / 0 | 0 |
| security: secret-scan | `-p test_secret_scan.py` | 2 / 2 / 0 / 0 | 0 |
| gate fuzz | `-p test_gate_fuzz.py` | 4 / 4 / 0 / 0 | 0 |
| provider blocks | `-p test_search_provider_blocks.py` | 21 / 21 / 0 / 0 | 0 |
| plugin wiring | `-p test_plugin_wiring.py` | 8 / 8 / 0 / 0 | 0 |
| portable bundle | `-p test_portable_bundle.py` | 27 / 27 / 0 / 0 | 0 |
| search providers (slice 1) | `-p test_search_providers.py` | 11 / 11 / 0 / 0 | 0 |
| v3 multihop (slice 2) | `-p test_v3_multihop.py` | 4 / 4 / 0 / 0 | 0 |
| extract floor (slice 3) | `-p test_extract_floor.py` | 5 / 5 / 0 / 0 | 0 |
| manifest | `-p test_manifest.py` | 6 / 6 / 0 / 0 | 0 |
| bundle build | `build_plugin_bundle.py --source-root . --output <isolated-evidence-path>` | built ok | 0 |
| bundle check | `build_plugin_bundle.py --source-root . --check <bundle>` (note: `--check` takes the bundle path as its argument) | `ok <bundle>` | 0 |
| offline benchmarks | `python3 -B benchmarks/run.py` (portable gates only, no live scripts) | all 17 modules reported | 0 |
| `git diff --check` | clean, no output | — | 0 |
| `git status` | clean before gates; only this report file untracked at write time | — | 0 |

Totals: 559 offline tests (264 adapters + 295 goat-web) + 26 ultimate + 8
native, all GREEN. Zero failures, zero skips, zero BLOCKED. No live
network, no paid APIs, no dataset/seed/scoring modifications; no source
fixes were made during gating (nothing failed, nothing repaired).

## 4. Benchmark comparison plan (no live runs in this task)

- **Offline portable gates (runnable anywhere):** `python3 -B
  benchmarks/run.py` exercises `adapters/bench_gate.py` +
  `adapters/bench_modules.py` with fake transports and `perf_counter_ns`.
  Baseline expectation: all 17 modules report timing rows and the process
  exits 0. Any V5 slice must keep this green with no new module-list edits;
  record the per-module mean/p50/p99 table alongside the base table for
  regression comparison. Receipt for this HEAD is
  `evidence/consolidation/gate-benchmarks.txt`.
- **Held-out live protocol (for Claude, NOT run here):** live diagnostics in
  `benchmarks/live/` (`retrieval_eval.py` snippet/page recall on official
  datasets, `scrape_eval.py` documented approximation with dataset SHA
  `aad2b00` pinned in output, `smoke.py` all-routes live smoke incl. safety
  controls) are diagnostics, never official scores. Run them only in an
  environment where live egress is authorized; report env blocks separately
  (never score 0); never edit recorded `results/*.json` — new measurements
  go to new files. FRAMES reference point at audit time
  (`results/frames_n30.json`): n_valid 28/30, snippet_recall ≈ 0.107,
  page_recall ≈ 0.214 — the single-hop weakness slice 2 targets. Re-run the
  same FRAMES slice post-V5 and compare recall deltas; slice 2 is expected
  to lift bridge-entity questions while leaving single-hop scores unchanged.
- **What NOT to benchmark:** do not invent local substitutes for the
  official Firecrawl grader; `scrape_eval.py` stays a documented
  approximation.

## 5. Known limitations (carried, not introduced as regressions)

1. **Slice-3 crawl-empty-page aborts the whole crawl.** When any crawled
   page extracts to empty text, `goat_crawl` returns `_http_error_result`
   immediately, discarding already-collected pages, instead of skipping that
   page and continuing. `goat_extract` correctly errors per-URL; only the
   crawl loop's abort-vs-skip policy is debatable. Future fix must add a
   skip-and-continue test first.
2. **Unused constants.** `MAX_HOPS` / `MAX_CANDIDATES_PER_HOP` are exported
   from `adapters/answer_synth.py` (and in `__all__`) but zero callers
   reference them — `v3_wiring.py` hardcodes `len(plan) == 2` and
   `_CANDIDATE_CAP`. Either wire the constants in or remove them.
3. **One-bridge-family decomposition.** `decompose_query` fires only on
   `Where was the author|writer|creator|founder|inventor|director of <X>
   born?`. All other multi-hop shapes (comparisons, aggregations,
   multi-bridge chains, non-born relations) take the single-hop path and
   abstain as before. No regression — but V5 multihop coverage is one
   family wide.
4. **Exact-URL dedup.** `search_with_fallback` dedups on raw URL string
   equality (`seen_urls`); trailing-slash, query-param, and canonical-form
   duplicates across providers are not merged.
5. **`sources` (plural) dropped by the wiring allowlist.** Slice-1 success
   stamps both `source` and `sources`, but `_make_answer_operation`'s
   provenance copy loop only forwards `source, source_url, transitions,
   truncated, metadata, provenance` — `sources` never survives the answer
   path (the v3 answer backend does not consume the slice-1 registry at
   all). Decide whether the answer route should forward the contributor
   list or the field should stay search-route-only.
6. **Slice-2 citation renumbering assumes integer `index`.** Non-mapping
   sources or non-int indices fail the hop with `URL_BLOCKED`; safe but
   coarse — a malformed backend source poisons the whole answer instead of
   being dropped.
7. **Pre-existing gaps unchanged:** crawl is same-origin BFS in document
   order with no relevance ranking; verticals are metadata-only;
   English-Wikipedia default answers; forked DDG parsers (production vs
   `adapters/ddg_parser.py`); live-eval scripts duplicate route knowledge
   outside the gates.

## 6. Independent QA instructions for Claude Code

Do this on a fresh machine / fresh clone. Do NOT merge, deploy, go live,
spend money, or modify datasets.

```sh
git clone https://github.com/amitamit10/hermes-community-plugins
cd hermes-community-plugins
git checkout engineering/goat-v5-extract
git log --oneline -6   # expect 74b0415 / d3aa586 / 3686cf2 / 34c5148 / 1ea1dec on top
git status --short && git diff --check   # expect clean
```

Bundle build + check (isolated path outside the repo):

```sh
python3 -B goat-web/scripts/build_plugin_bundle.py --source-root . --output /tmp/goat-v5-qa-bundle
python3 -B goat-web/scripts/build_plugin_bundle.py --source-root . --check /tmp/goat-v5-qa-bundle
# expect: built ... / ok ..., both exit 0
```

Offline suites (all `python3 -B`, no network):

```sh
python3 -B -m unittest discover -s adapters                      # expect 264 OK
python3 -B -m unittest discover -s goat-web/tests                # expect 295 OK
python3 -B -m unittest discover -s goat-ultimate/tests           # expect 26 OK
python3 -B benchmarks/run.py                                     # expect exit 0, 17 module rows
```

Native registration (only if the Hermes source checkout and runtime venv
exist; otherwise record BLOCKED honestly — never fake a pass):

```sh
GOAT_HERMES_SOURCE_ROOT=<hermes-agent-src> GOAT_HERMES_RUNTIME_PYTHON=<venv-python> \
  python3 -B -m unittest discover -s goat-web/tests -p test_hermes_registration.py -v
# expect 8 OK where available
```

What NOT to do: no `git push`, no merge to any release branch, no deploy or
install of the bundle, no tags, no visibility changes, no live
`benchmarks/live/*` runs unless egress is explicitly authorized (then follow
§4), no edits to `benchmarks/` datasets/seeds/scoring, no edits to recorded
`results/*.json`, no new dependencies, no paid-provider credentials.

## 7. Review verdict

The cumulative diff was reviewed file-by-file against the audit's
must-not-change list. **No contract violations found:**

- `adapters/result_contract.py`, `adapters/ssrf_guard.py`,
  `goat-web/plugins/goat-web/url_gate.py`, `tool_schemas.py`,
  `adapters/bench_gate.py`, `adapters/bench_modules.py`, `benchmarks/`,
  and `goat_probe` semantics: **untouched** (empty diff).
- No hardcoded benchmark answers; no new runtime dependencies (slice-1 and
  slice-3 imports are stdlib-only); no error-code allowlist change
  (empty-content → existing `HTTP_ERROR`); no guard/DNS/TLS/redirect change;
  no probe-semantics change; evidence predicates in `answer_synth.py`
  read-only (additive planner functions only).
- Single-hop behavior pinned by tests on both changed routes (registry
  opt-in pin + full pre-existing suite green); the single-hop branch in
  `v3_wiring.py` duplicates rather than reuses the baseline block, which is
  a maintenance smell, not a behavior violation.
- Remaining REDs: **none**. All gates in §3 are GREEN with real exit 0.
