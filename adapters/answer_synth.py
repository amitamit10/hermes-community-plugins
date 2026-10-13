"""Bounded extractive fact answers with sentence-level grounding.

No network or model calls. Inject ``search(query)`` returning a Goat-style
mapping with a ``results`` list of title/url/extract/snippet items. Each
returned claim is one complete safe declarative source sentence that alone
covers the requested relation (capital/discovery/generic who-verb) or all
content query tokens (keyword); titles, other sentences, negated, uncertain,
fragmentary, overlong, conflicting, or answer-bound-pruned text never becomes
evidence. Sources are exact safe HTTPS URLs of at most 2048 chars, at most 5
results, 8000 answer chars; every listed source is cited by a real identical
sentence. Anything unsupported, ambiguous, multi-hop, or ungrounded returns
INSUFFICIENT_EVIDENCE, never a guess.
"""

from collections.abc import Mapping
import re

if __package__:
    from .result_contract import public_error_code, result_operation
else:
    from result_contract import public_error_code, result_operation


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
_QUESTION_STOPWORDS = frozenset((
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "is", "are", "was", "were", "be", "been", "being", "do", "does", "did", "done",
    "the", "a", "an", "of", "for", "to", "in", "on", "at", "by", "with", "about",
    "as", "from", "that", "this", "these", "those", "it", "its", "and", "or",
    "but", "if", "then", "than", "so", "such", "no", "not", "only", "own", "same",
    "tell", "me", "you", "your", "please", "name", "give", "list", "show",
))
_CAPITAL_TOKENS = frozenset(("capital", "capitals"))
_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
_INTERROGATIVE_FIRST = frozenset((
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "is", "are", "was", "were", "do", "does", "did",
    "tell", "name", "give", "list", "show",
))
_NEGATION_RE = re.compile(
    r"\b(never|not|no|neither|nor|without|deny|denies|denied|false)\b"
    r"|n['\u2019]t\b|\bcannot\b",
    re.IGNORECASE,
)
_HEDGE_RE = re.compile(
    r"\b(speculat\w*|alleg\w*|myth\w*|legend\w*|rumou?r\w*|perhaps|maybe|"
    r"possibly|probably|likely|unlikely|seem\w*|appear\w*|believ\w*|think\w*|"
    r"thought\w*|unconfirm\w*|disput\w*|controvers\w*|suppos\w*|purport\w*|"
    r"report\w*|claim\w*|suggest\w*|debunk\w*|hoax\w*|misconception\w*|"
    r"incorrect\w*|said|says|saying|told|tell\w*|asked?|asks?|question\w*|"
    r"according|sources?\b|critics?\b)\b",
    re.IGNORECASE,
)
_UNRESOLVED_SLOTS = frozenset((
    "i", "me", "my", "mine", "you", "your", "yours",
    "he", "him", "his", "she", "her", "hers",
    "it", "its", "we", "us", "our", "ours",
    "they", "them", "their", "theirs",
    "this", "that", "these", "those", "here", "there",
    "one", "ones", "someone", "somebody", "something",
    "anyone", "anybody", "anything",
    "everyone", "everybody", "everything",
    "nobody", "nothing",
    "who", "whom", "whose", "what", "which",
))
_DATE_PREFIX_RE = re.compile(r"^in \d{3,4}\b[\s,]*")
_DISCOVERY_VERBS = frozenset(("discover", "discovered", "discovers", "discovering"))
_GENERIC_QUERY_PAST_TO_BASE = {
    "wrote": "write", "written": "write", "invented": "invent",
    "found": "found", "founded": "found", "created": "create",
    "designed": "design",
}
_GENERIC_ACTIVE_FORMS = {
    "write": ("wrote",), "invent": ("invented",),
    "found": ("found", "founded"), "create": ("created",),
    "design": ("designed",),
}
_GENERIC_PASSIVE_FORMS = {
    "write": ("written",), "invent": ("invented",),
    "found": ("found", "founded"), "create": ("created",),
    "design": ("designed",),
}
_CLAUSE_ACTOR_TOKENS = frozenset((
    "that", "who", "whom", "whose", "which", "what",
    "know", "knows", "knew", "known", "knowing",
    "hear", "hears", "heard", "hearing",
    "say", "says", "said", "saying",
    "tell", "tells", "told", "telling",
    "ask", "asks", "asked", "asking",
    "think", "thinks", "thought", "thinking",
    "believe", "believes", "believed", "believing",
    "claim", "claims", "claimed", "claiming",
    "report", "reports", "reported", "reporting",
    "suggest", "suggests", "suggested", "suggesting",
    "according",
))
_ACTOR_TITLES = frozenset((
    "mr", "mrs", "ms", "miss", "dr", "prof", "professor",
    "sir", "dame", "lord", "lady", "st",
))
_ACTOR_CONNECTOR = frozenset(("and",))
_ACTOR_NON_NAME = frozenset((
    "could", "would", "should", "may", "might", "must", "shall",
    "will", "can", "ought", "have", "has", "had", "having",
    "am", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "done",
    "before", "after", "when", "while", "because", "although",
    "though", "unless", "until", "since", "during", "despite",
    "between", "among", "through", "over", "under", "above",
    "below", "behind", "beside", "around", "near",
    "almost", "also", "first", "jointly", "likewise", "just",
    "even", "still", "already", "merely", "nearly", "really",
    "very", "too", "quite", "rather", "together", "separately",
    "yesterday", "today", "tomorrow", "now", "then",
    "here", "there", "so", "very", "more", "most", "less",
    "least", "own", "same", "such", "only", "not", "no",
    "never", "neither", "nor", "without", "cannot",
))
_ACTOR_NAME_RE = re.compile(r"[a-z]+(?:[-'][a-z]+)*")


def _has_embedded_clause(raw):
    if not isinstance(raw, str) or not raw:
        return False
    return bool(set(_TOKEN_RE.findall(raw.casefold())) & _CLAUSE_ACTOR_TOKENS)


def _is_interrogative_query(query):
    if not isinstance(query, str) or not query.strip():
        return False
    if "?" in query:
        return True
    first = _TOKEN_RE.findall(query.strip().casefold())
    if not first:
        return False
    return first[0] in _INTERROGATIVE_FIRST


def _error_result(code):
    return {"error": {"code": code}}


def _map_error(error):
    try:
        mapped = public_error_code(error)
    except Exception:
        mapped = URL_BLOCKED
    if mapped != URL_BLOCKED:
        return mapped
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


def _is_known_clipped_snippet(item):
    """Producer-marked character-clipped snippet without a full extract."""
    try:
        if not isinstance(item, Mapping):
            return False
        if item.get("snippet_cut") is not True:
            return False
        return not _text(item.get("extract", ""))
    except Exception:
        return False


def _evidence_text(item):
    extract = _text(item.get("extract", "")) if isinstance(item, Mapping) else ""
    if extract:
        return extract
    if _is_known_clipped_snippet(item):
        return ""
    return _text(item.get("snippet", item.get("description", "")))


def _content_query_tokens(query):
    return _tokens(query) - _QUESTION_STOPWORDS


def _is_safe_answer_url(url):
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    if len(url) > MAX_URL_CHARS or "\\" in url or " " in url:
        return False
    if any(ord(c) < 32 or ord(c) == 127 for c in url):
        return False
    try:
        from urllib.parse import urlsplit as _split
        parsed = _split(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.fragment:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if "@" in parsed.netloc:
        return False
    try:
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if not host:
        return False
    if port is not None and port != 443:
        return False
    return True


def _is_unreliable_sentence(text):
    if '"' in text or '\u201c' in text or '\u201d' in text:
        return True
    low = text.casefold()
    if _NEGATION_RE.search(low):
        return True
    if _HEDGE_RE.search(low):
        return True
    return False


def _is_fragmentary_sentence(text):
    if "..." in text or "\u2026" in text:
        return True
    if len(text) > MAX_CONTENT_CHARS:
        return True
    return False


def _is_complete_sentence(text):
    if not text or "?" in text:
        return False
    stripped = text.rstrip()
    if not stripped.endswith((".", "!")):
        return False
    return True


_ABBREV_TOKENS = frozenset((
    "mr", "mrs", "ms", "miss", "dr", "prof", "professor",
    "sr", "jr", "st", "vs", "etc", "eg", "ie",
))
_BOUNDARY_RE = re.compile(r"[.!?]+\s+|[\r\n]+")


def _is_abbrev_boundary(text, punct_start, punct_end):
    try:
        before = text[:punct_start].rstrip()
        m = re.search(r"([A-Za-z0-9]+)\.?$", before)
        if m:
            word = m.group(1).casefold()
            if word in _ABBREV_TOKENS:
                return True
            if len(word) == 1 and word.isalpha():
                return True
        if punct_start > 0 and text[punct_start - 1].isdigit():
            rest = text[punct_end:].lstrip()
            if rest and rest[0].isdigit():
                return True
    except Exception:
        return False
    return False


def _split_sentences(text):
    if not isinstance(text, str) or not text:
        return []
    parts = []
    start = 0
    for match in _BOUNDARY_RE.finditer(text):
        s, e = match.span()
        chunk = match.group(0)
        if "\n" in chunk or "\r" in chunk:
            # Newline always segments; include any leading punctuation.
            if text[start:e].strip():
                # If chunk starts with punctuation (e.g., ".\n"), include it.
                if s > start and text[s - 1] in ".!?":
                    punct_start = s - 1
                    while punct_start > start and text[punct_start - 1] in ".!?":
                        punct_start -= 1
                    if not _is_abbrev_boundary(text, punct_start, s):
                        parts.append(text[start:s].strip())
                        start = e
                        continue
                # Pure newline or abbrev punctuation+newline: split without
                # manufacturing a new sentence end.
                cur = text[start:e].strip()
                # If newline separates without terminal punctuation, keep as
                # separate raw pieces to avoid merging across lines.
                if cur:
                    # Split at newline: keep left part as candidate.
                    left = text[start:s].strip()
                    if left:
                        parts.append(left)
                    start = e
            else:
                start = e
            continue
        punct_end = s
        while punct_end < e and text[punct_end] in ".!?":
            punct_end += 1
        if _is_abbrev_boundary(text, s, punct_end):
            continue
        parts.append(text[start:punct_end].strip())
        start = e
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _claim_texts(snippet):
    return [part.strip() for part in _split_sentences(snippet) if part.strip()]


def _truncate_to_verified_boundary(value, limit=MAX_CONTENT_CHARS):
    if not isinstance(value, str):
        value = str(value) if value is not None else ""
    if len(value) <= limit:
        return value
    candidate = value[:limit]
    # Find last verified complete boundary within limit.
    best = -1
    for match in _BOUNDARY_RE.finditer(value):
        s, e = match.span()
        chunk = match.group(0)
        if "\n" in chunk or "\r" in chunk:
            # newline boundary at s (or after punctuation)
            if s > limit:
                break
            # verify: boundary exists in original (it does) - keep
            # For newline with leading punctuation, include punctuation.
            if s > 0 and value[s - 1] in ".!?":
                # include the punctuation
                if s <= limit:
                    # check abbrev for the punctuation part
                    punct_start = s - 1
                    while punct_start > 0 and value[punct_start - 1] in ".!?":
                        punct_start -= 1
                    # find punct end (=s)
                    if _is_abbrev_boundary(value, punct_start, s):
                        continue
                    best = s
            else:
                best = s
            if e > limit:
                break
            continue
        else:
            punct_end = s
            while punct_end < e and value[punct_end] in ".!?":
                punct_end += 1
            if punct_end > limit:
                break
            if _is_abbrev_boundary(value, s, punct_end):
                continue
            best = punct_end
    if best <= 0:
        return ""
    return value[:best].strip()


def _citation(sources):
    return "".join(f"[{source}]" for source in sources)


def _canonical_slot(slot):
    if not isinstance(slot, str) or not slot:
        return ""
    text = " ".join(_TOKEN_RE.findall(slot.casefold()))
    text = _DATE_PREFIX_RE.sub("", text).strip()
    return " ".join(_TOKEN_RE.findall(text.casefold()))


def _is_resolved_slot(slot):
    if not isinstance(slot, str) or not slot:
        return False
    original = slot.strip()
    if not original:
        return False
    try:
        date_match = re.match(r"In\s+\d{3,4}\b[\s,]*", original, re.IGNORECASE)
    except Exception:
        date_match = None
    if date_match:
        original = original[date_match.end():].strip()
        if not original:
            return False
    try:
        orig_tokens = _TOKEN_RE.findall(original)
    except Exception:
        return False
    if not orig_tokens:
        return False
    lower_tokens = [token.casefold() for token in orig_tokens]
    if not 1 <= len(lower_tokens) <= 5:
        return False
    canon = _canonical_slot(slot)
    if not canon:
        return False
    if canon in _UNRESOLVED_SLOTS:
        return False
    if any(token in _UNRESOLVED_SLOTS for token in lower_tokens):
        return False
    if lower_tokens[0] in _ACTOR_CONNECTOR or lower_tokens[-1] in _ACTOR_CONNECTOR:
        return False
    prev_conn = False
    has_name = False
    for orig, token in zip(orig_tokens, lower_tokens):
        if token in _ACTOR_CONNECTOR:
            if prev_conn:
                return False
            prev_conn = True
            continue
        prev_conn = False
        if token in _UNRESOLVED_SLOTS:
            return False
        if token in _ACTOR_NON_NAME:
            return False
        if token in _QUESTION_STOPWORDS and token not in _ACTOR_TITLES:
            return False
        if token in _CLAUSE_ACTOR_TOKENS:
            return False
        if token in _ACTOR_TITLES:
            if not orig[:1].isupper():
                return False
            continue
        if len(orig) == 1 and orig.isalpha() and orig.isupper():
            has_name = True
            continue
        if not orig[:1].isupper():
            return False
        if not orig.isalpha():
            return False
        if not _ACTOR_NAME_RE.fullmatch(token):
            return False
        has_name = True
    if not has_name:
        return False
    return True


def _same_slot(first, second):
    if not first or not second:
        return False
    canon_first = _canonical_slot(first)
    canon_second = _canonical_slot(second)
    if not canon_first or not canon_second:
        return False
    return canon_first == canon_second


def _normalize_subject_phrase(raw):
    if not isinstance(raw, str):
        return ""
    return " ".join(_TOKEN_RE.findall(raw.casefold()))


def _subject_pattern(phrase):
    tokens = _TOKEN_RE.findall(phrase.casefold())
    if not tokens:
        return ""
    return r"\b" + r"\s+".join(re.escape(token) for token in tokens) + r"\b"


def _ranked_results(results, query_terms, limit):
    ranked = []
    for order, item in enumerate(results[:MAX_RESULTS]):
        if not isinstance(item, Mapping):
            continue
        snippet = _evidence_text(item)
        if not snippet:
            continue
        title = _text(item.get("title", ""))
        title_matches = len(query_terms & _tokens(title))
        snippet_matches = len(query_terms & _tokens(snippet))
        score = 3 * title_matches + 2 * snippet_matches
        ranked.append((score, order, item, title, snippet))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    return ranked[:limit]


def _is_capital_query(query_terms):
    return bool(query_terms & _CAPITAL_TOKENS)


def _capital_subject_phrase(query):
    if not isinstance(query, str):
        return ""
    low = query.casefold()
    match = re.search(r"\bcapital\s+of\s+(?P<subj>.+)", low)
    if not match:
        return ""
    return _normalize_subject_phrase(match.group("subj"))


def _parse_capital_query(query):
    if not isinstance(query, str):
        return ""
    if _NEGATION_RE.search(query.casefold()):
        return ""
    low = query.strip().casefold()
    if not low:
        return ""
    if _is_interrogative_query(query):
        match = re.match(
            r"(what|which)\s+is\s+the\s+capital\s+(city\s+)?of\s+(?P<subj>.+?)\s*\??\s*$",
            low,
        )
        if not match:
            return ""
        subj = _normalize_subject_phrase(match.group("subj"))
        if not subj:
            return ""
        toks = set(_TOKEN_RE.findall(subj))
        if not toks:
            return ""
        if toks & _CAPITAL_TOKENS:
            return ""
        if toks & _DISCOVERY_VERBS:
            return ""
        if toks & frozenset(("who", "what", "which", "whom", "whose")):
            return ""
        for form in list(_GENERIC_QUERY_PAST_TO_BASE.keys()) + list(
            _GENERIC_QUERY_PAST_TO_BASE.values()
        ):
            if form in toks:
                return ""
        qtoks = set(_TOKEN_RE.findall(low))
        if qtoks & _DISCOVERY_VERBS:
            return ""
        for form in list(_GENERIC_QUERY_PAST_TO_BASE.keys()) + list(
            _GENERIC_QUERY_PAST_TO_BASE.values()
        ):
            if form in qtoks:
                return ""
        padded = " " + subj + " "
        for marker in (
            " and ",
            " or ",
            " who ",
            " whom ",
            " whose ",
            " which ",
            " what ",
            " with ",
            " using ",
            " used ",
            " by ",
        ):
            if marker in padded:
                return ""
        return subj
    match = re.search(r"\bcapital\s+(city\s+)?of\s+(?P<subj>.+)", low)
    if not match:
        return ""
    subj = _normalize_subject_phrase(match.group("subj"))
    if not subj:
        return ""
    toks = set(_TOKEN_RE.findall(subj))
    if not toks:
        return ""
    if toks & _CAPITAL_TOKENS:
        return ""
    if toks & _DISCOVERY_VERBS:
        return ""
    if toks & frozenset(("who", "what", "which", "whom", "whose")):
        return ""
    for form in list(_GENERIC_QUERY_PAST_TO_BASE.keys()) + list(
        _GENERIC_QUERY_PAST_TO_BASE.values()
    ):
        if form in toks:
            return ""
    return subj


def _is_discovery_query(query_terms):
    return "who" in query_terms and bool(query_terms & _DISCOVERY_VERBS)


def _discovery_subject_phrase(query):
    if not isinstance(query, str):
        return ""
    low = query.casefold().strip()
    match = re.match(r"who\s+discovered\s+(?P<subj>.+?)\s*\??\s*$", low)
    if not match:
        return ""
    return _normalize_subject_phrase(match.group("subj"))


def _parse_orbit_query(query):
    """Parse ``What does <subject> orbit?`` into a normalized subject phrase.

    Returns the subject phrase or ``None`` when the query is not a direct
    single-relation orbit question. Grounding still requires one complete
    cited source sentence (e.g. ``The Moon orbits the Earth.``); answers
    are never hardcoded here.
    """
    if not isinstance(query, str):
        return None
    low = query.casefold().strip()
    match = re.match(r"what\s+does\s+(?P<subj>.+?)\s+orbit\s*\??\s*$", low)
    if not match:
        return None
    subject_phrase = _normalize_subject_phrase(match.group("subj"))
    if not subject_phrase:
        return None
    if "who" in _tokens(subject_phrase):
        return None
    return subject_phrase


def _parse_generic_who_query(query):
    if not isinstance(query, str):
        return None
    low = query.casefold().strip()
    match = re.match(r"who\s+(?P<verb>[a-z]+)\s+(?P<subj>.+?)\s*\??\s*$", low)
    if not match:
        return None
    base = _GENERIC_QUERY_PAST_TO_BASE.get(match.group("verb"))
    if not base:
        return None
    subject_phrase = _normalize_subject_phrase(match.group("subj"))
    if not subject_phrase:
        return None
    if "who" in _tokens(subject_phrase):
        return None
    return base, subject_phrase


def _generic_verb_alternation(forms):
    return r"(?:" + r"|".join(re.escape(v) for v in forms) + r")"


def _relation_patterns(kind, subj_pat, base=None):
    if kind == "capital":
        _desc = r"(?:\s+city)?(?:\s+and\s+(?:the\s+)?(?:largest|most\s+populous)\s+city)?"
        return [
            r"(?P<actor>.+?)\bis\s+the\s+capital"
            + _desc +
            r"\s+of\s+" + subj_pat + r"\s*[.!]\s*$",
            r"\bthe\s+capital" + _desc + r"\s+of\s+" + subj_pat
            + r"\s+is\s+(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            subj_pat + r"\s*['\u2019]s\s+capital" + _desc + r"\s+is\s+"
            r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
        ]
    if kind == "discovery":
        return [
            r"(?P<actor>.+?)\bdiscovered\b\s+" + subj_pat + r"\s*[.!]\s*$",
            subj_pat + r"\s+was\s+discovered(?:\s+in\s+\d{4})?\s+by\s+"
            r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
        ]
    if kind == "orbit":
        return [
            r".*?" + subj_pat + r"\s+orbits?\s+(?:the\s+|a\s+|an\s+)?"
            r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            r".*?" + subj_pat + r"\s+is\s+orbiting\s+(?:the\s+|a\s+|an\s+)?"
            r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            r"(?:the\s+|a\s+|an\s+)?(?P<actor>[^.!?]+?)\s+(?:is|was)\s+orbited\s+by\s+"
            r"(?:the\s+|a\s+|an\s+)?" + subj_pat + r"\s*[.!]\s*$",
        ]
    if kind == "generic":
        active_forms = _GENERIC_ACTIVE_FORMS.get(base, ())
        passive_forms = _GENERIC_PASSIVE_FORMS.get(base, ())
        patterns = []
        if active_forms:
            patterns.append(
                r"(?P<actor>.+?)\b" + _generic_verb_alternation(active_forms)
                + r"\b\s+" + subj_pat + r"\s*[.!]\s*$"
            )
        if passive_forms:
            patterns.append(
                subj_pat + r"\s+was\s+" + _generic_verb_alternation(passive_forms)
                + r"(?:\s+in\s+\d{4})?\s+by\s+(?P<actor>[^.!?]+?)\s*[.!]\s*$"
            )
        return patterns
    return []


def _relation_context(sentence, kind, subject_phrase, *, reliable):
    text = sentence.strip()
    if not text or "?" in text or not _is_complete_sentence(text):
        return None, None, None
    if reliable and (_is_fragmentary_sentence(text) or _is_unreliable_sentence(text)):
        return None, None, None
    low = text.casefold()
    if kind == "capital":
        if "capital punishment" in low or "capital" not in _tokens(text):
            return None, None, None
    if not subject_phrase or not isinstance(subject_phrase, str):
        return None, None, None
    subj_pat = _subject_pattern(subject_phrase)
    if not subj_pat:
        return None, None, None
    return text, low, subj_pat


def _first_actor_match(text, kind, subj_pat, base=None):
    for pattern in _relation_patterns(kind, subj_pat, base):
        match = re.match(pattern, text, re.IGNORECASE)
        if match and _TOKEN_RE.search(match.group("actor")):
            return match.group("actor")
    return None


def _relation_negative_patterns(kind, subj_pat, base=None):
    _neg = r"(?:not\s+|n['\u2019]t\s+|never\s+)"
    _aux_do = r"(?:did|do|does)"
    _aux_do_contract = r"(?:did|do|does)n['\u2019]t\s+"
    _be_contract = r"(?:is|are|was|were)n['\u2019]t\s+"
    _was_contract = r"(?:was|were)n['\u2019]t\s+"
    if kind == "capital":
        _be = r"(?:is|are|was|were)"
        _desc = r"(?:\s+city)?(?:\s+and\s+(?:the\s+)?(?:largest|most\s+populous)\s+city)?"
        return [
            r"(?P<actor>.+?)\b" + _be + r"\s+" + _neg + r"the\s+capital"
            + _desc +
            r"\s+of\s+" + subj_pat + r"\s*[.!]\s*$",
            r"(?P<actor>.+?)\b" + _be_contract + r"the\s+capital"
            + _desc +
            r"\s+of\s+" + subj_pat + r"\s*[.!]\s*$",
            r"\bthe\s+capital" + _desc + r"\s+of\s+" + subj_pat
            + r"\s+" + _be + r"\s+" + _neg + r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            r"\bthe\s+capital" + _desc + r"\s+of\s+" + subj_pat
            + r"\s+" + _be_contract + r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            subj_pat + r"\s*['\u2019]s\s+capital" + _desc + r"\s+"
            + _be + r"\s+" + _neg + r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            subj_pat + r"\s*['\u2019]s\s+capital" + _desc + r"\s+"
            + _be_contract + r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
        ]
    if kind == "discovery":
        return [
            r"(?P<actor>.+?)\b" + _aux_do + r"\s+" + _neg + r"discover\b\s+"
            + subj_pat + r"\s*[.!]\s*$",
            r"(?P<actor>.+?)\b" + _aux_do_contract + r"discover\b\s+"
            + subj_pat + r"\s*[.!]\s*$",
            r"(?P<actor>.+?)\bnever\s+discovered\b\s+" + subj_pat + r"\s*[.!]\s*$",
            subj_pat + r"\s+(?:was|were)\s+" + _neg
            + r"discovered(?:\s+in\s+\d{4})?\s+by\s+"
            r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            subj_pat + r"\s+" + _was_contract
            + r"discovered(?:\s+in\s+\d{4})?\s+by\s+"
            r"(?P<actor>[^.!?]+?)\s*[.!]\s*$",
        ]
    if kind == "orbit":
        return [
            r".*?" + subj_pat + r"\s+(?:does\s+not\s+|do\s+not\s+|did\s+not\s+|"
            r"doesn['\u2019]t\s+|don['\u2019]t\s+|didn['\u2019]t\s+|never\s+)"
            r"orbits?\s+(?:the\s+|a\s+|an\s+)?(?P<actor>[^.!?]+?)\s*[.!]\s*$",
            r"(?:the\s+|a\s+|an\s+)?(?P<actor>[^.!?]+?)\s+(?:is|was)\s+" + _neg
            + r"orbited\s+by\s+(?:the\s+|a\s+|an\s+)?" + subj_pat + r"\s*[.!]\s*$",
            r"(?:the\s+|a\s+|an\s+)?(?P<actor>[^.!?]+?)\s+" + _was_contract
            + r"orbited\s+by\s+(?:the\s+|a\s+|an\s+)?" + subj_pat + r"\s*[.!]\s*$",
            r"(?:the\s+|a\s+|an\s+)?(?P<actor>[^.!?]+?)\s+is\s+never\s+orbited\s+by\s+"
            r"(?:the\s+|a\s+|an\s+)?" + subj_pat + r"\s*[.!]\s*$",
        ]
    if kind == "generic":
        if base is None:
            return []
        active_forms = _GENERIC_ACTIVE_FORMS.get(base, ())
        passive_forms = _GENERIC_PASSIVE_FORMS.get(base, ())
        patterns = [
            r"(?P<actor>.+?)\b" + _aux_do + r"\s+" + _neg + re.escape(base)
            + r"\b\s+" + subj_pat + r"\s*[.!]\s*$",
            r"(?P<actor>.+?)\b" + _aux_do_contract + re.escape(base)
            + r"\b\s+" + subj_pat + r"\s*[.!]\s*$",
        ]
        if active_forms:
            patterns.append(
                r"(?P<actor>.+?)\bnever\s+" + _generic_verb_alternation(active_forms)
                + r"\b\s+" + subj_pat + r"\s*[.!]\s*$"
            )
        if passive_forms:
            patterns.append(
                subj_pat + r"\s+(?:was|were)\s+" + _neg
                + _generic_verb_alternation(passive_forms)
                + r"(?:\s+in\s+\d{4})?\s+by\s+(?P<actor>[^.!?]+?)\s*[.!]\s*$"
            )
            patterns.append(
                subj_pat + r"\s+" + _was_contract
                + _generic_verb_alternation(passive_forms)
                + r"(?:\s+in\s+\d{4})?\s+by\s+(?P<actor>[^.!?]+?)\s*[.!]\s*$"
            )
        return patterns
    return []


def _first_negative_actor_match(text, kind, subj_pat, base=None):
    for pattern in _relation_negative_patterns(kind, subj_pat, base):
        match = re.match(pattern, text, re.IGNORECASE)
        if match and _TOKEN_RE.search(match.group("actor")):
            return match.group("actor")
    return None


def _extract_relation_negative_slot(sentence, kind, subject_phrase, base=None):
    _text_val, low, subj_pat = _relation_context(
        sentence, kind, subject_phrase, reliable=False
    )
    if _text_val is None or subj_pat is None:
        return None
    raw = _first_negative_actor_match(_text_val, kind, subj_pat, base)
    if raw is None:
        return None
    if _has_embedded_clause(raw):
        return None
    if not _is_resolved_slot(raw):
        return None
    return _canonical_slot(raw) or None


def _extract_relation_slot(sentence, kind, subject_phrase, base=None):
    _text_val, low, subj_pat = _relation_context(sentence, kind, subject_phrase, reliable=False)
    if _text_val is None or subj_pat is None:
        return None
    raw = _first_actor_match(_text_val, kind, subj_pat, base)
    if raw is None:
        return None
    if _has_embedded_clause(raw):
        return None
    if not _is_resolved_slot(raw):
        return None
    return _canonical_slot(raw) or None


def _is_relation_evidence(sentence, kind, subject_phrase, base=None):
    _text_val, low, subj_pat = _relation_context(sentence, kind, subject_phrase, reliable=True)
    if _text_val is None or subj_pat is None:
        return False
    raw = _first_actor_match(_text_val, kind, subj_pat, base)
    if raw is None:
        return False
    if _has_embedded_clause(raw):
        return False
    return _is_resolved_slot(raw)


_KEYWORD_PREDICATES = frozenset((
    "is", "are", "was", "were", "be", "been", "being",
    "has", "have", "had", "having",
    "does", "do", "did", "done",
    "releases", "release", "released", "releasing",
    "shapes", "shape", "shaped", "shaping",
    "dominates", "dominate", "dominated", "dominating",
    "records", "record", "recorded", "recording",
    "uses", "use", "used", "using",
    "contains", "contain", "contained", "containing",
    "includes", "include", "included", "including",
    "provides", "provide", "provided", "providing",
    "produces", "produce", "produced", "producing",
    "generates", "generate", "generated", "generating",
    "causes", "cause", "caused", "causing",
    "involves", "involve", "involved", "involving",
    "requires", "require", "required", "requiring",
    "shows", "show", "showed", "shown", "showing",
    "indicates", "indicate", "indicated", "indicating",
    "follows", "follow", "followed", "following",
    "builds", "build", "built", "building",
    "evidence", "evidences",
    "here", "today", "there",
))


def _has_finite_predicate(sentence):
    try:
        toks = _tokens(sentence)
    except Exception:
        return False
    return bool(toks & _KEYWORD_PREDICATES)


def _is_keyword_evidence(sentence, content_tokens):
    if not content_tokens:
        return False
    text = sentence.strip()
    if not text or "?" in text or not _is_complete_sentence(text):
        return False
    if _is_fragmentary_sentence(text) or _is_unreliable_sentence(text):
        return False
    if not content_tokens <= _tokens(text):
        return False
    if not _has_finite_predicate(text):
        return False
    return True


def _is_keyword_negative_candidate(sentence, content_tokens):
    if not content_tokens:
        return False
    text = sentence.strip()
    if not text or "?" in text or not _is_complete_sentence(text):
        return False
    if _is_fragmentary_sentence(text):
        return False
    low = text.casefold()
    if not _NEGATION_RE.search(low):
        return False
    if not content_tokens <= _tokens(text):
        return False
    if not _has_finite_predicate(text):
        return False
    return True


def _keyword_has_conflict(ranked_all, content_tokens, *, extract_only=False):
    if not content_tokens:
        return False
    positives = False
    negatives = False
    for _score, _order, item, _title, _snippet in ranked_all:
        if not isinstance(item, Mapping):
            continue
        if extract_only:
            evidence = _text(item.get("extract", ""))
        else:
            if isinstance(item, Mapping):
                extract = _text(item.get("extract", ""))
                if extract:
                    evidence = extract
                else:
                    evidence = _evidence_text(item)
            else:
                evidence = ""
        if not evidence:
            continue
        for text in _claim_texts(_truncate_to_verified_boundary(evidence, MAX_CONTENT_CHARS)):
            if _is_keyword_evidence(text, content_tokens):
                positives = True
            elif _is_keyword_negative_candidate(text, content_tokens):
                negatives = True
            if positives and negatives:
                return True
    return False


def _item_texts(item, extract_only):
    if not isinstance(item, Mapping):
        return []
    if extract_only:
        evidence = _text(item.get("extract", ""))
    else:
        evidence = _evidence_text(item)
    if not evidence:
        return []
    return _claim_texts(_truncate_to_verified_boundary(evidence, MAX_CONTENT_CHARS))


def _collect_sentence_claims(ranked, is_evidence, *, extract_only=False):
    claims = []
    by_text = {}
    for source_index, (_score, _order, item, _title, _snippet) in enumerate(ranked, 1):
        if not isinstance(item, Mapping):
            continue
        if not _is_safe_answer_url(_text(item.get("url", ""))):
            continue
        for text in _item_texts(item, extract_only):
            if not is_evidence(text):
                continue
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


def _relation_has_conflict(ranked_all, kind, subject_phrase, base=None, *, extract_only=True):
    positives = []
    negatives = []
    unreliable_candidate = False
    for _score, _order, item, _title, _snippet in ranked_all:
        if not isinstance(item, Mapping):
            continue
        extract = _text(item.get("extract", "")) if extract_only else _evidence_text(item)
        if not extract:
            continue
        for text in _claim_texts(_truncate_to_verified_boundary(extract, MAX_CONTENT_CHARS)):
            slot = _extract_relation_slot(text, kind, subject_phrase, base)
            if slot is not None:
                if _is_relation_evidence(text, kind, subject_phrase, base):
                    positives.append(slot)
                else:
                    unreliable_candidate = True
                continue
            neg_slot = _extract_relation_negative_slot(
                text, kind, subject_phrase, base
            )
            if neg_slot is not None:
                negatives.append(neg_slot)
                continue
    if not positives:
        return False
    distinct = [positives[0]]
    for slot in positives[1:]:
        if any(_same_slot(slot, seen) for seen in distinct):
            continue
        distinct.append(slot)
        if len(distinct) >= 2:
            return True
    if unreliable_candidate:
        return True
    for neg in negatives:
        for pos in positives:
            if _same_slot(neg, pos):
                return True
    return False


def _full_fit_keep(claims):
    kept = []
    lines = []
    used = 0
    for claim in claims:
        citation = _citation(claim["sources"])
        separator = 1 if lines else 0
        capacity = MAX_ANSWER_CHARS - used - separator
        complete_length = len(claim["text"]) + 1 + len(citation)
        if complete_length > capacity:
            continue
        lines.append(f"{claim['text']} {citation}")
        used += separator + complete_length
        kept.append(claim)
    return "\n".join(lines), kept


def _full_answer_text(claims):
    return _full_fit_keep(claims)[0]


def _cap_keep_to_max(kept, max_results):
    if not kept:
        return [], []
    used_sorted = sorted({src for claim in kept for src in claim["sources"]})
    capped = used_sorted[:max_results]
    if not capped:
        return [], []
    capped_set = set(capped)
    filtered = []
    for claim in kept:
        remaining = [src for src in claim["sources"] if src in capped_set]
        if not remaining:
            continue
        filtered.append({"text": claim["text"], "sources": list(remaining)})
    if not filtered:
        return [], []
    answer = _full_answer_text(filtered)
    if not answer:
        return [], []
    _, refit = _full_fit_keep(filtered)
    if not refit:
        return [], []
    return answer, refit


def _finalize_answer(kept_in, ranked_by_old_all, max_results):
    if not kept_in:
        return None
    _ans0, _kept0 = _full_fit_keep(kept_in)
    if not _kept0 or not _ans0:
        return None
    _ans1, _kept1 = _cap_keep_to_max(_kept0, max_results)
    if not _kept1 or not _ans1:
        return None
    _used = sorted({src for claim in _kept1 for src in claim["sources"]})
    if not _used or len(_used) > max_results or len(_used) > MAX_RESULTS:
        return None
    _remap = {old: new for new, old in enumerate(_used, 1)}
    for claim in _kept1:
        claim["sources"] = [_remap[src] for src in claim["sources"]]
    _answer = _full_answer_text(_kept1)
    if not _answer or len(_answer) > MAX_ANSWER_CHARS:
        return None
    _sources = []
    for old in _used:
        _item, _title = ranked_by_old_all[old]
        _url = _text(_item.get("url", ""))
        if not _is_safe_answer_url(_url):
            return None
        _sources.append({
            "index": _remap[old],
            "title": _title[:MAX_TITLE_CHARS],
            "url": _url,
        })
    if not _sources:
        return None
    return _answer, _sources


@result_operation
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
        _qfold = query.strip().casefold()
    except Exception:
        _qfold = ""
    if _qfold and _NEGATION_RE.search(_qfold):
        return {"error": {"code": _INSUFFICIENT}}

    try:
        response = search(query.strip())
    except Exception as error:
        return _error_result(_map_error(error))

    if isinstance(response, Mapping) and response.get("error") is not None:
        return _error_result(_map_error(response.get("error")))
    if isinstance(response, Mapping) and response.get("ok") is False:
        upstream_error = response.get("error")
        if upstream_error is None:
            return _error_result(URL_BLOCKED)
        return _error_result(_map_error(upstream_error))
    results = response.get("results") if isinstance(response, Mapping) else None
    if not isinstance(results, (list, tuple)):
        return _error_result(URL_BLOCKED)
    if not results:
        return {"error": {"code": _INSUFFICIENT}}

    ranked_all = _ranked_results(results, _tokens(query), MAX_RESULTS)
    ranked_all = [
        row for row in ranked_all
        if isinstance(row[2], Mapping)
        and _is_safe_answer_url(_text(row[2].get("url", "")))
    ]
    if not ranked_all:
        return {"error": {"code": _INSUFFICIENT}}

    ranked_by_old_all = {}
    for index, (_score, _order, item, title, _snippet) in enumerate(ranked_all, 1):
        ranked_by_old_all[index] = (item, title)

    def _finish(gated):
        if not gated:
            return {"error": {"code": _INSUFFICIENT}}
        finalized = _finalize_answer(gated, ranked_by_old_all, max_results)
        if finalized is None:
            return {"error": {"code": _INSUFFICIENT}}
        answer, sources = finalized
        return {"answer": answer, "sources": sources}

    query_terms = _tokens(query)
    if _is_capital_query(query_terms):
        subject_phrase = _parse_capital_query(query)
        if not subject_phrase:
            return {"error": {"code": _INSUFFICIENT}}
        if _relation_has_conflict(ranked_all, "capital", subject_phrase, extract_only=True):
            return {"error": {"code": _INSUFFICIENT}}
        gated = _collect_sentence_claims(
            ranked_all,
            lambda text: _is_relation_evidence(text, "capital", subject_phrase),
            extract_only=True,
        )
        return _finish(gated)
    elif _is_discovery_query(query_terms):
        subject_phrase = _discovery_subject_phrase(query)
        if _relation_has_conflict(ranked_all, "discovery", subject_phrase, extract_only=True):
            return {"error": {"code": _INSUFFICIENT}}
        gated = _collect_sentence_claims(
            ranked_all,
            lambda text: _is_relation_evidence(text, "discovery", subject_phrase),
            extract_only=True,
        )
        return _finish(gated)
    else:
        orbit_subject = _parse_orbit_query(query)
        if orbit_subject:
            if _relation_has_conflict(ranked_all, "orbit", orbit_subject, extract_only=True):
                return {"error": {"code": _INSUFFICIENT}}
            gated = _collect_sentence_claims(
                ranked_all,
                lambda text: _is_relation_evidence(text, "orbit", orbit_subject),
                extract_only=True,
            )
            return _finish(gated)
        generic_parsed = _parse_generic_who_query(query)
        if generic_parsed is not None:
            base, subject_phrase = generic_parsed
            if _relation_has_conflict(ranked_all, "generic", subject_phrase, base, extract_only=False):
                return {"error": {"code": _INSUFFICIENT}}
            gated = _collect_sentence_claims(
                ranked_all,
                lambda text: _is_relation_evidence(text, "generic", subject_phrase, base),
                extract_only=False,
            )
            return _finish(gated)
        if _is_interrogative_query(query):
            return {"error": {"code": _INSUFFICIENT}}
        content_tokens = _content_query_tokens(query)
        if not content_tokens:
            return {"error": {"code": _INSUFFICIENT}}
        if _keyword_has_conflict(ranked_all, content_tokens, extract_only=False):
            return {"error": {"code": _INSUFFICIENT}}
        gated = _collect_sentence_claims(
            ranked_all,
            lambda text: _is_keyword_evidence(text, content_tokens),
            extract_only=False,
        )
        return _finish(gated)


MAX_HOPS = 2
MAX_CANDIDATES_PER_HOP = MAX_RESULTS
_BORN_AUTHOR_RE = re.compile(r"^\s*where\s+was\s+the\s+(author|writer|creator|founder|inventor|director)\s+of\s+(.+?)\s+born\s*\??\s*$", re.IGNORECASE)
_BRIDGE_VERB_RE = re.compile(r"^\s*(?P<bridge>.+?)\s+(wrote|found|founded|created|designed|invented|discovered|directed)\b", re.IGNORECASE)
_BORN_ROLE_VERBS = {
    "author": "wrote",
    "writer": "wrote",
    "creator": "created",
    "founder": "founded",
    "inventor": "invented",
    "director": "directed",
}


def decompose_query(query):
    if not isinstance(query, str):
        return [query]
    match = _BORN_AUTHOR_RE.match(query)
    if match:
        role = match.group(1).casefold()
        verb = _BORN_ROLE_VERBS.get(role, "")
        subject = match.group(2).strip()
        if not verb or not subject:
            stripped = query.strip()
            return [stripped if stripped else query]
        return ["Who " + verb + " " + subject + "?", "{bridge} born"]
    stripped = query.strip()
    return [stripped if stripped else query]


def extract_bridge_entity(answer_text):
    try:
        if not isinstance(answer_text, str):
            return ""
        first = ""
        for line in answer_text.splitlines():
            if line.strip():
                first = line
                break
        if not first:
            return ""
        cleaned = re.sub(r"(?:\s*\[\d+\])+\s*$", "", first)
        cleaned = cleaned.strip()
        while cleaned.endswith("."):
            cleaned = cleaned[:-1].strip()
        if not cleaned:
            return ""
        match = _BRIDGE_VERB_RE.match(cleaned)
        if not match:
            return ""
        candidate = match.group("bridge").strip()
        if not candidate:
            return ""
        tokens = _TOKEN_RE.findall(candidate)
        if not 1 <= len(tokens) <= 6:
            return ""
        for token in tokens:
            if token.casefold() in _UNRESOLVED_SLOTS:
                return ""
        _bridge_token_re = re.compile(r"[A-Za-z][\w\.\x27-]*")
        for token in tokens:
            if not _bridge_token_re.fullmatch(token):
                return ""
            if not token[0].isupper():
                return ""
        return candidate
    except Exception:
        return ""


_RESEARCH_MAX_QUERY = 2000
_RESEARCH_MAX_BINDING = 512
_RESEARCH_MAX_STEPS = 8
_RESEARCH_MIN_HOPS = 1
_RESEARCH_MAX_HOPS = 4
_RESEARCH_MIN_SEARCHES = 1
_RESEARCH_MAX_SEARCHES = 8
_RESEARCH_CHAIN_KIND = "compositional"
_RESEARCH_ROLE_TO_RELATION = {
    "author": ("generic", "write"),
    "writer": ("generic", "write"),
    "creator": ("generic", "create"),
    "founder": ("generic", "found"),
    "inventor": ("generic", "invent"),
    "designer": ("generic", "design"),
    "discoverer": ("discovery", None),
}
_RESEARCH_BASE_TO_PAST = {
    "write": "wrote",
    "invent": "invented",
    "found": "founded",
    "create": "created",
    "design": "designed",
    "discover": "discovered",
}
_RESEARCH_ALLOWED_KINDS = frozenset(("capital", "discovery", "orbit", "generic", "birth"))
_RESEARCH_GENERIC_BASES = frozenset(("write", "invent", "found", "create", "design"))
_RESEARCH_COMPARISON_TOKENS = frozenset((
    "than", "compared", "comparing", "comparison", "versus", "vs",
    "more", "most", "less", "least",
    "bigger", "biggest", "taller", "tallest", "larger", "largest",
    "smaller", "smallest", "better", "best", "worse", "worst",
    "higher", "highest", "lower", "lowest", "greater", "greatest",
    "earlier", "earliest", "later", "latest",
))
_RESEARCH_SCOPE_TOKENS = frozenset((
    "all", "every", "each", "any", "some", "several", "many", "few",
    "both", "either", "neither", "always", "never", "only", "just", "even",
))
_RESEARCH_OUTER_WHO_RE = re.compile(
    r"^\s*who\s+(?P<verb>[a-z]+)\s+(?P<inner>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_OUTER_CAPITAL_RE = re.compile(
    r"^\s*(?:what|which)\s+is\s+the\s+capital\s+(?:city\s+)?of\s+(?P<inner>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_OUTER_ORBIT_RE = re.compile(
    r"^\s*what\s+does\s+(?P<inner>.+?)\s+orbit\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_NP_CAPITAL_RE = re.compile(
    r"^\s*the\s+capital\s+(?:city\s+)?of\s+(?P<inner>.+?)\s*$",
    re.IGNORECASE,
)
_RESEARCH_NP_ORBIT_BODY_RE = re.compile(
    r"^\s*the\s+body\s+orbited\s+by\s+(?P<inner>.+?)\s*$",
    re.IGNORECASE,
)
_RESEARCH_NP_ROLE_RE = re.compile(
    r"^\s*the\s+(?P<role>author|writer|creator|founder|inventor|designer|discoverer)\s+of\s+(?P<inner>.+?)\s*$",
    re.IGNORECASE,
)
_RESEARCH_PLACEHOLDER_RE = re.compile(r"\{s(\d+)\}")
_RESEARCH_CHAIN_FACETS = "facets"
_RESEARCH_CHAIN_COMPARISON = "comparison"
_RESEARCH_CHAIN_INTERSECTION = "intersection"
_RESEARCH_ALLOWED_CHAIN_KINDS = frozenset((
    "compositional", "facets", "comparison", "intersection",
))
_RESEARCH_PLURAL_CAPITAL_RE = re.compile(
    r"^\s*what\s+are\s+the\s+capitals\s+of\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_COMPARE_CAPITAL_RE = re.compile(
    r"^\s*compare\s+the\s+capitals\s+of\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)\s*\.?\s*$",
    re.IGNORECASE,
)
_RESEARCH_AUTHOR_INTERSECT_RE = re.compile(
    r"^\s*who\s+both\s+(?P<v1>[a-z]+)\s+(?P<s1>.+?)\s+and\s+(?P<v2>[a-z]+)\s+(?P<s2>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_CAPITAL_INTERSECT_RE = re.compile(
    r"^\s*which\s+city\s+is\s+the\s+capital\s+of\s+both\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_CONJUNCTION_RE = re.compile(r"\b(and|or)\b", re.IGNORECASE)
_RESEARCH_BORN_RE = re.compile(
    r"^\s*(?P<wh>when|where)\s+was\s+(?P<inner>.+?)\s+born\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_YEAR_SUFFIX_RE = re.compile(
    r"^\s*(?P<base>.+?)\s+in\s+(?P<year>\d{4})\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_BORN_COMPARE_RE = re.compile(
    r"^\s*was\s+(?P<a>.+?)\s+born\s+(?P<comp>before|after)\s+(?P<b>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_BIRTH_GAP_RE = re.compile(
    r"^\s*how\s+many\s+years\s+between\s+the\s+births\s+of\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)\s*\??\s*$",
    re.IGNORECASE,
)
_RESEARCH_FOUR_DIGIT_RE = re.compile(r"^\d{4}$")
_RESEARCH_TEMPORAL_COMPARE_REASON = "unsupported_temporal_compare"
_RESEARCH_ARITHMETIC_REASON = "unsupported_arithmetic"
_RESEARCH_BIRTH_KIND = "birth"
_RESEARCH_BIRTH_FACETS = frozenset(("place", "date"))


def _research_new_unsupported(query, max_hops, max_searches):
    return {
        "status": "unsupported",
        "chain_kind": "none",
        "query": query,
        "max_hops": max_hops,
        "max_searches": max_searches,
        "steps": [],
        "reason": "unsupported",
    }


def _research_attach_candidates(plan_dict, max_hops, max_searches):
    try:
        if not isinstance(plan_dict, dict):
            return plan_dict
        if plan_dict.get("status") != "planned":
            return plan_dict
        try:
            _ms = plan_dict.get("max_searches", max_searches)
            if type(_ms) is not int or not 1 <= _ms <= 8:
                _ms = max_searches
            _total = 5 * _ms
        except Exception:
            _total = 40
        plan_dict["max_candidates_per_call"] = 5
        plan_dict["candidates_per_call"] = 5
        plan_dict["candidate_limit"] = 5
        plan_dict["max_candidates_total"] = _total
        plan_dict["candidates_total"] = _total
        plan_dict["total_result_limit"] = _total
        plan_dict["candidates_considered"] = 0
        return plan_dict
    except Exception:
        return plan_dict


def _research_conjoined_literal_blocked(literal):
    try:
        if not isinstance(literal, str) or not literal:
            return False
        if "{" in literal or "}" in literal:
            return False
        return _RESEARCH_CONJUNCTION_RE.search(literal) is not None
    except Exception:
        return False


def _research_step_depth(steps, depends):
    try:
        if not depends:
            return 1
        by_id = {s.get("id"): s.get("depth") for s in steps}
        depths = [by_id[d] for d in depends if d in by_id]
        if not depths:
            return None
        if any(type(d) is not int for d in depths):
            return None
        return 1 + max(depths)
    except Exception:
        return None


def _research_append_step(steps, query_template, relation, depends):
    try:
        if not isinstance(query_template, str) or not query_template:
            return None
        if len(query_template) > _RESEARCH_MAX_QUERY:
            return None
        if len(steps) >= _RESEARCH_MAX_STEPS:
            return None
        if not isinstance(depends, list):
            return None
        by_id = {s.get("id") for s in steps}
        for dep in depends:
            if dep not in by_id:
                return None
        depth = _research_step_depth(steps, depends)
        if depth is None:
            return None
        step_id = "s%d" % (len(steps) + 1)
        steps.append({
            "id": step_id,
            "depth": depth,
            "depends_on": list(depends),
            "query_template": query_template,
            "grounding_template": query_template,
            "relation": dict(relation),
            "emit": False,
        })
        return "{%s}" % step_id
    except Exception:
        return None


def _research_operand_ref(text, steps):
    try:
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        if not stripped or len(stripped) > _RESEARCH_MAX_BINDING:
            return None
        if "{" in stripped or "}" in stripped or "?" in stripped:
            return None
        if _RESEARCH_CONJUNCTION_RE.search(" " + stripped + " "):
            # Operands themselves must not contain further conjunctions.
            # Allow only the top-level split; nested conjunction unsupported.
            pass
            # Fall through to NP parse which will reject via literal checks.
        ref = _research_parse_np_to_steps(stripped, steps)
        if ref is None:
            return None
        if len(steps) > _RESEARCH_MAX_STEPS:
            return None
        # Operands must not be bare conjoined literals (three-way splits fail).
        try:
            if "{" not in ref and _research_conjoined_literal_blocked(ref):
                return None
        except Exception:
            return None
        return ref
    except Exception:
        return None


def _research_ref_depends(ref, steps):
    try:
        if not isinstance(ref, str):
            return None
        found = ["s%d" % int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(ref)]
        by_id = {s.get("id") for s in steps}
        for dep in found:
            if dep not in by_id:
                return None
        # Exact in-order: refs only use existing ids.
        return found
    except Exception:
        return None


def _research_try_facets(stripped, max_hops, max_searches):
    try:
        if ";" not in stripped:
            return None
        parts = [p.strip() for p in stripped.split(";")]
        if not 2 <= len(parts) <= 4:
            return None
        for part in parts:
            if not part or len(part) > _RESEARCH_MAX_QUERY:
                return None
            if "{" in part or "}" in part:
                return None
            if ";" in part:
                return None
        combined = []
        for part in parts:
            sub = plan_research_query(part, max_hops=max_hops, max_searches=max_searches)
            if not isinstance(sub, dict) or sub.get("status") != "planned":
                return None
            if sub.get("chain_kind") != _RESEARCH_CHAIN_KIND:
                return None
            sub_steps = sub.get("steps")
            if not isinstance(sub_steps, list) or not sub_steps:
                return None
            offset = len(combined)
            id_map = {}
            for index, row in enumerate(sub_steps, 1):
                old_id = "s%d" % index
                new_id = "s%d" % (offset + index)
                id_map[old_id] = new_id
            for row in sub_steps:
                try:
                    template = row.get("query_template")
                    grounding = row.get("grounding_template")
                    depends = row.get("depends_on")
                    relation = row.get("relation")
                    retr = row.get("retrieval_template")
                    tcond = row.get("temporal_condition")
                except Exception:
                    return None
                new_depends = []
                for dep in depends:
                    if dep not in id_map:
                        return None
                    new_depends.append(id_map[dep])
                new_template = template
                new_grounding = grounding
                new_retr = retr
                for old_id, new_id in id_map.items():
                    num_old = old_id[1:]
                    num_new = new_id[1:]
                    new_template = new_template.replace("{s%s}" % num_old, "{s%s}" % num_new)
                    new_grounding = new_grounding.replace("{s%s}" % num_old, "{s%s}" % num_new)
                    if isinstance(new_retr, str):
                        new_retr = new_retr.replace("{s%s}" % num_old, "{s%s}" % num_new)
                depth = _research_step_depth(combined, new_depends)
                if depth is None:
                    return None
                new_id = id_map[row.get("id")]
                if new_id != "s%d" % (len(combined) + 1):
                    return None
                entry = {
                    "id": new_id,
                    "depth": depth,
                    "depends_on": list(new_depends),
                    "query_template": new_template,
                    "grounding_template": new_grounding,
                    "relation": dict(relation),
                    "emit": bool(row.get("emit")),
                }
                if isinstance(retr, str) and retr:
                    if len(new_retr) > _RESEARCH_MAX_QUERY:
                        return None
                    entry["retrieval_template"] = new_retr
                if isinstance(tcond, dict) and tcond:
                    # Closed: only year string exactly four digits.
                    try:
                        keys = set(tcond)
                    except Exception:
                        return None
                    if keys != {"year"}:
                        return None
                    yv = tcond.get("year")
                    if not _research_is_four_digit_year(yv):
                        return None
                    entry["temporal_condition"] = {"year": yv}
                combined.append(entry)
                if len(combined) > _RESEARCH_MAX_STEPS:
                    return None
        if len(combined) > _RESEARCH_MAX_STEPS:
            return None
        # Facet terminals keep emit True; intermediates False (from sub-plans).
        return {
            "status": "planned",
            "chain_kind": _RESEARCH_CHAIN_FACETS,
            "query": stripped,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "steps": combined,
            "reason": "planned",
        }
    except Exception:
        return None


def _research_try_comparison(stripped, max_hops, max_searches):
    try:
        match = _RESEARCH_PLURAL_CAPITAL_RE.match(stripped)
        kind_match = "plural"
        if match is None:
            match = _RESEARCH_COMPARE_CAPITAL_RE.match(stripped)
            kind_match = "compare"
        if match is None:
            return None
        text_a = match.group("a").strip()
        text_b = match.group("b").strip()
        if not text_a or not text_b:
            return None
        steps = []
        ref_a = _research_operand_ref(text_a, steps)
        if ref_a is None:
            return None
        # Snapshot depths before second operand so cross-deps stay in-order.
        ref_b = _research_operand_ref(text_b, steps)
        if ref_b is None:
            return None
        depends_a = _research_ref_depends(ref_a, steps)
        depends_b = _research_ref_depends(ref_b, steps)
        if depends_a is None or depends_b is None:
            return None
        query_a = _research_capital_query(ref_a)
        query_b = _research_capital_query(ref_b)
        placeholder_a = _research_append_step(
            steps, query_a, {"kind": "capital"}, depends_a
        )
        if placeholder_a is None:
            return None
        # Recompute depends_b against grown steps (ids unchanged, still valid).
        depends_b = _research_ref_depends(ref_b, steps)
        if depends_b is None:
            return None
        # Guard: second operand ref must still resolve (no mutation of ids).
        placeholder_b = _research_append_step(
            steps, query_b, {"kind": "capital"}, depends_b
        )
        if placeholder_b is None:
            return None
        for row in steps:
            row["emit"] = False
        # Mark facet terminals (steps with no dependents) emit True.
        depended = set()
        for row in steps:
            for dep in row.get("depends_on", []):
                depended.add(dep)
        for row in steps:
            if row.get("id") not in depended:
                row["emit"] = True
        # Both capital terminals must emit.
        if sum(1 for r in steps if r.get("emit") is True) < 2:
            return None
        _ = kind_match
        return {
            "status": "planned",
            "chain_kind": _RESEARCH_CHAIN_COMPARISON,
            "query": stripped,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "steps": steps,
            "reason": "planned",
        }
    except Exception:
        return None


def _research_try_intersection(stripped, max_hops, max_searches):
    try:
        match = _RESEARCH_AUTHOR_INTERSECT_RE.match(stripped)
        if match is not None:
            verb1 = match.group("v1").casefold()
            subj1 = match.group("s1").strip()
            verb2 = match.group("v2").casefold()
            subj2 = match.group("s2").strip()
            if not subj1 or not subj2:
                return None
            base1 = _GENERIC_QUERY_PAST_TO_BASE.get(verb1)
            base2 = _GENERIC_QUERY_PAST_TO_BASE.get(verb2)
            if base1 is None or base2 is None:
                return None
            past1 = _RESEARCH_BASE_TO_PAST.get(base1, "")
            past2 = _RESEARCH_BASE_TO_PAST.get(base2, "")
            if not past1 or not past2:
                return None
            steps = []
            ref1 = _research_operand_ref(subj1, steps)
            if ref1 is None:
                return None
            ref2 = _research_operand_ref(subj2, steps)
            if ref2 is None:
                return None
            depends1 = _research_ref_depends(ref1, steps)
            depends2 = _research_ref_depends(ref2, steps)
            if depends1 is None or depends2 is None:
                return None
            query1 = _research_who_query(past1, ref1)
            if _research_append_step(
                steps, query1, {"kind": "generic", "base": base1}, depends1
            ) is None:
                return None
            depends2 = _research_ref_depends(ref2, steps)
            if depends2 is None:
                return None
            query2 = _research_who_query(past2, ref2)
            if _research_append_step(
                steps, query2, {"kind": "generic", "base": base2}, depends2
            ) is None:
                return None
            for row in steps:
                row["emit"] = False
            depended = set()
            for row in steps:
                for dep in row.get("depends_on", []):
                    depended.add(dep)
            for row in steps:
                if row.get("id") not in depended:
                    row["emit"] = True
            if sum(1 for r in steps if r.get("emit") is True) < 2:
                return None
            return {
                "status": "planned",
                "chain_kind": _RESEARCH_CHAIN_INTERSECTION,
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": steps,
                "reason": "planned",
            }
        cap_match = _RESEARCH_CAPITAL_INTERSECT_RE.match(stripped)
        if cap_match is not None:
            text_a = cap_match.group("a").strip()
            text_b = cap_match.group("b").strip()
            if not text_a or not text_b:
                return None
            steps = []
            ref_a = _research_operand_ref(text_a, steps)
            if ref_a is None:
                return None
            ref_b = _research_operand_ref(text_b, steps)
            if ref_b is None:
                return None
            depends_a = _research_ref_depends(ref_a, steps)
            depends_b = _research_ref_depends(ref_b, steps)
            if depends_a is None or depends_b is None:
                return None
            query_a = _research_capital_query(ref_a)
            if _research_append_step(
                steps, query_a, {"kind": "capital"}, depends_a
            ) is None:
                return None
            depends_b = _research_ref_depends(ref_b, steps)
            if depends_b is None:
                return None
            query_b = _research_capital_query(ref_b)
            if _research_append_step(
                steps, query_b, {"kind": "capital"}, depends_b
            ) is None:
                return None
            for row in steps:
                row["emit"] = False
            depended = set()
            for row in steps:
                for dep in row.get("depends_on", []):
                    depended.add(dep)
            for row in steps:
                if row.get("id") not in depended:
                    row["emit"] = True
            if sum(1 for r in steps if r.get("emit") is True) < 2:
                return None
            return {
                "status": "planned",
                "chain_kind": _RESEARCH_CHAIN_INTERSECTION,
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": steps,
                "reason": "planned",
            }
        return None
    except Exception:
        return None


def _research_is_four_digit_year(value):
    try:
        if not isinstance(value, str):
            return False
        if _RESEARCH_FOUR_DIGIT_RE.match(value) is None:
            return False
        return True
    except Exception:
        return False


def _research_birth_query(subject_ref):
    return "%s born" % subject_ref


def _research_try_born(stripped, max_hops, max_searches):
    try:
        m = _RESEARCH_BORN_RE.match(stripped)
        if m is None:
            return None
        wh = m.group("wh").casefold()
        inner = m.group("inner").strip()
        if not inner:
            return None
        facet = "date" if wh == "when" else "place"
        if facet not in _RESEARCH_BIRTH_FACETS:
            return None
        steps = []
        inner_ref = _research_parse_np_to_steps(inner, steps)
        if inner_ref is None:
            return None
        if len(steps) >= _RESEARCH_MAX_STEPS:
            return None
        if "{" not in inner_ref and _research_conjoined_literal_blocked(inner_ref):
            return None
        depends = []
        if "{" in inner_ref:
            try:
                nums = [int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(inner_ref)]
            except Exception:
                return None
            by_id = {s.get("id") for s in steps}
            depends = ["s%d" % n for n in nums]
            for d in depends:
                if d not in by_id:
                    return None
            if sorted(depends) != sorted(set(depends)):
                return None
            # In-order: inner_ref must only use existing ids in order.
            try:
                max_num = max(nums) if nums else 0
                if max_num != len(steps):
                    # Inner parse builds linear chain; allow only tail dep.
                    # General case: depend on all referenced ids.
                    pass
            except Exception:
                return None
            # For linear inner chains, depend on last step only.
            # Collect exact dep list from ref.
            depends = ["s%d" % n for n in sorted(set(nums))]
            # Require deps are exactly 1..len(steps) prefix for compositional.
            # Simplify: depend on immediate predecessor when linear.
            if len(steps) >= 1:
                # Use last step as sole dep when inner_ref is single placeholder chain.
                # If multiple placeholders (should not happen for NP), keep all.
                if len(depends) == 1:
                    pass
        else:
            # Bare literal inner without steps: direct birth on a literal NP
            # compiles to ONE supported keyword grounding step (depth 1).
            if not _research_valid_literal(inner_ref):
                return None
            depends = []
        birth_q = _research_birth_query(inner_ref)
        if len(birth_q) > _RESEARCH_MAX_QUERY:
            return None
        # Depth = 1 + max(dep depths)
        depth = _research_step_depth(steps, depends)
        if depth is None:
            return None
        step_id = "s%d" % (len(steps) + 1)
        # Compositional linear depth must equal index.
        if depth != len(steps) + 1:
            return None
        steps.append({
            "id": step_id,
            "depth": depth,
            "depends_on": list(depends),
            "query_template": birth_q,
            "grounding_template": birth_q,
            "relation": {"kind": _RESEARCH_BIRTH_KIND, "facet": facet},
            "emit": True,
        })
        for row in steps[:-1]:
            row["emit"] = False
        return {
            "status": "planned",
            "chain_kind": _RESEARCH_CHAIN_KIND,
            "query": stripped,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "steps": steps,
            "reason": "planned",
        }
    except Exception:
        return None


def _research_try_year_qualified(stripped, max_hops, max_searches):
    try:
        m = _RESEARCH_YEAR_SUFFIX_RE.match(stripped)
        if m is None:
            return None
        base = m.group("base").strip()
        year = m.group("year").strip()
        if not _research_is_four_digit_year(year):
            return None
        if not base:
            return None
        # Base must be an existing supported Who question without qualifier.
        base_q = base.strip()
        if not base_q.endswith("?"):
            base_q = base_q + "?"
        # Validate base via existing generic/discovery parsers.
        parsed = _parse_generic_who_query(base_q)
        base_kind = None
        base_base = None
        if parsed is not None:
            base_base, _norm_subj = parsed
            if base_base not in _RESEARCH_GENERIC_BASES:
                return None
            base_kind = "generic"
            raw_subj = _research_extract_raw_subject(base_kind, base_q, base_base)
            if not raw_subj or not _research_valid_literal(raw_subj):
                return None
        else:
            # Discovery form.
            try:
                toks = _tokens(base_q)
            except Exception:
                return None
            if not _is_discovery_query(toks):
                return None
            raw_subj = _research_extract_raw_subject("discovery", base_q)
            if not raw_subj:
                return None
            if not _research_valid_literal(raw_subj):
                return None
            base_kind = "discovery"
            base_base = None
        # Build single-step plan with distinct retrieval vs grounding.
        retrieval = stripped
        grounding = base_q
        if len(retrieval) > _RESEARCH_MAX_QUERY or len(grounding) > _RESEARCH_MAX_QUERY:
            return None
        if year not in retrieval:
            return None
        if year in grounding:
            return None
        if base_kind == "generic":
            relation = {"kind": "generic", "base": base_base}
        else:
            relation = {"kind": "discovery"}
        step = {
            "id": "s1",
            "depth": 1,
            "depends_on": [],
            "query_template": retrieval,
            "retrieval_template": retrieval,
            "grounding_template": grounding,
            "relation": dict(relation),
            "temporal_condition": {"year": year},
            "emit": True,
        }
        return {
            "status": "planned",
            "chain_kind": _RESEARCH_CHAIN_KIND,
            "query": stripped,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "steps": [step],
            "reason": "planned",
        }
    except Exception:
        return None


def _research_try_temporal_compare(stripped, max_hops, max_searches):
    try:
        m = _RESEARCH_BORN_COMPARE_RE.match(stripped)
        if m is None:
            return None
        raw_a = m.group("a").strip()
        raw_b = m.group("b").strip()
        comp = m.group("comp").casefold()
        if comp not in ("before", "after"):
            return None
        if not raw_a or not raw_b:
            return None
        if "{" in raw_a or "}" in raw_a or "?" in raw_a:
            return None
        if "{" in raw_b or "}" in raw_b or "?" in raw_b:
            return None
        # Operands must be proper resolved names (no conjunctions, no clauses).
        if _research_conjoined_literal_blocked(raw_a):
            return None
        if _research_conjoined_literal_blocked(raw_b):
            return None
        if _has_embedded_clause(raw_a) or _has_embedded_clause(raw_b):
            return None
        if not _is_resolved_slot(raw_a) or not _is_resolved_slot(raw_b):
            return None
        if len(raw_a) > _RESEARCH_MAX_BINDING or len(raw_b) > _RESEARCH_MAX_BINDING:
            return None
        # Two independent date facets.
        q_a = _research_birth_query(raw_a)
        q_b = _research_birth_query(raw_b)
        if len(q_a) > _RESEARCH_MAX_QUERY or len(q_b) > _RESEARCH_MAX_QUERY:
            return None
        steps = [
            {
                "id": "s1",
                "depth": 1,
                "depends_on": [],
                "query_template": q_a,
                "grounding_template": q_a,
                "relation": {"kind": _RESEARCH_BIRTH_KIND, "facet": "date"},
                "emit": True,
            },
            {
                "id": "s2",
                "depth": 1,
                "depends_on": [],
                "query_template": q_b,
                "grounding_template": q_b,
                "relation": {"kind": _RESEARCH_BIRTH_KIND, "facet": "date"},
                "emit": True,
            },
        ]
        return {
            "status": "planned",
            "chain_kind": _RESEARCH_CHAIN_COMPARISON,
            "query": stripped,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "steps": steps,
            "answerable": False,
            "reason": _RESEARCH_TEMPORAL_COMPARE_REASON,
        }
    except Exception:
        return None


def _research_try_arithmetic(stripped, max_hops, max_searches):
    try:
        m = _RESEARCH_BIRTH_GAP_RE.match(stripped)
        if m is None:
            # Generic arithmetic scope: how-many with between/births stays arithmetic.
            try:
                low = stripped.casefold()
            except Exception:
                return None
            if "how many" in low and "between" in low and "birth" in low:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "answerable": False,
                    "reason": _RESEARCH_ARITHMETIC_REASON,
                }
            return None
        return {
            "status": "unsupported",
            "chain_kind": "none",
            "query": stripped,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "steps": [],
            "answerable": False,
            "reason": _RESEARCH_ARITHMETIC_REASON,
        }
    except Exception:
        return None


def _research_strict_hops(value):
    return type(value) is int and _RESEARCH_MIN_HOPS <= value <= _RESEARCH_MAX_HOPS


def _research_strict_searches(value):
    return type(value) is int and _RESEARCH_MIN_SEARCHES <= value <= _RESEARCH_MAX_SEARCHES


def _research_has_comparison_or_scope(text):
    try:
        toks = set(_TOKEN_RE.findall(text.casefold()))
    except Exception:
        return True
    if toks & _RESEARCH_COMPARISON_TOKENS:
        return True
    if toks & _RESEARCH_SCOPE_TOKENS:
        return True
    return False


def _research_valid_literal(raw):
    try:
        if not isinstance(raw, str):
            return False
        stripped = raw.strip()
        if not stripped or len(stripped) > _RESEARCH_MAX_BINDING:
            return False
        if "{" in stripped or "}" in stripped:
            return False
        if "?" in stripped:
            return False
        if _has_embedded_clause(stripped):
            return False
        if _research_has_comparison_or_scope(stripped):
            return False
        if not _is_resolved_slot(stripped):
            return False
        return True
    except Exception:
        return False


def _research_orbit_query(subject_ref):
    return "What does %s orbit?" % subject_ref


def _research_capital_query(subject_ref):
    return "What is the capital of %s?" % subject_ref


def _research_who_query(past_verb, subject_ref):
    return "Who %s %s?" % (past_verb, subject_ref)


def _research_parse_np_to_steps(text, steps):
    try:
        if not isinstance(text, str):
            return None
        stripped = text.strip()
        if not stripped or len(stripped) > _RESEARCH_MAX_QUERY:
            return None
        if "?" in stripped or "{" in stripped or "}" in stripped:
            return None
        if _research_has_comparison_or_scope(stripped):
            return None
        match = _RESEARCH_NP_CAPITAL_RE.match(stripped)
        if match:
            inner = match.group("inner").strip()
            if not inner:
                return None
            inner_ref = _research_parse_np_to_steps(inner, steps)
            if inner_ref is None:
                return None
            if len(steps) >= _RESEARCH_MAX_STEPS:
                return None
            prev = len(steps)
            step_id = "s%d" % (prev + 1)
            query = _research_capital_query(inner_ref)
            if len(query) > _RESEARCH_MAX_QUERY:
                return None
            steps.append({
                "id": step_id,
                "depth": prev + 1,
                "depends_on": [] if prev == 0 else ["s%d" % prev],
                "query_template": query,
                "grounding_template": query,
                "relation": {"kind": "capital"},
                "emit": False,
            })
            return "{%s}" % step_id
        match = _RESEARCH_NP_ORBIT_BODY_RE.match(stripped)
        if match:
            inner = match.group("inner").strip()
            if not inner:
                return None
            inner_ref = _research_parse_np_to_steps(inner, steps)
            if inner_ref is None:
                return None
            if len(steps) >= _RESEARCH_MAX_STEPS:
                return None
            prev = len(steps)
            step_id = "s%d" % (prev + 1)
            query = _research_orbit_query(inner_ref)
            if len(query) > _RESEARCH_MAX_QUERY:
                return None
            steps.append({
                "id": step_id,
                "depth": prev + 1,
                "depends_on": [] if prev == 0 else ["s%d" % prev],
                "query_template": query,
                "grounding_template": query,
                "relation": {"kind": "orbit"},
                "emit": False,
            })
            return "{%s}" % step_id
        match = _RESEARCH_NP_ROLE_RE.match(stripped)
        if match:
            role = match.group("role").casefold()
            inner = match.group("inner").strip()
            if not inner:
                return None
            mapped = _RESEARCH_ROLE_TO_RELATION.get(role)
            if mapped is None:
                return None
            kind, base = mapped
            inner_ref = _research_parse_np_to_steps(inner, steps)
            if inner_ref is None:
                return None
            if len(steps) >= _RESEARCH_MAX_STEPS:
                return None
            if kind == "discovery":
                query = _research_who_query("discovered", inner_ref)
                relation = {"kind": "discovery"}
            else:
                past = _RESEARCH_BASE_TO_PAST.get(base, "")
                if not past:
                    return None
                query = _research_who_query(past, inner_ref)
                relation = {"kind": "generic", "base": base}
            if len(query) > _RESEARCH_MAX_QUERY:
                return None
            prev = len(steps)
            step_id = "s%d" % (prev + 1)
            steps.append({
                "id": step_id,
                "depth": prev + 1,
                "depends_on": [] if prev == 0 else ["s%d" % prev],
                "query_template": query,
                "grounding_template": query,
                "relation": dict(relation),
                "emit": False,
            })
            return "{%s}" % step_id
        # Literal leaf.
        if not _research_valid_literal(stripped):
            return None
        return stripped
    except Exception:
        return None


def plan_research_query(query, max_hops=2, max_searches=4):
    try:
        if not isinstance(query, str):
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": "",
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
        stripped = query.strip()
        # Pure unsupported must not echo credential/control query.
        try:
            _has_ctl = any(ord(c) < 32 for c in query)
        except Exception:
            _has_ctl = False
        try:
            _has_cred = ("://" in stripped and "@" in stripped)
            if not _has_cred and "@" in stripped and "user:" in stripped.casefold():
                _has_cred = True
        except Exception:
            _has_cred = False
        if _has_ctl or _has_cred:
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": "",
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
        if not stripped or len(query) > _RESEARCH_MAX_QUERY or len(stripped) > _RESEARCH_MAX_QUERY:
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": stripped[:_RESEARCH_MAX_QUERY] if isinstance(stripped, str) else "",
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
        try:
            has_mark = re.search(r"\S", stripped) is not None
        except Exception:
            has_mark = True
        if not has_mark:
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
        if "{" in stripped or "}" in stripped:
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
        # Cycle4: explicit multi-facet / comparison / intersection grammars
        # run before generic comparison/scope rejection.
        try:
            if ";" in stripped:
                faceted = _research_try_facets(stripped, max_hops, max_searches)
                if faceted is not None:
                    return faceted
                # Semicolon present but not all fragments fully supported:
                # fail closed, never partially split.
                if len([p for p in stripped.split(";")]) >= 2:
                    return {
                        "status": "unsupported",
                        "chain_kind": "none",
                        "query": stripped,
                        "max_hops": max_hops,
                        "max_searches": max_searches,
                        "steps": [],
                        "reason": "unsupported",
                    }
            compared = _research_try_comparison(stripped, max_hops, max_searches)
            if compared is not None:
                return compared
            intersected = _research_try_intersection(stripped, max_hops, max_searches)
            if intersected is not None:
                return intersected
            born_plan = _research_try_born(stripped, max_hops, max_searches)
            if born_plan is not None:
                return born_plan
            year_plan = _research_try_year_qualified(stripped, max_hops, max_searches)
            if year_plan is not None:
                return year_plan
            tcomp = _research_try_temporal_compare(stripped, max_hops, max_searches)
            if tcomp is not None:
                return tcomp
            arith = _research_try_arithmetic(stripped, max_hops, max_searches)
            if arith is not None:
                return arith
        except Exception:
            pass
        if _research_has_comparison_or_scope(stripped):
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
        steps = []
        # Outer orbit.
        match = _RESEARCH_OUTER_ORBIT_RE.match(stripped)
        if match:
            inner = match.group("inner").strip()
            if not inner:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            inner_ref = _research_parse_np_to_steps(inner, steps)
            if inner_ref is None or len(steps) >= _RESEARCH_MAX_STEPS:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            if "{" not in inner_ref and _research_conjoined_literal_blocked(inner_ref):
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            step_id = "s%d" % (len(steps) + 1)
            query_template = _research_orbit_query(inner_ref)
            if len(query_template) > _RESEARCH_MAX_QUERY:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            depends = [] if not steps else ["s%d" % len(steps)]
            steps.append({
                "id": step_id,
                "depth": len(steps) + 1,
                "depends_on": list(depends),
                "query_template": query_template,
                "grounding_template": query_template,
                "relation": {"kind": "orbit"},
                "emit": True,
            })
            for row in steps[:-1]:
                row["emit"] = False
            return {
                "status": "planned",
                "chain_kind": _RESEARCH_CHAIN_KIND,
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": steps,
                "reason": "planned",
            }
        # Outer capital.
        match = _RESEARCH_OUTER_CAPITAL_RE.match(stripped)
        if match:
            inner = match.group("inner").strip()
            if not inner:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            inner_ref = _research_parse_np_to_steps(inner, steps)
            if inner_ref is None or len(steps) >= _RESEARCH_MAX_STEPS:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            if "{" not in inner_ref and _research_conjoined_literal_blocked(inner_ref):
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            step_id = "s%d" % (len(steps) + 1)
            query_template = _research_capital_query(inner_ref)
            if len(query_template) > _RESEARCH_MAX_QUERY:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            depends = [] if not steps else ["s%d" % len(steps)]
            steps.append({
                "id": step_id,
                "depth": len(steps) + 1,
                "depends_on": list(depends),
                "query_template": query_template,
                "grounding_template": query_template,
                "relation": {"kind": "capital"},
                "emit": True,
            })
            for row in steps[:-1]:
                row["emit"] = False
            return {
                "status": "planned",
                "chain_kind": _RESEARCH_CHAIN_KIND,
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": steps,
                "reason": "planned",
            }
        # Outer Who.
        match = _RESEARCH_OUTER_WHO_RE.match(stripped)
        if match:
            verb = match.group("verb").casefold()
            inner = match.group("inner").strip()
            if not inner:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            if verb == "discovered":
                kind = "discovery"
                base = None
                past = "discovered"
            else:
                base = _GENERIC_QUERY_PAST_TO_BASE.get(verb)
                if base is None:
                    return {
                        "status": "unsupported",
                        "chain_kind": "none",
                        "query": stripped,
                        "max_hops": max_hops,
                        "max_searches": max_searches,
                        "steps": [],
                        "reason": "unsupported",
                    }
                kind = "generic"
                past = _RESEARCH_BASE_TO_PAST.get(base, "")
                if not past:
                    return {
                        "status": "unsupported",
                        "chain_kind": "none",
                        "query": stripped,
                        "max_hops": max_hops,
                        "max_searches": max_searches,
                        "steps": [],
                        "reason": "unsupported",
                    }
            inner_ref = _research_parse_np_to_steps(inner, steps)
            if inner_ref is None or len(steps) >= _RESEARCH_MAX_STEPS:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            if "{" not in inner_ref and _research_conjoined_literal_blocked(inner_ref):
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            step_id = "s%d" % (len(steps) + 1)
            query_template = _research_who_query(past, inner_ref)
            if len(query_template) > _RESEARCH_MAX_QUERY:
                return {
                    "status": "unsupported",
                    "chain_kind": "none",
                    "query": stripped,
                    "max_hops": max_hops,
                    "max_searches": max_searches,
                    "steps": [],
                    "reason": "unsupported",
                }
            depends = [] if not steps else ["s%d" % len(steps)]
            if kind == "discovery":
                relation = {"kind": "discovery"}
            else:
                relation = {"kind": "generic", "base": base}
            steps.append({
                "id": step_id,
                "depth": len(steps) + 1,
                "depends_on": list(depends),
                "query_template": query_template,
                "grounding_template": query_template,
                "relation": relation,
                "emit": True,
            })
            for row in steps[:-1]:
                row["emit"] = False
            return {
                "status": "planned",
                "chain_kind": _RESEARCH_CHAIN_KIND,
                "query": stripped,
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": steps,
                "reason": "planned",
            }
        return {
            "status": "unsupported",
            "chain_kind": "none",
            "query": stripped,
            "max_hops": max_hops,
            "max_searches": max_searches,
            "steps": [],
            "reason": "unsupported",
        }
    except Exception:
        try:
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": query.strip() if isinstance(query, str) else "",
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
        except Exception:
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": "",
                "max_hops": 3,
                "max_searches": 4,
                "steps": [],
                "reason": "unsupported",
            }


_plan_research_query_raw = plan_research_query


def plan_research_query(query, max_hops=2, max_searches=4):
    try:
        _res = _plan_research_query_raw(query, max_hops=max_hops, max_searches=max_searches)
    except Exception:
        try:
            return _plan_research_query_raw(query, max_hops=max_hops, max_searches=max_searches)
        except Exception:
            return {
                "status": "unsupported",
                "chain_kind": "none",
                "query": "",
                "max_hops": max_hops,
                "max_searches": max_searches,
                "steps": [],
                "reason": "unsupported",
            }
    try:
        return _research_attach_candidates(_res, max_hops, max_searches)
    except Exception:
        return _res


def _research_extract_raw_subject(kind, substituted, base=None):
    try:
        if kind == "orbit":
            match = re.match(
                r"^\s*what\s+does\s+(?P<subj>.+?)\s+orbit\s*\??\s*$",
                substituted,
                re.IGNORECASE,
            )
            if not match:
                return ""
            return match.group("subj").strip()
        if kind == "capital":
            match = re.match(
                r"^\s*(?:what|which)\s+is\s+the\s+capital\s+(?:city\s+)?of\s+(?P<subj>.+?)\s*\??\s*$",
                substituted,
                re.IGNORECASE,
            )
            if not match:
                return ""
            return match.group("subj").strip()
        if kind == "discovery":
            match = re.match(
                r"^\s*who\s+discovered\s+(?P<subj>.+?)\s*\??\s*$",
                substituted,
                re.IGNORECASE,
            )
            if not match:
                return ""
            return match.group("subj").strip()
        if kind == "generic":
            if base is None:
                return ""
            past = _RESEARCH_BASE_TO_PAST.get(base, "")
            if not past:
                return ""
            match = re.match(
                r"^\s*who\s+(?P<verb>[a-z]+)\s+(?P<subj>.+?)\s*\??\s*$",
                substituted,
                re.IGNORECASE,
            )
            if not match:
                return ""
            if match.group("verb").casefold() != past.casefold():
                # Accept any past mapping to same base for validation.
                mapped = _GENERIC_QUERY_PAST_TO_BASE.get(
                    match.group("verb").casefold()
                )
                if mapped != base:
                    return ""
            return match.group("subj").strip()
        return ""
    except Exception:
        return ""


def validate_research_plan(plan, max_hops=None, max_searches=None):
    try:
        if not isinstance(plan, dict):
            return False
        allowed_top = frozenset((
            "status", "chain_kind", "query", "max_hops",
            "max_searches", "steps", "reason", "answerable",
            "max_candidates_per_call", "candidates_per_call",
            "candidate_limit", "max_candidates_total",
            "candidates_total", "total_result_limit",
            "candidates_considered",
        ))
        try:
            for key in plan:
                if key not in allowed_top:
                    return False
        except Exception:
            return False
        status = plan.get("status")
        chain_kind = plan.get("chain_kind")
        query = plan.get("query")
        inner_hops = plan.get("max_hops")
        inner_searches = plan.get("max_searches")
        steps = plan.get("steps")
        reason = plan.get("reason")
        answerable = plan.get("answerable", True)
        if status != "planned" or chain_kind not in _RESEARCH_ALLOWED_CHAIN_KINDS:
            return False
        # Executable dependency facets may carry explicit unsupported-computed
        # flag; original planned relations stay closed (reason planned).
        if answerable is True:
            if reason != "planned":
                return False
            if "answerable" in plan:
                # answerable True must be strict bool when present.
                if type(plan.get("answerable")) is not bool:
                    return False
        else:
            if type(answerable) is not bool or answerable is not False:
                return False
            if reason != _RESEARCH_TEMPORAL_COMPARE_REASON:
                return False
            if chain_kind != _RESEARCH_CHAIN_COMPARISON:
                return False
        if not isinstance(query, str) or not query.strip():
            return False
        if len(query) > _RESEARCH_MAX_QUERY or len(query.strip()) > _RESEARCH_MAX_QUERY:
            return False
        try:
            if re.search(r"\S", query) is None:
                return False
        except Exception:
            return False
        if not _research_strict_hops(inner_hops):
            return False
        if not _research_strict_searches(inner_searches):
            return False
        # Strict explicit budgets: type(x) is int BEFORE equality (True==1 fails).
        if max_hops is not None:
            if type(max_hops) is not int:
                return False
            if not _research_strict_hops(max_hops):
                return False
            if max_hops != inner_hops:
                return False
        if max_searches is not None:
            if type(max_searches) is not int:
                return False
            if not _research_strict_searches(max_searches):
                return False
            if max_searches != inner_searches:
                return False
        # Optional known candidate fields strictly validated when present.
        try:
            for _pk in ("max_candidates_per_call", "candidates_per_call", "candidate_limit"):
                if _pk in plan:
                    _pv = plan.get(_pk)
                    if type(_pv) is not int or _pv != 5:
                        return False
            for _tk in ("max_candidates_total", "candidates_total", "total_result_limit"):
                if _tk in plan:
                    _tv = plan.get(_tk)
                    if type(_tv) is not int or _tv != 5 * inner_searches:
                        return False
                    if not 1 <= _tv <= 40:
                        return False
            if "candidates_considered" in plan:
                _ccv = plan.get("candidates_considered")
                if type(_ccv) is not int or not 0 <= _ccv <= 40:
                    return False
        except Exception:
            return False
        if not isinstance(steps, list) or not 1 <= len(steps) <= _RESEARCH_MAX_STEPS:
            return False
        allowed_step_keys = frozenset((
            "id", "depth", "depends_on", "query_template",
            "grounding_template", "relation", "emit",
            "retrieval_template", "temporal_condition",
        ))
        is_compositional = (chain_kind == _RESEARCH_CHAIN_KIND)
        # Collect ids for DAG checks.
        seen_ids = set()
        for index, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                return False
            try:
                for key in step:
                    if key not in allowed_step_keys:
                        return False
            except Exception:
                return False
            expected_id = "s%d" % index
            if step.get("id") != expected_id:
                return False
            seen_ids.add(expected_id)
        # Emit must be True exactly at facet terminals (no dependents).
        depended_ids = set()
        for step in steps:
            depends = step.get("depends_on")
            if not isinstance(depends, list):
                return False
            for dep in depends:
                if not isinstance(dep, str):
                    return False
                depended_ids.add(dep)
        for index, step in enumerate(steps, 1):
            expected_id = "s%d" % index
            if type(step.get("depth")) is not int:
                return False
            depends = step.get("depends_on")
            if not isinstance(depends, list):
                return False
            # In-order DAG: deps must be earlier ids, no dups, no self.
            if len(set(depends)) != len(depends):
                return False
            for dep in depends:
                if dep not in seen_ids:
                    return False
                try:
                    dep_num = int(dep[1:])
                except Exception:
                    return False
                if not 1 <= dep_num < index:
                    return False
            # Declared depth = 1 + max(dep depths).
            try:
                if not depends:
                    expected_depth = 1
                else:
                    dep_depths = []
                    for dep in depends:
                        dep_row = next(s for s in steps if s.get("id") == dep)
                        dep_depths.append(dep_row.get("depth"))
                    if any(type(d) is not int for d in dep_depths):
                        return False
                    expected_depth = 1 + max(dep_depths)
            except Exception:
                return False
            if step.get("depth") != expected_depth:
                return False
            if is_compositional:
                if type(step.get("depth")) is not int or step.get("depth") != index:
                    return False
                if index == 1:
                    if depends != []:
                        return False
                else:
                    if depends != ["s%d" % (index - 1)]:
                        return False
            query_template = step.get("query_template")
            grounding_template = step.get("grounding_template")
            if not isinstance(query_template, str) or not query_template:
                return False
            if not isinstance(grounding_template, str) or not grounding_template:
                return False
            if len(query_template) > _RESEARCH_MAX_QUERY:
                return False
            if len(grounding_template) > _RESEARCH_MAX_QUERY:
                return False
            # Templates must exactly match declared dep IDs.
            try:
                found = [int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(query_template)]
            except Exception:
                return False
            try:
                found_ground = [int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(grounding_template)]
            except Exception:
                return False
            try:
                dep_nums = sorted(int(d[1:]) for d in depends)
            except Exception:
                return False
            if sorted(found) != dep_nums:
                return False
            if sorted(found_ground) != dep_nums:
                return False
            if is_compositional:
                if index == 1:
                    if found or found_ground:
                        return False
                    if "{" in query_template or "}" in query_template:
                        return False
                    if "{" in grounding_template or "}" in grounding_template:
                        return False
                else:
                    if found != [index - 1]:
                        return False
                    if found_ground != [index - 1]:
                        return False
                    cleaned = _RESEARCH_PLACEHOLDER_RE.sub("", query_template)
                    if "{" in cleaned or "}" in cleaned:
                        return False
                    cleaned_ground = _RESEARCH_PLACEHOLDER_RE.sub("", grounding_template)
                    if "{" in cleaned_ground or "}" in cleaned_ground:
                        return False
            else:
                cleaned = _RESEARCH_PLACEHOLDER_RE.sub("", query_template)
                if "{" in cleaned or "}" in cleaned:
                    return False
                cleaned_ground = _RESEARCH_PLACEHOLDER_RE.sub("", grounding_template)
                if "{" in cleaned_ground or "}" in cleaned_ground:
                    return False
            relation = step.get("relation")
            if not isinstance(relation, dict):
                return False
            try:
                for key in relation:
                    if key not in ("kind", "base", "facet"):
                        return False
            except Exception:
                return False
            kind = relation.get("kind")
            if kind not in _RESEARCH_ALLOWED_KINDS:
                return False
            base = relation.get("base")
            facet = relation.get("facet")
            if kind == "generic":
                if base not in _RESEARCH_GENERIC_BASES:
                    return False
                if "facet" in relation:
                    return False
            elif kind == _RESEARCH_BIRTH_KIND:
                if "base" in relation:
                    return False
                if facet not in _RESEARCH_BIRTH_FACETS:
                    return False
            else:
                if "base" in relation:
                    return False
                if "facet" in relation:
                    return False
            # Closed optional temporal fields.
            retr_tpl = step.get("retrieval_template")
            tcond = step.get("temporal_condition")
            has_retr = "retrieval_template" in step
            has_tcond = "temporal_condition" in step
            if has_retr:
                if not isinstance(retr_tpl, str) or not retr_tpl:
                    return False
                if len(retr_tpl) > _RESEARCH_MAX_QUERY:
                    return False
                try:
                    found_retr = [int(n) for n in _RESEARCH_PLACEHOLDER_RE.findall(retr_tpl)]
                except Exception:
                    return False
                if sorted(found_retr) != dep_nums:
                    return False
                cleaned_retr = _RESEARCH_PLACEHOLDER_RE.sub("", retr_tpl)
                if "{" in cleaned_retr or "}" in cleaned_retr:
                    return False
                # Retrieval must not be used for non-year steps.
                if not has_tcond:
                    return False
            else:
                found_retr = None
            if has_tcond:
                if not isinstance(tcond, dict):
                    return False
                try:
                    if set(tcond) != {"year"}:
                        return False
                except Exception:
                    return False
                yv = tcond.get("year")
                if not _research_is_four_digit_year(yv):
                    return False
                if not has_retr:
                    return False
                # Retrieval includes exact year, grounding omits qualifier.
                try:
                    if yv not in retr_tpl:
                        return False
                    if yv in grounding_template:
                        return False
                    if yv not in query_template:
                        return False
                except Exception:
                    return False
            else:
                if has_retr:
                    return False
            emit = step.get("emit")
            if type(emit) is not bool:
                return False
            is_terminal = (expected_id not in depended_ids)
            if is_compositional:
                if index < len(steps):
                    if emit is not False:
                        return False
                else:
                    if emit is not True:
                        return False
            else:
                if emit is not is_terminal:
                    return False
            # Grounding must map to existing families via neutral placeholder.
            # For year-qualified steps, validate grounding (without year), not
            # retrieval (with year); never ground on retrieval query with year.
            try:
                neutral = "X"
                substituted = query_template
                for dep_num in found:
                    substituted = substituted.replace(
                        "{s%d}" % dep_num, neutral
                    )
                substituted_ground = grounding_template
                for dep_num in found_ground:
                    substituted_ground = substituted_ground.replace(
                        "{s%d}" % dep_num, neutral
                    )
                if has_retr and has_tcond:
                    check_text = substituted_ground
                else:
                    check_text = substituted
                    # For birth, query and grounding are identical keyword shape;
                    # either text carries the same born placeholder proof.
                    if kind == _RESEARCH_BIRTH_KIND:
                        check_text = substituted_ground
            except Exception:
                return False
            if kind == "orbit":
                if _parse_orbit_query(check_text) is None:
                    return False
                raw = _research_extract_raw_subject(kind, check_text)
                if not raw or len(raw) > _RESEARCH_MAX_BINDING:
                    return False
                if not depends and not _research_valid_literal(raw):
                    return False
            elif kind == "capital":
                if not _parse_capital_query(check_text):
                    return False
                raw = _research_extract_raw_subject(kind, check_text)
                if not raw or len(raw) > _RESEARCH_MAX_BINDING:
                    return False
                if not depends and not _research_valid_literal(raw):
                    return False
            elif kind == "discovery":
                toks = _tokens(check_text)
                if not _is_discovery_query(toks):
                    return False
                if not _discovery_subject_phrase(check_text):
                    return False
                raw = _research_extract_raw_subject(kind, check_text)
                if not raw or len(raw) > _RESEARCH_MAX_BINDING:
                    return False
                if not depends and not _research_valid_literal(raw):
                    return False
            elif kind == "generic":
                # Year-qualified generic validates grounding without year.
                parsed = _parse_generic_who_query(check_text)
                if parsed is None:
                    return False
                parsed_base, _subj = parsed
                if parsed_base != base:
                    return False
                raw = _research_extract_raw_subject(kind, check_text, base)
                if not raw or len(raw) > _RESEARCH_MAX_BINDING:
                    return False
                if not depends and not _research_valid_literal(raw):
                    return False
                if has_tcond:
                    # Grounding must equal base question without qualifier.
                    try:
                        if yv in check_text:
                            return False
                    except Exception:
                        return False
            elif kind == _RESEARCH_BIRTH_KIND:
                try:
                    low_q = check_text.casefold()
                    low_g = substituted_ground.casefold()
                except Exception:
                    return False
                if "born" not in low_q or "born" not in low_g:
                    return False
                # Terminal grounding stays subject-specific, not loosened to a
                # bare year or bare place token.
                try:
                    if "{s" in check_text or "{s" in substituted_ground:
                        pass
                    # When placeholders present, both templates must carry them.
                    # Already checked via found vs depends; now check shape.
                    if depends:
                        if "{s" not in query_template and "{s" not in grounding_template:
                            return False
                        if "{s" not in grounding_template:
                            return False
                    else:
                        # Independent date facets have no placeholders but must
                        # still be subject-specific born keyword queries.
                        if "born" not in low_q:
                            return False
                except Exception:
                    return False
                # Facet is already checked closed (place/date).
                # No timestamp fabrication: birth templates never carry years.
                try:
                    if re.search(r"\b\d{4}\b", check_text) is not None:
                        # Independent facets are keyword "<name> born" without year.
                        # Compositional birth also has no year literal.
                        return False
                except Exception:
                    return False
            else:
                return False
        # New kinds require at least two terminals for facets/comparison/intersection.
        if not is_compositional:
            terminals = [s for s in steps if s.get("id") not in depended_ids]
            if len(terminals) < 2:
                # Facets/comparison/intersection are multi-terminal by design.
                # Single-terminal DAGs must use compositional kind.
                return False
            if chain_kind not in (
                _RESEARCH_CHAIN_FACETS,
                _RESEARCH_CHAIN_COMPARISON,
                _RESEARCH_CHAIN_INTERSECTION,
            ):
                return False
        return True
    except Exception:
        return False


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
    "MAX_HOPS",
    "MAX_CANDIDATES_PER_HOP",
    "decompose_query",
    "extract_bridge_entity",
    "plan_research_query",
    "validate_research_plan",
]
