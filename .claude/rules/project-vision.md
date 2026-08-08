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

Current version: **v2.2.5**

**Production status: Microsoft Store ready.** A 9-hour overnight chaos run (June 2026) completed 10,001 UIA interactions across mild / moderate / wild chaos levels (seeds 1, 42, 99). Result: zero application crashes, all 62 pages functional before and after (confirmed by identical systematic pre/post runs). The app is considered production-stable for Microsoft Store submission.

**Chaos run log** — each entry is a full `tools/run_all_monkey_tests.ps1` result. A run is clean
only if `netsentinel_crash.log` gained **zero bytes** (baseline its size at run start; the log is
append-only and never rotated, so a count means nothing — RULE-CHAOS2). A native SEH fault does
not kill the process, so "no crash" alone is not evidence of a clean run.

| Date | Duration | Result |
|---|---|---|
| June 2026 | 9 h overnight | 10,001 interactions, seeds 1/42/99 — clean; the Store-readiness baseline |
| 2026-07-13 | 1 h, 7 phases | 1,230 interactions + 2 full 62-page systematic sweeps — clean, **zero crash-log growth**. First run to survive the UIA warmup fix (RULE-WIN10); every prior run aborted its phase on a new `0x8001010d` entry. Peak RSS 509–574 MB, no upward trend. |
| 2026-07-13/14 | ~7 h overnight (8 h budget, user-interrupted mid-wild) | 9,729 interactions across mild/moderate/wild soak laps (1,291 / 3,397 / 5,041) — clean, **zero crash-log growth** (baseline unchanged at 6,775,780 bytes from before the run to after). Zero exceptions logged at every progress checkpoint. Peak RSS 674 → 775 → 750 MB across the three laps — flat, no leak trend. |
| 2026-07-21/22 (v2.1.39) | ~10 h overnight (15:26–01:23), 1 coverage cycle + soak lap 1 | 13,612 interactions across mild/moderate/wild/real-mouse-wild/scan-navigate + a full mild→moderate→wild soak lap (1,498 / 1,441 / 8,351) + 2 full 62-page systematic sweeps — clean, **zero crash-log growth** (`netsentinel_crash.log` byte-identical, mtime unchanged from before the run to after). Zero exceptions in every phase. One self-healed hang (47 s stall at iter 1535) mid-wild-soak — health monitor auto-restarted the app and the phase continued cleanly to iter 8,351. Three "shutdown hang" flags in the raw phase table were a `monkey_test.py` false positive, not an app defect: the titlebar-X click missed after a Win+Down chaos action resized the window, confirmed via `netsentinel_shutdown.log` showing no `closeEvent` entry at any of those three timestamps (vs. a clean, logged 2.39 s exit for the one phase that closed normally). **Open lead, unlike the flat 07-13/14 run:** Peak RSS rose across the soak ladder — mild 690 → moderate 967 → wild 1,432 MB — and tracemalloc's Python-level snapshots don't account for the growth, so it is very likely a native Qt/matplotlib-side leak (the same invisible-to-tracemalloc class as the already-fixed command-palette/dialog leaks), not yet isolated. |
| 2026-07-23/24 (v2.1.43, RULE-CHAOS1 catch-up for v2.1.42) | ~11.5 h across the day, final 4.5 h wild-soak phase (19:37–00:04) at full 16,200 s budget | Earlier same-day phases (12:46–14:13) hit the already-diagnosed Win+Down/minimized-window false-restart and false-"shutdown hang" patterns — the exact defects fixed mid-run by `0977625`/`a69c7aa`/`c425f9b` in this release, so this run doubled as their validation. Final full-budget wild-soak phase: 9,656 iterations, **0 crashes, 0 exceptions**, **zero growth** in both `netsentinel_crash.log` and `netsentinel_exceptions.log` (mtimes predate the phase), clean titlebar-X shutdown (1.78 s). 2 restarts, both self-healed `[health]` hang-detections (46 s+ stalls), not app faults. **RSS lead still open, unchanged by this release's fixes (none targeted memory):** 549 MB → 1,440.8 MB peak over 4.5 h, same ballpark as the 07-21/22 wild-soak peak (1,432 MB) — not worsened, not resolved. |
| 2026-08-03/04 (v2.2.2) | ~10 h overnight (21:37–07:46, user-interrupted mid soak-lap-2-mild) | 1 coverage cycle + soak lap 1 (mild/moderate/wild, full budget) — clean, **0 crashes, 0 exceptions**, `netsentinel_crash.log` byte-identical since 2026-07-30 (zero growth). 1 self-healed restart (window/process gone at iter 1616, foreground reclaimed in 15 s), 0 hangs. **Peak RSS 1,838 MB (wild soak lap 1)** — the first run confirmed free of the `+ust` instrumentation artifact below; RSS ladder back to the 07-21/22–07-23/24 ballpark (1,432–1,441 MB), not the 2,880–3,798 MB range seen while `+ust` was armed. See closure note below the table. |
| 2026-08-06/07 (v2.2.2, post-Signal-Quality) | ~11 h overnight (21:39–08:34, user-interrupted mid soak-lap-2-moderate) | 1 coverage cycle + soak lap 1 (full budget) + partial lap 2 — clean, **0 crashes, 0 exceptions**, `netsentinel_crash.log` byte-identical to its run-start baseline (6,784,379 bytes, mtime still 2026-07-30). Both systematic sweeps 68/68 pages. The only `netsentinel_exceptions.log` growth is `KeyboardInterrupt` frames timestamped at the user's Ctrl+C — teardown noise, not a defect. 3 restarts, all the foreground-stuck escape hatch (`f2e483b`/`0e1575d`) firing correctly after 20 consecutive focus-reclaim failures — this run is that fix's first live validation. **Read the peak-RSS column with care here:** see the measurement note below the table. |

**Peak RSS is the max of a noisy oscillating signal — compare steady-state medians instead.**
The 2026-08-06/07 run's `AI_REPORT.md` peak column suggested a +38.7% wild-soak regression
(1,838 → 2,550 MB) against the 08-03/04 row. Medians from the same runs' `Progress iter=… rss=…MB`
series tell a much smaller story — mild 556 → 561 MB (noise), moderate 1,086 → 1,218 MB (+12%),
wild 1,237 → 1,488 MB (+20%) — and the *shape* is a sawtooth plateau, not a climb (moderate
oscillates 1,014 → 1,294 → 1,002 → 1,301, nothing like the monotone +556 MB/hr signature of the
lazy-page-timer leak). Decisively, the drift **resets lap-over-lap**: mild lap 1 median 556 MB vs
lap 2 median 554 MB in a fresh process. That is exactly the criterion the closure note below sets
for reopening this lead, and it is not met — so it stays closed. This is the same
peak-vs-plateau trap already recorded for the 2026-07-31 run; prefer medians for any future
run-over-run comparison.

One tempting hypothesis was killed by measurement rather than code reading: that the Signal
Quality workstream's default-on alert rules exploded the unacked backlog, making the Home card's
new per-refresh ranking O(N) over a growing N. Only **9 alerts fired across the entire 11-hour
run**, and the unacked backlog is **128 rows** — ranking 128 rows every 30 s is free. Check the
`alert_fired` table before building on any alert-volume theory.

**The RSS lead carried by the 07-21/22 and 07-23/24 rows is closed as of v2.2.0.** Root cause
was never navigation, native Qt/matplotlib retention, or Network Map: `ui/nav/lazy_page.py`'s
background chunk-builder constructs every lazy page shortly after startup, so a `QTimer` started
in `__init__` ran for the whole session on pages the user never opened — rebuilding
`QTableWidget`s whose `QTableWidgetItem`s are C++ objects, which is why five rounds of
tracemalloc/UMDH/VMMap saw nothing. Measured on an idle Dashboard with a real `MetricStore`:
**+556 MB/hr → −19.6 MB/hr**. Full narrative in
`docs/spikes/idle-rss-leak-lazy-page-timers.md`; invariant captured as RULE-WIN18.

**Chaos-verified and closed as of 2026-08-04.** The bench-only caveat above is resolved: the
2,880 MB (07-27/28) and 3,798 MB (08-02) peaks that briefly reopened this lead after v2.2.0 turned
out to be measured with a stray debugging gflag, `FLG_USER_STACK_TRACE_DB` (`+ust`), armed on
`python.exe` — left set by an unrelated UMDH probing session. `+ust` captures a full native stack
trace on every heap allocation, which inflates both startup time (5.8 s → 99 s measured) and
reported RSS, and is invisible to Python-level tools (tracemalloc), which is why five earlier
diagnostic rounds saw nothing conclusive. `tools/monkey_test.py` and
`tools/run_all_monkey_tests.ps1` now refuse to start (`--allow-gflags` to override) if `+ust` is
armed, so it cannot silently recur. The 2026-08-03/04 row above is the first full soak run
confirmed clear of it, and its peak (1,838 MB) landed back in the pre-`+ust` ballpark instead of
climbing further. A small residual drift remains (~150–200 MB within that one wild-soak lap,
sample floor ~1,520 MB → ~1,700 MB) but is an order of magnitude below what motivated this
investigation and is not being pursued further given the app's established crash-free record;
revisit only if a future run shows the drift compounding lap-over-lap rather than resetting.

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
- **CVE lifecycle tracker** — per-device CVE tracking (schema v20)
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
- **Two colour themes, instant switching** — Arctic Clean (light, cool-slate chrome with deep-indigo table headers) and Midnight Pro (dark, bright royal-blue accent); clicking a theme swatch in Settings restyles the whole running app immediately, no restart (`ui/styles.py`)
- **Native Windows window chrome** — the custom header is drawn into a REAL Win32 window (frame painting suppressed via `WM_NCCALCSIZE`), so Aero Snap, Snap Layouts, Win+arrow, drag-to-snap, shake and native resize all work. Default for every Windows user since v2.1.30; non-Windows keeps the frameless path (`ui/native_chrome.py`)
- **Configurable Overview tile dashboard** — drag to reorder, layout persists
- **Skeleton loading rows** — placeholder rows while scan workers run (`ui/widgets/skeleton.py`)
- **Feature Guide** — filterable index of feature entries with Open buttons (`ui/pages/discover_page.py`)
- **Scan Registry / flyout dot badges** — per-page scan state drives flyout and rail badges (`_NavBuilderMixin`)
- **_ScanStatusTile** — Overview tile showing live scan state for all Security Audit tools
- **Last run chips** — "Last run: N ago" chip on Speed Test and DNS Zone pages

### Home Page
- **"Since you were last here" banner** — new devices and outages since last session
- **"What to do next" suggestions strip** — up to four action cards after each scan (rules in `modules/suggestion_engine.py`)
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
