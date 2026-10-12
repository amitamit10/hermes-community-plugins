"""Ordered pluggable search backend with bounded fallback (GOAT V5 Slice 1).

DuckDuckGo HTML stays provider #1 with unchanged default behavior; the
Wikipedia OpenSearch API is provider #2. Both are keyless and need no new
runtime dependencies. Fallback is opt-in per call (``allow_fallback=True``);
otherwise callers run the single-provider baseline path untouched.

Conventions (mirroring ``adapters/free_stack.fallback_chain`` where stated):
- every success stamps ``source`` (contributing provider name);
- every fallback hop appends ``{from, to, reason}`` to ``transitions``
  (``transitions`` is omitted when no hop occurred);
- ``MISSING_CONFIG`` stops the chain immediately;
- the last provider error is preserved verbatim when all providers fail.

Transition ``reason`` values are provenance strings (public error codes plus
``NO_RESULTS``/``PARTIAL_RESULTS``); they are not new error codes and the
result-contract allowlist is unchanged. Guards/DNS/TLS/redirect semantics
are untouched: every provider URL passes ``check_url`` before fetching.
"""

import http.client
import json
import socket
import time
from collections import abc
from urllib.parse import urlencode, urlsplit

if __package__:
    from .url_gate import (
        CONNECTION_ERROR,
        DNS_ERROR,
        REDIRECT_BLOCKED,
        UPSTREAM_TIMEOUT,
        URL_BLOCKED,
        URLGateError,
        check_url,
        pinned_fetch,
    )
else:  # Backward-compatible top-level import used by the offline tests.
    from url_gate import (
        CONNECTION_ERROR,
        DNS_ERROR,
        REDIRECT_BLOCKED,
        UPSTREAM_TIMEOUT,
        URL_BLOCKED,
        URLGateError,
        check_url,
        pinned_fetch,
    )

# Canonical public codes owned by result_contract/goat_tools, repeated here
# as literals so this module never imports goat_tools (import cycle).
PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
HTTP_ERROR = "HTTP_ERROR"
RATE_LIMITED = "RATE_LIMITED"
MISSING_CONFIG = "MISSING_CONFIG"

_PUBLIC_ERROR_CODES = frozenset(
    (
        URL_BLOCKED,
        REDIRECT_BLOCKED,
        MISSING_CONFIG,
        PROVIDER_BLOCKED,
        HTTP_ERROR,
        RATE_LIMITED,
        DNS_ERROR,
        UPSTREAM_TIMEOUT,
        CONNECTION_ERROR,
    )
)

# Errors worth bounded retries before failing over; anything else
# (challenge/block/validation failures) fails over immediately.
_TRANSIENT_ERROR_CODES = frozenset((RATE_LIMITED, UPSTREAM_TIMEOUT, CONNECTION_ERROR))

WIKIPEDIA_OPENSEARCH_URL = "https://en.wikipedia.org/w/api.php"
MAX_RESULTS_CAP = 5
MAX_TEXT_CHARS = 8000
MAX_ATTEMPTS = 3

DEFAULT_ORDER = ("ddg", "wikipedia")


class Provider(object):
    """One ordered search backend: ``search`` + ``available`` callables."""

    def __init__(self, name, search, available=None):
        self.name = name
        self.search = search
        self._available = available

    def available(self, provider_config=None):
        if self._available is None:
            return True
        try:
            return bool(self._available(provider_config))
        except Exception:
            return False


_REGISTRY = {}


def _disabled_names(provider_config):
    try:
        if isinstance(provider_config, abc.Mapping):
            disabled = provider_config.get("disabled")
            if isinstance(disabled, (list, tuple, frozenset, set)):
                return [n for n in disabled if isinstance(n, str)]
    except Exception:
        pass
    return []


def _default_available(name):
    def _available(provider_config=None):
        return name not in _disabled_names(provider_config)

    return _available


def register_provider(name, search, available=None):
    """Register (or replace) one provider; returns the Provider."""
    if available is None:
        available = _default_available(name)
    provider = Provider(name, search, available)
    _REGISTRY[name] = provider
    return provider


def get_provider(name):
    return _REGISTRY.get(name)


def ordered_providers(names=None):
    """Return registered providers in the requested order (DDG first)."""
    order = tuple(names) if names is not None else DEFAULT_ORDER
    providers = []
    for name in order:
        provider = _REGISTRY.get(name)
        if provider is not None:
            providers.append(provider)
    return providers


def reset_registry():
    """Clear the registry and re-register the built-in providers."""
    _REGISTRY.clear()
    register_provider("wikipedia", wikipedia_search)


def _response_parts(response):
    if isinstance(response, (str, bytes)):
        status, body, final_url, headers = 200, response, None, None
    elif isinstance(response, dict):
        status = response.get("status", 200)
        body = response.get("body", response.get("text", ""))
        final_url = response.get("url", response.get("final_url"))
        headers = response.get("headers")
    else:
        status = getattr(response, "status", 200)
        body = getattr(response, "body", getattr(response, "text", ""))
        final_url = getattr(response, "url", getattr(response, "final_url", None))
        try:
            headers = getattr(response, "headers", None)
        except Exception:
            headers = None
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    elif isinstance(body, str):
        text = body
    else:
        text = str(body) if body is not None else ""
    if type(status) is int:
        pass
    else:
        status = 0
    return status, text, final_url, headers


def _provider_fetch(url, transport):
    """Gate, fetch, and revalidate one provider URL (mirrors _fetch)."""
    allowed, code = check_url(url)
    if not allowed:
        raise URLGateError(code)
    response = transport(url)
    status, text, final_url, headers = _response_parts(response)
    if final_url:
        allowed, code = check_url(final_url)
        if not allowed:
            try:
                public_host = urlsplit(url).hostname if isinstance(url, str) else None
            except ValueError:
                public_host = None
            raise URLGateError(REDIRECT_BLOCKED, status=status, host=public_host)
    return status, text, final_url or url, headers


def _map_exception(error):
    if isinstance(error, dict):
        code = error.get("code", error.get("error"))
    elif isinstance(error, socket.gaierror):
        return DNS_ERROR
    elif isinstance(error, TimeoutError):
        return UPSTREAM_TIMEOUT
    elif isinstance(error, OSError):
        return CONNECTION_ERROR
    elif isinstance(error, http.client.HTTPException):
        return CONNECTION_ERROR
    else:
        code = getattr(error, "code", error)
    if code is None:
        return MISSING_CONFIG
    if not isinstance(code, str):
        return URL_BLOCKED
    if code in _PUBLIC_ERROR_CODES:
        return code
    return URL_BLOCKED


def _strict_retry_after(value):
    if type(value) is bool:
        return None
    if type(value) is int:
        return value if 0 <= value <= 31536000 else None
    if type(value) is str:
        text = value.strip()
        if not text or not text.isdigit():
            return None
        try:
            number = int(text)
        except Exception:
            return None
        return number if 0 <= number <= 31536000 else None
    return None


def _retry_after_from_headers(headers):
    try:
        if not isinstance(headers, dict):
            return None
        for key, value in headers.items():
            if isinstance(key, str) and key.lower() in ("retry-after", "retry_after"):
                return _strict_retry_after(value)
        return None
    except Exception:
        return None


def _clip(text, limit=MAX_TEXT_CHARS):
    if not isinstance(text, str):
        return ""
    return text[:limit]


def wikipedia_search(query, *, transport, max_results=MAX_RESULTS_CAP):
    """Keyless Wikipedia OpenSearch provider over the injected transport."""
    try:
        fetch = transport if callable(transport) else pinned_fetch
        if not callable(fetch):
            raise URLGateError(URL_BLOCKED)
        if not isinstance(query, str) or not query.strip():
            raise URLGateError(URL_BLOCKED)
        count = max_results if type(max_results) is int else MAX_RESULTS_CAP
        if type(count) is not int or not 1 <= count <= MAX_RESULTS_CAP:
            raise URLGateError(URL_BLOCKED)
        search_url = WIKIPEDIA_OPENSEARCH_URL + "?" + urlencode(
            {
                "action": "opensearch",
                "search": query.strip(),
                "limit": count,
                "namespace": 0,
                "format": "json",
            }
        )
        status, body, _final_url, headers = _provider_fetch(search_url, fetch)
        if type(status) is not int or not 100 <= status <= 599:
            raise URLGateError(URL_BLOCKED)
        if status == 429:
            out = {"error": {"code": RATE_LIMITED}, "status": status}
            retry_after = _retry_after_from_headers(headers)
            if retry_after is not None:
                out["retry_after"] = retry_after
            return out
        if not 200 <= status < 300:
            return {"error": {"code": HTTP_ERROR}, "status": status}
        try:
            payload = json.loads(body)
        except Exception:
            raise URLGateError(PROVIDER_BLOCKED)
        if (
            not isinstance(payload, list)
            or len(payload) != 4
            or not isinstance(payload[1], list)
            or not isinstance(payload[2], list)
            or not isinstance(payload[3], list)
        ):
            raise URLGateError(PROVIDER_BLOCKED)
        _echoed, titles, descriptions, urls = payload
        results = []
        for index, raw_url in enumerate(urls):
            if len(results) >= count:
                break
            if not isinstance(raw_url, str) or not raw_url:
                continue
            allowed, _code = check_url(raw_url)
            if not allowed:
                continue
            title = titles[index] if index < len(titles) else ""
            snippet = descriptions[index] if index < len(descriptions) else ""
            results.append(
                {
                    "title": _clip(title),
                    "url": raw_url,
                    "snippet": _clip(snippet),
                }
            )
        return {"results": results}
    except Exception as error:
        code = error.code if isinstance(error, URLGateError) else _map_exception(error)
        if not isinstance(code, str) or code not in _PUBLIC_ERROR_CODES:
            code = URL_BLOCKED
        return {"error": {"code": code}}


def _error_code_of(outcome):
    try:
        error = outcome.get("error")
    except Exception:
        return URL_BLOCKED
    if not isinstance(error, abc.Mapping):
        return URL_BLOCKED
    code = error.get("code")
    return code if isinstance(code, str) else URL_BLOCKED


def _clean_merged_item(item):
    if not isinstance(item, abc.Mapping):
        return None
    url = item.get("url")
    if not isinstance(url, str) or not url:
        return None
    title = item.get("title", "")
    snippet = item.get("snippet", "")
    return {
        "title": title if isinstance(title, str) else "",
        "url": url,
        "snippet": snippet if isinstance(snippet, str) else "",
    }


def _with_source(response, source, transitions):
    result = dict(response)
    result["source"] = source
    if transitions:
        result["transitions"] = list(transitions)
    return result


def _bounded_attempts(max_attempts):
    if type(max_attempts) is not int:
        return 1
    return max(1, min(max_attempts, MAX_ATTEMPTS))


def _attempt_with_retries(
    provider, query, *, transport, max_results, max_attempts=1, sleep=None,
    backoff_base=0.05, backoff_cap=1.0,
):
    """Run one provider with bounded retries on transient errors only."""
    tries = _bounded_attempts(max_attempts)
    if sleep is None:
        sleep = time.sleep
    try:
        base = float(backoff_base)
    except Exception:
        base = 0.05
    if not 0 <= base <= backoff_cap:
        base = 0.05
    outcome = {"error": {"code": URL_BLOCKED}}
    for attempt in range(1, tries + 1):
        try:
            raw = provider.search(query, transport=transport, max_results=max_results)
        except Exception as error:
            raw = {"error": {"code": _map_exception(error)}}
        if not isinstance(raw, abc.Mapping):
            raw = {"error": {"code": URL_BLOCKED}}
        outcome = raw
        if outcome.get("error") is None:
            return outcome
        if attempt >= tries:
            return outcome
        if _error_code_of(outcome) not in _TRANSIENT_ERROR_CODES:
            return outcome
        delay = base * (2.0 ** (attempt - 1))
        if delay > backoff_cap:
            delay = backoff_cap
        try:
            sleep(delay)
        except Exception:
            pass
    return outcome


def search_with_fallback(
    query,
    *,
    transport,
    max_results=MAX_RESULTS_CAP,
    provider_config=None,
    providers=None,
    max_attempts=1,
    sleep=None,
):
    """Dispatch over the ordered registry with budget, fallback, provenance.

    Providers are tried in order within the attempt/provider budget. The
    first success wins; errors fail over to the next provider with a stamped
    transition. ``MISSING_CONFIG`` stops immediately. When every provider
    fails, the last error is preserved verbatim with the full chain.
    """
    cap = max_results if type(max_results) is int else MAX_RESULTS_CAP
    if type(cap) is not int or not 1 <= cap <= MAX_RESULTS_CAP:
        cap = MAX_RESULTS_CAP
    chain = ordered_providers(providers)
    available_chain = []
    for provider in chain:
        try:
            if provider.available(provider_config):
                available_chain.append(provider)
        except Exception:
            continue
    if not available_chain:
        return {"error": {"code": URL_BLOCKED}, "source": None}
    transitions = []
    last_error = None
    last_error_source = None
    merged = []
    seen_urls = set()
    contributors = []
    for index, provider in enumerate(available_chain):
        outcome = _attempt_with_retries(
            provider,
            query,
            transport=transport,
            max_results=cap,
            max_attempts=max_attempts,
            sleep=sleep,
        )
        if outcome.get("error") is not None:
            code = _error_code_of(outcome)
            if code == MISSING_CONFIG:
                return _with_source(outcome, provider.name, transitions)
            last_error = outcome
            last_error_source = provider.name
            if index < len(available_chain) - 1:
                transitions.append(
                    {
                        "from": provider.name,
                        "to": available_chain[index + 1].name,
                        "reason": code,
                    }
                )
            continue
        items = outcome.get("results")
        if not isinstance(items, list):
            items = []
        added = 0
        for item in items:
            if len(merged) >= cap:
                break
            cleaned = _clean_merged_item(item)
            if cleaned is None or cleaned["url"] in seen_urls:
                continue
            seen_urls.add(cleaned["url"])
            merged.append(cleaned)
            added += 1
        if added:
            contributors.append(provider.name)
        if len(merged) >= cap:
            break
        if index < len(available_chain) - 1:
            transitions.append(
                {
                    "from": provider.name,
                    "to": available_chain[index + 1].name,
                    "reason": "NO_RESULTS" if added == 0 else "PARTIAL_RESULTS",
                }
            )
    if merged:
        out = {
            "results": merged[:cap],
            "source": contributors[0],
            "sources": list(contributors),
        }
        if transitions:
            out["transitions"] = list(transitions)
        return out
    if last_error is not None:
        return _with_source(last_error, last_error_source, transitions)
    return _with_source({"results": []}, available_chain[-1].name, transitions)


register_provider("wikipedia", wikipedia_search)
