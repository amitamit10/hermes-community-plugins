"""Fail-closed URL checks for public web fetches (pinned DNS/network egress by design; unit tests run fully offline with fakes)."""

import ipaddress
import http.client
import re
import socket
from urllib.parse import urljoin, urlsplit


OK = "OK"
BAD_SCHEME = "BAD_SCHEME"
CREDENTIALS_IN_URL = "CREDENTIALS_IN_URL"
PRIVATE_HOST = "PRIVATE_HOST"
BAD_PORT = "BAD_PORT"
URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"

_DOMAIN_RE = re.compile(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\Z")


def _blocked_address(address):
    """Return whether an IP is non-public or belongs to a special-use range."""
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return not address.is_global or any(
        (
            address.is_loopback,
            address.is_private,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def _numeric_looking_host(host):
    """Reject non-canonical numeric hosts some URL stacks parse as IPv4."""
    final_label = host.rsplit(".", 1)[-1]
    return final_label.isdecimal() or (
        final_label.lower().startswith("0x")
        and len(final_label) > 2
        and all(char in "0123456789abcdefABCDEF" for char in final_label[2:])
    )


def _normalize_host(host):
    if not host or "%" in host:
        return None
    try:
        return host.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError):
        return None


def _blocked_name(host):
    return any(
        host == suffix or host.endswith("." + suffix)
        for suffix in ("localhost", "local", "internal")
    )


def check_url(url):
    """Return ``(allowed, code)`` for an HTTPS URL on the default port only."""
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

    authority = parsed.netloc
    if authority.endswith(":"):
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

    # Parse IP literals before DNS-name validation (IPv6 contains colons).
    try:
        address = ipaddress.ip_address(raw_host)
    except ValueError:
        address = None
    if address is not None:
        return (False, PRIVATE_HOST) if _blocked_address(address) else (True, OK)

    host = _normalize_host(raw_host)
    if not host or len(host) > 253:
        return False, URL_BLOCKED
    if _blocked_name(host):
        return False, PRIVATE_HOST
    if _numeric_looking_host(host):
        return False, PRIVATE_HOST
    if not _DOMAIN_RE.fullmatch(host):
        return False, URL_BLOCKED
    labels = host.split(".")
    if any(len(label) > 63 or label.startswith("-") or label.endswith("-") for label in labels):
        return False, URL_BLOCKED
    return True, OK


def _current_https_url(current_host):
    if not isinstance(current_host, str) or not current_host or current_host != current_host.strip():
        return None
    if "\\" in current_host or any(ord(char) < 0x20 or ord(char) == 0x7F for char in current_host):
        return None
    try:
        parsed = urlsplit(current_host)
    except ValueError:
        return None

    if parsed.scheme:
        if parsed.scheme.lower() != "https" or not check_url(current_host)[0]:
            return None
        return current_host

    # The documented argument is a host; accept a bare IPv6 literal as well.
    authority = current_host
    if ":" in authority and not authority.startswith("["):
        try:
            ipaddress.IPv6Address(authority)
        except ValueError:
            pass
        else:
            authority = "[" + authority + "]"
    candidate = "https://" + authority + "/"
    try:
        candidate_parts = urlsplit(candidate)
    except ValueError:
        return None
    if candidate_parts.path != "/" or candidate_parts.query or candidate_parts.fragment:
        return None
    if not check_url(candidate)[0]:
        return None
    return candidate


def check_redirect(current_host, location, hops_used):
    """Validate a redirect target; at most two HTTPS hops are permitted."""
    if isinstance(hops_used, bool) or not isinstance(hops_used, int) or not 0 <= hops_used < 2:
        return False, REDIRECT_BLOCKED
    base_url = _current_https_url(current_host)
    if base_url is None or not isinstance(location, str) or not location:
        return False, REDIRECT_BLOCKED
    if "\\" in location or any(ord(char) < 0x20 or ord(char) == 0x7F for char in location):
        return False, REDIRECT_BLOCKED
    try:
        target = urljoin(base_url, location)
    except (TypeError, ValueError):
        return False, REDIRECT_BLOCKED
    allowed, _code = check_url(target)
    return (True, OK) if allowed else (False, REDIRECT_BLOCKED)


class URLGateError(Exception):
    """A URL-gate failure carrying an internal, non-public error code."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _host_url(host):
    """Build a validation URL for a host-only value."""
    if not isinstance(host, str) or not host or host != host.strip():
        raise URLGateError(URL_BLOCKED)
    candidate_host = host
    if candidate_host.startswith("[") and candidate_host.endswith("]"):
        candidate_host = candidate_host[1:-1]
    try:
        address = ipaddress.ip_address(candidate_host)
    except ValueError:
        address = None
    authority = "[" + candidate_host + "]" if isinstance(address, ipaddress.IPv6Address) else candidate_host
    allowed, code = check_url("https://" + authority + "/")
    if not allowed:
        raise URLGateError(code)
    if address is not None:
        return str(address), authority
    normalized = _normalize_host(candidate_host)
    if not normalized:
        raise URLGateError(URL_BLOCKED)
    return normalized, authority


def _address_from_answer(answer):
    """Extract an address from getaddrinfo output or a plain test address."""
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
                raise URLGateError(URL_BLOCKED) from None
    if not isinstance(candidate, str):
        raise URLGateError(URL_BLOCKED)
    try:
        return ipaddress.ip_address(candidate.split("%", 1)[0])
    except ValueError:
        raise URLGateError(URL_BLOCKED) from None


def resolve_and_validate(host, resolver=None):
    """Resolve a host and reject it if any answer is not globally routable.

    ``resolver`` follows the ``socket.getaddrinfo`` call signature. All answers
    are checked before any address is returned, preventing mixed public/private
    DNS responses from being used selectively.
    """
    normalized_host, _authority = _host_url(host)
    lookup = socket.getaddrinfo if resolver is None else resolver
    try:
        answers = lookup(normalized_host, 443, type=socket.SOCK_STREAM)
    except URLGateError:
        raise
    except Exception as exc:
        raise URLGateError(URL_BLOCKED) from exc
    if not answers:
        raise URLGateError(URL_BLOCKED)

    verified = []
    seen = set()
    for answer in answers:
        address = _address_from_answer(answer)
        if _blocked_address(address):
            raise URLGateError(PRIVATE_HOST)
        text = str(address)
        if text not in seen:
            seen.add(text)
            verified.append(text)
    if not verified:
        raise URLGateError(URL_BLOCKED)
    return verified


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that dials a validated IP but authenticates the host."""

    def __init__(self, hostname, address, timeout=10):
        super().__init__(hostname, port=443, timeout=timeout)
        self._pinned_address = address

    def connect(self):
        if self._tunnel_host:
            raise OSError("HTTPS proxy tunnels are not supported")
        sock = socket.create_connection(
            (self._pinned_address, self.port), self.timeout, self.source_address
        )
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def pinned_fetch(url, resolver=None, timeout=10, max_response_bytes=1_048_576):
    """Fetch an HTTPS URL by a freshly verified IP, following at most 2 hops.

    Each hop is independently URL-checked and resolved. The HTTP Host header
    and TLS SNI/certificate hostname remain the URL hostname, not the pinned IP.
    """
    if isinstance(max_response_bytes, bool) or not isinstance(max_response_bytes, int) or max_response_bytes < 1:
        raise ValueError("max_response_bytes must be a positive integer")
    current = url
    redirects = 0
    while True:
        allowed, code = check_url(current)
        if not allowed:
            raise URLGateError(code)
        parsed = urlsplit(current)
        raw_host = parsed.hostname
        if not raw_host:
            raise URLGateError(URL_BLOCKED)
        try:
            address = ipaddress.ip_address(raw_host)
        except ValueError:
            address = None
        hostname = str(address) if address is not None else _normalize_host(raw_host)
        if not hostname:
            raise URLGateError(URL_BLOCKED)
        try:
            addresses = resolve_and_validate(hostname, resolver=resolver)
        except URLGateError as exc:
            if redirects:
                raise URLGateError(REDIRECT_BLOCKED) from exc
            raise
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        host_header = "[" + hostname + "]" if isinstance(address, ipaddress.IPv6Address) else hostname
        if parsed.netloc.endswith(":443"):
            host_header += ":443"
        connection = _PinnedHTTPSConnection(hostname, addresses[0], timeout=timeout)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Host": host_header,
                    "User-Agent": "goat-web/1.0",
                    "Accept": "text/html,text/plain,application/json;q=0.9,*/*;q=0.5",
                    "Connection": "close",
                },
            )
            response = connection.getresponse()
            body = response.read(max_response_bytes + 1)
            if len(body) > max_response_bytes:
                body = body[:max_response_bytes]
            status = response.status
            headers = {name.lower(): value for name, value in response.getheaders()}
        finally:
            connection.close()

        if status in (301, 302, 303, 307, 308) and headers.get("location"):
            if redirects >= 2:
                raise URLGateError(REDIRECT_BLOCKED)
            allowed, redirect_code = check_redirect(current, headers["location"], redirects)
            if not allowed:
                raise URLGateError(redirect_code)
            current = urljoin(current, headers["location"])
            redirects += 1
            continue
        return {"status": status, "headers": headers, "body": body, "url": current}

