"""RULE-UI2 — a toast shows its whole message, whatever its length and whether or not it has an action.

Found 2026-09-18 by rendering the real export-failure toast: the toast is a fixed 300 px wide, its
height came from ``adjustSize()`` — i.e. ``sizeHint()``, computed at the message label's
unconstrained width — and S6 put an action button inline. The button squeezed the message to 94 px,
which needed 195 px of height and got 90, so "Close it in the other program, or choose another
location." (the *what next* half of RULE-A2) was cut off.

The assertions compare the label with its own ``heightForWidth``, so they hold on any platform's
fonts (offscreen text measures wider than native, which only makes a clipped toast clip more).
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QLabel, QPushButton, QWidget  # noqa: E402

from ui.widgets.toast import ToastManager  # noqa: E402

# The longest real message shape: an S6 export failure with an explained why/next (~200 chars).
_LONG = ("The inventory changes could not be saved. Windows refused access. The file may be open in "
         "another program, or the location is protected. Close it in the other program, or choose "
         "another location.")


@pytest.fixture
def manager(qt_app):
    """A ToastManager with a fresh parent, reset afterwards (RULE-WIN4)."""
    ToastManager._inst = None
    parent = QWidget()
    parent.resize(900, 700)
    mgr = ToastManager.instance()
    mgr.attach(parent)
    yield mgr

    for t in list(mgr._toasts):
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


def _shown_toast(mgr, **kwargs):
    ToastManager.show(_LONG, "error", detail="PermissionError: [Errno 13]", **kwargs)
    QTest.qWait(400)          # the slide-in animation (150 ms) ends on the final geometry
    toast = mgr._toasts[-1]
    toast.grab()              # delivers pending resize events: lays the children out
    message = next(lbl for lbl in toast.findChildren(QLabel) if lbl.text() == _LONG)
    return toast, message


def _assert_fits(message: QLabel) -> None:
    needed = message.heightForWidth(message.width())
    assert message.height() >= needed, (
        f"the toast message is cut off: its label is {message.width()}x{message.height()} px but the "
        f"wrapped text needs {needed} px of height. Size the toast from heightForWidth(_WIDTH), not "
        "adjustSize()/sizeHint() (RULE-UI2)."
    )


def test_long_message_with_an_action_shows_in_full(manager) -> None:
    _toast, message = _shown_toast(manager, action_label="Choose another location",
                                   action_callback=lambda: None)
    _assert_fits(message)


def test_long_message_without_an_action_shows_in_full(manager) -> None:
    _toast, message = _shown_toast(manager)
    _assert_fits(message)


def test_the_action_button_does_not_take_the_message_width(manager) -> None:
    toast, message = _shown_toast(manager, action_label="Choose another location",
                                  action_callback=lambda: None)
    button = next(b for b in toast.findChildren(QPushButton) if b.text() == "Choose another location")
    assert button.geometry().top() >= message.geometry().bottom(), (
        "the action button sits beside the message, squeezing it into a narrow column — "
        "put it on its own row below the text"
    )
