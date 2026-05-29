# NetSentinel Hardware Plugin Ecosystem — Hardening Plan

**Goal:** Any user can drop a Python script into the plugins folder (or click "Add" in the UI)
and get a working hardware integration — first time, every time, without prior knowledge of
the internal architecture.  This is the core differentiator that drives adoption.

---

## Current State Audit (as of v1.9.45)

### What works
- In-process importlib execution (no broken subprocess in frozen builds)
- AppData path copy on `_import_bundled` (stable across PyInstaller runs)
- Startup migration of stale `_MEI*` paths
- Keyring credential storage
- `PipInstallDialog` for plugins that declare `PYPI_PACKAGE`
- `set_error` with pip install button on HubCard

### Known gaps (each is a backlog item below)

| Gap | Impact |
|---|---|
| Missing `PYPI_PACKAGE` in `deco_plugin.py` | First-add silently fails until restart |
| No pre-flight dependency check before add | User sees red error after registering |
| `_apply_result` showed "Online" when `extra.error` was set | Silent failure on hub card |
| No plugin health / success-rate tracking | Random failures invisible to user |
| No test harness to validate a plugin before registering | Breaking plugins get added |
| No template wizard or CLI tool | Author friction; inconsistent plugin structure |
| Multiple instances of same plugin not supported | One ZTE only; one Deco only |
| No plugin version / min_app_version guard | Old plugins silently break on upgrade |
| `_NS_ROOT` baked at class definition time | Fragile when running from AppData |
| No structured error classification (auth vs network vs missing dep) | User can't self-diagnose |

---

## P0 — Stop the Bleeding (must ship in next release)

### P0-1  Pre-flight dependency check in `_import_bundled`  ✅ partially done
- `PYPI_PACKAGE` on each bundled plugin triggers `PipInstallDialog` before registration
- **Remaining:** add `PYPI_PACKAGE = "tplinkrouterc6u"` to `deco_plugin.py` ✅ done
- **Also:** after in-process `exec_module`, catch `ImportError` from the plugin itself and
  surface it as a dep-missing error with install button before writing to QSettings

### P0-2  Surface `extra.error` through `set_error` on HubCard  ✅ done
- `_apply_result` now calls `set_error` and returns early when `extra.error` is set
- The pip-install button auto-appears when the message matches `pip install <pkg>`

### P0-3  `plugin_device_page` banner uses same pip-install detection  
- `_show_banner(err, RED)` should also parse `pip install <pkg>` and offer a one-click install
- Currently the banner is static text — no action button

### P0-4  Worker `_NS_ROOT` must not be baked at class definition time
- `_NS_ROOT = str(Path(__file__).parent.parent)` is computed once when the class is defined
- When running in-process from AppData, the `__file__` context may differ
- Fix: compute at runtime inside `_run_once` using `sys.modules["__main__"].__file__` or
  `get_app_data_dir().parent` as fallback

### P0-5  Smoke-test all bundled plugins on startup (headless, no network)
- On startup, validate each registered plugin with `_validate_script(path)` and check that
  all declared `PYPI_PACKAGE` values are importable
- If a dep is missing, set the card to error state immediately (not after first poll interval)
- Emit a startup warning toast listing broken plugins

---

## P1 — Rock-Solid New-User Experience

### P1-1  Guided "Add Hardware" wizard
- Replace the current flat "Add Integration" button with a 3-step wizard:
  1. **Detect** — run `hw_detect` scan automatically; highlight matched hardware
  2. **Install deps** — show one combined pip install for all missing packages before proceeding
  3. **Authenticate** — credential dialog with live test ("Testing…" spinner → green tick)
- The wizard only completes (writes to QSettings) after the live test passes
- This guarantees the plugin works before it is ever registered

### P1-2  Blocking live-test before registration
- `_import_bundled` must call `get_info()` + `get_status()` in a background thread after the
  credential dialog, BEFORE calling `_save_paths`
- Show "Testing connection…" spinner on the credential dialog
- On success: save, close dialog, show green tick on card
- On failure: show error inline in dialog with specific remediation text; do NOT save

### P1-3  Structured error classification in plugin results
Plugin `extra.error` strings should be machine-readable, not prose.  Introduce a lightweight
convention (no breaking change — just a consistent prefix):

```
"AUTH: wrong password"
"DEPS: tplinkrouterc6u not installed"
"NET: connection refused at 192.168.68.1"
"TIMEOUT: no response in 10 s"
```

`_apply_result` / `_show_banner` parse the prefix and show:
- `AUTH` → "Wrong password — re-enter credentials" + Edit Password button
- `DEPS` → "Missing library: X" + Install button  
- `NET` → "Cannot reach 192.168.68.1 — check IP and firewall"
- `TIMEOUT` → "Device not responding — is it powered on?"

### P1-4  Per-plugin health tracking
Store in QSettings `hardware/health/<path_hash>`:
```json
{"success": 42, "error": 3, "last_ok": 1748000000, "last_err_msg": "..."}
```
- Success rate shown on HubCard as a small "42/45" counter
- Auto-disable plugin after 10 consecutive errors (with "Re-enable" button)
- Circuit-breaker: if plugin hasn't succeeded in 24 h, mark as degraded (amber dot)

### P1-5  Dependency auto-install on startup for registered plugins
- On every startup, for each registered plugin with `PYPI_PACKAGE`, check if importable
- If not importable, show a non-blocking amber toast: "Deco plugin needs tplinkrouterc6u — Install now?"
- One-click install from the toast triggers `PipInstallDialog`
- This covers the "upgrade app but pip env has been reset" case

### P1-6  Plugin reload without restart
- After pip install succeeds, reload the plugin module cache (`importlib.invalidate_caches()`)
  and re-run `_start_poll_worker` — the user should NOT need to restart the app

---

## P2 — Multiple Devices, Richer Config

### P2-1  Multiple instances of the same plugin
Current system: one plugin path → one device.  Users with two Deco systems, or two modems,
cannot add both.

New model: a plugin path is a **type**, not an instance.  Each instance has:
- A display name (e.g. "Office Deco")
- An IP override
- Its own keyring credential: `keyring.set_password("NetSentinel/hardware", instance_id, pw)`
- Its own QSettings key: `hardware/instances/<hash>: {path, ip, name}`

UI: "Add Another Instance" button on each plugin card.  Each instance gets its own card and
its own rail item under Extend.

### P2-2  Typed configuration schema
Plugin metadata may declare a `CONFIG_SCHEMA` dict of typed fields:

```python
CONFIG_SCHEMA = {
    "poll_interval": {"type": "int", "default": 60, "min": 10, "label": "Poll every (s)"},
    "verify_ssl":    {"type": "bool", "default": False, "label": "Verify SSL certificate"},
}
```

`_import_bundled` auto-generates a configuration panel from the schema.  Values passed to
`get_status()` / `get_info()` via a `config: dict` argument (backwards-compatible: default
argument, plugins without it still work).

### P2-3  Plugin icons
Plugin may declare `ICON_URL` (a URL to a small PNG) or include an `icon.png` alongside the
script.  The icon is shown on the HubCard and the rail button.

---

## P3 — Author Tooling & Community

### P3-1  Plugin validator CLI
```powershell
python -m netsentinel.plugin_tools validate plugins/my_plugin.py
```
Checks: required constants, function signatures, PYPI_PACKAGE, no top-level network calls,
no hardcoded passwords, reachable device (optional `--live` flag).

### P3-2  Plugin template generator
In-app "Create plugin from template" in the Hardware page → asks: hardware name, IP,
credential label, PYPI package → writes a ready-to-edit `.py` file to `plugins/`.

### P3-3  In-app output console
Each plugin card has a "Logs" tab showing the last N lines of plugin stdout/stderr.
Currently errors vanish after `set_error` — raw output is never visible to the user.

### P3-4  Community plugin index
A JSON file hosted on GitHub (`netsentinel-plugins/index.json`) listing community plugins:
```json
[
  {
    "name": "Ubiquiti EdgeRouter",
    "author": "community",
    "pypi": "paramiko",
    "file_url": "https://raw.githubusercontent.com/.../edgerouter_plugin.py",
    "sha256": "abc123..."
  }
]
```
In-app "Browse Community Plugins" tab fetches this index and shows install cards.
SHA-256 verified before execution.  No auto-update without user action.

### P3-5  Plugin bundle format (.nspkg)
A `.nspkg` is a ZIP containing:
- `plugin.py` — the main script
- `manifest.json` — name, version, author, pypi deps, min_ns_version
- Optional: `icon.png`, `README.md`

Import by dragging `.nspkg` onto the Hardware page or via "Import from file" button.

---

## P4 — Security & Signing

### P4-1  Unsigned plugin warning
Any plugin not shipped as part of the NetSentinel installer or installed from the official
community index shows a one-time "This plugin runs arbitrary Python code" consent dialog
with the plugin's file path and size.

### P4-2  Official plugin signing
Bundled plugins (in `plugins/`) are SHA-256 hashed at build time and listed in
`data/plugin_hashes.json`.  At runtime the hash is verified before loading.  Tampering shows
a permanent error banner, not silent execution.

### P4-3  Restricted import list (advisory)
Bundled plugins may declare `SAFE_IMPORTS = ["requests", "keyring", "modules.*"]`.
The validator warns (does not block) if the plugin imports anything outside this list.

---

## Test Coverage Plan

Every item above requires tests.  Priorities:

| Test file | Covers |
|---|---|
| `tests/test_plugin_polling_worker.py` | In-process load, error emit, timeout, missing file |
| `tests/test_import_bundled.py` | AppData copy, PYPI_PACKAGE check, credential flow, blocking live-test |
| `tests/test_plugin_health.py` | Success/error counters, circuit-breaker, startup smoke |
| `tests/test_plugin_validator.py` | `_validate_script` edge cases, missing fields, bad syntax |
| `tests/test_hub_card_errors.py` | `extra.error` routing, pip-install button, auth vs net vs deps |
| `tests/test_plugin_migration.py` | Stale `_MEI*` paths replaced, AppData copy idempotent |

Current gap: `workers/plugin_polling_worker.py` has **zero tests**.  This is a blocking RULE-T2
violation.  A worker test must be added before any further plugin changes ship.

---

## Immediate Next Actions (ordered)

1. [x] `tests/test_plugin_polling_worker.py` — lifecycle test (RULE-T2 compliance)  ✅ v1.9.45
2. [x] P0-3: pip-install action button in `plugin_device_page` banner  ✅ v1.9.45
3. [x] P0-4: fix `_NS_ROOT` runtime computation  ✅ v1.9.45
4. [x] P1-2: blocking live-test before registration completes  ✅ v1.9.45
5. [x] P1-3: structured error prefix convention in all bundled plugins  ✅ v1.9.45
6. [x] P0-5: startup smoke-check for registered plugins  ✅ v1.9.45
7. [x] P1-4: per-plugin health tracking  ✅ v1.9.45
8. [x] P2-1: multi-instance support  ✅ v1.9.45
9. [x] P3-3: in-app output console (`≡ Logs` button on HubCard)  ✅ v1.9.46
10. [x] P4-1: unsigned plugin warning dialog + consent tracking  ✅ v1.9.46
11. [x] `tests/test_plugin_validator.py`, `test_plugin_health.py`, `test_plugin_migration.py`, `test_hub_card_errors.py`  ✅ v1.9.46

## Remaining

- P2-2: Typed CONFIG_SCHEMA (plugin declares poll_interval, verify_ssl, etc.)
- P2-3: Plugin icons (ICON_URL or icon.png alongside script)
- P3-1: Plugin validator CLI (`python -m netsentinel.plugin_tools validate`)
- P3-2: Plugin template wizard (in-app "Create from template" with name/IP/cred/pypi fields)
- P3-4: Community plugin index (GitHub-hosted JSON, SHA-256 verified)
- P3-5: Plugin bundle format (.nspkg ZIP)
- P4-2: Official plugin signing (build-time SHA-256 hash list in data/plugin_hashes.json)
- P4-3: Restricted import list (advisory warning for imports outside SAFE_IMPORTS)
- `tests/test_import_bundled.py` — AppData copy, PYPI_PACKAGE check, credential flow

---

*Plan created 2026-05-29.  Sprint 3 completed 2026-05-29 at v1.9.46.*
