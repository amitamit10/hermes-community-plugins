from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

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

    def search(self, query: str, *, api_key: str | None = None) -> AdapterResult:
        if not api_key or not api_key.strip():
            return AdapterResult(MISSING_CONFIG)
        if not (
            self.endpoint
            and self.endpoint.startswith("https://")
            and self.auth_header
            and self.payload_builder is not None
        ):
            return AdapterResult(
                "UNVERIFIED_CONFIG",
                error="Serper endpoint, auth header, and payload schema require explicit HTTPS configuration",
            )
        if not query or not query.strip():
            return AdapterResult("INVALID_REQUEST", error="query must not be empty")
        try:
            payload = self.payload_builder(query)
        except Exception as exc:
            return AdapterResult("INVALID_REQUEST", error=type(exc).__name__)
        if not isinstance(payload, Mapping):
            return AdapterResult("INVALID_REQUEST", error="payload builder must return a mapping")
        try:
            response = self._transport(
                method="POST",
                url=self.endpoint,
                headers={self.auth_header: api_key, "Content-Type": "application/json"},
                json=dict(payload),
            )
        except Exception as exc:
            return AdapterResult("REQUEST_FAILED", error=type(exc).__name__)
        if not isinstance(response, Mapping):
            return AdapterResult("INVALID_RESPONSE", error="transport must return a mapping")
        return AdapterResult("OK", data=dict(response))


class YouClient:
    requires_key = True
    experimental = False
    verified = True
    verification_status = "verified"
    SEARCH_ENDPOINT = "https://ydc-index.io/v1/search"

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def search(self, query: str, *, api_key: str | None = None) -> AdapterResult:
        if not api_key or not api_key.strip():
            return AdapterResult(MISSING_CONFIG)
        if not query or not query.strip():
            return AdapterResult("INVALID_REQUEST", error="query must not be empty")
        try:
            response = self._transport(
                method="POST",
                url=self.SEARCH_ENDPOINT,
                headers={"X-API-Key": api_key, "Content-Type": "application/json"},
                json={"query": query},
            )
        except Exception as exc:
            return AdapterResult("REQUEST_FAILED", error=type(exc).__name__)
        if not isinstance(response, Mapping):
            return AdapterResult("INVALID_RESPONSE", error="transport must return a mapping")
        return AdapterResult("OK", data=dict(response))
