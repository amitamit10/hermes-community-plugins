# Goat modules: runnable usage examples

כל דוגמה עצמאית, משתמשת בנתוני fixture ובתעבורת דמה בלבד; אין גישה לרשת ואין מפתחות אמיתיים. מחרוזות `test-only` הן ערכי בדיקה פיקטיביים. נכללים 17 מודולי `goat-packs` ושני מודולי companion (`adapters.py`, `url_gate.py`); `bench_gate.py` הוא harness למדידה, לא מודול מימוש.

## `answer_synth.py`

```python
from answer_synth import goat_answer
def search(query): return {"results": [{"title": "Python release", "url": "https://example.com/python", "snippet": "Python 3.13 adds an interactive interpreter."}]}
answer = goat_answer("Python release", search)
assert answer["sources"][0]["url"] == "https://example.com/python"
```

## `anysearch_adapter.py`

```python
from anysearch_adapter import AnySearchClient
def fake(url, *, method, headers, json): return {"status": 200, "body": {"jsonrpc": "2.0", "id": json["id"], "result": {"content": [{"type": "text", "text": "offline fixture"}]}}}
result = AnySearchClient(fake).search("offline")
assert result == {"ok": True, "data": "offline fixture"}
```

## `browser_tier.py`

```python
from browser_tier import BrowserTier
fetch = lambda url: {"status": 200, "body": "A public offline article fixture."}
page = BrowserTier(transport=fetch).fetch("https://example.com/article")
assert page["ok"] and page["source"] == "transport"
```

## `crawl_pro.py`

```python
from crawl_pro import crawl_pro
docs = {"https://example.com/": {"status": 200, "body": "<a href='/about'>About</a>"}, "https://example.com/about": {"status": 200, "body": "About page"}}
def fake(url): return docs.get(url, {"status": 404, "body": ""})
crawl = crawl_pro("https://example.com/", fake, respect_robots=False)
assert [p["url"] for p in crawl["pages"]] == ["https://example.com/", "https://example.com/about"]
```

## `deep_verticals.py`

```python
from deep_verticals import stooq_daily
csv = "Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,1,2,10\n"
prices = stooq_daily("aapl.us", transport=lambda url: csv)
assert prices["prices"][0]["close"] == 2.0
```

## `donsetch_adapter.py`

```python
from donsetch_adapter import DonsetchAdapter
adapter = DonsetchAdapter(binary_checker=lambda path: False, binary_path="/offline/demo")
status = adapter.check()
assert status["ok"] is False
```

## `exa_adapter.py`

```python
from exa_adapter import ExaClient
fake = lambda url, **request: {"status": 200, "body": {"results": [{"title": "Fixture"}]}}
result = ExaClient(api_key="test-only", transport=fake).search("offline")
assert result["ok"]
```

## `firecrawl_adapter.py`

```python
from firecrawl_adapter import FirecrawlClient
fake = lambda url, **request: {"status": 200, "body": {"success": True, "data": {"markdown": "Fixture"}}}
result = FirecrawlClient("test-only", fake).scrape("https://example.com/page")
assert result["ok"]
```

## `free_search.py`

```python
import json
from free_search import wikipedia_search
body = json.dumps(["offline", ["Offline"], ["A fixture page"], ["https://en.wikipedia.org/wiki/Offline"]])
result = wikipedia_search("offline", transport=lambda url: body)
assert result["results"][0]["title"] == "Offline"
```

## `free_stack.py`

```python
import json
from free_stack import wikipedia_search
body = json.dumps({"query": {"search": [{"title": "Offline", "fullurl": "https://en.wikipedia.org/wiki/Offline", "snippet": "Fixture"}]}})
result = wikipedia_search("offline", transport=lambda url: body)
assert result["results"][0]["title"] == "Offline"
```

## `free_verticals.py`

```python
import json
from free_verticals import scholar_search
body = json.dumps({"message": {"items": [{"DOI": "10.1000/demo", "title": ["Offline paper"], "URL": "https://doi.org/10.1000/demo"}]}})
result = scholar_search("offline", transport=lambda url: body)
assert result["results"][0]["title"] == "Offline paper"
```

## `native_tier.py`

```python
from native_tier import native_search
fake_search = lambda query, *, limit: {"data": {"web": [{"title": "Fixture", "url": "https://example.com", "description": "Offline result"}]}}
result = native_search("offline", fake_search)
assert result["results"][0]["title"] == "Fixture"
```

## `rss_watcher.py`

```python
from rss_watcher import RSSWatcher
feed = "<rss><channel><item><guid>demo-1</guid><title>Fixture</title><link>https://example.com/item</link></item></channel></rss>"
watcher = RSSWatcher(lambda url: feed)
items = watcher.poll("https://example.com/feed.xml")
assert items[0]["id"] == "demo-1"
```

## `search_filters.py`

```python
from search_filters import with_search_filters
backend = lambda query: {"ok": True, "results": [{"url": "https://docs.example.com/a", "language": "en-US"}]}
search = with_search_filters(backend, allowed_domains=["example.com"], language="en")
assert len(search("offline")["results"]) == 1
```

## `serper_you_adapter.py`

```python
from serper_you_adapter import SerperClient
fake = lambda **request: {"organic": []}
client = SerperClient(fake, endpoint="https://serper.invalid/search", auth_header="X-Test-Key", payload_builder=lambda q: {"q": q})
result = client.search("offline", api_key="test-only")
assert result.status == "OK" and result.data == {"organic": []}
```

## `ssrf_guard.py`

```python
from ssrf_guard import validate_public_url
resolver = lambda host, port, **kwargs: ["93.184.216.34"]
assert validate_public_url("https://example.com/page", resolver=resolver) is True
```

## `tavily_adapter.py`

```python
from tavily_adapter import TavilyClient
fake = lambda url, **request: {"status": 200, "body": {"results": [{"title": "Fixture"}]}}
result = TavilyClient(api_key="test-only", transport=fake).search("offline", max_results=1)
assert result["data"]["results"][0]["title"] == "Fixture"
```

## `adapters.py`

```python
from adapters import trafilatura_like_extract, crawl_frontier, rss_parse
text = trafilatura_like_extract("<main>Offline text</main>")
crawl = crawl_frontier("https://example.com/", lambda url: "<a href='/next'>Next</a>", max_pages=2)
feed = rss_parse()
assert text == "Offline text" and len(crawl["pages"]) == 2 and feed[0]["title"] == "Sample article"
```

## `url_gate.py`

```python
from url_gate import check_url, check_redirect
assert check_url("https://example.com/") == (True, "OK")
assert check_redirect("example.com", "/next", 0) == (True, "OK")
```
