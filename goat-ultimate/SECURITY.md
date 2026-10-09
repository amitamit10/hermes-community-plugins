# Security — GOAT Ultimate Router

This router skill is read-only routing; it does not implement network fetch itself. The `hermes-goat-web` plugin (ID `hermes-goat-web`, dir `goat-web`) is bounded read-only retrieval (HTTPS/443, SSRF gate, no stealth/proxy/CAPTCHA bypass). Paid backends fail closed with `MISSING_CONFIG`.

## Gate evidence (staging, not a full audit)

- Registry: `python -m unittest discover -s tests` → **11/11 PASS** (`test_registry.py` 4, `test_registry_v2.py` 7) on `registry/capabilities.json` (schema v2, 11 task classes, 11 providers, paid-gate fail-closed, fallback order `anysearch → searxng → wikipedia → duckduckgo`).
- Staging plugin (`goat-browser-staging` / `goat-public/goat-web` snapshot): `unittest` **51/51 PASS**, `scripts/fuzz_gate.py` **4,288 cases, 0 failures** (2,600 URLs, 1,683 redirects, 5 non-string, 284 userinfo), `scripts/audit_staging.py` **OK: no staging findings** — heuristic check (4 secret markers, 2 absolute-path prefixes, `.env`/`auth` names, symlinks; not a comprehensive secret scan).
- Plugin identity aligned: `goat-web/plugins/goat-web/plugin.yaml` declares `name: hermes-goat-web` (installed at `$HERMES_HOME/plugins/hermes-goat-web/`, entrypoint `__init__:register`, tools `goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`). The directory `goat-web` and ID `hermes-goat-web` are now documented as aligned; commands use `hermes-goat-web`.
- Registry mirrored: `registry/capabilities.json` (canonical) and `skills/goat-ultimate/registry/capabilities.json` (installed layout) are identical (`diff` identical, keep both for compat).
- References: `goat-packs/gate-reverify-tick2.md`, `references/qa-report.md`, `references/merge-notes.md`, `goat-browser-staging/references/qa-report.md`.

## What this does NOT claim

- No "security-reviewed" certification is claimed. The gates above are staging/heuristic only.
- No release approval. Publication or live enable (`hermes plugins enable hermes-goat-web`) requires explicit human approval and a fresh `hermes plugins validate` / `doctor` run in the install window.
- See `SKILL.md` sections “GOAT web plugin identity”, “Probe helper”, “Extended and future routes”, and “Security note” for routing, probe, and future-module (`answer_synth`/`goat_answer`, `search_filters`, `deep_verticals`) status.

## Reporting

Use the repository host's private reporting channel if enabled; otherwise a private maintainer channel linked from the project page. Include exact commit, component, reproduction, impact, and minimal PoC without secrets. Do not post exploits in public issues.
