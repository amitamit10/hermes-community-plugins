# Worked examples (continued)

The outputs below are exact illustrative fixtures in the `goat_tools.py` handler return shape, not claims about live `example.com` responses. Each example shows the complete public tool input and its corresponding output. Provider credentials remain in server-side configuration and never appear in tool inputs or outputs.

## 7. Paid search adapter with configured key

Precondition: a deployment wrapper has selected a paid search adapter and its key is present in server-side configuration. Adapter selection and the key are not public tool arguments; this example shows the public call and sanitized handler result.

Input (`goat_search`):

```json
{
  "query": "sample API guide",
  "limit": 1
}
```

Output:

```json
{
  "ok": true,
  "results": [
    {
      "title": "Sample API guide",
      "url": "https://example.com/docs",
      "snippet": "Illustrative result from the configured search adapter."
    }
  ],
  "truncated": false
}
```

## 8. Paid search adapter without its required key

Precondition: the deployment wrapper selected a paid adapter that requires a key, but no key is configured. The default keyless DuckDuckGo search is a separate configuration; this fixture demonstrates the missing-config error for the selected paid adapter.

Input (`goat_search`):

```json
{
  "query": "sample API guide",
  "limit": 1
}
```

Output:

```json
{
  "ok": false,
  "error": "MISSING_CONFIG"
}
```

## 9. RSS watcher: first poll

Precondition: the watcher polls a public RSS URL using `goat_extract`. Extraction returns the feed body as text; it does not parse or retain watcher state.

Input (`goat_extract`):

```json
{
  "url": "https://example.com/feed.xml"
}
```

Output:

```json
{
  "ok": true,
  "url": "https://example.com/feed.xml",
  "status": 200,
  "content": "<?xml version=\"1.0\"?><rss version=\"2.0\"><channel><title>Example feed</title><item><guid>https://example.com/posts/1</guid><title>First item</title></item></channel></rss>",
  "truncated": false
}
```

## 10. RSS watcher: later poll finds another GUID

The watcher makes the same stateless extraction call on its next poll. Its own state compares stable item identifiers such as `guid` and decides that item 2 is new.

Input (`goat_extract`):

```json
{
  "url": "https://example.com/feed.xml"
}
```

Output:

```json
{
  "ok": true,
  "url": "https://example.com/feed.xml",
  "status": 200,
  "content": "<?xml version=\"1.0\"?><rss version=\"2.0\"><channel><title>Example feed</title><item><guid>https://example.com/posts/1</guid><title>First item</title></item><item><guid>https://example.com/posts/2</guid><title>Second item</title></item></channel></rss>",
  "truncated": false
}
```

## 11. Public redirect chain

Precondition: the fixture follows two redirects, and every hop and the final URL is public and allowed. The returned `url` is the final response URL.

Input (`goat_extract`):

```json
{
  "url": "https://example.com/old-guide"
}
```

Output:

```json
{
  "ok": true,
  "url": "https://example.com/docs/guide",
  "status": 200,
  "content": "Illustrative guide content after the redirect chain.",
  "truncated": false
}
```

## 12. Redirect chain blocked at a private destination

Precondition: the public starting URL redirects through a chain whose destination resolves to a non-public address. The redirect is rejected and the public error contract exposes only `REDIRECT_BLOCKED`.

Input (`goat_extract`):

```json
{
  "url": "https://example.com/redirect-to-private"
}
```

Output:

```json
{
  "ok": false,
  "error": "REDIRECT_BLOCKED"
}
```

## 13. IDNA-equivalent hosts stay same-origin in a crawl

Precondition: the illustrative transport maps this placeholder host to a public address. The Unicode hostname and its punycode form normalize to the same origin, so the crawl follows the link.

Input (`goat_crawl`):

```json
{
  "url": "https://bücher.example/"
}
```

Output:

```json
{
  "ok": true,
  "pages": [
    {
      "url": "https://bücher.example/",
      "status": 200,
      "content": "<a href=\"https://xn--bcher-kva.example/about\">About</a>",
      "truncated": false
    },
    {
      "url": "https://xn--bcher-kva.example/about",
      "status": 200,
      "content": "About page.",
      "truncated": false
    }
  ],
  "truncated": false
}
```

## 14. Crawl depth bound

The crawl depth is fixed at 2: the start page is depth 0, followed by pages at depths 1 and 2. Links on a depth-2 page are not enqueued, so the depth-3 page is absent.

Input (`goat_crawl`):

```json
{
  "url": "https://example.com/root"
}
```

Output:

```json
{
  "ok": true,
  "pages": [
    {
      "url": "https://example.com/root",
      "status": 200,
      "content": "<a href=\"/level-1\">Level 1</a>",
      "truncated": false
    },
    {
      "url": "https://example.com/level-1",
      "status": 200,
      "content": "<a href=\"/level-2\">Level 2</a>",
      "truncated": false
    },
    {
      "url": "https://example.com/level-2",
      "status": 200,
      "content": "<a href=\"/level-3\">Level 3</a>",
      "truncated": false
    }
  ],
  "truncated": false
}
```

## 15. Crawl page-count bound

The crawl is fixed at 10 pages total, including the start page. This breadth-first fixture queues ten child links; it returns the start page and the first nine children, then reports `truncated: true` because one queued page remains. The tool input has no caller-controlled page-limit field.

Input (`goat_crawl`):

```json
{
  "url": "https://example.com/hub"
}
```

Output:

```json
{
  "ok": true,
  "pages": [
    {
      "url": "https://example.com/hub",
      "status": 200,
      "content": "<a href=\"/p1\">1</a><a href=\"/p2\">2</a><a href=\"/p3\">3</a><a href=\"/p4\">4</a><a href=\"/p5\">5</a><a href=\"/p6\">6</a><a href=\"/p7\">7</a><a href=\"/p8\">8</a><a href=\"/p9\">9</a><a href=\"/p10\">10</a>",
      "truncated": false
    },
    {
      "url": "https://example.com/p1",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p2",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p3",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p4",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p5",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p6",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p7",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p8",
      "status": 200,
      "content": "",
      "truncated": false
    },
    {
      "url": "https://example.com/p9",
      "status": 200,
      "content": "",
      "truncated": false
    }
  ],
  "truncated": true
}
```

## 16. Crawl same-origin boundary

Links to a different origin are skipped; the crawl only fetches the start page and its same-origin link.

Input (`goat_crawl`):

```json
{
  "url": "https://example.com/start"
}
```

Output:

```json
{
  "ok": true,
  "pages": [
    {
      "url": "https://example.com/start",
      "status": 200,
      "content": "<a href=\"/inside\">Inside</a><a href=\"https://example.net/outside\">Outside</a>",
      "truncated": false
    },
    {
      "url": "https://example.com/inside",
      "status": 200,
      "content": "Inside.",
      "truncated": false
    }
  ],
  "truncated": false
}
```
