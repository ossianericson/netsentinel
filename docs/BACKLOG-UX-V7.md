# NetSentinel — UX Product Backlog V7

## Product Owner Statement

V6 made NetSentinel feel premium: consistent motion, tight density control, coach marks,
a proper header bar. Every page has the same *quality of construction*.

V7 goes one level deeper: **every screen should earn the time spent looking at it.**
Charts should tell a story at a glance. Tables should let you find anything in seconds.
The Home page should be a daily digest worth opening, not just a launcher. Power users
should get fast actions without navigation. Every data page should feel like it was built
by someone who thought hard about what *this specific data* means to the user.

Audience: Home users, hobbyists, students — same as V6.
Design north star: "The data explains itself."

Non-negotiables carried from V6:
- No clutter — every new control earns its space
- Respect Reduce Motion in all new animations
- Animations short, subtle, purposeful
- Must stay maintainable in Qt/Python

V7 is six sprints across approximately 10 sessions. All 49 items are UI-only or
UI-primary — no new workers, no new database tables unless explicitly noted.

---

## Section 1 — Home & Overview Depth

Goal: Turn the Home page and Overview into a beautiful daily dashboard. These are the
two most-opened pages; they should feel information-rich the moment they load.

---

### HOME-1 — Grade Circle Visual Upgrade + Crossfade Animation

**Problem**: The hero grade display is a plain 68×68 QLabel showing a letter. It looks
functional but not beautiful. When the grade updates it swaps instantly.

**Fix**:
1. Upgrade `_grade_circle` to a custom `_GradeRing` QPainter widget: draw a 4px arc
   (same style as the speed test gauge from ANIM-5) behind the letter at an angle
   proportional to the score. Letter stays centered. Arc color from `status_color()`.
2. On grade update: the arc sweeps from old angle to new angle over 600 ms
   (`QVariantAnimation`, `QEasingCurve.OutExpo`). The letter crossfades
   (opacity 1→0→1, 300 ms `OutQuad`) with the new value loading at the opacity valley.
3. Add a small numeric score below the letter (e.g. "82") that count-ups on update
   (same pattern as ANIM-5 speed test count-up, 600 ms OutExpo).
4. Respects `_reduce_motion()` — instant swap if enabled.

**Why it matters**: The grade is the most important number in the app. It should feel as
satisfying to see update as a speed test result.

**Duration**: arc sweep 600 ms, letter crossfade 300 ms
**Files**: `ui/pages/home_page.py` (`_GradeRing` inner widget, `set_grade()` slot)

---

### HOME-2 — Week-over-Week Grade Delta Chip

**Problem**: Grade history is stored in QSettings (up to 14 entries) but never surfaced
to the user. They can't tell if they're improving.

**Fix**: Compute the delta between this week's average score and last week's average score
from `_load_grade_history()`. Show a small chip beside the grade ring: "↑ +8 vs last week"
(GREEN) or "↓ −3 vs last week" (RED) or "— no change" (TEXT_MUTED). Hide if < 2 data
points. Update on each grade set.

**Files**: `ui/pages/home_page.py` (compute delta in `set_grade()`, chip widget in hero area)

---

### HOME-3 — Live Events Ticker on Recurring Home

**Problem**: Recurring users opening the app have no immediate sense of what happened
since their last visit. They have to navigate to Timeline to find out.

**Fix**: Below the freshness strip on the recurring-user layout, add a slim 28px "events
ticker" bar. Shows the last 3 timeline events as static text: bullet · "09:14 · Pi 3B+
went offline · 2h ago". Pulls from MetricStore's device events. Updates on each scan
completion. Hidden if no events in the last 24h. Clicking any event navigates to Timeline.

**Files**: `ui/pages/home_page.py` (new `_EventsTicker` QFrame, `_preload_from_store` update)

---

### HOME-4 — Speed Mini-Card Micro-Sparkline

**Problem**: The Speed mini-card on Home shows a single number ("247 Mbps") with a
static status dot. It gives no sense of whether that's typical or unusual.

**Fix**: Add a 72×16 QPainter sparkline below the value label showing the last 5 speed
test download results. Reuses the `_GradeSparkline` painter pattern. Color: GREEN if
trending ≥ baseline, AMBER if trending down >10%. Hidden if < 3 history points.

**Files**: `ui/pages/home_page.py` (`_MiniCard` extended with optional sparkline slot;
`set_speed()` slot passes sparkline data)

---

### HOME-5 — Diagnosis Last-Verdict Summary on Home

**Problem**: The home page shows an alert count but not the diagnosis state. A user with
"Poor DNS" or "High Packet Loss" in their last diagnosis has no reminder of it on Home.

**Fix**: Add a slim one-line summary row at the bottom of the recurring section: "Last
diagnosis: B+ · 2 issues · 4 days ago  [Re-run →]". Pull from the QSettings-stored
diagnosis history (OUTPUT-1 from V3). If the last verdict is CRITICAL or WARNING,
color the label accordingly. Clicking "Re-run →" navigates to Diagnosis.

**Files**: `ui/pages/home_page.py` (one-line widget, read diagnosis QSettings JSON)

---

### OVERVIEW-1 — Tile Click-to-Expand Micro-Detail

**Problem**: Overview tiles are fixed height (175 px) and show a summary. Users who want
more detail must navigate away.

**Fix**: Clicking an Overview tile expands it with a second content row (height animates
from 175 → 280 px, 280 ms `QEasingCurve.OutQuart`). The expanded row shows:
- `device_count` → "X new · Y offline · Z total" breakdown with semantic colors
- `rtt_summary` → top-3 slowest hosts as compact rows (hostname, RTT ms, loss %)
- `alert_feed` → last 2 alerts expanded with rule + time
- Other tiles → "View full →" link as fallback

Second click or clicking another tile collapses to 175 px (same easing). One tile open
at a time. Respects reduce-motion (no animation, instant resize).

**Files**: `ui/pages/overview_page.py` (`_BaseTile` expand/collapse, per-tile `_build_detail()`)

---

### OVERVIEW-2 — New Tile: Top Talkers

**Description**: A new tile type "Top Talkers" showing the top-3 devices by bandwidth
this session. Each row: device hostname (or IP if unnamed), ↓ down MB, ↑ up MB. Data
from the LiveBandwidthPage session totals — requires the bandwidth worker to be running.

If the bandwidth worker is not running, shows an empty state: "Start Live Bandwidth to
see top talkers."

**Files**: `ui/pages/overview_page.py` (new `_TopTalkersTile` class); `ui/dashboard.py`
(push session totals to tile via a new slot after each bandwidth worker tick)

---

### OVERVIEW-3 — New Tile: Recent Events

**Description**: A new tile type "Recent Events" showing the last 5 timeline entries as
compact rows. Each row: event icon (joined/left/alert/scan), brief label, elapsed time
right-aligned. Clicking any row navigates to Timeline. Clicking the tile title navigates
to Timeline.

Data query: `MetricStore.get_device_events(limit=5)` and `MetricStore.get_recent_alerts(limit=5)`.
Merge and sort by timestamp.

**Files**: `ui/pages/overview_page.py` (new `_RecentEventsTile`); MetricStore query
(reuses existing methods, no new table)

---

### OVERVIEW-4 — New Tile: Trend Status

**Description**: A new tile type "Trend Status" showing the verdict from the latest
trend analysis run. Displays: "3 critical · 1 warning · 12 clean" in semantic colors, or
"No trend data — click Run Analysis" empty state. Navigates to Trend page on click.

The dashboard pushes the latest `TrendReport` to this tile via a signal each time a
trend analysis completes (or on page load from a cached result in MetricStore).

**Files**: `ui/pages/overview_page.py` (new `_TrendStatusTile`); `ui/dashboard.py` (push
slot after trend worker finishes)

---

### OVERVIEW-5 — Tile Data-Age Indicator

**Problem**: The tile's `_ts_lbl` timestamp label exists but is permanently hidden. Users
can't tell if a tile's data is fresh or hours old.

**Fix**: Show `_ts_lbl` always. Format: "updated 2m ago" in TEXT_MUTED. When data age
exceeds 30 minutes, style it AMBER. When age exceeds 2 hours, style it RED. Logic runs
via a 60-second QTimer on the OverviewPage.

This is a style-only change — no data plumbing needed. The `_scanned_at` timestamp is
already stored on each tile.

**Files**: `ui/pages/overview_page.py` (`_BaseTile._ts_lbl` visibility + color logic;
OverviewPage 60s refresh timer)

---

## Section 2 — Visual Data Depth

Goal: Every chart and map page should show data that explains itself visually. No page
should make the user do mental arithmetic to understand what they're looking at.

---

### VIZ-1 — Geo Map: Enriched Click-to-Investigate

**Problem**: Clicking a scatter dot on the geo map selects it, but the detail panel on
the right shows only basic geo info (country, city). There's no connection to the rest of
the app's data.

**Fix**: When a dot is selected, enrich the right-side detail panel with:
- Country flag emoji + city + org/ASN string (already available from GeoLite2)
- Risk level chip (CRITICAL/HIGH/MEDIUM from threat intel if available)
- "Related threat intel entries:" list — query MetricStore for ThreatEntry records
  matching this IP; show up to 3 as compact rows with rule + timestamp
- "View in Threat Intel →" link if any entries exist
- "Connections from this IP in last 24h: N" from Connections history (if in MetricStore)

No new data table. All queries hit existing MetricStore methods.

**Files**: `ui/pages/geo_map_page.py` (canvas click handler, detail panel widget rebuild)

---

### VIZ-2 — Bandwidth Page: Event Annotations

**Problem**: The bandwidth chart shows traffic levels but gives no context for spikes
— the user can't tell if a spike was a device joining, a scan, or an alert.

**Fix**: When the bandwidth page is visible and receives an event signal from the
dashboard (new device join, RATE_SPIKE alert), add a vertical `axvline()` tick on the
matplotlib axes at the current x position. Annotations:
- Device join: green tick, label "device joined"
- RATE_SPIKE alert: red tick, label "rate alert"
- Store up to 10 annotations; evict oldest when full.
- Hovering a tick shows the full label via `mpl_connect('motion_notify_event')`.
- Annotations are ephemeral — cleared on page hide, not persisted.
- Reduce-motion: tick appears without color fade.

Dashboard wires to this page via a new `annotate_event(label, color)` slot.

**Files**: `ui/pages/live_bandwidth_page.py` (annotation logic + hover handler);
`ui/dashboard.py` (wire device join + RATE_SPIKE alert events to bandwidth page slot)

---

### VIZ-3 — Trend Page: Per-Host Mini-Sparklines

**Problem**: The trend table shows text arrows (↑/↓/→) for trend direction. Users can't
see the shape of the trend — a slowly rising line looks the same as a spike.

**Fix**: Add an 8th column "Trend" to the trend table. Each cell contains a 80×18
QPainter sparkline widget showing the measured values over the analysis window.
Color: GREEN if stable or falling, RED if rising toward threshold.
Reuses the `_GradeSparkline` painter logic from `home_page.py`.

The `TrendResult` object already carries a `points` list — use it directly.

**Files**: `ui/pages/trend_page.py` (new `_MiniSparkline` inner widget; add column to
`_build_results_card()`; populate from `TrendResult.points` in `_populate_table()`)

---

### VIZ-4 — History Page: RTT Chart Enhancements

**Problem**: The RTT chart in `history_page.py` is a bare matplotlib line. No threshold
reference, no area fill, no hover interaction — it looks like a placeholder chart.

**Fix**:
1. Shaded area: `fill_between()` under the RTT line at 20% alpha
2. Threshold reference line: dashed amber `axhline` at 100ms (the default "poor" threshold)
   with a right-edge label "100ms threshold"
3. Hover tooltip: `mpl_connect('motion_notify_event')` → show a floating annotation
   with exact RTT, jitter, and loss at the nearest data point when cursor is over the chart

**Files**: `ui/pages/history_page.py` (matplotlib chart setup + hover handler)

---

### VIZ-5 — Speed Test: History Line Chart

**Problem**: The speed test history is only a table. A user with 20 test results can't
see their trend at a glance — they have to read rows.

**Fix**: Add a matplotlib line chart above the history table. Two lines: download (ACCENT
blue) and upload (GREEN). X axis: date/time. Y axis: Mbps. Dots at each test point.
Hovering a dot shows the full test details in a floating annotation.
Chart updates on new test completion. Height: 140px fixed.

**Files**: `ui/pages/speed_test_page.py` (new `_HistoryChart` FigureCanvas widget above
`self._table`; populate from `MetricStore.query_speed_test_history()`)

---

### VIZ-6 — Monitor Overview: Event-Count Mini-Sparklines

**Problem**: Running monitor tiles (ARP, DHCP, Storm, Port Scan) show a status dot but
no sense of activity level. Users can't tell if the monitor has been quiet or busy.

**Fix**: For each running monitor tile, add a 80×16 QPainter bar chart showing event
counts per hour for the last 6 hours. Bars are 10px wide, colored by severity. Query
from MetricStore alert history filtered by rule prefix.

Stopped tiles do not show the sparkline. Update every 5 minutes.

**Files**: `ui/pages/monitor_overview_page.py` (new `_EventSparkline` painter widget;
per-tile data query from MetricStore)

---

### VIZ-7 — Protocol Visualizer: Inventory Name Overlay

**Problem**: Protocol nodes in the protocol visualizer are labeled by IP address. Users
who have named their devices must mentally cross-reference.

**Fix**: When building node labels in `protocol_animator.py` or `protocol_viz_page.py`,
cross-reference the IP against the last scan result (or MetricStore device records) to
look up `custom_name` or `hostname`. Node label format: "Router\n192.168.1.1" (name on
top line, IP on second line, smaller font). Fall back to IP-only if not found.

**Files**: `ui/pages/protocol_viz_page.py` or `modules/protocol_animator.py` (node label
builder); receives device name map via push from dashboard on scan completion

---

### VIZ-8 — Geo Map: Risk Heatmap Overlay (Toggle)

**Problem**: The geo map scatters dots uniformly. Areas with many high-risk IPs look the
same as areas with a single benign lookup.

**Fix**: Add a "Show heatmap" toggle button above the map. When on, draw a soft radial
glow (a matplotlib `contourf` or set of concentric `Circle` patches at low alpha) behind
each dot with risk score > 50. Radius and opacity scale with risk. Toggle stored in
QSettings. Does not affect dot clickability.

**Files**: `ui/pages/geo_map_page.py` (toggle button + heatmap draw logic)

---

## Section 3 — Filter & Search Improvements

Goal: Find anything in any table in under two seconds. Several high-density pages still
lack filtering. This section closes every remaining gap.

---

### FILTER-4 — CVE Page Text Search

**Problem**: The CVE tracker has a state filter dropdown but no text search. Finding a
specific CVE ID or package name requires reading the table row by row.

**Fix**: Add a `QLineEdit` search input to the left of the existing state filter combo.
Placeholder: "Filter by CVE ID, package, or host…". On each keystroke (200 ms debounce),
filter `self._rows` by matching any of: CVE ID, package name, host, or notes text.
Works in AND with the existing state filter combo.

Show a match count chip: "12 / 47" right-aligned in the toolbar.

**Files**: `ui/pages/cve_page.py` (search input in toolbar; filter logic in `_refresh()`)

---

### FILTER-5 — DHCP Lease Text Search

**Problem**: The DHCP lease page has no filter control at all. On networks with many
leases, finding a specific device requires scrolling.

**Fix**: Add a compact filter bar (QLineEdit) above the lease table. Placeholder: "Filter
by IP, MAC, or hostname…". Real-time row-show/hide filtering on keystroke. Show match
count chip.

**Files**: `ui/pages/dhcp_lease_page.py` (new filter bar + filter logic in `_refresh_table()`)

---

### FILTER-6 — Column Width Persistence (5 Tables)

**Problem**: Column widths in the 5 density-toggle tables (Devices, Connections, CVE,
Log Hub, DHCP) reset to defaults on every app launch. Users who have sized columns for
their data lose that work.

**Fix**: For each table, connect `horizontalHeader().sectionResized(int, int, int)` to a
slot that saves the new width to `QSettings` under a per-table key
(e.g. `"table/cve/col_widths"`). On `showEvent()` (not `__init__`), restore saved widths
before the table becomes visible.

Shared helper: `save_column_widths(table, key)` and `restore_column_widths(table, key)`
functions in a new `ui/table_utils.py` module. Call from each page.

**Files**: new `ui/table_utils.py`; `inventory_page.py`, `connections_page.py`,
`cve_page.py`, `log_hub_page.py`, `dhcp_lease_page.py`

---

### FILTER-7 — Connections Page: Group-by-Process Toggle

**Problem**: The connections page shows one row per connection. A browser with 40 open
connections floods the table and buries more interesting processes.

**Fix**: Add a "Group by process" toggle button in the Connections toolbar. When enabled:
- Collapse to one row per process name
- Columns: Process | PID | Connection count | External count | Risk level (worst)
- Click a row to expand it and see individual connections (nested, indented)
- Toggle state persisted in QSettings

When disabled: back to the current flat per-connection view.

**Files**: `ui/pages/connections_page.py` (grouping model + expand/collapse logic)

---

### FILTER-8 — Threat Intel Results Text Search

**Problem**: The threat intel page has an IP lookup field but no way to search or filter
the accumulated results table (all IPs checked against threat feeds).

**Fix**: Add a text search input above the results table. Matches IP address, country
name, or threat source/feed name. Real-time filtering. Works alongside any existing
severity/source filter if present.

**Files**: `ui/pages/threat_intel_page.py` (search input + filter logic)

---

### FILTER-9 — Timeline Text Search

**Problem**: The timeline page has source-category chips but no text search. Finding all
events for a specific device (e.g. "Pi 3B+" or "192.168.1.44") requires reading the
entire table.

**Fix**: Add a text search input to the timeline's control bar (left of the existing
source chips). Matches hostname, IP, or event description text. Real-time filtering.
Works in AND with the source chip filter.

**Files**: `ui/pages/timeline_page.py` (search input + combined filter logic)

---

### FILTER-10 — Log Hub: Filtered CSV Export

**Problem**: Users can see log data in the Log Hub but cannot export it for analysis in
other tools.

**Fix**: Add a small "↓ Export" button to the Log Hub control bar (right of the source
chips). Clicking writes the currently visible filtered rows (respecting source toggle +
text search + time range) as a CSV file via `QFileDialog.getSaveFileName`. Columns:
Timestamp, Source, Level, Message. Show a toast on completion.

**Files**: `ui/pages/log_hub_page.py` (export button + CSV write logic)

---

### FILTER-11 — Inventory Tag-Chip Filter

**Problem**: Devices can have tags (e.g. "iot", "trusted", "media") set via the label
dialog. But the main inventory table has no way to filter by tag — the global text search
does not filter by tag.

**Fix**: Add a tag-chip row below the main search bar. Populate dynamically from all
unique non-empty tags across all known devices. Each chip is toggleable; clicking it
adds/removes it from an active tag filter set. Multiple active chips = OR filter.
When no chips are active, all devices are shown (same as today).

**Files**: `ui/pages/inventory_page.py` (tag-chip row + combined filter logic in `_apply_filter()`)

---

### FILTER-12 — Notifications: Bulk Dismiss

**Problem**: After the app flags 20 events overnight, clearing them requires 20 individual
dismissals. There's no multi-select or bulk action.

**Fix**: Add multi-select checkboxes to the alert history table (leftmost column, visible
on hover or when any row is selected). When one or more rows are checked, show a floating
action bar at the bottom of the table:
- "Dismiss X selected" (marks acknowledged)
- "Snooze 1h" / "Snooze 8h" (bulk snooze)
- "Deselect all"

Match the pattern already used in Inventory bulk actions (V3 OUTPUT-5).

**Files**: `ui/pages/notifications_page.py` (checkbox column + bulk action bar)

---

### FILTER-13 — Speed Test History Date Filter

**Problem**: The speed test history table shows all tests with no date filter. On a
device with months of history this becomes unwieldy.

**Fix**: Add a date-range filter combo above the history table: "Last 7 days / Last 30
days / Last 90 days / All". Selecting a range re-queries `MetricStore.query_speed_test_history()`
with a `since` timestamp. Default: Last 30 days.

**Files**: `ui/pages/speed_test_page.py` (filter combo + re-query on change)

---

## Section 4 — Animations & Polish

Goal: Extend the V6 animation language to pages and interactions that weren't covered,
and fix visual inconsistencies that accumulated across sprints.

---

### ANIM-6 — KPI Tile Count-Up System-Wide

**Problem**: The count-up animation was added for the speed test (ANIM-5) but the
pattern hasn't spread. All other numeric KPI tiles across Connections, CVE, DHCP, Monitor
Overview, and History update instantly with `setText()`.

**Fix**: Create a lightweight shared `_AnimatedKpi` wrapper (a QLabel subclass with a
`set_value(int)` method that drives a `QVariantAnimation` over 400 ms InOutQuad). Apply
to KPI value labels in:
- `connections_page.py` (Total / Established / External / Blocked)
- `cve_page.py` (Open / Critical / High)
- `dhcp_lease_page.py` (Total / Active / Expired)
- `monitor_overview_page.py` (per-tile counts)

Gate with `_reduce_motion()` — instant on reduce-motion.

**Duration**: 400 ms `InOutQuad`
**Files**: new `ui/widgets/animated_kpi.py`; wire into 4 pages

---

### ANIM-7 — Overview Tile Hover Lift

**Problem**: Overview tiles have a hover border color change (ACCENT) but no physical
lift feel. The V6 north star ("Apple-level detail") calls for more depth.

**Fix**: On `enterEvent`, animate the tile's `pos().y()` upward by 2px over 120 ms
`OutQuart` using `QPropertyAnimation(self, b"pos")`. On `leaveEvent`, return to original
position over 80 ms. Simultaneously, adjust the tile's stylesheet shadow slightly on
hover (increase bottom-shadow from 0 to 2px).

Only fires when not in edit mode (drag handles visible). Respects reduce-motion.

**Duration**: enter 120 ms OutQuart, leave 80 ms OutCubic
**Files**: `ui/pages/overview_page.py` (`_BaseTile.enterEvent`, `leaveEvent`)

---

### ANIM-8 — Scan Progress Smooth Easing

**Problem**: The scan progress bar in the dashboard header advances in discrete steps
(per-host, ~0–100 in N jumps). The jerky progress bar undermines the premium feel.

**Fix**: When the progress bar's target value changes, animate smoothly from the current
value to the new target using `QPropertyAnimation` on the `value` property. Duration:
250 ms per step, `InOutSine`. If a new target arrives before the current animation
finishes, restart from the current animated position to the new target.

**Duration**: 250 ms per step, `InOutSine`
**Files**: `ui/dashboard.py` (scan progress bar — wrap in a `_SmoothProgressBar` subclass)

---

### ANIM-9 — Alert Badge Decay

**Problem**: When the user navigates to Notifications (alerts viewed), the red badge
on the rail button disappears instantly. This is abrupt and inconsistent with ANIM-3
(the thump on increment).

**Fix**: On badge clear (count reaches 0 or user visits Notifications), animate the
badge opacity from 1.0 → 0.0 over 400 ms `OutCubic` before hiding the badge widget.
The badge scale returns to 1.0 first if it was at a non-default scale from a prior thump.

**Duration**: 400 ms `OutCubic`
**Files**: `ui/dashboard.py` (`_RailButton` badge opacity clear animation)

---

### POLISH-12 — Modem & Mesh Signal Bar Widgets

**Problem**: `modem_page.py` and `mesh_router_page.py` show raw signal numbers (RSRP:
−95 dBm, RSRQ: −12 dB). Home users don't know the scales. They have to look up what
"−95 dBm" means.

**Fix**: Replace raw signal number labels with a `_SignalBar` QPainter widget:
5 vertical bars (like a phone signal icon). Bars filled based on:
- RSRP: < −110 = 1 bar, −110–−100 = 2 bars, −100–−90 = 3 bars, −90–−80 = 4 bars, > −80 = 5 bars
- Similar thresholds for RSRQ, SINR, SNR (values defined in a constant dict)

Bar fill color from `status_color()`. Raw value shown in a small tooltip. New widget in
`ui/widgets/signal_bar.py`.

Apply to all signal-strength fields on both pages.

**Files**: new `ui/widgets/signal_bar.py`; `ui/pages/modem_page.py`;
`ui/pages/mesh_router_page.py`

---

### POLISH-13 — KPI Tile Visual Consistency Pass

**Problem**: KPI tiles across pages have inconsistent heights (some 56px, some 64px,
some variable), label typography (7px, 9px, 10px), and value typography (18px, 20px,
22px). The app looks slightly inconsistent on pages side by side.

**Fix**: Audit all KPI tiles in: `connections_page.py`, `cve_page.py`,
`dhcp_lease_page.py`, `history_page.py`, `trend_page.py`, `monitor_overview_page.py`.
Standardize to a shared `_kpi_tile()` helper in `ui/table_utils.py`:
- Fixed height: 56px
- Label: 9px all-caps, TEXT_SECONDARY
- Value: 22px bold, TEXT_PRIMARY (or semantic color)
- Left border accent: 3px

This is a mechanical visual-only change — no logic changes.

**Files**: `ui/table_utils.py` (shared `_kpi_tile()` helper); 6 page files updated to use it

---

### POLISH-14 — Reports Page Chart Preview

**Problem**: The reports page likely shows a plain table or empty state. It exists in the
nav but gives no immediate data value.

**Fix**: Add a 140px matplotlib preview panel above the report table showing two overlaid
sparklines: device count over time (ACCENT line) and grade score over time (GREEN line),
both from the last 7 days of MetricStore data. X axis: dates. Shows loading state while
querying. Empty state if < 2 data points.

**Files**: `ui/pages/reports_page.py` (new preview chart above main content)

---

## Section 5 — Actions & Power Features

Goal: Common tasks that currently require navigation should be reachable in 1–2 clicks
from where the user already is.

---

### ACT-1 — Connections Page: Process-Path Rich Tooltip

**Problem**: The Connections page shows a short process name (e.g. "chrome.exe") but not
the full path or process context.

**Fix**: When hovering a process name cell, show a rich tooltip:
```
chrome.exe
C:\Program Files\Google\Chrome\Application\chrome.exe
PID 4821 · 34 connections · 3 external
```
Path and PID are already available in the connection data. Format using `setToolTip()`
with newline-separated text and `setToolTipDuration(5000)`.

**Files**: `ui/pages/connections_page.py` (`_build_row()` or table population — add
tooltip on the process cell)

---

### ACT-2 — CVE Page: Export Filtered CVEs

**Problem**: There's no way to get CVE data out of the app for sharing or ticketing.

**Fix**: Add an "↓ Export CSV" button to the CVE toolbar (right-aligned). Exports the
currently filtered rows (respects text search + state filter) including: CVE ID, package,
CVSS score, severity, state, owner, days open, host, notes. Timestamp appended to
filename. Show a toast on completion.

**Files**: `ui/pages/cve_page.py` (export button + CSV write)

---

### ACT-3 — Inventory: Scan Comparison View

**Problem**: Users can see the current device list but can't compare two scan results to
understand what changed over a longer period (e.g. "what was new two weeks ago?").

**Fix**: Add a "Compare scans" button in the Inventory toolbar. Opens a small dialog with
two dropdowns: "Scan A" and "Scan B", each populated with up to 20 past scan timestamps
from MetricStore. On "Compare", switch the table to comparison mode:
- Green rows: devices in B but not A (new)
- Red rows: devices in A but not B (disappeared)
- White rows: devices in both (unchanged)

Exit comparison mode with a "Back to live view" button.

**Files**: `ui/pages/inventory_page.py` (compare button + mode + MetricStore scan list query)

---

### ACT-4 — Speed Test: Set as Baseline per Result

**Problem**: Users have no way to mark a "good day" test as a reference to compare
future results against.

**Fix**: Right-click any speed test history row → "Set as baseline". The selected row
gets a ★ marker. All subsequent rows in the table show a delta chip: "+42 Mbps ↑" (GREEN)
or "−15 Mbps ↓" (RED) relative to the baseline's download. Baseline stored in QSettings.
Right-click baseline row → "Clear baseline" removes it.

**Files**: `ui/pages/speed_test_page.py` (right-click menu, delta cell rendering,
QSettings baseline store)

---

### ACT-5 — Timeline: Click Event → Jump to Page

**Problem**: The timeline shows events but clicking a row does nothing — users have to
manually navigate to the relevant page.

**Fix**: Single-click on a timeline event row navigates to the relevant page:
- Device JOINED / LEFT / DOWN / UP / RECOVERED → Inventory (`select_device(ip)`)
- Alert event → Notifications + auto-open alert drawer for that alert
- Scan complete → Home page (grade section)
- Certificate event → TLS & Exposure page
- Speed test result → Speed Test page (scroll to matching history row)

Uses the same `navigate_to` signal pattern already on the page.

**Files**: `ui/pages/timeline_page.py` (row click handler + `navigate_to` signal routing);
`ui/dashboard.py` (wire ACT-3 targets in existing signal chain)

---

### ACT-6 — DHCP: "Find in Inventory" per Lease Row

**Problem**: The DHCP lease page shows IP/MAC/hostname, but there's no way to get to
that device's full profile in Inventory without manually copying the IP.

**Fix**: Add a right-click context menu on the DHCP table: "Find in Inventory →" calls
`navigate_to.emit("Devices")` and then `InventoryPage.select_device(ip)`. Reuses the
popover → Inventory pattern established in V3.

**Files**: `ui/pages/dhcp_lease_page.py` (right-click context menu + `navigate_to` signal);
`ui/dashboard.py` (pass device selection downstream to InventoryPage)

---

### ACT-7 — Baseline Page: Schedule Auto-Snapshot

**Problem**: The baseline page has a manual "Take snapshot" button (V3 DEVICE-5). The
auto-snapshot setting (every N scans) is in Settings, but the baseline page doesn't show
or control it.

**Fix**: Add a one-line schedule strip in the baseline page header bar:
"Auto-snapshot: every 3 scans [Edit]". Clicking "Edit" opens an inline widget with a
spin box (1–10 scans). Persisted in the same QSettings key as the Settings page control.
Both places stay in sync. If auto-snapshot is off, shows "Auto-snapshot: off [Enable]".

**Files**: `ui/pages/baseline_page.py` (schedule strip, reads/writes same QSettings key
as `settings_page.py`)

---

### ACT-8 — Cert Page: Renew-Reminder Snooze

**Problem**: Certificates expiring in < 30 days show amber warning rows. These are
correct but can't be silenced for certificates that are known to be in renewal process.

**Fix**: Right-click an expiring certificate row → "Snooze reminder" submenu:
- Snooze 7 days
- Snooze 30 days

Stores a QSettings expiry key per certificate hostname+port. While snoozed, the row
renders in TEXT_MUTED styling instead of AMBER. A small "z" chip appears in the row.
Expiry check runs at row render time (not at snooze-set time). Matches the alert snooze
pattern from V2 ALERT-1.

**Files**: `ui/pages/cert_page.py` (right-click menu, QSettings snooze check in row
render)

---

## Section 6 — Settings & Education

Goal: Make the app self-teaching and configurable beyond the current three preset themes.

---

### SET-1 — Notification Channel Test Buttons

**Problem**: After configuring a notification channel (email, webhook, Telegram), users
must trigger a real alert to verify it works. There's no way to test without waiting.

**Fix**: Add a "Send test" button beside each configured notification channel row in the
Settings integrations card. Pressing sends a test notification through that specific
channel: subject "NetSentinel test message", body "This is a test from NetSentinel on
[hostname] at [timestamp]." Shows a toast with the result ("Test sent ✓" or "Failed: …").
Runs off the main thread (same worker pattern as existing notification sends).

**Files**: `ui/pages/settings_page.py` (test button per channel row, worker call)

---

### SET-2 — Appearance: Accent Color Picker

**Problem**: The three preset themes (Arctic Clean, Midnight Pro, Obsidian Neon) cover
the main use cases but offer no personalization within a theme. Power users want to tweak.

**Fix**: Add an "Accent color" row in the Appearance card below the theme picker. Show
6 preset accent swatches (Apple system blue, teal, indigo, orange, pink, yellow) plus a
"Custom…" swatch that opens `QColorDialog`. Selecting any swatch overrides the `ACCENT`
token in `ui/styles.py` at runtime and saves to QSettings. Override is applied on next
app start (same restart-to-apply pattern as theme changes). A preview chip shows the
selected color name.

**Files**: `ui/pages/settings_page.py` (accent row + swatch widgets); `ui/styles.py`
(read QSettings override on module load)

---

### SET-3 — Settings Export / Import

**Problem**: There's no way to back up or migrate settings between machines (e.g. when
reinstalling or moving to a new PC).

**Fix**: Add "Export settings (JSON)" and "Import settings" buttons in the Maintenance
card. Export: reads all QSettings keys/values and writes a JSON file via `QFileDialog`.
Import: reads a JSON file, shows a summary dialog ("This will change 14 settings. Continue?"),
then writes the values. Both operations run synchronously (settings files are tiny).
Sensitive values (API keys, SMTP password) are included but the export dialog warns
"This file contains credentials — store it securely."

**Files**: `ui/pages/settings_page.py` (export/import buttons); new helper function
`modules/settings_io.py`

---

### EDU-1 — Per-Page Help Panel (? in PageHeaderBar)

**Problem**: The dashboard has a contextual help drawer (the `?` button in the title bar)
showing page-specific help content. But it's a global overlay that requires knowing to
look in the title bar. Users on a new page don't see a visible help affordance.

**Fix**: Add a small `?` icon to the right side of every `PageHeaderBar` widget. Clicking
it opens a small `QFrame` popover anchored to the header (not a full overlay): 280px wide,
shows the page's `what` and `hidden` entries from the dashboard's `_HELP_CONTENT` dict.
Dismiss on outside click. The popover reuses the text content that already exists — no new
copy needed.

**Files**: `ui/widgets/page_header.py` (? icon + popover widget); `ui/dashboard.py`
(pass the relevant `_HELP_CONTENT` entry to each page's `PageHeaderBar` at construction)

---

### EDU-2 — Keyboard Shortcut Hints in Tooltips

**Problem**: Many actions have keyboard shortcuts (Ctrl+K, Ctrl+L, J/K, Ctrl+R) but
users discover them only via the `?` overlay. Tooltips on those actions don't mention the
shortcut.

**Fix**: For every toolbar button, nav item, and action that has a registered shortcut,
append the shortcut in muted text to the existing tooltip:
```
Open Log Hub [Ctrl+L]
```
Format: `existing_tooltip + f"\n{shortcut}"` where shortcut is rendered in a secondary
color via rich text if `setToolTip()` supports it (use HTML: `<br><span ...>`).
Apply to: Ctrl+K search, Ctrl+L log hub, Ctrl+R rescan, J/K nav, Ctrl+, settings,
Ctrl+B bandwidth.

**Files**: `ui/dashboard.py` (nav item tooltips); each relevant page's toolbar buttons

---

### EDU-3 — Feature Guide "New in V7" / "Updated" Badges

**Problem**: When the app ships a new version users don't know which features are new or
recently improved. The Feature Guide is a great place to surface this.

**Fix**: Add a `"badge"` field to each `_FEATURES` entry in `discover_page.py`. Values:
`None` (default, no chip), `"new"` (green chip, "New"), `"updated"` (amber chip, "Updated").
Render a small chip beside the feature name in the feature card. Set appropriate badges
for all items added or significantly changed in V7.

Badge chips auto-hide after 60 days based on the `"badge_until"` date field (ISO date
string). If no `badge_until` is set, badges display indefinitely.

**Files**: `ui/pages/discover_page.py` (`_FEATURES` list, card render logic)

---

## Section 7 — Prioritization Table

| Item | Section | Impact | Effort | Sprint |
|---|---|---|---|---|
| ✅ FILTER-4 — CVE text search | Filters | High | Low | 1 · v1.9.36 |
| ✅ FILTER-5 — DHCP text search | Filters | High | Low | 1 · v1.9.36 |
| ✅ FILTER-6 — Column width persistence | Filters | Med | Low | 1 · v1.9.36 |
| ✅ ANIM-6 — KPI count-up system-wide | Animations | Med | Low | 1 · v1.9.36 |
| ✅ POLISH-13 — KPI tile consistency | Polish | Med | Low | 1 · v1.9.36 |
| ✅ ACT-1 — Connections process tooltip | Actions | Med | Low | 1 · v1.9.36 |
| ✅ EDU-3 — Feature Guide badges | Education | Low | Low | 1 · v1.9.36 |
| ✅ FILTER-13 — Speed test date filter | Filters | Med | Low | 1 · v1.9.36 |
| HOME-1 — Grade ring upgrade + animation | Home | High | Med | 3 |
| ✅ HOME-2 — Week-over-week delta chip | Home | Med | Low | 2 · v1.9.37 |
| ✅ VIZ-3 — Trend sparklines | Viz | High | Med | 2 · v1.9.37 |
| ✅ VIZ-4 — History RTT chart enhancements | Viz | High | Med | 2 · v1.9.37 |
| ✅ VIZ-5 — Speed test history line chart | Viz | High | Med | 2 · v1.9.37 |
| ✅ OVERVIEW-1 — Tile click-to-expand | Overview | High | Med | 2 · v1.9.37 |
| ✅ OVERVIEW-5 — Tile data-age indicator | Overview | Med | Low | 2 · v1.9.37 |
| ✅ ACT-2 — CVE export CSV | Actions | Med | Low | 2 · v1.9.37 |
| ✅ HOME-1 — Grade ring + sweep animation | Home | High | Med | 3 · v1.9.38 |
| ✅ OVERVIEW-2 — Top Talkers tile | Overview | High | Med | 3 · v1.9.38 |
| ✅ OVERVIEW-3 — Recent Events tile | Overview | High | Med | 3 · v1.9.38 |
| ✅ OVERVIEW-4 — Trend Status tile | Overview | Med | Low | 3 · v1.9.38 |
| ✅ HOME-3 — Live events ticker | Home | Med | Low | 3 · v1.9.38 |
| ✅ HOME-4 — Speed mini-card sparkline | Home | Med | Low | 3 · v1.9.38 |
| ✅ ANIM-7 — Tile hover lift | Animations | Med | Low | 3 · v1.9.38 |
| ✅ ANIM-8 — Smooth progress bar | Animations | Low | Low | 3 · v1.9.38 |
| ✅ VIZ-6 — Monitor Overview sparklines | Viz | Med | Low | 3 · v1.9.38 |
| OVERVIEW-2 — Top Talkers tile | Overview | High | Med | 3 |
| OVERVIEW-3 — Recent Events tile | Overview | High | Med | 3 |
| OVERVIEW-4 — Trend Status tile | Overview | Med | Med | 3 |
| HOME-3 — Live events ticker | Home | Med | Med | 3 |
| HOME-4 — Speed mini-card sparkline | Home | Med | Low | 3 |
| HOME-5 — Diagnosis verdict summary | Home | Med | Low | 3 |
| ANIM-7 — Tile hover lift | Animations | Med | Low | 3 |
| ANIM-8 — Scan progress smooth easing | Animations | Med | Low | 3 |
| VIZ-6 — Monitor event sparklines | Viz | Med | Med | 3 |
| FILTER-7 — Connections group-by-process | Filters | High | High | 4 |
| FILTER-8 — Threat Intel text search | Filters | Med | Low | 4 |
| FILTER-9 — Timeline text search | Filters | Med | Low | 4 |
| FILTER-10 — Log Hub CSV export | Filters | Med | Low | 4 |
| FILTER-11 — Inventory tag-chip filter | Filters | High | Med | 4 |
| FILTER-12 — Notifications bulk dismiss | Filters | High | Med | 4 |
| ACT-5 — Timeline jump to page | Actions | High | Med | 4 |
| ACT-6 — DHCP find-in-inventory | Actions | Med | Low | 4 |
| EDU-1 — Per-page help panel | Education | High | Med | 4 |
| ✅ ACT-3 — Inventory scan comparison | Actions | High | High | 5 · v1.9.40 |
| ✅ ACT-4 — Speed test baseline | Actions | Med | Med | 5 · v1.9.40 |
| ✅ ACT-7 — Baseline auto-snapshot strip | Actions | Med | Low | 5 · v1.9.40 |
| ✅ ACT-8 — Cert snooze | Actions | Med | Low | 5 · v1.9.40 |
| ✅ VIZ-1 — Geo Map click-to-investigate | Viz | Med | Med | 5 · v1.9.40 |
| ✅ VIZ-2 — Bandwidth event annotations | Viz | Med | Med | 5 · v1.9.40 |
| ✅ VIZ-7 — Protocol Viz node labels | Viz | Med | Med | 5 · v1.9.40 |
| ✅ ANIM-9 — Alert badge decay | Animations | Low | Low | 5 · v1.9.40 |
| ✅ SET-1 — Notification test buttons | Settings | High | Med | 6 · v1.9.41 |
| ✅ SET-2 — Accent color picker | Settings | Med | Med | 6 · v1.9.41 |
| ✅ SET-3 — Settings export/import | Settings | Med | Med | 6 · v1.9.41 |
| ✅ POLISH-12 — Signal bar widgets | Polish | High | Med | 6 · v1.9.41 |
| ✅ POLISH-14 — Reports chart preview | Polish | Med | Med | 6 · v1.9.41 |
| ✅ VIZ-8 — Geo Map heatmap overlay | Viz | Low | Med | 6 · v1.9.41 |
| ✅ EDU-2 — Shortcut hints in tooltips | Education | Med | Med | 6 · v1.9.41 |

---

## Section 8 — Sprint Plan

### Sprint 1 — Quick wins ✅ SHIPPED v1.9.36

Low effort, immediately visible. Every item is a targeted addition to one file.

1. ✅ FILTER-4 — CVE text search (200 ms debounce, match-count chip)
2. ✅ FILTER-5 — DHCP text search (IP/MAC/hostname filter)
3. ✅ FILTER-6 — Column width persistence (`ui/table_utils.py` + 6 tables: Devices, Connections, CVE, Log Hub, DHCP, Speed Test)
4. ✅ FILTER-13 — Speed test history date filter (7d/30d/90d/All, default 30d)
5. ✅ ANIM-6 — KPI count-up system-wide (`ui/widgets/animated_kpi.py` + Connections, CVE, DHCP, Monitor Overview)
6. ✅ POLISH-13 — KPI tile visual consistency pass (`kpi_tile()` in `ui/table_utils.py`, 56px/22px standard)
7. ✅ ACT-1 — Connections process-path rich tooltip (exe_name + full_path + PID · N conn · N external)
8. ✅ EDU-3 — Feature Guide "new/updated" badges (badge chip renderer, "Updated" badges expire 2026-07-24)

---

### Sprint 2 — Visual data depth ✅ SHIPPED v1.9.37 (HOME-1 deferred)

Chart upgrades and home page improvements. Medium effort, high impact.

1. HOME-1 — Grade ring upgrade + sweep animation + score count-up *(deferred to Sprint 3)*
2. ✅ HOME-2 — Week-over-week grade delta chip
3. ✅ VIZ-3 — Trend page per-host mini-sparklines (`_MiniSparkline` QPainter; `TrendResult.points` field added)
4. ✅ VIZ-4 — History page RTT chart enhancements (dashed 100 ms threshold line + hover tooltip; `hideEvent` lifecycle)
5. ✅ VIZ-5 — Speed Test history line chart (140 px FigureCanvas above table; download/upload lines; hover annotation)
6. ✅ OVERVIEW-1 — Tile click-to-expand micro-detail (175→280 px, 280 ms OutQuart; DeviceCountTile top-5 hosts; RttSummaryTile top-3 with bar; AlertFeedTile with timestamps; "View full →" fallback; one-at-a-time collapse)
7. ✅ OVERVIEW-5 — Tile data-age indicator (grey/amber/red at 30 min/2 h; 60 s page-level refresh timer)
8. ✅ ACT-2 — CVE filtered CSV export (respects active text/state filter; timestamped filename; Days Open + Notes columns)

---

### Sprint 3 — New tiles + home depth ✅ SHIPPED v1.9.38

Overview becomes a configurable dashboard. Home is worth opening every morning.

1. ✅ HOME-1 — Grade ring upgrade + sweep animation + score count-up
2. ✅ OVERVIEW-2 — Top Talkers tile
3. ✅ OVERVIEW-3 — Recent Events tile
4. ✅ OVERVIEW-4 — Trend Status tile
5. ✅ HOME-3 — Live events ticker
6. ✅ HOME-4 — Speed mini-card sparkline
7. ✅ HOME-5 — Diagnosis verdict summary row *(was already shipped in v1.9.37)*
8. ✅ ANIM-7 — Overview tile hover lift
9. ✅ ANIM-8 — Scan progress smooth easing
10. ✅ VIZ-6 — Monitor Overview event-count sparklines

---

### Sprint 4 — Filters, actions, and education (shipped v1.9.39, 2026-05-26)

Close every remaining filter gap. Wire timeline events. Add per-page help.

1. ✅ FILTER-7 — Connections group-by-process toggle
2. ✅ FILTER-8 — Threat Intel text search
3. ✅ FILTER-9 — Timeline text search
4. ✅ FILTER-10 — Log Hub filtered CSV export
5. ✅ FILTER-11 — Inventory tag-chip filter
6. ✅ FILTER-12 — Notifications bulk dismiss
7. ✅ ACT-5 — Timeline click-event → jump to page
8. ✅ ACT-6 — DHCP "Find in Inventory" per row
9. ✅ EDU-1 — Per-page help panel (PageHeaderBar ? icon)

---

### Sprint 5 — Power actions + advanced visualization ✅ SHIPPED v1.9.40

Power user workflows: scan comparison, baseline, cert snooze. Bandwidth gets smarter.

1. ✅ ACT-3 — Inventory scan comparison view
2. ✅ ACT-4 — Speed Test set-as-baseline
3. ✅ ACT-7 — Baseline page schedule strip
4. ✅ ACT-8 — Cert page renew-reminder snooze
5. ✅ VIZ-1 — Geo Map click-to-investigate (enriched detail panel)
6. ✅ VIZ-2 — Bandwidth event annotations (device/alert ticks)
7. ✅ VIZ-7 — Protocol Visualizer inventory name overlay
8. ✅ ANIM-9 — Alert badge decay animation

---

### ✅ Sprint 6 — Settings, polish, education (v1.9.41 — complete)

Final polish. Settings become a proper configuration hub. Every page teaches itself.

1. ✅ SET-1 — Notification channel test buttons
2. ✅ SET-2 — Appearance accent color picker
3. ✅ SET-3 — Settings export / import
4. ✅ POLISH-12 — Modem & Mesh signal bar widgets
5. ✅ POLISH-14 — Reports page chart preview
6. ✅ VIZ-8 — Geo Map risk heatmap toggle
7. ✅ EDU-2 — Keyboard shortcut hints in tooltips

---

## Section 9 — Implementation Guidance (Top 3 Sprint 1 Items)

---

### FILTER-4 & FILTER-5 — CVE and DHCP Text Search (same pattern)

Both follow the identical pattern. Use CVE as the example.

Add to `cve_page.py` toolbar (in `_build_toolbar()` or equivalent):

```python
self._search_input = QLineEdit()
self._search_input.setPlaceholderText("Filter by CVE ID, package, or host…")
self._search_input.setFixedWidth(240)
self._search_input.setFixedHeight(26)
self._search_input.setStyleSheet(
    f"QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
    f" border:1px solid {BORDER}; border-radius:3px; padding:0 8px;"
    f" font-size:11px; }}"
    f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
)
self._search_timer = QTimer(self)
self._search_timer.setSingleShot(True)
self._search_timer.setInterval(200)  # 200 ms debounce
self._search_input.textChanged.connect(
    lambda: self._search_timer.start()
)
self._search_timer.timeout.connect(self._refresh)
self._match_lbl = QLabel("")
self._match_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
```

In `_refresh()`, add a pre-filter step:

```python
query = self._search_input.text().strip().lower()
if query:
    filtered = [
        r for r in self._rows
        if query in r.get("cve_id", "").lower()
        or query in r.get("package", "").lower()
        or query in (r.get("host") or "").lower()
        or query in (r.get("notes") or "").lower()
    ]
else:
    filtered = self._rows

# Existing state filter still applies on top of text filter:
state = self._filter_combo.currentText()
if state != "All States":
    filtered = [r for r in filtered if r.get("state") == state]

self._match_lbl.setText(f"{len(filtered)} / {len(self._rows)}")
self._displayed_rows = filtered
```

DHCP equivalent: filter on `ip`, `mac`, `hostname` fields.

---

### FILTER-6 — Column Width Persistence (shared helper)

Add `ui/table_utils.py`:

```python
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QTableWidget

def save_column_widths(table: QTableWidget, key: str) -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    widths = [table.columnWidth(i) for i in range(table.columnCount())]
    qs.setValue(f"table/{key}/col_widths", widths)

def restore_column_widths(table: QTableWidget, key: str) -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    widths = qs.value(f"table/{key}/col_widths", [])
    if widths:
        for i, w in enumerate(widths):
            if i < table.columnCount() and int(w) > 0:
                table.setColumnWidth(i, int(w))
```

In each page, connect the header's `sectionResized` signal once after table creation:

```python
self._table.horizontalHeader().sectionResized.connect(
    lambda _log, _old, _new: save_column_widths(self._table, "cve")
)
```

In each page's `showEvent()`:

```python
def showEvent(self, event) -> None:
    restore_column_widths(self._table, "cve")
    super().showEvent(event)
```

Table keys: `"devices"`, `"connections"`, `"cve"`, `"log_hub"`, `"dhcp"`.

---

### ANIM-6 — KPI Count-Up (shared widget)

Add `ui/widgets/animated_kpi.py`:

```python
from PyQt6.QtCore import QEasingCurve, QVariantAnimation
from PyQt6.QtWidgets import QLabel
from ui.theme import _reduce_motion

class AnimatedKpi(QLabel):
    """QLabel that count-up animates when its integer value changes."""

    def __init__(self, text: str = "—", fmt: str = "{}", parent=None):
        super().__init__(text, parent)
        self._target = 0
        self._fmt = fmt
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(
            lambda v: self.setText(self._fmt.format(int(v)))
        )

    def set_value(self, value: int) -> None:
        if _reduce_motion():
            self.setText(self._fmt.format(value))
            return
        try:
            current = int(self.text().replace(",", ""))
        except ValueError:
            current = 0
        self._anim.stop()
        self._anim.setStartValue(float(current))
        self._anim.setEndValue(float(value))
        self._anim.start()
```

Usage in any page — replace `kpi_val_label.setText(str(n))` with:

```python
# In __init__: create as AnimatedKpi instead of QLabel
from ui.widgets.animated_kpi import AnimatedKpi
self._kpi_total = AnimatedKpi("—")

# On data update:
self._kpi_total.set_value(len(connections))
```

---

## Architecture notes

- `ui/table_utils.py` is the shared home for `save_column_widths`, `restore_column_widths`,
  and the standardized `_kpi_tile()` helper. Sprint 1 creates it; later sprints use it.
- All new animation code must call `_reduce_motion()` from `ui/theme.py` before starting.
- New tile types (OVERVIEW-2, OVERVIEW-3, OVERVIEW-4) follow the `_BaseTile` subclass
  pattern already in `overview_page.py`. Do not modify `_BaseTile` base behavior.
- VIZ items that add matplotlib interactivity (`mpl_connect`) must disconnect handlers in
  `hideEvent()` to avoid dangling callbacks when the page is hidden.
- ACT-3 (scan comparison) is the highest-effort item in the backlog. If time-constrained,
  implement the dialog and scan selection first, then the diff rendering as a follow-on.
