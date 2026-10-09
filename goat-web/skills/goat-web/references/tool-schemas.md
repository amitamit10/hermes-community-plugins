# Tool schemas

The schemas below define the public contract. Inputs are strict: each registered JSON schema sets `additionalProperties: false`, and unknown fields return the public `URL_BLOCKED` error rather than changing the requested operation. Apply the URL policy in [url-policy.md](url-policy.md) wherever a URL is accepted.

## `goat_search`

Input:

```text
{
  query: string (required, non-empty),
  max_results: integer (optional, default 5, range 1..5)
}
```

`max_results` values that are not integers use the default of 5. Integer values outside 1..5 return `URL_BLOCKED`.

Success result:

```text
{
  results: [
    { title: string, url: string, snippet: string }
  ]
}
```

Search only. Do not fetch, open, probe, or crawl result URLs. The success object contains only `results`, and its count must not exceed `max_results`.

## `goat_extract`

Input:

```text
{ url: string (required, one URL) }
```

Success result:

```text
{
  url: string,
  final_url: string,
  status: integer,
  title: string,
  text: string (maximum 8000 characters),
  truncated: boolean
}
```

Retrieve and extract readable text from only the supplied page, following only policy-compliant redirects. Do not recursively fetch links. `url` is the requested input URL; `final_url` is the last validated URL after redirects. `text` is normalized readable text, not raw HTML. Set `truncated` when extracted text exceeds the character limit and return only the first 8,000 characters. The success object contains only the fields shown above.

## `goat_crawl`

Input:

```text
{
  url: string (required, starting URL),
  max_depth: integer (optional, default 2, range 0..2),
  max_pages: integer (optional, default 10, range 1..10)
}
```

`max_depth` and `max_pages` must be integers within their documented ranges; other types or out-of-range values return `URL_BLOCKED`.

Success result:

```text
{
  pages: [
    {
      url: string,
      depth: integer,
      status: integer,
      title: string,
      text: string (maximum 8000 characters),
      truncated: boolean
    }
  ]
}
```

Use breadth-first search. The starting page is depth zero and counts toward `max_pages`. Follow only links with the same origin as the starting URL (same HTTPS scheme, normalized hostname, and effective port). Visit each normalized URL at most once. Do not exceed either bound; cap each page's text at 8,000 characters. Each page's `url` is the requested URL, and its `truncated` flag applies to that page's text. Validate every discovered URL before requesting it. The success object contains only `pages`; there is no crawl-wide status or truncation field.

## `goat_probe`

Input:

```text
{ url: string (required, one URL) }
```

Success result:

```text
{ ok: boolean, status: integer | null, host: string }
```

Check reachability only. Do not read or return response content. `status` is the HTTP status when one is received, otherwise `null`; `host` is the normalized hostname. Do not add fields to this result.

## Fail-closed errors

For policy or required-configuration failures, return an error with one of these codes and stop:

```text
{ error: { code: "URL_BLOCKED" } }
{ error: { code: "REDIRECT_BLOCKED" } }
{ error: { code: "MISSING_CONFIG" } }
```

Use `URL_BLOCKED` for an invalid or disallowed initial URL; use `REDIRECT_BLOCKED` for an invalid, disallowed, excessive, or failed-revalidation redirect; use `MISSING_CONFIG` when a required search-provider or network configuration is absent. Never turn an error into a less-restricted request.
