"""
CertPage — TLS certificate expiry monitor page (T2#6).

Shows the latest cert check result per host:port, with KPI tiles and
a sortable table.  Refreshes automatically every 5 minutes or when the
CertWorker emits check_done.
"""

from __future__ import annotations

import json
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.cert_monitor import CertTarget
from modules.metric_store import CertCheckPoint, MetricStore
from ui.widgets.context_menu import install_copy_menu
from ui.widgets.empty_state_card import EmptyStateCard
from PyQt6.QtWidgets import QMenu

from ui import styles as _s

_QS_KEY = "cert_monitor/targets"
_QS_EXCLUDED_KEY = "cert_monitor/auto_excluded"


class CertPage(QWidget):
    """Displays TLS certificate expiry status for all monitored hosts."""

    certs_changed   = pyqtSignal(list)   # list[CertTarget]
    scan_requested  = pyqtSignal()       # emitted when first host added from empty state
    scan_complete   = pyqtSignal()       # emitted when a check_done cycle finishes

    def __init__(self, store: Optional[MetricStore] = None, parent=None):
        super().__init__(parent)
        self._store = store
        self._query_hours = 168.0
        self._configured: list[dict] = self._load_targets()
        self._setup_ui()
        if self._configured:
            self._content_stack.setCurrentIndex(1)
        self._refresh()
        # Auto-refresh every 5 min — deliberately NOT started here (RULE-WIN18).
        # The lazy page-builder constructs this page shortly after startup
        # whether or not the user ever opens it, so a timer started at
        # construction rebuilds the whole table for the entire session on a page
        # nobody has looked at. showEvent() starts it; hideEvent() stops it.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(300_000)
        self._refresh_timer.timeout.connect(self._refresh)

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
        targets = [
            CertTarget(host=t["host"], ports=t.get("ports", [443]), label=t.get("label", ""))
            for t in self._configured
        ]
        self.certs_changed.emit(targets)

    def _add_host(self, host: str, port: int) -> None:
        host = host.strip()
        if not host:
            return
        for t in self._configured:
            if t["host"] == host and port in t.get("ports", [443]):
                return
        self._configured.append({"host": host, "ports": [port], "label": ""})
        self._save_targets()
        self._emit_targets()
        self._content_stack.setCurrentIndex(1)

    def _remove_host(self, host: str) -> None:
        removed = [t for t in self._configured if t["host"] == host]
        self._configured = [t for t in self._configured if t["host"] != host]
        # A removed auto-enrolled target must not silently come back on the
        # next port-sweep run (V6 Sprint 3.3) — record it so
        # merge_auto_targets() skips it going forward.
        if any(t.get("label") == "auto" for t in removed):
            excluded = self._load_excluded()
            excluded.add(host)
            self._save_excluded(excluded)
        self._save_targets()
        self._emit_targets()
        if not self._configured:
            self._content_stack.setCurrentIndex(0)
        self._refresh()

    def _load_excluded(self) -> set:
        raw = QSettings("NetSentinel", "NetSentinel").value(_QS_EXCLUDED_KEY, "[]")
        try:
            return set(json.loads(raw))
        except Exception:
            return set()

    def _save_excluded(self, excluded: set) -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(_QS_EXCLUDED_KEY, json.dumps(sorted(excluded)))

    def merge_auto_targets(self, auto_targets: list) -> None:
        """
        Merge auto-enrolled CertTarget objects (from
        modules.cert_auto_enroll.auto_enroll_from_sweep) into the persisted
        target list. Hosts the user previously removed (tracked via
        _QS_EXCLUDED_KEY) are never re-added. No-op if nothing new.
        """
        existing_hosts = {t["host"] for t in self._configured}
        excluded = self._load_excluded()
        added = False
        for target in auto_targets:
            if target.host in existing_hosts or target.host in excluded:
                continue
            self._configured.append({"host": target.host, "ports": list(target.ports), "label": "auto"})
            existing_hosts.add(target.host)
            added = True
        if not added:
            return
        self._save_targets()
        self._emit_targets()
        self._content_stack.setCurrentIndex(1)
        self._refresh()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("TLS Certificate Monitor")
        _s.themed_ss(title, "font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};")
        layout.addWidget(title)

        subtitle = QLabel("Latest TLS certificate status per host — checks run hourly.")
        _s.themed_ss(subtitle, "font-size: 11px; color: {TEXT_SECONDARY};")
        layout.addWidget(subtitle)

        self._content_stack = QStackedWidget()

        # ── Page 0: empty state ───────────────────────────────────────────────
        empty = QWidget()
        evl = QVBoxLayout(empty)
        evl.setContentsMargins(0, 0, 0, 0)
        evl.setSpacing(0)

        e0_card = EmptyStateCard(
            icon="◈",
            title="No certificates monitored yet",
            what_it_shows=(
                "TLS certificate expiry, validity, and issuer details for any host you monitor. "
                "Run a network scan to populate discovered devices, or add a specific host below."
            ),
            why_it_matters=(
                "An expired certificate makes your site unreachable with a scary error message "
                "— NetSentinel alerts you 30 days before expiry so you never get caught out."
            ),
            btn_label="→ Scan Network",
        )

        e0_host = QLineEdit()
        e0_host.setPlaceholderText("Hostname  (e.g. example.com)")
        e0_host.setFixedWidth(220)
        _s.themed_ss(e0_host, "font-size:11px; border:1px solid {BORDER}; padding:3px 6px;")
        e0_port = QSpinBox()
        e0_port.setRange(1, 65535)
        e0_port.setValue(443)
        e0_port.setFixedWidth(_s.SPINBOX_WIDTH_WIDE_PLAIN)
        # background-color/color/font-size ONLY -- border/padding make the
        # +/- buttons unclickable under windows11 (see style_spinbox() docstring).
        _s.themed_ss(e0_port, "background:{BG_DARK}; font-size:11px; color:{TEXT_PRIMARY};")
        _s.style_spinbox(e0_port)
        e0_add = QPushButton("Add Host")
        e0_add.setObjectName("btnScan")
        e0_add.setFixedHeight(30)

        def _add_from_empty():
            self._add_host(e0_host.text(), e0_port.value())
            e0_host.clear()
            self.scan_requested.emit()

        e0_card.clicked.connect(self.scan_requested.emit)
        e0_add.clicked.connect(_add_from_empty)
        e0_host.returnPressed.connect(_add_from_empty)

        form_row = QHBoxLayout()
        form_row.setSpacing(6)
        for w in (e0_host, e0_port, e0_add):
            form_row.addWidget(w)
        center = QHBoxLayout()
        center.addStretch()
        center.addLayout(form_row)
        center.addStretch()

        evl.addWidget(e0_card)
        evl.addSpacing(8)
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
        self._kpi_ok       = self._make_kpi("CERTS OK",      "—", "GREEN")
        self._kpi_expiring = self._make_kpi("EXPIRING SOON", "—", "AMBER")
        self._kpi_expired  = self._make_kpi("EXPIRED",       "—", "RED")
        self._kpi_error    = self._make_kpi("UNREACHABLE",   "—", "TEXT_SECONDARY")
        for w in (self._kpi_ok, self._kpi_expiring, self._kpi_expired, self._kpi_error):
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

        bar_lbl = QLabel("Certificate Status")
        _s.themed_ss(bar_lbl, "font-size: 13px; font-weight: bold; color: {TEXT_PRIMARY};")
        tb_layout.addWidget(bar_lbl)
        tb_layout.addStretch()

        self._txt_host = QLineEdit()
        self._txt_host.setPlaceholderText("Hostname")
        self._txt_host.setFixedWidth(180)
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
        btn_add = QPushButton("+ Add")
        btn_add.setFixedHeight(24)
        _s.themed_ss(btn_add, "font-size:11px; color:{ACCENT}; border:1px solid {ACCENT};"
            " background:transparent; padding:0 10px;")

        def _add_from_bar():
            self._add_host(self._txt_host.text(), self._spin_port.value())
            self._txt_host.clear()

        btn_add.clicked.connect(_add_from_bar)
        self._txt_host.returnPressed.connect(_add_from_bar)

        for w in (self._txt_host, self._spin_port, btn_add):
            tb_layout.addWidget(w)

        card_layout.addWidget(title_bar)

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["HOST", "PORT", "STATUS", "DAYS LEFT", "EXPIRES", "SUBJECT", "ISSUER"]
        )
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
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
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_cert_context_menu)
        install_copy_menu(self._table)
        card_layout.addWidget(self._table)
        cl.addWidget(card, stretch=1)
        self._content_stack.addWidget(content)

        layout.addWidget(self._content_stack, stretch=1)

    # ── KPI helpers ───────────────────────────────────────────────────────────

    def _make_kpi(self, label: str, value: str, accent: str) -> QFrame:
        # `accent` is a theme-token NAME (e.g. "GREEN"), resolved live.
        frame = QFrame()
        _s.themed_ss(frame, lambda tk=accent: (
            f"QFrame {{ background: {_s.BG_CARD}; border: 1px solid {_s.BORDER}; "
            f"border-left: 3px solid {getattr(_s, tk)}; }}"
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
        rows = self._store.query_cert_status(hours=self._query_hours)
        self._populate(rows)

    def set_global_hours(self, hours: float) -> None:
        self._query_hours = hours
        self._refresh()

    def on_check_done(self, results: list) -> None:
        """Slot — connected to CertWorker.check_done."""
        self._refresh()
        self.scan_complete.emit()

    # ── Table population ──────────────────────────────────────────────────────

    def _populate(self, rows: List[CertCheckPoint]) -> None:
        self._table.setRowCount(0)
        ok = expiring = expired = errored = 0

        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            if r.error:
                status_text  = "UNREACHABLE"
                status_ctok  = "TEXT_SECONDARY"
                errored += 1
            elif r.is_expired:
                status_text  = "EXPIRED"
                status_ctok  = "RED"
                expired += 1
            elif r.days_remaining is not None and r.days_remaining < 30:
                status_text  = "EXPIRING"
                status_ctok  = "AMBER"
                expiring += 1
            else:
                status_text  = "OK"
                status_ctok  = "GREEN"
                ok += 1

            days_str    = str(r.days_remaining) if r.days_remaining is not None else "—"
            expires_str = r.not_after or "—"

            # ACT-8: check snooze state for expiring/expired certs
            import time as _t
            snoozed = False
            snooze_chip = ""
            if status_text in ("EXPIRING", "EXPIRED"):
                snooze_key = f"cert/snooze/{r.host}:{r.port}"
                snooze_until = float(
                    QSettings("NetSentinel", "NetSentinel").value(snooze_key, 0) or 0
                )
                if snooze_until > _t.time():
                    snoozed = True
                    snooze_chip = "  z"
                else:
                    QSettings("NetSentinel", "NetSentinel").remove(snooze_key)

            effective_ctok = "TEXT_MUTED" if snoozed else status_ctok

            self._table.setItem(row_idx, 0, self._cell(r.host))
            self._table.setItem(row_idx, 1, self._cell(str(r.port)))

            dot = QLabel(f"  {status_text}{snooze_chip}")
            _s.themed_ss(dot, lambda tk=effective_ctok: (
                f"color: {getattr(_s, tk)}; font-size: 11px; font-weight: bold; padding-left: 4px;"
            ))
            dot.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setCellWidget(row_idx, 2, dot)

            days_item = self._cell(days_str)
            if not snoozed:
                if r.is_expired:
                    days_item.setForeground(QColor(_s.RED))
                elif r.days_remaining is not None and r.days_remaining < 30:
                    days_item.setForeground(QColor(_s.AMBER))
            else:
                days_item.setForeground(QColor(_s.TEXT_MUTED))
            self._table.setItem(row_idx, 3, days_item)
            self._table.setItem(row_idx, 4, self._cell(expires_str))
            self._table.setItem(row_idx, 5, self._cell(r.subject or "—"))
            self._table.setItem(row_idx, 6, self._cell(r.issuer or "—"))

        if not rows and self._configured:
            self._table.setRowCount(1)
            placeholder = QTableWidgetItem("Waiting for first check cycle…")
            placeholder.setForeground(QColor(_s.TEXT_SECONDARY))
            placeholder.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(0, 0, placeholder)
            self._table.setSpan(0, 0, 1, 7)

        self._set_kpi(self._kpi_ok,       "CERTS OK",      ok)
        self._set_kpi(self._kpi_expiring, "EXPIRING SOON", expiring)
        self._set_kpi(self._kpi_expired,  "EXPIRED",       expired)
        self._set_kpi(self._kpi_error,    "UNREACHABLE",   errored)

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ── ACT-8: snooze reminder ────────────────────────────────────────────────

    def _on_cert_context_menu(self, pos) -> None:
        import time as _t
        row = self._table.rowAt(pos.y())
        if row < 0:
            return
        host_item = self._table.item(row, 0)
        port_item = self._table.item(row, 1)
        if host_item is None or port_item is None:
            return
        host = host_item.text().strip()
        port = port_item.text().strip()
        if not host:
            return

        snooze_key = f"cert/snooze/{host}:{port}"
        snooze_until = float(
            QSettings("NetSentinel", "NetSentinel").value(snooze_key, 0) or 0
        )
        is_snoozed = snooze_until > _t.time()

        _menu_ss = ("QMenu {{ background:{BG_CARD}; color:{TEXT_PRIMARY}; font-size:11px;"
            " border:1px solid {BORDER}; }}"
            "QMenu::item:selected {{ background:{BG_HOVER}; color:{TEXT_PRIMARY}; }}")
        menu = QMenu(self)
        _s.themed_ss(menu, _menu_ss)

        snooze_menu = menu.addMenu("Snooze reminder")
        _s.themed_ss(snooze_menu, _menu_ss)
        act_7d = snooze_menu.addAction("Snooze 7 days")
        act_30d = snooze_menu.addAction("Snooze 30 days")
        act_7d.triggered.connect(lambda: self._snooze_cert(host, port, days=7))
        act_30d.triggered.connect(lambda: self._snooze_cert(host, port, days=30))

        if is_snoozed:
            act_clear = menu.addAction("Clear snooze")
            act_clear.triggered.connect(lambda: self._clear_cert_snooze(host, port))

        menu.addSeparator()
        act_fix = menu.addAction("How to Fix")
        act_fix.triggered.connect(lambda: self._show_cert_fix(host, port, row))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _show_cert_fix(self, host: str, port: str, row: int) -> None:
        from PyQt6.QtWidgets import QMessageBox
        status_it  = self._table.item(row, 2)
        days_it    = self._table.item(row, 3)
        status = status_it.text() if status_it else ""
        days_txt = days_it.text() if days_it else ""

        if "OK" in status.upper() or ("VALID" in status.upper() and "EXPIR" not in status.upper()):
            msg = f"<b>{host}:{port}</b> — certificate is valid, no action required."
        elif "EXPIRED" in status.upper():
            msg = (
                f"<b>{host}:{port}</b> — certificate has already EXPIRED.<br><br>"
                "<b>Immediate steps:</b><br>"
                "1. Renew or replace the certificate on the server immediately.<br>"
                "2. If using Let's Encrypt, run <code>certbot renew</code>.<br>"
                "3. Restart the web server after installing the new certificate.<br>"
                "4. Verify the renewed cert appears here within 5 minutes."
            )
        else:
            msg = (
                f"<b>{host}:{port}</b> — certificate expires in {days_txt}.<br><br>"
                "<b>Steps to renew:</b><br>"
                "1. Log into your certificate authority or hosting panel.<br>"
                "2. Renew before expiry — most CAs allow renewal 30+ days early.<br>"
                "3. For Let's Encrypt: run <code>certbot renew --force-renewal</code>.<br>"
                "4. Install the new certificate and restart the service.<br>"
                "5. Verify the new expiry date appears in this table."
            )
        QMessageBox.information(self, "How to Fix", msg)

    def _snooze_cert(self, host: str, port: str, days: int) -> None:
        import time as _t
        expiry = _t.time() + days * 86400
        QSettings("NetSentinel", "NetSentinel").setValue(
            f"cert/snooze/{host}:{port}", expiry
        )
        self._refresh()

    def _clear_cert_snooze(self, host: str, port: str) -> None:
        QSettings("NetSentinel", "NetSentinel").remove(f"cert/snooze/{host}:{port}")
        self._refresh()

    # ── Timer lifecycle ───────────────────────────────────────────────────────

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    def hideEvent(self, event) -> None:
        """Stop the auto-refresh while the page isn't visible (RULE-WIN15)."""
        self._refresh_timer.stop()
        super().hideEvent(event)
