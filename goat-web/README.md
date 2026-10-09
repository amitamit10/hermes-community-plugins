# hermes-goat-web

A Hermes Agent extension package for bounded public-web search, text extraction, crawling, and URL diagnostics. The declared tools are:

- `goat_search` — search the public web and return bounded results.
- `goat_extract` — retrieve and extract readable text from a public URL.
- `goat_crawl` — crawl a bounded set of public pages within policy limits.
- `goat_probe` — inspect whether a public URL is reachable and report basic response information.

Safety boundaries: this extension is not for stealth, proxy rotation, CAPTCHA solving, or bypassing access controls. The URL-policy gate itself requires no credentials. Provider API keys are needed only for paid backends; if a required key is absent, that operation must fail closed with `MISSING_CONFIG`. The package must not silently weaken policy limits. No network service is started or required by the package.

Public-safe review status: the audited snapshot had nine `test_*.py` files (51 unittest cases), along with the URL gate, audit script, and skill documentation. A later working-tree rerun differs; see [the QA report](references/qa-report.md). The audit is a narrow heuristic: it checks four secret-marker byte strings, two configured workspace/home absolute-path prefixes, `.env`/`auth`-style names, symlinks, and scan errors. An `OK` result is not a comprehensive secret scan or a full release gate. A complete independent public-safe review has not been completed in this packaging pass, and no release approval is claimed. Do not treat this staging tree as release-approved.

Publication requires explicit human approval.
