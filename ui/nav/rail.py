"""
ui.nav.rail -- Activity-rail navigation widgets extracted from ui.dashboard.

Provides: _LUCIDE, _make_nav_icon, _NavEntry, _RailButton, _FlyoutItem,
          _FlyoutPanel, _CanvasClickFilter, _ClickLabel, _SmoothProgressBar
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import (
    QByteArray, QEasingCurve, QObject, QPropertyAnimation, QSize,
    Qt, QVariantAnimation, pyqtProperty, pyqtSignal,
)
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QProgressBar, QScrollArea,
    QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AUDIT_RED, BG_HOVER, NAV_DIVIDER, RED, SIDEBAR_BG, SIDEBAR_HOVER,
    SIDEBAR_ITEM_FG, SIDEBAR_SECTION_BG, SIDEBAR_SEL_BG, TEXT_MUTED,
    TEXT_SECONDARY, WHITE,
)


# -- Lucide icon library (MIT) -----------------------------------------------
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


def _make_nav_icon(icon_name: str, size: int = 20, color: str = SIDEBAR_ITEM_FG) -> QIcon:
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

    _COLOR_NORMAL = SIDEBAR_ITEM_FG
    _COLOR_ACTIVE = WHITE
    _LABEL_COLOR  = TEXT_MUTED

    def __init__(self, icon_name: str, tooltip: str, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        # First word of section name, max 9 chars — shown below the icon
        self._short_label = (tooltip.split()[0]) if tooltip else ""
        self._badge_color: str = ""
        self._badge_count: str = ""   # non-empty → numeric red pill overrides dot
        self._left_dot: str = ""      # POLISH-1: monitor state dot on left edge
        # ANIM-3: badge thump — scale 1.25→1.0 on count increase
        self._badge_scale: float = 1.0
        self._badge_anim = QPropertyAnimation(self, b"badgeScale", self)
        self._badge_anim.setDuration(250)
        self._badge_anim.setEasingCurve(QEasingCurve.Type.OutBack)
        # ANIM-9: badge fade-out — opacity 1.0→0.0 when count drops to zero
        self._badge_opacity: float = 1.0
        self._badge_fade_anim = QPropertyAnimation(self, b"badgeOpacity", self)
        self._badge_fade_anim.setDuration(400)
        self._badge_fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._badge_fade_anim.finished.connect(self._on_badge_fade_done)
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

    @pyqtProperty(float)
    def badgeScale(self) -> float:
        return self._badge_scale

    @badgeScale.setter
    def badgeScale(self, value: float) -> None:
        self._badge_scale = value
        self.update()

    @pyqtProperty(float)
    def badgeOpacity(self) -> float:
        return self._badge_opacity

    @badgeOpacity.setter
    def badgeOpacity(self, value: float) -> None:
        self._badge_opacity = value
        self.update()

    def _on_badge_fade_done(self) -> None:
        self._badge_color = ""
        self._badge_count = ""
        self._badge_opacity = 1.0
        self.update()

    def set_badge(self, value) -> None:
        """Set or clear the badge.

        Pass a positive int/str digit to show a red numeric pill.
        Pass a colour string (hex) to show a plain status dot.
        Pass 0, empty string, or None to clear.
        """
        if value and str(value).isdigit() and int(value) > 0:
            new_count = int(value)
            old_count = int(self._badge_count) if self._badge_count else 0
            self._badge_count = str(value)
            self._badge_color = ""
            # ANIM-3: thump on count increase only
            if new_count > old_count:
                from ui.theme import _reduce_motion
                if not _reduce_motion():
                    self._badge_anim.stop()
                    self._badge_anim.setStartValue(1.25)
                    self._badge_anim.setEndValue(1.0)
                    self._badge_anim.start()
        elif value and not str(value).isdigit():
            self._badge_fade_anim.stop()
            self._badge_opacity = 1.0
            self._badge_color = str(value)
            self._badge_count = ""
        else:
            # ANIM-9: fade out rather than immediate hide when a badge was showing
            if self._badge_count or self._badge_color:
                from ui.theme import _reduce_motion
                if not _reduce_motion():
                    self._badge_fade_anim.stop()
                    self._badge_opacity = 1.0
                    self._badge_fade_anim.setStartValue(1.0)
                    self._badge_fade_anim.setEndValue(0.0)
                    self._badge_fade_anim.start()
                    return   # _on_badge_fade_done will clear after 400 ms
            self._badge_color = ""
            self._badge_count = ""
            self._badge_opacity = 1.0
        self.update()

    def set_left_dot(self, color: str) -> None:
        """POLISH-1: set or clear the monitor-state dot on the left edge.

        Pass a hex colour to show; pass empty string to clear.
        """
        self._left_dot = color or ""
        self.update()

    def paintEvent(self, event):
        from ui import styles as _s
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
            p.setBrush(QColor(_s.ACCENT))
            p.drawRect(0, 10, 3, 38)   # spans the 48px icon zone, inset 10px top/bottom

        # POLISH-1: left-edge monitor state dot — 6px, flush left, icon-zone centre
        # Positioned at x=4 to clear the 3px accent bar; y=22 centres it in the icon zone
        if self._left_dot:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._left_dot))
            p.drawEllipse(QRectF(4, 22, 6, 6))

        # Numeric red pill badge — top-right corner (ANIM-3: scaled during thump)
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
            cx = pill_x + pill_w / 2
            cy = pill_y + pill_h / 2
            p.save()
            p.translate(cx, cy)
            p.scale(self._badge_scale, self._badge_scale)
            p.translate(-cx, -cy)
            p.setOpacity(self._badge_opacity)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(_s.RED))
            p.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 7, 7)
            p.setPen(QColor(_s.WHITE))
            p.drawText(QRect(pill_x, pill_y, pill_w, pill_h),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                       self._badge_count)
            p.restore()
        # Plain colour dot badge — top-right corner
        elif self._badge_color:
            p.save()
            p.setOpacity(self._badge_opacity)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(self._badge_color))
            p.drawEllipse(self.width() - 11, 3, 7, 7)
            p.restore()

        # Short label below the icon
        font = QFont("Segoe UI", 7)
        p.setFont(font)
        lbl_color = _s.WHITE if self.isChecked() else _s.SIDEBAR_ITEM_FG
        p.setPen(QColor(lbl_color))
        fm = QFontMetrics(font)
        text = fm.elidedText(self._short_label, Qt.TextElideMode.ElideRight, self.width() - 4)
        p.drawText(QRect(0, 46, self.width(), 12),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   text)
        p.end()

    def _refresh_icon(self):
        from ui import styles as _s
        color = _s.WHITE if self.isChecked() else _s.SIDEBAR_ITEM_FG
        self.setIcon(_make_nav_icon(self._icon_name, 20, color))
        self.setIconSize(QSize(20, 20))

    def setChecked(self, checked: bool):
        super().setChecked(checked)
        self._refresh_icon()

    def refresh_theme(self) -> None:
        from ui import styles as _s
        _RailButton._COLOR_NORMAL = _s.SIDEBAR_ITEM_FG
        _RailButton._COLOR_ACTIVE = _s.WHITE
        _RailButton._LABEL_COLOR  = _s.TEXT_MUTED
        self._refresh_icon()
        self.update()


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
        self._danger = danger
        self._apply_item_style()

    def _apply_item_style(self) -> None:
        from ui import styles as _s
        _fg = _s.AUDIT_RED if self._danger else _s.SIDEBAR_ITEM_FG
        self.setStyleSheet(
            f"QPushButton {{"
            f"  text-align: left; padding: 0 14px;"
            f"  background: transparent; color: {_fg};"
            f"  border: none; font-size: 11px;"
            f"}}"
            f"QPushButton:hover {{ background: {_s.SIDEBAR_HOVER}; color: {_s.WHITE}; }}"
            f"QPushButton:checked {{ background: {_s.SIDEBAR_SEL_BG}; color: {_s.WHITE}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_fg}; }}"
        )

    def refresh_theme(self) -> None:
        self._apply_item_style()

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
        self._flyout_hdr = hdr
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
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
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
        self._hint_lbl = _hint
        _hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; padding: 4px 0;"
            f" background: {SIDEBAR_BG}; border: none;"
            f" border-top: 1px solid {NAV_DIVIDER};"
        )
        outer.addWidget(_hint)

        self._items: dict = {}   # label -> _FlyoutItem

    def refresh_theme(self) -> None:
        from ui import styles as _s
        self.setStyleSheet(f"background: {_s.SIDEBAR_BG};")
        self._flyout_hdr.setStyleSheet(
            f"background: {_s.SIDEBAR_SECTION_BG}; border-bottom: 1px solid {_s.NAV_DIVIDER};"
        )
        self._title_lbl.setStyleSheet(
            f"color: {_s.TEXT_MUTED}; font-size: 9px; font-weight: 600;"
            f" letter-spacing: 1px; background: transparent; border: none;"
        )
        self._pin_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none;"
            f" color: {_s.TEXT_SECONDARY}; font-size: 14px; }}"
            f"QPushButton:hover {{ color: {_s.WHITE}; }}"
            f"QPushButton:checked {{ color: {_s.ACCENT}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.TEXT_SECONDARY}; }}"
        )
        self._hint_lbl.setStyleSheet(
            f"color: {_s.TEXT_MUTED}; font-size: 9px; padding: 4px 0;"
            f" background: {_s.SIDEBAR_BG}; border: none;"
            f" border-top: 1px solid {_s.NAV_DIVIDER};"
        )
        for item in self._items.values():
            item.refresh_theme()

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


class _SmoothProgressBar(QProgressBar):
    """
    ANIM-8: QProgressBar subclass with smooth-eased value transitions.

    Call set_smooth_value(n) to animate from current value to n (250ms InOutSine).
    In indeterminate mode (range 0,0) behaves identically to QProgressBar.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._anim: QVariantAnimation | None = None

    def set_smooth_value(self, target: int) -> None:
        from ui.theme import _reduce_motion
        if _reduce_motion() or self.maximum() == 0:
            self.setValue(target)
            return
        if self._anim is not None:
            self._anim.stop()
        anim = QVariantAnimation(self)
        anim.setStartValue(float(self.value()))
        anim.setEndValue(float(target))
        anim.setDuration(250)
        anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        anim.valueChanged.connect(lambda v: self.setValue(int(v)))
        anim.start()
        self._anim = anim