"""P3 bool regression: max_results=True must fail closed URL_BLOCKED."""
import importlib.util
import socket
import sys
import types
import unittest
from pathlib import Path

# offline guard ---------------------------------------------------------------
_attempts = []
_orig_getaddrinfo = socket.getaddrinfo
_orig_gethostbyname = socket.gethostbyname
_orig_create = socket.create_connection
_orig_connect = socket.socket.connect


def _blocked(*a, **kw):
    _attempts.append("blocked")
    raise AssertionError("offline forbids network")


ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_DIR = ROOT / "goat-web" / "plugins" / "goat-web"
ADAPTERS_DIR = ROOT / "adapters"
WIRING_PATH = PLUGIN_DIR / "v3_wiring.py"

_PKG_NAME = "p3_bool_pkg"
_VENDOR_NAME = _PKG_NAME + "._goat_v3_vendor"
_WIRING_FULL = _PKG_NAME + ".v3_wiring"
_mod = None


def _load_mod():
    """Load real v3_wiring with real adapters as vendored package (no bundle)."""
    global _mod
    if _mod is not None:
        return _mod
    if _PKG_NAME not in sys.modules:
        pkg = types.ModuleType(_PKG_NAME)
        pkg.__path__ = [str(PLUGIN_DIR)]
        sys.modules[_PKG_NAME] = pkg
    if _VENDOR_NAME not in sys.modules:
        vendor_pkg = types.ModuleType(_VENDOR_NAME)
        vendor_pkg.__path__ = [str(ADAPTERS_DIR)]
        sys.modules[_VENDOR_NAME] = vendor_pkg
    for stem in (
        "result_contract",
        "ddg_parser",
        "ssrf_guard",
        "answer_synth",
        "search_filters",
        "free_stack",
        "free_verticals",
    ):
        full = _VENDOR_NAME + "." + stem
        if full not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                full, ADAPTERS_DIR / (stem + ".py")
            )
            if spec is None or spec.loader is None:
                raise AssertionError("could not load vendor %s" % stem)
            module = importlib.util.module_from_spec(spec)
            sys.modules[full] = module
            spec.loader.exec_module(module)
    if _WIRING_FULL not in sys.modules:
        spec = importlib.util.spec_from_file_location(_WIRING_FULL, WIRING_PATH)
        if spec is None or spec.loader is None:
            raise AssertionError("could not load v3_wiring by file spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_WIRING_FULL] = module
        spec.loader.exec_module(module)
    _mod = sys.modules[_WIRING_FULL]
    return _mod


def _fake_search(query, *, max_results=5):
    return {
        "ok": True,
        "results": [
            {"title": "T%d" % i, "url": "https://example.com/%d" % i, "snippet": "s"}
            for i in range(5)
        ],
    }


def _fake_transport(url):
    return {"status": 200, "body": b"{}"}


def _stub_vertical_register(mod):
    """Isolate wiring layer: fake vertical ops succeed regardless of limit.

    The real free_verticals backend already rejects bool via
    type(value) is not int, which would mask the wiring-layer flaw
    (missing type check in _make_vertical_operation). Stubbing register()
    proves wiring forwards bool instead of fail-closing itself.
    """
    original = mod._vendor_verticals.register

    def _ok_op(query, transport=None, *, limit=5, provider_config=None):
        return {
            "ok": True,
            "results": [{"title": "S", "url": "https://example.com/s"}],
            "truncated": False,
        }

    mod._vendor_verticals.register = lambda: {
        "goat_scholar": _ok_op,
        "goat_news": _ok_op,
        "goat_images": _ok_op,
    }
    return original


class P3BoolTests(unittest.TestCase):
    def setUp(self):
        self._g = socket.getaddrinfo
        self._h = socket.gethostbyname
        self._c = socket.create_connection
        self._co = socket.socket.connect
        socket.getaddrinfo = _blocked
        socket.gethostbyname = _blocked
        socket.create_connection = _blocked
        socket.socket.connect = _blocked
        _attempts.clear()
        self.addCleanup(setattr, socket, "getaddrinfo", self._g)
        self.addCleanup(setattr, socket, "gethostbyname", self._h)
        self.addCleanup(setattr, socket, "create_connection", self._c)
        self.addCleanup(setattr, socket.socket, "connect", self._co)

    def tearDown(self):
        socket.getaddrinfo = self._g
        socket.gethostbyname = self._h
        socket.create_connection = self._c
        socket.socket.connect = self._co

    def _deps(self, mod):
        return mod.WiringDependencies(
            search=_fake_search,
            vertical_transports={
                "scholar": _fake_transport,
                "news": _fake_transport,
                "images": _fake_transport,
            },
        )

    def test_filtered_bool_true_is_url_blocked(self):
        mod = _load_mod()
        h = mod.make_handlers(self._deps(mod))
        out = h["goat_filtered_search"]("test query", max_results=True)
        self.assertEqual(out, {"ok": False, "error": {"code": "URL_BLOCKED"}})
        self.assertEqual(_attempts, [])

    def test_vertical_bool_true_is_url_blocked(self):
        mod = _load_mod()
        original = _stub_vertical_register(mod)
        self.addCleanup(setattr, mod._vendor_verticals, "register", original)
        h = mod.make_handlers(self._deps(mod))
        out = h["goat_vertical_search"]("scholar", "test query", max_results=True)
        self.assertEqual(out, {"ok": False, "error": {"code": "URL_BLOCKED"}})
        self.assertEqual(_attempts, [])

    def test_filtered_bool_false_is_url_blocked(self):
        mod = _load_mod()
        h = mod.make_handlers(self._deps(mod))
        out = h["goat_filtered_search"]("test query", max_results=False)
        self.assertEqual(out, {"ok": False, "error": {"code": "URL_BLOCKED"}})
        self.assertEqual(_attempts, [])

    def test_vertical_bool_false_is_url_blocked(self):
        mod = _load_mod()
        original = _stub_vertical_register(mod)
        self.addCleanup(setattr, mod._vendor_verticals, "register", original)
        h = mod.make_handlers(self._deps(mod))
        out = h["goat_vertical_search"]("scholar", "test query", max_results=False)
        self.assertEqual(out, {"ok": False, "error": {"code": "URL_BLOCKED"}})
        self.assertEqual(_attempts, [])

    def test_filtered_nan_is_url_blocked(self):
        mod = _load_mod()
        h = mod.make_handlers(self._deps(mod))
        out = h["goat_filtered_search"]("test query", max_results=float("nan"))
        self.assertEqual(out, {"ok": False, "error": {"code": "URL_BLOCKED"}})
        self.assertEqual(_attempts, [])


if __name__ == "__main__":
    unittest.main()
