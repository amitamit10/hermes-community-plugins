"""Central result-contract tests (offline, TESTS ONLY slice)."""

import inspect
import unittest
from importlib.util import find_spec


def _load():
    assert find_spec("result_contract") is not None, "result_contract module is missing"
    import importlib

    return importlib.import_module("result_contract")


class ResultContractNormalizationTests(unittest.TestCase):
    def test_normalize_success_returns_new_dict_and_preserves_payload(self):
        mod = _load()
        payload = {
            "results": [{"title": "t", "url": "https://example.test/a"}],
            "text": "hello",
            "pages": [{"url": "https://example.test/a"}],
            "answer": "hello",
            "sources": ["https://example.test/a"],
            "source": "fake",
            "truncated": True,
            "transitions": ["https://example.test/a"],
            "custom": {"k": "v"},
        }
        original = dict(payload)
        result = mod.normalize_result(payload)
        # New shallow dict, input not mutated.
        self.assertIsNot(result, payload)
        self.assertEqual(payload, original)
        self.assertEqual(result.get("ok"), True)
        for key, value in original.items():
            self.assertEqual(result[key], value)
        # Already-True normalized idempotently.
        again = mod.normalize_result(result)
        self.assertEqual(again, result)
        self.assertIsNot(again, result)

    def test_normalize_failure_sanitizes_and_maps_public_code(self):
        mod = _load()
        # Contradictory ok=True with non-None error still fails.
        bad = {
            "ok": True,
            "error": {"code": "PRIVATE_HOST"},
            "body": "raw",
            "status": 429,
            "provider": "x",
            "exception": "boom",
            "source": "fake",
            "transitions": ["a"],
            "truncated": False,
            "results": ["must-be-dropped-on-failure"],
        }
        snapshot = dict(bad)
        result = mod.normalize_result(bad)
        self.assertIsNot(result, bad)
        self.assertEqual(bad, snapshot)
        self.assertEqual(result.get("ok"), False)
        self.assertEqual(result.get("error"), {"code": "URL_BLOCKED"})
        # Preserve provenance, strip raw diagnostics.
        self.assertEqual(result.get("source"), "fake")
        self.assertEqual(result.get("transitions"), ["a"])
        self.assertEqual(result.get("truncated"), False)
        for stripped in ("body", "status", "provider", "exception"):
            self.assertNotIn(stripped, result)
        # Explicit code mapping table.
        cases = {
            "URL_BLOCKED": "URL_BLOCKED",
            "REDIRECT_BLOCKED": "REDIRECT_BLOCKED",
            "MISSING_CONFIG": "MISSING_CONFIG",
            "BAD_SCHEME": "URL_BLOCKED",
            "BAD_PORT": "URL_BLOCKED",
            "PRIVATE_HOST": "URL_BLOCKED",
            "CREDENTIALS_IN_URL": "URL_BLOCKED",
            "INVALID_INPUT": "URL_BLOCKED",
            "PROVIDER_ERROR": "URL_BLOCKED",
            "TRANSPORT_ERROR": "URL_BLOCKED",
            "HTTP_ERROR": "URL_BLOCKED",
            "INVALID_RESPONSE": "URL_BLOCKED",
            "UNKNOWN_SOMETHING": "URL_BLOCKED",
            "REDIRECT_FAILED": "REDIRECT_BLOCKED",
            "TOO_MANY_REDIRECTS": "REDIRECT_BLOCKED",
            "INVALID_REDIRECT": "REDIRECT_BLOCKED",
            "PROVIDER_NOT_CONFIGURED": "MISSING_CONFIG",
            "MISSING_PROVIDER_CONFIG": "MISSING_CONFIG",
            "UNVERIFIED_CONFIG": "MISSING_CONFIG",
            "UNAVAILABLE": "MISSING_CONFIG",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                out = mod.normalize_result({"ok": False, "error": raw})
                self.assertEqual(out, {"ok": False, "error": {"code": expected}})
        # Nested error dict, exception .code, None, non-mapping, cyclic fail closed.
        self.assertEqual(
            mod.normalize_result({"error": {"code": "TOO_MANY_REDIRECTS"}})["error"],
            {"code": "REDIRECT_BLOCKED"},
        )
        exc = Exception("leak")
        exc.code = "PRIVATE_HOST"
        self.assertEqual(mod.public_error_code(exc), "URL_BLOCKED")
        self.assertEqual(mod.public_error_code(None), "URL_BLOCKED")
        self.assertEqual(mod.normalize_result(None)["error"], {"code": "URL_BLOCKED"})
        for non_mapping in ("string", 123, ["x"], True):
            with self.subTest(value=non_mapping):
                out = mod.normalize_result(non_mapping)
                self.assertEqual(out.get("ok"), False)
                self.assertEqual(out.get("error"), {"code": "URL_BLOCKED"})
        cyclic = {}
        cyclic["error"] = cyclic
        out = mod.normalize_result(cyclic)
        self.assertEqual(out.get("ok"), False)
        self.assertEqual(out.get("error"), {"code": "URL_BLOCKED"})

    def test_provider_blocked_is_preserved_as_public_code(self):
        mod = _load()
        # Literal distinct code must survive as ok=False, not collapse.
        self.assertEqual(mod.public_error_code("PROVIDER_BLOCKED"), "PROVIDER_BLOCKED")
        self.assertEqual(mod.public_error_code({"code": "PROVIDER_BLOCKED"}), "PROVIDER_BLOCKED")
        self.assertEqual(mod.public_error_code({"error": {"code": "PROVIDER_BLOCKED"}}), "PROVIDER_BLOCKED")
        self.assertEqual(
            mod.public_error_code({"error": "PROVIDER_BLOCKED"}), "PROVIDER_BLOCKED"
        )
        exc = Exception("leak")
        exc.code = "PROVIDER_BLOCKED"
        self.assertEqual(mod.public_error_code(exc), "PROVIDER_BLOCKED")
        self.assertEqual(
            mod.normalize_result({"error": {"code": "PROVIDER_BLOCKED"}}),
            {"ok": False, "error": {"code": "PROVIDER_BLOCKED"}},
        )
        # Raw legacy error shape preserves the distinct code.
        self.assertEqual(
            mod.normalize_result({"error": {"code": "PROVIDER_BLOCKED"}})["error"],
            {"code": "PROVIDER_BLOCKED"},
        )

    def test_provider_blocked_sanitizes_and_preserves_provenance(self):
        mod = _load()
        raw = {
            "ok": False,
            "error": {"code": "PROVIDER_BLOCKED"},
            "body": "raw-body-secret",
            "status": 202,
            "provider": "x",
            "exception": "boom-secret",
            "results": [{"title": "must-be-dropped"}],
            "source": "fake",
            "transitions": ["a"],
            "truncated": True,
        }
        snapshot = dict(raw)
        out = mod.normalize_result(raw)
        self.assertEqual(raw, snapshot)
        self.assertEqual(out.get("ok"), False)
        self.assertEqual(out.get("error"), {"code": "PROVIDER_BLOCKED"})
        self.assertEqual(out.get("source"), "fake")
        self.assertEqual(out.get("transitions"), ["a"])
        self.assertEqual(out.get("truncated"), True)
        for stripped in ("body", "status", "provider", "exception", "results"):
            self.assertNotIn(stripped, out)
        self.assertNotIn("raw-body-secret", repr(out))
        self.assertNotIn("boom-secret", repr(out))
        # error_result preserves code with allowlisted provenance only.
        err = mod.error_result("PROVIDER_BLOCKED", source="fake", transitions=["a"], truncated=False)
        self.assertEqual(err, {"ok": False, "error": {"code": "PROVIDER_BLOCKED"},
                               "source": "fake", "transitions": ["a"], "truncated": False})
        nested = mod.error_result({"error": {"code": "PROVIDER_BLOCKED"}}, source="fake")
        self.assertEqual(nested.get("error"), {"code": "PROVIDER_BLOCKED"})
        exc = Exception("internal diagnostic detail")
        exc.code = "PROVIDER_BLOCKED"
        exc_out = mod.error_result(exc)
        self.assertEqual(exc_out.get("error"), {"code": "PROVIDER_BLOCKED"})
        self.assertNotIn("internal diagnostic detail", repr(exc_out))

        @mod.result_operation
        def op_passthrough():
            return {"error": {"code": "PROVIDER_BLOCKED"}, "body": "secret-body",
                    "status": 202, "results": ["x"], "source": "fake"}

        passed = op_passthrough()
        self.assertEqual(passed.get("ok"), False)
        self.assertEqual(passed.get("error"), {"code": "PROVIDER_BLOCKED"})
        self.assertEqual(passed.get("source"), "fake")
        self.assertNotIn("secret-body", repr(passed))

        @mod.result_operation
        def op_raise():
            err = RuntimeError("internal diagnostic detail")
            err.code = "PROVIDER_BLOCKED"
            raise err

        raised = op_raise()
        self.assertEqual(raised.get("ok"), False)
        self.assertEqual(raised.get("error"), {"code": "PROVIDER_BLOCKED"})
        self.assertNotIn("internal diagnostic detail", repr(raised))

    def test_public_helpers_and_operation_decorator(self):
        mod = _load()
        # public_error_code / error_result with provenance.
        self.assertEqual(mod.public_error_code({"error": {"code": "INVALID_REDIRECT"}}), "REDIRECT_BLOCKED")
        err = mod.error_result("UNAVAILABLE", source="fake", transitions=["a"], truncated=True)
        self.assertEqual(err.get("ok"), False)
        self.assertEqual(err.get("error"), {"code": "MISSING_CONFIG"})
        self.assertEqual(err.get("source"), "fake")
        self.assertEqual(err.get("transitions"), ["a"])
        self.assertEqual(err.get("truncated"), True)
        self.assertNotIn("exception", err)

        @mod.result_operation
        def my_op(query, limit=3):
            """Doc."""
            return {"results": [query], "truncated": False}

        self.assertEqual(my_op.__name__, "my_op")
        self.assertTrue(hasattr(my_op, "__wrapped__"))
        self.assertEqual(inspect.signature(my_op), inspect.signature(my_op.__wrapped__))
        self.assertEqual(
            my_op("q")["ok"], True,
        )

        def boom():
            raise RuntimeError("internal diagnostic detail")

        decorated_boom = mod.result_operation(boom)
        out = decorated_boom()
        self.assertEqual(out.get("ok"), False)
        self.assertEqual(out.get("error"), {"code": "URL_BLOCKED"})
        self.assertNotIn("internal diagnostic detail", repr(out))

        # Normalizing only explicitly decorated operations.
        def raw():
            return {"ok": True, "results": []}

        self.assertFalse(hasattr(raw, "__wrapped__"))
        self.assertEqual(raw(), {"ok": True, "results": []})


if __name__ == "__main__":
    unittest.main()
