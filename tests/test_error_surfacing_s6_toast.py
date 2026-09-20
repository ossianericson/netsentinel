"""S6 — an error toast can carry its next step and its raw detail (finding F6: "no error toast has
an action").

Before S6 only kind ``"action"`` drew a button, so an export failure could say "choose another
location" but not offer it, and the raw exception had nowhere to go except the message itself
(RULE-A2 forbids that). ``detail`` is the tooltip; the message stays plain.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QWidget  # noqa: E402

from ui.widgets.toast import ToastManager  # noqa: E402

RAW = "[Errno 13] Permission denied: 'C:\\Users\\Åsa\\Documents\\enheter.csv'"


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
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def _button(toast, text):
    return next((b for b in toast.findChildren(QPushButton) if b.text() == text), None)


def _message_label(toast, message):
    return next(lbl for lbl in toast.findChildren(QLabel) if lbl.text() == message)


def test_an_error_toast_offers_its_action_and_the_click_runs_it(manager):
    clicked: list = []

    ToastManager.show("The file could not be saved.", "error",
                      action_label="Choose another location",
                      action_callback=lambda: clicked.append(True))

    toast = manager._toasts[-1]
    button = _button(toast, "Choose another location")
    assert button is not None, "an error toast with an action drew no button"

    button.click()

    assert clicked == [True]
    assert toast not in manager._toasts, "the toast stayed up after its action ran"


def test_a_toast_without_an_action_draws_no_action_button(manager):
    ToastManager.show("The file could not be saved.", "error")

    assert [b.text() for b in manager._toasts[-1].findChildren(QPushButton) if b.text()] == []


def test_detail_is_the_message_tooltip_never_the_message(manager):
    ToastManager.show("The file could not be saved.", "error", detail=RAW)

    label = _message_label(manager._toasts[-1], "The file could not be saved.")

    assert "Permission denied" in label.toolTip()
    assert "&#x27;" in label.toolTip() or "&#39;" in label.toolTip(), "tooltip is not HTML-escaped"
    assert "Permission denied" not in label.text()


def test_no_detail_means_no_tooltip(manager):
    ToastManager.show("Saved", "success")

    assert _message_label(manager._toasts[-1], "Saved").toolTip() == ""


def test_detail_and_action_survive_the_pre_attach_queue(qt_app):
    ToastManager._inst = None
    mgr = ToastManager.instance()
    parent = QWidget()
    try:
        ToastManager.show("The file could not be saved.", "error",
                          action_label="Choose another location", action_callback=lambda: None,
                          detail=RAW)
        mgr.attach(parent)

        toast = mgr._toasts[-1]
        assert _button(toast, "Choose another location") is not None
        assert "Permission denied" in _message_label(toast, "The file could not be saved.").toolTip()
    finally:
        for t in list(mgr._toasts):
            t.deleteLater()
        mgr._toasts.clear()
        ToastManager._inst = None
        parent.deleteLater()
        for _ in range(3):
            QApplication.processEvents()
