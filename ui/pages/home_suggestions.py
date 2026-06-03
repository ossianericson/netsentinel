"""
home_suggestions.py — _HomeSuggestionsMixin: 'What to do next' strip logic for HomePage.

Extracted from ui/pages/home_page.py (Sprint 13).
HomePage inherits from _HomeSuggestionsMixin.
"""
from __future__ import annotations

import datetime

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QMenu, QPushButton, QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_HOVER, RED,
    TEXT_PRIMARY,
)

_SNOOZE_DAYS = 7


class _HomeSuggestionsMixin:
    """Mixin providing the 'What to do next' suggestions strip for HomePage.

    Extracted from ui/pages/home_page.py (Sprint 13).
    Requires self._suggestions_inner, self._suggestions_sec, and self._suggestions_card
    to be pre-built by the host class.
    Requires signals: navigate_to, start_monitoring_requested, investigate_live_requested.
    """

    # ── Persistence helpers ───────────────────────────────────────────────────

    @staticmethod
    def _suggestion_is_suppressed(qs: QSettings, now: datetime.datetime, action_key: str) -> bool:
        """Return True if this suggestion was acted on or snoozed within 7 days."""
        for prefix in ("suggestion_acted/", "suggestion_snoozed/"):
            ts_str = qs.value(f"{prefix}{action_key}", "")
            if ts_str:
                try:
                    ts = datetime.datetime.fromisoformat(str(ts_str))
                    if (now - ts).days < _SNOOZE_DAYS:
                        return True
                except Exception:
                    pass
        return False

    def _record_suggestion_acted(self, action_key: str | None) -> None:
        if action_key:
            QSettings("NetSentinel", "NetSentinel").setValue(
                f"suggestion_acted/{action_key}",
                datetime.datetime.now().isoformat(),
            )

    def _snooze_suggestion(self, action_key: str, row_widget: QWidget) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(
            f"suggestion_snoozed/{action_key}",
            datetime.datetime.now().isoformat(),
        )
        row_widget.setVisible(False)
        # Hide the card header if all rows are now hidden
        visible = any(
            self._suggestions_inner.itemAt(i) and
            self._suggestions_inner.itemAt(i).widget() and
            self._suggestions_inner.itemAt(i).widget().isVisible()
            for i in range(self._suggestions_inner.count())
        )
        if not visible:
            self._suggestions_sec.setVisible(False)
            self._suggestions_card.setVisible(False)

    def _suggestion_context_menu(
        self, row_widget: QWidget, action_key: str | None, pos
    ) -> None:
        if not action_key:
            return
        menu = QMenu(row_widget)
        snooze_act = menu.addAction(f"Snooze {_SNOOZE_DAYS} days")
        snooze_act.triggered.connect(
            lambda: self._snooze_suggestion(action_key, row_widget)
        )
        menu.exec(row_widget.mapToGlobal(pos))

    # ── Main populate method ──────────────────────────────────────────────────

    def set_suggestions(self, suggestions: list) -> None:
        """Populate and show the 'What to do next' strip."""
        qs = QSettings("NetSentinel", "NetSentinel")
        now = datetime.datetime.now()

        # Filter out snoozed / already-acted suggestions
        active = [
            s for s in suggestions
            if not (
                s.get("action_key") and
                self._suggestion_is_suppressed(qs, now, s["action_key"])
            )
        ]

        while self._suggestions_inner.count():
            item = self._suggestions_inner.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not active:
            self._suggestions_sec.setVisible(False)
            self._suggestions_card.setVisible(False)
            return

        for sug in active[:4]:
            text       = sug.get("text", "")
            action     = sug.get("action_label", "Fix →")
            target     = sug.get("target")
            priority   = sug.get("priority", "medium")
            action_key = sug.get("action_key")
            colour     = RED if priority == "high" else (AMBER if priority == "medium" else ACCENT)

            row = QWidget()
            row.setStyleSheet("background:transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(8)

            dot = QLabel("●")
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
                btn.clicked.connect(
                    lambda _c=False, k=action_key: (
                        self._record_suggestion_acted(k),
                        self.investigate_live_requested.emit(),
                    )
                )
            elif target is not None:
                btn.clicked.connect(
                    lambda _c=False, k=action_key, t=target: (
                        self._record_suggestion_acted(k),
                        self.navigate_to.emit(t),
                    )
                )
            else:
                btn.clicked.connect(
                    lambda _c=False, k=action_key: (
                        self._record_suggestion_acted(k),
                        self.start_monitoring_requested.emit(),
                    )
                )

            rl.addWidget(dot)
            rl.addWidget(lbl, 1)
            rl.addWidget(btn)

            # Right-click → Snooze
            if action_key:
                row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                row.customContextMenuRequested.connect(
                    lambda pos, r=row, k=action_key: self._suggestion_context_menu(r, k, pos)
                )

            self._suggestions_inner.addWidget(row)

        self._suggestions_sec.setVisible(True)
        self._suggestions_card.setVisible(True)
