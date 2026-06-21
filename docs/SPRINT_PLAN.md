# NetSentinel — 10-Sprint Improvement Plan

**Version baseline:** v2.1.14  
**Status:** MS Store stable. All sprints are improvements to existing features — no new pages, no new functionality.  
**How to use:** Copy the relevant sprint section into a new chat. Each section is self-contained — the new chat can start immediately without re-deriving context.

---

## Preamble (paste into every new chat)

> NetSentinel v2.1.14 — PyQt6 desktop network scanner/monitor, Microsoft Store stable.
> Improvement-only policy: no new features, no new pages. Polish, stability, test coverage, and UX refinement of existing features only.
>
> **Commit gate (mandatory before every commit):**
> 1. `ruff check . --select=F401,F811,F841` — must exit 0
> 2. `python -m pytest tests/ -q` — all tests must pass
> 3. `python tools/debug_launch.py` — read `netsentinel_debug.log`, confirm `Dashboard() instantiated OK` and `window.show() called OK`
> 4. Tell the user "Tests pass, app launched cleanly — please verify the window looks correct."

---

## Sprint 1 — Crash Risks & Code Violations

**Risk:** Critical | **Effort:** S | **Benefit:** Prevents heap-corruption crashes; clears CodeQL violations

### Background

Five unparented `QTimer.singleShot` calls are live crash risks. When a widget is deleted (fixture teardown, rapid navigation) before the timer fires, the callback hits a zombie C++ object, raises `RuntimeError` through Qt's callback machinery, and corrupts the heap. The crash surfaces as `STATUS_STACK_BUFFER_OVERRUN` hundreds of tests later — not at the callsite (RULE-WIN5).

### Items

**1. Fix 5 unparented `QTimer.singleShot` → parented `QTimer(self)`**

```python
# WRONG — unparented, fires on zombie if widget deleted within N ms
QTimer.singleShot(2000, lambda: btn.setText(orig))

# CORRECT — parented QTimer is auto-destroyed with the widget
_t = QTimer(self)
_t.setSingleShot(True)
_t.timeout.connect(lambda: btn.setText(orig))
_t.start(2000)
```

Files to fix:
- `ui/app_settings.py:182`
- `ui/pages/hardware_browse_mixin.py:497`
- `ui/pages/log_hub_page.py:553-554` (two timers)
- `ui/pages/notif_extra_channels.py:349`
- `ui/widgets/credential_dialog.py:207`

**2. Fix `__import__()` abuse → proper top-level imports**

`ui/scan_enrichment.py` lines 459, 475, 706 use `__import__("re").compile(...)` and `__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(...)`. Replace with standard top-level `import re` and `from PyQt6.QtGui import QColor`.

**3. Fix RULE-LINT4 violation in `ui/pages/settings_cards.py:41`**

Replace `import ui.styles as _styles` (module import) with `from ui import styles as _styles` inside the method body. The module-import form conflicts with the top-level `from ui.styles import (...)` and triggers CodeQL `py/import-and-import-from`.

**4. Fix 3 bare `except:` blocks in `tests/test_zte.py:46,65,75`**

Add an inline comment to each explaining why the exception is non-fatal:

```python
# WRONG
except:
    return None

# CORRECT
except Exception:
    return None  # non-fatal — response JSON may be malformed on test fixture
```

### Done when
- [ ] All 5 QTimers converted to parented form; grep confirms no remaining unparented `QTimer.singleShot.*self\.` in `ui/`
- [ ] `__import__()` calls removed from `scan_enrichment.py`
- [ ] RULE-LINT4 violation resolved in `settings_cards.py`
- [ ] All 3 bare excepts in `test_zte.py` have explanatory comments
- [ ] Commit gate passes (ruff → pytest → debug_launch)

---

## Sprint 2 — File Budget Relief

**Risk:** High | **Effort:** M | **Benefit:** Prevents CI breakage on any future touch to these files

### Background

`settings_cards.py` is 1,557 lines against a 1,560-line budget — 3 lines of safety margin. `alert_engine.py` is 775 lines against an 800-line budget. `metric_store.py` is 711 against 730. The next time any of these files is edited for any reason, CI fails. These splits must happen before any other work touches those files.

### Items

**1. Split `ui/pages/settings_cards.py` — extract appearance methods**

`settings_cards.py` contains `_SettingsCardsMixin`. Extract appearance-related card builders (theme selector, display density, colour scheme) into a new `ui/pages/settings_appearance_cards.py` mixin. `_SettingsCardsMixin` inherits from it. Target: bring `settings_cards.py` below 1,200 lines.

Note: `ui/pages/settings_appearance.py` already exists as a stub (marked INCOMPLETE in CLAUDE.md). Use that file as the destination.

**2. Split `modules/alert_engine.py` — extract cert/service check methods**

Move `evaluate_cert_checks()` and `evaluate_service_checks()` (and any helpers they call) into a new `modules/alert_engine_checks.py`. `AlertEngine` imports and calls them. Target: bring `alert_engine.py` below 700 lines.

Add `"modules.alert_engine_checks"` to `hiddenimports` in `NetSentinel.spec` (RULE-B1).  
Add `tests/test_alert_engine_checks.py` with at least one import test and one behavioural test (RULE-T1).

**3. Plan `modules/metric_store.py` split**

`metric_store.py` (711 lines, budget 730) already has partial splits in `metric_store_schema.py`, `metric_store_queries.py`, etc. Identify the next logical chunk to extract (candidate: write-path methods for `device_state` and `known_device` tables). Document the plan in a comment at the top of the file — do not execute the split this sprint unless the file grows further.

**4. Plan `modules/topology_cytoscape.py` split**

682 lines, budget 720. Extract `_build_style()` and `_build_stylesheet()` into `modules/topology_cytoscape_style.py`. Schedule for Sprint 3 if the file does not change this sprint; execute immediately if any edit is needed.

### Done when
- [ ] `settings_cards.py` is below 1,400 lines; `test_module_loc.py` passes
- [ ] `alert_engine.py` is below 750 lines; `test_module_loc.py` passes
- [ ] `alert_engine_checks.py` has tests; full suite passes
- [ ] `metric_store.py` split plan documented in file header comment
- [ ] `topology_cytoscape.py` split plan documented or executed
- [ ] Commit gate passes

---

## Sprint 3 — Worker Lifecycle Tests

**Risk:** High | **Effort:** M | **Benefit:** 22 critical workers get a safety-net; silent start/stop failures become detectable

### Background

22 of 27 workers have no lifecycle test (RULE-T2). A worker that silently fails to start or stop is a live bug with no detection mechanism. The pattern to follow is in `tests/test_bandwidth_worker.py`.

### Items

**1. Add lifecycle tests for all 22 missing workers**

For each worker: instantiate → `start()` → short wait (`QTest.qWait(100)` or `time.sleep(0.1)`) → call `stop()` / set `_running = False` → assert `not worker.isRunning()`.

Priority order (most critical first):
1. `workers/scan_worker.py` — core discovery
2. `workers/availability_worker.py` — always-on monitoring
3. `workers/health_worker.py` — ambient health score
4. `workers/service_diagnostics_worker.py`
5. `workers/app_traffic_worker.py`
6. `workers/cert_worker.py`
7. `workers/dhcp_lease_worker.py`
8. `workers/diagnosis_worker.py`
9. `workers/dns_zone_worker.py`
10. `workers/ha_worker.py`
11. `workers/hw_detect_worker.py`
12. `workers/iface_bw_worker.py`
13. `workers/lldp_worker.py`
14. `workers/passive_observer_worker.py`
15. `workers/plugin_worker.py`
16. `workers/process_worker.py`
17. `workers/report_scheduler_worker.py`
18. `workers/rest_api_worker.py`
19. `workers/service_worker.py`
20. `workers/snmp_trap_worker.py`
21. `workers/syslog_worker.py`
22. `workers/threat_intel_worker.py`
23. `workers/speed_test_worker.py`
24. `workers/wifi_monitor_worker.py`

Each test file goes in `tests/test_<worker_name>.py`. Use `conftest.py`'s `qt_app` fixture (autouse). Each fixture must call `worker.deleteLater()` + 3× `app.processEvents()` in teardown (RULE-WIN4).

**2. Add REST API security tests**

Add `tests/test_rest_api_security.py` covering:
- Invalid API key → 401 response
- Missing API key → 401 response
- Malformed query param (e.g. `?hours=abc` on `/uptime`) → graceful error, not 500
- CORS header only present for `127.0.0.1` / `localhost` origin

### Done when
- [ ] All 22 (or more) workers have `test_<name>.py` with lifecycle test
- [ ] REST API security tests added and green
- [ ] `python -m pytest tests/ -q` passes with new tests
- [ ] Commit gate passes

---

## Sprint 4 — UX: Right-Click Context Menus

**Risk:** Medium | **Effort:** M | **Benefit:** Every table in the app becomes actionable; eliminates RULE-UX3 violations across 19 pages

### Background

19 pages have data tables with no right-click context menu (RULE-UX3). Users cannot copy rows, copy cells, or access "How to Fix" without selecting text manually. 13 other pages already have context menus — this sprint brings the rest up to the same standard.

### Items

**Add `customContextMenuRequested` to all 19 missing pages**

Minimum menu items per table:
- **Copy row** (tab-separated values to clipboard)
- **Copy cell** (current cell text to clipboard)
- One contextual action relevant to the page (see list below)

Reuse `ui/widgets/context_menu.py` helpers where applicable.

| Page | File | Contextual action |
|---|---|---|
| Automation Hooks | `automation_page.py` | "Enable / Disable rule" |
| Baseline | `baseline_page.py` | "Reset baseline" |
| DNS Zone | `dns_zone_page.py` | "Lookup in Threat Intel" |
| Geo Map | `geo_map_page.py` | "Show device in Inventory" |
| IP Calculator | `ip_calculator_page.py` | "Copy subnet" |
| Live Bandwidth | `live_bandwidth_page.py` | "Show device in Inventory" |
| Maintenance | `maintenance_page.py` | "Edit window" |
| Plugin Devices | `plugin_device_page.py` | "Reload plugin" |
| Security Overview | `security_overview_page.py` | "View details" |
| Service Diagnostics | `service_diagnostics_page.py` | "Re-run probe" |
| Service Heartbeat | `service_page.py` | "Diagnose →" |
| Settings | `settings_cards.py` | — (copy only; settings rows aren't data rows) |
| SNMP Traps | `snmp_trap_page.py` | "Copy OID" |
| Syslog | `syslog_page.py` | "Filter by host" |
| Threat Intel | `threat_intel_page.py` | "Open in AbuseIPDB" |
| Trigger Builder | `trigger_builder_page.py` | "Duplicate trigger" |
| Uptime & SLA | `uptime_page.py` | "Show in Timeline" |
| WiFi Heatmap | `wifi_heatmap_page.py` | "Copy BSSID" |
| WiFi Monitor | `wifi_monitor_page.py` | "Filter by BSSID" |

### Done when
- [ ] All 19 pages have right-click menus with at minimum Copy + one contextual action
- [ ] Right-click on any table row does not throw an exception (test manually on each page)
- [ ] Commit gate passes

---

## Sprint 5 — UX: Empty States

**Risk:** Medium | **Effort:** M | **Benefit:** Eliminates blank-table confusion for new users on 15 pages

### Background

15 pages show an empty table on first use with no guidance. This is RULE-UX5. The `EmptyStateCard` widget already exists at `ui/widgets/empty_state_card.py` — it just needs to be wired up.

### Items

**Add `QStackedWidget` + `EmptyStateCard` to 15 pages**

Pattern:
```python
# In __init__:
self._stack = QStackedWidget()
self._empty = EmptyStateCard(
    icon="⬡",
    title="No services monitored yet",
    why="Add a service to track its uptime and get alerted when it goes down.",
    cta_label="Add Service",
)
self._empty.cta_clicked.connect(self._on_add_service)
self._stack.addWidget(self._empty)       # index 0
self._stack.addWidget(self._content)     # index 1
self._stack.setCurrentIndex(0)

# When data arrives:
self._stack.setCurrentIndex(1)

# Add signal for app.py wiring:
scan_requested = pyqtSignal()
```

Wire each `scan_requested` signal in `app.py` to `window._start_full_scan` or the relevant worker.

| Page | File | CTA label | Signal target |
|---|---|---|---|
| Automation Hooks | `automation_page.py` | "Add Rule" | internal add dialog |
| DHCP Leases | `dhcp_lease_page.py` | "Scan Network" | `scan_requested` |
| Home Automation | `home_automation_page.py` | "Scan Network" | `scan_requested` |
| Maintenance Windows | `maintenance_page.py` | "Add Window" | internal add dialog |
| Plugin Devices | `plugin_device_page.py` | "Open Hardware Hub" | nav to Hardware |
| Security Overview | `security_overview_page.py` | "Run Security Scan" | `scan_requested` |
| Service Heartbeat | `service_page.py` | "Add Service" | internal add dialog |
| Syslog Viewer | `syslog_page.py` | "Start Monitoring" | syslog worker |
| Threat Intel | `threat_intel_page.py` | "Run Scan" | `scan_requested` |
| Trigger Builder | `trigger_builder_page.py` | "Add Trigger" | internal add dialog |
| WiFi Heatmap | `wifi_heatmap_page.py` | "Import Floor Plan" | internal import |
| Alert History | `notif_alert_history.py` | "Configure Alerts" | nav to Notifications |
| Dep Card | `notif_dep_card.py` | "Add Dependency" | internal add dialog |
| IP Calculator | `ip_calculator_page.py` | "Enter a subnet above" | focus input field |
| App Traffic | `app_traffic_page.py` | "Start Monitoring" | traffic worker |

### Done when
- [ ] All 15 pages show `EmptyStateCard` on first load (verify with clean QSettings)
- [ ] CTA buttons are functional (open dialog, emit signal, or focus input as appropriate)
- [ ] Populated pages switch to content view when data arrives
- [ ] Commit gate passes

---

## Sprint 6 — Scan Radar Animation

**Risk:** Low | **Effort:** S | **Benefit:** Fills the dead waiting state during scanning with a visually meaningful animation; the radar metaphor directly represents what network scanning does

### Background

Between clicking "Scan" and results arriving, the Home page shows a static skeleton placeholder — dead space the user stares at for 5–15 seconds. This sprint adds a phosphor-green radar sweep that occupies that space, showing discovered devices as dots appearing in real time as the worker finds them. It is purely additive: nothing is removed or replaced. When results arrive the radar fades out and the normal results view takes over.

### Items

**1. Add `RADAR_*` color constants to `ui/styles.py`**

Add to all four theme dicts (`_ARCTIC_CLEAN`, `_DARK_PRO`, `_OBSIDIAN_NEON`, `_ABYSS`):

```python
"RADAR_BG":    "#050F05",   # near-black green-tinted background
"RADAR_GRID":  "#0D2E0D",   # dim concentric rings and spokes
"RADAR_GREEN": "#00FF41",   # bright sweep arm and fresh device dots
"RADAR_TRAIL": "#00CC33",   # phosphor trail body
```

Add all four names to the explicit export list so static analysis can see them (RULE-AH6). Run `python -m pytest tests/test_style_token_imports.py -v` to confirm.

**2. Create `ui/widgets/scan_radar_widget.py` — `ScanRadarWidget`**

A self-contained `QWidget` that draws a full radar display in `paintEvent`. Minimum size 300×300 px; scales with parent.

Elements drawn each frame:
- Filled background circle (`RADAR_BG`)
- 4 concentric range rings (`RADAR_GRID`, 1 px)
- 8 azimuth spokes at 45° intervals (`RADAR_GRID`, 1 px)
- Small centre crosshair
- Phosphor trail — `QConicalGradient` from transparent → `RADAR_GREEN`, 60° arc, rotated to match `_sweep_angle`; single draw call, no per-degree loop
- Sweep arm — bright line from centre to edge at `_sweep_angle` (`RADAR_GREEN`, 2 px)
- Device dots — 6 px filled circles at deterministic radar positions; brief expand-and-fade burst ring when first appearing, settles to solid dot
- Status text below circle: `"Scanning…  {n} devices found"` in `RADAR_GREEN`

Animation: `_tick_timer = QTimer(self)` at 33 ms → advance `_sweep_angle` by 2.0°/tick → `update()`. One full rotation ≈ 6 seconds at 30 fps. Timer is parented (RULE-WIN5); no `QTimer.singleShot` anywhere in this widget.

Public API:
```python
def start(self) -> None
def stop(self) -> None
def add_device(self, ip: str, name: str, device_type: str) -> None
```

Device positioning algorithm: hash the IP's last octet → azimuth angle (0–360°); subnet prefix determines ring (1–4 from centre outward). Deterministic — same network always produces the same dot layout.

**3. Add `device_found` signal to `workers/scan_worker.py`**

Emit `device_found(dict)` for each device as it is confirmed during the scan loop, before `result_ready` fires. Enables dots to appear incrementally rather than all at once at the end.

```python
device_found = pyqtSignal(dict)   # {"ip": str, "name": str, "type": str}
```

**4. Wire radar into the Home page scan card**

In `ui/pages/home_page.py`, wrap the scan-trigger hero area in a `QStackedWidget`:
- Page 0 — existing scan button / getting-started content (default)
- Page 1 — `ScanRadarWidget` (300×300, centred in card)

On scan start → flip to page 1, call `radar.start()`, connect `scan_worker.device_found → radar.add_device`.  
On `result_ready` → call `radar.stop()`, 400 ms `QPropertyAnimation` opacity fade to 0, then flip back to page 0.

**5. Register in `NetSentinel.spec` and add tests**

Add `"ui.widgets.scan_radar_widget"` to `hiddenimports` (RULE-B1).

Create `tests/test_scan_radar_widget.py`:
- Import test
- `start()` → assert `_tick_timer.isActive()` is `True`
- `stop()` → assert `_tick_timer.isActive()` is `False`
- `add_device("192.168.1.5", "Router", "router")` → assert `len(widget._devices) == 1`
- Widget fixture uses `deleteLater()` + 3× `processEvents()` in teardown (RULE-WIN4)

### Done when
- [ ] `RADAR_*` constants present in all 4 theme dicts; `test_style_token_imports.py` passes
- [ ] Radar visible and animating on Home page when a scan starts
- [ ] Device dots appear incrementally as `device_found` signal fires during scan
- [ ] Radar fades out and Home page returns to normal when `result_ready` fires
- [ ] `tests/test_scan_radar_widget.py` passes; no new ruff/mypy violations
- [ ] Commit gate passes

---

## Sprint 7 — Loading States & Performance Perception

**Risk:** Low | **Effort:** S | **Benefit:** Eliminates "is the app frozen?" perception; users stop double-clicking buttons

### Background

Pages that trigger slow workers give no feedback between button click and result. The UX rule is: any operation >500ms must show visible loading state (RULE-UX2). No new architecture needed — it's button state + spinner wiring.

### Items

**1. Add button disable + loading label to all slow worker triggers**

Pattern:
```python
def _on_run_clicked(self):
    self._run_btn.setEnabled(False)
    self._run_btn.setText("Running…")
    self._worker.start()

def _on_result(self, data):
    self._run_btn.setEnabled(True)
    self._run_btn.setText("Run")
    # populate table...

def _on_error(self, msg):
    self._run_btn.setEnabled(True)
    self._run_btn.setText("Run")
```

Priority pages (operations clearly >2s):
- `diagnosis_page.py` — "Run Diagnosis" button
- `cert_page.py` — "Check Certificates" button
- `cve_page.py` — "Lookup CVEs" button
- `service_diagnostics_page.py` — "Run Diagnostics" button
- `geo_map_page.py` — "Load Map" button
- `threat_intel_page.py` — "Run Lookup" button
- `reports_page.py` — "Generate Report" button
- `network_doc_page.py` — "Generate Doc" button

**2. Add animated progress indicator to full discovery scan**

The full discovery scan (scan_worker) is the longest operation in the app. The existing progress signal exists — wire it to a `QProgressBar` or pulsing status label in the header/breadcrumb area so users can see scan progress from any page, not just the Overview.

**3. Speed Test page: show "Testing…" between click and first result**

Currently the button goes grey. Add "Testing… (this takes ~20s)" text so users know the expected wait time.

### Done when
- [ ] All 8 priority pages disable their trigger button during worker run
- [ ] Button text changes to "Running…" / "Testing…" during operation
- [ ] Scan progress visible from any page during a full discovery scan
- [ ] Commit gate passes

---

## Sprint 8 — Command Palette Quick Actions

**Risk:** Low | **Effort:** M | **Benefit:** Every existing feature is one Ctrl+K away; power-user delight without new features

### Background

The command palette (Ctrl+K) currently only navigates to pages. Adding action items makes it a genuine launcher — users can start a speed test, run a diagnosis, or export a report without navigating first.

### Items

**1. Add 8–10 action items to `ui/command_palette.py`**

Actions to add (all trigger existing functionality):

| Label | Kind | Handler |
|---|---|---|
| "Start Speed Test" | action | Navigate to Speed Test + trigger run |
| "Run Full Scan" | action | Emit `_start_full_scan` |
| "Run Diagnosis: Slow Internet" | action | Navigate to Diagnosis + pre-select tile |
| "Run Diagnosis: No Connection" | action | Navigate to Diagnosis + pre-select tile |
| "Export PDF Report" | action | Call `save_pdf_report()` |
| "Export Network Doc" | action | Navigate to Network Doc + trigger generate |
| "Copy REST API Key" | action | Read from keyring → clipboard + toast |
| "Open Quick Check (Ctrl+Shift+H)" | action | Open `QuickCheckWindow` |
| "Toggle Network Logger" | action | Start/stop network logger worker |
| "View Alert History" | action | Navigate to Notifications → history tab |

Implementation: add to `_ALL_ITEMS` list in `command_palette.py` with `kind="action"` and an `action_key` string. Handle `action_key` in `_on_activated()` with a dispatch dict.

**2. Add `Alt+1–5` keyboard shortcuts for top 5 pages**

Wire in `dashboard.py` `keyPressEvent`:
- `Alt+1` → Overview
- `Alt+2` → Devices
- `Alt+3` → Speed Test
- `Alt+4` → What's Wrong?
- `Alt+5` → Network Logger

**3. Document shortcuts in the Help tip bar**

Add a "Keyboard Shortcuts" entry to `_PAGE_HELP` (global / no-page entry) and surface it from the `?` button on the home page.

### Done when
- [ ] 8+ action items appear in Ctrl+K palette and execute correctly
- [ ] Alt+1–5 navigate to the correct pages
- [ ] Shortcuts documented in help
- [ ] Commit gate passes

---

## Sprint 9 — Behavioral Integration Tests (Part 1)

**Risk:** Medium | **Effort:** L | **Benefit:** Catches UI regressions before they reach the Store; 10 most critical pages covered

### Background

28 pages have no behavioral integration test (RULE-T7). Unit tests catch module logic; behavioral tests catch the wiring between data → widget → visible state. Start with the 10 highest-risk pages (security-sensitive, complex, or most-used).

### Items

For each page: instantiate with a mock `MetricStore` → inject realistic mock data → call the slot that handles it → assert a specific widget state.

```python
# Example pattern
def test_cert_page_shows_rows_after_result(qt_app, mock_store):
    page = CertPage(store=mock_store)
    certs = [{"host": "example.com", "days_left": 30, "status": "OK"}]
    page.on_cert_result(certs)
    assert page._table.rowCount() == 1
    try:
        page.deleteLater()
    except RuntimeError:
        pass
    QApplication.instance().processEvents()
```

**10 pages for this sprint:**

| Page | File | What to test |
|---|---|---|
| REST API | `rest_api_page.py` | API key displays masked; copy button works; status probe shows result |
| Automation | `automation_page.py` | Rule appears in table after add; enable/disable toggle changes row |
| Notifications | `notifications_page.py` | Channel enable/disable persists; test-send button triggers signal |
| Settings | `settings_page.py` | Theme switch updates `QSettings`; page re-renders on theme change |
| Diagnosis | `diagnosis_page.py` | Symptom tile click starts worker; result text appears after mock result |
| Service Heartbeat | `service_page.py` | Service row appears after add; "Diagnose →" signal emits correct service |
| Active Connections | `connections_page.py` | Process table populates with mock psutil data; firewall block button visible |
| Certificates | `cert_page.py` | Row count matches mock data; expiry colour correct (RED for <30 days) |
| CVE Tracker | `cve_page.py` | CVE rows appear after mock inject; severity badge uses correct colour |
| History | `history_page.py` | Diff table shows added/removed devices; snapshot count label correct |

### Done when
- [ ] 10 behavioral test files created and green
- [ ] Each test asserts at least one widget state (not just "page instantiates")
- [ ] `python -m pytest tests/ -q` passes
- [ ] Commit gate passes

---

## Sprint 10 — Help Content Quality & Feature Guide Polish

**Risk:** Low | **Effort:** S | **Benefit:** Directly improves MS Store ratings by reducing "what does this do?" confusion

### Background

All 75 pages have help entries (architecture audit confirmed complete coverage). The issue is quality: descriptions are technical rather than user-facing. "The topology is rebuilt after every scan" tells a user what happens but not why they care. This sprint rewrites for the non-technical majority and fills the thin Feature Guide groups.

### Items

**1. Rewrite help entries in `ui/help.py` to lead with "why this matters"**

Format: one sentence of "why you care" → one sentence of "how to start".

Before: `"The topology is rebuilt after every scan — devices are positioned based on ARP and gateway relationships"`  
After: `"See how your devices connect — find the rogue bridge or overloaded switch that's causing slow Wi-Fi. Positions update automatically after each scan."`

Rewrite the 15 weakest entries (identify by scanning for entries that start with "The" or contain no action verb).

**2. Expand `ui/pages/discover_data.py` Feature Guide thin groups**

- **"New in this version"** — currently 2 entries. Add 8 entries for the most significant v2.x features: Network Segments, Persistent Device Map, Service Diagnostics, Service Heartbeat Diagnose action, What's Wrong? service tile, App Traffic page, LLDP/CDP scanner, Network Map Cytoscape upgrade.
- **"Hidden features"** — currently 0 entries. Add 6 tips: Ctrl+Shift+H Quick Check window, right-click any device to pin it, right-click flyout items to pin to rail, Ctrl+F sidebar search from anywhere, Alt+1–5 page shortcuts (Sprint 7), Lab Mode live challenge injection from Network Logger.

**3. Link home suggestions to Feature Guide entry names**

In `ui/pages/home_suggestions.py`, replace any raw strings that reference feature names with a reference to the corresponding `page` key in `_FEATURES`. This ensures suggestion text stays in sync with Feature Guide labels when either is renamed.

**4. Add "Recommended setup" callout to home page for first-run users**

Show a dismissible card on the home page (QSettings-gated: only until dismissed) with 3 recommended first steps:
1. Run a full scan
2. Enable Network Logger
3. Add one alert rule

Card is dismissed permanently when the user clicks "Got it" or completes all 3 steps.

### Done when
- [ ] 15+ help entries rewritten with "why this matters" language
- [ ] "New in this version" has ≥8 entries; "Hidden features" has ≥6 entries
- [ ] Home suggestions reference Feature Guide page keys
- [ ] "Recommended setup" card shows on first run; dismisses permanently
- [ ] Commit gate passes

---

## Sprint 11 — Settings Reorganization, Onboarding & Inventory Split

**Risk:** Low | **Effort:** L | **Benefit:** Retention (onboarding), power-user clarity (settings), long-term code health (inventory split)

### Background

Settings page has no clear organization — everything is a flat list of cards. New users can't find what matters. Onboarding (`ui/onboarding.py` is 23 lines) gives no guided path. `inventory_page.py` is 2,842 lines with 4 extractable dialog classes sitting in the main file.

### Items

**1. Add category navigation to Settings page**

Add a horizontal chip bar at the top of the settings page:

`Appearance` | `Monitoring` | `Alerts` | `Integrations` | `Advanced`

Each chip filters the visible cards. Default: show all. Persist last-selected chip in `QSettings("settings/last_category")`.

Card → category mapping:
- **Appearance:** Theme, Display Density, Colour Scheme, Window Layout
- **Monitoring:** Scan Intervals, Network Logger, Availability Monitor, Modem, Mesh
- **Alerts:** Notification Channels, Alert Rules, Maintenance Windows, Escalation Policy
- **Integrations:** MQTT, REST API, Webhook, SMTP, Pushover, Ntfy, Telegram
- **Advanced:** MetricStore path, Keychain, Export/Import settings, Plugin paths

**2. Expand the guided tour to 5 meaningful steps**

Current tour is minimal. Extend `ui/guided_tour.py` to cover:

1. **"What NetSentinel does"** — tooltip on the header bar: "This is your network control centre. Let's take a 60-second tour."
2. **"Run your first scan"** — tooltip on the scan button: "Click here to discover every device on your network."
3. **"Understand results"** — tooltip on the Devices table: "Each row is a device. Red = risk. Right-click any row for actions."
4. **"Set up monitoring"** — tooltip on the Network Logger nav item: "Enable this to record RTT, DNS, and outages continuously."
5. **"Configure an alert"** — tooltip on Notifications nav item: "Get a toast or email when something changes."

Tour starts automatically on first run (`tour/v2_done` QSettings key, not `v1_done`). Can be restarted from Settings → Advanced → "Restart guided tour".

**3. Extract inventory dialogs to `ui/widgets/inventory_dialogs.py`**

Move these 4 classes out of `ui/pages/inventory_page.py`:
- `_DeviceLabelDialog`
- `_TypeOverrideDialog`
- `_SegmentEditorDialog`
- `_ScanCompareDialog`

New file: `ui/widgets/inventory_dialogs.py`. Update imports in `inventory_page.py`. This removes ~800 lines from `inventory_page.py` (2,842 → ~2,050).

Add `"ui.widgets.inventory_dialogs"` to `hiddenimports` in `NetSentinel.spec` (RULE-B1).

**4. Behavioral integration tests — Part 2**

Remaining 18 pages get their first behavioral test (continued from Sprint 8):

`baseline_page`, `cert_page` (if not done in S8), `dhcp_lease_page`, `dns_zone_page`, `geo_map_page`, `home_automation_page`, `ip_calculator_page`, `lab_mode_page`, `live_bandwidth_page`, `maintenance_page`, `monitor_overview_page`, `mqtt_page`, `network_doc_page`, `protocol_viz_page`, `snmp_trap_page`, `syslog_page`, `timeline_page`, `trend_page`

Minimum: instantiate page with mock store → assert initial stack index is 0 (empty state) OR assert table is empty → inject mock data → assert table/widget reflects data.

### Done when
- [ ] Settings category chips filter cards correctly; last chip persists
- [ ] Guided tour has 5 steps; starts on first run; restartable from Settings
- [ ] `inventory_dialogs.py` created; `inventory_page.py` is below 2,100 lines; all imports updated
- [ ] 18+ additional behavioral tests added and green
- [ ] Commit gate passes

---

## Sprint Summary

| # | Theme | Risk | Effort | Primary Win |
|---|---|---|---|---|
| S1 | Crash risks + CodeQL violations | Critical | S | Stability |
| S2 | File budget relief | High | M | CI integrity |
| S3 | Worker lifecycle tests (22) | High | M | Test coverage |
| S4 | Right-click context menus (19 pages) | Medium | M | UX polish |
| S5 | Empty states (15 pages) | Medium | M | New-user clarity |
| S6 | Scan radar animation | Low | S | Visual polish / scan experience |
| S7 | Loading states | Low | S | Perceived performance |
| S8 | Command palette quick actions | Low | M | Power-user access |
| S9 | Behavioral integration tests pt.1 | Medium | L | Regression safety |
| S10 | Help content + Feature Guide | Low | S | Store ratings |
| S11 | Settings + onboarding + inventory split | Low | L | Retention + code health |

**Rule:** S1–S3 are non-negotiable prerequisites. The crash risks and file budget pressure are live dangers regardless of how stable the app feels today. S4 onwards can be reordered based on user feedback.
