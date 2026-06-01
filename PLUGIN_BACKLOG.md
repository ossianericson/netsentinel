# NetSentinel — Plugin System Backlog

**Audit date:** 2026-06-01  
**Auditor:** Claude Code (end-to-end user simulation)  
**Scope:** Both plugin systems — scan plugins (`plugin_system.py`) and hardware plugins (`hub_card.py`/`hub_helpers.py`)

---

## Audit Method

1. Read all plugin-related source files top-to-bottom
2. Simulated user workflow: create plugin → validate → load → run
3. Ran all 9 plugin test files (138 tests) + full suite (2664 tests)
4. Traced path from wizard UI write → loader read — found critical path mismatch
5. Cross-checked docstrings, example code, and canonical risk level enums

---

## Critical Bug Fixed (this session)

### PB-BUG-1 — plugins_dir() fallback did not match wizard write path ✅ FIXED

**File:** `modules/plugin_system.py:98`  
**Symptom:** Any plugin created via the Hardware wizard or .nspkg installer was **invisible to the scan-plugin loader** on a production install.

**Root cause:**
- Wizard writes to: `get_app_data_dir() / "plugins"` → `%LOCALAPPDATA%\NetSentinel\plugins`
- Loader fallback was: `Path.home() / ".config" / "NetSentinel" / "plugins"` → `C:\Users\<user>\.config\NetSentinel\plugins`
- On Windows these are different directories — confirmed by running both paths live.

**Fix applied:** Changed fallback in `plugins_dir()` to `_get_app_data_dir() / "plugins"`, and imported `get_app_data_dir` with the same try/except guard already used for `is_store_app`.

**Test added:** `TestLoadPluginsEdgeCases::test_plugins_dir_fallback_matches_appdata`

---

## Minor Fix Applied (this session)

### PB-FIX-1 — PluginResult.risk_level docstring was wrong ✅ FIXED

**File:** `modules/plugin_system.py:52`  
**Issue:** Comment said `# LOW / MEDIUM / HIGH / CRITICAL` but the example plugin (and the internal scan risk system) also uses `CLEAN`. Updated to `# LOW / MEDIUM / HIGH / CLEAN / CRITICAL`.

---

## Missing Tests Fixed (this session)

11 new tests added to `tests/test_plugin_system.py`, covering:

| Test | What it catches |
|---|---|
| `test_run_plugin_run_fn_none_reports_load_failure` | `_run_fn=None` must produce a non-empty `.error` |
| `test_run_plugin_run_fn_raises_captured_as_error` | Runtime exceptions in plugins must be caught |
| `test_run_plugin_wrong_return_type_reported` | Plugin returning `dict` instead of `PluginResult` |
| `test_run_plugin_store_app_returns_disabled_error` | Store build guard path |
| `test_underscore_files_are_skipped` | `_private.py` must not be loaded |
| `test_broken_plugin_included_with_none_run_fn` | Syntax-error plugin appears with `_run_fn=None` |
| `test_ensure_example_plugin_idempotent` | Writing example must not overwrite existing files |
| `test_ensure_example_plugin_writes_when_empty` | Writing example to an empty dir |
| `test_plugins_dir_fallback_matches_appdata` | Fallback path alignment |
| `test_template_passes_validate_plugin` | Wizard _TEMPLATE passes `validate_plugin()` |
| `test_template_is_hardware_plugin_not_scan_plugin` | Template is NOT a scan plugin (documents the dual-system boundary) |

---

## Architecture Clarification (for future contributors)

NetSentinel has **two completely separate plugin systems**. They share a directory but serve different purposes:

| System | Files | Discovery | Required API | Used by |
|---|---|---|---|---|
| **Scan plugins** | `modules/plugin_system.py` | Auto-scanned from `plugins/` dir | `PLUGIN_META` dict + `run(devices)` | Security Audit → Plugins page |
| **Hardware plugins** | `ui/widgets/hub_card.py`, `hub_helpers.py`, `workers/plugin_polling_worker.py` | User-selected file or .nspkg | `HARDWARE_NAME`, `HARDWARE_TYPE`, `get_info()`, `get_status()` | Extend → Hardware page |

The wizard (`ui/pages/plugin_wizard_mixin.py`) creates **hardware plugins**.  
The validator CLI (`python -m modules.plugin_tools validate`) validates **hardware plugins**.  
`load_plugins()` discovers **scan plugins**.

**These must not be confused.** A hardware plugin template will be silently skipped by `load_plugins()` (no `run()` function, no `PLUGIN_META`) — this is by design and is now documented by a test.

---

## Open Backlog Items

### Priority 1 — User can actually create a working scan plugin

**PB-1** — End-to-end scan plugin creation guide in the UI  
*Current state:* There is no wizard or "New Plugin" button for scan plugins. The only wizard creates hardware plugins. A user wanting to write a scan plugin has to find the auto-generated `example_open_ports_report.py` file manually.  
*Required:* Add a "New Scan Plugin" button on the Plugins page (Security Audit section) that opens a simplified wizard (name, description, tags, output fields) and writes a scan-plugin template with `PLUGIN_META` + `run()`.  
*Effort:* M  

**PB-2** — Scan plugin validator (separate from hardware plugin validator)  
*Current state:* `plugin_tools.py` validates hardware plugins. No equivalent for scan plugins.  
*Required:* `validate_scan_plugin(path)` that checks: valid Python, `PLUGIN_META` present, `run()` callable, `run()` accepts `(devices, **kwargs)`.  
*Effort:* S  

**PB-3** — Reload button on the Plugins page  
*Current state:* After a user drops a `.py` file into the plugins folder, they must restart the app to see it.  
*Required:* Add a "Reload Plugins" button that calls `load_plugins()` and refreshes the table without restarting.  
*Effort:* S  

### Priority 2 — Plugin authoring feedback loop

**PB-4** — Inline validator result on the Plugins page  
*Current state:* The validator CLI (`python -m modules.plugin_tools validate`) is only documented in CLAUDE.md. No in-app equivalent.  
*Required:* Each row in the Plugins table should show a coloured status badge (green/amber/red) that reflects `validate_plugin()` result. Clicking shows the full issue list.  
*Effort:* M  

**PB-5** — "Run this plugin" dry-run button on the Plugins page  
*Current state:* Scan plugins can only be run as part of a full scan. There's no way to test a plugin against the last scan result.  
*Required:* Right-click context menu on each plugin row → "Test with last scan" → runs the plugin against `_m1_result["devices"]` → shows the `PluginResult` in a dialog.  
*Effort:* S  

**PB-6** — Plugin sandbox output log  
*Current state:* If a scan plugin raises an error, the error appears in `PluginResult.error` but is never surfaced in the UI.  
*Required:* Show a truncated traceback in a collapsed "Error details" section in the plugin result row. Map to RULE-A2 (translate errors to plain English where possible).  
*Effort:* S  

### Priority 3 — Plugin Ecosystem (remaining P-items from main backlog)

**PB-7** — Typed CONFIG_SCHEMA (P2-2)  
Plugin declares `CONFIG_SCHEMA = {"poll_interval": {"type": "int", "default": 60}, ...}`; the Hub card auto-generates a config panel.  
*Effort:* M  

**PB-8** — Community plugin index (P3-4)  
GitHub-hosted JSON index; SHA-256 verified before install; in-app "Browse" tab in Hardware page.  
The `plugin_registry.py` module already implements the network layer — the UI is the missing piece.  
*Effort:* M  

**PB-9** — Plugin bundle format UI (P3-5)  
`.nspkg` ZIP format is implemented in `modules/nspkg.py` with full test coverage.  
Missing: in-app "Install from .nspkg" button on the Hardware page.  
*Effort:* S  

### Priority 4 — Hardening

**PB-10** — Plugin directory race condition  
`plugins_dir()` calls `mkdir(exist_ok=True)` on every call. In multi-threaded startup this is safe but adds disk I/O every time any plugin API is called. Cache the result after the first successful call.  
*Effort:* XS  

**PB-11** — Scan plugin API versioning  
`PLUGIN_META` has no `api_version` field. If the `PluginResult` or `run()` contract changes in future, there's no way to detect stale plugins.  
*Required:* Add optional `PLUGIN_META["api_version"] = "1"`. Warn (not block) if absent.  
*Effort:* XS  

**PB-12** — Windows path length limit for plugin install  
`install_plugin()` in `plugin_registry.py` writes directly to `plugins_dir()`. On Windows, if the plugin filename + AppData path exceeds 260 chars, `write_bytes()` raises `FileNotFoundError`. No test or guard for this.  
*Required:* Truncate filenames to 80 chars before install; add a test.  
*Effort:* XS  

---

## Test Coverage Summary (after this session)

| File | Tests before | Tests after | New coverage |
|---|---|---|---|
| `tests/test_plugin_system.py` | 15 | 26 | Store-app guard, `_run_fn=None`, broken plugin, skip `_` files, idempotency, template validation, dual-system boundary |
| `tests/test_plugin_tools.py` | 22 | 22 | No change — already good |
| `tests/test_plugin_registry.py` | 18 | 18 | No change |
| `tests/test_plugin_resilience.py` | 15 | 15 | No change |
| `tests/test_plugin_isolation.py` | 5 | 5 | No change |
| `tests/test_plugin_health.py` | 11 | 11 | No change |
| `tests/test_plugin_migration.py` | 6 | 6 | No change |
| `tests/test_plugin_validator.py` | 14 | 14 | No change |
| `tests/test_nspkg.py` | 20 | 20 | No change |
| **Total** | **126** | **137** | +11 |

Full suite: **2675 passed, 5 skipped** (was 2664 before this session).

---

## Sprint Queue (recommended order)

| Sprint | Items | Effort |
|---|---|---|
| Sprint A | PB-3 (reload button), PB-5 (dry-run), PB-10 (cache dir) | S+S+XS |
| Sprint B | PB-2 (scan validator), PB-4 (inline validator badge), PB-11 (api_version) | S+M+XS |
| Sprint C | PB-1 (scan plugin wizard), PB-6 (error log) | M+S |
| Sprint D | PB-8 (community index UI), PB-9 (nspkg install UI) | M+S |
| Sprint E | PB-7 (CONFIG_SCHEMA UI), PB-12 (path length guard) | M+XS |

---
*Generated by end-to-end plugin audit, 2026-06-01*
