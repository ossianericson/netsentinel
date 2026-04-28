"""
FirstRunDialog — One-time onboarding walkthrough for new users.

Shown automatically on first launch (QSettings "ui/first_run_done" not set).
User can dismiss at any slide or check "Don't show again".
Contains 4 slides that orient a new user and explicitly direct them to
Settings for colour/theme customisation.

Architecture rules observed:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O. Pure UI widget.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, BG_CARD, BG_DARK, BORDER, TEXT_PRIMARY, TEXT_SECONDARY,
    NAV_BAR, BTN_HOVER_BG, GREEN, AMBER, RED,
)

_FIRST_RUN_KEY = "ui/first_run_done"

SLIDES = [
    {
        "icon": "🛡",
        "title": "Welcome to NetSentinel",
        "body": (
            "<p>NetSentinel is a <b>professional network security scanner</b> for IT administrators, "
            "engineers, and advanced home users.</p>"
            "<p>It discovers every device on your network, detects threats like ARP spoofing and "
            "rogue access points, monitors uptime and latency, and generates evidence-grade reports "
            "for ISP disputes.</p>"
            "<p>This short guide will get you scanning in under 2 minutes.</p>"
        ),
    },
    {
        "icon": "▶",
        "title": "Your First Scan",
        "body": (
            "<p><b>1. Click Run Scan</b> in the top bar.</p>"
            "<p>NetSentinel sweeps your subnet using ARP, ICMP, and mDNS in parallel. "
            "Most home and SMB networks complete in 10–30 seconds.</p>"
            "<p><b>2. Right-click any table row</b> for instant actions: "
            "Copy IP, Port Scan, Wake-on-LAN, and How to Fix guidance.</p>"
            "<p><b>3. Hover over any risk badge</b> (CLEAN / LOW / MEDIUM / HIGH) for a plain-English "
            "explanation of what it means and what to do.</p>"
            "<p>The <b>Overview</b> page updates live as results come in — watch the tiles change.</p>"
        ),
    },
    {
        "icon": "⚙",
        "title": "Unlock More Features",
        "body": (
            "<p>The sidebar has three sections:</p>"
            "<p><b>STANDARD</b> — everything you need for day-to-day monitoring: "
            "device discovery, DNS outage detection, uptime tracking, WiFi analysis, and reports. "
            "No administrator rights needed for most of these.</p>"
            "<p><b>ADVANCED</b> — deep analysis tools: hop-by-hop MTR trace, ARP spoof detection, "
            "DHCP rogue server detection, bandwidth monitor, SNMP poller, and more. "
            "Click the <b>ADVANCED</b> header in the sidebar to expand this section.</p>"
            "<p><b>SECURITY AUDIT</b> — active scanning: SYN/UDP port scanner, OS fingerprinting, "
            "CVE lookup, and credential testing. Requires administrator rights and explicit "
            "authorisation on the target network.</p>"
        ),
    },
    {
        "icon": "🎨",
        "title": "Customise NetSentinel",
        "body": (
            "<p><b>Change the colour theme</b> at any time:</p>"
            "<p>Click <b>⚙</b> in the top bar → <b>App Settings (Theme &amp; Display)…</b>. "
            "Three themes are available: <em>Arctic Clean</em> (professional light), "
            "<em>Midnight Pro</em> (dark charcoal), and <em>Obsidian Neon</em> (true black + neon). "
            "The theme takes effect after restarting.</p>"
            "<p><b>Learn the features:</b> click <b>❓</b> in the top bar to open Help &amp; Reference — "
            "feature guide, troubleshooting scenarios, risk level explanations, and networking glossary.</p>"
            "<p>You're ready. Close this dialog and run your first scan.</p>"
        ),
    },
]


def should_show_first_run() -> bool:
    """Return True if the first-run dialog has never been completed."""
    qs = QSettings("NetSentinel", "NetSentinel")
    return not qs.value(_FIRST_RUN_KEY, False, type=bool)


def mark_first_run_done() -> None:
    """Persist that the first-run dialog has been completed."""
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue(_FIRST_RUN_KEY, True)


class FirstRunDialog(QDialog):
    """
    Four-slide onboarding walkthrough.

    Usage::
        if should_show_first_run():
            dlg = FirstRunDialog(parent=window)
            dlg.exec()
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to NetSentinel")
        self.setModal(True)
        self.setFixedSize(560, 460)
        self.setStyleSheet(
            f"QDialog{{background:{BG_CARD};border:1px solid {BORDER};}}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Progress indicator strip
        self._prog_strip = _ProgressStrip(len(SLIDES), parent=self)
        outer.addWidget(self._prog_strip)

        # Slides
        self._stack = QStackedWidget(parent=self)
        for slide_data in SLIDES:
            self._stack.addWidget(_SlideWidget(slide_data, parent=self._stack))
        outer.addWidget(self._stack, 1)

        # Bottom bar
        bottom = QFrame(parent=self)
        bottom.setStyleSheet(
            f"background:{BG_DARK};border-top:1px solid {BORDER};"
        )
        bot_l = QHBoxLayout(bottom)
        bot_l.setContentsMargins(16, 8, 16, 8)
        bot_l.setSpacing(8)

        self._chk_skip = QCheckBox("Don't show this again", parent=bottom)
        self._chk_skip.setStyleSheet(
            f"font-size:11px;color:{TEXT_SECONDARY};"
        )
        bot_l.addWidget(self._chk_skip)
        bot_l.addStretch()

        self._btn_back = QPushButton("← Back", parent=bottom)
        self._btn_back.setFixedWidth(80)
        self._btn_back.setStyleSheet(self._outline_style())
        self._btn_back.clicked.connect(self._go_back)
        bot_l.addWidget(self._btn_back)

        self._btn_next = QPushButton("Next →", parent=bottom)
        self._btn_next.setFixedWidth(100)
        self._btn_next.setStyleSheet(self._primary_style())
        self._btn_next.clicked.connect(self._go_next)
        bot_l.addWidget(self._btn_next)

        outer.addWidget(bottom)

        self._update_buttons()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _go_next(self):
        idx = self._stack.currentIndex()
        if idx < len(SLIDES) - 1:
            self._stack.setCurrentIndex(idx + 1)
            self._prog_strip.set_step(idx + 1)
            self._update_buttons()
        else:
            self._finish()

    def _go_back(self):
        idx = self._stack.currentIndex()
        if idx > 0:
            self._stack.setCurrentIndex(idx - 1)
            self._prog_strip.set_step(idx - 1)
            self._update_buttons()

    def _finish(self):
        if self._chk_skip.isChecked():
            mark_first_run_done()
        self.accept()

    def _update_buttons(self):
        idx = self._stack.currentIndex()
        self._btn_back.setVisible(idx > 0)
        is_last = idx == len(SLIDES) - 1
        self._btn_next.setText("Get Started" if is_last else "Next →")
        self._btn_next.setFixedWidth(110 if is_last else 100)

    # ── Button styles ─────────────────────────────────────────────────────────

    @staticmethod
    def _primary_style() -> str:
        return (
            f"QPushButton{{background:{ACCENT};color:{NAV_BAR};"
            f"border:1px solid {ACCENT};border-radius:4px;"
            f"padding:5px 14px;font-size:11px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT}dd;}}"
        )

    @staticmethod
    def _outline_style() -> str:
        return (
            f"QPushButton{{background:{BG_CARD};color:{ACCENT};"
            f"border:1px solid {ACCENT};border-radius:4px;"
            f"padding:5px 14px;font-size:11px;}}"
            f"QPushButton:hover{{background:{BTN_HOVER_BG};}}"
        )


class _ProgressStrip(QWidget):
    """Row of filled/empty dots showing which slide is active."""

    def __init__(self, total: int, parent: QWidget | None = None):
        super().__init__(parent)
        self._total = total
        self._step = 0
        self.setFixedHeight(28)
        self.setStyleSheet(f"background:{NAV_BAR};")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(6)

        self._dots: list[QLabel] = []
        for i in range(total):
            dot = QLabel("●", parent=self)
            dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._dots.append(dot)
            lay.addWidget(dot)
        lay.addStretch()

        step_lbl = QLabel(f"  GETTING STARTED", parent=self)
        step_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:10px;font-weight:bold;background:transparent;"
        )
        lay.addWidget(step_lbl)
        self._step_lbl = step_lbl
        self.set_step(0)

    def set_step(self, step: int):
        self._step = step
        for i, dot in enumerate(self._dots):
            if i == step:
                dot.setStyleSheet(f"color:{ACCENT};font-size:14px;background:transparent;")
            elif i < step:
                dot.setStyleSheet(f"color:{GREEN};font-size:10px;background:transparent;")
            else:
                dot.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;background:transparent;")
        self._step_lbl.setText(f"  STEP {step + 1} OF {self._total}")


class _SlideWidget(QWidget):
    """A single onboarding slide: icon + title + rich-text body."""

    def __init__(self, data: dict, parent: QWidget | None = None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{BG_CARD};")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 24, 32, 16)
        lay.setSpacing(12)

        # Icon + title row
        header = QWidget(parent=self)
        header.setStyleSheet(f"background:{BG_CARD};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)

        icon_lbl = QLabel(data["icon"], parent=header)
        icon_lbl.setStyleSheet(
            f"font-size:28px;background:transparent;color:{ACCENT};"
        )
        icon_lbl.setFixedWidth(40)
        hl.addWidget(icon_lbl)

        title_lbl = QLabel(data["title"], parent=header)
        f = QFont("Segoe UI", 15)
        f.setBold(True)
        title_lbl.setFont(f)
        title_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY};background:transparent;"
        )
        hl.addWidget(title_lbl, 1)
        lay.addWidget(header)

        # Divider
        div = QFrame(parent=self)
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color:{BORDER};background:{BORDER};")
        div.setFixedHeight(1)
        lay.addWidget(div)

        # Body
        body_lbl = QLabel(parent=self)
        body_lbl.setTextFormat(Qt.TextFormat.RichText)
        body_lbl.setText(
            f"<span style='font-size:11px;color:{TEXT_PRIMARY};"
            f"line-height:1.7;'>{data['body']}</span>"
        )
        body_lbl.setWordWrap(True)
        body_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        body_lbl.setStyleSheet(f"background:transparent;")
        lay.addWidget(body_lbl, 1)
