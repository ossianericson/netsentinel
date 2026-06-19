"""
ui/widgets/weekly_report_card.py — "Your Network Last Week" home page card (S8-3).

Shows a narrative weekly summary built by modules/weekly_report.py, once per
calendar week. Includes an "Email me this report →" action that reuses the
already-configured Email notification channel (modules/notification_channels).
"""
from __future__ import annotations

import time

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    BG_CARD,
    BG_HOVER,
    BORDER,
    CARD_RADIUS,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_LAST_SHOWN_KEY = "weekly_report/last_shown_week"


def _current_week_key() -> str:
    return time.strftime("%Y-%W", time.localtime())


class WeeklyReportCard(QWidget):
    """Home page card showing a narrative weekly network summary."""

    navigate_to    = pyqtSignal(str)   # reserved for future drill-down links
    email_requested = pyqtSignal()     # "Email me this report →" clicked

    def __init__(self, store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._setup_ui()
        self.setVisible(False)

    def _setup_ui(self) -> None:
        self.setObjectName("weeklyReportCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._frame = QFrame()
        self._frame.setObjectName("weeklyReportFrame")
        self._frame.setStyleSheet(
            f"QFrame#weeklyReportFrame {{ background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}"
        )
        frame_lay = QVBoxLayout(self._frame)
        frame_lay.setContentsMargins(14, 10, 14, 10)
        frame_lay.setSpacing(6)

        top_row = QHBoxLayout()
        title = QLabel("YOUR NETWORK LAST WEEK")
        title.setStyleSheet(
            f"font-size:10px; font-weight:700; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; letter-spacing:1.5px;"
        )
        top_row.addWidget(title)
        top_row.addStretch()
        dismiss_btn = QPushButton("×")
        dismiss_btn.setFixedSize(20, 20)
        dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:14px; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        dismiss_btn.clicked.connect(self.dismiss)
        top_row.addWidget(dismiss_btn)
        frame_lay.addLayout(top_row)

        self._bullets_lbl = QLabel("")
        self._bullets_lbl.setWordWrap(True)
        self._bullets_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        frame_lay.addWidget(self._bullets_lbl)

        btn_row = QHBoxLayout()
        self._email_btn = QPushButton("Email me this report →")
        self._email_btn.setFlat(True)
        self._email_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._email_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{ACCENT_DARK}; background:transparent; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._email_btn.clicked.connect(self.email_requested)
        btn_row.addWidget(self._email_btn)
        btn_row.addStretch()
        frame_lay.addLayout(btn_row)

        outer.addWidget(self._frame)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, force: bool = False) -> None:
        """Rebuild the card from MetricStore; shows once per calendar week."""
        if self._store is None:
            self.setVisible(False)
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        current_week = _current_week_key()
        if not force and qs.value(_LAST_SHOWN_KEY, "") == current_week:
            self.setVisible(False)
            return

        from modules.weekly_report import build_weekly_report_bullets
        plan_speed = float(qs.value("traffic/plan_speed_mbps", 0.0))
        bullets = build_weekly_report_bullets(self._store, plan_speed_mbps=plan_speed)
        if not bullets:
            self.setVisible(False)
            return

        self._bullets_lbl.setText("\n".join(f"•  {b}" for b in bullets))
        self.setVisible(True)

    def dismiss(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(_LAST_SHOWN_KEY, _current_week_key())
        self.setVisible(False)

    def current_bullets_text(self) -> str:
        return self._bullets_lbl.text()
