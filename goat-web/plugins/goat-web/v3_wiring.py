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


class _AnswerRequestBudget:
    """Per-operation physical HTTP budget token.

    Each logical answer call may use at most two HTTP requests; the whole
    operation may use at most twice ``max_searches``. Shared failure code is
    ``INSUFFICIENT_EVIDENCE`` with controlled status metadata; no retries,
    redirects or endpoint changes.
    """

    def __init__(self, max_searches):
        if type(max_searches) is not int or not 1 <= max_searches <= 8:
            raise ValueError("max_searches out of bounds")
        self.max_searches = max_searches
        self.max_http = 2 * max_searches
        self.used = 0

    def try_consume(self, count=1):
        try:
            if type(count) is bool:
                return False
            if type(count) is not int or count < 1:
                return False
            if self.used + count > self.max_http:
                return False
            self.used += count
            return True
        except Exception:
            return False

    def try_acquire(self, count=1):
        return self.try_consume(count)

    def acquire(self, count=1):
        return self.try_consume(count)


class _BudgetExhausted(Exception):
    """Internal budget exhaustion carrying public INSUFFICIENT_EVIDENCE."""

    def __init__(self):
        super().__init__("INSUFFICIENT_EVIDENCE")
        self.code = "INSUFFICIENT_EVIDENCE"


def make_default_answer_search(*, _fetch=None, _resolver=None, _connection_factory=None):
    """Build the trusted default Wikipedia intro-extract answer dependency."""

    _base_transport = make_official_transport(
        WIKIPEDIA_ACTION_ENDPOINT,
        _fetch=_fetch,
        _resolver=_resolver,
        _connection_factory=_connection_factory,
    )

    def _answer_search(query, *, max_results=_CANDIDATE_CAP, _request_budget=None):
        # Per-logical-call cap <=2 ALWAYS; whole-OP cap via caller-shared token.
        # Missing private token creates LOCAL per-logical token, never factory
        # lifetime cap. Attempt counts increment BEFORE invocation.
        _call_state = {"count": 0}
        if _request_budget is None:
            try:
                _local_budget = _AnswerRequestBudget(1)
            except Exception:
                _local_budget = None

            def _budgeted_transport(
                url, *, _fetch=_fetch, _resolver=_resolver,
                _connection_factory=_connection_factory
            ):
                if _call_state["count"] >= 2:
                    raise _BudgetExhausted()
                if _local_budget is not None:
                    try:
                        _allowed = _local_budget.try_consume(1)
                    except Exception:
                        _allowed = False
                    if _allowed is not True:
                        raise _BudgetExhausted()
                _call_state["count"] += 1
                return _call_official(
                    url,
                    WIKIPEDIA_ACTION_ENDPOINT,
                    _fetch=_fetch,
                    _resolver=_resolver,
                    _connection_factory=_connection_factory,
                )

            _transport = _budgeted_transport
        else:

            def _budgeted_transport(
                url, *, _fetch=_fetch, _resolver=_resolver,
                _connection_factory=_connection_factory
            ):
                if _call_state["count"] >= 2:
                    raise _BudgetExhausted()
                try:
                    consume = getattr(_request_budget, "try_consume", None)
                    if consume is None:
                        consume = getattr(_request_budget, "try_acquire", None)
                    if consume is None:
                        consume = getattr(_request_budget, "acquire", None)
                except Exception:
                    consume = None
                if callable(consume):
                    try:
                        allowed = consume(1)
                    except Exception:
                        allowed = False
                    if allowed is not True:
                        raise _BudgetExhausted()
                else:
                    try:
                        used = getattr(_request_budget, "used", None)
                        max_http = getattr(_request_budget, "max_http", None)
                        if type(used) is not int or type(max_http) is not int:
                            raise _BudgetExhausted()
                        if used + 1 > max_http:
                            raise _BudgetExhausted()
                        setattr(_request_budget, "used", used + 1)
                    except _BudgetExhausted:
                        raise
                    except Exception:
                        raise _BudgetExhausted() from None
                _call_state["count"] += 1
                return _call_official(
                    url,
                    WIKIPEDIA_ACTION_ENDPOINT,
                    _fetch=_fetch,
                    _resolver=_resolver,
                    _connection_factory=_connection_factory,
                )

            _transport = _budgeted_transport
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

    _answer_search._GOAT_BUDGET_AWARE = True
    _answer_search._GOAT_BUILTIN_METERED = True
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


_TRAILING_MARKERS_RE = re.compile(r"((?:\s*\[\d+\])+)\s*$")
_MARKER_FIND_RE = re.compile(r"\[(\d+)\]")
_KNOWN_RESEARCH_STATUS = frozenset((
    "budget_exhausted", "completed", "complete",
    "abstained", "partial", "unsupported",
))
_KNOWN_RESEARCH_REASON = frozenset((
    "budget_exhausted", "completed", "complete",
    "abstained", "partial", "unsupported",
    "unsupported_temporal_compare", "unsupported_arithmetic",
    "cycle", "repeated_query",
))
_TEMPORAL_COMPARE_REASON = "unsupported_temporal_compare"
_ARITHMETIC_REASON = "unsupported_arithmetic"
_YEAR_RE = re.compile(r"^\d{4}$")
_MODAL_RE = re.compile(
    r"\b(may|might|could|would|should|must|shall|will|can|ought)\b"
    r"|\bmay\s+have\b|\bmight\s+have\b|\bcould\s+have\b",
    re.IGNORECASE,
)
_RESEARCH_PLACEHOLDER_RE = re.compile(r"\{s(\d+)\}")


def _is_four_digit_year(value):
    try:
        if not isinstance(value, str):
            return False
        return _YEAR_RE.match(value) is not None
    except Exception:
        return False


def _subject_pattern_for(name):
    try:
        import re as _re2
        toks = _TOKEN_RE.findall(name.casefold()) if isinstance(name, str) else []
        if not toks:
            return ""
        return r"\b" + r"\s+".join(_re2.escape(t) for t in toks) + r"\b"
    except Exception:
        return ""


def _strip_markers(line):
    try:
        return re.sub(r"(?:\s*\[\d+\])+\s*$", "", line).strip()
    except Exception:
        return line.strip() if isinstance(line, str) else ""


def _hop_claim_lines(hop_answer):
    try:
        if not isinstance(hop_answer, str) or not hop_answer:
            return []
        out = []
        for line in hop_answer.split("\n"):
            if not line.strip():
                continue
            cleaned = _strip_markers(line)
            if cleaned:
                out.append(cleaned)
        return out
    except Exception:
        return []


def _is_strict_born_sentence(sentence, subject, facet):
    """Subject-specific whole born sentence gate (conservative).

    Rejects wrong facet type, modal, negative, hedged, conflicting slots.
    Never infers date from location or vice versa. Uses only complete
    source BODY sentences; titles alone never satisfy.
    """
    try:
        if not isinstance(sentence, str) or not sentence:
            return False
        if not isinstance(subject, str) or not subject.strip():
            return False
        if facet not in ("place", "date"):
            return False
        text = sentence.strip()
        if not text:
            return False
        if "?" in text:
            return False
        if not text.rstrip().endswith((".", "!")):
            return False
        low = text.casefold()
        if "born" not in low:
            return False
        # Subject-specific: WHOLE subject was-born assertion must appear.
        # Subject tokens anywhere plus year/place is insufficient; require
        # adjacent "<subject> was|were born" so cross-subject
        # "Mira met Nera who was born ..." cannot anchor.
        try:
            pat = _subject_pattern_for(subject)
            if not pat:
                return False
            if re.search(pat, low) is None:
                return False
            adj_pat = pat + r"\s+(was|were)\s+born\b"
            if re.search(adj_pat, low) is None:
                return False
        except Exception:
            return False
        # Extra relative/joint clauses never become birth evidence.
        try:
            if re.search(r"\b(who|whom|whose|which|that)\b", low) is not None:
                return False
            if re.search(r"\b(met|visiting|visited|visit|before|after|while|during|since|because|although|though|unless|until|and|or|but)\b", low) is not None:
                return False
        except Exception:
            return False
        # Reject modal / negative / hedged via shared unreliable plus modal.
        try:
            neg_re = getattr(_vendor_answer, "_NEGATION_RE", None)
            if neg_re is not None and neg_re.search(low):
                return False
            else:
                # Fallback negation when vendor regex unavailable.
                if neg_re is None and re.search(
                    r"\b(never|not|no|neither|nor|without)\b|n['\u2019]t\b|\bcannot\b",
                    low,
                ):
                    return False
        except Exception:
            return False
        try:
            hedge_re = getattr(_vendor_answer, "_HEDGE_RE", None)
            if hedge_re is not None and hedge_re.search(low):
                return False
        except Exception:
            return False
        try:
            if _MODAL_RE.search(low):
                return False
        except Exception:
            return False
        # Fragmentary / quoted text never becomes evidence.
        try:
            if "..." in text or "\u2026" in text:
                return False
            if '"' in text or "\u201c" in text or "\u201d" in text:
                return False
        except Exception:
            return False
        # Facet conditions: date needs 4-digit year, place needs non-year place.
        # Conservatively reject unsupported numeric date formats (ISO/slashes).
        try:
            if re.search(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", text) is not None:
                return False
            if re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b", text) is not None:
                return False
        except Exception:
            return False
        try:
            years = re.findall(r"\b\d{4}\b", text)
        except Exception:
            years = []
        if facet == "date":
            if not years:
                return False
        else:
            # Place: require born-in whose immediate object is a place, not a
            # year. Date-only "born in 1984 before visiting Arbor" starts with
            # a year so it cannot satisfy Where even though Arbor appears
            # later as the object of "visiting".
            try:
                m = re.search(r"born\s+in\s+([^\.\!\?]+)", text, re.IGNORECASE)
            except Exception:
                m = None
            if m is None:
                return False
            frag = m.group(1)
            try:
                frag_stripped = frag.strip()
                if re.match(r"^\d{4}\b", frag_stripped) is not None:
                    return False
            except Exception:
                return False
            # Remove years from fragment; need a remaining place token.
            try:
                no_year = re.sub(r"\b\d{4}\b", " ", frag)
                toks = re.findall(r"[A-Za-z][\w\-']*", no_year)
            except Exception:
                return False
            has_place = False
            for tok in toks:
                if not tok[:1].isupper():
                    continue
                # Skip generic stopwords that are not places.
                if tok.casefold() in ("in", "the", "a", "an"):
                    continue
                has_place = True
                break
            if not has_place:
                return False
        return True
    except Exception:
        return False


def _born_gate_passes(hop_answer, subject, facet):
    """Require at least one strict born sentence and no conflicting slots."""
    try:
        lines = _hop_claim_lines(hop_answer)
        if not lines:
            return False
        passing = [ln for ln in lines if _is_strict_born_sentence(ln, subject, facet)]
        if not passing:
            return False
        # Conflicting slots: distinct exact dates (date) or places (place).
        # Compare exact date slots for conflicting full dates, not year-only
        # when supported; unsupported formats already rejected strictly above.
        if facet == "date":
            slots = set()
            for ln in passing:
                try:
                    m_full = re.search(
                        r"\b(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\b",
                        ln, re.IGNORECASE,
                    )
                    if m_full is None:
                        m_full = re.search(
                            r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})\b",
                            ln, re.IGNORECASE,
                        )
                    if m_full is not None:
                        slots.add(m_full.group(1).strip().casefold())
                    else:
                        for y in re.findall(r"\b\d{4}\b", ln):
                            slots.add(y)
                except Exception:
                    continue
            if len(slots) != 1:
                if len(slots) == 0:
                    return False
                return False
        else:
            places = set()
            for ln in passing:
                try:
                    m = re.search(r"born\s+in\s+([^\.\!\?]+)", ln, re.IGNORECASE)
                    if m is None:
                        continue
                    frag = m.group(1)
                    no_year = re.sub(r"\b\d{4}\b", " ", frag)
                    toks = re.findall(r"[A-Za-z][\w\-']*", no_year)
                    cands = [t for t in toks if t[:1].isupper() and t.casefold() not in ("in", "the", "a", "an")]
                    if not cands:
                        continue
                    # Canonical place: first capitalized run lowercased.
                    # Use full fragment normalized for conflict check.
                    norm = " ".join(cands).casefold()
                    places.add(norm)
                except Exception:
                    continue
            if len(places) != 1:
                return False
        # All passing sentences must be strict; any non-passing line that still
        # mentions subject+born indicates unreliable/conflicting evidence.
        # To stay conservative, if any line contains subject and born but fails
        # strict gate, abstain (covers modal/negative/hedged leaks).
        try:
            pat = _subject_pattern_for(subject)
            for ln in lines:
                if ln in passing:
                    continue
                low = ln.casefold()
                if "born" not in low:
                    continue
                if pat and re.search(pat, low) is None:
                    continue
                # Non-passing subject+born sentence present -> conflict/unreliable.
                return False
        except Exception:
            pass
        return True
    except Exception:
        return False


def _year_gate_passes(hop_answer, year):
    """Source BODY complete statement must cover exact year."""
    try:
        if not _is_four_digit_year(year):
            return False
        lines = _hop_claim_lines(hop_answer)
        if not lines:
            return False
        found = False
        for ln in lines:
            try:
                if re.search(r"\b%s\b" % re.escape(year), ln) is not None:
                    found = True
                    break
            except Exception:
                continue
        return found
    except Exception:
        return False


def _has_duplicate_urls(sources):
    try:
        if not isinstance(sources, list):
            return False
        urls = []
        for entry in sources:
            if not isinstance(entry, Mapping):
                return False
            try:
                urls.append(entry.get("url"))
            except Exception:
                return False
        return len(urls) != len(set(urls))
    except Exception:
        return False


def _compose_cited_answer(answer_text, sources_list, *, max_results):
    """Closed bounded source+marker composer: dedup actual URLs, remap 1..N.

    Parses whole complete grounded claim lines and suffixes source markers
    only. Validates strict index via ``type is int`` and URL via both length
    and guard checks. Assigns contiguous 1..N by first appearance; every
    direct source is cited. Supports global final ``max_results`` cap.
    Returns ``(answer, sources)`` or ``None`` on any violation.
    """
    try:
        if not isinstance(answer_text, str) or not answer_text:
            return None
        if not isinstance(sources_list, list) or not sources_list:
            return None
        if type(max_results) is not int or not 1 <= max_results <= _CANDIDATE_CAP:
            return None
        old_to_url = {}
        url_to_title = {}
        for entry in sources_list:
            if not isinstance(entry, Mapping):
                return None
            try:
                idx = entry.get("index")
                url = entry.get("url")
                title = entry.get("title", "")
            except Exception:
                return None
            if type(idx) is not int or idx < 1:
                return None
            if not isinstance(url, str) or not url:
                return None
            if len(url) > _vendor_answer.MAX_URL_CHARS:
                return None
            try:
                allowed, _code = _vendor_guard.check_url(url)
            except Exception:
                return None
            if not allowed:
                return None
            if idx in old_to_url:
                if old_to_url[idx] != url:
                    return None
                continue
            old_to_url[idx] = url
            if url not in url_to_title:
                url_to_title[url] = title if isinstance(title, str) else ""
        if not old_to_url:
            return None
        lines = answer_text.split("\n")
        parsed = []
        url_order = []
        url_to_new = {}
        for line in lines:
            if not line.strip():
                continue
            match = _TRAILING_MARKERS_RE.search(line)
            if not match:
                return None
            marker_block = match.group(1)
            claim_text = line[: match.start()].rstrip()
            if not claim_text:
                return None
            stripped_claim = claim_text.strip()
            if not stripped_claim.endswith((".", "!")):
                return None
            # Any literal numeric bracket in verbatim claim BODY is ambiguous
            # with our citations: abstain rather than strip or phantom-map.
            # Only suffix markers generated by synth may be remapped.
            try:
                if _MARKER_FIND_RE.search(claim_text) is not None:
                    return None
            except Exception:
                return None
            try:
                old_indices = [int(n) for n in _MARKER_FIND_RE.findall(marker_block)]
            except Exception:
                return None
            if not old_indices:
                return None
            for old_idx in old_indices:
                if old_idx not in old_to_url:
                    return None
            parsed.append((claim_text, old_indices))
            for old_idx in old_indices:
                url = old_to_url[old_idx]
                if url not in url_to_new:
                    url_to_new[url] = len(url_order) + 1
                    url_order.append(url)
        if not parsed or not url_order:
            return None
        if len(url_order) > max_results:
            kept = set(url_order[:max_results])
            filtered = []
            for claim_text, old_indices in parsed:
                urls = [old_to_url[idx] for idx in old_indices]
                if all(u in kept for u in urls):
                    filtered.append((claim_text, old_indices))
            if not filtered:
                return None
            parsed = filtered
            url_order = []
            url_to_new = {}
            for _, old_indices in parsed:
                for old_idx in old_indices:
                    url = old_to_url[old_idx]
                    if url not in url_to_new:
                        url_to_new[url] = len(url_order) + 1
                        url_order.append(url)
            if not url_order or len(url_order) > max_results:
                return None
        new_lines = []
        for claim_text, old_indices in parsed:
            mapped = [url_to_new[old_to_url[idx]] for idx in old_indices]
            seen = set()
            uniq = []
            for new_idx in mapped:
                if new_idx not in seen:
                    seen.add(new_idx)
                    uniq.append(new_idx)
            if not uniq:
                return None
            suffix = "".join("[%d]" % n for n in uniq)
            new_lines.append("%s %s" % (claim_text, suffix))
        new_answer = "\n".join(new_lines)
        if not new_answer or len(new_answer) > _vendor_answer.MAX_ANSWER_CHARS:
            return None
        new_sources = []
        for new_idx, url in enumerate(url_order, 1):
            title = url_to_title.get(url, "")
            if not isinstance(title, str):
                title = ""
            title = title[: _vendor_answer.MAX_TITLE_CHARS]
            if len(url) > _vendor_answer.MAX_URL_CHARS:
                return None
            try:
                allowed, _code = _vendor_guard.check_url(url)
            except Exception:
                return None
            if not allowed:
                return None
            new_sources.append({"index": new_idx, "title": title, "url": url})
        try:
            cited_all = set()
            for line in new_lines:
                for num in _MARKER_FIND_RE.findall(line):
                    cited_all.add(int(num))
        except Exception:
            return None
        if cited_all != set(range(1, len(new_sources) + 1)):
            return None
        return (new_answer, new_sources)
    except Exception:
        return None


def _research_http_counts(max_searches, _op_budget=None, _is_builtin=False):
    try:
        _max_http = 2 * max_searches if type(max_searches) is int else 8
    except Exception:
        _max_http = 8
    try:
        if _is_builtin is True:
            _used = getattr(_op_budget, "used", 0) if _op_budget is not None else 0
            if type(_used) is not int or _used < 0:
                _used = 0
            if _used > _max_http:
                _used = _max_http
            return _used, _max_http
        return None, _max_http
    except Exception:
        return None, _max_http


def _build_failure_hops(*, completed=0, failed_code=None, hop_urls=None, max_hops=2):
    try:
        out = []
        n = completed if type(completed) is int and 0 <= completed <= 8 else 0
        for i in range(1, min(n, 8) + 1):
            _url = None
            try:
                if isinstance(hop_urls, list) and i - 1 < len(hop_urls):
                    _url = hop_urls[i - 1]
            except Exception:
                _url = None
            entry = {
                "id": "s%d" % i,
                "index": i,
                "depth": i,
                "status": "completed",
                "code": "COMPLETED",
            }
            if isinstance(_url, str) and _url:
                try:
                    _allowed, _c = _vendor_guard.check_url(_url)
                except Exception:
                    _allowed = False
                if _allowed and len(_url) <= _vendor_answer.MAX_URL_CHARS:
                    entry["url"] = _url
            out.append(entry)
            if len(out) >= 8:
                break
        if isinstance(failed_code, str) and failed_code:
            try:
                _fc = _vendor_contract.public_error_code({"code": failed_code})
            except Exception:
                _fc = failed_code
            fid = n + 1
            if 1 <= fid <= 8:
                out.append({
                    "id": "s%d" % fid,
                    "index": fid,
                    "depth": fid,
                    "status": "failed",
                    "code": _fc,
                })
                if len(out) > 8:
                    del out[8:]
        return out[:8]
    except Exception:
        return []


def _build_actual_hops(plan_steps, hops_out, fail_index, fail_code):
    """Actual trace from real plan steps + real hops_out on EACH attempt.

    StepID/index<=8 and depth EXACT declared DAG depth, deps validated real
    IDs. Statuses/codes/safe URLs only on failure (no body text). Never
    derive full hop URL provenance from the intermediate-summary cap5.
    """
    try:
        if not isinstance(plan_steps, list) or not plan_steps:
            return None
        if type(fail_index) is not int or not 1 <= fail_index <= 8:
            return None
        if len(plan_steps) < fail_index or len(plan_steps) > 8:
            return None
        try:
            _fc = _vendor_contract.public_error_code({"code": fail_code}) if isinstance(fail_code, str) else "INSUFFICIENT_EVIDENCE"
        except Exception:
            _fc = "INSUFFICIENT_EVIDENCE"
        if _fc not in ("INSUFFICIENT_EVIDENCE", "MISSING_CONFIG", "URL_BLOCKED",
                       "REDIRECT_BLOCKED", "HTTP_ERROR", "RATE_LIMITED",
                       "PROVIDER_BLOCKED", "DNS_ERROR", "UPSTREAM_TIMEOUT",
                       "CONNECTION_ERROR"):
            _fc = "INSUFFICIENT_EVIDENCE"
        seen_ids = set()
        for _s in plan_steps:
            try:
                if isinstance(_s, Mapping) and isinstance(_s.get("id"), str):
                    seen_ids.add(_s.get("id"))
            except Exception:
                continue
        out = []
        for i in range(1, fail_index + 1):
            try:
                step = plan_steps[i - 1]
            except Exception:
                return None
            if not isinstance(step, Mapping):
                return None
            try:
                sid = step.get("id")
                sdepth = step.get("depth")
                sdeps = step.get("depends_on")
            except Exception:
                return None
            if sid != "s%d" % i:
                return None
            if type(i) is not int or not 1 <= i <= 8:
                return None
            if type(sdepth) is not int or not 1 <= sdepth <= 8:
                return None
            if not isinstance(sdeps, list):
                return None
            for dep in sdeps:
                if not isinstance(dep, str) or dep not in seen_ids:
                    return None
                try:
                    dep_num = int(dep[1:])
                except Exception:
                    return None
                if not 1 <= dep_num < i:
                    return None
            if i < fail_index:
                entry = {"id": sid, "index": i, "depth": sdepth, "status": "completed", "code": "COMPLETED", "depends_on": list(sdeps)}
                # Actual safe URL of this successful hop from hops_out, not
                # from the capped intermediate summary.
                try:
                    hop = hops_out[i - 1] if isinstance(hops_out, list) and i - 1 < len(hops_out) else None
                    _url = None
                    if isinstance(hop, Mapping):
                        srcs = hop.get("sources", [])
                        if isinstance(srcs, list):
                            for _e in srcs:
                                if not isinstance(_e, Mapping):
                                    continue
                                try:
                                    _u = _e.get("url")
                                except Exception:
                                    continue
                                if not isinstance(_u, str) or not _u:
                                    continue
                                if len(_u) > _vendor_answer.MAX_URL_CHARS:
                                    continue
                                try:
                                    _al, _cc = _vendor_guard.check_url(_u)
                                except Exception:
                                    continue
                                if not _al:
                                    continue
                                _url = _u
                                break
                    if isinstance(_url, str) and _url:
                        entry["url"] = _url
                except Exception:
                    pass
            else:
                entry = {"id": sid, "index": i, "depth": sdepth, "status": "failed", "code": _fc, "depends_on": list(sdeps)}
            out.append(entry)
            if len(out) > 8:
                return None
        return out[:8]
    except Exception:
        return None


def _budget_exhausted_result(*, max_hops, max_searches, hops_planned=2,
                             _op_budget=None, _is_builtin=False):
    try:
        if type(max_hops) is not int or not 1 <= max_hops <= 4:
            max_hops = 2
        if type(max_searches) is not int or not 1 <= max_searches <= 8:
            max_searches = 4
        if type(hops_planned) is not int or not 0 <= hops_planned <= 8:
            hops_planned = 2
    except Exception:
        max_hops, max_searches, hops_planned = 2, 4, 2
    try:
        _planned = hops_planned
        _executed = 0
        _calls = 0
    except Exception:
        _planned, _executed, _calls = hops_planned, 0, 0
    try:
        _http, _max_http = _research_http_counts(max_searches, _op_budget, _is_builtin)
    except Exception:
        _http, _max_http = None, 2 * max_searches
    try:
        _total = 5 * max_searches if type(max_searches) is int else 40
    except Exception:
        _total = 40
    _research = {
        "status": "budget_exhausted",
        "reason": "budget_exhausted",
        "max_hops": max_hops,
        "max_searches": max_searches,
        "hops_planned": _planned,
        "hops_completed": 0,
        "planned": _planned,
        "executed": 0,
        "search_calls": 0,
        "max_http_requests": _max_http,
        "max_candidates_per_call": 5,
        "candidates_per_call": 5,
        "candidate_limit": 5,
        "max_candidates_total": _total,
        "candidates_total": _total,
        "total_result_limit": _total,
        "candidates_considered": 0,
    }
    if _http is None:
        _research["http_requests"] = None
    else:
        _research["http_requests"] = _http
    return {
        "ok": False,
        "error": {"code": "INSUFFICIENT_EVIDENCE"},
        "metadata": {
            "research": _research,
        },
    }


def _research_failure_result(*, status, max_hops, max_searches, hops_planned,
                             hops_completed, search_calls, code="INSUFFICIENT_EVIDENCE",
                             intermediate=None, kind=None, reason=None,
                             year=None, answerable=None, _op_budget=None,
                             _is_builtin=False, http_requests=None,
                             max_http_requests=None, candidates_considered=None,
                             hops=None, hop_urls=None):
    try:
        if status not in _KNOWN_RESEARCH_STATUS:
            status = "abstained"
        if type(max_hops) is not int or not 1 <= max_hops <= 4:
            max_hops = 2
        if type(max_searches) is not int or not 1 <= max_searches <= 8:
            max_searches = 4
        if type(hops_planned) is not int or not 0 <= hops_planned <= 8:
            hops_planned = 0
        if type(hops_completed) is not int or not 0 <= hops_completed <= 8:
            hops_completed = 0
        if type(search_calls) is not int or not 0 <= search_calls <= 8:
            search_calls = 0
        try:
            _code = _vendor_contract.public_error_code({"code": code})
        except Exception:
            _code = "INSUFFICIENT_EVIDENCE"
        if _code not in ("INSUFFICIENT_EVIDENCE", "MISSING_CONFIG", "URL_BLOCKED",
                         "REDIRECT_BLOCKED", "HTTP_ERROR", "RATE_LIMITED",
                         "PROVIDER_BLOCKED", "DNS_ERROR", "UPSTREAM_TIMEOUT",
                         "CONNECTION_ERROR"):
            _code = "INSUFFICIENT_EVIDENCE"
        if reason is None:
            reason = status if status in _KNOWN_RESEARCH_REASON else status
        else:
            if not isinstance(reason, str) or reason not in _KNOWN_RESEARCH_REASON:
                reason = status if status in _KNOWN_RESEARCH_REASON else status
        research = {
            "status": status,
            "reason": reason,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "hops_planned": hops_planned,
            "hops_completed": hops_completed,
            "planned": hops_planned,
            "executed": hops_completed,
            "search_calls": search_calls,
        }
        # Bounded physical + candidate accounting: constructed, never upstream.
        try:
            _mhttp = max_http_requests
            if _mhttp is None:
                _mhttp = 2 * max_searches
            if type(_mhttp) is not int or _mhttp != 2 * max_searches:
                _mhttp = 2 * max_searches
        except Exception:
            _mhttp = 2 * max_searches
        research["max_http_requests"] = _mhttp
        try:
            _hreq = http_requests
            if _hreq is None and _op_budget is not None and _is_builtin is True:
                _u = getattr(_op_budget, "used", 0)
                _hreq = _u if type(_u) is int else 0
            if _hreq is not None and _is_builtin is not True:
                # Arbitrary custom marked backend: physical unknown.
                if http_requests is None:
                    _hreq = None
            if _hreq is not None:
                if type(_hreq) is not int or not 0 <= _hreq <= _mhttp:
                    _hreq = None if _is_builtin is not True else max(0, min(_mhttp, int(_hreq))) if isinstance(_hreq, int) else None
        except Exception:
            _hreq = None
        research["http_requests"] = _hreq
        try:
            _total = 5 * max_searches
        except Exception:
            _total = 40
        research["max_candidates_per_call"] = 5
        research["candidates_per_call"] = 5
        research["candidate_limit"] = 5
        research["max_candidates_total"] = _total
        research["candidates_total"] = _total
        research["total_result_limit"] = _total
        try:
            _cc = candidates_considered
            if _cc is None:
                _cc = 0
            if type(_cc) is not int or not 0 <= _cc <= 40:
                _cc = 0
        except Exception:
            _cc = 0
        research["candidates_considered"] = _cc
        if kind in ("comparison", "intersection", "facets"):
            research["kind"] = kind
        # Closed controlled extras: year exactly four digits, answerable bool.
        if year is not None:
            if _is_four_digit_year(year):
                research["year"] = year
        if answerable is not None:
            if type(answerable) is bool:
                research["answerable"] = answerable
        if isinstance(intermediate, list) and len(intermediate) <= 5:
            clean = []
            for item in intermediate:
                if not isinstance(item, Mapping):
                    continue
                try:
                    url = item.get("url")
                    title = item.get("title", "")
                    hop = item.get("hop", 1)
                except Exception:
                    continue
                if not isinstance(url, str) or not url:
                    continue
                if len(url) > _vendor_answer.MAX_URL_CHARS:
                    continue
                try:
                    allowed, _c = _vendor_guard.check_url(url)
                except Exception:
                    continue
                if not allowed:
                    continue
                if not isinstance(title, str):
                    title = ""
                title = title[:_vendor_answer.MAX_TITLE_CHARS]
                if type(hop) is not int or not 1 <= hop <= 8:
                    continue
                clean.append({"url": url, "title": title, "hop": hop})
                if len(clean) >= 5:
                    break
            research["intermediate_evidence"] = clean
        else:
            research["intermediate_evidence"] = []
        # Bounded failure hops: IDs/index/depth/depends_on/status/code/safe
        # URLs only (no body text). Unsupported/pre-budget abort with 0
        # search calls has EMPTY actual execution hops, no phantom failed s1.
        try:
            _fhops = hops
            if _fhops is None:
                if hops_completed == 0 and search_calls == 0:
                    _fhops = []
                else:
                    _urls = None
                    try:
                        if isinstance(hop_urls, list):
                            _urls = list(hop_urls)
                        elif isinstance(intermediate, list):
                            _urls = [i.get("url") for i in intermediate if isinstance(i, Mapping)]
                    except Exception:
                        _urls = None
                    _fhops = _build_failure_hops(
                        completed=hops_completed, failed_code=_code,
                        hop_urls=_urls, max_hops=max_hops,
                    )
            if not isinstance(_fhops, list) or len(_fhops) > 8:
                if hops_completed == 0 and search_calls == 0:
                    _fhops = []
                else:
                    _fhops = _build_failure_hops(
                        completed=hops_completed, failed_code=_code,
                        hop_urls=None, max_hops=max_hops,
                    )
            _clean_hops = []
            for _h in _fhops[:8]:
                if not isinstance(_h, Mapping):
                    continue
                try:
                    _hid = _h.get("id")
                    _hidx = _h.get("index")
                    _hdep = _h.get("depth")
                    _hst = _h.get("status")
                    _hcode = _h.get("code")
                    _hurl = _h.get("url", None)
                    _hdeps = _h.get("depends_on", None)
                except Exception:
                    continue
                if not isinstance(_hid, str) or not _hid:
                    continue
                if type(_hidx) is not int or not 1 <= _hidx <= 8:
                    continue
                if type(_hdep) is not int or not 1 <= _hdep <= 8:
                    continue
                if not isinstance(_hst, str) or _hst not in ("completed", "failed"):
                    continue
                try:
                    _pc = _vendor_contract.public_error_code({"code": _hcode}) if isinstance(_hcode, str) else None
                except Exception:
                    _pc = None
                if _hst == "failed":
                    if _pc is None and _hcode not in ("COMPLETED",):
                        continue
                else:
                    if _hcode != "COMPLETED":
                        continue
                _entry = {"id": _hid, "index": _hidx, "depth": _hdep, "status": _hst, "code": _hcode}
                if _hdeps is not None:
                    if not isinstance(_hdeps, list):
                        continue
                    _valid_deps = True
                    for _d in _hdeps:
                        if not isinstance(_d, str) or not _d:
                            _valid_deps = False
                            break
                        try:
                            _dn = int(_d[1:]) if _d.startswith("s") else -1
                        except Exception:
                            _valid_deps = False
                            break
                        if not 1 <= _dn < _hidx or _dn > 8:
                            _valid_deps = False
                            break
                    if not _valid_deps:
                        continue
                    _entry["depends_on"] = list(_hdeps)
                if _hurl is not None:
                    if not isinstance(_hurl, str) or not _hurl:
                        continue
                    if len(_hurl) > _vendor_answer.MAX_URL_CHARS:
                        continue
                    try:
                        _al, _cc2 = _vendor_guard.check_url(_hurl)
                    except Exception:
                        continue
                    if not _al:
                        continue
                    _entry["url"] = _hurl
                _clean_hops.append(_entry)
                if len(_clean_hops) >= 8:
                    break
            _fhops_out = _clean_hops
        except Exception:
            _fhops_out = []
    except Exception:
        return _failure("URL_BLOCKED")
    _out = {
        "ok": False,
        "error": {"code": _code},
        "metadata": {"research": research},
    }
    try:
        if isinstance(_fhops_out, list) and _fhops_out:
            _out["hops"] = list(_fhops_out)
            _out["metadata"]["hops"] = list(_fhops_out)
    except Exception:
        pass
    return _out


def _unsupported_research_result(*, max_hops, max_searches, hops_planned=0,
                                 reason=None, year=None, answerable=None):
    if isinstance(reason, str) and reason in _KNOWN_RESEARCH_REASON:
        _r = reason
    else:
        _r = None
    # Preserve explicit unsupported-computation reasons; default stays generic.
    if _r in (_TEMPORAL_COMPARE_REASON, _ARITHMETIC_REASON):
        return _research_failure_result(
            status="unsupported",
            max_hops=max_hops,
            max_searches=max_searches,
            hops_planned=hops_planned,
            hops_completed=0,
            search_calls=0,
            code="INSUFFICIENT_EVIDENCE",
            intermediate=[],
            reason=_r,
            year=year,
            answerable=answerable,
        )
    return _research_failure_result(
        status="unsupported",
        max_hops=max_hops,
        max_searches=max_searches,
        hops_planned=hops_planned,
        hops_completed=0,
        search_calls=0,
        code="INSUFFICIENT_EVIDENCE",
        intermediate=[],
    )


def _build_intermediate_evidence(hop1_stamped, final_urls):
    try:
        out = []
        seen = set()
        try:
            final_set = set(final_urls) if isinstance(final_urls, list) else set()
        except Exception:
            final_set = set()
        if not isinstance(hop1_stamped, list):
            return []
        for entry in hop1_stamped:
            if len(out) >= 5:
                break
            if not isinstance(entry, Mapping):
                continue
            try:
                url = entry.get("url")
                title = entry.get("title", "")
            except Exception:
                continue
            if not isinstance(url, str) or not url:
                continue
            if url in final_set or url in seen:
                continue
            if len(url) > _vendor_answer.MAX_URL_CHARS:
                continue
            try:
                allowed, _code = _vendor_guard.check_url(url)
            except Exception:
                continue
            if not allowed:
                continue
            if not isinstance(title, str):
                title = ""
            title = title[: _vendor_answer.MAX_TITLE_CHARS]
            out.append({"url": url, "title": title, "hop": 1})
            seen.add(url)
        return out
    except Exception:
        return []


def _build_research_metadata(*, status, max_hops, max_searches, hops_planned,
                             hops_completed, search_calls=None, kind=None,
                             reason=None, year=None, answerable=None,
                             _op_budget=None, _is_builtin=False,
                             candidates_considered=None, http_requests=None,
                             max_http_requests=None):
    try:
        if status not in _KNOWN_RESEARCH_STATUS:
            return None
        if type(max_hops) is not int or not 1 <= max_hops <= 4:
            return None
        if type(max_searches) is not int or not 1 <= max_searches <= 8:
            return None
        if type(hops_planned) is not int or not 0 <= hops_planned <= 8:
            return None
        if type(hops_completed) is not int or not 0 <= hops_completed <= 8:
            return None
        if search_calls is None:
            search_calls = hops_completed
        if type(search_calls) is not int or not 0 <= search_calls <= 8:
            return None
        if reason is None:
            reason = status if status in _KNOWN_RESEARCH_REASON else status
        else:
            if not isinstance(reason, str) or reason not in _KNOWN_RESEARCH_REASON:
                return None
        inner = {
            "status": status,
            "reason": reason,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "hops_planned": hops_planned,
            "hops_completed": hops_completed,
            "planned": hops_planned,
            "executed": hops_completed,
            "search_calls": search_calls,
        }
        try:
            _mhttp2 = max_http_requests
            if _mhttp2 is None:
                _mhttp2 = 2 * max_searches
            if type(_mhttp2) is not int or _mhttp2 != 2 * max_searches:
                _mhttp2 = 2 * max_searches
        except Exception:
            _mhttp2 = 2 * max_searches
        inner["max_http_requests"] = _mhttp2
        try:
            _h2 = http_requests
            if _h2 is None and _op_budget is not None and _is_builtin is True:
                _u2 = getattr(_op_budget, "used", 0)
                _h2 = _u2 if type(_u2) is int else 0
            if _h2 is not None and _is_builtin is not True and http_requests is None:
                _h2 = None
            if _h2 is not None and (type(_h2) is not int or not 0 <= _h2 <= _mhttp2):
                _h2 = None if _is_builtin is not True else None
                return None
        except Exception:
            _h2 = None
        inner["http_requests"] = _h2
        try:
            _tot2 = 5 * max_searches
        except Exception:
            _tot2 = 40
        inner["max_candidates_per_call"] = 5
        inner["candidates_per_call"] = 5
        inner["candidate_limit"] = 5
        inner["max_candidates_total"] = _tot2
        inner["candidates_total"] = _tot2
        inner["total_result_limit"] = _tot2
        try:
            _cc2 = candidates_considered
            if _cc2 is None:
                _cc2 = 0
            if type(_cc2) is not int or not 0 <= _cc2 <= 40:
                return None
        except Exception:
            return None
        inner["candidates_considered"] = _cc2
        if kind in ("comparison", "intersection", "facets"):
            inner["kind"] = kind
        if year is not None:
            if not _is_four_digit_year(year):
                return None
            inner["year"] = year
        if answerable is not None:
            if type(answerable) is not bool:
                return None
            inner["answerable"] = answerable
        return {"research": inner}
    except Exception:
        return None


def _build_chain_intermediate(stamped_hops, final_urls):
    try:
        out = []
        seen = set()
        try:
            final_set = set(final_urls) if isinstance(final_urls, list) else set()
        except Exception:
            final_set = set()
        if not isinstance(stamped_hops, list):
            return []
        for hop_sources in stamped_hops:
            if len(out) >= 5:
                break
            if not isinstance(hop_sources, list):
                continue
            for entry in hop_sources:
                if len(out) >= 5:
                    break
                if not isinstance(entry, Mapping):
                    continue
                try:
                    url = entry.get("url")
                    title = entry.get("title", "")
                    hop = entry.get("hop", 1)
                except Exception:
                    continue
                if not isinstance(url, str) or not url:
                    continue
                if url in final_set or url in seen:
                    continue
                if len(url) > _vendor_answer.MAX_URL_CHARS:
                    continue
                try:
                    allowed, _code = _vendor_guard.check_url(url)
                except Exception:
                    continue
                if not allowed:
                    continue
                if not isinstance(title, str):
                    title = ""
                title = title[:_vendor_answer.MAX_TITLE_CHARS]
                if type(hop) is not int or not 1 <= hop <= 8:
                    continue
                out.append({"url": url, "title": title, "hop": hop})
                seen.add(url)
        return out
    except Exception:
        return []


def _research_step_binding_sentences(hop_answer):
    try:
        if not isinstance(hop_answer, str) or not hop_answer:
            return []
        lines = []
        for line in hop_answer.split("\n"):
            if not line.strip():
                continue
            cleaned = re.sub(r"(?:\s*\[\d+\])+\s*$", "", line).strip()
            if cleaned:
                lines.append(cleaned)
        return lines
    except Exception:
        return []


def _research_unique_binding(sentences, kind, subject_phrase, base=None):
    try:
        canon_to_raw = {}
        order = []
        for sentence in sentences:
            try:
                if not _vendor_answer._is_relation_evidence(
                    sentence, kind, subject_phrase, base
                ):
                    continue
            except Exception:
                continue
            try:
                raw = _vendor_answer._first_actor_match(
                    sentence,
                    kind,
                    _vendor_answer._subject_pattern(subject_phrase),
                    base,
                )
            except Exception:
                raw = None
            if not isinstance(raw, str) or not raw.strip():
                continue
            raw = raw.strip()
            try:
                if "{" in raw or "}" in raw:
                    continue
            except Exception:
                continue
            # Resolved binding must not carry URL/credential/control; reject
            # scalar ambiguity (joint conjunction) without weakening grounding.
            try:
                if any(ord(c) < 32 for c in raw):
                    continue
                if "://" in raw:
                    continue
                if "@" in raw and ("://" in raw or "user:" in raw.casefold()):
                    continue
                if re.search(r"\b(and|or)\b", raw, re.IGNORECASE) is not None:
                    continue
            except Exception:
                continue
            try:
                if not _vendor_answer._is_resolved_slot(raw):
                    continue
            except Exception:
                continue
            try:
                canon = _vendor_answer._canonical_slot(raw)
            except Exception:
                continue
            if not canon:
                continue
            if len(raw) > 512 or len(canon) > 512:
                continue
            if canon not in canon_to_raw:
                canon_to_raw[canon] = raw
                order.append(canon)
        if len(order) != 1:
            return None, []
        canon = order[0]
        return canon_to_raw[canon], [canon]
    except Exception:
        return None, []


def _research_terminal_subject(grounding, kind, base):
    try:
        if kind == "orbit":
            return _vendor_answer._parse_orbit_query(grounding) or ""
        if kind == "capital":
            return _vendor_answer._parse_capital_query(grounding) or ""
        if kind == "discovery":
            return _vendor_answer._discovery_subject_phrase(grounding) or ""
        if kind == "generic":
            parsed = _vendor_answer._parse_generic_who_query(grounding)
            return parsed[1] if parsed is not None else ""
        return ""
    except Exception:
        return ""


def _compose_multi_terminal(terminal_hops, *, max_results):
    """Combine independent terminal claims with actual URL dedup.

    Returns (answer, sources) or "CAP_EXCEEDED" when distinct URLs exceed
    the global cap (caller must abstain/partial, never silently drop a
    facet) or None on any violation.
    """
    try:
        if not isinstance(terminal_hops, list) or not terminal_hops:
            return None
        if type(max_results) is not int or not 1 <= max_results <= _CANDIDATE_CAP:
            return None
        url_order = []
        url_to_title = {}
        combined_lines = []
        for hop in terminal_hops:
            try:
                hop_answer = hop.get("answer", "")
                hop_sources = hop.get("sources", [])
            except Exception:
                return None
            if not isinstance(hop_answer, str) or not hop_answer:
                return None
            if not isinstance(hop_sources, list) or not hop_sources:
                return None
            local_to_url = {}
            for entry in hop_sources:
                if not isinstance(entry, Mapping):
                    return None
                try:
                    idx = entry.get("index")
                    url = entry.get("url")
                    title = entry.get("title", "")
                except Exception:
                    return None
                if type(idx) is not int or idx < 1:
                    return None
                if not isinstance(url, str) or not url:
                    return None
                if url not in url_to_title:
                    url_to_title[url] = title if isinstance(title, str) else ""
                # Last wins for duplicate local idx must be consistent.
                if idx in local_to_url and local_to_url[idx] != url:
                    return None
                local_to_url[idx] = url
            for line in hop_answer.split("\n"):
                if not line.strip():
                    continue
                match = _TRAILING_MARKERS_RE.search(line)
                if not match:
                    return None
                marker_block = match.group(1)
                claim_text = line[: match.start()].rstrip()
                if not claim_text or not claim_text.strip().endswith((".", "!")):
                    return None
                try:
                    local_indices = [int(n) for n in _MARKER_FIND_RE.findall(marker_block)]
                except Exception:
                    return None
                if not local_indices:
                    return None
                global_indices = []
                for local_idx in local_indices:
                    if local_idx not in local_to_url:
                        return None
                    url = local_to_url[local_idx]
                    if url not in url_order:
                        url_order.append(url)
                    global_indices.append(url_order.index(url) + 1)
                combined_lines.append((claim_text, global_indices))
        if not combined_lines or not url_order:
            return None
        if len(url_order) > max_results:
            return "CAP_EXCEEDED"
        # Rebuild with contiguous 1..N by first appearance (already contiguous).
        new_lines = []
        for claim_text, global_indices in combined_lines:
            seen = set()
            uniq = []
            for num in global_indices:
                if num not in seen:
                    seen.add(num)
                    uniq.append(num)
            if not uniq:
                return None
            suffix = "".join("[%d]" % n for n in uniq)
            new_lines.append("%s %s" % (claim_text, suffix))
        new_answer = "\n".join(new_lines)
        if not new_answer or len(new_answer) > _vendor_answer.MAX_ANSWER_CHARS:
            return None
        new_sources = []
        for new_idx, url in enumerate(url_order, 1):
            title = url_to_title.get(url, "")
            if not isinstance(title, str):
                title = ""
            new_sources.append({
                "index": new_idx,
                "title": title[: _vendor_answer.MAX_TITLE_CHARS],
                "url": url,
            })
        # Validate via closed composer (dedup + citation completeness).
        # Build old-style inputs referencing url_order positions.
        old_sources = [
            {"index": i + 1, "title": url_to_title.get(u, ""), "url": u}
            for i, u in enumerate(url_order)
        ]
        checked = _compose_cited_answer(new_answer, old_sources, max_results=max_results)
        if checked is None:
            return None
        return checked
    except Exception:
        return None


def _execute_research_plan(plan, *, max_results, max_hops, max_searches,
                           _search_call, _op_budget, _budget_aware,
                           _is_builtin=False):
    try:
        try:
            validate = getattr(_vendor_answer, "validate_research_plan", None)
        except Exception:
            validate = None
        if not callable(validate):
            return _unsupported_research_result(
                max_hops=max_hops, max_searches=max_searches, hops_planned=0
            )
        try:
            valid = validate(plan)
        except Exception:
            valid = False
        if valid is not True:
            try:
                steps_len = len(plan.get("steps", [])) if isinstance(plan, dict) else 0
            except Exception:
                steps_len = 0
            if type(steps_len) is not int or not 0 <= steps_len <= 8:
                steps_len = 0
            return _unsupported_research_result(
                max_hops=max_hops, max_searches=max_searches,
                hops_planned=steps_len,
            )
        steps = plan.get("steps")
        hops_planned = len(steps)
        try:
            chain_kind = plan.get("chain_kind", "compositional")
        except Exception:
            chain_kind = "compositional"
        if chain_kind not in ("compositional", "facets", "comparison", "intersection"):
            chain_kind = "compositional"
        try:
            max_depth = max(
                s.get("depth") for s in steps
                if isinstance(s, Mapping) and type(s.get("depth")) is int
            )
        except Exception:
            return _failure("URL_BLOCKED")
        # max_hops bounds DEPTH, not number of independent facets.
        if max_depth > max_hops or hops_planned > max_searches:
            return _budget_exhausted_result(
                max_hops=max_hops, max_searches=max_searches,
                hops_planned=hops_planned,
            )
        # Physical preempt: need at most 2*hops_planned HTTP within 2*max_searches.
        try:
            if _budget_aware:
                used = getattr(_op_budget, "used", 0)
                cap = getattr(_op_budget, "max_http", 2 * max_searches)
                if type(used) is int and type(cap) is int:
                    if used + 2 * hops_planned > cap:
                        return _budget_exhausted_result(
                            max_hops=max_hops, max_searches=max_searches,
                            hops_planned=hops_planned,
                        )
        except Exception:
            pass
        bindings = {}
        hops_out = []
        stamped_nonterminal = []
        stamped_completed = []
        search_calls = 0
        _seen_queries = set()
        _candidates_considered = 0

        def _http_now():
            try:
                if _is_builtin is True and _op_budget is not None:
                    _u = getattr(_op_budget, "used", 0)
                    return _u if type(_u) is int else 0
                return None
            except Exception:
                return None

        def _actual_hops_for(_fail_idx, _fail_code):
            try:
                return _build_actual_hops(steps, hops_out, _fail_idx, _fail_code)
            except Exception:
                return None

        def _actual_completed_hops():
            try:
                out = []
                for _i, _st in enumerate(steps, 1):
                    if not isinstance(_st, Mapping):
                        return None
                    try:
                        _sid = _st.get("id")
                        _sdep = _st.get("depth")
                        _sdeps = _st.get("depends_on")
                    except Exception:
                        return None
                    if _sid != "s%d" % _i:
                        return None
                    if type(_sdep) is not int or not 1 <= _sdep <= 8:
                        return None
                    if not isinstance(_sdeps, list):
                        return None
                    entry = {"id": _sid, "index": _i, "depth": _sdep, "status": "completed", "code": "COMPLETED", "depends_on": list(_sdeps)}
                    try:
                        _hop = hops_out[_i - 1] if isinstance(hops_out, list) and _i - 1 < len(hops_out) else None
                        if isinstance(_hop, Mapping):
                            _srcs = _hop.get("sources", [])
                            if isinstance(_srcs, list):
                                for _e in _srcs:
                                    if not isinstance(_e, Mapping):
                                        continue
                                    try:
                                        _u = _e.get("url")
                                    except Exception:
                                        continue
                                    if not isinstance(_u, str) or not _u:
                                        continue
                                    if len(_u) > _vendor_answer.MAX_URL_CHARS:
                                        continue
                                    try:
                                        _al, _cc = _vendor_guard.check_url(_u)
                                    except Exception:
                                        continue
                                    if not _al:
                                        continue
                                    entry["url"] = _u
                                    break
                    except Exception:
                        pass
                    out.append(entry)
                return out[:8]
            except Exception:
                return None

        _global_failure_result = _research_failure_result
        _outer_op_budget = _op_budget
        _outer_is_builtin = _is_builtin

        def _failure_with_actual(*, status, max_hops, max_searches, hops_planned,
                                 hops_completed, search_calls, code="INSUFFICIENT_EVIDENCE",
                                 intermediate=None, kind=None, reason=None,
                                 year=None, answerable=None, _op_budget=None,
                                 _is_builtin=False, http_requests=None,
                                 max_http_requests=None, candidates_considered=None,
                                 hops=None, hop_urls=None):
            try:
                if candidates_considered is None:
                    try:
                        candidates_considered = _candidates_considered
                    except Exception:
                        candidates_considered = 0
                if _op_budget is None:
                    try:
                        _op_budget = _outer_op_budget
                    except Exception:
                        pass
                if _is_builtin is False:
                    try:
                        if _outer_is_builtin is True:
                            _is_builtin = True
                    except Exception:
                        pass
                if http_requests is None:
                    try:
                        http_requests = _http_now()
                    except Exception:
                        pass
                if hops is None:
                    try:
                        if hops_completed == 0 and search_calls == 0:
                            hops = []
                        elif hops_completed < hops_planned:
                            try:
                                _fi = hops_completed + 1
                            except Exception:
                                _fi = 1
                            _ah = _build_actual_hops(steps, hops_out, _fi, code)
                            if isinstance(_ah, list):
                                hops = _ah
                        else:
                            _ac = _actual_completed_hops()
                            if isinstance(_ac, list):
                                hops = _ac
                    except Exception:
                        pass
            except Exception:
                pass
            return _global_failure_result(
                status=status, max_hops=max_hops, max_searches=max_searches,
                hops_planned=hops_planned, hops_completed=hops_completed,
                search_calls=search_calls, code=code, intermediate=intermediate,
                kind=kind, reason=reason, year=year, answerable=answerable,
                _op_budget=_op_budget, _is_builtin=_is_builtin,
                http_requests=http_requests, max_http_requests=max_http_requests,
                candidates_considered=candidates_considered, hops=hops,
                hop_urls=hop_urls,
            )

        def _fail_partial(_idx, _completed, _calls, _code, _inter, _kind=None, _reason=None):
            try:
                _st = "partial" if _idx > 1 else "abstained"
            except Exception:
                _st = "abstained"
            try:
                _ah = _actual_hops_for(_idx, _code)
            except Exception:
                _ah = None
            return _research_failure_result(
                status=_st,
                max_hops=max_hops, max_searches=max_searches,
                hops_planned=hops_planned,
                hops_completed=_completed,
                search_calls=_calls,
                code=_code,
                intermediate=_inter,
                kind=_kind,
                reason=_reason,
                _op_budget=_op_budget,
                _is_builtin=_is_builtin,
                http_requests=_http_now(),
                candidates_considered=_candidates_considered,
                hops=_ah,
            )
        for index, step in enumerate(steps, 1):
            try:
                step_id = step.get("id")
                template = step.get("query_template")
                relation = step.get("relation", {})
                kind = relation.get("kind")
                base = relation.get("base")
                facet = relation.get("facet")
                grounding_tpl = step.get("grounding_template", template)
                retrieval_tpl = step.get("retrieval_template", None)
                tcond = step.get("temporal_condition", None)
            except Exception:
                return _failure("URL_BLOCKED")
            if not isinstance(template, str) or not template:
                return _failure("URL_BLOCKED")
            if not isinstance(grounding_tpl, str) or not grounding_tpl:
                return _failure("URL_BLOCKED")
            # Closed temporal extras.
            year = None
            if isinstance(tcond, dict):
                try:
                    if set(tcond) != {"year"}:
                        return _failure("URL_BLOCKED")
                    yv = tcond.get("year")
                    if not _is_four_digit_year(yv):
                        return _failure("URL_BLOCKED")
                    year = yv
                except Exception:
                    return _failure("URL_BLOCKED")
            elif tcond is not None:
                return _failure("URL_BLOCKED")
            if retrieval_tpl is not None:
                if not isinstance(retrieval_tpl, str) or not retrieval_tpl:
                    return _failure("URL_BLOCKED")
                if year is None:
                    return _failure("URL_BLOCKED")
            # Resolve placeholders from prior bindings only (both templates).
            grounding = grounding_tpl
            retrieval_q = retrieval_tpl if isinstance(retrieval_tpl, str) else template
            try:
                needed_g = [int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(grounding_tpl)]
                needed_r = [int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(retrieval_q)]
                needed = sorted(set(needed_g + [int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(template)]))
            except Exception:
                return _failure("URL_BLOCKED")
            for dep_num in sorted(set(needed_g + needed_r)):
                dep_id = "s%d" % dep_num
                if dep_id not in bindings:
                    return _failure_with_actual(
                        status="partial" if index > 1 else "abstained",
                        max_hops=max_hops, max_searches=max_searches,
                        hops_planned=hops_planned,
                        hops_completed=index - 1,
                        search_calls=search_calls,
                        intermediate=_build_chain_intermediate(
                            stamped_nonterminal, []
                        ),
                    )
                grounding = grounding.replace("{s%d}" % dep_num, bindings[dep_id])
                retrieval_q = retrieval_q.replace("{s%d}" % dep_num, bindings[dep_id])
            if "{" in grounding or "}" in grounding:
                return _failure("URL_BLOCKED")
            if "{" in retrieval_q or "}" in retrieval_q:
                return _failure("URL_BLOCKED")
            if len(grounding) < 1 or len(grounding) > 2000:
                return _failure("URL_BLOCKED")
            if len(retrieval_q) < 1 or len(retrieval_q) > 2000:
                return _failure("URL_BLOCKED")
            # Resolved binding must not carry URL/credential/control.
            try:
                if any(ord(c) < 32 for c in retrieval_q):
                    return _failure("URL_BLOCKED")
                if any(ord(c) < 32 for c in grounding):
                    return _failure("URL_BLOCKED")
                if "://" in retrieval_q or "://" in grounding:
                    return _fail_partial(index, index - 1, search_calls, "URL_BLOCKED", _build_chain_intermediate(stamped_nonterminal, []))
                if "@" in retrieval_q or "@" in grounding:
                    _low_r = retrieval_q.casefold()
                    _low_g = grounding.casefold()
                    if "user:" in _low_r or "user:" in _low_g or "://" in retrieval_q or "://" in grounding:
                        return _fail_partial(index, index - 1, search_calls, "URL_BLOCKED", _build_chain_intermediate(stamped_nonterminal, []))
            except Exception:
                pass
            # Retrieval includes exact year, grounding omits qualifier.
            if year is not None:
                try:
                    if year not in retrieval_q:
                        return _failure("URL_BLOCKED")
                    if year in grounding:
                        return _failure("URL_BLOCKED")
                except Exception:
                    return _failure("URL_BLOCKED")
            # Seen resolved-query set BEFORE retrieval: self-loop stops after 1.
            try:
                if retrieval_q in _seen_queries:
                    return _failure_with_actual(
                        status="partial" if index > 1 else "abstained",
                        max_hops=max_hops, max_searches=max_searches,
                        hops_planned=hops_planned,
                        hops_completed=index - 1,
                        search_calls=search_calls + 1 if type(search_calls) is int else 1,
                        code="INSUFFICIENT_EVIDENCE",
                        intermediate=_build_chain_intermediate(stamped_completed, []),
                        reason="repeated_query",
                        _op_budget=_op_budget,
                        _is_builtin=_is_builtin,
                        http_requests=_http_now(),
                        candidates_considered=_candidates_considered,
                    )
                _seen_queries.add(retrieval_q)
            except Exception:
                pass
            if search_calls + 1 > max_searches:
                return _budget_exhausted_result(
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=hops_planned,
                    _op_budget=_op_budget, _is_builtin=_is_builtin,
                )
            # Attempt counts increment BEFORE invocation, including errors.
            search_calls += 1
            try:
                response = _search_call(retrieval_q)
            except Exception as error:
                try:
                    _code = _vendor_contract.public_error_code(error)
                except Exception:
                    _code = "URL_BLOCKED"
                if _code == "INSUFFICIENT_EVIDENCE":
                    try:
                        if _budget_aware and getattr(
                            _op_budget, "used", 0
                        ) >= getattr(_op_budget, "max_http", 2 * max_searches):
                            return _budget_exhausted_result(
                                max_hops=max_hops, max_searches=max_searches,
                                hops_planned=hops_planned,
                                _op_budget=_op_budget, _is_builtin=_is_builtin,
                            )
                    except Exception:
                        pass
                return _failure_with_actual(
                    status="partial" if index > 1 else "abstained",
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=hops_planned,
                    hops_completed=index - 1,
                    search_calls=search_calls,
                    code=_code,
                    intermediate=_build_chain_intermediate(
                        stamped_nonterminal, []
                    ),
                    _op_budget=_op_budget,
                    _is_builtin=_is_builtin,
                    http_requests=_http_now(),
                    candidates_considered=_candidates_considered,
                )
            try:
                normalized = _vendor_contract.normalize_result(response)
            except Exception:
                return _fail_partial(index, index - 1, search_calls, "URL_BLOCKED", _build_chain_intermediate(stamped_nonterminal, []))
            try:
                backend_failed = (
                    normalized.get("ok") is False
                    or normalized.get("error") is not None
                )
            except Exception:
                return _fail_partial(index, index - 1, search_calls, "URL_BLOCKED", _build_chain_intermediate(stamped_nonterminal, []))
            if backend_failed:
                try:
                    code = _vendor_contract.public_error_code(
                        normalized.get("error")
                    )
                except Exception:
                    code = "URL_BLOCKED"
                if code == "INSUFFICIENT_EVIDENCE":
                    try:
                        if _budget_aware and getattr(
                            _op_budget, "used", 0
                        ) >= getattr(_op_budget, "max_http", 2 * max_searches):
                            return _budget_exhausted_result(
                                max_hops=max_hops, max_searches=max_searches,
                                hops_planned=hops_planned,
                                _op_budget=_op_budget, _is_builtin=_is_builtin,
                            )
                    except Exception:
                        pass
                return _failure_with_actual(
                    status="partial" if index > 1 else "abstained",
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=hops_planned,
                    hops_completed=index - 1,
                    search_calls=search_calls,
                    code=code,
                    intermediate=_build_chain_intermediate(
                        stamped_nonterminal, []
                    ),
                    _op_budget=_op_budget,
                    _is_builtin=_is_builtin,
                    http_requests=_http_now(),
                    candidates_considered=_candidates_considered,
                )
            try:
                results = normalized.get("results")
            except Exception:
                return _fail_partial(index, index - 1, search_calls, "URL_BLOCKED", _build_chain_intermediate(stamped_nonterminal, []))
            if not isinstance(results, list):
                return _fail_partial(index, index - 1, search_calls, "URL_BLOCKED", _build_chain_intermediate(stamped_nonterminal, []))
            try:
                candidates = list(results[:_CANDIDATE_CAP])
            except Exception:
                return _fail_partial(index, index - 1, search_calls, "URL_BLOCKED", _build_chain_intermediate(stamped_nonterminal, []))
            try:
                _candidates_considered = min(40, _candidates_considered + len(candidates))
            except Exception:
                pass
            safe = [item for item in candidates if _safe_candidate(item)]

            def _synth_search(_q, _safe=list(safe)):
                return {"ok": True, "results": list(_safe)}

            try:
                if kind == "generic":
                    raw = _vendor_answer.goat_answer(
                        grounding, search=_synth_search, max_results=max_results
                    )
                else:
                    raw = _vendor_answer.goat_answer(
                        grounding, search=_synth_search, max_results=max_results
                    )
            except Exception as error:
                try:
                    _c = _vendor_contract.public_error_code(error)
                except Exception:
                    _c = "URL_BLOCKED"
                return _failure(_c)
            if not isinstance(raw, Mapping):
                return _failure("URL_BLOCKED")
            try:
                raw_failed = (
                    raw.get("ok") is False or raw.get("error") is not None
                )
            except Exception:
                return _failure("URL_BLOCKED")
            if raw_failed:
                # Intersection: ambiguous/conflicting evidence abstains even
                # after a prior success; only truly missing evidence is partial.
                try:
                    _is_intersection = (chain_kind == "intersection")
                except Exception:
                    _is_intersection = False
                if _is_intersection and len(safe) > 0:
                    return _failure_with_actual(
                        status="abstained",
                        max_hops=max_hops, max_searches=max_searches,
                        hops_planned=hops_planned,
                        hops_completed=index - 1,
                        search_calls=search_calls,
                        intermediate=_build_chain_intermediate(
                            stamped_completed, []
                        ),
                        kind="intersection",
                    )
                return _failure_with_actual(
                    status="partial" if index > 1 else "abstained",
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=hops_planned,
                    hops_completed=index - 1,
                    search_calls=search_calls,
                    intermediate=_build_chain_intermediate(
                        stamped_completed, []
                    ),
                )
            try:
                hop_answer = raw.get("answer", "")
                hop_sources = raw.get("sources", [])
            except Exception:
                return _failure("URL_BLOCKED")
            if not isinstance(hop_answer, str) or not hop_answer:
                return _failure("URL_BLOCKED")
            if not isinstance(hop_sources, list) or not hop_sources:
                return _failure("URL_BLOCKED")
            # Temporal post-constraints on original grounded output (ALL 5 safe
            # candidates already used). Never filter negatives/conflicts beforehand.
            if year is not None:
                try:
                    if not _year_gate_passes(hop_answer, year):
                        return _failure_with_actual(
                            status="partial" if index > 1 else "abstained",
                            max_hops=max_hops, max_searches=max_searches,
                            hops_planned=hops_planned,
                            hops_completed=index - 1,
                            search_calls=search_calls,
                            intermediate=_build_chain_intermediate(
                                stamped_completed, []
                            ),
                        )
                except Exception:
                    return _failure("URL_BLOCKED")
            if kind == "birth":
                try:
                    # Subject-specific whole born sentence gate.
                    subj_name = ""
                    try:
                        low_g = grounding.casefold()
                        if low_g.endswith(" born"):
                            subj_name = grounding[: -len(" born")].strip()
                        else:
                            # Fallback: strip trailing born token.
                            parts = grounding.rsplit(" ", 1)
                            if len(parts) == 2 and parts[1].casefold() == "born":
                                subj_name = parts[0].strip()
                            else:
                                subj_name = grounding.strip()
                    except Exception:
                        subj_name = ""
                    if not subj_name:
                        return _failure("URL_BLOCKED")
                    if facet not in ("place", "date"):
                        return _failure("URL_BLOCKED")
                    if not _born_gate_passes(hop_answer, subj_name, facet):
                        return _failure_with_actual(
                            status="partial" if index > 1 else "abstained",
                            max_hops=max_hops, max_searches=max_searches,
                            hops_planned=hops_planned,
                            hops_completed=index - 1,
                            search_calls=search_calls,
                            intermediate=_build_chain_intermediate(
                                stamped_completed, []
                            ),
                        )
                except Exception:
                    return _failure("URL_BLOCKED")
            try:
                if _has_duplicate_urls(hop_sources):
                    fixed = _compose_cited_answer(
                        hop_answer, hop_sources, max_results=max_results
                    )
                    if fixed is None:
                        return _failure_with_actual(
                            status="partial" if index > 1 else "abstained",
                            max_hops=max_hops, max_searches=max_searches,
                            hops_planned=hops_planned,
                            hops_completed=index - 1,
                            search_calls=search_calls,
                            intermediate=_build_chain_intermediate(
                                stamped_nonterminal, []
                            ),
                        )
                    hop_answer, hop_sources = fixed
            except Exception:
                return _failure("URL_BLOCKED")
            # Stamp hop sources with local indices + hop number.
            try:
                stamped = []
                for entry in hop_sources:
                    if not isinstance(entry, Mapping):
                        return _failure("URL_BLOCKED")
                    data = dict(entry)
                    if type(data.get("index")) is not int:
                        return _failure("URL_BLOCKED")
                    data["hop"] = index
                    stamped.append(data)
            except Exception:
                return _failure("URL_BLOCKED")
            hops_out.append({
                "query": retrieval_q,
                "answer": hop_answer,
                "sources": stamped,
            })
            is_terminal = (step.get("emit") is True)
            # Resolve binding only for non-terminal steps (dependents need it).
            if not is_terminal:
                # Determine subject phrase for this step's relation.
                try:
                    subj = _research_terminal_subject(grounding, kind, base)
                except Exception:
                    subj = ""
                if not subj:
                    stamped_completed.append(stamped)
                    return _failure_with_actual(
                        status="partial" if index > 1 else "abstained",
                        max_hops=max_hops, max_searches=max_searches,
                        hops_planned=hops_planned,
                        hops_completed=index,
                        search_calls=search_calls,
                        intermediate=_build_chain_intermediate(
                            stamped_completed, []
                        ),
                    )
                sentences = _research_step_binding_sentences(hop_answer)
                display, _canons = _research_unique_binding(
                    sentences, kind, subj, base
                )
                if not isinstance(display, str) or not display:
                    # Ambiguous or ungrounded bridge: abstain, never guess.
                    stamped_nonterminal.append(stamped)
                    stamped_completed.append(stamped)
                    return _failure_with_actual(
                        status="partial" if index > 1 else "abstained",
                        max_hops=max_hops, max_searches=max_searches,
                        hops_planned=hops_planned,
                        hops_completed=index,
                        search_calls=search_calls,
                        intermediate=_build_chain_intermediate(
                            stamped_completed, []
                        ),
                    )
                bindings[step_id] = display
                stamped_nonterminal.append(stamped)
                stamped_completed.append(stamped)
            else:
                # Terminal step: no binding needed, but keep for completeness.
                try:
                    bindings[step_id] = ""
                except Exception:
                    pass
                stamped_completed.append(stamped)
        # Only terminal emitting steps contribute final statements.
        try:
            terminal_steps = [s for s in steps if s.get("emit") is True]
        except Exception:
            return _failure("URL_BLOCKED")
        # Explicit unsupported computation: bounded grounded date retrieval for
        # both operands, NO final comparison, sources absent, intermediate URLs.
        try:
            _ans_flag = plan.get("answerable", True)
            _plan_reason = plan.get("reason", "planned")
        except Exception:
            _ans_flag, _plan_reason = True, "planned"
        if _ans_flag is False and _plan_reason == _TEMPORAL_COMPARE_REASON:
            try:
                inter = _build_chain_intermediate(stamped_completed, [])
            except Exception:
                inter = []
            # No date arithmetic, counts, rankings guessed; evidence-only.
            return _failure_with_actual(
                status="unsupported",
                max_hops=max_hops, max_searches=max_searches,
                hops_planned=hops_planned,
                hops_completed=hops_planned,
                search_calls=search_calls,
                intermediate=inter,
                kind="comparison" if chain_kind == "comparison" else None,
                reason=_TEMPORAL_COMPARE_REASON,
                answerable=False,
                _op_budget=_op_budget,
                _is_builtin=_is_builtin,
                http_requests=_http_now(),
                candidates_considered=_candidates_considered,
            )
        if chain_kind == "compositional":
            if len(terminal_steps) != 1 or terminal_steps[0].get("id") != steps[-1].get("id"):
                return _failure("URL_BLOCKED")
            final_hop = hops_out[-1]
            try:
                composed = _compose_cited_answer(
                    final_hop["answer"], final_hop["sources"],
                    max_results=max_results,
                )
            except Exception:
                return _failure("URL_BLOCKED")
            if composed is None:
                return _failure_with_actual(
                    status="partial",
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=hops_planned,
                    hops_completed=hops_planned - 1,
                    search_calls=search_calls,
                    intermediate=_build_chain_intermediate(
                        stamped_nonterminal, []
                    ),
                )
            final_answer, final_sources = composed
            result_kind = None
        else:
            if len(terminal_steps) < 2:
                return _failure("URL_BLOCKED")
            try:
                terminal_ids = {s.get("id") for s in terminal_steps}
            except Exception:
                return _failure("URL_BLOCKED")
            id_to_hop = {}
            try:
                for hop, step in zip(hops_out, steps):
                    id_to_hop[step.get("id")] = hop
            except Exception:
                return _failure("URL_BLOCKED")
            try:
                terminal_hops = [id_to_hop[tid] for tid in [s.get("id") for s in steps if s.get("id") in terminal_ids]]
            except Exception:
                return _failure("URL_BLOCKED")
            if len(terminal_hops) != len(terminal_steps):
                return _failure("URL_BLOCKED")
            result_kind = None
            if chain_kind == "comparison":
                result_kind = "comparison"
            elif chain_kind == "intersection":
                result_kind = "intersection"
            elif chain_kind == "facets":
                result_kind = None
            # Intersection: require unique exact canonical equality across
            # all terminals using only grounded relation slots.
            if chain_kind == "intersection":
                try:
                    slot_canons = []
                    for step, hop in zip(
                        [s for s in steps if s.get("id") in terminal_ids],
                        terminal_hops,
                    ):
                        relation = step.get("relation", {})
                        tkind = relation.get("kind")
                        tbase = relation.get("base")
                        grounding_q = ""
                        try:
                            for h, s2 in zip(hops_out, steps):
                                if s2.get("id") == step.get("id"):
                                    grounding_q = h.get("query", "")
                                    break
                        except Exception:
                            grounding_q = ""
                        subj = _research_terminal_subject(grounding_q, tkind, tbase)
                        if not subj:
                            return _failure_with_actual(
                                status="abstained",
                                max_hops=max_hops, max_searches=max_searches,
                                hops_planned=hops_planned,
                                hops_completed=hops_planned - 1,
                                search_calls=search_calls,
                                intermediate=_build_chain_intermediate(
                                    stamped_completed, []
                                ),
                                kind="intersection",
                            )
                        sentences = _research_step_binding_sentences(hop.get("answer", ""))
                        _display, canons = _research_unique_binding(
                            sentences, tkind, subj, tbase
                        )
                        if _display is None or len(canons) != 1:
                            return _failure_with_actual(
                                status="abstained",
                                max_hops=max_hops, max_searches=max_searches,
                                hops_planned=hops_planned,
                                hops_completed=hops_planned - 1,
                                search_calls=search_calls,
                                intermediate=_build_chain_intermediate(
                                    stamped_completed, []
                                ),
                                kind="intersection",
                            )
                        slot_canons.append(canons[0])
                    first = slot_canons[0] if slot_canons else ""
                    for other in slot_canons[1:]:
                        try:
                            same = _vendor_answer._same_slot(first, other)
                        except Exception:
                            same = (first == other)
                        if not same:
                            return _failure_with_actual(
                                status="abstained",
                                max_hops=max_hops, max_searches=max_searches,
                                hops_planned=hops_planned,
                                hops_completed=hops_planned,
                                search_calls=search_calls,
                                intermediate=_build_chain_intermediate(
                                    stamped_completed, []
                                ),
                                kind="intersection",
                            )
                except Exception:
                    return _failure("URL_BLOCKED")
            try:
                composed = _compose_multi_terminal(
                    terminal_hops, max_results=max_results
                )
            except Exception:
                return _failure("URL_BLOCKED")
            if composed == "CAP_EXCEEDED":
                return _failure_with_actual(
                    status="partial",
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=hops_planned,
                    hops_completed=hops_planned - 1,
                    search_calls=search_calls,
                    intermediate=_build_chain_intermediate(
                        stamped_completed, []
                    ),
                    kind=result_kind,
                )
            if composed is None:
                return _failure_with_actual(
                    status="partial",
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=hops_planned,
                    hops_completed=hops_planned - 1,
                    search_calls=search_calls,
                    intermediate=_build_chain_intermediate(
                        stamped_completed, []
                    ),
                    kind=result_kind,
                )
            final_answer, final_sources = composed
        try:
            final_urls = [s.get("url") for s in final_sources]
        except Exception:
            return _failure("URL_BLOCKED")
        intermediate = _build_chain_intermediate(stamped_nonterminal, final_urls)
        # Propagate literal year for temporal qualifier successes (closed).
        _year_out = None
        try:
            for _st in steps:
                _tc = _st.get("temporal_condition")
                if isinstance(_tc, dict):
                    _yv = _tc.get("year")
                    if _is_four_digit_year(_yv):
                        _year_out = _yv
                        break
        except Exception:
            _year_out = None
        try:
            meta = _build_research_metadata(
                status="completed",
                max_hops=max_hops,
                max_searches=max_searches,
                hops_planned=hops_planned,
                hops_completed=hops_planned,
                search_calls=search_calls,
                kind=result_kind,
                year=_year_out,
                _op_budget=_op_budget,
                _is_builtin=_is_builtin,
                candidates_considered=_candidates_considered,
                http_requests=_http_now(),
            )
        except Exception:
            meta = None
        if meta is None:
            return _failure("URL_BLOCKED")
        try:
            out = {}
            out["answer"] = final_answer
            out["sources"] = final_sources
            out["ok"] = True
            out["hops"] = list(hops_out)
            inner = dict(meta.get("research", {}))
            inner["intermediate_evidence"] = list(intermediate)
            meta["research"] = inner
            out["metadata"] = meta
            out["provenance"] = {"intermediate_evidence": list(intermediate)}
        except Exception:
            return _failure("URL_BLOCKED")
        return out
    except Exception:
        return _failure("URL_BLOCKED")


def _make_answer_operation(deps):
    def _answer_operation(query, max_results=_CANDIDATE_CAP, *, research=False,
                          max_hops=2, max_searches=4):
        if (
            not isinstance(query, str)
            or len(query) < 1
            or len(query) > 2000
            or re.search(r"\S", query) is None
        ):
            return _failure("URL_BLOCKED")
        if type(max_results) is not int or not 1 <= max_results <= _CANDIDATE_CAP:
            return _failure("URL_BLOCKED")
        if type(research) is not bool:
            return _failure("URL_BLOCKED")
        if type(max_hops) is not int or not 1 <= max_hops <= 4:
            return _failure("URL_BLOCKED")
        if type(max_searches) is not int or not 1 <= max_searches <= 8:
            return _failure("URL_BLOCKED")
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
        try:
            _op_budget = _AnswerRequestBudget(max_searches)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            _budget_aware = getattr(search, "_GOAT_BUDGET_AWARE", False) is True
        except Exception:
            _budget_aware = False
        try:
            _is_builtin = getattr(search, "_GOAT_BUILTIN_METERED", False) is True
        except Exception:
            _is_builtin = False

        def _search_call(_q):
            # Honor trusted budget protocol once; no TypeError retry without
            # budget (prevents hidden HTTP retries). Custom physical unknown.
            if _budget_aware:
                return search(
                    _q, max_results=_CANDIDATE_CAP, _request_budget=_op_budget
                )
            return search(_q, max_results=_CANDIDATE_CAP)

        def _budget_exhausted():
            try:
                return _budget_aware and _op_budget.used >= _op_budget.max_http
            except Exception:
                return False

        def _failure_with_budget(code):
            try:
                if code == "INSUFFICIENT_EVIDENCE" and _budget_exhausted():
                    return _budget_exhausted_result(
                        max_hops=max_hops,
                        max_searches=max_searches,
                        hops_planned=2 if _is_two_hop else 1,
                        _op_budget=_op_budget, _is_builtin=_is_builtin,
                    )
            except Exception:
                pass
            return _failure(code)

        stripped = query.strip() if isinstance(query, str) else query
        # research=True rejects credential/control before backend (zero calls).
        if research is True and isinstance(stripped, str):
            try:
                _has_control = any(ord(c) < 32 for c in stripped)
            except Exception:
                _has_control = False
            try:
                _has_cred = ("://" in stripped and "@" in stripped)
                if not _has_cred and "@" in stripped and "user:" in stripped.casefold():
                    _has_cred = True
            except Exception:
                _has_cred = False
            if _has_control or _has_cred:
                return _failure("URL_BLOCKED")
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
        if research is True:
            try:
                _plan_fn = getattr(_vendor_answer, "plan_research_query", None)
                _validate_fn = getattr(
                    _vendor_answer, "validate_research_plan", None
                )
            except Exception:
                _plan_fn, _validate_fn = None, None
            _research_plan = None
            if callable(_plan_fn):
                try:
                    _research_plan = _plan_fn(
                        stripped, max_hops=max_hops, max_searches=max_searches
                    )
                except Exception:
                    _research_plan = None
            _research_valid = False
            if isinstance(_research_plan, dict) and callable(_validate_fn):
                try:
                    _research_valid = _validate_fn(_research_plan) is True
                except Exception:
                    _research_valid = False
            if _research_valid:
                return _execute_research_plan(
                    _research_plan,
                    max_results=max_results,
                    max_hops=max_hops,
                    max_searches=max_searches,
                    _search_call=_search_call,
                    _op_budget=_op_budget,
                    _budget_aware=_budget_aware,
                    _is_builtin=_is_builtin,
                )
            # Opt-in research never falls back to legacy two-hop/single-hop
            # with guessed scope; dedicated plan or explicit unsupported only.
            try:
                _up_len = len(
                    _research_plan.get("steps", [])
                ) if isinstance(_research_plan, dict) else 0
            except Exception:
                _up_len = 0
            if type(_up_len) is not int or not 0 <= _up_len <= 8:
                _up_len = 0
            try:
                _up_reason = _research_plan.get("reason") if isinstance(_research_plan, dict) else None
                if not isinstance(_up_reason, str) or _up_reason not in _KNOWN_RESEARCH_REASON:
                    _up_reason = None
            except Exception:
                _up_reason = None
            try:
                _up_ans = _research_plan.get("answerable") if isinstance(_research_plan, dict) else None
                if type(_up_ans) is not bool:
                    _up_ans = None
            except Exception:
                _up_ans = None
            # Preserve explicit unsupported-computation reasons; arithmetic
            # abstains with zero calls but public reason stays.
            if _up_reason in (_TEMPORAL_COMPARE_REASON, _ARITHMETIC_REASON):
                return _unsupported_research_result(
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=_up_len,
                    reason=_up_reason,
                    answerable=_up_ans,
                )
            return _unsupported_research_result(
                max_hops=max_hops, max_searches=max_searches,
                hops_planned=_up_len,
            )
        if _is_two_hop:
            try:
                _needs_two = 2
            except Exception:
                _needs_two = 2
            if max_hops < _needs_two or max_searches < _needs_two:
                return _budget_exhausted_result(
                    max_hops=max_hops,
                    max_searches=max_searches,
                    hops_planned=2,
                )
        if not _is_two_hop:
            try:
                response = _search_call(stripped)
            except Exception as error:
                try:
                    _code = _vendor_contract.public_error_code(error)
                except Exception:
                    _code = "URL_BLOCKED"
                return _failure_with_budget(_code)
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
                return _failure_with_budget(code)
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
            try:
                _single_sources = out.get("sources")
                _single_answer = out.get("answer")
            except Exception:
                return _failure("URL_BLOCKED")
            # Always validate final citation composition even for legacy
            # single-hop, not only duplicate URLs. Inner numeric brackets in
            # claim BODY abstain (no strip, no phantom indices).
            try:
                _recomposed = _compose_cited_answer(
                    _single_answer, _single_sources, max_results=max_results
                )
            except Exception:
                _recomposed = None
            if _recomposed is None:
                return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
            _new_answer, _new_sources = _recomposed
            out["answer"] = _new_answer
            out["sources"] = _new_sources
            return out
        hop1 = plan[0]
        try:
            response1 = _search_call(hop1)
        except Exception as error:
            try:
                _code1 = _vendor_contract.public_error_code(error)
            except Exception:
                _code1 = "URL_BLOCKED"
            return _failure_with_budget(_code1)
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
            return _failure_with_budget(code)
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
        try:
            _legacy_n1 = len(candidates1)
        except Exception:
            _legacy_n1 = 0
        _legacy_n2 = [0]

        def _legacy_candidate_total():
            try:
                _a = _legacy_n1 if type(_legacy_n1) is int else 0
                _b = _legacy_n2[0] if type(_legacy_n2[0]) is int else 0
                _t = _a + _b
                if _t < 0:
                    return 0
                if _t > 40:
                    return 40
                return _t
            except Exception:
                return 0

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
        # Legacy resolved guards before second transport: bridge <=512,
        # resolved query <=2000, no userinfo/controls/joint ambiguity.
        # Violation -> no second call, no credential leak.
        try:
            _bad_bridge = False
            try:
                if len(bridge) < 1 or len(bridge) > 512:
                    _bad_bridge = True
                elif any(ord(c) < 32 for c in bridge):
                    _bad_bridge = True
                elif "://" in bridge:
                    _bad_bridge = True
                elif "@" in bridge and ("user:" in bridge.casefold() or "://" in bridge):
                    _bad_bridge = True
                elif re.search(r"\b(and|or)\b", bridge, re.IGNORECASE) is not None:
                    _bad_bridge = True
                elif len(hop2) < 1 or len(hop2) > 2000:
                    _bad_bridge = True
                elif any(ord(c) < 32 for c in hop2):
                    _bad_bridge = True
                elif "://" in hop2:
                    _bad_bridge = True
                elif "@" in hop2 and "user:" in hop2.casefold():
                    _bad_bridge = True
            except Exception:
                _bad_bridge = True
            if _bad_bridge:
                try:
                    _tmpb = []
                    for _s in hop1_sources:
                        if isinstance(_s, Mapping):
                            try:
                                _d = dict(_s)
                                if type(_d.get("index")) is not int:
                                    continue
                                _d["hop"] = 1
                                _tmpb.append(_d)
                            except Exception:
                                continue
                    try:
                        _interb = _build_intermediate_evidence(_tmpb, [])
                    except Exception:
                        _interb = []
                    try:
                        _http_b = getattr(_op_budget, "used", 0) if _is_builtin is True and _op_budget is not None else None
                        if _http_b is not None and type(_http_b) is not int:
                            _http_b = None
                    except Exception:
                        _http_b = None
                    try:
                        _leg_url = None
                        for _e in _tmpb:
                            try:
                                _u = _e.get("url")
                            except Exception:
                                continue
                            if isinstance(_u, str) and _u:
                                try:
                                    _al, _cc = _vendor_guard.check_url(_u)
                                except Exception:
                                    continue
                                if _al and len(_u) <= _vendor_answer.MAX_URL_CHARS:
                                    _leg_url = _u
                                    break
                        _leg_hops = [
                            {"id": "s1", "index": 1, "depth": 1, "status": "completed", "code": "COMPLETED", "depends_on": []},
                            {"id": "s2", "index": 2, "depth": 2, "status": "failed", "code": "INSUFFICIENT_EVIDENCE", "depends_on": ["s1"]},
                        ]
                        if isinstance(_leg_url, str) and _leg_url:
                            _leg_hops[0]["url"] = _leg_url
                    except Exception:
                        _leg_hops = None
                    return _research_failure_result(
                        status="partial",
                        max_hops=max_hops, max_searches=max_searches,
                        hops_planned=2, hops_completed=1,
                        search_calls=1,
                        code="INSUFFICIENT_EVIDENCE",
                        intermediate=_interb,
                        _op_budget=_op_budget, _is_builtin=_is_builtin,
                        http_requests=_http_b,
                        candidates_considered=_legacy_candidate_total(),
                        hops=_leg_hops,
                    )
                except Exception:
                    return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
        except Exception:
            pass

        def _legacy_partial(_code):
            try:
                _tmp = []
                for _s in hop1_sources:
                    if isinstance(_s, Mapping):
                        try:
                            _d = dict(_s)
                            if type(_d.get("index")) is not int:
                                continue
                            _d["hop"] = 1
                            _tmp.append(_d)
                        except Exception:
                            continue
                try:
                    _inter = _build_intermediate_evidence(_tmp, [])
                except Exception:
                    _inter = []
                try:
                    _http_l = getattr(_op_budget, "used", 0) if _is_builtin is True and _op_budget is not None else None
                    if _http_l is not None and type(_http_l) is not int:
                        _http_l = None
                except Exception:
                    _http_l = None
                try:
                    _leg_url2 = None
                    for _e2 in _tmp:
                        try:
                            _u2 = _e2.get("url")
                        except Exception:
                            continue
                        if isinstance(_u2, str) and _u2:
                            try:
                                _al2, _cc2 = _vendor_guard.check_url(_u2)
                            except Exception:
                                continue
                            if _al2 and len(_u2) <= _vendor_answer.MAX_URL_CHARS:
                                _leg_url2 = _u2
                                break
                    try:
                        _leg_code = _vendor_contract.public_error_code({"code": _code})
                    except Exception:
                        _leg_code = _code
                    _leg_hops2 = [
                        {"id": "s1", "index": 1, "depth": 1, "status": "completed", "code": "COMPLETED", "depends_on": []},
                        {"id": "s2", "index": 2, "depth": 2, "status": "failed", "code": _leg_code, "depends_on": ["s1"]},
                    ]
                    if isinstance(_leg_url2, str) and _leg_url2:
                        _leg_hops2[0]["url"] = _leg_url2
                except Exception:
                    _leg_hops2 = None
                return _research_failure_result(
                    status="partial",
                    max_hops=max_hops, max_searches=max_searches,
                    hops_planned=2, hops_completed=1,
                    search_calls=2,
                    code=_code,
                    intermediate=_inter,
                    _op_budget=_op_budget, _is_builtin=_is_builtin,
                    http_requests=_http_l,
                    candidates_considered=_legacy_candidate_total(),
                    hops=_leg_hops2,
                )
            except Exception:
                return {"ok": False, "error": {"code": _code}}

        try:
            response2 = _search_call(hop2)
        except Exception as error:
            try:
                _code2e = _vendor_contract.public_error_code(error)
            except Exception:
                _code2e = "URL_BLOCKED"
            # Terminal failure after grounded hop1: controlled partial.
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial(_code2e)
            except Exception:
                pass
            return _failure_with_budget(_code2e)
        try:
            normalized2 = _vendor_contract.normalize_result(response2)
        except Exception:
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial("URL_BLOCKED")
            except Exception:
                pass
            return _failure("URL_BLOCKED")
        try:
            backend_failed2 = (
                normalized2.get("ok") is False
                or normalized2.get("error") is not None
            )
        except Exception:
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial("URL_BLOCKED")
            except Exception:
                pass
            return _failure("URL_BLOCKED")
        if backend_failed2:
            try:
                code = _vendor_contract.public_error_code(
                    normalized2.get("error")
                )
            except Exception:
                code = "URL_BLOCKED"
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial(code)
            except Exception:
                pass
            return _failure_with_budget(code)
        try:
            results2 = normalized2.get("results")
        except Exception:
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial("URL_BLOCKED")
            except Exception:
                pass
            return _failure("URL_BLOCKED")
        if not isinstance(results2, list):
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial("URL_BLOCKED")
            except Exception:
                pass
            return _failure("URL_BLOCKED")
        try:
            overproduced2 = len(results2) > _CANDIDATE_CAP
        except Exception:
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial("URL_BLOCKED")
            except Exception:
                pass
            return _failure("URL_BLOCKED")
        try:
            candidates2 = list(results2[:_CANDIDATE_CAP])
        except Exception:
            try:
                if isinstance(hop1_sources, list) and hop1_sources:
                    return _legacy_partial("URL_BLOCKED")
            except Exception:
                pass
            return _failure("URL_BLOCKED")
        try:
            _legacy_n2[0] = len(candidates2)
        except Exception:
            pass
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
            try:
                _c2e = _vendor_contract.public_error_code(error)
            except Exception:
                _c2e = "URL_BLOCKED"
            try:
                return _legacy_partial(_c2e)
            except Exception:
                return _failure(_c2e)
        if not isinstance(raw2, Mapping):
            try:
                return _legacy_partial("URL_BLOCKED")
            except Exception:
                return _failure("URL_BLOCKED")
        try:
            raw_failed2 = (
                raw2.get("ok") is False or raw2.get("error") is not None
            )
        except Exception:
            try:
                return _legacy_partial("URL_BLOCKED")
            except Exception:
                return _failure("URL_BLOCKED")
        if raw_failed2:
            try:
                _err2 = raw2.get("error")
            except Exception:
                try:
                    return _legacy_partial("URL_BLOCKED")
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
                try:
                    return _legacy_partial("INSUFFICIENT_EVIDENCE")
                except Exception:
                    return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
            try:
                code = _vendor_contract.public_error_code(raw2.get("error"))
            except Exception:
                code = "URL_BLOCKED"
            try:
                return _legacy_partial(code)
            except Exception:
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
                try:
                    return _legacy_partial("INSUFFICIENT_EVIDENCE")
                except Exception:
                    return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
        try:
            _hop1_dup = _has_duplicate_urls(hop1_sources)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            _hop2_dup = _has_duplicate_urls(hop2_sources)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            if _hop1_dup:
                _fixed1 = _compose_cited_answer(
                    hop1_answer, hop1_sources, max_results=max_results
                )
                if _fixed1 is None:
                    return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
                hop1_answer_fixed, hop1_sources_fixed = _fixed1
            else:
                hop1_answer_fixed, hop1_sources_fixed = hop1_answer, hop1_sources
            if _hop2_dup:
                _fixed2 = _compose_cited_answer(
                    hop2_answer, hop2_sources, max_results=max_results
                )
                if _fixed2 is None:
                    return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
                hop2_answer_fixed, hop2_sources_fixed = _fixed2
            else:
                hop2_answer_fixed, hop2_sources_fixed = hop2_answer, hop2_sources
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            _final_composed = _compose_cited_answer(
                hop2_answer_fixed, hop2_sources_fixed, max_results=max_results
            )
        except Exception:
            try:
                return _legacy_partial("URL_BLOCKED")
            except Exception:
                return _failure("URL_BLOCKED")
        if _final_composed is None:
            try:
                return _legacy_partial("INSUFFICIENT_EVIDENCE")
            except Exception:
                return {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
        _final_answer, _final_sources = _final_composed
        try:
            hop1_stamped = []
            for _s in hop1_sources_fixed:
                if not isinstance(_s, Mapping):
                    return _failure("URL_BLOCKED")
                _d = dict(_s)
                try:
                    _idx = _d.get("index")
                except Exception:
                    return _failure("URL_BLOCKED")
                if type(_idx) is not int:
                    return _failure("URL_BLOCKED")
                _d["hop"] = 1
                hop1_stamped.append(_d)
            hop2_stamped = []
            for _s in hop2_sources_fixed:
                if not isinstance(_s, Mapping):
                    return _failure("URL_BLOCKED")
                _d = dict(_s)
                try:
                    _idx = _d.get("index")
                except Exception:
                    return _failure("URL_BLOCKED")
                if type(_idx) is not int:
                    return _failure("URL_BLOCKED")
                _d["hop"] = 2
                hop2_stamped.append(_d)
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            _final_urls = [s.get("url") for s in _final_sources]
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            _intermediate = _build_intermediate_evidence(hop1_stamped, _final_urls)
        except Exception:
            _intermediate = []
        try:
            try:
                _used_l = getattr(_op_budget, "used", 0) if _is_builtin is True and _op_budget is not None else None
                if _used_l is not None and type(_used_l) is not int:
                    _used_l = None
            except Exception:
                _used_l = None
            _research_meta = _build_research_metadata(
                status="completed",
                max_hops=max_hops,
                max_searches=max_searches,
                hops_planned=2,
                hops_completed=2,
                search_calls=2,
                _op_budget=_op_budget,
                _is_builtin=_is_builtin,
                http_requests=_used_l,
                candidates_considered=_legacy_candidate_total(),
            )
        except Exception:
            _research_meta = None
        if _research_meta is None:
            return _failure("URL_BLOCKED")
        try:
            out = {}
        except Exception:
            return _failure("URL_BLOCKED")
        out["answer"] = _final_answer
        out["sources"] = _final_sources
        out["ok"] = True
        # Successful legacy 2-hop: self-construct provenance/hops; preserve
        # ONLY verified default wikipedia labels, never foreign transitions/
        # metadata/provenance/exception/credential strings.
        for _key in ("source", "source_url"):
            try:
                if _key in provenance2:
                    _v = provenance2[_key]
                    if _key == "source" and _v == WIKIPEDIA_SOURCE:
                        out[_key] = _v
                    elif _key == "source_url" and _v == WIKIPEDIA_SOURCE_URL:
                        out[_key] = _v
            except Exception:
                return _failure("URL_BLOCKED")
        try:
            out["hops"] = [
                {"query": hop1, "answer": hop1_answer_fixed, "sources": hop1_stamped},
                {"query": hop2, "answer": hop2_answer_fixed, "sources": hop2_stamped},
            ]
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            _meta = dict(_research_meta)
            _research_inner = dict(_meta.get("research", {}))
            _research_inner["intermediate_evidence"] = list(_intermediate)
            _meta["research"] = _research_inner
            out["metadata"] = _meta
        except Exception:
            return _failure("URL_BLOCKED")
        try:
            out["provenance"] = {"intermediate_evidence": list(_intermediate)}
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
