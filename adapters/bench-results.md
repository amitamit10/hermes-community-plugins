# URL gate benchmark results

- Synthetic hosts per operation: 10,000 unique HTTPS `.example.com` addresses.
- Warm-up: 100 calls per operation; all measured cases validated successfully.
- Timing: per-call `perf_counter_ns`; p95 uses nearest-rank; no DNS or network access.
- Runtime: Python 3.13.5.

| Operation | Median (µs/call) | p95 (µs/call) | Total measured (ms) | Throughput (calls/s) |
|---|---:|---:|---:|---:|
| `check_url` | 18.520 | 19.321 | 195.188 | 51,233 |
| `check_redirect` | 51.161 | 60.201 | 551.412 | 18,135 |
