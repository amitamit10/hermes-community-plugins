import json
import unittest
from urllib.parse import parse_qs, urlsplit

import deep_verticals as dv


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class DeepVerticalsTests(unittest.TestCase):
    def test_stooq_daily_parses_csv_and_uses_free_csv_endpoint(self):
        transport = FakeTransport(
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-02,185.64,188.44,183.89,185.64,82488700\n"
        )

        result = dv.stooq_daily("aapl.us", transport=transport)

        self.assertEqual(result, {
            "symbol": "aapl.us",
            "prices": [{
                "date": "2024-01-02", "open": 185.64, "high": 188.44,
                "low": 183.89, "close": 185.64, "volume": 82488700,
            }],
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.scheme, request.netloc, request.path),
                         ("https", "stooq.com", "/q/d/l/"))
        self.assertEqual(parse_qs(request.query), {"s": ["aapl.us"], "i": ["d"]})

    def test_stooq_accepts_range_and_semicolon_csv(self):
        transport = FakeTransport(
            "Date;Open;High;Low;Close;Volume\n"
            "2024-01-02;10;12;9;11;1000\n"
        )

        result = dv.stooq_daily(
            "abc.us", transport=transport, start_date="2024-01-01", end_date="2024-01-31",
        )

        self.assertEqual(result["prices"][0]["close"], 11.0)
        self.assertEqual(parse_qs(urlsplit(transport.calls[0]).query), {
            "s": ["abc.us"], "i": ["d"], "d1": ["20240101"], "d2": ["20240131"],
        })

    def test_nvd_lookup_extracts_matching_cve_and_builds_cveids_query(self):
        payload = {"totalResults": 1, "vulnerabilities": [{"cve": {
            "id": "CVE-2024-12345",
            "descriptions": [{"lang": "en", "value": "Example vulnerability"}],
        }}]}
        transport = FakeTransport(payload)

        result = dv.nvd_cve_lookup("CVE-2024-12345", transport=transport)

        self.assertEqual(result, {
            "cve_id": "CVE-2024-12345", "found": True,
            "total_results": 1, "cve": payload["vulnerabilities"][0]["cve"],
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual(request.netloc, "services.nvd.nist.gov")
        self.assertEqual(request.path, "/rest/json/cves/2.0")
        self.assertEqual(parse_qs(request.query), {"cveIds": ["CVE-2024-12345"]})

    def test_nvd_empty_collection_returns_not_found(self):
        result = dv.nvd_cve_lookup(
            "CVE-2024-12345", transport=FakeTransport({"totalResults": 0, "vulnerabilities": []}),
        )
        self.assertEqual(result, {
            "cve_id": "CVE-2024-12345", "found": False, "total_results": 0, "cve": None,
        })

    def test_crossref_lookup_uses_work_endpoint_and_returns_message(self):
        work = {"DOI": "10.1234/abc.def", "title": ["Example paper"], "type": "journal-article"}
        transport = FakeTransport(json.dumps({"status": "ok", "message": work}))

        result = dv.crossref_doi_lookup("10.1234/abc.def", transport=transport)

        self.assertEqual(result, {"doi": "10.1234/abc.def", "work": work})
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.scheme, request.netloc, request.path),
                         ("https", "api.crossref.org", "/works/10.1234/abc.def"))

    def test_crossref_accepts_decoded_payload_from_fake_transport(self):
        work = {"DOI": "10.5555/example", "title": ["Fixture"]}
        result = dv.crossref_doi_lookup(
            "10.5555/example", transport=FakeTransport({"status": "ok", "message": work}),
        )
        self.assertEqual(result, {"doi": "10.5555/example", "work": work})

    def test_open_meteo_forecast_requests_current_conditions(self):
        current = {"time": "2024-01-01T12:00", "temperature_2m": 12.3, "weather_code": 3}
        payload = {
            "latitude": 52.52, "longitude": 13.419, "timezone": "Europe/Berlin",
            "current": current, "current_units": {"temperature_2m": "°C"},
        }
        transport = FakeTransport(json.dumps(payload))

        result = dv.open_meteo_forecast(52.52, 13.41, transport=transport)

        self.assertEqual(result, {
            "latitude": 52.52, "longitude": 13.419, "timezone": "Europe/Berlin",
            "current": current, "current_units": {"temperature_2m": "°C"},
        })
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.netloc, request.path),
                         ("api.open-meteo.com", "/v1/forecast"))
        query = parse_qs(request.query)
        self.assertEqual(query["latitude"], ["52.52"])
        self.assertEqual(query["longitude"], ["13.41"])
        self.assertEqual(query["forecast_days"], ["1"])
        self.assertEqual(query["timezone"], ["auto"])
        self.assertIn("temperature_2m", query["current"][0])

    def test_frankfurter_rates_parses_v2_rates_and_query_options(self):
        rates = [{"date": "2024-01-02", "base": "USD", "quote": "EUR", "rate": 0.91}]
        transport = FakeTransport(rates)

        result = dv.frankfurter_rates(
            base="USD", quotes=["EUR"], on_date="2024-01-02", transport=transport,
        )

        self.assertEqual(result, {"base": "USD", "rates": rates})
        request = urlsplit(transport.calls[0])
        self.assertEqual((request.netloc, request.path),
                         ("api.frankfurter.dev", "/v2/rates"))
        self.assertEqual(parse_qs(request.query), {
            "base": ["USD"], "quotes": ["EUR"], "date": ["2024-01-02"],
        })

    def test_invalid_arguments_fail_closed_for_each_domain(self):
        transports = [FakeTransport() for _ in range(5)]
        results = [
            dv.stooq_daily("aapl.us&x=1", transport=transports[0]),
            dv.nvd_cve_lookup("CVE-2024-bad", transport=transports[1]),
            dv.crossref_doi_lookup("doi:10.1234/example", transport=transports[2]),
            dv.open_meteo_forecast(91, 0, transport=transports[3]),
            dv.frankfurter_rates(base="usd", transport=transports[4]),
        ]
        self.assertEqual(results, [{"error": {"code": dv.URL_BLOCKED}}] * 5)
        self.assertEqual([transport.calls for transport in transports], [[]] * 5)

    def test_missing_transport_and_transport_exception_use_public_error_envelope(self):
        self.assertEqual(dv.stooq_daily("aapl.us"), {"error": {"code": dv.MISSING_CONFIG}})
        result = dv.frankfurter_rates(transport=FakeTransport(RuntimeError("private detail")))
        self.assertEqual(result, {"error": {"code": dv.URL_BLOCKED}})
        self.assertNotIn("private detail", repr(result))

    def test_cross_origin_redirect_is_reported_as_redirect_blocked(self):
        response = {"status": 200, "body": "{}", "url": "https://attacker.example/"}
        result = dv.crossref_doi_lookup("10.1234/example", transport=FakeTransport(response))
        self.assertEqual(result, {"error": {"code": dv.REDIRECT_BLOCKED}})

    def test_malformed_weather_payload_maps_to_public_url_error(self):
        result = dv.open_meteo_forecast(0, 0, transport=FakeTransport("not json"))
        self.assertEqual(result, {"error": {"code": dv.URL_BLOCKED}})


if __name__ == "__main__":
    unittest.main()
