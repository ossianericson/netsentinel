"""S1.3 — the toast system's three gaps (finding F6).

  * ``"warning"`` is used at three call sites but ``toast.py`` never defined it,
    so ``.get(kind, ...)`` fell through: accent border, no auto-dismiss timer —
    a warning rendered as a *sticky info* toast.
  * ``_show()`` evicted ``self._toasts[0]`` once three were on screen, oldest
    first, with no regard for kind. A sticky error (auto-dismiss 0, i.e. "stays
    until the user clicks it") was silently removed by three routine successes.
  * A toast raised before ``attach()`` returned early and vanished. Startup
    failures are exactly the ones that land in that window.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QWidget  # noqa: E402

from ui.widgets import toast as toast_mod  # noqa: E402
from ui.widgets.toast import ToastManager  # noqa: E402


@pytest.fixture
def manager(qt_app):
    """A ToastManager with a fresh parent, reset afterwards (RULE-WIN4)."""
    ToastManager._inst = None
    parent = QWidget()
    parent.resize(900, 700)
    yield ToastManager.instance(), parent

    mgr = ToastManager.instance()
    for t in list(getattr(mgr, "_toasts", [])):
        try:
            t.deleteLater()
        except RuntimeError:
            pass  # C++ object already gone
    mgr._toasts.clear()
    ToastManager._inst = None
    parent.deleteLater()
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_warning_is_a_defined_kind():
    """Undefined kinds fall through to the info defaults, silently."""
    assert "warning" in toast_mod._AUTO_DISMISS_MS, (
        "toast.py does not define a 'warning' kind, so the three call sites "
        "using it render as sticky info toasts"
    )
    assert toast_mod._AUTO_DISMISS_MS["warning"] > 0, (
        "a warning must auto-dismiss; 0 means 'stays until clicked'"
    )
    assert toast_mod._type_border("warning") == toast_mod._s.AMBER


def test_warning_border_is_not_the_info_fallback():
    assert toast_mod._type_border("warning") != toast_mod._type_border("info")


def test_a_sticky_error_is_not_evicted_by_routine_successes(manager):
    """Three successes must not silently discard the error the user must see."""
    mgr, parent = manager
    mgr.attach(parent)

    ToastManager.show("Scan failed — no route to host", "error")
    for i in range(3):
        ToastManager.show(f"Export {i} saved", "success")

    kinds = [t._kind for t in mgr._toasts]
    assert "error" in kinds, (
        f"the sticky error toast was evicted by later successes; on screen: {kinds}"
    )


def test_a_toast_raised_before_attach_is_not_dropped(manager):
    """Startup failures land before attach(); they must not vanish."""
    mgr, parent = manager

    ToastManager.show("REST API could not bind to port 8080", "error")
    mgr.attach(parent)

    kinds = [t._kind for t in mgr._toasts]
    assert "error" in kinds, (
        "a toast raised before attach() was dropped instead of queued"
    )
