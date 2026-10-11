# QA report — GOAT staging trees (local candidate)

Branch `work/goat-v3-docs-final`, HEAD `0128a3a970d7d6e8052c985027ddad6a80b2d2a9`. Scope: local/offline only — no live install, enable, or publish. The combined contracts/wiring predecessor is staged, not committed; treat historical counts as snapshots until the parent final gate resolves the R1 regression.

## Historical snapshot vs current wiring

- Historically reported `goat-browser-staging` snapshots (e.g., 8 files/44 cases early, 10 files/56 cases later) included only the four legacy tools. Parent verified **408 existing tests** before docs integration but flagged an **R1 regression pending separate fix**.
- Current GOAT V3 (`0.2.0`) wires seven tools on four fixed official endpoints (Wikipedia Action, Crossref, GDELT, Commons). Fuzzer counts historically reported as 4,288 total (2,600 URL distinct, 1,683 redirect, 5 non-string, 284 userinfo, 0 failures) are prior runs — reproduce rather than quote.

## Current verification (reproducible, portable)

No `/opt/data`, no `PYTHONPATH`, no credentials, no network required beyond optional smoke.

```sh
git clone <repo-url> goat && cd goat

# Build and read-only bundle check
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
# ok /tmp/hermes-goat-web

# Offline unit suites (fakes, deterministic)
python3 -B -m unittest discover -s adapters -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v 2>&1 | tail -n 20

# Offline gates — confirm before claiming
python3 goat-web/scripts/fuzz_gate.py
python3 goat-web/scripts/audit_staging.py  # narrow heuristic, not a full secret scan
python3 goat-web/scripts/build_plugin_bundle.py --help
hermes --help; hermes plugins --help; hermes plugins validate --help  # read-only
hermes plugins validate /tmp/hermes-goat-web 2>&1 | head
```

Confirm actual Hermes flags (`--help`) before scripting; local candidate only — do not treat as live or published.

## Limitations not claimed

- Paid providers (Exa/Tavily/Firecrawl/Serper/You) exercised only via fake transports; Serper remains experimental/unverified.
- No live exhaust testing of all 14 providers, no microbenchmark claim, no browser extension, no self-host SearXNG activation in this candidate.
- Any historical snippet showing `limit` instead of `max_results` or omitting `ok` is invalid after V3 — see `goat-web/skills/goat-web/references/tool-schemas.md`.

Quarantined to `artifacts/docs-final/`; see exported patch manifest for the incremental change set.
