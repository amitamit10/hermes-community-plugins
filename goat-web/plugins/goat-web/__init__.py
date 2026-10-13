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


_KNOWN_ANSWER_STATUS = frozenset((
    "budget_exhausted", "completed", "complete",
    "abstained", "partial", "unsupported",
))
_KNOWN_ANSWER_REASON = frozenset((
    "budget_exhausted", "completed", "complete",
    "abstained", "partial", "unsupported",
    "unsupported_temporal_compare", "unsupported_arithmetic",
    "cycle", "repeated_query",
))


def _sanitize_failure_hops(raw_result):
    try:
        _cands = []
        try:
            if isinstance(raw_result, dict):
                _top = raw_result.get("hops")
                if isinstance(_top, list):
                    _cands = list(_top)
                else:
                    try:
                        _md = raw_result.get("metadata")
                        if isinstance(_md, dict):
                            _mh = _md.get("hops")
                            if isinstance(_mh, list):
                                _cands = list(_mh)
                            else:
                                try:
                                    _pv = raw_result.get("provenance")
                                    if isinstance(_pv, dict):
                                        _ph = _pv.get("hops")
                                        if isinstance(_ph, list):
                                            _cands = list(_ph)
                                except Exception:
                                    pass
                    except Exception:
                        pass
        except Exception:
            return None
        if not _cands:
            return None
        if len(_cands) > 8:
            return None
        from ._goat_v3_vendor.result_contract import public_error_code as _pec
        clean = []
        for _h in _cands[:8]:
            if not isinstance(_h, dict):
                return None
            for _fb in ("answer", "extract", "snippet", "exception", "results", "raw", "upstream", "error"):
                try:
                    if _fb in _h:
                        return None
                except Exception:
                    return None
            try:
                _hid = _h.get("id")
                _hidx = _h.get("index")
                _hdep = _h.get("depth")
                _hst = _h.get("status")
                _hcode = _h.get("code")
                _hurl = _h.get("url", None)
            except Exception:
                return None
            if not isinstance(_hid, str) or not _hid:
                return None
            if type(_hidx) is not int or not 1 <= _hidx <= 8:
                return None
            if type(_hdep) is not int or not 1 <= _hdep <= 8:
                return None
            if not isinstance(_hst, str) or _hst not in ("completed", "failed"):
                return None
            if not isinstance(_hcode, str) or not _hcode:
                return None
            try:
                if _hst == "failed":
                    _pc = _pec({"code": _hcode})
                    if _pc not in ("INSUFFICIENT_EVIDENCE", "MISSING_CONFIG", "URL_BLOCKED", "REDIRECT_BLOCKED", "HTTP_ERROR", "RATE_LIMITED", "PROVIDER_BLOCKED", "DNS_ERROR", "UPSTREAM_TIMEOUT", "CONNECTION_ERROR"):
                        if _hcode not in ("COMPLETED",):
                            return None
                else:
                    if _hcode != "COMPLETED":
                        return None
            except Exception:
                return None
            _entry = {"id": _hid, "index": _hidx, "depth": _hdep, "status": _hst, "code": _hcode}
            try:
                if "depends_on" in _h:
                    _hdeps = _h.get("depends_on")
                    if not isinstance(_hdeps, list):
                        return None
                    for _d in _hdeps:
                        if not isinstance(_d, str) or not _d:
                            return None
                        try:
                            _dn = int(_d[1:]) if _d.startswith("s") else -1
                        except Exception:
                            return None
                        if not 1 <= _dn < _hidx or _dn > 8:
                            return None
                    _entry["depends_on"] = list(_hdeps)
            except Exception:
                return None
            if _hurl is not None:
                if not isinstance(_hurl, str) or not _hurl:
                    return None
                if len(_hurl) > 2048:
                    return None
                try:
                    _al, _cc = _vendor_guard.check_url(_hurl)
                except Exception:
                    return None
                if not _al:
                    return None
                _entry["url"] = _hurl
            clean.append(_entry)
            if len(clean) > 8:
                return None
        return clean
    except Exception:
        return None


def _sanitize_answer_research_metadata(raw_result):
    """Fixed goat_answer-only metadata.research sanitizer (failures only).

    Copies only known status/reason, strict bounded ints, bounded hop IDs
    and safe URLs. Never copies answer/extract/snippet/exception or raw
    upstream metadata. Returns ``{"research": {...}}`` or ``None``.
    """
    try:
        if not isinstance(raw_result, dict):
            try:
                from collections.abc import Mapping as _Mapping

                if not isinstance(raw_result, _Mapping):
                    return None
            except Exception:
                return None
        try:
            metadata = raw_result.get("metadata")
        except Exception:
            return None
        if not isinstance(metadata, dict):
            try:
                from collections.abc import Mapping as _Mapping2

                if not isinstance(metadata, _Mapping2):
                    return None
            except Exception:
                return None
            return None
        try:
            research = metadata.get("research")
        except Exception:
            return None
        if not isinstance(research, dict):
            return None
        try:
            status = research.get("status")
            reason = research.get("reason", status)
            max_hops = research.get("max_hops")
            max_searches = research.get("max_searches")
            hops_planned = research.get("hops_planned")
            hops_completed = research.get("hops_completed")
            planned = research.get("planned", hops_planned)
            executed = research.get("executed", hops_completed)
            search_calls = research.get("search_calls", hops_completed)
            http_requests = research.get("http_requests", None)
            max_http_requests = research.get("max_http_requests", None)
        except Exception:
            return None
        if not isinstance(status, str) or status not in _KNOWN_ANSWER_STATUS:
            return None
        if not isinstance(reason, str) or reason not in _KNOWN_ANSWER_REASON:
            return None
        if type(max_hops) is not int or not 1 <= max_hops <= 4:
            return None
        if type(max_searches) is not int or not 1 <= max_searches <= 8:
            return None
        if type(hops_planned) is not int or not 0 <= hops_planned <= 8:
            return None
        if type(hops_completed) is not int or not 0 <= hops_completed <= 8:
            return None
        if type(planned) is not int or not 0 <= planned <= 8:
            return None
        if type(executed) is not int or not 0 <= executed <= 8:
            return None
        if type(search_calls) is not int or not 0 <= search_calls <= 8:
            return None
        # max_http_requests bounded 2*max_searches; http strict count or None.
        try:
            if max_http_requests is None:
                max_http_requests = 2 * max_searches
            if type(max_http_requests) is not int or max_http_requests != 2 * max_searches:
                return None
            if http_requests is None:
                pass
            elif type(http_requests) is not int or not 0 <= http_requests <= max_http_requests:
                return None
        except Exception:
            return None
        sanitized = {
            "status": status,
            "reason": reason,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "hops_planned": hops_planned,
            "hops_completed": hops_completed,
            "planned": planned,
            "executed": executed,
            "search_calls": search_calls,
            "http_requests": http_requests,
            "max_http_requests": max_http_requests,
        }
        # Bounded candidate accounting (constructed, never upstream copy).
        try:
            for _ck in ("max_candidates_per_call", "candidates_per_call", "candidate_limit"):
                if _ck in research:
                    _cv = research.get(_ck)
                    if type(_cv) is not int or _cv != 5:
                        return None
                    sanitized[_ck] = 5
            for _tk in ("max_candidates_total", "candidates_total", "total_result_limit"):
                if _tk in research:
                    _tv = research.get(_tk)
                    if type(_tv) is not int or _tv != 5 * max_searches:
                        return None
                    sanitized[_tk] = _tv
            if "candidates_considered" in research:
                _ccv = research.get("candidates_considered")
                if type(_ccv) is not int or not 0 <= _ccv <= 40:
                    return None
                sanitized["candidates_considered"] = _ccv
        except Exception:
            return None
        # Closed controlled extras: year exactly four digits, answerable bool.
        try:
            if "year" in research:
                yv = research.get("year")
                if not isinstance(yv, str):
                    return None
                import re as _re_year
                if _re_year.match(r"^\d{4}$", yv) is None:
                    return None
                sanitized["year"] = yv
            if "answerable" in research:
                av = research.get("answerable")
                if type(av) is not bool:
                    return None
                sanitized["answerable"] = av
        except Exception:
            return None
        try:
            if "kind" in research:
                kind = research.get("kind")
                if kind in ("facets", "comparison", "intersection"):
                    sanitized["kind"] = kind
                else:
                    return None
        except Exception:
            return None
        # Optional bounded intermediate evidence: safe URLs only, hop IDs 1..8.
        try:
            has_intermediate = "intermediate_evidence" in research
        except Exception:
            has_intermediate = False
        if has_intermediate:
            try:
                intermediate = research.get("intermediate_evidence")
            except Exception:
                return None
            if not isinstance(intermediate, list) or len(intermediate) > 5:
                return None
            clean_items = []
            for item in intermediate:
                if not isinstance(item, dict):
                    return None
                # Failure copies NO answer/extract/snippet/exception/raw.
                for forbidden in (
                    "answer",
                    "extract",
                    "snippet",
                    "exception",
                    "results",
                    "error",
                    "raw",
                    "upstream",
                ):
                    try:
                        if forbidden in item:
                            return None
                    except Exception:
                        return None
                try:
                    url = item.get("url")
                    title = item.get("title", "")
                    hop = item.get("hop", 1)
                except Exception:
                    return None
                if not isinstance(url, str) or not url:
                    return None
                if len(url) > 2048:
                    return None
                try:
                    allowed, _code = _vendor_guard.check_url(url)
                except Exception:
                    return None
                if not allowed:
                    return None
                if not isinstance(title, str):
                    return None
                if len(title) > 512:
                    return None
                if type(hop) is not int or not 1 <= hop <= 8:
                    return None
                clean_items.append({"url": url, "title": title, "hop": hop})
            sanitized["intermediate_evidence"] = clean_items
        # Reject unexpected top-level research keys beyond allowlist.
        try:
            allowed_keys = {
                "status",
                "reason",
                "max_hops",
                "max_searches",
                "hops_planned",
                "hops_completed",
                "planned",
                "executed",
                "search_calls",
                "http_requests",
                "max_http_requests",
                "max_candidates_per_call",
                "candidates_per_call",
                "candidate_limit",
                "max_candidates_total",
                "candidates_total",
                "total_result_limit",
                "candidates_considered",
                "intermediate_evidence",
                "kind",
                "year",
                "answerable",
            }
            for key in research:
                if key not in allowed_keys:
                    return None
        except Exception:
            return None
        return {"research": sanitized}
    except Exception:
        return None


def _json_handler(operation, parameters, *, _is_goat_answer=False):
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
                if _is_goat_answer:
                    try:
                        sanitized = _sanitize_answer_research_metadata(result)
                    except Exception:
                        sanitized = None
                    if isinstance(sanitized, dict):
                        try:
                            payload["metadata"] = sanitized
                        except Exception:
                            pass
                    # Carry every partial's bounded failure hops through sanitizer.
                    try:
                        _fh = _sanitize_failure_hops(result)
                    except Exception:
                        _fh = None
                    if isinstance(_fh, list) and _fh:
                        try:
                            payload["hops"] = list(_fh)
                        except Exception:
                            pass
                        try:
                            if isinstance(payload.get("metadata"), dict):
                                payload["metadata"]["hops"] = list(_fh)
                            else:
                                payload["metadata"] = {"hops": list(_fh)}
                        except Exception:
                            pass
                # Failure copies NO answer/extract/snippet/exception/raw.
                for _drop in (
                    "answer",
                    "extract",
                    "snippet",
                    "exception",
                    "results",
                    "raw",
                    "upstream",
                ):
                    try:
                        if _drop in payload:
                            del payload[_drop]
                    except Exception:
                        pass
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
            handler=_json_handler(
                operations[name],
                schema["parameters"],
                _is_goat_answer=(name == "goat_answer"),
            ),
            description=schema["description"],
        )
