# NetSentinel — UX Product Backlog V5

## Product Owner Statement

V1–V4 shipped a lot of features. V5 is the session where we stop adding and start
verifying. Not everything that was "implemented" was tested end-to-end in a real flow.
Signal chains with three hops, conditions that depend on QSettings state, alert paths
that route through four files — these are where regressions live and where the product
quietly breaks without telling anyone.

V5 is two things in one day:

**Audit** — walk every major user flow from V1–V4 and confirm it actually works as
described. Find the broken links, the signals that never fire, the conditions that
evaluate wrong, the navigate targets that 404.

**Polish** — fix the UI issues that have accumulated across four sessions of additive
work. Each sprint added widgets to existing pages without stepping back to look at the
whole. Some pages are now visually crowded or hierarchically confused. Fix the worst ones.

Items are ordered by impact. Work top to bottom. Do not skip audit items to do polish.

---

## Audit items — verify these actually work

### AUDIT-1 — First-run flow, complete end-to-end ✅

**What to verify**: On a fresh `QSettings` state (or after ONBOARD-1 reset), the full
first-run sequence fires correctly:
1. Home opens in hero mode (`_set_first_run_mode`) — single centred scan CTA, no other sections
2. First scan completes → post-scan sheet appears (`_maybe_show_post_scan_sheet`)
3. Sheet is dismissed → setup checklist card appears
4. `scan_count` increments correctly on each subsequent scan
5. After 5 scans + all checklist items checked → recurring layout replaces first-run layout

If any step doesn't fire, find the broken condition and fix it. This flow is the
first impression for every new user and has never been walked end-to-end after all the
subsequent patches to `home_page.py`.

**Acceptance**: All 5 steps fire in sequence on a clean state. No step is skipped.
Recurring layout appears at the right threshold.

**Files**: `ui/pages/home_page.py`, QSettings keys `home/scan_count`, `home/checklist_done`.

---

### AUDIT-2 — Alert snooze actually suppresses notifications ✅

**What to verify**: Right-click snooze on an alert rule sets a QSettings expiry key.
Confirm `notification_router.py` checks that key before firing. Test: snooze a rule,
trigger the condition that would fire it, confirm no notification is sent.

Also verify: snooze expiry is checked at fire time (not at snooze-set time), so a 1-hour
snooze set at 11:58 doesn't expire at 12:00 because the app restarted.

**Acceptance**: Snoozed rule does not fire during the snooze window. Fires correctly
after expiry. Clock icon visible on snoozed rule row.

**Files**: `modules/notification_router.py` (snooze check), `ui/pages/notifications_page.py`.

---

### AUDIT-3 — Alert drawer → Log Hub signal chain ✅

**What to verify**: The "Log Hub →" button in `alert_drawer.py` emits `view_in_log_hub(ts, source_key)`.
Trace the full chain:
1. `AlertDrawer.view_in_log_hub` signal
2. → `NotificationsPage` re-emits it upward
3. → `Dashboard._on_view_alert_in_log_hub()` receives it
4. → navigates to Log Hub
5. → calls `LogHubPage.jump_to_alert_time(ts, source_key)`
6. → Log Hub switches to History mode, sets ±30min window, force-enables the source toggle

Confirm each hop is connected. Confirm `_rule_to_log_source()` maps all rule prefixes
used in practice (ARP_FLOOD, DHCP_ROGUE, RATE_SPIKE, CVE, PORT_SCAN, etc.).

**Acceptance**: Clicking "Log Hub →" on any alert navigates correctly and shows log
entries from ±30 minutes around the alert timestamp with the correct source selected.

**Files**: `ui/widgets/alert_drawer.py`, `ui/pages/notifications_page.py`,
`ui/dashboard.py`, `ui/pages/log_hub_page.py`.

---

### AUDIT-4 — Global time range reaches all wired pages ✅

**What to verify**: Changing the global time range `QComboBox` in the title bar emits
`global_time_range_changed(float)`. Confirm the signal is connected at init time to
all five intended pages: history, cert, service, speed_test, notifications.

For each: change the global range and confirm the page re-queries data for the new window.
CVE was intentionally skipped (no hours param) — verify that skip is still correct.
Log Hub was also skipped — confirm the decision still holds (live mode irrelevant;
history mode uses jump_to_alert_time instead).

**Acceptance**: All five pages respond to time range changes. CVE and Log Hub correctly
do not respond. No page silently swallows the signal without updating.

**Files**: `ui/dashboard.py` (`_init_pages` signal wiring), each of the five pages.

---

### AUDIT-5 — Monitor Overview receives all its data pushes ✅

**What to verify**: `MonitorOverviewPage` is supposed to show state from multiple sources.
Confirm each of the following is actually wired and reaches the page:
- Network grade + score dimensions (from scan result → `set_grade_details()`)
- Storm monitor state (from storm worker → `set_storm_state()` or equivalent)
- Port scan result (from port scan → `set_port_scan_result()` or equivalent)
- CVE result (from threat intel → `set_cve_result()` or equivalent)
- Automation health (new in V4 — `AUTO-2` — skip if not yet built)

For each: find where the data originates, trace the signal/callback to MonitorOverviewPage,
confirm the tile renders it. If any wire is missing, add it.

**Acceptance**: All four data sources reach Monitor Overview and render in their tiles.
No tile shows "No data" for data that was produced in the same session.

**Files**: `ui/pages/monitor_overview_page.py`, `ui/dashboard.py` (push calls after each worker result).

---

### AUDIT-6 — Diagnosis CTA_MAP — all 10 nav targets resolve

**What to verify**: `diagnosis_page.py` has a `_CTA_MAP` with 10 finding categories
mapped to nav targets. Click "Navigate →" on a finding card for each category and confirm
the destination page loads correctly. Common failure mode: the nav key string doesn't
match what `_nav_rail_go_to()` expects, so the navigate call silently does nothing.

Produce a complete list of all 10 keys and their targets. Fix any that resolve to the
wrong page or produce no navigation.

**Acceptance**: All 10 CTA buttons navigate to the correct page. No silent failures.

**Files**: `ui/pages/diagnosis_page.py` (`_CTA_MAP`), `ui/dashboard.py` (`_nav_rail_go_to` key map).

---

### AUDIT-7 — FLOW-2 alert row click routing — all 4 targets

**What to verify**: In notifications_page, clicking an alert row routes by rule prefix:
- `PORT_SCAN` → Port Scan page
- `THREAT_INTEL` / `CVE` → Threat Intelligence page
- `RATE_SPIKE` → Bandwidth (Live Bandwidth) page
- Host-based alerts → Inventory row for that host
- Default → Notifications (no crash, stays on page)

Test each route. Verify Inventory row-select actually scrolls to and selects the device.
Verify Bandwidth navigates to the live view, not the history tab.

**Acceptance**: All 4 route types navigate correctly. No route silently fails. Inventory
row-select finds the device when the IP is known.

**Files**: `ui/pages/notifications_page.py` (click handler), `ui/pages/inventory_page.py`
(`select_device`), `ui/dashboard.py`.

---

### AUDIT-8 — Device popover → Inventory "View in Inventory" flow

**What to verify**: Right-clicking a device IP in Connections, Threat Intel, CVE, or
Log Hub opens the `DevicePopover`. The popover has a "View in Inventory" button.
Confirm the full chain:
1. Popover button emits `open_inventory(ip)` signal
2. → `Dashboard._on_popover_open_inventory(ip)` receives it
3. → navigates to Inventory
4. → calls `InventoryPage.select_device(ip)` which scrolls to and highlights the row

If the device isn't in the current scan result (i.e. the IP isn't in the table), confirm
it gracefully does nothing rather than crashing.

**Acceptance**: "View in Inventory" works from all 4 source pages. Inventory scrolls to
the correct row. Graceful no-op if device not in table.

**Files**: `ui/widgets/device_popover.py`, `ui/dashboard.py`, `ui/pages/inventory_page.py`.

---

### AUDIT-9 — Home "Action needed" card hide/show lifecycle

**What to verify**: The "Action needed" card (DASH-1) is shown when there are
unacknowledged alerts or offline unlabelled devices, and hidden when both are zero.
Test the following transitions:
- App opens with 3 pending alerts → card visible
- User acks all alerts from the alert drawer → card hides (or updates to "No alerts")
- Card re-appears after next scan finds new alerts
- Card shows the correct alert count (not cached from previous session)

Common failure mode: the card's hide condition checks a stale value from page init
rather than a live query.

**Acceptance**: Card appears and disappears correctly at each transition. Count is always
current. Card never shows "0 alerts" when there are zero.

**Files**: `ui/pages/home_page.py` (`_refresh_action_needed` or equivalent).

---

### AUDIT-10 — Delivery log retry actually resends

**What to verify**: In notifications_page, the delivery log has a retry panel for failed
rows (NOTIF-4). Clicking Retry on a failed delivery should call
`NotificationRouter` to resend the notification through the original channel.

Confirm: retry button is wired to an actual resend call. Confirm the row status updates
to ⟳ while retrying and ✓ or ✗ after result. Confirm the retry path doesn't create a
duplicate alert in the alert history table.

**Acceptance**: Retry button resends via the correct channel. Row status updates correctly.
No duplicate alert created.

**Files**: `ui/pages/notifications_page.py` (retry button), `modules/notification_router.py`.

---

## Polish items — fix the accumulated rough edges

### POLISH-1 — Home page visual hierarchy

**Problem**: The recurring-user Home layout now has: freshness strip + "This week" card
(V4) + grade section + action needed card + alerts header + monitoring pills + setup checklist
(if not done). On a typical session that's 5–6 stacking regions before the user sees any
real content. It reads as a dashboard with everything at equal weight.

**Fix**: Establish a clear visual hierarchy:
1. Freshness strip — stays (slim, utility)
2. Action needed card — stays first when non-empty (urgent)
3. "This week" card + grade side-by-side in a two-column row (not stacked)
4. Monitoring pills row — slim, below the stats
5. Setup checklist — only show if not complete; once complete, remove from layout entirely
   (not just collapse — remove the widget) so it doesn't take space

The grade circle and "This week" card belong in the same horizontal band — they answer
the same question ("how is my network?") and should feel like one unit.

**Acceptance**: Recurring layout has at most 4 visible regions (strip, action card when
non-empty, stats row, pills). Nothing competes for first-glance attention equally.

**Files**: `ui/pages/home_page.py` (recurring layout rebuild).

---

### POLISH-2 — Log Hub control bar

**Problem**: Log Hub has three controls stacked or side-by-side: source chip bar, search
bar, live/history toggle. On smaller windows they wrap or overlap. The source chip bar
has 8+ chips which overflow. The search bar and chips both filter rows but look like
separate features.

**Fix**:
- Merge search bar and source chips into one unified filter row: search input on the left,
  source chips to the right of it, live/history toggle anchored to the far right.
- Source chips: show only the currently-enabled sources as chips (not all possible sources).
  Add a "+" chip that opens a source picker popover for sources not currently shown.
- Live/history toggle: make it visually distinct (pill toggle, not just a button) so it
  reads as a mode, not an action.

**Acceptance**: All three controls fit in one row at 1024px width. Source chips don't
overflow. Controls read as a coherent filter bar, not three separate widgets.

**Files**: `ui/pages/log_hub_page.py` (control bar layout).

---

### POLISH-3 — Notifications page: Alert History as default tab

**Problem**: The notifications page has two tabs: "Delivery Log" and "Alert History"
(NOTIF-6). Delivery Log is the first tab (existing feature). Alert History was added
after. Most users who navigate to Notifications want to see alerts, not delivery metadata.

**Fix**: Swap the tab order so "Alert History" is tab index 0 (default visible). Rename
"Delivery Log" to "Delivery & Retry" to better describe its retry functionality.

While here: confirm the Alert History table's double-click-to-navigate works for all
rule prefixes (uses the same rule prefix routing as FLOW-2 — see AUDIT-7).

**Acceptance**: Alert History is the default visible tab. "Delivery & Retry" tab is
second. Double-click routing works for all rule types.

**Files**: `ui/pages/notifications_page.py` (tab order + rename).

---

### POLISH-4 — Monitor Overview: active state clarity

**Problem**: Monitor Overview shows tiles for ARP, DHCP, Storm, Port Scan, and CVE.
When a monitor is running, the tile looks identical to when it's stopped — except for
a small status dot. Users can't tell at a glance what's active.

**Fix**: Active monitor tiles get a left border accent (2px ACCENT colour) and a
slightly different background tint (ACCENT_LITE at 20% opacity). Stopped tiles remain
neutral. The status dot stays but the border is the primary active signal.

Apply the same pattern to the Automation tile (V4 AUTO-2) once built.

This is a pure CSS/style change — no logic changes.

**Acceptance**: Running monitors visually distinct from stopped at a glance. Accent
border and tint applied only to running/active tiles.

**Files**: `ui/pages/monitor_overview_page.py` (tile widget style update).

---

### POLISH-5 — Settings page: section jump navigation

**Problem**: Settings is a long single-scroll page with 8+ cards. Finding "SMTP port"
or "Scheduled scan" requires scrolling past unrelated sections. The search bar (SETTINGS-1)
highlights but doesn't jump.

**Fix**: Add a sticky anchor list on the left side of the Settings page — a narrow
sidebar (~110px) with section names as flat buttons: Notifications / Schedule / Monitors /
Appearance / Maintenance / About. Clicking an item calls `QScrollArea.ensureWidgetVisible()`
on the corresponding card. The active section highlights as the user scrolls (scroll-spy:
QScrollArea `valueChanged` → check which card is topmost visible).

If a sidebar at this scale feels too heavy, implement as a horizontal tab-strip at the
top of the settings scroll area instead (same scroll-spy behaviour).

**Acceptance**: Clicking a section name scrolls to it. Active section highlighted while
in view. No layout regression on resize.

**Files**: `ui/pages/settings_page.py`.

---

### POLISH-6 — Grade breakdown dialog: "How to improve" prominence

**Problem**: The grade breakdown dialog (EXPLAIN-1) shows sub-score bars and a "How to
improve" tip for the lowest-scoring item. The tip is rendered as regular body text and
gets lost below the bars.

**Fix**: Give the "How to improve" tip a distinct treatment:
- Amber left border (2px) on a `QFrame`
- Bold label: "Biggest improvement" above the tip text
- CTA link below: "Go to [relevant page] →" that navigates directly (reuse `_CTA_MAP`
  logic from Diagnosis if the categories overlap)

Move this tip block to the top of the dialog (above the score bars), not the bottom —
users want the action, not the data.

**Acceptance**: Tip is visually distinct (bordered frame). "Biggest improvement" label.
CTA link navigates to the relevant page. Tip is above the score bars.

**Files**: `ui/pages/home_page.py` or wherever `_GradeBreakdownDialog` is defined
(check `home_page.py` and `monitor_overview_page.py`).

---

### POLISH-7 — Command palette: discoverability and content

**Problem**: The command palette (`Ctrl+K`) is one of the best features but users
don't know it exists. The placeholder text says something generic. The recent actions
section (RECUR-3) is there but easy to miss.

**Fix**:
- Placeholder: "Search pages, devices, actions… (Ctrl+K)" — actually say what it searches
- Add a one-line hint row at the bottom of the palette when the query is empty:
  `Tip: type an IP address to find a device`
- Add a keyboard shortcut hint column to all page results: the shortcut if one exists
  (e.g. `Ctrl+L` for Log Hub, `Ctrl+,` for Settings) shown right-aligned in muted text
- Ensure `Ctrl+K` is shown in the `?` keyboard shortcut overlay (KEYBOARD-1 from V2)

**Acceptance**: Placeholder text is descriptive. IP hint shown when palette is empty.
Shortcuts shown for pages that have them. Ctrl+K in shortcut overlay.

**Files**: `ui/dashboard.py` (palette widget, placeholder, hint row, shortcut column).

---

### POLISH-8 — Flyout panel: visual separation between sections

**Problem**: The flyout nav panel has section headers (set to 9px TEXT_MUTED per VC5)
and items below them. On dark backgrounds the header → item visual boundary is subtle.
When items have dots (NAV-1) or badges (TRUST-2), the dots crowd the section headers.

**Fix**:
- Add 8px top margin above each section header (not the first one)
- Add a 1px `BORDER` colour divider line above each section header
- Ensure dots and badges on items don't reduce the item label's text width — use a fixed
  right-side slot for dots so text always has full width

**Acceptance**: Sections read as distinct groups. No dot/badge overlaps label text.
Divider lines visible between sections.

**Files**: `ui/dashboard.py` (`_FlyoutPanel`, `_FlyoutItem`, section header builder).

---

### POLISH-9 — Table row height and alternating row colour consistency

**Problem**: Across the app, QTableWidget rows have inconsistent heights: some pages
use 22px, some 26px, some let Qt pick. Alternating row colour (`BG_ALT_ROW`) is applied
in some pages but not others.

**Fix**: Audit and standardise:
- All data tables: `verticalHeader().setDefaultSectionSize(26)`
- All data tables: `setAlternatingRowColors(True)` with `BG_ALT_ROW` set in stylesheet
- Pages to check: Inventory, Log Hub, Notifications (both tabs), Port Scan results,
  Threat Intel, CVE, Speed Test history, Cert, Service

This is a mechanical pass — no logic changes.

**Acceptance**: All listed tables have 26px rows and alternating row colour. Visual
consistency across pages.

**Files**: Each of the listed pages — `setDefaultSectionSize(26)` and `setAlternatingRowColors`.

---

### POLISH-10 — Empty state warmth: add context line

**Problem**: Empty states across the app (added in V2 EMPTY-1) follow the pattern:
icon + headline + CTA. They're correct but cold. "No traffic captured yet" with a
"Start Monitor" button gives the user no sense of what they'll see when they do start.

**Fix**: Add a one-sentence context line between the headline and the CTA for the 6
primary empty states. The line answers "what will I see?" not "why is this empty":

- Bandwidth: *"Live traffic by device, updated every second."*
- Port Scanner: *"Open ports on every device in your network, ranked by risk."*
- Protocol Visualizer: *"Animated diagram of the protocols your network is speaking right now."*
- SNMP Traps: *"Alerts sent by your routers and switches when something changes."*
- Threat Intelligence: *"IPs and domains on your network matched against live threat feeds."*
- ARP Spoof Watch: *"Real-time detection of devices impersonating your router."*

**Acceptance**: Each of the 6 empty states has a context sentence. Text is warm and
outcome-focused, not feature-description.

**Files**: `ui/dashboard.py` or the respective page files where `_empty_state_widget()`
is constructed for each surface.

---

## Architecture notes for this session

- Do audit items first, in order. Each broken wire found in audit is a bug fix — prioritise over polish.
- If an audit item requires a non-trivial fix (> 30 min), note it as a separate backlog item rather than patching in-place.
- Polish items are independent of each other — if time runs short, stop after POLISH-5 and ship what's done.
- No new pages, no new modules (except if TIMELINE-1 from V4 hasn't been built yet and audit reveals the timeline_event table is needed for AUDIT-9 context — in that case, skip and note it as a V4 carry-forward).
