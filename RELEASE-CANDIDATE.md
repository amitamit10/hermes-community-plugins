# Release Candidate — GOAT V3 `0.2.0` (Local, Not Published)

**Base**: `1311d89a76adeb3d4b56e281014991ee3a83f3f5` • **Plugin**: `hermes-goat-web` `0.2.0` • **Registry**: `schema_version: 3`.

## What this is and isn’t

- **Is**: local, offline-verifiable candidate with seven closed-schema tools pinned to four official HTTPS endpoints.
- **Is not**: a published tag/release, a Git push, or an activated live plugin. No `hermes plugins enable` or gateway restart is claimed. Any claim of “published”, “live”, or “perfectly tested” is intentionally avoided.

Confirm on your machine:

```sh
git rev-parse HEAD  # 1311d89a76adeb3d4b56e281014991ee3a83f3f5
cat goat-web/plugins/goat-web/plugin.yaml  # name: hermes-goat-web version: 0.2.0
python3 -B goat-web/scripts/build_plugin_bundle.py --help
```

## Seven tools, closed, sanitized codes

See `goat-web/skills/goat-web/references/tool-schemas.md` for the exact closed schemas (`additionalProperties: false`). Success is `{"ok": true, ...}`, failures are `URL_BLOCKED`, `REDIRECT_BLOCKED`, `MISSING_CONFIG` (`{"ok": false, "error": {"code": "..."}}`), plus `PROVIDER_BLOCKED` for provider bot-challenge blocks once the provider-sibling P1-2 fix lands (not in this baseline). Time/language filters exclude missing metadata without inference; `goat_answer` is extractive with numbered citations, not LLM synthesis.

## Portable verification (no live install)

From a fresh `git clone`, with the disposable credential-free native wrapper from `adapters/QUICKSTART.md` section 2 (`SCRATCH`/`RUNTIME`; `RUNTIME` must point at the approved installed Hermes source version — never the shared auto-repair launcher, never `--install-deps`):

```sh
git clone <repo-url> goat && cd goat
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web  # fresh dir required
hermes_readonly plugins validate /tmp/hermes-goat-web
hermes_readonly plugins doctor /tmp/hermes-goat-web --ci
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web  # ok
python3 -B -m unittest discover -s adapters -p "test_*.py" -v
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v
```

No pipes above — they would mask exit codes. No totals are quoted and no CI-green claim is made; keep full local output as the receipt. Historical QA (422 collected, 416 passed, 6 skipped at base `1311d89a`) is history, not the current modified total, and the 27 portable-bundle checks are a subset of `goat-web/tests` — never double-count them. Fuzzer `fuzz_gate.py`, `audit_staging.py`, and paid adapters beyond fake transports are not claimed as comprehensive or benchmark; `browser-extension` and `self-host SearXNG` integration remain research.

Deliberate startup only through the reviewed companion `goat-web/scripts/start_with_preflight.py` (outside the bundle), and only after separate network-startup approval — see `adapters/QUICKSTART.md` section 4. Plain `hermes chat` / `hermes gateway run` are not protected.

## Publication gates (explicit, separate)

- Build and `bundle-manifest.json` hash check passes read-only.
- Offline suites reproduced on a second clean machine for the exact pinned checkout.
- Native `validate` and `doctor --ci` pass for the built bundle path read-only.
- Explicit human approval for: (a) any repository visibility change/push/tag, (b) any live `hermes plugins install --ref <sha> --no-enable` / `enable` (ref installs without enabling), (c) any network smoke against official endpoints, (d) any native status/readback/profile install, (e) any service change pointing at the startup companion. Until then this patch stays local and is not pushed or installed.
