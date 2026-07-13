"""
tabs_helpers.py — Shared UI utility functions for tab content builders.

Extracted from ui/tabs.py (Sprint 8). Imported by tabs.py, tabs_scan.py,
tabs_network.py, and tabs_diag.py to avoid circular imports.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QHeaderView,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ui import styles as _s
from ui.styles import alpha


_RISK_LABELS: dict[str, str] = {
    "HIGH":     "Action required",
    "STORM":    "Critical — act now",
    "CRITICAL": "Action required",
    "MEDIUM":   "Needs attention",
    "WARNING":  "Needs attention",
    "LOW":      "Minor notice",
    "CLEAN":    "All clear",
    "NONE":     "All clear",
    "INFO":     "Minor notice",
    "UNKNOWN":  "Not assessed",
}


def risk_to_label(risk: str) -> str:
    """Map an internal scan risk string to a user-facing severity label."""
    return _RISK_LABELS.get((risk or "").upper(), risk or "Unknown")


def _make_scroll_area(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setStyleSheet("QScrollArea { border: none; }")
    return sa


def _table(headers: list) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    # Interactive, not ResizeToContents: ResizeToContents recomputes every
    # column's ideal width (a per-cell sizeHint() / font-metrics pass) on
    # every model change, which freezes the main thread for seconds on
    # tables with hundreds-to-thousands of rows (RULE-PERF1).
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    t.horizontalHeader().setStretchLastSection(True)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(True)
    t.verticalHeader().setDefaultSectionSize(24)  # compact row height
    return t


def _add_row(table: QTableWidget, values: list, level: str = "CLEAN"):
    from PyQt6.QtGui import QColor
    from ui.styles import RISK_COLORS as _RC, TEXT_SECONDARY as _TS
    row = table.rowCount()
    table.insertRow(row)
    color = _RC.get(level.upper(), _TS)
    for col, val in enumerate(values):
        item = QTableWidgetItem(str(val))
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
    w = _W()
    vl = _VL(w)
    vl.setContentsMargins(32, 32, 32, 32)
    vl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic = _L(icon)
    ic.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    ic.setStyleSheet("font-size:30px; background:transparent; border:none;")
    hd = _L(headline)
    hd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    _s.themed_ss(hd, "font-size:13px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent; border:none;")
    bd = _L(body)
    bd.setAlignment(_Qt.AlignmentFlag.AlignCenter)
    bd.setWordWrap(True)
    _s.themed_ss(bd, "font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
    vl.addWidget(ic)
    vl.addWidget(hd)
    vl.addSpacing(4)
    vl.addWidget(bd)
    if cta_label and cta_action:
        vl.addSpacing(10)
        btn = _B(cta_label)
        btn.setFixedHeight(28)
        btn.setCursor(_Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(
            btn,
            "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:4px; font-size:11px; font-weight:600; padding:0 16px; }}"
            "QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        btn.clicked.connect(cta_action)
        hl = _HL()
        hl.setAlignment(_Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(btn)
        vl.addLayout(hl)
    return w


def _error_state_widget(message: str, retry_fn: "callable") -> "QWidget":
    """Reusable error-state panel: warning icon + message + Retry button."""
    from PyQt6.QtWidgets import QWidget as _W, QVBoxLayout as _VL, QHBoxLayout as _HL, QLabel as _L, QPushButton as _B
    from PyQt6.QtCore import Qt as _Qt
    from ui.styles import AMBER as _AM, BG_HOVER as _BH, TEXT_PRIMARY as _TP
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
            f"QPushButton:hover {{ background:{alpha(_AM, 0x22)}; }}"
            f"QPushButton:pressed {{ background:{_BH}; color:{_AM}; }}"
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
    from ui.styles import TEXT_PRIMARY as _TP
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
        f"color:{_TP}; font-weight:bold; font-size:11px;"
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


def _page_header(title: str, subtitle: str = "") -> "QFrame":
    """
    Returns a QFrame header container with 16/20/12px breathing room and a
    1px bottom divider.  title 18px bold TEXT_PRIMARY, subtitle 11px TEXT_SECONDARY.
    """
    from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
    from ui.styles import BORDER as _BR, TEXT_PRIMARY as _TP, TEXT_SECONDARY as _TS
    container = QFrame()
    container.setObjectName("pageHeader")
    container.setStyleSheet(
        f"QFrame#pageHeader {{ background: transparent; border: none;"
        f" border-bottom: 1px solid {_BR}; }}"
    )
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{_TP}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;"
    )
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color:{_TS}; font-size:11px;"
            "padding:0; background:transparent; border:none;"
        )
        vbox.addWidget(s)
    return container


# ── Scan-status label helpers ─────────────────────────────────────────────────

def _scan_age_str(ts: float) -> str:
    """Return a human-readable age string for a scan timestamp.

    Examples: ``"just now"``, ``"2m ago"``, ``"1h 4m ago"``, ``"3d ago"``.
    Returns ``"never"`` when ``ts`` is 0 or None.
    """
    import time as _time
    if not ts:
        return "never"
    age = max(0.0, _time.time() - ts)
    if age < 60:
        return "just now"
    if age < 3600:
        return f"{int(age // 60)}m ago"
    if age < 86400:
        h = int(age // 3600)
        m = int((age % 3600) // 60)
        return f"{h}h {m}m ago" if m else f"{h}h ago"
    return f"{int(age // 86400)}d ago"


def format_scan_status(verdict: str, ts: float) -> str:
    """Build the standardised scan status string used on every scan page.

    Format: ``"<verdict> · Last run: <age>"``

    When ``ts`` is 0/None (never run), returns ``"<verdict> · Never run"``.
    """
    age = _scan_age_str(ts)
    if age == "never":
        return f"{verdict} · Never run"
    return f"{verdict} · Last run: {age}"
