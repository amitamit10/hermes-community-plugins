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

    def test_url_gate_bytes_match_trusted_reference_eof_normalized(self):
        pack = pathlib.Path(__file__).resolve().parent / "url_gate.py"
        ref = (
            pathlib.Path(__file__).resolve().parents[1]
            / "goat-web"
            / "plugins"
            / "goat-web"
            / "url_gate.py"
        )
        self.assertTrue(ref.is_file(), "trusted url_gate reference is missing: " + str(ref))
        self.assertTrue(pack.is_file(), "adapters/url_gate.py is missing")
        # EOF-only normalization: every trusted byte preserved except the
        # redundant terminal newline (pack must end in precisely one newline).
        self.assertEqual(pack.read_bytes(), ref.read_bytes().rstrip(b"\n") + b"\n")


if __name__ == "__main__":
    unittest.main()
