"""
Main Dashboard — NetSentinel network security scanner and monitor.
"""

import datetime
import html
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QByteArray, QEasingCurve, QObject, QPoint, QPropertyAnimation, QRect, QSettings, QSize, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.command_palette import CommandPalette
from ui.live_graph import LiveGraphWidget
from ui.npcap_banner import NpcapMissingBanner
from ui.styles import (
    ACCENT, ACCENT_LITE, ACCENT_DARK, ADMIN_WARN_FG, ADMIN_WARN_HOVER,
    AMBER, AMBER_BG, AUDIT_RED, BG_ALT_ROW, BG_CARD, BG_DARK, BG_HOVER, BLUE, BORDER, BORDER_MED,
    CHART_PURPLE,
    BTN_HOVER_BG, CARD_HDR_BORDER, CARD_RADIUS, GRADE_A_BG, GRADE_B_FG, GRADE_B_BG, GRADE_C_BG,
    GRADE_D_BG, GRADE_F_FG, GRADE_F_BG, GREEN, GREEN_BG,
    MAIN_STYLE, NAV_BAR, NAV_DIVIDER, PRO_BANNER_BORDER, PRO_WARN_BG,
    RED, RED_BG, RISK_BG, RISK_COLORS,
    SIDEBAR_BG, SIDEBAR_HOVER, SIDEBAR_ITEM_FG, SIDEBAR_SECTION_BG, SIDEBAR_SECTION_FG,
    SIDEBAR_SEL_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    UPDATE_BAR_BG, UPDATE_BAR_BORDER, UPDATE_BAR_FG, WHITE,
)
from modules.utils import get_offenders_path, is_admin


def _color_for_level(level: str) -> str:
    return RISK_COLORS.get(level.upper(), TEXT_SECONDARY)


def _bg_for_level(level: str) -> str:
    return RISK_BG.get(level.upper(), BG_CARD)


class RiskBadge(QLabel):
    def __init__(self, level: str, parent=None):
        super().__init__(level.upper(), parent)
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"color:{color}; background:{bg}; border:1px solid {color};"
            "border-radius:3px; padding:1px 8px; font-weight:bold; font-size:10px;"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)


class VerdictPanel(QFrame):
    """Traffic-light coloured plain-English verdict box."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("verdictFrame")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self._title = QLabel("Overall Verdict")
        self._title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))

        self._text = QLabel("Run a scan to see results.")
        self._text.setObjectName("verdictText")
        self._text.setWordWrap(True)
        self._text.setFont(QFont("Segoe UI", 11))
        self._text.setTextFormat(Qt.TextFormat.PlainText)

        self._layout.addWidget(self._title)
        self._layout.addWidget(self._text)
        self._set_level("UNKNOWN")

    def _set_level(self, level: str):
        color = _color_for_level(level)
        bg    = _bg_for_level(level)
        self.setStyleSheet(
            f"QFrame#verdictFrame {{ background:{bg}; border-left:4px solid {color};"
            f"border-radius:0px; border-top:1px solid {BORDER};"
            f"border-right:1px solid {BORDER}; border-bottom:1px solid {BORDER}; }}"
        )
        self._title.setStyleSheet(f"color:{color}; font-weight:bold; padding:6px 12px 2px 12px;")
        self._text.setStyleSheet(f"color:{TEXT_PRIMARY}; padding:2px 12px 8px 12px; font-size:11px;")

    def update(self, text: str, level: str = "UNKNOWN"):
        self._set_level(level)
        self._text.setText(text)


# ─── Module Tab Helpers ─────────────────────────────────────────────────────

def _make_scroll_area(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setStyleSheet("QScrollArea { border: none; }")
    return sa


def _table(headers: list) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(True)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.horizontalHeader().setDefaultSectionSize(120)
    t.setShowGrid(True)
    t.verticalHeader().setDefaultSectionSize(24)  # compact row height
    return t


def _add_row(table: QTableWidget, values: list, level: str = "CLEAN"):
    from PyQt6.QtGui import QColor
    row = table.rowCount()
    table.insertRow(row)
    color = _color_for_level(level)
    for col, val in enumerate(values):
        item = QTableWidgetItem(str(val))
        # Only colorise the text for high-risk rows; normal rows use default dark text
        if level in ("HIGH", "STORM", "MEDIUM", "WARNING"):
            item.setForeground(QColor(color))
        table.setItem(row, col, item)


def _add_skeleton_rows(table: QTableWidget, count: int = 8) -> None:
    """Insert placeholder rows while a scan worker is running."""
    from PyQt6.QtGui import QColor
    from ui.styles import TEXT_MUTED as _TM
    col_count = table.columnCount()
    for _ in range(count):
        row = table.rowCount()
        table.insertRow(row)
        for col in range(col_count):
            item = QTableWidgetItem("—")
            item.setForeground(QColor(_TM))
            table.setItem(row, col, item)


def _empty_state_widget(icon: str, headline: str, body: str,
                        cta_label: "str | None", cta_action: "callable | None") -> "QWidget":
    """Reusable empty-state panel: icon + headline + body text + optional CTA button."""
    from PyQt6.QtWidgets import QWidget as _W, QVBoxLayout as _VL, QHBoxLayout as _HL, QLabel as _L, QPushButton as _B
    from PyQt6.QtCore import Qt as _Qt
    from ui.styles import ACCENT as _AC, TEXT_PRIMARY as _TP, TEXT_SECONDARY as _TS
    w = _W()
    vl = _VL(w)
    vl.setContentsMargins(32, 32, 32, 32)
    vl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic = _L(icon)
    ic.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet(f"font-size:30px; background:transparent; border:none;")
    hd = _L(headline)
    hd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    hd.setStyleSheet(f"font-size:13px; font-weight:bold; color:{_TP}; background:transparent; border:none;")
    bd = _L(body)
    bd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    bd.setWordWrap(True)
    bd.setStyleSheet(f"font-size:11px; color:{_TS}; background:transparent; border:none;")
    vl.addWidget(ic)
    vl.addWidget(hd)
    vl.addSpacing(4)
    vl.addWidget(bd)
    if cta_label and cta_action:
        vl.addSpacing(10)
        btn = _B(cta_label)
        btn.setFixedHeight(28)
        btn.setCursor(_Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:{_AC}; color:#fff; border:none;"
            f" border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }}"
            f"QPushButton:hover {{ background:#1a6fc4; }}"
        )
        btn.clicked.connect(cta_action)
        hl = _HL()
        hl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(btn)
        vl.addLayout(hl)
    return w


def _error_state_widget(message: str, retry_fn: "callable") -> "QWidget":
    """Reusable error-state panel: ⚠ icon + message + Retry button."""
    from PyQt6.QtWidgets import QWidget as _W, QVBoxLayout as _VL, QHBoxLayout as _HL, QLabel as _L, QPushButton as _B
    from PyQt6.QtCore import Qt as _Qt
    from ui.styles import AMBER as _AM, TEXT_PRIMARY as _TP, TEXT_SECONDARY as _TS
    w = _W()
    vl = _VL(w)
    vl.setContentsMargins(32, 32, 32, 32)
    vl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic = _L("⚠")
    ic.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet(f"font-size:28px; color:{_AM}; background:transparent; border:none;")
    hd = _L(message)
    hd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    hd.setWordWrap(True)
    hd.setStyleSheet(f"font-size:12px; color:{_TP}; background:transparent; border:none;")
    vl.addWidget(ic)
    vl.addSpacing(6)
    vl.addWidget(hd)
    if retry_fn:
        vl.addSpacing(10)
        btn = _B("Retry")
        btn.setFixedHeight(28)
        btn.setCursor(_Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{_AM}; border:1px solid {_AM};"
            f" border-radius:4px; font-size:11px; padding:0 16px; }}"
            f"QPushButton:hover {{ background:{_AM}22; }}"
        )
        btn.clicked.connect(retry_fn)
        hl = _HL()
        hl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(btn)
        vl.addLayout(hl)
    return w


def _make_card(title: str) -> tuple:
    """
    Build a standard enterprise card frame.
    Returns (card_QFrame, body_QVBoxLayout) — add content widgets to body_layout.
    Card: white BG, 0px border-radius, navy header bar (32px) with uppercase title.
    """
    from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel
    card = QFrame()
    card.setObjectName("card")
    card_lay = QVBoxLayout(card)
    card_lay.setContentsMargins(0, 0, 0, 0)
    card_lay.setSpacing(0)

    hdr = QFrame()
    hdr.setObjectName("cardHeader")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 0, 10, 0)
    hdr_lay.setSpacing(0)
    t = QLabel(title.upper())
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        "letter-spacing:0.5px; background:transparent; border:none;"
    )
    hdr_lay.addWidget(t)
    hdr_lay.addStretch()
    card_lay.addWidget(hdr)

    body_lay = QVBoxLayout()
    body_lay.setContentsMargins(0, 0, 0, 0)
    body_lay.setSpacing(0)
    card_lay.addLayout(body_lay, 1)

    return card, body_lay


def _page_header(title: str, subtitle: str = "") -> QFrame:
    """
    Returns a QFrame header container with 16/20/12px breathing room and a
    1px bottom divider.  title 18px bold TEXT_PRIMARY, subtitle 11px TEXT_SECONDARY.
    """
    container = QFrame()
    container.setObjectName("pageHeader")
    container.setStyleSheet(
        f"QFrame#pageHeader {{ background: transparent; border: none;"
        f" border-bottom: 1px solid {BORDER}; }}"
    )
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;"
    )
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;"
        )
        vbox.addWidget(s)
    return container


# ─── Activity-Rail Navigation widgets ────────────────────────────────────────

# Lucide icon library (MIT) — 24×24 viewBox, stroke="currentColor"
_LUCIDE: dict = {
    "home": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'
        '<polyline points="9 22 9 12 15 12 15 22"/></svg>'
    ),
    "activity": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>'
    ),
    "grid": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/>'
        '<rect x="14" y="3" width="7" height="7"/>'
        '<rect x="14" y="14" width="7" height="7"/>'
        '<rect x="3" y="14" width="7" height="7"/></svg>'
    ),
    "monitor": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2"/>'
        '<line x1="8" y1="21" x2="16" y2="21"/>'
        '<line x1="12" y1="17" x2="12" y2="21"/></svg>'
    ),
    "shield": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>'
    ),
    "bar-chart": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><line x1="12" y1="20" x2="12" y2="10"/>'
        '<line x1="18" y1="20" x2="18" y2="4"/>'
        '<line x1="6" y1="20" x2="6" y2="16"/></svg>'
    ),
    "book-open": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>'
        '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>'
    ),
    "settings": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><circle cx="12" cy="12" r="3"/>'
        '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06'
        'a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09'
        'A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06'
        'A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09'
        'A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06'
        'A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09'
        'a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06'
        'A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09'
        'a1.65 1.65 0 0 0-1.51 1z"/></svg>'
    ),
    "search": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><circle cx="11" cy="11" r="8"/>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
    ),
    "wifi": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"/>'
        '<path d="M1.42 9a16 16 0 0 1 21.16 0"/>'
        '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
        '<line x1="12" y1="20" x2="12.01" y2="20"/></svg>'
    ),
    "network": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><rect x="16" y="16" width="6" height="6" rx="1"/>'
        '<rect x="2" y="16" width="6" height="6" rx="1"/>'
        '<rect x="9" y="2" width="6" height="6" rx="1"/>'
        '<path d="M5 16v-3a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v3"/>'
        '<path d="M12 12V8"/></svg>'
    ),
    "zap": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>'
    ),
    "server": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/>'
        '<rect x="2" y="14" width="20" height="8" rx="2"/>'
        '<line x1="6" y1="6" x2="6.01" y2="6"/>'
        '<line x1="6" y1="18" x2="6.01" y2="18"/></svg>'
    ),
    "map-pin": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>'
        '<circle cx="12" cy="10" r="3"/></svg>'
    ),
    "terminal": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/>'
        '<line x1="12" y1="19" x2="20" y2="19"/></svg>'
    ),
    "layers": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/>'
        '<polyline points="2 17 12 22 22 17"/>'
        '<polyline points="2 12 12 17 22 12"/></svg>'
    ),
    "globe": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><circle cx="12" cy="12" r="10"/>'
        '<line x1="2" y1="12" x2="22" y2="12"/>'
        '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10'
        ' 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
    ),
    "log": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12'
        'a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>'
        '<line x1="16" y1="13" x2="8" y2="13"/>'
        '<line x1="16" y1="17" x2="8" y2="17"/>'
        '<polyline points="10 9 9 9 8 9"/></svg>'
    ),
    "alert-triangle": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94'
        'a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
        '<line x1="12" y1="9" x2="12" y2="13"/>'
        '<line x1="12" y1="17" x2="12.01" y2="17"/></svg>'
    ),
    "eye": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>'
        '<circle cx="12" cy="12" r="3"/></svg>'
    ),
    "pin": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"/>'
        '<path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1'
        'a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9'
        'A2 2 0 0 0 5 15.24z"/></svg>'
    ),
    "x": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/>'
        '<line x1="6" y1="6" x2="18" y2="18"/></svg>'
    ),
    "chevron-right": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>'
    ),
    "scan": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M3 7V5a2 2 0 0 1 2-2h2"/>'
        '<path d="M17 3h2a2 2 0 0 1 2 2v2"/>'
        '<path d="M21 17v2a2 2 0 0 1-2 2h-2"/>'
        '<path d="M7 21H5a2 2 0 0 1-2-2v-2"/>'
        '<line x1="7" y1="12" x2="17" y2="12"/></svg>'
    ),
    "lock": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/>'
        '<path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>'
    ),
    "tool": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0'
        'l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91'
        'a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
    ),
    "bell": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>'
        '<path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>'
    ),
    "cpu": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/>'
        '<rect x="9" y="9" width="6" height="6"/>'
        '<line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/>'
        '<line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/>'
        '<line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/>'
        '<line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>'
    ),
    "info": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"'
        ' fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'
        ' stroke-linejoin="round"><circle cx="12" cy="12" r="10"/>'
        '<line x1="12" y1="16" x2="12" y2="12"/>'
        '<line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    ),
}


def _make_nav_icon(icon_name: str, size: int = 20, color: str = "#A8B8C8") -> QIcon:
    """Render a Lucide SVG string to a QIcon at the given pixel size and colour."""
    from PyQt6.QtSvg import QSvgRenderer
    svg_str = _LUCIDE.get(icon_name, _LUCIDE["activity"])
    svg_str = svg_str.replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return QIcon(pix)


@dataclass
class _NavEntry:
    label: str
    page: "QWidget"
    action: Optional[Callable] = None
    admin_required: bool = False
    audit_item: bool = False
    pinned: bool = False


class _RailButton(QPushButton):
    """48×58 icon + label button for the activity rail."""

    _COLOR_NORMAL = "#A8B8C8"
    _COLOR_ACTIVE = "#FFFFFF"
    _LABEL_COLOR  = "#6B7A8D"

    def __init__(self, icon_name: str, tooltip: str, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        # First word of section name, max 9 chars — shown below the icon
        self._short_label = (tooltip.split()[0]) if tooltip else ""
        self._badge_color: str = ""
        self._badge_count: str = ""   # non-empty → numeric red pill overrides dot
        self._left_dot: str = ""      # POLISH-1: monitor state dot on left edge
        self.setCheckable(True)
        self.setFixedSize(56, 58)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_icon()
        self.setStyleSheet(
            "QPushButton {"
            "  background: transparent;"
            "  border: none;"
            "  border-radius: 0px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(255,255,255,0.07);"
            "}"
            f"QPushButton:checked {{"
            f"  background: rgba(255,255,255,0.10);"
            f"}}"
        )

    def set_badge(self, value) -> None:
        """Set or clear the badge.

        Pass a positive int/str digit to show a red numeric pill.
        Pass a colour string (hex) to show a plain status dot.
        Pass 0, empty string, or None to clear.
        """
        if value and str(value).isdigit() and int(value) > 0:
            self._badge_count = str(value)
            self._badge_color = ""
        elif value and not str(value).isdigit():
            self._badge_color = str(value)
            self._badge_count = ""
        else:
            self._badge_color = ""
            self._badge_count = ""
        self.update()

    def set_left_dot(self, color: str) -> None:
        """POLISH-1: set or clear the monitor-state dot on the left edge.

        Pass a hex colour to show; pass empty string to clear.
        """
        self._left_dot = color or ""
        self.update()

    def paintEvent(self, event):
        from PyQt6.QtGui import QPainter, QColor, QFont, QFontMetrics, QPen
        from PyQt6.QtCore import QRect, QRectF
        # QSS background + hover/checked effects
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Accent bar — painted after QSS so it sits on top of background
        if self.isChecked():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRect(0, 10, 3, 38)   # spans the 48px icon zone, inset 10px top/bottom

        # POLISH-1: left-edge monitor state dot — 6px, flush left, icon-zone centre
        # Positioned at x=4 to clear the 3px accent bar; y=22 centres it in the icon zone
        if self._left_dot:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._left_dot))
            p.drawEllipse(QRectF(4, 22, 6, 6))

        # Numeric red pill badge — top-right corner
        if self._badge_count:
            badge_font = QFont("Segoe UI", 7)
            badge_font.setBold(True)
            p.setFont(badge_font)
            fm = QFontMetrics(badge_font)
            text_w = fm.horizontalAdvance(self._badge_count)
            pill_w = max(15, text_w + 6)
            pill_h = 14
            pill_x = self.width() - pill_w - 2
            pill_y = 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(RED))
            p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 7, 7)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(QRect(pill_x, pill_y, pill_w, pill_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       self._badge_count)
        # Plain colour dot badge — top-right corner
        elif self._badge_color:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._badge_color))
            p.drawEllipse(self.width() - 11, 3, 7, 7)

        # Short label below the icon
        font = QFont("Segoe UI", 7)
        p.setFont(font)
        lbl_color = self._COLOR_ACTIVE if self.isChecked() else SIDEBAR_ITEM_FG
        p.setPen(QColor(lbl_color))
        fm = QFontMetrics(font)
        text = fm.elidedText(self._short_label, Qt.TextElideMode.ElideRight, self.width() - 4)
        p.drawText(QRect(0, 46, self.width(), 12),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   text)
        p.end()

    def _refresh_icon(self):
        color = self._COLOR_ACTIVE if self.isChecked() else self._COLOR_NORMAL
        self.setIcon(_make_nav_icon(self._icon_name, 20, color))
        self.setIconSize(QSize(20, 20))

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._refresh_icon()


class _FlyoutItem(QPushButton):
    """Single row in the flyout panel — checkable, left-aligned, pin-aware."""

    pin_toggled = pyqtSignal(str, bool)   # (label, is_pinned_now)

    def __init__(self, label: str, pinned: bool = False, danger: bool = False, parent=None):
        super().__init__(label, parent)
        self._label = label
        self._pinned = pinned
        self._dot: str = ""
        self.setCheckable(True)
        self.setMinimumHeight(28)
        self.setMaximumHeight(36)
        self.setMinimumWidth(280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_ctx_menu)
        _fg = AUDIT_RED if danger else SIDEBAR_ITEM_FG
        self.setStyleSheet(
            f"QPushButton {{"
            f"  text-align: left; padding: 0 14px;"
            f"  background: transparent; color: {_fg};"
            f"  border: none; font-size: 11px;"
            f"}}"
            f"QPushButton:hover {{ background: {SIDEBAR_HOVER}; color: {WHITE}; }}"
            f"QPushButton:checked {{ background: {SIDEBAR_SEL_BG}; color: {WHITE}; }}"
        )

    def set_dot(self, color: str) -> None:
        """Set or clear the status dot. Pass empty string to clear."""
        self._dot = color or ""
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self._dot:
            from PyQt6.QtGui import QPainter, QColor
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._dot))
            p.drawEllipse(self.width() - 14, (self.height() - 7) // 2, 7, 7)
            p.end()

    def _show_ctx_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        txt = "Unpin from Quick Access" if self._pinned else "Pin to Quick Access"
        menu.addAction(txt).triggered.connect(self._toggle_pin)
        menu.exec(self.mapToGlobal(pos))

    def _toggle_pin(self):
        self._pinned = not self._pinned
        self.pin_toggled.emit(self._label, self._pinned)

    @property
    def item_label(self) -> str:
        return self._label


class _FlyoutPanel(QWidget):
    """280px animated slide-in panel that appears next to the activity rail."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setMaximumWidth(0)
        self.setStyleSheet(f"background: {SIDEBAR_BG};")

        self._anim = QPropertyAnimation(self, b"maximumWidth")
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._on_anim_finished)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar: section title + pin toggle
        hdr = QWidget()
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"background: {SIDEBAR_SECTION_BG}; border-bottom: 1px solid {NAV_DIVIDER};"
        )
        hlay = QHBoxLayout(hdr)
        hlay.setContentsMargins(12, 0, 4, 0)
        hlay.setSpacing(4)
        self._title_lbl = QLabel()
        self._title_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 600;"
            f" letter-spacing: 1px; background: transparent; border: none;"
        )
        self._pin_btn = QPushButton("⊞")
        self._pin_btn.setFixedSize(24, 24)
        self._pin_btn.setCheckable(True)
        self._pin_btn.setToolTip("Pin panel open")
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {TEXT_SECONDARY}; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {WHITE}; }}"
            f"QPushButton:checked {{ color: {ACCENT}; }}"
        )
        hlay.addWidget(self._title_lbl, 1)
        hlay.addWidget(self._pin_btn)
        outer.addWidget(hdr)

        # Scrollable item list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; }"
        )
        self._item_container = QWidget()
        self._item_layout = QVBoxLayout(self._item_container)
        self._item_layout.setContentsMargins(0, 4, 0, 4)
        self._item_layout.setSpacing(0)
        self._item_layout.addStretch()
        scroll.setWidget(self._item_container)
        outer.addWidget(scroll, 1)

        # Pin hint footer
        _hint = QLabel("Right-click any page to pin it ★")
        _hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; padding: 4px 0;"
            f" background: {SIDEBAR_BG}; border: none;"
            f" border-top: 1px solid {NAV_DIVIDER};"
        )
        outer.addWidget(_hint)

        self._items: dict = {}   # label -> _FlyoutItem

    @property
    def is_pinned(self) -> bool:
        return self._pin_btn.isChecked()

    def load_section(
        self,
        title: str,
        entries: list,
        active_label: str,
        on_click: Callable,
        on_pin_toggle: Callable,
    ) -> None:
        while self._item_layout.count() > 1:
            w = self._item_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self._items.clear()
        self._title_lbl.setText(title.upper())
        for label, pinned, danger in entries:
            btn = _FlyoutItem(label, pinned, danger)
            btn.setChecked(label == active_label)
            btn.clicked.connect(
                lambda _c, b=btn, lbl=label: self._on_item_clicked(b, lbl, on_click)
            )
            btn.pin_toggled.connect(on_pin_toggle)
            self._item_layout.insertWidget(self._item_layout.count() - 1, btn)
            self._items[label] = btn

    def _on_item_clicked(self, btn: "_FlyoutItem", label: str, on_click) -> None:
        """NAV-4: flash checked highlight for 120ms then navigate."""
        btn.setChecked(True)
        from PyQt6.QtCore import QTimer as _QT
        _QT.singleShot(120, lambda: on_click(label))

    def set_active(self, label: str) -> None:
        for lbl, btn in self._items.items():
            btn.setChecked(lbl == label)

    def apply_dot(self, label: str, color: str) -> None:
        """Set status dot on the named item if it's currently visible."""
        btn = self._items.get(label)
        if btn:
            btn.set_dot(color)

    def open(self) -> None:
        self._anim.stop()
        # setMinimumWidth forces the parent layout to allocate full width;
        # without this the flyout is clipped to whatever the rail panel was given.
        self.setMinimumWidth(280)
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(280)
        self.setVisible(True)
        self._anim.start()

    def close_panel(self) -> None:
        self._anim.stop()
        self.setMinimumWidth(0)
        self._anim.setStartValue(self.maximumWidth())
        self._anim.setEndValue(0)
        self._anim.start()

    def _on_anim_finished(self) -> None:
        if self.maximumWidth() == 0:
            self.setVisible(False)


class _CanvasClickFilter(QObject):
    """Event filter on the content wrapper — requests flyout close on canvas click."""

    close_requested = pyqtSignal()

    def eventFilter(self, obj, event) -> bool:
        from PyQt6.QtCore import QEvent
        if event.type() == QEvent.Type.MouseButtonPress:
            self.close_requested.emit()
        return False


class _ClickLabel(QLabel):
    """QLabel that emits clicked() when pressed — used for status-bar pulse segments."""
    clicked = pyqtSignal()

    def mousePressEvent(self, ev):
        self.clicked.emit()
        super().mousePressEvent(ev)


# ── Per-page contextual help content ─────────────────────────────────────────
# Shown in the "?" strip below the breadcrumb.
# Keys are exact nav page labels. "what" = 1-2 sentences. "hidden" = bullet list.

_PAGE_HELP: dict[str, dict] = {
    # ── Getting Started ────────────────────────────────────────────────────────
    "Home": {
        "what": "Your network at a glance — live status, device count, speed, and stability.",
        "hidden": [
            "The 'What to do next' strip surfaces features you haven't tried yet — it updates as you explore.",
            "When the logger detects something interesting, an amber card appears here. Click 'Investigate →' to open a live Lab exercise.",
            "Click the mini cards (Speed, Stability, Devices) to jump directly to those pages.",
        ],
    },
    "Overview": {
        "what": "Live summary of all scan results — device list, graded health, port scan summary, and bandwidth at a glance.",
        "hidden": [
            "The 'Share Card' button exports a 520×300 summary card as PNG, clipboard image, or standalone HTML — useful for ISP escalations.",
            "All tiles here update live from background workers — you don't need to re-scan to see fresh data.",
        ],
    },
    "Speed Test": {
        "what": "Measures your actual download speed using Ookla CLI, speedtest-cli, or a built-in pure-Python fallback.",
        "hidden": [
            "Results are logged to the Network Logger so you can track speed changes over days or weeks.",
            "The three-tier engine falls through automatically — if Ookla is not installed, speedtest-cli is tried, then the built-in fallback.",
        ],
    },
    "DNS & Stability": {
        "what": "Measures DNS resolver latency over time and detects outages as short as one ping interval.",
        "hidden": [
            "The 'Explain This' strip explains DNS and why slow DNS makes everything feel slow even on a fast connection.",
            "Outage timestamps are recorded even when the logger is running in the background with no visible indicator.",
            "Switch to the 'DNS Benchmark' tab to compare Cloudflare, Google, and Quad9 against your system resolver side-by-side.",
        ],
    },
    "Diagnose": {
        "what": "One-click root-cause analysis — sequences network, storm, rogue device, and STP checks to surface the most likely cause of your problem.",
        "hidden": [
            "Pick a symptom tile (Slow / Dropping / Can't Connect) before running — this scopes the checks to the most relevant modules.",
            "The 'Do this first' priority card at the top is the single most actionable finding. Fix that before looking at the rest.",
        ],
    },
    # ── Discover ───────────────────────────────────────────────────────────────
    "Devices": {
        "what": "Every device on your subnet with IP, MAC, vendor, hostname, and risk level.",
        "hidden": [
            "Right-click any row for quick actions: How to Fix, block from network, view availability history.",
            "The 'Explain This' strip at the bottom explains how ARP works and what a rogue device is.",
            "Click the column headers to sort by IP, risk level, or vendor.",
            "Vendor and model are resolved offline using the OUI database — no internet call needed.",
        ],
    },
    "WiFi Networks": {
        "what": "Scans visible SSIDs for hidden networks, rogue APs, WPS-enabled routers, and co-channel interference.",
        "hidden": [
            "Hidden SSIDs appear as '<hidden>' — a rogue AP advertising no SSID is still listed here.",
            "WPS-enabled networks are flagged because WPS PIN attacks can bypass WPA2 in minutes.",
            "Co-channel interference is flagged when two strong APs on the same channel are detected — switch one to a non-overlapping channel.",
        ],
    },
    "WiFi Heatmap": {
        "what": "Visual signal-strength heatmap — drag the floor plan, click positions to capture dBm readings.",
        "hidden": [
            "Click any point on the floor plan to record the current signal level at that position — walk through rooms while clicking.",
            "Red = strong, blue = weak. Areas below −75 dBm are likely to cause connection drops.",
            "Export the heatmap as PNG to attach to a support ticket or share with a Wi-Fi installer.",
        ],
    },
    "Network Map": {
        "what": "Auto-generated topology diagram showing how discovered devices relate to each other.",
        "hidden": [
            "The topology is rebuilt after every scan — devices are positioned based on ARP and gateway relationships.",
            "Click any node to jump to that device's row in the Devices page.",
        ],
    },
    "DHCP Leases": {
        "what": "Live view of all active DHCP leases on your network — flags unexpected or rogue DHCP servers.",
        "hidden": [
            "A rogue DHCP server flag means two devices are handing out IP addresses — this can cause connection failures across the whole network.",
            "Lease data is read from the OS lease table — no packet capture needed, works without Npcap.",
        ],
    },
    "Home Automation": {
        "what": "Device join/leave events, alerts, and per-device uptime states forwarded to Home Assistant or an MQTT broker.",
        "hidden": [
            "Set up the MQTT broker address in Settings first — the page will show 'not connected' until that is done.",
            "Device presence events arrive within seconds of a device appearing or disappearing on the network.",
        ],
    },
    # ── Monitor ────────────────────────────────────────────────────────────────
    "Live Bandwidth": {
        "what": "Rolling 60-second upload/download chart per network interface — updates every second.",
        "hidden": [
            "Switch between interfaces using the dropdown if you have both Wi-Fi and Ethernet active.",
            "Spikes that correlate with Broadcast Storm events help confirm a storm is saturating the link.",
        ],
    },
    "Bandwidth Usage": {
        "what": "Per-device bandwidth usage collected during packet capture sessions.",
        "hidden": [
            "Packet capture requires Npcap on Windows — install it from npcap.com for this tab to populate.",
            "Click a row to see the breakdown of protocols that device is using.",
        ],
    },
    "Active Connections": {
        "what": "Process-to-socket map showing which app owns each open connection — one-click firewall block per process.",
        "hidden": [
            "Click 'Block' on any process to add a Windows Firewall outbound rule — you can unblock it from the same row.",
            "Processes with many connections to non-local IPs are worth investigating — click the destination IP to run a WHOIS.",
            "The list refreshes every few seconds automatically — watch for processes that appear briefly and disappear.",
        ],
    },
    "Availability History": {
        "what": "RTT and UP/DEGRADED/DOWN state charts per device — 1 h / 12 h / 24 h / 7 d zoom.",
        "hidden": [
            "Data accumulates as long as the Network Logger is running — start it early and leave it on for evidence-grade output.",
            "Use the 7-day view to find patterns: if a device drops every night at 2 AM, that is a strong clue about what is rebooting it.",
        ],
    },
    "Geolocation Map": {
        "what": "Offline world map showing where internet-facing IPs are located — no API key, no external calls.",
        "hidden": [
            "Uses the MaxMind GeoLite2-City database bundled with the app — all lookups are local.",
            "IPs that map to unexpected countries may indicate traffic going through a VPN exit node or a compromised proxy.",
        ],
    },
    "IPv6 Devices": {
        "what": "Discovers IPv6-addressed devices on your network using NDP and multicast probes.",
        "hidden": [
            "Many home networks have IPv6 active without the owner knowing — this tab reveals the full device census.",
            "Link-local addresses (fe80::) are not routable — global unicast addresses (2xxx:) are the ones exposed to the internet.",
        ],
    },
    "Network Logger": {
        "what": "'Log Sources' tab: configure what gets recorded (ping, DNS, modem, mesh, ARP, Syslog, SNMP) and start/stop logging. 'Activity Log' tab: unified chronological viewer for all sources.",
        "hidden": [
            "The logger runs even when the app window is minimised — check the status bar dot to confirm it is active.",
            "CSV files are saved to the logs/ folder in the app data directory — you can open them in Excel for custom analysis.",
            "Enable 'Auto-start on launch' so logging begins the moment the app opens without any manual step.",
            "Any row with an ARP event shows a '▶ ARP' button — click it to jump to the Protocol Visualizer pre-loaded with that event.",
            "Filter the Activity Log by hostname using the filter box — useful on busy networks.",
        ],
    },
    "Service Heartbeat": {
        "what": "Monitors specific hosts and ports on a schedule — alerts when a service goes down.",
        "hidden": [
            "Add your router's management page, NAS, or home server here to get notified the moment they become unreachable.",
            "Heartbeat checks run on their own schedule independent of the main scanner — no need to rescan to refresh them.",
        ],
    },
    # ── Reports ────────────────────────────────────────────────────────────────
    "Network Grade": {
        "what": "Scores your network A–F across speed, latency, DNS, packet loss, device security, and STP health.",
        "hidden": [
            "Each grade dimension has an actionable 'Fix tip' — expand the row to see what to do.",
            "Run 'Grade My Network' after making changes to see whether they improved the score.",
        ],
    },
    "Network Health Report": {
        "what": "Generates a standalone HTML report with MTR hop table, packet-loss %, DNS latency, and timestamped outage log. Great for ISP support tickets.",
        "hidden": [
            "The report is a single self-contained HTML file — email it or attach it to a support ticket with no extra files needed.",
            "Run the Network Logger for at least an hour before generating the report so the outage log has enough data.",
        ],
    },
    "Network Doc": {
        "what": "Auto-assembled network documentation page — device list, cert inventory, topology diagram, and accumulated port scan results.",
        "hidden": [
            "Export as PDF or HTML to hand to an IT consultant or keep as a record before making network changes.",
            "The device count and cert status update automatically after every scan — you don't need to regenerate manually.",
        ],
    },
    "IP Calculator": {
        "what": "Subnet calculator with CIDR notation reference, subnetting rules, and address class tables.",
        "hidden": [
            "Enter any IP/prefix (e.g. 192.168.1.50/24) to instantly see the network address, broadcast, usable range, and host count.",
            "The reference panels explain CIDR and subnetting concepts — useful if you are studying for Network+ or CCNA.",
        ],
    },
    "Notifications": {
        "what": "Configure where alerts go — desktop notifications, webhook URLs, and email targets.",
        "hidden": [
            "Webhooks can point to Slack, Discord, or any service with an incoming webhook URL — no plugin needed.",
            "Test the webhook before relying on it — use the 'Send Test' button to confirm delivery.",
        ],
    },
    # ── Analysis ───────────────────────────────────────────────────────────────
    "Connectivity Tests": {
        "what": "One-click ping, DNS, HTTP, and MTR tests with a plain-English verdict.",
        "hidden": [
            "MTR (traceroute) shows exactly which hop is introducing packet loss — useful for ISP complaints.",
            "The status bar 'Online/Offline' dot reflects the last logger result, not this page — run a test here for an immediate check.",
        ],
    },
    "Hop-by-Hop Trace": {
        "what": "MTR-style traceroute showing per-hop latency and packet-loss — identifies exactly which ISP hop is the problem.",
        "hidden": [
            "Run the trace twice — once when things are good and once when they are slow — then compare the hop-by-hop RTTs.",
            "High loss at a hop that still delivers traffic is usually ICMP rate-limiting, not a real problem. Loss that persists on all hops after it is the real issue.",
        ],
    },
    "ARP Spoof Watch": {
        "what": "Watches for MAC address conflicts that indicate a man-in-the-middle attack on the local segment.",
        "hidden": [
            "The 'Explain This' strip shows a step-by-step ARP spoofing diagram — useful for understanding how the attack works.",
            "Requires Npcap on Windows and admin rights — the tab shows a banner if these are missing.",
        ],
    },
    "SNMP Device Info": {
        "what": "Queries routers and switches via SNMP for port stats, CPU load, and uptime.",
        "hidden": [
            "Most home routers have SNMP disabled by default — enable it in the router admin panel first.",
            "Use SNMPv2c with the 'public' community string to start — change this if your router uses a custom community.",
        ],
    },
    "SNMP Trap Receiver": {
        "what": "Listens for SNMP trap messages from routers and switches — catches interface-down events automatically.",
        "hidden": [
            "Configure your router to send traps to this machine's IP address and port 162.",
            "Trap events appear in the Logs page 'SNMP Traps' tab as well as here.",
        ],
    },
    "Syslog Viewer": {
        "what": "Receives and displays syslog messages from network devices over UDP 514.",
        "hidden": [
            "Configure your router or switch to forward syslog to this machine's IP address.",
            "Syslog messages also appear in the Logs page 'Syslog' tab for unified viewing.",
        ],
    },
    "Tools & Wake-on-LAN": {
        "what": "Ping, traceroute, WHOIS, port check, and Wake-on-LAN utilities in one place.",
        "hidden": [
            "Wake-on-LAN requires the target device to have WoL enabled in its BIOS and the NIC driver settings.",
            "The WHOIS lookup works on both IP addresses and domain names.",
        ],
    },
    "Broadcast Storm": {
        "what": "Listens for abnormal broadcast traffic and identifies the source device or loop.",
        "hidden": [
            "The 'Explain This' strip explains what causes a broadcast storm and how STP is supposed to prevent them.",
            "Storm level SAFE / WARNING / CRITICAL is shown with the broadcast packets-per-second rate.",
        ],
    },
    "Rogue Bridge (STP)": {
        "what": "Captures BPDU frames and alerts when an unexpected switch claims the STP root election.",
        "hidden": [
            "The 'Explain This' strip explains STP, what a root election is, and why rogue bridges cause 30-second periodic outages.",
            "Mesh Wi-Fi nodes connected via Ethernet cable are a common source of rogue bridge events.",
        ],
    },
    "IoT Behaviour": {
        "what": "Learns normal traffic per IoT device and alerts on port scans, new destinations, and traffic rate spikes.",
        "hidden": [
            "Run the baseline for at least 24 hours before expecting accurate alerts — the model needs time to learn normal behaviour.",
            "Alerts fire when a device contacts a destination it has never used before — common after firmware updates.",
        ],
    },
    "Trend Forecasts": {
        "what": "Extrapolates RTT and packet-loss trends to predict future degradation based on historical data.",
        "hidden": [
            "Forecasts are only meaningful after several days of Network Logger data — short runs produce wide confidence intervals.",
        ],
    },
    "Root Cause Analysis": {
        "what": "Correlates events across modules to surface the most likely root cause of complex multi-symptom problems.",
        "hidden": [
            "Run a full scan and let the Network Logger collect data for at least an hour before using this — it needs events to correlate.",
        ],
    },
    # ── Automation ─────────────────────────────────────────────────────────────
    "Automation Hooks": {
        "what": "Webhook and script triggers on network events — device down, high RTT, new device discovered.",
        "hidden": [
            "Hooks fire in the background — configure a webhook URL and watch your Slack or Discord channel for events.",
            "Script hooks run any executable on your machine, so you can trigger Home Assistant scenes, send emails, or log to a database.",
        ],
    },
    "Scheduled Scans": {
        "what": "Run discovery and port scans on a repeating schedule — useful for overnight audits or compliance snapshots.",
        "hidden": [
            "Scheduled scans run even when the main window is not visible — the background service handles them.",
            "Combine with Config Snapshots to automatically save the state after each scheduled scan.",
        ],
    },
    "Custom Triggers": {
        "what": "Build your own event rules: if RTT exceeds a threshold for N consecutive pings, fire an action.",
        "hidden": [
            "Triggers can call webhooks, run scripts, or send desktop notifications — the same actions as Automation Hooks.",
        ],
    },
    "MQTT / Home Assistant": {
        "what": "Publishes device presence, uptime, and alerts to an MQTT broker for Home Assistant integration.",
        "hidden": [
            "Set the MQTT broker address and port in Settings — the page will show connection status once configured.",
            "Each device gets its own Home Assistant entity — ideal for automations like 'if the kids' tablet leaves the network, run a script'.",
        ],
    },
    "Config Snapshots": {
        "what": "Takes point-in-time snapshots of your scan results — compare current state to a baseline.",
        "hidden": [
            "Take a snapshot right after a clean setup, then compare against it after any change to see exactly what shifted.",
        ],
    },
    "Maintenance Windows": {
        "what": "Suppress alerts during planned downtime so you don't get paged for your own maintenance.",
        "hidden": [
            "Windows are one-time or recurring — set a recurring window for regular router reboots or backup jobs.",
        ],
    },
    # ── Security Audit ─────────────────────────────────────────────────────────
    "Port Scan (TCP)": {
        "what": "SYN stealth port scanner — identifies open TCP ports on discovered devices. Requires admin + Npcap.",
        "hidden": [
            "SYN scan is faster and quieter than a connect scan because it never completes the three-way handshake.",
            "Scan results feed into Device Risk Score and CVE Lookup automatically.",
        ],
    },
    "Port Scan (UDP)": {
        "what": "UDP port scanner — identifies open UDP services including DNS, SNMP, and NTP.",
        "hidden": [
            "UDP scanning is slower than TCP because closed ports respond with ICMP unreachable, which routers often rate-limit.",
            "Focus on ports 53, 161, 123, and 5353 for the most common home-network UDP services.",
        ],
    },
    "CVE Lookup": {
        "what": "Cross-references discovered OS and service versions against the NVD database on demand.",
        "hidden": [
            "CVE data is fetched from services.nvd.nist.gov — this is the only external call in this tab.",
            "Run a port scan first so there are service versions to look up — CVE Lookup needs version strings to match against.",
        ],
    },
    "Threat Intel": {
        "what": "Checks IP addresses from your scan results against threat intelligence feeds for known malicious hosts.",
        "hidden": [
            "Click any flagged IP to see which feed reported it and when it was last seen.",
        ],
    },
    "TLS & Exposure": {
        "what": "Monitors TLS certificate expiry per host and checks for accidental internet exposure of internal services.",
        "hidden": [
            "Certificates are checked hourly — you will see an alert badge 30 days before any cert expires.",
            "Exposure checks probe from the internet side — a result of 'exposed' means the port is reachable from outside your network.",
        ],
    },
    "Login Test": {
        "what": "Tests common default credentials against discovered services — for authorised use on networks you own.",
        "hidden": [
            "This test only tries documented factory-default passwords, not brute-force lists — it is designed for auditing your own devices.",
            "Results feed into Device Risk Score — a device with default credentials gets a critical risk flag.",
        ],
    },
    "OS Detection": {
        "what": "Fingerprints device operating systems using TCP/IP stack analysis.",
        "hidden": [
            "Accuracy improves when port scan data is available — run a TCP port scan first.",
        ],
    },
    "Device Risk Score": {
        "what": "Calculates a per-device risk score based on open ports, OS age, CVEs, and default credentials.",
        "hidden": [
            "Scores update automatically as port scan, CVE lookup, and login test results come in.",
            "Click any device row to see the specific findings that are driving its score up.",
        ],
    },
    "CVE Tracker": {
        "what": "Tracks active CVEs for your network devices over time — shows newly discovered vulnerabilities since last scan.",
        "hidden": [
            "Newly discovered CVEs appear with a 'New' badge — these are the ones to prioritise for patching.",
        ],
    },
    "Exposed to Internet": {
        "what": "Checks whether services on your network are reachable from the public internet via your external IP.",
        "hidden": [
            "A result of 'exposed' means someone outside your network could connect to that port — check your router's port-forwarding rules.",
        ],
    },
    "Full Device Discovery": {
        "what": "Parallel ARP + ICMP + TCP SYN + mDNS sweep for maximum device census accuracy. Requires admin + Npcap.",
        "hidden": [
            "This finds devices that don't respond to ARP alone — smart TVs and IoT devices that block pings are often missed by standard discovery.",
        ],
    },
    "Windows Shares (SMB)": {
        "what": "Enumerates accessible SMB shares on Windows devices on your network.",
        "hidden": [
            "Shared folders that are visible without a password are flagged — these are a common data-exfiltration risk on home networks.",
        ],
    },
    "Recon Plugins": {
        "what": "Custom port-scanner and enumeration scripts — not hardware driver plugins. Drop a .py plugin file into the plugins/ directory to add new scan capabilities.",
        "hidden": [
            "See CONTRIBUTING.md for the plugin API — a plugin is a single Python class with a run() method.",
            "These are recon/scan scripts, not hardware integrations. For routers and modems, use the Hardware section.",
        ],
    },
    "Private Endpoint Check": {
        "what": "Verifies that cloud private endpoints are not accidentally exposed on your local network.",
        "hidden": [
            "Useful if you run cloud VMs with VPN-connected private endpoints — this confirms the endpoint is not leaking.",
        ],
    },
    "Cloud Metadata Probe": {
        "what": "Detects cloud metadata service exposure (169.254.169.254) on the local subnet.",
        "hidden": [
            "A reachable metadata endpoint from a device that should not have cloud access indicates a misconfigured VM or container.",
        ],
    },
    "DHCP Rogue Monitor": {
        "what": "Watches for unauthorised DHCP servers responding on your network — a sign of a misconfigured device or attack.",
        "hidden": [
            "Requires Npcap on Windows — the monitor listens for DHCP OFFER frames on the wire.",
            "A rogue DHCP server can redirect your DNS to a malicious resolver — this is a common attack on public Wi-Fi.",
        ],
    },
    # ── Education ──────────────────────────────────────────────────────────────
    "Protocol Visualizer": {
        "what": "Animated step-by-step diagrams of ARP, DNS, TCP, DHCP, and STP using your real device addresses.",
        "hidden": [
            "Click any step in the step list to jump directly to it — you don't have to watch the full animation.",
            "The '▸ Why this protocol matters' panel at the bottom links the animation to real threats NetSentinel detects.",
            "The 'See diagram' button in any Explain This panel jumps here with the right protocol pre-selected.",
        ],
    },
    "Lab Mode": {
        "what": "Guided exercises that walk you through diagnosing your live network step by step.",
        "hidden": [
            "When the Home page shows a live event card, clicking 'Investigate →' drops you straight into a one-step lab built from that event.",
            "After finishing an exercise, click 'Export Report (HTML)' to save a portable lab report.",
            "Hints don't penalise you — use them freely. The solution is always there if you're stuck.",
        ],
    },
    "Feature Guide": {
        "what": "Every NetSentinel feature in one place — searchable, with descriptions and direct navigation.",
        "hidden": [
            "Use the search bar to find features by keyword — 'heatmap', 'arp', 'stp', or 'hidden' all work.",
            "Features marked with a badge (Npcap, admin) need extra setup — hover the badge for details.",
            "Click 'Open →' on any feature card to jump directly to that page.",
        ],
    },
}


# Pages that auto-expand the tip bar on first visit (they have non-obvious interactions)
_AUTO_HELP_PAGES: frozenset[str] = frozenset({
    "Network Logger", "Lab Mode", "Protocol Visualizer",
    "Automation Hooks", "MQTT / Home Assistant", "TLS & Exposure",
    "Service Heartbeat", "SNMP Trap Receiver", "Syslog Viewer",
    "IoT Behaviour", "Scheduled Scans",
})


def _make_chart_window(fig) -> "QMainWindow":
    from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout
    from PyQt6.QtCore import Qt as _Qt
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

    win = QMainWindow()
    win.setWindowTitle("Network Logger — RTT Chart")
    win.setAttribute(_Qt.WidgetAttribute.WA_DeleteOnClose)
    win.resize(1400, 820)

    container = QWidget()
    lay = QVBoxLayout(container)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)

    canvas = FigureCanvasQTAgg(fig)

    try:
        from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
    except ImportError:
        from matplotlib.backends.backend_qt import NavigationToolbar2QT

    toolbar = NavigationToolbar2QT(canvas, win)
    win.addToolBar(toolbar)
    lay.addWidget(canvas)
    win.setCentralWidget(container)
    canvas.draw()
    return win


# ─── Main Window ─────────────────────────────────────────────────────────────

class Dashboard(QMainWindow):
    _update_available         = pyqtSignal(str)
    global_time_range_changed = pyqtSignal(float)  # hours: float

    def __init__(self, store=None, alert_engine=None, notif_router=None, maint_manager=None):
        super().__init__()
        self._store        = store          # MetricStore | None
        self._alert_engine = alert_engine   # AlertEngine | None
        self._notif_router = notif_router   # NotificationRouter | None
        self._maint_manager = maint_manager # MaintenanceWindowManager | None
        self._global_hours = 24.0
        self.setWindowTitle("NetSentinel  —  Network Security Scanner & Monitor")
        self.setMinimumSize(900, 600)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setStyleSheet(MAIN_STYLE)
        self._maximize_btn = None   # set by _build_header; updated in changeEvent
        self._pre_maximize_geo: "QRect | None" = None  # saved before showMaximized()

        # Window icon
        from pathlib import Path as _Path
        from PyQt6.QtGui import QIcon as _QIcon
        import sys as _sys
        _base = _Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else _Path(__file__).parent.parent
        for _ico in ("assets/icons/NetSentinel.ico", "NetSentinel.ico", "icon.ico"):
            _p = _base / _ico
            if _p.exists():
                self.setWindowIcon(_QIcon(str(_p)))
                break

        self._offenders_path = get_offenders_path()
        self._admin = is_admin()

        # Scan results cache
        self._m1_result = None
        self._m2_result = None
        self._m3_result = None
        self._m4_result = None
        self._m5_result = None

        # Mesh enrichment — populated when MeshRouterPage scan completes
        self._mesh_enrichment: dict = {}   # normalised MAC → MeshClient

        # Plugin enrichment — one entry per plugin path; merged in _apply_mesh_enrichment
        # dict[path, dict[mac, client_dict]] — supports multiple router/AP plugins
        self._plugin_enrichments: dict[str, dict] = {}
        self._plugin_nodes:       dict[str, list] = {}  # path → [{name,mac,role}]
        self._plugin_hardware_name: str = ""  # name of last-run plugin

        # Last modem credentials — used to resume ZteWorker after plugin test
        self._last_modem_host: str = ""
        self._last_modem_pw:   str = ""

        # M1 satellite grouping state
        self._m1_sat_expanded: dict = {}   # node_name → bool (default False = collapsed)
        self._m1_grouping_active: bool = False

        # Active workers
        self._workers = []
        self._active_count = 0
        self._prescan_worker = None
        self._diag_worker = None
        self._logger_worker = None

        # Cached results
        self._net_info: dict = {}
        self._wan_ip:   str  = ""   # public WAN IP, fetched once per session after scan
        self._diag_result = None
        self._last_scan_devices: list = []    # for NetworkDocPage port_data accumulation
        self._port_data_cache:   dict = {}    # {ip: [port_dict, ...]} across scan types
        self._auto_report_pending:   bool = False  # True while full-report run is in progress
        self._auto_report_scan_done: bool = False
        self._auto_report_diag_done: bool = False
        self._pending_benchmark:     bool = False  # True when Grade My Network triggered a scan
        self._pending_isp_report:    bool = False  # True when ISP Report triggered diagnostics

        # Network pulse bar state
        self._last_scan_time:   float = 0.0  # epoch set on each m1 result
        self._last_log_status:  str   = ""   # "OK" | "SLOW" | "FAIL" | ""

        # Page transition animation
        self._fade_anim: QPropertyAnimation | None = None

        # Graph update timer
        self._graph_timer = QTimer()
        self._graph_timer.setInterval(500)
        self._graph_timer.timeout.connect(self._refresh_graph)

        # Weekly digest check — fires once per hour to see if a digest should be sent (RECUR-2)
        self._digest_timer = QTimer()
        self._digest_timer.setInterval(3_600_000)  # 1 hour
        self._digest_timer.timeout.connect(self._check_weekly_digest)
        self._digest_timer.start()
        QTimer.singleShot(5000, self._check_weekly_digest)

        # System tray guardian
        self._tray_quit = False   # set True when quitting via tray menu
        from ui.system_tray import SystemTrayManager
        self._tray_manager = SystemTrayManager(self)
        self._tray_manager.setup()
        # Keep legacy _tray_icon reference so _show_alert_toast still works
        self._tray_icon = self._tray_manager._tray

        # Ctrl+Q always quits immediately regardless of tray setting
        from PyQt6.QtGui import QShortcut, QKeySequence
        _quit_sc = QShortcut(QKeySequence("Ctrl+Q"), self)
        _quit_sc.activated.connect(self._quit_app)

        # Ctrl+F focuses the sidebar search box from anywhere in the app
        _search_sc = QShortcut(QKeySequence("Ctrl+F"), self)
        _search_sc.activated.connect(self._focus_nav_search)

        # Ctrl+K opens the command palette
        _palette_sc = QShortcut(QKeySequence("Ctrl+K"), self)
        _palette_sc.activated.connect(self._open_command_palette)

        # Esc closes the flyout panel in Standard/Pro mode
        _esc_sc = QShortcut(QKeySequence("Escape"), self)
        _esc_sc.activated.connect(self._on_canvas_click)

        # ? — shortcut overlay
        _help_sc = QShortcut(QKeySequence("?"), self)
        _help_sc.activated.connect(self._open_shortcut_overlay)

        # Ctrl+, — Settings
        _settings_sc = QShortcut(QKeySequence("Ctrl+,"), self)
        _settings_sc.activated.connect(self._open_settings_dialog)

        # Ctrl+L — Log Hub
        _loghub_sc = QShortcut(QKeySequence("Ctrl+L"), self)
        _loghub_sc.activated.connect(lambda: self._nav_rail_go_to("Network Logger"))

        # Pinned pages — persisted across sessions
        self._nav_pinned_labels: set = self._load_pinned_labels()
        self._nav_label_to_widget: dict = {}
        self._nav_history: list = []  # NAV-5: back-stack; direct rail clicks clear it

        # ── Progressive-disclosure nav mode ───────────────────────────────────
        self._nav_mode: str = "home"
        self._nav_admin_rows: set = set()   # rows requiring admin — get ·admin badge
        self._nav_audit_rows: set = set()   # Security Audit section rows — rendered in RED
        self._nav_action_rows: dict = {}
        # Rail-mode state (Standard/Pro)
        self._nav_sections: list = []        # [{name, icon, entries:[_NavEntry]}]
        self._nav_open_section: str = ""     # name of currently expanded flyout section
        self._nav_rail_buttons: dict = {}    # section_name -> _RailButton
        self._nav_page_to_section: dict = {} # page_label -> section_name
        self._nav_current_page_label: str = ""
        # Read saved mode before building the UI so _build_tabs() uses it
        try:
            from PyQt6.QtCore import QSettings as _QS
            _s = _QS(str(Dashboard._settings_path()), _QS.Format.IniFormat)
            _m = _s.value("nav/mode", "home")
            if _m in ("home", "standard", "pro"):
                self._nav_mode = _m
        except Exception:
            pass

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top application bar (dark navy)
        root.addWidget(self._build_header())

        # Update notification bar — hidden until background check finds a newer release
        self._update_bar = self._build_update_bar()
        self._update_bar.setVisible(False)
        self._update_available.connect(self._on_update_available)
        root.addWidget(self._update_bar)

        # Main area: sidebar+content fills window; verdict strip hidden until scan
        _main = self._build_tabs()
        _verdict_area = self._build_verdict_area()
        _verdict_area.setVisible(False)
        # Auto-show verdict strip on first scan result without touching callsites
        _orig_vu = self._verdict.update
        def _vu(text: str, level: str = "UNKNOWN", _ov=_orig_vu):
            _verdict_area.setVisible(True)
            _ov(text, level)
        self._verdict.update = _vu  # type: ignore[method-assign]
        root.addWidget(_main, 1)
        root.addWidget(_verdict_area)

        # Status bar
        self._status_bar = QStatusBar()
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setFixedHeight(4)
        self._progress.setVisible(False)
        self._status_bar.addPermanentWidget(self._progress)

        # ── Network pulse widgets (permanent, right-aligned) ─────────────────
        _pulse_base = (
            "QLabel { padding: 0 8px; font-size: 11px; background: transparent;"
            f" border: none; color: {TEXT_MUTED}; }}"
            "QLabel:hover { color: #FFFFFF; }"
        )
        _pulse_sep = QFrame()
        _pulse_sep.setFrameShape(QFrame.Shape.VLine)
        _pulse_sep.setFixedWidth(1)
        _pulse_sep.setStyleSheet(f"background: {NAV_DIVIDER}; border: none;")

        self._pulse_online_lbl  = _ClickLabel("○  —")
        self._pulse_devices_lbl = _ClickLabel("■  —")
        self._pulse_scan_lbl    = _ClickLabel("Last scan: —")
        self._pulse_logger_lbl  = _ClickLabel("○  Logger off")
        for _l in (self._pulse_online_lbl, self._pulse_devices_lbl,
                   self._pulse_scan_lbl, self._pulse_logger_lbl):
            _l.setStyleSheet(_pulse_base)
            _l.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pulse_online_lbl.setToolTip(
            "Connection status (last logger result)\nClick to open Connectivity Tests"
        )
        self._pulse_devices_lbl.setToolTip(
            "Number of devices seen in the last scan\nClick to open Overview"
        )
        self._pulse_scan_lbl.setToolTip(
            "Time since the last network scan completed\nClick to open Overview"
        )
        self._pulse_logger_lbl.setToolTip(
            "Network logger state — starts automatically on first launch\nClick to open Logs"
        )

        self._pulse_online_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("What's Wrong?"))
        self._pulse_devices_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("Overview"))
        self._pulse_scan_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("Overview"))
        self._pulse_logger_lbl.clicked.connect(
            lambda: self._nav_rail_go_to("Network Logger"))

        self._status_bar.addPermanentWidget(_pulse_sep)
        self._status_bar.addPermanentWidget(self._pulse_online_lbl)
        self._status_bar.addPermanentWidget(self._pulse_devices_lbl)
        self._status_bar.addPermanentWidget(self._pulse_scan_lbl)
        self._status_bar.addPermanentWidget(self._pulse_logger_lbl)

        self.setStatusBar(self._status_bar)
        self._set_status("Ready.")

        # 10-second pulse timer — keeps status-bar indicators current
        self._pulse_timer = QTimer()
        self._pulse_timer.setInterval(10_000)
        self._pulse_timer.timeout.connect(self._refresh_pulse_bar)
        self._pulse_timer.start()
        # Load network info in background on startup
        self._refresh_network_info()
        # Silent background update check
        self._start_update_check()
        # Restore full settings (mode, scan hosts, etc.) after UI is built
        self._restore_settings()
        # Install resize grips for all 8 edges/corners (frameless window)
        self._install_edge_grips()
        # Auto-start modem polling if credentials were saved from a prior session
        self._check_modem_autorun()

    def _build_mode_bar(self) -> QWidget:
        """Mode-switcher pill — now built inline inside the sidebar in _build_tabs().
        This method is kept as a no-op for compatibility."""
        from PyQt6.QtWidgets import QWidget as _W
        return _W()  # empty placeholder; never added to the layout

    # ── Frameless window — drag support on header ────────────────────────────

    class _DragHeader(QWidget):
        """Header bar that lets the user drag the frameless window."""
        def __init__(self, window: "Dashboard", parent=None):
            super().__init__(parent)
            self._win      = window
            self._drag_pos: QPoint | None = None
            self.setAttribute(
                __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.WidgetAttribute.WA_StyledBackground,
                False,
            )

        def paintEvent(self, _e):
            from PyQt6.QtGui import QPainter, QColor
            from ui.styles import NAV_BAR, NAV_DIVIDER
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(NAV_BAR))
            p.setPen(QColor(NAV_DIVIDER))
            p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            p.end()

        def mousePressEvent(self, e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = (
                    e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
                )
            super().mousePressEvent(e)

        def mouseMoveEvent(self, e):
            if self._drag_pos and e.buttons() == Qt.MouseButton.LeftButton:
                if self._win.isMaximized():
                    # restore first, then re-anchor drag so window follows cursor
                    self._win.showNormal()
                    self._drag_pos = QPoint(
                        self._win.width() // 2,
                        e.globalPosition().toPoint().y() - self._win.frameGeometry().top(),
                    )
                self._win.move(e.globalPosition().toPoint() - self._drag_pos)
            super().mouseMoveEvent(e)

        def mouseReleaseEvent(self, e):
            self._drag_pos = None
            super().mouseReleaseEvent(e)

        def mouseDoubleClickEvent(self, e):
            if e.button() == Qt.MouseButton.LeftButton:
                self._win._toggle_maximize()
            super().mouseDoubleClickEvent(e)

    def _build_header(self) -> QWidget:
        """Slim top bar: brand | stretch | verdict | actions."""
        from PyQt6.QtWidgets import QMenu, QToolButton

        w = self._DragHeader(self)
        w.setObjectName("appBar")
        w.setFixedHeight(42)
        # Background is painted by _DragHeader.paintEvent — no CSS needed for colour.
        # Stylesheet here only scopes child widget colours (labels transparent, etc.)
        w.setStyleSheet(
            f"QLabel {{ background:transparent; color:{WHITE}; border:none; }}"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.setSpacing(6)

        # ── Brand (left, fixed) ───────────────────────────────────────────────
        import sys as _sys
        _base = Path(_sys._MEIPASS) if getattr(_sys, "frozen", False) else Path(__file__).parent.parent
        _pix = QPixmap(str(_base / "assets" / "icons" / "netsentinel.png"))
        _icon = QLabel()
        _icon.setFixedSize(24, 24)
        _icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _icon.setStyleSheet(f"background:{NAV_BAR};")
        if not _pix.isNull():
            _icon.setPixmap(
                _pix.scaled(24, 24,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
            )
            _icon.repaint()
        else:
            _icon.setText("N")
            _icon.setStyleSheet(
                f"background:{ACCENT}; color:{WHITE}; border-radius:5px;"
                " font-size:13px; font-weight:bold;"
            )
        lay.addWidget(_icon)
        lay.addSpacing(6)

        brand_lbl = QLabel("NetSentinel")
        brand_lbl.setObjectName("lblTitle")
        brand_lbl.setStyleSheet(
            f"color:{WHITE}; background:transparent;"
            " font-size:13px; font-weight:bold; letter-spacing:0.5px;"
        )
        lay.addWidget(brand_lbl)

        # ── Stretch — pushes everything else to the right ─────────────────────
        lay.addStretch(1)

        # ── Network status (centre) — hidden until a scan produces real data ────
        self._verdict_badge = QLabel()
        self._verdict_badge.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; font-weight:600;"
            f" background:transparent; border:none; padding:0 12px;"
        )
        self._verdict_badge.setToolTip("Overall network status")
        self._verdict_badge.setVisible(False)
        lay.addWidget(self._verdict_badge)

        lay.addStretch(1)

        # _header_mode_lbl kept as hidden attribute — used by _update_mode_pill
        self._header_mode_lbl = QLabel()
        self._header_mode_lbl.setVisible(False)
        # (not added to layout — Pro mode context is shown in the sidebar pill)

        # Hidden logical widgets — keep as attributes so _set_scanning can enable/disable
        self._btn_scan = QPushButton()
        self._btn_scan.clicked.connect(self._start_full_scan)
        self._btn_export = QPushButton()
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_report)

        # ── Settings dropdown (⚙) ─────────────────────────────────────────────
        _menu_s = QMenu()
        _menu_s.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; padding:4px; font-size:11px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; }}"
        )

        _act_about = _menu_s.addAction("About NetSentinel")
        _act_about.triggered.connect(self._show_about)
        _menu_s.addSeparator()
        _act_app_settings = _menu_s.addAction("⚙  App Settings…")
        _act_app_settings.triggered.connect(self._open_settings_dialog)
        _menu_s.addSeparator()
        _act_quit = _menu_s.addAction("✕  Quit NetSentinel")
        _act_quit.triggered.connect(self._quit_app)

        # Transparent at rest — header dark bg shows through; border+accent on hover
        _icon_btn_qss = (
            f"QToolButton {{ background:transparent; color:{TEXT_MUTED};"
            f" border:1px solid {SIDEBAR_SECTION_BG}; border-radius:5px;"
            f" font-family:'Segoe UI Symbol','Segoe UI',sans-serif;"
            f" font-size:12px; padding:0 8px;"
            f" min-height:26px; max-height:26px; }}"
            f"QToolButton:hover {{ background:{ACCENT}; color:{WHITE}; border-color:{ACCENT_DARK}; }}"
            "QToolButton::menu-indicator { image: none; }"
        )
        _btn_settings = QToolButton()
        _btn_settings.setText("⚙︎")
        _btn_settings.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        _btn_settings.setMenu(_menu_s)
        _btn_settings.setToolTip("Scan Settings — module toggles, durations, and app preferences")
        _btn_settings.setStyleSheet(_icon_btn_qss)
        lay.addSpacing(4)
        lay.addWidget(_btn_settings)

        # ── Global time range picker (TIME-1) ────────────────────────────────
        _time_combo_qss = (
            f"QComboBox {{ background:transparent; color:{TEXT_MUTED};"
            f" border:1px solid {SIDEBAR_SECTION_BG}; border-radius:5px;"
            f" font-size:11px; padding:0 6px;"
            f" min-height:26px; max-height:26px; min-width:52px; }}"
            f"QComboBox:hover {{ border-color:{ACCENT}; color:{WHITE}; }}"
            f"QComboBox::drop-down {{ border:none; width:16px; }}"
            f"QComboBox QAbstractItemView {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; selection-background-color:{ACCENT}; }}"
        )
        self._time_range_combo = QComboBox()
        self._time_range_combo.addItems(["1h", "6h", "24h", "7d", "30d"])
        self._time_range_combo.setCurrentText("24h")
        self._time_range_combo.setToolTip("Global time window — applies to all data pages")
        self._time_range_combo.setStyleSheet(_time_combo_qss)
        self._time_range_combo.currentTextChanged.connect(self._on_global_time_changed)
        lay.addSpacing(4)
        lay.addWidget(self._time_range_combo)

        # ── Scan button — persistent trigger visible from every page ─────────
        self._header_scan_btn = QToolButton()
        self._header_scan_btn.setText("▶  Scan")
        self._header_scan_btn.setToolTip("Run full network scan (ARP + WiFi + DNS + port discovery)")
        self._header_scan_btn.setStyleSheet(_icon_btn_qss)
        self._header_scan_btn.clicked.connect(self._start_full_scan)
        lay.addWidget(self._header_scan_btn)

        # ── POLISH-5: Theme toggle — cycles through all 3 themes, toast + restart ──
        from ui.styles import THEMES, get_active_theme_name, set_active_theme_name
        _theme_names = list(THEMES.keys())
        _theme_icons = {"Arctic Clean": "☀", "Midnight Pro": "🌙", "Obsidian Neon": "✦"}
        _current_theme = get_active_theme_name()
        _theme_btn = QPushButton(_theme_icons.get(_current_theme, "☀"))
        _theme_btn.setObjectName("themeToggleBtn")
        _theme_btn.setFixedSize(30, 28)
        _theme_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _theme_btn.setToolTip(f"Theme: {_current_theme} — click to cycle")
        _theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _theme_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{WHITE}; border:none;"
            f" font-size:13px; border-radius:4px; }}"
            f"QPushButton:hover {{ background:rgba(255,255,255,0.10); }}"
        )

        def _on_theme_toggle():
            from ui.styles import THEMES, get_active_theme_name, set_active_theme_name
            from ui.widgets.toast import ToastManager
            _names = list(THEMES.keys())
            _cur = get_active_theme_name()
            _next = _names[(_names.index(_cur) + 1) % len(_names)] if _cur in _names else _names[0]
            set_active_theme_name(_next)
            _theme_btn.setToolTip(f"Theme: {_next} — restart to apply")
            ToastManager.show(f"Theme set to {_next} — restart to apply", "info")

        _theme_btn.clicked.connect(_on_theme_toggle)
        lay.addSpacing(4)
        lay.addWidget(_theme_btn)

        # ── Window controls ───────────────────────────────────────────────────
        # Segoe MDL2 Assets: the exact font Windows uses for its own title bar
        # buttons — looks native on Win10/11; degrades to readable symbols elsewhere.
        _sep = QFrame()
        _sep.setFrameShape(QFrame.Shape.VLine)
        _sep.setFixedWidth(1)
        _sep.setFixedHeight(26)
        _sep.setStyleSheet(f"background:{NAV_DIVIDER}; border:none;")
        lay.addSpacing(8)
        lay.addWidget(_sep)
        lay.addSpacing(2)

        # _ChromeButton strips Qt's focus-rect drawing so no ring ever bleeds
        # outside the button bounds — matches VS Code / native title bar behaviour.
        from PyQt6.QtWidgets import QStyle

        class _ChromeButton(QPushButton):
            def initStyleOption(self, option):
                super().initStyleOption(option)
                option.state = option.state & ~QStyle.StateFlag.State_HasFocus

        _wc_base = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED};"
            f" border:none; border-radius:0px; outline:none; padding:0;"
            f" font-family:'Segoe MDL2 Assets','Segoe UI Symbol','Segoe UI';"
            f" font-size:10px;"
            f" min-width:46px; max-width:46px;"
            f" min-height:42px; max-height:42px; }}"
            f"QPushButton:focus, QPushButton:focus-visible {{ outline:none; border:none; }}"
            f"QPushButton:pressed {{ outline:none; border:none; }}"
        )
        # NoSubpixelAntialias eliminates ClearType fringing on Segoe MDL2 glyphs
        _wc_font = QFont("Segoe MDL2 Assets", 10)
        _wc_font.setStyleStrategy(QFont.StyleStrategy.NoSubpixelAntialias)

        _btn_min = _ChromeButton("")     # ChromeMinimize
        _btn_min.setToolTip("Minimise")
        _btn_min.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _btn_min.setFont(_wc_font)
        _btn_min.setStyleSheet(
            _wc_base +
            f"QPushButton:hover {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
        )
        _btn_min.clicked.connect(self.showMinimized)
        lay.addWidget(_btn_min)

        self._maximize_btn = _ChromeButton("")   # ChromeMaximize
        self._maximize_btn.setToolTip("Maximise")
        self._maximize_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._maximize_btn.setFont(_wc_font)
        self._maximize_btn.setStyleSheet(
            _wc_base +
            f"QPushButton:hover {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{SIDEBAR_HOVER}; color:{WHITE}; }}"
        )
        self._maximize_btn.clicked.connect(self._toggle_maximize)
        lay.addWidget(self._maximize_btn)

        _btn_close = _ChromeButton("")   # ChromeClose
        _btn_close.setToolTip("Close")
        _btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        _btn_close.setFont(_wc_font)
        _btn_close.setStyleSheet(
            _wc_base +
            f"QPushButton:hover {{ background:{RED}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{RED}; color:{WHITE}; }}"
        )
        _btn_close.clicked.connect(self._quit_app)
        lay.addWidget(_btn_close)

        return w

    # ── Frameless window — helpers ───────────────────────────────────────────

    def _toggle_maximize(self):
        from PyQt6.QtCore import Qt
        if self.windowState() & Qt.WindowState.WindowMaximized:
            # Capture and clear _pre_maximize_geo BEFORE showNormal() so the
            # changeEvent handler (which also clears it) cannot race us.
            pre_geo = self._pre_maximize_geo
            self._pre_maximize_geo = None
            self.showNormal()
            if pre_geo is not None:
                self.setGeometry(pre_geo)
        else:
            self._pre_maximize_geo = self.geometry()
            self.showMaximized()

    def changeEvent(self, event):
        super().changeEvent(event)
        if getattr(self, "_maximize_btn", None) is not None:
            from PyQt6.QtCore import QEvent, Qt
            if event.type() == QEvent.Type.WindowStateChange:
                is_max = bool(self.windowState() & Qt.WindowState.WindowMaximized)
                self._maximize_btn.setText("" if is_max else "")
                self._maximize_btn.setToolTip("Restore" if is_max else "Maximise")
                if not is_max:
                    self._pre_maximize_geo = None
                if hasattr(self, "_edge_grips"):
                    self._place_edge_grips()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_edge_grips"):
            self._place_edge_grips()

    # ── Windows Snap Layouts ─────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_snap_subclass_installed", False):
            self._install_snap_subclass()
            self._snap_subclass_installed = True
        # Attach toast manager once window is visible
        from ui.widgets.toast import ToastManager
        ToastManager.instance().attach(self)
        # OUTPUT-4: scan summary sheet (lazy init, parented to main window)
        if not hasattr(self, "_scan_sheet"):
            from ui.widgets.scan_summary_sheet import ScanSummarySheet
            self._scan_sheet = ScanSummarySheet(self)
            self._scan_sheet.navigate_requested.connect(self._nav_rail_go_to)
        # SCHED-3: restore monitors that were running before last close
        if not getattr(self, "_monitors_restored", False):
            self._monitors_restored = True
            from PyQt6.QtCore import QTimer as _QT3
            _QT3.singleShot(3000, self._restore_running_monitors)

    def _install_snap_subclass(self):
        """Subclass the Win32 HWND so WM_NCHITTEST returns HTMAXBUTTON over our
        maximize button.  This is safer than nativeEvent because the message ID
        arrives as a plain C argument — no MSG struct pointer parsing needed."""
        try:
            import ctypes, ctypes.wintypes as wt

            WM_NCHITTEST = 0x0084
            HTMAXBUTTON  = 9

            _DefSubclassProc = ctypes.windll.comctl32.DefSubclassProc
            _DefSubclassProc.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
            _DefSubclassProc.restype  = ctypes.c_ssize_t

            SUBCLASSPROC = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t,
                wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM,
                ctypes.c_size_t,   # UINT_PTR  uIdSubclass
                ctypes.c_size_t,   # DWORD_PTR dwRefData
            )

            WM_NCLBUTTONDOWN = 0x00A1
            WM_NCLBUTTONUP   = 0x00A2

            win = self

            def _over_maximize_btn():
                btn = win._maximize_btn
                if btn is None:
                    return False
                from PyQt6.QtGui import QCursor
                p  = QCursor.pos()
                tl = btn.mapToGlobal(btn.rect().topLeft())
                return (tl.x() <= p.x() < tl.x() + btn.width() and
                        tl.y() <= p.y() < tl.y() + btn.height())

            def _proc(hwnd, msg, wparam, lparam, uid, ref):
                if msg == WM_NCHITTEST and _over_maximize_btn():
                    return HTMAXBUTTON
                # Intercept non-client clicks on the maximize button so we drive
                # the toggle ourselves instead of letting DefWindowProc do it.
                if wparam == HTMAXBUTTON:
                    if msg == WM_NCLBUTTONDOWN:
                        return 0  # swallow — we act on release
                    if msg == WM_NCLBUTTONUP:
                        win._toggle_maximize()
                        return 0
                return _DefSubclassProc(hwnd, msg, wparam, lparam)

            self._snap_subclass_proc = SUBCLASSPROC(_proc)
            hwnd = int(self.winId())

            # WS_THICKFRAME + WS_MAXIMIZEBOX are required for Windows to show the
            # Snap Layout flyout — without them it ignores HTMAXBUTTON entirely.
            GWL_STYLE      = -16
            WS_THICKFRAME  = 0x00040000
            WS_MAXIMIZEBOX = 0x00010000
            _GetWindowLong = ctypes.windll.user32.GetWindowLongW
            _SetWindowLong = ctypes.windll.user32.SetWindowLongW
            _GetWindowLong.argtypes = [wt.HWND, ctypes.c_int]
            _GetWindowLong.restype  = ctypes.c_long
            _SetWindowLong.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
            _SetWindowLong.restype  = ctypes.c_long
            style = _GetWindowLong(hwnd, GWL_STYLE)
            _SetWindowLong(hwnd, GWL_STYLE, style | WS_THICKFRAME | WS_MAXIMIZEBOX)
            # Tell DWM to recalculate the non-client area after the style change.
            SWP_FLAGS = 0x0027  # SWP_NOMOVE|SWP_NOSIZE|SWP_NOZORDER|SWP_FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_FLAGS)

            _SetWindowSubclass = ctypes.windll.comctl32.SetWindowSubclass
            _SetWindowSubclass.argtypes = [wt.HWND, SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
            _SetWindowSubclass.restype  = wt.BOOL
            _SetWindowSubclass(hwnd, self._snap_subclass_proc, 1, 0)
        except Exception:
            pass

    def _install_edge_grips(self):
        """Create 8 transparent resize-grip strips around the window border."""
        from PyQt6.QtCore import Qt, QRect, QPoint
        from PyQt6.QtWidgets import QWidget
        _CURSORS = {
            "nw": Qt.CursorShape.SizeFDiagCursor,
            "n":  Qt.CursorShape.SizeVerCursor,
            "ne": Qt.CursorShape.SizeBDiagCursor,
            "w":  Qt.CursorShape.SizeHorCursor,
            "e":  Qt.CursorShape.SizeHorCursor,
            "sw": Qt.CursorShape.SizeBDiagCursor,
            "s":  Qt.CursorShape.SizeVerCursor,
            "se": Qt.CursorShape.SizeFDiagCursor,
        }
        win = self

        class _Grip(QWidget):
            def __init__(self, edge, parent):
                super().__init__(parent)
                self._edge = edge
                self._drag_start = None
                self._start_geo  = None
                self.setCursor(_CURSORS[edge])
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
                self.setStyleSheet("background: transparent;")

            def mousePressEvent(self, e):
                if e.button() == Qt.MouseButton.LeftButton:
                    self._drag_start = e.globalPosition().toPoint()
                    self._start_geo  = win.geometry()

            def mouseMoveEvent(self, e):
                if self._drag_start is None:
                    return
                if not (e.buttons() & Qt.MouseButton.LeftButton):
                    return
                d   = e.globalPosition().toPoint() - self._drag_start
                geo = QRect(self._start_geo)
                if "n" in self._edge: geo.setTop(geo.top()    + d.y())
                if "s" in self._edge: geo.setBottom(geo.bottom() + d.y())
                if "w" in self._edge: geo.setLeft(geo.left()   + d.x())
                if "e" in self._edge: geo.setRight(geo.right()  + d.x())
                if geo.width() >= win.minimumWidth() and geo.height() >= win.minimumHeight():
                    win.setGeometry(geo)

            def mouseReleaseEvent(self, e):
                self._drag_start = None

        self._edge_grips = {k: _Grip(k, self) for k in _CURSORS}
        self._place_edge_grips()

    def _place_edge_grips(self):
        from PyQt6.QtCore import Qt
        m = 6
        w, h = self.width(), self.height()
        is_max = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        rects = {
            "nw": (0,     0,     m,     m),
            "n":  (m,     0,     w-2*m, m),
            "ne": (w-m,   0,     m,     m),
            "w":  (0,     m,     m,     h-2*m),
            "e":  (w-m,   m,     m,     h-2*m),
            "sw": (0,     h-m,   m,     m),
            "s":  (m,     h-m,   w-2*m, m),
            "se": (w-m,   h-m,   m,     m),
        }
        for name, grip in self._edge_grips.items():
            x, y, gw, gh = rects[name]
            grip.setGeometry(x, y, gw, gh)
            grip.setVisible(not is_max)
            grip.raise_()

    def _build_update_bar(self) -> QWidget:
        """Thin update-available bar — hidden until a newer release is detected."""
        container = QWidget()
        container.setObjectName("updateNotifBar")
        container.setFixedHeight(28)
        row = QHBoxLayout(container)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(6)
        container.setStyleSheet(
            f"QWidget#updateNotifBar {{ background:{UPDATE_BAR_BG}; "
            f"border-bottom: 1px solid {UPDATE_BAR_BORDER}; }}"
        )
        icon = QLabel("↑")
        icon.setStyleSheet(f"color:{ACCENT}; font-size:12px; background:transparent; border:none;")
        row.addWidget(icon)
        self._update_bar_lbl = QLabel("A new version is available.")
        self._update_bar_lbl.setStyleSheet(
            f"color:{UPDATE_BAR_FG}; font-size:11px; background:transparent; border:none;"
        )
        self._update_bar_lbl.setOpenExternalLinks(True)
        self._update_bar_lbl.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self._update_bar_lbl, 1)
        btn_dismiss = QPushButton("✕")
        btn_dismiss.setFixedSize(20, 20)
        btn_dismiss.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:none; font-size:12px; }}"
            f"QPushButton:hover {{ color:{UPDATE_BAR_FG}; }}"
        )
        btn_dismiss.clicked.connect(container.hide)
        row.addWidget(btn_dismiss)
        return container

    def _start_update_check(self):
        """Kick off a background thread to check the GitHub releases API."""
        import threading
        def _check():
            try:
                import urllib.request, json as _json
                from PyQt6.QtWidgets import QApplication
                current = QApplication.applicationVersion()
                url = "https://api.github.com/repos/ossianericson/netsentinel/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "NetSentinel"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = _json.loads(resp.read())
                latest = data.get("tag_name", "").lstrip("v")
                def _ver(s):
                    try:
                        return tuple(int(x) for x in s.split("."))
                    except ValueError:
                        return (0,)
                if latest and _ver(latest) > _ver(current):
                    self._show_update_bar(latest)
            except Exception:
                pass  # silent — no network or rate-limited; user can check manually
        threading.Thread(target=_check, daemon=True).start()

    def _show_update_bar(self, latest: str):
        """Called from the background thread — must dispatch to the UI thread."""
        self._update_available.emit(latest)

    @pyqtSlot(str)
    def _on_update_available(self, latest: str):
        """Runs on the UI thread — safe to touch widgets."""
        from PyQt6.QtWidgets import QApplication
        current = QApplication.applicationVersion()
        msg = (
            f"NetSentinel v{latest} is available (you have v{current}) — "
            f'<a href="https://github.com/ossianericson/netsentinel/releases/latest" '
            f'style="color:{ACCENT};">Download</a>'
            f' &nbsp;·&nbsp; or run: <code>winget upgrade NetSentinel.NetSentinel</code>'
        )
        self._update_bar_lbl.setText(msg)
        self._update_bar.setVisible(True)

    # ── Admin pill badge delegate ────────────────────────────────────────────

    class _NavAdminDelegate(
        __import__("PyQt6.QtWidgets", fromlist=["QStyledItemDelegate"]).QStyledItemDelegate
    ):
        """Paints a small red 'admin' pill badge on the right of admin nav rows."""

        _BADGE = "admin"
        _H     = 13
        _PAD   = 4
        _GAP   = 6

        def __init__(self, admin_rows: set, color: str, parent=None):
            from PyQt6.QtWidgets import QStyledItemDelegate
            super().__init__(parent)
            self._admin_rows    = admin_rows
            self._color         = color
            self._count_badges: dict = {}  # row → (count_str, bg_color)

        def set_count_badge(self, row: int, count: int, color: str) -> None:
            if count > 0:
                self._count_badges[row] = (str(count), color)
            else:
                self._count_badges.pop(row, None)

        def _paint_pill(self, painter, option, text: str, bg: str, right_offset: int) -> int:
            """Paint a pill badge; returns the width consumed (for stacking badges)."""
            from PyQt6.QtCore import Qt, QRect
            from PyQt6.QtGui import QColor, QFont, QPainter
            f = QFont("Segoe UI", 7)
            f.setBold(True)
            painter.setFont(f)
            fm  = painter.fontMetrics()
            bw  = fm.horizontalAdvance(text) + self._PAD * 2
            bx  = option.rect.right() - right_offset - bw - self._GAP
            by  = option.rect.center().y() - self._H // 2
            rect = QRect(bx, by, bw, self._H)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)
            painter.setPen(QColor("#FFFFFF"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            return bw + self._GAP

        def paint(self, painter, option, index):
            from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem
            from PyQt6.QtGui import QPainter
            opt = QStyleOptionViewItem(option)
            opt.state &= ~QStyle.StateFlag.State_HasFocus
            super().paint(painter, opt, index)
            row = index.row()
            painter.save()
            right_offset = 0
            if row in self._admin_rows:
                right_offset += self._paint_pill(painter, option, self._BADGE, self._color, right_offset)
            if row in self._count_badges:
                text, bg = self._count_badges[row]
                self._paint_pill(painter, option, text, bg, right_offset)
            painter.restore()

    # ── Sidebar navigation helpers ───────────────────────────────────────────
    # Data model (initialised in _build_tabs):
    #   _nav_item_icons[row]    str  — emoji shown in icon-only mode
    #   _nav_item_labels[row]   str  — full label text
    #   _nav_header_rows        set  — rows that are section or sub-group headers
    #   _nav_section_groups[r]  dict — {children:[rows], collapsed:bool, level:0|1}
    #   _nav_current_section    int  — row of last section header added
    #   _nav_current_subgroup   int  — row of last sub-group header (-1 = none)
    #   _nav_collapsed          bool — sidebar in icon-only (narrow) mode

    def _nav_add_section(self, label: str, icon: str = "■",
                         collapsed_by_default: bool = False,
                         fg_color: str = None) -> int:
        """Add a collapsible section header row."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QFont as _QFont, QBrush
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)   # clickable but not selectable
        item.setSizeHint(QSize(0, 28))
        item.setBackground(QBrush(QColor(SIDEBAR_SECTION_BG)))
        f = _QFont("Segoe UI", 9)
        f.setBold(True)
        item.setFont(f)
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]    = icon
        self._nav_item_labels[row]   = label
        self._nav_header_rows.add(row)
        self._nav_section_groups[row] = {
            "children": [], "collapsed": collapsed_by_default, "level": 0,
            "fg_color": fg_color,
        }
        self._nav_current_section  = row
        self._nav_current_subgroup = -1
        self._nav_separators.add(row)          # legacy compat
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_subgroup(self, label: str, icon: str = "▸",
                          collapsed_by_default: bool = True) -> int:
        """Add an indented collapsible sub-group header under the current section."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QBrush
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        item.setSizeHint(QSize(0, 26))
        item.setBackground(QBrush(QColor(SIDEBAR_SECTION_BG)))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]    = icon
        self._nav_item_labels[row]   = label
        self._nav_header_rows.add(row)
        self._nav_section_groups[row] = {
            "children": [], "collapsed": collapsed_by_default, "level": 1
        }
        self._nav_section_groups[self._nav_current_section]["children"].append(row)
        self._nav_separators.add(row)          # legacy compat
        self._nav_current_subgroup = row
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_page(self, icon: str, label: str, widget: QWidget) -> int:
        """Add a page entry to the sidebar and the stacked widget. Returns nav row index."""
        from PyQt6.QtCore import QSize
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        page_idx = self._stack.addWidget(widget)
        row = self._nav.count() - 1
        self._nav_row_to_page[row] = page_idx
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        self._nav_label_to_widget[label] = widget
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        return row

    def _nav_add_alias(self, icon: str, label: str, page_idx: int) -> int:
        """Add a nav entry that points to an already-registered page stack index.

        Use this to expose the same page in multiple sidebar locations (e.g. the
        Pinned quick-access section and its canonical grouped position) without
        adding the widget to QStackedWidget a second time.
        """
        from PyQt6.QtCore import QSize
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_row_to_page[row] = page_idx
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        return row

    def _nav_set_page(self, nav_row: int):
        if nav_row not in self._nav_row_to_page:
            return
        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
            w = self._stack.currentWidget()
            if w:
                w.setGraphicsEffect(None)
            self._fade_anim = None
        self._stack.setCurrentIndex(self._nav_row_to_page[nav_row])
        label = self._nav_item_labels.get(nav_row, "")
        if label:
            self.setWindowTitle(f"NetSentinel — {label}")

    def _nav_crossfade_to(self, target_widget) -> None:
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        from PyQt6.QtCore import QPropertyAnimation, QEasingCurve

        if self._fade_anim is not None and self._fade_anim.state() == QPropertyAnimation.State.Running:
            self._fade_anim.stop()
            cur = self._stack.currentWidget()
            if cur:
                cur.setGraphicsEffect(None)
            self._fade_anim = None

        if self._stack.currentWidget() is target_widget:
            return

        cur = self._stack.currentWidget()
        if cur is None:
            self._stack.setCurrentWidget(target_widget)
            return

        effect = QGraphicsOpacityEffect(cur)
        cur.setGraphicsEffect(effect)

        fade_out = QPropertyAnimation(effect, b"opacity", cur)
        fade_out.setDuration(80)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)
        self._fade_anim = fade_out

        def _on_fade_out_done():
            cur.setGraphicsEffect(None)
            self._stack.setCurrentWidget(target_widget)
            in_effect = QGraphicsOpacityEffect(target_widget)
            target_widget.setGraphicsEffect(in_effect)
            fade_in = QPropertyAnimation(in_effect, b"opacity", target_widget)
            fade_in.setDuration(80)
            fade_in.setStartValue(0.0)
            fade_in.setEndValue(1.0)
            fade_in.setEasingCurve(QEasingCurve.Type.OutQuad)
            fade_in.finished.connect(lambda: target_widget.setGraphicsEffect(None))
            self._fade_anim = fade_in
            fade_in.start()

        fade_out.finished.connect(_on_fade_out_done)
        fade_out.start()

    def _nav_refresh_item_text(self, row: int):
        """Rewrite displayed text for a nav row based on collapsed/expanded mode."""
        item = self._nav.item(row)
        if item is None:
            return
        icon  = self._nav_item_icons.get(row, "")
        label = self._nav_item_labels.get(row, "")
        if self._nav_collapsed:
            item.setText(icon)
            if row not in self._nav_header_rows:
                item.setToolTip(label)
        elif row in self._nav_section_groups:
            grp   = self._nav_section_groups[row]
            arrow = "\u25b6" if grp["collapsed"] else "\u25bc"
            from PyQt6.QtGui import QColor
            if grp["level"] == 0:
                item.setText(f" {arrow}  {label.upper()}")
            else:
                item.setText(f"     {arrow}  {label}")
            _fg = grp.get("fg_color") or SIDEBAR_SECTION_FG
            item.setForeground(QColor(_fg))
            item.setToolTip("")
        else:
            star = " ★" if label in self._nav_pinned_labels else ""
            item.setText(f"  {icon}  {label}{star}")
            item.setToolTip("")
            from PyQt6.QtGui import QColor
            if row in self._nav_audit_rows:
                item.setForeground(QColor(AUDIT_RED))
            else:
                item.setForeground(QColor(SIDEBAR_ITEM_FG))

    def _nav_toggle_section(self, header_row: int):
        """Collapse or expand a section / sub-group header."""
        if header_row not in self._nav_section_groups:
            return
        grp = self._nav_section_groups[header_row]
        grp["collapsed"] = not grp["collapsed"]
        self._nav_refresh_item_text(header_row)
        self._nav_apply_section_visibility(header_row, grp["collapsed"])
        # Persist so the user's preference survives restarts
        from PyQt6.QtCore import QSettings
        _s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _s.setValue(f"nav/group_{header_row}_collapsed", str(grp["collapsed"]))

    def _nav_apply_section_visibility(self, header_row: int, hide: bool):
        """Show/hide direct children; recurse into sub-group children."""
        for child_row in self._nav_section_groups[header_row]["children"]:
            child_item = self._nav.item(child_row)
            if child_item:
                child_item.setHidden(hide)
            if child_row in self._nav_section_groups:
                child_grp    = self._nav_section_groups[child_row]
                effective_hide = hide or child_grp["collapsed"]
                for sub_row in child_grp["children"]:
                    sub_item = self._nav.item(sub_row)
                    if sub_item:
                        sub_item.setHidden(effective_hide)

    def _nav_goto_label(self, label: str):
        """Navigate to the sidebar page whose label matches exactly."""
        if self._nav_mode != "home":
            self._nav_rail_go_to(label)
            return
        for row, lbl in self._nav_item_labels.items():
            if lbl == label and row not in self._nav_header_rows:
                self._nav.setCurrentRow(row)
                self._nav_set_page(row)
                return

    @pyqtSlot()
    def _toggle_sidebar(self):
        """Show/hide the rail sidebar (VSCode-style: toggle entire panel)."""
        visible = not self._nav_rail_panel.isVisible()
        self._nav_rail_panel.setVisible(visible)
        self._sidebar_toggle_btn.setText("▶" if not visible else "◀")

    def _focus_nav_search(self) -> None:
        """Expand sidebar if collapsed, then focus the search box."""
        if self._nav_collapsed:
            self._toggle_sidebar()
        self._nav_search.setFocus()
        self._nav_search.selectAll()

    @pyqtSlot(str)
    def _on_nav_search_changed(self, text: str):
        """Filter sidebar items to those whose label contains text."""
        text = text.strip().lower()
        if not text:
            # Restore visibility: show all then re-hide collapsed sections
            for row in range(self._nav.count()):
                item = self._nav.item(row)
                if item:
                    item.setHidden(False)
            for hrow, grp in self._nav_section_groups.items():
                if grp["collapsed"]:
                    self._nav_apply_section_visibility(hrow, True)
            return
        for row in range(self._nav.count()):
            if row in self._nav_header_rows:
                continue
            label = self._nav_item_labels.get(row, "").lower()
            item  = self._nav.item(row)
            if item:
                item.setHidden(text not in label)

    def _on_nav_item_clicked(self, item):
        """Toggle section/sub-group headers when clicked."""
        row = self._nav.row(item)
        if row in self._nav_section_groups:
            self._nav_toggle_section(row)

    def _build_tabs(self) -> QWidget:
        # ── Build all page widgets ────────────────────────────────────────────
        m1  = self._build_m1_tab()
        m2  = self._build_m2_tab()
        m3  = self._build_m3_tab()
        m4  = self._build_m4_tab()
        m5  = self._build_m5_tab()
        net = self._build_network_info_tab()
        dia = self._build_diagnostics_tab()
        log = self._build_logger_tab()

        from ui.pages.history_page import HistoryPage
        self._history_page = HistoryPage(store=self._store)
        self.global_time_range_changed.connect(self._history_page.set_global_hours)

        from ui.pages.inventory_page import InventoryPage
        self._inventory_page = InventoryPage(store=self._store)
        self._inventory_page.device_selected.connect(
            self._on_inventory_device_selected,
            Qt.ConnectionType.QueuedConnection,
        )

        from ui.pages.cert_page import CertPage
        self._cert_page = CertPage(store=self._store)
        self.global_time_range_changed.connect(self._cert_page.set_global_hours)

        from ui.pages.uptime_page import UptimePage
        self._uptime_page = UptimePage(store=self._store)

        from ui.pages.service_page import ServicePage
        self._service_page = ServicePage(store=self._store)
        self.global_time_range_changed.connect(self._service_page.set_global_hours)

        from ui.pages.reports_page import ReportsPage
        self._reports_page = ReportsPage(store=self._store)

        from ui.pages.notifications_page import NotificationsPage
        self._notifications_page = NotificationsPage(router=None, parent=None)
        self._notifications_page.navigate_to.connect(self._nav_rail_go_to)
        self._notifications_page.view_in_log_hub.connect(self._on_view_alert_in_log_hub)
        self._notifications_page.automation_rule_requested.connect(self._on_automation_rule_requested)
        self._notifications_page.set_store(self._store)
        self.global_time_range_changed.connect(self._notifications_page.set_global_hours)

        from ui.pages.baseline_page import BaselinePage
        self._baseline_page = BaselinePage(store=self._store, parent=None)
        self._baseline_page.drift_detected.connect(self._on_config_drift_detected)

        from ui.pages.trend_page import TrendPage
        self._trend_page = TrendPage(store=self._store, parent=None)
        self._trend_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.maintenance_page import MaintenancePage
        self._maintenance_page = MaintenancePage(parent=None)

        from ui.pages.snmp_trap_page import SnmpTrapPage
        self._snmp_trap_page = SnmpTrapPage(store=self._store)
        self._snmp_trap_page.navigate_to_settings.connect(
            lambda: self._nav_go_to("Settings")
        )

        from ui.pages.syslog_page import SyslogPage
        self._syslog_page = SyslogPage(parent=None)

        from ui.pages.log_hub_page import LogHubPage
        self._log_hub_page = LogHubPage(store=self._store, parent=None)
        self._log_hub_page.animate_requested.connect(self._on_animate_log_entry)
        self._log_hub_page.live_challenge_detected.connect(self._on_live_challenge)
        self._log_hub_page.logging_active_changed.connect(self._update_monitor_badge)
        self._log_hub_page.navigate_to.connect(self._nav_rail_go_to)
        self._last_modem_log_ts: float = 0.0
        self._last_mesh_log_ts:  float = 0.0

        from ui.pages.overview_page import OverviewPage
        self._overview_page = OverviewPage(store=self._store, parent=None)

        from ui.pages.diagnosis_page import DiagnosisPage
        self._diagnosis_page = DiagnosisPage(store=self._store, parent=None)

        from ui.pages.settings_page import SettingsPage
        self._settings_page = SettingsPage(parent=None)
        self._settings_page.reload_oui_requested.connect(self._reload_oui_db)
        self._settings_page.reset_dismissed_requested.connect(self._reset_dismissed_notices)
        self._settings_page.export_all_requested.connect(self._on_export_all)
        self._settings_page.run_setup_requested.connect(self._on_run_first_time_setup)
        self._settings_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.speed_test_page import SpeedTestPage
        self._speed_test_page = SpeedTestPage(store=self._store, parent=None)
        self._speed_test_page.modem_pause_requested.connect(self._on_modem_disconnect)
        self._speed_test_page.modem_resume_requested.connect(self._resume_modem_worker)
        self.global_time_range_changed.connect(self._speed_test_page.set_global_hours)

        from ui.pages.home_automation_page import HomeAutomationPage
        self._ha_page = HomeAutomationPage(store=self._store, parent=None)
        self._ha_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.connections_page import ConnectionsPage
        self._connections_page = ConnectionsPage(parent=None)

        from ui.pages.live_bandwidth_page import LiveBandwidthPage
        self._live_bandwidth_page = LiveBandwidthPage(parent=None)

        from ui.pages.dhcp_lease_page import DhcpLeasePage
        self._dhcp_lease_page = DhcpLeasePage(parent=None)

        from ui.pages.dns_zone_page import DnsZonePage
        self._dns_zone_page = DnsZonePage(parent=None)

        from ui.pages.threat_intel_page import ThreatIntelPage
        self._threat_intel_page = ThreatIntelPage(parent=None)
        self._threat_intel_page.show_on_map.connect(self._show_ip_on_geo_map)

        from ui.pages.security_overview_page import SecurityOverviewPage
        self._security_overview_page = SecurityOverviewPage(parent=None)
        self._security_overview_page.navigate_to.connect(self._nav_rail_go_to)
        self._security_overview_page.scan_requested.connect(self._start_full_scan)
        self._security_overview_page.security_scan_requested.connect(self._run_security_scans)

        from ui.pages.cve_page import CvePage
        self._cve_page = CvePage(self._store, parent=None)
        self._cve_page.navigate_to_inventory.connect(
            lambda ip: (self._nav_rail_go_to("Inventory Changes"), self._inventory_page.select_device(ip))
        )

        # ── DEVICE-1: device quick-profile popover ────────────────────────────
        from ui.widgets.device_popover import DevicePopover
        self._device_popover = DevicePopover(parent=self)
        self._device_popover.set_store(self._store)
        self._device_popover.navigate_to_inventory.connect(self._on_popover_open_inventory)
        self._device_popover.navigate_to_threat_intel.connect(self._on_popover_open_threat_intel)

        # Inject popover into pages that need it
        for _p in (self._connections_page, self._threat_intel_page,
                   self._cve_page, self._log_hub_page):
            if hasattr(_p, "set_popover"):
                _p.set_popover(self._device_popover)

        from ui.pages.automation_page import AutomationPage
        self._automation_page = AutomationPage(parent=None)

        from ui.pages.network_doc_page import NetworkDocPage
        self._network_doc_page = NetworkDocPage(parent=None)

        from ui.pages.mqtt_page import MqttPage
        self._mqtt_page = MqttPage(parent=None)

        from ui.pages.ip_calculator_page import IpCalculatorPage
        self._ip_calc_page = IpCalculatorPage(parent=None)

        from ui.pages.wifi_heatmap_page import WifiHeatmapPage
        self._wifi_heatmap_page = WifiHeatmapPage(parent=None)

        from ui.pages.geo_map_page import GeoMapPage
        self._geo_map_page = GeoMapPage(parent=None)

        from ui.pages.trigger_builder_page import TriggerBuilderPage
        self._trigger_page = TriggerBuilderPage(store=self._store, parent=None)

        from ui.pages.lab_mode_page import LabModePage
        self._lab_mode_page = LabModePage(store=self._store, parent=None)

        from ui.pages.protocol_viz_page import ProtocolVizPage
        self._protocol_viz_page = ProtocolVizPage(parent=None)
        self._protocol_viz_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.discover_page import FeatureGuidePage
        self._discover_page = FeatureGuidePage(parent=None)
        self._discover_page.navigate_to.connect(self._nav_rail_go_to)

        from ui.pages.hardware_integration_page import HardwareIntegrationPage
        self._hardware_integration_page = HardwareIntegrationPage(parent=None)
        self._hardware_integration_page.plugin_result.connect(self._on_hardware_plugin_result)
        self._hardware_integration_page.navigate_to.connect(self._nav_rail_go_to)
        self._hardware_integration_page.geo_map_ip.connect(self._show_ip_on_geo_map)
        self._hardware_integration_page.port_scan_ip.connect(
            lambda ip: (self._syn_host.setText(ip), self._nav_rail_go_to("Port Scan (TCP)"))
        )
        self._hardware_integration_page.check_abuse_ip.connect(
            lambda ip: (self._threat_intel_page.check_ip(ip), self._nav_rail_go_to("Threat Intelligence"))
        )

        # Pre-populate enrichment from cached QSettings so the first scan has
        # hostname / band / node data without waiting for the first poll cycle.
        from ui.pages.hardware_integration_page import _load_paths as _hw_paths, _load_last_result as _hw_last
        from modules.deco_client import _norm_mac as _hw_nm
        for _hw_p in _hw_paths():
            _hw_cached = _hw_last(_hw_p)
            if _hw_cached and _hw_cached.get("info", {}).get("type") != "modem":
                self._plugin_enrichments[_hw_p] = {
                    _hw_nm(c.get("mac", "")): c
                    for c in _hw_cached.get("clients", [])
                    if c.get("mac")
                }

        # Create one PluginDevicePage per saved plugin path.
        # Pages are registered in the nav by _build_pro_nav() further below.
        from ui.pages.plugin_device_page import PluginDevicePage
        from ui.pages.hardware_integration_page import _validate_script as _hw_validate
        from pathlib import Path as _HwPath
        self._plugin_pages: dict[str, PluginDevicePage] = {}
        for _hw_p in _hw_paths():
            _ok, _msg, _meta = _hw_validate(_hw_p)
            _hw_type   = _meta.get("type", "other") if _ok else "other"
            _hw_label  = _meta.get("name") if _ok else _HwPath(_hw_p).stem
            _hw_ip     = _meta.get("ip", "") if _ok else ""
            _cred_lbl  = _meta.get("credential_label", "Password") if _ok else "Password"
            _pg = PluginDevicePage(_hw_p, _hw_label, _hw_type, hw_ip=_hw_ip,
                                   credential_label=_cred_lbl, parent=None)
            _pg.test_requested.connect(self._on_plugin_page_test)
            if not _ok or not _HwPath(_hw_p).is_file():
                _pg.mark_unavailable()
            else:
                # Seed with cached result so page shows data on first open
                _hw_cached2 = _hw_last(_hw_p)
                if _hw_cached2:
                    _pg.update(_hw_cached2)
                    if _hw_type == "modem":
                        import time as _t2
                        from modules.network_infrastructure import hw_state as _hws
                        _s2 = _hw_cached2.get("status", {})
                        _x2 = _s2.get("extra", {})
                        _hws.update_modem({
                            "ts":               int(_t2.time()),
                            "wan_ip":           _s2.get("wan_ip"),
                            "wan_status":       _s2.get("wan_status"),
                            "firmware_version": _x2.get("firmware"),
                            "network_type":     _x2.get("network_type"),
                            "signal_bars":      _x2.get("signal_bars"),
                            "mcc":              _x2.get("mcc"),
                            "mnc":              _x2.get("mnc"),
                            "cell_id":          _x2.get("cell_id"),
                            "enb_id":           _x2.get("enb_id"),
                            "nr5g_rsrp_dbm":    _x2.get("nr5g_rsrp_dbm"),
                            "nr5g_sinr_db":     _x2.get("nr5g_sinr_db"),
                            "nr5g_rsrq_db":     _x2.get("nr5g_rsrq_db"),
                            "nr5g_band":        _x2.get("nr5g_band"),
                            "nr5g_pci":         _x2.get("nr5g_pci"),
                            "nr5g_arfcn":       _x2.get("nr5g_arfcn"),
                            "lte_rsrp_dbm":     _x2.get("lte_rsrp_dbm"),
                            "lte_snr_db":       _x2.get("lte_snr_db"),
                            "lte_rsrq_db":      _x2.get("lte_rsrq_db"),
                            "lte_band":         _x2.get("lte_band"),
                            "lte_pci":          _x2.get("lte_pci"),
                            "lte_earfcn":       _x2.get("lte_earfcn"),
                            "endc_info":        _x2.get("endc_info"),
                        }, source=_hw_p, hw_name=_hw_label)
            self._plugin_pages[_hw_p] = _pg

        # Populate Log Hub DB bar and set initial Monitor badge once the event loop starts.
        from PyQt6.QtCore import QTimer as _QT
        _QT.singleShot(0, lambda: self._log_hub_page.update_plugin_sources(
            [pg._label for pg in self._plugin_pages.values()]
        ))
        _QT.singleShot(0, self._update_monitor_badge)
        _QT.singleShot(0, self._push_monitor_pills)

        from ui.pages.mesh_router_page import MeshRouterPage
        self._mesh_router_page = MeshRouterPage(parent=None)
        self._mesh_router_page.scan_done.connect(self._on_mesh_result)
        self._mesh_router_page.geo_map_ip.connect(self._show_ip_on_geo_map)
        self._mesh_router_page.port_scan_ip.connect(
            lambda ip: (self._syn_host.setText(ip), self._nav_rail_go_to("Port Scan (TCP)"))
        )
        self._mesh_router_page.check_abuse_ip.connect(
            lambda ip: (self._threat_intel_page.check_ip(ip), self._nav_rail_go_to("Threat Intelligence"))
        )

        from ui.pages.modem_page import ModemPage
        self._modem_page = ModemPage(parent=None)
        self._modem_page.connect_requested.connect(self._on_modem_connect)
        self._modem_page.disconnect_requested.connect(self._on_modem_disconnect)

        from ui.pages.rest_api_page import RestApiPage
        self._rest_api_page = RestApiPage(store=self._store, parent=None)

        self._mtr_tab_widget      = self._build_mtr_tab()
        self._adv_tab_widget      = self._build_advanced_tools_tab()
        self._topology_tab_widget = self._build_topology_tab()
        self._arp_tab_widget      = self._build_arp_monitor_tab()
        self._dhcp_tab_widget     = self._build_dhcp_tab()
        self._bw_tab_widget       = self._build_bandwidth_tab()
        self._sched_tab_widget    = self._build_scheduler_tab()
        self._snmp_tab_widget     = self._build_snmp_tab()

        self._recon_syn_tab_widget       = self._build_recon_syn_tab()
        self._recon_udp_tab_widget       = self._build_recon_udp_tab()
        self._recon_os_tab_widget        = self._build_recon_os_tab()
        self._recon_risk_tab_widget      = self._build_recon_risk_tab()
        self._recon_cve_tab_widget       = self._build_recon_cve_tab()
        self._recon_exposure_tab_widget  = self._build_recon_exposure_tab()
        self._recon_cred_tab_widget      = self._build_recon_cred_tab()
        self._recon_discovery_tab_widget = self._build_recon_discovery_tab()
        self._recon_smb_tab_widget       = self._build_recon_smb_tab()
        self._recon_plugin_tab_widget    = self._build_recon_plugin_tab()
        self._recon_pe_tab_widget        = self._build_recon_pe_tab()
        self._recon_cloud_tab_widget     = self._build_recon_cloud_metadata_tab()
        self._ipv6_tab_widget            = self._build_ipv6_tab()
        self._correlator_tab_widget      = self._build_correlator_tab()
        self._iot_baseline_tab_widget    = self._build_iot_baseline_tab()
        self._benchmark_tab_widget       = self._build_benchmark_tab()

        from ui.pages.wifi_monitor_page import WiFiMonitorPage
        self._wifi_monitor_page = WiFiMonitorPage(parent=None)

        from ui.pages.monitor_overview_page import MonitorOverviewPage
        self._monitor_overview_page = MonitorOverviewPage(parent=None)
        self._monitor_overview_page.navigate_to.connect(self._nav_rail_go_to)

        self._help_tab_widget            = self._build_help_tab()

        # ── Store tab refs for mode nav builders ──────────────────────────────
        self._m1_tab = m1
        self._m2_tab = m2
        self._m3_tab = m3
        self._m4_tab = m4
        self._m5_tab = m5
        self._net_tab = net
        self._dia_tab = dia
        self._log_tab = log

        # Unified logging container — "Log Sources" (config) first, "Activity Log" (viewer) second.
        # Created here before the nav runs so each widget has exactly one parent (the container)
        # and is never registered separately in the stack.
        from PyQt6.QtWidgets import QTabWidget as _LogTW
        self._logging_container = _LogTW()
        self._logging_container.setStyleSheet(
            f"QTabWidget::pane {{ border:1px solid {BORDER}; background:{BG_DARK}; }}"
            f"QTabBar::tab {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"  padding:6px 18px; border:1px solid {BORDER}; border-bottom:none; margin-right:2px; }}"
            f"QTabBar::tab:selected {{ background:{ACCENT}; color:{BG_DARK}; font-weight:bold; }}"
            f"QTabBar::tab:hover {{ background:{BG_HOVER}; }}"
        )
        self._logging_container.addTab(self._log_tab,       "Log Sources")
        self._logging_container.addTab(self._log_hub_page,  "Activity Log")

        # HomePage (pre-instantiated here; registered in stack below)
        from ui.pages.home_page import HomePage
        self._home_page = HomePage(store=self._store, parent=None)
        # Wire HomePage hero buttons and incoming speed results (guard prevents
        # double-connection if _build_tabs() is ever called more than once)
        self._pending_live_scenario = None
        if not self._home_page._signals_connected:
            self._home_page._btn_scan.clicked.connect(self._start_full_scan)
            self._home_page._btn_rescan_compact.clicked.connect(self._start_full_scan)
            self._home_page._btn_isp.clicked.connect(self._open_isp_from_home)
            self._home_page._btn_diagnose.clicked.connect(self._open_diagnosis)
            self._speed_test_page.test_completed.connect(self._home_page.on_speed_result)
            self._speed_test_page.test_completed.connect(self._on_speed_test_modem_forward)
            self._home_page.navigate_to.connect(self._on_overview_navigate)
            self._home_page.start_monitoring_requested.connect(self._toggle_logger)
            self._home_page.investigate_live_requested.connect(self._on_investigate_live)
            self._home_page.alert_view_requested.connect(self._on_alert_view_requested)
            self._home_page.rescan_requested.connect(self._start_full_scan)
            self._home_page._signals_connected = True
        self._overview_page.navigate_to.connect(self._on_overview_navigate)
        self._overview_page.scan_requested.connect(self._start_full_scan)
        self._overview_page.report_requested.connect(self._run_full_report)
        self._overview_page.export_requested.connect(self._export_report)
        self._overview_page.security_scan_requested.connect(self._run_security_scans)
        self._overview_page.modem_tile_clicked.connect(self._on_modem_tile_clicked)
        self._active_modem_plugin_label: str = ""
        self._diagnosis_page.navigate_to.connect(self._on_overview_navigate)
        self._diagnosis_page.diagnosis_saved.connect(self._home_page.refresh_diag_summary)

        # Populate home page suggestions on first build (deferred so _home_page exists)
        from PyQt6.QtCore import QTimer as _QTr
        _QTr.singleShot(0, self._refresh_home_suggestions)

        # ── Worker refs ───────────────────────────────────────────────────────
        self._arp_worker:        Optional[object] = None
        self._dhcp_worker:       Optional[object] = None
        self._bw_worker:         Optional[object] = None
        self._sched_worker:      Optional[object] = None
        self._snmp_worker:       Optional[object] = None
        self._syn_worker:        Optional[object] = None
        self._udp_worker:        Optional[object] = None
        self._cve_worker:        Optional[object] = None
        self._exposure_worker:   Optional[object] = None
        self._os_worker:         Optional[object] = None
        self._cred_worker:       Optional[object] = None
        self._discovery_worker:  Optional[object] = None
        self._smb_worker:        Optional[object] = None
        self._pe_worker:         Optional[object] = None
        self._ipv6_worker:       Optional[object] = None
        self._cloud_worker:      Optional[object] = None
        self._log_chart_summary: Optional[object] = None   # last loaded LogSummary
        self._last_benchmark_result: Optional[object] = None  # last BenchmarkResult

        # ── Sidebar list + stacked content ────────────────────────────────────
        self._nav = QListWidget()
        self._nav.setObjectName("sideNav")
        self._nav_delegate = self._NavAdminDelegate(self._nav_admin_rows, RED, self._nav)
        self._nav.setItemDelegate(self._nav_delegate)
        # Right-click → pin/unpin to Favourites
        self._nav.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._nav.customContextMenuRequested.connect(self._nav_context_menu)
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.setMinimumSize(0, 0)
        # Pre-register HomePage so _nav_ref() can find it via indexOf()
        self._stack.addWidget(self._home_page)
        self._stack.addWidget(self._diagnosis_page)
        self._stack.addWidget(self._lab_mode_page)
        self._stack.addWidget(self._protocol_viz_page)
        self._stack.addWidget(self._discover_page)
        self._stack.addWidget(self._hardware_integration_page)
        self._stack.addWidget(self._rest_api_page)
        self._nav_row_to_page:   dict = {}
        self._nav_separators:    set  = set()
        # Extended nav data model
        self._nav_item_icons:    dict = {}
        self._nav_item_labels:   dict = {}
        self._nav_header_rows:   set  = set()
        self._nav_section_groups: dict = {}
        self._nav_current_section:  int  = -1
        self._nav_current_subgroup: int  = -1
        self._nav_collapsed:     bool = False

        # ── PINNED — top 7 most-used pages; always visible, no subgroups ──────────
        self._nav_add_section("Pinned", icon="📌")
        self._nav_add_page("⬡", "Overview",             self._overview_page)
        self._nav_add_page("◎", "DNS & Outages",        m5)
        self._nav_add_page("▲", "Live Bandwidth",       self._live_bandwidth_page)
        self._nav_add_page("⚡", "Speed Test",           self._speed_test_page)
        self._nav_add_page("⊞", "Devices on Network",   m1)
        self._nav_add_page("⏷", "Availability History", self._history_page)
        self._nav_add_page("⇄", "Active Connections",   self._connections_page)

        # ── STANDARD — full organised structure ───────────────────────────────────
        self._nav_add_section("Standard", icon="◼", collapsed_by_default=False)

        # Discover — expanded by default so the user immediately sees what's there
        self._nav_add_subgroup("Discover", icon="🖥", collapsed_by_default=False)
        self._nav_add_page ("〇", "WiFi Networks",        m4)
        self._nav_add_page ("ℹ",  "Network Info",         net)
        self._nav_add_page ("≡", "DHCP Lease Inventory", self._dhcp_lease_page)
        self._nav_add_page ("⊹", "DNS Zone Map",         self._dns_zone_page)
        self._nav_current_subgroup = -1

        # Threat Detection — collapsed; expand when you need security analysis
        self._nav_add_subgroup("Threat Detection", icon="🛡")
        self._nav_add_page("⚠", "Broadcast Storm",      m3)
        self._nav_add_page("⇌", "Rogue Bridge (STP)",   m2)
        self._nav_add_page("◈", "IoT Behaviour",        self._iot_baseline_tab_widget)
        self._nav_current_subgroup = -1

        # Health & History — collapsed; historical data on demand
        self._nav_add_subgroup("Health & History", icon="◉")
        self._nav_add_page ("∆", "Inventory Changes",    self._inventory_page)
        self._nav_add_page ("✓", "Uptime & SLA",         self._uptime_page)
        self._nav_add_page ("◉", "Service Heartbeat",    self._service_page)
        self._nav_add_page ("▦", "Network Grade",        self._benchmark_tab_widget)
        self._nav_current_subgroup = -1

        # Diagnostics — collapsed; deeper investigation tools
        self._nav_add_subgroup("Diagnostics", icon="💊")
        self._nav_add_page("≣", "Network Logger",        self._logging_container)
        self._nav_add_page("↗", "Trend Forecasts",      self._trend_page)
        self._nav_add_page("⬡", "IPv6 Devices",         self._ipv6_tab_widget)
        self._nav_current_subgroup = -1

        # Reports & Alerts — collapsed; admin/config
        self._nav_add_subgroup("Reports & Alerts", icon="🔔")
        self._nav_add_page("◟", "Notifications",        self._notifications_page)
        self._nav_add_page("⊟", "Auto Reports",         self._reports_page)
        self._nav_add_page("⊛", "Config Snapshots",     self._baseline_page)
        self._nav_add_page("⚙", "Maintenance Windows",  self._maintenance_page)
        self._nav_add_page("△", "Custom Triggers",      self._trigger_page)
        self._nav_current_subgroup = -1

        # Tools — collapsed; utilities
        self._nav_add_subgroup("Tools", icon="⚡")
        self._nav_add_page ("⌂", "Home Automation",     self._ha_page)
        _tools_heatmap_row = self._nav_add_page("◈", "WiFi Heatmap",       self._wifi_heatmap_page)
        _tools_geomap_row  = self._nav_add_page("⊕", "Geolocation Map",    self._geo_map_page)
        self._nav_current_subgroup = -1

        # ── ADVANCED (collapsed by default) ────────────────────────────────────
        self._nav_adv_sep = self._nav.count()
        self._nav_add_section("Advanced", icon="⚙", collapsed_by_default=True)

        self._nav_add_subgroup("Deep Analysis", icon="🔬")
        _mtr_row  = self._nav_add_page("⦳", "Hop-by-Hop Trace",  self._mtr_tab_widget)
        _arp_row  = self._nav_add_page("⊙", "ARP Spoof Watch",    self._arp_tab_widget)
        _snmp_row = self._nav_add_page("⊳", "SNMP Device Info",   self._snmp_tab_widget)
        _snmp_trap_row = self._nav_add_page("⊲", "SNMP Trap Receiver", self._snmp_trap_page)
        _syslog_row    = self._nav_add_page("≡", "Syslog Viewer",       self._syslog_page)
        self._nav_current_subgroup = -1

        _adv_tools_row = self._nav_add_page("⚙", "Tools & Wake-on-LAN", self._adv_tab_widget)
        _adv_map_row   = self._nav_add_page("⬡", "Network Map",          self._topology_tab_widget)
        _adv_bw_row    = self._nav_add_page("▲", "Bandwidth Usage",       self._bw_tab_widget)
        _adv_sched_row = self._nav_add_page("⏱", "Scheduled Scans",       self._sched_tab_widget)
        _adv_auto_row  = self._nav_add_page("→", "Automation Hooks",      self._automation_page)
        _adv_doc_row   = self._nav_add_page("▣", "Network Doc",            self._network_doc_page)
        _adv_mqtt_row  = self._nav_add_page("◉", "MQTT / Home Assistant",  self._mqtt_page)

        # compat refs
        self._nav_adv_rows      = [_mtr_row, _adv_tools_row, _adv_map_row,
                                    _arp_row, _adv_bw_row, _adv_sched_row,
                                    _snmp_row, _snmp_trap_row, _syslog_row,
                                    _adv_auto_row, _adv_doc_row, _adv_mqtt_row,
                                    _tools_heatmap_row]
        self._adv_tab_index_adv = _adv_tools_row
        self._adv_tab_index_mtr = _mtr_row
        self._nav_separators.add(self._nav_adv_sep)

        # ── SECURITY AUDIT (collapsed by default) ──────────────────────────────
        self._nav_recon_sep = self._nav.count()
        self._nav_add_section("Security Audit", icon="🔐", collapsed_by_default=True)
        self._nav_recon_rows = [
            self._nav_add_page("⊙", "Security Overview",      self._security_overview_page),
            self._nav_add_page("🧠", "Threat Intelligence",    self._threat_intel_page),
            self._nav_add_page("✚", "TLS & exposure",         self._cert_page),
            self._nav_add_page("🔎", "Port Scan (TCP)",        self._recon_syn_tab_widget),
            self._nav_add_page("🔎", "Port Scan (UDP)",        self._recon_udp_tab_widget),
            self._nav_add_page("💻", "OS Detection",           self._recon_os_tab_widget),
            self._nav_add_page("⚠",  "Device Risk Score",     self._recon_risk_tab_widget),
            self._nav_add_page("🛡", "Known CVEs",             self._recon_cve_tab_widget),
            self._nav_add_page("📋", "CVE Tracker",              self._cve_page),
            self._nav_add_page("🌍", "Exposed to Internet",    self._recon_exposure_tab_widget),
            self._nav_add_page("🔑", "Login Test (SSH/SMB)",   self._recon_cred_tab_widget),
            self._nav_add_page("🔭", "Full Device Discovery",  self._recon_discovery_tab_widget),
            self._nav_add_page("🗂", "Windows Shares (SMB)",   self._recon_smb_tab_widget),
            self._nav_add_page("🔌", "Recon Plugins",          self._recon_plugin_tab_widget),
            self._nav_add_page("🔒", "Private Endpoint Check", self._recon_pe_tab_widget),
            self._nav_add_page("☁",  "Cloud Metadata Probe",  self._recon_cloud_tab_widget),
        ]
        self._nav_separators.add(self._nav_recon_sep)
        self._recon_tab_start_index = -1  # kept for compat

        # ── EDUCATION (collapsed by default) ───────────────────────────────────
        self._nav_edu_sep = self._nav.count()
        self._nav_add_section("Education", icon="◎", collapsed_by_default=True)
        self._nav_add_page("⬡", "Lab Mode",             self._lab_mode_page)
        self._nav_add_page("◈", "Protocol Visualizer",  self._protocol_viz_page)
        self._nav_add_page("◉", "Feature Guide",        self._discover_page)
        self._nav_add_page("?", "Help & Reference",     self._help_tab_widget)
        self._nav_separators.add(self._nav_edu_sep)

        # ── EXTEND (collapsed by default) ───────────────────────────────────
        self._nav_extend_sep = self._nav.count()
        self._nav_add_section("Extend", icon="⬡", collapsed_by_default=True)
        self._nav_add_page("⊕", "Hardware", self._hardware_integration_page)
        self._nav_separators.add(self._nav_extend_sep)

        # Apply initial collapse for ALL groups that start collapsed (both level-0
        # sections and level-1 sub-groups).  Process level-0 first so parent
        # hide state is established before children are evaluated.
        for _hrow, _grp in self._nav_section_groups.items():
            if _grp["collapsed"] and _grp["level"] == 0:
                self._nav_apply_section_visibility(_hrow, True)
        for _hrow, _grp in self._nav_section_groups.items():
            if _grp["collapsed"] and _grp["level"] == 1:
                self._nav_apply_section_visibility(_hrow, True)

        # ── Wire signals ──────────────────────────────────────────────────────
        self._nav.currentRowChanged.connect(self._on_nav_row_changed)
        self._nav.itemClicked.connect(self._on_nav_item_clicked)
        # Select the Overview row (first real page in the Pinned section)
        self._nav.setCurrentRow(1)

        # ── Build sidebar panels ───────────────────────────────────────────────
        # Panel 0 — flat QListWidget sidebar (Home mode)
        self._nav_flat_panel = QWidget()
        self._nav_flat_panel.setFixedWidth(220)
        self._nav_flat_panel.setStyleSheet(f"QWidget {{ background:{SIDEBAR_BG}; }}")
        _fp_lay = QVBoxLayout(self._nav_flat_panel)
        _fp_lay.setContentsMargins(0, 0, 0, 0)
        _fp_lay.setSpacing(0)

        self._mode_seg_btns: dict = {}   # kept for compat — buttons no longer rendered

        # Search / filter (flat panel only — hidden by default)
        self._nav_search = QLineEdit()
        self._nav_search.setObjectName("navSearch")
        self._nav_search.setPlaceholderText("  Filter…")
        self._nav_search.setFixedHeight(28)
        self._nav_search.setStyleSheet(
            f"QLineEdit#navSearch {{"
            f" background:{SIDEBAR_HOVER}; color:{SIDEBAR_ITEM_FG};"
            f" border:none; border-bottom:1px solid {NAV_DIVIDER};"
            f" padding:0 8px; font-size:11px; }}"
            f"QLineEdit#navSearch:focus {{ color:{WHITE}; }}"
        )
        self._nav_search.textChanged.connect(self._on_nav_search_changed)
        self._nav_search.setVisible(False)

        # Collapse ◀ / ▶ toggle (flat panel footer)
        self._sidebar_toggle_btn = QPushButton("◀")
        self._sidebar_toggle_btn.setFixedHeight(24)
        self._sidebar_toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{SIDEBAR_SECTION_BG}; color:{SIDEBAR_SECTION_FG};"
            f" border:none; border-top:1px solid {NAV_DIVIDER}; font-size:11px; }}"
            f"QPushButton:hover {{ color:{WHITE}; background:{SIDEBAR_HOVER}; }}"
        )
        self._sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)

        _fp_lay.addWidget(self._nav_search)
        _fp_lay.addWidget(self._nav, 1)
        _fp_lay.addWidget(self._sidebar_toggle_btn)

        # Panel 1 — activity rail + flyout (Standard/Pro mode)
        self._nav_rail_panel = QWidget()
        self._nav_rail_panel.setStyleSheet(f"QWidget {{ background:{SIDEBAR_BG}; }}")
        _rp_lay = QHBoxLayout(self._nav_rail_panel)
        _rp_lay.setContentsMargins(0, 0, 0, 0)
        _rp_lay.setSpacing(0)

        # 48px icon rail
        self._nav_rail = QWidget()
        self._nav_rail.setFixedWidth(56)
        self._nav_rail.setStyleSheet(
            f"background: {SIDEBAR_BG}; border-right: 1px solid {NAV_DIVIDER};"
        )
        self._nav_rail_lay = QVBoxLayout(self._nav_rail)
        self._nav_rail_lay.setContentsMargins(0, 0, 0, 0)
        self._nav_rail_lay.setSpacing(0)

        # Mode pill at top of rail (cycling dot)
        self._rail_mode_btn = QPushButton("●")
        self._rail_mode_btn.setFixedSize(48, 32)
        self._rail_mode_btn.setToolTip("Click to cycle: Standard → Pro → Home")
        self._rail_mode_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rail_mode_btn.clicked.connect(self._cycle_mode)
        self._rail_mode_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {ACCENT}; font-size: 10px; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.07); }}"
        )
        self._rail_mode_btn.setVisible(False)  # mode switcher removed

        # Persistent search button — always visible at top of rail, opens Ctrl+K palette
        _rail_search_btn = QPushButton()
        _rail_search_btn.setFixedSize(56, 36)
        _rail_search_btn.setToolTip("Search all pages  (Ctrl+K)")
        _rail_search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _rail_search_btn.setIcon(_make_nav_icon("search", 18, "#6B7A8D"))
        _rail_search_btn.setIconSize(QSize(18, 18))
        _rail_search_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; outline: none;"
            f" border-bottom: 1px solid {NAV_DIVIDER}; }}"
            f"QPushButton:hover {{ background: rgba(255,255,255,0.07); }}"
            f"QPushButton:focus, QPushButton:focus-visible {{"
            f" outline: none; border: none; border-bottom: 1px solid {NAV_DIVIDER}; }}"
        )
        _rail_search_btn.clicked.connect(self._open_command_palette)
        self._nav_rail_lay.addWidget(_rail_search_btn)
        self._nav_rail_lay.addStretch()

        # Settings button pinned at bottom of rail
        self._rail_settings_btn = _RailButton("settings", "Settings")
        self._rail_settings_btn.clicked.connect(self._open_settings_dialog)
        self._nav_rail_lay.addWidget(self._rail_settings_btn)

        # Flyout panel (zero-width when closed)
        self._nav_flyout = _FlyoutPanel(self._nav_rail_panel)

        _rp_lay.addWidget(self._nav_rail)
        _rp_lay.addWidget(self._nav_flyout)

        # Sidebar container — show/hide panels so the layout respects their widths
        self._nav_sidebar_container = QWidget()
        _sc_lay = QHBoxLayout(self._nav_sidebar_container)
        _sc_lay.setContentsMargins(0, 0, 0, 0)
        _sc_lay.setSpacing(0)
        _sc_lay.addWidget(self._nav_flat_panel)
        _sc_lay.addWidget(self._nav_rail_panel)
        self._nav_rail_panel.setVisible(True)    # always visible — no mode switcher

        # Canvas click filter — closes flyout when user clicks content area
        self._canvas_filter = _CanvasClickFilter(self)
        self._canvas_filter.close_requested.connect(self._on_canvas_click)

        # ── Assemble sidebar + content area ───────────────────────────────────
        container = QWidget()
        container.setObjectName("contentArea")
        h = QHBoxLayout(container)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self._nav_sidebar_container)
        # 1px divider between sidebar stack and content
        div = QFrame()
        div.setFrameShape(QFrame.Shape.VLine)
        div.setStyleSheet(f"background: {NAV_DIVIDER}; max-width: 1px;")
        h.addWidget(div)
        # Content wrapper
        content_wrapper = QWidget()
        content_wrapper.setObjectName("contentArea")
        cw_lay = QVBoxLayout(content_wrapper)
        cw_lay.setContentsMargins(12, 10, 12, 8)
        cw_lay.setSpacing(0)

        # Breadcrumb row — label + "?" help button
        bc_row = QHBoxLayout()
        bc_row.setContentsMargins(0, 0, 0, 0)
        bc_row.setSpacing(4)
        self._back_btn = QPushButton("‹ Back")
        self._back_btn.setFixedHeight(20)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:11px; background:transparent;"
            f" border:none; padding:0 4px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
        )
        self._back_btn.setVisible(False)
        self._back_btn.clicked.connect(self._nav_go_back)
        bc_row.addWidget(self._back_btn)

        self._breadcrumb_lbl = QLabel("Getting Started  ›  Home")
        self._breadcrumb_lbl.setFixedHeight(20)
        self._breadcrumb_lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 0 2px;"
            f" background: transparent; border: none;"
        )
        bc_row.addWidget(self._breadcrumb_lbl, 1)

        cw_lay.addLayout(bc_row)

        self._tip_bar = QPushButton("ⓘ  Tips  ▾")
        self._tip_bar.setCheckable(True)
        self._tip_bar.setFixedHeight(22)
        self._tip_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tip_bar.setStyleSheet(
            f"QPushButton {{ text-align:left; padding:0 10px; font-size:10px;"
            f" color:{ACCENT}; background:transparent; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
            f"QPushButton:hover {{ color:{WHITE}; }}"
            f"QPushButton:checked {{ color:{WHITE}; font-weight:bold;"
            f" border-bottom:1px solid {ACCENT}; }}"
        )
        self._tip_bar.toggled.connect(self._toggle_help_panel)
        cw_lay.addWidget(self._tip_bar)

        # Collapsible help strip — shown below breadcrumb, hidden by default
        self._help_panel = QFrame()
        self._help_panel.setObjectName("pageHelpPanel")
        self._help_panel.setStyleSheet(
            f"QFrame#pageHelpPanel {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:6px; }}"
        )
        self._help_panel.setVisible(False)
        hp_lay = QVBoxLayout(self._help_panel)
        hp_lay.setContentsMargins(12, 8, 12, 8)
        hp_lay.setSpacing(4)
        self._help_what_lbl = QLabel()
        self._help_what_lbl.setWordWrap(True)
        self._help_what_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        hp_lay.addWidget(self._help_what_lbl)
        self._help_hidden_lbl = QLabel()
        self._help_hidden_lbl.setWordWrap(True)
        self._help_hidden_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        hp_lay.addWidget(self._help_hidden_lbl)

        _kbd_shortcuts = [
            ("Ctrl+K",         "Command palette — find any page or feature"),
            ("Ctrl+R",         "Run full network scan"),
            ("Ctrl+E",         "Export last scan results"),
            ("Ctrl+Q",         "Quit"),
            ("F5",             "Refresh current page"),
            ("Escape",         "Close section panel"),
            ("Right-click",    "Context menu on any table row"),
            ("Ctrl+Shift+M",   "Visual Diagnostic Overlay"),
        ]
        self._help_shortcuts_lbl = QLabel(
            "<b>Keyboard shortcuts:</b>  " +
            "   ·   ".join(f"<code>{k}</code> {d}" for k, d in _kbd_shortcuts)
        )
        self._help_shortcuts_lbl.setWordWrap(True)
        self._help_shortcuts_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
            f" border-top:1px solid {BORDER}; padding-top:4px; margin-top:2px;"
        )
        self._help_shortcuts_lbl.setTextFormat(Qt.TextFormat.RichText)
        hp_lay.addWidget(self._help_shortcuts_lbl)

        cw_lay.addWidget(self._help_panel)

        cw_lay.setSpacing(6)
        cw_lay.addWidget(self._stack)
        h.addWidget(content_wrapper, 1)
        content_wrapper.installEventFilter(self._canvas_filter)

        # Copy-to-clipboard right-click menus
        for tbl in (
            self._m1_table, self._m2_table, self._m3_table, self._m4_table,
            self._m5_outage_table, self._net_devices_table, self._adapters_table,
            self._diag_ping_table, self._diag_dns_table, self._diag_trace_table,
            self._diag_leak_table, self._log_live_table, self._log_outage_table,
            self._mtr_table, self._ps_table, self._bl_table,
            self._arp_table, self._dhcp_table, self._bw_table, self._snmp_table,
            self._recon_syn_table, self._recon_udp_table,
            self._recon_os_table, self._recon_risk_table, self._recon_cve_table,
            self._recon_exposure_table,
            self._recon_cred_sw_table, self._recon_cred_svc_table,
            self._recon_cred_user_table, self._recon_disc_table,
            self._recon_smb_shares_table, self._recon_smb_users_table,
            self._ipv6_table, self._cloud_network_table,
        ):
            self._enable_copy_menu(tbl)

        # Alert badge refresh — poll every 30 s for unacked alerts on Security Audit section
        self._alert_badge_timer = QTimer(self)
        self._alert_badge_timer.setInterval(30_000)
        self._alert_badge_timer.timeout.connect(self._refresh_alert_badge)
        self._alert_badge_timer.start()
        # Attach empty-state overlays to key scan tables
        from ui.empty_state import EmptyStateOverlay
        EmptyStateOverlay(self._m1_table, "⊞", "No devices found",
                          "Click  Scan  to discover devices on the network")
        EmptyStateOverlay(self._m2_table, "⇌", "No STP anomalies detected",
                          "Run a scan to check for rogue bridges")
        EmptyStateOverlay(self._m3_table, "⚠", "No storms detected",
                          "Run a scan to check for broadcast storms")

        # Keep self._tabs pointing at something for any legacy code that checks it
        self._tabs = container
        return container

    @pyqtSlot(int)
    def _on_nav_row_changed(self, row: int):
        """Navigate to the page for the selected nav row."""
        if row < 0 or row in self._nav_header_rows:
            return
        # Action rows trigger a callable instead of navigating
        if row in self._nav_action_rows:
            self._nav_action_rows[row]()
            return
        self._nav_set_page(row)
        # Reset tray badge when user views any page (they are attending to the app)
        if hasattr(self, "_tray_manager"):
            self._tray_manager.reset_badge()

    def _nav_go_to(self, label: str) -> None:
        """Programmatically navigate to the page with the given sidebar label."""
        if self._nav_mode != "home":
            self._nav_rail_go_to(label)
            return
        for row, lbl in self._nav_item_labels.items():
            if lbl == label:
                self._nav.setCurrentRow(row)
                return

    # ── Progressive-disclosure nav ────────────────────────────────────────────

    def _update_mode_pill(self) -> None:
        """Highlight the active segment in the mode segmented control."""
        if hasattr(self, "_mode_seg_btns"):
            for _mk, _mb in self._mode_seg_btns.items():
                _mb.setChecked(_mk == self._nav_mode)
        if hasattr(self, "_header_mode_lbl"):
            self._header_mode_lbl.setVisible(False)
        # Rail mode button shows the current mode letter
        if hasattr(self, "_rail_mode_btn"):
            _short = {"home": "H", "standard": "S", "pro": "P"}.get(self._nav_mode, "?")
            _accent = {"home": ACCENT, "standard": "#2E7D32", "pro": "#C62828"}.get(
                self._nav_mode, ACCENT
            )
            self._rail_mode_btn.setText(_short)
            self._rail_mode_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: none;"
                f" color: {_accent}; font-size: 11px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: rgba(255,255,255,0.07); }}"
            )

    def _cycle_mode(self) -> None:
        """Cycle through home → standard → pro → home on pill click."""
        _order = ["home", "standard", "pro"]
        _idx = _order.index(self._nav_mode) if self._nav_mode in _order else 0
        self._set_mode(_order[(_idx + 1) % len(_order)])

    def _set_mode(self, mode: str) -> None:
        """Switch to mode, persist, and rebuild the nav."""
        self._nav_mode = mode
        from PyQt6.QtCore import QSettings
        s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        s.setValue("nav/mode", mode)
        s.sync()
        self._rebuild_nav_for_mode()

    def _open_isp_from_home(self) -> None:
        if self._nav_mode == "home":
            self._set_mode("standard")
        self._nav_go_to("Network Health Report")

    def _rebuild_nav_for_mode(self) -> None:
        """Clear sidebar and rebuild it for the current _nav_mode."""
        # ── Reset flat-nav state ───────────────────────────────────────────────
        self._nav.clear()
        self._nav_row_to_page.clear()
        self._nav_item_icons.clear()
        self._nav_item_labels.clear()
        self._nav_header_rows.clear()
        self._nav_section_groups.clear()
        self._nav_separators.clear()
        self._nav_action_rows.clear()
        self._nav_admin_rows.clear()
        self._nav_audit_rows.clear()
        self._nav_current_section  = -1
        self._nav_current_subgroup = -1
        # Reset compat refs so methods that check them don't crash
        self._adv_tab_index_adv = -1
        self._adv_tab_index_mtr = -1

        # ── Reset rail-nav state ───────────────────────────────────────────────
        self._nav_sections.clear()
        self._nav_page_to_section.clear()
        self._nav_open_section = ""
        if hasattr(self, "_nav_flyout") and self._nav_flyout.maximumWidth() > 0:
            self._nav_flyout.close_panel()

        # ── Sidebar panel — rail is permanent, flat panel zeroed out ─────────────
        # setFixedWidth(0) removes the flat panel's contribution to the container's
        # max-width, letting the flyout expand freely to its full 260 px.
        self._nav_flat_panel.setFixedWidth(0)
        self._nav_flat_panel.setVisible(False)
        self._nav_rail_panel.setVisible(True)

        # ── Build nav content — always the full Pro set ───────────────────────
        self._build_pro_nav()

        # ── Inject Pinned section at the top if user has pins ─────────────────
        # _build_pro_nav populates _nav_label_to_widget so widget lookups work here
        # NAV-3: ≤4 pins → individual direct-nav buttons with visible labels on rail
        #        >4 pins → single "Pinned" flyout section (preserves existing behaviour)
        if self._nav_pinned_labels:
            _pinned_entries = []
            for _lbl in sorted(self._nav_pinned_labels):
                _w = self._nav_label_to_widget.get(_lbl)
                if _w is not None:
                    _pinned_entries.append(_NavEntry(
                        label=_lbl, page=_w,
                        admin_required=False, audit_item=False, pinned=True,
                    ))
            if _pinned_entries and len(_pinned_entries) > 4:
                self._nav_sections.insert(0, {
                    "name": "Pinned", "icon": "pin", "entries": _pinned_entries,
                })
            # ≤4 pins: stored separately; _nav_finalize_rail renders them as direct buttons
            self._nav_direct_pins: list = _pinned_entries if len(_pinned_entries) <= 4 else []
        else:
            self._nav_direct_pins = []

        # ── Finalise rail and restore last-used section (VSCode style) ────────
        self._nav_finalize_rail()
        _qs = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _last = _qs.value("nav/last_section", "")
        _open = _last if any(s["name"] == _last for s in self._nav_sections) \
                else (self._nav_sections[0]["name"] if self._nav_sections else "")
        if _open:
            self._nav_rail_toggle(_open)
            _sec = next((s for s in self._nav_sections if s["name"] == _open), None)
            if _sec and _sec["entries"]:
                self._nav_rail_go_to(_sec["entries"][0].label)

        self._update_mode_pill()

        # Final pass: guarantee all audit rows are red regardless of build order
        from PyQt6.QtGui import QColor as _QColor
        for _arow in self._nav_audit_rows:
            _aitem = self._nav.item(_arow)
            if _aitem:
                _aitem.setForeground(_QColor(AUDIT_RED))

    def _nav_ref(self, icon: str, label: str, widget: "QWidget") -> int:
        """Add a nav alias entry for a widget already registered in the stack."""
        idx = self._stack.indexOf(widget)
        if idx < 0:
            idx = self._stack.addWidget(widget)
        self._nav_label_to_widget[label] = widget
        return self._nav_add_alias(icon, label, idx)

    def _nav_flat_item(self, icon: str, label: str, widget: "QWidget",
                       admin_required: bool = False, audit_item: bool = False) -> int:
        """Add a flat-nav item and optionally mark it admin/audit for red styling."""
        row = self._nav_ref(icon, label, widget)
        if admin_required:
            self._nav_admin_rows.add(row)
        if audit_item:
            self._nav_audit_rows.add(row)
        return row

    def _nav_add_action(self, icon: str, label: str, action) -> int:
        """Add a nav item that calls *action* instead of navigating to a page."""
        from PyQt6.QtCore import QSize
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(QSize(0, 30))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]  = icon
        self._nav_item_labels[row] = label
        parent = (self._nav_current_subgroup if self._nav_current_subgroup >= 0
                  else self._nav_current_section)
        if parent >= 0:
            self._nav_section_groups[parent]["children"].append(row)
        self._nav_refresh_item_text(row)
        self._nav_action_rows[row] = action
        return row

    def _nav_add_spacer(self) -> None:
        """Add a non-selectable visual spacer row in the nav list."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QBrush
        sep = QListWidgetItem()
        sep.setFlags(Qt.ItemFlag.NoItemFlags)
        sep.setSizeHint(QSize(0, 10))
        sep.setBackground(QBrush(QColor(SIDEBAR_BG)))
        self._nav.addItem(sep)
        self._nav_header_rows.add(self._nav.count() - 1)

    def _nav_add_section_label(self, label: str, fg_color: str = None) -> int:
        """Add a NON-collapsible ALL-CAPS section divider label (not interactive)."""
        from PyQt6.QtCore import QSize
        from PyQt6.QtGui import QColor, QFont as _QFont
        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)   # not selectable, not clickable
        item.setSizeHint(QSize(0, 26))
        f = _QFont("Segoe UI", 9)
        f.setBold(True)
        item.setFont(f)
        item.setText(f"  {label.upper()}")
        _fg = fg_color or SIDEBAR_SECTION_FG
        item.setForeground(QColor(_fg))
        self._nav.addItem(item)
        row = self._nav.count() - 1
        self._nav_item_icons[row]  = ""
        self._nav_item_labels[row] = label
        self._nav_header_rows.add(row)
        # Deliberately NOT in _nav_section_groups — no collapse/expand logic
        return row

    # ── Rail-mode nav helpers ─────────────────────────────────────────────────

    def _nav_begin_section(self, name: str, icon: str) -> None:
        """Start a new section in rail mode. Must be followed by _nav_add_rail_item calls."""
        self._nav_sections.append({"name": name, "icon": icon, "entries": []})

    def _nav_add_rail_item(
        self,
        label: str,
        widget: "QWidget",
        pinned: bool = False,
        admin_required: bool = False,
        audit_item: bool = False,
    ) -> None:
        """Register a page under the current rail section (last in _nav_sections)."""
        if not self._nav_sections:
            return
        # Ensure widget is in the stack
        if self._stack.indexOf(widget) < 0:
            self._stack.addWidget(widget)
        self._nav_label_to_widget[label] = widget
        entry = _NavEntry(
            label=label,
            page=widget,
            admin_required=admin_required,
            audit_item=audit_item,
            pinned=label in self._nav_pinned_labels or pinned,
        )
        self._nav_sections[-1]["entries"].append(entry)
        self._nav_page_to_section[label] = self._nav_sections[-1]["name"]

    def _nav_finalize_rail(self) -> None:
        """Build _RailButton widgets from _nav_sections and wire them up."""
        # Clear old rail buttons (between the mode-btn and settings-btn)
        stretch_idx = None
        for i in range(self._nav_rail_lay.count()):
            item = self._nav_rail_lay.itemAt(i)
            if item and item.spacerItem():
                stretch_idx = i
                break
        # Remove all rail section buttons (inserted between mode btn and stretch)
        while stretch_idx and stretch_idx > 1:
            item = self._nav_rail_lay.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()
            stretch_idx -= 1

        self._nav_rail_buttons.clear()
        self._nav_rail_pin_buttons: dict = {}  # label -> _RailPinButton

        # NAV-3: Direct-nav Quick Access buttons (≤4 pins) ─────────────────────
        direct_pins = getattr(self, "_nav_direct_pins", [])
        if direct_pins:
            # "QUICK ACCESS" separator label above the pin buttons
            qa_lbl = QLabel("QUICK\nACCESS")
            qa_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            qa_lbl.setFixedSize(56, 24)
            qa_lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:7px; font-weight:bold;"
                f" letter-spacing:0.5px; background:transparent;"
            )
            insert_at = self._nav_rail_lay.count() - 2
            self._nav_rail_lay.insertWidget(insert_at, qa_lbl)

            for entry in direct_pins:
                lbl = entry.label
                # short display: first word, max 8 chars
                short = lbl.split()[0][:8]
                pin_btn = _RailButton("star", lbl)
                pin_btn._short_label = short
                pin_btn.setToolTip(lbl)
                pin_btn.clicked.connect(
                    lambda _c, label=lbl: (
                        self._nav_rail_go_to(label),
                        self._nav_flyout.close_panel() if hasattr(self, "_nav_flyout") else None,
                    )
                )
                insert_at = self._nav_rail_lay.count() - 2
                self._nav_rail_lay.insertWidget(insert_at, pin_btn)
                self._nav_rail_pin_buttons[lbl] = pin_btn

        for sec in self._nav_sections:
            btn = _RailButton(sec["icon"], sec["name"])
            btn.clicked.connect(lambda _c, s=sec["name"]: self._nav_rail_toggle(s))
            if sec["name"] == "Security Audit":
                btn.setToolTip(
                    "Security Audit\n"
                    "Items shown in red require admin rights or run\n"
                    "active probes against devices on your network."
                )
            # Insert before the stretch (index = count - 2: stretch + settings)
            insert_at = self._nav_rail_lay.count() - 2
            self._nav_rail_lay.insertWidget(insert_at, btn)
            self._nav_rail_buttons[sec["name"]] = btn

    def _nav_rail_toggle(self, section_name: str) -> None:
        """Toggle the flyout for the given section; close if already open."""
        if self._nav_open_section == section_name and self._nav_flyout.maximumWidth() > 0:
            # Clicking the active section icon collapses the flyout
            if not self._nav_flyout.is_pinned:
                self._nav_flyout.close_panel()
                self._nav_open_section = ""
                self._nav_rail_buttons[section_name].setChecked(False)
            return
        # Switch to the new section
        self._nav_open_section = section_name
        for name, btn in self._nav_rail_buttons.items():
            btn.setChecked(name == section_name)
        sec = next((s for s in self._nav_sections if s["name"] == section_name), None)
        if sec is None:
            return
        entries = [
            (e.label, e.label in self._nav_pinned_labels, e.admin_required or e.audit_item)
            for e in sec["entries"]
        ]
        self._nav_flyout.load_section(
            title=section_name,
            entries=entries,
            active_label=self._nav_current_page_label,
            on_click=self._nav_rail_go_to,
            on_pin_toggle=self._on_rail_pin_toggle,
        )
        # Re-apply any saved flyout dots after items are rebuilt
        for _lbl, _color in getattr(self, "_flyout_dots", {}).items():
            if _color:
                self._nav_flyout.apply_dot(_lbl, _color)
        self._nav_flyout.open()
        _qs = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        _qs.setValue("nav/last_section", section_name)

    def _nav_rail_go_to(self, label: str, _push_history: bool = False) -> None:
        """Navigate to a page by label in rail mode. Flyout stays open."""
        widget = self._nav_label_to_widget.get(label)
        if widget is None:
            return
        if (
            label != "Settings"
            and hasattr(self, "_settings_page")
            and self._settings_page.is_dirty()
            and not self._settings_page.confirm_leave()
        ):
            return
        if _push_history and hasattr(self, "_nav_history"):
            current = getattr(self, "_nav_current_page_label", None)
            if current and current != label:
                self._nav_history.append(current)
        elif hasattr(self, "_nav_history"):
            self._nav_history.clear()
        if hasattr(self, "_back_btn"):
            self._back_btn.setVisible(bool(self._nav_history))
        self._nav_current_page_label = label
        self._nav_crossfade_to(widget)
        self._nav_flyout.set_active(label)
        section = self._nav_page_to_section.get(label, "")
        if hasattr(self, "_breadcrumb_lbl"):
            self._breadcrumb_lbl.setText(f"{section}  ›  {label}" if section else label)
        if hasattr(self, "_help_panel"):
            self._update_help_panel(label)
        if hasattr(self, "_tray_manager"):
            self._tray_manager.reset_badge()
        # Auto-expand tips on first visit to pages with non-obvious interactions
        if label in _AUTO_HELP_PAGES and _PAGE_HELP.get(label) and hasattr(self, "_tip_bar"):
            import json as _json
            _qs2 = QSettings("NetSentinel", "NetSentinel")
            try:
                _visited2 = _json.loads(_qs2.value("discover/visited_pages", "[]"))
            except Exception:
                _visited2 = []
            if label not in _visited2:
                self._tip_bar.setChecked(True)
        self._track_page_visit(label)

    def _nav_deep_link_go_to(self, label: str) -> None:
        """Navigate via a deep link — pushes the current page onto the back stack."""
        self._nav_rail_go_to(label, _push_history=True)

    @pyqtSlot()
    def _nav_go_back(self) -> None:
        if not self._nav_history:
            return
        prev = self._nav_history.pop()
        widget = self._nav_label_to_widget.get(prev)
        if widget is None:
            return
        self._nav_current_page_label = prev
        self._nav_crossfade_to(widget)
        self._nav_flyout.set_active(prev)
        section = self._nav_page_to_section.get(prev, "")
        if hasattr(self, "_breadcrumb_lbl"):
            self._breadcrumb_lbl.setText(f"{section}  ›  {prev}" if section else prev)
        if hasattr(self, "_back_btn"):
            self._back_btn.setVisible(bool(self._nav_history))

    def keyPressEvent(self, event) -> None:
        from PyQt6.QtCore import Qt as _Qt
        if event.key() == _Qt.Key.Key_Escape and self._nav_history:
            self._nav_go_back()
            event.accept()
        else:
            super().keyPressEvent(event)

    @pyqtSlot()
    def _on_modem_tile_clicked(self) -> None:
        label = getattr(self, "_active_modem_plugin_label", "")
        if label:
            self._nav_rail_go_to(label)
        else:
            self._nav_rail_go_to("Hardware")

    @pyqtSlot(str)
    def _on_inventory_device_selected(self, mac: str) -> None:
        """Navigate to Devices and scroll/select the row matching this MAC."""
        self._nav_rail_go_to("Devices")
        self._m1_highlight_mac(mac)

    def _m1_highlight_mac(self, mac: str) -> None:
        """Scroll the Devices table to the row matching `mac` and select it."""
        if not hasattr(self, "_m1_table"):
            return
        mac_lower = mac.lower()
        for row in range(self._m1_table.rowCount()):
            item = self._m1_table.item(row, 2)  # MAC Address column
            if item and item.text().lower() == mac_lower:
                self._m1_table.selectRow(row)
                self._m1_table.scrollToItem(
                    item, self._m1_table.ScrollHint.PositionAtCenter
                )
                break

    @pyqtSlot(str)
    def _on_config_drift_detected(self, message: str) -> None:
        """Show a status-bar and tray notification when snapshot comparison finds drift."""
        self._baseline_has_drift = True
        self._refresh_section_badges()
        self._set_status(f"⚠ {message}")
        if self._tray_manager.is_available():
            self._tray_manager.show_notification(
                "Config Drift Detected", message, "WARNING"
            )

    def _update_help_panel(self, label: str) -> None:
        """Refresh tip bar text and collapse the help panel when the page changes."""
        info = _PAGE_HELP.get(label, {})
        self._tip_bar_has_content = bool(info)

        # Collapse panel silently on page change
        if hasattr(self, "_tip_bar"):
            self._tip_bar.blockSignals(True)
            self._tip_bar.setChecked(False)
            self._tip_bar.blockSignals(False)
        if hasattr(self, "_help_panel"):
            self._help_panel.setVisible(False)

        if not info:
            if hasattr(self, "_tip_bar"):
                self._tip_bar.setText("ⓘ  Keyboard Shortcuts  ▾")
            if hasattr(self, "_help_what_lbl"):
                self._help_what_lbl.setText("")
            if hasattr(self, "_help_hidden_lbl"):
                self._help_hidden_lbl.setVisible(False)
            return

        if hasattr(self, "_tip_bar"):
            self._tip_bar.setText(f"ⓘ  Tips for {label}  ▾")

        what = info.get("what", "")
        bullets = info.get("hidden", [])
        if hasattr(self, "_help_what_lbl"):
            self._help_what_lbl.setText(what)
        if hasattr(self, "_help_hidden_lbl"):
            if bullets:
                hidden_text = "\n".join(f"  •  {b}" for b in bullets)
                self._help_hidden_lbl.setText(f"Hidden interactions:\n{hidden_text}")
                self._help_hidden_lbl.setVisible(True)
            else:
                self._help_hidden_lbl.setVisible(False)

    def _toggle_help_panel(self, checked: bool) -> None:
        # Panel always opens — shortcuts are useful on every page
        if hasattr(self, "_help_panel"):
            self._help_panel.setVisible(checked)

    # ── Visited-feature tracking ───────────────────────────────────────────────

    # Ordered list of high-value pages to surface to unvisited users.
    _DISCOVERY_PAGES = [
        ("Protocol Visualizer", "See animated diagrams of ARP, DNS, TCP and more — using your real devices"),
        ("Lab Mode",            "Try a guided exercise: find a rogue device or diagnose slow DNS on your live network"),
        ("Network Grade",       "Get an A–F score for your network health across 8 dimensions"),
        ("Network Health Report", "Generate a network health report — great for ISP support tickets"),
        ("What's Wrong?",       "Pick a symptom and get a plain-English verdict with a prioritised fix list"),
        ("Feature Guide",       "See everything this app can do — including features most users never find"),
        ("Network Logger",      "Configure log sources and view the live activity log — all in one place"),
    ]

    def _track_page_visit(self, label: str) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        raw = qs.value("discover/visited_pages", "[]")
        try:
            visited: list = _json.loads(raw)
        except Exception:
            visited = []
        if label not in visited:
            visited.append(label)
            qs.setValue("discover/visited_pages", _json.dumps(visited))
            self._refresh_home_suggestions()
            # NAV-3: first-time pin hint after visiting 3 Analysis pages
            if not qs.value("nav/pin_hint_shown", False, type=bool):
                analysis_sec = next(
                    (s for s in self._nav_sections if s["name"] == "Analysis"), None
                )
                if analysis_sec:
                    analysis_labels = {e.label for e in analysis_sec["entries"]}
                    visited_analysis = [p for p in visited if p in analysis_labels]
                    if len(visited_analysis) >= 3:
                        qs.setValue("nav/pin_hint_shown", True)
                        self._set_status(
                            "Tip: right-click any page in the menu to pin it ★ for faster access"
                        )

    def _refresh_home_suggestions(self) -> None:
        if not hasattr(self, "_home_page"):
            return
        # Don't overwrite a live challenge card
        if getattr(self, "_pending_live_scenario", None) is not None:
            return
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        raw = qs.value("discover/visited_pages", "[]")
        try:
            visited: set = set(_json.loads(raw))
        except Exception:
            visited = set()
        suggestions = []
        for page_label, description in self._DISCOVERY_PAGES:
            if page_label not in visited:
                suggestions.append({
                    "text": description,
                    "action_label": "Try it →",
                    "target": page_label,
                    "priority": "low",
                })
            if len(suggestions) >= 3:
                break
        self._home_page.set_suggestions(suggestions)

    def _on_rail_pin_toggle(self, label: str, is_pinned: bool) -> None:
        """Update pinned set, persist, and rebuild nav so Pinned section appears/disappears."""
        if is_pinned:
            self._nav_pinned_labels.add(label)
        else:
            self._nav_pinned_labels.discard(label)
        self._save_pinned_labels()
        self._rebuild_nav_for_mode()

    def _on_canvas_click(self) -> None:
        """Close flyout on canvas click (only if not pinned)."""
        if hasattr(self, "_nav_flyout") and not self._nav_flyout.is_pinned:
            if self._nav_flyout.maximumWidth() > 0:
                self._nav_flyout.close_panel()
                self._nav_open_section = ""
                for btn in self._nav_rail_buttons.values():
                    btn.setChecked(False)

    def _build_pro_nav(self) -> None:
        """Full nav \u2014 activity rail + flyout. No mode switcher; this is the only nav."""
        self._nav_begin_section("Getting Started", "grid")
        self._nav_add_rail_item("Home",               self._home_page)
        self._nav_add_rail_item("Overview",            self._overview_page)
        self._nav_add_rail_item("Speed Test",          self._speed_test_page)
        self._nav_add_rail_item("DNS & Stability",     self._m5_tab)
        self._nav_add_rail_item("What's Wrong?",       self._diagnosis_page)

        self._nav_begin_section("Discover", "network")
        self._nav_add_rail_item("Devices",             self._m1_tab)
        self._nav_add_rail_item("Network Map",         self._topology_tab_widget)
        self._nav_add_rail_item("WiFi Networks",       self._m4_tab)
        self._nav_add_rail_item("WiFi Heatmap",        self._wifi_heatmap_page)
        self._nav_add_rail_item("DHCP Leases",         self._dhcp_lease_page)
        self._nav_add_rail_item("Home Automation",     self._ha_page)

        self._nav_begin_section("Monitor", "monitor")
        self._nav_add_rail_item("Network Logger",      self._logging_container)
        self._nav_add_rail_item("Live Bandwidth",      self._live_bandwidth_page)
        self._nav_add_rail_item("Active Connections",  self._connections_page)
        self._nav_add_rail_item("Availability History", self._history_page)
        self._nav_add_rail_item("Inventory Changes",   self._inventory_page)
        self._nav_add_rail_item("Bandwidth Usage",     self._bw_tab_widget)
        self._nav_add_rail_item("Service Heartbeat",   self._service_page)
        self._nav_add_rail_item("IPv6 Devices",        self._ipv6_tab_widget)

        self._nav_begin_section("Reports", "bar-chart")
        self._nav_add_rail_item("Network Grade",       self._benchmark_tab_widget)
        self._nav_add_rail_item("Network Health Report", self._reports_page)
        self._nav_add_rail_item("Network Doc",         self._network_doc_page)
        self._nav_add_rail_item("IP Calculator",       self._ip_calc_page)
        self._nav_add_rail_item("Notifications",       self._notifications_page)

        self._nav_begin_section("Analysis", "cpu")
        self._nav_add_rail_item("Broadcast Storm",     self._m3_tab)
        self._nav_add_rail_item("Rogue Bridge (STP)",  self._m2_tab)
        self._nav_add_rail_item("IoT Behaviour",       self._iot_baseline_tab_widget)
        self._nav_add_rail_item("Monitor Overview",    self._monitor_overview_page)
        self._nav_add_rail_item("802.11 Monitor",      self._wifi_monitor_page)
        self._nav_add_rail_item("ARP Spoof Watch",     self._arp_tab_widget)
        self._nav_add_rail_item("Hop-by-Hop Trace",    self._mtr_tab_widget)
        self._nav_add_rail_item("SNMP Device Info",    self._snmp_tab_widget)
        self._nav_add_rail_item("Tools & Wake-on-LAN", self._adv_tab_widget)
        self._nav_add_rail_item("Geolocation Map",     self._geo_map_page)
        self._nav_add_rail_item("Trend Forecasts",     self._trend_page)

        self._nav_begin_section("Automation", "zap")
        self._nav_add_rail_item("Automation Hooks",    self._automation_page)
        self._nav_add_rail_item("Scheduled Scans",     self._sched_tab_widget)
        self._nav_add_rail_item("Custom Triggers",     self._trigger_page)
        self._nav_add_rail_item("MQTT / Home Assistant", self._mqtt_page)
        self._nav_add_rail_item("REST API",            self._rest_api_page)
        self._nav_add_rail_item("Config Snapshots",    self._baseline_page)
        self._nav_add_rail_item("Maintenance Windows", self._maintenance_page)

        self._nav_begin_section("Security Audit", "shield")
        self._nav_add_rail_item("Security Overview",    self._security_overview_page,     audit_item=True)
        self._nav_add_rail_item("Port Scan (TCP)",      self._recon_syn_tab_widget,       admin_required=True, audit_item=True)
        self._nav_add_rail_item("Port Scan (UDP)",      self._recon_udp_tab_widget,       admin_required=True, audit_item=True)
        self._nav_add_rail_item("CVE Lookup",           self._recon_cve_tab_widget,       audit_item=True)
        self._nav_add_rail_item("Threat Intel",         self._threat_intel_page,          audit_item=True)
        self._nav_add_rail_item("TLS & Exposure",       self._cert_page,                  audit_item=True)
        self._nav_add_rail_item("Login Test",           self._recon_cred_tab_widget,      admin_required=True, audit_item=True)
        self._nav_add_rail_item("OS Detection",         self._recon_os_tab_widget,        audit_item=True)
        self._nav_add_rail_item("Device Risk Score",    self._recon_risk_tab_widget,      audit_item=True)
        self._nav_add_rail_item("CVE Tracker",          self._cve_page,                   audit_item=True)
        self._nav_add_rail_item("Exposed to Internet",  self._recon_exposure_tab_widget,  audit_item=True)
        self._nav_add_rail_item("Full Device Discovery", self._recon_discovery_tab_widget, audit_item=True)
        self._nav_add_rail_item("Windows Shares (SMB)", self._recon_smb_tab_widget,       audit_item=True)
        self._nav_add_rail_item("Recon Plugins",         self._recon_plugin_tab_widget,    audit_item=True)
        self._nav_add_rail_item("Private Endpoint Check", self._recon_pe_tab_widget,      audit_item=True)
        self._nav_add_rail_item("Cloud Metadata Probe", self._recon_cloud_tab_widget,     audit_item=True)
        self._nav_add_rail_item("DHCP Rogue Monitor",   self._dhcp_tab_widget,            audit_item=True)

        self._nav_begin_section("Education", "book-open")
        self._nav_add_rail_item("Protocol Visualizer", self._protocol_viz_page)
        self._nav_add_rail_item("Lab Mode",            self._lab_mode_page)
        self._nav_add_rail_item("Feature Guide",       self._discover_page)
        self._nav_add_rail_item("Help & Reference",    self._help_tab_widget)

        self._nav_begin_section("Extend", "plug")
        self._nav_add_rail_item("Hardware",        self._hardware_integration_page)
        for _hw_p, _pg in getattr(self, "_plugin_pages", {}).items():
            self._nav_add_rail_item(_pg._label, _pg)

    #── Favourites / pinnable pages ───────────────────────────────────────────

    def _load_pinned_labels(self) -> set:
        try:
            from PyQt6.QtCore import QSettings
            s = QSettings(str(Dashboard._settings_path()), QSettings.Format.IniFormat)
            raw = s.value("nav/pinned_labels", "")
            return set(filter(None, raw.split("|||"))) if raw else set()
        except Exception:
            return set()

    def _save_pinned_labels(self) -> None:
        try:
            from PyQt6.QtCore import QSettings
            s = QSettings(str(Dashboard._settings_path()), QSettings.Format.IniFormat)
            s.setValue("nav/pinned_labels", "|||".join(sorted(self._nav_pinned_labels)))
        except Exception:
            pass

    def _build_favourites_section(self) -> None:
        """Prepend a Favourites section when the user has pinned at least one page."""
        if not self._nav_pinned_labels:
            return
        self._nav_add_section_label("Favourites")
        for label in sorted(self._nav_pinned_labels):
            widget = self._nav_label_to_widget.get(label)
            if widget is not None:
                self._nav_ref("★", label, widget)

    def _toggle_pin_label(self, label: str) -> None:
        if label in self._nav_pinned_labels:
            self._nav_pinned_labels.discard(label)
        else:
            self._nav_pinned_labels.add(label)
        self._save_pinned_labels()
        self._rebuild_nav_for_mode()

    def _nav_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        item = self._nav.itemAt(pos)
        if item is None:
            return
        row = self._nav.row(item)
        if row in self._nav_header_rows or row in self._nav_action_rows:
            return
        label = self._nav_item_labels.get(row, "")
        if not label:
            return
        menu = QMenu()
        if label in self._nav_pinned_labels:
            act = menu.addAction("★  Remove from Favourites")
        else:
            act = menu.addAction("☆  Pin to Favourites")
        chosen = menu.exec(self._nav.viewport().mapToGlobal(pos))
        if chosen is act:
            self._toggle_pin_label(label)

    # ── Command palette ───────────────────────────────────────────────────────

    # ── Monitoring state helpers (NAV-2) ──────────────────────────────────────

    _MONITOR_PAGES: dict = {
        "ARP Spoof Watch":     "_arp_worker",
        "DHCP Rogue Monitor":  "_dhcp_worker",
        "Bandwidth Monitor":   "_bw_worker",
    }

    def _is_monitor_running(self, worker_attr: str) -> bool:
        w = getattr(self, worker_attr, None)
        return bool(w and w.isRunning())

    # ── Recent-action recording (RECUR-3) ─────────────────────────────────────

    def _record_recent_action(self, action_id: str, label: str, page: str, params: dict) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            existing: list = _json.loads(qs.value("recur/recent_actions", "[]"))
        except Exception:
            existing = []
        existing = [a for a in existing if a.get("id") != action_id]
        existing.insert(0, {"id": action_id, "label": label, "page": page, "params": params})
        qs.setValue("recur/recent_actions", _json.dumps(existing[:10]))

    def _build_palette_items(self) -> list:
        import json as _json

        # Recent actions (RECUR-3) — prepend with separator
        recent_items: list = []
        try:
            recent = _json.loads(
                QSettings("NetSentinel", "NetSentinel").value("recur/recent_actions", "[]")
            )
        except Exception:
            recent = []
        if recent:
            recent_items.append({"label": "Recent", "kind": "separator"})
            for a in recent[:5]:
                recent_items.append({
                    "icon": "⟳", "label": a["label"], "kind": "recent",
                    "id": a["id"], "page": a["page"], "params": a.get("params", {}),
                })

        # Pages (NAV-2: add monitoring state to monitor pages)
        seen: set = set()
        pages = []
        for sec in self._nav_sections:
            for entry in sec["entries"]:
                if entry.label and entry.label not in seen:
                    seen.add(entry.label)
                    worker_attr = self._MONITOR_PAGES.get(entry.label)
                    if worker_attr:
                        running = self._is_monitor_running(worker_attr)
                        state = "● Monitoring" if running else "○ Not running"
                        pages.append({
                            "icon": "◎",
                            "label": f"{entry.label}  {state}",
                            "kind": "page",
                            "real_label": entry.label,
                        })
                        if not running:
                            pages.append({
                                "icon": "▶",
                                "label": f"Start {entry.label}",
                                "kind": "action",
                            })
                    else:
                        pages.append({"icon": "◎", "label": entry.label, "kind": "page"})

        if recent_items:
            pages_section = [{"label": "Pages", "kind": "separator"}] + pages
        else:
            pages_section = pages

        actions = [
            {"icon": "⟳", "label": "Run Full Scan",    "kind": "action"},
            {"icon": "⚙", "label": "Open Settings",    "kind": "action"},
            {"icon": "◄", "label": "Toggle Sidebar",   "kind": "action"},
            {"icon": "◈", "label": "Diagnose Network", "kind": "action"},
        ]
        return recent_items + pages_section + actions

    def _open_command_palette(self) -> None:
        items = self._build_palette_items()
        pal = CommandPalette(items, parent=self)
        pal.load_recent_data(self._store)
        pal.page_requested.connect(self._nav_rail_go_to)
        pal.action_requested.connect(self._on_palette_action)
        pal.exec()

    def _open_shortcut_overlay(self) -> None:
        """Show the keyboard shortcut reference overlay (KEYBOARD-1)."""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        from ui.styles import BG_CARD, BORDER, CARD_RADIUS, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED
        dlg = QDialog(self)
        dlg.setWindowTitle("Keyboard Shortcuts")
        dlg.setMinimumWidth(420)
        dlg.setModal(True)
        dlg.setStyleSheet(
            f"QDialog {{ background:{BG_CARD}; }}"
            f"QLabel {{ color:{TEXT_PRIMARY}; background:transparent; }}"
        )
        vlay = QVBoxLayout(dlg)
        vlay.setContentsMargins(20, 16, 20, 16)
        vlay.setSpacing(8)
        hdr = QLabel("Keyboard Shortcuts")
        hdr.setStyleSheet(f"font-size:15px; font-weight:bold; color:{TEXT_PRIMARY};")
        vlay.addWidget(hdr)
        shortcuts = [
            ("?",           "Show this reference"),
            ("Ctrl+K",      "Command palette"),
            ("Ctrl+F",      "Focus nav search"),
            ("Ctrl+R",      "Run full scan"),
            ("Ctrl+,",      "Settings"),
            ("Ctrl+L",      "Log Hub"),
            ("Ctrl+Q",      "Quit"),
            ("J / K",       "Next / previous row in tables"),
            ("Escape",      "Close panel / flyout"),
        ]
        for key, desc in shortcuts:
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent;")
            row_lay = QHBoxLayout(row_w)
            row_lay.setContentsMargins(0, 2, 0, 2)
            key_lbl = QLabel(key)
            key_lbl.setFixedWidth(110)
            key_lbl.setStyleSheet(
                f"font-family:monospace; font-size:11px; font-weight:bold;"
                f" color:{ACCENT}; background:{BORDER}22;"
                f" border:1px solid {BORDER}; border-radius:3px; padding:1px 5px;"
            )
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
            row_lay.addWidget(key_lbl)
            row_lay.addSpacing(12)
            row_lay.addWidget(desc_lbl, 1)
            vlay.addWidget(row_w)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(dlg.accept)
        btns.button(QDialogButtonBox.StandardButton.Close).setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:4px; padding:4px 14px; }}"
        )
        vlay.addSpacing(4)
        vlay.addWidget(btns)
        dlg.exec()

    def _on_palette_action(self, action: str) -> None:
        if action.startswith("__device__"):
            ip_or_mac = action[len("__device__"):]
            self._nav_rail_go_to("Inventory Changes")
            if hasattr(self, "_inventory_page"):
                self._inventory_page.select_device(ip_or_mac)
        elif action.startswith("__alert__"):
            import json as _json
            try:
                alert_dict = _json.loads(action[len("__alert__"):])
                if hasattr(self, "_notifications_page"):
                    self._nav_rail_go_to("Notifications")
                    self._notifications_page._alert_drawer.open(alert_dict)
            except Exception:
                pass
        elif action.startswith("__recent__"):
            self._replay_recent_action(action[len("__recent__"):])
        elif action == "Run Full Scan":
            self._start_full_scan()
        elif action == "Open Settings":
            self._open_settings_dialog()
        elif action == "Toggle Sidebar":
            self._toggle_sidebar()
        elif action == "Diagnose Network":
            self._open_diagnosis()
        elif action == "Start ARP Spoof Watch":
            self._nav_rail_go_to("ARP Spoof Watch")
            self._start_arp_monitor()
        elif action == "Start DHCP Rogue Monitor":
            self._nav_rail_go_to("DHCP Rogue Monitor")
            self._start_dhcp_scan()
        elif action == "Start Bandwidth Monitor":
            self._nav_rail_go_to("Live Bandwidth")
            self._start_bandwidth_monitor()

    def _replay_recent_action(self, action_id: str) -> None:
        import json as _json
        qs = QSettings("NetSentinel", "NetSentinel")
        try:
            recent: list = _json.loads(qs.value("recur/recent_actions", "[]"))
        except Exception:
            return
        action = next((a for a in recent if a.get("id") == action_id), None)
        if action is None:
            return
        page = action.get("page", "")
        params = action.get("params", {})
        self._nav_rail_go_to(page)
        if page == "Port Scan (TCP)" and hasattr(self, "_syn_host"):
            self._syn_host.setText(params.get("host", ""))
        elif page == "Tools & Wake-on-LAN" and hasattr(self, "_ps_host"):
            self._ps_host.setText(params.get("host", ""))
        elif page == "Hop-by-Hop Trace" and hasattr(self, "_mtr_target"):
            self._mtr_target.setText(params.get("target", ""))

    def _on_overview_navigate(self, label: str) -> None:
        if label == "Diagnose Network":
            self._open_diagnosis()
        else:
            self._nav_rail_go_to(label)

    def _open_diagnosis(self) -> None:
        self._nav_rail_go_to("What's Wrong?")

    # ── Alert badge on Security Audit nav section ─────────────────────────────

    def _refresh_alert_badge(self) -> None:
        if not hasattr(self, "_store") or self._store is None:
            return
        # Rail mode: dot + tooltip handled by _refresh_section_badges
        self._refresh_section_badges()

    # ── Module 1 ──────────────────────────────────────────────────────────────

    def _build_kpi_bar(self) -> QWidget:
        """
        Four KPI tiles: Total Nodes | Critical Risks | Unauthorized | Scan Status.
        Sits at the top of the Devices page. Values are updated by _update_kpi_tiles().
        """
        bar = QWidget()
        bar.setFixedHeight(56)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 6)
        row.setSpacing(8)

        def _tile(dot_color: str, label: str, start_val: str, start_color: str):
            """Return (tile QFrame, dot QLabel, value QLabel)."""
            tile = QFrame()
            tile.setObjectName("card")
            tile.setStyleSheet(
                f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
                f"border-left:3px solid {dot_color};border-radius:0px;}}"
            )
            vl = QVBoxLayout(tile)
            vl.setContentsMargins(8, 4, 8, 4)
            vl.setSpacing(1)

            hdr = QHBoxLayout()
            hdr.setSpacing(4)
            dot = QLabel("●")
            dot.setStyleSheet(
                f"color:{dot_color}; font-size:9px; background:transparent; border:none;"
            )
            lbl = QLabel(label.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
                "letter-spacing:0.5px; background:transparent; border:none;"
            )
            hdr.addWidget(dot)
            hdr.addWidget(lbl)
            hdr.addStretch()
            vl.addLayout(hdr)

            val = QLabel(start_val)
            val.setStyleSheet(
                f"color:{start_color}; font-size:18px; font-weight:bold;"
                "background:transparent; border:none;"
            )
            vl.addWidget(val)
            return tile, dot, val

        t1, self._kpi_nodes_dot,  self._kpi_nodes_val  = _tile(ACCENT,          "Total Nodes",    "—", TEXT_MUTED)
        t2, self._kpi_risk_dot,   self._kpi_risk_val   = _tile(TEXT_MUTED,      "Critical Risks", "—", TEXT_MUTED)
        t3, self._kpi_unauth_dot, self._kpi_unauth_val = _tile(TEXT_MUTED,      "Unauthorized",   "—", TEXT_MUTED)
        t4, self._kpi_scan_dot,   self._kpi_scan_val   = _tile(TEXT_SECONDARY,  "Scan Status",    "Ready", TEXT_SECONDARY)

        # Keep references to the tiles themselves so we can update border colours
        self._kpi_risk_tile  = t2
        self._kpi_unauth_tile = t3

        for t in (t1, t2, t3, t4):
            row.addWidget(t, 1)
        return bar

    def _update_kpi_tiles(self, data: dict) -> None:
        """Refresh KPI tile values from a completed scan result dict."""
        devices    = data.get("devices", [])
        total      = len(devices)
        high_risk  = sum(
            1 for d in devices
            if (d.risk_level if not isinstance(d, dict) else d.get("risk_level", "")) in ("HIGH", "CRITICAL")
        )
        unauth     = data.get("high_risk_count", high_risk)

        # Nodes tile — always blue
        self._kpi_nodes_val.setText(str(total))
        self._kpi_nodes_val.setStyleSheet(
            f"color:{ACCENT}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )

        # Critical risks tile — green if 0, amber if 1-2, red if 3+
        risk_color = GREEN if high_risk == 0 else (AMBER if high_risk <= 2 else RED)
        self._kpi_risk_val.setText(str(high_risk))
        self._kpi_risk_val.setStyleSheet(
            f"color:{risk_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_risk_dot.setStyleSheet(
            f"color:{risk_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_risk_tile.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-left:3px solid {risk_color};border-radius:0px;}}"
        )

        # Unauthorized tile — green if 0, red if >0
        unauth_color = GREEN if unauth == 0 else RED
        self._kpi_unauth_val.setText(str(unauth))
        self._kpi_unauth_val.setStyleSheet(
            f"color:{unauth_color}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        self._kpi_unauth_dot.setStyleSheet(
            f"color:{unauth_color}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_unauth_tile.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-left:3px solid {unauth_color};border-radius:0px;}}"
        )

        # Scan status tile — green "Complete"
        self._kpi_scan_val.setText("Complete")
        self._kpi_scan_dot.setStyleSheet(
            f"color:{GREEN}; font-size:9px; background:transparent; border:none;"
        )
        self._kpi_scan_val.setStyleSheet(
            f"color:{GREEN}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )

    def _build_m1_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── KPI summary tiles ─────────────────────────────────────────────────
        lay.addWidget(self._build_kpi_bar())

        self._m1_status = QLabel("Not yet scanned.")
        self._m1_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")

        self._m1_group_btn = QPushButton("▼▼  Collapse All")
        self._m1_group_btn.setFixedHeight(22)
        self._m1_group_btn.setStyleSheet(
            f"QPushButton{{background:{BG_DARK};color:{TEXT_MUTED};border:1px solid {BORDER};"
            f"border-radius:3px;padding:0 8px;font-size:10px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{TEXT_PRIMARY};}}"
        )
        self._m1_group_btn.setVisible(False)
        self._m1_group_btn.clicked.connect(self._m1_toggle_all_groups)

        _node_grp_on = QSettings("NetSentinel", "NetSentinel").value(
            "devices/group_by_node", False, type=bool
        )
        self._m1_group_by_node: bool = _node_grp_on

        # Segmented view control — always enabled, no plugin gate
        self._m1_seg_active_ss = (
            f"QPushButton{{background:{ACCENT_DARK};color:#fff;border:none;"
            f"border-radius:3px;padding:0 10px;font-size:10px;}}"
            f"QPushButton:hover{{background:{ACCENT};}}"
        )
        self._m1_seg_inactive_ss = (
            f"QPushButton{{background:transparent;color:{TEXT_MUTED};border:none;"
            f"border-radius:3px;padding:0 10px;font-size:10px;}}"
            f"QPushButton:hover{{background:{BG_HOVER};color:{TEXT_PRIMARY};}}"
        )
        _seg_frame = QFrame()
        _seg_frame.setFixedHeight(24)
        _seg_frame.setStyleSheet(
            f"QFrame{{background:{BG_DARK};border:1px solid {BORDER};border-radius:4px;}}"
        )
        _seg_lay = QHBoxLayout(_seg_frame)
        _seg_lay.setContentsMargins(1, 1, 1, 1)
        _seg_lay.setSpacing(0)

        self._m1_seg_list = QPushButton("≡  List")
        self._m1_seg_list.setFixedHeight(22)
        self._m1_seg_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self._m1_seg_list.setToolTip("Flat device list")
        self._m1_seg_list.setStyleSheet(
            self._m1_seg_inactive_ss if _node_grp_on else self._m1_seg_active_ss
        )
        self._m1_seg_node = QPushButton("⊞  By Node")
        self._m1_seg_node.setFixedHeight(22)
        self._m1_seg_node.setCursor(Qt.CursorShape.PointingHandCursor)
        self._m1_seg_node.setToolTip("Group devices by mesh node / AP")
        self._m1_seg_node.setStyleSheet(
            self._m1_seg_active_ss if _node_grp_on else self._m1_seg_inactive_ss
        )
        _seg_lay.addWidget(self._m1_seg_list)
        _seg_lay.addWidget(self._m1_seg_node)

        self._m1_seg_list.clicked.connect(lambda: self._on_node_group_toggled(False))
        self._m1_seg_node.clicked.connect(lambda: self._on_node_group_toggled(True))

        _status_row = QHBoxLayout()
        _status_row.setContentsMargins(0, 0, 0, 0)
        _status_row.addWidget(self._m1_status, 1)
        _status_row.addWidget(_seg_frame)
        _status_row.addSpacing(4)
        _status_row.addWidget(self._m1_group_btn)

        # Integration discovery banner — hidden until scan finds a device matching
        # a bundled plugin's default gateway IP
        from PyQt6.QtWidgets import QLabel as _QL, QPushButton as _QPB
        self._m1_int_banner = QFrame()
        self._m1_int_banner.setVisible(False)
        _ib_lay = QHBoxLayout(self._m1_int_banner)
        _ib_lay.setContentsMargins(10, 5, 10, 5)
        _ib_lay.setSpacing(8)
        self._m1_int_banner.setStyleSheet(
            f"QFrame {{ background:{ACCENT}18; border:1px solid {ACCENT}55;"
            " border-radius:4px; }}"
        )
        self._m1_int_lbl = QLabel()
        self._m1_int_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent; border:none;"
        )
        _ib_lay.addWidget(self._m1_int_lbl, 1)
        _int_cfg_btn = QPushButton("Configure  →")
        _int_cfg_btn.setFixedHeight(22)
        _int_cfg_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _int_cfg_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            " border-radius:3px; font-size:10px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:#005A9E; }}"
        )
        _int_cfg_btn.clicked.connect(
            lambda: self._nav_rail_go_to("Hardware")
        )
        _ib_lay.addWidget(_int_cfg_btn)

        self._m1_node_hint = QLabel()   # hidden stub — hint lives in By Node group header
        self._m1_node_hint.setVisible(False)

        self._m1_table = _table([
            "IP Address", "Hostname", "MAC Address", "Vendor", "Risk", "Device Type",
            "Node", "Band", "Verdict",
        ])
        self._m1_table.setColumnWidth(0, 120)
        self._m1_table.setColumnWidth(1, 160)
        self._m1_table.setColumnWidth(2, 145)
        self._m1_table.setColumnWidth(3, 180)
        self._m1_table.setColumnWidth(4, 70)
        self._m1_table.setColumnWidth(5, 130)
        self._m1_table.setColumnWidth(6, 155)
        self._m1_table.setColumnWidth(7, 55)
        # Node (6) and Band (7) are hidden until a Deco scan populates them
        self._m1_table.setColumnHidden(6, True)
        self._m1_table.setColumnHidden(7, True)
        self._m1_table.setStyleSheet(
            f"QTableWidget::item:hover {{ background-color: {BG_HOVER}; }}"
        )

        # Column sorting (click header to sort ascending/descending)
        self._m1_table.setSortingEnabled(True)
        self._m1_table.horizontalHeader().setSortIndicatorShown(True)
        self._m1_table.horizontalHeader().sortIndicatorChanged.connect(
            self._m1_sort_changed
        )

        # Right-click context menu
        self._m1_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m1_table.customContextMenuRequested.connect(self._m1_context_menu)

        # Double-click → pre-fill Port Scan (TCP) and navigate there
        self._m1_table.doubleClicked.connect(self._m1_row_double_clicked)

        # Empty-state placeholder shown when table has no rows
        self._m1_empty = QLabel("Run a scan to discover devices on this network.")
        self._m1_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._m1_empty.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:13px; padding:40px;"
            "background:transparent; border:none;"
        )

        # ── Card wrapping table + empty state ─────────────────────────────────
        m1_card, m1_body = _make_card("Discovered Devices")

        # Search bar + filter chips (FILTER-1)
        _frow_w = QWidget()
        _frow_w.setStyleSheet("background:transparent;")
        _frow = QHBoxLayout(_frow_w)
        _frow.setContentsMargins(8, 5, 8, 4)
        _frow.setSpacing(6)

        self._m1_search = QLineEdit()
        self._m1_search.setPlaceholderText("Search IP, hostname, MAC, vendor…")
        self._m1_search.setFixedHeight(26)
        self._m1_search.setClearButtonEnabled(True)
        self._m1_search.setStyleSheet(
            f"QLineEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 6px; font-size:11px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._m1_search.textChanged.connect(self._m1_apply_filter)
        _frow.addWidget(self._m1_search, 1)

        self._m1_chip_active_ss = (
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f" border-radius:3px; padding:0 8px; font-size:10px; }}"
        )
        self._m1_chip_inactive_ss = (
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:0 8px; font-size:10px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; border-color:{TEXT_MUTED}; }}"
        )
        self._m1_chip = "all"
        self._m1_chip_btns: dict = {}
        for _ckey, _clabel in (
            ("all", "All"), ("online", "Online"),
            ("offline", "Offline"), ("unknown", "Unknown vendor"),
        ):
            _cbtn = QPushButton(_clabel)
            _cbtn.setFixedHeight(22)
            _cbtn.setCursor(Qt.CursorShape.PointingHandCursor)
            _cbtn.setStyleSheet(
                self._m1_chip_active_ss if _ckey == "all" else self._m1_chip_inactive_ss
            )
            _cbtn.clicked.connect(lambda _=False, k=_ckey: self._m1_set_chip(k))
            self._m1_chip_btns[_ckey] = _cbtn
            _frow.addWidget(_cbtn)

        m1_body.addWidget(_frow_w)

        # Stack: table on top, empty label behind — we toggle visibility
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._m1_stack = _SW()
        self._m1_stack.addWidget(self._m1_empty)   # index 0 — empty state
        self._m1_stack.addWidget(self._m1_table)   # index 1 — live data
        self._m1_stack.setCurrentIndex(0)
        m1_body.addWidget(self._m1_stack)

        lay.addLayout(_status_row)
        lay.addWidget(self._m1_int_banner)
        lay.addWidget(m1_card, 1)

        from ui.widgets.explainer_panel import ExplainerPanel
        self._m1_explainer = ExplainerPanel("rogue_device")
        self._m1_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m1_explainer)
        return w

    @pyqtSlot('QModelIndex')
    def _m1_row_double_clicked(self, index) -> None:
        """Double-click a device row → pre-fill SYN scanner IP and navigate."""
        ip_item = self._m1_table.item(index.row(), 0)
        if ip_item:
            ip = ip_item.text().strip()
            if ip and hasattr(self, "_syn_host"):
                self._syn_host.setText(ip)
                self._nav_rail_go_to("Port Scan (TCP)")

    def _m1_set_chip(self, key: str) -> None:
        self._m1_chip = key
        for k, btn in self._m1_chip_btns.items():
            btn.setStyleSheet(
                self._m1_chip_active_ss if k == key else self._m1_chip_inactive_ss
            )
        self._m1_apply_filter()

    def _m1_apply_filter(self) -> None:
        text = self._m1_search.text().lower().strip()
        chip = self._m1_chip
        for row in range(self._m1_table.rowCount()):
            text_match = not text or any(
                text in (self._m1_table.item(row, col) or QTableWidgetItem()).text().lower()
                for col in (0, 1, 2, 3)
            )
            risk_item = self._m1_table.item(row, 4)
            risk = (risk_item.text() if risk_item else "").upper()
            vendor_item = self._m1_table.item(row, 3)
            vendor = (vendor_item.text() if vendor_item else "").lower().strip()
            if chip == "all":
                chip_match = True
            elif chip == "online":
                chip_match = risk != "UNKNOWN"
            elif chip == "offline":
                chip_match = risk == "UNKNOWN"
            else:
                chip_match = vendor in ("unknown", "—", "")
            self._m1_table.setRowHidden(row, not (text_match and chip_match))

    def _m1_sort_changed(self, col: int, order) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("home/m1_sort_col", col)
        qs.setValue("home/m1_sort_order", int(order))

    def _m1_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m1_table.rowAtIndex(pos) if hasattr(self._m1_table, 'rowAtIndex') \
              else self._m1_table.rowAt(pos.y())
        if row < 0:
            return
        first = self._m1_table.item(row, 0)
        if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
            return
        ip  = (first or QTableWidgetItem()).text()
        mac = (self._m1_table.item(row, 2) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_scan     = menu.addAction(f"🔍  Port Scan  {ip}")
        act_geo      = menu.addAction(f"🗺  Show on Geo Map →")
        act_abuseipdb = menu.addAction(f"🛡  Check IP (AbuseIPDB) →")
        act_wol      = menu.addAction(f"⚡  Wake-on-LAN  →  {mac}")
        # Show CVE Tracker link only when this IP has tracked CVE entries
        _has_cves = False
        try:
            if self._store:
                _has_cves = any(c.get("host") == ip for c in self._store.list_cve_lifecycles())
        except Exception:
            pass
        act_cve = menu.addAction(f"🔎  View in CVE Tracker →") if _has_cves else None
        menu.addSeparator()
        act_fix      = menu.addAction("🔧  How to Fix")
        menu.addSeparator()
        act_copy_ip  = menu.addAction("📋  Copy IP")
        act_copy_mac = menu.addAction("📋  Copy MAC")
        act_copy_row = menu.addAction("📋  Copy full row")
        chosen = menu.exec(self._m1_table.viewport().mapToGlobal(pos))
        if chosen == act_scan:
            self._run_port_scan(ip)
        elif chosen == act_geo:
            self._show_ip_on_geo_map(ip)
        elif chosen == act_abuseipdb:
            self._threat_intel_page.check_ip(ip)
            self._nav_rail_go_to("Threat Intelligence")
        elif act_cve and chosen == act_cve:
            self._nav_rail_go_to("CVE Tracker")
        elif chosen == act_wol:
            self._send_wol(mac)
        elif chosen == act_fix:
            # find remediation from stored result
            rem = ""
            if self._m1_result:
                for d in self._m1_result.get("devices", []):
                    d_ip = d.get("ip", "") if isinstance(d, dict) else getattr(d, "ip", "")
                    if d_ip == ip:
                        rem = d.get("remediation", "") if isinstance(d, dict) else getattr(d, "remediation", "")
                        break
            self._show_how_to_fix(ip, rem or "No specific remediation available for this device.")
        elif chosen == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(ip)
        elif chosen == act_copy_mac:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(mac)
        elif chosen == act_copy_row:
            from PyQt6.QtWidgets import QApplication
            parts = []
            for col in range(self._m1_table.columnCount()):
                item = self._m1_table.item(row, col)
                parts.append(item.text() if item else "")
            QApplication.clipboard().setText("\t".join(parts))

    def _net_devices_context_menu(self, pos) -> None:
        """Context menu for the Network Info tab's device table."""
        from PyQt6.QtWidgets import QMenu
        row = self._net_devices_table.rowAt(pos.y())
        if row < 0:
            return
        ip  = (self._net_devices_table.item(row, 0) or QTableWidgetItem()).text()
        mac = (self._net_devices_table.item(row, 2) or QTableWidgetItem()).text()
        if not ip:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_scan  = menu.addAction(f"🔍  Port Scan  {ip}")
        act_geo   = menu.addAction(f"🗺  Show on Geo Map →")
        act_abuse = menu.addAction(f"🛡  Check IP (AbuseIPDB) →")
        menu.addSeparator()
        act_copy_ip  = menu.addAction("📋  Copy IP")
        act_copy_mac = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._net_devices_table.viewport().mapToGlobal(pos))
        if chosen == act_scan:
            self._run_port_scan(ip)
        elif chosen == act_geo:
            self._show_ip_on_geo_map(ip)
        elif chosen == act_abuse:
            self._threat_intel_page.check_ip(ip)
            self._nav_rail_go_to("Threat Intelligence")
        elif chosen == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(ip)
        elif chosen == act_copy_mac:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(mac)

    # ── Module 2 ──────────────────────────────────────────────────────────────

    def _build_m2_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addWidget(NpcapMissingBanner(parent=empty))
        evl.addStretch()
        em_desc = QLabel(
            "STP/BPDU frame capture identifies unauthorised Spanning Tree root bridges\n"
            "that cause intermittent network drops and DNS failures."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start STP Capture")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(200)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "Rogue Bridge Detection",
            "STP/BPDU frame capture — identifies unauthorised Spanning Tree root bridges"
        ))
        self._m2_status = QLabel("Not yet scanned.")
        self._m2_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m2_status)
        card, card_body = _make_card("STP Frames Detected")
        self._m2_table = _table([
            "Source MAC", "BPDU Type", "Root MAC", "Bridge Priority",
            "Hello (s)", "MaxAge (s)", "FwdDelay (s)", "Rogue?"
        ])
        self._m2_table.setColumnWidth(0, 150)
        self._m2_table.setColumnWidth(1, 80)
        self._m2_table.setColumnWidth(2, 150)
        self._m2_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m2_table.customContextMenuRequested.connect(self._m2_context_menu)
        card_body.addWidget(self._m2_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m2_explainer = ExplainerPanel("stp_rogue")
        self._m2_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m2_explainer)

        self._m2_stack = QStackedWidget()
        self._m2_stack.addWidget(empty)
        self._m2_stack.addWidget(content)
        return self._m2_stack

    def _m2_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m2_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m2_table.item(row, 0) or QTableWidgetItem()).text()
        is_rogue = (self._m2_table.item(row, 7) or QTableWidgetItem()).text().strip().upper() in ("YES", "TRUE", "ROGUE")
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_fix  = menu.addAction("🔧  How to Fix")
        menu.addSeparator()
        act_copy = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._m2_table.viewport().mapToGlobal(pos))
        if chosen == act_fix:
            if is_rogue:
                rem = (
                    f"A rogue STP Root Bridge was detected from {src_mac}. "
                    "Disconnect the Ethernet cable from this device immediately. "
                    "If it is a mesh satellite (e.g. Google Nest, TP-Link Deco), it must use "
                    "Wi-Fi backhaul only — do not connect it via Ethernet. "
                    "After disconnecting, wait 60 seconds for the real router to reclaim the Root Bridge role, "
                    "then re-run this scan to confirm the network is stable."
                )
            else:
                rem = (
                    f"Device {src_mac} is sending STP BPDUs but is not currently rated as rogue. "
                    "This is expected for your main router or managed switch. "
                    "If you see repeated outages, verify this MAC belongs to your router."
                )
            self._show_how_to_fix(src_mac, rem)
        elif chosen == act_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(src_mac)

    # ── Module 3 ──────────────────────────────────────────────────────────────

    def _build_m3_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addWidget(NpcapMissingBanner(parent=empty))
        evl.addStretch()
        em_desc = QLabel(
            "Live packet capture measures broadcast and multicast rates\n"
            "and identifies the device causing a broadcast storm."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start Broadcast Capture")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(220)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "Broadcast Storm Analysis",
            "Live packet capture — measures broadcast/multicast rates and storm level"
        ))
        self._m3_status = QLabel("Not yet scanned.")
        self._m3_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m3_status)
        stats = QHBoxLayout()
        self._m3_bcast_lbl = self._stat_label("Broadcast/s", "—")
        self._m3_mcast_lbl = self._stat_label("Multicast/s", "—")
        self._m3_ratio_lbl = self._stat_label("Bcast ratio", "—")
        self._m3_level_lbl = self._stat_label("Storm level", "—")
        for w2 in (self._m3_bcast_lbl, self._m3_mcast_lbl,
                   self._m3_ratio_lbl, self._m3_level_lbl):
            stats.addWidget(w2)
        stats.addStretch()
        lay.addLayout(stats)
        card, card_body = _make_card("Broadcast Sources")
        self._m3_table = _table(["Source MAC", "Broadcast Packets", "Rogue Match?"])
        self._m3_table.setColumnWidth(0, 160)
        self._m3_table.setColumnWidth(1, 160)
        self._m3_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._m3_table.customContextMenuRequested.connect(self._m3_context_menu)
        card_body.addWidget(self._m3_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m3_explainer = ExplainerPanel("broadcast_storm")
        self._m3_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m3_explainer)

        self._m3_stack = QStackedWidget()
        self._m3_stack.addWidget(empty)
        self._m3_stack.addWidget(content)
        return self._m3_stack

    def _m3_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        row = self._m3_table.rowAt(pos.y())
        if row < 0:
            return
        src_mac = (self._m3_table.item(row, 0) or QTableWidgetItem()).text()
        bcast   = (self._m3_table.item(row, 1) or QTableWidgetItem()).text()
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_fix  = menu.addAction("🔧  How to Fix")
        act_copy = menu.addAction("📋  Copy MAC")
        chosen = menu.exec(self._m3_table.viewport().mapToGlobal(pos))
        if chosen == act_fix:
            rem = (
                f"Device {src_mac} sent {bcast} broadcast packets. "
                "To resolve a broadcast storm: "
                "1. Identify the physical device using the MAC address "
                "(check your router's DHCP table). "
                "2. Restart or reboot that device. "
                "3. Check for firmware updates — faulty firmware is a common cause. "
                "4. If the storm continues, disconnect the device from the network "
                "and move it to a separate VLAN or guest network. "
                "5. High broadcast rates from IoT devices (cameras, smart plugs) often indicate "
                "a failing device that needs replacement."
            )
            self._show_how_to_fix(src_mac, rem)
        elif chosen == act_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(src_mac)

    # ── Module 4 ──────────────────────────────────────────────────────────────

    def _build_m4_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "No WiFi scan has been run yet.\n"
            "NetSentinel will enumerate nearby networks, detect rogue SSIDs,\n"
            "and flag co-channel interference."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Scan for WiFi Networks")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(220)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "WiFi Networks",
            "Wireless scan — SSID enumeration, rogue AP detection, co-channel interference"
        ))
        self._m4_status = QLabel("Not yet scanned.")
        self._m4_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m4_status)

        # Deco band-usage KPI chips — hidden until mesh data arrives
        self._m4_deco_bar = self._build_m4_deco_bar()
        self._m4_deco_bar.setVisible(False)
        lay.addWidget(self._m4_deco_bar)

        card, card_body = _make_card("Detected Networks")
        self._m4_table = _table([
            "SSID", "BSSID", "Nodes", "Channel", "Band", "Signal (dBm)",
            "Rogue SSID?", "Co-Channel?", "Connected?",
        ])
        self._m4_table.setColumnWidth(0, 180)
        self._m4_table.setColumnWidth(1, 150)
        self._m4_table.setColumnWidth(2, 55)   # Nodes
        self._m4_table.setColumnWidth(5, 105)  # Signal range
        self._m4_table.setColumnWidth(8, 95)   # Connected
        card_body.addWidget(self._m4_table)
        lay.addWidget(card, 1)

        self._m4_stack = QStackedWidget()
        self._m4_stack.addWidget(empty)
        self._m4_stack.addWidget(content)
        return self._m4_stack

    def _build_m4_deco_bar(self) -> QWidget:
        """KPI chips showing Deco band usage — revealed when mesh data is present."""
        bar = QWidget()
        bar.setFixedHeight(62)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 2, 0, 4)
        row.setSpacing(8)

        def _chip(dot_color: str, label: str):
            tile = QFrame()
            tile.setObjectName("card")
            tile.setStyleSheet(
                f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
                f"border-left:3px solid {dot_color};border-radius:0px;}}"
            )
            vl = QVBoxLayout(tile)
            vl.setContentsMargins(8, 4, 8, 4)
            vl.setSpacing(1)
            hdr = QHBoxLayout()
            hdr.setSpacing(4)
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{dot_color};font-size:9px;background:transparent;border:none;")
            lbl = QLabel(label.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED};font-size:9px;font-weight:bold;"
                "letter-spacing:0.5px;background:transparent;border:none;"
            )
            hdr.addWidget(dot); hdr.addWidget(lbl); hdr.addStretch()
            vl.addLayout(hdr)
            val = QLabel("—")
            val.setStyleSheet(f"color:{TEXT_MUTED};font-size:18px;font-weight:bold;"
                              "background:transparent;border:none;")
            vl.addWidget(val)
            return tile, val

        header = QLabel("Deco band usage")
        header.setStyleSheet(f"color:{TEXT_MUTED};font-size:10px;padding:0;background:transparent;")
        row.addWidget(header)

        t1, self._m4_chip_24   = _chip(GREEN,        "2.4 GHz clients")
        t2, self._m4_chip_5    = _chip(ACCENT,        "5 GHz clients")
        t3, self._m4_chip_6    = _chip(CHART_PURPLE,  "6 GHz clients")
        t4, self._m4_chip_wired = _chip(TEXT_SECONDARY, "Wired clients")
        for t in (t1, t2, t3, t4):
            row.addWidget(t, 1)
        row.addStretch()
        return bar

    def _update_m4_deco_chips(self) -> None:
        """Refresh Deco band-usage chips from current mesh enrichment data."""
        if not getattr(self, "_mesh_enrichment", None):
            return
        counts: dict = {"2.4G": 0, "5G": 0, "6G": 0, "Wired": 0}
        for mc in self._mesh_enrichment.values():
            band = getattr(mc, "band", "")
            if band in counts:
                counts[band] += 1
        self._m4_chip_24.setText(str(counts["2.4G"]))
        self._m4_chip_5.setText(str(counts["5G"]))
        self._m4_chip_6.setText(str(counts["6G"]))
        self._m4_chip_wired.setText(str(counts["Wired"]))
        self._m4_deco_bar.setVisible(True)

    # ── Module 5 ──────────────────────────────────────────────────────────────

    def _build_m5_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()
        em_desc = QLabel(
            "Continuous RTT and DNS monitoring hasn't started yet.\n"
            "Run a scan to begin measuring latency and detecting outages."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        em_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        em_btn = QPushButton("Start Monitoring")
        em_btn.setObjectName("btnScan")
        em_btn.setFixedWidth(180)
        em_btn.clicked.connect(self._start_full_scan)
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(12)
        evl.addWidget(em_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addStretch()

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(_page_header(
            "DNS & Outage Monitor",
            "Continuous RTT/DNS monitoring — latency graph, outage detection, STP correlation"
        ))
        self._m5_status = QLabel("Not yet scanned.")
        self._m5_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0;")
        lay.addWidget(self._m5_status)
        self._graph = LiveGraphWidget()
        self._graph.setMinimumHeight(80)
        lay.addWidget(self._graph, 2)
        card, card_body = _make_card("Detected Outages")
        self._m5_outage_table = _table([
            "Target", "Duration (s)", "Consecutive Drops", "STP Signature?", "Severity"
        ])
        card_body.addWidget(self._m5_outage_table)
        lay.addWidget(card, 1)
        from ui.widgets.explainer_panel import ExplainerPanel
        self._m5_explainer = ExplainerPanel("dns_stability")
        self._m5_explainer.navigate_to.connect(self._nav_rail_go_to)
        lay.addWidget(self._m5_explainer)

        self._m5_stack = QStackedWidget()
        self._m5_stack.addWidget(empty)
        self._m5_stack.addWidget(content)
        return self._m5_stack

    # ── Network Info tab ──────────────────────────────────────────────────────

    def _build_network_info_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Header row
        hdr = QHBoxLayout()
        hdr_lbl = QLabel("🌐  Network Configuration")
        hdr_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        hdr_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        hdr.addWidget(hdr_lbl)
        hdr.addStretch()
        self._btn_net_refresh = QPushButton("↺  Refresh")
        self._btn_net_refresh.setObjectName("btnNetRefresh")
        self._btn_net_refresh.clicked.connect(self._refresh_network_info)
        hdr.addWidget(self._btn_net_refresh)
        lay.addLayout(hdr)

        # Info card
        self._net_info_card = QFrame()
        self._net_info_card.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        self._net_card_layout = QVBoxLayout(self._net_info_card)
        self._net_card_layout.setContentsMargins(18, 14, 18, 14)
        self._net_card_layout.setSpacing(8)

        self._net_info_label = QLabel("Loading network information…")
        self._net_info_label.setWordWrap(True)
        self._net_info_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        self._net_card_layout.addWidget(self._net_info_label)

        lay.addWidget(self._net_info_card)

        # Router links card
        router_frame = QFrame()
        router_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        rl = QVBoxLayout(router_frame)
        rl.setContentsMargins(18, 14, 18, 14)
        rl.setSpacing(6)
        rl_title = QLabel("🔗  Router / Modem Admin Panel")
        rl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        rl_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        rl.addWidget(rl_title)
        rl_desc = QLabel(
            "Click a link below to open your router's admin page in a browser.\n"
            "Most home routers use http://192.168.x.1 — Huawei 5G modems also "
            "have /html/index.html"
        )
        rl_desc.setWordWrap(True)
        rl_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        rl.addWidget(rl_desc)

        self._router_links_layout = QHBoxLayout()
        self._router_links_layout.setSpacing(10)
        rl.addLayout(self._router_links_layout)
        lay.addWidget(router_frame)

        # ── OS network settings shortcuts ─────────────────────────────────────
        os_frame = QFrame()
        os_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        os_l = QVBoxLayout(os_frame)
        os_l.setContentsMargins(18, 12, 18, 12)
        os_l.setSpacing(6)
        os_title = QLabel("⚙️  Network Settings Shortcuts")
        os_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        os_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        os_l.addWidget(os_title)
        os_btn_row = QHBoxLayout()
        os_btn_row.setSpacing(8)
        self._os_setting_btns: list = []
        import platform as _plat
        _sys = _plat.system()
        if _sys == "Windows":
            _shortcuts = [
                ("📶  Wi-Fi Settings",       "ms-settings:network-wifi"),
                ("🔌  Ethernet Settings",    "ms-settings:network-ethernet"),
                ("🌐  Network Status",       "ms-settings:network-status"),
                ("🔒  VPN Settings",         "ms-settings:network-vpn"),
                ("🛡  Firewall & Security",  "ms-settings:windowsdefender"),
            ]
        elif _sys == "Darwin":
            _shortcuts = [
                ("📶  Network Preferences",  "x-apple.systempreferences:com.apple.preference.network"),
                ("📋  Wireless Diagnostics", "open://"),  # fallback — handled below
            ]
        else:
            _shortcuts = []
        for label, uri in _shortcuts:
            btn = QPushButton(label)
            btn.setObjectName("btnNetRefresh")
            btn.setFixedHeight(30)
            btn.setToolTip(f"Open {uri}")
            if uri.startswith("ms-settings:"):
                btn.clicked.connect(lambda _c=False, u=uri: __import__('os').startfile(u))
            elif uri.startswith("x-apple"):
                btn.clicked.connect(
                    lambda _c=False, u=uri: __import__('subprocess').run(
                        ["open", u], capture_output=True
                    )
                )
            os_btn_row.addWidget(btn)
        os_btn_row.addStretch()
        os_l.addLayout(os_btn_row)
        lay.addWidget(os_frame)

        # ── DHCP lease card ───────────────────────────────────────────────────
        dhcp_frame = QFrame()
        dhcp_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        dhcp_l = QVBoxLayout(dhcp_frame)
        dhcp_l.setContentsMargins(18, 12, 18, 12)
        dhcp_l.setSpacing(4)
        dhcp_title = QLabel("🕐  DHCP Lease  &  Adapter Details")
        dhcp_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        dhcp_title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        dhcp_l.addWidget(dhcp_title)
        self._dhcp_label = QLabel("Loading…")
        self._dhcp_label.setWordWrap(True)
        self._dhcp_label.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        dhcp_l.addWidget(self._dhcp_label)
        lay.addWidget(dhcp_frame)

        # ── Adapters table ────────────────────────────────────────────────────
        adp_lbl = QLabel("  Network Adapters")
        adp_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(adp_lbl)
        self._adapters_table = _table([
            "Adapter Name", "Type", "IPv4", "MAC Address", "Speed", "WiFi Signal", "SSID", "Status"
        ])
        self._adapters_table.setColumnWidth(0, 180)
        self._adapters_table.setColumnWidth(1, 70)
        self._adapters_table.setColumnWidth(2, 115)
        self._adapters_table.setColumnWidth(3, 140)
        self._adapters_table.setColumnWidth(4, 80)
        self._adapters_table.setColumnWidth(5, 90)
        self._adapters_table.setColumnWidth(6, 140)
        self._adapters_table.setMaximumHeight(130)
        lay.addWidget(self._adapters_table)

        # ── All-devices table (populated after scan) ──────────────────────────
        dev_lbl = QLabel("  All Devices Seen on This Network  (populated after scan)")
        dev_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(dev_lbl)

        self._net_devices_table = _table([
            "IP Address", "Hostname", "MAC Address", "Vendor", "Risk"
        ])
        self._net_devices_table.setColumnWidth(0, 120)
        self._net_devices_table.setColumnWidth(1, 180)
        self._net_devices_table.setColumnWidth(2, 145)
        self._net_devices_table.setColumnWidth(3, 200)
        self._net_devices_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._net_devices_table.customContextMenuRequested.connect(self._net_devices_context_menu)
        lay.addWidget(self._net_devices_table, 1)
        return w

    def _update_net_info_ui(self, info: dict):
        """Populate the Network Info tab from a get_network_info() dict."""
        self._net_info = info
        self._protocol_viz_page.set_context(
            net_info=self._net_info,
            devices=self._m1_result.get("devices", []) if self._m1_result else [],
            diag_result=self._diag_result,
            m2_result=self._m2_result,
        )
        self._diagnosis_page.set_network_info(
            info.get("gateway"),
            info.get("gateway_mac"),
        )

        lines = []
        for entry in info.get("local_ips", []):
            mask = f" / {entry['mask']}" if entry.get("mask") else ""
            lines.append(
                f"<b>Local IP:</b>  {entry['ip']}{mask}"
                f"  <span style='color:{TEXT_SECONDARY}'>(adapter: {entry['adapter']})</span>"
            )
        gw = info.get("gateway")
        if gw:
            lines.append(f"<b>Default Gateway:</b>  {gw}")
        dns = info.get("dns_servers", [])
        if dns:
            lines.append(f"<b>DNS Servers:</b>  {',  '.join(dns)}")
        domain = info.get("domain", "")
        if domain:
            lines.append(f"<b>Domain:</b>  {domain}")

        self._net_info_label.setTextFormat(Qt.TextFormat.RichText)
        self._net_info_label.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px; line-height:1.8;")
        self._net_info_label.setText("<br>".join(lines) if lines else "No network information available.")

        # Show a basic header status once the network is confirmed reachable
        if not self._verdict_badge.isVisible():
            if info.get("gateway") and info.get("local_ips"):
                self._verdict_badge.setText("● Network healthy")
                self._verdict_badge.setStyleSheet(
                    f"color:{GREEN}; font-size:11px; font-weight:600;"
                    " background:transparent; border:none; padding:0 12px;"
                )
                self._verdict_badge.setVisible(True)

        # Rebuild router links
        while self._router_links_layout.count():
            item = self._router_links_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if gw:
            for label, url in [
                (f"http://{gw}/",                    f"http://{gw}/"),
                (f"http://{gw}/html/index.html",     f"http://{gw}/html/index.html"),
                (f"https://{gw}/",                   f"https://{gw}/"),
            ]:
                btn = QPushButton(label)
                btn.setObjectName("btnRouterLink")
                btn.setToolTip(f"Open {url} in your browser")
                btn.clicked.connect(lambda _checked, u=url: webbrowser.open(u))
                self._router_links_layout.addWidget(btn)
        self._router_links_layout.addStretch()

        # ── Populate DHCP lease ──────────────────────────────────────────────
        dhcp = info.get("dhcp", {})
        dhcp_parts = []
        if dhcp.get("dhcp_enabled"):
            if dhcp.get("dhcp_server"):
                dhcp_parts.append(f"<b>DHCP Server:</b>  {dhcp['dhcp_server']}")
            if dhcp.get("lease_obtained"):
                dhcp_parts.append(f"<b>Lease Obtained:</b>  {dhcp['lease_obtained']}")
            if dhcp.get("lease_expires"):
                dhcp_parts.append(f"<b>Lease Expires:</b>  {dhcp['lease_expires']}")
            if dhcp.get("lease_duration_h"):
                dhcp_parts.append(
                    f"<b>Lease Duration:</b>  {dhcp['lease_duration_h']:.0f} h"
                )
        elif dhcp.get("dhcp_enabled") is False:
            dhcp_parts.append("DHCP is disabled on this adapter (static IP)")
        else:
            dhcp_parts.append("DHCP lease information not available.")
        self._dhcp_label.setTextFormat(Qt.TextFormat.RichText)
        self._dhcp_label.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; line-height:1.8;")
        self._dhcp_label.setText("  " + "&nbsp;&nbsp;&nbsp;│&nbsp;&nbsp;&nbsp;".join(dhcp_parts))

        # ── Populate adapters table ──────────────────────────────────────────
        from PyQt6.QtGui import QColor
        self._adapters_table.setRowCount(0)
        for a in info.get("adapters", []):
            row = self._adapters_table.rowCount()
            self._adapters_table.insertRow(row)
            connected = a.get("connected", False)
            row_color = TEXT_PRIMARY if connected else TEXT_SECONDARY
            speed = a.get("speed_mbps", 0)
            speed_str = f"{speed} Mbps" if speed else "—"
            sig = a.get("signal_pct", -1)
            sig_str = f"{sig}%" if sig >= 0 else "—"
            status_str = "Connected" if connected else "Disconnected"
            status_color = GREEN if connected else RED
            vals = [
                a.get("name", ""),
                a.get("type", ""),
                a.get("ipv4", "—"),
                a.get("mac", "—"),
                speed_str,
                sig_str,
                a.get("ssid", ""),
                status_str,
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                c = status_color if col == 7 else row_color
                item.setForeground(QColor(c))
                self._adapters_table.setItem(row, col, item)

    # ── Diagnostics tab ───────────────────────────────────────────────────────

    def _build_diagnostics_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        # Top bar
        top = QHBoxLayout()
        title = QLabel("⚡  Network Health & Diagnostics")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        self._btn_diag = QPushButton("⚡  Run Diagnostics")
        self._btn_diag.setObjectName("btnDiag")
        self._btn_diag.setFixedHeight(34)
        self._btn_diag.clicked.connect(self._start_diagnostics)
        top.addWidget(self._btn_diag)
        lay.addLayout(top)

        self._diag_status_lbl = QLabel("Click 'Run Diagnostics' to test connectivity and performance.")
        self._diag_status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._diag_status_lbl)

        # Summary row
        summary_row = QHBoxLayout()
        self._diag_speed_lbl  = self._stat_label("Download", "—")
        self._diag_public_lbl = self._stat_label("Public IP", "—")
        self._diag_dns_lbl    = self._stat_label("System DNS", "—")
        self._diag_gw_lbl     = self._stat_label("Gateway RTT", "—")
        for w2 in (self._diag_gw_lbl, self._diag_speed_lbl,
                   self._diag_dns_lbl, self._diag_public_lbl):
            summary_row.addWidget(w2)
        summary_row.addStretch()
        lay.addLayout(summary_row)

        # Two-column detail: Ping | DNS
        cols = QHBoxLayout()
        cols.setSpacing(10)

        left = QVBoxLayout()
        left.addWidget(QLabel("  Ping Tests"))
        self._diag_ping_table = _table(["Host", "IP", "RTT (ms)", "Status"])
        self._diag_ping_table.setColumnWidth(0, 120)
        self._diag_ping_table.setColumnWidth(1, 120)
        self._diag_ping_table.setColumnWidth(2, 70)
        left.addWidget(self._diag_ping_table)

        right = QVBoxLayout()
        right.addWidget(QLabel("  DNS Speed"))
        self._diag_dns_table = _table(["DNS Server", "Latency (ms)", "Resolved IP", "Status"])
        self._diag_dns_table.setColumnWidth(0, 110)
        self._diag_dns_table.setColumnWidth(1, 100)
        self._diag_dns_table.setColumnWidth(2, 110)
        right.addWidget(self._diag_dns_table)

        cols.addLayout(left, 1)
        cols.addLayout(right, 1)
        lay.addLayout(cols)

        # HTTP connectivity
        http_row = QHBoxLayout()
        http_lbl = QLabel("  Internet Connectivity:")
        http_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        http_row.addWidget(http_lbl)
        self._diag_http_labels: list = []
        for name, _ in [("Google 204", ""), ("Cloudflare", ""), ("Apple captive", "")]:
            lbl = QLabel(f"● {name}: —")
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding:0 10px;")
            self._diag_http_labels.append(lbl)
            http_row.addWidget(lbl)
        http_row.addStretch()
        lay.addLayout(http_row)

        # DNS Leak
        leak_row = QHBoxLayout()
        leak_lbl_hdr = QLabel("  DNS Leak Test:")
        leak_lbl_hdr.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        leak_row.addWidget(leak_lbl_hdr)
        self._diag_leak_lbl = QLabel("—")
        self._diag_leak_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-left:10px;")
        self._diag_leak_lbl.setWordWrap(True)
        leak_row.addWidget(self._diag_leak_lbl, 1)
        lay.addLayout(leak_row)
        self._diag_leak_table = _table(["Resolver IP", "Country", "ASN / Org"])
        self._diag_leak_table.setColumnWidth(0, 130)
        self._diag_leak_table.setColumnWidth(1, 120)
        self._diag_leak_table.setMaximumHeight(110)
        lay.addWidget(self._diag_leak_table)

        # Traceroute
        trace_lbl = QLabel("  Traceroute to 8.8.8.8:")
        trace_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(trace_lbl)
        self._diag_trace_table = _table(["Hop", "IP Address", "RTT (ms)"])
        self._diag_trace_table.setColumnWidth(0, 50)
        self._diag_trace_table.setColumnWidth(1, 160)
        lay.addWidget(self._diag_trace_table, 1)
        return w

    # ── Logger tab ────────────────────────────────────────────────────────────

    def _build_logger_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QTextEdit
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        _qs = QSettings("NetSentinel", "NetSentinel")

        # ── Page header ───────────────────────────────────────────────────────
        title = QLabel("📋  Network Logger")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            "background:transparent; border:none;"
        )
        lay.addWidget(title)

        # ── Log Sources card ──────────────────────────────────────────────────
        src_card, src_body = _make_card("Log Sources")

        def _section_lbl(text: str) -> QLabel:
            lbl = QLabel(text.upper())
            lbl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
                "letter-spacing:0.8px; background:transparent; border:none;"
            )
            return lbl

        def _chk(text: str, tooltip: str = "") -> QCheckBox:
            c = QCheckBox(text)
            c.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px;")
            if tooltip:
                c.setToolTip(tooltip)
            return c

        def _spin(lo: int, hi: int, val: int, suffix: str, w: int = 72) -> QSpinBox:
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setSuffix(suffix)
            s.setFixedWidth(w)
            s.setStyleSheet(
                f"QSpinBox {{ background:{BG_CARD}; border:1px solid {BORDER};"
                f" border-radius:4px; padding:1px 4px; font-size:11px; color:{TEXT_PRIMARY}; }}"
                f"QSpinBox:disabled {{ color:{TEXT_MUTED}; }}"
            )
            return s

        # ── Active Pollers ────────────────────────────────────────────────────
        src_body.addWidget(_section_lbl("Active Pollers"))

        # Ping RTT row
        ping_row = QHBoxLayout()
        ping_row.setSpacing(6)
        ping_lbl = QLabel("Ping RTT")
        ping_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:600;")
        int_lbl = QLabel("Interval:")
        int_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_interval = _spin(5, 3600, _qs.value("logger/interval_s", 60, type=int), " s", 72)
        self._log_interval.setToolTip("How often to ping each host")
        self._log_interval.valueChanged.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/interval_s", v)
        )
        ping_row.addWidget(ping_lbl)
        ping_row.addSpacing(8)
        ping_row.addWidget(int_lbl)
        ping_row.addWidget(self._log_interval)
        ping_row.addStretch()
        src_body.addLayout(ping_row)

        # Ping optional sub-measurements
        opt_row = QHBoxLayout()
        opt_row.setSpacing(12)
        opt_row.setContentsMargins(0, 0, 0, 0)
        self._log_chk_jitter = _chk("Jitter  (3× ping)", "Measure RTT variance — adds 2 extra pings per cycle")
        self._log_chk_dns    = _chk("DNS latency",       "Time a DNS lookup each cycle")
        self._log_chk_http   = _chk("HTTP check",        "Check HTTP reachability each cycle")
        self._log_chk_jitter.setChecked(_qs.value("logger/chk_jitter", False, type=bool))
        self._log_chk_dns   .setChecked(_qs.value("logger/chk_dns",    False, type=bool))
        self._log_chk_http  .setChecked(_qs.value("logger/chk_http",   False, type=bool))
        self._log_chk_jitter.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_jitter", v))
        self._log_chk_dns.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_dns", v))
        self._log_chk_http.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_http", v))
        opt_row.addSpacing(16)
        for c in (self._log_chk_jitter, self._log_chk_dns, self._log_chk_http):
            opt_row.addWidget(c)
        opt_row.addStretch()
        src_body.addLayout(opt_row)

        src_body.addSpacing(4)

        # 5G Modem row
        modem_row = QHBoxLayout()
        modem_row.setSpacing(6)
        self._log_chk_modem = _chk(
            "5G Modem signal",
            "Log modem signal metrics (RSRP, SINR, band…) to the database at the set interval.\n"
            "Requires modem credentials saved on the Modem page."
        )
        self._log_chk_modem.setChecked(_qs.value("logging/modem_enabled", False, type=bool))
        modem_int_lbl = QLabel("Log every:")
        modem_int_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_modem_interval = _spin(
            1, 60, _qs.value("logging/modem_interval_min", 5, type=int), " min"
        )
        self._log_modem_interval.setEnabled(self._log_chk_modem.isChecked())
        self._log_modem_interval.setToolTip("How often to write modem signal data to the database")
        self._log_chk_modem.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("logging/modem_enabled", v),
                self._log_modem_interval.setEnabled(v),
            )
        )
        self._log_modem_interval.valueChanged.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/modem_interval_min", v)
        )
        modem_row.addWidget(self._log_chk_modem)
        modem_row.addSpacing(8)
        modem_row.addWidget(modem_int_lbl)
        modem_row.addWidget(self._log_modem_interval)
        modem_row.addStretch()
        src_body.addLayout(modem_row)

        # Mesh row
        mesh_row = QHBoxLayout()
        mesh_row.setSpacing(6)
        self._log_chk_mesh = _chk(
            "Mesh router status",
            "Log mesh node status (online count, worst RSSI…) to the database at the set interval.\n"
            "Requires Deco credentials saved on the Hardware Integration page."
        )
        self._log_chk_mesh.setChecked(_qs.value("logging/mesh_enabled", False, type=bool))
        mesh_int_lbl = QLabel("Log every:")
        mesh_int_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_mesh_interval = _spin(
            1, 60, _qs.value("logging/mesh_interval_min", 5, type=int), " min"
        )
        self._log_mesh_interval.setEnabled(self._log_chk_mesh.isChecked())
        self._log_mesh_interval.setToolTip("How often to write mesh status data to the database")
        self._log_chk_mesh.toggled.connect(
            lambda v: (
                QSettings("NetSentinel", "NetSentinel").setValue("logging/mesh_enabled", v),
                self._log_mesh_interval.setEnabled(v),
            )
        )
        self._log_mesh_interval.valueChanged.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/mesh_interval_min", v)
        )
        mesh_row.addWidget(self._log_chk_mesh)
        mesh_row.addSpacing(8)
        mesh_row.addWidget(mesh_int_lbl)
        mesh_row.addWidget(self._log_mesh_interval)
        mesh_row.addStretch()
        src_body.addLayout(mesh_row)

        src_body.addSpacing(6)

        # ── Passive Listeners ─────────────────────────────────────────────────
        src_body.addWidget(_section_lbl("Passive Listeners"))

        passive_row = QHBoxLayout()
        passive_row.setSpacing(16)
        self._log_chk_arp = _chk(
            "ARP watch",
            "Flag new or changed ARP entries — new devices, MAC changes, possible spoofing."
        )
        self._log_chk_arp.setChecked(_qs.value("logger/chk_arp", False, type=bool))
        self._log_chk_arp.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/chk_arp", v)
        )
        self._log_chk_syslog = _chk(
            "Syslog receiver",
            "Listen for syslog messages (UDP 514) from routers and other devices."
        )
        self._log_chk_syslog.setChecked(_qs.value("logging/syslog_enabled", True, type=bool))
        self._log_chk_syslog.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/syslog_enabled", v)
        )
        self._log_chk_snmp = _chk(
            "SNMP trap receiver",
            "Listen for SNMPv1/v2c traps (UDP 162) from managed devices."
        )
        self._log_chk_snmp.setChecked(_qs.value("logging/snmp_enabled", True, type=bool))
        self._log_chk_snmp.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logging/snmp_enabled", v)
        )
        for c in (self._log_chk_arp, self._log_chk_syslog, self._log_chk_snmp):
            passive_row.addWidget(c)
        passive_row.addStretch()
        src_body.addLayout(passive_row)

        lay.addWidget(src_card)

        # ── Logger controls row ───────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        self._btn_log_start = QPushButton("▶  Start Logger")
        self._btn_log_start.setObjectName("btnDiag")
        self._btn_log_start.setFixedHeight(34)
        self._btn_log_start.clicked.connect(self._toggle_logger)

        self._btn_log_open = QPushButton("📂  Open Log File")
        self._btn_log_open.setFixedHeight(34)
        self._btn_log_open.setEnabled(False)
        self._btn_log_open.clicked.connect(self._open_log_file)

        self._btn_log_analyse = QPushButton("⊕  Load & Analyse")
        self._btn_log_analyse.setFixedHeight(34)
        self._btn_log_analyse.clicked.connect(self._load_log_file)

        self._btn_log_chart = QPushButton("◎  View Chart")
        self._btn_log_chart.setFixedHeight(34)
        self._btn_log_chart.setEnabled(False)
        self._btn_log_chart.setToolTip("Render loaded log as RTT chart (opens interactive window)")
        self._btn_log_chart.clicked.connect(self._view_log_chart)

        rot_lbl = QLabel("Rotate file:")
        rot_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._log_rotation = QComboBox()
        self._log_rotation.addItems(["Off", "1 hour", "6 hours", "12 hours", "24 hours"])
        self._log_rotation.setFixedWidth(90)
        self._log_rotation.setToolTip(
            "Start a new CSV file after this interval — keeps files to a manageable size.\n"
            "12 h is best practice."
        )
        _rot_vals = [0, 1, 6, 12, 24]
        self._log_rotation_vals = _rot_vals
        _saved_rot = _qs.value("logger/rotation_hours", 12, type=int)
        self._log_rotation.setCurrentIndex(
            _rot_vals.index(_saved_rot) if _saved_rot in _rot_vals else 3
        )
        self._log_rotation.currentIndexChanged.connect(
            lambda i, v=_rot_vals: QSettings("NetSentinel", "NetSentinel").setValue(
                "logger/rotation_hours", v[i]
            )
        )

        self._log_chk_autostart = QCheckBox("Auto-start on launch")
        self._log_chk_autostart.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:600;")
        self._log_chk_autostart.setToolTip(
            "Logger will start immediately each time the app launches — no manual step required."
        )
        self._log_chk_autostart.setChecked(_qs.value("logger/auto_start", False, type=bool))
        self._log_chk_autostart.toggled.connect(
            lambda v: QSettings("NetSentinel", "NetSentinel").setValue("logger/auto_start", v)
        )

        ctrl_row.addWidget(self._btn_log_start)
        ctrl_row.addWidget(self._btn_log_open)
        ctrl_row.addWidget(self._btn_log_analyse)
        ctrl_row.addWidget(self._btn_log_chart)
        ctrl_row.addSpacing(12)
        ctrl_row.addWidget(rot_lbl)
        ctrl_row.addWidget(self._log_rotation)
        ctrl_row.addSpacing(12)
        ctrl_row.addWidget(self._log_chk_autostart)
        ctrl_row.addStretch()
        lay.addLayout(ctrl_row)

        # ── Status + summary stats ────────────────────────────────────────────
        self._log_status_lbl = QLabel(
            "Logger not running.  Start it, then leave the app running in the background."
        )
        self._log_status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._log_status_lbl)

        stats_row = QHBoxLayout()
        self._log_stat_total   = self._stat_label("Total Pings", "—")
        self._log_stat_uptime  = self._stat_label("Uptime", "—")
        self._log_stat_avgrtt  = self._stat_label("Avg RTT", "—")
        self._log_stat_outages = self._stat_label("Outages", "—")
        for s in (self._log_stat_total, self._log_stat_uptime,
                  self._log_stat_avgrtt, self._log_stat_outages):
            stats_row.addWidget(s)
        stats_row.addStretch()
        lay.addLayout(stats_row)

        # ── Log analysis results panel ────────────────────────────────────────
        analysis_lbl = QLabel("  Log Analysis:")
        analysis_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(analysis_lbl)
        self._log_analysis_box = QTextEdit()
        self._log_analysis_box.setReadOnly(True)
        self._log_analysis_box.setMaximumHeight(160)
        self._log_analysis_box.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            f"border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; padding:6px;"
        )
        self._log_analysis_box.setPlaceholderText(
            "Load a log file to see automatic diagnostic findings here."
        )
        lay.addWidget(self._log_analysis_box)

        # ── Outage summary ────────────────────────────────────────────────────
        outage_lbl = QLabel("  Detected Outages:")
        outage_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(outage_lbl)
        self._log_outage_table = _table([
            "Host", "Outage Start", "Outage End", "Duration (s)", "Consecutive Fails"
        ])
        self._log_outage_table.setMaximumHeight(160)
        lay.addWidget(self._log_outage_table)

        # ── Live ping log ─────────────────────────────────────────────────────
        live_lbl = QLabel("  Live log (most recent pings):")
        live_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(live_lbl)
        self._log_live_table = _table([
            "Timestamp", "Host", "RTT (ms)", "Jitter", "DNS (ms)", "HTTP", "ARP Event", "Status"
        ])
        self._log_live_table.setColumnWidth(0, 155)
        self._log_live_table.setColumnWidth(1, 120)
        self._log_live_table.setColumnWidth(2, 70)
        self._log_live_table.setColumnWidth(3, 65)
        self._log_live_table.setColumnWidth(4, 70)
        self._log_live_table.setColumnWidth(5, 50)
        self._log_live_table.setColumnWidth(6, 180)
        lay.addWidget(self._log_live_table, 1)

        return w

    # ── MTR tab (Advanced) ────────────────────────────────────────────────────

    def _build_mtr_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("🔁  Continuous Traceroute  (MTR)")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        tgt_lbl = QLabel("Target:")
        tgt_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        self._mtr_target = QLineEdit("8.8.8.8")
        self._mtr_target.setFixedWidth(130)
        self._btn_mtr = QPushButton("▶  Start MTR")
        self._btn_mtr.setObjectName("btnDiag")
        self._btn_mtr.setFixedHeight(30)
        self._btn_mtr.clicked.connect(self._toggle_mtr)
        top.addWidget(tgt_lbl)
        top.addWidget(self._mtr_target)
        top.addWidget(self._btn_mtr)
        lay.addLayout(top)

        self._mtr_status = QLabel("Click Start MTR to run a continuous hop-by-hop trace.")
        self._mtr_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._mtr_status)

        self._mtr_table = _table(["Hop", "IP Address", "Sent", "Loss %", "Avg RTT (ms)", "Last RTT"])
        self._mtr_table.setColumnWidth(0, 45)
        self._mtr_table.setColumnWidth(1, 160)
        self._mtr_table.setColumnWidth(2, 60)
        self._mtr_table.setColumnWidth(3, 70)
        self._mtr_table.setColumnWidth(4, 110)
        lay.addWidget(self._mtr_table, 1)
        self._mtr_worker = None
        # {hop: {ip, sent, lost, total_rtt}}
        self._mtr_stats: dict = {}
        self._mtr_cycle = 0
        return w

    # ── Advanced Tools tab ────────────────────────────────────────────────────

    def _build_advanced_tools_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(10)

        title = QLabel("🔧  Advanced Tools")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        lay.addWidget(title)

        # Port Scanner card
        ps_frame = QFrame()
        ps_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        ps_l = QVBoxLayout(ps_frame)
        ps_l.setContentsMargins(16, 12, 16, 12)
        ps_l.setSpacing(6)
        ps_title = QLabel("🔍  Port Scanner")
        ps_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ps_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        ps_l.addWidget(ps_title)
        ps_desc = QLabel(
            "TCP connect-scan of common ports on any host.  "
            "No admin required.  Right-click a device in Device Fingerprinter → Port Scan."
        )
        ps_desc.setWordWrap(True)
        ps_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        ps_l.addWidget(ps_desc)
        ps_row = QHBoxLayout()
        self._ps_host = QLineEdit()
        self._ps_host.setPlaceholderText("IP or hostname…")
        self._ps_host.setFixedWidth(180)
        from PyQt6.QtWidgets import QComboBox
        self._ps_mode = QComboBox()
        self._ps_mode.addItems(["Normal", "Fast", "Low Impact"])
        self._ps_mode.setFixedWidth(90)
        self._ps_mode.setToolTip(
            "Fast: 100 threads, 0.35s timeout\n"
            "Normal: 50 threads, 0.60s timeout\n"
            "Low Impact: 8 threads, 1.20s timeout, 50ms delay"
        )
        self._btn_ps = QPushButton("Scan Ports")
        self._btn_ps.setObjectName("btnDiag")
        self._btn_ps.setFixedHeight(30)
        self._btn_ps.clicked.connect(
            lambda: self._run_port_scan(self._ps_host.text().strip())
        )
        self._ps_status = QLabel("")
        self._ps_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        ps_row.addWidget(self._ps_host)
        ps_row.addWidget(self._ps_mode)
        ps_row.addWidget(self._btn_ps)
        ps_row.addWidget(self._ps_status, 1)
        ps_l.addLayout(ps_row)
        self._ps_table = _table(["Port", "Service", "Version", "Banner", "Risk"])
        self._ps_table.setColumnWidth(0, 60)
        self._ps_table.setColumnWidth(1, 170)
        self._ps_table.setColumnWidth(2, 180)
        self._ps_table.setColumnWidth(3, 200)
        self._ps_table.setMaximumHeight(220)
        ps_l.addWidget(self._ps_table)
        lay.addWidget(ps_frame)

        # Wake-on-LAN card
        wol_frame = QFrame()
        wol_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        wol_l = QVBoxLayout(wol_frame)
        wol_l.setContentsMargins(16, 12, 16, 12)
        wol_l.setSpacing(6)
        wol_title = QLabel("⚡  Wake-on-LAN")
        wol_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        wol_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        wol_l.addWidget(wol_title)
        wol_row = QHBoxLayout()
        self._wol_mac = QLineEdit()
        self._wol_mac.setPlaceholderText("MAC address  aa:bb:cc:dd:ee:ff")
        self._wol_mac.setFixedWidth(220)
        self._btn_wol = QPushButton("Send WoL Packet")
        self._btn_wol.setObjectName("btnNetRefresh")
        self._btn_wol.setFixedHeight(30)
        self._btn_wol.clicked.connect(
            lambda: self._send_wol(self._wol_mac.text().strip())
        )
        self._wol_status = QLabel("")
        self._wol_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        wol_row.addWidget(QLabel("MAC:"))
        wol_row.addWidget(self._wol_mac)
        wol_row.addWidget(self._btn_wol)
        wol_row.addWidget(self._wol_status, 1)
        wol_l.addLayout(wol_row)
        lay.addWidget(wol_frame)

        # Device Baseline card
        bl_frame = QFrame()
        bl_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        bl_l = QVBoxLayout(bl_frame)
        bl_l.setContentsMargins(16, 12, 16, 12)
        bl_l.setSpacing(6)
        bl_title = QLabel("📋  New Device Alerts  (baseline diff)")
        bl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        bl_title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        bl_l.addWidget(bl_title)
        bl_desc = QLabel(
            "After each scan, devices not seen before are highlighted here.  "
            "Baseline is saved to ~/Documents/NetSentinel/device_baseline.json."
        )
        bl_desc.setWordWrap(True)
        bl_desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        bl_l.addWidget(bl_desc)
        self._bl_new_lbl = QLabel("No scan run yet.")
        self._bl_new_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        bl_l.addWidget(self._bl_new_lbl)
        self._bl_table = _table(["IP", "Hostname", "MAC", "Vendor", "First Seen"])
        self._bl_table.setMaximumHeight(160)
        bl_l.addWidget(self._bl_table)
        lay.addWidget(bl_frame)

        lay.addStretch()
        return w

    # ── MTR handlers ──────────────────────────────────────────────────────────

    @pyqtSlot()
    def _toggle_mtr(self):
        if self._mtr_worker and self._mtr_worker.isRunning():
            self._mtr_worker.stop()
            self._btn_mtr.setText("▶  Start MTR")
            self._mtr_status.setText("MTR stopped.")
            self._mtr_worker = None
        else:
            target = self._mtr_target.text().strip() or "8.8.8.8"
            self._record_recent_action(
                action_id=f"mtr:{target}",
                label=f"Hop-by-hop trace · {target}",
                page="Hop-by-Hop Trace",
                params={"target": target},
            )
            from workers.scan_worker import MTRWorker
            self._mtr_stats = {}
            self._mtr_table.setRowCount(0)
            self._mtr_cycle = 0
            self._mtr_worker = MTRWorker(target=target)
            self._mtr_worker.hop_result.connect(self._on_mtr_hop)
            self._mtr_worker.cycle_done.connect(self._on_mtr_cycle)
            self._mtr_worker.status.connect(self._mtr_status.setText)
            self._mtr_worker.error.connect(self._mtr_status.setText)
            self._mtr_worker.start()
            self._btn_mtr.setText("⏹  Stop MTR")

    @pyqtSlot(int, str, float)
    def _on_mtr_hop(self, hop_n: int, ip: str, rtt: float):
        if hop_n not in self._mtr_stats:
            self._mtr_stats[hop_n] = {"ip": ip, "sent": 0, "lost": 0, "total": 0.0}
        s = self._mtr_stats[hop_n]
        s["sent"] += 1
        if rtt < 0:
            s["lost"] += 1
        else:
            s["total"] += rtt
        s["last"] = rtt

    @pyqtSlot(int)
    def _on_mtr_cycle(self, cycle: int):
        from PyQt6.QtGui import QColor
        self._mtr_cycle = cycle
        self._mtr_table.setRowCount(0)
        for hop_n in sorted(self._mtr_stats):
            s = self._mtr_stats[hop_n]
            sent = s["sent"]
            lost = s["lost"]
            ok = sent - lost
            loss_pct = (lost / sent * 100) if sent else 0
            avg_rtt = (s["total"] / ok) if ok else -1
            last = s.get("last", -1)
            loss_color = RED if loss_pct > 10 else (AMBER if loss_pct > 0 else GREEN)
            row = self._mtr_table.rowCount()
            self._mtr_table.insertRow(row)
            vals = [
                str(hop_n), s["ip"], str(sent),
                f"{loss_pct:.0f}%",
                f"{avg_rtt:.0f} ms" if avg_rtt >= 0 else "—",
                f"{last:.0f} ms" if last >= 0 else "—",
            ]
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(loss_color if col == 3 else TEXT_PRIMARY))
                self._mtr_table.setItem(row, col, item)

    # ── Port scan handlers ────────────────────────────────────────────────────

    def _run_port_scan(self, host: str):
        if not host:
            return
        self._record_recent_action(
            action_id=f"ps:{host}",
            label=f"Port scan · {host}",
            page="Tools & Wake-on-LAN",
            params={"host": host},
        )
        from workers.scan_worker import PortScanWorker
        if hasattr(self, "_ps_host"):
            self._ps_host.setText(host)
        self._nav_rail_go_to("Tools & Wake-on-LAN")
        self._ps_table.setRowCount(0)
        mode = self._ps_mode.currentText().lower() if hasattr(self, "_ps_mode") else "normal"
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(f"Scanning {host} ({mode} mode)…")
        self._ps_worker = PortScanWorker(host=host, mode=mode)
        self._ps_worker.result.connect(self._on_port_scan_result)
        self._ps_worker.status.connect(lambda m: self._ps_status.setText(m) if hasattr(self, "_ps_status") else None, Qt.ConnectionType.QueuedConnection)
        self._ps_worker.error.connect(lambda e: self._ps_status.setText(f"Error: {e}") if hasattr(self, "_ps_status") else None, Qt.ConnectionType.QueuedConnection)
        self._ps_worker.start()

    @pyqtSlot(object)
    def _on_port_scan_result(self, data):
        from PyQt6.QtGui import QColor
        self._last_portscan_result = data   # cache for Nmap XML export
        self._ps_table.setRowCount(0)
        for p in data.open_ports:
            row = self._ps_table.rowCount()
            self._ps_table.insertRow(row)
            risk_color = RED if p.risk == "HIGH" else TEXT_PRIMARY
            for col, val in enumerate([str(p.port), p.name, p.service_version or "", p.banner or "", p.risk]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(risk_color if col in (1, 4) else TEXT_PRIMARY))
                self._ps_table.setItem(row, col, item)
        if hasattr(self, "_ps_status"):
            self._ps_status.setText(data.plain_verdict)
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_open_port_count(len(data.open_ports))
        # ── Update NetworkDocPage with accumulated port data ──────────────────
        try:
            if data.open_ports:
                _host_key = getattr(data, "host", "") or getattr(data, "ip", "")
                if _host_key:
                    self._port_data_cache[_host_key] = [
                        {"port": str(p.port), "protocol": "tcp",
                         "service": p.name or "", "state": "open",
                         "banner": p.banner or p.service_version or ""}
                        for p in data.open_ports
                    ]
            _nd_cert: list = []
            if self._store is not None:
                for _c in self._store.query_cert_status():
                    _nd_cert.append({"host": _c.host, "cn": _c.subject or "",
                                     "issuer": _c.issuer or "", "not_after": _c.not_after or "",
                                     "days_remaining": _c.days_remaining})
            self._network_doc_page.set_scan_data(
                devices=self._last_scan_devices,
                port_data=self._port_data_cache,
                cert_data=_nd_cert,
                topo_widget=getattr(self, "_topology_widget", None),
            )
        except Exception:
            pass

    # ── WoL handler ───────────────────────────────────────────────────────────

    def _send_wol(self, mac: str):
        from modules.utils import send_wol
        ok = send_wol(mac)
        msg = f"WoL magic packet sent to {mac}" if ok else f"Invalid MAC address: {mac}"
        color = GREEN if ok else RED
        if hasattr(self, "_wol_status"):
            self._wol_status.setStyleSheet(f"color:{color}; font-size:11px;")
            self._wol_status.setText(msg)
        else:
            self._set_status(msg)

    # ── Logger handlers ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _toggle_logger(self):
        if self._logger_worker and self._logger_worker.isRunning():
            # Stop
            self._logger_worker.stop_logger()
            self._btn_log_start.setText("▶  Start Logger")
            self._log_status_lbl.setText("Logger stopped.")
            self._btn_log_open.setEnabled(True)
            self._home_page.set_monitoring_status(False)
        else:
            # Start
            import time as _time
            from workers.scan_worker import LoggerWorker
            interval = self._log_interval.value()
            rotation_h = self._log_rotation_vals[self._log_rotation.currentIndex()]
            self._logger_worker = LoggerWorker(
                interval_s=interval,
                enable_jitter=self._log_chk_jitter.isChecked(),
                enable_dns=self._log_chk_dns.isChecked(),
                enable_http=self._log_chk_http.isChecked(),
                enable_arp=self._log_chk_arp.isChecked(),
                rotation_hours=rotation_h,
            )
            self._logger_start_ts = _time.time()
            self._logger_outage_count = 0
            self._logger_worker.entry_received.connect(self._on_log_entry)
            self._logger_worker.status.connect(self._log_status_lbl.setText)
            self._logger_worker.rotated.connect(self._on_log_rotate)
            self._logger_worker.error.connect(
                lambda e: self._log_status_lbl.setText(f"Error: {e}"),
                Qt.ConnectionType.QueuedConnection,
            )
            self._logger_worker.start()
            self._btn_log_start.setText("⏹  Stop Logger")
            self._btn_log_open.setEnabled(False)
            self._log_live_table.setRowCount(0)
            self._log_outage_table.setRowCount(0)
            self._home_page.set_monitoring_status(True, "", 0)
            # One-time prompt: only the very first time logging is started in this installation
            _qs2 = QSettings("NetSentinel", "NetSentinel")
            if not _qs2.value("logger/first_start_prompted", False, type=bool):
                _qs2.setValue("logger/first_start_prompted", True)
                from PyQt6.QtWidgets import QMessageBox
                _ans = QMessageBox.question(
                    self, "Logging started",
                    "Logger is now running.\n\nSwitch to Activity Log to view entries?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if _ans == QMessageBox.StandardButton.Yes and hasattr(self, "_logging_container"):
                    self._logging_container.setCurrentIndex(1)
                    self._nav_rail_go_to("Network Logger")

    @pyqtSlot(object)
    def _on_log_entry(self, entry):
        """Called from LoggerWorker for each new ping result."""
        self._last_log_status = entry.status
        self._refresh_pulse_bar()
        if hasattr(self, "_log_hub_page"):
            self._log_hub_page.add_log_entry(entry)

    @pyqtSlot(object)
    def _on_live_challenge(self, scenario) -> None:
        """Show an amber suggestion card on Home when a live lab scenario is ready."""
        self._pending_live_scenario = scenario
        if hasattr(self, "_home_page"):
            self._home_page.set_suggestions([{
                "text": f"Something just happened — {scenario.title.lower()}",
                "action_label": "Investigate →",
                "target": "__live__",
                "priority": "medium",
            }])

    def _on_investigate_live(self) -> None:
        """Navigate to Lab Mode and inject the pending live challenge scenario."""
        scenario = self._pending_live_scenario
        self._pending_live_scenario = None
        if scenario is None:
            return
        self._nav_rail_go_to("Lab Mode")
        if hasattr(self, "_lab_mode_page"):
            self._lab_mode_page.inject_live_challenge(scenario)

    @pyqtSlot(object)
    def _on_alert_view_requested(self, alert) -> None:
        """Navigate to the most relevant page for the alert that was clicked."""
        # Dict alerts come from the Home action-needed card rows — open the drawer directly
        if isinstance(alert, dict):
            self._nav_rail_go_to("Notifications")
            try:
                if hasattr(self, "_notifications_page"):
                    self._notifications_page._alert_drawer.open(alert)
            except Exception:
                pass
            return
        rule_type = getattr(alert, "rule_type", "") or ""
        host = getattr(alert, "host", "") or ""
        if rule_type == "PORT_SCAN" and host:
            if hasattr(self, "_syn_host"):
                self._syn_host.setText(host)
            self._nav_rail_go_to("Port Scan (TCP)")
        elif rule_type in ("THREAT_INTEL", "CVE") and host:
            if hasattr(self, "_threat_intel_page"):
                self._threat_intel_page.check_ip(host)
            self._nav_rail_go_to("Threat Intelligence")
        elif rule_type == "RATE_SPIKE" and host:
            self._nav_rail_go_to("Live Bandwidth")
        elif host:
            self._on_inventory_device_selected(host)
        else:
            self._nav_rail_go_to("Notifications")

    @pyqtSlot(object)
    def _on_animate_log_entry(self, entry) -> None:
        """Navigate to Protocol Visualizer and pre-load the protocol for this log entry."""
        self._nav_rail_go_to("Protocol Visualizer")
        if hasattr(self, "_protocol_viz_page"):
            self._protocol_viz_page.load_from_event(entry)
        from PyQt6.QtGui import QColor
        color_map = {"OK": GREEN, "SLOW": AMBER, "FAIL": RED}
        status_color = color_map.get(entry.status, TEXT_SECONDARY)
        rtt_str    = f"{entry.rtt_ms:.0f}"    if entry.rtt_ms    >= 0 else "—"
        jitter_str = f"{entry.jitter_ms:.0f}" if entry.jitter_ms >= 0 else ""
        dns_str    = f"{entry.dns_ms:.0f}"    if entry.dns_ms    >= 0 else ""
        http_str   = str(entry.http_status)   if entry.http_status >= 0 else ""
        arp_str    = entry.arp_event or ""

        # Prepend new row (keep max 500 rows visible)
        self._log_live_table.insertRow(0)
        row_vals = [entry.timestamp, entry.host, rtt_str, jitter_str,
                    dns_str, http_str, arp_str, entry.status]
        for col, val in enumerate(row_vals):
            item = QTableWidgetItem(str(val))
            c = status_color if col == 7 else (AMBER if col == 6 and val else TEXT_PRIMARY)
            item.setForeground(QColor(c))
            self._log_live_table.setItem(0, col, item)
        if self._log_live_table.rowCount() > 500:
            self._log_live_table.setRowCount(500)

        # Update live stats
        if self._logger_worker:
            summary = self._logger_worker.get_summary()
            if summary:
                self._update_stat(self._log_stat_total,
                                  str(summary.total_pings))
                self._update_stat(self._log_stat_uptime,
                                  f"{summary.uptime_pct:.1f}%",
                                  GREEN if summary.uptime_pct >= 99 else (AMBER if summary.uptime_pct >= 95 else RED))
                self._update_stat(self._log_stat_avgrtt,
                                  f"{summary.avg_rtt_ms:.0f} ms" if summary.avg_rtt_ms > 0 else "—")
                self._update_stat(self._log_stat_outages,
                                  str(len(summary.outages)),
                                  RED if summary.outages else GREEN)
                # Update home page monitoring card
                import time as _t
                elapsed_s = int(_t.time() - getattr(self, "_logger_start_ts", _t.time()))
                h, rem = divmod(elapsed_s, 3600)
                m = rem // 60
                elapsed_str = (f"{h} h {m} m" if h else f"{m} m") if elapsed_s >= 60 else ""
                self._logger_outage_count = len(summary.outages)
                self._home_page.set_monitoring_status(True, elapsed_str, self._logger_outage_count)
                self._log_chart_summary = summary
                self._btn_log_chart.setEnabled(True)

                # Rebuild outage table
                self._log_outage_table.setRowCount(0)
                for o in summary.outages:
                    row = self._log_outage_table.rowCount()
                    self._log_outage_table.insertRow(row)
                    for col, val in enumerate([
                        o.host, o.start, o.end,
                        f"{o.duration_s:.0f}", str(o.consecutive_fails)
                    ]):
                        item = QTableWidgetItem(str(val))
                        item.setForeground(
                            __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(RED)
                        )
                        self._log_outage_table.setItem(row, col, item)

    @pyqtSlot(str, int)
    def _on_log_rotate(self, filename: str, segment: int):
        """Called when NetworkLogger starts a new CSV segment."""
        self._log_status_lbl.setText(
            f"Segment {segment} started — now logging to {filename}"
        )

    def _open_log_file(self):
        """Open the log CSV in the default text editor / Excel."""
        if self._logger_worker and self._logger_worker.log_file:
            path = self._logger_worker.log_file
            if path.exists():
                webbrowser.open(path.as_uri())

    # ── Retention helpers ─────────────────────────────────────────────────────

    def _compute_suggestions(self) -> None:
        """Compute actionable next-steps and push them to the home page."""
        if not hasattr(self, "_home_page"):
            return
        suggestions: list = []

        # High-risk devices from last scan
        if getattr(self, "_m1_result", None):
            high = self._m1_result.get("high_risk_count", 0)
            if high > 0:
                s = "s" if high != 1 else ""
                suggestions.append({
                    "text": f"{high} high-risk device{s} found — review security findings",
                    "action_label": "View Overview →",
                    "target": "Overview",
                    "priority": "high",
                })

        # Stability logger not running
        if not (self._logger_worker and self._logger_worker.isRunning()):
            suggestions.append({
                "text": "Network stability is not being monitored — start logging to detect outages",
                "action_label": "Start Monitoring →",
                "target": None,
                "priority": "medium",
            })

        # No speed test in the last 7 days
        if self._store is not None:
            try:
                speed_rows = self._store.query_speed_test_history(hours=168, limit=1)
                if not speed_rows:
                    suggestions.append({
                        "text": "No speed test in the last 7 days — check your internet performance",
                        "action_label": "Run Speed Test →",
                        "target": "Speed Test",
                        "priority": "low",
                    })
            except Exception:
                pass

        # Open CVEs
        if self._store is not None:
            try:
                open_cves = self._store.list_cve_lifecycles(state_filter="Open")
                n = len(open_cves)
                if n > 0:
                    s = "s" if n != 1 else ""
                    suggestions.append({
                        "text": f"{n} open CVE{s} need remediation",
                        "action_label": "View CVEs →",
                        "target": "CVE Tracker",
                        "priority": "high",
                    })
            except Exception:
                pass

        # Poor grade
        bm = getattr(self, "_last_benchmark_result", None)
        if bm is not None:
            grade = getattr(bm, "overall_grade", None)
            if grade in ("C", "D", "F"):
                suggestions.append({
                    "text": f"Your network grade is {grade} — run a health check for recommendations",
                    "action_label": "View Overview →",
                    "target": "Overview",
                    "priority": "medium",
                })

        self._home_page.set_suggestions(suggestions)

    def _compute_last_visit_summary(self) -> None:
        """Show 'Since you were last here' on the home page using MetricStore + QSettings."""
        if not hasattr(self, "_home_page") or self._store is None:
            return
        try:
            import time as _time
            from PyQt6.QtCore import QSettings as _QS
            _s = _QS("NetSentinel", "NetSentinel")
            last_ts = int(_s.value("app/last_visit_ts", 0, type=int))
            now = int(_time.time())

            # Update the visit timestamp so next launch measures from now
            _s.setValue("app/last_visit_ts", str(now))

            if last_ts == 0:
                return  # First ever launch — nothing to compare

            hours_since = (now - last_ts) / 3600.0
            if hours_since < 0.5:
                return  # Relaunched within 30 min — not worth showing

            # Format "last visit" string
            if hours_since < 2:
                last_str = "about an hour ago"
            elif hours_since < 24:
                last_str = f"{int(hours_since)} hours ago"
            elif hours_since < 48:
                last_str = "yesterday"
            else:
                last_str = f"{int(hours_since / 24)} days ago"

            joined_events = self._store.query_device_events(
                hours=hours_since, event_types=["JOINED"]
            )
            joined_count = len({e.ip for e in joined_events})

            outage_events = self._store.query_device_events(
                hours=hours_since, event_types=["DOWN"]
            )
            outage_count = len(outage_events)

            self._home_page.set_last_visit_summary(joined_count, outage_count, last_str)
        except Exception:
            pass

    def _maybe_send_weekly_digest(self) -> None:
        """Show a tray digest notification if 7+ days since the last one."""
        try:
            import time as _time
            from PyQt6.QtCore import QSettings as _QS
            _s = _QS("NetSentinel", "NetSentinel")
            last_ts = int(_s.value("app/last_digest_ts", 0, type=int))
            now = int(_time.time())
            if now - last_ts < 7 * 86400:
                return
            if not self._tray_manager.is_available():
                return

            parts: list[str] = []
            if self._store is not None:
                try:
                    speed_rows = self._store.query_speed_test_history(hours=168, limit=1)
                    if speed_rows:
                        dl = speed_rows[0].download_mbps or 0.0
                        parts.append(f"Speed: {dl:.0f} Mbps download")
                    joined = self._store.query_device_events(hours=168, event_types=["JOINED"])
                    if joined:
                        n = len({e.ip for e in joined})
                        s = "s" if n != 1 else ""
                        parts.append(f"{n} new device{s} joined")
                    g = self._store.query_last_grade()
                    if g:
                        parts.append(f"Network grade: {g['grade']}")
                except Exception:
                    pass

            if not parts:
                parts.append("Network has been running smoothly")

            self._tray_manager.show_notification(
                "NetSentinel Weekly Digest",
                "  ·  ".join(parts),
                "INFO",
            )
            _s.setValue("app/last_digest_ts", str(now))
        except Exception:
            pass

    def _load_log_file(self):
        """Let the user pick any existing log CSV and show its analysis."""
        from PyQt6.QtWidgets import QFileDialog
        from modules.network_logger import load_log_file
        from pathlib import Path

        log_dir = str(Path.home() / "Documents" / "NetSentinel" / "logs")
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open NetSentinel Log", log_dir, "CSV Log Files (*.csv);;All Files (*)"
        )
        if not path_str:
            return
        summary = load_log_file(Path(path_str))

        # Populate stats
        self._update_stat(self._log_stat_total, str(summary.total_pings))
        self._update_stat(self._log_stat_uptime,
                          f"{summary.uptime_pct:.1f}%",
                          GREEN if summary.uptime_pct >= 99 else (AMBER if summary.uptime_pct >= 95 else RED))
        self._update_stat(self._log_stat_avgrtt,
                          f"{summary.avg_rtt_ms:.0f} ms" if summary.avg_rtt_ms > 0 else "—")
        self._update_stat(self._log_stat_outages,
                          str(len(summary.outages)),
                          RED if summary.outages else GREEN)

        # Populate live table with loaded entries (newest first) — all 8 columns
        from PyQt6.QtGui import QColor as _QColor
        self._log_live_table.setRowCount(0)
        for entry in reversed(summary.entries[-500:]):
            status_color = {"OK": GREEN, "SLOW": AMBER, "FAIL": RED}.get(entry.status, TEXT_SECONDARY)
            rtt_str    = f"{entry.rtt_ms:.0f}"    if entry.rtt_ms    >= 0 else "—"
            jitter_str = f"{entry.jitter_ms:.0f}" if entry.jitter_ms >= 0 else ""
            dns_str    = f"{entry.dns_ms:.0f}"    if entry.dns_ms    >= 0 else ""
            http_str   = str(entry.http_status)   if entry.http_status >= 0 else ""
            arp_str    = entry.arp_event or ""
            row = self._log_live_table.rowCount()
            self._log_live_table.insertRow(row)
            for col, val in enumerate([
                entry.timestamp, entry.host, rtt_str, jitter_str,
                dns_str, http_str, arp_str, entry.status,
            ]):
                item = QTableWidgetItem(str(val))
                c = status_color if col == 7 else (AMBER if col == 6 and val else TEXT_PRIMARY)
                item.setForeground(_QColor(c))
                self._log_live_table.setItem(row, col, item)

        # Outage table — AMBER < 5 min, RED ≥ 5 min
        self._log_outage_table.setRowCount(0)
        for o in summary.outages:
            row = self._log_outage_table.rowCount()
            self._log_outage_table.insertRow(row)
            out_color = AMBER if o.duration_s < 300 else RED
            for col, val in enumerate([
                o.host, o.start, o.end, f"{o.duration_s:.0f}", str(o.consecutive_fails)
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(_QColor(out_color))
                self._log_outage_table.setItem(row, col, item)

        self._log_status_lbl.setText(
            f"Loaded {summary.total_pings} entries from {Path(path_str).name}  "
            f"— {len(summary.outages)} outage(s), {summary.uptime_pct:.1f}% uptime"
        )

        # Store summary and enable the chart button
        self._log_chart_summary = summary
        self._btn_log_chart.setEnabled(True)

        # ── Automated analysis ────────────────────────────────────────────────
        try:
            from modules.network_logger import analyse_log
            findings = analyse_log(summary)
            _sev_color = {"HIGH": RED, "WARN": AMBER, "INFO": GREEN}
            html_parts = []
            for f in findings:
                fc = _sev_color.get(f.severity, TEXT_SECONDARY)
                html_parts.append(
                    f"<p style='margin:4px 0'>"
                    f"<span style='color:{fc};font-weight:bold'>[{f.severity}] {f.category}: {f.title}</span>"
                    f"<br><span style='color:{TEXT_SECONDARY}'>{f.detail}</span></p>"
                )
            self._log_analysis_box.setHtml("".join(html_parts))
        except Exception as _exc:
            self._log_analysis_box.setPlainText(f"Analysis failed: {_exc}")

    # ── IPv6 tab ──────────────────────────────────────────────────────────────

    def _build_ipv6_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("🔷  IPv6 Devices")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        self._btn_ipv6_scan = QPushButton("▶  Scan IPv6")
        self._btn_ipv6_scan.setObjectName("btnDiag")
        self._btn_ipv6_scan.setFixedHeight(34)
        self._btn_ipv6_scan.clicked.connect(self._start_ipv6_scan)
        top.addWidget(self._btn_ipv6_scan)
        lay.addLayout(top)

        self._ipv6_status = QLabel(
            "Reads the OS IPv6 neighbour cache, then actively pings fe80::/8 on each interface."
        )
        self._ipv6_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._ipv6_status)

        self._ipv6_table = _table(["IPv6 Address", "MAC Address", "State", "Source"])
        self._ipv6_table.setColumnWidth(0, 340)
        self._ipv6_table.setColumnWidth(1, 150)
        self._ipv6_table.setColumnWidth(2, 110)
        self._ipv6_table.setColumnWidth(3, 80)
        lay.addWidget(self._ipv6_table, 1)
        return w

    @pyqtSlot()
    def _start_ipv6_scan(self):
        if self._ipv6_worker and self._ipv6_worker.isRunning():
            return
        from workers.scan_worker import IPv6Worker
        self._ipv6_table.setRowCount(0)
        self._btn_ipv6_scan.setEnabled(False)
        self._ipv6_worker = IPv6Worker()
        self._ipv6_worker.result.connect(self._on_ipv6_result)
        self._ipv6_worker.status.connect(self._ipv6_status.setText)
        self._ipv6_worker.error.connect(
            lambda e: self._ipv6_status.setText(f"⚠ {e}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self._ipv6_worker.finished.connect(
            lambda: self._btn_ipv6_scan.setEnabled(True),
            Qt.ConnectionType.QueuedConnection,
        )
        self._ipv6_worker.start()

    @pyqtSlot(list)
    def _on_ipv6_result(self, devices: list):
        from PyQt6.QtGui import QColor
        self._ipv6_table.setRowCount(0)
        for d in devices:
            row = self._ipv6_table.rowCount()
            self._ipv6_table.insertRow(row)
            source_color = ACCENT_LITE if d.get("source") == "active" else TEXT_SECONDARY
            state_color  = GREEN if d.get("state", "").upper() == "REACHABLE" else TEXT_SECONDARY
            for col, val in enumerate([
                d.get("ip6", ""), d.get("mac", ""),
                d.get("state", ""), d.get("source", ""),
            ]):
                item = QTableWidgetItem(str(val))
                if col == 2:
                    item.setForeground(QColor(state_color))
                elif col == 3:
                    item.setForeground(QColor(source_color))
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
                self._ipv6_table.setItem(row, col, item)
        if not devices:
            self._ipv6_status.setText(
                "No IPv6 devices found — this is normal for most home networks"
            )
        else:
            self._ipv6_status.setText(
                f"{len(devices)} IPv6 device(s) found  "
                f"({sum(1 for d in devices if d.get('source')=='active')} via active sweep, "
                f"{sum(1 for d in devices if d.get('source')=='cache')} from cache)"
            )

    # ── Cloud Metadata tab (Recon) ────────────────────────────────────────────

    def _build_recon_cloud_metadata_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("☁  Cloud Metadata Detection")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        top.addWidget(title)
        top.addStretch()
        self._btn_cloud_scan = QPushButton("▶  Run Check")
        self._btn_cloud_scan.setObjectName("btnDiag")
        self._btn_cloud_scan.setFixedHeight(34)
        self._btn_cloud_scan.clicked.connect(self._start_cloud_metadata)
        top.addWidget(self._btn_cloud_scan)
        lay.addLayout(top)

        self._cloud_status = QLabel(
            "Probes 169.254.169.254 (AWS/Azure/GCP) to detect if this machine is inside a cloud VM. "
            "Also checks network devices for SSRF metadata-proxy exposure."
        )
        self._cloud_status.setWordWrap(True)
        self._cloud_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(self._cloud_status)

        # Local IMDS result card
        self._cloud_local_box = QTextEdit()
        self._cloud_local_box.setReadOnly(True)
        self._cloud_local_box.setMaximumHeight(180)
        self._cloud_local_box.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            f"border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; padding:6px;"
        )
        self._cloud_local_box.setPlaceholderText(
            "IMDS probe result will appear here — runs in < 1 second per provider."
        )
        lay.addWidget(self._cloud_local_box)

        net_lbl = QLabel("  Network SSRF Exposure  (devices that proxy 169.254.169.254):")
        net_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding-top:4px;")
        lay.addWidget(net_lbl)
        self._cloud_network_table = _table(
            ["Device IP", "MAC", "Hostname", "Exposed?", "Risk", "Finding"]
        )
        self._cloud_network_table.setColumnWidth(0, 120)
        self._cloud_network_table.setColumnWidth(1, 140)
        self._cloud_network_table.setColumnWidth(2, 140)
        self._cloud_network_table.setColumnWidth(3, 75)
        self._cloud_network_table.setColumnWidth(4, 70)
        lay.addWidget(self._cloud_network_table, 1)
        return w

    @pyqtSlot()
    def _start_cloud_metadata(self):
        if self._cloud_worker and self._cloud_worker.isRunning():
            return
        from workers.scan_worker import CloudMetadataWorker
        self._cloud_local_box.clear()
        self._cloud_network_table.setRowCount(0)
        self._btn_cloud_scan.setEnabled(False)
        self._cloud_status.setText("Probing IMDS endpoints…")
        # Pass in last known devices if available
        devices = getattr(self, "_last_scan_devices", [])
        self._cloud_worker = CloudMetadataWorker(devices=devices)
        self._cloud_worker.local_result.connect(self._on_cloud_local_result)
        self._cloud_worker.network_result.connect(self._on_cloud_network_result)
        self._cloud_worker.status.connect(self._cloud_status.setText)
        self._cloud_worker.error.connect(
            lambda e: self._cloud_status.setText(f"⚠ {e}"),
            Qt.ConnectionType.QueuedConnection,
        )
        self._cloud_worker.finished.connect(
            lambda: self._btn_cloud_scan.setEnabled(True),
            Qt.ConnectionType.QueuedConnection,
        )
        self._cloud_worker.start()

    @pyqtSlot(object)
    def _on_cloud_local_result(self, result):
        risk_color = {"NONE": GREEN, "INFO": AMBER, "HIGH": RED}.get(result.risk_level, TEXT_SECONDARY)
        risk_icon  = {"NONE": "✔", "INFO": "ℹ", "HIGH": "⚠"}.get(result.risk_level, "?")
        lines = [
            f"<b style='color:{risk_color}'>{risk_icon} [{result.risk_level}]  {result.plain_verdict}</b>",
        ]
        if result.provider:
            lines.append(f"<br><b>Provider:</b> {result.provider}")
            if result.instance_id:
                lines.append(f"<b>Instance:</b> {result.instance_id}")
            if result.region:
                lines.append(f"<b>Region:</b> {result.region}")
            if result.account_id:
                lines.append(f"<b>Account:</b> {result.account_id}")
            if result.public_ip:
                lines.append(f"<b>Public IP:</b> {result.public_ip}")
            if result.ami_id:
                lines.append(f"<b>AMI:</b> {result.ami_id}")
            if result.project_id:
                lines.append(f"<b>Project:</b> {result.project_id}")
            if result.imdsv2_enforced is not None:
                v2_color = GREEN if result.imdsv2_enforced else RED
                v2_txt   = "enforced (secure)" if result.imdsv2_enforced else "NOT enforced — HIGH RISK"
                lines.append(f"<b>IMDSv2:</b> <span style='color:{v2_color}'>{v2_txt}</span>")
        for finding in result.findings:
            lines.append(f"<br><span style='color:{AMBER}'>⚠ {finding}</span>")
        self._cloud_local_box.setHtml("<br>".join(lines))

    @pyqtSlot(list)
    def _on_cloud_network_result(self, results: list):
        from PyQt6.QtGui import QColor
        self._cloud_network_table.setRowCount(0)
        for r in results:
            row = self._cloud_network_table.rowCount()
            self._cloud_network_table.insertRow(row)
            exposed_color = RED if r.exposed else GREEN
            row_color = RED if r.exposed else TEXT_SECONDARY
            finding_str = r.findings[0][:100] if r.findings else "—"
            for col, val in enumerate([
                r.device_ip, r.device_mac, r.hostname,
                "YES" if r.exposed else "no",
                r.risk_level, finding_str,
            ]):
                item = QTableWidgetItem(str(val))
                if col == 3:
                    item.setForeground(QColor(exposed_color))
                elif col in (4, 5):
                    item.setForeground(QColor(row_color))
                else:
                    item.setForeground(QColor(TEXT_SECONDARY if not r.exposed else RED))
                self._cloud_network_table.setItem(row, col, item)

    # ── Log chart handler ─────────────────────────────────────────────────────

    @pyqtSlot()
    def _view_log_chart(self):
        if not self._log_chart_summary:
            return
        try:
            if getattr(self, "_chart_window", None) and self._chart_window.isVisible():
                self._chart_window.raise_()
                self._chart_window.activateWindow()
                return
        except RuntimeError:
            pass
        try:
            from modules.log_chart import build_figure
            self._btn_log_chart.setEnabled(False)
            self._log_status_lbl.setText("Rendering chart…")
            fig = build_figure(self._log_chart_summary)
            self._chart_window = _make_chart_window(fig)
            self._chart_window.show()
            self._log_status_lbl.setText("Chart opened.")
        except Exception as exc:
            self._log_status_lbl.setText(f"Chart error: {exc}")
        finally:
            self._btn_log_chart.setEnabled(True)

    # ── Root Cause Analysis (Correlator) tab ─────────────────────────────────

    def _build_correlator_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Automatically links findings from all scans — STP, Storm, Diagnostics, and the "
            "Stability Log — to identify the single root cause of your network problems. "
            "Distinguishes between a fault in your home network versus a problem at your ISP. "
            "Run at least one scan first, then click Analyse."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._corr_status = QLabel("No analysis yet — run scans first, then click Analyse.")
        self._corr_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._corr_status.setWordWrap(True)

        # Verdict banner
        self._corr_verdict = QLabel("Run a scan to see the root cause summary.")
        self._corr_verdict.setWordWrap(True)
        self._corr_verdict.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:2px solid {BORDER}; "
            "border-radius:4px; padding:10px 14px; font-size:13px; font-weight:bold;"
        )

        ctrl = QHBoxLayout()
        btn_analyse = QPushButton("🧩  Analyse Root Cause Now")
        btn_analyse.setObjectName("btnScan")
        btn_analyse.setToolTip("Correlate all scan results and produce a prioritised root-cause list.")
        btn_analyse.clicked.connect(self._run_correlator)
        ctrl.addWidget(btn_analyse)
        ctrl.addStretch()

        # Findings table
        self._corr_table = _table([
            "Severity", "Category", "Source", "What's Wrong", "How to Fix It"
        ])
        self._corr_table.setColumnWidth(0, 80)
        self._corr_table.setColumnWidth(1, 200)
        self._corr_table.setColumnWidth(2, 160)
        self._corr_table.setColumnWidth(3, 300)

        lay.addWidget(info)
        lay.addWidget(self._corr_verdict)
        lay.addWidget(self._corr_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._corr_table, 1)
        return w

    @pyqtSlot()
    def _run_correlator(self):
        from PyQt6.QtGui import QColor
        try:
            from modules.root_cause_correlator import correlate

            # Gather available results — everything is optional
            diag   = self._diag_result
            m3_res = self._m3_result   # StormResult
            m1_dev = self._m1_result.get("devices", []) if self._m1_result else []
            gw_mac = self._net_info.get("gateway_mac", None) if self._net_info else None

            # Collect BPDU list from m2 result if present
            bpdus = []
            if self._m2_result and "bpdus" in self._m2_result:
                bpdus = self._m2_result["bpdus"]

            # Log summary from logger worker
            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass

            result = correlate(
                diag_result=diag,
                storm_result=m3_res,
                stp_bpdus=bpdus,
                fingerprint_devices=m1_dev,
                log_summary=log_summary,
                gateway_mac=gw_mac,
            )

            # Update verdict banner colour
            sev_colors = {
                "CRITICAL": RED, "HIGH": RED, "MEDIUM": AMBER,
                "LOW": GREEN, "INFO": TEXT_SECONDARY,
            }
            banner_color = sev_colors.get(result.global_severity, TEXT_SECONDARY)
            self._corr_verdict.setStyleSheet(
                f"background:{BG_CARD}; color:{banner_color}; "
                f"border:2px solid {banner_color}; border-radius:4px; "
                "padding:10px 14px; font-size:13px; font-weight:bold;"
            )
            self._corr_verdict.setText(result.plain_summary)

            # Populate findings table
            self._corr_table.setRowCount(0)
            for f in result.findings:
                row = self._corr_table.rowCount()
                self._corr_table.insertRow(row)
                color = sev_colors.get(f.severity, TEXT_SECONDARY)
                for col, val in enumerate([
                    f.severity, f.category, f.source, f.headline, f.remediation
                ]):
                    item = QTableWidgetItem(str(val))
                    if col in (0, 1):
                        item.setForeground(QColor(color))
                    self._corr_table.setItem(row, col, item)

            isp_tag = " [ISP issue — local alerts suppressed]" if result.suppress_local_alerts else ""
            self._corr_status.setText(
                f"Analysis complete — {result.finding_count} finding(s), "
                f"global severity: {result.global_severity}{isp_tag}"
            )

        except Exception as exc:
            self._corr_status.setText(f"⚠ Correlation failed: {exc}")

    # ── IoT Behavioural Baseline tab ─────────────────────────────────────────

    def _build_iot_baseline_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))

        info = QLabel(
            "NetSentinel learns what traffic is normal for each IoT device on your network "
            "(smart speakers, cameras, TVs, etc.) and alerts you if one behaves differently — "
            "e.g. suddenly port-scanning, contacting an unusual server, or flooding traffic. "
            "Run a Devices scan first, then click Learn to capture a baseline."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        self._iot_status = QLabel("No baseline loaded. Run 'Devices on Network' scan first.")
        self._iot_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._iot_status.setWordWrap(True)

        ctrl = QHBoxLayout()
        btn_learn = QPushButton("📖  Learn Normal Behaviour (60 s)")
        btn_learn.setObjectName("btnNetRefresh")
        btn_learn.setToolTip(
            "Sniffs traffic for 60 seconds to record which servers and ports each IoT device normally uses."
        )
        btn_learn.clicked.connect(self._run_iot_learn)

        btn_monitor = QPushButton("👁  Start Anomaly Monitor")
        btn_monitor.setObjectName("btnScan")
        btn_monitor.setToolTip("Continuously watches IoT device traffic and alerts on deviations from the baseline.")
        btn_monitor.clicked.connect(self._run_iot_monitor)

        btn_stop = QPushButton("⏹  Stop Monitor")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_iot_monitor)

        self._iot_learn_duration = QSpinBox()
        self._iot_learn_duration.setRange(30, 600)
        self._iot_learn_duration.setValue(60)
        self._iot_learn_duration.setSuffix(" s")
        self._iot_learn_duration.setToolTip("How many seconds to observe traffic during the learning phase")
        self._iot_learn_duration.setFixedWidth(80)

        ctrl.addWidget(btn_learn)
        ctrl.addWidget(self._iot_learn_duration)
        ctrl.addSpacing(12)
        ctrl.addWidget(btn_monitor)
        ctrl.addWidget(btn_stop)
        ctrl.addStretch()

        # Baseline summary table
        self._iot_baseline_table = _table([
            "Device", "IP", "MAC", "Type", "Known IPs", "Known Ports", "Avg pps", "Learned"
        ])
        self._iot_baseline_table.setColumnWidth(0, 200)
        self._iot_baseline_table.setColumnWidth(1, 110)
        self._iot_baseline_table.setColumnWidth(2, 145)
        self._iot_baseline_table.setColumnWidth(3, 150)
        self._iot_baseline_table.setColumnWidth(4, 60)
        self._iot_baseline_table.setColumnWidth(5, 70)
        self._iot_baseline_table.setColumnWidth(6, 65)

        # Live alert table
        alerts_lbl = QLabel("Live Anomaly Alerts")
        alerts_lbl.setStyleSheet(f"color:{ACCENT_LITE};font-size:12px;font-weight:bold;padding:6px 0 2px 0;")
        self._iot_alert_table = _table([
            "Time", "Device", "Alert Type", "Severity", "Detail", "Remediation", "Action"
        ])
        self._iot_alert_table.setColumnWidth(0, 75)
        self._iot_alert_table.setColumnWidth(1, 170)
        self._iot_alert_table.setColumnWidth(2, 130)
        self._iot_alert_table.setColumnWidth(3, 75)
        self._iot_alert_table.setColumnWidth(4, 300)
        self._iot_alert_table.setColumnWidth(5, 180)
        self._iot_alert_table.setColumnWidth(6, 110)

        lay.addWidget(info)
        lay.addWidget(self._iot_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._iot_baseline_table)
        lay.addWidget(alerts_lbl)
        lay.addWidget(self._iot_alert_table, 1)

        self._iot_monitor_obj = None
        return w

    def _populate_iot_baseline_table(self, baselines: dict) -> None:
        from PyQt6.QtGui import QColor
        self._iot_baseline_table.setRowCount(0)
        for mac, b in baselines.items():
            row = self._iot_baseline_table.rowCount()
            self._iot_baseline_table.insertRow(row)
            label = b.model or b.vendor or mac
            for col, val in enumerate([
                label, b.ip, mac, b.device_type,
                str(len(b.known_ips)), str(len(b.known_ports)),
                f"{b.avg_pps:.1f}", b.learned_at[:10] if b.learned_at else "—",
            ]):
                self._iot_baseline_table.setItem(row, col, QTableWidgetItem(str(val)))

    @pyqtSlot()
    def _run_iot_learn(self):
        if not self._m1_result:
            self._iot_status.setText("⚠ Run 'Devices on Network' scan first.")
            return
        devices = self._m1_result.get("devices", [])
        duration = self._iot_learn_duration.value()
        self._iot_status.setText(f"Learning for {duration} s — keep devices active…")
        try:
            from modules.iot_baseline import learn
            from pathlib import Path
            def _do_learn():
                baselines = learn(
                    devices=devices, duration_s=duration,
                    progress_cb=lambda m: self._iot_status.setText(m),
                )
                self._populate_iot_baseline_table(baselines)
                self._iot_status.setText(
                    f"Baseline learned for {len(baselines)} IoT device(s). "
                    "Click 'Start Anomaly Monitor' to watch for deviations."
                )
            import threading
            threading.Thread(target=_do_learn, daemon=True).start()
        except Exception as exc:
            self._iot_status.setText(f"⚠ Learn failed: {exc}")

    @pyqtSlot()
    def _run_iot_monitor(self):
        try:
            from modules.iot_baseline import load_or_create, IoTMonitor
            from PyQt6.QtGui import QColor
            import time

            if not self._m1_result:
                self._iot_status.setText("⚠ Run 'Devices on Network' scan first.")
                return

            devices = self._m1_result.get("devices", [])

            def _start():
                baselines = load_or_create(
                    devices=devices,
                    progress_cb=lambda m: self._iot_status.setText(m),
                )
                if not baselines:
                    self._iot_status.setText("⚠ No IoT baselines — run Learn first.")
                    return
                self._populate_iot_baseline_table(baselines)

                _IOT_INVESTIGATE_TARGET = {
                    "SYN_SCAN":       "Port Scan (TCP)",
                    "NEW_PORT":       "Port Scan (TCP)",
                    "NEW_DEST":       "Threat Intel",
                    "METADATA_PROBE": "Cloud Metadata Probe",
                    "RATE_SPIKE":     "Live Bandwidth",
                }

                def _on_alert(alert):
                    row = self._iot_alert_table.rowCount()
                    self._iot_alert_table.insertRow(row)
                    sev_color = RED if alert.severity == "CRITICAL" else (AMBER if alert.severity == "HIGH" else BLUE)
                    for col, val in enumerate([
                        alert.timestamp[11:19], alert.device_label,
                        alert.alert_type.replace("_", " ").title(),
                        alert.severity, alert.detail, alert.remediation,
                    ]):
                        item = QTableWidgetItem(str(val))
                        if col in (2, 3):
                            item.setForeground(QColor(sev_color))
                        self._iot_alert_table.setItem(row, col, item)
                    target = _IOT_INVESTIGATE_TARGET.get(alert.alert_type, "Devices")
                    inv_btn = QPushButton("Investigate →")
                    inv_btn.setFlat(True)
                    inv_btn.setStyleSheet(f"color:{ACCENT_LITE};font-size:11px;text-align:left;padding:2px 4px;")
                    inv_btn.clicked.connect(lambda _checked, t=target: self._nav_rail_go_to(t))
                    self._iot_alert_table.setCellWidget(row, 6, inv_btn)
                    self._iot_alert_table.scrollToBottom()
                    self._iot_status.setText(
                        f"⚠ Alert: {alert.alert_type} on {alert.device_label}"
                    )

                self._iot_monitor_obj = IoTMonitor(
                    baselines=baselines,
                    on_alert=_on_alert,
                    on_error=lambda m: self._iot_status.setText(f"⚠ {m}"),
                )
                self._iot_monitor_obj.start()
                self._iot_status.setText(
                    f"Monitoring {len(baselines)} IoT device(s) — watching for anomalies…"
                )

            import threading
            threading.Thread(target=_start, daemon=True).start()

        except Exception as exc:
            self._iot_status.setText(f"⚠ Monitor failed: {exc}")

    @pyqtSlot()
    def _stop_iot_monitor(self):
        if self._iot_monitor_obj:
            self._iot_monitor_obj.stop()
            self._iot_monitor_obj = None
            self._iot_status.setText("Anomaly monitor stopped.")

    # ── Network Grade (Benchmark) tab ─────────────────────────────────────────

    def _build_benchmark_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QStackedWidget as _SW
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        # Content stack: page 0 = empty state, page 1 = grade content
        self._bm_stack = _SW()

        # ── Page 0: empty state ────────────────────────────────────────────────
        _empty_w = QWidget()
        _el = QVBoxLayout(_empty_w)
        _el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _el.setSpacing(10)
        _el.setContentsMargins(40, 60, 40, 60)

        _icon_lbl = QLabel("◎")
        _icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _icon_lbl.setStyleSheet(
            f"font-size:48px; color:{BORDER_MED}; background:transparent; border:none;"
        )
        _desc_lbl = QLabel(
            "Grade your network across 8 health dimensions — Uptime, Latency, Jitter, "
            "DNS Speed, Download Speed, Device Safety, STP Health, and Broadcast Storm Level — "
            "compared against a perfect home network baseline."
        )
        _desc_lbl.setWordWrap(True)
        _desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _desc_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none; max-width:520px;"
        )
        _btn_scan_grade = QPushButton("◎  Scan & Grade")
        _btn_scan_grade.setObjectName("btnScan")
        _btn_scan_grade.setFixedHeight(36)
        _btn_scan_grade.clicked.connect(self._scan_and_grade)
        _el.addWidget(_icon_lbl)
        _el.addSpacing(4)
        _el.addWidget(_desc_lbl)
        _el.addSpacing(12)
        _el.addWidget(_btn_scan_grade, alignment=Qt.AlignmentFlag.AlignCenter)
        self._bm_stack.addWidget(_empty_w)

        # ── Page 1: grade content ──────────────────────────────────────────────
        _content_w = QWidget()
        _cl = QVBoxLayout(_content_w)
        _cl.setContentsMargins(0, 0, 0, 0)
        _cl.setSpacing(6)

        info = QLabel(
            "Compares your network against a 'Perfect Home Network' baseline and gives "
            "an A–F letter grade across Uptime, Latency, Jitter, DNS Speed, Download Speed, "
            "Device Safety, STP Health, and Broadcast Storm Level."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        # Grade display
        grade_row = QHBoxLayout()
        self._bm_grade_label = QLabel("—")
        self._bm_grade_label.setFixedSize(90, 90)
        self._bm_grade_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._bm_grade_label.setStyleSheet(
            "font-size:40px; font-weight:bold; border-radius:45px; "
            f"background:{BG_CARD}; border:3px solid {BORDER}; color:{TEXT_PRIMARY};"
        )
        self._bm_score_label = QLabel("Score: —")
        self._bm_score_label.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:16px; font-weight:bold;"
        )
        self._bm_verdict_label = QLabel("Click Grade My Network to score your connection.")
        self._bm_verdict_label.setWordWrap(True)
        self._bm_verdict_label.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; max-width:500px;"
        )
        grade_text = QVBoxLayout()
        grade_text.addWidget(self._bm_score_label)
        grade_text.addWidget(self._bm_verdict_label)
        grade_row.addWidget(self._bm_grade_label)
        grade_row.addSpacing(16)
        grade_row.addLayout(grade_text)
        grade_row.addStretch()

        ctrl = QHBoxLayout()
        btn_grade = QPushButton("◎  Grade My Network")
        btn_grade.setObjectName("btnScan")
        btn_grade.setToolTip("Score your network health across all available dimensions.")
        btn_grade.clicked.connect(self._run_benchmark)
        btn_isp = QPushButton("⊟  Network Health Report")
        btn_isp.setObjectName("btnNetRefresh")
        btn_isp.setToolTip(
            "Export a Network Health Report — hop table, outages, grade — "
            "as HTML you can print to PDF and attach to an ISP support ticket."
        )
        btn_isp.clicked.connect(self._export_isp_report)
        ctrl.addWidget(btn_grade)
        ctrl.addWidget(btn_isp)
        ctrl.addStretch()

        # Dimension breakdown table
        self._bm_table = _table(["Dimension", "Grade", "Your Value", "Ideal", "Verdict", "Fix Tip"])
        self._bm_table.setColumnWidth(0, 190)
        self._bm_table.setColumnWidth(1, 50)
        self._bm_table.setColumnWidth(2, 100)
        self._bm_table.setColumnWidth(3, 90)
        self._bm_table.setColumnWidth(4, 280)

        _cl.addWidget(info)
        _cl.addLayout(grade_row)
        _cl.addSpacing(6)
        _cl.addLayout(ctrl)
        _cl.addWidget(self._bm_table, 1)
        self._bm_stack.addWidget(_content_w)

        lay.addWidget(self._bm_stack, 1)
        return w

    @pyqtSlot()
    def _scan_and_grade(self):
        """Empty-state CTA: start a full scan then auto-grade when done."""
        self._bm_stack.setCurrentIndex(1)
        self._bm_verdict_label.setText("Scanning your network…")
        self._pending_benchmark = True
        self._start_full_scan()

    @pyqtSlot()
    def _run_benchmark(self):
        self._bm_stack.setCurrentIndex(1)
        from PyQt6.QtGui import QColor
        try:
            from modules.network_benchmark import grade as bm_grade

            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass

            result = bm_grade(
                log_summary=log_summary,
                diag_result=self._diag_result,
                m1_result=self._m1_result,
                m2_result=self._m2_result,
                m3_result=self._m3_result,
            )
            self._last_benchmark_result = result
            try:
                self._store.record_grade(result.overall_grade, result.overall_score, result.overall_verdict)
            except Exception:
                pass

            # Update grade circle
            grade_styles = {
                "A": (GREEN,       GRADE_A_BG),
                "B": (GRADE_B_FG,  GRADE_B_BG),
                "C": (AMBER,       GRADE_C_BG),
                "D": (RED,         GRADE_D_BG),
                "F": (GRADE_F_FG,  GRADE_F_BG),
                "N/A": (TEXT_SECONDARY, BG_CARD),
            }
            fg, bg = grade_styles.get(result.overall_grade, (TEXT_SECONDARY, BG_CARD))
            self._bm_grade_label.setText(result.overall_grade)
            self._bm_grade_label.setStyleSheet(
                f"font-size:40px; font-weight:bold; border-radius:45px; "
                f"background:{bg}; border:3px solid {fg}; color:{fg};"
            )
            self._bm_score_label.setText(f"Score: {result.overall_score:.0f}/100")
            self._bm_score_label.setStyleSheet(f"color:{fg}; font-size:16px; font-weight:bold;")
            self._bm_verdict_label.setText(result.overall_verdict)
            self._overview_page.on_grade(result.overall_grade, result.overall_score)
            self._home_page.on_grade(result.overall_grade, result.overall_score)
            self._home_page.on_grade_details(result.overall_grade, result.overall_score,
                                             getattr(result, "dimensions", []))
            if hasattr(self._home_page, "_update_this_week"):
                self._home_page._update_this_week()
            if hasattr(self, "_monitor_overview_page"):
                self._monitor_overview_page.set_grade(result.overall_grade, result.overall_score)
                self._monitor_overview_page.set_grade_details(result.overall_grade,
                                                              result.overall_score,
                                                              getattr(result, "dimensions", []))
            QSettings("NetSentinel", "NetSentinel").setValue("grade/last_run", True)
            self._home_page.refresh_checklist()
            from modules.diagnostic_card import build_card_data
            self._overview_page.set_card_data(
                build_card_data(result, self._diag_result, self._store)
            )
            if hasattr(self, "_tray_manager") and self._tray_manager:
                self._tray_manager.set_grade(result.overall_grade)

            _GRADE_FIX_TARGET = {
                "Connection Uptime":          "Availability History",
                "Average Latency":            "DNS & Stability",
                "Jitter (Call Quality)":      "DNS & Stability",
                "DNS Response Speed":         "DNS & Stability",
                "Download Speed":             "Speed Test",
                "Network Device Safety":      "Devices",
                "Spanning Tree (STP) Health": "Rogue Bridge (STP)",
                "Broadcast Storm Level":      "Broadcast Storm",
            }
            # Populate dimension table
            self._bm_table.setRowCount(0)
            for d in result.dimensions:
                row = self._bm_table.rowCount()
                self._bm_table.insertRow(row)
                grade_color = {
                    "A": GREEN, "B": GRADE_B_FG, "C": AMBER, "D": RED, "F": GRADE_F_FG
                }.get(d.grade, TEXT_SECONDARY)
                for col, val in enumerate([
                    d.name, d.grade, d.value_label, d.ideal_label, d.verdict, d.tip
                ]):
                    item = QTableWidgetItem(str(val))
                    if col == 1:
                        item.setForeground(QColor(grade_color))
                    self._bm_table.setItem(row, col, item)
                if d.grade in ("D", "F"):
                    target = _GRADE_FIX_TARGET.get(d.name)
                    if target:
                        fix_btn = QPushButton(f"Fix this →")
                        fix_btn.setFlat(True)
                        fix_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                        fix_btn.setStyleSheet(
                            f"QPushButton{{color:{ACCENT};font-size:10px;background:transparent;"
                            f"border:none;text-align:left;padding:0 4px;}}"
                            f"QPushButton:hover{{color:{ACCENT_DARK};}}"
                        )
                        fix_btn.clicked.connect(
                            lambda _checked, t=target: self._nav_rail_go_to(t)
                        )
                        self._bm_table.setCellWidget(row, 5, fix_btn)

        except Exception as exc:
            self._bm_verdict_label.setText(f"⚠ Grading failed: {exc}")

    @pyqtSlot()
    def _export_isp_report(self):
        if self._m1_result is None and getattr(self, "_diag_result", None) is None:
            self._bm_stack.setCurrentIndex(1)
            self._bm_verdict_label.setText("Running diagnostics to build the ISP report…")
            self._pending_isp_report = True
            self._start_diagnostics()
            return

        try:
            from modules.report_exporter import save_isp_report
            from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit as _QLE

            # Collect optional ISP name & account ref from user
            dlg = QDialog(self)
            dlg.setWindowTitle("Network Health Report — Optional Details")
            dlg.setMinimumWidth(380)
            dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
            form = QFormLayout(dlg)
            isp_edit = _QLE()
            isp_edit.setPlaceholderText("e.g. BT, Virgin Media, Comcast…")
            isp_edit.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; border-radius:4px; padding:4px;")
            ref_edit = _QLE()
            ref_edit.setPlaceholderText("e.g. REF-123456 (optional)")
            ref_edit.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; border-radius:4px; padding:4px;")
            form.addRow("ISP Name:", isp_edit)
            form.addRow("Account / Ticket Ref:", ref_edit)
            btns = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
            )
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            form.addRow(btns)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return

            isp_name   = isp_edit.text().strip()
            account_ref = ref_edit.text().strip()

            # Gather data
            log_summary = None
            if self._logger_worker:
                try:
                    log_summary = self._logger_worker.get_summary()
                except Exception:
                    pass
            bm_result = getattr(self, "_last_benchmark_result", None)

            # Pick save path
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"ISP_Report_{ts}.html"
            docs_dir = Path.home() / "Documents" / "NetSentinel" / "reports"
            docs_dir.mkdir(parents=True, exist_ok=True)
            path_str, _ = QFileDialog.getSaveFileName(
                self, "Save Network Health Report", str(docs_dir / default_name),
                "HTML Report (*.html);;All Files (*)"
            )
            if not path_str:
                return

            out = save_isp_report(
                output_path=Path(path_str),
                log_summary=log_summary,
                diag_result=self._diag_result,
                benchmark_result=bm_result,
                m1_result=self._m1_result,
                isp_name=isp_name,
                account_ref=account_ref,
            )
            webbrowser.open(out.as_uri())
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Network Health Report Error", str(exc))

    # ── How to Fix dialog (shared by M1 / M2 / M3 context menus) ─────────────

    def _show_how_to_fix(self, title: str, remediation: str):
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QScrollArea as _SA

        dlg = QDialog(self)
        dlg.setWindowTitle(f"How to Fix — {title}")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
        lay = QVBoxLayout(dlg)

        heading = QLabel(f"<b>Remediation steps for: {title}</b>")
        heading.setStyleSheet(f"color:{ACCENT_LITE}; font-size:13px; padding-bottom:4px;")
        heading.setWordWrap(True)
        lay.addWidget(heading)

        # Split on ". " or "\\n" for numbered steps
        import re
        raw = remediation.strip() if remediation else "No specific fix information available."
        parts = [p.strip() for p in re.split(r'\. (?=[A-Z0-9])', raw) if p.strip()]
        if len(parts) <= 1 and "\n" in raw:
            parts = [p.strip() for p in raw.split("\n") if p.strip()]

        steps_html = ""
        for i, step in enumerate(parts, 1):
            s = html.escape(step)
            if not s.endswith("."):
                s += "."
            steps_html += f"<li style='margin-bottom:8px'><b>Step {i}:</b> {s}</li>"
        if not steps_html:
            steps_html = f"<li>{html.escape(raw)}</li>"

        txt = QLabel(f"<ol style='padding-left:18px;line-height:1.8'>{steps_html}</ol>")
        txt.setWordWrap(True)
        txt.setTextFormat(Qt.TextFormat.RichText)
        txt.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:12px; padding:4px;")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.addWidget(txt)
        inner_lay.addStretch()
        scroll.setWidget(inner)
        scroll.setStyleSheet(f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0px;")
        scroll.setMinimumHeight(160)

        lay.addWidget(scroll, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.accept)
        lay.addWidget(btns)
        dlg.exec()

    # ── Window lifecycle ──────────────────────────────────────────────────────

    def _quit_app(self):
        """Unconditional quit — bypasses minimize-to-tray logic."""
        self._tray_quit = True
        self.close()

    def closeEvent(self, event):
        """X button hides to tray (app keeps monitoring). Quit via ⚙ menu or Ctrl+Q to exit."""
        if (not self._tray_quit
                and self._tray_manager.is_available()
                and self._tray_manager.minimize_to_tray_enabled()):
            event.ignore()
            self._tray_manager._hide_window()
            self._tray_manager.show_notification(
                "NetSentinel",
                "Still monitoring in the system tray — use ⚙ › Quit to exit.",
                "INFO",
            )
            return

        # ── Real shutdown path ────────────────────────────────────────────────
        self._save_window_state()

        # Collect every worker the dashboard owns into one flat list
        _all_workers = []
        # Transient/one-shot workers
        for attr in ("_net_info_worker", "_diag_worker", "_prescan_worker",
                     "_mtr_worker", "_ps_worker", "_ipv6_worker", "_cloud_worker",
                     "_arp_worker", "_dhcp_worker", "_bw_worker", "_sched_worker",
                     "_snmp_worker", "_syn_worker", "_udp_worker", "_cve_worker",
                     "_exposure_worker", "_os_worker", "_cred_worker",
                     "_discovery_worker", "_smb_worker", "_pe_worker",
                     "_plugin_worker"):
            w = getattr(self, attr, None)
            if w is not None:
                _all_workers.append(w)
        # Workers tracked in self._workers (scan module workers)
        _all_workers.extend(list(self._workers))

        # Signal stop to every running worker first (non-blocking)
        for w in _all_workers:
            if w.isRunning():
                if hasattr(w, "stop"):
                    w.stop()
                elif hasattr(w, "stop_logger"):
                    w.stop_logger()
                else:
                    w.quit()  # ask the event loop to exit

        # Stop the persistent logger worker
        if self._logger_worker and self._logger_worker.isRunning():
            self._logger_worker.stop_logger()
            _all_workers.append(self._logger_worker)

        # Wait briefly for each worker — 800 ms cap so close is responsive
        for w in _all_workers:
            if w.isRunning():
                w.wait(800)
            if w.isRunning():
                w.terminate()
                w.wait(2000)   # wait after terminate before object destruction

        super().closeEvent(event)
        # os._exit(0) bypasses Qt destructor cleanup entirely.
        # This is intentional: calling QApplication.quit() after terminate()
        # can still trigger QThread destructor crashes (STATUS_STACK_BUFFER_OVERRUN)
        # if a thread's OS handle is not yet released. os._exit(0) skips all
        # C++/Qt destructors and exits the process cleanly at the OS level.
        import os as _os
        _os._exit(0)

    # ── Verdict area ─────────────────────────────────────────────────────────

    def _build_verdict_area(self) -> QWidget:
        """Compact verdict strip at bottom — thin, doesn't waste screen space."""
        w = QWidget()
        w.setStyleSheet(
            f"background:{BG_CARD}; border-top:1px solid {BORDER};"
        )
        lay = QHBoxLayout(w)
        lay.setContentsMargins(12, 4, 12, 4)
        lay.setSpacing(0)

        self._verdict = VerdictPanel()
        lay.addWidget(self._verdict, 1)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _stat_label(self, title: str, value: str) -> QFrame:
        """KPI card: coloured left border, label above, large number below."""
        frame = QFrame()
        frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER};"
            f"border-left:3px solid {ACCENT}; border-radius:3px;"
        )
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(10, 6, 10, 6)
        fl.setSpacing(1)
        t = QLabel(title.upper())
        t.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:9px; font-weight:bold; letter-spacing:0.5px;"
        )
        v = QLabel(value)
        v.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;")
        v.setObjectName(f"stat_{title.replace('/','_').replace(' ','_')}")
        fl.addWidget(t)
        fl.addWidget(v)
        return frame

    def _find_stat_value(self, frame: QFrame) -> Optional[QLabel]:
        for child in frame.findChildren(QLabel):
            if child.objectName().startswith("stat_"):
                return child
        return None

    def _update_stat(self, frame: QFrame, value: str, color: str = TEXT_PRIMARY):
        lbl = self._find_stat_value(frame)
        if lbl:
            lbl.setText(value)
            lbl.setStyleSheet(f"color:{color};font-size:18px;font-weight:bold;")

    def _set_status(self, msg: str):
        self._status_bar.showMessage(f"  {msg}")

    def _refresh_pulse_bar(self) -> None:
        """Update the four permanent status-bar indicators (called every 10 s)."""
        import time as _t

        _muted  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {TEXT_MUTED}; }} QLabel:hover {{ color: #FFFFFF; }}"
        _green  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {GREEN}; }} QLabel:hover {{ color: #FFFFFF; }}"
        _amber  = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {AMBER}; }} QLabel:hover {{ color: #FFFFFF; }}"
        _red    = f"QLabel {{ padding: 0 8px; font-size: 11px; background: transparent; border: none; color: {RED}; }} QLabel:hover {{ color: #FFFFFF; }}"

        # Online / Offline
        status = self._last_log_status
        if status == "OK":
            self._pulse_online_lbl.setText("●  Online")
            self._pulse_online_lbl.setStyleSheet(_green)
        elif status == "SLOW":
            self._pulse_online_lbl.setText("●  Slow")
            self._pulse_online_lbl.setStyleSheet(_amber)
        elif status == "FAIL":
            self._pulse_online_lbl.setText("●  Offline")
            self._pulse_online_lbl.setStyleSheet(_red)
        else:
            self._pulse_online_lbl.setText("○  —")
            self._pulse_online_lbl.setStyleSheet(_muted)

        # Device count
        n = len(self._last_scan_devices)
        if n > 0:
            self._pulse_devices_lbl.setText(f"■  {n} device{'s' if n != 1 else ''}")
        else:
            self._pulse_devices_lbl.setText("■  —")
        self._pulse_devices_lbl.setStyleSheet(_muted)

        # Last scan age
        if self._last_scan_time > 0:
            elapsed = _t.time() - self._last_scan_time
            if elapsed < 60:
                age = "just now"
            elif elapsed < 3600:
                age = f"{int(elapsed // 60)}m ago"
            else:
                age = f"{int(elapsed // 3600)}h ago"
            self._pulse_scan_lbl.setText(f"Last scan: {age}")
        else:
            self._pulse_scan_lbl.setText("Last scan: —")
        self._pulse_scan_lbl.setStyleSheet(_muted)

        # Logger status
        logging_on = bool(self._logger_worker and self._logger_worker.isRunning())
        if logging_on:
            self._pulse_logger_lbl.setText("⏺  Logging")
            self._pulse_logger_lbl.setStyleSheet(_green)
        else:
            self._pulse_logger_lbl.setText("○  Logger off")
            self._pulse_logger_lbl.setStyleSheet(_muted)

    def _show_alert_toast(self, alert) -> None:
        """Show a desktop notification for a fired alert."""
        from ui.styles import RED, AMBER
        severity = getattr(alert, "severity", "INFO")
        message  = getattr(alert, "message",  str(alert))

        # Update status bar regardless
        prefix = "🔴" if severity == "CRITICAL" else "🟡"
        self._set_status(f"{prefix} {message}")

        # Desktop toast via tray manager
        if self._tray_manager.is_available():
            self._tray_manager.show_notification("NetSentinel Alert", message, severity)
            self._tray_manager.increment_badge()
        elif self._tray_icon is not None:
            # Legacy fallback (should never be reached after tray_manager setup)
            from PyQt6.QtWidgets import QSystemTrayIcon
            icon_type = (
                QSystemTrayIcon.MessageIcon.Critical
                if severity == "CRITICAL"
                else QSystemTrayIcon.MessageIcon.Warning
            )
            self._tray_icon.showMessage("NetSentinel Alert", message, icon_type, 5000)



    # ── Global time range (TIME-1) ────────────────────────────────────────────

    def _on_global_time_changed(self, text: str) -> None:
        mapping = {"1h": 1.0, "6h": 6.0, "24h": 24.0, "7d": 168.0, "30d": 720.0}
        hours = mapping.get(text, 24.0)
        self._global_hours = hours
        self.global_time_range_changed.emit(hours)

    def _set_global_time_combo(self, hours: float) -> None:
        """Sync the title bar combo to a given hours value (used by TIME-2 jump)."""
        reverse = {1.0: "1h", 6.0: "6h", 24.0: "24h", 168.0: "7d", 720.0: "30d"}
        text = reverse.get(hours)
        if text and hasattr(self, "_time_range_combo"):
            self._time_range_combo.blockSignals(True)
            self._time_range_combo.setCurrentText(text)
            self._time_range_combo.blockSignals(False)

    # ── DEVICE-1: popover navigation handlers ────────────────────────────────

    def _on_popover_open_inventory(self, ip_or_mac: str) -> None:
        self._nav_rail_go_to("Inventory Changes")
        if hasattr(self, "_inventory_page"):
            self._inventory_page.select_device(ip_or_mac)

    def _on_popover_open_threat_intel(self, ip: str) -> None:
        self._nav_rail_go_to("Threat Intelligence")
        if hasattr(self, "_threat_intel_page") and ip:
            self._threat_intel_page.check_ip(ip)

    # ── TIME-2: View in Log Hub from alert drawer ─────────────────────────────

    def _on_view_alert_in_log_hub(self, alert_ts: float, source_key: str) -> None:
        self._nav_rail_go_to("Network Logger")
        if hasattr(self, "_log_hub_page"):
            self._log_hub_page.jump_to_alert_time(alert_ts, source_key)

    @pyqtSlot(str, str)
    def _on_automation_rule_requested(self, rule_name: str, match_value: str) -> None:
        self._nav_rail_go_to("Automation Hooks")
        if hasattr(self, "_automation_page"):
            self._automation_page.prefill_rule(rule_name, match_value)

    # ── SCHED-3: monitor persistence ──────────────────────────────────────────

    _MONITOR_KEYS = {
        "arp":       "_arp_worker",
        "bandwidth": "_bw_worker",
        "scheduler": "_sched_worker",
    }

    def _save_monitor_state(self, key: str, running: bool) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        saved = set(qs.value("monitors/was_running", "", type=str).split(",")) - {""}
        if running:
            saved.add(key)
        else:
            saved.discard(key)
        qs.setValue("monitors/was_running", ",".join(sorted(saved)))

    def _restore_running_monitors(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        keys = set(qs.value("monitors/was_running", "", type=str).split(",")) - {""}
        if "arp" in keys and not (self._arp_worker and self._arp_worker.isRunning()):
            self._start_arp_monitor()
        if "bandwidth" in keys and not (self._bw_worker and self._bw_worker.isRunning()):
            self._start_bandwidth_monitor()
        if "scheduler" in keys and not (self._sched_worker and self._sched_worker.isRunning()):
            self._start_scheduler()

    def _set_scanning(self, scanning: bool):
        self._btn_scan.setEnabled(not scanning)
        if hasattr(self, "_header_scan_btn"):
            self._header_scan_btn.setEnabled(not scanning)
        if hasattr(self, "_home_page"):
            self._home_page.set_scanning(scanning)
        if hasattr(self, "_overview_page"):
            self._overview_page.set_scanning(scanning)
        self._progress.setVisible(scanning)
        # Update KPI scan-status tile
        if scanning:
            self._kpi_scan_val.setText("Scanning…")
            self._kpi_scan_dot.setStyleSheet(
                f"color:{ACCENT}; font-size:9px; background:transparent; border:none;"
            )
            self._kpi_scan_val.setStyleSheet(
                f"color:{ACCENT}; font-size:18px; font-weight:bold;"
                "background:transparent; border:none;"
            )
        if not scanning:
            _has_results = any(x is not None for x in [
                self._m1_result, self._m2_result, self._m3_result,
                self._m4_result, self._m5_result
            ])
            self._btn_export.setEnabled(_has_results)
            if hasattr(self, "_overview_page"):
                self._overview_page.set_export_enabled(_has_results)
                if not self._auto_report_pending:
                    self._overview_page.set_report_running(False)

    # ── Shared copy-to-clipboard for tables ──────────────────────────────────

    @staticmethod
    def _enable_copy_menu(table: QTableWidget):
        """Wire a right-click 'Copy row' action to any QTableWidget."""
        from PyQt6.QtCore import Qt as _Qt
        table.setContextMenuPolicy(_Qt.ContextMenuPolicy.CustomContextMenu)

        def _show_menu(pos):
            from PyQt6.QtWidgets import QMenu as _QMenu
            from PyQt6.QtGui import QClipboard as _QClipboard
            from PyQt6.QtWidgets import QApplication as _QApp
            rows_selected = sorted({i.row() for i in table.selectedIndexes()})
            if not rows_selected:
                return
            menu = _QMenu(table)
            act_row  = menu.addAction("Copy selected row(s)")
            act_cell = menu.addAction("Copy selected cell")
            chosen = menu.exec(table.viewport().mapToGlobal(pos))
            if chosen == act_row:
                lines = []
                for r in rows_selected:
                    parts = [
                        (table.item(r, c).text() if table.item(r, c) else "")
                        for c in range(table.columnCount())
                    ]
                    lines.append("\t".join(parts))
                _QApp.clipboard().setText("\n".join(lines))
            elif chosen == act_cell:
                item = table.currentItem()
                if item:
                    _QApp.clipboard().setText(item.text())

        table.customContextMenuRequested.connect(_show_menu)

    # ── Window state persistence ──────────────────────────────────────────────

    @staticmethod
    def _settings_path() -> "Path":
        """
        Return the path to NetSentinel.ini.

        Priority:
          1. Same directory as the running executable / script (portable use —
             settings travel with the exe on a USB stick or shared folder).
          2. Fallback: ~/.config/NetSentinel/NetSentinel.ini (if the exe dir
             is not writable, e.g. installed in Program Files).
        """
        import sys as _sys
        exe_dir = Path(_sys.executable).parent if getattr(_sys, "frozen", False) \
            else Path(__file__).resolve().parent.parent
        candidate = exe_dir / "NetSentinel.ini"
        try:
            # Quick write-test
            candidate.touch(exist_ok=True)
            return candidate
        except OSError:
            fallback = Path.home() / ".config" / "NetSentinel" / "NetSentinel.ini"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            return fallback

    def _save_settings(self):
        from PyQt6.QtCore import QSettings
        s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        # Window geometry (save maximized state separately — restoreGeometry alone
        # is unreliable for frameless windows before show() is called)
        s.setValue("window/geometry", self.saveGeometry().toBase64().data().decode())
        s.setValue("window/maximized", str(self.isMaximized()))
        # Persist the pre-maximize size so the next startup restores correctly.
        if self.isMaximized() and self._pre_maximize_geo is not None:
            r = self._pre_maximize_geo
            s.setValue("window/normal_x", r.x())
            s.setValue("window/normal_y", r.y())
            s.setValue("window/normal_width", r.width())
            s.setValue("window/normal_height", r.height())
        # Sidebar nav state
        s.setValue("nav/collapsed", str(self._nav_collapsed))
        s.setValue("nav/mode", self._nav_mode)
        for _hrow, _grp in self._nav_section_groups.items():
            if _grp["level"] == 0:
                s.setValue(f"nav/section_{_hrow}_collapsed", str(_grp["collapsed"]))
        if hasattr(self, "_ps_host"):
            s.setValue("scan/last_port_scan_host", self._ps_host.text())
        if hasattr(self, "_ps_mode"):
            s.setValue("scan/port_scan_mode", self._ps_mode.currentText())
        if hasattr(self, "_syn_host"):
            s.setValue("scan/last_syn_host", self._syn_host.text())
        if hasattr(self, "_syn_ports_combo"):
            s.setValue("scan/syn_port_range", self._syn_ports_combo.currentText())
        if hasattr(self, "_syn_rate"):
            s.setValue("scan/syn_rate_pps", self._syn_rate.value())
        if hasattr(self, "_udp_host"):
            s.setValue("scan/last_udp_host", self._udp_host.text())
        s.sync()

    def _restore_settings(self):
        from PyQt6.QtCore import QSettings
        from PyQt6.QtCore import QByteArray
        s = QSettings(str(self._settings_path()), QSettings.Format.IniFormat)
        # Window geometry
        geom_b64 = s.value("window/geometry", "")
        was_maximized = s.value("window/maximized", "False") == "True"
        # Fresh-install fallback — prevents starting maximized with no saved geometry.
        self.resize(1280, 800)
        if was_maximized:
            # Do NOT call restoreGeometry() here — when saved while maximized the
            # geometry bytes represent the full-screen rect, which would become
            # Qt's internal "restore geometry."  showNormal() would then restore
            # to a full-screen-sized-but-not-maximised window (the reported bug).
            # Instead, set a sensible normal size first so showNormal() snaps back
            # to something reasonable, then enter the maximised state.
            nx = s.value("window/normal_x")
            ny = s.value("window/normal_y")
            nw = s.value("window/normal_width", "1280")
            nh = s.value("window/normal_height", "800")
            try:
                if nx is not None and ny is not None:
                    self.setGeometry(int(nx), int(ny), int(nw), int(nh))
                else:
                    self.resize(int(nw), int(nh))
            except (ValueError, TypeError):
                self.resize(1280, 800)
            self.showMaximized()
        elif geom_b64:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geom_b64.encode()))
            except Exception:
                pass
        # Sidebar nav state
        if s.value("nav/collapsed", "False") == "True" and not self._nav_collapsed:
            self._toggle_sidebar()
        for _hrow in list(self._nav_section_groups.keys()):
            _grp = self._nav_section_groups[_hrow]
            if _grp["level"] == 0:
                # Top-level sections
                _saved = s.value(f"nav/section_{_hrow}_collapsed", None)
                if _saved is not None and (_saved == "True") != _grp["collapsed"]:
                    self._nav_toggle_section(_hrow)
            else:
                # Subgroups: restore saved preference; fall back to the group's own default
                _saved = s.value(f"nav/group_{_hrow}_collapsed", None)
                _want_collapsed = (_saved == "True") if _saved is not None else _grp["collapsed"]
                if _want_collapsed != _grp["collapsed"]:
                    self._nav_toggle_section(_hrow)
        if hasattr(self, "_ps_host"):
            host = s.value("scan/last_port_scan_host", "")
            if host:
                self._ps_host.setText(host)
        if hasattr(self, "_ps_mode"):
            mode = s.value("scan/port_scan_mode", "")
            if mode:
                idx = self._ps_mode.findText(mode)
                if idx >= 0:
                    self._ps_mode.setCurrentIndex(idx)
        if hasattr(self, "_syn_host"):
            syn_host = s.value("scan/last_syn_host", "")
            if syn_host:
                self._syn_host.setText(syn_host)
        if hasattr(self, "_syn_ports_combo"):
            syn_range = s.value("scan/syn_port_range", "")
            if syn_range:
                idx = self._syn_ports_combo.findText(syn_range)
                if idx >= 0:
                    self._syn_ports_combo.setCurrentIndex(idx)
        if hasattr(self, "_syn_rate"):
            rate = s.value("scan/syn_rate_pps", 500, type=int)
            self._syn_rate.setValue(rate)
        if hasattr(self, "_udp_host"):
            udp_host = s.value("scan/last_udp_host", "")
            if udp_host:
                self._udp_host.setText(udp_host)
        # Apply saved nav mode — must be last so sidebar is fully built
        _saved_mode = s.value("nav/mode", "home")
        if _saved_mode in ("home", "standard", "pro"):
            self._nav_mode = _saved_mode
        self._rebuild_nav_for_mode()

        # On first launch, default the logger to auto-start so monitoring begins immediately.
        _qs_app = QSettings("NetSentinel", "NetSentinel")
        if _qs_app.value("logger/auto_start") is None:
            _qs_app.setValue("logger/auto_start", True)
            if hasattr(self, "_log_chk_autostart"):
                self._log_chk_autostart.setChecked(True)

        # Auto-start stability logger if the user opted in (or on first launch)
        if _qs_app.value("logger/auto_start", True, type=bool):
            from PyQt6.QtCore import QTimer as _QTimer
            _QTimer.singleShot(1500, self._toggle_logger)

        # Retention helpers — run after the event loop is warm
        from PyQt6.QtCore import QTimer as _QT2
        _QT2.singleShot(2000, self._compute_last_visit_summary)
        _QT2.singleShot(4000, self._maybe_send_weekly_digest)

    # Keep old names as aliases so any external code still works
    def _save_window_state(self):
        self._save_settings()

    def _restore_window_state(self):
        self._restore_settings()

    # ── OUI database reload ───────────────────────────────────────────────────

    def _reload_oui_db(self):
        """Re-read offenders.json without restarting the app."""
        self._offenders_path = get_offenders_path()
        self._set_status("OUI vendor database reloaded.")

    def _reset_dismissed_notices(self) -> None:
        """Clear all permanently-dismissed banner QSettings keys and re-show banners."""
        qs = QSettings("NetSentinel", "NetSentinel")
        dismissed_keys = [k for k in qs.allKeys() if k.endswith("_dismissed")]
        for k in dismissed_keys:
            qs.remove(k)
        # Trigger re-evaluation of Npcap banner state on next show
        qs.remove("home/npcap_dismissed")
        if hasattr(self, "_home_page"):
            self._home_page.showEvent(None)
        self._set_status("All dismissed notices have been reset.")

    @pyqtSlot()
    def _on_run_first_time_setup(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("home/checklist_done", False)
        qs.setValue("home/scan_count", 0)
        self._nav_rail_go_to("Home")
        if hasattr(self, "_home_page"):
            self._home_page._recurring_mode = False
            self._home_page._set_first_run_mode(True)
            self._home_page.refresh_checklist()

    @pyqtSlot()
    def _on_export_all(self) -> None:
        from PyQt6.QtWidgets import QFileDialog as _QFD
        import time as _t
        default = f"netsentinel-export-{_t.strftime('%Y%m%d-%H%M%S')}.zip"
        path, _ = _QFD.getSaveFileName(
            self, "Export All Data", default, "ZIP Archives (*.zip)"
        )
        if not path:
            return
        try:
            from modules.exporter import export_all_zip
            from pathlib import Path as _P
            export_all_zip(self._store, _P(path))
            from ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(f"Export saved to {path}", "info")
        except Exception as exc:
            from PyQt6.QtWidgets import QMessageBox as _MB
            _MB.warning(self, "Export Failed", str(exc))

    # ── Topology tab ──────────────────────────────────────────────────────────

    def _build_topology_tab(self) -> QWidget:
        from ui.topology_widget import TopologyWidget
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lbl = QLabel("Network topology — run a Device Fingerprint scan first.")
        lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._topology_widget = TopologyWidget()
        lay.addWidget(lbl)
        lay.addWidget(self._topology_widget, 1)
        return w

    # ── ARP monitor tab ───────────────────────────────────────────────────────

    def _build_arp_monitor_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._arp_status = QLabel("ARP spoof monitor not running.")
        self._arp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Start ARP Monitor (30s)")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_arp_monitor)
        btn_row.addWidget(btn_start)
        btn_row.addStretch()
        self._arp_table = _table(["Type", "Attacker MAC", "Attacker IP", "Victim IP", "Original MAC", "Verdict"])
        self._arp_table.setColumnWidth(0, 110)
        self._arp_table.setColumnWidth(1, 145)
        self._arp_table.setColumnWidth(2, 120)
        self._arp_table.setColumnWidth(5, 400)
        # Empty state shown when monitor hasn't started / no events yet
        from PyQt6.QtWidgets import QStackedWidget as _SW
        self._arp_stack = _SW()
        self._arp_stack.addWidget(_empty_state_widget(
            "⊙", "ARP Watch not running",
            "Monitor your network for ARP spoofing and man-in-the-middle attacks.",
            "Start ARP Watch", self._start_arp_monitor,
        ))
        self._arp_stack.addWidget(self._arp_table)
        lay.addWidget(self._arp_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._arp_stack, 1)
        return w

    @pyqtSlot()
    def _start_arp_monitor(self):
        from workers.scan_worker import ARPMonitorWorker
        if self._arp_worker and self._arp_worker.isRunning():
            return
        self._arp_table.setRowCount(0)
        gateway_ip = self._net_info.get("gateway") if self._net_info else None
        self._arp_worker = ARPMonitorWorker(gateway_ip=gateway_ip, duration=30)
        self._arp_worker.event_found.connect(self._on_arp_event)
        self._arp_worker.result.connect(lambda r: self._arp_status.setText(r.plain_verdict), Qt.ConnectionType.QueuedConnection)
        self._arp_worker.status.connect(self._arp_status.setText)
        self._arp_worker.error.connect(lambda e: self._arp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._arp_worker.finished.connect(self._push_monitor_pills)
        self._arp_worker.start()
        self._arp_status.setText("ARP monitor started…")
        QSettings("NetSentinel", "NetSentinel").setValue("home/setup/arp_started", True)
        self._save_monitor_state("arp", True)
        self._push_monitor_pills()
        self._set_flyout_dot("ARP Spoof Watch", GREEN)

    @pyqtSlot(object)
    def _on_arp_event(self, event):
        self._arp_stack.setCurrentIndex(1)   # switch from empty state to table
        row = self._arp_table.rowCount()
        self._arp_table.insertRow(row)
        level = "HIGH" if event.event_type in ("GATEWAY_HIJACK",) else "MEDIUM"
        for col, val in enumerate([
            event.event_type, event.attacker_mac, event.attacker_ip,
            event.victim_ip, event.original_mac, event.verdict
        ]):
            item = QTableWidgetItem(str(val))
            item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                _color_for_level(level)
            ))
            self._arp_table.setItem(row, col, item)
        # Tray notification for ARP attacks
        if self._tray_manager.is_available():
            self._tray_manager.show_notification(
                f"ARP Attack Detected — {event.event_type.replace('_', ' ').title()}",
                f"{event.attacker_ip} ({event.attacker_mac}) → {event.verdict}",
                "CRITICAL" if level == "HIGH" else "WARNING",
            )
            self._tray_manager.increment_badge()

    # ── DHCP monitor tab ──────────────────────────────────────────────────────

    def _build_dhcp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._dhcp_status = QLabel("DHCP rogue server monitor not running.")
        self._dhcp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Send DHCP Discover")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_dhcp_scan)
        btn_row.addWidget(btn_start)
        btn_row.addStretch()
        self._dhcp_table = _table(["Server IP", "Server MAC", "Offered IP", "Gateway", "DNS", "Lease", "Rogue?", "Verdict"])
        self._dhcp_table.setColumnWidth(7, 400)
        lay.addWidget(self._dhcp_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._dhcp_table, 1)
        return w

    @pyqtSlot()
    def _start_dhcp_scan(self):
        from workers.scan_worker import DHCPDetectorWorker
        if self._dhcp_worker and self._dhcp_worker.isRunning():
            return
        self._dhcp_table.setRowCount(0)
        self._dhcp_worker = DHCPDetectorWorker(duration=10)
        self._dhcp_worker.offer_found.connect(self._on_dhcp_offer)
        self._dhcp_worker.result.connect(lambda r: self._dhcp_status.setText(r.plain_verdict), Qt.ConnectionType.QueuedConnection)
        self._dhcp_worker.status.connect(self._dhcp_status.setText)
        self._dhcp_worker.error.connect(lambda e: self._dhcp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._dhcp_worker.finished.connect(self._push_monitor_pills)
        self._dhcp_worker.start()
        self._dhcp_status.setText("DHCP discover sent — listening for offers…")
        self._push_monitor_pills()
        self._set_flyout_dot("DHCP Rogue Monitor", GREEN)

    @pyqtSlot(object)
    def _on_dhcp_offer(self, offer):
        row = self._dhcp_table.rowCount()
        self._dhcp_table.insertRow(row)
        level = "HIGH" if offer.is_rogue else "CLEAN"
        for col, val in enumerate([
            offer.server_ip, offer.server_mac, offer.offered_ip,
            offer.gateway, ", ".join(offer.dns_servers),
            f"{offer.lease_time}s", "YES ⚠" if offer.is_rogue else "No",
            offer.verdict,
        ]):
            item = QTableWidgetItem(str(val))
            item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                _color_for_level(level)
            ))
            self._dhcp_table.setItem(row, col, item)

    # ── Bandwidth tab ─────────────────────────────────────────────────────────

    def _build_bandwidth_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(NpcapMissingBanner(parent=w))
        self._bw_status = QLabel("Bandwidth monitor not running. Requires admin + Npcap.")
        self._bw_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        btn_row = QHBoxLayout()
        btn_start = QPushButton("▶  Start Bandwidth Monitor")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_bandwidth_monitor)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_bandwidth_monitor)
        btn_row.addWidget(btn_start)
        btn_row.addWidget(btn_stop)
        btn_row.addStretch()
        self._bw_table = _table(["MAC / Label", "TX (kbps)", "RX (kbps)", "Total (kbps)", "Total (Mbps)"])
        from PyQt6.QtWidgets import QStackedWidget as _SW2
        self._bw_stack = _SW2()
        self._bw_stack.addWidget(_empty_state_widget(
            "▲", "No traffic captured yet",
            "Start the bandwidth monitor to see per-device upload and download rates.",
            "Start Monitor", self._start_bandwidth_monitor,
        ))
        self._bw_stack.addWidget(self._bw_table)
        lay.addWidget(self._bw_status)
        lay.addLayout(btn_row)
        lay.addWidget(self._bw_stack, 1)
        return w

    @pyqtSlot()
    def _start_bandwidth_monitor(self):
        from workers.scan_worker import BandwidthWorker
        if self._bw_worker and self._bw_worker.isRunning():
            return
        # Build label map from M1 results if available
        label_map: dict = {}
        if self._m1_result:
            for d in self._m1_result.get("devices", []):
                mac = d.get("mac", "") if isinstance(d, dict) else (getattr(d, "mac", "") or "")
                host = d.get("hostname", "") if isinstance(d, dict) else (getattr(d, "hostname", "") or "")
                vendor = d.get("vendor", "") if isinstance(d, dict) else (getattr(d, "vendor", "") or "")
                if mac:
                    label_map[mac.lower()] = host or vendor or mac
        self._bw_worker = BandwidthWorker(interval_s=5.0, label_map=label_map)
        self._bw_worker.snapshot.connect(self._on_bw_snapshot)
        self._bw_worker.status.connect(self._bw_status.setText)
        self._bw_worker.error.connect(lambda e: self._bw_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._bw_worker.start()
        self._save_monitor_state("bandwidth", True)

    @pyqtSlot()
    def _stop_bandwidth_monitor(self):
        if self._bw_worker:
            self._bw_worker.stop()
            self._bw_status.setText("Bandwidth monitor stopped.")
            self._save_monitor_state("bandwidth", False)

    @pyqtSlot(object)
    def _on_bw_snapshot(self, snap):
        self._bw_stack.setCurrentIndex(1)   # switch from empty state to table
        self._bw_table.setRowCount(0)
        for entry in snap.entries:
            row = self._bw_table.rowCount()
            self._bw_table.insertRow(row)
            total_kbps = entry.total_bps / 1000
            level = "HIGH" if total_kbps > 5000 else ("MEDIUM" if total_kbps > 500 else "CLEAN")
            for col, val in enumerate([
                entry.label or entry.mac,
                f"{entry.tx_bps/1000:.1f}",
                f"{entry.rx_bps/1000:.1f}",
                f"{total_kbps:.1f}",
                f"{entry.total_mbps:.3f}",
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                    _color_for_level(level)
                ))
                self._bw_table.setItem(row, col, item)
        self._bw_status.setText(
            f"Bandwidth snapshot ({snap.window_s:.0f}s window) — "
            f"{len(snap.entries)} device(s)"
        )

    # ── Scheduler tab ─────────────────────────────────────────────────────────

    def _build_scheduler_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._sched_status = QLabel("Scheduled scanner not running.")
        self._sched_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl_row = QHBoxLayout()
        self._sched_interval = QSpinBox()
        self._sched_interval.setRange(1, 1440)
        self._sched_interval.setValue(15)
        self._sched_interval.setSuffix(" min")
        self._sched_interval.setFixedWidth(90)
        btn_start = QPushButton("▶  Start Scheduler")
        btn_start.setObjectName("btnNetRefresh")
        btn_start.clicked.connect(self._start_scheduler)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_scheduler)
        ctrl_row.addWidget(QLabel("Interval:"))
        ctrl_row.addWidget(self._sched_interval)
        ctrl_row.addWidget(btn_start)
        ctrl_row.addWidget(btn_stop)
        ctrl_row.addStretch()
        self._sched_log = QTextEdit()
        self._sched_log.setReadOnly(True)
        self._sched_log.setStyleSheet(f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;")
        lay.addWidget(self._sched_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._sched_log, 1)
        return w

    @pyqtSlot()
    def _start_scheduler(self):
        from workers.scan_worker import SchedulerWorker
        if self._sched_worker and self._sched_worker.isRunning():
            return
        from PyQt6.QtCore import QSettings as _QS
        _qs = _QS("NetSentinel", "NetSentinel")
        self._sched_worker = SchedulerWorker(
            interval_minutes=self._sched_interval.value(),
            offenders_path=self._offenders_path,
            notify_desktop=_qs.value("tray/notify_new_device", False, type=bool),
        )
        self._sched_worker.status.connect(self._on_sched_status)
        self._sched_worker.alert.connect(lambda t, m: self._sched_log.append(f"🔔 {t}: {m}"), Qt.ConnectionType.QueuedConnection)
        self._sched_worker.error.connect(lambda e: self._sched_log.append(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._sched_worker.start()
        self._save_monitor_state("scheduler", True)

    @pyqtSlot()
    def _stop_scheduler(self):
        if self._sched_worker:
            self._sched_worker.stop()
            self._sched_status.setText("Scheduler stopped.")
            self._save_monitor_state("scheduler", False)

    @pyqtSlot(str)
    def _on_sched_status(self, msg: str):
        self._sched_status.setText(msg)
        self._sched_log.append(msg)

    # ── SNMP tab ──────────────────────────────────────────────────────────────

    def _build_snmp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._snmp_status = QLabel("SNMP poller not running.")
        self._snmp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl_row = QHBoxLayout()
        self._snmp_community = QLineEdit()
        self._snmp_community.setFixedWidth(120)
        self._snmp_community.setPlaceholderText("community string")
        self._snmp_community.setEchoMode(QLineEdit.EchoMode.Password)  # RULE 22-D
        # RULE 22-A: load community string from OS keychain
        try:
            import keyring as _kr
            _stored = _kr.get_password("NetSentinel", "snmp/community")
            self._snmp_community.setText(_stored or "public")
        except Exception:
            self._snmp_community.setText("public")
        self._snmp_community.editingFinished.connect(self._save_snmp_community)
        btn_poll = QPushButton("▶  Poll All Devices")
        btn_poll.setObjectName("btnNetRefresh")
        btn_poll.clicked.connect(self._start_snmp_poll)
        ctrl_row.addWidget(QLabel("Community:"))
        ctrl_row.addWidget(self._snmp_community)
        ctrl_row.addWidget(btn_poll)
        ctrl_row.addStretch()
        self._snmp_table = _table(["Host", "Name", "Description", "Uptime", "Interfaces", "Contact"])
        self._snmp_table.setColumnWidth(0, 120)
        self._snmp_table.setColumnWidth(2, 350)
        lay.addWidget(self._snmp_status)
        lay.addLayout(ctrl_row)
        lay.addWidget(self._snmp_table, 1)
        return w

    @pyqtSlot()
    def _start_snmp_poll(self):
        from workers.scan_worker import SNMPWorker
        if self._snmp_worker and self._snmp_worker.isRunning():
            return
        # Collect IPs from last M1 scan + gateway
        hosts: list = []
        if self._m1_result:
            for d in self._m1_result.get("devices", []):
                ip = getattr(d, "ip", None) if not isinstance(d, dict) else d.get("ip")
                if ip:
                    hosts.append(ip)
        gw = self._net_info.get("gateway") if self._net_info else None
        if gw and gw not in hosts:
            hosts.insert(0, gw)
        if not hosts:
            self._snmp_status.setText("No devices found — run a Device Fingerprint scan first.")
            return
        self._snmp_table.setRowCount(0)
        community = self._snmp_community.text().strip() or "public"
        self._snmp_worker = SNMPWorker(hosts=hosts, community=community)
        self._snmp_worker.host_result.connect(self._on_snmp_result)
        self._snmp_worker.status.connect(self._snmp_status.setText)
        self._snmp_worker.error.connect(lambda e: self._snmp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._snmp_worker.start()

    @pyqtSlot()
    def _save_snmp_community(self) -> None:
        """Persist SNMP community string to OS keychain (RULE 22-A)."""
        value = self._snmp_community.text().strip()
        try:
            import keyring as _kr
            if value:
                _kr.set_password("NetSentinel", "snmp/community", value)
            else:
                try:
                    _kr.delete_password("NetSentinel", "snmp/community")
                except Exception:
                    pass
        except Exception:
            pass

    @pyqtSlot(object)
    def _on_snmp_result(self, result):
        if not result.reachable:
            return
        row = self._snmp_table.rowCount()
        self._snmp_table.insertRow(row)
        for col, val in enumerate([
            result.host, result.sys_name, result.sys_descr[:80],
            result.sys_uptime, result.if_count, result.sys_contact,
        ]):
            self._snmp_table.setItem(row, col, QTableWidgetItem(str(val)))

    # ── Recon: SYN Stealth Scan tab ───────────────────────────────────────────

    def _build_recon_syn_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        warn = QLabel(
            "⚠  SYN stealth scan requires administrator privileges and Npcap (Windows). "
            "Scans are not logged by the target's application layer. "
            "Use only on networks you own or have authorization to test."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{AMBER};font-size:11px;background:{AMBER_BG};padding:6px;border-radius:4px;")
        self._syn_status = QLabel("SYN scanner idle.")
        self._syn_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        self._syn_host = QLineEdit()
        self._syn_host.setPlaceholderText("IP or hostname…")
        self._syn_host.setFixedWidth(180)
        self._syn_rate = QSpinBox()
        self._syn_rate.setRange(10, 5000)
        self._syn_rate.setValue(500)
        self._syn_rate.setSuffix(" pps")
        self._syn_rate.setFixedWidth(100)
        from PyQt6.QtWidgets import QComboBox as _CB
        self._syn_ports_combo = _CB()
        self._syn_ports_combo.addItems(["Top 1000 ports", "Common 26 ports", "Full range (slow)"])
        self._syn_ports_combo.setFixedWidth(160)
        btn = QPushButton("⚡  SYN Scan")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_syn_scan)
        btn_stop = QPushButton("■  Stop")
        btn_stop.setObjectName("btnNetRefresh")
        btn_stop.clicked.connect(self._stop_syn_scan)
        ctrl.addWidget(self._syn_host)
        ctrl.addWidget(QLabel("Rate:"))
        ctrl.addWidget(self._syn_rate)
        ctrl.addWidget(self._syn_ports_combo)
        ctrl.addWidget(btn)
        ctrl.addWidget(btn_stop)
        ctrl.addStretch()
        self._recon_syn_table = _table(["Port", "State", "Protocol", "Service", "CVEs"])
        self._recon_syn_table.setColumnWidth(0, 70)
        self._recon_syn_table.setColumnWidth(1, 90)
        self._recon_syn_table.setColumnWidth(2, 70)
        self._recon_syn_table.setColumnWidth(3, 180)
        self._recon_syn_table.setColumnWidth(4, 70)
        self._recon_syn_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._recon_syn_table.customContextMenuRequested.connect(self._syn_table_context_menu)
        self._recon_syn_table.cellClicked.connect(self._on_syn_cell_clicked)
        from PyQt6.QtWidgets import QStackedWidget as _SW3
        self._syn_stack = _SW3()
        self._syn_stack.addWidget(_empty_state_widget(
            "🔎", "No scan run yet",
            "Enter a target host above and click SYN Scan to discover open TCP ports.",
            None, None,
        ))
        self._syn_stack.addWidget(self._recon_syn_table)
        lay.addWidget(warn)
        lay.addWidget(self._syn_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._syn_stack, 1)
        return w

    @pyqtSlot()
    def _start_syn_scan(self):
        from workers.scan_worker import SYNScanWorker
        host = self._syn_host.text().strip()
        if not host:
            return
        if self._syn_worker and self._syn_worker.isRunning():
            return
        self._record_recent_action(
            action_id=f"syn:{host}",
            label=f"Port Scan (TCP) · {host}",
            page="Port Scan (TCP)",
            params={"host": host},
        )
        self._recon_syn_table.setRowCount(0)
        self._syn_status.setText("⏳  Scanning ports…  this may take up to 30 seconds")
        mode_text = self._syn_ports_combo.currentText()
        if "Full range" in mode_text:
            ports = list(range(1, 65536))
        elif "Common 26" in mode_text:
            from modules.port_scanner import COMMON_PORTS
            ports = COMMON_PORTS
        else:
            from modules.syn_scanner import TOP_1000_PORTS
            ports = TOP_1000_PORTS
        rate = self._syn_rate.value()
        self._syn_worker = SYNScanWorker(host=host, ports=ports, rate_pps=rate)
        self._syn_worker.result.connect(self._on_syn_result)
        self._syn_worker.status.connect(self._syn_status.setText)
        self._syn_worker.error.connect(lambda e: self._syn_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._syn_worker.start()

    @pyqtSlot()
    def _stop_syn_scan(self):
        if self._syn_worker:
            self._syn_worker.stop()

    @pyqtSlot(int, int)
    def _on_syn_cell_clicked(self, row: int, col: int) -> None:
        if col != 4:
            return
        svc_item = self._recon_syn_table.item(row, 3)
        if svc_item and svc_item.text():
            self._nav_rail_go_to("CVE Tracker")

    def _syn_table_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        row = self._recon_syn_table.rowAt(pos.y())
        host = self._syn_host.text().strip()
        if row < 0 or not host:
            return
        port_item = self._recon_syn_table.item(row, 0)
        svc_item  = self._recon_syn_table.item(row, 3)
        port = (port_item.text() if port_item else "")
        svc  = (svc_item.text()  if svc_item  else "")
        menu = QMenu(self)
        menu.setStyleSheet(f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};")
        act_geo   = menu.addAction(f"🗺  Show {host} on Geo Map →")
        act_abuse = menu.addAction(f"🛡  Check {host} (AbuseIPDB) →")
        menu.addSeparator()
        act_copy_host = menu.addAction(f"📋  Copy host  ({host})")
        if port:
            act_copy_port = menu.addAction(f"📋  Copy  {host}:{port}  ({svc})")
        else:
            act_copy_port = None
        chosen = menu.exec(self._recon_syn_table.viewport().mapToGlobal(pos))
        if chosen == act_geo:
            self._show_ip_on_geo_map(host)
        elif chosen == act_abuse:
            self._threat_intel_page.check_ip(host)
            self._nav_rail_go_to("Threat Intelligence")
        elif chosen == act_copy_host:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(host)
        elif act_copy_port and chosen == act_copy_port:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(f"{host}:{port}")

    @pyqtSlot(object)
    def _on_syn_result(self, result):
        from PyQt6.QtGui import QColor
        self._syn_stack.setCurrentIndex(1)   # switch from empty state to table
        self._recon_syn_table.setRowCount(0)
        # Build quick CVE-count lookup by service keyword from MetricStore
        _cve_counts: dict[str, int] = {}
        try:
            if self._store is not None:
                _all_cves = self._store.list_cve_lifecycles() or []
                for _cve in _all_cves:
                    _svc = (_cve.get("service") or "").split()[0].lower()
                    if _svc:
                        _cve_counts[_svc] = _cve_counts.get(_svc, 0) + 1
        except Exception:
            pass
        for p in result.open_ports:
            row = self._recon_syn_table.rowCount()
            self._recon_syn_table.insertRow(row)
            color = RED if p.state == "open" else AMBER
            for col, val in enumerate([str(p.port), p.state, p.proto, p.service]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_syn_table.setItem(row, col, item)
            # CVE count badge (col 4)
            svc_key = (p.service or "").split()[0].lower()
            cve_n = _cve_counts.get(svc_key, 0)
            cve_item = QTableWidgetItem(f"{cve_n} CVEs" if cve_n else "—")
            cve_item.setForeground(QColor(AMBER if cve_n else TEXT_MUTED))
            if cve_n:
                cve_item.setToolTip(f"Click to view {cve_n} CVE(s) for {p.service}")
            self._recon_syn_table.setItem(row, 4, cve_item)
        self._syn_status.setText(result.plain_verdict if not result.error else f"⚠ {result.error}")
        # ── Update NetworkDocPage with accumulated port data ──────────────────
        try:
            if result.open_ports:
                _host_key = getattr(result, "host", "") or getattr(result, "ip", "")
                if _host_key:
                    self._port_data_cache[_host_key] = [
                        {"port": str(p.port), "protocol": p.proto or "tcp",
                         "service": p.service or "", "state": p.state or "open",
                         "banner": ""}
                        for p in result.open_ports
                    ]
            _nd_cert: list = []
            if self._store is not None:
                for _c in self._store.query_cert_status():
                    _nd_cert.append({"host": _c.host, "cn": _c.subject or "",
                                     "issuer": _c.issuer or "", "not_after": _c.not_after or "",
                                     "days_remaining": _c.days_remaining})
            self._network_doc_page.set_scan_data(
                devices=self._last_scan_devices,
                port_data=self._port_data_cache,
                cert_data=_nd_cert,
                topo_widget=getattr(self, "_topology_widget", None),
            )
        except Exception:
            pass

    # ── Recon: UDP Scan tab ───────────────────────────────────────────────────

    def _build_recon_udp_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        warn = QLabel(
            "⚠  UDP scan requires administrator privileges and Npcap (Windows). "
            "No response = open|filtered (firewall or open service — UDP is ambiguous)."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet(f"color:{AMBER};font-size:11px;background:{AMBER_BG};padding:6px;border-radius:4px;")
        self._udp_status = QLabel("UDP scanner idle.")
        self._udp_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        self._udp_host = QLineEdit()
        self._udp_host.setPlaceholderText("IP or hostname…")
        self._udp_host.setFixedWidth(180)
        btn = QPushButton("📻  UDP Scan")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_udp_scan)
        ctrl.addWidget(self._udp_host)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_udp_table = _table(["Port", "State", "Service"])
        self._recon_udp_table.setColumnWidth(0, 70)
        self._recon_udp_table.setColumnWidth(1, 120)
        self._recon_udp_table.setColumnWidth(2, 220)
        lay.addWidget(warn)
        lay.addWidget(self._udp_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_udp_table, 1)
        return w

    @pyqtSlot()
    def _start_udp_scan(self):
        from workers.scan_worker import UDPScanWorker
        host = self._udp_host.text().strip()
        if not host:
            return
        if self._udp_worker and self._udp_worker.isRunning():
            return
        self._recon_udp_table.setRowCount(0)
        self._udp_status.setText("⏳  Scanning UDP ports…  this may take 1–2 minutes")
        self._udp_worker = UDPScanWorker(host=host)
        self._udp_worker.result.connect(self._on_udp_result)
        self._udp_worker.status.connect(self._udp_status.setText)
        self._udp_worker.error.connect(lambda e: self._udp_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._udp_worker.start()

    @pyqtSlot(object)
    def _on_udp_result(self, result):
        from PyQt6.QtGui import QColor
        self._recon_udp_table.setRowCount(0)
        for p in result.open_ports:
            row = self._recon_udp_table.rowCount()
            self._recon_udp_table.insertRow(row)
            color = AMBER if p.state == "open|filtered" else GREEN
            for col, val in enumerate([str(p.port), p.state, p.service]):
                item = QTableWidgetItem(val)
                item.setForeground(QColor(color))
                self._recon_udp_table.setItem(row, col, item)
        self._udp_status.setText(result.plain_verdict if not result.error else f"⚠ {result.error}")

    # ── Recon: Deep OS Fingerprint tab ────────────────────────────────────────

    def _build_recon_os_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._os_status = QLabel("OS fingerprinter idle. Run Device Fingerprint scan first, or enter IPs manually.")
        self._os_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._os_status.setWordWrap(True)
        ctrl = QHBoxLayout()
        self._os_hosts_input = QLineEdit()
        self._os_hosts_input.setPlaceholderText("Leave blank to use M1 scan results…")
        btn = QPushButton("🖥  Fingerprint")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_os_fingerprint)
        ctrl.addWidget(self._os_hosts_input, 1)
        ctrl.addWidget(btn)
        self._recon_os_table = _table(["IP", "TTL", "OS Family", "Confidence", "TCP Window", "Banner Hint"])
        self._recon_os_table.setColumnWidth(0, 120)
        self._recon_os_table.setColumnWidth(1, 50)
        self._recon_os_table.setColumnWidth(2, 200)
        self._recon_os_table.setColumnWidth(3, 80)
        self._recon_os_table.setColumnWidth(4, 100)
        lay.addWidget(self._os_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_os_table, 1)
        return w

    @pyqtSlot()
    def _start_os_fingerprint(self):
        from workers.scan_worker import OSFingerprintWorker
        manual = self._os_hosts_input.text().strip()
        if manual:
            ips = [x.strip() for x in manual.replace(",", " ").split() if x.strip()]
        else:
            ips = []
            if self._m1_result:
                for d in self._m1_result.get("devices", []):
                    ip = getattr(d, "ip", None) if not isinstance(d, dict) else d.get("ip")
                    if ip:
                        ips.append(ip)
        if not ips:
            self._os_status.setText("No IPs to fingerprint. Run a scan first or enter IPs manually.")
            return
        if self._os_worker and self._os_worker.isRunning():
            return
        self._recon_os_table.setRowCount(0)
        self._os_worker = OSFingerprintWorker(ips=ips)
        self._os_worker.result.connect(self._on_os_result)
        self._os_worker.status.connect(self._os_status.setText)
        self._os_worker.error.connect(lambda e: self._os_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._os_worker.start()

    @pyqtSlot(dict)
    def _on_os_result(self, data: dict):
        for guess in data.get("guesses", []):
            row = self._recon_os_table.rowCount()
            self._recon_os_table.insertRow(row)
            for col, val in enumerate([
                getattr(guess, "ip", ""),
                str(getattr(guess, "ttl", "")),
                getattr(guess, "os_family", ""),
                getattr(guess, "confidence", ""),
                getattr(guess, "tcp_window", ""),
                getattr(guess, "banner_hint", ""),
            ]):
                self._recon_os_table.setItem(row, col, QTableWidgetItem(str(val)))
        self._os_status.setText(f"Fingerprinted {len(data.get('guesses', []))} host(s).")

    # ── Recon: Risk Scorer tab ────────────────────────────────────────────────

    def _build_recon_risk_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        self._risk_status = QLabel("Risk scorer idle. Run Device Fingerprint scan first.")
        self._risk_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        ctrl = QHBoxLayout()
        btn = QPushButton("🎯  Score All Devices")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._run_risk_scorer)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_risk_table = _table(["IP", "Device Type", "Score", "Severity", "Primary Finding", "Remediation"])
        self._recon_risk_table.setColumnWidth(0, 120)
        self._recon_risk_table.setColumnWidth(1, 160)
        self._recon_risk_table.setColumnWidth(2, 55)
        self._recon_risk_table.setColumnWidth(3, 80)
        self._recon_risk_table.setColumnWidth(4, 300)
        lay.addWidget(self._risk_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_risk_table, 1)
        return w

    @pyqtSlot()
    def _run_risk_scorer(self):
        from PyQt6.QtGui import QColor
        if not self._m1_result:
            self._risk_status.setText("No scan data — run Device Fingerprint first.")
            return
        try:
            from modules.risk_scorer import score_devices
            assessments = score_devices(self._m1_result.get("devices", []))
            self._recon_risk_table.setRowCount(0)
            for a in assessments:
                row = self._recon_risk_table.rowCount()
                self._recon_risk_table.insertRow(row)
                color = (RED if a.severity in ("CRITICAL", "HIGH") else
                         AMBER if a.severity == "MEDIUM" else GREEN)
                top_finding = a.findings[0].title if a.findings else "—"
                for col, val in enumerate([
                    a.ip, a.device_type or a.vendor,
                    str(a.total_score), a.severity,
                    top_finding, a.top_remediation,
                ]):
                    item = QTableWidgetItem(str(val))
                    item.setForeground(QColor(color if col in (2, 3) else TEXT_PRIMARY))
                    self._recon_risk_table.setItem(row, col, item)
            critical = sum(1 for a in assessments if a.severity in ("CRITICAL", "HIGH"))
            self._risk_status.setText(
                f"Scored {len(assessments)} device(s) — {critical} HIGH/CRITICAL risk."
            )
        except Exception as exc:
            self._risk_status.setText(f"⚠ Risk scoring failed: {exc}")

    # ── Recon: CVE Lookup tab ─────────────────────────────────────────────────

    def _build_recon_cve_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        info = QLabel(
            "Queries the NVD (National Vulnerability Database) API v2 for known CVEs "
            "matching service versions detected by the port scanner. "
            "Set NVD_API_KEY environment variable for higher rate limits."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._cve_status = QLabel("CVE lookup idle. Run the port scanner first (Advanced Tools tab).")
        self._cve_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._cve_status.setWordWrap(True)
        ctrl = QHBoxLayout()
        self._cve_target_input = QLineEdit()
        self._cve_target_input.setPlaceholderText("Optional: manually add service versions, e.g.  OpenSSH 8.9p1, Apache/2.4.54")
        btn = QPushButton("🛡  Lookup CVEs")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_cve_lookup)
        ctrl.addWidget(self._cve_target_input, 1)
        ctrl.addWidget(btn)
        self._recon_cve_table = _table(["CVE ID", "Service", "Score", "Severity", "Published", "Description"])
        self._recon_cve_table.setColumnWidth(0, 130)
        self._recon_cve_table.setColumnWidth(1, 160)
        self._recon_cve_table.setColumnWidth(2, 55)
        self._recon_cve_table.setColumnWidth(3, 80)
        self._recon_cve_table.setColumnWidth(4, 90)
        lay.addWidget(info)
        lay.addWidget(self._cve_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_cve_table, 1)
        return w

    @pyqtSlot()
    def _start_cve_lookup(self):
        from workers.scan_worker import CVELookupWorker
        if self._cve_worker and self._cve_worker.isRunning():
            return

        # Collect service versions from last port scan result
        versions: list = []
        manual = self._cve_target_input.text().strip()
        if manual:
            versions = [v.strip() for v in manual.split(",") if v.strip()]
        else:
            # Pull from port scan results table
            ps_table = self._ps_table
            version_col = 2  # Version column index in port scan table
            for row in range(ps_table.rowCount()):
                item = ps_table.item(row, version_col)
                if item and item.text().strip():
                    versions.append(item.text().strip())

        if not versions:
            self._cve_status.setText("No service versions found. Run a port scan first or enter versions manually.")
            return

        self._recon_cve_table.setRowCount(0)
        self._cve_worker = CVELookupWorker(service_versions=list(set(versions)))
        self._cve_worker.cve_result.connect(self._on_cve_result)
        self._cve_worker.status.connect(self._cve_status.setText)
        self._cve_worker.finished_all.connect(lambda: self._cve_status.setText(
            self._cve_status.text() + "  ✓ Done."
        ), Qt.ConnectionType.QueuedConnection)
        self._cve_worker.start()

    @pyqtSlot(str, object)
    def _on_cve_result(self, service_version: str, result):
        from PyQt6.QtGui import QColor
        for cve in result.cves:
            row = self._recon_cve_table.rowCount()
            self._recon_cve_table.insertRow(row)
            sev = (cve.severity or "NONE").upper()
            color = (RED if sev in ("CRITICAL", "HIGH") else
                     AMBER if sev == "MEDIUM" else
                     BLUE if sev == "LOW" else TEXT_SECONDARY)
            for col, val in enumerate([
                cve.cve_id, service_version,
                f"{cve.cvss_score:.1f}", sev,
                cve.published, cve.description,
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(color if col in (2, 3) else TEXT_PRIMARY))
                self._recon_cve_table.setItem(row, col, item)
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_cve_count(self._recon_cve_table.rowCount())

    # ── Recon: Internet Exposure tab ──────────────────────────────────────────

    def _build_recon_exposure_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        info = QLabel(
            "Checks whether LAN devices are reachable from the public internet.\n"
            "Stage 1: fetches your public WAN IP and detects carrier-grade NAT (CGNAT).\n"
            "Stage 2: queries your router's UPnP/IGD (LAN-only SSDP) for port-forwarding rules — "
            "any forwarded port means that service is internet-accessible."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._exposure_status = QLabel("Internet exposure check idle.")
        self._exposure_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")
        self._exposure_status.setWordWrap(True)
        self._exposure_verdict = QLabel("")
        self._exposure_verdict.setWordWrap(True)
        self._exposure_verdict.setStyleSheet(
            f"color:{AMBER};font-size:12px;font-weight:bold;padding:6px;"
            f"background:{AMBER_BG};border-radius:4px;"
        )
        self._exposure_verdict.hide()
        ctrl = QHBoxLayout()
        btn = QPushButton("🌐  Check Exposure")
        btn.setObjectName("btnNetRefresh")
        btn.clicked.connect(self._start_exposure_check)
        ctrl.addWidget(btn)
        ctrl.addStretch()
        self._recon_exposure_table = _table(
            ["Device IP", "External Port", "Internal Port", "Protocol", "Description", "Enabled"]
        )
        self._recon_exposure_table.setColumnWidth(0, 130)
        self._recon_exposure_table.setColumnWidth(1, 110)
        self._recon_exposure_table.setColumnWidth(2, 110)
        self._recon_exposure_table.setColumnWidth(3, 70)
        self._recon_exposure_table.setColumnWidth(4, 200)
        lay.addWidget(info)
        lay.addWidget(self._exposure_verdict)
        lay.addWidget(self._exposure_status)
        lay.addLayout(ctrl)
        lay.addWidget(self._recon_exposure_table, 1)
        return w

    @pyqtSlot()
    def _start_exposure_check(self):
        from workers.scan_worker import InternetExposureWorker
        if self._exposure_worker and self._exposure_worker.isRunning():
            return
        self._recon_exposure_table.setRowCount(0)
        self._exposure_verdict.hide()
        self._exposure_worker = InternetExposureWorker()
        self._exposure_worker.result.connect(self._on_exposure_result)
        self._exposure_worker.status.connect(self._exposure_status.setText)
        self._exposure_worker.error.connect(lambda e: self._exposure_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._exposure_worker.start()

    @pyqtSlot(object)
    def _on_exposure_result(self, result):
        from PyQt6.QtGui import QColor
        risk_color = RED if result.risk == "HIGH" else AMBER if result.risk == "MEDIUM" else GREEN
        self._exposure_verdict.setText(result.plain_verdict)
        self._exposure_verdict.setStyleSheet(
            f"color:{risk_color};font-size:12px;font-weight:bold;padding:6px;"
            f"background:{RED_BG};border-radius:4px;" if result.risk == "HIGH" else
            f"color:{risk_color};font-size:12px;font-weight:bold;padding:6px;"
            f"background:{AMBER_BG};border-radius:4px;"
        )
        self._exposure_verdict.show()
        self._recon_exposure_table.setRowCount(0)
        for m in result.upnp_mappings:
            row = self._recon_exposure_table.rowCount()
            self._recon_exposure_table.insertRow(row)
            row_color = RED if m.enabled else TEXT_SECONDARY
            for col, val in enumerate([
                m.internal_ip, str(m.external_port), str(m.internal_port),
                m.protocol, m.description, "Yes" if m.enabled else "No",
            ]):
                item = QTableWidgetItem(str(val))
                item.setForeground(QColor(row_color))
                self._recon_exposure_table.setItem(row, col, item)
        self._exposure_status.setText(
            f"WAN IP: {result.wan_ip or 'unknown'} | "
            f"CGNAT: {'Yes' if result.cgnat else 'No'} | "
            f"UPnP mappings: {len(result.upnp_mappings)}"
        )

    # ── Help page ────────────────────────────────────────────────────────────

    def _build_help_tab(self) -> QWidget:
        """Static Help & Shortcuts reference page."""
        page = QWidget()
        page.setObjectName("contentArea")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        # Page header
        outer.addWidget(_page_header(
            "Help & Shortcuts",
            "Quick-start guide, keyboard shortcuts, and feature reference",
        ))

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        body = QWidget()
        body.setObjectName("contentArea")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 12, 20)
        bl.setSpacing(12)

        def _section(title: str, rows: list[tuple[str, str]]) -> QFrame:
            card = QFrame()
            card.setObjectName("card")
            card.setStyleSheet(
                f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
                f"border-radius:{CARD_RADIUS};}}"
            )
            cl = QVBoxLayout(card)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)

            # title bar
            tb = QFrame()
            tb.setObjectName("cardHeader")
            tb.setFixedHeight(32)
            tb.setStyleSheet(
                f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};"
            )
            tbl = QHBoxLayout(tb)
            tbl.setContentsMargins(12, 0, 12, 0)
            t = QLabel(title)
            t.setStyleSheet(
                f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;"
            )
            tbl.addWidget(t)
            tbl.addStretch()
            cl.addWidget(tb)

            # rows
            tbl_w = QTableWidget(len(rows), 2)
            tbl_w.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            tbl_w.horizontalHeader().setVisible(False)
            tbl_w.verticalHeader().setVisible(False)
            tbl_w.setShowGrid(False)
            tbl_w.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
            tbl_w.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            tbl_w.setStyleSheet(
                f"QTableWidget{{background:{BG_CARD};border:none;font-size:11px;}}"
                f"QTableWidget::item{{padding:4px 8px;color:{TEXT_PRIMARY};}}"
            )
            tbl_w.horizontalHeader().setStretchLastSection(True)
            tbl_w.setColumnWidth(0, 220)
            tbl_w.verticalHeader().setDefaultSectionSize(24)

            for i, (key, desc) in enumerate(rows):
                k = QTableWidgetItem(key)
                k.setFont(QFont("Consolas", 10))
                k.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(ACCENT_DARK))
                k.setBackground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(BG_ALT_ROW if i % 2 else BG_CARD))
                d = QTableWidgetItem(desc)
                d.setBackground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(BG_ALT_ROW if i % 2 else BG_CARD))
                tbl_w.setItem(i, 0, k)
                tbl_w.setItem(i, 1, d)

            tbl_w.setFixedHeight(len(rows) * 24 + 2)
            cl.addWidget(tbl_w)
            return card

        # ── Getting started ──────────────────────────────────────────────────
        intro_card = QFrame()
        intro_card.setObjectName("card")
        intro_card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        icl = QVBoxLayout(intro_card)
        icl.setContentsMargins(0, 0, 0, 0)
        icl.setSpacing(0)

        itb = QFrame()
        itb.setFixedHeight(32)
        itb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
        itbl = QHBoxLayout(itb)
        itbl.setContentsMargins(12, 0, 12, 0)
        itl = QLabel("Getting Started")
        itl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
        itbl.addWidget(itl)
        itbl.addStretch()
        icl.addWidget(itb)

        intro_text = QLabel(
            "<p style='margin:12px 16px 4px 16px; font-size:11px; "
            f"color:{TEXT_PRIMARY}; line-height:1.6;'>"
            "<b>1. Run as Administrator</b> — STP, Storm, ARP, and Bandwidth modules "
            "require raw packet capture (Npcap on Windows). Right-click the shortcut "
            "→ Run as Administrator, or the app will prompt you automatically.<br><br>"
            "<b>2. Click Run Scan</b> — the main scan button sweeps your subnet, "
            "flushes ARP/DNS caches, and populates all Standard tabs in parallel. "
            "Most scans finish in 10–30 seconds depending on network size.<br><br>"
            "<b>3. Switch to Standard mode</b> — click the mode pill in the top bar "
            "(shows Home ▾ by default) and choose Standard. This reveals MTR, Bandwidth, "
            "ARP Watch, DHCP, Network Map, Scheduled Scans, Trend Forecasts, and more.<br><br>"
            "<b>4. Switch to Pro mode for Security Audit</b> — choose Pro from the same "
            "mode pill to reveal SYN/UDP port scanners, OS detection, CVE lookup, credential "
            "testing, and cloud metadata probe. "
            "Only use on networks you own or have explicit written authorisation to test.<br><br>"
            "<b>5. Right-click anything</b> — every table row has a context menu "
            "with Copy IP, Copy MAC, Port Scan, How to Fix, Wake-on-LAN, and more.<br><br>"
            "<b>6. Generate a Network Health Report</b> — run the Stability Logger for at least "
            "30 minutes, then open Network Grade → Network Health Report. Exports a "
            "standalone HTML file with evidence-grade data — great for ISP support tickets."
            "</p>"
        )
        intro_text.setWordWrap(True)
        intro_text.setTextFormat(Qt.TextFormat.RichText)
        icl.addWidget(intro_text)
        bl.addWidget(intro_card)

        # ── First 10 Minutes walkthrough ─────────────────────────────────────
        walkthrough_card = QFrame()
        walkthrough_card.setObjectName("card")
        walkthrough_card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        wcl = QVBoxLayout(walkthrough_card)
        wcl.setContentsMargins(0, 0, 0, 0)
        wcl.setSpacing(0)
        wtb = QFrame()
        wtb.setFixedHeight(32)
        wtb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
        wtbl = QHBoxLayout(wtb)
        wtbl.setContentsMargins(12, 0, 12, 0)
        wtl = QLabel("First 10 Minutes — Guided Walkthrough")
        wtl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
        wtbl.addWidget(wtl)
        wtbl.addStretch()
        wcl.addWidget(wtb)
        walkthrough_text = QLabel(
            f"<div style='margin:12px 16px 12px 16px; font-size:11px; "
            f"color:{TEXT_PRIMARY}; line-height:1.7;'>"
            f"<b style='color:{ACCENT};'>Step 1 — See what's on your network</b><br>"
            "Click <b>Run Scan</b> on the Home screen (or press Ctrl+R). NetSentinel sends "
            "ARP requests to every address in your subnet and builds a full device list. "
            "Most home networks finish in under 15 seconds.<br>"
            "<i>What to look for:</i> any device you don't recognise. Note its MAC address "
            "— the first 6 characters identify the manufacturer (e.g. <code>B8:27:EB</code> = Raspberry Pi).<br><br>"

            f"<b style='color:{ACCENT};'>Step 2 — Check your connection quality</b><br>"
            "Go to <b>DNS &amp; Outages</b>. You'll see a live RTT graph to your gateway and "
            "internet targets. A flat line under 10 ms to your router is healthy. "
            "Spikes above 200 ms, or gaps in the line, indicate packet loss.<br>"
            "<i>What to look for:</i> regular drops every 30–45 seconds often mean a "
            "device on your network is winning the STP Root Bridge election. "
            "See <i>Learn Networking</i> below for what that means.<br><br>"

            f"<b style='color:{ACCENT};'>Step 3 — Run the Health Check</b><br>"
            "Open <b>Health Check</b> and click <b>Run Diagnostics</b>. This tests ping "
            "to 5 targets, compares DNS speed across 4 resolvers, checks HTTP reachability, "
            "and runs a traceroute to your gateway.<br>"
            "<i>What to look for:</i> if the DNS comparison shows your ISP's resolver "
            "is 3–5× slower than Cloudflare (1.1.1.1), switching DNS in your router settings "
            "can noticeably speed up browsing.<br><br>"

            f"<b style='color:{ACCENT};'>Step 4 — Get your Network Grade</b><br>"
            "Open <b>Network Grade</b>. The A–F score across 8 dimensions tells you "
            "where your network ranks. Any dimension rated C or below has a "
            "<b>How to Fix</b> guide — click the row.<br>"
            "<i>What to look for:</i> a low Safety score means unknown or high-risk "
            "devices are present. A low STP score means a rogue bridge was detected.<br><br>"

            f"<b style='color:{ACCENT};'>Step 5 — Let it run in the background</b><br>"
            "Leave NetSentinel open for 30+ minutes while you use your network normally. "
            "The <b>Stability Log</b> and <b>Availability History</b> tabs build up "
            "timestamped evidence. After 30 minutes, <b>Network Grade → Network Health Report</b> "
            "produces a standalone HTML file you can attach to an ISP support ticket — "
            "with hop-by-hop packet loss, outage timestamps, and DNS latency data.<br><br>"

            f"<b style='color:{ACCENT};'>Tip — Right-click everything</b><br>"
            "Every table row in NetSentinel has a context menu. Right-click any device "
            "for <b>Copy IP</b>, <b>Copy MAC</b>, <b>Port Scan</b>, <b>How to Fix</b>, "
            "and <b>Wake-on-LAN</b>. Right-click any scan result for remediation guidance."
            "</div>"
        )
        walkthrough_text.setWordWrap(True)
        walkthrough_text.setTextFormat(Qt.TextFormat.RichText)
        wcl.addWidget(walkthrough_text)
        bl.addWidget(walkthrough_card)

        # ── Keyboard shortcuts ───────────────────────────────────────────────
        bl.addWidget(_section("Keyboard Shortcuts", [
            ("Ctrl + R",           "Run full scan"),
            ("Ctrl + Shift + M",   "Visual Diagnostic Overlay (Matrix)"),
            ("Ctrl + E",           "Export last scan results"),
            ("Ctrl + Q",           "Quit application"),
            ("F5",                 "Refresh current tab"),
            ("Right-click",        "Context menu on any table row"),
        ]))

        # ── Feature reference ────────────────────────────────────────────────
        bl.addWidget(_section("Standard Features (no admin required for most)", [
            ("Devices on Network",   "ARP scan — every device with IP, MAC, vendor, model, type, risk"),
            ("Rogue Bridge (STP)",   "Captures BPDUs and flags devices stealing the Root Bridge role"),
            ("Broadcast Storm",      "Measures broadcast/multicast flood levels by source device"),
            ("WiFi Networks",        "Hidden SSIDs, rogue APs, co-channel interference, WPS flags"),
            ("DNS & Outages",        "Live ping + DNS latency graph with STP reconvergence detection"),
            ("My Network Info",      "Local IPs, subnet, gateway, DNS servers, DHCP lease, adapter speeds"),
            ("Health Check",         "On-demand ping, DNS speed test, traceroute, HTTP check, DNS leak test"),
            ("Stability Log",        "Long-term logger — timestamped outage evidence for ISP disputes"),
            ("Availability History", "Per-target uptime log with expandable incident detail per row"),
            ("Network Grade",        "A–F score across 8 dimensions with an exportable Network Health Report"),
            ("Root Cause Analysis",  "Correlates STP, Storm, DNS, and Logger data — ISP vs local verdict"),
            ("IoT Behaviour",        "Baselines normal IoT traffic, alerts on port scanning or new servers"),
            ("IPv6 Devices",         "Link-local segment sweep via OS neighbour cache and ping"),
            ("Service Heartbeat",    "Monitor uptime and response time of any host:port — custom target list"),
            ("Active Connections",   "Live table of current TCP/UDP connections with process and remote IP"),
            ("WiFi Heatmap",         "Import floor plan, record signal-strength readings, IDW heatmap overlay per AP"),
            ("Geolocation Map",      "World-map plot of internet-facing IPs — MaxMind GeoLite2 local DB, no external API"),
            ("Custom Triggers",      'Alert expressions: avg(rtt[\"ip\"], 5m) > 80 — visual builder, test now, cooldown'),
            ("Protocol Visualizer",  "Animated ARP, DNS, TCP, DHCP, and STP diagrams using your real scan data"),
            ("Lab Mode",             "Hands-on sandbox exercises for learning networking protocols step by step"),
        ]))

        bl.addWidget(_section("Advanced Features (Standard and Pro modes)", [
            ("Hop-by-Hop Trace",     "Continuous MTR — live per-hop loss % and RTT, updating every cycle"),
            ("Tools & Wake-on-LAN",  "TCP port scanner (Fast / Normal / Low), service banners, WoL sender"),
            ("Network Map",          "Visual topology diagram of devices and their relationships"),
            ("ARP Spoof Watch",      "Detects ARP poisoning and MITM attacks in real time"),
            ("DHCP Leases",          "DHCP lease inventory — all IPs handed out by your router"),
            ("DHCP Rogue Monitor",   "Actively probes for rogue DHCP servers via crafted Discover packets"),
            ("Bandwidth Usage",      "Per-device rx/tx bps monitor via live packet capture"),
            ("Scheduled Scans",      "Automated scans every N minutes with desktop notifications"),
            ("SNMP Device Info",     "Polls SNMPv1/v2c OIDs — no extra dependencies required"),
            ("Syslog Receiver",      "Collects syslog messages from routers, switches, and servers"),
            ("SNMP Trap Receiver",   "Receives SNMP trap messages from network devices"),
            ("Trend Forecasts",      "ML-based predictive forecasting of latency, packet loss, and uptime"),
            ("Config Snapshots",     "Timestamped network configuration snapshots with diff highlighting"),
            ("Maintenance Windows",  "Schedule maintenance periods to suppress alerts during planned downtime"),
            ("Automation Hooks",     "Fire webhook / run script when network events occur — device-down, high RTT, new device"),
            ("Network Documentation","Auto-generates HTML/Markdown snapshot: inventory, services, topology, TLS"),
            ("MQTT / Home Assistant","Publish device/metric events to MQTT broker; HA Discovery payloads"),
        ]))

        bl.addWidget(_section("Security Audit Features (Pro mode — admin required)", [
            ("Port Scan (TCP)",       "Raw SYN scanner — stealthy, fast, admin required"),
            ("Port Scan (UDP)",       "UDP service discovery"),
            ("OS Detection",          "OS fingerprinting via TTL + banner + SYN probe"),
            ("Device Risk Score",     "Per-device numeric risk score with remediation guidance"),
            ("Known CVEs",            "NVD API v2 CVE lookup for detected software/services"),
            ("Exposed to Internet",   "WAN IP, CGNAT detection, UPnP port mapping enumeration"),
            ("Login Test (SSH/SMB)",  "Credential testing against SSH and SMB services"),
            ("Full Device Discovery", "Parallel ARP + ICMP + TCP SYN + mDNS discovery"),
            ("Windows Shares (SMB)",  "NetBIOS + SMB share and user enumeration"),
            ("Private Endpoint Check","DNS/TCP/TLS reachability checker for cloud private endpoints"),
            ("Cloud Metadata Probe",  "Detects SSRF exposure via cloud VM metadata endpoint access"),
        ]))

        # ── What's New ───────────────────────────────────────────────────────
        from PyQt6.QtWidgets import QApplication
        app_ver = QApplication.applicationVersion()
        bl.addWidget(_section(f"What's New in v{app_ver}", [
            ("Protocol Visualizer",         "Animated step-by-step diagrams of ARP, DNS, TCP, DHCP, and STP using real scan data"),
            ("'Since you were last here'",  "Home screen shows new devices joined and outages recorded since your last session"),
            ("Next-step suggestion cards",  "After a scan the Home screen surfaces the most useful action (run speed test, fix CVEs, etc.)"),
            ("Weekly digest notification",  "Tray notification on startup summarises speed, new devices, and grade once per week"),
            ("Web dashboard",               "Read-only browser view at http://localhost:8765/dashboard — LAN access from phone or tablet"),
            ("Page transitions",            "120 ms opacity fade when switching between pages — smoother navigation"),
            ("Collapsible row detail",       "Click any device, service, or uptime row to expand an inline detail panel"),
            ("WiFi Heatmap",               "Floor plan import + signal-strength sampling + IDW heatmap overlay per AP"),
            ("Geolocation Map",            "MaxMind GeoLite2 local DB; world-map plot of IPs; integrates with Threat Intel"),
            ("Custom Triggers",            "avg(rtt[\"ip\"], 5m) > 80 — expression builder, test against live data, cooldown"),
            ("Automation Hooks",           "Event-driven webhook / script rules — device-down, high RTT, new device"),
            ("Alert rules opt-in only",    "All alert rules default off — enable individually in Settings → Notifications"),
        ]))

        # ── Requirements ─────────────────────────────────────────────────────
        bl.addWidget(_section("Requirements & Notes", [
            ("Administrator rights",  "Required for STP, Storm, ARP Watch, Bandwidth, SYN scan"),
            ("Npcap (Windows)",        "Required for raw packet capture — https://npcap.com (free)"),
            ("Python 3.10+",           "If running from source: pip install -r requirements.txt"),
            ("WINGET_PAT (CI only)",   "GitHub PAT with repo scope — needed only for automated winget submission in CI"),
        ]))

        # ── Risk Level Guide ──────────────────────────────────────────────────
        risk_card = QFrame()
        risk_card.setObjectName("card")
        risk_card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        rcl = QVBoxLayout(risk_card)
        rcl.setContentsMargins(0, 0, 0, 0)
        rcl.setSpacing(0)
        rtb = QFrame()
        rtb.setFixedHeight(32)
        rtb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
        rtbl = QHBoxLayout(rtb)
        rtbl.setContentsMargins(12, 0, 12, 0)
        rtl = QLabel("Risk Level Guide")
        rtl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
        rtbl.addWidget(rtl)
        rtbl.addStretch()
        rcl.addWidget(rtb)

        _risk_rows = [
            ("CLEAN",   GREEN,    GREEN_BG,  "No threats or issues detected. All devices are expected."),
            ("LOW",     ACCENT,   BG_CARD,   "Minor or informational — no immediate action required."),
            ("MEDIUM",  AMBER,    AMBER_BG,  "Noteworthy — review soon. Examples: unknown device, degraded RTT."),
            ("WARNING", AMBER,    AMBER_BG,  "Active issue that should be investigated promptly."),
            ("HIGH",    RED,      RED_BG,    "Serious threat detected — ARP spoof, rogue bridge, rogue DHCP."),
            ("STORM",   RED,      RED_BG,    "Broadcast storm in progress — network performance is impacted now."),
            ("UNKNOWN", TEXT_MUTED, BG_CARD, "Device or result could not be classified. Check manually."),
        ]
        for lvl, fg, bg, meaning in _risk_rows:
            rw = QWidget()
            rw.setStyleSheet(f"background:{bg};")
            rwl = QHBoxLayout(rw)
            rwl.setContentsMargins(12, 4, 12, 4)
            rwl.setSpacing(10)
            badge = QLabel(lvl)
            badge.setFixedWidth(72)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"color:{fg};font-size:10px;font-weight:bold;"
                f"border:1px solid {fg};border-radius:3px;padding:1px 4px;"
                f"background:transparent;"
            )
            ml = QLabel(meaning)
            ml.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;")
            rwl.addWidget(badge)
            rwl.addWidget(ml, 1)
            rcl.addWidget(rw)
        bl.addWidget(risk_card)

        # ── Common Scenarios ──────────────────────────────────────────────────
        bl.addWidget(_section("I want to…  (Common Scenarios)", [
            ("…see every device on my network",       "Devices on Network — run a scan"),
            ("…find out why my internet is slow",     "Network Grade → run benchmark; Stability Log for long-term evidence"),
            ("…detect if someone is on my WiFi",      "WiFi Networks + Devices on Network → look for unknown MACs"),
            ("…prove to my ISP the problem is theirs","Stability Log for 30+ min → Network Grade → Network Health Report"),
            ("…check if a device is hacked",          "Device Risk Score + Known CVEs (Security Audit section)"),
            ("…monitor uptime of my servers",         "Service Heartbeat → add hosts + ports to watch"),
            ("…see all open ports on a device",       "Tools & Wake-on-LAN → TCP Port Scan (Advanced section)"),
            ("…detect ARP spoofing / MITM attack",    "ARP Spoof Watch (Advanced section)"),
            ("…see who is using the most bandwidth",  "Bandwidth Usage (Advanced section)"),
            ("…check TLS certificate expiry",         "TLS & exposure (Security Audit section)"),
            ("…trace packet loss hop-by-hop",         "Hop-by-Hop Trace / MTR (Advanced section)"),
            ("…map WiFi coverage in a room",          "WiFi Heatmap (Tools) — import floor plan, walk space, render heatmap"),
            ("…see where threat IPs are located",     "Geolocation Map (Tools) — import from Threat Intel or add IPs manually"),
            ("…alert on custom metric thresholds",    "Custom Triggers (Reports & Alerts) — write expressions like avg(rtt,5m)>80"),
            ("…trigger automation when a host drops", "Automation Hooks (Advanced) — add webhook/script rule for device-down event"),
            ("…send events to Home Assistant",        "MQTT / Home Assistant (Advanced) — configure broker, enable Discovery"),
            ("…change the colour theme",              "⚙ Settings → Appearance — Colour Theme"),
            ("…see how ARP/DNS/TCP actually works",   "Protocol Visualizer (Education section) — animated diagrams using your real scan data"),
            ("…use NetSentinel from my phone",        "Web Dashboard — open http://localhost:8765/dashboard on any LAN device"),
            ("…get a weekly health summary",          "Automatic — weekly digest tray notification fires on startup once per 7 days"),
            ("…forecast when my network will degrade","Trend Forecasts (Standard/Pro) — ML-based latency and uptime prediction"),
        ]))

        # ── Glossary ──────────────────────────────────────────────────────────
        bl.addWidget(_section("Glossary — Key Terms", [
            ("ARP",            "Address Resolution Protocol — maps IP addresses to MAC addresses on a LAN"),
            ("ARP Spoofing",   "Attack where a device sends fake ARP replies to redirect traffic through it"),
            ("BPDU",           "Bridge Protocol Data Unit — packets used by switches to elect the Root Bridge"),
            ("CGNAT",          "Carrier-Grade NAT — ISP shares one public IP across many customers; you can't host servers"),
            ("CVE",            "Common Vulnerabilities and Exposures — public database of known security flaws"),
            ("DHCP",           "Dynamic Host Configuration Protocol — server that hands out IP addresses automatically"),
            ("DNS",            "Domain Name System — translates names like google.com to IP addresses"),
            ("DNS Leak",       "When your DNS queries go to your ISP's server instead of your chosen one (privacy risk)"),
            ("Jitter",         "Variation in packet arrival time — high jitter causes choppy voice/video calls"),
            ("MAC address",    "Hardware address burned into a network adapter — unique per device (first 3 bytes = vendor OUI)"),
            ("mDNS",           "Multicast DNS — lets devices announce themselves on the LAN without a central server"),
            ("MITM",           "Man-in-the-Middle — attacker intercepts traffic between two parties"),
            ("MTR",            "My TraceRoute — combines ping and traceroute, showing loss % at each hop"),
            ("Npcap",          "Windows packet capture driver required for raw network access (free, from npcap.com)"),
            ("OUI",            "Organizationally Unique Identifier — the first 3 bytes of a MAC that identify the vendor"),
            ("RTT",            "Round-Trip Time — how long a packet takes to travel to a host and back (in ms)"),
            ("SNMP",           "Simple Network Management Protocol — queries routers/switches for status data"),
            ("SSRF",           "Server-Side Request Forgery — server makes unintended requests; exploits cloud metadata APIs"),
            ("STP",            "Spanning Tree Protocol — prevents loops in switched networks by electing a Root Bridge"),
            ("Subnet",         "A range of IP addresses within a network, e.g. 192.168.1.0/24 = 256 addresses"),
            ("SYN scan",       "Port scan technique using half-open TCP connections — stealthy, fast, needs admin rights"),
            ("TLS",            "Transport Layer Security — encrypts connections (HTTPS, SMTPS, etc.); replaces SSL"),
            ("UPnP",           "Universal Plug and Play — lets devices open ports on your router automatically (security risk)"),
            ("WAN IP",         "Your external public IP address as seen by the internet"),
        ]))

        # ── Learn Networking ─────────────────────────────────────────────────
        learn_card = QFrame()
        learn_card.setObjectName("card")
        learn_card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        lcl = QVBoxLayout(learn_card)
        lcl.setContentsMargins(0, 0, 0, 0)
        lcl.setSpacing(0)
        ltb = QFrame()
        ltb.setFixedHeight(32)
        ltb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
        ltbl = QHBoxLayout(ltb)
        ltbl.setContentsMargins(12, 0, 12, 0)
        ltl = QLabel("Learn Networking — How Your Network Actually Works")
        ltl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
        ltbl.addWidget(ltl)
        ltbl.addStretch()
        lcl.addWidget(ltb)
        learn_text = QLabel(
            f"<div style='margin:12px 16px 14px 16px; font-size:11px; "
            f"color:{TEXT_PRIMARY}; line-height:1.75;'>"

            f"<b style='font-size:12px; color:{ACCENT};'>Your home network at a glance</b><br>"
            "Your <b>router</b> sits between two worlds: the <b>WAN</b> (your ISP — the internet) "
            "and the <b>LAN</b> (your home devices). Every device on the LAN gets two addresses: "
            "a <b>MAC address</b> (burned into the hardware, identifies the manufacturer, never changes) "
            "and an <b>IP address</b> (assigned by DHCP, can change on reconnect). "
            "Your router runs <b>DHCP</b> to hand out IPs automatically and <b>DNS</b> to translate "
            "names like <i>google.com</i> into the IP addresses that packets actually travel to.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>How the scan works — ARP</b><br>"
            "<b>ARP</b> (Address Resolution Protocol) is how devices on a LAN find each other. "
            "When your computer wants to talk to 192.168.1.1, it broadcasts <i>"
            "\"Who has 192.168.1.1?\"</i> — every device on the subnet hears this. "
            "The device with that IP replies with its MAC address. "
            "NetSentinel sends an ARP request to every address in your subnet simultaneously, "
            "then listens for replies — revealing every active device without any special permissions.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>Reading RTT — what the numbers mean</b><br>"
            "<b>RTT</b> (Round-Trip Time) is how long a packet takes to travel to a host and "
            "return, measured in milliseconds. Good benchmarks: <b>&lt; 1 ms</b> to your router "
            "(same LAN); <b>&lt; 20 ms</b> to your ISP gateway; <b>&lt; 50 ms</b> to major internet "
            "servers. Over <b>100 ms</b> consistently to 8.8.8.8 means your connection is struggling. "
            "<b>Jitter</b> (variation between readings) matters for voice and video — "
            "a stable 30 ms line is better than one that swings between 5 ms and 200 ms.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>Spanning Tree Protocol (STP) — the hidden troublemaker</b><br>"
            "STP prevents network loops by electing one device as the <b>Root Bridge</b> — "
            "all traffic flows through it. Your router should win this election. "
            "But mesh WiFi nodes, smart TVs, and game consoles connected via Ethernet also "
            "participate in STP. If any device has a lower <i>Bridge ID</i> than your router, "
            "it wins the election — and your router blocks its own uplink port while the "
            "new root reconverges the network. This causes <b>15–45 second outages every few minutes</b> "
            "that ISP support always blames on WiFi interference. "
            "NetSentinel captures the BPDU packets that reveal which device is doing this.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>ARP spoofing — how MITM attacks work</b><br>"
            "Because ARP has no authentication, a device can send <i>fake</i> ARP replies: "
            "<i>\"I have the IP of your router — send traffic to my MAC instead.\"</i> "
            "Every device on the LAN updates its ARP cache with the lie. Now all your traffic "
            "flows through the attacker's machine, which reads it and forwards it on — "
            "a classic <b>Man-in-the-Middle (MITM)</b> attack. "
            "NetSentinel detects this by watching for IP-to-MAC mapping conflicts in ARP traffic.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>Broadcast storms — when traffic eats itself</b><br>"
            "ARP requests, mDNS queries, and DHCP discovery are all <b>broadcasts</b> — "
            "every device on the LAN must process each one. Normally this is a tiny background noise. "
            "But a network loop (two cables between the same two switches), a misconfigured device, "
            "or a compromised machine can generate thousands of broadcasts per second. "
            "Every device spends all its time processing broadcasts and has no capacity left for "
            "real traffic. This looks exactly like an ISP outage — but the problem is entirely local. "
            "The Broadcast Storm tab shows the flood rate and which device is the source.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>DNS — the phone book, and why it affects speed</b><br>"
            "Every website visit starts with a DNS lookup before a single byte of content loads. "
            "If your DNS resolver is slow, <i>every</i> page has a hidden delay. "
            "ISP-provided DNS servers are often 30–100 ms. "
            "Cloudflare (1.1.1.1) and Google (8.8.8.8) are typically under 10 ms from most locations. "
            "A <b>DNS leak</b> happens when your DNS queries bypass your VPN or privacy settings "
            "and go to your ISP instead — revealing every site you visit. "
            "The Health Check tab benchmarks all resolvers side-by-side on your current connection.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>Open ports — what they reveal</b><br>"
            "Every service on a device listens on a numbered <b>port</b>. "
            "Port 22 = SSH (remote terminal), 80 = HTTP, 443 = HTTPS, "
            "3389 = Windows Remote Desktop, 8080 = admin web interfaces. "
            "If a device has unexpected management ports open — especially from the WAN — "
            "it may be misconfigured or compromised. "
            "A <b>SYN scan</b> (Security Audit mode) sends a half-open TCP connection to each port "
            "and measures whether something replies — fast, precise, and requires admin rights "
            "because it bypasses the normal OS socket layer.<br><br>"

            f"<b style='font-size:12px; color:{ACCENT};'>The Network Grade — what each dimension measures</b><br>"
            "<b>Uptime</b> — % of time your internet target was reachable in the last 24h. "
            "<b>Latency</b> — average RTT to internet; A = under 20 ms, F = over 150 ms. "
            "<b>Jitter</b> — RTT variance; A = under 5 ms, F = over 50 ms. "
            "<b>DNS Speed</b> — fastest resolver found vs slowest. "
            "<b>Download Speed</b> — measured against your expected throughput. "
            "<b>Device Safety</b> — any HIGH or CRITICAL risk devices drag this down. "
            "<b>STP Health</b> — any rogue bridge detected = instant F. "
            "<b>Storm Level</b> — broadcast packets per second vs your LAN capacity."
            "</div>"
        )
        learn_text.setWordWrap(True)
        learn_text.setTextFormat(Qt.TextFormat.RichText)
        lcl.addWidget(learn_text)
        bl.addWidget(learn_card)

        # ── Appearance / Theme → redirect to Settings ─────────────────────────
        appear_callout = QFrame()
        appear_callout.setObjectName("card")
        appear_callout.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        acl = QVBoxLayout(appear_callout)
        acl.setContentsMargins(0, 0, 0, 0)
        acl.setSpacing(0)
        atb = QFrame()
        atb.setFixedHeight(32)
        atb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
        atbl = QHBoxLayout(atb)
        atbl.setContentsMargins(12, 0, 12, 0)
        atl = QLabel("Appearance & Customisation")
        atl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
        atbl.addWidget(atl)
        atbl.addStretch()
        acl.addWidget(atb)
        abody = QWidget()
        abody.setStyleSheet(f"background:{BG_CARD};")
        abl = QHBoxLayout(abody)
        abl.setContentsMargins(16, 10, 16, 12)
        abl.setSpacing(12)
        ainfo = QLabel(
            "Colour themes, display preferences, and shortcuts are managed in one place."
        )
        ainfo.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
        abl.addWidget(ainfo, 1)
        btn_go_settings = QPushButton("⚙  Open Settings")
        btn_go_settings.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{NAV_BAR};"
            f"border:1px solid {ACCENT};border-radius:4px;"
            f"padding:5px 14px;font-size:11px;font-weight:bold;}}"
        )
        btn_go_settings.clicked.connect(
            lambda: self._open_settings_dialog()
        )
        abl.addWidget(btn_go_settings)
        acl.addWidget(abody)
        bl.addWidget(appear_callout)

        # ── Check for updates ─────────────────────────────────────────────────
        update_card = QFrame()
        update_card.setObjectName("card")
        update_card.setStyleSheet(
            f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS};}}"
        )
        ucl = QVBoxLayout(update_card)
        ucl.setContentsMargins(0, 0, 0, 0)
        ucl.setSpacing(0)
        utb = QFrame()
        utb.setFixedHeight(32)
        utb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
        utbl = QHBoxLayout(utb)
        utbl.setContentsMargins(12, 0, 12, 0)
        utl = QLabel("Updates")
        utl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
        utbl.addWidget(utl)
        utbl.addStretch()
        ucl.addWidget(utb)
        ubody = QHBoxLayout()
        ubody.setContentsMargins(12, 8, 12, 10)
        self._update_lbl = QLabel(f"Current version: v{app_ver}")
        self._update_lbl.setStyleSheet(f"font-size:11px;color:{TEXT_PRIMARY};")
        ubody.addWidget(self._update_lbl, 1)
        btn_update = QPushButton("Check for Updates")
        btn_update.setObjectName("btnNetRefresh")
        btn_update.setFixedWidth(140)
        btn_update.clicked.connect(self._check_for_updates)
        ubody.addWidget(btn_update)
        ucl.addLayout(ubody)
        bl.addWidget(update_card)

        bl.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)
        return page

    def _check_for_updates(self):
        """Manual update check from the Help tab button."""
        import urllib.request, json as _json
        from PyQt6.QtWidgets import QApplication
        current = QApplication.applicationVersion()
        self._update_lbl.setText("Checking…")
        QApplication.processEvents()
        try:
            url = "https://api.github.com/repos/ossianericson/netsentinel/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "NetSentinel"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read())
            latest = data.get("tag_name", "").lstrip("v")
            def _ver(s):
                try:
                    return tuple(int(x) for x in s.split("."))
                except ValueError:
                    return (0,)
            if latest and _ver(latest) > _ver(current):
                self._update_lbl.setText(
                    f"Update available: v{latest} (you have v{current}) — "
                    '<a href="https://github.com/ossianericson/netsentinel/releases/latest" '
                    f'style="color:{ACCENT};">Download</a>'
                    ' &nbsp;·&nbsp; or: <code>winget upgrade NetSentinel.NetSentinel</code>'
                )
                self._update_lbl.setOpenExternalLinks(True)
                self._update_lbl.setTextFormat(Qt.TextFormat.RichText)
                self._on_update_available(latest)  # also show the notification bar
            else:
                self._update_lbl.setText(f"You're up to date (v{current})")
        except Exception as exc:
            self._update_lbl.setText(f"Update check failed: {exc}")

    def _show_about(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QApplication
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QFont
        dlg = QDialog(self)
        dlg.setWindowTitle("About NetSentinel")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet(self.styleSheet())
        lay = QVBoxLayout(dlg)
        lay.setSpacing(10)
        lay.setContentsMargins(28, 24, 28, 20)

        title = QLabel("NetSentinel")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{ACCENT};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        version = QLabel(f"Version {QApplication.applicationVersion()}")
        version.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc = QLabel("Network Security Scanner & Connectivity Monitor")
        desc.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)

        author = QLabel("Built by <b>Ossian Ericson</b>")
        author.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:13px;")
        author.setAlignment(Qt.AlignmentFlag.AlignCenter)

        github = QLabel(
            '<a href="https://github.com/ossianericson/netsentinel" '
            f'style="color:{ACCENT};">github.com/ossianericson/netsentinel</a>'
        )
        github.setOpenExternalLinks(True)
        github.setAlignment(Qt.AlignmentFlag.AlignCenter)
        github.setStyleSheet("font-size:12px;")

        btn_close = QPushButton("Close")
        btn_close.setObjectName("btnNetRefresh")
        btn_close.setFixedWidth(100)
        btn_close.clicked.connect(dlg.accept)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        btn_row.addStretch()

        disclaimer = QLabel(
            "For use on networks you own or have explicit authorization to test."
        )
        disclaimer.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer.setWordWrap(True)

        for w in (title, version, desc, author, github):
            lay.addWidget(w)
        lay.addSpacing(8)
        lay.addWidget(disclaimer)
        lay.addSpacing(4)
        lay.addLayout(btn_row)

        dlg.exec()

    def _open_settings_dialog(self):
        """Open App Settings (theme, display preferences) as a persistent non-modal dialog."""
        if not hasattr(self, "_settings_dlg") or self._settings_dlg is None:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout
            dlg = QDialog(self)
            dlg.setWindowTitle("App Settings")
            dlg.resize(660, 540)
            dlg.setStyleSheet(f"QDialog{{background:{BG_DARK};}}")
            lay = QVBoxLayout(dlg)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.addWidget(self._settings_page)
            self._settings_dlg = dlg
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def _open_help_dialog(self):
        """Navigate to Help & Reference in the Education sidebar section."""
        self._nav_rail_go_to("Help & Reference")

    # ── Scan orchestration ───────────────────────────────────────────────────

    @pyqtSlot(list)
    def _run_security_scans(self, tool_labels: list) -> None:
        """Navigate to the first selected security tool page (Phase 1)."""
        if not tool_labels:
            return
        if self._active_count > 0:
            self._set_status("Main scan in progress — please wait before running security tools.")
            return
        self._nav_rail_go_to(tool_labels[0])

    @pyqtSlot()
    def _start_full_scan(self):
        # Track whether this scan was triggered from the home page so we can
        # auto-navigate to Overview once device results arrive.
        self._scan_from_home = (
            hasattr(self, "_home_page")
            and self._stack.currentWidget() is self._home_page
        )
        # Reset UI
        self._m1_result = self._m2_result = self._m3_result = None
        self._m4_result = self._m5_result = None
        self._m1_grouping_active = False
        self._m1_group_btn.setVisible(False)
        self._m1_table.setRowCount(0)
        _add_skeleton_rows(self._m1_table)
        self._m2_table.setRowCount(0)
        self._m3_table.setRowCount(0)
        self._m4_table.setRowCount(0)
        self._m5_outage_table.setRowCount(0)
        self._net_devices_table.setRowCount(0)
        self._graph.reset()
        self._verdict.update("Pre-scan in progress (flushing caches & sweeping subnet)…", "UNKNOWN")
        self._set_scanning(True)
        self._active_count = 0

        # Run pre-scan first (flush + ping sweep), then kick off modules
        from workers.scan_worker import PreScanWorker
        self._prescan_worker = PreScanWorker(flush_caches=True)
        self._prescan_worker.status.connect(self._on_prescan_status)
        self._prescan_worker.done.connect(self._launch_modules)
        self._prescan_worker.start()

    @pyqtSlot(str)
    def _on_prescan_status(self, m: str):
        """Propagate pre-scan progress to the status bar and all module status labels."""
        self._set_status(m)
        for lbl in (self._m1_status, self._m2_status, self._m3_status,
                    self._m4_status, self._m5_status):
            lbl.setText(m)
        if hasattr(self, "_home_page"):
            self._home_page.set_scan_progress(m)

    @pyqtSlot()
    def _launch_modules(self):
        try:
            self._launch_modules_impl()
        except Exception as exc:
            self._set_status(f"Scan startup failed: {exc}")
            self._set_scanning(False)
            self._verdict.update(f"Scan failed to start: {exc}", "HIGH")

    def _launch_modules_impl(self):
        from workers.scan_worker import (
            Module1Worker, Module2Worker, Module3Worker,
            Module4Worker, Module5Worker,
        )

        gateway_ip   = self._net_info.get("gateway") if self._net_info else None
        gateway_mac  = self._net_info.get("gateway_mac") if self._net_info else None
        # Pre-populate rogue MACs from the previous scan (best-effort; M1 and M3 run concurrently)
        rogue_macs: list = []
        if self._m1_result:
            for _d in self._m1_result.get("devices", []):
                _risk = _d.risk_level if not isinstance(_d, dict) else _d.get("risk_level", "")
                _mac  = _d.mac        if not isinstance(_d, dict) else _d.get("mac", "")
                if _risk == "HIGH" and _mac:
                    rogue_macs.append(_mac)

        self._verdict.update("Scan in progress…", "UNKNOWN")
        self._workers.clear()
        self._active_count = 0
        # Refresh network info now that caches have been flushed (Fix #14)
        self._refresh_network_info()

        # Module 1 — always runs
        w1 = Module1Worker(self._offenders_path)
        w1.result.connect(self._on_m1_result)
        w1.status.connect(lambda m: (
            self._set_status(m), self._m1_status.setText(m),
            hasattr(self, "_home_page") and self._home_page.set_scan_progress(m),
        ))
        w1.error.connect(lambda e: self._m1_status.setText(f"Error: {e}"))
        w1.finished.connect(self._on_worker_done)
        self._workers.append(w1)
        self._active_count += 1

        _scan_qs = QSettings("NetSentinel", "NetSentinel")

        # Module 2 — needs admin + Scapy
        if _scan_qs.value("scan/stp_enabled", True, type=bool):
            _stp_dur = _scan_qs.value("scan/stp_duration_s", 10, type=int)
            w2 = Module2Worker(gateway_mac, duration=_stp_dur)
            w2.bpdu_found.connect(self._on_bpdu_found)
            w2.result.connect(self._on_m2_result)
            w2.status.connect(lambda m: (self._set_status(m), self._m2_status.setText(m)))
            w2.error.connect(lambda e: self._m2_status.setText(f"⚠ {e}"))
            w2.finished.connect(self._on_worker_done)
            self._workers.append(w2)
            self._active_count += 1

        # Module 3
        if _scan_qs.value("scan/storm_enabled", True, type=bool):
            _storm_dur = _scan_qs.value("scan/storm_duration_s", 10, type=int)
            w3 = Module3Worker(
                duration=_storm_dur,
                known_rogue_macs=rogue_macs,
            )
            w3.result.connect(self._on_m3_result)
            w3.status.connect(lambda m: (self._set_status(m), self._m3_status.setText(m)))
            w3.error.connect(lambda e: self._m3_status.setText(f"⚠ {e}"))
            w3.finished.connect(self._on_worker_done)
            self._workers.append(w3)
            self._active_count += 1

        # Module 4
        if _scan_qs.value("scan/wifi_enabled", True, type=bool):
            w4 = Module4Worker()
            w4.result.connect(self._on_m4_result)
            w4.status.connect(lambda m: (self._set_status(m), self._m4_status.setText(m)))
            w4.error.connect(lambda e: self._m4_status.setText(f"⚠ {e}"))
            w4.finished.connect(self._on_worker_done)
            self._workers.append(w4)
            self._active_count += 1

        # Module 5
        if _scan_qs.value("scan/dns_enabled", True, type=bool):
            w5 = Module5Worker(gateway_ip=gateway_ip)
            w5.ping_point.connect(self._on_ping_point)
            w5.dns_point.connect(self._on_dns_point)
            w5.result.connect(self._on_m5_result)
            w5.status.connect(lambda m: (self._set_status(m), self._m5_status.setText(m)))
            w5.error.connect(lambda e: self._m5_status.setText(f"⚠ {e}"))
            w5.finished.connect(self._on_worker_done)
            self._workers.append(w5)
            self._active_count += 1
            self._graph_timer.start()

        for w in self._workers:
            w.start()

        # Trigger immediate modem and Deco refresh alongside the scan.
        # The mesh M1-fallback (_check_mesh_autorun) stays active for first runs
        # where _net_info hasn't resolved the gateway yet.
        self._trigger_modem_refresh()
        self._trigger_mesh_refresh()

    # ── Module result handlers ────────────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_m1_result(self, data: dict):
        import time as _t
        self._last_scan_time = _t.time()
        self._m1_result = data
        devices = data.get("devices", [])
        if hasattr(self, "_overview_page") and devices:
            self._overview_page.set_has_results(True)
        if hasattr(self, "_security_overview_page"):
            self._security_overview_page.notify_scan_complete()
        if hasattr(self, "_monitor_overview_page"):
            import datetime as _dt
            self._monitor_overview_page.set_last_scan_time(_dt.datetime.now())
        if hasattr(self, "_home_page") and devices:
            self._home_page._device_count = max(self._home_page._device_count, len(devices))
        self._m1_table.setRowCount(0)
        for d in devices:
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            dtype   = d.device_type if not isinstance(d, dict) else d.get("device_type", "")
            # Fall back to connection_type when device_type is blank
            if not dtype:
                dtype = d.connection_type if not isinstance(d, dict) else d.get("connection_type", "Unknown Device")
            verdict = d.verdict  if not isinstance(d, dict) else d.get("verdict", "")
            _add_row(self._m1_table, [ip, host or "—", mac, vendor, level, dtype, "", "", verdict], level)

        # Re-apply search/chip filter and restore persisted sort (FILTER-1 / FILTER-2)
        self._m1_apply_filter()
        _qs = QSettings("NetSentinel", "NetSentinel")
        _sc = _qs.value("home/m1_sort_col", -1, type=int)
        _so = _qs.value("home/m1_sort_order", 0, type=int)
        if _sc >= 0:
            self._m1_table.sortByColumn(_sc, Qt.SortOrder(_so))

        self._m1_scan_summary = (
            f"✓  {data.get('total_count', 0)} devices scanned — "
            f"{data.get('high_risk_count', 0)} HIGH RISK"
        )
        self._m1_status.setText(self._m1_scan_summary)
        # Mirror into Network Info tab
        self._net_devices_table.setRowCount(0)
        for d in data.get("devices", []):
            level   = d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")
            ip      = d.ip       if not isinstance(d, dict) else d.get("ip", "?")
            host    = d.hostname if not isinstance(d, dict) else d.get("hostname", "")
            mac     = d.mac      if not isinstance(d, dict) else d.get("mac", "?")
            vendor  = d.vendor   if not isinstance(d, dict) else d.get("vendor", "Unknown")
            _add_row(self._net_devices_table, [ip, host or "—", mac, vendor, level], level)

        # ── Baseline diff ────────────────────────────────────────────────────
        try:
            from modules.utils import load_device_baseline, save_device_baseline, diff_devices_against_baseline
            # Convert device objects to plain dicts for the util function
            dev_dicts = []
            for d in data.get("devices", []):
                dev_dicts.append({
                    "mac":      (d.mac      if not isinstance(d, dict) else d.get("mac", "")),
                    "ip":       (d.ip       if not isinstance(d, dict) else d.get("ip", "")),
                    "hostname": (d.hostname if not isinstance(d, dict) else d.get("hostname", "")),
                    "vendor":   (d.vendor   if not isinstance(d, dict) else d.get("vendor", "")),
                })
            baseline = load_device_baseline()
            new_devs = diff_devices_against_baseline(dev_dicts, baseline)
            save_device_baseline(baseline)
            self._bl_table.setRowCount(0)
            if new_devs:
                self._bl_new_lbl.setText(f"⚠  {len(new_devs)} new device(s) detected since last scan!")
                self._bl_new_lbl.setStyleSheet(f"color:{AMBER}; font-size:11px;")
                for nd in new_devs:
                    first = baseline.get((nd.get("mac") or "").lower(), {}).get("first_seen", "—")
                    _add_row(self._bl_table,
                             [nd.get("ip","?"), nd.get("hostname","") or "—",
                              nd.get("mac","?"), nd.get("vendor","Unknown"), first],
                             "MEDIUM")
            else:
                self._bl_new_lbl.setText("✓  No new devices since last scan.")
                self._bl_new_lbl.setStyleSheet(f"color:{GREEN}; font-size:11px;")
        except Exception as _exc:
            self._bl_new_lbl.setText(f"Baseline check failed: {_exc}")

        # ── Feed Network Doc page ─────────────────────────────────────────────
        self._last_scan_devices = data.get("devices", [])
        _cert_data: list = []
        if self._store is not None:
            try:
                for _c in self._store.query_cert_status():
                    _cert_data.append({
                        "host": _c.host,
                        "cn":   _c.subject or "",
                        "issuer":        _c.issuer or "",
                        "not_after":     _c.not_after or "",
                        "days_remaining": _c.days_remaining,
                    })
            except Exception:
                pass
        self._network_doc_page.set_scan_data(
            devices=self._last_scan_devices,
            port_data=self._port_data_cache,
            cert_data=_cert_data,
            topo_widget=getattr(self, "_topology_widget", None),
        )

        # ── Persistent device tracking (MetricStore) ──────────────────────────
        if self._store is not None:
            try:
                from modules.device_tracker import DeviceTracker
                if not hasattr(self, "_device_tracker"):
                    self._device_tracker = DeviceTracker(self._store)
                tr = self._device_tracker.process_scan(data.get("devices", []))
                self._last_scan_new  = len(tr.new_devices)
                self._last_scan_gone = len(tr.gone_devices)
                if tr.new_devices:
                    msgs = [f"{d.ip or d.mac} ({d.vendor or 'Unknown'})"
                            for d in tr.new_devices[:3]]
                    extra = f" +{len(tr.new_devices)-3} more" if len(tr.new_devices) > 3 else ""
                    status_msg = f"🆕 {len(tr.new_devices)} new device(s): {', '.join(msgs)}{extra}"
                    self._set_status(status_msg)
                    # Tray notification — only if user opted in
                    from PyQt6.QtCore import QSettings as _QS
                    if (
                        self._tray_manager.is_available()
                        and _QS("NetSentinel", "NetSentinel").value(
                            "tray/notify_new_device", False, type=bool
                        )
                    ):
                        summary = ", ".join(
                            f"{d.ip or d.mac}" for d in tr.new_devices[:2]
                        )
                        if len(tr.new_devices) > 2:
                            summary += f" +{len(tr.new_devices)-2} more"
                        self._tray_manager.show_notification(
                            "New Device Joined",
                            summary,
                            "WARNING",
                        )
                        self._tray_manager.increment_badge()
                if tr.gone_devices:
                    gone_msgs = [f"{d.ip or d.mac}" for d in tr.gone_devices[:2]]
                    self._set_status(
                        f"⚠  {len(tr.gone_devices)} device(s) gone: {', '.join(gone_msgs)}"
                    )
                # Feed tracker result into alert engine + MQTT
                if self._alert_engine is not None:
                    for a in self._alert_engine.evaluate_tracker_result(tr):
                        self._show_alert_toast(a)
                        self._home_page.on_alert(a)
                        self._mqtt_page.on_alert(a.severity, a.message, a.host)
                # Forward device events to MQTT publisher
                for _d in tr.new_devices:
                    self._mqtt_page.on_device_event("joined", {
                        "mac": _d.mac or "", "ip": _d.ip or "",
                        "hostname": _d.hostname or "", "vendor": _d.vendor or "",
                    })
                for _d in tr.gone_devices:
                    self._mqtt_page.on_device_event("left", {
                        "mac": _d.mac or "", "ip": _d.ip or "",
                        "hostname": _d.hostname or "", "vendor": _d.vendor or "",
                    })
            except Exception:
                pass   # tracker errors must never break the scan result handler

        # ── Feed Geo Map with discovered device IPs (public ones auto-filtered) ─
        try:
            _ips = [
                (d.ip if not isinstance(d, dict) else d.get("ip", ""))
                for d in data.get("devices", [])
            ]
            self._geo_map_page.add_ips([ip for ip in _ips if ip])
        except Exception:
            pass

        # ── Start / refresh AvailabilityWorker after each scan ────────────────
        try:
            if self._store is not None and data.get("devices"):
                from workers.availability_worker import AvailabilityWorker
                from modules.availability_monitor import TargetConfig
                _targets = []
                for _d in data.get("devices", []):
                    _ip  = _d.ip       if not isinstance(_d, dict) else _d.get("ip", "")
                    _mac = _d.mac      if not isinstance(_d, dict) else _d.get("mac", "")
                    _hn  = _d.hostname if not isinstance(_d, dict) else _d.get("hostname", "")
                    if _ip:
                        _targets.append(TargetConfig(
                            host=_ip, mac=_mac or None,
                            hostname=_hn or None, label=_hn or _ip,
                        ))
                if _targets:
                    if hasattr(self, "_avail_worker") and self._avail_worker.isRunning():
                        self._avail_worker.set_targets(_targets)
                    else:
                        self._avail_worker = AvailabilityWorker(
                            store=self._store, targets=_targets, interval_s=60,
                        )
                        self._avail_worker.cycle_done.connect(self._on_avail_cycle_done)
                        self._avail_worker.start()
        except Exception:
            pass

        self._update_overall_verdict()
        self._update_kpi_tiles(data)
        # Show the table (hide the empty-state placeholder)
        self._m1_stack.setCurrentIndex(1)
        # Show benchmark content pane (user can now grade without being sent elsewhere)
        if hasattr(self, "_bm_stack"):
            self._bm_stack.setCurrentIndex(1)
        # Refresh topology widget with new device list
        try:
            gw_ip  = self._net_info.get("gateway") if self._net_info else None
            gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
            self._topology_widget.render(
                data.get("devices", []), gw_ip, gw_mac,
                mesh_units=getattr(self, "_mesh_units", None),
                mesh_enrichment=getattr(self, "_mesh_enrichment", None),
                modem_data=getattr(self, "_last_modem_data", None),
            )
        except AttributeError:
            pass  # topology widget not yet initialised
        except Exception as _topo_exc:
            self._set_status(f"Topology render error: {_topo_exc}")
        # Re-apply any active NL search now that new data is loaded
        if hasattr(self, "_m1_search") and self._m1_search.text().strip():
            self._filter_m1_by_nl(self._m1_search.text())

        self._compute_suggestions()

        # DEVICE-5: auto-snapshot when setting is on
        try:
            _qs_d5 = QSettings("NetSentinel", "NetSentinel")
            if _qs_d5.value("baseline/auto_snapshot", False, type=bool) and self._store is not None:
                from modules.config_baseline import (
                    build_snapshot_from_scan,
                    diff_snapshots,
                    list_snapshots as _ls,
                    store_snapshot as _ss,
                    delete_snapshot as _ds,
                )
                import datetime as _dt_d5
                _label = f"Auto · {_dt_d5.datetime.now().strftime('%Y-%m-%d %H:%M')}"
                _dev_dicts = []
                for _d in data.get("devices", []):
                    _dev_dicts.append({
                        "mac":      (_d.mac      if not isinstance(_d, dict) else _d.get("mac", "")),
                        "ip":       (_d.ip       if not isinstance(_d, dict) else _d.get("ip", "")),
                        "hostname": (_d.hostname if not isinstance(_d, dict) else _d.get("hostname", "")),
                        "vendor":   (_d.vendor   if not isinstance(_d, dict) else _d.get("vendor", "")),
                        "open_ports": (list(getattr(_d, "open_ports", [])) if not isinstance(_d, dict) else _d.get("open_ports", [])),
                    })
                _new_snap = build_snapshot_from_scan(_dev_dicts, label=_label)

                # Load previous auto-snapshots for drift check
                _all_snaps = _ls(self._store, limit=200)
                _auto_snaps = [s for s in _all_snaps if (s.label or "").startswith("Auto ·")]

                _prev = _auto_snaps[0] if _auto_snaps else None
                if _prev:
                    _diff = diff_snapshots(_prev, _new_snap)
                    if _diff.has_drift:
                        self._baseline_has_drift = True
                        self._refresh_section_badges()
                        from ui.widgets.toast import ToastManager
                        ToastManager.show(
                            f"Baseline drift: {_diff.summary()} — Config Snapshots",
                            "info",
                        )

                _ss(self._store, _new_snap)

                # Keep only last 10 auto-snapshots; never touch manually-labelled ones
                _all_snaps2 = _ls(self._store, limit=200)
                _auto_only = [s for s in _all_snaps2 if (s.label or "").startswith("Auto ·")]
                for _old in _auto_only[10:]:
                    try:
                        _ds(self._store, _old.id)
                    except Exception:
                        pass
        except Exception:
            pass  # auto-snapshot errors must never break the scan result handler


        # Auto-navigate to Overview on the very first scan only (home page onboarding).
        # After that the user knows the app — leave them where they are.
        _qs = QSettings("NetSentinel", "NetSentinel")
        _first_scan = not _qs.value("app/has_scanned_before", False, type=bool)
        if getattr(self, "_scan_from_home", False) and len(devices) > 0 and _first_scan:
            self._scan_from_home = False
            _qs.setValue("app/has_scanned_before", True)
            self._nav_rail_go_to("Overview")

        # Re-apply cached mesh/plugin enrichment immediately so names/nodes are
        # visible without waiting for the async worker.
        if self._mesh_enrichment or any(self._plugin_enrichments.values()):
            self._apply_mesh_enrichment()

        # Mesh enrichment — show button when a gateway is found; auto-run if
        # the user has already entered their mesh password this session.
        self._check_mesh_autodetect(data)
        self._check_hw_autodetect()

        # Push cached modem signal to the Modem page so it shows fresh data
        # immediately after a network scan, without waiting for the next 30 s poll.
        if getattr(self, "_last_modem_data", None) and hasattr(self, "_modem_page"):
            self._modem_page.on_modem_signal(self._last_modem_data)

        # Fetch WAN IP in background so geo map can resolve LAN devices later
        if not self._wan_ip:
            self._fetch_wan_ip()

        # Integration discovery banner — show when scanned devices match a
        # bundled plugin gateway that isn't already imported
        self._check_integration_banner(devices)

        # OUTPUT-4: post-scan summary sheet
        if hasattr(self, "_scan_sheet") and self._store is not None:
            try:
                import time as _t_o4
                _pending = [
                    a for a in self._store.get_recent_alerts(hours=24)
                    if not a.get("acked_ts")
                ]
                self._scan_sheet.show_sheet(
                    total_devices=len(devices),
                    new_devices=getattr(self, "_last_scan_new", 0),
                    missing_devices=getattr(self, "_last_scan_gone", 0),
                    pending_alerts=len(_pending),
                    baseline_diffs=1 if getattr(self, "_baseline_has_drift", False) else 0,
                    new_cves=0,
                )
            except Exception:
                pass

    def _fetch_wan_ip(self) -> None:
        """Fetch the public WAN IP once per session in a background thread."""
        import threading

        def _do():
            try:
                from modules.internet_exposure import _get_wan_ip
                ip, _ = _get_wan_ip()
                if ip:
                    self._wan_ip = ip
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self._geo_map_page.set_home_ip(ip))
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    def _show_ip_on_geo_map(self, ip: str) -> None:
        """Navigate to Geolocation Map and pin the given IP (from right-click).

        For private/LAN addresses the public WAN IP is used instead, since every
        device on the same network shares the same internet-facing location.
        """
        import ipaddress
        try:
            addr = ipaddress.ip_address(ip)
            is_private = addr.is_private or addr.is_loopback or addr.is_link_local
        except ValueError:
            is_private = False

        self._nav_rail_go_to("Geolocation Map")

        if is_private:
            if self._wan_ip:
                self._geo_map_page.navigate_to_ip(
                    self._wan_ip, label=f"Your Network  (local: {ip})"
                )
            else:
                # WAN IP not yet known — show placeholder then fetch and update
                self._geo_map_page._detail_ip.setText(ip)
                self._geo_map_page._detail_body.setText(
                    "Resolving your public WAN IP…\n"
                    "This takes a few seconds on first use."
                )
                self._geo_map_page._detail_links.setText("")
                import threading
                def _do_and_update():
                    try:
                        from modules.internet_exposure import _get_wan_ip
                        wan, _ = _get_wan_ip()
                        if wan:
                            self._wan_ip = wan
                            from PyQt6.QtCore import QTimer
                            QTimer.singleShot(0, lambda: (
                                self._geo_map_page.set_home_ip(wan),
                                self._geo_map_page.navigate_to_ip(
                                    wan, label=f"Your Network  (local: {ip})"
                                ),
                            ))
                    except Exception:
                        pass
                threading.Thread(target=_do_and_update, daemon=True).start()
        else:
            try:
                self._geo_map_page.navigate_to_ip(ip, label="Threat Intel")
            except Exception:
                pass

    # ── Mesh enrichment ────────────────────────────────────────────────────────

    def _check_mesh_autodetect(self, m1_data: dict) -> None:
        """Pre-fill gateway IP on Mesh & Router page; auto-run if keyring has saved creds."""
        gateway_ip = m1_data.get("gateway_ip")
        if not gateway_ip:
            return
        if hasattr(self, "_mesh_router_page"):
            self._mesh_router_page.set_gateway_ip(gateway_ip)
        self._check_mesh_autorun(gateway_ip)

    def _check_mesh_autorun(self, gateway_ip: str) -> None:
        """Re-fetch mesh data on every scan if keyring has credentials for gateway_ip."""
        # Skip if a previous fetch is still in flight
        existing = getattr(self, "_mesh_auto_worker", None)
        if existing and existing.isRunning():
            return
        try:
            import keyring as _kr
            pw = _kr.get_password("NetSentinel/mesh", gateway_ip)
        except Exception:
            return
        if not pw:
            return
        from workers.mesh_worker import MeshWorker
        worker = MeshWorker(host=gateway_ip, password=pw)
        # Route through the page's own handler so its UI gets populated;
        # scan_done from there fires _on_mesh_result for enrichment.
        worker.result.connect(self._mesh_router_page._on_result)
        worker.status.connect(lambda msg: self._m1_status.setText(
            f"{getattr(self, '_m1_scan_summary', '')}  ·  {msg}"
        ), Qt.ConnectionType.QueuedConnection)
        # Keep a reference so the thread isn't garbage-collected mid-run
        self._mesh_auto_worker = worker
        worker.start()

    def _check_hw_autodetect(self) -> None:
        """Run hardware catalogue detection once per gateway IP per session."""
        gw_ip  = (self._net_info or {}).get("gateway", "").strip()
        gw_mac = (self._net_info or {}).get("gateway_mac", "").strip()
        if not gw_ip:
            return
        # Only re-run when the gateway IP changes (avoid redundant HTTP probes)
        if getattr(self, "_hw_detect_last_gw", "") == gw_ip:
            return
        existing = getattr(self, "_hw_detect_worker", None)
        if existing and existing.isRunning():
            return
        self._hw_detect_last_gw = gw_ip
        from workers.hw_detect_worker import HwDetectWorker
        worker = HwDetectWorker(ip=gw_ip, gateway_mac=gw_mac or None, parent=self)
        worker.detected.connect(self._on_hw_detected)
        self._hw_detect_worker = worker
        worker.start()

    @pyqtSlot(list)
    def _on_hw_detected(self, matches: list) -> None:
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.on_hardware_detected(matches)

    def _plugin_gateway_map(self) -> dict:
        """Return {ip: plugin_name} for all bundled plugins. Cached per session; cleared by _clear_plugin_gateway_cache."""
        if hasattr(self, "_plugin_gateway_map_cache"):
            return self._plugin_gateway_map_cache
        import ast
        plugins_dir = Path(__file__).parent.parent / "plugins"
        result: dict = {}
        if not plugins_dir.is_dir():
            self._plugin_gateway_map_cache = result
            return result
        for py in plugins_dir.glob("*.py"):
            try:
                tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
                ip = name = None
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign):
                        for t in node.targets:
                            if isinstance(t, ast.Name):
                                if t.id == "HARDWARE_IP" and isinstance(node.value, ast.Constant):
                                    ip = node.value.value
                                elif t.id == "HARDWARE_NAME" and isinstance(node.value, ast.Constant):
                                    name = node.value.value
                if ip and name:
                    result[ip] = name
            except Exception:
                continue
        self._plugin_gateway_map_cache = result
        return result

    def _check_integration_banner(self, devices: list) -> None:
        """Show discovery banner when a scanned device matches an un-imported bundled plugin."""
        if not hasattr(self, "_m1_int_banner"):
            return
        try:
            gateway_map = self._plugin_gateway_map()
            if not gateway_map:
                self._m1_int_banner.setVisible(False)
                return

            # Find which plugin IPs are already imported
            from PyQt6.QtCore import QSettings as _QS
            _imported_paths = set(
                _QS("NetSentinel", "NetSentinel").value("hardware/plugin_paths", [], type=list)
            )
            import ast
            imported_ips: set = set()
            for p in _imported_paths:
                try:
                    tree = ast.parse(Path(p).read_text(encoding="utf-8", errors="replace"))
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            for t in node.targets:
                                if (isinstance(t, ast.Name) and t.id == "HARDWARE_IP"
                                        and isinstance(node.value, ast.Constant)):
                                    imported_ips.add(node.value.value)
                except Exception:
                    continue

            # Collect scanned IPs
            scanned_ips = {
                (d.ip if not isinstance(d, dict) else d.get("ip", ""))
                for d in devices
            }

            # Find matches: gateway IP in scan AND plugin not yet imported
            matches = [
                name for ip, name in gateway_map.items()
                if ip in scanned_ips and ip not in imported_ips
            ]

            if matches:
                names = ", ".join(matches[:3])
                if len(matches) > 3:
                    names += f" +{len(matches) - 3} more"
                self._m1_int_lbl.setText(
                    f"⚡  Hardware detected — {names} available for integration"
                )
                self._m1_int_banner.setVisible(True)
            else:
                self._m1_int_banner.setVisible(False)
        except Exception:
            self._m1_int_banner.setVisible(False)

    @pyqtSlot(dict)
    def _on_mesh_result(self, data: dict) -> None:
        """Receive scan result from MeshRouterPage and enrich the Devices table."""
        from modules.deco_client import _norm_mac
        clients  = data.get("clients", [])
        provider = data.get("provider", "mesh").title()
        self._mesh_units      = data.get("units", [])
        self._mesh_enrichment = {c.mac: c for c in clients}
        self._apply_mesh_enrichment()
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.on_mesh_card_data(
                self._mesh_units, clients, provider
            )
        matched  = sum(1 for c in clients if c.mac in self._mesh_enrichment)
        summary  = getattr(self, "_m1_scan_summary", "")
        self._m1_status.setText(
            f"{summary}  ·  {provider}: {matched} device{'s' if matched != 1 else ''} enriched"
        )
        # Monitor logging — live entry + throttled DB write
        if hasattr(self, "_log_hub_page"):
            from PyQt6.QtCore import QSettings
            import time as _time
            s = QSettings()
            if s.value("logging/mesh_enabled", False, type=bool):
                self._log_hub_page.add_mesh_entry(data)
                interval_s = s.value("logging/mesh_interval_min", 5, type=int) * 60
                now = _time.time()
                if self._store and now - self._last_mesh_log_ts >= interval_s:
                    units        = self._mesh_units
                    unit_count   = len(units)
                    online_count = sum(1 for u in units if getattr(u, "online", True))
                    worst_name, worst_rssi = None, None
                    for u in units:
                        rssi = getattr(u, "rssi", None) or getattr(u, "signal_level", None)
                        if rssi is not None and (worst_rssi is None or rssi < worst_rssi):
                            worst_rssi = rssi
                            worst_name = getattr(u, "name", "") or getattr(u, "device_id", "")
                    try:
                        self._store.record_mesh_snapshot(
                            unit_count=unit_count,
                            online_count=online_count,
                            worst_unit=worst_name,
                            worst_rssi=worst_rssi,
                        )
                        self._last_mesh_log_ts = now
                    except Exception:
                        pass

    @pyqtSlot(dict)
    def _on_hardware_plugin_result(self, data: dict) -> None:
        """Route a successful plugin Test result to the relevant existing page.

        modem plugins  → Modem page + Overview tile (via _on_modem_signal)
        router/ap/mesh → Devices table hostname enrichment (via _plugin_enrichments[path])
        """
        import time as _t
        from modules.deco_client import _norm_mac

        info    = data.get("info", {})
        status  = data.get("status", {})
        clients = data.get("clients", [])
        hw_type = info.get("type", "")
        hw_name = info.get("name", "plugin")
        self._plugin_hardware_name = hw_name

        # Clear discovery banner cache so next scan re-evaluates imported plugins
        self.__dict__.pop("_plugin_gateway_map_cache", None)

        # ── Modem plugins: route signal to Modem page + Overview tile ─────────
        if hw_type == "modem":
            # Track which plugin page corresponds to the active modem
            _modem_path = data.get("_path", hw_name)
            if _modem_path in getattr(self, "_plugin_pages", {}):
                self._active_modem_plugin_label = self._plugin_pages[_modem_path]._label
            extra = status.get("extra", {})
            self._on_modem_signal({
                "ts":               int(_t.time()),
                "wan_ip":           status.get("wan_ip"),
                "wan_status":       status.get("wan_status"),
                "firmware_version": extra.get("firmware"),
                "network_type":     extra.get("network_type"),
                "signal_bars":      extra.get("signal_bars"),
                "mcc":              extra.get("mcc"),
                "mnc":              extra.get("mnc"),
                "cell_id":          extra.get("cell_id"),
                "enb_id":           extra.get("enb_id"),
                "nr5g_rsrp_dbm":    extra.get("nr5g_rsrp_dbm"),
                "nr5g_sinr_db":     extra.get("nr5g_sinr_db"),
                "nr5g_rsrq_db":     extra.get("nr5g_rsrq_db"),
                "nr5g_band":        extra.get("nr5g_band"),
                "nr5g_pci":         extra.get("nr5g_pci"),
                "nr5g_arfcn":       extra.get("nr5g_arfcn"),
                "lte_rsrp_dbm":     extra.get("lte_rsrp_dbm"),
                "lte_snr_db":       extra.get("lte_snr_db"),
                "lte_rsrq_db":      extra.get("lte_rsrq_db"),
                "lte_band":         extra.get("lte_band"),
                "lte_pci":          extra.get("lte_pci"),
                "lte_earfcn":       extra.get("lte_earfcn"),
                "endc_info":        extra.get("endc_info"),
            })
            path = data.get("_path", hw_name)
            if path in getattr(self, "_plugin_pages", {}):
                self._plugin_pages[path].update(data)
            self._refresh_hardware_badge()
            if hasattr(self, "_log_hub_page"):
                _plugin_names = [pg._label for pg in getattr(self, "_plugin_pages", {}).values()]
                self._log_hub_page.add_plugin_entry(data)
                self._log_hub_page.update_plugin_sources(_plugin_names)
                _qs_key = hw_name.lower().replace(" ", "_")
                from PyQt6.QtCore import QSettings as _QS_pl
                if self._store and _QS_pl().value(f"logging/plugin_{_qs_key}_enabled", False, type=bool):
                    self._store.record_plugin_snapshot(hw_name, data)
            return  # modem plugins have no LAN clients to enrich

        # ── Router/AP/mesh plugins: enrich Devices table + topology ──────────
        path = data.get("_path", hw_name)
        self._plugin_enrichments[path] = {
            _norm_mac(c.get("mac", "")): c
            for c in clients
            if c.get("mac")
        }
        # Store node list so topology can group devices by AP/satellite.
        # If the plugin returned clients but no nodes (single-AP router),
        # synthesize one node so topology and "Group by node" still work.
        nodes = status.get("extra", {}).get("nodes", [])
        if not nodes and clients and hw_type in ("router", "mesh", "ap"):
            nodes = [{"name": hw_name, "role": "primary",
                      "ip": info.get("ip", ""), "mac": ""}]
        self._plugin_nodes[path] = nodes
        self._apply_mesh_enrichment()  # handles topology + regrouping + synthesis
        from modules.network_infrastructure import hw_state
        hw_state.update_router(clients, nodes, source=path, hw_name=hw_name)
        n = len(self._plugin_enrichments[path])
        if hasattr(self, "_m1_status"):
            summary = getattr(self, "_m1_scan_summary", "")
            self._m1_status.setText(
                f"{summary}  ·  {hw_name}: {n} device{'s' if n != 1 else ''} enriched"
            )

        # Update plugin device page (modem path returns early above, so this
        # only runs for router/AP/switch types).
        if path in getattr(self, "_plugin_pages", {}):
            self._plugin_pages[path].update(data)

        self._refresh_hardware_badge()
        if hasattr(self, "_log_hub_page"):
            _plugin_names = [pg._label for pg in getattr(self, "_plugin_pages", {}).values()]
            self._log_hub_page.add_plugin_entry(data)
            self._log_hub_page.update_plugin_sources(_plugin_names)
            _qs_key = hw_name.lower().replace(" ", "_")
            from PyQt6.QtCore import QSettings as _QS_pl
            if self._store and _QS_pl().value(f"logging/plugin_{_qs_key}_enabled", False, type=bool):
                self._store.record_plugin_snapshot(hw_name, data)

    def _update_monitor_badge(self, _active: bool = False) -> None:
        """Refresh all section badges and Home pills when log source state changes."""
        self._push_monitor_pills()

    def _refresh_section_badges(self, *, arp: bool = None, dhcp: bool = None,
                                 storm: bool = None, logger: bool = None) -> None:
        """Update rail section button dots for Monitor, Analysis, and Security Audit."""
        if not hasattr(self, "_nav_rail_buttons"):
            return
        if arp is None:
            arp = bool(self._arp_worker and self._arp_worker.isRunning())
        if dhcp is None:
            dhcp = bool(self._dhcp_worker and self._dhcp_worker.isRunning())
        if storm is None:
            storm = self._m3_monitoring_active()
        if logger is None:
            qs = QSettings("NetSentinel", "NetSentinel")
            logger = any(
                qs.value(k, False, type=bool)
                for k in qs.allKeys()
                if k.startswith("logging/") and k.endswith("_enabled")
            )
        # Monitor — left dot: green when any log source is active, muted when idle
        mon_btn = self._nav_rail_buttons.get("Monitor")
        if mon_btn:
            mon_btn.set_badge("")   # top-right badge not used for Monitor
            mon_btn.set_left_dot(GREEN if logger else TEXT_MUTED)
        # Analysis — left dot: green when ARP watch or broadcast storm is running
        ana_btn = self._nav_rail_buttons.get("Analysis")
        if ana_btn:
            ana_btn.set_badge("")   # top-right badge not used for Analysis
            ana_btn.set_left_dot(GREEN if (arp or storm) else TEXT_MUTED)
        # Security Audit — numeric red pill when unacked alerts exist, green dot when DHCP running
        sec_btn = self._nav_rail_buttons.get("Security Audit")
        if sec_btn:
            try:
                alert_count = len(self._store.get_unacked_alerts()) if self._store else 0
            except Exception:
                alert_count = 0
            if alert_count > 0:
                sec_btn.set_badge(alert_count)   # numeric red pill
                sec_btn.setToolTip(f"Security Audit — {alert_count} unacknowledged alert(s)")
            elif dhcp:
                sec_btn.set_badge(GREEN)
                sec_btn.setToolTip("Security Audit")
            else:
                sec_btn.set_badge(0)
                sec_btn.setToolTip("Security Audit")

        # POLISH-2: CVE Tracker — count of Open-state CVEs
        cve_btn = self._nav_rail_buttons.get("CVE Tracker")
        if cve_btn and self._store:
            try:
                open_cves = len(self._store.list_cve_lifecycles(state_filter="Open"))
            except Exception:
                open_cves = 0
            cve_btn.set_badge(open_cves if open_cves > 0 else 0)
            if open_cves:
                cve_btn.setToolTip(f"CVE Tracker — {open_cves} open CVE{'s' if open_cves != 1 else ''}")

        # POLISH-2: TLS & Exposure — count of expiring / expired certs
        tls_btn = self._nav_rail_buttons.get("TLS & Exposure")
        if tls_btn and self._store:
            try:
                certs = self._store.query_cert_status(hours=168)
                expired  = sum(1 for c in certs if getattr(c, "is_expired", False))
                expiring = sum(
                    1 for c in certs
                    if not getattr(c, "is_expired", False)
                    and 0 <= (getattr(c, "days_remaining", 999) or 999) <= 30
                )
            except Exception:
                expired = expiring = 0
            cert_total = expired + expiring
            if cert_total > 0:
                tls_btn.set_badge(RED if expired > 0 else AMBER)
                tls_btn.setToolTip(
                    f"TLS & Exposure — {expired} expired, {expiring} expiring soon"
                    if expired else f"TLS & Exposure — {expiring} cert{'s' if expiring != 1 else ''} expiring soon"
                )
            else:
                tls_btn.set_badge(0)

        # POLISH-2: Config Snapshots — drift indicator "≠" when auto-snapshot drifted
        base_btn = self._nav_rail_buttons.get("Config Snapshots")
        if base_btn:
            if getattr(self, "_baseline_has_drift", False):
                base_btn.set_badge(AMBER)
                base_btn.setToolTip("Config Snapshots — baseline drift detected")
            else:
                base_btn.set_badge(0)

    def _check_weekly_digest(self) -> None:
        """Fire a weekly digest notification if conditions are met (RECUR-2)."""
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("notif/weekly_digest_enabled", False, type=bool):
            return
        now = datetime.datetime.now()
        if now.weekday() != 6:  # Sunday only
            return
        time_str = qs.value("notif/weekly_digest_time", "09:00")
        try:
            h, m = (int(x) for x in time_str.split(":"))
        except Exception:
            return
        if now.hour < h or (now.hour == h and now.minute < m):
            return
        last_ts = float(qs.value("notif/weekly_digest_last_ts", 0))
        if now.timestamp() - last_ts < 6 * 86400:
            return
        qs.setValue("notif/weekly_digest_last_ts", now.timestamp())
        if hasattr(self, "_notifications_page"):
            body = self._notifications_page._generate_weekly_summary()
        else:
            body = "NetSentinel weekly digest"
        if self._notif_router:
            try:
                from modules.notification_router import Alert as _Alert
                alert = _Alert(
                    rule_name="Weekly Digest",
                    rule_type="WEEKLY_DIGEST",
                    severity="INFO",
                    host="NetSentinel",
                    message=body,
                )
                self._notif_router.dispatch(alert)
            except Exception:
                pass

    def _set_flyout_dot(self, label: str, color: str) -> None:
        """Set or clear a status dot on a flyout item by label."""
        if not hasattr(self, "_flyout_dots"):
            self._flyout_dots: dict[str, str] = {}
        self._flyout_dots[label] = color
        if hasattr(self, "_nav_flyout"):
            self._nav_flyout.apply_dot(label, color)

    def _push_monitor_pills(self) -> None:
        """Push current monitoring states to Home pills, flyout dots, and section badges."""
        arp    = bool(self._arp_worker  and self._arp_worker.isRunning())
        dhcp   = bool(self._dhcp_worker and self._dhcp_worker.isRunning())
        storm  = self._m3_monitoring_active()
        qs     = QSettings("NetSentinel", "NetSentinel")
        logger = any(
            qs.value(k, False, type=bool)
            for k in qs.allKeys()
            if k.startswith("logging/") and k.endswith("_enabled")
        )
        if hasattr(self, "_home_page"):
            self._home_page.set_monitor_pills(arp, dhcp, storm, logger)
            if self._store is not None:
                try:
                    unacked = self._store.get_unacked_alerts()
                    offline = sum(
                        1 for d in self._store.get_known_devices().values()
                        if getattr(d, "last_seen", 0) and
                        (__import__("time").time() - d.last_seen) > 1800
                    )
                    self._home_page.set_action_needed(len(unacked), offline)
                    self._home_page.set_pending_alert_rows(unacked)
                except Exception:
                    pass
        # Flyout item dots — always reflect current state
        self._set_flyout_dot("ARP Spoof Watch",    GREEN if arp    else "")
        self._set_flyout_dot("DHCP Rogue Monitor", GREEN if dhcp   else "")
        self._set_flyout_dot("Broadcast Storm",    GREEN if storm  else "")
        self._set_flyout_dot("Network Logger",     GREEN if logger else "")
        # AUTO-1/2: Automation dot and tile — green if any rule fired in last 24h
        try:
            from modules.automation_hooks import get_engine as _get_ae
            _ae = _get_ae()
            _auto_ts = _ae.get_last_triggered()
            _auto_rules = _ae.get_rules()
            import time as _t
            _auto_active = _auto_ts > 0 and (_t.time() - _auto_ts) < 86400
            self._set_flyout_dot("Automation Hooks", GREEN if _auto_active else "")
            if hasattr(self, "_monitor_overview_page"):
                self._monitor_overview_page.set_automation_status(
                    len(_auto_rules), _auto_ts
                )
        except Exception:
            pass
        # Section button badges
        self._refresh_section_badges(arp=arp, dhcp=dhcp, storm=storm, logger=logger)
        # Push to Monitor Overview page
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_arp_status(arp, alerted=False)
            self._monitor_overview_page.set_dhcp_status(dhcp)
            if self._store is not None:
                try:
                    self._monitor_overview_page.set_monitor_event_times(
                        arp=self._store.get_last_event_time("ARP"),
                        dhcp=self._store.get_last_event_time("DHCP"),
                        storm=self._store.get_last_event_time("Storm"),
                        iot=self._store.get_last_event_time("IoT"),
                        ports=self._store.get_last_event_time("Port"),
                        cve=self._store.get_last_event_time("CVE"),
                    )
                except Exception:
                    pass

    def _m3_monitoring_active(self) -> bool:
        """Return True if any scan worker (including storm) is currently running."""
        return any(
            w.isRunning()
            for w in getattr(self, "_workers", [])
            if hasattr(w, "isRunning")
        )

    def _refresh_hardware_badge(self) -> None:
        """Update the Extend section rail button tooltip to show active plugin count."""
        n = len(getattr(self, "_plugin_pages", {}))
        if n == 0:
            return
        btn = self._nav_rail_buttons.get("Extend")
        if btn:
            btn.setToolTip(f"Extend — {n} plugin{'s' if n != 1 else ''} active")

    @pyqtSlot(str)
    def _on_plugin_page_test(self, path: str) -> None:
        """Run the plugin once immediately when the Test button is clicked.

        Delegates to HardwareIntegrationPage._run_plugin so that:
        - only one PluginPollingWorker exists per plugin (no duplicate logins)
        - all signal connections are QObject→QObject (auto-queued, thread-safe)
        - the result flows through the existing plugin_result→_on_hardware_plugin_result
          path which calls page.update(data) → test_done()
        """
        self._hardware_integration_page._run_plugin(path)

    def _apply_mesh_enrichment(self) -> None:
        """Merge MeshClient and plugin client data into the M1 table rows."""
        if not self._m1_result:
            return
        # Merge all per-plugin enrichment dicts into one flat MAC→client map
        _all_plugin: dict = {}
        for _pe in self._plugin_enrichments.values():
            _all_plugin.update(_pe)
        if not self._mesh_enrichment and not _all_plugin:
            return

        from PyQt6.QtGui import QColor
        from modules.deco_client import _norm_mac

        _mac_re = __import__("re").compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", __import__("re").I)
        any_matched = False
        plugin_any_matched = False

        for row in range(self._m1_table.rowCount()):
            mac_item = self._m1_table.item(row, 2)
            if not mac_item:
                continue
            mc = self._mesh_enrichment.get(_norm_mac(mac_item.text()))
            if not mc:
                continue

            any_matched = True

            # Override hostname (col 1) with Deco-assigned name when it looks like a real name
            if mc.name and not _mac_re.match(mc.name):
                name_item = QTableWidgetItem(mc.name)
                name_item.setForeground(QColor(TEXT_PRIMARY))
                name_item.setToolTip("Name assigned in Deco app")
                self._m1_table.setItem(row, 1, name_item)

            # Node column (col 6)
            node_item = QTableWidgetItem(mc.unit_name)
            node_item.setForeground(QColor(TEXT_PRIMARY))
            self._m1_table.setItem(row, 6, node_item)

            # Band column (col 7) with speed tooltip
            band_item = QTableWidgetItem(mc.band)
            band_item.setForeground(QColor(TEXT_PRIMARY))
            band_item.setToolTip(
                f"Upload:   {mc.upload_kbps} KB/s\n"
                f"Download: {mc.download_kbps} KB/s"
            )
            self._m1_table.setItem(row, 7, band_item)

        # Reveal Node and Band columns once any Deco data is present
        if any_matched:
            self._m1_table.setColumnHidden(6, False)
            self._m1_table.setColumnHidden(7, False)
            if self._m1_group_by_node:
                self._regroup_m1_by_satellite()

        # Plugin enrichment — update hostname column for any matching MAC or IP
        plugin_enrichment = _all_plugin
        plugin_name = getattr(self, "_plugin_hardware_name", "plugin")
        if plugin_enrichment:
            # Build IP index as fallback for MAC-randomized devices (iOS/Android)
            plugin_by_ip = {c.get("ip"): c for c in plugin_enrichment.values() if c.get("ip")}
            for row in range(self._m1_table.rowCount()):
                mac_item = self._m1_table.item(row, 2)
                pc = plugin_enrichment.get(_norm_mac(mac_item.text())) if mac_item else None
                if pc is None:
                    ip_item = self._m1_table.item(row, 0)
                    if ip_item:
                        pc = plugin_by_ip.get(ip_item.text())
                if not pc:
                    continue
                plugin_any_matched = True
                # Backfill MAC into the table row when ARP scan left it blank
                if (not mac_item or not mac_item.text()) and pc.get("mac"):
                    _mac_fill = QTableWidgetItem(pc["mac"])
                    _mac_fill.setForeground(QColor(TEXT_PRIMARY))
                    _mac_fill.setToolTip(f"MAC from {plugin_name}")
                    self._m1_table.setItem(row, 2, _mac_fill)
                hostname = pc.get("hostname", "")
                if hostname and not _mac_re.match(hostname):
                    name_item = QTableWidgetItem(hostname)
                    name_item.setForeground(QColor(TEXT_PRIMARY))
                    name_item.setToolTip(f"Name from {plugin_name}")
                    self._m1_table.setItem(row, 1, name_item)
                # Fall back to hw name so single-AP plugins still enable grouping
                unit = pc.get("unit", "") or plugin_name
                if unit:
                    node_item = QTableWidgetItem(unit)
                    node_item.setForeground(QColor(TEXT_PRIMARY))
                    node_item.setToolTip(f"Node from {plugin_name}")
                    self._m1_table.setItem(row, 6, node_item)
                    self._m1_table.setColumnHidden(6, False)
                band = pc.get("band", "")
                if band:
                    band_item = QTableWidgetItem(band)
                    band_item.setForeground(QColor(TEXT_PRIMARY))
                    band_item.setToolTip(f"Band from {plugin_name}")
                    self._m1_table.setItem(row, 7, band_item)
                    self._m1_table.setColumnHidden(7, False)

        if plugin_any_matched and self._m1_group_by_node:
            self._regroup_m1_by_satellite()

        # Mirror enrichment onto DeviceInfo objects so exports include it
        for d in self._m1_result.get("devices", []):
            mac = _norm_mac(d.mac if not isinstance(d, dict) else d.get("mac", ""))
            mc = self._mesh_enrichment.get(mac)
            if mc:
                if isinstance(d, dict):
                    d["mesh_unit"]      = mc.unit_name
                    d["mesh_band"]      = mc.band
                    d["mesh_up_kbps"]   = mc.upload_kbps
                    d["mesh_down_kbps"] = mc.download_kbps
                else:
                    d.mesh_unit      = mc.unit_name
                    d.mesh_band      = mc.band
                    d.mesh_up_kbps   = mc.upload_kbps
                    d.mesh_down_kbps = mc.download_kbps

        # Mirror plugin band/unit onto DeviceInfo objects so exports include them
        for d in self._m1_result.get("devices", []):
            _dmac = _norm_mac(d.mac if not isinstance(d, dict) else d.get("mac", ""))
            _pc = _all_plugin.get(_dmac)
            if not _pc:
                continue
            _pu, _pb = _pc.get("unit", ""), _pc.get("band", "")
            if _pu:
                if isinstance(d, dict): d["mesh_unit"] = _pu
                else: d.mesh_unit = _pu
            if _pb:
                if isinstance(d, dict): d["mesh_band"] = _pb
                else: d.mesh_band = _pb

        # Sync every enriched hostname from the table back onto the DeviceInfo
        # objects so the topology render sees the same names as the Devices table.
        # This captures all enrichment sources (mesh, mDNS, DHCP, NetBIOS).
        _mac_to_host: dict = {}
        for _r in range(self._m1_table.rowCount()):
            _h = self._m1_table.item(_r, 1)
            _m = self._m1_table.item(_r, 2)
            if _h and _m and _m.text():
                txt = _h.text().strip()
                if txt and txt != "—":
                    _mac_to_host[_norm_mac(_m.text())] = txt
        for _d in self._m1_result.get("devices", []):
            _dmac = _norm_mac(_d.mac if not isinstance(_d, dict) else _d.get("mac", ""))
            if _dmac in _mac_to_host:
                if isinstance(_d, dict):
                    _d["hostname"] = _mac_to_host[_dmac]
                else:
                    _d.hostname = _mac_to_host[_dmac]

        # Refresh the Network Info tab device table with enriched hostnames
        try:
            self._net_devices_table.setRowCount(0)
            for _d in self._m1_result.get("devices", []):
                _level  = _d.risk_level if not isinstance(_d, dict) else _d.get("risk_level", "UNKNOWN")
                _ip     = _d.ip         if not isinstance(_d, dict) else _d.get("ip", "?")
                _host   = _d.hostname   if not isinstance(_d, dict) else _d.get("hostname", "")
                _mac    = _d.mac        if not isinstance(_d, dict) else _d.get("mac", "?")
                _vendor = _d.vendor     if not isinstance(_d, dict) else _d.get("vendor", "Unknown")
                _add_row(self._net_devices_table, [_ip, _host or "—", _mac, _vendor, _level], _level)
        except Exception:
            pass

        # Refresh AvailabilityWorker targets so Uptime page labels use enriched names
        try:
            if hasattr(self, "_avail_worker") and self._m1_result:
                from modules.availability_monitor import TargetConfig
                _targets = []
                for _d in self._m1_result.get("devices", []):
                    _ip  = _d.ip       if not isinstance(_d, dict) else _d.get("ip", "")
                    _mac = _d.mac      if not isinstance(_d, dict) else _d.get("mac", "")
                    _hn  = _d.hostname if not isinstance(_d, dict) else _d.get("hostname", "")
                    if _ip:
                        _targets.append(TargetConfig(
                            host=_ip, mac=_mac or None,
                            hostname=_hn or None, label=_hn or _ip,
                        ))
                if _targets:
                    self._avail_worker.set_targets(_targets)
        except Exception:
            pass

        # Re-render topology — native mesh preferred; fall back to plugin node data
        try:
            gw_ip  = self._net_info.get("gateway")     if self._net_info else None
            gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
            _eff_units  = getattr(self, "_mesh_units", None)
            _eff_enrich = self._mesh_enrichment or None
            if not _eff_units and _all_plugin:
                from types import SimpleNamespace as _SN
                _pnodes_flat: list = []
                for _pnlist in getattr(self, "_plugin_nodes", {}).values():
                    for _n in _pnlist:
                        _pnodes_flat.append(_SN(
                            name=_n.get("name", ""), role=_n.get("role", "satellite"),
                            mac=_norm_mac(_n.get("mac", "")), online=True,
                        ))
                if _pnodes_flat:
                    _eff_units  = _pnodes_flat
                    _eff_enrich = {
                        mac: _SN(mac=mac, ip=c.get("ip", ""), name=c.get("hostname", ""),
                                 band=c.get("band", ""), unit_name=c.get("unit", ""),
                                 upload_kbps=0, download_kbps=0)
                        for mac, c in _all_plugin.items()
                    }
            self._topology_widget.render(
                self._m1_result.get("devices", []), gw_ip, gw_mac,
                mesh_units=_eff_units,
                mesh_enrichment=_eff_enrich,
                modem_data=getattr(self, "_last_modem_data", None),
            )
        except Exception:
            pass

        # Update the Deco band-usage chips on the WiFi Networks page
        self._update_m4_deco_chips()

        # Synthesize M1 rows for mesh clients that ARP scan did not see
        # (e.g. phones connected to a satellite that did not respond to ARP)
        _existing_macs: set = set()
        _existing_ips: set = set()
        for _r in range(self._m1_table.rowCount()):
            _mi = self._m1_table.item(_r, 2)
            if _mi and _mi.text():
                _existing_macs.add(_norm_mac(_mi.text()))
            _ii = self._m1_table.item(_r, 0)
            if _ii and _ii.text() and _ii.text() != "—":
                _existing_ips.add(_ii.text().strip())
        _synth_added = False
        for _mc in self._mesh_enrichment.values():
            if _norm_mac(_mc.mac) in _existing_macs:
                continue
            # Also skip if the device's IP is already in the table (ARP found it without MAC)
            if _mc.ip and _mc.ip in _existing_ips:
                continue
            _add_row(
                self._m1_table,
                [_mc.ip or "—", _mc.name or "—", _mc.mac, "", "CLEAN",
                 "Wireless Client", _mc.unit_name, _mc.band,
                 "Mesh-only — not visible to ARP scan"],
                "CLEAN",
            )
            _synth_item = self._m1_table.item(self._m1_table.rowCount() - 1, 0)
            if _synth_item:
                _synth_item.setData(Qt.ItemDataRole.UserRole + 10, "__mesh_synth__")
            _existing_macs.add(_norm_mac(_mc.mac))
            _synth_added = True
        if _synth_added:
            self._m1_table.setColumnHidden(6, False)
            self._m1_table.setColumnHidden(7, False)

        # Synthesize rows for plugin-only clients not seen by ARP scan
        # (e.g. a phone connected to the router that didn't reply to ARP)
        _plugin_synth_added = False
        for _pmac, _pc in _all_plugin.items():
            if not _pmac or _pmac in _existing_macs:
                continue
            _pip   = _pc.get("ip", "") or "—"
            _phn   = _pc.get("hostname", "") or "—"
            if _pip == "—" and _phn == "—":
                continue  # nothing useful to show
            # Skip if the device's IP is already in the table (ARP found it without MAC)
            if _pip != "—" and _pip in _existing_ips:
                continue
            _add_row(
                self._m1_table,
                [_pip, _phn, _pmac, "", "CLEAN",
                 "Wireless Client", _pc.get("unit", ""), _pc.get("band", ""),
                 "Plugin-only — not visible to ARP scan"],
                "CLEAN",
            )
            _psi = self._m1_table.item(self._m1_table.rowCount() - 1, 0)
            if _psi:
                _psi.setData(Qt.ItemDataRole.UserRole + 10, "__plugin_synth__")
            _existing_macs.add(_pmac)
            _plugin_synth_added = True
        if _plugin_synth_added:
            self._m1_table.setColumnHidden(6, False)
            self._m1_table.setColumnHidden(7, False)

        # Regroup M1 table into collapsible satellite sections (only when toggle is ON)
        if (any_matched or _synth_added or plugin_any_matched or _plugin_synth_added) \
                and getattr(self, "_m1_group_by_node", False):
            self._regroup_m1_by_satellite()

    @pyqtSlot(bool)
    def _on_node_group_toggled(self, checked: bool) -> None:
        self._m1_group_by_node = checked
        QSettings("NetSentinel", "NetSentinel").setValue("devices/group_by_node", checked)
        if hasattr(self, "_m1_seg_list"):
            self._m1_seg_list.setStyleSheet(
                self._m1_seg_inactive_ss if checked else self._m1_seg_active_ss
            )
            self._m1_seg_node.setStyleSheet(
                self._m1_seg_active_ss if checked else self._m1_seg_inactive_ss
            )
        if checked:
            self._regroup_m1_by_satellite()
        else:
            self._m1_flatten_table()

    def _m1_flatten_table(self) -> None:
        """Strip satellite section headers — restore flat device list."""
        from PyQt6.QtGui import QColor as _QC
        rows_data = []
        for row in range(self._m1_table.rowCount()):
            first = self._m1_table.item(row, 0)
            if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                continue
            cells, risk = [], "CLEAN"
            for col in range(self._m1_table.columnCount()):
                item = self._m1_table.item(row, col)
                cells.append({
                    "text":    item.text()    if item else "",
                    "tooltip": item.toolTip() if item else "",
                })
            risk_item = self._m1_table.item(row, 4)
            if risk_item:
                risk = risk_item.text().strip()
            rows_data.append({"cells": cells, "risk": risk})

        if not rows_data:
            return
        self._m1_table.setSortingEnabled(False)
        self._m1_table.setRowCount(0)
        self._m1_group_btn.setVisible(False)
        for rd in rows_data:
            r = self._m1_table.rowCount()
            self._m1_table.insertRow(r)
            rc = _color_for_level(rd["risk"])
            high = rd["risk"] in ("HIGH", "STORM")
            for col, cell in enumerate(rd["cells"]):
                item = QTableWidgetItem(cell["text"])
                item.setForeground(_QC(rc if (col == 4 or high) else TEXT_PRIMARY))
                if cell["tooltip"]:
                    item.setToolTip(cell["tooltip"])
                self._m1_table.setItem(r, col, item)
        self._m1_table.resizeColumnsToContents()
        self._m1_table.setSortingEnabled(True)

    def _regroup_m1_by_satellite(self) -> None:
        """Rebuild M1 table with collapsible satellite section header rows."""
        from PyQt6.QtGui import QColor, QFont

        # Collect device row data — skip any existing header rows
        rows_data = []
        for row in range(self._m1_table.rowCount()):
            first = self._m1_table.item(row, 0)
            if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                continue
            cells = []
            for col in range(self._m1_table.columnCount()):
                item = self._m1_table.item(row, col)
                cells.append({
                    "text":    item.text() if item else "",
                    "tooltip": item.toolTip() if item else "",
                })
            node_item = self._m1_table.item(row, 6)
            node = (node_item.text().strip() if node_item else "") or "__unassigned__"
            risk_item = self._m1_table.item(row, 4)
            risk = risk_item.text().strip() if risk_item else "CLEAN"
            rows_data.append({"cells": cells, "node": node, "risk": risk})

        if not rows_data:
            return

        # Group by node
        groups: dict = {}
        for rd in rows_data:
            groups.setdefault(rd["node"], []).append(rd)

        sorted_nodes = sorted(k for k in groups if k != "__unassigned__")
        has_named_nodes = bool(sorted_nodes)
        self._m1_has_named_nodes = has_named_nodes
        if "__unassigned__" in groups:
            sorted_nodes.append("__unassigned__")

        # Rebuild table — sorting must be off to prevent sentinel rows from scrambling
        self._m1_table.setSortingEnabled(False)
        self._m1_table.setRowCount(0)
        n_cols = self._m1_table.columnCount()

        for node_name in sorted_nodes:
            device_rows = groups[node_name]
            if node_name == "__unassigned__":
                display_name = "Other / Direct" if has_named_nodes else "All devices"
            else:
                display_name = node_name
            expanded = self._m1_sat_expanded.get(node_name, True)
            arrow = "▼" if expanded else "▶"
            nc = len(device_rows)

            # Header row
            hdr_row = self._m1_table.rowCount()
            self._m1_table.insertRow(hdr_row)
            hdr_text = f"   {arrow}  {display_name}   ·   {nc} device{'s' if nc != 1 else ''}"
            hdr_item = QTableWidgetItem(hdr_text)
            hdr_item.setData(Qt.ItemDataRole.UserRole, "__sat_header__")
            hdr_item.setData(Qt.ItemDataRole.UserRole + 1, node_name)
            hdr_item.setForeground(QColor(TEXT_PRIMARY))
            hdr_item.setBackground(QColor(BG_DARK))
            f = QFont()
            f.setBold(True)
            f.setItalic(True)
            hdr_item.setFont(f)
            hdr_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._m1_table.setItem(hdr_row, 0, hdr_item)
            self._m1_table.setSpan(hdr_row, 0, 1, n_cols)
            self._m1_table.setRowHeight(hdr_row, 26)

            # Device rows
            for rd in device_rows:
                dev_row = self._m1_table.rowCount()
                self._m1_table.insertRow(dev_row)
                risk_color = _color_for_level(rd["risk"])
                high_risk = rd["risk"] in ("HIGH", "STORM")
                for col, cell in enumerate(rd["cells"]):
                    item = QTableWidgetItem(cell["text"])
                    if col == 4:
                        item.setForeground(QColor(risk_color))
                    elif high_risk:
                        item.setForeground(QColor(risk_color))
                    else:
                        item.setForeground(QColor(TEXT_PRIMARY))
                    if cell["tooltip"]:
                        item.setToolTip(cell["tooltip"])
                    self._m1_table.setItem(dev_row, col, item)
                if not expanded:
                    self._m1_table.setRowHidden(dev_row, True)

        self._m1_grouping_active = True
        self._m1_group_btn.setVisible(True)
        # Sorting stays OFF in grouped mode — re-enabled by _m1_flatten_table on switch back
        # Connect click handler once
        if not getattr(self, "_m1_group_click_connected", False):
            self._m1_table.cellClicked.connect(self._m1_toggle_sat_section)
            self._m1_group_click_connected = True

    def _m1_toggle_sat_section(self, row: int, col: int) -> None:
        """Toggle a satellite section open/closed when its header row is clicked."""
        first = self._m1_table.item(row, 0)
        if not first or first.data(Qt.ItemDataRole.UserRole) != "__sat_header__":
            return
        node_name = first.data(Qt.ItemDataRole.UserRole + 1)
        expanded = not self._m1_sat_expanded.get(node_name, False)
        self._m1_sat_expanded[node_name] = expanded

        # Count device rows in this section (rows until next header or end)
        nc = 0
        next_row = row + 1
        while next_row < self._m1_table.rowCount():
            r_first = self._m1_table.item(next_row, 0)
            if r_first and r_first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                break
            nc += 1
            next_row += 1

        _hn = getattr(self, "_m1_has_named_nodes", False)
        if node_name == "__unassigned__":
            display_name = "Other / Direct" if _hn else "All devices"
        else:
            display_name = node_name
        arrow = "▼" if expanded else "▶"
        first.setText(f"   {arrow}  {display_name}   ·   {nc} device{'s' if nc != 1 else ''}")

        for dev_row in range(row + 1, next_row):
            self._m1_table.setRowHidden(dev_row, not expanded)

        # Update button label
        self._m1_update_group_btn()

    def _m1_set_all_expanded(self, expanded: bool) -> None:
        """Show or hide all satellite sections without rebuilding the table."""
        for row in range(self._m1_table.rowCount()):
            first = self._m1_table.item(row, 0)
            if not first or first.data(Qt.ItemDataRole.UserRole) != "__sat_header__":
                continue
            node_name = first.data(Qt.ItemDataRole.UserRole + 1)
            self._m1_sat_expanded[node_name] = expanded

            # Count and show/hide following device rows
            nc = 0
            next_row = row + 1
            while next_row < self._m1_table.rowCount():
                r_first = self._m1_table.item(next_row, 0)
                if r_first and r_first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                    break
                nc += 1
                next_row += 1

            _hn = getattr(self, "_m1_has_named_nodes", False)
            if node_name == "__unassigned__":
                display_name = "Other / Direct" if _hn else "All devices"
            else:
                display_name = node_name
            arrow = "▼" if expanded else "▶"
            first.setText(f"   {arrow}  {display_name}   ·   {nc} device{'s' if nc != 1 else ''}")
            for dev_row in range(row + 1, next_row):
                self._m1_table.setRowHidden(dev_row, not expanded)

    def _m1_toggle_all_groups(self) -> None:
        """Expand all if any are collapsed; collapse all if all are expanded."""
        all_expanded = bool(self._m1_sat_expanded) and all(
            self._m1_sat_expanded.get(n, False) for n in self._m1_sat_expanded
        )
        self._m1_set_all_expanded(not all_expanded)
        self._m1_update_group_btn()

    def _m1_update_group_btn(self) -> None:
        """Sync the expand/collapse button label with current state."""
        all_expanded = bool(self._m1_sat_expanded) and all(
            self._m1_sat_expanded.get(n, False) for n in self._m1_sat_expanded
        )
        self._m1_group_btn.setText("▼▼  Collapse All" if all_expanded else "▶▶  Expand All")

    # ── Modem (ZTE MC889 / generic WAN modem) ───────────────────────────────

    def _check_modem_autorun(self) -> None:
        """Start ZTE polling on launch if host + password were saved in a prior session."""
        from PyQt6.QtCore import QSettings
        settings = QSettings()
        host = settings.value("modem/last_host", "").strip()
        if not host:
            return
        try:
            import keyring as _kr
            pw = _kr.get_password("NetSentinel/modem", host)
        except Exception:
            return
        if not pw:
            return
        self._on_modem_connect(host, pw)

    def _trigger_modem_refresh(self) -> None:
        """Restart ZTE worker for an immediate fresh poll at scan time."""
        from PyQt6.QtCore import QSettings
        host = QSettings().value("modem/last_host", "").strip()
        if not host:
            return
        try:
            import keyring as _kr
            pw = _kr.get_password("NetSentinel/modem", host)
        except Exception:
            return
        if not pw:
            return
        self._on_modem_connect(host, pw)

    def _trigger_mesh_refresh(self) -> None:
        """Start a fresh Deco scan at scan time using the cached gateway IP.

        Falls back to the M1-result path (_check_mesh_autorun) when _net_info
        hasn't resolved the gateway yet (first run, cold start).
        """
        gateway_ip = (self._net_info or {}).get("gateway", "").strip()
        if not gateway_ip:
            return
        # Don't interrupt a fetch that's already in flight
        existing = getattr(self, "_mesh_auto_worker", None)
        if existing and existing.isRunning():
            return
        try:
            import keyring as _kr
            pw = _kr.get_password("NetSentinel/mesh", gateway_ip)
        except Exception:
            return
        if not pw:
            return
        from workers.mesh_worker import MeshWorker
        worker = MeshWorker(host=gateway_ip, password=pw)
        # Route through the page's own handler so its UI (nodes/clients tables,
        # status label) gets populated; scan_done from there fires _on_mesh_result.
        worker.result.connect(self._mesh_router_page._on_result)
        worker.status.connect(lambda msg: self._m1_status.setText(
            f"{getattr(self, '_m1_scan_summary', '')}  ·  {msg}"
        ), Qt.ConnectionType.QueuedConnection)
        self._mesh_auto_worker = worker
        worker.start()

    @pyqtSlot(str, str)
    @pyqtSlot(object)
    def _on_speed_test_modem_forward(self, result) -> None:
        """Forward speed-test modem snapshot to the Modem page and Hardware Hub."""
        sig = getattr(result, "modem_signal", None)
        if sig:
            if hasattr(self, "_modem_page"):
                self._modem_page.on_modem_signal(sig)
            if hasattr(self, "_hardware_integration_page"):
                self._hardware_integration_page.on_modem_card_data(sig)
            return
        # No ZTE signal — check if a plugin modem has a cached result
        if not hasattr(self, "_hardware_integration_page"):
            return
        try:
            from ui.pages.hardware_integration_page import (
                _load_paths, _load_last_result, _validate_script
            )
            for _p in _load_paths():
                _ok, _, _meta = _validate_script(_p)
                if _ok and _meta.get("type") == "modem":
                    _cached = _load_last_result(_p)
                    if _cached:
                        _extra = _cached.get("status", {}).get("extra", {})
                        if _extra:
                            self._hardware_integration_page.on_modem_card_data(_extra)
                        break
        except Exception:
            pass

    def _on_modem_connect(self, host: str, password: str) -> None:
        """Start (or restart) the ZTE polling worker."""
        self._on_modem_disconnect()
        from workers.zte_worker import ZteWorker
        worker = ZteWorker(host=host, password=password, interval_s=30)
        worker.result.connect(self._on_modem_signal)
        worker.error.connect(self._on_modem_error)
        worker.status.connect(self._on_modem_status)
        self._zte_worker = worker
        worker.start()
        self._last_modem_host = host
        self._last_modem_pw   = password
        # Give the speed test page the modem credentials for signal enrichment
        if hasattr(self, "_speed_test_page"):
            self._speed_test_page.set_modem_credentials(host, password)
        # Pause modem plugin workers — native ZteWorker owns the session
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.set_native_modem_connected(True)

    def _resume_modem_worker(self) -> None:
        """Restart ZteWorker after a plugin test, using cached or keyring credentials."""
        if self._last_modem_host and self._last_modem_pw:
            self._on_modem_connect(self._last_modem_host, self._last_modem_pw)
        else:
            self._trigger_modem_refresh()

    @pyqtSlot()
    def _on_modem_disconnect(self) -> None:
        """Stop the ZTE polling worker and clear cached modem data."""
        worker = getattr(self, "_zte_worker", None)
        if worker:
            worker.stop()
            if not worker.wait(3000):
                worker.terminate()
                worker.wait(500)
            self._zte_worker = None
        self._last_modem_data = None
        from modules.network_infrastructure import hw_state
        hw_state.clear_modem()
        if hasattr(self, "_speed_test_page"):
            self._speed_test_page.clear_modem_credentials()
        # Resume modem plugin workers — native session is gone
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.set_native_modem_connected(False)

    @pyqtSlot(dict)
    def _on_modem_signal(self, data: dict) -> None:
        """Cache signal data, route to Modem page, Overview tile, topology, and Monitor."""
        self._last_modem_data = data
        from modules.network_infrastructure import hw_state
        hw_state.update_modem(data, source="zte", hw_name="ZTE MC889")
        if hasattr(self, "_modem_page"):
            self._modem_page.on_modem_signal(data)
        if hasattr(self, "_overview_page"):
            self._overview_page.on_modem_signal(data)
        if hasattr(self, "_hardware_integration_page"):
            self._hardware_integration_page.on_native_modem_data(data)
            self._hardware_integration_page.on_modem_card_data(data)
        # Update topology only when the modem's connection details change.
        # Skipping on every poll prevents a costly matplotlib redraw every 30 s.
        _topo_key = (data.get("wan_ip"), data.get("network_type"))
        if (_topo_key != getattr(self, "_last_modem_topo_key", None)
                and getattr(self, "_m1_result", None)
                and hasattr(self, "_topology_widget")):
            self._last_modem_topo_key = _topo_key
            try:
                gw_ip  = self._net_info.get("gateway")     if self._net_info else None
                gw_mac = self._net_info.get("gateway_mac") if self._net_info else None
                self._topology_widget.render(
                    self._m1_result.get("devices", []), gw_ip, gw_mac,
                    mesh_units=getattr(self, "_mesh_units", None),
                    mesh_enrichment=getattr(self, "_mesh_enrichment", None),
                    modem_data=data,
                )
            except Exception:
                pass
        # Monitor logging — live entry + throttled DB write
        if hasattr(self, "_log_hub_page"):
            from PyQt6.QtCore import QSettings
            import time as _time
            s = QSettings()
            if s.value("logging/modem_enabled", False, type=bool):
                self._log_hub_page.add_modem_entry(data)
                interval_s = s.value("logging/modem_interval_min", 5, type=int) * 60
                now = _time.time()
                if self._store and now - self._last_modem_log_ts >= interval_s:
                    try:
                        self._store.record_modem_signal(
                            network_type=data.get("network_type"),
                            signal_bars=data.get("signal_bars"),
                            cell_id=data.get("cell_id"),
                            enb_id=data.get("enb_id"),
                            mcc=data.get("mcc"),
                            mnc=data.get("mnc"),
                            wan_ip=data.get("wan_ip"),
                            nr5g_band=data.get("nr5g_band"),
                            nr5g_rsrp=data.get("nr5g_rsrp_dbm"),
                            nr5g_sinr=data.get("nr5g_sinr_db"),
                            nr5g_rsrq=data.get("nr5g_rsrq_db"),
                            nr5g_pci=data.get("nr5g_pci"),
                            nr5g_arfcn=data.get("nr5g_arfcn"),
                            lte_band=data.get("lte_band"),
                            lte_rsrp=data.get("lte_rsrp_dbm"),
                            lte_snr=data.get("lte_snr_db"),
                            lte_rsrq=data.get("lte_rsrq_db"),
                            lte_pci=data.get("lte_pci"),
                            lte_earfcn=data.get("lte_earfcn"),
                        )
                        self._last_modem_log_ts = now
                    except Exception:
                        pass

    @pyqtSlot(str)
    def _on_modem_error(self, msg: str) -> None:
        if hasattr(self, "_modem_page"):
            self._modem_page.on_modem_error(msg)

    @pyqtSlot(str)
    def _on_modem_status(self, msg: str) -> None:
        if hasattr(self, "_modem_page"):
            self._modem_page.on_modem_status(msg)

    @pyqtSlot(str)
    def _filter_m1_by_nl(self, text: str):
        """Filter Device Fingerprinter rows using the NL query engine."""
        text = text.strip()
        # Clear filter — restore each section's individual collapsed/expanded state
        if not text:
            if self._m1_grouping_active:
                for row in range(self._m1_table.rowCount()):
                    first = self._m1_table.item(row, 0)
                    if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                        self._m1_table.setRowHidden(row, False)
                        node_name = first.data(Qt.ItemDataRole.UserRole + 1)
                        exp = self._m1_sat_expanded.get(node_name, False)
                        next_row = row + 1
                        while next_row < self._m1_table.rowCount():
                            r = self._m1_table.item(next_row, 0)
                            if r and r.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                                break
                            self._m1_table.setRowHidden(next_row, not exp)
                            next_row += 1
            else:
                for row in range(self._m1_table.rowCount()):
                    self._m1_table.setRowHidden(row, False)
            if self._m1_result:
                self._m1_status.setText(
                    f"✓  {self._m1_result.get('total_count', 0)} devices scanned — "
                    f"{self._m1_result.get('high_risk_count', 0)} HIGH RISK"
                )
            return
        if not self._m1_result:
            return
        try:
            from modules.nl_query import query as _nl_query
            devices = self._m1_result.get("devices", [])
            result = _nl_query(devices, text)
            if result.error:
                self._m1_status.setText(f"⚠  {result.error}")
                return
            matched_ips = {
                (m.device.ip if not isinstance(m.device, dict) else m.device.get("ip", ""))
                for m in result.matches
            }
            for row in range(self._m1_table.rowCount()):
                first = self._m1_table.item(row, 0)
                if first and first.data(Qt.ItemDataRole.UserRole) == "__sat_header__":
                    self._m1_table.setRowHidden(row, False)  # always keep headers visible
                    continue
                ip_item = first
                ip = ip_item.text() if ip_item else ""
                self._m1_table.setRowHidden(row, ip not in matched_ips)
            self._m1_status.setText(
                f"Filter: {len(matched_ips)} match(es) — {result.explanation}"
            )
        except Exception as exc:
            self._m1_status.setText(f"Filter error: {exc}")

    @pyqtSlot(dict)
    def _on_avail_cycle_done(self, result: dict) -> None:
        """Route AvailabilityWorker cycle results to HistoryPage, HA page, and MQTT."""
        states = result.get("states", {})
        rtts   = result.get("rtts",   {})
        try:
            self._history_page.on_cycle_done(result)
        except Exception:
            pass
        try:
            self._ha_page.on_availability_update(states)
        except Exception:
            pass
        try:
            for _ip, _state in states.items():
                self._mqtt_page.on_uptime_state(_ip, _state, rtts.get(_ip) or 0.0)
        except Exception:
            pass

    @pyqtSlot(object)
    def _on_bpdu_found(self, bpdu):
        level = "HIGH" if bpdu.is_rogue else "CLEAN"
        _add_row(
            self._m2_table,
            [
                bpdu.src_mac, bpdu.bpdu_type, bpdu.root_mac,
                str(bpdu.bridge_priority),
                f"{bpdu.hello_time:.1f}", f"{bpdu.max_age:.1f}", f"{bpdu.forward_delay:.1f}",
                "\u26a0 YES" if bpdu.is_rogue else "No",
            ],
            level,
        )
        if bpdu.is_rogue:
            self._m2_status.setText(f"\u26a0 ROGUE ROOT BRIDGE: {bpdu.src_mac}")

    @pyqtSlot(dict)
    def _on_m2_result(self, data: dict):
        self._m2_stack.setCurrentIndex(1)
        self._m2_result = data
        rogue = data.get("rogue_count", 0)
        total = data.get("total_bpdus", 0)
        self._m2_status.setText(
            f"✓  {total} BPDU frame(s) captured — {rogue} rogue Root Bridge claim(s)"
        )
        self._update_overall_verdict()

    @pyqtSlot(object)
    def _on_m3_result(self, storm):
        self._m3_stack.setCurrentIndex(1)
        self._m3_result = storm
        level = storm.storm_level if not isinstance(storm, dict) else storm.get("storm_level", "?")
        bps   = storm.bcast_per_sec if not isinstance(storm, dict) else storm.get("bcast_per_sec", 0)
        mps   = storm.mcast_per_sec if not isinstance(storm, dict) else storm.get("mcast_per_sec", 0)
        ratio = storm.bcast_ratio if not isinstance(storm, dict) else storm.get("bcast_ratio", 0)
        top5  = storm.top_sources if not isinstance(storm, dict) else storm.get("top_sources", [])
        rogues = set(storm.rogue_matches if not isinstance(storm, dict) else storm.get("rogue_matches", []))

        self._update_stat(self._m3_bcast_lbl, f"{bps:.1f}", _color_for_level(level))
        self._update_stat(self._m3_mcast_lbl, f"{mps:.1f}")
        self._update_stat(self._m3_ratio_lbl, f"{ratio:.1%}")
        self._update_stat(self._m3_level_lbl, level, _color_for_level(level))

        self._m3_table.setRowCount(0)
        for mac, count in top5:
            is_rogue = mac in rogues
            _add_row(
                self._m3_table,
                [mac, str(count), "⚠ YES — CONFIRMED SABOTAGE" if is_rogue else "No"],
                "HIGH" if is_rogue else "CLEAN",
            )

        self._m3_status.setText(f"✓  Storm level: {level} ({bps:.1f} bcast/s)")
        self._update_overall_verdict()
        if hasattr(self, "_monitor_overview_page"):
            self._monitor_overview_page.set_storm_status(level)

    @pyqtSlot(object)
    def _on_m4_result(self, wifi):
        self._m4_stack.setCurrentIndex(1)
        self._m4_result = wifi
        networks = wifi.networks if not isinstance(wifi, dict) else wifi.get("networks", [])
        my_ssid  = (wifi.my_ssid if not isinstance(wifi, dict) else wifi.get("my_ssid", "")) or ""
        self._m4_table.setRowCount(0)

        def _g(obj, attr, default):
            return getattr(obj, attr, default) if not isinstance(obj, dict) else obj.get(attr, default)

        # Clear co-channel flags for BSSIDs whose OUI matches a known mesh unit
        mesh_units = getattr(self, "_mesh_units", None)
        mesh_ouis: set = set()
        if mesh_units:
            mesh_ouis = {
                u.mac[:8] for u in mesh_units
                if hasattr(u, "mac") and len(u.mac) >= 8
            }
            for _n in networks:
                if _g(_n, "co_channel_conflict", False):
                    _bssid = _g(_n, "bssid", "")
                    if _bssid and len(_bssid) >= 8 and _bssid[:8] in mesh_ouis:
                        if not isinstance(_n, dict):
                            _n.co_channel_conflict = False
                        else:
                            _n["co_channel_conflict"] = False

        # Build OUI set from ALL named SSIDs so we can identify backhaul hidden SSIDs
        # even when Deco API data isn't available.
        named_ouis: set = set()
        for n in networks:
            ssid  = _g(n, "ssid", "")
            bssid = _g(n, "bssid", "")
            if ssid and bssid and len(bssid) >= 8:
                named_ouis.add(bssid[:8])
        # Also include Deco-API OUIs
        named_ouis |= mesh_ouis

        # Deco node-name lookup: mac[:17].lower() → node name
        deco_names: dict = {}
        if mesh_units:
            for u in mesh_units:
                if hasattr(u, "mac") and hasattr(u, "name"):
                    deco_names[u.mac[:17].lower()] = u.name

        def _is_backhaul(bssid: str) -> bool:
            """True when a hidden SSID's OUI matches the mesh system's named OUI."""
            if len(bssid) < 8:
                return False
            oui = bssid[:8]
            # Locally-administered variants of named OUIs are common for backhaul.
            # Check exact match and also the canonical (globally-administered) form.
            canon = bssid[0]
            try:
                first = int(bssid[0:2], 16)
                canon_first = first & 0xFD  # clear locally-administered bit
                canon_oui = f"{canon_first:02x}{bssid[2:8]}"
            except ValueError:
                canon_oui = oui
            return oui in named_ouis or canon_oui in named_ouis

        # Group named SSIDs; group hidden SSIDs by (channel, band)
        ssid_groups: dict = {}
        hidden_groups: dict = {}
        for n in networks:
            ssid = _g(n, "ssid", "")
            if ssid:
                ssid_groups.setdefault(ssid, []).append(n)
            else:
                ch   = _g(n, "channel", 0)
                band = _g(n, "band", "?")
                hidden_groups.setdefault((ch, band), []).append(n)

        display_rows: list = []

        for ssid, group in ssid_groups.items():
            best     = max(group, key=lambda x: _g(x, "signal_dbm", -100))
            worst    = min(group, key=lambda x: _g(x, "signal_dbm", -100))
            rogue    = any(_g(x, "is_rogue_ssid",      False) for x in group)
            conflict = any(_g(x, "co_channel_conflict", False) for x in group)
            bssid    = _g(best, "bssid", "")
            # Build per-node tooltip: prefer Deco names, fall back to raw BSSIDs
            node_tips = []
            for x in sorted(group, key=lambda x: _g(x, "signal_dbm", -100), reverse=True):
                b = _g(x, "bssid", "")
                name = deco_names.get(b[:17].lower(), "")
                sig  = _g(x, "signal_dbm", 0)
                node_tips.append(f"{name or b}  {sig} dBm")
            display_rows.append((
                best, ssid, bssid, len(group), node_tips,
                rogue, conflict, False,
                _g(best, "signal_dbm", 0), _g(worst, "signal_dbm", 0),
            ))

        for (_ch, _band), group in hidden_groups.items():
            best     = max(group, key=lambda x: _g(x, "signal_dbm", -100))
            worst    = min(group, key=lambda x: _g(x, "signal_dbm", -100))
            rogue    = any(_g(x, "is_rogue_ssid",      False) for x in group)
            conflict = any(_g(x, "co_channel_conflict", False) for x in group)
            bssid    = _g(best, "bssid", "")
            backhaul = _is_backhaul(bssid)
            node_tips = [_g(x, "bssid", "") for x in group]
            display_rows.append((
                best, None, bssid, len(group), node_tips,
                rogue, conflict, backhaul,
                _g(best, "signal_dbm", 0), _g(worst, "signal_dbm", 0),
            ))

        from PyQt6.QtWidgets import QTableWidgetItem
        for n, ssid, bssid, node_count, node_tips, rogue, conflict, backhaul, sig_best, sig_worst in display_rows:
            ch   = _g(n, "channel", 0)
            band = _g(n, "band", "?")
            connected = bool(my_ssid and ssid and ssid == my_ssid)

            # SSID display
            if ssid:
                ssid_d = ssid
            elif backhaul:
                ssid_d = "Mesh Backhaul"
            else:
                ssid_d = "[HIDDEN]"

            # Signal: show range when nodes differ by more than 2 dBm
            if node_count > 1 and abs(sig_best - sig_worst) > 2:
                sig_d = f"{sig_best} / {sig_worst} dBm"
            else:
                sig_d = f"{sig_best} dBm"

            # Nodes column tooltip
            node_tip = "\n".join(node_tips) if node_tips else ""

            level = "HIGH" if rogue else ("MEDIUM" if conflict else "CLEAN")

            row_idx = self._m4_table.rowCount()
            self._m4_table.insertRow(row_idx)

            ssid_item = QTableWidgetItem(ssid_d)
            if backhaul:
                from PyQt6.QtGui import QColor
                ssid_item.setForeground(QColor(TEXT_MUTED))
                ssid_item.setToolTip(
                    "Hidden SSID used for inter-node mesh communication.\n"
                    "Not a user network — safe to ignore."
                )

            bssid_item = QTableWidgetItem(bssid)

            nodes_item = QTableWidgetItem(str(node_count) if node_count > 1 else "")
            if node_count > 1:
                nodes_item.setToolTip(node_tip)
                from PyQt6.QtGui import QColor
                nodes_item.setForeground(QColor(ACCENT))

            sig_item  = QTableWidgetItem(sig_d)
            rogue_item = QTableWidgetItem("⚠ Yes" if rogue else "No")
            conf_item  = QTableWidgetItem("⚠ Yes" if conflict else "No")
            conn_item  = QTableWidgetItem("✓ Yes" if connected else "")

            from PyQt6.QtGui import QColor as _QC
            if rogue:
                rogue_item.setForeground(_QC(RED))
            if conflict:
                conf_item.setForeground(_QC(AMBER))
            if connected:
                conn_item.setForeground(_QC(GREEN))

            for col, item in enumerate([
                ssid_item, bssid_item, nodes_item,
                QTableWidgetItem(str(ch)), QTableWidgetItem(band),
                sig_item, rogue_item, conf_item, conn_item,
            ]):
                item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._m4_table.setItem(row_idx, col, item)

        rogue_c  = wifi.rogue_count  if not isinstance(wifi, dict) else wifi.get("rogue_count", 0)
        hidden_c = wifi.hidden_count if not isinstance(wifi, dict) else wifi.get("hidden_count", 0)
        self._m4_status.setText(
            f"✓  {len(networks)} networks — {rogue_c} suspicious SSIDs, {hidden_c} hidden"
            + (f"  ·  connected: {my_ssid}" if my_ssid else "")
        )
        self._update_overall_verdict()

    @pyqtSlot(object)
    def _on_ping_point(self, pt):
        if self._m5_stack.currentIndex() == 0:
            self._m5_stack.setCurrentIndex(1)
        self._graph.add_ping_point(pt.timestamp, pt.target, pt.rtt_ms)

    @pyqtSlot(object)
    def _on_dns_point(self, pt):
        self._graph.add_ping_point(pt.timestamp, "DNS", pt.rtt_ms)

    @pyqtSlot(object)
    def _on_m5_result(self, corr):
        self._m5_result = corr
        self._graph_timer.stop()
        self._graph.redraw()

        outages  = corr.micro_outages   if not isinstance(corr, dict) else corr.get("micro_outages", [])
        stp_list = corr.stp_signatures  if not isinstance(corr, dict) else corr.get("stp_signatures", [])
        self._m5_outage_table.setRowCount(0)
        for o in outages:
            is_stp = o in stp_list
            level = "HIGH" if is_stp else "MEDIUM"
            _add_row(
                self._m5_outage_table,
                [
                    o.get("target", "?"),
                    f"{o.get('duration', 0):.1f}",
                    str(o.get("consecutive_drops", 0)),
                    "⚠ YES — STP" if is_stp else "No",
                    level,
                ],
                level,
            )

        self._m5_status.setText(
            f"\u2713  {len(outages)} outage(s) \u2014 "
            f"{len(stp_list)} "
            "STP reconvergence signature(s)"
        )
        self._update_overall_verdict()

    def _refresh_graph(self):
        self._graph.redraw()

    @pyqtSlot()
    def _on_worker_done(self):
        self._active_count -= 1
        if self._active_count <= 0:
            self._active_count = 0
            self._set_scanning(False)
            self._set_status("Scan complete.")
            self._refresh_pulse_bar()
            self._graph_timer.stop()
            self._graph.redraw()
            self._workers.clear()
            self._push_monitor_pills()   # clear Analysis badge + Broadcast Storm dot
            if self._auto_report_pending:
                self._auto_report_scan_done = True
                self._maybe_auto_report()
            if getattr(self, "_pending_benchmark", False):
                self._pending_benchmark = False
                self._run_benchmark()

    # ── Overall verdict ───────────────────────────────────────────────────────

    def _update_overall_verdict(self):
        verdicts = []
        level = "CLEAN"

        if self._m1_result:
            v = self._m1_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m1_result.get("high_risk_count", 0) > 0:
                level = "HIGH"

        if self._m2_result:
            v = self._m2_result.get("plain_verdict", "")
            if v:
                verdicts.append(v)
            if self._m2_result.get("rogue_count", 0) > 0:
                level = "HIGH"

        if self._m3_result:
            storm_level = (
                self._m3_result.storm_level
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("storm_level", "CLEAN")
            )
            v = (
                self._m3_result.plain_verdict
                if not isinstance(self._m3_result, dict)
                else self._m3_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            if storm_level in ("STORM", "WARNING") and level == "CLEAN":
                level = "MEDIUM" if storm_level == "WARNING" else "HIGH"

        if self._m4_result:
            v = (
                self._m4_result.plain_verdict
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            rogue_c = (
                self._m4_result.rogue_count
                if not isinstance(self._m4_result, dict)
                else self._m4_result.get("rogue_count", 0)
            )
            if rogue_c and level == "CLEAN":
                level = "MEDIUM"

        if self._m5_result:
            v = (
                self._m5_result.plain_verdict
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("plain_verdict", "")
            )
            if v:
                verdicts.append(v)
            stp_sigs = (
                self._m5_result.stp_signatures
                if not isinstance(self._m5_result, dict)
                else self._m5_result.get("stp_signatures", [])
            )
            if stp_sigs:
                level = "HIGH"

        if self._diag_result:
            v = getattr(self._diag_result, "plain_verdict", "") or ""
            if v:
                verdicts.append(f"Diagnostics: {v}")
            # Failed ping to gateway → escalate
            gw_ping = next(
                (p for p in getattr(self._diag_result, "ping_results", []) if p.host == "Gateway"),
                None,
            )
            if gw_ping and gw_ping.status == "FAIL" and level == "CLEAN":
                level = "HIGH"
            # DNS leak
            leak = getattr(self._diag_result, "dns_leak", None)
            if leak and getattr(leak, "leak_detected", False) and level == "CLEAN":
                level = "MEDIUM"

        combined = "\n\n".join(verdicts) if verdicts else "Scan in progress..."
        self._verdict.update(combined, level)
        # Show the compact status badge once real data is available
        self._verdict_badge.setText(f"\u25cf {level}")
        self._verdict_badge.setStyleSheet(
            f"color:{_color_for_level(level)}; font-size:11px; font-weight:bold; padding:0 8px;"
            "background:transparent; border:none;"
        )
        self._verdict_badge.setVisible(True)

    # ── Export ────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _run_full_report(self):
        """Run all modules + diagnostics, then auto-open the HTML report. No dialogs."""
        if self._active_count > 0:
            self._set_status("Scan already in progress — please wait.")
            return

        # Arm the auto-report flags
        self._auto_report_pending   = True
        self._auto_report_scan_done = False
        # Diagnostics: start them now; mark done immediately if they were already run
        self._auto_report_diag_done = False
        # Force all scan modules on for the full report run
        _rqs = QSettings("NetSentinel", "NetSentinel")
        for _k in ("stp", "storm", "wifi", "dns"):
            _rqs.setValue(f"scan/{_k}_enabled", True)
        if hasattr(self, "_overview_page"):
            self._overview_page.set_report_running(True)

        # Start diagnostics in the background (runs in parallel with the scan)
        if self._diag_worker and self._diag_worker.isRunning():
            self._auto_report_diag_done = True   # already running; result will arrive
        else:
            self._start_diagnostics()

        # Start the full scan (M1–M5 all checked above)
        self._start_full_scan()

    def _maybe_auto_report(self) -> None:
        """Generate and open the report once both scan and diagnostics are done."""
        if not self._auto_report_pending:
            return
        if not (self._auto_report_scan_done and self._auto_report_diag_done):
            return
        self._auto_report_pending   = False
        self._auto_report_scan_done = False
        self._auto_report_diag_done = False
        if hasattr(self, "_overview_page"):
            self._overview_page.set_report_running(False)
        try:
            import datetime as _dt
            from modules.utils import get_app_data_dir
            from modules.report_exporter import save_report
            _ts  = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            _out = get_app_data_dir() / "reports" / f"netsentinel_report_{_ts}.html"
            _out.parent.mkdir(parents=True, exist_ok=True)
            _level = "CLEAN"
            if self._m1_result and self._m1_result.get("high_risk_count", 0):
                _level = "HIGH"
            if self._m2_result and self._m2_result.get("rogue_count", 0):
                _level = "HIGH"
            _verdict = self._verdict._text.text() if hasattr(self._verdict, "_text") else ""
            save_report(
                _out,
                module1_data=self._m1_result,
                module2_data=self._m2_result,
                module3_data=self._m3_result,
                module4_data=self._m4_result,
                module5_data=self._m5_result,
                diagnostics_data=self._diag_result,
                network_info_data=self._net_info if self._net_info else None,
                overall_verdict=_verdict,
                overall_level=_level,
            )
            webbrowser.open(_out.as_uri())
            self._set_status(f"Report ready — {_out.name}")
        except Exception as _exc:
            self._set_status(f"Auto-report failed: {_exc}")
            if hasattr(self, "_overview_page"):
                self._overview_page.set_report_running(False)

    @pyqtSlot()
    def _export_report(self):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        default_dir = str(Path.home() / "Desktop")

        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            str(Path(default_dir) / f"netsentinel_report_{ts}.html"),
            "HTML Report (*.html);;JSON Export (*.json);;CSV Device List (*.csv);;Nmap XML (*.xml);;All Files (*)",
        )
        if not path_str:
            return

        out = Path(path_str)

        # Determine overall level
        level = "CLEAN"
        if self._m1_result and self._m1_result.get("high_risk_count", 0):
            level = "HIGH"
        if self._m2_result and self._m2_result.get("rogue_count", 0):
            level = "HIGH"
        overall = self._verdict._text.text()

        try:
            suffix = out.suffix.lower()
            if suffix == ".json":
                from modules.report_exporter import save_json_report
                save_json_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
            elif suffix == ".csv":
                from modules.report_exporter import save_csv_report
                save_csv_report(out, self._m1_result)
            elif suffix == ".xml":
                from modules.report_exporter import save_nmap_xml_report
                ps_result = getattr(self, "_last_portscan_result", None)
                save_nmap_xml_report(out, self._m1_result, ps_result)
            else:
                from modules.report_exporter import save_report
                save_report(
                    out,
                    module1_data=self._m1_result,
                    module2_data=self._m2_result,
                    module3_data=self._m3_result,
                    module4_data=self._m4_result,
                    module5_data=self._m5_result,
                    diagnostics_data=self._diag_result,
                    network_info_data=self._net_info if self._net_info else None,
                    overall_verdict=overall,
                    overall_level=level,
                )
                webbrowser.open(out.as_uri())
            self._set_status(f"Report saved: {out.name}")
        except Exception as exc:
            self._set_status(f"Export failed: {exc}")

    # ── Network Info ──────────────────────────────────────────────────────────

    def _refresh_network_info(self):
        from workers.scan_worker import NetworkInfoWorker
        # Guard: don't start a second worker if one is already running
        if hasattr(self, "_net_info_worker") and self._net_info_worker and self._net_info_worker.isRunning():
            return
        self._net_info_worker = NetworkInfoWorker()
        self._net_info_worker.result.connect(self._update_net_info_ui)
        self._net_info_worker.error.connect(lambda e: self._net_info_label.setText(f"Error: {e}"), Qt.ConnectionType.QueuedConnection)
        self._net_info_worker.start()
        self._net_info_label.setText("Refreshing network information…")

    # ── Diagnostics ───────────────────────────────────────────────────────────

    @pyqtSlot()
    def _start_diagnostics(self):
        from workers.scan_worker import DiagnosticsWorker
        if self._diag_worker and self._diag_worker.isRunning():
            return
        self._diag_ping_table.setRowCount(0)
        self._diag_dns_table.setRowCount(0)
        self._diag_trace_table.setRowCount(0)
        for lbl in self._diag_http_labels:
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding:0 10px;")
            name = lbl.text().split(":")[0].lstrip("● ")
            lbl.setText(f"● {name}: testing…")
        self._update_stat(self._diag_speed_lbl, "…")
        self._update_stat(self._diag_public_lbl, "…")
        self._update_stat(self._diag_dns_lbl, "…")
        self._update_stat(self._diag_gw_lbl, "…")
        self._btn_diag.setEnabled(False)
        self._diag_status_lbl.setText("Running diagnostics…")

        gw = self._net_info.get("gateway") if self._net_info else None
        self._diag_worker = DiagnosticsWorker(gateway_ip=gw)
        self._diag_worker.status.connect(lambda m: self._diag_status_lbl.setText(m), Qt.ConnectionType.QueuedConnection)
        self._diag_worker.result.connect(self._on_diag_result)
        self._diag_worker.error.connect(
            lambda e: (
                self._diag_status_lbl.setText(f"Error: {e}"),
                self._btn_diag.setEnabled(True),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self._diag_worker.finished.connect(self._on_diag_worker_finished)
        self._diag_worker.start()

    @pyqtSlot()
    def _on_diag_worker_finished(self):
        self._btn_diag.setEnabled(True)
        # If a diagnostics error prevented _on_diag_result from firing, we still
        # need to unblock the auto-report so it doesn't wait forever.
        if self._auto_report_pending and not self._auto_report_diag_done:
            self._auto_report_diag_done = True
            self._maybe_auto_report()

    @pyqtSlot(object)
    def _on_diag_result(self, result):
        from ui.styles import GREEN, AMBER, RED, TEXT_SECONDARY, TEXT_PRIMARY, BLUE

        self._diag_result = result
        self._protocol_viz_page.set_context(
            net_info=self._net_info,
            devices=self._m1_result.get("devices", []) if self._m1_result else [],
            diag_result=self._diag_result,
            m2_result=self._m2_result,
        )

        # Ping table
        self._diag_ping_table.setRowCount(0)
        for p in result.ping_results:
            color = GREEN if p.status == "OK" else (AMBER if p.status == "SLOW" else RED)
            rtt_str = f"{p.rtt_ms:.0f}" if p.rtt_ms >= 0 else "unreachable"
            row = self._diag_ping_table.rowCount()
            self._diag_ping_table.insertRow(row)
            for col, val in enumerate([p.host, p.ip, rtt_str, p.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                        color if col == 3 else TEXT_PRIMARY
                    )
                )
                self._diag_ping_table.setItem(row, col, item)

        # DNS table
        self._diag_dns_table.setRowCount(0)
        for d in result.dns_results:
            color = GREEN if d.status == "OK" else (AMBER if d.status == "SLOW" else RED)
            lat_str = f"{d.latency_ms:.0f} ms" if d.latency_ms >= 0 else "failed"
            row = self._diag_dns_table.rowCount()
            self._diag_dns_table.insertRow(row)
            for col, val in enumerate([d.server, lat_str, d.resolved_ip, d.status]):
                item = QTableWidgetItem(str(val))
                item.setForeground(
                    __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(
                        color if col == 3 else TEXT_PRIMARY
                    )
                )
                self._diag_dns_table.setItem(row, col, item)

        # HTTP labels
        for i, h in enumerate(result.http_results):
            if i < len(self._diag_http_labels):
                lbl = self._diag_http_labels[i]
                color = GREEN if h.status == "OK" else (AMBER if h.status == "PARTIAL" else RED)
                code_str = str(h.status_code) if h.status_code else "—"
                lbl.setText(f"● {h.url}: {h.status} ({code_str})")
                lbl.setStyleSheet(f"color:{color}; font-size:11px; padding:0 10px;")

        # Traceroute
        self._diag_trace_table.setRowCount(0)
        for hop in result.trace_hops:
            rtt_str = f"{hop.rtt_ms:.0f}" if hop.rtt_ms >= 0 else "—"
            row = self._diag_trace_table.rowCount()
            self._diag_trace_table.insertRow(row)
            for col, val in enumerate([str(hop.hop), hop.ip, rtt_str]):
                self._diag_trace_table.setItem(row, col, QTableWidgetItem(val))

        # Summary stats
        gw_ping = next((p for p in result.ping_results if p.host == "Gateway"), None)
        gw_str = (f"{gw_ping.rtt_ms:.0f} ms" if gw_ping and gw_ping.rtt_ms >= 0 else "—")
        gw_col = GREEN if gw_ping and gw_ping.status == "OK" else (AMBER if gw_ping and gw_ping.status == "SLOW" else RED)
        self._update_stat(self._diag_gw_lbl, gw_str, gw_col)

        speed_str = (
            f"{result.download_mbps:.1f} Mbps"
            if result.download_mbps >= 1
            else (f"{result.download_mbps * 1000:.0f} Kbps" if result.download_mbps > 0 else "—")
        )
        self._update_stat(self._diag_speed_lbl, speed_str, GREEN if result.download_mbps > 0 else RED)
        self._update_stat(self._diag_public_lbl, result.public_ip or "—", BLUE if result.public_ip else RED)

        sys_dns = next((d for d in result.dns_results if d.server == "System DNS"), None)
        dns_str = f"{sys_dns.latency_ms:.0f} ms" if sys_dns and sys_dns.latency_ms >= 0 else "—"
        dns_col = GREEN if sys_dns and sys_dns.status == "OK" else (AMBER if sys_dns and sys_dns.status == "SLOW" else RED)
        self._update_stat(self._diag_dns_lbl, dns_str, dns_col)

        self._diag_status_lbl.setText(f"Diagnostics complete.  {result.plain_verdict}")
        self._btn_diag.setEnabled(True)

        # DNS Leak
        from PyQt6.QtGui import QColor
        leak = getattr(result, "dns_leak", None)
        self._diag_leak_table.setRowCount(0)
        if leak:
            color = RED if leak.leak_detected else GREEN
            self._diag_leak_lbl.setText(leak.plain_verdict)
            self._diag_leak_lbl.setStyleSheet(f"color:{color}; font-size:11px; padding-left:10px;")
            for e in leak.resolvers_seen:
                r = self._diag_leak_table.rowCount()
                self._diag_leak_table.insertRow(r)
                for col, val in enumerate([e.server_ip, e.country, e.org]):
                    self._diag_leak_table.setItem(r, col, QTableWidgetItem(val))

        self._update_overall_verdict()
        if self._auto_report_pending:
            self._auto_report_diag_done = True
            self._maybe_auto_report()
        if getattr(self, "_pending_isp_report", False):
            self._pending_isp_report = False
            self._export_isp_report()

    # ── Recon: Credentialed SSH Scan ─────────────────────────────────────────

    def _build_recon_cred_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout, QComboBox
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Connects to a remote host via SSH and collects:\n"
            "installed packages, running services, local users, patch level,\n"
            "listening ports, sudo NOPASSWD entries, and failed login attempts.\n"
            "Requires SSH access (password or private key). "
            "Works on Linux, macOS, and Windows (OpenSSH)."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        self._cred_host    = QLineEdit(); self._cred_host.setPlaceholderText("192.168.1.1")
        self._cred_port    = QSpinBox(); self._cred_port.setRange(1, 65535); self._cred_port.setValue(22)
        self._cred_user    = QLineEdit(); self._cred_user.setPlaceholderText("root")
        self._cred_pass    = QLineEdit(); self._cred_pass.setPlaceholderText("(leave blank to use key)")
        self._cred_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._cred_key     = QLineEdit(); self._cred_key.setPlaceholderText("/home/user/.ssh/id_rsa")
        self._cred_os      = QComboBox()
        self._cred_os.addItems(["auto", "linux", "macos", "windows"])
        form.addRow("Host:", self._cred_host)
        form.addRow("SSH Port:", self._cred_port)
        form.addRow("Username:", self._cred_user)
        form.addRow("Password:", self._cred_pass)
        form.addRow("Key file:", self._cred_key)
        form.addRow("OS hint:", self._cred_os)

        ctrl = QHBoxLayout()
        self._btn_cred = QPushButton("🔑  Run Credentialed Scan")
        self._btn_cred.setObjectName("btnNetRefresh")
        self._btn_cred.clicked.connect(self._start_cred_scan)
        self._btn_cred_stop = QPushButton("⏹  Stop")
        self._btn_cred_stop.clicked.connect(lambda: self._cred_worker and self._cred_worker.stop())
        ctrl.addWidget(self._btn_cred)
        ctrl.addWidget(self._btn_cred_stop)
        ctrl.addStretch()

        self._cred_status = QLabel("Credentialed scan idle.")
        self._cred_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._cred_status.setWordWrap(True)

        self._cred_verdict = QLabel("")
        self._cred_verdict.setWordWrap(True)
        self._cred_verdict.setStyleSheet(
            f"color:{GREEN};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._cred_verdict.hide()

        self._recon_cred_sw_table   = _table(["Package", "Version", "Source"])
        self._recon_cred_svc_table  = _table(["Service", "Status", "PID"])
        self._recon_cred_user_table = _table(["User", "UID / SID", "Home", "Shell"])
        self._recon_cred_sessions_table = _table(["Active Session (logged-in user)"])

        from PyQt6.QtWidgets import QTableWidgetItem as _TWI2
        self._recon_cred_info_table = _table(["Field", "Value"])
        self._recon_cred_info_table.horizontalHeader().setSectionResizeMode(
            1, __import__("PyQt6.QtWidgets", fromlist=["QHeaderView"]).QHeaderView.ResizeMode.Stretch
        )

        from PyQt6.QtWidgets import QTabWidget as _TW
        inner_tabs = _TW()
        inner_tabs.addTab(self._recon_cred_info_table,     "▪ Device Info")
        inner_tabs.addTab(self._recon_cred_sw_table,       "📦 Software")
        inner_tabs.addTab(self._recon_cred_svc_table,      "⚙ Services")
        inner_tabs.addTab(self._recon_cred_user_table,     "👤 Users")
        inner_tabs.addTab(self._recon_cred_sessions_table, "● Active Sessions")

        lay.addWidget(info)
        lay.addWidget(form_w)
        lay.addWidget(self._cred_verdict)
        lay.addWidget(self._cred_status)
        lay.addLayout(ctrl)
        lay.addWidget(inner_tabs, 1)
        return w

    @pyqtSlot()
    def _start_cred_scan(self):
        from workers.scan_worker import CredentialedScanWorker
        host = self._cred_host.text().strip()
        if not host:
            self._cred_status.setText("⚠ Enter a host IP or hostname.")
            return
        if self._cred_worker and self._cred_worker.isRunning():
            return
        self._recon_cred_sw_table.setRowCount(0)
        self._recon_cred_svc_table.setRowCount(0)
        self._recon_cred_user_table.setRowCount(0)
        self._recon_cred_sessions_table.setRowCount(0)
        self._recon_cred_info_table.setRowCount(0)
        self._cred_verdict.hide()
        self._cred_worker = CredentialedScanWorker(
            host=host,
            ssh_port=self._cred_port.value(),
            username=self._cred_user.text().strip() or "root",
            password=self._cred_pass.text(),
            key_path=self._cred_key.text().strip(),
            os_hint=self._cred_os.currentText(),
        )
        self._cred_worker.result.connect(self._on_cred_result)
        self._cred_worker.status.connect(self._cred_status.setText)
        self._cred_worker.error.connect(lambda e: self._cred_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._cred_worker.start()

    @pyqtSlot(object)
    def _on_cred_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        flags = res.risk_flags
        color = RED if flags else GREEN
        self._cred_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        self._cred_verdict.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._cred_verdict.show()
        self._cred_status.setText("Credentialed scan complete.")

        # ── Device Info tab ───────────────────────────────────────────────
        info_rows = [
            ("OS",             res.patch_info.os_version or res.os_type),
            ("Kernel / Build", res.patch_info.kernel),
            ("Last Update",    res.patch_info.last_update),
            ("Pending Updates",str(res.patch_info.pending_updates)),
            ("Serial Number",  res.serial_number or "—"),
            ("Failed Logins (24 h)", str(res.failed_logins)),
        ]
        for field_name, value in info_rows:
            r = self._recon_cred_info_table.rowCount()
            self._recon_cred_info_table.insertRow(r)
            self._recon_cred_info_table.setItem(r, 0, _TWI(field_name))
            self._recon_cred_info_table.setItem(r, 1, _TWI(value))

        # ── Active Sessions tab ───────────────────────────────────────────
        if res.active_sessions:
            for session_user in res.active_sessions:
                r = self._recon_cred_sessions_table.rowCount()
                self._recon_cred_sessions_table.insertRow(r)
                self._recon_cred_sessions_table.setItem(r, 0, _TWI(session_user))
        else:
            r = self._recon_cred_sessions_table.rowCount()
            self._recon_cred_sessions_table.insertRow(r)
            self._recon_cred_sessions_table.setItem(r, 0, _TWI("No active interactive sessions detected"))

        for sw in res.software:
            r = self._recon_cred_sw_table.rowCount()
            self._recon_cred_sw_table.insertRow(r)
            for c, v in enumerate([sw.name, sw.version, sw.source]):
                self._recon_cred_sw_table.setItem(r, c, _TWI(v))

        for svc in res.services:
            r = self._recon_cred_svc_table.rowCount()
            self._recon_cred_svc_table.insertRow(r)
            for c, v in enumerate([svc.name, svc.status, str(svc.pid) if svc.pid else ""]):
                self._recon_cred_svc_table.setItem(r, c, _TWI(v))

        for u in res.users:
            r = self._recon_cred_user_table.rowCount()
            self._recon_cred_user_table.insertRow(r)
            for c, v in enumerate([u.username, u.uid, u.home, u.shell]):
                self._recon_cred_user_table.setItem(r, c, _TWI(v))

    # ── Recon: Ultra-fast Combined Discovery ─────────────────────────────────

    def _build_recon_discovery_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Runs all discovery methods in parallel and merges results:\n"
            "• ARP cache (passive, instant)\n"
            "• ARP broadcast sweep (Scapy — requires admin)\n"
            "• ICMP ping sweep (64 parallel threads)\n"
            "• TCP SYN probe to ports 80/443/22/8080 (Scapy)\n"
            "• mDNS query (zero-conf devices: printers, Chromecast, Apple TV)\n"
            "Typically completes a /24 in under 3 seconds."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        ctrl = QHBoxLayout()
        self._disc_cidr = QLineEdit()
        self._disc_cidr.setPlaceholderText("192.168.1.0/24  (blank = auto-detect)")
        self._disc_cidr.setMaximumWidth(260)
        self._disc_passive_chk = QCheckBox("Passive only (no active probes)")
        self._btn_disc = QPushButton("🚀  Start Discovery")
        self._btn_disc.setObjectName("btnNetRefresh")
        self._btn_disc.clicked.connect(self._start_discovery)
        self._btn_disc_stop = QPushButton("⏹  Stop")
        self._btn_disc_stop.clicked.connect(lambda: self._discovery_worker and self._discovery_worker.stop())
        ctrl.addWidget(self._disc_cidr)
        ctrl.addWidget(self._disc_passive_chk)
        ctrl.addWidget(self._btn_disc)
        ctrl.addWidget(self._btn_disc_stop)
        ctrl.addStretch()

        self._disc_status = QLabel("Combined discovery idle.")
        self._disc_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._disc_status.setWordWrap(True)

        self._recon_disc_table = _table(["IP", "MAC", "Hostname", "Methods", "Latency (ms)"])
        self._recon_disc_table.setColumnWidth(0, 130)
        self._recon_disc_table.setColumnWidth(1, 140)
        self._recon_disc_table.setColumnWidth(2, 200)
        self._recon_disc_table.setColumnWidth(3, 180)

        lay.addWidget(info)
        lay.addLayout(ctrl)
        lay.addWidget(self._disc_status)
        lay.addWidget(self._recon_disc_table, 1)
        return w

    @pyqtSlot()
    def _start_discovery(self):
        from workers.scan_worker import CombinedDiscoveryWorker
        if self._discovery_worker and self._discovery_worker.isRunning():
            return
        self._recon_disc_table.setRowCount(0)
        self._disc_status.setText("Starting combined discovery…")
        self._discovery_worker = CombinedDiscoveryWorker(
            cidr=self._disc_cidr.text().strip(),
            passive_only=self._disc_passive_chk.isChecked(),
        )
        self._discovery_worker.result.connect(self._on_discovery_result)
        self._discovery_worker.status.connect(self._disc_status.setText)
        self._discovery_worker.error.connect(lambda e: self._disc_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._discovery_worker.start()

    @pyqtSlot(object)
    def _on_discovery_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        self._disc_status.setText(res.plain_verdict)
        for dev in res.devices:
            r = self._recon_disc_table.rowCount()
            self._recon_disc_table.insertRow(r)
            ms = f"{dev.response_ms:.0f}" if dev.response_ms else ""
            for c, v in enumerate([dev.ip, dev.mac, dev.hostname,
                                    ", ".join(dev.discovery_methods), ms]):
                self._recon_disc_table.setItem(r, c, _TWI(v))

    # ── Recon: SMB / NetBIOS Enumerator ──────────────────────────────────────

    def _build_recon_smb_tab(self) -> QWidget:
        from PyQt6.QtWidgets import QFormLayout, QTabWidget as _TW
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "NetBIOS + SMB enumeration.\n"
            "Tier 1 (no credentials): machine name, workgroup/domain, OS version, "
            "anonymous session check, share list (Windows scanner only).\n"
            "Tier 2 (with credentials): full share list, local users, active sessions, "
            "local groups. Requires impacket or Windows net.exe."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setContentsMargins(0, 0, 0, 0)
        self._smb_host   = QLineEdit(); self._smb_host.setPlaceholderText("192.168.1.1")
        self._smb_user   = QLineEdit(); self._smb_user.setPlaceholderText("(blank = Tier 1 only)")
        self._smb_pass   = QLineEdit(); self._smb_pass.setPlaceholderText("")
        self._smb_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._smb_domain = QLineEdit(); self._smb_domain.setPlaceholderText("WORKGROUP")
        form.addRow("Host:", self._smb_host)
        form.addRow("Username:", self._smb_user)
        form.addRow("Password:", self._smb_pass)
        form.addRow("Domain:", self._smb_domain)

        ctrl = QHBoxLayout()
        self._btn_smb = QPushButton("🗂  Enumerate SMB")
        self._btn_smb.setObjectName("btnNetRefresh")
        self._btn_smb.clicked.connect(self._start_smb_enum)
        self._btn_smb_stop = QPushButton("⏹  Stop")
        self._btn_smb_stop.clicked.connect(lambda: self._smb_worker and self._smb_worker.stop())
        ctrl.addWidget(self._btn_smb)
        ctrl.addWidget(self._btn_smb_stop)
        ctrl.addStretch()

        self._smb_status = QLabel("SMB enumeration idle.")
        self._smb_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._smb_status.setWordWrap(True)

        self._smb_verdict = QLabel("")
        self._smb_verdict.setWordWrap(True)
        self._smb_verdict.setStyleSheet(
            f"color:{AMBER};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._smb_verdict.hide()

        self._recon_smb_shares_table = _table(["Share", "Type", "Comment", "Risk"])
        self._recon_smb_users_table  = _table(["Username", "SID / UID", "Full Name", "Last Logon"])

        inner_tabs = _TW()
        inner_tabs.addTab(self._recon_smb_shares_table, "📁 Shares")
        inner_tabs.addTab(self._recon_smb_users_table,  "👤 Users")

        lay.addWidget(info)
        lay.addWidget(form_w)
        lay.addWidget(self._smb_verdict)
        lay.addWidget(self._smb_status)
        lay.addLayout(ctrl)
        lay.addWidget(inner_tabs, 1)
        return w

    @pyqtSlot()
    def _start_smb_enum(self):
        from workers.scan_worker import SMBEnumWorker
        host = self._smb_host.text().strip()
        if not host:
            self._smb_status.setText("⚠ Enter a host IP or hostname.")
            return
        if self._smb_worker and self._smb_worker.isRunning():
            return
        self._recon_smb_shares_table.setRowCount(0)
        self._recon_smb_users_table.setRowCount(0)
        self._smb_verdict.hide()
        self._smb_worker = SMBEnumWorker(
            host=host,
            username=self._smb_user.text().strip(),
            password=self._smb_pass.text(),
            domain=self._smb_domain.text().strip(),
        )
        self._smb_worker.result.connect(self._on_smb_result)
        self._smb_worker.status.connect(self._smb_status.setText)
        self._smb_worker.error.connect(lambda e: self._smb_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._smb_worker.start()

    @pyqtSlot(object)
    def _on_smb_result(self, res):
        from PyQt6.QtWidgets import QTableWidgetItem as _TWI
        flags = res.risk_flags
        color = RED if any("Anonymous" in f or "DC" in f for f in flags) else (AMBER if flags else GREEN)
        self._smb_verdict.setText(res.plain_verdict + (f"\n⚠ {' | '.join(flags)}" if flags else ""))
        self._smb_verdict.setStyleSheet(
            f"color:{color};font-size:11px;font-weight:bold;padding:4px;"
            f"background:{BG_CARD};border-radius:4px;"
        )
        self._smb_verdict.show()
        self._smb_status.setText("SMB enumeration complete.")

        high_risk = {"DISK"}
        for share in res.shares:
            r = self._recon_smb_shares_table.rowCount()
            self._recon_smb_shares_table.insertRow(r)
            risk = "HIGH" if (share.share_type in high_risk and not share.name.endswith("$")) else "—"
            for c, v in enumerate([share.name, share.share_type, share.comment, risk]):
                item = _TWI(v)
                if risk == "HIGH":
                    from PyQt6.QtGui import QColor
                    item.setForeground(QColor(RED))
                self._recon_smb_shares_table.setItem(r, c, item)

        for u in res.users:
            r = self._recon_smb_users_table.rowCount()
            self._recon_smb_users_table.insertRow(r)
            for c, v in enumerate([u.username, u.uid, u.full_name, u.last_logon]):
                self._recon_smb_users_table.setItem(r, c, _TWI(v))

    # ── Recon: Plugin System ──────────────────────────────────────────────────

    def _build_recon_plugin_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel(
            "Custom plugins extend NetSentinel with your own checks.\n"
            "Each plugin is a .py file in the plugins/ folder (shown below) with a "
            "PLUGIN_META dict and a run(devices) function that returns a PluginResult.\n"
            "Click Reload to re-scan the folder after adding or editing a plugin."
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:4px 0;")

        ctrl = QHBoxLayout()
        self._btn_plugin_reload = QPushButton("↺  Reload Plugins")
        self._btn_plugin_reload.setObjectName("btnNetRefresh")
        self._btn_plugin_reload.clicked.connect(self._reload_plugins)

        self._btn_plugin_open_dir = QPushButton("📂  Open Plugins Folder")
        self._btn_plugin_open_dir.setObjectName("btnNetRefresh")
        self._btn_plugin_open_dir.clicked.connect(self._open_plugins_dir)

        self._btn_plugin_run = QPushButton("▶  Run Selected")
        self._btn_plugin_run.setObjectName("btnNetRefresh")
        self._btn_plugin_run.clicked.connect(self._run_selected_plugin)

        ctrl.addWidget(self._btn_plugin_reload)
        ctrl.addWidget(self._btn_plugin_open_dir)
        ctrl.addWidget(self._btn_plugin_run)
        ctrl.addStretch()

        self._plugin_dir_lbl = QLabel("")
        self._plugin_dir_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")

        self._plugin_list_table = _table(["Plugin", "Version", "Tags", "Description", "Author"])
        self._plugin_list_table.setColumnWidth(0, 180)
        self._plugin_list_table.setColumnWidth(1, 60)
        self._plugin_list_table.setColumnWidth(2, 120)
        self._plugin_list_table.setColumnWidth(3, 300)

        self._plugin_status = QLabel("Click Reload Plugins to discover .py files in the plugins folder.")
        self._plugin_status.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        self._plugin_status.setWordWrap(True)

        self._plugin_result_text = QTextEdit()
        self._plugin_result_text.setReadOnly(True)
        self._plugin_result_text.setMaximumHeight(160)
        self._plugin_result_text.setStyleSheet(
            f"background:{BG_CARD};color:{TEXT_PRIMARY};font-size:11px;"
            f"border:1px solid {BORDER};border-radius:{CARD_RADIUS};padding:6px;"
        )
        self._plugin_result_text.setPlaceholderText("Plugin output will appear here…")

        lay.addWidget(info)
        lay.addLayout(ctrl)
        lay.addWidget(self._plugin_dir_lbl)
        lay.addWidget(self._plugin_list_table, 1)
        lay.addWidget(self._plugin_status)
        lay.addWidget(self._plugin_result_text)

        self._plugins: list = []
        self._plugin_worker = None
        self._reload_plugins()
        return w

    @pyqtSlot()
    def _reload_plugins(self):
        from modules.plugin_system import load_plugins, plugins_dir
        self._plugins = load_plugins()
        d = plugins_dir()
        self._plugin_dir_lbl.setText(f"Plugins folder: {d}")
        self._plugin_list_table.setRowCount(0)
        for p in self._plugins:
            r = self._plugin_list_table.rowCount()
            self._plugin_list_table.insertRow(r)
            for c, v in enumerate([p.name, p.version, p.tag_str, p.description, p.author]):
                self._plugin_list_table.setItem(r, c, QTableWidgetItem(v))
        n = len(self._plugins)
        self._plugin_status.setText(
            f"{n} plugin{'s' if n != 1 else ''} loaded. Select one and click Run Selected."
        )

    @pyqtSlot()
    def _open_plugins_dir(self):
        from modules.plugin_system import plugins_dir
        import subprocess, sys
        d = str(plugins_dir())
        if sys.platform == "win32":
            subprocess.Popen(["explorer", d])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", d])
        else:
            subprocess.Popen(["xdg-open", d])

    @pyqtSlot()
    def _run_selected_plugin(self):
        from workers.scan_worker import PluginWorker
        row = self._plugin_list_table.currentRow()
        if row < 0 or row >= len(self._plugins):
            self._plugin_status.setText("⚠ Select a plugin from the list first.")
            return
        if self._plugin_worker and self._plugin_worker.isRunning():
            return
        info = self._plugins[row]
        # Use Module 1 scan results as device list if available
        devices = []
        if self._m1_result:
            devices = self._m1_result.get("devices", [])
        self._plugin_status.setText(f"Running '{info.name}'…")
        self._plugin_result_text.clear()
        self._plugin_worker = PluginWorker(info, devices)
        self._plugin_worker.result.connect(self._on_plugin_result)
        self._plugin_worker.status.connect(self._plugin_status.setText)
        self._plugin_worker.error.connect(self._on_plugin_error)
        self._plugin_worker.start()

    @pyqtSlot(object)
    def _on_plugin_result(self, res):
        lines = [f"Plugin: {res.plugin_name}", f"Risk: {res.risk_level}"]
        if res.findings:
            lines.append(f"Findings ({len(res.findings)}):")
            for f in res.findings:
                lines.append(f"  • {f}")
        else:
            lines.append("No findings.")
        self._plugin_result_text.setPlainText("\n".join(lines))
        color = RED if res.risk_level in ("HIGH", "CRITICAL") else (AMBER if res.risk_level == "MEDIUM" else GREEN)
        self._plugin_status.setText(
            f"'{res.plugin_name}' complete — {res.risk_level} "
            f"({len(res.findings)} finding{'s' if len(res.findings) != 1 else ''})."
        )
        self._plugin_status.setStyleSheet(f"color:{color};font-size:11px;")

    @pyqtSlot(str)
    def _on_plugin_error(self, msg: str):
        self._plugin_result_text.setPlainText(f"ERROR:\n{msg}")
        self._plugin_status.setText("Plugin failed — see output above.")
        self._plugin_status.setStyleSheet(f"color:{RED};font-size:11px;")

    # ── Private Endpoint Checker tab ─────────────────────────────────────────

    def _build_recon_pe_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        title = QLabel("🔒  Private Endpoint Checker")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold; background:transparent; border:none;")
        lay.addWidget(title)

        desc = QLabel(
            "Verify that named service endpoints resolve to private (RFC-1918) IPs, "
            "are TCP-reachable, and have valid TLS certificates.  "
            "Works for Azure Private Link, AWS PrivateLink, and any internal hostname:port."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        lay.addWidget(desc)

        # ── Input area ────────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS};"
        )
        input_lay = QVBoxLayout(input_frame)
        input_lay.setContentsMargins(14, 10, 14, 10)
        input_lay.setSpacing(6)

        input_lbl = QLabel("Endpoints — one per line, format:  hostname:port  or  IP:port  (port optional, defaults to 443)")
        input_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        input_lay.addWidget(input_lbl)

        self._pe_input = QTextEdit()
        self._pe_input.setPlaceholderText(
            "myblob.privatelink.blob.core.windows.net:443\n"
            "my-rds.cluster-xxxx.us-east-1.rds.amazonaws.com:5432\n"
            "10.0.1.55:22"
        )
        self._pe_input.setFixedHeight(100)
        self._pe_input.setStyleSheet(
            f"background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER};"
            "border-radius:4px; padding:6px; font-size:12px; font-family:'Courier New';"
        )
        input_lay.addWidget(self._pe_input)

        btn_row = QHBoxLayout()
        self._btn_pe_run = QPushButton("▶  Run Checks")
        self._btn_pe_run.setObjectName("btnDiag")
        self._btn_pe_run.setFixedHeight(34)
        self._btn_pe_run.clicked.connect(self._run_pe_checks)
        self._btn_pe_clear = QPushButton("Clear")
        self._btn_pe_clear.setFixedHeight(34)
        self._btn_pe_clear.clicked.connect(lambda: (
            self._pe_table.setRowCount(0),
            self._pe_status.setText("")
        ))
        self._pe_status = QLabel("")
        self._pe_status.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px;")
        btn_row.addWidget(self._btn_pe_run)
        btn_row.addWidget(self._btn_pe_clear)
        btn_row.addWidget(self._pe_status, 1)
        input_lay.addLayout(btn_row)
        lay.addWidget(input_frame)

        # ── Results table ─────────────────────────────────────────────────────
        self._pe_table = _table([
            "Status", "Endpoint", "Cloud", "Resolved IP(s)",
            "Private?", "TCP", "TLS Days", "Findings"
        ])
        self._pe_table.setColumnWidth(0, 60)
        self._pe_table.setColumnWidth(1, 220)
        self._pe_table.setColumnWidth(2, 70)
        self._pe_table.setColumnWidth(3, 150)
        self._pe_table.setColumnWidth(4, 65)
        self._pe_table.setColumnWidth(5, 55)
        self._pe_table.setColumnWidth(6, 70)
        lay.addWidget(self._pe_table, 1)

        return w

    @pyqtSlot()
    def _run_pe_checks(self):
        from workers.scan_worker import PrivateEndpointWorker
        from modules.private_endpoint_checker import EndpointSpec

        raw = self._pe_input.toPlainText().strip()
        if not raw:
            self._pe_status.setText("⚠ Enter at least one endpoint above.")
            return
        if self._pe_worker and self._pe_worker.isRunning():
            return

        specs: list = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                # Could be host:port OR IPv6 — detect by counting colons
                parts = line.rsplit(":", 1)
                try:
                    port = int(parts[1])
                    host = parts[0].strip("[]")
                except ValueError:
                    host = line
                    port = 443
            else:
                host = line
                port = 443
            specs.append(EndpointSpec(host=host, port=port))

        if not specs:
            self._pe_status.setText("⚠ No valid endpoints parsed.")
            return

        self._pe_table.setRowCount(0)
        self._pe_status.setText(f"Checking {len(specs)} endpoint(s)…")
        self._btn_pe_run.setEnabled(False)

        self._pe_worker = PrivateEndpointWorker(specs)
        self._pe_worker.result.connect(self._on_pe_result)
        self._pe_worker.status.connect(self._pe_status.setText)
        self._pe_worker.error.connect(lambda e: self._pe_status.setText(f"⚠ {e}"), Qt.ConnectionType.QueuedConnection)
        self._pe_worker.finished_all.connect(self._on_pe_done)
        self._pe_worker.start()

    @pyqtSlot(object)
    def _on_pe_result(self, res):
        from PyQt6.QtGui import QColor
        row = self._pe_table.rowCount()
        self._pe_table.insertRow(row)

        status_color = GREEN if res.status == "PASS" else (AMBER if res.status == "WARN" else RED)
        ips_str  = ", ".join(res.resolved_ips[:3]) + ("…" if len(res.resolved_ips) > 3 else "")
        priv_str = "✔ Yes" if res.is_private else ("⚠ LEAK" if res.dns_leak else "—")
        tcp_str  = "✔" if res.tcp_open else "✘"
        tls_str  = str(res.cert.days_left) if (res.cert and not res.cert.error and res.cert.days_left >= 0) else "—"
        findings = " | ".join(res.findings) if res.findings else "All checks passed"
        if res.dns_server:
            findings += f"  [resolver: {res.dns_server}]"

        vals = [res.status, res.spec.label, res.cloud or "—", ips_str,
                priv_str, tcp_str, tls_str, findings]
        for col, val in enumerate(vals):
            item = QTableWidgetItem(str(val))
            c = status_color if col == 0 else (
                (GREEN if "✔" in str(val) else (RED if "✘" in str(val) or "LEAK" in str(val) else TEXT_PRIMARY))
            )
            item.setForeground(QColor(c))
            self._pe_table.setItem(row, col, item)

    @pyqtSlot()
    def _on_pe_done(self):
        total = self._pe_table.rowCount()
        fails = sum(
            1 for r in range(total)
            if (self._pe_table.item(r, 0) or QTableWidgetItem()).text() == "FAIL"
        )
        self._pe_status.setText(
            f"✓ Done — {total} endpoint(s), {fails} FAIL, {total - fails} OK."
        )
        self._btn_pe_run.setEnabled(True)







