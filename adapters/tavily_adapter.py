"""Injected-transport client for Tavily search, extract, and crawl.

The callable receives the endpoint URL first, with request details supplied as
keyword arguments: ``method``, ``headers``, and ``json``. No default network
transport or unauthenticated fallback is provided.
"""

import json as _json
from collections.abc import Mapping

from ssrf_guard import GuardError, URL_BLOCKED, check_url, validate_public_url


API_BASE_URL = "https://api.tavily.com"
SEARCH_ENDPOINT = API_BASE_URL + "/search"
EXTRACT_ENDPOINT = API_BASE_URL + "/extract"
CRAWL_ENDPOINT = API_BASE_URL + "/crawl"
MISSING_CONFIG = "MISSING_CONFIG"
_MISSING = object()


def _missing_config():
    return {"ok": False, "error": MISSING_CONFIG}


def _invalid_input():
    return {"ok": False, "error": "INVALID_INPUT"}


def _validate_target(url, resolver):
    allowed, code = check_url(url)
    if not allowed:
        raise GuardError(code)
    # Injected transports are caller-controlled; only an explicitly supplied
    # resolver performs wrapper-level DNS validation. Real transports must pin.
    if resolver is not None:
        validate_public_url(url, resolver=resolver)


class TavilyClient:
    """Small keyed API client with all HTTP delegated to ``transport``."""

    requires_key = True

    def __init__(self, api_key=None, transport=None, *, resolver=None):
        self._api_key = api_key
        self._transport = transport
        self._resolver = resolver

    def _ready(self):
        return (
            isinstance(self._api_key, str)
            and bool(self._api_key.strip())
            and callable(self._transport)
        )

    def _post(self, endpoint, payload):
        headers = {
            "Authorization": "Bearer " + self._api_key.strip(),
            "Content-Type": "application/json",
        }
        try:
            response = self._transport(
                endpoint, method="POST", headers=headers, json=payload
            )
        except Exception:
            return {"ok": False, "error": "TRANSPORT_ERROR"}

        status, body = self._response_parts(response)
        if not 200 <= status < 300:
            return {"ok": False, "error": "HTTP_ERROR", "status": status}
        data = self._decode_body(body)
        if data is _MISSING:
            return {"ok": False, "error": "INVALID_RESPONSE"}
        return {"ok": True, "data": data}

    def search(self, query, **options):
        """Submit a Tavily Search API request."""
        if not self._ready():
            return _missing_config()
        if not isinstance(query, str) or not query.strip():
            return _invalid_input()
        payload = dict(options)
        payload["query"] = query.strip()
        return self._post(SEARCH_ENDPOINT, payload)

    def extract(self, urls, **options):
        """Extract one URL or a batch of up to 20 URLs."""
        if not self._ready():
            return _missing_config()
        if isinstance(urls, str):
            url_list = [urls]
        elif isinstance(urls, (list, tuple)):
            url_list = list(urls)
        else:
            return _invalid_input()
        if (
            not url_list
            or len(url_list) > 20
            or any(not isinstance(url, str) or not url.strip() for url in url_list)
        ):
            return _invalid_input()
        try:
            for target in url_list:
                _validate_target(target, self._resolver)
        except GuardError:
            return {"error": {"code": URL_BLOCKED}}
        payload = dict(options)
        payload["urls"] = url_list
        return self._post(EXTRACT_ENDPOINT, payload)

    def crawl(self, url, **options):
        """Start a Tavily Crawl API request."""
        if not self._ready():
            return _missing_config()
        if not isinstance(url, str) or not url.strip():
            return _invalid_input()
        try:
            _validate_target(url, self._resolver)
        except GuardError:
            return {"error": {"code": URL_BLOCKED}}
        payload = dict(options)
        payload["url"] = url
        return self._post(CRAWL_ENDPOINT, payload)

    @staticmethod
    def _response_parts(response):
        """Extract status and body from mappings or response-like objects."""
        if isinstance(response, (str, bytes)):
            status, body = 200, response
        elif isinstance(response, Mapping):
            is_envelope = any(
                key in response for key in ("status", "status_code", "body", "text")
            )
            if is_envelope:
                status = response.get("status", response.get("status_code", 200))
                body = response.get("body", response.get("text", _MISSING))
                if body is _MISSING:
                    body = {
                        key: value
                        for key, value in response.items()
                        if key not in ("status", "status_code")
                    }
            else:
                status, body = 200, response
        else:
            status = getattr(response, "status", getattr(response, "status_code", 200))
            json_method = getattr(response, "json", None)
            if callable(json_method):
                try:
                    body = json_method()
                except Exception:
                    body = getattr(response, "text", _MISSING)
            else:
                body = getattr(response, "body", getattr(response, "text", _MISSING))
        try:
            status = int(status)
        except (TypeError, ValueError, OverflowError):
            status = 0
        return status, body

    @staticmethod
    def _decode_body(body):
        if isinstance(body, (Mapping, list)):
            return dict(body) if isinstance(body, Mapping) else body
        if isinstance(body, bytes):
            try:
                body = body.decode("utf-8")
            except UnicodeDecodeError:
                return _MISSING
        if isinstance(body, str):
            try:
                return _json.loads(body)
            except (TypeError, ValueError):
                return _MISSING
        return _MISSING


TavilyAdapter = TavilyClient

__all__ = [
    "API_BASE_URL",
    "CRAWL_ENDPOINT",
    "EXTRACT_ENDPOINT",
    "MISSING_CONFIG",
    "SEARCH_ENDPOINT",
    "TavilyAdapter",
    "TavilyClient",
]
