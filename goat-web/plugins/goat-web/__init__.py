"""Hermes directory-plugin wrapper for the GOAT web tools."""

import json

from ._goat_v3_vendor import ssrf_guard as _vendor_guard
from ._goat_v3_vendor.result_contract import failure_diagnostics, http_error_code, normalize_result, public_error_code
from . import v3_wiring
from .goat_tools import register as goat_handlers
from .tool_schemas import SCHEMAS, validate_args


def _failure_envelope(error):
    try:
        code = public_error_code(error)
    except Exception:
        code = "URL_BLOCKED"
    return {"ok": False, "error": {"code": code}}


def _failure_diagnostics(normalized):
    """Reuse shared diagnostics; JSON failure provenance stays suppressed."""
    try:
        return failure_diagnostics(normalized)
    except Exception:
        return {}


def _json_handler(operation, parameters):
    def call(args, **_kwargs):
        try:
            valid, validated = validate_args(parameters, args)
            if not valid:
                return json.dumps(
                    {"ok": False, "error": {"code": "URL_BLOCKED"}},
                    ensure_ascii=False,
                    allow_nan=False,
                )
            try:
                result = operation(**validated)
            except Exception as error:
                return json.dumps(
                    _failure_envelope(error),
                    ensure_ascii=False,
                    allow_nan=False,
                )
            normalized = normalize_result(result)
            try:
                failed = (
                    normalized.get("ok") is False
                    or normalized.get("error") is not None
                )
            except Exception:
                failed = True
            if failed:
                try:
                    payload = _failure_envelope(normalized.get("error"))
                    payload.update(_failure_diagnostics(normalized))
                except Exception:
                    payload = {"ok": False, "error": {"code": "URL_BLOCKED"}}
            else:
                try:
                    payload = dict(normalized)
                except Exception:
                    payload = {"ok": False, "error": {"code": "URL_BLOCKED"}}
                    return json.dumps(
                        payload, ensure_ascii=False, allow_nan=False
                    )
                payload["ok"] = True
            return json.dumps(payload, ensure_ascii=False, allow_nan=False)
        except Exception as error:
            return json.dumps(
                _failure_envelope(error), ensure_ascii=False, allow_nan=False
            )

    return call


def checked_fetch(url, *, timeout=10, max_response_bytes=_vendor_guard.MAX_RESPONSE_BYTES,
                    max_redirects=_vendor_guard.MAX_REDIRECTS, resolver=None, connection_factory=None):
    """Default fetch boundary: same pinned_fetch, then HTTP/challenge typing.

    The v3 fixed-endpoint URL check in ``_call_official`` still runs before
    this is called. Classified responses raise a sanitized typed GuardError;
    no extra request, retry, endpoint change or redirect/proxy is performed.
    """
    response = _vendor_guard.pinned_fetch(
        url,
        timeout=timeout,
        max_response_bytes=max_response_bytes,
        max_redirects=max_redirects,
        resolver=resolver,
        connection_factory=connection_factory,
    )
    try:
        if isinstance(response, dict):
            status_value = response.get("status", 0)
            body = response.get("body", response.get("text", ""))
        else:
            status_value = getattr(response, "status", 0)
            body = getattr(response, "body", getattr(response, "text", ""))
    except Exception:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED) from None
    code = http_error_code(status_value, body)
    if code is not None:
        raise _vendor_guard.GuardError(code)
    return response


def register(ctx, *, deps=None):
    """Register the legacy tools plus the V3 answer tool with Hermes."""
    bound = v3_wiring.default_dependencies(_fetch=checked_fetch) if deps is None else deps
    operations = {**goat_handlers(), **v3_wiring.make_handlers(bound)}
    assert set(operations) == set(SCHEMAS)
    for name, schema in SCHEMAS.items():
        ctx.register_tool(
            name=name,
            toolset="goat_web",
            schema=schema,
            handler=_json_handler(operations[name], schema["parameters"]),
            description=schema["description"],
        )
