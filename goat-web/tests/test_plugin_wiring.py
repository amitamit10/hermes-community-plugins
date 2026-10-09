import importlib
import importlib.util
import shutil
import socket
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = ROOT / "plugins" / "goat-web"
EXPECTED_TOOLS = {"goat_search", "goat_extract", "goat_crawl", "goat_probe"}


class PluginWiringTests(unittest.TestCase):
    def test_hermes_plugin_validator_accepts_directory(self):
        hermes = shutil.which("hermes")
        self.assertIsNotNone(hermes, "hermes CLI is required for plugin validation")
        result = subprocess.run(
            [hermes, "plugins", "validate", str(PLUGIN_DIR)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Validation passed.", result.stdout)

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
