# Tool schemas

Closed public contract. Each registered JSON schema sets `additionalProperties: false`; unknown fields return the public `URL_BLOCKED` error rather than executing. URL policy in [url-policy.md](url-policy.md) applies wherever a URL is accepted. All success envelopes carry `ok: true` (plus tool-specific fields); failures carry `ok: false, error: {code}` with only three public codes.

## `goat_search`

Input:

```json
{
  "query": "string (required, non-empty)",
  "max_results": "integer 1..5, default 5"
}
```

Booleans, strings, floats for `max_results` are rejected (`URL_BLOCKED`). Success:

```json
{ "ok": true, "results": [ { "title": "string", "url": "string", "snippet": "string" } ] }
```

Search only; does not fetch result URLs. Count ≤ `max_results`. Legacy default backend: DuckDuckGo HTML (keyless).

## `goat_extract`

Input: `{ "url": "string (required, one HTTPS URL)" }`

Success:

```json
{
  "ok": true,
  "url": "string",
  "final_url": "string",
  "status": "integer",
  "title": "string",
  "text": "string ≤8000 chars",
  "truncated": "boolean"
}
```

Follows only policy-compliant redirects. `text` is normalized readable text, not raw HTML.

## `goat_crawl`

Input:

```json
{
  "url": "string (required, start URL)",
  "max_depth": "integer 0..2, default 2",
  "max_pages": "integer 1..10, default 10"
}
```

Bounds enforced; out-of-range or non-integer returns `URL_BLOCKED`.

Success:

```json
{
  "ok": true,
  "pages": [
    { "url": "string", "depth": "integer", "status": "integer", "title": "string", "text": "string ≤8000", "truncated": "boolean" }
  ]
}
```

Breadth-first, start depth 0 counts toward `max_pages`, same-origin only, each normalized URL once, per-page truncation flag. No crawl-wide status/truncation beyond per-page.

## `goat_probe`

Input: `{ "url": "string (required)" }`

Success:

```json
{ "ok": true, "status": "integer|null", "host": "string" }
```

Plus reachability boolean in `ok` (true for 2xx/3xx-ish per probe). No body returned.

## `goat_answer`

Deterministic extractive answer over bounded official Wikipedia Action API snippets. No model call, no page fetch.

Input:

```json
{
  "query": "string 1..2000, non-blank (\\S)",
  "max_results": "integer 1..5, default 5"
}
```

Bounded to `https://en.wikipedia.org/w/api.php` via pinned fetch; candidates limited to ≤5, each URL ≤2048 chars and passing the URL gate.

Success:

```json
{
  "ok": true,
  "answer": "string ≤8000, numbered [1] citations per claim",
  "sources": [ { "index": "integer", "title": "string ≤512", "url": "string" } ],
  "source": "wikipedia",
  "source_url": "https://en.wikipedia.org/w/api.php"
}
```

Claims are deduplicated sentences from snippets ranked by title/snippet term overlap; truncation uses ellipsis before citation.

## `goat_filtered_search`

Inclusive filter over ≤5 official Wikipedia Action API candidates. Active filters exclude missing/invalid metadata; no inference, no refill, no fallback.

Input:

```json
{
  "query": "string 1..2000, non-blank",
  "max_results": "integer 1..5, default 5",
  "time_after": "string ISO date/datetime, optional (inclusive UTC; naive → UTC)",
  "time_before": "string ISO date/datetime, optional",
  "allowed_domains": ["bare DNS/IP, not URL, 20 max, unique"],
  "denied_domains": ["same, deny wins over allow; empty allowed excludes all"],
  "language": "string BCP-47 2..63, primary matches regional variants, regional requires exact"
}
```

Date fields checked: `published_at`, `publishedAt`, `published_date`, `publication_date`, `published`, `date`, `datetime`, `timestamp`, `created_at`. Calendar validity and `time_after ≤ time_before` are validated before retrieval. Language fields checked: `language`, `language_code`, `lang`, `locale`.

Success:

```json
{ "ok": true, "results": [ { "title": "string", "url": "string", "snippet": "string", "published": "string", "language": "string", ... } ], "truncated": "boolean" }
```

Filtered set is bounded to `max_results`; `truncated` signals upstream >5 or per-item >8000.

## `goat_vertical_search`

One official keyless metadata API per call. No article/image downloads or paid fallback.

Input:

```json
{
  "vertical": "\"scholar\" | \"news\" | \"images\"",
  "query": "string 1..2000, non-blank",
  "max_results": "integer 1..5, default 5"
}
```

Endpoints (pinned fetch, 10s, 1 MiB, 0 redirects):

- `scholar` → `https://api.crossref.org/works` — returns provider links/DOI, authors, year, venue; no abstract fetch
- `news` → `https://api.gdeltproject.org/api/v2/doc/doc` — returns `snippet`/`published`/`source`/`language` + GDELT attribution links
- `images` → `https://commons.wikimedia.org/w/api.php` — returns `image_url`/`page_url` plus per-file `license`/`license_url`/`creator`/`description`; unsafe/missing-license records excluded without download

Success:

```json
{
  "ok": true,
  "vertical": "scholar|news|images",
  "results": [ { "title": "string", "url": "string", ...vertical fields } ],
  "source": "crossref|gdelt|wikimedia-commons",
  "source_url": "official endpoint",
  "truncated": "boolean"
}
```

## Fail-closed errors (all tools)

```json
{ "ok": false, "error": { "code": "URL_BLOCKED" } }
{ "ok": false, "error": { "code": "REDIRECT_BLOCKED" } }
{ "ok": false, "error": { "code": "MISSING_CONFIG" } }
```

`URL_BLOCKED` for invalid/disallowed initial URL or invalid arguments/unknown fields; `REDIRECT_BLOCKED` for invalid/disallowed/excessive redirect; `MISSING_CONFIG` when a required dependency (search transport or vertical transport) is absent or `None`. No internal details are exposed; only these three codes.
