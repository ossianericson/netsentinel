"""
TrendPage — Predictive trend alerting UI.

Shows linear-regression forecasts for RTT, packet loss, and jitter for every
monitored host. Highlights hosts whose metrics are projected to breach
configured thresholds within a user-selected time horizon.

Architecture rules:
  • All colours from ui/styles — no hardcoded hex values.
  • No blocking I/O on the main thread (QThread for analysis run).
  • MetricStore injected via constructor.
"""
from __future__ import annotations

import time
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, AMBER_BG, BG_ALT_ROW, BG_CARD, BG_DARK,
    BORDER, CARD_HDR_BORDER, CARD_RADIUS, GREEN, RED, RED_BG,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from modules.trend_analyser import TrendResult, TrendReport, run_full_trend_report


# ── Background worker ─────────────────────────────────────────────────────────

class _TrendWorker(QThread):
    result_ready = pyqtSignal(object)   # TrendReport
    error        = pyqtSignal(str)

    def __init__(self, store, window_hours: float, parent=None):
        super().__init__(parent)
        self._store = store
        self._window_hours = window_hours

    def run(self):
        try:
            report = run_full_trend_report(self._store, window_hours=self._window_hours)
            self.result_ready.emit(report)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def _kpi_tile(label: str, value: str, accent: str = ACCENT) -> QWidget:
    w = QFrame()
    w.setStyleSheet(
        f"QFrame{{background:{BG_CARD};border:1px solid {BORDER};"
        f"border-left:3px solid {accent};min-width:110px;}}"
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


_SEV_COLOR = {"CRITICAL": RED, "WARNING": AMBER, "INFO": ACCENT, "CLEAN": GREEN}
_SEV_BG    = {"CRITICAL": RED_BG, "WARNING": AMBER_BG, "INFO": BG_CARD, "CLEAN": BG_CARD}
_METRIC_LABEL = {"rtt_ms": "RTT (ms)", "loss_pct": "Loss (%)", "jitter_ms": "Jitter (ms)"}


class TrendPage(QWidget):
    """Predictive trend alerting page."""

    navigate_to = pyqtSignal(str)

    def __init__(self, store=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("contentArea")
        self._store = store
        self._worker: Optional[_TrendWorker] = None
        self._last_report: Optional[TrendReport] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        outer.addWidget(_page_header(
            "Predictive Trend Alerting",
            "Linear regression forecasts — projected time until monitored metrics breach thresholds",
        ))

        # KPI row
        self._kpi_hosts    = _kpi_tile("Hosts Analysed", "—")
        self._kpi_critical = _kpi_tile("Critical",        "—", RED)
        self._kpi_warnings = _kpi_tile("Warnings",        "—", AMBER)
        self._kpi_clean    = _kpi_tile("Clean",           "—", GREEN)
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        for w in (self._kpi_hosts, self._kpi_critical, self._kpi_warnings, self._kpi_clean):
            kpi_row.addWidget(w)
        kpi_row.addStretch()
        outer.addLayout(kpi_row)

        # RECUR-4: this-week vs last-week RTT headline
        self._headline_lbl = QLabel("")
        self._headline_lbl.setVisible(False)
        self._headline_lbl.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{TEXT_PRIMARY};"
            f" background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:4px; padding:8px 14px;"
        )
        outer.addWidget(self._headline_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        il = QVBoxLayout(inner)
        il.setContentsMargins(16, 8, 16, 16)
        il.setSpacing(12)
        il.addWidget(self._build_controls())
        il.addWidget(self._build_results_card())
        il.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)

    # ── Controls card ─────────────────────────────────────────────────────────

    def _build_controls(self) -> QWidget:
        row = QWidget()
        row.setStyleSheet(f"background:{BG_DARK};")
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)

        lbl = QLabel("Analysis window:")
        lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;")
        hl.addWidget(lbl)

        self._window_combo = QComboBox()
        for label, hours in [("6 hours", 6), ("12 hours", 12), ("24 hours", 24),
                              ("3 days", 72), ("7 days", 168)]:
            self._window_combo.addItem(label, hours)
        self._window_combo.setCurrentIndex(2)  # default 24 h
        self._window_combo.setFixedHeight(26)
        self._window_combo.setStyleSheet(
            f"QComboBox{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
            f"border-radius:2px;padding:0 6px;font-size:11px;}}"
            f"QComboBox::drop-down{{border:none;}}"
            f"QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};selection-background-color:{ACCENT};}}"
        )
        hl.addWidget(self._window_combo)

        self._btn_run = QPushButton("▶  Run Analysis")
        self._btn_run.setFixedHeight(26)
        self._btn_run.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};border:none;"
            f"border-radius:2px;padding:0 16px;font-size:11px;font-weight:bold;}}"
            f"QPushButton:hover{{background:{ACCENT_DARK};}}"
            f"QPushButton:disabled{{background:{BORDER};color:{TEXT_SECONDARY};}}"
        )
        self._btn_run.clicked.connect(self._run_analysis)
        hl.addWidget(self._btn_run)

        self._status_lbl = QLabel(
            "Enable Network RTT logging in Log Hub to build forecast data."
        )
        self._status_lbl.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        hl.addWidget(self._status_lbl)

        self._btn_log_hub = QPushButton("Open Log Hub →")
        self._btn_log_hub.setFlat(True)
        self._btn_log_hub.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_log_hub.setStyleSheet(
            f"QPushButton{{color:{ACCENT};font-size:10px;background:transparent;"
            f"border:none;padding:0 0 0 4px;}}"
            f"QPushButton:hover{{color:{ACCENT_DARK};}}"
        )
        self._btn_log_hub.clicked.connect(lambda: self.navigate_to.emit("Network Logger"))
        hl.addWidget(self._btn_log_hub)
        hl.addStretch()
        return row

    # ── Results card ──────────────────────────────────────────────────────────

    def _build_results_card(self) -> QWidget:
        card, bl = _card("Trend Forecast — All Hosts")

        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels(
            ["Host", "Metric", "Current", "Trend/h", "Threshold", "ETA", "Verdict"]
        )
        _hdr_tips = {
            1: "Metric being tracked: RTT (round-trip time), Loss (packet loss %), or Jitter (variation in RTT).",
            2: ("Current measured value.\n"
                "RTT: Good < 20 ms · Acceptable 20–100 ms · Poor > 100 ms\n"
                "Loss: Good 0% · Acceptable < 1% · Poor ≥ 1%\n"
                "Jitter: Good < 5 ms · Acceptable 5–20 ms · Poor > 20 ms"),
            3: "Rate of change per hour (linear regression slope). Positive = getting worse.",
            4: "The configured alert threshold. When the projected value exceeds this, a verdict is raised.",
            5: "Estimated time until the metric breaches its threshold at the current trend rate.",
            6: "CRITICAL = breach imminent.  WARNING = trending up.  CLEAN = stable or improving.",
        }
        for col, tip in _hdr_tips.items():
            item = self._table.horizontalHeaderItem(col)
            if item:
                item.setToolTip(tip)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(
            0, __import__("PyQt6.QtWidgets", fromlist=["QHeaderView"]).QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setMinimumHeight(300)
        self._table.setStyleSheet(
            f"QTableWidget{{border:none;font-size:11px;color:{TEXT_PRIMARY};"
            f"gridline-color:{BORDER};alternate-background-color:{BG_ALT_ROW};}}"
            f"QHeaderView::section{{background:{ACCENT};color:{WHITE};"
            f"font-size:10px;font-weight:bold;padding:3px 5px;border:none;}}"
            f"QTableWidget::item{{padding:2px 5px;}}"
        )
        for w, col in zip((130, 80, 70, 70, 80, 80), range(6)):
            self._table.setColumnWidth(col, w)
        bl.addWidget(self._table)

        note = QLabel(
            "R² < 0.5 = noisy data / no clear trend.  "
            "ETA shown only when the trend is rising toward the threshold within 30 days."
        )
        note.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:10px;")
        bl.addWidget(note)
        return card

    # ── Analysis runner ───────────────────────────────────────────────────────

    @pyqtSlot()
    def _run_analysis(self):
        if self._worker and self._worker.isRunning():
            return
        if self._store is None:
            self._status_lbl.setText("No data store connected.")
            return
        self._btn_run.setEnabled(False)
        self._btn_run.setText("⏳ Analysing…")
        hours = self._window_combo.currentData()
        self._worker = _TrendWorker(self._store, window_hours=hours, parent=None)
        self._worker.result_ready.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(object)
    def _on_result(self, report: TrendReport):
        self._last_report = report
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶  Run Analysis")
        self._populate_table(report)
        self._update_kpis(report)
        self._update_rtt_headline()
        self._btn_log_hub.setVisible(False)
        hosts = len({r.host for r in report.results})
        ts_str = time.strftime("%H:%M:%S", time.localtime(report.ts))
        self._status_lbl.setText(
            f"Last run: {ts_str} — {hosts} host(s), {len(report.results)} metric(s) analysed"
        )

    def showEvent(self, event):
        super().showEvent(event)
        self._update_rtt_headline()

    def _update_rtt_headline(self) -> None:
        """RECUR-4: compute this-week vs last-week RTT average and update headline label."""
        if self._store is None:
            return
        try:
            hosts = self._store.query_all_rtt_hosts(hours=336)  # 14 days
        except Exception:
            return
        if not hosts:
            self._headline_lbl.setVisible(False)
            return

        now = time.time()
        week_boundary = now - 7 * 86400  # 7 days ago

        this_week_vals: list[float] = []
        last_week_vals: list[float] = []
        for host in hosts:
            try:
                pts = self._store.query_rtt_history(host, hours=336)
            except Exception:
                continue
            for pt in pts:
                rtt = getattr(pt, "rtt_ms", None)
                if rtt is None or rtt <= 0:
                    continue
                if pt.ts >= week_boundary:
                    this_week_vals.append(rtt)
                else:
                    last_week_vals.append(rtt)

        if not this_week_vals:
            self._headline_lbl.setVisible(False)
            return

        this_avg = sum(this_week_vals) / len(this_week_vals)

        if last_week_vals:
            last_avg = sum(last_week_vals) / len(last_week_vals)
            delta = this_avg - last_avg
            if delta > 5:
                arrow, color = "↑", AMBER if delta < 20 else RED
            elif delta < -5:
                arrow, color = "↓", GREEN
            else:
                arrow, color = "→", GREEN
            diff_str = f" ({arrow} {abs(delta):.0f}ms vs. last week)"
        else:
            color = GREEN if this_avg < 50 else AMBER if this_avg < 150 else RED
            diff_str = " (no prior week data)"

        self._headline_lbl.setText(
            f"RTT this week: {this_avg:.0f}ms avg{diff_str}"
        )
        self._headline_lbl.setStyleSheet(
            f"font-size:13px; font-weight:bold; color:{color};"
            f" background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:4px; padding:8px 14px;"
        )
        self._headline_lbl.setVisible(True)

    @pyqtSlot(str)
    def _on_error(self, err: str):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("▶  Run Analysis")
        self._status_lbl.setText(f"Analysis error: {err}")

    # ── Table population ──────────────────────────────────────────────────────

    def _populate_table(self, report: TrendReport):
        from PyQt6.QtGui import QColor
        self._table.setRowCount(0)
        for r in report.results:
            row = self._table.rowCount()
            self._table.insertRow(row)
            sev_color = _SEV_COLOR.get(r.severity, TEXT_PRIMARY)

            unit = {"rtt_ms": "ms", "loss_pct": "%", "jitter_ms": "ms"}.get(r.metric, "")
            trend_str = f"+{r.slope_per_hour:.3f}" if r.slope_per_hour >= 0 else f"{r.slope_per_hour:.3f}"

            if r.eta_hours is None:
                eta_str = "—"
            elif r.eta_hours < 1:
                eta_str = f"<1 h"
            elif r.eta_hours < 48:
                eta_str = f"{r.eta_hours:.1f} h"
            else:
                eta_str = f"{r.eta_hours/24:.1f} d"

            for col, val in enumerate([
                r.host,
                _METRIC_LABEL.get(r.metric, r.metric),
                f"{r.current_value:.1f}{unit}",
                f"{trend_str}{unit}/h",
                f"{r.threshold:.0f}{unit}",
                eta_str,
                r.severity,
            ]):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 6:
                    item.setForeground(QColor(sev_color))
                    item.setFont(__import__("PyQt6.QtGui", fromlist=["QFont"]).QFont(
                        "Segoe UI", 9, __import__("PyQt6.QtGui", fromlist=["QFont"]).QFont.Weight.Bold
                    ))
                self._table.setItem(row, col, item)

            # Colour ETA cell by severity
            if r.eta_hours is not None and r.severity in ("CRITICAL", "WARNING"):
                eta_item = self._table.item(row, 5)
                if eta_item:
                    eta_item.setForeground(QColor(sev_color))

    def _update_kpis(self, report: TrendReport):
        hosts = len({r.host for r in report.results})
        crit  = len(report.critical)
        warn  = len(report.warnings)
        clean = len([r for r in report.results if r.severity == "CLEAN"])
        for tile, val, col in [
            (self._kpi_hosts,    str(hosts), ACCENT),
            (self._kpi_critical, str(crit),  RED if crit else TEXT_SECONDARY),
            (self._kpi_warnings, str(warn),  AMBER if warn else TEXT_SECONDARY),
            (self._kpi_clean,    str(clean), GREEN),
        ]:
            lbl = tile.findChild(QLabel, "kpi_val")
            if lbl:
                lbl.setText(val)
                lbl.setStyleSheet(f"color:{col};font-size:22px;font-weight:bold;")
