#!/usr/bin/env python3
"""Live smoke of every registered GOAT tool. Usage: smoke.py BUNDLE OUT.json"""
import json, sys, datetime
sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import load_tools, call
tools = load_tools(sys.argv[1])
CASES = [
 ("goat_search", {"query": "python programming language"}),
 ("goat_search", {"query": "who wrote the Rust borrow checker RFC", "max_results": 3}),
 ("goat_search", {"query": "capital of Australia"}),
 ("goat_search", {"query": "zxqvbnmw98123 qqqplmkj nonsense"}),
 ("goat_search", {"query": "openai gpt latest release", "max_results": 5}),
 ("goat_extract", {"url": "https://example.com"}),
 ("goat_extract", {"url": "https://en.wikipedia.org/wiki/Alan_Turing"}),
 ("goat_extract", {"url": "https://docs.python.org/3/library/json.html"}),
 ("goat_crawl", {"url": "https://example.com", "max_depth": 1, "max_pages": 3}),
 ("goat_crawl", {"url": "https://docs.python.org/3/", "max_depth": 1, "max_pages": 5}),
 ("goat_probe", {"url": "https://example.com"}),
 ("goat_probe", {"url": "https://httpbin.org/status/404"}),
 ("goat_answer", {"query": "Who discovered penicillin?"}),
 ("goat_answer", {"query": "What is the capital of France?"}),
 ("goat_filtered_search", {"query": "machine learning", "allowed_domains": ["en.wikipedia.org"], "language": "en"}),
 ("goat_vertical_search", {"vertical": "scholar", "query": "transformer attention", "max_results": 3}),
 ("goat_vertical_search", {"vertical": "news", "query": "inflation", "max_results": 3}),
 ("goat_vertical_search", {"vertical": "images", "query": "red panda", "max_results": 3}),
 # safety controls
 ("goat_probe", {"url": "https://127.0.0.1"}),
 ("goat_extract", {"url": "http://example.com"}),
 ("goat_extract", {"url": "https://169.254.169.254/latest/meta-data/"}),
 ("goat_search", {"query": ""}),
]
print("registered:", sorted(tools))
rows = []
for name, args in CASES:
    out, ms = call(tools, name, args)
    code = (out.get("error") or {}).get("code")
    rows.append({"tool": name, "args": args, "latency_ms": round(ms, 1), "ok": out.get("ok"), "error_code": code, "output": out})
    n = len(out.get("results", out.get("pages", []))) if isinstance(out, dict) else ""
    print(f"{name:22} ok={out.get('ok')!s:5} code={code} ms={ms:8.0f} n={n} {json.dumps(args)[:70]}")
json.dump({"utc": datetime.datetime.utcnow().isoformat()+"Z", "rows": rows}, open(sys.argv[2], "w"), indent=1, ensure_ascii=False)
