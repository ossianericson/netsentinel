"""
PageHeaderBar — slim page-level header (POLISH-6).

40px without subtitle, 56px with subtitle.

Usage::

    from ui.widgets.page_header import PageHeaderBar

    hdr = PageHeaderBar("Live Bandwidth", subtitle="Shows data transfer speeds for each network interface in real time.")
    hdr.add_chip("94 Mbps up")          # optional; call add_chip() for each live stat
    root.addWidget(hdr)

    # Update a chip dynamically:
    hdr.set_chip(0, "110 Mbps up")

    # Or use a pre-named chip so you can update it by key:
    hdr.add_chip("—", key="upload")
    hdr.set_chip_by_key("upload", "110 Mbps up")

    # First-visit context banner (S7-1) — dismissible strip below the header,
    # shown once per page_key then never again (tracked via ui/context_banners.py):
    hdr.show_first_visit_banner(
        "live_bandwidth",
        "This chart updates every second. Look for sustained spikes — a short burst "
        "during a video call is normal; an interface pegged at 100% for minutes is not.",
    )
"""
from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ui import styles as _s
from ui.styles import alpha, themed_ss
from ui.widgets.device_detail_pane import _wire_close_icon


class PageHeaderBar(QWidget):
    """Title bar: bold page title left · optional subtitle below · live chips right · 1px separator.

    Height is 40px without subtitle, 56px with subtitle.
    """

    _CHIP_STYLE = (
        f"color:{_s.TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
        " padding: 0 0 0 0;"
    )
    _SEP_STYLE = f"color:{_s.TEXT_MUTED}; font-size:11px; background:transparent; border:none;"

    _BANNER_HEIGHT = 30

    def __init__(self, title: str, subtitle: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._has_subtitle = bool(subtitle)
        self._base_height = 56 if self._has_subtitle else 40
        self._banner_key = ""
        self.setFixedHeight(self._base_height)
        self.setObjectName("PageHeaderBar")
        _s.themed_ss(self, "#PageHeaderBar {{ background: transparent; border-bottom: 1px solid {BORDER}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_row = QWidget()
        top_row.setFixedHeight(self._base_height)
        outer = QHBoxLayout(top_row)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Left side: title (+ optional subtitle below it)
        if self._has_subtitle:
            left = QVBoxLayout()
            left.setContentsMargins(0, 0, 0, 0)
            left.setSpacing(1)
        else:
            left = None

        self._title_lbl = QLabel(title)
        _s.themed_ss(self._title_lbl, "color:{TEXT_PRIMARY}; font-size:14px; font-weight:600;"
            " background:transparent; border:none;")

        if left is not None:
            left.addWidget(self._title_lbl)
            self._subtitle_lbl = QLabel(subtitle)
            _s.themed_ss(self._subtitle_lbl, "color:{TEXT_MUTED}; font-size:10px; background:transparent; border:none;")
            left.addWidget(self._subtitle_lbl)
            outer.addLayout(left)
        else:
            self._subtitle_lbl = None
            outer.addWidget(self._title_lbl)

        outer.addStretch(1)

        # Chip area — chips and separators added dynamically
        self._chip_area = QHBoxLayout()
        self._chip_area.setContentsMargins(0, 0, 0, 0)
        self._chip_area.setSpacing(0)
        outer.addLayout(self._chip_area)

        self._chips:     list[QLabel] = []
        self._chip_keys: dict[str, QLabel] = {}

        root.addWidget(top_row)

        # First-visit context banner (S7-1) — hidden until show_first_visit_banner() is called
        self._banner_row = QWidget()
        self._banner_row.setFixedHeight(self._BANNER_HEIGHT)
        self._banner_row.setVisible(False)
        banner_lay = QHBoxLayout(self._banner_row)
        banner_lay.setContentsMargins(0, 0, 0, 4)
        banner_lay.setSpacing(8)

        self._banner_lbl = QLabel("")
        self._banner_lbl.setWordWrap(True)
        _s.themed_ss(self._banner_lbl, "color:{TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;")
        banner_lay.addWidget(self._banner_lbl, 1)

        self._banner_dismiss_btn = QPushButton()
        self._banner_dismiss_btn.setFixedSize(18, 18)
        self._banner_dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._banner_dismiss_btn.setToolTip("Dismiss — won't show again")
        _wire_close_icon(self._banner_dismiss_btn)
        _s.themed_ss(self._banner_dismiss_btn, "QPushButton {{ background:transparent; border:none; padding:0; }}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:transparent; }}")
        self._banner_dismiss_btn.clicked.connect(self._dismiss_banner)
        banner_lay.addWidget(self._banner_dismiss_btn)

        root.addWidget(self._banner_row)

    # ── Public API ────────────────────────────────────────────────────────────

    def show_first_visit_banner(self, page_key: str, text: str) -> None:
        """Show a dismissible one-paragraph banner below the header (S7-1).

        No-op if the banner for ``page_key`` was already dismissed (or shown
        and auto-marked seen) in a previous session. Call once per page
        construction — the banner only ever appears on a user's first visit.
        """
        from ui.context_banners import should_show_banner
        if not should_show_banner(page_key):
            return
        self._banner_key = page_key
        self._banner_lbl.setText(f"ⓘ  {text}")
        self._banner_row.setVisible(True)
        self.setFixedHeight(self._base_height + self._BANNER_HEIGHT)

    def _dismiss_banner(self) -> None:
        from ui.context_banners import mark_banner_seen
        if self._banner_key:
            mark_banner_seen(self._banner_key)
        self._banner_row.setVisible(False)
        self.setFixedHeight(self._base_height)

    def set_title(self, title: str) -> None:
        self._title_lbl.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        if self._subtitle_lbl is not None:
            self._subtitle_lbl.setText(subtitle)

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
            f"QPushButton {{ background:transparent; color:{_s.TEXT_MUTED}; font-size:11px;"
            f" font-weight:bold; border:1px solid {alpha(_s.WHITE, 0x22)}; border-radius:11px; padding:0; }}"
            f"QPushButton:hover {{ border-color:{_s.ACCENT}; color:{_s.ACCENT}; background:transparent; }}"
            f"QPushButton:checked {{ background:{_s.ACCENT}; color:{_s.WHITE}; border-color:{_s.ACCENT}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.TEXT_MUTED}; }}"
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

    def hideEvent(self, event) -> None:
        # Auto-dismiss the help popover when the page is navigated away from —
        # the QStackedWidget hides the outgoing page, firing hideEvent on its
        # header, so the popover never gets left stuck open on another page.
        if hasattr(self, "_help_popover"):
            self._close_help()
        super().hideEvent(event)

    def refresh_theme(self) -> None:
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
        if self._subtitle_lbl is not None:
            self._subtitle_lbl.setStyleSheet(
                f"color:{_s.TEXT_MUTED}; font-size:10px; background:transparent; border:none;"
            )
        for chip in self._chips:
            chip.setStyleSheet(self._CHIP_STYLE)
        if hasattr(self, "_help_btn"):
            self._help_btn.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{_s.TEXT_MUTED}; font-size:11px;"
                f" font-weight:bold; border:1px solid {_s.alpha(_s.WHITE, 0x22)}; border-radius:11px; padding:0; }}"
                f"QPushButton:hover {{ border-color:{_s.ACCENT}; color:{_s.ACCENT}; background:transparent; }}"
                f"QPushButton:checked {{ background:{_s.ACCENT}; color:{_s.WHITE}; border-color:{_s.ACCENT}; }}"
                f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.TEXT_MUTED}; }}"
            )
        self._banner_lbl.setStyleSheet(
            f"color:{_s.TEXT_SECONDARY}; font-size:11px; background:transparent; border:none;"
        )
        self._banner_dismiss_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{_s.TEXT_MUTED}; font-size:13px;"
            f" border:none; padding:0; }}"
            f"QPushButton:hover {{ color:{_s.TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ color:{_s.TEXT_MUTED}; }}"
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
        themed_ss(
            self,
            "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:4px; }}",
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)

        title_lbl = QLabel(title)
        title_lbl.setWordWrap(True)
        themed_ss(
            title_lbl,
            "font-size:12px; font-weight:bold; color:{TEXT_PRIMARY};"
            " background:transparent; border:none;",
        )
        lay.addWidget(title_lbl)

        def _section_label(text: str) -> QLabel:
            lbl = QLabel(text)
            themed_ss(
                lbl,
                "font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
                " background:transparent; border:none; letter-spacing:0.5px;",
            )
            return lbl

        lay.addWidget(_section_label("WHAT IT DOES"))
        body_lbl = QLabel(body)
        body_lbl.setWordWrap(True)
        themed_ss(
            body_lbl,
            "font-size:11px; color:{TEXT_PRIMARY}; background:transparent; border:none;",
        )
        lay.addWidget(body_lbl)

        if tips:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            themed_ss(sep, "color:{BORDER}; background:{BORDER};")
            sep.setFixedHeight(1)
            lay.addWidget(sep)
            lay.addWidget(_section_label("TIPS"))
            for tip in tips[:2]:
                tip_lbl = QLabel(f"▸  {tip}")
                tip_lbl.setWordWrap(True)
                themed_ss(
                    tip_lbl,
                    "font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;",
                )
                lay.addWidget(tip_lbl)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        themed_ss(sep2, "color:{BORDER}; background:{BORDER};")
        sep2.setFixedHeight(1)
        lay.addWidget(sep2)
        lay.addWidget(_section_label("SHORTCUTS"))
        for key, desc in _GLOBAL_SHORTCUTS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            key_lbl = QLabel(key)
            key_lbl.setFixedWidth(56)
            themed_ss(
                key_lbl,
                "font-size:10px; font-weight:bold; color:{ACCENT};"
                " background:transparent; border:none; font-family:Consolas,monospace;",
            )
            desc_lbl = QLabel(desc)
            themed_ss(
                desc_lbl,
                "font-size:10px; color:{TEXT_SECONDARY}; background:transparent; border:none;",
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
