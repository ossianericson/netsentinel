"""
ui/pages/app_traffic_page.py — Per-Host Application Traffic Breakdown
======================================================================
Shows which protocols and application categories each device is using,
based on port-heuristic classification of live packet capture.

Layout
------
  Page header
  Controls row: [Host selector] [status] [Start/Stop button]
  Card: Horizontal stacked bar chart — hosts on Y, categories as coloured segments
  Card: Detail table — per-protocol breakdown for the selected host
"""

from __future__ import annotations

from typing import Dict, List, Optional

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.colours import APP_CATEGORY_COLORS
from modules.app_traffic_classifier import CATEGORY_ORDER as _CAT_ORDER
from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE,
    BG_ALT_ROW, BG_CARD, BORDER,
    CHART_AXIS, CHART_BG, CHART_GRID, CHART_PLOT_BG,
    GREEN, RED, RED_DARK, RED_HOVER, TABLE_ROW_BORDER, TABLE_SEL,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
    TH_BG, TH_BORDER, TH_TEXT, WHITE,
)
from ui.widgets.empty_state_card import EmptyStateCard

_INTERVAL_S = 10.0   # capture window length in seconds
_MAX_HOSTS  = 12     # max hosts shown simultaneously in chart


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_bytes(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f} KB"
    return f"{n} B"


def _cat_color(cat: str) -> str:
    return APP_CATEGORY_COLORS.get(cat, APP_CATEGORY_COLORS["Other"])


def _make_card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setStyleSheet(
        f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    hdr = QFrame()
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(f"background:{TH_BG}; border:none; border-radius:0;")
    hdr_lay = QHBoxLayout(hdr)
    hdr_lay.setContentsMargins(12, 0, 12, 0)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        f"color:{TH_TEXT}; font-size:11px; font-weight:bold;"
        f" background:transparent; border:none;"
    )
    hdr_lay.addWidget(lbl)
    outer.addWidget(hdr)

    body = QVBoxLayout()
    body.setContentsMargins(8, 8, 8, 8)
    body.setSpacing(6)
    outer.addLayout(body)
    return card, body


# ── Main page ─────────────────────────────────────────────────────────────────

class AppTrafficPage(QWidget):
    """Per-host application-layer traffic breakdown."""

    scan_requested = pyqtSignal()   # RULE-UX5 compatibility (not used here)
    #: Emitted on every snapshot with the top bandwidth consumer (S5-4).
    #: Payload: {"label": str, "bytes_total": int, "share_pct": float, "window_s": float}
    top_host_changed = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._worker = None
        self._running = False

        # {label/mac -> AppHostSnapshot} — last received data per host
        self._snapshots: Dict[str, object] = {}
        self._selected_host = "All Hosts"

        self._setup_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        from ui.widgets.page_header import PageHeaderBar
        root.addWidget(PageHeaderBar("App Traffic", subtitle="Shows which applications and devices are using your bandwidth right now."))

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        hl = QLabel("Host:")
        hl.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; background:transparent; border:none;"
        )
        self._host_combo = QComboBox()
        self._host_combo.setMinimumWidth(240)
        self._host_combo.setStyleSheet(
            f"QComboBox {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" padding:3px 8px; font-size:11px; min-height:26px; }}"
        )
        self._host_combo.addItem("All Hosts")
        self._host_combo.currentTextChanged.connect(self._on_host_changed)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            f"font-size:10px; color:{TEXT_MUTED}; background:transparent; border:none;"
        )

        self._toggle_btn = QPushButton("▶  Start Monitoring")
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; font-size:11px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:hover   {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._toggle_btn.clicked.connect(self._toggle_monitoring)

        ctrl.addWidget(hl)
        ctrl.addWidget(self._host_combo)
        ctrl.addStretch()
        ctrl.addWidget(self._status_lbl)
        ctrl.addWidget(self._toggle_btn)
        root.addLayout(ctrl)

        # Content stack: 0 = empty state, 1 = live charts
        self._content_stack = QStackedWidget()

        empty = EmptyStateCard(
            icon="◆",
            title="App Traffic Analyzer",
            what_it_shows=(
                "Shows which protocols and applications each device is using — "
                "Web, DNS, Streaming, Gaming, VPN, P2P, and more — broken down "
                "by bytes per 10-second window."
            ),
            why_it_matters=(
                "Reveals unexpected traffic: a device secretly torrenting, "
                "an IoT device phoning home, or a machine routing through "
                "a VPN tunnel you didn't configure."
            ),
            btn_label="Start Monitoring",
        )
        empty.clicked.connect(self._toggle_monitoring)
        self._content_stack.addWidget(empty)

        # Index 1: live charts
        charts_w = QWidget()
        cl = QVBoxLayout(charts_w)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)

        # Stacked bar chart
        bar_card, bar_body = _make_card(
            "HOST BREAKDOWN  —  BYTES PER PROTOCOL CATEGORY  (LAST 10 s)"
        )
        self._fig = Figure(figsize=(10, 3.5), facecolor=CHART_BG)
        self._fig.subplots_adjust(left=0.25, right=0.98, top=0.95, bottom=0.15)
        self._ax = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setStyleSheet(f"background:{CHART_BG}; border:none;")
        self._canvas.setMinimumHeight(120)
        bar_body.addWidget(self._canvas)
        cl.addWidget(bar_card, 2)

        # Category legend
        legend_card = QFrame()
        legend_card.setStyleSheet(
            f"background:{BG_CARD}; border:1px solid {BORDER}; border-radius:0;"
        )
        self._legend_lay = QHBoxLayout(legend_card)
        self._legend_lay.setContentsMargins(12, 6, 12, 6)
        self._legend_lay.setSpacing(14)
        self._legend_items: List[QLabel] = []
        self._build_legend()
        cl.addWidget(legend_card)

        # Detail table
        tbl_card, tbl_body = _make_card(
            "PROTOCOL DETAIL  —  SELECT A HOST ABOVE OR FROM THE DROPDOWN"
        )
        self._tbl = QTableWidget(0, 4)
        self._tbl.setHorizontalHeaderLabels(
            ["Category", "Protocol / App", "Bytes", "% of Traffic"]
        )
        self._tbl.horizontalHeader().setStretchLastSection(True)
        for col, width in enumerate([110, 150, 90]):
            self._tbl.setColumnWidth(col, width)
            self._tbl.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Interactive
            )
        self._tbl.setAlternatingRowColors(True)
        self._tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.verticalHeader().setDefaultSectionSize(24)
        self._tbl.setMaximumHeight(220)
        self._tbl.setStyleSheet(
            f"QTableWidget {{ border:none; font-size:11px; color:{TEXT_PRIMARY}; }}"
            f"QHeaderView::section {{"
            f"  background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
            f"  font-weight:bold; padding:4px 5px; border:none;"
            f"  border-right:1px solid {TH_BORDER};"
            f"}}"
            f"QTableWidget::item:selected {{ background:{TABLE_SEL}; color:{TEXT_PRIMARY}; }}"
            f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
            f"QTableWidget::item {{ border-bottom:1px solid {TABLE_ROW_BORDER}; }}"
        )
        self._tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tbl.customContextMenuRequested.connect(self._ctx_menu)
        tbl_body.addWidget(self._tbl)
        cl.addWidget(tbl_card, 1)

        self._content_stack.addWidget(charts_w)
        root.addWidget(self._content_stack, 1)

        self._draw_empty_chart()

    # ── Monitoring lifecycle ──────────────────────────────────────────────────

    def _toggle_monitoring(self) -> None:
        if self._running:
            self._stop_worker()
        else:
            self._start_worker()

    def _start_worker(self) -> None:
        if self._running:
            return
        from workers.app_traffic_worker import AppTrafficWorker
        self._worker = AppTrafficWorker(interval_s=_INTERVAL_S, parent=self)
        self._worker.snapshot_ready.connect(self._on_snapshot)
        self._worker.error.connect(self._on_error)
        self._worker.start()
        self._running = True
        self._toggle_btn.setText("■  Stop Monitoring")
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{RED}; color:{WHITE}; border:none;"
            f" border-radius:3px; font-size:11px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:hover   {{ background:{RED_HOVER}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{RED_DARK}; color:{WHITE}; }}"
        )
        self._status_lbl.setText(f"Monitoring  •  {_INTERVAL_S:.0f} s window")

    def _stop_worker(self) -> None:
        if self._worker:
            self._worker.stop()
            self._worker.wait(3000)
            self._worker = None
        self._running = False
        self._toggle_btn.setText("▶  Start Monitoring")
        self._toggle_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f" border-radius:3px; font-size:11px; font-weight:bold; padding:0 14px; }}"
            f"QPushButton:hover   {{ background:{ACCENT_LITE}; color:{WHITE}; }}"
            f"QPushButton:pressed {{ background:{ACCENT_DARK}; color:{WHITE}; }}"
        )
        self._status_lbl.setText("Stopped")

    def closeEvent(self, event) -> None:
        self._stop_worker()
        super().closeEvent(event)

    # ── External label map (from scan result) ─────────────────────────────────

    def set_label_map(self, label_map: dict) -> None:
        """Pass MAC→display-name mapping from latest scan result."""
        if self._worker:
            self._worker.set_label_map(label_map)

    # ── Slot: new snapshot ────────────────────────────────────────────────────

    @pyqtSlot(object)
    def _on_snapshot(self, snap) -> None:
        self._content_stack.setCurrentIndex(1)

        # Update per-host data keyed by display label
        for host in snap.hosts:
            key = host.label or host.mac
            self._snapshots[key] = host

        self._refresh_host_combo()
        self._redraw_chart()
        self._refresh_detail_table()
        self._status_lbl.setText(
            f"Monitoring  •  {_INTERVAL_S:.0f} s window  •  "
            f"{len(self._snapshots)} host(s) active"
        )
        self._emit_top_host()

    def _emit_top_host(self) -> None:
        """Emit the current top bandwidth consumer for the home page card (S5-4)."""
        if not self._snapshots:
            return
        total = sum(h.total_bytes for h in self._snapshots.values())
        if total <= 0:
            return
        top = max(self._snapshots.values(), key=lambda h: h.total_bytes)
        self.top_host_changed.emit({
            "label": top.label or top.mac,
            "bytes_total": top.total_bytes,
            "share_pct": (top.total_bytes / total * 100) if total else 0.0,
            "window_s": top.window_s,
        })

    def _on_error(self, msg: str) -> None:
        self._ax.clear()
        self._ax.set_facecolor(CHART_PLOT_BG)
        self._ax.text(
            0.5, 0.5, msg,
            ha="center", va="center", fontsize=8,
            color=RED, transform=self._ax.transAxes,
        )
        self._canvas.draw_idle()
        self._stop_worker()
        self._status_lbl.setText("Error — see chart for details")

    # ── Host combo ────────────────────────────────────────────────────────────

    def _refresh_host_combo(self) -> None:
        current = self._host_combo.currentText()
        self._host_combo.blockSignals(True)
        self._host_combo.clear()
        self._host_combo.addItem("All Hosts")
        for label in sorted(self._snapshots.keys()):
            self._host_combo.addItem(label)
        idx = self._host_combo.findText(current)
        self._host_combo.setCurrentIndex(max(idx, 0))
        self._host_combo.blockSignals(False)

    @pyqtSlot(str)
    def _on_host_changed(self, text: str) -> None:
        self._selected_host = text
        self._redraw_chart()
        self._refresh_detail_table()

    # ── Chart ─────────────────────────────────────────────────────────────────

    def _draw_empty_chart(self) -> None:
        ax = self._ax
        ax.clear()
        ax.set_facecolor(CHART_PLOT_BG)
        self._fig.patch.set_facecolor(CHART_BG)
        ax.tick_params(colors=CHART_AXIS, labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER)
        ax.text(
            0.5, 0.5,
            "Start monitoring to see per-host protocol breakdown",
            ha="center", va="center", fontsize=9,
            color=TEXT_MUTED, transform=ax.transAxes,
        )
        self._canvas.draw_idle()

    @pyqtSlot()
    def _redraw_chart(self) -> None:
        ax = self._ax
        ax.clear()
        ax.set_facecolor(CHART_PLOT_BG)
        self._fig.patch.set_facecolor(CHART_BG)

        if not self._snapshots:
            self._draw_empty_chart()
            return

        if self._selected_host == "All Hosts":
            hosts_to_show = sorted(
                self._snapshots.values(), key=lambda h: h.total_bytes, reverse=True
            )[:_MAX_HOSTS]
        else:
            h = self._snapshots.get(self._selected_host)
            hosts_to_show = [h] if h else []

        if not hosts_to_show:
            self._draw_empty_chart()
            return

        labels = [h.label or h.mac for h in hosts_to_show]
        y_pos = list(range(len(hosts_to_show)))

        # Compute per-category byte arrays aligned with hosts_to_show
        lefts = [0.0] * len(hosts_to_show)
        for cat in _CAT_ORDER:
            values_kb = []
            for host in hosts_to_show:
                totals = host.category_totals()
                values_kb.append(totals.get(cat, 0) / 1_000)

            if all(v == 0.0 for v in values_kb):
                continue

            ax.barh(
                y_pos, values_kb, left=lefts,
                color=_cat_color(cat), alpha=0.85, height=0.6,
                label=cat,
            )
            lefts = [l + v for l, v in zip(lefts, values_kb)]

        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("KB (this window)", fontsize=8, color=CHART_AXIS)
        ax.tick_params(colors=CHART_AXIS, labelsize=8)
        for sp in ax.spines.values():
            sp.set_edgecolor(BORDER)
        ax.grid(True, axis="x", linestyle="--", linewidth=0.4, color=CHART_GRID)
        self._canvas.draw_idle()

    # ── Legend ────────────────────────────────────────────────────────────────

    def _build_legend(self) -> None:
        for lbl in self._legend_items:
            self._legend_lay.removeWidget(lbl)
            lbl.deleteLater()
        self._legend_items.clear()
        for cat in _CAT_ORDER:
            dot = QLabel(f"● {cat}")
            dot.setStyleSheet(
                f"color:{_cat_color(cat)}; font-size:9px;"
                f" background:transparent; border:none;"
            )
            self._legend_lay.addWidget(dot)
            self._legend_items.append(dot)
        self._legend_lay.addStretch()

    # ── Detail table ──────────────────────────────────────────────────────────

    def _refresh_detail_table(self) -> None:
        self._tbl.setRowCount(0)
        if not self._snapshots:
            return

        if self._selected_host == "All Hosts":
            # Aggregate across all hosts
            agg: Dict[tuple, int] = {}
            total = 0
            for host in self._snapshots.values():
                for flow in host.flows:
                    key = (flow.category, flow.app)
                    agg[key] = agg.get(key, 0) + flow.bytes_total
                    total += flow.bytes_total
            rows = sorted(agg.items(), key=lambda x: -x[1])
        else:
            host = self._snapshots.get(self._selected_host)
            if not host:
                return
            rows = [((f.category, f.app), f.bytes_total) for f in host.flows]
            total = host.total_bytes

        for (cat, app), b in rows:
            pct = (b / total * 100) if total > 0 else 0.0
            row = self._tbl.rowCount()
            self._tbl.insertRow(row)

            cat_item = QTableWidgetItem(cat)
            cat_item.setForeground(QColor(_cat_color(cat)))

            app_item = QTableWidgetItem(app)
            app_item.setForeground(QColor(TEXT_PRIMARY))

            bytes_item = QTableWidgetItem(_fmt_bytes(b))
            bytes_item.setForeground(QColor(TEXT_SECONDARY))

            pct_fg = GREEN if pct > 50 else ACCENT if pct > 10 else TEXT_SECONDARY
            pct_item = QTableWidgetItem(f"{pct:.1f}%")
            pct_item.setForeground(QColor(pct_fg))

            for col, item in enumerate((cat_item, app_item, bytes_item, pct_item)):
                self._tbl.setItem(row, col, item)

    # ── Context menu ──────────────────────────────────────────────────────────

    def _ctx_menu(self, pos) -> None:
        item = self._tbl.itemAt(pos)
        if not item:
            return
        row = item.row()
        menu = QMenu(self)
        copy_act = menu.addAction("Copy Row")
        menu.addSeparator()
        info_act = menu.addAction("What is this protocol?")
        chosen = menu.exec(self._tbl.viewport().mapToGlobal(pos))
        if chosen == copy_act:
            parts = [
                self._tbl.item(row, c).text()
                for c in range(self._tbl.columnCount())
                if self._tbl.item(row, c)
            ]
            QApplication.clipboard().setText("  ".join(parts))
        elif chosen == info_act:
            cat_txt = self._tbl.item(row, 0)
            app_txt = self._tbl.item(row, 1)
            cat = cat_txt.text() if cat_txt else ""
            app = app_txt.text() if app_txt else ""
            QMessageBox.information(
                self, "Protocol Info",
                f"Category: {cat}\nProtocol / App: {app}\n\n"
                f"Traffic is classified by destination TCP/UDP port.\n"
                f"Devices using non-standard ports may appear under 'Other'."
            )
