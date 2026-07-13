"""
Tests for the native window chrome (experimental/native_chrome, Phase 3).

WHY THESE ARE PURE-FUNCTION TESTS
---------------------------------
RULE-TP4-DASH forbids constructing a Dashboard in-process, and a WM_NCHITTEST
callback cannot be driven from pytest at all — Windows invokes it, we do not.  So
ui/native_chrome.py is split deliberately: every decision that can be *wrong* lives
in pure functions taking plain ints, and the ctypes callback is a thin shell around
them.  That shell is covered by the two structural guards at the bottom.

The last guard is the important one.  RULE-WIN9's mechanism is that the native
callback must never touch Qt: Windows calls it synchronously and reentrantly from
inside its own SendMessage dispatch, so a Qt call (or a GIL block) there is a route
to IsHungAppWindow, and the resulting fault is a native SEH fault no Python
try/except can catch.  A code review cannot hold that line across future edits; an
AST guard can.
"""
import ast
import re
from pathlib import Path

import pytest

from ui.native_chrome import (
    HANDLED_NC_MESSAGES,
    HTCAPTION,
    HTCLIENT,
    HTMAXBUTTON,
    HTTOP,
    HTTOPLEFT,
    HTTOPRIGHT,
    HTLEFT,
    HTBOTTOM,
    HTRIGHT,
    WM_NCCALCSIZE,
    WM_NCHITTEST,
    WM_NCLBUTTONDOWN,
    WM_NCLBUTTONUP,
    WM_NCMOUSELEAVE,
    WM_NCMOUSEMOVE,
    client_origin,
    client_rect_for_nccalcsize,
    hit_test,
    lparam_point,
)

REPO = Path(__file__).resolve().parents[1]

# Typical Windows 11 @ 100% DPI.
FRAME_X, FRAME_Y, PADDING = 8, 8, 4

# A 1000x800 window at (100, 100), header 42px tall (matches _build_header).
WIN_RECT = (100, 100, 1100, 900)
HEADER = (0, 0, 1000, 42)          # client-relative
MAX_BTN = (908, 0, 954, 42)        # client-relative — middle chrome button
CLIENT_RECTS = (
    (862, 0, 908, 42),             # minimize
    (954, 0, 1000, 42),            # close
    (700, 8, 800, 34),             # "Scan" button
)


def _origin(is_maximized=False):
    return client_origin(WIN_RECT, FRAME_X, FRAME_Y, PADDING, is_maximized)


def _hit_screen(x, y, *, is_maximized=False, default=HTCLIENT):
    """Hit-test a point given in SCREEN coords — the space Windows sends in lParam."""
    return hit_test(
        x, y, WIN_RECT, _origin(is_maximized),
        HEADER, MAX_BTN, CLIENT_RECTS, FRAME_X, FRAME_Y, is_maximized, default,
    )


def _hit(x, y, *, is_maximized=False, default=HTCLIENT):
    """Hit-test a point given in CLIENT coords, converted to screen for the call.

    Note the client origin is inset from the window on the left (the resize border
    stays non-client), so client x=0 is NOT on the window's left edge — border cases
    must use _hit_screen.
    """
    ox, oy = _origin(is_maximized)
    return _hit_screen(x + ox, y + oy, is_maximized=is_maximized, default=default)


# ── WM_NCCALCSIZE ───────────────────────────────────────────────────────────────

def test_nccalcsize_reclaims_only_the_top():
    """Left/right/bottom keep their resize borders; only the caption is reclaimed.

    Insetting the top too would leave the title bar drawn; insetting nothing at all
    (the naive "just return 0") would put the client area outside the window on
    three sides.
    """
    out = client_rect_for_nccalcsize((100, 100, 1100, 900), FRAME_X, FRAME_Y, PADDING, False)
    assert out == (112, 100, 1088, 888)


def test_nccalcsize_maximized_client_is_exactly_the_work_area():
    """Regression (measured on the live window): a maximized client must land on the
    work area exactly — no pixel above the screen, no gap above the taskbar.

    Windows sizes a maximized window to the work area INFLATED by the full frame
    (frame + padding) on every side, and expects WM_NCCALCSIZE to hand that
    inflation back.  Insetting the top by `padding` alone — the value the
    non-maximized branch reclaims — left the header's top 4px off the top of the
    screen and an 8px dead strip above the taskbar.  When maximized there is no
    caption to reclaim: the top takes the same inset as every other side.
    """
    work_area = (0, 0, 3440, 1400)                       # taskbar at the bottom
    inflate_x, inflate_y = FRAME_X + PADDING, FRAME_Y + PADDING
    maximized_window = (
        work_area[0] - inflate_x, work_area[1] - inflate_y,
        work_area[2] + inflate_x, work_area[3] + inflate_y,
    )

    client = client_rect_for_nccalcsize(
        maximized_window, FRAME_X, FRAME_Y, PADDING, True
    )

    assert client == work_area, (
        f"maximized client {client} != work area {work_area} — "
        f"top<0 clips the header off-screen; bottom<work leaves a dead strip."
    )


def test_nccalcsize_only_maximized_reclaims_the_top():
    """The top inset is the whole trick, and it differs by state: restored windows
    reclaim the caption (top untouched), maximized ones must not."""
    rect = (100, 100, 1100, 900)
    normal = client_rect_for_nccalcsize(rect, FRAME_X, FRAME_Y, PADDING, False)
    zoomed = client_rect_for_nccalcsize(rect, FRAME_X, FRAME_Y, PADDING, True)

    assert normal[1] == rect[1], "restored window must reclaim the caption"
    assert zoomed[1] == rect[1] + FRAME_Y + PADDING
    assert normal[0] == zoomed[0] and normal[2] == zoomed[2] and normal[3] == zoomed[3]


def test_client_origin_tracks_nccalcsize():
    """The origin used to convert cursor->client must agree with the rect we asked
    for, or every cached widget rect is offset and the whole hit-test is skewed."""
    for is_max in (False, True):
        rect = client_rect_for_nccalcsize(WIN_RECT, FRAME_X, FRAME_Y, PADDING, is_max)
        assert client_origin(WIN_RECT, FRAME_X, FRAME_Y, PADDING, is_max) == (rect[0], rect[1])


# ── WM_NCHITTEST ────────────────────────────────────────────────────────────────

def test_top_edge_is_a_resize_border():
    """After WM_NCCALCSIZE there is no non-client area at the top, so Windows says
    HTCLIENT there and we must synthesize the resize band ourselves."""
    assert _hit(500, 0) == HTTOP
    assert _hit(500, FRAME_Y - 1) == HTTOP


def test_top_corners_win_over_the_side_border_windows_reports():
    """Regression: Windows' own frame still spans the full height, so at the top
    corners it answers plain HTLEFT/HTRIGHT.  Passing that through costs the user
    diagonal corner resize — the top band must be tested first."""
    left, top, right, _bottom = WIN_RECT
    assert _hit_screen(left, top, default=HTLEFT) == HTTOPLEFT
    assert _hit_screen(right - 1, top, default=HTRIGHT) == HTTOPRIGHT


def test_side_and_bottom_borders_pass_through_untouched():
    """These Windows already resolves correctly from the frame we kept — this is
    what buys native edge resize and lets the 8 _Grip widgets go."""
    left, _top, right, bottom = WIN_RECT
    assert _hit_screen(left, 500, default=HTLEFT) == HTLEFT
    assert _hit_screen(right - 1, 500, default=HTRIGHT) == HTRIGHT
    assert _hit_screen(500, bottom - 1, default=HTBOTTOM) == HTBOTTOM


def test_maximized_window_has_no_resize_band():
    """A maximized window cannot be resized; claiming HTTOP there fights the OS."""
    assert _hit(500, 0, is_maximized=True) == HTCAPTION


def test_maximize_button_is_the_caption_button():
    """The one legitimate HTMAXBUTTON — this is what Windows 11 requires before it
    will offer the Snap Layouts flyout."""
    assert _hit(930, 20) == HTMAXBUTTON


def test_other_header_widgets_stay_client():
    """Regression: returning HTCAPTION for the whole header makes every control in
    it unclickable — Qt never sees a mouse event in a non-client area.  Minimize,
    close and Scan must stay HTCLIENT."""
    assert _hit(880, 20) == HTCLIENT, "minimize became non-client — unclickable"
    assert _hit(975, 20) == HTCLIENT, "close became non-client — unclickable"
    assert _hit(750, 20) == HTCLIENT, "Scan button became non-client — unclickable"


def test_empty_header_space_is_the_caption():
    """This is what buys native drag, Aero Snap, shake, double-click and Alt+Space."""
    assert _hit(400, 20) == HTCAPTION


def test_below_the_header_is_ordinary_client():
    assert _hit(400, 300) == HTCLIENT


def test_lparam_point_handles_a_monitor_left_of_the_primary():
    """Screen coords are signed 16-bit halves.  Reading them unsigned puts a cursor
    on a left-hand monitor ~65000px away, and every hit-test silently misses."""
    assert lparam_point((100 & 0xFFFF) | (200 << 16)) == (100, 200)
    packed = ((-50) & 0xFFFF) | (((-30) & 0xFFFF) << 16)
    assert lparam_point(packed) == (-50, -30)


# ── Structural guards ───────────────────────────────────────────────────────────

def test_full_nc_message_set_is_handled():
    """RULE-WIN2: never ship a partial NC implementation.

    Claiming HTMAXBUTTON without owning the button's mouse messages leaves Windows
    half-driving a caption button we draw ourselves — a partial WM_NCHITTEST-only
    hook is exactly the shape that crashed before.
    """
    required = {
        WM_NCCALCSIZE, WM_NCHITTEST, WM_NCMOUSEMOVE,
        WM_NCLBUTTONDOWN, WM_NCLBUTTONUP, WM_NCMOUSELEAVE,
    }
    assert required <= HANDLED_NC_MESSAGES

    source = (REPO / "ui" / "native_chrome.py").read_text(encoding="utf-8")
    proc = _find_function(source, "_make_subclass_proc")
    compared = {
        node.comparators[0].id
        for node in ast.walk(proc)
        if isinstance(node, ast.Compare)
        and node.comparators and isinstance(node.comparators[0], ast.Name)
    }
    missing = {"WM_NCCALCSIZE", "WM_NCHITTEST", "WM_NCMOUSELEAVE",
               "WM_NCLBUTTONDOWN", "WM_NCLBUTTONUP", "WM_NCMOUSEMOVE"} - compared
    assert not missing, (
        f"the subclass proc no longer handles {sorted(missing)}. RULE-WIN2: a "
        f"partial NC-message implementation is the crashing shape — either handle "
        f"the whole set or claim none of it."
    )


def test_subclass_proc_touches_no_qt_object():
    """RULE-WIN9 corollary: the native callback must touch ZERO Qt objects.

    Windows invokes it synchronously and reentrantly from inside its own SendMessage
    dispatch.  A Qt call there (QCursor.pos(), mapToGlobal(), constructing a QTimer)
    reaches into Qt/COM internals from a raw message hook while the main thread may
    be busy elsewhere, and blocking on the GIL inside a synchronous SendMessage is a
    route to IsHungAppWindow.  The sanctioned escape is PostMessage — which lands in
    WM_APP_MAX_HOVER, on Qt's own event loop, out of the input-synchronous context.
    """
    source = (REPO / "ui" / "native_chrome.py").read_text(encoding="utf-8")
    proc = _find_function(source, "_make_subclass_proc")

    offenders = []
    for node in ast.walk(proc):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", "") or ""
            names = [a.name for a in node.names]
            if "PyQt6" in module or any("PyQt6" in n for n in names):
                offenders.append(f"line {node.lineno}: imports PyQt6")
        elif isinstance(node, ast.Name) and re.fullmatch(r"Q[A-Z]\w+", node.id):
            offenders.append(f"line {node.lineno}: references Qt type {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in {
            "mapToGlobal", "mapTo", "pos", "geometry", "rect", "width", "height",
            "isMaximized", "showMaximized", "showNormal", "setProperty",
        }:
            offenders.append(f"line {node.lineno}: calls Qt method .{node.attr}()")

    assert not offenders, (
        "the WM_NCHITTEST subclass proc reaches into Qt:\n  "
        + "\n  ".join(offenders)
        + "\nCache the geometry on the Qt side (refresh_chrome_rects) and read the "
          "plain dict instead; to make Qt act, PostMessage and handle it in the "
          "queued WM_APP_MAX_HOVER branch."
    )


def test_native_chrome_is_off_by_default():
    """The flag gates a native path that has not yet survived a chaos soak
    (RULE-EXP1).  The previously-verified frameless window stays the default until
    it has."""
    source = (REPO / "ui" / "dashboard.py").read_text(encoding="utf-8")
    match = re.search(r'"experimental/native_chrome",\s*(\w+)', source)
    assert match, "dashboard.py no longer reads the experimental/native_chrome flag"
    assert match.group(1) == "False", (
        "experimental/native_chrome defaults to True — it must stay opt-in until a "
        "clean multi-hour chaos soak has run with it on."
    )


def _find_function(source: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{name}() not found in ui/native_chrome.py")
