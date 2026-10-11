"""Startup preflight wrapper contract (companion OUTSIDE bundle)."""
import contextlib
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "goat-web" / "scripts" / "start_with_preflight.py"
BUILD_SCRIPT = ROOT / "goat-web" / "scripts" / "build_plugin_bundle.py"
BUILD_ROOT = ROOT.parent / "artifacts" / "wiring-build"

EXPECTED_CONSENT = (
    "GOAT preflight refused: network check not consented; "
    "re-run with --allow-network --bundle <verified-bundle> -- <hermes args> "
    "to opt in to a single https://example.com probe before Hermes starts."
)
EXPECTED_FAILURE = (
    "GOAT preflight failed: environment cannot support pinned fetch to https://example.com; "
    "production use requires direct egress with public DNS replies and direct HTTPS/443 with TLS; "
    "mandatory-proxy, private/synthetic/mixed DNS, and restricted egress are unsupported with no proxy fallback; "
    "this may also be a transient outage; "
    "success at this fixed endpoint does not prove general Internet or provider access; "
    "not starting Hermes."
)
EXPECTED_RECEIPT = (
    "GOAT preflight passed: https://example.com via pinned_fetch; "
    "starting Hermes; this endpoint is not proof of all providers."
)
SEVEN = {"goat_search", "goat_extract", "goat_crawl", "goat_probe",
         "goat_answer", "goat_filtered_search", "goat_vertical_search"}
PROXY_ENV = {"http_proxy": "http://proxy.invalid:8080", "https_proxy": "http://proxy.invalid:8080",
             "HTTP_PROXY": "http://proxy.invalid:8080", "HTTPS_PROXY": "http://proxy.invalid:8080",
             "ALL_PROXY": "http://proxy.invalid:8080", "all_proxy": "http://proxy.invalid:8080",
             "NO_PROXY": "", "no_proxy": ""}


def _load_wrapper():
    name = "goat_startup_preflight_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            spec.loader.exec_module(mod)
        assert out.getvalue() == "" and err.getvalue() == ""
        return name, mod
    except BaseException:
        sys.modules.pop(name, None)
        raise


def _drop(prefix):
    for k in tuple(sys.modules):
        if k == prefix or k.startswith(prefix + "."):
            sys.modules.pop(k, None)


def _bundle_mods():
    return {k for k in sys.modules if k.startswith("goat_preflight_bundle_")}


def _load_builder():
    name = "goat_preflight_builder_" + uuid.uuid4().hex
    spec = importlib.util.spec_from_file_location(name, BUILD_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(name, None)
        raise
    sys.modules.pop(name, None)
    return mod


def _build_bundle(case):
    import shutil
    import tempfile
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="goat-preflight-", dir=str(BUILD_ROOT))
    case.addCleanup(shutil.rmtree, tmp, True)
    out = Path(tmp) / "hermes-goat-web"
    _load_builder().build_bundle(ROOT, out)
    return out


def _gai(addr):
    return (2, 1, 6, "", (addr, 443))


class _Resp:
    def __init__(self, status=200, body=b"ok"):
        self.status = status
        self._b = body

    def read(self, _l):
        return self._b

    def getheaders(self):
        return []


def _conn_class(calls, status=200, body=b"ok", exc=None):
    class C:
        def __init__(self, hostname, address, timeout=10):
            calls["constructed"].append((hostname, address))

        def request(self, method, path, headers=None):
            calls["requested"].append((method, path, headers))

        def getresponse(self):
            if exc is not None:
                raise exc
            return _Resp(status, body)

        def close(self):
            pass

    return C


def _pinned_transport(case, addrs=None, dns_exc=None, status=200, body=b"ok", conn_exc=None):
    pkg = "goat_preflight_helper_" + uuid.uuid4().hex
    bdir = _build_bundle(case)
    spec = importlib.util.spec_from_file_location(
        pkg, bdir / "__init__.py", submodule_search_locations=[str(bdir)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[pkg] = mod
    case.addCleanup(_drop, pkg)
    spec.loader.exec_module(mod)
    import importlib as _il
    url_gate = _il.import_module(pkg + ".url_gate")
    calls = {"resolver": [], "constructed": [], "requested": []}
    def resolver(host, port, *a, **k):
        calls["resolver"].append((host, port))
        if dns_exc is not None:
            raise dns_exc
        return [_gai(x) for x in addrs]
    conn = _conn_class(calls, status=status, body=body, exc=conn_exc)
    def transport(url):
        with mock.patch.object(url_gate, "_PinnedHTTPSConnection", conn):
            return url_gate.pinned_fetch(url, resolver=resolver)
    return transport, calls


def _run(wmod, argv, _exec=None, _transport=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        kw = {}
        if _exec is not None:
            kw["_exec"] = _exec
        if _transport is not None:
            kw["_transport"] = _transport
        rc = wmod.main(argv, **kw)
    return rc, out.getvalue(), err.getvalue()


class DefaultTests(unittest.TestCase):
    def test_exists_and_default_refuses(self):
        self.assertTrue(SCRIPT.is_file())
        _n, wmod = _load_wrapper()
        try:
            fake = str(ROOT.parent / "artifacts" / "test-scratch" / "no-such-bundle")
            before = _bundle_mods()
            with mock.patch.object(os, "execvp", side_effect=AssertionError()), \
                mock.patch("importlib.util.spec_from_file_location", side_effect=AssertionError()), \
                mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError()), \
                mock.patch.object(socket, "gethostbyname", side_effect=AssertionError()), \
                mock.patch.object(socket, "gethostbyaddr", side_effect=AssertionError()), \
                mock.patch.object(socket, "getnameinfo", side_effect=AssertionError()):
                rc, out, err = _run(wmod, ["--bundle", fake, "--", "chat"])
            self.assertNotEqual(rc, 0)
            self.assertEqual(out, "")
            self.assertEqual(err.strip().splitlines(), [EXPECTED_CONSENT])
            self.assertEqual(_bundle_mods() - before, set())
        finally:
            _drop(_n)
        self.assertNotIn(_n, sys.modules)


class SuccessTests(unittest.TestCase):
    def test_receipt_then_exec(self):
        bundle = _build_bundle(self)
        _n, wmod = _load_wrapper()
        try:
            order = []
            t, calls = _pinned_transport(self, addrs=["93.184.216.34"])
            def counting(url):
                order.append("probe")
                return t(url)
            def fake_exec(p, a):
                order.append("exec")
                self.assertEqual(a, ["hermes", "chat", "--foo", "bar"])
                return 0
            with mock.patch.object(socket, "gethostbyname", side_effect=AssertionError()), \
                mock.patch.object(socket, "gethostbyaddr", side_effect=AssertionError()), \
                mock.patch.object(socket, "getnameinfo", side_effect=AssertionError()):
                rc, out, err = _run(wmod, ["--bundle", str(bundle), "--allow-network",
                                           "--", "chat", "--foo", "bar"],
                                    _exec=fake_exec, _transport=counting)
            self.assertEqual(rc, 0)
            self.assertEqual(out, "")
            self.assertEqual(err.strip().splitlines(), [EXPECTED_RECEIPT])
            self.assertEqual(order, ["probe", "exec"])
            self.assertEqual(calls["resolver"], [("example.com", 443)])
            self.assertEqual(len(calls["constructed"]), 1)
            self.assertEqual(len(calls["requested"]), 1)
        finally:
            _drop(_n)

    def test_default_route_real_fetch_no_global_socket_patch(self):
        import functools
        bundle = _build_bundle(self)
        _n, wmod = _load_wrapper()
        try:
            import importlib as _il
            probe, pkg = wmod._load_bundle_probe(str(bundle))
            self.assertTrue(callable(probe))
            self.addCleanup(_drop, pkg)
            tools = _il.import_module(pkg + ".goat_tools")
            ug = _il.import_module(pkg + ".url_gate")
            calls = {"resolver": [], "constructed": [], "requested": []}
            def fake_resolver(host, port, *a, **k):
                calls["resolver"].append((host, port))
                return [_gai("93.184.216.34")]
            tools.pinned_fetch = functools.partial(ug.pinned_fetch, resolver=fake_resolver)
            orig = probe
            seen = {}
            def inner(url, *a, **k):
                self.assertNotIn("transport", k)
                self.assertEqual(a, ())
                seen["url"] = url
                return orig(url)
            with mock.patch.object(ug, "_PinnedHTTPSConnection", _conn_class(calls)):
                with mock.patch.object(wmod, "_load_bundle_probe", return_value=(inner, pkg)):
                    execs = []
                    with mock.patch.dict(os.environ, PROXY_ENV):
                        rc, out, err = _run(
                            wmod, ["--bundle", str(bundle), "--allow-network",
                                   "--", "gateway", "run"],
                            _exec=lambda p, a: execs.append(list(a)) or 0)
            self.assertEqual(rc, 0)
            self.assertEqual(seen.get("url"), "https://example.com")
            self.assertEqual(out, "")
            self.assertEqual(err.strip().splitlines(), [EXPECTED_RECEIPT])
            self.assertEqual(execs, [["hermes", "gateway", "run"]])
            self.assertEqual(calls["resolver"], [("example.com", 443)])
            self.assertEqual(calls["constructed"], [("example.com", "93.184.216.34")])
            self.assertEqual(len(calls["requested"]), 1)
        finally:
            _drop(_n)


class FailureTests(unittest.TestCase):
    def _fail(self, transport=None, loader_result=None, hermes=("chat",), env=None):
        bundle = _build_bundle(self)
        _n, wmod = _load_wrapper()
        try:
            calls = []
            def no_exec(p, a):
                calls.append((p, a))
                raise AssertionError("no exec")
            args = ["--bundle", str(bundle), "--allow-network", "--"] + list(hermes)
            if loader_result is not None:
                with mock.patch.object(wmod, "_load_bundle_probe", return_value=loader_result):
                    with mock.patch.dict(os.environ, env or {}):
                        rc, out, err = _run(wmod, args, _exec=no_exec)
            else:
                with mock.patch.dict(os.environ, env or {}):
                    rc, out, err = _run(wmod, args, _exec=no_exec, _transport=transport)
            self.assertNotEqual(rc, 0)
            self.assertEqual(calls, [])
            self.assertEqual(out, "")
            self.assertEqual(err.strip().splitlines(), [EXPECTED_FAILURE])
            return err
        finally:
            _drop(_n)

    def test_private_mixed_no_connection(self):
        for addrs in (["10.0.0.5"], ["93.184.216.34", "192.168.1.7"]):
            with self.subTest(addrs=addrs):
                t, calls = _pinned_transport(self, addrs=addrs)
                err = self._fail(transport=t, env=PROXY_ENV)
                self.assertEqual(calls["constructed"], [])
                self.assertEqual(calls["requested"], [])
                self.assertEqual(len(calls["resolver"]), 1)
                for ip in addrs:
                    self.assertNotIn(ip, err)

    def test_dns_tls_http500(self):
        t, _ = _pinned_transport(self, dns_exc=OSError("dns down SECRET-XYZ"))
        self.assertNotIn("SECRET-XYZ", self._fail(transport=t, hermes=("gateway", "run")))
        t2, _ = _pinned_transport(self, addrs=["93.184.216.34"], conn_exc=OSError("tls down"))
        self.assertNotIn("proxy.invalid", self._fail(transport=t2, env=PROXY_ENV))
        t3, _ = _pinned_transport(self, addrs=["93.184.216.34"], status=500, body=b"x password=hunter2")
        self.assertNotIn("hunter2", self._fail(transport=t3, hermes=("gateway", "run")))

    def test_malformed_probe_result(self):
        # Coverage-first: strict validator already rejects these; loader fakes, no live calls.
        bad_cases = [None, "x", [1], 200, {}, {"ok": True},
                     {"status": 200, "host": "example.com"}, {"ok": True, "status": 200},
                     {"ok": True, "host": "example.com"}, {"ok": True, "status": 200, "host": "example.com",
                                                           "error": {"code": "X"}},
                     {"ok": True, "status": 200, "host": "example.com", "error": {}},
                     {"ok": True, "status": 200, "host": "evil.example", "error": None},
                     {"ok": True, "status": 200, "host": "", "error": None},
                     {"ok": True, "status": 200, "host": None, "error": None},
                     {"ok": True, "status": True, "host": "example.com", "error": None},
                     {"ok": True, "status": "200", "host": "example.com", "error": None},
                     {"ok": True, "status": 199, "host": "example.com", "error": None},
                     {"ok": True, "status": 300, "host": "example.com", "error": None},
                     {"ok": True, "status": 500, "host": "example.com", "error": None},
                     {"ok": True, "status": 0, "host": "example.com", "error": None},
                     {"ok": False, "status": 200, "host": "example.com", "error": None}]
        for bad in bad_cases:
            with self.subTest(bad=bad):
                err = self._fail(loader_result=(lambda *a, **k: bad, "fake-pkg"))
                self.assertNotIn("evil", err)
        _n, wmod = _load_wrapper()
        try:
            self.assertTrue(wmod._probe_ok({"ok": True, "status": 200, "host": "example.com"}))
            self.assertTrue(wmod._probe_ok({"ok": True, "status": 204, "host": "example.com"}))
            self.assertTrue(wmod._probe_ok({"ok": True, "status": 299, "host": "example.com"}))
        finally:
            _drop(_n)


class LoaderTests(unittest.TestCase):
    def _rejected(self, bundle_path, leak_check=True):
        _n, wmod = _load_wrapper()
        try:
            before = _bundle_mods()
            with mock.patch.object(os, "execvp", side_effect=AssertionError("no exec")), \
                mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("no DNS before load error")), \
                mock.patch.object(socket, "gethostbyname", side_effect=AssertionError("no DNS")), \
                mock.patch.object(socket, "gethostbyaddr", side_effect=AssertionError("no DNS")), \
                mock.patch.object(socket, "getnameinfo", side_effect=AssertionError("no DNS")):
                rc, out, err = _run(wmod, ["--bundle", str(bundle_path), "--allow-network",
                                           "--", "chat"], _exec=lambda p, a: None)
            self.assertNotEqual(rc, 0)
            self.assertEqual(out, "")
            self.assertEqual(err.strip().splitlines(), [wmod.BUNDLE_ERROR])
            if leak_check:
                self.assertEqual(_bundle_mods() - before, set())
            return err
        finally:
            _drop(_n)

    def test_missing_manifest_rejected(self):
        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="goat-nomanifest-", dir=str(BUILD_ROOT)))
        self.addCleanup(shutil.rmtree, str(tmp), True)
        (tmp / "__init__.py").write_text("X = 1\n", encoding="utf-8")
        (tmp / "goat_tools.py").write_text("def goat_probe(url): return {}\n", encoding="utf-8")
        self._rejected(tmp)

    def test_source_template_rejected(self):
        self._rejected(ROOT / "goat-web" / "plugins" / "goat-web")

    def test_corrupt_bundle_rejected_without_leak(self):
        import shutil
        import tempfile
        good = _build_bundle(self)
        parent = Path(tempfile.mkdtemp(prefix="goat-corrupt-", dir=str(BUILD_ROOT)))
        self.addCleanup(shutil.rmtree, str(parent), True)
        bad = parent / "hermes-goat-web"
        shutil.copytree(good, bad)
        (bad / "goat_tools.py").write_text("raise RuntimeError('corrupt-bundle-marker')\n", encoding="utf-8")
        err = self._rejected(bad)
        self.assertNotIn("corrupt-bundle-marker", err)

    def test_wrapper_import_leaves_no_trace(self):
        _n, wmod = _load_wrapper()
        self.assertIn(_n, sys.modules)
        _drop(_n)
        self.assertNotIn(_n, sys.modules)
        builder = _load_builder()
        self.assertTrue(callable(builder.build_bundle))
        self.assertEqual([k for k in sys.modules if k.startswith("goat_preflight_builder_")], [])


class EdgeTests(unittest.TestCase):
    def test_help_bundle_exec_inventory(self):
        _n, wmod = _load_wrapper()
        try:
            with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError()), \
                mock.patch.object(os, "execvp", side_effect=AssertionError()):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    with self.assertRaises(SystemExit) as ctx:
                        wmod.main(["--help"])
                self.assertEqual(ctx.exception.code, 0)
                self.assertIn("--bundle", out.getvalue())
            with mock.patch.object(os, "execvp", side_effect=AssertionError()):
                rc, out, err = _run(wmod, ["--bundle", "/no/such/b-xyz", "--allow-network", "--", "chat"])
            self.assertNotEqual(rc, 0)
            self.assertEqual(err.strip().splitlines(), [wmod.BUNDLE_ERROR])
            self.assertNotIn("xyz", err)
            bundle = _build_bundle(self)
            t, _ = _pinned_transport(self, addrs=["93.184.216.34"])
            def boom(p, a):
                raise OSError("exec down SECRET-E")
            rc, out, err = _run(wmod, ["--bundle", str(bundle), "--allow-network",
                                      "--", "gateway", "run"], _exec=boom, _transport=t)
            lines = err.strip().splitlines()
            self.assertEqual(lines, [EXPECTED_RECEIPT, wmod.EXEC_ERROR])
            self.assertNotIn("SECRET-E", err)
            seen = {}
            rc, out, err = _run(wmod, ["--bundle", str(bundle), "--allow-network",
                                      "--", "gateway", "run", "--port", "7777"],
                                _exec=lambda p, a: seen.setdefault("a", a) or 0, _transport=t)
            self.assertEqual(seen["a"], ["hermes", "gateway", "run", "--port", "7777"])
            found = {str((Path(c) / n).relative_to(bundle)) for c, _, fs in os.walk(bundle) for n in fs}
            self.assertNotIn("start_with_preflight.py", found)
            pkg = "goat_preflight_edge_" + uuid.uuid4().hex
            spec = importlib.util.spec_from_file_location(
                pkg, bundle / "__init__.py", submodule_search_locations=[str(bundle)])
            mod = importlib.util.module_from_spec(spec)
            sys.modules[pkg] = mod
            try:
                spec.loader.exec_module(mod)
                tools = {}
                class Ctx:
                    def register_tool(self, **kw):
                        tools[kw["name"]] = kw
                mod.register(Ctx())
                self.assertEqual(set(tools), SEVEN)
                for tool in tools.values():
                    self.assertIs(tool["schema"]["parameters"]["additionalProperties"], False)
            finally:
                _drop(pkg)
        finally:
            _drop(_n)


_CHILD_HARNESS = r'''
import sys as _s
_W = {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyaddr",
      "socket.getnameinfo", "socket.connect", "socket.__new__"}
_A = []
def _h(_e, _a):
    if _e in _W:
        try:
            _r = repr(_a)[:120]
        except Exception:
            _r = "?"
        _A.append([_e, _r])
        raise RuntimeError("child-blocked:" + _e)
_s.addaudithook(_h)
import json as _j, os as _o, io as _i, contextlib as _c
_mode = _s.argv[1]
def _emit(_o2):
    _o2["attempts"] = _A
    _o2["argv"] = _s.argv[1:]
    _o2["cwd"] = _o.getcwd()
    print(_j.dumps(_o2))
if _mode == "selfcheck":
    _ok = False
    try:
        _h("socket.getaddrinfo", ("example.com", 443))
    except RuntimeError:
        _ok = len(_A) == 1
    _emit({"mode": "selfcheck", "ok": _ok})
    raise SystemExit(0 if _ok else 1)
elif _mode == "runpy":
    import runpy as _r
    _script, _sargs = _s.argv[2], _j.loads(_s.argv[3])
    _so, _se, _code = _i.StringIO(), _i.StringIO(), 0
    _s.argv = [_script] + _sargs
    try:
        with _c.redirect_stdout(_so), _c.redirect_stderr(_se):
            _r.run_path(_script, run_name="__main__")
    except SystemExit as _e:
        _code = _e.code if isinstance(_e.code, int) else (0 if _e.code is None else 2)
    except BaseException as _e:
        _code = 99
        _se.write("harness-error: %r" % (_e,))
    _emit({"mode": "runpy", "exit": _code, "stdout": _so.getvalue(), "stderr": _se.getvalue(), "ok": True})
else:
    import importlib.util as _ilu, uuid as _uu
    from functools import partial as _pt
    _wpath, _bdir = _s.argv[2], _s.argv[3]
    _out = {"mode": "scenario", "ok": False}
    try:
        _wn = "goat_child_wrapper_" + _uu.uuid4().hex
        _spec = _ilu.spec_from_file_location(_wn, _wpath)
        _wm = _ilu.module_from_spec(_spec)
        _s.modules[_wn] = _wm
        _spec.loader.exec_module(_wm)
        _CONS, _FAIL, _RCPT = _wm.CONSENT_REFUSAL, _wm.PREFLIGHT_FAILURE, _wm.SUCCESS_RECEIPT
        _xcalls = []
        def _noexec(p, a):
            _xcalls.append([p, list(a)])
            raise AssertionError("child-no-exec")
        def _call(_args, **_kw):
            _so, _se = _i.StringIO(), _i.StringIO()
            with _c.redirect_stdout(_so), _c.redirect_stderr(_se):
                _rc = _wm.main(_args, **_kw)
            return _rc, _so.getvalue(), _se.getvalue()
        _rc, _co, _ce = _call(["--bundle", "/nonexistent-child-xyz", "--", "chat"], _exec=_noexec)
        assert _rc != 0 and _co == "" and _ce.strip().splitlines() == [_CONS], ("default", _rc, _ce)
        assert [k for k in _s.modules if k.startswith("goat_preflight_bundle_")] == []
        _out["default"] = True
        _probe, _pkg = _wm._load_bundle_probe(_bdir)
        assert callable(_probe)
        import importlib as _im
        _tools = _im.import_module(_pkg + ".goat_tools")
        _ug = _im.import_module(_pkg + ".url_gate")
        _tmap = {}
        class _Cx:
            def register_tool(self, **kw):
                _tmap[kw["name"]] = kw
        _im.import_module(_pkg).register(_Cx())
        assert set(_tmap) == {"goat_search", "goat_extract", "goat_crawl", "goat_probe",
                              "goat_answer", "goat_filtered_search", "goat_vertical_search"}
        for _tv in _tmap.values():
            assert _tv["schema"]["parameters"]["additionalProperties"] is False
        _out["seven"] = True
        _pub = [(2, 1, 6, "", ("93.184.216.34", 443))]
        _sc = {"resolver": [], "constructed": [], "requested": []}
        def _fres(h, p, *a, **k):
            _sc["resolver"].append([h, p])
            return list(_pub)
        class _FR:
            status = 200
            def read(self, _l):
                return b"ok"
            def getheaders(self):
                return []
        class _FC:
            def __init__(s, hn, ad, timeout=10):
                _sc["constructed"].append([hn, ad])
            def request(s, m, p, headers=None):
                _sc["requested"].append([m, p])
            def getresponse(s):
                return _FR()
            def close(s):
                pass
        _tools.pinned_fetch = _pt(_ug.pinned_fetch, resolver=_fres)
        _ug._PinnedHTTPSConnection = _FC
        _orig = _probe
        _seen = {}
        def _spy(u, *a, **k):
            assert "transport" not in k and not a and u == "https://example.com", (u, a, k)
            _seen["url"] = u
            return _orig(u)
        _wm._load_bundle_probe = lambda b: (_spy, _pkg)
        _o.environ.update({"http_proxy": "http://proxy.invalid:8080", "https_proxy": "http://proxy.invalid:8080",
                           "HTTP_PROXY": "http://proxy.invalid:8080", "HTTPS_PROXY": "http://proxy.invalid:8080",
                           "ALL_PROXY": "http://proxy.invalid:8080", "all_proxy": "http://proxy.invalid:8080"})
        _order = []
        def _sp2(u, *a, **k):
            _order.append("probe")
            return _spy(u, *a, **k)
        _wm._load_bundle_probe = lambda b: (_sp2, _pkg)
        _ex = {}
        def _okx(p, a):
            _order.append("exec")
            _ex["argv"] = list(a)
            return 0
        _rc, _co, _ce = _call(["--bundle", _bdir, "--allow-network", "--", "chat", "--x", "1"], _exec=_okx)
        assert _rc == 0, (_rc, _ce)
        assert _co == "" and _ce.strip().splitlines() == [_RCPT], repr(_ce)
        assert _order == ["probe", "exec"] and _ex["argv"] == ["hermes", "chat", "--x", "1"]
        assert _sc["resolver"] == [["example.com", 443]] and len(_sc["constructed"]) == 1
        assert len(_sc["requested"]) == 1
        _out["success"] = {"resolver": 1, "constructed": 1, "requested": 1}
        for _ad in (["10.0.0.5"], ["93.184.216.34", "192.168.1.7"]):
            _fc = {"resolver": [], "constructed": [], "requested": []}
            def _fr2(h, p, *a, **k):
                _fc["resolver"].append([h, p])
                return [(2, 1, 6, "", (_ip, 443)) for _ip in _ad]
            class _FC2:
                def __init__(s, *a, **k):
                    _fc["constructed"].append(True)
                def request(s, *a, **k):
                    _fc["requested"].append(True)
                def getresponse(s):
                    raise AssertionError("unreachable")
                def close(s):
                    pass
            _tools.pinned_fetch = _pt(_ug.pinned_fetch, resolver=_fr2)
            _ug._PinnedHTTPSConnection = _FC2
            _rc, _co, _ce = _call(["--bundle", _bdir, "--allow-network", "--", "chat"], _exec=_noexec)
            assert _rc != 0 and _co == "" and _ce.strip().splitlines() == [_FAIL], (_rc, _ce)
            assert _fc["constructed"] == [] and _fc["requested"] == [] and len(_fc["resolver"]) == 1
            assert _xcalls == []
        _out["failure"] = True
        assert _A == [], _A
        _out["ok"] = True
    except BaseException as _e:
        import traceback as _tb
        _out["ok"] = False
        _out["error"] = "%r" % (_e,)
        _out["trace"] = _tb.format_exc()[-2000:]
    _emit(_out)
    raise SystemExit(0 if _out["ok"] else 1)
'''


class FreshExportTests(unittest.TestCase):
    def test_fresh_export_audited_children(self):
        import shutil
        import tarfile
        import tempfile
        import io as _io
        base = Path(tempfile.mkdtemp(prefix="goat-fresh-", dir=str(BUILD_ROOT)))
        self.addCleanup(shutil.rmtree, str(base), True)
        cp = subprocess.run(["git", "archive", "1311d89a76adeb3d4b56e281014991ee3a83f3f5"],
                            cwd=str(ROOT), capture_output=True, timeout=60, check=False)
        self.assertEqual(cp.returncode, 0)
        with tarfile.open(fileobj=_io.BytesIO(cp.stdout)) as tf:
            tf.extractall(path=str(base))
        for rel in ("goat-web/scripts/start_with_preflight.py", "goat-web/tests/test_startup_preflight.py"):
            dst = base / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes((ROOT / rel).read_bytes())
        out_dir = base.parent / (base.name + "-bundle")
        self.addCleanup(shutil.rmtree, str(out_dir), True)
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
               "HOME": str(BUILD_ROOT), "HERMES_HOME": str(BUILD_ROOT),
               "XDG_CACHE_HOME": str(BUILD_ROOT), "XDG_CONFIG_HOME": str(BUILD_ROOT),
               "XDG_DATA_HOME": str(BUILD_ROOT), "XDG_STATE_HOME": str(BUILD_ROOT),
               "TMPDIR": str(BUILD_ROOT), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
               "PYTHONDONTWRITEBYTECODE": "1", "HERMES_DEV": "1",
               "HERMES_DISABLE_LAZY_INSTALLS": "1", "HERMES_ENABLE_PROJECT_PLUGINS": "0"}
        script = base / "goat-web" / "scripts" / "build_plugin_bundle.py"
        wrap = base / "goat-web" / "scripts" / "start_with_preflight.py"

        def child(*hargs, timeout=60):
            r = subprocess.run(["python3", "-I", "-S", "-B", "-c", _CHILD_HARNESS] + list(hargs),
                               env=env, cwd=str(base), capture_output=True, text=True,
                               timeout=timeout, check=False)
            self.assertEqual(r.returncode, 0, "harness mode %r crashed rc=%s err=%r" % (
                hargs[0], r.returncode, r.stderr[-2000:]))
            try:
                payload = json.loads(r.stdout)
            except ValueError:
                self.fail("child %r emitted no JSON: stdout=%r stderr=%r" % (
                    hargs[0], r.stdout[-1000:], r.stderr[-1000:]))
            return payload

        pb = child("runpy", str(script), json.dumps(["--output", str(out_dir)]), timeout=120)
        self.assertEqual(pb["exit"], 0, pb["stderr"])
        self.assertEqual(pb["attempts"], [])
        pc = child("runpy", str(script), json.dumps(["--check", str(out_dir)]), timeout=60)
        self.assertEqual(pc["exit"], 0, pc["stderr"])
        self.assertEqual(pc["attempts"], [])
        self.assertFalse((out_dir / "start_with_preflight.py").exists())
        ph = child("runpy", str(wrap), json.dumps(["--help"]), timeout=30)
        self.assertEqual(ph["exit"], 0)
        self.assertIn("--bundle", ph["stdout"])
        self.assertEqual(ph["attempts"], [])
        pd = child("runpy", str(wrap), json.dumps(["--bundle", str(out_dir), "--", "chat"]), timeout=30)
        self.assertNotEqual(pd["exit"], 0)
        self.assertEqual(pd["stdout"], "")
        self.assertEqual(pd["stderr"].strip().splitlines(), [EXPECTED_CONSENT])
        self.assertEqual(pd["attempts"], [])
        ps = child("selfcheck", timeout=30)
        self.assertTrue(ps["ok"])
        self.assertEqual(len(ps["attempts"]), 1)
        psc = child("scenario", str(wrap), str(out_dir), timeout=120)
        self.assertTrue(psc["ok"], psc.get("error"))
        self.assertEqual(psc["attempts"], [])
        self.assertTrue(psc["seven"])
        self.assertEqual(psc["success"], {"resolver": 1, "constructed": 1, "requested": 1})
        self.assertTrue(psc["failure"])
        self.assertTrue(psc["default"])


if __name__ == "__main__":
    unittest.main()
