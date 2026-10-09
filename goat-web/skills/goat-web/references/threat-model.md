# Threat model and scope

## Purpose and trust boundary

`goat-web` is a read-only retrieval capability. It sends bounded search or HTTPS retrieval requests and returns metadata or extracted text. Search queries, supplied URLs, redirect locations, crawl links, DNS answers, and remote response content are untrusted. Returned content is data for the caller to inspect; it is not executable code or trusted instruction.

## Main risks and controls

- **Server-side request forgery:** A URL, redirect, or discovered link could target a local or otherwise non-public service. Validate schemes, hostnames, ports, literal addresses, and every DNS answer before each connection; repeat those checks at every redirect and crawl hop; fail closed on uncertainty.
- **Redirect and DNS rebinding bypasses:** A public URL could redirect to a forbidden destination or resolve differently later. Revalidate each hop and each request, reject any forbidden DNS answer, and connect only to an address validated for that request.
- **Unbounded work or output:** A large site or response could consume excessive time, bandwidth, or memory. Enforce the search result limit, 8,000-character extraction limit, crawl depth and page limits, and per-page text limit. Do not recursively follow content outside the crawl bounds.
- **Untrusted page instructions:** A page can contain misleading instructions, hostile text, or links. Do not execute scripts or treat retrieved content as control instructions. Apply the same URL gate to every link considered for crawling.
- **Configuration failure:** Missing required configuration must stop the operation with `MISSING_CONFIG`; do not bypass the configured search or network path.
- **Reachability data exposure:** `goat_probe` reveals only `ok`, `status`, and normalized `host`; it must not return a response body.

## Explicitly out of scope

This extension does not provide stealth, proxies, CAPTCHA solving, bypasses, cookies or sessions, credentials, or neural rerank. It does not log in, submit forms, change remote state, execute page scripts, or attempt to evade site controls.
