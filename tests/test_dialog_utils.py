"""Behavioral test for ui.dialog_utils.run_dialog() (RULE-WIN8).

A QDialog parented to a live widget is a C++ child of that parent; dropping
the Python reference after `.exec()` does not free it. run_dialog() must
always schedule deletion, regardless of how the dialog closed.
"""
import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QEvent, QTimer  # noqa: E402
from PyQt6.QtWidgets import QDialog, QWidget  # noqa: E402

from ui.dialog_utils import run_dialog  # noqa: E402


def _pump(app, times=5):
    for _ in range(times):
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()


def test_run_dialog_returns_the_exec_result_and_deletes_the_dialog(qt_app):
    parent = QWidget()
    dlg = QDialog(parent)
    QTimer.singleShot(0, dlg.accept)  # self-close so exec() doesn't block the test

    result = run_dialog(dlg)

    assert result == QDialog.DialogCode.Accepted
    _pump(qt_app)
    live = [c for c in parent.findChildren(QDialog)]
    assert live == [], f"dialog not cleaned up after run_dialog(): {live}"

    parent.deleteLater()
    _pump(qt_app)


def test_run_dialog_deletes_even_when_rejected(qt_app):
    parent = QWidget()
    dlg = QDialog(parent)
    QTimer.singleShot(0, dlg.reject)

    result = run_dialog(dlg)

    assert result == QDialog.DialogCode.Rejected
    _pump(qt_app)
    live = [c for c in parent.findChildren(QDialog)]
    assert live == [], f"dialog not cleaned up after run_dialog(): {live}"

    parent.deleteLater()
    _pump(qt_app)
