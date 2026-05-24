# NetSentinel — UX Product Backlog V2

## Product Owner Statement

V1 earned trust by working. V2 earns trust by communicating.

NetSentinel now monitors five things, stores history for everything, and fires alerts when it matters. But the app still does not tell the user *what it found*, *how fresh the data is*, *why this matters*, or *what to do next*. A Datadog dashboard that goes silent feels dangerous — you don't know if the service is healthy or if monitoring broke. NetSentinel has the same problem at every layer.

This backlog is about turning a capable monitoring tool into a product that a non-expert can trust. The test: a user who has been running NetSentinel for two weeks, opens it on Monday morning, and in 30 seconds knows whether anything needs their attention — without clicking into six pages.

Every item below is anchored to a specific user moment of confusion, mistrust, or abandon.

---

## Priority tiers

- **P0** — broken promises (feature exists, user cannot reliably use it)
- **P1** — first-impression failures and trust gaps (user doesn't know if the app is working)
- **P2** — recurring-user friction (power user confusion, abandoned flows)
- **P3** — polish (small inconsistencies that accumulate into "this feels unfinished")

---

## Implementation order (remaining)

| # | Item | Title | Priority | Sprint | Status |
|---|------|-------|----------|--------|--------|
| 1 | TRUST-1 | Home "last checked" freshness strip | P0 | 1 | ✅ done |
| 2 | TRUST-2 | Rail badge counts for alerts | P0 | 1 | ✅ done |
| 3 | EMPTY-1 | Consistent empty states with inline CTAs on all data pages | P1 | 1 | ✅ done |
| 4 | SCAN-1 | Post-scan delta summary ("3 new devices since last scan") | P1 | 2 | ✅ done |
| 5 | EXPLAIN-1 | Network Grade score breakdown tooltip/drawer | P1 | 2 | ✅ done |
| 6 | EXPLAIN-2 | Contextual help tooltips on all technical metric labels | P1 | 2 | ✅ done |
| 7 | FILTER-1 | Global search/filter bar on Inventory table | P2 | 3 | ✅ done |
| 8 | FILTER-2 | Sortable columns + persistent sort in Inventory | P2 | 3 | ✅ done |
| 9 | DEVICE-1 | Device notes and custom name/tag editing | P2 | 3 | ✅ done |
| 10 | ALERT-1 | Alert snooze (1h / 8h / forever) per rule | P1 | 4 | ✅ done |
| 11 | ALERT-2 | Alert deduplication counter ("fired 7 times in 1h") | P2 | 4 | ✅ done |
| 12 | TIME-1 | Data age indicators on Monitor Overview tiles | P1 | 4 | ✅ done |
| 13 | KEYBOARD-1 | Global keyboard shortcut map (? opens overlay) | P2 | 5 | ✅ done |
| 14 | KEYBOARD-2 | J/K row navigation in all tables | P2 | 5 | ✅ done |
| 15 | VISUAL-1 | Severity colour consistency: amber/red/green used only for their semantic | P3 | 5 | ✅ done |
| 16 | DEVICE-2 | Per-device history drawer: last-seen, scan appearances, signal | P2 | 6 | ✅ done |
| 17 | SCAN-2 | Scan progress: per-host status ("probing 192.168.1.12…") | P2 | 6 | ✅ done |
| 18 | SETTINGS-1 | Settings search bar | P3 | 6 | ✅ done |
| 19 | SETTINGS-2 | Unsaved-changes guard (dirty dot + confirm-on-leave) | P1 | 7 | ✅ done |
| 20 | TRUST-3 | Monitor health indicators (last event time per monitor) | P1 | 7 | ✅ done |
| 21 | DASH-1 | "Action needed" section on Home (pending alerts + offline devices) | P1 | 7 | ✅ done |
| 22 | EXPLAIN-3 | Inline remediation steps for each Diagnosis finding (expandable) | P2 | 8 | ✅ done |
| 23 | FILTER-3 | Alert history filter: severity / rule / time range | P2 | 8 | ✅ done |
| 24 | VISUAL-2 | Loading skeleton rows for all async data loads (no more blank → populated flash) | P3 | 8 | ✅ done |

---

## Sprint 1 — "Is it working?" trust signals

### TRUST-1 — Home "last checked" freshness strip

**User moment**: User opens the app on Monday. Home shows a grade and alert counts. Are those from right now, or from Friday?

**What to build**: A slim strip above the Home scroll area showing:
- Last scan: `2 hours ago` (or `Never`)
- Monitors: `ARP active · DHCP active · Storm inactive`
- Tap-to-refresh icon on the right

**Acceptance**: Strip always visible on Home. Timestamps update when a scan or monitor event fires. "Never" shown in amber.

**Files**: `ui/pages/home_page.py` — add strip widget in `__init__`, update in `_on_scan_complete` and `_push_monitor_pills`.

---

### TRUST-2 — Rail badge counts for alerts

**User moment**: User has 4 unacknowledged alerts. Nothing on the rail communicates this.

**What to build**: `_RailButton.set_badge(n)` already exists (green dot). Extend it to accept a count string (e.g. `"4"`) and render a numeric red pill badge instead of a plain dot when `n > 0`. Update `_push_monitor_pills` to pull unacknowledged alert count from `MetricStore.get_recent_alerts()` and call `set_badge` on the Notifications rail button.

**Acceptance**: Rail button shows `4` in red pill when there are 4 unacknowledged alerts. Clears to no badge when count is 0.

**Files**: `ui/dashboard.py` — `_RailButton.set_badge`, `_push_monitor_pills` / scan callback.

---

### EMPTY-1 — Consistent empty states with inline CTAs

**User moment**: User opens Bandwidth Monitor, Port Scanner, or SNMP Traps page for the first time. Sees a blank table with no explanation.

**What to build**: Each of the following pages needs an empty-state widget (icon + headline + one-line explainer + CTA button) shown when the data table/list has 0 rows and no active session:
- Bandwidth Monitor: "No traffic captured yet" + "Start Monitor" button
- Port Scanner: "No scan run yet" + "Run Port Scan" button
- Protocol Visualizer: "No capture session" + "Start Capture" button
- SNMP Traps: "No traps received" + "Configure SNMP" (→ Settings)
- Threat Intelligence: "No results yet" + "Run CVE Scan" button
- ARP Spoof Watch: "Not running" + "Start ARP Watch" button

**Acceptance**: Empty state shows instead of blank area. CTA directly triggers the primary action or navigates to configuration.

**Files**: `ui/pages/bandwidth_page.py`, `port_scan_page.py`, `protocol_viz_page.py`, `snmp_page.py`, `threat_intel_page.py`, `arp_page.py`.

---

## Sprint 2 — Scan interpretation

### SCAN-1 — Post-scan delta summary

**User moment**: User runs a scan. Sees a list of 12 devices. Were any of those new? Did any disappear? Did anything change?

**What to build**: After scan completes, compare current result against last scan result (stored in `MetricStore`). Inject a delta banner at top of the device list with:
- `+2 new devices` (amber)
- `1 device missing` (red)  
- `No changes` (green) if identical

Store previous scan result snapshot in `QSettings` (JSON-serialised list of MACs). On `_on_scan_complete`, diff and render banner. Banner has `×` dismiss.

**Acceptance**: Delta banner appears after every non-first scan. Correct counts. Dismissed per session.

**Files**: `ui/pages/home_page.py`, potentially `modules/metric_store.py` if snapshot storage needs DB.

---

### EXPLAIN-1 — Network Grade score breakdown

**User moment**: User sees "Grade: C+". They have no idea what that means or which metric is dragging it down.

**What to build**: The grade chip/widget on Home and MonitorOverview should have a `(?)` info button beside it. Clicking opens a `QDialog` or side drawer showing the grade rubric: which sub-scores contributed, their individual values, and one-line remediation for the lowest-scoring item.

Grade sub-scores already available from the scan result dict — surface them here.

**Acceptance**: `(?)` button visible next to grade. Drawer shows sub-score breakdown with colour-coded bars. "How to improve" tip for the worst sub-score.

**Files**: `ui/pages/home_page.py`, `ui/pages/monitor_overview_page.py` — add info button and drawer.

---

### EXPLAIN-2 — Contextual help tooltips on technical metric labels

**User moment**: User sees "RTT: 14ms (p95: 31ms)" on the Trend page. Or "RSRP: -89 dBm" on Modem. They don't know if that's good or bad.

**What to build**: Add rich tooltips to all technical metric labels across:
- Trend page: RTT, packet loss, jitter, p95
- Modem page: RSRP, RSRQ, SINR, RSSI, band, eNB
- Mesh page: signal strength, channel, backhaul RSSI
- Network Grade widget: each letter grade

Tooltip content: what the metric means in one sentence + "Good: X–Y  /  Acceptable: Y–Z  /  Poor: >Z"

**Acceptance**: Hovering any labelled metric shows a tooltip with context. No new UI elements needed beyond `setToolTip()` calls.

**Files**: `ui/pages/trend_page.py`, `modem_page.py`, `mesh_router_page.py`, `home_page.py`.

---

## Sprint 3 — Inventory power

### FILTER-1 — Global search/filter bar on Inventory

**User moment**: User has 30 devices. Wants to find "the Nest thermostat". Has to scroll and scan by eye.

**What to build**: Add a `QLineEdit` search bar above the Inventory table. Filter rows in real-time (case-insensitive match on IP, MAC, hostname, vendor). Add a "Filter" chip row for: `All` / `Online` / `Offline` / `Unknown vendor`. Both filters compose.

**Acceptance**: Typing filters rows instantly. Chips filter by status. "No matches" empty state shown if 0 rows after filter.

**Files**: `ui/pages/inventory_page.py` (or wherever the device table lives).

---

### FILTER-2 — Sortable columns + persistent sort in Inventory

**User moment**: User wants devices sorted by last-seen to find what just connected.

**What to build**: Make all Inventory table columns sortable via header click. Persist last sort column + direction in `QSettings`. Add `Last Seen` column if not already present.

**Acceptance**: Click any column header to sort. Arrow indicator on active sort column. Sort persists across sessions.

**Files**: `ui/pages/inventory_page.py`.

---

### DEVICE-1 — Device notes and custom name/tag editing

**User moment**: User sees "192.168.1.47 — Unknown vendor". They know it's their son's Xbox. There's no way to record this.

**What to build**: Double-clicking a device row opens an inline edit panel (or `QDialog`) with:
- Custom name field
- Tags (comma-separated, rendered as chips)
- Notes textarea
- `Save` / `Cancel`

Store in `MetricStore` as a new `device_labels` table (MAC → name, tags, notes). Render custom name in place of hostname when set. Show a pencil icon on hover to hint editability.

**Acceptance**: Double-click opens editor. Custom name replaces hostname in table. Tags shown as small chips. Data survives restart.

**Files**: `modules/metric_store.py` (new table), `ui/pages/inventory_page.py`.

---

## Sprint 4 — Alert control

### ALERT-1 — Alert snooze per rule

**User moment**: User gets "ARP announcement flood" every 10 minutes because their printer is quirky. They want to silence it for tonight without disabling the rule permanently.

**What to build**: Right-click menu on alert rows (and on rule rows in Notifications settings) offers "Snooze: 1 hour / 8 hours / Until tomorrow / Indefinitely". Store snooze expiry in `QSettings` keyed by rule name. `notification_router.py` checks snooze expiry before firing. Snoozed rules get an amber clock icon.

**Acceptance**: Right-click snooze menu on alert rows. Snoozed rules show clock icon. Notifications suppressed for snoozed rules. Snooze expires automatically.

**Files**: `modules/notification_router.py`, `ui/pages/notifications_page.py`.

---

### ALERT-2 — Alert deduplication counter

**User moment**: User opens Alert History and sees 40 rows, all "ARP flood detected". The signal is buried in noise.

**What to build**: In `MetricStore.get_recent_alerts()`, group consecutive same-rule same-host alerts within a 1-hour window. Return a `count` field. In the Alert History table, render count as a `×7` badge on the first row of each group. Collapsed groups expand on click.

**Acceptance**: Consecutive duplicate alerts collapsed with count badge. Expanding shows individual timestamps.

**Files**: `modules/metric_store.py`, `ui/pages/notifications_page.py`.

---

### TIME-1 — Data age indicators on Monitor Overview tiles

**User moment**: User opens Monitor Overview. ARP tile shows "3 detections". When were those? Yesterday? A second ago?

**What to build**: Each tile on `MonitorOverviewPage` shows a "last event" timestamp below its stat: `"Last event: 4 minutes ago"` or `"No events yet"`. Pull from `MetricStore` per-monitor last-event timestamp. Update on `showEvent`.

**Acceptance**: All six monitor tiles show last-event time. Format: `"X minutes ago"` / `"X hours ago"` / `"Never"`.

**Files**: `ui/pages/monitor_overview_page.py`, `modules/metric_store.py` (add `get_last_event_time(monitor_name)` if needed).

---

## Sprint 5 — Keyboard power

### KEYBOARD-1 — Global keyboard shortcut overlay

**User moment**: Power user wants to navigate without the mouse but can't discover any shortcuts exist.

**What to build**: Pressing `?` anywhere in the app opens a `QDialog` overlay listing all keyboard shortcuts in two columns. Sections: Navigation / Actions / Tables. Close on `Escape` or `?` again.

Existing shortcuts to document: `Ctrl+K` (command palette), `Ctrl+R` (rescan), `Escape` (close flyout). New shortcuts to add in same PR: `Ctrl+,` → Settings, `Ctrl+L` → Log Hub.

**Acceptance**: `?` opens overlay. All shortcuts listed. Overlay closeable. New shortcuts functional.

**Files**: `ui/dashboard.py` — add `keyPressEvent`, `_ShortcutOverlay` dialog class.

---

### KEYBOARD-2 — J/K row navigation in all tables

**User moment**: Power user has keyboard focus in a table. Arrow keys don't move between rows. J/K don't work either.

**What to build**: Subclass or configure `QTableWidget` / `QTableView` instances across Inventory, Alert History, Delivery Log, and Log Hub so that `J` moves to next row, `K` moves to previous row, `Enter` triggers row action (same as double-click). Standard arrow keys should already work — verify and fix if not.

**Acceptance**: J/K navigate rows in all major tables. Enter triggers row action. No regression on existing double-click or click handlers.

**Files**: `ui/pages/inventory_page.py`, `notifications_page.py`, `log_hub_page.py`.

---

### VISUAL-1 — Semantic colour audit

**User moment**: User sees amber text on the Log Hub export banner. Is that a warning? Then sees amber for a "helpful tip". Amber has lost meaning.

**What to build**: Audit all uses of `AMBER`, `RED`, `GREEN` colour constants across UI pages. Correct usages where colour conveys the wrong semantic:
- `RED` / `AUDIT_RED`: errors, security threats, critical failures only
- `AMBER`: warnings, degraded-but-not-failed, action-needed
- `GREEN`: success, healthy, active

Produce a one-time pass across all page files. No new features — just a colour correctness pass.

**Acceptance**: Each colour is used only for its defined semantic. No amber on neutral/informational text.

**Files**: Across `ui/pages/*.py` — read-only audit then targeted edits.

---

## Sprint 6 — Device intelligence

### DEVICE-2 — Per-device history drawer

**User moment**: User wants to know when "Unknown device" first appeared, how many times it showed up in scans, and what its signal was last time.

**What to build**: Clicking a device row in Inventory opens a right-side drawer panel (not a modal) showing:
- First seen / Last seen
- Number of scan appearances
- Open ports (from last port scan, if available)
- Speed test results attributed to this IP (if any)
- Modem/mesh signal at last scan time
- Notes (from DEVICE-1 if implemented, else a placeholder)

Pull data from `MetricStore` scan history. The drawer slides in from the right — use `QPropertyAnimation` on width.

**Acceptance**: Click row → drawer slides in. Shows history data. Clicking another row updates drawer. Close button or click-outside dismisses.

**Files**: `ui/pages/inventory_page.py` — add `_DeviceDrawer` widget.

---

### SCAN-2 — Scan progress per-host status

**User moment**: User clicks Scan. Progress bar fills slowly. They have no idea if it's stuck or actively working.

**What to build**: During the scan, the progress area (currently a spinner + "Scanning…") shows a live-updating single line: `Probing 192.168.1.12 (14 of 254)…`. Update from the scan worker's progress signal. No need to show all hosts — just the current one.

**Acceptance**: Scan progress shows current host. Updates at least once per 2 seconds. Doesn't slow the scan.

**Files**: `ui/pages/home_page.py`, relevant scan worker (whichever emits progress).

---

### SETTINGS-1 — Settings search bar

**User moment**: User wants to change the SMTP port. They can't remember which section it's in and scroll through three cards looking.

**What to build**: Add a `QLineEdit` search bar at the top of the Settings page. Typing highlights matching labels in-place (yellow background on match). No rows hidden — just visually emphasised matches. Clear on empty. Minimum 3 characters to trigger.

**Acceptance**: Typing "smtp" highlights SMTP-related fields. Highlighting clears when search cleared.

**Files**: `ui/pages/settings_page.py`.

---

## Sprint 7 — Data integrity signals

### SETTINGS-2 — Unsaved-changes guard

**User moment**: User edits SMTP host, gets distracted, navigates away. Settings silently revert. They spend 20 minutes debugging why notifications stopped.

**What to build**: Settings page tracks a `_dirty` flag. When any field changes, set dirty. Show a small amber `●` in the page header (or on the Save button). If user navigates away while dirty, show a `QMessageBox` "You have unsaved changes — save or discard?".

Connect to `_push_section` in dashboard to intercept navigation when dirty.

**Acceptance**: Dirty dot appears on any field edit. Navigation-away triggers confirm dialog. Saving or discarding clears dirty state.

**Files**: `ui/pages/settings_page.py`, `ui/dashboard.py` (navigation intercept).

---

### TRUST-3 — Monitor health indicators

**User moment**: User enabled ARP Watch three weeks ago. Today it shows "0 detections". Is that good (network is clean) or bad (monitor crashed and missed everything)?

**What to build**: On `MonitorOverviewPage` and in the monitor rail pills, each active monitor shows a health indicator:
- `●` green: running, last event within expected interval
- `●` amber: running, but no data received in longer than expected (possible missed events)
- `●` grey: stopped / never started

Pull health from monitor thread `is_alive()` + last-emitted-event timestamp vs. expected polling interval.

**Acceptance**: Each monitor tile and rail pill shows a coloured health dot. Amber if no events in 2× the polling interval.

**Files**: `ui/pages/monitor_overview_page.py`, `ui/dashboard.py` (`_push_monitor_pills`).

---

### DASH-1 — "Action needed" section on Home

**User moment**: User opens the app. Grade is B, 2 alerts, 1 device offline. Those facts are scattered across three sections. There is no single "here is what needs your attention" view.

**What to build**: Add an "Action needed" card at the very top of the Home scroll area (above the grade section), shown only when there is something to show. Contents (in priority order):
- Unacknowledged alerts (count + highest severity chip + "View →")
- Devices that appeared in last scan but have no label and no prior history (count + "Review →")
- Monitors that are enabled but unhealthy (from TRUST-3)
- Setup checklist items still unchecked (only if checklist not yet complete)

Card hidden when all items resolve to zero.

**Acceptance**: Card appears when there is ≥1 item. Each item has a navigate link. Card disappears when all clear.

**Files**: `ui/pages/home_page.py`.

---

## Sprint 8 — Depth and polish

### EXPLAIN-3 — Inline remediation steps in Diagnosis

**User moment**: Diagnosis says "DNS resolving slowly". The CTA navigates to DNS Stability. But the user doesn't know what to *do* about it.

**What to build**: For each finding category in `_CTA_MAP`, add a `_REMEDIATION` dict with 2–4 bullet-point steps. Render them in a collapsible `▶ What to do` expander inside each finding card, below the existing description.

**Acceptance**: Each finding card has a `▶ What to do` expander. Expanding shows 2–4 concrete steps. Steps are specific (not "check your router").

**Files**: `ui/pages/diagnosis_page.py`.

---

### FILTER-3 — Alert history filtering

**User moment**: User wants to see only `CRITICAL` alerts from the last 7 days to understand a bad week.

**What to build**: Above the Alert History table in Notifications, add:
- Severity filter chips: `All` / `Critical` / `High` / `Medium` / `Low`
- Time range dropdown: `Last 24h` / `Last 7 days` / `Last 30 days`

Both compose. Re-queries `MetricStore.get_recent_alerts()` with updated params on change.

**Acceptance**: Selecting filters updates table immediately. Chips and dropdown state is visible.

**Files**: `ui/pages/notifications_page.py`.

---

### VISUAL-2 — Loading skeleton rows

**User moment**: User navigates to Inventory or Port Scanner while data loads. Table is blank for 0.5–2 seconds then suddenly populates. This looks like a bug, not a load.

**What to build**: When a page begins an async data fetch, show 5–8 "skeleton" rows — `QTableWidget` rows with `QLabel` items containing a grey animated `QPropertyAnimation` shimmer (or a static light-grey background). Replace with real data on arrival.

Implement a reusable `_insert_skeleton_rows(table, count)` helper in `ui/dashboard.py` or a new `ui/widgets/skeleton.py`. Apply to: Inventory, Port Scanner, Threat Intelligence, Alert History.

**Acceptance**: Loading state shows skeleton rows, not blank. Transition to real data is smooth (no flash).

**Files**: `ui/pages/inventory_page.py`, `port_scan_page.py`, `threat_intel_page.py`, `ui/pages/notifications_page.py`.

---

## Notes for the next product cycle

These items were observed but are out of scope for this backlog. Log them for V3:

- **Multi-network support**: Users with home + office VPN want separate network profiles.
- **Export all**: Single "Export everything" ZIP (all logs + scan history + grade timeline) for support tickets.
- **Dark/light theme toggle in title bar**: Currently only accessible in Settings → Appearance.
- **Onboarding re-entry**: No way to replay the "post-scan sheet" or checklist after dismissal — only reset in Settings → Reset dismissed notices.
- **Mobile companion**: Out of scope for desktop V2 but the REST API is already there.
