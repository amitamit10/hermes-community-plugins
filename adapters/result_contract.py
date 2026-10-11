"""Central stdlib result contract for public adapter operations."""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from typing import Any

URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
MISSING_CONFIG = "MISSING_CONFIG"
PROVIDER_BLOCKED = "PROVIDER_BLOCKED"

PUBLIC_ERROR_CODES = frozenset((URL_BLOCKED, REDIRECT_BLOCKED, MISSING_CONFIG, PROVIDER_BLOCKED))

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
    "MISSING_CONFIG",
    "PROVIDER_BLOCKED",
    "PUBLIC_ERROR_CODES",
    "REDIRECT_BLOCKED",
    "URL_BLOCKED",
    "error_result",
    "normalize_result",
    "public_error_code",
    "result_operation",
]


def public_error_code(error: Any) -> str:
    """Map any error value to a public error code, cycle-safe."""
    seen: set[int] = set()
    current: Any = error
    for _ in range(16):
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
    return out_fail


def error_result(error: Any, **provenance: Any) -> dict[str, Any]:
    """Build a sanitized failure result with allowlisted provenance only."""
    try:
        code = public_error_code(error)
    except Exception:
        code = URL_BLOCKED
    out: dict[str, Any] = {"ok": False, "error": {"code": code}}
    out.update(_provenance(provenance))
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
