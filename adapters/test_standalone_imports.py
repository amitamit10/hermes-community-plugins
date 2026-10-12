"""Standalone cold-copy import tests (offline, no checkout deps)."""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest


class StandaloneImportsTests(unittest.TestCase):
    def test_browser_tier_imports_standalone_offline(self):
        src = pathlib.Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as outer:
            child_tmpdir = pathlib.Path(outer) / "child-tmp"
            child_tmpdir.mkdir()
            cold = child_tmpdir / "pack"
            cold.mkdir()
            # Cold copy: only adapters/*.py, no other trees.
            for src_file in sorted(src.glob("*.py")):
                shutil.copy2(src_file, cold / src_file.name)
            child_code = "\n".join([
                "import socket",
                "def _blocked(*args, **kwargs):",
                "    raise AssertionError('network disabled during standalone import')",
                "socket.getaddrinfo = _blocked",
                "socket.create_connection = _blocked",
                "_orig_socket = socket.socket",
                "class _NoConnectSocket(_orig_socket):",
                "    def connect(self, *args, **kwargs):",
                "        raise AssertionError('network disabled during standalone import')",
                "socket.socket = _NoConnectSocket",
                "import answer_synth",
                "import anysearch_adapter",
                "import browser_tier",
                "import crawl_pro",
                "import deep_verticals",
                "import donsetch_adapter",
                "import exa_adapter",
                "import firecrawl_adapter",
                "import free_search",
                "import free_stack",
                "import free_verticals",
                "import native_tier",
                "import rss_watcher",
                "import search_filters",
                "import serper_you_adapter",
                "import tavily_adapter",
                "import ssrf_guard",
                "print('standalone pack imports ok')",
            ])
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env["TMPDIR"] = str(child_tmpdir)
            proc = subprocess.run(
                [sys.executable, "-B", "-c", child_code],
                cwd=str(cold),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)


class UrlGateParityTests(unittest.TestCase):
    def test_url_gate_ends_in_precisely_one_newline(self):
        pack = pathlib.Path(__file__).resolve().parent / "url_gate.py"
        self.assertTrue(pack.is_file(), "adapters/url_gate.py is missing")
        raw = pack.read_bytes()
        self.assertEqual(raw, raw.rstrip(b"\n") + b"\n")

    def test_legacy_url_gate_frozen_to_initial_tracked_sha256(self):
        # Freeze the unowned legacy copy: scope forbids synchronizing it with the
        # evolved plugin gate, so byte-parity is obsolete. The file must remain
        # exactly the initially tracked bytes (no scratch dependency).
        import hashlib
        pack = pathlib.Path(__file__).resolve().parent / "url_gate.py"
        self.assertTrue(pack.is_file(), "adapters/url_gate.py is missing")
        expected = "63cf05040adf56dcae807498512c537fb0cead8580de68ae29f303430356eaf5"
        self.assertEqual(hashlib.sha256(pack.read_bytes()).hexdigest(), expected)

    def test_policy_functions_ast_identical_to_trusted_reference(self):
        # Unmodified URL-policy/security definitions must stay identical to the
        # evolved trusted reference. New diagnostics/taxonomy helpers may diverge;
        # these core policy bodies must not.
        import ast
        pack = pathlib.Path(__file__).resolve().parent / "url_gate.py"
        ref = (
            pathlib.Path(__file__).resolve().parents[1]
            / "goat-web"
            / "plugins"
            / "goat-web"
            / "url_gate.py"
        )
        self.assertTrue(ref.is_file(), "trusted url_gate reference is missing: " + str(ref))
        pack_tree = ast.parse(pack.read_text())
        ref_tree = ast.parse(ref.read_text())
        def _defs(tree):
            out = {}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    out[node.name] = ast.dump(node, annotate_fields=False, include_attributes=False)
            return out
        pack_defs = _defs(pack_tree)
        ref_defs = _defs(ref_tree)
        for name in ("_blocked_address", "_numeric_looking_host", "_normalize_host",
                     "_blocked_name", "check_url", "_current_https_url",
                     "check_redirect", "_host_url", "_address_from_answer",
                     "_PinnedHTTPSConnection"):
            self.assertIn(name, pack_defs, "legacy missing " + name)
            self.assertIn(name, ref_defs, "trusted reference missing " + name)
            self.assertEqual(pack_defs[name], ref_defs[name], "policy drift in " + name)
        # Security TLS body: pinned connection must dial the validated IP while
        # authenticating the hostname (Host/SNI pinning preserved).
        ref_src = ref.read_text()
        self.assertIn("server_hostname", ref_src)
        self.assertIn("create_connection", ref_src)
        self.assertIn("wrap_socket", ref_src)

    def test_semantic_policy_parity_allows_only_dns_taxonomy_differences(self):
        # Offline semantic parity: public/private/mixed resolver and redirect
        # policy must agree; ONLY new DNS/timeout taxonomy (DNS_ERROR and the
        # intended UPSTREAM_TIMEOUT for resolver TimeoutError) may differ from
        # the legacy URL_BLOCKED/REDIRECT_BLOCKED. Private/mixed stays block.
        import importlib.util
        import socket as _socket
        pack_path = pathlib.Path(__file__).resolve().parent / "url_gate.py"
        ref_path = (
            pathlib.Path(__file__).resolve().parents[1]
            / "goat-web"
            / "plugins"
            / "goat-web"
            / "url_gate.py"
        )
        def _load(name, path):
            spec = importlib.util.spec_from_file_location(name, str(path))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        legacy = _load("legacy_url_gate_freeze", pack_path)
        trusted = _load("trusted_url_gate_owned", ref_path)
        # check_url / check_redirect agreement on policy cases.
        for url in ("https://example.com/", "https://8.8.8.8/",
                    "http://example.com/", "https://example.com:8080/",
                    "https://user@example.com/", "https://localhost/",
                    "https://127.0.0.1/", "https://[::1]/"):
            self.assertEqual(legacy.check_url(url), trusted.check_url(url), "check_url drift for " + url)
        for current, location, hops in (("https://example.com/", "/next", 0),
                                        ("https://example.com/", "https://other.example/x", 0),
                                        ("https://example.com/", "https://127.0.0.1/x", 0),
                                        ("https://example.com/", "/next", 2)):
            self.assertEqual(legacy.check_redirect(current, location, hops),
                             trusted.check_redirect(current, location, hops),
                             "check_redirect drift for " + repr((current, location, hops)))
        def _code(mod, fn, *args, **kwargs):
            try:
                return ("ok", fn(*args, **kwargs))
            except Exception as exc:
                return ("err", getattr(exc, "code", None))
        def _gai(addr):
            return (_socket.AF_INET, _socket.SOCK_STREAM, 6, "", (addr, 443))
        # Public resolver agrees exactly.
        for mod in (legacy, trusted):
            self.assertEqual(mod.resolve_and_validate("example.com", resolver=lambda h, p, type=0: [_gai("8.8.8.8")]), ["8.8.8.8"])
        # Private and mixed stay policy block on BOTH guards.
        for answers in ([_gai("127.0.0.1")], [_gai("8.8.8.8"), _gai("127.0.0.1")]):
            for mod in (legacy, trusted):
                kind, code = _code(mod, mod.resolve_and_validate, "example.com", resolver=lambda h, p, type=0, _a=answers: list(_a))
                self.assertEqual((kind, code), ("err", "PRIVATE_HOST"))
        # Resolver taxonomy: legacy stays URL_BLOCKED/DNS-free; trusted may use
        # DNS_ERROR (gaierror/empty/OSError) or UPSTREAM_TIMEOUT (TimeoutError).
        # Any other divergence is forbidden.
        cases = [
            ("gaierror", lambda h, p, type=0: (_ for _ in ()).throw(_socket.gaierror(-2, "boom"))),
            ("empty", lambda h, p, type=0: []),
            ("timeout", lambda h, p, type=0: (_ for _ in ()).throw(TimeoutError("boom"))),
            ("oserror", lambda h, p, type=0: (_ for _ in ()).throw(OSError("boom"))),
        ]
        allowed_trusted = {"URL_BLOCKED", "DNS_ERROR", "UPSTREAM_TIMEOUT"}
        for name, resolver in cases:
            with self.subTest(resolver=name):
                lkind, lcode = _code(legacy, legacy.resolve_and_validate, "example.com", resolver=resolver)
                tkind, tcode = _code(trusted, trusted.resolve_and_validate, "example.com", resolver=resolver)
                self.assertEqual(lkind, "err")
                self.assertEqual(tkind, "err")
                self.assertEqual(lcode, "URL_BLOCKED", "legacy resolver must stay URL_BLOCKED for " + name)
                self.assertIn(tcode, allowed_trusted, "trusted resolver drift for " + name)
                if tcode != lcode:
                    self.assertIn(tcode, ("DNS_ERROR", "UPSTREAM_TIMEOUT"), "only DNS/timeout taxonomy may differ for " + name)
        # Malformed answers stay URL_BLOCKED on both (no weakening).
        for mod in (legacy, trusted):
            kind, code = _code(mod, mod.resolve_and_validate, "example.com", resolver=lambda h, p, type=0: ["not-an-address!!"])
            self.assertEqual((kind, code), ("err", "URL_BLOCKED"))
        # Pinned-fetch redirect policy: private/mixed stays REDIRECT_BLOCKED on both.
        class _Resp:
            def __init__(self, status, headers):
                self.status = status
                self._headers = headers
            def read(self, _limit):
                return b"ok"
            def getheaders(self):
                return self._headers
        def _conn_for(responses, seen):
            class _C:
                def __init__(self, hostname, address, timeout=10):
                    seen.append((hostname, address))
                def request(self, *a, **k):
                    pass
                def getresponse(self):
                    s, h = responses.pop(0)
                    return _Resp(s, h)
                def close(self):
                    pass
            return _C
        for mod, modname in ((legacy, "legacy"), (trusted, "trusted")):
            with self.subTest(redirect="private", mod=modname):
                seen = []
                responses = [(302, [("Location", "https://127.0.0.1/private")])]
                orig = mod._PinnedHTTPSConnection
                mod._PinnedHTTPSConnection = _conn_for(list(responses), seen)
                try:
                    kind, code = _code(mod, mod.pinned_fetch, "https://example.com/start", resolver=lambda h, p, type=0: [_gai("8.8.8.8")])
                finally:
                    mod._PinnedHTTPSConnection = orig
                self.assertEqual((kind, code), ("err", "REDIRECT_BLOCKED"))
        # Public-redirect DNS failure: legacy REDIRECT_BLOCKED, trusted DNS_ERROR
        # (taxonomy preserved across the redirect boundary). Only that pair allowed.
        for mod, modname, expected in ((legacy, "legacy", "REDIRECT_BLOCKED"), (trusted, "trusted", "DNS_ERROR")):
            with self.subTest(redirect="public-dns", mod=modname):
                seen = []
                responses = [(302, [("Location", "https://other.example/next")])]
                orig = mod._PinnedHTTPSConnection
                mod._PinnedHTTPSConnection = _conn_for(list(responses), seen)
                def _split(h, p, type=0):
                    if h == "example.com":
                        return [_gai("8.8.8.8")]
                    raise _socket.gaierror(-2, "boom")
                try:
                    kind, code = _code(mod, mod.pinned_fetch, "https://example.com/start", resolver=_split)
                finally:
                    mod._PinnedHTTPSConnection = orig
                self.assertEqual((kind, code), ("err", expected))


if __name__ == "__main__":
    unittest.main()
