"""Small Exa search/contents client with an explicitly injected transport.

The transport contract mirrors the Goat web tools response envelope while
allowing the POST request details required by Exa:
    transport(url, *, method="POST", headers={...}, json={...})
The client never creates a network transport or falls back to a keyless API.
"""

import json as _json
from collections.abc import Mapping


MISSING_CONFIG = "MISSING_CONFIG"
SEARCH_URL = "https://api.exa.ai/search"
CONTENTS_URL = "https://api.exa.ai/contents"


def _missing_config():
    return {"ok": False, "error": MISSING_CONFIG}


def _decode_body(body):
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="replace")
    if isinstance(body, str):
        try:
            return _json.loads(body)
        except _json.JSONDecodeError:
            return body
    return body


def _response_parts(response):
    """Return (status, parsed_body) for Goat-style or direct fake responses."""
    if isinstance(response, (str, bytes)):
        return 200, _decode_body(response)
    if isinstance(response, Mapping):
        is_envelope = any(key in response for key in ("status", "status_code", "body", "text"))
        if not is_envelope:
            return 200, response
        status = response.get("status", response.get("status_code", 200))
        body = response.get("body", response.get("text"))
    else:
        status = getattr(response, "status", getattr(response, "status_code", 200))
        body = getattr(response, "body", getattr(response, "text", None))
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = 0
    return status, _decode_body(body)


class ExaClient:
    """Client for Exa Search and Contents endpoints.

    ``api_key`` and ``transport`` are explicit dependencies. A missing key is
    reported before any transport call, and the transport is never replaced
    with a network implementation.
    """

    requires_key = True

    def __init__(self, *, api_key=None, transport=None):
        self.api_key = api_key
        self.transport = transport

    def _ready(self):
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            return False
        if not callable(self.transport):
            return False
        return True

    def _post(self, url, payload):
        response = self.transport(
            url,
            method="POST",
            headers={
                "x-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        status, body = _response_parts(response)
        if not 200 <= status < 300:
            return {
                "ok": False,
                "error": "HTTP_ERROR",
                "status": status,
                "body": body,
            }
        return {"ok": True, "data": body}

    def search(self, query, *, num_results=10, search_type=None, contents=None):
        if not self._ready():
            return _missing_config()
        if not isinstance(query, str) or not query.strip():
            return {"ok": False, "error": "INVALID_INPUT"}
        if isinstance(num_results, bool) or not isinstance(num_results, int) or num_results < 1:
            return {"ok": False, "error": "INVALID_INPUT"}
        payload = {"query": query.strip(), "numResults": num_results}
        if search_type is not None:
            if not isinstance(search_type, str) or not search_type.strip():
                return {"ok": False, "error": "INVALID_INPUT"}
            payload["type"] = search_type
        if contents is not None:
            if not isinstance(contents, Mapping):
                return {"ok": False, "error": "INVALID_INPUT"}
            payload["contents"] = dict(contents)
        return self._post(SEARCH_URL, payload)

    def contents(self, ids, **options):
        if not self._ready():
            return _missing_config()
        if isinstance(ids, str):
            ids = [ids]
        elif isinstance(ids, (list, tuple)):
            ids = list(ids)
        else:
            return {"ok": False, "error": "INVALID_INPUT"}
        if not ids or any(not isinstance(item, str) or not item.strip() for item in ids):
            return {"ok": False, "error": "INVALID_INPUT"}
        if any(not isinstance(key, str) or not key for key in options):
            return {"ok": False, "error": "INVALID_INPUT"}
        return self._post(CONTENTS_URL, {"ids": ids, **options})
