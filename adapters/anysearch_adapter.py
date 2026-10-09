"""Injected-transport client for AnySearch's JSON-RPC tools.

Anonymous access is the default; pass ``api_key`` for Bearer authentication.
No network transport is created implicitly and request failures never trigger
an alternate provider or silent fallback.

Vertical-domain rule: before searching a supported non-general domain, call
``vertical_discover`` (the AnySearch ``get_sub_domains`` tool). Use its
returned ``sub_domain`` and include every parameter marked ``(required)`` in
``sub_domain_params``. A required parameter may be supplied as an empty string
when the query has no applicable value.
"""

from collections.abc import Mapping
import json as _json
import re as _re
from urllib.parse import urlsplit


ENDPOINT = "https://api.anysearch.com/mcp"
MISSING_CONFIG = "MISSING_CONFIG"
URL_BLOCKED = "URL_BLOCKED"
INVALID_INPUT = "INVALID_INPUT"
VERTICAL_DISCOVERY_REQUIRED = "VERTICAL_DISCOVERY_REQUIRED"
MISSING_REQUIRED_PARAMS = "MISSING_REQUIRED_PARAMS"

AVAILABLE_DOMAINS = frozenset((
    "general", "resource", "social_media", "finance", "academic", "legal",
    "health", "business", "security", "ip", "code", "energy",
    "environment", "agriculture", "travel", "film", "gaming",
))
_MISSING = object()
_ENVELOPE_KEYS = frozenset(("status", "status_code", "body", "text"))


def _failure(error, **details):
    return {"ok": False, "error": error, **details}


def _decode_body(body):
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if isinstance(body, str):
        try:
            return _json.loads(body)
        except (TypeError, ValueError):
            return _MISSING
    if isinstance(body, (Mapping, list)):
        return body
    return _MISSING


def _response_parts(response):
    """Read a Goat-style HTTP envelope or a direct JSON-RPC fake response."""
    if isinstance(response, (str, bytes)):
        status, body = 200, response
    elif isinstance(response, Mapping):
        if any(key in response for key in _ENVELOPE_KEYS):
            status = response.get("status", response.get("status_code", 200))
            body = response.get("body", response.get("text", _MISSING))
            if body is _MISSING:
                body = {
                    key: value for key, value in response.items()
                    if key not in ("status", "status_code")
                }
        else:
            status, body = 200, response
    else:
        status = getattr(response, "status", getattr(response, "status_code", 200))
        body = getattr(response, "body", getattr(response, "text", _MISSING))
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    return status, body


def _result_data(rpc_result):
    if isinstance(rpc_result, Mapping):
        if rpc_result.get("isError") is True or rpc_result.get("error") is not None:
            return _MISSING
        structured = rpc_result.get("structuredContent", _MISSING)
        if structured is not _MISSING:
            return structured
        content = rpc_result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, Mapping) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        return text
        return rpc_result
    return rpc_result


def _normalize_name(value):
    return _re.sub(r"[^a-z0-9]", "", str(value).lower())


def _required_from_schema(schema):
    """Extract required parameter names from JSON-like or documented schemas."""
    required = set()
    if isinstance(schema, str):
        stripped = schema.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = _json.loads(stripped)
            except (TypeError, ValueError):
                parsed = _MISSING
            if parsed is not _MISSING:
                return _required_from_schema(parsed)
        pattern = r"([A-Za-z_][A-Za-z0-9_.-]*(?:\s*:\s*[A-Za-z_][A-Za-z0-9_.\[\]-]*)?)\s*\(\s*required\s*\)"
        for match in _re.finditer(pattern, schema, flags=_re.IGNORECASE):
            required.add(match.group(1).split(":", 1)[0].strip())
        return required
    if isinstance(schema, (list, tuple)):
        for item in schema:
            if isinstance(item, Mapping):
                name = item.get("name", item.get("key", item.get("param")))
                if name is not None and item.get("required") is True:
                    required.add(str(name))
                required.update(_required_from_schema(item))
            elif isinstance(item, str):
                required.update(_required_from_schema(item))
        return required
    if not isinstance(schema, Mapping):
        return required

    listed = schema.get("required")
    if isinstance(listed, (list, tuple, set, frozenset)):
        required.update(str(name) for name in listed if isinstance(name, str))
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, spec in properties.items():
            if isinstance(spec, Mapping) and spec.get("required") is True:
                required.add(str(name))
            elif isinstance(spec, str) and "required" in spec.lower():
                required.add(str(name))
        required.update(_required_from_schema(properties))

    for name, spec in schema.items():
        if name in ("required", "properties", "type", "description", "title"):
            continue
        if isinstance(spec, Mapping):
            if spec.get("required") is True:
                required.add(str(name))
            required.update(_required_from_schema(spec))
        elif isinstance(spec, str) and "required" in spec.lower():
            required.add(str(name))
    return required


def _markdown_rows(text):
    lines = [line.strip() for line in text.splitlines() if "|" in line]
    headers = None
    rows = []
    for line in lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(_re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells):
            continue
        normalized = [_normalize_name(cell) for cell in cells]
        if headers is None:
            if "subdomain" in normalized and any(key in normalized for key in ("paramsschema", "params", "requiredparams")):
                headers = normalized
            continue
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def _discovery_rows(value):
    """Yield sub-domain records from structured data or AnySearch's table text."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = _json.loads(stripped)
            except (TypeError, ValueError):
                parsed = _MISSING
            if parsed is not _MISSING:
                yield from _discovery_rows(parsed)
                return
        yield from _markdown_rows(value)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _discovery_rows(item)
        return
    if not isinstance(value, Mapping):
        return

    normalized = {_normalize_name(key): item for key, item in value.items()}
    sub_domain = normalized.get("subdomain")
    if isinstance(sub_domain, str) and sub_domain.strip():
        yield value
        return
    for key in ("subdomains", "items", "results", "domains", "data"):
        nested = normalized.get(key)
        if nested is not None:
            yield from _discovery_rows(nested)


class AnySearchClient:
    """AnySearch search client with an injected HTTP transport.

    The transport is called as ``transport(url, method="POST", headers=...,
    json=...)``. ``api_key`` is optional; without it requests are anonymous.
    A missing or failing transport is never replaced by a network fallback.
    """

    requires_key = False

    def __init__(self, transport=None, *, api_key=None):
        self._transport = transport
        self._api_key = api_key
        self._request_id = 0
        self._discovered_domains = set()
        self._discovered_subdomains = {}

    def _call(self, tool_name, arguments):
        if not callable(self._transport):
            return _failure(MISSING_CONFIG)
        headers = {"Content-Type": "application/json"}
        if isinstance(self._api_key, str) and self._api_key.strip():
            headers["Authorization"] = "Bearer " + self._api_key.strip()
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        try:
            response = self._transport(
                ENDPOINT,
                method="POST",
                headers=headers,
                json=payload,
            )
        except Exception:
            return _failure(URL_BLOCKED)

        status, raw_body = _response_parts(response)
        if not 200 <= status < 300:
            return _failure(URL_BLOCKED)
        body = _decode_body(raw_body)
        if body is _MISSING or not isinstance(body, Mapping):
            return _failure(URL_BLOCKED)
        if body.get("error") is not None:
            return _failure(URL_BLOCKED)
        rpc_result = body.get("result", _MISSING)
        if rpc_result is _MISSING:
            if body.get("ok") is False:
                return _failure(URL_BLOCKED)
            data = body.get("data", body)
        else:
            data = _result_data(rpc_result)
            if data is _MISSING:
                return _failure(URL_BLOCKED)
        return {"ok": True, "data": data}

    def _search_arguments(self, query, *, max_results=None, domain=None,
                          sub_domain=None, sub_domain_params=None):
        if not isinstance(query, str) or not query.strip():
            return _failure(INVALID_INPUT)
        if max_results is not None and (
            isinstance(max_results, bool)
            or not isinstance(max_results, int)
            or not 1 <= max_results <= 10
        ):
            return _failure(INVALID_INPUT)
        if domain is not None and (not isinstance(domain, str) or domain not in AVAILABLE_DOMAINS):
            return _failure(INVALID_INPUT)
        if sub_domain is not None and (not isinstance(sub_domain, str) or not sub_domain.strip()):
            return _failure(INVALID_INPUT)
        if sub_domain_params is not None and not isinstance(sub_domain_params, Mapping):
            return _failure(INVALID_INPUT)
        if domain is None and (sub_domain is not None or sub_domain_params is not None):
            return _failure(INVALID_INPUT)

        if domain is not None and domain != "general":
            if domain not in self._discovered_domains:
                return _failure(VERTICAL_DISCOVERY_REQUIRED)
            if sub_domain is None:
                return _failure(INVALID_INPUT)
            known_for_domain = {
                key for key in self._discovered_subdomains if key[0] == domain
            }
            pair = (domain, sub_domain)
            if known_for_domain and pair not in self._discovered_subdomains:
                return _failure("INVALID_SUB_DOMAIN")
            required = self._discovered_subdomains.get(pair, frozenset())
            provided = set(sub_domain_params or {})
            missing = sorted(required - provided)
            if missing:
                return _failure(MISSING_REQUIRED_PARAMS, missing=missing)

        arguments = {"query": query.strip()}
        if domain is not None:
            arguments["domain"] = domain
        if sub_domain is not None:
            arguments["sub_domain"] = sub_domain
        if sub_domain_params is not None:
            arguments["sub_domain_params"] = dict(sub_domain_params)
        if max_results is not None:
            arguments["max_results"] = max_results
        return arguments

    def search(self, query, *, max_results=None, domain=None, sub_domain=None,
               sub_domain_params=None):
        """Search generally or in a discovered vertical domain."""
        arguments = self._search_arguments(
            query,
            max_results=max_results,
            domain=domain,
            sub_domain=sub_domain,
            sub_domain_params=sub_domain_params,
        )
        if "ok" in arguments and arguments.get("ok") is False:
            return arguments
        return self._call("search", arguments)

    def batch_search(self, queries):
        """Submit 1-5 search objects in one AnySearch batch call."""
        if not isinstance(queries, (list, tuple)) or not 1 <= len(queries) <= 5:
            return _failure(INVALID_INPUT)
        normalized = []
        allowed = {"query", "max_results", "domain", "sub_domain", "sub_domain_params"}
        for item in queries:
            if not isinstance(item, Mapping) or set(item) - allowed or "query" not in item:
                return _failure(INVALID_INPUT)
            arguments = self._search_arguments(
                item["query"],
                max_results=item.get("max_results"),
                domain=item.get("domain"),
                sub_domain=item.get("sub_domain"),
                sub_domain_params=item.get("sub_domain_params"),
            )
            if "ok" in arguments and arguments.get("ok") is False:
                return arguments
            normalized.append(arguments)
        return self._call("batch_search", {"queries": normalized})

    def extract(self, url):
        """Extract an HTTP(S) page as Markdown through AnySearch."""
        if not isinstance(url, str) or not url.strip():
            return _failure(INVALID_INPUT)
        try:
            parsed = urlsplit(url.strip())
            if parsed.scheme.lower() not in ("http", "https") or not parsed.hostname:
                return _failure(INVALID_INPUT)
        except ValueError:
            return _failure(INVALID_INPUT)
        return self._call("extract", {"url": url.strip()})

    def vertical_discover(self, domain=None, *, domains=None):
        """Call ``get_sub_domains`` before vertical search; cache required params."""
        if domains is not None and domain is not None:
            return _failure(INVALID_INPUT)
        if domains is None:
            if not isinstance(domain, str) or domain not in AVAILABLE_DOMAINS:
                return _failure(INVALID_INPUT)
            requested = [domain]
            arguments = {"domain": domain}
        else:
            if isinstance(domains, str):
                raw = domains.strip()
                try:
                    decoded = _json.loads(raw) if raw.startswith("[") else _MISSING
                except (TypeError, ValueError):
                    decoded = _MISSING
                if isinstance(decoded, list):
                    requested = decoded
                else:
                    requested = [part.strip() for part in raw.split(",") if part.strip()]
            elif isinstance(domains, (list, tuple)):
                requested = list(domains)
            else:
                return _failure(INVALID_INPUT)
            if not 1 <= len(requested) <= 5 or any(
                not isinstance(item, str) or item not in AVAILABLE_DOMAINS
                for item in requested
            ):
                return _failure(INVALID_INPUT)
            arguments = {"domains": requested}

        result = self._call("get_sub_domains", arguments)
        if result.get("ok"):
            self._discovered_domains.update(requested)
            for row in _discovery_rows(result.get("data")):
                normalized = {_normalize_name(key): value for key, value in row.items()}
                row_domain = normalized.get("domain")
                sub_domain = normalized.get("subdomain")
                if not isinstance(sub_domain, str) or not sub_domain.strip():
                    continue
                if not isinstance(row_domain, str) or not row_domain.strip():
                    row_domain = requested[0] if len(requested) == 1 else None
                if row_domain not in requested:
                    continue
                schema = normalized.get(
                    "paramsschema",
                    normalized.get("requiredparams", normalized.get("params")),
                )
                self._discovered_subdomains[(row_domain, sub_domain)] = frozenset(
                    _required_from_schema(schema)
                )
        return result

    # Keep the underlying AnySearch tool name available for callers that prefer it.
    get_sub_domains = vertical_discover


AnySearchAdapter = AnySearchClient

__all__ = [
    "AVAILABLE_DOMAINS",
    "ENDPOINT",
    "INVALID_INPUT",
    "MISSING_CONFIG",
    "MISSING_REQUIRED_PARAMS",
    "URL_BLOCKED",
    "VERTICAL_DISCOVERY_REQUIRED",
    "AnySearchAdapter",
    "AnySearchClient",
]
