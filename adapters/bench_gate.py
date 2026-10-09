#!/usr/bin/env python3
# Measure URL-gate latency on deterministic synthetic hosts without network access.
from __future__ import annotations

import math
import platform
import statistics
import time
import types
from pathlib import Path

REFERENCE = Path(__file__).resolve().parent.parent / "goat-browser-staging" / "plugins" / "goat-web" / "url_gate.py"
COUNT = 10_000
WARMUP = 100


def load_gate():
    if not REFERENCE.is_file():
        raise FileNotFoundError(f"URL gate reference is missing: {REFERENCE}")
    source = REFERENCE.read_text(encoding="utf-8")
    module = types.ModuleType("bench_url_gate_target")
    exec(compile(source, str(REFERENCE), "exec"), module.__dict__)
    return module


def measure(function, values):
    for value in values[:WARMUP]:
        function(value)
    samples = []
    started = time.perf_counter_ns()
    for value in values:
        call_started = time.perf_counter_ns()
        function(value)
        samples.append(time.perf_counter_ns() - call_started)
    elapsed_ns = time.perf_counter_ns() - started
    return samples, elapsed_ns


def nearest_rank(values, percentile):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def main():
    gate = load_gate()
    hosts = [f"bench-{index:05d}.example.com" for index in range(COUNT)]
    urls = [f"https://{host}/synthetic/{index}?case={index}" for index, host in enumerate(hosts)]
    redirects = [
        (host, f"/next/{index}?case={index}", 0)
        for index, host in enumerate(hosts)
    ]

    # Validate every generated case outside the timed sections.
    for url in urls:
        if gate.check_url(url) != (True, gate.OK):
            raise RuntimeError(f"Unexpected check_url result for {url}")
    for redirect in redirects:
        if gate.check_redirect(*redirect) != (True, gate.OK):
            raise RuntimeError(f"Unexpected check_redirect result for {redirect[0]}")

    url_samples, url_elapsed = measure(gate.check_url, urls)
    redirect_samples, redirect_elapsed = measure(lambda redirect: gate.check_redirect(*redirect), redirects)

    print("# URL gate benchmark results")
    print()
    print(f"- Synthetic hosts per operation: {COUNT:,} unique HTTPS `.example.com` addresses.")
    print(f"- Warm-up: {WARMUP} calls per operation; all measured cases validated successfully.")
    print("- Timing: per-call `perf_counter_ns`; p95 uses nearest-rank; no DNS or network access.")
    print(f"- Runtime: Python {platform.python_version()}.")
    print()
    print("| Operation | Median (µs/call) | p95 (µs/call) | Total measured (ms) | Throughput (calls/s) |")
    print("|---|---:|---:|---:|---:|")
    for name, samples, elapsed in (
        ("`check_url`", url_samples, url_elapsed),
        ("`check_redirect`", redirect_samples, redirect_elapsed),
    ):
        median_us = statistics.median(samples) / 1_000
        p95_us = nearest_rank(samples, 0.95) / 1_000
        total_ms = elapsed / 1_000_000
        throughput = COUNT / (elapsed / 1_000_000_000)
        print(f"| {name} | {median_us:.3f} | {p95_us:.3f} | {total_ms:.3f} | {throughput:,.0f} |")


if __name__ == "__main__":
    main()
