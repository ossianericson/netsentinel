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
**Status:** Not started

**Rationale:** `DiagnosisPage` is one of the strongest features in the app but is buried and
technically framed. This sprint adds a new entry point that routes to existing tools — it does
not modify any existing page.

### Items

- [ ] **S3-1** Symptom-first landing — a "Troubleshoot" entry point accessible from the home
  page hero, system tray, and Ctrl+K presenting problems in user language:

  ```
  What's the problem?
  [ Streaming buffering/not working ]  [ Gaming lag or disconnects ]
  [ Slow internet                   ]  [ Device won't connect      ]
  [ WiFi keeps dropping             ]  [ Suspicious device on network ]
  [ A website or app isn't loading  ]  [ Something is using all my bandwidth ]
  ```

  This is a new page in the "Getting Started" section — it does not replace `DiagnosisPage`,
  it routes to it and to other existing tools.

- [ ] **S3-2** Symptom-to-diagnostic routing — each tile maps to a pre-configured diagnostic
  sequence using existing workers with pre-set parameters. No new diagnostic logic:
  - "Streaming buffering" → speed test + DNS latency + bandwidth + ISP ping
  - "WiFi keeps dropping" → WiFi signal survey + channel interference + ping stability
  - "Device won't connect" → DHCP scan + ARP scan + IP conflict check
  - "Something using bandwidth" → routes directly to App Traffic page, pre-run

- [ ] **S3-3** Symptom-aware findings language — diagnosis results present findings in the
  context of the symptom chosen. Not "DNS query time: 450 ms" but "DNS is slow (450 ms,
  normal is <50 ms) — this is likely causing your streaming service to stall between videos."
  The raw number stays. The context is added around it.

- [ ] **S3-4** "Is this my ISP or my router?" quick test — a dedicated 30-second test:
  ping gateway → ping ISP DNS → ping external DNS → ping Cloudflare → ping Netflix CDN.
  Returns a plain-English answer: "The problem is between your router and your ISP. Your local
  network is fine." Technical users will appreciate this too — it automates a standard
  diagnostic sequence. Add as a button on the DiagnosisPage and as a Ctrl+K entry.

- [ ] **S3-5** Promote DiagnosisPage everywhere — add a "Troubleshoot" CTA to: home page hero,
  system tray right-click menu, top Ctrl+K result when no query is typed, and the alert drawer
  for any alert. The page already does the right thing — it just needs to be findable.

- [ ] **S3-6** Symptom search aliases in Ctrl+K — "netflix not working" → streaming diagnostic,
  "why is my internet slow" → "Slow internet" tile, "new device appeared" → Devices page.
  All existing Ctrl+K entries unchanged; this adds aliases.

---

## Sprint 4 — Smart Alert Architecture

**Theme:** Alerts that explain themselves and know when to stay quiet
**Status:** Not started

**Rationale:** The alert pipeline, trend analyser, and availability monitor all exist independently
with no unified priority hierarchy, no resolution signal, and messages that are technically
accurate but not actionable.

### Items

- [ ] **S4-1** Alert resolution tier — add a **Healthy** (green) alert tier that is currently
  missing entirely. When a previous critical or warning alert resolves, fire a resolution
  notification: "Your internet is back — was down for 4 minutes." The full taxonomy:
  - **Critical** (red ✗): Something is broken now
  - **Warning** (amber ⚠): Something is degrading
  - **Info** (blue ●): Something changed
  - **Healthy** (green ✓): A previous issue resolved
  The resolution tier is the most impactful single addition — it tells users when they can
  stop worrying.

- [ ] **S4-2** Baseline learning window — first 7 days of monitoring establish normal baselines
  for: download/upload speeds, DNS latency, device count, bandwidth by time of day. After day 7,
  anomaly alerts fire when readings deviate >2 standard deviations from the user's own baseline.
  Transforms alerts from absolute thresholds to relative anomalies. Fewer false positives.
  Technical users will appreciate the OLS-regression approach this extends from `trend_analyser.py`.

- [ ] **S4-3** Alert consolidation with drill-down — if N devices (N > threshold) show the same
  failure simultaneously, surface a network-level summary: "5 devices lost connectivity — your
  internet may be down." But preserve individual device detail in an expandable section within
  the consolidated alert. Never lose the per-device information; just promote the summary.

- [ ] **S4-4** Plain-English alert format — every alert follows a strict template:
  ```
  [What happened] + [actual numbers] + [what it means] + [what to do]

  "Your internet speed dropped to 8 Mbps (normally 95 Mbps on this connection).
   This will affect streaming and video calls.
   → Run a full speed test to confirm  → Check if your ISP is having an outage"
  ```
  The raw numbers stay. The actionable steps are added.

- [ ] **S4-5** "All quiet" opt-in notification — user-configurable tray notification (default: off,
  suggested 8am) when no warnings or critical alerts fired yesterday: "Your network was healthy
  all day. 5 devices active, no issues detected." Opt-in only.

- [ ] **S4-6** Pattern-based suppression suggestions — build on `maintenance_window.py`. If the
  same alert fires at the same time 3 weeks in a row, offer: "This alert has fired every Tuesday
  at 2am for 3 weeks. Looks like a maintenance window — want to suppress it automatically?"
  Offer; never auto-suppress.

---

## Sprint 5 — Device Intelligence & People-Centric Inventory

**Theme:** Devices are people's things, not MAC addresses
**Status:** Not started

**Rationale:** The persistent device map is the foundation. This sprint builds the human layer
on top of it. All technical data remains visible — names and groups are added as an additional
layer, not a replacement for IP/MAC/OUI.

### Items

- [ ] **S5-1** Device naming with smart suggestions — when a new device appears, suggest a name
  based on: mDNS hostname, DHCP hostname, OUI vendor, device type. Suggestion appears as a
  toast: "New device: Apple iPhone (AC:DE:48) — tap to name it." Accepted names appear
  alongside (not instead of) the technical identifiers in the Devices table.

- [ ] **S5-2** Room/owner grouping — allow users to assign devices to user-defined groups:
  "Living Room", "John's devices", "IoT". The Devices page can filter by these groups via the
  existing pill filter bar. This is a human taxonomy on top of the existing subnet grouping —
  both coexist; neither replaces the other.

- [ ] **S5-3** Per-device health summary — each named device gets a status: Online / Offline /
  Slow / Unusual. The Devices page header shows "3 of your 12 devices are showing unusual
  behaviour" as a top-line summary. Technical details (which ports, what RTT) remain
  in the table rows exactly as-is.

- [ ] **S5-4** "Who is hogging bandwidth?" instant answer — a card on the home page and a
  prominent widget on the Live Bandwidth page: "Right now: John's MacBook is using 87% of your
  bandwidth at 94 Mbps." Requires per-device attribution from `app_traffic_worker.py` surfaced
  as a human-readable answer. The App Traffic page raw data is unchanged.

- [ ] **S5-5** Device behaviour change alerts — extend `iot_baseline.py` to all device types.
  Alert when a normally-inactive device starts making unusual connections: "John's old laptop
  (usually offline) just connected and is downloading 2 GB. Was this you?" Routes to the
  App Traffic page pre-filtered to that device.

- [ ] **S5-6** Per-device history timeline — for each named device, a timeline showing: when
  online, bandwidth used, any security findings. Accessible from right-click context menu on
  any device row. Additive — does not change the existing row layout.

---

## Sprint 6 — Traffic Context & Application-Layer Visibility

**Theme:** Show what the network is being used for, not just how much
**Status:** Not started

**Rationale:** Raw bandwidth numbers (94 Mbps) are meaningless without context. The existing
`app_traffic_classifier.py` and `AppTrafficPage` provide the raw data — this sprint turns
it into narrative that sits alongside the raw view.

### Items

- [ ] **S6-1** Traffic category dashboard — a chart on the App Traffic page showing bandwidth
  by application category (Streaming, Gaming, Video Calls, Social Media, Downloads, IoT) for
  the last 24 hours. Answers "where did all my bandwidth go?" Categories use plain names and
  icons; raw protocol/port data remains accessible in the existing table below.

- [ ] **S6-2** Per-device per-category breakdown — drill down from the category view: click
  "Streaming (48 GB this week)" to see which devices were streaming and which CDN ranges
  (Netflix vs YouTube vs Twitch based on destination IP ranges). No deep packet inspection —
  CDN IP ranges are sufficient.

- [ ] **S6-3** "Usage insights" card on home page — "Your household used 187 GB this week.
  Most was streaming (68%), mainly between 7pm and 11pm. Gaming traffic increased 40% vs last
  week." Data-driven, no interpretation beyond the numbers.

- [ ] **S6-4** ISP plan comparison — if the user has set their plan speed in Settings, traffic
  context includes plan utilization: "You used 12% of your monthly data cap." Optional — only
  shown if plan speed is configured.

- [ ] **S6-5** QoS recommendations — based on traffic patterns, surface: "Video calls and gaming
  overlap every weekday 9am–5pm. Consider QoS prioritisation for those devices. Here's how →"
  Generated deterministically from pattern analysis; shown once per pattern detected.

- [ ] **S6-6** Service status overlay — show known service status alongside local diagnostics:
  "Netflix reports no outages. Your local connection to Netflix is fine. Buffering is caused by
  bandwidth being shared with 3 other active devices." Uses service health data from
  `service_diagnostics.py`.

---

## Sprint 7 — Contextual Guidance Layer

**Theme:** Guide new users to what they need without restructuring anything for existing users
**Status:** Not started

**Rationale:** The original plan proposed a dual-mode UI with a user-type questionnaire that
collapsed the rail to 4 sections and hid technical data behind expanders by default. This
fails the additive test: it takes away the information density and navigation structure that
technical users depend on, based on a self-declared persona that may be wrong.

The alternative: surface guidance contextually, make it opt-in, make it dismissible.
One UI for everyone. Guidance layers appear on top; they never replace or hide the data.

### Items

- [ ] **S7-1** First-visit context banners — each page gets an optional one-paragraph
  interpretation banner displayed the first time a user visits (tracked per-page via QSettings).
  Shows below the page header, above the content. Explains what the page shows and what to look
  for. Technical users dismiss it once and never see it again. Subsequent visits show no banner.
  Implementation: a thin dismissible strip, not a modal. Opt-out, not opt-in.

- [ ] **S7-2** Column quick-view preset — a "Quick / Full" toggle button in the Devices table
  header. Full (default) shows all columns including IP, MAC, OUI, risk score, open ports.
  Quick shows Name, Status, Device Type, Last Seen. The toggle is per-table, persists to
  QSettings, and defaults to Full. Technical data is never hidden by default; simplification
  is an explicit user opt-in.

- [ ] **S7-3** Contextual "learn more" inline links — in scan result rows and alert text, surface
  brief inline "what is this? →" links at the point of discovery. Click expands a JargonTooltip
  panel (the existing widget, extended with multi-paragraph content). Additive — existing rows
  unchanged; the link appears as a small inline icon.

- [ ] **S7-4** "Recently visited" rail shortcut — a pinnable "Recent" entry at the top of the
  Pinned section (already exists) that lists the last 3 pages visited. Helps new users retrace
  their steps. Rail structure and all 9 sections unchanged.

- [ ] **S7-5** Ctrl+K natural language aliases — extend the command palette to accept symptom
  queries and plain-English descriptions as aliases for pages. "Netflix slow" → Service
  Diagnostics, "who is online" → Devices, "is my internet ok" → Overview. All existing Ctrl+K
  entries unchanged; aliases are additive entries in the index.

- [ ] **S7-6** Mode-aware empty state copy — the `EmptyStateCard` renders different copy
  depending on what the page is for, not on a declared user mode. Device page empty state:
  "No devices found yet. Run a scan to discover what's connected — takes about 30 seconds."
  This is a copy improvement to existing cards, not a mode system.

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
