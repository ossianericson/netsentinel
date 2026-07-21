"""
ServicePage — TCP service/port heartbeat monitor page (T2#7).

Displays the latest check result per service (host:port), with KPI tiles
and a sortable table. Refreshes automatically every minute or when
ServiceWorker emits check_done.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from ui.expanding_table import ExpandingTable
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.skeleton import clear_skeleton_rows, insert_skeleton_rows

from modules.metric_store import MetricStore, ServiceCheckPoint
from modules.service_monitor import ServiceTarget, check_tcp
from ui.styles import (
    STATUS_ICON_CRIT, STATUS_ICON_OK,
)
from ui import styles as _s

_QS_KEY = "service_monitor/targets"


def _ts_label(ts: int) -> str:
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        return dt.strftime("%H:%M:%S")
    except Exception:
        return "—"


class _AddProbeWorker(QThread):
    """One-off reachability check run before a new target is persisted.

    Without this, any text landing in the add-service field (a typo, or an
    automated fuzz click into the host box with the port spinbox's 443
    default) becomes a permanent monitor with no confirmation — and if the
    target was never actually reachable, it fires a CRITICAL Service Down
    alert on its very first check and forever after.
    """
    result = pyqtSignal(bool)

    def __init__(self, host: str, port: int, parent=None):
        super().__init__(parent)
        self._host = host
        self._port = port

    def run(self) -> None:
        up, _rtt, _err = check_tcp(self._host, self._port, timeout=3.0)
        self.result.emit(up)


class ServicePage(QWidget):
    """Displays TCP service/port heartbeat status for all monitored services."""

    services_changed  = pyqtSignal(list)   # list[ServiceTarget]
    scan_requested    = pyqtSignal()       # emitted when first service added from empty state
    diagnose_service  = pyqtSignal(str)    # emits service_id (or "") → navigate to Service Diagnostics
    check_now_requested = pyqtSignal()     # emitted after adding a service to wake the worker

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._query_hours = 24.0
        self._rows: list[ServiceCheckPoint] = []
        self._configured: list[dict] = self._load_targets()
        self._add_probe: Optional[_AddProbeWorker] = None
        self._setup_ui()
        if self._configured:
            self._content_stack.setCurrentIndex(1)
        insert_skeleton_rows(self._table, count=4)
        self._refresh()
        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(60_000)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_targets(self) -> list[dict]:
        raw = QSettings("NetSentinel", "NetSentinel").value(_QS_KEY, "[]")
        try:
            return list(json.loads(raw))
        except Exception:
            return []

    def _save_targets(self) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(_QS_KEY, json.dumps(self._configured))

    def _emit_targets(self) -> None:
        targets = [ServiceTarget(t["host"], t["port"], t.get("label", "")) for t in self._configured]
        self.services_changed.emit(targets)

    def _probe_and_add(self, host: str, port: int, label: str, on_result) -> bool:
        """Probe host:port for reachability before persisting it as a target.

        An unreachable target is hard-blocked, not silently added — see
        _AddProbeWorker's docstring for why. Returns True once a probe has
        been started (the outcome arrives asynchronously via
        on_result(up: bool)); returns False without starting a probe if the
        input was rejected synchronously (blank host, or a duplicate that is
        already monitored) — mirrors the previous synchronous return value.
        """
        host = host.strip()
        if not host:
            return False
        for t in self._configured:
            if t["host"] == host and t["port"] == port:
                return False
        if self._add_probe is not None and self._add_probe.isRunning():
            return False

        def _finish(up: bool) -> None:
            if up:
                self._configured.append(
                    {"host": host, "port": port, "label": label.strip() or f"{host}:{port}"}
                )
                self._save_targets()
                self._emit_targets()
                self._content_stack.setCurrentIndex(1)
            on_result(up)

        self._add_probe = _AddProbeWorker(host, port, parent=self)
        self._add_probe.result.connect(_finish)
        self._add_probe.start()
        return True

    def _remove_service(self, host: str, port: int) -> None:
        self._configured = [t for t in self._configured if not (t["host"] == host and t["port"] == port)]
        self._save_targets()
        self._emit_targets()
        if not self._configured:
            self._content_stack.setCurrentIndex(0)
        self._refresh()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Service Heartbeat Monitor")
        _s.themed_ss(title, "font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        subtitle = QLabel("TCP port reachability checks — configured services are probed every minute.")
        _s.themed_ss(subtitle, "font-size: 11px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        self._content_stack = QStackedWidget()

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.addStretch()

        em_desc = QLabel(
            "No services configured.\n"
            "Add a hostname or IP and port below to start monitoring TCP reachability."
        )
        em_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        em_desc.setWordWrap(True)
        _s.themed_ss(em_desc, "color:{TEXT_SECONDARY}; font-size:12px;")
        evl.addWidget(em_desc, alignment=Qt.AlignmentFlag.AlignCenter)
        evl.addSpacing(16)

        # Inline add form for empty state
        e0_host  = QLineEdit()
        e0_host.setPlaceholderText("Host / IP  (e.g. 192.168.1.1)")
        e0_host.setFixedWidth(200)
        _s.themed_ss(e0_host, "font-size:11px; border:1px solid {BORDER}; padding:3px 6px;")
        e0_port  = QSpinBox()
        e0_port.setRange(1, 65535)
        e0_port.setValue(443)
        e0_port.setFixedWidth(_s.SPINBOX_WIDTH_WIDE_PLAIN)
        # background-color/color/font-size ONLY -- border/padding make the
        # +/- buttons unclickable under windows11 (see style_spinbox() docstring).
        _s.themed_ss(e0_port, "background:{BG_DARK}; font-size:11px; color:{TEXT_PRIMARY};")
        _s.style_spinbox(e0_port)
        e0_label = QLineEdit()
        e0_label.setPlaceholderText("Label  (optional)")
        e0_label.setFixedWidth(140)
        _s.themed_ss(e0_label, "font-size:11px; border:1px solid {BORDER}; padding:3px 6px;")
        e0_add   = QPushButton("Add Service")
        e0_add.setObjectName("btnScan")
        e0_add.setFixedHeight(30)

        _e0_normal_style = "font-size:11px; border:1px solid {BORDER}; padding:3px 6px;"
        _e0_error_style = "font-size:11px; border:1px solid {RED}; padding:3px 6px;"

        def _add_from_empty():
            host = e0_host.text()
            port = e0_port.value()
            label = e0_label.text()

            def _done(up: bool):
                e0_add.setEnabled(True)
                e0_add.setText("Add Service")
                if up:
                    e0_host.clear()
                    e0_label.clear()
                    self.check_now_requested.emit()
                    self.scan_requested.emit()
                else:
                    msg = f"Couldn't reach {host.strip()}:{port} — not added."
                    _s.themed_ss(e0_host, _e0_error_style)
                    e0_host.setToolTip(_s.safe_tooltip(msg))
                    # setToolTip() alone only shows on hover — pop it up immediately
                    # so the rejection reason is actually seen, not just a red flash.
                    QToolTip.showText(e0_host.mapToGlobal(e0_host.rect().bottomLeft()), msg, e0_host)
                    _t = QTimer(self)
                    _t.setSingleShot(True)
                    _t.timeout.connect(lambda: (_s.themed_ss(e0_host, _e0_normal_style), e0_host.setToolTip("")))
                    _t.start(2500)

            started = self._probe_and_add(host, port, label, _done)
            if started:
                e0_add.setEnabled(False)
                e0_add.setText("Checking…")

        e0_add.clicked.connect(_add_from_empty)
        e0_host.returnPressed.connect(_add_from_empty)

        form_row = QHBoxLayout()
        form_row.setSpacing(6)
        for w in (e0_host, e0_port, e0_label, e0_add):
            form_row.addWidget(w)
        center = QHBoxLayout()
        center.addStretch()
        center.addLayout(form_row)
        center.addStretch()
        evl.addLayout(center)
        evl.addStretch()
        self._content_stack.addWidget(empty)

        # ── Page 1: content ───────────────────────────────────────────────────
        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self._kpi_up    = self._make_kpi("SERVICES UP",    "—", "GREEN")
        self._kpi_down  = self._make_kpi("SERVICES DOWN",  "—", "RED")
        self._kpi_total = self._make_kpi("TOTAL SERVICES", "—", "ACCENT")
        self._kpi_avg   = self._make_kpi("AVG RTT (UP)",   "—", "ACCENT")
        for w in (self._kpi_up, self._kpi_down, self._kpi_total, self._kpi_avg):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        cl.addLayout(kpi_row)

        card = QFrame()
        _s.themed_ss(card, "QFrame {{ background: {BG_CARD}; border: 1px solid {BORDER}; border-radius: {CARD_RADIUS}; }}")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # Title bar with inline add form
        title_bar = QFrame()
        _s.themed_ss(title_bar, "background: {BG_CARD}; border-bottom: 1px solid {CARD_HDR_BORDER};")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 6, 10, 6)
        tb_layout.setSpacing(6)

        bar_lbl = QLabel("Service Status")
        _s.themed_ss(bar_lbl, "font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY};")
        tb_layout.addWidget(bar_lbl)
        tb_layout.addStretch()
        self._svc_refresh_lbl = QLabel("")
        _s.themed_ss(self._svc_refresh_lbl, "font-size: 10px; color: {TEXT_MUTED};")
        tb_layout.addWidget(self._svc_refresh_lbl)
        tb_layout.addSpacing(10)

        self._txt_host = QLineEdit()
        self._txt_host.setPlaceholderText("Host / IP")
        self._txt_host.setFixedWidth(160)
        self._txt_host.setFixedHeight(24)
        _s.themed_ss(self._txt_host, "font-size:11px; border:1px solid {BORDER}; padding:2px 5px;")
        self._spin_port = QSpinBox()
        self._spin_port.setRange(1, 65535)
        self._spin_port.setValue(443)
        self._spin_port.setFixedWidth(_s.SPINBOX_WIDTH_WIDE_PLAIN)
        self._spin_port.setFixedHeight(24)
        # background-color/color/font-size ONLY -- border/padding make the
        # +/- buttons unclickable under windows11 (see style_spinbox() docstring).
        _s.themed_ss(self._spin_port, "background:{BG_DARK}; font-size:11px; color:{TEXT_PRIMARY};")
        _s.style_spinbox(self._spin_port)
        self._txt_label = QLineEdit()
        self._txt_label.setPlaceholderText("Label")
        self._txt_label.setFixedWidth(120)
        self._txt_label.setFixedHeight(24)
        _s.themed_ss(self._txt_label, "font-size:11px; border:1px solid {BORDER}; padding:2px 5px;")
        btn_add = QPushButton("+ Add")
        btn_add.setFixedHeight(24)
        _s.themed_ss(btn_add, "QPushButton {{ font-size:11px; color:{ACCENT}; border:1px solid {ACCENT};"
            " background:transparent; padding:0 10px; }}"
            "QPushButton:hover   {{ color:{ACCENT_LITE}; border-color:{ACCENT_LITE}; }}"
            "QPushButton:pressed {{ color:{ACCENT_DARK}; border-color:{ACCENT_DARK}; }}")

        _bar_normal_style = "font-size:11px; border:1px solid {BORDER}; padding:2px 5px;"
        _bar_error_style = "font-size:11px; border:1px solid {RED}; padding:2px 5px;"

        def _flash_bar_host(tooltip: str, duration_ms: int) -> None:
            _s.themed_ss(self._txt_host, _bar_error_style)
            self._txt_host.setToolTip(_s.safe_tooltip(tooltip) if tooltip else tooltip)
            if tooltip:
                # setToolTip() alone only shows on hover — pop it up immediately
                # so the rejection reason is actually seen, not just a red flash.
                QToolTip.showText(
                    self._txt_host.mapToGlobal(self._txt_host.rect().bottomLeft()),
                    tooltip,
                    self._txt_host,
                )
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(lambda: (
                _s.themed_ss(self._txt_host, _bar_normal_style), self._txt_host.setToolTip("")
            ))
            _t.start(duration_ms)

        def _add_from_bar():
            host = self._txt_host.text().strip()
            if not host:
                _flash_bar_host("", 1500)
                return
            port = self._spin_port.value()
            label = self._txt_label.text()

            def _done(up: bool):
                btn_add.setEnabled(True)
                btn_add.setText("+ Add")
                if up:
                    self._txt_host.clear()
                    self._txt_label.clear()
                    self.check_now_requested.emit()
                else:
                    _flash_bar_host(f"Couldn't reach {host}:{port} — not added.", 2500)

            started = self._probe_and_add(host, port, label, _done)
            if started:
                btn_add.setEnabled(False)
                btn_add.setText("Checking…")

        btn_add.clicked.connect(_add_from_bar)
        self._txt_host.returnPressed.connect(_add_from_bar)

        for w in (self._txt_host, self._spin_port, self._txt_label, btn_add):
            tb_layout.addWidget(w)

        card_layout.addWidget(title_bar)

        self._table = ExpandingTable(
            0, 6,
            detail_builder=lambda r: self._build_service_detail(r),
            detail_height=120,
        )
        self._table.setHorizontalHeaderLabels(
            ["SERVICE", "HOST", "PORT", "STATUS", "RTT (ms)", "LAST CHECK"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(ExpandingTable.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(ExpandingTable.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)
        _s.themed_ss(self._table, """
            QTableWidget {{
                border: none; gridline-color: {TABLE_ROW_BORDER};
                font-size: 11px; color: {TEXT_PRIMARY};
                alternate-background-color: {BG_ALT_ROW};
            }}
            QHeaderView::section {{
                background-color: {TH_BG}; color: {TH_TEXT};
                font-size: 11px; font-weight: bold;
                padding: 4px 5px; border: none;
            }}
            QTableWidget::item {{ padding: 4px 5px; }}
            QTableWidget::item:hover {{ background: {BG_HOVER}; }}
            QTableWidget::item:selected {{
                background: {TABLE_SEL}; color: {TEXT_PRIMARY};
            }}
            """)
        self._table.setShowGrid(True)
        self._table.setWordWrap(False)
        self._table.verticalHeader().setDefaultSectionSize(24)

        def _svc_copy_url():
            r = self._table.currentRow()
            if r >= 0:
                host_it = self._table.item(r, 1)
                port_it = self._table.item(r, 2)
                if host_it and port_it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(f"{host_it.text()}:{port_it.text()}")

        def _svc_copy_status():
            r = self._table.currentRow()
            if r >= 0:
                it = self._table.item(r, 3)
                if it:
                    from PyQt6.QtWidgets import QApplication as _QApp
                    _QApp.clipboard().setText(it.text())

        def _svc_how_to_fix():
            r = self._table.currentRow()
            if r < 0:
                return
            from PyQt6.QtWidgets import QMessageBox
            status_it = self._table.item(r, 3)
            status = status_it.text() if status_it else ""
            if "UP" in status.upper() or "OK" in status.upper():
                msg = "Service is responding normally — no action required."
            else:
                svc_it  = self._table.item(r, 0)
                host_it = self._table.item(r, 1)
                port_it = self._table.item(r, 2)
                svc  = svc_it.text()  if svc_it  else "service"
                host = host_it.text() if host_it else "host"
                port = port_it.text() if port_it else "port"
                msg = (
                    f"<b>{svc}</b> at {host}:{port} is not responding.<br><br>"
                    "Steps to investigate:<br>"
                    "1. Ping the host to confirm basic connectivity.<br>"
                    "2. Check that the service is running (e.g. <code>netstat -an | grep {port}</code>).<br>"
                    "3. Verify firewall rules allow inbound traffic on port {port}.<br>"
                    "4. Check service logs for crash or restart errors.<br>"
                    "5. Confirm the host IP/port in the service target list is correct."
                )
            QMessageBox.information(self, "How to Fix", msg)

        def _svc_diagnose():
            r = self._table.currentRow()
            if r < 0:
                return
            host_it = self._table.item(r, 1)
            host = host_it.text().strip() if host_it else ""
            service_id = self._find_service_id(host)
            self.diagnose_service.emit(service_id)

        install_copy_menu(self._table, [
            ("separator",     None),
            ("Copy target",   _svc_copy_url),
            ("Copy status",   _svc_copy_status),
            ("separator",     None),
            ("How to Fix",    _svc_how_to_fix),
            ("Diagnose →",    _svc_diagnose),
        ])
        card_layout.addWidget(self._table)
        cl.addWidget(card, stretch=1)
        self._content_stack.addWidget(content)

        layout.addWidget(self._content_stack, stretch=1)

    # ── KPI helpers ───────────────────────────────────────────────────────────

    def _make_kpi(self, label: str, value: str, accent_name: str) -> QFrame:
        frame = QFrame()
        _s.themed_ss(frame, lambda name=accent_name: (
            f"QFrame {{ background: {_s.BG_CARD}; border: 1px solid {_s.BORDER}; "
            f"border-left: 3px solid {getattr(_s, name)}; }}"
        ))
        frame.setMinimumWidth(100)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(2)
        lbl = QLabel(label)
        _s.themed_ss(lbl, "font-size: 9px; font-weight: bold; color: {TEXT_SECONDARY};")
        val = QLabel(value)
        _s.themed_ss(val, "font-size: 22px; font-weight: bold; color: {TEXT_PRIMARY};")
        val.setObjectName(f"kpi_val_{label}")
        lay.addWidget(lbl)
        lay.addWidget(val)
        return frame

    def _set_kpi(self, frame: QFrame, label: str, value) -> None:
        w = frame.findChild(QLabel, f"kpi_val_{label}")
        if w:
            w.setText(str(value))

    # ── Data refresh ──────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if not self._store or not self.isVisible():
            return
        rows = self._store.query_service_status(hours=self._query_hours)
        self._populate(rows)

    def set_global_hours(self, hours: float) -> None:
        self._query_hours = hours
        self._refresh()

    def on_check_done(self, results: list) -> None:
        """Slot — connected to ServiceWorker.check_done."""
        self._refresh()

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, rows: List[ServiceCheckPoint]) -> None:
        # Only show services that are still in the configured target list so that
        # removed services don't reappear from stale DB history data.
        configured_set = {(t["host"], t["port"]) for t in self._configured}
        rows = [r for r in rows if (r.host, r.port) in configured_set]
        self._rows = list(rows)
        clear_skeleton_rows(self._table)
        self._table.setSortingEnabled(False)
        self._table.clear_detail()
        self._table.setRowCount(0)

        if not rows:
            if self._configured:
                # Targets exist but no check data yet — show waiting hint
                self._table.setRowCount(1)
                placeholder = QTableWidgetItem("Waiting for first check cycle…")
                placeholder.setForeground(QColor(_s.TEXT_SECONDARY))
                placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(0, 0, placeholder)
                self._table.setSpan(0, 0, 1, 6)
            for kpi, lbl, v in [
                (self._kpi_up,    "SERVICES UP",    "0"),
                (self._kpi_down,  "SERVICES DOWN",  "0"),
                (self._kpi_total, "TOTAL SERVICES", "0"),
                (self._kpi_avg,   "AVG RTT (UP)",   "—"),
            ]:
                self._set_kpi(kpi, lbl, v)
            return

        up_count = down_count = 0
        rtts = []

        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            if r.up:
                status_text  = f"{STATUS_ICON_OK}  UP"
                status_color = _s.GREEN
                up_count += 1
                if r.rtt_ms is not None:
                    rtts.append(r.rtt_ms)
            else:
                status_text  = f"{STATUS_ICON_CRIT}  DOWN"
                status_color = _s.RED
                down_count += 1

            rtt_str = f"{r.rtt_ms:.1f}" if r.rtt_ms is not None else "—"

            self._table.setItem(row_idx, 0, self._cell(r.label or f"{r.host}:{r.port}"))
            self._table.setItem(row_idx, 1, self._cell(r.host))
            self._table.setItem(row_idx, 2, self._cell(str(r.port)))

            if r.up:
                dot = QLabel(status_text)
                dot.setStyleSheet(
                    f"color: {status_color}; font-size: 11px; font-weight: bold; padding-left: 4px;"
                )
                dot.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                dot.setToolTip(_s.safe_tooltip(f"● {r.label or r.host}:{r.port} responded successfully."))
                self._table.setCellWidget(row_idx, 3, dot)
            else:
                # DOWN row — status label + inline Diagnose button
                _cell_w = QWidget()
                _cell_w.setStyleSheet("background: transparent;")
                _cell_h = QHBoxLayout(_cell_w)
                _cell_h.setContentsMargins(4, 0, 4, 0)
                _cell_h.setSpacing(6)
                _dot = QLabel(status_text)
                _dot.setStyleSheet(
                    f"color: {status_color}; font-size: 11px; font-weight: bold;"
                    " background: transparent;"
                )
                _dot.setToolTip(_s.safe_tooltip(f"{r.label or r.host}:{r.port} is not responding — the service may be offline or blocked by a firewall."))
                _cell_h.addWidget(_dot)
                _cell_h.addStretch()
                _diag_btn = QPushButton("Diagnose →")
                _diag_btn.setFixedHeight(18)
                _diag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _s.themed_ss(_diag_btn, "QPushButton {{ background: transparent; color: {ACCENT};"
                    " font-size: 9px; border: 1px solid {ACCENT}; border-radius: 2px; padding: 0 4px; }}"
                    "QPushButton:hover {{ background: {BG_HOVER}; color: {ACCENT}; }}"
                    "QPushButton:pressed {{ background: {BORDER}; color: {TEXT_PRIMARY}; }}")
                _host = r.host
                _diag_btn.clicked.connect(
                    lambda _=False, _h=_host: self.diagnose_service.emit(
                        self._find_service_id(_h)
                    )
                )
                _cell_h.addWidget(_diag_btn)
                self._table.setCellWidget(row_idx, 3, _cell_w)

            rtt_item = QTableWidgetItem(rtt_str)
            rtt_item.setFlags(rtt_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            rtt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if r.rtt_ms is not None:
                rtt_item.setData(Qt.ItemDataRole.UserRole, r.rtt_ms)
            self._table.setItem(row_idx, 4, rtt_item)

            self._table.setItem(row_idx, 5, self._cell(_ts_label(r.ts)))

        avg_rtt = f"{sum(rtts)/len(rtts):.1f} ms" if rtts else "—"
        self._set_kpi(self._kpi_up,    "SERVICES UP",    str(up_count))
        self._set_kpi(self._kpi_down,  "SERVICES DOWN",  str(down_count))
        self._set_kpi(self._kpi_total, "TOTAL SERVICES", str(len(rows)))
        self._set_kpi(self._kpi_avg,   "AVG RTT (UP)",   avg_rtt)

        self._table.setSortingEnabled(True)
        self._svc_refresh_lbl.setText(
            f"Updated {datetime.now(tz=timezone.utc).astimezone().strftime('%H:%M:%S')}"
        )

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ── Detail panel ──────────────────────────────────────────────────────────

    def _build_service_detail(self, logical_row: int) -> QWidget:
        # Use the host:port from the visible table row (sort-order-safe lookup)
        # rather than self._rows[logical_row] which is insertion-order based.
        host_it = self._table.item(logical_row, 1)
        port_it = self._table.item(logical_row, 2)
        if not host_it or not port_it:
            return QWidget()
        try:
            lookup_host = host_it.text()
            lookup_port = int(port_it.text())
        except (ValueError, AttributeError):
            return QWidget()
        r = next(
            (row for row in self._rows if row.host == lookup_host and row.port == lookup_port),
            None,
        )
        if r is None:
            return QWidget()
        status_color = _s.GREEN if r.up else _s.RED

        outer = QWidget()
        outer.setStyleSheet(
            f"QWidget {{ background:{_s.BG_HOVER}; border:none;"
            f" border-left:3px solid {status_color}; }}"
        )
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

        col1 = QWidget()
        col1.setStyleSheet("QWidget { background:transparent; border:none; }")
        g1 = QFormLayout(col1)
        g1.setContentsMargins(0, 0, 0, 0)
        g1.setSpacing(3)
        g1.setHorizontalSpacing(12)
        g1.addRow(_hdr("Service"), _val(r.label or f"{r.host}:{r.port}"))
        g1.addRow(_hdr("Host"),    _val(r.host))
        g1.addRow(_hdr("Port"),    _val(str(r.port)))

        rtt_str = f"{r.rtt_ms:.1f} ms" if r.rtt_ms is not None else "—"
        col2 = QWidget()
        col2.setStyleSheet("QWidget { background:transparent; border:none; }")
        g2 = QFormLayout(col2)
        g2.setContentsMargins(0, 0, 0, 0)
        g2.setSpacing(3)
        g2.setHorizontalSpacing(12)
        g2.addRow(_hdr("Status"),     _val("UP" if r.up else "DOWN", status_color))
        g2.addRow(_hdr("RTT"),        _val(rtt_str))
        g2.addRow(_hdr("Last Check"), _val(_ts_label(r.ts)))
        if not r.up and r.error:
            g2.addRow(_hdr("Error"), _val(r.error, _s.RED))

        # Recent history from store (last 5 checks)
        if self._store:
            history = self._store.query_service_history(r.host, r.port, hours=1.0)[-5:]
            if history:
                dots = "  ".join(("●" if p.up else "○") for p in reversed(history))
                col3 = QWidget()
                col3.setStyleSheet("QWidget { background:transparent; border:none; }")
                g3 = QFormLayout(col3)
                g3.setContentsMargins(0, 0, 0, 0)
                g3.setSpacing(3)
                g3.setHorizontalSpacing(12)
                recent_lbl = _val(dots)
                _s.themed_ss(recent_lbl, "font-size:14px; color:{GREEN}; background:transparent; border:none; letter-spacing:2px;")
                g3.addRow(_hdr("Last 5 checks"), recent_lbl)
                lay.addWidget(col3)

        lay.addWidget(col1)
        lay.addWidget(col2)
        lay.addStretch()

        # Remove button — captures host/port from current row
        _host = r.host
        _port = r.port
        btn_rm = QPushButton("Remove Service")
        btn_rm.setFixedHeight(24)
        _s.themed_ss(btn_rm, "font-size:10px; color:{RED}; border:1px solid {RED};"
            " background:transparent; padding:0 8px;")
        btn_rm.clicked.connect(lambda: self._remove_service(_host, _port))
        lay.addWidget(btn_rm, alignment=Qt.AlignmentFlag.AlignVCenter)

        return outer

    # ── Service catalog lookup ────────────────────────────────────────────────

    @staticmethod
    def _find_service_id(host: str) -> str:
        """Return SERVICE_CATALOG id whose probe_hosts contains host, or ''."""
        if not host:
            return ""
        try:
            from modules.service_diagnostics import SERVICE_CATALOG
            for entry in SERVICE_CATALOG.values():
                if host in entry.probe_hosts:
                    return entry.id
        except Exception:
            pass  # non-fatal — catalog unavailable
        return ""

    # ── Public navigation slot ────────────────────────────────────────────────

    def focus_on_host(self, ip: str, mac: str = "") -> None:
        """Public slot — scroll to and select the first service row for this host."""
        if not ip or ip in ("—", ""):
            return
        for row in range(self._table.rowCount()):
            host_it = self._table.item(row, 1)
            if host_it and host_it.text() == ip:
                self._table.setCurrentCell(row, 1)
                self._table.scrollToItem(host_it)
                break
