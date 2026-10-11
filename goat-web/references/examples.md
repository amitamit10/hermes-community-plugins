# Worked examples

Illustrative fixtures for the seven-tool contract (sanitized, not live network claims). Each shows the exact tool input and its `ok: true` output or fail-closed `ok: false` error.

## 1. Search

Input (`goat_search`):

```json
{ "query": "example.com documentation", "max_results": 2 }
```

Output:

```json
{
  "ok": true,
  "results": [
    { "title": "Example documentation overview", "url": "https://example.com/docs", "snippet": "Illustrative result about docs." },
    { "title": "Example getting started guide", "url": "https://example.com/guide", "snippet": "Illustrative guide snippet." }
  ]
}
```

Search returns ≤ requested results without fetching them.

## 2. Extract one page

Input (`goat_extract`):

```json
{ "url": "https://example.com/guide" }
```

Output:

```json
{
  "ok": true,
  "url": "https://example.com/guide",
  "final_url": "https://example.com/guide",
  "status": 200,
  "title": "Example guide",
  "text": "Illustrative extracted text.",
  "truncated": false
}
```

Policy-compliant redirects only; text is normalized readable text ≤8000 chars.

## 3. Crawl same-origin

Input (`goat_crawl`):

```json
{ "url": "https://example.com/docs", "max_depth": 1, "max_pages": 3 }
```

Output:

```json
{
  "ok": true,
  "pages": [
    { "url": "https://example.com/docs", "depth": 0, "status": 200, "title": "Example documentation", "text": "Starting page text.", "truncated": false },
    { "url": "https://example.com/guide", "depth": 1, "status": 200, "title": "Example guide", "text": "Guide page text.", "truncated": false },
    { "url": "https://example.com/faq", "depth": 1, "status": 200, "title": "Example FAQ", "text": "FAQ text.", "truncated": false }
  ]
}
```

BFS, start depth 0, same origin, per-page truncation.

## 4. Probe

Input (`goat_probe`):

```json
{ "url": "https://example.com/" }
```

Output:

```json
{ "ok": true, "status": 200, "host": "example.com" }
```

No body returned.

## 5. Extractive answer (Wikipedia)

Input (`goat_answer`):

```json
{ "query": "cats domestication", "max_results": 2 }
```

Output:

```json
{
  "ok": true,
  "answer": "Cats were domesticated in the Near East [1]\nEarly cats lived with humans in ancient villages [2]",
  "sources": [
    { "index": 1, "title": "Cat", "url": "https://en.wikipedia.org/wiki/Cat" },
    { "index": 2, "title": "Domestication of the cat", "url": "https://en.wikipedia.org/wiki/Domestication_of_the_cat" }
  ],
  "source": "wikipedia",
  "source_url": "https://en.wikipedia.org/w/api.php"
}
```

Extractive, deterministic sentences from snippets with numbered citations. Not LLM synthesis; bounded to the official Wikipedia Action API.

## 6. Filtered Wikipedia search

Input (`goat_filtered_search`):

```json
{
  "query": "climate policy",
  "max_results": 3,
  "time_after": "2024-01-01",
  "time_before": "2024-12-31T23:59:59Z",
  "allowed_domains": ["wikipedia.org"],
  "language": "en"
}
```

Output:

```json
{
  "ok": true,
  "results": [
    { "title": "Climate policy", "url": "https://en.wikipedia.org/wiki/Climate_policy", "snippet": "Policy overview snippet.", "published": "2024-06-01T00:00:00+00:00", "language": "en-US" }
  ]
}
```

Inclusive UTC filter; naive dates mean UTC; primary `en` matches `en-US` but not vice versa; missing/invalid metadata excluded.

## 7. Vertical scholar (Crossref)

Input (`goat_vertical_search`):

```json
{ "vertical": "scholar", "query": "graph neural networks", "max_results": 2 }
```

Output:

```json
{
  "ok": true,
  "vertical": "scholar",
  "source": "crossref",
  "source_url": "https://api.crossref.org/works",
  "results": [
    { "title": "Graph Neural Networks: A Review", "url": "https://doi.org/10.1234/example", "doi": "10.1234/example", "authors": ["Jane Doe"], "year": 2023, "venue": "Journal of Machine Learning" }
  ],
  "truncated": false
}
```

Provider links only; no abstract download required.

## 8. Vertical news (GDELT) and image licensing (Commons)

`goat_vertical_search` with `vertical: news` returns `snippet`/`published`/`source` per article plus GDELT attribution links. `vertical: images` returns per-file `license`, `license_url`, `creator`, `description`, `page_url` for that file — verify licensing before reuse. No paid fallback.

## 9. Blocked URL / redirect / missing config

```json
{ "ok": false, "error": { "code": "URL_BLOCKED" } }
{ "ok": false, "error": { "code": "REDIRECT_BLOCKED" } }
{ "ok": false, "error": { "code": "MISSING_CONFIG" } }
```

Invalid initial URL or unknown field → `URL_BLOCKED`; disallowed/excessive redirect → `REDIRECT_BLOCKED`; absent required transport/config → `MISSING_CONFIG` before any fetch. All three are closed, sanitized codes.

## RSS watcher (adapter, not a Hermes tool)

`adapters/rss_watcher.py` maps feeds to normalized items: RSS `guid` / Atom `id` → `id` (fallback hash), `title`→`title`, `link`→`url`, `description`/`summary`/`content`→`summary`, `pubDate`/`published`/`updated`→`published`. Dedup uses an injected fetcher and bounded watermark; no network by default.

## Serper + You adapters (keyed, separate from verticals)

`serper_you_adapter.py` — `SerperClient` requires explicit `endpoint` + `auth_header` + `payload_builder` plus `api_key`; missing pieces return `MISSING_CONFIG` without transport. Marked experimental/unverified. `YouClient` posts JSON to `https://ydc-index.io/v1/search` with `X-API-Key` header; missing key or transport → `MISSING_CONFIG`; both use `result_operation` normalization to the three public codes.
