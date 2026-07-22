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
    should_reinstall_native_chrome,
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


def test_native_chrome_ships_to_every_windows_user():
    """Promoted in v2.1.30 after a clean chaos soak with the flag on (RULE-EXP1).

    The gate must be the PLATFORM, never a QSettings flag. Reintroducing a flag —
    even one defaulting to True — puts working Aero Snap back at the mercy of a
    stale stored value: the app never wrote the key, but dev machines and the
    Phase-3 probe scripts wrote an explicit `false`, and those users would silently
    keep the old unsnappable window on every future build.
    """
    source = (REPO / "ui" / "dashboard.py").read_text(encoding="utf-8")
    # Matches a QSettings read of the key, not a mere mention — the code comment
    # explaining why the flag was removed names it, and must stay allowed.
    assert not re.search(r'value\(\s*["\']experimental/native_chrome', source), (
        "dashboard.py reads an experimental/native_chrome flag again — the chrome was "
        "promoted to the default in v2.1.30 and the gate must stay platform-only, or "
        "anyone with a stale stored `false` never gets working snap."
    )
    assert re.search(r"_native_chrome\s*=\s*_sys_plat\.platform\s*==\s*[\"']win32[\"']", source), (
        "dashboard.py no longer gates the native chrome on sys.platform == 'win32'. "
        "Windows must always get it; non-Windows must always get the frameless path, "
        "which is the only implementation there."
    )


def test_geometry_is_reapplied_after_the_chrome_is_installed():
    """Regression: the window came up 32px low, a strip of desktop above the header.

    Two constraints collide, and both are load-bearing:

    1. The chrome can only be installed once the HWND exists — showEvent — and by
       then `_restore_settings()` has already placed the window against a frame that
       still had a real caption. WM_NCCALCSIZE then deletes that caption, leaving the
       window a caption-height out of place. The wrong rect is saved back on exit, so
       it sticks on every launch.
    2. Installing the chrome EARLIER does not fix it. Forcing the HWND to exist during
       construction (winId()) makes Qt re-push its stale creation-time geometry over
       the restored one — measured: the window collapsed to its 900x600 minimum,
       centred. That was tried and reverted; do not re-try it.

    So the chrome install must be followed by re-applying the saved rect, which is
    what reapply_geometry_after_chrome() does.
    """
    source = (REPO / "ui" / "header.py").read_text(encoding="utf-8")
    installer = _find_function(source, "_install_window_chrome")

    called = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(installer)
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert "reapply_geometry_after_chrome" in called, (
        "_install_window_chrome() installs the native chrome but never re-applies the "
        "saved geometry. WM_NCCALCSIZE changes the frame shape out from under a window "
        "that has already been positioned, so it ends up a caption-height (~32px) out "
        "and a strip of bare desktop shows above the header."
    )


def test_show_event_refreshes_chrome_rects_unconditionally():
    """Regression: minimize-to-tray then restore left the minimize button unclickable.

    changeEvent() calls _refresh_chrome_rects() on every WindowStateChange, including
    the one Qt fires mid-showNormal() while restoring a window that SystemTrayManager
    previously hid with a real .hide() (minimize-to-tray). At that exact point the
    header's child widgets still report isVisible() == False (the explicit-hidden flag
    hasn't cleared yet), so refresh_chrome_rects()'s isVisible() filter writes an EMPTY
    state["client"] — dropping every header button, including minimize, from the
    native hit-test cache. Nothing corrects it until something else forces a
    resizeEvent() (e.g. maximizing), which is why maximizing "fixes" the symptom.

    showEvent() only fires once the window is genuinely visible again, so a call to
    _refresh_chrome_rects() there is guaranteed correct — but it must be unconditional.
    _install_window_chrome() is a one-time no-op after the first show (gated by
    self._snap_subclass_installed), so nesting the refresh inside it would only ever
    fire on the very first show and never correct the tray-restore case.
    """
    source = (REPO / "ui" / "header.py").read_text(encoding="utf-8")
    show_event = _find_function(source, "showEvent")

    top_level_calls = {
        node.value.func.attr
        for node in show_event.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
    }
    assert "_refresh_chrome_rects" in top_level_calls, (
        "showEvent() no longer calls self._refresh_chrome_rects() unconditionally at "
        "its top level. Without it, restoring from the system tray (or any hide()-then-"
        "showNormal() path) leaves the native hit-test cache stale/empty until the next "
        "resize, making header buttons like minimize unclickable on the first click "
        "after restore."
    )


# ── WinIdChange reinstall (Network Map QWebEngineView recreates the HWND) ─────────

def test_reinstall_decision_fires_only_on_a_genuine_hwnd_change():
    """A QWebEngineView (Network Map) forces Qt to destroy and recreate the top-level
    HWND — see docs/spikes/webengine-hwnd-recreation.md. The WM_NCCALCSIZE subclass
    dies with the old handle, so Windows draws the real title bar above the header.
    The fix reinstalls the chrome on the new HWND; this is the decision that gates it.

    Reinstall ONLY when: native chrome is the active path, it was already installed
    once (prev_hwnd != 0), and the handle genuinely changed to a new non-zero HWND.
    """
    OLD, NEW = 1000, 2000
    assert should_reinstall_native_chrome(True, OLD, NEW) is True


def test_reinstall_decision_skips_the_first_winid_creation():
    """WinIdChange also fires when the window's HWND is first created — before the
    one-time install in showEvent has run. prev_hwnd is still 0 there, and the
    first-show path (_install_window_chrome) owns that install, so reinstall must not
    fire and race it."""
    assert should_reinstall_native_chrome(True, 0, 1234) is False


def test_reinstall_decision_skips_when_hwnd_unchanged():
    """No recreation, nothing to reinstall — and reinstalling on the same live HWND
    would needlessly re-subclass a window that is already correct."""
    assert should_reinstall_native_chrome(True, 5000, 5000) is False


def test_reinstall_decision_skips_a_zero_new_hwnd():
    """Defensive: a destroyed/not-yet-realised window reports winId 0; installing a
    subclass on it is meaningless."""
    assert should_reinstall_native_chrome(True, 5000, 0) is False


def test_reinstall_decision_off_on_non_windows_chrome():
    """The frameless (non-Windows) path has no WM_NCCALCSIZE subclass to lose, so a
    winId change there must never trigger the Win32-only reinstall."""
    assert should_reinstall_native_chrome(False, 1000, 2000) is False


def test_header_event_hook_reinstalls_chrome_on_winid_change():
    """AppHeaderMixin.event() must catch QEvent.WinIdChange and route to the reinstall
    path — that is the only cause-agnostic signal Qt gives us that the native handle
    changed (QWebEngineView today, any future native child / DPI rebuild tomorrow)."""
    source = (REPO / "ui" / "header.py").read_text(encoding="utf-8")
    event_fn = _find_function_in(source, "event")
    names = _names_and_attrs(event_fn)
    assert "WinIdChange" in names, (
        "AppHeaderMixin.event() does not reference QEvent.WinIdChange — the native "
        "title bar reappears permanently when Network Map builds its QWebEngineView, "
        "because nothing re-establishes the WM_NCCALCSIZE subclass on the new HWND."
    )


def test_reinstall_path_reinstalls_without_reapplying_saved_geometry():
    """The reinstall must call install_native_chrome on the new handle but must NOT
    call reapply_geometry_after_chrome: that reads the SAVED rect, which is correct
    only at first show. Mid-session the user may have moved/resized the window, so the
    reinstall has to keep the current rect and merely re-suppress the frame."""
    source = (REPO / "ui" / "native_chrome.py").read_text(encoding="utf-8")
    reinstall = _find_function_in(source, "reinstall_after_winid_change")
    called = _names_and_attrs(reinstall)
    assert "install_native_chrome" in called, (
        "_reinstall_chrome_after_winid_change() never calls install_native_chrome — "
        "the frame is not re-established on the recreated HWND."
    )
    assert "reapply_geometry_after_chrome" not in called, (
        "_reinstall_chrome_after_winid_change() calls reapply_geometry_after_chrome, "
        "which snaps the window back to the SAVED rect. Mid-session recreation must "
        "keep the window where the user left it — only re-suppress the frame."
    )


def test_network_map_marks_container_native_before_building_the_web_view():
    """Prevention layer: the web view's container must be made WA_NativeWindow BEFORE
    the QWebEngineView is constructed, so Qt hosts the view under an already-native
    ancestor instead of destroying and recreating the top-level window.

    Order is the whole point (docs/spikes/webengine-hwnd-recreation.md,
    strategy `container_late`): if the setAttribute runs AFTER the view is built the
    recreation has already happened and the window visibly flashes as if it restarted.
    """
    source = (REPO / "ui" / "pages" / "network_map_page.py").read_text(encoding="utf-8")
    fn = _find_function_in(source, "_try_init_webengine")

    native_attr_line = None
    web_view_line = None
    for node in ast.walk(fn):
        if (isinstance(node, ast.Attribute) and node.attr == "WA_NativeWindow"
                and native_attr_line is None):
            native_attr_line = node.lineno
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "QWebEngineView" and web_view_line is None):
            web_view_line = node.lineno

    assert native_attr_line is not None, (
        "_try_init_webengine() no longer marks the container WA_NativeWindow — the "
        "top-level window will be recreated when the QWebEngineView attaches, dropping "
        "the native chrome and flashing the whole window."
    )
    assert web_view_line is not None, "QWebEngineView construction not found"
    assert native_attr_line < web_view_line, (
        f"WA_NativeWindow is set on line {native_attr_line} but the QWebEngineView is "
        f"built on line {web_view_line}: the container must be native BEFORE the view "
        f"is created, or the recreation (and flash) has already happened."
    )


def _find_function_in(source: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{name}() not found")


def _names_and_attrs(fn: ast.AST) -> set:
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
    return out


def _find_function(source: str, name: str) -> ast.FunctionDef:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    # raise, not pytest.fail(): CodeQL does not know fail() is NoReturn, so it sees an
    # implicit `return None` here mixed with the explicit return above (py/mixed-returns).
    # pytest reports an AssertionError identically.
    raise AssertionError(f"{name}() not found in ui/native_chrome.py")
