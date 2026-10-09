# Capability Matrix

## Keep as-is — do not reimplement

| Capability | Existing behavior to preserve |
|---|---|
| `web_search` | Uses `ddgs`. |
| `web_extract` | Extracts one page, up to 15K characters. |
| `browser_exec` | Local browser execution plus the `browser-browser-use` plugin. |
| Blocked-page recovery | Try archive, then API, then Byparr, with browser last. |
| Byparr | Use for Cloudflare only. |
| `rss-feeds` | Keep the existing capability. |
| `web-api-automation` | Keep the existing capability. |

## Build new in this collection

| Capability | Status |
|---|---|
| Central URL and SSRF gate | Build as a new shared capability. |
| PSL cookie enforcement | Future work. |
| Bounded deep-crawl frontier | Future work. |

## Paid features — key required

Keep each feature behind a `requires_key` gate. If its key is missing, return a missing-key error; do not silently fall back to another provider or capability.

- Firecrawl
- Exa
- Tavily
- Serper
- Browserbase stealth
- Bright Data

## Free merge candidates — permissive licenses only

| Component | License | Candidate role |
|---|---|---|
| Trafilatura | Apache-2.0 | Extraction core. |
| Crawlee-python | Apache-2.0 | Queue and rate control. |
| feedparser | BSD-2-Clause | RSS. |
| Mozilla Readability.js | Apache-2.0 | In-browser readability. |

## External services only — never vendor

AGPL and GPL tools are external services only; do not vendor them:

- SearXNG
- Firecrawl engine
- RSSHub
- ultimate-sitemap-parser
