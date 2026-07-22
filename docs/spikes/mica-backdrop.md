# Spike — can a DWM Mica/Acrylic backdrop show through native chrome?

**Status:** COMPLETE. **Result: DISPROVEN — structurally incompatible with the shipped custom-chrome technique. Not implemented.**
**Related:** `window-chrome-shadow.md`, `window-snap-subclass.md`, RULE-WIN9, RULE-SPIKE1.
**Trigger:** user asked whether QWindowKit (`c:\Code\qwindowkit-main`, a C++ Qt
frameless-window library with zero Python bindings — not adoptable directly)
had anything worth learning from. One genuinely new, small idea surfaced:
QWindowKit's Mica/Acrylic `DWMWA_SYSTEMBACKDROP_TYPE` support, which
`native_chrome.py` has never touched. This spike evaluates it in isolation.

## Hypothesis

`DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE=38, DWMSBT_MAINWINDOW=2)`
(Windows 11 22H2+, build 22621) could paint a Mica frosted-glass material
behind NetSentinel's ~40px custom titlebar strip (`ui/header.py`'s
`_DragHeader`), the way Windows Terminal/Explorer/Settings show Mica behind
their own title/tab bars, while the rest of the app (content, sidebar, cards)
stays fully opaque as today — a purely additive, cosmetic, flag-gated change.

## Method

Dev machine: Windows build 26200 (`sys.getwindowsversion()`), well above the
22621 floor — no version-gating blocker.

`scratchpad/spike_mica.py` — real top-level windows built with the actual,
unmodified `ui.native_chrome.install_native_chrome()` (not an idealized
stand-in), screen-grabbed for comparison:

| mode | what it is | result |
|---|---|---|
| `no_backdrop` | shipping chrome, solid `NAV_BAR` header — reference | solid navy header, as expected |
| `mica_opaque_header` | `DwmSetWindowAttribute` Mica ON, header still painted solid | **pixel-identical to `no_backdrop`** — confirms opaque paint fully blocks the backdrop; this is the "ship an invisible no-op" trap the plan called out in advance |
| `mica_translucent_header` (first attempt) | Mica ON + `WA_TranslucentBackground` + header `fillRect(alpha=0)` in default `SourceOver` mode | **solid black** — the exact QWindowKit-documented "background turns black" bug reproduced |
| `mica_translucent_workaround` | + QWindowKit's documented fix: a 1×1-then-restore `MoveWindow` nudge after the attribute call (`win32windowcontext.cpp:1004-1025`) | **still solid black** — their workaround did not fix it on this PyQt6/Win11 combination |
| `mica_translucent_header` (2nd attempt) | + `WA_NoSystemBackground`/`WA_TranslucentBackground` on the header widget itself + `QPainter.CompositionMode.CompositionMode_Source` for the clear (the real bug: default `SourceOver` alpha=0 is a no-op over Qt's opaque auto-fill) | **still solid black** — ruled out the Qt-side compositing-mode explanation |
| `mica_extend_frame` | + `DwmExtendFrameIntoClientArea` with all-`(-1)` "sheet of glass" margins (the standard technique DWM needs to actually treat a region as backdrop-eligible) | **Mica-adjacent rendering appears, but a native Win11 titlebar with real minimize/maximize/close glyphs reappears at the top of the window** |
| `mica_extend_frame_top_only` | same, but margins `(0,0,40,0)` — only the 40px header strip, not the whole window | **identical result** — the native titlebar returns even when only the header-height margin is extended |

Screenshots: `scratchpad/mica_poc_*.png` (7 files, one per mode above).

## Result — mechanism identified, and it's a hard conflict, not a bug to route around

Getting DWM to actually paint the Mica material behind a region requires
telling DWM that region is glass/non-client via `DwmExtendFrameIntoClientArea`
— `DwmSetWindowAttribute(DWMWA_SYSTEMBACKDROP_TYPE, ...)` alone sets the
window's backdrop *policy* but DWM still renders solid black behind any
per-pixel-alpha client region it does not consider glass. That was proven
independently of any Qt-side mistake (ruled out the composition-mode
explanation with the 2nd translucent-header attempt).

But `native_chrome.py`'s entire technique (RULE-WIN9) depends on the *opposite*
claim: `WM_NCCALCSIZE` reports zero non-client inset at the top so DWM treats
the **whole window as ordinary client area with no native caption**, which is
precisely what stops Windows from drawing its own titlebar/min/max/close
buttons and hands that space to the Qt-painted header. The moment any
`DwmExtendFrameIntoClientArea` margin is applied — even just the 40px header
strip, not the whole window — Windows reactivates native caption rendering
over that region and the real system buttons reappear, stacked over the
custom header. The two techniques claim the same non-client/client boundary
and directly contradict each other: Mica-eligible-glass and
suppressed-native-caption cannot both be true for the same pixels.

This is a **structural** incompatibility, not a fixable implementation detail
— unlike the QWindowKit black-background bug (which they document as fixable
with a nudge on some driver/Qt combos), the extend-frame requirement is not
optional, and its side effect (native caption returns) is not something a
workaround can suppress without re-fighting the exact RULE-WIN9 problem
`native_chrome.py` was built to solve in the first place.

## Constraints checklist (RULE-SPIKE1)

- **PyInstaller frozen exe:** N/A — nothing is being implemented; the calls
  involved (`DwmSetWindowAttribute`, `DwmExtendFrameIntoClientArea`) are plain
  `dwmapi.dll` ctypes calls that would be frozen-safe if this were shipped, but
  it is not being shipped.
- **PyQt6:** confirmed the failure is not a Qt compositing-mode mistake (ruled
  out explicitly via the 2nd translucent-header attempt) — it is a genuine
  DWM-level requirement that conflicts with the existing chrome technique.
- **Windows version gate:** would have been `sys.getwindowsversion().build >=
  22621`; moot given the result.

## Conclusion — CLOSED, do not implement

Mica/Acrylic backdrop material is **not compatible** with NetSentinel's
existing native-chrome technique without giving up the custom-drawn titlebar
(i.e. reintroducing native min/max/close buttons NetSentinel replaced on
purpose) — which is a strictly worse trade for a purely cosmetic feature.
`native_chrome.py` stays untouched; no flag, no new module, no `ui/header.py`
change. Per the plan's decision gate, this is the same outcome shape as
`window-chrome-shadow.md`: a real investigation, a real mechanism found, and a
"do not implement" conclusion. If a future audit re-suggests Mica/Acrylic for
NetSentinel's window, **this spike is the answer** — the backdrop material
requires ceding exactly the non-client region the custom chrome exists to own.
