# UX Notes — GOAT V3 (concise)

> Prior gaps analysis cited mismatched examples (`limit` vs `max_results`) and stale install/registry instructions. Those mismatches are fixed in this branch — every example now uses closed schemas with `ok: true` success and one sanitized error code. The remaining UX focus is portable validation, not new flows.

## Install path (what changed)

- The authoring `goat-web/plugins/goat-web/` directory is **not** a direct install — use `python3 -B goat-web/scripts/build_plugin_bundle.py --output <fresh target>` and validate the built directory.
- Registry lives at `goat-ultimate/registry/capabilities.json` (mirrored to `skills/goat-ultimate/registry/capabilities.json`); both are identical.
- Hermes commands use manifest ID `hermes-goat-web`: `hermes plugins validate <built-path>` read-only; actual `install`/`doctor` flags vary by Hermes — confirm via `hermes plugins --help` before scripting. Do not document `install` with a local directory unless your Hermes explicitly supports it.

## Example correctness

All examples in `goat-web/references/examples.md` and `goat-web/skills/goat-web/references/tool-schemas.md` now use `max_results` and `additionalProperties: false` closed arguments. Any prior snippet showing `limit`, `ok: content`, or fabricated microbenchmark output is invalid after V3 — report it rather than treating it as current.

## Self-host and browser notes

SearXNG self-host fits a small 2-vCPU VPS but remains research (`searxng-notes.md`, `selfhost-matrix.md`); no unapproved SearXNG instance activation is part of this candidate. Browser-extension wiring remains unimplemented — no live browser recovery claim.

## Security wording

Keep “candidate requiring independent review” — do not claim audited, perfect, or published. Seven tools, three sanitized codes, pinned egress, and offline fake-transport coverage are the current claims; no live exhaustive provider testing.
