# GOAT V3 Quickstart (5-Min Path)

Offline-first validation using the built `hermes-goat-web` bundle. No API keys, no network, no live plugin enable required.

## 0. Network contract — read before any build/run with network

GOAT itself is Python standard library only (3.11+). The Hermes host is a separate dependency floor: Hermes Agent must be installed for read-only `validate`/`doctor` checks, and every native command below runs through the approved installed interpreter — never the shared auto-repair `hermes` launcher.

`pinned_fetch` dials by system DNS, then pins the connection:

- System DNS must return **only globally-public approved IPv4/IPv6 addresses per hostname** — no mixed, private, or synthetic replies. The resolver itself may be internal as long as its answers are genuinely public.
- The connection goes **direct to the validated IP over HTTPS/443 with the original host for TLS/SNI** (timeout 10s, 1 MiB cap, 0 redirects — unchanged). `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` are **never used**; there is no proxy fallback.
- Private/synthetic/mixed DNS, mandatory-proxy-only, and restricted-egress environments **fail closed**. A normal NAT with public DNS answers and direct HTTPS egress is **supported**, not inherently broken. Proxy variables being set does **not** disqualify a machine while direct access works.
- A TLS handshake failure and similar transport errors may be **transient**. One `https://example.com` success proves only that endpoint — not providers, and not DNS for every host.

## Prerequisites

- Python 3.11+, `git`, Hermes Agent (for read-only `validate` checks)
- Stdlib only for GOAT — no `pip install`, no `PYTHONPATH`
- Authoritative references: Hermes developer plugin guide (`https://hermes-agent.nousresearch.com/docs/developer-guide/plugins`) plus the Hermes user plugin docs. Ground truth reviewed: GOAT base `1311d89a76adeb3d4b56e281014991ee3a83f3f5` against Hermes source HEAD `66605471e9f0b0832abbefaf625ce08e948ca540` (native runtime `3.14.7`).

## 1. Clone (portable)

```sh
git clone <repo-url> goat
cd goat
python3 --version  # 3.11+
ls goat-web/plugins/goat-web/plugin.yaml goat-web/scripts/build_plugin_bundle.py
```

> `goat-web/plugins/goat-web/` is a source template — it imports `._goat_v3_vendor` which exists only in a built bundle. The source tree is **not installable**; only builder output is validatable.

## 2. Read-only native wrapper (no install, no enable)

Every native command uses the approved installed interpreter directly (`-I -B -m hermes_cli.main` — not `-S`, host deps are needed), with a disposable scratch environment and a credential-free `env -i`. `PYTHONDONTWRITEBYTECODE=1` is set **explicitly** because `-B` on the parent alone does not propagate to the validator's `-c` child (default `validate` writes 14 `.pyc` files, after which `--check` fails). Never pass `--install-deps`, and never run the shared launcher (it can auto-repair). `RUNTIME` must point at the approved installed Hermes source version:

```sh
SCRATCH=<disposable-empty-dir>  # fresh per run
mkdir -p "$SCRATCH/home" "$SCRATCH/tmp" "$SCRATCH/xdg-cache" "$SCRATCH/xdg-config" "$SCRATCH/xdg-data" "$SCRATCH/xdg-state"
RUNTIME="${GOAT_HERMES_RUNTIME_PYTHON:-<approved-hermes-python>}"
hermes_readonly() {
  env -i PATH=/usr/bin:/bin LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    HOME="$SCRATCH/home" HERMES_HOME="$SCRATCH/home" \
    TMPDIR="$SCRATCH/tmp" TEMP="$SCRATCH/tmp" TMP="$SCRATCH/tmp" \
    XDG_CACHE_HOME="$SCRATCH/xdg-cache" XDG_CONFIG_HOME="$SCRATCH/xdg-config" \
    XDG_DATA_HOME="$SCRATCH/xdg-data" XDG_STATE_HOME="$SCRATCH/xdg-state" \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    HERMES_DEV=1 HERMES_DISABLE_LAZY_INSTALLS=1 HERMES_ENABLE_PROJECT_PLUGINS=0 \
    "$RUNTIME" -I -B -m hermes_cli.main "$@"
}
hermes_readonly --help  # confirm flags on your Hermes version first
```

This isolation is **not** a network sandbox or a no-write guarantee: `doctor` executes trusted code, and host-side unrelated imports still run. For enforced no-network gates, prefer the audited native unittest gates (`goat-web/tests/test_hermes_registration.py`).

## 3. Build, native checks, manifest check (in this order)

```sh
python3 -B goat-web/scripts/build_plugin_bundle.py --output /tmp/hermes-goat-web  # fresh dir required
hermes_readonly plugins validate /tmp/hermes-goat-web
hermes_readonly plugins doctor /tmp/hermes-goat-web --ci
python3 -B goat-web/scripts/build_plugin_bundle.py --check /tmp/hermes-goat-web
# ok /tmp/hermes-goat-web
ls /tmp/hermes-goat-web/bundle-manifest.json
```

Only `/tmp/hermes-goat-web` is standalone and Hermes-validatable. Registration (`register_fn(ctx)` via the directory loader) runs at discovery — not only at first startup — and `doctor`/`validate` perform real registration/capability probes; none of them ever invoke the network preflight below. Do not weaken the strict bundle inventory.

## 4. Deliberate startup companion (opt-in preflight, not automatic)

Plain `hermes chat` / `hermes gateway run` alone are **not** protected. The supported gating entrypoint is the reviewed companion `goat-web/scripts/start_with_preflight.py`, which checks once via the real `goat_probe` default `pinned_fetch` path and only then `os.execvp("hermes", ["hermes"] + args)`. It is a startup gate, not a manual probe utility. (Hermes does expose `on_session_start`, but no reviewed universal fail-closed network gate was established — choosing this explicit entrypoint instead of registration-time I/O is deliberate.)

The companion lives **outside** the deterministic bundle (no builder/manifest addition). Keep the reviewed script alongside the reviewed built bundle and verify `builder --check` first. The manifest-presence check is **not** integrity verification, a signature, or authorization to load arbitrary code — load only reviewed artifacts.

Offline first (no bundle import, no DNS/socket, no exec):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B goat-web/scripts/start_with_preflight.py --help  # exit 0
PYTHONDONTWRITEBYTECODE=1 python3 -B goat-web/scripts/start_with_preflight.py --bundle /tmp/hermes-goat-web -- chat
# exit 2: one consent-refusal line on stderr, nothing launched
```

After separate approvals for a network startup **and** for the correct already-staged/enabled target profile — examples, **not executed**:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B <repo>/goat-web/scripts/start_with_preflight.py --bundle <reviewed-built-bundle> --allow-network -- chat [...]
PYTHONDONTWRITEBYTECODE=1 python3 -B <repo>/goat-web/scripts/start_with_preflight.py --bundle <reviewed-built-bundle> --allow-network -- gateway run [...]
```

`--allow-network` consents **per invocation** (no env trigger, no remembered state). On success the wrapper prints exactly one fixed receipt line on stderr, then execs Hermes; on an unsuccessful check it prints exactly one sanitized actionable line (exit 4) with no exec, no retry, and no proxy fallback. Bundle-load failures (exit 3) and exec failures (exit 5, after the success receipt — a launch diagnostic, not an environment diagnostic) are separate. No automatic integration is claimed for normal `hermes` commands or services; pointing a service at the companion needs a separately approved service change (**not done**).

## 5. Validate offline (reproducible, no hardcoded totals)

```sh
python3 -B -m unittest discover -s adapters -p "test_*.py" -v
python3 -B -m unittest discover -s goat-web/tests -p "test_*.py" -v
python3 -B -m unittest discover -s goat-ultimate/tests -p "test_*.py" -v
python3 goat-web/scripts/fuzz_gate.py   # correctness fuzzer, offline
python3 goat-web/scripts/audit_staging.py  # narrow heuristic
```

No `| head` / `| tail` above — pipes would mask the exit code. Keep full local output as the receipt; no totals are quoted here and no CI-green claim is made (the repo root has no `.github/workflows`; the tracked nested `goat-web/.github/workflows/goat-gate.yml` is not a root Actions workflow). Historical QA (422 collected, 416 passed, 6 skipped at base `1311d89a`) is history and the user baseline — not the current modified total. The 27 portable-bundle checks are a **subset** of the `goat-web/tests` suite; never double-count them.

The six native gates in `test_hermes_registration.py` skip without `GOAT_HERMES_SOURCE_ROOT` / `GOAT_HERMES_RUNTIME_PYTHON` (or the suite's known fallback install paths). Skipped is **not** passed and not integration proof.

## 6. Try the seven tools with fake transports

**Search (DuckDuckGo HTML):**

```python
from adapters.free_stack import duckduckgo_search
def fake(url):
    assert url.startswith("https://html.duckduckgo.com/html/?q=")
    return {"body": '<a class="result__a" href="https://example.org/cats">Cats</a><div class="result__snippet">Feline</div>'}
print(duckduckgo_search("cats", transport=fake))
# {'ok': True, 'results': [...]}
```

**Extractive answer (Wikipedia, extractive, not LLM):**

```python
from adapters.answer_synth import goat_answer
def fake_search(q):
    return {"ok": True, "results": [{"title": "Cat", "url": "https://example.org/cat", "snippet": "Cats were domesticated in the Near East. Early cats lived with humans."}]}
print(goat_answer("cats domestication", search=fake_search, max_results=2))
# {'ok': True, 'answer': '... [1]', 'sources': [...]}
```

**Filtered search (inclusive UTC, domains, language):**

```python
from adapters.search_filters import with_search_filters
wrapped = with_search_filters(lambda q: {"ok": True, "results": [{"title": "P", "url": "https://example.org/p", "published": "2024-06-01", "language": "en-US"}]}, time_after="2024-01-01", language="en")
print(wrapped("q"))
```

**Verticals (Crossref/GDELT/Commons — metadata + links only):**

```python
from adapters.free_verticals import scholar_search, news_search, image_search
print(scholar_search("graphs", transport=lambda u: {"body": '{"message":{"items":[{"title":"T","URL":"https://example.org/d","DOI":"10.1/x"}]}}'}))
```

Every success envelope is `{"ok": true, ...}`. Failures are `URL_BLOCKED`, `REDIRECT_BLOCKED`, `MISSING_CONFIG` — plus `PROVIDER_BLOCKED` for provider bot-challenge blocks. That fourth code needs the provider-sibling P1-2 fix and is **not** supported by baseline `1311d89a` alone: validation/type/URL failures stay `URL_BLOCKED`, a provider challenge is not a URL-gate or environment failure, and a passing startup probe does not guarantee DuckDuckGo. See `SECURITY.md` and `TROUBLESHOOTING.md`.
