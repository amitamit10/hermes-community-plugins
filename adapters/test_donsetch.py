import unittest

from donsetch_adapter import (
    DEFAULT_BINARY_PATH,
    MISSING_CONFIG,
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

        self.assertEqual(result, {"ok": False, "error": {"code": MISSING_CONFIG}})
        self.assertEqual(checker.paths, [DEFAULT_BINARY_PATH])

    def test_broken_binary_normalizes_missing_without_explanation(self):
        checker = FakeBinaryChecker(error=OSError("GLIBC_2.39 not found"))

        result = DonsetchAdapter(binary_checker=checker).check()

        self.assertEqual(result, {"ok": False, "error": {"code": MISSING_CONFIG}})
        self.assertNotIn("explanation", result)
        self.assertNotIn("GLIBC", repr(result))
        self.assertEqual(checker.paths, [DEFAULT_BINARY_PATH])


if __name__ == "__main__":
    unittest.main()
