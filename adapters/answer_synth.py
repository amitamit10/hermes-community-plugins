"""Deterministic, extractive answer synthesis for Goat search snippets.

This module does not perform network or model calls. Inject a search callable
with the interface ``search(query)``; its response should contain a ``results``
list of title/url/snippet mappings, as returned by ``goat_search``.
"""

from collections.abc import Mapping
import re


MISSING_CONFIG = "MISSING_CONFIG"
URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
MAX_ANSWER_CHARS = 8000
MAX_CONTENT_CHARS = MAX_ANSWER_CHARS
MAX_RESULTS = 5
MAX_TITLE_CHARS = 512
MAX_URL_CHARS = 2048
_PUBLIC_ERRORS = frozenset((MISSING_CONFIG, URL_BLOCKED, REDIRECT_BLOCKED))
_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|[\r\n]+")


def _error_result(code):
    return {"error": {"code": code}}


def _map_error(error):
    if isinstance(error, Mapping):
        code = error.get("code", error.get("error"))
        if isinstance(code, Mapping):
            code = code.get("code")
    else:
        code = getattr(error, "code", error)
    if code is None:
        return MISSING_CONFIG
    if not isinstance(code, str):
        return URL_BLOCKED
    if code in _PUBLIC_ERRORS:
        return code
    if code in ("PROVIDER_NOT_CONFIGURED", "MISSING_PROVIDER_CONFIG"):
        return MISSING_CONFIG
    if code in ("REDIRECT_FAILED", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT"):
        return REDIRECT_BLOCKED
    return URL_BLOCKED


def _text(value):
    return value.strip() if isinstance(value, str) else ""


def _tokens(text):
    return {token.casefold() for token in _TOKEN_RE.findall(text)}


def _ranked_results(results, query_terms, limit):
    ranked = []
    for order, item in enumerate(results[:MAX_RESULTS]):
        if not isinstance(item, Mapping):
            continue
        snippet = _text(item.get("snippet", item.get("description", "")))
        if not snippet:
            continue
        title = _text(item.get("title", ""))
        title_matches = len(query_terms & _tokens(title))
        snippet_matches = len(query_terms & _tokens(snippet))
        score = 3 * title_matches + 2 * snippet_matches
        ranked.append((score, order, item, title, snippet))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return ranked[:limit]


def _claim_texts(snippet):
    return [part.strip() for part in _SENTENCE_RE.split(snippet) if part.strip()]


def _deduplicated_claims(ranked):
    claims = []
    by_text = {}
    for source_index, (_score, _order, _item, _title, snippet) in enumerate(ranked, 1):
        for text in _claim_texts(snippet):
            key = " ".join(_TOKEN_RE.findall(text.casefold()))
            if not key:
                continue
            existing = by_text.get(key)
            if existing is None:
                existing = {"text": text, "sources": []}
                by_text[key] = existing
                claims.append(existing)
            if source_index not in existing["sources"]:
                existing["sources"].append(source_index)
    return claims


def _citation(sources):
    return "".join(f"[{source}]" for source in sources)


def _fit_claim(text, citation, capacity):
    complete = f"{text} {citation}"
    if len(complete) <= capacity:
        return complete
    reserve = len(citation) + 2  # ellipsis and separating space
    text_capacity = capacity - reserve
    if text_capacity < 1:
        return ""
    excerpt = text[:text_capacity]
    if len(text) > text_capacity and " " in excerpt:
        excerpt = excerpt.rsplit(" ", 1)[0]
    excerpt = excerpt.rstrip(" ,;:")
    if not excerpt:
        return ""
    return f"{excerpt}… {citation}"


def _answer_text(claims):
    lines = []
    used = 0
    for claim in claims:
        citation = _citation(claim["sources"])
        separator = 1 if lines else 0
        capacity = MAX_ANSWER_CHARS - used - separator
        original_length = len(claim["text"]) + 1 + len(citation)
        line = _fit_claim(claim["text"], citation, capacity)
        if not line:
            break
        if lines and len(line) < original_length:
            break
        lines.append(line)
        used += separator + len(line)
        if len(line) < original_length:
            break
    return "\n".join(lines)


def goat_answer(query, search=None, *, max_results=MAX_RESULTS):
    """Return ranked extractive claims with one-based source citations.

    The injected callable is invoked as ``search(query)`` and must return a
    Goat-style mapping with a ``results`` list. An empty result set is reported
    as ``MISSING_CONFIG`` to match the surrounding Goat tool contract.
    """
    if not callable(search):
        return _error_result(MISSING_CONFIG)
    if not isinstance(query, str) or not query.strip():
        return _error_result(URL_BLOCKED)
    if (
        isinstance(max_results, bool)
        or not isinstance(max_results, int)
        or not 1 <= max_results <= MAX_RESULTS
    ):
        return _error_result(URL_BLOCKED)

    try:
        response = search(query.strip())
    except Exception as error:
        return _error_result(_map_error(error))

    if isinstance(response, Mapping) and response.get("error") is not None:
        return _error_result(_map_error(response.get("error")))
    results = response.get("results") if isinstance(response, Mapping) else None
    if not isinstance(results, (list, tuple)) or not results:
        return _error_result(MISSING_CONFIG)

    ranked = _ranked_results(results, _tokens(query), max_results)
    if not ranked:
        return _error_result(MISSING_CONFIG)

    answer = _answer_text(_deduplicated_claims(ranked))
    if not answer:
        return _error_result(MISSING_CONFIG)

    sources = [
        {
            "index": index,
            "title": title[:MAX_TITLE_CHARS],
            "url": _text(item.get("url", ""))[:MAX_URL_CHARS],
        }
        for index, (_score, _order, item, title, _snippet) in enumerate(ranked, 1)
    ]
    return {"answer": answer, "sources": sources}


def register():
    """Return the public tool-name to handler mapping for plugin loading."""
    return {"goat_answer": goat_answer}


__all__ = [
    "MAX_ANSWER_CHARS",
    "MAX_CONTENT_CHARS",
    "MAX_RESULTS",
    "MISSING_CONFIG",
    "REDIRECT_BLOCKED",
    "URL_BLOCKED",
    "goat_answer",
    "register",
]
