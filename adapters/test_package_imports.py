"""Package import RED test (milestone 01b).

Verifies that the canonical ``adapters/`` directory loads as a uniquely
named package (no ``sys.path`` mutation) in a clean ``python -I -S -B``
subprocess running in an unrelated scratch cwd under the authorized
``artifacts/wiring-build/`` root, importing the real ``answer_synth``,
``search_filters``, ``free_stack`` and ``free_verticals`` modules.

Expected state for this RED-only milestone: the package import FAILS
because the current adapter sources use absolute sibling imports
(``from result_contract import ...``, ``from ddg_parser import ...``,
``from ssrf_guard import ...``), which cannot resolve without a flat
directory on ``sys.path`` or top-level aliases. No production change
is made in this milestone.

Also preserves the existing flat-directory usage check (which passes).
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
import uuid

EXPECTED_MODULES = (
    "answer_synth",
    "search_filters",
    "free_stack",
    "free_verticals",
)

TOP_LEVEL_ALIASES_FORBIDDEN = (
    "result_contract",
    "ssrf_guard",
    "ddg_parser",
    "answer_synth",
    "search_filters",
    "free_stack",
    "free_verticals",
    "adapters",
)

_SOCKET_GUARD = "\n".join(
    [
        "import socket",
        "def _blocked(*args, **kwargs):",
        "    raise AssertionError('network disabled during import test')",
        "socket.getaddrinfo = _blocked",
        "socket.create_connection = _blocked",
        "_orig_socket = socket.socket",
        "class _NoConnectSocket(_orig_socket):",
        "    def connect(self, *args, **kwargs):",
        "        raise AssertionError('network disabled during import test')",
        "socket.socket = _NoConnectSocket",
    ]
)

# Child program: load the canonical adapters directory as a uniquely named
# package WITHOUT mutating sys.path, then import the four real modules
# through that package. argv[1] = adapters dir, argv[2] = package name.
_PACKAGE_CHILD_CODE = "\n".join(
    [_SOCKET_GUARD]
    + [
        "import importlib.util",
        "import sys",
        "import types",
        "adapters_dir = sys.argv[1]",
        "pkg_name = sys.argv[2]",
        "before_path = list(sys.path)",
        "pkg = types.ModuleType(pkg_name)",
        "pkg.__path__ = [adapters_dir]",
        "sys.modules[pkg_name] = pkg",
        "loaded = {}",
        "for _name in ('answer_synth', 'search_filters', 'free_stack', 'free_verticals'):",
        "    _fullname = pkg_name + '.' + _name",
        "    _spec = importlib.util.spec_from_file_location(_fullname, adapters_dir + '/' + _name + '.py')",
        "    assert _spec is not None and _spec.loader is not None, 'no spec for ' + _fullname",
        "    _mod = importlib.util.module_from_spec(_spec)",
        "    sys.modules[_fullname] = _mod",
        "    _spec.loader.exec_module(_mod)",
        "    loaded[_name] = _mod",
        "assert callable(loaded['answer_synth'].goat_answer), 'answer_synth.goat_answer missing'",
        "assert callable(loaded['search_filters'].with_search_filters), 'search_filters.with_search_filters missing'",
        "assert callable(loaded['free_stack'].wikipedia_search), 'free_stack.wikipedia_search missing'",
        "assert callable(loaded['free_verticals'].register), 'free_verticals.register missing'",
        "assert list(sys.path) == before_path, 'child mutated sys.path: %r -> %r' % (before_path, list(sys.path))",
        "for _alias in ('result_contract', 'ssrf_guard', 'ddg_parser', 'answer_synth', 'search_filters', 'free_stack', 'free_verticals', 'adapters'):",
        "    assert _alias not in sys.modules, 'top-level alias present: ' + _alias",
        "print('package imports ok')",
    ]
)

# Child program: existing flat-directory usage (cwd on sys.path).
_FLAT_CHILD_CODE = "\n".join(
    [_SOCKET_GUARD]
    + [
        "import answer_synth",
        "import search_filters",
        "import free_stack",
        "import free_verticals",
        "assert callable(answer_synth.goat_answer)",
        "assert callable(search_filters.with_search_filters)",
        "assert callable(free_stack.wikipedia_search)",
        "assert callable(free_verticals.register)",
        "print('flat imports ok')",
    ]
)


def _wiring_build_root():
    # adapters/test_package_imports.py -> wiring/ -> work-root -> artifacts/wiring-build/
    wiring_root = pathlib.Path(__file__).resolve().parent.parent
    return wiring_root.parent / "artifacts" / "wiring-build"


def _sanitized_env(tmpdir):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["TMPDIR"] = str(tmpdir)
    return env


class PackageImportTests(unittest.TestCase):
    def test_canonical_adapters_load_as_unique_package(self):
        """RED: canonical adapters must import as a package without sys.path edits."""
        adapters_dir = pathlib.Path(__file__).resolve().parent
        build_root = _wiring_build_root()
        build_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="pkg-import-", dir=str(build_root)
        ) as tmp:
            scratch = pathlib.Path(tmp) / "child-cwd"
            scratch.mkdir()
            pkg_name = "goat_adapters_pkg_" + uuid.uuid4().hex
            proc = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    _PACKAGE_CHILD_CODE,
                    str(adapters_dir),
                    pkg_name,
                ],
                cwd=str(scratch),
                env=_sanitized_env(tmp),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                proc.returncode,
                0,
                "package import failed:\nSTDOUT:\n"
                + proc.stdout
                + "\nSTDERR:\n"
                + proc.stderr,
            )
            self.assertIn("package imports ok", proc.stdout)


class FlatDirectoryUseTests(unittest.TestCase):
    def test_flat_directory_imports_still_work(self):
        """Existing usage: top-level sibling imports with the adapters dir as cwd."""
        adapters_dir = pathlib.Path(__file__).resolve().parent
        build_root = _wiring_build_root()
        build_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="flat-import-", dir=str(build_root)
        ) as tmp:
            # Mirror the existing standalone style: plain -B with the
            # adapters directory as cwd (no -I/-S, so cwd stays importable).
            proc = subprocess.run(
                [sys.executable, "-B", "-c", _FLAT_CHILD_CODE],
                cwd=str(adapters_dir),
                env=_sanitized_env(tmp),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                proc.returncode,
                0,
                "flat-directory import failed:\nSTDOUT:\n"
                + proc.stdout
                + "\nSTDERR:\n"
                + proc.stderr,
            )
            self.assertIn("flat imports ok", proc.stdout)


if __name__ == "__main__":
    unittest.main()
