# QA report — goat-web (local candidate)

Branch `work/goat-v3-docs-final`, HEAD `0128a3a970d7d6e8052c985027ddad6a80b2d2a9`. Scope: local/offline checks only. No live Hermes install, enable, or network publish was performed for this documentation pass. The combined contracts/wiring predecessor is staged, not committed — do not treat staged baseline counts as final.

## What is verified here vs historically reported

- **Current wiring**: seven tools (`goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`, `goat_answer`, `goat_filtered_search`, `goat_vertical_search`) registered via `goat-web/plugins/goat-web/__init__.py` + `v3_wiring.py` onto fixed official endpoints. Only the built `hermes-goat-web` directory is standalone.
- **Historical `goat-browser-staging` counts** cited in `2026-10-09` snapshots (e.g., 61 tests, 51 plugin cases, fuzz 4,288 cases with 2,600 URL / 1,683 redirect / 284 userinfo / 5 non-string) are history. The parent verified **408 existing tests** before docs integration but flagged an **R1 regression pending separate fix** — do not hardcode a final total until the parent final gate.

## Reproducible commands (portable, no `PYTHONPATH`, no `/opt/data`)

Clone on a second clean machine, then:

```sh
git clone <repo-url> goat && cd goat

# Build the standalone bundle (fresh directory required)
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
# ok /tmp/hermes-goat-web

# Offline unit suites (fakes, no keys, no network)
python3 -B -m unittest discover -s adapters -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v 2>&1 | tail -n 20

# Fuzzer and staging audit (deterministic, offline)
python3 goat-web/scripts/fuzz_gate.py
python3 goat-web/scripts/audit_staging.py

# Read-only Hermes check (isolated, no install or enable)
# Confirm your Hermes flags first: hermes --help; hermes plugins --help
hermes plugins validate /tmp/hermes-goat-web 2>&1 | head
hermes --help; hermes plugins --help; hermes plugins validate --help
```

Prefer these commands over quoted historical totals. Treat any prior snippet that shows `limit` instead of `max_results` or omits `ok` as invalid after the V3 mapping — see `goat-web/references/examples.md` and `tool-schemas.md` for the current contract.

## Inventory (this tree)

- Source template: `goat-web/plugins/goat-web/` (7 files + `plugin.yaml`) — requires build to become standalone.
- Built bundle: deterministic `bundle-manifest.json` covering `LICENSE`, `VENDOR-LICENSE`, `VENDOR-PROVENANCE.md`, 5 plugin top-levels, 7 vendored `_goat_v3_vendor/*.py`, and generated `_goat_v3_vendor/__init__.py`.
- No live plugin enable, MCP change, or gateway restart was performed in this pass.

## Limitations explicitly not claimed

- Not all providers tested live (paid adapters use fake transports only; Serper unverified).
- No microbenchmark claimed; fuzzer is correctness.
- Browser-extension and self-host SearXNG integration remain research, not part of this candidate.
- No perfection, no published release/tag, no comprehensive secret scan beyond the narrow heuristic in `audit_staging.py`.

Report quarantined to `artifacts/docs-final/` ownership; see the exported docs-only patch manifest for the incremental change set.
