"""
native_chrome.py — real-Windows-window custom chrome (``experimental/native_chrome``).

WHY THIS EXISTS
---------------
``Qt.FramelessWindowHint`` does not produce "a normal window without decoration" —
it produces a bare ``WS_POPUP`` with no ``WS_CAPTION``, no ``WS_SYSMENU``, no
``WS_THICKFRAME`` and no maximize box (measured on the live window; see
``docs/spikes/window-snap-subclass.md``).  Windows therefore never regards it as a
maximizable, snappable, caption-bearing window: even after ``showMaximized()``,
``GetWindowPlacement().showCmd`` is still ``SW_SHOWNORMAL`` and ``IsZoomed()`` is
still ``False``, because Qt fakes "maximized" by resizing the popup to the work
area.  Answering ``WM_NCHITTEST`` with ``HTMAXBUTTON`` there claims a capability the
style does not carry — it points DWM's caption-button / Snap-Layouts machinery at a
window that has no caption — and that invalid state is the ``0x8001010d``
(``RPC_E_CANTCALLOUT_ININPUTSYNCCALL``) SEH fault (RULE-WIN9).  It is also why
Aero Snap, drag-to-edge, Win+arrow and shake have never worked.

This module does the opposite, and it is what VS Code/Electron, Windows Terminal and
Chrome all do: **keep a real window and merely stop Windows painting the frame.**
The window keeps ``WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MIN/MAXIMIZEBOX``;
``WM_NCCALCSIZE`` trims the non-client area away so the client area covers the title
bar.  The frame stops being *drawn*, while every native behaviour it carries
survives:

===========================  ==================================================
``HTCAPTION`` over header    native drag, Aero Snap, drag-to-edge, shake,
                             double-click-to-maximize, Alt+Space
``HTMAXBUTTON`` over our     the Windows 11 Snap Layouts flyout — legitimate now,
maximize button              because the window really does have a caption
``HTLEFT``/``HTTOP``/...     native resize on every edge and corner
===========================  ==================================================

LAYOUT
------
1. **Pure functions** (:func:`client_rect_for_nccalcsize`, :func:`client_origin`,
   :func:`hit_test`, :func:`lparam_point`) — plain ints, no Qt, no ctypes.  Every
   piece of logic that can be *wrong* lives here, where tests can reach it without a
   window (RULE-TP4-DASH forbids constructing a Dashboard in-process).
2. **The Win32 shell** — the subclass procedure and its installer.

THE SUBCLASS PROCEDURE TOUCHES ZERO QT OBJECTS (RULE-WIN9 corollary).  Windows calls
it synchronously and reentrantly from inside its own ``SendMessage`` dispatch; a
ctypes callback that calls into Qt there — or that blocks acquiring the GIL — is its
own route to ``IsHungAppWindow``.  It reads one plain ``dict`` that the Qt side
refills on resize, and answers with pure user32 calls.  When it needs the Qt side to
act (maximize, hover repaint) it **posts** a message: ``PostMessage`` returns
immediately and the work runs later on Qt's own event loop, out of the
input-synchronous context.  ``WM_APP_MAX_HOVER`` below is the one sanctioned place
Qt is touched, and it is only ever reached through the posted-message queue.
"""
from __future__ import annotations

import sys

# ── Win32 constants ─────────────────────────────────────────────────────────────
WM_NCCALCSIZE    = 0x0083
WM_NCHITTEST     = 0x0084
WM_NCMOUSEMOVE   = 0x00A0
WM_NCLBUTTONDOWN = 0x00A1
WM_NCLBUTTONUP   = 0x00A2
WM_NCMOUSELEAVE  = 0x02A2
WM_SYSCOMMAND    = 0x0112
WM_APP_MAX_HOVER = 0x8000 + 0x21   # WM_APP + 0x21 — our own posted message

SC_MAXIMIZE = 0xF030
SC_RESTORE  = 0xF120

HTCLIENT      = 1
HTCAPTION     = 2
HTMAXBUTTON   = 9
HTLEFT        = 10
HTRIGHT       = 11
HTTOP         = 12
HTTOPLEFT     = 13
HTTOPRIGHT    = 14
HTBOTTOM      = 15
HTBOTTOMLEFT  = 16
HTBOTTOMRIGHT = 17

#: RULE-WIN2 — a partial NC implementation is what crashes.  Claiming HTMAXBUTTON
#: without also owning the button's mouse messages leaves Windows half-driving a
#: caption button we draw ourselves.  Every message here must stay handled; the
#: completeness of this set is asserted by tests/test_native_chrome.py.
HANDLED_NC_MESSAGES = frozenset({
    WM_NCCALCSIZE,
    WM_NCHITTEST,
    WM_NCMOUSEMOVE,
    WM_NCLBUTTONDOWN,
    WM_NCLBUTTONUP,
    WM_NCMOUSELEAVE,
})

#: Hit results Windows already resolved correctly from the (still present) frame —
#: we pass these straight back rather than second-guessing them.
NATIVE_BORDER_HITS = frozenset({
    HTLEFT, HTRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT,
    HTTOP, HTTOPLEFT, HTTOPRIGHT,
})

SM_CXFRAME        = 32
SM_CYFRAME        = 33
SM_CXPADDEDBORDER = 92

GWL_STYLE      = -16
WS_CAPTION     = 0x00C00000
WS_SYSMENU     = 0x00080000
WS_THICKFRAME  = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000

_SUBCLASS_ID_NATIVE = 2   # 1 is the legacy snap hook — never collide
_SUBCLASS_ID_SNAP   = 1


# ══════════════════════════════════════════════════════════════════════════════
# Pure functions — plain ints in, plain ints out.  No Qt, no ctypes, no globals.
# ══════════════════════════════════════════════════════════════════════════════

def client_rect_for_nccalcsize(
    rect: tuple[int, int, int, int],
    frame_x: int,
    frame_y: int,
    padding: int,
    is_maximized: bool,
) -> tuple[int, int, int, int]:
    """Shrink the proposed window rect into the client rect we actually want.

    Left/right/bottom keep their resize borders in the non-client area — that is
    what buys native edge-resize for free.  Only the **top** is reclaimed: pulling
    the client up over the caption is what makes the title bar stop being drawn.

    The ``is_maximized`` branch is not cosmetic, and it is not the same inset.
    Windows sizes a maximized window to the work area *inflated by the full frame on
    every side*, expecting the standard ``WM_NCCALCSIZE`` to hand that inflation
    back.  So when zoomed there is no caption to reclaim — the top takes the same
    inset as the other three sides, and the client lands on the work area exactly.
    Reclaiming the top there instead (or insetting by ``padding`` alone, which is
    what Microsoft's own custom-title-bar sample does) pushes the header off the top
    of the screen and leaves a dead strip above the taskbar — measured, not guessed:
    client origin came back as (0, -4) on a 3440x1440 display.
    """
    left, top, right, bottom = rect
    left += frame_x + padding
    right -= frame_x + padding
    bottom -= frame_y + padding
    if is_maximized:
        top += frame_y + padding
    return (left, top, right, bottom)


def client_origin(
    win_rect: tuple[int, int, int, int],
    frame_x: int,
    frame_y: int,
    padding: int,
    is_maximized: bool,
) -> tuple[int, int]:
    """Screen coords of client (0, 0). Must track :func:`client_rect_for_nccalcsize`.

    Cached widget rects are stored *client-relative*, so they survive a window move
    without a refresh; this converts a screen-space cursor into that space.
    """
    left, top, _right, _bottom = win_rect
    return (left + frame_x + padding,
            top + (frame_y + padding if is_maximized else 0))


def _contains(rect: tuple[int, int, int, int], x: int, y: int) -> bool:
    left, top, right, bottom = rect
    return left <= x < right and top <= y < bottom


def hit_test(
    x: int,
    y: int,
    win_rect: tuple[int, int, int, int],
    origin: tuple[int, int],
    header_rect: tuple[int, int, int, int],
    max_btn_rect: tuple[int, int, int, int],
    client_rects: "tuple[tuple[int, int, int, int], ...]",
    frame_x: int,
    frame_y: int,
    is_maximized: bool,
    default_hit: int,
) -> int:
    """Answer ``WM_NCHITTEST``.  ``x``/``y`` are screen coords; rects are client-relative.

    ``default_hit`` is what ``DefSubclassProc`` said — it already resolves the
    left/right/bottom borders correctly, so we only override where we must.

    Order matters: the top band is tested *before* the passthrough, because at the
    top corners Windows reports plain ``HTLEFT``/``HTRIGHT`` (its own frame still
    spans the full height), which would cost the user diagonal corner resize.
    """
    win_left, win_top, win_right, _win_bottom = win_rect

    # 1. Top border — after WM_NCCALCSIZE there is no non-client area up here at
    #    all, so Windows cannot resolve it and we must synthesize it ourselves.
    if not is_maximized and win_top <= y < win_top + frame_y:
        if x < win_left + frame_x:
            return HTTOPLEFT
        if x >= win_right - frame_x:
            return HTTOPRIGHT
        return HTTOP

    # 2. Borders Windows already got right.
    if default_hit in NATIVE_BORDER_HITS:
        return default_hit

    cx = x - origin[0]
    cy = y - origin[1]

    # 3. Our maximize button — the one place HTMAXBUTTON is legitimate, and the
    #    only way Windows offers the Snap Layouts flyout.
    if _contains(max_btn_rect, cx, cy):
        return HTMAXBUTTON

    # 4. Every other interactive header widget stays client, so Qt keeps handling
    #    its hover and clicks normally (gear, time range, Scan, minimize, close).
    for rect in client_rects:
        if _contains(rect, cx, cy):
            return HTCLIENT

    # 5. The rest of the header is the caption: native drag, snap, shake, Alt+Space.
    if _contains(header_rect, cx, cy):
        return HTCAPTION

    return default_hit


def lparam_point(lparam: int) -> tuple[int, int]:
    """Extract the signed screen coords Windows packs into a ``WM_NCHITTEST`` lParam.

    The halves are signed 16-bit: a window on a monitor left of the primary has
    negative x, and reading them unsigned puts the cursor 65536 px away.
    """
    x = lparam & 0xFFFF
    y = (lparam >> 16) & 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    if y >= 0x8000:
        y -= 0x10000
    return (x, y)


def should_reinstall_native_chrome(
    native_chrome: bool, prev_hwnd: int, new_hwnd: int
) -> bool:
    """Decide whether a ``WinIdChange`` warrants reinstalling the chrome subclass.

    The subclass is bound to a specific ``HWND``.  When Qt embeds a native-backed
    child — the first ``QWebEngineView`` on the Network Map page — it recreates the
    top-level window to host it, and the ``WM_NCCALCSIZE`` subclass dies with the old
    handle, so Windows draws the real title bar again
    (``docs/spikes/webengine-hwnd-recreation.md``).  ``QEvent.WinIdChange`` is the one
    cause-agnostic signal Qt gives us that this happened; reacting to it survives any
    future recreation trigger, not just ``QWebEngineView``.

    Reinstall only when all three hold, or we either race the first-show install or
    needlessly re-subclass a window that is already correct:

    * ``native_chrome`` — the Win32 path is active (the frameless path has no subclass
      to lose);
    * ``prev_hwnd`` is non-zero — the one-time install already ran, so this is a
      *re*-creation, not the window's first ``WinIdChange`` during initial show;
    * ``new_hwnd`` is a *different*, non-zero handle — an actual recreation.
    """
    return bool(native_chrome and prev_hwnd and new_hwnd and new_hwnd != prev_hwnd)


# ══════════════════════════════════════════════════════════════════════════════
# Win32 shell
# ══════════════════════════════════════════════════════════════════════════════

def _frame_metrics(hwnd: int, user32) -> tuple[int, int, int]:
    """(frame_x, frame_y, padding) for this window's *current* DPI.

    Read live rather than cached: WM_NCCALCSIZE arrives immediately after
    WM_DPICHANGED, so a cache refreshed from the Qt side would be one frame stale
    exactly when the numbers change.
    """
    dpi = 0
    try:
        dpi = int(user32.GetDpiForWindow(hwnd))   # Win10 1607+
    except (AttributeError, OSError):
        dpi = 0  # pre-1607 — fall back to the system-wide metrics below
    if dpi:
        get = user32.GetSystemMetricsForDpi
        return (int(get(SM_CXFRAME, dpi)),
                int(get(SM_CYFRAME, dpi)),
                int(get(SM_CXPADDEDBORDER, dpi)))
    get = user32.GetSystemMetrics
    return (int(get(SM_CXFRAME)), int(get(SM_CYFRAME)), int(get(SM_CXPADDEDBORDER)))


def _make_subclass_proc(state: dict, def_proc, user32, rect_cls, track_leave):
    """Build the SUBCLASSPROC body.  Nothing in here may touch a Qt object.

    ``state`` is a plain dict the Qt side refills — reading it is a dict lookup, not
    a C++ dispatch into Qt.  Every escape back to Qt goes through PostMessage.
    """
    import ctypes

    def _proc(hwnd, msg, wparam, lparam, uid, ref):
        # A Python exception must never escape a ctypes callback: it does not
        # propagate as a normal error, it corrupts the C-level return value
        # Windows is waiting on — undefined behaviour inside message dispatch.
        try:
            if msg == WM_NCCALCSIZE:
                if not wparam:
                    return def_proc(hwnd, msg, wparam, lparam)
                frame_x, frame_y, padding = _frame_metrics(hwnd, user32)
                # lParam -> NCCALCSIZE_PARAMS, whose first field is rgrc[0].
                rect = ctypes.cast(lparam, ctypes.POINTER(rect_cls)).contents
                rect.left, rect.top, rect.right, rect.bottom = client_rect_for_nccalcsize(
                    (rect.left, rect.top, rect.right, rect.bottom),
                    frame_x, frame_y, padding, bool(user32.IsZoomed(hwnd)),
                )
                return 0

            if msg == WM_NCHITTEST:
                default_hit = def_proc(hwnd, msg, wparam, lparam)
                win_rect = _window_rect(hwnd, user32, rect_cls)
                if win_rect is None:
                    return default_hit
                frame_x, frame_y, padding = _frame_metrics(hwnd, user32)
                zoomed = bool(user32.IsZoomed(hwnd))
                x, y = lparam_point(lparam)
                hit = hit_test(
                    x, y, win_rect,
                    client_origin(win_rect, frame_x, frame_y, padding, zoomed),
                    state["header"], state["max_btn"], state["client"],
                    frame_x, frame_y, zoomed, int(default_hit),
                )
                _sync_hover(hwnd, state, user32, track_leave, hit == HTMAXBUTTON)
                return hit

            if msg == WM_NCMOUSELEAVE:
                _sync_hover(hwnd, state, user32, track_leave, False)
                return def_proc(hwnd, msg, wparam, lparam)

            if wparam == HTMAXBUTTON:
                # RULE-WIN2: owning HTMAXBUTTON means owning its mouse messages
                # too. Windows cannot paint a caption button on a window whose
                # caption it no longer draws, so we swallow these and drive the
                # visuals (hover) and the action (release) ourselves.
                if msg == WM_NCMOUSEMOVE:
                    return 0
                if msg == WM_NCLBUTTONDOWN:
                    return 0   # act on the release, like a real caption button
                if msg == WM_NCLBUTTONUP:
                    command = SC_RESTORE if user32.IsZoomed(hwnd) else SC_MAXIMIZE
                    # Posted, not called: Windows performs the maximize itself on
                    # its own event loop, so no Qt object is touched from inside
                    # this input-synchronous callback.  Qt sees the resulting
                    # state change and swaps the glyph in changeEvent().
                    user32.PostMessageW(hwnd, WM_SYSCOMMAND, command, 0)
                    return 0

            if msg == WM_APP_MAX_HOVER:
                # Queued context — this message was POSTED, so we are on Qt's own
                # event loop now, not inside a SendMessage.  The one place it is
                # safe to reach back into Qt.
                callback = state.get("on_hover")
                if callback is not None:
                    callback(bool(wparam))
                return 0

            return def_proc(hwnd, msg, wparam, lparam)
        except Exception:
            try:
                return def_proc(hwnd, msg, wparam, lparam)
            except Exception:
                return 0   # must return an int — never raise past the C boundary

    return _proc


def _window_rect(hwnd: int, user32, rect_cls):
    rect = rect_cls()
    import ctypes
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top, rect.right, rect.bottom)


def _sync_hover(hwnd: int, state: dict, user32, track_leave, over: bool) -> None:
    """Post a hover change for the maximize button, once per transition.

    The button sits in the non-client area now, so Qt never sees a mouse event for
    it and its ``:hover`` rule can never fire — without this it would be the one
    dead-looking button in the header.
    """
    if bool(state.get("max_hover")) == over:
        return
    state["max_hover"] = over
    if over:
        track_leave(hwnd)   # so we still clear if the cursor leaves the window
    user32.PostMessageW(hwnd, WM_APP_MAX_HOVER, 1 if over else 0, 0)


def _make_leave_tracker(user32):
    import ctypes
    import ctypes.wintypes as wintypes

    class _TRACKMOUSEEVENT(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("hwndTrack", wintypes.HWND),
            ("dwHoverTime", wintypes.DWORD),
        ]

    TME_LEAVE     = 0x00000002
    TME_NONCLIENT = 0x00000010

    def _track(hwnd: int) -> None:
        event = _TRACKMOUSEEVENT()
        event.cbSize = ctypes.sizeof(_TRACKMOUSEEVENT)
        event.dwFlags = TME_LEAVE | TME_NONCLIENT
        event.hwndTrack = hwnd
        event.dwHoverTime = 0
        user32.TrackMouseEvent(ctypes.byref(event))

    return _track


def _make_hover_callback(win):
    """Qt-side half of the hover. Runs only from the posted WM_APP_MAX_HOVER."""
    def _on_hover(over: bool) -> None:
        button = getattr(win, "_maximize_btn", None)
        if button is None:
            return
        try:
            button.setProperty("ncHover", "true" if over else "false")
            style = button.style()
            style.unpolish(button)
            style.polish(button)
        except RuntimeError:
            pass  # non-fatal — button already torn down during shutdown
    return _on_hover


def refresh_chrome_rects(win) -> None:
    """Recache the header/button rects the hit-test reads.  Qt side, never the callback.

    Rects are stored **client-relative**, so a window *move* cannot invalidate them —
    only a resize or a maximize/restore can, which is exactly when this is called.
    """
    state = getattr(win, "_nc_state", None)
    if state is None:
        return
    header = getattr(win, "_app_header", None)
    button = getattr(win, "_maximize_btn", None)
    if header is None or button is None:
        return
    from PyQt6.QtCore import QPoint

    def _rect_of(widget) -> tuple[int, int, int, int]:
        top_left = widget.mapTo(win, QPoint(0, 0))
        return (top_left.x(), top_left.y(),
                top_left.x() + widget.width(), top_left.y() + widget.height())

    try:
        state["header"] = _rect_of(header)
        state["max_btn"] = _rect_of(button)
        state["client"] = tuple(
            _rect_of(widget)
            for widget in getattr(win, "_header_nc_client_widgets", ())
            if widget is not None and widget.isVisible()
        )
    except RuntimeError:
        pass  # non-fatal — a widget was destroyed mid-teardown


def install_native_chrome(win) -> bool:
    """Turn ``win`` into a real Windows window whose frame simply is not painted.

    Returns True when the subclass is live.  Callers keep the legacy frameless path
    on False, so a failure here degrades rather than breaks.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        class _RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                        ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        user32 = ctypes.windll.user32
        comctl32 = ctypes.windll.comctl32

        def_proc = comctl32.DefSubclassProc
        def_proc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        def_proc.restype = ctypes.c_ssize_t

        SUBCLASSPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            ctypes.c_size_t, ctypes.c_size_t,
        )

        state: dict = {
            "header": (0, 0, 0, 0),
            "max_btn": (0, 0, 0, 0),
            "client": (),
            "max_hover": False,
            "on_hover": _make_hover_callback(win),
        }
        win._nc_state = state

        proc = SUBCLASSPROC(
            _make_subclass_proc(state, def_proc, user32, _RECT, _make_leave_tracker(user32))
        )
        # Held on the window: a ctypes callback that gets garbage-collected while
        # Windows still holds the function pointer is a use-after-free.
        win._nc_subclass_proc = proc

        hwnd = int(win.winId())

        get_long = user32.GetWindowLongW
        set_long = user32.SetWindowLongW
        get_long.argtypes = [wintypes.HWND, ctypes.c_int]
        get_long.restype = ctypes.c_long
        set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        set_long.restype = ctypes.c_long

        # Belt and braces: without FramelessWindowHint Qt already gives us these,
        # but the whole point of RULE-WIN9 is to never *assume* the style carries a
        # capability we are about to claim.
        style = get_long(hwnd, GWL_STYLE)
        set_long(hwnd, GWL_STYLE, style | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME
                 | WS_MINIMIZEBOX | WS_MAXIMIZEBOX)

        set_subclass = comctl32.SetWindowSubclass
        set_subclass.argtypes = [wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
        set_subclass.restype = wintypes.BOOL
        if not set_subclass(hwnd, proc, _SUBCLASS_ID_NATIVE, 0):
            return False

        refresh_chrome_rects(win)

        # SWP_FRAMECHANGED forces the WM_NCCALCSIZE that applies all of the above.
        SWP_FLAGS = 0x0027   # NOMOVE | NOSIZE | NOZORDER | FRAMECHANGED
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)
        return True
    except Exception:
        return False   # non-fatal — caller stays on the legacy frameless window


def reinstall_after_winid_change(win) -> None:
    """Re-establish the chrome subclass after Qt recreated the window's HWND.

    Called from ``AppHeaderMixin.event()`` on ``QEvent.WinIdChange`` — Qt destroys and
    recreates the top-level HWND to host a native child (Network Map's
    ``QWebEngineView``), and the ``WM_NCCALCSIZE`` subclass dies with the old handle.
    This reinstalls it on the new one but NEVER re-applies saved geometry (that is
    correct only at first show; mid-session the window must stay where the user has
    it) — ``install_native_chrome`` merely re-subclasses and re-suppresses the frame.
    ``win._last_native_hwnd`` gates it to a genuine recreation.
    See ``docs/spikes/webengine-hwnd-recreation.md``.
    """
    new_hwnd = int(win.winId())
    if not should_reinstall_native_chrome(
        getattr(win, "_native_chrome", False),
        getattr(win, "_last_native_hwnd", 0),
        new_hwnd,
    ):
        return
    if install_native_chrome(win):
        win._last_native_hwnd = new_hwnd


def install_snap_subclass(win) -> None:
    """LEGACY (``experimental/snap_layout_hover``) — the frameless HTMAXBUTTON hook.

    Kept byte-for-byte so the previously-shipped path is unchanged, but understand
    what it is: it returns HTMAXBUTTON on a captionless WS_POPUP, which is the
    RULE-WIN9 fault itself.  It is off by default and ``native_chrome`` is its
    replacement, not its fix.
    """
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        _DefSubclassProc = ctypes.windll.comctl32.DefSubclassProc
        _DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        _DefSubclassProc.restype = ctypes.c_ssize_t

        SUBCLASSPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
            ctypes.c_size_t, ctypes.c_size_t,
        )

        def _over_maximize_btn():
            try:
                btn = win._maximize_btn
                if btn is None:
                    return False
                from PyQt6.QtGui import QCursor
                p = QCursor.pos()
                tl = btn.mapToGlobal(btn.rect().topLeft())
                return (tl.x() <= p.x() < tl.x() + btn.width() and
                        tl.y() <= p.y() < tl.y() + btn.height())
            except Exception:
                return False  # non-fatal — treat as "not over the button"

        def _proc(hwnd, msg, wparam, lparam, uid, ref):
            try:
                if msg == WM_NCHITTEST and _over_maximize_btn():
                    return HTMAXBUTTON
                if wparam == HTMAXBUTTON:
                    if msg == WM_NCLBUTTONDOWN:
                        return 0  # swallow — we act on release
                    if msg == WM_NCLBUTTONUP:
                        from PyQt6.QtCore import QTimer as _QTimer
                        _t = _QTimer(win)
                        _t.setSingleShot(True)
                        _t.timeout.connect(win._toggle_maximize)
                        _t.start(0)
                        return 0
                return _DefSubclassProc(hwnd, msg, wparam, lparam)
            except Exception:
                try:
                    return _DefSubclassProc(hwnd, msg, wparam, lparam)
                except Exception:
                    return 0  # last-resort — must return an int, never raise

        win._snap_subclass_proc = SUBCLASSPROC(_proc)
        hwnd = int(win.winId())

        _GetWindowLong = ctypes.windll.user32.GetWindowLongW
        _SetWindowLong = ctypes.windll.user32.SetWindowLongW
        _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
        _GetWindowLong.restype = ctypes.c_long
        _SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        _SetWindowLong.restype = ctypes.c_long
        style = _GetWindowLong(hwnd, GWL_STYLE)
        _SetWindowLong(hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_MAXIMIZEBOX)
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

        _SetWindowSubclass = ctypes.windll.comctl32.SetWindowSubclass
        _SetWindowSubclass.argtypes = [wintypes.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
        _SetWindowSubclass.restype = wintypes.BOOL
        _SetWindowSubclass(hwnd, win._snap_subclass_proc, _SUBCLASS_ID_SNAP, 0)
    except Exception:
        pass  # non-fatal — the maximize button still works, just no Snap flyout
