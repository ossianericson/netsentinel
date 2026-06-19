"""Scan summary sheet — slides up from bottom after every scan."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ui.styles import ACCENT, AMBER, BG_CARD, BORDER, GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, BG_HOVER

_HEIGHT = 240
_DISMISS_S = 30


class ScanSummarySheet(QFrame):
    """Non-modal 240px sheet that slides up from the bottom of the window after every scan.

    Caller must parent this to the main window and call show_sheet() after each scan.
    The sheet auto-dismisses after 30 seconds and respects a QSettings opt-out.
    """

    navigate_requested = pyqtSignal(str)  # emits page label

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("scanSummarySheet")
        self._build()
        self.setVisible(False)
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        self._tick_left = 0

    # ── Construction ─────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.setStyleSheet(
            f"QFrame#scanSummarySheet {{ background:{BG_CARD}; border-top:2px solid {ACCENT}; }}"
        )
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Countdown progress bar — 3px strip at the very top
        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(3)
        self._progress.setRange(0, _DISMISS_S)
        self._progress.setValue(_DISMISS_S)
        self._progress.setStyleSheet(
            f"QProgressBar {{ border:none; background:{BORDER}; border-radius:0; }}"
            f"QProgressBar::chunk {{ background:{ACCENT}; border-radius:0; }}"
        )
        root.addWidget(self._progress)

        body = QWidget()
        body.setStyleSheet(
            f"QWidget {{ background:{BG_CARD}; }}"
            f"QLabel {{ background:transparent; border:none; }}"
        )
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 10, 20, 10)
        bl.setSpacing(10)

        # Header
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("Scan Complete")
        hdr_lbl.setStyleSheet(f"font-size:14px; font-weight:bold; color:{TEXT_PRIMARY};")
        close_btn = QPushButton("×")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none; font-size:17px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        close_btn.clicked.connect(self._dismiss)
        hdr_row.addWidget(hdr_lbl, 1)
        hdr_row.addWidget(close_btn)
        bl.addLayout(hdr_row)

        # Section cards
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)
        self._sec_devices  = self._make_section("Devices")
        self._sec_alerts   = self._make_section("Alerts")
        self._sec_baseline = self._make_section("Baseline")
        self._sec_cves     = self._make_section("CVEs")
        for sec in (self._sec_devices, self._sec_alerts, self._sec_baseline, self._sec_cves):
            cards_row.addWidget(sec)
        cards_row.addStretch()
        bl.addLayout(cards_row)

        # Wire navigation once so signals don't stack across calls
        self._section_link(self._sec_devices).clicked.connect(
            lambda: self._navigate("Inventory")
        )
        self._section_link(self._sec_alerts).clicked.connect(
            lambda: self._navigate("Notifications")
        )
        self._section_link(self._sec_baseline).clicked.connect(
            lambda: self._navigate("Config Snapshots")
        )
        self._section_link(self._sec_cves).clicked.connect(
            lambda: self._navigate("CVE Tracker")
        )

        # Don't show again
        dns_row = QHBoxLayout()
        dns_btn = QPushButton("Don't show after scans")
        dns_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dns_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:10px; text-decoration:underline; padding:0; }}"
            f"QPushButton:hover {{ color:{TEXT_SECONDARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        dns_btn.clicked.connect(self._dont_show)
        dns_row.addStretch()
        dns_row.addWidget(dns_btn)
        bl.addLayout(dns_row)

        root.addWidget(body, 1)

    @staticmethod
    def _make_section(title: str) -> QFrame:
        f = QFrame()
        f.setObjectName("summarySection")
        f.setStyleSheet(
            f"QFrame#summarySection {{ border:1px solid {BORDER}; border-radius:6px;"
            f" background:{BG_CARD}; min-width:130px; max-width:200px; }}"
            f"QLabel {{ border:none; background:transparent; }}"
        )
        lay = QVBoxLayout(f)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        title_lbl = QLabel(title.upper())
        title_lbl.setStyleSheet(
            f"font-size:9px; font-weight:bold; color:{TEXT_MUTED}; letter-spacing:1px;"
        )
        val_lbl = QLabel("—")
        val_lbl.setObjectName("secVal")
        val_lbl.setStyleSheet(f"font-size:20px; font-weight:bold; color:{TEXT_MUTED};")
        sub_lbl = QLabel("")
        sub_lbl.setObjectName("secSub")
        sub_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY};")
        link_btn = QPushButton("View →")
        link_btn.setObjectName("secLink")
        link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        link_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none;"
            f" font-size:10px; padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        lay.addWidget(title_lbl)
        lay.addWidget(val_lbl)
        lay.addWidget(sub_lbl)
        lay.addWidget(link_btn)
        return f

    @staticmethod
    def _sec_val(sec: QFrame) -> QLabel:
        return sec.findChild(QLabel, "secVal")

    @staticmethod
    def _sec_sub(sec: QFrame) -> QLabel:
        return sec.findChild(QLabel, "secSub")

    @staticmethod
    def _section_link(sec: QFrame) -> QPushButton:
        return sec.findChild(QPushButton, "secLink")

    # ── Public API ───────────────────────────────────────────────────────────

    def show_sheet(self, *, total_devices: int, new_devices: int, missing_devices: int,
                   pending_alerts: int, baseline_diffs: int, new_cves: int) -> None:
        """Populate sections and slide the sheet up. No-ops if user opted out."""
        from PyQt6.QtCore import QSettings
        if QSettings("NetSentinel", "NetSentinel").value("scan_summary/dont_show", False, type=bool):
            return

        # Devices
        v, s = self._sec_val(self._sec_devices), self._sec_sub(self._sec_devices)
        color = GREEN if total_devices > 0 else TEXT_MUTED
        v.setStyleSheet(f"font-size:20px; font-weight:bold; color:{color};")
        v.setText(str(total_devices))
        parts = []
        if new_devices:
            parts.append(f"+{new_devices} new")
        if missing_devices:
            parts.append(f"{missing_devices} missing")
        s.setText(" · ".join(parts) if parts else "no changes")

        # Alerts
        v, s = self._sec_val(self._sec_alerts), self._sec_sub(self._sec_alerts)
        color = AMBER if pending_alerts > 0 else GREEN
        v.setStyleSheet(f"font-size:20px; font-weight:bold; color:{color};")
        v.setText(str(pending_alerts))
        s.setText("pending" if pending_alerts > 0 else "all clear")

        # Baseline
        v, s = self._sec_val(self._sec_baseline), self._sec_sub(self._sec_baseline)
        if baseline_diffs > 0:
            v.setStyleSheet(f"font-size:20px; font-weight:bold; color:{AMBER};")
            v.setText(str(baseline_diffs))
            s.setText("change(s) detected")
            self._section_link(self._sec_baseline).setVisible(True)
        else:
            v.setStyleSheet(f"font-size:20px; font-weight:bold; color:{GREEN};")
            v.setText("—")
            s.setText("no drift")
            self._section_link(self._sec_baseline).setVisible(False)

        # CVEs
        v, s = self._sec_val(self._sec_cves), self._sec_sub(self._sec_cves)
        color = RED if new_cves > 0 else TEXT_MUTED
        v.setStyleSheet(f"font-size:20px; font-weight:bold; color:{color};")
        v.setText(str(new_cves))
        s.setText("new matches" if new_cves > 0 else "no new CVEs")

        self._animate_in()
        self._tick_left = _DISMISS_S
        self._progress.setValue(self._tick_left)
        self._timer.start()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _navigate(self, page: str) -> None:
        self.navigate_requested.emit(page)
        self._dismiss()

    def _animate_in(self) -> None:
        parent = self.parent()
        if parent is None:
            return
        pw, ph = parent.width(), parent.height()
        self.setGeometry(0, ph, pw, _HEIGHT)
        self.setVisible(True)
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(QRect(0, ph, pw, _HEIGHT))
        self._anim.setEndValue(QRect(0, ph - _HEIGHT, pw, _HEIGHT))
        self._anim.start()

    def _on_tick(self) -> None:
        self._tick_left -= 1
        self._progress.setValue(self._tick_left)
        if self._tick_left <= 0:
            self._dismiss()

    def _dismiss(self) -> None:
        self._timer.stop()
        parent = self.parent()
        if parent is None:
            self.setVisible(False)
            return
        pw, ph = parent.width(), parent.height()
        self._anim.stop()
        self._anim.setStartValue(self.geometry())
        self._anim.setEndValue(QRect(0, ph, pw, _HEIGHT))
        self._anim.finished.connect(self._on_dismiss_done)
        self._anim.start()

    def _on_dismiss_done(self) -> None:
        try:
            self._anim.finished.disconnect(self._on_dismiss_done)
        except Exception:
            pass  # non-fatal
        self.setVisible(False)

    def _dont_show(self) -> None:
        from PyQt6.QtCore import QSettings
        QSettings("NetSentinel", "NetSentinel").setValue("scan_summary/dont_show", True)
        self._dismiss()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self.parent():
            self.parent().installEventFilter(self)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self.parent():
            self.parent().removeEventFilter(self)

    def eventFilter(self, obj, event) -> bool:
        if obj is self.parent() and event.type() == QEvent.Type.Resize and self.isVisible():
            parent = self.parent()
            self.setGeometry(0, parent.height() - _HEIGHT, parent.width(), _HEIGHT)
        return False
