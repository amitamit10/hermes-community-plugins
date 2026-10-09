"""Fail-closed time, domain, and language filters for injected search callables.

Wrap a Goat-style callable with :func:`with_search_filters`. Time bounds are
inclusive UTC instants (date-only values mean midnight UTC). When a filter is
active, results missing usable metadata for that filter are excluded."""

from collections.abc import Mapping
from datetime import date, datetime, time, timezone
import ipaddress
import math
import re
from urllib.parse import urlsplit


URL_BLOCKED = "URL_BLOCKED"
_ERROR_RESULT = {"error": {"code": URL_BLOCKED}}
_DATE_FIELDS = (
    "published_at",
    "publishedAt",
    "published_date",
    "publication_date",
    "published",
    "date",
    "datetime",
    "timestamp",
    "created_at",
)
_LANGUAGE_FIELDS = ("language", "language_code", "lang", "locale")
_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
_LANGUAGE_TAG = re.compile(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*\Z")


class _InvalidFilter(ValueError):
    """Raised internally when filter configuration cannot be trusted."""


def _parse_datetime(value):
    """Convert a supported date/time value into an aware UTC datetime."""
    if isinstance(value, bool):
        raise _InvalidFilter("boolean is not a date")
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise _InvalidFilter("non-finite timestamp")
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            raise _InvalidFilter("timestamp out of range") from None
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            raise _InvalidFilter("expected an ISO date or datetime") from None
    else:
        raise _InvalidFilter("unsupported date value")

    try:
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise _InvalidFilter("invalid timezone-aware date") from None


def _normalize_host(value):
    """Normalize a bare DNS name or IP literal; reject URL-like values."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise _InvalidFilter("domain must be a non-empty bare host")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise _InvalidFilter("whitespace/control character in domain")
    candidate = value[:-1] if value.endswith(".") else value
    if not candidate or candidate.endswith(".") or "/" in candidate or "\\" in candidate or "@" in candidate or "%" in candidate:
        raise _InvalidFilter("domain must be a bare host")

    ip_text = candidate[1:-1] if candidate.startswith("[") and candidate.endswith("]") else candidate
    try:
        return str(ipaddress.ip_address(ip_text))
    except ValueError:
        pass
    if ":" in candidate or "[" in candidate or "]" in candidate:
        raise _InvalidFilter("invalid IP/domain syntax")

    try:
        ascii_host = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError:
        raise _InvalidFilter("invalid internationalized domain") from None
    if len(ascii_host) > 253 or not ascii_host:
        raise _InvalidFilter("domain name is too long")
    labels = ascii_host.split(".")
    if any(not _DOMAIN_LABEL.fullmatch(label) for label in labels):
        raise _InvalidFilter("invalid domain label")
    # Numeric pseudo-addresses such as 127.1 are interpreted inconsistently.
    if labels[-1].isdecimal():
        raise _InvalidFilter("ambiguous numeric host")
    return ascii_host


def _normalize_domain_set(value):
    if value is None:
        return None
    if isinstance(value, str):
        entries = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        entries = value
    else:
        raise _InvalidFilter("domain filter must be a host or finite collection of hosts")
    try:
        return frozenset(_normalize_host(entry) for entry in entries)
    except TypeError:
        raise _InvalidFilter("invalid domain collection") from None


def _normalize_language(value):
    if not isinstance(value, str) or not _LANGUAGE_TAG.fullmatch(value):
        raise _InvalidFilter("language must be a BCP-47-like tag")
    return value.lower()


def _result_host(value):
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() not in ("http", "https"):
            return None
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            return None
        host = parsed.hostname
        if not host:
            return None
        port = parsed.port
        if port is not None and not 1 <= port <= 65535:
            return None
        return _normalize_host(host)
    except (UnicodeError, ValueError, _InvalidFilter):
        return None


def _host_matches(host, domain):
    try:
        ipaddress.ip_address(host)
        return host == domain
    except ValueError:
        try:
            ipaddress.ip_address(domain)
            return host == domain
        except ValueError:
            return host == domain or host.endswith("." + domain)


def _metadata_value(item, fields):
    for field in fields:
        if field in item:
            return item[field]
    return None


def _date_matches(item, lower, upper):
    value = _metadata_value(item, _DATE_FIELDS)
    if value is None:
        return False
    try:
        moment = _parse_datetime(value)
    except _InvalidFilter:
        return False
    return (lower is None or moment >= lower) and (upper is None or moment <= upper)


def _language_matches(item, requested):
    value = _metadata_value(item, _LANGUAGE_FIELDS)
    try:
        actual = _normalize_language(value)
    except _InvalidFilter:
        return False
    if actual == requested:
        return True
    return "-" not in requested and actual.split("-", 1)[0] == requested


def _error_result():
    return {"error": dict(_ERROR_RESULT["error"])}


def with_search_filters(
    search,
    *,
    time_after=None,
    time_before=None,
    allowed_domains=None,
    denied_domains=None,
    language=None,
):
    """Return a wrapper that filters results from an injected search callable.

    ``time_after`` and ``time_before`` are inclusive. Domain entries are bare
    hostnames/IP literals; a listed DNS domain also matches its subdomains.
    Deny rules take precedence over allow rules. A primary language request
    (for example ``en``) matches its regional tags (for example ``en-US``); a
    regional request requires that exact normalized tag.

    Invalid filter configuration, a non-callable backend, backend exceptions,
    and malformed successful responses return the public ``URL_BLOCKED`` error
    envelope without leaking exception details.
    """
    invalid = False
    try:
        lower = None if time_after is None else _parse_datetime(time_after)
        upper = None if time_before is None else _parse_datetime(time_before)
        if lower is not None and upper is not None and lower > upper:
            raise _InvalidFilter("time range is reversed")
        allow = _normalize_domain_set(allowed_domains)
        deny = _normalize_domain_set(denied_domains)
        requested_language = None if language is None else _normalize_language(language)
    except Exception:
        # Untrusted configuration values must never escape as exceptions.
        invalid = True
        lower = upper = allow = deny = requested_language = None

    def filtered_search(*args, **kwargs):
        if invalid or not callable(search):
            return _error_result()
        try:
            payload = search(*args, **kwargs)
        except Exception:
            return _error_result()
        try:
            if not isinstance(payload, Mapping):
                return _error_result()
            if "error" in payload:
                if isinstance(payload["error"], Mapping):
                    return dict(payload)
                return _error_result()
            if payload.get("ok") is False or not isinstance(payload.get("results"), list):
                return _error_result()

            filtered = []
            for item in payload["results"]:
                if not isinstance(item, Mapping):
                    continue
                if (lower is not None or upper is not None) and not _date_matches(item, lower, upper):
                    continue
                if allow is not None or deny is not None:
                    host = _result_host(item.get("url"))
                    if host is None:
                        continue
                    if deny is not None and any(_host_matches(host, domain) for domain in deny):
                        continue
                    if allow is not None and not any(_host_matches(host, domain) for domain in allow):
                        continue
                if requested_language is not None and not _language_matches(item, requested_language):
                    continue
                filtered.append(item)

            result = dict(payload)
            result["results"] = filtered
            return result
        except Exception:
            return _error_result()

    return filtered_search


__all__ = ["URL_BLOCKED", "with_search_filters"]
