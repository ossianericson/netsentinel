# Spike: WM_NCHITTEST snap-layout subclass crash (RULE-SPIKE1/2)

## Windows API / constraint involved

`ui/header.py::_install_snap_subclass()` installs a raw Win32 window subclass via
`comctl32.SetWindowSubclass`, with a ctypes `WINFUNCTYPE` callback (`_proc`) invoked
directly by Windows on every `WM_NCHITTEST`, `WM_NCLBUTTONDOWN`, and `WM_NCLBUTTONUP`
message over the frameless window's title bar. This is required so Windows 11 Snap
Layouts recognizes our custom maximize button (`HTMAXBUTTON` hit-test result) — without
it, Windows silently ignores the Snap flyout for frameless/custom-chrome windows.

## Known incompatibility with PyInstaller frozen exe

Not applicable here — `ctypes.windll` calls resolve identically in source and frozen
builds; this is not a PyInstaller-specific risk.

## PyQt6-specific constraints

The callback touches live Qt state (`QCursor.pos()`, `btn.mapToGlobal()`,
`btn.rect()`) from *inside* a reentrant native WNDPROC context — a call Windows makes
synchronously as part of its own message dispatch, not through Qt's event loop. This
is the same class of risk as `nativeEvent(WM_NCHITTEST)` (RULE-WIN2): reaching into
Qt/COM internals from a raw message hook while the main thread may simultaneously be
busy elsewhere (background QThread activity, a page-crossfade animation, etc.).

**A prior attempt used `nativeEvent()` directly and crashed with
`STATUS_ACCESS_VIOLATION`.** The current `SetWindowSubclass` approach was adopted as
"safer" (comment in `_install_snap_subclass`'s docstring) because the message ID
arrives as a plain C argument instead of requiring `MSG` struct pointer parsing.

## Proof-of-concept result: reproduced, still unsafe

Live reproduction (2026-07-03): launched the app from source, clicked **Update
Feeds** on the Threat Intel page (starts a background `QThread` doing network I/O),
then immediately navigated across several nav pages while the download was in
flight. This produced two fresh entries in `netsentinel_crash.log` within the same
session:

```
Windows fatal exception: code 0x8001010d   (RPC_E_CANTCALLOUT_ININPUTSYNCCALL)
Current thread ... ui\header.py, line 434/451, in _proc
```

Root cause: `_proc` had **no exception handling**. A ctypes `WINFUNCTYPE` callback
that lets a Python exception escape does not raise normally — it corrupts the C-level
return value the OS/comctl32 caller expects, which is undefined behavior at the
Win32 message-dispatch level. Under thread contention (background worker busy +
main-thread animation), a transient failure in the Qt geometry calls inside
`_over_maximize_btn()` (or any other path through `_proc`) had no safety net.

**Fix applied:** wrap `_proc`'s entire body — and `_over_maximize_btn()`
independently — in `try/except Exception`, always falling back to
`_DefSubclassProc` (or `0` as an absolute last resort) so no Python exception can
ever reach the ctypes/C boundary. This does not remove the reentrancy risk inherent
to touching Qt from a native callback, but it removes the specific failure mode
that was observed (an unhandled exception corrupting the callback's return value).

## Verdict

**Works, with the hardening applied.** The reentrant-callback pattern itself remains
inherently riskier than a pure win32/user32-only subclass (i.e., one that never
touches Qt objects), but a full rewrite to cache button geometry outside the
callback (updated only on resize/move) was assessed as a larger, separate change
and deferred — see "Follow-up" below.

## Follow-up (not done in this pass)

- Cache `_maximize_btn`'s screen rect on resize/move events instead of querying
  live Qt geometry (`mapToGlobal`) on every `WM_NCHITTEST`, which fires on every
  mouse move over the frame. This would remove the last remaining Qt-touching call
  from inside the native callback entirely.

---

## Root cause found (2026-07-13) — the window is not a real window

The hardening above treated a symptom. A live probe of the running app
(`Dashboard` built for real, maximize button clicked for real, then the **native**
window state read back via `GetWindowLongW` / `GetWindowPlacement` / `IsZoomed`)
shows what Windows actually believes about our window:

```
--- BEFORE maximize ---
  GWL_STYLE      = 0x96000000
  styles present = ['WS_POPUP']
  styles MISSING = ['WS_CAPTION', 'WS_SYSMENU', 'WS_THICKFRAME',
                    'WS_MINIMIZEBOX', 'WS_MAXIMIZEBOX', 'WS_MAXIMIZE']
  showCmd        = 1 (SW_SHOWNORMAL)
  IsZoomed()     = False

[qt] isMaximized() = True          <-- Qt says maximized
[qt] geometry      = (0, 0, 3440, 1392)

--- AFTER maximize (Qt says isMaximized=True) ---
  GWL_STYLE      = 0x96000000      <-- unchanged
  styles present = ['WS_POPUP']
  showCmd        = 1 (SW_SHOWNORMAL)   <-- NOT SW_SHOWMAXIMIZED
  IsZoomed()     = False               <-- Windows: "not maximized"
```

`Qt.FramelessWindowHint` (`ui/dashboard.py:109`) produces a bare **`WS_POPUP`**
window with **no `WS_CAPTION` and no `WS_SYSMENU`**. Qt then implements
"maximized" for it by *resizing the popup to the work area* — it never calls
`ShowWindow(SW_MAXIMIZE)`, so the native window is never in the zoomed state.

**This is the real mechanism behind the 0x8001010d fault.**
`_install_snap_subclass()` adds back only `WS_THICKFRAME | WS_MAXIMIZEBOX`
(`ui/header.py`), and then returns **`HTMAXBUTTON`** from `WM_NCHITTEST` — i.e. it
tells Windows *"the cursor is over a **caption button**"* on a window that **has no
caption**. Snap Layouts is caption-button machinery; we invoke it against a
captionless `WS_POPUP`. The COM/RPC reentrancy fault is that invalid state
surfacing when it happens inside an input-synchronous `SendMessage`.

No amount of hardening the callback can fix this — the callback is not the bug.
The *window* is malformed. This also explains, structurally, why Aero Snap,
drag-to-edge, `Win`+arrow, and shake have never worked: none of them exist for a
`WS_POPUP` with no caption and no maximize box.

### Consequence for the fix

The correct fix is the standard custom-chrome architecture used by VS Code /
Electron, Windows Terminal and Chrome: **keep a real Windows window and merely
stop Windows from painting the frame**, rather than deleting the frame and lying
to DWM about it.

- Drop `FramelessWindowHint`; keep `WS_CAPTION | WS_SYSMENU | WS_THICKFRAME |
  WS_MINIMIZEBOX | WS_MAXIMIZEBOX`.
- Handle **`WM_NCCALCSIZE`** (wParam=TRUE → return 0) so the client area covers the
  whole window: the title bar and frame stop being *drawn* while every native
  behaviour they carry is preserved.
- Then `HTMAXBUTTON` is legitimate (the window really does have a caption), and
  `HTCAPTION` over the header gives native drag ⇒ Aero Snap, shake, drag-to-top,
  Alt+Space, double-click — for free.
- Handle the full NC message set, never a partial one (RULE-WIN2).
- Keep the native callback free of *all* Qt calls: cache the button rect on
  resize/move, use `GetCursorPos` rather than `QCursor.pos()`. A ctypes callback
  that blocks on the GIL inside a synchronous `SendMessage` is its own route to
  `IsHungAppWindow`.

Tracked as Phase 3; gate behind `experimental/native_chrome` (RULE-EXP1) and
promote only after a clean multi-hour chaos soak with the flag on.

---

## Phase 3 implemented (2026-07-13) — `ui/native_chrome.py`, flag OFF by default

Built exactly as prescribed above. `ui/native_chrome.py` splits in two so the risky
half is testable: **pure functions** (`client_rect_for_nccalcsize`, `client_origin`,
`hit_test`, `lparam_point`) take plain ints and hold every decision that can be
wrong; the ctypes callback is a thin shell around them. The callback touches **zero
Qt objects** — it reads a plain dict the Qt side refills on resize, takes the cursor
straight from `lParam`, and when it needs Qt to act it *posts* a message
(`WM_SYSCOMMAND`/`SC_MAXIMIZE` for the click, `WM_APP_MAX_HOVER` for the hover) so
the work lands on Qt's own event loop, out of the input-synchronous context.

### Measured on the live window (the same probe that found the root cause)

Constructing a real `Dashboard` with the flag on, then reading back what *Windows*
believes, and driving the real callback with real `SendMessage(WM_NCHITTEST)` calls:

```
                       flag OFF (shipped)          flag ON (Phase 3)
styles present         ['WS_POPUP']                WS_POPUP, WS_CAPTION, WS_SYSMENU,
                                                   WS_THICKFRAME, WS_MIN/MAXIMIZEBOX
styles MISSING         WS_CAPTION, WS_SYSMENU,     — none —
                       WS_THICKFRAME, WS_MIN/MAX
after showMaximized()
  Qt isMaximized()     True                        True
  showCmd              1 (SW_SHOWNORMAL)           3 (SW_SHOWMAXIMIZED)
  IsZoomed()           False                       True
```

`showCmd == 3` / `IsZoomed() == True` is the whole point: **Windows now agrees the
window is maximized.** `HTMAXBUTTON` is therefore a true statement about a
caption-bearing window, not the RULE-WIN9 lie. Every hit-test came back as designed
through the real callback: maximize button → `HTMAXBUTTON`, empty header →
`HTCAPTION`, close/minimize/Scan → `HTCLIENT` (still Qt-clickable), edges →
`HTLEFT`/`HTTOP`/`HTTOPLEFT`.

### One bug the probe caught that the design did not predict

Microsoft's own custom-title-bar sample insets a **maximized** window's client top by
`padding` alone. Measured, that lands the client origin at `(0, -4)` on a 3440x1440
display: the header's top 4px sits off the top of the screen, with a matching 8px
dead strip above the taskbar. Windows inflates a maximized window by the **full**
frame (`frame + padding`) on *every* side, so when zoomed the top takes the same
inset as the other three — there is no caption to reclaim in that state. With
`top += frame_y + padding` the client lands on the work area exactly (`(0, 0)`,
3440x1392). Locked in by
`test_nccalcsize_maximized_client_is_exactly_the_work_area`.

### `WS_POPUP` is NOT the tell — do not read this doc that way

Qt sets **`WS_POPUP` on every top-level window on Windows**, including a plain,
fully-decorated `QMainWindow` that snaps perfectly well. Measured, four variants:

```
default QMainWindow (no setWindowFlags)      popup=YES  + CAPTION SYSMENU THICKFRAME MIN/MAXBOX
Qt.Window                                    popup=YES  + CAPTION SYSMENU THICKFRAME MIN/MAXBOX
Qt.Window | Title | SysMenu | MinMax | Close  popup=YES  + CAPTION SYSMENU THICKFRAME MIN/MAXBOX
FramelessWindowHint | Window                 popup=YES  (and NOTHING else)
```

So the presence of `WS_POPUP` proves nothing, and "the window is a `WS_POPUP`" is the
wrong summary of the root cause. What actually broke snap was the **missing** bits —
no `WS_CAPTION`, no `WS_SYSMENU`, no `WS_THICKFRAME`, no maximize box. Chasing the
popup bit costs a wasted fix: it is present in the working configuration too.

### Verified working (2026-07-13), flag ON, by synthesising the real hotkeys

Driving Win+arrow through the OS (`keybd_event`) against a real `Dashboard` and
reading back `GetWindowRect` / `IsZoomed`, on a 3440x1392 work area:

```
restored     -> Win+Left -> (-7, 0, 1727, 1399)   left half        ✅
restored     -> Win+Up   -> IsZoomed() == True    maximized        ✅
left-snapped -> Win+Up   -> 1734x703              top-left quadrant ✅ (correct Win11 gesture)
```

The window snaps like any normal Windows application. Note when testing by hand that
the flag is read once in `Dashboard.__init__` — **the app must be restarted after
setting it**, and a window that "does nothing" on Win+arrow is the signature of the
flag being off, not of a broken hook.

### Known limitation (accepted, flag-gated)

An **auto-hide taskbar** may not reveal when the window is maximized: the work area
then spans the full screen, so the maximized client reaches the screen edge and
Windows has no sliver left to trigger the reveal. The usual remedy is a 1px inset on
the auto-hide edge. Not implemented — revisit if the soak or a user hits it.

### Still to do before this can be the default

1. A clean multi-hour chaos soak **with the flag on** (RULE-CHAOS1 — the user runs
   it, not the agent). The chaos net now actually reaches this surface: window-chrome
   actions including `Win+Z` (Snap Layouts) run at every chaos level, and a
   crash-log watcher fails a run on any new `netsentinel_crash.log` entry — the only
   record a native SEH fault like `0x8001010d` leaves.
2. Only then: flip the default, and delete the 8 `_Grip` widgets, the manual
   `move()` drag in `_DragHeader`, and `install_snap_subclass()` — all three exist
   only to compensate for a window that was never real.

### Why this went unnoticed for so long

`tools/monkey_test.py` could not have caught any of it: the window chrome was
blacklisted (`_BLACKLIST`) *and* every `Button` in the top 60px of the window was
spatially excluded in `_enabled_controls()`. Not one chaos iteration in the
project's history ever clicked the maximize button. Both exclusions are now
removed (close/minimize remain, for app-lifecycle reasons only), window-chrome
chaos actions were added — including `Win+Z`, the Snap-Layouts flyout that
triggers this fault — and a crash-log watcher now fails a run on any *new*
`netsentinel_crash.log` entry, since `faulthandler` is the only thing that records
a native SEH fault like `0x8001010d`. Locked in by
`tests/test_monkey_chrome_coverage.py`.
