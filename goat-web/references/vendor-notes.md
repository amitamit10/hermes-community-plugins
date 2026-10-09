# Vendor metadata notes

Retrieval date: 2026-10-09

Scope: stable release and direct runtime dependency metadata for the listed distributions. Optional extras are excluded. SPDX identifiers below were verified via project/package metadata; the full LICENSE files were not read.

## Trafilatura

- Current stable version: 2.3.0
- SPDX license: Apache-2.0
- Official source: https://github.com/adbar/trafilatura
- Upstream source tag: `v2.3.0`; tag commit SHA: `6c1977a00b4e82ebb7e6fad1192467adaf24d430`
- Package metadata: https://pypi.org/project/trafilatura/2.3.0/ (PyPI version `2.3.0`)
- Direct runtime dependencies: certifi; charset_normalizer >=3.5.2; courlan >=1.4.0; htmldate >=1.11.0; justext >=3.0.2; lxml >=6.1.3; urllib3 >=2.8.0,<3.
- Plan: vendored (local dependency; no external service required).

## Crawlee for Python (Apify)

- Distribution: `crawlee`
- Current stable version: 1.10.3
- SPDX license: Apache-2.0
- Official source: https://github.com/apify/crawlee-python
- Package metadata: https://pypi.org/project/crawlee/1.10.3/
- Direct runtime dependencies: async-timeout >=5.0.1; cachetools >=5.5.0; colorama >=0.4.0; impit >=0.13.2; more-itertools >=10.2.0; proclimits >=0.2.0; protego >=0.5.0; psutil >=6.0.0; pydantic-settings >=2.12.0; pydantic >=2.11.0; tldextract >=5.3.0; typing-extensions >=4.10.0; yarl >=1.18.0.
- Optional integration/feature extras (such as Playwright, HTTPX, and BeautifulSoup) are not included in that base dependency list.
- Plan: vendored (local dependency; no external service required).

## feedparser

- Current stable version: 6.0.14
- SPDX license: BSD-2-Clause
- Official source: https://github.com/kurtmckee/feedparser
- Package metadata: https://pypi.org/project/feedparser/6.0.14/
- Direct runtime dependencies: feedparser-sgmllib >=2,<3.
- Plan: vendored (local dependency; no external service required).

## readability-lxml

- Current stable version: 0.9
- SPDX license: Apache-2.0
- Official source: https://github.com/buriy/python-readability
- Upstream source tag: `0.9`; tag commit SHA: `7159b09ad688378779294cbb5d9f3cfa3274368f`
- Package metadata: https://pypi.org/project/readability-lxml/0.9/ (PyPI version `0.9`)
- Direct runtime dependencies: chardet >=5.2.0,<6.0.0; cssselect >=1.2,<1.3 for Python <3.9 or >=1.3,<1.4 for Python >=3.9; lxml >=5.4,<7; lxml-html-clean >=0.4.2,<0.5.0 (subject to the package's environment markers).
- Plan: vendored (local dependency; no external service required).

## Verification note

Versions, license identifiers, and direct dependency constraints were taken from the linked PyPI project metadata; the source SHAs above resolve the corresponding upstream tags. The license check was metadata-only, not a full read of any LICENSE file. No packages were installed.
