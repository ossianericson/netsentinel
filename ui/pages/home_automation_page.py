"""
Home Automation Hub page.

Layout
──────
  Top:    Page title + subtitle
  KPI row: Total / Online / Offline / Detected-today
  Filter bar: Room filter | Category filter | Search | + Add | Scan button
  Middle splitter:
    Left  (60%): Device table
    Right (40%): Detail panel (slides in on row select)
  Bottom: Pinned widget strip (horizontal scroll of live mini-tiles)
"""

from __future__ import annotations

import datetime
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_HDR_BORDER,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
)

# ── Category definitions ──────────────────────────────────────────────────────

_CATEGORIES = [
    ("home_automation", "Home Automation"),
    ("smart_hub",       "Smart Hub"),
    ("lighting",        "Lighting"),
    ("media_player",    "Media Player"),
    ("smart_tv",        "Smart TV"),
    ("smart_speaker",   "Smart Speaker"),
    ("smart_plug",      "Smart Plug"),
    ("thermostat",      "Thermostat"),
    ("security",        "Security"),
    ("camera",          "Camera"),
    ("unknown",         "Unknown"),
]

_CAT_DISPLAY = {k: v for k, v in _CATEGORIES}

_CAT_ICON = {
    "home_automation": "🏠",
    "smart_hub":       "🔗",
    "lighting":        "💡",
    "media_player":    "🔊",
    "smart_tv":        "📺",
    "smart_speaker":   "🔈",
    "smart_plug":      "🔌",
    "thermostat":      "🌡",
    "security":        "🔒",
    "camera":          "📷",
    "unknown":         "❓",
}

_STATUS_COLOR = {"UP": GREEN, "DOWN": RED, "DEGRADED": AMBER, "UNKNOWN": TEXT_MUTED}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet(
        f"QFrame#card {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0; }}"
    )
    outer = QVBoxLayout(frame)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"background:{BG_CARD}; border-bottom:1px solid {CARD_HDR_BORDER}; border-radius:0;"
    )
    hl = QHBoxLayout(hdr)
    hl.setContentsMargins(12, 0, 10, 0)
    t = QLabel(title.upper())
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-weight:bold; font-size:11px;"
        f" letter-spacing:0.5px; background:transparent; border:none;"
    )
    hl.addWidget(t)
    hl.addStretch()
    outer.addWidget(hdr)

    body = QVBoxLayout()
    body.setContentsMargins(0, 0, 0, 0)
    outer.addLayout(body, 1)
    return frame, body


def _kpi_tile(label: str, color: str = ACCENT) -> tuple[QFrame, QLabel]:
    """Return (tile_frame, value_label)."""
    tile = QFrame()
    tile.setStyleSheet(
        f"background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {color}; border-radius:0;"
    )
    lay = QVBoxLayout(tile)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(2)

    lbl = QLabel(label.upper())
    lbl.setStyleSheet(
        f"color:{TEXT_MUTED}; font-size:9px; font-weight:bold;"
        f" letter-spacing:0.5px; border:none; background:transparent;"
    )
    val = QLabel("—")
    val.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:22px; font-weight:bold;"
        f" border:none; background:transparent;"
    )
    lay.addWidget(lbl)
    lay.addWidget(val)
    return tile, val


# ── Device Edit Dialog ────────────────────────────────────────────────────────

class _DeviceEditDialog(QDialog):
    """Edit custom_name, room, category, notes for a device."""

    def __init__(self, device_data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Device")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
        form = QFormLayout(self)
        form.setSpacing(8)

        _inp = (
            f"QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:4px 8px;"
            f" font-size:11px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        _cbo = (
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:3px 8px;"
            f" font-size:11px; }}"
        )

        self._name  = QLineEdit(device_data.get("custom_name") or "")
        self._name.setPlaceholderText("e.g. Living Room Hub")
        self._name.setStyleSheet(_inp)

        self._room  = QLineEdit(device_data.get("room") or "")
        self._room.setPlaceholderText("e.g. Living Room")
        self._room.setStyleSheet(_inp)

        self._cat   = QComboBox()
        self._cat.setStyleSheet(_cbo)
        for key, label in _CATEGORIES:
            self._cat.addItem(f"{_CAT_ICON.get(key, '')}  {label}", key)
        cur_cat = device_data.get("category", "unknown")
        for i in range(self._cat.count()):
            if self._cat.itemData(i) == cur_cat:
                self._cat.setCurrentIndex(i)
                break

        self._notes = QPlainTextEdit(device_data.get("notes") or "")
        self._notes.setMaximumHeight(80)
        self._notes.setStyleSheet(
            f"QPlainTextEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:4px;"
            f" font-size:11px; }}"
        )

        form.addRow("Friendly Name:", self._name)
        form.addRow("Room:",          self._room)
        form.addRow("Category:",      self._cat)
        form.addRow("Notes:",         self._notes)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def values(self) -> dict:
        return {
            "custom_name": self._name.text().strip() or None,
            "room":        self._room.text().strip() or None,
            "category":    self._cat.currentData(),
            "notes":       self._notes.toPlainText().strip() or None,
        }


# ── RTT mini-chart for detail panel ──────────────────────────────────────────

class _RttMiniChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fig    = Figure(figsize=(3.5, 1.4), dpi=96, facecolor=BG_CARD)
        self._ax     = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._canvas)
        self._draw_empty()

    def _draw_empty(self) -> None:
        ax = self._ax
        ax.cla()
        ax.set_facecolor("#FAFBFC")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(BORDER)
        ax.spines["bottom"].set_color(BORDER)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
        ax.set_xlabel("", fontsize=0)
        ax.set_ylabel("RTT ms", color=TEXT_SECONDARY, fontsize=8)
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes,
                ha="center", va="center", color=TEXT_MUTED, fontsize=9)
        ax.grid(True, color="#E8EDF2", linewidth=0.6)
        self._fig.tight_layout(pad=0.5)
        self._canvas.draw_idle()

    def plot(self, points: list) -> None:
        """points: list of RttPoint objects."""
        ax = self._ax
        ax.cla()
        ax.set_facecolor("#FAFBFC")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(BORDER)
        ax.spines["bottom"].set_color(BORDER)
        ax.tick_params(colors=TEXT_SECONDARY, labelsize=8)
        ax.set_ylabel("RTT ms", color=TEXT_SECONDARY, fontsize=8)
        ax.grid(True, color="#E8EDF2", linewidth=0.6)

        if not points:
            self._draw_empty()
            return

        ts   = [p.ts for p in points]
        rtts = [p.rtt_ms if p.rtt_ms >= 0 else None for p in points]
        # Normalise timestamps to relative minutes
        t0   = ts[0]
        x    = [(t - t0) / 60 for t in ts]
        y    = [r if r is not None else float("nan") for r in rtts]
        drops = [xi for xi, ri in zip(x, rtts) if ri is None]

        ax.plot(x, y, color=ACCENT, linewidth=1.2)
        if drops:
            ax.scatter(drops, [0] * len(drops), color=RED, marker="x", s=30)

        ax.set_xlabel("Min ago", color=TEXT_SECONDARY, fontsize=8)
        self._fig.tight_layout(pad=0.5)
        self._canvas.draw_idle()


# ── Pinned widget mini-tile ───────────────────────────────────────────────────

class _PinnedTile(QFrame):
    """Small status tile for a pinned HA device."""

    unpin_requested = None  # connected per-instance

    def __init__(self, device: dict, parent=None):
        super().__init__(parent)
        self._mac = device.get("mac", "")
        self.setFixedSize(160, 80)
        self.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-left:3px solid {ACCENT}; border-radius:0; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        name = device.get("custom_name") or device.get("hostname") or device.get("mac", "?")
        self._name_lbl = QLabel(name[:22])
        self._name_lbl.setStyleSheet(
            f"font-size:11px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )

        cat   = device.get("category", "unknown")
        icon  = _CAT_ICON.get(cat, "❓")
        room  = device.get("room") or ""
        self._sub_lbl = QLabel(f"{icon}  {room}" if room else icon)
        self._sub_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_SECONDARY};"
            f" border:none; background:transparent;"
        )

        status = device.get("status", "UNKNOWN")
        color  = _STATUS_COLOR.get(status, TEXT_MUTED)
        self._status_lbl = QLabel(f"● {status}")
        self._status_lbl.setStyleSheet(
            f"font-size:10px; font-weight:bold; color:{color};"
            f" border:none; background:transparent;"
        )

        lay.addWidget(self._name_lbl)
        lay.addWidget(self._sub_lbl)
        lay.addWidget(self._status_lbl)

    def update_status(self, status: str) -> None:
        color = _STATUS_COLOR.get(status, TEXT_MUTED)
        self._status_lbl.setText(f"● {status}")
        self._status_lbl.setStyleSheet(
            f"font-size:10px; font-weight:bold; color:{color};"
            f" border:none; background:transparent;"
        )

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; font-size:11px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; }}"
        )
        unpin = menu.addAction("Unpin from Overview")
        action = menu.exec(event.globalPos())
        if action == unpin and self.unpin_requested:
            self.unpin_requested(self._mac)


# ── Main page ─────────────────────────────────────────────────────────────────

class HomeAutomationPage(QWidget):
    """
    Home Automation Hub — discover, label, and monitor HA devices.
    """

    def __init__(self, store=None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._store = store
        self._devices: List[dict] = []        # cached rows for table display
        self._pinned_tiles: Dict[str, _PinnedTile] = {}
        self._ha_worker   = None
        self._mac_worker  = None
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(120_000)   # 2-min auto-refresh
        self._refresh_timer.timeout.connect(self._load_devices)

        self._setup_ui()
        self._load_devices()
        self._refresh_timer.start()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Page header
        title = QLabel("Home Automation Hub")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
            f" background:transparent; border:none;"
        )
        sub = QLabel(
            "Discover, label and monitor smart home devices on your network"
        )
        sub.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none; padding:0 0 4px 0;"
        )
        root.addWidget(title)
        root.addWidget(sub)

        # ── KPI row ───────────────────────────────────────────────────────────
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_total,    self._lbl_total    = _kpi_tile("Total Devices",    ACCENT)
        self._kpi_online,   self._lbl_online   = _kpi_tile("Online Now",       GREEN)
        self._kpi_offline,  self._lbl_offline  = _kpi_tile("Offline",          RED)
        self._kpi_detected, self._lbl_detected = _kpi_tile("Auto-Detected",    AMBER)
        for tile in (self._kpi_total, self._kpi_online,
                     self._kpi_offline, self._kpi_detected):
            kpi_row.addWidget(tile, 1)
        root.addLayout(kpi_row)

        # ── Filter / action row ───────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        cbo_style = (
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:4px 8px;"
            f" font-size:11px; min-height:26px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
        )
        inp_style = (
            f"QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:4px 8px;"
            f" font-size:11px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )

        self._room_filter = QComboBox()
        self._room_filter.setStyleSheet(cbo_style)
        self._room_filter.setMinimumWidth(130)
        self._room_filter.addItem("All Rooms", None)
        self._room_filter.currentIndexChanged.connect(self._apply_filters)

        self._cat_filter  = QComboBox()
        self._cat_filter.setStyleSheet(cbo_style)
        self._cat_filter.setMinimumWidth(150)
        self._cat_filter.addItem("All Categories", None)
        for key, label in _CATEGORIES[:-1]:   # exclude 'unknown'
            self._cat_filter.addItem(f"{_CAT_ICON.get(key, '')}  {label}", key)
        self._cat_filter.currentIndexChanged.connect(self._apply_filters)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search name, IP, MAC…")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setStyleSheet(inp_style)
        self._search_box.textChanged.connect(self._apply_filters)

        btn_scan = QPushButton("🔍  Scan Network")
        btn_scan.setObjectName("btnScan")
        btn_scan.setFixedHeight(30)
        btn_scan.setToolTip("Scan all known devices for HA protocol signatures")
        btn_scan.clicked.connect(self._run_ha_scan)

        btn_add = QPushButton("＋  Add Device")
        btn_add.setObjectName("btnNetRefresh")
        btn_add.setFixedHeight(30)
        btn_add.setToolTip("Pre-register a device by MAC address")
        btn_add.clicked.connect(self._add_device_dialog)

        filter_row.addWidget(QLabel("Room:"))
        filter_row.addWidget(self._room_filter)
        filter_row.addWidget(QLabel("Category:"))
        filter_row.addWidget(self._cat_filter)
        filter_row.addWidget(self._search_box, 1)
        filter_row.addWidget(btn_scan)
        filter_row.addWidget(btn_add)
        root.addLayout(filter_row)

        # ── Status label ──────────────────────────────────────────────────────
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            f" background:transparent; border:none;"
        )
        root.addWidget(self._status_lbl)

        # ── Main splitter: device table | detail panel ────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background:{BORDER}; width:1px; }}"
        )

        # Device table
        tbl_card, tbl_body = _card("Devices")
        self._tbl = QTableWidget(0, 7)
        self._tbl.setHorizontalHeaderLabels([
            "Status", "Name", "Room", "Category", "IP", "MAC / Vendor", "Last Seen",
        ])
        self._tbl.horizontalHeader().setStretchLastSection(True)
        self._tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setShowGrid(True)
        self._tbl.verticalHeader().setDefaultSectionSize(24)
        self._tbl.setColumnWidth(0, 55)
        self._tbl.setColumnWidth(2, 100)
        self._tbl.setColumnWidth(3, 120)
        self._tbl.setColumnWidth(4, 110)
        self._tbl.setColumnWidth(5, 160)
        self._tbl.setColumnWidth(6, 120)
        self._tbl.setStyleSheet(
            f"QTableWidget {{ border:none; font-size:11px; color:{TEXT_PRIMARY}; }}"
            f"QHeaderView::section {{"
            f"  background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
            f"  font-weight:bold; padding:4px 5px; border:none;"
            f"  border-right:1px solid #254A6E;"
            f"}}"
            f"QTableWidget::item:selected {{ background:#CCE4F7; color:{TEXT_PRIMARY}; }}"
            f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
            f"QTableWidget::item {{ border-bottom:1px solid #EAEAEA; }}"
        )
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._context_menu)
        self._tbl.selectionModel().currentRowChanged.connect(
            lambda cur, _prev: self._on_row_selected(cur.row())
        )
        tbl_body.addWidget(self._tbl)
        splitter.addWidget(tbl_card)

        # Detail panel
        self._detail_panel = self._build_detail_panel()
        splitter.addWidget(self._detail_panel)
        splitter.setSizes([620, 340])

        root.addWidget(splitter, 3)

        # ── Pinned widget strip ───────────────────────────────────────────────
        pin_card, pin_body = _card("Pinned Devices (Overview Widgets)")
        pin_body.setContentsMargins(8, 8, 8, 8)

        self._pin_scroll = QScrollArea()
        self._pin_scroll.setWidgetResizable(True)
        self._pin_scroll.setFixedHeight(96)
        self._pin_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._pin_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._pin_scroll.setStyleSheet(
            f"QScrollArea {{ border:none; background:{BG_DARK}; }}"
        )

        self._pin_container = QWidget()
        self._pin_container.setStyleSheet(f"background:{BG_DARK};")
        self._pin_layout = QHBoxLayout(self._pin_container)
        self._pin_layout.setContentsMargins(0, 4, 0, 4)
        self._pin_layout.setSpacing(8)
        self._pin_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self._pin_empty_lbl = QLabel(
            "No pinned devices yet — right-click a device → Pin to Overview"
        )
        self._pin_empty_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
        )
        self._pin_layout.addWidget(self._pin_empty_lbl)

        self._pin_scroll.setWidget(self._pin_container)
        pin_body.addWidget(self._pin_scroll)
        root.addWidget(pin_card)

    def _build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-left:3px solid {BORDER}; }}"
        )
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self._det_name = QLabel("Select a device")
        self._det_name.setStyleSheet(
            f"font-size:14px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" border:none; background:transparent;"
        )
        self._det_name.setWordWrap(True)

        self._det_status = QLabel("")
        self._det_status.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; border:none; background:transparent;"
        )

        self._det_meta = QLabel("")
        self._det_meta.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:none; background:transparent;"
        )
        self._det_meta.setWordWrap(True)

        self._rtt_chart = _RttMiniChart()

        btn_row = QHBoxLayout()
        self._btn_edit = QPushButton("✏  Edit")
        self._btn_edit.setObjectName("btnNetRefresh")
        self._btn_edit.setFixedHeight(26)
        self._btn_edit.clicked.connect(self._edit_selected)

        self._btn_pin = QPushButton("📌  Pin to Overview")
        self._btn_pin.setObjectName("btnNetRefresh")
        self._btn_pin.setFixedHeight(26)
        self._btn_pin.clicked.connect(self._pin_selected)

        self._btn_lookup = QPushButton("🔍  Look up MAC")
        self._btn_lookup.setObjectName("btnNetRefresh")
        self._btn_lookup.setFixedHeight(26)
        self._btn_lookup.setToolTip("Look up vendor for this MAC address online")
        self._btn_lookup.clicked.connect(self._lookup_mac)

        btn_row.addWidget(self._btn_edit)
        btn_row.addWidget(self._btn_pin)
        btn_row.addWidget(self._btn_lookup)
        btn_row.addStretch()

        lay.addWidget(self._det_name)
        lay.addWidget(self._det_status)
        lay.addWidget(self._det_meta)
        lay.addWidget(self._rtt_chart)
        lay.addLayout(btn_row)
        lay.addStretch()

        return panel

    # ── Device loading ────────────────────────────────────────────────────────

    def _load_devices(self) -> None:
        """Load all HA-categorised devices from MetricStore."""
        if not self._store:
            self._set_status("No database — run a scan to populate devices")
            return
        try:
            devices = self._store.query_ha_devices()
            self._devices = [self._kd_to_dict(d) for d in devices]
        except Exception as exc:
            self._set_status(f"⚠  {exc}")
            self._devices = []

        self._rebuild_filters()
        self._populate_table(self._devices)
        self._update_kpis()
        self._rebuild_pins()

    def _kd_to_dict(self, kd) -> dict:
        """Convert KnownDevice to a plain dict for table/UI use."""
        return {
            "mac":         kd.mac,
            "ip":          kd.ip or "",
            "hostname":    kd.hostname or "",
            "vendor":      kd.vendor or "",
            "device_type": kd.device_type or "",
            "custom_name": kd.custom_name or "",
            "room":        kd.room or "",
            "category":    kd.category,
            "notes":       kd.notes or "",
            "is_pinned":   kd.is_pinned,
            "first_seen":  kd.first_seen,
            "last_seen":   kd.last_seen,
            "status":      "UNKNOWN",   # refreshed separately
        }

    def _rebuild_filters(self) -> None:
        """Repopulate room combo box from current device list."""
        rooms = sorted({d["room"] for d in self._devices if d["room"]})
        cur_room = self._room_filter.currentData()
        self._room_filter.blockSignals(True)
        self._room_filter.clear()
        self._room_filter.addItem("All Rooms", None)
        for r in rooms:
            self._room_filter.addItem(r, r)
        # Restore selection
        for i in range(self._room_filter.count()):
            if self._room_filter.itemData(i) == cur_room:
                self._room_filter.setCurrentIndex(i)
                break
        self._room_filter.blockSignals(False)

    def _populate_table(self, devices: List[dict]) -> None:
        self._tbl.setRowCount(0)
        for d in devices:
            row = self._tbl.rowCount()
            self._tbl.insertRow(row)

            status = d.get("status", "UNKNOWN")
            sc = _STATUS_COLOR.get(status, TEXT_MUTED)
            status_item = QTableWidgetItem(f"●  {status}")
            status_item.setForeground(QColor(sc))

            name = d.get("custom_name") or d.get("hostname") or d.get("mac", "?")
            cat  = d.get("category", "unknown")
            icon = _CAT_ICON.get(cat, "❓")
            last = ""
            if d.get("last_seen"):
                try:
                    last = datetime.datetime.fromtimestamp(
                        d["last_seen"]
                    ).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass

            vendor_str = d.get("vendor") or d.get("device_type") or ""
            mac_str    = d.get("mac", "")
            mac_vendor = f"{mac_str}" + (f"  {vendor_str}" if vendor_str else "")

            cells = [
                status_item,
                QTableWidgetItem(("📌 " if d.get("is_pinned") else "") + name),
                QTableWidgetItem(d.get("room", "")),
                QTableWidgetItem(f"{icon}  {_CAT_DISPLAY.get(cat, cat)}"),
                QTableWidgetItem(d.get("ip", "")),
                QTableWidgetItem(mac_vendor),
                QTableWidgetItem(last),
            ]
            cells[0] = status_item
            for col in range(1, len(cells)):
                self._tbl.setItem(row, col, cells[col])
            self._tbl.setItem(row, 0, status_item)

            # Store MAC in row data for lookup
            self._tbl.item(row, 0).setData(Qt.ItemDataRole.UserRole, d.get("mac", ""))

    def _update_kpis(self) -> None:
        total   = len(self._devices)
        online  = sum(1 for d in self._devices if d.get("status") == "UP")
        offline = sum(1 for d in self._devices if d.get("status") == "DOWN")
        self._lbl_total.setText(str(total))
        self._lbl_online.setText(str(online))
        self._lbl_offline.setText(str(offline))
        # Detected = devices with a non-manual category
        detected = sum(
            1 for d in self._devices if d.get("category", "unknown") != "unknown"
        )
        self._lbl_detected.setText(str(detected))

    # ── Filtering ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _apply_filters(self) -> None:
        room_filter = self._room_filter.currentData()
        cat_filter  = self._cat_filter.currentData()
        text        = self._search_box.text().strip().lower()

        for row in range(self._tbl.rowCount()):
            d = self._devices[row] if row < len(self._devices) else {}
            hide = False
            if room_filter and d.get("room") != room_filter:
                hide = True
            if cat_filter and d.get("category") != cat_filter:
                hide = True
            if text:
                searchable = " ".join([
                    d.get("custom_name", ""), d.get("hostname", ""),
                    d.get("ip", ""), d.get("mac", ""), d.get("vendor", ""),
                    d.get("room", ""),
                ]).lower()
                if text not in searchable:
                    hide = True
            self._tbl.setRowHidden(row, hide)

    # ── Detail panel ──────────────────────────────────────────────────────────

    @pyqtSlot(int)
    def _on_row_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._devices):
            return
        d = self._devices[row]
        name = d.get("custom_name") or d.get("hostname") or d.get("mac", "?")
        self._det_name.setText(name)

        status = d.get("status", "UNKNOWN")
        sc = _STATUS_COLOR.get(status, TEXT_MUTED)
        self._det_status.setText(f"● {status}")
        self._det_status.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:{sc};"
            f" border:none; background:transparent;"
        )

        meta_parts = []
        if d.get("ip"):       meta_parts.append(f"IP: {d['ip']}")
        if d.get("mac"):      meta_parts.append(f"MAC: {d['mac']}")
        if d.get("vendor"):   meta_parts.append(f"Vendor: {d['vendor']}")
        if d.get("room"):     meta_parts.append(f"Room: {d['room']}")
        if d.get("notes"):    meta_parts.append(f"Notes: {d['notes']}")
        self._det_meta.setText("\n".join(meta_parts))

        # Load RTT history
        if self._store and d.get("ip"):
            try:
                pts = self._store.query_rtt_history(d["ip"], hours=24)
                self._rtt_chart.plot(pts)
            except Exception:
                self._rtt_chart._draw_empty()

    # ── Actions ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _edit_selected(self) -> None:
        row = self._tbl.currentRow()
        if row < 0 or row >= len(self._devices):
            return
        self._open_edit_dialog(self._devices[row])

    def _open_edit_dialog(self, device: dict) -> None:
        dlg = _DeviceEditDialog(device, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        vals = dlg.values()
        mac = device.get("mac", "")
        if self._store and mac:
            try:
                self._store.update_device_ha_info(mac=mac, **vals)
            except Exception as exc:
                self._set_status(f"⚠  Save failed: {exc}")
                return
        # Update local cache
        device.update(vals)
        self._rebuild_filters()
        self._populate_table(self._devices)
        self._update_kpis()
        self._rebuild_pins()

    @pyqtSlot()
    def _pin_selected(self) -> None:
        row = self._tbl.currentRow()
        if row < 0 or row >= len(self._devices):
            return
        d = self._devices[row]
        mac = d.get("mac", "")
        new_pinned = not d.get("is_pinned", False)
        if self._store and mac:
            try:
                self._store.update_device_ha_info(mac=mac, is_pinned=new_pinned)
            except Exception:
                pass
        d["is_pinned"] = new_pinned
        self._populate_table(self._devices)
        self._rebuild_pins()
        self._btn_pin.setText("📌  Unpin" if new_pinned else "📌  Pin to Overview")

    @pyqtSlot()
    def _lookup_mac(self) -> None:
        row = self._tbl.currentRow()
        if row < 0 or row >= len(self._devices):
            return
        mac = self._devices[row].get("mac", "")
        if not mac:
            return
        self._set_status(f"Looking up {mac} online…")
        from workers.ha_worker import MacLookupWorker
        self._mac_worker = MacLookupWorker(mac, parent=self)
        self._mac_worker.result_ready.connect(self._on_mac_lookup_done)
        self._mac_worker.error.connect(lambda e: self._set_status(f"⚠  {e}"))
        self._mac_worker.start()

    @pyqtSlot(str, str)
    def _on_mac_lookup_done(self, mac: str, vendor: str) -> None:
        if vendor:
            self._set_status(f"✓  {mac} → {vendor}")
            # Persist vendor to DB
            if self._store:
                try:
                    self._store.upsert_known_device(mac=mac, vendor=vendor)
                except Exception:
                    pass
            # Update local cache
            for d in self._devices:
                if d.get("mac") == mac:
                    d["vendor"] = vendor
                    break
            self._populate_table(self._devices)
        else:
            self._set_status(f"⚠  No vendor found for {mac}")

    @pyqtSlot()
    def _run_ha_scan(self) -> None:
        from workers.ha_worker import HaScanWorker

        if self._ha_worker and self._ha_worker.isRunning():
            return

        # Build host list from all known devices + current HA devices
        hosts = [{"ip": d["ip"], "mac": d["mac"]}
                 for d in self._devices if d.get("ip")]
        if not hosts and self._store:
            try:
                all_dev = self._store.get_known_devices()
                hosts = [
                    {"ip": kd.ip, "mac": kd.mac}
                    for kd in all_dev.values() if kd.ip
                ]
            except Exception:
                pass

        if not hosts:
            self._set_status("No known devices to scan — run a device scan first")
            return

        self._set_status(f"Scanning {len(hosts)} hosts for HA signatures…")
        self._ha_worker = HaScanWorker(hosts, parent=self)
        self._ha_worker.status.connect(self._set_status)
        self._ha_worker.results_ready.connect(self._on_ha_scan_done)
        self._ha_worker.error.connect(lambda e: self._set_status(f"⚠  {e}"))
        self._ha_worker.start()

    @pyqtSlot(list)
    def _on_ha_scan_done(self, matches: list) -> None:
        from modules.ha_detector import ha_category

        count = len(matches)
        self._set_status(f"✓  HA scan complete — {count} signature(s) found")

        for match in matches:
            # Record in DB
            if self._store:
                try:
                    self._store.record_ha_detected(
                        ip=match.ip, mac=match.mac,
                        ha_type=match.ha_type,
                        confidence=match.confidence,
                        detail=match.detail,
                    )
                    # Auto-categorise + upsert the device
                    if match.mac:
                        self._store.upsert_known_device(
                            mac=match.mac, ip=match.ip,
                            device_type=match.label,
                        )
                        self._store.update_device_ha_info(
                            mac=match.mac,
                            category=ha_category(match.ha_type),
                        )
                except Exception:
                    pass

        self._load_devices()

    def _add_device_dialog(self) -> None:
        """Pre-register a device by MAC address (not yet on network)."""
        import re
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Device Manually")
        dlg.setMinimumWidth(380)
        dlg.setStyleSheet(f"background:{BG_DARK}; color:{TEXT_PRIMARY};")
        form = QFormLayout(dlg)
        form.setSpacing(8)

        _inp = (
            f"QLineEdit {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:4px 8px;"
            f" font-size:11px; }}"
        )
        mac_edit  = QLineEdit(); mac_edit.setPlaceholderText("aa:bb:cc:dd:ee:ff")
        mac_edit.setStyleSheet(_inp)
        name_edit = QLineEdit(); name_edit.setPlaceholderText("Friendly name")
        name_edit.setStyleSheet(_inp)
        room_edit = QLineEdit(); room_edit.setPlaceholderText("e.g. Kitchen")
        room_edit.setStyleSheet(_inp)
        cat_cbo   = QComboBox()
        cat_cbo.setStyleSheet(
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px; padding:3px 8px;"
            f" font-size:11px; }}"
        )
        for key, label in _CATEGORIES:
            cat_cbo.addItem(f"{_CAT_ICON.get(key, '')}  {label}", key)

        form.addRow("MAC Address:", mac_edit)
        form.addRow("Name:",        name_edit)
        form.addRow("Room:",        room_edit)
        form.addRow("Category:",    cat_cbo)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        mac = mac_edit.text().strip()
        if not re.fullmatch(
            r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", mac
        ):
            self._set_status("⚠  Invalid MAC address format")
            return

        if self._store:
            import time as _t
            try:
                self._store.upsert_known_device(mac=mac.lower())
                self._store.update_device_ha_info(
                    mac=mac.lower(),
                    custom_name=name_edit.text().strip() or None,
                    room=room_edit.text().strip() or None,
                    category=cat_cbo.currentData(),
                )
            except Exception as exc:
                self._set_status(f"⚠  {exc}")
                return

        self._set_status(f"✓  Device {mac} added")
        self._load_devices()

    # ── Context menu ──────────────────────────────────────────────────────────

    def _context_menu(self, pos) -> None:
        row = self._tbl.rowAt(pos.y())
        if row < 0 or row >= len(self._devices):
            return
        d = self._devices[row]

        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; font-size:11px; padding:4px; }}"
            f"QMenu::item {{ padding:5px 20px; }}"
            f"QMenu::item:selected {{ background:{BG_HOVER}; }}"
        )
        act_edit   = menu.addAction("✏  Edit Device…")
        pin_label  = "📌  Unpin from Overview" if d.get("is_pinned") else "📌  Pin to Overview"
        act_pin    = menu.addAction(pin_label)
        menu.addSeparator()
        act_lookup = menu.addAction("🌐  Look Up MAC Online")
        act_copy_ip  = menu.addAction("Copy IP")
        act_copy_mac = menu.addAction("Copy MAC")

        action = menu.exec(self._tbl.viewport().mapToGlobal(pos))
        if action == act_edit:
            self._open_edit_dialog(d)
        elif action == act_pin:
            self._tbl.setCurrentRow(row)
            self._pin_selected()
        elif action == act_lookup:
            self._tbl.setCurrentRow(row)
            self._lookup_mac()
        elif action == act_copy_ip:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(d.get("ip", ""))
        elif action == act_copy_mac:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(d.get("mac", ""))

    # ── Pinned widget strip ───────────────────────────────────────────────────

    def _rebuild_pins(self) -> None:
        pinned = [d for d in self._devices if d.get("is_pinned")]

        # Remove existing tiles no longer pinned
        for mac in list(self._pinned_tiles):
            if not any(d.get("mac") == mac for d in pinned):
                tile = self._pinned_tiles.pop(mac)
                self._pin_layout.removeWidget(tile)
                tile.deleteLater()

        # Add new tiles
        for d in pinned:
            mac = d.get("mac", "")
            if mac not in self._pinned_tiles:
                tile = _PinnedTile(d, parent=self._pin_container)
                tile.unpin_requested = self._unpin_device
                self._pinned_tiles[mac] = tile
                self._pin_layout.addWidget(tile)
            else:
                self._pinned_tiles[mac].update_status(d.get("status", "UNKNOWN"))

        self._pin_empty_lbl.setVisible(len(pinned) == 0)

    def _unpin_device(self, mac: str) -> None:
        if self._store and mac:
            try:
                self._store.update_device_ha_info(mac=mac, is_pinned=False)
            except Exception:
                pass
        for d in self._devices:
            if d.get("mac") == mac:
                d["is_pinned"] = False
        self._populate_table(self._devices)
        self._rebuild_pins()

    # ── Public: called by availability worker when a cycle completes ──────────

    def on_availability_update(self, states: dict) -> None:
        """
        states: {ip: "UP" | "DOWN" | "DEGRADED"}
        Called from the dashboard when the availability monitor fires.
        """
        ip_to_status = {ip: s for ip, s in states.items()}
        for d in self._devices:
            d["status"] = ip_to_status.get(d.get("ip", ""), "UNKNOWN")
        self._populate_table(self._devices)
        self._update_kpis()
        self._rebuild_pins()

    # ── Status helper ─────────────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._status_lbl.setText(text)
