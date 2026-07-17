# Spike — native chrome lost when Network Map creates its QWebEngineView

**Status:** POC complete, works. Fix approved (safety-net reinstall on `WinIdChange`).
**Related:** `window-snap-subclass.md` (the native-chrome design), RULE-WIN9, RULE-WIN2.

## Symptom

The real Windows title bar ("NetSentinel — Dashboard") appears **above** the custom
header a few seconds after startup — never at startup itself. Reported as "always ~3
seconds after the app looks started"; the real trigger is **navigating to Network
Map**, which the user does habitually right after launch.

## Root cause

On Windows the main window is a *normal* Win32 window that keeps its real
`WS_CAPTION | WS_SYSMENU | WS_THICKFRAME` (`ui/dashboard.py`); the title bar is not
absent, it is merely not *painted*, because a `comctl32` subclass answers
`WM_NCCALCSIZE` with the caption reclaimed (`ui/native_chrome.py::install_native_chrome`,
installed once from `AppHeaderMixin.showEvent`).

`QWebEngineView` is backed by a native child window (Chromium compositor surface).
The first time Network Map is shown it builds that view
(`ui/pages/network_map_page.py::_try_init_webengine`, deferred to `showEvent` for
startup perf). To host a native child, Qt promotes the ancestor chain to native and
**destroys and recreates the top-level window's HWND**. The new HWND:

1. is a fresh window with the default frame → Windows draws the title bar again, and
2. does **not** carry the `WM_NCCALCSIZE` subclass — that died with the old HWND.

It never recovers, because `_install_window_chrome()` is guarded by
`_snap_subclass_installed` (already `True` from the first show), so the chrome is
never re-established on the new handle.

### Measured (live app)

Same Dashboard instance, before vs after navigating to Network Map:

| moment | HWND | caption height | window height |
|---|---|---|---|
| just shown (Home) | `18548766` | 0 (suppressed ✅) | 1197 |
| after Network Map | `18614302` | 31 (title bar ❌) | 1228 (+31 = title bar) |

The HWND number changed — proof the native window was recreated, not merely repainted.

## Windows / Qt / PyInstaller constraints

- **Win32 API:** `WM_NCCALCSIZE` frame suppression via a `SetWindowSubclass` hook is
  bound to a specific `HWND`. When Windows destroys that HWND (Qt-driven recreation),
  the subclass is auto-removed by the OS; no leak, but no survival either.
- **PyQt6:** Qt raises `QEvent::WinIdChange` (type 203) on a widget whenever its
  `winId()` changes — including this recreation. It is delivered to the top-level
  widget's `event()` and is the documented, cause-agnostic hook for "the native
  handle just changed." `QWebEngineView`/`QtWebEngineWidgets` must be imported (or
  `AA_ShareOpenGLContexts` set) *before* `QApplication` — the app already satisfies
  this; only mattered for the standalone POC.
- **PyInstaller:** no special incompatibility. The recreation is a Qt runtime
  behaviour identical frozen vs. source, and the `WinIdChange` hook is pure Qt (no
  ctypes/frozen-path concerns beyond what `native_chrome.py` already handles).

## POC result — works

`scratchpad/spike_webengine_recreate.py`: a minimal top-level window, real
`install_native_chrome`, then embed a `QWebEngineView` after 1.5 s.

```
[t0] shown:                     hwnd=6949222 capH=31
[t0] install_native_chrome=True hwnd=6949222 capH=0     (suppressed)
[t1] before webview:            hwnd=6949222 capH=0
[event] WinIdChange -> new hwnd=7014758 capH=31         (recreation + title bar back)
[event]   reinstall_native_chrome -> True; capH=0 hwnd=7014758   (re-suppressed)
```

Confirms all three gating facts: (a) `QWebEngineView` recreates the top-level HWND,
(b) `WinIdChange` fires on the top-level, (c) calling `install_native_chrome()` from
that handler re-suppresses the frame on the new HWND. `install_native_chrome` is
already re-entrant (rebuilds `_nc_state`, `_nc_subclass_proc`); the old proc drops
harmlessly once its now-destroyed HWND releases it.

## Fix — two layers

The safety net alone fixed the title bar, but left a visible artifact: the top-level
window is still genuinely destroyed and recreated, so the whole window **flashes as if
the app restarted** on the first Network Map visit (user-reported). So both layers ship.

### Layer 1 — prevention (removes the flash)

Make the web view's container `WA_NativeWindow` **before** the `QWebEngineView` is
built, so Qt hosts the native view under an already-native ancestor instead of
rebuilding the window tree. Measured across strategies (`scratchpad/spike_prevent.py`,
install chrome → embed a `QWebEngineView`):

| strategy | HWND recreated? | title bar | web view |
|---|---|---|---|
| none (baseline) | **yes** | back | ok |
| `AA_DontCreateNativeWidgetSiblings` | yes | back | ok |
| `WA_DontCreateNativeAncestors` on the view | yes | back | ok |
| **`WA_NativeWindow` on top-level + container** | **no** | stays hidden | ok |
| `WA_NativeWindow` on the **container only**, set late | **no** | stays hidden | ok |

`WA_NativeWindow` on the container is the minimal winner. It **must** be set late — in
`showEvent`/`_try_init_webengine`, after the top-level is shown and chrome is
installed — never at construction: forcing the top-level HWND to exist early makes Qt
re-push its stale creation-time geometry and collapses the window to its minimum size
(the same trap `test_geometry_is_reapplied_after_the_chrome_is_installed` guards).
Implemented in `ui/pages/network_map_page.py::_try_init_webengine`, guarded by
`test_network_map_marks_container_native_before_building_the_web_view`.

### Layer 2 — safety net (cause-agnostic correctness guarantee)

Catch `QEvent::WinIdChange` in `AppHeaderMixin.event()` and, when native chrome is
active and was already installed once on a *different* HWND
(`should_reinstall_native_chrome`), re-run the install on the new handle — **without**
re-applying saved geometry (mid-session keeps the user's current rect, unlike the
first-show path which calls `reapply_geometry_after_chrome`). Prevention removes the
known trigger; the safety net still catches any *future* recreation (other native
widgets, DPI-driven rebuilds) so the title bar can never return permanently even if
prevention is bypassed. Belt and braces, deliberately.

### Verified

Live walk: launched the real app, navigated to Network Map — HWND did **not** change,
caption height stayed 0 (no title bar, no flash); web view rendered. User confirmed
manually.
