"""Hermes directory-plugin wrapper for the GOAT web tools."""

import json

from ._goat_v3_vendor.result_contract import normalize_result, public_error_code
from . import v3_wiring
from .goat_tools import register as goat_handlers
from .tool_schemas import SCHEMAS, validate_args


def _failure_envelope(error):
    try:
        code = public_error_code(error)
    except Exception:
        code = "URL_BLOCKED"
    return {"ok": False, "error": {"code": code}}


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


def register(ctx, *, deps=None):
    """Register the legacy tools plus the V3 answer tool with Hermes."""
    bound = v3_wiring.default_dependencies() if deps is None else deps
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
