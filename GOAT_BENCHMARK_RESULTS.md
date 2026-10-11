# GOAT V3 — Independent Live Benchmark Results (first baseline)

Tester: Claude Code (independent QA). Builder: Hermes. **No production code was modified.**
Target: `hermes-community-plugins` @ `163c2d9` (verified: `git log` HEAD of the base before this work; bundle built with `goat-web/scripts/build_plugin_bundle.py`).
Run date: 2026-10-11 (UTC). Raw data: `results/*.json`. Harness (benchmark-only, new): `benchmarks/live/`.

## 1. Environment verification (Step 1) — PASS, live execution allowed

| Check | Result |
|---|---|
| Baseline commit | `163c2d9` present, tree clean |
| Harness / preflight found | `benchmarks/run.py` (offline only), `adapters/bench_gate.py`, `goat-web/scripts/start_with_preflight.py` |
| DNS | `example.com→104.20.23.154/172.66.147.243`, `en.wikipedia.org→208.80.153.224`, `html.duckduckgo.com→40.89.244.232`, `api.tavily.com→44.193.171.14…` — all genuinely public; **no 198.18.x.x** |
| Direct HTTPS | Python `socket.create_connection` to `example.com:443` / `en.wikipedia.org:443` connected to the public peer IP, TLS 1.3 verified with the *system* trust store (no MITM CA needed). `curl --noproxy '*'` → 200 |
| Proxy-only / DNS interception | An env HTTPS proxy exists (`127.0.0.1:35569`) but direct egress also works, so GOAT's "no proxy fallback" contract is satisfiable. Resolver is 8.8.8.8 |
| GOAT preflight (`start_with_preflight.py --allow-network`) | **"GOAT preflight passed … via pinned_fetch"**. (rc=5 afterwards only because `hermes` binary isn't installed here.) |
| SSRF protection | Untouched. Negative controls enforced live: `https://127.0.0.1`, `http://example.com`, `https://169.254.169.254/…`, empty query → `URL_BLOCKED` |
| Offline suites | adapters 222 OK, goat-web 211 OK (6 skipped, native-gate env), goat-ultimate 26 OK; `benchmarks/run.py` runs |

Caveat: this container's egress is proxy-policy-governed; results are valid for *this* environment/IP only (shared datacenter IP → more DDG bot challenges than a residential host).

## 2. Live tool smoke (Step 2) — `results/smoke_live.json`

Seven tools registered: `goat_search, goat_extract, goat_crawl, goat_probe, goat_answer, goat_filtered_search, goat_vertical_search`. Invoked through the real plugin `register()` JSON handlers. 22 calls (18 functional, 4 safety negatives).

| Tool | Cases | Outcome | Latency |
|---|---|---|---|
| goat_search | 5 | 5/5 ok, relevant top hits (python.org, Canberra, OpenAI release notes); nonsense query still returned 4 junk hits (no empty) | 688–806 ms |
| goat_extract | 3 | 3/3 ok (example.com, Wikipedia, docs.python.org) | 133–489 ms |
| goat_crawl | 2 | 2/2 ok (1 page, 5 pages) | 172–778 ms |
| goat_probe | 2 | example.com ok; `httpbin.org/status/404` → `URL_BLOCKED` (no status returned) | 111–212 ms |
| goat_answer | 2 | ok=true but **wrong/garbled** ("capital of France" → answer about capital punishment) — FA-3 | 324–544 ms |
| goat_filtered_search | 1 | ok=true, **empty results** for `machine learning` + `en.wikipedia.org` + `en` — FA-4 | 352 ms |
| goat_vertical_search | 3 | scholar ok (low-quality figure records), images ok, **news: URL_BLOCKED after 10.1 s** (timeout misclassified) — FA-5 | 263–536 ms; news 10139 ms |
| safety negatives | 4 | 4/4 correctly blocked, 0 ms | – |

Success rate (functional): 14 ok-envelope / 18 = 78%; of those 14, 2 (`goat_answer`) and 1 (`filtered_search`) are semantically wrong/empty. Latency across 21 live calls: p50 352 ms, p95 806 ms (excluding the 10 s timeout, which is the max).

**PROVIDER_BLOCKED confirmation (search): PASS.** Real DDG HTTP 202 anomaly page (verified independently with urllib: status 202, body contains "anomaly"/"challenge") yielded `PROVIDER_BLOCKED` at 221–234 ms in 3 live occurrences (SimpleQA-n5 q0; FRAMES-n30 two cases, incl. q8), never an empty success.
**PROVIDER_BLOCKED for extract: FAIL.** HTTP 403 pages returned `ok:true` with junk/empty text (6/30 Firecrawl cases, FA-1).

## 3. Established benchmarks (Step 3)

### Evaluator availability
No `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` or any competitor key is present, and paid calls are not authorized. The official You.com / Tavily-style harness grades with an LLM judge and an LLM synthesis step → **official accuracy scores were NOT produced**. Nothing below is an official score.

| Suite | Official data obtained? | Official grading run? | What was run |
|---|---|---|---|
| You.com `web-search-api-evals` (SimpleQA, FRAMES) | Yes — repo @ `2e3e1b5bdd02bf962b0e86fbcede8c7263823980`, `data/simpleqa_full_dataset.csv` (4326 q), `data/frames_full_dataset.csv` (824 q) | **No** (needs paid LLM judge+synthesizer) | GOAT retrieval-only diagnostic, 5 then 30 each, seed 0 |
| Firecrawl scrape-content-dataset-v1 | Yes — HF sha `aad2b002cd74147236ee6fb4fd7e2bcf28955c3c`, 1000 pages | Partially — Firecrawl's grader repo not reachable; **documented approximation** | `goat_extract`, 5 then 30, seed 0 |
| Tavily Search Evals | `tavily-ai/search-evals` not found/accessible (a `tavily-search-evals` ref exists but wasn't in session scope); same SimpleQA data via You.com repo | No | – (covered by SimpleQA above) |
| Exa Benchmarks | Not accessible | No | – |
| OpenBenchmarks | No public repo/data located | No | – |
| BrowseComp / DeepSearchQA / FinSearchComp | Data present in You.com repo | No — marked research-endpoint-only | not run |

### Retrieval-only diagnostic (NOT comparable to published accuracy)
Metric: normalized gold-answer string containment in GOAT `goat_search` top-5 titles+snippets ("snippet recall") and additionally in `goat_extract` text of top-3 pages ("page recall"). It is an upper-bound-ish *evidence-availability* proxy: containment ≠ a correct synthesized answer, and no LLM answers were produced. Provider blocks are excluded from denominators and reported separately.

| Suite (n, seed 0) | Valid | PROVIDER_BLOCKED | Snippet recall | Page recall | Search p50 / p95 |
|---|---|---|---|---|---|
| SimpleQA n=5 | 4 | 1 | 75% | 100% | 786 / 842 ms |
| SimpleQA n=30 | 30 | 0 | **83.3%** | **93.3%** | 816 / 996 ms |
| FRAMES n=30 | 28 | 2 | **10.7%** | **21.4%** | 860 / 1061 ms |

Interpretation: GOAT's keyless DDG-backed search surfaces the gold string for single-hop SimpleQA facts, but **multi-hop FRAMES retrieval is weak** (queries are long compositional questions; DDG returns generic pages — FA-2).

### Firecrawl scrape-content-dataset-v1 on `goat_extract` (approximate grader)
Grader (mine, documented in `benchmarks/live/scrape_eval.py`): truth_recall = share of `truth_text` tokens in extracted text; truth_hit = recall ≥ 0.8; lie leak = normalized `lie_text` substring present.

| n | Coverage (ok envelope) | truth_hit (of ok) | mean truth_recall | lie leak | truncated @8000 | p50 / p95 |
|---|---|---|---|---|---|---|
| 5 | 100% | 20% | 0.44 | 0% | 40% | 673 / 2512 ms |
| 30 | 100% (but 7 are HTTP 403/404/202 pages) | **36.7%** | 0.51 | 3.3% | 23.3% | 743 / 3651 ms |

Real coverage (HTTP 2xx only) = 23/30 = 76.7%. Static-HTML extractor; JS-rendered pages score ~0 (FA-6).

### Not yet done / expansion
Expansion beyond 30 (e.g. 100–300) was not run in this first pass to avoid DDG rate-blocks on a shared IP; harness supports it (`N` argument). Official-judge scores need an authorized evaluator key.

## 4. Cost
GOAT is keyless: $0 per request; paid-API cost per successful task = $0 (no LLM synthesis exists in GOAT either). Competitor costs were not measured.

## 5. Reproduce
```
python3 -B goat-web/scripts/build_plugin_bundle.py --output $B
python3 -B benchmarks/live/smoke.py $B results/smoke_live.json
python3 -B benchmarks/live/retrieval_eval.py $B <you.com repo>/data/simpleqa_full_dataset.csv simpleqa 30 0 results/simpleqa_n30.json --extract
python3 -B benchmarks/live/retrieval_eval.py $B <you.com repo>/data/frames_full_dataset.csv frames 30 0 results/frames_n30.json --extract
python3 -B benchmarks/live/scrape_eval.py $B <HF 1-0-0.csv @aad2b00> 30 0 results/firecrawl_n30.json
```
Benchmark-only changes: new `benchmarks/live/{common,smoke,retrieval_eval,scrape_eval}.py`, new `results/`. No existing file touched except the docs listed in the deliverables.
