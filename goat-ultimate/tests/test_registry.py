"""Validate the canonical GOAT Ultimate capability registry with unittest."""

import copy
import importlib.util
import json
import shutil
import socket
import sys
import tempfile
import unittest
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY_PATH = ROOT / "registry" / "capabilities.json"
MIRROR_PATH = ROOT / "skills" / "goat-ultimate" / "registry" / "capabilities.json"
WIRING_ROOT = ROOT.parent
BUILD_SCRIPT = WIRING_ROOT / "goat-web" / "scripts" / "build_plugin_bundle.py"
BUILD_ROOT = WIRING_ROOT.parent / "artifacts" / "wiring-build"
EXPECTED_CLASSES = {
    "web-search",
    "extraction",
    "browser",
    "crawl",
    "rss",
    "api-automation",
    "media",
    "docs-artifacts",
    "sheets",
    "maps",
    "memory",
}
SOURCES = ["builtin", "bundled", "local", "hub", "goat", "paid"]
STATUSES = ["keep", "route", "future"]
CLASSIFICATIONS = ["canonical-free", "route", "future-unavailable"]
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"

EXPECTED_ROUTES = [
    {
        "id": "answer",
        "task_class": "web-search",
        "tool": "goat_answer",
        "arguments": {},
        "provider_id": "wikipedia",
        "status": "route",
        "on_error": "fail_closed_no_fallback",
    },
    {
        "id": "filtered-search",
        "task_class": "web-search",
        "tool": "goat_filtered_search",
        "arguments": {},
        "provider_id": "wikipedia",
        "status": "route",
        "on_error": "fail_closed_no_fallback",
    },
    {
        "id": "scholar",
        "task_class": "web-search",
        "tool": "goat_vertical_search",
        "arguments": {"vertical": "scholar"},
        "provider_id": "crossref",
        "status": "route",
        "on_error": "fail_closed_no_fallback",
    },
    {
        "id": "news",
        "task_class": "web-search",
        "tool": "goat_vertical_search",
        "arguments": {"vertical": "news"},
        "provider_id": "gdelt",
        "status": "route",
        "on_error": "fail_closed_no_fallback",
    },
    {
        "id": "images",
        "task_class": "web-search",
        "tool": "goat_vertical_search",
        "arguments": {"vertical": "images"},
        "provider_id": "wikimedia-commons",
        "status": "route",
        "on_error": "fail_closed_no_fallback",
    },
]
ROUTE_KEYS = ["id", "task_class", "tool", "arguments", "provider_id", "status", "on_error"]
ROUTE_IDS = ["answer", "filtered-search", "scholar", "news", "images"]
ROUTE_TOOLS = ["goat_answer", "goat_filtered_search", "goat_vertical_search"]
ROUTE_PROVIDERS = ["wikipedia", "crossref", "gdelt", "wikimedia-commons"]
EXPECTED_ALL_TOOLS = {
    "goat_search",
    "goat_extract",
    "goat_crawl",
    "goat_probe",
    "goat_answer",
    "goat_filtered_search",
    "goat_vertical_search",
}
ORIGINAL_PROVIDER_IDS = [
    "anysearch",
    "searxng",
    "wikipedia",
    "duckduckgo",
    "tavily",
    "exa",
    "firecrawl",
    "serper",
    "browserbase-stealth",
    "bright-data",
    "donsetch",
]
NEW_PROVIDERS = [
    {
        "id": "crossref",
        "name": "Crossref",
        "classification": "route",
        "capabilities": ["web-search"],
        "access": "anonymous",
        "requires_key": False,
        "key_optional": False,
    },
    {
        "id": "gdelt",
        "name": "GDELT",
        "classification": "route",
        "capabilities": ["web-search"],
        "access": "anonymous",
        "requires_key": False,
        "key_optional": False,
    },
    {
        "id": "wikimedia-commons",
        "name": "Wikimedia Commons",
        "classification": "route",
        "capabilities": ["web-search"],
        "access": "anonymous",
        "requires_key": False,
        "key_optional": False,
    },
]
EXPECTED_PAID_GATE_PROVIDERS = [
    "Firecrawl",
    "Exa",
    "Tavily",
    "Serper",
    "Browserbase stealth",
    "Bright Data",
]
EXPECTED_FALLBACK_ORDER = ["anysearch", "searxng", "wikipedia", "duckduckgo"]

# Minimal, dependency-free JSON Schema subset used by this registry. The
# instance validator below implements every keyword declared in this schema.
REGISTRY_SCHEMA = {
    "$schema": SCHEMA_URI,
    "type": "object",
    "required": ["$schema", "schema_version", "counts", "paid_backend_gate", "capabilities", "providers", "operation_routes"],
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string", "const": SCHEMA_URI},
        "schema_version": {"type": "integer", "const": 3},
        "providers": {
            "type": "object",
            "required": ["classifications", "canonical_by_capability", "fallback_order", "fallback_policy", "entries"],
            "properties": {
                "classifications": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                "canonical_by_capability": {"type": "object"},
                "fallback_order": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                "fallback_policy": {"type": "object"},
                "entries": {"type": "array", "minItems": 14, "maxItems": 14},
            },
        },
        "counts": {
            "type": "object",
            "required": ["task_classes", "by_status", "by_source", "providers", "by_provider_classification"],
            "additionalProperties": False,
            "properties": {
                "task_classes": {"type": "integer", "minimum": 0},
                "providers": {"type": "integer", "minimum": 0},
                "by_provider_classification": {
                    "type": "object",
                    "required": CLASSIFICATIONS,
                    "additionalProperties": False,
                    "properties": {key: {"type": "integer", "minimum": 0} for key in CLASSIFICATIONS},
                },
                "by_status": {
                    "type": "object",
                    "required": STATUSES,
                    "additionalProperties": False,
                    "properties": {status: {"type": "integer", "minimum": 0} for status in STATUSES},
                },
                "by_source": {
                    "type": "object",
                    "required": SOURCES,
                    "additionalProperties": False,
                    "properties": {source: {"type": "integer", "minimum": 0} for source in SOURCES},
                },
            },
        },
        "paid_backend_gate": {
            "type": "object",
            "required": ["requires_key", "missing_config_error", "on_missing_config", "providers"],
            "additionalProperties": False,
            "properties": {
                "requires_key": {"type": "boolean", "const": True},
                "missing_config_error": {"type": "string", "const": "MISSING_CONFIG"},
                "on_missing_config": {"type": "string", "const": "fail_closed_no_fallback"},
                "providers": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1},
                },
            },
        },
        "capabilities": {
            "type": "array",
            "minItems": len(EXPECTED_CLASSES),
            "maxItems": len(EXPECTED_CLASSES),
            "items": {
                "type": "object",
                "required": ["name", "canonical_provider", "source", "overlaps_resolved", "status"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "enum": sorted(EXPECTED_CLASSES)},
                    "canonical_provider": {"type": "string", "minLength": 1},
                    "source": {"type": "string", "enum": SOURCES},
                    "overlaps_resolved": {
                        "type": "array",
                        "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "status": {"type": "string", "enum": STATUSES},
                },
            },
        },
        "operation_routes": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "uniqueItems": True,
            "items": {
                "type": "object",
                "required": ROUTE_KEYS,
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string", "enum": ROUTE_IDS},
                    "task_class": {"type": "string", "enum": ["web-search"]},
                    "tool": {"type": "string", "enum": ROUTE_TOOLS},
                    "arguments": {"type": "object"},
                    "provider_id": {"type": "string", "enum": ROUTE_PROVIDERS},
                    "status": {"type": "string", "enum": ["route"]},
                    "on_error": {"type": "string", "enum": ["fail_closed_no_fallback"]},
                },
                "enum": EXPECTED_ROUTES,
            },
        },
    },
}


def _validate_json_schema(instance, schema, path="$", errors=None):
    """Validate the small JSON Schema subset declared above."""
    if errors is None:
        errors = []

    expected_type = schema.get("type")
    valid_types = {
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
        "string": lambda value: isinstance(value, str),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
    }
    if expected_type in valid_types and not valid_types[expected_type](instance):
        errors.append(f"{path}: expected {expected_type}")
        return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} is not in enum")
    if expected_type == "string" and len(instance) < schema.get("minLength", 0):
        errors.append(f"{path}: string is shorter than minLength")
    if expected_type == "integer" and instance < schema.get("minimum", 0):
        errors.append(f"{path}: integer is below minimum")

    if expected_type == "object":
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extras = set(instance) - set(properties)
            if extras:
                errors.append(f"{path}: unexpected properties {sorted(extras)!r}")
        for key, value in instance.items():
            if key in properties:
                _validate_json_schema(value, properties[key], f"{path}.{key}", errors)

    if expected_type == "array":
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: array is shorter than minItems")
        if len(instance) > schema.get("maxItems", float("inf")):
            errors.append(f"{path}: array is longer than maxItems")
        if schema.get("uniqueItems") and len(instance) != len({json.dumps(item, sort_keys=True) for item in instance}):
            errors.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if item_schema:
            for index, value in enumerate(instance):
                _validate_json_schema(value, item_schema, f"{path}[{index}]", errors)

    return errors


_BUILDER_MODULE = None


def _load_builder():
    global _BUILDER_MODULE
    if _BUILDER_MODULE is not None:
        return _BUILDER_MODULE
    spec = importlib.util.spec_from_file_location("goat_v3_bundle_builder_reg1", BUILD_SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load bundle builder by file spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules["goat_v3_bundle_builder_reg1"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop("goat_v3_bundle_builder_reg1", None)
        raise
    _BUILDER_MODULE = module
    return module


def _build_and_register():
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="goat-reg1-", dir=str(BUILD_ROOT))
    pkgdir = Path(tmp) / "hermes-goat-web"
    _load_builder().build_bundle(WIRING_ROOT, pkgdir)
    module_name = "goat_reg1_pkg_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(
        module_name, pkgdir / "__init__.py", submodule_search_locations=[str(pkgdir)]
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
    return tmp, module_name, module


def _unload(module_name):
    for loaded in tuple(sys.modules):
        if loaded == module_name or loaded.startswith(module_name + "."):
            sys.modules.pop(loaded, None)


class _RecordingContext:
    def __init__(self):
        self.tools = {}

    def register_tool(self, **kwargs):
        self.tools[kwargs["name"]] = kwargs


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with REGISTRY_PATH.open(encoding="utf-8") as registry_file:
            cls.registry = json.load(registry_file)

    def test_json_schema_valid(self):
        errors = _validate_json_schema(self.registry, REGISTRY_SCHEMA)
        self.assertEqual(errors, [], "Registry schema validation errors:\n" + "\n".join(errors))

    def test_schema_version_is_3(self):
        self.assertEqual(self.registry["schema_version"], 3)

    def test_exactly_one_canonical_target_per_task_class(self):
        capabilities = self.registry["capabilities"]
        names = Counter(entry["name"] for entry in capabilities)
        self.assertEqual(set(names), EXPECTED_CLASSES)
        self.assertTrue(all(count == 1 for count in names.values()))
        for entry in capabilities:
            self.assertIsInstance(entry["canonical_provider"], str)
            self.assertTrue(entry["canonical_provider"].strip())

    def test_duplicate_canonical_targets_are_explicitly_resolved(self):
        by_target = defaultdict(list)
        for entry in self.registry["capabilities"]:
            by_target[entry["canonical_provider"]].append(entry)

        for target, entries in by_target.items():
            if len(entries) > 1:
                resolved = any(target in entry["overlaps_resolved"] for entry in entries)
                self.assertTrue(
                    resolved,
                    f"Canonical target {target!r} is shared without appearing in overlaps_resolved",
                )

    def test_recorded_counts_match_registry(self):
        capabilities = self.registry["capabilities"]
        counts = self.registry["counts"]
        self.assertEqual(counts["task_classes"], len(capabilities))
        self.assertEqual(
            counts["by_status"],
            {status: Counter(entry["status"] for entry in capabilities).get(status, 0) for status in STATUSES},
        )
        self.assertEqual(
            counts["by_source"],
            {source: Counter(entry["source"] for entry in capabilities).get(source, 0) for source in SOURCES},
        )

    def test_task_class_counts_unchanged(self):
        counts = self.registry["counts"]
        self.assertEqual(counts["task_classes"], 11)
        self.assertEqual(counts["by_status"], {"keep": 4, "route": 7, "future": 0})
        self.assertEqual(
            counts["by_source"],
            {"builtin": 2, "bundled": 0, "local": 6, "hub": 0, "goat": 3, "paid": 0},
        )

    def test_operation_routes_exact_identity(self):
        self.assertIn("operation_routes", self.registry)
        self.assertEqual(self.registry["operation_routes"], EXPECTED_ROUTES)
        by_id = {route["id"]: route for route in self.registry["operation_routes"]}
        self.assertEqual(set(by_id), set(ROUTE_IDS))
        for route in EXPECTED_ROUTES:
            self.assertEqual(by_id[route["id"]], route)
        for route in self.registry["operation_routes"]:
            self.assertEqual(sorted(route), sorted(ROUTE_KEYS))

    def test_operation_routes_validator_rejects_mutations(self):
        self.assertIn("operation_routes", self.registry)
        base = copy.deepcopy(self.registry)
        mutations = []
        altered = copy.deepcopy(base["operation_routes"][0])
        altered["tool"] = "goat_filtered_search"
        m = copy.deepcopy(base)
        m["operation_routes"] = [altered] + copy.deepcopy(base["operation_routes"][1:])
        mutations.append(("tool-swap", m))
        altered = copy.deepcopy(base["operation_routes"][2])
        altered["provider_id"] = "gdelt"
        m = copy.deepcopy(base)
        m["operation_routes"] = copy.deepcopy(base["operation_routes"][:2]) + [altered] + copy.deepcopy(base["operation_routes"][3:])
        mutations.append(("provider-swap", m))
        altered = copy.deepcopy(base["operation_routes"][2])
        altered["arguments"] = {"vertical": "news"}
        m = copy.deepcopy(base)
        m["operation_routes"] = copy.deepcopy(base["operation_routes"][:2]) + [altered] + copy.deepcopy(base["operation_routes"][3:])
        mutations.append(("vertical-swap", m))
        altered = copy.deepcopy(base["operation_routes"][2])
        altered["arguments"] = {"vertical": "scholar", "extra": "x"}
        m = copy.deepcopy(base)
        m["operation_routes"] = copy.deepcopy(base["operation_routes"][:2]) + [altered] + copy.deepcopy(base["operation_routes"][3:])
        mutations.append(("extra-arg", m))
        altered = copy.deepcopy(base["operation_routes"][0])
        altered["extra"] = "x"
        m = copy.deepcopy(base)
        m["operation_routes"] = [altered] + copy.deepcopy(base["operation_routes"][1:])
        mutations.append(("extra-key", m))
        dup = copy.deepcopy(base["operation_routes"][0])
        m = copy.deepcopy(base)
        m["operation_routes"] = [dup, dup] + copy.deepcopy(base["operation_routes"][2:4]) + [copy.deepcopy(base["operation_routes"][4])]
        mutations.append(("duplicate-missing", m))
        m = copy.deepcopy(base)
        m["operation_routes"] = copy.deepcopy(base["operation_routes"][:4])
        mutations.append(("missing-one", m))
        m = copy.deepcopy(base)
        m["operation_routes"] = copy.deepcopy(base["operation_routes"]) + [copy.deepcopy(base["operation_routes"][0])]
        mutations.append(("extra-route", m))
        m = copy.deepcopy(base)
        m["schema_version"] = 2
        mutations.append(("version-2", m))
        for label, mutated in mutations:
            with self.subTest(mutation=label):
                errors = _validate_json_schema(mutated, REGISTRY_SCHEMA)
                self.assertTrue(errors, f"mutation {label} must fail validator")

    def test_provider_counts_are_14_with_12_routes(self):
        entries = self.registry["providers"]["entries"]
        counts = self.registry["counts"]
        self.assertEqual(len(entries), 14)
        self.assertEqual(counts["providers"], 14)
        recomputed = {key: Counter(entry["classification"] for entry in entries).get(key, 0) for key in CLASSIFICATIONS}
        self.assertEqual(recomputed, {"canonical-free": 1, "route": 12, "future-unavailable": 1})
        self.assertEqual(counts["by_provider_classification"], recomputed)
        ids = [entry["id"] for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[:11], ORIGINAL_PROVIDER_IDS)
        self.assertEqual(ids[11:], ["crossref", "gdelt", "wikimedia-commons"])

    def test_new_anonymous_providers_appended(self):
        by_id = {entry["id"]: entry for entry in self.registry["providers"]["entries"]}
        for expected in NEW_PROVIDERS:
            with self.subTest(provider=expected["id"]):
                self.assertIn(expected["id"], by_id)
                self.assertEqual(by_id[expected["id"]], expected)

    def test_paid_gate_and_canonical_fallback_unchanged(self):
        gate = self.registry["paid_backend_gate"]
        self.assertTrue(gate["requires_key"])
        self.assertEqual(gate["missing_config_error"], "MISSING_CONFIG")
        self.assertEqual(gate["on_missing_config"], "fail_closed_no_fallback")
        self.assertCountEqual(gate["providers"], EXPECTED_PAID_GATE_PROVIDERS)
        providers = self.registry["providers"]
        self.assertEqual(providers["canonical_by_capability"], {"web-search": "anysearch"})
        self.assertEqual(providers["fallback_order"], EXPECTED_FALLBACK_ORDER)
        self.assertEqual(
            providers["fallback_policy"],
            {"mode": "explicit", "transitions_visible": True, "on_paid_missing_config": "fail_closed_no_fallback"},
        )
        capability = next(item for item in self.registry["capabilities"] if item["name"] == "web-search")
        self.assertEqual(capability["canonical_provider"], "anysearch")

    def test_mirror_is_exact_bytes(self):
        authoritative = REGISTRY_PATH.read_bytes()
        mirrored = MIRROR_PATH.read_bytes()
        self.assertEqual(mirrored, authoritative)
        self.assertEqual(json.loads(mirrored), json.loads(authoritative))

    def test_built_plugin_tools_crosscheck(self):
        self.assertIn("operation_routes", self.registry)
        getaddrinfo = socket.getaddrinfo
        create_connection = socket.create_connection

        def _blocked(*args, **kwargs):
            raise AssertionError("network disabled during offline test")

        socket.getaddrinfo = _blocked
        socket.create_connection = _blocked
        tmp = None
        module_name = None
        try:
            tmp, module_name, module = _build_and_register()
            deps = module.v3_wiring.WiringDependencies(search=None, vertical_transports=None)
            ctx = _RecordingContext()
            module.register(ctx, deps=deps)
            self.assertEqual(set(ctx.tools), EXPECTED_ALL_TOOLS)
            self.assertNotIn("anysearch", ctx.tools)
            self.assertNotIn("AnySearch", ctx.tools)
            route_tools = {route["tool"] for route in self.registry["operation_routes"]}
            self.assertEqual(route_tools, {"goat_answer", "goat_filtered_search", "goat_vertical_search"})
            for tool in route_tools:
                self.assertIn(tool, ctx.tools)
            vertical_enum = ctx.tools["goat_vertical_search"]["schema"]["parameters"]["properties"]["vertical"]["enum"]
            self.assertEqual(vertical_enum, ["scholar", "news", "images"])
        finally:
            socket.getaddrinfo = getaddrinfo
            socket.create_connection = create_connection
            if module_name is not None:
                _unload(module_name)
            if tmp is not None:
                shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
