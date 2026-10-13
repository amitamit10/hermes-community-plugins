# GOAT V5.1 offline evaluation (synthetic only)

Offline, deterministic, stdlib-only. No live bench, no network, no paid
calls. Pinned questions/golds/benchmarks/results are never inspected.

## API (`evaluation/v51/run.py`)

```python
planner_coverage(dataset_path, expected_sha256, query_column, *,
                 format='csv', max_hops=4, max_searches=8,
                 expected_count=None) -> dict  # format: csv|tsv|jsonl
replay_fixtures(source_root, fixture_path, expected_sha256) -> dict
```

- `planner_coverage`: pure planner only from frozen
  `adapters/answer_synth.py` (`plan_research_query` +
  `validate_research_plan`). Verifies raw bytes against strict lower64
  hex `expected_sha256` BEFORE parse/plan. Strict integer budgets
  (`type(x) is int`; bool/float/str/None reject). Projects only
  `query_column` into the engine; never reads/uses/logs other column
  values. Rows carry `id`/`query_hash`/`status`/step counts, never full
  query text. `decomposed_queries` = >1 step, `emitted_queries` = >=1
  step, `executable_queries` = valid DAG AND inside chosen
  hops/search budgets (`executable_steps` separate). `answerable=False`
  preserved for unsupported computations even when executable.
  Reports `supported_answer_quality: None` and
  `no_available_offline_evidence`, `network_calls: 0`. No sampling,
  no row filtering, exact dataset identity/count.
  Wrong hash or `expected_count` mismatch fails closed (`ok: False`,
  `network_calls: 0`); strict violations return `ok: False` (tests also
  accept `ValueError`).

- `replay_fixtures`: REAL fresh bundle builder (`build_bundle` +
  `check_bundle`) + REAL `register` + REAL JSON handler, REAL
  `make_default_answer_search` / wiki parser / classifier / planner /
  grounding. ONLY the HTTP `_fetch` boundary is faked with exact
  fixture extracts. Keyword lookup uses the current
  `_answer_keywords` extractor only. Extract bodies are exact fixture
  text; `temporal_literal`/date/answer fields are never appended;
  qualifiers are never stripped (missing keyword = valid empty search
  JSON = abstain, no fallback). Metrics `agentic_supported_answer_quality`
  checks exact complete-source-sentence support + strict contiguous
  direct markers on ANSWERED fixtures only; no recall/accuracy fields.
  Counts `answered`/`abstained`/`partial`/`provider_errors` reconcile to
  `fixture_count`; `unsupported` traces (temporal/arithmetic) reconcile
  as `abstained` but keep distinct `status`/`reason` from provider
  errors. Raw bounded traces carry actual logical/HTTP budgets,
  hashes/source identity, `synthetic` label. Deterministic across runs
  (time fields excluded). Socket/DNS blocked (`attempt_count: 0`);
  `fake_http_calls` counted separately. No runtime deps.

## Static fixtures

- `evaluation/v51/fixture-evidence.json` (`label: synthetic`, per-fixture
  `label: synthetic`, exact request-response maps). Deliberate synthetic
  data, no real API claim. Covers: chain/facets/intersection positives,
  year positive (passive `was invented in 1984 by`), year negative
  (missing 1984 abstains), date positive (`was born in 1970`), date
  place-only negative (`Dessa Lark was born in Hollis` for a When
  question abstains, no invented date), ambiguous/missing/conflicting/
  negative/modal, provider error (`force_http_status: 500`), temporal
  unsupported (`unsupported_temporal_compare`), arithmetic unsupported.
  Frozen after algorithm; no datasource/gold rules in prod.

## CLI (actual receipts, not stubs; exit nonzero on reject; no `--live`)

```
python3 -B evaluation/v51/run.py coverage \
  --dataset <path> --expected-sha256 <lower64> --query-column <name> \
  --format csv|tsv|jsonl --max-hops 4 --max-searches 8 \
  [--expected-count 824] --output <path>

python3 -B evaluation/v51/run.py replay \
  --fixture <path> --expected-sha256 <lower64> \
  --source-root <repo> --output <path>
```

Coverage defaults are 4/8 for this evaluation harness. Replay always uses
`max_hops=4/max_searches=8` internally (bounded traces record actuals).

## Live protocol

Proposed only in `evaluation/v51/live-protocol.md` and
`docs/v51-research.md`. Actual execution NOT authorized / NOT performed.
Requires separate authorization, preregistered questions/evidence/
scoring, and frozen hash.
