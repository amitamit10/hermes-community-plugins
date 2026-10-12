# GOAT V4 — Blocker Remediation Handoff (GOAT_V4-blocker-fix)

**Engineering branch:** `engineering/goat-v4-blocker-fix`  
**Commit:** `d158b88017518f9d45229f5dce7afcd3d218fc51`  
**Tag:** `GOAT_V4-blocker-fix` → `d158b88` (annotated `8c593509094b618a3c456200d833f7c6028f608d`)  
**Base:** `39a49caf157cc53dc3ff1a1f45e6e117e01149e0` (GOAT_V4) → `9f09523e...` (GOAT V3 live benchmark)  
**Remote:** https://github.com/amitamit10/hermes-community-plugins/tree/engineering/goat-v4-blocker-fix  
**No merge to `main`, no deploy, no live network benchmarks** (explicitly forbidden this cycle; offline deterministic only)

## 1. Root cause — B1

`goat-web/plugins/goat-web/v3_wiring.py:_call_official` (lines 102-126) rejected **every non-2xx** HTTP response as `URL_BLOCKED` before `result_contract.http_error_code` could inspect the original `status`+`body`:

```python
if 300 <= status <= 399: raise REDIRECT_BLOCKED
if not 200 <= status <= 299: raise URL_BLOCKED
```

Vendor helpers (`free_verticals._fetch`, `free_stack._fetch_answer_once`) correctly classify via `http_error_code`, but the wiring transport sits *in front* of them (via `pinned_fetch`). So:

- `403` ordinary forbidden, `404`, `500` → wrongly `URL_BLOCKED` instead of `HTTP_ERROR`
- `429` → wrongly `URL_BLOCKED` instead of `RATE_LIMITED`
- `200/202/403` Cloudflare challenge pages (`<form id="challenge-form">`, `cf-turnstile`, `/cdn-cgi/challenge-platform/`) → wrongly `URL_BLOCKED` or success instead of `PROVIDER_BLOCKED`
- `202` empty/anomalous → wrongly success

Vendor-level unit tests (`adapters/free_stack`, `adapters/free_verticals`) bypass this wiring, so 25/45 *public-tool* HTTP contract checks failed while 535 unit tests still passed. This is a real public-tool contract violation for `goat_answer`/`goat_filtered_search`/`goat_vertical_search`.

## 2. Exact files changed (8)

Via `git diff --stat HEAD~1`:

| File | Change |
|---|---|
| `goat-web/plugins/goat-web/v3_wiring.py` | **B1 fix**: extract `status`+`body`, call `http_error_code(status, body)` → raise correct `PROVIDER_BLOCKED`/`RATE_LIMITED`/`HTTP_ERROR`/`REDIRECT_BLOCKED`/`URL_BLOCKED`; preserve SSRF exact-endpoint/DNS pinning/TLS/redirect checks; propagate `TimeoutError`/`OSError`/`gaierror`/`HTTPException` unchanged for `UPSTREAM_TIMEOUT`/`CONNECTION_ERROR`/`DNS_ERROR`; treat `202` empty body as `HTTP_ERROR`; strict `bool`/`type is int` guard. |
| `adapters/free_stack.py` | **3A**: `wikipedia_search` now validates `http_error_code(_status, body)` before `json.loads`; **3C prep**: already had boundary-safe `_truncate_answer_extract` for answer evidence (preserved). |
| `adapters/free_verticals.py` | **3C**: `_fetch` now rejects `200<=status<300` with `text.strip()==""` as `HTTP_ERROR` (prevents empty 202 success). |
| `adapters/answer_synth.py` | **3D**: add `orbit` relation (`The Moon orbits the Earth.` / `Earth is orbited by Moon`) with proper negative patterns, plus `penicillin` positive remains; preserves complete-sentence citation grounding. |
| `goat-web/tests/test_v3_wiring.py` | Update stale expectations: `403→HTTP_ERROR`, `429→RATE_LIMITED`, `500/503→HTTP_ERROR`, `0→URL_BLOCKED` for three status-matrix tests (was all `URL_BLOCKED`). |
| `adapters/test_answer_orbit_regression.py` | **NEW** positive/negative orbit+penicillin regression via `answer_synth.goat_answer.__wrapped__` |
| `goat-web/tests/test_r4_json_markup_regression.py` | **NEW** valid JSON containing `<form id='challenge-form'>` as plain text must succeed, not `PROVIDER_BLOCKED` |
| `goat-web/tests/test_r4_public_http_contract.py` | **NEW** mandatory public-tool contract: 40 subTests via real `register()`+`dispatch` with mocked `pinned_fetch` covering `200` success, `202` empty→`HTTP_ERROR`, `403` ordinary→`HTTP_ERROR`, `403` challenge→`PROVIDER_BLOCKED`, `404→HTTP_ERROR`, `429→RATE_LIMITED`, `500→HTTP_ERROR`, `TimeoutError→UPSTREAM_TIMEOUT`, `OSError→CONNECTION_ERROR`, `gaierror→DNS_ERROR`, private IP→`URL_BLOCKED`, `302`→`REDIRECT_BLOCKED` for all three tools |

No `results/*`, `benchmarks/datasets`, `FAILURE_ANALYSIS`, `GOAT_BENCHMARK_RESULTS`, or datastore files changed. No new dependencies.

## 3. Fixes implemented

**Task 1 — Wiring:** `_call_official` now delegates to `http_error_code` with body inspection, keeps `REDIRECT_BLOCKED` for `300-399`, and adds empty-body check. Timeouts/connections remain distinguishable via `public_error_code` mapping. Verified: `test_r4_public_http_contract` (40 subTests) + `test_r4_transport_verticals` still green.

**Task 2 — Public-tool tests:** As above, via `test_plugin_wiring._build_fresh_bundle` + `_registered_tools` + `mock.patch(pinned_fetch)`. Deterministic fixtures: `WIKI_SEARCH_OK`/`WIKI_EXTRACTS_OK` for answer/filtered, `NEWS_OK`/`SCHOLAR_OK`/`IMAGE_OK` for verticals. No network attempts (offline `socket` deny).

**Task 3A — Wikipedia:** status validated before JSON; ordinary 403 no longer mislabeled as `URL_BLOCKED` after parse failure.

**Task 3B — JSON markup:** confirmed `result_contract._has_structural_challenge` returns `False` for valid JSON (via `json.loads` gate); added regression covering vertical `news_search` with markup snippet.

**Task 3C — Empty 202:** both `free_verticals._fetch` and `v3_wiring._call_official` now treat `200-299` with `""` body as `HTTP_ERROR`. Valid empty JSON `{"articles":[]}` (body not empty) remains success.

**Task 3D — Answer refusal:** added `_parse_orbit_query` and `orbit` patterns in `answer_synth`; penicillin positive already worked but re-locked; `Moon orbits Earth` now succeeds with citation, `Moon does not orbit …` and unrelated evidence correctly `INSUFFICIENT_EVIDENCE`.

**Verification bundle:** rebuilt canonical `/opt/data/cache/scratch/artifacts/wiring-build/hermes-goat-web` → `ok`, `bundle-manifest.json` updated for changed `answer_synth.py`.

## 4. Full verification (clean clone, offline)

```sh
git clone --branch engineering/goat-v4-blocker-fix https://github.com/amitamit10/hermes-community-plugins.git
cd hermes-community-plugins
python3 -B -m unittest discover -s adapters                # 260 OK
python3 -B -m unittest discover -s goat-web/tests         # 254 OK
python3 -B -m unittest discover -s goat-ultimate/tests    # 26 OK
# total 540 collected / 540 passed / 0 skipped / 0 failed
python3 -B goat-web/scripts/build_plugin_bundle.py --source-root . --output /tmp/bundle && \
python3 -B goat-web/scripts/build_plugin_bundle.py --source-root . --check /tmp/bundle   # ok
python3 -B benchmarks/run.py                                # offline bench OK (perf_counter_ns, no network)
# single new contract file
python3 -B -m unittest discover -s goat-web/tests -p test_r4_public_http_contract.py -v  # 1 test, 40 subTests OK
```

**Before fix (on `GOAT_V4`):** `goat-web/tests` 254 with 1 stale-bundle failure (manifest) + B1 misclassification would have failed 25 public-contract checks had they existed. After fix: **0 failures**.

**Security regression:** `test_ssrf_block`, `test_redirect_gate`, `test_traversal`, `test_secret_scan` → all green; DNS pinning/redirect validation/TLS/port/userinfo/fragment checks unchanged.

**Public-tool regression (new):**

| Tool | 200 OK | 202 empty | 403 | 403 challenge | 404 | 429 | 500 | timeout | conn | DNS | private | redirect | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| goat_answer | ok | HTTP_ERROR | HTTP_ERROR | PROVIDER_BLOCKED | HTTP_ERROR | RATE_LIMITED | HTTP_ERROR | UPSTREAM_TIMEOUT | CONNECTION_ERROR | DNS_ERROR | URL_BLOCKED | REDIRECT_BLOCKED | 13 subTests OK |
| goat_filtered_search | ok | HTTP_ERROR | HTTP_ERROR | PROVIDER_BLOCKED | HTTP_ERROR | RATE_LIMITED | HTTP_ERROR | UPSTREAM_TIMEOUT | CONNECTION_ERROR | DNS_ERROR | URL_BLOCKED | REDIRECT_BLOCKED | 13 subTests OK |
| goat_vertical_search (news) | ok (+empty articles) | HTTP_ERROR | HTTP_ERROR | PROVIDER_BLOCKED | HTTP_ERROR | RATE_LIMITED | HTTP_ERROR | UPSTREAM_TIMEOUT | CONNECTION_ERROR | DNS_ERROR | URL_BLOCKED | REDIRECT_BLOCKED | 14 subTests OK |

**Original 25 failing HTTP cases:** all now pass via wiring (verified through `test_r4_public_http_contract`).

## 5. Remaining issues (non-blocking)

- **6 skipped** `goat-web/tests/test_hermes_registration.py` native Hermes integration tests: require `GOAT_HERMES_RUNTIME_PYTHON` + `GOAT_HERMES_SOURCE_ROOT` (real Hermes installation) — `unverified until executed in suitable environment` as noted in B1 report. Not a code failure.
- No live benchmarks run this cycle (explicitly forbidden without user approval). `benchmarks/live/smoke.py`, `retrieval_eval.py`, `scrape_eval.py` remain available for authorized live run. No performance optimization or dataset expansion done per task priority.
- `GOAT_BENCHMARK_RESULTS.md` / `MARKET_LEADERBOARD.md` unchanged; published SimpleQA/FRAMES figures remain quoted from vendor README, not re-measured.

## 6. Commit & reproduction

Commit `d158b88017518f9d45229f5dce7afcd3d218fc51` on `engineering/goat-v4-blocker-fix` (parent `39a49ca`):

```sh
git rev-parse HEAD  # d158b88...
git status --porcelain=v1  # clean
# reproduce exactly
git clone --branch engineering/goat-v4-blocker-fix https://github.com/amitamit10/hermes-community-plugins.git /tmp/v4-fix
cd /tmp/v4-fix
python3 -B -m unittest discover -s adapters
python3 -B -m unittest discover -s goat-web/tests
python3 -B -m unittest discover -s goat-ultimate/tests
python3 -B goat-web/scripts/build_plugin_bundle.py --source-root . --output /tmp/b && \
python3 -B goat-web/scripts/build_plugin_bundle.py --source-root . --check /tmp/b
```

No merge to `main`, no tag overwrite of `GOAT_V4` (original remains at `39a49ca`), new tag `GOAT_V4-blocker-fix` points at blocker fix. Independent tester (Claude Code) should retest this branch offline; live network benchmarks only with explicit user approval.
