# Compatibility

- Hermes Agent: extension/plugin target. Reviewed against Hermes source HEAD `66605471e9f0b0832abbefaf625ce08e948ca540` (native runtime `3.14.7`); developer plugin guide at `https://hermes-agent.nousresearch.com/docs/developer-guide/plugins` is authoritative. Run read-only `validate`/`doctor` only through the approved installed interpreter (`-I -B -m hermes_cli.main`) with the disposable credential-free env in `adapters/QUICKSTART.md` section 2 — never the shared auto-repair launcher, never `--install-deps`.
- Python: 3.11 or newer for GOAT itself; Python standard library only, no third-party runtime dependencies. The Hermes host floor is separate.
- Operating system: Linux (portable pure-Python otherwise).
- Network: production needs direct egress with public-DNS-only answers and direct HTTPS/443 (see `adapters/QUICKSTART.md` section 0). Plain `hermes chat` / `hermes gateway run` are not preflight-protected; the supported gate is the explicit companion `goat-web/scripts/start_with_preflight.py` kept outside the bundle. Plugin `register`/import/`doctor`/`validate` never run the network check.
- Native gates: the six `test_hermes_registration.py` gates skip without `GOAT_HERMES_SOURCE_ROOT` / `GOAT_HERMES_RUNTIME_PYTHON`; skipped is not passed and not integration proof.

GOAT V3 (`0.2.0`) is a local release candidate built from this checkout only. It has not been published as a tag/release and is not activated as a live plugin. Offline fake-transport unit tests cover the seven tools and registry; official-provider smoke against the four fixed endpoints is opt-in. No live paid-provider testing or performance benchmarking is claimed for this candidate.
