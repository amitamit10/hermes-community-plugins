"""Dependency-free, keyless web-search clients with Goat-style envelopes.

All clients accept a one-argument ``transport(url)`` callable, which keeps
unit tests fully offline. The default transport uses pinned stdlib HTTP(S)
connections, rejects non-public destinations, and permits loopback HTTP only
for the explicitly configured SearXNG instance.
"""

from collections.abc import Mapping
import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit

if __package__:
    from .ddg_parser import _SearchParser, _VOID_TAGS, _plain_text
    from .result_contract import public_error_code, result_operation
else:
    from ddg_parser import _SearchParser, _VOID_TAGS, _plain_text
    from result_contract import public_error_code, result_operation


DEFAULT_SEARXNG_URL = "http://localhost:8888"
DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
WIKIPEDIA_ACTION_ENDPOINT = "https://en.wikipedia.org/w/api.php"
MAX_RESULTS = 5
MAX_CONTENT_CHARS = 8000
MAX_RESPONSE_BYTES = 1_048_576
REQUEST_TIMEOUT = 10

MISSING_CONFIG = "MISSING_CONFIG"
URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
_PUBLIC_ERRORS = frozenset((MISSING_CONFIG, URL_BLOCKED, REDIRECT_BLOCKED))
_REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))
_DOMAIN_RE = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\Z")


class _ClientError(Exception):
    """Internal error that carries a public Goat error code."""

    def __init__(self, code):
        super().__init__(code)
        try:
            mapped = public_error_code(code)
        except Exception:
            mapped = URL_BLOCKED
        self.code = mapped


def _error_result(error, *, instance_unreachable=False):
    """Reduce internal/provider failures to the public error envelope."""
    try:
        mapped = public_error_code(error)
    except Exception:
        mapped = URL_BLOCKED
    if mapped != URL_BLOCKED:
        return {"error": {"code": mapped}}
    if instance_unreachable and isinstance(error, OSError):
        return {"error": {"code": MISSING_CONFIG}}
    return {"error": {"code": URL_BLOCKED}}


def _error(code):
    return {"error": {"code": code if code in _PUBLIC_ERRORS else URL_BLOCKED}}


def _is_loopback_host(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _check_url(url, *, allow_local=False):
    """Validate URL syntax and the public/loopback destination policy."""
    if not isinstance(url, str) or not url or url != url.strip():
        return False, URL_BLOCKED
    if "\\" in url or any(ord(char) < 0x20 or ord(char) == 0x7F for char in url):
        return False, URL_BLOCKED
    try:
        parsed = urlsplit(url)
        scheme = parsed.scheme.lower()
        if scheme not in (("https", "http") if allow_local else ("https",)):
            return False, URL_BLOCKED
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            return False, URL_BLOCKED
        raw_host = parsed.hostname
        if not raw_host or "%" in raw_host:
            return False, URL_BLOCKED
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return False, URL_BLOCKED
        if scheme == "https" and port not in (None, 443):
            return False, URL_BLOCKED
        host = raw_host.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        return False, URL_BLOCKED

    if not host or len(host) > 253 or not _DOMAIN_RE.fullmatch(host):
        try:
            address = ipaddress.ip_address(raw_host)
        except ValueError:
            return False, URL_BLOCKED
        if allow_local and address.is_loopback:
            return True, None
        if not address.is_global:
            return False, URL_BLOCKED
        return (True, None) if scheme == "https" else (False, URL_BLOCKED)

    labels = host.split(".")
    if any(len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        return False, URL_BLOCKED
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        if allow_local and host == "localhost":
            return True, None
        return False, URL_BLOCKED

    # Reject alternate numeric spellings that some URL libraries parse as IPs.
    final_label = host.rsplit(".", 1)[-1]
    if final_label.isdecimal() or (
        final_label.startswith("0x")
        and len(final_label) > 2
        and all(char in "0123456789abcdef" for char in final_label[2:])
    ):
        return False, URL_BLOCKED
    return (True, None) if scheme == "https" else (False, URL_BLOCKED)


def _transport_or_default(transport):
    if transport is None:
        return _default_transport
    if not callable(transport):
        raise _ClientError(URL_BLOCKED)
    return transport


def _response_parts(response):
    if isinstance(response, (str, bytes)):
        status, body, final_url, headers = 200, response, None, {}
    elif isinstance(response, Mapping):
        response_fields = {"status", "body", "text", "url", "final_url", "headers"}
        if response_fields.intersection(response):
            status = response.get("status", 200)
            body = response.get("body", response.get("text", ""))
            final_url = response.get("url", response.get("final_url"))
            headers = response.get("headers", {})
        else:
            # Conveniently accept decoded JSON fixtures as response bodies too.
            status, body, final_url, headers = 200, json.dumps(response), None, {}
    else:
        status = getattr(response, "status", 200)
        body = getattr(response, "body", getattr(response, "text", ""))
        final_url = getattr(response, "url", getattr(response, "final_url", None))
        headers = getattr(response, "headers", {})

    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    elif isinstance(body, (Mapping, list)):
        body = json.dumps(body)
    elif not isinstance(body, str):
        body = str(body) if body is not None else ""
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    if not isinstance(headers, Mapping):
        try:
            headers = dict(headers)
        except (TypeError, ValueError):
            headers = {}
    normalized_headers = {str(name).lower(): value for name, value in headers.items()}
    return status, body, final_url, normalized_headers


def _origin(url):
    parsed = urlsplit(url)
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    return parsed.scheme.lower(), host, port


def _redirect_target(current_url, location, *, allow_local):
    if not isinstance(location, str) or not location:
        raise _ClientError(REDIRECT_BLOCKED)
    try:
        target = urljoin(current_url, location)
        current_is_local = allow_local and _is_loopback_host(urlsplit(current_url).hostname or "")
        allowed, _code = _check_url(target, allow_local=allow_local)
        if not allowed:
            raise _ClientError(REDIRECT_BLOCKED)
        if current_is_local and _origin(target) != _origin(current_url):
            raise _ClientError(REDIRECT_BLOCKED)
        return target
    except (TypeError, UnicodeError, ValueError):
        raise _ClientError(REDIRECT_BLOCKED) from None


def _fetch(url, transport, *, allow_local=False):
    allowed, _code = _check_url(url, allow_local=allow_local)
    if not allowed:
        raise _ClientError(URL_BLOCKED)

    current = url
    for redirects_used in range(3):
        response = transport(current)
        status, body, final_url, headers = _response_parts(response)
        effective_url = final_url or current
        if final_url:
            allowed, _code = _check_url(final_url, allow_local=allow_local)
            if not allowed:
                raise _ClientError(REDIRECT_BLOCKED)
            if allow_local and _is_loopback_host(urlsplit(current).hostname or ""):
                if _origin(final_url) != _origin(current):
                    raise _ClientError(REDIRECT_BLOCKED)

        if status in _REDIRECT_STATUSES and headers.get("location"):
            if redirects_used >= 2:
                raise _ClientError(REDIRECT_BLOCKED)
            current = _redirect_target(effective_url, headers["location"], allow_local=allow_local)
            continue
        return status, body, effective_url
    raise _ClientError(REDIRECT_BLOCKED)


def _resolve_public_addresses(host, port):
    """Resolve and validate every address before dialing one pinned address."""
    local = _is_loopback_host(host)
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = [str(literal)]
    else:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        addresses = []
        seen = set()
        for answer in answers:
            try:
                address_text = answer[4][0]
                address = ipaddress.ip_address(address_text.split("%", 1)[0])
            except (IndexError, TypeError, ValueError):
                raise OSError("could not validate resolved address") from None
            text = str(address)
            if text not in seen:
                seen.add(text)
                addresses.append(text)
    if not addresses:
        raise OSError("hostname did not resolve")

    for address_text in addresses:
        address = ipaddress.ip_address(address_text)
        if local:
            if not address.is_loopback:
                raise _ClientError(URL_BLOCKED)
        elif not address.is_global:
            raise _ClientError(URL_BLOCKED)
    return addresses


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host, address, port, timeout):
        super().__init__(host, port=port, timeout=timeout)
        self._pinned_address = address

    def connect(self):
        if self._tunnel_host:
            raise OSError("proxy tunnels are not supported")
        self.sock = socket.create_connection(
            (self._pinned_address, self.port), self.timeout, self.source_address
        )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, port, timeout):
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        if self._tunnel_host:
            raise OSError("proxy tunnels are not supported")
        sock = socket.create_connection(
            (self._pinned_address, self.port), self.timeout, self.source_address
        )
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _default_transport(url):
    """Perform one bounded request without proxies or unvalidated redirects."""
    allowed, _code = _check_url(url, allow_local=True)
    if not allowed:
        raise _ClientError(URL_BLOCKED)
    parsed = urlsplit(url)
    host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    addresses = _resolve_public_addresses(host, port)
    if parsed.scheme.lower() == "https":
        connection = _PinnedHTTPSConnection(host, addresses[0], port, REQUEST_TIMEOUT)
    else:
        connection = _PinnedHTTPConnection(host, addresses[0], port, REQUEST_TIMEOUT)

    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    host_header = f"[{host}]" if ":" in host else host
    default_port = 443 if parsed.scheme.lower() == "https" else 80
    if port != default_port:
        host_header += f":{port}"
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Host": host_header,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                "User-Agent": "Goat-FreeStack/1.0",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            body = body[:MAX_RESPONSE_BYTES]
        return {
            "status": response.status,
            "headers": dict(response.getheaders()),
            "body": body,
            "url": url,
        }
    finally:
        connection.close()


def _query_or_error(query):
    if not isinstance(query, str) or not query.strip():
        raise _ClientError(URL_BLOCKED)
    return query.strip()


def _limit(max_results):
    try:
        parsed = int(max_results)
    except (TypeError, ValueError, OverflowError):
        parsed = MAX_RESULTS
    return max(0, min(MAX_RESULTS, parsed))


def _truncate(value):
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    return value[:MAX_CONTENT_CHARS], len(value) > MAX_CONTENT_CHARS


def _truncate_answer_extract(value):
    """Boundary-safe truncation for answer evidence extracts only.

    Ordinary search/title paths keep the original bounded character-clip
    contract via :func:`_truncate`. Answer extracts must never present a
    character-clipped tail as a complete sentence, so cut back to the last
    verified sentence boundary within the limit (empty when none exists).
    """
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    if len(value) <= MAX_CONTENT_CHARS:
        return value, False
    truncated_flag = True
    limit = MAX_CONTENT_CHARS
    boundary_re = re.compile(r"[.!?]+\s+|[\r\n]+")
    abbrev = frozenset((
        "mr", "mrs", "ms", "miss", "dr", "prof", "professor",
        "sr", "jr", "st", "vs", "etc", "eg", "ie",
    ))

    def _is_abbrev(text, ps, pe):
        try:
            before = text[:ps].rstrip()
            m = re.search(r"([A-Za-z0-9]+)\.?$", before)
            if m:
                w = m.group(1).casefold()
                if w in abbrev:
                    return True
                if len(w) == 1 and w.isalpha():
                    return True
            if ps > 0 and text[ps - 1].isdigit():
                rest = text[pe:].lstrip()
                if rest and rest[0].isdigit():
                    return True
        except Exception:
            return False
        return False

    best = -1
    for match in boundary_re.finditer(value):
        s, e = match.span()
        chunk = match.group(0)
        if "\n" in chunk or "\r" in chunk:
            if s > limit:
                break
            if s > 0 and value[s - 1] in ".!?":
                ps = s - 1
                while ps > 0 and value[ps - 1] in ".!?":
                    ps -= 1
                if _is_abbrev(value, ps, s):
                    continue
                best = s
            else:
                best = s
            if e > limit:
                break
            continue
        pe = s
        while pe < e and value[pe] in ".!?":
            pe += 1
        if pe > limit:
            break
        if _is_abbrev(value, s, pe):
            continue
        best = pe
    if best <= 0:
        return "", truncated_flag
    return value[:best].strip(), truncated_flag


def _valid_result_url(url):
    allowed, _code = _check_url(url)
    return allowed


def _json_body(body):
    try:
        return json.loads(body)
    except (TypeError, ValueError):
        raise _ClientError(URL_BLOCKED) from None


def _require_answer_endpoint(url):
    allowed, _code = _check_url(url)
    if not allowed:
        raise _ClientError(URL_BLOCKED)
    try:
        parsed = urlsplit(url)
        expected = urlsplit(WIKIPEDIA_ACTION_ENDPOINT)
    except ValueError:
        raise _ClientError(URL_BLOCKED) from None
    if parsed.scheme != "https":
        raise _ClientError(URL_BLOCKED)
    try:
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        raise _ClientError(URL_BLOCKED) from None
    if host != "en.wikipedia.org":
        raise _ClientError(URL_BLOCKED)
    if parsed.path != expected.path:
        raise _ClientError(URL_BLOCKED)
    try:
        port = parsed.port
    except ValueError:
        raise _ClientError(URL_BLOCKED) from None
    if port is not None:
        raise _ClientError(URL_BLOCKED)
    if parsed.username is not None or parsed.password is not None:
        raise _ClientError(URL_BLOCKED)
    if "@" in parsed.netloc:
        raise _ClientError(URL_BLOCKED)
    if parsed.fragment:
        raise _ClientError(URL_BLOCKED)


def _fetch_answer_once(url, transport):
    """One fixed-endpoint request; reject redirects and foreign final URLs."""
    _require_answer_endpoint(url)
    response = transport(url)
    status, body, final_url, _headers = _response_parts(response)
    try:
        if __package__:
            from .result_contract import http_error_code as _shared_http_error_code
        else:
            from result_contract import http_error_code as _shared_http_error_code
    except Exception:
        _shared_http_error_code = None
    try:
        if isinstance(response, (str, bytes)):
            _raw_status = 200
        elif isinstance(response, Mapping):
            _fields = {"status", "body", "text", "url", "final_url", "headers"}
            if _fields.intersection(response):
                _raw_status = response.get("status", 200)
            else:
                _raw_status = 200
        else:
            _raw_status = getattr(response, "status", 200)
    except Exception:
        _raw_status = 0
    if final_url:
        try:
            allowed, _code = _check_url(final_url, allow_local=False)
        except Exception:
            raise _ClientError(REDIRECT_BLOCKED) from None
        if not allowed:
            raise _ClientError(REDIRECT_BLOCKED)
        if final_url != url:
            raise _ClientError(REDIRECT_BLOCKED)
    if _shared_http_error_code is not None:
        try:
            _code = _shared_http_error_code(_raw_status, body)
        except Exception:
            _code = URL_BLOCKED
        if _code is not None:
            raise _ClientError(_code)
    if isinstance(_raw_status, bool) or type(_raw_status) is not int:
        raise _ClientError(URL_BLOCKED)
    if 300 <= _raw_status <= 399:
        raise _ClientError(REDIRECT_BLOCKED)
    if not 200 <= _raw_status <= 299:
        raise _ClientError(URL_BLOCKED)
    return _raw_status, body, final_url or url


def _ddg_result_url(raw_url):
    if not isinstance(raw_url, str) or not raw_url:
        return None
    try:
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        return None
    if host == "duckduckgo.com" or host.endswith(".duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        if not target:
            return None
        raw_url = target
    elif not parsed.scheme:
        raw_url = urljoin(DDG_ENDPOINT, raw_url)
    allowed, _code = _check_url(raw_url)
    return raw_url if allowed else None


@result_operation
def duckduckgo_search(query, transport=None, *, max_results=MAX_RESULTS):
    """Search DuckDuckGo's keyless HTML endpoint and parse result anchors."""
    try:
        search_text = _query_or_error(query)
        limit = _limit(max_results)
        fetch = _transport_or_default(transport)
        url = DDG_ENDPOINT + "?" + urlencode({"q": search_text})
        _status, body, _final_url = _fetch(url, fetch)
        parser = _SearchParser()
        parser.feed(body)
        parser.close()
        truncated = len(parser.results) > limit
        results = []
        for index, item in enumerate(parser.results[:limit]):
            result_url = _ddg_result_url(item["url"])
            if result_url is None:
                continue
            title, title_cut = _truncate(item["title"])
            snippet = parser.snippets[index] if index < len(parser.snippets) else ""
            snippet, snippet_cut = _truncate(snippet)
            truncated = truncated or title_cut or snippet_cut
            candidate = {"title": title, "url": result_url, "snippet": snippet}
            if snippet_cut:
                candidate["snippet_cut"] = True
            results.append(candidate)
        return {"ok": True, "results": results, "truncated": truncated}
    except Exception as error:
        return _error_result(error)


def _has_english_provenance(effective_url):
    try:
        parsed = urlsplit(effective_url)
        expected = urlsplit(WIKIPEDIA_ACTION_ENDPOINT)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    try:
        host = (parsed.hostname or "").encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        return False
    if host != "en.wikipedia.org":
        return False
    if parsed.path != expected.path:
        return False
    return True


@result_operation
def wikipedia_search(query, transport=None, *, max_results=MAX_RESULTS):
    """Search Wikipedia through its keyless MediaWiki Action API."""
    try:
        search_text = _query_or_error(query)
        limit = _limit(max_results)
        fetch = _transport_or_default(transport)
        url = WIKIPEDIA_ACTION_ENDPOINT + "?" + urlencode({
            "action": "query",
            "list": "search",
            "srsearch": search_text,
            "srlimit": limit,
            "format": "json",
            "formatversion": 2,
        })
        _status, body, effective_url = _fetch(url, fetch)
        payload = _json_body(body)
        if not isinstance(payload, Mapping):
            raise _ClientError(URL_BLOCKED)
        query_data = payload.get("query")
        items = query_data.get("search") if isinstance(query_data, Mapping) else None
        if not isinstance(items, list):
            raise _ClientError(URL_BLOCKED)
        truncated = len(items) > limit
        results = []
        for item in items[:limit]:
            if not isinstance(item, Mapping):
                continue
            title = item.get("title", "")
            if not isinstance(title, str):
                title = str(title)
            raw_url = item.get("fullurl")
            if not isinstance(raw_url, str) or not raw_url:
                slug = quote(title.replace(" ", "_"), safe="()_,")
                raw_url = "https://en.wikipedia.org/wiki/" + slug
            if not _valid_result_url(raw_url):
                continue
            clean_title, title_cut = _truncate(title)
            snippet, snippet_cut = _truncate(_plain_text(item.get("snippet", "")))
            truncated = truncated or title_cut or snippet_cut
            candidate = {"title": clean_title, "url": raw_url, "snippet": snippet}
            if snippet_cut:
                candidate["snippet_cut"] = True
            try:
                candidate_host = (urlsplit(raw_url).hostname or "").lower().rstrip(".")
            except ValueError:
                candidate_host = ""
            # Source-owned: the fixed Action endpoint is English Wikipedia, so
            # only candidates that remain on the English canonical host carry
            # English when the effective response endpoint is still the fixed
            # English endpoint. Foreign/unknown fullurl values stay unlabeled.
            if candidate_host == "en.wikipedia.org" and _has_english_provenance(effective_url):
                candidate["language"] = "en"
            results.append(candidate)
        return {"ok": True, "results": results, "truncated": truncated}
    except Exception as error:
        return _error_result(error)


def _is_safe_answer_title(value):
    if not isinstance(value, str):
        return False
    title = value.strip()
    if not title or len(title) > 512:
        return False
    if "|" in title:
        return False
    if any(ord(char) < 32 or ord(char) == 127 for char in title):
        return False
    return True


def _valid_answer_pageid(value):
    return type(value) is int and value > 0


@result_operation
def wikipedia_answer_search(query, transport=None, *, max_results=MAX_RESULTS):
    """Bounded Wikipedia intro-extract evidence for default answers.

    Uses only the fixed Action endpoint: one keyword search plus one
    batched ``prop=extracts&explaintext=1&exintro=1`` request built from
    the search response's own titles (no continuation, no arbitrary URL
    fetch, no provider fullurl). Canonical source URLs are generated
    from titles. Each extract is capped at 8000 chars, at most 5 pages
    and 40000 total chars. Missing/invalid/disambiguation pages are
    skipped. No snippet fallback: results carry ``extract`` text.
    """
    try:
        if type(max_results) is not int or not 1 <= max_results <= MAX_RESULTS:
            raise _ClientError(URL_BLOCKED)
        limit = max_results
        search_text = _query_or_error(query)
        if len(search_text) > 2000:
            raise _ClientError(URL_BLOCKED)
        fetch = _transport_or_default(transport)
        search_url = WIKIPEDIA_ACTION_ENDPOINT + "?" + urlencode({
            "action": "query",
            "list": "search",
            "srsearch": search_text,
            "srlimit": limit,
            "format": "json",
            "formatversion": 2,
        })
        _status, body, _final_url = _fetch_answer_once(search_url, fetch)
        payload = _json_body(body)
        if not isinstance(payload, Mapping):
            raise _ClientError(URL_BLOCKED)
        query_data = payload.get("query")
        items = query_data.get("search") if isinstance(query_data, Mapping) else None
        if not isinstance(items, list):
            raise _ClientError(URL_BLOCKED)
        truncated = len(items) > limit
        requested = []
        seen = set()
        requested_pageids = set()
        for item in items[:limit]:
            if not isinstance(item, Mapping):
                continue
            raw_title = item.get("title", "")
            if not _is_safe_answer_title(raw_title):
                continue
            title = raw_title.strip()
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            raw_pid = item.get("pageid")
            pid = raw_pid if _valid_answer_pageid(raw_pid) else None
            if pid is not None:
                requested_pageids.add(pid)
            requested.append((title, pid))
            if len(requested) >= limit:
                break
        requested = requested[:MAX_RESULTS]
        if not requested:
            return {"ok": True, "results": [], "truncated": truncated}
        requested_titles = {title.casefold() for title, _pid in requested}
        if len(requested_pageids) == len(requested) and requested_pageids:
            extracts_params = {
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "exintro": 1,
                "pageids": "|".join(str(pid) for _t, pid in requested),
                "format": "json",
                "formatversion": 2,
            }
        else:
            extracts_params = {
                "action": "query",
                "prop": "extracts",
                "explaintext": 1,
                "exintro": 1,
                "titles": "|".join(title for title, _pid in requested),
                "format": "json",
                "formatversion": 2,
            }
        extracts_url = WIKIPEDIA_ACTION_ENDPOINT + "?" + urlencode(extracts_params)
        _status2, body2, _final2 = _fetch_answer_once(extracts_url, fetch)
        payload2 = _json_body(body2)
        if not isinstance(payload2, Mapping):
            raise _ClientError(URL_BLOCKED)
        query_data2 = payload2.get("query")
        pages_value = query_data2.get("pages") if isinstance(query_data2, Mapping) else None
        if isinstance(pages_value, Mapping):
            pages = list(pages_value.values())
        elif isinstance(pages_value, list):
            pages = pages_value
        else:
            raise _ClientError(URL_BLOCKED)
        results = []
        total_chars = 0
        truncated = truncated or len(pages_value) > limit if isinstance(pages_value, (list, Mapping)) else truncated
        for page in pages[:MAX_RESULTS]:
            if not isinstance(page, Mapping):
                continue
            if "missing" in page or "invalid" in page:
                continue
            raw_title = page.get("title", "")
            if not _is_safe_answer_title(raw_title):
                continue
            title = raw_title.strip()
            raw_pid = page.get("pageid")
            pid_valid = _valid_answer_pageid(raw_pid)
            title_match = title.casefold() in requested_titles
            pid_match = pid_valid and raw_pid in requested_pageids
            if not (title_match or pid_match):
                continue
            if "(disambiguation)" in title.casefold():
                continue
            try:
                props = page.get("pageprops")
            except Exception:
                props = None
            if isinstance(props, Mapping):
                try:
                    if "disambiguation" in props:
                        continue
                except Exception:
                    pass
            raw_extract = page.get("extract", "")
            if not isinstance(raw_extract, str):
                continue
            clean_extract = _plain_text(raw_extract)
            if not clean_extract:
                continue
            if "may refer to:" in clean_extract.casefold():
                continue
            _clean_title, title_cut = _truncate(title)
            truncated = truncated or title_cut
            clean_extract, extract_cut = _truncate_answer_extract(clean_extract)
            truncated = truncated or extract_cut
            if total_chars + len(clean_extract) > MAX_RESULTS * MAX_CONTENT_CHARS:
                truncated = True
                break
            total_chars += len(clean_extract)
            slug = quote(title.replace(" ", "_"), safe="()_,")
            canonical = "https://en.wikipedia.org/wiki/" + slug
            if not _valid_result_url(canonical):
                continue
            results.append({
                "title": title,
                "url": canonical,
                "extract": clean_extract,
                "language": "en",
            })
            if len(results) >= limit:
                break
        return {"ok": True, "results": results, "truncated": truncated}
    except Exception as error:
        return _error_result(error)


def _searxng_endpoint(instance_url):
    if not isinstance(instance_url, str) or not instance_url.strip():
        raise _ClientError(MISSING_CONFIG)
    instance_url = instance_url.strip()
    allowed, _code = _check_url(instance_url, allow_local=True)
    if not allowed:
        raise _ClientError(URL_BLOCKED)
    try:
        parsed = urlsplit(instance_url)
        if parsed.query or parsed.fragment:
            raise _ClientError(URL_BLOCKED)
        path = parsed.path.rstrip("/") + "/search"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))
    except ValueError:
        raise _ClientError(URL_BLOCKED) from None


@result_operation
def searxng_search(
    query,
    instance_url=DEFAULT_SEARXNG_URL,
    transport=None,
    *,
    max_results=MAX_RESULTS,
    base_url=None,
):
    """Search the configured SearXNG instance (localhost:8888 by default).

    Loopback HTTP is permitted only for this local instance. A missing or
    unreachable instance returns ``MISSING_CONFIG``; provider keys are never
    requested or exposed.
    """
    try:
        if base_url is not None:
            instance_url = base_url
        endpoint = _searxng_endpoint(instance_url)
        search_text = _query_or_error(query)
        limit = _limit(max_results)
        fetch = _transport_or_default(transport)
        url = endpoint + "?" + urlencode({"q": search_text, "format": "json"})
        _status, body, _final_url = _fetch(url, fetch, allow_local=True)
        payload = _json_body(body)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            raise _ClientError(URL_BLOCKED)
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
            snippet_value = item.get("content", item.get("snippet", item.get("description", "")))
            snippet, snippet_cut = _truncate(snippet_value)
            truncated = truncated or title_cut or snippet_cut
            candidate = {"title": title, "url": result_url, "snippet": snippet}
            if snippet_cut:
                candidate["snippet_cut"] = True
            results.append(candidate)
        return {"ok": True, "results": results, "truncated": truncated}
    except Exception as error:
        return _error_result(error, instance_unreachable=True)


@result_operation
def fallback_chain(
    query,
    instance_url=DEFAULT_SEARXNG_URL,
    transport=None,
    *,
    max_results=MAX_RESULTS,
    allow_fallback=False,
    transports=None,
    searxng_transport=None,
    wikipedia_transport=None,
    ddg_transport=None,
):
    """Search SearXNG, Wikipedia and DuckDuckGo under an explicit fallback policy.

    Fallback is disabled unless ``allow_fallback=True``. ``MISSING_CONFIG``
    always stops immediately, regardless of that policy. Every returned result
    identifies its source; fallback results also list each transition and its
    reason. ``transports`` may map provider names to injected one-URL callables.
    Named transport arguments take precedence; ``transport`` is a shared
    fallback useful for sequential offline fixtures.
    """
    if transports is not None and not isinstance(transports, Mapping):
        return {**_error(URL_BLOCKED), "source": None}
    supplied = transports or {}
    providers = (
        ("searxng", searxng_transport, searxng_search),
        ("wikipedia", wikipedia_transport, wikipedia_search),
        ("ddg", ddg_transport, duckduckgo_search),
    )
    transitions = []

    def with_source(response, source):
        result = dict(response)
        result["source"] = source
        if transitions:
            result["transitions"] = list(transitions)
        return result

    for index, (name, explicit_transport, client) in enumerate(providers):
        selected_transport = explicit_transport
        if selected_transport is None:
            selected_transport = supplied.get(name)
        if selected_transport is None and name == "ddg":
            selected_transport = supplied.get("duckduckgo")
        if selected_transport is None:
            selected_transport = transport
        if name == "searxng":
            response = client(
                query, instance_url=instance_url, transport=selected_transport, max_results=max_results
            )
        else:
            response = client(query, transport=selected_transport, max_results=max_results)

        if response.get("ok") is True:
            if response.get("results"):
                return with_source(response, name)
            if allow_fallback is not True or index == len(providers) - 1:
                return with_source(response, name)
            reason = "NO_RESULTS"
        else:
            error = response.get("error")
            code = error.get("code") if isinstance(error, Mapping) else None
            if code == MISSING_CONFIG:
                return with_source(response, name)
            if allow_fallback is not True or index == len(providers) - 1:
                return with_source(response, name)
            reason = code if isinstance(code, str) else "PROVIDER_ERROR"

        next_name = providers[index + 1][0]
        transitions.append({"from": name, "to": next_name, "reason": reason})

    return with_source(_error(URL_BLOCKED), providers[-1][0])


# Short aliases retain intuitive provider names without duplicating logic.
ddg_search = duckduckgo_search
wikipedia_action_search = wikipedia_search


__all__ = [
    "DEFAULT_SEARXNG_URL",
    "DDG_ENDPOINT",
    "WIKIPEDIA_ACTION_ENDPOINT",
    "MAX_CONTENT_CHARS",
    "MAX_RESULTS",
    "MAX_RESPONSE_BYTES",
    "MISSING_CONFIG",
    "REDIRECT_BLOCKED",
    "URL_BLOCKED",
    "ddg_search",
    "duckduckgo_search",
    "fallback_chain",
    "searxng_search",
    "wikipedia_action_search",
    "wikipedia_answer_search",
    "wikipedia_search",
]
