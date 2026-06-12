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
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("QtAgg")
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import FancyArrowPatch, Polygon as MplPolygon
from matplotlib.collections import PatchCollection


def _geojson_path() -> Path:
    base = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent.parent.parent
    return base / "ui" / "assets" / "world_110m.geojson"


_PATCHES_CACHE: list = []   # parsed once, reused across redraws and zoom


def _load_country_patches(color: str, alpha: float) -> list:
    """Return a list of MplPolygon patches for all country outlines (cached after first parse)."""
    global _PATCHES_CACHE
    if _PATCHES_CACHE:
        return _PATCHES_CACHE
    geo = _geojson_path()
    if not geo.exists():
        return []
    try:
        with open(geo, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return []

    patches = []
    for feature in data.get("features", []):
        geom = feature.get("geometry") or {}
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if gtype == "Polygon":
            rings = [coords[0]]
        elif gtype == "MultiPolygon":
            rings = [poly[0] for poly in coords]
        else:
            continue
        for ring in rings:
            if len(ring) < 3:
                continue
            arr = np.array(ring, dtype=float)
            patches.append(MplPolygon(arr[:, :2], closed=True))
    _PATCHES_CACHE = patches
    return patches

from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.empty_state_card import EmptyStateCard

from modules.geo_locator import (
    GEOLITE_MIRROR_URL,
    GeoLocator,
    GeoResult,
    db_path,
    download_db_permalink,
    get_locator,
)
from ui.styles import (
    ACCENT, ACCENT_DARK, AMBER, BG_ALT_ROW,
    BG_CARD, BG_HOVER, BORDER,
    CARD_HDR_BORDER, CARD_RADIUS, CHART_GRID,
    CHART_PLOT_BG, GREEN, INPUT_PLACEHOLDER,
    MAP_LAND_BG, MAP_LAND_BORDER, RED, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, TH_BG, TH_TEXT,
    WHITE,
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
            f"QPushButton {{ background:{ACCENT}; color:{WHITE}; border:none;"
            f"  border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{ACCENT_DARK}; }}"
            f"QPushButton:disabled {{ background:{INPUT_PLACEHOLDER}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background:{BG_CARD}; color:{TEXT_PRIMARY};"
            f"  border:1px solid {BORDER}; border-radius:3px; padding:0 10px; }}"
            f"QPushButton:hover {{ background:{BG_HOVER}; }}"
            f"QPushButton:disabled {{ color:{TEXT_MUTED}; }}"
            f"QPushButton:pressed {{ color:{TEXT_PRIMARY}; }}"
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

def _country_flag(code: str) -> str:
    """Convert a 2-letter ISO country code to a flag emoji."""
    if not code or len(code) != 2:
        return ""
    code = code.upper()
    try:
        return chr(0x1F1E6 + ord(code[0]) - ord("A")) + chr(0x1F1E6 + ord(code[1]) - ord("A"))
    except Exception:
        return ""


class GeoMapPage(QWidget):
    """World-map geolocation of internet-facing IPs."""

    navigate_requested = pyqtSignal(str)   # page label — emitted by "View in Threat Intel →"
    scan_requested     = pyqtSignal()      # emitted by empty-state CTA

    def __init__(self, store=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._locator: GeoLocator = get_locator()
        # ip → (GeoResult, category, [linked labels])
        self._points: Dict[str, Tuple[GeoResult, str, List[str]]] = {}
        self._lookup_worker: Optional[_LookupWorker] = None
        self._dl_worker: Optional[_DownloadWorker] = None
        self._selected_ip: Optional[str] = None

        # Zoom state — stores intended view center/span; max zoom-out is ±180/±90
        self._xlim: list = [-155.0, 155.0]
        self._ylim: list = [-55.0, 78.0]
        # Home coordinates for threat arc lines (set via set_home_ip)
        self._home_ll: Optional[Tuple[float, float]] = None

        self._build_ui()
        self._refresh_db_status()

    # ── Page lifecycle ────────────────────────────────────────────────────────

    def hideEvent(self, event) -> None:
        """Release the MaxMind mmdb file handle when this page is hidden."""
        try:
            get_locator().close()
        except Exception:
            pass  # non-fatal — locator may already be closed
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        """Re-open the MaxMind mmdb when the page becomes visible again."""
        super().showEvent(event)
        try:
            get_locator().reload()
        except Exception:
            pass  # non-fatal — mmdb may not be installed yet

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
            "Plot public IPs from threat intel, exposure scans, or manual entry on a world map. "
            "The IP Lookup Database (GeoLite2) resolves IPs to coordinates — "
            "download it once to enable dot placement. The map outline is always available."
        )
        sub.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        sub.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(sub)

        # DB status + import row
        top_row = QHBoxLayout()
        top_row.setSpacing(6)
        self._db_card, self._db_layout = _card("IP Lookup Database (GeoLite2)")
        self._import_card, self._import_layout = _card("Add IPs")
        top_row.addWidget(self._db_card, 1)
        top_row.addWidget(self._import_card, 2)
        root.addLayout(top_row)

        self._build_db_card()
        self._build_import_card()

        # ── Content stack: page 0 = empty state, page 1 = map + table ───────────
        self._map_stack = QStackedWidget()

        # Page 0 — empty state
        _empty = EmptyStateCard(
            icon="⊕",
            title="No locations to display",
            what_it_shows=(
                "Public IP addresses from threat intel, exposure scans, and manual "
                "entry plotted on a world map with country, city, and ASN data."
            ),
            why_it_matters=(
                "Knowing where external connections originate helps spot "
                "geo-suspicious traffic and suspicious ISPs at a glance."
            ),
            btn_label="Scan to discover IPs →",
        )
        _empty.clicked.connect(self.scan_requested.emit)
        self._map_stack.addWidget(_empty)

        # Page 1 — map + IP table
        _map_page = QWidget()
        _map_page_lay = QVBoxLayout(_map_page)
        _map_page_lay.setContentsMargins(0, 0, 0, 0)
        _map_page_lay.setSpacing(6)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_map_panel())
        splitter.addWidget(self._build_detail_panel())
        splitter.setSizes([900, 280])
        _map_page_lay.addWidget(splitter, 1)
        _map_page_lay.addWidget(self._build_ip_table_card())

        self._map_stack.addWidget(_map_page)
        root.addWidget(self._map_stack, 1)

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

        # Quick download (P3TERX mirror — no account required)
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        quick_lbl = QLabel("No database?")
        quick_lbl.setStyleSheet(f"font-size:10px; color:{TEXT_SECONDARY};")
        self._btn_quick_dl = _btn("↓  Quick Download  (no account needed)", accent=True)
        self._btn_quick_dl.setToolTip(
            "Downloads GeoLite2-City.mmdb from the P3TERX mirror on GitHub.\n"
            "Source: github.com/P3TERX/GeoLite.mmdb  (~67 MB)"
        )
        self._btn_quick_dl.clicked.connect(self._on_quick_download)
        quick_row.addWidget(quick_lbl)
        quick_row.addWidget(self._btn_quick_dl)
        quick_row.addStretch()
        self._db_layout.addLayout(quick_row)

        # Custom URL download (MaxMind permalink or any trusted URL)
        dl_row = QHBoxLayout()
        dl_row.setSpacing(4)
        self._permalink_edit = QLineEdit()
        self._permalink_edit.setPlaceholderText(
            "Or paste a custom MaxMind permalink URL…")
        self._permalink_edit.setFixedHeight(24)
        self._permalink_edit.setStyleSheet(
            f"border:1px solid {BORDER}; border-radius:3px; padding:0 6px;"
            f"font-size:10px; background:{BG_CARD};")
        self._btn_dl = _btn("↓  Download")
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

        btn_add    = _btn("✚  Add", accent=True)
        btn_ti     = _btn("🧠  Threat Intel IPs")
        btn_ti.setToolTip("Import top-confidence IP indicators from the local threat intel cache")
        btn_clear  = _btn("✕  Clear All")
        btn_add.clicked.connect(self._on_add_manual)
        btn_ti.clicked.connect(self._load_threat_intel_ips)
        btn_clear.clicked.connect(self._on_clear_all)

        row.addWidget(QLabel("Manual:"))
        row.addWidget(self._manual_edit, 1)
        row.addWidget(btn_add)
        row.addWidget(btn_ti)
        row.addWidget(btn_clear)
        self._import_layout.addLayout(row)

        legend_row = QHBoxLayout()
        for cat, color in _MARKER_COLOR.items():
            legend_row.addWidget(_dot(color))
            lbl = QLabel(cat)
            lbl.setStyleSheet(f"font-size:9px; color:{TEXT_SECONDARY};")
            legend_row.addWidget(lbl)
            legend_row.addSpacing(8)
        self._chk_arcs = QCheckBox("Show lines from home to threat IPs")
        self._chk_arcs.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
        self._chk_arcs.setToolTip(
            "Draws arcs from your network's public IP to each Threat Intel dot.\n"
            "Set home location via right-click 'Show on Geolocation Map' on a local device."
        )
        self._chk_arcs.stateChanged.connect(self._redraw_map)
        legend_row.addWidget(self._chk_arcs)
        self._chk_heatmap = QCheckBox("Show risk heatmap")
        self._chk_heatmap.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
        self._chk_heatmap.setToolTip(
            "Draws radial colour glow behind Threat Intel and Exposed Service dots\n"
            "to highlight geographic risk concentrations."
        )
        self._chk_heatmap.stateChanged.connect(self._redraw_map)
        legend_row.addWidget(self._chk_heatmap)
        legend_row.addStretch()
        self._import_layout.addLayout(legend_row)

    def _build_map_panel(self) -> QWidget:
        panel = QWidget()
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(0)

        self._fig = Figure(facecolor=CHART_PLOT_BG, dpi=96)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self._canvas)

        self._canvas.mpl_connect("button_press_event", self._on_map_click)
        self._canvas.mpl_connect("scroll_event", self._on_scroll)
        self._canvas.mpl_connect("resize_event", lambda e: self._redraw_map())
        self._draw_base_map()
        self._canvas.draw()
        return panel

    def _build_detail_panel(self) -> QWidget:
        card, layout = _card("Selected IP — Details")

        self._detail_ip = QLabel("—")
        self._detail_ip.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._detail_ip.setStyleSheet(f"color:{TEXT_PRIMARY};")

        # Placeholder — shown when no dot is selected (or while resolving)
        self._detail_body = QLabel("Click a dot on the map to see details.")
        self._detail_body.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        self._detail_body.setWordWrap(True)

        # Enriched widgets — hidden until an IP is selected
        self._detail_location = QLabel("")
        self._detail_location.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:10px;")
        self._detail_location.setWordWrap(True)
        self._detail_location.setVisible(False)

        self._detail_org = QLabel("")
        self._detail_org.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
        self._detail_org.setWordWrap(True)
        self._detail_org.setVisible(False)

        self._detail_cat = QLabel("")
        self._detail_cat.setStyleSheet(f"font-size:10px;")
        self._detail_cat.setVisible(False)

        self._detail_risk = QLabel("")
        self._detail_risk.setStyleSheet(f"font-size:10px;")
        self._detail_risk.setVisible(False)

        self._detail_sep = QFrame()
        self._detail_sep.setFrameShape(QFrame.Shape.HLine)
        self._detail_sep.setStyleSheet(f"color:{BORDER}; margin:2px 0;")
        self._detail_sep.setVisible(False)

        self._detail_ti_hdr = QLabel("Related threat intel:")
        self._detail_ti_hdr.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:9px; font-weight:600;")
        self._detail_ti_hdr.setVisible(False)

        self._detail_ti_text = QLabel("")
        self._detail_ti_text.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
        self._detail_ti_text.setWordWrap(True)
        self._detail_ti_text.setVisible(False)

        self._detail_view_ti = QPushButton("View in Threat Intel →")
        self._detail_view_ti.setFlat(True)
        self._detail_view_ti.setStyleSheet(
            f"QPushButton {{ color:{ACCENT}; font-size:9px; border:none;"
            f"  padding:0; text-align:left; }}"
            f"QPushButton:hover {{ color:{TH_BG}; }}"
            f"QPushButton:pressed {{ background:{BG_HOVER}; color:{ACCENT}; }}"
        )
        self._detail_view_ti.setCursor(Qt.CursorShape.PointingHandCursor)
        self._detail_view_ti.clicked.connect(
            lambda: self.navigate_requested.emit("Threat Intel"))
        self._detail_view_ti.setVisible(False)

        self._detail_alerts = QLabel("")
        self._detail_alerts.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        self._detail_alerts.setVisible(False)

        self._detail_links = QLabel("")
        self._detail_links.setStyleSheet(f"color:{TEXT_MUTED}; font-size:9px;")
        self._detail_links.setWordWrap(True)

        for w in (self._detail_ip, self._detail_body,
                  self._detail_location, self._detail_org,
                  self._detail_cat, self._detail_risk,
                  self._detail_sep,
                  self._detail_ti_hdr, self._detail_ti_text,
                  self._detail_view_ti, self._detail_alerts,
                  self._detail_links):
            layout.addWidget(w)
        layout.addStretch()

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

    def _screen_limits(self):
        """Compute xlim/ylim that fill the canvas at equirectangular proportions.

        Replaces set_aspect so limits are not double-expanded on figure resize.
        Returns the stored limits unchanged if the canvas isn't laid out yet.
        """
        w = self._canvas.width()
        h = self._canvas.height()
        if w <= 0 or h <= 0:
            return list(self._xlim), list(self._ylim)

        widget_ratio = w / h
        lon_span = self._xlim[1] - self._xlim[0]
        lat_span = self._ylim[1] - self._ylim[0]
        cx = (self._xlim[0] + self._xlim[1]) / 2
        cy = (self._ylim[0] + self._ylim[1]) / 2
        data_ratio = lon_span / lat_span

        # Expand whichever dimension is "too small" to fill the canvas
        if data_ratio > widget_ratio:
            lat_span = lon_span / widget_ratio
        else:
            lon_span = lat_span * widget_ratio

        lon_span = min(lon_span, 360.0)
        lat_span = min(lat_span, 180.0)
        cx = max(-180.0 + lon_span / 2, min(180.0 - lon_span / 2, cx))
        cy = max(-90.0 + lat_span / 2, min(90.0 - lat_span / 2, cy))
        return [cx - lon_span / 2, cx + lon_span / 2], [cy - lat_span / 2, cy + lat_span / 2]

    def _draw_base_map(self) -> None:
        """Clear axes and redraw world outline using stored zoom limits."""
        ax = self._ax
        ax.cla()
        ax.set_facecolor(CHART_PLOT_BG)
        xlim, ylim = self._screen_limits()
        ax.set_xlim(xlim)
        ax.set_ylim(ylim)
        ax.axis("off")

        # Grid lines
        for lon in range(-180, 181, 30):
            ax.axvline(lon, color=CHART_GRID, linewidth=0.4, zorder=0)
        for lat in range(-90, 91, 30):
            ax.axhline(lat, color=CHART_GRID, linewidth=0.4, zorder=0)

        try:
            self._draw_country_borders()
        except Exception:
            ax.text(0, 0,
                    "Install Cartopy or Natural Earth shapefiles for country borders.",
                    ha="center", va="center", color=TEXT_MUTED,
                    fontsize=8, transform=ax.transData)

        self._fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    def _draw_country_borders(self) -> None:
        patches = _load_country_patches(CHART_GRID, alpha=1.0)
        if not patches:
            self._ax.text(
                0, 0,
                "Map data not found. The file ui/assets/world_110m.geojson is missing.",
                ha="center", va="center", color=TEXT_MUTED,
                fontsize=8, transform=self._ax.transData,
            )
            return
        col = PatchCollection(
            patches,
            facecolor=MAP_LAND_BG,   # dark ocean-contrast land fill
            edgecolor=MAP_LAND_BORDER,   # subtle border
            linewidth=0.4,
            zorder=1,
        )
        self._ax.add_collection(col)

    def _redraw_map(self, *_args) -> None:
        """Redraw base map then overlay clustered data points and optional arcs."""
        self._draw_base_map()

        if self._points:
            plottable = [
                (ip, result, cat)
                for ip, (result, cat, _) in self._points.items()
                if not result.is_bogon
                and not (result.latitude == 0.0 and result.longitude == 0.0)
            ]

            # Threat arc lines (drawn below dots so dots appear on top)
            show_arcs = hasattr(self, "_chk_arcs") and self._chk_arcs.isChecked()
            if show_arcs and self._home_ll is not None:
                home_lat, home_lon = self._home_ll
                for _ip, result, cat in plottable:
                    if cat != _CAT_THREAT:
                        continue
                    arrow = FancyArrowPatch(
                        (home_lon, home_lat),
                        (result.longitude, result.latitude),
                        connectionstyle="arc3,rad=0.15",
                        arrowstyle="-",
                        color=RED,
                        linewidth=0.5,
                        alpha=0.18,
                        zorder=2,
                        transform=self._ax.transData,
                    )
                    self._ax.add_patch(arrow)

            # Risk heatmap glow (VIZ-8) — radial patches behind dots
            show_heatmap = hasattr(self, "_chk_heatmap") and self._chk_heatmap.isChecked()
            if show_heatmap:
                import matplotlib.patches as _mpatches
                _glow_cfg = {
                    _CAT_THREAT:  (RED,   0.09, 8.0),
                    _CAT_EXPOSED: (AMBER, 0.06, 6.0),
                }
                for _ip, result, cat in plottable:
                    if cat not in _glow_cfg:
                        continue
                    glow_color, glow_alpha, glow_r = _glow_cfg[cat]
                    for r_mult in (1.0, 0.6, 0.3):
                        circle = _mpatches.Circle(
                            (result.longitude, result.latitude),
                            radius=glow_r * r_mult,
                            color=glow_color,
                            alpha=glow_alpha * r_mult,
                            zorder=2,
                            transform=self._ax.transData,
                            linewidth=0,
                        )
                        self._ax.add_patch(circle)

            # Screen-space clustered dots
            for cluster in self._cluster_points(plottable):
                color = _MARKER_COLOR.get(cluster["cat"], ACCENT)
                lon, lat = cluster["lon"], cluster["lat"]
                selected = cluster["selected"]
                count = cluster["count"]
                size = 90 if selected else (45 + min(count - 1, 15) * 4 if count > 1 else 40)
                edge = TEXT_PRIMARY if selected else "none"
                self._ax.scatter(
                    lon, lat, s=size, c=color, zorder=3,
                    edgecolors=edge, linewidths=1.2, alpha=0.85,
                )
                if count >= 3:
                    self._ax.text(
                        lon, lat, str(count),
                        ha="center", va="center",
                        fontsize=6, color=WHITE, fontweight="bold", zorder=4,
                    )

        self._canvas.draw()

    # ── Canvas click ──────────────────────────────────────────────────────────

    def _on_map_click(self, event) -> None:
        if event.inaxes != self._ax:
            return
        if event.dblclick:
            self._xlim = [-180.0, 180.0]   # full world; set_aspect fills screen
            self._ylim = [-90.0, 90.0]
            self._redraw_map()
            return
        if event.button != 1:
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

        # -- Location ---
        flag = _country_flag(result.country)
        country = result.country_name or result.country or "—"
        loc = f"{flag} {country}".strip() if flag else country
        if result.city:
            loc += f"  ·  {result.city}"
        self._detail_location.setText(loc)
        self._detail_location.setVisible(True)

        # -- Org / ASN ---
        org_parts = [p for p in (result.asn, result.org) if p]
        if org_parts:
            self._detail_org.setText("  ·  ".join(org_parts))
            self._detail_org.setVisible(True)
        else:
            self._detail_org.setVisible(False)

        # -- Category chip ---
        cat_color = _MARKER_COLOR.get(category, ACCENT)
        self._detail_cat.setText(f"Category:  ● {category}")
        self._detail_cat.setStyleSheet(f"color:{cat_color}; font-size:10px;")
        self._detail_cat.setVisible(True)

        # -- Threat intel: risk chip + related entries ---
        ti_entries: list = []
        try:
            from modules.threat_intel import load_from_cache
            ti_entries = [
                e for e in load_from_cache()
                if getattr(e, "itype", "") == "ip" and e.indicator == ip
            ]
        except Exception:
            pass  # non-fatal

        if ti_entries:
            best = max(ti_entries, key=lambda e: e.confidence)
            conf = best.confidence
            if conf >= 90:
                risk_color, risk_label = RED, "CRITICAL"
            elif conf >= 70:
                risk_color, risk_label = RED, "HIGH"
            elif conf >= 50:
                risk_color, risk_label = AMBER, "MEDIUM"
            else:
                risk_color, risk_label = TEXT_SECONDARY, "LOW"
            self._detail_risk.setText(f"Risk:  ● {risk_label}  (confidence {conf}%)")
            self._detail_risk.setStyleSheet(f"font-size:10px; color:{risk_color};")
            self._detail_risk.setVisible(True)

            lines = []
            for e in ti_entries[:3]:
                cats = ", ".join(e.categories[:2]) if e.categories else e.source
                suffix = f"  [{e.last_seen}]" if getattr(e, "last_seen", "") else ""
                lines.append(f"  • {e.source}: {cats}{suffix}")
            self._detail_ti_hdr.setVisible(True)
            self._detail_ti_text.setText("\n".join(lines))
            self._detail_ti_text.setVisible(True)
            self._detail_view_ti.setVisible(True)
        else:
            self._detail_risk.setVisible(False)
            self._detail_ti_hdr.setVisible(False)
            self._detail_ti_text.setVisible(False)
            self._detail_view_ti.setVisible(False)

        # -- Alert count from MetricStore ---
        has_extra = bool(ti_entries)
        if self._store is not None:
            try:
                recent = self._store.get_recent_alerts(hours=24)
                count = sum(1 for a in recent if a.get("host", "") == ip)
                self._detail_alerts.setText(f"Alerts in last 24 h:  {count}")
                self._detail_alerts.setStyleSheet(
                    f"color:{RED}; font-size:9px;" if count > 0
                    else f"color:{TEXT_MUTED}; font-size:9px;"
                )
                self._detail_alerts.setVisible(True)
                has_extra = True
            except Exception:
                self._detail_alerts.setVisible(False)
        else:
            self._detail_alerts.setVisible(False)

        self._detail_sep.setVisible(has_extra)

        # -- Linked labels ---
        if links:
            self._detail_links.setText("Linked:\n" + "\n".join(f"  • {l}" for l in links))
        else:
            self._detail_links.setText("")

        # Hide placeholder, show enriched panel
        self._detail_body.setVisible(False)

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

    def navigate_to_ip(self, ip: str, category: str = _CAT_MANUAL,
                       label: str = "") -> None:
        """Add a single IP and select it — called by right-click 'Show on Map'."""
        self.add_ips([ip], category, {ip: [label]} if label else {})
        self._selected_ip = ip

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
        resolved_ips = set()
        for r in results:
            links = link_map.get(r.ip, [])
            if isinstance(links, str):
                links = [links]
            self._points[r.ip] = (r, category, list(links))
            resolved_ips.add(r.ip)
        if self._points and self._map_stack.currentIndex() == 0:
            self._map_stack.setCurrentIndex(1)
        self._refresh_table()
        self._redraw_map()
        # If the selected IP just resolved, populate the enriched detail panel
        if self._selected_ip and self._selected_ip in resolved_ips:
            self._select_ip(self._selected_ip)

    # ── Scroll zoom ───────────────────────────────────────────────────────────

    def _on_scroll(self, event) -> None:
        if event.inaxes != self._ax or event.xdata is None:
            return
        factor = 0.80 if event.button == "up" else 1.25   # zoom in / out ~20%
        cx, cy = event.xdata, event.ydata

        # Zoom from the currently displayed limits (already aspect-corrected)
        # so the cursor stays anchored to the same map position.
        xl, xr = self._ax.get_xlim()
        yb, yt = self._ax.get_ylim()
        new_xl = cx + (xl - cx) * factor
        new_xr = cx + (xr - cx) * factor
        new_yb = cy + (yb - cy) * factor
        new_yt = cy + (yt - cy) * factor

        lon_span = min(new_xr - new_xl, 360.0)
        lat_span = min(new_yt - new_yb, 180.0)
        lon_span = max(lon_span, 2.0)
        lat_span = max(lat_span, 1.0)
        new_cx = (new_xl + new_xr) / 2
        new_cy = (new_yb + new_yt) / 2
        new_cx = max(-180.0 + lon_span / 2, min(180.0 - lon_span / 2, new_cx))
        new_cy = max(-90.0 + lat_span / 2, min(90.0 - lat_span / 2, new_cy))
        self._xlim = [new_cx - lon_span / 2, new_cx + lon_span / 2]
        self._ylim = [new_cy - lat_span / 2, new_cy + lat_span / 2]
        self._redraw_map()

    # ── Clustering ────────────────────────────────────────────────────────────

    def _cluster_points(self, plottable: list) -> list:
        """Group nearby screen-space dots; returns list of cluster dicts."""
        if not plottable:
            return []

        coords = np.array([[r.longitude, r.latitude] for _, r, _ in plottable])
        try:
            display = self._ax.transData.transform(coords)
        except Exception:
            display = coords   # fallback: use data coords as proxy

        RADIUS_PX = 18
        used = [False] * len(plottable)
        clusters = []

        for i in range(len(plottable)):
            if used[i]:
                continue
            group = [i]
            for j in range(i + 1, len(plottable)):
                if used[j]:
                    continue
                dx = display[i, 0] - display[j, 0]
                dy = display[i, 1] - display[j, 1]
                if dx * dx + dy * dy < RADIUS_PX * RADIUS_PX:
                    group.append(j)
            for idx in group:
                used[idx] = True

            cats = [plottable[k][2] for k in group]
            dominant = max(set(cats), key=cats.count)
            center_lon = sum(plottable[k][1].longitude for k in group) / len(group)
            center_lat = sum(plottable[k][1].latitude for k in group) / len(group)
            selected = any(plottable[k][0] == self._selected_ip for k in group)

            clusters.append({
                "lon": center_lon, "lat": center_lat,
                "cat": dominant, "count": len(group), "selected": selected,
            })

        return clusters

    # ── Public API ────────────────────────────────────────────────────────────

    def set_home_ip(self, ip: str) -> None:
        """Cache the home location (WAN IP) used to draw threat arc lines."""
        try:
            result = self._locator.lookup(ip)
            if result and not result.is_bogon and result.latitude != 0.0:
                self._home_ll = (result.latitude, result.longitude)
        except Exception:
            pass  # non-fatal

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
        self._detail_body.setVisible(True)
        self._detail_links.setText("")
        for w in (self._detail_location, self._detail_org, self._detail_cat,
                  self._detail_risk, self._detail_sep, self._detail_ti_hdr,
                  self._detail_ti_text, self._detail_view_ti, self._detail_alerts):
            w.setVisible(False)
        self._redraw_map()

    def _on_reload_db(self) -> None:
        self._locator.reload()
        self._refresh_db_status()
        self._after_db_loaded()

    def _on_quick_download(self) -> None:
        self._btn_quick_dl.setEnabled(False)
        self._dl_status.setText("Downloading from GitHub mirror (~67 MB)…")
        self._dl_status.setStyleSheet(f"font-size:9px; color:{TEXT_SECONDARY};")
        self._dl_worker = _DownloadWorker(GEOLITE_MIRROR_URL)
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.done.connect(self._on_quick_dl_done)
        self._dl_worker.error.connect(self._on_quick_dl_error)
        self._dl_worker.start()

    @pyqtSlot(str)
    def _on_quick_dl_done(self, path: str) -> None:
        self._btn_quick_dl.setEnabled(True)
        self._on_dl_done(path)

    @pyqtSlot(str)
    def _on_quick_dl_error(self, msg: str) -> None:
        self._btn_quick_dl.setEnabled(True)
        self._on_dl_error(msg)

    def _on_download_db(self) -> None:
        url = self._permalink_edit.text().strip()
        if not url:
            self._dl_status.setText("Paste a permalink URL first.")
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
        self._after_db_loaded()

    @pyqtSlot(str)
    def _on_dl_error(self, msg: str) -> None:
        self._btn_dl.setEnabled(True)
        self._dl_status.setText(
            f"GeoLite2 database download failed — {msg}. "
            "Check your internet connection and try again."
        )
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

    def _after_db_loaded(self) -> None:
        """Called whenever the GeoLite2 DB becomes available (download or reload).

        1. Re-resolves any existing zero-coordinate points in one batch.
        2. If the map is still empty, auto-imports IPs from the threat intel cache.
        """
        if not self._locator.is_available:
            return

        # Batch re-resolve: collect all unresolved IPs, clear them, queue once per category
        by_cat: Dict[str, Dict[str, list]] = {}
        for ip, (result, cat, links) in list(self._points.items()):
            if not result.is_bogon and result.latitude == 0 and result.longitude == 0:
                by_cat.setdefault(cat, {})[ip] = links
        for ip in [ip for cat_map in by_cat.values() for ip in cat_map]:
            self._points.pop(ip, None)
        for cat, link_map in by_cat.items():
            self._queue_lookup(list(link_map.keys()), cat, link_map)

        # Auto-populate from threat intel if map is still empty
        if not self._points:
            self._load_threat_intel_ips()

    def _load_threat_intel_ips(self) -> None:
        """Import top-confidence IP indicators from the local threat intel cache."""
        try:
            from modules.threat_intel import load_from_cache
            entries = [e for e in load_from_cache() if getattr(e, "itype", "") == "ip"]
            entries.sort(key=lambda e: getattr(e, "confidence", 0), reverse=True)
            entries = entries[:500]
            if entries:
                link_map = {e.indicator: [getattr(e, "source", "")] for e in entries}
                self._queue_lookup([e.indicator for e in entries], _CAT_THREAT, link_map)
                self._dl_status.setText(
                    f"Auto-loaded {len(entries)} threat intel IPs from local cache."
                )
                self._dl_status.setStyleSheet(f"font-size:9px; color:{TEXT_SECONDARY};")
        except Exception:
            pass  # non-fatal

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
