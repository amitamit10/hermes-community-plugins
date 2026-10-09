"""Validate the canonical GOAT Ultimate capability registry with unittest."""

import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY_PATH = ROOT / "registry" / "capabilities.json"
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
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"

# Minimal, dependency-free JSON Schema subset used by this registry. The
# instance validator below implements every keyword declared in this schema.
REGISTRY_SCHEMA = {
    "$schema": SCHEMA_URI,
    "type": "object",
    "required": ["$schema", "schema_version", "counts", "paid_backend_gate", "capabilities", "providers"],
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string", "const": SCHEMA_URI},
        "schema_version": {"type": "integer", "const": 2},
        "providers": {
            "type": "object",
            "required": ["classifications", "canonical_by_capability", "fallback_order", "fallback_policy", "entries"],
            "properties": {
                "classifications": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                "canonical_by_capability": {"type": "object"},
                "fallback_order": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
                "fallback_policy": {"type": "object"},
                "entries": {"type": "array", "minItems": 1},
            },
        },
        "counts": {
            "type": "object",
            "required": ["task_classes", "by_status", "by_source", "providers", "by_provider_classification"],
            "additionalProperties": False,
            "properties": {
                "task_classes": {"type": "integer", "minimum": 0},
                "providers": {"type": "integer", "minimum": 0},
                "by_provider_classification": {"type": "object"},
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


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with REGISTRY_PATH.open(encoding="utf-8") as registry_file:
            cls.registry = json.load(registry_file)

    def test_json_schema_valid(self):
        errors = _validate_json_schema(self.registry, REGISTRY_SCHEMA)
        self.assertEqual(errors, [], "Registry schema validation errors:\n" + "\n".join(errors))

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


if __name__ == "__main__":
    unittest.main()
