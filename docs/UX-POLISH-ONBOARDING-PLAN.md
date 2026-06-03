# NetSentinel — UX Polish & Onboarding Master Plan
# Sprints H1–H10

**Created:** 2026-06-03  
**Status:** Active  
**Scope:** Polish only — zero new features. Every sprint refines something already in the app.  
**Goal:** World-class first-run experience; every user can leave the logger running and return to actionable insights.

---

## Context

After 20+ sprints of feature and stability work the app works correctly. What it now lacks is **guided comprehension** — new users can run a scan but don't know what to look at, don't understand that leaving the network logger on overnight is the highest-value action they can take, and are confused about the difference between hardware being "detected" vs "added".

Three specific user-reported problems drive this plan:

1. **First-run jump to Overview** — After the 3-slide welcome, a scan starts and then the app silently drops the user on the Overview page with data but no interpretation. Users need a guided reveal that takes them through key pages *as the data populates*.

2. **Hardware stays "detected" forever** — After a user adds a hardware plugin, the Home page Getting Started card still shows it as "detected" rather than "connected". The importance of hardware integration during initial setup is also not communicated clearly enough.

3. **The logging → insights loop is invisible** — Users don't know to leave the Network Logger running. When they come back there is no "here's what we found while you were away" entry point. The flow from *logger detects an anomaly* → *diagnose it* → *fix it* → *verify it's fixed* is technically present but not connected.

---

## Sprint Index

| Sprint | Theme | Effort | Files Touched |
|---|---|---|---|
| ✅ **H1** | Guided First-Run Tour | L | `ui/guided_tour.py` (new), `ui/tabs.py`, `ui/scan_wiring.py`, `tests/test_guided_tour.py` — completed 2026-06-03 |
| ✅ **H2** | Hardware Integration State & Prominence | M | `ui/widgets/home_session_widgets.py`, `ui/pages/home_data_mixin.py`, `ui/plugin_page_mixin.py`, `ui/first_run_dialog.py`, `app.py`, `tests/test_getting_started_card.py` — completed 2026-06-03 |
| ✅ **H3** | Network Logger as First-Class Citizen | M | `ui/pages/log_hub_page.py`, `ui/pages/log_source_panel.py`, `ui/pages/diagnosis_page.py`, `ui/widgets/home_session_widgets.py`, `app.py`, `tests/test_log_hub_empty_state.py` — completed 2026-06-03 |
| ✅ **H4** | Proactive Actionable Insights | M | `ui/pages/home_page.py`, `ui/pages/home_data_mixin.py`, `ui/pages/home_suggestions.py`, `ui/tabs_logger.py`, `tests/test_home_suggestions.py` — completed 2026-06-03 |
| ✅ **H5** | Diagnosis Fix + Verify Loop | S | `ui/pages/diagnosis_page.py`, `workers/diagnosis_worker.py`, `ui/pages/home_data_mixin.py`, `ui/pages/settings_appearance.py`, `tests/test_diagnosis_page.py` — completed 2026-06-03 |
| ✅ **H6** | Empty State Consistency Audit | M | `ui/pages/overview_page.py`, `snmp_trap_page.py`, `wifi_monitor_page.py`, `geo_map_page.py`, `timeline_page.py`, `speed_test_page.py`, `trend_page.py`, `app.py` — completed 2026-06-03 |
| ✅ **H7** | Contextual Coach Marks | M | `ui/pages/log_hub_page.py`, `ui/pages/diagnosis_page.py`, `ui/pages/home_data_mixin.py`, `ui/pages/home_page.py`, `ui/pages/inventory_page.py`, `tests/test_coach_marks.py` — completed 2026-06-03 |
| ✅ **H8** | Home Page Recurring Mode Polish | S | `ui/pages/home_data_mixin.py`, `ui/widgets/home_session_widgets.py`, `ui/pages/home_page.py`, `tests/test_getting_started_card.py` — completed 2026-06-03 |
| **H9** | Page-Level Help & Keyboard Shortcuts | S | `ui/widgets/page_header.py`, `ui/help_tab.py`, `ui/pages/settings_page.py` |
| **H10** | Terminology, Tone & Milestone Cards | S | String audit across all `ui/` files |

Effort: S = 1–2 days · M = 3–5 days · L = 5–8 days

---

## Sprint H1 — Guided First-Run Tour

### Problem
After the 3-slide `WelcomeOverlay` a scan auto-starts. When the first device is found
`_set_first_run_mode(False)` fires and the app shows everything at once. A button
in the post-scan sheet says "View Overview" — the user clicks it and lands on a full
dashboard with no interpretation. **None of the key pages (Devices, Grade, Log Hub)
were ever pointed out.**

### Goal
Replace the silent post-scan jump with a **guided tour widget** that walks the user through
4 stops at the moment each page has meaningful data, then lands on Overview. The tour is
skippable at any step and never shows again once completed.

### Design

#### Tour widget — `ui/guided_tour.py` (new file, ~300 lines)

A `GuidedTour(QObject)` that attaches to the `Dashboard` instance.
It maintains a step index and owns a persistent **tour bar** widget — a
slim 48 px strip pinned below the breadcrumb that shows:
```
Step 2 of 4  ·  ● Your devices are in the Devices page   [Next →]   [Skip tour]
```

The bar uses `ui/styles.py` colours only. It is NOT a modal — the user can click
around the app normally while the tour is visible.

Each step definition:
```python
@dataclass
class TourStep:
    nav_label: str          # passed to _nav_rail_go_to()
    title:     str
    body:      str          # shown in the bar
    wait_for:  str | None   # QSettings flag that must be truthy before step activates
```

#### Steps

| Step | Navigates to | Title | Body | Wait condition |
|---|---|---|---|---|
| 1 | Devices | Your inventory | "Every device on your network is listed here. Look for Unknown devices — they are new arrivals." | scan complete (≥1 device) |
| 2 | Network Grade (Overview) | Your network score | "NetSentinel grades your network A–F across 8 dimensions. Low scores have one-click remediation." | grade worker result received |
| 3 | Log Hub | Leave this running | "The Network Logger records RTT, jitter, and DNS every 30 seconds. Leave it on and come back tomorrow for stability insights." | always (no wait) |
| 4 | Overview | The full picture | "Overview shows all active monitors, today's alerts, and your running grade. This is your home base." | always |

At Step 3 the tour auto-enables the Network RTT source toggle if it is currently off
(with a visible confirmation: "Logger started ✓"). This is the single most impactful
UX change in this plan — the user leaves with logging running without ever having
to find the toggle.

#### Trigger conditions

Tour fires when ALL of the following are true at the moment the first scan
completes:
- `QSettings("ui/first_run_done")` is True (welcome overlay was shown)
- `QSettings("tour/v1_done")` is False or absent

Stored as `tour/v1_done` = True when user either completes Step 4 or clicks "Skip tour".
Both complete the tour — skip is never punished.

#### What changes in existing files

**`ui/first_run_dialog.py`**
- Remove the direct `_nav_rail_go_to("Overview")` call that currently fires when the scan
  button is clicked
- Emit a new `scan_and_tour_requested` signal instead
- The dashboard (or `app.py`) connects this signal to start the scan AND schedule the
  tour trigger

**`ui/dashboard.py`**
- In `_on_scan_done()`: if `tour/v1_done` is False, call `GuidedTour(self).start()`
- `GuidedTour` calls `self._dashboard._nav_rail_go_to()` for each step advance

**`ui/pages/home_page.py`**
- The hero section scan button must also check: if tour is pending and scan just
  completed from the hero button, trigger the same tour

### Acceptance criteria
- [ ] User completes welcome overlay, scan runs, tour bar appears
- [ ] Each "Next →" navigates to correct page with data populated (not empty)
- [ ] Step 3 enables Network RTT source toggle automatically
- [ ] "Skip tour" on any step ends tour, persists `tour/v1_done`
- [ ] On second launch tour never shows again
- [ ] On first launch with Skip-during-welcome, tour still shows after first scan
- [ ] Tour bar is not shown on Overview or any other page during normal use after completion

### Test file
`tests/test_guided_tour.py` — import, instantiate, verify step count, verify
`tour/v1_done` is set after complete/skip.

---

## Sprint H2 — Hardware Integration State & Prominence

### Problem A: "Detected" state persists after hardware is added

`GettingStartedCard` in `ui/widgets/home_session_widgets.py` tracks hardware steps using
`QSettings("hw_zte_added")` and `QSettings("hw_deco_added")`. But after the plugin is
successfully registered by `HubCard`, these QSettings keys are **not written** from the
hardware page. The card continues showing `○ Connect 5G Modem` with an "Add →" button
even after the plugin is live. The `update_hw_status()` slot on the card exists but is
not wired to anything in `app.py`.

### Fix A
In `ui/pages/hardware_integration_page.py`, after a plugin is successfully registered:
```python
QSettings().setValue("hw_zte_added", True)   # or hw_deco_added, hw_custom_added
self.hardware_added.emit(plugin_id)           # new signal
```
In `app.py`, wire `window._hardware_page.hardware_added` → `window._home_page.on_hardware_added()`.
`on_hardware_added()` calls `GettingStartedCard.update_hw_status()` which already exists
and changes the row from `○` to `✓`.

Also write the QSettings key on app startup if the plugin registry already has an entry
(handles the case where the user added hardware in a previous session but the key was never
set).

### Problem B: Hardware importance is not communicated

Hardware integration (ZTE modem, Deco router) is listed in the Getting Started card after
core steps like "Run your first scan". But hardware integration is what makes the Devices
page useful — it adds real hostnames, signal data, and mesh topology. Without it the scan
results look generic.

### Fix B
In `ui/widgets/home_session_widgets.py`, reorder the Getting Started card steps:

**Before (current order):**
1. Connect 5G Modem
2. Connect Mesh Router
3. Run your first scan
4. Run a Network Grade
5. Turn on ARP Spoof Watch

**After (new order + copy changes):**
1. ▶ Run your first scan *(unchanged — must come first so scan data exists)*
2. ○ Connect your router (Mesh/DHCP device) — *"Get real device names, signal strength, and your full network map"*
3. ○ Connect your modem (5G/cable) — *"See signal quality in every speed test. Critical for ISP accountability."*
4. ○ Run a Network Grade *(unchanged)*
5. ○ Turn on ARP Spoof Watch *(unchanged)*

The copy on steps 2 and 3 must convey **what you lose without them**, not just what they do.

### Problem C: Hardware detection doesn't feed the Getting Started card

`hw_detect_worker.py` emits results but the Home page Getting Started card doesn't react
to detection events. When a ZTE modem or Deco router is detected on the network, the card
should change from:
```
○ Connect your router    [Add →]
```
to:
```
◉ Router detected nearby!    [Add it now →]    ← amber dot, more urgent CTA
```

### Fix C
In `app.py`, wire `hw_detect_worker.result_ready` → `window._home_page.on_hw_detected(result)`.
`on_hw_detected()` updates `GettingStartedCard` to show detected-but-not-added state
with amber indicator and "Add it now →" CTA label.

### Problem D: Welcome overlay says nothing about hardware

The 3-slide `WelcomeOverlay` covers monitoring and security but never mentions that
connecting your router/modem is what enables the full picture. Slide 2 ("Discover & protect")
should include a bullet: *"Connect your router and modem to unlock real device names and signal data."*

### Fix D
In `ui/first_run_dialog.py`, add one bullet to slide 2 (the "Discover & protect" slide):
```python
("🔌", "Connect your hardware", "Plug in your router and modem to unlock real device names and signal quality data — no extra software required.")
```

### Acceptance criteria
- [ ] After adding ZTE plugin: home page Getting Started card shows `✓ Connected` immediately without restart
- [ ] After adding Deco plugin: same
- [ ] If plugin was added in a previous session: card shows `✓` on next startup
- [ ] When hw_detect_worker finds a ZTE/Deco on network: card shows amber "detected nearby" state
- [ ] Welcome overlay slide 2 includes hardware bullet
- [ ] Getting Started card step order matches new order above

### Test file
`tests/test_getting_started_card.py` — state transitions for each step.

---

## Sprint H3 — Network Logger as First-Class Citizen

### Problem
The Network Logger (background RTT/jitter/DNS recorder) is the highest-value passive
feature in the app. A user who leaves it running for 24 hours gets stability trends,
outage windows, and ISP accountability data. But:
- It is **not mentioned in the Getting Started card**
- The **Log Hub empty state** is passive: "No log entries yet. Enable sources above."
  — no CTA, no explanation of what sources are, no sense of urgency
- When the logger IS running there is **no confirmation** on the Home page ("Logger active")
- The Diagnosis page doesn't warn when the logger hasn't run long enough to have meaningful data

### Fix 1: Add Network Logger to Getting Started

In `ui/widgets/home_session_widgets.py`, add a sixth step to `GettingStartedCard`:

```
○ Start the Network Logger    "Records RTT and DNS every 30 s — leave it on for daily insights"    [Start →]
```

Clicking "Start →" navigates to Log Hub **and** auto-enables Network RTT source.
Step completion tracked by `QSettings("logger_started_once")` = True.
The key is set when `network_logger.py` emits its first write event OR when the user
manually enables any Log Hub source.

This step should appear **after** the grade step (position 5 of 6) so core steps come first.

### Fix 2: Log Hub empty state → active CTA

In `ui/pages/log_hub_page.py`, replace the current `EmptyStateOverlay` with
an `EmptyStateCard` (following RULE-UX5):

```
Icon:  ≡  (log icon)
Title: "No logs yet — start monitoring"
Body:  "The Network Logger records RTT, jitter and DNS every 30 seconds.
        Leave it running for a few hours to see stability trends and spot outages."
CTA:   [Start Network Logger →]
```

The CTA button emits `start_logger_requested = pyqtSignal()`.
Wire in `app.py`: `window._log_hub_page.start_logger_requested.connect(window._start_network_logger)`.

This empty state only shows when ALL sources are off. As soon as one source is enabled
the normal table view shows (even if it is empty — that is fine, user can see it populating).

### Fix 3: Home page monitoring pill tooltips

In `ui/widgets/home_session_widgets.py` (`FreshnessStrip`), each pill currently has no
tooltip. Add rich tooltips:

- **Logger pill:** `"Network Logger is ON — recording RTT and DNS every 30 s. Check Log Hub for trends."`
  / OFF: `"Network Logger is OFF — click to start recording stability data."`
- **ARP pill:** `"ARP Spoof Watch is ON — detecting address-spoofing attacks in real time."`
  / OFF: `"ARP Spoof Watch is OFF — click Start Monitoring to enable."`
- (Similar for DHCP, Storm)

Pills should be **clickable** when off — clicking an off pill navigates to the relevant
page (Log Hub for Logger, ARP page for ARP, etc.) with the start action pre-focused.

### Fix 4: Diagnosis page logger warning

In `ui/pages/diagnosis_page.py`, at the top of the diagnosis results area, add a
dismissible inline warning when `network_logger.get_total_logged_hours() < 2`:

```
⚠ Network Logger has less than 2 hours of data — some findings may be incomplete.
[Start Logger →]
```

Use the existing `AMBER` colour from `ui/styles.py`. Dismissed per-session only
(not permanently — it remains relevant until the user has meaningful data).

### Acceptance criteria
- [ ] Getting Started card has "Start the Network Logger" as step 6
- [ ] Clicking it navigates to Log Hub and enables Network RTT source
- [ ] Step marked complete when any log source has been on for ≥1 minute
- [ ] Log Hub empty state shows EmptyStateCard with "Start Network Logger →" CTA
- [ ] Monitoring pills have tooltips (off and on variants)
- [ ] Clicking an off monitoring pill navigates to the relevant page
- [ ] Diagnosis page shows amber warning when logger data < 2 h

### Test file
`tests/test_log_hub_empty_state.py` — page renders without crash, CTA button exists.

---

## Sprint H4 — Proactive Actionable Insights

### Problem
`log_hub_page.py` already detects anomalies and emits `live_challenge_detected`. It
also shows a yellow banner inside the Log Hub page. But:
- The signal is **not forwarded to the Home page** — if the user is anywhere else, they miss it
- The Home page suggestions strip is **not persisted** — dismissed suggestions reappear
- There is **no "today's insights" summary** — users don't know what happened while away

### Fix 1: Home page notification for live challenges

In `ui/pages/home_page.py`, add a new slot `on_live_challenge(scenario)`.
Wire in `app.py`: `window._log_hub_page.live_challenge_detected.connect(window._home_page.on_live_challenge)`.

`on_live_challenge()` shows a persistent (not toast — permanent until acted-on) inline
banner at the top of the Home hero area:

```
📶 Connectivity issue detected at 14:23 — several failed pings to your gateway.
[Diagnose now →]   [Dismiss]
```

"Diagnose now →" calls `_nav_rail_go_to("What's Wrong?")` and pre-selects the
"Connection keeps dropping" symptom tile.
"Dismiss" hides the banner for the rest of the session.

Colour: `AMBER` background from `ui/styles.py`. Maximum one banner at a time (new
detection replaces old).

### Fix 2: Persist suggestion dismissals

In `ui/pages/home_suggestions.py`, every suggestion has an `action_key` string.
Currently dismissals are not persisted — dismissed suggestions reappear on next scan.

Change: when the user clicks an action button on a suggestion, store
`QSettings("suggestion_acted/{action_key}")` = ISO timestamp.
When building the suggestions list, filter out any suggestion whose `action_key`
has been acted on within the last 7 days.

Also add a "Snooze 7 days" option (right-click context menu on each suggestion row)
that stores `QSettings("suggestion_snoozed/{action_key}")` = ISO timestamp and hides
the suggestion for 7 days.

### Fix 3: "Since you were away" insights summary

In `ui/pages/home_data_mixin.py`, when the app starts, load a summary from
`MetricStore` covering the period since `last_seen_ts` (already stored in QSettings
as `home/last_seen_ts`). This already partially exists as the "freshness strip"
delta, but the summary should be richer:

When the app starts AND logger has data from the gap period:
- If ≥3 consecutive ping failures: show a card: *"While you were away: connectivity dropped at [time]. X failed pings."*
- If RTT increased >50% vs baseline: *"RTT is higher than usual (Xms vs Yms baseline)."*
- Otherwise: *"All clear since [time] — X pings logged, 0 issues."*

This card appears in the hero section, above the main CTA, and is dismissible.
It uses the existing `_delta_banner` infrastructure — extend it rather than build new.

### Fix 4: Suggestions strip always shows ≥1 entry after scan

The suggestions backend occasionally returns 0 suggestions (when all conditions are
green). In that case the strip disappears entirely, which makes it feel unreliable.

Add a fallback suggestion that always appears when no other suggestions exist and the
user has never enabled the Network Logger:

```python
{"action_key": "start_logger", "priority": "low",
 "text": "Enable the Network Logger to track stability over time",
 "action": "Log Hub", "button": "Start →"}
```

This ensures the "WHAT TO DO NEXT" section never shows empty, which would confuse
users into thinking there's nothing left to do.

### Acceptance criteria
- [ ] Live challenge banner appears on Home page when anomaly detected in Log Hub
- [ ] "Diagnose now →" navigates to Diagnosis with correct symptom pre-selected
- [ ] Acted-on suggestions do not reappear within 7 days
- [ ] Right-click on suggestion shows "Snooze 7 days" option
- [ ] "Since you were away" summary card shows on startup when logger detected issues
- [ ] "WHAT TO DO NEXT" section always shows ≥1 entry after first scan

### Test file
`tests/test_home_suggestions.py` — suggestion persistence, snooze expiry, fallback entry.

---

## Sprint H5 — Diagnosis Fix + Verify Loop

### Problem
`CorrelatedFinding` in `modules/root_cause_correlator.py` already has a `verify_step`
field (line 51) with text like *"After restarting your router, run What's Wrong? again
to confirm the gateway is responding."* But this field is **never rendered in the UI**.
Users complete a remediation step with no way to verify it worked.

### Fix 1: Render verify_step in finding cards

In `ui/pages/diagnosis_page.py`, each finding card (both hero and collapsible) should
show the `verify_step` text below the remediation:

```
Remediation:
  Restart your router by unplugging it for 30 seconds.

After fixing:
  ▶ Verify this fix   ← QPushButton, secondary style
```

The "Verify this fix" button stores which finding it belongs to (by `headline` hash) and:
1. Triggers a focused re-run of the DiagnosisWorker with `focused=True` mode
2. Shows a spinner ("Checking...")
3. On completion: if the finding is gone → show `GREEN` ✓ "Fixed!" label
4. If the finding persists → show `AMBER` "Still present — try next step" with a link to
   the relevant follow-up page

### Fix 2: DiagnosisWorker focused mode

In `workers/diagnosis_worker.py`, add an optional parameter `focused_on: str | None = None`.
When set, the worker runs only the subset of checks relevant to the named finding
(e.g., for "gateway not responding" only run ping-to-gateway, not full discovery scan).

This keeps the verify round-trip fast (< 5 seconds for most findings) so the user
stays in the flow.

### Fix 3: Post-scan sheet is recoverable

Currently `home/post_scan_sheet_dismissed` is stored permanently — once the user
closes the post-scan sheet it never shows again, even on the next app launch.

Change: store the dismissal as a per-scan timestamp. If the user runs a new scan,
show the post-scan sheet again (with fresh data from the new scan). The sheet should
feel like "your latest scan summary", not a one-time tutorial.

Also: add a persistent "summary" link in the `FreshnessStrip` (bottom-left of the
freshness bar):
```
Last scan: 5m ago  ·  [3 findings]    ← clickable, re-shows the post-scan sheet
```

The `[3 findings]` label is a `QPushButton` with `flat=True` that re-shows the sheet.

### Acceptance criteria
- [ ] Each diagnosis finding card shows `verify_step` text and "Verify this fix" button
- [ ] Clicking "Verify this fix" runs a fast re-check and shows ✓ or "still present"
- [ ] DiagnosisWorker accepts `focused_on` parameter and skips irrelevant checks
- [ ] Post-scan sheet reappears on every new scan (not permanently dismissed)
- [ ] Freshness strip shows `[N findings]` link that re-opens the post-scan sheet

### Test file
Extend `tests/test_diagnosis_page.py` with verify_step rendering tests.

---

## Sprint H6 — Empty State Consistency Audit

### Problem
Pages that use `EmptyStateCard` (Inventory, History, Cert, Uptime, Service, Network Doc)
correctly follow RULE-UX5. Pages that use raw `EmptyStateOverlay` without a CTA button
are RULE-UX5 violations. The Overview page violates RULE-UX5 by showing empty tiles.

### Audit and fix list

| Page file | Current empty state | Fix |
|---|---|---|
| `ui/pages/log_hub_page.py` | `EmptyStateOverlay` — passive | Replace with `EmptyStateCard` + "Start Network Logger →" *(done in H3)* |
| `ui/pages/overview_page.py` | Empty tiles visible | `QStackedWidget`: page 0 = `EmptyStateCard` + "Scan Network →", page 1 = normal tiles. Switch to page 1 on first `on_cycle_done()` |
| `ui/pages/snmp_trap_page.py` | "No traps received yet" text | `EmptyStateCard`: "Waiting for SNMP traps" + "Configure source →" |
| `ui/pages/wifi_monitor_page.py` | "No frames captured" text | `EmptyStateCard`: "No frames yet" + "Start monitoring" CTA |
| `ui/pages/geo_map_page.py` | Empty map | If no devices: overlay card "Run a scan to plot device locations" + "Scan →" CTA |
| `ui/pages/timeline_page.py` | Empty table | `EmptyStateCard`: "No events yet" + "Run a scan to populate the timeline" |
| `ui/pages/speed_test_page.py` | Empty history table | `EmptyStateCard`: "No speed tests yet" + "Run Speed Test →" |
| `ui/pages/trend_page.py` | Blank chart | `EmptyStateCard`: "No trend data yet — run scans daily for at least 3 days" + "Scan →" |

For each page:
1. Create a `QStackedWidget` with page 0 = `EmptyStateCard`, page 1 = current content
2. Add `scan_requested = pyqtSignal()` if page needs a scan CTA
3. Wire the signal in `app.py` per RULE-UX5

### Overview page empty state (priority)

Overview is the default landing page for many users. Seeing 12 empty tiles with "—"
and "No data" is the worst first impression in the app. This fix alone will eliminate
the most common new-user confusion.

The `EmptyStateCard` for Overview:
```
Icon:  ⬡  (hexagon)
Title: "Your network at a glance"
Body:  "Scan your network to populate the overview dashboard — devices, grade, alerts and stability all in one place."
CTA:   [Scan my network →]
```

### Acceptance criteria
- [ ] Overview page shows `EmptyStateCard` on first launch, not empty tiles
- [ ] All 8 pages listed above have active CTAs in empty state
- [ ] `scan_requested` signal is wired per RULE-UX5 for each page that uses it
- [ ] `python -m pytest tests/test_nav_completeness.py -v` still passes
- [ ] `python tools/debug_launch.py` confirms clean launch after all changes

---

## Sprint H7 — Contextual Coach Marks

### Problem
`ui/widgets/coach_mark.py` implements a polished `CoachMarkChain` that highlights widgets
with bubbles. It is keyed to `QSettings("onboarding_v6_done")` — once true, it never runs
again. That means:
- Users who skipped or clicked through quickly never get guidance inside the app
- Complex features (Network Grade breakdown, Log Hub source panel, Diagnosis symptom selector)
  have no contextual help on first use

### Design

Add **contextual coach marks** (not first-run) keyed to per-feature flags:

```python
# Pattern for every contextual coach mark:
qs = QSettings()
key = "coach/log_hub_sources_shown"
if not qs.value(key, False, bool):
    chain = CoachMarkChain(self, steps)
    chain.finished.connect(lambda: qs.setValue(key, True))
    chain.start()
```

Each mark fires only once per feature, independently of the global first-run flag.
The QSettings key naming convention: `coach/{feature_name}_shown`.

### Coach mark definitions

#### Log Hub — first visit (fires when page first shown and logger is off)
Target: the sources toggle bar  
Title: "Choose what to log"  
Body: "Toggle Network RTT to start logging ping latency every 30 seconds. Leave it on for 24 hours for the best insights."  
Button: "Start Network RTT →"

#### Network Grade — first grade result (fires when Grade page first shows an A–F result)
Target: the grade ring widget  
Title: "Your network grade"  
Body: "This score reflects 8 dimensions of network health. Click the ring to see the breakdown and improve your score."  
Button: "See breakdown →"

#### Diagnosis — idle page first visit (fires when Diagnosis page first shown with no results)
Target: the symptom tile row  
Title: "Describe your symptom"  
Body: "Pick the symptom closest to what you're experiencing. NetSentinel runs targeted checks instead of a full scan — takes 30 seconds."  
Button: "Got it"

#### Devices page — first device row right-click hint
Show a small coach bubble pointing to the first device row:  
Title: "Right-click for actions"  
Body: "Right-click any device row to label it, check its ports, or add it to your watchlist."  
Button: "Got it"

#### Overview — first time monitoring pills are visible on home page
Target: the ARP Watch pill  
Title: "Your monitors"  
Body: "These run in the background. Enable ARP Watch to detect spoofing attacks; enable Logger to record stability data."  
Button: "Got it"

### Acceptance criteria
- [ ] Log Hub coach mark fires on first visit when logger is off, not again after
- [ ] Network Grade coach mark fires when first result arrives, not again after
- [ ] Diagnosis coach mark fires on first visit to idle Diagnosis page, not again after
- [ ] Devices right-click coach mark fires once on first device result
- [ ] All marks respect their individual QSettings flags (clearing one flag re-shows that mark, others unaffected)
- [ ] `python -m pytest tests/` passes (no import errors from coach mark wiring)

---

## Sprint H8 — Home Page Recurring Mode Polish

### Problem
At ≥5 scans completed the Home page switches from "first-run layout" to "recurring layout"
— monitoring status, weekly metrics, live events ticker. This is a significant visual change
with no explanation. Users who see it for the first time think the app broke.

Also: the post-scan sheet (addressed in H5) needs a visible "summary" link in the
freshness strip so users can always find it.

### Fix 1: Recurring mode transition card

In `ui/pages/home_data_mixin.py`, when transitioning to recurring mode (the 5th scan):
show a one-time slide-in card above the content area:

```
┌─────────────────────────────────────────────────────────────────── [×] ──┐
│  ⬡  Home page upgraded                                                    │
│                                                                            │
│  You've run 5 scans — great work. The home page now shows your             │
│  monitoring status and this week's activity summary.                       │
│                                                                            │
│  Your devices and grade history are still in the Discover and Reports     │
│  sections. Press Ctrl+K to find any page instantly.                        │
└────────────────────────────────────────────────────────────────────────────┘
```

This card uses `ACCENT` left border, `BG_CARD` background, dismissible with ×.
Persisted: `home/recurring_mode_intro_shown` = True.

### Fix 2: Getting Started card completion state

When all 6 Getting Started steps are complete (scan done, hardware added, grade run,
ARP enabled, logger started), replace the card entirely with a **completion celebration card**:

```
✓  All done — your network is set up and monitored
   Network logger is running · ARP Watch is active · Grade: A
   [Explore features →]    [View this week's summary →]
```

"Explore features →" navigates to the Feature Guide (Discover section).
"View this week's summary →" opens the weekly digest if one exists, otherwise navigates
to Overview.

The completion card replaces the GettingStartedCard in the same position.
Completion state: `QSettings("setup/all_done")` = True.

### Fix 3: Monitoring pills show "last event" on hover

In `FreshnessStrip`, each active pill currently shows only the name and colour dot.
Add a tooltip showing the last event from that monitor:

- **Logger pill (active):** `"Logging since 2h 15m ago · Last entry: 14:47 · RTT: 23ms"`
- **ARP pill (active):** `"ARP Watch active · Last check: 2m ago · 0 events"`

This is purely tooltip text — no layout change. Use `ToolTip` already in use elsewhere.

### Acceptance criteria
- [ ] On 5th scan, recurring-mode intro card shows once
- [ ] Card dismissed with × and never shown again
- [ ] When all 6 steps complete, GettingStartedCard replaced with completion card
- [ ] "Explore features →" navigates to Feature Guide
- [ ] Active monitoring pills show last-event tooltip text

---

## Sprint H9 — Page-Level Help & Keyboard Shortcuts

### Problem
The Quick Tips card on the Home page is the only in-app discovery mechanism for power-user
features. It is dismissible forever. Most users dismiss it on first launch without reading.
Keyboard shortcuts, right-click menus, and the command palette remain largely undiscovered.

### Fix 1: ? button on every page header

`ui/widgets/page_header.py` already has an actions bar (`_header_bar`). Add a standard
`?` button (secondary icon button) to every page header. Clicking it shows a
`QDialog` (or the existing tip bar) with page-specific help content pulled from
`_PAGE_HELP` (which already exists for all pages per RULE-D1).

The dialog shows:
```
[Page Name] Help

What this page does:
  [first line of _PAGE_HELP]

How to use it:
  [second line of _PAGE_HELP]

Keyboard shortcuts:
  Ctrl+K   Open command palette
  Ctrl+F   Focus sidebar search
  Esc      Close flyout
  [page-specific shortcuts if any]
```

This is a **read-only display dialog**, not interactive. Style: `BG_CARD` background,
`16px` title, `12px` body, close with Esc.

### Fix 2: Keyboard shortcuts reference page

In `ui/pages/settings_page.py` or the Help tab (`ui/help_tab.py`), add a
"Keyboard Shortcuts" section listing all global and page-specific shortcuts in a
2-column table.

Global shortcuts to document:
- `Ctrl+K` — Command palette (find any page)
- `Ctrl+F` — Focus sidebar search
- `Esc` — Close flyout / dismiss dialog
- `F5` — Rescan
- Right-click device row — Actions menu
- Right-click nav item — Pin to sidebar

This section already belongs in the Help tab — it just doesn't exist yet.

### Fix 3: Remove Quick Tips card from Home page

The Home page Quick Tips card (`_tips_card`) is displaced by:
1. The guided tour (H1)
2. The ? button on every page header (this sprint)
3. The keyboard shortcuts reference (this sprint)

Remove the `_tips_card` entirely from `home_page.py`. Clean up the `QSettings`
`home/tips_dismissed` key (no longer needed). This reduces Home page noise.

### Acceptance criteria
- [ ] Every page in the app has a ? button in the page header
- [ ] ? button shows a dialog with page help from `_PAGE_HELP`
- [ ] Help tab (or Settings) has a "Keyboard Shortcuts" section with all global shortcuts
- [ ] Quick Tips card removed from Home page
- [ ] `python -m pytest tests/` passes

---

## Sprint H10 — Terminology, Tone & Milestone Cards

### Problem
The app uses "findings", "alerts", "issues", and "problems" inconsistently across pages.
Users don't have a mental model of "which screen tells me what". Scan completion emits
no visible notification. There is no acknowledgement of milestones (first week of logging,
100th scan, etc.) that would reinforce the habit loop.

### Fix 1: Terminology consistency audit

Audit all user-visible strings in `ui/pages/*.py` and `ui/widgets/*.py`:

| Term to standardise | Use it for | Avoid |
|---|---|---|
| **Finding** | Root cause correlator output (`CorrelatedFinding`) | "issue", "problem" |
| **Alert** | Rule-triggered notification (`AlertEngine` output) | "warning", "event" (ambiguous) |
| **Event** | Timeline / Log Hub entry | "log", "record" |
| **Insight** | The broader category on Home page "What to do next" section | "suggestion", "tip" |

This is a grep-and-replace pass — no logic changes. Run `test_source_encoding.py`
after to ensure no mojibake.

### Fix 2: Scan completion toast

In `ui/dashboard.py`, when `_on_scan_done()` fires, emit a non-blocking `Toast`:

```python
Toast(self, f"Scan complete — {n_devices} devices · Grade {grade}", style="success")
```

This uses the existing `ui/widgets/toast.py` infrastructure. The toast disappears
after 4 seconds automatically. It is shown on every scan completion, including
auto-scheduled rescans.

If the grade changed since the previous scan: *"Scan complete — Grade improved from B to A"*
or *"Scan complete — Grade dropped from A to B — 2 new findings"* (with amber/red style).

### Fix 3: Milestone cards

Define a set of milestones and show a one-time card on the Home page when each is reached:

| Milestone | Message | QSettings key |
|---|---|---|
| 24h of logging | "You've been monitoring for 24 hours. Here's what we found: [N events, X ms avg RTT]." | `milestone/logger_24h` |
| 7 days of logging | "7 days of data. Your network stability score is [X%] — above/below average for home networks." | `milestone/logger_7d` |
| 10th scan | "You've run 10 scans. Your network grade has been [A/B/C] on average." | `milestone/scan_10` |
| First alert acknowledged | "Alert acknowledged! Your history is in Notifications → Alert History." | `milestone/first_ack` |

Cards are dismissible, appear once each, styled with `ACCENT` left border.

### Fix 4: Error message audit

Audit all `error` signal handlers in `ui/pages/*.py` for RULE-A2 compliance:
*every error message must say what failed, why it likely failed, what to try next.*

Pattern to find and fix:
```python
# BAD — raw exception shown
self._status.setText(f"Error: {e}")

# GOOD — translated for user
self._status.setText(
    "Scan failed — network may be unavailable. "
    "Check your Wi-Fi connection and try again."
)
```

Run a grep for `f"Error: {e}"` and `str(e)` in UI files to find violations.

### Acceptance criteria
- [ ] "findings", "alerts", "events", "insights" used consistently across all pages
- [ ] Scan completion toast shows on every scan, style changes if grade improved/dropped
- [ ] 4 milestone cards defined and triggered correctly (fire once each)
- [ ] Grep for `f"Error: {e}"` in `ui/` returns 0 results
- [ ] `python -m pytest tests/ -q` passes after all string changes

---

## Sprint Sequencing Rationale

**Start with H1 (Guided First-Run Tour)** — this fixes the most visible and reported problem.
Every new user hits it. The tour also auto-enables the logger (H3's core goal) so the rest
of the onboarding chain flows naturally.

**H2 (Hardware) and H3 (Logger)** can run in parallel after H1 since they touch different files.

**H4 (Insights) depends on H3** — the proactive anomaly nudge needs the logger running.

**H5 (Verify Loop) is independent** — touches only Diagnosis files. Can run in parallel with H2/H3.

**H6 (Empty States) is a sweep sprint** — safe to run any time, low risk. Good to run
after H1–H5 as a polish pass before external review.

**H7 (Coach Marks) depends on H1** — many of the coach marks fire in contexts that H1's
tour already visits. Coordinate so tour steps and coach marks don't overlap.

**H8–H10** are polish passes. H8 can be batched with H6 if time allows.

---

## Files Not to Touch

These files contain correct, stable implementations that solve adjacent problems. Do not
refactor or "improve" them during this plan's sprints:

- `modules/root_cause_correlator.py` — findings engine is good; only add `verify_step` rendering (H5)
- `ui/nav/rail.py`, `ui/nav/builder.py` — navigation is working; no structural changes
- `ui/dashboard.py` — only add tour trigger and scan-completion toast; no restructure
- `modules/metric_store.py` — no schema changes
- `ui/styles.py` — only additive (new colour constants if needed)

---

## Verification Checklist (After All Sprints)

Run before any version bump:

```powershell
# 1. Full test suite
python -m pytest tests/ -q

# 2. App launch gate
python tools/debug_launch.py
# Confirm: "Dashboard() instantiated OK" + "window.show() called OK" in log

# 3. Encoding check
python -m pytest tests/test_source_encoding.py -v

# 4. Version consistency
python -m pytest tests/test_version_consistency.py -v

# 5. Nav completeness
python -m pytest tests/test_nav_completeness.py -v
```

User-facing acceptance (tell user to verify):
- [ ] Launch app fresh (delete QSettings key `ui/first_run_done` to simulate first-run)
- [ ] Complete welcome overlay → scan starts → guided tour bar appears
- [ ] Follow tour to Devices, Grade, Log Hub (logger auto-starts), Overview
- [ ] Navigate to Log Hub → empty state shows CTA button
- [ ] Add a hardware plugin → Getting Started card updates immediately
- [ ] Run Diagnosis → each finding card shows "Verify this fix" button
- [ ] Leave app for 1 hour with logger on → restart and see "Since you were away" card

---

## Version Bump Target

This plan spans approximately 8–10 working days of implementation. Suggested version bump:

| Sprint(s) | Version |
|---|---|
| H1–H2 | v1.9.77 |
| H3–H5 | v1.9.78 |
| H6–H8 | v1.9.79 |
| H9–H10 | v1.9.80 |

Each version gets a README changelog entry per RULE-R1b before bumping.

---

*Plan created: 2026-06-03. Source: UX audit across first_run_dialog.py, home_page.py,*
*home_data_mixin.py, home_session_widgets.py, log_hub_page.py, diagnosis_page.py,*
*root_cause_correlator.py, hardware_integration_page.py, hub_card.py, overview_page.py,*
*coach_mark.py, home_suggestions.py.*
