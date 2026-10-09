"""Fail-closed public HTTPS URL validation and pinned stdlib fetching.

Importing this module performs no DNS or network activity. Resolvers and
connection factories are injectable so security tests can stay fully offline.
"""

import http.client
import ipaddress
import re
import socket
import ssl
from urllib.parse import urljoin, urlsplit


OK = "OK"
URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
PRIVATE_HOST = "PRIVATE_HOST"
BAD_SCHEME = "BAD_SCHEME"
BAD_PORT = "BAD_PORT"
CREDENTIALS_IN_URL = "CREDENTIALS_IN_URL"
MAX_RESPONSE_BYTES = 1_048_576
MAX_REDIRECTS = 2
MAX_TIMEOUT_SECONDS = 30

_DOMAIN_RE = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\Z")
_REDIRECT_STATUSES = frozenset((300, 301, 302, 303, 305, 307, 308))
_METADATA_ADDRESSES = frozenset(
    (
        ipaddress.ip_network("169.254.169.254/32"),
        ipaddress.ip_network("100.100.100.200/32"),
        ipaddress.ip_network("fd00:ec2::254/128"),
    )
)


class GuardError(Exception):
    """A URL-gate failure carrying a sanitized public error code."""

    def __init__(self, code):
        self.code = code if code in (REDIRECT_BLOCKED, PRIVATE_HOST, BAD_SCHEME, BAD_PORT, CREDENTIALS_IN_URL, URL_BLOCKED) else URL_BLOCKED
        super().__init__(self.code)


def _blocked_address(address):
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return (
        not address.is_global
        or address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or any(address.version == network.version and address in network for network in _METADATA_ADDRESSES)
    )


def _normalize_host(host):
    if not isinstance(host, str) or not host or "%" in host:
        return None
    try:
        return host.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        return None


def _blocked_name(host):
    return any(host == suffix or host.endswith("." + suffix) for suffix in ("localhost", "local", "internal"))


def _numeric_looking_host(host):
    final_label = host.rsplit(".", 1)[-1]
    return final_label.isdecimal() or (
        final_label.startswith("0x")
        and len(final_label) > 2
        and all(char in "0123456789abcdef" for char in final_label[2:])
    )


def check_url(url):
    """Return ``(allowed, code)`` for an HTTPS URL on port 443 only.

    Hostnames are syntactically checked here. DNS answers are checked by
    ``resolve_and_validate`` or by ``pinned_fetch`` immediately before connect.
    """
    if not isinstance(url, str) or not url or url != url.strip():
        return False, URL_BLOCKED
    if "\\" in url or any(ord(char) < 0x20 or ord(char) == 0x7F for char in url):
        return False, URL_BLOCKED
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False, URL_BLOCKED
    if parsed.scheme.lower() != "https":
        return False, BAD_SCHEME
    if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
        return False, CREDENTIALS_IN_URL
    if parsed.netloc.endswith(":"):
        return False, BAD_PORT
    try:
        port = parsed.port
    except ValueError:
        return False, BAD_PORT
    if port is not None and port != 443:
        return False, BAD_PORT
    raw_host = parsed.hostname
    if not raw_host:
        return False, URL_BLOCKED
    try:
        address = ipaddress.ip_address(raw_host)
    except ValueError:
        address = None
    if address is not None:
        return (False, PRIVATE_HOST) if _blocked_address(address) else (True, OK)
    host = _normalize_host(raw_host)
    if not host or len(host) > 253:
        return False, URL_BLOCKED
    if _blocked_name(host) or _numeric_looking_host(host):
        return False, PRIVATE_HOST
    if not _DOMAIN_RE.fullmatch(host):
        return False, URL_BLOCKED
    labels = host.split(".")
    if any(len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        return False, URL_BLOCKED
    return True, OK


def _address_from_answer(answer):
    if isinstance(answer, str):
        candidate = answer
    else:
        try:
            sockaddr = answer[4]
            candidate = sockaddr[0] if isinstance(sockaddr, (tuple, list)) else sockaddr
        except (IndexError, KeyError, TypeError):
            try:
                candidate = answer[0]
            except (IndexError, KeyError, TypeError):
                raise GuardError(URL_BLOCKED) from None
    if not isinstance(candidate, str):
        raise GuardError(URL_BLOCKED)
    try:
        return ipaddress.ip_address(candidate.split("%", 1)[0])
    except ValueError:
        raise GuardError(URL_BLOCKED) from None


def resolve_and_validate(host, resolver=None):
    """Resolve every answer and reject the hostname if any answer is non-public.

    ``resolver`` follows ``socket.getaddrinfo(host, port, type=...)``. It is not
    invoked until this function is called; import-time use is always offline.
    """
    normalized = _normalize_host(host)
    if not normalized:
        raise GuardError(URL_BLOCKED)
    try:
        literal = ipaddress.ip_address(normalized)
    except ValueError:
        literal = None
    if literal is not None:
        if _blocked_address(literal):
            raise GuardError(PRIVATE_HOST)
        return [str(literal)]

    lookup = socket.getaddrinfo if resolver is None else resolver
    try:
        answers = lookup(normalized, 443, type=socket.SOCK_STREAM)
    except Exception:
        raise GuardError(URL_BLOCKED) from None
    if not answers:
        raise GuardError(URL_BLOCKED)
    verified = []
    seen = set()
    for answer in answers:
        address = _address_from_answer(answer)
        if _blocked_address(address):
            raise GuardError(PRIVATE_HOST)
        text = str(address)
        if text not in seen:
            seen.add(text)
            verified.append(text)
    if not verified:
        raise GuardError(URL_BLOCKED)
    return verified


def resolve_public_url(url, resolver=None):
    """Validate URL syntax and resolve every DNS answer, failing closed.

    When ``resolver`` is omitted the system resolver is used. Fetching code must
    use the returned addresses to pin its connection; validation alone is only
    a preflight for adapters whose transport pins independently.
    """
    allowed, code = check_url(url)
    if not allowed:
        raise GuardError(code)
    parsed = urlsplit(url)
    if not parsed.hostname:
        raise GuardError(URL_BLOCKED)
    return resolve_and_validate(parsed.hostname, resolver=resolver)


def validate_public_url(url, resolver=None):
    """Validate public HTTPS/443 syntax and resolve every DNS answer.

    Omitting ``resolver`` uses the system resolver; this function never skips
    DNS validation for hostnames. Network transports must still pin the
    returned address (``pinned_fetch`` does so at connection time) to close the
    DNS-rebinding window.
    """
    resolve_public_url(url, resolver=resolver)
    return True


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Dial the verified address while retaining host-based TLS verification."""

    def __init__(self, hostname, address, timeout=10):
        super().__init__(hostname, port=443, timeout=timeout, context=ssl.create_default_context())
        self._pinned_address = address

    def connect(self):
        if self._tunnel_host:
            raise OSError("HTTPS proxy tunnels are not supported")
        sock = socket.create_connection((self._pinned_address, self.port), self.timeout, self.source_address)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _pinned_request_once(url, *, resolver, timeout, max_response_bytes, connection_factory):
    allowed, code = check_url(url)
    if not allowed:
        raise GuardError(code)
    parsed = urlsplit(url)
    raw_host = parsed.hostname
    if not raw_host:
        raise GuardError(URL_BLOCKED)
    try:
        ip_literal = ipaddress.ip_address(raw_host)
    except ValueError:
        ip_literal = None
    hostname = str(ip_literal) if ip_literal is not None else _normalize_host(raw_host)
    if not hostname:
        raise GuardError(URL_BLOCKED)
    addresses = resolve_and_validate(hostname, resolver=resolver)
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    host_header = "[" + hostname + "]" if isinstance(ip_literal, ipaddress.IPv6Address) else hostname
    if parsed.netloc.endswith(":443"):
        host_header += ":443"
    factory = _PinnedHTTPSConnection if connection_factory is None else connection_factory
    connection = factory(hostname, addresses[0], timeout=timeout)
    try:
        connection.request(
            "GET",
            path,
            headers={
                "Host": host_header,
                "User-Agent": "goat-packs/1.0",
                "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.5",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        body = response.read(max_response_bytes + 1)
        if not isinstance(body, bytes) or len(body) > max_response_bytes:
            raise GuardError(URL_BLOCKED)
        headers = {str(name).lower(): value for name, value in response.getheaders()}
        return {"status": response.status, "headers": headers, "body": body, "url": url}
    except GuardError:
        raise
    except Exception:
        raise GuardError(URL_BLOCKED) from None
    finally:
        try:
            connection.close()
        except Exception:
            pass


def pinned_fetch(
    url,
    *,
    resolver=None,
    timeout=10,
    max_response_bytes=MAX_RESPONSE_BYTES,
    connection_factory=None,
    max_redirects=MAX_REDIRECTS,
):
    """Fetch HTTPS by a freshly resolved/pinned IP; revalidate each redirect.

    Response bodies are read with a one-byte overflow probe and rejected if
    larger than ``max_response_bytes``. A custom ``connection_factory`` is a
    test seam; it receives ``(hostname, pinned_address, timeout=...)``.
    """
    if (
        isinstance(max_response_bytes, bool)
        or not isinstance(max_response_bytes, int)
        or not 1 <= max_response_bytes <= MAX_RESPONSE_BYTES
    ):
        raise ValueError("max_response_bytes must be between 1 and MAX_RESPONSE_BYTES")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not 0 < timeout <= MAX_TIMEOUT_SECONDS
    ):
        raise ValueError("timeout must be finite and between zero and MAX_TIMEOUT_SECONDS")
    if isinstance(max_redirects, bool) or not isinstance(max_redirects, int) or not 0 <= max_redirects <= MAX_REDIRECTS:
        raise ValueError("max_redirects must be between zero and MAX_REDIRECTS")
    current = url
    redirects = 0
    while True:
        if redirects:
            try:
                response = _pinned_request_once(
                    current,
                    resolver=resolver,
                    timeout=timeout,
                    max_response_bytes=max_response_bytes,
                    connection_factory=connection_factory,
                )
            except GuardError:
                raise GuardError(REDIRECT_BLOCKED) from None
        else:
            response = _pinned_request_once(
                current,
                resolver=resolver,
                timeout=timeout,
                max_response_bytes=max_response_bytes,
                connection_factory=connection_factory,
            )
        location = response["headers"].get("location")
        if response["status"] not in _REDIRECT_STATUSES or not isinstance(location, str) or not location:
            return response
        if redirects >= max_redirects:
            if max_redirects == 0:
                return response
            raise GuardError(REDIRECT_BLOCKED)
        try:
            target = urljoin(current, location)
        except (TypeError, ValueError):
            raise GuardError(REDIRECT_BLOCKED) from None
        allowed, _code = check_url(target)
        if not allowed:
            raise GuardError(REDIRECT_BLOCKED)
        current = target
        redirects += 1


__all__ = [
    "BAD_PORT",
    "BAD_SCHEME",
    "CREDENTIALS_IN_URL",
    "GuardError",
    "MAX_REDIRECTS",
    "MAX_RESPONSE_BYTES",
    "MAX_TIMEOUT_SECONDS",
    "OK",
    "PRIVATE_HOST",
    "REDIRECT_BLOCKED",
    "URL_BLOCKED",
    "check_url",
    "pinned_fetch",
    "resolve_and_validate",
    "resolve_public_url",
    "validate_public_url",
]
