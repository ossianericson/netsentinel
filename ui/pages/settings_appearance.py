"""
settings_appearance.py — _SettingsAppearanceMixin: appearance and display card builders.

Extracted from ui/pages/settings_cards.py (Sprint 13) to keep that file within budget.
SettingsPage inherits both _SettingsCardsMixin and _SettingsAppearanceMixin.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtCore import pyqtSignal as _pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import styles as _styles
from ui.styles import (
    ACCENT, ACCENT_PURPLE,
    BG_HOVER, BORDER, DEEP_ORANGE, GREEN, RED, TEAL, TEXT_PRIMARY,
    TEXT_SECONDARY,
)
class _ThemeSwatch(QFrame):
    """Clickable mini colour-palette preview card for one theme."""

    clicked = _pyqtSignal(str)

    def __init__(self, name: str, colors: dict, parent=None):
        super().__init__(parent)
        self._name = name
        self._colors = colors
        self.setFixedSize(128, 90)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Apply {name} theme")
        self._build(colors)

    def _build(self, c: dict) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        nav = QLabel()
        nav.setFixedHeight(12)
        nav.setStyleSheet(f"background:{c['NAV_BAR']};border:none;")
        outer.addWidget(nav)

        body_w = QWidget()
        body_w.setStyleSheet(f"background:{c['BG_DARK']};border:none;")
        body_lay = QHBoxLayout(body_w)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)

        sb = QLabel()
        sb.setFixedWidth(8)
        sb.setStyleSheet(f"background:{c.get('SIDEBAR_BG', c['NAV_BAR'])};border:none;")
        body_lay.addWidget(sb)

        content_w = QWidget()
        content_w.setStyleSheet(f"background:{c['BG_DARK']};border:none;")
        content_lay = QHBoxLayout(content_w)
        content_lay.setContentsMargins(6, 6, 6, 6)
        content_lay.setSpacing(5)

        card = QLabel()
        card.setFixedSize(36, 26)
        card.setStyleSheet(
            f"background:{c['BG_CARD']};border:1px solid {c['BORDER']};border-radius:2px;"
        )
        content_lay.addWidget(card)

        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background:{c['ACCENT']};border-radius:2px;border:none;")
        content_lay.addWidget(dot)
        content_lay.addStretch()

        body_lay.addWidget(content_w, 1)
        outer.addWidget(body_w, 1)

        name_lbl = QLabel(self._name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setFixedHeight(18)
        name_lbl.setStyleSheet(
            f"font-size:10px;font-weight:500;color:{c['TEXT_PRIMARY']};"
            f"background:{c['BG_CARD']};border:none;"
        )
        outer.addWidget(name_lbl)

    def set_active(self, active: bool) -> None:
        own_accent = self._colors["ACCENT"]
        if active:
            self.setStyleSheet(
                f"QFrame{{border:2px solid {own_accent};border-radius:4px;}}"
            )
        else:
            self.setStyleSheet(
                f"QFrame{{border:1px solid {_styles.BORDER};border-radius:4px;}}"
                f"QFrame:hover{{border-color:{own_accent};}}"
            )

    def mousePressEvent(self, event) -> None:
        self.clicked.emit(self._name)


class _SettingsAppearanceMixin:
    """Mixin providing appearance and display card builder methods for SettingsPage.

    Extracted from ui/pages/settings_cards.py (Sprint 13).
    """

    def _build_appearance_card(self) -> QFrame:
        from ui.pages.settings_cards import _card  # lazy import breaks circular dependency
        card, bl = _card("Appearance — Colour Theme")
        desc = QLabel(
            "Choose a colour theme. Takes effect after restarting the app."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px;color:{TEXT_SECONDARY};background:transparent;")
        bl.addWidget(desc)
        self._theme_status_lbl = QLabel("")
        self._theme_status_lbl.setStyleSheet(
            f"font-size:11px;color:{ACCENT};background:transparent;"
        )
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(10)
        self._theme_swatches: dict[str, _ThemeSwatch] = {}
        for name, colors in _styles.THEMES.items():
            sw = _ThemeSwatch(name, colors)
            sw.clicked.connect(self._on_theme)
            self._theme_swatches[name] = sw
            swatch_row.addWidget(sw)
        swatch_row.addStretch()
        bl.addLayout(swatch_row)
        bl.addWidget(self._theme_status_lbl)
        self._refresh_theme_swatches()
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

    def _refresh_theme_swatches(self) -> None:
        active = _styles.get_active_theme_name()
        for name, sw in self._theme_swatches.items():
            sw.set_active(name == active)

    def _on_theme(self, name: str) -> None:
        from ui.styles import set_active_theme_name
        set_active_theme_name(name)
        self._refresh_theme_swatches()
        self._theme_status_lbl.setText(f"Theme '{name}' saved — restart the app to apply.")

    # ── Display preferences ───────────────────────────────────────────────────

    def _build_display_card(self) -> QFrame:
        from ui.pages.settings_cards import _card  # lazy import breaks circular dependency
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
