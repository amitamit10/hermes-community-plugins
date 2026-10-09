"""Small fixed regression seed of hostile URL and redirect cases."""

import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit


sys.path.insert(0, str(Path(__file__).parent.parent / "plugins" / "goat-web"))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from url_gate import check_redirect, check_url  # noqa: E402
from fuzz_gate import generate_url_cases  # noqa: E402


NASTY_URLS = (
    "https://2130706433/",  # one-part decimal IPv4
    "https://0x7f000001/",  # hexadecimal IPv4
    "https://0177.0.0.1/",  # octal IPv4
    "https://127.1/",  # shortened IPv4
    "https://[::1]/",
    "https://[::ffff:127.0.0.1]/",
    "https://[64:ff9b::7f00:1]/",  # NAT64 encoding of 127.0.0.1
    "https://LOCALHOST./",
    "https://printer。local/",  # IDNA separator
    "https://１２７。０。０。１/",  # full-width IPv4 characters
    "https://user:pass@example.com/",
    "https://user@127.0.0.1/",
    "http://example.com/",
    "https://example.com:444/",
    " https://example.com/ ",
    "https://" + ("a" * 64) + ".example/",
    "https://[fe80::1%25eth0]/",
)

NASTY_REDIRECTS = (
    ("example.com", "https://127.0.0.1/admin", 0),
    ("example.com", "//2130706433/", 0),
    ("example.com", "https://user@example.com/", 0),
    ("example.com", "http://example.com/", 0),
    ("example.com", "https://[::ffff:192.168.1.1]/", 1),
    ("https://127.0.0.1/start", "/next", 0),
    ("https://user@example.com/start", "/next", 0),
    ("example.com", "https://[64:ff9b::7f00:1]/", 0),
    ("example.com", "https://example.com:444/", 0),
    ("example.com", "https://u:p@169.254.169.254/latest", 1),
)


class GateFuzzRegressionTests(unittest.TestCase):
    def test_generated_userinfo_urls_are_rejected(self):
        userinfo_urls = []
        for url, _must_reject, _must_allow, _label in generate_url_cases():
            try:
                has_userinfo = "@" in urlsplit(url).netloc
            except ValueError:
                has_userinfo = False
            if has_userinfo:
                userinfo_urls.append(url)

        self.assertTrue(userinfo_urls, "the generator must exercise URL userinfo")
        for url in userinfo_urls:
            with self.subTest(url=url):
                self.assertFalse(check_url(url)[0], f"unexpectedly allowed userinfo URL {url!r}")

    def test_generated_urls_include_raw_and_percent_encoded_credentials(self):
        userinfo_values = set()
        for url, _must_reject, _must_allow, _label in generate_url_cases():
            try:
                netloc = urlsplit(url).netloc
            except ValueError:
                continue
            if "@" in netloc:
                userinfo_values.add(netloc.rsplit("@", 1)[0])

        for credentials in ("user", "user:pass", "u%40x:p%3Ass", "@", "user%3Aname:pa%40ss"):
            with self.subTest(credentials=credentials):
                self.assertIn(credentials, userinfo_values)

    def test_fixed_nasty_urls_are_rejected(self):
        for url in NASTY_URLS:
            with self.subTest(url=url):
                self.assertFalse(check_url(url)[0], f"unexpectedly allowed {url!r}")

    def test_fixed_nasty_redirects_are_rejected(self):
        for source, location, hops in NASTY_REDIRECTS:
            with self.subTest(source=source, location=location, hops=hops):
                self.assertFalse(
                    check_redirect(source, location, hops)[0],
                    f"unexpectedly allowed redirect {source!r} -> {location!r}",
                )


if __name__ == "__main__":
    unittest.main()
