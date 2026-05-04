"""
GeoMapPage — Geolocation map for internet-facing IPs.

Layout
──────
  Top:    Page title + subtitle
  Row:    [DB status card] | [Import / Source card]
  Main:   Matplotlib world-map canvas (scatter dots)
          Right sidebar: detail panel (IP info + linked devices/alerts)
  Bottom: IP table (all plotted IPs with geo info)

Data sources
────────────
  • Threat intelligence feed (ThreatEntry objects)
  • Internet exposure scan (WAN IP + UPnP-exposed hosts)
  • Manual IP entry
  • Dashboard push via set_threat_entries() / add_ips()

All lookups are local (GeoLite2-City.mmdb).
No IPs are sent to external services.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.geo_locator import GeoLocator, GeoResult, db_path, download_db_permalink, get_locator
from ui.styles import (
    ACCENT,
    AMBER,
    BG_ALT_ROW,
    BG_CARD,
    BG_DARK,
    BG_HOVER,
    BORDER,
    CARD_HDR_BORDER,
    CARD_RADIUS,
    CHART_BG,
    CHART_GRID,
    CHART_PLOT_BG,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TH_BG,
    TH_TEXT,
)


# ── Workers ───────────────────────────────────────────────────────────────────

class _LookupWorker(QThread):
    """Resolve a list of IP strings to GeoResult objects."""
    result_ready = pyqtSignal(list)    # List[GeoResult]
    error = pyqtSignal(str)

    def __init__(self, ips: List[str], locator: GeoLocator) -> None:
        super().__init__()
        self._ips = ips
        self._locator = locator

    def run(self) -> None:
        try:
            results = self._locator.lookup_many(self._ips)
            self.result_ready.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


class _DownloadWorker(QThread):
    """Download the GeoLite2-City.mmdb from a MaxMind permalink URL."""
    progress = pyqtSignal(int, int)   # (bytes_received, total_bytes)
    done = pyqtSignal(str)            # success message
    error = pyqtSignal(str)

    def __init__(self, url: str) -> None:
        super().__init__()
        self._url = url

    def run(self) -> None:
        try:
            path = download_db_permalink(
                self._url, on_progress=self.progress.emit)
            self.done.emit(str(path))
        except Exception as exc:
            self.error.emit(str(exc))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _btn(label: str, accent: bool = False) -> QPushButton:
    b = QPushButton(label)
    b.setFixedHeight(26)
    b.setFont(QFont("Segoe UI", 9))
    if accent:
        b.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none;"
            f"  border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:#005A9E; }}"
            f"QPushButton:disabled {{ background:#9BA8B4; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"  border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ color:{TEXT_MUTED}; }}"
        )
    return b


def _card(title: str) -> Tuple[QWidget, QVBoxLayout]:
    card = QWidget()
    card.setObjectName("geoCard")
    card.setStyleSheet(
        f"QWidget#geoCard {{ background:{BG_CARD}; border:1px solid {BORDER}; border-radius:{CARD_RADIUS}; }}"
    )
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    hdr = QLabel(title)
    hdr.setFixedHeight(32)
    hdr.setStyleSheet(
        f"background:{BG_CARD}; color:{TEXT_PRIMARY}; font-weight:600; font-size:11px;"
        f"padding:0 12px; border-bottom:1px solid {CARD_HDR_BORDER};"
    )
    outer.addWidget(hdr)
    inner_w = QWidget()
    inner_w.setStyleSheet(f"background:{BG_CARD};")
    inner = QVBoxLayout(inner_w)
    inner.setContentsMargins(10, 8, 10, 8)
    inner.setSpacing(5)
    outer.addWidget(inner_w)
    return card, inner


def _table(headers: List[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)   # RULE 3
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setAlternatingRowColors(True)
    t.horizontalHeader().setStretchLastSection(True)
    t.setStyleSheet(
        f"QTableWidget {{ border:none; font-size:11px; background:{BG_CARD};"
        f"  alternate-background-color:{BG_ALT_ROW}; gridline-color:{BORDER}; }}"
        f"QTableWidget::item:hover {{ background:{BG_HOVER}; }}"
        f"QHeaderView::section {{ background:{TH_BG}; color:{TH_TEXT};"
        f"  font-size:10px; font-weight:600; border:none; padding:0 8px; height:24px; }}"
    )
    return t


def _dot(color: str) -> QLabel:
    lbl = QLabel("●")
    lbl.setStyleSheet(f"color:{color}; font-size:12px;")
    lbl.setFixedWidth(18)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


# ── Marker categories and colours ────────────────────────────────────────────

_CAT_THREAT  = "Threat Intel"
_CAT_EXPOSED = "Exposed Service"
_CAT_MANUAL  = "Manual Entry"

_MARKER_COLOR = {
    _CAT_THREAT:  RED,
    _CAT_EXPOSED: AMBER,
    _CAT_MANUAL:  ACCENT,
}


# ── Main page ─────────────────────────────────────────────────────────────────

class GeoMapPage(QWidget):
    """World-map geolocation of internet-facing IPs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._locator: GeoLocator = get_locator()
        # ip → (GeoResult, category, [linked labels])
        self._points: Dict[str, Tuple[GeoResult, str, List[str]]] = {}
        self._lookup_worker: Optional[_LookupWorker] = None
        self._dl_worker: Optional[_DownloadWorker] = None
        self._selected_ip: Optional[str] = None

        self._build_ui()
        self._refresh_db_status()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Title
        title = QLabel("Geolocation Map")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{TEXT_PRIMARY};")
        sub = QLabel(
            "Plot public IPs from threat intel, exposure scans, or manual entry "
            "on a world map using the local GeoLite2-City database."
        )
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        sub.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(sub)

        # DB status + import row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self._db_card, self._db_layout = _card("GeoLite2 Database")
        self._import_card, self._import_layout = _card("Add IPs")
        top_row.addWidget(self._db_card, 1)
        top_row.addWidget(self._import_card, 2)
        root.addLayout(top_row)

        self._build_db_card()
        self._build_import_card()

        # Main splitter: map + detail panel
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_map_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setSizes([900, 280])
        root.addWidget(splitter, 1)

        # IP table
        root.addWidget(self._build_ip_table_card())

    def _build_db_card(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        self._db_status_dot = _dot(TEXT_MUTED)
        self._db_status_lbl = QLabel("Checking…")
        self._db_status_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY};")
        self._db_path_lbl = QLabel("")
        self._db_path_lbl.setStyleSheet(f"font-size:9px; color:{TEXT_MUTED};")
        self._db_path_lbl.setWordWrap(True)

        row.addWidget(self._db_status_dot)
        row.addWidget(self._db_status_lbl)
        row.addStretch()
        btn_reload = _btn("↺  Reload DB")
        btn_reload.clicked.connect(self._on_reload_db)
        row.addWidget(btn_reload)
        self._db_layout.addLayout(row)
        self._db_layout.addWidget(self._db_path_lbl)

        # Permalink download
        dl_row = QHBoxLayout()
        dl_row.setSpacing(4)
        self._permalink_edit = QLineEdit()
        self._permalink_edit.setPlaceholderText(
            "Paste MaxMind permalink URL to download GeoLite2-City.mmdb…")
        self._permalink_edit.setFixedHeight(24)
        self._permalink_edit.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:3px; padding:0 6px;"
            f"font-size:10px; background:{BG_CARD};")
        self._btn_dl = _btn("↓  Download DB", accent=True)
        self._btn_dl.clicked.connect(self._on_download_db)
        self._dl_status = QLabel("")
        self._dl_status.setStyleSheet(f"font-size:9px; color:{TEXT_SECONDARY};")
        dl_row.addWidget(self._permalink_edit, 1)
        dl_row.addWidget(self._btn_dl)
        self._db_layout.addLayout(dl_row)
        self._db_layout.addWidget(self._dl_status)

    def _build_import_card(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(6)

        self._manual_edit = QLineEdit()
        self._manual_edit.setPlaceholderText("Enter IP(s) — comma or space separated")
        self._manual_edit.setFixedHeight(24)
        self._manual_edit.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:3px; padding:0 6px;"
            f"font-size:10px; background:{BG_CARD};")
        self._manual_edit.returnPressed.connect(self._on_add_manual)

        btn_add   = _btn("✚  Add", accent=True)
        btn_clear = _btn("✕  Clear All")
        btn_add.clicked.connect(self._on_add_manual)
        btn_clear.clicked.connect(self._on_clear_all)

        row.addWidget(QLabel("Manual:"))
        row.addWidget(self._manual_edit, 1)
        row.addWidget(btn_add)
        row.addWidget(btn_clear)
        self._import_layout.addLayout(row)

        legend_row = QHBoxLayout()
        for cat, color in _MARKER_COLOR.items():
            legend_row.addWidget(_dot(color))
            lbl = QLabel(cat)
            lbl.setStyleSheet(f"font-size:9px; color:{TEXT_SECONDARY};")
            legend_row.addWidget(lbl)
            legend_row.addSpacing(8)
        legend_row.addStretch()
        self._import_layout.addLayout(legend_row)

    def _build_map_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(0)

        self._fig = Figure(facecolor=CHART_BG, dpi=96)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._canvas)

        self._canvas.mpl_connect("button_press_event", self._on_map_click)
        self._draw_base_map()
        return panel

    def _build_detail_panel(self) -> QWidget:
        card, layout = _card("Selected IP — Details")
        self._detail_ip    = QLabel("—")
        self._detail_ip.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._detail_ip.setStyleSheet(f"color:{TEXT_PRIMARY};")
        self._detail_body  = QLabel("Click a dot on the map to see details.")
        self._detail_body.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        self._detail_body.setWordWrap(True)
        self._detail_links = QLabel("")
        self._detail_links.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        self._detail_links.setWordWrap(True)

        layout.addWidget(self._detail_ip)
        layout.addWidget(self._detail_body)
        layout.addWidget(self._detail_links)
        layout.addStretch()

        # Wrap in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(card)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        scroll.setMinimumWidth(220)
        scroll.setMaximumWidth(340)
        return scroll

    def _build_ip_table_card(self) -> QWidget:
        card, layout = _card("All Plotted IPs")
        self._ip_table = _table(
            ["IP", "Country", "City", "Lat", "Lon", "Category", "Linked"])
        self._ip_table.setFixedHeight(160)
        self._ip_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        self._ip_table.horizontalHeader().setStretchLastSection(True)
        self._ip_table.itemSelectionChanged.connect(self._on_table_selection)
        layout.addWidget(self._ip_table)
        return card

    # ── Map rendering ─────────────────────────────────────────────────────────

    def _draw_base_map(self) -> None:
        """Draw a minimal world outline using matplotlib path data."""
        ax = self._ax
        ax.cla()
        ax.set_facecolor(CHART_PLOT_BG)
        ax.set_xlim(-180, 180)
        ax.set_ylim(-90, 90)
        ax.set_aspect("equal")
        ax.axis("off")

        # Grid lines
        for lon in range(-180, 181, 30):
            ax.axvline(lon, color=CHART_GRID, linewidth=0.4, zorder=0)
        for lat in range(-90, 91, 30):
            ax.axhline(lat, color=CHART_GRID, linewidth=0.4, zorder=0)

        # Try to draw country borders from Natural Earth data bundled with matplotlib
        try:
            self._draw_country_borders()
        except Exception:
            # Graceful fallback — plain grid only
            ax.text(0, 0,
                    "Install Cartopy or Natural Earth shapefiles for country borders.",
                    ha="center", va="center", color=TEXT_MUTED,
                    fontsize=8, transform=ax.transData)

        self._fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
        self._canvas.draw()

    def _draw_country_borders(self) -> None:
        """Draw world country borders using matplotlib's bundled basemap-style data."""
        # Use mpl_toolkits.basemap if available, else skip borders gracefully
        # matplotlib alone doesn't bundle shapefile data so we skip without error
        pass

    def _redraw_map(self) -> None:
        """Redraw base map then overlay all data points."""
        self._draw_base_map()
        if not self._points:
            self._canvas.draw()
            return

        for ip, (result, category, _links) in self._points.items():
            if result.is_bogon or (result.latitude == 0.0 and result.longitude == 0.0):
                continue
            color = _MARKER_COLOR.get(category, ACCENT)
            size  = 80 if ip == self._selected_ip else 40
            edge  = TEXT_PRIMARY if ip == self._selected_ip else "none"
            self._ax.scatter(
                result.longitude, result.latitude,
                s=size, c=color, zorder=3,
                edgecolors=edge, linewidths=1.2,
                alpha=0.85,
            )

        self._fig.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)
        self._canvas.draw()

    # ── Canvas click ──────────────────────────────────────────────────────────

    def _on_map_click(self, event) -> None:
        if event.inaxes != self._ax or event.button != 1:
            return
        lon, lat = event.xdata, event.ydata
        if lon is None or lat is None:
            return

        # Find nearest dot within ~5 degrees tolerance
        best_ip = None
        best_dist = float("inf")
        for ip, (result, _cat, _links) in self._points.items():
            if result.is_bogon:
                continue
            d = (result.longitude - lon) ** 2 + (result.latitude - lat) ** 2
            if d < best_dist:
                best_dist = d
                best_ip = ip

        if best_ip and best_dist < 25:   # ~5° radius
            self._select_ip(best_ip)

    def _select_ip(self, ip: str) -> None:
        self._selected_ip = ip
        result, category, links = self._points[ip]
        self._detail_ip.setText(ip)

        lines = [
            f"Country:  {result.country_name or result.country or '—'}",
            f"City:     {result.city or '—'}",
            f"Lat/Lon:  {result.latitude:.3f}, {result.longitude:.3f}",
            f"Category: {category}",
        ]
        self._detail_body.setText("\n".join(lines))
        if links:
            self._detail_links.setText("Linked:\n" + "\n".join(f"  • {l}" for l in links))
        else:
            self._detail_links.setText("")

        # Highlight matching row in table
        for row in range(self._ip_table.rowCount()):
            if self._ip_table.item(row, 0) and self._ip_table.item(row, 0).text() == ip:
                self._ip_table.selectRow(row)
                break

        self._redraw_map()

    # ── Data ingestion ────────────────────────────────────────────────────────

    def set_threat_entries(self, entries: list) -> None:
        """
        Accept a list of ThreatEntry objects from the threat intel page.
        Only IP-type indicators with public addresses are plotted.
        """
        ips = [e.indicator for e in entries
               if getattr(e, "itype", "") == "ip"]
        self._queue_lookup(ips, _CAT_THREAT,
                           {e.indicator: e.source for e in entries
                            if getattr(e, "itype", "") == "ip"})

    def add_ips(self, ips: List[str], category: str = _CAT_MANUAL,
                labels: Optional[Dict[str, List[str]]] = None) -> None:
        """Add a list of IPs to the map, resolving them in a background thread."""
        self._queue_lookup(ips, category, labels or {})

    def _queue_lookup(self, ips: List[str], category: str,
                      link_map: Dict[str, object]) -> None:
        """Filter to public IPs and start lookup worker."""
        public = [ip for ip in ips if _is_plottable(ip)]
        if not public:
            return
        if self._lookup_worker and self._lookup_worker.isRunning():
            # Queue is simplified: just drop if busy (no long queues of public IPs)
            return
        self._lookup_worker = _LookupWorker(public, self._locator)
        self._lookup_worker.result_ready.connect(
            lambda results, cat=category, lm=link_map: self._on_results(results, cat, lm))
        self._lookup_worker.error.connect(
            lambda msg: None)   # silent fail — geo is best-effort
        self._lookup_worker.start()

    @pyqtSlot(list)
    def _on_results(self, results: List[GeoResult], category: str,
                    link_map: Dict[str, object]) -> None:
        for r in results:
            links = link_map.get(r.ip, [])
            if isinstance(links, str):
                links = [links]
            self._points[r.ip] = (r, category, list(links))
        self._refresh_table()
        self._redraw_map()

    # ── Button handlers ───────────────────────────────────────────────────────

    def _on_add_manual(self) -> None:
        raw = self._manual_edit.text().strip()
        if not raw:
            return
        import re
        ips = re.split(r"[,\s]+", raw)
        valid = [ip.strip() for ip in ips if ip.strip()]
        self._manual_edit.clear()
        self.add_ips(valid, _CAT_MANUAL)

    def _on_clear_all(self) -> None:
        self._points.clear()
        self._selected_ip = None
        self._ip_table.setRowCount(0)
        self._detail_ip.setText("—")
        self._detail_body.setText("Click a dot on the map to see details.")
        self._detail_links.setText("")
        self._redraw_map()

    def _on_reload_db(self) -> None:
        self._locator.reload()
        self._refresh_db_status()
        # Re-resolve all existing points
        if self._points:
            all_ips = list(self._points.keys())
            cats   = {ip: self._points[ip][1] for ip in all_ips}
            links  = {ip: self._points[ip][2] for ip in all_ips}
            self._points.clear()
            for ip in all_ips:
                self._queue_lookup([ip], cats[ip], {ip: links[ip]})

    def _on_download_db(self) -> None:
        url = self._permalink_edit.text().strip()
        if not url:
            self._dl_status.setText("Paste a MaxMind permalink URL first.")
            self._dl_status.setStyleSheet(f"font-size:9px; color:{AMBER};")
            return
        self._btn_dl.setEnabled(False)
        self._dl_status.setText("Downloading…")
        self._dl_status.setStyleSheet(f"font-size:9px; color:{TEXT_SECONDARY};")

        self._dl_worker = _DownloadWorker(url)
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.done.connect(self._on_dl_done)
        self._dl_worker.error.connect(self._on_dl_error)
        self._dl_worker.start()

    @pyqtSlot(int, int)
    def _on_dl_progress(self, received: int, total: int) -> None:
        if total > 0:
            pct = int(received * 100 / total)
            self._dl_status.setText(f"Downloading… {pct}%")
        else:
            mb = received / 1_048_576
            self._dl_status.setText(f"Downloading… {mb:.1f} MB")

    @pyqtSlot(str)
    def _on_dl_done(self, path: str) -> None:
        self._btn_dl.setEnabled(True)
        self._dl_status.setText(f"Saved to {Path(path).name}")
        self._dl_status.setStyleSheet(f"font-size:9px; color:{GREEN};")
        self._locator.reload()
        self._refresh_db_status()

    @pyqtSlot(str)
    def _on_dl_error(self, msg: str) -> None:
        self._btn_dl.setEnabled(True)
        self._dl_status.setText(f"Error: {msg}")
        self._dl_status.setStyleSheet(f"font-size:9px; color:{RED};")

    # ── Table ─────────────────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        self._ip_table.setRowCount(0)
        for ip, (result, category, links) in sorted(self._points.items()):
            row = self._ip_table.rowCount()
            self._ip_table.insertRow(row)
            items = [
                QTableWidgetItem(ip),
                QTableWidgetItem(result.country_name or result.country or "—"),
                QTableWidgetItem(result.city or "—"),
                QTableWidgetItem(f"{result.latitude:.3f}" if result.latitude else "—"),
                QTableWidgetItem(f"{result.longitude:.3f}" if result.longitude else "—"),
                QTableWidgetItem(category),
                QTableWidgetItem(", ".join(links) if links else ""),
            ]
            # Colour the category cell
            cat_color = _MARKER_COLOR.get(category, ACCENT)
            items[5].setForeground(QColor(cat_color))

            for col, item in enumerate(items):
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                self._ip_table.setItem(row, col, item)

    def _on_table_selection(self) -> None:
        rows = self._ip_table.selectedItems()
        if not rows:
            return
        ip = self._ip_table.item(self._ip_table.currentRow(), 0)
        if ip and ip.text() in self._points:
            self._select_ip(ip.text())

    # ── DB status ─────────────────────────────────────────────────────────────

    def _refresh_db_status(self) -> None:
        path = db_path()
        if self._locator.is_available:
            self._db_status_dot.setStyleSheet(f"color:{GREEN}; font-size:12px;")
            self._db_status_lbl.setText("GeoLite2-City.mmdb loaded")
            self._db_status_lbl.setStyleSheet(f"font-size:10px; color:{GREEN};")
        elif path.exists():
            self._db_status_dot.setStyleSheet(f"color:{AMBER}; font-size:12px;")
            self._db_status_lbl.setText("Database found but could not be opened")
            self._db_status_lbl.setStyleSheet(f"font-size:10px; color:{AMBER};")
        else:
            self._db_status_dot.setStyleSheet(f"color:{TEXT_MUTED}; font-size:12px;")
            self._db_status_lbl.setText("No database — download below or copy .mmdb manually")
            self._db_status_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_MUTED};")
        self._db_path_lbl.setText(str(path))


# ── Utilities ─────────────────────────────────────────────────────────────────

def _is_plottable(ip: str) -> bool:
    """Return True for valid, non-bogon IPv4 addresses."""
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv6Address):
            return False   # skip IPv6 for now (world map is 2D)
        return not addr.is_private and not addr.is_loopback and not addr.is_link_local
    except ValueError:
        return False
