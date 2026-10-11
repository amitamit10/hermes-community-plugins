# Capability Matrix (historical snapshot — see GOAT V3)

> Historical note: this matrix describes pre-V3 “keep vs build new” planning around `goat-web` v1’s four-tool gate. As of GOAT V3 `0.2.0` the centralized URL/SSRF gate, bounded deep-crawl frontier, and fixed official wiring for Wikipedia/Crossref/GDELT/Commons are implemented in the built `hermes-goat-web` bundle. Treat rows marked “future work” below as history; for current routing see `goat-ultimate/registry/capabilities.json` (schema_version 3) and `goat-web/skills/goat-web/SKILL.md`.

## Keep as-is — do not reimplement

| Capability | Existing Hermes route |
|---|---|
| `web_search` | `web_search` (Hermes built-in) routed to `goat_search` for GOAT |
| `web_extract` | `web_extract` → `goat_extract` |
| `browser_exec` | Local browser via CDP plus `browser-browser-use` support |
| `rss-feeds` | `rss-feeds` (GOAT adapters use `rss_watcher` mapping) |
| `web-api-automation` | keep |

## Built in this collection (GOAT V3 `0.2.0`)

| Capability | Status |
|---|---|
| Central URL and SSRF gate | **Shipped** — `goat-web/plugins/goat-web/url_gate.py` + pinned HTTPS egress |
| PSL / cookie enforcement | Deferred — out of scope for this candidate |
| Bounded deep-crawl frontier | **Shipped** — `goat_crawl` BFS depth ≤2 / pages ≤10, same-origin only |
| Deterministic answer + filtered search | **Shipped** — `goat_answer` / `goat_filtered_search` on Wikipedia Action API |
| Keyless verticals | **Shipped** — `goat_vertical_search` on Crossref/GDELT/Commons |

## Paid features — key required, fail-closed

Stay behind `requires_key` and return `MISSING_CONFIG` when absent; no silent fallback.

- Firecrawl, Exa, Tavily, Serper, Browserbase stealth, Bright Data (see `goat-ultimate/registry/capabilities.json` paid gate)
- Serper You/MCP profiles are experimental/unverified; explicit endpoint/auth required or `MISSING_CONFIG`

## Free merge candidates — permissive licenses only

| Component | License | Candidate role |
|---|---|---|
| Trafilatura | Apache-2.0 | Extraction core (reference) |
| Crawlee-python | Apache-2.0 | Queue/rate control (reference) |
| feedparser | BSD-2-Clause | RSS mapping (see `rss_watcher` mapping) |
| Mozilla Readability.js | Apache-2.0 | In-browser readability |

## External services only — never vendor

AGPL/GPL tools remain external services:

- SearXNG, Firecrawl engine, RSSHub, ultimate-sitemap-parser

SearXNG fits a small 2-vCPU VPS; self-host integration remains research, not part of this candidate’s bundle.
