import unittest

from donsetch_adapter import (
    DEFAULT_BINARY_PATH,
    GLIBC_EXPLANATION,
    MISSING_CONFIG,
    UNAVAILABLE,
    DonsetchAdapter,
)


class FakeBinaryChecker:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.paths = []

    def __call__(self, path):
        self.paths.append(path)
        if self.error is not None:
            raise self.error
        return self.result


class DonsetchAdapterTests(unittest.TestCase):
    def test_missing_binary_returns_missing_config(self):
        checker = FakeBinaryChecker(result=False)

        result = DonsetchAdapter(binary_checker=checker).check()

        self.assertEqual(result["error"], MISSING_CONFIG)
        self.assertFalse(result["ok"])
        self.assertEqual(checker.paths, [DEFAULT_BINARY_PATH])

    def test_glibc_broken_binary_returns_unavailable_with_explanation(self):
        checker = FakeBinaryChecker(error=OSError("GLIBC_2.39 not found"))

        result = DonsetchAdapter(binary_checker=checker).check()

        self.assertEqual(result["error"], UNAVAILABLE)
        self.assertFalse(result["ok"])
        self.assertIn("GLIBC_2.39", result["explanation"])
        self.assertEqual(result["explanation"], GLIBC_EXPLANATION)
        self.assertEqual(checker.paths, [DEFAULT_BINARY_PATH])


if __name__ == "__main__":
    unittest.main()
