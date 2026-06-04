# Apple-Like Onboarding Plan — NetSentinel v1.9.86

## Current State (verified via screenshots, 2026-06-04)

App launches directly to the Overview dashboard with full complexity immediately visible.
A background scan starts automatically without user consent.
A thin blue step-counter banner appears at the top ("Step 1 of 9 — Scanning your network").
A small tooltip in the top-right says "One-click scan" with a "Got it" button.
After dismissing the tooltip a "Next →" button appears to advance through 9 coach marks.
A "Scan Complete" bottom sheet pops up showing device counts.

None of this is Apple-like. Apple never auto-starts anything. Apple never shows full product
complexity on first launch. Apple shows one focused screen at a time.

---

## Core Principle

Show one thing, then the next thing. Every screen has exactly one question or one action.
The full app is hidden until the user has been through a focused welcome sequence.
Nothing happens without consent.

---

## What to Delete / Replace

| Current element | Problem | Action |
|---|---|---|
| Auto-scan on first launch | Scanning without consent feels invasive | Remove — scan only fires when user clicks a button |
| Thin blue tour banner at top | Cluttered, corporate, breaks the UI | Delete entirely |
| "Step 1 of 9" text counter | 9 steps is too many; text counter is ugly | Replace with dot progress indicator |
| Coach mark tooltips as onboarding | Tiny, easy to miss, not immersive | Remove from first-run; keep as power-user hints post-onboarding |
| "Skip tour" link | Fine to keep but must not be prominent | Keep as small muted text link |

---

## The New Flow — 6 Screens

### Screen 0 — Welcome (full-screen overlay, BLOCKS the dashboard)

```
┌─────────────────────────────────────┐
│                                     │
│          [NetSentinel icon]         │
│                                     │
│        Welcome to NetSentinel       │  ← 28px semibold
│                                     │
│  Your network, visible and secured  │  ← 14px muted
│                                     │
│                                     │
│      [  Get Started  ]              │  ← accent button, 48px tall
│                                     │
│          Skip setup →               │  ← muted text link
│                                     │
└─────────────────────────────────────┘
```

- Full-screen white overlay sitting above the entire window
- App behind it is fully rendered but invisible — no flicker when overlay dismisses
- No nav rail, no breadcrumbs, no tiles — just this

---

### Screen 1 — Permission to Scan

```
┌─────────────────────────────────────┐
│  ○  ●  ○  ○  ○  ○           [Skip] │  ← dot progress, 6 dots
│                                     │
│           [Scan animation]          │  ← animated concentric rings
│                                     │
│    Let's see what's on your         │
│    network                          │  ← 22px
│                                     │
│  NetSentinel will scan your local   │
│  network to find connected devices. │  ← 13px muted, 2 lines max
│  Nothing leaves your device.        │
│                                     │
│      [  Scan my network  ]          │  ← primary button
│                                     │
└─────────────────────────────────────┘
```

- User must click to start scan — no auto-start
- Animated concentric rings graphic, not the full dashboard

---

### Screen 2 — Scanning in Progress

```
┌─────────────────────────────────────┐
│  ○  ○  ●  ○  ○  ○           [Skip] │
│                                     │
│      [Animated radar sweep]         │  ← rotating arc graphic
│                                     │
│       Scanning your network…        │  ← 22px
│                                     │
│   Checking 192.168.1.0/24           │  ← live status text, 12px muted
│                                     │
│  ████████████░░░░░░░░░  47%         │  ← thin progress bar
│                                     │
└─────────────────────────────────────┘
```

- Full-screen, no progress to next step until scan completes
- Live status line updates from scan worker signals

---

### Screen 3 — Results Reveal ("Wow" moment)

```
┌─────────────────────────────────────┐
│  ○  ○  ○  ●  ○  ○           [Skip] │
│                                     │
│               19                   │  ← 72px bold accent, count-up animation
│          devices found              │  ← 16px muted
│                                     │
│  ┌──────────┐  ┌──────────────────┐ │
│  │ 0 Alerts │  │ Grade: B         │ │  ← two summary cards
│  └──────────┘  └──────────────────┘ │
│                                     │
│    "Your network looks healthy.     │
│     No high-risk devices detected." │  ← plain-English verdict
│                                     │
│      [  See my devices  ]           │
│                                     │
└─────────────────────────────────────┘
```

- Big animated number count-up for device count
- Two KPI cards: alerts and grade
- One plain-English sentence from root cause correlator
- "See my devices" advances to Screen 4

---

### Screen 4 — Devices Page Spotlight

```
┌─────────────────────────────────────┐
│  ○  ○  ○  ○  ●  ○           [Skip] │
│                                     │
│  [Miniature device table preview]   │  ← scaled-down live widget preview
│                                     │
│    Every device, in plain English   │  ← 18px
│                                     │
│  Unknown devices are highlighted.   │  ← 13px muted
│  Right-click any row for actions.   │
│                                     │
│      [  Next  →  ]                  │
│                                     │
└─────────────────────────────────────┘
```

---

### Screen 5 — Logger Always Running

```
┌─────────────────────────────────────┐
│  ○  ○  ○  ○  ○  ●           [Skip] │
│                                     │
│  [Tiny RTT sparkline animation]     │
│                                     │
│  Your connection is being watched   │  ← 18px
│                                     │
│  RTT and DNS are logged every 30s.  │
│  Leave it running overnight to      │
│  build outage evidence.             │
│                                     │
│      [  Done — Start exploring  ]   │  ← green button
│                                     │
└─────────────────────────────────────┘
```

---

### Screen 6 — Done (brief, then auto-dismiss)

```
┌─────────────────────────────────────┐
│                                     │
│              ✓                      │  ← large green checkmark, animates in
│                                     │
│          You're all set             │  ← 22px
│                                     │
│  (overlay fades out after 1.5s,     │
│   revealing the full dashboard)     │
│                                     │
└─────────────────────────────────────┘
```

---

## Files to Create

| File | Purpose |
|---|---|
| `ui/widgets/onboarding_overlay.py` | Full-screen overlay widget with all 6 screens as QStackedWidget pages |
| `ui/widgets/scan_animation.py` | Animated QPainter concentric rings / radar sweep graphic |

---

## Files to Modify

| File | Change |
|---|---|
| `ui/onboarding.py` | Strip to a thin shim that creates and shows `OnboardingOverlay`; delete `OnboardingOrchestrator` and all step/spotlight machinery |
| `ui/dashboard.py` | Remove `_tour_bar` (blue banner); remove `_tour_next_btn`, `_tour_skip_btn`, `_tour_step_lbl`, `_tour_body_lbl` from the header build; keep `_maybe_start_onboarding()` |
| `ui/header.py` | Remove tour bar from the header layout |

## Files to Leave Alone

- `ui/widgets/coach_mark.py` — still used post-onboarding for power-user hints
- `ui/widgets/home_session_widgets.py` — `GettingStartedCard` stays on the Home page
- All scan/worker machinery — the overlay triggers `_start_full_scan()` via signal

---

## Integration Points

```
app.py
  → _maybe_start_onboarding()
      → creates OnboardingOverlay(dashboard)
          → overlay.show() sits above everything
          → Screen 1: user clicks "Scan my network"
              → emits scan_requested signal
              → dashboard._start_full_scan() fires
              → overlay listens to scan worker progress signals
          → Screen 2: progress updates from scan_worker
          → Screen 3: uses _m1_result when available
          → Screen 5: triggers network logger start
          → Screen 6: marks done, fades out
```

QSettings key: `ui/onboarding_v2_done` (reuses existing key so existing users are not reshown)

---

## Sprint Breakdown

### Sprint I1 — Core overlay scaffold + Welcome + Permission screens
- [ ] Create `ui/widgets/onboarding_overlay.py` with `QStackedWidget`
- [ ] Screen 0 (Welcome) and Screen 1 (Permission) working
- [ ] Remove auto-scan from onboarding orchestrator
- [ ] Remove blue tour banner from dashboard header
- [ ] App launches cleanly, overlay shows, clicking "Scan my network" fires scan
- [ ] All existing tests pass

### Sprint I2 — Scanning progress + Results reveal
- [ ] Screen 2: live progress bar wired to scan worker `progress` signal
- [ ] Screen 3: animated count-up, KPI summary cards, plain-English verdict
- [ ] `scan_animation.py` QPainter widget (concentric rings for Screen 1, radar for Screen 2)

### Sprint I3 — Feature spotlight screens + Done animation
- [ ] Screens 4 and 5 (miniature previews, not full widgets)
- [ ] Screen 6 (done checkmark + fade-out reveal animation)
- [ ] Logger auto-start on Screen 5 button click
- [ ] Mark `ui/onboarding_v2_done` in QSettings on completion
- [ ] Full flow tested via screenshot automation

### Sprint I4 — Polish + verification
- [ ] Dot progress indicator (6 dots, current = filled accent, others = muted)
- [ ] Cross-fade transitions between screens (150ms)
- [ ] "Skip setup" goes directly to Screen 6 (still shows done animation)
- [ ] Keyboard: Enter advances, Esc = Skip
- [ ] Screenshot each screen and confirm against this spec

---

## Verification Checklist (per RULE-T6)

Before any sprint is marked complete:
1. Clear QSettings: `Remove-Item "HKCU:\Software\NetSentinel" -Recurse -Force`
2. Launch app and screenshot each of the 6 screens
3. Confirm NO auto-scan fires before user clicks "Scan my network"
4. Confirm blue tour banner is GONE from the header
5. Confirm coach marks do NOT fire during first-run
6. Confirm overlay fades out cleanly and full dashboard is revealed
7. Confirm second launch (with QSettings set) skips the overlay entirely
