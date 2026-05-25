# NetSentinel — UX Product Backlog V6

## Product Owner Statement

V5 verified and polished the flows built across V1–V4. V6 goes one level deeper: making
NetSentinel feel premium, calm, and delightful for home network enthusiasts — people who
love watching their network like a beautiful live dashboard.

Audience: Home users, hobbyists, students (not enterprise).
Design north star: Apple-level attention to detail + tinkerer-friendly soul.

Non-negotiables:
- No clutter
- Respect "Reduce Motion" OS setting
- Animations short, subtle, fast
- Must stay maintainable in Qt/Pythondo all 

---

## Section 1 — Micro-Animations

Goal: Identify the handful of moments where motion earns its keep by communicating state
change, not just looking nice.

### ANIM-1 — Device Online/Offline Pulse

**Description**: When a device transitions online → a single soft ripple expands outward
from its geo-map pin or discovery-table row indicator dot. Offline → the dot fades to grey
with a gentle opacity drop. No looping.

**Duration**: 400 ms
**Easing**: `QEasingCurve.OutCubic`

**Justification**: The most meaningful moment in the whole app — a device appearing or
disappearing. Motion confirms it's real and anchors attention to the right row without
requiring a color scan.

**Files**: `ui/pages/discover_page.py`, `ui/widgets/` (new `PulsingDot` widget)

---

### ANIM-2 — Bandwidth Sparkline Live Update

**Description**: When a new data point arrives on the bandwidth graph, the rightmost
segment slides in from the right edge while old points shift left. Not a full redraw —
just the leading edge.

**Duration**: 200 ms
**Easing**: `QEasingCurve.Linear` (matches data cadence; easing would feel dishonest here)

**Justification**: Without motion, high-throughput moments are invisible unless the user is
watching. The slide-in makes spikes feel like events rather than column value changes.

**Files**: bandwidth graph widget (painter-level change)

---

### ANIM-3 — Alert Badge Increment

**Description**: When the alert count on the nav rail increments, the badge does a quick
scale-up (1.0 → 1.2 → 1.0) — a single "thump." No animation on decrement.

**Duration**: 250 ms
**Easing**: `QEasingCurve.OutBack` (slight overshoot gives it physical weight)

**Justification**: The nav rail is peripheral; this creates a small but unmissable gravity
pull toward unread alerts without a notification sound.

**Files**: `ui/dashboard.py` (nav rail badge widget)

---

### ANIM-4 — Log Hub New-Row Arrival

**Description**: The newest row in the Log Hub table starts at 60% opacity and fades to
100% over 300 ms. Only the most recent row animates; older ones don't re-animate on scroll.
Skip if log velocity > 5 rows/sec to prevent flicker.

**Duration**: 300 ms
**Easing**: `QEasingCurve.OutQuad`

**Justification**: At normal cadence it separates "just happened" from "already processed."
At high velocity the animation is suppressed automatically.

**Files**: `ui/pages/log_hub_page.py`

---

### ANIM-5 — Speed Test Count-Up

**Description**: The speed test result value (e.g. "247 Mbps") counts up from 0 using a
number tween, synchronized with the circular progress arc sweeping to its final position.

**Duration**: 600 ms
**Easing**: `QEasingCurve.OutExpo` (fast start, slow finish — lands with confidence)

**Justification**: Speed test results are inherently satisfying to reveal. The count-up
makes a 247 Mbps result feel earned, not just printed. This is the one moment in the app
that benefits from a slightly longer animation.

**Files**: `ui/pages/speed_test_page.py`

---

### Skipped animations — with reasons

| Animation | Why skipped |
|---|---|
| Page/nav transition slide | NetSentinel is a utility. Page switches are purposeful; sliding pages make users feel like they're waiting for content that's already rendered. |
| Settings panel open/close | Settings are modal utility. Animation here is pure noise. |
| Geo-map zoom animation | The geo canvas already handles this; layering another animation system on top risks jitter and fights the painter loop. |
| Protocol diagram build-up on load | The protocol visualizer is already animated during operation. An intro animation adds latency to a feature users open for information, not spectacle. |

---

## Section 2 — General Polish Recommendations

Goal: Fix the details that make the difference between "good app" and "app I trust with
my network."

### POLISH-1 — Semantic Color System (single source of truth)

**Problem**: Device health, alert severity, and signal strength all use slightly different
red/yellow/green values sourced from different places.

**Fix**: Consolidate into one `ui/theme.py` token dict:
`COLOR_GOOD`, `COLOR_WARN`, `COLOR_CRITICAL`, `COLOR_OFFLINE`, `COLOR_NEUTRAL`.
Wire every widget through it. Makes dark-mode and high-contrast support a one-file change
later.

**Why it matters**: Users unconsciously learn color = meaning. Inconsistent reds erode
trust in alerts.

**Files**: new `ui/theme.py`; audit all widgets for hardcoded color strings

---

### POLISH-2 — Table Row Density Toggle

**Problem**: No way for users to control information density — one size fits nobody
perfectly.

**Fix**: Add a compact/comfortable toggle (⊟/⊞ icon in table toolbars). Comfortable = 36px
rows with subtle dividers. Compact = 24px rows, no dividers, monospace values. Store
preference in QSettings per-table.

**Why it matters**: A student on a 13" laptop needs compact. A hobbyist on a 27" monitor
loves breathing room.

**Files**: shared table toolbar widget; each data table page

---

### POLISH-3 — Empty States: Verify and Extend CTA Wiring

**Note**: V5 POLISH-10 already added context sentences to the 6 primary empty states.
V2 EMPTY-1 added the base empty state pattern. This item is scoped to:
1. Verify POLISH-10 context sentences are present in all 6 locations
2. Confirm CTA buttons are wired to actual actions (not just rendered)
3. Add directed empty states to any pages still showing a blank table

**Pattern**: SVG icon + one-line label + context sentence + single action CTA.

**Files**: `ui/dashboard.py`, respective page files where `_empty_state_widget()` is built

---

### POLISH-4 — Tooltip Quality Pass

**Problem**: Most tooltips show raw property names or nothing.

**Fix**: Replace with bold label + one plain-English sentence. For technical values (RSRP,
SNR, TTL), add a parenthetical like "(higher is better)" or "(normal: < 5ms)". Cap at
200 chars. Set `setToolTipDuration(4000)`.

Start with: discovery page + log hub + modem page (highest technical density).

**Why it matters**: Highest-leverage improvement for new users. Teaches the app without
a manual. ~1 hour per screen.

**Files**: `ui/pages/discover_page.py`, `ui/pages/log_hub_page.py`, `ui/pages/modem_page.py`

---

### POLISH-5 — First-Run Coach Marks

**Note**: V5 AUDIT-1 verified the first-run flow works end-to-end. This item adds
discoverability UI on top of that verified flow.

**Problem**: New users stare at an empty map and close the app. The first-run flow fires
but doesn't explain what they're looking at.

**Fix**: Three overlapping coach marks (semi-transparent highlight + callout bubble),
firing once on first launch, keyed to `QSettings("onboarding_v6_done")`.
- Screen 1: geo map — "Your network, on a map."
- Screen 2: nav rail discovery item
- Screen 3: alert bell

Each has X and "Got it →" button. Not a wizard — dismissible at any point.

**Files**: new `ui/widgets/coach_mark.py`; `ui/dashboard.py` (first-launch trigger)

---

### POLISH-6 — Value-Density Header Bar

**Problem**: Page headers use 60–80px of vertical real estate on every screen for a title
and whitespace.

**Fix**: Replace with a slim 40px bar: page title left-aligned in font-weight 600, and
2–3 live summary chips right-aligned (e.g. "12 devices · 2 alerts · 94 Mbps up"). Chips
update in place. 1px bottom separator in surface color, no border box.

**Why it matters**: Makes every page feel information-rich the moment it loads.

**Files**: shared header bar widget; each page that currently has a large title header

---

## Section 3 — Prioritization Table

Goal: Give the team a clear sprint path that delivers visible wins fast.

| Item | Impact | Effort | Status | Notes |
|---|---|---|---|---|
| POLISH-1 — Semantic color system | High | Low | ✅ v1.9.31 | `ui/theme.py` — `status_color()` + `_reduce_motion()` backed by `ui/styles` |
| POLISH-3 — Empty states verify+extend | High | Low | ✅ v1.9.31 | All 6 V5 surfaces verified; log hub empty state added |
| POLISH-4 — Tooltip quality pass | High | Low | ✅ v1.9.31 | inventory column headers + filter checkboxes; log hub source chips |
| ANIM-1 — Device pulse | High | Med | ✅ v1.9.31 | `PulsingDot` widget; pulses on new JOINED/UP/RECOVERED in inventory |
| ANIM-4 — Log Hub row fade | Low | Low | ✅ v1.9.31 | 60→100% over 300 ms; skipped at >5 rows/sec or reduce-motion |
| POLISH-6 — Value-density header | Med | Low | ✅ v1.9.34 | `PageHeaderBar` widget; 17 pages updated; 40px bar replaces title+subtitle |
| ANIM-5 — Speed test count-up | Med | Low | ✅ v1.9.34 | `_start_tile_count_up`; 600 ms OutExpo; skips at reduce-motion |
| POLISH-5 — First-run coach marks | High | Med | ✅ v1.9.34 | `CoachMarkChain`; 3 marks; keyed to `onboarding_v6_done` |
| ANIM-3 — Alert badge thump | Low | Low | ✅ v1.9.34 | `_RailButton.badgeScale` pyqtProperty; 250 ms OutBack; on count increase only |
| POLISH-2 — Table density toggle | Med | Med | — | Power-user feature; correct but not urgent |
| ANIM-2 — Bandwidth sparkline slide | Med | Med | — | Requires custom painter change |

### Sprint 1 — shipped v1.9.31

1. ✅ POLISH-1 — Semantic color system
2. ✅ POLISH-3 — Empty states verify+extend
3. ✅ POLISH-4 — Tooltip pass (inventory + log hub)
4. ✅ ANIM-1 — Device pulse
5. ✅ ANIM-4 — Log Hub row fade (added to sprint)

### Sprint 2 — shipped v1.9.34

1. ✅ POLISH-6 — Value-density header bar — `PageHeaderBar` widget; 17 pages
2. ✅ ANIM-5 — Speed test count-up — `QVariantAnimation` on download + upload tiles
3. ✅ POLISH-5 — First-run coach marks — `CoachMarkChain`; 3 overlays
4. ✅ ANIM-3 — Alert badge thump — `_RailButton.badgeScale` on count increase

### Sprint 3 — next up

1. POLISH-2 — Table density toggle — compact/comfortable toggle per table, persisted in QSettings
2. ANIM-2 — Bandwidth sparkline slide — custom painter change on bandwidth graph widget

---

## Section 4 — Implementation Guidance (Top 3 Priorities)

Goal: Give the developer working code patterns they can drop in without architecture
decisions.

---

### POLISH-1 — Semantic Color System

Create `ui/theme.py` as the single color authority:

```python
# ui/theme.py
from PyQt6.QtGui import QColor

COLORS = {
    "good":     QColor("#34C759"),   # Apple system green
    "warn":     QColor("#FF9F0A"),   # Apple system orange
    "critical": QColor("#FF3B30"),   # Apple system red
    "offline":  QColor("#8E8E93"),   # Apple system grey
    "neutral":  QColor("#636366"),
    "surface":  QColor("#1C1C1E"),
    "surface2": QColor("#2C2C2E"),
    "separator":QColor("#38383A"),
}

def status_color(status: str) -> QColor:
    """Map device/alert status string → semantic QColor."""
    return COLORS.get(status.lower(), COLORS["neutral"])
```

Usage in any widget:

```python
from ui.theme import status_color, COLORS

indicator.setStyleSheet(
    f"background: {status_color(device.status).name()}; border-radius: 5px;"
)
```

For dark/light mode later: swap the COLORS dict at startup based on
`QApplication.palette().window().color().lightness()` — no other code changes needed.

---

### ANIM-1 — Device Online Pulse

Add a `PulsingDot` widget to `ui/widgets/pulsing_dot.py`:

```python
# ui/widgets/pulsing_dot.py
from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtWidgets import QLabel

class PulsingDot(QLabel):
    """Status dot that plays a single pulse on state change."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._opacity = 1.0
        self._current_color = None
        self._anim = QPropertyAnimation(self, b"opacity", self)
        self._anim.setDuration(400)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        self._opacity = value
        if self._current_color:
            color = self._current_color.name()
            self.setStyleSheet(
                f"background:{color}; border-radius:5px; opacity:{value:.2f};"
            )

    def set_status(self, status: str, animate: bool = True):
        from ui.theme import status_color
        self._current_color = status_color(status)
        self.setStyleSheet(
            f"background:{self._current_color.name()}; border-radius:5px;"
        )
        if animate and not _reduce_motion():
            self._anim.stop()
            self._anim.setStartValue(1.4)
            self._anim.setEndValue(1.0)
            self._anim.start()


def _reduce_motion() -> bool:
    from PyQt6.QtWidgets import QApplication
    hints = QApplication.styleHints()
    if hasattr(hints, "isReduceMotionPreferred"):
        return hints.isReduceMotionPreferred()
    from PyQt6.QtCore import QSettings
    return QSettings().value("accessibility/reduce_motion", False, type=bool)
```

---

### POLISH-3 — Empty State Widget

One reusable component for any page that shows a blank table:

```python
# ui/widgets/empty_state.py
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon

class EmptyState(QWidget):
    action_clicked = pyqtSignal()

    def __init__(self, icon_path: str, message: str, context: str = "",
                 cta: str | None = None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(QIcon(icon_path).pixmap(48, 48))
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        msg_lbl = QLabel(message)
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 600;")

        layout.addWidget(icon_lbl)
        layout.addWidget(msg_lbl)

        if context:
            ctx_lbl = QLabel(context)
            ctx_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ctx_lbl.setStyleSheet("color: #8E8E93; font-size: 13px;")
            layout.addWidget(ctx_lbl)

        if cta:
            btn = QPushButton(cta)
            btn.setStyleSheet(
                "QPushButton { background: transparent; color: #0A84FF; "
                "border: none; font-size: 13px; } "
                "QPushButton:hover { text-decoration: underline; }"
            )
            btn.clicked.connect(self.action_clicked)
            layout.addWidget(btn)
```

Usage (stacked behind the table, shown when model is empty):

```python
self._empty = EmptyState(
    "assets/icons/devices.svg",
    "No devices found yet.",
    "Your network devices will appear here after a scan.",
    "Start a scan →",
)
self._empty.action_clicked.connect(self._on_start_scan)
self._stack.addWidget(self._empty)
self._stack.addWidget(self._table)

# Switch based on data:
self._stack.setCurrentWidget(
    self._empty if self._model.rowCount() == 0 else self._table
)
```

---

## Architecture notes for this session

- Start with POLISH-1 (semantic color system) — it unblocks all other visual work.
- POLISH-3 empty state audit: check all 6 surfaces from V5 POLISH-10 before adding new ones.
- ANIM-1 through ANIM-5: all must check `_reduce_motion()` before starting any animation.
- No new pages or nav entries this session — V6 is purely feel, not features.
- If POLISH-5 (coach marks) scope feels large, descope to a single coach mark on the geo
  map only and carry the rest to V7.
