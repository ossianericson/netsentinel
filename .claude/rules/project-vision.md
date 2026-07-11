---
paths:
  - "**"
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

Current version: **v2.1.28**

**Production status: Microsoft Store ready.** A 9-hour overnight chaos run (June 2026) completed 10,001 UIA interactions across mild / moderate / wild chaos levels (seeds 1, 42, 99). Result: zero application crashes, all 62 pages functional before and after (confirmed by identical systematic pre/post runs). The app is considered production-stable for Microsoft Store submission.

The full version history lives in `CHANGELOG.md` (and the highlights in
`README.md`). It is not duplicated here — a per-version chain in this file only
rots out of date. The app reached feature-complete at v2.1.0; everything since is
polish, discoverability, and bug fixes.

**Development phase:** The feature set is complete as of v2.1.0. All future development is **polish and user-requested changes only** — UX refinements, documentation accuracy, cross-feature discoverability glue, and bug fixes. No new features should be added without an explicit user request.

---

## Implemented Features

One line per feature — full behavioural detail lives in the module's own docstring, not here.

### Core Scanning & Detection
- **Layer 2 rogue device detection** — ARP scanning, MAC/OUI classification, rogue bridge (STP) detection
- **Broadcast storm analysis** — real-time packet capture and storm level measurement
- **WiFi network enumeration** — rogue SSIDs, co-channel interference
- **DNS & connectivity monitoring** — latency graphing, outage detection, DNS leak testing
- **Active security audit** — SYN/UDP port scanning, OS fingerprinting, CVE lookup, credential testing (admin)
- **Background network logging** — continuous ping/RTT/jitter/DNS logging with file rotation
- **Network topology visualisation** — live matplotlib graph of device relationships
- **IoT behaviour baselining** — detects devices going outside their normal behaviour
- **Internet speed test** — Ookla CLI → speedtest-cli → pure-Python cascade (`modules/speed_tester.py`)
- **SMB/Windows Share enumeration** — discovers exposed shares (`modules/smb_enumerator.py`)
- **Private endpoint exposure checker** — RFC 1918 boundary tests (`modules/private_endpoint_checker.py`)
- **Cloud metadata probe** — detects AWS/Azure/GCP IMDS exposure (`modules/cloud_metadata.py`)
- **Device identification** — async OUI vendor lookup and enrichment on first scan (`modules/device_classifier.py`)
- **Service mapper** — maps device type/vendor to relevant monitored services (`modules/service_mapper.py`)
- **Network segment/zone grouping** — colour-coded /24 subnets with user-editable names (`modules/network_segments.py`)
- **Persistent device map** — pinned/cached/stale freshness states carried across scans (`ui/scan_wiring.py`)
- **"Hide offline" Inventory filter** — hides cached/stale rows without losing the persistent map

### Monitoring & Alerting
- **Network Logger** — unified chronological monitor across RTT/modem/mesh/syslog/SNMP sources
- **Active Connections** — process-to-socket map with firewall block/unblock
- **Live Bandwidth** — 60-second rolling per-interface chart
- **Threat Intelligence** — ThreatIntelDB + AbuseIPDB v2 lookup (consent-gated)
- **DHCP Lease Inventory** — rogue DHCP server detection
- **DNS Zone Mapping** — AXFR + mDNS
- **CVE lifecycle tracker** — per-device CVE tracking (schema v8)
- **Alert pipeline** — AlertEngine + NotificationRouter across Toast/Webhook/Email/Pushover/Ntfy/Telegram
- **Maintenance windows** — alert suppression per device or fleet-wide
- **Predictive trend alerting** — OLS regression over RTT/loss/jitter with ETA-to-threshold
- **Modem Signal Monitor** — 5G modem signal stats (`ui/pages/modem_page.py`)
- **Mesh Router Monitor** — mesh node signal stats and topology (`ui/pages/mesh_router_page.py`)
- **802.11 Monitor Mode** — passive frame capture via Npcap, admin required (`ui/pages/wifi_monitor_page.py`)
- **Monitor Overview** — aggregated dashboard across monitoring streams (`ui/pages/monitor_overview_page.py`)
- **Timeline** — chronological event log across monitoring sources (`ui/pages/timeline_page.py`)
- **Service Diagnostics** — on-demand DNS/TCP/HTTPS/ICMP/traceroute probes with failure-layer classification (`modules/service_diagnostics.py`)

### Navigation & UI
- **VSCode-style activity rail navigation** — 48 px icon rail + 280 px animated flyout, 9 sections
- **Rail icon labels** — section name drawn below each rail icon
- **Persistent search button** — opens Ctrl+K from the rail
- **Breadcrumb strip** — "Section › Page" label above the content area
- **Pinned section** — right-click any flyout item to pin; persists via QSettings
- **Command palette (Ctrl+K)** — fuzzy-match any page or action
- **Sidebar search (Ctrl+F)** — focuses sidebar search from anywhere in the app
- **Page help popover (?)** — floating panel anchored below the ? button
- **Lucide SVG rail section icons** — clean scalable SVG at any size (RULE 25)
- **Two colour themes** — Arctic Clean (light, cool-slate chrome with deep-indigo table headers) and Midnight Pro (dark, bright royal-blue accent) (`ui/styles.py`)
- **Configurable Overview tile dashboard** — drag to reorder, layout persists
- **Skeleton loading rows** — placeholder rows while scan workers run (`ui/widgets/skeleton.py`)
- **Feature Guide** — filterable index of feature entries with Open buttons (`ui/pages/discover_page.py`)
- **Scan Registry / flyout dot badges** — per-page scan state drives flyout and rail badges (`_NavBuilderMixin`)
- **_ScanStatusTile** — Overview tile showing live scan state for all Security Audit tools
- **Last run chips** — "Last run: N ago" chip on Speed Test and DNS Zone pages

### Home Page
- **"Since you were last here" banner** — new devices and outages since last session
- **"What to do next" suggestions strip** — up to four action cards after each scan
- **Weekly digest tray notification** — 7-day summary on startup
- **Dismissible browser dashboard strip** — shown when REST API is enabled
- **Dismissible Quick Tips card** — Ctrl+K, right-click pin, REST API hint
- **Scan Center card** — always-visible 5-row card with per-row state dot and action button

### Diagnosis & Root Cause
- **One-click "What's Wrong?" diagnosis** — symptom tiles → sequenced scan → plain-English findings (`ui/pages/diagnosis_page.py`)
- **Service Heartbeat Diagnose action** — right-click action routes to Service Diagnostics (`ui/pages/service_page.py`)
- **Root Cause Correlator** — prioritised findings and global verdict (`modules/root_cause_correlator.py`)
- **Health Check** — on-demand ping, DNS speed test, traceroute, HTTP check, DNS leak test

### Data & Reporting
- **PDF report export** — `save_pdf_report()`
- **Config baseline snapshots and diff viewer** — structured added/removed/changed device diff
- **REST API** — read-only Flask API, OS-keychain key (`ui/pages/rest_api_page.py`)
- **Browser dashboard** — self-contained dark HTML page at `/dashboard`, auto-refreshes
- **Wi-Fi signal-strength heatmap** — floor plan import, per-BSSID IDW interpolation
- **Geolocation map** — offline MaxMind GeoLite2-City, no API key
- **Network documentation generator** — one-click HTML/Markdown snapshot (`ui/pages/network_doc_page.py`)
- **Shareable diagnostic card** — PNG/HTML export with grade, ISP, top findings
- **MQTT / Home Assistant publisher** — Discovery payloads, OS keychain credentials (`ui/pages/mqtt_page.py`)
- **Speed Test modem signal snapshot** — saves 20 modem signal fields per test

### Automation
- **Automation Hooks** — event-to-action shell command pipeline (`ui/pages/automation_page.py`)
- **Custom Triggers** — expression builder for alerting conditions (`modules/trigger_expression.py`)
- **Scheduled Reports** — configurable delivery schedule (`workers/report_scheduler_worker.py`)

### Security Audit (requires admin or Npcap)
- **Security Overview** — aggregate security findings dashboard with grade and Scan Status card (`ui/pages/security_overview_page.py`)
- **Full Device Discovery** — comprehensive multi-method device enumeration
- **Login Test** — credentialed scan (SSH, SMB, FTP, Telnet) (`modules/credentialed_scan.py`)
- **Natural language device search** — (`modules/nl_query.py`)

### Education
- **Interactive protocol visualizer** — 10-protocol animated diagrams using real scan data (`ui/pages/protocol_viz_page.py`)
- **Lab / scenario mode** — guided exercises with live challenges from Network Logger events (`ui/pages/lab_mode_page.py`)
- **Contextual explainer panel** — collapsible plain-English panel on detection pages (`ui/widgets/explainer_panel.py`)

### Security & Plumbing
- **AppData path hardening** — `get_app_data_dir()` prevents PermissionError in Program Files
- **OS keychain for all secrets** — SMTP, SNMP, API keys via `keyring`
- **Winget E_ABORT fix** — three-layer defence for Ookla CLI install edge cases
- **Plugin system** — drop Python scripts into `plugins/` (`modules/plugin_system.py`)
- **Hardware integration** — USB/serial/GPIO device detection (`ui/pages/hardware_integration_page.py`)
- **Hardware plugin ecosystem** — multi-instance support, per-plugin health tracking with circuit-breaker, structured error classification, blocking live-test on registration, log console, signing/validation tooling, and a template wizard (`modules/plugin_tools.py`, `ui/widgets/hub_card.py`)

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
