"""
device_detail_pane.py — Helper dialog and drawer classes for InventoryPage.

Extracted from ui/pages/inventory_page.py (Sprint 13) to keep that file within budget.
inventory_page.py imports all classes back from here.
"""
from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidgetItem, QTextEdit, QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BG_HOVER, BORDER, GREEN, RED, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    WHITE,
)

if TYPE_CHECKING:
    from modules.metric_store import MetricStore

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
            l = QLabel(t)
            l.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED};")
            return l

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
            f"QPushButton:hover {{ background:{ACCENT}dd; }}"
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
        self._store.update_device_ha_info(
            self._mac, custom_name=name, tags=tags, notes=notes
        )
        self.accept()


# ── Device history drawer (DEVICE-2) ─────────────────────────────────────────

class _DeviceDrawer(QFrame):
    """Slide-in panel showing per-device history — last seen, event count, metadata."""

    closed = pyqtSignal()

    _DRAWER_WIDTH = 300

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("deviceDrawer")
        self.setStyleSheet(
            f"QFrame#deviceDrawer {{ background:{BG_CARD}; border-left:1px solid {BORDER}; }}"
            f"QLabel {{ background:transparent; border:none; color:{TEXT_PRIMARY}; }}"
        )
        self.setFixedWidth(self._DRAWER_WIDTH)
        self.setVisible(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        hdr_row = QHBoxLayout()
        self._title_lbl = QLabel("Device")
        self._title_lbl.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
        )
        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:none;"
            f" font-size:15px; }}"
            f"QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        close_btn.clicked.connect(self.close_drawer)
        hdr_row.addWidget(self._title_lbl, 1)
        hdr_row.addWidget(close_btn)
        lay.addLayout(hdr_row)

        self._mac_lbl    = QLabel("")
        self._mac_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        lay.addWidget(self._mac_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color:{BORDER}; background:{BORDER}; max-height:1px;")
        lay.addWidget(sep)

        def _row(label: str, value_lbl: QLabel) -> None:
            r = QHBoxLayout()
            l = QLabel(label)
            l.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED}; min-width:90px;")
            value_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_PRIMARY};")
            r.addWidget(l)
            r.addWidget(value_lbl, 1)
            lay.addLayout(r)

        self._first_seen_val = QLabel("—")
        self._last_seen_val  = QLabel("—")
        self._event_count_val = QLabel("—")
        self._vendor_val     = QLabel("—")
        self._custom_val     = QLabel("—")
        self._tags_val       = QLabel("—")
        self._notes_val      = QLabel("—")
        self._notes_val.setWordWrap(True)

        _row("First seen",   self._first_seen_val)
        _row("Last seen",    self._last_seen_val)
        _row("Events",       self._event_count_val)
        _row("Vendor",       self._vendor_val)
        _row("Custom name",  self._custom_val)
        _row("Tags",         self._tags_val)
        _row("Notes",        self._notes_val)
        lay.addStretch()

        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def load(self, mac: str, store: "Optional[MetricStore]") -> None:
        self._title_lbl.setText("Device")
        self._mac_lbl.setText(mac)
        if store is None:
            return
        devices = store.get_known_devices()
        kd = devices.get(mac.lower()) or devices.get(mac)
        if kd:
            self._first_seen_val.setText(
                datetime.datetime.fromtimestamp(kd.first_seen).strftime("%Y-%m-%d %H:%M")
                if kd.first_seen else "—"
            )
            self._last_seen_val.setText(
                datetime.datetime.fromtimestamp(kd.last_seen).strftime("%Y-%m-%d %H:%M")
                if kd.last_seen else "—"
            )
            self._vendor_val.setText(kd.vendor or "—")
            self._custom_val.setText(kd.custom_name or "—")
            self._tags_val.setText(kd.tags or "—")
            self._notes_val.setText(kd.notes or "—")
            if kd.custom_name:
                self._title_lbl.setText(kd.custom_name)
        try:
            events = store.query_device_events(hours=720, event_types=None)
            count = sum(1 for e in events if (e.mac or "").lower() == mac.lower())
            self._event_count_val.setText(str(count) if count else "0")
        except Exception:
            self._event_count_val.setText("—")

    def open_drawer(self) -> None:
        parent = self.parent()
        if parent is None:
            return
        ph = parent.height()
        pw = parent.width()
        w  = self._DRAWER_WIDTH
        self.setGeometry(pw, 0, w, ph)
        self.setVisible(True)
        self.raise_()
        self._anim.setStartValue(QRect(pw, 0, w, ph))
        self._anim.setEndValue(QRect(pw - w, 0, w, ph))
        self._anim.start()

    def close_drawer(self) -> None:
        parent = self.parent()
        if parent is None:
            self.setVisible(False)
            self.closed.emit()
            return
        pw = parent.width()
        w  = self._DRAWER_WIDTH
        ph = parent.height()
        self._anim.setStartValue(QRect(pw - w, 0, w, ph))
        self._anim.setEndValue(QRect(pw, 0, w, ph))
        self._anim.finished.connect(self._on_close_done)
        self._anim.start()

    def _on_close_done(self) -> None:
        self._anim.finished.disconnect(self._on_close_done)
        self.setVisible(False)
        self.closed.emit()


# ── Event type display config ─────────────────────────────────────────────────

_EVENT_STYLE: dict[str, tuple[str, str]] = {
    # event_type: (badge_color, label)
    "JOINED":    (GREEN,  "JOINED"),
    "LEFT":      (AMBER,  "LEFT"),
    "DOWN":      (RED,    "DOWN"),
    "UP":        (GREEN,  "UP"),
    "DEGRADED":  (AMBER,  "DEGRADED"),
    "RECOVERED": (GREEN,  "RECOVERED"),
}

_ALL_TYPES = list(_EVENT_STYLE.keys())

_WINDOWS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}


# ── Helper: coloured badge cell ───────────────────────────────────────────────

def _badge_item(text: str, color: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(color))
    item.setFont(
        __import__("PyQt6.QtGui", fromlist=["QFont"]).QFont("Segoe UI", 9, 75)  # Bold
    )
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


def _plain_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


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

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet(f"font-size:11px; color:{TEXT_MUTED};")
            return l

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
            f"QPushButton:hover {{ background:{ACCENT}dd; }}"
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
