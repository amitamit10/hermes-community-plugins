"""Authoritative tool schemas and dependency-free public argument validation.

Owns the exact closed JSON schemas for the registered Hermes tools. The
validator enforces every keyword actually used by those schemas and fails
closed on any unknown schema keyword instead of silently ignoring it.
"""

import re

from .goat_tools import MAX_CRAWL_DEPTH, MAX_CRAWL_PAGES, MAX_RESULTS


SCHEMAS = {
    "goat_search": {
        "name": "goat_search",
        "description": "Search public web results with bounded output.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "max_results": {
                    "type": "integer",
                    "description": f"Maximum results (1..{MAX_RESULTS}).",
                    "minimum": 1,
                    "maximum": MAX_RESULTS,
                    "default": MAX_RESULTS,
                },
                "allow_fallback": {
                    "type": "boolean",
                    "default": False,
                    "description": "Opt-in ordered fallback (DDG then Wikipedia) with source/transitions provenance; default False keeps single-provider baseline.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "goat_extract": {
        "name": "goat_extract",
        "description": "Fetch one public HTTPS page and return bounded content.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public HTTPS URL."},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    "goat_crawl": {
        "name": "goat_crawl",
        "description": "Crawl same-origin public HTTPS pages within fixed bounds.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public HTTPS start URL."},
                "max_depth": {
                    "type": "integer",
                    "description": f"Maximum crawl depth (0..{MAX_CRAWL_DEPTH}).",
                    "minimum": 0,
                    "maximum": MAX_CRAWL_DEPTH,
                    "default": MAX_CRAWL_DEPTH,
                },
                "max_pages": {
                    "type": "integer",
                    "description": f"Maximum pages to visit (1..{MAX_CRAWL_PAGES}).",
                    "minimum": 1,
                    "maximum": MAX_CRAWL_PAGES,
                    "default": MAX_CRAWL_PAGES,
                },
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    "goat_probe": {
        "name": "goat_probe",
        "description": "Check a public HTTPS URL and return status and host.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public HTTPS URL."},
            },
            "required": ["url"],
            "additionalProperties": False,
        },
    },
    "goat_answer": {
        "name": "goat_answer",
        "description": (
            "Deterministic sentence-grounded answer from fixed English Wikipedia "
            "Action API search plus readable intro extracts (at most two official "
            "requests, at most five candidates). No model call or arbitrary page "
            "fetch; direct complete subject-relation evidence or public "
            "INSUFFICIENT_EVIDENCE; bounded full claims with cited sources only; "
            "multi-hop unsupported; not general-web coverage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                    "pattern": "\\S",
                    "description": (
                        "Nonblank query; at most 2000 Unicode characters. "
                        "Surrounding whitespace is stripped by the adapter."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 5,
                    "description": (
                        "Maximum returned results or answer sources, 1 through 5; "
                        "booleans, strings and floats are rejected."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "goat_filtered_search": {
        "name": "goat_filtered_search",
        "description": (
            "Filter at most five official Wikipedia Action API candidates from the "
            "known English source (language=en) by inclusive UTC time, domain and "
            "language metadata. Active filters exclude missing metadata; no fabricated "
            "dates, refill, fallback or metadata inference; deny wins; primary matches "
            "regional variants, regional requires exact tag."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                    "pattern": "\\S",
                    "description": (
                        "Nonblank query; at most 2000 Unicode characters. "
                        "Surrounding whitespace is stripped by the adapter."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 5,
                    "description": (
                        "Maximum returned results or answer sources, 1 through 5; "
                        "booleans, strings and floats are rejected."
                    ),
                },
                "time_after": {
                    "type": "string",
                    "minLength": 10,
                    "maxLength": 64,
                    "pattern": (
                        "^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                        "(?:\\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?$"
                    ),
                    "description": (
                        "Inclusive ISO date or datetime with seconds; date-only and "
                        "timezone-naive datetimes mean UTC. Calendar validity and "
                        "ordering are checked before retrieval."
                    ),
                },
                "time_before": {
                    "type": "string",
                    "minLength": 10,
                    "maxLength": 64,
                    "pattern": (
                        "^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                        "(?:\\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?$"
                    ),
                    "description": (
                        "Inclusive ISO date or datetime with seconds; date-only and "
                        "timezone-naive datetimes mean UTC. Calendar validity and "
                        "ordering are checked before retrieval."
                    ),
                },
                "allowed_domains": {
                    "type": "array",
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 253,
                    },
                    "description": (
                        "Bare DNS names or IP literals, not URLs, credentials, ports "
                        "or wildcards. DNS names match their exact host and subdomains. "
                        "Empty allowed_domains excludes every result; omission is "
                        "unfiltered."
                    ),
                },
                "denied_domains": {
                    "type": "array",
                    "maxItems": 20,
                    "uniqueItems": True,
                    "items": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 253,
                    },
                    "description": (
                        "Bare DNS names or IP literals, not URLs, credentials, ports "
                        "or wildcards. DNS names match their exact host and subdomains. "
                        "Empty allowed_domains excludes every result; omission is "
                        "unfiltered."
                    ),
                },
                "language": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 63,
                    "pattern": "^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
                    "description": (
                        "BCP-47-like tag. A primary language matches regional variants; "
                        "a regional request requires that exact normalized tag. Missing "
                        "or invalid metadata is excluded."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    "goat_vertical_search": {
        "name": "goat_vertical_search",
        "description": (
            "Search one official, keyless metadata API: scholar=Crossref, "
            "news=GDELT, images=Wikimedia Commons. Return provider/source "
            "links and per-file image licensing; no article/image downloads "
            "or paid fallback."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vertical": {
                    "type": "string",
                    "enum": ["scholar", "news", "images"],
                },
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 2000,
                    "pattern": "\\S",
                    "description": (
                        "Nonblank query; at most 2000 Unicode characters. "
                        "Surrounding whitespace is stripped by the adapter."
                    ),
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 5,
                    "description": (
                        "Maximum returned results or answer sources, 1 through 5; "
                        "booleans, strings and floats are rejected."
                    ),
                },
            },
            "required": ["vertical", "query"],
            "additionalProperties": False,
        },
    },
}

_KNOWN_NODE_KEYWORDS = frozenset(
    (
        "type",
        "properties",
        "required",
        "additionalProperties",
        "minLength",
        "maxLength",
        "pattern",
        "minimum",
        "maximum",
        "default",
        "description",
        "enum",
        "items",
        "maxItems",
        "uniqueItems",
    )
)


def _invalid():
    return False, None


def _check_string(node, value):
    if not isinstance(value, str):
        return False
    for keyword in ("minLength", "maxLength"):
        bound = node.get(keyword)
        if keyword in node:
            if isinstance(bound, bool) or not isinstance(bound, int) or bound < 0:
                return False
    if "minLength" in node and len(value) < node["minLength"]:
        return False
    if "maxLength" in node and len(value) > node["maxLength"]:
        return False
    if "pattern" in node:
        pattern = node["pattern"]
        if not isinstance(pattern, str):
            return False
        try:
            compiled = re.compile(pattern)
        except re.error:
            return False
        if compiled.search(value) is None:
            return False
    return True


def _check_integer(node, value):
    if type(value) is not int:
        return False
    for keyword in ("minimum", "maximum"):
        if keyword in node:
            bound = node[keyword]
            if isinstance(bound, bool) or not isinstance(bound, (int, float)):
                return False
    if "minimum" in node and value < node["minimum"]:
        return False
    if "maximum" in node and value > node["maximum"]:
        return False
    return True


def _validate_node(node, value):
    if not isinstance(node, dict):
        return _invalid()
    if set(node) - _KNOWN_NODE_KEYWORDS:
        return _invalid()
    if node.get("type") == "string":
        if set(node) & {"minimum", "maximum", "properties", "required",
                         "additionalProperties", "items", "maxItems", "uniqueItems"}:
            return _invalid()
        if not _check_string(node, value):
            return _invalid()
    elif node.get("type") == "integer":
        if set(node) & {"minLength", "maxLength", "pattern", "properties", "required",
                         "additionalProperties", "items", "maxItems", "uniqueItems"}:
            return _invalid()
        if not _check_integer(node, value):
            return _invalid()
    elif node.get("type") == "boolean":
        if set(node) & {"minLength", "maxLength", "pattern", "minimum", "maximum",
                         "properties", "required", "additionalProperties",
                         "items", "maxItems", "uniqueItems"}:
            return _invalid()
        if type(value) is not bool:
            return _invalid()
        if "default" in node and type(node["default"]) is not bool:
            return _invalid()
    elif node.get("type") == "array":
        if set(node) & {"minLength", "maxLength", "pattern", "minimum", "maximum",
                         "properties", "required", "additionalProperties"}:
            return _invalid()
        if not isinstance(value, list):
            return _invalid()
        if "maxItems" in node:
            bound = node["maxItems"]
            if isinstance(bound, bool) or not isinstance(bound, int) or bound < 0:
                return _invalid()
            if len(value) > bound:
                return _invalid()
        if "uniqueItems" in node:
            flag = node["uniqueItems"]
            if not isinstance(flag, bool):
                return _invalid()
            if flag:
                for index, item in enumerate(value):
                    for other in value[index + 1:]:
                        if item == other:
                            return _invalid()
        items = node.get("items")
        if "items" in node:
            for item in value:
                valid, _ = _validate_node(items, item)
                if not valid:
                    return _invalid()
    elif node.get("type") == "object":
        if set(node) & {"minLength", "maxLength", "pattern", "minimum", "maximum",
                         "items", "maxItems", "uniqueItems", "enum"}:
            return _invalid()
        if not isinstance(value, dict):
            return _invalid()
        properties = node.get("properties", {})
        required = node.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list):
            return _invalid()
        if any(not isinstance(name, str) for name in required):
            return _invalid()
        for name in required:
            if name not in value:
                return _invalid()
        additional = node.get("additionalProperties", True)
        if not isinstance(additional, bool):
            return _invalid()
        if additional is False:
            if any(name not in properties for name in value):
                return _invalid()
        for name, subschema in properties.items():
            if name in value:
                valid, _ = _validate_node(subschema, value[name])
                if not valid:
                    return _invalid()
    else:
        return _invalid()
    if "enum" in node:
        allowed = node["enum"]
        if not isinstance(allowed, list):
            return _invalid()
        if not any(value == choice for choice in allowed):
            return _invalid()
    return True, None


def validate_args(parameters, args):
    """Validate model-supplied args; return (ok, validated_dict_or_None)."""
    valid, _ = _validate_node(
        parameters if isinstance(parameters, dict) else {}, args
    )
    if not valid:
        return False, None
    validated = {}
    properties = parameters.get("properties", {})
    for name, subschema in properties.items():
        if name in args:
            validated[name] = args[name]
        elif isinstance(subschema, dict) and "default" in subschema:
            validated[name] = subschema["default"]
    return True, validated
