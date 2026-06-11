"""
ServiceDiagnosticsPage — diagnose whether a streaming/gaming service is reachable
from this network and identify the failure layer (Sprint 4).

Layout
------
  Control bar — service picker, traceroute toggle, Run Diagnostics button
  QStackedWidget:
    page 0 — empty state with inline CTA
    page 1 — summary card (failure layer + confidence) + 4-layer details table
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.metric_store import MetricStore
from modules.service_diagnostics import SERVICE_CATALOG, ServiceDiagnosticResult
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE,
    AMBER,
    BG_ALT_ROW, BG_CARD, BG_DARK,
    BORDER, CARD_HDR_BORDER, CARD_RADIUS,
    GREEN, RED, TABLE_ROW_BORDER, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TH_BG, TH_TEXT, WHITE,
)
from ui.widgets.context_menu import install_copy_menu
from workers.service_diagnostics_worker import ServiceDiagnosticsWorker


# ── Layer display helpers ─────────────────────────────────────────────────────

_LAYER_LABELS = {
    "none":           ("All layers OK", GREEN),
    "device":         ("Device problem", RED),
    "local_network":  ("Local network", RED),
    "dns":            ("DNS failure", AMBER),
    "isp":            ("ISP issue", AMBER),
    "routing":        ("Routing problem", AMBER),
    "remote_outage":  ("Remote outage", AMBER),
}

_STREAMING_IDS = {
    s.id for s in __import__("modules.service_diagnostics", fromlist=["_STREAMING"])._STREAMING
}


def _layer_badge(failure_layer: str) -> tuple[str, str]:
    """Return (label, colour) for a failure layer string."""
    return _LAYER_LABELS.get(failure_layer, (failure_layer, TEXT_SECONDARY))


def _ts_label(ts: int) -> str:
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%H:%M:%S")
    except Exception:
        return "—"


# ── Page ──────────────────────────────────────────────────────────────────────

class ServiceDiagnosticsPage(QWidget):
    """Diagnose streaming and gaming service connectivity."""

    # Emitted when the page wants the dashboard to run a full scan
    scan_requested = pyqtSignal()

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store   = store
        self._worker: Optional[ServiceDiagnosticsWorker] = None
        self._last_result: Optional[ServiceDiagnosticResult] = None
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        root.addWidget(self._build_control_card())

        self._status_lbl = QLabel("Select a service and click Run Diagnostics.")
        self._status_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_empty_state())
        self._stack.addWidget(self._build_results_scroll())

        root.addWidget(self._status_lbl)
        root.addWidget(self._stack, 1)

    def _build_control_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)

        lbl = QLabel("Service:")
        lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-weight:600; border:none;")
        lay.addWidget(lbl)

        self._service_combo = QComboBox()
        self._service_combo.setMinimumWidth(200)
        self._populate_service_picker()
        lay.addWidget(self._service_combo)

        self._traceroute_chk = QCheckBox("Include traceroute")
        self._traceroute_chk.setToolTip(
            "Adds path analysis (~30 s extra). Shows each network hop to the service."
        )
        self._traceroute_chk.setStyleSheet(f"color:{TEXT_PRIMARY}; border:none;")
        lay.addWidget(self._traceroute_chk)

        lay.addStretch()

        self._run_btn = QPushButton("Run Diagnostics")
        self._run_btn.setFixedHeight(32)
        self._run_btn.clicked.connect(self._on_run_clicked)
        self._run_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f"border-radius:4px; padding:0 16px; font-weight:600; }}"
            f"QPushButton:hover   {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
            f"QPushButton:disabled {{ background:{BORDER}; color:{TEXT_MUTED}; }}"
        )
        lay.addWidget(self._run_btn)

        return card

    def _populate_service_picker(self) -> None:
        streaming_entries = sorted(
            (e for e in SERVICE_CATALOG.values() if e.category == "streaming"),
            key=lambda e: e.name,
        )
        gaming_entries = sorted(
            (e for e in SERVICE_CATALOG.values() if e.category == "gaming"),
            key=lambda e: e.name,
        )
        for entry in streaming_entries:
            self._service_combo.addItem(f"{entry.name}  (Streaming)", entry.id)
        for entry in gaming_entries:
            self._service_combo.addItem(f"{entry.name}  (Gaming)", entry.id)

    def _build_empty_state(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.setSpacing(12)

        icon_lbl = QLabel("◎")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:48px;")

        title_lbl = QLabel("Select a service and run diagnostics")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:16px; font-weight:600;"
        )

        sub_lbl = QLabel(
            "NetSentinel will probe DNS, TCP reachability, latency, and (optionally)\n"
            "the network path to identify where any failure is occurring."
        )
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:12px;")

        lay.addWidget(icon_lbl)
        lay.addWidget(title_lbl)
        lay.addWidget(sub_lbl)
        return w

    def _build_results_scroll(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background:{BG_DARK};")

        container = QWidget()
        container.setStyleSheet(f"background:{BG_DARK};")
        vlay = QVBoxLayout(container)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(10)

        self._summary_card = self._build_summary_card()
        self._layers_card  = self._build_layers_card()

        vlay.addWidget(self._summary_card)
        vlay.addWidget(self._layers_card)
        vlay.addStretch()

        scroll.setWidget(container)
        return scroll

    def _build_summary_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS}; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        # Header row
        hdr = QHBoxLayout()
        self._sum_service_lbl = QLabel("—")
        self._sum_service_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:15px; font-weight:700; border:none;"
        )
        hdr.addWidget(self._sum_service_lbl)
        hdr.addStretch()
        self._sum_ts_lbl = QLabel("")
        self._sum_ts_lbl.setStyleSheet(f"color:{TEXT_MUTED}; font-size:11px; border:none;")
        hdr.addWidget(self._sum_ts_lbl)
        lay.addLayout(hdr)

        # Layer badge row
        badge_row = QHBoxLayout()
        self._sum_badge = QLabel("—")
        self._sum_badge.setFixedHeight(24)
        self._sum_badge.setStyleSheet(
            f"border-radius:4px; padding:2px 10px; font-size:12px;"
            f"font-weight:600; color:{WHITE}; background:{TEXT_MUTED};"
        )
        badge_row.addWidget(self._sum_badge)

        self._sum_conf_lbl = QLabel("")
        self._sum_conf_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:12px; border:none;"
        )
        badge_row.addWidget(self._sum_conf_lbl)
        badge_row.addStretch()
        lay.addLayout(badge_row)

        # Summary text
        self._sum_text = QLabel("")
        self._sum_text.setWordWrap(True)
        self._sum_text.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; border:none;"
        )
        lay.addWidget(self._sum_text)

        return card

    def _build_layers_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f"border-radius:{CARD_RADIUS}; }}"
        )
        vlay = QVBoxLayout(card)
        vlay.setContentsMargins(0, 0, 0, 0)
        vlay.setSpacing(0)

        # Card header
        hdr = QFrame()
        hdr.setFixedHeight(32)
        hdr.setStyleSheet(
            f"background:{TH_BG}; border-radius:{CARD_RADIUS} {CARD_RADIUS} 0 0;"
            f"border-bottom:1px solid {CARD_HDR_BORDER};"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(12, 0, 12, 0)
        hdr_lbl = QLabel("Diagnostic Layers")
        hdr_lbl.setStyleSheet(
            f"color:{TH_TEXT}; font-weight:700; font-size:12px; border:none;"
        )
        hdr_lay.addWidget(hdr_lbl)
        vlay.addWidget(hdr)

        # Layers table
        self._layers_table = QTableWidget(4, 3)
        self._layers_table.setHorizontalHeaderLabels(["Layer", "Status", "Details"])
        self._layers_table.verticalHeader().setVisible(False)
        self._layers_table.verticalHeader().setDefaultSectionSize(24)
        self._layers_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._layers_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._layers_table.setAlternatingRowColors(True)
        self._layers_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._layers_table.setColumnWidth(0, 120)
        self._layers_table.setColumnWidth(1, 80)
        self._layers_table.setStyleSheet(
            f"QTableWidget {{ border:none; background:{BG_CARD}; "
            f"alternate-background-color:{BG_ALT_ROW}; gridline-color:{TABLE_ROW_BORDER}; }}"
            f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; "
            f"border:none; padding:4px 8px; font-weight:700; }}"
            f"QTableWidget::item {{ padding:0 8px; color:{TEXT_PRIMARY}; "
            f"border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
            f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        )
        install_copy_menu(self._layers_table)
        self._layers_table.setFixedHeight(24 * 4 + 28)
        vlay.addWidget(self._layers_table)

        # Traceroute section (hidden until used)
        self._trace_hdr = QFrame()
        self._trace_hdr.setFixedHeight(32)
        self._trace_hdr.setStyleSheet(
            f"background:{TH_BG}; border:none; border-top:1px solid {CARD_HDR_BORDER};"
        )
        th_lay = QHBoxLayout(self._trace_hdr)
        th_lay.setContentsMargins(12, 0, 12, 0)
        th_lbl = QLabel("Network Path (Traceroute)")
        th_lbl.setStyleSheet(
            f"color:{TH_TEXT}; font-weight:700; font-size:12px; border:none;"
        )
        th_lay.addWidget(th_lbl)
        self._trace_hdr.hide()
        vlay.addWidget(self._trace_hdr)

        self._trace_table = QTableWidget(0, 3)
        self._trace_table.setHorizontalHeaderLabels(["Hop", "Address", "RTT (ms)"])
        self._trace_table.verticalHeader().setVisible(False)
        self._trace_table.verticalHeader().setDefaultSectionSize(24)
        self._trace_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._trace_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._trace_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._trace_table.setColumnWidth(0, 60)
        self._trace_table.setColumnWidth(2, 100)
        self._trace_table.setStyleSheet(
            f"QTableWidget {{ border:none; background:{BG_CARD}; "
            f"gridline-color:{TABLE_ROW_BORDER}; }}"
            f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; "
            f"border:none; padding:4px 8px; font-weight:700; }}"
            f"QTableWidget::item {{ padding:0 8px; color:{TEXT_PRIMARY}; "
            f"border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
            f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
        )
        install_copy_menu(self._trace_table)
        self._trace_table.hide()
        vlay.addWidget(self._trace_table)

        return card

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_run_clicked(self) -> None:
        idx = self._service_combo.currentIndex()
        if idx < 0:
            return
        service_id = self._service_combo.itemData(idx)
        traceroute = self._traceroute_chk.isChecked()

        self._run_btn.setEnabled(False)
        self._run_btn.setText("Running…")
        self._set_status("Connecting to probes…")

        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._worker.wait(3000)

        self._worker = ServiceDiagnosticsWorker(
            service_id=service_id, traceroute=traceroute, parent=self
        )
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._set_status)
        self._worker.start()

    def _on_result(self, result: ServiceDiagnosticResult) -> None:
        self._last_result = result
        self._update_results(result)
        self._stack.setCurrentIndex(1)
        self._run_btn.setText("Run Diagnostics")
        self._run_btn.setEnabled(True)

    def _on_error(self, msg: str) -> None:
        self._set_status(msg, is_error=True)
        self._run_btn.setText("Run Diagnostics")
        self._run_btn.setEnabled(True)

    def set_service(self, service_id: str) -> None:
        """Pre-select a service in the combo box by ID and focus the run button."""
        for i in range(self._service_combo.count()):
            if self._service_combo.itemData(i) == service_id:
                self._service_combo.setCurrentIndex(i)
                break
        self._run_btn.setFocus()

    def _set_status(self, msg: str, is_error: bool = False) -> None:
        color = RED if is_error else TEXT_MUTED
        self._status_lbl.setStyleSheet(f"color:{color}; font-size:12px;")
        self._status_lbl.setText(msg)

    # ── Results rendering ─────────────────────────────────────────────────────

    def _update_results(self, result: ServiceDiagnosticResult) -> None:
        # Summary card
        self._sum_service_lbl.setText(result.service_name)
        self._sum_ts_lbl.setText(_ts_label(result.ts))

        badge_text, badge_color = _layer_badge(result.failure_layer)
        self._sum_badge.setText(badge_text)
        self._sum_badge.setStyleSheet(
            f"border-radius:4px; padding:2px 10px; font-size:12px;"
            f"font-weight:600; color:{WHITE}; background:{badge_color};"
        )
        self._sum_conf_lbl.setText(f"  Confidence: {result.confidence}%")
        self._sum_text.setText(result.summary or "No summary available.")

        # Diagnostic layers table
        def _row(row_idx: int, name: str, passed: bool, detail: str) -> None:
            status_char = "●"
            status_color = GREEN if passed else RED
            name_item  = QTableWidgetItem(name)
            status_item = QTableWidgetItem(status_char)
            status_item.setForeground(__import__("PyQt6.QtGui", fromlist=["QColor"]).QColor(status_color))
            status_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            detail_item = QTableWidgetItem(detail or "—")
            for item in (name_item, status_item, detail_item):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._layers_table.setItem(row_idx, 0, name_item)
            self._layers_table.setItem(row_idx, 1, status_item)
            self._layers_table.setItem(row_idx, 2, detail_item)

        _row(0, "DNS",           result.dns.passed,           result.dns.detail)
        _row(1, "Reachability",  result.reachability.passed,  result.reachability.detail)
        _row(2, "Latency",       result.latency.passed,        result.latency.detail)

        path_detail = result.path.detail if result.trace else "Not checked (enable traceroute)"
        _row(3, "Path",          result.path.passed,           path_detail)

        # Traceroute table
        if result.trace and result.trace.hops:
            self._trace_hdr.show()
            self._trace_table.show()
            hops = result.trace.hops
            self._trace_table.setRowCount(len(hops))
            for i, hop in enumerate(hops):
                rtt = f"{hop.rtt_ms:.1f}" if hop.rtt_ms >= 0 else "*"
                for col, val in enumerate([str(hop.hop), hop.ip or "*", rtt]):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self._trace_table.setItem(i, col, item)
            self._trace_table.setFixedHeight(
                min(len(hops), 15) * 24 + 28
            )
        else:
            self._trace_hdr.hide()
            self._trace_table.hide()
