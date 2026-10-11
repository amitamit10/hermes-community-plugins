# GOAT V3 — Dry Run and Candidate Checklist

Branch `work/goat-v3-docs-final`, HEAD `0128a3a970d7d6e8052c985027ddad6a80b2d2a9`. Local candidate `0.2.0` only — not a published release/tag or activated plugin. No live `hermes skills install`, `hermes plugins install`, gateway restart, or repository push is performed in this documentation pass.

## What GOAT V3 is

- `goat-ultimate` — routing skill + registry `capabilities.json` (11 task classes, 14 providers, schema_version 3).
- `hermes-goat-web` — built plugin `0.2.0` from `goat-web/scripts/build_plugin_bundle.py` exposing seven tools: `goat_search`, `goat_extract`, `goat_crawl`, `goat_probe`, `goat_answer`, `goat_filtered_search`, `goat_vertical_search`.

The authoring directory `goat-web/plugins/goat-web` is a template; only `build_plugin_bundle.py --output <fresh target>` output is standalone.

## Dry run performed (offline, disposable, isolated)

Executed in a fresh `/tmp` scratch with no network, no credentials, no shared home writes, and no dependency installs:

```sh
python3 -B goat-web/scripts/build_plugin_bundle.py --help
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web  # ok
python3 -B -m unittest discover -s adapters -p "test_*.py"
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py"
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py"
# plus hermes CLI help read-only where available (before touching live home)
```

Parent verified **408 tests** before docs integration; **R1 regression pending separate fix**. One `test_portable_bundle` failure in a fresh scratch (missing approved standalone bundle path) is expected outside the staged approval — the deterministic `bundle-manifest.json` `ok` check is the gate here. Treat all verification as local candidate, not release approval.

## GO vs NO-GO checklist before any enable or publish

1. Re-run the exact commands above on a second clean machine from a fresh `git clone` with a fresh `HOME`/`HERMES_HOME` isolation.
2. Confirm Hermes flags read-only: `hermes --help`, `hermes plugins --help`, `hermes plugins validate --help`, then `hermes plugins validate /tmp/hermes-goat-web` and `hermes doctor` on the built bundle — no install or enable yet.
3. Run `hermes plugins install <catalog-or-git> --ref <sha> --no-enable` only with an explicit pinned ref; if your Hermes reports catalog/git only, do not assume local-path install — use an approved local-install method or stop.
4. Verify `bundle-manifest.json` hashes against the allowlist (copy drift → `stale bundle copy` error).
5. Keep `adapters/answer_synth.py`, `search_filters.py`, `free_verticals.py` as helpers — they are registered only via `v3_wiring` onto the four pinned official endpoints, not as loose provider drops.

## Portable install sketch (after explicit approval only)

```sh
git clone <repo-url> goat && cd goat
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
hermes plugins validate /tmp/hermes-goat-web
# staged → disabled install → readback → separate enable step
# hrmes skills: two skills only, no --force, no bulk sync
# hrmes plugins: one id hermes-goat-web only; keep MCP disabled single donsetch_hardened
hermes skills list; hermes plugins list --json; hermes mcp list
```

## What not to touch live

- Do not overwrite existing skills/plugins with `--force` or bulk `update`; snapshot hashes of the existing home before any write.
- Do not add/modify MCP, edit `config.yaml` / `.env` / `auth.json`, sessions, or memories.
- Do not enable paid backends or start network services without separate approval.

Historical Hebrew rehearsal notes describing `goat-browser-staging`/`goat-packs` counts and `246/247` baseline deltas are superseded by this V3 candidate’s `408 tests verified + R1 pending` state — keep that history out of current claims and reproduce via the commands above.
