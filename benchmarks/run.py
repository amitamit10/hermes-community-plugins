#!/usr/bin/env python3
"""Offline benchmark entry: runs gate then module suites locally."""
from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = ROOT / "adapters"


def main() -> None:
    print("OFFLINE benchmarks: deterministic synthetic hosts and injected fake inputs only.")
    print("Local Python-only perf_counter_ns timing; not real provider/network/browser latency.")
    runpy.run_path(str(ADAPTERS / "bench_gate.py"), run_name="__main__")
    runpy.run_path(str(ADAPTERS / "bench_modules.py"), run_name="__main__")


if __name__ == "__main__":
    main()
