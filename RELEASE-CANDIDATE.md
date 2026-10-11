# Release Candidate — GOAT V3 `0.2.0` (Local, Not Published)

**Branch**: `work/goat-v3-docs-final` @ `0128a3a970d7d6e8052c985027ddad6a80b2d2a9` • **Plugin**: `hermes-goat-web` `0.2.0` • **Registry**: `schema_version: 3` • **Staged wiring**: predecessor combined contracts/wiring staged, not committed.

## What this is and isn’t

- **Is**: local, offline-verifiable candidate with seven closed-schema tools pinned to four official HTTPS endpoints. The combined contracts/wiring predecessor is **STAGED, not committed** — do not alter that staged baseline.
- **Is not**: a published tag/release, a Git push, or an activated live plugin. No `hermes plugins enable` or gateway restart is claimed. Any claim of “published”, “live”, or “perfectly tested” is intentionally avoided.

Confirm on your machine:

```sh
git rev-parse HEAD  # 0128a3a970d7d6e8052c985027ddad6a80b2d2a9
cat goat-web/plugins/goat-web/plugin.yaml  # name: hermes-goat-web version: 0.2.0
python3 -B goat-web/scripts/build_plugin_bundle.py --help
```

## Seven tools, closed, three sanitized codes

See `goat-web/skills/goat-web/references/tool-schemas.md` for the exact closed schemas (`additionalProperties: false`). Success is `{"ok": true, ...}`, failures are exactly `URL_BLOCKED`, `REDIRECT_BLOCKED`, `MISSING_CONFIG` (`{"ok": false, "error": {"code": "..."}}`). Time/language filters exclude missing metadata without inference; `goat_answer` is extractive with numbered citations, not LLM synthesis.

## Portable verification (no live install)

From a fresh `git clone` with a disposable `HOME`/`HERMES_HOME`:

```sh
git clone <repo-url> goat && cd goat
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web  # ok
python3 -B -m unittest discover -s adapters -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v 2>&1 | tail -n 20
hermes --help; hermes plugins --help; hermes plugins validate --help  # confirm flags on your Hermes
hermes plugins validate /tmp/hermes-goat-web 2>&1 | head
```

Parent verified **408 tests** before docs integration but flagged **R1 regression pending separate fix** — prefer the commands above over a hardcoded total until the parent final gate. Fuzzer `fuzz_gate.py`, `audit_staging.py`, and paid adapters beyond fake transports are not claimed as comprehensive or benchmark; `browser-extension` and `self-host SearXNG` integration remain research.

## Publication gates (explicit, separate)

- Build and `bundle-manifest.json` hash check passes read-only.
- Offline suites reproduced on a second clean machine for the exact pinned checkout.
- `hermes plugins validate` passes for the built bundle path read-only.
- Explicit human approval for: (a) any repository visibility change/push/tag, (b) any live `hermes plugins install --no-enable` / `enable` with pinned `--ref`, (c) any network smoke against official endpoints. Until then this patch stays local under `artifacts/docs-final/` and is not pushed or installed.
