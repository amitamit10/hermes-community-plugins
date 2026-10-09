"""Keyless vertical data clients with injected one-URL transports.

Public API endpoints (checked against provider documentation):
- Stocks / Stooq CSV: https://stooq.com/q/d/l/?s=aapl.us&i=d
  Docs/site: https://stooq.com/q/d/?s=aapl.us&i=d
- CVE / NVD API 2.0: https://services.nvd.nist.gov/rest/json/cves/2.0?cveIds=CVE-2024-0001
  Docs: https://nvd.nist.gov/developers/vulnerabilities (public limit: 5 requests / 30 sec)
- DOI / Crossref: https://api.crossref.org/works/10.1038/nature12373
  Docs: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- Weather / Open-Meteo: https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41
  Docs: https://open-meteo.com/en/docs
- Currency / Frankfurter v2: https://api.frankfurter.dev/v2/rates?base=USD&quotes=EUR,ILS
  Docs: https://www.frankfurter.dev/docs/

No network is performed here: callers inject ``transport(url)``. Public failures
use the bounded Goat-style ``{"error": {"code": ...}}`` envelope.
"""

import csv
import io
import json
import math
import re
from collections.abc import Mapping
from datetime import date
from urllib.parse import quote, urlencode, urlsplit


STOOQ_CSV_ENDPOINT = "https://stooq.com/q/d/l/"
NVD_CVE_ENDPOINT = "https://services.nvd.nist.gov/rest/json/cves/2.0"
CROSSREF_WORKS_ENDPOINT = "https://api.crossref.org/works/"
OPEN_METEO_FORECAST_ENDPOINT = "https://api.open-meteo.com/v1/forecast"
FRANKFURTER_RATES_ENDPOINT = "https://api.frankfurter.dev/v2/rates"

MISSING_CONFIG = "MISSING_CONFIG"
URL_BLOCKED = "URL_BLOCKED"
REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
_PUBLIC_ERRORS = frozenset((MISSING_CONFIG, URL_BLOCKED, REDIRECT_BLOCKED))
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024
_SYMBOL_RE = re.compile(r"[A-Za-z0-9^_.-]{1,32}\Z")
_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


class _ClientError(Exception):
    """Internal error carrying one public Goat error code."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code if isinstance(code, str) and code in _PUBLIC_ERRORS else URL_BLOCKED


def _error_result(error):
    code = getattr(error, "code", None)
    if isinstance(code, str) and code in _PUBLIC_ERRORS:
        public_code = code
    elif isinstance(code, str) and code in ("MISSING_CONFIG", "PROVIDER_NOT_CONFIGURED", "MISSING_PROVIDER_CONFIG"):
        public_code = MISSING_CONFIG
    elif isinstance(code, str) and code in ("REDIRECT_FAILED", "TOO_MANY_REDIRECTS", "INVALID_REDIRECT"):
        public_code = REDIRECT_BLOCKED
    else:
        public_code = URL_BLOCKED
    return {"error": {"code": public_code}}


def _response_parts(response):
    """Accept text/bytes, transport response objects, or decoded fake payloads."""
    if isinstance(response, (str, bytes)):
        status, body, final_url = 200, response, None
    elif isinstance(response, Mapping):
        envelope_fields = {"body", "text", "url", "final_url"}
        is_envelope = bool(envelope_fields.intersection(response)) or type(response.get("status")) is int
        if is_envelope:
            status = response.get("status", 200)
            body = response.get("body", response.get("text", ""))
            final_url = response.get("url", response.get("final_url"))
        else:
            status, body, final_url = 200, response, None
    elif isinstance(response, list):
        status, body, final_url = 200, response, None
    else:
        status = getattr(response, "status", 200)
        body = getattr(response, "body", getattr(response, "text", ""))
        final_url = getattr(response, "url", getattr(response, "final_url", None))
    try:
        status = int(status)
    except (TypeError, ValueError, OverflowError):
        status = 0
    if isinstance(body, bytes):
        if len(body) > _MAX_RESPONSE_BYTES:
            raise _ClientError(URL_BLOCKED)
        body = body.decode("utf-8-sig", errors="replace")
    elif isinstance(body, (Mapping, list)):
        body = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    elif not isinstance(body, str):
        body = "" if body is None else str(body)
    if len(body.encode("utf-8")) > _MAX_RESPONSE_BYTES:
        raise _ClientError(URL_BLOCKED)
    return status, body, final_url


def _fetch(transport, url):
    if transport is None:
        raise _ClientError(MISSING_CONFIG)
    if not callable(transport):
        raise _ClientError(URL_BLOCKED)
    response = transport(url)
    status, body, final_url = _response_parts(response)
    if final_url:
        try:
            original = urlsplit(url)
            final = urlsplit(final_url)
            original_port = original.port if original.port is not None else 443
            final_port = final.port if final.port is not None else 443
            same_origin = (
                final.scheme.lower() == "https"
                and original.scheme.lower() == "https"
                and final.hostname is not None
                and final.hostname.lower().rstrip(".") == (original.hostname or "").lower().rstrip(".")
                and final_port == original_port
                and final.username is None
                and final.password is None
            )
        except (TypeError, ValueError):
            same_origin = False
        if not same_origin:
            raise _ClientError(REDIRECT_BLOCKED)
    if not 200 <= status < 300:
        raise _ClientError(URL_BLOCKED)
    return body


def _run(operation):
    try:
        return operation()
    except Exception as error:
        return _error_result(error)


def _iso_date(value):
    if not isinstance(value, str) or not _ISO_DATE_RE.fullmatch(value):
        raise _ClientError(URL_BLOCKED)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise _ClientError(URL_BLOCKED) from None
    if parsed.isoformat() != value:
        raise _ClientError(URL_BLOCKED)
    return value


def _csv_dialect(text):
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;")
    except csv.Error:
        return csv.excel


def _finite_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise _ClientError(URL_BLOCKED) from None
    if not math.isfinite(number):
        raise _ClientError(URL_BLOCKED)
    return number


def _stock_prices(text):
    reader = csv.DictReader(io.StringIO(text), dialect=_csv_dialect(text))
    if not reader.fieldnames:
        raise _ClientError(URL_BLOCKED)
    names = {name.strip().lower() for name in reader.fieldnames if name}
    required = {"date", "open", "high", "low", "close", "volume"}
    if not required.issubset(names):
        raise _ClientError(URL_BLOCKED)
    prices = []
    for row in reader:
        if not row or not any(value and value.strip() for value in row.values() if isinstance(value, str)):
            continue
        normalized = {key.strip().lower(): value for key, value in row.items() if key}
        day = _iso_date(normalized.get("date"))
        volume_value = _finite_number(normalized.get("volume"))
        if not volume_value.is_integer() or volume_value < 0:
            raise _ClientError(URL_BLOCKED)
        prices.append({
            "date": day,
            "open": _finite_number(normalized.get("open")),
            "high": _finite_number(normalized.get("high")),
            "low": _finite_number(normalized.get("low")),
            "close": _finite_number(normalized.get("close")),
            "volume": int(volume_value),
        })
    return prices


def stooq_daily(symbol, transport=None, *, start_date=None, end_date=None):
    """Return daily OHLCV records from Stooq's public CSV endpoint.

    Optional dates use ISO YYYY-MM-DD and are sent to Stooq as d1/d2=YYYYMMDD.
    """
    def operation():
        if not isinstance(symbol, str) or not _SYMBOL_RE.fullmatch(symbol):
            raise _ClientError(URL_BLOCKED)
        params = {"s": symbol, "i": "d"}
        if start_date is not None:
            params["d1"] = _iso_date(start_date).replace("-", "")
        if end_date is not None:
            params["d2"] = _iso_date(end_date).replace("-", "")
        if start_date is not None and end_date is not None and start_date > end_date:
            raise _ClientError(URL_BLOCKED)
        url = STOOQ_CSV_ENDPOINT + "?" + urlencode(params)
        return {"symbol": symbol, "prices": _stock_prices(_fetch(transport, url))}
    return _run(operation)


_CVE_ID_RE = re.compile(r"CVE-\d{4}-\d{4,}\Z", re.IGNORECASE)


def nvd_cve_lookup(cve_id, transport=None):
    """Look up one CVE using the public, keyless NVD CVE API 2.0."""
    def operation():
        if not isinstance(cve_id, str) or not _CVE_ID_RE.fullmatch(cve_id):
            raise _ClientError(URL_BLOCKED)
        url = NVD_CVE_ENDPOINT + "?" + urlencode({"cveIds": cve_id})
        try:
            payload = json.loads(_fetch(transport, url))
        except (json.JSONDecodeError, TypeError):
            raise _ClientError(URL_BLOCKED) from None
        if not isinstance(payload, Mapping) or not isinstance(payload.get("vulnerabilities"), list):
            raise _ClientError(URL_BLOCKED)
        total_results = payload.get("totalResults")
        if type(total_results) is not int or total_results < 0:
            raise _ClientError(URL_BLOCKED)
        match = None
        for item in payload["vulnerabilities"]:
            if not isinstance(item, Mapping):
                continue
            cve = item.get("cve")
            cve_identifier = cve.get("id") if isinstance(cve, Mapping) else None
            if isinstance(cve_identifier, str) and cve_identifier.casefold() == cve_id.casefold():
                match = cve
                break
        return {
            "cve_id": cve_id,
            "found": match is not None,
            "total_results": total_results,
            "cve": match,
        }
    return _run(operation)


_DOI_RE = re.compile(r"10\.\d{4,9}/\S+\Z", re.IGNORECASE)


def crossref_doi_lookup(doi, transport=None):
    """Retrieve a Crossref work record for a literal DOI identifier."""
    def operation():
        if not isinstance(doi, str) or len(doi) > 1024 or not _DOI_RE.fullmatch(doi):
            raise _ClientError(URL_BLOCKED)
        url = CROSSREF_WORKS_ENDPOINT + quote(doi, safe="/")
        try:
            payload = json.loads(_fetch(transport, url))
        except (json.JSONDecodeError, TypeError):
            raise _ClientError(URL_BLOCKED) from None
        if not isinstance(payload, Mapping) or not isinstance(payload.get("message"), Mapping):
            raise _ClientError(URL_BLOCKED)
        work = payload["message"]
        returned_doi = work.get("DOI", doi)
        if not isinstance(returned_doi, str):
            raise _ClientError(URL_BLOCKED)
        return {"doi": returned_doi, "work": work}
    return _run(operation)


_CURRENT_WEATHER_VARIABLES = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "precipitation,weather_code,wind_speed_10m"
)
_TIMEZONE_RE = re.compile(r"[A-Za-z0-9_+./-]{1,64}\Z")


def open_meteo_forecast(latitude, longitude, transport=None, *, forecast_days=1, timezone="auto"):
    """Fetch current conditions from Open-Meteo's no-key forecast API."""
    def operation():
        if isinstance(latitude, bool) or not isinstance(latitude, (int, float)):
            raise _ClientError(URL_BLOCKED)
        if isinstance(longitude, bool) or not isinstance(longitude, (int, float)):
            raise _ClientError(URL_BLOCKED)
        lat, lon = float(latitude), float(longitude)
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise _ClientError(URL_BLOCKED)
        if type(forecast_days) is not int or not 1 <= forecast_days <= 16:
            raise _ClientError(URL_BLOCKED)
        if not isinstance(timezone, str) or not _TIMEZONE_RE.fullmatch(timezone):
            raise _ClientError(URL_BLOCKED)
        params = {
            "latitude": format(lat, ".8g"),
            "longitude": format(lon, ".8g"),
            "current": _CURRENT_WEATHER_VARIABLES,
            "forecast_days": str(forecast_days),
            "timezone": timezone,
        }
        url = OPEN_METEO_FORECAST_ENDPOINT + "?" + urlencode(params)
        try:
            payload = json.loads(_fetch(transport, url))
        except (json.JSONDecodeError, TypeError):
            raise _ClientError(URL_BLOCKED) from None
        if not isinstance(payload, Mapping) or not isinstance(payload.get("current"), Mapping):
            raise _ClientError(URL_BLOCKED)
        current_units = payload.get("current_units", {})
        if not isinstance(current_units, Mapping):
            raise _ClientError(URL_BLOCKED)
        response_lat = _finite_number(payload.get("latitude"))
        response_lon = _finite_number(payload.get("longitude"))
        response_timezone = payload.get("timezone")
        if not isinstance(response_timezone, str):
            raise _ClientError(URL_BLOCKED)
        return {
            "latitude": response_lat,
            "longitude": response_lon,
            "timezone": response_timezone,
            "current": payload["current"],
            "current_units": current_units,
        }
    return _run(operation)


_CURRENCY_CODE_RE = re.compile(r"[A-Z]{3}\Z")


def frankfurter_rates(base="EUR", quotes=None, transport=None, *, on_date=None):
    """Fetch current or dated exchange rates from the keyless Frankfurter v2 API.

    ``quotes`` is an optional list/tuple of ISO 4217 codes; ``on_date`` is an
    optional ISO date. Without ``on_date``, the provider returns its latest
    working-day rates.
    """
    def operation():
        if not isinstance(base, str) or not _CURRENCY_CODE_RE.fullmatch(base):
            raise _ClientError(URL_BLOCKED)
        params = {"base": base}
        requested_quotes = None
        if quotes is not None:
            if not isinstance(quotes, (list, tuple)) or not 1 <= len(quotes) <= 50:
                raise _ClientError(URL_BLOCKED)
            if any(not isinstance(code, str) or not _CURRENCY_CODE_RE.fullmatch(code) for code in quotes):
                raise _ClientError(URL_BLOCKED)
            if len(set(quotes)) != len(quotes):
                raise _ClientError(URL_BLOCKED)
            requested_quotes = set(quotes)
            params["quotes"] = ",".join(quotes)
        if on_date is not None:
            params["date"] = _iso_date(on_date)
        url = FRANKFURTER_RATES_ENDPOINT + "?" + urlencode(params)
        try:
            payload = json.loads(_fetch(transport, url))
        except (json.JSONDecodeError, TypeError):
            raise _ClientError(URL_BLOCKED) from None
        if not isinstance(payload, list):
            raise _ClientError(URL_BLOCKED)
        rates = []
        for item in payload:
            if not isinstance(item, Mapping):
                raise _ClientError(URL_BLOCKED)
            day = _iso_date(item.get("date"))
            item_base = item.get("base")
            quote = item.get("quote")
            if item_base != base or not isinstance(quote, str) or not _CURRENCY_CODE_RE.fullmatch(quote):
                raise _ClientError(URL_BLOCKED)
            if requested_quotes is not None and quote not in requested_quotes:
                raise _ClientError(URL_BLOCKED)
            rate = _finite_number(item.get("rate"))
            if rate <= 0:
                raise _ClientError(URL_BLOCKED)
            rates.append({"date": day, "base": item_base, "quote": quote, "rate": rate})
        return {"base": base, "rates": rates}
    return _run(operation)
