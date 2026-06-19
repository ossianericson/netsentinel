# Changelog

All notable changes to NetSentinel are documented here. The current version summary lives in [README.md](README.md#changelog); the full history is below.

---

### v2.1.12

**Added**
- `ui/perf_audit.py` — `warn_if_nav_slow()` nav timing warnings and `profile_page_init()` cProfile wrapper for page-init instrumentation
- `ui/widgets/feedback_dialog.py` — local in-app feedback dialog; writes timestamped entries to `feedback.log` with no network calls; accessible via Ctrl+K "Give Feedback"
- `STATUS_ICON_OK/WARN/CRIT/UNKNOWN` shape constants in `ui/styles.py`; applied in service heartbeat, uptime, and monitor verdict displays so status is not conveyed by colour alone
- Focus rings (`QPushButton:focus` CSS) on activity-rail buttons and flyout items for keyboard navigation
- `tests/test_status_icons.py`, `tests/test_keyboard_nav.py`, `tests/test_empty_state_audit.py`, `tests/test_loading_state_audit.py`, `tests/test_theme_consistency.py`, `tests/test_feedback_dialog.py`, `tests/test_perf_audit.py` — UX audit test suite

**Fixed**
- Stripped UTF-8 BOM from `ui/nav/rail.py` that caused silent `SyntaxError` in `ast.parse`-based test checks
- `test_no_duplicate_methods.py` now correctly exempts `@pyqtProperty` getter/setter pairs from the duplicate-method check

---

### v2.1.11

**Added**
- `modules/cdn_ranges.py` — static CDN/streaming-provider IP range classifier (Netflix/YouTube/Twitch/Disney+) for App Traffic device drill-downs
- `modules/traffic_insights.py` — household usage narrative, ISP plan utilization, and QoS overlap recommendation builders
- `modules/service_bandwidth_overlay.py` — bandwidth-sharing context note for Service Diagnostics
- `ui/widgets/usage_insights_card.py` — home page "Usage insights" card (weekly category breakdown, plan utilization, dismissible QoS suggestion)
- `app_traffic_sample` table (schema v17) persists App Traffic history; new "Last 24 Hours by Category" chart on the App Traffic page with click-to-drill-down by device and CDN
- "Internet Plan" settings card — optional monthly data cap feeding plan utilization on the home page

---

### v2.1.10

**Added**
- Persistent device map: after each scan, pinned and static-candidate offline devices (infrastructure roles, IP-stable seen 3+ times) are appended to the Inventory snapshot with freshness state `pinned`, `cached` (<24 h), or `stale` (<7 d); implemented in `ScanResultMixin._merge_scan_with_persistent()` (`ui/scan_wiring.py`)
- "Hide offline" toggle in the Current Devices card header hides `cached`/`stale` rows without discarding the persistent map; resets on navigation

**Fixed**
- `ui/scan_wiring.py`: `_store_ref` used before assignment in `_on_m1_result` inventory block; replaced with `_inv_store` to fix silent `UnboundLocalError` that prevented segment detection from running

---

### v2.1.9

**Fixed**
- `modules/topology_cytoscape.py`: removed re-export block that created a cyclic import with `topology_cytoscape_html`
- `modules/topology_cytoscape_html.py`: promoted lazy `build_cytoscape_elements` imports to module-level now that the cycle is broken
- `tests/test_topology_cytoscape_html.py`: unified import form to `from modules import topology_cytoscape_html` to resolve CodeQL `py/import-and-import-from`

---

### v2.1.8

**Changed**
- Overview tiles: staleness callout shown when data is >24 h old ("Data from X days ago — rescan?" in amber); 30 min+ shown in amber, 2 h+ in red
- Notifications page: split into "Configure" tab (channel cards, alert rules, dependency tree) and "Alert History" tab; switching to history auto-refreshes the log
- Alert history: storm banner appears when ≥5 alerts from the same /24 subnet arrive within 60 s, with a direct link to the dependency tree card
- Auto-resume: monitors (ARP Watch, Live Bandwidth, Scheduled Scans) that were running on last close are restarted on the next launch with an opt-out amber banner

**Fixed**
- `ui/nav/builder.py`: removed invalid `_nav_add_subgroup()` calls in `_build_pro_nav()` that crashed the app with `KeyError: -1`

---

### v2.1.7

**Added**
- `modules/topology_cytoscape_html.py` — HTML/JS page template builder for Cytoscape map split from `topology_cytoscape.py`
- `ui/pages/notif_dep_card.py` — `_NotifDepMixin`: alert dependency tree card; parent–child alert suppression with `_AddDepDialog`; QSettings persistence
- `ui/widgets/alert_drawer.py`: inline acknowledge form with name/comment fields; ack info badge shown on already-acknowledged alerts
- `ui/pages/network_map_page.py`: "Lock Layout" toggle — freezes node positions so re-scans update data without resetting the Cytoscape layout; incremental `window.updateTopology()` used after first load to prevent positional drift

**Fixed**
- `modules/topology_cytoscape.py`: `build_elements_for_update()` exported for incremental topology refreshes without full HTML reload

---

### v2.1.6

**Added**
- `modules/snmp_poller.py`: SNMP interface error metrics — `ifInErrors`/`ifOutErrors` polled per interface; stored in MetricStore and surfaced in SNMP Device Info page

**Fixed**
- Startup cache restore — Network Map and topology widget now render from MetricStore cache on startup without requiring a rescan
- Interactive Network Map blank after scan — Cytoscape.js JS error when master mesh node was referenced as a parent
- Classic and Interactive topology satellite assignments now match the Devices table

---

### v2.1.5

**Fixed**
- All matplotlib chart backgrounds now use `ui/styles.py` tokens
- `QTimer.singleShot` calls replaced with parented `QTimer(self)` instances across widget classes
- `app.py` wiring refactor — always-on worker signals connected after `Dashboard` construction
- Network Map interactive view: hierarchical top-down Cytoscape.js layout and LLDP hint + WebEngine fallback polish

---

### v2.1.4

**Added**
- `modules/lldp_scanner.py` — LLDP/CDP neighbor scanner; passive sniff + active frame mode; raw TLV parser; `LldpNeighbor` dataclass
- `workers/lldp_worker.py` — `LldpWorker` QThread; 15-second sniff in 3-second slices; emits `result_ready(list[LldpNeighbor])`; no-op when not admin
- `modules/topology_snapshot.py` — `TopologySnapshot`, `TopologyDiff`; save/load/diff topology state; change detection for new/removed/moved devices
- `ui/topology_widget.py`: LLDP overlay layer, topology diff overlay, zoom controls, node click → `DeviceDrawer`, health overlays on edges
- `ui/scan_wiring.py`: `_on_lldp_result()` slot wired into `_on_m1_result()` to auto-launch LLDP scan after every device discovery
- `tests/test_lldp_scanner.py` — 11 tests covering import, dataclass, TLV parsing, mocked sniff, and worker lifecycle
- `tests/test_topology_snapshot.py` — tests for `TopologySnapshot` save/load/diff

**Changed**
- `modules/topology_layout.py`: layout keyed on scan-derived `compute_scan_id()` hash so saved positions survive interface changes without poisoning unrelated scans
- Topology map segment pill colours now reflect `NetworkSegment.colour` from `modules/network_segments.py`

---

### v2.1.3

**Added**
- MetricStore schema v13: `device_classification_overrides` table — user-set type overrides survive all enrichment re-runs permanently
- `modules/device_classifier.py`: `get_all_device_types()` — sorted list of every valid device type label for UI dropdowns
- `inventory_page.py`: `_TypeOverrideDialog` — right-click "Override Device Type…" on any device; type combobox with Set/Clear/Cancel
- `inventory_page.py`: confidence indicator prefix in Type column (★ user override, ● high ≥70%, ◑ medium 30–70%, ○ low <30%)
- `inventory_page.py`: Classification section in device detail drawer — current type, override badge, confidence level, evidence list, Clear Override button
- `ui/scan_enrichment.py`: override guard in `_apply_dhcp_fingerprints()` and `_on_passive_observation()` — user-set overrides block all automatic enrichment upgrades
- `tests/test_device_classifier.py`: 5 new tests for `get_all_device_types()`

---

### v2.1.2

**Added**
- `modules/network_segments.py` — `NetworkSegment` dataclass, `auto_detect_segments()`, `classify_device_segment()`, `merge_segments()`; groups scan devices into colour-coded /24 subnets
- MetricStore schema v11: `network_segments` table (CIDR unique, `auto_created` flag, user-editable name/colour)
- `inventory_page.py`: colour-coded segment pill bar above the device table with multi-select filter; Segment `●` column; `_SegmentEditorDialog` for right-click segment editing
- `ui/scan_wiring.py`: segments auto-detected and persisted after every full scan; stored user-defined segments win over auto-detected ones on CIDR conflict
- `tests/test_network_segments.py`: 15 tests covering detection, classification, merge logic, and scaling guard

---

### v2.1.1

**Fixed**
- `modules/rogue_device.py`: proxy-ARP deduplication — IPs sharing the gateway MAC are collected in `proxy_arp_ips` and excluded from device results so the gateway never appears twice
- `modules/rogue_device.py`: gateway device always classified as `Router / Gateway` via `is_gateway` parameter, chip-OUI heuristic, and consumer-hostname sanity check
- `ui/scan_enrichment.py`: gateway hostname guard in plugin enrichment loop — plugin client entries whose IP matches the gateway are skipped
- `ui/scan_enrichment.py`: gateway MAC filtered from `_plugin_enrichments` so the router's own MAC never appears as a client device
- `ui/scan_enrichment.py`: IP-keyed hostname sync skips the gateway `DeviceInfo` object to prevent the mesh/table-cell sync from overwriting the gateway hostname
- `ui/scan_enrichment.py`: post-enrichment device-type cell sync writes `DeviceInfo.device_type` back to the Devices table for all devices with a known type
- `tests/test_scan_enrichment.py`: regression test for shared-MAC (proxy-ARP) sync

---

### v2.1.0

**Added**
- `modules/service_mapper.py` — device_type/vendor → `ServiceInfo` list mapping engine; feeds Service Diagnostics and Service Heartbeat
- `modules/service_diagnostics.py` — `DiagnosticEngine` with service catalog (Netflix, YouTube, Steam, Xbox, PS5, Disney+, Twitch, Spotify) and failure-layer classification
- `modules/service_diagnostics_probes.py` — low-level DNS/TCP/HTTPS/ICMP/traceroute probes used by `DiagnosticEngine`
- `workers/service_diagnostics_worker.py` — `ServiceDiagnosticsWorker` QThread wrapping `DiagnosticEngine.run()`
- `ui/pages/service_diagnostics_page.py` — Service Diagnostics page in the Monitor section; service picker combobox, traceroute toggle, live probe results with per-layer verdict cards
- `DiagnosisPage`: "A service is unreachable" symptom tile — runs `ServiceDiagnosticsWorker`, translates `failure_layer` into a synthetic finding card with plain-English remediation steps
- `ServicePage`: "Diagnose →" right-click context menu item — maps the selected service host to a `SERVICE_CATALOG` entry and navigates to `ServiceDiagnosticsPage` with that service pre-selected
- `ServiceDiagnosticsPage.set_service(id)` — public method to pre-select a service programmatically and focus the Run button
- `tests/test_sprint5_integration.py` — 22 tests covering layer translation, CTA map, `_find_service_id()`, widget state, and `set_service()` pre-selection

**Fixed**
- `ui/scan_enrichment.py`: vendor/type enrichment now populates on first scan — async OUI lookup for Unknown devices without requiring a re-scan
- `modules/service_diagnostics_probes.py`: IPv6 address cast to `str` before assignment; `CREATE_NO_WINDOW` guarded with `getattr` for non-Windows platforms; traceroute reach-check now correctly references `result.host`

---

### v2.0.1

**Fixed**
- Sorting any table column no longer crashes with `TypeError` — PyQt6 `Qt.SortOrder` enum now correctly accessed via `.value` before storing to `QSettings`
- `setTextAlignment()` calls in `dhcp_lease_page`, `dns_zone_page`, and `threat_intel_page` now pass the `Qt.AlignmentFlag` enum directly instead of wrapping in `int()`
- All tables using the shared `_table()` helper now auto-size columns to content (`ResizeToContents`) instead of a fixed 120 px default; last column stretches to fill available space
- Network Grade table columns (Dimension, Grade, Your Value, Ideal, Verdict) no longer truncate text

---

### v2.0.0

**Added**
- `packaging/AppxManifest.xml`: declared `windows.startupTask` (uap5, disabled by default) — enables user-controlled auto-start via Settings → Apps → Startup for Microsoft Store builds
- `app.py`: `--startup-logger` flag — starts the app minimised to the system tray and auto-starts the Network Logger; fired by the Windows startup task when the user opts in

**Changed**
- `ui/system_tray.py`: "Launch at Startup" registry entry now registers `--startup-logger` instead of `--minimised`, so enabling auto-start also begins background logging
- `ui/pages/settings_cards.py`: startup checkbox label updated to reflect that auto-start runs as a background logger

---

### v1.9.99

**Fixed**
- `ui/header.py`: snap-layout maximize button no longer crashes with `RPC_E_WRONG_THREAD` when a native file dialog is open — `_toggle_maximize()` is now invoked via `QMetaObject.invokeMethod` with `QueuedConnection`
- `app.py`: `tplinkrouterc6u` pre-imported on the main STA thread before any background workers start — eliminates `RPC_E_WRONG_THREAD` crash loop on app restart after a wild chaos run
- `tools/monkey_test.py`: raised `_UNRESPONSIVE_SECS` from 20 s to 45 s — prevents false-positive test terminations on slow connections
- Navigation animations and live chart redraws: eliminated linear memory accumulation where old `FuncAnimation` / `Line2D` objects were never released between redraws

---

### v1.9.98

**Fixed**
- `ui/pages/cve_page.py`: CVE Tracker now shows an empty state with "Run Scan" CTA when no CVEs are tracked
- `ui/pages/threat_intel_page.py`: added `focus_on_host()` slot to pre-filter the threat feed to a specific IP
- `ui/dashboard.py`: About dialog displayed literal `&amp;` entity — replaced with plain `&`

**Changed**
- `ui/pages/cve_page.py`: right-click context menu now includes "Check in Threat Intel" — navigates to Threat Intel page pre-filtered to the selected IP
- `ui/tabs.py`: wired `lookup_threat_intel_for` signal on CVE page to `focus_on_host()` on Threat Intel page with automatic nav jump
- `ui/pages/live_bandwidth_page.py`: removed unused `scan_requested` signal
- `ui/pages/dns_zone_page.py`: removed unused `scan_requested` signal

---

### v1.9.97

**Changed**
- `ui/pages/discover_data.py`: Feature Guide groups reworked by user purpose — `"Advanced"` group eliminated; threat-detection features consolidated into `"Security"`; scheduling and integration tools into new `"Automation"` group; monitoring infrastructure into `"Monitoring"`; utility/visualization tools into `"Diagnostics"`

---

### v1.9.96

**Fixed**
- `ui/pages/discover_data.py`: corrected Feature Guide group assignments for 8 entries — Npcap-gated Analysis tools moved to correct groups

**Changed**
- RULE-D2 updated with canonical Feature Guide group → nav section mapping table

---

### v1.9.95

**Fixed**
- `tools/test_setup.ps1`: replaced UTF-8 box-drawing characters with ASCII equivalents to prevent PowerShell 5.1 parse error

**Validated**
- Chaos/stability run (2026-06-10): 10,001 UIA interactions across mild / moderate / wild chaos levels — 0 exceptions, 0 crashes; all 62 pages navigable before and after

---

### v1.9.94

**Changed**
- `ui/pages/home_page.py`: removed theme-chooser banner from the home page
- `ui/header.py`: removed theme cycle button from the top navigation bar
- `ui/widgets/home_session_widgets.py`: merged "Connect your router" and "Connect your modem" Getting Started steps into a single "Connect your hardware" step

**Fixed**
- `ui/pages/inventory_page.py`: Devices page now shows a "Current Devices" snapshot card after a scan — IP, hostname, MAC, manufacturer, type, and risk without requiring hardware plugins

---

### v1.9.93

**Fixed**
- `ui/widgets/coach_mark.py`: added `_HighlightRing` — blue border ring drawn around the target widget while each coach mark step is active
- `ui/dashboard.py`: post-scan tour (Steps 2–9) now fires immediately after "Got it" on Step 1, without waiting for scan to complete
- `ui/dashboard.py`: added Hardware Hub as Step 9 of 9 in the onboarding tour; tour navigates to Overview on completion

---

### v1.9.92

**Fixed**
- `release.yml`: add `update_release: true` to `softprops/action-gh-release` — prevents "already_exists" failure when a tag is re-pushed or CI is retriggered for an existing release

---

### v1.9.91

**Fixed**
- `ui/command_palette.py`: command palette now opens non-modally (`show()` instead of `exec()`) — clicking anywhere outside the palette dismisses it
- `ui/widgets/page_header.py`: `_HelpPopover.show_at()` now clamps position to `screen.availableGeometry()` so the help popover never renders partially off-screen
- Resolved 100+ CodeQL code-scanning alerts across `modules/`, `workers/`, `tools/`, and `ui/`
- Test suite: eliminated intermittent `STATUS_STACK_BUFFER_OVERRUN` heap corruption caused by unparented `QTimer.singleShot()` and Qt widgets deleted by Python GC instead of `deleteLater()`
- CI pipeline: ruff, mypy, pip-audit all now pass; CVE findings in dependencies resolved

**Changed**
- `tools/monkey_test.py`: `_dismiss_blocking_dialogs()` detects Windows common file dialogs and dismisses them immediately
- `tools/monkey_test.py`: `_act_edit()` strips pywinauto key-sequence special characters before `type_keys()`
- `tools/monkey_test.py`: default `mem_limit_mb` raised 800 → 1500 MB
- `tplinkrouterc6u` dependency updated to `~=5.22`

**Security**
- pip-audit CVE findings resolved; `requirements.txt` updated to patched versions

**Validated**
- 9-hour overnight chaos run: 10,001 UIA interactions across mild / moderate / wild chaos levels; zero application crashes; all 61 pages pass systematic pre/post coverage; app confirmed production-stable

---

### v1.9.90

**Fixed**
- `ui/command_palette.py`: command palette now opens non-modally; app-level `installEventFilter` in `showEvent` / `removeEventFilter` in `hideEvent` so outside-click detection fires correctly
- `ui/widgets/page_header.py`: `_HelpPopover.show_at()` now clamps position to screen available geometry
- `tests/test_monkey_test.py`: marked `pytest.mark.monkey` and excluded from CI `addopts`
- `tools/monkey_test.py`: dependency checks now raise `ImportError` instead of `sys.exit()` when imported without `pywinauto`
- `tools/monkey_test.py`: `_dismiss_blocking_dialogs()` detects Windows common file dialogs
- `tools/monkey_test.py`: `_act_edit()` strips pywinauto key-sequence special characters

**Changed**
- APM instructions updated: Roadmap / backlog section removed
- `tools/monkey_test.py`: default `mem_limit_mb` raised from 800 → 1500 MB

**Validated**
- 9-hour overnight chaos run (June 2026): 10,001 UIA interactions; zero application crashes; all 61 pages pass

---

### v1.9.89

**Added**
- `tools/monkey_test.py` — pywinauto UIA + psutil chaos/monkey harness; `--source`, `--connect`, and exe-path modes; mild/moderate/wild chaos levels; memory/CPU health monitor; screenshot on crash; seed-reproducible runs
- `tests/test_monkey_test.py` — 11 unit tests covering import, `Config`, `Stats`, `History`, blacklist logic, and CLI smoke test
- `requirements-dev.txt` — documents `pywinauto`, `psutil`, and `Pillow` as dev-only dependencies

---

### v1.9.88

**Added**
- `ui/widgets/diagnostic_card_widget.py` — `render_card_widget()` extracted from `modules/diagnostic_card.py` to eliminate PyQt6 dependency in the module layer
- `tests/test_metric_store_queries_metrics.py` — 14 behavioural tests for `_MetricsQueriesMixin`
- `tests/test_metric_store_queries_uptime.py` — 12 behavioural tests for `_UptimeQueriesMixin`

---

### v1.9.87

**Fixed**
- `report_exporter.py`: removed phantom `save_nmap_report` from `__all__`
- `speed_tester_backends.py`: SSL shim now sets `minimum_version = TLSv1_2`
- `network_log_writer.py`: host-presence check converted from `in` operator to set superset `>=`
- `report_isp.py`: implicit three-way string concatenation in list wrapped in parentheses
- `test_source_encoding.py`: regex character-class patterns for Windows-1252 curly quotes fixed
- `debug_launch.py`: log file registered with `atexit` to ensure closure even on exception
- `dashboard.py`: removed unused `n_findings` variable; empty `except` block now logs at DEBUG level

**Changed**
- README Quality section: test count corrected

---

### v1.9.86

**Fixed**
- `scan_wiring.py`: `AMBER_BG` / `RED_BG` `NameError` crash on internet exposure scan results
- `hub_helpers.py`: stale "Plugin" nav item after settings reset — `_is_temp_artifact` now catches `pytest-of-` temp paths
- `hardware_integration_page.py`: "How to write a plugin script" guide moved to a dedicated **Write a Plugin** tab

**Added**
- Settings → Maintenance: **Skip all guided hints** button marks all 7 coach-mark keys as seen in one click

---

### v1.9.85

**Changed**
- `ui/onboarding.py`: rewrote 9-step sequence to value-first order — scan fires on step 1, step 2 shows real device list, steps 4–5 show Speed Test and Logger already running
- `ui/onboarding.py`: `_step1_fire_scans()` starts scan + speed test (500ms) + logger (1s) at step 1
- `tests/test_onboarding.py`: fully rewritten to validate new step sequence

---

### v1.9.84

**Fixed**
- `ui/onboarding.py` step 6 (Network Grade): tile grid now shows immediately instead of the "Scan" CTA
- `ui/onboarding.py` step 7 (Logger): replaced three broken spotlight targets that resolved to `None`
- `ui/pages/speed_test_page.py`: empty-state "Run Speed Test →" CTA now hides while a test is in progress

**Added**
- `ui/pages/log_hub_page.py`: `self._sources_bar` attribute exposes the source-toggle bar widget for spotlight targeting
- `ui/pages/home_page.py`: hardware nudge bar shown after onboarding completes until first hardware plugin is configured

---

### v1.9.83

**Added**
- `_HelpPopover` now shows a three-section layout: "What it does", up to two usage tips, and global keyboard shortcuts

**Changed**
- `_wire_page_help_btn()` now passes `hidden` tips to `set_help()` so the ? popover shows contextual tips per page

**Removed**
- Quick Tips card removed from `HomePage` — keyboard shortcut hints are now surfaced via the ? button on every page header

---

### v1.9.82

**Added**
- `_recurring_intro_card` on `HomePage` — one-time "Home page upgraded" banner shown when recurring mode activates for the first time
- `_setup_complete_card` on `HomePage` — celebration card replacing `GettingStartedCard` once all 6 setup steps are done
- `completion_done` signal on `GettingStartedCard` — emitted 2 s after all steps complete
- `FreshnessStrip.update_logger_tooltip()` — enriches the Logger pill tooltip with "logging since X" when logger is active

---

### v1.9.81

**Added**
- Contextual coach marks — 5 per-feature one-shot overlays keyed to individual `coach/*` QSettings flags
- `tests/test_coach_marks.py` — 22 tests covering flag hygiene, skip conditions, and method presence

---

### v1.9.80

**Changed**
- `overview_page.py` — tile grid wrapped in `QStackedWidget`; shows `EmptyStateCard` on first launch
- `snmp_trap_page.py` — custom inline empty state replaced with `EmptyStateCard`
- `wifi_monitor_page.py` — frame table wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Start Monitoring →" CTA
- `geo_map_page.py` — map + IP table wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Scan to discover IPs →"
- `timeline_page.py` — event feed wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Run a scan →"
- `speed_test_page.py` — plain-label empty state upgraded to `EmptyStateCard`
- `trend_page.py` — analysis content wrapped in `QStackedWidget`; shows `EmptyStateCard` with "Start Logger →"

---

### v1.9.79

**Added**
- `tests/test_diagnosis_page.py` — verify_step rendering tests

**Changed**
- Diagnosis finding cards now render `verify_step` text and a "Verify this fix" button that runs a focused re-check
- `DiagnosisWorker` accepts `focused_on` parameter to run only checks relevant to a specific finding headline
- Post-scan sheet dismissal is now per-scan; `FreshnessStrip` shows `[N findings]` link to re-open the sheet
- Diagnosis page shows an amber inline warning when Network Logger has less than 2 hours of data

---

### v1.9.78

**Added**
- `tests/test_getting_started_card.py` — step order, `_checklist_states` keys, `notify_hw_detected` and pill-type assertions
- `tests/test_log_hub_empty_state.py` — `start_logger_requested` signal, content stack page count, CTA button presence

**Changed**
- Getting Started card step order: scan is now first, hardware steps second, logger added as step 6
- FreshnessStrip monitoring pills converted from `QLabel` to `QPushButton` (flat); clicking an inactive pill navigates to the relevant page
- Log Hub empty state replaced with `EmptyStateCard` + "Start Network Logger →" CTA

---

### v1.9.77

**Changed**
- Architecture documentation corrected to match actual codebase: 7 missing `ui/` files added, 2 duplicate entries removed, non-existent worker stubs removed

---

### v1.9.76

**Changed**
- Settings > Appearance: theme selector replaced with visual mini swatch cards (128×90 px each) showing a scaled colour preview
- Theme banner and header theme-cycle button now apply themes instantly via `apply_theme()` instead of requiring a restart

---

### v1.9.75

**Fixed**
- `settings_cards.py`: Configuration Status chips rendering black — `_chip_style()` returned plain strings instead of f-strings
- `hub_helpers.py`: Plugin instances stored with stale PyInstaller temp-dir paths resolved to stable `AppData/plugins/` copy on load
- `hardware_integration_page.py`: Credential dialog was silently skipped when re-registering a plugin after a settings reset
- `deco_client.py`: Deco XE75 authentication now falls back to HTTPS with `verify_ssl=False` when HTTP times out
- `deco_plugin.py`: `_fmt_err` network keywords now checked before auth keywords so timeout errors show correctly
- `plugin_page_mixin.py`: `_reload_section` called with wrong kwarg; Extend flyout now updates correctly after adding a plugin
- `credential_dialog.py`: Dialog now centers on main window instead of appearing off-screen

---

### v1.9.74

**Added**
- `ui/styles.py`: `apply_theme()`, `apply_accent_override()`, `get_theme_manager()`, `get_app_qss()` — live theme switching without restart
- `ui/dashboard.py`: `_on_theme_changed()` slot re-applies MAIN_STYLE cascade
- `ui/nav/rail.py`: `refresh_theme()` on rail and flyout widgets
- `tests/test_themes.py`: 8 new tests for live theme API

**Changed**
- Settings → Appearance: theme and accent changes now apply immediately
- `app.py`: QMenu/QToolTip QSS injected via `get_app_qss()` so it reflects the active theme at runtime

---

### v1.9.73

**Added**
- `ui/nav/builder.py` — `_proactive_wire_page_help_btns()` wires the `?` help button on every page at startup

**Changed**
- `ui/help_tab.py` — keyboard shortcuts table expanded to 15 entries
- `ui/pages/settings_cards.py` — keyboard shortcuts card expanded to 11 entries with grouped categories
- `ui/pages/settings_page.py` — settings search now performs full-text match against per-card keyword strings
- `app.py` — fixed `_home_automation_page` → `_ha_page` and `_trigger_builder_page` → `_trigger_page` in scan_requested wiring

---

### v1.9.72

**Added**
- `modules/metric_store_queries_uptime.py` — `_UptimeQueriesMixin` with 5 uptime/device-state query methods
- `modules/metric_store_queries_metrics.py` — `_MetricsQueriesMixin` with 10 RTT/speed/CVE/alert/modem/mesh query methods
- `tests/test_metric_store_queries_split.py` — 15 tests covering split composition and behaviour
- `ui/styles.py` — "Abyss" WCAG AA high-contrast theme: true black backgrounds, steel teal accent

**Changed**
- `modules/metric_store_queries.py` — reduced from 619 to 299 lines; now a facade inheriting the two new mixins
- `tests/test_worker_lifecycle.py` — added `SpeedTestWorker`, `CombinedDiscoveryWorker`, and `BandwidthWorker` lifecycle tests

---

### v1.9.70

**Added**
- `modules/lab_scenarios.py` — 6 new lab scenarios: Measure DNS Resolver Speed, Find an Open Port, Detect a DHCP Conflict, Measure Network Jitter, Identify Device Manufacturers, Read a Network Topology Map (total now 10 scenarios)
- `ui/pages/lab_mode_page.py` — `_run_port()` and `_run_dhcp()` scan runners added for new scenario scan types

**Changed**
- `ui/pages/home_page.py` — monitoring pills now carry plain-English `setToolTip()` text explaining what each monitor does
- `ui/widgets/alert_drawer.py` — "WHAT TO DO" section added with per-alert-type actionable fix text

---

### v1.9.69

**Added**
- `ui/widgets/empty_state_card.py` — reusable `EmptyStateCard` widget with icon, what/why copy, and CTA button
- `data/glossary.json` — 30 plain-English definitions for network terminology
- `ui/widgets/jargon_tooltip.py` — `JargonTooltip` QLabel subclass: underlines a term and shows its definition on hover
- `tests/test_empty_state_card.py` — widget construction, signal emission, and content tests
- `tests/test_jargon_tooltip.py` — glossary file validation and widget behaviour tests

**Changed**
- `ui/pages/inventory_page.py`, `uptime_page.py`, `cert_page.py` — bare empty states replaced with `EmptyStateCard`
- `ui/pages/security_overview_page.py` — findings section empty message replaced with structured widget
- `ui/pages/protocol_viz_page.py` — `select_protocol(key)` public API added
- `ui/pages/lab_mode_page.py` — `explore_protocol = pyqtSignal(str)` added; "See how X works →" button navigates to Protocol Visualizer

**Fixed**
- `ui/tabs_recon.py` — `@pyqtSlot("QPoint")` replaced with `@pyqtSlot(QPoint)` — fixed Dashboard startup crash

---

### v1.9.68

**Added**
- `modules/plugin_registry.py`: Windows MAX_PATH guard — `install_plugin()` truncates filename stems to 80 chars before writing
- `tests/test_hardware_integration.py`: 8 new tests covering `CONFIG_SCHEMA` end-to-end

---

### v1.9.67

**Fixed**
- `notification_channels.py`: Pushover, ntfy, and Telegram delivery failures now reported in alert history
- `metric_store_queries.py`: `query_uptime_table()` reduced from N+1+N×M queries to 1+len(windows) GROUP BY queries
- `metric_store_queries.py`: replaced `SELECT *` with explicit column lists in key query methods
- `home_page.py`: un-parented `QTimer.singleShot(2500, banner.hide)` replaced with parented `QTimer(banner)`
- `maintenance_window.py`: documented UTC requirement for `start_ts`/`end_ts` in `is_currently_active`
- `test_source_encoding.py`: extended mojibake detection to cover 4-byte emoji sequences
- `requirements.txt`: bumped `pytest-cov` from ~=5.0 to ~=7.1

**Security**
- Resolved 30 CodeQL code-scanning alerts: unused imports removed, empty `except` blocks documented, dead code removed

---

### v1.9.66

**Changed**
- `ui/dashboard.py`: 6,472→**1,967 lines** — three further mixin extractions complete the dashboard decomposition; inherits `ScanResultMixin`, `AppHeaderMixin`, `TabBuilderMixin`, `_NavBuilderMixin`, `_MonitorStateMixin`, `_PluginPageMixin`
- `ui/scan_wiring.py`: 1,279→676 lines — inherits `ScanEnrichmentMixin`; 12 duplicate enrichment methods removed
- `ui/scan_enrichment.py`: 634→1,230 lines — `_apply_mesh_enrichment`, `_regroup_m1_by_satellite`, and 7 M1 table helpers added

**Added**
- `ui/tabs_recon.py` — `_ReconTabsMixin`: 29 security-audit recon tab builders
- `ui/nav/builder.py` — `_NavBuilderMixin`: all nav structure building, runtime switching, command palette, pin management
- `ui/monitor_state.py` — `_MonitorStateMixin`: verdict/badge/pill display, KPI tiles, `VerdictPanel`, `RiskBadge`
- `ui/plugin_page_mixin.py` — `_PluginPageMixin`: plugin page lifecycle, hardware auto-detect, integration banner

---

### v1.9.65

**Changed**
- `ui/tabs_diag.py`: logger tab + retention helpers extracted to `ui/tabs_logger.py`; `tabs_diag.py` 1,182→448 lines
- `ui/pages/home_page.py`: 2,238→1,128 lines — widget classes moved out; all data handlers extracted to `_HomeDataMixin`

**Added**
- `ui/tabs_logger.py` — `_LoggerTabMixin`: Network Logger tab builder, logger start/stop handlers, live-challenge handlers, retention helpers
- `ui/pages/home_data_mixin.py` — `_HomeDataMixin`: all data update and public slot methods for `HomePage`

---

### v1.9.64

**Added**
- `tests/test_port_scanner.py` — 15 tests for `modules/port_scanner.py`
- `tests/test_report_pdf.py` — 6 tests for `modules/report_pdf.py`
- `tests/test_module_coverage_gate.py` — CI gate: every `modules/*.py` must have a `tests/test_*.py`
- `tests/test_codeql_prevention.py`: `test_no_hardcoded_hex_in_ui_files` — AST-based hex-colour enforcement gate

---

### v1.9.63

**Added**
- `ui/tabs_analysis.py` — `_AnalysisTabsMixin`: IPv6, Cloud Metadata, Root Cause Correlator, IoT Baseline, and Benchmark tab builders
- `ui/widgets/kpi_bar.py` — `_KpiBarMixin`: KPI bar widget + update logic
- `ui/pages/discover_data.py` — `_FEATURES` list and `_GROUPS_ORDER` data extracted (page reduced from 1,360 → 229 lines)
- `ui/pages/help_content.py` — `_PAGE_HELP` dict extracted from `ui/help.py`
- `ui/pages/home_suggestions.py` — `_HomeSuggestionsMixin` extracted from `ui/pages/home_page.py`
- `ui/pages/settings_appearance.py` — `_SettingsAppearanceMixin` stub
- `ui/pages/notif_extra_channels.py` — `_NotifExtraChannelsMixin`
- `ui/scan_enrichment.py` — `ScanEnrichmentMixin` extracted from `ui/scan_wiring.py`
- `ui/widgets/overview_tile_monitor.py` — monitoring tile classes extracted
- `ui/widgets/device_detail_panels.py` — `_ModemDetailPanel`, `_RouterDetailPanel` extracted
- `ui/widgets/device_detail_pane.py` — device detail widgets extracted
- `ui/widgets/modem_signal_panel.py` — `_ModemSignalPanelMixin` extracted
- `ui/tabs_diag_extra.py` — `_DiagExtraTabsMixin`

---

### v1.9.62

**Added**
- `tests/test_colour_inventory.py` — per-file hardcoded-hex budget tables for 63 UI files
- 18 new Tier 2 scan/detection module test files — 140 new tests

**Changed**
- `ui/dashboard.py` and related files: removed dead flat-nav mode system — `_nav_mode`, `_nav_goto_label`, and related infrastructure

---

### v1.9.61

**Added**
- `ui/tabs.py` — `TabBuilderMixin` extracted from `dashboard.py`
- `ui/header.py` — `AppHeaderMixin` extracted from `dashboard.py`
- `ui/app_settings.py` — `save_settings()`, `restore_settings()`, `center_on_screen()` extracted
- `ui/help.py` — `build_help_tab()` extracted
- `ui/widgets/hub_helpers.py` — pure data-persistence helpers extracted from `hub_card.py`

---

### v1.9.60

**Added**
- `modules/metric_store_schema.py` — DDL, schema version, column migrations, and all dataclasses extracted from `metric_store.py`
- `modules/metric_store_queries.py` — `MetricStoreQueryMixin` with all read/query methods
- `modules/report_html.py` — CSS template and HTML generation helpers extracted
- `modules/report_pdf.py` — `save_pdf_report()` with weasyprint/headless-browser cascade
- `modules/utils_net.py` — `get_network_info()`, `get_dhcp_info()`, `get_interface_details()` extracted
- `modules/utils_platform.py` — `get_ipv6_devices()`, `ping_sweep_ipv6()` extracted

**Changed**
- `modules/metric_store.py`: 1,673 → 623 lines; WAL checkpoint at startup if `-wal` > 50 MB
- `modules/report_exporter.py`: 1,241 → 716 lines
- `modules/utils.py`: 1,055 → 421 lines

---

### v1.9.59

**Changed**
- `ui/dashboard.py`: 23 `_on_*_result` scan-result handlers extracted to `ui/scan_wiring.py` as `ScanResultMixin`; dashboard.py reduced from 13,483 → 10,046 lines
- `ui/pages/hardware_integration_page.py`: `HubCard` and plugin helpers extracted to `ui/widgets/hub_card.py`
- `ui/pages/overview_page.py`: all 14 Overview tile classes extracted to `ui/widgets/overview_tile.py`

---

### v1.9.57

**Fixed**
- `ui/topology_widget.py`: invalid escape sequence in module docstring — eliminates `DeprecationWarning` in full test run

---

### v1.9.56

**Fixed**
- Test suite crash (`STATUS_STACK_BUFFER_OVERRUN`): `QFileSystemWatcher` OS threads in `test_hardware_integration.py` accumulating without cleanup
- Removed module-level `QApplication` creation from 7 test files — conftest.py's session fixture now owns the `QApplication`

**Added**
- `tests/test_codeql_prevention.py` — static AST checks for bare `except:` blocks and URL substring comparisons
- `tests/conftest.py` QSettings isolation fixture — each test gets a unique org/app name
- `tests/conftest.py` crash logger fixture — writes test names to `ns_test_crash_log.txt` before each run

---

### v1.9.55

**Fixed**
- `data/plugin_hashes.json` hashes now computed on LF-normalised content — fixes CI failures on Linux/macOS checkout
- Documented the APM gap: `.apm/instructions/` are the true sources; `bump_version.py` regenerates `.claude/rules/`

---

### v1.9.54

**Fixed**
- Resolved all open CodeQL alerts: `py/empty-except` comments added across 8 files
- Removed unused imports from 4 modules and all affected test files

---

### v1.9.53

**Fixed**
- `data/plugin_hashes.json`: regenerated after bundled plugin edits; stale hashes caused `_start_poll_worker_inst` to silently return early
- `ui/pages/hardware_integration_page.py`: added explanatory comments to five bare `except: pass` blocks

---

### v1.9.52

**Added**
- `HubCard`: `✎` rename button on every hub card — change propagates atomically to nav flyout, breadcrumb, pinned set, and command palette
- `tests/test_credential_robustness.py` — 8 tests: instance ID determinism, multi-instance independence, rename registry update
- `tests/test_plugin_isolation.py` — 5 tests: module namespace isolation between poll cycles
- `tests/test_plugin_resilience.py` — 10 tests: backoff interval calculation, circuit breaker behaviour

---

### v1.9.50

**Fixed**
- `workers/plugin_polling_worker.py`: replaced `os.environ["NETSENTINEL_PLUGIN_IP"]` with direct module-attribute injection — each instance gets its own namespace, zero cross-instance IP pollution
- `HubCard`: adds `🔑 Re-enter Password` button shown only on `AUTH:` errors
- `ui/dashboard.py`: `_reload_section(name, force_open)` helper consolidates flyout-reload logic

**Added**
- `tests/test_env_var_isolation.py` — 6 tests: module attribute preferred over env var; concurrent `exec_module` loads have independent namespaces

---

### v1.9.48

**Added**
- `modules/nspkg.py` — `.nspkg` plugin bundle format (ZIP with `plugin.py` + `manifest.json` + optional `icon.png`)
- Hardware Hub "⬡ Import .nspkg" button
- `CONFIG_SCHEMA` support — plugins declare typed config fields; `HubCard` auto-generates a ⚙ config panel
- Community plugin Browse tab — fetches a GitHub-hosted JSON index; per-entry SHA-256 verified before download
- `tests/test_nspkg.py` — 13 tests covering bundle unpacking, manifest validation, and error paths
- `tests/test_community_index.py` — 9 tests covering index fetch, SHA-256 mismatch, and download success

---

### v1.9.47

**Added**
- `modules/plugin_tools.py` — plugin validator CLI; static checks for required constants, function signatures, top-level network calls, and imports outside safe list
- `tools/generate_plugin_hashes.py` + `data/plugin_hashes.json` — build-time SHA-256 hash list for bundled plugins
- Hardware Hub "⬡ New Plugin" button — template wizard dialog generates a filled-in `.py` file
- Plugin icon support — `HubCard` displays 24×24 PNG icon from `icon.png` or `ICON_PATH` constant
- `tests/test_plugin_tools.py` — 23 tests covering validator, signature check, and CLI

---

### v1.9.46

**Added**
- `workers/plugin_polling_worker.py`: `log_line` signal emits structured per-poll log entries
- Hardware Hub `HubCard`: `≡ Logs` toggle button expands a collapsible console showing the last 100 plugin log lines
- P4-1 unsigned plugin warning dialog — shown once per unique plugin file before registering a non-bundled script
- `tests/test_plugin_validator.py` — 16 tests for `_validate_script` and `_classify_error`
- `tests/test_plugin_health.py` — 15 tests for health tracking and circuit-breaker
- `tests/test_hub_card_errors.py` — 13 tests for `HubCard.set_error` routing

---

### v1.9.45

**Added**
- Home page unified "Getting Started" checklist with "Add →" buttons that open the credential dialog directly

**Changed**
- `modem_page.py`, `mesh_router_page.py` and their workers removed; ZTE MC889 and TP-Link Deco XE75 managed exclusively via the hardware plugin system

**Fixed**
- `home_page.py`: `_check_recurring_mode` was iterating dict keys instead of values when testing setup completion

---

### v1.9.44

**Added**
- `ui/first_run_dialog.py`: 3-slide Apple-style welcome wizard with progress dots, Back/Next navigation, and "Scan my network →" CTA
- `PluginDevicePage` modem view: `SignalBar` widgets for RSRP and SINR

**Changed**
- Extend nav section: "Modem" and "Mesh & Router" legacy items removed; hardware plugin pages are the sole nav entries under Extend

---

### v1.9.43

**Added**
- `tests/test_hardware_integration.py` — 35 tests covering crash scenarios and plugin import lifecycle
- Hardware plugin dependency auto-install: `PYPI_PACKAGE` constant added to 6 bundled plugins; clicking "＋ Add" opens `PipInstallDialog` automatically if the library is missing

**Fixed**
- `hardware_integration_page.py`: `RecursionError` crash from infinite signal loop via `_on_hardware_plugin_result`
- `hardware_integration_page.py`: `AttributeError` when `network_type` key is present but `None`
- `hardware_integration_page.py`: startup crash when QSettings data is corrupt or a plain string
- `hardware_integration_page.py`: `RuntimeError: wrapped C/C++ object deleted` when a `HubCard` was removed while its refresh `QTimer` was still pending

---

### v1.9.42

- **wmic → CimInstance migration** — all credentialed-scan Windows commands ported from deprecated `wmic` to `powershell -NoProfile Get-CimInstance`; fully compatible with Windows 11 24H2
- **REST API hardening** — CORS restricted to `localhost` origins only; query-parameter auth removed; switched from Flask dev server to waitress WSGI
- **CLI output path validation** — `cli.py` resolves output paths with `Path.resolve()` and creates missing parent directories
- **MSIX cosign signing in CI** — release workflow signs the MSIX artifact with `cosign sign-blob` (keyless OIDC)

---

### v1.9.41

- **Notification channel test buttons** — Settings > Active Integrations shows a "Send test" button next to Email, Webhook, and Pushover rows
- **Accent colour picker** — Settings > Appearance gains a row of 6 preset accent swatches and a "Custom…" colour dialog
- **Settings export / import** — Settings > Maintenance gains "Export settings (JSON)" and "Import settings" buttons backed by `modules/settings_io.py`; secrets remain in the OS keychain
- **Signal strength bar widget** — new `ui/widgets/signal_bar.py` QPainter widget draws 5 phone-style vertical bars for RSRP, RSRQ, SINR, SNR
- **Reports chart preview** — Reports page shows a matplotlib sparkline of device count and network grade for the last 7 days

---

### v1.9.40

- **Geo map enriched detail panel** — clicking a mapped IP shows a full enriched panel: flag + country/city, ASN/org, threat-intel risk chip, alert count, and "View in Threat Intel →" button
- **Bandwidth event annotations** — rate-spike and new-device events annotated directly on the Live Bandwidth chart
- **Protocol visualizer name overlay** — AnimNodes with IP addresses enriched with device hostname from the last inventory scan
- **Alert badge decay** — when a rail-section badge is cleared, it fades out over 400 ms
- **Inventory scan comparison** — Inventory page gains a "⊞ Compare" toolbar button for modal diff dialog
- **Speed test baseline** — right-click any Speed Test history row to "★ Set as Baseline"; subsequent rows display download/upload delta arrows

---

### v1.6.4

- One-click "What's Wrong?" diagnosis — symptom tiles (slow / dropping / can't connect), sequences network diagnostics → storm → rogue device → STP checks, surfaces a "Do this first" priority finding card
- Shareable diagnostic card — "Share Card ▾" button on Overview; exports a summary card (grade, ISP, top 3 findings) as PNG or HTML
- Lab / Scenario Mode — four guided exercises with progressive hints, solution reveal, and exportable HTML result report
- Network Doc page now receives real data after every scan
- MQTT / HA page wiring — device join/leave events, alerts, and uptime states now flow to the MQTT publisher automatically
- Fixed `ModuleNotFoundError` crash on startup in installed builds

---

### v1.6.2

- Top-bar brand icon — replaced the "N" letter placeholder with the actual app icon (24×24, smooth-scaled)
- New icon design — hexagon + shield identity across all sizes: ICO (7 resolutions), MS Store tiles, macOS/Linux PNG
- `generate_icons.py` — new script regenerates all raster assets from the embedded design
