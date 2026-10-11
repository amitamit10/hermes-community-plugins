"""GOAT startup preflight companion (OUTSIDE the built bundle)."""
import argparse
import importlib.util
import os
import sys
import uuid
from pathlib import Path

PROBE_URL = "https://example.com"
PROBE_HOST = "example.com"
CONSENT_REFUSAL = (
    "GOAT preflight refused: network check not consented; "
    "re-run with --allow-network --bundle <verified-bundle> -- <hermes args> "
    "to opt in to a single https://example.com probe before Hermes starts."
)
PREFLIGHT_FAILURE = (
    "GOAT preflight failed: environment cannot support pinned fetch to https://example.com; "
    "production use requires direct egress with public DNS replies and direct HTTPS/443 with TLS; "
    "mandatory-proxy, private/synthetic/mixed DNS, and restricted egress are unsupported with no proxy fallback; "
    "this may also be a transient outage; "
    "success at this fixed endpoint does not prove general Internet or provider access; "
    "not starting Hermes."
)
BUNDLE_ERROR = (
    "GOAT preflight bundle error: cannot load verified bundle; "
    "pass --bundle <verified hermes-goat-web bundle dir> built by goat-web/scripts/build_plugin_bundle.py; "
    "not starting Hermes."
)
EXEC_ERROR = (
    "GOAT preflight launch error: cannot exec hermes with given args; "
    "ensure hermes is installed and args are 'chat [...]' or 'gateway run [...]'; "
    "not starting Hermes."
)
SUCCESS_RECEIPT = (
    "GOAT preflight passed: https://example.com via pinned_fetch; "
    "starting Hermes; this endpoint is not proof of all providers."
)


def _split(argv):
    items = list(argv)
    if "--" in items:
        i = items.index("--")
        return items[:i], items[i + 1 :]
    return items, []


def _parse(flags):
    p = argparse.ArgumentParser(description="GOAT preflight probe before hermes.")
    p.add_argument("--bundle")
    p.add_argument("--allow-network", action="store_true")
    return p.parse_args(flags)


def _cleanup(pkg):
    for k in tuple(sys.modules):
        if pkg and (k == pkg or k.startswith(pkg + ".")):
            sys.modules.pop(k, None)

def _load_bundle_probe(bdir):
    try:
        d = Path(bdir)
        if not (d.is_dir() and (d / "__init__.py").is_file()
                and (d / "goat_tools.py").is_file() and (d / "bundle-manifest.json").is_file()):
            return None, None
    except Exception:
        return None, None
    pkg = "goat_preflight_bundle_" + uuid.uuid4().hex
    try:
        spec = importlib.util.spec_from_file_location(
            pkg, d / "__init__.py", submodule_search_locations=[str(d)])
        if spec is None or spec.loader is None:
            return None, None
        mod = importlib.util.module_from_spec(spec)
        sys.modules[pkg] = mod
        try:
            spec.loader.exec_module(mod)
            tools = importlib.import_module(pkg + ".goat_tools")
        except Exception:
            _cleanup(pkg)
            return None, None
        probe = getattr(tools, "goat_probe", None)
        if not callable(probe):
            _cleanup(pkg)
            return None, None
        return probe, pkg
    except Exception:
        _cleanup(pkg)
        return None, None

def _probe_ok(r):
    try:
        s = r.get("status")
        return (isinstance(r, dict) and r.get("ok") is True and type(s) is int
                and 200 <= s < 300 and r.get("error") is None and r.get("host") == PROBE_HOST)
    except Exception:
        return False

def main(argv=None, *, _exec=None, _transport=None):
    flags, hermes = _split(sys.argv[1:] if argv is None else argv)
    opts = _parse(flags)
    if not opts.allow_network:
        print(CONSENT_REFUSAL, file=sys.stderr)
        return 2
    if not opts.bundle:
        print(BUNDLE_ERROR, file=sys.stderr)
        return 3
    if not hermes:
        argparse.ArgumentParser(description="GOAT preflight probe before hermes.").error(
            "--bundle and -- <hermes args> are required with --allow-network")
    probe, pkg = _load_bundle_probe(opts.bundle)
    if probe is None:
        print(BUNDLE_ERROR, file=sys.stderr)
        return 3
    try:
        try:
            result = probe(PROBE_URL, transport=_transport) if _transport is not None else probe(PROBE_URL)
        except Exception:
            print(PREFLIGHT_FAILURE, file=sys.stderr)
            return 4
        if not _probe_ok(result):
            print(PREFLIGHT_FAILURE, file=sys.stderr)
            return 4
        print(SUCCESS_RECEIPT, file=sys.stderr)
        try:
            (_exec or os.execvp)("hermes", ["hermes"] + list(hermes))
        except Exception:
            print(EXEC_ERROR, file=sys.stderr)
            return 5
        return 0
    finally:
        _cleanup(pkg)


if __name__ == "__main__":
    raise SystemExit(main())
