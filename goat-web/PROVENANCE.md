# Provenance

Component-level provenance for this package. Original components are covered by the project MIT license. The extraction and package entries below are references only; no Mozilla Readability, Trafilatura, or readability-lxml implementation code is copied or vendored.

| Component | Status | Source URL | License SPDX |
|---|---|---|---|
| `url_gate` | original | — (original work; no external source) | MIT |
| `goat_tools.py` | original | — (original work; no external source) | MIT |
| `adapters.py` | original dependency-free adapter implementation; extraction is a documented placeholder, not copied/vendor code | — (original work; no external source) | MIT |
| `__init__.py` | original Hermes directory-plugin wrapper and JSON-schema registration | — (original work; no external source) | MIT |
| `plugin.yaml` | original directory-plugin manifest/configuration | — (original work; no external source) | MIT |
| `hermes-goat-web.plugin.json` | original legacy plugin manifest/configuration | — (original work; no external source) | MIT |
| Audit script | original | — (original work; no external source) | MIT |
| Test 1 | original | — (original work; no external source) | MIT |
| Test 2 | original | — (original work; no external source) | MIT |
| Test 3 | original | — (original work; no external source) | MIT |
| Test 4 | original | — (original work; no external source) | MIT |
| Test 5 | original | — (original work; no external source) | MIT |
| Skill docs | original | — (original work; no external source) | MIT |
| MIT license text | adapted from the non-versioned OSI MIT page; project copyright notice/line wrapping customized; canonical SPDX text reference pinned at commit `279b7e997a87c09be00dd6bdda189519ade502cf` | https://opensource.org/license/mit/; https://github.com/spdx/license-list-data/blob/279b7e997a87c09be00dd6bdda189519ade502cf/text/MIT.txt | MIT |
| Mozilla-Readability-inspired extraction approach | design reference only; no code copied or implemented in this tree | https://github.com/mozilla/readability/tree/ab4027a8b37669745016869a37a504727992b2ba (reference commit `ab4027a8b37669745016869a37a504727992b2ba`) | Apache-2.0 |
| Trafilatura reference | PyPI/source reference only; no code copied or vendored; PyPI `trafilatura==2.3.0` | https://pypi.org/project/trafilatura/2.3.0/; upstream tag `v2.3.0`, commit `6c1977a00b4e82ebb7e6fad1192467adaf24d430` | Apache-2.0 |
| `readability-lxml` reference | PyPI/source reference only; no code copied or vendored; PyPI `readability-lxml==0.9` | https://pypi.org/project/readability-lxml/0.9/; upstream tag `0.9`, commit `7159b09ad688378779294cbb5d9f3cfa3274368f` | Apache-2.0 |

## Loader compatibility

The directory-plugin loader uses `plugins/goat-web/plugin.yaml` and its `__init__:register` entrypoint, which receives the Hermes plugin context and registers the four schema-backed tools. The legacy loader manifest, `hermes-goat-web.plugin.json`, instead points to the no-argument `goat_tools.register` entrypoint, which returns the name-to-handler mapping. These are intentionally distinct loader contracts over the same implementation; the YAML entrypoint is the active directory-plugin registration path.

The reference revisions and PyPI release versions were checked on 2026-10-09. See [`references/vendor-notes.md`](references/vendor-notes.md) for package metadata and dependency details. These are not runtime dependencies of this package.
