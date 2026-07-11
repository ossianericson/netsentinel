"""
Inventory dialog helpers — extracted from ui/pages/inventory_page.py.

Contains four standalone QDialog subclasses used by InventoryPage:
  _DeviceLabelDialog     — edit custom name, tags, and notes for a device
  _TypeOverrideDialog    — permanently pin a device to a specific type
  _ScanCompareDialog     — pick two scan sessions to compare
  _SegmentEditorDialog   — create or edit a network segment
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTextEdit, QVBoxLayout,
)

from ui.styles import (
    alpha,
    ACCENT, ACCENT_DARK, ACCENT_LITE, BG_CARD, BG_DARK, BG_HOVER, BORDER,
    RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)

if TYPE_CHECKING:
    from modules.metric_store import MetricStore

from modules.device_admin import (
    clear_classification_override, set_classification_override, update_device_ha_info,
)


# ── Device label editor dialog (DEVICE-1) ────────────────────────────────────

class _DeviceLabelDialog(QDialog):
    """Edit custom name, tags, and notes for a known device."""

    def __init__(self, mac: str, store: "MetricStore", parent=None) -> None:
        super().__init__(parent)
        self._mac = mac
        self._store = store
        self.setWindowTitle("Edit Device")
        self.setMinimumWidth(380)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog {{ background:{BG_CARD}; }}"
            f"QLabel {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QLineEdit, QTextEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:4px; padding:4px; }}"
            f"QLineEdit:focus, QTextEdit:focus {{ border-color:{ACCENT}; }}"
        )

        known = store.get_known_devices()
        device = known.get(mac.lower()) or known.get(mac)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        hdr = QLabel(f"Device  <span style='color:{TEXT_MUTED};font-size:10px;'>{mac}</span>")
        hdr.setStyleSheet(f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};")
        lay.addWidget(hdr)

        form = QFormLayout()
        form.setSpacing(8)
        form.setHorizontalSpacing(12)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. Living Room TV")
        if device and device.custom_name:
            self._name.setText(device.custom_name)

        self._tags = QLineEdit()
        self._tags.setPlaceholderText("e.g. iot, trusted, media — comma-separated")
        if device and device.tags:
            self._tags.setText(device.tags)

        self._notes = QTextEdit()
        self._notes.setPlaceholderText("Notes…")
        self._notes.setFixedHeight(72)
        if device and device.notes:
            self._notes.setPlainText(device.notes)

        def _lbl(t: str) -> QLabel:
            lb = QLabel(t)
            lb.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED};")
            return lb

        form.addRow(_lbl("Name"), self._name)
        form.addRow(_lbl("Tags"), self._tags)
        form.addRow(_lbl("Notes"), self._notes)
        lay.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:hover {{ background:{alpha(ACCENT, 0xdd)}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        btns.accepted.connect(self._save)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _save(self) -> None:
        name = self._name.text().strip() or None
        tags = self._tags.text().strip() or None
        notes = self._notes.toPlainText().strip() or None
        update_device_ha_info(
            self._store, self._mac, custom_name=name, tags=tags, notes=notes
        )
        self.accept()


# ── Device type override dialog (Sprint 6) ──────────────────────────────────

class _TypeOverrideDialog(QDialog):
    """Let the user permanently pin a device to a specific type."""

    def __init__(self, mac: str, current_type: str,
                 current_override: Optional[str],
                 store: "MetricStore", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Override Device Type")
        self.setFixedWidth(340)
        self.setModal(True)
        self._mac   = mac
        self._store = store

        from modules.device_classifier import get_all_device_types
        all_types = get_all_device_types()

        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.setContentsMargins(16, 16, 16, 16)

        info = QLabel(f"<b>{mac}</b><br>Current type: {current_type}")
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        info.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        lay.addWidget(info)

        self._combo = QComboBox()
        self._combo.addItems(all_types)
        self._combo.setStyleSheet(
            f"QComboBox {{ font-size:11px; color:{TEXT_PRIMARY}; background:{BG_CARD};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:3px 6px; }}"
        )
        sel = current_override or current_type
        idx = self._combo.findText(sel)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        lay.addWidget(self._combo)

        btns = QHBoxLayout()
        set_btn = QPushButton("Set Override")
        set_btn.setFixedHeight(28)
        set_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; font-size:11px; padding:0 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        set_btn.clicked.connect(self._set_override)
        btns.addWidget(set_btn)

        if current_override:
            clr_btn = QPushButton("Clear Override")
            clr_btn.setFixedHeight(28)
            clr_btn.setStyleSheet(
                f"QPushButton {{ background:{BG_CARD}; color:{RED};"
                f" border:1px solid {RED}; border-radius:3px; font-size:11px; }}"
                f"QPushButton:hover {{ background:{RED}; color:{WHITE}; }}"
                f"QPushButton:pressed {{ background:{RED}; color:{WHITE}; }}"
            )
            clr_btn.clicked.connect(self._clear_override)
            btns.addWidget(clr_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(28)
        cancel_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px; font-size:11px; }}"
            f"QPushButton:hover {{ border-color:{ACCENT}; color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}"
        )
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)

    def _set_override(self) -> None:
        try:
            set_classification_override(self._store, self._mac, self._combo.currentText())
        except Exception:
            pass  # non-fatal
        self.accept()

    def _clear_override(self) -> None:
        try:
            clear_classification_override(self._store, self._mac)
        except Exception:
            pass  # non-fatal
        self.accept()


# ── Scan comparison dialog (ACT-3) ────────────────────────────────────────────

class _ScanCompareDialog(QDialog):
    """Pick two scan sessions to compare."""

    def __init__(self, sessions: list, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare Scans")
        self.setMinimumWidth(400)
        self.setModal(True)
        self._sessions = sessions  # list of (ts, label)
        self._ts_a = 0
        self._ts_b = 0
        self.setStyleSheet(
            f"QDialog {{ background:{BG_CARD}; }}"
            f"QLabel {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; padding:3px 6px; font-size:11px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        hdr = QLabel("Compare two scan sessions")
        hdr.setStyleSheet(f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};")
        lay.addWidget(hdr)

        desc = QLabel(
            "Scan A is the earlier baseline.  Scan B is the later snapshot.  "
            "New devices appear green; devices that disappeared appear red."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        lay.addWidget(desc)

        labels = [s[1] for s in sessions]

        form = QFormLayout()
        form.setSpacing(8)
        form.setHorizontalSpacing(12)

        def _lbl(t: str) -> QLabel:
            lb = QLabel(t)
            lb.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED};")
            return lb

        self._combo_a = QComboBox()
        self._combo_a.addItems(labels)
        if len(labels) > 1:
            self._combo_a.setCurrentIndex(len(labels) - 2)  # second-to-last = older
        self._combo_b = QComboBox()
        self._combo_b.addItems(labels)
        self._combo_b.setCurrentIndex(len(labels) - 1)   # last = newer

        form.addRow(_lbl("Scan A (baseline)"), self._combo_a)
        form.addRow(_lbl("Scan B (compare to)"), self._combo_b)
        lay.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("Compare")
        btns.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:hover {{ background:{alpha(ACCENT, 0xdd)}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _on_accept(self) -> None:
        self._ts_a = self._sessions[self._combo_a.currentIndex()][0]
        self._ts_b = self._sessions[self._combo_b.currentIndex()][0]
        self.accept()

    def result_timestamps(self) -> tuple:
        return self._ts_a, self._ts_b


# ── Segment editor dialog ─────────────────────────────────────────────────────

class _SegmentEditorDialog(QDialog):
    """Create or edit a network segment (name, CIDR, colour, description)."""

    def __init__(self, segment=None, parent=None) -> None:
        super().__init__(parent)
        from modules.network_segments import SEGMENT_PALETTE
        self._palette = SEGMENT_PALETTE
        self._segment = segment  # None = create new
        self.setWindowTitle("Edit Segment" if segment else "New Segment")
        self.setMinimumWidth(380)
        self.setModal(True)
        self.setStyleSheet(
            f"QDialog {{ background:{BG_CARD}; }}"
            f"QLabel {{ color:{TEXT_PRIMARY}; background:transparent; }}"
            f"QLineEdit, QTextEdit {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:4px; padding:4px; }}"
            f"QLineEdit:focus, QTextEdit:focus {{ border-color:{ACCENT}; }}"
            f"QComboBox {{ background:{BG_DARK}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:4px; padding:3px 6px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)

        hdr = QLabel("Segment" if not segment else segment.name)
        hdr.setStyleSheet(f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};")
        lay.addWidget(hdr)

        form = QFormLayout()
        form.setSpacing(8)
        form.setHorizontalSpacing(12)

        def _lbl(t: str) -> QLabel:
            lb = QLabel(t)
            lb.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED};")
            return lb

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. IoT VLAN")
        if segment:
            self._name_edit.setText(segment.name)

        self._cidr_edit = QLineEdit()
        self._cidr_edit.setPlaceholderText("e.g. 192.168.1.0/24")
        if segment:
            self._cidr_edit.setText(segment.cidr)
            self._cidr_edit.setReadOnly(True)
            self._cidr_edit.setStyleSheet(
                f"QLineEdit {{ background:{BG_DARK}; color:{TEXT_MUTED};"
                f" border:1px solid {BORDER}; border-radius:4px; padding:4px; }}"
            )

        self._color_combo = QComboBox()
        _color_names = [
            "Blue", "Green", "Red", "Amber",
            "Purple", "Teal", "Orange", "Indigo",
        ]
        for i, (hex_c, name) in enumerate(zip(self._palette, _color_names)):
            self._color_combo.addItem(f"● {name}", hex_c)
            self._color_combo.setItemData(
                i, QColor(hex_c),
                Qt.ItemDataRole.ForegroundRole,
            )
        if segment:
            idx = self._palette.index(segment.color) if segment.color in self._palette else 0
            self._color_combo.setCurrentIndex(idx)

        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText("Optional description…")
        self._desc_edit.setFixedHeight(64)
        if segment:
            self._desc_edit.setPlainText(segment.description)

        form.addRow(_lbl("Name"),        self._name_edit)
        _cidr_lbl = _lbl("CIDR")
        _cidr_lbl.setToolTip(
            "CIDR — shorthand for a block of IP addresses. "
            "192.168.1.0/24 covers all 256 addresses from .0 to .255."
        )
        form.addRow(_cidr_lbl,           self._cidr_edit)
        form.addRow(_lbl("Colour"),      self._color_combo)
        form.addRow(_lbl("Description"), self._desc_edit)
        lay.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        btns.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f" border-radius:4px; padding:4px 14px; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def result_segment(self) -> dict:
        """Return a dict with the edited values; call after exec() == Accepted."""
        return {
            "name": self._name_edit.text().strip() or "Unnamed Segment",
            "cidr": self._cidr_edit.text().strip(),
            "color": self._color_combo.currentData() or self._palette[0],
            "description": self._desc_edit.toPlainText().strip(),
        }
