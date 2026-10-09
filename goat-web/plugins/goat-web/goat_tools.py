"""Bounded SSRF-safe Goat web handlers and their plugin registration entrypoint.

Search uses DuckDuckGo HTML by default; no API key or provider credential is required. All outbound requests use pinned HTTPS fetch."""

from collections import deque
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urldefrag, urljoin, urlsplit

if __package__:
    from .adapters import trafilatura_like_extract
    from .url_gate import (
        BAD_PORT,
        BAD_SCHEME,
        CREDENTIALS_IN_URL,
        PRIVATE_HOST,
        REDIRECT_BLOCKED,
        URL_BLOCKED,
        URLGateError,
        check_url,
        pinned_fetch,
    )
else:  # Backward-compatible top-level import used by the existing offline tests.
    from adapters import trafilatura_like_extract
    from url_gate import (
        BAD_PORT,
        BAD_SCHEME,
        CREDENTIALS_IN_URL,
        PRIVATE_HOST,
        REDIRECT_BLOCKED,
        URL_BLOCKED,
        URLGateError,
        check_url,
        pinned_fetch,
    )


MISSING_CONFIG = "MISSING_CONFIG"
PUBLIC_ERROR_CODES = frozenset((URL_BLOCKED, REDIRECT_BLOCKED, MISSING_CONFIG))
MAX_RESULTS = 5
MAX_CONTENT_CHARS = 8000
MAX_CRAWL_DEPTH = 2
MAX_CRAWL_PAGES = 10
_UNSET = object()

_INTERNAL_URL_ERRORS = frozenset(
    (BAD_SCHEME, CREDENTIALS_IN_URL, BAD_PORT, PRIVATE_HOST, URL_BLOCKED)
)


def map_error(error):
    """Map internal/provider failures to the three public error codes only."""
    if isinstance(error, dict):
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


def _transport_or_error(transport, provider_config):
    if provider_config is not _UNSET and provider_config is None:
        raise URLGateError(MISSING_CONFIG)
    if transport is None:
        return pinned_fetch
    if not callable(transport):
        raise URLGateError(URL_BLOCKED)
    return transport


def _response_parts(response):
    if isinstance(response, (str, bytes)):
        status, body, final_url = 200, response, None
    elif isinstance(response, dict):
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
    except (TypeError, ValueError):
        status = 0
    return status, text, final_url


def _fetch(url, transport):
    allowed, code = check_url(url)
    if not allowed:
        raise URLGateError(code)
    response = transport(url)
    status, text, final_url = _response_parts(response)
    if final_url:
        allowed, code = check_url(final_url)
        if not allowed:
            raise URLGateError(REDIRECT_BLOCKED)
    return status, text, final_url or url


def _truncate(text, limit=MAX_CONTENT_CHARS):
    return text[:limit], len(text) > limit


def _normalized_origin(url):
    allowed, code = check_url(url)
    if not allowed:
        raise URLGateError(code)
    parsed = urlsplit(url)
    host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    return parsed.scheme.lower(), host, parsed.port or 443


def _origin_matches(url, origin):
    try:
        return _normalized_origin(url) == origin
    except (URLGateError, UnicodeError, ValueError):
        return False


def _clean_url(url):
    return urldefrag(url)[0]


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class _TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._capturing = False
        self._seen_title = False

    def handle_starttag(self, tag, _attrs):
        if tag.lower() == "title" and not self._seen_title:
            self._capturing = True

    def handle_endtag(self, tag):
        if tag.lower() == "title" and self._capturing:
            self._capturing = False
            self._seen_title = True

    def handle_data(self, data):
        if self._capturing:
            self.parts.append(data)


def _extract_title(body):
    parser = _TitleParser()
    parser.feed(body)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _bounded_integer(value, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise URLGateError(URL_BLOCKED)
    return value


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


def _search_result_url(raw_url):
    if not raw_url:
        return None
    parsed = urlsplit(raw_url)
    if parsed.netloc.lower().endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            raw_url = target
    if not raw_url.startswith(("https://", "http://")):
        return None
    allowed, _code = check_url(raw_url)
    return raw_url if allowed else None


def goat_search(query, transport=None, *, limit=MAX_RESULTS, provider_config=_UNSET):
    """Search public web results using DuckDuckGo HTML (keyless by default)."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        if not isinstance(query, str) or not query.strip():
            raise URLGateError(URL_BLOCKED)
        limit = _bounded_integer(limit, 1, MAX_RESULTS)
        search_url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query.strip()})
        _status, body, _final_url = _fetch(search_url, fetch)
        parser = _SearchParser()
        parser.feed(body)
        results = []
        for index, item in enumerate(parser.results[:limit]):
            result_url = _search_result_url(item["url"])
            if result_url is None:
                continue
            title, _title_cut = _truncate(item["title"])
            snippet = parser.snippets[index] if index < len(parser.snippets) else ""
            snippet, _snippet_cut = _truncate(snippet)
            results.append({"title": title, "url": result_url, "snippet": snippet})
        return {"results": results}
    except Exception as error:
        return _error_result(error)


def goat_extract(url, transport=None, *, provider_config=_UNSET):
    """Fetch one public HTTPS page and return extracted text capped at 8000 characters."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        status, body, final_url = _fetch(url, fetch)
        text, truncated = _truncate(trafilatura_like_extract(body))
        return {
            "url": url,
            "final_url": final_url,
            "status": status,
            "title": _extract_title(body),
            "text": text,
            "truncated": truncated,
        }
    except Exception as error:
        return _error_result(error)


def goat_crawl(
    url,
    transport=None,
    *,
    max_depth=MAX_CRAWL_DEPTH,
    max_pages=MAX_CRAWL_PAGES,
    provider_config=_UNSET,
):
    """Breadth-first crawl of same-origin HTTPS links within schema bounds."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        depth_limit = _bounded_integer(max_depth, 0, MAX_CRAWL_DEPTH)
        page_limit = _bounded_integer(max_pages, 1, MAX_CRAWL_PAGES)
        origin = _normalized_origin(url)
        start = _clean_url(url)
        queue = deque(((start, 0),))
        visited = set()
        pages = []
        while queue and len(pages) < page_limit:
            current, depth = queue.popleft()
            current = _clean_url(current)
            if current in visited:
                continue
            if not _origin_matches(current, origin):
                continue
            visited.add(current)
            status, body, final_url = _fetch(current, fetch)
            if not _origin_matches(final_url, origin):
                raise URLGateError(REDIRECT_BLOCKED)
            text, content_cut = _truncate(trafilatura_like_extract(body))
            pages.append(
                {
                    "url": current,
                    "depth": depth,
                    "status": status,
                    "title": _extract_title(body),
                    "text": text,
                    "truncated": content_cut,
                }
            )
            if depth >= depth_limit:
                continue
            parser = _LinkParser()
            parser.feed(body)
            for href in parser.links:
                target = _clean_url(urljoin(final_url, href))
                if target not in visited and _origin_matches(target, origin):
                    queue.append((target, depth + 1))
        return {"pages": pages}
    except Exception as error:
        return _error_result(error)


def goat_probe(url, transport=None, *, provider_config=_UNSET):
    """Return only success, HTTP/error status, and the parsed host."""
    try:
        parsed = urlsplit(url) if isinstance(url, str) else None
        host = parsed.hostname if parsed is not None and parsed.hostname else ""
    except ValueError:
        host = ""
    try:
        fetch = _transport_or_error(transport, provider_config)
        status, _body, _final_url = _fetch(url, fetch)
        if not 100 <= status <= 599:
            return _error_result(URL_BLOCKED)
        return {"ok": 200 <= status < 400, "status": status, "host": host}
    except Exception as error:
        return _error_result(error)

def register():
    """Return the public tool-name to handler mapping for plugin loading."""
    return {
        "goat_search": goat_search,
        "goat_extract": goat_extract,
        "goat_crawl": goat_crawl,
        "goat_probe": goat_probe,
    }
