# GOAT V3 Quickstart (5-Min Path)

Offline-first validation using the built `hermes-goat-web` bundle. No API keys, no network, no live plugin enable required.

## Prerequisites

- Python 3.11+, `git`, Hermes Agent (for read-only `validate` checks)
- Stdlib only — no `pip install`, no `PYTHONPATH`

## 1. Clone (portable)

```sh
git clone <repo-url> goat
cd goat
python3 --version  # 3.11+
ls goat-web/plugins/goat-web/plugin.yaml goat-web/scripts/build_plugin_bundle.py
```

> `goat-web/plugins/goat-web/` is a source template — it imports `._goat_v3_vendor` which exists only in a built bundle.

## 2. Build a fresh standalone bundle

```sh
python3 -B goat-web/scripts/build_plugin_bundle.py --help
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
ls /tmp/hermes-goat-web/bundle-manifest.json
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
# ok /tmp/hermes-goat-web
```

Layout inside the bundle:

```
__init__.py  goat_tools.py  url_gate.py  tool_schemas.py  v3_wiring.py
plugin.yaml  hermes-goat-web.plugin.json  _goat_v3_vendor/*.py
```

Only `/tmp/hermes-goat-web` is standalone and Hermes-validatable. The source directory is not.

## 3. Read-only Hermes check (no install)

```sh
# confirm flags on your Hermes version first
hermes --help; hermes plugins --help; hermes plugins validate --help
hermes plugins validate /tmp/hermes-goat-web 2>&1 | head
# no install, no enable, no gateway restart
```

## 4. Validate offline (reproducible, no hardcoded totals)

```sh
python3 -B -m unittest discover -s adapters -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v 2>&1 | tail -n 20
python3 goat-web/scripts/fuzz_gate.py   # correctness fuzzer, offline
python3 goat-web/scripts/audit_staging.py  # narrow heuristic
```

Parent verified **408 existing tests** before integration; an **R1 regression is pending a separate fix** — prefer the commands above over quoting a final total until the parent final gate.

## 5. Try the seven tools with fake transports

**Search (DuckDuckGo HTML):**

```python
from adapters.free_stack import duckduckgo_search
def fake(url):
    assert url.startswith("https://html.duckduckgo.com/html/?q=")
    return {"body": '<a class="result__a" href="https://example.org/cats">Cats</a><div class="result__snippet">Feline</div>'}
print(duckduckgo_search("cats", transport=fake))
# {'ok': True, 'results': [...]}
```

**Extractive answer (Wikipedia, extractive, not LLM):**

```python
from adapters.answer_synth import goat_answer
def fake_search(q):
    return {"ok": True, "results": [{"title": "Cat", "url": "https://example.org/cat", "snippet": "Cats were domesticated in the Near East. Early cats lived with humans."}]}
print(goat_answer("cats domestication", search=fake_search, max_results=2))
# {'ok': True, 'answer': '... [1]', 'sources': [...]}
```

**Filtered search (inclusive UTC, domains, language):**

```python
from adapters.search_filters import with_search_filters
wrapped = with_search_filters(lambda q: {"ok": True, "results": [{"title": "P", "url": "https://example.org/p", "published": "2024-06-01", "language": "en-US"}]}, time_after="2024-01-01", language="en")
print(wrapped("q"))
```

**Verticals (Crossref/GDELT/Commons — metadata + links only):**

```python
from adapters.free_verticals import scholar_search, news_search, image_search
print(scholar_search("graphs", transport=lambda u: {"body": '{"message":{"items":[{"title":"T","URL":"https://example.org/d","DOI":"10.1/x"}]}}'}))
```

Every success envelope is `{"ok": true, ...}`; failures are exactly one of `URL_BLOCKED`, `REDIRECT_BLOCKED`, `MISSING_CONFIG`. Next: `TROUBLESHOOTING.md`.
