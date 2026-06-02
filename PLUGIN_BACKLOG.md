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

**PB-3** ✅ — Reload button on the Plugins page *(was already implemented; regression test added)*  
*Current state:* `↺ Reload Plugins` button exists in `ui/tabs_recon.py`, calls `_reload_plugins()` → `load_plugins()`.  
*Effort:* S  

### Priority 2 — Plugin authoring feedback loop

**PB-4** — Inline validator result on the Plugins page  
*Current state:* The validator CLI (`python -m modules.plugin_tools validate`) is only documented in CLAUDE.md. No in-app equivalent.  
*Required:* Each row in the Plugins table should show a coloured status badge (green/amber/red) that reflects `validate_plugin()` result. Clicking shows the full issue list.  
*Effort:* M  

**PB-5** ✅ — "Run this plugin" dry-run button on the Plugins page  
*Implemented:* Right-click → `▶ Test with last scan` runs the plugin in `_run_plugin_in_dialog()` and shows `PluginResult` in a `QDialog`. Right-click → `Copy name` copies the plugin name to the clipboard.  
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

**PB-10** ✅ — Plugin directory race condition  
*Implemented:* Added `_plugins_dir_cache: Optional[Path] = None` to `modules/plugin_system.py`. `plugins_dir()` returns the cached result on all calls after the first, eliminating repeated `mkdir()` I/O.  
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

| Sprint | Items | Effort | Status |
|---|---|---|---|
| Sprint A | PB-3 (reload button), PB-5 (dry-run), PB-10 (cache dir) | S+S+XS | ✅ Done 2026-06-02 |
| Sprint B | PB-2 (scan validator), PB-4 (inline validator badge), PB-11 (api_version) | S+M+XS | |
| Sprint C | PB-1 (scan plugin wizard), PB-6 (error log) | M+S | |
| Sprint D | PB-8 (community index UI), PB-9 (nspkg install UI) | M+S | |
| Sprint E | PB-7 (CONFIG_SCHEMA UI), PB-12 (path length guard) | M+XS | |

---

## Sprint A Completion Notes (2026-06-02)

**PB-3 ✅** — Reload Plugins button (`↺ Reload Plugins`) was already present in `ui/tabs_recon.py` before this sprint. Added regression test `TestPluginReloadButton::test_reload_button_and_method_exist_in_source` confirming it is wired.

**PB-5 ✅** — Added right-click context menu to `_plugin_list_table` in `_build_recon_plugin_tab()`:
- `Qt.ContextMenuPolicy.CustomContextMenu` policy set
- `customContextMenuRequested` → `_on_plugin_table_context()` handler
- Menu actions: `▶ Test with last scan` (runs plugin via `_run_plugin_in_dialog()`, shows `PluginResult` in a modal `QDialog`) and `Copy name`
- 2 new tests: `TestPluginTableContextMenu`

**PB-10 ✅** — Added `_plugins_dir_cache: Optional[Path] = None` module-level variable to `modules/plugin_system.py`. `plugins_dir()` now returns the cached `Path` on every call after the first, eliminating repeated `mkdir()` I/O. 2 new tests: `TestPluginsDirCache`.

**Suite after sprint:** 2680 passed, 5 skipped (was 2675 before).

---

## Next Sprint: Sprint B

| Item | File(s) to create/modify | Key detail |
|---|---|---|
| PB-2 | `modules/plugin_system.py` | `validate_scan_plugin(path)` — check valid Python, `PLUGIN_META` present, `run()` callable and accepts `(devices, **kwargs)` |
| PB-4 | `ui/tabs_recon.py` | Add `Status` column to plugin table; call `validate_scan_plugin()` per row; coloured `●` badge (green/amber/red); click shows issue list in tooltip or dialog |
| PB-11 | `modules/plugin_system.py` | Warn (not block) when `PLUGIN_META` has no `"api_version"` key; add to `PluginInfo` |

---
*Generated by end-to-end plugin audit, 2026-06-01. Sprint A completed 2026-06-02.*
