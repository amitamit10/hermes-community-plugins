"""Keyless search clients with Goat-compatible bounds and error responses.

DuckDuckGo HTML and Wikipedia OpenSearch need no credentials. SearXNG is
self-hosted/configurable: it fails closed until a base URL is supplied. Each
client accepts a one-argument ``transport(url)`` callable for deterministic
integration and tests; omitting it uses a small stdlib HTTPS transport.
"""

from collections.abc import Mapping
from html.parser import HTMLParser
import ipaddress
import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from ssrf_guard import (
    GuardError,
    MAX_RESPONSE_BYTES,
    REDIRECT_BLOCKED,
    URL_BLOCKED,
    check_url as _guard_check_url,
    pinned_fetch,
    validate_public_url,
)


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
_DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
_WIKIPEDIA_ENDPOINT = "https://en.wikipedia.org/w/api.php"


class _URLGateError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def map_error(error):
    """Map internal/provider failures to the three public Goat error codes."""
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
    return {"error": {"code": map_error(error)}}


def _legacy_check_url(url):
    """Perform stdlib-only URL checks matching Goat's public-URL boundary."""
    if not isinstance(url, str) or not url or any(ord(char) < 32 for char in url):
        return False, URL_BLOCKED
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https"):
            return False, "BAD_SCHEME"
        if parsed.username is not None or parsed.password is not None:
            return False, "CREDENTIALS_IN_URL"
        if not parsed.hostname:
            return False, URL_BLOCKED
        try:
            port = parsed.port
        except ValueError:
            return False, "BAD_PORT"
        if port is not None and not 1 <= port <= 65535:
            return False, "BAD_PORT"
        hostname = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        if not hostname or "\\" in parsed.netloc or any(c.isspace() for c in hostname):
            return False, URL_BLOCKED
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            return False, "PRIVATE_HOST"
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            return False, "PRIVATE_HOST"
    except (UnicodeError, ValueError):
        return False, URL_BLOCKED
    return True, None


def _check_url(url):
    """Use the shared HTTPS/443 URL boundary without performing DNS."""
    return _guard_check_url(url)


def _transport_or_error(transport, provider_config):
    if provider_config is not _UNSET and provider_config is None:
        raise _URLGateError(MISSING_CONFIG)
    if transport is None:
        return _default_transport
    if not callable(transport):
        raise _URLGateError(URL_BLOCKED)
    return transport


class _SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        allowed, _code = _check_url(newurl)
        if not allowed:
            raise _URLGateError(REDIRECT_BLOCKED)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def _legacy_default_transport(url):
    """Fetch a URL using only urllib; redirects are rechecked before following."""
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
            "User-Agent": "Goat-FreeSearch/1.0",
        },
    )
    opener = build_opener(_SafeRedirectHandler())
    try:
        with opener.open(request, timeout=10) as response:
            return {
                "status": response.status,
                "body": response.read(),
                "url": response.geturl(),
            }
    except HTTPError as error:
        # Preserve the Goat-style HTTP envelope; callers parse the body the same
        # way regardless of status, just as goat_tools' search handler does.
        return {"status": error.code, "body": error.read(), "url": error.geturl()}


def _default_transport(url):
    """Fetch with DNS validation and a connection pinned to the verified IP."""
    return pinned_fetch(url, max_response_bytes=MAX_RESPONSE_BYTES)


def _legacy_response_parts(response):
    if isinstance(response, (str, bytes)):
        status, body, final_url = 200, response, None
    elif isinstance(response, Mapping):
        status = response.get("status", 200)
        body = response.get("body", response.get("text", ""))
        final_url = response.get("url", response.get("final_url"))
    else:
        status = getattr(response, "status", 200)
        body = getattr(response, "body", getattr(response, "text", ""))
        final_url = getattr(response, "url", getattr(response, "final_url", None))
    if isinstance(body, bytes):
        text = body.decode("utf-8", errors="replace")
    elif isinstance(body, str):
        text = body
    else:
        text = str(body) if body is not None else ""
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    return status, text, final_url


def _response_parts(response):
    if isinstance(response, (str, bytes)):
        status, body, final_url = 200, response, None
    elif isinstance(response, Mapping):
        status = response.get("status", 200)
        body = response.get("body", response.get("text", ""))
        final_url = response.get("url", response.get("final_url"))
    else:
        status = getattr(response, "status", 200)
        body = getattr(response, "body", getattr(response, "text", ""))
        final_url = getattr(response, "url", getattr(response, "final_url", None))
    if isinstance(body, bytes):
        if len(body) > MAX_RESPONSE_BYTES:
            raise _URLGateError(URL_BLOCKED)
        text = body.decode("utf-8", errors="replace")
    elif isinstance(body, str):
        bounded = []
        used = 0
        for char in body:
            used += len(char.encode("utf-8", errors="replace"))
            if used > MAX_RESPONSE_BYTES:
                raise _URLGateError(URL_BLOCKED)
            bounded.append(char)
        text = "".join(bounded)
    elif body is None:
        text = ""
    elif isinstance(body, (Mapping, list, tuple)):
        raise _URLGateError(URL_BLOCKED)
    else:
        raise _URLGateError(URL_BLOCKED)
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    return status, text, final_url


def _fetch(url, transport, resolver=None):
    allowed, code = _check_url(url)
    if not allowed:
        raise _URLGateError(code)
    if transport is _default_transport:
        if resolver is None:
            response = pinned_fetch(url, max_response_bytes=MAX_RESPONSE_BYTES)
        else:
            response = pinned_fetch(url, resolver=resolver, max_response_bytes=MAX_RESPONSE_BYTES)
    else:
        if resolver is not None:
            try:
                validate_public_url(url, resolver=resolver)
            except GuardError as error:
                raise _URLGateError(error.code) from None
        response = transport(url)
    _status, text, final_url = _response_parts(response)
    if final_url:
        try:
            allowed, _code = _check_url(final_url)
            if not allowed:
                raise _URLGateError(REDIRECT_BLOCKED)
            if resolver is not None and transport is not _default_transport:
                validate_public_url(final_url, resolver=resolver)
        except GuardError:
            raise _URLGateError(REDIRECT_BLOCKED) from None
    return text, final_url or url


def _limit(max_results):
    try:
        return max(0, min(MAX_RESULTS, int(max_results)))
    except (TypeError, ValueError):
        return MAX_RESULTS


def _truncate(text, limit=MAX_CONTENT_CHARS):
    if not isinstance(text, str):
        text = str(text) if text is not None else ""
    return text[:limit], len(text) > limit


def _valid_result_url(url):
    allowed, _code = _check_url(url)
    return allowed


def _json_body(body):
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        raise _URLGateError(URL_BLOCKED) from None


class _SearchParser(HTMLParser):
    _VOID_TAGS = frozenset(
        ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr")
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results = []
        self.snippets = []
        self._capture = None
        self._stack = []

    def _finish_capture(self):
        kind, href, chunks = self._capture
        text = " ".join("".join(chunks).split())
        if kind == "result":
            self.results.append({"url": href, "title": text})
        else:
            self.snippets.append(text)
        self._capture = None
        self._stack = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if self._capture is not None:
            if tag.lower() not in self._VOID_TAGS:
                self._stack.append(tag.lower())
            return
        if tag.lower() == "a" and "result__a" in classes:
            self._capture = ("result", attributes.get("href", ""), [])
            self._stack = [tag.lower()]
        elif "result__snippet" in classes:
            self._capture = ("snippet", "", [])
            self._stack = [tag.lower()]

    def handle_endtag(self, tag):
        if self._capture is None:
            return
        tag = tag.lower()
        if tag not in self._stack:
            return
        self._stack = self._stack[: len(self._stack) - 1 - self._stack[::-1].index(tag)]
        if not self._stack:
            self._finish_capture()

    def handle_data(self, data):
        if self._capture is not None:
            self._capture[2].append(data)


def _duckduckgo_result_url(raw_url):
    if not raw_url:
        return None
    try:
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if host == "duckduckgo.com" or host.endswith(".duckduckgo.com"):
            target = parse_qs(parsed.query).get("uddg", [None])[0]
            if target:
                raw_url = target
            else:
                return None
    except (UnicodeError, ValueError):
        return None
    if not raw_url.startswith(("https://", "http://")):
        return None
    return raw_url if _valid_result_url(raw_url) else None


def _query_or_error(query):
    if not isinstance(query, str) or not query.strip():
        raise _URLGateError(URL_BLOCKED)
    return query.strip()


def duckduckgo_search(
    query,
    transport=None,
    *,
    max_results=MAX_RESULTS,
    provider_config=_UNSET,
    resolver=None,
):
    """Search DuckDuckGo's public HTML endpoint without an API key."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        search_text = _query_or_error(query)
        limit = _limit(max_results)
        url = _DDG_ENDPOINT + "?" + urlencode({"q": search_text})
        body, _final_url = _fetch(url, fetch, resolver)
        parser = _SearchParser()
        parser.feed(body)
        results = []
        truncated = len(parser.results) > limit
        for index, item in enumerate(parser.results[:limit]):
            result_url = _duckduckgo_result_url(item["url"])
            if result_url is None:
                continue
            title, title_cut = _truncate(item["title"])
            snippet = parser.snippets[index] if index < len(parser.snippets) else ""
            snippet, snippet_cut = _truncate(snippet)
            truncated = truncated or title_cut or snippet_cut
            results.append({"title": title, "url": result_url, "snippet": snippet})
        return {"ok": True, "results": results, "truncated": truncated}
    except Exception as error:
        return _error_result(error)


def wikipedia_search(
    query,
    transport=None,
    *,
    max_results=MAX_RESULTS,
    provider_config=_UNSET,
    resolver=None,
):
    """Search Wikipedia via the keyless MediaWiki OpenSearch API."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        search_text = _query_or_error(query)
        limit = _limit(max_results)
        url = _WIKIPEDIA_ENDPOINT + "?" + urlencode({
            "action": "opensearch",
            "search": search_text,
            "limit": limit,
            "namespace": 0,
            "format": "json",
        })
        body, _final_url = _fetch(url, fetch, resolver)
        payload = _json_body(body)
        if not isinstance(payload, list) or len(payload) < 4:
            raise _URLGateError(URL_BLOCKED)
        _search_term, titles, descriptions, urls = payload[:4]
        if not all(isinstance(values, list) for values in (titles, descriptions, urls)):
            raise _URLGateError(URL_BLOCKED)
        truncated = max(len(titles), len(urls)) > limit
        results = []
        for index in range(min(limit, len(titles), len(urls))):
            result_url = urls[index]
            if not isinstance(result_url, str) or not _valid_result_url(result_url):
                continue
            title, title_cut = _truncate(titles[index])
            description = descriptions[index] if index < len(descriptions) else ""
            snippet, snippet_cut = _truncate(description)
            truncated = truncated or title_cut or snippet_cut
            results.append({"title": title, "url": result_url, "snippet": snippet})
        return {"ok": True, "results": results, "truncated": truncated}
    except Exception as error:
        return _error_result(error)


def _searxng_base_url(base_url, provider_config):
    if provider_config is not _UNSET and provider_config is None:
        raise _URLGateError(MISSING_CONFIG)
    if base_url is None and isinstance(provider_config, Mapping):
        base_url = provider_config.get("base_url")
    if not isinstance(base_url, str) or not base_url.strip():
        raise _URLGateError(MISSING_CONFIG)
    base_url = base_url.strip()
    allowed, code = _check_url(base_url)
    if not allowed:
        raise _URLGateError(code)
    parsed = urlsplit(base_url)
    if parsed.scheme.lower() != "https" or parsed.query or parsed.fragment:
        raise _URLGateError(URL_BLOCKED)
    path = parsed.path.rstrip("/") + "/search"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def searxng_search(
    query,
    base_url=None,
    transport=None,
    *,
    max_results=MAX_RESULTS,
    provider_config=_UNSET,
    resolver=None,
):
    """Search a configured SearXNG instance; never picks an instance implicitly."""
    try:
        endpoint = _searxng_base_url(base_url, provider_config)
        fetch = _transport_or_error(transport, provider_config)
        search_text = _query_or_error(query)
        limit = _limit(max_results)
        url = endpoint + "?" + urlencode({"q": search_text, "format": "json"})
        body, _final_url = _fetch(url, fetch, resolver)
        payload = _json_body(body)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            raise _URLGateError(URL_BLOCKED)
        items = payload["results"]
        truncated = len(items) > limit
        results = []
        for item in items[:limit]:
            if not isinstance(item, Mapping):
                continue
            result_url = item.get("url")
            if not isinstance(result_url, str) or not _valid_result_url(result_url):
                continue
            title, title_cut = _truncate(item.get("title", ""))
            snippet, snippet_cut = _truncate(item.get("content", item.get("snippet", item.get("description", ""))))
            truncated = truncated or title_cut or snippet_cut
            results.append({"title": title, "url": result_url, "snippet": snippet})
        return {"ok": True, "results": results, "truncated": truncated}
    except Exception as error:
        return _error_result(error)


# Short aliases make the common provider names convenient without duplicating
# implementations or changing their injected-transport contract.
ddg_search = duckduckgo_search
wikipedia_opensearch_search = wikipedia_search


__all__ = [
    "MAX_CONTENT_CHARS",
    "MAX_RESPONSE_BYTES",
    "MAX_RESULTS",
    "MISSING_CONFIG",
    "PUBLIC_ERROR_CODES",
    "REDIRECT_BLOCKED",
    "URL_BLOCKED",
    "ddg_search",
    "duckduckgo_search",
    "map_error",
    "searxng_search",
    "wikipedia_opensearch_search",
    "wikipedia_search",
]
