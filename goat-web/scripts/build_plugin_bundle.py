"""Build the portable ``hermes-goat-web`` directory-plugin bundle.

The authoring ``goat-web/plugins/goat-web`` directory is a source template,
not an installable plugin: it imports the private ``._goat_v3_vendor``
package, which only exists inside a built bundle. This script copies an
explicit reviewed allowlist of source files byte-for-byte into a
caller-chosen fresh output directory and writes a deterministic
``bundle-manifest.json``. It never installs, enables, downloads, or reads
config/auth state.

Layout of the built bundle (relative to the output directory)::

    __init__.py                  <- goat-web/plugins/goat-web/__init__.py
    goat_tools.py                <- goat-web/plugins/goat-web/goat_tools.py
    adapters.py                  <- goat-web/plugins/goat-web/adapters.py
    url_gate.py                  <- goat-web/plugins/goat-web/url_gate.py
    tool_schemas.py              <- goat-web/plugins/goat-web/tool_schemas.py
    v3_wiring.py                 <- goat-web/plugins/goat-web/v3_wiring.py
    plugin.yaml                  <- goat-web/plugins/goat-web/plugin.yaml
    _goat_v3_vendor/*.py         <- adapters/*.py (exact byte copies)
    _goat_v3_vendor/__init__.py  <- generated inert initializer
    hermes-goat-web.plugin.json  <- goat-web/hermes-goat-web.plugin.json
    LICENSE                      <- goat-web/LICENSE
    VENDOR-LICENSE               <- adapters/LICENSE
    VENDOR-PROVENANCE.md         <- adapters/PROVENANCE.md
    bundle-manifest.json         <- generated deterministic manifest
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_SOURCE_ROOT = SCRIPT_PATH.parents[2]

# (source relative path, bundle output relative path).
PLUGIN_FILES = (
    ("goat-web/plugins/goat-web/__init__.py", "__init__.py"),
    ("goat-web/plugins/goat-web/goat_tools.py", "goat_tools.py"),
    ("goat-web/plugins/goat-web/search_providers.py", "search_providers.py"),
    ("goat-web/plugins/goat-web/adapters.py", "adapters.py"),
    ("goat-web/plugins/goat-web/url_gate.py", "url_gate.py"),
    ("goat-web/plugins/goat-web/tool_schemas.py", "tool_schemas.py"),
    ("goat-web/plugins/goat-web/v3_wiring.py", "v3_wiring.py"),
    ("goat-web/plugins/goat-web/plugin.yaml", "plugin.yaml"),
)

REQUIRED_VENDOR_FILES = (
    ("adapters/answer_synth.py", "_goat_v3_vendor/answer_synth.py"),
    ("adapters/search_filters.py", "_goat_v3_vendor/search_filters.py"),
    ("adapters/free_verticals.py", "_goat_v3_vendor/free_verticals.py"),
    ("adapters/free_stack.py", "_goat_v3_vendor/free_stack.py"),
    ("adapters/ssrf_guard.py", "_goat_v3_vendor/ssrf_guard.py"),
    ("adapters/ddg_parser.py", "_goat_v3_vendor/ddg_parser.py"),
)

# Explicit optional filename: copied only when present in the source tree.
# It is currently required in practice because the other vendors import it;
# the transitive-closure check below enforces that.
OPTIONAL_VENDOR_FILES = (
    ("adapters/result_contract.py", "_goat_v3_vendor/result_contract.py"),
)

OTHER_FILES = (
    ("goat-web/hermes-goat-web.plugin.json", "hermes-goat-web.plugin.json"),
    ("goat-web/LICENSE", "LICENSE"),
    ("adapters/LICENSE", "VENDOR-LICENSE"),
    ("adapters/PROVENANCE.md", "VENDOR-PROVENANCE.md"),
)

VENDOR_INIT_OUTPUT = "_goat_v3_vendor/__init__.py"
VENDOR_INIT_BYTES = (
    b'"""Private vendored GOAT adapter package (generated, do not edit)."""\n'
)
MANIFEST_NAME = "bundle-manifest.json"
MANIFEST_VERSION = 1


class BundleError(Exception):
    """Fail-closed packaging error."""


def resolve_source_root(explicit=None):
    """Resolve the repository root; tests may pass a trusted override."""
    if explicit is not None:
        return Path(explicit)
    return DEFAULT_SOURCE_ROOT


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _absolute(path):
    return Path(os.path.abspath(str(path)))


def _check_no_symlink_chain(path, label):
    """Reject path or any of its ancestors being a symlink."""
    current = _absolute(path)
    chain = [current] + list(current.parents)
    for node in chain:
        if os.path.islink(str(node)):
            raise BundleError(
                "%s path or ancestor is a symlink: %s" % (label, node)
            )
    return current


def _check_contained(candidate_abs, root_abs, label):
    root_str = str(root_abs)
    cand_str = str(candidate_abs)
    if cand_str != root_str and not cand_str.startswith(root_str + os.sep):
        raise BundleError("%s escapes source root: %s" % (label, candidate_abs))
    # Belt-and-braces against symlink redirection even where lstat missed.
    real_root = Path(os.path.realpath(str(root_abs)))
    real_cand = Path(os.path.realpath(str(candidate_abs)))
    try:
        real_cand.relative_to(real_root)
    except ValueError:
        raise BundleError(
            "%s escapes source root: %s" % (label, candidate_abs)
        ) from None
    return candidate_abs


def _read_source(source_root_abs, rel):
    """Read one allowlisted source file; reject symlinks/escapes/nonregular."""
    if os.path.isabs(rel) or ".." in Path(rel).parts:
        raise BundleError("invalid allowlisted source name: %s" % rel)
    candidate = _absolute(source_root_abs / rel)
    _check_contained(candidate, source_root_abs, "source")
    # Ancestor symlinks between the source root and the file.
    node = candidate
    while node != source_root_abs:
        if os.path.islink(str(node)):
            raise BundleError("source or ancestor is a symlink: %s" % node)
        node = node.parent
    if os.path.islink(str(source_root_abs)):
        raise BundleError("source root is a symlink: %s" % source_root_abs)
    if not os.path.lexists(str(candidate)):
        raise BundleError("missing source: %s" % rel)
    if not os.path.isfile(str(candidate)) or os.path.islink(str(candidate)):
        raise BundleError("source is not a regular file: %s" % rel)
    with open(str(candidate), "rb") as handle:
        return handle.read()


def _stdlib_names():
    try:
        names = set(sys.stdlib_module_names)
    except AttributeError:  # pragma: no cover - very old interpreters
        names = set()
    names.add("__future__")
    return names


def _check_vendor_closure(sources):
    """Fail if a vendored file needs a private sibling outside the set.

    ``sources`` maps module stem -> file bytes for the vendored package.
    Relative imports (``level >= 1``) always denote local vendored siblings,
    never the standard library: ``from .json import ...`` requires an
    explicitly packaged ``json`` sibling. Any ``level > 1`` import escapes
    the package and fails closed. Absolute (``level == 0``) imports must be
    vendored siblings (the canonical dual-import fallback) or standard
    library; anything else is a real packaging blocker, never silently
    copied.
    """
    stdlib_names = _stdlib_names()
    for stem, data in sorted(sources.items()):
        try:
            tree = ast.parse(data.decode("utf-8"), filename=stem + ".py")
        except (SyntaxError, UnicodeDecodeError) as error:
            raise BundleError("cannot parse vendored source %s: %s" % (stem, error))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                level = node.level or 0
                if level > 1:
                    raise BundleError(
                        "vendored module %s uses out-of-package relative "
                        "import" % stem
                    )
                if level == 1:
                    if node.module:
                        name = node.module.split(".")[0]
                        if name not in sources:
                            raise BundleError(
                                "vendored module %s imports %s outside the "
                                "explicit vendor allowlist" % (stem, name)
                            )
                    else:
                        for alias in node.names:
                            name = alias.name.split(".")[0]
                            if name not in sources:
                                raise BundleError(
                                    "vendored module %s imports %s outside "
                                    "the explicit vendor allowlist"
                                    % (stem, name)
                                )
                elif node.module:
                    name = node.module.split(".")[0]
                    if name in sources or name in stdlib_names:
                        continue
                    raise BundleError(
                        "vendored module %s imports %s outside the explicit "
                        "vendor allowlist" % (stem, name)
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in sources or name in stdlib_names:
                        continue
                    raise BundleError(
                        "vendored module %s imports %s outside the explicit "
                        "vendor allowlist" % (stem, name)
                    )


def _check_vendor_reference(stem, dotted, vendor_stems):
    """Validate one ``_goat_v3_vendor[.submodule]`` reference from plugins."""
    parts = dotted.split(".")
    assert parts[0] == "_goat_v3_vendor"
    if len(parts) > 2:
        raise BundleError(
            "plugin module %s imports %s outside the explicit vendor "
            "allowlist" % (stem, dotted)
        )
    if len(parts) == 2 and parts[1] not in vendor_stems:
        raise BundleError(
            "plugin module %s imports %s outside the explicit vendor "
            "allowlist" % (stem, dotted)
        )


def _check_plugin_closure(plugin_sources, vendor_stems):
    """Fail if a plugin file imports a module outside the bundle closure.

    ``plugin_sources`` maps bundle-top-level module stem -> file bytes.
    Local (``level == 1``) imports must name explicitly packaged bundle
    modules (plugin siblings or the private ``_goat_v3_vendor`` package,
    whose submodule must itself be allowlisted); a relative standard-library
    name such as ``from .json import ...`` is a missing local dependency,
    not the permitted stdlib module. ``level > 1`` escapes fail closed.
    Absolute imports must be packaged siblings, the private vendor package,
    or standard library.
    """
    stdlib_names = _stdlib_names()
    allowed_local = set(plugin_sources) | {"_goat_v3_vendor"}
    for stem, data in sorted(plugin_sources.items()):
        try:
            tree = ast.parse(data.decode("utf-8"), filename=stem + ".py")
        except (SyntaxError, UnicodeDecodeError) as error:
            raise BundleError("cannot parse plugin source %s: %s" % (stem, error))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                level = node.level or 0
                if level > 1:
                    raise BundleError(
                        "plugin module %s uses out-of-package relative "
                        "import" % stem
                    )
                if level == 1:
                    if node.module:
                        top = node.module.split(".")[0]
                        if top not in allowed_local:
                            raise BundleError(
                                "plugin module %s imports %s outside the "
                                "explicit bundle allowlist" % (stem, node.module)
                            )
                        if top == "_goat_v3_vendor":
                            _check_vendor_reference(stem, node.module, vendor_stems)
                            if node.module == "_goat_v3_vendor":
                                for alias in node.names:
                                    if alias.name == "*":
                                        continue
                                    if alias.name.split(".")[0] not in vendor_stems:
                                        raise BundleError(
                                            "plugin module %s imports %s outside "
                                            "the explicit vendor allowlist"
                                            % (stem, alias.name)
                                        )
                    else:
                        for alias in node.names:
                            if alias.name == "*":
                                continue
                            top = alias.name.split(".")[0]
                            if top not in allowed_local:
                                raise BundleError(
                                    "plugin module %s imports %s outside the "
                                    "explicit bundle allowlist"
                                    % (stem, alias.name)
                                )
                            if top == "_goat_v3_vendor":
                                _check_vendor_reference(
                                    stem, alias.name, vendor_stems
                                )
                elif node.module:
                    top = node.module.split(".")[0]
                    if top in allowed_local or top in stdlib_names:
                        if top == "_goat_v3_vendor":
                            _check_vendor_reference(stem, node.module, vendor_stems)
                        continue
                    raise BundleError(
                        "plugin module %s imports %s outside the explicit "
                        "bundle allowlist" % (stem, node.module)
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in allowed_local or top in stdlib_names:
                        if top == "_goat_v3_vendor":
                            _check_vendor_reference(stem, alias.name, vendor_stems)
                        continue
                    raise BundleError(
                        "plugin module %s imports %s outside the explicit "
                        "bundle allowlist" % (stem, alias.name)
                    )


def _collect_mapping(source_root_abs):
    """Read every allowlisted source; return {output_rel: (src_rel, bytes)}."""
    _check_no_symlink_chain(source_root_abs, "source")
    mapping = {}
    plugin_sources = {}
    for rel, out in PLUGIN_FILES + OTHER_FILES:
        mapping[out] = (rel, _read_source(source_root_abs, rel))
    for out, (rel, data) in mapping.items():
        if out.endswith(".py") and "/" not in out:
            plugin_sources[Path(out).stem] = data
    vendor_sources = {}
    for rel, out in REQUIRED_VENDOR_FILES:
        data = _read_source(source_root_abs, rel)
        mapping[out] = (rel, data)
        vendor_sources[Path(out).stem] = data
    for rel, out in OPTIONAL_VENDOR_FILES:
        candidate = _absolute(source_root_abs / rel)
        if os.path.lexists(str(candidate)):
            data = _read_source(source_root_abs, rel)
            mapping[out] = (rel, data)
            vendor_sources[Path(out).stem] = data
    _check_vendor_closure(vendor_sources)
    _check_plugin_closure(plugin_sources, set(vendor_sources))
    return mapping


def _expected_inventory(mapping):
    files = set(mapping) | {VENDOR_INIT_OUTPUT, MANIFEST_NAME}
    directories = {"_goat_v3_vendor"}
    return files, directories


def _manifest_bytes(mapping):
    entries = []
    for out in sorted(mapping):
        rel, data = mapping[out]
        entries.append(
            {"source": rel, "output": out, "sha256": _sha256_bytes(data)}
        )
    entries.append(
        {
            "source": None,
            "output": VENDOR_INIT_OUTPUT,
            "sha256": _sha256_bytes(VENDOR_INIT_BYTES),
        }
    )
    entries.sort(key=lambda entry: entry["output"])
    manifest = {"version": MANIFEST_VERSION, "files": entries}
    return (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _check_no_overlap(source_root_abs, other_abs, other_label):
    """Fail if either path contains the other; message carries 'overlap'."""
    src_str = str(source_root_abs)
    other_str = str(other_abs)
    if (
        other_str == src_str
        or other_str.startswith(src_str + os.sep)
        or src_str.startswith(other_str + os.sep)
    ):
        raise BundleError(
            "%s overlaps source root: %s" % (other_label, other_abs)
        )


def _check_output_fresh(output_abs, source_root_abs):
    _check_no_symlink_chain(output_abs, "output")
    _check_no_overlap(source_root_abs, output_abs, "output")
    if os.path.lexists(str(output_abs)):
        raise BundleError("output already exists: %s" % output_abs)


def build_bundle(source_root, output):
    """Build a fresh bundle; return the output directory Path."""
    source_root_abs = _absolute(resolve_source_root(source_root))
    _check_no_symlink_chain(source_root_abs, "source")
    if not source_root_abs.is_dir():
        raise BundleError("missing source root: %s" % source_root_abs)
    output_abs = _absolute(Path(output))
    _check_output_fresh(output_abs, source_root_abs)
    mapping = _collect_mapping(source_root_abs)
    output_abs.mkdir(parents=True)
    try:
        vendor_dir = output_abs / "_goat_v3_vendor"
        vendor_dir.mkdir(parents=False)
        for out in sorted(mapping):
            target = output_abs / out
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(str(target), "wb") as handle:
                handle.write(mapping[out][1])
        with open(str(output_abs / VENDOR_INIT_OUTPUT), "wb") as handle:
            handle.write(VENDOR_INIT_BYTES)
        with open(str(output_abs / MANIFEST_NAME), "wb") as handle:
            handle.write(_manifest_bytes(mapping))
    except Exception:
        # Never leave a half-written bundle behind; caller sees the error.
        for child in sorted(output_abs.rglob("*"), reverse=True):
            try:
                if child.is_symlink() or child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            except OSError:
                pass
        try:
            output_abs.rmdir()
        except OSError:
            pass
        raise
    check_bundle(source_root_abs, output_abs)
    return output_abs


def _walk_inventory(bundle_abs):
    import stat as _stat

    files = set()
    directories = set()
    for current, dirnames, filenames in os.walk(str(bundle_abs)):
        dirnames.sort()
        filenames.sort()
        for name in dirnames + filenames:
            full = Path(current) / name
            try:
                file_stat = os.lstat(str(full))
            except OSError as error:
                raise BundleError(
                    "unreadable bundle entry %s: %s" % (full, error)
                ) from None
            if _stat.S_ISLNK(file_stat.st_mode):
                raise BundleError("bundle contains a symlink: %s" % full)
            rel = str(full.relative_to(bundle_abs))
            if _stat.S_ISDIR(file_stat.st_mode):
                directories.add(rel)
            elif _stat.S_ISREG(file_stat.st_mode):
                files.add(rel)
            else:
                # FIFO, socket, device, or anything else: fail closed here,
                # before any open() can block on it.
                raise BundleError(
                    "bundle entry is not a regular file or directory: %s" % full
                )
    return files, directories


def check_bundle(source_root, bundle):
    """Read-only verification of a built bundle; raise BundleError on drift."""
    source_root_abs = _absolute(resolve_source_root(source_root))
    bundle_abs = _absolute(Path(bundle))
    _check_no_symlink_chain(bundle_abs, "bundle")
    _check_no_symlink_chain(source_root_abs, "source")
    _check_no_overlap(source_root_abs, bundle_abs, "bundle")
    if not bundle_abs.is_dir():
        raise BundleError("missing bundle: %s" % bundle_abs)
    mapping = _collect_mapping(source_root_abs)
    expected_files, expected_directories = _expected_inventory(mapping)
    found_files, found_directories = _walk_inventory(bundle_abs)
    if found_files != expected_files:
        raise BundleError(
            "unexpected bundle file inventory: missing=%s extra=%s"
            % (
                sorted(expected_files - found_files),
                sorted(found_files - expected_files),
            )
        )
    if found_directories != expected_directories:
        raise BundleError(
            "unexpected bundle directory inventory: missing=%s extra=%s"
            % (
                sorted(expected_directories - found_directories),
                sorted(found_directories - expected_directories),
            )
        )
    manifest_path = bundle_abs / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise BundleError("unreadable bundle manifest: %s" % error) from None
    if not isinstance(manifest, dict) or set(manifest) != {"version", "files"}:
        raise BundleError("bundle manifest has unexpected top-level fields")
    if manifest.get("version") != MANIFEST_VERSION:
        raise BundleError("bundle manifest has unknown version")
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise BundleError("bundle manifest has no file list")
    by_output = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise BundleError("bundle manifest has a malformed entry")
        if set(entry) != {"source", "output", "sha256"}:
            raise BundleError("bundle manifest entry has unexpected fields")
        if not isinstance(entry["output"], str) or not isinstance(
            entry["sha256"], str
        ):
            raise BundleError("bundle manifest has a malformed entry")
        if entry["source"] is not None and not isinstance(entry["source"], str):
            raise BundleError("bundle manifest has a malformed entry")
        if entry["output"] in by_output:
            raise BundleError(
                "bundle manifest has a duplicate output: %s" % entry["output"]
            )
        by_output[entry["output"]] = entry
    # Manifest must describe exactly the copied files plus the generated init.
    if set(by_output) != (set(mapping) | {VENDOR_INIT_OUTPUT}):
        raise BundleError("bundle manifest inventory does not match allowlist")
    for out in sorted(mapping):
        rel, canonical = mapping[out]
        entry = by_output[out]
        if entry["source"] != rel:
            raise BundleError("manifest source mismatch for %s" % out)
        canonical_hash = _sha256_bytes(canonical)
        if entry["sha256"] != canonical_hash:
            raise BundleError("manifest hash is stale for %s" % out)
        try:
            with open(str(bundle_abs / out), "rb") as handle:
                actual = handle.read()
        except OSError as error:
            raise BundleError("unreadable bundle file %s: %s" % (out, error))
        if actual != canonical or _sha256_bytes(actual) != canonical_hash:
            raise BundleError("stale bundle copy: %s" % out)
    init_entry = by_output[VENDOR_INIT_OUTPUT]
    if init_entry["source"] is not None:
        raise BundleError("generated init manifest entry must have null source")
    if init_entry["sha256"] != _sha256_bytes(VENDOR_INIT_BYTES):
        raise BundleError("manifest hash is stale for %s" % VENDOR_INIT_OUTPUT)
    try:
        with open(str(bundle_abs / VENDOR_INIT_OUTPUT), "rb") as handle:
            actual_init = handle.read()
    except OSError as error:
        raise BundleError(
            "unreadable bundle file %s: %s" % (VENDOR_INIT_OUTPUT, error)
        )
    if actual_init != VENDOR_INIT_BYTES:
        raise BundleError("stale bundle copy: %s" % VENDOR_INIT_OUTPUT)
    return bundle_abs


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Build or verify the portable hermes-goat-web bundle."
    )
    parser.add_argument("--output", help="fresh directory to build the bundle in")
    parser.add_argument("--check", help="read-only verification of a bundle")
    parser.add_argument(
        "--source-root",
        default=None,
        help="trusted source-root override (tests only)",
    )
    args = parser.parse_args(argv)
    try:
        if args.output and args.check:
            raise BundleError("use only one of --output or --check")
        if args.output:
            build_bundle(args.source_root, args.output)
            print("built %s" % _absolute(Path(args.output)))
        elif args.check:
            check_bundle(args.source_root, args.check)
            print("ok %s" % _absolute(Path(args.check)))
        else:
            raise BundleError("one of --output or --check is required")
    except BundleError as error:
        print("error: %s" % error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
