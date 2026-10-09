"""Read-only staging audit using narrow heuristics, not a full release gate.

Checks a small fixed set of secret-marker byte strings and absolute-path
prefixes, `.env`/`auth`-style names, symlinks, and filesystem scan errors.
A clean result is not a comprehensive secret or credential scan.
"""

import os
import stat
import sys
from pathlib import Path


_SECRET_MARKERS = (
    b"AK" + b"IA",
    b"ghp" + b"_",
    b"xoxb" + b"-",
    b"BEGIN PRIVATE" + b" KEY",
)
_ABSOLUTE_MARKERS = (b"/" + b"opt/", b"/" + b"home/")


def _sensitive_name(name):
    lowered = name.casefold()
    if lowered.startswith(".env"):
        return True
    return (
        lowered == "auth"
        or lowered.startswith(("auth.", "auth_", "auth-"))
        or lowered.endswith(".auth")
    )


def _relative(root, path):
    relative = os.path.relpath(path, root)
    return "." if relative == os.curdir else relative.replace(os.sep, "/")


def scan_staging(base_dir):
    """Return ``[(finding_kind, relative_path), ...]`` without following links."""
    try:
        raw_path = os.fspath(base_dir)
    except TypeError:
        return [("scan-error", ".")]
    root = os.path.abspath(raw_path)
    root_path = Path(root)

    # Reject a symlink anywhere in the supplied root path before walking it.
    component = root_path
    while True:
        if os.path.islink(component):
            return [("symlink", ".")]
        if component.parent == component:
            break
        component = component.parent
    if not os.path.isdir(root):
        return [("scan-error", ".")]

    findings = []

    def on_walk_error(_error):
        findings.append(("scan-error", "."))

    for current, directories, filenames in os.walk(root, topdown=True, followlinks=False, onerror=on_walk_error):
        directories.sort()
        filenames.sort()
        for directory in list(directories):
            full_path = os.path.join(current, directory)
            rel_path = _relative(root, full_path)
            if os.path.islink(full_path):
                findings.append(("symlink", rel_path))
                directories.remove(directory)
            if _sensitive_name(directory):
                findings.append(("sensitive-file", rel_path))

        for filename in filenames:
            full_path = os.path.join(current, filename)
            rel_path = _relative(root, full_path)
            try:
                metadata = os.lstat(full_path)
            except OSError:
                findings.append(("scan-error", rel_path))
                continue
            if stat.S_ISLNK(metadata.st_mode):
                findings.append(("symlink", rel_path))
                continue
            if _sensitive_name(filename):
                findings.append(("sensitive-file", rel_path))
            if not stat.S_ISREG(metadata.st_mode):
                continue
            try:
                with open(full_path, "rb") as source:
                    content = source.read()
            except OSError:
                findings.append(("scan-error", rel_path))
                continue
            for marker in _SECRET_MARKERS:
                if marker in content:
                    findings.append(("secret-pattern", rel_path))
            for marker in _ABSOLUTE_MARKERS:
                if marker in content:
                    findings.append(("absolute-path", rel_path))

    return sorted(findings)


def main():
    staging_root = Path(__file__).parent.parent
    findings = scan_staging(staging_root)
    if findings:
        for kind, relative_path in findings:
            print(f"{kind}: {relative_path}")
        print(f"FAIL: {len(findings)} finding(s)")
        return 1
    print("OK: no staging findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
