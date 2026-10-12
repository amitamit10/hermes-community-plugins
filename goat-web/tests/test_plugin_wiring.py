"""Milestone 07a: plugin wiring against the real built bundle (TDD).

Loads the portable bundle produced by the real builder into a fresh
directory under the approved ``artifacts/wiring-build`` root. The source
``goat-web/plugins/goat-web`` directory is a template, not installable: it
imports the private ``._goat_v3_vendor`` package that only exists inside a
built bundle.

Native Hermes manager validation is NOT claimed here; it is the mandatory
separate gate owned by ``test_hermes_registration``. This module asserts the
built inventory instead of invoking a live validator.

Normative expectations are owned constants below; these tests only read
owned sources and fresh build outputs, never external plan documents.
"""

import importlib
import importlib.util
import json
import shutil
import socket
import sys
import tempfile
import unittest
import uuid
from unittest import mock
from pathlib import Path


WIRING_ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = WIRING_ROOT / "goat-web" / "scripts" / "build_plugin_bundle.py"
BUILD_ROOT = WIRING_ROOT.parent / "artifacts" / "wiring-build"

# Self-contained normative expectations (owned by this test, not the plan).
EXPECTED_SEVEN = frozenset(
    {
        "goat_search",
        "goat_extract",
        "goat_crawl",
        "goat_probe",
        "goat_answer",
        "goat_filtered_search",
        "goat_vertical_search",
    }
)
EXPECTED_LEGACY_FOUR = frozenset(
    {"goat_search", "goat_extract", "goat_crawl", "goat_probe"}
)
EXPECTED_TOOLSET = "goat_web"
FORBIDDEN_ALIASES = frozenset({"goat_scholar", "goat_news", "goat_images"})
EXACT_URL_BLOCKED = {"ok": False, "error": {"code": "URL_BLOCKED"}}

EXPECTED_BUNDLE_FILES = frozenset(
    {
        "__init__.py",
        "goat_tools.py",
        "adapters.py",
        "url_gate.py",
        "tool_schemas.py",
        "v3_wiring.py",
        "search_providers.py",
        "plugin.yaml",
        "_goat_v3_vendor/answer_synth.py",
        "_goat_v3_vendor/search_filters.py",
        "_goat_v3_vendor/free_verticals.py",
        "_goat_v3_vendor/free_stack.py",
        "_goat_v3_vendor/ssrf_guard.py",
        "_goat_v3_vendor/ddg_parser.py",
        "_goat_v3_vendor/result_contract.py",
        "_goat_v3_vendor/__init__.py",
        "hermes-goat-web.plugin.json",
        "LICENSE",
        "VENDOR-LICENSE",
        "VENDOR-PROVENANCE.md",
        "bundle-manifest.json",
    }
)


def _load_builder():
    """Import the real bundle builder by file spec (no sys.path edits)."""
    module_name = "goat_bundle_builder_" + uuid.uuid4().hex
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
    return module


def _build_fresh_bundle(test_case):
    """Build a fresh bundle under the approved scratch root; return its dir."""
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="goat-wiring-", dir=str(BUILD_ROOT))
    test_case.addCleanup(shutil.rmtree, tmp, True)
    output = Path(tmp) / "hermes-goat-web"
    builder = _load_builder()
    builder.build_bundle(WIRING_ROOT, output)
    return output


def _load_built_package(bundle_dir):
    module_name = "goat_web_wiring_test_plugin_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(
        module_name,
        bundle_dir / "__init__.py",
        submodule_search_locations=[str(bundle_dir)],
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load built GOAT plugin package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module_name, module


def _unload_built_package(module_name):
    for loaded_name in tuple(sys.modules):
        if loaded_name == module_name or loaded_name.startswith(module_name + "."):
            sys.modules.pop(loaded_name, None)


def _registered_tools(module, deps=None):
    tools = {}

    class RecordingContext:
        def register_tool(self, **kwargs):
            tools[kwargs["name"]] = kwargs

    if deps is None:
        module.register(RecordingContext())
    else:
        module.register(RecordingContext(), deps=deps)
    return tools


class PluginWiringTests(unittest.TestCase):
    def test_built_bundle_passes_builder_check_with_exact_inventory(self):
        # Native Hermes manager validation is the separate mandatory gate
        # owned by test_hermes_registration; this unit asserts the built
        # inventory instead of claiming native validation.
        bundle = _build_fresh_bundle(self)
        builder = _load_builder()
        builder.check_bundle(WIRING_ROOT, bundle)
        found = set()
        for current, _dirnames, filenames in __import__("os").walk(bundle):
            for name in filenames:
                found.add(str((Path(current) / name).relative_to(bundle)))
        self.assertEqual(found, EXPECTED_BUNDLE_FILES)

    def test_seven_tools_registered_with_real_ctx(self):
        bundle = _build_fresh_bundle(self)
        module_name, module = _load_built_package(bundle)
        self.addCleanup(_unload_built_package, module_name)
        tools = _registered_tools(module)
        self.assertEqual(set(tools), set(EXPECTED_SEVEN))
        for name, tool in tools.items():
            with self.subTest(tool=name):
                self.assertEqual(tool["toolset"], EXPECTED_TOOLSET)
                self.assertEqual(tool["schema"]["name"], name)
                self.assertTrue(callable(tool["handler"]))
        for alias in FORBIDDEN_ALIASES:
            self.assertNotIn(alias, tools)

    def test_registered_search_handler_accepts_max_results(self):
        bundle = _build_fresh_bundle(self)
        module_name, module = _load_built_package(bundle)
        self.addCleanup(_unload_built_package, module_name)
        handler = _registered_tools(module)["goat_search"]["handler"]
        body = "".join(
            f'<a class="result__a" href="https://example.com/{index}">Title {index}</a>'
            f'<div class="result__snippet">Snippet {index}</div>'
            for index in range(4)
        )
        with mock.patch.dict(
            module.goat_handlers.__globals__,
            {"pinned_fetch": lambda _url: {"status": 200, "body": body}},
        ):
            result = json.loads(handler({"query": "bounded", "max_results": 2}))
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual([item["title"] for item in result["results"]], ["Title 0", "Title 1"])

    def test_json_handler_maps_binding_and_bad_argument_errors_to_public_contract(self):
        bundle = _build_fresh_bundle(self)
        module_name, module = _load_built_package(bundle)
        self.addCleanup(_unload_built_package, module_name)
        tools = _registered_tools(module)
        handler = tools["goat_search"]["handler"]
        binding_error = json.loads(handler({"query": "query", "unexpected": True}))

        def bad_argument(**_kwargs):
            raise ValueError("invalid argument")

        parameters = tools["goat_search"]["schema"]["parameters"]
        argument_error = json.loads(
            module._json_handler(bad_argument, parameters)({"query": "query"})
        )
        self.assertEqual(binding_error, EXACT_URL_BLOCKED)
        self.assertEqual(argument_error, EXACT_URL_BLOCKED)

    def test_registered_crawl_schema_documents_bounded_controls(self):
        bundle = _build_fresh_bundle(self)
        module_name, module = _load_built_package(bundle)
        self.addCleanup(_unload_built_package, module_name)
        schema = _registered_tools(module)["goat_crawl"]["schema"]["parameters"]
        properties = schema["properties"]
        self.assertEqual(set(properties), {"url", "max_depth", "max_pages"})
        self.assertEqual(properties["max_depth"]["minimum"], 0)
        self.assertEqual(properties["max_depth"]["maximum"], 2)
        self.assertEqual(properties["max_pages"]["minimum"], 1)
        self.assertEqual(properties["max_pages"]["maximum"], 10)

    def test_registered_schemas_reject_additional_properties(self):
        bundle = _build_fresh_bundle(self)
        module_name, module = _load_built_package(bundle)
        self.addCleanup(_unload_built_package, module_name)
        tools = _registered_tools(module)
        self.assertEqual(set(tools), set(EXPECTED_SEVEN))
        for name, tool in tools.items():
            with self.subTest(tool=name):
                self.assertIs(tool["schema"]["parameters"]["additionalProperties"], False)
        search_properties = tools["goat_search"]["schema"]["parameters"]["properties"]
        self.assertEqual(search_properties["max_results"]["minimum"], 1)
        self.assertEqual(search_properties["max_results"]["maximum"], 5)

    def test_goat_tools_register_returns_four_callables(self):
        bundle = _build_fresh_bundle(self)
        module_name, module = _load_built_package(bundle)
        self.addCleanup(_unload_built_package, module_name)
        goat_tools = importlib.import_module(module_name + ".goat_tools")
        handlers = goat_tools.register()
        self.assertEqual(set(handlers), set(EXPECTED_LEGACY_FOUR))
        self.assertTrue(all(callable(handler) for handler in handlers.values()))
        del module

    def test_plugin_import_and_registration_do_not_use_network(self):
        calls = []

        def reject_network(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("network used during plugin import")

        bundle = _build_fresh_bundle(self)
        module_name = "goat_plugin_import_smoke_" + uuid.uuid4().hex
        spec = importlib.util.spec_from_file_location(
            module_name,
            bundle / "__init__.py",
            submodule_search_locations=[str(bundle)],
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        original_getaddrinfo = socket.getaddrinfo
        original_create_connection = socket.create_connection
        socket.getaddrinfo = reject_network
        socket.create_connection = reject_network
        registered = []
        try:
            spec.loader.exec_module(module)
            context = type(
                "RecordingContext",
                (),
                {
                    "register_tool": lambda self, name, *args, **kwargs: registered.append(name)
                },
            )()
            module.register(context)
        finally:
            socket.getaddrinfo = original_getaddrinfo
            socket.create_connection = original_create_connection
            _unload_built_package(module_name)
        self.assertEqual(set(registered), set(EXPECTED_SEVEN))
        self.assertEqual(len(registered), 7)


if __name__ == "__main__":
    unittest.main()
