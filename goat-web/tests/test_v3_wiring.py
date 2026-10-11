"""Milestones 03-05: answer/filter/vertical wiring tests (strict vertical TDD).

Loads the real plugin package built by the real bundle builder
(``goat-web/scripts/build_plugin_bundle.py``, imported by file spec) into a
fresh directory under the authorized ``artifacts/wiring-build/`` root. No
ad-hoc byte copies and no source-template assumptions. All tests stay
offline: socket/DNS use is denied.
"""

import importlib.util
import json
import shutil
import socket
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


WIRING_ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = WIRING_ROOT / "goat-web" / "scripts" / "build_plugin_bundle.py"
BUILD_ROOT = WIRING_ROOT.parent / "artifacts" / "wiring-build"

_BUILDER_MODULE = None


def _load_builder():
    """Import the real bundle builder by file spec (no sys.path edits)."""
    global _BUILDER_MODULE
    if _BUILDER_MODULE is not None:
        return _BUILDER_MODULE
    module_name = "goat_v3_bundle_builder"
    spec = importlib.util.spec_from_file_location(module_name, BUILD_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load bundle builder by file spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    _BUILDER_MODULE = module
    return module


def build_fixture_package():
    """Build a fresh portable bundle with the real builder."""
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="goat-answer-", dir=str(BUILD_ROOT))
    pkgdir = Path(tmp) / "hermes-goat-web"
    _load_builder().build_bundle(WIRING_ROOT, pkgdir)
    return tmp, pkgdir


def load_fixture_package(pkgdir):
    module_name = "goat_answer_pkg_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(
        module_name,
        pkgdir / "__init__.py",
        submodule_search_locations=[str(pkgdir)],
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load fixture GOAT plugin package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module_name, module


def unload_fixture_package(module_name):
    for loaded_name in tuple(sys.modules):
        if loaded_name == module_name or loaded_name.startswith(module_name + "."):
            sys.modules.pop(loaded_name, None)


class RecordingContext:
    def __init__(self):
        self.tools = {}

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs


def register_fixture(module, ctx, search):
    """Exercise the real package register() with explicit dependencies."""
    wiring = getattr(module, "v3_wiring", None)
    if wiring is None:
        module.register(ctx)
        return None
    deps = wiring.WiringDependencies(search=search, vertical_transports=None)
    module.register(ctx, deps=deps)
    return deps


class OfflineTestCase(unittest.TestCase):
    def setUp(self):
        self._getaddrinfo = socket.getaddrinfo
        self._create_connection = socket.create_connection

        def _blocked(*args, **kwargs):
            raise AssertionError("network disabled during offline test")

        socket.getaddrinfo = _blocked
        socket.create_connection = _blocked
        self.addCleanup(setattr, socket, "getaddrinfo", self._getaddrinfo)
        self.addCleanup(setattr, socket, "create_connection", self._create_connection)


class AnswerRegistrationTests(OfflineTestCase):
    def test_goat_answer_registered_with_real_json_handler(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)

        def fake_search(query, *, max_results=5):
            return {"ok": True, "results": []}

        ctx = RecordingContext()
        register_fixture(module, ctx, fake_search)
        self.assertIn(
            "goat_answer",
            ctx.tools,
            "goat_answer is missing in real registration: %r" % sorted(ctx.tools),
        )
        tool = ctx.tools["goat_answer"]
        self.assertEqual(tool["toolset"], "goat_web")
        self.assertEqual(tool["schema"]["name"], "goat_answer")
        raw = tool["handler"]({"query": "offline evidence"})
        self.assertIsInstance(raw, str)
        self.assertIsInstance(json.loads(raw), dict)


class FixtureMixin:
    def load_tools(self, search):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        ctx = RecordingContext()
        register_fixture(module, ctx, search)
        return module, ctx.tools


class FilterRegistrationTests(OfflineTestCase, FixtureMixin):
    def test_goat_filtered_search_registered_with_real_json_handler(self):
        def fake_search(query, *, max_results=5):
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake_search)
        self.assertIn(
            "goat_filtered_search",
            tools,
            "goat_filtered_search is missing in real registration: %r"
            % sorted(tools),
        )
        tool = tools["goat_filtered_search"]
        self.assertEqual(tool["toolset"], "goat_web")
        self.assertEqual(tool["schema"]["name"], "goat_filtered_search")
        raw = tool["handler"]({"query": "offline evidence"})
        self.assertIsInstance(raw, str)
        self.assertIsInstance(json.loads(raw), dict)


EXPECTED_ANSWER_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2000,
            "pattern": "\\S",
            "description": (
                "Nonblank query; at most 2000 Unicode characters. "
                "Surrounding whitespace is stripped by the adapter."
            ),
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "default": 5,
            "description": (
                "Maximum returned results or answer sources, 1 through 5; "
                "booleans, strings and floats are rejected."
            ),
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


class AnswerSchemaTests(OfflineTestCase, FixtureMixin):
    def test_seven_tools_answer_filter_and_vertical_registered(self):
        def fake_search(query, *, max_results=5):
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake_search)
        self.assertEqual(
            set(tools),
            {
                "goat_search",
                "goat_extract",
                "goat_crawl",
                "goat_probe",
                "goat_answer",
                "goat_filtered_search",
                "goat_vertical_search",
            },
        )

    def test_answer_schema_matches_plan_exactly(self):
        def fake_search(query, *, max_results=5):
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake_search)
        schema = tools["goat_answer"]["schema"]
        self.assertEqual(schema["name"], "goat_answer")
        self.assertEqual(
            schema["description"],
            "Deterministic extractive answer with numbered URL citations over "
            "bounded official Wikipedia Action API search snippets. No model "
            "call or page fetch; not general-web coverage.",
        )
        self.assertEqual(schema["parameters"], EXPECTED_ANSWER_PARAMETERS)
        self.assertEqual(
            tools["goat_answer"]["description"], schema["description"]
        )

    def test_legacy_schema_controls_preserved(self):
        def fake_search(query, *, max_results=5):
            return {"ok": True, "results": []}

        module, tools = self.load_tools(fake_search)
        for name in ("goat_search", "goat_extract", "goat_crawl", "goat_probe"):
            with self.subTest(tool=name):
                params = tools[name]["schema"]["parameters"]
                self.assertIs(params["additionalProperties"], False)
        search_props = tools["goat_search"]["schema"]["parameters"]["properties"]
        self.assertEqual(search_props["max_results"]["minimum"], 1)
        self.assertEqual(search_props["max_results"]["maximum"], 5)
        self.assertEqual(search_props["max_results"]["default"], 5)
        self.assertNotIn("non-integers use the default", search_props["max_results"]["description"])
        crawl_props = tools["goat_crawl"]["schema"]["parameters"]["properties"]
        self.assertEqual(crawl_props["max_depth"]["minimum"], 0)
        self.assertEqual(crawl_props["max_depth"]["maximum"], 2)
        self.assertEqual(crawl_props["max_pages"]["minimum"], 1)
        self.assertEqual(crawl_props["max_pages"]["maximum"], 10)
        handlers = module.goat_handlers()
        self.assertEqual(
            set(handlers), {"goat_search", "goat_extract", "goat_crawl", "goat_probe"}
        )

    def test_validator_rejects_unknown_schema_keywords(self):
        def fake_search(query, *, max_results=5):  # pragma: no cover
            raise AssertionError("must not be called")

        module, _ = self.load_tools(fake_search)
        bogus = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
            "additionalProperties": False,
            "futureKeyword": True,
        }
        valid, _ = module.tool_schemas.validate_args(bogus, {"query": "x"})
        self.assertFalse(valid)


class AnswerValidationTests(OfflineTestCase, FixtureMixin):
    def _handler(self, calls):
        def fake_search(query, *, max_results=5):
            calls.append((query, max_results))
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake_search)
        return tools["goat_answer"]["handler"]

    def test_invalid_args_reject_before_dependencies(self):
        bad_values = [
            None,
            [],
            "query",
            42,
            {},
            {"max_results": 2},
            {"query": ""},
            {"query": "   "},
            {"query": 123},
            {"query": None},
            {"query": "x" * 2001},
            {"query": "ok", "max_results": 0},
            {"query": "ok", "max_results": 6},
            {"query": "ok", "max_results": True},
            {"query": "ok", "max_results": False},
            {"query": "ok", "max_results": "5"},
            {"query": "ok", "max_results": 5.0},
            {"query": "ok", "max_results": None},
            {"query": "ok", "transport": "https://example.com/"},
            {"query": "ok", "resolver": "8.8.8.8"},
            {"query": "ok", "provider_config": {}},
            {"query": "ok", "endpoint": "https://example.com/"},
            {"query": "ok", "base_url": "https://example.com/"},
            {"query": "ok", "api_key": "secret"},
            {"query": "ok", "headers": {}},
            {"query": "ok", "cookies": {}},
            {"query": "ok", "fallback": True},
            {"query": "ok", "auth": "token"},
        ]
        for bad in bad_values:
            with self.subTest(args=repr(bad)[:80]):
                calls = []
                handler = self._handler(calls)
                payload = json.loads(handler(bad))
                self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}})
                self.assertEqual(calls, [])

    def test_legacy_integer_bounds_reject_bool(self):
        def fake_search(query, *, max_results=5):  # pragma: no cover
            raise AssertionError("must not be called")

        _, tools = self.load_tools(fake_search)
        for name, args in (
            ("goat_search", {"query": "q", "max_results": True}),
            ("goat_crawl", {"url": "https://example.com/", "max_depth": False}),
            ("goat_crawl", {"url": "https://example.com/", "max_pages": 1.0}),
        ):
            with self.subTest(tool=name):
                payload = json.loads(tools[name]["handler"](args))
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )

    def test_handler_ignores_hermes_context_kwargs(self):
        calls = []

        def fake_search(query, *, max_results=5):
            calls.append((query, max_results))
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": "ctx"}, task_id="t-1", scope="s", extra=None
            )
        )
        self.assertEqual(calls, [("ctx", 5)])
        self.assertEqual(payload["error"]["code"], "MISSING_CONFIG")

    def test_handler_result_is_ascii_unescaped_json(self):
        def fake_search(query, *, max_results=5):
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Café naïve",
                        "url": "https://example.com/caf%C3%A9",
                        "snippet": "Café naïve fission sites release energy. Extra words here.",
                    }
                ],
            }

        _, tools = self.load_tools(fake_search)
        raw = tools["goat_answer"]["handler"](
            {"query": "Café naïve fission energy"}
        )
        self.assertIn("Caf", raw)
        self.assertNotIn("\\u00e9", raw)
        payload = json.loads(raw)
        self.assertTrue(payload["ok"])


def _search_with(results=None, **kwargs):
    def fake_search(query, *, max_results=5):
        fake_search.calls.append((query, max_results))
        response = {"ok": True, "results": list(results or [])}
        response.update(kwargs)
        return response

    fake_search.calls = []
    return fake_search


class AnswerSemanticsTests(OfflineTestCase, FixtureMixin):
    def test_extractive_cited_claims_dedupe_and_fetch_once(self):
        fake_search = _search_with(
            [
                {
                    "title": "Café fission one",
                    "url": "https://example.com/fission-one",
                    "snippet": (
                        "Nuclear fission releases energy. "
                        "Café reactors use fission heat."
                    ),
                },
                {
                    "title": "Fission two",
                    "url": "https://example.com/fission-two",
                    "snippet": (
                        "Nuclear fission releases energy. "
                        "Control rods manage fission rate."
                    ),
                },
            ],
            source="wikipedia",
            source_url="https://en.wikipedia.org/w/api.php",
        )
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": "nuclear fission energy"})
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(fake_search.calls, [("nuclear fission energy", 5)])
        self.assertIn("[1][2]", payload["answer"])
        self.assertIn("Café", payload["answer"])
        self.assertEqual(
            [item["index"] for item in payload["sources"]], [1, 2]
        )
        urls = {item["url"] for item in payload["sources"]}
        import re

        cited = {int(n) for n in re.findall(r"\[(\d+)\]", payload["answer"])}
        self.assertTrue(cited)
        self.assertTrue(cited <= {1, 2})
        for line in payload["answer"].split("\n"):
            self.assertRegex(line, r"\[\d+\]")
        self.assertNotIn("results", payload)

    def test_requested_source_cap_applies_after_single_fetch(self):
        fake_search = _search_with(
            [
                {
                    "title": "Candidate %d" % index,
                    "url": "https://example.com/candidate-%d" % index,
                    "snippet": "Nuclear fission candidate evidence number %d here." % index,
                }
                for index in range(5)
            ]
        )
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": "nuclear fission", "max_results": 1}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(fake_search.calls, [("nuclear fission", 5)])
        self.assertEqual(len(payload["sources"]), 1)

    def test_title_url_answer_bounds(self):
        long_title = "T" * 600
        exact_url = "https://example.com/" + "u" * (2048 - len("https://example.com/"))
        too_long_url = exact_url + "x"
        self.assertEqual(len(exact_url), 2048)
        fake_search = _search_with(
            [
                {"title": long_title, "url": exact_url, "snippet": "Bounded fission evidence here."},
                {"title": "Excluded", "url": too_long_url, "snippet": "Bounded fission evidence here."},
            ]
        )
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": "bounded fission evidence"})
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["sources"]), 1)
        self.assertEqual(len(payload["sources"][0]["title"]), 512)
        self.assertEqual(payload["sources"][0]["url"], exact_url)
        self.assertNotIn(too_long_url, json.dumps(payload))

    def test_long_answer_capped_at_8000(self):
        snippet = ("fission energy evidence words " * 100).strip()
        fake_search = _search_with(
            [
                {
                    "title": "Long %d" % index,
                    "url": "https://example.com/long-%d" % index,
                    "snippet": snippet,
                }
                for index in range(5)
            ]
        )
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": "fission energy evidence words"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertLessEqual(len(payload["answer"]), 8000)

    def test_unsafe_missing_urls_excluded_before_synthesis(self):
        fake_search = _search_with(
            [
                {
                    "title": "Insecure",
                    "url": "http://example.com/insecure",
                    "snippet": "Nuclear fission scoring terms dominate this snippet text.",
                },
                {"title": "No URL", "snippet": "Nuclear fission scoring terms dominate this snippet text."},
                {
                    "title": "Good",
                    "url": "https://example.com/secure",
                    "snippet": "Nuclear fission scoring terms dominate this snippet text.",
                },
            ]
        )
        _, tools = self.load_tools(fake_search)
        raw = tools["goat_answer"]["handler"](
            {"query": "nuclear fission scoring terms dominate"}
        )
        payload = json.loads(raw)
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["url"] for item in payload["sources"]],
            ["https://example.com/secure"],
        )
        self.assertNotIn("http://example.com/insecure", raw)

    def test_missing_empty_snippetless_evidence_is_missing_config(self):
        module, _ = self.load_tools(_search_with([]))
        deps_none = module.v3_wiring.WiringDependencies(
            search=None, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps_none)
        payload = json.loads(ctx.tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})

        def not_callable_search():
            return _search_with([])

        _, tools = self.load_tools("not-a-callable")
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})

        _, tools = self.load_tools(_search_with([]))
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})

        _, tools = self.load_tools(
            _search_with([{"title": "T", "url": "https://example.com/t"}])
        )
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})

    def test_typed_backend_failures_survive_as_public_codes(self):
        class RedirectError(Exception):
            code = "REDIRECT_BLOCKED"

        class MissingError(Exception):
            code = "PROVIDER_NOT_CONFIGURED"

        def raising_search(kind):
            def fake_search(query, *, max_results=5):
                if kind == "redirect":
                    raise RedirectError("moved")
                raise MissingError("no provider")

            return fake_search

        _, tools = self.load_tools(raising_search("redirect"))
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(
            payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}
        )

        _, tools = self.load_tools(raising_search("missing"))
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})

        def error_search(query, *, max_results=5):
            return {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}

        _, tools = self.load_tools(error_search)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(
            payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}
        )

    def test_malformed_backend_results_are_url_blocked(self):
        def list_search(query, *, max_results=5):
            return ["not", "a", "mapping"]

        _, tools = self.load_tools(list_search)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}})

        def bare_false_search(query, *, max_results=5):
            return {"ok": False}

        _, tools = self.load_tools(bare_false_search)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}})

        class HostileMapping(dict):
            def get(self, key, default=None):
                raise RuntimeError("hostile backend")

        def hostile_search(query, *, max_results=5):
            return HostileMapping(ok=True, results=[])

        _, tools = self.load_tools(hostile_search)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}})

    def test_provenance_preserved_on_success_only(self):
        fake_search = _search_with(
            [
                {
                    "title": "Provenance fission",
                    "url": "https://example.com/provenance",
                    "snippet": "Provenance fission evidence is recorded here today.",
                }
            ],
            source="wikipedia",
            source_url="https://en.wikipedia.org/w/api.php",
            truncated=True,
        )
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": "provenance fission evidence recorded"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "wikipedia")
        self.assertEqual(
            payload["source_url"], "https://en.wikipedia.org/w/api.php"
        )
        self.assertIn("answer", payload)
        self.assertIn("sources", payload)

        _, tools = self.load_tools(_search_with([]))
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "q"}))
        self.assertEqual(set(payload), {"ok", "error"})
        self.assertEqual(set(payload["error"]), {"code"})


class AnswerRepairTests(OfflineTestCase, FixtureMixin):
    def test_malformed_success_backends_are_url_blocked(self):
        malformed = [
            {},
            {"ok": True},
            {"ok": True, "results": None},
            {"ok": True, "results": "https://example.com/x"},
            {"ok": True, "results": {"title": "T"}},
            {"ok": True, "results": 5},
        ]
        for backend in malformed:
            with self.subTest(backend=repr(backend)[:80]):

                def fake_search(query, *, max_results=5, _backend=backend):
                    fake_search.calls.append((query, max_results))
                    return dict(_backend)

                fake_search.calls = []
                _, tools = self.load_tools(fake_search)
                payload = json.loads(
                    tools["goat_answer"]["handler"]({"query": "q"})
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )

    def test_success_provenance_preserved_without_result_copy(self):
        fake_search = _search_with(
            [
                {
                    "title": "Provenance fission",
                    "url": "https://example.com/provenance",
                    "snippet": "Provenance fission evidence is recorded here today.",
                }
            ],
            source="wikipedia",
            source_url="https://en.wikipedia.org/w/api.php",
            transitions=["t-one", "t-two"],
            truncated=True,
            metadata={"k": "v"},
            provenance={"p": "q"},
            results_should_not_leak="no",
        )
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": "provenance fission evidence recorded"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["source"], "wikipedia")
        self.assertEqual(
            payload["source_url"], "https://en.wikipedia.org/w/api.php"
        )
        self.assertEqual(payload["transitions"], ["t-one", "t-two"])
        self.assertIs(payload["truncated"], True)
        self.assertEqual(payload["metadata"], {"k": "v"})
        self.assertEqual(payload["provenance"], {"p": "q"})
        self.assertIn("answer", payload)
        self.assertIn("sources", payload)
        self.assertNotIn("results", payload)
        self.assertNotIn("results_should_not_leak", payload)

    def test_overproducing_backend_caps_before_filter_no_refill(self):
        def fake_search(query, *, max_results=5):
            fake_search.calls.append((query, max_results))
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Candidate %d" % index,
                        "url": "https://example.com/candidate-%d" % index,
                        "snippet": "Nuclear fission candidate evidence number %d here."
                        % index,
                    }
                    for index in range(7)
                ],
            }

        fake_search.calls = []
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": "nuclear fission candidate evidence"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(fake_search.calls, [("nuclear fission candidate evidence", 5)])
        self.assertLessEqual(len(payload["sources"]), 5)
        self.assertIs(payload.get("truncated"), True)

    def test_nonjson_nan_provenance_is_url_blocked(self):
        bad_provenances = [
            {"transitions": float("nan")},
            {"transitions": float("inf")},
            {"source": {1, 2, 3}},
            {"metadata": object()},
        ]
        for extra in bad_provenances:
            with self.subTest(extra=sorted(extra)):
                kwargs = {
                    "source": "wikipedia",
                    "source_url": "https://en.wikipedia.org/w/api.php",
                }
                kwargs.update(extra)

                def fake_search(query, *, max_results=5, _kw=dict(kwargs)):
                    response = {
                        "ok": True,
                        "results": [
                            {
                                "title": "Provenance fission",
                                "url": "https://example.com/provenance",
                                "snippet": (
                                    "Provenance fission evidence is recorded here today."
                                ),
                            }
                        ],
                    }
                    response.update(_kw)
                    return response

                _, tools = self.load_tools(fake_search)
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {"query": "provenance fission evidence recorded"}
                    )
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(set(payload), {"ok", "error"})

    def test_snippetless_skipped_evidence_is_not_truncation(self):
        fake_search = _search_with(
            [
                {
                    "title": "Good fission",
                    "url": "https://example.com/good",
                    "snippet": (
                        "Nuclear fission candidate evidence here today."
                    ),
                },
                {
                    "title": "Snippetless",
                    "url": "https://example.com/snippetless",
                },
            ]
        )
        _, tools = self.load_tools(fake_search)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": "nuclear fission candidate evidence",
                 "max_results": 5}
            )
        )
        self.assertTrue(payload["ok"], payload)
        self.assertEqual(len(payload["sources"]), 1)
        self.assertEqual(
            payload["sources"][0]["url"], "https://example.com/good"
        )
        self.assertFalse(payload.get("truncated", False), payload)


EXPECTED_FILTER_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2000,
            "pattern": "\\S",
            "description": (
                "Nonblank query; at most 2000 Unicode characters. "
                "Surrounding whitespace is stripped by the adapter."
            ),
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "default": 5,
            "description": (
                "Maximum returned results or answer sources, 1 through 5; "
                "booleans, strings and floats are rejected."
            ),
        },
        "time_after": {
            "type": "string",
            "minLength": 10,
            "maxLength": 64,
            "pattern": (
                "^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                "(?:\\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?$"
            ),
            "description": (
                "Inclusive ISO date or datetime with seconds; date-only and "
                "timezone-naive datetimes mean UTC. Calendar validity and "
                "ordering are checked before retrieval."
            ),
        },
        "time_before": {
            "type": "string",
            "minLength": 10,
            "maxLength": 64,
            "pattern": (
                "^[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}"
                "(?:\\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?)?$"
            ),
            "description": (
                "Inclusive ISO date or datetime with seconds; date-only and "
                "timezone-naive datetimes mean UTC. Calendar validity and "
                "ordering are checked before retrieval."
            ),
        },
        "allowed_domains": {
            "type": "array",
            "maxItems": 20,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 253,
            },
            "description": (
                "Bare DNS names or IP literals, not URLs, credentials, ports "
                "or wildcards. DNS names match their exact host and subdomains. "
                "Empty allowed_domains excludes every result; omission is "
                "unfiltered."
            ),
        },
        "denied_domains": {
            "type": "array",
            "maxItems": 20,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 253,
            },
            "description": (
                "Bare DNS names or IP literals, not URLs, credentials, ports "
                "or wildcards. DNS names match their exact host and subdomains. "
                "Empty allowed_domains excludes every result; omission is "
                "unfiltered."
            ),
        },
        "language": {
            "type": "string",
            "minLength": 2,
            "maxLength": 63,
            "pattern": "^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$",
            "description": (
                "BCP-47-like tag. A primary language matches regional variants; "
                "a regional request requires that exact normalized tag. Missing "
                "or invalid metadata is excluded."
            ),
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}


def _filter_search(results, calls, **root):
    def fake_search(query, *, max_results=5):
        calls.append((query, max_results))
        response = {"ok": True, "results": list(results)}
        response.update(root)
        return response

    return fake_search


class FilterSchemaTests(OfflineTestCase, FixtureMixin):
    def test_filter_schema_matches_plan_exactly(self):
        def fake_search(query, *, max_results=5):
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake_search)
        schema = tools["goat_filtered_search"]["schema"]
        self.assertEqual(schema["name"], "goat_filtered_search")
        self.assertEqual(
            schema["description"],
            "Filter at most five official Wikipedia Action API search candidates "
            "by inclusive UTC time, domain and language metadata. Active filters "
            "exclude missing metadata; no metadata inference, refill or fallback.",
        )
        self.assertEqual(schema["parameters"], EXPECTED_FILTER_PARAMETERS)
        self.assertEqual(
            tools["goat_filtered_search"]["description"], schema["description"]
        )

    def test_filter_invalid_args_reject_before_dependencies(self):
        bad_values = [
            None,
            [],
            "query",
            42,
            {},
            {"max_results": 2},
            {"query": ""},
            {"query": "   "},
            {"query": 123},
            {"query": None},
            {"query": "x" * 2001},
            {"query": "ok", "max_results": 0},
            {"query": "ok", "max_results": 6},
            {"query": "ok", "max_results": True},
            {"query": "ok", "max_results": False},
            {"query": "ok", "max_results": "5"},
            {"query": "ok", "max_results": 5.0},
            {"query": "ok", "max_results": None},
            {"query": "ok", "time_after": 20240101},
            {"query": "ok", "time_after": None},
            {"query": "ok", "time_after": "2024-1-1"},
            {"query": "ok", "time_after": "noon"},
            {"query": "ok", "time_after": "x" * 65},
            {"query": "ok", "time_before": ["2024-01-01"]},
            {"query": "ok", "allowed_domains": "example.com"},
            {"query": "ok", "allowed_domains": None},
            {"query": "ok", "allowed_domains": ["ok"] * 21},
            {"query": "ok", "allowed_domains": ["example.com", "example.com"]},
            {"query": "ok", "allowed_domains": ["example.com", 42]},
            {"query": "ok", "allowed_domains": [""]},
            {"query": "ok", "denied_domains": ["ok"] * 21},
            {"query": "ok", "denied_domains": ["a.com", "a.com"]},
            {"query": "ok", "denied_domains": 42},
            {"query": "ok", "language": "e"},
            {"query": "ok", "language": "x" * 64},
            {"query": "ok", "language": "en_US"},
            {"query": "ok", "language": None},
            {"query": "ok", "language": 42},
            {"query": "ok", "transport": "https://example.com/"},
            {"query": "ok", "resolver": "8.8.8.8"},
            {"query": "ok", "provider_config": {}},
            {"query": "ok", "endpoint": "https://example.com/"},
            {"query": "ok", "base_url": "https://example.com/"},
            {"query": "ok", "api_key": "secret"},
            {"query": "ok", "headers": {}},
            {"query": "ok", "cookies": {}},
            {"query": "ok", "fallback": True},
            {"query": "ok", "auth": "token"},
            {"query": "ok", "model": "gpt-x"},
        ]
        for bad in bad_values:
            with self.subTest(args=repr(bad)[:80]):
                calls = []

                def fake_search(query, *, max_results=5):
                    calls.append((query, max_results))
                    return {"ok": True, "results": []}

                _, tools = self.load_tools(fake_search)
                payload = json.loads(
                    tools["goat_filtered_search"]["handler"](bad)
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(calls, [])

    def test_filter_semantic_config_rejects_before_search(self):
        bad_filters = [
            {"time_after": "2024-02-30"},
            {"time_before": "2024-13-01T00:00:00Z"},
            {"time_after": "2024-02-01", "time_before": "2024-01-01"},
            {"time_after": "2024-01-01", "time_before": "2023-12-31T23:59:59Z"},
            {"allowed_domains": ["https://example.com/"]},
            {"allowed_domains": ["example.com:8080"]},
            {"allowed_domains": ["*.example.com"]},
            {"allowed_domains": ["user@example.com"]},
            {"denied_domains": ["https://example.com/"]},
            {"language": "en-"},
        ]
        for extra in bad_filters:
            with self.subTest(extra=extra):
                calls = []
                _, tools = self.load_tools(
                    _filter_search([{"url": "https://example.com/a"}], calls)
                )
                args = {"query": "q"}
                args.update(extra)
                payload = json.loads(
                    tools["goat_filtered_search"]["handler"](args)
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(calls, [])

    def test_all_options_supplied_and_twenty_domains_accepted(self):
        domains = ["host%d.example" % index for index in range(20)]
        calls = []
        _, tools = self.load_tools(
            _filter_search(
                [{"title": "good", "url": "https://host0.example/a",
                  "published_at": "2024-06-01T00:00:00Z",
                  "language": "en"}],
                calls,
            )
        )
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "max_results": 5,
                 "time_after": "2024-01-01",
                 "time_before": "2024-12-31T23:59:59Z",
                 "allowed_domains": domains,
                 "denied_domains": ["other.example"],
                 "language": "en"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(calls, [("q", 5)])

    def test_handler_ignores_hermes_context_kwargs(self):
        calls = []
        _, tools = self.load_tools(_filter_search([], calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "ctx"}, task_id="t-1", scope="s", extra=None
            )
        )
        self.assertEqual(calls, [("ctx", 5)])
        self.assertEqual(payload, {"ok": True, "results": []})


class FilterTimeTests(OfflineTestCase, FixtureMixin):
    def test_inclusive_endpoints_and_timezone_equivalence(self):
        results = [
            {"title": "before", "url": "https://example.com/before",
             "published_at": "2024-01-14T23:59:59Z"},
            {"title": "lower", "url": "https://example.com/lower",
             "published_at": "2024-01-15T00:00:00Z"},
            {"title": "mid", "url": "https://example.com/mid",
             "published_at": "2024-01-17T12:00:00Z"},
            {"title": "upper", "url": "https://example.com/upper",
             "published_at": "2024-01-20T12:00:00+00:00"},
            {"title": "after", "url": "https://example.com/after",
             "published_at": "2024-01-20T12:00:01Z"},
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "time_after": "2024-01-15",
                 "time_before": "2024-01-20T12:00:00Z"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["results"]],
            ["lower", "mid", "upper"],
        )
        self.assertEqual(calls, [("q", 5)])

    def test_timezone_and_naive_equivalence(self):
        results = [
            {"title": "midnight", "url": "https://example.com/a",
             "published_at": "2024-01-15T00:00:00Z"},
        ]
        for extra in (
            {"time_after": "2024-01-15T05:00:00+05:00"},
            {"time_after": "2024-01-15T00:00:00"},
            {"time_after": "2024-01-15"},
        ):
            with self.subTest(extra=extra):
                calls = []
                _, tools = self.load_tools(_filter_search(results, calls))
                args = {"query": "q"}
                args.update(extra)
                payload = json.loads(
                    tools["goat_filtered_search"]["handler"](args)
                )
                self.assertTrue(payload["ok"])
                self.assertEqual(len(payload["results"]), 1)

    def test_every_date_alias_supported(self):
        fields = (
            "published_at", "publishedAt", "published_date",
            "publication_date", "published", "date", "datetime",
            "timestamp", "created_at",
        )
        for field in fields:
            with self.subTest(field=field):
                calls = []
                _, tools = self.load_tools(
                    _filter_search(
                        [{"title": field, "url": "https://example.com/a",
                          field: "2024-06-01T00:00:00Z"}],
                        calls,
                    )
                )
                payload = json.loads(
                    tools["goat_filtered_search"]["handler"](
                        {"query": "q", "time_after": "2024-01-01",
                         "time_before": "2024-12-31"}
                    )
                )
                self.assertTrue(payload["ok"])
                self.assertEqual(len(payload["results"]), 1)
                self.assertEqual(calls, [("q", 5)])

    def test_first_present_invalid_alias_is_authoritative(self):
        calls = []
        _, tools = self.load_tools(
            _filter_search(
                [{"title": "bad-first", "url": "https://example.com/a",
                  "published_at": "not-a-date",
                  "published": "2024-06-01T00:00:00Z"}],
                calls,
            )
        )
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "time_after": "2024-01-01",
                 "time_before": "2024-12-31"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["results"], [])
        self.assertEqual(calls, [("q", 5)])

    def test_missing_null_invalid_dates_excluded_but_unfiltered_retained(self):
        results = [
            {"title": "no-date", "url": "https://example.com/a"},
            {"title": "null-date", "url": "https://example.com/b",
             "published_at": None},
            {"title": "invalid-date", "url": "https://example.com/c",
             "date": "2024-13-45"},
            {"title": "good", "url": "https://example.com/d",
             "published_at": "2024-06-01T00:00:00Z"},
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "time_after": "2024-01-01"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["results"]], ["good"]
        )

        calls2 = []
        _, tools2 = self.load_tools(_filter_search(results, calls2))
        payload2 = json.loads(tools2["goat_filtered_search"]["handler"]({"query": "q"}))
        self.assertTrue(payload2["ok"])
        self.assertEqual(len(payload2["results"]), 4)


def _wikipedia_action_body(items):
    return json.dumps({"query": {"search": items}}).encode("utf-8")


def _fake_pinned_fetch(status, body, calls):
    def fake_fetch(url, **kwargs):
        calls.append((url, kwargs))
        return {"status": status, "headers": {}, "body": body, "url": url}

    return fake_fetch


class FilterDomainTests(OfflineTestCase, FixtureMixin):
    def test_allow_exact_and_subdomain_not_suffix_lookalikes(self):
        results = [
            {"title": "exact", "url": "https://example.com/a"},
            {"title": "sub", "url": "https://deep.sub.example.com/b"},
            {"title": "lookalike", "url": "https://notexample.com/c"},
            {"title": "suffix", "url": "https://example.com.evil.com/d"},
            {"title": "other", "url": "https://other.org/e"},
            {"title": "unusable", "url": "not a url"},
            {"title": "missing"},
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "allowed_domains": ["example.com"]}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["results"]],
            ["exact", "sub"],
        )
        self.assertEqual(calls, [("q", 5)])

    def test_deny_wins_over_allow_and_empty_allow_excludes_all(self):
        results = [
            {"title": "apex", "url": "https://example.com/a"},
            {"title": "sub", "url": "https://sub.example.com/b"},
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "allowed_domains": ["example.com"],
                 "denied_domains": ["sub.example.com"]}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["results"]], ["apex"]
        )

        calls2 = []
        _, tools2 = self.load_tools(_filter_search(results, calls2))
        payload2 = json.loads(
            tools2["goat_filtered_search"]["handler"](
                {"query": "q", "allowed_domains": []}
            )
        )
        self.assertTrue(payload2["ok"])
        self.assertEqual(payload2["results"], [])

        calls3 = []
        _, tools3 = self.load_tools(_filter_search(results, calls3))
        payload3 = json.loads(tools3["goat_filtered_search"]["handler"]({"query": "q"}))
        self.assertTrue(payload3["ok"])
        self.assertEqual(len(payload3["results"]), 2)


class FilterLanguageTests(OfflineTestCase, FixtureMixin):
    def test_primary_matches_regional_variants(self):
        results = [
            {"title": "en", "url": "https://example.com/a", "language": "en"},
            {"title": "en-us", "url": "https://example.com/b", "language": "en-US"},
            {"title": "en-gb", "url": "https://example.com/c", "language": "en-GB"},
            {"title": "fr", "url": "https://example.com/d", "language": "fr"},
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "language": "en"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["results"]],
            ["en", "en-us", "en-gb"],
        )
        self.assertEqual(calls, [("q", 5)])

    def test_regional_request_requires_exact_tag(self):
        results = [
            {"title": "en", "url": "https://example.com/a", "language": "en"},
            {"title": "en-us", "url": "https://example.com/b", "language": "en-US"},
            {"title": "en-gb", "url": "https://example.com/c", "language": "en-GB"},
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "language": "en-US"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["results"]], ["en-us"]
        )

    def test_missing_invalid_languages_excluded_but_unfiltered_retained(self):
        results = [
            {"title": "no-lang", "url": "https://example.com/a"},
            {"title": "null-lang", "url": "https://example.com/b",
             "language": None},
            {"title": "bad-lang", "url": "https://example.com/c",
             "lang": "xx_YY!"},
            {"title": "good", "url": "https://example.com/d", "lang": "en"},
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "language": "en"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(
            [item["title"] for item in payload["results"]], ["good"]
        )

        _, tools2 = self.load_tools(_filter_search(results, []))
        payload2 = json.loads(tools2["goat_filtered_search"]["handler"]({"query": "q"}))
        self.assertTrue(payload2["ok"])
        self.assertEqual(len(payload2["results"]), 4)


class FilterCapTests(OfflineTestCase, FixtureMixin):
    def test_later_candidate_qualifies_with_final_cap_and_metadata_preserved(self):
        results = [
            {"title": "blocked", "url": "https://denied.example/x",
             "snippet": "first", "custom_extra": "kept-0"},
            {"title": "second", "url": "https://example.com/second",
             "snippet": "second", "custom_extra": "kept-1"},
            {"title": "third", "url": "https://example.com/third",
             "snippet": "third", "custom_extra": "kept-2"},
        ]
        calls = []
        _, tools = self.load_tools(
            _filter_search(
                results, calls, source="wikipedia",
                source_url="https://en.wikipedia.org/w/api.php",
                transitions=["t"], truncated=False,
            )
        )
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "nuclear fission", "max_results": 1,
                 "denied_domains": ["denied.example"]}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(calls, [("nuclear fission", 5)])
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["title"], "second")
        self.assertEqual(payload["results"][0]["custom_extra"], "kept-1")
        self.assertEqual(payload["source"], "wikipedia")
        self.assertEqual(
            payload["source_url"], "https://en.wikipedia.org/w/api.php"
        )
        self.assertEqual(payload["transitions"], ["t"])
        self.assertTrue(payload["truncated"])

    def test_filtering_itself_is_not_truncation(self):
        results = [
            {"title": "keep-%d" % index,
             "url": "https://example.com/%d" % index}
            for index in range(2)
        ] + [
            {"title": "drop-%d" % index,
             "url": "https://denied.example/%d" % index}
            for index in range(3)
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "denied_domains": ["denied.example"]}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["results"]), 2)
        self.assertEqual(calls, [("q", 5)])
        self.assertFalse(payload.get("truncated", False))

    def test_candidate_overproduction_caps_at_five_with_truncated(self):
        results = [
            {"title": "item-%d" % index,
             "url": "https://example.com/%d" % index}
            for index in range(7)
        ]
        calls = []
        _, tools = self.load_tools(_filter_search(results, calls))
        payload = json.loads(
            tools["goat_filtered_search"]["handler"]({"query": "q"})
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["results"]), 5)
        self.assertTrue(payload["truncated"])
        self.assertEqual(calls, [("q", 5)])

    def test_empty_filter_result_is_success(self):
        calls = []
        _, tools = self.load_tools(
            _filter_search(
                [{"title": "old", "url": "https://example.com/a",
                  "published_at": "2020-01-01T00:00:00Z"}],
                calls,
            )
        )
        payload = json.loads(
            tools["goat_filtered_search"]["handler"](
                {"query": "q", "time_after": "2024-01-01"}
            )
        )
        self.assertEqual(payload, {"ok": True, "results": []})
        self.assertEqual(calls, [("q", 5)])

    def test_typed_backend_failures_survive_filter_wrapper(self):
        class RedirectError(Exception):
            code = "REDIRECT_BLOCKED"

        class MissingError(Exception):
            code = "PROVIDER_NOT_CONFIGURED"

        def raising_search(kind):
            def fake_search(query, *, max_results=5):
                if kind == "redirect":
                    raise RedirectError("moved")
                raise MissingError("no provider")

            return fake_search

        _, tools = self.load_tools(raising_search("redirect"))
        payload = json.loads(tools["goat_filtered_search"]["handler"]({"query": "q"}))
        self.assertEqual(
            payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}
        )

        _, tools = self.load_tools(raising_search("missing"))
        payload = json.loads(tools["goat_filtered_search"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})

        def error_search(query, *, max_results=5):
            return {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}

        _, tools = self.load_tools(error_search)
        payload = json.loads(tools["goat_filtered_search"]["handler"]({"query": "q"}))
        self.assertEqual(
            payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}
        )

    def test_missing_backend_is_missing_config_but_invalid_filters_reject_first(self):
        module, _ = self.load_tools(
            _filter_search([{"url": "https://example.com/a"}], [])
        )
        deps_none = module.v3_wiring.WiringDependencies(
            search=None, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps_none)
        payload = json.loads(
            ctx.tools["goat_filtered_search"]["handler"]({"query": "q"})
        )
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})

        payload = json.loads(
            ctx.tools["goat_filtered_search"]["handler"](
                {"query": "q", "time_after": "2024-02-30"}
            )
        )
        self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}})

        _, tools = self.load_tools("not-a-callable")
        payload = json.loads(tools["goat_filtered_search"]["handler"]({"query": "q"}))
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})


class OfficialDefaultTransportTests(OfflineTestCase, FixtureMixin):
    def _wiring(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        return module.v3_wiring

    def test_default_search_uses_fixed_endpoint_with_exact_fetch_bounds(self):
        wiring = self._wiring()
        calls = []
        body = _wikipedia_action_body(
            [
                {
                    "title": "Nuclear fission",
                    "snippet": "Nuclear fission releases <b>energy</b> slowly.",
                }
            ]
        )
        search = wiring.make_default_search(
            _fetch=_fake_pinned_fetch(200, body, calls)
        )
        response = search("nuclear fission", max_results=5)
        self.assertEqual(len(calls), 1)
        url, kwargs = calls[0]
        self.assertTrue(
            url.startswith("https://en.wikipedia.org/w/api.php?"),
            url,
        )
        self.assertEqual(
            kwargs,
            {
                "timeout": 10,
                "max_response_bytes": 1048576,
                "max_redirects": 0,
                "resolver": None,
                "connection_factory": None,
            },
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["source"], "wikipedia")
        self.assertEqual(
            response["source_url"], "https://en.wikipedia.org/w/api.php"
        )
        self.assertEqual(
            response["results"][0]["url"],
            "https://en.wikipedia.org/wiki/Nuclear_fission",
        )

    def test_default_search_forwards_resolver_and_connection_seams(self):
        wiring = self._wiring()
        calls = []
        seen = {}

        def fake_fetch(url, **kwargs):
            seen.update(kwargs)
            return {
                "status": 200,
                "headers": {},
                "body": _wikipedia_action_body([]),
                "url": url,
            }

        resolver = object()
        factory = object()
        search = wiring.make_default_search(
            _fetch=fake_fetch, _resolver=resolver, _connection_factory=factory
        )
        search("q", max_results=5)
        self.assertIs(seen["resolver"], resolver)
        self.assertIs(seen["connection_factory"], factory)
        self.assertEqual(seen["timeout"], 10)
        self.assertEqual(seen["max_redirects"], 0)

    def test_redirect_is_blocked_without_second_request(self):
        wiring = self._wiring()
        calls = []
        body = _wikipedia_action_body(
            [{"title": "Nuclear fission", "snippet": "usable evidence"}]
        )
        search = wiring.make_default_search(
            _fetch=_fake_pinned_fetch(301, body, calls)
        )
        response = search("nuclear fission", max_results=5)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            response, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}
        )

    def test_error_statuses_are_url_blocked(self):
        wiring = self._wiring()
        for status in (403, 429, 500, 200 - 200):
            with self.subTest(status=status):
                calls = []
                search = wiring.make_default_search(
                    _fetch=_fake_pinned_fetch(status, b"{}", calls)
                )
                response = search("q", max_results=5)
                self.assertEqual(len(calls), 1)
                self.assertEqual(
                    response, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )

    def test_transport_preflight_rejects_non_fixed_urls(self):
        wiring = self._wiring()
        base = "https://en.wikipedia.org/w/api.php?action=query"
        bad_urls = [
            "http://en.wikipedia.org/w/api.php?action=query",
            "https://en.wikipedia.com/w/api.php?action=query",
            "https://en.wikipedia.org/w/other.php?action=query",
            "https://en.wikipedia.org:8443/w/api.php?action=query",
            "https://user:pass@en.wikipedia.org/w/api.php?action=query",
            base + "#fragment",
        ]
        for bad in bad_urls:
            with self.subTest(url=bad):
                called = []

                def never_fetch(url, **kwargs):  # pragma: no cover
                    called.append(url)
                    raise AssertionError("fetch must not run")

                with self.assertRaises(Exception) as raised:
                    wiring.wikipedia_transport(bad, _fetch=never_fetch)
                self.assertEqual(called, [])
                self.assertIn(
                    getattr(raised.exception, "code", None),
                    ("URL_BLOCKED", "REDIRECT_BLOCKED"),
                )

    def test_default_dependencies_are_offline_and_frozen(self):
        wiring = self._wiring()
        deps = wiring.default_dependencies()
        self.assertTrue(callable(deps.search))
        self.assertEqual(
            set(deps.vertical_transports), {"scholar", "news", "images"}
        )
        for name in ("scholar", "news", "images"):
            self.assertTrue(callable(deps.vertical_transports[name]))
        import dataclasses

        with self.assertRaises(dataclasses.FrozenInstanceError):
            deps.search = None

        transports = {"scholar": lambda url: {}}
        snapped = wiring.WiringDependencies(
            search=None, vertical_transports=transports
        )
        transports["scholar"] = lambda url: {"changed": True}
        transports["news"] = lambda url: {}
        self.assertEqual(set(snapped.vertical_transports), {"scholar"})

        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        ctx = RecordingContext()
        module.register(ctx)
        self.assertEqual(
            set(ctx.tools),
            {
                "goat_search",
                "goat_extract",
                "goat_crawl",
                "goat_probe",
                "goat_answer",
                "goat_filtered_search",
                "goat_vertical_search",
            },
        )


VERTICAL_ENDPOINTS = {
    "scholar": "https://api.crossref.org/works",
    "news": "https://api.gdeltproject.org/api/v2/doc/doc",
    "images": "https://commons.wikimedia.org/w/api.php",
}

VERTICAL_SOURCES = {
    "scholar": ("crossref", "https://www.crossref.org/"),
    "news": ("gdelt", "https://gdeltproject.org/"),
    "images": ("wikimedia-commons", "https://commons.wikimedia.org/"),
}

EXPECTED_VERTICAL_PARAMETERS = {
    "type": "object",
    "properties": {
        "vertical": {
            "type": "string",
            "enum": ["scholar", "news", "images"],
        },
        "query": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2000,
            "pattern": "\\S",
            "description": (
                "Nonblank query; at most 2000 Unicode characters. "
                "Surrounding whitespace is stripped by the adapter."
            ),
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 5,
            "default": 5,
            "description": (
                "Maximum returned results or answer sources, 1 through 5; "
                "booleans, strings and floats are rejected."
            ),
        },
    },
    "required": ["vertical", "query"],
    "additionalProperties": False,
}

EXPECTED_VERTICAL_DESCRIPTION = (
    "Search one official, keyless metadata API: scholar=Crossref, news=GDELT, "
    "images=Wikimedia Commons. Return provider/source links and per-file image "
    "licensing; no article/image downloads or paid fallback."
)


def _crossref_body(items):
    return json.dumps({"status": "ok", "message": {"items": items}}).encode("utf-8")


def _gdelt_body(articles):
    return json.dumps({"articles": articles}).encode("utf-8")


def _commons_body(pages):
    return json.dumps({"query": {"pages": pages}}).encode("utf-8")


def _recording_transport(calls, body, status=200):
    def fake_transport(url):
        calls.append(url)
        return {"status": status, "headers": {}, "body": body, "url": url}

    return fake_transport


def _scholar_item(title="Scholarly fission", doi="10.1234/fission"):
    return {
        "title": [title],
        "DOI": doi,
        "URL": "https://example.com/scholarly-fission",
        "author": [{"given": "Marie", "family": "Curie"}],
        "container-title": ["Journal of Fission"],
        "published-print": {"date-parts": [[2021]]},
    }


def _news_article(title="Fission grid news"):
    return {
        "title": title,
        "url": "https://publisher.example/grid-news",
        "snippet": "Grid operators discuss fission output.",
        "seendate": "20261009T120000Z",
        "domain": "publisher.example",
        "language": "English",
        "sourcecountry": "United States",
    }


def _commons_page(title="File:Fission.jpg"):
    return {
        "pageid": 42,
        "title": title,
        "imageinfo": [
            {
                "thumburl": "https://upload.wikimedia.org/thumb/fission.jpg",
                "url": "https://upload.wikimedia.org/fission.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Fission.jpg",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                    "Artist": {"value": "Ada Example"},
                    "ImageDescription": {"value": "A fission diagram."},
                },
            }
        ],
    }


def _vertical_tools(transports, test_case):
    tmp, pkgdir = build_fixture_package()
    test_case.addCleanup(shutil.rmtree, tmp, True)
    module_name, module = load_fixture_package(pkgdir)
    test_case.addCleanup(unload_fixture_package, module_name)

    def dummy_search(query, *, max_results=5):  # pragma: no cover
        raise AssertionError("search must not run for vertical tests")

    deps = module.v3_wiring.WiringDependencies(
        search=dummy_search, vertical_transports=dict(transports)
    )
    ctx = RecordingContext()
    module.register(ctx, deps=deps)
    return module, ctx.tools


class VerticalRegistrationTests(OfflineTestCase):
    def test_goat_vertical_search_registered_with_real_json_handler(self):
        calls = []
        transports = {
            name: _recording_transport(calls, _crossref_body([]))
            for name in ("scholar", "news", "images")
        }
        module, tools = _vertical_tools(transports, self)
        self.assertIn(
            "goat_vertical_search",
            tools,
            "goat_vertical_search is missing in real registration: %r"
            % sorted(tools),
        )
        tool = tools["goat_vertical_search"]
        self.assertEqual(tool["toolset"], "goat_web")
        self.assertEqual(tool["schema"]["name"], "goat_vertical_search")
        raw = tool["handler"]({"vertical": "scholar", "query": "offline evidence"})
        self.assertIsInstance(raw, str)
        self.assertIsInstance(json.loads(raw), dict)

    def test_seven_tools_registered_and_no_vertical_aliases(self):
        def fake_search(query, *, max_results=5):
            return {"ok": True, "results": []}

        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        ctx = RecordingContext()
        deps = module.v3_wiring.WiringDependencies(
            search=fake_search,
            vertical_transports={
                "scholar": lambda url: {"status": 200, "body": b"{}"},
                "news": lambda url: {"status": 200, "body": b"{}"},
                "images": lambda url: {"status": 200, "body": b"{}"},
            },
        )
        module.register(ctx, deps=deps)
        self.assertEqual(
            set(ctx.tools),
            {
                "goat_search",
                "goat_extract",
                "goat_crawl",
                "goat_probe",
                "goat_answer",
                "goat_filtered_search",
                "goat_vertical_search",
            },
        )
        for alias in ("goat_scholar", "goat_news", "goat_images"):
            self.assertNotIn(alias, ctx.tools)

    def test_vertical_schema_matches_plan_exactly(self):
        calls = []
        module, tools = _vertical_tools(
            {"scholar": _recording_transport(calls, _crossref_body([]))}, self
        )
        del module
        schema = tools["goat_vertical_search"]["schema"]
        self.assertEqual(schema["name"], "goat_vertical_search")
        self.assertEqual(schema["description"], EXPECTED_VERTICAL_DESCRIPTION)
        self.assertEqual(schema["parameters"], EXPECTED_VERTICAL_PARAMETERS)
        self.assertEqual(
            tools["goat_vertical_search"]["description"], schema["description"]
        )


class VerticalValidationTests(OfflineTestCase):
    def test_enum_root_query_count_unknown_reject_before_transport(self):
        bad_values = [
            None,
            [],
            "query",
            42,
            {},
            {"query": "q"},
            {"vertical": "scholar"},
            {"vertical": "books", "query": "q"},
            {"vertical": "", "query": "q"},
            {"vertical": None, "query": "q"},
            {"vertical": 42, "query": "q"},
            {"vertical": "SCHOLAR", "query": "q"},
            {"vertical": "scholar", "query": ""},
            {"vertical": "scholar", "query": "   "},
            {"vertical": "scholar", "query": 123},
            {"vertical": "scholar", "query": None},
            {"vertical": "scholar", "query": "x" * 2001},
            {"vertical": "news", "query": "ok", "max_results": 0},
            {"vertical": "news", "query": "ok", "max_results": 6},
            {"vertical": "news", "query": "ok", "max_results": True},
            {"vertical": "news", "query": "ok", "max_results": False},
            {"vertical": "news", "query": "ok", "max_results": "5"},
            {"vertical": "news", "query": "ok", "max_results": 5.0},
            {"vertical": "news", "query": "ok", "max_results": None},
            {"vertical": "images", "query": "ok", "transport": "https://example.com/"},
            {"vertical": "images", "query": "ok", "limit": 2},
            {"vertical": "images", "query": "ok", "resolver": "8.8.8.8"},
            {"vertical": "images", "query": "ok", "provider_config": {}},
            {"vertical": "images", "query": "ok", "endpoint": "https://example.com/"},
            {"vertical": "images", "query": "ok", "base_url": "https://example.com/"},
            {"vertical": "images", "query": "ok", "api_key": "secret"},
            {"vertical": "images", "query": "ok", "headers": {}},
            {"vertical": "images", "query": "ok", "cookies": {}},
            {"vertical": "images", "query": "ok", "fallback": True},
            {"vertical": "images", "query": "ok", "auth": "token"},
            {"vertical": "images", "query": "ok", "model": "gpt-x"},
        ]
        for bad in bad_values:
            with self.subTest(args=repr(bad)[:80]):
                calls = []
                _, tools = _vertical_tools(
                    {
                        "scholar": _recording_transport(calls, _crossref_body([])),
                        "news": _recording_transport(calls, _gdelt_body([])),
                        "images": _recording_transport(calls, _commons_body([])),
                    },
                    self,
                )
                payload = json.loads(
                    tools["goat_vertical_search"]["handler"](bad)
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(calls, [])

    def test_handler_ignores_hermes_context_kwargs(self):
        calls = []
        _, tools = _vertical_tools(
            {"scholar": _recording_transport(calls, _crossref_body([]))}, self
        )
        payload = json.loads(
            tools["goat_vertical_search"]["handler"](
                {"vertical": "scholar", "query": "ctx"},
                task_id="t-1",
                scope="s",
                extra=None,
            )
        )
        self.assertEqual(len(calls), 1)
        self.assertTrue(payload["ok"])


class VerticalSnapshotTests(OfflineTestCase, FixtureMixin):
    def test_vertical_transports_snapshot_is_read_only(self):
        def fake_search(query, *, max_results=5):  # pragma: no cover
            raise AssertionError("must not be called")

        module, _ = self.load_tools(fake_search)
        original = {"scholar": lambda url: {"status": 200, "body": b"{}"}}
        deps = module.v3_wiring.WiringDependencies(
            search=fake_search, vertical_transports=original
        )
        with self.assertRaises(TypeError):
            deps.vertical_transports["scholar"] = lambda url: {}
        with self.assertRaises(TypeError):
            deps.vertical_transports["news"] = lambda url: {}
        original["scholar"] = lambda url: {"changed": True}
        original["news"] = lambda url: {}
        self.assertEqual(set(deps.vertical_transports), {"scholar"})
        selected = deps.vertical_transports["scholar"]
        self.assertEqual(selected("https://example.com/"), {"status": 200, "body": b"{}"})

    def test_explicit_deps_do_not_reconstruct_defaults(self):
        scholar_calls = []
        news_calls = []
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        deps = module.v3_wiring.WiringDependencies(
            search=None,
            vertical_transports={
                "scholar": _recording_transport(scholar_calls, _crossref_body([])),
            },
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        payload = json.loads(
            ctx.tools["goat_vertical_search"]["handler"](
                {"vertical": "news", "query": "q"}
            )
        )
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})
        self.assertEqual(scholar_calls, [])
        self.assertEqual(news_calls, [])

        deps_none = module.v3_wiring.WiringDependencies(
            search=None, vertical_transports=None
        )
        ctx2 = RecordingContext()
        module.register(ctx2, deps=deps_none)
        payload = json.loads(
            ctx2.tools["goat_vertical_search"]["handler"](
                {"vertical": "scholar", "query": "q"}
            )
        )
        self.assertEqual(payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}})


class VerticalDispatchTests(OfflineTestCase):
    def _dispatch(self, vertical, query, max_results=None):
        from urllib.parse import urlsplit, parse_qs

        calls = []
        bodies = {
            "scholar": _crossref_body([_scholar_item()]),
            "news": _gdelt_body([_news_article()]),
            "images": _commons_body([_commons_page()]),
        }
        transports = {
            name: _recording_transport(calls, bodies[name])
            for name in ("scholar", "news", "images")
        }
        _, tools = _vertical_tools(transports, self)
        args = {"vertical": vertical, "query": query}
        if max_results is not None:
            args["max_results"] = max_results
        payload = json.loads(tools["goat_vertical_search"]["handler"](args))
        self.assertEqual(calls, [calls[0]] if calls else [])
        parsed = urlsplit(calls[0])
        params = parse_qs(parsed.query)
        return payload, parsed, params, calls

    def test_scholar_request_url_rows_and_limit_mapping(self):
        from urllib.parse import urlsplit

        for max_results, expected_rows in ((None, "5"), (1, "1"), (5, "5")):
            with self.subTest(max_results=max_results):
                payload, parsed, params, calls = self._dispatch(
                    "scholar", "fission energy", max_results
                )
                self.assertTrue(payload["ok"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(
                    calls[0].split("?")[0], VERTICAL_ENDPOINTS["scholar"]
                )
                self.assertEqual(params["query"], ["fission energy"])
                self.assertEqual(params["rows"], [expected_rows])
                self.assertNotIn("max_results", params)
                self.assertIn("select", params)
                self.assertNotIn("abstract", params["select"][0].lower())
                self.assertEqual(payload["vertical"], "scholar")
                self.assertEqual(payload["source"], "crossref")
                self.assertEqual(payload["source_url"], "https://www.crossref.org/")

    def test_news_request_url_maxrecords_mapping(self):
        for max_results, expected in ((None, "5"), (1, "1"), (5, "5")):
            with self.subTest(max_results=max_results):
                payload, parsed, params, calls = self._dispatch(
                    "news", "grid outage", max_results
                )
                self.assertTrue(payload["ok"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].split("?")[0], VERTICAL_ENDPOINTS["news"])
                self.assertEqual(params["query"], ["grid outage"])
                self.assertEqual(params["maxrecords"], [expected])
                self.assertNotIn("max_results", params)
                self.assertEqual(payload["vertical"], "news")
                self.assertEqual(payload["source"], "gdelt")
                self.assertEqual(payload["source_url"], "https://gdeltproject.org/")

    def test_images_request_url_gsrlimit_mapping(self):
        for max_results, expected in ((None, "5"), (1, "1"), (5, "5")):
            with self.subTest(max_results=max_results):
                payload, parsed, params, calls = self._dispatch(
                    "images", "fission diagram", max_results
                )
                self.assertTrue(payload["ok"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0].split("?")[0], VERTICAL_ENDPOINTS["images"])
                self.assertEqual(params["gsrsearch"], ["fission diagram"])
                self.assertEqual(params["gsrlimit"], [expected])
                self.assertNotIn("max_results", params)
                self.assertEqual(payload["vertical"], "images")
                self.assertEqual(payload["source"], "wikimedia-commons")
                self.assertEqual(
                    payload["source_url"], "https://commons.wikimedia.org/"
                )

    def test_missing_none_transports_yield_missing_config_without_network(self):
        for transports in (
            {},
            {"scholar": None},
            {"scholar": "not-callable"},
            None,
        ):
            with self.subTest(transports=repr(transports)[:60]):
                calls = []
                tmp, pkgdir = build_fixture_package()
                self.addCleanup(shutil.rmtree, tmp, True)
                module_name, module = load_fixture_package(pkgdir)
                self.addCleanup(unload_fixture_package, module_name)
                deps = module.v3_wiring.WiringDependencies(
                    search=None, vertical_transports=transports
                )
                ctx = RecordingContext()
                module.register(ctx, deps=deps)
                payload = json.loads(
                    ctx.tools["goat_vertical_search"]["handler"](
                        {"vertical": "scholar", "query": "q"}
                    )
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "MISSING_CONFIG"}}
                )
                self.assertEqual(calls, [])

    def test_vertical_failures_are_exact_public_envelope(self):
        calls = []
        _, tools = _vertical_tools(
            {"scholar": _recording_transport(calls, b"not-json", status=200)},
            self,
        )
        payload = json.loads(
            tools["goat_vertical_search"]["handler"](
                {"vertical": "scholar", "query": "q"}
            )
        )
        self.assertEqual(payload, {"ok": False, "error": {"code": "URL_BLOCKED"}})


class VerticalMetadataTests(OfflineTestCase):
    def test_scholar_fields_preserved_without_abstract_fetch(self):
        calls = []
        _, tools = _vertical_tools(
            {"scholar": _recording_transport(calls, _crossref_body([_scholar_item()]))},
            self,
        )
        payload = json.loads(
            tools["goat_vertical_search"]["handler"](
                {"vertical": "scholar", "query": "fission"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(calls), 1)
        (result,) = payload["results"]
        self.assertEqual(result["title"], "Scholarly fission")
        self.assertEqual(result["doi"], "10.1234/fission")
        self.assertEqual(result["url"], "https://example.com/scholarly-fission")
        self.assertEqual(result["authors"], ["Marie Curie"])
        self.assertEqual(result["year"], 2021)
        self.assertEqual(result["venue"], "Journal of Fission")
        self.assertNotIn("abstract", result)
        self.assertIn("truncated", payload)

    def test_news_publisher_and_gdelt_attribution_preserved(self):
        calls = []
        _, tools = _vertical_tools(
            {"news": _recording_transport(calls, _gdelt_body([_news_article()]))},
            self,
        )
        payload = json.loads(
            tools["goat_vertical_search"]["handler"](
                {"vertical": "news", "query": "grid"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(calls), 1)
        (result,) = payload["results"]
        self.assertEqual(result["title"], "Fission grid news")
        self.assertEqual(result["url"], "https://publisher.example/grid-news")
        self.assertEqual(result["snippet"], "Grid operators discuss fission output.")
        self.assertEqual(result["published"], "20261009T120000Z")
        self.assertEqual(result["source"], "publisher.example")
        self.assertEqual(result["language"], "English")
        self.assertEqual(result["country"], "United States")
        self.assertEqual(payload["source"], "gdelt")
        self.assertEqual(payload["source_url"], "https://gdeltproject.org/")

    def test_commons_license_creator_and_page_url_preserved(self):
        calls = []
        _, tools = _vertical_tools(
            {"images": _recording_transport(calls, _commons_body([_commons_page()]))},
            self,
        )
        payload = json.loads(
            tools["goat_vertical_search"]["handler"](
                {"vertical": "images", "query": "fission"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(calls), 1)
        (result,) = payload["results"]
        self.assertEqual(result["url"], "https://upload.wikimedia.org/thumb/fission.jpg")
        self.assertEqual(
            result["page_url"], "https://commons.wikimedia.org/wiki/File:Fission.jpg"
        )
        self.assertEqual(result["creator"], "Ada Example")
        self.assertEqual(result["license"], "CC BY-SA 4.0")
        self.assertEqual(
            result["license_url"], "https://creativecommons.org/licenses/by-sa/4.0/"
        )
        self.assertEqual(result["description"], "A fission diagram.")

    def test_commons_no_license_or_unsafe_records_excluded_without_download(self):
        calls = []
        good = _commons_page()
        no_license = _commons_page("File:NoLicense.jpg")
        no_license["imageinfo"][0]["extmetadata"] = {}
        unsafe = _commons_page("File:Unsafe.jpg")
        unsafe["imageinfo"][0]["thumburl"] = "http://example.com/unsafe.jpg"
        unsafe["imageinfo"][0]["url"] = "http://example.com/unsafe.jpg"
        _, tools = _vertical_tools(
            {
                "images": _recording_transport(
                    calls, _commons_body([no_license, unsafe, good])
                )
            },
            self,
        )
        payload = json.loads(
            tools["goat_vertical_search"]["handler"](
                {"vertical": "images", "query": "fission"}
            )
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(payload["results"]), 1)
        self.assertEqual(payload["results"][0]["title"], "File:Fission.jpg")


class VerticalOfficialTransportTests(OfflineTestCase, FixtureMixin):
    def _wiring(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        return module.v3_wiring

    def test_preflight_rejects_non_exact_authority_path(self):
        wiring = self._wiring()
        endpoints = {
            "wikipedia": "https://en.wikipedia.org/w/api.php",
            "crossref": "https://api.crossref.org/works",
            "gdelt": "https://api.gdeltproject.org/api/v2/doc/doc",
            "commons": "https://commons.wikimedia.org/w/api.php",
        }
        for name, endpoint in endpoints.items():
            transport = wiring.make_official_transport(endpoint)
            bad_urls = [
                endpoint.replace("https://", "http://") + "?x=1",
                endpoint + "?x=1#fragment",
                "https://user:pass@" + endpoint[8:] + "?x=1",
                endpoint + ":443?x=1",
                endpoint + "/other?x=1",
                endpoint.replace(".org", ".com") + "?x=1",
                endpoint.replace("https://", "https://sub.") + "?x=1",
                endpoint.replace(".org", ".org.") + "?x=1",
                endpoint.upper().replace("HTTPS", "https") + "?x=1",
                "not a url",
                "",
            ]
            for bad in bad_urls:
                with self.subTest(endpoint=name, url=bad):
                    called = []

                    def never_fetch(url, **kwargs):  # pragma: no cover
                        called.append(url)
                        raise AssertionError("fetch must not run")

                    with self.assertRaises(Exception) as raised:
                        transport(bad, _fetch=never_fetch)
                    self.assertEqual(called, [])
                    code = getattr(raised.exception, "code", raised.exception)
                    self.assertEqual(
                        wiring._vendor_contract.public_error_code(code),
                        "URL_BLOCKED",
                    )

    def test_all_statuses_mapped_before_parsing_without_second_request(self):
        wiring = self._wiring()
        endpoints = (
            "https://en.wikipedia.org/w/api.php",
            "https://api.crossref.org/works",
            "https://api.gdeltproject.org/api/v2/doc/doc",
            "https://commons.wikimedia.org/w/api.php",
        )
        for endpoint in endpoints:
            transport = wiring.make_official_transport(endpoint)
            for status in (300, 301, 302, 303, 304, 307, 308, 399):
                with self.subTest(endpoint=endpoint, status=status):
                    calls = []
                    with self.assertRaises(Exception) as raised:
                        transport(
                            endpoint + "?x=1",
                            _fetch=_fake_pinned_fetch(status, b"{}", calls),
                        )
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(
                        getattr(raised.exception, "code", None),
                        "REDIRECT_BLOCKED",
                    )
            for status in (403, 429, 500, 503, 0):
                with self.subTest(endpoint=endpoint, status=status):
                    calls = []
                    with self.assertRaises(Exception) as raised:
                        transport(
                            endpoint + "?x=1",
                            _fetch=_fake_pinned_fetch(status, b"{}", calls),
                        )
                    self.assertEqual(len(calls), 1)
                    code = getattr(raised.exception, "code", raised.exception)
                    self.assertEqual(
                        wiring._vendor_contract.public_error_code(code),
                        "URL_BLOCKED",
                    )

    def test_default_dependencies_bind_all_four_official_endpoints(self):
        wiring = self._wiring()
        deps = wiring.default_dependencies()
        self.assertTrue(callable(deps.search))
        self.assertEqual(
            set(deps.vertical_transports), {"scholar", "news", "images"}
        )
        with self.assertRaises(TypeError):
            deps.vertical_transports["scholar"] = lambda url: {}

    def test_default_vertical_transports_use_exact_fetch_bounds(self):
        wiring = self._wiring()
        bodies = {
            "scholar": _crossref_body([_scholar_item()]),
            "news": _gdelt_body([_news_article()]),
            "images": _commons_body([_commons_page()]),
        }
        for vertical in ("scholar", "news", "images"):
            with self.subTest(vertical=vertical):
                calls = []
                deps = wiring.default_dependencies(
                    _fetch=_fake_pinned_fetch(200, bodies[vertical], calls)
                )
                transport = deps.vertical_transports[vertical]
                response = transport(VERTICAL_ENDPOINTS[vertical] + "?q=fission")
                self.assertEqual(len(calls), 1)
                url, kwargs = calls[0]
                self.assertEqual(url, VERTICAL_ENDPOINTS[vertical] + "?q=fission")
                self.assertEqual(
                    kwargs,
                    {
                        "timeout": 10,
                        "max_response_bytes": 1048576,
                        "max_redirects": 0,
                        "resolver": None,
                        "connection_factory": None,
                    },
                )
                self.assertEqual(response["status"], 200)


class VerticalPinnedBoundaryTests(OfflineTestCase):
    """Real pinned_fetch with fake resolver/connection_factory, socket denied."""

    PINNED_ADDRESS = "93.184.216.34"

    def _seams(self, bodies, statuses=None, factory_error=None):
        import socket as socket_module

        test = self
        resolver_calls = []
        factory_calls = []
        request_calls = []
        read_bounds = []

        def fake_resolver(host, port, type=None):
            resolver_calls.append((host, port))
            return [
                (
                    socket_module.AF_INET,
                    socket_module.SOCK_STREAM,
                    6,
                    "",
                    (test.PINNED_ADDRESS, 0),
                )
            ]

        class FakeResponse:
            def __init__(self, status, body, headers):
                self.status = status
                self._body = body
                self._headers = headers

            def read(self, bound):
                read_bounds.append(bound)
                return self._body

            def getheaders(self):
                return list(self._headers)

        class FakeConnection:
            def __init__(self, hostname, address, timeout=None):
                factory_calls.append((hostname, address, timeout))
                test.assertEqual(address, test.PINNED_ADDRESS)
                test.assertEqual(timeout, 10)
                self.hostname = hostname

            def request(self, method, path, headers=None):
                request_calls.append((method, self.hostname, path, headers))
                test.assertEqual(method, "GET")
                test.assertEqual((headers or {}).get("Host"), self.hostname)

            def getresponse(self):
                status = (statuses or {}).get(self.hostname, 200)
                headers = []
                if 300 <= status <= 399:
                    headers = [("Location", "https://example.com/redirect")]
                return FakeResponse(status, bodies[self.hostname], headers)

            def close(self):
                pass

        def fake_factory(hostname, address, timeout=None):
            if factory_error is not None:
                raise factory_error
            return FakeConnection(hostname, address, timeout=timeout)

        seams = {
            "resolver_calls": resolver_calls,
            "factory_calls": factory_calls,
            "request_calls": request_calls,
            "read_bounds": read_bounds,
        }
        return fake_resolver, fake_factory, seams

    def _wiki_body(self):
        return _wikipedia_action_body(
            [
                {
                    "title": "Nuclear fission",
                    "snippet": "Nuclear fission releases <b>energy</b> slowly.",
                }
            ]
        )

    def test_all_four_official_routes_through_real_pinned_fetch(self):
        bodies = {
            "en.wikipedia.org": self._wiki_body(),
            "api.crossref.org": _crossref_body([_scholar_item()]),
            "api.gdeltproject.org": _gdelt_body([_news_article()]),
            "commons.wikimedia.org": _commons_body([_commons_page()]),
        }
        resolver, factory, seams = self._seams(bodies)
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        deps = module.v3_wiring.default_dependencies(
            _resolver=resolver, _connection_factory=factory
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        answer = json.loads(
            ctx.tools["goat_answer"]["handler"]({"query": "nuclear fission"})
        )
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["source"], "wikipedia")
        filtered = json.loads(
            ctx.tools["goat_filtered_search"]["handler"]({"query": "fission"})
        )
        self.assertTrue(filtered["ok"])
        for vertical, source in (
            ("scholar", "crossref"),
            ("news", "gdelt"),
            ("images", "wikimedia-commons"),
        ):
            with self.subTest(vertical=vertical):
                payload = json.loads(
                    ctx.tools["goat_vertical_search"]["handler"](
                        {"vertical": vertical, "query": "fission"}
                    )
                )
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["source"], source)
                self.assertTrue(payload["results"])
        hosts = sorted(host for host, _port in seams["resolver_calls"])
        self.assertEqual(
            hosts,
            [
                "api.crossref.org",
                "api.gdeltproject.org",
                "commons.wikimedia.org",
                "en.wikipedia.org",
                "en.wikipedia.org",
            ],
        )
        requested_hosts = sorted(host for _m, host, _p, _h in seams["request_calls"])
        self.assertEqual(
            requested_hosts,
            [
                "api.crossref.org",
                "api.gdeltproject.org",
                "commons.wikimedia.org",
                "en.wikipedia.org",
                "en.wikipedia.org",
            ],
        )
        for _hostname, address, timeout in seams["factory_calls"]:
            self.assertEqual(address, self.PINNED_ADDRESS)
            self.assertEqual(timeout, 10)
        for bound in seams["read_bounds"]:
            self.assertEqual(bound, 1048577)
        for method, _host, _path, _headers in seams["request_calls"]:
            self.assertEqual(method, "GET")

    def test_pinned_status_matrix_end_to_end(self):
        import socket as socket_module

        bodies = {
            "en.wikipedia.org": self._wiki_body(),
            "api.crossref.org": _crossref_body([_scholar_item()]),
            "api.gdeltproject.org": _gdelt_body([_news_article()]),
            "commons.wikimedia.org": _commons_body([_commons_page()]),
        }
        for status in (300, 301, 302, 303, 304, 307, 308, 399):
            with self.subTest(status=status):
                resolver, factory, seams = self._seams(
                    bodies, statuses={"api.crossref.org": status}
                )
                tmp, pkgdir = build_fixture_package()
                try:
                    module_name, module = load_fixture_package(pkgdir)
                    try:
                        deps = module.v3_wiring.default_dependencies(
                            _resolver=resolver, _connection_factory=factory
                        )
                        ctx = RecordingContext()
                        module.register(ctx, deps=deps)
                        payload = json.loads(
                            ctx.tools["goat_vertical_search"]["handler"](
                                {"vertical": "scholar", "query": "fission"}
                            )
                        )
                    finally:
                        unload_fixture_package(module_name)
                finally:
                    shutil.rmtree(tmp, True)
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "REDIRECT_BLOCKED"}}
                )
                scholar_requests = [
                    call for call in seams["request_calls"] if call[1] == "api.crossref.org"
                ]
                self.assertEqual(len(scholar_requests), 1)
        for status in (403, 429, 500, 503):
            with self.subTest(status=status):
                resolver, factory, seams = self._seams(
                    bodies, statuses={"api.crossref.org": status}
                )
                tmp, pkgdir = build_fixture_package()
                self.addCleanup(shutil.rmtree, tmp, True)
                module_name, module = load_fixture_package(pkgdir)
                self.addCleanup(unload_fixture_package, module_name)
                deps = module.v3_wiring.default_dependencies(
                    _resolver=resolver, _connection_factory=factory
                )
                ctx = RecordingContext()
                module.register(ctx, deps=deps)
                payload = json.loads(
                    ctx.tools["goat_vertical_search"]["handler"](
                        {"vertical": "scholar", "query": "fission"}
                    )
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
        for failure, body_override in (
            ("timeout", None),
            ("malformed", b"not json {{{"),
            ("overflow", b"x" * (1048576 + 1)),
        ):
            with self.subTest(failure=failure):
                bodies_case = dict(bodies)
                if body_override is not None:
                    bodies_case["api.crossref.org"] = body_override
                error = (
                    socket_module.timeout("timed out")
                    if failure == "timeout"
                    else None
                )
                if failure == "timeout":
                    def timeout_factory(hostname, address, timeout=None):
                        raise socket_module.timeout("timed out")

                    resolver, _, seams = self._seams(bodies_case)
                    factory = timeout_factory
                else:
                    resolver, factory, seams = self._seams(bodies_case)
                tmp, pkgdir = build_fixture_package()
                self.addCleanup(shutil.rmtree, tmp, True)
                module_name, module = load_fixture_package(pkgdir)
                self.addCleanup(unload_fixture_package, module_name)
                deps = module.v3_wiring.default_dependencies(
                    _resolver=resolver, _connection_factory=factory
                )
                ctx = RecordingContext()
                module.register(ctx, deps=deps)
                payload = json.loads(
                    ctx.tools["goat_vertical_search"]["handler"](
                        {"vertical": "scholar", "query": "fission"}
                    )
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                del error

    def test_default_import_and_register_need_no_network_subprocess_or_threads(self):
        import subprocess
        import threading

        blocked = AssertionError("subprocess disabled during offline test")
        real_popen = subprocess.Popen
        real_run = subprocess.run
        subprocess.Popen = lambda *a, **k: (_ for _ in ()).throw(blocked)
        subprocess.run = lambda *a, **k: (_ for _ in ()).throw(blocked)
        self.addCleanup(setattr, subprocess, "Popen", real_popen)
        self.addCleanup(setattr, subprocess, "run", real_run)
        before_threads = threading.active_count()
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        deps = module.v3_wiring.default_dependencies()
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        self.assertEqual(len(ctx.tools), 7)
        self.assertEqual(threading.active_count(), before_threads)


if __name__ == "__main__":
    unittest.main()
