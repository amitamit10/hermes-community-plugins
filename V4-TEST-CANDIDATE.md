# V4-RC2 — Round 4 Engineering Test Candidate (Isolated, Not Live)

**Label**: `V4-RC2` / Round 4 engineering candidate. This supersedes the independently rejected `V4-RC1` handoff; do not conflate the two.
**Base**: `9f09523e9adec3aae7e1af6af3f2c1846a17012a`.
**Plugin**: `hermes-goat-web` `0.2.0` — name, version, registry metadata remain intentionally compatible with existing V3 metadata. Schema `V3` and internal plugin `0.2` were NOT renamed for this candidate.
**Scope**: isolated repo only. No commit, push, merge, install, activation, live network test, live quality score, or worker was run to prepare this file.

## What this is and is not

- **Is**: a portable engineering candidate for a separate independent tester to verify offline.
- **Is not**: a public tag, a published release, a live activation, or a score claim. No `hermes plugins enable`, gateway restart, live evaluation, or benchmark score is claimed here.
- **Pending separately**: independent tester verification and any live evaluation. Keep full local output as evidence; do not invent numeric totals in this handoff. The parent external receipt binds full gate counts after freeze.

## Complete candidate (correction of RC1 prose)

The RC1 handoff misleadingly said only test/prose files were touched and all shared source was unchanged. That description is superseded. This complete candidate integrates, relative to the pre-integrated input (not QA HEAD):

- shared HTTP/error taxonomy (`CONNECTION_ERROR` and related contract mapping),
- grounded default intro answers from the fixed English Wikipedia Action API (at most two official requests, at most five candidates, 8000 chars per evidence, 40000 total),
- source-owned filter metadata (`language=en` on the fixed-endpoint canonical host; optional `snippet_cut:true` only when an ordinary snippet was actually character-clipped),
- plus review fixes F01–F11.

Compatibility assertions are deltas relative to that pre-integrated input, not assertions against QA HEAD.

## F06 stabilization in this wave

- Ordinary search keeps the original bounded contract: generic `_truncate` is the HEAD character-clip (`value[:8000]`, cut flag) for all DuckDuckGo / SearXNG / Wikipedia records and titles.
- Answer evidence alone uses a dedicated boundary-safe truncator (`_truncate_answer_extract` in `adapters/free_stack.py`) only for `wikipedia_answer_search` extracts, so a character-clipped tail is never presented as a complete sentence.
- A character-clipped ordinary snippet carries source-owned `snippet_cut:true` only when actually cut; uncut snippets carry no new field and no inferred dates, language, or source.
- The answer consumer (`adapters/answer_synth.py`) conservatively skips known `snippet_cut` snippet-only items instead of treating an artificial terminal period as complete; full extracts, uncut snippets, and earlier safe extract facts are preserved.
- Bounds unchanged: `MAX_RESULTS=5`, `MAX_CONTENT_CHARS=8000`, `40000` total, at most `2` answer requests. No request-shape, scoring, or dataset changes.

## Answer grammar scope

Conservative bounded English only: direct clause with a named actor and finite predicate for the requested relation, or a complete declarative keyword claim covering all content tokens with a finite predicate. Unsupported names, paraphrases, multi-hop, model inference, and unrestricted semantic entailment abstain with public `INSUFFICIENT_EVIDENCE`, never a guess.

## Preserved exactly

`results/*`, `benchmarks/*`, `datasets/scoring`, and QA reports (`FAILURE_ANALYSIS.md`, `HERMES_FIX_REQUEST.md`, `GOAT_BENCHMARK_RESULTS.md`, `MARKET_LEADERBOARD.md`) are untouched. This handoff quotes no invented counts and no current all-green claim.

## Portable verification (offline, no live install)

Run from the repo root. Use `python3 -B` direct to stdout with no pipes that mask exit codes. Use fresh paths under the configured scratch root (`../artifacts/wiring-build/`); do not use `/tmp`.

```sh
git rev-parse HEAD
# expect 9f09523e9adec3aae7e1af6af3f2c1846a17012a

cat goat-web/plugins/goat-web/plugin.yaml
# expect name: hermes-goat-web version: 0.2.0, seven tools

python3 -B goat-web/scripts/build_plugin_bundle.py --output ../artifacts/wiring-build/v4-rc2-hermes-goat-web
# fresh directory required; fails if output exists

python3 -B goat-web/scripts/build_plugin_bundle.py --check ../artifacts/wiring-build/v4-rc2-hermes-goat-web

python3 -B -m unittest discover -s adapters -p "test_*.py"
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py"
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py"
```

Focused checks used during preparation (parent captures full evidence):

```sh
python3 -B -m unittest test_v4_review_answers.ReviewF06OrdinarySnippetTests.test_f06_ordinary_snippet_bounded_and_clipped_not_grounded
# cwd: adapters/

python3 -B -m unittest test_v4_review_answers.ReviewF06Tests.test_f06_clipped_tail_false_fact test_v4_review_answers.ReviewF07Tests.test_f07_keyword_complete_declarative_claim
# cwd: adapters/

python3 -B -m unittest goat-web.tests.test_v4_review_grounding.ReviewF06OrdinarySnippetTests.test_f06_ordinary_snippet_bounded_and_clipped_not_grounded goat-web.tests.test_v4_review_grounding.ReviewF06ClippedTailTests.test_f06_clipped_tail_false_fact
# cwd: repo root
```

No commit, push, activation, or live quality score. Capture counts and gates separately from full output; this handoff quotes no totals.

## Tester gates (separate)

- Fresh-bundle build and `--check` pass read-only on a clean checkout at the base above.
- The three offline suites above reproduce on a second clean machine; full stdout is the receipt.
- Native `validate` and `doctor --ci` (real `PluginContext` / `PluginManager` / `tools.registry`, disposable `HERMES_HOME`, no `--install-deps`) pass for the built bundle path, when the approved runtime and source are present; otherwise they skip with a clear reason.
- No repository visibility change, push, tag, live install / enable, network smoke, or service change without explicit human approval. Parent rebuilds, captures full suites, freezes, and reviews after this stop.
