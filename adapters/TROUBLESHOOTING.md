# GOAT Packs — Troubleshooting

All public failures use a closed set of error codes. No stack traces, provider keys, or internal diagnostics are exposed. Map the code, find the cause, apply the fix.

## Quick table

| Code | Meaning | Typical cause | Fix |
|---|---|---|---|
| `URL_BLOCKED` | URL failed public-HTTPS gate before any fetch, or response/body was malformed | private host, bad scheme/port, credentials in URL, control chars, non-global IP, truncated/malformed payload | Use a public `https://` URL on port 443; strip credentials; re-encode query; check payload shape |
| `REDIRECT_BLOCKED` | A redirect was unsafe or exceeded the limit | redirect to `http`/private host/different origin (crawl), userinfo/port violation, >2 hops, final URL outside gate | Follow only `https` same-public redirects; cap at 2 hops; for crawl keep same origin |
| `MISSING_CONFIG` | Required configuration absent — no fetch attempted | `SearXNG` `base_url`/`instance_url` missing, `provider_config=None`, transport `None` without default | Supply `base_url="https://search.example"` (free_search) or `instance_url` (free_stack); pass an injected `transport` for tests |

All three appear as `{"error": {"code": "<CODE>"}}`. Success is `{"ok": True, ...}`; `truncated=True` is not an error — it signals >5 results or >8000-char text.

---

## URL_BLOCKED

**When:** any URL (input, result, `base_url`, redirect target) fails `ssrf_guard.check_url` / `free_stack._check_url`. Also when a response body is not valid HTML/JSON, or a result URL is not `https` public — e.g., `javascript:`, `file:`, `http:`, or `duckduckgo.com` redirect without `uddg`.

**Common examples:**

- `http://example.org` → `https://example.org` (staging/packs require `https`; `free_stack` SearXNG instance is the only `http://localhost` exception)
- `https://user:pass@example.org` → strip credentials
- `https://127.0.0.1/`, `https://10.0.0.5/`, `https://[::1]/`, `https://intranet.local/` → private/loopback/link-local → blocked by design
- `https://example.org:8080/search` → non-443 port → blocked (omit port; 443 is implied)
- `https://example.org/search with space` → control char → percent-encode query (`q=...` via `urlencode`)
- `javascript:alert(1)` or `//duckduckgo.com/l/?uddg=` missing target → result URL discarded

**Checks:**

```python
from ssrf_guard import check_url
print(check_url("https://example.org/p"))      # (True, None) expected
print(check_url("http://example.org/p"))       # (False, 'URL_BLOCKED')
print(check_url("https://user:pass@example.org")) # (False, URL_BLOCKED)
```

**Fix:** use `https://` public hostname, no port, no `@`, encode with `urllib.parse.urlencode`; for `free_search.searxng_search` pass `base_url="https://search.example/"` without query/fragment; for `free_stack` keep default `http://localhost:8888` or a validated `http(s)` loopback.

**Also check:** `free_search` and `native_tier` bound max_results to 5 and snippet/text to 8000 chars; a 0-limit is not an error but returns empty results with `truncated=True`. Wikipedia `OpenSearch` (free_search) vs `Action API` (free_stack) both map malformed JSON to `URL_BLOCKED`.

---

## REDIRECT_BLOCKED

**When:** a hop after the initial fetch points outside the public gate, or exceeds policy.

- Initial URL passes but `final_url`/`Location` is `http`, private, credentials, bad port, or cross-origin (crawl).
- More than 2 redirects (both `free_search` pinned fetch and `free_stack` loop guard).
- `goat-browser-staging` browser/crawl: same-origin redirect required; `free_stack` also blocks loopback→public origin change.

**Examples:**

```python
from free_search import duckduckgo_search
# Fake transport that hides a redirect via final_url:
def evil(url): return {"body": "{}", "url": "http://127.0.0.1/private"}
print(duckduckgo_search("q", transport=evil))
# {'error': {'code': 'REDIRECT_BLOCKED'}}

from free_stack import searxng_search
# Loopback SearXNG redirecting to public host is blocked:
def redirecting(url): return {"status": 302, "headers": {"Location": "https://example.org"}, "body": ""}
print(searxng_search("q", instance_url="http://localhost:8888", transport=redirecting))
# {'error': {'code': 'REDIRECT_BLOCKED'}}
```

**Checks:**

- Inspect `transport` return: if you use `{"url": final_url}` or `Location:` header, that value must itself pass `check_url` with `https` on 443 (or loopback for the pinned SearXNG instance).
- For `crawl_pro`, every link enqueued must be same-origin as `start_url`; robots `Disallow` that yields `("/" ,)` blocks the crawl rather than returning `REDIRECT_BLOCKED`.

**Fix:** ensure targets only redirect within `https://` public space; keep hops ≤2; for local SearXNG keep redirects loopback-only; for crawls, seed with canonical `https://host/` and author only same-origin links.

---

## MISSING_CONFIG

**When:** a required provider address/key is not supplied — the pack never attempts a fetch.

| Caller | Missing value | Diagnostic |
|---|---|---|
| `free_search.searxng_search` | `base_url` and `provider_config["base_url"]` both empty/None | Returns `MISSING_CONFIG` before `transport` is called |
| `free_stack.searxng_search` | `instance_url` is `None`/`""` or unreachable (`OSError` on default) | Returns `MISSING_CONFIG`; no fallback hops counted |
| `native_tier.native_search/native_extract` | `web_search`/`web_extract` is `None` | Returns `MISSING_CONFIG` without calling the tier |
| `free_search.duckduckgo_search(..., provider_config=None)` | explicit `None` signals unconfigured provider | `MISSING_CONFIG` even with a valid transport (test: `test_errors_follow_goat_public_codes`) |
| `free_stack.fallback_chain` | first provider was `MISSING_CONFIG` | Stops immediately even if `allow_fallback=True`; `source` is that provider, no extra transport calls |

**Examples:**

```python
from free_search import searxng_search
print(searxng_search("q"))  # {'error': {'code': 'MISSING_CONFIG'}} — no base_url
print(searxng_search("q", base_url="https://search.example", transport=lambda u: {"results": []}))
# {'ok': True, ...} — now configured

from free_stack import searxng_search as fs_search
print(fs_search("q", instance_url=None, transport=lambda u: {"results": []}))
# {'error': {'code': 'MISSING_CONFIG'}} — transport not called

from free_search import duckduckgo_search
print(duckduckgo_search("q", transport=lambda u: "ok", provider_config=None))
# {'error': {'code': 'MISSING_CONFIG'}}
```

**Fix:** pass `base_url="https://search.example"` (free_search, must be `https` without query) or `instance_url="http://localhost:8888/"` (free_stack, loopback allowed only there). For tests, always inject a `transport` and a valid URL; `MISSING_CONFIG` tests assert `transport.calls == []` to prove no fetch was attempted.

---

## Validate failures

- `ImportError: No module named 'ddg_parser'` / `url_gate` — you copied a subset. Recopy the full `goat-packs/` directory; `QUICKSTART.md` step 1 validates this.
- `Ran 177 tests OK` expected; `160 tests` means the old staging-`PYTHONPATH` workaround is still assumed — update to the vendored `url_gate.py` + `ddg_parser.py` (no `PYTHONPATH` needed).
- `fuzz_gate.py` 4288/0 expected; any failure is a gate regression, not a network issue (the fuzzer is deterministic and offline).

## Getting help

Include in a bug report: pack commit, the exact `error.code`, the sanitized URL host (no private IP, no credentials), `source`/`transitions` for fallback, and a minimal `FakeTransport` repro. Do not paste private hostnames, cloud metadata (`169.254.169.254`), or provider keys.
