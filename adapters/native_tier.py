"""Bounded adapters for Hermes-native web search and extraction callables.

This module never creates a network client. Inject ``hermes_web_search`` and
``web_extract``-compatible callables so tests and callers control the native
tool boundary.
"""

import inspect
from collections.abc import Mapping
from urllib.parse import urlsplit

from ssrf_guard import check_url, pinned_fetch, resolve_public_url


MISSING_CONFIG = "MISSING_CONFIG"
URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
PUBLIC_ERROR_CODES = frozenset((URL_BLOCKED, REDIRECT_BLOCKED, MISSING_CONFIG))
MAX_RESULTS = 5
MAX_CONTENT_CHARS = 8000
_UNSET = object()
_INTERNAL_URL_ERRORS = frozenset(
    ("BAD_SCHEME", "CREDENTIALS_IN_URL", "BAD_PORT", "PRIVATE_HOST", URL_BLOCKED)
)


def map_error(error):
    """Map provider/internal failures to the Goat public error codes."""
    if isinstance(error, Mapping):
        code = error.get("code", error.get("error"))
    else:
        code = getattr(error, "code", error)
    if code is None:
        return MISSING_CONFIG
    if not isinstance(code, str):
        return URL_BLOCKED
    if code in PUBLIC_ERROR_CODES:
        return code
    if code in _INTERNAL_URL_ERRORS:
        return URL_BLOCKED
    if code in ("MISSING_CONFIG", "PROVIDER_NOT_CONFIGURED", "MISSING_PROVIDER_CONFIG"):
        return MISSING_CONFIG
    if code in ("REDIRECT_FAILED", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT"):
        return REDIRECT_BLOCKED
    return URL_BLOCKED


def _error_result(error):
    return {"ok": False, "error": map_error(error)}


def _callable_error(function):
    if function is None:
        return MISSING_CONFIG
    if not callable(function):
        return URL_BLOCKED
    return None


def _limit(max_results):
    try:
        return max(0, min(MAX_RESULTS, int(max_results)))
    except (TypeError, ValueError, OverflowError):
        return MAX_RESULTS


def _text(value):
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _truncate(value):
    text = _text(value)
    return text[:MAX_CONTENT_CHARS], len(text) > MAX_CONTENT_CHARS


def _legacy_valid_web_url(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme.lower() in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and (parsed.port is None or 1 <= parsed.port <= 65535)
        )
    except (ValueError, UnicodeError):
        return False


def _valid_web_url(value, resolver=None):
    allowed, _code = check_url(value)
    if not allowed:
        return False
    if resolver is None:
        return True
    try:
        resolve_public_url(value, resolver=resolver)
    except Exception:
        return False
    return True


def _supports_keyword(function, keyword):
    try:
        parameters = inspect.signature(function).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == keyword or parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )


def _extract_with_pinned_context(web_extract, url, resolver, addresses):
    """Give pin-aware native adapters the guarded fetch primitive and answer."""
    # P1 fix: keep validated addresses pinned. When a resolver is supplied,
    # the addresses must be forwarded to the adapter so the connection can be
    # pinned; discarding them would allow a later DNS rebinding to private IP.
    # Non-pin-aware adapters are fail-closed when resolver is required.
    if resolver is not None and not (_supports_keyword(web_extract, "pinned_fetch") or _supports_keyword(web_extract, "resolved_addresses")):
        # Keep addresses but adapter cannot pin -> fail closed for live.
        # For offline fakes without resolver this branch is not taken.
        # We raise so native_extract maps to URL_BLOCKED.
        raise ValueError("adapter must support pinned_fetch or resolved_addresses when resolver is supplied")
    kwargs = {"urls": [url], "char_limit": MAX_CONTENT_CHARS}
    if _supports_keyword(web_extract, "pinned_fetch"):
        def guarded_fetch(target, **options):
            if "connection_factory" in options:
                raise ValueError("native adapter may not override the pinned connection factory")
            options["resolver"] = resolver
            return pinned_fetch(target, **options)

        kwargs["pinned_fetch"] = guarded_fetch
    if _supports_keyword(web_extract, "resolved_addresses"):
        kwargs["resolved_addresses"] = tuple(addresses)
    return web_extract(**kwargs)


def _response_error(response):
    if isinstance(response, Mapping):
        if response.get("ok") is False:
            return map_error(response)
        if response.get("error") is not None or response.get("code") is not None:
            return map_error(response)
    return None


def _search_items(response):
    if not isinstance(response, Mapping):
        return response if isinstance(response, (list, tuple)) else None
    data = response.get("data", response)
    if isinstance(data, Mapping):
        items = data.get("web", data.get("results"))
        return items if isinstance(items, (list, tuple)) else None
    return data if isinstance(data, (list, tuple)) else None


def native_search(query, web_search=None, *, max_results=MAX_RESULTS, resolver=None):
    """Search via an injected native callable and return the Goat result shape.

    ``web_search`` is called as ``web_search(query, limit=bounded_limit)``; its
    native ``data.web`` items are normalized to title/url/snippet records.
    """
    missing = _callable_error(web_search)
    if missing is not None:
        return _error_result(missing)
    if not isinstance(query, str) or not query.strip():
        return _error_result(URL_BLOCKED)
    limit = _limit(max_results)
    try:
        response = web_search(query.strip(), limit=limit)
    except Exception as error:
        return _error_result(error)
    error = _response_error(response)
    if error is not None:
        return _error_result(error)
    items = _search_items(response)
    if items is None:
        return _error_result(URL_BLOCKED)

    truncated = len(items) > limit
    results = []
    for item in items[:limit]:
        if not isinstance(item, Mapping):
            continue
        url = item.get("url")
        if not _valid_web_url(url, resolver=resolver):
            continue
        title, title_cut = _truncate(item.get("title", ""))
        snippet, snippet_cut = _truncate(item.get("description", item.get("snippet", "")))
        truncated = truncated or title_cut or snippet_cut
        results.append({"title": title, "url": url, "snippet": snippet})
    return {"ok": True, "results": results, "truncated": truncated}


def _extract_record(response):
    if isinstance(response, str):
        return {"content": response}
    if not isinstance(response, Mapping):
        return None
    data = response.get("data", response)
    if isinstance(data, Mapping):
        records = data.get("results")
        if isinstance(records, (list, tuple)):
            return records[0] if records else None
        if "content" in data or "text" in data or "error" in data:
            return data
    elif isinstance(data, (list, tuple)):
        return data[0] if data else None
    return None


def native_extract(url, web_extract=None, *, resolver=None):
    """Extract a page through an injected, pin-aware native adapter.

    The adapter receives the resolved address set when a resolver is supplied,
    and adapters supporting the ``pinned_fetch`` keyword receive the guarded
    transport. Without a resolver the wrapper performs syntax-only validation
    so injected fakes stay offline; a live legacy adapter must pin its own
    connection and expose every redirect. With no adapter, no fetch is attempted.
    """
    missing = _callable_error(web_extract)
    if missing is not None:
        return _error_result(missing)
    try:
        allowed, _code = check_url(url)
        if not allowed:
            return _error_result(URL_BLOCKED)
        addresses = resolve_public_url(url, resolver=resolver) if resolver is not None else ()
    except Exception:
        return _error_result(URL_BLOCKED)
    try:
        response = _extract_with_pinned_context(web_extract, url, resolver, addresses)
    except Exception as error:
        return _error_result(error)
    error = _response_error(response)
    if error is not None:
        return _error_result(error)
    record = _extract_record(response)
    if not isinstance(record, Mapping):
        return _error_result(URL_BLOCKED)
    if record.get("error") is not None or record.get("code") is not None:
        return _error_result(record)
    final_url = record.get("url", url)
    if not _valid_web_url(final_url, resolver=resolver):
        return _error_result(REDIRECT_BLOCKED)
    content_value = record.get("content", record.get("text"))
    if content_value is None:
        return _error_result(URL_BLOCKED)
    content, truncated = _truncate(content_value)
    return {"ok": True, "url": final_url, "content": content, "truncated": truncated}


class NativeTier:
    """Small holder for injected native search and extract callables."""

    def __init__(self, web_search=None, web_extract=None, *, resolver=None):
        self.web_search = web_search
        self.web_extract = web_extract
        self.resolver = resolver

    def search(self, query, *, max_results=MAX_RESULTS):
        return native_search(
            query, self.web_search, max_results=max_results, resolver=self.resolver
        )

    def extract(self, url):
        return native_extract(url, self.web_extract, resolver=self.resolver)


__all__ = [
    "MAX_CONTENT_CHARS",
    "MAX_RESULTS",
    "MISSING_CONFIG",
    "NativeTier",
    "PUBLIC_ERROR_CODES",
    "REDIRECT_BLOCKED",
    "URL_BLOCKED",
    "map_error",
    "native_extract",
    "native_search",
]
