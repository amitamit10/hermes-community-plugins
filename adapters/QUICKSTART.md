# GOAT Packs — Quickstart (5-Min Path)

Reach a working search → extract → triage loop in under five minutes. All steps are offline with fake transports; no API keys, browser credentials, or network access required for validation.

## Prerequisites

- Python 3.11+ (stdlib only, no `pip install` required)
- A copy of the complete `goat-packs/` directory (keep sibling `.py` files together — `free_search.py` now imports `ddg_parser.py`, `browser_tier.py` imports `url_gate.py`)

```sh
python3 --version  # 3.11+
ls goat-packs/*.py | wc -l   # expect 39 (21 impl + 18 tests) including ddg_parser.py
```

## 1. Install — 30s

Copy the whole directory; no `PYTHONPATH` or package install needed when you run from inside it.

```sh
cp -r <goat-packs-dir> /tmp/goat-packs
cd /tmp/goat-packs
python3 -c 'import ddg_parser, free_search, free_stack, native_tier, browser_tier, ssrf_guard, url_gate; print("imports OK")'
# expected: imports OK
```

> Keep `ddg_parser.py`, `ssrf_guard.py`, and `url_gate.py` alongside the pack after copy; `free_search` and `free_stack` share the single `ddg_parser._SearchParser`.

## 2. Validate — 60s

Run the offline suite. Failures here are doc drift, not network flakiness.

```sh
cd /tmp/goat-packs
python3 -m unittest discover -s . -p 'test_*.py' -v 2>&1 | tail -n 5
# expected: Ran 177 tests in ...  OK

# If you have the staging sibling present:
python3 -m unittest discover -s <goat-web-dir>/tests -v 2>&1 | tail -n 3
# expected: Ran 61 tests in ... OK
python3 <goat-web-dir>/scripts/fuzz_gate.py
# expected: total_cases=4288 failures=0
```

If `python3 -m unittest` shows 177 OK, your pack copy is self-contained. If it reports `ModuleNotFoundError: No module named 'url_gate'`, you copied only a subset — copy the full directory again.

## 3. Search — 60s

Keyless providers need no credentials. Inject a one-argument `transport(url)` for offline fixtures; the real `pinned_fetch` is used only when you omit `transport`.

**DDG HTML (free_search — OpenSearch-compatible, HTTPS-only SearXNG remains fail-closed):**

```python
from free_search import duckduckgo_search

def fake_ddg(url):
    assert url.startswith("https://html.duckduckgo.com/html/?q=")
    return {"body": '''
      <a class="result__a" href="https://example.org/cats">Cats</a>
      <div class="result__snippet">Feline summary</div>
    '''}

print(duckduckgo_search("cats", transport=fake_ddg))
# {'ok': True, 'results': [{'title': 'Cats', 'url': 'https://example.org/cats', 'snippet': 'Feline summary'}], 'truncated': False}
```

**Stack with explicit fallback (free_stack):**

```python
from free_stack import fallback_chain
import json

wiki = lambda url: json.dumps({"query": {"search": [{"title": "Python", "snippet": "lang"}]}})
ddg  = lambda url: '<a class="result__a" href="https://example.org/d">D</a>'

res = fallback_chain("python", allow_fallback=True, wikipedia_transport=wiki, ddg_transport=ddg, searxng_transport=lambda u: {"results": []})
print(res["source"], res.get("transitions"))
# wikipedia [{'from': 'searxng', 'to': 'wikipedia', 'reason': 'NO_RESULTS'}]
```

**Native wrapper (if you have Hermes callables):**

```python
from native_tier import native_search

def fake_web_search(query, limit=5):
    return {"data": {"web": [{"title": "T", "url": "https://example.org/p", "description": "d"}]}}
print(native_search("q", web_search=fake_web_search))
```

## 4. Extract — 60s

**Single-page extract (pin-aware native tier):**

```python
from native_tier import native_extract

def fake_extract(urls, char_limit=8000):
    return {"data": {"results": [{"content": "hello world", "url": urls[0]}]}}

print(native_extract("https://example.org/p", web_extract=fake_extract))
# {'ok': True, 'url': 'https://example.org/p', 'content': 'hello world', 'truncated': False}
```

**Crawl (same-origin, depth/page capped at 3/25):**

```python
from crawl_pro import crawl_pro

def fake_fetch(url):
    if "robots" in url: return {"status": 404, "body": "", "headers": {}}
    if "sitemap" in url: return {"status": 404, "body": "", "headers": {}}
    return {"status": 200, "body": '<a href="https://example.org/other">x</a>', "headers": {}}

print(crawl_pro("https://example.org/start", transport=fake_fetch, max_pages=2))
# {'pages': [...], 'requests_by_host': {'example.org': ...}, 'truncated': ...}
```

Browser tier uses the same `transport(url)` contract plus `ssrf_guard` pinning; see `browser_tier.py` docstring for `request_gate` requirements.

## 5. Triage — 60s

Every public result uses the same envelope:

- Success: `{"ok": True, "results": [...], "truncated": bool, "source": "searxng|wikipedia|ddg"}` (plus `transitions` when fallback occurred)
- Failure: `{"error": {"code": "URL_BLOCKED|REDIRECT_BLOCKED|MISSING_CONFIG"}}`

Quick triage:

```python
res = duckduckgo_search("q", transport=fake_ddg)
if res.get("ok"):
    if res.get("truncated"): print("more than 5 hits — re-query with narrower terms")
    for r in res["results"]: print(r["title"], r["url"])
else:
    code = res["error"]["code"]
    # See TROUBLESHOOTING.md for code → fix
    print("failed:", code)
```

- `source` tells you which provider answered; `transitions` tells you why fallback moved (e.g., `NO_RESULTS` vs `URL_BLOCKED`).
- `truncated=True` means the provider returned > `max_results` or text exceeded 8000 chars — not an error.

Total time: <5 minutes installed → validated → searched → extracted → triaged.

Next: `TROUBLESHOOTING.md` for the three public error codes, and `README.md` for full gate commands.
