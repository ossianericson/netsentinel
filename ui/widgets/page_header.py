"""
PageHeaderBar — slim 40px page-level header (POLISH-6).

Usage::

    from ui.widgets.page_header import PageHeaderBar

    hdr = PageHeaderBar("Live Bandwidth")
    hdr.add_chip("94 Mbps up")          # optional; call add_chip() for each live stat
    root.addWidget(hdr)

    # Update a chip dynamically:
    hdr.set_chip(0, "110 Mbps up")

    # Or use a pre-named chip so you can update it by key:
    hdr.add_chip("—", key="upload")
    hdr.set_chip_by_key("upload", "110 Mbps up")
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QCursor
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui.styles import ACCENT, BG_CARD, BORDER, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, BG_HOVER, WHITE


class PageHeaderBar(QWidget):
    """40px title bar: bold page title left · live chips right · 1px separator."""

    _CHIP_STYLE = (
        f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
        " padding: 0 0 0 0;"
    )
    _SEP_STYLE = f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;"

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setObjectName("PageHeaderBar")
        self.setStyleSheet(
            f"#PageHeaderBar {{ background: transparent; border-bottom: 1px solid {BORDER}; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._title_lbl = QLabel(title)
        self._title_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:14px; font-weight:600;"
            " background:transparent; border:none;"
        )
        lay.addWidget(self._title_lbl)
        lay.addStretch(1)

        # Chip area — chips and separators added dynamically
        self._chip_area = QHBoxLayout()
        self._chip_area.setContentsMargins(0, 0, 0, 0)
        self._chip_area.setSpacing(0)
        lay.addLayout(self._chip_area)

        self._chips:     list[QLabel] = []
        self._chip_keys: dict[str, QLabel] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def add_chip(self, text: str, key: str = "") -> None:
        """Append a chip to the right side. Multiple chips are separated by ·."""
        if self._chips:
            sep = QLabel(" · ")
            sep.setStyleSheet(self._SEP_STYLE)
            self._chip_area.addWidget(sep)

        lbl = QLabel(text)
        lbl.setStyleSheet(self._CHIP_STYLE)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._chip_area.addWidget(lbl)
        self._chips.append(lbl)
        if key:
            self._chip_keys[key] = lbl

    def set_chip(self, index: int, text: str) -> None:
        if 0 <= index < len(self._chips):
            self._chips[index].setText(text)

    def set_chip_by_key(self, key: str, text: str) -> None:
        if key in self._chip_keys:
            self._chip_keys[key].setText(text)

    def set_help(self, title: str, body: str, tips: list | None = None) -> None:
        """Add a ? button that shows a floating help panel on click."""
        if hasattr(self, "_help_btn"):
            return  # already set

        self._help_popover = _HelpPopover(title, body, tips=tips)

        self._help_btn = QPushButton("?")
        self._help_btn.setFixedSize(22, 22)
        self._help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._help_btn.setToolTip("Page help")
        self._help_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; font-size:11px;"
            f" font-weight:bold; border:1px solid {BORDER}; border-radius:11px; padding:0; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; color:{ACCENT}; background:transparent; }}"
            f"QPushButton:checked {{ background:{ACCENT}; color:{WHITE}; border-color:{ACCENT}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        self._help_btn.setCheckable(True)
        self._help_btn.toggled.connect(self._toggle_help)
        self._chip_area.addSpacing(8)
        self._chip_area.addWidget(self._help_btn)

    def _toggle_help(self, checked: bool) -> None:
        if not checked:
            self._help_popover.hide()
            return
        btn_global = self._help_btn.mapToGlobal(
            QPoint(self._help_btn.width() // 2, self._help_btn.height())
        )
        self._help_popover.show_at(btn_global)

    def _close_help(self) -> None:
        self._help_popover.hide()
        if hasattr(self, "_help_btn"):
            self._help_btn.setChecked(False)

    def refresh_theme(self) -> None:
        import ui.styles as _s
        PageHeaderBar._CHIP_STYLE = (
            f"color:{_s.TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
            " padding: 0 0 0 0;"
        )
        PageHeaderBar._SEP_STYLE = (
            f"color:{_s.TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
        )
        self.setStyleSheet(
            f"#PageHeaderBar {{ background: transparent; border-bottom: 1px solid {_s.BORDER}; }}"
        )
        self._title_lbl.setStyleSheet(
            f"color:{_s.TEXT_PRIMARY}; font-size:14px; font-weight:600;"
            " background:transparent; border:none;"
        )
        for chip in self._chips:
            chip.setStyleSheet(self._CHIP_STYLE)
        if hasattr(self, "_help_btn"):
            self._help_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{_s.TEXT_MUTED}; font-size:11px;"
                f" font-weight:bold; border:1px solid {_s.BORDER}; border-radius:11px; padding:0; }}"
                f"QPushButton:hover {{ border-color:{_s.ACCENT}; color:{_s.ACCENT}; background:transparent; }}"
                f"QPushButton:checked {{ background:{_s.ACCENT}; color:{_s.WHITE}; border-color:{_s.ACCENT}; }}"
                f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.TEXT_MUTED}; }}"
            )


_GLOBAL_SHORTCUTS = [
    ("Ctrl+K", "Command palette"),
    ("Ctrl+F", "Focus sidebar search"),
    ("Esc", "Close flyout"),
]


class _HelpPopover(QFrame):
    """Floating 300px help panel shown below the ? button."""

    def __init__(
        self,
        title: str,
        body: str,
        tips: list | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(300)
        self.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        title_lbl.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" background:transparent; border:none;"
        )
        lay.addWidget(title_lbl)

        def _section_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
                f" background:transparent; border:none; letter-spacing:0.5px;"
            )
            return lbl

        lay.addWidget(_section_label("WHAT IT DOES"))
        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;"
        )
        lay.addWidget(body_lbl)

        if tips:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"color:{BORDER}; background:{BORDER};")
            sep.setFixedHeight(1)
            lay.addWidget(sep)
            lay.addWidget(_section_label("TIPS"))
            for tip in tips[:2]:
                tip_lbl = QLabel(f"▸  {tip}")
                tip_lbl.setWordWrap(True)
                tip_lbl.setStyleSheet(
                    f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
                )
                lay.addWidget(tip_lbl)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet(f"color:{BORDER}; background:{BORDER};")
        sep2.setFixedHeight(1)
        lay.addWidget(sep2)
        lay.addWidget(_section_label("SHORTCUTS"))
        for key, desc in _GLOBAL_SHORTCUTS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            key_lbl = QLabel(key)
            key_lbl.setFixedWidth(56)
            key_lbl.setStyleSheet(
                f"font-size:10px; font-weight:bold; color:{ACCENT};"
                f" background:transparent; border:none; font-family:Consolas,monospace;"
            )
            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet(
                f"font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
            )
            row.addWidget(key_lbl)
            row.addWidget(desc_lbl, 1)
            lay.addLayout(row)

    def show_at(self, global_pos: QPoint) -> None:
        self.adjustSize()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 4

        # Clamp so the popover stays fully on-screen.
        screen = QApplication.screenAt(global_pos)
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            x = max(avail.left() + 4, min(x, avail.right()  - self.width()  - 4))
            y = max(avail.top()  + 4, min(y, avail.bottom() - self.height() - 4))

        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.move(x, y)
        self.show()
        self.raise_()
