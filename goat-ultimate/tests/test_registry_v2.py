"""Validate the v2 canonical capability/provider registry without dependencies."""

import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY_PATH = ROOT / "registry" / "capabilities.json"
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"
TASK_CLASSES = {
    "web-search", "extraction", "browser", "crawl", "rss",
    "api-automation", "media", "docs-artifacts", "sheets", "maps", "memory",
}
STATUSES = ["keep", "route", "future"]
SOURCES = ["builtin", "bundled", "local", "hub", "goat", "paid"]
CLASSIFICATIONS = ["canonical-free", "route", "future-unavailable"]
PAID_GATE_NAMES = [
    "Firecrawl", "Exa", "Tavily", "Serper", "Browserbase stealth", "Bright Data",
]
PAID_SEARCH_IDS = {"tavily", "exa", "firecrawl", "serper"}
EXPECTED_FALLBACK_ORDER = ["anysearch", "searxng", "wikipedia", "duckduckgo"]

# Dependency-free validation schema for the registry's declared v2 shape.
REGISTRY_SCHEMA = {
    "type": "object",
    "required": ["$schema", "schema_version", "counts", "paid_backend_gate", "capabilities", "providers"],
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string", "const": SCHEMA_URI},
        "schema_version": {"type": "integer", "const": 2},
        "counts": {
            "type": "object",
            "required": ["task_classes", "by_status", "by_source", "providers", "by_provider_classification"],
            "additionalProperties": False,
            "properties": {
                "task_classes": {"type": "integer", "minimum": 0},
                "providers": {"type": "integer", "minimum": 0},
                "by_status": {
                    "type": "object", "required": STATUSES, "additionalProperties": False,
                    "properties": {key: {"type": "integer", "minimum": 0} for key in STATUSES},
                },
                "by_source": {
                    "type": "object", "required": SOURCES, "additionalProperties": False,
                    "properties": {key: {"type": "integer", "minimum": 0} for key in SOURCES},
                },
                "by_provider_classification": {
                    "type": "object", "required": CLASSIFICATIONS, "additionalProperties": False,
                    "properties": {key: {"type": "integer", "minimum": 0} for key in CLASSIFICATIONS},
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
                    "type": "array", "minItems": 1, "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1},
                },
            },
        },
        "capabilities": {
            "type": "array", "minItems": len(TASK_CLASSES), "maxItems": len(TASK_CLASSES),
            "items": {
                "type": "object",
                "required": ["name", "canonical_provider", "source", "overlaps_resolved", "status"],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "enum": sorted(TASK_CLASSES)},
                    "canonical_provider": {"type": "string", "minLength": 1},
                    "source": {"type": "string", "enum": SOURCES},
                    "overlaps_resolved": {
                        "type": "array", "uniqueItems": True,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "status": {"type": "string", "enum": STATUSES},
                },
            },
        },
        "providers": {
            "type": "object",
            "required": ["classifications", "canonical_by_capability", "fallback_order", "fallback_policy", "entries"],
            "additionalProperties": False,
            "properties": {
                "classifications": {
                    "type": "array", "minItems": len(CLASSIFICATIONS), "maxItems": len(CLASSIFICATIONS),
                    "uniqueItems": True,
                    "items": {"type": "string", "enum": CLASSIFICATIONS},
                },
                "canonical_by_capability": {
                    "type": "object", "required": ["web-search"], "additionalProperties": False,
                    "properties": {"web-search": {"type": "string", "minLength": 1}},
                },
                "fallback_order": {
                    "type": "array", "minItems": 4, "maxItems": 4, "uniqueItems": True,
                    "items": {"type": "string", "minLength": 1},
                },
                "fallback_policy": {
                    "type": "object",
                    "required": ["mode", "transitions_visible", "on_paid_missing_config"],
                    "additionalProperties": False,
                    "properties": {
                        "mode": {"type": "string", "const": "explicit"},
                        "transitions_visible": {"type": "boolean", "const": True},
                        "on_paid_missing_config": {"type": "string", "const": "fail_closed_no_fallback"},
                    },
                },
                "entries": {
                    "type": "array", "minItems": 11, "maxItems": 11,
                    "items": {
                        "type": "object",
                        "required": ["id", "name", "classification", "capabilities", "access", "requires_key", "key_optional"],
                        "additionalProperties": False,
                        "properties": {
                            "id": {"type": "string", "minLength": 1},
                            "name": {"type": "string", "minLength": 1},
                            "classification": {"type": "string", "enum": CLASSIFICATIONS},
                            "capabilities": {
                                "type": "array", "uniqueItems": True,
                                "items": {"type": "string", "enum": sorted(TASK_CLASSES)},
                            },
                            "access": {"type": "string", "enum": ["anonymous", "self-hosted-optional", "keyed", "unavailable"]},
                            "requires_key": {"type": "boolean"},
                            "key_optional": {"type": "boolean"},
                            "optional_key_env": {"type": "string", "minLength": 1},
                            "missing_config_error": {"type": "string", "const": "MISSING_CONFIG"},
                            "on_missing_config": {"type": "string", "const": "fail_closed_no_fallback"},
                        },
                    },
                },
            },
        },
    },
}


def _validate_schema(instance, schema, path="$", errors=None):
    """Validate the JSON Schema keywords used by REGISTRY_SCHEMA."""
    if errors is None:
        errors = []
    expected_type = schema.get("type")
    type_checks = {
        "object": lambda value: isinstance(value, dict),
        "array": lambda value: isinstance(value, list),
        "string": lambda value: isinstance(value, str),
        "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
        "boolean": lambda value: isinstance(value, bool),
    }
    if expected_type in type_checks and not type_checks[expected_type](instance):
        errors.append(f"{path}: expected {expected_type}")
        return errors
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} is not allowed")
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
            for key in sorted(set(instance) - set(properties)):
                errors.append(f"{path}: unexpected property {key!r}")
        for key, value in instance.items():
            if key in properties:
                _validate_schema(value, properties[key], f"{path}.{key}", errors)
    if expected_type == "array":
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: array is shorter than minItems")
        if len(instance) > schema.get("maxItems", float("inf")):
            errors.append(f"{path}: array is longer than maxItems")
        if schema.get("uniqueItems"):
            encoded = [json.dumps(value, sort_keys=True, separators=(",", ":")) for value in instance]
            if len(encoded) != len(set(encoded)):
                errors.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if item_schema:
            for index, value in enumerate(instance):
                _validate_schema(value, item_schema, f"{path}[{index}]", errors)
    return errors


class RegistryV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with REGISTRY_PATH.open(encoding="utf-8") as registry_file:
            cls.registry = json.load(registry_file)
        cls.entries = cls.registry.get("providers", {}).get("entries", [])
        cls.by_id = {entry.get("id"): entry for entry in cls.entries}

    def test_registry_matches_v2_schema(self):
        errors = _validate_schema(self.registry, REGISTRY_SCHEMA)
        self.assertEqual(errors, [], "Registry schema errors:\n" + "\n".join(errors))

    def test_provider_ids_and_classification_counts_match(self):
        ids = [entry["id"] for entry in self.entries]
        self.assertEqual(len(ids), len(set(ids)), "Provider IDs must be unique")
        counts = self.registry["counts"]
        self.assertEqual(counts["providers"], len(self.entries))
        self.assertEqual(
            counts["by_provider_classification"],
            {classification: Counter(entry["classification"] for entry in self.entries).get(classification, 0)
             for classification in CLASSIFICATIONS},
        )

    def test_capability_counts_match_records(self):
        capabilities = self.registry["capabilities"]
        counts = self.registry["counts"]
        self.assertEqual(counts["task_classes"], len(TASK_CLASSES))
        self.assertEqual(len(capabilities), len(TASK_CLASSES))
        self.assertEqual(
            counts["by_status"],
            {status: Counter(item["status"] for item in capabilities).get(status, 0) for status in STATUSES},
        )
        self.assertEqual(
            counts["by_source"],
            {source: Counter(item["source"] for item in capabilities).get(source, 0) for source in SOURCES},
        )

    def test_web_search_canonical_is_anonymous_anysearch(self):
        capability = next(item for item in self.registry["capabilities"] if item["name"] == "web-search")
        canonical_id = self.registry["providers"]["canonical_by_capability"]["web-search"]
        provider = self.by_id[canonical_id]
        self.assertEqual(capability["canonical_provider"], "anysearch")
        self.assertEqual(canonical_id, "anysearch")
        self.assertEqual(provider["classification"], "canonical-free")
        self.assertEqual(provider["access"], "anonymous")
        self.assertFalse(provider["requires_key"])
        self.assertTrue(provider["key_optional"])
        self.assertEqual(provider["optional_key_env"], "ANYSEARCH_API_KEY")

    def test_free_fallback_order_is_canonical(self):
        self.assertEqual(self.registry["providers"]["fallback_order"], EXPECTED_FALLBACK_ORDER)
        self.assertEqual(self.by_id["searxng"]["access"], "self-hosted-optional")
        self.assertNotIn("donsetch", EXPECTED_FALLBACK_ORDER)
        policy = self.registry["providers"]["fallback_policy"]
        self.assertEqual(policy["mode"], "explicit")
        self.assertTrue(policy["transitions_visible"])

    def test_all_paid_gate_providers_require_keys_and_fail_closed(self):
        gate = self.registry["paid_backend_gate"]
        self.assertTrue(gate["requires_key"])
        self.assertEqual(gate["missing_config_error"], "MISSING_CONFIG")
        self.assertEqual(gate["on_missing_config"], "fail_closed_no_fallback")
        self.assertCountEqual(gate["providers"], PAID_GATE_NAMES)
        by_name = {entry["name"]: entry for entry in self.entries}
        for name in PAID_GATE_NAMES:
            with self.subTest(provider=name):
                provider = by_name[name]
                self.assertEqual(provider["classification"], "route")
                self.assertTrue(provider["requires_key"])
                self.assertFalse(provider["key_optional"])
                self.assertEqual(provider["missing_config_error"], "MISSING_CONFIG")
                self.assertEqual(provider["on_missing_config"], "fail_closed_no_fallback")
        for provider_id in PAID_SEARCH_IDS:
            with self.subTest(provider=provider_id):
                self.assertIn("web-search", self.by_id[provider_id]["capabilities"])

    def test_unavailable_provider_is_not_routable(self):
        provider = self.by_id["donsetch"]
        self.assertEqual(provider["classification"], "future-unavailable")
        self.assertEqual(provider["access"], "unavailable")
        self.assertNotIn("donsetch", self.registry["providers"]["fallback_order"])


if __name__ == "__main__":
    unittest.main()
