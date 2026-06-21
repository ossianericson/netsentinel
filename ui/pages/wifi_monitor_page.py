"""
WiFiMonitorPage — passive 802.11 monitor mode capture.

Puts a supported NIC into monitor mode via Npcap and reads raw
802.11 management frames (beacons, probe requests/responses, auth,
association, deauth).  No frames are transmitted — purely passive.
Falls back silently if monitor mode is unsupported on the adapter.
Power-user feature.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.npcap_banner import NpcapMissingBanner
from ui.styles import (
    ACCENT, AMBER, BORDER, GREEN, RED,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_TEXT,
)
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard


class WiFiMonitorPage(QWidget):
    """Passive 802.11 monitor mode capture page."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._worker = None
        self._build_ui()
        self._populate_interfaces()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(8)

        lay.addWidget(NpcapMissingBanner(parent=self))

        title = QLabel("Passive 802.11 Monitor")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:16px;font-weight:bold;padding:4px 0;"
        )
        lay.addWidget(title)

        desc = QLabel(
            "Puts a supported NIC into monitor mode via Npcap and reads raw "
            "802.11 management frames — beacons, probe requests/responses, "
            "authentication, association, and deauth frames.  "
            "No packets are transmitted; this is a purely passive capture.  "
            "Requires a Npcap-compatible wireless adapter with monitor mode support."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:11px;padding:2px 0 6px 0;"
        )
        lay.addWidget(desc)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)
        ctrl.addWidget(QLabel("Interface:"))
        self._iface_combo = QComboBox()
        self._iface_combo.setMinimumWidth(280)
        self._iface_combo.setToolTip("Select the wireless interface to capture on")
        ctrl.addWidget(self._iface_combo)
        self._btn_start = QPushButton("▶  Start Capture")
        self._btn_start.setObjectName("btnScan")
        self._btn_stop = QPushButton("⏹  Stop")
        self._btn_stop.setObjectName("btnNetRefresh")
        self._btn_stop.setEnabled(False)
        self._btn_start.clicked.connect(self._start)
        self._btn_stop.clicked.connect(self._stop)
        ctrl.addWidget(self._btn_start)
        ctrl.addWidget(self._btn_stop)
        ctrl.addStretch()
        lay.addLayout(ctrl)

        self._status_lbl = QLabel(
            "Ready — select an interface and click Start Capture."
        )
        self._status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        lay.addWidget(self._status_lbl)

        # ── Content stack: page 0 = empty state, page 1 = frame table ───────────
        self._capture_stack = QStackedWidget()

        # Page 0 — empty state
        _empty = EmptyStateCard(
            icon="◆",
            title="No frames captured yet",
            what_it_shows=(
                "Raw 802.11 management frames — beacons, probe requests, "
                "authentication and deauth frames from nearby wireless devices."
            ),
            why_it_matters=(
                "Passive capture reveals hidden SSIDs, rogue access points, "
                "and deauth attacks without transmitting any traffic."
            ),
            btn_label="Start Monitoring →",
        )
        _empty.clicked.connect(self._start)
        self._capture_stack.addWidget(_empty)

        # Page 1 — frame table + footer
        _table_page = QWidget()
        _tlay = QVBoxLayout(_table_page)
        _tlay.setContentsMargins(0, 0, 0, 0)
        _tlay.setSpacing(4)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Time", "Frame Type", "Source MAC", "SSID", "Destination"]
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setColumnWidth(0, 72)
        self._table.setColumnWidth(1, 140)
        self._table.setColumnWidth(2, 160)
        self._table.setColumnWidth(3, 200)
        self._table.setStyleSheet(
            f"QTableWidget{{border:1px solid {BORDER};font-size:11px;"
            f"color:{TEXT_PRIMARY};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{TH_TEXT};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
        )
        def _wm_filter_bssid():
            r = self._table.currentRow()
            if r < 0:
                return
            src_item = self._table.item(r, 2)
            if src_item is None:
                return
            bssid = src_item.text()
            for row in range(self._table.rowCount()):
                it = self._table.item(row, 2)
                self._table.setRowHidden(row, it is None or it.text() != bssid)

        install_copy_menu(self._table, [
            ("separator",      None),
            ("Filter by BSSID", _wm_filter_bssid),
        ])
        _tlay.addWidget(self._table, 1)

        bottom = QHBoxLayout()
        self._frame_count_lbl = QLabel("0 frames captured")
        self._frame_count_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:10px;"
        )
        bottom.addWidget(self._frame_count_lbl)
        bottom.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(70)
        clear_btn.clicked.connect(self._clear)
        bottom.addWidget(clear_btn)
        _tlay.addLayout(bottom)

        self._capture_stack.addWidget(_table_page)
        lay.addWidget(self._capture_stack, 1)

    def _populate_interfaces(self) -> None:
        from workers.wifi_monitor_worker import WiFiMonitorWorker
        ifaces = WiFiMonitorWorker.list_interfaces()
        if ifaces:
            self._iface_combo.addItems(ifaces)
        else:
            self._iface_combo.addItem("(no interfaces found)")
            self._btn_start.setEnabled(False)

    # ── Actions ───────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _start(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        from workers.wifi_monitor_worker import WiFiMonitorWorker
        iface = self._iface_combo.currentText()
        self._worker = WiFiMonitorWorker(iface=iface, parent=None)
        self._worker.frame_captured.connect(self._on_frame)
        self._worker.status.connect(self._on_status)
        self._worker.error.connect(self._on_error)
        self._worker.unsupported.connect(self._on_unsupported)
        self._worker.start()
        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._set_status(f"Starting monitor mode on {iface}…", GREEN)

    @pyqtSlot()
    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker.wait(2000)
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._set_status("Capture stopped.", TEXT_SECONDARY)

    @pyqtSlot()
    def _clear(self) -> None:
        self._table.setRowCount(0)
        self._frame_count_lbl.setText("0 frames captured")

    # ── Slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot(dict)
    def _on_frame(self, f: dict) -> None:
        if self._capture_stack.currentIndex() == 0:
            self._capture_stack.setCurrentIndex(1)
        row = self._table.rowCount()
        if row >= 5000:
            self._table.removeRow(0)
            row -= 1
        self._table.insertRow(row)
        for col, val in enumerate(
            [f["ts"], f["frame_type"], f["src"], f["ssid"], f["dst"]]
        ):
            self._table.setItem(row, col, QTableWidgetItem(str(val)))
        self._table.scrollToBottom()
        self._frame_count_lbl.setText(
            f"{self._table.rowCount()} frames captured"
        )

    @pyqtSlot(str)
    def _on_status(self, msg: str) -> None:
        self._set_status(msg, GREEN)

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._set_status(f"⚠ {msg}", RED)

    @pyqtSlot(str)
    def _on_unsupported(self, msg: str) -> None:
        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._set_status(f"ℹ {msg}", AMBER)

    def _set_status(self, msg: str, color: str) -> None:
        self._status_lbl.setStyleSheet(f"color:{color};font-size:11px;")
        self._status_lbl.setText(msg)
