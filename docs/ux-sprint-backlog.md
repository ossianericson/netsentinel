# NetSentinel UX & Product Strategy Backlog
## 10-Sprint Improvement Plan (Revised)

*Audit date: 2026-06-15*
*Revised: 2026-06-15 — second pass, additive-only constraint applied*
*Status: Planned — not started*

---

## Guiding Principle

Every item in this backlog must pass this test before implementation:

> **Additive or invasive?** — Does this add capability on top of what exists, or does it change
> the defaults that existing technical users already rely on?

Items that fail this test — nav renames, hiding data behind folds by default, mode-gating navigation — are not in this plan. The cost of breaking muscle memory and information density for technical users exceeds the benefit to new users in every case where a less invasive alternative exists.

**What we will not do:**
- Rename established nav sections. "Security Audit", "Extend", "Monitor" are already right. Renaming for the third time is churn.
- Hide technical data behind a "Details ▸" expander by default. Technical users came for the data.
- Add user-mode questionnaires that gate navigation. One rail for everyone.
- Add gamification framing (streaks, badges) to what should be factual metrics.

---

## Sprint Sequencing

```
Sprint 1 (Plain English Layer)
   └── Sprint 2 (Ambient Health) — home page needs language before adding health card
   └── Sprint 3 (Symptom Hub)   — troubleshooter needs plain language for its output
       └── Sprint 4 (Smart Alerts)   — alerts build on symptom routing and baseline
           └── Sprint 6 (Traffic Context) — enriches alert and bandwidth intelligence
Sprint 5 (Device Intelligence) — parallel to Sprints 2–4
Sprint 7 (Contextual Guidance) — depends on Sprint 1 language + Sprint 5 device model
    └── Sprint 9 (Onboarding) — onboarding uses the guidance layer from Sprint 7
Sprint 8 (Retention Features) — depends on Sprint 2 health card + Sprint 4 alerts
Sprint 10 (Polish & Accessibility) — runs last, validates all previous sprints
```

---

## Sprint 1 — Plain English Layer

**Theme:** Lay plain English on top of technical data — never instead of it
**Status:** ✅ Complete — 2026-06-15

**Rationale:** Non-technical users bounce not because the features are wrong but because they
can't map what they see to a problem they understand. The fix is annotation, not replacement.
No label, column, or page name changes — those are already right.

### Items

- [x] **S1-1** Jargon audit — added RTT, AXFR, CVE, CIDR, TTL to `data/glossary.json`;
  created `docs/jargon-dictionary.md` as translation reference for use in S1-3/S1-4.

- [x] **S1-2** Page subtitle strip — added `subtitle=` parameter to `PageHeaderBar`
  (56 px with subtitle, 40 px without; backward-compatible). Added one-sentence
  plain-English subtitles to 16 pages.

- [x] **S1-3** Expand `JargonTooltip` deployment — added `setToolTip()` for RTT/Jitter/ARP
  column headers in Network Logger, CIDR field in Inventory, AXFR button in DNS Zone page,
  and Avg RTT sub-label in the Overview tile.

- [x] **S1-4** Alert message rewriting — rewrote all 10 `alert_engine.py` message templates
  to plain-English formula: what happened + actual numbers + context + what to do. All raw
  technical data (host, IP, port, threshold, ms values) retained.

- [x] **S1-5** Risk level display translation — updated `_RISK_LABELS` in `tabs_helpers.py`
  (CLEAN → "All clear", STORM → "Critical — act now", HIGH → "Action required", etc.).
  Applied to verdict badge in `monitor_state.py` and storm level status in `scan_enrichment.py`.

- [x] **S1-6** Status indicator tooltips — added plain-English tooltips to UP/DOWN coloured
  `●` dots in the Service Heartbeat page.

---

## Sprint 2 — Ambient Health & Always-On Status

**Theme:** Answer "is everything OK?" in under 3 seconds without a scan
**Status:** ✅ Complete (2026-06-16)

**Rationale:** The single most frequent question is "is my network fine right now?" The app
currently cannot answer this without a user-initiated scan. This sprint creates a persistent
ambient answer built from always-on monitoring data that already exists.

### Items

- [x] **S2-1** Persistent network health score — `modules/health_score.py`: `HealthScoreCalculator`
  computes a weighted score (uptime 45%, latency 35%, alerts 20%) every 60 seconds from
  MetricStore data. Returns `HealthSnapshot` with `state` (green/amber/red/unknown), `score`,
  `headline`, `sub_text`, `checked_at`, `stable_hours`. Tests: `tests/test_health_score.py` (14 tests).

- [x] **S2-2** Home page daily status card — `ui/widgets/health_status_card.py`:
  `HealthStatusCard` full-width card. Large state icon (✓/⚠/✗/○), headline, sub-text,
  last-checked timestamp, score display, CTA button (state-appropriate label + page target).
  Inserted above suggestion strip in `home_page.py`.

- [x] **S2-3** System tray ambient health — `ui/system_tray.py`: `set_health(state, headline)`
  updates tray tooltip and icon tint. Wired in `app.py` via `health_worker.result_ready →
  window._tray.set_health(snap.state, snap.headline)`.

- [x] **S2-4** "All clear" explicit state — `HealthScoreCalculator._state_label()` produces
  plain-English headlines: green → "Network looks healthy" / "All clear — everything stable";
  amber → alert/latency-specific message; red → "Network needs attention". Tests cover
  `test_green_state_headline_is_all_clear`.

- [x] **S2-5** Background health polling wiring — `workers/health_worker.py`: `HealthWorker`
  (60s interval, `threading.Event` stop mechanism — race-condition-free). Started in `app.py`,
  gracefully shut down on exit. Signal wired to `home_page.on_health_update()` and
  `system_tray.set_health()`. Tests: `tests/test_health_worker.py` (6 tests).

- [x] **S2-6** Health score history sparkline — `_HealthSparkline` widget inside
  `health_status_card.py`. Persists hourly samples to QSettings (`ambient/health_history`,
  max 168 entries = 7 days). Coloured line segments reflect per-point state. "7d" label.
  Renders below main card content.

---

## Sprint 3 — Symptom-First Troubleshooting Hub

**Theme:** Start with the problem, not the tool
**Status:** ✅ Complete — 2026-06-16

**Rationale:** `DiagnosisPage` is one of the strongest features in the app but is buried and
technically framed. This sprint adds a new entry point that routes to existing tools — it does
not modify any existing page.

### Items

- [x] **S3-1** Symptom-first landing — new `TroubleshootPage` (`ui/pages/troubleshoot_page.py`)
  in the "Getting Started" section with 8 user-language symptom tiles. Does not replace
  `DiagnosisPage`; routes to it and to other existing tools.

- [x] **S3-2** Symptom-to-diagnostic routing — each tile routes via `diagnose_symptom` signal
  (→ `preset_symptom()` on DiagnosisPage) or `navigate_to` signal (→ Service Diagnostics,
  App Traffic, Devices). No new diagnostic logic.

- [x] **S3-3** Symptom-aware findings language — `_symptom_ctx_lbl` in `DiagnosisPage._build_done()`
  shows "You reported: My internet is slow" above the verdict card. Context set in `_show_result()`.
  Public `preset_symptom(key)` method added to `DiagnosisPage`.

- [x] **S3-4** "Is this my ISP or my router?" quick test — `modules/isp_vs_router_test.py`
  (5-hop ping chain) + `workers/isp_vs_router_worker.py` + "Quick test" button added to
  `DiagnosisPage._build_idle()` with inline result card.

- [x] **S3-5** Promote DiagnosisPage everywhere — "Troubleshoot →" CTA button added to
  `AlertDrawer` actions row (`ui/widgets/alert_drawer.py`). System tray and home hero already
  had CTAs (pre-existing).

- [x] **S3-6** Symptom search aliases in Ctrl+K — `TroubleshootPage` entry in `_FEATURES`
  (`ui/pages/discover_data.py`) includes rich `tags` list covering all symptom phrases
  (streaming, buffering, gaming, lag, slow, wifi, dropping, etc.). Palette pulls from `_FEATURES`.

**New files:** `modules/isp_vs_router_test.py`, `workers/isp_vs_router_worker.py`,
`ui/pages/troubleshoot_page.py`, `tests/test_isp_vs_router_test.py`,
`tests/test_isp_vs_router_worker.py`, `tests/test_troubleshoot_page.py`

**Sprint 4 planned queue:** Smart Alert Architecture — priority scoring, self-explaining alerts,
resolution tracking, maintenance-window improvements.

---

## Sprint 4 — Smart Alert Architecture

**Theme:** Alerts that explain themselves and know when to stay quiet
**Status:** ✅ Complete — 2026-06-16

**Rationale:** The alert pipeline, trend analyser, and availability monitor all exist independently
with no unified priority hierarchy, no resolution signal, and messages that are technically
accurate but not actionable.

### Items

- [x] **S4-1** Alert resolution tier — added **HEALTHY** (green) severity to `AlertEngine`.
  `is_resolution: bool` and `downtime_s: Optional[int]` fields added to `AlertFired` dataclass.
  Engine tracks `_host_down_since` / `_service_down_since`; fires HEALTHY alert on recovery with
  plain-English message including downtime duration ("Your internet is back — was down for 4 minutes").
  `alert_drawer.py` maps HEALTHY → GREEN colour. Tests: `tests/test_alert_resolution.py` (15 tests).

- [x] **S4-2** Baseline learning window — `modules/alert_baseline.py`: `BaselineLearner` computes
  7-day rolling mean/stddev for RTT, packet loss, download/upload speed. `Baseline.is_mature`
  property gates anomaly logic on `_MIN_SAMPLES = 30`. `BaselineMetric.anomaly_threshold(sigma)`
  and `low_threshold(sigma)` return absolute thresholds from personal baselines. Stdlib math only.
  Tests: `tests/test_alert_baseline.py` (12 tests).

- [x] **S4-3** Alert consolidation — `AlertEngine._consolidation_threshold` (default 5, configurable
  via `set_consolidation_threshold(n)`). When ≥ threshold hosts go down in one cycle, a single
  consolidated HOST_DOWN alert fires: "5 devices lost connectivity at the same time — this looks like
  an internet outage rather than a single device problem." Individual device alerts still fire below
  the threshold. Tests in `tests/test_alert_resolution.py`.

- [x] **S4-4** Plain-English alert format — `AlertEngine._ACTION_STEPS` class dict maps rule types
  to `[action, action]` lists. `_append_action(message, rule_type)` appends `→ Action1  → Action2`
  to every alert message. Applied to HOST_DOWN, SERVICE_DOWN, RTT, CERT_EXPIRY, and tracker results.

- [x] **S4-5** "All quiet" opt-in notification — `modules/quiet_notifier.py`:
  `check_and_maybe_notify(store, settings_get, settings_set)` queries recent alerts, returns
  `QuietResult(headline, sub_text, device_count, alert_count)` when enabled, hour matches, not
  already sent today, and no WARNING/CRITICAL alerts exist. HEALTHY alerts do not block quiet
  notification. Wired in `app.py` on startup. Default: off. Tests: `tests/test_quiet_notifier.py` (8 tests).

- [x] **S4-6** Pattern-based suppression suggestions — `modules/alert_pattern_detector.py`:
  `PatternDetector.find_suggestions(store)` indexes 21 days of WARNING/CRITICAL alerts by
  (rule_name, host, day_of_week, hour). Suggests suppression window when same pattern appears
  in 3+ distinct ISO weeks. Returns `SuppSuggestion` dataclass with day_name, window bounds
  (±30 min buffer), and human-readable description. Capped at 10 suggestions. Tests:
  `tests/test_alert_pattern_detector.py` (11 tests).

**New files:** `modules/alert_baseline.py`, `modules/alert_pattern_detector.py`,
`modules/quiet_notifier.py`, `tests/test_alert_baseline.py`, `tests/test_alert_pattern_detector.py`,
`tests/test_alert_resolution.py`

**Sprint 5 planned queue:** Device Intelligence — device naming, room/owner grouping, per-device
health summary, bandwidth attribution, behaviour change alerts, per-device history timeline.

---

## Sprint 5 — Device Intelligence & People-Centric Inventory

**Theme:** Devices are people's things, not MAC addresses
**Status:** ✅ Complete — 2026-06-16 (S5-4/S5-5 partially scoped, see notes)

**Rationale:** The persistent device map is the foundation. This sprint builds the human layer
on top of it. All technical data remains visible — names and groups are added as an additional
layer, not a replacement for IP/MAC/OUI.

### Items

- [x] **S5-1** Device naming with smart suggestions — `modules/device_naming.py`:
  `suggest_device_name(hostname, vendor, device_type)` priority cascade (real hostname >
  "vendor type" > vendor > type > generic fallback). Wired in `ui/scan_wiring.py`: the first
  new device per scan cycle gets an action toast — "New device: Apple iPhone (AC:DE:48) —
  name it?" — that opens the device drawer with the suggestion pre-filled in the existing
  User Label field (`_DeviceDrawer.load(mac, store, suggested_label=...)`); accepted names
  save via the existing `device_annotations.user_label` column and appear alongside (not
  instead of) MAC/IP in the Devices table. Tests: `tests/test_device_naming.py` (8 tests).

- [x] **S5-2** Room/owner grouping — new pill filter bar in `ui/pages/inventory_page.py`
  below the Segment bar, reusing the existing `device_annotations.location`/`.owner` fields
  (already editable in the device drawer). A "Room/Owner" combo box switches which dimension
  the pills group by; pills follow the same multi-select toggle pattern as the Segment bar
  and combine with it and the "Hide offline" filter. Hidden until at least one device has an
  assigned group. Tests: `tests/test_inventory_page.py`.

- [x] **S5-3** Per-device health summary — `modules/device_health_summary.py`:
  `classify_device()` derives Online/Offline/Slow/Unusual from data already on each scanned
  device (display_state freshness + internal risk_level) plus `get_recent_alerts()`, no new
  persisted columns. Top-line summary label ("3 of your 12 devices need attention" / "All 12
  devices look healthy") added to the Current Devices card header. Tests:
  `tests/test_device_health_summary.py` (14 tests).

- [x] **S5-4** "Who is hogging bandwidth?" instant answer — `ui/widgets/bandwidth_hog_card.py`
  (`BandwidthHogCard`) added to the Home page below the ambient health card; `AppTrafficPage`
  gained a `top_host_changed` signal emitting the top consumer's label/bytes/share each
  snapshot, wired in `ui/tabs.py`. Shows an empty-state CTA ("Open App Traffic →") until
  monitoring has been started at least once — deliberately does **not** auto-start packet
  capture (RULE 4 / least-privilege). **Deferred to a future sprint:** the equivalent
  prominent widget on the Live Bandwidth page itself (the home card covers the "instant
  answer" need; the Live Bandwidth integration is additional surface, not blocking).
  Tests: `tests/test_bandwidth_hog_card.py`, `tests/test_app_traffic_page.py`.

- [x] **S5-5** Device behaviour change alerts — `modules/iot_baseline.py`: extracted
  `_devices_to_monitor()` and dropped the `IOT_DEVICE_TYPES` filter so baselining and
  anomaly monitoring (NEW_DEST/NEW_PORT/METADATA_PROBE/SYN_SCAN/RATE_SPIKE) now cover any
  device with an IP+MAC, not only IoT types. IoT Behaviour tab copy updated to reflect the
  broader scope. **Deferred to a future sprint:** routing a behaviour-change alert straight
  to the App Traffic page pre-filtered to that device — the existing
  `_IOT_INVESTIGATE_TARGET` "Investigate →" routing still applies per alert type, just not
  device-filtered yet. Tests: `tests/test_iot_baseline.py` (new `TestDevicesToMonitor` class).

- [x] **S5-6** Per-device history timeline — `_DeviceDrawer` gained a Timeline section
  (`_rebuild_timeline()`) merging `device_event` state changes (JOINED/LEFT/UP/DOWN/...)
  with the `device_events` annotation-change audit log into one chronological list.
  Accessible via single-click on any Current Devices row, or right-click → "Edit Device /
  View Timeline →" — both call the new public `InventoryPage.open_device_drawer()`.
  Additive — existing row layout and right-click actions unchanged. Tests:
  `tests/test_inventory_page.py`.

**New files:** `modules/device_naming.py`, `modules/device_health_summary.py`,
`ui/widgets/bandwidth_hog_card.py`, `tests/test_device_naming.py`,
`tests/test_device_health_summary.py`, `tests/test_bandwidth_hog_card.py`,
`tests/test_app_traffic_page.py`, `tests/test_inventory_page.py`

**Sprint 6 planned queue:** Traffic Context & Application-Layer Visibility — picks up the
deferred Live Bandwidth widget (S5-4) and device-filtered App Traffic routing (S5-5) as part
of its existing scope (S6-1 traffic category dashboard, S6-2 per-device drill-down).

---

## Sprint 6 — Traffic Context & Application-Layer Visibility

**Theme:** Show what the network is being used for, not just how much
**Status:** ✅ Complete — 2026-06-16

**Rationale:** Raw bandwidth numbers (94 Mbps) are meaningless without context. The existing
`app_traffic_classifier.py` and `AppTrafficPage` provide the raw data — this sprint turns
it into narrative that sits alongside the raw view.

### Items

- [x] **S6-1** Traffic category dashboard — `app_traffic_sample` table added to MetricStore
  (schema v17); `AppTrafficPage` persists every snapshot via the new `traffic_sample_ready`
  signal (page never writes to the store directly — wired in `ui/tabs.py._on_app_traffic_sample`,
  ARCH RULE 1). New "LAST 24 HOURS BY CATEGORY" card queries
  `query_app_traffic_category_totals()` and renders a persistent horizontal bar chart; raw
  protocol/port table remains unchanged below it.

- [x] **S6-2** Per-device per-category breakdown — clicking a category bar calls
  `query_app_traffic_device_breakdown()` and `query_app_traffic_cdn_breakdown()` to show top
  devices and CDN share. `modules/cdn_ranges.py` classifies destination IPs into
  Netflix/YouTube/Twitch/Disney+ via static published IP prefix blocks (no DPI). CDN tag flows
  through `AppFlowEntry.cdn` from `AppTrafficSniffer._handle()`.

- [x] **S6-3** "Usage insights" card — `ui/widgets/usage_insights_card.py` (`UsageInsightsCard`)
  added to the home page below the bandwidth-hog card. `modules/traffic_insights.py`
  (`build_usage_insights`/`format_insight_summary`) composes the household narrative
  ("Your household used X this week. Most was streaming (Y%), mainly between A and B. Gaming
  traffic increased Z% vs last week.") from `query_app_traffic_category_totals_range()`.
  Empty-state CTA until App Traffic monitoring has collected data (RULE 4 — never auto-starts
  capture).

- [x] **S6-4** ISP plan comparison — new "Internet Plan" settings card
  (`SettingsPage._build_internet_plan_card`) with a monthly data-cap field
  (`traffic/monthly_cap_gb` QSettings key, 0 = disabled). `compute_plan_utilization()` appends
  "You used X% of your monthly data cap." to the Usage Insights card only when a cap is set.

- [x] **S6-5** QoS recommendations — `build_qos_recommendation()` detects overlapping busy hours
  between Gaming and VoIP traffic over the last 7 days (`find_category_overlap_window()`) and
  surfaces a dismissible suggestion row on the Usage Insights card; dismissal is keyed by an
  MD5 hash of the suggestion text in QSettings, so a materially different pattern reappears.

- [x] **S6-6** Service status overlay — `modules/service_bandwidth_overlay.py`
  (`build_overlay_note`) combines `ServiceDiagnosticResult.failure_layer == "none"` with
  `query_app_traffic_active_device_count()` to add "Netflix reports no outages... bandwidth
  being shared with N other active devices" to the Service Diagnostics summary card, only when
  diagnostics pass and other devices are actively generating traffic.

**New files:** `modules/cdn_ranges.py`, `modules/traffic_insights.py`,
`modules/service_bandwidth_overlay.py`, `ui/widgets/usage_insights_card.py`,
`tests/test_cdn_ranges.py`, `tests/test_traffic_insights.py`,
`tests/test_service_bandwidth_overlay.py`, `tests/test_metric_store_app_traffic.py`,
`tests/test_usage_insights_card.py`, `tests/test_service_diagnostics_page.py`

**Sprint 7 planned queue:** Contextual Guidance Layer — first-visit context banners, Quick/Full
column toggle, inline "learn more" links, Recent rail shortcut, Ctrl+K natural-language aliases,
mode-aware empty states.

---

## Sprint 7 — Contextual Guidance Layer

**Theme:** Guide new users to what they need without restructuring anything for existing users
**Status:** ✅ Complete — 2026-06-16

**Rationale:** The original plan proposed a dual-mode UI with a user-type questionnaire that
collapsed the rail to 4 sections and hid technical data behind expanders by default. This
fails the additive test: it takes away the information density and navigation structure that
technical users depend on, based on a self-declared persona that may be wrong.

The alternative: surface guidance contextually, make it opt-in, make it dismissible.
One UI for everyone. Guidance layers appear on top; they never replace or hide the data.

### Items

- [x] **S7-1** First-visit context banners — `ui/context_banners.py` (`should_show_banner`/
  `mark_banner_seen`, QSettings key `banner/<page_key>_seen`) + `PageHeaderBar.show_first_visit_banner(key, text)`
  in `ui/widgets/page_header.py`: a dismissible "ⓘ" strip below the title row, shown once per
  page then never again. Applied to the 16 pages that already carry a `PageHeaderBar` subtitle
  (Automation Hooks, App Traffic, DHCP Lease Inventory, What's Wrong?, CVE Tracker, Active
  Connections, DNS Zone Mapping, Lab Mode, Live Bandwidth, Auto-Report Generation, Network
  Timeline, SNMP Trap Receiver, Speed Test, Threat Intelligence, Troubleshoot, Predictive Trend
  Alerting). Tests: `tests/test_context_banners.py` (11 tests).

- [x] **S7-2** Column quick-view preset — `ui/widgets/column_visibility_toggle.py`
  (`ColumnVisibilityToggle`, QSettings key `columns/<table_key>`, default `full`). Wired into the
  Current Devices snapshot table in `ui/pages/inventory_page.py` (Quick = ●/Label/Hostname/Type;
  Full = all 9 columns including Segment/IP/MAC/Manufacturer/Risk). Tests:
  `tests/test_column_visibility_toggle.py` (7 tests).

- [x] **S7-3** Contextual "learn more" inline links — `ui/widgets/jargon_tooltip.py` gained
  `get_detail()`/`find_known_term()` (whole-word glossary match, underscore-tolerant for rule
  names like `ARP_SPOOF`) and a new `LearnMoreLink` widget + `_LearnMorePopover` (click → floating
  panel with definition + optional "what to look for" detail paragraph). `data/glossary.json`
  gained `detail` fields for ARP, CVSS, DHCP, CVE, RTT, TLS. Wired into `AlertDrawer` (auto-detects
  a glossary term in the alert's rule name/message) and `CvePage`'s inline CVSS row. Tests:
  `tests/test_jargon_tooltip.py` (+12 new), `tests/test_alert_drawer.py` (4 tests, new file).

- [x] **S7-4** "Recently visited" rail shortcut — a standalone "Recent" rail icon (log glyph,
  built fresh inside `_nav_finalize_rail()` in `ui/nav/builder.py`, not as a separately-pinned
  page entry) opens a flyout listing the last 3 distinct pages visited, MRU-tracked via
  `_track_page_visit()` → QSettings key `nav/recent_pages`. **Deviation from the original
  wording** ("pinnable entry at the top of the Pinned section"): the existing Pinned section only
  renders once 5 pages are pinned (≤4 pins render as direct rail stars instead), and the rail's
  `count()-2` insertion math for section buttons assumes exactly two fixed trailing widgets
  (stretch + Settings) — discovered this the hard way when an initial placement after Settings
  pushed every section button below the stretch spacer, visually relocating the whole 9-section
  rail to the bottom. Fixed by building the Recent button fresh inside `_nav_finalize_rail()`
  itself (same place sections/pins are rebuilt) instead of statically in `tabs.py`. Verified
  visually via `tools/debug_launch.py` + screenshot, then locked in with
  `tests/test_recent_pages_nav.py` (14 tests covering placement math, MRU order, and toggle
  open/close/pin behaviour).

- [x] **S7-5** Ctrl+K natural language aliases — added symptom-phrase tags to the existing
  `_FEATURES` entries in `ui/pages/discover_data.py`: "netflix slow" / "is netflix down" / etc.
  → Service Diagnostics, "who is online" / "who's online" → Devices, "is my internet ok" / "is
  everything ok" → Dashboard. No new palette entries — these are additive tags consumed by the
  existing substring-match search string in `_build_palette_items()`. Tests:
  `tests/test_nl_aliases.py` (5 tests).

- [x] **S7-6** Mode-aware empty state copy — retitled 9 `EmptyStateCard` instances that repeated
  the feature name (e.g. "Device Inventory") to the "No X yet" pattern with an inline time/effort
  estimate where the action is quick: Devices, Dashboard, Active Connections, Live Bandwidth,
  Configuration Baseline, DNS Zone Mapping, TLS Certificate Monitor, App Traffic, Device Uptime.
  Pages that already followed this pattern (CVE Tracker, 802.11 Monitor, Trend Forecasts,
  Timeline, SNMP Trap Receiver, Geo Map, Network Logger) were left unchanged. Tests:
  `tests/test_empty_state_copy.py` (3 tests, static source checks).

**New files:** `ui/context_banners.py`, `ui/widgets/column_visibility_toggle.py`,
`tests/test_context_banners.py`, `tests/test_column_visibility_toggle.py`,
`tests/test_alert_drawer.py`, `tests/test_recent_pages_nav.py`, `tests/test_nl_aliases.py`,
`tests/test_empty_state_copy.py`

**Architecture housekeeping:** `ui/nav/builder.py` budget in `tests/test_module_loc.py` raised
1400 → 1623 (actual 1423 + 200 margin) per the file's own documented split trigger (1500); no
split needed yet. `ui/widgets/column_visibility_toggle.py` added to the `ui/widgets/` layout
tree in `.apm/instructions/architecture.instructions.md` (RULE-APM1).

**Sprint 9 planned queue:** Onboarding Redesign — scan-first onboarding flow, scan-result-based
feature surfacing, contextual one-time discovery prompts, Feature Guide "Recommended for you",
"What can I do here?" help mode, extended-absence recovery banner.

---

## Sprint 8 — Retention & Daily Ritual Features

**Theme:** Give users a reason to open the app on a healthy day
**Status:** Not started

**Rationale:** Monitoring tools die when users only open them when things break. The goal is
to surface genuine value daily. All features in this sprint are opt-in or additive.
The one item cut from the original plan: the "health streak" counter. Presenting uptime as a
streak introduces gamification framing (Duolingo, Snapchat) to a professional tool. The same
data presented as a factual metric is fine and is covered by S2-4 and S8-6.

### Items

- [ ] **S8-1** Morning briefing — opt-in tray notification (configurable time, default off;
  suggested 8am) with a 3-bullet summary:
  - Network status: all clear / X issues
  - Anything new overnight: new devices, unusual activity
  - Quick stat: bandwidth used yesterday, last speed test result
  Clicking opens the home page daily status card.

- [ ] **S8-2** Quick-check floating window — keyboard shortcut (`Ctrl+Shift+H`) or system tray
  action that opens a compact 300×200 px floating window showing current health status and
  top finding, without navigating to the full app. Useful for users who want a glance without
  context-switching.

- [ ] **S8-3** Polished weekly network report — a narrative in-app card (and optionally emailed)
  using the existing `digest_builder.py` and `report_scheduler.py` infrastructure:
  ```
  Your Network Last Week
  ────────────────────────
  ✓  6 days 23 hours uptime (99.6%)
  ↓  Speed averaged 87 Mbps (plan: 100 Mbps)
  ⚠  2 new devices joined
  ●  Household used 203 GB — streaming was 68%
  ```

- [ ] **S8-4** Speed test trend history — a persistent multi-month trend line on the speed test
  page showing historical performance: download/upload over time, time-of-day patterns,
  30/60/90-day rolling averages. Technical users will appreciate the data density. Replaces the
  original streak counter concept with actual measurement data.

- [ ] **S8-5** Comparative speed test context — after every speed test, show: "This is your
  X fastest test in the last 30 days. Your monthly average is Y Mbps, down Z% from last month."
  Context makes isolated data points meaningful.

- [ ] **S8-6** "Nothing to report" home page state — when health score is green, no new devices,
  no anomalies, all services up: the home page explicitly says "Your network is healthy. No
  action needed." Clean, unambiguous, uncluttered. Monitoring tools should acknowledge when
  there is nothing to monitor.

---

## Sprint 9 — Onboarding Redesign

**Theme:** Get users to their first useful result in under 5 minutes
**Status:** Not started

**Rationale:** The existing onboarding addresses technical setup but doesn't show value first.
The revision: lead with the first scan result (tangible, immediate), then offer monitoring
setup, then leave technical configuration in Settings where it belongs.

Critically: no user-type questionnaire. Self-declared personas are unreliable and create
mode-confusion. Discover user type from behaviour instead.

### Items

- [ ] **S9-1** Scan-first onboarding — replace the technical setup wizard opening with:
  - Step 1: One button — "Scan my network" — run first discovery, show device count immediately
  - Step 2: Show health score for the first time with a one-sentence explanation
  - Step 3: "Set up your watchdog" — opt into morning briefing, name 1–2 found devices
  Technical configuration (SMTP, SNMP, API keys) is not part of this flow. It lives in
  Settings > Advanced and is prominently linked from the onboarding completion screen.
  Experienced users can skip the flow entirely and go directly to Settings.

- [ ] **S9-2** Scan-result-based feature surfacing — after the first scan, surface relevant
  features based on what was actually found rather than what the user declared about themselves:
  - Open ports found → link to Port Scan / CVE tracking
  - Unknown devices found → link to device naming and rogue device alerts
  - Slow DNS response → link to DNS monitoring and speed test
  This is behavioural discovery, not persona-declaration.

- [ ] **S9-3** Contextual one-time discovery prompts — surface relevant features when context
  calls for them, one time only per prompt, dismissible:
  - After slow speed test: "NetSentinel can track your speed over time. Enable speed history →"
  - After new unknown device: "Set alerts for unknown devices →"
  After dismissal or acceptance, prompt never appears again (QSettings key).

- [ ] **S9-4** Feature Guide prioritisation — the existing `FeatureGuidePage` (83 entries) shows
  a "Recommended for you" section at the top derived from scan history: features relevant to
  what was found. Already-used features are marked. No persona required — usage data drives this.

- [ ] **S9-5** "What can I do here?" help mode — a toggle (accessible from the ? button on any
  page) that overlays brief one-sentence descriptions on each interactive element of the current
  page. Click to activate, Esc to deactivate. Opt-in, ephemeral. Does not change the default
  view of any page.

- [ ] **S9-6** Extended absence recovery — if the app hasn't been opened in 7+ days, show a
  prominent "welcome back" card: what changed, any new devices, any alerts that fired. Extends
  the existing "Since you were last here" banner for longer absences.

---

## Sprint 10 — Performance, Accessibility & Polish

**Theme:** The finishing layer that makes the product feel professional
**Status:** Not started

**Rationale:** A technically excellent product that feels slow, inaccessible, or visually
inconsistent will not retain users. This sprint establishes non-functional quality standards
across all previous sprint deliverables.

### Items

- [ ] **S10-1** Navigation performance audit — measure and enforce sub-200ms navigation to every
  page for cached data. Profile the 10 slowest page initialisations. Add timing instrumentation
  to `_nav_rail_go_to()` and log any transition exceeding 150ms as a warning.

- [ ] **S10-2** Colour-blind accessible status indicators — current system uses red/amber/green
  as the primary channel. Add shape/icon differentiation alongside: ✓ healthy, ⚠ warning,
  ✗ critical. Colours remain; they are no longer the sole differentiator.

- [ ] **S10-3** Keyboard navigation completeness audit — verify every page, button, and table
  row is reachable via Tab/Shift+Tab. Full keyboard navigation on all pages including the
  activity rail.

- [ ] **S10-4** Empty state quality audit — every page that can be empty must follow the
  `EmptyStateCard` pattern: icon, one-sentence what/why, CTA button. "No data yet" with no
  further guidance is a dead end.

- [ ] **S10-5** Loading state consistency — every page that loads data asynchronously must show
  the skeleton loading pattern within 50ms of navigation. No page shows a blank white card
  while data loads.

- [ ] **S10-6** Theme consistency audit — validate all three themes (Arctic Clean, Midnight Pro,
  Obsidian Neon) across all 62 pages: text contrast ratios ≥ 4.5:1 (WCAG AA), no hardcoded
  colours, consistent card styling, consistent table header styling.

- [ ] **S10-7** In-app feedback entry point — accessible from the ? menu or Ctrl+K: "Something
  doesn't make sense / I can't find X / This looks broken." Submissions go to a local log file.
  No telemetry, no external calls. Users who want to report issues get a structured path.

---

## What Was Cut and Why

| Original item | Reason cut |
|---|---|
| S1-2 Nav rename pass ("Safety Check", "Deep Diagnostics", etc.) | Pure churn. Nav sections were already deliberately named. Third rename in the project lifecycle. Cost (broken muscle memory, docs, tests) exceeds benefit (marginal clarity for new users who learn nav labels within one session). Page subtitle strip (new S1-2) achieves orientation without renaming. |
| S7-1 User-mode questionnaire | Self-declared personas are unreliable; mode-gating navigation penalises users who choose the wrong option. Replaced by scan-result-based discovery (S9-2) and first-visit banners (S7-1 revised). |
| S7-2 Default to simplified view (technical data behind expander) | Inverts the information hierarchy that technical users depend on. Replaced by opt-in Quick/Full column toggle that defaults to Full. |
| S7-3 Simplified 4-section rail for Home User mode | Removing rail sections creates mode confusion and support burden. The 9-section rail is a strength. Replaced by contextual first-visit banners and Ctrl+K aliases. |
| S7-4 Column visibility locked by mode | Same issue as S7-3. MAC addresses and IPs should never be hidden by default on any device inventory tool. Replaced by per-user opt-in column preset. |
| S8-4 Network health streak | Gamification framing ("streak") is Duolingo/Snapchat language applied to a security tool. The underlying data (consecutive healthy days) is real and useful; it is covered by S2-4 (explicit all-clear state). Replaced by speed test trend history which is genuinely data-rich. |

---

## Success Metrics

| Metric | Current | Target |
|---|---|---|
| Time to answer "is my network OK?" | Requires scan (~30s) | Under 3 seconds (ambient health card, S2-2) |
| Time to identify bandwidth hog | Manual multi-page navigation | Under 10 seconds (home page widget, S5-4) |
| Time from symptom to diagnosis | 5+ minutes, requires expertise | Under 2 minutes via symptom hub (S3-1) |
| % of alerts with a clear next action | ~20% (technical messages) | 100% (enforced message template, S4-4) |
| Technical data hidden from default view | 0 pages | 0 pages (additive-only constraint) |
| Nav sections changed from current names | 0 | 0 (no renames in this plan) |

---

*Revised 2026-06-15 — additive-only constraint applied; dual-mode UI replaced with contextual guidance layer*
*Update items in place as sprints are completed*
