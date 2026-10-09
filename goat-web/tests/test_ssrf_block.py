import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "plugins" / "goat-web"))

from url_gate import (  # noqa: E402
    BAD_PORT,
    BAD_SCHEME,
    CREDENTIALS_IN_URL,
    OK,
    PRIVATE_HOST,
    URL_BLOCKED,
    check_url,
)


class SSRFBlockTests(unittest.TestCase):
    def test_required_http_ssrf_examples_are_rejected(self):
        for url in ("http://169.254.169.254/", "http://localhost:8080/"):
            with self.subTest(url=url):
                self.assertEqual(check_url(url)[0], False)

    def test_private_and_special_ipv4_literals_are_blocked(self):
        blocked = (
            "127.0.0.1",
            "10.20.30.40",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.2",
            "169.254.169.254",
            "0.0.0.0",
            "224.0.0.1",
            "240.0.0.1",
            "100.64.0.1",
        )
        for host in blocked:
            with self.subTest(host=host):
                self.assertEqual(check_url("https://" + host + "/")[1], PRIVATE_HOST)

    def test_private_and_special_ipv6_literals_are_blocked(self):
        blocked = ("::1", "fe80::1", "ff02::1", "fc00::1", "::ffff:127.0.0.1")
        for host in blocked:
            with self.subTest(host=host):
                self.assertEqual(check_url("https://[" + host + "]/")[1], PRIVATE_HOST)

    def test_local_hostnames_are_blocked(self):
        for host in ("localhost", "printer.local", "api.internal", "local", "internal", "x.localhost"):
            with self.subTest(host=host):
                self.assertEqual(check_url("https://" + host + "/")[1], PRIVATE_HOST)

    def test_userinfo_is_rejected(self):
        self.assertEqual(check_url("https://user:pass@example.com/")[1], CREDENTIALS_IN_URL)

    def test_non_443_and_malformed_ports_are_rejected(self):
        for url in ("https://example.com:8443/", "https://example.com:abc/", "https://example.com:/"):
            with self.subTest(url=url):
                self.assertEqual(check_url(url)[1], BAD_PORT)

    def test_non_https_schemes_are_rejected(self):
        for url in ("http://example.com/", "ftp://example.com/", "file:///etc/passwd"):
            with self.subTest(url=url):
                self.assertEqual(check_url(url)[1], BAD_SCHEME)

    def test_public_domain_and_ip_are_allowed(self):
        for url in ("https://example.com/path", "https://8.8.8.8/", "https://[2606:4700:4700::1111]/"):
            with self.subTest(url=url):
                self.assertEqual(check_url(url), (True, OK))

    def test_ambiguous_numeric_hosts_are_blocked(self):
        for host in ("127.1", "0177.0.0.1", "2130706433", "0x7f000001"):
            with self.subTest(host=host):
                self.assertEqual(check_url("https://" + host + "/")[1], PRIVATE_HOST)

    def test_malformed_urls_fail_closed(self):
        for url in ("", "https:///missing-host", "https://bad host/", "https://example.com\\@127.0.0.1/"):
            with self.subTest(url=url):
                self.assertFalse(check_url(url)[0])
        self.assertEqual(check_url("https:///missing-host")[1], URL_BLOCKED)


if __name__ == "__main__":
    unittest.main()
