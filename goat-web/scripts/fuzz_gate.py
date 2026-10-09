"""Deterministic, offline adversarial fuzzer for goat-web's URL gate."""

from __future__ import annotations

import random
import sys
from pathlib import Path
from urllib.parse import urlsplit


_GATE_DIR = Path(__file__).resolve().parents[1] / "plugins" / "goat-web"
sys.path.insert(0, str(_GATE_DIR))

from url_gate import check_redirect, check_url  # noqa: E402


# Authorities are written exactly as they appear after https://, including
# brackets for IPv6 literals.
PRIVATE_AUTHORITIES = (
    "localhost",
    "LOCALHOST.",
    "printer.local",
    "api.internal",
    "x.localhost",
    "127.0.0.1",
    "127.1",
    "0177.0.0.1",
    "0177.1",
    "2130706433",
    "0x7f000001",
    "0X7F000001",
    "0x7f.1",
    "10.0.0.1",
    "172.16.0.1",
    "192.168.1.2",
    "169.254.169.254",
    "0.0.0.0",
    "100.64.0.1",
    "224.0.0.1",
    "240.0.0.1",
    "[::1]",
    "[::]",
    "[fe80::1]",
    "[fc00::1]",
    "[ff02::1]",
    "[::ffff:127.0.0.1]",
    "[0:0:0:0:0:ffff:7f00:1]",
    "[2002:7f00:1::1]",
    # The well-known NAT64 prefix can translate this literal to 127.0.0.1.
    "[64:ff9b::7f00:1]",
)

UNICODE_PRIVATE_AUTHORITIES = (
    "localhost。",
    "printer。local",
    "127。0。0。1",
    "１２７。０。０。１",
    "localhost．",
    "localhost｡",
)

PUBLIC_AUTHORITIES = (
    "example.com",
    "EXAMPLE.COM",
    "bücher.example",
    "xn--bcher-kva.example",
    "8.8.8.8",
    "[2606:4700:4700::1111]",
)

BAD_PORTS = ("0", "1", "80", "444", "65536", "-1", "+443", "abc", "443x")
NON_HTTPS_SCHEMES = ("http", "ftp", "file", "ws", "gopher")

CREDENTIAL_VARIANTS = (
    "user",
    "user:pass",
    "u%40x:p%3Ass",
    "@",
    "user%3Aname:pa%40ss",
)


def generate_url_cases(count: int = 2600, seed: int = 0x60A7) -> list[tuple[str, bool, bool, str]]:
    """Return (URL, must_reject, must_allow, label) cases, all deterministic."""
    rng = random.Random(seed)
    cases: list[tuple[str, bool, bool, str]] = []
    for index in range(count):
        path = f"/fuzz/{index:04x}"
        mode = index % 12
        private = rng.choice(PRIVATE_AUTHORITIES)
        public = rng.choice(PUBLIC_AUTHORITIES)

        if mode == 0:
            url = f"https://{private}{path}"
            label = "private literal/name"
        elif mode == 1:
            credentials = rng.choice(CREDENTIAL_VARIANTS)
            url = f"https://{credentials}@{public}{path}"
            label = "userinfo"
        elif mode == 2:
            scheme = rng.choice(NON_HTTPS_SCHEMES)
            url = f"{scheme}://{public}{path}"
            label = "non-https scheme"
        elif mode == 3:
            port = rng.choice(BAD_PORTS)
            url = f"https://{private}:{port}{path}"
            label = "private target with odd port"
        elif mode == 4:
            url = f" https://{private}{path} "
            label = "leading/trailing whitespace"
        elif mode == 5:
            long_host = ("a" * 64) + "." + ("b" * 63) + "." + ("c" * 63) + "." + ("d" * 63)
            url = f"https://{long_host}{path}"
            label = "overlong hostname"
        elif mode == 6:
            port = rng.choice(BAD_PORTS)
            url = f"https://{public}:{port}{path}"
            label = "odd port"
        elif mode == 7:
            malformed = rng.choice(("[::1", "[fe80::1%25eth0]", "[::ffff:127.0.0.1]junk"))
            url = f"https://{malformed}{path}"
            label = "malformed/zone-scoped IPv6 authority"
        elif mode == 8:
            unicode_host = rng.choice(UNICODE_PRIVATE_AUTHORITIES)
            url = f"https://{unicode_host}{path}"
            label = "IDNA/unicode private host"
        elif mode == 9:
            # Mix capitalization, a trailing DNS dot, and an encoded-private IP.
            host = rng.choice(("LOCALHOST.", "127.0.0.1.", "0X7F000001", "0177.0.0.1"))
            url = f"HTTPS://{host}{path}"
            label = "mixed-case or alternate numeric host"
        elif mode == 10:
            form = rng.randrange(3)
            if form == 0:
                credentials = rng.choice(CREDENTIAL_VARIANTS)
                url = f"https://{credentials}@{private}{path}"
                label = "userinfo plus private host"
            elif form == 1:
                url = f"http://{private}{path}"
                label = "non-https private host"
            else:
                url = f"https://{private}{path}"
                label = "private address form"
        else:
            # Positive controls ensure the harness also exercises legitimate
            # mixed-case, IDNA, IPv4, and IPv6 HTTPS targets.
            host = rng.choice(PUBLIC_AUTHORITIES)
            if host == "example.com":
                url = f"HTTPS://ExAmPlE.CoM{path}"
            else:
                url = f"https://{host}{path}"
            label = "known public HTTPS control"
            cases.append((url, False, True, label))
            continue
        cases.append((url, True, False, label))

    if len({case[0] for case in cases}) < 2000:
        raise AssertionError("URL generator produced fewer than 2000 distinct URLs")
    return cases


def generate_redirect_cases(count: int = 1400, seed: int = 0xD1EC7) -> list[tuple[object, object, object, bool, bool, str]]:
    """Return (source, location, hops, must_reject, must_allow, label) cases."""
    rng = random.Random(seed)
    cases: list[tuple[object, object, object, bool, bool, str]] = []
    for index in range(count):
        suffix = f"/redirect/{index:04x}"
        private = rng.choice(PRIVATE_AUTHORITIES)
        public = rng.choice(PUBLIC_AUTHORITIES)
        mode = index % 10

        if mode == 0:
            case = ("example.com", f"https://{private}{suffix}", 0, True, False, "absolute private redirect")
        elif mode == 1:
            case = ("example.com", f"//{private}{suffix}", 1, True, False, "protocol-relative private redirect")
        elif mode == 2:
            case = ("example.com", f"https://u:p@{public}{suffix}", 0, True, False, "credentialed redirect")
        elif mode == 3:
            scheme = rng.choice(NON_HTTPS_SCHEMES)
            case = ("example.com", f"{scheme}://{public}{suffix}", 0, True, False, "non-https redirect")
        elif mode == 4:
            case = (f"https://{private}/start", f"/next/{index}", 0, True, False, "private redirect source")
        elif mode == 5:
            case = (f"https://user@{public}/start", f"/next/{index}", 0, True, False, "credentialed redirect source")
        elif mode == 6:
            case = ("example.com", f" https://{private}{suffix} ", 0, True, False, "whitespace redirect target")
        elif mode == 7:
            hop = rng.choice((-1, 2, True, "0", None))
            case = ("example.com", f"/next/{index}", hop, True, False, "invalid redirect hop count")
        elif mode == 8:
            bad_location = rng.choice((None, "", "\\\\127.0.0.1\\x", "http://127.0.0.1/", "https://example.com:444/"))
            case = ("example.com", bad_location, 0, True, False, "malformed or unsafe redirect location")
        else:
            # An explicit two-step chain: the public first hop is valid, while
            # the second hop resolves to a private literal and must be denied.
            source = f"https://chain-{index}.example/start"
            first = f"https://hop-{index}.example/one"
            cases.append((source, first, 0, False, True, "safe first hop in redirect chain"))
            cases.append((first, f"//{private}{suffix}", 1, True, False, "private second hop in redirect chain"))
            cases.append((first, "/third", 2, True, False, "redirect chain hop limit"))
            continue
        cases.append(case)

    # Exercise non-string parameters as well as the URL-shaped cases.
    cases.extend(
        (
            ("example.com", None, 0, True, False, "non-string location"),
            (None, "/next", 0, True, False, "non-string redirect source"),
            ("example.com", "/next", object(), True, False, "opaque hop count"),
        )
    )
    return cases


def _record_result(
    stage: str,
    sample: str,
    result: object,
    must_reject: bool,
    must_allow: bool,
) -> str | None:
    if not isinstance(result, tuple) or len(result) != 2:
        return f"{stage} returned malformed result: {result!r}"
    allowed, code = result
    if type(allowed) is not bool:
        return f"{stage} returned non-bool allowed field: {allowed!r}"
    if must_reject and allowed:
        return f"{stage} allowed forbidden target (code={code!r}): {sample}"
    if must_allow and not allowed:
        return f"{stage} rejected known-public control (code={code!r}): {sample}"
    return None


def _url_has_userinfo(url: str) -> bool:
    try:
        return "@" in urlsplit(url).netloc
    except ValueError:
        return False


def run() -> int:
    failures: list[str] = []
    total_cases = 0
    failure_count = 0
    userinfo_url_cases = 0

    def record(failure: str | None) -> None:
        nonlocal failure_count
        if failure is not None:
            failure_count += 1
            if len(failures) < 20:
                failures.append(failure)

    url_cases = generate_url_cases()
    for url, must_reject, must_allow, label in url_cases:
        total_cases += 1
        has_userinfo = _url_has_userinfo(url)
        if has_userinfo:
            userinfo_url_cases += 1
            if not must_reject:
                record("generator marked userinfo URL as non-reject")
        try:
            result = check_url(url)
        except Exception as exc:  # Any exception is a gate failure.
            record(f"check_url raised {type(exc).__name__}: {label}: {url!r}")
            continue
        record(_record_result("check_url", f"{label}: {url!r}", result, must_reject or has_userinfo, must_allow))

    for value in (None, 1, b"https://example.com", [], {}):
        total_cases += 1
        try:
            result = check_url(value)  # type: ignore[arg-type]
        except Exception as exc:
            record(f"check_url raised {type(exc).__name__} for {value!r}")
            continue
        record(_record_result("check_url", repr(value), result, True, False))

    redirect_cases = generate_redirect_cases()
    for source, location, hops, must_reject, must_allow, label in redirect_cases:
        total_cases += 1
        sample = f"{label}: source={source!r}, location={location!r}, hops={hops!r}"
        try:
            result = check_redirect(source, location, hops)  # type: ignore[arg-type]
        except Exception as exc:
            record(f"check_redirect raised {type(exc).__name__}: {sample}")
            continue
        record(_record_result("check_redirect", sample, result, must_reject, must_allow))

    print(f"total_cases={total_cases}")
    print(f"url_cases={len(url_cases)} distinct_urls={len({case[0] for case in url_cases})}")
    print(f"userinfo_url_cases={userinfo_url_cases}")
    print(f"redirect_cases={len(redirect_cases)}")
    print(f"failures={failure_count}")
    for index, failure in enumerate(failures, start=1):
        print(f"failure[{index}]={failure}")
    return 1 if failure_count else 0


if __name__ == "__main__":
    raise SystemExit(run())
