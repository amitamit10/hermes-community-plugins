# GOAT V3 Failure Analysis (baseline `163c2d9`, live 2026-10-11)

Raw evidence: `results/smoke_live.json`, `results/firecrawl_n30.json`, `results/frames_n30.json`, `results/simpleqa_n30.json`.

| ID | Severity | Summary |
|---|---|---|
| FA-1 | **High** | `goat_extract`/`goat_crawl` return `ok:true` on HTTP 403 bot-block pages (no `PROVIDER_BLOCKED`) |
| FA-2 | High (quality) | Multi-hop search recall very low (FRAMES 10.7% snippet recall) |
| FA-3 | High | `goat_answer` returns incoherent/wrong extractive answers |
| FA-4 | Medium | `goat_filtered_search` returns empty for ordinary query |
| FA-5 | Medium | `goat_vertical_search news` timeout (10.1 s) surfaced as `URL_BLOCKED` |
| FA-6 | Medium | Extraction quality: 36.7% truth-hit; JS pages empty; 8000-char cap truncates 23% |
| FA-7 | Low | `goat_probe` of a 404 returns `URL_BLOCKED` with no status |
| FA-8 | Low | Nonsense query returns 4 irrelevant hits (no low-confidence signal) |
| ENV | info | DDG 202 challenges on shared IP: 3/65 searches → correctly `PROVIDER_BLOCKED` (not a defect) |

## FA-1 extract returns success on provider/WAF blocks
- Input: `goat_extract {"url":"https://www.reuters.com/world/asia-pacific/indonesia-dishes-out-first-…"}` (Firecrawl case; also codezine.jp, cnil.fr, oc.eco.br, loopnet.com).
- Expected: `{"ok":false,"error":{"code":"PROVIDER_BLOCKED"}}` (task rule: bot challenge must not be a misleading success). Actual: `ok:true, status:403`, text 0–511 chars of block-page junk; 6/30 cases (20%) plus one 404 and one 202.
- Evidence: `results/firecrawl_n30.json` rows with `status` 403.
- Root cause (code read): `goat_extract` (`goat-web/plugins/goat-web/goat_tools.py` ~L303) never inspects `status`; only `goat_search` maps 403/429 to `PROVIDER_BLOCKED`.
- Repro: run `benchmarks/live/scrape_eval.py` n=30 seed 0, or call extract on the Reuters URL.
- Fix (Hermes): in extract/crawl, map 403/429 (and recognised challenge pages) to `PROVIDER_BLOCKED`; map 4xx/5xx to a non-success; keep 2xx semantics.
- Acceptance: unit test with 403 fixture → PROVIDER_BLOCKED; live n=30 Firecrawl run shows 0 `ok:true` with status ≥ 400.
- Rerun: `scrape_eval.py` n=30 seed 0.

## FA-2 multi-hop recall
- Input: FRAMES seed-0 n=30 (e.g. "What Formula One car was driven in 1994 by the nephew of a race car driver … " gold `Minardi M194`).
- Expected: evidence retrieved; actual: gold in snippets 3/28, in pages 6/28. Backend sends the whole long question to DDG HTML, no decomposition, no follow-up searches.
- Severity High for agentic use; not a bug per se — a capability gap.
- Fix: optional query decomposition/iterative retrieval; or document limit. Acceptance: FRAMES n=30 page recall ≥ 50% (proxy) and official judged run once evaluator authorised.
- Rerun: `retrieval_eval.py` FRAMES n=30 seed 0, then official run.

## FA-3 `goat_answer` incoherent
- Input: `goat_answer {"query":"What is the capital of France?"}`. Expected: Paris-bearing answer. Actual: sentences about US capital punishment, "On what day were you born?"; `Who discovered penicillin?` → clipped fragments, no named discoverer.
- Root cause (inference): keyword-overlap ranking over Wikipedia *search snippets* (fragmentary, `<span>`-stripped) with no entity/page grounding.
- Fix: pull page intro extracts (prop=extracts) or require sentence-level term coverage; return `ok:false`/low-confidence when no sentence covers the query.
- Acceptance: both repro queries contain "Paris" / "Fleming"; add regression tests.

## FA-4 `goat_filtered_search` empty
- Input: `{"query":"machine learning","allowed_domains":["en.wikipedia.org"],"language":"en"}` → `{"ok":true,"results":[]}`.
- Expected ≥1 en.wikipedia.org result. Per schema docs, filters exclude records lacking metadata; Wikipedia candidates likely lack `language` field → all excluded.
- Fix: derive language/domain from the known source (wikipedia→`en`) or return a distinct reason (`filtered_out_count`).
- Acceptance: repro returns ≥1 result.

## FA-5 news vertical timeout
- Input: `goat_vertical_search {"vertical":"news","query":"inflation"}` → `URL_BLOCKED` after 10139 ms (pinned-fetch 10 s timeout hit; GDELT is known-slow/rate limited).
- Issue: transport failure is indistinguishable from policy block; only 4 public codes exist. Fix: add a `UPSTREAM_TIMEOUT`/`TRANSPORT_ERROR` code (or map to PROVIDER_BLOCKED) and document. Acceptance: timeout fixture returns the new code.

## FA-6 extraction quality
- 30 Firecrawl cases: truth_hit 36.7%, 23.3% truncated at 8000 chars; e.g. `https://alexkademusic.com/links`, `seiserre.com.ar` recall 0–0.16 (JS-rendered / link lists), `claas.com` 0.52.
- Fix: improve main-content extraction (boilerplate removal), raise/parameterise cap, report `js_required` hint. Acceptance: truth_hit ≥ 60% on the same 30 (approx. grader).

## FA-7 / FA-8 (low)
- FA-7: `goat_probe {"url":"https://httpbin.org/status/404"}` → `URL_BLOCKED`; schema says status returned. Return `{ok:false,status:404,host}`.
- FA-8: `zxqvbnmw98123 qqqplmkj nonsense` returns 4 unrelated results; DDG fuzzy-matches — informational.

## Environmental (not scored as quality)
DDG HTTP 202 anomaly challenges (confirmed with urllib: status 202, "anomaly" in body) produced `PROVIDER_BLOCKED` ×3 in ~65 searches; excluded from recall denominators.
