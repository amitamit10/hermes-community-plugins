# URL and SSRF policy

This policy applies to every URL supplied to `goat_extract`, `goat_crawl`, or `goat_probe`, and to every redirect or crawl link before it is requested.

## Accepted URLs

- Accept HTTPS URLs only. Reject `http`, `file`, `ftp`, `data`, `javascript`, and every other scheme.
- Reject URLs containing username or password userinfo.
- Accept port 443 only. If the URL omits a port, use 443; accept an explicitly supplied port only when it parses as 443. Reject malformed, out-of-range, and all other ports (fail closed).
- Parse and normalize the hostname before checking it. Do not allow alternate encodings, trailing dots, or case differences to evade the checks.
- A URL that fails parsing or policy validation is rejected before any network request.

## Destination checks

Reject these hostnames, including subdomains where applicable: `localhost`, names ending in `.local`, and names ending in `.internal`.

For IP literals and DNS results, reject loopback, private, link-local, multicast, reserved, unspecified, and otherwise non-public addresses. This includes at least `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1`, `fe80::/10`, and `0.0.0.0`. Check both IPv4 and IPv6 answers; if a hostname resolves to multiple addresses and any address is forbidden, reject the hostname. Account for IPv4-mapped IPv6 addresses as their mapped IPv4 address.

Resolve and validate the destination before connecting. Connect only to an address that was validated for that request, while retaining the original hostname for HTTPS certificate validation and the request host. Recheck DNS results for each new request rather than trusting an earlier lookup.

## Redirects

Allow no more than two redirects. Follow HTTPS-to-HTTPS redirects only. Resolve relative redirect locations against the current URL, then parse and fully revalidate the destination—including scheme, userinfo, hostname, DNS answers, and port—before following each hop. Do not downgrade to HTTP or continue after a blocked or invalid redirect.

An invalid initial URL returns `URL_BLOCKED`. A redirect that is invalid, disallowed, exceeds the hop limit, or fails revalidation returns `REDIRECT_BLOCKED`. Missing required search or network configuration returns `MISSING_CONFIG`. All three conditions stop the operation; never retry them with weaker checks or a fallback transport.

## Scope of requests

Use retrieval requests only. Do not send credentials, cookies, session state, or other user-specific authorization data. Do not execute page scripts. Search returns search-provider results and must not fetch the URLs in those results.
