# GOAT V5.1 research (offline contract)

## Public schema contract (exact)

- `research`: strict bool, default `False`. Non-bool rejects with zero
  backend calls.
- `max_hops`: integer 1..4, default `2`. Bool/float/str/None/out-of-range
  rejects. Bounds dependency depth (not facet count).
- `max_searches`: integer 1..8, default `4`. Strict as above. Bounds
  logical search calls.
- `max_results`: integer 1..5, default `5`. Strict as above. Caps direct
  final sources globally (`direct sources GLOBAL <= max_results`).

Bounds:

- Queries/templates <=2000 chars; bindings <=512 chars.
- Candidates 5 per call, 40 overall (`5*max_searches`); final answer
  <=8000 chars.
- Direct sources GLOBAL <= `max_results`; intermediate summary <=5;
  hop trace <=8 with safe per-hop URL provenance <=40.
- Wikipedia <=2 HTTP attempts per logical call, total
  <=2*`max_searches` <=16. Zero model/provider cost.
- Trusted injected host backend: physical count unknown/null; logical
  cap only (`max_http_requests = 2*max_searches`).

## SUPPORTED English compositional grammar

- Single-relation: `What does X orbit?`, `What is the capital of X?`,
  `Who <wrote|invented|found|founded|created|designed|discovered> X?`.
- Explicit full-question facets: `Who wrote A?; Who designed B?`
  (2..4 facets, each a full supported question; bare `and` without `;`
  unsupported).
- Plural capital: `What are the capitals of A and B?`; `Compare the
  capitals of A and B.` (evidence-only, no ranking).
- Intersection equality: `Who both wrote A and designed B?`;
  `Which city is the capital of both A and B?` (unique exact canonical
  equality across terminals, else abstain).
- Birth/year facts: `When|Where was <NP> born?` (subject-specific whole
  `was|were born` sentences; date needs 4-digit year, place needs
  capitalized place, never inferred across facets); `Who <verb> X in
  YYYY?` (retrieval includes year, grounding omits it, year gate
  requires year in source body sentences).

Strict abstention: unsupported arithmetic (`unsupported_arithmetic`),
date comparison (`unsupported_temporal_compare`, executable facets but
`answerable: False`), scopes/comparison tokens, pronouns, ambiguity
(distinct bindings), missing/negative/modal/conflicting evidence,
cycles/repeated queries, budget exhaustion. No general-web or FRAMES
accuracy claim; sentence-grounded English Wikipedia extracts only.

## Compatibility notes (intentional changes)

- Default normal single-hop identical to legacy (exact answer/sources,
  single search, no metadata change).
- Automatic legacy two-hop final citations corrected (final cites only
  terminal hop, strict contiguous 1..N) + sanitized partial/provenance
  (intermediate evidence capped, safe URLs only).
- Original predicates unchanged; old FRAMES paths call Search, not
  Answer.

## Live protocol (proposed only)

New held-out live protocol requires separate authorization,
preregistered questions/evidence/scoring, and frozen hash. Actual
execution NOT authorized / NOT performed. See
`evaluation/v51/live-protocol.md`. No `--live` flag exists.
