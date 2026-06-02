# Plan: Live Theme Switching (no restart required)

## Context
Currently switching theme in Settings saves to QSettings and shows "restart to apply." The goal is immediate visual change. The blocker: `MAIN_STYLE` and all 76 files' inline `setStyleSheet()` calls bake hex values at construction time via f-string evaluation. Re-applying the root QSS cascade handles widgets without inline styles; widgets with inline styles need their own re-run.

## Architecture

All 100% of inline stylesheets already use token f-strings (`f"color: {ACCENT};"`). After updating `ui/styles` module globals via `globals().update(THEMES[name])`, any method that re-reads tokens via the module object (`import ui.styles as _s; _s.ACCENT`) gets fresh values. The pattern: extract each page's `setStyleSheet` calls into `_apply_styles()`, call it at construction and again from `refresh_theme()`.

## Phase 1 — Infrastructure (`ui/styles.py`)

Add after `MAIN_STYLE = _build_qss()` at line 1119:

**`get_theme_manager()`** — lazy singleton returning a `QObject` subclass with `theme_changed = pyqtSignal(str)`. Deferred construction (class defined inside function so `pyqtSignal` doesn't fire before `QApplication` exists — matches existing lazy-import pattern in file).

```python
_theme_manager = None
def get_theme_manager():
    global _theme_manager
    if _theme_manager is None:
        from PyQt6.QtCore import QObject, pyqtSignal as _sig
        class _ThemeManager(QObject):
            theme_changed = _sig(str)
        _theme_manager = _ThemeManager()
    return _theme_manager
```

**`apply_theme(name: str)`** — live switch entry point:
1. Validate name in `THEMES`
2. `globals().update(THEMES[name])`
3. Check `get_accent_override()`; if set, call `_compute_accent_variants()` and update globals for `ACCENT/ACCENT_LITE/ACCENT_DARK`
4. Update `RISK_COLORS` and `RISK_BG` **in-place** (other modules hold a reference to these dict objects — replacing them would leave stale references):
   ```python
   import sys
   _m = sys.modules[__name__]
   _m.RISK_COLORS.clear(); _m.RISK_COLORS.update({"HIGH": _m.RED, "STORM": _m.RED, ...})
   _m.RISK_BG.clear();     _m.RISK_BG.update({"HIGH": _m.RED_BG, ...})
   ```
5. `globals()["MAIN_STYLE"] = _build_qss()`
6. Persist: `QSettings("NetSentinel", "NetSentinel").setValue("ui/theme", name)`
7. `get_theme_manager().theme_changed.emit(name)`

**`apply_accent_override(hex_val: str | None)`** — same flow but only updates accent tokens + rebuilds MAIN_STYLE + emits. Replaces `set_accent_override()` usage at the call sites.

**`get_app_qss() -> str`** — returns the QMenu + QToolTip QSS currently inline in `app.py` (lines 434–443), reading live module globals at call time. Used by both `app.py` at startup and `_on_theme_changed` at runtime.

Also update docstring on `set_active_theme_name()` — remove "takes effect on restart."

## Phase 2 — App-level QSS (`app.py`)

Replace lines 432–443:
```python
from ui.styles import get_app_qss
app.setStyleSheet(get_app_qss())
```

## Phase 3 — Dashboard wiring (`ui/dashboard.py`)

Add `import ui.styles as _styles` to top-level imports (or use it inside the method).

In `__init__`, after `self.setStyleSheet(MAIN_STYLE)` (line 138):
```python
from ui.styles import get_theme_manager as _gtm
_gtm().theme_changed.connect(self._on_theme_changed)
```

Add slot:
```python
def _on_theme_changed(self, _name: str) -> None:
    import ui.styles as _s
    from PyQt6.QtWidgets import QApplication
    self.setStyleSheet(_s.MAIN_STYLE)                        # re-apply cascade
    app = QApplication.instance()
    if app:
        app.setStyleSheet(_s.get_app_qss())                  # QMenu/QToolTip
    for i in range(self._stack.count()):                     # all registered pages
        w = self._stack.widget(i)
        if w and hasattr(w, "refresh_theme"):
            w.refresh_theme()
```

## Phase 4 — Settings trigger (`ui/pages/settings_cards.py`)

`_on_theme()` at line 641:
```python
def _on_theme(self, name: str) -> None:
    from ui.styles import apply_theme
    apply_theme(name)
    self._refresh_theme_buttons()
    self._theme_status_lbl.setText(f"Theme '{name}' applied.")
```

`_refresh_theme_buttons()` must re-read tokens via module object (not import-time names):
```python
import ui.styles as _s
active = _s.get_active_theme_name()
# use _s.ACCENT, _s.NAV_BAR etc. in f-strings
```

Update description label: "Changes apply immediately."

Also update `settings_appearance.py` `_on_theme()` (line 166) identically for symmetry.

For accent handlers (`_on_accent_swatch`, `_on_accent_custom`, `_on_accent_reset`) in both files: replace `_styles.set_accent_override(...)` with `apply_accent_override(...)` and update status labels.

## Phase 5 — Per-page `refresh_theme()` (all 76 files)

**Pattern for every page/widget file with `setStyleSheet()` calls:**

1. Extract all `setStyleSheet(...)` calls from the construction method into `_apply_styles(self)`. The method must reference tokens via the module object:
   ```python
   def _apply_styles(self) -> None:
       import ui.styles as _s
       self.setStyleSheet(f"background:{_s.BG_DARK};")
       self._label.setStyleSheet(f"color:{_s.TEXT_PRIMARY};")
       # ...all other setStyleSheet calls...
   ```
2. Call `self._apply_styles()` at the end of `__init__` (or end of the build method).
3. Add:
   ```python
   def refresh_theme(self) -> None:
       self._apply_styles()
   ```

**For pages with matplotlib charts** (live_bandwidth_page, history_page, speed_test_page, geo_map_page, live_graph.py, wifi_heatmap_page, topology_widget): add chart colour update to `refresh_theme()`:
```python
import ui.styles as _s
self._fig.patch.set_facecolor(_s.BG_CARD)
self._ax.set_facecolor(_s.BG_ALT_ROW)
for sp in self._ax.spines.values(): sp.set_color(_s.BORDER)
self._ax.tick_params(colors=_s.CHART_AXIS)
self._ax.grid(True, color=_s.BORDER, linewidth=0.8)
self._canvas.draw_idle()
```
For pages where `_redraw_chart()` already applies all axis styles: just call `self._redraw_chart()` instead.

**For widget classes** (`ui/widgets/*.py`) that have inline styles: same pattern. Parent page's `refresh_theme()` must also call `refresh_theme()` on any owned widget instances stored as attributes (e.g. `self._grade_ring.refresh_theme()`).

**For dashboard-level mixin widgets** (nav rail buttons, header bar): the `MAIN_STYLE` cascade covers `#appBar` and `#sideNav` by objectName. `_RailButton` and `_FlyoutPanel` in `ui/nav/rail.py` have inline styles — add `refresh_theme()` to each. In `_on_theme_changed`, after stack iteration, also call:
```python
for btn in self._nav_sections_btns.values():  # rail section buttons
    if hasattr(btn, "refresh_theme"): btn.refresh_theme()
```
(Use whatever attribute stores the `_RailButton` instances.)

**Interspersed-style pages** (where `setStyleSheet` calls are scattered through widget creation rather than at the end): use the two-pass approach — keep widget creation in place, but move all `setStyleSheet(...)` calls to `_apply_styles()`. The widgets are stored as `self._xxx` attributes by construction time, so `_apply_styles()` can reference them safely.

## Phase 6 — Tests (`tests/test_themes.py`)

Add `TestApplyTheme` class:
- `test_apply_theme_updates_globals` — call `apply_theme("Midnight Pro")`, assert `ui.styles.ACCENT == THEMES["Midnight Pro"]["ACCENT"]`
- `test_apply_theme_rebuilds_main_style` — call `apply_theme("Abyss")`, assert `ui.styles.MAIN_STYLE` contains `THEMES["Abyss"]["BG_DARK"]`
- `test_apply_theme_updates_risk_colors_in_place` — get reference before call, assert same object has new RED after switch
- `test_apply_theme_emits_signal` — connect a mock slot, verify it's called with theme name
- `test_get_app_qss_reflects_current_theme` — switch theme, assert `get_app_qss()` contains new BG_CARD
- `test_apply_accent_override_updates_accent` — call `apply_accent_override("#FF5500")`, assert `ui.styles.ACCENT == "#FF5500"`
- `test_apply_accent_override_none_restores_default` — override then reset, assert ACCENT matches active theme default

## Execution Order

1. `ui/styles.py` — add `get_theme_manager`, `apply_theme`, `apply_accent_override`, `get_app_qss`
2. `app.py` — use `get_app_qss()`
3. `tests/test_themes.py` — new test class (run tests, must pass)
4. `ui/dashboard.py` — connect signal, add `_on_theme_changed`
5. `ui/pages/settings_cards.py` + `settings_appearance.py` — call `apply_theme`, update labels
6. `ui/pages/` (all 54 page files) — extract `_apply_styles()`, add `refresh_theme()`
7. `ui/widgets/` (22 widget files) — same pattern
8. `ui/nav/rail.py` — `refresh_theme()` on `_RailButton` and `_FlyoutPanel`
9. `ui/live_graph.py` + `ui/topology_widget.py` — chart refresh in `refresh_theme()`
10. Run full test suite, run debug_launch.py, manual theme-switch test

## Verification

- `python -m pytest tests/ -q` — all pass
- `python tools/debug_launch.py` → confirm `window.show() called OK`
- Manual: Settings → click "Midnight Pro" → entire app changes immediately (no restart)
- Manual: click "Abyss" → switches to true-black
- Manual: click "Arctic Clean" → back to light
- Manual: pick a purple accent swatch → accent updates immediately on buttons/nav
- Manual: right-click a table row → context menu uses new theme colours
- Manual: hover any widget → tooltip uses new theme colours
