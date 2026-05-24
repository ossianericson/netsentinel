# NetSentinel — UX Product Backlog V4

## Product Owner Statement

V1 made NetSentinel work. V2 made it communicate. V3 made its features talk to each other.
V4 makes the app work *for* the user when they're not there.

Right now the app is reactive: it waits. The user must open it, click Scan, navigate to Alerts,
open a drawer, manually cross-reference CVEs with Inventory, then open another page to check
automation. Every insight requires the user to be the integration layer — connecting facts that
the app already has but hasn't assembled.

V4 closes that gap. Scans run on schedule. When an alert fires the drawer already has the
evidence: port scan, CVE matches, device history, all pre-fetched. The Home page tells you
what changed while you were away without clicking anything. Automation and Reports — pages that
exist and have real backends — earn their place in the nav. The app tells you when it itself has
a problem. Power users get structured search, a full export, and back-navigation that doesn't
lose context.

The test for V4: a user who was away for three days opens the app, and in under 30 seconds knows
exactly what happened, what needs attention, and that the app was working the whole time.

---

## Priority tiers

- **P0** — broken promises (feature exists, user cannot reliably use it)
- **P1** — proactive insight gaps (app has the data but makes the user assemble it)
- **P2** — orphaned features (page exists, is functional, but isn't connected to the main flow)
- **P3** — power-user and polish (completeness gaps that stop the product feeling professional)

---

## Implementation order

| # | Item | Title | Priority | Sprint | Status |
|---|------|-------|----------|--------|--------|
| 1 | SCHED-1 | Scheduled scan (daily / weekly / on-open) | P1 | 1 | ⬜ |
| 2 | SCHED-2 | Schedule status on Home freshness strip | P1 | 1 | ⬜ |
| 3 | SCHED-3 | Monitor auto-resume on launch (on by default) | P1 | 1 | ✅ |
| 4 | SCHED-4 | Weekly digest upgrade — full HTML email report | P2 | 1 | ⬜ |
| 5 | INTEL-1 | Alert drawer auto-investigation (eager async + skeletons) | P1 | 2 | ✅ |
| 6 | INTEL-2 | CVE → Inventory device count cross-link | P1 | 2 | ✅ |
| 7 | INTEL-3 | Port scan open port → CVE count badge | P2 | 2 | ✅ |
| 8 | INTEL-4 | Alert row → "Create automation rule" CTA | P2 | 2 | ✅ |
| 9 | HEALTH-3 | Consistent error state widget for all async-loading pages | P1 | 2 | ✅ |
| 10 | TOAST-1 | Toast notification system (bottom-right, 4s, stacked, undo) | P1 | 2 | ✅ |
| 11 | DASH-2 | "This week" summary card on Home | P1 | 3 | ✅ |
| 12 | DASH-3 | 7-day grade sparkline on Home | P2 | 3 | ✅ |
| 13 | TIMELINE-1 | Activity timeline page (primary nav under Analysis) | P2 | 3 | ⬜ |
| 14 | TIMELINE-2 | "Today at a glance" header on timeline | P2 | 3 | ⬜ |
| 15 | HEALTH-1 | App health panel in Settings | P1 | 4 | ⬜ |
| 16 | HEALTH-2 | Offline / no-LAN detection banner | P1 | 4 | ⬜ |
| 17 | HEALTH-4 | Config completeness card in Settings | P2 | 4 | ⬜ |
| 18 | AUTO-1 | Automation page in nav + running-rule health dot | P2 | 5 | ✅ |
| 19 | AUTO-2 | Automation health tile in Monitor Overview | P2 | 5 | ✅ |
| 20 | REPORT-1 | Reports page in nav, schedule + generate end-to-end | P2 | 5 | ⬜ |
| 21 | REPORT-2 | "Generate Now" → structured clipboard report | P3 | 5 | ✅ |
| 22 | POWER-1 | Log Hub structured search (field:value syntax) | P3 | 6 | ✅ |
| 23 | POWER-2 | Export all — ZIP of all CSVs from Settings | P2 | 6 | ✅ |
| 24 | POWER-3 | Command palette content search (device names / IPs) | P3 | 6 | ✅ |
| 25 | PERF-1 | Lazy page instantiation + startup splash | P2 | 6 | ⬜ |
| 26 | NAV-5 | Back breadcrumb on pages opened from alerts / popovers | P3 | 6 | ✅ |
| 27 | ONBOARD-1 | "Run first-time setup again" in Settings | P3 | 6 | ✅ |

---

## Sprint 1 — Proactive scanning

The app runs whether or not the user opens it. Scans happen on schedule. Monitors resume
automatically. The weekly digest is a real email, not a one-liner.

### SCHED-1 — Scheduled scan

**User moment**: User has been running NetSentinel for two weeks. They've never set up a
schedule. Every insight depends on them remembering to click Scan.

**What to build**: A background QTimer in `dashboard.py` that fires a full scan at a
user-configured time. Settings card "Scheduled Scan" with:
- Enable toggle (off by default)
- Recurrence: Daily / Weekly / On app open
- Time picker (HH:MM, only shown for Daily/Weekly)
- "Run now" button

Store config in QSettings (`schedule/enabled`, `schedule/mode`, `schedule/time`).
On dashboard init, if enabled and last-run-date < today, fire immediately (missed window).
Emit through the existing `_start_full_scan` path so all callbacks fire normally.

**Acceptance**: Scan runs automatically at configured time without user interaction. "Run
now" works in all modes. Missed scans fire on next launch.

**Files**: `ui/pages/settings_page.py` (new card), `ui/dashboard.py` (QTimer + missed-scan
check in `__init__`).

---

### SCHED-2 — Schedule status on Home freshness strip

**User moment**: User opens the app. The freshness strip shows "Last scan: 3 hours ago".
They don't know if the next automatic scan is in 20 minutes or 23 hours.

**What to build**: Extend the Home freshness strip with a third item: `Next scan: today 8:00 PM`
(or `On app open` / `—` if scheduling is disabled). Update whenever the schedule QSettings key
changes. Pull next-run time from the same QTimer calculation used by SCHED-1.

**Acceptance**: Freshness strip always shows next scan timing when scheduling is enabled.
Updates immediately if user changes the schedule in Settings.

**Files**: `ui/pages/home_page.py` (freshness strip layout), `ui/dashboard.py`
(emit signal after schedule change).

---

### SCHED-3 — Monitor auto-resume on launch

**User moment**: User closes the app with ARP Watch and DHCP Monitor running. Reopens it
next morning. Both are off. They have 8 hours of blind spot.

**What to build**: On dashboard close, persist the set of running monitors to QSettings
(`monitors/was_running` = comma-separated list of monitor keys). On next launch,
auto-start each monitor in that list before the user interacts. On by default; user can
opt out via Settings toggle "Resume monitors on launch".

Monitor keys: `arp`, `dhcp`, `storm`, `net` (logger), `modem`, `mesh`.

**Acceptance**: Monitors that were running at close are running 3 seconds after reopen
(network interfaces may take a moment). Toast confirms: "3 monitors resumed". Opt-out
toggle in Settings works.

**Files**: `ui/dashboard.py` (`closeEvent`, `_init_pages` resume block), `ui/pages/settings_page.py`
(opt-out toggle).

---

### SCHED-4 — Weekly digest upgrade — full HTML email

**User moment**: User receives the weekly digest. It says "7 alerts this week." They have
no idea what the alerts were, whether the grade improved, or if new devices appeared.

**What to build**: Upgrade `RECUR-2`'s digest notification from a plain-text one-liner to
a full HTML email body containing:
- Network grade this week vs. last week (letter grade + score delta)
- Top 5 alerts by severity (rule, host, timestamp)
- New devices since last digest (hostname / vendor / IP)
- CVE count (total tracked, new this period)
- Uptime % for the period (from MetricStore speed test / RTT data)

Generate HTML in `modules/notification_router.py` or a new
`modules/digest_builder.py`. Reuse the existing SMTP send path.
The "Generate now" button in Settings produces and sends the same HTML immediately.

**Acceptance**: Digest email contains all five sections with real data. Renders correctly
in Gmail and Outlook (inline styles only, no external CSS). "Generate now" sends within 5s.

**Files**: New `modules/digest_builder.py`, `modules/notification_router.py`
(wire digest_builder into the weekly timer), `ui/pages/settings_page.py` (Generate now).

---

## Sprint 2 — Alert intelligence + error foundation

When an alert fires the drawer has already assembled the evidence. Pages that fail
a data load show something useful, not a blank widget. Non-blocking feedback uses
toasts, not amber banners that fight for space.

### INTEL-1 — Alert drawer auto-investigation

**User moment**: Alert fires: "Port scan detected from 192.168.1.44". User opens the
drawer. There's the alert text. That's it. They now have to manually navigate to Port Scan,
Inventory, and Threat Intel — in that order — to understand what's happening.

**What to build**: When `AlertDrawer` opens for an alert that has a source IP, immediately
fire three async lookups (QThread or existing worker reuse):
1. **Device history** — `MetricStore.get_device_history(ip)`: first seen, last seen,
   scan appearance count, custom label if set
2. **Last port scan** — `MetricStore.query_port_scan_history(ip, limit=1)`: open ports
   from the most recent scan against this IP
3. **CVE matches** — `ThreatIntelDB.get_matches_for_ip(ip)`: CVE IDs + severity for this host

Show skeleton loaders (grey shimmer rows, same pattern as VISUAL-2 from V2) for each
panel while data fetches. Replace with real content on arrival. If lookup returns empty,
show the empty-state ("No port scan history for this IP — Run scan →" with a CTA).

Layout inside drawer below the existing content:
```
▼ Evidence   [auto-expanded]
  Device       192.168.1.44 · "Xbox Series X" · first seen 14 days ago · 23 appearances
  Open ports   80 (HTTP) · 443 (HTTPS) · 8080 (HTTP-alt)
  CVEs         CVE-2024-1234 High · CVE-2023-8821 Medium
```

Each section navigates on click (Device → Inventory row, Port → Port Scan, CVE → Threat Intel).

**Acceptance**: Evidence panel appears on every alert with a source IP. Data loads within 2s
on a warm DB. Skeleton rows visible while loading. Empty states correct when no data exists.
Click targets navigate correctly.

**Files**: `ui/widgets/alert_drawer.py` (Evidence panel + async fetch), `modules/metric_store.py`
(add `get_device_history(ip)` and `query_port_scan_history(ip)` if not present),
`modules/threat_intel_db.py` (add `get_matches_for_ip(ip)` if not present).

---

### INTEL-2 — CVE → Inventory device count cross-link

**User moment**: CVE page shows "CVE-2024-3094 (Critical) — OpenSSH backdoor". The user
has no idea if any of their devices are running the affected version. They manually scroll
Inventory comparing IP addresses.

**What to build**: In `cve_page.py`, each CVE row that has matched hosts (from
`ThreatIntelDB`) shows an amber chip: `3 devices ›`. Clicking the chip navigates to
Inventory and pre-filters to show only the affected IPs. Implement via the existing
`device_popover` → Inventory `select_device()` pattern, or directly call a new
`InventoryPage.filter_to_ips(ips: list[str])` method that sets the search bar text to
an IP-list filter and re-applies `_m1_apply_filter()`.

**Acceptance**: CVE rows with matched hosts show device count chip. Click navigates to
Inventory showing only affected devices. Filter is visible in search bar (user can clear it).

**Files**: `ui/pages/cve_page.py` (chip in row), `ui/pages/inventory_page.py`
(add `filter_to_ips()`), `ui/dashboard.py` (wire nav signal from CVE page).

---

### INTEL-3 — Port scan open port → CVE count badge

**User moment**: Port scan returns port 22 (SSH) on three devices. The user doesn't know
if any CVEs relate to the detected SSH service version. That cross-reference lives in a
different page.

**What to build**: In the Port Scan results table, add a "CVEs" column (rightmost). For
each row where a service is identified (SSH, HTTP, SMB, etc.), query `ThreatIntelDB` for
CVE count matching that service keyword. Render as a badge: `2 CVEs` in amber if count > 0,
or `—` if none. Clicking the badge opens `cve_page` pre-filtered to that service keyword.

Keep the query lightweight — a count query, not a full fetch. Run after the port scan
completes (not per-row during scan).

**Acceptance**: CVE badge appears in port scan results within 1s of scan completion.
Amber when CVEs found, dash when none. Click navigates correctly.

**Files**: `ui/pages/` wherever the port scan result table renders
(likely `ui/dashboard.py` `_build_recon_syn_tab`), `modules/threat_intel_db.py`
(add `count_cves_for_service(service: str) -> int`).

---

### INTEL-4 — Alert row → "Create automation rule" CTA

**User moment**: ARP flood alert has fired 12 times from the same device. The user knows
they want to auto-block that MAC or run a script — but there's no path from the alert
to the automation engine.

**What to build**: In `notifications_page.py`, add a right-click menu item on alert rows
in the Alert History table: "Create automation rule for this alert type". Clicking opens
`AutomationPage` and calls a new `prefill_rule(trigger: str, match: str)` method that
pre-populates the rule editor dialog with:
- Trigger: the alert's rule prefix (e.g. `ARP_FLOOD`)
- Match: the source IP or host from the alert

The dialog opens immediately — user confirms or edits, then saves.

**Acceptance**: Right-click on alert row shows "Create automation rule". Click navigates
to Automation and opens pre-filled editor. User can save or cancel without side effects.

**Files**: `ui/pages/notifications_page.py` (context menu), `ui/pages/automation_page.py`
(add `prefill_rule()`), `ui/dashboard.py` (wire nav + prefill signal).

---

### HEALTH-3 — Consistent error state widget for all async-loading pages

**User moment**: User opens Trend page. The worker fails silently (Wi-Fi just dropped).
The chart area is blank. Is it loading? Did it fail? Is there no data?

**What to build**: A reusable `_error_state_widget(message: str, retry_fn: callable) -> QWidget`
module-level helper (mirror of `_empty_state_widget` from V2). Shows:
- ⚠ icon (amber, 32px)
- `message` headline (e.g. "Failed to load trend data")
- "Retry" flat button that calls `retry_fn`

Apply to every page that performs an async data fetch and can fail:
`trend_page.py`, `speed_test_page.py`, `cert_page.py`, `service_page.py`,
`history_page.py`, `baseline_page.py`.

Each page already has a `_stack` (or equivalent) — add the error widget as a third
stack index. On worker error signal, switch to error index. Retry button calls the
same `_load` or `_refresh` method that the page uses on `showEvent`.

**Acceptance**: Any async page that fails a load shows the error widget, not blank.
Retry button triggers the normal load path. Error state clears on success.

**Files**: `ui/dashboard.py` or `ui/widgets/error_state.py` (helper), then each of
the six pages above.

---

### TOAST-1 — Toast notification system

**User moment**: User saves a device label. An amber banner appears at the top of the page
for 5 seconds. User clicks Export. Another banner. The page is accumulating coloured strips
that fight for space with actual content.

**What to build**: A `ToastManager` singleton overlay anchored to the bottom-right corner
of the main window. Toasts stack upward (max 3 visible; older ones pushed off). Each toast:
- Icon (✓ green / ⚠ amber / ✗ red) + short message (1 line, max 60 chars)
- Optional "Undo" button that calls a provided callback
- 4-second auto-dismiss with a subtle progress bar underline
- Manual dismiss via ×

API: `ToastManager.instance().show(message, level="info"|"warning"|"error", undo_fn=None)`

Replace amber banners used for non-critical feedback with toast calls:
- Device label saved (DEVICE-1)
- CSV export started / complete
- Automation rule saved
- Monitor resumed (SCHED-3 confirmation)
- Report generated

Leave in place: LOG-4 cap banner (requires user action), LOG-5 live challenge banner
(persistent until dismissed), Settings dirty guard.

**Acceptance**: Toasts appear bottom-right. Stack correctly. Auto-dismiss after 4s.
Undo fires callback when clicked. Existing amber banners that are non-critical now use toasts.

**Files**: New `ui/widgets/toast_manager.py`, `ui/dashboard.py` (create overlay on init),
then callsites listed above.

---

## Sprint 3 — The morning view

The Home page becomes the answer to "what happened while I was away." A timeline page
gives the full chronological record.

### DASH-2 — "This week" summary card on Home

**User moment**: User opens the app Monday morning. Home shows the current grade and
pending alerts. There's no summary of what happened over the weekend. They'd have to
manually cross-reference Notifications, Inventory, and CVE.

**What to build**: A card placed below the freshness strip and above the grade section,
always visible, titled "This week". Four stat chips in a row:
- `N alerts` (red if N > 0, grey if 0) — count of alerts in last 7 days
- `N new devices` (amber if N > 0, grey if 0) — MACs not seen before this week
- Grade delta: `Grade: B → A-` (green if improved, red if declined, grey if unchanged)
- `N CVEs tracked` (count from ThreatIntelDB, no delta needed)

Each chip navigates to the relevant page on click. Pull data on `showEvent` + after
each scan. Show skeleton loaders while fetching.

**Acceptance**: Card always visible. Stats load within 1s (DB queries). Click targets
navigate. Skeleton loaders visible on first load. Card updates after a scan completes.

**Files**: `ui/pages/home_page.py` (new `_this_week_card` widget + `_refresh_this_week()`).

---

### DASH-3 — 7-day grade sparkline on Home

**User moment**: Grade circle shows "A-". Is that an improvement? Has it been declining
for two weeks? The user has no reference point.

**What to build**: A small sparkline (80×24px, QPainter line chart) rendered beneath the
grade circle on the Home recurring layout. Pull the last 7 scan grade scores from
`MetricStore` (the `score` field already stored with each scan). Map letter grades to
numeric if needed (A=95, A-=90, B+=87, B=83, etc.). Draw a simple polyline; colour the
line green if the last point ≥ the first, red if declining.

Only shown in the recurring-user layout (after 5 scans, same condition as RECUR-1).

**Acceptance**: Sparkline renders below grade circle after 5+ scans. Colour reflects
trend direction. Tooltip on hover shows "7 days: A → A- → B+ → A-".

**Files**: `ui/pages/home_page.py` (new `_GradeSparkline` QPainter widget), `modules/metric_store.py`
(add `get_grade_history(days=7) -> list[tuple[datetime, float]]` if not present).

---

### TIMELINE-1 — Activity timeline page

**User moment**: User wants to understand a sequence of events — a device appeared,
then two alerts fired, then a CVE was flagged. That sequence lives across three pages
with no shared timeline.

**What to build**: New page `ui/pages/timeline_page.py`. Primary nav entry labelled
"Activity" in the Analysis section, between Monitor Overview and Diagnosis. Nav icon:
clock or list.

The page shows a reverse-chronological event feed, grouped by date ("Today", "Yesterday",
"Monday 19 May", etc.). Event types and their sources:

| Event type | Source | Icon |
|---|---|---|
| Scan completed | MetricStore scan history | 🔍 |
| Alert fired | MetricStore alerts | 🔔 (coloured by severity) |
| New device seen | MetricStore device first-seen | 📶 |
| CVE matched | ThreatIntelDB match log | ⚠ |
| Monitor started/stopped | QSettings monitor state log | ● |
| Speed test run | MetricStore speed test history | ⚡ |

Each row: icon · timestamp · description · optional navigate link.
Example: `🔔 14:32  ARP flood from 192.168.1.44 (Critical)  [View alert →]`

Load last 30 days on open. "Load more" button at bottom. Search bar to filter by
event type or keyword. Source filter chips: All / Scans / Alerts / Devices / CVEs.

Store monitor start/stop events in a new `timeline_event` table in MetricStore:
`(id, ts, type, description, metadata_json)`. Dashboard writes an event row when
monitors start/stop, scans complete, new devices are found.

**Acceptance**: Page loads in under 2s for 30 days of events. Groups by date. Filter
chips work. Navigate links route correctly. Monitor events appear in real time as
monitors start/stop during the session.

**Files**: New `ui/pages/timeline_page.py`, `modules/metric_store.py`
(new `timeline_event` table + `add_timeline_event()` + `get_timeline_events()`),
`ui/dashboard.py` (writes events on monitor start/stop + scan complete),
`ui/pages/discover_page.py` (add to Feature Guide), `_build_pro_nav()` (add nav entry).

---

### TIMELINE-2 — "Today at a glance" header on timeline

**User moment**: User opens the timeline. The full event list is useful but dense.
They want the 5-second summary first, then the detail.

**What to build**: A pinned header above the event list (not scrollable) showing the
summary for today:
- N events today
- Highest-severity alert today (rule + severity chip), or "No alerts" in green
- N new devices today
- Last scan time today, or "No scan yet today"

Render as a single-row info strip with four chips. Updates via the same `_refresh`
call that loads the event list.

**Acceptance**: Header always visible at top of timeline. Shows today's data only.
Updates when new events arrive during the session.

**Files**: `ui/pages/timeline_page.py` (header widget + `_refresh_today_header()`).

---

## Sprint 4 — App health and reliability

The app tells the user when it itself has a problem.

### HEALTH-1 — App health panel in Settings

**User moment**: Scheduled scan didn't run last night. The user has no idea whether the
scheduler is working, whether the background worker crashed, or whether the DB is locked.

**What to build**: New card in `settings_page.py` at the top of the maintenance section:
"App Health". Shows a table of background components:

| Component | Status | Last active |
|---|---|---|
| Scan scheduler | ● Running | Next: today 8:00 PM |
| ARP monitor | ● Running | 2 min ago |
| DHCP monitor | ● Stopped | — |
| Log Hub (net) | ● Running | 4 sec ago |
| Report scheduler | ● Idle | Last: Mon 08:00 |
| MetricStore DB | ● OK | — |

Dot colours: green (running/ok), grey (stopped/idle), red (error — worker thread dead
or last heartbeat > 2× polling interval).

Pull status from: monitor thread `is_alive()`, QSettings last-heartbeat timestamps
(each worker writes `heartbeat/{key}` on each poll cycle), `ReportScheduler.status()`.

"Run diagnostics" button fires a quick self-check of each component and refreshes the table.

**Acceptance**: Table shows real status for all components. Red dot if worker is dead.
Refreshes on page open. "Run diagnostics" updates within 3s.

**Files**: `ui/pages/settings_page.py` (new card), `ui/dashboard.py` (workers write
heartbeat QSettings key on each cycle — add one-liner to each worker callback).

---

### HEALTH-2 — Offline / no-LAN detection banner

**User moment**: User's switch rebooted. NetSentinel is running, monitoring is "active",
but nothing is actually reachable. The app gives no indication that its monitoring is blind.

**What to build**: A persistent amber strip (same height as LOG-5 challenge banner) shown
at the top of the main window content area when the LAN is unreachable. Detection: attempt
a `socket.connect` to the default gateway (pulled from `netifaces` or `subprocess ipconfig`)
every 30s. If three consecutive checks fail, show the banner:
`"No network connection detected — monitoring may be incomplete. [Retry ›]"`

The [Retry ›] button forces an immediate recheck. Banner auto-dismisses when LAN is
reachable again. If no gateway can be determined, skip detection (never show).

**Acceptance**: Banner appears within 90s of LAN going down. Dismisses automatically
when LAN comes back. Retry button triggers immediate recheck. Never shown if detection
cannot determine the gateway.

**Files**: `ui/dashboard.py` (LAN check QTimer, banner strip widget in main layout).

---

### HEALTH-4 — Configuration completeness card in Settings

**User moment**: User has been running NetSentinel for a month. They haven't configured
email alerts. They don't know that scheduling, CVE tracking, and the weekly digest exist.

**What to build**: Card at the top of Settings (above all sections): "Your setup — 3 of 6
features configured". Six feature chips, each green (configured) or grey (not configured):
- **Notifications** — green if any rule is enabled and an SMTP/webhook is saved
- **Scheduled scan** — green if SCHED-1 is enabled
- **Monitor auto-resume** — green if SCHED-3 is enabled
- **Weekly digest** — green if RECUR-2 opt-in is enabled
- **CVE tracking** — green if ThreatIntelDB has been populated at least once
- **Automation** — green if at least one automation rule is saved

Each grey chip is a link that scrolls Settings to the relevant card (or navigates to
the relevant page for Automation/CVE). Summary text below chips:
"Set up notifications to get alerted when something goes wrong →"
(only shown if Notifications is grey; take the highest-priority unconfigured item).

**Acceptance**: Card shows correct configured count. Chips reflect real QSettings/DB state.
Grey chip clicks scroll or navigate correctly. Recalculates on `showEvent`.

**Files**: `ui/pages/settings_page.py` (new card at top).

---

## Sprint 5 — Orphaned page integration

Automation, Reports, and other well-built pages earn their place in the nav and
connect to the rest of the product.

### AUTO-1 — Automation page in nav + health dot

**User moment**: Automation rules exist and run, but the page is hard to find.
Users don't discover it without reading the Feature Guide.

**What to build**: Confirm `AutomationPage` is registered in `_build_pro_nav()` under
a visible section (suggest: Analysis, after Monitor Overview). If already registered,
verify it appears for all user types. Add a green activity dot on the rail button
(`set_left_dot`) when at least one automation rule has triggered in the last 24 hours
(check via `AutomationEngine.last_triggered_within(hours=24)`).

Add `AutomationPage` to the Feature Guide `_FEATURES` list in `discover_page.py` if
not already present.

**Acceptance**: Automation nav entry visible in rail. Rail button shows green dot when
a rule triggered in last 24h. Feature Guide entry exists.

**Files**: `ui/dashboard.py` (`_build_pro_nav()`, `_push_monitor_pills`),
`ui/pages/discover_page.py`, `modules/automation_hooks.py`
(add `last_triggered_within(hours)` if not present).

---

### AUTO-2 — Automation health tile in Monitor Overview

**User moment**: Monitor Overview shows ARP, DHCP, Storm, and Port Scan tiles. The user
enabled two automation rules — there's no tile telling them whether automations fired.

**What to build**: New tile in `MonitorOverviewPage` between existing monitor tiles and
the grade tile: "Automation". Shows:
- N rules enabled / N total
- Last triggered: `rule_name · 4 hours ago` (or "No triggers yet")
- Status dot: green if any rule enabled, grey if none

Pull from `AutomationEngine.get_rules()` and `AutomationEngine.get_last_trigger()`.
Tile click navigates to Automation page.

**Acceptance**: Tile visible in Monitor Overview. Shows correct rule count and last
trigger. Navigates to Automation on click. Dot reflects enabled state.

**Files**: `ui/pages/monitor_overview_page.py` (new tile), `ui/dashboard.py`
(push automation state on `_push_monitor_pills` or `showEvent`).

---

### REPORT-1 — Reports page in nav, schedule + generate end-to-end

**User moment**: `ReportsPage` exists and has a real `ReportScheduler` backend. But
the page isn't surfaced in the nav and the "Generate Now" button may have an unverified
end-to-end path.

**What to build**:
1. Confirm `ReportsPage` is registered in `_build_pro_nav()` under Analysis.
2. Manually trace "Generate Now" → `ReportScheduler.generate()` → file written →
   success toast. Fix any broken links in the chain.
3. Add `ReportsPage` to Feature Guide.
4. Connect the output directory "Open folder ›" button to `QDesktopServices.openUrl`.

This item is primarily verification + wiring, not new UI.

**Acceptance**: Reports page reachable from nav. "Generate Now" produces a file and shows
a success toast. "Open folder" opens the output directory in Explorer. Feature Guide entry
exists.

**Files**: `ui/dashboard.py` (`_build_pro_nav()`), `ui/pages/reports_page.py` (fix any
broken path), `ui/pages/discover_page.py`.

---

### REPORT-2 — "Generate Now" → structured clipboard report

**User moment**: User wants to paste a quick network summary into a support ticket or
Slack message. The PDF report is too much; they need plain text now.

**What to build**: In `reports_page.py`, add a "Copy to clipboard" button beside "Generate
Now". This produces a plain-text structured summary (similar to FLOW-3 "Copy report" in
Diagnosis but for the full network state):

```
NetSentinel Network Report — 24 May 2026
Grade: A-  (↑ from B+ last week)
Devices: 14 online, 2 offline
Alerts (7 days): 3 critical, 8 high, 12 medium
CVEs tracked: 7  (2 critical)
Last scan: 24 May 2026 08:14
Monitors: ARP ✓  DHCP ✓  Storm ✗  Logger ✓
```

Copy to `QApplication.clipboard()`. Show "Copied ✓" flash on button for 2s (same
pattern as FLOW-3).

**Acceptance**: Button copies formatted summary. Content is accurate at time of click.
Button shows "Copied ✓" confirmation. No file written — clipboard only.

**Files**: `ui/pages/reports_page.py`.

---

## Sprint 6 — Power-user completeness

The last gaps that stop the product feeling professional to a power user.

### POWER-1 — Log Hub structured search

**User moment**: Log Hub has free-text search. User wants `source:arp ip:192.168.1.44`
to find all ARP events from a specific host. Free-text can't do that reliably.

**What to build**: Extend `log_hub_page.py` search bar to parse `field:value` tokens
before falling back to free-text match. Supported fields:
- `source:` — matches source chip key (arp, dhcp, storm, net, modem, mesh, snmp, syslog, plugin)
- `ip:` — substring match on the Host column
- `severity:` — matches severity label (info, warning, critical)
- Bare terms — match anywhere (existing behaviour)

Multiple tokens compose with AND. Token parsing: split on whitespace, detect `word:` prefix.
Show a one-line hint below the search bar listing available fields (only shown when bar is focused
and empty). Example: `source:arp  ip:192.168.x  severity:critical`

**Acceptance**: `source:arp ip:192.168.1.44` correctly filters to ARP rows from that IP.
Mixed field + free-text works. Hint text visible on focus. No regression on existing free-text search.

**Files**: `ui/pages/log_hub_page.py` (`_apply_filter` + token parser).

---

### POWER-2 — Export all — ZIP of all CSVs

**User moment**: User is filing a support ticket or migrating to a new machine. They want
everything. Currently they have to export from 4 different pages one at a time.

**What to build**: Settings → Maintenance card → "Export all data" button. On click,
opens a `QFileDialog` to pick a destination directory, then generates:
- `scan_history.csv` — all scan results
- `alerts.csv` — all alerts (last 90 days)
- `logs.csv` — Log Hub export (last 7 days, or date range from the same picker used by LOG-4)
- `speed_tests.csv` — all speed test results
- `cve_matches.csv` — all CVE matches from ThreatIntelDB

ZIPs all five into `netsentinel_export_YYYYMMDD.zip`. Shows progress toast while generating.
Success toast with "Open folder ›" undo action opens containing folder.

**Acceptance**: Button in Settings works. ZIP contains all five CSVs with headers. Progress
toast visible during generation. No crash on empty tables (write header-only CSV).

**Files**: `ui/pages/settings_page.py` (button), new `modules/exporter.py`
(orchestrates the five CSV writes + ZIP), `ui/dashboard.py` (pass store reference).

---

### POWER-3 — Command palette content search

**User moment**: User types "192.168.1.44" in the command palette. Currently gets zero
results — the palette only matches page names. They have to navigate to Inventory to find
the device.

**What to build**: Extend command palette results with a "Devices" section (shown only
when query looks like an IP or hostname — contains `.` or alphanumeric ≥ 4 chars). Query
`MetricStore` for devices matching the search term (IP, MAC, hostname, custom label).
Show up to 3 device rows: `📶 192.168.1.44 — Xbox Series X  [View in Inventory →]`.
Selecting a result navigates to Inventory and calls `filter_to_ips([ip])`.

Keep the existing page-nav results above the device results.

**Acceptance**: Typing an IP shows matching device rows below nav results. Selecting
navigates to Inventory with filter applied. Non-IP queries still work as before.

**Files**: `ui/dashboard.py` (command palette result builder — add device query section).

---

### PERF-1 — Lazy page instantiation + startup splash

**User moment**: User launches NetSentinel. There's a 2–3 second blank window before
anything appears. Internally, 40+ pages are being constructed simultaneously.

**What to build**: Convert `_init_pages()` in `dashboard.py` to lazy instantiation:
pages are constructed the first time the user navigates to them, not at startup.
Keep a `_page_cache: dict[str, QWidget]` — `_push_section()` checks the cache,
creates on miss. Critical pages (Home, Settings, Notifications) still init eagerly
so the first open is instant.

Add a startup splash: a frameless `QSplashScreen` showing the NetSentinel logo +
`"Starting…"` label. Show before `QApplication.exec()`, close when the main window
first becomes visible (connect to `QMainWindow.showEvent`).

**Acceptance**: Cold startup shows splash within 200ms. Main window appears noticeably
faster (target: under 1s to interactive Home). Pages that haven't been visited yet
don't cause any startup delay. First-visit delay for lazy pages is under 300ms.

**Files**: `ui/dashboard.py` (`_init_pages` → lazy cache, splash in `main.py` or
`app.py`), `main.py` (splash screen).

---

### NAV-5 — Back breadcrumb on deep-link navigation

**User moment**: Alert drawer "Log Hub →" link opens Log Hub. User is done. Pressing
Escape or Back goes… nowhere. They have to manually navigate back to Notifications.

**What to build**: Track a navigation stack in `dashboard.py` (max depth 5):
`_nav_history: list[str]` — each `_nav_rail_go_to()` call appends the previous page key.
Add a "‹ Back" label button in the title bar, left of the page title, shown only when
`_nav_history` is non-empty. Clicking it pops the stack and navigates to the previous page.

Also wire `Escape` key (when no modal/flyout is open) to trigger back navigation.

This is intentionally simple — no forward navigation, no breadcrumb trail beyond one level.

**Acceptance**: "‹ Back" button appears after any deep-link navigation. Click returns to
previous page. Escape works as back when no modal is open. Back button hidden on direct
rail click navigation (not a deep link).

**Files**: `ui/dashboard.py` (`_nav_rail_go_to`, title bar layout, `keyPressEvent`).

---

### ONBOARD-1 — "Run first-time setup again" in Settings

**User moment**: New user dismissed the setup checklist before completing it. There's
a "Reset dismissed notices" button in Settings but it resets everything — not a targeted
checklist re-entry.

**What to build**: Settings → Maintenance card → "Run first-time setup" button. Clicking:
1. Resets `QSettings` keys `home/checklist_done` and `home/scan_count` to 0
2. Navigates to Home
3. Triggers `_set_first_run_mode()` so the hero CTA and checklist card reappear
4. Shows toast: "Setup checklist reset — complete the steps to finish configuring NetSentinel"

This is additive to the existing "Reset all dismissed notices" button — both coexist.

**Acceptance**: Button in Settings triggers checklist re-entry. Home returns to first-run
layout. Steps can be completed again in sequence. Toast confirms the reset.

**Files**: `ui/pages/settings_page.py` (button), `ui/pages/home_page.py`
(`_set_first_run_mode` callable from dashboard signal), `ui/dashboard.py` (wire signal).

---

## Architecture decisions made for this backlog

- **TIMELINE-1 nav placement**: Primary entry in Analysis section, between Monitor Overview and Diagnosis.
- **SCHED-3 default**: Monitor auto-resume is ON by default; user opts out in Settings.
- **INTEL-1 fetch strategy**: Eager async on drawer open — all three lookups fire simultaneously; skeleton rows shown while data loads.
- **TOAST-1 scope**: Replaces non-persistent amber banners only. Persistent banners (LOG-4 cap, LOG-5 challenge, HEALTH-2 offline) are not toasts.
- **PERF-1 eager pages**: Home, Settings, Notifications instantiate eagerly. All others are lazy.
- **NAV-5 trigger**: Only deep-link navigations (from alert drawer, popover, CVE chip, etc.) push the back stack. Direct rail clicks clear it.

---

## Notes for the next product cycle (V5 candidates)

- **Multi-network profiles**: Users with home + VPN want separate scan histories and alert rules per network.
- **Mobile companion**: REST API is live; a read-only iOS/Android view of grade + active alerts is a natural extension.
- **Plugin marketplace**: Plugin system is stable — a curated list of community plugins with one-click install.
- **MQTT automation**: `mqtt_page.py` exists; deeper integration with home-automation platforms (Home Assistant).
- **Network topology map**: Visual diagram of device relationships (router → switch → hosts) from ARP + DHCP data.
- **Wi-Fi heatmap + inventory merge**: Heatmap shows labelled devices (from DEVICE-1 labels) at their physical positions.
