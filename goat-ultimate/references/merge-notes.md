# Merge notes and provenance ledger

Retrieval date: 2026-10-09. Private-repository sources were read via read-only `gh api` calls; each path pin below is the latest commit SHA returned for that path. No repository was cloned or pushed; no package was installed. Only local documentation and the local frontmatter-gate workflow were edited in the two staging trees; no live system or external repository was changed.

## Per-source ledger

| Source path | Retrieved | Upstream commit SHA | Reconciliation / use |
|---|---|---|---|
| `goat-browser-staging/skills/goat-web/SKILL.md` and `goat-browser-staging/skills/goat-web/references/tool-schemas.md` | 2026-10-09 | N/A — local staging snapshot; no `.git` metadata, and no source files copied | Referenced for the four GOAT web tool contracts and fail-closed URL behavior. `goat_search`, `goat_extract`, `goat_crawl`, and `goat_probe` are reused by reference; no implementation or tests were copied. |
| `goat-browser-staging/plugins/goat-web/goat_tools.py` and `goat-browser-staging/plugins/goat-web/url_gate.py` | 2026-10-09 | N/A — local staging snapshot; no `.git` metadata, and no source files copied | Existing implementation remains read-only. Canonical routes name the existing `goat_search`, `goat_extract`, and `goat_crawl` tools. `goat_probe` remains available for reachability checks, not a separate requested task class. |
| `goat-browser-staging/references/capability-matrix.md` | 2026-10-09 | N/A — local staging snapshot; no `.git` metadata | Reconciled the existing `web_search`, `web_extract`, browser, RSS, API-automation, and paid-provider overlaps. Existing capabilities are not modified. |
| `goat-browser-staging/PROVENANCE.md` and `goat-browser-staging/references/vendor-notes.md` | 2026-10-09 | Mozilla Readability `ab4027a8b37669745016869a37a504727992b2ba`; Trafilatura `v2.3.0` `6c1977a00b4e82ebb7e6fad1192467adaf24d430`; readability-lxml `0.9` `7159b09ad688378779294cbb5d9f3cfa3274368f`; SPDX MIT text `279b7e997a87c09be00dd6bdda189519ade502cf` | Local provenance/vendor notes are not git-backed; these are the pinned upstream references only. The PyPI versions are `trafilatura==2.3.0` and `readability-lxml==0.9`; no package source is copied or installed. |
| `amitamit10/hermes-community-extensions/skills/hermes-capability-router/SKILL.md` | 2026-10-09 | `0f7bf7ba4184d8faf21e605d56a5c3b3214bb246` | Adapted route-first selection, use of the smallest relevant capability, explicit side-effect boundaries, credential exclusion, and verification principles. Attribution is included in the new skill. The helper implementation was not copied. |
| `amitamit10/hermes-community-extensions/catalog/collection.yaml` | 2026-10-09 | `1fa77832c9e37aa09112fb48235ccc6c8712f439` | Reconciled the router and `hermes-doc-artifacts`, `hermes-xlsx-artifacts`, and `hermes-map-artifacts` entries with the route table. Routes are references only and do not install or activate components. Collection status and license policy are not changed. |
| `amitamit10/hermes-community-extensions/bootstrap/runtime-inventory.json` | 2026-10-09 | `0f7bf7ba4184d8faf21e605d56a5c3b3214bb246` | Historical upstream repository source only; no local environment state is represented. |
| `amitamit10/hermes-community-extensions/bootstrap/local-skills.inventory.json` | 2026-10-09 | `0f7bf7ba4184d8faf21e605d56a5c3b3214bb246` | Used as a reference inventory for local-skill route candidates; no inventory entry was copied into the GOAT-WEB staging area. |
| `amitamit10/hermes-community-extensions/docs/phase-2-capability-review.json` | 2026-10-09 | `1fa77832c9e37aa09112fb48235ccc6c8712f439` | Reconciled staged/deferred candidates and rejected overlapping or risky components. The staged-only MemPalace plugin is not selected as the canonical memory provider; the Hermes builtin `memory` route is retained. |
| Hermes CLI reference | N/A | N/A — environment-specific output omitted | Generic command reference only; no machine-specific state is retained. |

The private-repository SHAs above were obtained with `gh api repos/amitamit10/hermes-community-extensions/commits?path=<path>&per_page=1 --jq '[0].sha' --`. Local staging references are marked N/A because they have no upstream repository commit.

## GOAT-WEB v1 reference boundary

The v1 tools remain exactly where they are and are referred to by their existing names; no source, schema, or test file from that staging area was copied or edited. The documented bounds retained by reference are: search returns at most five results without fetching result URLs; single-page extraction returns at most 8,000 characters; crawl is same-origin breadth-first, depth at most two and pages at most ten; probe reports reachability without returning a response body. All GOAT URLs, redirects, and crawl-discovered URLs remain subject to the existing URL/SSRF gate.

The route map selects the bounded GOAT extractor (8,000-character cap) over the separate Hermes `web_extract` capability (15,000-character cap) to keep extraction behind the GOAT URL gate. `web_extract` itself is not changed or copied. Search similarly routes through the existing GOAT DuckDuckGo-backed implementation; the other providers stay noncanonical. `browser_exec` remains the canonical browser capability, with `browser-browser-use` as its support layer rather than a second route.

## Canonical routing and rejected overlaps

`registry/capabilities.json` is the only canonical mapping. There are 11 task classes and one canonical provider per class. Counts in the registry are checked by `tests/test_registry.py`.

- `web-search`: `goat_search` wins over the Hermes builtin `web_search`, bundled `web-ddgs`, and optional keyed providers.
- `extraction`: `goat_extract` wins over builtin `web_extract` and optional Exa, Firecrawl, and Tavily extraction routes.
- `browser`: `browser_exec` is retained. Browserbase stealth is a paid alternative, not a fallback; `browser-browser-use` is a support layer.
- `crawl`: `goat_crawl` wins over reference-MCP `web_crawl`, paid Firecrawl, and external-only `ultimate-sitemap-parser`.
- `rss`: existing local `rss-feeds` is retained; RSSHub remains external-only and is not bundled.
- `api-automation`: existing local `web-api-automation` is retained.
- `media`: `youtube-content` is the single default route. `youtube-downloader`, `gif-search`, `songsee`, and `ascii-video` remain specialized, noncanonical workflows.
- `docs-artifacts`: `hermes-doc-artifacts` is the default; `hermes-book-artifacts` remains a specialized book-generation route.
- `sheets`: `hermes-xlsx-artifacts` is selected over the generic `xlsx` skill for artifact generation.
- `maps`: `hermes-map-artifacts` is selected for map-artifact generation; the separate `maps` OSM/OSRM skill is for geocoding and route lookup, not the artifact route.
- `memory`: Hermes builtin `memory` is selected; staged-only `mempalace` and the derived `memory-wiki` dashboard are not alternate canonical providers.

Firecrawl, Exa, Tavily, Serper, Browserbase stealth, and Bright Data are explicitly gated under `paid_backend_gate`: `requires_key` is true, missing configuration yields `MISSING_CONFIG`, and no silent fallback is permitted. The phase-2 review's official reference-fetch/filesystem/git candidate was also rejected for overlap with Hermes built-ins. AGPL/GPL tools and services called out by the source matrix—SearXNG, the Firecrawl engine, RSSHub, and ultimate-sitemap-parser—remain external-only and are not vendored. No credentials, absolute filesystem paths, or provider secrets are recorded here.
