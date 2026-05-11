"""
LogHubPage — unified monitor for all NetSentinel log sources.

One chronological table with a source toggle bar. Toggling a source
controls both visibility and (for Modem/Mesh) whether data is logged to DB.

Sources:
  Network RTT  — continuous ping logger entries (CSV + live)
  5G Modem     — periodic signal snapshots (DB + live, user-configurable interval)
  Mesh         — periodic status snapshots (DB + live, user-configurable interval)
  Syslog       — received syslog messages (live only)
  SNMP         — received SNMP traps (live only)

QSettings keys (prefix "logging/"):
  net_enabled         bool   default True
  modem_enabled       bool   default False
  modem_interval_min  int    default 5
  mesh_enabled        bool   default False
  mesh_interval_min   int    default 5
  syslog_enabled      bool   default True
  snmp_enabled        bool   default True
"""
from __future__ import annotations

import datetime as _dt
import time as _t
from typing import Optional

from PyQt6.QtCore import Qt, QSettings, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BG_HOVER, BG_ALT_ROW,
    BORDER, CARD_RADIUS, GREEN, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
)

_MAX_ROWS = 500
_LIVE_CHALLENGE_COOLDOWN = 60.0

# Source key → (display label, accent colour)
_SOURCES: dict[str, tuple[str, str]] = {
    "net":    ("RTT",    ACCENT),
    "modem":  ("MODEM",  GREEN),
    "mesh":   ("MESH",   AMBER),
    "syslog": ("SYSLOG", TEXT_SECONDARY),
    "snmp":   ("SNMP",   RED),
}
_LABEL_TO_KEY = {label: key for key, (label, _) in _SOURCES.items()}

_SYSLOG_SEVERITY_COLOR = {
    "EMERG": RED, "ALERT": RED, "CRIT": RED,
    "ERR": AMBER, "WARNING": AMBER,
    "NOTICE": TEXT_PRIMARY, "INFO": TEXT_PRIMARY, "DEBUG": TEXT_MUTED,
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _source_key(label: str) -> str:
    return _LABEL_TO_KEY.get(label, label.lower())


def _fmt_ts(ts: float) -> str:
    dt = _dt.datetime.fromtimestamp(ts)
    if _t.time() - ts < 86400:
        return dt.strftime("%H:%M:%S")
    return dt.strftime("%m-%d %H:%M")


def _status_color(status: str) -> str:
    return {"OK": GREEN, "SLOW": AMBER, "FAIL": RED}.get(status.upper(), TEXT_SECONDARY)


def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setStretchLastSection(False)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.setShowGrid(False)
    t.setStyleSheet(
        f"QTableWidget {{ background:{BG_CARD}; border:none; font-size:11px; color:{TEXT_PRIMARY}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT}; font-size:11px;"
        f" font-weight:bold; padding:4px 8px; border:none; }}"
        f"QTableWidget::item:selected {{ background:#CCE4F7; color:{TEXT_PRIMARY}; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QTableWidget::item:alternate {{ background:{BG_ALT_ROW}; }}"
    )
    return t


# ── Live challenge builder (preserved) ───────────────────────────────────────

def _build_live_scenario(entry, consecutive_fails: int = 0):
    """Return a one-step LabScenario for an interesting log entry, or None."""
    from modules.lab_scenarios import LabScenario, LabStep
    if entry.arp_event and entry.arp_event.startswith("NEW"):
        return LabScenario(
            id="live_new_device",
            title="New Device Detected",
            goal="A new device just appeared on your network. Investigate whether it belongs here.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"A new device appeared: {entry.arp_event}. "
                    "Run a scan to see all devices on your network and confirm it belongs."
                ),
                scan_type="rogue",
                hint="Look at the Risk column. An unexpected vendor or blank hostname may indicate a rogue device.",
                solution=(
                    "If the device has Risk = HIGH or an unexpected vendor, record its MAC address. "
                    "If it's one of your devices, whitelist it from the Overview page."
                ),
            )],
        )
    if entry.dns_ms >= 0 and entry.dns_ms > 200:
        return LabScenario(
            id="live_slow_dns",
            title="Slow DNS Detected",
            goal=f"DNS latency spiked to {entry.dns_ms:.0f} ms. Diagnose your resolver.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"Your DNS resolver just returned {entry.dns_ms:.0f} ms — above the 200 ms threshold. "
                    "Run the DNS check to measure it formally over 60 seconds."
                ),
                scan_type="dns",
                hint="A single high reading may be transient. The 60-second scan shows whether outages correlate with DNS failures.",
                solution=(
                    "If average DNS is consistently high, switch to 1.1.1.1 (Cloudflare) or "
                    "8.8.8.8 (Google) in your router's DNS settings."
                ),
            )],
        )
    if consecutive_fails >= 3:
        return LabScenario(
            id="live_connectivity_fail",
            title="Connectivity Issues Detected",
            goal="Multiple consecutive failures were logged. Diagnose your connection.",
            effort="S",
            steps=[LabStep(
                instruction=(
                    f"Your logger recorded 3+ consecutive FAIL results to {entry.host}. "
                    "Run the DNS and stability check to determine whether this is a routing or DNS issue."
                ),
                scan_type="dns",
                hint="If pings fail but DNS works, the fault is upstream routing. If both fail together, try your DNS server settings.",
                solution=(
                    "Check your router first. If ping to 8.8.8.8 also fails, contact your ISP. "
                    "If only DNS fails, change the DNS server in your router settings to 1.1.1.1."
                ),
            )],
        )
    return None


# ── LogHubPage ────────────────────────────────────────────────────────────────

class LogHubPage(QWidget):
    """
    Unified monitor — all log sources in one chronological table.

    Source toggle bar controls logging and visibility per source.
    Modem and Mesh have user-configurable log intervals (1–60 min).

    Preserved public API:
        add_log_entry(entry)   — network RTT live entry from LoggerWorker
        add_modem_entry(data)  — modem signal dict from dashboard
        add_mesh_entry(data)   — mesh status dict from dashboard
        on_syslog_message(msg) — syslog message object
        on_snmp_trap(trap)     — SNMP trap object
        show_network_log()     — ensure RTT visible + scroll to top
    """

    animate_requested       = pyqtSignal(object)
    live_challenge_detected = pyqtSignal(object)

    _HEADERS = ["Time", "Source", "Host", "Event", "Detail", "Status"]

    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._store = store
        self._entries:            list[dict] = []
        self._consecutive_fails:  int        = 0
        self._last_live_challenge: float     = 0.0
        self._toggle_btns:   dict[str, QPushButton] = {}
        self._interval_boxes: dict[str, QSpinBox]   = {}
        self._src_bold_font = QFont()
        self._src_bold_font.setBold(True)
        self._src_bold_font.setPointSize(8)

        self._setup_ui()
        QTimer.singleShot(300, self._load_history)

    # ── UI construction ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hdr = QLabel("Monitor")
        hdr.setFixedHeight(36)
        hdr.setStyleSheet(
            f"QLabel {{ background:{BG_DARK}; font-size:15px; font-weight:bold;"
            f" color:{TEXT_PRIMARY}; padding:0 16px; border-bottom:1px solid {BORDER}; }}"
        )
        root.addWidget(hdr)

        inner = QWidget()
        inner.setStyleSheet(f"background:{BG_DARK};")
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(16, 10, 16, 12)
        inner_lay.setSpacing(8)

        inner_lay.addWidget(self._build_source_bar())

        card = QFrame()
        card.setObjectName("logcard")
        card.setStyleSheet(
            f"QFrame#logcard {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)

        self._table = _make_table(self._HEADERS)
        self._table.setColumnWidth(0, 130)
        self._table.setColumnWidth(1, 68)
        self._table.setColumnWidth(2, 150)
        self._table.setColumnWidth(3, 145)
        self._table.setColumnWidth(5, 72)
        self._table.horizontalHeader().setSectionResizeMode(
            4, self._table.horizontalHeader().ResizeMode.Stretch
        )
        card_lay.addWidget(self._table)
        inner_lay.addWidget(card, 1)

        scroll = QScrollArea()
        scroll.setWidget(inner)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG_DARK}; border:none; }}")
        root.addWidget(scroll, 1)

    def _build_source_bar(self) -> QWidget:
        bar = QFrame()
        bar.setStyleSheet(
            f"QFrame {{ background:{BG_CARD}; border:1px solid {BORDER};"
            f" border-radius:{CARD_RADIUS}; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 7, 12, 7)
        lay.setSpacing(6)

        lbl = QLabel("Sources:")
        lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
        )
        lay.addWidget(lbl)

        s = QSettings()
        for key, (label, color) in _SOURCES.items():
            default_on = key in ("net", "syslog", "snmp")
            enabled = s.value(f"logging/{key}_enabled", default_on, type=bool)

            btn = QPushButton(f"{'●' if enabled else '○'}  {label}")
            btn.setCheckable(True)
            btn.setChecked(enabled)
            btn.setFixedHeight(26)
            self._style_toggle(btn, enabled, color)
            btn.clicked.connect(lambda checked, k=key: self._on_source_toggled(k, checked))
            self._toggle_btns[key] = btn
            lay.addWidget(btn)

            if key in ("modem", "mesh"):
                spin = QSpinBox()
                spin.setRange(1, 60)
                spin.setSuffix(" min")
                spin.setFixedWidth(78)
                spin.setFixedHeight(26)
                spin.setValue(s.value(f"logging/{key}_interval_min", 5, type=int))
                spin.setEnabled(enabled)
                spin.setToolTip(f"How often to save {label} data to the database")
                spin.setStyleSheet(
                    f"QSpinBox {{ background:{BG_CARD}; border:1px solid {BORDER};"
                    f" border-radius:4px; padding:1px 4px; font-size:11px; color:{TEXT_PRIMARY}; }}"
                    f"QSpinBox:disabled {{ color:{TEXT_MUTED}; }}"
                )
                spin.valueChanged.connect(
                    lambda val, k=key: QSettings().setValue(f"logging/{k}_interval_min", val)
                )
                self._interval_boxes[key] = spin
                lay.addWidget(spin)

        lay.addStretch()

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search…")
        self._search_box.setFixedWidth(200)
        self._search_box.setFixedHeight(26)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setStyleSheet(
            f"QLineEdit {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:4px;"
            f" padding:1px 8px; font-size:11px; color:{TEXT_PRIMARY}; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}"
        )
        self._search_box.textChanged.connect(self._apply_filter)
        lay.addWidget(self._search_box)

        return bar

    def _style_toggle(self, btn: QPushButton, enabled: bool, color: str) -> None:
        if enabled:
            btn.setStyleSheet(
                f"QPushButton {{ background:{color}22; color:{color}; font-size:11px;"
                f" font-weight:bold; border:1px solid {color}; border-radius:12px;"
                f" padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{color}44; }}"
            )
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background:{BG_CARD}; color:{TEXT_MUTED}; font-size:11px;"
                f" border:1px solid {BORDER}; border-radius:12px; padding:1px 10px; }}"
                f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            )

    def _on_source_toggled(self, key: str, checked: bool) -> None:
        label, color = _SOURCES[key]
        btn = self._toggle_btns[key]
        btn.setText(f"{'●' if checked else '○'}  {label}")
        self._style_toggle(btn, checked, color)
        if key in self._interval_boxes:
            self._interval_boxes[key].setEnabled(checked)
        QSettings().setValue(f"logging/{key}_enabled", checked)
        self._apply_filter()

    def _is_source_enabled(self, key: str) -> bool:
        btn = self._toggle_btns.get(key)
        return btn.isChecked() if btn else False

    # ── Entry management ──────────────────────────────────────────────────────

    def _make_entry(
        self,
        src_key: str,
        ts: float,
        host: str,
        event: str,
        detail: str,
        status: str,
        raw=None,
    ) -> dict:
        label = _SOURCES[src_key][0]
        return {
            "source_key": src_key,
            "source":     label,
            "ts":         ts,
            "row":        (_fmt_ts(ts), label, host, event, detail, status),
            "raw":        raw,
        }

    def _add_live(self, e: dict) -> None:
        """Insert a live entry and update the table immediately if visible."""
        self._entries.insert(0, e)
        if len(self._entries) > _MAX_ROWS:
            self._entries = self._entries[:_MAX_ROWS]
        if not self._is_source_enabled(e["source_key"]):
            return
        filt = self._search_box.text().strip().lower()
        if filt and not self._row_matches(e["row"], filt):
            return
        self._table.insertRow(0)
        self._set_table_row(0, e)
        if self._table.rowCount() > _MAX_ROWS:
            self._table.setRowCount(_MAX_ROWS)

    def _apply_filter(self) -> None:
        filt = self._search_box.text().strip().lower()
        visible = [
            e for e in self._entries
            if self._is_source_enabled(e["source_key"])
            and (not filt or self._row_matches(e["row"], filt))
        ]
        self._table.setRowCount(0)
        for i, e in enumerate(visible[:_MAX_ROWS]):
            self._table.insertRow(i)
            self._set_table_row(i, e)

    def _row_matches(self, row: tuple, filt: str) -> bool:
        return any(filt in str(row[i]).lower() for i in (2, 3, 4))

    def _set_table_row(self, idx: int, e: dict) -> None:
        row = e["row"]
        _, src_color = _SOURCES.get(e["source_key"], ("", TEXT_PRIMARY))
        sc = _status_color(row[5]) if row[5] else TEXT_SECONDARY

        for col, val in enumerate(row):
            # ARP animate button in Event column for RTT entries
            if (col == 3 and e["raw"] is not None
                    and hasattr(e["raw"], "arp_event") and e["raw"].arp_event):
                btn = QPushButton(f"▶ ARP  {str(val)[:30]}")
                btn.setStyleSheet(
                    f"QPushButton {{ background:transparent; border:none; color:{AMBER};"
                    f" font-size:10px; text-align:left; padding:0 4px; }}"
                    f"QPushButton:hover {{ color:{ACCENT}; text-decoration:underline; }}"
                )
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                _raw = e["raw"]
                btn.clicked.connect(lambda _=False, r=_raw: self.animate_requested.emit(r))
                self._table.setCellWidget(idx, col, btn)
            else:
                item = QTableWidgetItem(str(val))
                if col == 1:
                    item.setForeground(QColor(src_color))
                    item.setFont(self._src_bold_font)
                elif col == 5:
                    item.setForeground(QColor(sc))
                else:
                    item.setForeground(QColor(TEXT_PRIMARY))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                self._table.setItem(idx, col, item)

    def _sort_and_render(self) -> None:
        self._entries.sort(key=lambda e: e["ts"], reverse=True)
        self._entries = self._entries[:_MAX_ROWS]
        self._apply_filter()

    # ── History loader ────────────────────────────────────────────────────────

    def _load_history(self) -> None:
        # Network RTT from CSV
        try:
            from modules.network_logger import list_log_files, load_log_file
            files = list_log_files()
            if files:
                summary = load_log_file(files[0])
                for entry in list(reversed(summary.entries[-200:])):
                    try:
                        ts = _dt.datetime.fromisoformat(entry.timestamp).timestamp()
                    except Exception:
                        ts = _t.time()
                    rtt_str  = f"{entry.rtt_ms:.0f}ms" if entry.rtt_ms >= 0 else "—"
                    dns_str  = f"DNS {entry.dns_ms:.0f}ms" if entry.dns_ms >= 0 else ""
                    http_str = f"HTTP {entry.http_status}" if entry.http_status >= 0 else ""
                    detail   = "  ·  ".join(filter(None, [rtt_str, dns_str, http_str]))
                    self._entries.append(self._make_entry(
                        "net", ts, entry.host,
                        entry.arp_event or entry.status, detail, entry.status, raw=entry,
                    ))
        except Exception:
            pass

        if self._store:
            # Modem signal history
            if self._is_source_enabled("modem"):
                try:
                    for p in self._store.query_modem_signal_log(hours=168, limit=200):
                        self._entries.append(self._modem_point_to_entry(p))
                except Exception:
                    pass

            # Mesh history
            if self._is_source_enabled("mesh"):
                try:
                    for p in self._store.query_mesh_signal_log(hours=168, limit=200):
                        unit_str = f"{p.online_count}/{p.unit_count} units"
                        parts = [f"{p.online_count}/{p.unit_count} units online"]
                        if p.worst_unit and p.worst_rssi is not None:
                            parts.append(f"worst: {p.worst_unit} {p.worst_rssi:.0f} dBm")
                        self._entries.append(self._make_entry(
                            "mesh", float(p.ts), "Mesh system",
                            unit_str, "  ·  ".join(parts), "OK",
                        ))
                except Exception:
                    pass

        self._sort_and_render()

    def _modem_point_to_entry(self, p) -> dict:
        ts      = float(getattr(p, "ts", _t.time()))
        nt      = getattr(p, "network_type", None) or ""
        band    = getattr(p, "nr5g_band", None) or getattr(p, "lte_band", None) or ""
        nr_rsrp = getattr(p, "nr5g_rsrp", None)
        lte_rsrp = getattr(p, "lte_rsrp", None)
        rsrp    = nr_rsrp if nr_rsrp is not None else lte_rsrp
        rsrp_str = f"{rsrp:.1f} dBm" if rsrp is not None else ""
        bars    = getattr(p, "signal_bars", None)
        bars_str = f"{bars}/5" if bars is not None else ""
        mcc, mnc = getattr(p, "mcc", None), getattr(p, "mnc", None)
        host    = f"{mcc}-{mnc}" if mcc and mnc else "ZTE MC889"
        detail  = "  ·  ".join(filter(None, [nt, band, rsrp_str, bars_str]))
        return self._make_entry("modem", ts, host, "Signal", detail, nt or "")

    # ── Public API ────────────────────────────────────────────────────────────

    def add_log_entry(self, entry) -> None:
        """Network RTT live entry from LoggerWorker."""
        if entry.status == "FAIL":
            self._consecutive_fails += 1
        else:
            self._consecutive_fails = 0

        now = _t.time()
        if now - self._last_live_challenge > _LIVE_CHALLENGE_COOLDOWN:
            scenario = _build_live_scenario(entry, self._consecutive_fails)
            if scenario is not None:
                self._last_live_challenge = now
                self.live_challenge_detected.emit(scenario)

        rtt_str  = f"{entry.rtt_ms:.0f}ms" if entry.rtt_ms >= 0 else "—"
        dns_str  = f"DNS {entry.dns_ms:.0f}ms" if entry.dns_ms >= 0 else ""
        http_str = f"HTTP {entry.http_status}" if entry.http_status >= 0 else ""
        detail   = "  ·  ".join(filter(None, [rtt_str, dns_str, http_str]))
        self._add_live(self._make_entry(
            "net", now, entry.host,
            entry.arp_event or entry.status, detail, entry.status, raw=entry,
        ))

    def add_modem_entry(self, data: dict) -> None:
        """Modem signal live entry — called from dashboard."""
        ts   = float(data.get("ts") or _t.time())
        mcc, mnc = data.get("mcc"), data.get("mnc")
        host = f"{mcc}-{mnc}" if mcc and mnc else "ZTE MC889"
        nt   = data.get("network_type") or ""
        band = data.get("nr5g_band") or data.get("lte_band") or ""
        rsrp_raw = (data.get("nr5g_rsrp_dbm")
                    if data.get("nr5g_rsrp_dbm") is not None
                    else data.get("lte_rsrp_dbm"))
        rsrp_str = f"{rsrp_raw:.1f} dBm" if rsrp_raw is not None else ""
        bars = data.get("signal_bars")
        bars_str = f"{bars}/5" if bars is not None else ""
        detail = "  ·  ".join(filter(None, [nt, band, rsrp_str, bars_str]))
        self._add_live(self._make_entry("modem", ts, host, "Signal", detail, nt or ""))

    def add_mesh_entry(self, data: dict) -> None:
        """Mesh status live entry — called from dashboard."""
        units        = data.get("units", [])
        unit_count   = len(units)
        online_count = sum(1 for u in units if getattr(u, "online", True))
        worst_name, worst_rssi = "", None
        for u in units:
            rssi = getattr(u, "rssi", None) or getattr(u, "signal_level", None)
            if rssi is not None and (worst_rssi is None or rssi < worst_rssi):
                worst_rssi = rssi
                worst_name = getattr(u, "name", "") or getattr(u, "device_id", "")
        unit_str = f"{online_count}/{unit_count} units"
        parts    = [f"{online_count}/{unit_count} units online"]
        if worst_name and worst_rssi is not None:
            parts.append(f"worst: {worst_name} {worst_rssi:.0f} dBm")
        self._add_live(self._make_entry(
            "mesh", _t.time(), "Mesh system", unit_str, "  ·  ".join(parts), "OK",
        ))

    @pyqtSlot(object)
    def on_syslog_message(self, msg) -> None:
        severity = getattr(msg, "severity", "INFO")
        host     = getattr(msg, "source_ip", "") or getattr(msg, "hostname", "—")
        detail   = str(getattr(msg, "message", str(msg)))[:140]
        self._add_live(self._make_entry("syslog", _t.time(), host, severity, detail, ""))

    @pyqtSlot(object)
    def on_snmp_trap(self, trap) -> None:
        host   = getattr(trap, "source_ip", "—")
        event  = getattr(trap, "trap_type", "")
        detail = getattr(trap, "oid", "")
        self._add_live(self._make_entry("snmp", _t.time(), host, event, detail, ""))

    def show_network_log(self) -> None:
        """Ensure Network RTT source is visible and scroll to top."""
        btn = self._toggle_btns.get("net")
        if btn and not btn.isChecked():
            btn.setChecked(True)
            self._on_source_toggled("net", True)
        self._table.scrollToTop()
