# Changelog

All notable changes to NetSentinel are documented here. The current version summary lives in [README.md](README.md#changelog); the full history is below.

---

### v2.1.18

**Added**
- `modules/device_types.py` — canonical device-type label constants (`TYPE_SMART_PLUG`, `TYPE_SMART_THERMOSTAT`, `TYPE_SMART_BULB`, Matter); import from here, never hardcode strings (P1-1–P1-4)

**Fixed**
- Nest vendor regex no longer collides with generic Nest thermostats; wearable dead-code path removed (P0-1, P0-2)

---

### v2.1.17

**Fixed**
- Monitor resume bar now uses informational blue styling instead of amber/warning — resuming a monitor from the previous session is expected behaviour, not a caution event
- "Action needed" card on Home page no longer appears for offline devices; card is now reserved for genuine unacknowledged user-configured alerts only

---

### v2.1.16

**Added**
- `modules/protocol_animator_extra.py` — five additional scene builders (OSPF Hello/LSA, NAT translation, VLAN 802.1Q, TLS 1.3 handshake, ICMP traceroute); Protocol Visualizer expanded from 5 to 10 protocols with a 2-row button grid
- Security Overview Scan Center card — per-audit verdict, last-run timestamp, and staleness timer; scan registry persists results across restarts
- Scan Status tile on the Overview page with live verdict chips for all 5 audit categories
- Last Run chips on the Security Overview header row for at-a-glance audit freshness

**Fixed**
- Security Overview "Run Audit" button now navigates to the correct audit page (was running silently in background with no visible feedback)
- Verdict strings wired into all 5 Scan Status card rows (rows previously showed blank verdict)

---

### v2.1.15

**Added**
- `ui/widgets/inventory_dialogs.py` — `_DeviceLabelDialog`, `_TypeOverrideDialog`, `_ScanCompareDialog`, `_SegmentEditorDialog` extracted from `inventory_page.py` (Sprint 11)
- Settings page category chip bar (`All | Appearance | Monitoring | Alerts | Integrations | Advanced`) with `QSettings("settings/last_category")` persistence
- `ui/guided_tour.py` — 5-step first-run guided tour using `tour/v2_done` key; auto-starts on first launch, restartable from Settings → Advanced
- `ui/widgets/scan_radar_widget.py` — phosphor-green radar sweep animation on Home page during scan wait state (Sprint 6)
- `modules/alert_engine_checks.py` — `_AlertChecksMixin` split from `alert_engine.py` for cert/service check evaluation (file budget relief, Sprint 2)
- Empty state cards with inline "Run Scan" CTA on 8 pages: Connections, CVE, DHCP Lease, DNS Zone, Geo Map, Security Overview, Threat Intel, Uptime (Sprint 5, RULE-UX5)
- Right-click context menus on all 19 scan result tables with "Copy" and "How to Fix" actions (Sprint 4, RULE-UX3)
- Loading states and skeleton placeholders on scan-dependent pages (Sprint 7, RULE-UX2)
- Radar sweep and scan progress bar moved inline into Home page action bar (replaces separate widget)
- RULE-T2 worker lifecycle tests for 22 workers; REST API security tests (`test_rest_api_security.py`)
- Behavioral integration tests for 18 additional pages (`BaselinePage`, `CertPage`, `DhcpLeasePage`, `DnsZonePage`, `GeoMapPage`, `HomeAutomationPage`, `IpCalculatorPage`, `LabModePage`, `LiveBandwidthPage`, `MaintenancePage`, `MonitorOverviewPage`, `MqttPage`, `NetworkDocPage`, `ProtocolVizPage`, `SnmpTrapPage`, `SyslogPage`, `TimelinePage`, `TrendPage`)

**Fixed**
- Devices table blank after scan — `DeviceInfo.get()` was eagerly evaluated before data arrived; now lazy
- Three Inventory scan bugs: vendor not persisted after enrichment, mesh enrichment overwriting live data, blank cells on re-scan
- Scan wiped Devices table for ~10 s on every scan — previous table data now preserved during scan and replaced atomically on completion
- Discovered Devices showing only raw IPs after restart — `_m1_table` now seeded from network map cache on startup
- Redundant left sidebar removed from Settings page; chip bar is now the sole category navigator
- Parented `QTimer(self)` replaces all unparented `QTimer.singleShot` calls in widget classes (RULE-WIN5)
- Removed `__import__` abuse in plugin system; bare `except` blocks annotated with RULE-LINT2 comments
- Chaos foreground claim now asserted before chaos iterations begin, preventing first-iteration miss

---

### v2.1.14

**Fixed**
- `ui/command_palette.py`: `hideEvent` now calls `parent().activateWindow()` so closing the palette returns focus to the main window instead of falling through to the Windows Desktop
- `ui/pages/hardware_integration_page.py`: re-entry guards (`_browse_active`, `_register_active` flags) on `_on_browse` and `_register_plugin` prevent duplicate file/credential dialogs from rapid clicks
- `tools/monkey_test.py`: added RULE-LINT2 inline comment to bare `pass` in `except` block

---

### v2.1.13

**Fixed**
- Monitor resume bar dismiss button (✕) now uses amber accent colour instead of `TEXT_SECONDARY`, making it visible across all three themes

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

### v1.9.x

Development sprint versions (v1.9.48 – v1.9.99). See [git commit history](https://github.com/ossianericson/netsentinel/commits/main) for details.

**Highlights**
- PyInstaller single-exe packaging, Windows Installer (Inno Setup), WinGet distribution
- Plugin ecosystem with `.nspkg` format, signed plugins, multi-instance hardware Hub cards
- CodeQL security hardening and 4,100+ automated tests
- Monkey/chaos tester: 10,001 UIA interactions across 62 pages, zero crashes
- Microsoft Store certification build
