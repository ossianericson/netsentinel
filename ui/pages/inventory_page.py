"""
InventoryPage — network inventory change history page (T2#8).

Shows a live event log of every JOINED / LEFT / DOWN / UP / DEGRADED / RECOVERED
event recorded by MetricStore, with filtering by event type and time window.

Architecture rules observed:
  • Imports PyQt6 and ui/styles — UI page only.
  • MetricStore injected as constructor parameter — never constructed here.
  • All colours from ui/styles — no hardcoded hex values.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

import time as _time

from PyQt6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer, pyqtSignal, pyqtSlot,
)
from PyQt6.QtGui import QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ui.expanding_table import ExpandingTable
from ui.tabs_helpers import risk_to_label
from ui.widgets.column_visibility_toggle import ColumnVisibilityToggle
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard
from ui.widgets.skeleton import clear_skeleton_rows, insert_skeleton_rows

from ui.styles import (
    alpha,
)

if TYPE_CHECKING:
    from modules.metric_store import MetricStore

from modules.device_admin import (
    clear_classification_override, set_device_alert_opt_in,
)
from modules.network_segments import upsert_segment

from ui.widgets.inventory_dialogs import (
    _DeviceLabelDialog, _TypeOverrideDialog, _ScanCompareDialog, _SegmentEditorDialog,
)
from ui.widgets.device_detail_pane import _wire_close_icon
from ui import styles as _s
from ui.dialog_utils import run_dialog

# ── Device history drawer (DEVICE-2) ─────────────────────────────────────────

class _DeviceDrawer(QFrame):
    """Slide-in panel showing per-device history, annotations, and IP history."""

    closed = pyqtSignal()

    _DRAWER_WIDTH = 340

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("deviceDrawer")
        _s.themed_ss(self, "QFrame#deviceDrawer {{ background:{BG_CARD}; border-left:1px solid {BORDER}; }}"
            "QLabel {{ background:transparent; border:none; color:{TEXT_PRIMARY}; }}")
        self.setFixedWidth(self._DRAWER_WIDTH)
        self.setVisible(False)

        self._current_mac: str = ""
        self._current_store: "Optional[MetricStore]" = None

        # ── Outer layout: fixed header + scrollable body ───────────────────────
        outer_lay = QVBoxLayout(self)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        hdr_frame = QFrame()
        _s.themed_ss(hdr_frame, "QFrame {{ background:{BG_CARD}; border-bottom:1px solid {BORDER}; }}")
        hdr_row = QHBoxLayout(hdr_frame)
        hdr_row.setContentsMargins(14, 10, 10, 10)
        self._title_lbl = QLabel("Device")
        _s.themed_ss(self._title_lbl, "font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};")
        close_btn = QPushButton()
        close_btn.setFixedSize(22, 22)
        close_btn.setToolTip(_s.safe_tooltip("Close"))
        _wire_close_icon(close_btn)
        _s.themed_ss(close_btn, "QPushButton {{ background:transparent; border:none; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; }}")
        close_btn.clicked.connect(self.close_drawer)
        hdr_row.addWidget(self._title_lbl, 1)
        hdr_row.addWidget(close_btn)
        outer_lay.addWidget(hdr_frame)

        # ── Scrollable body ────────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background:transparent; border:none; }"
            "QScrollBar:vertical { width:6px; }"
        )
        outer_lay.addWidget(scroll, 1)

        body = QWidget()
        body.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)
        scroll.setWidget(body)

        self._mac_lbl = QLabel("")
        _s.themed_ss(self._mac_lbl, "font-size:10px; color:{TEXT_MUTED};")
        lay.addWidget(self._mac_lbl)

        def _sep() -> None:
            s = QFrame()
            s.setFrameShape(QFrame.Shape.HLine)
            _s.themed_ss(s, "color:{BORDER}; background:{BORDER}; max-height:1px;")
            lay.addWidget(s)

        def _info_row(label: str, val_lbl: QLabel) -> None:
            r = QHBoxLayout()
            l = QLabel(label)
            _s.themed_ss(l, "font-size:10px; color:{TEXT_MUTED}; min-width:90px;")
            _s.themed_ss(val_lbl, "font-size:10px; color:{TEXT_PRIMARY};")
            r.addWidget(l)
            r.addWidget(val_lbl, 1)
            lay.addLayout(r)

        def _section_hdr(title: str) -> None:
            h = QLabel(title)
            _s.themed_ss(h, "font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
                " text-transform:uppercase; letter-spacing:1px;"
                " padding-top:4px;")
            lay.addWidget(h)

        # ── Classification section (Sprint 6) ─────────────────────────────────
        self._class_frame = QFrame()
        self._class_frame.setVisible(False)
        _cf_lay = QVBoxLayout(self._class_frame)
        _cf_lay.setContentsMargins(0, 4, 0, 4)
        _cf_lay.setSpacing(3)

        _ch = QLabel("CLASSIFICATION")
        _s.themed_ss(_ch, "font-size:10px; font-weight:bold; color:{TEXT_SECONDARY};"
            " text-transform:uppercase; letter-spacing:1px;")
        _cf_lay.addWidget(_ch)

        _ct_row = QHBoxLayout()
        self._class_type_val = QLabel("—")
        _s.themed_ss(self._class_type_val, "font-size:10px; font-weight:bold; color:{TEXT_PRIMARY};")
        self._class_override_badge = QLabel("★ Override")
        self._class_override_badge.setVisible(False)
        _s.themed_ss(self._class_override_badge, "font-size:9px; color:{ACCENT}; padding:1px 4px;"
            " border:1px solid {ACCENT}; border-radius:2px;")
        _ct_row.addWidget(self._class_type_val)
        _ct_row.addWidget(self._class_override_badge)
        _ct_row.addStretch()
        _cf_lay.addLayout(_ct_row)

        self._class_conf_val = QLabel("Confidence: —")
        _s.themed_ss(self._class_conf_val, "font-size:10px; color:{TEXT_MUTED};")
        _cf_lay.addWidget(self._class_conf_val)

        self._class_evidence_val = QLabel("")
        _s.themed_ss(self._class_evidence_val, "font-size:10px; color:{TEXT_MUTED};")
        self._class_evidence_val.setWordWrap(True)
        _cf_lay.addWidget(self._class_evidence_val)

        self._class_clear_btn = QPushButton("Clear Override")
        self._class_clear_btn.setFixedHeight(24)
        self._class_clear_btn.setVisible(False)
        _s.themed_ss(self._class_clear_btn, "QPushButton {{ background:{BG_CARD}; color:{RED}; border:1px solid {RED};"
            " border-radius:3px; font-size:10px; padding:0 8px; }}"
            "QPushButton:hover {{ background:{RED}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{RED}; color:{WHITE}; }}")
        self._class_clear_btn.clicked.connect(self._clear_type_override)
        _cf_lay.addWidget(self._class_clear_btn)

        lay.addWidget(self._class_frame)

        self._class_sep = QFrame()
        self._class_sep.setFrameShape(QFrame.Shape.HLine)
        _s.themed_ss(self._class_sep, "color:{BORDER}; background:{BORDER}; max-height:1px;")
        self._class_sep.setVisible(False)
        lay.addWidget(self._class_sep)

        # ── Device info section ────────────────────────────────────────────────
        self._first_seen_val  = QLabel("—")
        self._last_seen_val   = QLabel("—")
        self._event_count_val = QLabel("—")
        self._vendor_val      = QLabel("—")
        self._custom_val      = QLabel("—")
        self._tags_val        = QLabel("—")
        self._notes_val       = QLabel("—")
        self._notes_val.setWordWrap(True)
        self._services_val    = QLabel("—")
        self._services_val.setWordWrap(True)

        _info_row("First seen",  self._first_seen_val)
        _info_row("Last seen",   self._last_seen_val)
        _info_row("Events",      self._event_count_val)
        _info_row("Vendor",      self._vendor_val)
        _info_row("Custom name", self._custom_val)
        _info_row("Tags",        self._tags_val)
        _info_row("Notes",       self._notes_val)
        _info_row("Services",    self._services_val)

        # ── Notes & Labels section ─────────────────────────────────────────────
        _sep()
        _section_hdr("Notes & Labels")

        _field_ss = (
            f"QLineEdit, QPlainTextEdit {{"
            f" background:{_s.BG_DARK}; color:{_s.TEXT_PRIMARY};"
            f" border:1px solid {_s.BORDER}; border-radius:3px; padding:3px; font-size:10px; }}"
            f"QLineEdit:focus, QPlainTextEdit:focus {{ border-color:{_s.ACCENT}; }}"
        )
        form_frame = QFrame()
        form_frame.setStyleSheet(_field_ss)
        form_lay = QFormLayout(form_frame)
        form_lay.setContentsMargins(0, 4, 0, 4)
        form_lay.setSpacing(5)
        form_lay.setHorizontalSpacing(8)

        def _flbl(t: str) -> QLabel:
            lb = QLabel(t)
            _s.themed_ss(lb, "font-size:10px; color:{TEXT_MUTED};")
            return lb

        self._ann_label    = QLineEdit()
        self._ann_label.setPlaceholderText("e.g. Living Room TV")
        self._ann_location = QLineEdit()
        self._ann_location.setPlaceholderText("e.g. Rack 3 / Bedroom")
        self._ann_owner    = QLineEdit()
        self._ann_owner.setPlaceholderText("e.g. IT Dept / Alice")
        self._ann_tag      = QLineEdit()
        self._ann_tag.setPlaceholderText("e.g. INV-2024-042")
        self._ann_notes    = QPlainTextEdit()
        self._ann_notes.setPlaceholderText("Free text notes…")
        self._ann_notes.setFixedHeight(60)

        form_lay.addRow(_flbl("User Label"), self._ann_label)
        form_lay.addRow(_flbl("Location"),   self._ann_location)
        form_lay.addRow(_flbl("Owner"),      self._ann_owner)
        form_lay.addRow(_flbl("Asset Tag"),  self._ann_tag)
        form_lay.addRow(_flbl("Notes"),      self._ann_notes)
        lay.addWidget(form_frame)

        save_btn = QPushButton("Save Changes")
        save_btn.setFixedHeight(26)
        _s.themed_ss(save_btn, "QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            " border-radius:3px; font-size:10px; padding:0 12px; }}"
            "QPushButton:hover {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            "QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}")
        save_btn.clicked.connect(self._save_annotations)
        lay.addWidget(save_btn)

        _sc = QShortcut(QKeySequence("Ctrl+S"), self)
        _sc.activated.connect(self._save_annotations)

        # ── IP History section ─────────────────────────────────────────────────
        _sep()
        _section_hdr("IP History")
        self._ip_history_body = QVBoxLayout()
        self._ip_history_body.setSpacing(2)
        lay.addLayout(self._ip_history_body)

        # ── Timeline section (S5-6) ───────────────────────────────────────────
        _sep()
        _section_hdr("Timeline")
        self._timeline_body = QVBoxLayout()
        self._timeline_body.setSpacing(2)
        lay.addLayout(self._timeline_body)

        lay.addStretch()

        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def load(self, mac: str, store: "Optional[MetricStore]", suggested_label: str = "") -> None:
        self._current_mac   = mac
        self._current_store = store
        self._title_lbl.setText("Device")
        self._mac_lbl.setText(mac)
        if store is None:
            return
        devices = store.get_known_devices()
        kd = devices.get(mac.lower()) or devices.get(mac)

        # ── Classification section ─────────────────────────────────────────────
        _override: Optional[str] = None
        try:
            _override = store.get_classification_override(mac)
        except Exception:
            pass  # non-fatal — table may not exist on first run
        if kd:
            self._class_frame.setVisible(True)
            self._class_sep.setVisible(True)
            _cur_type = _override or kd.device_type or "Unknown Device"
            self._class_type_val.setText(_cur_type)
            if _override:
                self._class_override_badge.setVisible(True)
                self._class_conf_val.setText("Permanently overridden by user")
                self._class_clear_btn.setVisible(True)
            else:
                self._class_override_badge.setVisible(False)
                _conf = float(kd.confidence or 0.0)
                if _conf >= 0.7:
                    _label = f"{_conf:.0%} (high)"
                elif _conf >= 0.3:
                    _label = f"{_conf:.0%} (medium)"
                elif _conf > 0.0:
                    _label = f"{_conf:.0%} (low)"
                else:
                    _label = "unknown"
                self._class_conf_val.setText(f"Confidence: {_label}")
                self._class_clear_btn.setVisible(False)
            try:
                from modules.device_classifier import classify_with_evidence as _cwe
                _cr = _cwe(
                    vendor=kd.vendor or "",
                    hostname=kd.hostname or "",
                    open_ports=set(),
                    os_family="",
                    mac=mac,
                    is_gateway=False,
                )
                if _cr.evidence:
                    self._class_evidence_val.setText(
                        "Evidence: " + ", ".join(_cr.evidence[:4])
                    )
                else:
                    self._class_evidence_val.setText("Evidence: OUI lookup only")
            except Exception:
                self._class_evidence_val.setText("")  # non-fatal

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
                import json as _json
                names = _json.loads(kd.services) if kd.services else []
                self._services_val.setText(", ".join(names) if names else "—")
            except Exception:
                self._services_val.setText("—")  # non-fatal — services field may be absent
        try:
            events = store.query_device_events(hours=720, event_types=None)
            count = sum(1 for e in events if (e.mac or "").lower() == mac.lower())
            self._event_count_val.setText(str(count) if count else "0")
        except Exception:
            self._event_count_val.setText("—")  # non-fatal — event history unavailable

        # ── Annotations ───────────────────────────────────────────────────────
        try:
            from modules.device_tracker import get_annotations as _get_ann
            ann = _get_ann(mac, store)
            existing_label = ann.get("user_label", "")
            self._ann_label.setText(existing_label or suggested_label)
            self._ann_location.setText(ann.get("location", ""))
            self._ann_owner.setText(ann.get("owner", ""))
            self._ann_tag.setText(ann.get("asset_tag", ""))
            self._ann_notes.setPlainText(ann.get("notes", ""))
        except Exception:
            pass  # non-fatal — annotation table may not exist on first run

        # ── IP History ────────────────────────────────────────────────────────
        self._rebuild_ip_history(mac, store)

        # ── Timeline (S5-6) ───────────────────────────────────────────────────
        self._rebuild_timeline(mac, store)

    def _clear_type_override(self) -> None:
        if not self._current_store or not self._current_mac:
            return
        try:
            clear_classification_override(self._current_store, self._current_mac)
        except Exception:
            pass  # non-fatal
        self.load(self._current_mac, self._current_store)

    def _rebuild_ip_history(self, mac: str, store: "Optional[MetricStore]") -> None:
        """Clear and repopulate the IP history rows."""
        while self._ip_history_body.count():
            item = self._ip_history_body.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        if store is None:
            return
        try:
            from modules.device_tracker import get_ip_history as _get_hist
            hist = _get_hist(mac, store)
        except Exception:
            hist = []  # non-fatal — table may not exist on first run
        if not hist:
            empty = QLabel("No IP history recorded yet")
            _s.themed_ss(empty, "font-size:10px; color:{TEXT_MUTED}; padding:2px 0;")
            self._ip_history_body.addWidget(empty)
            return
        for entry in hist:
            row_lbl = QLabel(
                f"{entry['ip']}  ·  {_fmt_ago(entry['last_seen'])}  "
                f"({entry['seen_count']}×)"
            )
            _s.themed_ss(row_lbl, "font-size:10px; color:{TEXT_PRIMARY};")
            self._ip_history_body.addWidget(row_lbl)

    def _rebuild_timeline(self, mac: str, store: "Optional[MetricStore]") -> None:
        """Clear and repopulate the combined device timeline (S5-6).

        Merges device_event state changes (JOINED/LEFT/UP/DOWN/...) with the
        device_events annotation-change audit log into one chronological list.
        """
        while self._timeline_body.count():
            item = self._timeline_body.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        if store is None:
            return

        entries: list = []  # (epoch, display text)

        try:
            for e in store.query_device_events(hours=720, event_types=None):
                if (e.mac or "").lower() != mac.lower():
                    continue
                ts_str = datetime.datetime.fromtimestamp(e.ts).strftime("%Y-%m-%d %H:%M")
                entries.append((float(e.ts), f"{ts_str}  ·  {e.event_type}"))
        except Exception:
            pass  # non-fatal — event history unavailable

        try:
            import calendar as _cal
            from modules.device_tracker import get_device_events as _get_events
            for ev in _get_events(mac, store, limit=20):
                try:
                    dt = datetime.datetime.strptime(ev["ts"], "%Y-%m-%d %H:%M:%S")
                    epoch = float(_cal.timegm(dt.timetuple()))
                except (ValueError, TypeError):
                    epoch = 0.0
                label = ev["event_type"].replace("_", " ").title()
                change = (
                    f"{ev['old_value']} → {ev['new_value']}"
                    if ev["old_value"] or ev["new_value"] else ""
                )
                text = f"{ev['ts'][:16]}  ·  {label}"
                if change:
                    text += f"  ({change})"
                entries.append((epoch, text))
        except Exception:
            pass  # non-fatal — audit table may not exist on schema upgrade

        if not entries:
            empty = QLabel("No timeline events recorded yet")
            _s.themed_ss(empty, "font-size:10px; color:{TEXT_MUTED}; padding:2px 0;")
            self._timeline_body.addWidget(empty)
            return

        entries.sort(key=lambda t: t[0], reverse=True)
        for _, text in entries[:15]:
            row_lbl = QLabel(text)
            row_lbl.setWordWrap(True)
            _s.themed_ss(row_lbl, "font-size:10px; color:{TEXT_PRIMARY};")
            self._timeline_body.addWidget(row_lbl)

    def _save_annotations(self) -> None:
        if not self._current_mac or not self._current_store:
            return
        try:
            from modules.device_tracker import save_annotations as _save_ann
            _save_ann(
                self._current_mac,
                self._current_store,
                user_label=self._ann_label.text().strip(),
                location=self._ann_location.text().strip(),
                owner=self._ann_owner.text().strip(),
                asset_tag=self._ann_tag.text().strip(),
                notes=self._ann_notes.toPlainText().strip(),
            )
        except Exception:
            pass  # non-fatal — save failure should not crash the drawer

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


def _fmt_ago(ts_str: str) -> str:
    """Convert a UTC datetime string to a human-readable 'X ago' label."""
    try:
        dt = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        secs = int((datetime.datetime.utcnow() - dt).total_seconds())
        if secs < 60:
            return "just now"
        if secs < 3600:
            return f"{secs // 60} min ago"
        if secs < 86400:
            return f"{secs // 3600}h ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return ts_str


# ── Event type display config ─────────────────────────────────────────────────

_EVENT_STYLE: dict[str, tuple[str, str]] = {
    # event_type: (badge_color_token, label) — colour resolved live via _s at use
    "JOINED":    ("GREEN",  "JOINED"),
    "LEFT":      ("AMBER",  "LEFT"),
    "DOWN":      ("RED",    "DOWN"),
    "UP":        ("GREEN",  "UP"),
    "DEGRADED":  ("AMBER",  "DEGRADED"),
    "RECOVERED": ("GREEN",  "RECOVERED"),
}

_ALL_TYPES = list(_EVENT_STYLE.keys())

_WINDOWS = {"1h": 1, "6h": 6, "24h": 24, "7d": 168, "30d": 720}


# ── Helper: coloured badge cell ───────────────────────────────────────────────

def _badge_item(text: str, color: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(getattr(_s, color)))
    item.setFont(
        __import__("PyQt6.QtGui", fromlist=["QFont"]).QFont("Segoe UI", 9, 75)  # Bold
    )
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item


def _plain_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    return item



# ── Main page ────────────────────────────────────────────────────────────────

class InventoryPage(QWidget):
    """
    Full-page inventory change event log.

    Parameters
    ----------
    store : MetricStore | None
        Injected from app.py. Shows a placeholder if None.
    """

    scan_requested          = pyqtSignal()
    device_selected         = pyqtSignal(str)   # emits MAC when a row is double-clicked
    show_connections_for    = pyqtSignal(str)   # IP → navigate to Connections + filter
    check_cves_for          = pyqtSignal(str)   # IP → navigate to CVE Tracker + filter
    show_on_map             = pyqtSignal(str)   # IP → navigate to Geo Map
    navigate_to             = pyqtSignal(str)   # generic page-label navigation (S9-3)

    REFRESH_MS = 15_000   # refresh every 15 s

    def __init__(self, store: "Optional[MetricStore]" = None, parent=None):
        super().__init__(parent)
        self._store    = store
        self._window_h = 24
        self._active_types: set[str] = set(_ALL_TYPES)
        self._active_tags: set[str] = set()
        self._rows: list = []
        self._last_refresh_ts = 0.0
        self._compare_mode = False
        self._scan_devices: list = []  # last scan result, set via set_scan_devices()
        self._current_segments: list = []   # NetworkSegment list from last scan
        self._active_seg_ids: Optional[set] = None  # None = show all
        self._seg_pills: dict = {}           # {segment_id_or_cidr: QPushButton}
        self._hide_offline: bool = False     # when True, hide cached/stale rows
        self._group_dim: str = "location"    # "location" (Room) or "owner" (S5-2)
        self._active_group_keys: Optional[set] = None  # None = show all
        self._group_pills: dict = {}         # {group_key: QPushButton}
        self._current_annotations: dict = {}  # {mac: {user_label, location, owner, ...}}
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(self.REFRESH_MS)
        self._auto_timer.timeout.connect(self._refresh)

        self._build_ui()

        if store:
            self._refresh()
            self._auto_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        from ui.table_utils import restore_column_widths
        restore_column_widths(self._table, "devices")
        if self._table.rowCount() == 0:
            insert_skeleton_rows(self._table, count=6)
        self._refresh()

    def _maybe_show_coach_devices(self) -> None:
        if not self.isVisible():
            return
        from PyQt6.QtCore import QSettings
        qs = QSettings("NetSentinel", "NetSentinel")
        if not qs.value("tour/v1_done", False, type=bool):
            return
        key = "coach/devices_rightclick_shown"
        if qs.value(key, False, type=bool):
            return
        if self._table.rowCount() == 0:
            return
        win = self.window()
        if not (win and win.isVisible()):
            return
        from ui.widgets.coach_mark import CoachMarkChain
        CoachMarkChain(
            win,
            [{
                "target": lambda t=self._table: t,
                "title": "Right-click for actions",
                "body": (
                    "Right-click any device row to label it, check its ports, "
                    "or add it to your watchlist."
                ),
            }],
            on_done=lambda: QSettings("NetSentinel", "NetSentinel").setValue(key, True),
        ).start()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # Title — always visible
        t = QLabel("Inventory Change History")
        _s.themed_ss(t, "font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};")
        s = QLabel("Device join, leave, and state-change events — recorded by the background monitor")
        _s.themed_ss(s, "font-size:11px; color:{TEXT_SECONDARY};")
        root.addWidget(t)
        root.addWidget(s)

        self._content_stack = QStackedWidget()

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = EmptyStateCard(
            icon="◆",
            title="No devices found yet",
            what_it_shows=(
                "Every device currently connected to your network — phones, laptops, smart TVs, "
                "routers — with their IP address, MAC address, and manufacturer. "
                "Run a scan to discover what's connected — takes about 30 seconds."
            ),
            why_it_matters="You can't secure a device you don't know exists.",
            btn_label="Run Scan",
        )
        empty.clicked.connect(self.scan_requested)
        self._content_stack.addWidget(empty)

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        # ── Segment filter bar (hidden until scan data arrives) ───────────────
        self._seg_bar_frame = QFrame()
        self._seg_bar_frame.setVisible(False)
        _s.themed_ss(self._seg_bar_frame, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; padding:4px 8px; }}")
        seg_bar_outer = QHBoxLayout(self._seg_bar_frame)
        seg_bar_outer.setContentsMargins(8, 4, 8, 4)
        seg_bar_outer.setSpacing(0)
        _seg_lbl = QLabel("Segment:")
        _s.themed_ss(_seg_lbl, "font-size:11px; font-weight:bold; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; padding-right:6px;")
        seg_bar_outer.addWidget(_seg_lbl)
        self._seg_scroll = QScrollArea()
        self._seg_scroll.setWidgetResizable(True)
        self._seg_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._seg_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._seg_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._seg_scroll.setFixedHeight(36)
        self._seg_scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        _seg_inner = QWidget()
        _seg_inner.setStyleSheet("background:transparent;")
        self._seg_pill_row = QHBoxLayout(_seg_inner)
        self._seg_pill_row.setContentsMargins(0, 2, 0, 2)
        self._seg_pill_row.setSpacing(6)
        self._seg_pill_row.addStretch()
        self._seg_scroll.setWidget(_seg_inner)
        seg_bar_outer.addWidget(self._seg_scroll, 1)
        cl.addWidget(self._seg_bar_frame)

        # ── Room/Owner group filter bar (S5-2, hidden until annotations exist) ─
        self._group_bar_frame = QFrame()
        self._group_bar_frame.setVisible(False)
        _s.themed_ss(self._group_bar_frame, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; padding:4px 8px; }}")
        group_bar_outer = QHBoxLayout(self._group_bar_frame)
        group_bar_outer.setContentsMargins(8, 4, 8, 4)
        group_bar_outer.setSpacing(6)
        _group_lbl = QLabel("Group:")
        _s.themed_ss(_group_lbl, "font-size:11px; font-weight:bold; color:{TEXT_SECONDARY};"
            " background:transparent; border:none; padding-right:6px;")
        group_bar_outer.addWidget(_group_lbl)
        self._group_dim_combo = QComboBox()
        self._group_dim_combo.addItem("Room", "location")
        self._group_dim_combo.addItem("Owner", "owner")
        self._group_dim_combo.setFixedHeight(24)
        _s.themed_ss(self._group_dim_combo, "QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            " border:1px solid {BORDER}; border-radius:3px; padding:0 6px;"
            " font-size:11px; }}")
        self._group_dim_combo.currentIndexChanged.connect(self._on_group_dim_changed)
        group_bar_outer.addWidget(self._group_dim_combo)
        self._group_scroll = QScrollArea()
        self._group_scroll.setWidgetResizable(True)
        self._group_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._group_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._group_scroll.setFixedHeight(36)
        self._group_scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        _group_inner = QWidget()
        _group_inner.setStyleSheet("background:transparent;")
        self._group_pill_row = QHBoxLayout(_group_inner)
        self._group_pill_row.setContentsMargins(0, 2, 0, 2)
        self._group_pill_row.setSpacing(6)
        self._group_pill_row.addStretch()
        self._group_scroll.setWidget(_group_inner)
        group_bar_outer.addWidget(self._group_scroll, 1)
        cl.addWidget(self._group_bar_frame)

        # ── Current Devices snapshot card ──────────────────────────────────────
        snap_card = QFrame()
        snap_card.setObjectName("snapCard")
        _s.themed_ss(snap_card, "QFrame#snapCard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            " border-radius:{CARD_RADIUS}; }}")
        snap_card_lay = QVBoxLayout(snap_card)
        snap_card_lay.setContentsMargins(0, 0, 0, 0)
        snap_card_lay.setSpacing(0)

        snap_hdr = QFrame()
        _s.themed_ss(snap_hdr, "QFrame {{ background:{TH_BG}; border-radius:{CARD_RADIUS} {CARD_RADIUS} 0 0; }}")
        snap_hdr_lay = QHBoxLayout(snap_hdr)
        snap_hdr_lay.setContentsMargins(10, 5, 10, 5)
        snap_hdr_lay.setSpacing(8)
        snap_title = QLabel("Current Devices")
        _s.themed_ss(snap_title, "font-size:11px; font-weight:bold; color:{TH_TEXT}; background:transparent; border:none;")
        self._snap_count_lbl = QLabel("Run a scan to see all devices")
        _s.themed_ss(self._snap_count_lbl, "font-size:10px; color:{TH_TEXT}; background:transparent; border:none; opacity:0.7;")
        self._hide_offline_btn = QPushButton("Hide offline")
        self._hide_offline_btn.setCheckable(True)
        self._hide_offline_btn.setFixedHeight(20)
        self._hide_offline_btn.setToolTip(_s.safe_tooltip(
            "Hide cached/stale devices — devices not seen in this scan"
        ))
        self._hide_offline_btn.setStyleSheet(
            f"QPushButton {{ font-size:10px; color:{_s.TH_TEXT}; background:transparent;"
            f" border:1px solid {alpha(_s.TH_TEXT, 0x44)}; border-radius:3px; padding:0 7px; }}"
            f"QPushButton:hover {{ background:{alpha(_s.TH_TEXT, 0x22)}; }}"
            f"QPushButton:checked {{ background:{alpha(_s.TH_TEXT, 0x33)}; border-color:{_s.TH_TEXT}; }}"
            f"QPushButton:pressed {{ background:{alpha(_s.TH_TEXT, 0x22)}; color:{_s.TH_TEXT}; }}"
        )
        self._hide_offline_btn.toggled.connect(self._on_hide_offline_toggled)
        snap_hdr_lay.addWidget(snap_title)
        snap_hdr_lay.addStretch()
        snap_hdr_lay.addWidget(self._hide_offline_btn)
        snap_hdr_lay.addWidget(self._snap_count_lbl)
        snap_card_lay.addWidget(snap_hdr)

        # ── Health summary top-line (S5-3) ─────────────────────────────────────
        self._health_summary_lbl = QLabel("")
        self._health_summary_lbl.setVisible(False)
        _s.themed_ss(self._health_summary_lbl, "font-size:10px; color:{TEXT_SECONDARY}; background:{BG_ALT_ROW};"
            " border:none; border-bottom:1px solid {BORDER}; padding:4px 10px;")
        snap_card_lay.addWidget(self._health_summary_lbl)

        # ── Unknown-device alert prompt (S9-3, one-time, dismissible) ─────────
        self._unknown_device_prompt = QFrame()
        self._unknown_device_prompt.setVisible(False)
        _s.themed_ss(self._unknown_device_prompt, "QFrame {{ background:{BG_HOVER}; border:none;"
            " border-bottom:1px solid {BORDER}; }}")
        _udp_lay = QHBoxLayout(self._unknown_device_prompt)
        _udp_lay.setContentsMargins(10, 4, 8, 4)
        _udp_lay.setSpacing(8)
        self._unknown_device_lbl = QLabel("")
        self._unknown_device_lbl.setWordWrap(True)
        _s.themed_ss(self._unknown_device_lbl, "font-size:10px; color:{TEXT_PRIMARY}; background:transparent; border:none;")
        _udp_lay.addWidget(self._unknown_device_lbl, 1)
        _udp_btn = QPushButton("Set up alerts →")
        _udp_btn.setFlat(True)
        _udp_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(_udp_btn, "QPushButton {{ color:{ACCENT}; font-size:10px; background:transparent;"
            " border:none; padding:0; }}"
            "QPushButton:hover {{ color:{ACCENT_DARK}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        _udp_btn.clicked.connect(self._on_unknown_device_alert_clicked)
        _udp_lay.addWidget(_udp_btn)
        _udp_dismiss = QPushButton()
        _udp_dismiss.setFixedSize(18, 18)
        _udp_dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        _wire_close_icon(_udp_dismiss)
        _s.themed_ss(_udp_dismiss, "QPushButton {{ background:transparent; border:none; padding:0; }}"
            "QPushButton:hover {{ background:transparent; }}"
            "QPushButton:pressed {{ background:transparent; }}")
        _udp_dismiss.clicked.connect(self._dismiss_unknown_device_prompt)
        _udp_lay.addWidget(_udp_dismiss)
        snap_card_lay.addWidget(self._unknown_device_prompt)

        cols_snap = ["●", "Segment", "IP Address", "Label", "Hostname", "MAC Address", "Manufacturer", "Type", "Risk"]
        self._snap_table = QTableWidget(0, len(cols_snap))
        self._snap_table.setHorizontalHeaderLabels(cols_snap)
        self._snap_table.verticalHeader().setVisible(False)
        self._snap_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._snap_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._snap_table.setAlternatingRowColors(True)
        self._snap_table.verticalHeader().setDefaultSectionSize(24)
        self._snap_table.setShowGrid(False)
        self._snap_table.setSortingEnabled(True)
        _s.themed_ss(self._snap_table, """
            QTableWidget {{
                font-size:11px; color:{TEXT_PRIMARY};
                background:{BG_CARD}; border:none; outline:none;
                gridline-color:{BORDER};
            }}
            QTableWidget::item {{ padding:3px 5px; }}
            QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}
            QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}
            QHeaderView::section {{
                background:{TH_BG}; color:{TH_TEXT};
                font-size:11px; font-weight:bold;
                padding:4px 5px; border:none;
            }}
            """)
        _sh = self._snap_table.horizontalHeader()
        _sh.resizeSection(0, 22)   # ●
        _sh.resizeSection(1, 24)   # Segment colour dot
        _sh.resizeSection(2, 110)  # IP Address
        _sh.resizeSection(3, 110)  # Label
        _sh.resizeSection(4, 140)  # Hostname
        _sh.resizeSection(5, 140)  # MAC Address
        _sh.resizeSection(6, 140)  # Manufacturer
        _sh.resizeSection(7, 100)  # Type
        _sh.setStretchLastSection(True)

        # Quick / Full column-visibility toggle (S7-2) — defaults to Full;
        # technical data (IP, MAC, Manufacturer, Risk) is never hidden by default.
        self._column_toggle = ColumnVisibilityToggle(
            "inventory_snap", self._snap_table, quick_columns=[0, 3, 4, 7],
        )
        snap_hdr_lay.insertWidget(2, self._column_toggle)

        self._snap_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._snap_table.customContextMenuRequested.connect(
            self._snap_table_context_menu
        )
        self._snap_table.itemClicked.connect(self._on_snap_row_clicked)
        snap_card_lay.addWidget(self._snap_table)

        self._snap_empty_lbl = QLabel("Run a scan to see discovered devices here.")
        self._snap_empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _s.themed_ss(self._snap_empty_lbl, "color:{TEXT_MUTED}; font-size:12px; padding:24px; background:transparent; border:none;")
        snap_card_lay.addWidget(self._snap_empty_lbl)
        self._snap_table.setVisible(False)

        # Current Devices vs. change-history below share a user-resizable splitter
        # instead of a fixed max-height — Current Devices was previously capped at
        # 200px regardless of window size while the history table below took all
        # remaining space via a stretch factor.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(snap_card)

        bottom_pane = QWidget()
        bl = QVBoxLayout(bottom_pane)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(8)

        ctrl_row = QHBoxLayout()
        ctrl_row.addStretch()
        self._zoom_btns: dict[str, QPushButton] = {}
        for lbl in _WINDOWS:
            btn = QPushButton(lbl)
            btn.setFixedSize(40, 26)
            btn.setCheckable(True)
            btn.setStyleSheet(self._zoom_style(False))
            btn.clicked.connect(lambda _c, l=lbl: self._set_window(l))
            self._zoom_btns[lbl] = btn
            ctrl_row.addWidget(btn)
        rb = QPushButton("↻ Refresh")
        rb.setFixedHeight(26)
        _s.themed_ss(rb, "QPushButton {{ font-size:11px; color:{ACCENT}; background:{BG_CARD};"
            " border:1px solid {ACCENT}; border-radius:3px; padding:0 8px; }}"
            "QPushButton:hover {{ background:{BG_HOVER}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}")
        rb.clicked.connect(self._refresh)
        ctrl_row.addWidget(rb)
        btn_compare = QPushButton("⊞ Compare Scans")
        btn_compare.setFixedHeight(26)
        _s.themed_ss(btn_compare, "QPushButton {{ font-size:11px; color:{TEXT_SECONDARY}; background:{BG_CARD};"
            " border:1px solid {BORDER}; border-radius:3px; padding:0 8px; }}"
            "QPushButton:hover {{ color:{TEXT_PRIMARY}; border-color:{ACCENT}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}")
        btn_compare.clicked.connect(self._open_compare_dialog)
        ctrl_row.addWidget(btn_compare)
        bl.addLayout(ctrl_row)

        # ACT-3: compare mode banner (hidden when in live view)
        self._compare_banner = QFrame()
        self._compare_banner.setVisible(False)
        self._compare_banner.setStyleSheet(
            f"QFrame {{ background:{alpha(_s.ACCENT, 0x18)}; border:1px solid {alpha(_s.ACCENT, 0x44)};"
            f" border-radius:3px; }}"
        )
        _cb_lay = QHBoxLayout(self._compare_banner)
        _cb_lay.setContentsMargins(10, 5, 10, 5)
        _cb_lay.setSpacing(10)
        self._compare_banner_lbl = QLabel("")
        _s.themed_ss(self._compare_banner_lbl, "font-size:11px; font-weight:bold; color:{ACCENT}; background:transparent; border:none;")
        _cb_lay.addWidget(self._compare_banner_lbl, 1)
        _back_btn = QPushButton("← Back to live view")
        _back_btn.setFixedHeight(24)
        _back_btn.setStyleSheet(
            f"QPushButton {{ font-size:11px; color:{_s.ACCENT}; background:transparent;"
            f" border:1px solid {_s.ACCENT}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{alpha(_s.ACCENT, 0x22)}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.ACCENT}; }}"
        )
        _back_btn.clicked.connect(self._exit_compare_mode)
        _cb_lay.addWidget(_back_btn)
        _export_diff_btn = QPushButton("⬇ Export Diff as CSV")
        _export_diff_btn.setFixedHeight(24)
        _export_diff_btn.setStyleSheet(
            f"QPushButton {{ font-size:11px; color:{_s.ACCENT}; background:transparent;"
            f" border:1px solid {_s.ACCENT}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{alpha(_s.ACCENT, 0x22)}; }}"
            f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.ACCENT}; }}"
        )
        _export_diff_btn.clicked.connect(self._export_diff_csv)
        _cb_lay.addWidget(_export_diff_btn)
        bl.addWidget(self._compare_banner)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_total   = self._make_kpi("Total Events",  "—", _s.ACCENT)
        self._kpi_joined  = self._make_kpi("Joined",        "—", _s.GREEN)
        self._kpi_left    = self._make_kpi("Left",          "—", _s.AMBER)
        self._kpi_down    = self._make_kpi("Down Events",   "—", _s.RED)
        self._kpi_devices = self._make_kpi("Devices Known", "—", _s.ACCENT)
        for w in (self._kpi_total, self._kpi_joined, self._kpi_left,
                  self._kpi_down, self._kpi_devices):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        bl.addLayout(kpi_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        filter_lbl = QLabel("Filter:")
        _s.themed_ss(filter_lbl, "font-size:11px; color:{TEXT_SECONDARY};")
        filter_row.addWidget(filter_lbl)
        _event_tips = {
            "JOINED":    "New device appeared on the network for the first time.",
            "LEFT":      "Device stopped responding — may have disconnected or powered off.",
            "DOWN":      "Device confirmed offline after multiple missed availability checks.",
            "UP":        "A previously down device is reachable again.",
            "DEGRADED":  "Device response time or signal quality has fallen below threshold.",
            "RECOVERED": "Degraded device has returned to normal performance.",
        }
        self._type_checks: dict[str, QCheckBox] = {}
        for et in _ALL_TYPES:
            color, label = _EVENT_STYLE[et]   # color is a token name
            cb = QCheckBox(label)
            cb.setChecked(True)
            _s.themed_ss(cb, lambda c=color: f"QCheckBox {{ font-size:11px; color:{getattr(_s, c)}; font-weight:bold; }}")
            _tip = _event_tips.get(et, "")
            cb.setToolTip(_s.safe_tooltip(_tip) if _tip else _tip)
            cb.toggled.connect(lambda checked, t=et: self._toggle_type(t, checked))
            self._type_checks[et] = cb
            filter_row.addWidget(cb)
        filter_row.addStretch()

        btn_export_inv = QPushButton("↓ Export")
        btn_export_inv.setFixedHeight(24)
        btn_export_inv.setCursor(Qt.CursorShape.PointingHandCursor)
        _s.themed_ss(btn_export_inv, "QPushButton {{ font-size:11px; color:{TEXT_SECONDARY}; border:1px solid {BORDER};"
            " background:transparent; padding:0 10px; border-radius:3px; }}"
            "QPushButton:hover {{ color:{TEXT_PRIMARY}; }}"
            "QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_SECONDARY}; }}")
        btn_export_inv.clicked.connect(self._export_csv)
        filter_row.addWidget(btn_export_inv)
        bl.addLayout(filter_row)

        # Tag-chip filter row (FILTER-11)
        tag_row_lay = QHBoxLayout()
        tag_row_lay.setSpacing(4)
        _tag_lbl = QLabel("Tags:")
        _s.themed_ss(_tag_lbl, "font-size:11px; color:{TEXT_SECONDARY};")
        tag_row_lay.addWidget(_tag_lbl)
        self._tag_chip_area = QHBoxLayout()
        self._tag_chip_area.setSpacing(4)
        tag_row_lay.addLayout(self._tag_chip_area)
        tag_row_lay.addStretch()
        self._tag_chips: dict[str, QPushButton] = {}
        bl.addLayout(tag_row_lay)

        card = QFrame()
        _s.themed_ss(card, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)
        cols = ["●", "Time", "Event", "IP / Host", "MAC", "Vendor", "Detail"]
        self._table = ExpandingTable(
            0, len(cols),
            detail_builder=lambda r: self._build_event_detail(r),
            detail_height=96,
        )
        self._table.setHorizontalHeaderLabels(cols)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(ExpandingTable.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(ExpandingTable.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(ExpandingTable.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        _s.themed_ss(self._table, """
            QTableWidget {{
                font-size:11px; color:{TEXT_PRIMARY};
                background:{BG_CARD}; gridline-color:{BORDER};
                border:none; outline:none;
            }}
            QTableWidget::item {{ padding:3px 5px; border-bottom:1px solid TABLE_ROW_BORDER; }}
            QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}
            QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}
            QHeaderView::section {{
                background:{TH_BG}; color:{TH_TEXT};
                font-size:11px; font-weight:bold;
                padding:4px 5px; border:none;
                border-right:1px solid TH_BORDER;
            }}
            """)
        hdr = self._table.horizontalHeader()
        hdr.resizeSection(0, 22)   # ● status dot
        hdr.resizeSection(1, 140)  # Time
        hdr.resizeSection(2, 90)   # Event
        hdr.resizeSection(3, 130)  # IP / Host
        hdr.resizeSection(4, 135)  # MAC
        hdr.resizeSection(5, 130)  # Vendor
        hdr.setStretchLastSection(True)
        _header_tips = [
            "Alert dot — red: critical alert active · amber: unacked alert · grey: clear",
            "When the event was recorded",
            "JOINED: first seen · LEFT: no response · DOWN: confirmed offline"
            " · UP: back online · DEGRADED: quality drop · RECOVERED: back to normal",
            "IP address, or custom label if one has been set for this device",
            "Hardware (MAC) address — double-click a row to edit device details",
            "NIC vendor identified from the MAC OUI prefix",
            "Additional context recorded with the event",
        ]
        for _i, _tip in enumerate(_header_tips):
            _hi = self._table.horizontalHeaderItem(_i)
            if _hi:
                _hi.setToolTip(_s.safe_tooltip(_tip))
        self._table.cellDoubleClicked.connect(self._on_row_double_clicked)
        self._table.cellClicked.connect(self._on_row_single_clicked)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        def _inv_copy_ip():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 3)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        def _inv_copy_mac():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 4)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        def _inv_label_device():
            r = self._table.currentRow()
            if r < 0:
                return
            mac_it = self._table.item(r, 4)
            if mac_it and mac_it.text() and mac_it.text() != "—":
                dlg = _DeviceLabelDialog(mac_it.text(), self._store, self)
                run_dialog(dlg)

        def _inv_open_browser():
            r = self._table.currentRow()
            if r >= 0:
                ip_it = self._table.item(r, 3)
                if ip_it:
                    ip = ip_it.text().strip()
                    if ip and ip != "—":
                        import webbrowser
                        webbrowser.open(f"http://{ip}")

        def _inv_check_connections():
            r = self._table.currentRow()
            if r >= 0:
                ip_it = self._table.item(r, 3)
                if ip_it:
                    ip = ip_it.text().strip()
                    if ip and ip != "—":
                        self.show_connections_for.emit(ip)

        def _inv_check_cves():
            r = self._table.currentRow()
            if r >= 0:
                ip_it = self._table.item(r, 3)
                if ip_it:
                    ip = ip_it.text().strip()
                    if ip and ip != "—":
                        self.check_cves_for.emit(ip)

        def _inv_show_on_map():
            r = self._table.currentRow()
            if r >= 0:
                ip_it = self._table.item(r, 3)
                if ip_it:
                    ip = ip_it.text().strip()
                    if ip and ip != "—":
                        self.show_on_map.emit(ip)

        install_copy_menu(self._table, [
            ("separator",           None),
            ("Copy IP",             _inv_copy_ip),
            ("Copy MAC",            _inv_copy_mac),
            ("separator",           None),
            ("Label Device",        _inv_label_device),
            ("Open in Browser",     _inv_open_browser),
            ("separator",           None),
            ("Check Connections",   _inv_check_connections),
            ("Check CVEs",          _inv_check_cves),
            ("Show on Geo Map",     _inv_show_on_map),
        ])

        card_lay.addWidget(self._table)
        from ui.table_utils import save_column_widths
        self._table.horizontalHeader().sectionResized.connect(
            lambda _l, _o, _n: save_column_widths(self._table, "devices")
        )

        # OUTPUT-5: bulk action bar (hidden until ≥2 rows selected)
        self._bulk_bar = QFrame()
        self._bulk_bar.setVisible(False)
        _s.themed_ss(self._bulk_bar, "QFrame {{ background:{BG_HOVER}; border-top:2px solid {ACCENT}; }}")
        _bb_lay = QHBoxLayout(self._bulk_bar)
        _bb_lay.setContentsMargins(12, 6, 12, 6)
        _bb_lay.setSpacing(10)
        self._bulk_count_lbl = QLabel("0 rows selected")
        _s.themed_ss(self._bulk_count_lbl, "font-size:11px; font-weight:bold; color:{TEXT_PRIMARY}; background:transparent; border:none;")
        _bb_lay.addWidget(self._bulk_count_lbl)
        _bb_lay.addStretch()
        for _lbl, _slot in [
            ("Export selection", "_bulk_export"),
            ("Snooze alerts 1h", "_bulk_snooze_1h"),
            ("Snooze alerts 8h", "_bulk_snooze_8h"),
            ("Deselect",         "_bulk_deselect"),
        ]:
            _b = QPushButton(_lbl)
            _b.setFixedHeight(24)
            _b.setCursor(Qt.CursorShape.PointingHandCursor)
            _b.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{_s.ACCENT}; border:1px solid {alpha(_s.ACCENT, 0x44)};"
                f" border-radius:3px; font-size:11px; padding:0 10px; }}"
                f"QPushButton:hover {{ background:{alpha(_s.ACCENT, 0x22)}; }}"
                f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.ACCENT}; }}"
            )
            _b.clicked.connect(getattr(self, _slot))
            _bb_lay.addWidget(_b)
        card_lay.addWidget(self._bulk_bar)
        bl.addWidget(card, 1)

        splitter.addWidget(bottom_pane)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 480])
        cl.addWidget(splitter, 1)
        self._content_stack.addWidget(content)

        # ── Page 2: scan comparison view ──────────────────────────────────────
        compare_page = QWidget()
        cmp_lay = QVBoxLayout(compare_page)
        cmp_lay.setContentsMargins(0, 0, 0, 0)
        cmp_lay.setSpacing(0)
        cmp_card = QFrame()
        _s.themed_ss(cmp_card, "QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}")
        cmp_card_lay = QVBoxLayout(cmp_card)
        cmp_card_lay.setContentsMargins(0, 0, 0, 0)
        cmp_card_lay.setSpacing(0)
        self._cmp_table = QTableWidget(0, 6)
        self._cmp_table.setHorizontalHeaderLabels(
            ["●", "Status", "IP / Host", "MAC", "Vendor", "First Seen"]
        )
        self._cmp_table.verticalHeader().setVisible(False)
        self._cmp_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._cmp_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._cmp_table.setAlternatingRowColors(False)
        self._cmp_table.verticalHeader().setDefaultSectionSize(24)
        self._cmp_table.setShowGrid(False)
        _cmp_hdr = self._cmp_table.horizontalHeader()
        _cmp_hdr.resizeSection(0, 22)
        _cmp_hdr.resizeSection(1, 100)
        _cmp_hdr.resizeSection(3, 140)
        _cmp_hdr.resizeSection(4, 130)
        _cmp_hdr.resizeSection(5, 130)
        _cmp_hdr.setStretchLastSection(False)
        _cmp_hdr.setSectionResizeMode(2, _cmp_hdr.ResizeMode.Stretch)
        _s.themed_ss(self._cmp_table, """
            QTableWidget {{
                font-size:11px; color:{TEXT_PRIMARY};
                background:{BG_CARD}; border:none; outline:none;
                gridline-color:{BORDER};
            }}
            QTableWidget::item {{ padding:3px 5px; border-bottom:1px solid TABLE_ROW_BORDER; }}
            QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}
            QHeaderView::section {{
                background:{TH_BG}; color:{TH_TEXT};
                font-size:11px; font-weight:bold;
                padding:4px 5px; border:none;
                border-right:1px solid TH_BORDER;
            }}
            """)
        cmp_card_lay.addWidget(self._cmp_table)
        cmp_lay.addWidget(cmp_card, 1)
        self._content_stack.addWidget(compare_page)

        root.addWidget(self._content_stack, 1)
        self._set_window("24h")

        # DEVICE-2: slide-in drawer (overlay, parented to self)
        self._device_drawer = _DeviceDrawer(self)
        self._device_drawer.closed.connect(lambda: None)  # no-op; drawer hides itself

    # ── Window / filter controls ──────────────────────────────────────────────

    def _set_window(self, label: str) -> None:
        self._window_h = _WINDOWS[label]
        for lbl, btn in self._zoom_btns.items():
            active = lbl == label
            btn.setChecked(active)
            btn.setStyleSheet(self._zoom_style(active))
        self._refresh()

    def _on_hide_offline_toggled(self, checked: bool) -> None:
        self._hide_offline = checked
        self._apply_segment_filter()

    # ── Unknown-device alert prompt (S9-3) ────────────────────────────────────

    def _maybe_show_unknown_device_prompt(self, unknown_count: int) -> None:
        from ui.context_banners import should_show_banner
        if unknown_count <= 0 or not should_show_banner("inventory_unknown_device_alert"):
            self._unknown_device_prompt.setVisible(False)
            return
        s = "s" if unknown_count != 1 else ""
        self._unknown_device_lbl.setText(
            f"ⓘ  {unknown_count} unidentified device{s} on your network — "
            "set up an alert to get notified the moment a new one joins."
        )
        self._unknown_device_prompt.setVisible(True)

    def _on_unknown_device_alert_clicked(self) -> None:
        from ui.context_banners import mark_banner_seen
        mark_banner_seen("inventory_unknown_device_alert")
        self._unknown_device_prompt.setVisible(False)
        self.navigate_to.emit("Custom Triggers")

    def _dismiss_unknown_device_prompt(self) -> None:
        from ui.context_banners import mark_banner_seen
        mark_banner_seen("inventory_unknown_device_alert")
        self._unknown_device_prompt.setVisible(False)

    def _toggle_type(self, event_type: str, checked: bool) -> None:
        if checked:
            self._active_types.add(event_type)
        else:
            self._active_types.discard(event_type)
        self._refresh()

    def _toggle_tag(self, tag: str, active: bool) -> None:
        if active:
            self._active_tags.add(tag)
        else:
            self._active_tags.discard(tag)
        self._refresh()

    def _refresh_tag_chips(self, known_devices: dict) -> None:
        """Rebuild the tag-chip row from current known devices."""
        all_tags: set[str] = set()
        for kd in known_devices.values():
            if kd.tags:
                for t in (t.strip() for t in kd.tags.split(",") if t.strip()):
                    all_tags.add(t)

        current_tags = set(self._tag_chips.keys())
        if all_tags == current_tags:
            return  # No change — avoid flicker

        # Remove old chips
        while self._tag_chip_area.count():
            item = self._tag_chip_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._tag_chips.clear()

        for tag in sorted(all_tags):
            active = tag in self._active_tags
            btn = QPushButton(tag)
            btn.setCheckable(True)
            btn.setChecked(active)
            btn.setFixedHeight(22)
            btn.setStyleSheet(self._tag_chip_style(active))
            btn.toggled.connect(lambda checked, t=tag: self._toggle_tag(t, checked))
            self._tag_chip_area.addWidget(btn)
            self._tag_chips[tag] = btn

    @staticmethod
    def _tag_chip_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ font-size:10px; font-weight:bold; color:{_s.ACCENT};"
                f" background:{alpha(_s.ACCENT, 0x18)}; border:1px solid {_s.ACCENT}; border-radius:10px;"
                f" padding:1px 8px; }}"
                f"QPushButton:hover {{ background:{alpha(_s.ACCENT, 0x30)}; }}"
            )
        return (
            f"QPushButton {{ font-size:10px; color:{_s.TEXT_MUTED};"
            f" background:transparent; border:1px solid {_s.BORDER}; border-radius:10px;"
            f" padding:1px 8px; }}"
            f"QPushButton:hover {{ background:{_s.BG_HOVER}; }}"
        )

    @staticmethod
    def _zoom_style(active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ font-size:11px; background:{_s.ACCENT}; color:{_s.WHITE};"
                f" border:1px solid {_s.ACCENT}; border-radius:3px; }}"
            )
        return (
            f"QPushButton {{ font-size:11px; background:{_s.BG_CARD}; color:{_s.ACCENT};"
            f" border:1px solid {_s.BTN_DISABLED_BORDER}; border-radius:3px; }}"
            f"QPushButton:hover {{ background:{_s.BG_HOVER}; }}"
        )

    # ── KPI helper ────────────────────────────────────────────────────────────

    @staticmethod
    def _make_kpi(label: str, value: str, accent: str) -> QFrame:
        f = QFrame()
        f.setObjectName("kpiTile")
        f.setStyleSheet(
            f"QFrame#kpiTile {{ background:{_s.BG_CARD}; border:1px solid {_s.BORDER};"
            f" border-left:3px solid {accent}; min-width:100px; max-width:180px; }}"
        )
        lay = QVBoxLayout(f)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(1)
        lbl_w = QLabel(label.upper())
        _s.themed_ss(lbl_w, "font-size:9px; font-weight:bold; color:{TEXT_SECONDARY};"
            "background:transparent; border:none;")
        val_w = QLabel(value)
        _s.themed_ss(val_w, "font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};"
            "background:transparent; border:none;")
        val_w.setObjectName("kpiVal")
        lay.addWidget(lbl_w)
        lay.addWidget(val_w)
        return f

    @staticmethod
    def _set_kpi(tile: QFrame, value: str) -> None:
        w = tile.findChild(QLabel, "kpiVal")
        if w:
            w.setText(value)

    # ── Refresh ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _refresh(self) -> None:
        if not self._store:
            return
        if not self.isVisible():
            # _auto_timer ticks every REFRESH_MS for the page's whole lifetime —
            # skip the full table teardown/rebuild (one new PulsingDot per row)
            # while a different nav page is showing. showEvent() forces a
            # refresh when this page becomes visible again.
            return

        active = list(self._active_types) if self._active_types else _ALL_TYPES
        events = self._store.query_device_events(
            hours=self._window_h,
            event_types=active if len(active) < len(_ALL_TYPES) else None,
        )

        # KPI counts
        all_events = self._store.query_device_events(hours=self._window_h)
        total  = len(all_events)
        joined = sum(1 for e in all_events if e.event_type == "JOINED")
        left   = sum(1 for e in all_events if e.event_type == "LEFT")
        down   = sum(1 for e in all_events if e.event_type == "DOWN")
        known  = len(self._store.get_known_devices())

        self._set_kpi(self._kpi_total,   str(total))
        self._set_kpi(self._kpi_joined,  str(joined))
        self._set_kpi(self._kpi_left,    str(left))
        self._set_kpi(self._kpi_down,    str(down))
        self._set_kpi(self._kpi_devices, str(known))

        # Table
        prev_ts = self._last_refresh_ts
        clear_skeleton_rows(self._table)
        self._table.setSortingEnabled(False)
        self._table.clear_detail()
        self._table.setRowCount(0)
        self._rows = []

        if not events:
            return

        if self._content_stack.currentIndex() == 0:
            self._content_stack.setCurrentIndex(1)
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._maybe_show_coach_devices)
            _t.start(700)

        # DEVICE-2: build alert host set for dot lookup (one query, reused per row)
        try:
            _recent_alerts = self._store.get_recent_alerts(hours=24) if self._store else []
        except Exception:
            _recent_alerts = []
        _alert_hosts: set[str] = set()
        _crit_hosts:  set[str] = set()
        for _a in _recent_alerts:
            if _a.get("acked_ts"):
                continue
            _h = _a.get("host", "")
            if _h:
                _alert_hosts.add(_h)
                if _a.get("severity", "") == "CRITICAL":
                    _crit_hosts.add(_h)

        known_devices = self._store.get_known_devices()
        self._refresh_tag_chips(known_devices)

        for evt in events:
            vendor = ""
            custom_name = ""
            kd = known_devices.get((evt.mac or "").lower())
            if kd:
                vendor = kd.vendor or ""
                custom_name = kd.custom_name or ""

            # FILTER-11: tag filter (OR — show event if device has any active tag)
            if self._active_tags and kd:
                device_tags = {t.strip() for t in (kd.tags or "").split(",") if t.strip()}
                if not self._active_tags.intersection(device_tags):
                    continue
            elif self._active_tags and not kd:
                continue  # unknown device, no tags → skip when tag filter active

            self._rows.append((evt, vendor))

            row = self._table.rowCount()
            self._table.insertRow(row)
            dt_str = datetime.datetime.fromtimestamp(evt.ts).strftime("%Y-%m-%d %H:%M:%S")
            color, _ = _EVENT_STYLE.get(evt.event_type, ("TEXT_SECONDARY", evt.event_type))
            hostname = (kd.hostname if kd and kd.hostname else "") or ""
            host_cell = custom_name or hostname or evt.ip or "—"

            # ANIM-1: alert status dot — PulsingDot widget, pulses on new online events
            from ui.widgets.pulsing_dot import PulsingDot
            _keys = {k for k in (evt.ip, evt.mac) if k}
            if _keys & _crit_hosts:
                _dot_hex, _dot_tip = _s.RED, "CRITICAL alert active"
            elif _keys & _alert_hosts:
                _dot_hex, _dot_tip = _s.AMBER, "Unacked alert active"
            else:
                _dot_hex, _dot_tip = _s.TEXT_MUTED, ""
            _dot = PulsingDot()
            _is_new = prev_ts > 0 and evt.ts > prev_ts
            _dot.set_status(
                QColor(_dot_hex),
                animate=_is_new and evt.event_type in ("JOINED", "UP", "RECOVERED"),
            )
            if _dot_tip:
                _dot.setToolTip(_s.safe_tooltip(_dot_tip))
            self._table.setCellWidget(row, 0, _dot)

            self._table.setItem(row, 1, _plain_item(dt_str))
            self._table.setItem(row, 2, _badge_item(evt.event_type, color))
            self._table.setItem(row, 3, _plain_item(host_cell))
            self._table.setItem(row, 4, _plain_item(evt.mac or "—"))
            self._table.setItem(row, 5, _plain_item(vendor or "—"))
            self._table.setItem(row, 6, _plain_item(evt.detail or ""))
            self._table.setRowHeight(row, 24)

        self._table.setSortingEnabled(True)
        self._last_refresh_ts = _time.time()

    @pyqtSlot(dict)
    def on_cycle_done(self, _result: dict) -> None:
        """Slot for AvailabilityWorker.cycle_done — refresh on each monitoring cycle."""
        self._refresh()

    @pyqtSlot(list)
    def set_scan_devices(self, devices: list) -> None:
        """Populate the Current Devices snapshot from the latest scan result."""
        self._scan_devices = devices
        self._snap_table.setSortingEnabled(False)
        self._snap_table.setRowCount(0)

        if not devices:
            self._snap_table.setVisible(False)
            self._snap_empty_lbl.setVisible(True)
            self._snap_count_lbl.setText("Run a scan to see all devices")
            self._seg_bar_frame.setVisible(False)
            self._group_bar_frame.setVisible(False)
            self._health_summary_lbl.setVisible(False)
            self._unknown_device_prompt.setVisible(False)
            return

        from modules.device_classifier import classify_device
        from modules.device_tracker import get_all_annotations as _get_all_ann
        from modules.network_segments import classify_device_segment
        _RISK_COLOR = {
            "HIGH": _s.RED, "STORM": _s.RED, "MEDIUM": _s.AMBER,
            "WARNING": _s.AMBER, "LOW": _s.GREEN, "CLEAN": _s.GREEN,
        }
        _annotations: dict = {}
        if self._store:
            try:
                _annotations = _get_all_ann(self._store)
            except Exception:
                pass  # non-fatal — table may not exist on first run
        self._current_annotations = _annotations

        # Load all overrides once for the confidence indicator
        _overrides: dict = {}
        if self._store:
            try:
                _overrides = self._store.get_all_classification_overrides()
            except Exception:
                pass  # non-fatal — table may not exist on first run

        # Use segments loaded by set_segments() (called from scan_wiring after scan)
        segments = self._current_segments

        for d in devices:
            ip       = (d.ip       if not isinstance(d, dict) else d.get("ip", "?")) or "?"
            host     = (d.hostname if not isinstance(d, dict) else d.get("hostname", "")) or ""
            mac      = (d.mac      if not isinstance(d, dict) else d.get("mac", "?")) or "?"
            vendor   = (d.vendor   if not isinstance(d, dict) else d.get("vendor", "")) or ""
            dtype    = (d.device_type if not isinstance(d, dict) else d.get("device_type", "")) or ""
            if not dtype:
                dtype = (d.connection_type if not isinstance(d, dict) else d.get("connection_type", "")) or ""
            if not dtype or dtype == "Unknown Device":
                _new = classify_device(d)
                if _new and _new != "Unknown Device":
                    dtype = _new
            _raw_level = (d.risk_level if not isinstance(d, dict) else d.get("risk_level", "UNKNOWN")) or "UNKNOWN"
            level    = risk_to_label(_raw_level)
            label    = _annotations.get(mac.lower(), {}).get("user_label", "")
            conf     = float((getattr(d, 'confidence', 0.0) if not isinstance(d, dict) else d.get("confidence", 0.0)) or 0.0)
            _is_gw   = bool((d.is_gateway if not isinstance(d, dict) else d.get("is_gateway", False)) or False)
            _mac_key = mac.lower()
            _is_ovr  = _mac_key in _overrides

            # Confidence indicator prefix (★ override, ● high, ◑ medium, ○ low)
            if _is_ovr:
                _ci_char  = "★"
                _ci_color = _s.ACCENT
                _ci_tip   = f"User override: {_overrides[_mac_key]}"
            elif conf >= 0.7 or _is_gw:
                _ci_char  = "●"
                _ci_color = _s.GREEN
                _ci_tip   = f"Confidence: {conf:.0%} (high)"
            elif conf >= 0.3:
                _ci_char  = "◑"
                _ci_color = _s.AMBER
                _ci_tip   = f"Confidence: {conf:.0%} (medium)"
            else:
                _ci_char  = "○"
                _ci_color = _s.TEXT_MUTED
                _ci_tip   = "Confidence: unknown" if conf == 0.0 else f"Confidence: {conf:.0%} (low)"
            dtype_display = f"{_ci_char} {dtype or '—'}"

            # Segment classification
            seg = classify_device_segment(ip, segments) if segments else None
            seg_key = seg.id if (seg and seg.id > 0) else (seg.cidr if seg else None)

            row = self._snap_table.rowCount()
            self._snap_table.insertRow(row)

            # Col 0: status dot — reflects live/cached/stale/pinned freshness
            _display_state = (d.get("display_state", "") if isinstance(d, dict)
                              else getattr(d, "display_state", "")) or ""
            _last_seen_ts  = (d.get("last_seen_ts", 0) if isinstance(d, dict)
                              else getattr(d, "last_seen_ts", 0)) or 0
            if _display_state == "pinned":
                dot_char  = "⬡"
                dot_color = _s.ACCENT
                dot_tip   = "Pinned — always shown"
            elif _display_state in ("cached", "stale"):
                _ago = _time.time() - _last_seen_ts if _last_seen_ts else 0
                if _display_state == "cached":
                    dot_char  = "◌"
                    dot_color = _s.AMBER
                    _h = int(_ago // 3600)
                    _m = int((_ago % 3600) // 60)
                    dot_tip = f"Cached — last seen {_h}h {_m}m ago"
                else:
                    dot_char  = "○"
                    dot_color = _s.TEXT_MUTED
                    _days = int(_ago // 86400)
                    dot_tip = f"Stale — last seen {_days}d ago"
            else:
                # Live scan result — use risk colour
                dot_char  = "●"
                dot_color = _RISK_COLOR.get(level, _s.TEXT_MUTED)
                dot_tip   = f"Online  ·  Risk: {level}"
            dot_item = QTableWidgetItem(dot_char)
            dot_item.setForeground(QColor(dot_color))
            dot_item.setToolTip(_s.safe_tooltip(dot_tip))
            dot_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            # Store display_state so _apply_segment_filter can hide offline rows
            dot_item.setData(Qt.ItemDataRole.UserRole + 1, _display_state)
            # Store (location, owner) so the group pill bar can filter by either (S5-2)
            _ann = _annotations.get(mac.lower(), {})
            dot_item.setData(
                Qt.ItemDataRole.UserRole + 2,
                (_ann.get("location", ""), _ann.get("owner", "")),
            )
            self._snap_table.setItem(row, 0, dot_item)

            # Col 1: segment colour dot
            if seg:
                seg_dot = QTableWidgetItem("●")
                seg_dot.setForeground(QColor(seg.color))
                seg_dot.setToolTip(_s.safe_tooltip(seg.name))
                seg_dot.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                # Store seg_key as user data for filtering
                seg_dot.setData(Qt.ItemDataRole.UserRole, seg_key)
            else:
                seg_dot = QTableWidgetItem("○")
                seg_dot.setForeground(QColor(_s.TEXT_MUTED))
                seg_dot.setToolTip(_s.safe_tooltip("Unknown segment"))
                seg_dot.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                seg_dot.setData(Qt.ItemDataRole.UserRole, None)
            self._snap_table.setItem(row, 1, seg_dot)

            # Cols 2–8: IP, Label, Hostname, MAC, Vendor, Type, Risk
            _vals = [ip, label, host or "—", mac, vendor or "—", dtype_display, level]
            for col, val in enumerate(_vals, 2):
                item = _plain_item(val)
                if col == 3 and label:
                    item.setForeground(QColor(_s.ACCENT))
                elif col == 7:
                    item.setForeground(QColor(_ci_color))
                    item.setToolTip(_s.safe_tooltip(_ci_tip))
                self._snap_table.setItem(row, col, item)
            self._snap_table.setRowHeight(row, 24)

        self._snap_table.setSortingEnabled(True)

        # Rebuild Room/Owner group pills from the freshly stored annotations (S5-2)
        self._rebuild_group_pills()

        # Apply current segment filter (hide rows not in active segments)
        self._apply_segment_filter()

        online = sum(
            1 for d in devices
            if (d.risk_level if not isinstance(d, dict) else d.get("risk_level", "")) not in ("", "UNKNOWN", None)
        )
        total = len(devices)
        self._snap_count_lbl.setText(f"{total} devices  ·  {online} active")
        self._snap_table.setVisible(True)
        self._snap_empty_lbl.setVisible(False)

        # ── Health summary top-line (S5-3) ─────────────────────────────────────
        try:
            from modules.device_health_summary import summarize_devices, summary_line
            recent_alerts = self._store.get_recent_alerts(hours=24.0) if self._store else []
            health_results = summarize_devices(devices, recent_alerts)
            self._health_summary_lbl.setText(summary_line(health_results))
            self._health_summary_lbl.setVisible(True)
        except Exception:
            self._health_summary_lbl.setVisible(False)  # non-fatal

        # ── Unknown-device alert prompt (S9-3) ─────────────────────────────────
        _unknown_count = 0
        for d in devices:
            _dt = (d.device_type if not isinstance(d, dict) else d.get("device_type", "")) or ""
            if _dt.strip().lower() in ("", "unknown", "unknown device"):
                _unknown_count += 1
        self._maybe_show_unknown_device_prompt(_unknown_count)

        # Switch to content view if still on empty state
        if self._content_stack.currentIndex() == 0:
            self._content_stack.setCurrentIndex(1)

    def update_device_vendor(self, mac: str, vendor: str) -> None:
        """Update the Manufacturer cell (col 6) in _snap_table for a resolved vendor.

        Called by _on_vendor_resolved in scan_wiring after async OUI lookup returns a
        result, so the Inventory page shows the resolved vendor in the current session
        without requiring a rescan or restart.
        """
        if not mac or not vendor:
            return
        norm = mac.lower().replace("-", "").replace(":", "")
        for row in range(self._snap_table.rowCount()):
            mac_item = self._snap_table.item(row, 5)  # col 5 = MAC Address
            if not mac_item:
                continue
            row_norm = mac_item.text().lower().replace(":", "").replace("-", "")
            if row_norm == norm:
                vendor_item = self._snap_table.item(row, 6)  # col 6 = Manufacturer
                if vendor_item:
                    vendor_item.setText(vendor)
                break

    def _on_snap_row_clicked(self, item: QTableWidgetItem) -> None:
        """Single-click a Current Devices row to open its drawer (S5-6)."""
        if not self._store or item is None:
            return
        mac_item = self._snap_table.item(item.row(), 5)  # col 5 = MAC Address
        mac = mac_item.text().strip() if mac_item else ""
        if mac and mac != "—":
            self.open_device_drawer(mac)

    def _snap_table_context_menu(self, pos) -> None:
        """Right-click context menu for the Current Devices snapshot table."""
        idx = self._snap_table.indexAt(pos)
        if not idx.isValid():
            return
        row = idx.row()
        mac_item  = self._snap_table.item(row, 5)  # col 5 = MAC Address
        dtype_item = self._snap_table.item(row, 7)  # col 7 = Type
        if not mac_item:
            return
        mac = mac_item.text().strip()
        raw_dtype = (dtype_item.text().strip() if dtype_item else "") or ""
        # Strip confidence indicator prefix
        for _pfx in ("★ ", "● ", "◑ ", "○ "):
            if raw_dtype.startswith(_pfx):
                raw_dtype = raw_dtype[len(_pfx):]
                break

        current_override: Optional[str] = None
        alert_opt_in = False
        if self._store:
            try:
                current_override = self._store.get_classification_override(mac)
            except Exception:
                pass  # non-fatal
            try:
                known = self._store.get_known_devices()
                alert_opt_in = bool(known[mac].alert_opt_in) if mac in known else False
            except Exception:
                pass  # non-fatal

        menu = QMenu(self)
        act_drawer   = menu.addAction("Edit Device / View Timeline →")
        menu.addSeparator()
        act_override = menu.addAction("Override Device Type…")
        act_clear    = menu.addAction("Clear Type Override")
        act_clear.setEnabled(bool(current_override))
        menu.addSeparator()
        act_alert_toggle = menu.addAction(
            "Stop alerting on this device" if alert_opt_in
            else "Alert me if this device goes down"
        )

        action = menu.exec(self._snap_table.viewport().mapToGlobal(pos))
        if action == act_drawer and self._store:
            self.open_device_drawer(mac)
        elif action == act_override and self._store:
            dlg = _TypeOverrideDialog(mac, raw_dtype, current_override, self._store, self)
            if run_dialog(dlg) == QDialog.DialogCode.Accepted:
                self.set_scan_devices(self._scan_devices)
        elif action == act_clear and self._store:
            try:
                clear_classification_override(self._store, mac)
            except Exception:
                pass  # non-fatal
            self.set_scan_devices(self._scan_devices)
        elif action == act_alert_toggle and self._store:
            try:
                set_device_alert_opt_in(self._store, mac, not alert_opt_in)
            except Exception:
                pass  # non-fatal

    @pyqtSlot(list)
    def set_segments(self, segments: list) -> None:
        """Store current segments and rebuild pill bar (called from scan_wiring)."""
        self._current_segments = segments
        self._rebuild_segment_pills(segments)

    def _rebuild_segment_pills(self, segments: list) -> None:
        """Rebuild the horizontal pill bar from *segments*."""
        # Clear existing pills
        while self._seg_pill_row.count() > 1:  # keep trailing stretch
            item = self._seg_pill_row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._seg_pills.clear()

        if not segments:
            self._seg_bar_frame.setVisible(False)
            return

        # Count devices per segment for pill labels
        seg_counts: dict = {}
        for d in self._scan_devices:
            ip = (d.ip if not isinstance(d, dict) else d.get("ip", "")) or ""
            try:
                from modules.network_segments import classify_device_segment
                s = classify_device_segment(ip, segments)
                key = s.id if (s and s.id > 0) else (s.cidr if s else "__none__")
            except Exception:
                key = "__none__"
            seg_counts[key] = seg_counts.get(key, 0) + 1

        all_count = len(self._scan_devices)

        # "All" pill
        all_pill = self._make_seg_pill(
            f"All ({all_count})", None, active=self._active_seg_ids is None
        )
        all_pill.clicked.connect(lambda: self._toggle_segment(None))
        self._seg_pill_row.insertWidget(0, all_pill)
        self._seg_pills["__all__"] = all_pill

        for idx, seg in enumerate(segments):
            key = seg.id if seg.id > 0 else seg.cidr
            count = seg_counts.get(seg.id if seg.id > 0 else seg.cidr, 0)
            if count == 0:
                count = seg_counts.get(seg.cidr, 0)
            pill = self._make_seg_pill(
                f"{seg.name} ({count})",
                seg.color,
                active=(self._active_seg_ids is not None and key in self._active_seg_ids),
            )
            pill.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            pill.customContextMenuRequested.connect(
                lambda _pos, s=seg: self._open_seg_context(s)
            )
            pill.clicked.connect(lambda _c=False, k=key: self._toggle_segment(k))
            self._seg_pill_row.insertWidget(idx + 1, pill)
            self._seg_pills[key] = pill

        self._seg_bar_frame.setVisible(True)

    def _make_seg_pill(self, text: str, color: Optional[str], active: bool) -> QPushButton:
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(active)
        btn.setFixedHeight(24)
        btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_pill_style(btn, color, active)
        return btn

    def _apply_pill_style(self, btn: QPushButton, color: Optional[str], active: bool) -> None:
        dot_color = color or _s.ACCENT
        if active:
            btn.setStyleSheet(
                f"QPushButton {{ background:{alpha(dot_color, 0x22)}; color:{_s.TEXT_PRIMARY};"
                f" border:1.5px solid {dot_color}; border-radius:12px;"
                f" font-size:11px; padding:0 10px; font-weight:bold; }}"
                f"QPushButton:hover {{ background:{alpha(dot_color, 0x33)}; color:{_s.TEXT_PRIMARY}; }}"
                f"QPushButton:pressed {{ background:{alpha(dot_color, 0x44)}; color:{_s.TEXT_PRIMARY}; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{_s.TEXT_SECONDARY};"
                f" border:1px solid {_s.BORDER}; border-radius:12px;"
                f" font-size:11px; padding:0 10px; }}"
                f"QPushButton:hover {{ background:{_s.BG_HOVER}; color:{_s.TEXT_PRIMARY};"
                f" border-color:{dot_color}; }}"
                f"QPushButton:pressed {{ background:{_s.BG_HOVER}; color:{_s.TEXT_SECONDARY}; }}"
            )

    def _toggle_segment(self, seg_key) -> None:
        """Toggle a segment pill; None = select all (clear filter)."""
        if seg_key is None:
            # "All" selected — clear filter
            self._active_seg_ids = None
            for key, btn in self._seg_pills.items():
                active = key == "__all__"
                color = None if key == "__all__" else None
                if key != "__all__":
                    # find colour from current segments
                    color = self._seg_color_for_key(key)
                btn.setChecked(active)
                self._apply_pill_style(btn, color, active)
        else:
            # Toggle this specific segment
            if self._active_seg_ids is None:
                self._active_seg_ids = {seg_key}
            elif seg_key in self._active_seg_ids:
                self._active_seg_ids.discard(seg_key)
                if not self._active_seg_ids:
                    self._active_seg_ids = None  # all cleared → show all
            else:
                self._active_seg_ids.add(seg_key)

            # Update pill appearances
            all_active = self._active_seg_ids is None
            if "__all__" in self._seg_pills:
                self._seg_pills["__all__"].setChecked(all_active)
                self._apply_pill_style(self._seg_pills["__all__"], None, all_active)
            for key, btn in self._seg_pills.items():
                if key == "__all__":
                    continue
                active = (self._active_seg_ids is not None and key in self._active_seg_ids)
                btn.setChecked(active)
                color = self._seg_color_for_key(key)
                self._apply_pill_style(btn, color, active)

        self._apply_segment_filter()

    def _seg_color_for_key(self, key) -> Optional[str]:
        for seg in self._current_segments:
            k = seg.id if seg.id > 0 else seg.cidr
            if k == key:
                return seg.color
        return None

    def _apply_segment_filter(self) -> None:
        """Show/hide snap_table rows based on _active_seg_ids and _hide_offline."""
        _offline_states = {"cached", "stale"}
        for row in range(self._snap_table.rowCount()):
            hidden = False

            # Offline filter: hide rows whose display_state is cached or stale
            if self._hide_offline:
                dot_item = self._snap_table.item(row, 0)
                _state = (
                    dot_item.data(Qt.ItemDataRole.UserRole + 1)
                    if dot_item else ""
                ) or ""
                if _state in _offline_states:
                    hidden = True

            # Segment filter: hide rows not in the active segment set
            if not hidden and self._active_seg_ids is not None:
                seg_item = self._snap_table.item(row, 1)
                row_key = seg_item.data(Qt.ItemDataRole.UserRole) if seg_item else None
                if row_key not in self._active_seg_ids:
                    hidden = True

            # Room/Owner group filter (S5-2): hide rows not in the active group set
            if not hidden and self._active_group_keys is not None:
                dot_item = self._snap_table.item(row, 0)
                _loc_owner = (
                    dot_item.data(Qt.ItemDataRole.UserRole + 2) if dot_item else None
                ) or ("", "")
                _idx = 0 if self._group_dim == "location" else 1
                row_group = (_loc_owner[_idx] or "").strip() or "Unassigned"
                if row_group not in self._active_group_keys:
                    hidden = True

            self._snap_table.setRowHidden(row, hidden)

    def _open_seg_context(self, seg) -> None:
        """Right-click context menu on a segment pill."""
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        _s.themed_ss(menu, "QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; }}"
            "QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
        edit_act = menu.addAction("Edit Segment")
        action = menu.exec(self.cursor().pos())
        if action == edit_act:
            dlg = _SegmentEditorDialog(segment=seg, parent=self)
            if run_dialog(dlg) == QDialog.DialogCode.Accepted and self._store:
                vals = dlg.result_segment()
                seg.name = vals["name"]
                seg.color = vals["color"]
                seg.description = vals["description"]
                try:
                    upsert_segment(self._store, seg)
                except Exception:
                    pass  # non-fatal — DB write failure should not crash the UI
                self._rebuild_segment_pills(self._current_segments)
                self.set_scan_devices(self._scan_devices)

    # ── Room/Owner group pills (S5-2) ───────────────────────────────────────────

    def _on_group_dim_changed(self, _idx: int) -> None:
        self._group_dim = self._group_dim_combo.currentData()
        self._active_group_keys = None
        self._rebuild_group_pills()
        self._apply_segment_filter()

    def _group_value(self, mac: str) -> str:
        ann = self._current_annotations.get(mac.lower(), {})
        return (ann.get(self._group_dim, "") or "").strip()

    def _rebuild_group_pills(self) -> None:
        """Rebuild the Room/Owner pill bar from devices in the current scan."""
        while self._group_pill_row.count() > 1:  # keep trailing stretch
            item = self._group_pill_row.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._group_pills.clear()

        counts: dict = {}
        for d in self._scan_devices:
            mac = (d.mac if not isinstance(d, dict) else d.get("mac", "")) or ""
            key = self._group_value(mac) or "Unassigned"
            counts[key] = counts.get(key, 0) + 1

        # Only show the bar once at least one device has a group assigned
        if not counts or set(counts) == {"Unassigned"}:
            self._group_bar_frame.setVisible(False)
            return

        all_count = len(self._scan_devices)
        all_pill = self._make_seg_pill(
            f"All ({all_count})", None, active=self._active_group_keys is None
        )
        all_pill.clicked.connect(lambda: self._toggle_group(None))
        self._group_pill_row.insertWidget(0, all_pill)
        self._group_pills["__all__"] = all_pill

        for idx, key in enumerate(sorted(counts)):
            pill = self._make_seg_pill(
                f"{key} ({counts[key]})",
                None,
                active=(self._active_group_keys is not None and key in self._active_group_keys),
            )
            pill.clicked.connect(lambda _c=False, k=key: self._toggle_group(k))
            self._group_pill_row.insertWidget(idx + 1, pill)
            self._group_pills[key] = pill

        self._group_bar_frame.setVisible(True)

    def _toggle_group(self, group_key: Optional[str]) -> None:
        """Toggle a group pill; None = select all (clear filter)."""
        if group_key is None:
            self._active_group_keys = None
            for key, btn in self._group_pills.items():
                active = key == "__all__"
                btn.setChecked(active)
                self._apply_pill_style(btn, None, active)
        else:
            if self._active_group_keys is None:
                self._active_group_keys = {group_key}
            elif group_key in self._active_group_keys:
                self._active_group_keys.discard(group_key)
                if not self._active_group_keys:
                    self._active_group_keys = None
            else:
                self._active_group_keys.add(group_key)

            all_active = self._active_group_keys is None
            if "__all__" in self._group_pills:
                self._group_pills["__all__"].setChecked(all_active)
                self._apply_pill_style(self._group_pills["__all__"], None, all_active)
            for key, btn in self._group_pills.items():
                if key == "__all__":
                    continue
                active = (self._active_group_keys is not None and key in self._active_group_keys)
                btn.setChecked(active)
                self._apply_pill_style(btn, None, active)

        self._apply_segment_filter()

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _build_event_detail(self, logical_row: int) -> QWidget:
        if logical_row >= len(self._rows):
            return QWidget()
        evt, vendor = self._rows[logical_row]
        color, _ = _EVENT_STYLE.get(evt.event_type, ("TEXT_SECONDARY", evt.event_type))

        outer = QWidget()
        _s.themed_ss(outer, lambda c=color: (
            f"QWidget {{ background:{_s.BG_HOVER}; border:none;"
            f" border-left:3px solid {getattr(_s, c)}; }}"
        ))
        lay = QHBoxLayout(outer)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(32)

        def _hdr(t):
            l = QLabel(t)
            _s.themed_ss(l, "font-size:10px; font-weight:bold; color:{TEXT_MUTED}; background:transparent; border:none;")
            return l

        def _val(t, c=_s.TEXT_PRIMARY):
            l = QLabel(str(t))
            l.setStyleSheet(f"font-size:11px; color:{c}; background:transparent; border:none;")
            return l

        ts_str = datetime.datetime.fromtimestamp(evt.ts).strftime("%Y-%m-%d %H:%M:%S")
        col1 = QWidget()
        col1.setStyleSheet("QWidget { background:transparent; border:none; }")
        g1 = QFormLayout(col1)
        g1.setContentsMargins(0, 0, 0, 0)
        g1.setSpacing(3)
        g1.setHorizontalSpacing(12)
        g1.addRow(_hdr("Timestamp"), _val(ts_str))
        g1.addRow(_hdr("Event"),     _val(evt.event_type, color))
        g1.addRow(_hdr("IP"),        _val(evt.ip or "—"))

        col2 = QWidget()
        col2.setStyleSheet("QWidget { background:transparent; border:none; }")
        g2 = QFormLayout(col2)
        g2.setContentsMargins(0, 0, 0, 0)
        g2.setSpacing(3)
        g2.setHorizontalSpacing(12)
        g2.addRow(_hdr("MAC"),    _val(evt.mac or "—"))
        g2.addRow(_hdr("Vendor"), _val(vendor or "—"))
        if evt.detail:
            g2.addRow(_hdr("Detail"), _val(evt.detail))

        lay.addWidget(col1)
        lay.addWidget(col2)
        lay.addStretch()
        return outer

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "_device_drawer") and self._device_drawer.isVisible():
            w = _DeviceDrawer._DRAWER_WIDTH
            self._device_drawer.setGeometry(
                self.width() - w, 0, w, self.height()
            )

    @pyqtSlot(int, int)
    def _on_row_single_clicked(self, row: int, _col: int) -> None:
        item = self._table.item(row, 4)  # MAC column (shifted by DEVICE-2 dot col)
        if not item:
            return
        mac = item.text().strip()
        if not mac or mac == "—":
            return
        self._device_drawer.load(mac, self._store)
        if not self._device_drawer.isVisible():
            self._device_drawer.open_drawer()

    @pyqtSlot(int, int)
    def _on_row_double_clicked(self, row: int, _col: int) -> None:
        item = self._table.item(row, 4)  # MAC column (shifted by DEVICE-2 dot col)
        if not item:
            return
        mac = item.text().strip()
        if not mac or mac == "—":
            return
        if self._store:
            dlg = _DeviceLabelDialog(mac, self._store, parent=self)
            if run_dialog(dlg) == QDialog.DialogCode.Accepted:
                self._refresh()
        else:
            self.device_selected.emit(mac)

    def _export_csv(self) -> None:
        import csv as _csv
        import datetime as _dt2
        from PyQt6.QtWidgets import QFileDialog
        from ui.widgets.toast import ToastManager
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Inventory Events", "inventory_events.csv", "CSV files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        cols = ["Time", "Event", "IP / Host", "MAC", "Vendor", "Detail"]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(cols)
                for evt, vendor in self._rows:
                    dt_str = _dt2.datetime.fromtimestamp(evt.ts).strftime("%Y-%m-%d %H:%M:%S")
                    w.writerow([dt_str, evt.event_type, evt.ip or "—",
                                evt.mac or "—", vendor or "—", evt.detail or ""])
            import os
            ToastManager.show(f"✓ Saved to {os.path.basename(path)}", "success")
        except Exception as exc:
            ToastManager.show(f"Export failed: {exc}", "error")

    def _export_diff_csv(self) -> None:
        """Export the scan-comparison diff table (_cmp_table) as CSV — the
        added/removed/unchanged device list built by _start_compare_mode()."""
        import csv as _csv
        from PyQt6.QtWidgets import QFileDialog
        from ui.widgets.toast import ToastManager
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Diff as CSV", "inventory_diff.csv", "CSV files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        cols = ["Status", "IP / Host", "MAC", "Vendor", "First Seen"]
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(cols)
                for row in range(self._cmp_table.rowCount()):
                    w.writerow([
                        (self._cmp_table.item(row, col).text() if self._cmp_table.item(row, col) else "")
                        for col in range(1, 6)
                    ])
            import os
            ToastManager.show(f"✓ Saved to {os.path.basename(path)}", "success")
        except Exception as exc:
            ToastManager.show(f"Export failed: {exc}", "error")

    def focus_on_host(self, ip: str, mac: str = "") -> None:
        """Navigate to and highlight the device matching ip or mac (cross-page API)."""
        self.select_device(ip or mac)

    def open_device_drawer(self, mac: str, suggested_label: str = "") -> None:
        """Open the device drawer for *mac* (cross-page API — S5-1 naming toast)."""
        if not mac:
            return
        self._device_drawer.load(mac, self._store, suggested_label=suggested_label)
        if not self._device_drawer.isVisible():
            self._device_drawer.open_drawer()

    def select_device(self, ip_or_mac: str) -> None:
        """DEVICE-1: Navigate to and select the row matching ip_or_mac (IP or MAC address)."""
        needle = ip_or_mac.strip().lower()
        for row in range(self._table.rowCount()):
            ip_item  = self._table.item(row, 3)  # "IP / Host" (shifted by DEVICE-2 dot col)
            mac_item = self._table.item(row, 4)  # "MAC"
            ip_text  = (ip_item.text()  if ip_item  else "").strip().lower()
            mac_text = (mac_item.text() if mac_item else "").strip().lower()
            if needle in (ip_text, mac_text):
                self._table.selectRow(row)
                self._table.scrollToItem(self._table.item(row, 1))  # scroll to Time col
                mac = mac_item.text().strip() if mac_item else ""
                if mac and mac != "—":
                    self._device_drawer.load(mac, self._store)
                    if not self._device_drawer.isVisible():
                        self._device_drawer.open_drawer()
                return

    # ── OUTPUT-5: bulk selection actions ──────────────────────────────────────

    def _on_selection_changed(self, selected, deselected) -> None:
        n = len(self._table.selectionModel().selectedRows())
        if n >= 2:
            self._bulk_count_lbl.setText(f"{n} devices selected")
            self._bulk_bar.setVisible(True)
        else:
            self._bulk_bar.setVisible(False)

    def _bulk_export(self) -> None:
        import csv as _csv
        from PyQt6.QtWidgets import QFileDialog
        from ui.widgets.toast import ToastManager

        rows = sorted(set(idx.row() for idx in self._table.selectionModel().selectedIndexes()))
        if not rows:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Selected Devices", "inventory_selection.csv", "CSV files (*.csv)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = _csv.writer(f)
                w.writerow(["Time", "Event", "IP / Host", "MAC", "Vendor", "Detail"])
                for row in rows:
                    def _t(col):
                        it = self._table.item(row, col)
                        return it.text() if it else ""
                    w.writerow([_t(1), _t(2), _t(3), _t(4), _t(5), _t(6)])
            import os
            ToastManager.show(f"✓ Exported {len(rows)} rows to {os.path.basename(path)}", "success")
        except Exception as exc:
            ToastManager.show(f"Export failed: {exc}", "error")

    def _bulk_snooze(self, hours: int) -> None:
        import time as _t
        from PyQt6.QtCore import QSettings
        from ui.widgets.toast import ToastManager

        rows = sorted(set(idx.row() for idx in self._table.selectionModel().selectedIndexes()))
        if not rows:
            return
        qs = QSettings("NetSentinel", "NetSentinel")
        expiry = _t.time() + hours * 3600
        snoozed: list[str] = []
        for row in rows:
            for col in (3, 4):  # IP/Host, MAC
                it = self._table.item(row, col)
                key = (it.text() if it else "").strip()
                if key and key != "—":
                    qs.setValue(f"alerts/snooze/{key}", expiry)
                    if col == 3:
                        snoozed.append(key)
        ToastManager.show(
            f"Snoozed alerts for {len(snoozed)} device(s) for {hours}h", "success"
        )
        self._table.clearSelection()

    def _bulk_snooze_1h(self) -> None:
        self._bulk_snooze(1)

    def _bulk_snooze_8h(self) -> None:
        self._bulk_snooze(8)

    def _bulk_deselect(self) -> None:
        self._table.clearSelection()

    # ── ACT-3: scan comparison ────────────────────────────────────────────────

    def _build_scan_sessions(self) -> list:
        """Group device events into scan sessions (30-minute windows).

        Returns list of (ts, label) sorted oldest→newest, up to 20 entries.
        """
        if not self._store:
            return []
        try:
            events = self._store.query_device_events(hours=8760)  # up to 1 year
        except Exception:
            return []

        if not events:
            return []

        sorted_events = sorted(events, key=lambda e: e.ts)
        sessions: list = []
        last_ts = 0
        for evt in sorted_events:
            if evt.ts - last_ts > 1800:  # 30-minute gap = new session
                sessions.append(evt.ts)
            last_ts = evt.ts

        # Format labels
        result = []
        for ts in sessions:
            dt = datetime.datetime.fromtimestamp(ts)
            label = dt.strftime("%Y-%m-%d %H:%M")
            result.append((ts, label))

        return result[-20:]  # most recent 20

    def _open_compare_dialog(self) -> None:
        sessions = self._build_scan_sessions()
        if len(sessions) < 2:
            from ui.widgets.toast import ToastManager
            ToastManager.show(
                "Need at least 2 scan sessions in history to compare. "
                "Run more scans first.",
                "warning",
            )
            return
        dlg = _ScanCompareDialog(sessions, parent=self)
        if run_dialog(dlg) == QDialog.DialogCode.Accepted:
            ts_a, ts_b = dlg.result_timestamps()
            self._start_compare_mode(ts_a, ts_b)

    def _start_compare_mode(self, ts_a: int, ts_b: int) -> None:
        if not self._store:
            return
        self._compare_mode = True

        # Collect MACs active in each session window (±15 min around session ts)
        try:
            all_events = self._store.query_device_events(hours=8760)
        except Exception:
            return

        def _macs_in_window(pivot: int) -> set:
            window = 900  # 15 minutes
            return {
                e.mac for e in all_events
                if e.mac and abs(e.ts - pivot) <= window
            }

        macs_a = _macs_in_window(ts_a)
        macs_b = _macs_in_window(ts_b)
        new_macs  = macs_b - macs_a
        gone_macs = macs_a - macs_b
        both_macs = macs_a & macs_b

        known = self._store.get_known_devices() if self._store else {}

        # Build table rows: (sort_key, mac, status, color, bg)
        table_rows = []
        for mac in new_macs:
            table_rows.append((0, mac, "NEW", _s.GREEN, f"{alpha(_s.GREEN, 0x18)}"))
        for mac in gone_macs:
            table_rows.append((1, mac, "GONE", _s.RED, f"{alpha(_s.RED, 0x18)}"))
        for mac in both_macs:
            table_rows.append((2, mac, "UNCHANGED", _s.TEXT_MUTED, _s.BG_CARD))

        self._cmp_table.setRowCount(0)
        for _sort, mac, status, color, bg in sorted(table_rows, key=lambda x: x[0]):
            kd = known.get(mac.lower()) or known.get(mac)
            vendor = (kd.vendor or "—") if kd else "—"
            host   = (kd.custom_name or kd.ip or kd.hostname or mac) if kd else mac
            first  = (
                datetime.datetime.fromtimestamp(kd.first_seen).strftime("%Y-%m-%d %H:%M")
                if kd and kd.first_seen else "—"
            )
            row = self._cmp_table.rowCount()
            self._cmp_table.insertRow(row)

            dot = QTableWidgetItem("●")
            dot.setForeground(QColor(color))
            dot.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._cmp_table.setItem(row, 0, dot)

            for col, text in enumerate([status, host, mac, vendor, first], start=1):
                item = QTableWidgetItem(text)
                item.setForeground(QColor(color if col == 1 else _s.TEXT_PRIMARY))
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self._cmp_table.setItem(row, col, item)

            self._cmp_table.setRowHeight(row, 24)

        # Update banner
        dt_a = datetime.datetime.fromtimestamp(ts_a).strftime("%Y-%m-%d %H:%M")
        dt_b = datetime.datetime.fromtimestamp(ts_b).strftime("%Y-%m-%d %H:%M")
        self._compare_banner_lbl.setText(
            f"Compare: {dt_a}  →  {dt_b}  ·  "
            f"{len(new_macs)} new  ·  {len(gone_macs)} gone  ·  {len(both_macs)} unchanged"
        )
        self._compare_banner.setVisible(True)
        self._content_stack.setCurrentIndex(2)

    def _exit_compare_mode(self) -> None:
        self._compare_mode = False
        self._compare_banner.setVisible(False)
        idx = 1 if self._rows else 0
        self._content_stack.setCurrentIndex(idx)
