# Worked examples

The outputs below are exact illustrative fixtures for the documented tool contract, not claims about live `example.com` responses. Each example shows the complete tool input and its corresponding output.

## 1. Search

Input (`goat_search`):

```json
{
  "query": "example.com documentation",
  "limit": 2
}
```

Output:

```json
{
  "results": [
    {
      "title": "Example documentation overview",
      "url": "https://example.com/docs",
      "snippet": "An illustrative result about documentation on the example site."
    },
    {
      "title": "Example getting started guide",
      "url": "https://example.com/guide",
      "snippet": "An illustrative result introducing a sample guide."
    }
  ]
}
```

Search returns at most the requested number of results and does not fetch the result URLs.

## 2. Extract one page

Input (`goat_extract`):

```json
{
  "url": "https://example.com/guide"
}
```

Output:

```json
{
  "url": "https://example.com/guide",
  "final_url": "https://example.com/guide",
  "status": 200,
  "title": "Example guide",
  "text": "Illustrative extracted text from the example guide page.",
  "truncated": false
}
```

Extraction follows only policy-compliant redirects and returns no more than 8,000 characters of normalized readable text (not raw HTML). `url` remains the requested URL; `final_url` identifies the validated response destination after redirects.

## 3. Crawl same-origin pages

Input (`goat_crawl`):

```json
{
  "url": "https://example.com/docs",
  "max_depth": 1,
  "max_pages": 3
}
```

Output:

```json
{
  "pages": [
    {
      "url": "https://example.com/docs",
      "depth": 0,
      "status": 200,
      "title": "Example documentation",
      "text": "Illustrative text for the starting documentation page.",
      "truncated": false
    },
    {
      "url": "https://example.com/guide",
      "depth": 1,
      "status": 200,
      "title": "Example guide",
      "text": "Illustrative text for the guide page.",
      "truncated": false
    },
    {
      "url": "https://example.com/faq",
      "depth": 1,
      "status": 200,
      "title": "Example FAQ",
      "text": "Illustrative text for the FAQ page.",
      "truncated": false
    }
  ]
}
```

The start page is depth zero. The crawl is breadth-first, stays on the starting URL's origin, and stays within both supplied bounds. Each page carries its own text-truncation flag; the crawl result contains only `pages`.

## 4. Probe reachability

Input (`goat_probe`):

```json
{
  "url": "https://example.com/"
}
```

Output:

```json
{
  "ok": true,
  "status": 200,
  "host": "example.com"
}
```

A probe reports reachability metadata only; it does not return page content.

## 5. Block an SSRF destination

Precondition for this illustrative test fixture: `private.example.com` resolves to a non-public address. The URL is rejected before a connection is made.

Input (`goat_probe`):

```json
{
  "url": "https://private.example.com/"
}
```

Output:

```json
{
  "error": {
    "code": "URL_BLOCKED"
  }
}
```

## 6. Missing key for an explicitly selected paid search backend

Precondition: a paid search backend has been explicitly selected and its required API key is absent. The default DuckDuckGo HTML search is keyless. The paid-backend request fails closed; no key is included in the tool input.

Input (`goat_search`):

```json
{
  "query": "example.com documentation",
  "limit": 3
}
```

Output:

```json
{
  "error": {
    "code": "MISSING_CONFIG"
  }
}
```
