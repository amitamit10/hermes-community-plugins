"""Portable bundle builder tests (Milestone 06, TDD).

Build outputs live ONLY under ../artifacts/wiring-build/.
All builder invocations go through the real command line.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BUILD_SCRIPT = ROOT / "goat-web" / "scripts" / "build_plugin_bundle.py"
ARTIFACTS_BUILD = ROOT.parent / "artifacts" / "wiring-build"

PLUGIN_SOURCES = [
    "goat-web/plugins/goat-web/__init__.py",
    "goat-web/plugins/goat-web/goat_tools.py",
    "goat-web/plugins/goat-web/adapters.py",
    "goat-web/plugins/goat-web/url_gate.py",
    "goat-web/plugins/goat-web/tool_schemas.py",
    "goat-web/plugins/goat-web/v3_wiring.py",
    "goat-web/plugins/goat-web/plugin.yaml",
]

VENDOR_SOURCES = [
    "adapters/answer_synth.py",
    "adapters/search_filters.py",
    "adapters/free_verticals.py",
    "adapters/free_stack.py",
    "adapters/ssrf_guard.py",
    "adapters/ddg_parser.py",
    "adapters/result_contract.py",
]

OTHER_SOURCES = [
    "goat-web/hermes-goat-web.plugin.json",
    "goat-web/LICENSE",
    "adapters/LICENSE",
    "adapters/PROVENANCE.md",
]

EXPECTED_FILES = {
    "__init__.py",
    "goat_tools.py",
    "adapters.py",
    "url_gate.py",
    "tool_schemas.py",
    "v3_wiring.py",
    "plugin.yaml",
    "_goat_v3_vendor/answer_synth.py",
    "_goat_v3_vendor/search_filters.py",
    "_goat_v3_vendor/free_verticals.py",
    "_goat_v3_vendor/free_stack.py",
    "_goat_v3_vendor/ssrf_guard.py",
    "_goat_v3_vendor/ddg_parser.py",
    "_goat_v3_vendor/result_contract.py",
    "_goat_v3_vendor/__init__.py",
    "hermes-goat-web.plugin.json",
    "LICENSE",
    "VENDOR-LICENSE",
    "VENDOR-PROVENANCE.md",
    "bundle-manifest.json",
}

SOURCE_OF_OUTPUT = {}
for _rel in PLUGIN_SOURCES:
    SOURCE_OF_OUTPUT[Path(_rel).name] = _rel
for _rel in VENDOR_SOURCES:
    SOURCE_OF_OUTPUT["_goat_v3_vendor/" + Path(_rel).name] = _rel
SOURCE_OF_OUTPUT["hermes-goat-web.plugin.json"] = (
    "goat-web/hermes-goat-web.plugin.json"
)
SOURCE_OF_OUTPUT["LICENSE"] = "goat-web/LICENSE"
SOURCE_OF_OUTPUT["VENDOR-LICENSE"] = "adapters/LICENSE"
SOURCE_OF_OUTPUT["VENDOR-PROVENANCE.md"] = "adapters/PROVENANCE.md"

FORBIDDEN_BUNDLE_NAMES = [
    "anysearch_adapter.py",
    "tavily_adapter.py",
    "exa_adapter.py",
    "firecrawl_adapter.py",
    "serper_you_adapter.py",
    "donsetch_adapter.py",
    "native_tier.py",
    "browser_tier.py",
    "crawl_pro.py",
    "deep_verticals.py",
    "rss_watcher.py",
    "free_search.py",
    "test_result_contract.py",
    "ssrf_guard.pyi",
]


def _run_builder(*args):
    return subprocess.run(
        [sys.executable, "-B", str(BUILD_SCRIPT)] + list(args),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _fresh_dir(test_name):
    base = ARTIFACTS_BUILD / "t" / test_name
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    return base


def _build(name):
    base = _fresh_dir(name)
    output = base / "hermes-goat-web"
    result = _run_builder("--output", str(output))
    assert result.returncode == 0, result.stdout + result.stderr
    return output


def _stage_sources(name, *, omit=(), symlink=()):
    """Materialize a filtered source tree under wiring-build for CLI tests."""
    base = _fresh_dir("stage-" + name)
    stage = base / "srcroot"
    for rel in PLUGIN_SOURCES + VENDOR_SOURCES + OTHER_SOURCES:
        if rel in omit:
            continue
        target = stage / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel in symlink:
            target.symlink_to(ROOT / rel)
        else:
            shutil.copy2(ROOT / rel, target)
    return stage


class PortableBundleBuildTests(unittest.TestCase):
    def test_builder_script_exists(self):
        self.assertTrue(BUILD_SCRIPT.is_file(), "missing builder script")

    def test_build_creates_bundle_with_exact_inventory_and_byte_copies(self):
        base = _fresh_dir("exact-inventory")
        output = base / "hermes-goat-web"
        result = _run_builder("--output", str(output))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        found_files = set()
        for current, dirnames, filenames in os.walk(output):
            dirnames.sort()
            for name in filenames:
                full = Path(current) / name
                self.assertFalse(
                    os.path.islink(full), "bundle contains symlink: %s" % full
                )
                found_files.add(str(full.relative_to(output)))
        self.assertEqual(found_files, EXPECTED_FILES)
        for out_rel, src_rel in SOURCE_OF_OUTPUT.items():
            with self.subTest(entry=out_rel):
                canonical = (ROOT / src_rel).read_bytes()
                actual = (output / out_rel).read_bytes()
                self.assertEqual(actual, canonical, "stale copy: %s" % out_rel)
                self.assertEqual(
                    hashlib.sha256(actual).hexdigest(),
                    hashlib.sha256(canonical).hexdigest(),
                )
        for name in FORBIDDEN_BUNDLE_NAMES:
            with self.subTest(forbidden=name):
                self.assertFalse((output / name).exists(), name)
                self.assertFalse(
                    (output / "_goat_v3_vendor" / name).exists(), name
                )

    def test_manifest_is_deterministic_with_relative_hashes_only(self):
        output = _build("manifest-shape")
        text = (output / "bundle-manifest.json").read_text(encoding="utf-8")
        manifest = json.loads(text)
        self.assertEqual(set(manifest), {"version", "files"})
        self.assertEqual(manifest["version"], 1)
        outputs = [entry["output"] for entry in manifest["files"]]
        self.assertEqual(outputs, sorted(outputs))
        for entry in manifest["files"]:
            with self.subTest(entry=entry.get("output")):
                self.assertEqual(set(entry), {"source", "output", "sha256"})
                self.assertFalse(os.path.isabs(entry["output"]))
                if entry["source"] is not None:
                    self.assertFalse(os.path.isabs(entry["source"]))
                    self.assertNotIn("..", Path(entry["source"]).parts)
                digest = entry["sha256"]
                self.assertEqual(len(digest), 64)
                int(digest, 16)
        self.assertNotIn(str(ROOT), text)
        self.assertNotIn(str(output), text)

    def test_deterministic_build_twice(self):
        first = _build("twice-first")
        second = _build("twice-second")
        first_manifest = (first / "bundle-manifest.json").read_bytes()
        second_manifest = (second / "bundle-manifest.json").read_bytes()
        self.assertEqual(first_manifest, second_manifest)
        first_files = {
            str(path.relative_to(first)): path.read_bytes()
            for path in sorted(first.rglob("*"))
            if path.is_file()
        }
        second_files = {
            str(path.relative_to(second)): path.read_bytes()
            for path in sorted(second.rglob("*"))
            if path.is_file()
        }
        self.assertEqual(set(first_files), set(second_files))
        self.assertEqual(set(first_files), EXPECTED_FILES)
        for name in first_files:
            with self.subTest(entry=name):
                self.assertEqual(first_files[name], second_files[name])

    def test_check_accepts_fresh_build(self):
        output = _build("check-ok")
        result = _run_builder("--check", str(output))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_rejects_stale_copy(self):
        output = _build("stale-copy")
        target = output / "_goat_v3_vendor" / "ssrf_guard.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        result = _run_builder("--check", str(output))
        self.assertNotEqual(result.returncode, 0)

    def test_check_rejects_tampered_manifest_matching_copy(self):
        output = _build("tampered-manifest")
        target = output / "_goat_v3_vendor" / "ddg_parser.py"
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
        manifest_path = output / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["files"]:
            if entry["output"] == "_goat_v3_vendor/ddg_parser.py":
                entry["sha256"] = hashlib.sha256(
                    target.read_bytes()
                ).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        result = _run_builder("--check", str(output))
        self.assertNotEqual(result.returncode, 0)

    def test_check_rejects_unexpected_bundle_entries(self):
        output = _build("unexpected-entry")
        (output / "extra.txt").write_text("not allowlisted\n")
        result = _run_builder("--check", str(output))
        self.assertNotEqual(result.returncode, 0)
        (output / "extra.txt").unlink()
        (output / "extra_dir").mkdir()
        result = _run_builder("--check", str(output))
        self.assertNotEqual(result.returncode, 0)

    def test_build_rejects_existing_output(self):
        base = _fresh_dir("existing-output")
        output = base / "hermes-goat-web"
        first = _run_builder("--output", str(output))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = _run_builder("--output", str(output))
        self.assertNotEqual(second.returncode, 0)

    def test_build_rejects_output_overlapping_source(self):
        inside = ROOT / "wiring-build-overlap-probe"
        result = _run_builder("--output", str(inside))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(os.path.lexists(str(inside)))
        result = _run_builder("--output", str(ROOT))
        self.assertNotEqual(result.returncode, 0)

    def test_build_rejects_missing_required_source(self):
        stage = _stage_sources("missing-required", omit=["adapters/ssrf_guard.py"])
        base = _fresh_dir("missing-required-out")
        result = _run_builder(
            "--source-root", str(stage), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0)

    def test_build_rejects_missing_optional_transitive_import(self):
        stage = _stage_sources(
            "missing-optional", omit=["adapters/result_contract.py"]
        )
        base = _fresh_dir("missing-optional-out")
        result = _run_builder(
            "--source-root", str(stage), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0)

    def test_build_rejects_symlink_source(self):
        stage = _stage_sources(
            "symlink-source", symlink=["adapters/ssrf_guard.py"]
        )
        base = _fresh_dir("symlink-source-out")
        result = _run_builder(
            "--source-root", str(stage), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0)

    def test_build_rejects_symlink_output_ancestor(self):
        base = _fresh_dir("symlink-output")
        real = base / "real"
        real.mkdir()
        link = base / "link"
        link.symlink_to(real, target_is_directory=True)
        result = _run_builder("--output", str(link / "hermes-goat-web"))
        self.assertNotEqual(result.returncode, 0)

    def test_approved_standalone_bundle_passes_check(self):
        output = ARTIFACTS_BUILD / "hermes-goat-web"
        self.assertTrue(output.is_dir(), "missing approved standalone bundle")
        result = _run_builder("--check", str(output))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


def _stage_with_injection(name, rel, extra_line):
    """Stage a source tree with one line prepended to a staged file."""
    stage = _stage_sources(name)
    target = stage / rel
    text = target.read_text(encoding="utf-8")
    target.write_text(extra_line + text, encoding="utf-8")
    return stage


def _via_ancestor_symlink(name):
    """Return (stage, via) where via reaches stage through a symlinked ancestor."""
    stage = _stage_sources(name)
    linkbase = _fresh_dir(name + "-linkbase")
    link = linkbase / "parentlink"
    link.symlink_to(stage.parent, target_is_directory=True)
    return stage, link / "srcroot"


class AncestorSymlinkRootTests(unittest.TestCase):
    def test_build_rejects_source_root_through_ancestor_symlink(self):
        _, via = _via_ancestor_symlink("anc-build")
        base = _fresh_dir("anc-build-out")
        result = _run_builder(
            "--source-root", str(via), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("symlink", result.stderr.lower(), result.stderr)

    def test_check_rejects_source_root_through_ancestor_symlink(self):
        _, via = _via_ancestor_symlink("anc-check")
        bundle = _build("anc-check-bundle")
        result = _run_builder(
            "--source-root", str(via), "--check", str(bundle)
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("symlink", result.stderr.lower(), result.stderr)


class VendorClosureClassifierTests(unittest.TestCase):
    def test_build_rejects_package_relative_stdlib_shadow(self):
        stage = _stage_with_injection(
            "rel-shadow", "adapters/ssrf_guard.py", "from .json import loads\n"
        )
        base = _fresh_dir("rel-shadow-out")
        result = _run_builder(
            "--source-root", str(stage), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_build_rejects_level_two_relative_escape(self):
        stage = _stage_with_injection(
            "rel-escape", "adapters/ddg_parser.py", "from ..outside import thing\n"
        )
        base = _fresh_dir("rel-escape-out")
        result = _run_builder(
            "--source-root", str(stage), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


class PluginClosureTests(unittest.TestCase):
    def test_build_rejects_plugin_local_import_outside_allowlist(self):
        stage = _stage_with_injection(
            "plugin-local",
            "goat-web/plugins/goat-web/tool_schemas.py",
            "from .nonexistent_local_xyz import thing\n",
        )
        base = _fresh_dir("plugin-local-out")
        result = _run_builder(
            "--source-root", str(stage), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


class NonregularSourceTests(unittest.TestCase):
    def test_build_rejects_directory_source_file(self):
        stage = _stage_sources("nonregular-src")
        target = stage / "adapters" / "ddg_parser.py"
        target.unlink()
        target.mkdir()
        (target / "placeholder.txt").write_text("not a module\n")
        base = _fresh_dir("nonregular-src-out")
        result = _run_builder(
            "--source-root", str(stage), "--output", str(base / "hermes-goat-web")
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)


class ManifestHardeningTests(unittest.TestCase):
    def test_check_rejects_duplicate_output_records(self):
        output = _build("dup-manifest")
        manifest_path = output / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"].append(dict(manifest["files"][0]))
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        result = _run_builder("--check", str(output))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_rejects_unexpected_top_level_manifest_fields(self):
        output = _build("extra-manifest-field")
        manifest_path = output / "bundle-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["extra"] = ["not-allowlisted"]
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        result = _run_builder("--check", str(output))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_rejects_source_bundle_overlap_before_read(self):
        output = _build("overlap-check")
        result = _run_builder("--source-root", str(output), "--check", str(output))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("overlap", result.stderr.lower(), result.stderr)

    def test_check_rejects_nonregular_bundle_entry(self):
        output = _build("nonregular-entry")
        target = output / "LICENSE"
        target.unlink()
        target.mkdir()
        result = _run_builder("--check", str(output))
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_check_rejects_fifo_bundle_entry_without_hanging(self):
        output = _build("fifo-entry")
        target = output / "LICENSE"
        target.unlink()
        os.mkfifo(str(target))
        try:
            proc = subprocess.run(
                [sys.executable, "-B", str(BUILD_SCRIPT), "--check", str(output)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.fail("check hung on fifo entry instead of failing closed")
        self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)


_CLEAN_CHILD_CODE = (
    "import importlib.util\n"
    "import json\n"
    "import os\n"
    "import re\n"
    "import socket\n"
    "import subprocess\n"
    "import sys\n"
    "bundle = sys.argv[1]\n"
    "path_before = list(sys.path)\n"
    "def _blocked(*args, **kwargs):\n"
    "    raise AssertionError('network/subprocess use is forbidden in clean child')\n"
    "socket.getaddrinfo = _blocked\n"
    "socket.create_connection = _blocked\n"
    "# NOTE: socket.socket itself must stay intact: stdlib ssl subclasses it\n"
    "# at bundle import time. create_connection/getaddrinfo blocks below\n"
    "# already forbid every real TCP path (ssrf_guard uses create_connection).\n"
    "subprocess.Popen = _blocked\n"
    "subprocess.run = _blocked\n"
    "subprocess.call = _blocked\n"
    "subprocess.check_call = _blocked\n"
    "subprocess.check_output = _blocked\n"
    "if hasattr(os, 'system'):\n"
    "    os.system = _blocked\n"
    "package_name = 'goat_clean_%d' % os.getpid()\n"
    "spec = importlib.util.spec_from_file_location(\n"
    "    package_name, os.path.join(bundle, '__init__.py'),\n"
    "    submodule_search_locations=[bundle])\n"
    "assert spec is not None and spec.loader is not None, 'no spec for bundle'\n"
    "module = importlib.util.module_from_spec(spec)\n"
    "sys.modules[package_name] = module\n"
    "try:\n"
    "    spec.loader.exec_module(module)\n"
    "except Exception:\n"
    "    sys.modules.pop(package_name, None)\n"
    "    raise\n"
    "assert sys.path == path_before, 'sys.path changed: %r -> %r' % (path_before, sys.path)\n"
    "for _bad in ('ssrf_guard', 'ddg_parser', 'result_contract', 'adapters', 'goat_tools'):\n"
    "    assert _bad not in sys.modules, 'top-level alias present: %s' % _bad\n"
    "real_bundle = os.path.realpath(bundle)\n"
    "for _name, _loaded in list(sys.modules.items()):\n"
    "    if _name == package_name or _name.startswith(package_name + '.'):\n"
    "        _location = getattr(_loaded, '__file__', None)\n"
    "        assert _location is not None, 'module without file: %s' % _name\n"
    "        _real = os.path.realpath(_location)\n"
    "        assert _real == real_bundle or _real.startswith(real_bundle + os.sep), (_name, _location)\n"
    "class RecordingContext(object):\n"
    "    def __init__(self):\n"
    "        self.tools = {}\n"
    "    def register_tool(self, **kwargs):\n"
    "        self.tools[kwargs['name']] = kwargs\n"
    "wiring = module.v3_wiring\n"
    "WiringDependencies = wiring.WiringDependencies\n"
    "def fake_search(query, *, max_results=5):\n"
    "    assert isinstance(query, str), type(query)\n"
    "    return {'ok': True, 'results': [\n"
    "        {'title': 'Denied early', 'url': 'https://denied.example/early',\n"
    "         'snippet': 'Nuclear fission releases energy here.',\n"
    "         'published_at': '2024-06-01T00:00:00Z', 'language': 'en'},\n"
    "        {'title': 'Caf\\u00e9 fission \\u00e9\\u00e9n', 'url': 'https://good.example/un%C3%AFcode-1',\n"
    "         'snippet': 'Nuclear fission releases energy. Caf\\u00e9 reactors use fission heat.',\n"
    "         'published_at': '2024-06-01T00:00:00Z', 'language': 'en'},\n"
    "        {'title': 'Fission two', 'url': 'https://good.example/fission-two',\n"
    "         'snippet': 'Nuclear fission releases energy. Control rods manage fission rate.',\n"
    "         'published_at': '2024-06-01T00:00:00Z', 'language': 'en'},\n"
    "    ]}\n"
    "recorded = {}\n"
    "def _fake_transport(kind, payload):\n"
    "    def _transport(url):\n"
    "        recorded.setdefault(kind, []).append(url)\n"
    "        return {'status': 200, 'body': json.dumps(payload, ensure_ascii=False)}\n"
    "    return _transport\n"
    "scholar_payload = {'message': {'items': [\n"
    "    {'title': ['Scholar Caf\\u00e9 paper'], 'DOI': '10.1234/cafe-2021',\n"
    "     'URL': 'https://example.com/paper', 'author': [{'given': 'Ada', 'family': 'Lovelace'}],\n"
    "     'issued': {'date-parts': [[2021]]}, 'container-title': ['Journal of Tests']}\n"
    "]}}\n"
    "news_payload = {'articles': [\n"
    "    {'title': 'Example news headline', 'url': 'https://example.com/news-item',\n"
    "     'snippet': 'Snippet words here.', 'seendate': '20261009T120000Z',\n"
    "     'domain': 'example.com', 'language': 'English', 'sourcecountry': 'United States'}\n"
    "    ]}\n"
    "images_payload = {'query': {'pages': [\n"
    "    {'title': 'File:Caf\\u00e9 test.jpg', 'imageinfo': [{\n"
    "        'thumburl': 'https://upload.wikimedia.org/thumb.jpg',\n"
    "        'url': 'https://upload.wikimedia.org/full.jpg',\n"
    "        'descriptionurl': 'https://commons.wikimedia.org/wiki/File:Cafe_test.jpg',\n"
    "        'extmetadata': {\n"
    "            'LicenseShortName': {'value': 'CC-BY-SA 4.0'},\n"
    "            'LicenseUrl': {'value': 'https://creativecommons.org/licenses/by-sa/4.0/'},\n"
    "            'Artist': {'value': 'Test Artist'},\n"
    "            'ImageDescription': {'value': 'Caf\\u00e9 description'}}}]}\n"
    "]}}\n"
    "deps = WiringDependencies(search=fake_search, vertical_transports={\n"
    "    'scholar': _fake_transport('scholar', scholar_payload),\n"
    "    'news': _fake_transport('news', news_payload),\n"
    "    'images': _fake_transport('images', images_payload)})\n"
    "ctx = RecordingContext()\n"
    "module.register(ctx, deps=deps)\n"
    "expected = {'goat_search', 'goat_extract', 'goat_crawl', 'goat_probe',\n"
    "            'goat_answer', 'goat_filtered_search', 'goat_vertical_search'}\n"
    "assert set(ctx.tools) == expected, sorted(ctx.tools)\n"
    "for _tool in ctx.tools.values():\n"
    "    assert _tool['toolset'] == 'goat_web', _tool\n"
    "    assert _tool['schema']['name'] in expected, _tool['schema']\n"
    "raw_answer = ctx.tools['goat_answer']['handler']({'query': 'nuclear fission energy'})\n"
    "assert '\\\\u00e9' not in raw_answer, 'answer JSON must not escape Unicode'\n"
    "answer = json.loads(raw_answer)\n"
    "assert answer.get('ok') is True, answer\n"
    "assert 'Caf\\u00e9' in answer.get('answer', ''), answer\n"
    "sources = answer.get('sources')\n"
    "assert isinstance(sources, list) and sources, answer\n"
    "assert [item['index'] for item in sources] == list(range(1, len(sources) + 1)), sources\n"
    "cited = {int(n) for n in re.findall(r'\\[(\\d+)\\]', answer['answer'])}\n"
    "assert cited and cited <= {item['index'] for item in sources}, (answer, sources)\n"
    "for _line in answer['answer'].split('\\n'):\n"
    "    assert re.search(r'\\[\\d+\\]', _line), _line\n"
    "for _item in sources:\n"
    "    assert _item['url'].startswith('https://'), _item\n"
    "payload = json.loads(ctx.tools['goat_filtered_search']['handler'](\n"
    "    {'query': 'fission energy', 'max_results': 1, 'allowed_domains': ['good.example']}))\n"
    "assert payload.get('ok') is True, payload\n"
    "assert isinstance(payload.get('results'), list) and len(payload['results']) == 1, payload\n"
    "only = payload['results'][0]\n"
    "assert only['url'] == 'https://good.example/un%C3%AFcode-1', only\n"
    "assert only.get('published_at') == '2024-06-01T00:00:00Z', only\n"
    "assert only.get('language') == 'en', only\n"
    "scholar = json.loads(ctx.tools['goat_vertical_search']['handler'](\n"
    "    {'vertical': 'scholar', 'query': 'offline scholar'}))\n"
    "assert scholar.get('ok') is True, scholar\n"
    "assert scholar.get('vertical') == 'scholar' and scholar.get('source') == 'crossref', scholar\n"
    "assert scholar.get('source_url') == 'https://www.crossref.org/', scholar\n"
    "first = scholar['results'][0]\n"
    "assert first['doi'] == '10.1234/cafe-2021' and first['authors'] == ['Ada Lovelace'], first\n"
    "assert first['year'] == 2021 and first['venue'] == 'Journal of Tests', first\n"
    "assert 'Caf\\u00e9' in first['title'], first\n"
    "news = json.loads(ctx.tools['goat_vertical_search']['handler'](\n"
    "    {'vertical': 'news', 'query': 'offline news'}))\n"
    "assert news.get('ok') is True, news\n"
    "assert news.get('vertical') == 'news' and news.get('source') == 'gdelt', news\n"
    "assert news.get('source_url') == 'https://gdeltproject.org/', news\n"
    "article = news['results'][0]\n"
    "assert article['url'] == 'https://example.com/news-item', article\n"
    "assert article['published'] == '20261009T120000Z', article\n"
    "assert article['language'] == 'English' and article['source'] == 'example.com', article\n"
    "images = json.loads(ctx.tools['goat_vertical_search']['handler'](\n"
    "    {'vertical': 'images', 'query': 'offline images'}))\n"
    "assert images.get('ok') is True, images\n"
    "assert images.get('vertical') == 'images' and images.get('source') == 'wikimedia-commons', images\n"
    "assert images.get('source_url') == 'https://commons.wikimedia.org/', images\n"
    "medium = images['results'][0]\n"
    "assert medium['license'] == 'CC-BY-SA 4.0' and medium['creator'] == 'Test Artist', medium\n"
    "assert medium['license_url'] == 'https://creativecommons.org/licenses/by-sa/4.0/', medium\n"
    "assert medium['page_url'] == 'https://commons.wikimedia.org/wiki/File:Cafe_test.jpg', medium\n"
    "assert recorded['scholar'][0].startswith('https://api.crossref.org/works?'), recorded\n"
    "assert recorded['news'][0].startswith('https://api.gdeltproject.org/api/v2/doc/doc?'), recorded\n"
    "assert recorded['images'][0].startswith('https://commons.wikimedia.org/w/api.php?'), recorded\n"
    "summary = {'answer_sources': len(sources), 'filtered_url': only['url'],\n"
    "           'scholar_doi': first['doi'], 'news_published': article['published'],\n"
    "           'images_license': medium['license']}\n"
    "sys.stdout.write('GOAT_CLEAN_PORTABILITY_OK ' + json.dumps(summary, ensure_ascii=False) + '\\n')\n"
)


class CleanPortableSubprocessTests(unittest.TestCase):
    def test_clean_isolated_subprocess_registers_and_invokes_all_three_routes(self):
        output = _build("clean-portable")
        empty_cwd = _fresh_dir("clean-cwd") / "cwd"
        empty_cwd.mkdir()
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
        proc = subprocess.run(
            [sys.executable, "-I", "-S", "-B", "-c", _CLEAN_CHILD_CODE, str(output)],
            cwd=str(empty_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        sentinel = None
        for line in proc.stdout.splitlines():
            if line.startswith("GOAT_CLEAN_PORTABILITY_OK "):
                sentinel = json.loads(line[len("GOAT_CLEAN_PORTABILITY_OK "):])
        self.assertIsNotNone(sentinel, proc.stdout + proc.stderr)
        self.assertEqual(
            sentinel,
            {
                "answer_sources": 3,
                "filtered_url": "https://good.example/un%C3%AFcode-1",
                "scholar_doi": "10.1234/cafe-2021",
                "news_published": "20261009T120000Z",
                "images_license": "CC-BY-SA 4.0",
            },
        )


if __name__ == "__main__":
    unittest.main()
