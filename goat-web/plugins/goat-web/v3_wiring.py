"""V3 tool composition: trusted dependencies and official-only operations.

Binds the real ``answer_synth.goat_answer`` adapter, the real
``search_filters.with_search_filters`` wrapper and the real
``free_verticals.register()`` vertical mapping to explicit dependencies.
Default routes use only the four fixed official HTTPS API endpoints behind
the final vendored ``ssrf_guard.pinned_fetch``.
"""

import dataclasses
import re
from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Optional
from urllib.parse import urlsplit

from ._goat_v3_vendor import answer_synth as _vendor_answer
from ._goat_v3_vendor import free_stack as _vendor_stack
from ._goat_v3_vendor import free_verticals as _vendor_verticals
from ._goat_v3_vendor import result_contract as _vendor_contract
from ._goat_v3_vendor import search_filters as _vendor_filters
from ._goat_v3_vendor import ssrf_guard as _vendor_guard


WIKIPEDIA_ACTION_ENDPOINT = "https://en.wikipedia.org/w/api.php"
CROSSREF_ENDPOINT = "https://api.crossref.org/works"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
COMMONS_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
WIKIPEDIA_SOURCE = "wikipedia"
WIKIPEDIA_SOURCE_URL = WIKIPEDIA_ACTION_ENDPOINT

_VERTICAL_META = {
    "scholar": ("crossref", "https://www.crossref.org/"),
    "news": ("gdelt", "https://gdeltproject.org/"),
    "images": ("wikimedia-commons", "https://commons.wikimedia.org/"),
}

_PINNED_TIMEOUT = 10
_PINNED_MAX_BYTES = 1048576
_PINNED_MAX_REDIRECTS = 0

_CANDIDATE_CAP = 5


@dataclasses.dataclass(frozen=True)
class WiringDependencies:
    """Host/test-owned dependency object; explicit values replace defaults."""

    search: Optional[Callable[..., Any]] = None
    vertical_transports: Optional[Mapping[str, Any]] = None
    answer_search: Optional[Callable[..., Any]] = None

    def __post_init__(self):
        transports = self.vertical_transports
        if transports is not None:
            if not isinstance(transports, Mapping):
                raise TypeError("vertical_transports must be a mapping or None")
            snapshot = MappingProxyType(dict(transports))
        else:
            snapshot = None
        object.__setattr__(self, "vertical_transports", snapshot)


def _require_exact_endpoint(url, endpoint):
    """Fail closed unless ``url`` matches the fixed HTTPS authority/path."""
    if not isinstance(url, str):
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    allowed, _code = _vendor_guard.check_url(url)
    if not allowed:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    try:
        expected = urlsplit(endpoint)
        parsed = urlsplit(url)
    except ValueError:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED) from None
    if parsed.scheme != "https":
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    if parsed.username is not None or parsed.password is not None:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    if "@" in parsed.netloc:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    if parsed.fragment:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    if parsed.netloc.endswith(":"):
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    try:
        port = parsed.port
    except ValueError:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED) from None
    if port is not None:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    if parsed.netloc != expected.netloc:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    if parsed.path != expected.path:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)


def _require_wikipedia_url(url):
    _require_exact_endpoint(url, WIKIPEDIA_ACTION_ENDPOINT)


def _call_official(url, endpoint, *, _fetch, _resolver, _connection_factory):
    """Fetch one fixed-endpoint URL; classify HTTP errors, keep SSRF blocks."""
    _require_exact_endpoint(url, endpoint)
    fetch = _fetch if _fetch is not None else _vendor_guard.pinned_fetch
    response = fetch(
        url,
        timeout=_PINNED_TIMEOUT,
        max_response_bytes=_PINNED_MAX_BYTES,
        max_redirects=_PINNED_MAX_REDIRECTS,
        resolver=_resolver,
        connection_factory=_connection_factory,
    )
    try:
        if isinstance(response, Mapping):
            status_value = response.get("status", 0)
            body = response.get("body", response.get("text", ""))
        else:
            status_value = getattr(response, "status", 0)
            body = getattr(response, "body", getattr(response, "text", ""))
    except Exception:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED) from None
    try:
        code = _vendor_contract.http_error_code(status_value, body)
    except Exception:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED) from None
    if code is not None:
        raise _vendor_guard.GuardError(code)
    if isinstance(status_value, bool) or type(status_value) is not int:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    if 300 <= status_value <= 399:
        raise _vendor_guard.GuardError(_vendor_guard.REDIRECT_BLOCKED)
    if not 200 <= status_value <= 299:
        raise _vendor_guard.GuardError(_vendor_guard.URL_BLOCKED)
    try:
        if body is None:
            _empty = True
        elif isinstance(body, str):
            _empty = body.strip() == ""
        elif isinstance(body, (bytes, bytearray)):
            _empty = bytes(body).decode("utf-8", errors="replace").strip() == ""
        else:
            _empty = False
    except Exception:
        _empty = False
    if _empty:
        raise _vendor_guard.GuardError(_vendor_guard.HTTP_ERROR)
    return response


def make_official_transport(endpoint, *, _fetch=None, _resolver=None,
                             _connection_factory=None):
    """Build a transport pinned to one fixed official HTTPS endpoint."""

    def _transport(url, *, _fetch=_fetch, _resolver=_resolver,
                   _connection_factory=_connection_factory):
        return _call_official(
            url,
            endpoint,
            _fetch=_fetch,
            _resolver=_resolver,
            _connection_factory=_connection_factory,
        )

    return _transport


def wikipedia_transport(url, *, _fetch=None, _resolver=None, _connection_factory=None):
    """Fetch one fixed-endpoint Wikipedia Action URL; reject all non-2xx."""
    return _call_official(
        url,
        WIKIPEDIA_ACTION_ENDPOINT,
        _fetch=_fetch,
        _resolver=_resolver,
        _connection_factory=_connection_factory,
    )


def make_default_search(*, _fetch=None, _resolver=None, _connection_factory=None):
    """Build the trusted default Wikipedia Action search dependency."""

    _transport = make_official_transport(
        WIKIPEDIA_ACTION_ENDPOINT,
        _fetch=_fetch,
        _resolver=_resolver,
        _connection_factory=_connection_factory,
    )

    def _search(query, *, max_results=_CANDIDATE_CAP):
        try:
            raw = _vendor_stack.wikipedia_search(
                query, transport=_transport, max_results=max_results
            )
        except Exception as error:
            return {
                "ok": False,
                "error": {"code": _vendor_contract.public_error_code(error)},
            }
        if not isinstance(raw, Mapping):
            return {"ok": False, "error": {"code": "URL_BLOCKED"}}
        if raw.get("ok") is False or raw.get("error") is not None:
            return {
                "ok": False,
                "error": {"code": _vendor_contract.public_error_code(raw.get("error"))},
            }
        out = dict(raw)
        out["source"] = WIKIPEDIA_SOURCE
        out["source_url"] = WIKIPEDIA_SOURCE_URL
        return out

    return _search


_ANSWER_STOPWORDS = frozenset((
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did",
    "done", "the", "a", "an", "of", "for", "to", "in", "on", "at", "by",
    "with", "about", "as", "from", "that", "this", "these", "those", "it",
    "its", "and", "or", "but", "if", "then", "than", "so", "such", "no",
    "not", "only", "own", "same", "tell", "me", "you", "your", "please",
    "name", "give", "list", "show",
))
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _answer_keywords(query):
    if not isinstance(query, str):
        return ""
    tokens = _TOKEN_RE.findall(query)
    kept = [token for token in tokens if token.casefold() not in _ANSWER_STOPWORDS]
    if kept:
        return " ".join(kept)
    return query.strip()


def make_default_answer_search(*, _fetch=None, _resolver=None, _connection_factory=None):
    """Build the trusted default Wikipedia intro-extract answer dependency."""

    _transport = make_official_transport(
        WIKIPEDIA_ACTION_ENDPOINT,
        _fetch=_fetch,
        _resolver=_resolver,
        _connection_factory=_connection_factory,
    )

    def _answer_search(query, *, max_results=_CANDIDATE_CAP):
        try:
            keywords = _answer_keywords(query)
            raw = _vendor_stack.wikipedia_answer_search(
                keywords, transport=_transport, max_results=max_results
            )
        except Exception as error:
            return {
                "ok": False,
                "error": {"code": _vendor_contract.public_error_code(error)},
            }
        if not isinstance(raw, Mapping):
            return {"ok": False, "error": {"code": "URL_BLOCKED"}}
        if raw.get("ok") is False or raw.get("error") is not None:
            return {
                "ok": False,
                "error": {"code": _vendor_contract.public_error_code(raw.get("error"))},
            }
        out = dict(raw)
        out["source"] = WIKIPEDIA_SOURCE
        out["source_url"] = WIKIPEDIA_SOURCE_URL
        return out

    return _answer_search


def make_vertical_transports(*, _fetch=None, _resolver=None,
                               _connection_factory=None):
    """Build the three fixed official vertical transports."""
    return {
        "scholar": make_official_transport(
            CROSSREF_ENDPOINT,
            _fetch=_fetch,
            _resolver=_resolver,
            _connection_factory=_connection_factory,
        ),
        "news": make_official_transport(
            GDELT_ENDPOINT,
            _fetch=_fetch,
            _resolver=_resolver,
            _connection_factory=_connection_factory,
        ),
        "images": make_official_transport(
            COMMONS_ENDPOINT,
            _fetch=_fetch,
            _resolver=_resolver,
            _connection_factory=_connection_factory,
        ),
    }


def default_dependencies(*, _fetch=None, _resolver=None, _connection_factory=None):
    """Build default dependencies; used only when ``deps`` is omitted."""
    return WiringDependencies(
        search=make_default_search(
            _fetch=_fetch,
            _resolver=_resolver,
            _connection_factory=_connection_factory,
        ),
        vertical_transports=make_vertical_transports(
            _fetch=_fetch,
            _resolver=_resolver,
            _connection_factory=_connection_factory,
        ),
        answer_search=make_default_answer_search(
            _fetch=_fetch,
            _resolver=_resolver,
            _connection_factory=_connection_factory,
        ),
    )


def _failure(code):
    return {"ok": False, "error": {"code": code}}


def _safe_candidate(item):
    if not isinstance(item, Mapping):
        return False
    try:
        url = item.get("url")
    except Exception:
        return False
    if not isinstance(url, str) or not url:
        return False
    if len(url) > _vendor_answer.MAX_URL_CHARS:
        return False
    try:
        allowed, _code = _vendor_guard.check_url(url)
    except Exception:
        return False
    return bool(allowed)


def _make_answer_operation(deps):
    def _answer_operation(query, max_results=_CANDIDATE_CAP):
        try:
            answer_backend = getattr(deps, "answer_search", None)
        except Exception:
            answer_backend = None
        if answer_backend is None or not callable(answer_backend):
            search = deps.search
        else:
            search = answer_backend
        if search is None or not callable(search):
            return _failure("MISSING_CONFIG")
        stripped = query.strip() if isinstance(query, str) else query
        try:
            plan = _vendor_answer.decompose_query(stripped)
        except Exception:
            plan = None
        if not isinstance(plan, list):
            plan = None
        _is_two_hop = (
            isinstance(plan, list)
            and len(plan) == 2
            and isinstance(plan[0], str)
            and isinstance(plan[1], str)
        )
        if not _is_two_hop:
            try:
                response = search(stripped, max_results=_CANDIDATE_CAP)
            except Exception as error:
                return _failure(_vendor_contract.public_error_code(error))
            try:
                normalized_backend = _vendor_contract.normalize_result(response)
            except Exception:
                return _failure("URL_BLOCKED")
            try:
                backend_failed = (
                    normalized_backend.get("ok") is False
                    or normalized_backend.get("error") is not None
                )
            except Exception:
                return _failure("URL_BLOCKED")
            if backend_failed:
                try:
                    code = _vendor_contract.public_error_code(
                        normalized_backend.get("error")
                    )
                except Exception:
                    code = "URL_BLOCKED"
                return _failure(code)
            try:
                results = normalized_backend.get("results")
            except Exception:
                return _failure("URL_BLOCKED")
            if not isinstance(results, list):
                return _failure("URL_BLOCKED")
            try:
                overproduced = len(results) > _CANDIDATE_CAP
            except Exception:
                return _failure("URL_BLOCKED")
            try:
                candidates = list(results[:_CANDIDATE_CAP])
            except Exception:
                return _failure("URL_BLOCKED")
            safe = [item for item in candidates if _safe_candidate(item)]
            provenance = {}
            for _key in (
                "source",
                "source_url",
                "transitions",
                "truncated",
                "metadata",
                "provenance",
            ):
                try:
                    if _key in normalized_backend:
                        provenance[_key] = normalized_backend[_key]
                except Exception:
                    return _failure("URL_BLOCKED")

            def _synth_search(_candidate_query):
                return {"ok": True, "results": list(safe)}

            try:
                raw = _vendor_answer.goat_answer(
                    stripped, search=_synth_search, max_results=max_results
                )
            except Exception as error:
                return _failure(_vendor_contract.public_error_code(error))
            if not isinstance(raw, Mapping):
                return _failure("URL_BLOCKED")
            try:
                raw_failed = (
                    raw.get("ok") is False or raw.get("error") is not None
                )
            except Exception:
                return _failure("URL_BLOCKED")
            if raw_failed:
                try:
                    code = _vendor_contract.public_error_code(raw.get("error"))
                except Exception:
                    code = "URL_BLOCKED"
                return _failure(code)
            try:
                out = dict(raw)
            except Exception:
                return _failure("URL_BLOCKED")
            out["ok"] = True
            for _key, _value in provenance.items():
                if _key in ("answer", "sources", "ok", "error", "results"):
                    continue
                out[_key] = _value
            truncated_needed = bool(overproduced)
            if truncated_needed:
                try:
                    present = "truncated" in out
                except Exception:
                    return _failure("URL_BLOCKED")
                if not present:
                    out["truncated"] = True
                else:
                    try:
                        current = out.get("truncated")
                    except Exception:
                        return _failure("URL_BLOCKED")
                    if current is False:
                        out["truncated"] = True
            return out
        hop1 = plan[0]
        try:
            response1 = search(hop1, max_results=_CANDIDATE_CAP)
        except Exception as error:
            return _failure(_vendor_contract.public_error_code(error))
        try:
            normalized1 = _vendor_contract.normalize_result(response1)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            backend_failed1 = (
                normalized1.get("ok") is False
                or normalized1.get("error") is not None
            )
        except Exception:
            return _failure("URL_BLOCKED")
        if backend_failed1:
            try:
                code = _vendor_contract.public_error_code(
                    normalized1.get("error")
                )
            except Exception:
                code = "URL_BLOCKED"
            return _failure(code)
        try:
            results1 = normalized1.get("results")
        except Exception:
            return _failure("URL_BLOCKED")
        if not isinstance(results1, list):
            return _failure("URL_BLOCKED")
        try:
            overproduced1 = len(results1) > _CANDIDATE_CAP
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            candidates1 = list(results1[:_CANDIDATE_CAP])
        except Exception:
            return _failure("URL_BLOCKED")
        safe1 = [item for item in candidates1 if _safe_candidate(item)]
        provenance1 = {}
        for _key in (
            "source",
            "source_url",
            "transitions",
            "truncated",
            "metadata",
            "provenance",
        ):
            try:
                if _key in normalized1:
                    provenance1[_key] = normalized1[_key]
            except Exception:
                return _failure("URL_BLOCKED")

        def _synth_search1(_candidate_query):
            return {"ok": True, "results": list(safe1)}

        try:
            raw1 = _vendor_answer.goat_answer(
                hop1, search=_synth_search1, max_results=max_results
            )
        except Exception as error:
            return _failure(_vendor_contract.public_error_code(error))
        if not isinstance(raw1, Mapping):
            return _failure("URL_BLOCKED")
        try:
            raw_failed1 = (
                raw1.get("ok") is False or raw1.get("error") is not None
            )
        except Exception:
            return _failure("URL_BLOCKED")
        if raw_failed1:
            try:
                _err1 = raw1.get("error")
            except Exception:
                return _failure("URL_BLOCKED")
            _insufficient1 = False
            try:
                if isinstance(_err1, Mapping):
                    _c1 = _err1.get("code")
                    if _c1 == "INSUFFICIENT_EVIDENCE":
                        _insufficient1 = True
                    elif isinstance(_c1, Mapping) and _c1.get("code") == "INSUFFICIENT_EVIDENCE":
                        _insufficient1 = True
                    elif _err1.get("error") == "INSUFFICIENT_EVIDENCE":
                        _insufficient1 = True
                elif _err1 == "INSUFFICIENT_EVIDENCE":
                    _insufficient1 = True
            except Exception:
                _insufficient1 = False
            if _insufficient1:
                return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
            try:
                code = _vendor_contract.public_error_code(raw1.get("error"))
            except Exception:
                code = "URL_BLOCKED"
            return _failure(code)
        try:
            hop1_answer = raw1.get("answer", "")
            hop1_sources = raw1.get("sources", [])
        except Exception:
            return _failure("URL_BLOCKED")
        if not isinstance(hop1_answer, str):
            hop1_answer = ""
        if not isinstance(hop1_sources, list):
            return _failure("URL_BLOCKED")
        try:
            bridge = _vendor_answer.extract_bridge_entity(hop1_answer)
        except Exception:
            bridge = ""
        if not isinstance(bridge, str) or not bridge:
            return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
        hop2 = plan[1].replace("{bridge}", bridge)
        try:
            response2 = search(hop2, max_results=_CANDIDATE_CAP)
        except Exception as error:
            return _failure(_vendor_contract.public_error_code(error))
        try:
            normalized2 = _vendor_contract.normalize_result(response2)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            backend_failed2 = (
                normalized2.get("ok") is False
                or normalized2.get("error") is not None
            )
        except Exception:
            return _failure("URL_BLOCKED")
        if backend_failed2:
            try:
                code = _vendor_contract.public_error_code(
                    normalized2.get("error")
                )
            except Exception:
                code = "URL_BLOCKED"
            return _failure(code)
        try:
            results2 = normalized2.get("results")
        except Exception:
            return _failure("URL_BLOCKED")
        if not isinstance(results2, list):
            return _failure("URL_BLOCKED")
        try:
            overproduced2 = len(results2) > _CANDIDATE_CAP
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            candidates2 = list(results2[:_CANDIDATE_CAP])
        except Exception:
            return _failure("URL_BLOCKED")
        safe2 = [item for item in candidates2 if _safe_candidate(item)]
        provenance2 = {}
        for _key in (
            "source",
            "source_url",
            "transitions",
            "truncated",
            "metadata",
            "provenance",
        ):
            try:
                if _key in normalized2:
                    provenance2[_key] = normalized2[_key]
            except Exception:
                return _failure("URL_BLOCKED")

        def _synth_search2(_candidate_query):
            return {"ok": True, "results": list(safe2)}

        try:
            raw2 = _vendor_answer.goat_answer(
                hop2, search=_synth_search2, max_results=max_results
            )
        except Exception as error:
            return _failure(_vendor_contract.public_error_code(error))
        if not isinstance(raw2, Mapping):
            return _failure("URL_BLOCKED")
        try:
            raw_failed2 = (
                raw2.get("ok") is False or raw2.get("error") is not None
            )
        except Exception:
            return _failure("URL_BLOCKED")
        if raw_failed2:
            try:
                _err2 = raw2.get("error")
            except Exception:
                return _failure("URL_BLOCKED")
            _insufficient2 = False
            try:
                if isinstance(_err2, Mapping):
                    _c2 = _err2.get("code")
                    if _c2 == "INSUFFICIENT_EVIDENCE":
                        _insufficient2 = True
                    elif isinstance(_c2, Mapping) and _c2.get("code") == "INSUFFICIENT_EVIDENCE":
                        _insufficient2 = True
                    elif _err2.get("error") == "INSUFFICIENT_EVIDENCE":
                        _insufficient2 = True
                elif _err2 == "INSUFFICIENT_EVIDENCE":
                    _insufficient2 = True
            except Exception:
                _insufficient2 = False
            if _insufficient2:
                return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
            try:
                code = _vendor_contract.public_error_code(raw2.get("error"))
            except Exception:
                code = "URL_BLOCKED"
            return _failure(code)
        try:
            hop2_answer = raw2.get("answer", "")
            hop2_sources = raw2.get("sources", [])
        except Exception:
            return _failure("URL_BLOCKED")
        if not isinstance(hop2_answer, str):
            hop2_answer = ""
        if not isinstance(hop2_sources, list):
            return _failure("URL_BLOCKED")
        if hop2_answer:
            try:
                _neg_re = getattr(_vendor_answer, "_NEGATION_RE", None)
            except Exception:
                _neg_re = None
            if _neg_re is None:
                _neg_re = re.compile(
                    r"\b(never|not|no|neither|nor|without|deny|denies|denied|false)\b"
                    r"|n['\u2019]t\b|\bcannot\b",
                    re.IGNORECASE,
                )
            try:
                _bridge_tokens = [t.casefold() for t in _TOKEN_RE.findall(bridge)]
            except Exception:
                _bridge_tokens = []
            _conflict = False
            if _bridge_tokens:
                try:
                    _claim_fn = getattr(_vendor_answer, "_claim_texts", None)
                    _ev_fn = getattr(_vendor_answer, "_evidence_text", None)
                except Exception:
                    _claim_fn = None
                    _ev_fn = None
                for _item in safe2:
                    try:
                        if _ev_fn is not None:
                            _ev = _ev_fn(_item)
                        else:
                            _ev = ""
                            if isinstance(_item, Mapping):
                                _ex = _item.get("extract", "")
                                _ev = _ex.strip() if isinstance(_ex, str) else ""
                                if not _ev:
                                    _sn = _item.get("snippet", _item.get("description", ""))
                                    _ev = _sn.strip() if isinstance(_sn, str) else ""
                    except Exception:
                        continue
                    if not _ev:
                        continue
                    try:
                        if _claim_fn is not None:
                            _sents = _claim_fn(_ev)
                        else:
                            _sents = [_ev]
                    except Exception:
                        _sents = [_ev]
                    for _sent in _sents:
                        try:
                            _stoks = set(_TOKEN_RE.findall(_sent.casefold()))
                        except Exception:
                            continue
                        if not all(_bt in _stoks for _bt in _bridge_tokens):
                            continue
                        try:
                            if _neg_re.search(_sent.casefold()):
                                _conflict = True
                                break
                        except Exception:
                            continue
                    if _conflict:
                        break
            if _conflict:
                return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
        try:
            _m = len(hop1_sources)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            _shifted = re.sub(
                r"\[(\d+)\]",
                lambda _mo: "[%d]" % (int(_mo.group(1)) + _m),
                hop2_answer,
            )
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            hop1_stamped = []
            for _s in hop1_sources:
                if not isinstance(_s, Mapping):
                    return _failure("URL_BLOCKED")
                _d = dict(_s)
                _d["hop"] = 1
                hop1_stamped.append(_d)
            hop2_renumbered = []
            for _s in hop2_sources:
                if not isinstance(_s, Mapping):
                    return _failure("URL_BLOCKED")
                _d = dict(_s)
                try:
                    _idx = _d.get("index")
                except Exception:
                    return _failure("URL_BLOCKED")
                if not isinstance(_idx, int):
                    return _failure("URL_BLOCKED")
                _d["index"] = _idx + _m
                _d["hop"] = 2
                hop2_renumbered.append(_d)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            out = dict(raw2)
        except Exception:
            return _failure("URL_BLOCKED")
        out["answer"] = _shifted
        out["sources"] = hop1_stamped + hop2_renumbered
        out["ok"] = True
        try:
            if "error" in out:
                del out["error"]
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            if "results" in out:
                del out["results"]
        except Exception:
            return _failure("URL_BLOCKED")
        for _key, _value in provenance2.items():
            if _key in ("answer", "sources", "ok", "error", "results"):
                continue
            out[_key] = _value
        try:
            out["hops"] = [
                {"query": hop1, "answer": hop1_answer, "sources": hop1_stamped},
                {"query": hop2, "answer": hop2_answer, "sources": hop2_renumbered},
            ]
        except Exception:
            return _failure("URL_BLOCKED")
        truncated_needed = bool(overproduced1 or overproduced2)
        if truncated_needed:
            try:
                present = "truncated" in out
            except Exception:
                return _failure("URL_BLOCKED")
            if not present:
                out["truncated"] = True
            else:
                try:
                    current = out.get("truncated")
                except Exception:
                    return _failure("URL_BLOCKED")
                if current is False:
                    out["truncated"] = True
        return out

    return _answer_operation


def _make_filtered_search_operation(deps):
    def _filtered_operation(
        query,
        max_results=_CANDIDATE_CAP,
        time_after=None,
        time_before=None,
        allowed_domains=None,
        denied_domains=None,
        language=None,
    ):
        backend = deps.search

        def _bounded(inner_query, **_kwargs):
            question = inner_query
            try:
                if backend is None or not callable(backend):
                    return _failure("MISSING_CONFIG")
                response = backend(question, max_results=_CANDIDATE_CAP)
            except Exception as error:
                return _failure(_vendor_contract.public_error_code(error))
            normalized = _vendor_contract.normalize_result(response)
            if (
                normalized.get("ok") is False
                or normalized.get("error") is not None
            ):
                return _failure(
                    _vendor_contract.public_error_code(
                        normalized.get("error")
                    )
                )
            results = normalized.get("results")
            if not isinstance(results, list):
                return _failure("URL_BLOCKED")
            if len(results) > _CANDIDATE_CAP:
                capped = dict(normalized)
                capped["results"] = list(results[:_CANDIDATE_CAP])
                capped["truncated"] = True
                return capped
            return normalized

        try:
            wrapper = _vendor_filters.with_search_filters(
                _bounded,
                time_after=time_after,
                time_before=time_before,
                allowed_domains=allowed_domains,
                denied_domains=denied_domains,
                language=language,
            )
        except Exception as error:
            return _failure(_vendor_contract.public_error_code(error))
        try:
            raw = wrapper(query)
        except Exception as error:
            return _failure(_vendor_contract.public_error_code(error))
        normalized = _vendor_contract.normalize_result(raw)
        if (
            normalized.get("ok") is False
            or normalized.get("error") is not None
        ):
            return _failure(
                _vendor_contract.public_error_code(normalized.get("error"))
            )
        results = normalized.get("results")
        if not isinstance(results, list):
            return _failure("URL_BLOCKED")
        if type(max_results) is not int or max_results != max_results:
            return _failure("URL_BLOCKED")
        if len(results) > max_results:
            out = dict(normalized)
            out["results"] = list(results[:max_results])
            out["truncated"] = True
            return out
        return normalized

    return _filtered_operation


def _make_vertical_operation(deps):
    def _vertical_operation(vertical, query, max_results=_CANDIDATE_CAP):
        if type(max_results) is not int or max_results != max_results:
            return _failure("URL_BLOCKED")
        operations = _vendor_verticals.register()
        mapping = {
            "scholar": operations.get("goat_scholar"),
            "news": operations.get("goat_news"),
            "images": operations.get("goat_images"),
        }
        operation = mapping.get(vertical)
        if operation is None or not callable(operation):
            return _failure("URL_BLOCKED")
        transports = deps.vertical_transports
        try:
            selected = transports.get(vertical) if isinstance(transports, Mapping) else None
        except Exception:
            selected = None
        if selected is None or not callable(selected):
            return _failure("MISSING_CONFIG")
        try:
            raw = operation(query, transport=selected, limit=max_results)
        except Exception as error:
            return _failure(_vendor_contract.public_error_code(error))
        if not isinstance(raw, Mapping):
            return _failure("URL_BLOCKED")
        if raw.get("ok") is False or raw.get("error") is not None:
            return _failure(_vendor_contract.public_error_code(raw.get("error")))
        out = dict(raw)
        out["ok"] = True
        out["vertical"] = vertical
        source, source_url = _VERTICAL_META[vertical]
        out["source"] = source
        out["source_url"] = source_url
        return out

    return _vertical_operation


def make_handlers(deps):
    """Return the V3 operation mapping bound to explicit dependencies."""
    return {
        "goat_answer": _make_answer_operation(deps),
        "goat_filtered_search": _make_filtered_search_operation(deps),
        "goat_vertical_search": _make_vertical_operation(deps),
    }
