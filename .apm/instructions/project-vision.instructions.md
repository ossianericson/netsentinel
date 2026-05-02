---
applyTo: "**"
---

# NetSentinel — Project Vision & Purpose

## Strategic Goals (from BACKLOG.md)

NetSentinel has two parallel strategic goals:

1. **De-facto home network standard** — become the first tool recommended when anyone says "my network is broken". The tool must show what is happening on the real network, in plain English, without requiring the user to already know what STP, ARP, or DNS are.

2. **Educational standard** — become the natural starting point for anyone learning how networks actually work. Every feature should produce output that maps directly to a textbook concept or exam objective and can be submitted as evidence of work.

Both goals are served by the same core property: zero prior knowledge required. Everything on the backlog either lowers the barrier for non-technical users or makes the tool usable in structured learning contexts.

---

## What This Product Is

NetSentinel is a **professional-grade network security scanner and monitor** for Windows, macOS, and Linux. It is a desktop GUI application (PyQt6) targeting IT administrators, network engineers, security-aware home lab users, and students/educators who need an enterprise-quality tool — not a toy.

**Current version: 1.6.0**

---

## Implemented Features (shipped as of v1.6.0)

### Core Scanning & Detection
- **Layer 2 rogue device detection** — ARP scanning, MAC/OUI classification, rogue bridge (STP) detection
- **Broadcast storm analysis** — real-time packet capture and storm level measurement
- **WiFi network enumeration** — rogue SSIDs, co-channel interference
- **DNS & connectivity monitoring** — latency graphing, outage detection, DNS leak testing
- **Active security audit** — SYN/UDP port scanning, OS fingerprinting, CVE lookup, credential testing (requires admin)
- **Background network logging** — continuous ping/RTT/jitter/DNS logging with analysis
- **Network topology visualisation** — live matplotlib graph showing device relationships
- **IoT behaviour baselining** — detect devices going outside their normal behaviour
- **Internet speed test** — Ookla CLI (1 Gbps+) → speedtest-cli (8 threads) → pure-Python (16 TCP streams)

### Monitoring & Alerting
- **Active Connections** — process-to-socket map with firewall block/unblock
- **Live Bandwidth** — 60-second rolling per-interface chart
- **Threat Intelligence** — ThreatIntelDB, AbuseIPDB v2 lookup (consent-gated)
- **DHCP Lease Inventory** — rogue DHCP server detection
- **DNS Zone Mapping** — AXFR + mDNS
- **CVE lifecycle tracker** — per-device CVE tracking with metric_store schema v7
- **Alert pipeline** — AlertEngine + NotificationRouter with Toast/Webhook/Email/Pushover/Ntfy/Telegram channels
- **Maintenance windows** — alert suppression per device or fleet-wide
- **Predictive trend alerting** — OLS regression over RTT/loss/jitter with ETA-to-threshold

### Navigation & UI
- **Progressive sidebar navigation** — Home / Standard / Pro modes; toggled by pill; persists via QSettings
- **Command palette (Ctrl+K)** — fuzzy-match any page or action; arrow keys + Enter; Esc to dismiss
- **Pinnable sidebar pages** — right-click to pin to Favourites section; persists via QSettings
- **Sidebar search (Ctrl+F)** — focuses sidebar search from anywhere in the app
- **Geometric Unicode sidebar icons** — RULE 25 compliance; no photo-emoji
- **Three colour themes** — Arctic Clean, Midnight Pro, Obsidian Neon; all values in `ui/styles.py`
- **Configurable Overview tile dashboard** — drag to reorder, layout persists

### Data & Reporting
- **PDF report export** — `save_pdf_report()`
- **Config baseline snapshots and diff viewer** — structured diff: added/removed/changed devices
- **REST API** — read-only Flask, 127.0.0.1 default, OS-keychain API key
- **Wi-Fi signal-strength heatmap** — floor plan import, per-BSSID IDW interpolation, PNG export
- **Geolocation map** — offline MaxMind GeoLite2-City, no API key, no external calls
- **Network documentation generator** — one-click HTML/Markdown network snapshot
- **MQTT / Home Assistant publisher** — Discovery payloads, configurable broker, OS keychain credentials

### UX Polish (v1.6.0)
- **Inline row expansion** — CVE Tracker and Active Connections; GitHub PR style; click to toggle
- **Animated counter tiles** — ease-out count-up on Overview refresh; 3 px health bar per tile
- **Alert badge on Security Audit** — live unacknowledged CVE count, updates every 30 s
- **Empty-state overlays** — centred icon + placeholder on all major tables
- **Alert rules default to disabled** on fresh installs — no alert fires without explicit opt-in

### Security & Plumbing
- **AppData path hardening** — `get_app_data_dir()` prevents PermissionError in `C:\Program Files\`
- **OS keychain for all secrets** — SMTP, SNMP, API keys via `keyring`; never QSettings
- **Winget E_ABORT fix** — three-layer defence for Ookla CLI install edge cases
- **Plugin system** — drop Python scripts into `plugins/`; exposed via Pro mode sidebar

---

## Roadmap (from BACKLOG.md)

### Priority 1 — De-facto Home Standard
Items that require no configuration and produce output a non-technical person can act on immediately:

1. **One-click "What's Wrong" diagnosis** — single button runs all detection modules; 3-sentence plain-English verdict with remediation. New: `modules/root_cause.py`, `modules/root_cause_correlator.py` (drive existing logic).
2. **Shareable diagnostic card export** — PNG/HTML: network grade, ISP, top 3 findings, attribution. New: `modules/diagnostic_card.py`.
3. **ISP comparison telemetry** (opt-in only) — contextualises speed/latency against median for user's ISP+country. New: `modules/isp_telemetry.py`; requires a backend endpoint.

### Priority 2 — Educational Standard
Items that produce output mappable to textbook concepts and submittable as lab evidence:

1. **Interactive protocol visualizer** — animated ARP/DNS/TCP/DHCP/STP diagrams using real scan data. New: `ui/pages/protocol_viz_page.py`, `modules/protocol_animator.py`.
2. **Lab / scenario mode** — pre-built exercises ("Find the rogue device", "Diagnose slow DNS") with hints, solution reveals, exportable results. New: `ui/pages/lab_mode_page.py`, `modules/lab_scenarios.py`.
3. **"What just happened?" event feed** — plain-English explanation of every network event as it fires.
4. **Classroom export** — signed scan report (JSON + HTML) with machine fingerprint; instructor aggregation view. New: `modules/classroom_export.py`, `ui/pages/classroom_page.py`.

### Priority 3 — Polish and Retention
Low-effort improvements to reduce friction for existing users:

- Card border radius 8 px (one QSS line in `ui/styles.py`)
- Sidebar left accent bar (3 px coloured strip on active row)
- "Abyss" WCAG AA high-contrast theme (fourth theme)
- Skeleton loading rows while scan workers run
- Collapsible inline row detail in Devices, Services, Availability History tables
- Breadcrumb strip above QStackedWidget showing current section → page
- Keyboard shortcut reference card in Help panel
- Per-page documentation link opening the relevant wiki section

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

- Do not add consumer-style gamification (glow effects, neon colours, oversized animations)
- Do not abstract away technical detail — show MAC addresses, full IP ranges, exact RTTs
- Do not add cloud sync, accounts, or telemetry without explicit opt-in
- Do not bundle third-party binaries with their own licences (Ookla CLI, Npcap)
- Do not use photo-emoji in the sidebar — geometric Unicode symbols only (RULE 25)
