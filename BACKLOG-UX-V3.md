# NetSentinel — UX Product Backlog V3

## Product Owner Statement

V1 built the features. V2 made them communicate. V3 makes them serve each other.

The app today is a collection of capable, isolated tools. A user can monitor ARP spoofing, track CVEs, run speed tests, and view TLS cert expiry — but these features don't know about each other. An alert fires, the user navigates to the right page, and finds themselves on an empty table they have to fill in from memory. The device they're investigating appears in Inventory, Connections, Threat Intel, CVE Tracker, and the Geo Map — but nowhere do those five views share a common device context.

**The test for V3:** A user gets an ARP Spoof Alert at 2am. At 9am they open the app. Within 90 seconds they can:
1. See exactly what triggered the alert (device, time, what changed)
2. See what that device was doing in the logs around that time — without navigating manually
3. Know if that device is new or a known device behaving differently
4. Decide to block, snooze, or mark resolved — from one place
5. Have confidence the threat is gone

This requires coherent data flow between Notifications → Alert Detail → Log Hub → Inventory → Connections. Right now, none of those handoffs exist. V3 builds them.

**Team:** 5 full-time developers. 4 one-week sprints. ~75 effective dev-days.

---

## Effort scale

| Size | Days | What it means |
|------|------|---------------|
| XS | 1 | Targeted edit to one file |
| S | 2 | A new method or component in one file |
| M | 4 | A new feature spanning 2–3 files |
| L | 7 | A new component + wiring across 4+ files |
| XL | 12 | Architectural change touching most of the app |

---

## Priority tiers

- **P0** — Feature exists but leaves user worse off than if it didn't (broken promise)
- **P1** — User cannot trust the data they're seeing (trust gap)
- **P2** — Correct data, but requires too many steps or too much prior knowledge (friction)
- **P3** — Works correctly, feels inconsistent or unpolished (perception gap)

---

## Backlog — all 24 items

| # | Item | Title | Epic | Priority | Size | Sprint |
|---|------|-------|------|----------|------|--------|
| 1 | TIME-1 | Global time range picker — sync all pages | Coherent Time | P1 | L | 1 |
| 2 | TIME-2 | "Jump to this time" — alert row opens Log Hub pre-filtered | Coherent Time | P1 | M | 1 |
| 3 | TIME-3 | History page: per-host filter (see one device's RTT trend) | Coherent Time | P2 | M | 2 |
| 4 | ALERT-1 | Alert detail panel — full context in a side drawer | Alert Intelligence | P0 | L | 1 |
| 5 | ALERT-2 | Alert source enrichment — contextual data per rule type | Alert Intelligence | P1 | M | 1 |
| 6 | ALERT-3 | One-click acknowledge from the Home action-needed card | Alert Intelligence | P2 | XS | 2 |
| 7 | ALERT-4 | Log Hub: "Show alerts near this entry" — ±5min correlation | Alert Intelligence | P2 | S | 3 |
| 8 | DEVICE-1 | Device quick-profile popover — right-click any MAC/IP in the app | Device Intelligence | P1 | L | 2 |
| 9 | DEVICE-2 | Inventory: live alert dot per device row | Device Intelligence | P2 | S | 2 |
| 10 | DEVICE-3 | CVE tracker: affected device count — link to filtered Inventory | Device Intelligence | P2 | M | 2 |
| 11 | DEVICE-4 | Connections: block/unblock with confirmation + undo toast | Device Intelligence | P0 | S | 1 |
| 12 | DEVICE-5 | Baseline: auto-snapshot on scan complete (opt-in in Settings) | Device Intelligence | P2 | M | 3 |
| 13 | OUTPUT-1 | Diagnosis history — last 5 results stored, accessible from Home | Actions & Output | P2 | M | 2 |
| 14 | OUTPUT-2 | Export from 5 pages: inventory (CSV), CVEs, baseline diff, alert history, diagnosis report | Actions & Output | P2 | L | 3 |
| 15 | OUTPUT-3 | Command palette upgrade: search recent alerts + known devices, not just pages | Actions & Output | P2 | M | 3 |
| 16 | OUTPUT-4 | Post-scan summary sheet: "3 new, 1 drift, 2 alerts" — one-card action hub after every scan | Actions & Output | P1 | M | 2 |
| 17 | OUTPUT-5 | Bulk device actions: multi-select in Inventory → tag / snooze alerts / export selection | Actions & Output | P2 | M | 3 |
| 18 | POLISH-1 | Rail live status dots for active monitors | Navigation & Polish | P1 | S | 1 |
| 19 | POLISH-2 | Section badge counts: CVE open, cert expiring, baseline drift | Navigation & Polish | P2 | M | 2 |
| 20 | POLISH-3 | Toast notification system — replace all status-bar label feedback | Navigation & Polish | P3 | M | 2 |
| 21 | POLISH-4 | Smooth page transition — 140ms crossfade between stack pages | Navigation & Polish | P3 | S | 4 |
| 22 | POLISH-5 | Theme toggle in title bar — one click, not buried in Settings | Navigation & Polish | P3 | XS | 4 |
| 23 | POLISH-6 | Right-click standardization: shared base menu across all tables | Navigation & Polish | P3 | M | 4 |
| 24 | SETTINGS-1 | Unified integrations status card in Settings | Settings Coherence | P2 | M | 3 |

---

## Sprint plan

### Sprint 1 — "The handoff works" (Week 1)
*Foundation items that unblock everything else.*

5 items × roughly 15 dev-days. All items that make alerts actionable and prevent dangerous actions.

- **TIME-1** (L) — Global time range
- **ALERT-1** (L) — Alert detail panel
- **ALERT-2** (M) — Alert source enrichment
- **DEVICE-4** (S) — Connections block confirmation
- **POLISH-1** (S) — Rail live dots

**Definition of done for Sprint 1:** After a scan and an alert, a user can click the alert, see full context in a side drawer, and navigate from that drawer to the time-matched Log Hub view — all without typing a single search query.

---

### Sprint 2 — "Devices are first-class" (Week 2)

- **TIME-2** (M) — Jump to alert time in Log Hub
- **ALERT-3** (XS) — One-click ack from Home
- **DEVICE-1** (L) — Device quick-profile popover
- **DEVICE-2** (S) — Inventory alert dot
- **DEVICE-3** (M) — CVE → Inventory link
- **POLISH-2** (M) — Section badges
- **OUTPUT-1** (M) — Diagnosis history
- **OUTPUT-4** (M) — Post-scan summary sheet
- **POLISH-3** (M) — Toast system

**Definition of done for Sprint 2:** Right-clicking any IP in the app surfaces the device's name, alert state, and one-click navigation to its full profile in Inventory. Diagnosis results don't vanish when the user navigates away.

---

### Sprint 3 — "Users can act and export" (Week 3)

- **TIME-3** (M) — History per-host filter
- **DEVICE-5** (M) — Baseline auto-snapshot
- **OUTPUT-2** (L) — Export from 5 pages
- **OUTPUT-3** (M) — Command palette upgrade
- **OUTPUT-5** (M) — Bulk device actions
- **ALERT-4** (S) — Log Hub alert correlation
- **SETTINGS-1** (M) — Unified integrations card

**Definition of done for Sprint 3:** User can export a complete diagnosis report and the current CVE list with one button click. Command palette finds "New device — iPhone" not just "Inventory."

---

### Sprint 4 — "Polish ships" (Week 4)
*Perception work that makes the app feel finished.*

- **POLISH-4** (S) — Page crossfade
- **POLISH-5** (XS) — Theme in title bar
- **POLISH-6** (M) — Right-click standardization
- Regression sweep and bug fixes across all 24 items

**Definition of done for Sprint 4:** App demo-able to a new user without them encountering a broken or confusing interaction. Every significant action has a visual confirmation. No page transition is jarring.

---

## Detailed specs

---

### TIME-1 — Global time range picker

**User moment**: User wants to investigate an incident from yesterday. Every page has its own time selector set to "last 24h". Changing them one by one is tedious and error-prone — by the time they've changed three pages, they can't remember if Inventory is in sync.

**What to build**: A persistent time range widget in the title bar (next to the scan button). Options: `1h · 6h · 24h · 7d · 30d · Custom`. When changed, emits a `global_time_range_changed(hours: float)` signal on a shared singleton (or via the dashboard). All pages that have time-windowed queries connect to this signal and re-query. Each page still keeps its local selector as an override — the global range is the default.

Pages to wire: History, Log Hub, Inventory Events, Alert History, CVE Tracker (days-open filter), Speed Test history, Cert page (last-check window), Service page (hours=24 becomes configurable).

**Acceptance**:
- Changing the global picker re-queries all open pages within 200ms
- A "Viewing: 24h" indicator is visible on each page header when global range is active
- Pages with a local override show "custom" and don't re-query on global change
- Custom range shows a from/to date picker dialog

**Files**: `ui/dashboard.py` (title bar widget + signal), all time-windowed pages

---

### TIME-2 — "Jump to this time" from alert

**User moment**: Alert row shows "ARP Spoof detected · 02:47 · 192.168.1.22". User clicks it. They get navigated to "Threat Intelligence" with an empty table. They have no idea what was happening in the logs at 02:47.

**What to build**: The alert detail drawer (ALERT-1) includes a "View in Log Hub" button. Clicking it: (1) sets the global time range to ±30 minutes around the alert timestamp, (2) filters Log Hub to the source that generated the alert (ARP = network RTT source; syslog alerts = syslog source), (3) navigates to Log Hub. User lands on Log Hub already showing the relevant window.

**Acceptance**:
- "View in Log Hub" button present in alert detail
- Log Hub opens at the correct time window with the alert's source pre-selected
- Time range widget in title bar reflects the jumped-to window
- "Back to alert" breadcrumb or back button returns to the alert detail

**Files**: `ui/dashboard.py`, `ui/pages/log_hub_page.py`, `ui/pages/notifications_page.py`

---

### TIME-3 — History page: per-host filter

**User moment**: History page shows RTT for all monitored hosts as overlapping lines. When one line spikes, the user can't tell which host it is without inspecting the legend. They have no way to isolate one host.

**What to build**: Add a host selector combo above the RTT chart — populated from all hosts with RTT history in the current time window. Default: "All hosts". When a host is selected, the chart shows only that host's series, and the device availability chart below highlights that host's rows.

**Acceptance**:
- Combo populated from MetricStore RTT history hosts
- Selecting a host re-renders both charts for that host only
- "All hosts" resets to the current multi-series view
- Selection persists for the session

**Files**: `ui/pages/history_page.py`

---

### ALERT-1 — Alert detail panel

**User moment**: Alert says "New Device · 192.168.1.88 · WARNING". There is no way to see: what kind of device is it, when did it first appear, what ports does it have open, is it in Threat Intel. The user gets a fact but not context.

**What to build**: Clicking any alert row (in Notifications → Alert History or in the Home "Action needed" card) opens a right-side drawer panel (same `QPropertyAnimation` slide pattern as the DEVICE-2 drawer in Inventory). The panel shows:

- **Header**: rule name, severity badge, timestamp, host IP/MAC
- **Device context** (from MetricStore): first seen, last seen, vendor, custom name if set, tags
- **Metric at alert time**: for RTT alerts — the RTT value that triggered; for CERT_EXPIRY — days remaining; for NEW_DEVICE — whether the MAC is in the known-devices table; for THREAT_INTEL — the reputation score
- **Suggested next step**: one CTA button linked to the most relevant action (matches current `_on_alert_history_row_clicked` logic but more specific)
- **Actions row**: Acknowledge · Snooze · View in Log Hub · Dismiss

No new data fetching — everything is already in MetricStore. This is a display layer.

**Acceptance**:
- Drawer opens in < 100ms on click
- Correct metric shown for each of the 7 rule types
- Ack button marks `acked_ts` in the store and updates the Status column in the alert table
- "View in Log Hub" implements TIME-2 behavior
- Closing drawer returns focus to the alert table

**Files**: `ui/pages/notifications_page.py`, `ui/pages/home_page.py` (shared drawer widget)

---

### ALERT-2 — Alert source enrichment per rule type

**User moment**: Alert history shows "Cert Expiring · cert.example.com · WARNING". The Status column says "Pending". There is no indication that this cert expires in 3 days, not 30. All warning-severity alerts look the same regardless of urgency.

**What to build**: For each rule type, query MetricStore for the current state of the thing that triggered the alert, and render it as a sub-label in the Rule column of the alert history table:

| Rule type | Sub-label |
|---|---|
| CERT_EXPIRY | "Expires in 3 days" |
| CERT_EXPIRED | "Expired 12 days ago" |
| DEVICE_GONE | "Last seen 6h ago" |
| HOST_DOWN | "Down for 2h 14m" |
| HIGH_RTT | "Current RTT: 340ms" |
| THREAT_INTEL | "Abuse score: 87/100" |
| SERVICE_DOWN | "Port 443 · last up 3h ago" |

Rendered as a second line in the rule cell in `TEXT_MUTED` at 10px.

**Acceptance**:
- Each supported rule type shows its sub-label
- Sub-labels are live (re-queried on each `_refresh_alert_history` call)
- Unknown rule types show nothing — no regression
- Column width accommodates two-line cells without truncation

**Files**: `ui/pages/notifications_page.py`, `modules/metric_store.py` (possible new query methods)

---

### ALERT-3 — One-click acknowledge from Home

**User moment**: Home shows "2 pending alerts" in the Action Needed card. User reads the alert summary and wants to acknowledge it without navigating to Notifications. Currently they must click "View Alerts →", navigate to Notifications, find the row, right-click, and select Acknowledge.

**What to build**: Each alert row in the Home Action Needed card gets a small "✓ Ack" button inline (16px height, muted border). Clicking it calls `store.acknowledge_alert(alert_id)` and removes the row from the card. If all alerts are acked, the card hides.

**Acceptance**:
- "✓ Ack" button visible on each alert row in the Action Needed card
- Clicking acks immediately and removes the row (no round-trip navigation)
- Notifications page alert history shows the updated ack state on next refresh

**Files**: `ui/pages/home_page.py`, `modules/metric_store.py`

---

### ALERT-4 — Log Hub: correlate with nearby alerts

**User moment**: User is reading Log Hub entries from a suspicious time window. They see a syslog message at 03:12 and wonder if any alert fired around that time. Currently there's no way to cross-reference without navigating to Notifications and manually filtering.

**What to build**: Right-click context menu on any Log Hub row adds "Show alerts near this time (±10 min)". Selecting it opens a lightweight inline panel below the table (similar to the existing `_challenge_banner`) showing alert rows from MetricStore within ±10 minutes of the row's timestamp. Each alert row has a "View →" link to open the alert detail drawer (ALERT-1).

**Acceptance**:
- Right-click menu on Log Hub rows includes the correlation option
- Panel shows up to 5 alerts, sorted by severity
- "No alerts in this window" shown if none found
- Panel dismissible with a close button

**Files**: `ui/pages/log_hub_page.py`

---

### DEVICE-1 — Device quick-profile popover

**User moment**: Connections page shows "192.168.1.47 — Process: chrome.exe". Is that device the user's laptop or their kid's Chromebook? They have to navigate to Inventory, search for the IP, open the drawer, and come back. By the time they're done, they've lost their place in Connections.

**What to build**: A shared `DevicePopover(QFrame)` widget that can be triggered from any table cell containing a MAC or IP address. Implemented as a lightweight floating `QFrame` (not a dialog — no focus steal) that appears on hover+delay or right-click → "Device info":

- Name (custom name or vendor/unknown)
- MAC address
- First seen / Last seen
- Active alerts badge (if any)
- Tags (from DEVICE-1 V2)
- Two buttons: "Open in Inventory →" · "View in Threat Intel →"

The popover is a singleton positioned near the triggering cell and dismissed on mouse-leave or Escape.

Pages to wire: Connections (Remote IP column), Log Hub (message text IP extraction), CVE Tracker (Affected column), Threat Intel (IP column), Inventory itself.

**Acceptance**:
- Popover appears within 600ms of right-click → "Device info" on any IP cell
- Shows correct data from MetricStore for known devices; shows "Unknown — not seen in scans" for unrecognized IPs
- "Open in Inventory" navigates and pre-selects the device row
- Works for both MAC and IP addresses

**Files**: `ui/widgets/device_popover.py` (new), `ui/pages/connections_page.py`, `ui/pages/log_hub_page.py`, `ui/pages/cve_page.py`, `ui/pages/threat_intel_page.py`

---

### DEVICE-2 — Inventory: live alert state per device row

**User moment**: Inventory shows 18 devices. User scans down the list. One of them has an active alert that fired 4 minutes ago. There is nothing in the Inventory table that indicates this. User has to navigate to Notifications separately to find out.

**What to build**: In `_refresh()`, after populating each row, query `store.get_recent_alerts(hours=24)` (already cached from the dashboard push cycle) and check if any alert's `host` field matches the device's IP or MAC. If so, set a coloured dot in a new Status column:

- `●` RED — CRITICAL or unacked HIGH alert in last 24h
- `●` AMBER — WARNING alert in last 24h, unacked
- `●` TEXT_MUTED — all acked or no alerts

Hovering the dot shows a tooltip with the alert rule name and time.

**Acceptance**:
- Status column visible as first column in Inventory table
- Dots update on each `_refresh()` call
- Tooltip shows "Host Down · 14 min ago" format
- Acking an alert in Notifications removes the dot on next Inventory refresh

**Files**: `ui/pages/inventory_page.py`

---

### DEVICE-3 — CVE tracker: affected device count + link

**User moment**: CVE Tracker shows "CVE-2024-1234 — CRITICAL — libssl". The user has no idea which of their devices runs libssl or how many are affected. The CVE row is abstract — not actionable.

**What to build**: In the CVE table's "Affected" column (if it exists) or a new "Devices" column: show the count of known devices whose vendor/hostname matches the CVE's service/product field (from the CVE import data). The count is a clickable link that navigates to Inventory and applies a filter for that product string.

For CVEs imported from scan results (where the affected IP is known), show the specific IP(s) as chips.

**Acceptance**:
- Device count shown for all CVEs where affected product/IP is known
- Clicking the count navigates to Inventory with appropriate filter pre-filled
- "0 devices" shown (not blank) when no match found
- Does not slow CVE table population (uses cached MetricStore data)

**Files**: `ui/pages/cve_page.py`, `ui/pages/inventory_page.py`

---

### DEVICE-4 — Connections: block/unblock with confirmation + undo toast

**User moment**: User clicks "Block Process" for a suspicious connection. Firewall rule is created immediately with no confirmation. If they misclicked — or if they blocked a legitimate process — there's no undo, and the only way to remove the rule is to find it in the "Blocked rules" collapsible panel and click Delete there.

**What to build**:
1. Replace the direct `_block_process()` call with a `QMessageBox.question()` confirmation: "Block [process] from making outbound connections? This creates a Windows Firewall rule named NS-Block-[process]." Buttons: Block · Cancel.
2. On successful block, show a toast notification (POLISH-3): "✓ Blocked [process] — Undo" with a 10-second window. Undo removes the firewall rule immediately.
3. The "Unblock" action in the blocked rules panel no longer needs a separate confirmation (already explicit) — but also shows a toast: "✓ Unblocked [process]".

**Acceptance**:
- Block action requires confirmation; Cancel leaves no rule
- Undo toast appears for 10 seconds after block; clicking Undo removes the rule
- After Undo, the connection row reappears as unblocked in the next auto-refresh
- Unblock action from the blocked rules panel does NOT require confirmation (it's already a secondary explicit action)

**Files**: `ui/pages/connections_page.py`

---

### DEVICE-5 — Baseline: auto-snapshot on scan complete

**User moment**: User runs a scan every morning. They've never thought to click "Take Snapshot" in Baseline — they don't even know Baseline exists. When a change does occur (a rogue device opens a port), there's no historical comparison available because no snapshots were ever taken.

**What to build**: Add a toggle in Settings → Network Scanning: "Auto-snapshot after every scan (keeps last 10)". Default: off. When enabled, `_on_scan_complete` in the dashboard calls `build_snapshot_from_scan` automatically, stores it with an auto-generated label ("Auto · 2026-05-23 09:14"), and purges snapshots older than the most recent 10.

If the new snapshot differs from the previous auto-snapshot (using existing `diff_snapshots`), update the rail badge for Baseline (POLISH-2) and emit a brief notification: "Baseline drift detected — 1 port change on 192.168.1.3".

**Acceptance**:
- Toggle in Settings persists in QSettings
- Auto-snapshot created silently after each scan when enabled
- Only the last 10 auto-snapshots kept
- Drift notification fires if any changes detected vs. previous auto-snapshot
- Manually-labeled snapshots are not counted toward the 10-snapshot limit

**Files**: `ui/pages/settings_page.py`, `ui/dashboard.py`, `modules/config_baseline.py`

---

### OUTPUT-1 — Diagnosis history

**User moment**: User runs a diagnosis and sees "DNS Resolution Failure · 3 findings". They navigate away to fix it. When they come back to check if it's resolved, the diagnosis page is blank. There is no record of what was found or whether it's better now.

**What to build**: Store the last 5 diagnosis results in `QSettings` (JSON-serialised: timestamp, symptom selected, verdict, list of finding titles + severities). On the Home page, below the grade card, add a "Last diagnosis: 3h ago — 2 findings" link. Clicking it navigates to the Diagnosis page and restores the stored result directly into state 2 (done view) — the results are shown immediately without re-running.

The Diagnosis page adds a "History" icon button (clock icon) in its header. Clicking opens a `QDialog` listing the 5 stored results with timestamps; selecting one restores that result.

**Acceptance**:
- Diagnosis result serialised and stored after every completed run
- Home "last diagnosis" link shows correct timestamp and finding count
- Clicking the link restores the exact finding cards (including remediation expanders)
- "Run Again" button in the restored view clears history state and runs fresh
- History dialog lists all 5 with timestamps and verdict summary

**Files**: `ui/pages/diagnosis_page.py`, `ui/pages/home_page.py`

---

### OUTPUT-2 — Export from 5 pages

**User moment**: Security-aware user wants to file a ticket about a CVE. They want to attach the CVE list. They screenshot the table. A more advanced user wants to send an engineer the inventory snapshot before a network change. They screenshot again.

**What to build**: Add an "Export" button (↓ icon, compact) to the toolbar of 5 pages. Each exports the current filtered view:

| Page | Format | Content |
|------|--------|---------|
| Inventory | CSV | All columns including custom name, tags, last seen |
| CVE Tracker | CSV | CVE ID, score, state, days open, affected |
| Baseline diff | HTML | Styled diff card — diff only, not full snapshot |
| Alert History | CSV | All columns in current filter view |
| Diagnosis report | Plain text | Timestamp, symptom, verdict, all findings + remediation steps |

All exports use `QFileDialog.getSaveFileName`. On success, show a toast (POLISH-3): "✓ Saved to filename.csv".

**Acceptance**:
- Export button visible in toolbar on all 5 pages
- Export reflects the current filter state (not all data)
- Files open correctly in Excel / a browser after export
- Toast shows the filename (not full path)
- Export is disabled when the table has 0 rows (button greyed out with tooltip "Nothing to export")

**Files**: `ui/pages/inventory_page.py`, `ui/pages/cve_page.py`, `ui/pages/baseline_page.py`, `ui/pages/notifications_page.py`, `ui/pages/diagnosis_page.py`

---

### OUTPUT-3 — Command palette upgrade

**User moment**: User presses Ctrl+K. Types "iphone". Sees no results because the command palette only searches page names, not data. Types "Inventory" instead, navigates, and searches for the device manually.

**What to build**: Extend `CommandPalette` with a new result section "Recent data" (shown below the existing "Pages" section). The data section includes:

- Last 10 unique known devices: "Device — 192.168.1.22 · iPhone · Apple" → opens Inventory and selects that row
- Last 5 alerts: "Alert — Host Down · 192.168.1.1 · 3h ago" → opens alert detail drawer (ALERT-1)
- Last 3 scans: "Scan — 2026-05-23 09:14 · 18 devices" → opens the most recent post-scan summary

Results are pre-loaded from MetricStore when the palette opens (not live-queried on each keystroke). Fuzzy-match against device name, IP, MAC, vendor, and alert rule name.

**Acceptance**:
- Palette shows "Recent data" section when ≥1 data item matches the query
- Selecting a device row opens Inventory and highlights that device
- Selecting an alert opens the alert detail drawer
- Palette opens in < 80ms (data pre-loaded, not queried on open)
- Empty query shows most recent 5 data items as suggestions

**Files**: `ui/command_palette.py`, `ui/dashboard.py`

---

### OUTPUT-4 — Post-scan summary sheet

**User moment**: Scan finishes. A toast appears: "Scan complete — 18 devices found". User dismisses it. They have no idea that 2 of those devices are new, 1 has a CVE match, and the baseline drifted. All that information exists — it just isn't surfaced at the moment the user is most ready to act.

**What to build**: After scan completes, instead of just a toast, slide up a non-modal summary sheet at the bottom of the window (think macOS share sheet — 240px tall, slides up from the bottom edge of the content area, pushes content up). It shows:

- **Devices**: "18 found · +2 new · 0 missing" — "+ new" is a link to Inventory filtered to new devices
- **Alerts**: "2 pending alerts" — link to Notifications
- **Baseline**: "1 port change detected" (only shown if DEVICE-5 is enabled and drift found) — link to Baseline
- **CVEs**: "0 new CVE matches" (only if CVE scan was included)
- **Close** button (×) at top-right; also auto-dismisses after 30 seconds

This replaces the fragmented state today: delta banner on Home + action-needed card + toast notification.

**Acceptance**:
- Sheet appears after every scan (not just first scan)
- Slides up in 200ms with an OutCubic easing
- Each section is a clickable link to the relevant page
- Sheet does not appear if user is already on the target page
- Auto-dismiss countdown visible as a thin progress bar along the sheet top edge
- "Don't show again" option persists in QSettings

**Files**: `ui/dashboard.py`, `ui/widgets/scan_summary_sheet.py` (new)

---

### OUTPUT-5 — Bulk device actions in Inventory

**User moment**: After a scan, user sees 4 new unknown devices they want to label as "IoT — untrusted". They have to double-click each one individually to open the label dialog, type the tag, and save. Four times.

**What to build**: Enable multi-row selection in the Inventory table (currently single-select). When ≥2 rows are selected, a bulk action bar slides in above the table (40px, accent border):

- "X devices selected · Tag all · Snooze alerts (1h / 8h) · Export selection · Deselect"

**Tag all** opens a single `QDialog` with a tags field and notes field — entries applied to all selected devices.
**Snooze alerts** calls `router.set_snooze()` for each selected device's IP across all rules.
**Export selection** runs OUTPUT-2's Inventory export but restricted to selected rows.

**Acceptance**:
- Ctrl+Click and Shift+Click work for selection (standard Qt multi-select)
- Bulk action bar appears/disappears based on selection count
- Tag dialog applies to all selected devices in one DB write
- Snooze applies per-IP prefix (snoozes all rules mentioning that IP)
- Deselect clears selection and hides the action bar

**Files**: `ui/pages/inventory_page.py`

---

### POLISH-1 — Rail live status dots for active monitors

**User moment**: User has ARP Watch and DHCP Monitor running. The nav rail shows their labels but nothing indicates they're actively running. User isn't sure if they left them on after the last session.

**What to build**: Each monitor rail button gets a 6px dot on its left edge (inside the button, not a badge). Color:

- `●` GREEN — monitor thread is alive AND last event was within 2× its expected interval
- `●` AMBER — thread alive but no events in longer than expected (possible missed events)
- `●` TEXT_MUTED — not running / never started

This reuses the `set_monitor_event_times()` data already pushed by `_push_monitor_pills()` in dashboard. The rail button's `set_badge()` method extends to accept a `dot_color` parameter.

**Acceptance**:
- Dots visible on all 6 monitor section buttons in the rail
- Colors update on the same 30s refresh cycle as monitor pills on Home
- Dots are 6px, flush left edge of the button, not overlapping the label
- Works in both compact and expanded rail states

**Files**: `ui/dashboard.py` (`_RailButton`, `_push_monitor_pills`)

---

### POLISH-2 — Section badge counts beyond notifications

**User moment**: User glances at the rail and sees the red `3` badge on Notifications. They don't notice that CVE Tracker has 2 open CVEs they haven't reviewed, or that a TLS cert is expiring in 5 days.

**What to build**: Extend the badge system to 3 additional rail buttons:
- **CVE Tracker**: count of Open-state CVEs (not Acknowledged or Remediated)
- **TLS Certificates**: count of certs expiring in ≤ 30 days (AMBER) or already expired (RED)
- **Baseline**: show a small "≠" drift indicator when the last auto-snapshot differs from the one before it

All three badge counts are queried in `_push_monitor_pills()` using existing MetricStore methods. No new background threads.

**Acceptance**:
- CVE badge shows Open count; hides when count is 0
- Cert badge shows expiring+expired count; hides when 0; RED if any expired, AMBER if expiring only
- Baseline drift indicator shows "≠" symbol (not a count); clears when baseline is re-captured clean
- All three update on the same 30s cycle

**Files**: `ui/dashboard.py`

---

### POLISH-3 — Toast notification system

**User moment**: User clicks "Export" in the CVE page. The status bar at the bottom of the window briefly shows "Saved to cve_export.csv" in a label that blends into the UI. They miss it. They also click Export a second time because they're not sure it worked.

**What to build**: A `ToastManager` singleton (`ui/widgets/toast.py`) that renders slide-in toast notifications in the bottom-right corner of the main window:

- **Success**: GREEN border, ✓ icon, 3 second auto-dismiss
- **Error**: RED border, ✗ icon, persists until clicked
- **Info**: ACCENT border, ℹ icon, 4 second auto-dismiss
- **Action**: ACCENT border, message + one button, persists until dismissed

Toasts stack vertically (up to 3 visible). Each slides in from the right (150ms), has an ×  dismiss button, and a thin progress bar showing auto-dismiss countdown.

Replace all current uses of status label feedback (`self._status_lbl.setText(...)`, `_db_feedback_lbl`, etc.) with `ToastManager.show(message, type)` calls across all pages.

**Acceptance**:
- Toast appears within 50ms of the triggering action
- Multiple toasts stack without overlapping
- Success toasts auto-dismiss in 3s; Error toasts stay until clicked
- Dismissing all toasts leaves no visual artifact
- Existing QLabel status indicators can remain (they're cheap) — toasts are additive, not replacement (to reduce scope)

**Files**: `ui/widgets/toast.py` (new), `ui/dashboard.py` (instantiate + position manager), wired in 5+ pages for export and block/unblock actions

---

### POLISH-4 — Smooth page transition (crossfade)

**User moment**: Clicking a nav item causes an instant, jarring stack-swap. On a fast machine it's imperceptible; on a slower machine it's a flash of blank or a pop.

**What to build**: In `_nav_rail_go_to()`, instead of `self._stack.setCurrentWidget(widget)`, animate a crossfade using `QGraphicsOpacityEffect` + `QPropertyAnimation`:
1. Fade out current page (80ms, opacity 1→0)
2. In `finished` callback: swap widget, fade in new page (80ms, opacity 0→1)

Total transition: 160ms. Imperceptible on fast machines, smooth on slow ones.

**Acceptance**:
- Transition visible but not distracting at normal pace
- Transition skipped when navigating programmatically from a worker signal (to avoid UI stalls during async callbacks)
- No regressions on pages that animate internally (monitor overview tiles, drawer panels)

**Files**: `ui/dashboard.py`

---

### POLISH-5 — Theme toggle in title bar

**User moment**: User is working at night and wants to switch to dark mode. They navigate to Settings → Appearance, change the theme, see a "restart required" message, and restart the app. This is 5 steps for a preference that should be one click.

**What to build**: Add a 🌙/☀ icon button to the right of the title bar (left of minimize). Clicking it cycles through the 3 available themes. The theme switch applies immediately — no restart required — by calling a new `apply_theme_live()` function that re-applies the QSS stylesheet and refreshes all open pages' colour references.

If live theme application proves too complex (many hardcoded colours in widgets), at minimum: clicking the button changes theme in QSettings and shows a toast (POLISH-3): "Theme updated — restart to apply."

**Acceptance**:
- Icon button visible in title bar
- Cycling works for all 3 themes (Arctic Clean, Midnight Pro, Obsidian Neon)
- Setting persists in QSettings across restarts
- If live apply is not achievable in the sprint, toast + restart is acceptable

**Files**: `ui/dashboard.py`, `ui/styles.py`

---

### POLISH-6 — Right-click standardization across all tables

**User moment**: User right-clicks a row in CVE Tracker. Nothing happens. Right-clicks in Inventory. Gets a context menu. Right-clicks in Connections. Gets a different context menu. Each page has invented its own right-click behaviour (or none at all).

**What to build**: Define a shared `_TableContextMenu` helper class in `ui/widgets/context_menu.py`:

```
_TableContextMenu(table, actions: list[tuple[str, Callable]])
```

Provides the standard base actions for all tables:
- **Copy cell** — copies the selected cell text to clipboard
- **Copy row** — copies the full row as tab-separated text
- *(separator)*
- *(page-specific actions injected by the caller)*

Wire this helper to tables in: CVE Tracker (currently none), History page (none), Baseline (none), Service Monitor (none), Cert page (none). Pages that already have custom menus (Inventory, Connections, Notifications) keep their custom menus but add the Copy actions at the top.

**Acceptance**:
- All 10 major tables in the app have a right-click menu with at least Copy Cell and Copy Row
- Copy actions write correctly to the clipboard
- Page-specific actions appear below the standard separator
- No existing right-click functionality is removed

**Files**: `ui/widgets/context_menu.py` (new), 5+ page files

---

### SETTINGS-1 — Unified integrations status card

**User moment**: User wants to see if their email notification is still configured. They navigate to Notifications, scroll to the Email card, look for the credential status. They also remember the modem logging interval is in Log Hub. And the cert monitoring targets are in TLS Certificates. There is no single place to answer "what integrations does this app have active right now?"

**What to build**: Add a new card at the top of the Settings page: "Active integrations". One row per integration, all on one screen:

| Integration | Status indicator | Action |
|---|---|---|
| Email notifications | ✓ Configured / ✗ Not set | Configure → |
| Webhook | ✓ Configured (URL) | Configure → |
| Pushover / ntfy / Telegram | ✓ / ✗ | Configure → |
| 5G Modem (Log Hub) | ● Logging · every 5 min | Configure → |
| Mesh Router (Log Hub) | ● Not enabled | Configure → |
| Syslog receiver | ● Listening on :514 | Configure → |
| SNMP traps | ● Listening on :162 | Configure → |
| TLS cert targets | 3 targets configured | Configure → |
| Service monitor targets | 2 targets configured | Configure → |

"Configure →" navigates to the relevant page or scrolls to the relevant card. All status data is read from QSettings — no live queries.

**Acceptance**:
- Card visible at top of Settings page, above all other cards
- All 9 integration rows shown with correct live status
- "Configure →" navigates correctly for each integration
- Status indicators use correct semantic colours (GREEN = active, TEXT_MUTED = not configured)
- Search bar (SETTINGS-1 from V2) finds "email" and highlights this card

**Files**: `ui/pages/settings_page.py`

---

## Cross-cutting notes

**Shared components being created this sprint**: `ui/widgets/device_popover.py`, `ui/widgets/toast.py`, `ui/widgets/context_menu.py`, `ui/widgets/scan_summary_sheet.py`. These four widgets will be used across many pages — build them in Sprint 1 even if the full wiring happens in Sprint 2-3.

**Data contract assumption**: All alert detail enrichment assumes `MetricStore.get_known_devices()` and `MetricStore.get_recent_alerts()` return sufficient data. If new fields are needed (e.g., `days_remaining` on cert alerts), add columns to the existing tables rather than new tables.

**Not in scope for V3**: New monitoring capabilities (new protocol monitors, new threat feeds, new hardware integrations). V3 is exclusively about making the existing 24 features serve each other. Any new module discovery during implementation is noted at session end and considered for V4.

---

## Success metrics for the month

By end of Sprint 4, the following user journeys should be completable without navigating more than 2 pages:

1. **Morning review**: From Home, see what needs attention, ack or snooze all alerts, verify no baseline drift — under 60 seconds
2. **Incident investigation**: From alert, reach the log window for that time, identify the involved device, see its history — under 90 seconds
3. **Weekly report**: Export inventory + open CVEs + alert history for the past 7 days — under 2 minutes
4. **New device review**: After scan, review 3 new unknown devices, label them, snooze their alerts — under 3 minutes

These are the product's promises to power users. V3 ships when all four journeys work end-to-end without requiring the user to know where to look.
