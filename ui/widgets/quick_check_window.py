"""
ui/widgets/quick_check_window.py — QuickCheckWindow (S8-2).

A compact 300x200 frameless floating window showing the current ambient
health status and the most relevant finding, without navigating to the
full app. Opened via Ctrl+Shift+H or the tray menu "Quick Check" action.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    AMBER,
    BG_CARD,
    BORDER,
    CARD_RADIUS,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_STATE_ICON = {"green": "✓", "amber": "⚠", "red": "✗", "unknown": "○"}
_STATE_COLOUR = {"green": GREEN, "amber": AMBER, "red": RED, "unknown": TEXT_MUTED}


class QuickCheckWindow(QFrame):
    """Standalone floating window — current health status + top finding."""

    def __init__(self, store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(300, 200)
        self.setObjectName("quickCheckWindow")
        self.setStyleSheet(
            f"QFrame#quickCheckWindow {{ background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}"
        )
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 10, 12)
        outer.setSpacing(8)

        top_row = QHBoxLayout()
        title = QLabel("Quick Check")
        title.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; letter-spacing:1px;"
        )
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        close_btn.clicked.connect(self.close)
        top_row.addWidget(title)
        top_row.addStretch()
        top_row.addWidget(close_btn)
        outer.addLayout(top_row)

        icon_row = QHBoxLayout()
        icon_row.setSpacing(10)
        self._icon_lbl = QLabel("○")
        self._icon_lbl.setFixedWidth(32)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet(
            f"font-size:26px; font-weight:bold; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        self._headline_lbl = QLabel("Gathering health data…")
        self._headline_lbl.setWordWrap(True)
        self._headline_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        icon_row.addWidget(self._icon_lbl)
        icon_row.addWidget(self._headline_lbl, 1)
        outer.addLayout(icon_row)

        finding_hdr = QLabel("TOP FINDING")
        finding_hdr.setStyleSheet(
            f"font-size:9px; color:{TEXT_SECONDARY}; background:transparent;"
            " border:none; letter-spacing:1px;"
        )
        outer.addWidget(finding_hdr)

        self._finding_lbl = QLabel("—")
        self._finding_lbl.setWordWrap(True)
        self._finding_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        outer.addWidget(self._finding_lbl, 1)
        outer.addStretch()

    def refresh(self) -> None:
        """Recompute health status and top finding from MetricStore."""
        from modules.health_score import HealthScoreCalculator
        snapshot = HealthScoreCalculator().compute(self._store)

        colour = _STATE_COLOUR.get(snapshot.state, TEXT_MUTED)
        self._icon_lbl.setText(_STATE_ICON.get(snapshot.state, "○"))
        self._icon_lbl.setStyleSheet(
            f"font-size:26px; font-weight:bold; color:{colour};"
            " background:transparent; border:none;"
        )
        self._headline_lbl.setText(snapshot.headline)
        self._finding_lbl.setText(self._top_finding(snapshot))

    def _top_finding(self, snapshot) -> str:
        if self._store is not None:
            try:
                alerts = self._store.get_recent_alerts(hours=24.0, limit=1)
                if alerts:
                    return str(alerts[0].get("message") or alerts[0].get("rule_name", "—"))
            except Exception:
                pass  # non-fatal — fall through to the health sub-text
        return snapshot.sub_text
