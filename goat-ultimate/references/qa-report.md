# QA report — GOAT staging trees

Scope: local/offline verification only. Verification date: 2026-10-09. No network requests from the package, package installation, or live-system changes were performed.

## Historical audit snapshot

- The earlier `goat-browser-staging` snapshot recorded 8 `test_*.py` files and 44 unittest cases. This historical count is not the current tree count.

## Current verification

| Tree / gate | Result |
|---|---|
| `goat-browser-staging`: `goat-gate.yml` frontmatter-lint job | PASS; validated the one `SKILL.md` entrypoint. Reference Markdown is intentionally outside this frontmatter contract. |
| `goat-browser-staging`: `python3 -m unittest discover -s tests` | PASS; 56 tests across 10 `test_*.py` files. |
| `goat-browser-staging`: `python3 scripts/audit_staging.py` | PASS; `OK: no staging findings`. |
| `goat-browser-staging`: `goat-gate.yml` provenance/license job | PASS; `Provenance and license metadata checks passed.` |
| `goat-ultimate`: `python3 -m unittest discover -s tests` | PASS; 4 tests in 1 file. |

All workflow-equivalent local checks listed above are green. GitHub Actions itself was not run remotely; no repository was pushed.
