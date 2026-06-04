# NetSentinel — World-Class Onboarding Plan v2
# Single format. Two layers. Zero waiting.

**Status:** Planning  
**Replaces:** UX-POLISH-ONBOARDING-PLAN.md H1 (GuidedTour) + H7 (CoachMarks) + WelcomeOverlay  
**Goal:** One seamless experience that teaches the UI, navigates to real data, and never makes the user wait.

---

## The Core Problem With the Current Design

Three competing onboarding UIs, two different formats, one modal:

```
WelcomeOverlay (modal slides)     ← FORMAT A: blocks everything
    ↓  user clicks "Scan my network"
    ↓  wait for scan to complete
GuidedTour (tour bar strips)      ← FORMAT B: different look/feel
    ↓  tour navigates pages
CoachMarkChain (spotlights)       ← FORMAT C: fires independently, any time
```

Users experience: a modal they have to dismiss, then a wait, then a bar, then random popups.

---

## The New Design: One Format, Two Layers

```
OnboardingOrchestrator
  Layer 1 — Navigation bar   : "Step N of 9 · [title] · [body]  [Next →]  [Skip]"
  Layer 2 — Spotlight chain  : CoachMarkChain highlights specific widgets per step
```

Both layers are active at the same time. The bar tells the user WHERE they are and WHY.
The spotlight tells them WHAT each element does. "Next →" enables only after the
spotlight chain for that step completes (or user clicks "Skip step").

No modal. No waiting. No format switch.

---

## What Fires Immediately on First Launch (before any user action)

```python
# In dashboard.py _show_welcome_overlay() replacement:
def _start_onboarding(self):
    self._start_full_scan()          # device scan
    self._start_speed_test()         # speed test
    self._start_network_logger()     # RTT recording
    # grade auto-chains after scan via existing _on_scan_done logic
    OnboardingOrchestrator(self).start()
```

All four run concurrently. By Step 2 the scan is done. By Step 3 the grade is ready.
By Step 4 the speed test result is in. The user never stares at a spinner.

---

## Complete Step Sequence (9 steps total)

### PHASE 1 — App Shell Orientation (Steps 1–4)
Stays on the default page. Teaches the UI chrome before navigating anywhere.

---

#### Step 1 of 9 — The Navigation Rail
**Tour bar:** "Get around · Click any section on the left rail to expand its pages."  
**Auto-navigate:** none (stay on current page)  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| `_nav_rail` (the 48 px left rail) | "9 sections, all your tools" | "Getting Started, Discover, Monitor, Reports, Analysis, Automation, Security, Education, Extend — all here." |
| First rail button (Getting Started icon) | "Click to expand" | "Each icon expands a flyout panel listing every page in that section." |
| `_nav_flyout` panel (after opening it) | "Pages inside a section" | "Click any item to navigate. Right-click to pin it to the top." |

---

#### Step 2 of 9 — Find Anything Instantly
**Tour bar:** "Command palette · Press Ctrl+K to find any page or action."  
**Auto-navigate:** none  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| Search icon at top of rail | "Or click here" | "The magnifier opens the command palette — fuzzy-search across all 60+ pages." |
| `_breadcrumb_lbl` | "Always know where you are" | "This strip shows your current section and page. Use it to orient yourself." |

---

#### Step 3 of 9 — Network Health at a Glance
**Tour bar:** "Your verdict · The status bar shows your live network health."  
**Auto-navigate:** none  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| Verdict/badge in header | "Live health indicator" | "Updates after every scan: Network Healthy, Issues Found, or No Data." |
| Scan button in header | "One-click scan" | "Runs a full device discovery and grades your network. Takes 60–90 seconds." |
| `_tip_bar` (the blue tips strip) | "Page-specific tips" | "Every page has a tips bar. Click the › arrow to see what the page does and what to look for." |

---

#### Step 4 of 9 — Your Home Page
**Tour bar:** "Home · This is your daily starting point."  
**Auto-navigate:** `Home`  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| Getting Started card | "Your setup checklist" | "Complete these 6 steps once and you'll never see this card again. It tracks your progress automatically." |
| Hero scan button | "Start here after any restart" | "Run a scan every time you want fresh data. Historical data persists in the database between sessions." |
| Monitoring pills strip | "Background monitors" | "ARP Watch, Logger, DHCP, Storm — these run silently. Green = active, grey = off." |
| WHAT TO DO NEXT section | "Actionable insights" | "After each scan, NetSentinel surfaces the 3–4 most important things to act on." |

---

### PHASE 2 — Feature Pages (Steps 5–9)
Navigates to real pages with live data already loading.

---

#### Step 5 of 9 — Speed Test
**Tour bar:** "Speed Test · Already running — every result is logged for ISP accountability."  
**Auto-navigate:** `Speed Test`  
**Auto-action:** `_speed_test_page._run_test()` (if not already running)  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| Speed gauge (right panel) | "Live gauge" | "Shows download speed in real time as the test runs. The needle moves." |
| Server list (left panel) | "Server selection" | "Auto-selects the closest server. You can pick manually for consistent benchmarks." |
| TEST HISTORY table | "Your speed log" | "Every test is saved. Run weekly to track ISP throttling, time-of-day patterns, and plan compliance." |
| Engine badge ("Engine: Ookla CLI ✓") | "Three-tier engine" | "Uses Ookla CLI if installed, then speedtest-cli, then pure-Python. All produce the same data format." |

---

#### Step 6 of 9 — Network Grade
**Tour bar:** "Network Grade · Your A–F score across 8 security and stability dimensions."  
**Auto-navigate:** `Network Grade`  
**Auto-action:** emit `scan_requested` on grade page (triggers grade computation)  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| Grade ring (the A–F circle) | "Your overall grade" | "Click the ring to see the breakdown — which of the 8 dimensions is dragging the score down." |
| Grade breakdown rows | "8 dimensions" | "Device risk, DNS stability, uptime, cert health, CVE exposure, rogue detection, speed, and latency." |
| "How is the grade calculated?" link | "Full methodology" | "Explains the weighting formula. Useful for ISP accountability reports — export as PDF." |
| Findings section | "What to fix" | "Each finding links directly to the page where you fix it. No digging required." |

---

#### Step 7 of 9 — Network Logger
**Tour bar:** "Network Logger · Already recording every 30 seconds — leave this running."  
**Auto-navigate:** `Network Logger`  
**Auto-action:** `_log_hub_page.show_network_log()` (enable RTT if not on)  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| Source toggles (Ping RTT, DNS, etc.) | "What gets recorded" | "Toggle each source on or off. Ping RTT is the most valuable — it catches micro-outages your ISP won't admit to." |
| "Auto-start on launch" checkbox | "Enable this now" | "Starts recording the moment the app opens. You never have to remember to turn it on." |
| Live log table (TIMESTAMP / RTT cols) | "Live pings" | "Every row is one ping. Jitter = RTT variance. DNS = name resolution time. ARP = spoofing event." |
| DETECTED OUTAGES table | "Outage record" | "Consecutive failures are logged as outages with start time and duration. Exportable as evidence." |
| "Load Analysis →" button | "Diagnostic engine" | "Paste in any log file and get automatic findings: worst-hour, outage frequency, P95 latency." |

---

#### Step 8 of 9 — Hardware Integration
**Tour bar:** "Hardware · Connect your router or modem to unlock real device names and signal data."  
**Auto-navigate:** `Hardware`  
**Spotlight sequence (adapts based on detection state):**

| Target widget | Title | Body |
|---|---|---|
| Detected device banner (if shown) | "Detected nearby" | "NetSentinel found your [device] on the network. Click Add to connect it — takes 30 seconds." |
| "Add" button on detected card | "Connect it now" | "Enter your device's web UI credentials once. They're stored in the OS keychain, never in a file." |
| Hub card (after plugin added) | "What you get" | "Real hostnames in the Devices page, signal strength in Speed Test, mesh topology in Network Map." |
| Community Browse tab | "Plugin library" | "Browse plugins for other hardware — UPS devices, switches, access points, cameras." |

*If no hardware detected: spotlight points to "Add a hardware device" section with copy explaining the value.*

---

#### Step 9 of 9 — Overview
**Tour bar:** "Overview · Your home base — all monitors and your grade in one place."  
**Auto-navigate:** `Overview`  
**Spotlight sequence:**

| Target widget | Title | Body |
|---|---|---|
| Tile grid | "Your dashboard" | "Each tile is a live monitor. Drag to reorder. Click Edit Layout to add or remove tiles." |
| Grade tile | "Grade always visible" | "Updates after every scan. Hover for the breakdown. Click to go to the Network Grade page." |
| "What's Wrong?" button | "One-click diagnosis" | "Pick a symptom, get targeted findings in 30 seconds. No need to know what ARP or STP mean." |
| "Share Card →" button | "ISP accountability" | "Generates a shareable PNG with your grade, ISP name, and top findings. Send it to your provider." |

**On Finish:** `tour/v1_done = True` → tour bar hides → coach marks now eligible.

---

## Phase 3 — Post-Tour Coach Marks (fire only after tour/v1_done = True)

These are contextual, per-page, one-time hints for features not covered in the main tour.
Each fires on the FIRST visit to that page AFTER the tour is complete.

| Page | Trigger | Title | Body |
|---|---|---|---|
| Devices | First device table row visible | "Right-click for actions" | "Right-click any device to label it, check its ports, or add it to your watchlist." |
| What's Wrong? | First visit, no results | "Describe your symptom" | "Pick the closest symptom. Targeted checks — not a full scan. 30 seconds." |
| Network Logger | First visit after tour | "Choose what to log" | "Toggle Network RTT to start logging ping latency. Leave it on for 24 hours for the best insights." |
| Home (recurring mode) | After 5th scan | "Your monitors" | "These pills show what's running in the background. Click any grey pill to enable that monitor." |
| Network Grade | After first grade result | "Click the grade ring" | "The ring is interactive — click it to see the 8-dimension breakdown and what's dragging your score." |

---

## What Gets Removed / Superseded

| Component | Action |
|---|---|
| `WelcomeOverlay` (4-slide modal) | **Deleted from launch flow.** Class kept for import compat. `should_show_first_run()` returns False always. |
| `GuidedTour` class | **Superseded.** Kept in codebase for test compat. `OnboardingOrchestrator` replaces it. |
| Individual `_maybe_show_coach_*` per-page timers | **Kept but gated:** only fire after `tour/v1_done = True` (already done). |
| `_scan_from_home` flag logic | **Simplified:** scans start at app launch, not triggered by user action. |

---

## New Files

| File | Purpose |
|---|---|
| `ui/onboarding.py` | `OnboardingOrchestrator` — drives the full 9-step sequence |
| `tests/test_onboarding.py` | Regression tests: step count, nav labels, spotlight target paths, tour/v1_done set on finish |

---

## Data Structures

```python
@dataclass
class SpotlightTarget:
    widget_attr: str       # attribute path on dashboard, e.g. "_nav_rail"
                           # or page-relative: "_speed_test_page._btn_run"
    title: str
    body: str
    button_label: str = "Got it"

@dataclass
class OnboardingStep:
    step_num: int          # 1–9
    nav_label: str | None  # page to navigate to; None = stay on current page
    tour_title: str        # shown in the tour bar left label
    tour_body: str         # shown in the tour bar description
    spotlights: list[SpotlightTarget]
    auto_action: str | None  # method name to call on dashboard/page, e.g. "_run_test"
```

---

## Orchestrator Flow

```
OnboardingOrchestrator.start()
  → _fire_background_scans()      # device scan + speed test + logger + grade
  → _step = 0
  → _advance()

_advance():
  step = STEPS[_step]
  if step.nav_label:
      _dashboard._nav_rail_go_to(step.nav_label)
  _update_tour_bar(step)
  if step.auto_action:
      _run_auto_action(step.auto_action)
  if step.spotlights:
      _run_spotlight_chain(step.spotlights, on_done=_enable_next_button)
  else:
      _enable_next_button()

_enable_next_button():
  # Next → becomes clickable only after spotlights complete
  _tour_next_btn.setEnabled(True)

user clicks Next →:
  _step += 1
  if _step >= len(STEPS):
      _finish()
  else:
      _tour_next_btn.setEnabled(False)   # disable until next spotlight chain done
      _advance()

_finish():
  QSettings.setValue("tour/v1_done", True)
  _tour_bar.setVisible(False)
  # coach marks now eligible on next page visit
```

---

## Tour Bar Visual Design

```
┌─────────────────────────────────────────────────────────── [Next →]  [Skip tour] ─┐
│  Step 5 of 9  ·  Speed Test  ·  Already running — every result logged for ISP     │
│               accountability. Build months of data before disputing a bill.        │
└────────────────────────────────────────────────────────────────────────────────────┘
```

- Height: 48 px (existing `_tour_bar`)
- `Next →` is **disabled** (greyed) while spotlight chain runs
- `Next →` becomes **enabled** when spotlight chain finishes (or user dismisses last spotlight)
- `Skip tour` always enabled — skips entire tour, sets `tour/v1_done = True`

---

## Timing Reality Check

| Background scan | Typical duration | Done by step... |
|---|---|---|
| Device scan | 15–30 s | Step 4 (Home) |
| Network Grade | 30–60 s (after scan) | Step 6 (Grade) |
| Speed Test | 30–90 s | Step 5 (Speed Test) — live gauge shown |
| Network Logger | immediate | Step 7 |

The spotlight chains for steps 1–4 take ~45–90 seconds to click through.
By the time the user reaches Step 5, the device scan and grade are done.
Speed test shows a live gauge even while running — this is better than a spinner.

---

## Implementation Order (sprints)

| Sprint | Scope | Files |
|---|---|---|
| I1 | `OnboardingOrchestrator` skeleton + step data structures + tour bar wiring | `ui/onboarding.py`, `tests/test_onboarding.py` |
| I2 | Background scan auto-start + disable WelcomeOverlay | `ui/dashboard.py`, `ui/first_run_dialog.py` |
| I3 | Phase 1 spotlight targets (steps 1–4, app shell) — widget path resolution | `ui/onboarding.py` |
| I4 | Phase 2 spotlight targets (steps 5–9, feature pages) + auto-actions | `ui/onboarding.py` |
| I5 | Next → gating (disable until spotlight chain done) + Skip tour wiring | `ui/onboarding.py`, `ui/tabs.py` |
| I6 | Tests + regression guards (RULE-T5, RULE-T6) + APM rules update | `tests/test_onboarding.py` |

---

## APM Rules Triggered

- **RULE-T5**: All step nav labels must have an integration test asserting they exist in `_nav_label_to_widget`
- **RULE-T6**: Walk the full 9-step flow in the live app before marking done. Document: "Verified in live app: [observation]"

---

*Plan created: 2026-06-04.*  
*Sprint H11 implementation started 2026-06-04: `ui/onboarding.py` and `tests/test_onboarding.py` rewritten with value-first 9-step sequence. Step content and spotlight widget targets remain for visual refinement in the next session (see `docs/ONBOARDING-VISUAL-FIX-PLAN-V3.md` for remaining work: J1 home page surgery, J3 empty state polish, J4 tour bar animations).*
