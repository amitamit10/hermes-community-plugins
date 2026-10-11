# Registry v2 — Implemented (GOAT V3 `0.2.0`)

> This file was planning notes for `schema_version: 1` → `2`. As of `work/goat-v3-docs-final` the transition is implemented as `schema_version: 3` with `providers[]` entries. Earlier tables showing six desired entries are now history — the registry counts below are the current implementation.

## Current registry shape (authoritative at `goat-ultimate/registry/capabilities.json`)

- `schema_version: 3`, `counts: {task_classes: 11, providers: 14, by_provider_classification: {canonical-free: 1, route: 12, future-unavailable: 1}}`.
- Capabilities remain 11 task classes; `providers` list is separate (do not conflate provider count with capability count).
- `paid_backend_gate: {requires_key: true, missing_config_error: "MISSING_CONFIG", on_missing_config: "fail_closed_no_fallback", providers: ["Firecrawl","Exa","Tavily","Serper","Browserbase stealth","Bright Data"]}`.

## Provider entries (concise)

| id | classification | capabilities | requires_key | notes |
|---|---|---|---|---|
| `anysearch` | `canonical-free` | `web-search` | false (`ANYSEARCH_API_KEY` optional) | free canonical target |
| `searxng` | `route` | `web-search` | false | self-host-optional free fallback |
| `wikipedia` | `route` | `web-search` | false | keyless fallback |
| `duckduckgo` | `route` | `web-search` | false | keyless final fallback |
| `tavily` | `route` | `web-search` | true | `MISSING_CONFIG` → fail closed, no fallback |
| `exa` | `route` | `web-search` | true | same gate |
| `firecrawl` | `route` | `web-search` | true | same |
| `serper` | `route` | `web-search` | true | same — endpoint/auth still unverified until first-party doc check |
| `browserbase-stealth` | `route` | `browser` | true | same gate, not standalone web-search |
| `bright-data` | `route` | — | true | same |
| `donsetch` | `future-unavailable` | `web-search` | false | not routable |
| `crossref` | `route` | `web-search` | false | vertical scholar backing |
| `gdelt` | `route` | `web-search` | false | vertical news backing |
| `wikimedia-commons` | `route` | `web-search` | false | vertical images backing |

`You.com` remains outside the four web-search paid gate entries tracked here; do not add it to the gate without a new scoped record. Do not use a You MCP profile to bypass a keyed adapter’s `requires_key`.

## Invariants preserved

- `requires_key: true` providers carry `missing_config_error: "MISSING_CONFIG"` and `on_missing_config: "fail_closed_no_fallback"` per entry — do not rely on a global default.
- Only `anysearch` is `canonical-free`; paid routes require explicit selection + key.
- Free fallback order is fixed: `anysearch → searxng → wikipedia → duckduckgo`.
- Re-validate `counts` and `schema_version` only by counting the actual entries after edits.
