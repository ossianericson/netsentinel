# Spike: black/white window after minimize -> restore (native chrome)

**Status:** RESOLVED 2026-07-23 (RULE-WIN14). Root cause was NOT a repaint failure and
NOT native-chrome subclass loss — it was a Qt QWidget visibility desync. See "Resolution"
at the bottom; the "Next step" repaint theory above it is superseded and kept only as
investigation history.
**Date:** 2026-07-23
**Trigger for this investigation:** user stopped a wild-chaos monkey run
(`test_output/wild_soak_only/`, 2026-07-23 17:34-17:37) because the app window went
100% black, with only the Ctrl+K command palette overlay still rendering on top.

## 1. What Windows API / constraint is involved

`ui/native_chrome.py`'s custom window (real `WS_CAPTION | WS_SYSMENU | WS_THICKFRAME`,
`WM_NCCALCSIZE` used to suppress frame *painting* while keeping every native
capability — see that file's own module docstring, STATUS: SETTLED). Specifically:
the transition from `ShowWindow(hwnd, SW_MINIMIZE)` to `ShowWindow(hwnd, SW_RESTORE)`
on this window.

## 2. How the symptom was actually triggered in the wild run

`tools/monkey_test.py`'s `_chrome_maximize_toggle()` ("win+down" action) sends a real
`Win+Down` keystroke. The window was NOT maximized at the time
(`NetSentinel.ini` `[window] maximized=False`, size 900x800 at (0,0)) — on a
non-maximized window, native `Win+Down` is the OS's **minimize** shortcut, not
restore-down. Minimizing clears `WS_VISIBLE` (already documented in
`_is_minimized_and_alive()`'s docstring — confirmed live via `IsWindowVisible`
flipping 1->0). The harness's own `_force_foreground()` (called from `_assert_focus()`
before every subsequent click) then calls `ShowWindow(hwnd, SW_RESTORE)` to bring the
window back up whenever it isn't foreground — which happens automatically on the very
next iteration. In the captured run: `win+down` at iteration 10, then 118 of the next
139 iterations landed on a `MenuItem name='System'` (Windows' native system-menu
control, reachable because this window genuinely has `WS_SYSMENU` per the native-chrome
design) rather than any real app content — consistent with the client area having gone
unpainted and most other controls failing whatever on-screen/visibility check the
harness's `_enabled_controls()` applies (`blacklisted_skipped: 139` that run).

## 3. Known incompatibilities with PyInstaller frozen exe

None identified — this is a live-window compositing issue, not a packaging issue. Not
yet tested against a frozen build; no reason to expect it differs (the mechanism is
Win32/DWM-level, not source-vs-frozen).

## 4. PyQt6-specific constraints

`ui/header.py`'s `changeEvent()` already handles `QEvent.Type.WindowStateChange` for:
maximize-button glyph swap, minimize-to-tray opt-in, and `_refresh_chrome_rects()`. It
does **not** force a full client-area repaint (`self.update()` / `repaint()`) on the
iconic -> normal transition. Standard Qt windows don't need this — Qt's own internal
`WM_PAINT` handling normally repaints on restore — but this window's non-client area is
subclassed (`WM_NCCALCSIZE`/`WM_NCHITTEST` intercepted in `native_chrome.py`), and this
spike's live evidence shows that on THIS window, a real repaint does not happen: the
client area stays a blank, unpainted rectangle indefinitely (see reproduction below —
it did not recover across 7 further minimize/restore cycles and ~10+ seconds).

## 5. Proof-of-concept result: works / doesn't work / deferred

**Reproduced live**, isolated from every other chaos action.
`docs/spikes/minimize-restore-black-window-repro.py`:

1. Launches the real app from source.
2. Waits for the real Dashboard window (matched by the launched process's PID and a
   minimum size, re-resolved fresh via `EnumWindows` before every measurement — an
   earlier draft cached a transient/dead hwnd from during startup and produced a false
   "always black" reading; fixed and noted in the script's own docstring).
3. Measures mean grayscale brightness of the window's client area (`GetClientRect` +
   `ClientToScreen`, both DPI-aware and RULE-WIN11-compliant with declared
   `argtypes`/`restype`) before and after each of 8 `ShowWindow(SW_MINIMIZE)` ->
   `ShowWindow(SW_RESTORE)` cycles — 4 with a 0.5s gap (matching the real
   `win+down` -> later `_force_foreground()` timing) and 4 with a tight 0.15s gap
   (matching `_escalate_app_reclaim()`'s own minimize/restore knock).

**Result:** baseline brightness 29.2 (normal — dark Midnight Pro theme). After the
*very first* cycle (slow, 0.5s gap): 188.1. After the second cycle: 254.9 (essentially
pure white) — and it **stayed at exactly 254.9 for all 6 remaining cycles**, both slow
and fast timing. Screenshot confirms: the window renders as a completely blank white
rectangle with no titlebar, no header buttons, no content of any kind —
`docs/spikes/black-window-repro-cycle2.png` through `cycle8.png`.

This is the same *class* of bug as RULE-STARTUP2/RULE-WIN12 (an unpainted backbuffer
exposed by a native call racing Qt's paint, rendering as a flat colour "depending on
the rendering backend's clear colour") — but a **different trigger and a different
persistence shape**. The documented startup case is a single-frame flash tied to the
`showMaximized()` + restore-rect-fix startup sequence, self-resolving once Qt's first
real paint lands a moment later. This one:

- triggers from a **plain minimize/restore cycle**, at any point mid-session, not only
  on a maximized 2nd+ launch;
- does **not self-resolve** — it was still blank after 7 further cycles and roughly
  10+ seconds of continued interaction, matching the live wild-run report where it
  stayed black through several more chaos iterations and screenshots until the user
  intervened;
- appeared as **white** in this reproduction vs. **black** in the original report —
  consistent with RULE-STARTUP2's own note that the exposed colour depends on backend
  state, not evidence of a different mechanism.

**Not yet confirmed:** the exact repaint mechanism that's failing (Qt never receiving
a paint-invalidating message across the iconic transition on this subclassed window,
vs. something in `native_chrome.py`'s NC handling swallowing/mishandling a message it
shouldn't, vs. a DWM redirection-surface reset that only a specific native call can
force-clear). Also not yet confirmed whether interacting with the window (resize, move,
alt-tab away and back) ever forces recovery, or whether it requires a restart — the
2026-07-23 wild run's own app process closed cleanly when the harness clicked the
titlebar X, so it is not a hard hang, just a persistent paint failure while running.

## Next step (SUPERSEDED — the repaint theory below was wrong; see Resolution)

Candidate fix: in `ui/header.py::changeEvent()`, on `WindowStateChange` where the
window has just left `WindowMinimized` (was minimized, now isn't), force a full
repaint — likely `self.update()` plus, if that proves insufficient (Qt-level update
queued but the *native* backbuffer itself is what's stale), a native
`InvalidateRect(hwnd, None, True)` + `UpdateWindow(hwnd)` pair. **This was implemented
(Fix 1) and CONFIRMED INSUFFICIENT** — the repaint fired correctly but the window
stayed blank, because the problem was never a queued/stale paint. Fix 1 has been
reverted. Kept here only as investigation history.

## Resolution (2026-07-23) — Qt QWidget visibility desync, fixed by `self.show()`

A follow-up diagnostic (`docs/spikes/minimize-restore-hwnd-trace.py`, plus an env-gated
per-transition state dump in `changeEvent`, both since removed from app code) established
the real mechanism through four decisive observations:

1. **HWND is stable** across every minimize/restore cycle (`0x…083c` baseline→final). So
   the window is not recreated → `QEvent.WinIdChange` never fires → the QWebEngineView
   reinstall path is irrelevant. The prior "lost WM_NCCALCSIZE subclass" theory is wrong
   for the same reason: the subclass dies only with the handle, and the handle survives.
2. **Native chrome is innocent.** Forcing `_native_chrome=False` (frameless path) still
   reproduces the bug, just milder (brightness 29→74 vs 29→254) — so the cause is
   Qt-level, above the chrome.
3. **The thread is alive, not hung.** At the stuck state `IsHungAppWindow==0` and the
   window acks `WM_NULL` within timeout. That is why `InvalidateRect`+`UpdateWindow` and a
   real resize-nudge all failed: not a missed paint message.
4. **The smoking gun:** after the native `SW_RESTORE`, the top-level QWidget's
   `isVisible()` is stuck **False** (central widget `isVisible()` False too), while
   `windowHandle().isExposed()` is True and the Win32 window is visible. A QWidget/QWindow
   desync: the native restore bypassed Qt's own `showNormal()`, so Qt never re-set the
   widget's visible flag. Qt gates client painting **and** the QAccessible tree on that
   flag, so the window came back blank with only the 6 native-frame UIA controls instead
   of the ~166 real ones — and refused to repaint because it believed itself hidden.

**Fix (RULE-WIN14):** in `changeEvent()`, on the minimized → not-minimized edge, if
`not self.isVisible()`, call `self.show()` to re-sync Qt's visibility to the already-
restored Win32 window. `self.show()` **alone** is sufficient (no repaint call needed) and
is guarded so it never fires on a normal Qt-driven restore.

**Validated against `minimize-restore-black-window-repro.py` on both axes** (RULE-WIN10):
- native chrome: 8/8 cycles healthy, brightness 29→31.7 (was stuck 254.9 white), UIA tree
  166 controls (was 6);
- frameless: brightness 29→31.8 (was 74), UIA tree 168 (was 0).

Regression test: `tests/test_window_chrome.py::
test_changeevent_reshows_window_when_native_restore_leaves_it_hidden` (watched RED with the
fix neutralized, GREEN with it in). Diagnostic scripts kept:
`docs/spikes/minimize-restore-hwnd-trace.py` (HWND-identity / responsiveness / per-window
UIA trace) and `docs/spikes/minimize-restore-black-window-repro.py` (the canonical
brightness repro).
