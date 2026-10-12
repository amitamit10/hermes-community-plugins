"""Bounded SSRF-safe Goat web handlers and their plugin registration entrypoint.

Search uses DuckDuckGo HTML by default; no API key or provider credential is required. All outbound requests use pinned HTTPS fetch."""

import http.client
import json
import socket
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
PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
HTTP_ERROR = "HTTP_ERROR"
RATE_LIMITED = "RATE_LIMITED"
DNS_ERROR = "DNS_ERROR"
UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
CONNECTION_ERROR = "CONNECTION_ERROR"
PUBLIC_ERROR_CODES = frozenset((URL_BLOCKED, REDIRECT_BLOCKED, MISSING_CONFIG, PROVIDER_BLOCKED, HTTP_ERROR, RATE_LIMITED, DNS_ERROR, UPSTREAM_TIMEOUT, CONNECTION_ERROR))
MAX_RESULTS = 5
MAX_CONTENT_CHARS = 8000
MAX_CRAWL_DEPTH = 2
MAX_CRAWL_PAGES = 10
_UNSET = object()

_INTERNAL_URL_ERRORS = frozenset(
    (BAD_SCHEME, CREDENTIALS_IN_URL, BAD_PORT, PRIVATE_HOST, URL_BLOCKED)
)


def map_error(error):
    """Map internal/provider failures to the public error codes only."""
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


def _fetch(url, transport):
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
        self.has_challenge = False
        self.has_no_results = False
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
        if tag.lower() == "form":
            if attributes.get("id") in ("challenge-form", "captcha-form"):
                self.has_challenge = True
            elif "anomaly-modal__form" in classes:
                self.has_challenge = True
        if tag.lower() == "div":
            if classes & {"no-results", "no-results__message", "result--no-result"}:
                self.has_no_results = True
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


class _ChallengeParser(HTMLParser):
    """Structural provider-challenge detector for extraction (not SERP logic)."""

    _CHALLENGE_TITLES = ("just a moment", "verify you are human", "attention required")

    _INERT_TAGS = frozenset(("pre", "code", "textarea", "template"))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.form_challenge = False
        self.turnstile = False
        self.challenge_script = False
        self._in_title = False
        self._title_seen = False
        self._title_chunks = []
        self._inert_depth = 0

    def handle_starttag(self, tag, attrs):
        lowered = tag.lower()
        if lowered in self._INERT_TAGS:
            self._inert_depth += 1
            return
        if self._inert_depth > 0:
            return
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if lowered == "form":
            if attributes.get("id") in ("challenge-form", "captcha-form"):
                self.form_challenge = True
        if "anomaly-modal__form" in classes:
            self.form_challenge = True
        if "cf-turnstile" in classes:
            self.turnstile = True
        if lowered == "script":
            src = attributes.get("src") or ""
            if "/cdn-cgi/challenge-platform/" in src:
                self.challenge_script = True
        if lowered == "title" and not self._title_seen:
            self._in_title = True

    def handle_endtag(self, tag):
        lowered = tag.lower()
        if lowered in self._INERT_TAGS and self._inert_depth > 0:
            self._inert_depth -= 1
            return
        if self._inert_depth > 0:
            return
        if lowered == "title" and self._in_title:
            self._in_title = False
            self._title_seen = True

    def handle_startendtag(self, tag, attrs):
        # Self-closing tags never open inert scope nor carry a challenge widget.
        lowered = tag.lower()
        if lowered in self._INERT_TAGS:
            return
        if self._inert_depth > 0:
            return
        # Reuse start-tag logic for self-closing challenge widgets.
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data):
        if self._inert_depth > 0:
            return
        if self._in_title:
            self._title_chunks.append(data)

    @property
    def has_challenge(self):
        if self.form_challenge or self.turnstile:
            return True
        if self.challenge_script:
            title = " ".join("".join(self._title_chunks).split()).lower()
            return any(marker in title for marker in self._CHALLENGE_TITLES)
        return False


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


def goat_search(query, transport=None, *, max_results=MAX_RESULTS, provider_config=_UNSET):
    """Search public web results using DuckDuckGo HTML (keyless by default)."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        if not isinstance(query, str) or not query.strip():
            raise URLGateError(URL_BLOCKED)
        if type(max_results) is not int:
            max_results = MAX_RESULTS
        max_results = _bounded_integer(max_results, 1, MAX_RESULTS)
        search_url = "https://html.duckduckgo.com/html/?" + urlencode({"q": query.strip()})
        status, body, _final_url, _headers = _fetch(search_url, fetch)
        if status == 429:
            return _rate_limited_result(status, _retry_after_from_headers(_headers))
        if _validated_http_status(status) is None:
            raise URLGateError(URL_BLOCKED)
        if not 200 <= status < 300:
            if _has_provider_challenge(body):
                raise URLGateError(PROVIDER_BLOCKED)
            return _http_error_result(status)
        parser = _SearchParser()
        parser.feed(body)
        if parser.has_challenge:
            raise URLGateError(PROVIDER_BLOCKED)
        if not parser.results and body.strip() and not parser.has_no_results:
            raise URLGateError(PROVIDER_BLOCKED)
        results = []
        for index, item in enumerate(parser.results[:max_results]):
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


def _validated_http_status(value):
    """Return value only when it is a strict int HTTP status, else None."""
    if type(value) is not int:
        return None
    if not 100 <= value <= 599:
        return None
    return value


def _http_error_result(status):
    validated = _validated_http_status(status)
    if validated is None:
        return {"error": {"code": URL_BLOCKED}}
    return {"error": {"code": HTTP_ERROR}, "status": validated}


def _validated_retry_after(value):
    """Strict delta-seconds: int or digit-string within 0..31536000; bool rejected."""
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
    """Extract validated Retry-After delta-seconds from a headers mapping, else None."""
    try:
        if not isinstance(headers, dict):
            return None
        candidate = None
        found = False
        for key, val in headers.items():
            if isinstance(key, str) and key.lower() in ("retry-after", "retry_after"):
                candidate = val
                found = True
                break
        if not found:
            return None
        return _validated_retry_after(candidate)
    except Exception:
        return None


def _rate_limited_result(status, retry_after=None):
    validated = _validated_http_status(status)
    if validated is None:
        return {"error": {"code": URL_BLOCKED}}
    out = {"error": {"code": RATE_LIMITED}, "status": validated}
    valid_retry = _validated_retry_after(retry_after)
    if valid_retry is not None:
        out["retry_after"] = valid_retry
    return out


def _has_provider_challenge(body):
    """Return whether HTML carries a recognised provider challenge widget."""
    try:
        if isinstance(body, str) and "<" in body:
            try:
                json.loads(body)
                return False
            except Exception:
                pass
        parser = _ChallengeParser()
        parser.feed(body if isinstance(body, str) else "")
        parser.close()
        return bool(parser.has_challenge)
    except Exception:
        return False


def goat_extract(url, transport=None, *, provider_config=_UNSET):
    """Fetch one public HTTPS page and return extracted text capped at 8000 characters."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        status, body, final_url, headers = _fetch(url, fetch)
        if status == 429:
            return _rate_limited_result(status, _retry_after_from_headers(headers))
        if _has_provider_challenge(body):
            raise URLGateError(PROVIDER_BLOCKED)
        if _validated_http_status(status) is None:
            raise URLGateError(URL_BLOCKED)
        if not 200 <= status < 300:
            return _http_error_result(status)
        if not body.strip():
            return _http_error_result(status)
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
            status, body, final_url, headers = _fetch(current, fetch)
            if not _origin_matches(final_url, origin):
                raise URLGateError(REDIRECT_BLOCKED)
            if status == 429:
                return _rate_limited_result(status, _retry_after_from_headers(headers))
            if _has_provider_challenge(body):
                raise URLGateError(PROVIDER_BLOCKED)
            if _validated_http_status(status) is None:
                raise URLGateError(URL_BLOCKED)
            if not 200 <= status < 300:
                return _http_error_result(status)
            if not body.strip():
                return _http_error_result(status)
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


def _validated_probe_host(value):
    """Bare DNS/IP host only for probe diagnostics; rejects credentials/ports/paths."""
    if type(value) is not str:
        return None
    if not value or value != value.strip():
        return None
    if len(value) > 253:
        return None
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
        return None
    if any(c in value for c in (" ", "\\", "/", "?", "#", "@")):
        return None
    candidate = value
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    try:
        import ipaddress as _ip

        _ip.ip_address(candidate.split("%", 1)[0] if "%" in candidate else candidate)
        if "%" in candidate:
            return None
        return value
    except Exception:
        pass
    host = candidate.lower().rstrip(".")
    if not host or len(host) > 253:
        return None
    if ":" in host:
        return None
    labels = host.split(".")
    for label in labels:
        if not label or len(label) > 63:
            return None
        if label.startswith("-") or label.endswith("-"):
            return None
        for ch in label:
            if not (ch.isascii() and (ch.isalnum() or ch == "-")):
                return None
    return value


def _probe_host_from_url(url):
    """Return the validated public host for url, else None (never reflects private targets)."""
    if not isinstance(url, str):
        return None
    try:
        allowed, _code = check_url(url)
    except Exception:
        return None
    if not allowed:
        return None
    try:
        parsed = urlsplit(url)
        raw_host = parsed.hostname
    except ValueError:
        return None
    if not raw_host:
        return None
    try:
        canonical = raw_host.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        return None
    return _validated_probe_host(canonical)


def _probe_result(url, status, body, headers):
    """Map an observed HTTP response to the probe shape with safe diagnostics only."""
    validated_status = _validated_http_status(status)
    validated_host = _probe_host_from_url(url)
    if validated_status is None or validated_host is None:
        return {"ok": False, "error": {"code": URL_BLOCKED}}
    if validated_status == 429:
        out = {"ok": False, "error": {"code": RATE_LIMITED}, "status": validated_status, "host": validated_host}
        valid_retry = _retry_after_from_headers(headers)
        if valid_retry is not None:
            out["retry_after"] = valid_retry
        return out
    try:
        challenge = _has_provider_challenge(body if isinstance(body, str) else "")
    except Exception:
        challenge = False
    if challenge:
        return {"ok": False, "error": {"code": PROVIDER_BLOCKED}, "status": validated_status, "host": validated_host}
    if 200 <= validated_status < 400:
        return {"ok": True, "status": validated_status, "host": validated_host}
    return {"ok": False, "error": {"code": HTTP_ERROR}, "status": validated_status, "host": validated_host}


def _probe_exception_result(error):
    """Map a gate failure to the probe shape, preserving only validated redirect diagnostics."""
    code = map_error(error)
    if code != REDIRECT_BLOCKED:
        return _error_result(error)
    raw_status = getattr(error, "status", None)
    raw_host = getattr(error, "host", None)
    validated_status = _validated_http_status(raw_status)
    validated_host = _validated_probe_host(raw_host) if isinstance(raw_host, str) else None
    if validated_host is not None:
        try:
            if ":" in validated_host and not validated_host.startswith("["):
                candidate_url = "https://[" + validated_host + "]/"
            else:
                candidate_url = "https://" + validated_host + "/"
            probe_host = _probe_host_from_url(candidate_url)
            if probe_host is None:
                validated_host = None
        except Exception:
            validated_host = None
    if validated_status is None or validated_host is None:
        return {"ok": False, "error": {"code": REDIRECT_BLOCKED}}
    return {"ok": False, "error": {"code": REDIRECT_BLOCKED}, "status": validated_status, "host": validated_host}


def goat_probe(url, transport=None, *, provider_config=_UNSET):
    """Probe one public HTTPS URL; success keeps the exact old shape, failures carry safe diagnostics."""
    try:
        fetch = _transport_or_error(transport, provider_config)
        status, body, _final_url, headers = _fetch(url, fetch)
        return _probe_result(url, status, body, headers)
    except Exception as error:
        try:
            if map_error(error) == REDIRECT_BLOCKED and (
                getattr(error, "status", None) is not None or getattr(error, "host", None) is not None
            ):
                return _probe_exception_result(error)
        except Exception:
            pass
        return _error_result(error)

def register():
    """Return the public tool-name to handler mapping for plugin loading."""
    return {
        "goat_search": goat_search,
        "goat_extract": goat_extract,
        "goat_crawl": goat_crawl,
        "goat_probe": goat_probe,
    }
