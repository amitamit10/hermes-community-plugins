# Offline benchmarks (Python / stdlib only)

`benchmarks/run.py` is an offline, stdlib-only entry point. It prints an
OFFLINE banner, then runs the existing suites sequentially:

1. `adapters/bench_gate.py`
2. `adapters/bench_modules.py`

No network, DNS, sockets, provider endpoints, browser processes, extra
dependencies, parallelism, or benchmarking framework are involved.

## Run

From the checkout root:

```sh
python3 -B benchmarks/run.py
```

Cwd-independent (works from any directory). Set `GOAT_PACKS` to the absolute
checkout directory:

```sh
GOAT_PACKS="<absolute checkout directory>"
python3 -B "$GOAT_PACKS/benchmarks/run.py"
```

Focused existing suites using the same checkout variable:

```sh
python3 -B "$GOAT_PACKS/adapters/bench_gate.py"
python3 -B "$GOAT_PACKS/adapters/bench_modules.py"
```

## Interpreting numbers

- Module mean/p50/p99 and gate median/p95 are real `perf_counter_ns`
  measurements of local fake-input work on this machine.
- They are NOT provider throughput/latency, network, browser
  startup/rendering, or service-quality measurements.
- No sample figures are published here; run the entry locally for numbers.

Optional focused regression for this entry:

```sh
python3 -m unittest discover -s adapters -p "test_bench_gate.py" -v
```
