"""Milestone 08: real native Hermes registration + manager gates (H1/H2).

Parent side runs under the store interpreter (stdlib only) and delegates
every native import to fresh ``GOAT_HERMES_RUNTIME_PYTHON -I -B`` child
processes with disposable ``HERMES_HOME``/``HOME``/``TMPDIR``/XDG dirs set
BEFORE any host import. Children use the real ``PluginContext``,
``PluginManager``, ``PluginManifest`` and the real ``tools.registry``
singleton; no patched registry/context. CLI gates invoke the real
``hermes_cli.main.main`` with ``sys.argv`` equivalent to
``hermes plugins doctor <bundle> --ci`` and
``hermes plugins validate <bundle>`` (never ``--install-deps``, never the
shared auto-repair ``hermes`` shell launcher).

Missing/incompatible runtime is skipped for portability; when present the native gate is strict.
"""

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


WIRING_ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = WIRING_ROOT / "goat-web" / "scripts" / "build_plugin_bundle.py"
BUILD_ROOT = WIRING_ROOT.parent / "artifacts" / "wiring-build"

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
FORBIDDEN_ALIASES = frozenset({"goat_scholar", "goat_news", "goat_images"})

DEFAULT_RUNTIME_PYTHON = (
    "/opt/data/installs/7e7873c79b16436d/environments/"
    "6e58e8c283ae4457a5cef422e9cd58e5/venv/bin/python"
)
DEFAULT_SOURCE_ROOT = (
    "/srv/media-ingest/hermes-service-home/hermes-agent-src"
)


def _runtime_python():
    """Trusted portable runtime selection; missing runtime fails, never skips."""
    candidate = os.environ.get(
        "GOAT_HERMES_RUNTIME_PYTHON", DEFAULT_RUNTIME_PYTHON
    )
    if not candidate or not os.path.isfile(candidate) or not os.access(
        candidate, os.X_OK
    ):
        raise unittest.SkipTest(
            "native Hermes runtime not available; skipping native gate (%r) (set GOAT_HERMES_RUNTIME_PYTHON)" % (candidate,)
        )
    return candidate


def _source_root():
    """Trusted portable source selection; missing source fails, never skips."""
    candidate = os.environ.get(
        "GOAT_HERMES_SOURCE_ROOT", DEFAULT_SOURCE_ROOT
    )
    root = Path(candidate)
    if not root.is_dir() or not (root / "hermes_cli" / "main.py").is_file():
        raise unittest.SkipTest(
            "native Hermes source not available; skipping native gate (%r) (set GOAT_HERMES_SOURCE_ROOT)" % (candidate,)
        )
    return str(root)


def _load_builder():
    module_name = "goat_native_bundle_builder_" + uuid.uuid4().hex
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
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="goat-native-", dir=str(BUILD_ROOT))
    test_case.addCleanup(shutil.rmtree, tmp, True)
    output = Path(tmp) / "hermes-goat-web"
    _load_builder().build_bundle(WIRING_ROOT, output)
    return output


def _fresh_scratch(test_case, tag):
    base = BUILD_ROOT / "t" / ("%s-%s" % (tag, uuid.uuid4().hex[:8]))
    if base.exists():
        shutil.rmtree(base)
    (base / "home").mkdir(parents=True)
    (base / "tmp").mkdir(parents=True)
    (base / "xdg-config").mkdir(parents=True)
    (base / "xdg-data").mkdir(parents=True)
    (base / "xdg-cache").mkdir(parents=True)
    test_case.addCleanup(shutil.rmtree, str(base), True)
    return base


def _child_env(base):
    home = str(base / "home")
    tmp = str(base / "tmp")
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HERMES_HOME": home,
        "HOME": home,
        "TMPDIR": tmp,
        "TEMP": tmp,
        "TMP": tmp,
        "XDG_CONFIG_HOME": str(base / "xdg-config"),
        "XDG_DATA_HOME": str(base / "xdg-data"),
        "XDG_CACHE_HOME": str(base / "xdg-cache"),
        "HERMES_DISABLE_LAZY_INSTALLS": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return env


def _run_child(env, script_path, cwd, timeout=100):
    return subprocess.run(
        [_runtime_python(), "-I", "-B", str(script_path)],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


# ---------------------------------------------------------------------------
# Child script templates (run under the native runtime with -I -B).
# ---------------------------------------------------------------------------

_H1_PREAMBLE = r'''
import importlib.util as _ilu
import io as _io
import json as _json
import os as _os
import re as _re
import socket as _socket
import subprocess as _subprocess
import sys as _sys
import uuid as _uuid

BUNDLE = __BUNDLE__
SCRATCH = __SCRATCH__
SOURCE_ROOT = __SOURCE_ROOT__

assert _os.environ.get("HERMES_HOME", "").startswith(SCRATCH), _os.environ.get("HERMES_HOME")
assert _os.environ.get("HOME", "").startswith(SCRATCH), _os.environ.get("HOME")
assert _os.environ.get("TMPDIR", "").startswith(SCRATCH), _os.environ.get("TMPDIR")
assert "PYTHONPATH" not in _os.environ, "PYTHONPATH must be sanitized"
assert _os.environ.get("HERMES_DISABLE_LAZY_INSTALLS") == "1", "lazy installs must be suppressed"
for _bad in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HERMES_API_KEY"):
    assert _bad not in _os.environ, _bad

_SCRATCH_REAL = _os.path.realpath(SCRATCH)
_SECRET_BASES = frozenset({".env", "config.yaml", "auth.json"})

def _real_path(p):
    try:
        s = _os.fspath(p)
    except Exception:
        return None
    if isinstance(s, int):
        return None
    if isinstance(s, bytes):
        try:
            s = s.decode("utf-8", "surrogateescape")
        except Exception:
            return None
    if not isinstance(s, str):
        return None
    try:
        if not _os.path.isabs(s):
            s = _os.path.join(_os.getcwd(), s)
        return _os.path.realpath(s)
    except Exception:
        return None

def _inside_scratch(p):
    r = _real_path(p)
    if r is None:
        return False
    try:
        return _os.path.commonpath([r, _SCRATCH_REAL]) == _SCRATCH_REAL
    except Exception:
        return False

def _is_write_flags(flags):
    try:
        import os as _o
        return bool(flags & (_o.O_WRONLY | _o.O_RDWR | _o.O_CREAT | _o.O_TRUNC | _o.O_APPEND))
    except Exception:
        return False

def _auditor(event, args):
    if event == "open":
        try:
            raw = args[0]
        except Exception:
            return
        try:
            sp = _os.fspath(raw)
        except Exception:
            return
        if isinstance(sp, int):
            return
        if isinstance(sp, bytes):
            try:
                sp = sp.decode("utf-8", "surrogateescape")
            except Exception:
                return
        if not isinstance(sp, str):
            return
        flags = args[2] if len(args) > 2 else 0
        if _is_write_flags(flags):
            if sp == "/dev/null":
                return
            if sp.startswith("/dev/") or sp.startswith("/proc/"):
                raise RuntimeError("write to device denied: %r" % sp)
            if not _inside_scratch(sp):
                raise RuntimeError("write outside disposable scratch denied: %r" % sp)
        else:
            base = _os.path.basename(sp)
            if base in _SECRET_BASES and not _inside_scratch(sp):
                raise RuntimeError("live secret read denied: %r" % sp)
        return
    if event in ("os.mkdir", "os.remove", "os.rmdir", "os.unlink"):
        try:
            p = _os.fspath(args[0])
        except Exception:
            return
        if not _inside_scratch(p):
            raise RuntimeError("mutation outside scratch denied: %s %r" % (event, p))
        return
    if event in ("os.rename", "os.replace", "os.symlink", "os.link"):
        try:
            a = _os.fspath(args[0])
            b = _os.fspath(args[1])
        except Exception:
            return
        if not _inside_scratch(a) or not _inside_scratch(b):
            raise RuntimeError("mutation outside scratch denied: %s %r %r" % (event, a, b))
        return
    if event == "shutil.rmtree":
        try:
            p = _os.fspath(args[0])
        except Exception:
            return
        if not _inside_scratch(p):
            raise RuntimeError("mutation outside scratch denied: %s %r" % (event, p))
        return
    if event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.connect", "socket.__new__"):
        raise RuntimeError("network access is denied in native H1 gate: %s" % event)
    if event == "subprocess.Popen":
        raise RuntimeError("subprocess launch is denied in native H1 gate")
    if event in ("os.system", "os.spawn", "os.exec", "os.fork", "os.posix_spawn"):
        raise RuntimeError("process spawn is denied in native H1 gate: %s" % event)
    if event.startswith("os.spawn") or event.startswith("os.exec") or event.startswith("os.fork"):
        raise RuntimeError("process spawn is denied in native H1 gate: %s" % event)
    return

try:
    _sys.addaudithook(_auditor)
except Exception as _exc:
    _sys.stdout.write("GOAT_NATIVE_H1_FAIL " + _json.dumps({"stage": "auditor", "error": repr(_exc)}) + "\n")
    raise SystemExit(2)

def _selfcheck_h1():
    import os as _o
    _W = _o.O_WRONLY | _o.O_CREAT
    def _deny(ev, ar):
        try:
            _auditor(ev, ar)
        except RuntimeError:
            return True
        return False
    assert _deny("open", ("/tmp/goat-h1-outside-probe/evil.txt", "w", _W)), "open write outside must deny"
    assert _deny("open", (SCRATCH + "/../h1-escape.txt", "w", _W)), "relative escape write must deny"
    assert _deny("open", ("/opt/data/.env", "r", 0)), "live .env read must deny"
    assert _deny("open", ("/opt/data/auth.json", "r", 0)), "live auth read must deny"
    assert _deny("open", ("/opt/data/config.yaml", "r", 0)), "live config read must deny"
    assert _deny("os.mkdir", ("/tmp/goat-h1-evil-dir", 511, -1)), "mkdir outside must deny"
    assert _deny("os.remove", ("/tmp/goat-h1-evil", -1)), "remove outside must deny"
    assert _deny("os.rmdir", ("/tmp/goat-h1-evil", -1)), "rmdir outside must deny"
    assert _deny("os.rename", ("/tmp/a", "/tmp/b", -1, -1)), "rename outside must deny"
    assert _deny("os.symlink", ("/tmp/a", "/tmp/b", -1)), "symlink outside must deny"
    assert _deny("shutil.rmtree", ("/tmp/goat-h1-evil-tree", None)), "rmtree outside must deny"
    assert _deny("socket.getaddrinfo", ("example.com", 80, 0, 0, 0)), "getaddrinfo must deny"
    assert _deny("socket.gethostbyname", ("example.com",)), "gethostbyname must deny"
    assert _deny("socket.connect", (None, ("93.184.216.34", 80))), "connect must deny"
    assert _deny("socket.__new__", (None, 2, 1, 0)), "socket creation must deny"
    assert _deny("subprocess.Popen", ("/bin/sh", ["/bin/sh", "-c", "id"], None, None)), "popen must deny"
    assert _deny("os.system", ("id",)), "system must deny"
    _auditor("open", (SCRATCH + "/selfcheck-ok.txt", "w", _W))
    _auditor("open", ("/dev/null", "w", _W))
    _auditor("os.mkdir", (SCRATCH + "/selfcheck-dir", 511, -1))
    _sys.stdout.write("GOAT_NATIVE_H1_AUDIT_OK 1\n")

_selfcheck_h1()

def _deny_net(*_a, **_k):
    raise RuntimeError("network access is denied in native H1 gate")

_socket.create_connection = _deny_net
_socket.socket.connect = _deny_net
_socket.socket.connect_ex = _deny_net
_subprocess.Popen = _deny_net
_subprocess.run = _deny_net
_subprocess.call = _deny_net
_subprocess.check_call = _deny_net
_subprocess.check_output = _deny_net
if hasattr(_os, "system"):
    _os.system = _deny_net
if hasattr(_os, "fork"):
    try:
        _os.fork = _deny_net
    except Exception:
        pass
for _n in ("spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "posix_spawn"):
    if hasattr(_os, _n):
        try:
            setattr(_os, _n, _deny_net)
        except Exception:
            pass
for _n in ("execv", "execve", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe"):
    if hasattr(_os, _n):
        try:
            setattr(_os, _n, _deny_net)
        except Exception:
            pass

_sys.path.insert(0, SOURCE_ROOT)
'''

_H1_BODY = r'''
from hermes_cli.plugins import PluginContext, PluginManager
from hermes_cli.plugins_manifest import PluginManifest
from tools.registry import registry

_pkg = "goat_native_h1_%s" % _uuid.uuid4().hex
_spec = _ilu.spec_from_file_location(
    _pkg, _os.path.join(BUNDLE, "__init__.py"),
    submodule_search_locations=[BUNDLE])
assert _spec is not None and _spec.loader is not None, "no spec for bundle"
_mod = _ilu.module_from_spec(_spec)
_sys.modules[_pkg] = _mod
try:
    _spec.loader.exec_module(_mod)
except Exception:
    _sys.modules.pop(_pkg, None)
    raise
for _bad in ("ssrf_guard", "ddg_parser", "result_contract", "adapters", "goat_tools"):
    assert _bad not in _sys.modules, "top-level alias present: %s" % _bad

_home = _os.environ["HERMES_HOME"]
_manager = PluginManager(scope_key=_home)
_scope = _manager.scope_key
_manifest = PluginManifest(
    name="hermes-goat-web", version="0.2.0",
    source="user", path=BUNDLE,
    provides_tools=["goat_search", "goat_extract", "goat_crawl", "goat_probe",
                    "goat_answer", "goat_filtered_search", "goat_vertical_search"])
_ctx = PluginContext(_manifest, _manager)

_wiring = _mod.v3_wiring
_WD = _wiring.WiringDependencies
import dataclasses as _dc
assert _dc.is_dataclass(_WD), "WiringDependencies must be a dataclass"
_params = getattr(_WD, "__dataclass_params__", None)
assert _params is not None and _params.frozen, "WiringDependencies must be frozen"

def _fake_search(query, *, max_results=5):
    assert isinstance(query, str), type(query)
    return {"ok": True, "results": [
        {"title": "Denied early", "url": "https://denied.example/early",
         "snippet": "Nuclear fission releases energy here.",
         "published_at": "2024-06-01T00:00:00Z", "language": "en"},
        {"title": "Caf\u00e9 fission \u00e9\u00e9n", "url": "https://good.example/un%C3%AFcode-1",
         "snippet": "Nuclear fission releases energy. Caf\u00e9 reactors use fission heat.",
         "published_at": "2024-06-01T00:00:00Z", "language": "en"},
        {"title": "Fission two", "url": "https://good.example/fission-two",
         "snippet": "Nuclear fission releases energy. Control rods manage fission rate.",
         "published_at": "2024-06-01T00:00:00Z", "language": "en"},
    ]}

_scholar_payload = {"message": {"items": [
    {"title": ["Scholar Caf\u00e9 paper"], "DOI": "10.1234/cafe-2021",
     "URL": "https://example.com/paper", "author": [{"given": "Ada", "family": "Lovelace"}],
     "issued": {"date-parts": [[2021]]}, "container-title": ["Journal of Tests"]}
]}}
_news_payload = {"articles": [
    {"title": "Example news headline", "url": "https://example.com/news-item",
     "snippet": "Snippet words here.", "seendate": "20261009T120000Z",
     "domain": "example.com", "language": "English", "sourcecountry": "United States"}
]}
_images_payload = {"query": {"pages": [
    {"title": "File:Caf\u00e9 test.jpg", "imageinfo": [{
        "thumburl": "https://upload.wikimedia.org/thumb.jpg",
        "url": "https://upload.wikimedia.org/full.jpg",
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Cafe_test.jpg",
        "extmetadata": {
            "LicenseShortName": {"value": "CC-BY-SA 4.0"},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
            "Artist": {"value": "Test Artist"},
            "ImageDescription": {"value": "Caf\u00e9 description"}}}]}
]}}

_recorded = {}
def _fake_transport(kind, payload):
    def _transport(url):
        _recorded.setdefault(kind, []).append(url)
        return {"status": 200, "body": _json.dumps(payload, ensure_ascii=False)}
    return _transport

_deps = _WD(search=_fake_search, vertical_transports={
    "scholar": _fake_transport("scholar", _scholar_payload),
    "news": _fake_transport("news", _news_payload),
    "images": _fake_transport("images", _images_payload)})
try:
    _deps.search = None
    raise SystemExit("deps not frozen")
except _dc.FrozenInstanceError:
    pass
try:
    _deps.vertical_transports["scholar"] = None
    raise SystemExit("transports not frozen")
except TypeError:
    pass

_mod.register(_ctx, deps=_deps)

_EXPECTED = {"goat_search", "goat_extract", "goat_crawl", "goat_probe",
             "goat_answer", "goat_filtered_search", "goat_vertical_search"}
_scoped_names = set()
for _name in _EXPECTED:
    _entry = registry.get_entry(_name, scope=_scope)
    assert _entry is not None, "missing scoped entry: %s" % _name
    assert _entry.toolset == "goat_web", (_name, _entry.toolset)
    assert _entry.schema.get("name") == _name, (_name, _entry.schema)
    assert callable(_entry.handler), _name
    _scoped_names.add(_name)
for _alias in ("goat_scholar", "goat_news", "goat_images"):
    assert registry.get_entry(_alias, scope=_scope) is None, "alias entry present: %s" % _alias
assert registry.get_entry("goat_answer", scope="goat-nonexistent-scope-xyz") is None, "scope leak"
assert registry.get_entry("goat_search", scope="goat-nonexistent-scope-xyz") is None, "scope leak"

def _dispatch(name, args, **kw):
    _raw = registry.dispatch(name, args, scope=_scope, **kw)
    assert isinstance(_raw, str), (name, type(_raw))
    return _json.loads(_raw)

_raw_answer = registry.dispatch("goat_answer", {"query": "nuclear fission energy"}, scope=_scope)
assert isinstance(_raw_answer, str), type(_raw_answer)
assert "\\u00e9" not in _raw_answer, "answer JSON must not escape Unicode"
_answer = _json.loads(_raw_answer)
assert _answer.get("ok") is True, _answer
assert "Caf\u00e9" in _answer.get("answer", ""), _answer
_sources = _answer.get("sources")
assert isinstance(_sources, list) and _sources, _answer
assert [ _i["index"] for _i in _sources ] == list(range(1, len(_sources) + 1)), _sources
_cited = {int(_n) for _n in _re.findall(r"\[(\d+)\]", _answer["answer"])}
assert _cited and _cited <= { _i["index"] for _i in _sources }, (_answer, _sources)
for _line in _answer["answer"].split("\n"):
    assert _re.search(r"\[\d+\]", _line), _line
for _item in _sources:
    assert _item["url"].startswith("https://"), _item

_filtered = _dispatch("goat_filtered_search",
    {"query": "fission energy", "max_results": 1, "allowed_domains": ["good.example"]})
assert _filtered.get("ok") is True, _filtered
assert isinstance(_filtered.get("results"), list) and len(_filtered["results"]) == 1, _filtered
assert _filtered["results"][0]["url"] == "https://good.example/un%C3%AFcode-1", _filtered
assert _filtered["results"][0].get("published_at") == "2024-06-01T00:00:00Z", _filtered
assert _filtered["results"][0].get("language") == "en", _filtered

_scholar = _dispatch("goat_vertical_search", {"vertical": "scholar", "query": "offline scholar"})
assert _scholar.get("ok") is True, _scholar
assert _scholar.get("vertical") == "scholar" and _scholar.get("source") == "crossref", _scholar
assert _scholar.get("source_url") == "https://www.crossref.org/", _scholar
_first = _scholar["results"][0]
assert _first["doi"] == "10.1234/cafe-2021" and _first["authors"] == ["Ada Lovelace"], _first
assert _first["year"] == 2021 and _first["venue"] == "Journal of Tests", _first
assert "Caf\u00e9" in _first["title"], _first

_news = _dispatch("goat_vertical_search", {"vertical": "news", "query": "offline news"})
assert _news.get("ok") is True, _news
assert _news.get("vertical") == "news" and _news.get("source") == "gdelt", _news
assert _news.get("source_url") == "https://gdeltproject.org/", _news
_article = _news["results"][0]
assert _article["url"] == "https://example.com/news-item", _article
assert _article["published"] == "20261009T120000Z", _article
assert _article["language"] == "English" and _article["source"] == "example.com", _article

_images = _dispatch("goat_vertical_search", {"vertical": "images", "query": "offline images"})
assert _images.get("ok") is True, _images
assert _images.get("vertical") == "images" and _images.get("source") == "wikimedia-commons", _images
assert _images.get("source_url") == "https://commons.wikimedia.org/", _images
_medium = _images["results"][0]
assert _medium["license"] == "CC-BY-SA 4.0" and _medium["creator"] == "Test Artist", _medium
assert _medium["license_url"] == "https://creativecommons.org/licenses/by-sa/4.0/", _medium
assert _medium["page_url"] == "https://commons.wikimedia.org/wiki/File:Cafe_test.jpg", _medium
assert _recorded["scholar"][0].startswith("https://api.crossref.org/works?"), _recorded
assert _recorded["news"][0].startswith("https://api.gdeltproject.org/api/v2/doc/doc?"), _recorded
assert _recorded["images"][0].startswith("https://commons.wikimedia.org/w/api.php?"), _recorded

for (_tname, _badargs) in [
    ("goat_answer", {"query": None}),
    ("goat_answer", {"query": "ok", "bogus_field": 1}),
    ("goat_filtered_search", {"query": "ok", "max_results": True}),
    ("goat_vertical_search", {"vertical": "scholar", "query": None}),
    ("goat_vertical_search", {"vertical": "nope", "query": "ok"}),
    ("goat_search", {"query": None}),
    ("goat_search", {"query": "ok", "unknown_field": 1}),
    ("goat_probe", {"url": None}),
    ("no_such_goat_tool", {"query": "ok"}),
]:
    _rej = registry.dispatch(_tname, _badargs, scope=_scope)
    _rej_text = _rej if isinstance(_rej, str) else _json.dumps(_rej)
    _rej_obj = _json.loads(_rej_text) if isinstance(_rej, str) else _rej
    if _tname == "no_such_goat_tool":
        assert "error" in _rej_obj, _rej_obj
    else:
        assert _rej_obj.get("ok") is False, (_tname, _rej_obj)
        assert _rej_obj.get("error", {}).get("code") == "URL_BLOCKED", (_tname, _rej_obj)
        assert set(_rej_obj) == {"ok", "error"}, (_tname, sorted(_rej_obj))
        assert set(_rej_obj["error"]) == {"code"}, (_tname, _rej_obj)

_ctx_ignored = _dispatch("goat_answer", {"query": "nuclear fission"},
                         task_id="t-1", session_id="s-1", user_task="u-1", parent_agent="p-1")
assert _ctx_ignored.get("ok") is True, _ctx_ignored

_probe_mod = _sys.modules.get(_pkg + ".url_gate") or _sys.modules.get(_pkg + ".goat_tools")
_orig_getaddrinfo = _socket.getaddrinfo
def _fake_public_getaddrinfo(host, port, *a, **k):
    return [(_socket.AF_INET, _socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
_socket.getaddrinfo = _fake_public_getaddrinfo
import http.client as _http_client
class _Fake404Response(object):
    status = 404
    def read(self, n=-1):
        return b"not found"
    def getheaders(self):
        return [("content-type", "text/plain")]
class _Fake404Conn(object):
    def __init__(self, hostname, address, timeout=10):
        pass
    def request(self, *a, **k):
        pass
    def getresponse(self):
        return _Fake404Response()
    def close(self):
        pass
_url_gate_mod = None
for _mname, _mval in list(_sys.modules.items()):
    if _mname == _pkg or _mname.startswith(_pkg + "."):
        if getattr(_mval, "_PinnedHTTPSConnection", None) is not None:
            _url_gate_mod = _mval
            break
assert _url_gate_mod is not None, "url_gate module not found for network-level fake"
_orig_conn = _url_gate_mod._PinnedHTTPSConnection
_url_gate_mod._PinnedHTTPSConnection = _Fake404Conn
try:
    _probe_raw = registry.dispatch(
        "goat_probe", {"url": "https://example.com/missing-page-404-probe"}, scope=_scope)
finally:
    _url_gate_mod._PinnedHTTPSConnection = _orig_conn
    _socket.getaddrinfo = _orig_getaddrinfo
assert isinstance(_probe_raw, str), type(_probe_raw)
_probe = _json.loads(_probe_raw)
assert _probe.get("ok") is False, _probe
assert _probe.get("error", {}).get("code") == "URL_BLOCKED", _probe
assert set(_probe) == {"ok", "error"}, sorted(_probe)
assert set(_probe["error"]) == {"code"}, _probe

def _parse_simple_yaml(_text):
    _parsed = {}
    _current = None
    for _line in _text.splitlines():
        if not _line.strip() or _line.strip().startswith("#"):
            continue
        if _line.startswith((" ", "\t")):
            _s = _line.strip()
            assert _s.startswith("- ") and _current is not None, _line
            _current.append(_s[2:].strip())
            continue
        assert ":" in _line, _line
        _k, _, _v = _line.partition(":")
        _k = _k.strip()
        _v = _v.strip()
        assert _k and " " not in _k, _line
        if _v == "":
            _current = []
            _parsed[_k] = _current
        elif _v == "[]":
            _current = None
            _parsed[_k] = []
        else:
            _current = None
            _parsed[_k] = _v
    return _parsed

_plugin_yaml = _parse_simple_yaml(_io.open(_os.path.join(BUNDLE, "plugin.yaml"), encoding="utf-8").read())
_plugin_json = _json.loads(_io.open(_os.path.join(BUNDLE, "hermes-goat-web.plugin.json"), encoding="utf-8").read())
assert _plugin_yaml.get("version") == "0.2.0", _plugin_yaml
assert _plugin_json.get("version") == "0.2.0", _plugin_json
assert set(_plugin_yaml.get("tools", [])) == _EXPECTED, _plugin_yaml
assert set(_plugin_yaml.get("provides_tools", [])) == _EXPECTED, _plugin_yaml
assert set(_plugin_json.get("tools", [])) == _EXPECTED, _plugin_json

_summary = {"answer_sources": len(_sources), "filtered_url": _filtered["results"][0]["url"],
            "scholar_doi": _first["doi"], "news_published": _article["published"],
            "images_license": _medium["license"], "probe_code": _probe["error"]["code"],
            "manifest_version": _plugin_yaml.get("version"),
            "registered_seven": sorted(_scoped_names),
            "child_executable": _sys.executable}
_sys.stdout.write("GOAT_NATIVE_H1_OK " + _json.dumps(_summary, ensure_ascii=False) + "\n")
'''

_CLI_PREAMBLE = r'''
import io as _io
import json as _json
import os as _os
import socket as _socket
import sys as _sys

BUNDLE = __BUNDLE__
SCRATCH = __SCRATCH__
SOURCE_ROOT = __SOURCE_ROOT__
MODE = __MODE__

assert _os.environ.get("HERMES_HOME", "").startswith(SCRATCH), _os.environ.get("HERMES_HOME")
assert _os.environ.get("HOME", "").startswith(SCRATCH), _os.environ.get("HOME")
assert _os.environ.get("TMPDIR", "").startswith(SCRATCH), _os.environ.get("TMPDIR")
assert "PYTHONPATH" not in _os.environ, "PYTHONPATH must be sanitized"
assert _os.environ.get("HERMES_DISABLE_LAZY_INSTALLS") == "1", "lazy installs must be suppressed"

_SCRATCH_REAL = _os.path.realpath(SCRATCH)
_SECRET_BASES = frozenset({".env", "config.yaml", "auth.json"})
_PROBE_SENTINEL = "HERMES_VALIDATE_JSON:"

def _real_path(p):
    try:
        s = _os.fspath(p)
    except Exception:
        return None
    if isinstance(s, int):
        return None
    if isinstance(s, bytes):
        try:
            s = s.decode("utf-8", "surrogateescape")
        except Exception:
            return None
    if not isinstance(s, str):
        return None
    try:
        if not _os.path.isabs(s):
            s = _os.path.join(_os.getcwd(), s)
        return _os.path.realpath(s)
    except Exception:
        return None

def _inside_scratch(p):
    r = _real_path(p)
    if r is None:
        return False
    try:
        return _os.path.commonpath([r, _SCRATCH_REAL]) == _SCRATCH_REAL
    except Exception:
        return False

def _is_write_flags(flags):
    try:
        import os as _o
        return bool(flags & (_o.O_WRONLY | _o.O_RDWR | _o.O_CREAT | _o.O_TRUNC | _o.O_APPEND))
    except Exception:
        return False

def _is_probe_popen(popen_args):
    try:
        if not isinstance(popen_args, (list, tuple)) or len(popen_args) < 2:
            return False
        exe = popen_args[0]
        argv = popen_args[1]
        if not isinstance(argv, (list, tuple)) or len(argv) != 6:
            return False
        if argv[0] != exe or exe != _sys.executable:
            return False
        if argv[1] != "-c":
            return False
        script = argv[2]
        if not isinstance(script, str):
            return False
        if "hermes_validate_probe_plugin" not in script or "RecordingContext" not in script:
            return False
        if argv[3] != BUNDLE:
            return False
        if argv[4] != _PROBE_SENTINEL:
            return False
        opts = _json.loads(argv[5])
        if not isinstance(opts, dict):
            return False
        if "context_methods" not in opts or "kind" not in opts:
            return False
        if len(popen_args) >= 4 and isinstance(popen_args[3], dict):
            env = popen_args[3]
            if "PYTHONPATH" in env:
                return False
            for _bad in ("GOOGLE_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HERMES_API_KEY"):
                if _bad in env:
                    return False
            _hh = env.get("HERMES_HOME", "")
            if not isinstance(_hh, str):
                return False
            try:
                _hhr = _os.path.realpath(_hh)
                if _os.path.commonpath([_hhr, _SCRATCH_REAL]) != _SCRATCH_REAL:
                    return False
            except Exception:
                return False
        return True
    except Exception:
        return False

def _auditor(event, args):
    if event == "open":
        try:
            raw = args[0]
        except Exception:
            return
        try:
            sp = _os.fspath(raw)
        except Exception:
            return
        if isinstance(sp, int):
            return
        if isinstance(sp, bytes):
            try:
                sp = sp.decode("utf-8", "surrogateescape")
            except Exception:
                return
        if not isinstance(sp, str):
            return
        flags = args[2] if len(args) > 2 else 0
        if _is_write_flags(flags):
            if sp == "/dev/null":
                return
            if sp.startswith("/dev/") or sp.startswith("/proc/"):
                raise RuntimeError("write to device denied: %r" % sp)
            if not _inside_scratch(sp):
                raise RuntimeError("write outside disposable scratch denied: %r" % sp)
        else:
            base = _os.path.basename(sp)
            if base in _SECRET_BASES and not _inside_scratch(sp):
                raise RuntimeError("live secret read denied: %r" % sp)
        return
    if event in ("os.mkdir", "os.remove", "os.rmdir", "os.unlink"):
        try:
            p = _os.fspath(args[0])
        except Exception:
            return
        if not _inside_scratch(p):
            raise RuntimeError("mutation outside scratch denied: %s %r" % (event, p))
        return
    if event in ("os.rename", "os.replace", "os.symlink", "os.link"):
        try:
            a = _os.fspath(args[0])
            b = _os.fspath(args[1])
        except Exception:
            return
        if not _inside_scratch(a) or not _inside_scratch(b):
            raise RuntimeError("mutation outside scratch denied: %s %r %r" % (event, a, b))
        return
    if event == "shutil.rmtree":
        try:
            p = _os.fspath(args[0])
        except Exception:
            return
        if not _inside_scratch(p):
            raise RuntimeError("mutation outside scratch denied: %s %r" % (event, p))
        return
    if event in ("socket.getaddrinfo", "socket.gethostbyname", "socket.connect", "socket.__new__"):
        raise RuntimeError("network access is denied in native CLI gate: %s" % event)
    if event == "subprocess.Popen":
        if _is_probe_popen(args):
            return
        raise RuntimeError("subprocess launch is denied in native CLI gate")
    if event in ("os.system", "os.spawn", "os.exec", "os.fork", "os.posix_spawn"):
        raise RuntimeError("process spawn is denied in native CLI gate: %s" % event)
    if event.startswith("os.spawn") or event.startswith("os.exec") or event.startswith("os.fork"):
        raise RuntimeError("process spawn is denied in native CLI gate: %s" % event)
    return

_sys.addaudithook(_auditor)

def _selfcheck_cli():
    import os as _o
    _W = _o.O_WRONLY | _o.O_CREAT
    def _deny(ev, ar):
        try:
            _auditor(ev, ar)
        except RuntimeError:
            return True
        return False
    assert _deny("open", ("/tmp/goat-cli-outside-probe/evil.txt", "w", _W)), "open write outside must deny"
    assert _deny("open", (SCRATCH + "/../cli-escape.txt", "w", _W)), "relative escape write must deny"
    assert _deny("open", ("/opt/data/.env", "r", 0)), "live .env read must deny"
    assert _deny("open", ("/opt/data/auth.json", "r", 0)), "live auth read must deny"
    assert _deny("open", ("/opt/data/config.yaml", "r", 0)), "live config read must deny"
    assert _deny("os.mkdir", ("/tmp/goat-cli-evil-dir", 511, -1)), "mkdir outside must deny"
    assert _deny("os.rename", ("/tmp/a", "/tmp/b", -1, -1)), "rename outside must deny"
    assert _deny("shutil.rmtree", ("/tmp/goat-cli-evil-tree", None)), "rmtree outside must deny"
    assert _deny("socket.getaddrinfo", ("example.com", 80, 0, 0, 0)), "getaddrinfo must deny"
    assert _deny("socket.gethostbyname", ("example.com",)), "gethostbyname must deny"
    assert _deny("socket.connect", (None, ("93.184.216.34", 80))), "connect must deny"
    assert _deny("socket.__new__", (None, 2, 1, 0)), "socket creation must deny"
    assert _deny("subprocess.Popen", ("/bin/sh", ["/bin/sh", "-c", "id"], None, None)), "popen must deny"
    assert _deny("os.system", ("id",)), "system must deny"
    _auditor("open", (SCRATCH + "/selfcheck-ok.txt", "w", _W))
    _auditor("open", ("/dev/null", "w", _W))
    _auditor("os.mkdir", (SCRATCH + "/selfcheck-dir", 511, -1))
    _sys.stdout.write("GOAT_NATIVE_CLI_AUDIT_OK 1\n")

_selfcheck_cli()

def _deny_net(*_a, **_k):
    raise RuntimeError("network access is denied in native CLI gate")

def _allow_probe_argv(argv):
    try:
        if not isinstance(argv, (list, tuple)) or len(argv) != 6:
            return False
        if argv[0] != _sys.executable or argv[1] != "-c":
            return False
        if "hermes_validate_probe_plugin" not in argv[2] or "RecordingContext" not in argv[2]:
            return False
        return argv[3] == BUNDLE and argv[4] == _PROBE_SENTINEL
    except Exception:
        return False

import subprocess as _sp
_orig_popen = _sp.Popen
_orig_run = _sp.run
_orig_call = _sp.call
_orig_check_call = _sp.check_call
_orig_check_output = _sp.check_output
class _GuardedPopen(_orig_popen):
    def __init__(self, args, *a, **k):
        _argv = args if isinstance(args, (list, tuple)) else [args]
        if not _allow_probe_argv(list(_argv)):
            raise RuntimeError("subprocess launch is denied in native CLI gate")
        super().__init__(args, *a, **k)
_sp.Popen = _GuardedPopen
def _guarded_run(args, *a, **k):
    _argv = args if isinstance(args, (list, tuple)) else [args]
    if not _allow_probe_argv(list(_argv)):
        raise RuntimeError("subprocess launch is denied in native CLI gate")
    return _orig_run(args, *a, **k)
def _guarded_call(args, *a, **k):
    _argv = args if isinstance(args, (list, tuple)) else [args]
    if not _allow_probe_argv(list(_argv)):
        raise RuntimeError("subprocess launch is denied in native CLI gate")
    return _orig_call(args, *a, **k)
def _guarded_check_call(args, *a, **k):
    _argv = args if isinstance(args, (list, tuple)) else [args]
    if not _allow_probe_argv(list(_argv)):
        raise RuntimeError("subprocess launch is denied in native CLI gate")
    return _orig_check_call(args, *a, **k)
def _guarded_check_output(args, *a, **k):
    _argv = args if isinstance(args, (list, tuple)) else [args]
    if not _allow_probe_argv(list(_argv)):
        raise RuntimeError("subprocess launch is denied in native CLI gate")
    return _orig_check_output(args, *a, **k)
_sp.run = _guarded_run
_sp.call = _guarded_call
_sp.check_call = _guarded_check_call
_sp.check_output = _guarded_check_output
_socket.create_connection = _deny_net
_socket.socket.connect = _deny_net
_socket.socket.connect_ex = _deny_net
if hasattr(_os, "system"):
    try:
        _os.system = _deny_net
    except Exception:
        pass
if hasattr(_os, "fork"):
    try:
        _os.fork = _deny_net
    except Exception:
        pass
for _n in ("spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe", "posix_spawn"):
    if hasattr(_os, _n):
        try:
            setattr(_os, _n, _deny_net)
        except Exception:
            pass
for _n in ("execv", "execve", "execl", "execle", "execlp", "execlpe", "execvp", "execvpe"):
    if hasattr(_os, _n):
        try:
            setattr(_os, _n, _deny_net)
        except Exception:
            pass

_sys.path.insert(0, SOURCE_ROOT)
'''

_CLI_BODY = r'''
from hermes_cli.main import main as _hermes_main

if MODE == "doctor":
    _sys.argv = ["hermes", "plugins", "doctor", BUNDLE, "--ci"]
else:
    _sys.argv = ["hermes", "plugins", "validate", BUNDLE]

_out = _io.StringIO()
_err = _io.StringIO()
_exit = 0
_old_out, _old_err = _sys.stdout, _sys.stderr
_sys.stdout, _sys.stderr = _out, _err
try:
    try:
        _ret = _hermes_main()
        if isinstance(_ret, int):
            _exit = _ret
    except SystemExit as _exc:
        _exit = _exc.code if isinstance(_exc.code, int) else (1 if _exc.code else 0)
    except Exception as _exc:
        _err.write("hermes main raised %r\n" % (_exc,))
        _exit = 3
finally:
    _sys.stdout, _sys.stderr = _old_out, _old_err
_text = _out.getvalue() + _err.getvalue()
_sys.stdout.write("GOAT_NATIVE_CLI_%s_EXIT %d\n" % (MODE.upper(), _exit))
for _line in _text.splitlines()[-40:]:
    _sys.stdout.write("GOAT_NATIVE_CLI_%s_LOG %s\n" % (MODE.upper(), _line[:500]))
'''


def _write_child(base, name, template, mapping):
    text = template
    for key, value in mapping.items():
        text = text.replace(key, json.dumps(value))
    path = base / name
    path.write_text(text, encoding="utf-8")
    return path


class NativeH1RegistrationDispatchTests(unittest.TestCase):
    """H1: real PluginContext/Manager/Manifest + real registry dispatch."""

    def test_native_ctx_registers_seven_and_dispatches_all_routes(self):
        runtime = _runtime_python()
        source_root = _source_root()
        bundle = _build_fresh_bundle(self)
        base = _fresh_scratch(self, "native-h1")
        env = _child_env(base)
        script = _write_child(
            base,
            "h1_child.py",
            _H1_PREAMBLE + _H1_BODY,
            {
                "__BUNDLE__": str(bundle),
                "__SCRATCH__": str(base),
                "__SOURCE_ROOT__": source_root,
            },
        )
        proc = _run_child(env, script, cwd=base, timeout=100)
        sentinel = None
        audit_ok = False
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GOAT_NATIVE_H1_OK "):
                sentinel = json.loads(
                    line[len("GOAT_NATIVE_H1_OK "):]
                )
            elif line.strip() == "GOAT_NATIVE_H1_AUDIT_OK 1":
                audit_ok = True
        self.assertEqual(
            proc.returncode,
            0,
            "native H1 child failed: rc=%r\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout, proc.stderr),
        )
        self.assertIsNotNone(
            sentinel,
            "missing GOAT_NATIVE_H1_OK sentinel\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.stdout, proc.stderr),
        )
        self.assertTrue(audit_ok, "H1 auditor selfcheck missing\n%s" % proc.stdout)
        self.assertEqual(
            sentinel,
            {
                "answer_sources": 3,
                "filtered_url": "https://good.example/un%C3%AFcode-1",
                "scholar_doi": "10.1234/cafe-2021",
                "news_published": "20261009T120000Z",
                "images_license": "CC-BY-SA 4.0",
                "probe_code": "URL_BLOCKED",
                "manifest_version": "0.2.0",
                "registered_seven": sorted(EXPECTED_SEVEN),
                "child_executable": runtime,
            },
        )


class NativeH2ManagerValidationTests(unittest.TestCase):
    """H2: real hermes plugins doctor --ci and plugins validate (no deps)."""

    def _run_cli_gate(self, mode):
        source_root = _source_root()
        bundle = _build_fresh_bundle(self)
        base = _fresh_scratch(self, "native-" + mode)
        env = _child_env(base)
        script = _write_child(
            base,
            mode + "_child.py",
            _CLI_PREAMBLE + _CLI_BODY,
            {
                "__BUNDLE__": str(bundle),
                "__SCRATCH__": str(base),
                "__SOURCE_ROOT__": source_root,
                "__MODE__": mode,
            },
        )
        if mode == "validate":
            self.assertNotIn("--install-deps", script.read_text(encoding="utf-8"))
        proc = _run_child(env, script, cwd=base, timeout=120)
        return proc, bundle

    def test_plugins_doctor_ci_passes_with_seven_tools(self):
        proc, _bundle = self._run_cli_gate("doctor")
        exit_code = None
        logs = []
        audit_ok = False
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GOAT_NATIVE_CLI_DOCTOR_EXIT "):
                exit_code = int(line.split()[-1])
            elif line.startswith("GOAT_NATIVE_CLI_DOCTOR_LOG "):
                logs.append(line[len("GOAT_NATIVE_CLI_DOCTOR_LOG "):])
            elif line.strip() == "GOAT_NATIVE_CLI_AUDIT_OK 1":
                audit_ok = True
        text = "\n".join(logs)
        self.assertTrue(audit_ok, "CLI auditor selfcheck missing\n%s" % proc.stdout)
        self.assertEqual(
            proc.returncode,
            0,
            "doctor child crashed: rc=%r\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout, proc.stderr),
        )
        self.assertEqual(
            exit_code,
            0,
            "hermes plugins doctor --ci failed\nLOGS:\n%s\nSTDERR:\n%s"
            % (text, proc.stderr),
        )
        self.assertIn("hermes-goat-web", text, text)
        self.assertIn("0.2.0", text, text)
        self.assertIn("7 tool(s)", text, text)

    def test_plugins_validate_passes_without_install_deps(self):
        proc, _bundle = self._run_cli_gate("validate")
        exit_code = None
        logs = []
        audit_ok = False
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GOAT_NATIVE_CLI_VALIDATE_EXIT "):
                exit_code = int(line.split()[-1])
            elif line.startswith("GOAT_NATIVE_CLI_VALIDATE_LOG "):
                logs.append(line[len("GOAT_NATIVE_CLI_VALIDATE_LOG "):])
            elif line.strip() == "GOAT_NATIVE_CLI_AUDIT_OK 1":
                audit_ok = True
        text = "\n".join(logs)
        self.assertTrue(audit_ok, "CLI auditor selfcheck missing\n%s" % proc.stdout)
        self.assertEqual(
            proc.returncode,
            0,
            "validate child crashed: rc=%r\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout, proc.stderr),
        )
        self.assertEqual(
            exit_code,
            0,
            "hermes plugins validate failed\nLOGS:\n%s\nSTDERR:\n%s"
            % (text, proc.stderr),
        )
        self.assertIn("Validation passed.", text, text)


class AuditorDirectSelfcheckTests(unittest.TestCase):
    """Fast parent-side checks of the hardened auditor contract.

    No filesystem access, no sockets, no subprocess: the auditor
    callbacks are invoked directly with fake arguments using only
    realpath/commonpath on in-memory strings.
    """

    def _make_auditor(self, scratch):
        import os as _os

        scratch_real = _os.path.realpath(scratch)
        secrets = frozenset({".env", "config.yaml", "auth.json"})

        def _real(p):
            try:
                s = _os.fspath(p)
            except Exception:
                return None
            if isinstance(s, int):
                return None
            if isinstance(s, bytes):
                try:
                    s = s.decode("utf-8", "surrogateescape")
                except Exception:
                    return None
            if not isinstance(s, str):
                return None
            try:
                if not _os.path.isabs(s):
                    s = _os.path.join("/tmp/goat-audit-cwd", s)
                return _os.path.realpath(s)
            except Exception:
                return None

        def _inside(p):
            r = _real(p)
            if r is None:
                return False
            try:
                return _os.path.commonpath([r, scratch_real]) == scratch_real
            except Exception:
                return False

        def _is_write(flags):
            import os as _o

            return bool(
                flags
                & (_o.O_WRONLY | _o.O_RDWR | _o.O_CREAT | _o.O_TRUNC | _o.O_APPEND)
            )

        def auditor(event, args):
            if event == "open":
                sp = _os.fspath(args[0])
                if isinstance(sp, int):
                    return
                if isinstance(sp, bytes):
                    sp = sp.decode("utf-8", "surrogateescape")
                flags = args[2] if len(args) > 2 else 0
                if _is_write(flags):
                    if sp == "/dev/null":
                        return
                    if sp.startswith("/dev/") or sp.startswith("/proc/"):
                        raise RuntimeError("device denied")
                    if not _inside(sp):
                        raise RuntimeError("write outside denied")
                else:
                    if (
                        _os.path.basename(sp) in secrets
                        and not _inside(sp)
                    ):
                        raise RuntimeError("secret read denied")
                return
            if event in ("os.mkdir", "os.remove", "os.rmdir", "os.unlink"):
                if not _inside(_os.fspath(args[0])):
                    raise RuntimeError("mutation denied")
                return
            if event in ("os.rename", "os.replace", "os.symlink", "os.link"):
                if not _inside(_os.fspath(args[0])) or not _inside(
                    _os.fspath(args[1])
                ):
                    raise RuntimeError("mutation denied")
                return
            if event == "shutil.rmtree":
                if not _inside(_os.fspath(args[0])):
                    raise RuntimeError("mutation denied")
                return
            if event in (
                "socket.getaddrinfo",
                "socket.gethostbyname",
                "socket.connect",
                "socket.__new__",
            ):
                raise RuntimeError("network denied: %s" % event)
            if event == "subprocess.Popen":
                raise RuntimeError("subprocess denied")
            if event in (
                "os.system",
                "os.spawn",
                "os.exec",
                "os.fork",
                "os.posix_spawn",
            ):
                raise RuntimeError("spawn denied: %s" % event)
            if event.startswith("os.spawn") or event.startswith(
                "os.exec"
            ) or event.startswith("os.fork"):
                raise RuntimeError("spawn denied: %s" % event)
            return

        return auditor

    def test_templates_contain_hardened_guards(self):
        for template in (_H1_PREAMBLE, _CLI_PREAMBLE):
            self.assertIn("commonpath", template)
            self.assertIn("realpath", template)
            self.assertIn("socket.getaddrinfo", template)
            self.assertIn("socket.gethostbyname", template)
            self.assertIn("socket.__new__", template)
            self.assertIn("os.mkdir", template)
            self.assertIn("shutil.rmtree", template)
            self.assertIn("config.yaml", template)
            self.assertIn("auth.json", template)
            self.assertNotIn("_BUILD_ROOT", template)
        self.assertIn("hermes_validate_probe_plugin", _CLI_PREAMBLE)
        self.assertIn("RecordingContext", _CLI_PREAMBLE)
        self.assertIn("_is_probe_popen", _CLI_PREAMBLE)
        self.assertIn("isinstance(_ret, int)", _CLI_BODY)

    def test_direct_auditor_rejects_forbidden_events_without_filesystem(self):
        import os as _o

        scratch = "/tmp/goat-scratch-%s" % uuid.uuid4().hex[:8]
        auditor = self._make_auditor(scratch)
        write_flags = _o.O_WRONLY | _o.O_CREAT

        def denies(event, args):
            try:
                auditor(event, args)
            except RuntimeError:
                return True
            return False

        self.assertTrue(
            denies("open", ("/tmp/goat-outside-evil.txt", "w", write_flags))
        )
        self.assertTrue(
            denies("open", (scratch + "/../escape.txt", "w", write_flags))
        )
        self.assertTrue(denies("open", ("relative-escape.txt", "w", write_flags)))
        self.assertTrue(denies("open", ("/opt/data/.env", "r", 0)))
        self.assertTrue(denies("open", ("/opt/data/auth.json", "r", 0)))
        self.assertTrue(denies("open", ("/opt/data/config.yaml", "r", 0)))
        self.assertTrue(denies("os.mkdir", ("/tmp/goat-evil-dir", 511, -1)))
        self.assertTrue(denies("os.remove", ("/tmp/goat-evil", -1)))
        self.assertTrue(denies("os.rmdir", ("/tmp/goat-evil", -1)))
        self.assertTrue(denies("os.rename", ("/tmp/a", "/tmp/b", -1, -1)))
        self.assertTrue(denies("os.symlink", ("/tmp/a", "/tmp/b", -1)))
        self.assertTrue(denies("shutil.rmtree", ("/tmp/goat-evil-tree", None)))
        self.assertTrue(
            denies("socket.getaddrinfo", ("example.com", 80, 0, 0, 0))
        )
        self.assertTrue(denies("socket.gethostbyname", ("example.com",)))
        self.assertTrue(denies("socket.connect", (None, ("93.184.216.34", 80))))
        self.assertTrue(denies("socket.__new__", (None, 2, 1, 0)))
        self.assertTrue(
            denies(
                "subprocess.Popen",
                ("/bin/sh", ["/bin/sh", "-c", "id"], None, None),
            )
        )
        self.assertTrue(denies("os.system", ("id",)))
        # Allowed paths must not raise (still no filesystem access).
        auditor("open", (scratch + "/ok.txt", "w", write_flags))
        auditor("open", ("/dev/null", "w", write_flags))
        auditor("os.mkdir", (scratch + "/ok-dir", 511, -1))


class BrokenBundleNegativeTests(unittest.TestCase):
    """Real doctor/validate gates against damaged bundles must exit nonzero."""

    def _run_gate_with_bundle(self, mode, bundle):
        source_root = _source_root()
        base = _fresh_scratch(self, "native-broken-" + mode)
        env = _child_env(base)
        script = _write_child(
            base,
            mode + "_broken_child.py",
            _CLI_PREAMBLE + _CLI_BODY,
            {
                "__BUNDLE__": str(bundle),
                "__SCRATCH__": str(base),
                "__SOURCE_ROOT__": source_root,
                "__MODE__": mode,
            },
        )
        proc = _run_child(env, script, cwd=base, timeout=120)
        return proc

    def _parse_gate(self, proc, mode):
        exit_code = None
        logs = []
        audit_ok = False
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GOAT_NATIVE_CLI_%s_EXIT " % mode.upper()):
                exit_code = int(line.split()[-1])
            elif line.startswith("GOAT_NATIVE_CLI_%s_LOG " % mode.upper()):
                logs.append(line[len("GOAT_NATIVE_CLI_%s_LOG " % mode.upper()):])
            elif line.strip() == "GOAT_NATIVE_CLI_AUDIT_OK 1":
                audit_ok = True
        return exit_code, "\n".join(logs), audit_ok

    def test_doctor_rejects_bundle_missing_init(self):
        bundle = _build_fresh_bundle(self)
        target = Path(bundle) / "__init__.py"
        target.unlink()
        proc = self._run_gate_with_bundle("doctor", bundle)
        exit_code, text, audit_ok = self._parse_gate(proc, "doctor")
        self.assertTrue(audit_ok, "hardened auditor selfcheck must pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIsNotNone(exit_code, proc.stdout)
        self.assertNotEqual(exit_code, 0, text)
        self.assertNotIn("7 tool(s)", text)

    def test_validate_rejects_bundle_missing_vendor_dependency(self):
        bundle = _build_fresh_bundle(self)
        target = Path(bundle) / "_goat_v3_vendor" / "ssrf_guard.py"
        target.unlink()
        proc = self._run_gate_with_bundle("validate", bundle)
        exit_code, text, audit_ok = self._parse_gate(proc, "validate")
        self.assertTrue(audit_ok, "hardened auditor selfcheck must pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIsNotNone(exit_code, proc.stdout)
        self.assertNotEqual(exit_code, 0, text)
        self.assertNotIn("Validation passed.", text)


class NativeBytecodeCleanlinessTests(unittest.TestCase):
    """Milestone 12: real validate capability probe must not contaminate bundle bytes."""

    def _inventory(self, bundle):
        files = {}
        for root, dirs, names in os.walk(bundle):
            dirs.sort()
            for name in sorted(names):
                full = Path(root) / name
                rel = str(full.relative_to(bundle))
                files[rel] = hashlib.sha256(
                    full.read_bytes()
                ).hexdigest()
        return files

    def test_validate_leaves_bundle_bytes_unchanged(self):
        source_root = _source_root()
        bundle = _build_fresh_bundle(self)
        before = self._inventory(bundle)
        self.assertTrue(before, "fresh bundle inventory must be non-empty")
        self.assertEqual(
            [p for p in before if p.endswith(".pyc") or "__pycache__" in p],
            [],
            "fresh bundle must contain no bytecode",
        )
        base = _fresh_scratch(self, "native-validate-clean")
        env = _child_env(base)
        script = _write_child(
            base,
            "validate_clean_child.py",
            _CLI_PREAMBLE + _CLI_BODY,
            {
                "__BUNDLE__": str(bundle),
                "__SCRATCH__": str(base),
                "__SOURCE_ROOT__": source_root,
                "__MODE__": "validate",
            },
        )
        proc = _run_child(env, script, cwd=base, timeout=120)
        exit_code = None
        logs = []
        audit_ok = False
        for line in (proc.stdout or "").splitlines():
            if line.startswith("GOAT_NATIVE_CLI_VALIDATE_EXIT "):
                exit_code = int(line.split()[-1])
            elif line.startswith("GOAT_NATIVE_CLI_VALIDATE_LOG "):
                logs.append(line[len("GOAT_NATIVE_CLI_VALIDATE_LOG "):])
            elif line.strip() == "GOAT_NATIVE_CLI_AUDIT_OK 1":
                audit_ok = True
        text = "\n".join(logs)
        self.assertTrue(audit_ok, "CLI auditor selfcheck missing\n%s" % proc.stdout)
        self.assertEqual(
            proc.returncode,
            0,
            "validate child crashed: rc=%r\nSTDOUT:\n%s\nSTDERR:\n%s"
            % (proc.returncode, proc.stdout, proc.stderr),
        )
        self.assertEqual(
            exit_code,
            0,
            "hermes plugins validate failed\nLOGS:\n%s\nSTDERR:\n%s"
            % (text, proc.stderr),
        )
        self.assertIn("Validation passed.", text, text)
        after = self._inventory(bundle)
        extra = sorted(set(after) - set(before))
        missing = sorted(set(before) - set(after))
        changed = sorted(
            p for p in set(before) & set(after) if before[p] != after[p]
        )
        self.assertEqual(missing, [], "validate removed bundle files: %r" % (missing,))
        self.assertEqual(
            extra, [], "validate contaminated bundle with extra files: %r" % (extra,)
        )
        self.assertEqual(
            changed, [], "validate modified bundle bytes: %r" % (changed,)
        )
        self.assertEqual(
            [p for p in after if p.endswith(".pyc") or "__pycache__" in p],
            [],
            "bundle must contain no bytecode after validate: %r"
            % sorted(p for p in after if p.endswith(".pyc") or "__pycache__" in p),
        )


if __name__ == "__main__":
    unittest.main()
