# Test and Coverage Notes (current branch)

> Historical counts in earlier maps (23 modules, 177 tests, 56 tests, 4 tests, bench 22/19 gaps) are history. As of `work/goat-v3-docs-final` the parent verified **408 existing tests** before docs integration with an **R1 regression pending a separate fix**. Do not quote a final total until the parent final gate. Use reproducible commands below.

## Reproducible checks (portable, offline)

```sh
git clone <repo-url> goat && cd goat
python3 -B -m unittest discover -s adapters -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 goat-web/scripts/fuzz_gate.py   # correctness, offline; historical 4,288-case run is prior snapshot
```

In a fresh `/tmp` scratch the portable bundle gate is:

```sh
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web  # ok
```

One `test_portable_bundle` failure in a fresh scratch (missing approved standalone bundle path) is expected outside the staged approval; the `ok` check above is the portable readback.

## What is covered vs not

- **Covered**: fake-transport unit suites for closed schemas, URL/redirect gates, answer synthesis ranking/citation, domain/time/language filters, three vertical metadata mappers, pinned official transports.
- **Not in this candidate**: live paid-provider retests, exhaustive real-endpoint smoke (opt-in only), microbenchmarks, browser-extension or self-host end-to-end. The earlier `bench_gate.py` / `bench-results.md` fuzzer measures correctness, not performance — do not present as benchmark coverage, and remove any fabricated small-sample microbenchmark snippets from examples.

No coverage perfection is claimed. Reproduce on a second clean server via the commands above rather than quoting stale per-module gap tables.
