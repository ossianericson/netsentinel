---
applyTo: "**"
description: "NetSentinel project vision, strategic goals, implemented features (v1.9.94), and core product values."
---

# NetSentinel — Project Vision & Purpose

## Strategic Goals

NetSentinel has two parallel strategic goals:

1. **De-facto home network standard** — become the first tool recommended when anyone says "my network is broken". The tool must show what is happening on the real network, in plain English, without requiring the user to already know what STP, ARP, or DNS are.

2. **Educational standard** — become the natural starting point for anyone learning how networks actually work. Every feature should produce output that maps directly to a textbook concept or exam objective and can be submitted as evidence of work.

Both goals are served by the same core property: zero prior knowledge required.

---

## What This Product Is

NetSentinel is a **professional-grade network security scanner and monitor** for Windows, macOS, and Linux. It is a desktop GUI application (PyQt6) targeting IT administrators, network engineers, security-aware home lab users, and students/educators who need an enterprise-quality tool — not a toy.

Current version: **v2.1.10**

**Production status: Microsoft Store ready.** A 9-hour overnight chaos run (June 2026) completed 10,001 UIA interactions across mild / moderate / wild chaos levels (seeds 1, 42, 99). Result: zero application crashes, all 62 pages functional before and after (confirmed by identical systematic pre/post runs). The app is considered production-stable for Microsoft Store submission.

Version history (condensed): v1.9.40 → v1.9.54 (plugin ecosystem + robustness sprints) → v1.9.55–v1.9.60 (test-suite stability, module splits, MetricStore health) → v1.9.61–v1.9.62 (dashboard decomposition: tabs, help, header, settings, page splits) → v1.9.63–v1.9.64 (hex-colour purge, module test coverage, spec integrity) → v1.9.65 (home/hardware/notif/log/settings page splits, tabs sub-mixins) → v1.9.66 (Sprint 16–19: nav/monitor/plugin mixins, dashboard.py 13,483→1,967 lines — dashboard decomposition complete) → v1.9.67–v1.9.90 (CodeQL hardening, 2,000+ test suite, chaos/monkey harness, guided tour, onboarding rewrite — **Microsoft Store ready**) → v1.9.91–v1.9.94 (QTimer crash fixes, test suite stabilised to 3,099 tests, APM rules hardened, cross-feature discoverability improvements — feature set complete) → v2.0.0 (Sprint 1–4: device identification improvements, async OUI enrichment, service mapper engine, service connectivity diagnostics engine + probes, Service Diagnostics page) → v2.1.0 (Sprint 5: What's Wrong? service-unreachable tile; Service Heartbeat Diagnose → action; vendor/type enrichment on first scan; probe and enrichment fixes) → v2.1.2 (Sprint 4: network segment/zone grouping — device inventory grouped into colour-coded /24 subnets with pill filter bar and right-click editor; MetricStore schema v11)

**Development phase:** The feature set is complete as of v2.1.0. All future development is **polish and user-requested changes only** — UX refinements, documentation accuracy, cross-feature discoverability glue, and bug fixes. No new features should be added without an explicit user request.

---

## Implemented Features (as of v2.1.2)

### Core Scanning & Detection
- **Layer 2 rogue device detection** — ARP scanning, MAC/OUI classification, rogue bridge (STP) detection
- **Broadcast storm analysis** — real-time packet capture and storm level measurement
- **WiFi network enumeration** — rogue SSIDs, co-channel interference
- **DNS & connectivity monitoring** — latency graphing, outage detection, DNS leak testing
- **Active security audit** — SYN/UDP port scanning, OS fingerprinting, CVE lookup, credential testing (requires admin)
- **Background network logging** — continuous ping/RTT/jitter/DNS logging with file rotation
- **Network topology visualisation** — live matplotlib graph showing device relationships
- **IoT behaviour baselining** — detect devices going outside their normal behaviour
- **Internet speed test** — Ookla CLI (1 Gbps+) → speedtest-cli (8 threads) → pure-Python (16 TCP streams)
- **SMB/Windows Share enumeration** — `modules/smb_enumerator.py`; discovers exposed shares
- **Private endpoint exposure checker** — `modules/private_endpoint_checker.py`; RFC 1918 boundary tests
- **Cloud metadata probe** — `modules/cloud_metadata.py`; detects AWS/Azure/GCP IMDS exposure
- **Device identification improvements** — async OUI vendor lookup for Unknown devices; vendor/type enrichment populates on first scan without requiring a re-scan (`modules/device_classifier.py`, `ui/scan_enrichment.py`)
- **Service mapper** — `modules/service_mapper.py`; maps device_type/vendor to a list of relevant `ServiceInfo` objects (hostname, display name, protocol, expected port); feeds Service Diagnostics and Service Heartbeat
- **Network segment/zone grouping** — devices automatically grouped into colour-coded /24 subnets; pill filter bar above the Devices table with multi-select; user-editable segment names and colours via right-click editor; stored user-defined segments win over auto-detected ones on CIDR conflict (`modules/network_segments.py`, schema v11)
- **Persistent device map** — after each live scan, pinned and static-candidate devices (infrastructure roles, IP-stable devices seen 3+ times) that were not in the scan are appended to the Inventory snapshot with freshness states: `pinned` (always shown), `cached` (<24 h), or `stale` (<7 d); implemented in `ScanResultMixin._merge_scan_with_persistent()` in `ui/scan_wiring.py`
- **"Hide offline" Inventory filter** — toggle button in the Current Devices card header hides `cached`/`stale` rows without losing the persistent map; state is not persisted (resets on each navigation); implemented in `InventoryPage._on_hide_offline_toggled()` + `_apply_segment_filter()`

### Monitoring & Alerting
- **Network Logger** — unified chronological monitor combining Network RTT, 5G Modem, Mesh, Syslog, and SNMP Traps; source toggle bar; per-source intervals; emits `live_challenge_detected` → Lab Mode
- **Active Connections** — process-to-socket map with firewall block/unblock
- **Live Bandwidth** — 60-second rolling per-interface chart
- **Threat Intelligence** — ThreatIntelDB, AbuseIPDB v2 lookup (consent-gated)
- **DHCP Lease Inventory** — rogue DHCP server detection
- **DNS Zone Mapping** — AXFR + mDNS
- **CVE lifecycle tracker** — per-device CVE tracking with metric_store schema v8
- **Alert pipeline** — AlertEngine + NotificationRouter with Toast/Webhook/Email/Pushover/Ntfy/Telegram channels
- **Maintenance windows** — alert suppression per device or fleet-wide
- **Predictive trend alerting** — OLS regression over RTT/loss/jitter with ETA-to-threshold
- **Modem Signal Monitor** — ZTE MC889 5G modem signal stats (SINR, RSRP, band, cell ID); `modem_page.py`
- **Mesh Router Monitor** — TP-Link Deco XE75 node signal stats and topology; `mesh_router_page.py`
- **802.11 Monitor Mode** — passive frame capture via Npcap; `wifi_monitor_page.py`; requires admin
- **Monitor Overview** — aggregated dashboard across all monitoring streams; `monitor_overview_page.py`
- **Timeline** — chronological event log across all monitoring sources; `timeline_page.py`
- **Service Diagnostics** — `ui/pages/service_diagnostics_page.py`; on-demand DNS/TCP/HTTPS/ICMP/traceroute probes for streaming and gaming services; failure-layer classification (device → local_network → dns → isp → routing → remote_outage); backed by `modules/service_diagnostics.py`, `modules/service_diagnostics_probes.py`, `workers/service_diagnostics_worker.py` (Sprints 3–4, Monitor section)

### Navigation & UI
- **VSCode-style activity rail navigation** — permanent 48 px icon rail + 280 px animated flyout; 9 sections; full feature set always visible; last-open section restored via QSettings; mode switcher removed
- **Rail icon labels** — 9 px section name drawn below each rail icon (58 px button height); sections legible without hovering
- **Persistent search button** — magnifier at the top of the rail, always visible; opens Ctrl+K on click
- **Breadcrumb strip** — `"Section  ›  Page"` label above the content area; updated on every navigation
- **Pinned section** — right-click any flyout item to pin it; a "Pinned" rail section appears immediately at the top of the rail; persists via QSettings
- **Command palette (Ctrl+K)** — fuzzy-match any page or action; non-modal (click anywhere to dismiss); arrow keys + Enter; Esc to close
- **Sidebar search (Ctrl+F)** — focuses sidebar search from anywhere in the app
- **Page help popover (?)** — floating 300px panel anchored below the ? button; screen-edge clamped so it never renders off-screen
- **Lucide SVG rail section icons** — RULE 25; clean scalable SVG at any size
- **Three colour themes** — Arctic Clean, Midnight Pro, Obsidian Neon; all values in `ui/styles.py`
- **Configurable Overview tile dashboard** — drag to reorder, layout persists
- **Skeleton loading rows** — `ui/widgets/skeleton.py`; placeholder rows while scan workers run
- **Feature Guide** — `discover_page.py`; 83 feature entries across 9 groups with filter bar and Open buttons

### Home Page
- **"Since you were last here" banner** — new devices and outages since last session
- **"What to do next" suggestions strip** — up to four colour-coded action cards after each scan
- **Weekly digest tray notification** — 7-day summary on startup if 7+ days elapsed
- **Dismissible browser dashboard strip** — shown when REST API is enabled; links to `/dashboard`
- **Dismissible Quick Tips card** — Ctrl+K, right-click pin, right-click device rows, REST API hint

### Diagnosis & Root Cause
- **One-click "What's Wrong?" diagnosis** — `DiagnosisPage`; symptom tiles → sequenced scan → plain-English findings; tiles: slow internet, dropping connection, no connection, **a service is unreachable** (new — selects service via combobox, routes finding to Service Diagnostics); accessible from Home page button and Ctrl+K
- **Service Heartbeat Diagnose action** — "Diagnose →" right-click/context action on any monitored service in `service_page.py`; emits `diagnose_service` signal → navigates to Service Diagnostics pre-loaded for that service
- **Root Cause Correlator** — `modules/root_cause_correlator.py`; prioritised findings and global verdict
- **Health Check** — on-demand ping, DNS speed test, traceroute, HTTP check, DNS leak test

### Data & Reporting
- **PDF report export** — `save_pdf_report()`
- **Config baseline snapshots and diff viewer** — structured diff: added/removed/changed devices
- **REST API** — standalone page (`rest_api_page.py`); read-only Flask, 127.0.0.1 default, OS-keychain API key; live status probe; endpoint reference
- **Browser dashboard** — self-contained dark HTML page at `/dashboard`; auto-refreshes every 30 s
- **Wi-Fi signal-strength heatmap** — floor plan import, per-BSSID IDW interpolation, PNG export
- **Geolocation map** — offline MaxMind GeoLite2-City, no API key, no external calls
- **Network documentation generator** — one-click HTML/Markdown snapshot; `network_doc_page.py`
- **Shareable diagnostic card** — PNG/HTML export: grade circle, ISP, top 3 findings, attribution
- **MQTT / Home Assistant publisher** — Discovery payloads, configurable broker, OS keychain credentials; `mqtt_page.py`
- **Speed Test modem signal snapshot** — each test saves 20 modem signal fields to DB; clicking history row restores signal panel

### Automation
- **Automation Hooks** — event-to-action pipeline; shell command hooks on alert/scan events; `automation_page.py`
- **Custom Triggers** — expression builder for alerting conditions; `trigger_builder_page.py`, `modules/trigger_expression.py`
- **Scheduled Reports** — `report_scheduler_worker.py`; configurable delivery schedule

### Security Audit (requires admin or Npcap)
- **Security Overview** — aggregate security findings dashboard with grade; `security_overview_page.py`
- **Full Device Discovery** — comprehensive multi-method device enumeration
- **Login Test** — credentialed scan (SSH, SMB, FTP, Telnet); `modules/credentialed_scan.py`
- **Natural language device search** — `modules/nl_query.py`

### Education
- **Interactive protocol visualizer** — animated ARP/DNS/TCP/DHCP/STP diagrams using real scan data (`ui/pages/protocol_viz_page.py`, `modules/protocol_animator.py`)
- **Lab / scenario mode** — guided exercises with hints, solution reveals, exportable HTML results; live challenges injected from Network Logger events (`ui/pages/lab_mode_page.py`, `modules/lab_scenarios.py`)
- **Contextual explainer panel** — `ui/widgets/explainer_panel.py`; collapsible plain-English panel on detection pages

### Security & Plumbing
- **AppData path hardening** — `get_app_data_dir()` prevents PermissionError in `C:\Program Files\`
- **OS keychain for all secrets** — SMTP, SNMP, API keys via `keyring`; never QSettings
- **Winget E_ABORT fix** — three-layer defence for Ookla CLI install edge cases
- **Plugin system** — drop Python scripts into `plugins/`; `plugin_system.py` + `plugin_registry.py`; exposed via Security Audit sidebar
- **Hardware integration** — USB/serial/GPIO device detection; `hardware_integration_page.py` in Extend section
- **Hardware plugin ecosystem (v1.9.45–v1.9.47)**
  - Multi-instance support — same plugin type, different device IPs, each with its own keyring credential and Hub card
  - Per-plugin health tracking — success/error counters, circuit-breaker (auto-disable after 10 errors), degraded amber state after 24 h without success
  - Structured error classification — AUTH / DEPS / NET / TIMEOUT prefixes; `_classify_error()` routes to appropriate remediation text
  - Blocking live-test before registration — credential dialog runs get_info()+get_status() in background thread; only saves on success
  - Startup dep smoke-check — missing PYPI_PACKAGE dependencies surface as card errors immediately at startup
  - Plugin log console — "≡ Logs" toggle on each Hub card shows last 100 structured poll log lines (P3-3)
  - Unsigned plugin warning — one-time SHA-256-keyed consent dialog for non-bundled scripts (P4-1)
  - Plugin validator CLI — `python -m modules.plugin_tools validate <plugin.py>` performs static analysis (P3-1)
  - Plugin template wizard — "⬡ New Plugin" button in Hardware Hub generates a filled-in .py template (P3-2)
  - Plugin icon support — `icon.png` alongside script or `ICON_PATH` constant displayed as 24×24 on Hub cards (P2-3)
  - Bundled plugin signing — `data/plugin_hashes.json` SHA-256 hash list; tampered files blocked at load time (P4-2)
  - Restricted import advisory — `validate_plugin()` warns when imports fall outside `_DEFAULT_SAFE_IMPORTS` (P4-3)

---

## Target Users

- **IT administrators** managing SMB/enterprise networks
- **Security engineers** doing periodic audits
- **Home lab enthusiasts** who want a real tool, not a script
- **Students and educators** using the tool in networking courses (CompTIA Network+, CCNA lab contexts)
- **Non-technical home users** who need actionable answers without needing to understand the underlying protocols

---

## Core Product Values

1. **Information density over decoration** — every pixel of screen space must carry useful data
2. **Professional, not playful** — the UI should feel like an enterprise monitoring tool, not a gaming dashboard
3. **Actionable output** — every scan result must include a clear severity indicator and remediation path
4. **Zero unnecessary friction** — one click to run, right-click to act, keyboard shortcuts everywhere
5. **Least privilege** — all file writes go to `%LOCALAPPDATA%\NetSentinel\` via `get_app_data_dir()`; no writes to the exe directory or `Program Files`
6. **Plain English first** — technical detail is always available, but never the only presentation

---

## Non-Goals

- Do not add new features without an explicit user request — the feature set is complete; focus is polish, discoverability, and cross-feature cohesion
- Do not add consumer-style gamification (glow effects, neon colours, oversized animations)
- Do not abstract away technical detail — show MAC addresses, full IP ranges, exact RTTs
- Do not add cloud sync, accounts, or telemetry without explicit opt-in
- Do not bundle third-party binaries with their own licences (Ookla CLI, Npcap)
- Do not use photo-emoji in the sidebar — use Lucide SVG for rail section icons (RULE-25) and geometric Unicode for flyout item icons (RULE-I4)
