#!/usr/bin/env python3
"""
tools/monkey_mouse_test.py - Raw-input (real mouse) chaos harness for NetSentinel
==================================================================================
`tools/monkey_test.py` drives the UIA control tree: every action targets a named
element (Button, Edit, ComboBox, ...) via pywinauto's `click_input()`, which
teleports the OS cursor onto that element and clicks it. That is fast and finds
real bugs, but it structurally cannot exercise:

  * Column header clicks (sort) and header-border drags (column resize) —
    QHeaderView is not in monkey_test.py's `_SUPPORTED_TYPES` dispatch table
    at all, so a UIA-driven run never triggers a sort or a resize.
  * Continuous cursor movement across widgets (hover / mouse-enter-leave),
    which drives QSS `:hover` states and tooltips.
  * Drag gestures (splitter drags, column-resize drags).
  * Mouse-wheel scroll events at an arbitrary point.
  * Clicks that land on "dead space" between widgets rather than on a
    named element.

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
    --header-bias F       Probability of biasing an iteration toward a header
                          sort-click or column-resize drag instead of a random
                          point (default 0.25) — this is the setting that
                          targets the bug class UIA-driven testing misses.
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
from ctypes import wintypes
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
    pt = wintypes.POINT()
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
        win.type_keys(label[:6], with_spaces=True, pause=0.04)
        time.sleep(0.30)
        win.type_keys("{ENTER}")
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
    header_bias: float = 0.25
    zone_refresh_every: int = 5   # iterations between UIA rescans for zones/headers
    # Deterministic start page (forced via keyboard, not mouse) so every run
    # begins from the same known state instead of whatever QSettings restored.
    start_page: str = "Home"
    # Force a keyboard-driven page navigation every N iterations so the run
    # doesn't spend its whole duration randomly clicking a single page.
    page_switch_every: int = 12


# ── Tester ─────────────────────────────────────────────────────────────────────

_HEADER_TYPES = frozenset({"Header", "HeaderItem"})


class MouseMonkeyTester(_mt.MonkeyTester):
    """Reuses MonkeyTester's launch/connect/dialog-guard/health-monitor/crash-report
    machinery unchanged; overrides only how a single iteration picks and performs
    its action — raw screen coordinates + SendInput instead of a UIA control."""

    def __init__(self, cfg: MouseConfig):
        super().__init__(cfg)
        self.cfg: MouseConfig = cfg
        self._exclusion_rects: List = []
        self._header_rects: List = []
        self._last_zone_scan = -999
        self._start_page_done = False
        self._last_page_switch = 0

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
        exclusion = [_Rect(win_rect.left, win_rect.top, win_rect.right, win_rect.top + 60)]
        headers = []
        try:
            descendants = self._win.descendants()
        except Exception:
            descendants = []
        for ctrl in descendants:
            try:
                ctype = _mt._safe_type(ctrl)
                if ctype in _HEADER_TYPES:
                    headers.append(ctrl.rectangle())
                    continue
                if ctype in ("Button", "SplitButton", "MenuItem"):
                    name = _mt._safe_name(ctrl)
                    auto_id = _mt._safe_id(ctrl)
                    if _mt._is_blacklisted(name, auto_id):
                        exclusion.append(ctrl.rectangle())
            except Exception:
                continue
        self._exclusion_rects = exclusion
        self._header_rects = headers
        self.log.debug("[zones] exclusion=%d header=%d", len(exclusion), len(headers))

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
                _click(cx, cy)
                action = f"header_sort_click:({cx},{cy})"
            else:
                edge_x = rect.right - 2
                _drag(edge_x, cy, edge_x + random.randint(-60, 120), cy)
                action = f"header_resize_drag:x={edge_x}"
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
        ts = datetime.now().strftime("%H:%M:%S")

        if self._header_rects and random.random() < self.cfg.header_bias:
            return self._act_header(n, ts)

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
                _drag(x, y, x2, y2)
                action = f"drag:({x},{y})->({x2},{y2})"
            elif roll < thresholds[1]:
                notches = random.choice([-3, -2, -1, 1, 2, 3])
                _scroll(x, y, notches)
                action = f"scroll:({x},{y}):{notches}"
            elif roll < thresholds[2]:
                _click(x, y, button="right")
                time.sleep(0.2)
                try:
                    self._win.type_keys("{ESC}")  # dismiss any context menu that opened
                except Exception:
                    pass  # non-fatal — post-click dialog guard is the safety net
                action = f"right_click:({x},{y})"
            elif roll < thresholds[3]:
                _double_click(x, y)
                action = f"double_click:({x},{y})"
            else:
                _click(x, y)
                action = f"click:({x},{y})"
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
    p.add_argument("--header-bias", type=float, default=0.25, metavar="F",
                   help="Probability of targeting a table header (sort click or "
                        "column-resize drag) instead of a random point (default 0.25)")
    p.add_argument("--start-page", default="Home", metavar="NAME",
                   help="Page to force-navigate to via keyboard at startup/restart, "
                        "so every run begins from the same known state (default Home)")
    p.add_argument("--page-switch-every", type=int, default=12, metavar="N",
                   help="Force a keyboard-driven page navigation every N iterations "
                        "(default 12) so the run isn't stuck clicking one page")
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
        start_page=args.start_page,
        page_switch_every=args.page_switch_every,
    )

    sys.exit(MouseMonkeyTester(cfg).run())


if __name__ == "__main__":
    main()
