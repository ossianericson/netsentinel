# NetSentinel — Onboarding Visual Fix Plan v3
# Sprint Series J — Apple-Level First-Run Experience

**Created:** 2026-06-04  
**Status:** Active — supersedes V2 plan  
**Priority:** Fix visual chaos before adding any more logic  
**Goal:** One smooth, coherent journey that delivers immediate value — no random boxes, no jumping around.

---

## Screenshot Audit — What Is Actually Broken

### Home Page (01_home.png)

**What the user sees first:**
```
[Theme buttons: Light  Dark  Neon  Abyss]   ← FIRST VISIBLE ELEMENT. Wrong.
GETTING STARTED | 0/6 done
  ○ Run your first scan
  ○ Connect your router                          [Add →]
  ○ Connect your modem                           [Add →]
  ○ Run a Network Grade
  ○ Turn on ARP Spoof Watch
  ○ Start the Network Logger
  [×]

  What's on your network?
  [Scan Network]  [What's Wrong?]

  THE THREE THINGS THAT MATTER
  Speed —    Stability —    Devices —    ← looks broken

  MONITORING:  ○ ARP  ○ DHCP  ○ Storm  ○ Logger
  Monitoring is off.  [Start Network Logger]

  STABILITY MONITORING
  • Not running ○ start to log...             [Start Monitoring]  [View Log ∨]

  WHAT TO DO NEXT
  • Try a guided exercise...
  • Get an A–F score...
  • Generate a network health report...

  RECENT ALERTS
  No alerts — configure alerts in Settings
```

**Failures:**
1. **Theme switcher is the first interactive thing users see.** It should be in Settings, not floating above the Getting Started card.
2. **Eight competing sections** — all visible, all asking for attention, most empty. The user has no idea what to look at.
3. **"Three things that matter" shows dashes** — looks like the app is broken, not that it needs a scan.
4. **Three separate monitoring sections** (MONITORING pills, STABILITY MONITORING card, WHAT TO DO NEXT list) all say "not running" in different ways. Repetitive and demoralising.
5. **Getting Started card is visually weak** — tiny grey circles, "0/6 done" counter, two orphaned "Add →" buttons floating on the right with no visual connection to their rows.
6. **"Tips for Home ℹ"** link below breadcrumb looks like a legal footnote, not helpful guidance.

---

### Overview Page (04_overview.png)

**What the user sees:**
```
Overview
Live dashboard — drag tiles to rearrange in Edit Layout mode.
[Devices ∨] [Grade ∨] [Alerts: 0] [Services ∨]     [What's Wrong?] [Share Card+] [Edit Layout] [Rescan] [Export∨]

▼ How is the grade calculated?

┌──────────────────────────────────────────────────────┐
│                       ○                               │
│          Your network at a glance                     │
│  WHAT THIS PAGE SHOWS:                                │
│  Devices, network grade, active alerts...             │
│  WHY IT MATTERS:                                      │
│  A single dashboard to know whether your network...  │
│  [Scan my network →]                                  │
└──────────────────────────────────────────────────────┘

▼ Security Scan                                         ← shown BELOW the empty state?!
  ⚠ These tools actively probe devices...
  ☐ Threat Intelligence    ☑ TLS Certificates
  ☐ Device Risk Score      ☐ Known CVEs
  ☐ Port Scan (CTL) ⚠      ☐ Exposed to Internet ⚠
                                          [Run Selected]
```

**Failures:**
1. **Empty state card is fine but "Security Scan" appears below it** — this makes no sense. Why show scan checkboxes when the page is empty?
2. **"How is the grade calculated?" accordion** is shown when there is no grade. That text belongs on the grade page.
3. **Four filter pills** (Devices, Grade, Alerts, Services) with no data — they serve no purpose yet.

---

### Devices Page (05_devices.png)

**What the user sees:**
```
TOTAL NODES: —   CRITICAL RISK: —   UNAUTHORISED: —   SCAN STATUS: Idle

Not yet scanned.
┌──────────────────────────────────────────────────────────────────┐
│ DISCOVERED DEVICES                                                │
│ [Search IP, hostname, MAC, vendor...]  [All][Strong][Other]...  │
│                                                                  │
│                                                                  │
│           Run a scan to discover devices on this network.        │
│                                                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

**Failures:**
1. **KPI tiles show dashes** above the empty state — four tiles of `—` reinforce "broken" feeling.
2. **"Not yet scanned."** text above the card, then the empty state message inside the card — two different messages saying the same thing.
3. **Empty state has no CTA button** (RULE-UX5 violation) — passive text "Run a scan to discover devices" with no button.

---

### Network Logger (02_log_hub.png)

**What the user sees:**
```
LOG SOURCES
Active pollers: [✓] Ping RTT 60s  [✓] Jitter  [ ] DNS latency  [ ] HTTP check
               [ ] 5G Modem signal  [ ] Mesh router status

Passive listeners: [✓] ARP watch  [ ] Syslog receiver  [✓] SNMP trap receiver

[■ Stop Logger] [Open Log File] [Load Analysis] [View Chart] [Rotate File] [12 Hour ∨] [✓ Auto-start on launch]

Logger started — pinging every 60s → netlog_20260604_07343.csv

TOTAL PINGS: —   UPTIME: —   AVG RTT: —   OUTAGES: —

Log Analysis:
  Load a log file to see automatic diagnostic findings here.

Detected Outages:
  HOST | OUTAGE START | OUTAGE END | DURATION | CONSECUTIVE FAILS
  (empty)

Live log (most recent pings):
  TIMESTAMP | HOST | RTT (MS) | JITTER | DNS (MS) | HTTP | ARP EVENT | STATUS
  (empty)
```

**Failures:**
1. **Logger says "started" but all KPI tiles show dashes** — user has no feedback that logging is actually working.
2. **Two empty tables with column headers** — looks abandoned.
3. **Log Analysis placeholder text** in a grey box — looks like filler content.
4. **Source checkboxes are a wall of form controls** — no visual hierarchy, no explanation of which sources matter most.

---

## The Standard We're Aiming For

### What Apple does (and we must copy)

**Apple's iPhone setup:**
- One task per screen
- No competing information
- The UI is *quiet* — everything not relevant to the current step is hidden or greyed
- Progress is visible but not intrusive (small dots at bottom, not "0/6 done" badges)
- Each step delivers immediate, visible value before asking for the next action
- Animations are purposeful — they communicate "this moved from here to there", not just decoration
- Empty states are beautiful invitations, not broken-looking gaps

**Applied to NetSentinel first-run:**

```
WRONG (current):
  App opens → 8 sections visible → user paralysed → closes app

RIGHT (target):
  App opens → one beautiful card says "Let's find your devices" → 
  scan starts → devices appear one by one → user feels the tool working →
  "Nice, 14 devices found. Here's what matters." → natural next step offered
```

### The 3 non-negotiable design principles for this fix

**1. Hide until earned**  
Empty tiles, dashes, and "not yet run" sections must be HIDDEN until data exists. Not shown as dashes. Not shown with placeholder text. Hidden.

**2. One dominant action per screen**  
The home page may only have ONE primary button visible at a time. Right now it has: Scan Network, What's Wrong?, Start Network Logger, Start Monitoring, three bullet-point actions, and theme switcher buttons. That is 8+ calls to action. Max 1.

**3. Smooth means: the user never waits for nothing**  
If a scan takes 30s, show something moving. If the tour advances to a new page, the navigation should feel intentional — a 200ms fade, then spotlight on one element, then a clear sentence of value. Not: navigate → random box appears → user reads it → clicks Got It → nothing changes → another box appears.

---

## Sprint J1 — Home Page Surgery (DO FIRST, highest visual impact)

**Files:** `ui/pages/home_page.py`, `ui/pages/home_data_mixin.py`, `ui/widgets/home_session_widgets.py`, `ui/styles.py`  
**Effort:** M (3–4 hours)

### Fix J1-A: Remove theme switcher from home page

The theme buttons (`_theme_row` / `_theme_group`) are appearing in the home page content area. This is wrong — they belong in Settings.

**Locate in `ui/pages/home_page.py`:** Find where the Light/Dark/Neon/Abyss buttons are built.  
**Action:** Remove entirely from `home_page.py`. The Settings page already has a theme card — this is the only place it should exist.

If these buttons were added as part of Sprint H10, they must be reverted. The home page is not a settings panel.

### Fix J1-B: Collapse all empty sections until scan runs

**Current:** 8 sections visible, most showing dashes or "not yet run".  
**Target:** Show ONLY the Getting Started card + scan button until the first scan completes.

In `home_page.py` / `home_data_mixin.py`, implement a `_pre_scan_mode` that:
- Shows: Getting Started card + hero section (ONE scan button, full width)  
- Hides: "Three things that matter" strip, monitoring pills row, stability monitoring card, what to do next section, recent alerts section

Switch out of `_pre_scan_mode` on `on_scan_done()`. Animate the reveal with a 300ms opacity fade.

```python
# In _init_layout():
self._pre_scan_sections = [
    self._three_things_card,
    self._monitoring_row,
    self._stability_section,
    self._suggestions_section,
    self._alerts_section,
]
for w in self._pre_scan_sections:
    w.setVisible(False)

# In on_scan_done():
for w in self._pre_scan_sections:
    w.setVisible(True)
    # fade in with QPropertyAnimation opacity 0→1, 300ms
```

### Fix J1-C: Redesign the Getting Started card

**Current:** Tiny grey circles, "0/6 done" text counter, orphaned "Add →" buttons.  
**Target:** A card that feels like a proper setup checklist — clear, weighted, progress visible.

```
┌─ SETUP                                              ────────────────────────────────────── [×] ─┐
│                                                                                                   │
│  ████████████░░░░░░░░  2 of 6 complete                                                           │
│                                                                                                   │
│  ✓  Run your first scan          Discovered 14 devices                                           │
│  ✓  Connect your router          TP-Link Deco XE75 connected                                     │
│  ▶  Run a Network Grade          Score your network A–F — takes 60 seconds    [Run →]            │
│  ○  Connect your modem           See ISP signal quality in every speed test                      │
│  ○  Turn on ARP Spoof Watch      Detects spoofing attacks in real time                           │
│  ○  Start the Network Logger     Leave it on overnight for stability trends                      │
│                                                                                                   │
└───────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Key visual changes:
- **Progress bar** (linear, `ACCENT` fill) at the top, not "0/6 done" text
- **Completed steps** (`✓`) use `GREEN` text and lighter row background — visually satisfying
- **Active step** (`▶`) is highlighted with `ACCENT` left border and a CTA button — only ONE active step at a time
- **Future steps** (`○`) are grey text — visible but not shouting
- **No orphaned buttons** — the action button is inline with its row, right-aligned, but visually connected
- **Card uses `BG_CARD` background with `ACCENT`-coloured left border strip (4px)** — clear visual weight

Implementation in `ui/widgets/home_session_widgets.py`:
- Replace circular step indicators with a proper `QProgressBar` at top
- Mark only the NEXT incomplete step as "active" — not all incomplete steps equally
- Completed rows: light `GREEN` background tint `(GREEN + "18"` alpha hex)
- Active row: `ACCENT + "12"` alpha background + full `ACCENT` left border 4px

### Fix J1-D: Collapse the hero when Getting Started is visible

When the Getting Started card is visible (pre-scan-complete), the hero section should be MINIMAL:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  What's on your network?                                                                          │
│  Discover every device, check stability, detect threats.                                          │
│                                                       [→ Scan my network]                        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Remove "What's Wrong?" from the hero — it's secondary. One primary CTA only.

After scan completes, the hero can expand to show the grade ring, device count, and "What's Wrong?" as a secondary action.

### Fix J1-E: "Tips for Home ℹ" — remove or integrate

The tips link below the breadcrumb looks like an afterthought. Either:
- Remove entirely (the `?` button in the page header per Sprint H9 replaces it), OR
- Move it into the page header as a `?` icon button (already implemented in `ui/widgets/page_header.py`)

Do NOT show it as a link below the breadcrumb.

---

## Sprint H11 — Onboarding Tour Redesign (IMPLEMENT FIRST) ← YOUR DESIGN

### Step Sequence (9 steps, value-first)

| # | Title | What happens | What the user sees |
|---|---|---|---|
| 1 | Scan your network | Navigate to Overview. Trigger full scan immediately. Spotlight the scan button. | Button changes to "Scanning…", tiles show skeleton rows — something is happening |
| 2 | Devices found | Wait for first device batch (~15 s). Navigate to Devices. | Real device list with MACs, OUIs, IP addresses — first "wow" moment |
| 3 | Your network grade | Navigate to Overview. Grade ring is now populated. | Grade letter visible; spotlight the ring + "How is this calculated?" toggle |
| 4 | Speed Test (running since step 1) | Navigate to Speed Test. Gauge already moving. | Live gauge needle, engine badge — user sees it mid-test |
| 5 | Network Logger | Navigate to Log Hub. Logger already recording. | Spotlight sources bar + activity log — both populated |
| 6 | Hardware Integration | Navigate to Hardware. Show detected devices. | Spotlight the hub scroll; explain 30-second add flow |
| 7 | Home — your starting point | Navigate to Home. GettingStartedCard visible. | Spotlight checklist (what's done ✓), suggestions strip |
| 8 | Find anything — Ctrl+K | Stay on Home. Spotlight command palette button. | User has visited 5 pages — Ctrl+K now makes sense |
| 9 | You're set | Navigate to Overview. Tour bar shows "Finish ✓". | Full tile grid, live data in every tile — close tour |

### Key changes from the old 9-step flow
- Steps 1–3 (shell orientation: nav rail, breadcrumb, health badge) → **deleted** — self-explanatory after visiting 5 pages
- Scan fires **on step 1**, visible to the user — not hidden in `_fire_background_scans()` before step 1
- **Devices page added** (currently missing) — first tangible result of the scan
- Hardware step spotlights **real detected hardware**, not generic text
- **Ctrl+K moved to step 8** — user has context after visiting 5 pages
- **Home page at step 7** — GettingStartedCard shows 3–4 checkmarks already ticked, not zero

### `_fire_background_scans()` changes
Remove the pre-start pattern. Step 1's `auto_action` calls:
```python
_start_full_scan()           # device scan — fires immediately
_auto_speed_test()           # speed test starts 500 ms later
_auto_logger()               # logger starts 1 s later
```
Steps 2–9 display results of those **already-running** scans, not new ones.

### Files to touch
- `ui/onboarding.py` — full step list rewrite (~150 lines)
- No other files required — all spotlight targets exist after this session's fixes

---

## Sprint J2 — Onboarding Flow Rewrite (THE CORE PROBLEM)

**Files:** `ui/onboarding.py`, `ui/guided_tour.py`, `ui/dashboard.py`, `ui/tabs.py`  
**Effort:** L (5–6 hours)

### The Problem with the Current OnboardingOrchestrator

The current design (from V2 plan) navigates to 9 pages and fires SpotlightChains on each. In practice this means:

```
User sees: Flyout opens → "9 sections, all your tools" box appears
User clicks: Got it
Box disappears → no navigation, no change
Another box: "Or click here" pointing at magnifier
User clicks: Got it
Another box: "Always know where you are" pointing at breadcrumb
User clicks: Got it
...7 more steps of this
```

This is not onboarding. It is a slideshow of arrows. The user learns nothing because they are clicking away boxes, not interacting with the app.

### The Replacement: Value-First 4-Step Flow

Throw out the 9-step nav-and-spotlight design. Replace with a 4-step flow where each step has **ONE clear goal** and the UI *shows the result* before moving on.

```
Step 1: DISCOVER (automatic, user watches)
  - Scan starts immediately on first launch (no "click to start" — just starts)
  - Tour bar says: "Finding your devices... (14 found so far)"
  - Live count ticks up as devices appear
  - Next → unlocks when scan is done (or 30s timeout)

Step 2: UNDERSTAND (devices page, already populated)
  - Navigate to Devices automatically
  - Page shows real device list that just populated
  - Tour bar says: "These are your devices — the ones in red need attention"  
  - Spotlight: ONE soft highlight on the first "Unknown" device row (if any)
  - No multiple spotlights. One thing. ONE sentence.
  - Next → available immediately

Step 3: PROTECT (Network Logger — auto-start)
  - Navigate to Network Logger automatically
  - Logger starts automatically (user doesn't need to do anything)
  - Tour bar says: "Logger running — recording every 30 seconds. Come back tomorrow for stability data."
  - Spotlight: the KPI tiles that are now ticking
  - Next → available immediately

Step 4: DONE (back to Home)
  - Navigate to Home
  - Tour bar says: "You're set up. Run the grade when ready."  [Run Grade →]  [Done]
  - Show the Getting Started card in its improved form
  - Clicking Done sets tour/v1_done = True, hides bar
```

### Implementation: New Simplified Orchestrator

Replace the current `OnboardingOrchestrator` in `ui/onboarding.py` with a simpler state machine:

```python
# 4 states, not 9 steps
STATE_SCANNING = "scanning"   # scan running, live feedback
STATE_DEVICES  = "devices"    # navigated to Devices, show results
STATE_LOGGER   = "logger"     # navigated to Logger, auto-started
STATE_DONE     = "done"       # back to Home, offer grade

class OnboardingOrchestrator(QObject):
    def start(self):
        self._state = STATE_SCANNING
        self._start_background_scans()  # device scan + logger + speed test
        self._update_tour_bar()
        # Next → unlocks when scan_done fires

    def _on_scan_done(self, result):
        if self._state == STATE_SCANNING:
            self._state = STATE_DEVICES
            self._dashboard._nav_rail_go_to("Devices")
            self._update_tour_bar()
            self._tour_next_btn.setEnabled(True)

    def _advance(self):
        if self._state == STATE_DEVICES:
            self._state = STATE_LOGGER
            self._dashboard._nav_rail_go_to("Network Logger")
            self._start_logger()
            self._update_tour_bar()
            # Next → available after 2s (logger is already starting)
            QTimer.singleShot(2000, lambda: self._tour_next_btn.setEnabled(True))
        elif self._state == STATE_LOGGER:
            self._state = STATE_DONE
            self._dashboard._nav_rail_go_to("Home")
            self._update_tour_bar()
            # Next → replaced by "Done" + "Run Grade →"
```

### Tour Bar: Visual Design Specification

**Current tour bar is fine structurally but needs visual polish:**

```
┌──────────────────────────────────────────────────────────────────────────── [Next →]  [Skip] ─┐
│  Step 1 of 4  ·  Finding your devices...                14 found so far                        │
└────────────────────────────────────────────────────────────────────────────────────────────────┘
```

Specifications:
- Height: 48px (unchanged)
- Background: `ACCENT` with 10% opacity (`ACCENT + "1A"`) — subtle blue tint, not full blue
- Left border: 3px solid `ACCENT` — visual hook
- "Step N of 4" — `TEXT_SECONDARY` 11px
- The step title — `TEXT_PRIMARY` 13px **bold**
- Body text — `TEXT_SECONDARY` 12px
- `[Next →]` — filled `ACCENT` button, disabled (greyed) until step is ready
- `[Skip]` — text-only link, `TEXT_SECONDARY` — always enabled
- **Live counter** during scan: a small animated number next to the body text, ticking up as devices are found

### Remove the CoachMarkChain from onboarding

Coach marks (the spotlight bubbles) should NOT fire during onboarding. They add noise.

The rule: **CoachMarkChain fires only after `tour/v1_done = True`**, keyed to individual per-feature flags. During the main 4-step onboarding, no coach marks. Not one.

This is the source of the "random boxes popping up" problem. The current code fires the onboarding step spotlights AND has per-page `_maybe_show_coach_*` timers that can fire at the same time. They conflict. Solution: gate all `_maybe_show_coach_*` methods with `if not QSettings().value("tour/v1_done", False, bool): return`.

---

## Sprint J3 — Empty State Polish

**Files:** `ui/pages/inventory_page.py`, `ui/pages/overview_page.py`, `ui/pages/log_hub_page.py`  
**Effort:** S (2 hours)

### Fix J3-A: Devices page — hide KPI tiles when empty

In `ui/pages/inventory_page.py`, the four KPI tiles (TOTAL NODES, CRITICAL RISK, UNAUTHORISED, SCAN STATUS) should be hidden when `scan_status == "Idle"` and no devices exist.

Show them once data arrives. Showing `—  —  —  Idle` looks broken.

Also: the empty state text "Run a scan to discover devices on this network." inside the table area needs a **scan CTA button** (RULE-UX5):

```python
# RULE-UX5 compliant empty state for inventory:
empty_card = EmptyStateCard(
    icon="⬡",
    title="No devices found yet",
    body="Scan your network to discover every device — routers, phones, smart speakers, everything.",
    cta_label="Scan my network →",
)
empty_card.cta_clicked.connect(lambda: self.scan_requested.emit())
```

### Fix J3-B: Overview page — hide Security Scan below empty state

When Overview is in empty state (`no_data` stack page), the Security Scan section should not be visible. It currently shows below the empty state card which is extremely confusing — it looks like a separate form.

In `ui/pages/overview_page.py`, hide `self._security_scan_card` when in empty-state mode. Show it only after scan data arrives with `on_cycle_done()`.

Also: hide the "How is the grade calculated?" accordion when there is no grade. It's a distraction.

### Fix J3-C: Network Logger — live feedback when recording

When the logger is running, the KPI tiles should update within 60 seconds. But the tiles show `—` even with the logger running because the first ping hasn't been logged yet.

Add a **recording indicator** that fires immediately:

```
Logger started — pinging every 60s → netlog_20260604.csv
● Recording...  (small pulsing green dot using PulsingDot widget)
```

The pulsing dot (`ui/widgets/pulsing_dot.py`) already exists. Use it in the logger status bar when `self._is_running = True`.

Also: remove the "Log Analysis" section from the default view — move it behind the "Load Analysis →" button which already exists. The placeholder text "Load a log file to see automatic diagnostic findings here." just takes up space and looks like unfinished UI.

---

## Sprint J4 — Tour Bar Animation & Transitions

**Files:** `ui/tabs.py` (tour bar widgets), `ui/onboarding.py`  
**Effort:** S (1–2 hours)

This is the polish that turns "functional" into "smooth".

### Fix J4-A: Page transition animation

When the orchestrator calls `_nav_rail_go_to(label)`, the page stack currently snaps instantly (or crossfades in 160ms). For the onboarding, add a deliberate 400ms fade:

```python
def _onboarding_navigate(self, label: str):
    # Fade out current page
    anim_out = QPropertyAnimation(self._stack.currentWidget(), b"windowOpacity")
    anim_out.setDuration(200)
    anim_out.setStartValue(1.0)
    anim_out.setEndValue(0.0)
    anim_out.finished.connect(lambda: self._do_navigate_and_fade_in(label))
    anim_out.start()

def _do_navigate_and_fade_in(self, label: str):
    self._nav_rail_go_to(label)
    anim_in = QPropertyAnimation(self._stack.currentWidget(), b"windowOpacity")
    anim_in.setDuration(300)
    anim_in.setStartValue(0.0)
    anim_in.setEndValue(1.0)
    anim_in.start()
```

### Fix J4-B: Tour bar step transition

When advancing from step N to N+1, the tour bar body text should crossfade:

1. Fade current text out (150ms)
2. Update text  
3. Fade new text in (150ms)

This prevents the jarring "blink" when clicking Next →.

### Fix J4-C: Tour bar step progress dots

Replace the "Step N of 4" text with **4 dots** (like Apple's setup screen):

```
●●○○   Finding your devices...    14 found so far    [Next →]  [Skip]
```

Filled `ACCENT` dot = completed. Half-filled `ACCENT` dot = current. Empty `BG_HOVER` dot = future.

---

## Sprint J5 — "Since You Were Away" Home Page State

**Files:** `ui/pages/home_data_mixin.py`, `ui/widgets/home_session_widgets.py`  
**Effort:** S (1–2 hours)

After the onboarding is complete and the user has used the app for 24+ hours, the Home page should greet returning users with data — not the same Getting Started card.

### The returning user state (post-setup)

Once `setup/all_done = True` (all 6 Getting Started steps complete), the home page should look like this:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│  While you were away (last 14 hours):                                                           │
│  ● 347 pings logged · Average RTT: 24ms · 0 outages · 2 new devices                           │
│  ─────────────────────────────────────────────────────────────────────────────────────────────  │
│  New device: Unknown · 192.168.1.44 · Arrived 2h ago                              [Identify →] │
└─────────────────────────────────────────────────────────────────────────────────────────────────┘

  ● ARP Watch   ● Logger: 14h   ○ DHCP Watch   ○ Storm Detector

  [→ Scan Network]   [→ What's Wrong?]     Grade: B+  (last scan 14h ago)
```

This is the "Apple Weather" moment — open the app, immediately see what changed.

---

## Acceptance Criteria — The Full Definition of Done

Before any version bump, the following user journey must work end-to-end without any action being surprising or confusing:

### Clean install journey (delete `HKCU\Software\NetSentinel` first)

1. App opens. Splash screen appears briefly.
2. Home page shows: Getting Started card (step 1 active: "Run your first scan") + large Scan button. **Nothing else visible.**
3. Theme buttons are NOT visible anywhere on the home page.
4. User clicks Scan button. Onboarding bar appears at top of content:
   ```
   ●○○○   Finding your devices...   3 found so far   [Skip]
   ```
5. Live device count increments as scan runs. Next → is greyed out.
6. Scan completes. Next → becomes available. Bar says "14 devices found — see them here →"
7. User clicks Next →. App navigates to Devices page with a smooth 300ms fade.
8. Devices page shows the actual device table. ONE sentence in the bar: "These are your devices. Unknown ones may be guests or intruders."
9. No spotlight boxes pop up. No coach mark chains.
10. User clicks Next →. App navigates to Network Logger. Logger starts automatically.
11. Bar says: "Logger running. Come back tomorrow — you'll see any stability issues here."
12. Pulsing green dot next to "Recording..." in the logger status line.
13. User clicks Next →. App navigates back to Home.
14. Bar says: "You're set up. Run your network grade when ready." with two buttons: [Run Grade →] and [Done].
15. User clicks Done. Tour bar hides with a fade.
16. Home page reveals remaining sections (monitoring pills, what to do next) with a gentle fade-in.
17. Getting Started card updates: steps 1 and 2 now show ✓.

### No random boxes criterion
At no point during the journey above should a CoachMarkChain spotlight fire. Zero coach marks during first-run.

### Returning user journey (re-launch after 24h)
1. App opens. Home page shows "While you were away" banner if logger data exists.
2. Getting Started card shows which steps are complete.
3. No tour bar. No onboarding. Clean.

---

## What NOT to Do

- **Do not add more features to the onboarding** — the problem is complexity, not lack of content.
- **Do not make spotlights point at navigation menus** — pointing at the sidebar and saying "this is the nav" teaches nothing. Navigate there and show the actual content.
- **Do not fire coach marks and tour steps at the same time** — they will conflict. Pick one or the other for each context.
- **Do not show the Getting Started card to returning users who have completed setup** — replace it with the weekly summary card.
- **Do not animate for the sake of animating** — every animation must communicate something (this moved, this appeared, this is loading).

---

## Sprint Order & Timeline

| Sprint | Focus | Impact | Estimated Time |
|---|---|---|---|
| **J1** | Home page surgery — remove theme buttons, collapse empty sections, redesign Getting Started card | **Highest** — fixes first impression | 3–4 h |
| **J2** | Onboarding flow rewrite — value-first, no random boxes | **Highest** — fixes the core experience | 5–6 h |
| **J3** | Empty state polish — Devices CTA, Overview security scan, Logger live feedback | High — fixes "broken" feeling | 2 h |
| **J4** | Tour bar transitions — fade, dots, page transition animation | Medium — makes it feel smooth | 1–2 h |
| **J5** | Returning user state — "since you were away" banner | Medium — value for day-2+ users | 1–2 h |

**Total: approximately 12–16 hours to Apple-level first-run experience.**

---

## Files to Touch (complete list)

| File | Changes |
|---|---|
| `ui/pages/home_page.py` | Remove theme buttons, hide pre-scan sections, redesign hero |
| `ui/pages/home_data_mixin.py` | `_pre_scan_mode` logic, `on_scan_done` section reveal |
| `ui/widgets/home_session_widgets.py` | Getting Started card redesign — progress bar, active step highlight |
| `ui/onboarding.py` | Full rewrite — 4-state machine, value-first, no spotlight during onboarding |
| `ui/guided_tour.py` | Keep for backwards compat but do not trigger during onboarding |
| `ui/tabs.py` | Tour bar visual update (dots instead of "Step N of 4") |
| `ui/pages/inventory_page.py` | Hide KPI tiles when empty, add scan CTA button |
| `ui/pages/overview_page.py` | Hide security scan section when in empty state, hide grade accordion when no grade |
| `ui/pages/log_hub_page.py` | Add pulsing dot, move Log Analysis behind button |
| `ui/widgets/coach_mark.py` | Gate all coach mark chains on `tour/v1_done = True` |
| `ui/dashboard.py` | `_maybe_start_onboarding` → only `OnboardingOrchestrator`, remove WelcomeOverlay path |

## Files NOT to touch

- `modules/root_cause_correlator.py`
- `ui/nav/rail.py`, `ui/nav/builder.py`
- `ui/styles.py` — only additive if new colour constants needed
- `modules/metric_store.py`

---

*Plan created: 2026-06-04. Approved for implementation — start with J1.*
