# Compatibility

- Hermes Agent: extension/plugin target (read-only `hermes plugins validate` available offline; exact flags via `hermes --help`).
- Python: 3.11 or newer; Python standard library only, no third-party runtime dependencies.
- Operating system: Linux (portable pure-Python otherwise).

GOAT V3 (`0.2.0`) is a local release candidate built from this checkout only. It has not been published as a tag/release and is not activated as a live plugin. Offline fake-transport unit tests cover the seven tools and registry; official-provider smoke against the four fixed endpoints is opt-in. No live paid-provider testing or performance benchmarking is claimed for this candidate.
