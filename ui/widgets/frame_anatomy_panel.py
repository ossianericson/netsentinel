"""
FrameAnatomyPanel — collapsible "Frame Anatomy" inspector for the Protocol Visualizer (Phase A2).

Shows the current AnimStep's FrameLayer breakdown as a row of segmented pill
buttons (one per layer: "Ethernet II", "IPv4", "UDP", "DHCP", ...). Clicking a
segment shows its field/value pairs in a compact table below. Pattern-matched
off _ContextPanel (ui/pages/protocol_viz_page.py) and ExplainerPanel
(ui/widgets/explainer_panel.py) — same collapsible toggle-bar shape.

Usage::

    panel = FrameAnatomyPanel()
    layout.addWidget(panel)
    panel.set_layers(step.layers)   # call on every step change; [] hides the panel
"""
from __future__ import annotations

from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFrame, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

from modules.protocol_animator import FrameLayer
from ui import styles as _s
from ui.widgets.jargon_tooltip import get_definition


class FrameAnatomyPanel(QFrame):
    """Collapsible layered frame breakdown shown under the protocol canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("frameAnatomyPanel")
        _s.themed_ss(self, "QFrame#frameAnatomyPanel {{ background:transparent; border:none; }}")

        self._layers: List[FrameLayer] = []
        self._selected_index: int = 0
        self._segment_btns: List[QPushButton] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Toggle bar — collapsed by default, same shape as _ContextPanel.
        self._toggle = QPushButton("  ▸  Frame Anatomy")
        self._toggle.setCheckable(True)
        _s.themed_ss(self._toggle, "QPushButton {{ background:transparent; border:none;"
            " border-top:1px solid {BORDER}; color:{TEXT_MUTED}; font-size:11px;"
            " font-weight:600; text-align:left; padding:6px 12px; }}"
            "QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            "QPushButton:checked {{ color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
        self._toggle.toggled.connect(self._on_toggle)
        root.addWidget(self._toggle)

        # Expanded body
        self._body = QFrame()
        self._body.setVisible(False)
        _s.themed_ss(self._body, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0; }}")
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(16, 12, 16, 12)
        body_lay.setSpacing(8)

        self._segment_row = QHBoxLayout()
        self._segment_row.setSpacing(6)
        self._segment_group = QButtonGroup(self)
        self._segment_group.setExclusive(True)
        body_lay.addLayout(self._segment_row)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Field", "Value"])
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setMaximumHeight(180)
        _s.themed_ss(self._table, "QTableWidget {{ font-size:11px; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; background:{BG_CARD}; gridline-color:{BORDER}; }}"
            "QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:10px;"
            " font-weight:bold; border:none; padding:3px 6px; }}"
            "QTableWidget::item {{ padding:2px 6px; }}")
        body_lay.addWidget(self._table)

        root.addWidget(self._body)
        self.setVisible(False)

    # ── Public interface ───────────────────────────────────────────────────────

    def set_layers(self, layers: Optional[List[FrameLayer]]) -> None:
        """Rebuild the segment row for *layers* and show the previously-selected
        segment's fields (index clamped to the new layer count). Empty/None
        hides the whole panel — used for the missing-scan-data placeholder state.
        """
        layers = layers or []
        self._layers = layers

        while self._segment_row.count():
            item = self._segment_row.takeAt(0)
            w = item.widget()
            if w is not None:
                self._segment_group.removeButton(w)
                w.deleteLater()
        self._segment_btns = []

        if not layers:
            self._table.setRowCount(0)
            self.setVisible(False)
            return

        index = min(max(self._selected_index, 0), len(layers) - 1)
        self._selected_index = index

        for i, layer in enumerate(layers):
            btn = QPushButton(layer.name)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked, idx=i: self._on_segment_clicked(idx))
            self._segment_group.addButton(btn)
            self._segment_btns.append(btn)
            self._segment_row.addWidget(btn)
        self._segment_row.addStretch()
        self._style_segments()

        self._show_layer(layers[index])
        self.setVisible(True)

    # ── Internal ────────────────────────────────────────────────────────────────

    def _style_segments(self) -> None:
        for i, btn in enumerate(self._segment_btns):
            active = (i == self._selected_index)
            btn.setStyleSheet(
                f"QPushButton {{ border-radius:10px; font-size:10px; font-weight:bold;"
                f" padding:2px 10px;"
                f" background:{_s.ACCENT if active else 'transparent'};"
                f" color:{_s.WHITE if active else _s.TEXT_SECONDARY};"
                f" border:1px solid {_s.ACCENT if active else _s.BORDER}; }}"
                f"QPushButton:hover {{ background:{_s.ACCENT}; color:{_s.WHITE}; }}"
                f"QPushButton:pressed {{ color:{_s.TEXT_PRIMARY}; }}"
            )
            btn.setChecked(active)

    def _on_segment_clicked(self, index: int) -> None:
        self._selected_index = index
        self._style_segments()
        if 0 <= index < len(self._layers):
            self._show_layer(self._layers[index])

    def _show_layer(self, layer: FrameLayer) -> None:
        self._table.setRowCount(len(layer.fields))
        for row, (name, value) in enumerate(layer.fields):
            name_item = QTableWidgetItem(name)
            definition = get_definition(name)
            if definition:
                name_item.setToolTip(_s.safe_tooltip(definition))
            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, QTableWidgetItem(str(value)))

    def _on_toggle(self, checked: bool) -> None:
        self._toggle.setText("  ▾  Frame Anatomy" if checked else "  ▸  Frame Anatomy")
        self._body.setVisible(checked)
