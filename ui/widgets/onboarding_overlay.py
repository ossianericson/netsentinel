"""
onboarding_overlay.py — Full-screen Apple-like onboarding overlay (Sprint I1+).

Sits above the entire Dashboard window as a solid white widget.  The dashboard
content is fully rendered behind it so there is no flicker when the overlay
dismisses.

Screen sequence
---------------
  0  Welcome          — "Get Started" or "Skip setup"
  1  Permission       — "Scan my network" (emits scan_requested) or Skip
  2  Scanning         — live progress bar wired to scan worker (Sprint I2)
  3  Results reveal   — device count, grade, verdict  (Sprint I2)
  4  Devices page     — "Every device, in plain English"  (Sprint I3 placeholder)
  5  Logger running   — "Done — Start exploring"  (Sprint I3 placeholder)
  6  Done             — green checkmark, auto-dismisses after 1.5 s

QSettings key: ui/onboarding_v2_done  (reused — existing users are not reshown)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QSettings, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    ACCENT_DARK,
    ACCENT_LITE,
    AMBER,
    BG_CARD,
    BORDER,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WHITE,
)

_SETTINGS_KEY = "ui/onboarding_v2_done"
_TOUR_KEY     = "tour/v1_done"


class OnboardingOverlay(QWidget):
    """Full-screen first-run onboarding overlay."""

    # Emitted when the user clicks "Scan my network" on Screen 1.
    # Connect to dashboard._start_full_scan().
    scan_requested = pyqtSignal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)

        # Solid white background so the dashboard is invisible behind the overlay
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor(BG_CARD))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # Cover the full parent window immediately
        self.setGeometry(parent.rect())
        self.raise_()

        # Keep covering the parent when it resizes
        parent.installEventFilter(self)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Central stacked widget (one page per screen)
        self._stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._stack)

        self._build_screen_0()
        self._build_screen_1()
        self._build_screen_2()
        self._build_screen_3()
        self._build_screen_4()
        self._build_screen_5()
        self._build_screen_6()

        self._stack.setCurrentIndex(0)

        # Progress tracking for Screen 2
        self._scan_progress_count = 0

    # ── Parent resize tracking ─────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self.parent() and event.type() == QEvent.Type.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._do_skip()
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            idx = self._stack.currentIndex()
            if idx == 1:
                self._on_scan_clicked()
            elif 3 <= idx <= 5:
                # Screen 2 (scanning) must not be skipped via Enter — scan must complete
                self._go_to_screen(idx + 1)
        else:
            super().keyPressEvent(e)

    # ── Screen builders ────────────────────────────────────────────────────────

    def _build_screen_0(self) -> None:
        """Screen 0: Welcome."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = _CentreCard(360)
        lay  = card.inner

        # Brand icon
        _base = (
            Path(sys._MEIPASS)
            if getattr(sys, "frozen", False)
            else Path(__file__).parent.parent.parent
        )
        _pix = QPixmap(str(_base / "assets" / "icons" / "netsentinel.png"))
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(64, 64)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background:transparent;")
        if not _pix.isNull():
            icon_lbl.setPixmap(
                _pix.scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            icon_lbl.setText("N")
            icon_lbl.setStyleSheet(
                f"background:{ACCENT}; color:{WHITE}; border-radius:12px;"
                " font-size:28px; font-weight:bold;"
            )
        lay.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(24)

        title = QLabel("Welcome to NetSentinel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size:28px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(title)
        lay.addSpacing(10)

        sub = QLabel("Your network, visible and secured")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size:14px; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        lay.addWidget(sub)
        lay.addSpacing(44)

        btn_start = _AccentButton("Get Started")
        btn_start.clicked.connect(lambda: self._go_to_screen(1))
        lay.addWidget(btn_start)
        lay.addSpacing(14)

        skip_lbl = _SkipLink("Skip setup →")
        skip_lbl.clicked.connect(self._do_skip)
        lay.addWidget(skip_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_screen_1(self) -> None:
        """Screen 1: Permission to scan."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_TopBar(active_dot=0, on_skip=self._do_skip))
        outer.addStretch(1)

        card = _CentreCard(360)
        lay  = card.inner

        from ui.widgets.scan_animation import ScanAnimationWidget
        anim = ScanAnimationWidget(mode="rings")
        anim.setFixedSize(140, 140)
        lay.addWidget(anim, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(28)

        heading = QLabel("Let's see what's on\nyour network")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size:22px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(heading)
        lay.addSpacing(12)

        body = QLabel(
            "NetSentinel will scan your local network to\n"
            "find connected devices.  Nothing leaves your device."
        )
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        lay.addWidget(body)
        lay.addSpacing(40)

        self._scan_btn = _AccentButton("Scan my network")
        self._scan_btn.clicked.connect(self._on_scan_clicked)
        lay.addWidget(self._scan_btn)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_screen_2(self) -> None:
        """Screen 2: Scanning in progress — live progress bar + radar animation."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_TopBar(active_dot=1, on_skip=self._do_skip))
        outer.addStretch(1)

        card = _CentreCard(420)
        lay  = card.inner

        from ui.widgets.scan_animation import ScanAnimationWidget
        self._s2_radar = ScanAnimationWidget(mode="radar")
        self._s2_radar.setFixedSize(140, 140)
        lay.addWidget(self._s2_radar, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(24)

        heading = QLabel("Scanning your network…")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size:22px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(heading)
        lay.addSpacing(10)

        self._s2_status = QLabel("Starting scan…")
        self._s2_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._s2_status.setStyleSheet(
            f"font-size:12px; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        self._s2_status.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed
        )
        lay.addWidget(self._s2_status)
        lay.addSpacing(18)

        self._s2_bar = QProgressBar()
        self._s2_bar.setRange(0, 100)
        self._s2_bar.setValue(0)
        self._s2_bar.setTextVisible(False)
        self._s2_bar.setFixedHeight(4)
        self._s2_bar.setStyleSheet(
            f"QProgressBar {{ background:{BORDER}; border:none; border-radius:2px; }}"
            f"QProgressBar::chunk {{ background:{ACCENT}; border-radius:2px; }}"
        )
        lay.addWidget(self._s2_bar)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_screen_3(self) -> None:
        """Screen 3: Results reveal — device count, grade, verdict."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_TopBar(active_dot=2, on_skip=self._do_skip))
        outer.addStretch(1)

        card = _CentreCard(400)
        lay  = card.inner

        # Big animated device count
        self._s3_count_lbl = QLabel("0")
        self._s3_count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._s3_count_lbl.setStyleSheet(
            f"font-size:72px; font-weight:700; color:{ACCENT};"
            " background:transparent; border:none;"
        )
        lay.addWidget(self._s3_count_lbl)

        found_lbl = QLabel("devices found")
        found_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        found_lbl.setStyleSheet(
            f"font-size:16px; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        lay.addWidget(found_lbl)
        lay.addSpacing(24)

        # Two KPI cards side-by-side
        self._s3_alerts_card = _KpiCard("Alerts", "0", GREEN)
        self._s3_grade_card  = _KpiCard("Network Grade", "—", GREEN)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        kpi_row.addWidget(self._s3_alerts_card)
        kpi_row.addWidget(self._s3_grade_card)
        kpi_container = QWidget()
        kpi_container.setLayout(kpi_row)
        kpi_container.setStyleSheet("background:transparent;")
        lay.addWidget(kpi_container)
        lay.addSpacing(20)

        # Plain-English verdict
        self._s3_verdict = QLabel("")
        self._s3_verdict.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._s3_verdict.setWordWrap(True)
        self._s3_verdict.setStyleSheet(
            f"font-size:13px; color:{TEXT_SECONDARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(self._s3_verdict)
        lay.addSpacing(32)

        btn_see = _AccentButton("See my devices")
        btn_see.clicked.connect(lambda: self._go_to_screen(4))
        lay.addWidget(btn_see)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

        # Count-up animation state
        self._s3_target_count  = 0
        self._s3_current_count = 0
        self._s3_count_timer   = QTimer(self)
        self._s3_count_timer.timeout.connect(self._tick_count_up)

    def _build_screen_4(self) -> None:
        """Screen 4: Device table spotlight — every device in plain English."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_TopBar(active_dot=3, on_skip=self._do_skip))
        outer.addStretch(1)

        card = _CentreCard(440)
        lay  = card.inner

        heading = QLabel("Every device, in plain English")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size:22px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(heading)
        lay.addSpacing(8)

        sub = QLabel("Your network at a glance — names, types and risk levels.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(sub)
        lay.addSpacing(18)

        # Mini device table
        table_wrap = QWidget()
        table_wrap.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:6px;"
        )
        table_lay = QVBoxLayout(table_wrap)
        table_lay.setContentsMargins(0, 0, 0, 0)
        table_lay.setSpacing(0)

        rows = [
            (GREEN,  "Your Computer",  "192.168.1.2",  "Clean",  GREEN,  WHITE),
            (GREEN,  "iPhone",         "192.168.1.5",  "Clean",  GREEN,  WHITE),
            (AMBER,  "Unknown device", "192.168.1.12", "Review", AMBER,  TEXT_PRIMARY),
        ]
        for i, (dot_col, name, ip, chip_txt, chip_bg, chip_fg) in enumerate(rows):
            row_w = _DevicePreviewRow(dot_col, name, ip, chip_txt, chip_bg, chip_fg)
            if i < len(rows) - 1:
                row_w.setStyleSheet(
                    f"background:{BG_CARD};"
                    f" border-bottom:1px solid {BORDER};"
                )
            table_lay.addWidget(row_w)

        lay.addWidget(table_wrap)
        lay.addSpacing(10)

        note = QLabel("Right-click any device for context-sensitive actions.")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet(
            f"font-size:11px; font-style:italic; color:{TEXT_MUTED};"
            " background:transparent; border:none;"
        )
        lay.addWidget(note)
        lay.addSpacing(28)

        btn = _AccentButton("Next  →")
        btn.clicked.connect(lambda: self._go_to_screen(5))
        lay.addWidget(btn)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_screen_5(self) -> None:
        """Screen 5: Monitoring spotlight — live RTT sparkline demo."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(_TopBar(active_dot=4, on_skip=self._do_skip))
        outer.addStretch(1)

        card = _CentreCard(420)
        lay  = card.inner

        heading = QLabel("Your connection, always visible")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(
            f"font-size:22px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(heading)
        lay.addSpacing(8)

        sub = QLabel("Latency, packet loss and outages — tracked in the background.")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(sub)
        lay.addSpacing(22)

        from ui.widgets.scan_animation import MiniSparklineWidget
        self._s5_sparkline = MiniSparklineWidget()
        self._s5_sparkline.setFixedSize(320, 72)
        lay.addWidget(self._s5_sparkline, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(8)

        stats_lbl = QLabel("RTT  ≈ 9 ms  ·  0 packets lost")
        stats_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        stats_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(stats_lbl)
        lay.addSpacing(28)

        done_btn = QPushButton("Done — Start exploring")
        done_btn.setFixedHeight(48)
        done_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        done_btn.setStyleSheet(
            f"QPushButton {{ background:{GREEN}; color:{WHITE};"
            f" border:none; border-radius:8px; font-size:15px; font-weight:600; }}"
            f"QPushButton:hover    {{ background:{GREEN}; color:{WHITE}; }}"
            f"QPushButton:pressed  {{ background:{GREEN}; color:{WHITE}; }}"
        )
        done_btn.clicked.connect(lambda: self._go_to_screen(6))
        lay.addWidget(done_btn)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    def _build_screen_6(self) -> None:
        """Screen 6: Done — animated checkmark, auto-dismisses after 2.2 s."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addStretch(1)

        card = _CentreCard(360)
        lay  = card.inner

        from ui.widgets.scan_animation import CheckmarkAnimWidget
        self._s6_checkmark = CheckmarkAnimWidget()
        lay.addWidget(self._s6_checkmark, alignment=Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(22)

        done_lbl = QLabel("You're all set")
        done_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        done_lbl.setStyleSheet(
            f"font-size:22px; font-weight:600; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;"
        )
        lay.addWidget(done_lbl)

        sub_lbl = QLabel("NetSentinel is running in the background.")
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(sub_lbl)

        _add_centre(outer, card)
        outer.addStretch(1)
        self._stack.addWidget(page)

    # ── Navigation ─────────────────────────────────────────────────────────────

    def _go_to_screen(self, n: int) -> None:
        self._stack.setCurrentIndex(n)
        # Re-raise so sibling widgets (e.g. ScanSummarySheet) can't appear on top
        self.raise_()
        if n == 6:
            self._s6_checkmark.start_anim()
            # 800 ms animation + ~1400 ms rest before dismissing
            QTimer.singleShot(2200, self._finish)

    def _on_scan_clicked(self) -> None:
        self.scan_requested.emit()
        self._go_to_screen(2)

    def _do_skip(self) -> None:
        self._go_to_screen(6)

    def _finish(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue(_SETTINGS_KEY, True)
        qs.setValue(_TOUR_KEY, True)
        if self.parent():
            self.parent().removeEventFilter(self)
        # Stop all animation timers before deletion
        for attr in ("_s3_count_timer",):
            try:
                timer = getattr(self, attr, None)
                if timer is not None:
                    timer.stop()
            except Exception:
                pass
        try:
            from ui.widgets.scan_animation import (
                ScanAnimationWidget, MiniSparklineWidget, CheckmarkAnimWidget,
            )
            for cls in (ScanAnimationWidget, MiniSparklineWidget, CheckmarkAnimWidget):
                for w in self.findChildren(cls):
                    w.stop()
        except Exception:
            pass
        self.hide()
        self.deleteLater()

    # ── Public slots wired by dashboard ────────────────────────────────────────

    @pyqtSlot(str)
    def on_scan_progress(self, msg: str) -> None:
        """Update Screen 2 with a live status message from the scan worker."""
        if self._stack.currentIndex() != 2:
            return
        self._scan_progress_count += 1
        pct = min(90, self._scan_progress_count * 12)
        # Truncate to one line — no word wrap on Screen 2 status label
        display = msg if len(msg) <= 58 else msg[:55] + "…"
        self._s2_status.setText(display)
        self._s2_bar.setValue(pct)

    @pyqtSlot(dict)
    def on_scan_complete(self, data: dict) -> None:
        """Called when M1 result arrives — complete progress bar then show Screen 3."""
        if self._stack.currentIndex() != 2:
            return

        devices = data.get("devices", [])
        count   = data.get("total_count", len(devices))
        high    = data.get("high_risk_count", 0)
        if high == 0:
            # Fallback: count devices with HIGH risk_level
            high = sum(
                1 for d in devices
                if (d.risk_level if not isinstance(d, dict) else d.get("risk_level", "")) == "HIGH"
            )

        self._s2_bar.setValue(100)
        # Re-raise now — scan result may have triggered ScanSummarySheet.show_sheet()
        self.raise_()
        # Brief pause at 100% so the user sees completion before the transition
        QTimer.singleShot(400, lambda: self._show_screen_3(count, high))

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _show_screen_3(self, count: int, high: int) -> None:
        """Populate Screen 3 data and navigate to it, starting the count-up."""
        try:
            if self._stack.currentIndex() != 2:
                return
        except RuntimeError:
            return  # overlay already deleted

        # Derive grade and verdict from high-risk count
        if high == 0:
            grade       = "A"
            grade_color = GREEN
            verdict     = "Your network looks healthy. No high-risk devices detected."
        elif high == 1:
            grade       = "B"
            grade_color = AMBER
            verdict     = "One device may need attention. Review the Devices page for details."
        elif high < 4:
            grade       = "C"
            grade_color = AMBER
            verdict     = f"{high} devices flagged as high risk. Review the Devices page for details."
        else:
            grade       = "D"
            grade_color = RED
            verdict     = f"{high} devices flagged as high risk — your network needs attention."

        alert_color = RED if high > 0 else GREEN
        self._s3_alerts_card.set_value(str(high), alert_color)
        self._s3_grade_card.set_value(grade, grade_color)
        self._s3_verdict.setText(verdict)

        # Reset and start count-up animation
        self._s3_target_count  = count
        self._s3_current_count = 0
        self._s3_count_lbl.setText("0")

        self._go_to_screen(3)

        if count > 0:
            interval = max(16, 600 // count)
            self._s3_count_timer.start(interval)
        else:
            self._s3_count_lbl.setText("0")

    def _tick_count_up(self) -> None:
        """Advance the count-up label by one step per timer tick."""
        step = max(1, self._s3_target_count // 30)
        self._s3_current_count = min(
            self._s3_target_count,
            self._s3_current_count + step,
        )
        self._s3_count_lbl.setText(str(self._s3_current_count))
        if self._s3_current_count >= self._s3_target_count:
            self._s3_count_timer.stop()


# ── Private helper widgets ─────────────────────────────────────────────────────

class _CentreCard(QWidget):
    """Fixed-width card that centres itself horizontally inside a parent layout."""

    def __init__(self, width: int, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(width)
        self.inner = QVBoxLayout(self)
        self.inner.setContentsMargins(0, 0, 0, 0)
        self.inner.setSpacing(0)
        self.inner.setAlignment(Qt.AlignmentFlag.AlignTop)


def _add_centre(parent_layout: QVBoxLayout, widget: QWidget) -> None:
    """Add *widget* centred horizontally into *parent_layout*."""
    row = QHBoxLayout()
    row.addStretch(1)
    row.addWidget(widget)
    row.addStretch(1)
    parent_layout.addLayout(row)


class _AccentButton(QPushButton):
    """Standard accent-coloured primary action button (full width)."""

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE};"
            f" border:none; border-radius:8px; font-size:15px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )


class _SkipLink(QLabel):
    """Muted clickable "Skip setup →" label that emits a clicked() signal pattern."""

    clicked = pyqtSignal()

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"font-size:13px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class _KpiCard(QWidget):
    """Small bordered KPI card with a large value and a muted label beneath it."""

    def __init__(self, label: str, value: str, color: str, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(120)
        self.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:8px;"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(4)

        self._val_lbl = QLabel(value)
        self._val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._val_lbl.setStyleSheet(
            f"font-size:28px; font-weight:700; color:{color};"
            " background:transparent; border:none;"
        )
        lay.addWidget(self._val_lbl)

        name_lbl = QLabel(label)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(name_lbl)

    def set_value(self, value: str, color: str) -> None:
        """Update the displayed value and its colour."""
        self._val_lbl.setText(value)
        self._val_lbl.setStyleSheet(
            f"font-size:28px; font-weight:700; color:{color};"
            " background:transparent; border:none;"
        )


class _TopBar(QWidget):
    """
    Progress dots + Skip link shown at the top of Screens 1–5.

    active_dot: 0-based index of the highlighted dot (Screen 1 = 0, Screen 5 = 4).
    """

    def __init__(self, active_dot: int, on_skip, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(44)
        self.setStyleSheet("background:transparent;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 0, 28, 0)
        lay.setSpacing(8)

        for i in range(5):
            is_active = i == active_dot
            dot = QLabel("●" if is_active else "○")
            dot.setStyleSheet(
                f"font-size:9px; color:{ACCENT if is_active else BORDER};"
                " background:transparent; border:none;"
            )
            lay.addWidget(dot)

        lay.addStretch(1)

        skip = _SkipLink("Skip")
        skip.clicked.connect(on_skip)
        lay.addWidget(skip)


class _RiskChip(QLabel):
    """Small pill badge showing a risk level (e.g. 'Clean', 'Review')."""

    def __init__(self, text: str, bg: str, fg: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(18)
        self.setStyleSheet(
            f"background:{bg}; color:{fg}; border:none; border-radius:8px;"
            f" font-size:10px; font-weight:600; padding:0px 8px;"
        )


class _DevicePreviewRow(QWidget):
    """Single row in the Screen 4 device table preview."""

    def __init__(
        self,
        dot_color:  str,
        device_name: str,
        ip:          str,
        chip_text:   str,
        chip_bg:     str,
        chip_fg:     str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background:{BG_CARD};")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 7, 14, 7)
        lay.setSpacing(10)

        dot = QLabel("●")
        dot.setFixedWidth(12)
        dot.setStyleSheet(
            f"font-size:10px; color:{dot_color}; background:transparent; border:none;"
        )
        lay.addWidget(dot)

        name_lbl = QLabel(device_name)
        name_lbl.setStyleSheet(
            f"font-size:12px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        lay.addWidget(name_lbl)

        ip_lbl = QLabel(ip)
        ip_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )
        lay.addWidget(ip_lbl)

        lay.addStretch(1)

        chip = _RiskChip(chip_text, chip_bg, chip_fg)
        lay.addWidget(chip)
