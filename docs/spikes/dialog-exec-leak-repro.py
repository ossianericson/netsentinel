"""
Live repro (RULE-DBG3): quantify RSS growth from repeatedly opening a QDialog
that is parented to a long-lived widget (as ~47 call sites in ui/ did, pre-fix,
via `dlg = SomeDialog(..., parent=self); dlg.exec()`) with vs without an
explicit `deleteLater()` afterward. See RULE-WIN8's "general case" note in
development-rules.instructions.md for the numbers this produced and the fix
(`ui/dialog_utils.py::run_dialog()`).

Run manually: `python docs/spikes/dialog-exec-leak-repro.py`
Not part of the pytest suite — this is a one-off measurement script, kept for
provenance/reproducibility rather than as a regression gate (the AST guard in
tests/test_dialog_leak_guard.py is the actual regression gate).

Warms up caches first, force-flushes DeferredDelete events explicitly, and
runs fixed/leak/fixed in a sandwich to separate the leak's contribution from
one-time Qt/font/style cache growth and general heap drift.
"""
import gc
import os
import sys

import psutil
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QFormLayout,
    QLineEdit, QTextEdit, QDialogButtonBox, QLabel,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

app = QApplication.instance() or QApplication(sys.argv + ["-platform", "offscreen"])
proc = psutil.Process(os.getpid())


class RepresentativeDialog(QDialog):
    """Shape modeled on ui/widgets/inventory_dialogs.py::_DeviceLabelDialog:
    a form + notes box + button row."""

    def __init__(self, mac: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Label device {mac}")
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit()
        self._tags = QLineEdit()
        form.addRow("Name:", self._name)
        form.addRow("Tags:", self._tags)
        lay.addLayout(form)
        self._notes = QTextEdit()
        self._notes.setPlainText("x" * 2000)  # approximate populated device notes
        lay.addWidget(QLabel("Notes:"))
        lay.addWidget(self._notes)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)


def rss_mb() -> float:
    return proc.memory_info().rss / (1024 * 1024)


def settle():
    for _ in range(5):
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    gc.collect()


def run(n: int, cleanup: bool, parent: QWidget) -> float:
    settle()
    start = rss_mb()
    for i in range(n):
        dlg = RepresentativeDialog(f"aa:bb:cc:dd:ee:{i % 100:02x}", parent)
        dlg.show()
        app.processEvents()
        dlg.accept()          # mirrors dlg.exec() returning Accepted
        if cleanup:
            dlg.deleteLater()
        app.processEvents()
    settle()
    end = rss_mb()
    return end - start


if __name__ == "__main__":
    N = 500
    print(f"Iterations per run: {N}")

    parent = QWidget()  # stands in for a long-lived page (e.g. InventoryPage)
    parent.show()
    app.processEvents()

    warm = run(50, cleanup=True, parent=parent)
    print(f"warm-up (discarded): {warm:+.2f} MB")

    fixed1 = run(N, cleanup=True, parent=parent)
    print(f"WITH deleteLater() [1st]: RSS delta = {fixed1:+.2f} MB ({fixed1*1024/N:.1f} KB/dialog)")

    leak = run(N, cleanup=False, parent=parent)
    print(f"WITHOUT deleteLater():    RSS delta = {leak:+.2f} MB ({leak*1024/N:.1f} KB/dialog)")

    fixed2 = run(N, cleanup=True, parent=parent)
    print(f"WITH deleteLater() [2nd]: RSS delta = {fixed2:+.2f} MB ({fixed2*1024/N:.1f} KB/dialog)")

    fixed_avg = (fixed1 + fixed2) / 2
    print(f"\nfixed baseline (avg of sandwiching runs): {fixed_avg:+.2f} MB")
    print(f"leak run:                                  {leak:+.2f} MB")
    print(f"Difference attributable to the leak:       {leak - fixed_avg:+.2f} MB over {N} opens "
          f"({(leak - fixed_avg) * 1024 / N:.1f} KB/dialog)")
