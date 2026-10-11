# Remaining Work — GOAT V3 Candidate (concise)

> This short list is a concise testing guide for a second clean machine, not a sprawling roadmap. GOAT V3 `0.2.0` is a local candidate (branch `work/goat-v3-docs-final`, staged contracts/wiring). The parent verified **408 existing tests** before docs integration but flagged an **R1 regression pending a separate fix** — do not hardcode a final total until the parent final gate. The goal here is documentation alignment, not new code.

## Completed in this branch

- Seven closed-schema tools implemented and wired to fixed official endpoints: `request` pinned to `https://en.wikipedia.org/w/api.php`, `https://api.crossref.org/works`, `https://api.gdeltproject.org/api/v2/doc/doc`, `https://commons.wikimedia.org/w/api.php` (all with `pinned_fetch` timeout 10s / 1 MiB / 0 redirects).
- Deterministic `build_plugin_bundle.py` with `bundle-manifest.json` hashing and `_goat_v3_vendor/` shadowing; only the built `hermes-goat-web` directory is standalone.
- Registry `schema_version: 3` with 14 providers (canonical-free `anysearch`, 12 routes, 1 future-unavailable) and explicit fallback `anysearch → searxng → wikipedia → duckduckgo`.

## Verify on a clean second server (reproducible)

From a fresh `git clone` — no `/opt/data`, no `PYTHONPATH`, no credentials:

```sh
git clone <repo-url> goat && cd goat
python3 -B goat-web/scripts/build_plugin_bundle.py --help
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
python3 -B -m unittest discover -s adapters -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v 2>&1 | tail -n 20
hermes --help; hermes plugins --help; hermes plugins validate --help
hermes plugins validate /tmp/hermes-goat-web 2>&1 | head
```

Confirm actual `--help` output on that machine; do not assume `hermes plugins install` accepts local paths if your Hermes reports catalog/git only.

## What this docs pass intentionally does not claim

- No live enable, gateway restart, or publish. No `hermes plugins install` with a local directory unless an explicit approved local-install method exists for that Hermes version.
- Paid adapters (Exa/Tavily/Firecrawl/Serper/You) remain fake-transport only; Serper stays experimental/unverified.
- No microbenchmark, no browser-extension wiring, no self-host SearXNG activation — these remain research (`selfhost-matrix.md`, `searxng-notes.md`) and are not install prerequisites for this candidate.
- No assertion that every provider was tested live, no “perfect” claim, no hardened browser integration beyond what fake transports cover.

Historical 61/160/96 and early 51/51/11 snapshots in `qa-report.md` and `coverage-gaps.md` are stale — treat as history and use the commands above.

## Next step (separate, owner-approved)

Only after the parent resolves R1 and re-gates the exact tree: re-freeze baseline, run the verification block above on that exact commit, audit the built bundle, then seek explicit human approval before any `install --no-enable`, enable, or tag publication. Until then this documentation-alignment patch stays local under `artifacts/docs-final/`.
