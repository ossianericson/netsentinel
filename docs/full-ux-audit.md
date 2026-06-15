NetSentinel — Full UX Audit
(Expanded edition. Items from the initial analysis are revised and deepened; many new areas are added.)

A. Navigation and Information Architecture
The 62-page problem

NetSentinel has 62 navigable pages across 9 rail sections. The Monitor section alone has 15 items in its flyout: Active Monitors, Network Logger, Network Timeline, Live Bandwidth, App Traffic, Active Connections, Availability History, Inventory Changes, Bandwidth Usage, Service Heartbeat, IPv6 Devices, Uptime & SLA, Syslog Viewer, SNMP Trap Receiver, plus the plugin-provided Modem and Mesh & Router. That is more items in a single flyout than most users can scan without scrolling. When a user opens the Monitor flyout looking for "what happened yesterday," they face a 15-item list with no visual hierarchy to help them.

The root cause: the nav sections were defined by the developer's functional taxonomy ("what kind of tool is this?") rather than by user intent ("what do I need to do right now?"). A user never thinks "I need to go to the Monitor section"; they think "I want to see if my router dropped out at 3 AM." The flyout categories don't map to user goals.

Suggested flyout grouping within sections (no new sections needed — just visual sub-groups within the existing flyouts):

Within Monitor, two natural clusters:

Live data (Live Bandwidth, App Traffic, Active Connections, Network Logger, Syslog Viewer, SNMP Trap Receiver, Modem, Mesh & Router)
History and trends (Availability History, Inventory Changes, Network Timeline, Uptime & SLA, IPv6 Devices, Service Heartbeat, Active Monitors)
The _nav_add_subgroup() method already exists in the nav builder — it's just not used in the Monitor section.

Page naming inconsistencies found in the code

The _RULE_PAGE routing map in alert_drawer.py uses "TLS & Cert Monitor" as the page label. The _PAGE_HELP dict in help.py registers the same page as "TLS & Exposure". The notif_alert_history.py _RULE_NAME_CTA dict routes "cert expir" to "TLS & Cert Monitor". These are all referring to the same page, but with different names in different routing dictionaries. When a user clicks an alert about a certificate and is routed to "TLS & Cert Monitor," but the nav label reads "TLS & Exposure," they won't know they arrived at the right page.

Other naming issues:

"Inventory Changes" (the page) vs "Devices" (also shows device data, but different view)
"Network Timeline" vs "Activity Log" tab inside Network Logger (both are chronological event feeds from the same data, but described as separate things in help.py)
"Active Monitors" (the Monitor Overview page) vs "Monitor Overview" (the monitor_overview_page.py file and class name) — different names in code and UI
"DNS & Stability" combines two concepts — DNS benchmarking and packet-loss/latency monitoring — that are distinct enough to confuse new users about what they'll find
"Home Automation" (the MQTT bridge page) vs "MQTT / Home Assistant" (help.py calls it "MQTT / Home Assistant") — inconsistent labelling of the same feature
Three pages named "Overview" or "Monitor"

"Overview" (configurable tile dashboard, Getting Started), "Active Monitors" (monitor status grid, Monitor section), "Security Overview" (threat intel, Security Audit) — these three names carry the word "overview" or "monitor" and represent different things. From a cold start, a new user cannot infer what any of them show from the name alone.

B. Home Page — Expanded Analysis
The widget order problem in depth

Reading _setup_ui() top to bottom, the vertical order of widgets added to the scroll area (post-freshness strip) is:

Browser dashboard strip (conditional)
Getting Started checklist card (conditional — shown until setup_done)
Setup complete celebration card (conditional)
"Since you were last here" banner (conditional)
First scan guidance banner (conditional)
"Action needed" card with per-alert rows (conditional — shown when alerts exist)
Post-scan delta banner (conditional)
Milestone banner (conditional)
Recurring section (monitoring pills + grade + scan time + rescan + diagnosis + ticker)
"THIS WEEK" chips (alerts / new devices / grade change / CVEs)
Recurring intro card (one-time)
Live challenge banner (conditional)
Hero card (grade ring + "Scan Network" + "What's Wrong?" buttons)
Feature search bar
Post-scan summary sheet (conditional)
"THE THREE THINGS THAT MATTER" section label
Mini-cards row (Speed / Stability / Devices)
Monitoring pills row ← duplicate of items in #9
Monitoring pills hint text
"Did you know?" tip card
Monitoring nudge + "Start Network Logger" button
"STABILITY MONITORING" section label
Stability monitoring card (start/stop button)
Post-scan results strip (conditional)
"WHAT TO DO NEXT" section label + suggestions card
"RECENT ALERTS" header + "View all →" link
Alert card
A returning user with data lands on items 9–10 first (Recurring section + THIS WEEK). A brand-new user sees the checklist first. The hero card — the main explainer and primary CTA — is item 13.

More critically, items 9 and 18 contain nearly identical monitoring pill content. The recurring section (_rec_pill_arp, _rec_pill_dhcp, etc.) and the standalone monitoring pills row (_pill_arp, _pill_dhcp, etc.) are both constructed with the same four monitor labels and both connect to the same pages. They exist as two independent QWidget trees. There is no code path that shows one and hides the other — _recurring_section.setVisible() only hides the outer card, not the separate pills row below.

ALL CAPS section headers throughout the home page

The home page has eight ALL CAPS section headers: "THE THREE THINGS THAT MATTER", "MONITORING", "MONITORING STATUS", "THIS WEEK", "STABILITY MONITORING", "EXPLORE YOUR RESULTS", "WHAT TO DO NEXT", "RECENT ALERTS". ALL CAPS headers are a standard technique for secondary labels but eight on one scrollable page creates a visual rhythm that de-emphasises everything equally. Users lose the ability to skim for the most important thing because everything shouts equally. Three of these ("THE THREE THINGS THAT MATTER", "STABILITY MONITORING", "MONITORING STATUS") are nearly identical in meaning. The naming should distinguish between them and the caps case should be reduced.

"THE THREE THINGS THAT MATTER" is not scannable for new users

The three mini-cards (Speed / Stability / Devices) show "–" in both their value and secondary slots before a scan runs. A new user who navigates to Home before scanning sees three grey placeholder cards with no value. The section label "THE THREE THINGS THAT MATTER" promises importance but the cards deliver nothing. The cards should show their empty-state more helpfully: "Tap Scan to see your speed" rather than "–".

The live events ticker

_EventsTicker in the recurring section shows recent events (device joined, alert fired, etc.) as a scrolling row. This is valuable for a returning user. But it sits inside _recurring_section which is only shown after the user has done several scans (_recurring_mode = True). A first-time user never sees this. When it first becomes visible, it has no explanation — a user doesn't know what the small scrolling lines of text represent.

C. Overview (Tile Dashboard) — Expanded Analysis
CTA bar always visible, even when stale

The "Quick Network Assessment" CTA bar (_cta frame with border:1px solid {ACCENT}) is always present in the layout. After the first scan, it updates to "▶ Rescan" and the sub-text changes to "Discover devices · check stability · detect threats." But the frame never disappears. This means a full-width, accent-bordered box occupies permanent space at the top of the page — even for a power user who runs scans daily. A returning user who just ran a scan 10 minutes ago does not need to see a large "Scan Network" banner. The CTA bar should move to a more compact form after the first successful scan (or be placed in the header row of buttons, not as a separate full-width card).

Grade explanation panel as a collapsible toggle

The "▶ How is this grade calculated?" toggle panel is correct in concept — the explanation should be accessible but not default-visible. However, clicking it inserts 8 rows of dimension explanations inline between the hero pills and the tile grid. On a short window, this pushes the tile grid off-screen. A popover or side drawer would be less disruptive. The existing AlertDrawer pattern (slide-in from the right) could be reused here.

Hero pills use raw counts without baselines

The four hero pills (⬡ Devices: 12, ◈ Grade: B, ◬ Alerts: 3, ◆ Services: 8 up) use colour-coded borders (green/amber/red) but provide no baseline context. "Alerts: 3" — is that more or less than last week? "Devices: 12" — is one missing? A micro delta chip under each pill ("+1 since yesterday" or "−1 from last scan") would turn these from static snapshots into actionable indicators.

The Security Scan Panel

At the bottom of Overview is a _SecurityScanPanel — a collapsed widget for running Security Audit tools. This is an unusual placement: security audit actions living at the bottom of the general dashboard. A user who wants to run a port scan won't think to look at the bottom of Overview; they'll navigate to Security Audit. Conversely, a user scrolling Overview may stumble on this panel without knowing what it is. It creates confusion about whether Security Audit things belong in Overview or in their own section.

D. Active Monitors — Expanded Analysis
No unified monitor management surface

Monitors can be started or stopped from:

Home page "Start Monitoring" button (starts Network Logger)
Home page monitoring pills (navigate to individual monitor pages)
Individual pages (each has its own start/stop)
Getting Started checklist (steps 4 and 5 start ARP Watch and Network Logger)
There is no single screen where a user can see all monitors and their current run states simultaneously, start/stop any of them, and confirm which are logging. The Monitor Overview page is the closest thing but it shows data states (tile content) rather than monitor run states (running vs stopped vs error vs not-configured).

Run state vs data state confusion

The Monitor Overview tiles show things like "ARP Spoof Watch: No threats detected" in green. But "no threats detected" could mean (a) the monitor is running and found nothing, or (b) the monitor is not running and has never reported anything. These look identical in the tile. A user cannot tell whether ARP Watch is active protection or an unstarted feature showing an empty default state.

Per-monitor timestamps missing from home page pills

The monitoring pills on the home page show "○ ARP Watch" but no timestamp of when it last checked. Compare to a real security monitoring tool where every sensor shows its last poll time. "ARP Watch — last event: 3 min ago" vs "ARP Watch — not started" would be immediately meaningful. Currently the only place to see this is the individual page.

Start/stop state not persisted across restarts

From reading home_data_mixin.py and the app structure, no monitor auto-restarts on launch. The help text for Network Logger says "Enable 'Auto-start on launch' so logging begins the moment the app opens without any manual step" — this is described as a feature but based on the code it doesn't appear to be a QSettings-backed preference that's checked at startup. If it is implemented, it's not surfaced clearly to the user.

E. Security Overview — Expanded Analysis
Scope mismatch between the name and the content

The page pulls from load_from_cache() in modules/threat_intel.py only. It shows Threat Indicators, Malicious IPs, Blocked Domains, and a top-15 by-confidence findings table from ThreatIntelDB. A user who ran Port Scan, CVE Tracker, Login Test, and TLS check would expect to see all of these results summarised here. They won't.

The page is well-named from a threat intelligence perspective ("what does ThreatIntelDB know about IPs on my network?") but poorly named as the entry point to the Security Audit section. Any user who navigates to Security Audit and clicks the first item ("Security Overview") believes they're getting a total security picture.

KPI tiles lack trends and thresholds

The KPI tiles (Threat Indicators / Malicious IPs / Blocked Domains / Last Updated) show a large number and a label. "43 Threat Indicators" provides no reference point. A new user with 43 indicators doesn't know if that's catastrophic or normal background noise from internet scanners hitting their public IP. Without context — "was 45 last week, is trending down" or "this is typical for a home network" — the number is anxiety-inducing noise rather than actionable signal.

"Last Updated" KPI is the only freshness indicator

The ThreatIntelDB has a "Last Updated" timestamp tile. This is correct — the user needs to know if the data is stale. But if the last update was three days ago (because the update worker hasn't run), the user sees "3 days ago" with no indication of whether this is normal or a problem. The freshness tile should distinguish between "updated automatically as scheduled" and "update failed — manual action needed."

Quick nav pills at the top

Four quick nav pills (Threat Intel / Geolocation Map / Port Scan / CVEs) allow jumping to detailed pages. This is good cross-page linking. But these four pages are in different sections (Analysis, Security Audit) and the pills give no indication of where they navigate to. A user who clicks "Port Scan →" gets taken to a different section without warning.

F. Notifications Page — New Area
Three separate concerns on one page

The NotificationsPage header says "Route alerts to desktop notifications, webhooks, or email by severity." But the page contains:

Alert rule management (when does something fire — RTT thresholds, severity filters)
Channel configuration (where it fires — email, webhook, toast, Pushover, Ntfy, Telegram)
Alert history table (what already fired — past alert log)
Delivery log (was it successfully delivered?)
Alert dependency tree (suppress child alerts when parent is down)
Weekly digest toggle and escalation policy
A user who comes to Notifications because "I got too many alerts last night" has to scroll through channel configuration cards to find the history tab. A user who wants to add an email address for alerts has to navigate past the history and dependency tree. The page needs tabs that clearly separate configure (rules + channels) from review (history + delivery log).

The alert dependency tree is buried and critical

The _NotifDepMixin card (alert dependency tree: "when this parent device goes down, suppress alerts for these children") is one of the most operationally important features in the notification system. An alert storm from a single upstream outage can send dozens of duplicate alerts within seconds. The dependency tree prevents this entirely. But it lives as one card among many on a long-scrolling page, with no visual treatment that distinguishes it from a simple channel-configuration card.

A user experiencing an alert storm would not naturally think "I need to configure a dependency tree." They'd try to dismiss all the alerts or turn off notifications. The dependency tree needs to surface proactively — after a burst of alerts for the same time window, the app could suggest "6 alerts fired within 30 seconds — this looks like a parent-device outage. Set up alert dependencies to prevent storms like this."

Alert acknowledgment in three different places

Alert acknowledgment can happen:

In the Home page Action card (inline ack button per alert row)
In the Notifications page alert history table (right-click or button)
In the AlertDrawer (slide-in panel, only accessible from the Notifications page table)
The AlertDrawer is the most feature-rich view: it shows device context, fix text, "view in [page]" navigation, and an ack-with-comment field. But it's only accessible from the Notifications page. A user who acks an alert from the Home page action card never sees the remediation text or device context. These three acknowledgment paths should lead to the same rich detail view.

"Notifications" is the wrong home for alert history

Alert history lives under Reports > Notifications. A user who wants to know "what alerts fired yesterday?" thinks "alerts", not "notifications" and not "reports." Alert history should be accessible from the main Monitor section or from a dedicated Alerts page. The current placement means the most time-sensitive post-incident review information (what fired, when, was it delivered?) is in the Reports section alongside scheduled report configuration.

G. Finding Information — Expanded Analysis
Five different history views, no clear starting point

A user asking "what happened on my network last night?" has to choose from:

Network Timeline (Monitor section) — device joins/leaves, fired alerts, CVE discoveries, speed tests — reverse-chronological event feed
Network Logger → Activity Log (Monitor section) — RTT, DNS, modem signal, syslog — a different chronological feed for a different data domain
Availability History (Monitor section) — per-device RTT and UP/DOWN/DEGRADED charts over time
Inventory Changes (Monitor section) — device diff: which MACs joined or left
Notifications → Alert History (Reports section) — past fired alert rules with delivery log
These five are not redundant — they cover different data domains. But from a user's perspective, they all answer the same question: "what happened?" The user must already know which domain they're asking about to choose correctly. "Did my network drop last night?" might live in #2 (if the logger was running and captured a packet loss spike) or #3 (if the availability worker tracked a DOWN state) or #1 (if an alert fired), or #5 (if the alert email was sent).

The Timeline page is the right answer — but it's incomplete

The TimelinePage pulls from device_event, alert_log, cve_lifecycle, and speed_test tables. The NetworkLogger Activity Log pulls from RTT/DNS/modem/syslog data. These are genuinely separate stores. But from a user's perspective, a unified timeline that includes everything would be more useful than two separate chronological views. The Timeline page is architecturally the right concept; it just needs the Network Logger data incorporated as additional source chips alongside Devices / Alerts / CVEs / Speed Tests.

Alert → detail path is non-obvious

When a user sees an alert pill on the Overview page (AlertFeedTile), clicking it calls _on_alert_navigate() which maps the alert type to a destination page (e.g. SERVICE_DOWN → "Service Heartbeat"). The user is teleported to Service Heartbeat with no context about why they landed there or which alert triggered the navigation. The destination page has no "you arrived here from an alert for host X" context strip. The rich alert detail (fix text, device context, ack button) from AlertDrawer is not shown.

Ctrl+K searches pages, not data

The command palette matches against page names, feature names, and page labels. A user typing "192.168.1.5" gets no results. Typing "NETGEAR" gets no results. The palette operates on the app's structure, not on the app's data. For a tool that's fundamentally about data — devices, their IPs, MACs, hostnames, alerts, CVEs — this is a significant discoverability gap. The existing nl_query.py module can parse natural language device queries but it's wired only to a specific page.

H. Data Persistence and Saving — Expanded Analysis
No single source of truth for "what's configured"

Configuration is scattered across:

QSettings: tile order, monitor targets, dismissed banners, window geometry, nav state, notification channel URLs/thresholds
OS keychain (keyring): SMTP passwords, API keys, webhook secrets, SNMP community strings, MQTT credentials
MetricStore (SQLite): all time-series data, known devices, alert log, CVE records, device labels/notes
SettingsPage itself: theme picker, some display prefs
A user who wants to back up their configuration or move to a new machine has no clear path. The Settings page mentions "Export All Data" (emits export_all_requested) but this exports data, not configuration. The settings_io.py module provides QSettings export/import, but where is the UI for it exposed? If it's in the Settings page, it's not obvious to a user that there are two separate things to back up (QSettings and MetricStore).

Acknowledged alerts have no persistent visual state

When a user acknowledges an alert from the Home page action card, the row disappears from the action card. But on the Notifications page alert history table, acknowledged alerts are shown with a different background/style (from notif_alert_history.py's rendering logic). A user who acks from Home and later opens Notifications might not immediately see which alerts they already reviewed. The ack state is persisted in MetricStore, but the visual representation varies by page.

Settings page _dirty flag but no save/cancel pattern

The SettingsPage has self._dirty = False in __init__, implying change-tracking. But the pattern is auto-save — the _dirty flag exists but there's no visible "you have unsaved changes" indicator and no explicit Save button. If the dirty flag is used only internally (e.g. to offer "are you sure?" on navigation away), a user never sees it. This inconsistency in whether changes feel permanent or provisional creates uncertainty.

I. Behaviour Between App Starts — Expanded Analysis
What should auto-restart and what shouldn't

Based on reading the code and architecture:

Network Logger: manual start required every launch (no auto-start appears to be wired)
ARP Watch: manual start required
DHCP Rogue Monitor: manual start required
Broadcast Storm: manual start required
Availability worker: appears to auto-start in app.py (always-on worker)
Service Heartbeat worker: appears to auto-start (30-day QSettings persisted targets)
Trend worker: auto-runs on a schedule
The inconsistency is the problem. Some workers are always-on (availability, service heartbeat), others require a manual start per session (loggers, security monitors). From a user's perspective this is unpredictable. The getting-started checklist says "step 4: start ARP Watch" — but if the user has to repeat this every time they open the app, the checklist instruction becomes misleading.

Last-open page is not restored on relaunch

From the nav builder code, QSettings("nav/last_section") persists the last-open section. But it's not clear that the last-viewed page within that section is also restored. A user who was on "Availability History" when they closed the app may reopen to the Overview or Home page. The last-visited page label should be saved and restored on startup.

The splash screen gap

The app shows a splash screen during startup. During this time, workers are presumably initialising. There's no indication on the splash of what's loading or why it's slow. A user on a machine with many saved devices or a large MetricStore might wait several seconds with no feedback. A simple "Loading 3 weeks of history…" or progress indicator during the splash would set expectations.

"Closed for N days" states are common but unhandled

A typical home user opens NetSentinel twice a week. Over a week, the Network Logger was off, no scan ran, and the MetricStore has no new data. When the user opens the app, the Overview tiles show data from five days ago (with a timestamp like "5 days ago" in the tile age label). The Availability History charts show a gap. The Timeline shows no events for five days. None of these states have explicit "no data in this period" explanations — they just show the last known data, which looks like current data unless the user notices the timestamp.

J. Feature Discoverability — New Area
Feature Guide is in the Education section

The Feature Guide (83 features, 9 groups) is under Education > Feature Guide. A user who doesn't know to look in Education will never find it. The home page has an inline feature search bar that queries the same data, which helps — but the search bar requires the user to already have a search term in mind. Browsing 83 features without a search term requires navigating to the Feature Guide page.

"Did you know?" tip cards advance session-by-session but forget per-tip context

The home page shows one rotating "Did you know?" tip card from the "Hidden features" group. The tip is selected by index modulo the list length, advancing on each launch. But the dismissed keys are per-index, so tip #3 dismissed today is permanently hidden — the user never sees it again even after the tip cycle resets. A user who dismisses three tips on first day and then returns a month later might never see those tips again. The snooze period (7 days in _HomeSuggestionsMixin) is a better model — a dismissed tip should come back after N days rather than being permanently hidden.

Auto-help pages expand the tip bar on first visit

_AUTO_HELP_PAGES in nav/builder.py includes "Network Logger", "Lab Mode", "Protocol Visualizer", "Automation Hooks", "MQTT / Home Assistant", "TLS & Exposure", "Service Heartbeat", "IoT Behaviour", "Scheduled Scans." These pages auto-expand the tip bar on first visit. This is excellent for discoverability. But several equally-non-obvious pages are not in the list: "Bandwidth Usage", "Trend Forecasts", "App Traffic", "ARP Spoof Watch", "Active Monitors". The list appears to be manually curated and incomplete.

The "hidden features" tip category reveals a real discoverability problem

The Feature Guide has a "Hidden features" group. The name itself is an admission that these features are not surfaced through normal exploration. Features that are genuinely useful but require a non-obvious interaction (right-clicking a map node to jump to Devices, clicking a speed test history row to restore the modem signal panel, the bandwidth overlay on the Network Map, the Protocol Visualizer auto-load from Network Logger events) should not be permanently "hidden" — they should have discovery paths baked into the primary UI at the right moment.

K. Permissions and Requirements Gating — New Area
No upfront overview of what requires admin or Npcap

Eleven features require admin rights, Npcap, or both:

ARP Spoof Watch (Npcap)
DHCP Rogue Monitor (Npcap)
Broadcast Storm (Npcap + admin)
802.11 Monitor Mode (Npcap + admin)
App Traffic (Npcap + admin)
Bandwidth Usage (Npcap)
Port Scan / SYN scan (admin)
Login Test (admin required for SMB/SSH)
OS Detection (admin)
WiFi Monitor (admin)
Some ARP operations (admin)
A standard-user who installs the app and explores will discover these requirements one by one as they hit the error states or NpcapBanner on each page. There's no central "to unlock X features, you need Y" summary. The onboarding checklist doesn't mention Npcap at all. The Feature Guide entries for Npcap-required features have "requires": "Npcap" but this shows as grey sub-text, not as a clear setup step.

Npcap banner is per-page, not proactive

The NpcapBanner widget appears on pages that need it. But it only appears when the user has already navigated to that page. A user who installs NetSentinel and then wonders "why can't I see ARP Watch results?" will navigate there, see the Npcap banner, and may not know that several other pages are also affected. A one-time setup prompt during onboarding ("NetSentinel can protect you from ARP spoofing attacks, but it needs Npcap — install now?") would convert more users.

L. Data Export Consistency — New Area
No consistent export pattern across pages

Export behaviours vary significantly by page:

Overview: "Share Card" (PNG/HTML card) + "Export…" (HTML/JSON/CSV scan results) as separate buttons
Network Doc: "Export HTML" / "Export Markdown" buttons
Speed Test: implicit — results are stored in DB but no export button visible
Network Logger: CSV files written automatically to disk
Uptime/SLA: "export the table as CSV" mentioned in help but unclear where the button is
Reports page: PDF export
A user who wants to share their network health data with an IT consultant has to know which page exports which format. There's no "export everything in one place" option.

Speed test history is not exportable from the page

The Speed Test page stores test history in MetricStore but doesn't appear to have an explicit export button. The history table can be viewed in-app but cannot be easily shared. An IT admin presenting evidence to their ISP for a service level dispute needs export.

M. Page-Level UX Issues (Selected)
Speed Test: gauge shows nothing useful until first test runs

The matplotlib arc gauge (_GAUGE_START_DEG = 210, _GAUGE_END_DEG = -30, _GAUGE_SPAN = 240) shows a static empty dial on first load. A user who has never run a test sees a circle with no numbers, no context, and no placeholder. The empty state should say "Run a speed test to measure your connection" in the gauge area, not just show an empty arc.

Service Heartbeat: "Diagnose →" is right-click only

The diagnose_service signal in ServicePage is emitted when the user right-clicks a service row and selects "Diagnose →." This is a genuinely powerful integration (the most useful thing you can do when a service shows DOWN is immediately diagnose it). But right-click-only discoverability is the weakest possible affordance — most users only right-click when they already know right-click will do something. The "Diagnose" action should be available as an inline button in the DOWN state of a service row, not only in the context menu.

What's Wrong? symptom tiles are fixed to four scenarios

The DiagnosisPage has four symptom tiles: Slow Internet, Dropping Connection, Can't Connect, Service Unreachable. A user whose problem is "my printer keeps going offline" or "my smart TV buffers at 8 PM but not 10 PM" or "my Wi-Fi password was changed" doesn't have a tile for their symptom. The "Service Unreachable" tile is the right extension pattern — future tiles for "device disappeared from network" or "slow Wi-Fi but fast ethernet" would cover more real-world scenarios. As-is, a user whose symptom doesn't fit the four tiles might conclude "this tool can't help me" and leave.

Network Map: bandwidth overlay is completely non-discoverable

The Network Map page loads a BandwidthOverlayWorker to show per-device traffic bandwidth on the topology nodes. This feature — traffic volume visualised on the network map — is one of the most compelling in the product. But there is no visible control, legend, or toggle that tells the user it's active. A user looking at the Network Map has no idea the colours or thicknesses might encode bandwidth data. The overlay needs a prominent toggle and a legend.

Network Map: two views with no "which to use" guidance

The Network Map has an "Interactive" (Cytoscape.js) and "Classic" (matplotlib) view. The interactive view supports drag-to-arrange, physics layouts, and per-node HTML tooltips. The classic view is static. The UI to switch between them is a tab or button with no explanation. A user who encounters the classic view because WebEngine isn't installed might think the interactive view is just a broken feature, not a different component.

Trend Forecasts: OLS regression is not explained

The TrendPage shows linear-regression forecasts for RTT, packet loss, and jitter with an "ETA to threshold" column. This is a sophisticated feature. But a user who sees "ETA: 4.2 days" doesn't know what threshold is being predicted, what "OLS regression" means, or what to do with this information. The page needs a one-paragraph plain-English explainer (consistent with RULE-A1) that says: "NetSentinel looks at how your network metrics are trending and predicts when they'll reach a problem level — so you can fix things before they fail."

N. Full Ranked Improvement List — Top 25
Below is the full ranked list. Items 1–10 are revised and in some cases re-ranked from the initial analysis. Items 11–25 are new.

#1 — Fix the home page widget order and remove the duplicate pill row
Why: The primary CTA (grade ring + Scan button) is item 13 in a 27-item vertical scroll. New users give up or get lost before they reach it. The duplicate monitoring pill rows (one inside _recurring_section, one as a standalone widget below) show four identical controls twice on the same page.
Dev effort: Small (1–2 days) — reorder widget insertion in _setup_ui(), remove the standalone _monitoring_pills_row, verify nothing else references it.
Sprint: A

#2 — Monitoring pills: show live run state with a coloured indicator
Why: Security monitors that show "○ ARP Watch" regardless of running or stopped state give the user no security confidence. This is the highest-urgency clarity gap in the product — a tool for detecting network attacks should make it obvious whether the detection is active.
Dev effort: XS (hours) — update set_monitor_pills() to replace ○ with ● in green (running), grey (stopped), red (error), and update pill border colour to match.
Sprint: A

#3 — Persistent one-line status strip visible at all times on the Home page
Why: "Grade B · 12 devices · 0 alerts · last scan 47 min ago · Logger: on" is the single most informative sentence the app can show. Currently this data is fragmented across a grade ring, three mini-cards, a recent-alerts section, and a freshness strip.
Dev effort: Small (1 day) — the four Overview hero pills already assemble this data; wire the same values to a permanent strip in the Home page header (above the scroll area, below the freshness strip).
Sprint: A

#4 — Unify the three "Overview" concepts under distinct names
Why: "Overview," "Active Monitors," and "Security Overview" are three pages users conflate. No user can reliably choose the correct one from the nav without trial and error.
Dev effort: Medium (3–4 days) — rename pages, update all routing strings, breadcrumbs, help entries, _PAGE_HELP keys, _RULE_NAME_CTA maps, and Feature Guide entries. Nav label changes must cascade through every dict that maps labels to pages (at least: _RULE_PAGE, _RULE_NAME_CTA, _CTA_MAP, _SOURCE_PAGE_MAP, all navigate_to.emit() calls).
Sprint: B

#5 — Notifications page: separate configure vs review into clear tabs
Why: A user who arrives because "I got too many alerts" and a user who arrives to "add an email address" need fundamentally different starting points. The current single-scrolling-page model puts channel configuration, rule management, history table, dependency tree, and delivery log on one long page.
Dev effort: Medium (3 days) — split into two or three primary tabs: "Configure" (channels + rules + escalation + dependency), "Alert History" (history table + delivery log), and possibly "Weekly Digest." The tab widget already exists in notif_alert_history.py within the page — this is an expansion of existing structure, not a new pattern.
Sprint: B

#6 — Alert dependency tree: proactive storm detection and suggestion
Why: The most critical alerting feature (parent-child suppression to prevent alert storms) is invisible until a user already knows it exists. After a burst of alerts in the same 60-second window, the app should offer: "Multiple alerts for devices on the same subnet — set up alert dependencies to prevent storms."
Dev effort: Small (1–2 days) — in the alert engine, after writing N alerts within T seconds for the same subnet, emit a signal that the Home page or Notifications page surfaces as a contextual suggestion card with a "Set up →" button linking to the dependency tree card.
Sprint: B

#7 — Auto-restore monitors on app restart (with opt-out)
Why: If the user explicitly started ARP Watch on Monday, they intend to keep it running. Having to restart it every session creates gaps in protection and data. The getting-started checklist already asks the user to start specific monitors — that expressed intent should persist.
Dev effort: Medium (3 days) — save a QSettings flag for each monitor when started/stopped; read these on startup in app.py; restart the relevant workers; show a one-line banner "3 monitors resumed — [stop all]."
Sprint: B

#8 — Fix routing string inconsistencies ("TLS & Cert Monitor" vs "TLS & Exposure")
Why: Alert routing code in alert_drawer.py, notif_alert_history.py, and overview_page.py uses old or inconsistent page labels. When a user clicks an alert for a certificate and is routed to a page that doesn't match the name in the breadcrumb, they'll distrust the navigation.
Dev effort: XS-Small (a few hours to a day) — audit all routing dicts (_RULE_PAGE, _RULE_NAME_CTA, _CTA_MAP, _MAP in overview_page.py, _SOURCE_PAGE_MAP in timeline_page.py) against the canonical nav labels and align them.
Sprint: A

#9 — Security Overview: aggregate all security scan results, not just threat intel
Why: A user who ran port scan, CVE check, and login test navigates to Security Overview expecting a consolidated picture and finds only threat intelligence. The page name creates a promise the content doesn't keep.
Dev effort: Medium–Large (5–7 days) — add KPI tiles for: open high-risk ports (from MetricStore port scan data), devices with active CVEs by severity, login test failures, TLS issues. These data sources already exist in MetricStore; the work is aggregation queries and tile layout.
Sprint: D

#10 — Service Heartbeat "Diagnose →" should be an inline button for DOWN services
Why: The most useful action when a service shows DOWN is to immediately run Service Diagnostics for it. Right-click-only means most users never discover this integration.
Dev effort: XS (hours) — when a service row's status is DOWN, render an inline "Diagnose" button in the row (similar to how the "Block" button works in Active Connections). The signal wiring already exists.
Sprint: A

#11 — Monitor section: add visual sub-groups within the flyout
Why: 15 items in one flyout with no grouping is unnavigable. Users can't distinguish "live capture" monitors from "historical data" pages at a glance.
Dev effort: Small (1 day) — use _nav_add_subgroup() to split Monitor flyout into "Live" and "History & Reports" sub-groups. The method exists in the nav builder; it just needs to be called in _build_pro_nav().
Sprint: B

#12 — Unified timeline: merge Network Timeline with Network Logger Activity Log sources
Why: Users have two chronological "what happened" views in the same section (Network Logger Activity Log and Network Timeline). They cover different data domains but the user's question is the same. Adding RTT/DNS/modem events as additional chip filters on the Timeline page would create a single answer to "what happened on my network."
Dev effort: Medium (3–4 days) — TimelinePage loads from four MetricStore tables via a refresh worker. Adding a fifth data source (RTT/DNS from the logger's SQLite log) requires a new query in the refresh worker and a new filter chip in the UI.
Sprint: C

#13 — Standardise severity vocabulary everywhere
Why: Internal scan risk strings (HIGH, STORM, MEDIUM, CLEAN) and user-facing severity labels (Critical, High, Warning, Info) coexist on the same pages without translation. The Security Overview page, alert history, and scan result tables all show different vocabulary for the same concepts.
Dev effort: Small–Medium (2–3 days) — create a display-layer mapping function (_risk_to_label()) called at every point that renders scan risk to the user. No change to scoring logic.
Sprint: B

#14 — Ctrl+K: add data-layer search (IPs, MACs, hostnames, CVE IDs)
Why: The command palette searches page names. A tool that accumulates data about 20 devices, 100 alerts, and 50 CVEs should let users search that data from anywhere.
Dev effort: Medium (4–5 days) — extend the palette's result-building logic to query MetricStore for device matches (by IP, MAC, hostname, vendor) and alert matches (by rule name, host) when the query doesn't match a page label. Show results as "Device: 192.168.1.5 (NETGEAR) → Devices page" entries.
Sprint: C

#15 — Npcap: one-time proactive install prompt in the getting-started flow
Why: 11 features require Npcap. Discovering this per-page as a banner means the user repeatedly hits walls. A single "install Npcap to unlock real-time monitoring features" step in the getting-started checklist converts all 11 barriers at once.
Dev effort: Small (1 day) — add a step to GettingStartedCard (or the first-run dialog) that detects Npcap absence and offers a one-click install, similar to the existing OoklaCliBanner pattern.
Sprint: B

#16 — "Saved automatically" micro-feedback on significant user actions
Why: Auto-save is correct. But invisibility creates uncertainty — users re-configure on each session or distrust changes they made. One-second feedback like a brief bottom-of-page toast removes that anxiety.
Dev effort: XS (hours) — emit a toast.py notification on: alert acknowledged, monitor started/stopped, notification channel configured, settings changed, device label saved. The toast.py widget exists and is already used.
Sprint: A

#17 — Speed Test: meaningful empty state on the gauge before first test
Why: The matplotlib arc gauge shows a blank circle on first load. A new user who opens Speed Test sees an empty dial with no explanation of what to do.
Dev effort: XS (hours) — render a centred "Run a test to measure your speed" label in the gauge area before results exist.
Sprint: A

#18 — Network Map: visible toggle and legend for bandwidth overlay
Why: The bandwidth overlay (per-device traffic shown on topology nodes) is one of the most powerful visualisations in the product but has no visible toggle or legend. Users can't see it or understand it.
Dev effort: Small (1 day) — add a "Bandwidth Overlay: On/Off" toggle in the map toolbar (consistent with existing toolbar buttons) and a simple legend (coloured dots = traffic level) as a small inset when the overlay is active.
Sprint: C

#19 — Alert drawer accessible from Home page and Overview, not only Notifications
Why: The full alert detail (device context, fix text, "view in..." navigation, ack-with-comment) is only accessible by navigating to Notifications and clicking a table row. Users who ack alerts from the Home page or Overview never see the remediation guidance.
Dev effort: Medium (2–3 days) — make AlertDrawer a shared component that can be instantiated as an overlay on any page that shows alerts. Wire the Home page action card alert rows to open the drawer instead of navigating away.
Sprint: C

#20 — Tip card persistence: use snooze-and-return rather than permanent dismissal
Why: A user who dismisses 3 "Did you know?" tips on day one never sees those tips again even after weeks. Snoozed suggestions already use a 7-day revival pattern in _HomeSuggestionsMixin — apply the same logic to tip cards.
Dev effort: XS (hours) — change the tip card's dismiss handler to write a home/tip_{n}_snoozed timestamp rather than a permanent boolean, using the same 7-day window as suggestion snooze.
Sprint: A

#21 — What's Wrong?: expandable custom symptom field
Why: Four fixed symptom tiles cover common cases but exclude many real-world scenarios. Adding a fifth tile "Something else…" that lets the user describe the problem in free text, then routes to the most relevant diagnostic page based on keyword matching (using existing nl_query.py), would cover a much wider population of user problems.
Dev effort: Medium (2–3 days) — add a fifth symptom tile with a QLineEdit input, wire it to a keyword-based routing function that maps terms like "printer", "smart TV", "WiFi" to relevant diagnostic pages.
Sprint: C

#22 — Trend Forecasts: plain-English explainer on first visit
Why: "OLS regression", "ETA to threshold", and "threshold breach" are opaque terms. The page should auto-expand an explainer panel (using ExplainerPanel) on first visit, consistent with Network Logger, Lab Mode, and Protocol Visualizer.
Dev effort: XS (hours) — add "Trend Forecasts" to _AUTO_HELP_PAGES in nav/builder.py and write a short help entry in _PAGE_HELP.
Sprint: A

#23 — Last-viewed page persisted and restored on relaunch
Why: A user who was working on "Availability History" when they closed the app expects to return to the same page. Currently the app restores the last-open section (rail button) but not the specific page.
Dev effort: Small (1 day) — save _nav_current_page_label to QSettings on every _nav_rail_go_to() call; restore it on startup after _build_pro_nav() completes.
Sprint: B

#24 — "Closed for N days" state: explicit staleness callout on data pages
Why: When data is five days old, Overview tiles show their last-known values. A user returning after five days sees numbers that look current but aren't. Every tile already has an age label (_update_ts_display()); the issue is visibility — the age label is small and secondary.
Dev effort: Small (1–2 days) — when a tile's data age exceeds a threshold (e.g. 24 hours), replace the age label with a prominent amber "Data from 5 days ago — rescan?" and surface the Rescan button.
Sprint: B

#25 — Settings: clear link to "what needs to be backed up"
Why: Configuration is split across QSettings (settings_io.py export), MetricStore (database file), and OS keychain (no backup path). A user preparing to reinstall Windows or move to a new machine has no guide to backing up NetSentinel. The Settings page "Export All Data" button should be accompanied by a "Backup guide: 3 things to copy" inline explanation.
Dev effort: XS (documentation + 1 UI label) — add a short inline explanation next to the Export and Import buttons explaining what each covers and what it doesn't (keyring credentials cannot be exported; they must be re-entered on the new machine).
Sprint: C

Sprint allocation summary
Sprint	Items	Theme
A	1, 2, 3, 8, 10, 16, 17, 20, 22	Zero-code-risk polish: order, colours, labels, visibility
B	4, 5, 6, 7, 11, 13, 15, 23, 24	Navigation coherence and restart behaviour
C	12, 14, 18, 19, 21, 25	Cross-page integration and data search
D	9	Security Overview full aggregation (largest single item)
Sprint A items have no new pages, no new data pipelines, and no architectural changes. They are pure UX repair on existing code — the highest impact-per-hour work in the backlog.