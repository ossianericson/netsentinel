# NetSentinel Backlog

## Vision

NetSentinel has two parallel strategic goals: become the first tool recommended when anyone says "my network is broken" — the de-facto standard for home network troubleshooting — and become the natural starting point for anyone learning how networks actually work. Both goals are served by the same core property: the tool must show you what is happening on your real network, in plain English, without requiring you to already know what you are looking for. Everything on this backlog either lowers the barrier to non-technical users or makes the tool usable in structured learning contexts.

---

## Priority 1 — De-facto Home Standard

Items in this track lower the barrier for non-technical users. Each item should be self-contained, require no configuration, and produce output that a non-technical person can act on immediately.

---

### ~~1. Local browser dashboard (web UI)~~ ✅ done in v1.6.8

**Description:** A read-only HTML dashboard served by the existing REST API worker, accessible at `http://localhost:8765/dashboard` from any browser on the LAN. Shows: current device list, network grade, recent alerts, and speed test history. No login required on localhost; external access still requires the API key.

**Why it matters:** Mobile access and household sharing without requiring anyone to install the app. Also makes NetSentinel usable on headless servers where the PyQt6 GUI cannot run. The REST API already exists — this adds the front end.

**Effort:** S (was M — REST API was fully built before this was started)

**Files affected:**
- `modules/metric_store.py` — `grade_result` table + `record_grade()` / `query_last_grade()`
- `modules/rest_api.py` — `/grade` endpoint; `/dashboard` route (exempt from auth, key embedded in served HTML)
- `modules/web_dashboard.py` — new module, `build_html(api_key)` returns self-contained dark-theme HTML + JS
- `ui/dashboard.py` — `_run_benchmark()` now calls `store.record_grade()` so grade persists across restarts

---

### 4. Anonymous opt-in ISP comparison

**Description:** Opt-in only, zero PII. On opt-in, submits: ISP name, country code, anonymised speed, latency, and uptime percentage once per day. Shows the user how their connection compares to the median for their ISP and country. Requires explicit opt-in toggle with a clear sentence describing what is sent.

**Why it matters:** Contextualises results. "Your latency is 42 ms" is not actionable. "Your latency is 42 ms — 38% worse than the median for your ISP in your country" is. It also creates a daily re-engagement hook and produces community data that benefits all users.

**Effort:** L

**Files likely affected:**
- `modules/isp_telemetry.py` — new module, submission and query logic; must be opt-in only with no fallback to passive collection
- `ui/pages/speed_test_page.py` — opt-in toggle and comparison panel
- Requires a backend endpoint — document the API contract here before implementation

---


---

## Priority 2 — Educational Standard

Items in this track make NetSentinel usable in structured learning contexts. Each item should produce output that maps directly to a textbook concept or exam objective and can be submitted as evidence of work.

---

### ~~1. Interactive protocol visualizer~~ ✅ done in v1.6.9

**Description:** Animated step-by-step diagrams of five protocols — ARP resolution, DNS lookup, TCP handshake, DHCP lease, and STP election — using real data from the most recent scan to populate device names, IP addresses, and timing. Each step shows which frame is sent, which device handles it, and what state changes.

**Why it matters:** Nothing teaches like seeing your own network's traffic explained visually. Static protocol diagrams in textbooks use placeholder addresses. This uses your actual router, your actual devices, your actual resolver. The protocol becomes a real process rather than an abstract description.

**Effort:** L

**Files likely affected:**
- `ui/pages/protocol_viz_page.py` — new page, animation engine (SVG or canvas-based)
- `modules/protocol_animator.py` — new module, data extraction from MetricStore and live scan results

---

### 2. "What just happened?" contextual explanations

**Description:** After every scan, every BPDU detection, every CVE match, every alert — a collapsible panel at the bottom of the relevant page shows a plain-English explanation of the protocol involved and why the specific result matters. Collapsed by default to avoid obstructing experienced users.

**Why it matters:** Passive learning with zero extra effort from the user. A student who opens the Rogue Bridge tab and sees a rogue bridge detected also sees an explanation of what STP is, what a root bridge election does, and why this causes periodic drops — without navigating away from the result.

**Effort:** M

**Files likely affected:**
- `ui/widgets/explainer_panel.py` — new reusable widget, collapsible with a toggle chevron
- All detection page files — add the explainer panel to each relevant result area

---

### 3. CompTIA Network+ / CCNA curriculum alignment

**Description:** Each feature page shows which exam objective(s) it covers as a compact badge below the page title. An exportable "study session" report lists every feature used during the session alongside the corresponding exam objectives — formatted as a checklist a student can attach to homework or submit to an instructor.

**Why it matters:** Formal adoption by instructors requires curriculum mapping. Without it, a teacher cannot justify replacing a textbook lab with a live scan. With it, the tool becomes a natural fit for any course that covers CompTIA Network+ Domain 2 (Network Implementations) or CCNA Exam Topics 1.x–3.x.

**Effort:** S

**Files likely affected:**
- `data/curriculum_map.json` — new file, objective ID → feature mapping
- All `ui/pages/` files — read the map and render objective badges near page titles
- `ui/widgets/objective_badge.py` — new widget, renders a compact labelled badge

---

### 4. Classroom export

**Description:** Students export a signed scan report (JSON + rendered HTML) containing a timestamp, a machine fingerprint (non-identifying hash), scan results, and a list of features used. Instructors have a separate aggregation view: import multiple student reports and get a comparison table showing what each student found.

**Why it matters:** Makes the tool usable as a lab submission format. Without a way for instructors to collect and compare student results, individual exports are useful only to the student who ran them. With classroom export, a teacher can set "run a full scan and submit your report" as a graded lab.

**Effort:** M

**Files likely affected:**
- `modules/classroom_export.py` — new module, report signing and aggregation
- `ui/pages/classroom_page.py` — new page, student export view and teacher aggregation view

---

## Priority 3 — Polish and Retention

Items ordered by visual impact. Each is self-contained and can be implemented independently.

### Tier 1 — Highest visual impact (do these first)

- ~~**Card border radius 8 px**~~ — ✅ done in v1.6.6
- ~~**Sidebar left accent bar on selected item**~~ — ✅ already present (`border-left: 3px solid {ACCENT_LITE}` in global QSS)
- ~~**Remove emoji from action buttons**~~ — ✅ done in v1.6.6 (8 buttons replaced with geometric Unicode)

### Tier 2 — Structural polish

- ~~**Font size tokens in `ui/styles.py`**~~ — ✅ done in v1.6.6 (`FONT_XS` through `FONT_XL` added; new pages must use them)
- ~~**Focus ring visible in dark themes**~~ — ✅ done in v1.6.6 (`QPushButton/QCheckBox/QRadioButton:focus` outline in `_build_qss()`)

- **Skeleton loading rows while scan workers are running** — prevents layout jump when data arrives; use a `QStandardItemModel` with placeholder rows styled in `TEXT_MUTED`, swapped out when the worker emits results.

### Tier 3 — Interaction and discoverability

- ~~**Page transitions — 120 ms opacity fade on QStackedWidget switches**~~ — ✅ done in v1.6.7 (`QGraphicsOpacityEffect` + `QPropertyAnimation` 120 ms OutCubic in `Dashboard._nav_set_page()`; effect removed on `finished` to avoid child widget painting interference)

- ~~**Table sort indicators**~~ — ✅ done in v1.6.7 (`QHeaderView::sort-indicator` sizing rule added to `_build_qss()` in `ui/styles.py`; Qt Fusion native arrow rendered on all sortable tables)

- ~~**Window title follows navigation**~~ — ✅ done in v1.6.6 (`_nav_set_page()` calls `setWindowTitle(f"NetSentinel — {label}")`)

- ~~**Collapsible inline row detail**~~ — ✅ done in v1.6.7 (`ExpandingTable` extended to `inventory_page.py` (Devices), `service_page.py` (Services), `uptime_page.py` (Availability History); click row to expand detail panel with colored border-left accent and QFormLayout columns)

### Tier 4 — Nice-to-have

- **"Abyss" WCAG AA high-contrast theme** — fourth theme; true black background, high-contrast text, no low-opacity elements. Required for users with visual impairments.
- **Breadcrumb strip** — above the `QStackedWidget`, shows `Section › Page`. One `QLabel` updated in `_switch_page()`.
- **Keyboard shortcut reference card in Help panel** — currently the shortcut list only appears in Settings.
- **Per-page documentation link** — small `?` link on each page header opening the relevant wiki section.
- **Passive 802.11 monitor mode capture** — optional advanced capture path that puts a supported NIC into monitor mode (via Npcap on Windows) and reads raw 802.11 management/probe/beacon frames, bypassing normal Ethernet capture. Primarily useful on networks with AP client isolation. Silently falls back to standard capture if unsupported. Pro-tier feature — too advanced and too NIC-dependent to be a home-user default.

---

## Completed

Most recent first.

### v1.6.10 — May 2026

**Home-user retention — three engagement improvements**

- **"Since you were last here" banner** — appears on home page load when the app has been closed for 30+ minutes; counts new devices joined and outages recorded since last visit (via `query_device_events()`); stores `app/last_visit_ts` in QSettings on each launch; hidden on first-ever launch and on quick re-launches
- **Contextual "What to do next" suggestions strip** — appears after every scan completion on the home page; up to four colour-coded action cards (red = high priority, amber = medium, blue = low); checks: high-risk device count, logger not running, no speed test in 7 days, open CVEs, poor network grade (C/D/F); each card has a navigation button; all hidden when no suggestions exist
- **Weekly digest tray notification** — fires on startup if 7+ days since last digest (`app/last_digest_ts`); summarises last 7 days: download speed, new devices joined, network grade; gracefully skipped if tray is unavailable or store has no data
- `ui/pages/home_page.py` — `set_last_visit_summary()`, `set_suggestions()` methods; `_last_visit_card` panel and `_suggestions_card` strip added to layout
- `ui/dashboard.py` — `_compute_suggestions()`, `_compute_last_visit_summary()`, `_maybe_send_weekly_digest()` methods; `_compute_suggestions()` called at end of `_on_m1_result`; last-visit and digest helpers scheduled via `QTimer.singleShot` in `_restore_settings()`

---

### v1.6.9 — May 2026

**Closes P2-1 (Interactive protocol visualizer)**

- `ui/pages/protocol_viz_page.py` — new page in Education nav; five protocol picker buttons; auto-plays on selection; play/pause, reset, step-forward, step-back controls; step description panel with plain-English explanation per step
- `ui/widgets/protocol_canvas.py` — `ProtocolCanvas(QWidget)` custom QPainter animation; 30 fps tick via `QTimer`; ease-out-cubic dot travel; node cards coloured by role; dashed arrows for broadcasts; ghost trail of completed steps; arrowhead drawn on current step
- `modules/protocol_animator.py` — `AnimNode`, `AnimStep`, `ProtocolSceneData` dataclasses; five builders: `build_arp_scene`, `build_dns_scene`, `build_tcp_scene`, `build_dhcp_scene`, `build_stp_scene`; ARP and DNS use real gateway/resolver addresses from last scan; TCP and DHCP are conceptual illustrations labelled as such; STP uses live BPDU data when available
- `ui/dashboard.py` — `ProtocolVizPage` instantiated and added to Education section; `set_context()` called from `_update_net_info_ui` and `_on_diag_result` so the page refreshes on every scan
- `NetSentinel.spec` — three new hidden imports added

---

### v1.6.8 — May 2026

**Closes P1-1 (Local browser dashboard)**

- `GET /dashboard` — self-contained dark-theme HTML page served directly from the Flask REST API; no auth prompt (API key baked into the page JS at render time); auto-refreshes every 30 s with a live countdown; manual Refresh button; zero CDN dependencies
- Dashboard panels: Network Grade circle (coloured A–F), device table (name/IP/MAC/vendor/auth badge/last-seen), recent alerts (last 24 h with severity badges)
- `GET /grade` — new endpoint returning `{grade, score, verdict, ts}` (null fields if no benchmark has run)
- `modules/web_dashboard.py` — new module; `build_html(api_key)` generates the full page
- `modules/metric_store.py` — `grade_result` table (schema v8); `record_grade()` / `query_last_grade()`; grade persists across app restarts
- `ui/dashboard.py` — `_run_benchmark()` calls `store.record_grade()` after each benchmark run
- `modules/rest_api.py` — `/dashboard` and `/grade` added; docstring endpoint list updated; UTF-8 BOM stripped (was present on file, same issue as `cli.py` in v1.6.7)

---

### v1.6.7 — May 2026

**Priority 3 Tier 3 interaction polish**

- 120 ms opacity fade page transitions — `QGraphicsOpacityEffect` + `QPropertyAnimation` (OutCubic) applied to incoming widget in `Dashboard._nav_set_page()`; running animation aborted cleanly before new switch; effect removed on `finished` signal to avoid Qt painting interference with child widgets
- Sort indicator QSS — `QHeaderView::sort-indicator` sizing rule added to `_build_qss()` in `ui/styles.py`; native Qt Fusion arrow now visible on all sortable tables without image assets
- Collapsible inline row detail on three remaining pages — `ExpandingTable` replaces `QTableWidget` in `inventory_page.py` (Devices), `service_page.py` (Services), `uptime_page.py` (Availability History); each detail panel uses `border-left:3px solid {status_color}`, two `QFormLayout` columns, `BG_HOVER` background; `service_page.py` includes last-5-checks ●/○ dot history strip
- `ui.skeleton`, `ui.empty_state`, `ui.expanding_table`, `ui.command_palette` added to `NetSentinel.spec` `hiddenimports` — fixes macOS/Linux smoke-test failure where `ui.skeleton` was not reachable by PyInstaller static analysis
- `cli.py` UTF-8 BOM stripped — `SyntaxError: invalid non-printable character U+FEFF` at line 1 resolved

---

### v1.6.6 — May 2026

**Priority 3 Tier 1–2 UI polish**

- `CARD_RADIUS = "8px"` token added to `ui/styles.py`; all content card `QFrame`/`QWidget` styleSheets across 21 page files and `dashboard.py` updated — accent strips and card inner headers intentionally remain 0 px
- `FONT_XS`/`FONT_SM`/`FONT_MD`/`FONT_LG`/`FONT_XL` typography tokens added to `ui/styles.py`; new pages must use these (RULE-AH3 scope)
- Focus ring added to `_build_qss()` — `QPushButton/QCheckBox/QRadioButton:focus` gets `outline: 1px solid {ACCENT}` in every theme
- `QHeaderView::section:hover` background rule added to `_build_qss()`
- 8 action buttons / nav icon had emoji replaced with geometric Unicode glyphs: `◎ Scan & Grade`, `◎ Grade My Network`, `⊟ Generate ISP Report`, `◆ Guided Troubleshooter`, `⊕ Scan Network`, `⊕ Look up MAC`, `⊕ Load & Analyse Log`, `◎ View Chart`, `◉` Health & History nav group
- Window title now follows navigation: `_nav_set_page()` calls `self.setWindowTitle(f"NetSentinel — {label}")` on every switch
- `ui.skeleton`, `ui.empty_state`, `ui.expanding_table`, `ui.command_palette` added to `NetSentinel.spec` `hiddenimports` — fixes macOS/Linux smoke-test failure where `ui.skeleton` was never reached by PyInstaller static analysis

### v1.6.5 — May 2026

**Dashboard wiring audit + empty-state UX pattern**

- Full dashboard wiring audit — complete second pass connecting all unwired overview tile methods: `OverviewPage.update_cycle`, `update_ha_states` (from `avail_worker` cycle), `update_services` (from `svc_worker`); `ThreatIntelPage.entries_updated` signal wired to `GeoMapPage.set_threat_entries`; all always-on worker signals (AvailabilityWorker, CertWorker, SvcWorker, SnmpTrapWorker, SyslogWorker) verified present in `app.py`
- Empty-state with inline CTA — four pages converted from dead-end text to `QStackedWidget` pattern (page 0 = empty state + action button, page 1 = content): Network Grade ("Scan & Grade" auto-triggers scan + benchmark), ISP Report (triggers diagnostics when cold, auto-opens save dialog), Network Doc ("Scan & Document" via `scan_requested` signal), Availability History ("Start Monitoring" via `scan_requested` signal)
- RULE-DW2 — new APM rule: always-on worker signals must be wired in `app.py` after `window = Dashboard(...)`, not inside `Dashboard`; documents why and provides the pattern
- RULE-UX5 — new APM rule: empty-state with inline CTA is mandatory for data-dependent pages; documents `QStackedWidget` pattern, button label conventions, and wiring location

### v1.6.4 — May 2026

**Closes P1-1 (Shareable diagnostic card) and P2-2 (Lab / scenario mode)**

- Shareable diagnostic card *(P1-1)* — "Share Card ▾" button on Overview page, enabled after first benchmark run; QMenu with Save PNG, Copy PNG, and Save HTML; PNG rendered via `render_card_widget().grab()` — zero external deps; card shows grade circle, ISP/public IP, top 3 findings from worst benchmark dimensions, device count, timestamp, attribution line
- `modules/diagnostic_card.py` — `CardData` dataclass, `build_card_data()` (assembles from `BenchmarkResult` + optional `DiagnosticsResult` + `MetricStore`; no new scans), `render_card_widget()` (fixed 520×300 QWidget for Qt pixel grab)
- `modules/report_exporter.py` — `generate_card_html()` and `save_card_html()` reusing existing `_CSS` tokens; no new PDF path
- Lab / scenario mode *(P2-2)* — `LabModePage` (picker → runner → result panels) with four exercises: "Find the Rogue Device", "Diagnose Slow DNS", "Identify the Broadcast Storm Source", "Map Your Subnet"; progressive hints, solution reveal, exportable HTML result report; `_LabScanWorker` (QThread) per scan type; `LabResult.to_dict()` includes machine fingerprint for future classroom export (P2-4 compatibility); Education nav section
- `modules/lab_scenarios.py` — `LabScenario`, `LabStep`, `LabResult` dataclasses; JSON-serialisable result with `schema` and `machine_fp`
- `modules/report_exporter.py` — `generate_lab_html()` and `save_lab_report()`; no new export module or PDF engine

### v1.6.3 — May 2026

**Closes P1-2 (Guided troubleshooting wizard)**

- One-click "What's Wrong?" diagnosis *(P1-2)* — `DiagnosisPage` with symptom tiles ("My internet is slow" / "My connection keeps dropping" / "I can't connect at all"), idle → running → done state machine, finding cards with severity badges; `DiagnosisWorker` sequences: network diagnostics → storm analysis → rogue device scan → STP rogue bridge detection → root-cause correlation; `modules/root_cause_correlator.py` produces prioritised plain-English findings and global verdict; accessible from Home page banner and Ctrl+K command palette

### v1.6.2 — May 2026

- Home page UX overhaul — scan CTA hierarchy: primary "Start Scan" uses design-system `#btnScanHero` (filled accent); secondary "View ISP Report" uses global `QPushButton` outline style; removed `_action_btn_qss` inline-hex block (architecture violation)
- Dynamic scan button label — "Run First Scan" when no devices are known, switches to "Start Scan" after first successful scan cycle
- Guided Troubleshooter banner — moved from inline button row into a dedicated `UPDATE_BAR_BG` informational strip above the hero card, visually separating onboarding tool from operational scan loop; `self._btn_diagnose` wired and ready for diagnosis worker connection
- Subtitle microcopy updated to "Run a scan to discover devices and check connectivity."
- Removed 8 now-unused imports from `home_page.py`; all hero-section colours now sourced from `ui.styles` tokens

### v1.6.1 — May 2026

- New hexagon+shield icon identity across all assets — ICO (7 sizes), MS Store tiles (Square44/71/150/310, Wide310x150, StoreLogo), SplashScreen, macOS/Linux PNG
- `generate_icons.py` — programmatic icon generator, run after any brand change
- SVG source artwork: icon, store, tray, splash-screen variants
- Top-bar brand in `ui/dashboard.py` — 24×24 app icon replaces the "N" letter (PyInstaller-aware path, smooth-scaled QPixmap, "N" fallback if file missing)
- README rewrite — hero badges, story, features table, educator section, privacy table, 3-version changelog
- BACKLOG.md created — vision statement, Priority 1–3 tracks, completed archive
- `bump_version.py` patched to support `count` param so README changelog headers are not clobbered by wildcard substitution

### v1.6.0 — May 2026

- Command palette (Ctrl+K) — fuzzy-match any page or action; arrow keys + Enter to navigate; Esc to dismiss
- Pinnable sidebar pages — right-click to pin to a permanent Favourites section; state persists via QSettings
- Inline row expansion in CVE Tracker and Active Connections — no dialog, GitHub PR style; click again to collapse
- Animated counter tiles on Overview — ease-out count-up on each data refresh; 3 px health bar per tile
- Alert badge on Security Audit section header — live unacknowledged CVE count, updates every 30 s
- Empty-state overlays on all major tables — centred icon and placeholder text instead of blank area
- Winget E_ABORT fix — three-layer defence: `PrivilegesRequiredOverridesAllowed = dialog commandline`, `ShouldInstallOokla()` check guard, `/TASKS="!installookla"` in all manifest silent switches
- Alert rules default to disabled on fresh installs — no alert fires without explicit opt-in

### v1.5.0 — April 2026

- Progressive sidebar navigation — Home / Standard / Pro modes cycled by a pill; mode persists across sessions
- Wi-Fi signal-strength heatmap — floor plan import, per-BSSID IDW interpolation, PNG export
- Geolocation map — offline MaxMind GeoLite2-City, no API key, no external calls
- Custom trigger expressions — metric expression language with visual rule builder and live plain-English preview
- Automation hooks — event-driven webhook and script triggers
- Network documentation generator — one-click HTML/Markdown network snapshot
- MQTT / Home Assistant publisher — Discovery payloads, configurable broker, OS keychain credentials
- AppData path hardening — no PermissionError when installed in `C:\Program Files\`
- Sidebar emoji replaced with geometric Unicode symbols — RULE 25 compliance
- Ctrl+F sidebar search from any page

### v1.4.0 — March 2026

- Active Connections tab — process-to-socket map with firewall block/unblock
- Live Bandwidth tab — 60-second rolling interface chart
- SMTP and SNMP credentials migrated from QSettings plaintext to OS keychain
- Navigation restructured into 7 named subgroups

### v1.3.1

- Configurable Overview tile dashboard — drag to reorder, layout persists via QSettings
- Three colour themes — Arctic Clean, Midnight Pro, Obsidian Neon; all colour values in `ui/styles.py`
- Dedicated App Settings dialog
- Help & Reference panel — glossary, Common Scenarios table, Risk Level Guide
- First-run onboarding wizard — 3-step action wizard replacing the informational slideshow
- Notification routing rules — Toast / Webhook / Email channels with per-channel severity filter
- Config baseline snapshots and diff viewer — structured diff: added/removed/changed devices
- Predictive trend alerting — OLS regression over RTT/loss/jitter; ETA-to-threshold column
- Maintenance windows — alert suppression for defined periods per device or fleet-wide
- Version consistency test suite — 6 automated tests across all version-bearing files
