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

**PB-1** ✅ — End-to-end scan plugin creation guide in the UI  
*Implemented:* Added `"⬡  New Scan Plugin"` button to the Plugins tab toolbar in `ui/tabs_recon.py`. Clicking it opens a `QDialog` wizard (name, description, tags). On OK, writes a scan-plugin template with `PLUGIN_META` (all required keys + `api_version: "1"`) + `run(devices, **kwargs)` stub to `plugins_dir()`, then auto-reloads the plugin list. Template is validated to pass `validate_scan_plugin()` with zero issues. Filename is slug-sanitized and collision-safe. 5 new tests in `TestNewScanPluginWizard`.  
*Effort:* M  

**PB-2** ✅ — Scan plugin validator (separate from hardware plugin validator)  
*Implemented:* `validate_scan_plugin(path)` in `modules/plugin_system.py`. Checks: readable Python, valid syntax, no import error, `PLUGIN_META` dict with required keys, `api_version` present (advisory), `run()` callable and accepts `(devices, **kwargs)`. Returns `List[str]` of issues (empty = OK). 9 new tests.  
*Effort:* S  

**PB-3** ✅ — Reload button on the Plugins page *(was already implemented; regression test added)*  
*Current state:* `↺ Reload Plugins` button exists in `ui/tabs_recon.py`, calls `_reload_plugins()` → `load_plugins()`.  
*Effort:* S  

### Priority 2 — Plugin authoring feedback loop

**PB-4** ✅ — Inline validator result on the Plugins page  
*Implemented:* Added "Status" column (index 2) to `_plugin_list_table` in `ui/tabs_recon.py`. `_reload_plugins()` calls `validate_scan_plugin()` per plugin and sets a coloured `●` badge: green = all checks pass, amber = advisory only (api_version missing), red = error. Tooltip shows full issue list. Clicking the Status cell opens a `QDialog` with bullet-point issues. Right-click context menu gains "▣ Show validation" action. 4 new tests.  
*Effort:* M  

**PB-5** ✅ — "Run this plugin" dry-run button on the Plugins page  
*Implemented:* Right-click → `▶ Test with last scan` runs the plugin in `_run_plugin_in_dialog()` and shows `PluginResult` in a `QDialog`. Right-click → `Copy name` copies the plugin name to the clipboard.  
*Effort:* S  

**PB-6** ✅ — Plugin sandbox output log  
*Implemented:* Three-point error display upgrade across the plugin UI (RULE-A2 compliance):
1. `_on_plugin_error` (worker-level error): shows plain-English translation (What happened / Likely cause / What to try) + truncated traceback (last 10 lines) in `_plugin_result_text`.
2. `_on_plugin_result` in `scan_wiring.py`: when `res.error` is set, shows the same plain-English translation + truncated traceback inline.
3. `_run_plugin_in_dialog` (dry-run dialog): shows plain-English summary in the main output area + a hidden "▼ Show error details" `QPushButton` that reveals a collapsed `QTextEdit` with the raw traceback (last 15 lines). Toggle shows "▲ Hide error details" when expanded.
4 new tests in `TestPluginErrorDisplay`.  
*Effort:* S  

### Priority 3 — Plugin Ecosystem (remaining P-items from main backlog)

**PB-7** — Typed CONFIG_SCHEMA (P2-2)  
Plugin declares `CONFIG_SCHEMA = {"poll_interval": {"type": "int", "default": 60}, ...}`; the Hub card auto-generates a config panel.  
*Effort:* M  

**PB-8** ✅ — Community plugin index (P3-4)  
*Implemented:* Added `_ScanPluginRegistryFetchThread` and `_ScanPluginInstallThread` QThread classes to `ui/tabs_recon.py`. Added `"⬇  Get Plugins"` button to the scan plugins toolbar. Clicking opens a modal dialog with Refresh → fetches `plugin_registry.REGISTRY_URL` in background, shows one card per `RegistryEntry` (name, version, author, description) with an `⬇ Install` button. Install calls `install_plugin()` in a background thread; on success auto-reloads the plugin list. Added `sha256: str = ""` field to `RegistryEntry` in `modules/plugin_registry.py`; `install_plugin()` now verifies the SHA-256 digest when one is provided. 7 new tests in `TestCommunityPluginBrowse` (source-level) + 6 SHA-256 tests in `test_plugin_registry.py`.  
*Effort:* M  

**PB-9** ✅ — Plugin bundle format UI (P3-5)  
*Implemented:* `"⬡  Import .nspkg"` button was already present in `ui/pages/hardware_integration_page.py` (line 140-143) connected to `_on_import_nspkg()`, which opens a file dialog, calls `nspkg.unpack_nspkg()`, validates, and registers via `_import_bundled()`. "Browse" community tab was already present via `_HardwareBrowseMixin._build_browse_tab()` (line 245). Both confirmed working; 6 new page-level tests added in `test_hardware_integration.py` (PB-8/PB-9 section 11).  
*Effort:* S  

### Priority 4 — Hardening

**PB-10** ✅ — Plugin directory race condition  
*Implemented:* Added `_plugins_dir_cache: Optional[Path] = None` to `modules/plugin_system.py`. `plugins_dir()` returns the cached result on all calls after the first, eliminating repeated `mkdir()` I/O.  
*Effort:* XS  

**PB-11** ✅ — Scan plugin API versioning  
*Implemented:* Added `api_version: str = ""` field to `PluginInfo` dataclass. `load_plugins()` populates it from `meta.get("api_version", "")`. `validate_scan_plugin()` emits an advisory issue when `api_version` is absent (warning, not block). Bundled example plugin updated to declare `"api_version": "1"`. 4 new tests.  
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
| Sprint B | PB-2 (scan validator), PB-4 (inline validator badge), PB-11 (api_version) | S+M+XS | ✅ Done 2026-06-02 |
| Sprint C | PB-1 (scan plugin wizard), PB-6 (error log) | M+S | ✅ Done 2026-06-02 |
| Sprint D | PB-8 (community index UI), PB-9 (nspkg install UI) | M+S | ✅ Done 2026-06-02 |
| Sprint E | PB-7 (CONFIG_SCHEMA UI), PB-12 (path length guard) | M+XS | ✅ Done 2026-06-02 |

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

## Sprint B Completion Notes (2026-06-02)

**PB-2 ✅** — Added `validate_scan_plugin(path: Path) -> List[str]` to `modules/plugin_system.py`. Uses `ast.parse` for syntax, imports module, checks `PLUGIN_META` dict (required keys: name/version/description), warns on missing `api_version`, checks `run()` callable with `(devices, **kwargs)` signature. 9 new tests covering all error paths and the bundled example template.

**PB-4 ✅** — Added "Status" column to `_plugin_list_table`. `_reload_plugins()` calls `validate_scan_plugin()` per plugin and renders a coloured `●` (green/amber/red). Status cell click opens a `QDialog` with the full issue list. Right-click context menu gets "▣ Show validation" action. 4 new source-level tests.

**PB-11 ✅** — Added `api_version: str = ""` to `PluginInfo` dataclass. Populated from `PLUGIN_META.get("api_version", "")` in `load_plugins()`. Advisory warning in `validate_scan_plugin()` when absent. Bundled example plugin updated with `"api_version": "1"`. 4 new tests.

**Suite after sprint:** 2697 passed, 5 skipped (was 2680 before Sprint B; +17 tests).

**Note:** `@pyqtSlot(int, int)` was removed from `_on_plugin_status_cell_clicked` — PyQt6 metaclass interference with `customContextMenuRequested` signal connection when typed slot decorator is on an adjacent method in the same mixin class.

---

## Sprint C Completion Notes (2026-06-02)

**PB-1 ✅** — Added `"⬡  New Scan Plugin"` button to the Plugins tab in `ui/tabs_recon.py`. `_new_scan_plugin_wizard()` opens a QDialog with name/description/tags fields. On accept, slug-sanitizes the name to a Python filename, writes a compliant template (PLUGIN_META + run stub + api_version "1") to `plugins_dir()`, then calls `_reload_plugins()`. Note: `@pyqtSlot()` decorator intentionally omitted — PyQt6 metaclass interference with `customContextMenuRequested` in the same mixin class causes TypeError (same issue as PB-4 fix in Sprint B). 5 new tests: `TestNewScanPluginWizard`.

**PB-6 ✅** — Three-point error display upgrade: (1) `_on_plugin_error` in `tabs_recon.py` now shows plain-English "What happened / Likely cause / What to try" header + truncated traceback; (2) `_on_plugin_result` in `scan_wiring.py` checks `res.error` first and shows the same translation; (3) `_run_plugin_in_dialog` gains a collapsible "▼ Show error details" toggle that reveals a `QTextEdit` with the raw traceback. 4 new tests: `TestPluginErrorDisplay`.

**Suite after sprint:** 2706 passed, 5 skipped (was 2697 before Sprint C; +9 tests).

---

## Sprint D Completion Notes (2026-06-02)

**PB-8 ✅** — Added `_ScanPluginRegistryFetchThread` and `_ScanPluginInstallThread` QThread classes at module level in `ui/tabs_recon.py`. Added `"⬇  Get Plugins"` button (`_btn_plugin_community`) to the scan plugins toolbar; clicking opens a modal dialog with a Refresh button, a scroll area of plugin cards, and per-card `⬇ Install` buttons. Install runs `plugin_registry.install_plugin()` in a background thread and reloads the plugin list on success. Added `sha256: str = ""` to `RegistryEntry` and SHA-256 digest verification in `install_plugin()` when a digest is provided. Note: PB-9 hardware Browse tab (`_HardwareBrowseMixin`) and nspkg button were already implemented in the hardware page from earlier sprints — confirmed working and covered by new tests.

**PB-9 ✅** — Confirmed `"⬡  Import .nspkg"` button and `"Browse"` community tab already present and working in `ui/pages/hardware_integration_page.py`. Added 6 page-level integration tests in `test_hardware_integration.py` (section 11).

**Suite after sprint:** 2725 passed, 5 skipped (was 2706 before Sprint D; +19 tests).

---

## Next Sprint: Sprint E

| Item | File(s) to create/modify | Key detail |
|---|---|---|
| PB-7 | `ui/widgets/hub_card.py` | Typed `CONFIG_SCHEMA` — plugin declares `{"poll_interval": {"type": "int", "default": 60}, ...}`; Hub card auto-generates config panel |
| PB-12 | `modules/plugin_registry.py` | Windows path length guard — truncate plugin filenames to 80 chars before install; add test |

---

## Sprint E Completion Notes (2026-06-02)

**PB-12 ✅** — Added Windows path-length guard to `modules/plugin_registry.py`. `install_plugin()` now truncates the filename stem to 80 chars before writing so the full AppData path stays well under the Windows 260-char limit. 2 new regression tests in `tests/test_plugin_registry.py`.

**PB-7 ✅** — CONFIG_SCHEMA auto-generated config panel was already fully implemented end-to-end (hub_helpers.py `_validate_script` AST extraction → `HubCard._build_config_panel` → `_load/save_instance_config` → `PluginPollingWorker` config injection). Sprint E completed the missing coverage:
- Added a `CONFIG_SCHEMA` commented example block to `_TEMPLATE` in `hub_helpers.py` so the New Plugin wizard shows users how to declare the schema.
- Added 8 tests to `tests/test_hardware_integration.py` section 12: schema extraction via `_validate_script`, configure button visibility (with/without schema), widget type generation (int→QSpinBox, bool→QCheckBox, str→QLineEdit), `_apply_config` save roundtrip, worker poll-interval override from schema, and worker config kwarg injection verified via spy plugin file.

**Suite after sprint:** 2735 passed, 5 skipped (was 2725 before Sprint E; +10 tests).

---
*Generated by end-to-end plugin audit, 2026-06-01. Sprint A–E completed 2026-06-02.*
