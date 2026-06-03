"""
settings_appearance.py — _SettingsAppearanceMixin: appearance and display card builders.

Extracted from ui/pages/settings_cards.py (Sprint 13) to keep that file within budget.
SettingsPage inherits both _SettingsCardsMixin and _SettingsAppearanceMixin.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import ui.styles as _styles
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_PURPLE,
    BG_CARD, BG_DARK, BG_HOVER, BORDER, BTN_HOVER_BG, CARD_RADIUS,
    DEEP_ORANGE, GREEN, NAV_BAR, RED, TEAL, TEXT_MUTED, TEXT_PRIMARY,
    TEXT_SECONDARY, WHITE,
)
from ui.pages.settings_cards import _card


class _SettingsAppearanceMixin:
    """Mixin providing appearance and display card builder methods for SettingsPage.

    Extracted from ui/pages/settings_cards.py (Sprint 13).
    """

    def _build_appearance_card(self) -> QFrame:
        card, bl = _card("Appearance — Colour Theme")
        desc = QLabel(
            "Choose a colour theme for the entire application. "
            "Changes apply immediately."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(desc)
        self._theme_status_lbl = QLabel("")
        self._theme_status_lbl.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._theme_btns: dict = {}
        for name in _styles.THEMES:
            btn = QPushButton(name)
            self._theme_btns[name] = btn
            btn_row.addWidget(btn)
            btn.clicked.connect(lambda checked=False, n=name: self._on_theme(n))
        btn_row.addStretch()
        bl.addLayout(btn_row)
        bl.addWidget(self._theme_status_lbl)
        self._refresh_theme_buttons()
        bl.addSpacing(10)
        accent_hdr = QLabel("Accent Colour")
        accent_hdr.setStyleSheet(
            f"font-size:11px;font-weight:bold;color:{TEXT_PRIMARY};background:transparent;"
        )
        bl.addWidget(accent_hdr)
        accent_desc = QLabel(
            "Override the active theme's accent colour. Takes effect on next launch."
        )
        accent_desc.setWordWrap(True)
        accent_desc.setStyleSheet(
            f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;"
        )
        bl.addWidget(accent_desc)
        _ACCENT_PRESETS = [
            (ACCENT, "Blue"), (ACCENT_PURPLE, "Purple"), (GREEN, "Green"),
            (TEAL, "Teal"), (RED, "Red"),    (DEEP_ORANGE, "Orange"),
        ]
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(6)
        self._accent_status_lbl = QLabel("")
        self._accent_status_lbl.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )
        current_override = _styles.get_accent_override()
        for hex_val, name in _ACCENT_PRESETS:
            sw = QPushButton()
            sw.setFixedSize(28, 28)
            sw.setToolTip(f"{name} ({hex_val})")
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            active = (current_override == hex_val)
            border = ACCENT if active else BORDER
            sw.setStyleSheet(
                f"QPushButton{{background:{hex_val};border:2px solid {border};border-radius:4px;}}"
                f"QPushButton:hover{{border-color:{hex_val};}}"
            )
            sw.clicked.connect(
                lambda _=False, hx=hex_val, nm=name: self._on_accent_swatch(hx, nm)
            )
            swatch_row.addWidget(sw)
        custom_btn = QPushButton("Custom…")
        custom_btn.setFlat(True)
        custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        custom_btn.setStyleSheet(
            f"QPushButton{{color:{ACCENT};font-size:11px;background:transparent;"
            f"border:1px solid {BORDER};border-radius:4px;padding:3px 10px;}}"
            f"QPushButton:hover{{border-color:{ACCENT};}}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        custom_btn.clicked.connect(self._on_accent_custom)
        swatch_row.addWidget(custom_btn)
        reset_btn = QPushButton("Reset")
        reset_btn.setFlat(True)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(
            f"QPushButton{{color:{TEXT_SECONDARY};font-size:11px;background:transparent;"
            f"border:1px solid {BORDER};border-radius:4px;padding:3px 10px;}}"
            f"QPushButton:hover{{border-color:{ACCENT};}}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
        )
        reset_btn.clicked.connect(self._on_accent_reset)
        swatch_row.addWidget(reset_btn)
        swatch_row.addStretch()
        bl.addLayout(swatch_row)
        bl.addWidget(self._accent_status_lbl)
        return card

    def _on_accent_swatch(self, hex_val: str, name: str) -> None:
        from ui.styles import apply_accent_override
        apply_accent_override(hex_val)
        self._accent_status_lbl.setText(f"Accent set to {name} ({hex_val}).")

    def _on_accent_custom(self) -> None:
        from PyQt6.QtWidgets import QColorDialog
        from PyQt6.QtGui import QColor
        from ui.styles import apply_accent_override
        current = _styles.get_accent_override() or _styles.ACCENT
        chosen = QColorDialog.getColor(QColor(current), self, "Choose Accent Colour")
        if chosen.isValid():
            hex_val = chosen.name().upper()
            apply_accent_override(hex_val)
            self._accent_status_lbl.setText(f"Custom accent ({hex_val}) applied.")

    def _on_accent_reset(self) -> None:
        from ui.styles import apply_accent_override
        apply_accent_override(None)
        self._accent_status_lbl.setText("Accent reset to theme default.")

    def _refresh_theme_buttons(self) -> None:
        import ui.styles as _s
        active = _s.get_active_theme_name()
        for name, btn in self._theme_btns.items():
            if name == active:
                btn.setStyleSheet(
                    f"QPushButton{{background:{_s.ACCENT};color:{_s.NAV_BAR};"
                    f"border:1px solid {_s.ACCENT};border-radius:4px;"
                    f"padding:5px 14px;font-size:11px;font-weight:bold;}}"
                    f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}"
                )
            else:
                btn.setStyleSheet(
                    f"QPushButton{{background:{_s.BG_CARD};color:{_s.ACCENT};"
                    f"border:1px solid {_s.ACCENT};border-radius:4px;"
                    f"padding:5px 14px;font-size:11px;}}"
                    f"QPushButton:hover{{background:{_s.BTN_HOVER_BG};}}"
                    f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}"
                )

    def _on_theme(self, name: str) -> None:
        from ui.styles import apply_theme
        apply_theme(name)
        self._refresh_theme_buttons()
        self._theme_status_lbl.setText(f"Theme '{name}' applied.")

    # ── Display preferences ───────────────────────────────────────────────────

    def _build_display_card(self) -> QFrame:
        card, bl = _card("Display Preferences")
        qs = QSettings("NetSentinel", "NetSentinel")
        self._chk_compact = QCheckBox("Compact table rows (24 px — more devices visible)")
        self._chk_compact.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_compact.setChecked(qs.value("display/compact_rows", True, type=bool))
        self._chk_compact.toggled.connect(self._on_compact_toggled)
        bl.addWidget(self._chk_compact)
        self._chk_tooltips = QCheckBox("Show extended tooltips on hover (400 ms delay)")
        self._chk_tooltips.setStyleSheet(
            f"font-size:11px;color:{TEXT_PRIMARY};background:transparent;"
        )
        self._chk_tooltips.setChecked(qs.value("display/tooltips_enabled", True, type=bool))
        self._chk_tooltips.toggled.connect(self._on_tooltip_toggled)
        bl.addWidget(self._chk_tooltips)
        note = QLabel(
            "Row height and tooltip settings take effect the next time a table is populated."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"font-size:10px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(note)
        return card

    def _on_compact_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/compact_rows", checked)
        self._mark_dirty()

    def _on_tooltip_toggled(self, checked: bool) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue("display/tooltips_enabled", checked)
        self._mark_dirty()

    # ── Network Scanning ──────────────────────────────────────────────────────
