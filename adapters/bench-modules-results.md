# Goat-packs module benchmark results

- Calls per module: 200; warm-up: 20.
- All requests use deterministic injected fakes; DNS answers use an injected public-IP resolver.
- No sockets, DNS lookups, provider endpoints, or browser processes are used.
- Timing: `perf_counter_ns` per call; p50/p99 use nearest-rank; mean is arithmetic mean.
- Runtime: Python 3.13.5.

| Module | Mean (µs/call) | p50 (µs/call) | p99 (µs/call) |
|---|---:|---:|---:|
| `answer_synth` | 15.546 | 15.120 | 24.961 |
| `anysearch_adapter` | 4.004 | 3.960 | 4.640 |
| `browser_tier` | 96.582 | 95.401 | 114.521 |
| `crawl_pro` | 46.197 | 45.601 | 55.720 |
| `deep_verticals` | 13.822 | 13.560 | 21.280 |
| `donsetch_adapter` | 0.318 | 0.320 | 0.360 |
| `exa_adapter` | 2.398 | 2.360 | 2.521 |
| `firecrawl_adapter` | 29.961 | 29.441 | 40.401 |
| `free_search` | 99.158 | 97.481 | 119.241 |
| `free_stack` | 46.303 | 45.681 | 56.161 |
| `free_verticals` | 62.705 | 61.760 | 77.081 |
| `native_tier` | 15.586 | 15.360 | 20.801 |
| `rss_watcher` | 61.314 | 60.161 | 78.001 |
| `search_filters` | 24.219 | 23.800 | 35.441 |
| `serper_you_adapter` | 2.947 | 2.840 | 3.440 |
| `tavily_adapter` | 2.964 | 2.920 | 3.160 |
| `ssrf_guard` | 27.058 | 26.601 | 37.960 |
