#!/usr/bin/env python3
"""
tools/monkey_mouse_test.py - Raw-input (real mouse) chaos harness for NetSentinel
==================================================================================
`tools/monkey_test.py` drives the UIA control tree: every action targets a named
element (Button, Edit, ComboBox, ...) via pywinauto's `click_input()`, which
teleports the OS cursor onto that element and clicks it. That is fast and finds
real bugs, but it structurally cannot exercise:

  * A click that goes through the OS hit-test at the control's on-screen
    location. UIA `click_input()` addresses the element by its accessibility
    identity, so a transparent overlay sitting on top of a button, a
    wrong-widget-on-top z-order bug, or a control that only reacts to a real
    cursor are all invisible to it. This tool's PRIMARY mode (control_bias,
    default 75%) enumerates the same interactive controls but clicks their
    on-screen CENTRE with real SendInput — a genuine mouse click that any
    real hit-testing bug will intercept.
  * Column header clicks (sort) and header-border drags (column resize) —
    QHeaderView is not in monkey_test.py's `_SUPPORTED_TYPES` dispatch table
    at all, so a UIA-driven run never triggers a sort or a resize.
  * Continuous cursor movement across widgets (hover / mouse-enter-leave),
    which drives QSS `:hover` states and tooltips.
  * Drag gestures (splitter drags, column-resize drags).
  * Mouse-wheel scroll events at an arbitrary point.
  * Clicks that land on "dead space" between widgets rather than on a
    named element.

Every iteration falls into one of three bands (see MouseConfig.control_bias):
control-targeted real click (~75%), header sort/resize (~15%), pure random-pixel
chaos (~10%). The control band is what makes this a real "click the buttons with
the mouse" tester rather than a blind-pixel fuzzer.

The `QHeaderView.ResizeToContents` app-freeze fixed in commit fc9dd46 is the
concrete example: it is triggered by `sortByColumn()` (a header click) or a
row-insert while `ResizeToContents` is active, and the wild/moderate/mild
9-hour chaos runs (June 2026) never reproduced it because monkey_test.py never
clicks a header. A real user resizing a window or clicking "Name" to sort a
200-row device table hits it immediately.

This script complements (does NOT replace) monkey_test.py: it reuses every
piece of monkey_test.py's safety machinery (blacklist, dialog guard, focus
reclaim, health/hang monitor, crash reporting, app launch/restart) by
subclassing `MonkeyTester`, and replaces only the "pick a UIA control and
call its method" step with "pick a raw screen point / header rect and drive
the OS input queue directly via SendInput".

Usage (source - skips build step, faster iteration):
    python tools/monkey_mouse_test.py --source

Usage (exe):
    python tools/monkey_mouse_test.py "dist\\NetSentinel.exe"

Usage (attach to already-running app):
    python tools/monkey_mouse_test.py --connect

Options (in addition to every monkey_test.py option — see its --help):
    --drag-prob F         Probability of a drag gesture per non-header action (default 0.12)
    --scroll-prob F       Probability of a wheel-scroll action (default 0.20)
    --right-click-prob F  Probability of a right-click (context menu) action (default 0.08)
    --double-click-prob F Probability of a double-click action (default 0.08)
    --control-bias F      Probability of clicking the centre of a real
                          interactive control (Button/CheckBox/ComboBox/...)
                          with a real cursor, instead of a header or random
                          pixel (default 0.75) — this is the primary mode that
                          exercises OS hit-testing UIA-invoke can't reach.
    --header-bias F       Probability of biasing an iteration toward a header
                          sort-click or column-resize drag instead of a random
                          point (default 0.15) — targets the QHeaderView bug
                          class UIA-driven testing misses entirely.
    --start-page NAME     Page to force-navigate to (via Ctrl+K, keyboard —
                          not mouse) right after startup/restart, so every
                          run begins from the same known state instead of
                          whatever page QSettings restored (default "Home").
    --page-switch-every N Force a keyboard-driven page navigation every N
                          iterations so the run doesn't spend its whole
                          duration randomly clicking a single page
                          (default 12).

A pure random-point clicker would otherwise happily sit on whatever page the
app opened to (last-open section restored from QSettings) and click blind
points on that one page for the entire run — real coverage of the other ~60
pages requires forcing navigation, which is done via the same keyboard/
command-palette mechanism monkey_test.py already uses for its own nav
actions (never via mouse, since a mouse click on the flyout is exactly the
kind of UIA-tree-shaped action this tool intentionally avoids).

Requirements: same as monkey_test.py — pip install pywinauto psutil Pillow

Exit codes: identical to monkey_test.py (0 clean, 1 crash/hang, 2 launch failure)
"""

import ctypes
import dataclasses
import random
import sys
import time
from collections import namedtuple
import ctypes.wintypes
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
try:
    import monkey_test as _mt
except ImportError:
    if __name__ == "__main__":
        sys.exit("ERROR: pywinauto/psutil required.  pip install pywinauto psutil")
    raise

# ── Win32 SendInput plumbing ───────────────────────────────────────────────────
# Real cursor movement + hardware-level click/drag/scroll events, as opposed to
# pywinauto's click_input() which teleports the cursor onto a known UIA element.
# Using SendInput (not the deprecated mouse_event) so intermediate WM_MOUSEMOVE
# messages fire during transit, exercising hover/tooltip code paths a UIA
# element-targeted click never touches.

_PUL = ctypes.POINTER(ctypes.c_ulong)


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long), ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_long), ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong), ("dwExtraInfo", _PUL),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("mi", _MouseInput)]


class _Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", _InputUnion)]


_INPUT_MOUSE = 0
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_WHEEL = 0x0800

_Rect = namedtuple("_Rect", ["left", "top", "right", "bottom"])


def _send_mouse_event(flags: int, data: int = 0) -> None:
    extra = ctypes.c_ulong(0)
    ii = _InputUnion()
    ii.mi = _MouseInput(0, 0, data, flags, 0, ctypes.pointer(extra))
    inp = _Input(_INPUT_MOUSE, ii)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))


def _set_cursor_pos(x: int, y: int) -> None:
    try:
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
    except Exception:
        pass  # non-fatal — a missed move is caught by the next iteration's action result


def _get_cursor_pos() -> Tuple[int, int]:
    pt = ctypes.wintypes.POINT()
    try:
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y
    except Exception:
        return 0, 0


def _move_mouse_smooth(x2: int, y2: int, steps: int = 12, step_delay: float = 0.012) -> None:
    """Move the real OS cursor to (x2, y2) in discrete steps.

    Stepping (rather than SetCursorPos teleport) makes the OS generate real
    intermediate WM_MOUSEMOVE messages, so hover-triggered QSS states and
    tooltips get exercised the same way they would for an actual user.
    """
    x1, y1 = _get_cursor_pos()
    for i in range(1, steps + 1):
        ix = int(x1 + (x2 - x1) * i / steps)
        iy = int(y1 + (y2 - y1) * i / steps)
        _set_cursor_pos(ix, iy)
        time.sleep(step_delay)


def _click(x: int, y: int, button: str = "left") -> None:
    _move_mouse_smooth(x, y)
    down, up = ((_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP) if button == "left"
                else (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP))
    _send_mouse_event(down)
    time.sleep(random.uniform(0.03, 0.09))
    _send_mouse_event(up)


def _double_click(x: int, y: int) -> None:
    _click(x, y)
    time.sleep(random.uniform(0.05, 0.12))
    _send_mouse_event(_MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    _send_mouse_event(_MOUSEEVENTF_LEFTUP)


def _drag(x1: int, y1: int, x2: int, y2: int) -> None:
    _move_mouse_smooth(x1, y1)
    _send_mouse_event(_MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.05)
    _move_mouse_smooth(x2, y2, steps=16, step_delay=0.015)
    time.sleep(0.05)
    _send_mouse_event(_MOUSEEVENTF_LEFTUP)


def _scroll(x: int, y: int, notches: int) -> None:
    _move_mouse_smooth(x, y)
    _send_mouse_event(_MOUSEEVENTF_WHEEL, data=notches * 120)


def _rect_contains(rect, x: int, y: int, pad: int = 0) -> bool:
    return (rect.left - pad <= x <= rect.right + pad
            and rect.top - pad <= y <= rect.bottom + pad)


# Pages safe to force-navigate to for page-cycling coverage. Reuses
# monkey_test.py's already-vetted read-only page list and adds "Devices" —
# the primary sortable-table page (large QHeaderView, many rows) that
# monkey_test.py's own list omits because it also contains blacklisted
# buttons ("Remove Device"); those buttons stay protected by the same
# exclusion-zone logic used for random-point selection.
_PAGE_POOL: List[str] = list(_mt._SAFE_PAGES) + ["Devices"]


def _navigate_to_page(win, label: str, log) -> bool:
    """Force navigation to *label* via the Ctrl+K command palette.

    Keyboard-driven, not mouse — this is deliberate. The random-point mouse
    fuzzing in this tool must never be relied on to reach a specific page;
    it wanders. Anchoring the run to a known page (at startup) and moving it
    on a schedule (during the run) needs a deterministic mechanism, and the
    palette is the same one monkey_test.py already uses for its own nav
    actions, so it doesn't introduce a second, less-tested code path.
    """
    try:
        win.type_keys("^k")
        time.sleep(0.45)
        # set_foreground=False from here on: type_keys() defaults to
        # set_foreground=True, which re-focuses `win` (the cached DASHBOARD
        # window) before sending keys. Ctrl+K just opened the command
        # palette as its own top-level window that already took real focus
        # via its own showEvent(); re-asserting focus on the dashboard here
        # steals it straight back, so the typed text and Enter land on the
        # dashboard instead of the palette and navigation silently no-ops.
        win.type_keys(label[:6], with_spaces=True, pause=0.04, set_foreground=False)
        time.sleep(0.30)
        win.type_keys("{ENTER}", set_foreground=False)
        time.sleep(0.50)
        log.info("[nav] Forced navigation to %r via command palette", label)
        return True
    except Exception as exc:
        log.warning("[nav] Forced navigation to %r failed: %s", label, exc)
        try:
            win.type_keys("{ESC}")
        except Exception:
            pass  # non-fatal — next iteration's dialog/focus guards recover
        return False


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class MouseConfig(_mt.Config):
    drag_prob: float = 0.12
    scroll_prob: float = 0.20
    right_click_prob: float = 0.08
    double_click_prob: float = 0.08
    # Probability an iteration targets a discovered header rect (sort click
    # or column-border resize drag) instead of a random safe point. This is
    # the setting that reaches the bug class monkey_test.py structurally
    # cannot: QHeaderView sort/resize is not in its control dispatch table.
    header_bias: float = 0.15
    # Probability an iteration clicks the CENTRE of a discovered interactive
    # control (Button/CheckBox/ComboBox/TabItem/...) with real SendInput, rather
    # than a random pixel. This is the whole reason this tool exists alongside
    # monkey_test.py: monkey_test.py invokes controls through the UIA pattern
    # (no real cursor, no hit-testing), so a transparent overlay intercepting a
    # click, a wrong-widget-on-top z-order bug, or a hover-gated control are all
    # invisible to it. A real click at the control's on-screen centre goes
    # through the OS hit-test and surfaces exactly those. Default 0.75 →
    # ~75% control-targeted, ~15% header, ~10% pure-random chaos.
    control_bias: float = 0.75
    zone_refresh_every: int = 5   # iterations between UIA rescans for zones/headers
    # Deterministic start page (forced via keyboard, not mouse) so every run
    # begins from the same known state instead of whatever QSettings restored.
    start_page: str = "Home"
    # Force a keyboard-driven page navigation every N iterations so the run
    # doesn't spend its whole duration randomly clicking a single page.
    page_switch_every: int = 12
    # Maximise the app window at startup (and after every restart) so it fills
    # the work area. With the window maximised almost every on-screen point is
    # inside the app, which shrinks the off-window click surface to near zero —
    # complementary to (not a replacement for) the per-action _point_ok guard,
    # which still covers the taskbar strip, multi-monitor gaps, and popups.
    maximize: bool = True


# ── Tester ─────────────────────────────────────────────────────────────────────

_HEADER_TYPES = frozenset({"Header", "HeaderItem"})

# Interactive control types worth targeting with a real click. Deliberately
# excludes Edit (a click just steals keyboard focus, no behaviour to fuzz) and
# DataItem/table cells (hundreds per page, and random-point clicking already
# covers table bodies). Blacklisted buttons (destructive actions) are filtered
# separately via _is_blacklisted — same protection random-point clicking uses.
_CLICKABLE_TYPES = frozenset({
    "Button", "SplitButton", "CheckBox", "RadioButton",
    "ComboBox", "TabItem", "Hyperlink", "MenuItem", "ListItem",
})


class MouseMonkeyTester(_mt.MonkeyTester):
    """Reuses MonkeyTester's launch/connect/dialog-guard/health-monitor/crash-report
    machinery unchanged; overrides only how a single iteration picks and performs
    its action — raw screen coordinates + SendInput instead of a UIA control."""

    def __init__(self, cfg: MouseConfig):
        super().__init__(cfg)
        self.cfg: MouseConfig = cfg
        self._exclusion_rects: List = []
        self._header_rects: List = []
        self._control_rects: List = []   # (rect, name, ctype) of clickable controls
        self._last_zone_scan = -999
        self._start_page_done = False
        self._last_page_switch = 0

    # ── Off-window safety guard ──────────────────────────────────────────────
    # The single most important invariant of a raw-SendInput tester: never issue
    # a mouse event whose target point is outside the app window. monkey_test.py
    # is immune to this class of bug because it invokes controls by their UIA
    # identity (pywinauto re-resolves the element at click time); a coordinate
    # click has no such safety — if the window moved, minimised, or lost
    # foreground in the gap between capturing a rect (during _refresh_zones, a
    # multi-second UIA scan on a big page) and the SendInput, the click lands on
    # whatever is now at those screen coordinates: the desktop, or another app.
    # Every action method routes its clicks/drags/scrolls through _g_* wrappers
    # that re-verify, immediately before the input, that (a) our window is still
    # the foreground window and (b) the point is inside its LIVE rectangle.

    def _foreground_is_ours(self) -> bool:
        hwnd = getattr(self._win, "handle", 0) or 0
        if not hwnd:
            return False
        return _mt._get_foreground_hwnd() == hwnd

    def _win_rect_now(self):
        try:
            return self._win.rectangle()
        except Exception:
            return None  # window vanished from UIA tree; caller treats as "not ok"

    def _maximize_window(self) -> None:
        """Maximise the app window so it fills the work area. Best-effort: if it
        fails (or the app declines to maximise), the per-action _point_ok guard
        is still the hard backstop against off-window clicks."""
        if not self.cfg.maximize:
            return
        hwnd = getattr(self._win, "handle", 0) or 0
        if not hwnd:
            return
        try:
            ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
            time.sleep(0.35)
            self.log.info("[guard] app window maximised (fills work area)")
        except Exception:
            self.log.debug("[guard] maximise failed; per-action _point_ok still applies")

    def _point_ok(self, x: int, y: int, margin: int = 2) -> bool:
        """True only if our window is foreground AND (x, y) is inside its live
        rectangle. Re-checked immediately before every SendInput so a focus
        drift or window move between zone-scan and click can never send the
        cursor outside the app."""
        if not self._foreground_is_ours():
            return False
        r = self._win_rect_now()
        if r is None:
            return False
        return (r.left + margin <= x <= r.right - margin
                and r.top + margin <= y <= r.bottom - margin)

    def _off_window_skip(self, where: str, x: int, y: int) -> None:
        self.stats.off_window += 1
        self.log.debug("[guard] %s skipped: (%d,%d) outside live window rect "
                       "or app not foreground (off_window=%d)",
                       where, x, y, self.stats.off_window)

    def _g_click(self, x: int, y: int, button: str = "left") -> bool:
        if not self._point_ok(x, y):
            self._off_window_skip("click", x, y)
            return False
        _click(x, y, button)
        return True

    def _g_double_click(self, x: int, y: int) -> bool:
        if not self._point_ok(x, y):
            self._off_window_skip("double_click", x, y)
            return False
        _double_click(x, y)
        return True

    def _g_drag(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        # Both endpoints must be inside the live window; a drag that starts or
        # ends outside can fling the cursor onto another app mid-gesture.
        if not self._point_ok(x1, y1) or not self._point_ok(x2, y2):
            self._off_window_skip("drag", x2, y2)
            return False
        _drag(x1, y1, x2, y2)
        return True

    def _g_scroll(self, x: int, y: int, notches: int) -> bool:
        if not self._point_ok(x, y):
            self._off_window_skip("scroll", x, y)
            return False
        _scroll(x, y, notches)
        return True

    def _dismiss_startup_overlays(self) -> None:
        # Called by the base class at both initial startup AND after every
        # auto-restart (_restart_app). Re-arming the flag here — rather than
        # navigating immediately — means the actual palette navigation runs
        # inside _run_one() after _assert_focus() has already succeeded, so
        # the window is guaranteed foreground before we send Ctrl+K. Doing
        # it here directly would race the explicit foreground claim that
        # happens later in run()/_restart_app().
        super()._dismiss_startup_overlays()
        self._start_page_done = False

    # ── Zone discovery (read-only UIA — used only to pick safe/interesting
    #    coordinates; the actual interaction is raw input, not UIA) ─────────

    def _refresh_zones(self, n: int) -> None:
        if n - self._last_zone_scan < self.cfg.zone_refresh_every:
            return
        self._last_zone_scan = n
        try:
            win_rect = self._win.rectangle()
        except Exception:
            self.log.debug("window rectangle unavailable; skipping zone refresh")
            return

        # Always exclude the frameless title-bar chrome strip regardless of
        # whether UIA enumeration below finds the close/min/max buttons —
        # this is the same 60px margin monkey_test.py uses for its spatial filter.
        title_strip = _Rect(win_rect.left, win_rect.top, win_rect.right, win_rect.top + 60)
        exclusion = [title_strip]
        headers = []
        controls = []
        try:
            descendants = self._win.descendants()
        except Exception:
            descendants = []
        for ctrl in descendants:
            try:
                ctype = _mt._safe_type(ctrl)
                if ctype in _HEADER_TYPES:
                    hr = ctrl.rectangle()
                    hcx = (hr.left + hr.right) // 2
                    hcy = (hr.top + hr.bottom) // 2
                    # Drop headers whose centre is outside the window (scrolled
                    # out of a viewport, or a detached popup) — clicking them
                    # would send the cursor off-window.
                    if _rect_contains(win_rect, hcx, hcy):
                        headers.append(hr)
                    continue
                if ctype not in _CLICKABLE_TYPES:
                    continue
                name = _mt._safe_name(ctrl)
                auto_id = _mt._safe_id(ctrl)
                if _mt._is_blacklisted(name, auto_id):
                    # Destructive control — keep clicks (random or targeted) off it.
                    exclusion.append(ctrl.rectangle())
                    continue
                if not ctrl.is_visible() or not ctrl.is_enabled():
                    continue
                rect = ctrl.rectangle()
                # Skip degenerate / offscreen rects and anything under the
                # frameless title-bar chrome strip (close/min/max live there).
                if rect.right - rect.left < 6 or rect.bottom - rect.top < 6:
                    continue
                cx = (rect.left + rect.right) // 2
                cy = (rect.top + rect.bottom) // 2
                if _rect_contains(title_strip, cx, cy):
                    continue
                # Drop controls whose centre lies outside the window rectangle
                # (scrolled out of a viewport, off-screen stacked page, or a
                # detached popup). The per-action _point_ok guard is the final
                # net, but filtering here keeps the pool clean and the run
                # productive rather than repeatedly skipping dead targets.
                if not _rect_contains(win_rect, cx, cy):
                    continue
                controls.append((rect, name, ctype))
            except Exception:
                continue
        self._exclusion_rects = exclusion
        self._header_rects = headers
        self._control_rects = controls
        self.log.debug("[zones] exclusion=%d header=%d control=%d",
                       len(exclusion), len(headers), len(controls))

    def _random_point(self, max_tries: int = 25) -> Optional[Tuple[int, int]]:
        try:
            r = self._win.rectangle()
        except Exception:
            return None
        margin = 10  # stay clear of the frameless-window resize border
        if r.right - r.left <= margin * 2 or r.bottom - r.top <= margin * 2:
            return None
        for _ in range(max_tries):
            x = random.randint(r.left + margin, r.right - margin)
            y = random.randint(r.top + margin, r.bottom - margin)
            if any(_rect_contains(z, x, y, pad=2) for z in self._exclusion_rects):
                continue
            return x, y
        return None

    # ── Action selection ────────────────────────────────────────────────────

    def _do_page_switch(self, n: int, forced_page: Optional[str] = None) -> "_mt.Action":
        """Force a keyboard-driven palette navigation. Used both for the
        one-time deterministic start-page anchor and the recurring
        page_switch_every cycling — see _run_one()."""
        ts = datetime.now().strftime("%H:%M:%S")
        page = forced_page or random.choice(_PAGE_POOL)
        ok = _navigate_to_page(self._win, page, self.log)
        self._last_page_switch = n
        self._last_zone_scan = -999   # force a fresh zone/header scan on the new page
        return _mt.Action(n=n, ts=ts, ctype="Navigation", name="<win>",
                           auto_id="", action=f"forced_page:{page}",
                           result="ok" if ok else "err")

    def _act_header(self, n: int, ts: str) -> "_mt.Action":
        rect = random.choice(self._header_rects)
        try:
            cy = (rect.top + rect.bottom) // 2
            if random.random() < 0.5:
                cx = (rect.left + rect.right) // 2
                ok = self._g_click(cx, cy)
                action = f"header_sort_click:({cx},{cy})"
            else:
                edge_x = rect.right - 2
                # Clamp the drag target into the live window so a wide resize
                # can never fling the cursor past the right edge onto the desktop.
                wr = self._win_rect_now()
                raw_end = edge_x + random.randint(-60, 120)
                end_x = (min(max(raw_end, wr.left + 4), wr.right - 4)
                         if wr is not None else raw_end)
                ok = self._g_drag(edge_x, cy, end_x, cy)
                action = f"header_resize_drag:x={edge_x}->{end_x}"
            if not ok:
                return _mt.Action(n=n, ts=ts, ctype="Header", name="<header>",
                                  auto_id="", action="header:off_window",
                                  result="skipped:off_window")
            result = "ok"
            self.stats.record("Header", action)
            self._post_click_dialog_guard()
        except Exception as exc:
            action = "exception"
            result = f"err:{exc.__class__.__name__}:{str(exc)[:60]}"
            self.stats.exceptions += 1
        return _mt.Action(n=n, ts=ts, ctype="Header", name="<header>",
                           auto_id="", action=action, result=result)

    def _do_mouse_action(self, n: int) -> "_mt.Action":
        """Pick and perform one raw-input action.

        Cumulative probability bands (see MouseConfig.control_bias):
          [0, control_bias)              → click the CENTRE of a real control
          [control_bias, +header_bias)   → header sort-click / column-resize
          [that, 1.0)                    → pure random-pixel chaos
        The control-targeted band is what actually clicks buttons/checkboxes
        with a real cursor — the coverage monkey_test.py's UIA-invoke can't give.
        Each guard falls through when its rect list is empty (e.g. a page with
        no enumerable controls degrades gracefully to header/random)."""
        ts = datetime.now().strftime("%H:%M:%S")
        roll = random.random()
        if self._control_rects and roll < self.cfg.control_bias:
            return self._act_control(n, ts)
        if self._header_rects and roll < self.cfg.control_bias + self.cfg.header_bias:
            return self._act_header(n, ts)
        return self._act_random_point(n, ts)

    def _act_control(self, n: int, ts: str) -> "_mt.Action":
        """Click (or right/double-click) the centre of a discovered interactive
        control using real SendInput, so the click goes through OS hit-testing."""
        rect, name, ctype = random.choice(self._control_rects)
        # Jitter a few px inside the border so repeated runs don't hit the exact
        # same pixel, but never land on the 1px edge where a click can miss.
        lx, rx = rect.left + 3, rect.right - 3
        ty, by = rect.top + 2, rect.bottom - 2
        cx = random.randint(lx, rx) if rx > lx else (rect.left + rect.right) // 2
        cy = random.randint(ty, by) if by > ty else (rect.top + rect.bottom) // 2
        roll = random.random()
        try:
            if roll < self.cfg.right_click_prob:
                ok = self._g_click(cx, cy, button="right")
                if ok:
                    time.sleep(0.2)
                    try:
                        self._win.type_keys("{ESC}")  # dismiss any context menu that opened
                    except Exception:
                        pass  # non-fatal — post-click dialog guard is the safety net
                verb = "right_click"
            elif roll < self.cfg.right_click_prob + self.cfg.double_click_prob:
                ok = self._g_double_click(cx, cy)
                verb = "double_click"
            else:
                ok = self._g_click(cx, cy)
                verb = "click"
            if not ok:
                return _mt.Action(n=n, ts=ts, ctype=ctype, name=(name or f"({cx},{cy})")[:40],
                                  auto_id="", action=f"ctrl_{verb}:{ctype}:off_window",
                                  result="skipped:off_window")
            action = f"ctrl_{verb}:{ctype}:({cx},{cy})"
            result = "ok"
            # Record the REAL control type so by_control_type reflects genuine
            # control hits (Button/CheckBox/...), not an undifferentiated "Mouse".
            self.stats.record(ctype, action)
            self._post_click_dialog_guard()
        except Exception as exc:
            action = "exception"
            result = f"err:{exc.__class__.__name__}:{str(exc)[:60]}"
            self.stats.exceptions += 1
        return _mt.Action(n=n, ts=ts, ctype=ctype, name=(name or f"({cx},{cy})")[:40],
                           auto_id="", action=action, result=result)

    def _act_random_point(self, n: int, ts: str) -> "_mt.Action":
        """Original pure-chaos path: a random safe pixel, then a weighted
        drag / scroll / right / double / left action at that point."""
        pt = self._random_point()
        if pt is None:
            return _mt.Action(n=n, ts=ts, ctype="Mouse", name="<no-safe-point>",
                               auto_id="", action="skip", result="skipped:no_point")
        x, y = pt
        roll = random.random()
        thresholds = (
            self.cfg.drag_prob,
            self.cfg.drag_prob + self.cfg.scroll_prob,
            self.cfg.drag_prob + self.cfg.scroll_prob + self.cfg.right_click_prob,
            self.cfg.drag_prob + self.cfg.scroll_prob + self.cfg.right_click_prob + self.cfg.double_click_prob,
        )
        try:
            if roll < thresholds[0]:
                x2, y2 = self._random_point() or (x, y)
                ok = self._g_drag(x, y, x2, y2)
                action = f"drag:({x},{y})->({x2},{y2})"
            elif roll < thresholds[1]:
                notches = random.choice([-3, -2, -1, 1, 2, 3])
                ok = self._g_scroll(x, y, notches)
                action = f"scroll:({x},{y}):{notches}"
            elif roll < thresholds[2]:
                ok = self._g_click(x, y, button="right")
                if ok:
                    time.sleep(0.2)
                    try:
                        self._win.type_keys("{ESC}")  # dismiss any context menu that opened
                    except Exception:
                        pass  # non-fatal — post-click dialog guard is the safety net
                action = f"right_click:({x},{y})"
            elif roll < thresholds[3]:
                ok = self._g_double_click(x, y)
                action = f"double_click:({x},{y})"
            else:
                ok = self._g_click(x, y)
                action = f"click:({x},{y})"
            if not ok:
                return _mt.Action(n=n, ts=ts, ctype="Mouse", name=f"({x},{y})",
                                  auto_id="", action="off_window", result="skipped:off_window")
            result = "ok"
            self.stats.record("Mouse", action)
            self._post_click_dialog_guard()
        except Exception as exc:
            action = "exception"
            result = f"err:{exc.__class__.__name__}:{str(exc)[:60]}"
            self.stats.exceptions += 1
        return _mt.Action(n=n, ts=ts, ctype="Mouse", name=f"({x},{y})",
                           auto_id="", action=action, result=result)

    # ── Iteration (mirrors MonkeyTester._run_one's safety wrapper; only the
    #    "pick and perform an action" step in the middle differs) ──────────

    def _run_one(self, n: int) -> bool:
        if self._proc:
            _mt._wait_cpu(self._proc, self.cfg.cpu_threshold, self.cfg.cpu_wait_max)

        sleep = random.uniform(
            *{"mild": (0.6, 2.0), "wild": (0.05, 0.6)}.get(self.cfg.chaos, (0.3, 1.5))
        )
        time.sleep(sleep)

        if not self._alive():
            self.log.error("Process died before iteration %d", n)
            return False
        if not self._window_ok():
            self.log.error("Window gone before iteration %d", n)
            return False

        self._dismiss_blocking_dialogs()

        if not self._assert_focus():
            self.log.warning("[focus] skipping iteration %d (could not reclaim foreground)", n)
            self.stats.skipped += 1
            self.stats.completed += 1
            self._last_iter_time = time.time()
            return True
        time.sleep(0.08)

        self._refresh_zones(n)

        if not self._start_page_done:
            self._maximize_window()   # fill the work area before the run starts
            rec = self._do_page_switch(n, forced_page=self.cfg.start_page)
            self._start_page_done = True
        elif n - self._last_page_switch >= self.cfg.page_switch_every:
            rec = self._do_page_switch(n)
        elif random.random() < self.cfg.nav_prob:
            rec = self._do_nav(n)   # inherited: Ctrl+F/Ctrl+K/Esc keyboard shortcuts
        else:
            rec = self._do_mouse_action(n)

        self.hist.add(rec)
        self.log.debug(
            "[%4d] %-14s  %-24s  name=%-30r  %s",
            n, rec.ctype, rec.action, rec.name, rec.result,
        )
        self.stats.completed += 1
        self._last_iter_time = time.time()
        return True


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser():
    p = _mt._build_parser()
    p.description = "Raw-input (real mouse) chaos tester for NetSentinel"
    p.epilog = __doc__
    p.add_argument("--drag-prob", type=float, default=0.12, metavar="F",
                   help="Probability of a drag gesture per non-header action (default 0.12)")
    p.add_argument("--scroll-prob", type=float, default=0.20, metavar="F",
                   help="Probability of a wheel-scroll action (default 0.20)")
    p.add_argument("--right-click-prob", type=float, default=0.08, metavar="F",
                   help="Probability of a right-click action (default 0.08)")
    p.add_argument("--double-click-prob", type=float, default=0.08, metavar="F",
                   help="Probability of a double-click action (default 0.08)")
    p.add_argument("--header-bias", type=float, default=0.15, metavar="F",
                   help="Probability of targeting a table header (sort click or "
                        "column-resize drag) instead of a random point (default 0.15)")
    p.add_argument("--control-bias", type=float, default=0.75, metavar="F",
                   help="Probability of clicking the centre of a real interactive "
                        "control (Button/CheckBox/ComboBox/...) with a real cursor, "
                        "instead of a header or random pixel (default 0.75)")
    p.add_argument("--start-page", default="Home", metavar="NAME",
                   help="Page to force-navigate to via keyboard at startup/restart, "
                        "so every run begins from the same known state (default Home)")
    p.add_argument("--page-switch-every", type=int, default=12, metavar="N",
                   help="Force a keyboard-driven page navigation every N iterations "
                        "(default 12) so the run isn't stuck clicking one page")
    p.add_argument("--no-maximize", action="store_true",
                   help="Do NOT maximise the app window at startup. By default the "
                        "window is maximised so almost every on-screen point is inside "
                        "the app, minimising off-window clicks; pass this to test the "
                        "app in its restored (windowed) size instead")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if not args.source and not args.connect and not args.exe_path:
        print("ERROR: provide an exe path, --source, or --connect", file=sys.stderr)
        sys.exit(2)

    if args.exe_path and not Path(args.exe_path).exists():
        print(f"ERROR: exe not found: {args.exe_path}", file=sys.stderr)
        sys.exit(2)

    if args.tracemalloc and not args.source:
        print("WARNING: --tracemalloc only works with --source (ignored for exe/connect mode)",
              file=sys.stderr)

    cfg = MouseConfig(
        exe_path=args.exe_path,
        use_source=args.source,
        connect_only=args.connect,
        iterations=args.iterations,
        duration_secs=args.duration,
        chaos=args.chaos,
        seed=args.seed,
        screenshots=not args.no_screenshots,
        mem_limit_mb=args.mem_limit,
        output_dir=args.output_dir,
        log_file=args.log,
        focus_interval=args.focus_interval,
        prevent_sleep=not args.no_prevent_sleep,
        tracemalloc=args.tracemalloc and args.source,
        max_restarts=args.max_restarts,
        warmup_secs=args.warmup_secs,
        drag_prob=args.drag_prob,
        scroll_prob=args.scroll_prob,
        right_click_prob=args.right_click_prob,
        double_click_prob=args.double_click_prob,
        header_bias=args.header_bias,
        control_bias=args.control_bias,
        start_page=args.start_page,
        page_switch_every=args.page_switch_every,
        maximize=not args.no_maximize,
    )

    sys.exit(MouseMonkeyTester(cfg).run())


if __name__ == "__main__":
    main()
