# QA report — goat-browser-staging

Scope: current staging tree; local/offline checks only. Unit tests use fakes; the deterministic URL fuzzer does not contact the network. No credentials or secrets were used.

## Current inventory

- 10 `test_*.py` files; 61 unittest cases discovered.

## Current verification

| Gate | Result |
|---|---|
| `python3 -m unittest discover -s tests -v` | PASS, exit 0; 61 tests. |
| `python3 scripts/fuzz_gate.py` | PASS, exit 0; 4,288 total cases, 2,600 URL cases (2,600 distinct), 284 userinfo URL cases, 1,683 redirect cases, 0 failures. |
| `python3 scripts/audit_staging.py` | PASS, exit 0; `OK: no staging findings`. This is a narrow heuristic, not a comprehensive secret scan or release gate. |
| Provenance/license metadata check from `goat-gate.yml` | PASS; `Provenance and license metadata checks passed.` |
| Exact skill-reference frontmatter check from `goat-gate.yml` | PASS; the current gate scans `SKILL.md` files only. |

The output contracts for search, extract, and crawl are exercised offline by `tests/test_goat_tools.py`. Extract returns the requested URL, final validated URL, status, title, normalized readable text, and a text truncation flag. Crawl returns page records with depth/title/text and no undocumented crawl-wide fields.
