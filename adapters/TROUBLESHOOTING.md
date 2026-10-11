# Troubleshooting — GOAT V3

All public failures use a closed set. No stack traces, keys, or host internals leak. Map the code, apply the fix. All successes are `{"ok": true, ...}`; `truncated: true` is not an error.

## Quick table

| Code | Meaning | Typical cause | Fix |
|---|---|---|---|
| `URL_BLOCKED` | URL or argument failed the closed policy before fetch | private host, bad scheme/port, credentials in URL, control chars, non-global IP, unknown field or type error on closed schema | Use public `https://` on 443, no `@`, encode query; drop unknown fields; fix types (booleans/strings for integers) |
| `REDIRECT_BLOCKED` | Redirect unsafe or too many hops | `http`/private host/credentials/bad port, loopback→public origin change, >2 hops | Keep redirects `https` public within gate, same-origin where required, ≤2 hops |
| `MISSING_CONFIG` | Required dependency absent — no fetch attempted | `search` or `vertical_transports` is `None`/non-callable, transport missing in fake fixture, required config not passed | Inject `transport` / provide `deps` via `v3_wiring.WiringDependencies`; supply Hermes callables for live use |

All three appear as `{"ok": false, "error": {"code": "<CODE>"}}`.

## URL_BLOCKED

When: any URL (input, result, endpoint, redirect, crawl link) or argument fails `ssrf_guard.check_url` / closed schema. Includes: `http:`, `file:`, `javascript:`, `http://127.0.0.1/`, `https://10.0.0.5/`, `https://example.org:8080/` (non-443), `https://user:pass@example.org`, `https://example.org/space here`, `limit` instead of `max_results`, `max_results: true`/`"5"`, time `"not-a-date"`, `allowed_domains: ["https://example.org"]` (must be bare host).

```python
from goat-web.plugins.goat-web.tool_schemas import validate_args, SCHEMAS
print(validate_args(SCHEMAS["goat_search"]["parameters"], {"query": "hi", "limit": 2}))  # (False, None) → URL_BLOCKED
print(validate_args(SCHEMAS["goat_search"]["parameters"], {"query": "hi", "max_results": "2"}))  # (False, None)
```

Check: `python3 -B goat-web/scripts/build_plugin_bundle.py --help` confirms the builder still expects `--output` as a fresh directory.

Failures also include malformed HTML/JSON or result URLs not passing the gate (e.g., `duckduckgo.com/l/?uddg=` missing target).

## REDIRECT_BLOCKED

When: a hop after the initial fetch violates the gate or exceeds policy. The built bundle pins official endpoints (`pinned_fetch` timeout 10s, 1 MiB, 0 redirects); any 3xx is `REDIRECT_BLOCKED` before parsing.

```python
def evil(url): return {"body": "{}", "url": "http://127.0.0.1/private"}
from adapters.free_stack import duckduckgo_search
print(duckduckgo_search("q", transport=evil))
# {'ok': False, 'error': {'code': 'REDIRECT_BLOCKED'}}
```

## MISSING_CONFIG

When: a required dependency is not supplied. In V3 wiring the seven tools use explicit `WiringDependencies(search=..., vertical_transports={...})`. Default wiring binds the four pinned official transports lazily; if any transport is `None` or non-callable the handler returns `MISSING_CONFIG` without calling fetch.

| Caller | Missing value | Diagnostic |
|---|---|---|
| `goat_answer` / `goat_filtered_search` | `search` not callable | `MISSING_CONFIG` before candidate synthesis |
| `goat_vertical_search` | `vertical_transports[vertical]` absent | `MISSING_CONFIG` before endpoint call |
| `goat_*` (legacy) | `transport` absent and missing required URL/config | `MISSING_CONFIG` without weaker retry |

```python
from adapters.free_verticals import scholar_search
print(scholar_search("q", transport=None))
# {'ok': False, 'error': {'code': 'MISSING_CONFIG'}}  — no default network in offline test path when transport is None is context-dependent
```

## Adapter specifics

- **RSS watcher** (`adapters/rss_watcher.py`): `id` prefers `guid`/`id`, then `link`, then `sha256:` hash of title+published+summary. `max_items` bounds per poll; overflow remains unseen. Persist via `state_path` JSON `{version, seen}`.
- **Serper / You** (`serper_you_adapter.py`): `SerperClient` requires `endpoint` + `auth_header` + `payload_builder` plus `api_key`; missing pieces → `MISSING_CONFIG` without sending. Serper is marked `experimental/unverified`; You posts JSON to `https://ydc-index.io/v1/search` with `X-API-Key`.
- **Crossref / GDELT / Commons**: `free_verticals` returns safe results only — `scholar` DOI links, `news` GDELT metadata+links, `images` per-file license/credit/URL; records without URLs or required licensing are dropped without download.

## Validate failures

- `test_portable_bundle` failure about missing approved bundle in a fresh scratch is expected outside the staged approval path — rebuild via `build_plugin_bundle.py --output <fresh dir>` and re-check with `--check`.
- `ModuleNotFoundError: _goat_v3_vendor` means you tried to use the source template `goat-web/plugins/goat-web` directly — use the built `/tmp/hermes-goat-web` instead.
- Hermes `validate`/`doctor` flags: run `hermes --help`, `hermes plugins --help`, `hermes plugins validate --help` read-only before scripting; do not assume local-path `install` support if your Hermes reports catalog/git only.

Include in a bug report: exact `error.code`, sanitized host only, `source`/`transitions` where relevant, and a minimal `FakeTransport` repro. Do not paste private hostnames, cloud metadata (`169.254.169.254`), or keys.
