# V5.1 held-out live protocol (PROPOSED ONLY — NOT AUTHORIZED, NOT PERFORMED)

No `--live` flag exists. This file proposes; it does not execute.

## Gate

- Requires separate explicit authorization before any live call.
- Preregistered held-out questions, preregistered evidence snapshots,
  preregistered scoring rubric.
- Frozen algorithm hash recorded before any live run; any runtime drift
  aborts the run.
- Paid/provider calls, installs, config changes, and activation are out
  of scope for the current offline stage.

## Proposed steps (upon authorization only)

1. Freeze runtime; record `evidence/algorithm-freeze.json` hashes.
2. Preregister N held-out questions (disjoint from synthetic fixtures),
   evidence allowlist, and scoring (supported-answer quality only; no
   recall/accuracy without answers).
3. Execute bounded `goat_answer(research=True)` with preregistered
   budgets (`max_hops` 1..4, `max_searches` 1..8, `max_results` 1..5)
   via the real bundle; log raw bounded traces, HTTP counts, hashes.
4. Score only exact complete-source-sentence support with strict
   contiguous markers; abstain otherwise. Publish receipts.

Actual execution NOT authorized / NOT performed in this stage.
