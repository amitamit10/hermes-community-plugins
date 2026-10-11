# GOAT V3 vs Market — Leaderboard (published vs measured, kept separate)

> **No direct superiority/inferiority claim is made.** GOAT was *not* run through the official LLM-judged pipeline (no authorized evaluator/synthesis key; paid calls not approved). Published numbers below are quoted from the You.com `web-search-api-evals` README (commit `2e3e1b5`), which states: LLM judge GPT 5.4 Mini, synthesis GPT 5.6 Luna, run 2026-10-07. They were not re-measured by me and are the vendor-maintained repo's figures; Perplexity and Brave have no published figures in that README; Firecrawl published scores were not retrievable.

## A. Published (vendor-reported, NOT measured here)

**SimpleQA — accuracy (official LLM-judged)**

| Sampler | Accuracy | p50 ms |
|---|---|---|
| you_search | 96.11% | 597.9 |
| exa_search_with_text | 95.40% | 2502.0 |
| you_search_with_livecrawl | 95.23% | 4000.4 |
| parallel_search_basic | 94.87% | 1660.2 |
| tavily_search | 88.53% | 1930.0 |
| google_search | 50.08% | 1430.4 |

**FRAMES — accuracy (official LLM-judged)**

| Sampler | Accuracy | p50 ms |
|---|---|---|
| you_search | 74.03% | 884.2 |
| parallel_search_basic | 73.79% | 1730.9 |
| exa_search_with_text | 73.79% | 2693.7 |
| you_search_with_livecrawl | 72.12% | 3897.5 |
| tavily_search | 66.14% | 2240.0 |
| google_search | 60.00% | 1512.5 |

## B. Newly measured — GOAT only (retrieval-only diagnostic, different metric)

| Suite | n (seed 0) | Metric | GOAT | Search p50 / p95 | Reliability |
|---|---|---|---|---|---|
| SimpleQA | 30 | gold string in top-5 snippets | 83.3% | 816 / 996 ms | 30/30 served |
| SimpleQA | 30 | gold in snippets or top-3 page text | 93.3% | – | – |
| FRAMES | 30 | gold string in top-5 snippets | 10.7% | 860 / 1061 ms | 28/30 (2 PROVIDER_BLOCKED) |
| FRAMES | 30 | gold in snippets or top-3 page text | 21.4% | – | – |
| Firecrawl scrape v1 | 30 | truth_hit (approx. grader) | 36.7% | extract 743 / 3651 ms | 23/30 HTTP 2xx |

## C. Why these are not comparable
1. Metric: containment of the gold string in retrieved text ≠ LLM-judged correctness of a synthesized answer. GOAT has no synthesis step.
2. Subset: n=30 of 4326/824 (95% CI half-width ≈ ±13–18 pts); competitors were run on full sets.
3. Evaluator/config differ; GOAT = keyless DDG HTML + Wikipedia API from a shared datacenter IP.
4. Cost: GOAT $0/request vs paid competitors (not measured).

## D. Defensible readings
- GOAT retrieval latency (p50 ≈ 0.8 s) is in the same range as published p50s (0.6–2.7 s) — but published figures are provider-internal latency; not like-for-like.
- GOAT retrieves gold-bearing evidence for most single-hop SimpleQA items, yet is clearly weak on multi-hop (FRAMES) evidence; expect a large gap to published 66–74% once an official run is done. This is a hypothesis to confirm, not a result.
- Next step to get a comparable number: authorize an evaluator key, then run the official `eval_runner.py` with a GOAT sampler adapter (needs ≥300 cases per suite).
