"""Milestone 07a: manifest surfaces vs actual built-package registration.

Builds the portable bundle with the real builder (imported by file spec)
into a fresh directory under the approved ``artifacts/wiring-build`` root,
loads the built package, registers a recording context, and asserts both
manifest surfaces describe that actual registration.

Normative expectations are owned constants below; these tests only read
owned sources and fresh build outputs, never external plan documents.
"""

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
import uuid
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
EXPECTED_VERSION = "0.2.0"
EXPECTED_ENTRYPOINT = "__init__:register"
EXPECTED_TOOLSET = "goat_web"
FORBIDDEN_ALIASES = frozenset({"goat_scholar", "goat_news", "goat_images"})
FORBIDDEN_MANIFEST_KEYS = frozenset(
    {
        "overrides",
        "override",
        "permissions",
        "auth",
        "api_key",
        "api_keys",
        "secrets",
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
    tmp = tempfile.mkdtemp(prefix="goat-manifest-", dir=str(BUILD_ROOT))
    test_case.addCleanup(shutil.rmtree, tmp, True)
    output = Path(tmp) / "hermes-goat-web"
    builder = _load_builder()
    builder.build_bundle(WIRING_ROOT, output)
    return output


def _load_built_package(bundle_dir):
    module_name = "goat_manifest_pkg_" + uuid.uuid4().hex
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


def _parse_simple_plugin_yaml(text):
    """Parse the flat plugin.yaml shape with stdlib only.

    Supports top-level ``key: scalar`` lines, inline ``[]`` empty lists,
    and ``key:`` followed by ``  - item`` entries. Anything else raises.
    """
    parsed = {}
    current_list = None
    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.strip().startswith("#"):
            continue
        if raw_line.startswith((" ", "\t")):
            stripped = raw_line.strip()
            if not stripped.startswith("- ") or current_list is None:
                raise AssertionError("unexpected indented line: %r" % raw_line)
            current_list.append(stripped[2:].strip())
            continue
        if ":" not in raw_line:
            raise AssertionError("unexpected yaml line: %r" % raw_line)
        key, _, value = raw_line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key or " " in key:
            raise AssertionError("unexpected yaml key line: %r" % raw_line)
        if value == "":
            current_list = []
            parsed[key] = current_list
        elif value == "[]":
            current_list = None
            parsed[key] = []
        else:
            current_list = None
            parsed[key] = value
    return parsed


class RecordingContext:
    def __init__(self):
        self.tools = {}

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs


class ManifestRegistrationTests(unittest.TestCase):
    def _registration_and_manifests(self):
        bundle = _build_fresh_bundle(self)
        module_name, module = _load_built_package(bundle)
        self.addCleanup(_unload_built_package, module_name)
        ctx = RecordingContext()
        module.register(ctx)
        plugin_yaml = _parse_simple_plugin_yaml(
            (bundle / "plugin.yaml").read_text(encoding="utf-8")
        )
        plugin_json = json.loads(
            (bundle / "hermes-goat-web.plugin.json").read_text(encoding="utf-8")
        )
        return ctx.tools, plugin_yaml, plugin_json

    def test_both_manifests_declare_version_0_2_0(self):
        tools, plugin_yaml, plugin_json = self._registration_and_manifests()
        del tools
        self.assertEqual(plugin_yaml.get("version"), EXPECTED_VERSION)
        self.assertEqual(plugin_json.get("version"), EXPECTED_VERSION)

    def test_both_manifests_use_init_register_entrypoint(self):
        tools, plugin_yaml, plugin_json = self._registration_and_manifests()
        del tools
        self.assertEqual(plugin_yaml.get("entrypoint"), EXPECTED_ENTRYPOINT)
        self.assertEqual(plugin_json.get("entrypoint"), EXPECTED_ENTRYPOINT)

    def test_registered_seven_names_equal_both_manifests(self):
        tools, plugin_yaml, plugin_json = self._registration_and_manifests()
        registered = set(tools)
        self.assertEqual(registered, set(EXPECTED_SEVEN))
        self.assertEqual(set(plugin_yaml.get("tools", [])), set(EXPECTED_SEVEN))
        self.assertEqual(
            set(plugin_yaml.get("provides_tools", [])), set(EXPECTED_SEVEN)
        )
        self.assertEqual(set(plugin_json.get("tools", [])), set(EXPECTED_SEVEN))
        for alias in FORBIDDEN_ALIASES:
            self.assertNotIn(alias, registered)
            self.assertNotIn(alias, plugin_yaml.get("tools", []))
            self.assertNotIn(alias, plugin_json.get("tools", []))

    def test_registered_toolset_is_goat_web(self):
        tools, _plugin_yaml, _plugin_json = self._registration_and_manifests()
        self.assertEqual(len(tools), 7)
        for name, tool in tools.items():
            with self.subTest(tool=name):
                self.assertEqual(tool["toolset"], EXPECTED_TOOLSET)
                self.assertEqual(tool["schema"]["name"], name)
                self.assertTrue(callable(tool["handler"]))

    def test_manifests_have_empty_surfaces_and_pinned_egress(self):
        _tools, plugin_yaml, plugin_json = self._registration_and_manifests()
        for key in ("capabilities", "dependencies", "python_dependencies"):
            with self.subTest(surface=key):
                self.assertIn(key, plugin_yaml)
                self.assertEqual(plugin_yaml[key], [])
        for key in ("requires_env", "credentials"):
            with self.subTest(surface=key):
                if key in plugin_yaml:
                    self.assertEqual(plugin_yaml[key], [])
        self.assertEqual(plugin_json.get("credentials"), [])
        self.assertEqual(
            plugin_json.get("network_services"), ["pinned-https-egress"]
        )

    def test_manifests_require_no_perms_auth_or_overrides(self):
        _tools, plugin_yaml, plugin_json = self._registration_and_manifests()
        for key in FORBIDDEN_MANIFEST_KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, plugin_yaml)
                self.assertNotIn(key, plugin_json)
        self.assertNotIn("override", json.dumps(plugin_yaml).lower())


if __name__ == "__main__":
    unittest.main()
