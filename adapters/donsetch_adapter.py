"""Fail-closed availability stub for the Donsetch MCP adapter.

On this Hermes VPS, the installed ``donsetch-mcp-hermes`` and
``donsetch-hardened`` binaries fail to load because ``GLIBC_2.39`` is missing;
the ``donsetch_hardened`` MCP is disabled. This module intentionally does not
launch either binary or pretend the service works. It only checks whether the
configured executable is present, using an injectable ``binary_checker`` for
tests and alternate hosts.

The checker contract is ``checker(path) -> bool``: ``False`` means the binary
is not installed/configured, and ``True`` means it is present. Presence is not
runtime health: on the verified host it still returns ``UNAVAILABLE`` with the
known glibc diagnostic. A checker may raise ``FileNotFoundError`` for a missing
binary or an ``OSError`` containing a glibc diagnostic for a broken binary.
"""

import os

MISSING_CONFIG = "MISSING_CONFIG"
UNAVAILABLE = "UNAVAILABLE"
DEFAULT_BINARY_PATH = None  # set to your donsetch-mcp-hermes path or pass an explicit checker
GLIBC_EXPLANATION = (
    "Donsetch is unavailable: the installed donsetch-mcp-hermes and "
    "donsetch-hardened binaries require GLIBC_2.39, which is not available "
    "on this host; the donsetch_hardened MCP is disabled."
)
MISSING_EXPLANATION = (
    "Donsetch binary is missing or not executable; install/configure "
    "donsetch-mcp-hermes before use."
)
CHECKER_FAILURE_EXPLANATION = "Donsetch binary availability could not be verified."


def _default_binary_checker(path):
    """Check file presence/execute permission without running the binary."""
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _failure(error, explanation):
    """Construct a fail-closed result; this adapter never returns success."""
    return {"ok": False, "error": error, "explanation": explanation}


class DonsetchAdapter:
    """Documented availability-only stub for Donsetch.

    ``binary_checker`` is an injectable callable accepting the executable
    path and returning a bool. No network, subprocess, or MCP call is made.
    Even when the binary exists, ``check`` reports ``UNAVAILABLE`` because
    the installed build is known to require the missing ``GLIBC_2.39``.
    """

    def __init__(self, binary_checker=None, *, binary_path=DEFAULT_BINARY_PATH):
        self.binary_path = None if binary_path is None else os.fspath(binary_path)
        self._binary_checker = (
            _default_binary_checker if binary_checker is None else binary_checker
        )

    def check(self):
        """Return ``MISSING_CONFIG`` or ``UNAVAILABLE``; never claim success."""
        if not callable(self._binary_checker):
            return _failure(MISSING_CONFIG, MISSING_EXPLANATION)

        try:
            present = self._binary_checker(self.binary_path)
        except Exception as exc:
            detail = str(exc).lower()
            if "glibc" in detail or "ld-linux" in detail:
                return _failure(UNAVAILABLE, GLIBC_EXPLANATION)
            if isinstance(exc, FileNotFoundError):
                return _failure(MISSING_CONFIG, MISSING_EXPLANATION)
            return _failure(UNAVAILABLE, CHECKER_FAILURE_EXPLANATION)

        if present is False:
            return _failure(MISSING_CONFIG, MISSING_EXPLANATION)
        if present is True:
            return _failure(UNAVAILABLE, GLIBC_EXPLANATION)
        return _failure(UNAVAILABLE, CHECKER_FAILURE_EXPLANATION)


__all__ = [
    "DEFAULT_BINARY_PATH",
    "GLIBC_EXPLANATION",
    "MISSING_CONFIG",
    "UNAVAILABLE",
    "DonsetchAdapter",
]
