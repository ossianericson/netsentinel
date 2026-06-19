"""help_mode_overlay.py — HelpModeOverlay: ephemeral 'What can I do here?' mode (S9-5).

Walks the visible widgets of the current page and shows each one's existing
tooltip as an inline label, so a new user can see what every button/field
does without hunting for documentation. Click anywhere or press Esc to
dismiss. Purely a transient visual layer — never changes the underlying
page's default view (RULE additive-only constraint, Sprint 9 backlog).
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLabel, QWidget

from ui.styles import ACCENT, WHITE


class HelpModeOverlay(QWidget):
    """Transient overlay that labels every tooltip-bearing widget on ``target``."""

    closed = pyqtSignal()

    def __init__(self, target: QWidget) -> None:
        super().__init__(target)
        self._target = target
        self.setGeometry(target.rect())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._labels: list[QLabel] = []
        self._build_labels()
        self.show()
        self.raise_()
        self.setFocus()

    def _build_labels(self) -> None:
        seen_positions: set[tuple[int, int]] = set()
        for w in self._target.findChildren(QWidget):
            if w is self or not w.isVisible():
                continue
            tip = w.toolTip().strip()
            if not tip:
                continue
            pos = w.mapTo(self._target, QPoint(0, 0))
            key = (pos.x(), pos.y())
            if key in seen_positions:
                continue
            seen_positions.add(key)
            text = tip.split("\n")[0]
            if len(text) > 90:
                text = text[:87] + "…"
            lbl = QLabel(text, self)
            lbl.setWordWrap(True)
            lbl.setMaximumWidth(260)
            lbl.setStyleSheet(
                f"background:{ACCENT}; color:{WHITE}; font-size:10px;"
                f" border-radius:3px; padding:2px 6px;"
            )
            lbl.adjustSize()
            lx = max(0, pos.x())
            ly = max(0, pos.y() - lbl.height() - 2)
            lbl.move(lx, ly)
            lbl.show()
            self._labels.append(lbl)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 60))

    def mousePressEvent(self, event) -> None:
        self._close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._close()
        else:
            super().keyPressEvent(event)

    def _close(self) -> None:
        self.closed.emit()
        self.deleteLater()
