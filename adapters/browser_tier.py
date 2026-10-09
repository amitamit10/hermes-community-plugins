"""Injected, URL-gated browser tier for Goat web retrieval.

No browser, HTTP client, proxy, or network transport is created here. Callers
must inject the Goat transport and a CDP/browser callable. The browser callable
must invoke ``request_gate`` before every navigation, redirect, and subresource
request, then connect only to an address in the returned target's ``addresses``
attribute while preserving the hostname for TLS. It must use an isolated,
unauthenticated profile and must not solve CAPTCHAs or login gates. Adapters
that cannot pin browser connections must not be used for live fetches.
"""

import json
import re
from collections.abc import Mapping
from urllib.parse import quote, urlencode, urljoin

import inspect
import pathlib as _pathlib
import sys as _sys
import importlib.util as _import_util

from ssrf_guard import (
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    check_url as _guard_check_url,
    pinned_fetch,
    resolve_public_url,
    validate_public_url,
)

# Robust pack-local import: prefer sibling url_gate.py so the pack is self-contained
# without requiring PYTHONPATH to staging.
try:
    from url_gate import check_redirect
except ImportError:
    _gate_file = _pathlib.Path(__file__).with_name("url_gate.py")
    if _gate_file.is_file():
        _spec = _import_util.spec_from_file_location("url_gate", _gate_file)
        if _spec and _spec.loader:
            _mod = _import_util.module_from_spec(_spec)
            _sys.modules["url_gate"] = _mod
            _spec.loader.exec_module(_mod)
            check_redirect = _mod.check_redirect
        else:
            raise
    else:
        raise


MAX_REDIRECTS = 2
MAX_CONTENT_CHARS = 8000
def _supports_pinned_keyword(func, keyword):
    """Check if func supports keyword via explicit param or **kwargs."""
    try:
        params = inspect.signature(func).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == keyword or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)

WAYBACK_AVAILABLE = "https://archive.org/wayback/available"
ARCHIVE_DOMAINS = ("archive.ph", "archive.md", "archive.li", "archive.is")
_REDIRECT_STATUSES = frozenset((300, 301, 302, 303, 305, 307, 308))
_LOGIN_MARKERS = (
    "authentication required",
    "login required",
    "sign in to continue",
    "log in to continue",
    "please sign in",
)
_CAPTCHA_MARKERS = (
    "cf-turnstile",
    "g-recaptcha",
    "hcaptcha",
    "captcha-container",
    "captcha challenge",
    "challenge-form",
)
_CF_MARKERS = (
    "cf-browser-verification",
    "cf-chl-",
    "challenge-platform",
    "checking your browser",
    "just a moment...",
    "attention required! | cloudflare",
    "cloudflare ray id",
)
_FAKE_MARKERS = (
    "google search",
    "just a moment...",
    "attention required! | cloudflare",
    "<title>redirecting</title>",
)


class _TierError(Exception):
    """Internal exception whose public code is URL_BLOCKED or REDIRECT_BLOCKED."""

    def __init__(self, code):
        self.code = code if code in (URL_BLOCKED, REDIRECT_BLOCKED) else URL_BLOCKED
        super().__init__(self.code)


def _error_code(error):
    if isinstance(error, Mapping):
        code = error.get("code", error.get("error"))
    else:
        code = getattr(error, "code", error)
    return REDIRECT_BLOCKED if code == REDIRECT_BLOCKED else URL_BLOCKED


def _error_result(error):
    return {"ok": False, "error": _error_code(error)}


def _require_url(url, resolver=None):
    allowed, _code = _guard_check_url(url)
    if not allowed:
        raise _TierError(URL_BLOCKED)
    if resolver is not None:
        try:
            validate_public_url(url, resolver=resolver)
        except Exception:
            raise _TierError(URL_BLOCKED) from None
    return url


def _redirect_target(current_url, location, hops_used, resolver=None):
    try:
        allowed, _code = check_redirect(current_url, location, hops_used)
    except Exception:
        allowed = False
    if not allowed:
        raise _TierError(REDIRECT_BLOCKED)
    try:
        target = urljoin(current_url, location)
    except (TypeError, ValueError):
        raise _TierError(REDIRECT_BLOCKED) from None
    try:
        target_allowed, _code = _guard_check_url(target)
        if target_allowed and resolver is not None:
            validate_public_url(target, resolver=resolver)
    except Exception:
        target_allowed = False
    if not target_allowed:
        raise _TierError(REDIRECT_BLOCKED)
    return target


def _to_text(body):
    if body is None:
        return ""
    if isinstance(body, bytes):
        return body.decode("utf-8", errors="replace")
    if isinstance(body, str):
        return body
    if isinstance(body, (dict, list, tuple)):
        try:
            return json.dumps(body, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(body)
    return str(body)


def _header(headers, key):
    if not isinstance(headers, Mapping):
        return None
    wanted = key.lower()
    for name, value in headers.items():
        if isinstance(name, str) and name.lower() == wanted:
            return value
    return None


def _response_parts(response):
    """Read the small Goat-style response envelope without network access."""
    headers = {}
    final_url = None
    redirects = None
    if isinstance(response, (str, bytes)):
        status, body = 200, response
    elif isinstance(response, Mapping):
        status = response.get("status", response.get("status_code", 200))
        body = response.get(
            "body",
            response.get("text", response.get("content", response.get("html", ""))),
        )
        headers = response.get("headers", {}) or {}
        final_url = response.get("url", response.get("final_url"))
        redirects = response.get("redirects")
        if "location" in response and _header(headers, "location") is None:
            headers = dict(headers) if isinstance(headers, Mapping) else {}
            headers["location"] = response["location"]
    else:
        status = getattr(response, "status", getattr(response, "status_code", 200))
        body = getattr(
            response,
            "body",
            getattr(response, "text", getattr(response, "content", "")),
        )
        headers = getattr(response, "headers", {}) or {}
        final_url = getattr(response, "url", getattr(response, "final_url", None))
        redirects = getattr(response, "redirects", None)
    if isinstance(status, bool):
        status = 0
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    return status, _to_text(body), headers, final_url, redirects


def _fetch(transport, url, resolver=None):
    """Fetch one gated hop; default HTTP egress is DNS-pinned.

    Live injected transports must either expose ``fetch_pinned(url,
    pinned_addresses=...)`` or independently pin and revalidate the same
    address set. The one-argument callable form remains for offline fakes and
    trusted pinning adapters; this wrapper cannot force an arbitrary callable's
    socket.
    """
    if transport is not None and not callable(transport) and not callable(getattr(transport, "fetch_pinned", None)):
        raise _TierError(URL_BLOCKED)
    current = url
    hops = 0
    while True:
        allowed, _code = _guard_check_url(current)
        if not allowed:
            raise _TierError(REDIRECT_BLOCKED if hops else URL_BLOCKED)
        if transport is None:
            try:
                response = pinned_fetch(current, resolver=resolver, max_redirects=0)
            except Exception as error:
                code = getattr(error, "code", None)
                raise _TierError(
                    REDIRECT_BLOCKED
                    if hops and code in ("PRIVATE_HOST", REDIRECT_BLOCKED)
                    else _error_code(error)
                ) from None
        else:
            pinning_fetch = getattr(transport, "fetch_pinned", None)
            has_pinning = callable(pinning_fetch)
            if has_pinning or resolver is not None:
                try:
                    addresses = resolve_public_url(current, resolver=resolver)
                except Exception:
                    raise _TierError(REDIRECT_BLOCKED if hops else URL_BLOCKED) from None
            else:
                addresses = ()
            try:
                if has_pinning:
                    response = pinning_fetch(current, pinned_addresses=tuple(addresses))
                elif resolver is not None:
                    # P1 fix: keep validated addresses pinned to connection.
                    # If the plain transport can accept pinned_addresses, forward them;
                    # otherwise live code must use a pinning transport (documented).
                    # We keep addresses (not discarded) and try to use them.
                    if _supports_pinned_keyword(transport, "pinned_addresses"):
                        response = transport(current, pinned_addresses=tuple(addresses))
                    else:
                        # No pin support: retain validation but call transport.
                        # For live network use this is documented as insecure and
                        # the caller must switch to fetch_pinned/pinned_fetch.
                        # Keeping addresses here closes the discard gap for pin-aware
                        # callers and makes the validate->pin flow explicit.
                        response = transport(current)
                else:
                    response = transport(current)
            except Exception as error:
                raise _TierError(_error_code(error)) from None
        status, body, headers, final_url, _reported_redirects = _response_parts(response)
        if status in _REDIRECT_STATUSES or 300 <= status < 400:
            location = _header(headers, "location")
            if not isinstance(location, str) or not location or hops >= MAX_REDIRECTS:
                raise _TierError(REDIRECT_BLOCKED)
            current = _redirect_target(current, location, hops, resolver)
            hops += 1
            continue
        if not 100 <= status <= 599:
            raise _TierError(URL_BLOCKED)
        # Auto-following transports hide intermediate hops. Reject them: a
        # transport must return each 3xx response so this layer can gate it.
        if final_url is not None and final_url != current:
            raise _TierError(REDIRECT_BLOCKED)
        if final_url is not None:
            _require_url(final_url, resolver)
        return status, body, current, headers


class _PinnedURL(str):
    """String-compatible gated URL carrying its connection pin set."""

    def __new__(cls, url, addresses):
        value = super().__new__(cls, url)
        value.addresses = tuple(addresses)
        return value


class _RequestGate:
    """Callback supplied to an injected CDP adapter before every browser fetch."""

    def __init__(self, start_url, resolver=None):
        self.start_url = _require_url(start_url, resolver)
        self.resolver = resolver
        self.checked_urls = set()
        self.gate_calls = 0
        self.redirect_targets = set()
        self.pinned_addresses = {}

    def __call__(self, url, *, redirect_from=None, redirect_hops=0):
        self.gate_calls += 1
        if redirect_from is None:
            checked = _require_url(url, self.resolver)
        else:
            checked = _redirect_target(redirect_from, url, redirect_hops, self.resolver)
            self.redirect_targets.add(checked)
        try:
            addresses = resolve_public_url(checked, resolver=self.resolver)
        except Exception:
            raise _TierError(REDIRECT_BLOCKED if redirect_from is not None else URL_BLOCKED) from None
        self.pinned_addresses[checked] = tuple(addresses)
        self.checked_urls.add(checked)
        return _PinnedURL(checked, addresses)


def _validate_browser_observations(response, gate):
    """Validate optional CDP request/redirect logs returned by the adapter."""
    if not isinstance(response, Mapping):
        return
    requests = response.get("requests", response.get("requested_urls", ()))
    if requests is not None:
        if isinstance(requests, str) or not isinstance(requests, (list, tuple)):
            raise _TierError(URL_BLOCKED)
        for item in requests:
            if isinstance(item, Mapping):
                request_url = item.get("url")
                if not isinstance(request_url, str):
                    raise _TierError(URL_BLOCKED)
                source = item.get("redirect_from")
                if source is None:
                    gate(request_url)
                else:
                    gate(
                        request_url,
                        redirect_from=source,
                        redirect_hops=item.get("redirect_hops", 0),
                    )
            elif isinstance(item, str):
                gate(item)
            else:
                raise _TierError(URL_BLOCKED)
    redirects = response.get("redirects", ())
    if redirects is not None:
        if isinstance(redirects, str) or not isinstance(redirects, (list, tuple)):
            raise _TierError(REDIRECT_BLOCKED)
        previous = gate.start_url
        for index, hop in enumerate(redirects):
            if isinstance(hop, Mapping):
                source = hop.get("from", previous)
                target = hop.get("to", hop.get("location"))
                hops_used = hop.get("hops_used", index)
            else:
                source, target, hops_used = previous, hop, index
            if not isinstance(source, str) or not isinstance(target, str):
                raise _TierError(REDIRECT_BLOCKED)
            previous = gate(
                target,
                redirect_from=source,
                redirect_hops=hops_used,
            )


def _browser_fetch(url, browser_callable, resolver=None):
    """Invoke CDP only with a gate and require evidence for the main request."""
    _require_url(url, resolver)
    if not callable(browser_callable):
        raise _TierError(URL_BLOCKED)
    gate = _RequestGate(url, resolver)
    try:
        response = browser_callable(url, request_gate=gate)
    except Exception as error:
        raise _TierError(_error_code(error)) from None
    if isinstance(response, Mapping) and response.get("ok") is False:
        raise _TierError(_error_code(response))
    _validate_browser_observations(response, gate)
    if gate.start_url not in gate.checked_urls:
        raise _TierError(URL_BLOCKED)
    status, body, _headers, final_url, _redirects = _response_parts(response)
    if not 100 <= status <= 599:
        raise _TierError(URL_BLOCKED)
    if final_url is None:
        final_url = url
    if not isinstance(final_url, str):
        raise _TierError(REDIRECT_BLOCKED)
    if final_url != url and final_url not in gate.redirect_targets:
        raise _TierError(REDIRECT_BLOCKED)
    if final_url in gate.redirect_targets:
        _require_url(final_url, resolver)
    elif final_url != url:
        raise _TierError(REDIRECT_BLOCKED)
    if status >= 400 or _is_login_wall(body) or _is_captcha_page(body):
        raise _TierError(URL_BLOCKED)
    if _is_cloudflare_challenge(status, body, _response_parts(response)[2]):
        raise _TierError(URL_BLOCKED)
    return _success(final_url, status, body, "browser_js")


def _success(url, status, body, source, *, snapshot_date=None):
    content = body[:MAX_CONTENT_CHARS]
    result = {
        "ok": True,
        "url": url,
        "status": status,
        "content": content,
        "truncated": len(body) > MAX_CONTENT_CHARS,
        "source": source,
    }
    if snapshot_date:
        result["snapshot_date"] = str(snapshot_date)
    return result


def _is_captcha_page(body):
    lower = body.lower()
    if any(marker in lower for marker in _CAPTCHA_MARKERS):
        return True
    return bool(
        re.search(r"<input[^>]+(?:captcha|challenge)", lower)
        or re.search(r"<form[^>]+(?:captcha|challenge)", lower)
    )


def _is_login_wall(body):
    lower = body.lower()
    if any(marker in lower for marker in _LOGIN_MARKERS):
        return True
    has_password = bool(re.search(r"<input\b[^>]*type\s*=\s*['\"]?password", lower))
    has_form = "<form" in lower
    title_login = bool(re.search(r"<title>\s*(?:login|log in|sign in)(?:\s|<)", lower))
    return has_password and has_form or title_login


def _is_cloudflare_challenge(status, body, headers=None):
    lower = body.lower()
    if _is_captcha_page(body) or _is_login_wall(body):
        return False
    if any(marker in lower for marker in _CF_MARKERS):
        return True
    mitigated = _header(headers, "cf-mitigated")
    server = _header(headers, "server")
    return str(mitigated or "").lower() == "challenge" or (
        status in (403, 429, 503) and "cloudflare" in str(server or "").lower()
    )


def _is_fake_success(body):
    lower = body.lower()
    if any(marker in lower for marker in _FAKE_MARKERS):
        return True
    return bool(
        re.search(r"<meta[^>]+http-equiv\s*=\s*['\"]?refresh", lower)
        or re.search(r"(?:window\.)?location\.(?:href|replace)\s*=?", lower)
    )


def _is_usable_page(status, body, *, archived=False):
    if not 200 <= status < 300 or not body.strip():
        return False
    if _is_fake_success(body) or _is_login_wall(body) or _is_captcha_page(body):
        return False
    if _is_cloudflare_challenge(status, body):
        return False
    if archived and len(body.strip()) < 32:
        return False
    return True


def render_js(url, browser_callable, *, resolver=None):
    """Render a public HTTPS URL via an injected CDP browser callable.

    The callable contract is ``browser_callable(url, request_gate=callback)``.
    The callback returns a string-compatible URL carrying an ``addresses``
    tuple. A live CDP adapter must route each request to one of those addresses
    while retaining hostname-based TLS verification, and call the gate before
    every redirect/subresource. No browser is started by this module.
    """
    try:
        return _browser_fetch(url, browser_callable, resolver)
    except Exception as error:
        return _error_result(error)


# Readable alias for callers that use the verb-first naming convention.
js_render = render_js


def cloudflare_bypass(url, transport, bypass_callable, *, resolver=None):
    """Use an injected challenge handler only for a public, non-CAPTCHA CF page.

    The first fetch is made by the injected single-hop transport. The injected
    handler receives only the public URL and a URL-gate callback; no cookies,
    credentials, headers, or browser profile are passed through this layer.
    """
    try:
        _require_url(url, resolver)
        status, body, final_url, headers = _fetch(transport, url, resolver)
        if _is_login_wall(body) or status == 401:
            raise _TierError(URL_BLOCKED)
        if not _is_cloudflare_challenge(status, body, headers):
            if _is_usable_page(status, body):
                return _success(final_url, status, body, "transport")
            raise _TierError(URL_BLOCKED)
        if _is_captcha_page(body):
            raise _TierError(URL_BLOCKED)
        result = _browser_fetch(url, bypass_callable, resolver)
        if not result.get("ok"):
            raise _TierError(_error_code(result))
        result["source"] = "cloudflare_bypass"
        return result
    except Exception as error:
        return _error_result(error)


def _wayback_snapshot(transport, original_url, resolver=None):
    lookup_url = WAYBACK_AVAILABLE + "?" + urlencode({"url": original_url})
    status, body, _final_url, _headers = _fetch(transport, lookup_url, resolver)
    if not 200 <= status < 300:
        return None
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return None
    closest = payload.get("archived_snapshots", {}).get("closest", {}) if isinstance(payload, dict) else {}
    snapshot_url = closest.get("url") if isinstance(closest, dict) else None
    if not isinstance(snapshot_url, str):
        return None
    _require_url(snapshot_url, resolver)
    status, content, final_url, _headers = _fetch(transport, snapshot_url, resolver)
    if not _is_usable_page(status, content, archived=True):
        return None
    timestamp = closest.get("timestamp")
    return _success(final_url, status, content, "snapshot", snapshot_date=timestamp)


def _archive_today(transport, original_url, domains, resolver=None):
    encoded = quote(original_url, safe="/:?=&")
    for domain in domains:
        route = "https://" + domain + "/newest/" + encoded
        status, body, final_url, _headers = _fetch(transport, route, resolver)
        if _is_usable_page(status, body, archived=True):
            return _success(final_url, status, body, "snapshot")
    return None


class BrowserTier:
    """Browser/recovery tier with all side-effecting dependencies injected."""

    def __init__(
        self,
        *,
        transport=None,
        browser_callable=None,
        cloudflare_callable=None,
        archive_domains=ARCHIVE_DOMAINS,
        resolver=None,
    ):
        self.transport = transport
        self.browser_callable = browser_callable
        self.cloudflare_callable = cloudflare_callable
        self.archive_domains = tuple(archive_domains)
        self.resolver = resolver

    def fetch(self, url):
        """Single gated fetch, returning only successful public page content."""
        try:
            status, body, final_url, _headers = _fetch(self.transport, url, self.resolver)
            if not _is_usable_page(status, body):
                raise _TierError(URL_BLOCKED)
            return _success(final_url, status, body, "transport")
        except Exception as error:
            return _error_result(error)

    def render_js(self, url):
        return render_js(url, self.browser_callable, resolver=self.resolver)

    def cloudflare_bypass(self, url):
        return cloudflare_bypass(url, self.transport, self.cloudflare_callable, resolver=self.resolver)

    def recover_blocked_page(self, url, *, api_candidates=()):
        """Try public snapshots, a gated CF handler, API candidates, then CDP.

        ``api_candidates`` is an explicit iterable supplied by the caller; this
        method never guesses endpoint paths. Snapshot and browser results retain
        their provenance in the ``source`` field.
        """
        try:
            _require_url(url, self.resolver)
        except Exception as error:
            return _error_result(error)

        direct = None
        direct_error = None
        try:
            direct = _fetch(self.transport, url, self.resolver)
        except _TierError as error:
            if error.code == REDIRECT_BLOCKED:
                return _error_result(error)
            direct_error = error.code
        except Exception as error:
            direct_error = _error_code(error)

        direct_challenge = False
        direct_sensitive = False
        if direct is not None:
            status, body, final_url, headers = direct
            if status == 401 or _is_login_wall(body):
                return {"ok": False, "error": URL_BLOCKED}
            direct_challenge = _is_cloudflare_challenge(status, body, headers)
            direct_sensitive = _is_captcha_page(body)
            if _is_usable_page(status, body):
                return _success(final_url, status, body, "transport")

        last_error = direct_error or URL_BLOCKED
        try:
            snapshot = _wayback_snapshot(self.transport, url, self.resolver)
        except _TierError as error:
            if error.code == REDIRECT_BLOCKED:
                return _error_result(error)
            last_error = error.code
            snapshot = None
        except Exception as error:
            last_error = _error_code(error)
            snapshot = None
        if snapshot is not None:
            return snapshot

        try:
            archived = _archive_today(self.transport, url, self.archive_domains, self.resolver)
        except _TierError as error:
            if error.code == REDIRECT_BLOCKED:
                return _error_result(error)
            last_error = error.code
            archived = None
        except Exception as error:
            last_error = _error_code(error)
            archived = None
        if archived is not None:
            return archived

        if direct_challenge and not direct_sensitive:
            if callable(self.cloudflare_callable):
                try:
                    result = _browser_fetch(url, self.cloudflare_callable, self.resolver)
                    result["source"] = "cloudflare_bypass"
                    return result
                except _TierError as error:
                    if error.code == REDIRECT_BLOCKED:
                        return _error_result(error)
                    last_error = error.code
                except Exception as error:
                    last_error = _error_code(error)

        try:
            candidates = (api_candidates,) if isinstance(api_candidates, str) else tuple(api_candidates)
        except TypeError:
            return {"ok": False, "error": URL_BLOCKED}
        for candidate in candidates:
            try:
                status, content, final_url, _headers = _fetch(self.transport, candidate, self.resolver)
            except _TierError as error:
                if error.code == REDIRECT_BLOCKED:
                    return _error_result(error)
                last_error = error.code
                continue
            except Exception as error:
                last_error = _error_code(error)
                continue
            if _is_usable_page(status, content):
                return _success(final_url, status, content, "api")

        # Do not hand login or CAPTCHA pages to a browser or challenge handler.
        if direct_sensitive:
            return {"ok": False, "error": URL_BLOCKED}
        if callable(self.browser_callable):
            result = render_js(url, self.browser_callable, resolver=self.resolver)
            if result.get("ok"):
                return result
            if result.get("error") == REDIRECT_BLOCKED:
                return result
            last_error = _error_code(result)
        return {"ok": False, "error": last_error}

    # Short alias useful to callers wiring a recovery chain.
    recover = recover_blocked_page


def recover_blocked_page(
    url,
    *,
    transport,
    browser_callable=None,
    cloudflare_callable=None,
    api_candidates=(),
    archive_domains=ARCHIVE_DOMAINS,
    resolver=None,
):
    """Functional wrapper around :class:`BrowserTier` recovery."""
    tier = BrowserTier(
        transport=transport,
        browser_callable=browser_callable,
        cloudflare_callable=cloudflare_callable,
        archive_domains=archive_domains,
        resolver=resolver,
    )
    return tier.recover_blocked_page(url, api_candidates=api_candidates)


__all__ = [
    "ARCHIVE_DOMAINS",
    "BrowserTier",
    "MAX_CONTENT_CHARS",
    "MAX_REDIRECTS",
    "REDIRECT_BLOCKED",
    "URL_BLOCKED",
    "WAYBACK_AVAILABLE",
    "cloudflare_bypass",
    "js_render",
    "recover_blocked_page",
    "render_js",
]
