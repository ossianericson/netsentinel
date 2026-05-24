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

## Implementation order (remaining)

All items complete. Backlog shipped.

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
| NAV-3 | Pinned items label + "Quick Access" label + first-use toast | 7 |
| NUX-5 | Feature Guide "Start here" + "New in this version" groups | 7 |
| VC3 | Loading states for Port Scan, Network Grade, Diagnostics | 7 |
| NOTIF-5 | Escalation card collapsible "Advanced: Escalation" section | 8 |
| NOTIF-6 | Alert History tab in delivery log card | 8 |
| RECUR-4 | Trend Forecast this-week vs last-week RTT headline stat | 8 |
| VC5 | Flyout section headers 9px TEXT_MUTED; items 11px TEXT_PRIMARY | 8 |
| FLOW-3 | Diagnosis "Copy report" button with clipboard plain-text output | 8 |
| LOG-8 | Source toggle labels: "5G Modem", "Mesh Router", "Syslog", "SNMP Traps" | 8 |
| NAV-4 | Flyout item 120ms highlight before close (already done in prior sprint) | 4 |
