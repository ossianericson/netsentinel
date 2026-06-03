---
paths:
  - "**"
---

# NetSentinel — Architecture & Codebase Reference

## Technology Stack

| Layer | Technology |
|---|---|
| GUI framework | PyQt6 (Python) |
| Charts / graphs | matplotlib (QtAgg backend embedded in QWidget) |
| Network scanning | scapy, nmap, python-nmap |
| Packaging | PyInstaller (produces single-exe builds) |
| Distribution | Inno Setup installer + WinGet (Ookla.Speedtest.CLI as ExternalDependencies) |
| Config persistence | QSettings / INI file (NetSentinel.ini) |
| Data persistence | SQLite via MetricStore (WAL mode, schema v8) |
| Secrets | OS keychain via `keyring` (RULE 22-A) |
| Logging | Python `logging` module + custom CSV logger |

## Repository Layout

```
netsentinel/
├── app.py                  # Entry point — creates QApplication, launches Dashboard
├── cli.py                  # Headless CLI interface
├── svc.py                  # Windows service wrapper
├── requirements.txt
├── apm.yml                 # APM manifest
├── installer.iss           # Inno Setup — includes optional Ookla CLI winget task
├── .github/
│   ├── winget/             # WinGet manifests (Ookla.Speedtest.CLI as ExternalDependencies)
│   └── workflows/
│       └── release.yml     # CI: build → release → winget submit (RULE 20)
├── modules/                # All backend logic (no PyQt imports)
│   ├── alert_engine.py
│   ├── alert_suppressor.py     # EscalationPolicy + _default_rules + rule_settings_key (S20-4 split)
│   ├── arp_monitor.py          # Real-time ARP packet monitor
│   ├── automation_hooks.py     # Event-to-action pipeline and hook dispatcher
│   ├── availability_monitor.py
│   ├── bandwidth_monitor.py
│   ├── cert_monitor.py
│   ├── cloud_metadata.py       # Cloud instance metadata probe (AWS/Azure/GCP IMDS)
│   ├── colours.py              # Colour constants for charts and HTML reports (RULE-AH3 module source)
│   ├── combined_discovery.py   # Main scan orchestrator
│   ├── config_baseline.py
│   ├── credentialed_scan.py    # Authenticated login test scanner (SSH, SMB, FTP, Telnet)
│   ├── credentialed_scan_helpers.py  # Dataclasses + SSH backends + parsers (S20-2 split)
│   ├── cve_lookup.py
│   ├── deco_client.py          # TP-Link Deco XE75 mesh router API client
│   ├── device_classifier.py    # OUI → device type + risk score
│   ├── device_tracker.py
│   ├── dhcp_detector.py
│   ├── dhcp_lease_scanner.py
│   ├── diagnostic_card.py      # Shareable PNG/HTML card (grade, ISP, top 3 findings)
│   ├── digest_builder.py       # Weekly digest content builder (device changes, outage summary)
│   ├── dns_correlator.py       # Ping/DNS latency + outage detection
│   ├── dns_zone_scanner.py     # DNS zone enumeration (AXFR + mDNS)
│   ├── exporter.py             # Multi-format data export helpers (CSV, JSON, PDF)
│   ├── geo_locator.py          # Offline GeoLite2 IP geolocation lookup
│   ├── ha_detector.py
│   ├── hw_detect.py            # Hardware integration detection (USB, serial, GPIO devices)
│   ├── internet_exposure.py
│   ├── iot_baseline.py
│   ├── lab_scenarios.py        # Lab exercise definitions and result dataclasses
│   ├── log_chart.py            # Log chart data builder for Log Hub visualisations
│   ├── mac_lookup.py           # Online OUI/MAC vendor lookup helper
│   ├── mac_registry.py         # OUI database (offenders.json)
│   ├── maintenance_window.py   # Maintenance window schedule and suppression logic
│   ├── metric_store.py         # SQLite time-series DB (singleton, WAL mode, schema v8)
│   ├── metric_store_schema.py  # DDL, schema version, column migrations, dataclasses (S2-1 split)
│   ├── metric_store_queries.py # MetricStoreQueryMixin — cert/service/device/HA/snapshot/grade queries (E3 split)
│   ├── metric_store_queries_uptime.py  # _UptimeQueriesMixin — uptime/device-state query methods (E3 split)
│   ├── metric_store_queries_metrics.py # _MetricsQueriesMixin — RTT/speed/CVE/alert/modem/mesh queries (E3 split)
│   ├── mqtt_publisher.py       # MQTT broker client + Home Assistant Discovery payloads
│   ├── name_resolver.py        # Hostname resolution cascade (mDNS, NetBIOS, rDNS)
│   ├── net_doc_generator.py    # Network documentation HTML/Markdown snapshot generator
│   ├── network_benchmark.py
│   ├── network_diagnostics.py  # Health check routines (ping, traceroute, DNS leak, HTTP)
│   ├── network_infrastructure.py  # VLAN, gateway, routing table helpers
│   ├── network_log_writer.py   # Log dataclasses, file reader, summary + analysis engine (S20-6 split)
│   ├── network_logger.py       # Background ping logger (CSV → ~/Documents/NetSentinel/logs)
│   ├── nl_query.py             # Natural language query parser for device and event search
│   ├── notification_channels.py    # Per-channel delivery functions (S20-3 split)
│   ├── notification_router.py
│   ├── os_fingerprint.py
│   ├── plugin_registry.py      # Plugin discovery, metadata, enable/disable registry
│   ├── plugin_system.py        # Plugin loader and sandbox execution engine
│   ├── plugin_tools.py         # Plugin validator CLI + signature check (P3-1, P4-2, P4-3)
│   ├── nspkg.py                # .nspkg plugin bundle format — unpack_nspkg(), validate_manifest() (P3-5)
│   ├── port_scanner.py
│   ├── private_endpoint_checker.py  # RFC 1918 boundary exposure checker
│   ├── process_monitor.py      # Active process-to-socket correlation (psutil-based)
│   ├── protocol_animator.py    # AnimNode/AnimStep scene builders for protocol viz
│   ├── report_exporter.py      # Public API: save_*() entry points, JSON/CSV/NMap/card/lab
│   ├── report_isp.py           # ISP Accountability Report builder (S20-5 split)
│   ├── report_html.py          # HTML generation helpers — CSS, _badge, module HTML builders (S2-2 split)
│   ├── report_pdf.py           # PDF generation — weasyprint/headless-browser cascade (S2-2 split)
│   ├── report_scheduler.py     # Scheduled report generation and delivery logic
│   ├── rest_api.py             # Read-only Flask API (127.0.0.1, API key in keychain)
│   ├── risk_scorer.py
│   ├── rogue_device.py
│   ├── root_cause_correlator.py    # Prioritised plain-English findings from scan data
│   ├── scheduler.py
│   ├── settings_io.py          # QSettings export/import to/from JSON (SET-3)
│   ├── service_monitor.py      # Service heartbeat checker (TCP/HTTP/HTTPS probes)
│   ├── smb_enumerator.py       # SMB/Windows Share enumeration
│   ├── snmp_poller.py
│   ├── snmp_trap_receiver.py
│   ├── speed_tester.py         # 3-tier cascade public API (S20-7 split)
│   ├── speed_tester_backends.py  # Dataclasses + Ookla CLI + speedtest-cli + pure-Python backends (S20-7 split)
│   ├── storm_analyser.py
│   ├── stp_detector.py
│   ├── syn_scanner.py
│   ├── syslog_receiver.py      # UDP syslog message receiver and parser
│   ├── threat_intel.py
│   ├── tls_checker.py
│   ├── trend_analyser.py
│   ├── trigger_expression.py   # Trigger condition expression evaluator for automation hooks
│   ├── utils.py                # Core: get_app_data_dir(), is_admin(), ping_sweep, send_wol
│   ├── utils_net.py            # Network info: get_network_info(), get_dhcp_info(), get_interface_details() (S2-3 split)
│   ├── utils_platform.py       # IPv6 scanning: get_ipv6_devices(), ping_sweep_ipv6() (S2-3 split)
│   ├── web_dashboard.py        # build_html() — self-contained /dashboard HTML page
│   ├── wifi_heatmap.py         # WiFi signal IDW interpolation and heatmap data builder
│   ├── wifi_scanner.py         # 802.11 network enumeration (SSIDs, BSSIDs, signal levels)
│   └── zte_client.py           # ZTE MC889 5G modem API client (signal stats, cell info)
├── ui/
│   ├── styles.py               # SINGLE SOURCE OF TRUTH for all colours and QSS
│   ├── dashboard.py            # Main window shell (~1,967 lines; inherits ScanResultMixin, AppHeaderMixin, TabBuilderMixin, _NavBuilderMixin, _MonitorStateMixin, _PluginPageMixin)
│   ├── monitor_state.py        # _MonitorStateMixin — verdict/badge/pill display, KPI tiles, VerdictPanel, RiskBadge (Sprint 19)
│   ├── plugin_page_mixin.py    # _PluginPageMixin — plugin page lifecycle, HW auto-detect, scan launch (Sprint 19)
│   ├── nav/                    # Activity-rail navigation widget package
│   │   ├── __init__.py         # Re-exports from rail.py + builder.py
│   │   ├── rail.py             # _RailButton, _FlyoutPanel, _NavEntry and all nav widget classes
│   │   └── builder.py          # _NavBuilderMixin — all nav building/runtime/palette/pin methods (Sprint 19)
│   ├── command_palette.py      # Ctrl+K global fuzzy-search overlay
│   ├── empty_state.py          # EmptyStateOverlay — auto-shows/hides via model signals
│   ├── expanding_table.py      # ExpandingTable — inline master-detail row expansion
│   ├── first_run_dialog.py     # First-run setup wizard
│   ├── live_graph.py           # Matplotlib RTT line chart
│   ├── help.py                 # _PAGE_HELP dict — page help data for tip bar (Sprint 17: build_help_tab extracted to help_tab.py)
│   ├── help_tab.py             # build_help_tab() + _page_header() + _section/_entry/_subsection helpers (Sprint 17)
│   ├── npcap_banner.py         # Npcap install required banner (Store context)
│   ├── skeleton.py             # Skeleton loading placeholder (root-level variant)
│   ├── system_tray.py
│   ├── table_utils.py          # Shared table helpers (sort, copy, context menu)
│   ├── theme.py                # Theme application helpers
│   ├── topology_widget.py      # Matplotlib network topology map
│   ├── pages/
│   │   ├── automation_page.py      # Automation Hooks — event-to-action pipeline config
│   │   ├── baseline_page.py
│   │   ├── cert_page.py
│   │   ├── connections_page.py
│   │   ├── cve_page.py
│   │   ├── dhcp_lease_page.py
│   │   ├── diagnosis_page.py       # "What's Wrong?" DiagnosisPage — symptom tiles → scan → findings
│   │   ├── discover_page.py        # Feature Guide — filter bar + card widget (RULE-D2)
│   │   ├── discover_data.py        # _FEATURES list + _GROUPS_ORDER — pure data for FeatureGuidePage (Sprint 13)
│   │   ├── dns_zone_page.py
│   │   ├── geo_map_page.py         # Offline MaxMind geolocation map
│   │   ├── hardware_integration_page.py  # Hardware — USB/serial/GPIO device integration (Extend section)
│   │   ├── hardware_browse_mixin.py  # _HardwareBrowseMixin — community browse tab, catalog, and detection (S14-2 split)
│   │   ├── help_content.py         # _PAGE_HELP dict — page help data for tip bar (Sprint 13)
│   │   ├── history_page.py
│   │   ├── plugin_guide.py         # PluginGuide widget — collapsible 4-step plugin authoring guide (S14-2 split)
│   │   ├── plugin_wizard_mixin.py  # _PluginWizardMixin — "New Plugin" template wizard (S14-2 split)
│   │   ├── home_automation_page.py
│   │   ├── home_data_mixin.py      # _HomeDataMixin — all data handlers + public slots for HomePage (Sprint 15)
│   │   ├── home_page.py            # Landing page — hero, suggestions, tips, dashboard strip
│   │   ├── home_suggestions.py     # _HomeSuggestionsMixin — 'What to do next' strip logic (Sprint 13)
│   │   ├── inventory_page.py
│   │   ├── ip_calculator_page.py   # IP subnet calculator
│   │   ├── lab_mode_page.py        # LabModePage — guided exercises; inject_live_challenge()
│   │   ├── live_bandwidth_page.py
│   │   ├── log_hub_page.py         # Log Hub — unified chronological log (RTT, Modem, Mesh, Syslog, SNMP); emits live_challenge_detected
│   │   ├── log_source_panel.py     # _LogSourcePanelMixin — panel builders + source management for LogHubPage (S14-3b split)
│   │   ├── maintenance_page.py
│   │   ├── monitor_overview_page.py # Monitor Overview — aggregated view of all monitoring streams
│   │   ├── mqtt_page.py            # MQTT/Home Assistant — broker config, discovery payloads, test publish
│   │   ├── network_doc_page.py     # Network Doc — one-click HTML/Markdown snapshot
│   │   ├── notif_alert_history.py   # _NotifAlertHistoryMixin — alert history table + delivery/retry log + bulk actions (Sprint 17)
│   │   ├── notif_channel_panels.py  # _NotifChannelsMixin — email/toast/webhook/alert-rules card builders + test helpers (S14-3a)
│   │   ├── notif_extra_channels.py  # _NotifExtraChannelsMixin — Pushover/Ntfy/Telegram/Escalation/WeeklyDigest builders (Sprint 13)
│   │   ├── notifications_page.py
│   │   ├── ookla_cli_banner.py     # Dismissible install banner for Ookla CLI
│   │   ├── overview_page.py
│   │   ├── plugin_device_page.py   # Plugin Devices — plugin-provided virtual device pages
│   │   ├── protocol_viz_page.py    # Interactive ARP/DNS/TCP/DHCP/STP animation
│   │   ├── reports_page.py
│   │   ├── rest_api_page.py        # REST API — enable toggle, port, API key, live status probe, endpoint reference
│   │   ├── security_overview_page.py # Security Overview — aggregate security findings dashboard
│   │   ├── service_page.py
│   │   ├── settings_cards.py       # _SettingsCardsMixin — all settings card builders for SettingsPage; includes appearance/display cards (S14-3c)
│   │   ├── settings_appearance.py  # _SettingsAppearanceMixin — INCOMPLETE SPLIT: appearance card stubs (Sprint 13); not inherited by SettingsPage — appearance methods remain in settings_cards.py
│   │   ├── settings_page.py
│   │   ├── snmp_trap_page.py
│   │   ├── speed_test_page.py      # Speed Test — history rows store full modem signal dict; clicking a row restores signal panel
│   │   ├── syslog_page.py
│   │   ├── threat_intel_page.py
│   │   ├── timeline_page.py        # Timeline — chronological event log across all sources
│   │   ├── trend_page.py
│   │   ├── trigger_builder_page.py # Custom Triggers — expression builder for alerting conditions
│   │   ├── uptime_page.py
│   │   ├── wifi_heatmap_page.py    # Floor plan import + IDW interpolation + PNG export
│   │   └── wifi_monitor_page.py    # 802.11 Monitor — passive frame capture (Npcap; admin required)
│   ├── header.py               # AppHeaderMixin — header construction + frameless-window behaviour (S13-3 split)
│   ├── scan_wiring.py          # ScanResultMixin — scan result handlers (extracted from dashboard.py)
│   ├── scan_enrichment.py      # ScanEnrichmentMixin — mesh + hardware plugin enrichment handlers (Sprint 13)
│   ├── tabs.py                 # TabBuilderMixin — page factory and sidebar assembly; inherits all _*TabsMixin sub-mixins (Sprint 6)
│   ├── tabs_helpers.py         # Shared UI utility functions for tab builders; re-exported via tabs.py (Sprint 8)
│   ├── tabs_scan.py            # _ScanTabsMixin — scan result tab content builders M1–M5 (Sprint 8 split)
│   ├── tabs_network.py         # _NetworkTabsMixin — network configuration tab builder (Sprint 8 split)
│   ├── tabs_diag.py            # _DiagTabsMixin — diagnostics tab builder; inherits _DiagExtraTabsMixin + _LoggerTabMixin (Sprint 8 split)
│   ├── tabs_recon.py           # _ReconTabsMixin — security-audit recon tab builders (Sprint 18 split)
│   ├── tabs_analysis.py        # _AnalysisTabsMixin — IPv6/Cloud/Correlator/IoT/Benchmark tab builders (Sprint 13)
│   ├── tabs_diag_extra.py      # _DiagExtraTabsMixin — MTR tab + advanced tools tab + handlers (Sprint 13)
│   ├── tabs_logger.py          # _LoggerTabMixin — network logger tab builder + handlers + retention helpers (Sprint 15)
│   └── widgets/
│       ├── alert_drawer.py         # Slide-in alert detail drawer
│       ├── animated_kpi.py         # Animated KPI counter with ease-out count-up
│       ├── coach_mark.py           # Guided coach mark overlay for first-run hints
│       ├── context_menu.py         # Reusable right-click context menu builder
│       ├── density_toggle.py       # Compact/comfortable row density toggle widget
│       ├── device_popover.py       # Hover popover showing quick device info
│       ├── empty_state_card.py     # EmptyStateCard — reusable empty state with icon, what/why copy, and CTA button (Sprint A2)
│       ├── explainer_panel.py      # Reusable inline explanation panel (Lab Mode, Protocol Viz)
│       ├── home_widgets.py         # _GradeRing, _MiniSparkline, _GradeSparkline, _EventsTicker, grade history helpers, _MiniCard, _AlertRow
│       ├── home_session_widgets.py # FreshnessStrip, GettingStartedCard, _GradeBreakdownDialog, StandardWelcomePage, ProWelcomePage (Sprint 17)
│       ├── credential_dialog.py    # show_credential_dialog() + show_unsigned_warning() — standalone plugin credential dialogs (S14-2 split)
│       ├── device_detail_pane.py   # _DeviceLabelDialog, _DeviceDrawer, _ScanCompareDialog — InventoryPage helper dialogs (Sprint 13)
│       ├── device_detail_panels.py # _ModemDetailPanel, _RouterDetailPanel — hardware detail panels (Sprint 13 split)
│       ├── hub_card.py             # HubCard, PipInstallDialog and all plugin helpers
│       ├── hub_helpers.py          # Pure data-persistence and utility helpers extracted from hub_card.py (no widget logic)
│       ├── jargon_tooltip.py       # JargonTooltip — underlined QLabel with hover definition from glossary.json (Sprint A4)
│       ├── kpi_bar.py              # _KpiBarMixin — four KPI tiles for the Devices page (Sprint 13 split)
│       ├── objective_badge.py      # ObjectiveBadge — compact exam-objective pill badge (N+/CCNA/Sec+) for Lab Mode and Protocol Viz (Sprint B3)
│       ├── modem_signal_panel.py   # _ModemSignalPanelMixin — modem signal panel builder/updater for SpeedTestPage (Sprint 13)
│       ├── overview_tile.py        # Core tile classes (_BaseTile subclasses), _TILE_CLASSES/_DEFAULT_ORDER
│       ├── overview_tile_monitor.py # Monitoring-domain tiles: LiveBandwidth, DnsStability, ModemSignal, TopTalkers, RecentEvents, TrendStatus (Sprint 13)
│       ├── page_header.py          # Standard page header with title, help button, actions bar
│       ├── protocol_canvas.py      # QPainter animation engine for protocol diagrams
│       ├── pulsing_dot.py          # Animated status indicator dot (live/offline)
│       ├── scan_summary_sheet.py   # Bottom sheet showing scan summary stats
│       ├── signal_bar.py           # 5-bar phone-style signal-strength indicator (POLISH-12)
│       ├── skeleton.py             # Skeleton loading placeholder rows (widget variant)
│       └── toast.py                # Non-blocking toast notification widget
├── workers/                    # QThread wrappers (signals only, no logic)
│   ├── availability_worker.py
│   ├── cert_worker.py
│   ├── dhcp_lease_worker.py
│   ├── diagnosis_worker.py     # DiagnosisWorker — sequences symptom scans for What's Wrong?
│   ├── dns_zone_worker.py
│   ├── ha_worker.py
│   ├── hw_detect_worker.py     # HwDetectWorker — scans for connected hardware integration devices
│   ├── iface_bw_worker.py
│   ├── plugin_polling_worker.py  # PluginPollingWorker — periodic data fetch for polling-type plugins
│   ├── plugin_worker.py        # PluginWorker — event-driven execution runner for active plugins
│   ├── process_worker.py       # ProcessWorker — snapshots process-to-socket map via psutil
│   ├── report_scheduler_worker.py
│   ├── rest_api_worker.py
│   ├── scan_worker.py
│   ├── service_worker.py
│   ├── snmp_trap_worker.py
│   ├── speed_test_worker.py    # FetchServersWorker + SpeedTestWorker
│   ├── syslog_worker.py
│   ├── threat_intel_worker.py
│   └── wifi_monitor_worker.py  # WifiMonitorWorker — passive 802.11 capture thread (Npcap)
└── tests/
```

## Key Architectural Patterns

### Three-layer separation (ARCH RULE 1)

```
UI LAYER       ui/dashboard.py (shell/router), ui/pages/*.py (page widgets)
               • Reads from MetricStore for display
               • NEVER writes to MetricStore directly
               • NEVER imports from modules/alert_engine.py

DATA LAYER     modules/metric_store.py  ←→  NetSentinel.db (AppData)
               • Single source of truth for all persisted metrics

MODULE LAYER   modules/*.py
               • Pure business logic — NO PyQt imports, NO direct DB writes
```

### File write locations (ARCH RULE 23)
All file writes must use `get_app_data_dir()` from `modules/utils.py`:
- Windows: `%LOCALAPPDATA%\NetSentinel\`
- macOS: `~/Library/Application Support/NetSentinel/`
- Linux: `$XDG_CONFIG_HOME/NetSentinel/`

The exe directory is **read-only** when installed via WinGet or Inno Setup into `Program Files`.
The only exception is `network_logger.py` which writes CSVs to `~/Documents/NetSentinel/logs/` by design (user-accessible log files).

### MetricStore singleton (ARCH RULE 2)
`MetricStore` is instantiated **once** in `app.py` or `svc.py` and injected as a dependency.
Never construct it inside a page widget or module.

### Speed tester cascade (ARCH RULE 24)
`modules/speed_tester.py` tries backends in order:
1. **Ookla CLI binary** — `_find_ookla_cli()` searches 7 locations including WinGet Links dir
2. **speedtest-cli library** — 8 download / 4 upload threads; SSL-patched for Python 3.12
3. **Pure-Python HTTP** — 16 download / 8 upload `ThreadPoolExecutor` TCP streams

Frontend (`SpeedTestResult` dataclass) is identical regardless of backend.

### Dashboard navigation model
Main window: permanent 48 px activity rail (`_nav_rail`) + 280 px animated flyout (`_FlyoutPanel`) + `QStackedWidget` (`_stack`).

- **Sections** declared with `_nav_begin_section(name, lucide_icon_name)` inside `_build_pro_nav()`
- **Pages** registered with `_nav_add_rail_item(label, widget, admin_required, audit_item)`
- `_nav_finalize_rail()` builds `_RailButton` widgets from `_nav_sections` and inserts them into the rail layout
- `_nav_rail_toggle(section_name)` opens/closes the flyout for a section; persists last-open section to `QSettings("nav/last_section")`
- `_nav_rail_go_to(label)` switches the stack and updates the breadcrumb strip
- If `_nav_pinned_labels` is non-empty, a "Pinned" section is injected at index 0 of `_nav_sections` before `_nav_finalize_rail()`
- Ctrl+F focuses the sidebar search box; Ctrl+K opens the command palette; Esc closes the flyout

### Rail icon standard
Rail section buttons use **Lucide SVG icons** (MIT) defined in the `_LUCIDE` dict in `dashboard.py`. Available names: `home activity grid monitor shield bar-chart book-open settings search wifi network zap server map-pin terminal layers globe log alert-triangle eye pin x chevron-right scan lock tool bell cpu plug`.

Add new icons to `_LUCIDE` before using them in `_nav_begin_section()`. Do not use Unicode symbols or photo-emoji as rail section icons.

**Nav section placement guide** (use the correct section when adding new pages):
- Getting Started — daily-use core tools (Overview, Speed Test, DNS, Home, What's Wrong?)
- Discover — network inventory and topology (Devices, Network Map, WiFi, DHCP, Home Automation)
- Monitor — live data and history streams (Log Hub, Bandwidth, Connections, Availability, Service Heartbeat)
- Reports — grading, ISP reports, docs, notifications (Network Grade, Health Report, Network Doc, IP Calculator, Notifications)
- Analysis — deep packet / protocol tools, advanced diagnostics (Broadcast Storm, STP, IoT, Monitor Overview, 802.11 Monitor, ARP Watch, Trace, SNMP, Tools, Geo, Trends)
- Automation — scheduled scans, hooks, MQTT, REST API, integrations (Automation Hooks, Scheduled Scans, Custom Triggers, MQTT, REST API, Config Snapshots, Maintenance Windows)
- Security Audit — RED-labelled; elevated-privilege scan tools (Security Overview, Port Scan, CVE, Threat Intel, TLS, Login Test, OS Detection, Risk Score, Exposure, Discovery, SMB, Plugins, Private Endpoint, Cloud Metadata, DHCP Rogue)
- Education — learning tools (Protocol Visualizer, Lab Mode, Feature Guide, Help)
- Extend — hardware integrations and physical device management (Hardware)

### Scan workers
All network operations run in `workers/` (QThread subclasses). Emit `result_ready` and `error` signals. **Never** do blocking I/O on the main thread.

### Risk levels — two separate systems

**Internal scan risk scoring** (used in scan results, `RISK_COLORS`/`RISK_BG` in `ui/styles.py`):
`HIGH` > `STORM` > `MEDIUM` > `WARNING` > `LOW` > `CLEAN` > `UNKNOWN`

**UI severity labels** (used in alert displays, CVE pages, RULE-A3):
`Critical` > `High` > `Warning` > `Info`

These are distinct systems that coexist. Do not mix them — never display internal risk level strings like "STORM" or "CLEAN" to users as severity labels, and do not use UI severity labels (e.g. "Critical") as internal risk level values in RISK_COLORS lookups.

## Colour Palette (ui/styles.py constants)

```python
NAV_BAR     = "#141B2D"   # top application bar
SIDEBAR_BG  = "#1F2B3E"   # left sidebar
BG_DARK     = "#F4F4F4"   # main content area
BG_CARD     = "#FFFFFF"   # card backgrounds
BG_HOVER    = "#EEF4FF"   # table row hover
BG_ALT_ROW  = "#F7F9FC"   # zebra alternate row
ACCENT      = "#0078D4"   # primary brand blue
TH_BG       = "#1A3A5C"   # table header navy
TH_TEXT     = "#FFFFFF"
TEXT_PRIMARY   = "#1A1A2E"
TEXT_SECONDARY = "#5A6A7A"
BORDER      = "#D4D4D4"
RED    = "#D93025"
AMBER  = "#F59E0B"
GREEN  = "#2E7D32"
```

## WinGet Distribution

`Ookla.Speedtest.CLI` is declared as `ExternalDependencies` (NOT `PackageDependencies`) in all winget manifests.
See RULE-R3: using `PackageDependencies` blocks the install when the package is not in the official winget index.
The Inno Setup installer has an optional task that runs `winget install Ookla.Speedtest.CLI --silent`.
`OoklaCliBanner` in `ui/pages/ookla_cli_banner.py` handles in-app one-click install for portable users.

**Never bundle `speedtest.exe` inside the installer** — it has a proprietary Ookla EULA.
