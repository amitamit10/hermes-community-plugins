"""Central stdlib result contract for public adapter operations."""

from __future__ import annotations

import functools
import http.client
import socket
from collections.abc import Callable, Mapping
from html.parser import HTMLParser
from typing import Any

URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
DNS_ERROR = "DNS_ERROR"
UPSTREAM_TIMEOUT = "UPSTREAM_TIMEOUT"
CONNECTION_ERROR = "CONNECTION_ERROR"
MISSING_CONFIG = "MISSING_CONFIG"
PROVIDER_BLOCKED = "PROVIDER_BLOCKED"
HTTP_ERROR = "HTTP_ERROR"
RATE_LIMITED = "RATE_LIMITED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

PUBLIC_ERROR_CODES = frozenset((URL_BLOCKED, REDIRECT_BLOCKED, MISSING_CONFIG, PROVIDER_BLOCKED, HTTP_ERROR, RATE_LIMITED, DNS_ERROR, UPSTREAM_TIMEOUT, CONNECTION_ERROR, INSUFFICIENT_EVIDENCE))

_ALLOWLIST = ("source", "transitions", "truncated")

_REDIRECT_CODES = frozenset(("REDIRECT_FAILED", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT"))

_MISSING_CODES = frozenset((
    "MISSING_CONFIG",
    "PROVIDER_NOT_CONFIGURED",
    "MISSING_PROVIDER_CONFIG",
    "UNVERIFIED_CONFIG",
    "UNAVAILABLE",
))

_URL_CODES = frozenset((
    "URL_BLOCKED",
    "BAD_SCHEME",
    "BAD_PORT",
    "PRIVATE_HOST",
    "CREDENTIALS_IN_URL",
))

_UNSET: Any = object()

__all__ = [
    "CONNECTION_ERROR",
    "DNS_ERROR",
    "HTTP_ERROR",
    "INSUFFICIENT_EVIDENCE",
    "MISSING_CONFIG",
    "PROVIDER_BLOCKED",
    "PUBLIC_ERROR_CODES",
    "RATE_LIMITED",
    "REDIRECT_BLOCKED",
    "UPSTREAM_TIMEOUT",
    "URL_BLOCKED",
    "error_result",
    "failure_diagnostics",
    "http_error_code",
    "normalize_result",
    "public_error_code",
    "result_operation",
]


def public_error_code(error: Any) -> str:
    """Map any error value to a public error code, cycle-safe."""
    seen: set[int] = set()
    current: Any = error
    for _ in range(16):
        if isinstance(current, socket.gaierror):
            return DNS_ERROR
        if isinstance(current, TimeoutError):
            return UPSTREAM_TIMEOUT
        if isinstance(current, OSError):
            return CONNECTION_ERROR
        if isinstance(current, http.client.HTTPException):
            return CONNECTION_ERROR
        if current is None:
            return URL_BLOCKED
        if isinstance(current, Mapping):
            if id(current) in seen:
                return URL_BLOCKED
            seen.add(id(current))
            try:
                if "code" in current:
                    current = current["code"]
                    continue
                if "error" in current:
                    current = current["error"]
                    continue
            except Exception:
                return URL_BLOCKED
            return URL_BLOCKED
        if isinstance(current, str):
            if current in PUBLIC_ERROR_CODES:
                return current
            if current in _REDIRECT_CODES:
                return REDIRECT_BLOCKED
            if current in _MISSING_CODES:
                return MISSING_CONFIG
            return URL_BLOCKED
        try:
            code = getattr(current, "code", _UNSET)
        except Exception:
            return URL_BLOCKED
        if code is _UNSET:
            return URL_BLOCKED
        if code is current:
            return URL_BLOCKED
        if isinstance(code, (str, Mapping)) or code is None or hasattr(code, "code"):
            if isinstance(code, object) and id(code) in seen:
                return URL_BLOCKED
            current = code
            continue
        return URL_BLOCKED
    return URL_BLOCKED


def _validated_status(value: Any) -> int | None:
    """Strict top-level HTTP status: type(x) is int and 100<=x<=599, no coercion."""
    if type(value) is not int:
        return None
    if not 100 <= value <= 599:
        return None
    return value


def _validated_host(value: Any) -> str | None:
    """Bare DNS/IP host only: bounded length, no credentials/path/control/space."""
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
    bracketed = value.startswith("[") and value.endswith("]")
    candidate = value[1:-1] if bracketed else value
    # Accept IP literals (v4/v6, no zone) as-is; brackets are IPv6-only.
    try:
        import ipaddress as _ip

        _ip.ip_address(candidate.split("%", 1)[0] if "%" in candidate else candidate)
        if "%" in candidate:
            return None
        if bracketed and ":" not in candidate:
            return None
        return value
    except Exception:
        if bracketed:
            return None
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


def _validated_retry_after(value: Any) -> int | None:
    """Delta-seconds only: strict int or digit string within 0..31536000."""
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


class _ChallengeParser(HTMLParser):
    """Structural provider-challenge detector (mirrors the extract classifier)."""

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


def _has_structural_challenge(body: Any) -> bool:
    """Return whether the body carries a structural provider-challenge widget.

    HTML comments, escaped markup, script-quoted text and ordinary article
    prose mentioning CAPTCHAs are not challenges.
    """
    try:
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if not isinstance(body, str) or "<" not in body:
            return False
        try:
            import json as _json

            _json.loads(body)
            return False
        except Exception:
            pass
        parser = _ChallengeParser()
        parser.feed(body)
        parser.close()
        return bool(parser.has_challenge)
    except Exception:
        return False


def http_error_code(status: Any, body: Any = None) -> str | None:
    """Classify an HTTP response into a public error code.

    Returns ``None`` when the caller should continue normally (2xx content
    without a challenge, or 3xx redirect handling owned by the caller).
    Unknown or out-of-range statuses fail closed as ``URL_BLOCKED``.
    """
    if isinstance(status, bool):
        return URL_BLOCKED
    if type(status) is not int:
        return URL_BLOCKED
    if _validated_status(status) is None:
        return URL_BLOCKED
    if status == 429:
        return RATE_LIMITED
    if _has_structural_challenge(body):
        return PROVIDER_BLOCKED
    if 200 <= status < 300:
        return None
    if 300 <= status < 400:
        return None
    if not 100 <= status <= 599:
        return URL_BLOCKED
    return HTTP_ERROR


_DIAGNOSTIC_CODES = frozenset((HTTP_ERROR, RATE_LIMITED, PROVIDER_BLOCKED, REDIRECT_BLOCKED))


def _diagnostics(source: Mapping[str, Any] | None) -> dict[str, Any]:
    """Copy only explicitly validated status/host/retry_after diagnostics."""
    out: dict[str, Any] = {}
    if not isinstance(source, Mapping):
        return out
    try:
        if "status" in source:
            valid = _validated_status(source["status"])
            if valid is not None:
                out["status"] = valid
        if "host" in source:
            valid_host = _validated_host(source["host"])
            if valid_host is not None:
                out["host"] = valid_host
        if "retry_after" in source:
            valid_retry = _validated_retry_after(source["retry_after"])
            if valid_retry is not None:
                out["retry_after"] = valid_retry
    except Exception:
        pass
    return out


def failure_diagnostics(result: Any) -> dict[str, Any]:
    """Return validated status/host/retry_after for diagnostic failures only.

    Only ``HTTP_ERROR``/``RATE_LIMITED``/``PROVIDER_BLOCKED``/``REDIRECT_BLOCKED``
    preserve diagnostics; all other codes return ``{}``. Unknown fields are
    never copied and JSON failure provenance stays suppressed.
    """
    try:
        if not isinstance(result, Mapping):
            return {}
        try:
            err = result.get("error", None)
        except Exception:
            return {}
        try:
            code = public_error_code(err)
        except Exception:
            code = URL_BLOCKED
        if code not in _DIAGNOSTIC_CODES:
            return {}
        return _diagnostics(result)
    except Exception:
        return {}


def _provenance(source: Mapping[str, Any] | None, extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Copy only allowlisted provenance keys without traversing values."""
    out: dict[str, Any] = {}
    for container in (source, extra):
        if not isinstance(container, Mapping):
            continue
        for key in _ALLOWLIST:
            try:
                if key in container:
                    out[key] = container[key]
            except Exception:
                continue
    return out


def normalize_result(result: Any) -> dict[str, Any]:
    """Normalize any adapter return to the public result shape."""
    if not isinstance(result, Mapping):
        return {"ok": False, "error": {"code": URL_BLOCKED}}
    try:
        ok_val = result.get("ok", True)
        err_val = result.get("error", None)
    except Exception:
        return {"ok": False, "error": {"code": URL_BLOCKED}}
    failed = (ok_val is False) or (err_val is not None)
    if not failed:
        try:
            out = dict(result)
        except Exception:
            return {"ok": False, "error": {"code": URL_BLOCKED}}
        out["ok"] = True
        return out
    try:
        code = public_error_code(err_val)
    except Exception:
        code = URL_BLOCKED
    out_fail: dict[str, Any] = {"ok": False, "error": {"code": code}}
    out_fail.update(_provenance(result))
    out_fail.update(failure_diagnostics(result))
    return out_fail


def error_result(error: Any, **provenance: Any) -> dict[str, Any]:
    """Build a sanitized failure result with allowlisted provenance only."""
    try:
        code = public_error_code(error)
    except Exception:
        code = URL_BLOCKED
    out: dict[str, Any] = {"ok": False, "error": {"code": code}}
    out.update(_provenance(provenance))
    out.update(failure_diagnostics({"error": {"code": code}, **provenance}))
    return out


def result_operation(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate an explicit public operation with result normalization."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            raw = func(*args, **kwargs)
        except Exception as exc:
            return error_result(exc)
        return normalize_result(raw)

    return wrapper
