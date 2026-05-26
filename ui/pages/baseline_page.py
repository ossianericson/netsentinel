"""
BaselinePage — Configuration baseline snapshot UI.

Lets users capture point-in-time snapshots of network device inventory
(IP, MAC, hostname, open ports) and SNMP data, then compare any two
snapshots to detect configuration drift.

Features:
  - KPI tiles: snapshot count, last taken, drift status
  - Snapshots table: ts, label, device count, port count
  - Take Snapshot button (runs discovery in background QThread)
  - Delete Snapshot button
  - Compare button (select two rows) → shows diff card
  - Diff card: added/removed devices, port changes per device, SNMP changes

Architecture rules:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O on the main thread (QThread for scan).
  • MetricStore injected via constructor.
"""
from __future__ import annotations

import json
import time
from typing import List, Optional

from PyQt6.QtCore import Qt, QSettings, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG, BG_ALT_ROW, BG_CARD, BG_DARK,
    BG_HOVER, BORDER, CARD_HDR_BORDER, CARD_RADIUS, GREEN, GREEN_BG, RED, RED_BG,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.widgets.context_menu import install_copy_menu
from modules.config_baseline import (
    ConfigSnapshot, SnapshotDiff,
    build_snapshot_from_scan, diff_snapshots,
    list_snapshots as _list_snapshots,
    store_snapshot as _store_snapshot,
    delete_snapshot as _delete_snapshot,
    load_snapshot as _load_snapshot,
)


# ── Background worker ─────────────────────────────────────────────────────────

class _SnapshotWorker(QThread):
    """Runs combined_discovery in a background thread and emits the result."""

    result_ready = pyqtSignal(list)   # list of device dicts
    error        = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            from modules.combined_discovery import discover
            devices = discover()
            self.result_ready.emit(devices or [])
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ── Helper widgets ────────────────────────────────────────────────────────────

def _page_header(title: str, subtitle: str = "") -> QFrame:
    container = QFrame()
    container.setObjectName("pageHeader")
    container.setStyleSheet(
        f"QFrame#pageHeader {{ background: transparent; border: none;"
        f" border-bottom: 1px solid {BORDER}; }}"
    )
    vbox = QVBoxLayout(container)
    vbox.setContentsMargins(20, 16, 20, 12)
    vbox.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(
        f"color:{TEXT_PRIMARY}; font-size:18px; font-weight:bold;"
        "padding:0; background:transparent; border:none;"
    )
    vbox.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px;"
            "padding:0; background:transparent; border:none;"
        )
        vbox.addWidget(s)
    return container


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("card")
    card.setStyleSheet(
        f"QFrame#card{{background:{BG_CARD};border:1px solid {BORDER};border-radius:{CARD_RADIUS};}}"
    )
    cl = QVBoxLayout(card)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)
    tb = QFrame()
    tb.setFixedHeight(32)
    tb.setStyleSheet(f"background:{BG_CARD};border-bottom:1px solid {CARD_HDR_BORDER};")
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    lbl.setStyleSheet(f"color:{TEXT_PRIMARY};font-weight:bold;font-size:13px;")
    tbl.addWidget(lbl)
    tbl.addStretch()
    cl.addWidget(tb)
    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD};")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 12, 16, 14)
    bl.setSpacing(8)
    cl.addWidget(body)
    return card, bl


def _kpi_tile(label: str, value: str, accent_color: str = ACCENT) -> QWidget:
    w = QFrame()
    w.setStyleSheet(
        f"QFrame{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-left:3px solid {accent_color};min-width:110px;}}"
    )
    vl = QVBoxLayout(w)
    vl.setContentsMargins(10, 8, 10, 8)
    vl.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:9px;font-weight:bold;")
    val = QLabel(value)
    val.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:22px;font-weight:bold;")
    val.setObjectName("kpi_val")
    vl.addWidget(lbl)
    vl.addWidget(val)
    return w


def _btn(text: str, primary: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(26)
    if primary:
        b.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};border:none;"
            f"border-radius:2px;padding:0 14px;font-size:11px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT_DARK};}}"
            f"QPushButton:disabled{{background:{BORDER};color:{TEXT_SECONDARY};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton{{background:{BG_CARD};color:{TEXT_SECONDARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 12px;font-size:11px;}}"
            f"QPushButton:hover{{color:{ACCENT};border-color:{ACCENT};}}"
            f"QPushButton:disabled{{color:{BORDER};}}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    return b


# ── Main page ─────────────────────────────────────────────────────────────────

class BaselinePage(QWidget):
    """Configuration baseline snapshot and diff page."""

    drift_detected = pyqtSignal(str)   # message describing the drift found

    def __init__(self, store=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._store = store
        self._snapshots: List[ConfigSnapshot] = []
        self._worker: Optional[_SnapshotWorker] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        outer.addWidget(_page_header(
            "Configuration Baseline Snapshots",
            "Capture network state and compare snapshots to detect configuration drift",
        ))

        # ACT-7: auto-snapshot schedule strip
        outer.addWidget(self._build_schedule_strip())

        # KPI row
        self._kpi_count   = _kpi_tile("Snapshots",    "—")
        self._kpi_last    = _kpi_tile("Last Taken",   "—")
        self._kpi_drift   = _kpi_tile("Last Diff",    "—", GREEN)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        kpi_row.addWidget(self._kpi_count)
        kpi_row.addWidget(self._kpi_last)
        kpi_row.addWidget(self._kpi_drift)
        kpi_row.addStretch()
        outer.addLayout(kpi_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 8, 16, 16)
        il.setSpacing(12)

        il.addWidget(self._build_snapshots_card())
        self._diff_card_widget = self._build_diff_card()
        self._diff_card_widget.setVisible(False)
        il.addWidget(self._diff_card_widget)
        il.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

        self._load_snapshots()

    # ── Snapshots card ────────────────────────────────────────────────────────

    def _build_snapshots_card(self) -> QWidget:
        card, bl = _card("Snapshots")

        self._snap_table = QTableWidget(0, 5)
        self._snap_table.setHorizontalHeaderLabels(
            ["Taken", "Label", "Devices", "Open Ports", "ID"]
        )
        self._snap_table.horizontalHeader().setStretchLastSection(False)
        self._snap_table.horizontalHeader().setSectionResizeMode(
            1, __import__("PyQt6.QtWidgets", fromlist=["QHeaderView"]).QHeaderView.ResizeMode.Stretch
        )
        self._snap_table.verticalHeader().setVisible(False)
        self._snap_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._snap_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._snap_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self._snap_table.setAlternatingRowColors(True)
        self._snap_table.setFixedHeight(220)
        self._snap_table.setColumnHidden(4, True)  # hide ID column
        self._snap_table.setStyleSheet(
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )
        for w, col in zip((140, 0, 70, 80), range(4)):
            if w:
                self._snap_table.setColumnWidth(col, w)
        install_copy_menu(self._snap_table)
        bl.addWidget(self._snap_table)

        self._empty_lbl = QLabel(
            "No snapshots yet.  Take your first snapshot to start tracking configuration drift."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; padding:16px 0;"
        )
        bl.addWidget(self._empty_lbl)

        # Label input + action buttons
        action_row = QHBoxLayout()
        action_row.setSpacing(8)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("Snapshot label (optional)")
        self._label_edit.setFixedHeight(26)
        self._label_edit.setMaximumWidth(240)
        self._label_edit.setStyleSheet(
            f"QLineEdit{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 6px;font-size:11px;}}"
            f"QLineEdit:focus{{border-color:{ACCENT};}}"
        )

        self._btn_take   = _btn("📸  Take Snapshot", primary=True)
        self._btn_delete = _btn("Delete")
        self._btn_compare = _btn("Compare Selected (2)")
        self._btn_compare.setToolTip("Select exactly 2 rows, then click Compare")

        self._btn_take.clicked.connect(self._take_snapshot)
        self._btn_delete.clicked.connect(self._delete_snapshot)
        self._btn_compare.clicked.connect(self._compare_snapshots)

        action_row.addWidget(self._label_edit)
        action_row.addWidget(self._btn_take)
        action_row.addWidget(self._btn_delete)
        action_row.addWidget(self._btn_compare)
        action_row.addStretch()
        bl.addLayout(action_row)

        # Status label
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(self._status_lbl)

        return card

    # ── Diff card ─────────────────────────────────────────────────────────────

    def _build_diff_card(self) -> QWidget:
        card, bl = _card("Snapshot Comparison — Drift Report")

        self._diff_summary = QLabel("")
        self._diff_summary.setStyleSheet(
            f"color:{TEXT_PRIMARY};font-size:11px;padding:4px 0;"
        )
        bl.addWidget(self._diff_summary)

        self._diff_table = QTableWidget(0, 3)
        self._diff_table.setHorizontalHeaderLabels(["Host (IP)", "Category", "Change"])
        self._diff_table.horizontalHeader().setStretchLastSection(True)
        self._diff_table.verticalHeader().setVisible(False)
        self._diff_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._diff_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._diff_table.setAlternatingRowColors(True)
        self._diff_table.setMinimumHeight(180)
        self._diff_table.setStyleSheet(
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )
        for w, col in zip((130, 100), range(2)):
            self._diff_table.setColumnWidth(col, w)
        install_copy_menu(self._diff_table)
        bl.addWidget(self._diff_table)

        btn_export_diff = _btn("↓ Export HTML")
        btn_export_diff.clicked.connect(self._export_diff_html)
        diff_btn_row = QHBoxLayout()
        diff_btn_row.addWidget(btn_export_diff)
        diff_btn_row.addStretch()
        bl.addLayout(diff_btn_row)

        return card

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_snapshots(self) -> None:
        if self._store is None:
            return
        self._snapshots = _list_snapshots(self._store, limit=200)
        self._refresh_table()
        self._update_kpis()

    def _refresh_table(self) -> None:
        self._snap_table.setRowCount(0)
        self._empty_lbl.setVisible(not self._snapshots)
        for snap in self._snapshots:
            row = self._snap_table.rowCount()
            self._snap_table.insertRow(row)
            ts_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(snap.ts))
            total_ports = sum(len(d.open_ports) for d in snap.devices)
            for col, val in enumerate([
                ts_str,
                snap.label or "(no label)",
                str(len(snap.devices)),
                str(total_ports),
                str(snap.id),
            ]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._snap_table.setItem(row, col, item)

    def _update_kpis(self) -> None:
        count = len(self._snapshots)
        last  = time.strftime("%Y-%m-%d", time.localtime(self._snapshots[0].ts)) if self._snapshots else "—"
        self._kpi_count.findChild(QLabel, "kpi_val").setText(str(count))
        self._kpi_last.findChild(QLabel, "kpi_val").setText(last)

    # ── Take snapshot ─────────────────────────────────────────────────────────

    @pyqtSlot()
    def _take_snapshot(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._btn_take.setEnabled(False)
        self._btn_take.setText("⏳ Scanning…")
        self._status_lbl.setText("Discovery running…")
        label = self._label_edit.text().strip()

        self._worker = _SnapshotWorker(parent=None)
        self._worker.result_ready.connect(lambda devices: self._on_scan_done(devices, label))
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _on_scan_done(self, devices: list, label: str) -> None:
        if self._store:
            snap = build_snapshot_from_scan(devices, label=label)
            _store_snapshot(self._store, snap)
        self._btn_take.setEnabled(True)
        self._btn_take.setText("📸  Take Snapshot")
        self._label_edit.clear()
        self._status_lbl.setText(
            f"Snapshot captured — {len(devices)} device(s) found."
        )
        self._load_snapshots()

    def _on_scan_error(self, err: str) -> None:
        self._btn_take.setEnabled(True)
        self._btn_take.setText("📸  Take Snapshot")
        self._status_lbl.setText(f"Scan error: {err}")

    # ── Delete snapshot ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _delete_snapshot(self) -> None:
        rows = self._snap_table.selectionModel().selectedRows()
        if not rows:
            return
        ids = []
        for idx in rows:
            id_item = self._snap_table.item(idx.row(), 4)
            if id_item:
                ids.append(int(id_item.text()))
        if not ids:
            return
        reply = QMessageBox.question(
            self,
            "Delete Snapshot(s)",
            f"Delete {len(ids)} snapshot(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        for sid in ids:
            _delete_snapshot(self._store, sid)
        self._load_snapshots()
        self._diff_card_widget.setVisible(False)

    # ── Compare snapshots ─────────────────────────────────────────────────────

    @pyqtSlot()
    def _compare_snapshots(self) -> None:
        rows = self._snap_table.selectionModel().selectedRows()
        if len(rows) != 2:
            self._status_lbl.setText("Select exactly 2 snapshots to compare.")
            return

        ids = []
        for idx in rows:
            id_item = self._snap_table.item(idx.row(), 4)
            if id_item:
                ids.append(int(id_item.text()))
        if len(ids) != 2:
            return

        s1 = _load_snapshot(self._store, ids[0])
        s2 = _load_snapshot(self._store, ids[1])
        if not s1 or not s2:
            self._status_lbl.setText("Could not load snapshots.")
            return

        # old = the earlier one
        old, new = (s1, s2) if s1.ts <= s2.ts else (s2, s1)
        diff = diff_snapshots(old, new)
        self._show_diff(diff, old, new)

    def _show_diff(self, diff: SnapshotDiff, old: ConfigSnapshot, new: ConfigSnapshot) -> None:
        old_ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(old.ts))
        new_ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(new.ts))
        self._diff_summary.setText(
            f"Comparing <b>{old_ts} ({old.label or 'baseline'})</b> → "
            f"<b>{new_ts} ({new.label or 'current'})</b> — {diff.summary()}"
        )

        # Update drift KPI
        drift_txt = "Yes" if diff.has_drift else "None"
        drift_col = RED if diff.has_drift else GREEN
        kpi = self._kpi_drift.findChild(QLabel, "kpi_val")
        if kpi:
            kpi.setText(drift_txt)
            kpi.setStyleSheet(f"color:{drift_col};font-size:22px;font-weight:bold;")

        if diff.has_drift:
            self.drift_detected.emit(
                f"Config drift detected: {diff.summary()} ({old_ts} → {new_ts})"
            )

        self._diff_table.setRowCount(0)

        def _add_row(ip: str, category: str, change: str, color: str = TEXT_PRIMARY):
            row = self._diff_table.rowCount()
            self._diff_table.insertRow(row)
            for col, val in enumerate([ip, category, change]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                from PyQt6.QtGui import QColor
                item.setForeground(QColor(color))
                self._diff_table.setItem(row, col, item)

        for ip in diff.added_devices:
            _add_row(ip, "Device", "Added", GREEN)
        for ip in diff.removed_devices:
            _add_row(ip, "Device", "Removed", RED)
        for ip, ch in sorted(diff.changed_ports.items()):
            if ch["added"]:
                _add_row(ip, "Ports", f"Opened: {', '.join(str(p) for p in ch['added'])}", AMBER)
            if ch["removed"]:
                _add_row(ip, "Ports", f"Closed: {', '.join(str(p) for p in ch['removed'])}", TEXT_PRIMARY)
        for ip, ch in sorted(diff.changed_fields.items()):
            for field_name, vals in ch.items():
                _add_row(ip, field_name.capitalize(),
                         f"{vals['old'] or '(blank)'} → {vals['new'] or '(blank)'}", AMBER)
        for ip, oid_ch in sorted(diff.changed_snmp.items()):
            for oid, vals in oid_ch.items():
                _add_row(ip, f"SNMP/{oid}", f"{vals['old']} → {vals['new']}", AMBER)

        if self._diff_table.rowCount() == 0:
            _add_row("—", "—", "No changes detected between these snapshots", GREEN)

        self._diff_card_widget.setVisible(True)
        self._last_diff_summary = self._diff_summary.text()

    def _export_diff_html(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        from ui.widgets.toast import ToastManager
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Drift Report", "baseline_diff.html", "HTML files (*.html)"
        )
        if not path:
            return
        tbl = self._diff_table
        rows_html = ""
        colors = {GREEN: "#27ae60", RED: "#e74c3c", AMBER: "#f39c12", TEXT_PRIMARY: "#333"}
        for r in range(tbl.rowCount()):
            cells = ""
            for c in range(tbl.columnCount()):
                it = tbl.item(r, c)
                txt = it.text() if it else ""
                fg = it.foreground().color().name() if it else "#333"
                cells += f'<td style="padding:4px 8px;color:{fg}">{txt}</td>'
            rows_html += f"<tr>{cells}</tr>\n"
        summary_txt = getattr(self, "_last_diff_summary", "")
        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>NetSentinel Baseline Diff</title>
<style>body{{font-family:sans-serif;background:#f5f5f5;padding:16px}}
table{{border-collapse:collapse;width:100%;background:#fff;box-shadow:0 1px 3px #ccc}}
th{{background:#0078d4;color:#fff;padding:6px 8px;text-align:left}}
tr:nth-child(even){{background:#f9f9f9}}
</style></head><body>
<h2>NetSentinel — Baseline Drift Report</h2>
<p>{summary_txt}</p>
<table><tr><th>Host (IP)</th><th>Category</th><th>Change</th></tr>
{rows_html}</table>
</body></html>"""
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(html)
            import os
            ToastManager.show(f"✓ Saved to {os.path.basename(path)}", "success")
        except Exception as exc:
            ToastManager.show(f"Export failed: {exc}", "error")

    # ── ACT-7: schedule strip ─────────────────────────────────────────────────

    def _build_schedule_strip(self) -> QFrame:
        strip = QFrame()
        strip.setStyleSheet(
            f"QFrame {{ background:{BG_HOVER}; border:none;"
            f" border-bottom:1px solid {BORDER}; }}"
        )
        lay = QHBoxLayout(strip)
        lay.setContentsMargins(16, 6, 16, 6)
        lay.setSpacing(8)

        self._sched_lbl = QLabel()
        self._sched_lbl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        lay.addWidget(self._sched_lbl)
        lay.addStretch()

        # Inline edit widget (hidden until [Edit] clicked)
        self._sched_edit_widget = QFrame()
        self._sched_edit_widget.setStyleSheet("QFrame { background:transparent; border:none; }")
        edit_lay = QHBoxLayout(self._sched_edit_widget)
        edit_lay.setContentsMargins(0, 0, 0, 0)
        edit_lay.setSpacing(6)
        _every_lbl = QLabel("every")
        _every_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
        self._sched_spin = QSpinBox()
        self._sched_spin.setRange(1, 10)
        self._sched_spin.setValue(3)
        self._sched_spin.setFixedWidth(55)
        self._sched_spin.setFixedHeight(24)
        self._sched_spin.setStyleSheet(
            f"font-size:11px; border:1px solid {BORDER}; padding:2px 4px;"
        )
        _scans_lbl = QLabel("scans")
        _scans_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;")
        btn_save = QPushButton("Save")
        btn_save.setFixedHeight(24)
        btn_save.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; padding:0 10px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
        btn_save.clicked.connect(self._save_schedule)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(24)
        btn_cancel.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TEXT_MUTED}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:0 8px; font-size:11px; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{TEXT_MUTED}; }}"
        )
        btn_cancel.clicked.connect(self._cancel_schedule_edit)
        edit_lay.addWidget(_every_lbl)
        edit_lay.addWidget(self._sched_spin)
        edit_lay.addWidget(_scans_lbl)
        edit_lay.addWidget(btn_save)
        edit_lay.addWidget(btn_cancel)
        self._sched_edit_widget.setVisible(False)
        lay.addWidget(self._sched_edit_widget)

        self._sched_btn = QPushButton()
        self._sched_btn.setFixedHeight(24)
        self._sched_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{ACCENT}; border:1px solid {ACCENT}44;"
            f" border-radius:3px; padding:0 10px; font-size:11px; }}"
            f"QPushButton:hover {{ background:{ACCENT}18; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._sched_btn.clicked.connect(self._toggle_schedule_edit)
        lay.addWidget(self._sched_btn)

        self._refresh_schedule_strip()
        return strip

    def _refresh_schedule_strip(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        enabled = qs.value("baseline/auto_snapshot", False, type=bool)
        every = int(qs.value("baseline/auto_snapshot_every", 3) or 3)
        if enabled:
            self._sched_lbl.setText(
                f"Auto-snapshot: every {every} scan{'s' if every != 1 else ''}"
            )
            self._sched_btn.setText("Edit")
        else:
            self._sched_lbl.setText("Auto-snapshot: off")
            self._sched_btn.setText("Enable")

    def _toggle_schedule_edit(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        enabled = qs.value("baseline/auto_snapshot", False, type=bool)
        if not enabled:
            # Enable immediately with default interval
            qs.setValue("baseline/auto_snapshot", True)
        every = int(qs.value("baseline/auto_snapshot_every", 3) or 3)
        self._sched_spin.setValue(every)
        self._sched_edit_widget.setVisible(True)
        self._sched_btn.setVisible(False)

    def _save_schedule(self) -> None:
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("baseline/auto_snapshot", True)
        qs.setValue("baseline/auto_snapshot_every", self._sched_spin.value())
        self._sched_edit_widget.setVisible(False)
        self._sched_btn.setVisible(True)
        self._refresh_schedule_strip()

    def _cancel_schedule_edit(self) -> None:
        self._sched_edit_widget.setVisible(False)
        self._sched_btn.setVisible(True)

