# Hermes Community Plugins — GOAT Web Collection

A local release candidate for bounded public-web retrieval and routing on Hermes Agent. The `hermes-goat-web` plugin exposes seven closed-schema tools; `goat-ultimate` routes each task class to one canonical provider. This branch is a **local candidate (v0.2.0)**, not a published tag, release, or activated plugin.

Status: local candidate only. Do not treat this tree as installed or live. Verify on a clean second machine before any publication or enable.

## Seven tools (closed schemas, `additionalProperties: false`)

| Tool | Purpose | Key inputs | Success (`ok: true`) |
|---|---|---|---|
| `goat_search` | bounded DuckDuckGo HTML search | `query` (required), `max_results` 1..5 default 5 | `{ results: [{title, url, snippet}] }` ≤ requested |
| `goat_extract` | fetch one public HTTPS page | `url` | `{ url, final_url, status, title, text≤8000, truncated }` |
| `goat_crawl` | same-origin BFS, depth ≤2, pages ≤10 | `url`, `max_depth` 0..2 default 2, `max_pages` 1..10 default 10 | `{ pages: [{url, depth, status, title, text≤8000, truncated}] }` |
| `goat_probe` | reachability only | `url` | `{ ok, status, host }` — no body |
| `goat_answer` | deterministic extractive answer over ≤5 Wikipedia Action API snippets | `query` 1..2000 chars (non-blank), `max_results` 1..5 | `{ answer, sources: [{index, title, url}] }` numbered citations; no LLM synthesis |
| `goat_filtered_search` | same Wikipedia search with inclusive filters | `query`, `max_results`, `time_after`, `time_before`, `allowed_domains`/`denied_domains` (bare hosts, 20 max), `language` (BCP-47) | `{ results }` filtered; missing metadata excluded |
| `goat_vertical_search` | one official keyless vertical | `vertical` enum `scholar`/`news`/`images`, `query`, `max_results` | `scholar`→Crossref, `news`→GDELT, `images`→Wikimedia Commons; provider links plus per-file image licensing |

All validation, unknown fields, type errors, and policy blocks fail closed:

```
{ "ok": false, "error": { "code": "URL_BLOCKED" } }
{ "ok": false, "error": { "code": "REDIRECT_BLOCKED" } }
{ "ok": false, "error": { "code": "MISSING_CONFIG" } }
```

Only those three codes are public. No stack traces or credentials are exposed. Success envelopes always carry `ok: true`; errors never leak internals.

## Layout

- `goat-web/plugins/goat-web/` — **source template**, not installable. Imports `._goat_v3_vendor` which exists only inside a built bundle.
- `goat-web/scripts/build_plugin_bundle.py` — builds the standalone `hermes-goat-web` directory from an explicit allowlist with `bundle-manifest.json` and hash checks.
- `goat-ultimate/` — capability registry (11 task classes, 14 providers) and router skill.
- `adapters/` — provider adapters and self-host research with fake-transport unit tests (offline).

## Portable quickstart (clean machine, no network required for validation)

Prerequisites: Python 3.11+, `git`, Hermes Agent installed (for `validate` checks). No `pip install`, no `PYTHONPATH`, no credentials.

```sh
# 1. Clone
git clone <repo-url> goat && cd goat

# 2. Show bundle syntax (no install, no enable)
python3 -B goat-web/scripts/build_plugin_bundle.py --help
# usage: build_plugin_bundle.py [-h] [--output OUTPUT] [--check CHECK] [--source-root SOURCE_ROOT]

# 3. Build a fresh standalone bundle (fresh directory required)
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
ls /tmp/hermes-goat-web/bundle-manifest.json

# 4. Read-only verification of that bundle
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
# ok /tmp/hermes-goat-web

# 5. Offline tests — reproducible commands, no live plugin enable
python3 -B -m unittest discover -s adapters -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v 2>&1 | tail -n 20

# 6. Plugin manifest read-only check (isolated, no install)
# In a disposable HOME if you don't want to touch your live Hermes:
# HOME=$(mktemp -d) hermes plugins validate /tmp/hermes-goat-web 2>&1 | head
hermes plugins validate /tmp/hermes-goat-web 2>&1 | head
```

Only the built directory at `/tmp/hermes-goat-web` is standalone. `goat-web/plugins/goat-web` alone is not.

Hermes CLI reference (read-only, no install):

- `hermes plugins validate <bundle-path>` — read-only manifest + tool check
- `hermes plugins install <catalog-or-git> --ref <sha> --no-enable` — requires explicit ref; local paths require an approved local-install method
- `hermes doctor` / `hermes plugins doctor` — health checks; no enable/restart by default

Actual flags may vary by Hermes version — run `hermes --help`, `hermes plugins --help`, `hermes plugins validate --help` to confirm before scripting. Do not invent local-path support for `install` if your Hermes reports catalog/git only.

## Wiring and official endpoints

V3 wiring (`goat-web/plugins/goat-web/v3_wiring.py`) binds real adapters to fixed HTTPS endpoints and fails closed on any drift:

- Wikipedia Action API `https://en.wikipedia.org/w/api.php` for `goat_answer` / `goat_filtered_search` (extractive, not general web search)
- Crossref `https://api.crossref.org/works` for `goat_vertical_search` `scholar` (returns provider links, no abstract fetch)
- GDELT `https://api.gdeltproject.org/api/v2/doc/doc` for `news` (metadata + links)
- Commons `https://commons.wikimedia.org/w/api.php` for `images` (per-file license/credit)

`goat_search` in the legacy gate remains DuckDuckGo HTML. The three new tools do not fetch general web pages or synthesize via LLM; `time`/`language` filters exclude missing/invalid metadata without inference or refill.

## Security and error contract

Fail-closed HTTPS/443 + SSRF/DNS gate on every URL, redirect, and crawl link. Pin-checked egress for the four official endpoints (`pinned_fetch` timeout 10s, 1 MiB, 0 redirects). Three public error codes only. See `adapters/SECURITY.md` and `goat-web/PROVENANCE.md`. No comprehensive audit is claimed here; treat this as a candidate requiring independent review and explicit human approval before publication or live enable.

## Testing model

- **Fake-transport unit tests** — offline, deterministic; inject a one-argument `transport(url)` or fake Hermes callables.
- **Official-provider smoke** — opt-in only, against the four fixed endpoints above; not run by default.
- **No live key retests** for paid providers (Exa/Tavily/Firecrawl/Serper/You etc.) beyond fake-transport coverage; Serper remains experimental/unverified.
- **No microbenchmarks** claimed; fuzzer `scripts/fuzz_gate.py` is correctness, not performance.
- **Browser extension and self-host SearXNG integration** remain unimplemented research, not part of this candidate's install.

Historical QA counts in `goat-web/references/qa-report.md` and coverage/UX notes in `adapters/` are snapshots; treat them as history and reproduce with the commands above rather than relying on stale totals.

License: MIT. Not official, not audited — review before use. See `RELEASE-CANDIDATE.md` for the local candidate checklist.
