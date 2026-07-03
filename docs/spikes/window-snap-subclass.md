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
