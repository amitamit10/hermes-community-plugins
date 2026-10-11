from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from result_contract import public_error_code as _central_code, result_operation

MISSING_CONFIG = "MISSING_CONFIG"


@dataclass(frozen=True)
class AdapterResult:
    status: str
    data: Mapping[str, Any] | None = None
    error: str | None = None


Transport = Callable[..., Any]


class SerperClient:
    requires_key = True
    experimental = True
    verified = False
    verification_status = "experimental/unverified"

    def __init__(
        self,
        transport: Transport,
        *,
        endpoint: str | None = None,
        auth_header: str | None = None,
        payload_builder: Callable[[str], Mapping[str, Any]] | None = None,
    ) -> None:
        self._transport = transport
        self.endpoint = endpoint
        self.auth_header = auth_header
        self.payload_builder = payload_builder

    @result_operation
    def search(self, query: str, *, api_key: str | None = None) -> Mapping[str, Any]:
        if not api_key or not api_key.strip():
            return {"ok": False, "error": MISSING_CONFIG}
        if self._transport is None or not callable(self._transport):
            return {"ok": False, "error": MISSING_CONFIG}
        if not (
            self.endpoint
            and self.endpoint.startswith("https://")
            and self.auth_header
            and self.payload_builder is not None
        ):
            return {"ok": False, "error": MISSING_CONFIG}
        if not query or not query.strip():
            return {"ok": False, "error": "INVALID_REQUEST"}
        try:
            payload = self.payload_builder(query)
        except Exception:
            return {"ok": False, "error": "INVALID_REQUEST"}
        if not isinstance(payload, Mapping):
            return {"ok": False, "error": "INVALID_REQUEST"}
        try:
            response = self._transport(
                method="POST",
                url=self.endpoint,
                headers={self.auth_header: api_key, "Content-Type": "application/json"},
                json=dict(payload),
            )
        except Exception as exc:
            return {"ok": False, "error": _central_code(exc)}
        if not isinstance(response, Mapping):
            return {"ok": False, "error": "INVALID_RESPONSE"}
        if "status" in response or "status_code" in response:
            try:
                status = int(response.get("status", response.get("status_code", 0)))
            except (TypeError, ValueError, OverflowError):
                status = 0
            if not 200 <= status < 300:
                return {"ok": False, "error": "HTTP_ERROR"}
        return {"ok": True, "status": "OK", "data": dict(response)}


class YouClient:
    requires_key = True
    experimental = False
    verified = True
    verification_status = "verified"
    SEARCH_ENDPOINT = "https://ydc-index.io/v1/search"

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    @result_operation
    def search(self, query: str, *, api_key: str | None = None) -> Mapping[str, Any]:
        if not api_key or not api_key.strip():
            return {"ok": False, "error": MISSING_CONFIG}
        if self._transport is None or not callable(self._transport):
            return {"ok": False, "error": MISSING_CONFIG}
        if not query or not query.strip():
            return {"ok": False, "error": "INVALID_REQUEST"}
        try:
            response = self._transport(
                method="POST",
                url=self.SEARCH_ENDPOINT,
                headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                json={"query": query},
            )
        except Exception as exc:
            return {"ok": False, "error": _central_code(exc)}
        if not isinstance(response, Mapping):
            return {"ok": False, "error": "INVALID_RESPONSE"}
        if "status" in response or "status_code" in response:
            try:
                status = int(response.get("status", response.get("status_code", 0)))
            except (TypeError, ValueError, OverflowError):
                status = 0
            if not 200 <= status < 300:
                return {"ok": False, "error": "HTTP_ERROR"}
        return {"ok": True, "status": "OK", "data": dict(response)}
