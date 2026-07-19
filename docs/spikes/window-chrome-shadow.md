# Spike — does the native-chrome window need a DWM drop-shadow?

**Status:** COMPLETE. **Result: NO fix needed — the shadow is already present. Hypothesis DISPROVEN.**
**Related:** `window-snap-subclass.md`, `webengine-hwnd-recreation.md`, RULE-WIN9, RULE-SPIKE1.

## Hypothesis (from a grep, not a measurement)

A code audit found **no `DwmExtendFrameIntoClientArea` call anywhere in the repo** and
reasoned that reclaiming the whole client area via `WM_NCCALCSIZE` would drop the DWM
drop-shadow, leaving the window flat/cut-out. The textbook borderless-window fix is a 1px
`DwmExtendFrameIntoClientArea` margin (Windows Terminal's `NonClientIslandWindow` does this).

## Method

`scratchpad/spike_shadow.py` — three real top-level windows over a solid `#7F7F7F` backdrop,
screen-grabbed so any shadow shows against a known colour:

| mode | what it is |
|---|---|
| `normal` | a standard title-bar window — reference for a *correct* shadow |
| `native` | the **shipping** `install_native_chrome()` (WM_NCCALCSIZE, no DWM call) |
| `native_dwm` | same + `DwmExtendFrameIntoClientArea(MARGINS{0,0,0,1})` |

Measured on a 3440×1440 display, `devicePixelRatio=1.0`, Windows 11.

## Result — shadow already present; the DWM call is a no-op

- **`native` renders a full, soft DWM drop-shadow on all four edges** — visually equivalent to
  `normal` — plus Win11 rounded corners. The window keeps `WS_THICKFRAME`, and DWM draws the
  shadow (and rounds the corners) for any thick-frame window **regardless of whether the frame
  is painted**. `WM_NCCALCSIZE` suppresses the frame's *pixels*, not its *shadow*.
- `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` returns the **same** 7px side/bottom
  inset for `native` as for `normal` (`GetWindowRect 352,289,748,568` →
  `ExtendedFrameBounds 359,289,741,561`) — DWM treats the native-chrome window as a normally
  framed window.
- **`native_dwm` (`DwmExtendFrameIntoClientArea` → `hr=0`, success) is pixel-indistinguishable
  from `native`.** The call adds nothing visible.

## Constraints (recorded for completeness)

- **PyInstaller frozen exe:** N/A — nothing is being implemented. (`DwmExtendFrameIntoClientArea`
  is a plain `dwmapi.dll` ctypes call and would be frozen-safe, but it is not being added.)
- **PyQt6:** N/A — no code change to the app.

## Conclusion — CLOSED, do not implement

There is no shadow gap. The plan's optional "Section 2" is closed as **unnecessary**: adding
`DwmExtendFrameIntoClientArea` would be dead code that changes nothing. `ui/native_chrome.py`
stays frozen (its `STATUS: SETTLED` block). If a future audit re-flags "no
`DwmExtendFrameIntoClientArea` — missing shadow?", **this spike is the answer**: the shadow and
rounded corners come free from retained `WS_THICKFRAME`.
