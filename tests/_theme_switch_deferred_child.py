"""Subprocess child for experimental/theme_switch_deferred Dashboard tests.

NOT collected by pytest (leading-underscore filename). Invoked by
tests/test_theme_switch_deferred.py via subprocess.run([sys.executable, this_file,
<test_name>]).

Why a subprocess: RULE-TP4-DASH — a fully-constructed Dashboard cannot be
created-and-destroyed in-process on Windows without a Qt/QThread teardown crash,
which is why Dashboard.closeEvent() ends in os._exit(0). Mirrors
tests/_lazy_pages_child.py's contract exactly: main(name) runs the named test body
and calls os._exit(0) on success or os._exit(1) (after printing the traceback) on
any failure. The parent asserts on the child's return code.
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

# Redirect settings_path() to an isolated temp file BEFORE any Dashboard is
# constructed -- see tests/_lazy_pages_child.py's identical block for why:
# dash.close() below runs the real closeEvent()/save_settings(), which would
# otherwise overwrite the developer's real on-disk NetSentinel.ini with a
# never-shown Dashboard's degenerate geometry on every test-suite run.
import tempfile as _tempfile
from ui import app_settings as _app_settings
_TEST_SETTINGS_PATH = Path(_tempfile.mkdtemp()) / "NetSentinel_test.ini"
_app_settings.settings_path = lambda: _TEST_SETTINGS_PATH

_APP: QApplication | None = None


def _ensure_app() -> QApplication:
    global _APP
    if _APP is None:
        _APP = QApplication.instance() or QApplication(["netsentinel-test", "-platform", "offscreen"])
    return _APP


def test_deferred_flag_queues_offscreen_pages_and_flushes_on_nav() -> None:
    _ensure_app()
    from ui import styles as _s
    from ui.dashboard import Dashboard

    QSettings("NetSentinel", "NetSentinel").setValue("experimental/theme_switch_deferred", True)
    try:
        dash = Dashboard(store=None)
    finally:
        QSettings("NetSentinel", "NetSentinel").setValue("experimental/theme_switch_deferred", False)

    assert dash._theme_switch_deferred is True
    assert dash._theme_dirty_widgets == set()

    current = dash._stack.currentWidget()
    other_theme = "Arctic Clean" if _s.get_active_theme_name() != "Arctic Clean" else "Midnight Pro"
    _s.apply_theme(other_theme)

    assert dash._theme_dirty_widgets, "expected off-screen pages to be queued, not refreshed eagerly"
    assert current not in dash._theme_dirty_widgets, "the visible page must be refreshed immediately, never queued"

    # Find a nav label pointing at one of the queued (dirty) widgets, navigate to
    # it, and confirm the flush hook in _nav_rail_go_to (ui/nav/builder.py) both
    # refreshes it and removes it from the dirty set.
    dirty_widget = next(iter(dash._theme_dirty_widgets))
    label = next(
        lbl for lbl, w in dash._nav_label_to_widget.items() if w is dirty_widget
    )
    dash._nav_rail_go_to(label)
    assert dirty_widget not in dash._theme_dirty_widgets, "navigating to a dirty page must flush it"

    dash.close()   # drain workers + os._exit(0) — clean child success exit


def test_flag_off_refreshes_every_page_eagerly() -> None:
    """Default (flag False) path must stay byte-for-byte eager — nothing queued."""
    _ensure_app()
    from ui import styles as _s
    from ui.dashboard import Dashboard

    QSettings("NetSentinel", "NetSentinel").setValue("experimental/theme_switch_deferred", False)
    dash = Dashboard(store=None)
    assert dash._theme_switch_deferred is False

    other_theme = "Arctic Clean" if _s.get_active_theme_name() != "Arctic Clean" else "Midnight Pro"
    _s.apply_theme(other_theme)

    assert dash._theme_dirty_widgets == set(), "flag off must never queue any page"

    dash.close()   # drain workers + os._exit(0) — clean child success exit


def test_dashboard_owns_no_widget_stylesheet_so_app_sheet_governs() -> None:
    """Regression: a theme switch must actually repaint MAIN_STYLE-styled widgets.

    Qt resolves a widget's OWN stylesheet ahead of the QApplication stylesheet for
    that widget and every descendant. Dashboard.__init__ used to set MAIN_STYLE as
    Dashboard's widget-level sheet while _on_theme_changed() writes the merged sheet
    at application level — so after a switch the Dashboard still carried the PREVIOUS
    theme's MAIN_STYLE, which outranked the new app-level one for the whole page tree.
    Only the ~2,000 themed_ss widgets (their own direct setStyleSheet in stage 2)
    changed, leaving the app visibly half-switched.

    The invariant that closes it: Dashboard owns no widget-level stylesheet at all,
    before or after a switch, so the app-level sheet is the single authority.
    """
    _ensure_app()
    from ui import styles as _s
    from ui.dashboard import Dashboard

    dash = Dashboard(store=None)

    assert dash.styleSheet() == "", (
        "Dashboard carries a widget-level stylesheet; it outranks the app-level "
        "sheet that _on_theme_changed() writes, so a theme switch cannot repaint "
        f"anything styled by MAIN_STYLE. Got {dash.styleSheet()[:120]!r}"
    )

    other_theme = "Arctic Clean" if _s.get_active_theme_name() != "Arctic Clean" else "Midnight Pro"
    _s.apply_theme(other_theme)

    assert dash.styleSheet() == "", (
        "a theme switch left a widget-level stylesheet on the Dashboard — it will "
        "override the app-level sheet on the NEXT switch and strand old-theme colours"
    )
    # The app-level sheet is the one that must carry the full page styling.
    app_qss = _ensure_app().styleSheet()
    assert "QTableWidget" in app_qss, (
        "app-level stylesheet is missing MAIN_STYLE's page rules — the merged "
        "single-setStyleSheet path is not covering what Dashboard's sheet used to"
    )
    assert _s.BG_CARD in app_qss, "app-level stylesheet does not reflect the newly-applied theme"

    dash.close()   # drain workers + os._exit(0) — clean child success exit


_TESTS = {
    "test_deferred_flag_queues_offscreen_pages_and_flushes_on_nav": test_deferred_flag_queues_offscreen_pages_and_flushes_on_nav,
    "test_flag_off_refreshes_every_page_eagerly": test_flag_off_refreshes_every_page_eagerly,
    "test_dashboard_owns_no_widget_stylesheet_so_app_sheet_governs": test_dashboard_owns_no_widget_stylesheet_so_app_sheet_governs,
}


def main(name: str) -> None:
    fn = _TESTS.get(name)
    if fn is None:
        sys.stderr.write(f"unknown test: {name!r}; valid: {sorted(_TESTS)}\n")
        os._exit(2)
    try:
        fn()
    except (Exception, KeyboardInterrupt, SystemExit):  # noqa: BLE001 — report ANY failure via exit code
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("usage: _theme_switch_deferred_child.py <test_name>\n")
        os._exit(2)
    main(sys.argv[1])
