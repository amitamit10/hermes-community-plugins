# Tool schemas

Closed public contract. Each registered JSON schema sets `additionalProperties: false`; unknown fields return the public `URL_BLOCKED` error rather than executing. URL policy in [url-policy.md](url-policy.md) applies wherever a URL is accepted. All success envelopes carry `ok: true` (plus tool-specific fields); failures carry `ok: false, error: {code}` with ten public codes (`URL_BLOCKED`, `REDIRECT_BLOCKED`, `MISSING_CONFIG`, `PROVIDER_BLOCKED`, `HTTP_ERROR`, `RATE_LIMITED`, `DNS_ERROR`, `CONNECTION_ERROR`, `UPSTREAM_TIMEOUT`, `INSUFFICIENT_EVIDENCE`). Types and bounds policy is unchanged.

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

Deterministic sentence-grounded answer from fixed English Wikipedia Action API search plus readable intro extracts (at most two official requests, at most five candidates). No model call or arbitrary page fetch; direct complete subject-relation evidence or public `INSUFFICIENT_EVIDENCE`; bounded full claims with cited sources only; multi-hop unsupported; not general-web coverage.

Input:

```json
{
  "query": "string 1..2000, non-blank (\\S)",
  "max_results": "integer 1..5, default 5"
}
```

Bounded to the known English endpoint `https://en.wikipedia.org/w/api.php` via pinned fetch (10s, 1 MiB, 0 redirects); candidates limited to ≤5, each URL ≤2048 chars and passing the URL gate; wiki candidates carry `language: "en"`.

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

Claims are complete deduplicated source sentences (not ellipsis fragments) ranked by title/snippet term overlap; every listed source is cited by a real identical sentence; unsupported, ambiguous or multi-hop queries return `INSUFFICIENT_EVIDENCE`. Answer text ≤8000 chars; no paid source or quality-score claim.

## `goat_filtered_search`

Inclusive filter over ≤5 official Wikipedia Action API candidates from the known English source (`language: "en"`). Active filters exclude missing/invalid metadata (undated candidates are excluded when a time filter is active, otherwise retained); no fabricated dates, metadata inference, refill or fallback; deny wins over allow; primary language matches regional variants, regional requires the exact tag.

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
{ "ok": false, "error": { "code": "PROVIDER_BLOCKED" } }
{ "ok": false, "error": { "code": "HTTP_ERROR" } }
{ "ok": false, "error": { "code": "RATE_LIMITED" } }
{ "ok": false, "error": { "code": "DNS_ERROR" } }
{ "ok": false, "error": { "code": "CONNECTION_ERROR" } }
{ "ok": false, "error": { "code": "UPSTREAM_TIMEOUT" } }
{ "ok": false, "error": { "code": "INSUFFICIENT_EVIDENCE" } }
```

`URL_BLOCKED` for invalid/disallowed initial URL or invalid arguments/unknown fields; `REDIRECT_BLOCKED` for invalid/disallowed/excessive redirect; `MISSING_CONFIG` when a required dependency (search transport or vertical transport) is absent or `None`. `PROVIDER_BLOCKED` for provider-side denial with no retry, fallback, bypass, or raw HTML leakage. `HTTP_ERROR`, `RATE_LIMITED`, `DNS_ERROR`, `CONNECTION_ERROR`, `UPSTREAM_TIMEOUT` for typed transport failures; `INSUFFICIENT_EVIDENCE` for answer/filter with no direct complete-sentence evidence. Normalized shape is `{'ok': false, 'error': {'code': 'PROVIDER_BLOCKED'}}`; raw legacy shape is `{'error': {'code': 'PROVIDER_BLOCKED'}}`. No internal details or exception text are exposed; only validated `status`/`host`/`retry_after` are preserved on the diagnostic codes (`HTTP_ERROR`, `RATE_LIMITED`, `PROVIDER_BLOCKED`, `REDIRECT_BLOCKED`), all other codes carry no diagnostics. Only these ten codes.

`goat_search` returns `PROVIDER_BLOCKED` for HTTP 403/429, for known 202/200 bot-challenge pages matched by finite exact semantic form markers, and for nonempty anomalous no-SERP 200 bodies with no parsed results and no semantic empty-SERP evidence. All other non-2xx/invalid statuses remain `URL_BLOCKED`. Legitimate no-results remains `{ "ok": true, "results": [] }`, including recognized exact semantic DDG empty-SERP `div` markers (`no-results`, `no-results__message`, `result--no-result`); existing blank-200 and empty-204 compatibility is unchanged. Detection uses only those finite exact markers and semantic empty-SERP evidence, not CAPTCHA/bot words in result titles/snippets.
