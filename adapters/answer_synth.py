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
]
