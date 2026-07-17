# Changelog

All notable changes to NetSentinel are documented here. The current version summary lives in [README.md](README.md#changelog); the full history is below.

---

### v2.1.34

**Added**
- `ui/widgets/protocol_canvas.py`: cinematic rendering overhaul for the Protocol Visualizer — curved bezier packet paths with fading motion trails, arrival pulse rings, staggered broadcast rings, role glyphs, a backdrop dot-grid, a step-progress strip, and a 0.5x/1x/2x speed toggle
- `ui/widgets/frame_anatomy_panel.py` + `modules/protocol_frames.py`: collapsible Frame Anatomy inspector on the Protocol Visualizer — real layered Ethernet/IP/UDP/TCP and per-protocol payload breakdowns across all 10 scene builders, using real scan data where available
- `ui/widgets/protocol_storyboard.py`: "Copy image" / "Save PNG..." canvas export and a "Storyboard" filmstrip export (one panel per animation step) for the Protocol Visualizer, plus a right-click context menu exposing all three actions
- `modules/live_protocol_feed.py` + `workers/live_protocol_worker.py`: LIVE MODE for the Protocol Visualizer (ARP/DNS) — watch real captured traffic animate on the canvas as it happens, behind `experimental/protoviz_live` (default off), gated by the same admin/Npcap capability pattern as `LldpWorker`

**Changed**
- Protocol Visualizer now defers construction behind `experimental/lazy_pages` like the other 10 deferred pages, buffering fed scan-context so the first-ever visit in a session still shows current data instead of an empty state
- Restored `ProtocolCanvas`'s own built-in minimum height (240px) on the Protocol Viz page — the richer canvas visuals no longer feel cramped under the page's old 120px override
- Removed two dead widget modules (`ui/widgets/overview_tile_monitor.py`, `ui/widgets/scan_summary_sheet.py`) that were bundled into the shipped exe via `NetSentinel.spec` but never imported anywhere — shrinks the installed exe, no behaviour change
- Refreshed stale test-count figures in `README.md` and `docs/architecture.md` (suite had grown to 5,469 tests across 411 files; docs still read 5,243/398 and 5,291/405 respectively)

**Fixed**
- `ui/widgets/device_detail_pane.py`: device history drawer's close button (Network Map, Devices/Inventory) — a bare Unicode "x" glyph silently failed to paint on native Windows text rendering; replaced with a QPainter-painted icon via a shared `_wire_close_icon()` helper
- `modules/smb_enumerator.py`: guarded `subprocess.CREATE_NO_WINDOW` (Windows-only) behind a `getattr(..., 0)` fallback in `_net_view_shares`/`_net_exe_enum`, matching the existing pattern in `service_diagnostics_probes.py`
- `ui/pages/home_page.py`: three dismiss buttons (browser-dashboard strip, delta banner, post-scan sheet) rendered as invisible tofu (U+FFFD replacement character) on native Windows text rendering — the file's close-glyphs had been mojibake since v2.1.13; replaced with the same painted-icon pattern used for the device drawer close button

---

### v2.1.33

**Added**
- `ui/pages/protocol_viz_page.py`: clickable "Steps" list on the Protocol Visualizer — click any step to jump directly to it, with two-way sync between playback and the highlighted row (closes claims-audit F-48)
- 802.11 EAPOL frame classification in `workers/wifi_monitor_worker.py` (F-16)
- SNMP CPU/load polling in `modules/snmp_poller.py` (F-69)

**Changed**
- Network Map: mesh-only Wi-Fi clients that never answer ARP (e.g. the scanning PC itself) are now synthesized once in `NetworkMapPage.render()`, so the Classic and Interactive (Cytoscape) maps always agree on the device set
- Login Test now shows real last-update timestamps for credentialed scans instead of a placeholder (F-78)
- OS Detection reuses prior port-scan results instead of re-scanning (F-72)
- SMB share risk flags now require anonymous visibility, not just a non-hidden share name (F-88)
- Microsoft Store builds now point users at the Store's own update page instead of GitHub/`winget upgrade`, which is disallowed for Store installs
- `BACKLOG.md` retired — the four items left unbuilt (F-56, F-14, F-68, F-74) now carry "considered, deferred" notes directly in `docs/internal/claims-audit.md`

**Fixed**
- `ui/widgets/overview_tile.py`: dropped the unsupported QSS `cursor:default` property (Qt has no such property; it warned on every stylesheet apply) in favor of `setCursor()`
- `ui/live_graph.py`: stopped repeated `ax.legend()` / `set_tight_layout` stderr warnings by only calling `legend()` when a labelled artist exists and using explicit `subplots_adjust` margins
- Home page pending-alerts row label: a mixed f-string/non-f-string `themed_ss()` template left an unparseable QSS brace, logging "Could not parse stylesheet of object QLabel(...)" on every startup while restoring the last scan; guarded by `tests/test_themed_ss_callable_braces.py`

---

### v2.1.32

Shutdown-stability fix. No user-facing features or settings changed.

**Fixed**
- Always-on background monitors (`syslog` / `SNMP-trap` receivers, the passive SSDP/mDNS observer, and scheduled posture probes) are now stopped when the app quits, before the hard `os._exit(0)`. They were created in `app.py` but never registered with `Dashboard.closeEvent()`, so a raw-socket receiver could be mid `recvfrom()` during process teardown and crash with `STATUS_ACCESS_VIOLATION` — or hang — on exit
- `SnmpTrapWorker`/`SyslogWorker` now close their socket in `stop()` to interrupt the blocking read immediately, and `closeEvent` drains these workers without `terminate()` — calling `TerminateThread` on a thread inside a raw socket / Npcap call is what corrupted the teardown
- Removed the dead post-`app.exec()` cleanup block in `app.py` (unreachable because `closeEvent` hard-exits first); relocated the hardware-integration poll-worker `closedown()` into `closeEvent`

---

### v2.1.31

Documentation-accuracy release. No user-facing features or settings changed.

**Changed**
- Refreshed stale test-count figures in `README.md` and `docs/architecture.md` (suite had grown to 5,243 tests across 398 files; docs still read 4,890/344 and 5,109/370 respectively)
- Logged the 2026-07-13/14 overnight chaos soak in `project-vision.instructions.md` — 9,729 UIA interactions across mild/moderate/wild laps (1,291 / 3,397 / 5,041), zero crash-log growth, zero exceptions, flat peak RSS (674 → 775 → 750 MB)

---

### v2.1.30

Window and accessibility fixes. The headline is a long-standing UI Automation fault at startup: NetSentinel is now correctly readable by screen readers (Narrator, NVDA) from the moment it launches.

**Added**
- `ui/uia_warmup.py` — forces UIAutomationCore's one-time lazy init during startup, from a context where the COM call it makes is legal

**Changed**
- **Aero Snap, Snap Layouts, Win+arrow, drag-to-snap, shake and native edge-resize now work** — the custom header is drawn into a REAL Win32 window with only the frame *painting* suppressed (`WM_NCCALCSIZE`), instead of the frameless `WS_POPUP` Windows never considered snappable. This is now the default for every Windows user; the `experimental/native_chrome` flag is gone rather than merely defaulted on, so a stale stored `false` cannot keep anyone on the old window (`ui/native_chrome.py`)

**Fixed**
- Screen readers and other UI Automation clients could not attach cleanly at startup — the first `WM_GETOBJECT` the process answered raised `0x8001010d` (`RPC_E_CANTCALLOUT_ININPUTSYNCCALL`), because UIAutomationCore's one-time init needs an outgoing COM call and Windows always delivers that message inside an input-synchronous `SendMessage`
- The maximize button covered the taskbar instead of docking to the work area
- The window no longer starts a title-bar's height (~32px) below where it was left, leaving a strip of bare desktop above the header

---

### v2.1.29

Ships Instant Theme Switching — clicking a theme swatch in Settings now restyles the whole running app immediately, no restart required. Closes out the multi-phase live-theme-conversion project (all `ui/` files now read theme tokens live).

**Changed**
- `_on_theme` (`ui/pages/settings_cards.py`) now always applies the theme live via `apply_theme()` — removed the `experimental/live_theme_switch` QSettings flag and the legacy restart-required path
- Theme picker description now reads "Takes effect immediately" instead of "restart the app to apply"

**Fixed**
- 802.11 Monitor page (`ui/pages/wifi_monitor_page.py`) crashed on both "Start Monitoring" and "Stop Monitoring" — `_set_status()` was passed a resolved colour value instead of the expected theme-token name, raising `AttributeError`
- Resolved a CodeQL `py/unused-global-variable` alert in `ui/pages/log_source_panel.py` — added an explicit `__all__` so its cross-module constants/helpers (consumed only via `log_hub_page.py`'s import) are recognised as public

---

### v2.1.28

Stability and architecture-hygiene release — a batch of resource-leak, thread-safety, and data-correctness fixes, plus enforcement of the three-layer UI/data/module separation (ARCH RULE 1). No new features.

**Changed**
- Enforced the three-layer architecture boundary (ARCH RULE 1) — all UI writes to `MetricStore` now route through the module layer, `modules/settings_io.py` is PyQt-free, and the UI no longer imports `modules/alert_engine.py`

**Fixed**
- Closed leaked sockets, subprocesses, and child processes on error/timeout paths — across the discovery/enumeration modules, the STP/broadcast-storm scan, the DNS zone-transfer (AXFR) socket, and the Ookla CLI speed-test child
- Moved `netsh` firewall block/unblock calls off the GUI thread so a firewall action no longer stalls the UI (RULE 4)
- Stopped the vendor-lookup worker cooperatively instead of `terminate()`, and guarded against scan re-entrancy destroying in-flight workers
- Coalesced `HistoryPage` refresh requests so concurrent refresh workers no longer pile up
- Preserved `known_device.ip` on a vendor-only upsert and preserved unset fields on a partial `save_device_annotations` update, closing two silent data-loss paths
- Translated five raw worker-exception error slots into plain English (RULE-A2)
- Marked failed toast deliveries as `FAILED` rather than `DELIVERED`, logged previously-silenced snooze-registry failures, hardened notification strings, and fixed a scan status that could stay stuck on "Running"
- Dropped `NEW_OPEN_PORT` from the Security Audit acknowledge scope and routed audit dispatch through the `NavLabel` enum

---

### v2.1.27

Polish and stability release — sharpens the two built-in themes for contrast, fixes an intermittent startup COM-reentrancy fault, speeds up first paint, and repairs a CI gap that was silently hiding most of the test suite. No new features.

**Changed**
- Kept the theme lineup at two polished options (`Arctic Clean` light, `Midnight Pro` dark) and folded in the only measurable clarity wins from the experimental Sentinel palettes: `Arctic Clean` table headers deepened to indigo `#14205A` (white-on-header contrast 11.6→15.2:1) and `Midnight Pro`'s accent brightened to royal-blue `#3B82F6` (accent-on-card 4.32→4.63:1, now clears WCAG AA), with the full Midnight accent family (`SIDEBAR_SEL`, `BLUE`, `CHART_TITLE`, info/update-bar text) re-tinted to match
- Faster first paint — the Network Map's `WebEngine` view and the Threat Intel table now build lazily in `showEvent()` instead of during Dashboard construction; behind the opt-in `experimental/lazy_pages` flag, 10 leaf pages also defer construction until first shown
- APM instruction pipeline is now Claude-only — dropped the unused Copilot/Gemini targets and removed the generated `AGENTS.md`, `GEMINI.md`, and `.github/instructions/` outputs (dev tooling only)

**Fixed**
- Startup COM-reentrancy fault — the system-tray icon's `show()` and the remaining `Shell_NotifyIcon` call-outs are now deferred to `showEvent()` / guarded, stopping an intermittent `STATUS_ACCESS_VIOLATION` fault on some Windows machines (`ui/system_tray.py`, `ui/header.py`)
- CI was silently running only part of the test suite — a Dashboard test reaching `closeEvent()` → `os._exit(0)` terminated pytest early with a green exit; the offending Dashboard tests are now subprocess-isolated and `tests/test_suite_completes.py` guards against the regression, and the chaos-test focus guard was hardened to log and reclaim rather than skip
- `--tracemalloc` memory-soak launches again — tracemalloc now traces 1 frame and activates 3 s into the event loop instead of inline before `app.exec()`, so the window appears in ~11 s rather than timing out the soak harness (dev tooling only)

---

### v2.1.26

Internal tooling and dev-process release — consolidates monkey-test tooling into one budget-driven runner, closes a sleep/screensaver gap that could kill unattended chaos runs, repairs the APM instruction-compilation pipeline, and fixes a page-help popover that could get stuck open. No user-facing feature changes.

**Added**
- `logger/SPEC.md`, `logger/PLAN.md` — normative spec and phased build plan for a headless Raspberry Pi remote sensor logger feeding NetSentinel over MQTT (design-only, no code yet)
- `docs/chaos-testing.md` — documents the consolidated monkey-test workflow, linked from `docs/index.md` and `CONTRIBUTING.md`
- Memory-soak mode in `tools/run_all_monkey_tests.ps1` (`test.ps1 <hours> -Soak`) — after the first coverage cycle, runs one long-lived mild/moderate/wild process with `--tracemalloc` instead of restarting every few minutes, so slow memory leaks compound instead of resetting each cycle; `AI_REPORT.md` gains a Peak RSS column and embedded first/last tracemalloc snapshots

**Changed**
- Replaced 7 redundant `run_tests_*.bat`/smoke-test scripts with one budget-driven runner (`test.ps1 [1h|20h|blank]`) that cycles a coverage sweep plus 5 weighted chaos phases with rotating seeds and rewrites `AI_REPORT.md` after every phase
- Re-audited `docs/internal/future-features.md` against the current tree — moved 4 shipped items into a "Recently shipped" section, added Status notes to 10 partial items, corrected 2 factual errors

**Fixed**
- Page-help popover (`?` button) no longer gets stuck open after navigating to another page — `PageHeaderBar.hideEvent()` now auto-dismisses it; removed the unused "What can I do here?" tooltip-overlay feature (`ui/widgets/help_mode_overlay.py`)
- Chaos-test orchestrator no longer stalls indefinitely if the machine sleeps mid-run — `tools/test_setup.ps1` now holds `SetThreadExecutionState` for the entire run instead of relying on per-phase, admin-only `powercfg` calls that left every inter-phase gap unprotected
- APM governance pipeline: `netsentinel-apm.md` had the wrong filename suffix so its plan-first/stability rules silently produced zero generated output; restored as `session-workflow.instructions.md` and migrated 3 orphaned rule files (changelog, tests, pr-description) into the compiled pipeline

---

### v2.1.25

Internal maintainability release — an 8-part tech-debt backlog (P1–P8) drawn from a commit-history audit, closing the recurring bug classes the previous 90 commits kept re-fixing. No user-facing features or settings changed and behaviour is unchanged; all 4,875 tests pass (8 skipped). Each sprint shipped with its own ratchet test so the debt cannot silently regrow.

**Added**
- `ui/nav/labels.py` — a `NavLabel` registry giving every nav page label a single typed constant, replacing the raw string literals that were scattered across 23 files; `_nav_rail_go_to()` now logs a loud warning on an unknown label instead of silently doing nothing; guarded by `tests/test_nav_label_registry.py` (P1)
- `workers/base_worker.py` — a `BaseWorker(QThread)` base class with standard `result_ready`/`error`/`progress` signals, a templated `run()` that wraps an overridable `work()` in try/except, and a uniform `request_stop()`; 9 workers migrated onto it; guarded by `tests/test_base_worker.py` and `tests/test_worker_base_class.py` (P3)
- `tools/check_import_lint.py` — an import-hygiene gate (RULE-LINT5) catching CodeQL `py/import-and-import-from` and `py/cyclic-import`, neither of which ruff can detect; wired into `ci.yml` and the RULE-CI1 pre-push hook and guarded by `tests/test_import_lint.py` (P8)

**Changed**
- Converged all nav routing onto the `NavLabel` registry — migrated the four hand-maintained label copies (`_AUDIT_SCAN_LABELS`, `test_nav_completeness`, `discover_data.py`, and the nav builder) and the `navigate_to` wirings in `ui/tabs.py` onto the shared constants, so a page rename can no longer create a silent dead link (P1)
- De-forked `tools/systematic_test.py` — it now imports the blacklist / window-attach / click-guard machinery from `tools/monkey_test.py` (as the other chaos tools already did) instead of re-implementing it, so a safety fix lands once rather than needing to be applied in two places (P2)
- Consolidated shared network primitives into `modules/utils_net.py` — `tcp_probe()`, `get_arp_snapshot()`, and `parallel_map()` replace 14 hand-rolled socket probes, 5 ARP-table reads, 3 rogue subprocess pings, and 14 inline `ThreadPoolExecutor` fan-outs; guarded by `tests/test_utils_net_ratchet.py` (P4)
- Converged 11 duplicated private `_table()` factories onto `ui.tabs_helpers._table()`, resolving their drift (grid lines, resize mode, edit triggers) once so every page's tables behave identically; guarded by `tests/test_table_factory_consolidation.py` (P5)
- Added a QSS recipe layer to `ui/styles.py` (`qss_label`, `qss_muted_label`, `qss_frame`, `qss_chip`, `qss_dismiss_button`) and migrated the three heaviest inline-style files (`home_page.py`, `overview_tile.py`, `settings_cards.py`) onto it; RULE-QSS3, guarded by `tests/test_qss_recipe_adoption.py` (P6)
- Trimmed `ui/dashboard.py` by extracting its self-contained tab builders into `ui/tabs_monitors.py`, `ui/tabs_help.py`, and `ui/export_mixin.py`, and decomposed the ~300-line `_on_m1_result` in `ui/scan_wiring.py` into named single-responsibility steps (P7)
- Extended `tools/check_import_lint.py` with a cross-file unused-global-variable check (RULE-LINT6) and tightened ruff's `dummy-variable-rgx` in `pyproject.toml` to match CodeQL's narrower exemption — closing two blind spots where a dead module-level global or an underscore-prefixed dead local slipped past local linting
- Refreshed the line-count and test-count figures in `README.md` and `docs/architecture.md` (~136,000 lines of Python, 4,875 tests across 343 files)

**Fixed**
- Resolved 46 pre-existing CodeQL `py/import-and-import-from` alerts across ~40 test files, 3 bundled plugins (`asus_plugin.py`, `netgear_plugin.py`, `openwrt_plugin.py`), and `geo_map_page.py` (P8)
- Resolved 4 more open CodeQL alerts — a dead `_log` global (`network_logger.py`), a dead `_cb` local (`snmp_poller.py`), and two unused-public-export false-negatives (`dashboard.py` `_color_for_level`, `nav/labels.py` `KNOWN_LABELS`) — plus 4 additional dead locals surfaced by the tightened lint config (`app.py`, `ui/tabs.py`, `ui/widgets/overview_tile.py`, `tests/test_coach_marks.py`)

---

### v2.1.24

**Added**
- Per-device "Alert me if this device goes down" / "Stop alerting on this device" toggle in the Devices/Inventory context menu (`MetricStore.set_device_alert_opt_in()`, `known_device.alert_opt_in` — schema v19)
- "Unresolved Security Alerts" card on Security Overview — lists unacknowledged security-relevant alerts with an inline "✓ Acknowledge" button per row, reusing `MetricStore.acknowledge_alert()`

**Changed**
- Device-health alerts (`HOST_DOWN`, `RTT_THRESHOLD`, `FLAP`, `JITTER_HIGH`, `RTT_ANOMALY`, `IOT_BEHAVIOR`, `TREND_FORECAST`, `IP_CHURN`, `LOSS_THRESHOLD`, `HOST_DEGRADED`) now fire only for infrastructure-role devices or devices the user has explicitly opted in — previously every device seen in a scan (including guest phones and transient IoT devices) could trigger these; genuine security events (`NEW_DEVICE`, `ARP_SPOOF`, `ROGUE_DHCP`, `NEW_OPEN_PORT`, `NEW_CVE`, `NEW_EXPOSURE`, `CONFIG_DRIFT`, `CERT_EXPIRY`, `CERT_EXPIRED`) remain unaffected by opt-in
- Security Audit rail badge now counts only security-relevant unacked alerts (`SECURITY_RELEVANT_RULE_TYPES`) instead of every unacked alert, so the badge number matches the new Unresolved Security Alerts list on Security Overview
- `MetricStore.record_alert_fired()` now persists a stable `rule_type` column (schema v19); `get_unacked_alerts()` accepts a `rule_types` filter
- Refreshed the line-count and test-count figures in `README.md` and `docs/architecture.md` (~135,000 lines of Python, 4,800+ tests across 330+ files)

**Fixed**
- `speed_tester.py`: the speed-test server-list fetch now retries with backoff and falls back to a last-good cache on failure
- Eliminated a parentless-widget startup flash in `hub_card.py` (Configure button) and `rest_api_page.py` (external-access warning) — widgets are added to their layout before visibility is toggled (RULE-WIN7); guarded by new `tests/test_widget_visibility_order.py`
- Resolved 7 open CodeQL alerts (unused imports/globals, mixed returns)

**Security**
- Hardened the hardware-plugin AI prompts, the plugin template wizard, and 8 bundled plugins against prompt injection

---

### v2.1.23

**Added**
- `modules/lab_badge.py` — renders a Lab Mode completion badge PNG (hexagon/shield motif, scenario title, completion date); new "Download Badge (PNG)" button on the Lab Mode result panel alongside "Try Again"/"Export Report (HTML)"
- `modules/diagnostic_card.py::build_card_data_from_diagnosis()` — quiet "Share this result" strip on the "What's Wrong?" result panel with "Copy as image"/"Copy as Markdown" buttons, shown on every completed run
- `MetricStore.query_previous_grade()` — Network Grade tab now shows a "Your grade improved — share it" strip with "Copy as image"/"Copy as Markdown" buttons, but only on a genuine score improvement between the last two grade runs
- "Copy as Reddit post" and "Copy as email to ISP" buttons on the ISP Accountability Report, reusing `report_isp.generate_isp_complaint_text()` and the new `forum_export.build_isp_forum_markdown()`

**Fixed**
- `ui/styles.py`: added an `alpha()` helper and swept ~60 QSS sites that appended hex alpha as `{COLOR}22` — Qt parses 8-digit hex as `#AARRGGBB` (alpha-first), which scrambled those colours (mostly rendering invisible hover tints, and the Home "live challenge" banner as an opaque dark red); guarded by new `tests/test_qss_hex_alpha.py` (RULE-QSS2)
- `home_page.py`: the Home "live challenge" banner now renders as translucent amber via `AMBER_BG` instead of dark red
- `header.py`: the top-bar "▶ Scan" button now reads as a solid primary button at rest instead of being invisible until hover; the gear and time-range controls use a faint `alpha(WHITE, …)` hairline border so they no longer draw a harsh white box on the dark header bar in Arctic Clean
- `home_data_mixin.py`: the live-challenge banner now leads with the event's own wording (e.g. `New device detected`) instead of labelling every Network Logger event a "Connectivity issue"

---

### v2.1.22

**Added**
- `modules/report_sanitizer.py` — shared sanitizer for public sharing: aliases private IPs to stable `192.168.1.N` placeholders, strips MAC addresses/hostnames, and omits public IPs entirely; makes no network calls
- `modules/forum_export.py` — builds sanitized, forum-ready Markdown summaries for `DiagnosisPage` ("What's Wrong?") and `ServiceDiagnosticsPage` results; wired to new "Copy for Reddit/Discord" buttons on both pages
- `modules/topology_share.py` — renders a sanitized Network Map PNG independently of the on-screen view, so a new "Share (Sanitized PNG)" toolbar button on `NetworkMapPage` can never leak real IPs/MACs/hostnames
- `modules/service_escalation.py` — a `SERVICE_DOWN` heartbeat failure now triggers a background `DiagnosticEngine` probe and a follow-up notification classifying *why* the service is unreachable (filtered by a firewall/VPN/ISP vs. a genuine outage); new "Diagnose why (recommended)" sub-toggle under the `Service Down` alert rule
- `modules/proactive_digest.py` / `workers/proactive_probe_worker.py` — reusable due-check/day-tracking base (used by Morning Briefing) and a generic interval-loop `QThread` for future background probes
- `modules/scheduled_speed_test.py` and a new `BASELINE_DROP` `AlertRule` type — opt-in "Automatic Speed Tests" card on the Speed Test page (1h/3h/6h/12h/24h interval) fires a tray notification when download speed drops severely against your own rolling history, reusing `speed_drop_detector`'s verdict/copy
- `modules/digest_bullets.py` — Morning Briefing now summarizes overnight `SERVICE_DOWN` escalations and `BASELINE_DROP` speed trends, each gated on the corresponding feature's own opt-in state, capped at `MAX_BULLETS` with a "+N more" suffix
- Recurring daily "quiet hours" maintenance windows (`modules/maintenance_window.py`) — suppress scheduled speed tests and their notifications overnight without pausing the underlying heartbeat/monitoring data collection

**Changed**
- `MaintenanceWindowManager.record_suppression()` is now wired into `AlertEngine` via a new `set_suppression_recorder()` hook, so suppressed alerts actually appear in the maintenance suppression log
- `modules/alert_engine.py` maintenance-checker logic split into a new `_MaintenanceSuppressionMixin` (in `modules/alert_suppressor.py`) to stay under the 600-line module budget
- `modules/device_stability.py` and `modules/device_tracker.py` no longer call `MetricStore._execute_write()`/`_execute_read()` directly — all device inventory writes/reads (IP history, annotations, change-event audit trail, stability scoring, topology snapshots) now go through new public `MetricStore` methods; same for `modules/topology_snapshot.py` and the `/devices`/`/uptime` routes in `modules/rest_api.py`
- `modules/metric_store.py` split: device-inventory write methods (`record_ip_observation`, `upsert_known_device`, `record_device_state`, etc.) moved to new `modules/metric_store_writes_device.py` (`_DeviceWritesMixin`) to stay under the module LOC budget

**Fixed**
- Startup flash of a native OS-decorated window (title bar + min/max/close) for a fraction of a second: `ui/tabs_scan.py` (STP Capture / Broadcast Storm empty-state buttons), `ui/pages/home_page.py` (`setupCompleteCard`), and `ui/pages/log_source_panel.py` (Network Logger source-toggle buttons) were calling `.setVisible(...)` on a widget *before* it was added to its parent layout — Qt treats a still-parentless widget as an independent top-level window and gives it full native chrome. Fix: call `.setVisible(...)` only after `addWidget()`
- `device_ip_history.seen_count` no longer double-increments per scan: `ui/scan_wiring.py` was calling `record_ip_observation()` directly in the same handler where `DeviceTracker.process_scan()` (the intended single write path) also calls it, doubling `seen_count`/`scan_count` and skewing `ip_stability` every scan

---

### v2.1.21

**Added**
- `DiagnosticEngine.run_custom()` in `modules/service_diagnostics.py` — Service Diagnostics can now probe any typed hostname (e.g. `github.com`) via a "Custom host…" entry in the picker, not just the streaming/gaming catalog
- New `filtered` failure-layer classification: flags the ICMP-succeeds-but-TCP-fails signature of a firewall, VPN, or ISP silently blocking a connection, distinguishing it from a genuine `remote_outage`

**Changed**
- Navigation colour tokens extracted from hardcoded `rgba()` values into 8 named semantic tokens in `ui/styles.py` (`NAV_RAIL_HOVER_BG`, `NAV_RAIL_ACTIVE_BG`, `NAV_RAIL_FOCUS_BORDER`, `NAV_ITEM_HOVER_FG`, `NAV_ITEM_ACTIVE_FG`, `NAV_FLYOUT_FOCUS_BORDER`, `NAV_ITEM_PIN_HOVER_FG`, `CARD_BORDER`); Arctic Clean sidebar is now white chrome; `rail.py` `refresh_theme()` re-applies full QSS for live switching
- Badge/info-box/inline-warning/banner colours moved into per-theme palette dicts; Midnight Pro card background elevated to `#1C2128`; Arctic Clean canvas cooled to `#EEF2F7`

**Fixed**
- Dark-theme `BORDER` token (`rgba(255,255,255,0.08)`) crashed matplotlib (`ValueError: Invalid RGBA argument`) and silently rendered opaque black in `QColor`; new `CHART_SPINE` plain-hex token routes all non-QSS consumers (spines, edges, dividers, pens) safely
- Monitor resume banner and alert banners now render inside the content area only — both were inserted into the root `QVBoxLayout` and bled over the 48 px nav rail
- `setupCompleteCard` and `recurringIntroCard` now use semantic fill tokens (`GREEN_BG`, `INFO_BOX_BG`) instead of plain `BG_CARD`
- Arctic Clean active nav item text contrast raised from `#0078D4` (~3.7:1) to `#1F4E80` (~6.9:1, WCAG AA+)

---

### v2.1.20

**Added**
- `modules/scan_status_md.py` — renders the Security-Audit scan registry as a GitHub-flavoured Markdown table; "⧉ Copy as Markdown" button on the Security Overview `Scan Status` card copies a shareable status snapshot (tool, state, last-run age, finding) to the clipboard for tickets and email

**Changed**
- Theme lineup consolidated to two polished themes — `Arctic Clean` (light, cohesive cool-slate chrome) and `Midnight Pro` (dark); `Obsidian Neon` and `Abyss` removed. A saved theme that no longer exists falls back to `Midnight Pro` on next launch
- `ui/styles.py`: badge, info-box, inline-warning and IP-calculator cell colours are now theme-aware (moved into the per-theme palette dicts) instead of being baked for a single theme — fixes low-contrast "bar same as background" rendering on the non-design theme
- `Arctic Clean`: sidebar softened from near-black to a cohesive cool slate; primary accent refined from royal blue to slate blue (`#2C6CB0`)
- Monitor resume banner restyled to a neutral surface with a crisp green left accent (was a muddy translucent fill); dismiss `×` and "Stop all" now use visible neutral tokens
- New theme-aware `INPUT_BORDER` token raises form-field border contrast; "Forget Saved Password" recoloured to a destructive red treatment (amber reserved for warnings/stale state); health status card uses a crisp neutral border with a coloured left accent
- `tests/test_theme_consistency.py` extended with a WCAG-AA contrast gate over badge/info-box/inline-warning/banner foreground-on-background pairs and the input-border token, locking theme quality against regression
- Consolidated the APM governance layer (dedupe, de-rot, prune); hardened the chaos-test harness and pinned `wingetcreate`
- `ruff` requirement bumped to `>=0.15.20`

**Fixed**
- Credential loading repaired in 8 bundled hardware plugins
- `protocol_animator` and report charts now use embedded `Figure`/`Line2D` instead of the pyplot state machine
- Restore window focus after dismissing UI banners and cards
- Resolved 4 CodeQL `py/import-and-import-from` alerts in test files
- Untracked `NetSentinel.ini` temp file; ignore `NetSentinel.ini.*`

---

### v2.1.19

**Changed**
- `.claude/skills/check.md` — new session-start health-snapshot skill (`/check`)
- `.claude/skills/triage.md` — new bug triage skill (`/triage`) writes structured records to `.triage/`
- `.claude/skills/debug.md` — added Phase 6 "Improve" section: after every fix, evaluate whether a new `RULE-*` should be written while the mechanism is fresh

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
