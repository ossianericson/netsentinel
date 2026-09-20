"""Child process for tests/test_spinbox_text_fit.py — measures spin-box text fit natively.

Not a test module (no ``test_`` prefix). It needs the REAL platform plugin: under
``-platform offscreen`` fonts measure ~2x wider even with the windows11 style forced, so
the parent's offscreen QApplication cannot answer the question. Nothing is ever shown.

Reads a JSON list of cases ``{"id", "width", "lo", "hi", "suffix"}`` from the file named
in argv[1] and prints one ``RESULT:`` line holding a JSON list of
``{"id", "text", "avail", "need", "style"}``.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication, QSpinBox, QStyle, QStyleOptionFrame  # noqa: E402

_APP = QApplication([sys.argv[0]])  # module global: a discarded app is GC'd mid-run
# Read before any stylesheet is set: afterwards style() is Qt's stylesheet proxy, named "".
_STYLE = _APP.style().objectName()


def _measure(case: dict) -> dict:
    from ui import styles as _s

    sp = QSpinBox()
    sp.setRange(int(case["lo"]), int(case["hi"]))
    sp.setValue(int(case["hi"]))
    sp.setSuffix(case["suffix"])
    _s.style_spinbox(sp)
    # What the call sites use: background/colour/font-size only (see style_spinbox()).
    sp.setStyleSheet(f"QSpinBox {{ background:{_s.BG_DARK}; font-size:11px; color:{_s.TEXT_PRIMARY}; }}")
    sp.setFixedWidth(int(case["width"]))
    sp.grab()  # delivers the pending resize, so the internal QLineEdit is laid out
    le = sp.lineEdit()
    opt = QStyleOptionFrame()
    opt.initFrom(le)
    opt.rect = le.rect()
    contents = le.style().subElementRect(QStyle.SubElement.SE_LineEditContents, opt, le)
    margins = le.textMargins()
    avail = contents.width() - margins.left() - margins.right()
    text = sp.text()
    need = le.fontMetrics().horizontalAdvance(text) + 2  # +2: the cursor, as QAbstractSpinBox::sizeHint
    sp.deleteLater()
    return {"id": case["id"], "text": text, "avail": avail, "need": need, "style": _STYLE}


def main() -> None:
    from ui import styles as _s

    _APP.setStyleSheet(_s.MAIN_STYLE + _s.get_app_qss())
    cases = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    results = [_measure(c) for c in cases]
    _APP.processEvents()
    print("RESULT:" + json.dumps(results), flush=True)
    os._exit(0)  # skip interpreter teardown of Qt objects; the result is already out


if __name__ == "__main__":
    main()
