# Hermes Community Plugins — GOAT Web Collection

A public, security-reviewed collection of web search, extraction, crawl, and
browser-recovery building blocks for Hermes Agent, plus a capability-router
layer that maps every task class to exactly one canonical tool.

Free-first: keyless adapters (DuckDuckGo, Wikipedia, AnySearch anonymous,
SearXNG client) work with no API keys. Paid providers (Exa, Tavily,
Firecrawl, Serper, You.com) sit behind `requires_key` and fail closed with
`MISSING_CONFIG` — never a silent fallback. Only Firecrawl is self-hostable
(AGPL); the rest are proprietary SaaS. SearXNG fits a small 2-vCPU VPS.

## Layout

- `goat-web/` — fail-closed URL gate (SSRF/DNS-pinning), 4 tools
  (`goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`), skill docs,
  56 unit tests + 4,288-case fuzzer, CI gate. Validate:
  `hermes plugins validate goat-web/plugins/goat-web`.
- `goat-ultimate/` — machine-readable capability registry (11 task classes),
  router skill, tests.
- `adapters/` — provider adapters (free + paid + self-host research), each
  with fake-transport unit tests. 96/96 green.

## Security

Fail-closed SSRF gate, pinned-HTTPS egress, no credentials in code, public
error contract (`URL_BLOCKED` / `REDIRECT_BLOCKED` / `MISSING_CONFIG`).
See `adapters/SECURITY.md` and `goat-web/PROVENANCE.md` (pinned SHAs).

License: MIT. Not official, not audited — review before use.
