"""GOAT V5 Slice 2 bounded two-hop retrieval RED tests (offline).

Loads the real plugin package built by the real bundle builder
(``goat-web/scripts/build_plugin_bundle.py``, imported by file spec) into a
fresh directory under the authorized ``artifacts/wiring-build/`` root. No
ad-hoc byte copies and no source-template assumptions. All tests stay
offline: socket/DNS use is denied.
"""

import importlib.util
import json
import re
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


QUESTION = "Where was the author of Hamlet born?"

HOP1_RESULTS = [
    {
        "title": "Hamlet",
        "url": "https://example.com/hamlet",
        "extract": "William Shakespeare wrote Hamlet.",
    }
]

HOP2_RESULTS = [
    {
        "title": "Shakespeare",
        "url": "https://example.com/shakespeare",
        "extract": "William Shakespeare was born in Stratford-upon-Avon.",
    }
]

CONFLICT_RESULTS = [
    {
        "title": "Shakespeare",
        "url": "https://example.com/shakespeare",
        "extract": "William Shakespeare was born in Stratford-upon-Avon.",
    },
    {
        "title": "Shakespeare negative",
        "url": "https://example.com/shakespeare-negative",
        "extract": "William Shakespeare was not born in Stratford-upon-Avon.",
    },
]


class FixtureMixin:
    def load_tools(self, fake):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        wiring = module.v3_wiring
        deps = wiring.WiringDependencies(
            search=fake, answer_search=fake, vertical_transports=None
        )
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        return module, ctx.tools


class MultiHopTests(OfflineTestCase, FixtureMixin):
    def test_bridge_entity_two_hop_answer(self):
        def fake(query, *, max_results=5):
            fake.calls.append((query, max_results))
            if query == "Who wrote Hamlet?":
                return {"ok": True, "results": list(HOP1_RESULTS)}
            if query == "William Shakespeare born":
                return {"ok": True, "results": list(HOP2_RESULTS)}
            return {"ok": True, "results": []}

        fake.calls = []
        _, tools = self.load_tools(fake)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": QUESTION}))
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn(
            "William Shakespeare was born in Stratford-upon-Avon.",
            payload.get("answer", ""),
        )
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", payload.get("answer", ""))}
        self.assertTrue(cited)
        self.assertTrue(cited <= set(range(1, len(payload.get("sources", [])) + 1)))
        hops = payload.get("hops")
        self.assertIsInstance(hops, list)
        self.assertEqual(len(hops), 2)
        self.assertIn("William Shakespeare", hops[0].get("answer", ""))
        blob = json.dumps(payload)
        self.assertIn("https://example.com/hamlet", blob)
        self.assertIn("https://example.com/shakespeare", blob)

    def test_unresolvable_second_hop_abstains(self):
        def fake(query, *, max_results=5):
            fake.calls.append((query, max_results))
            if query == "Who wrote Hamlet?":
                return {"ok": True, "results": list(HOP1_RESULTS)}
            if query == "William Shakespeare born":
                return {"ok": True, "results": []}
            return {"ok": True, "results": []}

        fake.calls = []
        _, tools = self.load_tools(fake)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": QUESTION}))
        self.assertEqual(
            payload, {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
        )
        self.assertNotIn("answer", payload)

    def test_conflicting_hop_evidence_suppresses(self):
        def fake(query, *, max_results=5):
            fake.calls.append((query, max_results))
            if query == "Who wrote Hamlet?":
                return {"ok": True, "results": list(HOP1_RESULTS)}
            if query == "William Shakespeare born":
                return {"ok": True, "results": list(CONFLICT_RESULTS)}
            return {"ok": True, "results": []}

        fake.calls = []
        _, tools = self.load_tools(fake)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": QUESTION}))
        self.assertEqual(
            payload, {"ok": False, "error": {"code": "INSUFFICIENT_EVIDENCE"}}
        )
        self.assertNotIn("answer", payload)

    def test_single_hop_path_regression_pin(self):
        def fake(query, *, max_results=5):
            fake.calls.append((query, max_results))
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Canada",
                        "url": "https://example.com/canada",
                        "extract": "Ottawa is the capital of Canada.",
                    }
                ],
            }

        fake.calls = []
        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": "What is the capital of Canada?"})
        )
        expected = {
            "answer": "Ottawa is the capital of Canada. [1]",
            "ok": True,
            "sources": [
                {"index": 1, "title": "Canada", "url": "https://example.com/canada"}
            ],
        }
        self.assertEqual(payload, expected)


if __name__ == "__main__":
    unittest.main()
