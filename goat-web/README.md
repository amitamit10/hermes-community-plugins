# hermes-goat-web

Local release candidate `0.2.0` for bounded public-web search, extraction, crawling, and probing on Hermes Agent. Declared tools (seven, closed schemas):

- `goat_search` — bounded search (DuckDuckGo HTML); returns `results` ≤ `max_results`
- `goat_extract` — one public HTTPS page; returns `url`, `final_url`, `status`, `title`, `text` ≤8000, `truncated`
- `goat_crawl` — same-origin BFS; `max_depth` 0..2, `max_pages` 1..10; returns `pages`
- `goat_probe` — reachability only; returns `ok`, `status`, `host` (no body)
- `goat_answer` — deterministic extractive answer over ≤5 Wikipedia Action API snippets; returns `answer` with numbered URL citations plus `sources`; no page fetch, no LLM
- `goat_filtered_search` — filtered Wikipedia Action API search by inclusive UTC time, domains, language; active filters exclude missing metadata without inference
- `goat_vertical_search` — one official keyless vertical: `scholar`=Crossref, `news`=GDELT, `images`=Wikimedia Commons; returns provider/source links and per-file image licensing

All tools share a closed JSON schema (`additionalProperties: false`). Unknown fields, type errors, and policy blocks return a sanitized `ok:false` envelope with one of `URL_BLOCKED`, `REDIRECT_BLOCKED`, `MISSING_CONFIG`.

Safety boundaries: no stealth, proxy rotation, CAPTCHA solving, or bypass. URL-policy gate applies to every input URL, redirect, and crawl link. Provider keys only for paid backends; missing key fails closed (`MISSING_CONFIG`). No network service is started by the package.

## Source template vs standalone bundle

`goat-web/plugins/goat-web/` is a source template — it imports `._goat_v3_vendor`, which exists only inside a built bundle. Only the output of the builder is standalone.

```sh
# portable build, no pip install, no PYTHONPATH
python3 -B goat-web/scripts/build_plugin_bundle.py --help
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
# ok /tmp/hermes-goat-web
ls /tmp/hermes-goat-web/bundle-manifest.json
```

Validate a built bundle read-only (isolated, no install or enable):

```sh
hermes plugins validate /tmp/hermes-goat-web
```

Manifest `goat-web/plugins/goat-web/plugin.yaml` declares `name: hermes-goat-web` version `0.2.0`, entrypoint `__init__:register`. Directory `goat-web` and ID `hermes-goat-web` are aligned — Hermes commands use the manifest ID.

Status: local candidate from this checkout. No published release, tag, or live activation is claimed. Publication or enable requires explicit human approval and a re-run of `validate`/`doctor` on the exact built bundle. The vendored `_goat_v3_vendor/` inside the bundle mirrors `adapters/` allowlist (answer/filter/vertical/stack/guard/parser plus `result_contract`).
