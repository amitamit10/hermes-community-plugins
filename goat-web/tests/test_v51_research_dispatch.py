"""GOAT V5.1 research budget dispatch RED tests (offline, TEST-ONLY).

Uses the real plugin bundle builder + real register + real JSON dispatch.
Trusted boundary is faked only (search callable). Socket/DNS including
socket construction is denied during tests; no real traffic.
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
    global _BUILDER_MODULE
    if _BUILDER_MODULE is not None:
        return _BUILDER_MODULE
    module_name = "goat_v51_bundle_builder"
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
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="goat-answer-v51-", dir=str(BUILD_ROOT))
    pkgdir = Path(tmp) / "hermes-goat-web"
    _load_builder().build_bundle(WIRING_ROOT, pkgdir)
    return tmp, pkgdir


def load_fixture_package(pkgdir):
    module_name = "goat_answer_pkg_v51_" + uuid.uuid4().hex
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
        # Warm stdlib network modules before blocking construction so
        # fixture imports (http.client/ssl) hit sys.modules cache.
        try:
            import http.client  # noqa: F401
            import ssl  # noqa: F401
        except Exception:
            pass
        self._getaddrinfo = socket.getaddrinfo
        self._create_connection = socket.create_connection
        self._socket = socket.socket
        self._gethostbyname = getattr(socket, "gethostbyname", None)
        self._getnameinfo = getattr(socket, "getnameinfo", None)

        def _blocked(*args, **kwargs):
            raise AssertionError("network disabled during offline test")

        _orig_socket_cls = self._socket

        class _BlockedSocket(_orig_socket_cls):
            def __new__(cls, *args, **kwargs):
                raise AssertionError(
                    "socket construction disabled during offline test"
                )

        socket.getaddrinfo = _blocked
        socket.create_connection = _blocked
        socket.socket = _BlockedSocket
        if hasattr(socket, "gethostbyname"):
            socket.gethostbyname = _blocked
        if hasattr(socket, "getnameinfo"):
            socket.getnameinfo = _blocked
        self.addCleanup(setattr, socket, "getaddrinfo", self._getaddrinfo)
        self.addCleanup(setattr, socket, "create_connection", self._create_connection)
        self.addCleanup(setattr, socket, "socket", self._socket)
        if self._gethostbyname is not None:
            self.addCleanup(setattr, socket, "gethostbyname", self._gethostbyname)
        if self._getnameinfo is not None:
            self.addCleanup(setattr, socket, "getnameinfo", self._getnameinfo)


# Entity-neutral synthetic fixtures (not benchmark questions).
PORTA_QUESTION = "What is the capital of Porta?"
PORTA_RESULTS = [
    {
        "title": "Porta",
        "url": "https://example.com/porta",
        "extract": "Luma is the capital of Porta.",
    }
]
EXPECTED_PORTA_LEGACY = {
    "answer": "Luma is the capital of Porta. [1]",
    "ok": True,
    "sources": [
        {"index": 1, "title": "Porta", "url": "https://example.com/porta"}
    ],
}

# Compositional research chain synthetic fixtures (merged from out-of-scope
# chain file; behavior unchanged, reuses common real bundle fixture above).
QUESTION = "Who designed the capital of the body orbited by Runa?"
URL1 = "https://example.com/runa-orbit"
URL2 = "https://example.com/porta-capital"
URL3 = "https://example.com/luma-designed"


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

    def load_module(self):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        return module

    def porta_fake(self, calls):
        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            return {"ok": True, "results": list(PORTA_RESULTS)}

        return fake

    def chain_fake(self, calls):
        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == "What does Runa orbit?":
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Runa",
                            "url": URL1,
                            "extract": "Runa orbits Porta.",
                        }
                    ],
                }
            if query == "What is the capital of Porta?":
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Porta",
                            "url": URL2,
                            "extract": "Luma is the capital of Porta.",
                        }
                    ],
                }
            if query == "Who designed Luma?":
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Luma",
                            "url": URL3,
                            "extract": "Mira Vale designed Luma.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        return fake


class PublicBudgetTests(OfflineTestCase, FixtureMixin):
    def test_schema_exposes_research_budgets(self):
        calls = []
        _, tools = self.load_tools(self.porta_fake(calls))
        params = tools["goat_answer"]["schema"]["parameters"]
        props = params["properties"]
        # research boolean default False
        self.assertIn("research", props)
        self.assertEqual(props["research"]["type"], "boolean")
        self.assertIs(props["research"]["default"], False)
        # max_hops integer min1 max4 default2
        self.assertIn("max_hops", props)
        self.assertEqual(props["max_hops"]["type"], "integer")
        self.assertEqual(props["max_hops"]["minimum"], 1)
        self.assertEqual(props["max_hops"]["maximum"], 4)
        self.assertEqual(props["max_hops"]["default"], 2)
        # max_searches integer min1 max8 default4
        self.assertIn("max_searches", props)
        self.assertEqual(props["max_searches"]["type"], "integer")
        self.assertEqual(props["max_searches"]["minimum"], 1)
        self.assertEqual(props["max_searches"]["maximum"], 8)
        self.assertEqual(props["max_searches"]["default"], 4)
        # closed schema still required query only
        self.assertEqual(params["required"], ["query"])
        self.assertIs(params["additionalProperties"], False)

    def test_invalid_budgets_reject_with_zero_calls(self):
        bad_hops = [True, False, 0, 5, 9, -1, "2", 2.0, None, [], {}]
        bad_searches = [True, False, 0, 9, 10, -1, "4", 4.0, None, [], {}]
        for bad_hop in bad_hops:
            with self.subTest(bad_hop=repr(bad_hop)):
                calls = []
                _, tools = self.load_tools(self.porta_fake(calls))
                handler = tools["goat_answer"]["handler"]
                payload = json.loads(
                    handler(
                        {
                            "query": PORTA_QUESTION,
                            "research": False,
                            "max_hops": bad_hop,
                            "max_searches": 4,
                        }
                    )
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(calls, [])
        for bad_search in bad_searches:
            with self.subTest(bad_search=repr(bad_search)):
                calls = []
                _, tools = self.load_tools(self.porta_fake(calls))
                handler = tools["goat_answer"]["handler"]
                payload = json.loads(
                    handler(
                        {
                            "query": PORTA_QUESTION,
                            "research": False,
                            "max_hops": 2,
                            "max_searches": bad_search,
                        }
                    )
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(calls, [])

    def test_invalid_research_rejects_with_zero_calls(self):
        bad_research = ["true", "false", "False", 1, 0, 1.0, 0.0, None, [], {}, "yes"]
        for bad in bad_research:
            with self.subTest(bad_research=repr(bad)):
                calls = []
                _, tools = self.load_tools(self.porta_fake(calls))
                handler = tools["goat_answer"]["handler"]
                payload = json.loads(
                    handler(
                        {
                            "query": PORTA_QUESTION,
                            "research": bad,
                            "max_hops": 2,
                            "max_searches": 4,
                        }
                    )
                )
                self.assertEqual(
                    payload, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(calls, [])

    def test_explicit_valid_budgets_returns_exact_legacy(self):
        calls_legacy = []
        _, tools_legacy = self.load_tools(self.porta_fake(calls_legacy))
        legacy = json.loads(
            tools_legacy["goat_answer"]["handler"]({"query": PORTA_QUESTION})
        )
        self.assertEqual(legacy, EXPECTED_PORTA_LEGACY)
        self.assertEqual(calls_legacy, [(PORTA_QUESTION, 5)])
        # explicit valid budgets with research=False must be identical
        valid_combos = [
            {"research": False},
            {"research": False, "max_hops": 2, "max_searches": 4},
            {"research": False, "max_hops": 1, "max_searches": 1},
            {"research": False, "max_hops": 4, "max_searches": 8},
        ]
        for extra in valid_combos:
            with self.subTest(extra=extra):
                calls = []
                _, tools = self.load_tools(self.porta_fake(calls))
                args = {"query": PORTA_QUESTION}
                args.update(extra)
                payload = json.loads(tools["goat_answer"]["handler"](args))
                self.assertEqual(payload, EXPECTED_PORTA_LEGACY)
                self.assertEqual(payload, legacy)
                # no metadata change: exact keys only
                self.assertEqual(set(payload), {"answer", "ok", "sources"})
                self.assertNotIn("hops", payload)
                self.assertNotIn("research", payload)
                self.assertNotIn("max_hops", payload)
                self.assertNotIn("max_searches", payload)
                self.assertEqual(calls, [(PORTA_QUESTION, 5)])
                self.assertEqual(len(calls), 1)

    def test_omitted_controls_exact_legacy_single_hop(self):
        calls = []
        _, tools = self.load_tools(self.porta_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": PORTA_QUESTION})
        )
        self.assertEqual(payload, EXPECTED_PORTA_LEGACY)
        self.assertEqual(calls, [(PORTA_QUESTION, 5)])
        self.assertEqual(len(calls), 1)
        self.assertNotIn("hops", payload)

    def test_direct_make_handlers_invalid_budgets(self):
        calls = []
        fake = self.porta_fake(calls)
        module = self.load_module()
        wiring = module.v3_wiring
        try:
            deps = wiring.WiringDependencies(
                search=fake, answer_search=fake, vertical_transports=None
            )
        except TypeError as exc:
            self.fail("WiringDependencies missing kwargs support: %r" % (exc,))
        try:
            handlers = wiring.make_handlers(deps)
        except TypeError as exc:
            self.fail("make_handlers missing deps support: %r" % (exc,))
            return
        self.assertIn("goat_answer", handlers)
        op = handlers["goat_answer"]
        bad_cases = [
            {"max_hops": 0},
            {"max_hops": 5},
            {"max_hops": True},
            {"max_hops": 2.0},
            {"max_hops": "2"},
            {"max_hops": None},
            {"max_searches": 0},
            {"max_searches": 9},
            {"max_searches": False},
            {"max_searches": 4.0},
            {"max_searches": "4"},
            {"max_searches": None},
            {"research": "true"},
            {"research": 1},
            {"research": None},
        ]
        for extra in bad_cases:
            with self.subTest(extra=extra):
                calls.clear()
                kwargs = {"max_results": 5}
                kwargs.update(extra)
                try:
                    result = op(PORTA_QUESTION, **kwargs)
                except TypeError as exc:
                    self.fail(
                        "direct goat_answer missing budget kwarg support %r: %r"
                        % (extra, exc)
                    )
                    continue
                self.assertEqual(
                    result, {"ok": False, "error": {"code": "URL_BLOCKED"}}
                )
                self.assertEqual(calls, [])

    def test_direct_valid_kwargs_support(self):
        calls = []
        fake = self.porta_fake(calls)
        module = self.load_module()
        wiring = module.v3_wiring
        try:
            deps = wiring.WiringDependencies(
                search=fake, answer_search=fake, vertical_transports=None
            )
            handlers = wiring.make_handlers(deps)
        except TypeError as exc:
            self.fail("make_handlers/dep construction TypeError: %r" % (exc,))
            return
        op = handlers["goat_answer"]
        # Valid explicit budgets via direct call must match legacy single-hop.
        calls.clear()
        try:
            result = op(
                PORTA_QUESTION,
                max_results=5,
                research=False,
                max_hops=2,
                max_searches=4,
            )
        except TypeError as exc:
            self.fail("direct handler missing research budget support: %r" % (exc,))
            return
        self.assertEqual(
            result,
            {
                "answer": "Luma is the capital of Porta. [1]",
                "ok": True,
                "sources": [
                    {
                        "index": 1,
                        "title": "Porta",
                        "url": "https://example.com/porta",
                    }
                ],
            },
        )
        self.assertEqual(len(calls), 1)


class LegacyCitationTests(OfflineTestCase, FixtureMixin):
    COBALT_QUESTION = "Where was the inventor of Cobalt born?"
    HOP1_QUERY = "Who invented Cobalt?"
    HOP2_QUERY = "Mira Vale born"
    HOP1_URL = "https://example.com/cobalt-inventor"
    HOP2_URL = "https://example.com/mira-vale-birth"
    HOP1_RESULTS = [
        {
            "title": "Cobalt",
            "url": "https://example.com/cobalt-inventor",
            "extract": "Mira Vale invented Cobalt.",
        }
    ]
    HOP2_RESULTS = [
        {
            "title": "Mira Vale",
            "url": "https://example.com/mira-vale-birth",
            "extract": "Mira Vale was born in Arbor.",
        }
    ]

    def _cobalt_fake(self, calls, hop2_results=None):
        hop2 = hop2_results if hop2_results is not None else list(self.HOP2_RESULTS)

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.HOP1_QUERY:
                return {"ok": True, "results": list(self.HOP1_RESULTS)}
            if query == self.HOP2_QUERY:
                return {"ok": True, "results": list(hop2)}
            return {"ok": True, "results": []}

        return fake

    def _find_intermediate(self, payload):
        import json as _json  # local to avoid top edits

        # Accept self-constructed intermediate in metadata/provenance.
        for key in ("provenance", "metadata"):
            container = payload.get(key)
            if isinstance(container, dict):
                if isinstance(container.get("intermediate_evidence"), list):
                    return container["intermediate_evidence"]
                research = container.get("research")
                if isinstance(research, dict) and isinstance(
                    research.get("intermediate_evidence"), list
                ):
                    return research["intermediate_evidence"]
                prov = container.get("provenance")
                if isinstance(prov, dict) and isinstance(
                    prov.get("intermediate_evidence"), list
                ):
                    return prov["intermediate_evidence"]
        if isinstance(payload.get("intermediate_evidence"), list):
            return payload["intermediate_evidence"]
        return None

    def test_final_cites_only_hop2_strict(self):
        import re

        calls = []
        _, tools = self.load_tools(self._cobalt_fake(calls))
        payload = json.loads(tools["goat_answer"]["handler"]({"query": self.COBALT_QUESTION}))
        self.assertTrue(payload.get("ok"), payload)
        # Final sources ONLY hop2 URL, strict int index 1.
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(len(calls), 2, payload)
        entry = sources[0]
        self.assertIs(type(entry.get("index")), int, payload)
        self.assertEqual(entry.get("index"), 1, payload)
        self.assertEqual(entry.get("url"), self.HOP2_URL, payload)
        # Marker [1] only, every final source cited.
        answer = payload.get("answer", "")
        self.assertIn("Mira Vale was born in Arbor.", answer, payload)
        self.assertIn("[1]", answer, payload)
        self.assertNotIn("[2]", answer, payload)
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        self.assertEqual(cited, {1}, payload)
        self.assertEqual({s.get("index") for s in sources}, cited, payload)
        # Local hops retain correct local markers.
        hops = payload.get("hops")
        self.assertIsInstance(hops, list, payload)
        self.assertEqual(len(hops), 2, payload)
        self.assertIn("[1]", hops[0].get("answer", ""), payload)
        self.assertNotIn("[2]", hops[0].get("answer", ""), payload)
        self.assertEqual(hops[0].get("sources")[0].get("index"), 1, payload)
        self.assertIs(type(hops[0].get("sources")[0].get("index")), int, payload)
        self.assertEqual(hops[0].get("sources")[0].get("url"), self.HOP1_URL, payload)
        self.assertIn("[1]", hops[1].get("answer", ""), payload)
        self.assertNotIn("[2]", hops[1].get("answer", ""), payload)
        self.assertEqual(hops[1].get("sources")[0].get("index"), 1, payload)
        self.assertEqual(hops[1].get("sources")[0].get("url"), self.HOP2_URL, payload)
        # Bridge URL intermediate, not final.
        final_urls = [s.get("url") for s in sources]
        self.assertNotIn(self.HOP1_URL, final_urls, payload)
        blob = json.dumps(payload)
        self.assertIn(self.HOP1_URL, blob, payload)
        intermediate = self._find_intermediate(payload)
        self.assertIsNotNone(intermediate, payload)
        self.assertLessEqual(len(intermediate), 5, payload)
        urls = [
            item.get("url") if isinstance(item, dict) else item
            for item in intermediate
        ]
        self.assertIn(self.HOP1_URL, urls, payload)
        self.assertNotIn(self.HOP2_URL, urls, payload)

    def test_duplicate_hop2_urls_dedup_single_index(self):
        import re

        dup_url = "https://example.com/arbor-birth"
        hop2_dup = [
            {
                "title": "Mira Vale",
                "url": dup_url,
                "extract": "Mira Vale was born in Arbor.",
            },
            {
                "title": "Mira Vale birth",
                "url": dup_url,
                "extract": "Mira Vale was born in Arbor City.",
            },
        ]
        calls = []
        _, tools = self.load_tools(self._cobalt_fake(calls, hop2_results=hop2_dup))
        payload = json.loads(tools["goat_answer"]["handler"]({"query": self.COBALT_QUESTION}))
        self.assertTrue(payload.get("ok"), payload)
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertIs(type(sources[0].get("index")), int, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)
        self.assertEqual(sources[0].get("url"), dup_url, payload)
        answer = payload.get("answer", "")
        self.assertIn("Mira Vale was born in Arbor.", answer, payload)
        self.assertIn("Mira Vale was born in Arbor City.", answer, payload)
        self.assertIn("[1]", answer, payload)
        self.assertNotIn("[2]", answer, payload)
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        self.assertEqual(cited, {1}, payload)

    def test_max_results_one_caps_global_final(self):
        import re

        calls = []
        _, tools = self.load_tools(self._cobalt_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": self.COBALT_QUESTION, "max_results": 1}
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(sources[0].get("url"), self.HOP2_URL, payload)
        self.assertIs(type(sources[0].get("index")), int, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)
        answer = payload.get("answer", "")
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        self.assertEqual(cited, {1}, payload)
        self.assertNotIn("[2]", answer, payload)

    def test_max_hops_one_budget_exhausted(self):
        calls = []
        _, tools = self.load_tools(self._cobalt_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": self.COBALT_QUESTION, "max_hops": 1}
            )
        )
        self.assertEqual(calls, [], payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertEqual(
            payload.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", payload
        )
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "budget_exhausted", payload)

    def test_max_searches_one_budget_exhausted(self):
        calls = []
        _, tools = self.load_tools(self._cobalt_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": self.COBALT_QUESTION, "max_searches": 1}
            )
        )
        self.assertEqual(calls, [], payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertEqual(
            payload.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", payload
        )
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "budget_exhausted", payload)


class ActualRequestBudgetTests(OfflineTestCase, FixtureMixin):
    """Physical budget: fake HTTP boundary + real wikipedia_answer_search."""

    def _wikipedia_bodies(self, title="Mira Vale"):
        import json as _json
        import urllib.parse as _up

        search_body = _json.dumps(
            {"query": {"search": [{"title": title, "pageid": 1}]}}
        ).encode("utf-8")
        extracts_body = _json.dumps(
            {
                "query": {
                    "pages": [
                        {
                            "pageid": 1,
                            "title": title,
                            "extract": "%s was born in Arbor." % title,
                        }
                    ]
                }
            }
        ).encode("utf-8")
        return search_body, extracts_body

    def _fake_http(self, calls, search_body, extracts_body):
        def fake_fetch(url, **kwargs):
            calls.append(url)
            if "list=search" in url:
                return {"status": 200, "headers": {}, "body": search_body, "url": url}
            if "prop=extracts" in url:
                return {"status": 200, "headers": {}, "body": extracts_body, "url": url}
            return {"status": 200, "headers": {}, "body": search_body, "url": url}

        return fake_fetch

    def test_budget_token_api_exists(self):
        module = self.load_module()
        wiring = module.v3_wiring
        budget_cls = getattr(wiring, "_AnswerRequestBudget", None)
        self.assertTrue(callable(budget_cls), "missing _AnswerRequestBudget")
        tok = budget_cls(1)
        # Whole cap is twice max_searches.
        max_http = getattr(tok, "max_http", getattr(tok, "limit", None))
        self.assertEqual(max_http, 2)
        consume = getattr(tok, "try_consume", None)
        if consume is None:
            consume = getattr(tok, "try_acquire", None)
        if consume is None:
            consume = getattr(tok, "acquire", None)
        self.assertTrue(callable(consume), "missing budget consume api")

    def test_default_answer_accepts_private_budget(self):
        module = self.load_module()
        wiring = module.v3_wiring
        factory = getattr(wiring, "make_default_answer_search", None)
        self.assertTrue(callable(factory))
        search_body, extracts_body = self._wikipedia_bodies()
        calls = []
        answer_search = factory(_fetch=self._fake_http(calls, search_body, extracts_body))
        # Capability marker avoids changing custom fake contracts.
        marker = getattr(answer_search, "_GOAT_BUDGET_AWARE", None)
        self.assertTrue(marker is True, "missing budget capability marker")
        budget_cls = getattr(wiring, "_AnswerRequestBudget", None)
        self.assertTrue(callable(budget_cls))
        tok = budget_cls(4)
        # Must accept private kw without TypeError (budget component only).
        try:
            result = answer_search("Mira Vale born", max_results=5, _request_budget=tok)
        except TypeError as exc:
            self.fail("default answer missing _request_budget support: %r" % (exc,))
        self.assertTrue(isinstance(result, dict))
        # One logical call uses exactly two HTTP requests.
        self.assertEqual(len(calls), 2, result)

    def test_third_transport_never_invoked(self):
        module = self.load_module()
        wiring = module.v3_wiring
        budget_cls = getattr(wiring, "_AnswerRequestBudget", None)
        self.assertTrue(callable(budget_cls))
        search_body, extracts_body = self._wikipedia_bodies()
        fetch_calls = []
        fake_fetch = self._fake_http(fetch_calls, search_body, extracts_body)
        factory = getattr(wiring, "make_default_answer_search", None)
        self.assertTrue(callable(factory))
        answer_search = factory(_fetch=fake_fetch)
        tok = budget_cls(4)
        # Fake stack callback attempts 3 transport requests in 1 logical call.
        # Use the real budget-aware transport path: call answer_search which
        # internally does 2 fetches, then simulate a third attempt via the
        # same budget token - third must be refused before fetch.
        try:
            result = answer_search("Mira Vale born", max_results=5, _request_budget=tok)
        except TypeError as exc:
            self.fail("default answer missing _request_budget support: %r" % (exc,))
            return
        self.assertEqual(len(fetch_calls), 2, result)
        # Fake stack callback attempts 3 transport requests in 1 logical call:
        # use a fresh token with max_searches=1 (whole=2). One real logical
        # call consumes exactly 2 HTTP; a third transport attempt must be
        # refused before fetch (budget component only, not public grounding).
        tok2 = budget_cls(1)
        fetch2 = []
        answer2 = factory(_fetch=self._fake_http(fetch2, search_body, extracts_body))
        try:
            r1 = answer2("Mira Vale born", max_results=5, _request_budget=tok2)
        except TypeError as exc:
            self.fail("default answer missing _request_budget support: %r" % (exc,))
            return
        self.assertEqual(len(fetch2), 2, r1)
        fetch2_before = len(fetch2)
        c2 = getattr(tok2, "try_consume", None)
        if c2 is None:
            c2 = getattr(tok2, "try_acquire", None)
        if c2 is None:
            c2 = getattr(tok2, "acquire", None)
        self.assertTrue(callable(c2))
        try:
            allowed = c2(1)
        except TypeError:
            try:
                allowed = c2()
            except Exception:
                allowed = False
        self.assertIs(allowed, False, "third transport must be budget-blocked")
        self.assertEqual(len(fetch2), fetch2_before, "third fetch NEVER invoked")

    def test_two_steps_four_http_allowed_one_exhausted(self):
        module = self.load_module()
        wiring = module.v3_wiring
        budget_cls = getattr(wiring, "_AnswerRequestBudget", None)
        self.assertTrue(callable(budget_cls))
        factory = getattr(wiring, "make_default_answer_search", None)
        self.assertTrue(callable(factory))
        search_body, extracts_body = self._wikipedia_bodies()
        # 2 steps use 4 HTTP with budget 4 (whole 8) -> allowed.
        calls = []
        answer_search = factory(_fetch=self._fake_http(calls, search_body, extracts_body))
        tok_big = budget_cls(4)
        try:
            r1 = answer_search("Mira Vale born", max_results=5, _request_budget=tok_big)
            r2 = answer_search("Who invented Cobalt?", max_results=5, _request_budget=tok_big)
        except TypeError as exc:
            self.fail("default answer missing _request_budget support: %r" % (exc,))
            return
        self.assertEqual(len(calls), 4, (r1, r2))
        # Budget max_searches=1 (whole 2): after one logical call (2 HTTP),
        # next logical call must be explicitly exhausted with no extra fetch.
        calls2 = []
        answer_small = factory(_fetch=self._fake_http(calls2, search_body, extracts_body))
        tok_small = budget_cls(1)
        try:
            rs1 = answer_small("Mira Vale born", max_results=5, _request_budget=tok_small)
        except TypeError as exc:
            self.fail("default answer missing _request_budget support: %r" % (exc,))
            return
        self.assertEqual(len(calls2), 2, rs1)
        # Second logical call must fail as INSUFFICIENT_EVIDENCE without new fetch.
        try:
            rs2 = answer_small("Who invented Cobalt?", max_results=5, _request_budget=tok_small)
        except TypeError as exc:
            self.fail("default answer missing _request_budget support: %r" % (exc,))
            return
        self.assertIsInstance(rs2, dict)
        # Shared failure code INSUFFICIENT_EVIDENCE, no retries (no extra fetch).
        err = rs2.get("error", {})
        code = err.get("code") if isinstance(err, dict) else None
        # Public code mapping: allow raw or mapped, but must be INSUFFICIENT_EVIDENCE.
        self.assertEqual(code, "INSUFFICIENT_EVIDENCE", rs2)
        self.assertLessEqual(len(calls2), 2, rs2)
        self.assertEqual(len(calls2), 2, rs2)


class ResearchChainTests(OfflineTestCase, FixtureMixin):
    def test_compositional_chain_executes_three_queries(self):
        calls = []
        _, tools = self.load_tools(self.chain_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": QUESTION,
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 4,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        # Exact three grounded subqueries in dependency order.
        self.assertEqual(
            [q for q, _ in calls],
            [
                "What does Runa orbit?",
                "What is the capital of Porta?",
                "Who designed Luma?",
            ],
            payload,
        )
        self.assertEqual(len(calls), 3, payload)
        # Final sentence only terminal Mira Vale with [1] and URL3.
        self.assertEqual(
            payload.get("answer"), "Mira Vale designed Luma. [1]", payload
        )
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)
        self.assertIs(type(sources[0].get("index")), int, payload)
        self.assertEqual(sources[0].get("url"), URL3, payload)
        # Explicit research metadata.
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(
            research.get("status"), "completed", payload
        )
        self.assertEqual(research.get("planned"), 3, payload)
        self.assertEqual(research.get("executed"), 3, payload)
        self.assertEqual(research.get("search_calls"), 3, payload)
        # Hops with local indices.
        hops = payload.get("hops")
        self.assertIsInstance(hops, list, payload)
        self.assertEqual(len(hops), 3, payload)
        self.assertEqual(hops[0].get("query"), "What does Runa orbit?", payload)
        self.assertEqual(
            hops[1].get("query"), "What is the capital of Porta?", payload
        )
        self.assertEqual(hops[2].get("query"), "Who designed Luma?", payload)
        for hop in hops:
            for src in hop.get("sources", []):
                self.assertIs(type(src.get("index")), int, payload)
                self.assertEqual(src.get("index"), 1, payload)
        # Bridge URLs intermediate, not final.
        final_urls = [s.get("url") for s in sources]
        self.assertNotIn(URL1, final_urls, payload)
        self.assertNotIn(URL2, final_urls, payload)
        blob = json.dumps(payload)
        self.assertIn(URL1, blob, payload)
        self.assertIn(URL2, blob, payload)
        intermediate = research.get("intermediate_evidence", [])
        inter_urls = [
            item.get("url") if isinstance(item, dict) else item
            for item in intermediate
        ]
        self.assertIn(URL1, inter_urls, payload)
        self.assertIn(URL2, inter_urls, payload)
        self.assertNotIn(URL3, inter_urls, payload)

    def test_without_research_single_legacy_search_no_metadata(self):
        calls = []
        _, tools = self.load_tools(self.chain_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": QUESTION})
        )
        self.assertEqual(len(calls), 1, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertEqual(
            payload.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", payload
        )
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("metadata", payload, payload)
        self.assertNotIn("hops", payload, payload)

    def test_ambiguous_bridge_abstains_after_one_search(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == "What does Runa orbit?":
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Runa",
                            "url": "https://example.com/runa-a",
                            "extract": "Runa orbits Porta.",
                        },
                        {
                            "title": "Runa",
                            "url": "https://example.com/runa-b",
                            "extract": "Runa orbits Vela.",
                        },
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": QUESTION,
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 4,
                }
            )
        )
        self.assertEqual(len(calls), 1, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertEqual(
            payload.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", payload
        )
        self.assertNotIn("answer", payload, payload)
        # No guessed binding.
        blob = json.dumps(payload)
        self.assertNotIn("Porta", blob, payload)
        self.assertNotIn("Vela", blob, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "abstained", payload)

    def test_negative_first_hop_abstains(self):
        for extract in (
            "Runa does not orbit Porta.",
            "Runa perhaps orbits Porta.",
        ):
            with self.subTest(extract=extract):
                calls = []

                def fake(query, *, max_results=5, _ex=extract):
                    calls.append((query, max_results))
                    if query == "What does Runa orbit?":
                        return {
                            "ok": True,
                            "results": [
                                {
                                    "title": "Runa",
                                    "url": URL1,
                                    "extract": _ex,
                                }
                            ],
                        }
                    return {"ok": True, "results": []}

                _, tools = self.load_tools(fake)
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {
                            "query": QUESTION,
                            "research": True,
                            "max_hops": 3,
                            "max_searches": 4,
                        }
                    )
                )
                self.assertEqual(len(calls), 1, payload)
                self.assertIs(payload.get("ok"), False, payload)
                self.assertEqual(
                    payload.get("error", {}).get("code"),
                    "INSUFFICIENT_EVIDENCE",
                    payload,
                )
                self.assertNotIn("answer", payload, payload)
                research = payload.get("metadata", {}).get("research", {})
                self.assertEqual(research.get("status"), "abstained", payload)

    def test_insufficient_first_hop_abstains(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": QUESTION,
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 4,
                }
            )
        )
        self.assertEqual(len(calls), 1, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertEqual(
            payload.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", payload
        )
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "abstained", payload)


class FacetDispatchTests(OfflineTestCase, FixtureMixin):
    FACETS_QUERY = "Who wrote Cobalt?; Who designed Briar?"
    Q1 = "Who wrote Cobalt?"
    Q2 = "Who designed Briar?"
    URL1 = "https://example.com/cobalt-wrote"
    URL2 = "https://example.com/briar-designed"
    S1 = "Mira wrote Cobalt."
    S2 = "Nera designed Briar."

    def _facets_fake(self, calls, q2_results=None):
        q2 = q2_results if q2_results is not None else [
            {"title": "Briar", "url": self.URL2, "extract": self.S2}
        ]

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.Q1:
                return {
                    "ok": True,
                    "results": [
                        {"title": "Cobalt", "url": self.URL1, "extract": self.S1}
                    ],
                }
            if query == self.Q2:
                return {"ok": True, "results": list(q2)}
            return {"ok": True, "results": []}

        return fake

    def test_facets_success_two_cited_claims(self):
        import re

        calls = []
        _, tools = self.load_tools(self._facets_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.FACETS_QUERY,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(
            payload.get("answer"),
            "%s [1]\n%s [2]" % (self.S1, self.S2),
            payload,
        )
        sources = payload.get("sources")
        self.assertEqual(len(sources), 2, payload)
        self.assertEqual([s.get("index") for s in sources], [1, 2], payload)
        self.assertEqual([s.get("url") for s in sources], [self.URL1, self.URL2], payload)
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", payload.get("answer", ""))}
        self.assertEqual(cited, {1, 2}, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "completed", payload)
        self.assertEqual(research.get("planned"), 2, payload)
        self.assertEqual(research.get("executed"), 2, payload)
        self.assertEqual(research.get("search_calls"), 2, payload)
        self.assertEqual([q for q, _ in calls], [self.Q1, self.Q2], payload)

    def test_facets_second_facet_failure_partial_no_answer(self):
        variants = {
            "missing": [],
            "negative": [
                {
                    "title": "Briar",
                    "url": self.URL2,
                    "extract": "Nera did not design Briar.",
                }
            ],
            "modal": [
                {
                    "title": "Briar",
                    "url": self.URL2,
                    "extract": "Nera perhaps designed Briar.",
                }
            ],
            "conflicting": [
                {
                    "title": "Briar",
                    "url": self.URL2,
                    "extract": "Nera designed Briar.",
                },
                {
                    "title": "Briar",
                    "url": "https://example.com/briar-other",
                    "extract": "Tessa designed Briar.",
                },
            ],
        }
        for name, q2 in variants.items():
            with self.subTest(variant=name):
                calls = []
                _, tools = self.load_tools(self._facets_fake(calls, q2_results=q2))
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {
                            "query": self.FACETS_QUERY,
                            "research": True,
                            "max_hops": 1,
                            "max_searches": 2,
                        }
                    )
                )
                self.assertIs(payload.get("ok"), False, payload)
                self.assertEqual(
                    payload.get("error", {}).get("code"),
                    "INSUFFICIENT_EVIDENCE",
                    payload,
                )
                self.assertNotIn("answer", payload, payload)
                research = payload.get("metadata", {}).get("research", {})
                self.assertEqual(research.get("status"), "partial", payload)

    def test_bare_conjunction_unsupported(self):
        calls = []
        _, tools = self.load_tools(self._facets_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "Who wrote Cobalt and Briar?",
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "unsupported", payload)

    def test_same_url_dedup_single_source(self):
        import re

        url = "https://example.com/shared-evidence"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.Q1:
                return {
                    "ok": True,
                    "results": [
                        {"title": "Cobalt", "url": url, "extract": self.S1}
                    ],
                }
            if query == self.Q2:
                return {
                    "ok": True,
                    "results": [
                        {"title": "Briar", "url": url, "extract": self.S2}
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.FACETS_QUERY,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        sources = payload.get("sources")
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)
        self.assertEqual(sources[0].get("url"), url, payload)
        self.assertEqual(
            payload.get("answer"),
            "%s [1]\n%s [1]" % (self.S1, self.S2),
            payload,
        )
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", payload.get("answer", ""))}
        self.assertEqual(cited, {1}, payload)

    def test_max_results_one_partial_not_silent_drop(self):
        calls = []
        _, tools = self.load_tools(self._facets_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.FACETS_QUERY,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                    "max_results": 1,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "partial", payload)


class ComparisonDispatchTests(OfflineTestCase, FixtureMixin):
    Q1 = "What is the capital of Porta?"
    Q2 = "What is the capital of Vela?"
    URL1 = "https://example.com/porta-capital"
    URL2 = "https://example.com/vela-capital"
    S1 = "Luma is the capital of Porta."
    S2 = "Zara is the capital of Vela."

    def _fake(self, calls):
        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.Q1:
                return {
                    "ok": True,
                    "results": [
                        {"title": "Porta", "url": self.URL1, "extract": self.S1}
                    ],
                }
            if query == self.Q2:
                return {
                    "ok": True,
                    "results": [
                        {"title": "Vela", "url": self.URL2, "extract": self.S2}
                    ],
                }
            return {"ok": True, "results": []}

        return fake

    def test_plural_capitals_success(self):
        calls = []
        _, tools = self.load_tools(self._fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "What are the capitals of Porta and Vela?",
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn(self.S1, payload.get("answer", ""), payload)
        self.assertIn(self.S2, payload.get("answer", ""), payload)
        self.assertEqual(len(payload.get("sources", [])), 2, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "completed", payload)
        self.assertEqual(research.get("kind"), "comparison", payload)

    def test_compare_capitals_evidence_only(self):
        calls = []
        _, tools = self.load_tools(self._fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "Compare the capitals of Porta and Vela.",
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn(self.S1, payload.get("answer", ""), payload)
        self.assertIn(self.S2, payload.get("answer", ""), payload)
        # No numeric/ranking inference.
        for token in ("larger", "taller", "better", "1st", "first", "rank"):
            self.assertNotIn(token, payload.get("answer", "").casefold(), payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "completed", payload)
        self.assertEqual(research.get("kind"), "comparison", payload)


class IntersectionDispatchTests(OfflineTestCase, FixtureMixin):
    AUTHOR_Q = "Who both wrote Cobalt and designed Briar?"
    Q1 = "Who wrote Cobalt?"
    Q2 = "Who designed Briar?"
    URL1 = "https://example.com/cobalt-wrote"
    URL2 = "https://example.com/briar-designed"

    def _author_fake(self, calls, s1=None, s2=None, q2_extra=None):
        s1 = s1 if s1 is not None else "Mira wrote Cobalt."
        s2 = s2 if s2 is not None else "Mira designed Briar."

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.Q1:
                return {
                    "ok": True,
                    "results": [
                        {"title": "Cobalt", "url": self.URL1, "extract": s1}
                    ],
                }
            if query == self.Q2:
                results = [{"title": "Briar", "url": self.URL2, "extract": s2}]
                if q2_extra:
                    results.extend(q2_extra)
                return {"ok": True, "results": list(results)}
            return {"ok": True, "results": []}

        return fake

    def test_author_intersection_same_actor(self):
        calls = []
        _, tools = self.load_tools(self._author_fake(calls))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.AUTHOR_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn("Mira wrote Cobalt.", payload.get("answer", ""), payload)
        self.assertIn("Mira designed Briar.", payload.get("answer", ""), payload)
        self.assertEqual(len(payload.get("sources", [])), 2, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "completed", payload)
        self.assertEqual(research.get("kind"), "intersection", payload)

    def test_author_intersection_distinct_abstains(self):
        calls = []
        _, tools = self.load_tools(
            self._author_fake(calls, s1="Mira wrote Cobalt.", s2="Nera designed Briar.")
        )
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.AUTHOR_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "abstained", payload)

    def test_author_intersection_ambiguous_abstains(self):
        calls = []
        extra = [
            {
                "title": "Briar",
                "url": "https://example.com/briar-other",
                "extract": "Tessa designed Briar.",
            }
        ]
        _, tools = self.load_tools(
            self._author_fake(
                calls, s1="Mira wrote Cobalt.", s2="Mira designed Briar.",
                q2_extra=extra,
            )
        )
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.AUTHOR_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "abstained", payload)

    def test_author_intersection_missing_partial(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.Q1:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": self.URL1,
                            "extract": "Mira wrote Cobalt.",
                        }
                    ],
                }
            if query == self.Q2:
                return {"ok": True, "results": []}
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.AUTHOR_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "partial", payload)

    def test_capital_intersection_unique_equality(self):
        q1 = "What is the capital of Porta?"
        q2 = "What is the capital of Vela?"
        url1 = "https://example.com/porta-capital"
        url2 = "https://example.com/vela-capital"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == q1:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Porta",
                            "url": url1,
                            "extract": "Luma is the capital of Porta.",
                        }
                    ],
                }
            if query == q2:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Vela",
                            "url": url2,
                            "extract": "Luma is the capital of Vela.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "Which city is the capital of both Porta and Vela?",
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn("Luma is the capital of Porta.", payload.get("answer", ""), payload)
        self.assertIn("Luma is the capital of Vela.", payload.get("answer", ""), payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "completed", payload)
        self.assertEqual(research.get("kind"), "intersection", payload)

    def test_capital_intersection_distinct_abstains(self):
        q1 = "What is the capital of Porta?"
        q2 = "What is the capital of Vela?"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == q1:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Porta",
                            "url": "https://example.com/porta-capital",
                            "extract": "Luma is the capital of Porta.",
                        }
                    ],
                }
            if query == q2:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Vela",
                            "url": "https://example.com/vela-capital",
                            "extract": "Zara is the capital of Vela.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "Which city is the capital of both Porta and Vela?",
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "abstained", payload)


class TemporalDispatchTests(OfflineTestCase, FixtureMixin):
    WHEN_Q = "When was the inventor of Cobalt born?"
    WHERE_Q = "Where was the inventor of Cobalt born?"
    HOP1_QUERY = "Who invented Cobalt?"
    HOP1_URL = "https://example.com/cobalt-inventor"
    HOP2_URL = "https://example.com/mira-vale-birth"
    HOP1_RESULTS = [
        {
            "title": "Cobalt",
            "url": "https://example.com/cobalt-inventor",
            "extract": "Mira Vale invented Cobalt.",
        }
    ]
    YEAR_Q = "Who invented Cobalt in 1984?"
    YEAR_URL = "https://example.com/cobalt-invented-year"
    YEAR_POSITIVE = "Cobalt was invented in 1984 by Mira Vale."
    BEFORE_Q = "Was Mira Vale born before Nera Voss?"
    BETWEEN_Q = "How many years between the births of Mira Vale and Nera Voss?"
    PRONOUN_Q = "Which of those was earlier?"

    def _birth_fake(self, calls, hop2_results):
        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.HOP1_QUERY:
                return {"ok": True, "results": list(self.HOP1_RESULTS)}
            low = query.casefold()
            if "mira vale" in low and "born" in low:
                return {"ok": True, "results": list(hop2_results)}
            return {"ok": True, "results": []}

        return fake

    def _find_intermediate(self, payload):
        for key in ("provenance", "metadata"):
            container = payload.get(key)
            if isinstance(container, dict):
                if isinstance(container.get("intermediate_evidence"), list):
                    return container["intermediate_evidence"]
                research = container.get("research")
                if isinstance(research, dict) and isinstance(
                    research.get("intermediate_evidence"), list
                ):
                    return research["intermediate_evidence"]
        if isinstance(payload.get("intermediate_evidence"), list):
            return payload["intermediate_evidence"]
        research = payload.get("metadata", {}).get("research", {})
        if isinstance(research.get("intermediate_evidence"), list):
            return research["intermediate_evidence"]
        return None

    def test_when_born_date_success_final_direct_only(self):
        import re

        hop2 = [
            {
                "title": "Mira Vale",
                "url": self.HOP2_URL,
                "extract": "Mira Vale was born in 1984.",
            }
        ]
        calls = []
        _, tools = self.load_tools(self._birth_fake(calls, hop2))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.WHEN_Q,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        answer = payload.get("answer", "")
        self.assertIn("Mira Vale was born in 1984.", answer, payload)
        self.assertIn("[1]", answer, payload)
        self.assertNotIn("[2]", answer, payload)
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(sources[0].get("url"), self.HOP2_URL, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)
        self.assertIs(type(sources[0].get("index")), int, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "completed", payload)
        self.assertEqual(len(calls), 2, payload)
        self.assertEqual(calls[0][0], self.HOP1_QUERY, payload)
        self.assertIn("Mira Vale", calls[1][0], payload)
        self.assertIn("born", calls[1][0].casefold(), payload)
        final_urls = [s.get("url") for s in sources]
        self.assertNotIn(self.HOP1_URL, final_urls, payload)
        blob = json.dumps(payload)
        self.assertIn(self.HOP1_URL, blob, payload)
        intermediate = self._find_intermediate(payload)
        self.assertIsNotNone(intermediate, payload)
        urls = [
            item.get("url") if isinstance(item, dict) else item
            for item in intermediate
        ]
        self.assertIn(self.HOP1_URL, urls, payload)
        self.assertNotIn(self.HOP2_URL, urls, payload)
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        self.assertEqual(cited, {1}, payload)

    def test_where_location_positive_where_rejects_date_only(self):
        # Positive location case.
        hop2_loc = [
            {
                "title": "Mira Vale",
                "url": self.HOP2_URL,
                "extract": "Mira Vale was born in Arbor.",
            }
        ]
        calls = []
        _, tools = self.load_tools(self._birth_fake(calls, hop2_loc))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.WHERE_Q,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn("Mira Vale was born in Arbor.", payload.get("answer", ""), payload)
        # Date-only evidence must NOT satisfy a where question.
        hop2_date = [
            {
                "title": "Mira Vale",
                "url": self.HOP2_URL,
                "extract": "Mira Vale was born in 1984.",
            }
        ]
        calls2 = []
        _, tools2 = self.load_tools(self._birth_fake(calls2, hop2_date))
        payload2 = json.loads(
            tools2["goat_answer"]["handler"](
                {
                    "query": self.WHERE_Q,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertIs(payload2.get("ok"), False, payload2)
        self.assertNotIn("answer", payload2, payload2)
        # Location-only evidence must NOT satisfy a when question.
        calls3 = []
        _, tools3 = self.load_tools(self._birth_fake(calls3, hop2_loc))
        payload3 = json.loads(
            tools3["goat_answer"]["handler"](
                {
                    "query": self.WHEN_Q,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertIs(payload3.get("ok"), False, payload3)
        self.assertNotIn("answer", payload3, payload3)
        self.assertNotIn("1984", json.dumps(payload3), payload3)

    def test_temporal_qualifier_year_grounding(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if "1984" in query:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": self.YEAR_URL,
                            "extract": self.YEAR_POSITIVE,
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.YEAR_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn(self.YEAR_POSITIVE, payload.get("answer", ""), payload)
        self.assertIn("1984", payload.get("answer", ""), payload)
        self.assertNotIn("1985", payload.get("answer", ""), payload)
        # Query sent for retrieval MUST include 1984.
        self.assertTrue(any("1984" in q for q, _ in calls), payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "completed", payload)
        # Plan records distinct retrieval vs grounding plus literal year.
        blob = json.dumps(research).casefold()
        self.assertIn("1984", blob, payload)
        # Evidence without the year, or with the wrong year, abstains.
        for extract in (
            "Mira Vale invented Cobalt.",
            "Cobalt was invented in 1985 by Mira Vale.",
        ):
            with self.subTest(extract=extract):
                sub_calls = []

                def fake2(query, *, max_results=5, _ex=extract):
                    sub_calls.append((query, max_results))
                    return {
                        "ok": True,
                        "results": [
                            {
                                "title": "Cobalt",
                                "url": self.YEAR_URL,
                                "extract": _ex,
                            }
                        ],
                    }

                _, tools2 = self.load_tools(fake2)
                payload2 = json.loads(
                    tools2["goat_answer"]["handler"](
                        {
                            "query": self.YEAR_Q,
                            "research": True,
                            "max_hops": 1,
                            "max_searches": 2,
                        }
                    )
                )
                self.assertIs(payload2.get("ok"), False, payload2)
                self.assertNotIn("answer", payload2, payload2)

    def test_temporal_compare_never_calculates(self):
        url_a = "https://example.com/mira-vale-birth"
        url_b = "https://example.com/nera-voss-birth"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            low = query.casefold()
            if "mira vale" in low and "born" in low:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Mira Vale",
                            "url": url_a,
                            "extract": "Mira Vale was born in 1984.",
                        }
                    ],
                }
            if "nera voss" in low and "born" in low:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Nera Voss",
                            "url": url_b,
                            "extract": "Nera Voss was born in 1990.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.BEFORE_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertIn(research.get("status"), ("unsupported", "partial"), payload)
        self.assertIn(
            str(research.get("reason", "")),
            ("unsupported_temporal_compare",),
            payload,
        )
        # Query coverage spans both names when operands resolve.
        blob_calls = json.dumps(calls)
        self.assertIn("Mira Vale", blob_calls, payload)
        self.assertIn("Nera Voss", blob_calls, payload)
        # Source URLs intermediate only, never phantom final sources.
        self.assertNotIn("sources", payload, payload)
        blob = json.dumps(payload)
        self.assertIn(url_a, blob, payload)
        self.assertIn(url_b, blob, payload)
        for token in ("earlier", "before", "older", "first"):
            self.assertNotIn(token, blob.casefold().replace("before nera", ""), payload)

    def test_arithmetic_between_never_differences(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.BETWEEN_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertIn(research.get("status"), ("unsupported", "partial"), payload)
        self.assertIn(
            str(research.get("reason", "")), ("unsupported_arithmetic",), payload
        )
        self.assertNotIn("sources", payload, payload)
        # No fabricated difference number leaks.
        self.assertNotIn("6", json.dumps(payload), payload)

    def test_pronoun_scope_zero_calls_and_modal_abstains(self):
        calls = []
        _, tools = self.load_tools(self._birth_fake(calls, []))
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.PRONOUN_Q,
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 2,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertEqual(calls, [], payload)
        # Modal / negative / conflicting birth statements abstain.
        for extract in (
            "Mira Vale may have been born in 1984.",
            "Mira Vale was not born in 1984.",
            "Mira Vale perhaps was born in 1984.",
        ):
            with self.subTest(extract=extract):
                hop2 = [
                    {"title": "Mira Vale", "url": self.HOP2_URL, "extract": extract}
                ]
                sub_calls = []
                _, sub_tools = self.load_tools(self._birth_fake(sub_calls, hop2))
                sub_payload = json.loads(
                    sub_tools["goat_answer"]["handler"](
                        {
                            "query": self.WHEN_Q,
                            "research": True,
                            "max_hops": 2,
                            "max_searches": 4,
                        }
                    )
                )
                self.assertIs(sub_payload.get("ok"), False, sub_payload)
                self.assertNotIn("answer", sub_payload, sub_payload)


class ExecutionReceiptTests(OfflineTestCase, FixtureMixin):
    """Cycle6a TEST-ONLY execution receipt / hard-budget adversarial tracer.

    Real BUILT bundle register+JSON public research=True three relation chain
    using ONLY fake HTTP _fetch on default_dependencies (real
    wikipedia_answer_search/parser/classifier/planner/grounding). No real
    DNS/socket.
    """

    QUESTION_Z = "Who designed the capital of the body orbited by Zori?"
    EXPECTED_QUERIES = [
        "What does Zori orbit?",
        "What is the capital of Talor?",
        "Who designed Eren?",
    ]
    CANON_Z = "https://en.wikipedia.org/wiki/Zori"
    CANON_T = "https://en.wikipedia.org/wiki/Talor"
    CANON_E = "https://en.wikipedia.org/wiki/Eren"

    def _load_default_tools(self, fake_fetch):
        tmp, pkgdir = build_fixture_package()
        self.addCleanup(shutil.rmtree, tmp, True)
        module_name, module = load_fixture_package(pkgdir)
        self.addCleanup(unload_fixture_package, module_name)
        wiring = module.v3_wiring
        deps = wiring.default_dependencies(_fetch=fake_fetch)
        ctx = RecordingContext()
        module.register(ctx, deps=deps)
        return module, ctx.tools, wiring

    def _zori_fetch(self, calls, mode="success"):
        def fake_fetch(url, **kwargs):
            calls.append(url)
            import urllib.parse as _up

            parts = _up.urlsplit(url)
            qs = _up.parse_qs(parts.query)
            if "srsearch" in qs:
                sr = qs.get("srsearch", [""])[0]
                low = sr.casefold()
                if "zori" in low:
                    body = json.dumps(
                        {"query": {"search": [{"title": "Zori", "pageid": 101}]}}
                    ).encode("utf-8")
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                if "talor" in low:
                    if mode == "error_second_429":
                        return {"status": 429, "headers": {}, "body": b"{}", "url": url}
                    body = json.dumps(
                        {"query": {"search": [{"title": "Talor", "pageid": 102}]}}
                    ).encode("utf-8")
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                if "eren" in low:
                    body = json.dumps(
                        {"query": {"search": [{"title": "Eren", "pageid": 103}]}}
                    ).encode("utf-8")
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                body = json.dumps({"query": {"search": []}}).encode("utf-8")
                return {"status": 200, "headers": {}, "body": body, "url": url}
            if "pageids" in qs or "titles" in qs:
                titles = qs.get("titles", [""])[0] if "titles" in qs else ""
                pageids = qs.get("pageids", [""])[0] if "pageids" in qs else ""
                combo = (titles + " " + pageids).casefold()
                if "101" in combo or "zori" in combo:
                    body = json.dumps(
                        {
                            "query": {
                                "pages": [
                                    {
                                        "pageid": 101,
                                        "title": "Zori",
                                        "extract": "Zori orbits Talor.",
                                    }
                                ]
                            }
                        }
                    ).encode("utf-8")
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                if "102" in combo or "talor" in combo:
                    body = json.dumps(
                        {
                            "query": {
                                "pages": [
                                    {
                                        "pageid": 102,
                                        "title": "Talor",
                                        "extract": "Eren is the capital of Talor.",
                                    }
                                ]
                            }
                        }
                    ).encode("utf-8")
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                if "103" in combo or "eren" in combo:
                    body = json.dumps(
                        {
                            "query": {
                                "pages": [
                                    {
                                        "pageid": 103,
                                        "title": "Eren",
                                        "extract": "Liora Hale designed Eren.",
                                    }
                                ]
                            }
                        }
                    ).encode("utf-8")
                    return {"status": 200, "headers": {}, "body": body, "url": url}
                body = json.dumps({"query": {"pages": []}}).encode("utf-8")
                return {"status": 200, "headers": {}, "body": body, "url": url}
            if "list=search" in url:
                body = json.dumps({"query": {"search": []}}).encode("utf-8")
                return {"status": 200, "headers": {}, "body": body, "url": url}
            if "prop=extracts" in url:
                body = json.dumps({"query": {"pages": []}}).encode("utf-8")
                return {"status": 200, "headers": {}, "body": body, "url": url}
            body = json.dumps({"query": {"search": []}}).encode("utf-8")
            return {"status": 200, "headers": {}, "body": body, "url": url}

        return fake_fetch

    def test_three_relation_receipt_exact_budgets(self):
        import re

        fetch_calls = []
        _, tools, _wiring = self._load_default_tools(self._zori_fetch(fetch_calls, "success"))
        handler = tools["goat_answer"]["handler"]
        payload = json.loads(
            handler(
                {
                    "query": self.QUESTION_Z,
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 3,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        # Exactly 3 logical queries in dependency order via hops.
        hops = payload.get("hops")
        self.assertIsInstance(hops, list, payload)
        self.assertEqual(len(hops), 3, payload)
        self.assertEqual([h.get("query") for h in hops], self.EXPECTED_QUERIES, payload)
        # Exactly 6 HTTP fetch calls (2 per logical query).
        self.assertEqual(len(fetch_calls), 6, payload)
        search_reqs = [u for u in fetch_calls if "srsearch" in u or "list=search" in u]
        extract_reqs = [u for u in fetch_calls if "prop=extracts" in u or "pageids" in u or "titles" in u]
        # Parsed generator search vs intro extract dispatch.
        self.assertEqual(len(search_reqs), 3, payload)
        self.assertEqual(len(extract_reqs), 3, payload)
        # Final only terminal URL cited contiguous index 1.
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertIs(type(sources[0].get("index")), int, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)
        self.assertEqual(sources[0].get("url"), self.CANON_E, payload)
        answer = payload.get("answer", "")
        self.assertIn("Liora Hale designed Eren.", answer, payload)
        self.assertIn("[1]", answer, payload)
        self.assertNotIn("[2]", answer, payload)
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        self.assertEqual(cited, {1}, payload)
        # Intermediate first 2 safe URLs, terminal excluded.
        research = payload.get("metadata", {}).get("research", {})
        intermediate = research.get("intermediate_evidence", [])
        inter_urls = [i.get("url") if isinstance(i, dict) else i for i in intermediate]
        self.assertIn(self.CANON_Z, inter_urls, payload)
        self.assertIn(self.CANON_T, inter_urls, payload)
        self.assertNotIn(self.CANON_E, inter_urls, payload)
        final_urls = [s.get("url") for s in sources]
        self.assertNotIn(self.CANON_Z, final_urls, payload)
        self.assertNotIn(self.CANON_T, final_urls, payload)
        # Strict execution receipt metadata.
        self.assertEqual(research.get("search_calls"), 3, payload)
        self.assertEqual(research.get("http_requests"), 6, payload)
        self.assertEqual(research.get("max_http_requests"), 6, payload)
        self.assertEqual(research.get("max_http_requests"), 2 * 3, payload)
        self.assertEqual(research.get("status"), "completed", payload)

    def test_per_hop_429_partial_receipt(self):
        fetch_calls = []
        _, tools, _wiring = self._load_default_tools(
            self._zori_fetch(fetch_calls, "error_second_429")
        )
        handler = tools["goat_answer"]["handler"]
        payload = json.loads(
            handler(
                {
                    "query": self.QUESTION_Z,
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 3,
                }
            )
        )
        # First relation success (2 requests), second search 429.
        self.assertEqual(len(fetch_calls), 3, payload)
        self.assertIs(payload.get("ok"), False, payload)
        err = payload.get("error", {}).get("code")
        self.assertIn(err, ("RATE_LIMITED", "HTTP_ERROR"), payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "partial", payload)
        self.assertEqual(research.get("search_calls"), 2, payload)
        self.assertEqual(research.get("http_requests"), 3, payload)
        # Safe intermediate URL of hop1 present.
        intermediate = research.get("intermediate_evidence", [])
        inter_urls = [i.get("url") if isinstance(i, dict) else i for i in intermediate]
        self.assertIn(self.CANON_Z, inter_urls, payload)
        # Per-hop sanitized error code visible in metadata/provenance hops.
        hops = payload.get("hops")
        if hops is None:
            hops = payload.get("metadata", {}).get("hops", None)
        if hops is None:
            prov = payload.get("provenance", {})
            hops = prov.get("hops", None) if isinstance(prov, dict) else None
        self.assertIsInstance(hops, list, payload)
        blob_hops = json.dumps(hops)
        self.assertIn(err, blob_hops, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        blob = json.dumps(payload)
        self.assertNotIn("Traceback", blob, payload)
        self.assertNotIn("SECRET", blob, payload)
        self.assertNotIn("user:secret", blob.casefold(), payload)

    def test_malformed_backend_explicit_partial(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == "What does Zori orbit?":
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Zori",
                            "url": "https://example.com/zori-orbit",
                            "extract": "Zori orbits Talor.",
                        }
                    ],
                }
            if query == "What is the capital of Talor?":
                return {"ok": True, "results": "not-a-list"}
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.QUESTION_Z,
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 3,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertEqual(payload.get("error", {}).get("code"), "URL_BLOCKED", payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "partial", payload)
        self.assertIn("search_calls", research, payload)

    def test_thrown_after_first_hop_counts_attempt(self):
        for exc_kind in ("OSError", "TypeError"):
            with self.subTest(exc_kind=exc_kind):
                calls = []
                marker = "CRED-MARKER-9f3b2"

                def fake(query, *, max_results=5):
                    calls.append((query, max_results))
                    if query == "What does Zori orbit?":
                        return {
                            "ok": True,
                            "results": [
                                {
                                    "title": "Zori",
                                    "url": "https://example.com/zori-orbit",
                                    "extract": "Zori orbits Talor.",
                                }
                            ],
                        }
                    if query == "What is the capital of Talor?":
                        if exc_kind == "OSError":
                            raise OSError("transport down " + marker)
                        raise TypeError("bad type " + marker)
                    return {"ok": True, "results": []}

                _, tools = self.load_tools(fake)
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {
                            "query": self.QUESTION_Z,
                            "research": True,
                            "max_hops": 3,
                            "max_searches": 3,
                        }
                    )
                )
                self.assertEqual(len(calls), 2, payload)
                self.assertIs(payload.get("ok"), False, payload)
                research = payload.get("metadata", {}).get("research", {})
                # Attempted search counted BEFORE exception.
                self.assertEqual(research.get("search_calls"), 2, payload)
                self.assertIn(research.get("status"), ("partial", "abstained"), payload)
                blob = json.dumps(payload)
                self.assertNotIn(marker, blob, payload)
                self.assertNotIn("Traceback", blob, payload)


class HardLogicalCapTests(OfflineTestCase, FixtureMixin):
    def test_budget_aware_typeerror_no_retry_single_hop(self):
        calls = []

        def fake(query, *, max_results=5, _request_budget=None):
            calls.append((query, max_results, _request_budget is not None))
            if _request_budget is not None:
                raise TypeError("inner budget failure SECRET-RETRY-MARK")
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Porta",
                        "url": "https://example.com/porta",
                        "extract": "Luma is the capital of Porta.",
                    }
                ],
            }

        fake._GOAT_BUDGET_AWARE = True
        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "What is the capital of Porta?",
                    "research": True,
                    "max_hops": 1,
                    "max_searches": 1,
                }
            )
        )
        # Must call EXACTLY ONCE, no TypeError-driven retry without budget.
        self.assertEqual(len(calls), 1, payload)
        research = payload.get("metadata", {}).get("research", {})
        # Metadata counts the attempt (1, not 0).
        self.assertEqual(research.get("search_calls"), 1, payload)
        # Custom backend physical requests unknown/null, not a hard HTTP claim.
        http_req = research.get("http_requests", None)
        self.assertIn(http_req, (None,), payload)


class HardPhysicalCapTests(OfflineTestCase, FixtureMixin):
    def test_default_no_explicit_budget_at_most_two_fetch(self):
        import json as _json

        module = self.load_module()
        wiring = module.v3_wiring
        factory = getattr(wiring, "make_default_answer_search", None)
        self.assertTrue(callable(factory))
        search_body = _json.dumps(
            {"query": {"search": [{"title": "Mira Vale", "pageid": 7}]}}
        ).encode("utf-8")
        extracts_body = _json.dumps(
            {
                "query": {
                    "pages": [
                        {
                            "pageid": 7,
                            "title": "Mira Vale",
                            "extract": "Mira Vale was born in Arbor.",
                        }
                    ]
                }
            }
        ).encode("utf-8")
        fetch_calls = []

        def fake_fetch(url, **kwargs):
            fetch_calls.append(url)
            if "list=search" in url:
                return {"status": 200, "headers": {}, "body": search_body, "url": url}
            if "prop=extracts" in url:
                return {"status": 200, "headers": {}, "body": extracts_body, "url": url}
            return {"status": 200, "headers": {}, "body": search_body, "url": url}

        answer_search = factory(_fetch=fake_fetch)
        # Positive control with the real stack: one logical call uses
        # exactly two HTTP requests (spec is <=2 per logical call).
        r1 = answer_search("Mira Vale born", max_results=5)
        self.assertEqual(len(fetch_calls), 2, r1)
        # Reset between positive control and adversarial component test.
        del fetch_calls[:]
        # Adversarial budget-component test: a single logical call WITHOUT
        # a private budget where the controlled component fake attempts
        # three transport calls. The third must never reach fetch.
        # Spec is <=2 per logical call and <=2*max_searches per OP token;
        # independent logical helper calls each may use two, so the old
        # factory-lifetime second-call assertion was defective and is
        # replaced here. This callback mock tests ONLY the budget
        # component; the registered public three-relation test still uses
        # the real parser/classifier/planner/grounding.
        real_fn = wiring._vendor_stack.wikipedia_answer_search
        base = "https://en.wikipedia.org/w/api.php"

        def adversarial(query_text, transport=None, max_results=5, **kw):
            t = transport
            t(base + "?action=query&attempt=1")
            t(base + "?action=query&attempt=2")
            t(base + "?action=query&attempt=3")
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Mira Vale",
                        "url": "https://example.com/mira-vale",
                        "extract": "Mira Vale was born in Arbor.",
                    }
                ],
            }

        wiring._vendor_stack.wikipedia_answer_search = adversarial
        try:
            r2 = answer_search("Mira Vale born", max_results=5)
        finally:
            wiring._vendor_stack.wikipedia_answer_search = real_fn
        self.assertEqual(len(fetch_calls), 2, (r1, r2, fetch_calls))
        self.assertFalse(
            any("attempt=3" in u for u in fetch_calls), (r2, fetch_calls)
        )
        self.assertIsInstance(r2, dict, (r1, r2))
        err = (r2.get("error", {}) or {}).get("code") if isinstance(r2.get("error"), dict) else None
        self.assertEqual(err, "INSUFFICIENT_EVIDENCE", (r1, r2))


class MaliciousQueryGuardTests(OfflineTestCase, FixtureMixin):
    def test_credential_url_rejected_zero_calls(self):
        cred = "https://user:secret@example.com/foo"
        queries = [
            "Who designed %s?" % cred,
            "What is the capital of Porta %s?" % cred,
        ]
        for q in queries:
            with self.subTest(q=q):
                calls = []

                def fake(query, *, max_results=5):
                    calls.append((query, max_results))
                    return {"ok": True, "results": []}

                _, tools = self.load_tools(fake)
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {"query": q, "research": True, "max_hops": 2, "max_searches": 2}
                    )
                )
                self.assertEqual(calls, [], payload)
                self.assertIs(payload.get("ok"), False, payload)
                self.assertEqual(
                    payload.get("error", {}).get("code"), "URL_BLOCKED", payload
                )
                blob = json.dumps(payload)
                self.assertNotIn("user:secret", blob, payload)
                self.assertNotIn("secret@example", blob, payload)

    def test_control_chars_rejected_zero_calls(self):
        for q in ("Who designed Briar?\x00", "Who designed Briar\x1f?"):
            with self.subTest(q=repr(q)):
                calls = []

                def fake(query, *, max_results=5):
                    calls.append((query, max_results))
                    return {"ok": True, "results": []}

                _, tools = self.load_tools(fake)
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {"query": q, "research": True, "max_hops": 1, "max_searches": 2}
                    )
                )
                self.assertEqual(calls, [], payload)
                self.assertIs(payload.get("ok"), False, payload)
                self.assertEqual(
                    payload.get("error", {}).get("code"), "URL_BLOCKED", payload
                )
                blob = json.dumps(payload)
                self.assertNotIn("\x00", blob, payload)
                self.assertNotIn("\x1f", blob, payload)

    def test_bound_entity_source_cannot_copy_userinfo(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == "What does Zori orbit?":
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Zori",
                            "url": "https://user:secret@example.com/evil",
                            "extract": "Zori orbits Talor.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "Who designed the capital of the body orbited by Zori?",
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 3,
                }
            )
        )
        blob = json.dumps(payload)
        self.assertNotIn("user:secret", blob, payload)
        self.assertNotIn("secret@example", blob, payload)


class AggregateCandidatesGuardTests(OfflineTestCase, FixtureMixin):
    def test_per_call_five_and_total_forty_with_counts(self):
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            # Record per-call candidate volume via max_results echo.
            self.assertLessEqual(max_results, 5, (query, max_results))
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": "Who designed the capital of the body orbited by Zori?",
                    "research": True,
                    "max_hops": 3,
                    "max_searches": 8,
                }
            )
        )
        research = payload.get("metadata", {}).get("research", {})
        # Future-expected aggregate accounting: per-call <=5 and total <=40.
        per_call = research.get("max_candidates_per_call", research.get("candidates_per_call", None))
        total = research.get("max_candidates_total", research.get("candidates_total", None))
        self.assertIsNotNone(per_call, payload)
        self.assertIsNotNone(total, payload)
        self.assertLessEqual(int(per_call), 5, payload)
        self.assertLessEqual(int(total), 40, payload)


class LegacyPartialMetadataTests(OfflineTestCase, FixtureMixin):
    COBALT_QUESTION = "Where was the inventor of Cobalt born?"
    HOP1_QUERY = "Who invented Cobalt?"
    HOP2_QUERY = "Mira Vale born"
    HOP1_URL = "https://example.com/cobalt-inventor"
    HOP2_URL = "https://example.com/mira-vale-birth"

    def _partial_fake(self, calls, hop2_mode):
        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.HOP1_QUERY:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": self.HOP1_URL,
                            "extract": "Mira Vale invented Cobalt.",
                        }
                    ],
                }
            if query == self.HOP2_QUERY:
                if hop2_mode == "empty":
                    return {"ok": True, "results": []}
                if hop2_mode == "http_error":
                    return {"ok": False, "error": {"code": "HTTP_ERROR"}}
            return {"ok": True, "results": []}

        return fake

    def test_legacy_two_hop_partial_on_second_hop_failure(self):
        # Automatic legacy two-hop with research omitted: hop1 completes
        # grounded, hop2 empty or HTTP_ERROR. Existing task mandates partial
        # metadata surviving normalization, so legacy two-hop must too.
        for hop2_mode, expected_code in (
            ("empty", "INSUFFICIENT_EVIDENCE"),
            ("http_error", "HTTP_ERROR"),
        ):
            with self.subTest(hop2_mode=hop2_mode):
                calls = []
                _, tools = self.load_tools(self._partial_fake(calls, hop2_mode))
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {"query": self.COBALT_QUESTION}
                    )
                )
                self.assertIs(payload.get("ok"), False, payload)
                self.assertNotIn("answer", payload, payload)
                self.assertNotIn("sources", payload, payload)
                self.assertEqual(
                    payload.get("error", {}).get("code"),
                    expected_code,
                    payload,
                )
                research = payload.get("metadata", {}).get("research", {})
                self.assertEqual(research.get("status"), "partial", payload)
                self.assertEqual(research.get("search_calls"), 2, payload)
                intermediate = research.get("intermediate_evidence", [])
                inter_urls = [
                    item.get("url") if isinstance(item, dict) else item
                    for item in intermediate
                ]
                self.assertIn(self.HOP1_URL, inter_urls, payload)
                # No guessed final.
                blob = json.dumps(payload)
                self.assertNotIn("Arbor", blob, payload)

    def test_legacy_two_hop_success_ignores_foreign_provenance(self):
        import re

        marker = "SECRET-PROVENANCE-MARKER-7f3a"
        cred = "https://user:secret@example.com/evil-provenance"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.HOP1_QUERY:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": self.HOP1_URL,
                            "extract": "Mira Vale invented Cobalt.",
                        }
                    ],
                }
            if query == self.HOP2_QUERY:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Mira Vale",
                            "url": self.HOP2_URL,
                            "extract": "Mira Vale was born in Arbor.",
                        }
                    ],
                    "source": "wikipedia",
                    "source_url": "https://en.wikipedia.org/w/api.php",
                    "transitions": [
                        {"from": "hop2", "to": "final", "reason": marker + " " + cred}
                    ],
                    "metadata": {"evil": marker, "credential": cred},
                    "provenance": {"evil": marker, "url": cred},
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": self.COBALT_QUESTION})
        )
        self.assertTrue(payload.get("ok"), payload)
        answer = payload.get("answer", "")
        self.assertIn("Mira Vale was born in Arbor.", answer, payload)
        self.assertIn("[1]", answer, payload)
        self.assertNotIn("[2]", answer, payload)
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertIs(type(sources[0].get("index")), int, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)
        self.assertEqual(sources[0].get("url"), self.HOP2_URL, payload)
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        self.assertEqual(cited, {1}, payload)
        # Known real default labels preserved when safe; no arbitrary
        # upstream metadata copied.
        self.assertEqual(payload.get("source"), "wikipedia", payload)
        self.assertEqual(
            payload.get("source_url"), "https://en.wikipedia.org/w/api.php", payload
        )
        blob = json.dumps(payload)
        self.assertNotIn(marker, blob, payload)
        self.assertNotIn("SECRET-PROVENANCE", blob, payload)
        self.assertNotIn("user:secret", blob, payload)
        self.assertNotIn("secret@example", blob, payload)
        self.assertNotIn("Traceback", blob, payload)
        self.assertNotIn("evil", blob.casefold(), payload)


class LegacyCandidateReceiptTests(OfflineTestCase, FixtureMixin):
    """TELEMETRY ONLY: actual candidate receipt counts for legacy 2-hop.

    Automatic legacy path (research omitted). Engine knows actual counts,
    so it must report exact 2/1 (or capped 6), never false 0. No
    retrieval/planning/answer/evidence change: calls, answer, sources,
    status pinned unchanged.
    """

    COBALT_QUESTION = "Where was the inventor of Cobalt born?"
    HOP1_QUERY = "Who invented Cobalt?"
    HOP2_QUERY = "Mira Vale born"
    HOP1_URL = "https://example.com/cobalt-inventor"
    HOP2_URL = "https://example.com/mira-vale-birth"

    def _two_hop_fake(self, calls, hop1_results, hop2_results):
        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            if query == self.HOP1_QUERY:
                return {"ok": True, "results": list(hop1_results)}
            if query == self.HOP2_QUERY:
                return {"ok": True, "results": list(hop2_results)}
            return {"ok": True, "results": []}

        return fake

    def test_legacy_success_candidates_exact_two(self):
        hop1 = [
            {
                "title": "Cobalt",
                "url": self.HOP1_URL,
                "extract": "Mira Vale invented Cobalt.",
            }
        ]
        hop2 = [
            {
                "title": "Mira Vale",
                "url": self.HOP2_URL,
                "extract": "Mira Vale was born in Arbor.",
            }
        ]
        calls = []
        _, tools = self.load_tools(self._two_hop_fake(calls, hop1, hop2))
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": self.COBALT_QUESTION})
        )
        # Existing behavior unchanged (telemetry only).
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(len(calls), 2, payload)
        self.assertIn("Mira Vale was born in Arbor.", payload.get("answer", ""), payload)
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(sources[0].get("url"), self.HOP2_URL, payload)
        # Receipt: actual 2 candidates considered, never false 0.
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("search_calls"), 2, payload)
        got = research.get("candidates_considered", "MISSING")
        self.assertEqual(got, 2, payload)

    def test_legacy_partial_empty_second_candidates_exact_one(self):
        hop1 = [
            {
                "title": "Cobalt",
                "url": self.HOP1_URL,
                "extract": "Mira Vale invented Cobalt.",
            }
        ]
        hop2 = []
        calls = []
        _, tools = self.load_tools(self._two_hop_fake(calls, hop1, hop2))
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": self.COBALT_QUESTION})
        )
        # Existing partial contract unchanged.
        self.assertEqual(len(calls), 2, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        self.assertEqual(
            payload.get("error", {}).get("code"), "INSUFFICIENT_EVIDENCE", payload
        )
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "partial", payload)
        self.assertEqual(research.get("search_calls"), 2, payload)
        # Receipt: first 1 actual candidate, second empty => EXACT 1.
        got = research.get("candidates_considered", "MISSING")
        self.assertEqual(got, 1, payload)

    def test_legacy_overproduce_capped_six_not_raw_seven(self):
        # First hop overproduces 6 same-actor candidates; per-call prefix
        # bound <=5 before URL filter, so actual = 5 + second 1 = 6,
        # not raw 7. Never false 0.
        hop1 = [
            {
                "title": "Cobalt",
                "url": "https://example.com/cobalt-inventor-%d" % i,
                "extract": "Mira Vale invented Cobalt.",
            }
            for i in range(6)
        ]
        hop2 = [
            {
                "title": "Mira Vale",
                "url": self.HOP2_URL,
                "extract": "Mira Vale was born in Arbor.",
            }
        ]
        calls = []
        _, tools = self.load_tools(self._two_hop_fake(calls, hop1, hop2))
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": self.COBALT_QUESTION})
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertEqual(len(calls), 2, payload)
        research = payload.get("metadata", {}).get("research", {})
        # Per-call bound still <=5, total bound <=40.
        per_call = research.get(
            "max_candidates_per_call", research.get("candidates_per_call", 5)
        )
        total = research.get(
            "max_candidates_total", research.get("candidates_total", 40)
        )
        self.assertLessEqual(int(per_call), 5, payload)
        self.assertLessEqual(int(total), 40, payload)
        # Actual capped count 6, not raw 7, not false 0.
        got = research.get("candidates_considered", "MISSING")
        self.assertEqual(got, 6, payload)
        self.assertNotEqual(got, 7, payload)
        self.assertNotEqual(got, 0, payload)


class FinalGroundingAndCitationTests(OfflineTestCase, FixtureMixin):
    """Final adversarial grounding + citation tracer (TEST-ONLY, RED expected).

    Real BUILT bundle register+JSON; only search-callable boundary faked.
    No production/schema edits. Existing positives must stay green.
    """

    WHEN_DIRECT = "When was Mira Vale born?"
    WHERE_DIRECT = "Where was Mira Vale born?"
    BIRTH_URL = "https://example.com/mira-vale-birth"

    def _direct_fake(self, calls, body):
        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            self.assertLessEqual(len(query), 2000, (query,))
            low = query.casefold()
            if "mira vale" in low and "born" in low:
                return {
                    "ok": True,
                    "results": [
                        {"title": "Mira Vale", "url": self.BIRTH_URL, "extract": body}
                    ],
                }
            return {"ok": True, "results": []}

        return fake

    def test_direct_when_positive(self):
        calls = []
        _, tools = self.load_tools(
            self._direct_fake(calls, "Mira Vale was born in 1984.")
        )
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.WHEN_DIRECT,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn("Mira Vale was born in 1984.", payload.get("answer", ""), payload)
        self.assertIn("[1]", payload.get("answer", ""), payload)
        self.assertNotIn("[2]", payload.get("answer", ""), payload)
        sources = payload.get("sources")
        self.assertIsInstance(sources, list, payload)
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(sources[0].get("url"), self.BIRTH_URL, payload)
        self.assertIs(type(sources[0].get("index")), int, payload)
        self.assertEqual(sources[0].get("index"), 1, payload)

    def test_direct_where_positive(self):
        calls = []
        _, tools = self.load_tools(
            self._direct_fake(calls, "Mira Vale was born in Arbor.")
        )
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.WHERE_DIRECT,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertTrue(payload.get("ok"), payload)
        self.assertIn("Mira Vale was born in Arbor.", payload.get("answer", ""), payload)
        self.assertIn("[1]", payload.get("answer", ""), payload)
        sources = payload.get("sources")
        self.assertEqual(len(sources), 1, payload)
        self.assertEqual(sources[0].get("url"), self.BIRTH_URL, payload)

    def test_direct_misbound_subject_must_abstain(self):
        for query, body in (
            (self.WHEN_DIRECT, "Mira Vale met Nera Voss who was born in 1984."),
            (self.WHERE_DIRECT, "Mira Vale met Nera Voss who was born in Arbor."),
        ):
            with self.subTest(query=query, body=body):
                calls = []
                _, tools = self.load_tools(self._direct_fake(calls, body))
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {
                            "query": query,
                            "research": True,
                            "max_hops": 2,
                            "max_searches": 4,
                        }
                    )
                )
                self.assertIs(payload.get("ok"), False, payload)
                self.assertNotIn("answer", payload, payload)
                self.assertNotIn("sources", payload, payload)
                research = payload.get("metadata", {}).get("research", {})
                self.assertEqual(research.get("status"), "abstained", payload)

    def test_direct_where_must_not_answer_date_with_visiting_place(self):
        calls = []
        _, tools = self.load_tools(
            self._direct_fake(calls, "Mira Vale was born in 1984 before visiting Arbor.")
        )
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.WHERE_DIRECT,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "abstained", payload)
        blob = json.dumps(payload)
        self.assertNotIn("visiting Arbor", blob, payload)

    def test_direct_negative_modal_conflicting_still_no_answer(self):
        for body in (
            "Mira Vale was not born in 1984.",
            "Mira Vale may have been born in 1984.",
            "Mira Vale perhaps was born in Arbor.",
            "Mira Vale was born in 1984.",
        ):
            with self.subTest(body=body):
                pass
        for body in (
            "Mira Vale was not born in 1984.",
            "Mira Vale may have been born in 1984.",
            "Mira Vale perhaps was born in Arbor.",
        ):
            with self.subTest(body=body):
                calls = []
                _, tools = self.load_tools(self._direct_fake(calls, body))
                query = self.WHERE_DIRECT if "Arbor" in body else self.WHEN_DIRECT
                payload = json.loads(
                    tools["goat_answer"]["handler"](
                        {
                            "query": query,
                            "research": True,
                            "max_hops": 2,
                            "max_searches": 4,
                        }
                    )
                )
                self.assertIs(payload.get("ok"), False, payload)
                self.assertNotIn("answer", payload, payload)

    def test_direct_conflicting_full_dates_same_year_abstains(self):
        hop2 = [
            {
                "title": "Mira Vale",
                "url": self.BIRTH_URL,
                "extract": "Mira Vale was born on 1 January 1984.",
            },
            {
                "title": "Mira Vale",
                "url": "https://example.com/mira-vale-birth-2",
                "extract": "Mira Vale was born on 2 February 1984.",
            },
        ]
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            low = query.casefold()
            if "mira vale" in low and "born" in low:
                return {"ok": True, "results": list(hop2)}
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {
                    "query": self.WHEN_DIRECT,
                    "research": True,
                    "max_hops": 2,
                    "max_searches": 4,
                }
            )
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        blob = json.dumps(payload)
        self.assertNotIn("1 January", blob, payload)
        self.assertNotIn("2 February", blob, payload)

    def test_singlehop_normal_positive_control(self):
        url_a = "https://example.com/solara-a"
        url_b = "https://example.com/solara-b"
        body_a = "Solara produces energy."
        body_b = "Solara contains energy."
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            self.assertLessEqual(len(query), 2000, query)
            return {
                "ok": True,
                "results": [
                    {"title": "Solara A", "url": url_a, "extract": body_a},
                    {"title": "Solara B", "url": url_b, "extract": body_b},
                ],
            }

        _, tools = self.load_tools(fake)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "Solara energy"}))
        self.assertTrue(payload.get("ok"), payload)
        answer = payload.get("answer", "")
        self.assertIn(body_a, answer, payload)
        self.assertIn(body_b, answer, payload)
        import re as _re

        cited = {int(n) for n in _re.findall(r"\[(\d+)\]", answer)}
        sources = payload.get("sources", [])
        self.assertEqual(cited, {s.get("index") for s in sources}, payload)
        by_index = {s.get("index"): s.get("url") for s in sources}
        by_url = {url_a: body_a, url_b: body_b}
        for line in answer.split("\n"):
            m = _re.search(r"^(.*)\s+((?:\[\d+\])+)\s*$", line.strip())
            self.assertIsNotNone(m, (line, payload))
            text = m.group(1).strip()
            markers = {int(n) for n in _re.findall(r"\[(\d+)\]", m.group(2))}
            self.assertEqual(len(markers), 1, (line, payload))
            idx = next(iter(markers))
            url = by_index.get(idx)
            self.assertIsNotNone(url, (line, payload))
            self.assertEqual(text, by_url.get(url), (line, payload, text, url))

    def test_singlehop_bracket_marker_must_abstain(self):
        import re as _re

        url_a = "https://example.com/solara-a"
        url_b = "https://example.com/solara-b"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            return {
                "ok": True,
                "results": [
                    {
                        "title": "Solara A",
                        "url": url_a,
                        "extract": "Solara produces energy [2].",
                    },
                    {"title": "Solara B", "url": url_b, "extract": "Solara contains energy."},
                ],
            }

        _, tools = self.load_tools(fake)
        payload = json.loads(tools["goat_answer"]["handler"]({"query": "Solara energy"}))
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        blob = json.dumps(payload)
        self.assertNotIn("Solara produces energy", blob, payload)
        self.assertNotIn("[2]", blob, payload)

    def test_two_hop_bracket_marker_must_not_leak(self):
        import re as _re

        hop1_q = "Who invented Cobalt?"
        hop1_url = "https://example.com/cobalt-inventor"
        hop2_url = "https://example.com/mira-vale-birth"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            self.assertLessEqual(len(query), 2000, query)
            if query == hop1_q:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": hop1_url,
                            "extract": "Mira Vale invented Cobalt.",
                        }
                    ],
                }
            low = query.casefold()
            if "mira vale" in low and "born" in low:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Mira Vale",
                            "url": hop2_url,
                            "extract": "Mira Vale was born in Arbor [2].",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": "Where was the inventor of Cobalt born?"})
        )
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        blob = json.dumps(payload)
        self.assertNotIn("[2]", blob, payload)
        self.assertNotIn("was born in Arbor", blob, payload)

    def test_legacy_bridge_overlong_no_second_transport(self):
        long_actor = "A" + "a" * 599
        hop1_q = "Who invented Cobalt?"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            self.assertLessEqual(len(query), 2000, (len(query), query[:80]))
            if query == hop1_q:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": "https://example.com/cobalt-inventor",
                            "extract": "%s invented Cobalt." % long_actor,
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": "Where was the inventor of Cobalt born?"})
        )
        self.assertEqual(len(calls), 1, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        blob = json.dumps(payload)
        self.assertNotIn(long_actor[:50], blob, payload)
        self.assertNotIn("Traceback", blob, payload)
        self.assertNotIn("Exception", blob, payload)

    def test_legacy_bridge_userinfo_no_copy_no_second_transport(self):
        hop1_q = "Who invented Cobalt?"
        cred_url = "https://user:secret@example.com/evil"
        calls = []

        def fake(query, *, max_results=5):
            calls.append((query, max_results))
            self.assertLessEqual(len(query), 2000, query)
            if query == hop1_q:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": cred_url,
                            "extract": "Mira Vale invented Cobalt.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": "Where was the inventor of Cobalt born?"})
        )
        self.assertEqual(len(calls), 1, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        blob = json.dumps(payload)
        self.assertNotIn("user:secret", blob, payload)
        self.assertNotIn("secret@example", blob, payload)
        self.assertNotIn("Traceback", blob, payload)
        self.assertNotIn("Exception", blob, payload)
        research = payload.get("metadata", {}).get("research", {})
        intermediate = research.get("intermediate_evidence", [])
        for item in intermediate:
            self.assertNotIn("exception", json.dumps(item).casefold(), payload)
            if isinstance(item, dict):
                self.assertNotIn("exception", [k.casefold() for k in item.keys()], payload)

    def test_legacy_bridge_conjunction_guard_normal_unaffected(self):
        hop1_q = "Who invented Cobalt?"
        calls = []

        def fake_conj(query, *, max_results=5):
            calls.append((query, max_results))
            if query == hop1_q:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": "https://example.com/cobalt-inventor",
                            "extract": "Mira and Nera invented Cobalt.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake_conj)
        payload = json.loads(
            tools["goat_answer"]["handler"]({"query": "Where was the inventor of Cobalt born?"})
        )
        self.assertEqual(len(calls), 1, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        calls2 = []

        def fake_ok(query, *, max_results=5):
            calls2.append((query, max_results))
            if query == hop1_q:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Cobalt",
                            "url": "https://example.com/cobalt-inventor",
                            "extract": "Mira Vale invented Cobalt.",
                        }
                    ],
                }
            low = query.casefold()
            if "mira vale" in low and "born" in low:
                return {
                    "ok": True,
                    "results": [
                        {
                            "title": "Mira Vale",
                            "url": "https://example.com/mira-vale-birth",
                            "extract": "Mira Vale was born in Arbor.",
                        }
                    ],
                }
            return {"ok": True, "results": []}

        _, tools2 = self.load_tools(fake_ok)
        payload2 = json.loads(
            tools2["goat_answer"]["handler"](
                {"query": "Where was the inventor of Cobalt born?"}
            )
        )
        self.assertTrue(payload2.get("ok"), payload2)
        self.assertIn("Mira Vale was born in Arbor.", payload2.get("answer", ""), payload2)


class TraceDepthTests(OfflineTestCase, FixtureMixin):
    """REAL 4-facet-of-2-step plan (8 steps, depth 2) then terminal fails."""

    FACET_SUBJECTS = ("Cobalt", "Briar", "Ferro", "Greso")
    ACTORS = {
        "Cobalt": "Mira Vale",
        "Briar": "Nera Voss",
        "Ferro": "Tessa Hale",
        "Greso": "Liora Hale",
    }

    def _facet_query(self):
        return "; ".join(
            "When was the inventor of %s born?" % s for s in self.FACET_SUBJECTS
        )

    def _plan_via_bundle(self, module):
        vendor = module.v3_wiring._vendor_answer
        plan_fn = getattr(vendor, "plan_research_query", None)
        self.assertTrue(callable(plan_fn))
        plan = plan_fn(self._facet_query(), max_hops=2, max_searches=8)
        return plan, vendor

    def test_real_facet_plan_shape_eight_steps_depth_two(self):
        module = self.load_module()
        plan, vendor = self._plan_via_bundle(module)
        self.assertEqual(plan.get("status"), "planned", plan)
        self.assertEqual(plan.get("chain_kind"), "facets", plan)
        steps = plan.get("steps")
        self.assertIsInstance(steps, list, plan)
        self.assertEqual(len(steps), 8, plan)
        self.assertEqual([s.get("id") for s in steps], ["s%d" % i for i in range(1, 9)], plan)
        for s in steps:
            self.assertLessEqual(s.get("index", 0) if "index" in s else 0, 8, plan)
            self.assertLessEqual(s.get("depth"), 2, plan)
        self.assertEqual(
            [s.get("depth") for s in steps], [1, 2, 1, 2, 1, 2, 1, 2], plan
        )
        for s in steps:
            self.assertLessEqual(len(s.get("query_template", "")), 2000, plan)
            self.assertLessEqual(len(s.get("grounding_template", "")), 2000, plan)
        validate = getattr(vendor, "validate_research_plan", None)
        self.assertTrue(callable(validate))
        self.assertIs(validate(plan), True, plan)
        self.assertIs(validate(plan, max_hops=2, max_searches=8), True, plan)

    def test_terminal_step8_failure_partial_survives_with_depth_trace(self):
        import re as _re

        query = self._facet_query()
        module = self.load_module()
        plan, _vendor = self._plan_via_bundle(module)
        self.assertEqual(len(plan.get("steps", [])), 8, plan)
        expected_depth = [s.get("depth") for s in plan.get("steps")]
        expected_depends = [list(s.get("depends_on", [])) for s in plan.get("steps")]
        expected_ids = [s.get("id") for s in plan.get("steps")]
        calls = []
        actors = dict(self.ACTORS)

        def fake(query_text, *, max_results=5):
            calls.append((query_text, max_results))
            self.assertLessEqual(len(query_text), 2000, query_text)
            self.assertLessEqual(max_results, 5, (query_text, max_results))
            for subj, actor in actors.items():
                if query_text == "Who invented %s?" % subj:
                    return {
                        "ok": True,
                        "results": [
                            {
                                "title": subj,
                                "url": "https://example.com/%s-inventor" % subj.casefold(),
                                "extract": "%s invented %s." % (actor, subj),
                            }
                        ],
                    }
            low = query_text.casefold()
            for subj, actor in actors.items():
                if actor.casefold() in low and "born" in low:
                    if subj == "Greso":
                        return {"ok": True, "results": []}
                    return {
                        "ok": True,
                        "results": [
                            {
                                "title": actor,
                                "url": "https://example.com/%s-birth" % actor.split()[0].casefold(),
                                "extract": "%s was born in 1984." % actor,
                            }
                        ],
                    }
            return {"ok": True, "results": []}

        _, tools = self.load_tools(fake)
        payload = json.loads(
            tools["goat_answer"]["handler"](
                {"query": query, "research": True, "max_hops": 2, "max_searches": 8}
            )
        )
        self.assertEqual(len(calls), 8, payload)
        self.assertLessEqual(len(calls), 8, payload)
        self.assertIs(payload.get("ok"), False, payload)
        self.assertNotIn("answer", payload, payload)
        self.assertNotIn("sources", payload, payload)
        blob = json.dumps(payload)
        self.assertNotIn("Traceback", blob, payload)
        self.assertNotIn("Exception", blob, payload)
        self.assertNotIn("was born in", blob, payload)
        self.assertNotIn("extract", blob.casefold(), payload)
        self.assertNotIn("snippet", blob.casefold(), payload)
        research = payload.get("metadata", {}).get("research", {})
        self.assertEqual(research.get("status"), "partial", payload)
        self.assertEqual(research.get("planned"), 8, payload)
        self.assertEqual(research.get("executed"), 7, payload)
        self.assertEqual(research.get("search_calls"), 8, payload)
        self.assertLessEqual(int(research.get("search_calls", 0)), 8, payload)
        self.assertLessEqual(int(research.get("max_candidates_per_call", 5)), 5, payload)
        self.assertLessEqual(int(research.get("max_candidates_total", 40)), 40, payload)
        # Actual candidate count on failure is 7 (7 single candidates + empty
        # last), not default 0.
        self.assertEqual(research.get("candidates_considered"), 7, payload)
        hops = payload.get("metadata", {}).get("hops", payload.get("hops"))
        self.assertIsInstance(hops, list, payload)
        self.assertEqual(len(hops), 8, payload)
        for h in hops:
            self.assertLessEqual(int(h.get("index")), 8, payload)
            self.assertLessEqual(int(h.get("depth")), 2, payload)
        self.assertEqual([h.get("depth") for h in hops], expected_depth, payload)
        self.assertEqual([h.get("id") for h in hops], expected_ids, payload)
        for h, deps in zip(hops, expected_depends):
            self.assertIn("depends_on", h, (h, payload))
            self.assertEqual(list(h.get("depends_on", [])), deps, (h, payload))
        self.assertEqual(hops[-1].get("status"), "failed", payload)
        self.assertNotEqual(hops[-1].get("code"), "COMPLETED", payload)
        for h in hops[:-1]:
            self.assertEqual(h.get("status"), "completed", payload)
            self.assertEqual(h.get("code"), "COMPLETED", payload)
        for h in hops:
            url = h.get("url", None)
            if url is not None:
                self.assertTrue(url.startswith("https://example.com/"), (h, payload))
                self.assertNotIn("user:secret", url, payload)
                self.assertNotIn("@", url, payload)
        # Actual safe URLs of ALL 7 successful hops retained per-hop even
        # though intermediate-summary caps at 5; do not derive full hop URL
        # provenance from the capped summary and do not lose hop6/7 URLs.
        expected_urls = [
            "https://example.com/cobalt-inventor",
            "https://example.com/mira-birth",
            "https://example.com/briar-inventor",
            "https://example.com/nera-birth",
            "https://example.com/ferro-inventor",
            "https://example.com/tessa-birth",
            "https://example.com/greso-inventor",
        ]
        for h, exp_url in zip(hops[:7], expected_urls):
            self.assertEqual(h.get("url"), exp_url, (h, payload))
        self.assertNotIn("url", hops[7], payload)
        intermediate = research.get("intermediate_evidence", [])
        self.assertLessEqual(len(intermediate), 5, payload)

    def test_unsupported_and_prebudget_zero_calls_empty_trace(self):
        # Unsupported / pre-budget abort with 0 search calls must have EMPTY
        # actual execution hops, no phantom failed s1.
        for query, budgets in (
            ("Which of those was earlier?", {"max_hops": 2, "max_searches": 4}),
            (
                "Who designed the capital of the body orbited by Runa?",
                {"max_hops": 2, "max_searches": 4},
            ),
        ):
            with self.subTest(query=query, budgets=budgets):
                calls = []

                def fake(query_text, *, max_results=5):
                    calls.append((query_text, max_results))
                    return {"ok": True, "results": []}

                _, tools = self.load_tools(fake)
                args = {"query": query, "research": True}
                args.update(budgets)
                payload = json.loads(tools["goat_answer"]["handler"](args))
                self.assertEqual(calls, [], payload)
                self.assertIs(payload.get("ok"), False, payload)
                self.assertNotIn("answer", payload, payload)
                self.assertNotIn("sources", payload, payload)
                research = payload.get("metadata", {}).get("research", {})
                self.assertEqual(research.get("search_calls"), 0, payload)
                self.assertEqual(research.get("executed"), 0, payload)
                hops = payload.get("metadata", {}).get("hops", payload.get("hops", []))
                self.assertIsInstance(hops, list, payload)
                self.assertEqual(hops, [], payload)


# TESTS_ONLY_EXECUTION_READY
# TESTS_ONLY_BOUNDS_READY
# TESTS_ONLY_FINAL_ANCHORS_READY
if __name__ == "__main__":
    unittest.main()
