# NetSentinel — UX Product Backlog

## Product Owner Statement

NetSentinel has best-in-class detection. What it lacks is a user who knows it. Right now, a first-time user opens the app, sees a Home page with eight competing sections, presses Scan, and then has no idea what any of the results mean or what to do next. A recurring user who wants to set up alerting discovers that every rule is off by default, the test button gives no feedback, and the only way to know if a notification arrived is to wait. The logger — our most powerful continuous monitoring feature — is buried behind a collapsed accordion, and enabling modem logging does two things at once without telling you either of them.

These are not polish issues. They are the gap between a tool that works and a product people trust.

Every item on this backlog serves the same thesis Apple proved: people don't want features, they want outcomes. The outcome here is: *"I set this up once, it tells me when something is wrong, and I trust that it caught everything in between."*

---

## Priority tiers

- **P0** — broken promises (feature exists, user cannot reliably use it)
- **P1** — first-impression failures (new user journey, onboarding, first scan, first alert)
- **P2** — recurring-user friction (power user gets confused, gives up, or stops trusting the app)
- **P3** — polish (small inconsistencies that accumulate into "this feels unfinished")

---

## NUX — New User Experience

*The first 10 minutes define whether a user becomes a recurring user. Right now those 10 minutes are unguided.*

### NUX-1 · P0 · First run: no scan prompt on clean install

**What the user sees today:** Home page loads with "0 Devices" and six sections of tiles, most of which are empty or show zero. Nothing tells the user what to do first.

**What it should feel like:** iPhone setup wizard. One primary action, clearly labeled, with a short explanation of what it does and how long it takes.

**Acceptance criteria:**
- On first launch (no devices in DB), Home page collapses all secondary tiles and shows a single centered hero: "Discover your network" / "See every device, get a security score, and start monitoring — takes 30 seconds." / `[▶ Scan Network]` primary button.
- After the first scan completes, the hero animates out and the normal tile layout appears.
- Never shows again once at least one scan result is in the DB.

---

### NUX-2 · P1 · Post-scan: no "what happened and what's next" moment

**What the user sees today:** Scan completes. Devices table fills in. Nothing explains what the numbers mean, whether they look normal, or what the user should do next.

**What it should feel like:** After a health check, a doctor doesn't just hand you a printout — they say "here's what I found, here's what matters."

**Acceptance criteria:**
- After the first scan, a one-time "Your network at a glance" sheet slides up from the bottom (not a modal):
  - X devices found (N new, N recognized)
  - Network Grade badge (if already computed) or "Run a Network Grade →" inline link
  - One suggested action based on results: if no alerts → "Set up notifications →"; if open ports found → "Review open ports →"; if unknown devices → "Check unknown devices →"
- Sheet has an `×` dismiss. Dismissed permanently per profile. No "don't show again" checkbox — just dismiss once = gone.

---

### NUX-3 · P1 · No indication that background monitoring exists or is off

**What the user sees today:** Monitoring features (ARP Spoof Watch, DHCP Rogue, Broadcast Storm, Bandwidth Monitor) exist in the Analysis rail. None of them are running. The Home page shows their status tiles, but "Not monitoring" in muted grey is easy to skip.

**The trust gap:** If the user doesn't know monitoring is off, they trust the app is watching when it isn't. That trust will be broken the moment something happens that NetSentinel "missed."

**Acceptance criteria:**
- Home page, first section after devices: a single "Monitoring" row with three pill-badges — one each for ARP Watch, DHCP Watch, Broadcast Storm. Each pill is green ("Active") or amber ("Off"). Clicking any pill navigates to that feature's page.
- Shown permanently — not dismissible. This is the heartbeat.
- After the post-scan sheet (NUX-2) dismisses, if all three are off, show one inline nudge: "Monitoring is off — turn it on in 10 seconds →" that navigates to a new Monitoring Quick Setup sheet (NUX-4).

---

### NUX-4 · P1 · No quick-setup path for monitoring + alerts together

**What the user sees today:** To get monitoring and alerts working requires: enabling monitoring on 3 separate Analysis pages, then going to Notifications, adding an SMTP/webhook destination, then enabling individual rules, then testing each one. There is no guided path. Most users never complete it.

**What it should feel like:** Onboarding checklist (like Notion's "5 things to get started"). Not a wizard — a persistent sidebar card that tracks progress and disappears when done.

**Acceptance criteria:**
- "Setup" card on Home page (collapsible, not dismissible until all steps complete):
  1. ☐ Run your first scan
  2. ☐ Turn on ARP Spoof Watch
  3. ☐ Add a notification channel
  4. ☐ Enable at least one alert rule
  5. ☐ Run a Network Grade
- Each step is a clickable link that navigates to the relevant page.
- Steps auto-check as the user completes them (read from settings/DB).
- Card collapses (not disappears) once all five are done. User can re-expand from a small "✓ Setup complete" chip in the corner.

---

### NUX-5 · P2 · Feature Guide has no "start here" for new users

**What the user sees today:** Feature Guide lists every feature alphabetically by group. A new user has no idea which five features matter most for them.

**Acceptance criteria:**
- Add a "Start here" group at the top of Feature Guide (above Security) with 4–5 curated entries: Devices, Network Grade, What's Wrong?, ARP Spoof Watch, Notifications. Each entry has a "Why this matters" one-liner.
- Add a "New in this version" group that shows the 3 most recently added features (hardcoded list updated with each release).

---

## LOG — Logger / Log Hub

*The most important feature. Also the most hidden. A user who discovers it trusts NetSentinel completely. A user who never discovers it thinks the app only does scans.*

### LOG-1 · P0 · Modem/mesh logging toggle does two things, communicates neither

**What happens today:** Clicking the "Modem" toggle in Log Hub does two things: (1) shows/hides modem log rows in the table, and (2) starts or stops writing to the `modem_signal_log` DB table — a permanent change with data-loss implications. These are the same toggle with no distinction.

**The user experience failure:** A user who hides modem logs to declutter the table has unknowingly stopped recording modem history. They discover this six weeks later when they need the data for an ISP support ticket and it isn't there.

**Acceptance criteria:**
- Split into two controls: a **visibility eye icon** (show/hide rows in table, does not affect DB logging) and a **"Log to DB" toggle** that controls DB writes.
- "Log to DB" toggle shows a one-time confirmation on first enable: "Modem logs will be saved to your local database. This lets you review history later. Takes ~2 KB/day."
- "Log to DB" toggle shows an amber confirmation on disable: "Stop logging? You won't be able to review modem history going forward."
- Same pattern applies to Mesh toggle.

---

### LOG-2 · P0 · Scan Config accordion is invisible to first-time users

**What happens today:** The log interval for each source (how often modem/mesh data is sampled) lives inside a "Scan Config ▸" collapsed accordion. 99% of users will never open it.

**The consequence:** Users wonder why their modem log only has 10 entries after a week. The default interval is 5 minutes — fine — but there's no indication it's configurable or that it's even running.

**Acceptance criteria:**
- Replace accordion with a persistent inline header row per source (Modem, Mesh):
  `● Modem  [every 5 min ▾]  [Logging ●]`
  - The interval dropdown is always visible, not hidden.
  - The logging status dot is always visible (green = logging, grey = off).
- Remove the Scan Config accordion entirely.

---

### LOG-3 · P1 · No indication that the logger is running (or not) from outside Log Hub

**What happens today:** A user enables modem logging in Log Hub, navigates away, and has no idea if it's still running. The Home page shows no logger status. The rail nav shows no badge.

**Acceptance criteria:**
- Log Hub rail item gets a green dot badge when any source is actively logging to DB. Grey dot when none are logging. No dot when Log Hub hasn't been configured.
- Home page: add "Network Logger" as a fourth pill in the Monitoring row (NUX-3). Shows "3 sources" or "Off".

---

### LOG-4 · P1 · 500-row cap silently discards data

**What happens today:** The live table caps at 500 rows. When that cap is hit, old rows silently disappear. A user scrolled to the bottom, watching a problem unfold, suddenly loses context.

**Acceptance criteria:**
- When the cap is reached, show a banner above the table: "Showing last 500 entries — older entries are in your database. [Export log →]"
- "Export log" opens a date-range picker that exports filtered rows as CSV.
- Consider raising the in-memory cap to 2000 — 500 rows fills in ~20 minutes at high frequency.

---

### LOG-5 · P1 · Live challenge detection is invisible from within Log Hub

**What happens today:** `log_hub_page.py` emits `live_challenge_detected` — but this signal goes to the dashboard's status bar. A user watching the Log Hub table during an incident has no idea a challenge event was detected.

**Acceptance criteria:**
- When `live_challenge_detected` fires, show an inline amber banner at the top of the Log Hub table: "Live challenge detected at 14:32 — [View alert →]" that links to the alert in the Notifications log.
- Banner auto-dismisses after 60 seconds or on next log row after the challenge.

---

### LOG-6 · P2 · No way to search or filter the log table

**What happens today:** The log table is a flat chronological list. A user debugging a specific IP or event type has no way to filter.

**Acceptance criteria:**
- Add a search bar above the table: filters rows by source, IP, message content. Live filter (no enter required).
- Add a source filter chip bar: [All] [Modem] [Mesh] [Syslog] [SNMP] — replaces or supplements the toggle bar.
- Chips and search compose: selecting "Modem" chip + typing "RSRP" shows only modem rows containing that string.

---

### LOG-7 · P2 · No time-range filter for historical review

**What happens today:** The table shows the current in-memory live feed. There is no way to ask "show me what happened between 2am and 3am yesterday."

**Acceptance criteria:**
- Add "Live" / "History" toggle at the top of Log Hub.
- "History" mode shows a date + time range picker. Query is executed against all three DB log tables and merged chronologically.
- Exports remain available in history mode.

---

### LOG-8 · P3 · Source toggle bar label is unclear ("Modem" not "5G Modem")

**What happens today:** The source bar just says "Modem" — but the modem page is titled "5G Modem Signal". For users with non-5G modems or multiple hardware types, this is ambiguous.

**Acceptance criteria:** Source toggle labels match the full hardware page name: "5G Modem", "Mesh Router", "Syslog", "SNMP Traps". If a modem plugin is not connected, the "5G Modem" toggle is disabled with tooltip "Connect a modem plugin to enable modem logging."

---

## NOTIF — Notifications Setup Flow

*Getting your first alert working should take 2 minutes. Right now it takes 20, involves several invisible defaults, and gives you no confirmation that it worked.*

### NOTIF-1 · P0 · All alert rules are off by default — no indication of this anywhere

**What happens today:** A user adds an SMTP channel, saves it, and assumes they'll get alerts. They won't — every rule in the Rules tab is off by default. There is no warning, no nudge, no count badge showing "0 rules enabled."

**The user discovers this** when their device goes offline and they get no email. They open Notifications, see 47 rules, and have no idea which ones matter or why none are on.

**Acceptance criteria:**
- Notifications page header shows a persistent badge: "X rules active" (or "No rules active" in amber if zero).
- On first visit to Notifications after adding a channel: show a one-time inline banner: "You have 0 rules enabled. Rules control which events trigger a notification — enable at least one to get started. [Enable recommended rules →]"
- "Enable recommended rules" enables a curated default set: Device Offline, New Unknown Device, ARP Spoof Detected, Config Drift, Network Grade Drop. All five toggled on in one click.

---

### NOTIF-2 · P0 · Test button gives no feedback on failure

**What happens today:** A user clicks "Send test" for an SMTP channel. If it succeeds: a green toast appears. If it fails: the button re-enables. Nothing else. No error. No log. No hint about what went wrong.

**The user experience failure:** The user tries a second time, gets the same silence, and concludes the feature is broken. They are right — but for a reason that could be explained.

**Acceptance criteria:**
- On test failure, show an inline error below the channel form with the actual exception message (SMTP auth failure, timeout, TLS error, etc.).
- On test success, show green checkmark inline AND send a test notification that includes the text "If you received this, NetSentinel alerts are working. ✓"
- Failure state persists until the user edits any field (at which point it clears, indicating they should test again).

---

### NOTIF-3 · P1 · Keychain storage of SMTP credentials is invisible

**What happens today:** Passwords are stored via OS keychain — the right call. But the user has no idea. They see a plain password field, save, and the next time they open settings the field is blank. They assume their password was lost.

**Acceptance criteria:**
- Below the password field: a persistent note "Stored securely in your OS keychain — not in any file" with a lock icon.
- When the form loads and a keychain entry exists: password field shows `●●●●●●●●` placeholder and a "Change password" link. Clicking "Change password" clears the field for re-entry.

---

### NOTIF-4 · P1 · Delivery log has no "Status" column

**What happens today:** Delivery log shows Timestamp, Channel, Event. You can see what was sent but not whether it was delivered.

**Acceptance criteria:**
- Add "Status" column: ✓ Delivered, ✗ Failed (with tooltip showing the error), ⟳ Pending.
- Failed rows are highlighted with a subtle red background.
- Clicking a failed row opens a detail panel with the full error and a "Retry →" action.

---

### NOTIF-5 · P2 · Escalation channel UX is confusing

**What happens today:** "Escalation" is a second channel that fires when the primary channel fails. This is a power feature. But it's presented as a flat field next to the primary channel with no explanation. Most users either ignore it or think it's a required field.

**Acceptance criteria:**
- Move escalation into an expandable "Advanced: Escalation" section below each channel, collapsed by default.
- Add explainer text: "If this channel fails to deliver, NetSentinel will try the escalation channel instead."
- Show a visual flow: `[Primary] → fails → [Escalation]`.

---

### NOTIF-6 · P2 · No history of which alerts fired, only delivery log

**What happens today:** Delivery log shows deliveries. But a user asking "did ARP spoof watch fire last night?" has to correlate delivery timestamps with monitoring events mentally.

**Acceptance criteria:**
- Add "Alert History" tab (beside Delivery Log): shows every triggered alert with Type, Device/IP, Time, and Delivery Status.
- Clicking a row shows the alert detail and navigates to the relevant monitoring page.

---

## NAV — Navigation & Discovery

*The rail nav is well-structured. The problem is that users don't know what's inside sections they haven't explored, and there's no signal that something new is waiting for them.*

### NAV-1 · P1 · Analysis section has no ambient signal of what's running or what fired

**What happens today:** The Analysis rail section button shows "Analysis" with a count of active items. But there's no indication inside the section of what's running vs. what's idle, or whether any item has a pending alert.

**Acceptance criteria:**
- In the Analysis flyout, each item that has an active monitor shows a green dot to the left of its label.
- Each item that has an unacknowledged alert shows an amber dot.
- These dots pull from in-memory state, not from DB — lightweight.

---

### NAV-2 · P1 · Command palette (Ctrl+K) doesn't search monitoring state

**What happens today:** Ctrl+K searches page names. A user typing "arp" finds "ARP Spoof Watch" but gets no indication whether it's running.

**Acceptance criteria:**
- Command palette results for monitoring pages include their state: `ARP Spoof Watch  ●  Monitoring` or `ARP Spoof Watch  ○  Not running`.
- A result for a non-running monitor has a secondary action "Start monitoring →" that navigates to the page and starts it.

---

### NAV-3 · P2 · No "Recently visited" or "Pinned" quick access visible at a glance

**What happens today:** Pins to Quick Access work, but a user has to right-click a flyout item to discover pinning exists. The N8 hint ("Right-click any page to pin it ★") added in the last sprint helps, but pinned items live at the top of the rail as unlabeled items.

**Acceptance criteria:**
- Pinned items at the top of the rail have a visible label (not just an icon) when fewer than 4 are pinned.
- "Quick Access" section label appears above the pinned items when any exist.
- First-time use: after the first time a user visits 3 different Analysis pages, show a one-time toast: "Tip: right-click any page to pin it for faster access."

---

### NAV-4 · P3 · Flyout closes immediately on click — no visual confirmation of destination

**What happens today:** User clicks a flyout item, flyout closes, page transitions. This is fast but feels abrupt — there's no visual connection between the click and the resulting page.

**Acceptance criteria:**
- Clicked flyout item highlights (filled background) for 120ms before the flyout closes.
- No animation delay — purely the highlight, then close. Snappy but confirms the tap.

---

## FLOW — Cross-page Workflows

*The app has deep features but they don't tell each other what happened. A user investigating an alert should be able to follow a thread across pages without losing context.*

### FLOW-1 · P0 · No way to un-dismiss a permanently dismissed banner

**What happens today:** Several banners (Npcap missing, theme notice, compat notices) are dismissible and store that dismissal permanently in QSettings. There is no way to un-dismiss them.

**The failure case:** A user dismisses the Npcap install banner, installs Npcap, reinstalls the app, and the banner is gone. They expect to see confirmation that Npcap is now detected — but there's nothing.

**Acceptance criteria:**
- All permanently dismissed banners have a matching re-show trigger based on state: Npcap banner re-appears if Npcap is no longer detected (state changed). It should never be "permanently gone if state changes."
- Settings page (or Help panel) includes "Reset all dismissed notices" action. One click restores all banners.

---

### FLOW-2 · P1 · Alert → investigation flow drops the user at the top of a page

**What happens today:** XF2 (alert navigate) routes to the right page. But the user lands at the top of that page with no filter or highlight showing why they arrived. They have to mentally re-locate the device or event.

**Acceptance criteria:**
- Alert navigation passes context to the destination page:
  - Device IP/MAC → Devices table scrolls and selects the row (already done for XF6; apply same pattern here)
  - Port Scan alert → Port Scan (TCP) page pre-fills the IP from the alert
  - Threat Intel alert → Threat Intel page filters by the flagged IP
  - Live Bandwidth alert → Bandwidth page highlights the device row

---

### FLOW-3 · P1 · Diagnosis results have no "share" or "copy" action

**What happens today:** The "What's Wrong?" diagnosis page produces a detailed report. If a user wants to share it with ISP support or a sysadmin, they screenshot it or retype it.

**Acceptance criteria:**
- Diagnosis result has a "Copy report" button that puts a plain-text summary on the clipboard.
- Format: "NetSentinel Diagnosis Report — [date] / [verdict] / Findings: [list] / Recommended actions: [list]"
- Same clipboard output as the ISP Report export flow.

---

### FLOW-4 · P2 · Security Overview doesn't exist as a page (XF5 from old backlog)

**What happens today:** Network Grade has "Fix this →" links. ARP Spoof Watch, DHCP Rogue, Broadcast Storm, IoT anomalies are all separate pages. There is no single view that says "here is your current security posture."

**The user need:** After setting everything up, a user wants a single page they can glance at to confirm "all green." Right now they have to visit six pages.

**Acceptance criteria:**
- "Security Overview" page in Analysis section (between IoT Behaviour and 802.11 Monitor).
- Shows status tiles for each detection monitor: ARP Spoof, DHCP Rogue, Broadcast Storm, IoT anomaly count, open port count from last scan, CVE match count.
- Each tile is clickable → navigates to that feature's page.
- Network Grade score tile at top. No new logic — purely aggregating existing state.

---

### FLOW-5 · P2 · "What to do next" suggestions in Diagnosis are empty (UX3 carry)

**What happens today:** DiagnosisPage shows findings. Recommended actions are generic (e.g., "Check your DNS server"). They don't link to the specific NetSentinel feature that addresses the issue.

**Acceptance criteria:**
- Each finding type maps to a specific CTA:
  - DNS failure → "Run DNS lookup in Tools →"
  - High latency → "Check Live Bandwidth →"
  - ARP conflict → "Start ARP Spoof Watch →"
  - Firewall block → "Review open ports →"
  - Device unreachable → "Check Availability History →"
- CTAs appear as inline `[Navigate →]` flat buttons after the finding description.

---

## RECUR — Recurring User Power Features

*A user who opens NetSentinel every day needs a different experience than a new user. They want signal, not setup. They want to confirm things are fine, or jump straight to what's wrong.*

### RECUR-1 · P1 · Home page on return visit: still shows setup-oriented layout

**What happens today:** A recurring user who has everything configured sees the same Home page layout as a new user — scan button prominent, setup tiles visible. They want a dashboard, not a starting point.

**Acceptance criteria:**
- After NUX-4 setup checklist is complete and at least 5 scans are in the DB, Home page reorganizes:
  - Primary section: Monitoring status (ARP, DHCP, Broadcast, Logger pills from NUX-3)
  - Secondary: Network Grade + last scan timestamp + "Rescan" small button
  - Tertiary: Recent alerts (last 3) with "View all →" link
  - Hidden: Scan hero button (still accessible via F5 or "Rescan")
- This is not a separate mode — just a layout that emerges naturally as the user completes setup.

---

### RECUR-2 · P2 · No weekly/monthly summary of what NetSentinel caught

**What happens today:** A recurring user has no ambient signal of value delivered. They can check Inventory Changes, Delivery Log, etc. — but there's no "here's what happened this week" moment.

**Acceptance criteria:**
- Weekly summary notification (opt-in, off by default) sent at a user-chosen time each Sunday.
- Content: devices seen, new unknown devices, alerts fired, config drift events, CVE matches.
- Toggle in Notifications page: "Weekly digest" with time-of-day picker.
- Also available on demand: "Generate weekly summary" button in Notifications, outputs to clipboard.

---

### RECUR-3 · P2 · No shortcut to "repeat last action"

**What happens today:** A recurring user who runs a port scan on their NAS every week has to: navigate to Port Scan, enter the IP, select TCP, run scan. Four steps, same every time.

**Acceptance criteria:**
- Command palette (Ctrl+K) includes a "Recent actions" section showing the last 5 actions with context (e.g., "Port scan · 192.168.1.50 · TCP", "DNS lookup · 8.8.8.8").
- Selecting a recent action re-runs it immediately (navigating to the page with pre-filled inputs).
- Stored in QSettings, max 10 entries, per-profile.

---

### RECUR-4 · P3 · Trend Forecasts page has no "this week vs. last week" at a glance

**What happens today:** Trend Forecasts shows a chart. The chart requires interpretation. A user wanting "is my latency getting worse?" has to stare at a line.

**Acceptance criteria:**
- Above the chart: a single headline stat. "RTT this week: 14ms avg (↑ 3ms vs. last week)" in green/amber/red based on direction and magnitude.
- This is a QLabel computed from the last 14 days of RTT log data — no new ML, just averages.

---

## VC — Visual Consistency Carry

### VC3 · P2 · Loading states are inconsistent

**What happens today:** Some pages show a spinner, some show a skeleton (SK1 now done for Devices), some show nothing. A user who navigates to a page and sees it blank for 2 seconds assumes nothing is happening.

**Acceptance criteria:**
- All pages that have a fetch/compute step (Port Scan, DNS Lookup, Trace, Network Grade, etc.) show a consistent loading state: either the SK1 skeleton row pattern or a centered spinner with a one-line label ("Scanning ports… this may take up to 30 seconds").
- Pages that complete in <300ms do not show a loading state (flash avoidance threshold).

---

### VC5 · P3 · Section headers in the flyout have no visual weight hierarchy

**What happens today:** Flyout section headers (e.g., "Monitor", "Analysis", "Tools") are plain text labels. Flyout items are only marginally smaller. The hierarchy is present but not felt.

**Acceptance criteria:**
- Section headers are uppercase, letter-spaced (0.08em), 9px, `TEXT_MUTED` color — clearly categorical, not navigable.
- Items are 11px, `TEXT_PRIMARY`, with left padding for indentation.
- This matches the macOS sidebar visual grammar users are already trained on.

---

## Implementation order (recommended)

These are independent and can be shipped incrementally — each is a self-contained PR:

| Sprint | Items | Rationale |
|--------|-------|-----------|
| 1 | LOG-1, LOG-2, NOTIF-1, NOTIF-2 | P0 broken promises — fix before any UX work |
| 2 | NUX-1, NUX-2, NOTIF-3, LOG-3 | First-impression failures (new user in 10 minutes) |
| 3 | NUX-3, NUX-4, LOG-4, LOG-5 | Monitoring trust — the user who left something on |
| 4 | FLOW-1, FLOW-2, NAV-1, NOTIF-4 | Power-user friction |
| 5 | RECUR-1, FLOW-4 (Security Overview), FLOW-5 | Recurring user dashboard |
| 6 | LOG-6, LOG-7, RECUR-2, RECUR-3 | Power features |
| 7 | NAV-2, NAV-3, NUX-5, VC3 | Polish and discovery |
| 8 | NOTIF-5, NOTIF-6, RECUR-4, VC5, FLOW-3 | Finishing touches |
