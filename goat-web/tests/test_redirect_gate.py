import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "plugins" / "goat-web"))

from url_gate import OK, REDIRECT_BLOCKED, check_redirect  # noqa: E402


class RedirectGateTests(unittest.TestCase):
    def test_public_https_absolute_redirect_is_allowed(self):
        self.assertEqual(check_redirect("example.com", "https://other.example/path", 0), (True, OK))

    def test_relative_https_redirect_is_allowed(self):
        self.assertEqual(check_redirect("example.com", "/next", 1), (True, OK))

    def test_http_redirect_is_blocked(self):
        self.assertEqual(check_redirect("example.com", "http://other.example/", 0), (False, REDIRECT_BLOCKED))

    def test_private_and_local_redirect_targets_are_blocked(self):
        for location in (
            "https://169.254.169.254/latest/meta-data/",
            "https://localhost/",
            "//192.168.1.1/admin",
        ):
            with self.subTest(location=location):
                self.assertEqual(check_redirect("example.com", location, 0), (False, REDIRECT_BLOCKED))

    def test_two_hop_limit(self):
        self.assertEqual(check_redirect("example.com", "/one", 0), (True, OK))
        self.assertEqual(check_redirect("example.com", "/two", 1), (True, OK))
        self.assertEqual(check_redirect("example.com", "/three", 2), (False, REDIRECT_BLOCKED))

    def test_invalid_hop_counts_and_non_https_source_are_blocked(self):
        for hops in (-1, 2, True, "0"):
            with self.subTest(hops=hops):
                self.assertEqual(check_redirect("example.com", "/next", hops), (False, REDIRECT_BLOCKED))
        self.assertEqual(check_redirect("http://example.com", "/next", 0), (False, REDIRECT_BLOCKED))

    def test_target_userinfo_and_unsafe_ports_are_blocked(self):
        for location in ("https://user@other.example/", "https://other.example:444/"):
            with self.subTest(location=location):
                self.assertEqual(check_redirect("example.com", location, 0), (False, REDIRECT_BLOCKED))


if __name__ == "__main__":
    unittest.main()
