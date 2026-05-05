# NetSentinel Backlog

## Vision

NetSentinel has two parallel strategic goals: become the first tool recommended when anyone says "my network is broken" — the de-facto standard for home network troubleshooting — and become the natural starting point for anyone learning how networks actually work. Both goals are served by the same core property: the tool must show you what is happening on your real network, in plain English, without requiring you to already know what you are looking for. Everything on this backlog either lowers the barrier to non-technical users or makes the tool usable in structured learning contexts.

---

## Priority 0 — VSCode for Networking ✅ Complete in v1.7.0

Items in this track transform NetSentinel from a scanner you run occasionally into a monitor that is always running, always showing state, and always explaining what it sees. All items extend existing infrastructure — no new backends or animation engines.

Implementation order: 1-A → 1-B → 2-A → 3-B → 3-A → 2-B → 3-C. All shipped in v1.7.0.

---

### 1-A: Persistent status bar ✅ v1.7.0

**Description:** A permanent 24 px strip at the bottom of the main window showing four live segments: ● Online/Offline (from MetricStore last RTT), N devices (from MetricStore device count), "Last scan: Xm ago" (from MetricStore scan timestamp), and ⏺ Logger running / ○ Logger off (from `NetworkLogger.is_running()`). Updates on a 10-second QTimer. Clicking any segment navigates to the relevant page.

**Why it matters:** A new user who opens the app has no signal that anything is monitoring their network unless they navigate to a specific page. The status bar makes the app feel alive and contextual at all times — exactly what VSCode's status bar does for the editor state.

**Effort:** S

**Files likely affected:**
- `ui/dashboard.py` — new `_StatusBar` widget added below `_stack`; wired to MetricStore + NetworkLogger reference

---

### 1-B: Network Logger enabled by default ✅ v1.7.0

**Description:** On first launch (no `QSettings("logger/enabled")` key), enable the network logger for `8.8.8.8` and the detected default gateway. Users who want to disable it can via Settings. Also: default log rotation to 24 h so the CSV does not grow unbounded on a first-launch user.

**Why it matters:** The logger is the most valuable always-on tool in the app — it records outages with exact timestamps. But it requires manual opt-in. A new user who closes the app after a week has no record of what happened on their network.

**Effort:** XS

**Files likely affected:**
- `ui/dashboard.py` — first-launch detection + default logger start
- `ui/pages/settings_page.py` — UI copy update

---

### 2-A: Log Hub page ✅ v1.7.0

**Description:** New page `ui/pages/log_hub_page.py` presenting three inner tabs (not primary nav): Network Log (stream from the CSV files written by `network_logger.py`, colour-coded by status, filterable by host), Syslog (replicate the table from `syslog_page.py`), SNMP Traps (replicate the table from `snmp_trap_page.py`). Registered in the Monitor section as "Logs". Existing deep pages stay in nav.

**Why it matters:** Three log sources live in three separate nav sections. A new user who sees "Syslog Viewer" and "SNMP Trap Receiver" has no idea these are related to logging, or that the Network Logger writes CSV files at all. VSCode's Output panel with channels is the model: one place, filter by source.

**Effort:** M

**Files likely affected:**
- `ui/pages/log_hub_page.py` — new page
- `ui/dashboard.py` — register in Monitor section as "Logs"

---

### 3-B: "Explain This" collapsible panel on detection pages ✅ v1.7.0

**Description:** After a scan completes on any detection page (rogue device, DNS, storm, CVE), a collapsed "→ What just happened, technically?" bar appears at the bottom of the results card. Expanding it shows 3–5 sentences about the protocol exercised and a "▶ See animated diagram" button navigating to Protocol Visualizer. Content is a static `dict[page_id, str]` inside the new widget — no new network calls.

**Why it matters:** Passive learning with zero friction. A student who sees a rogue bridge detected also sees what STP does and why this causes periodic drops — without navigating away.

**Effort:** M

**Files likely affected:**
- `ui/widgets/explainer_panel.py` — new reusable collapsible widget
- Detection page files — add explainer panel below results card

---

### 3-A: Protocol Visualizer "What this means" panel ✅ v1.7.0

**Description:** Add a collapsible right panel (180 px, toggled by a "?" button) in `protocol_viz_page.py`. Two sections per protocol: "Why this protocol exists" (2–3 sentences) and "What can go wrong / what NetSentinel checks for" (with a link to the relevant scan page). Content is a static dict inside the page file.

**Why it matters:** The protocol visualizer currently shows how ARP works in general but gives no connection to why a user should care or what NetSentinel does about it. The "What this means" panel bridges animation → action.

**Effort:** S

**Files likely affected:**
- `ui/pages/protocol_viz_page.py` — collapsible panel + content dict

---

### 2-B: Log entry → protocol animation link ✅ v1.7.0

**Description:** Any row in the Log Hub Network Log tab with a non-empty `arp_event` column gets a clickable "▶ See ARP animation" cell. Clicking pre-loads Protocol Visualizer with the addresses from that ARP event via a new `load_from_event(entry)` method on `ProtocolVizPage`. The `build_arp_scene()` function already accepts addresses as parameters.

**Why it matters:** Makes the connection explicit: "something happened → here is the protocol that caused it → here is an animation of exactly that exchange with your real devices."

**Effort:** S

**Files likely affected:**
- `ui/pages/log_hub_page.py` — clickable delegate cell
- `ui/pages/protocol_viz_page.py` — `load_from_event()` method
- `ui/dashboard.py` — navigation wiring

---

### 3-C: Live Lab injection from logger events ✅ v1.7.0

**Description:** When the network logger detects an interesting event (new device, ARP change, DNS latency > 200 ms, FAIL streak ≥ 3), a flag is set on Dashboard. The Home page "What to do next" suggestions strip shows a new amber card: "Something just happened — investigate it." Clicking opens Lab Mode with a dynamically-generated one-step `LabScenario` built from the real event using the existing `LabScenario` / `LabStep` dataclasses. New method: `LabModePage.inject_live_challenge(scenario)`.

**Why it matters:** Transforms the protocol visualizer from "watch a scripted animation" to "here is what ARP looked like on your network 2 minutes ago — now figure out what it means." Bridges passive logging → active learning.

**Effort:** M

**Files likely affected:**
- `ui/pages/log_hub_page.py` — event detection and flag emission
- `ui/pages/lab_mode_page.py` — `inject_live_challenge()` method
- `ui/dashboard.py` — route live challenge signal to lab mode + suggestions strip

---

## Priority 0 — Feature Wiring

These features have backend workers and page UI but are permanently non-functional because no path exists for the user to configure them. The principle is absolute: a feature that cannot be activated from within the UI does not exist.

---

### FW-1: Service Heartbeat — target configuration UI ✅ Done

**Description:** `ServiceWorker` starts with `targets=[]` and `set_targets()` is never called. The Service Heartbeat page always shows an empty table and KPIs of "—". No user path exists to add a service to monitor.

Fix in three parts:
1. `ui/pages/service_page.py` — add inline "Add service" row (host input + port spinner + label field + "Add" button) above the table card. Each table row gets a "Remove" action. On every add/remove, emit `services_changed = pyqtSignal(list)` carrying the full updated `ServiceTarget` list. Persist the list to `QSettings("service_monitor/targets")` as a JSON array. On `__init__`, load from QSettings and populate the table. Apply RULE-UX5: QStackedWidget with page 0 = empty state + inline "Add a service to monitor" prompt, page 1 = content.
2. `app.py` — on startup, load `QSettings("service_monitor/targets")` JSON, deserialise to `[ServiceTarget(…)]`, call `svc_worker.set_targets(loaded_targets)`. Wire `window._service_page.services_changed.connect(svc_worker.set_targets)`.
3. `ui/pages/settings_page.py` (optional) — no change required; target management lives on the page.

**Why it matters:** A user who opens Service Heartbeat has no way to make it do anything. The feature is structurally dead on every install.

**Effort:** S

**Files:** `ui/pages/service_page.py`, `app.py`

---

### FW-2: TLS Certificate Monitor — target configuration UI ✅ Done

**Description:** Identical structural gap to FW-1. `CertWorker` starts with `targets=[]` and `set_targets()` is never called. The TLS Certificate Monitor page always shows an empty table.

Fix in three parts:
1. `ui/pages/cert_page.py` — add inline "Add host" row (hostname input + optional port list input + "Add" button) above the table card. Each table row gets a "Remove" action. Emit `certs_changed = pyqtSignal(list)` on every change. Persist to `QSettings("cert_monitor/targets")` as JSON. Load on `__init__`. Apply RULE-UX5: empty state with "Add a hostname to monitor its TLS certificate" prompt.
2. `app.py` — load `QSettings("cert_monitor/targets")`, deserialise to `[CertTarget(…)]`, call `cert_worker.set_targets(loaded_targets)`. Wire `window._cert_page.certs_changed.connect(cert_worker.set_targets)`.
3. No change to the worker or monitor module — `set_targets()` already exists.

**Why it matters:** Same as FW-1. A user who navigates to TLS Certificate Monitor has no way to add any hosts. The page has been in nav since v1.6.7 and has never been functional.

**Effort:** S

**Files:** `ui/pages/cert_page.py`, `app.py`

---

### FW-3: REST API — complete and gated endpoint reference ✅ Done

**Description:** Settings → REST API has a partial endpoint label (lines 528–536 of `settings_page.py`) that lists `/health`, `/devices`, `/alerts`, `/uptime/<ip>`, `/speed-history` but is missing `/dashboard` and `/grade` (both added in v1.6.8). The label is always visible regardless of whether the API is enabled, which makes it noise when disabled. There are no clickable or copyable full URLs.

Fix:
1. `ui/pages/settings_page.py` — replace the static `ref_lbl` with a `_build_endpoint_table()` helper that generates a compact two-column widget (GET path | full URL with current port). Include all 7 endpoints: `/health`, `/dashboard`, `/devices`, `/alerts`, `/uptime/<ip>`, `/speed-history`, `/grade`. Show the widget only when the API is enabled — hide/show it in `_update_api_status_label()`. Each row's URL label uses `setTextInteractionFlags(TextSelectableByMouse)` so the user can copy it. Auth reminder stays below the table.
2. No change to the REST API module or worker.

**Why it matters:** A user who enables the API and wants to query `/grade` or `/dashboard` from another tool has to read the source code to find those endpoints. Two endpoints added five months ago are invisible.

**Effort:** XS

**Files:** `ui/pages/settings_page.py`

---

## Priority 0 — Discoverability

Every powerful feature that a user cannot find, understand, or act on is a feature that does not exist. This track fixes the discoverability layer — making the full surface area of the app reachable and self-explanatory without requiring documentation.

Implementation order: D-1 → D-2 → D-3 → D-4 → D-5.

---

### D-REST: REST API — discoverable outside Settings ✅ Done

**Description:** FW-3 fixed the endpoint reference inside Settings. But a user who never opens Settings → REST API card never knows the API exists. Two surfaces needed:

1. **Feature Guide** (`ui/pages/discover_page.py` → `_FEATURES` list): add a "Local REST API" entry — group "Advanced", icon `⬡`, description "A read-only HTTP API at `localhost:{port}` — query devices, alerts, uptime, and network grade from any script, browser, or tool.", action button "Open Settings →" that navigates to the Settings page. Always shown regardless of API enabled/disabled state.
2. **Home page strip** (already exists when API enabled in `ui/dashboard.py`): extend the strip text to say "REST API running — dashboard + 7 endpoints available" and add a "Settings →" button alongside the existing "Open ↗" button so users can reach the full endpoint reference from the home screen.

**Why it matters:** The API is invisible to any user who hasn't already opened the Settings page. FW-3 fixed the reference; this fixes discovery.

**Effort:** XS

**Files:** `ui/pages/discover_page.py`, `ui/dashboard.py`

---

### D-AWARE: Feature Guide entries for all configurable features ✅ Done

**Description:** Service Heartbeat and TLS Certificate Monitor now have inline add forms (FW-1, FW-2), but a user who never navigates there still doesn't know these features exist. Feature Guide entries make them discoverable.

Add two entries to `_FEATURES` in `ui/pages/discover_page.py`:
- "Service Heartbeat" — group "Monitoring", description "TCP port reachability checker — monitors whether your router, NAS, server, or any host:port is accepting connections. Add targets directly on the page."
- "TLS Certificate Monitor" — group "Monitoring", description "Tracks HTTPS certificate expiry for any hostname you specify — alerts you before certs expire. Add hostnames directly on the page."

Both get "Open →" navigation buttons. No badge needed (the pages are already reachable via nav).

**Effort:** XS

**Files:** `ui/pages/discover_page.py`

---

### D-1: Status bar tooltips ✅ Done

**Description:** Each of the four status bar pulse segments (`● Online`, `■ N devices`, `Last scan: Xm ago`, `○ Logger off`) gets a `setToolTip()` call explaining what it shows and that it is clickable. A user who hovers a segment for the first time immediately understands what it represents and where clicking takes them.

**Effort:** XS

**Files:** `ui/dashboard.py`

---

### D-2: REST API — access from other devices guidance ✅ Done

**Description:** Settings → REST API adds an inline info label after the external-access checkbox: *"To reach the dashboard from a phone or another computer, enable external access above and browse to `http://[this-machine's-LAN-IP]:[port]/dashboard` from that device."* The label auto-formats with the current port number.

**Effort:** XS

**Files:** `ui/pages/settings_page.py`

---

### D-3: Feature Guide page ✅ Done

**Description:** A new `ui/pages/discover_page.py` page listing every NetSentinel feature with icon, name, one-sentence description, "Open →" navigation button, and an optional "requires" badge (Npcap, admin). Features are grouped: Monitoring, Diagnostics, Security, Learning, Hidden features, Advanced. A filter bar at the top narrows by name or description. Registered in the Education section of all three nav modes and in home nav.

**Why it matters:** The canonical answer to "what can this app do?" — a user who opens it once has a complete mental model.

**Effort:** M

**Files:** `ui/pages/discover_page.py` (new), `ui/dashboard.py`

---

### D-4: Per-page contextual help ✅ Done

**Description:** Replaced the original 20×20 hidden `?` button with a persistent full-width tip bar (`_tip_bar`) below the breadcrumb. Always visible. Shows "ⓘ Tips for {page} ▾" when the page has content; clicking expands the panel. Shows "ⓘ Open Feature Guide →" and navigates there directly when no content exists. Auto-expands on first visit to 11 complex pages. `_PAGE_HELP` expanded from 12 entries to 50 covering every nav page in both Standard and Pro nav. Fixed two broken keys (`"Devices on Network"` → `"Devices"`, `"DNS & Outages"` → `"DNS & Stability"`).

**Files:** `ui/dashboard.py`

---

### D-5: Visited-feature tracking + persistent Home suggestions ✅ Done

**Description:** Dashboard tracks which page labels the user has visited via `QSettings("discover/visited_pages")`. The Home page "What to do next" strip always shows 2–3 feature cards for high-value pages the user has never opened. Cards rotate through an ordered list (Protocol Visualizer → Lab Mode → Network Grade → ISP Report → Connectivity Tests → Feature Guide). Once a page is visited, its card disappears from the strip permanently.

**Files:** `ui/dashboard.py`

---

## Priority 1 — De-facto Home Standard

Items in this track lower the barrier for non-technical users. Each item should be self-contained, require no configuration, and produce output that a non-technical person can act on immediately.

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

### Tier 2 — Structural polish

- **Skeleton loading rows while scan workers are running** — prevents layout jump when data arrives; use a `QStandardItemModel` with placeholder rows styled in `TEXT_MUTED`, swapped out when the worker emits results.

### Tier 4 — Nice-to-have

- **"Abyss" WCAG AA high-contrast theme** — fourth theme; true black background, high-contrast text, no low-opacity elements. Required for users with visual impairments.
- **Keyboard shortcut reference card in Help panel** — currently the shortcut list only appears in Settings.
- **Per-page documentation link** — small `?` link on each page header opening the relevant wiki section.
- **Passive 802.11 monitor mode capture** — optional advanced capture path that puts a supported NIC into monitor mode (via Npcap on Windows) and reads raw 802.11 management/probe/beacon frames, bypassing normal Ethernet capture. Primarily useful on networks with AP client isolation. Silently falls back to standard capture if unsupported. Pro-tier feature — too advanced and too NIC-dependent to be a home-user default.

---

## Completed

Most recent first.

### Unreleased — May 2026

**Help system overhaul (D-4 completion)**

- `_help_btn` (hidden 20×20 `?` in breadcrumb) replaced with `_tip_bar` — a persistent full-width `QPushButton(checkable)` below the breadcrumb; always visible; text updates per-page
- `_PAGE_HELP` expanded from 12 entries to 50, covering every nav page in Standard and Pro nav; fixed broken keys `"Devices on Network"` → `"Devices"` and `"DNS & Outages"` → `"DNS & Stability"` (they never matched any rail page label)
- `_AUTO_HELP_PAGES` frozenset — 11 complex pages auto-expand the tip bar on first visit (Logs, Lab Mode, Protocol Visualizer, Automation Hooks, MQTT / Home Assistant, TLS & Exposure, Service Heartbeat, SNMP Trap Receiver, Syslog Viewer, IoT Behaviour, Scheduled Scans)
- Pages with no tips show `"ⓘ  Open Feature Guide  →"`; clicking navigates to Feature Guide directly
- `_toggle_help_panel` gates on `_tip_bar_has_content`; uses `blockSignals` on page change so the panel collapses silently without firing the toggled signal
- `_nav_rail_go_to` checks `_AUTO_HELP_PAGES` before `_track_page_visit` — if first visit and page has content, calls `self._tip_bar.setChecked(True)`
- `"info"` Lucide SVG added to `_LUCIDE`

**Feature Guide expansion**

- `_FEATURES` in `ui/pages/discover_page.py` expanded from 24 to 44 entries; all entries have `tags` list for synonym search
- Added missing features: Overview, Speed Test, WiFi Heatmap, WiFi Networks, Network Map, Active Connections, ARP Spoof Watch, CVE Lookup, Threat Intel, IoT Behaviour, Automation Hooks, Scheduled Scans, MQTT / Home Assistant, Geolocation Map, Network Doc, IP Calculator, Tools & Wake-on-LAN, Hop-by-Hop Trace, and others
- `_apply_filter` now searches `name`, `desc`, `group`, `page` label, and `tags` — "heatmap" now finds WiFi Heatmap
- Fixed page refs that never matched nav labels: `"Devices on Network"` → `"Devices"`, `"DNS & Outages"` → `"DNS & Stability"`

**Bug fixes**

- `SettingsPage._endpoint_ref` crash at startup — `_update_api_status_label()` was called before `self._endpoint_ref` was created; moved call to after all widgets are built
- Rail button text clipping — removed `[:9]` truncation (caused "Automatio"); widened drawText rect from 10 px to 12 px (fixed descender clip on "Getting")
- Rail button text quality — replaced `QFont() + setPixelSize(8)` with `QFont("Segoe UI", 7)` + `TextAntialiasing` render hint
- Protocol canvas pill sizing — replaced hardcoded 228 px width with `QFontMetrics.horizontalAdvance()` measurement + 14 px padding; pill now fits snugly around text
- Protocol canvas label offset — `px_n * 18` → `px_n * 28` (pill no longer overlaps the arrow line)

---

**Navigation overhaul — permanent rail, full discoverability**

Mode switcher removed; the VSCode-style activity rail is now always visible and always shows the full feature set. Progressive disclosure is replaced by pinning (user self-selects), Ctrl+K (find anything), section labels, and red audit items.

- `_build_pro_nav()` is the sole nav builder; `_build_standard_nav()` kept as dead code path for QSettings compatibility
- `_nav_flat_panel.setFixedWidth(0)` — zeroes the legacy flat panel so it contributes no width to the layout
- "Quick Access" section renamed "Getting Started" — reflects that it is a curated entry point, not a user-customised shortcut list
- `_RailButton` height 48→58 px; `paintEvent` draws the section name (first word, 9 px, `QFontMetrics.elidedText`) below the icon — sections are legible without hovering
- Accent bar moved from QSS `border-left` (which shifted icon centre) to `paintEvent` overlay — icon stays perfectly centred in the 48 px icon zone
- Persistent search button (48×36, "search" SVG) pinned at the top of the rail above all section buttons; clicking it opens the Ctrl+K command palette; visible at all times
- Breadcrumb strip (`_breadcrumb_lbl`, 20 px QLabel) inserted above `_stack` in the content wrapper; updated on every `_nav_rail_go_to()` call with `"{Section}  ›  {Page}"`
- Pinning bug fixed: `_rebuild_nav_for_mode()` now injects a "Pinned" rail section (pin icon) at index 0 of `_nav_sections` when `_nav_pinned_labels` is non-empty; `_on_rail_pin_toggle()` calls `_rebuild_nav_for_mode()` after saving so the section appears and disappears immediately
- Security Audit rail button tooltip extended to explain why items are red: "require admin rights or run active probes against devices on your network"
- Flyout width bug fixed: `_FlyoutPanel.open()` calls `setMinimumWidth(280)` before animating, forcing the parent `QHBoxLayout` to allocate the full width; `close_panel()` resets to 0; bumped 260→280 px

**Home page discoverability**

- Dismissible browser dashboard strip — appears when REST API is enabled; "Open ↗" button, "×" dismiss; dismissal persisted via `QSettings("home/dashboard_strip_dismissed")`
- Dismissible Quick Tips card — four tips covering Ctrl+K, right-click pin, right-click device rows, REST API; REST API tip hidden when API already enabled; dismissal persisted via `QSettings("home/tips_dismissed")`

**Settings page**

- REST API status label is now a live HTML link; `setOpenExternalLinks(True)` on the label; `_update_api_status_label()` renders `<a href="http://localhost:{port}/dashboard">` in accent colour

**Network Logger improvements**

- Renamed "Stability Log" → "Network Logger" everywhere (nav labels, tab header, UI copy)
- File rotation: Off / 1 h / 6 h / 12 h / 24 h combo in the logger tab; `NetworkLogger` accepts `rotation_hours` and rolls to a new timestamped CSV segment; `LoggerWorker` emits `rotated(path, segment_n)` signal on each roll
- Network Logger and Education section added to Home mode nav — users no longer need to switch modes to reach them

**Other UX fixes**

- Maximize button: `_save_settings` now persists `window/maximized` as a separate bool; `_restore_settings` calls `showMaximized()` explicitly after `restoreGeometry()` — fixes the frameless-window ordering bug where the button showed maximize but the window was already maximised
- Flyout auto-close: flyout no longer closes on item click; closes only on canvas click (`_CanvasClickFilter`) or Esc (new `QShortcut`)
- Last-open rail section restored from `QSettings("nav/last_section")` on every startup

---

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
