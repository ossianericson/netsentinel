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

### NUX-5 · P2 · Feature Guide has no "start here" for new users

**What the user sees today:** Feature Guide lists every feature alphabetically by group. A new user has no idea which five features matter most for them.

**Acceptance criteria:**
- Add a "Start here" group at the top of Feature Guide (above Security) with 4–5 curated entries: Devices, Network Grade, What's Wrong?, ARP Spoof Watch, Notifications. Each entry has a "Why this matters" one-liner.
- Add a "New in this version" group that shows the 3 most recently added features (hardcoded list updated with each release).

---

## LOG — Logger / Log Hub

### LOG-8 · P3 · Source toggle bar label is unclear ("Modem" not "5G Modem")

**What happens today:** The source bar just says "Modem" — but the modem page is titled "5G Modem Signal". For users with non-5G modems or multiple hardware types, this is ambiguous.

**Acceptance criteria:** Source toggle labels match the full hardware page name: "5G Modem", "Mesh Router", "Syslog", "SNMP Traps". If a modem plugin is not connected, the "5G Modem" toggle is disabled with tooltip "Connect a modem plugin to enable modem logging."

---

## NOTIF — Notifications Setup Flow

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

### FLOW-3 · P1 · Diagnosis results have no "share" or "copy" action

**What happens today:** The "What's Wrong?" diagnosis page produces a detailed report. If a user wants to share it with ISP support or a sysadmin, they screenshot it or retype it.

**Acceptance criteria:**
- Diagnosis result has a "Copy report" button that puts a plain-text summary on the clipboard.
- Format: "NetSentinel Diagnosis Report — [date] / [verdict] / Findings: [list] / Recommended actions: [list]"
- Same clipboard output as the ISP Report export flow.

---

## RECUR — Recurring User Power Features

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

## Implementation order (remaining)

| Sprint | Items | Rationale |
|--------|-------|-----------|
| 7 | NAV-3, NUX-5, VC3 | Polish and discovery |
| 8 | NOTIF-5, NOTIF-6, RECUR-4, VC5, FLOW-3, LOG-8, NAV-4 | Finishing touches |

---

## Completed

All items below are shipped. Spec detail lives in git history.

| Item | Title | Sprint |
|------|-------|--------|
| LOG-1 | Modem/mesh logging: split DB toggle from visibility eye | 1 |
| LOG-2 | Remove Scan Config accordion; persistent inline source header | 1 |
| NOTIF-1 | Rules badge + "Enable recommended rules" CTA | 1 |
| NOTIF-2 | Test button inline failure feedback + success checkmark | 1 |
| NUX-1 | First-run hero mode — single centered scan CTA | 2 |
| NUX-2 | Post-scan "Your network at a glance" bottom sheet | 2 |
| NOTIF-3 | Keychain note + "Change ›" link on all credential fields | 2 |
| LOG-3 | Monitor rail button green dot badge when any source is logging | 2 |
| NUX-3 | Monitoring row on Home (ARP/DHCP/Storm/Logger pills) | 3 |
| NUX-4 | Setup checklist card (5-step, collapsible) on Home | 3 |
| LOG-4 | 2000-row cap banner + CSV export with date-range picker | 3 |
| LOG-5 | Inline amber banner on live_challenge_detected; 60s auto-dismiss | 3 |
| FLOW-1 | "Reset all dismissed notices" in Settings maintenance card | 4 |
| FLOW-2 | Alert rows clickable; routes to PORT_SCAN / THREAT_INTEL / Bandwidth / Notifications | 4 |
| NAV-1 | Flyout item dots for active monitors and unacknowledged alerts | 4 |
| NOTIF-4 | Status column (✓/✗/⟳) in delivery log; failed rows red; retry panel | 4 |
| RECUR-1 | Recurring-user Home layout after 5 scans + checklist complete | 5 |
| FLOW-4 | MonitorOverviewPage in Analysis section | 5 |
| FLOW-5 | `_CTA_MAP` in DiagnosisPage — 10 finding categories → nav targets | 5 |
| LOG-6 | Search/filter bar above log table; source chip bar | 6 |
| LOG-7 | Live / History toggle with date-range DB query | 6 |
| RECUR-2 | Weekly digest notification (opt-in) with time-of-day picker | 6 |
| RECUR-3 | Command palette "Recent actions" section (last 5, re-runnable) | 6 |
| NAV-2 | Command palette results include monitor running state | 4 |
