#!/usr/bin/env python3
from __future__ import annotations

import importlib
import importlib.util
import json
import math
import platform
import statistics
import sys
import time
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL_GATE_REFERENCE = Path(__file__).resolve().parents[1] / "goat-web" / "plugins" / "goat-web" / "url_gate.py"
MODULES = (
    "answer_synth", "anysearch_adapter", "browser_tier", "crawl_pro",
    "deep_verticals", "donsetch_adapter", "exa_adapter", "firecrawl_adapter",
    "free_search", "free_stack", "free_verticals", "native_tier",
    "rss_watcher", "search_filters", "serper_you_adapter", "tavily_adapter",
    "ssrf_guard",
)
ITERATIONS = 200
WARMUP = 20
PUBLIC_IP = "93.184.216.34"


class FakeTransport:
    # Deterministic injected transport; never opens a socket.
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if callable(self.response):
            return self.response(*args, **kwargs)
        return self.response


def _resolver(host, port, **kwargs):
    return [PUBLIC_IP]


def _load_url_gate():
    if not URL_GATE_REFERENCE.is_file():
        raise FileNotFoundError("URL gate reference is missing: " + str(URL_GATE_REFERENCE))
    spec = importlib.util.spec_from_file_location("url_gate", URL_GATE_REFERENCE)
    if spec is None or spec.loader is None:
        raise ImportError("Could not load URL gate reference: " + str(URL_GATE_REFERENCE))
    module = importlib.util.module_from_spec(spec)
    sys.modules["url_gate"] = module
    spec.loader.exec_module(module)


def _load_modules():
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    _load_url_gate()
    modules = {}
    import_errors = {}
    for name in MODULES:
        try:
            modules[name] = importlib.import_module(name)
        except Exception as exc:
            import_errors[name] = exc
    if import_errors:
        details = ", ".join(
            name + " (" + type(error).__name__ + ")"
            for name, error in import_errors.items()
        )
        first_error = next(iter(import_errors.values()))
        raise ImportError("Could not import pack module(s): " + details) from first_error
    return modules


def _is_ok(result):
    return isinstance(result, Mapping) and result.get("ok") is True


def _build_cases():
    modules = _load_modules()
    cases = {}

    def add(name, operation, validator):
        cases[name] = (operation, validator)

    synth_result = {"results": [{
        "title": "Offline fixture",
        "url": "https://example.test/article",
        "snippet": "Offline fixture content is deterministic and synthetic.",
    }]}
    add("answer_synth", lambda: modules["answer_synth"].goat_answer(
        "offline fixture", search=lambda query: synth_result
    ), lambda result: isinstance(result, Mapping) and bool(result.get("answer")))

    rpc_transport = FakeTransport({"status": 200, "body": {
        "jsonrpc": "2.0", "id": 1,
        "result": {"content": [{"type": "text", "text": "offline fixture"}]},
    }})
    anysearch = modules["anysearch_adapter"].AnySearchClient(transport=rpc_transport)
    add("anysearch_adapter", lambda: anysearch.search("offline fixture"), _is_ok)

    browser_transport = FakeTransport({
        "status": 200, "body": "Synthetic public page content for an offline benchmark."
    })
    browser = modules["browser_tier"].BrowserTier(
        transport=browser_transport, resolver=_resolver
    )
    add("browser_tier", lambda: browser.fetch("https://example.test/article"), _is_ok)

    def crawl_response(url):
        if url.endswith("/sitemap.xml"):
            return {"status": 404, "body": ""}
        return {"status": 200, "body": "<html><body>Offline fixture.</body></html>"}

    crawl_transport = FakeTransport(crawl_response)
    add("crawl_pro", lambda: modules["crawl_pro"].crawl_pro(
        "https://example.test/", crawl_transport, respect_robots=False
    ), _is_ok)

    cve = {"id": "CVE-2024-12345", "descriptions": [
        {"lang": "en", "value": "Synthetic benchmark record"}
    ]}
    deep_transport = FakeTransport({"totalResults": 1, "vulnerabilities": [{"cve": cve}]})
    add("deep_verticals", lambda: modules["deep_verticals"].nvd_cve_lookup(
        "CVE-2024-12345", transport=deep_transport
    ), lambda result: isinstance(result, Mapping) and result.get("found") is True)

    donsetch_module = modules["donsetch_adapter"]
    donsetch = donsetch_module.DonsetchAdapter(binary_checker=lambda path: False)
    add("donsetch_adapter", donsetch.check, lambda result:
        isinstance(result, Mapping)
        and result.get("error") == donsetch_module.MISSING_CONFIG)

    exa_transport = FakeTransport({"status": 200, "body": {"results": [{"id": "fixture"}]}})
    exa = modules["exa_adapter"].ExaClient(
        api_key="offline-benchmark-placeholder", transport=exa_transport
    )
    add("exa_adapter", lambda: exa.search("offline fixture", num_results=1), _is_ok)

    firecrawl_transport = FakeTransport({"status": 200, "body": {
        "success": True, "data": {"markdown": "Offline fixture."}
    }})
    firecrawl = modules["firecrawl_adapter"].FirecrawlClient(
        "offline-benchmark-placeholder", firecrawl_transport, resolver=_resolver
    )
    add("firecrawl_adapter", lambda: firecrawl.scrape(
        "https://example.test/article"
    ), _is_ok)

    opensearch_payload = ["offline fixture", ["Offline Fixture"],
        ["Synthetic page."], ["https://en.wikipedia.org/wiki/Fixture"]]
    free_search_transport = FakeTransport({
        "status": 200, "body": json.dumps(opensearch_payload)
    })
    add("free_search", lambda: modules["free_search"].wikipedia_search(
        "offline fixture", transport=free_search_transport, resolver=_resolver
    ), _is_ok)

    wiki_payload = {"query": {"search": [{
        "title": "Offline Fixture", "pageid": 1, "snippet": "Synthetic page."
    }]}}
    free_stack_transport = FakeTransport(json.dumps(wiki_payload))
    add("free_stack", lambda: modules["free_stack"].wikipedia_search(
        "offline fixture", transport=free_stack_transport
    ), _is_ok)

    crossref_payload = {"message": {"items": [{
        "DOI": "10.1000/demo", "title": ["Offline fixture paper"],
        "author": [{"given": "Ada", "family": "Example"}],
        "published-print": {"date-parts": [[2024, 2, 3]]},
        "container-title": ["Synthetic Journal"],
        "URL": "https://doi.org/10.1000/demo",
    }]}}
    vertical_transport = FakeTransport({"body": json.dumps(crossref_payload)})
    add("free_verticals", lambda: modules["free_verticals"].scholar_search(
        "offline fixture", transport=vertical_transport
    ), _is_ok)

    native_payload = {"data": {"web": [{
        "title": "Offline fixture", "url": "https://example.test/article",
        "description": "Synthetic result content.",
    }]}}
    native = modules["native_tier"].NativeTier(
        web_search=lambda query, limit: native_payload
    )
    add("native_tier", lambda: native.search("offline fixture"), _is_ok)

    class FeedTransport:
        def __init__(self):
            self.sequence = 0
            self.calls = 0

        def __call__(self, url):
            self.sequence += 1
            self.calls += 1
            body = (
                "<rss version=\"2.0\"><channel><item>"
                "<guid>fixture-" + str(self.sequence) + "</guid>"
                "<title>Offline fixture</title>"
                "<link>https://example.test/item</link>"
                "</item></channel></rss>"
            )
            return {"status": 200, "body": body}

    feed_transport = FeedTransport()
    watcher = modules["rss_watcher"].RSSWatcher(feed_transport, max_seen=512)
    add("rss_watcher", lambda: watcher.poll("https://example.test/feed"),
        lambda result: isinstance(result, list) and len(result) == 1)

    filter_payload = {"ok": True, "results": [{
        "title": "Offline fixture", "url": "https://example.com/article",
        "snippet": "Synthetic result.", "published_at": "2024-01-01",
        "language": "en-US",
    }], "truncated": False, "source": "fake"}
    filtered = modules["search_filters"].with_search_filters(
        lambda query, **kwargs: filter_payload,
        allowed_domains=["example.com"], language="en",
    )
    add("search_filters", lambda: filtered("offline fixture", limit=3), _is_ok)

    serper_transport = FakeTransport({"organic": [{"title": "Offline fixture"}]})
    serper = modules["serper_you_adapter"].SerperClient(
        serper_transport, endpoint="https://serper.example/search",
        auth_header="X-Offline-Key", payload_builder=lambda query: {"q": query},
    )
    add("serper_you_adapter", lambda: serper.search(
        "offline fixture", api_key="offline-benchmark-placeholder"
    ), lambda result: getattr(result, "status", None) == "OK")

    tavily_transport = FakeTransport({"status": 200, "body": {
        "results": [{"title": "Offline fixture"}]
    }})
    tavily = modules["tavily_adapter"].TavilyClient(
        api_key="offline-benchmark-placeholder", transport=tavily_transport,
        resolver=_resolver,
    )
    add("tavily_adapter", lambda: tavily.search("offline fixture"), _is_ok)

    ssrf_guard = modules["ssrf_guard"]
    add("ssrf_guard", lambda: ssrf_guard.validate_public_url(
        "https://example.test/article", resolver=_resolver
    ), lambda result: result is True)

    if tuple(cases) != MODULES:
        raise RuntimeError("Benchmark case list does not match the 17 module inventory")
    return cases


def _nearest_rank(values, percentile):
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def run_benchmarks(iterations=ITERATIONS, warmup=WARMUP):
    if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    if isinstance(warmup, bool) or not isinstance(warmup, int) or warmup < 0:
        raise ValueError("warmup must be a non-negative integer")

    cases = _build_cases()
    results = {}
    for name in MODULES:
        operation, validator = cases[name]
        first_result = operation()
        if not validator(first_result):
            raise RuntimeError("Offline benchmark fixture failed validation for " + name)
        for _ in range(warmup):
            operation()
        samples = []
        for _ in range(iterations):
            started = time.perf_counter_ns()
            operation()
            samples.append(max(1, time.perf_counter_ns() - started))
        results[name] = {
            "iterations": iterations,
            "mean_ns": statistics.fmean(samples),
            "p50_ns": _nearest_rank(samples, 0.50),
            "p99_ns": _nearest_rank(samples, 0.99),
        }
    return results


def format_report(results, *, iterations=ITERATIONS, warmup=WARMUP):
    if set(results) != set(MODULES):
        raise ValueError("A complete report requires measurements for all 17 modules")
    lines = [
        "# Goat-packs module benchmark results", "",
        "- Calls per module: " + str(iterations) + "; warm-up: " + str(warmup) + ".",
        "- All requests use deterministic injected fakes; DNS answers use an injected public-IP resolver.",
        "- No sockets, DNS lookups, provider endpoints, or browser processes are used.",
        "- Timing: `perf_counter_ns` per call; p50/p99 use nearest-rank; mean is arithmetic mean.",
        "- Runtime: Python " + platform.python_version() + ".", "",
        "| Module | Mean (µs/call) | p50 (µs/call) | p99 (µs/call) |",
        "|---|---:|---:|---:|",
    ]
    for name in MODULES:
        stats = results[name]
        lines.append("| `" + name + "` | "
            + format(stats["mean_ns"] / 1000, ".3f") + " | "
            + format(stats["p50_ns"] / 1000, ".3f") + " | "
            + format(stats["p99_ns"] / 1000, ".3f") + " |")
    return "\n".join(lines) + "\n"


def main():
    print(format_report(run_benchmarks()), end="")


if __name__ == "__main__":
    main()
