# Fresh adversarial re-audit

**Verdict: NO-GO.** Four blocking findings remain (three security/contract issues and one publication gate). This review is read-only; only this report is written.

## Scope and verification

Reviewed the current enumerated contents of `goat-browser-staging` (31 files, including plugin code/manifests, skill references, scripts, tests, docs, license/provenance, and the hidden workflow files), `goat-ultimate` (8 files: skill, registry, tests, references, license/provenance), and `goat-packs` (38 files: adapters, tiers, tests, coverage/registry/security/fallback and SearXNG docs). `goat-ultimate/registry/live-inventory.json`, and a top-level README/LICENSE/PROVENANCE in `goat-packs`, are absent. The existing `goat-packs/readme-polish.md` is only a proposal.

Verified offline: browser staging unit tests pass (56, per current QA report; command exit 0); goat-ultimate tests pass (4; exit 0); goat-packs tests pass (96; exit 0). Browser fuzz gate: 4,288 cases, 0 failures; `audit_staging.py`: `OK: no staging findings`. No live network access was used. A targeted scan for common API-token/private-key patterns found no matches; this is not an exhaustive secret scan. The core browser plugin’s default `pinned_fetch` path does resolve/validate and pin public IPs; the blockers below are primarily in separate `goat-packs` paths that do not use that enforcement.

## Blocking findings

### B1 — SSRF/DNS rebinding boundary is not enforced across pack fetch paths

`goat-packs/free_search.py:63-95,108-136` validates URL syntax and literal IPs but does not resolve hostnames or pin the connected address. Its default `urllib` transport resolves independently, and `_SafeRedirectHandler` only repeats the syntactic check. A hostname (including a redirect hostname) can therefore resolve/rebind to a private, loopback, link-local, or metadata address after validation. It also accepts HTTP, unlike `SECURITY.md:13-17` (HTTPS/443 only).

Other exposed pack boundaries are weaker: `browser_tier.py:75-102,199-214,264-294` uses the syntactic `check_url` and treats browser request/redirect logs as optional evidence. Reproduction: a browser callable that returned a successful response without invoking `request_gate` or providing request logs was accepted as `{ok: True}`. `native_tier.py:75-88,165-191` checks only scheme/host syntax and delegates fetches; an offline spy confirmed `native_extract("https://127.0.0.1/", ...)` returns success and passes the private URL to the injected extractor. `AnySearchClient.extract` only checks HTTP(S)+hostname, while Tavily/Firecrawl extract/crawl accept arbitrary nonempty URL strings and submit them to remote fetch services.

**Required before integration:** route actual HTTP requests through the pinned public-IP transport; enforce equivalent egress restrictions for CDP/native extractors (not a cooperative callback alone); validate provider-fetch inputs against the documented public HTTPS policy or document and verify a provider-side SSRF guarantee. Add DNS rebinding, private redirect, and gate-bypass tests for these pack paths.

### B2 — Silent provider fallback violates the documented fail-closed/privacy policy

`goat-packs/free_stack.py:595-645` continues to Wikipedia and DuckDuckGo after *any* SearXNG error, including `MISSING_CONFIG`; there is no policy flag to prohibit the fallback or a reason in the result. Offline reproduction with `instance_url=None` and fake transports returned a DuckDuckGo success after calling Wikipedia and DDG. This sends a query to different external providers despite the selected SearXNG configuration being unavailable. It conflicts with `SECURITY.md:7,21` and `search-fallback-chain.md:8-12`, which require missing configuration to stop and prohibit silent provider/local/free-tier fallback.

Stop immediately on `MISSING_CONFIG`; permit other fallback only when explicitly requested by policy, and return the source plus the reason for each transition.

### B3 — Registered search schema invokes an uncaught argument error

`plugins/goat-web/__init__.py:11-16` advertises `goat_search.max_results`, but `plugins/goat-web/goat_tools.py:257` accepts `limit` (also the documented field in `tool-schemas.md:9-13`). `_json_handler` at `__init__.py:35-38` expands tool arguments directly and does not catch binding errors. Reproduction calling the registered handler with `max_results=2` raises `TypeError: goat_search() got an unexpected keyword argument 'max_results'` instead of returning the public error contract. The schema also omits `additionalProperties: false` despite the strict-input contract at `tool-schemas.md:3`; documented crawl controls (`max_depth`, `max_pages`) are not described in the registered schema.

Align schema and handler names, declare strict properties (including documented crawl fields), and validate/map bad arguments before dispatch so no `TypeError` escapes.

### B4 — No standalone license/provenance for `goat-packs`

The adapters and tier implementations are in a separate pack directory with no `LICENSE` or `PROVENANCE.md`; neighboring MIT files in the other staging trees do not automatically license this directory. This blocks independent publication/distribution until the pack’s license and source/attribution record are established. This finding does not assert that third-party code was copied.

## Minor findings

- **Stale inventory counts and missing source:** `coverage-notes.md:5-8,16` reports 246 total / 172 unmapped and excludes `parallel-subagent-orchestration`, while `skill-coverage.json:7,21-22,1258-60,1275-84` has 247 assignments / 74 mapped / 173 unmapped and includes it. Its source list points to the absent `goat-ultimate/registry/live-inventory.json`; `inventory-delta.md` also relies on that missing file. Refresh counts and restore or remove the referenced source before treating the coverage artifact as reproducible.
- **Unbounded input buffers:** `free_search.py:127-136` reads complete success/error response bodies without a byte cap; `rss_watcher.py:46-57,149-163` parses the full injected feed body with `ET.fromstring` without a size limit. This conflicts with the resource-bound requirement in `SECURITY.md:17` and can exhaust memory on oversized responses.
- **Stale/conflicting docs:** `references/review-luna.md` still says the four handlers are missing and DNS enforcement is absent in the old tree, despite current implementations and current QA results; mark it historical/superseded. `readme-polish.md:27-29` says goat-ultimate has no `PROVENANCE.md`, but it exists. Also `search-fallback-chain.md:5-8` names AnySearch canonical while `goat-ultimate/registry/capabilities.json:35-46` still names `goat_search`; resolve the routing decision. The browser README’s 51-test/9-file count is explicitly labeled as an earlier snapshot and points to the current 56-test QA report, so it is not itself stale.
- **Environment-specific absolute paths:** `donsetch_adapter.py:21`, `bench_gate.py:12`, and `skill-coverage.json:4-5` contain `/opt/data/...` paths (the JSON also points to the missing inventory). These are not credentials, but make the pack nonportable and expose local layout. Use relative/configurable references where appropriate.
- **Provenance completeness:** browser `PROVENANCE.md` has an MIT license and original-work statement, but its component table does not list the newly added `goat_tools.py`, `adapters.py`, `__init__.py`, and manifests individually. The active `plugin.yaml` entrypoint and four tool names do match the implementation; the legacy JSON manifest also points to its no-argument `goat_tools.register` entrypoint. Document the dual loader contracts and account for the new files in provenance.

## Disposition

Do not treat the passing suites/fuzz gate as release clearance. Close B1–B3 and establish B4’s licensing/provenance boundary, then rerun the gates against the final source tree.