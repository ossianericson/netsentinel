"""
ui.dialog_utils — modal-dialog cleanup helper.

RULE-WIN8: a QDialog/QMessageBox constructed with ``parent=self`` (or any live
widget) is owned by that parent in C++. Dropping the Python reference after
``dlg.exec()`` returns does NOT destroy it — the parent keeps a child pointer,
so every field, layout, and cached value on the dialog lives until the parent
itself is destroyed (in practice, until the app closes). A page whose dialog
gets opened repeatedly (right-click "Edit", "Compare", "Add Rule", ...) leaks
one full dialog instance per open. Route every locally-constructed modal
dialog's ``.exec()`` call through ``run_dialog()`` instead of calling it
directly, so the instance is always cleaned up regardless of how it closed
(accept, reject, or the window's close button).
"""
from __future__ import annotations

from PyQt6.QtWidgets import QDialog


def run_dialog(dlg: QDialog) -> int:
    """Run ``dlg`` modally and delete it afterward. Returns ``dlg.exec()``'s result code."""
    try:
        return dlg.exec()
    finally:
        dlg.deleteLater()
