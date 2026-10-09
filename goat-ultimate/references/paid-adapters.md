# Paid search/browser adapter reference

Retrieved: 2026-10-09

Scope: read-only research from official provider documentation/sites. No signups, keys, installs, or API requests were made.

## Router contract — required behavior, not a provider claim

For every provider adapter configured as `requires_key=true`, check for its configured key before making any provider request. If it is absent, return `MISSING_CONFIG` immediately. Make zero provider calls and do not silently fall back to another provider, a local search implementation, or a provider's unauthenticated/free interface. In particular, You.com's free MCP profile is a separate capability, not a fallback for its keyed API adapter. Any future keyless/payment-auth flow should be an explicitly separate adapter, not implicit behavior.

## Provider details

### Exa — VERIFIED

- Search: `POST https://api.exa.ai/search`.
- Extract: `POST https://api.exa.ai/contents` for known URLs/document IDs. Search can also return content for results using its `contents` options.
- Crawl: no separate crawl endpoint identified in the reference. `/contents` performs content retrieval/live-crawl fallback and supports `subpages` for linked-page crawling.
- Auth: `x-api-key: <key>`; docs also accept `Authorization: Bearer <key>`.
- Free tier: $10 in credits on signup; free balance resets to $10 on the first of each month. The pricing page says this is up to 2,500 Instant searches. Completing dashboard onboarding gives the first team a one-time additional $10 bonus. No payment method required.
- Sources: [Search](https://exa.ai/docs/reference/search), [Contents](https://exa.ai/docs/reference/get-contents), [Pricing](https://exa.ai/docs/reference/pricing).

### Tavily — VERIFIED

- Search: `POST https://api.tavily.com/search`.
- Extract: `POST https://api.tavily.com/extract` (one URL or batches up to 20 URLs).
- Crawl: `POST https://api.tavily.com/crawl`.
- Auth: `Authorization: Bearer <key>`.
- Free tier: 1,000 API credits per month, no credit card required. Basic Search costs 1 credit/request; Advanced Search costs 2. Basic Extract costs 1 credit per 5 successful URL extractions; Advanced Extract costs 2 credits per 5. Crawl combines mapping and extraction charges.
- Sources: [Search](https://docs.tavily.com/documentation/api-reference/endpoint/search), [Extract](https://docs.tavily.com/documentation/api-reference/endpoint/extract), [Crawl](https://docs.tavily.com/documentation/api-reference/endpoint/crawl), [Credits & Pricing](https://docs.tavily.com/documentation/api-credits).

### Serper — PARTIALLY VERIFIED

- Search: candidate `POST https://google.serper.dev/search` — UNVERIFIED from accessible first-party API documentation; do not wire this endpoint based on this note alone.
- Extract: no separate first-party extract endpoint verified.
- Crawl: no first-party crawl endpoint verified.
- Auth: header scheme UNVERIFIED from accessible first-party API documentation. Do not assume a header name without confirming in Serper's API reference/playground.
- Free tier: 2,500 free queries; the official homepage says no credit card is required. Its accessible page does not specify whether the quota renews or is one-time.
- Status: the official homepage confirms the SERP API product and free-query offer, but the accessible API playground/reference did not expose endpoint/auth details in this retrieval. Treat endpoint, auth, extract, and crawl capability as unverified.
- Sources: [Official Serper homepage](https://serper.dev/), [Official API playground](https://serper.dev/playground).

### Firecrawl — VERIFIED

- Search: `POST https://api.firecrawl.dev/v2/search`.
- Extract/scrape a known URL: `POST https://api.firecrawl.dev/v2/scrape` (page content in requested formats). Structured extraction is separately available at `POST https://api.firecrawl.dev/v2/extract`.
- Crawl: `POST https://api.firecrawl.dev/v2/crawl`.
- Auth: `Authorization: Bearer <key>`.
- Free tier: 1,000 credits/month, refreshed monthly; no card required. Basic scrape/crawl/map costs 1 credit per page; Search costs 2 credits per 10 results. So the free balance is about 1,000 basic pages or 500 ten-result searches, before mixing endpoint usage or add-ons.
- Sources: [Search](https://docs.firecrawl.dev/api-reference/endpoint/search), [Scrape](https://docs.firecrawl.dev/api-reference/endpoint/scrape), [Crawl](https://docs.firecrawl.dev/api-reference/endpoint/crawl), [Extract](https://docs.firecrawl.dev/api-reference/endpoint/extract), [Pricing](https://www.firecrawl.dev/pricing).

### You.com — VERIFIED

- Search: `POST https://ydc-index.io/v1/search` (GET is also supported for legacy/simple requests; docs say new features, including `extraction`, are POST-only). Search can return query highlights or full-page content using `extraction`; full-page mode crawls result pages.
- Extract known URLs: `POST https://ydc-index.io/v1/contents` (up to 10 URLs per request; returns Markdown/HTML/metadata).
- Crawl: no separate crawl endpoint identified in the API reference. The Contents API fetches/crawls known URLs; full-page extraction is available through Search.
- Auth: `X-API-Key: <key>`.
- Free tier: new API accounts receive $100 in free API credits, no credit card required. Separately, You.com documents an unauthenticated MCP free profile limited to search and 100 queries/day; Contents and the other non-search tools are excluded. This is not the keyed API adapter's missing-key fallback.
- Sources: [Search API](https://you.com/docs/api-reference/search/v1-search), [Contents API](https://you.com/docs/api-reference/contents), [Billing & Credits](https://you.com/docs/administration/billing), [MCP free profile](https://you.com/docs/build-with-agents/mcp-server).

## Retrieval/tool limitation

`web_search` was used to locate official provider pages. `web_extract` was attempted on official documentation URLs but the configured extraction backend returned that it is search-only and cannot extract page content. Endpoint and quota details marked VERIFIED were therefore checked against the corresponding official pages in the browser. Serper fields above are explicitly marked unverified where the accessible first-party pages did not substantiate them.
