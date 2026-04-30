"""
CVE Tracker Page — vulnerability lifecycle management (Tier 1 quick win #2).

Shows all CVEs discovered during port scans with full lifecycle tracking:
  - State: Open | Acknowledged | Accepted Risk | Remediated
  - Owner, notes, days open, CVSS score
  - Import from scan output (service version strings)
  - Filter by state

Extends the existing inline CVE lookup in the Security Audit tab.
This page stores lifecycle state in MetricStore.cve_lifecycle (schema v7).
"""
from __future__ import annotations

import time
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui  import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMenu, QPlainTextEdit, QPushButton, QSizePolicy,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from modules.metric_store import MetricStore
from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BORDER, CRITICAL, GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
)

# ── CVE state definitions ─────────────────────────────────────────────────────

CVE_STATES = ["Open", "Acknowledged", "Accepted Risk", "Remediated"]

_STATE_COLORS = {
    "Open":          RED,
    "Acknowledged":  AMBER,
    "Accepted Risk": TEXT_SECONDARY,
    "Remediated":    GREEN,
}

_SEVERITY_COLORS = {
    "CRITICAL": CRITICAL,
    "HIGH":     RED,
    "MEDIUM":   AMBER,
    "LOW":      ACCENT,
    "NONE":     TEXT_MUTED,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _table(cols: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(cols))
    t.setHorizontalHeaderLabels(cols)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.horizontalHeader().setStretchLastSection(True)
    t.setStyleSheet(
        f"QTableWidget {{ font-size:11px; color:{TEXT_PRIMARY}; gridline-color:#EAEAEA;"
        f" alternate-background-color:#F7F9FC; background:{BG_CARD}; border:none; }}"
        f"QTableWidget::item:hover {{ background:#EEF4FF; }}"
        f"QTableWidget::item:selected {{ background:#CCE4F7; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
        f" font-weight:bold; padding:4px 5px; border:none; }}"
    )
    return t


def _card(title: str) -> tuple[QWidget, QVBoxLayout]:
    outer = QWidget()
    outer.setStyleSheet(
        f"QWidget {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0px; }}"
    )
    ol = QVBoxLayout(outer)
    ol.setContentsMargins(0, 0, 0, 0)
    ol.setSpacing(0)
    hdr = QLabel(title)
    hdr.setStyleSheet(
        f"background:{BG_CARD}; border-bottom:1px solid #ECECEC;"
        f" padding:4px 12px; font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
    )
    ol.addWidget(hdr)
    body = QWidget()
    body.setStyleSheet(f"background:{BG_CARD}; border:none;")
    bl = QVBoxLayout(body)
    bl.setContentsMargins(12, 8, 12, 8)
    bl.setSpacing(6)
    ol.addWidget(body)
    return outer, bl


def _kpi_tile(label: str, value: str = "0", accent: str = ACCENT) -> tuple[QWidget, QLabel]:
    tile = QWidget()
    tile.setStyleSheet(
        f"background:{BG_CARD}; border:1px solid {BORDER};"
        f" border-left:3px solid {accent}; padding:4px 8px;"
    )
    tile.setMinimumWidth(110)
    tile.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    lay = QVBoxLayout(tile)
    lay.setContentsMargins(6, 4, 6, 4)
    lay.setSpacing(2)
    lbl = QLabel(label.upper())
    lbl.setStyleSheet(f"font-size:9px; font-weight:bold; color:{TEXT_SECONDARY}; border:none;")
    val = QLabel(value)
    val.setStyleSheet(f"font-size:22px; font-weight:bold; color:{TEXT_PRIMARY}; border:none;")
    lay.addWidget(lbl)
    lay.addWidget(val)
    return tile, val


# ── State-change dialog ───────────────────────────────────────────────────────

class _StateDialog(QDialog):
    def __init__(self, cve_id: str, current_state: str, owner: str, notes: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Update State — {cve_id}")
        self.setMinimumWidth(400)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self._combo = QComboBox()
        self._combo.addItems(CVE_STATES)
        idx = CVE_STATES.index(current_state) if current_state in CVE_STATES else 0
        self._combo.setCurrentIndex(idx)
        form.addRow("State:", self._combo)

        self._owner = QLineEdit(owner)
        self._owner.setPlaceholderText("Assigned to (optional)")
        form.addRow("Owner:", self._owner)

        self._notes = QPlainTextEdit(notes)
        self._notes.setFixedHeight(80)
        self._notes.setPlaceholderText("Notes / remediation steps…")
        form.addRow("Notes:", self._notes)

        lay.addLayout(form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    @property
    def state(self) -> str:
        return self._combo.currentText()

    @property
    def owner(self) -> str:
        return self._owner.text().strip()

    @property
    def notes(self) -> str:
        return self._notes.toPlainText().strip()


# ── Import dialog ─────────────────────────────────────────────────────────────

class _ImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import CVEs from Scan")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)

        info = QLabel(
            "Paste service version strings (one per line) or comma-separated.\n"
            "Example:  OpenSSH 8.9p1, Apache/2.4.54, nginx/1.18.0"
        )
        info.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        info.setWordWrap(True)
        lay.addWidget(info)

        host_row = QHBoxLayout()
        host_lbl = QLabel("Host (optional):")
        host_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_PRIMARY};")
        self._host = QLineEdit()
        self._host.setPlaceholderText("192.168.1.100")
        host_row.addWidget(host_lbl)
        host_row.addWidget(self._host)
        lay.addLayout(host_row)

        self._text = QPlainTextEdit()
        self._text.setFixedHeight(120)
        self._text.setPlaceholderText("OpenSSH 8.9p1\nApache/2.4.54\nnginx/1.18.0")
        lay.addWidget(self._text)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    @property
    def services(self) -> list[str]:
        raw = self._text.toPlainText()
        parts = [s.strip() for s in raw.replace(",", "\n").splitlines() if s.strip()]
        return parts

    @property
    def host(self) -> str:
        return self._host.text().strip()


# ── Main page ─────────────────────────────────────────────────────────────────

class CvePage(QWidget):
    """CVE lifecycle tracker page — Security Audit section."""

    def __init__(self, store: MetricStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._rows: list[dict] = []       # current displayed rows
        self._setup_ui()
        self._refresh()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setObjectName("CvePage")
        self.setStyleSheet(f"QWidget#CvePage {{ background:{BG_DARK}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Page title
        title = QLabel("CVE Lifecycle Tracker")
        title.setStyleSheet(f"font-size:18px; font-weight:bold; color:{TEXT_PRIMARY};")
        sub = QLabel(
            "Track discovered CVEs from Open through to Remediated. "
            "Import from scan results or add manually."
        )
        sub.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")
        root.addWidget(title)
        root.addWidget(sub)

        # KPI row
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)
        _, self._kpi_total   = _kpi_tile("Total CVEs",      "0", ACCENT)
        _, self._kpi_open    = _kpi_tile("Open",             "0", RED)
        _, self._kpi_ack     = _kpi_tile("Acknowledged",     "0", AMBER)
        _, self._kpi_risk    = _kpi_tile("Accepted Risk",    "0", TEXT_SECONDARY)
        _, self._kpi_fixed   = _kpi_tile("Remediated",       "0", GREEN)
        _, self._kpi_crit    = _kpi_tile("Critical/High",    "0", CRITICAL)
        for tile, _ in [
            _kpi_tile("Total CVEs", "0", ACCENT),
            _kpi_tile("Open", "0", RED),
            _kpi_tile("Acknowledged", "0", AMBER),
            _kpi_tile("Accepted Risk", "0", TEXT_SECONDARY),
            _kpi_tile("Remediated", "0", GREEN),
            _kpi_tile("Critical/High", "0", CRITICAL),
        ]:
            kpi_row.addWidget(tile)
        kpi_row.addStretch()

        # Re-build properly (tiles are created as pairs, we need the labels)
        kpi_row2 = QHBoxLayout()
        kpi_row2.setSpacing(10)
        t1, self._kpi_total = _kpi_tile("Total CVEs",   "0", ACCENT)
        t2, self._kpi_open  = _kpi_tile("Open",         "0", RED)
        t3, self._kpi_ack   = _kpi_tile("Acknowledged", "0", AMBER)
        t4, self._kpi_risk  = _kpi_tile("Accepted Risk","0", TEXT_SECONDARY)
        t5, self._kpi_fixed = _kpi_tile("Remediated",   "0", GREEN)
        t6, self._kpi_crit  = _kpi_tile("Critical/High","0", CRITICAL)
        for t in (t1, t2, t3, t4, t5, t6):
            kpi_row2.addWidget(t)
        kpi_row2.addStretch()
        root.addLayout(kpi_row2)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._filter_combo = QComboBox()
        self._filter_combo.addItems(["All States"] + CVE_STATES)
        self._filter_combo.setFixedWidth(150)
        self._filter_combo.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 4px;"
        )
        self._filter_combo.currentTextChanged.connect(self._refresh)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter by CVE ID, service, host…")
        self._search_box.setFixedWidth(240)
        self._search_box.setStyleSheet(
            f"font-size:11px; color:{TEXT_PRIMARY}; border:1px solid {BORDER}; padding:2px 6px;"
        )
        self._search_box.textChanged.connect(self._apply_filter)

        btn_import = QPushButton("Import from Scan")
        btn_import.setFixedHeight(34)
        btn_import.setStyleSheet(
            f"font-size:12px; font-weight:bold; color:white; background:{ACCENT};"
            f" border:none; padding:0 14px; border-radius:4px;"
        )
        btn_import.clicked.connect(self._import_dialog)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setFixedHeight(34)
        btn_refresh.setStyleSheet(
            f"font-size:12px; color:{ACCENT}; border:1px solid {ACCENT};"
            f" background:white; padding:0 14px; border-radius:4px;"
        )
        btn_refresh.clicked.connect(self._refresh)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"font-size:11px; color:{TEXT_SECONDARY};")

        toolbar.addWidget(QLabel("Filter:"))
        toolbar.addWidget(self._filter_combo)
        toolbar.addWidget(self._search_box)
        toolbar.addStretch()
        toolbar.addWidget(self._status_lbl)
        toolbar.addWidget(btn_refresh)
        toolbar.addWidget(btn_import)
        root.addLayout(toolbar)

        # Table card
        card, card_lay = _card("CVE Inventory")
        card_lay.setContentsMargins(0, 0, 0, 0)

        self._table = _table([
            "CVE ID", "CVSS", "Severity", "Service", "Host",
            "State", "Owner", "Days Open", "Description",
        ])
        self._table.setColumnWidth(0, 130)
        self._table.setColumnWidth(1, 50)
        self._table.setColumnWidth(2, 75)
        self._table.setColumnWidth(3, 140)
        self._table.setColumnWidth(4, 115)
        self._table.setColumnWidth(5, 110)
        self._table.setColumnWidth(6, 100)
        self._table.setColumnWidth(7, 75)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._context_menu)
        card_lay.addWidget(self._table)

        self._lbl_empty = QLabel(
            "No CVEs tracked yet. Run the port scanner then use \"Import from Scan\" "
            "to import discovered service versions."
        )
        self._lbl_empty.setStyleSheet(f"font-size:11px; color:#9BA8B4; padding:16px;")
        self._lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self._lbl_empty)

        root.addWidget(card, 1)

    # ── Data ──────────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        if self._store is None:
            return
        state_filter = self._filter_combo.currentText()
        if state_filter == "All States":
            state_filter = None
        self._rows = self._store.list_cve_lifecycles(state_filter)
        self._apply_filter(self._search_box.text())
        self._update_kpis()

    def _update_kpis(self) -> None:
        if self._store is None:
            return
        all_rows = self._store.list_cve_lifecycles(None)
        total = len(all_rows)
        open_  = sum(1 for r in all_rows if r["state"] == "Open")
        ack    = sum(1 for r in all_rows if r["state"] == "Acknowledged")
        risk   = sum(1 for r in all_rows if r["state"] == "Accepted Risk")
        fixed  = sum(1 for r in all_rows if r["state"] == "Remediated")
        crit   = sum(1 for r in all_rows if r["severity"] in ("CRITICAL", "HIGH"))
        self._kpi_total.setText(str(total))
        self._kpi_open.setText(str(open_))
        self._kpi_ack.setText(str(ack))
        self._kpi_risk.setText(str(risk))
        self._kpi_fixed.setText(str(fixed))
        self._kpi_crit.setText(str(crit))

    def _apply_filter(self, text: str = "") -> None:
        query = text.strip().lower()
        rows = self._rows
        if query:
            rows = [
                r for r in rows
                if query in r["cve_id"].lower()
                or query in (r["service"] or "").lower()
                or query in (r["host"] or "").lower()
                or query in (r["description"] or "").lower()
            ]
        self._populate_table(rows)
        visible = len(rows)
        total   = len(self._rows)
        self._status_lbl.setText(
            f"Showing {visible} of {total} CVE(s)" if visible != total else f"{total} CVE(s)"
        )

    def _populate_table(self, rows: list[dict]) -> None:
        self._table.setRowCount(0)
        now = int(time.time())
        for r in rows:
            row_idx = self._table.rowCount()
            self._table.insertRow(row_idx)

            days_open = max(0, (now - r["opened_ts"]) // 86400)
            severity  = (r["severity"] or "").upper()
            state     = r["state"]

            def _item(text: str) -> QTableWidgetItem:
                it = QTableWidgetItem(str(text))
                it.setData(Qt.ItemDataRole.UserRole, r["id"])
                return it

            self._table.setItem(row_idx, 0, _item(r["cve_id"]))

            score_item = _item(f"{r['cvss_score']:.1f}")
            score_val = float(r["cvss_score"])
            if score_val >= 9.0:
                score_item.setForeground(QColor(CRITICAL))
            elif score_val >= 7.0:
                score_item.setForeground(QColor(RED))
            elif score_val >= 4.0:
                score_item.setForeground(QColor(AMBER))
            self._table.setItem(row_idx, 1, score_item)

            sev_item = _item(severity)
            sev_item.setForeground(QColor(_SEVERITY_COLORS.get(severity, TEXT_PRIMARY)))
            self._table.setItem(row_idx, 2, sev_item)

            self._table.setItem(row_idx, 3, _item(r["service"]))
            self._table.setItem(row_idx, 4, _item(r["host"]))

            state_item = _item(state)
            state_item.setForeground(QColor(_STATE_COLORS.get(state, TEXT_PRIMARY)))
            self._table.setItem(row_idx, 5, state_item)

            self._table.setItem(row_idx, 6, _item(r["owner"]))

            days_item = _item(str(days_open))
            if state != "Remediated" and days_open > 30:
                days_item.setForeground(QColor(RED))
            elif state != "Remediated" and days_open > 7:
                days_item.setForeground(QColor(AMBER))
            self._table.setItem(row_idx, 7, days_item)

            self._table.setItem(row_idx, 8, _item(r["description"]))

        visible = self._table.rowCount() > 0
        self._table.setVisible(visible)
        self._lbl_empty.setVisible(not visible)

    def _selected_row_id(self) -> Optional[int]:
        sel = self._table.selectedItems()
        if not sel:
            return None
        return sel[0].data(Qt.ItemDataRole.UserRole)

    def _selected_row_data(self) -> Optional[dict]:
        row_id = self._selected_row_id()
        if row_id is None:
            return None
        for r in self._rows:
            if r["id"] == row_id:
                return r
        return None

    # ── Context menu ──────────────────────────────────────────────────────────

    def _context_menu(self, pos) -> None:
        row_data = self._selected_row_data()
        if not row_data:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:white; border:1px solid {BORDER}; font-size:11px; }}"
            f"QMenu::item {{ padding:4px 20px; }}"
            f"QMenu::item:selected {{ background:#EEF4FF; }}"
        )
        act_state  = menu.addAction("Change State…")
        menu.addSeparator()
        act_copy   = menu.addAction("Copy CVE ID")
        act_nvd    = menu.addAction("Open in NVD Browser")
        menu.addSeparator()
        act_delete = menu.addAction("Delete Entry")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == act_state:
            self._change_state(row_data)
        elif chosen == act_copy:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(row_data["cve_id"])
        elif chosen == act_nvd:
            import webbrowser
            webbrowser.open(f"https://nvd.nist.gov/vuln/detail/{row_data['cve_id']}")
        elif chosen == act_delete:
            self._store.delete_cve_lifecycle(row_data["id"])
            self._refresh()

    def _change_state(self, row_data: dict) -> None:
        dlg = _StateDialog(
            cve_id=row_data["cve_id"],
            current_state=row_data["state"],
            owner=row_data["owner"],
            notes=row_data["notes"],
            parent=self,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._store.update_cve_state(
                row_data["id"],
                dlg.state,
                dlg.owner,
                dlg.notes,
            )
            self._refresh()

    # ── Import dialog ─────────────────────────────────────────────────────────

    def _import_dialog(self) -> None:
        dlg = _ImportDialog(parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        services = dlg.services
        host     = dlg.host or ""
        if not services:
            return

        self._status_lbl.setText("Looking up CVEs…")
        self._status_lbl.repaint()

        try:
            from modules.cve_lookup import lookup as lookup_cve
        except ImportError:
            self._status_lbl.setText("cve_lookup module unavailable.")
            return

        imported = 0
        for svc in services:
            try:
                result = lookup_cve(svc)
                for cve in result.cves:
                    self._store.upsert_cve_lifecycle(
                        cve_id      = cve.cve_id,
                        service     = svc,
                        host        = host,
                        cvss_score  = cve.cvss_score,
                        severity    = cve.severity,
                        description = cve.description[:300],
                    )
                    imported += 1
            except Exception:
                pass

        self._refresh()
        self._status_lbl.setText(f"Imported {imported} CVE(s) from {len(services)} service(s).")
