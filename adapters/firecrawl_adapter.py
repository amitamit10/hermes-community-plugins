"""Injected-transport client for Firecrawl v2 scrape and crawl."""

import json as _json

from ssrf_guard import GuardError, URL_BLOCKED, validate_public_url


API_BASE_URL = "https://api.firecrawl.dev/v2"
SCRAPE_ENDPOINT = API_BASE_URL + "/scrape"
CRAWL_ENDPOINT = API_BASE_URL + "/crawl"
MISSING_CONFIG = "MISSING_CONFIG"

_MISSING = object()


class FirecrawlClient:
    """Small Firecrawl API client; all HTTP is delegated to ``transport``.

    The transport follows the Goat web transport convention of receiving the
    URL first, with request details supplied as keyword arguments. It is called
    as ``transport(url, method="POST", headers=..., json=...)``.
    """

    requires_key = True

    def __init__(self, api_key, transport, *, resolver=None):
        self._api_key = api_key
        self._transport = transport
        self._resolver = resolver

    def scrape(self, url, **options):
        """Submit a Firecrawl v2 scrape request."""
        return self._post(SCRAPE_ENDPOINT, url, options)

    def crawl(self, url, **options):
        """Start a Firecrawl v2 crawl request."""
        return self._post(CRAWL_ENDPOINT, url, options)

    def _post(self, endpoint, url, options):
        if self.requires_key and (not isinstance(self._api_key, str) or not self._api_key.strip()):
            return {"ok": False, "error": MISSING_CONFIG}
        if not isinstance(url, str) or not url.strip():
            return {"ok": False, "error": "INVALID_REQUEST"}
        try:
            validate_public_url(url, resolver=self._resolver)
        except GuardError:
            return {"error": {"code": URL_BLOCKED}}
        if not callable(self._transport):
            return {"ok": False, "error": "TRANSPORT_ERROR"}

        headers = {
            "Authorization": "Bearer " + self._api_key,
            "Content-Type": "application/json",
        }
        payload = dict(options)
        payload["url"] = url
        try:
            response = self._transport(endpoint, method="POST", headers=headers, json=payload)
        except Exception:
            return {"ok": False, "error": "TRANSPORT_ERROR"}

        status, body = self._response_parts(response)
        if status < 200 or status >= 300:
            return {"ok": False, "error": "HTTP_ERROR", "status": status}
        provider_data = self._decode_body(body)
        if provider_data is _MISSING:
            return {"ok": False, "error": "INVALID_RESPONSE"}
        if isinstance(provider_data, dict) and provider_data.get("success") is False:
            return {"ok": False, "error": "PROVIDER_ERROR"}

        if isinstance(provider_data, dict):
            data = provider_data.get("data", _MISSING)
            if data is _MISSING:
                data = {key: value for key, value in provider_data.items() if key != "success"}
        else:
            data = provider_data
        return {"ok": True, "data": data}

    @staticmethod
    def _response_parts(response):
        """Extract status/body from transport dicts or response-like objects."""
        if isinstance(response, dict):
            envelope = any(key in response for key in ("status", "status_code", "body", "text"))
            if envelope:
                status = response.get("status", response.get("status_code", 200))
                body = response.get("body", response.get("text", _MISSING))
                if body is _MISSING:
                    body = {key: value for key, value in response.items() if key not in ("status", "status_code")}
            else:
                status, body = 200, response
        elif isinstance(response, (str, bytes)):
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
        if isinstance(body, dict) or isinstance(body, list):
            return body
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


__all__ = [
    "API_BASE_URL",
    "CRAWL_ENDPOINT",
    "MISSING_CONFIG",
    "SCRAPE_ENDPOINT",
    "FirecrawlClient",
]
