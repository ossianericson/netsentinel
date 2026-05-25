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

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.styles import BORDER, TEXT_MUTED, TEXT_PRIMARY


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
