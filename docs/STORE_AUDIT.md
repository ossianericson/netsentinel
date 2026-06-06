# NetSentinel — Pre-Microsoft Store Audit
**Version audited:** v1.9.87  
**Audit date:** 2026-06-05  
**Status:** CONDITIONAL — store-ready foundations, specific polishes required

---

## Executive Summary

The app has strong architectural foundations, a passing 3 054-test suite, zero hardcoded
colours, correct MSIX packaging, and clean UTF-8 encoding. Issues to address before Store
submission, in priority order:

1. **Architecture (ARCH RULE 1):** `modules/diagnostic_card.py` imports PyQt6 directly.
2. **Worker test coverage (RULE-T2):** 19 of 20 workers have no lifecycle test.
3. **Table UX (RULE-3 + RULE-UX3):** Inconsistent row heights and missing right-click menus.
4. **Missing empty-state CTAs (RULE-UX5):** 7 live-data pages show blank tables with no prompt.
5. **File size (RULE-AH1):** 30+ UI files exceed 600 lines — low priority; the app works
   correctly today. **Do not start this work until all other sprints are complete and you
   have explicitly asked the user whether to proceed.**

Everything is **categorised by sprint** at the bottom. Start with Sprint S-A.

---

## 1. Microsoft Store / MSIX Compliance

| Check | Result | Notes |
|---|---|---|
| Version strings consistent across all 9 files | **PASS** | `test_version_consistency.py` enforces this |
| AppxManifest.xml version format `X.Y.Z.0` | **PASS** | 1.9.87.0 |
| MSIX staging copies single-file exe (not dir glob) | **PASS** | `release.yml` line 108 |
| Ookla nested-winget guard (3-layer defence) | **PASS** | RULE-W1/W2 compliant |
| `PrivilegesRequiredOverridesAllowed = dialog commandline` | **PASS** | `installer.iss` line 65 |
| WinGet manifests — all locale fields present | **PASS** | 3 manifests, all fields populated |
| `Ookla.Speedtest.CLI` as `ExternalDependencies` | **PASS** | Not `PackageDependencies` |
| CI winget job `needs: [release]` | **PASS** | `release.yml` structure correct |
| PyInstaller hiddenimports — all pages/workers/modules listed | **PASS** | `test_spec_hiddenimports.py` enforces this |

**Store compliance verdict: PASS.** No changes needed for submission mechanics.

---

## 2. Blocking Architecture Violations

### 2-A. `modules/diagnostic_card.py` imports PyQt6 (ARCH RULE 1)

**Lines 97–98:**
```python
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget
```

`modules/` must be pure Python with no PyQt imports. `diagnostic_card.py` builds a
shareable card widget, which is inherently UI code. The fix is to move the widget-building
logic to `ui/widgets/diagnostic_card_widget.py` and leave only the data-assembly logic in
`modules/diagnostic_card.py`.

**Sprint: S-A**

---

### 2-B. `modules/notification_router.py` uses lazy QSettings reads (ARCH RULE 1)

Lines 177, 200–201, 211–212 import `QSettings` inside function bodies to read/write snooze
state. This is an acceptable workaround (lazy import, not module-level) but creates a
hidden PyQt6 dependency in a "pure Python" module. The snooze state should be persisted
via a plain JSON file using `get_app_data_dir()` instead.

**Sprint: S-B**

---

## 3. Test Coverage Gaps

### 3-A. Missing module tests (RULE-T1)

| Module | Missing test file |
|---|---|
| [modules/metric_store_queries_metrics.py](../modules/metric_store_queries_metrics.py) | `tests/test_metric_store_queries_metrics.py` |
| [modules/metric_store_queries_uptime.py](../modules/metric_store_queries_uptime.py) | `tests/test_metric_store_queries_uptime.py` |

Minimum: one import test + one behavioural test per module.

**Sprint: S-A**

### 3-B. Missing worker lifecycle tests (RULE-T2)

19 of 20 workers have no corresponding test file. Minimum per worker: import +
instantiate + `start()` + `stop()` + assert `not isRunning()`.

| Worker | Missing test file |
|---|---|
| `workers/availability_worker.py` | `tests/test_availability_worker.py` |
| `workers/cert_worker.py` | `tests/test_cert_worker.py` |
| `workers/dhcp_lease_worker.py` | `tests/test_dhcp_lease_worker.py` |
| `workers/diagnosis_worker.py` | `tests/test_diagnosis_worker.py` |
| `workers/dns_zone_worker.py` | `tests/test_dns_zone_worker.py` |
| `workers/ha_worker.py` | `tests/test_ha_worker.py` |
| `workers/hw_detect_worker.py` | `tests/test_hw_detect_worker.py` |
| `workers/iface_bw_worker.py` | `tests/test_iface_bw_worker.py` |
| `workers/plugin_worker.py` | `tests/test_plugin_worker.py` |
| `workers/process_worker.py` | `tests/test_process_worker.py` |
| `workers/report_scheduler_worker.py` | `tests/test_report_scheduler_worker.py` |
| `workers/rest_api_worker.py` | `tests/test_rest_api_worker.py` |
| `workers/scan_worker.py` | `tests/test_scan_worker.py` |
| `workers/service_worker.py` | `tests/test_service_worker.py` |
| `workers/snmp_trap_worker.py` | `tests/test_snmp_trap_worker.py` |
| `workers/speed_test_worker.py` | `tests/test_speed_test_worker.py` |
| `workers/syslog_worker.py` | `tests/test_syslog_worker.py` |
| `workers/threat_intel_worker.py` | `tests/test_threat_intel_worker.py` |
| `workers/wifi_monitor_worker.py` | `tests/test_wifi_monitor_worker.py` |

**Sprint: S-C, S-D** (split in two batches of ~10)

---

## 4. Table Row Height Violations (RULE-3: must be 24 px)

The following tables use a non-standard row height. All must be corrected to
`verticalHeader().setDefaultSectionSize(24)`.

| File | Line | Current value |
|---|---|---|
| [ui/pages/cert_page.py](../ui/pages/cert_page.py) | 282 | 26 |
| [ui/pages/connections_page.py](../ui/pages/connections_page.py) | 616 | 22 |
| [ui/pages/cve_page.py](../ui/pages/cve_page.py) | 67, 349 | 26 |
| [ui/pages/inventory_page.py](../ui/pages/inventory_page.py) | 654 | 26 |
| [ui/pages/ip_calculator_page.py](../ui/pages/ip_calculator_page.py) | 415 | 20 |
| [ui/pages/log_hub_page.py](../ui/pages/log_hub_page.py) | 82 | 26 |
| [ui/pages/notif_alert_history.py](../ui/pages/notif_alert_history.py) | 232, 344 | 26 |
| [ui/pages/service_page.py](../ui/pages/service_page.py) | 300 | 26 |
| [ui/pages/speed_test_page.py](../ui/pages/speed_test_page.py) | 579 | 26 |
| [ui/pages/threat_intel_page.py](../ui/pages/threat_intel_page.py) | 105 | 26 |
| [ui/tabs_recon.py](../ui/tabs_recon.py) | 116 | 26 |
| [ui/tabs_helpers.py](../ui/tabs_helpers.py) | 45 | 120 (verify: likely a column width, not row height) |
| [ui/widgets/device_detail_panels.py](../ui/widgets/device_detail_panels.py) | 273, 327 | 22, 20 |
| [ui/widgets/hub_card.py](../ui/widgets/hub_card.py) | 399, 453 | 22, 20 |

**Sprint: S-E**

---

## 5. Missing Right-Click Context Menus (RULE-UX3)

The following pages contain `QTableWidget` or `QTreeWidget` instances but have
no `customContextMenuRequested` connection. Minimum menu items: **Copy** and
**How to Fix** (or context-appropriate equivalent).

| Page | Tables | Priority |
|---|---|---|
| [ui/pages/inventory_page.py](../ui/pages/inventory_page.py) | 18 | High — main device list |
| [ui/pages/cve_page.py](../ui/pages/cve_page.py) | — (has QTree) | High — CVE list |
| [ui/pages/service_page.py](../ui/pages/service_page.py) | 9 | High |
| [ui/pages/uptime_page.py](../ui/pages/uptime_page.py) | 10 | High |
| [ui/pages/baseline_page.py](../ui/pages/baseline_page.py) | 15 | Medium |
| [ui/pages/dns_zone_page.py](../ui/pages/dns_zone_page.py) | 11 | Medium |
| [ui/pages/syslog_page.py](../ui/pages/syslog_page.py) | 11 | Medium |
| [ui/pages/snmp_trap_page.py](../ui/pages/snmp_trap_page.py) | 11 | Medium |
| [ui/pages/maintenance_page.py](../ui/pages/maintenance_page.py) | 13 | Medium |
| [ui/pages/automation_page.py](../ui/pages/automation_page.py) | 16 | Medium |
| [ui/pages/trend_page.py](../ui/pages/trend_page.py) | 9 | Medium |
| [ui/pages/trigger_builder_page.py](../ui/pages/trigger_builder_page.py) | 11 | Medium |
| [ui/pages/wifi_heatmap_page.py](../ui/pages/wifi_heatmap_page.py) | 15 | Low |
| [ui/pages/wifi_monitor_page.py](../ui/pages/wifi_monitor_page.py) | 7 | Low |
| [ui/pages/live_bandwidth_page.py](../ui/pages/live_bandwidth_page.py) | 10 | Low |
| [ui/pages/security_overview_page.py](../ui/pages/security_overview_page.py) | 14 | Low |
| [ui/pages/geo_map_page.py](../ui/pages/geo_map_page.py) | 15 | Low |
| [ui/pages/plugin_device_page.py](../ui/pages/plugin_device_page.py) | 23 | Low |

Pages that don't need menus (settings forms, calculators): `settings_cards.py`,
`settings_page.py`, `ip_calculator_page.py`, `log_source_panel.py`.

**Sprint: S-F, S-G** (split high-priority vs medium/low)

---

## 6. Missing Empty-State Pattern (RULE-UX5)

Pages that show live data but lack the `scan_requested` signal + `QStackedWidget`
empty-state guard. Users who open these pages before running a scan see a blank or
confused UI with no call-to-action.

| Page | Issue |
|---|---|
| [ui/pages/connections_page.py](../ui/pages/connections_page.py) | Process table appears empty; no CTA to start monitoring |
| [ui/pages/cve_page.py](../ui/pages/cve_page.py) | CVE table empty without scan; no inline prompt |
| [ui/pages/dhcp_lease_page.py](../ui/pages/dhcp_lease_page.py) | No CTA to trigger DHCP scan |
| [ui/pages/dns_zone_page.py](../ui/pages/dns_zone_page.py) | No CTA |
| [ui/pages/syslog_page.py](../ui/pages/syslog_page.py) | No CTA (monitoring not started) |
| [ui/pages/threat_intel_page.py](../ui/pages/threat_intel_page.py) | Table empty; no CTA |
| [ui/pages/live_bandwidth_page.py](../ui/pages/live_bandwidth_page.py) | Chart blank; no start button |

Pages that are correctly exempt: `automation_page.py` (config form, always editable),
`baseline_page.py` (shows empty-on-purpose as starting point),
`maintenance_page.py` (scheduler), `settings_*.py`.

**Sprint: S-H**

---

## 7. Clean Passes (No Action Required)

| Area | Verdict |
|---|---|
| Hardcoded hex colours in `ui/` | **PASS** — zero violations outside `styles.py` |
| Button `:pressed { color: }` rules (RULE-AX1) | **PASS** — all 121 button stylesheet tests pass |
| Selection state colours (RULE-UX6) | **PASS** — all theme tokens used |
| Secrets in OS keychain (RULE-22-A) | **PASS** — no passwords/tokens in QSettings |
| `get_app_data_dir()` for file writes (RULE-23) | **PASS** — no hardcoded exe-dir paths |
| UTF-8 encoding / no mojibake (RULE-ENC1) | **PASS** — `test_source_encoding.py` green |
| Version consistency (RULE-11) | **PASS** — all 9 files at v1.9.87 |
| PyInstaller hiddenimports (RULE-B1) | **PASS** — `test_spec_hiddenimports.py` green |
| Nav pages registered in `_build_pro_nav()` | **PASS** — `test_nav_completeness.py` green |
| `_PAGE_HELP` entries for all pages | **PASS** — 30+ entries in `ui/help.py` |
| `_FEATURES` entries in discover_data.py | **PASS** — 50+ features across 8 groups |
| MSIX version format `X.Y.Z.0` | **PASS** |
| Ookla 3-layer winget guard | **PASS** |
| subprocess PIPE on startup paths | **PASS** — `flush_network_caches()` is user-triggered, not startup |
| Full test suite | **PASS** — 3054 passed, 10 skipped |

---

## 8. Sprint Plan

Work items are ordered so that earlier sprints unblock or simplify later ones.
After each sprint: run `python -m pytest tests/ -q` and `python tools/debug_launch.py`
before committing.

---

### Sprint S-A — Blocking compliance (1 session) ✅ 2026-06-05

The minimum set needed before Store submission.

- [x] **A1.** Move PyQt6 widget code out of `modules/diagnostic_card.py`
  into `ui/widgets/diagnostic_card_widget.py`; keep only data assembly in the module.
- [x] **A2.** Add `tests/test_metric_store_queries_metrics.py` (import + 2 query tests).
- [x] **A3.** Add `tests/test_metric_store_queries_uptime.py` (import + 2 query tests).
- [x] **A4.** Bump version, run full suite, verify app launch.

---

### Sprint S-B — Architecture clean-up (1 session) ✅ 2026-06-06

- [x] **B1.** Replace lazy `QSettings` snooze-state reads/writes in
  `modules/notification_router.py` with a plain JSON file via `get_app_data_dir()`.
  Remove the `from PyQt6.QtCore import QSettings` imports.
- [x] **B2.** Refactored `modules/hw_detect.already_installed()` to accept
  `registered_paths` as a parameter; removed `PyQt6` and `ui/` imports entirely.
  Updated caller in `ui/pages/hardware_browse_mixin.py` to pass `_load_paths()`.

---

### Sprint S-C — Worker lifecycle tests, batch 1 (1 session)

Add minimal lifecycle tests for 10 workers. Use the conftest `qt_app` fixture.
Pattern:
```python
def test_NAME_worker_lifecycle(qt_app):
    from workers.NAME_worker import NAMEWorker
    w = NAMEWorker()
    w.start()
    w.msleep(50)
    w.stop()
    w.wait(1000)
    assert not w.isRunning()
```

Batch 1: `availability`, `cert`, `dhcp_lease`, `diagnosis`, `dns_zone`, `ha`,
`hw_detect`, `iface_bw`, `plugin`, `process`.

---

### Sprint S-D — Worker lifecycle tests, batch 2 (1 session)

Batch 2: `report_scheduler`, `rest_api`, `scan`, `service`, `snmp_trap`,
`speed_test`, `syslog`, `threat_intel`, `wifi_monitor`.

Note: `scan_worker` and `wifi_monitor_worker` require network/admin access — mark
tests with `@pytest.mark.live` and confirm they skip in CI.

---

### Sprint S-E — Table row height standardisation (1 session)

Set `verticalHeader().setDefaultSectionSize(24)` on all non-compliant tables.
Work through the list in Section 4. Visually verify each page after changes.

- [ ] cert_page.py:282 (26 → 24)
- [ ] connections_page.py:616 (22 → 24)
- [ ] cve_page.py:67,349 (26 → 24)
- [ ] inventory_page.py:654 (26 → 24)
- [ ] ip_calculator_page.py:415 (20 → 24)
- [ ] log_hub_page.py:82 (26 → 24)
- [ ] notif_alert_history.py:232,344 (26 → 24)
- [ ] service_page.py:300 (26 → 24)
- [ ] speed_test_page.py:579 (26 → 24)
- [ ] threat_intel_page.py:105 (26 → 24)
- [ ] tabs_recon.py:116 (26 → 24)
- [ ] device_detail_panels.py:273,327 (22, 20 → 24)
- [ ] hub_card.py:399,453 (22, 20 → 24)
- [ ] tabs_helpers.py:45 — **verify**: value is 120; confirm this is a column width
  setting, not a row height, before changing.

---

### Sprint S-F — Right-click menus, high-priority pages (1 session)

Add `customContextMenuRequested` context menus with at minimum **Copy** and a
context-appropriate second action (e.g. "How to Fix", "Export Row", "Open in Browser").

- [ ] `inventory_page.py` — Copy IP, Copy MAC, Label Device, Open in Browser
- [ ] `service_page.py` — Copy URL, Copy Status, How to Fix
- [ ] `uptime_page.py` — Copy Host, Export Row
- [ ] `cve_page.py` — Copy CVE ID, Open NVD Link, How to Fix
- [ ] `baseline_page.py` — Copy, Export Row
- [ ] `dns_zone_page.py` — Copy Record, Export

---

### Sprint S-G — Right-click menus, remaining pages (1 session)

- [ ] `syslog_page.py` — Copy Message, Copy Host
- [ ] `snmp_trap_page.py` — Copy OID, Copy Source
- [ ] `maintenance_page.py` — Copy Window, Delete
- [ ] `automation_page.py` — Copy Hook, Run Now
- [ ] `trend_page.py` — Copy Metric, Export Row
- [ ] `trigger_builder_page.py` — Copy Expression
- [ ] `security_overview_page.py` — Copy Finding, How to Fix

---

### Sprint S-H — Empty-state CTAs for live-data pages (1 session)

Add the `scan_requested = pyqtSignal()` + `QStackedWidget` pattern to each page
listed in Section 6. Wire signal in `app.py`.

- [ ] `connections_page.py` — CTA: "Start Monitoring"
- [ ] `cve_page.py` — CTA: "Run Scan"
- [ ] `dhcp_lease_page.py` — CTA: "Scan DHCP"
- [ ] `dns_zone_page.py` — CTA: "Run Scan"
- [ ] `syslog_page.py` — CTA: "Start Monitoring"
- [ ] `threat_intel_page.py` — CTA: "Run Scan"
- [ ] `live_bandwidth_page.py` — CTA: "Start Monitoring"

---

## 9. Future Hardening (post-Store, backlog)

These are not blocking but represent good housekeeping for a v2 release:

- **Abyss high-contrast theme** — WCAG AA compliance for accessibility; fourth theme entry.
- **Keyboard shortcut reference card** — in Help panel; complete in-app discoverability.
- **Per-page `?` documentation links** — link each page header to the wiki section.
- **Classroom export** — `modules/classroom_export.py` + `ui/pages/classroom_page.py`.
- **ISP telemetry (opt-in)** — `modules/isp_telemetry.py`; daily anonymous submission.
- **Curriculum badge alignment** — `data/curriculum_map.json`; CompTIA N+/CCNA badges.
- **Community plugin index (P3-4)** — GitHub-hosted JSON; in-app Browse tab.
- **Typed CONFIG_SCHEMA for plugins (P2-2)** — auto-generated config panel.
- **`modules/notification_router.py` full cleanup** — remove all remaining `QSettings`
  lazy imports after Sprint S-B.

---

## 10. File Size Violations — DEFERRED (do not start until all other sprints complete)

> **GATE:** Only tackle this section after Sprints S-A through S-H are all checked off
> **and** you have asked the user: *"All other audit sprints are done. Do you want to
> start the file-size refactoring sprints (S-I and S-J)?"* Do not begin this work
> autonomously.

The app works correctly with these files at their current sizes. These splits are
housekeeping to maintain the RULE-AH1 600-line budget, not bug fixes. They have already
been worked on across ~10 prior sprints; the remaining oversize files are the genuinely
hard-to-split ones.

### Critical (> 1 000 lines)

| File | Lines | Suggested split |
|---|---|---|
| [ui/dashboard.py](../ui/dashboard.py) | **2 118** | Extract remaining result-handler methods to `scan_wiring.py` |
| [ui/widgets/overview_tile.py](../ui/widgets/overview_tile.py) | **1 869** | Move more monitoring tiles to `overview_tile_monitor.py` (already exists) |
| [ui/widgets/hub_card.py](../ui/widgets/hub_card.py) | **1 652** | Continue moving non-widget helpers to `hub_helpers.py` (already exists) |
| [ui/pages/settings_cards.py](../ui/pages/settings_cards.py) | **1 540** | Complete the `settings_appearance.py` split (stub exists but unused) |
| [ui/pages/speed_test_page.py](../ui/pages/speed_test_page.py) | **1 536** | Extract modem signal panel to `ui/widgets/modem_signal_panel.py` |
| [ui/tabs_recon.py](../ui/tabs_recon.py) | **1 459** | Move M6+ recon tab builders to `tabs_recon_extra.py` |
| [ui/pages/home_page.py](../ui/pages/home_page.py) | **1 432** | Extract session widgets to `home_session_widgets.py` (file exists — verify all moved) |
| [ui/pages/inventory_page.py](../ui/pages/inventory_page.py) | **1 362** | Extract device drawer + compare dialog to `device_detail_pane.py` (exists — verify) |
| [ui/scan_enrichment.py](../ui/scan_enrichment.py) | **1 244** | Split mesh/hardware enrichment handlers |
| [ui/nav/builder.py](../ui/nav/builder.py) | **1 222** | Split pin/palette methods to `nav/palette.py` |
| [ui/pages/geo_map_page.py](../ui/pages/geo_map_page.py) | **1 211** | Extract map rendering to `ui/widgets/geo_map_widget.py` |
| [ui/styles.py](../ui/styles.py) | **1 200** | Move theme application helpers to `ui/theme.py` (file exists — move more) |
| [ui/pages/home_automation_page.py](../ui/pages/home_automation_page.py) | **1 152** | Extract device-type panels |
| [ui/pages/discover_data.py](../ui/pages/discover_data.py) | **1 142** | Pure data file — acceptable; no logic to split |

### High (700–999 lines)

| File | Lines |
|---|---|
| [workers/scan_worker.py](../workers/scan_worker.py) | 1 129 |
| [ui/pages/home_data_mixin.py](../ui/pages/home_data_mixin.py) | 1 057 |
| [ui/pages/diagnosis_page.py](../ui/pages/diagnosis_page.py) | 1 054 |
| [ui/pages/log_hub_page.py](../ui/pages/log_hub_page.py) | 954 |
| [ui/tabs.py](../ui/tabs.py) | 948 |
| [ui/pages/log_source_panel.py](../ui/pages/log_source_panel.py) | 942 |
| [ui/pages/lab_mode_page.py](../ui/pages/lab_mode_page.py) | 927 |
| [ui/tabs_analysis.py](../ui/tabs_analysis.py) | 924 |
| [ui/pages/connections_page.py](../ui/pages/connections_page.py) | 913 |
| [ui/widgets/home_session_widgets.py](../ui/widgets/home_session_widgets.py) | 899 |
| [ui/pages/overview_page.py](../ui/pages/overview_page.py) | 846 |
| [ui/tabs_logger.py](../ui/tabs_logger.py) | 835 |
| [ui/pages/plugin_device_page.py](../ui/pages/plugin_device_page.py) | 833 |
| [ui/widgets/overview_tile_monitor.py](../ui/widgets/overview_tile_monitor.py) | 807 |
| [ui/pages/cve_page.py](../ui/pages/cve_page.py) | 804 |
| [ui/pages/hardware_integration_page.py](../ui/pages/hardware_integration_page.py) | 771 |
| [ui/pages/notif_alert_history.py](../ui/pages/notif_alert_history.py) | 764 |
| [ui/widgets/alert_drawer.py](../ui/widgets/alert_drawer.py) | 763 |
| [ui/nav/rail.py](../ui/nav/rail.py) | 757 |
| [ui/pages/wifi_heatmap_page.py](../ui/pages/wifi_heatmap_page.py) | 752 |
| [ui/tabs_scan.py](../ui/tabs_scan.py) | 740 |
| [ui/monitor_state.py](../ui/monitor_state.py) | 703 |
| [ui/scan_wiring.py](../ui/scan_wiring.py) | 697 |

### Medium (600–699 lines)

| File | Lines |
|---|---|
| [ui/pages/baseline_page.py](../ui/pages/baseline_page.py) | 691 |
| [ui/pages/threat_intel_page.py](../ui/pages/threat_intel_page.py) | 676 |
| [ui/help_tab.py](../ui/help_tab.py) | 671 |
| [ui/pages/trigger_builder_page.py](../ui/pages/trigger_builder_page.py) | 665 |
| [ui/header.py](../ui/header.py) | 654 |
| [ui/widgets/hub_helpers.py](../ui/widgets/hub_helpers.py) | 653 |
| [ui/pages/protocol_viz_page.py](../ui/pages/protocol_viz_page.py) | 623 |
| [ui/pages/notif_channel_panels.py](../ui/pages/notif_channel_panels.py) | 614 |
| [ui/pages/history_page.py](../ui/pages/history_page.py) | 603 |

**All `modules/` and `workers/` files are within budget.**

### Sprint S-I — File splits, batch 1 (1–2 sessions) — GATED

- [ ] Complete `settings_appearance.py` split from `settings_cards.py`
- [ ] Extract modem signal panel from `speed_test_page.py` to `modem_signal_panel.py`
- [ ] Move session widgets into `home_session_widgets.py` (verify all moved)
- [ ] Extract map rendering from `geo_map_page.py` to `geo_map_widget.py`
- [ ] Verify all new files added to `hiddenimports` in `NetSentinel.spec`

### Sprint S-J — File splits, batch 2 (1–2 sessions) — GATED

- [ ] Split `tabs_recon.py` — move M6+ builders to `tabs_recon_extra.py`
- [ ] Continue `hub_card.py` → `hub_helpers.py` migration
- [ ] Move theme-application helpers from `styles.py` to `theme.py`
- [ ] Extract remaining scan-result handlers from `dashboard.py` to `scan_wiring.py`
- [ ] Split `nav/builder.py` pin/palette methods to `nav/palette.py`
- [ ] Verify all new files added to `hiddenimports` in `NetSentinel.spec`

---

*Audit produced from static analysis, line counts, and regex scans of the v1.9.87 source tree.*  
*Re-run after each sprint: `python -m pytest tests/ -q && python tools/debug_launch.py`*
