import importlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parent.parent
PLUGIN_DIR = ROOT / "plugins" / "goat-web"
sys.path.insert(0, str(PLUGIN_DIR))


class PluginManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "hermes-goat-web.plugin.json").read_text())

    def test_manifest_has_valid_required_metadata(self):
        manifest = self.manifest
        self.assertIsInstance(manifest, dict)
        self.assertEqual(manifest.get("name"), "hermes-goat-web")
        self.assertIsInstance(manifest.get("version"), str)
        self.assertTrue(manifest["version"])
        self.assertIsInstance(manifest.get("risk_tier"), str)
        self.assertTrue(manifest["risk_tier"])
        self.assertIsInstance(manifest.get("tools"), list)
        self.assertIsInstance(manifest.get("credentials"), list)
        self.assertIsInstance(manifest.get("network_services"), list)
        self.assertIsInstance(manifest.get("entrypoint"), str)

    def test_manifest_entrypoint_exists_and_is_callable(self):
        module_name, function_name = self.manifest["entrypoint"].rsplit(".", 1)
        entrypoint = getattr(importlib.import_module(module_name), function_name)
        self.assertTrue(callable(entrypoint))

    def test_manifest_tools_are_registered(self):
        module_name, function_name = self.manifest["entrypoint"].rsplit(".", 1)
        handlers = getattr(importlib.import_module(module_name), function_name)()
        self.assertEqual(set(self.manifest["tools"]), set(handlers))
        self.assertEqual(
            set(self.manifest["tools"]),
            {"goat_search", "goat_extract", "goat_crawl", "goat_probe"},
        )
        self.assertTrue(all(callable(handler) for handler in handlers.values()))

    def test_manifest_declares_pinned_https_egress(self):
        self.assertTrue(self.manifest["network_services"])
        self.assertEqual(self.manifest["network_services"], ["pinned-https-egress"])


if __name__ == "__main__":
    unittest.main()
