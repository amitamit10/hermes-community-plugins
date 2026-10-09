import importlib
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = ROOT / "plugins" / "goat-web"
EXPECTED_TOOLS = {"goat_search", "goat_extract", "goat_crawl", "goat_probe"}


def _load_plugin_package():
    module_name = "goat_web_wiring_test_plugin"
    for loaded_name in tuple(sys.modules):
        if loaded_name == module_name or loaded_name.startswith(module_name + "."):
            sys.modules.pop(loaded_name, None)
    spec = importlib.util.spec_from_file_location(
        module_name,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load GOAT plugin package")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module_name, module


def _unload_plugin_package(module_name):
    for loaded_name in tuple(sys.modules):
        if loaded_name == module_name or loaded_name.startswith(module_name + "."):
            sys.modules.pop(loaded_name, None)


def _registered_tools(module):
    tools = {}

    class RecordingContext:
        def register_tool(self, **kwargs):
            tools[kwargs["name"]] = kwargs

    module.register(RecordingContext())
    return tools


class PluginWiringTests(unittest.TestCase):
    def test_hermes_plugin_validator_accepts_directory(self):
        hermes = shutil.which("hermes")
        self.assertIsNotNone(hermes, "hermes CLI is required for plugin validation")
        with tempfile.TemporaryDirectory(prefix="goat-web-validate-") as temporary_directory:
            copy = Path(temporary_directory) / "goat-web"
            shutil.copytree(PLUGIN_DIR, copy)
            result = subprocess.run(
                [hermes, "plugins", "validate", str(copy)],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Validation passed.", result.stdout)

    def test_registered_search_handler_accepts_max_results(self):
        module_name, module = _load_plugin_package()
        try:
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
        finally:
            _unload_plugin_package(module_name)

    def test_json_handler_maps_binding_and_bad_argument_errors_to_public_contract(self):
        module_name, module = _load_plugin_package()
        try:
            handler = _registered_tools(module)["goat_search"]["handler"]
            binding_error = json.loads(handler({"query": "query", "unexpected": True}))

            def bad_argument():
                raise ValueError("invalid argument")

            argument_error = json.loads(module._json_handler(bad_argument)({}))
            self.assertEqual(binding_error, {"error": {"code": "URL_BLOCKED"}})
            self.assertEqual(argument_error, {"error": {"code": "URL_BLOCKED"}})
        finally:
            _unload_plugin_package(module_name)

    def test_registered_crawl_schema_documents_bounded_controls(self):
        module_name, module = _load_plugin_package()
        try:
            schema = _registered_tools(module)["goat_crawl"]["schema"]["parameters"]
            properties = schema["properties"]
            self.assertEqual(set(properties), {"url", "max_depth", "max_pages"})
            self.assertEqual(properties["max_depth"]["minimum"], 0)
            self.assertEqual(properties["max_depth"]["maximum"], 2)
            self.assertEqual(properties["max_pages"]["minimum"], 1)
            self.assertEqual(properties["max_pages"]["maximum"], 10)
        finally:
            _unload_plugin_package(module_name)

    def test_registered_schemas_reject_additional_properties(self):
        module_name, module = _load_plugin_package()
        try:
            tools = _registered_tools(module)
            for name, tool in tools.items():
                with self.subTest(tool=name):
                    self.assertIs(tool["schema"]["parameters"]["additionalProperties"], False)
            search_properties = tools["goat_search"]["schema"]["parameters"]["properties"]
            self.assertEqual(search_properties["max_results"]["minimum"], 1)
            self.assertEqual(search_properties["max_results"]["maximum"], 5)
        finally:
            _unload_plugin_package(module_name)

    def test_goat_tools_register_returns_four_callables(self):
        sys.path.insert(0, str(PLUGIN_DIR))
        try:
            module = importlib.import_module("goat_tools")
        finally:
            sys.path.remove(str(PLUGIN_DIR))
        handlers = module.register()
        self.assertEqual(set(handlers), EXPECTED_TOOLS)
        self.assertTrue(all(callable(handler) for handler in handlers.values()))

    def test_plugin_import_and_registration_do_not_use_network(self):
        calls = []

        def reject_network(*args, **kwargs):
            calls.append((args, kwargs))
            raise AssertionError("network used during plugin import")

        context = type(
            "RecordingContext",
            (),
            {"register_tool": lambda self, name, *args, **kwargs: calls.append(name)},
        )()
        module_name = "goat_plugin_import_smoke"
        spec = importlib.util.spec_from_file_location(
            module_name,
            PLUGIN_DIR / "__init__.py",
            submodule_search_locations=[str(PLUGIN_DIR)],
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        module.__path__ = [str(PLUGIN_DIR)]
        sys.modules[module_name] = module
        original_getaddrinfo = socket.getaddrinfo
        original_create_connection = socket.create_connection
        socket.getaddrinfo = reject_network
        socket.create_connection = reject_network
        try:
            spec.loader.exec_module(module)
            module.register(context)
        finally:
            socket.getaddrinfo = original_getaddrinfo
            socket.create_connection = original_create_connection
            for name in tuple(sys.modules):
                if name == module_name or name.startswith(module_name + "."):
                    sys.modules.pop(name, None)
        self.assertEqual(set(calls), EXPECTED_TOOLS)
        self.assertEqual(len(calls), 4)


if __name__ == "__main__":
    unittest.main()
