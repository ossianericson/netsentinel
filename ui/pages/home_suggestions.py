"""
home_suggestions.py — _HomeSuggestionsMixin: 'What to do next' strip logic for HomePage.

Extracted from ui/pages/home_page.py (Sprint 13).
HomePage inherits from _HomeSuggestionsMixin.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_HOVER, RED,
    TEXT_PRIMARY,
)


class _HomeSuggestionsMixin:
    """Mixin providing the 'What to do next' suggestions strip for HomePage.

    Extracted from ui/pages/home_page.py (Sprint 13).
    Requires self._suggestions_inner, self._suggestions_sec, and self._suggestions_card
    to be pre-built by the host class.
    Requires signals: navigate_to, start_monitoring_requested, investigate_live_requested.
    """

    def set_suggestions(self, suggestions: list) -> None:
        """Populate and show the 'What to do next' strip."""
        while self._suggestions_inner.count():
            item = self._suggestions_inner.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not suggestions:
            self._suggestions_sec.setVisible(False)
            self._suggestions_card.setVisible(False)
            return

        for sug in suggestions[:4]:
            text     = sug.get("text", "")
            action   = sug.get("action_label", "Fix →")
            target   = sug.get("target")       # None = emit start_monitoring_requested
            priority = sug.get("priority", "medium")
            colour   = RED if priority == "high" else (AMBER if priority == "medium" else ACCENT)

            row = QWidget()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)

            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"font-size:8px; color:{colour}; background:transparent; border:none;"
            )
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
            )
            btn = QPushButton(action)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(
                f"QPushButton {{ color:{ACCENT}; font-size:11px;"
                f" background:transparent; border:none; padding:0; }}"
                f"QPushButton:hover {{ color:{ACCENT_DARK}; }}"
                f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
            )
            if target == "__live__":
                btn.clicked.connect(self.investigate_live_requested)
            elif target is not None:
                btn.clicked.connect(lambda _c=False, t=target: self.navigate_to.emit(t))
            else:
                btn.clicked.connect(self.start_monitoring_requested)

            rl.addWidget(dot)
            rl.addWidget(lbl, 1)
            rl.addWidget(btn)
            self._suggestions_inner.addWidget(row)

        self._suggestions_sec.setVisible(True)
        self._suggestions_card.setVisible(True)
