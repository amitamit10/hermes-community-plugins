# GOAT V4 — Blocker Remediation: corrected independent-retest record

## Status and scope

**Independent verdict: CONDITIONAL PASS, offline/staging only. Production is not authorized.**

This document records the historical blocker-fix candidate, not acceptance of any subsequent patch:

- QA HEAD: `7ee5fc28ac0321e77368bc131b2d5316e514a89c`.
- Code commit: `d158b88017518f9d45229f5dce7afcd3d218fc51`.
- Engineering branch: `engineering/goat-v4-blocker-fix`.
- Historical tag: `GOAT_V4-blocker-fix`, targeting the code commit.
- Code parent: `39a49caf157cc53dc3ff1a1f45e6e117e01149e0` (`GOAT_V4`).
- No merge, deployment, production activation, or live benchmark is authorized by the verdict.

The independent tester's report is `QA_V4_FINAL_RETEST.md`, stored outside the repository. This correction uses the tester's summary supplied by the user; the full external report is not available in this workspace. Builder claims are not independent acceptance evidence. Claude Code remains the designated independent tester.

## Correction of the previous verification claims

The previous claim **“540 collected / 540 passed / 0 skipped / 0 failed” is withdrawn**. The independent retest reported:

- Collected: **540**.
- Passed: **534**.
- Skipped: **6**.
- Failed: **0**.

The six skipped methods are native Hermes integration tests in `goat-web/tests/test_hermes_registration.py`. The tester's environment lacked `GOAT_HERMES_SOURCE_ROOT` and `GOAT_HERMES_RUNTIME_PYTHON`. Skipped methods were not executed and are not passes. A future native run must identify the actual source/runtime, set both variables explicitly, and record its own results separately; it must not retroactively change the tester's counts.

The preceding QA before blocker remediation likewise reported **535 collected / 529 passed / 6 skipped / 0 failed**, not 535 passes.

The previous claim that JSON-markup handling was completely fixed is also withdrawn. The added `test_r4_json_markup_regression.py` checked vertical news only. That route already handled JSON correctly; it did not verify the legacy extract/crawl/probe routes.

## B1 — root cause and confirmed fix

`v3_wiring._call_official` previously rejected every non-2xx response as `URL_BLOCKED` before downstream `result_contract.http_error_code` could inspect the original status and body. Vendor-helper tests bypassed this production boundary. Ordinary HTTP errors, rate limits, and provider challenge pages were therefore mislabeled as URL-policy failures.

The code commit changes classification at the wiring boundary while retaining exact-endpoint checks, DNS pinning, TLS verification, redirect validation, and SSRF policy:

- Ordinary 403, 404, and 5xx: `HTTP_ERROR`.
- HTTP 429: `RATE_LIMITED`.
- Recognized structural HTML challenges: `PROVIDER_BLOCKED`.
- Empty/anomalous successful responses on the affected official routes: `HTTP_ERROR`.
- Unsafe redirects: `REDIRECT_BLOCKED`.
- URL/SSRF policy violations: `URL_BLOCKED`.
- Timeout, connection, and DNS failures remain distinguishable.

**Independent confirmation:** the original 25 failing cases now pass **25/25 at each of two fixture levels**: injected fetch and the real pinned-fetch guard with fake DNS and connections only. Both levels invoke real registration and the serialized public tool handlers. These are separate matrices, not additional unit-test methods.

The tester also confirmed ordinary status/error classification, private and mixed DNS rejection before connection, and redirects to private addresses or HTTP being blocked. No guard, dataset, seed, or scoring weakening was reported.

## Historical code changes — eight files

Use the explicit code revision range, not `HEAD~1`, because the QA HEAD also includes a documentation commit:

```sh
git diff --name-status 39a49caf157cc53dc3ff1a1f45e6e117e01149e0 d158b88017518f9d45229f5dce7afcd3d218fc51
```

- `goat-web/plugins/goat-web/v3_wiring.py`: B1 HTTP classification at the real official-provider boundary; empty-body rejection on that path.
- `adapters/free_stack.py`: Wikipedia search validates HTTP status before interpreting JSON.
- `adapters/free_verticals.py`: empty-body rejection on official vertical fetches.
- `adapters/answer_synth.py`: grounded orbit relation handling and penicillin regression coverage.
- `goat-web/tests/test_v3_wiring.py`: correct obsolete expectations for ordinary HTTP errors/rate limits; preserve policy and redirect expectations.
- `adapters/test_answer_orbit_regression.py`: positive and negative grounded-answer regressions.
- `goat-web/tests/test_r4_json_markup_regression.py`: JSON-markup regression for vertical news **only**.
- `goat-web/tests/test_r4_public_http_contract.py`: registered public answer/filtered-search/vertical-search contracts with injected transport outcomes.

The private-IP case in the last file injects a guard exception from the mock. It tests exception propagation, **not actual private-address rejection**. Genuine SSRF acceptance requires the real guard, controlled resolver/connection seams, and proof that no connection was attempted.

## Other independently confirmed behavior

- Wikipedia search classifies upstream HTTP errors correctly.
- Penicillin and Moon-orbit questions return evidence-grounded answers whose citations resolve to the correct sources.
- Unrelated, negated, contradictory, and modal evidence returns `INSUFFICIENT_EVIDENCE`.
- The corrected existing 403/429 expectations are legitimate fixes to previously buggy expectations, not weakened policy checks.

## Open findings at the QA HEAD

### B3 — JSON data misclassified as a provider challenge

Valid JSON containing markup-like strings still returns `PROVIDER_BLOCKED` from `goat_extract`, `goat_crawl`, and `goat_probe`. The legacy HTML challenge parser needs response-data discrimination. A fix must exercise all three registered public tools through the actual guard and retain positive controls for genuine HTML challenges.

### B4 — empty HTTP 202 accepted on legacy content tools

`goat_extract` and `goat_crawl` still return empty successes for an empty HTTP 202 response. The official-provider wiring/vertical fixes do not cover these legacy routes. Regression tests must include empty and whitespace-only 202 responses and nonempty successful controls through the actual guard.

### Native integration and reporting

The six native methods remain **unverified in the independent tester's environment**. Correcting this report does not execute them. The prior counts and the inadequate private-IP fixture must not be reused as evidence of native or guard acceptance.

## Reproduction contract

For the historical candidate, pin the full QA revision before running anything:

```sh
git checkout --detach 7ee5fc28ac0321e77368bc131b2d5316e514a89c
git rev-parse HEAD
git status --porcelain=v1
python3 -B -m unittest discover -s adapters -v
python3 -B -m unittest discover -s goat-web/tests -v
python3 -B -m unittest discover -s goat-ultimate/tests -v
```

Build a fresh portable bundle with `goat-web/scripts/build_plugin_bundle.py --source-root . --output <isolated-bundle-directory>` and validate that same directory with `--check`. Use a unique task-local artifact parent where tests expect a canonical `artifacts/wiring-build/hermes-goat-web` path. Do not reuse another candidate's generated manifest.

For native verification in a suitable environment:

```sh
GOAT_HERMES_SOURCE_ROOT=<verified-Hermes-source-directory> \
GOAT_HERMES_RUNTIME_PYTHON=<verified-Hermes-Python-executable> \
python3 -B -m unittest discover -s goat-web/tests -p test_hermes_registration.py -v
```

These are reproduction instructions, not claims that the commands have been run by the reader. Preserve full outputs, real exits, cwd, revision, interpreter, explicit nonsecret prerequisite paths, and collected/passed/skipped/failed counts. Do not hide exits with output-filtering pipes. Use the test harness's temporary profiles and fake transports; do not activate the plugin in a live gateway.

## Acceptance still required

Before production consideration:

1. Fix B3 and B4 with registered public-tool tests through the real guard.
2. Add genuine private/mixed-DNS and unsafe-redirect regressions proving absence of forbidden connections.
3. Execute the six native methods with both explicit environment variables.
4. Rebuild and revalidate the portable bundle, and rerun full offline/security suites from an isolated fresh copy of the amended candidate.
5. Return the exact amended source identity, complete patch, actual counts, and receipts to Claude Code for a new independent retest.

A builder's subsequent green run does not replace independent acceptance, authorize a merge, or grant permission for production activation. Live benchmarks remain unrun unless separately authorized.
