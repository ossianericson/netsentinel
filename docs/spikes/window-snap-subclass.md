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
