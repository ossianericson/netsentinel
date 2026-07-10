"""
network_map_page.py — Interactive Cytoscape.js Network Map page.

Replaces the embedded TopologyWidget matplotlib tab with a full-page widget
that offers two views:
  • Interactive (QWebEngineView + Cytoscape.js) — drag-to-arrange, physics
    layouts, Focus Mode, per-node HTML tooltips, position persistence via
    QWebChannel bridge.
  • Classic (TopologyWidget matplotlib) — retained as a fallback for users
    without PyQt6-WebEngine or in headless mode.

The page implements the same public render() / update_lldp_neighbors() API
as TopologyWidget so that all existing callers in scan_wiring.py continue
to work without modification.

Architecture:
  • UI layer — inherits QWidget; no direct DB writes.
  • WebEngine is lazy-imported so the app starts even without PyQt6-WebEngine.
  • All colours come from ui/styles.py.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QObject, QSettings, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.styles import (
    ACCENT, ACCENT_DARK, ACCENT_LITE,
    AMBER, BG_CARD, BG_DARK, BG_HOVER, BORDER,
    GREEN, RED, TEAL, TEXT_MUTED,
    TEXT_PRIMARY, TEXT_SECONDARY, WHITE,
)
from ui.topology_widget import TopologyWidget
from modules.topology_layout import (
    NodePosition, TopologyEdge, clear_layout, compute_scan_id, load_layout, save_layout,
)
from modules.topology_cytoscape import LAYOUT_NAMES
from modules.topology_cytoscape_html import (
    build_cytoscape_html,
    build_elements_for_update,
)
from workers.bandwidth_worker import BandwidthOverlayWorker

log = logging.getLogger(__name__)

_SETTINGS_KEY_LAYOUT = "network_map/layout"
_SETTINGS_KEY_VIEW   = "network_map/active_view"  # "interactive" | "classic"

# Compact inline style for toolbar buttons — overrides the wide-padding
# #btnNetRefresh QSS which is designed for full-size action buttons, not
# the tight fixed-width buttons (32–116 px) used in the map toolbar.
_TOOLBAR_BTN_SS = (
    f"QPushButton{{background:{BG_CARD};color:{TEXT_PRIMARY};border:1px solid {BORDER};"
    f"border-radius:4px;padding:3px 10px;font-size:12px;font-weight:500;}}"
    f"QPushButton:hover{{background:{BG_HOVER};border-color:{ACCENT};color:{ACCENT};}}"
    f"QPushButton:pressed{{background:{ACCENT};color:{WHITE};border-color:{ACCENT_DARK};}}"
    f"QPushButton:checked{{background:{ACCENT};color:{WHITE};border-color:{ACCENT_DARK};}}"
    f"QPushButton:disabled{{background:{BG_CARD};color:{TEXT_MUTED};border-color:{BORDER};}}"
)


# ── QWebChannel bridge (server-side Python object) ───────────────────────────

class _CytoscapeBridge(QObject):
    """Python object exposed to Cytoscape.js via QWebChannel.

    Methods decorated with @pyqtSlot are callable from JavaScript.
    """

    node_clicked_signal = pyqtSignal(str)   # emits IP address
    export_ready        = pyqtSignal(str)   # emits base-64 PNG data URL

    def __init__(self, scan_id: str = "default", parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._scan_id = scan_id
        self._pending_positions: Dict[str, NodePosition] = {}

    def set_scan_id(self, scan_id: str) -> None:
        self._scan_id = scan_id
        self._pending_positions = {}

    @pyqtSlot(str)
    def nodeClicked(self, ip: str) -> None:  # noqa: N802 — JS convention
        self.node_clicked_signal.emit(ip)

    @pyqtSlot(str, str, str)
    def savePosition(self, node_id: str, x_str: str, y_str: str) -> None:  # noqa: N802
        """Persist a node position (0–1 normalised coords from JS)."""
        try:
            x = float(x_str)
            y = float(y_str)
        except (ValueError, TypeError):
            return
        self._pending_positions[node_id] = NodePosition(
            node_id=node_id, x=x, y=y, pinned=True,
        )
        try:
            existing = load_layout(self._scan_id)
            existing.update(self._pending_positions)
            save_layout(self._scan_id, existing)
        except Exception:
            pass  # non-fatal — position save is best-effort

    @pyqtSlot(str)
    def exportPng(self, data_url: str) -> None:  # noqa: N802
        self.export_ready.emit(data_url)


# ── NetworkMapPage ────────────────────────────────────────────────────────────

class NetworkMapPage(QWidget):
    """Full-page Network Map with interactive Cytoscape.js view + Classic fallback.

    Public API (mirrors TopologyWidget so scan_wiring.py needs no changes):
      render(**kwargs)                — feed both views
      update_lldp_neighbors(...)     — update LLDP overlay on both views
      fit_view()                     — fit the active view
      zoom_in() / zoom_out()         — classic view only (no-op on interactive)
      reset_layout()                 — clear saved positions and re-run layout
      node_clicked : pyqtSignal(str) — emitted when user clicks a node
      scan_requested : pyqtSignal()  — emitted by empty-state CTA button
    """

    node_clicked   = pyqtSignal(str)   # IP address of clicked device
    scan_requested = pyqtSignal()      # empty-state "Run Scan" CTA

    def __init__(self, store=None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._store = store
        self._last_render_kwargs: Dict[str, Any] = {}
        self._scan_id = "default"
        self._web_available = False
        self._web_view: Any = None
        self._bridge: Optional[_CytoscapeBridge] = None
        # STARTUP-PERF: QWebEngineView construction (~185 ms) is deferred out of
        # __init__ into the first showEvent() so it never blocks Dashboard build
        # / first paint. render() already guards on _web_available, so any
        # startup cache-restore render before the page is shown safely populates
        # the Classic view only; the Interactive view is filled on first show.
        self._webengine_init_attempted = False
        self._diff_mode = False
        self._traffic_overlay = False
        self._bw_by_mac: Dict[str, float] = {}
        self._bw_worker: Optional[BandwidthOverlayWorker] = None
        # True once setHtml() has been called; subsequent renders use
        # window.updateTopology() to preserve node positions instead of
        # reloading the entire page (which resets layout and causes drift).
        self._topology_loaded = False
        # Node ids present in the live Cytoscape graph as of the last full
        # build or incremental update. Scan results, mesh enrichment, and LLDP
        # data each arrive via separate render() calls in no guaranteed order.
        # Whichever lands first does the full geometric layout (geo_hierarchy
        # etc); whichever lands later is an incremental update that only
        # spirals the *new* node ids in via JS around the gateway — it never
        # re-runs the Python hierarchy algorithm, so the late-arriving group
        # ends up flat and mis-parented instead of nested under its real
        # parent. Tracked so that any update introducing node ids not yet in
        # this set can force one full geometric recompute, instead of leaving
        # the graph half-reflowed until the user manually re-picks a layout.
        self._known_node_ids: set = set()
        # Fires once per app session — auto-fits the view the first time any
        # render() call actually has devices to show, so a brand-new scan
        # always lands fully inside the visible window without the user
        # having to press "Fit" themselves. Forced explicitly (rather than
        # relying on Cytoscape's own post-layout cy.fit()) because that call
        # can run against a zero-size container if the Interactive tab isn't
        # the active one yet, and an incremental updateTopology() never fits.
        self._auto_fit_done = False

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # QStackedWidget: page 0 = empty state, page 1 = map content
        self._outer_stack = QStackedWidget()
        root.addWidget(self._outer_stack)

        # ── Page 0: empty state ──────────────────────────────────────────────
        empty = QWidget()
        empty_lay = QVBoxLayout(empty)
        empty_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon = QLabel("◆")
        empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_icon.setStyleSheet(f"font-size:40px; color:{TEXT_MUTED};")
        empty_title = QLabel("Network Map")
        empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_title.setStyleSheet(
            f"font-size:18px; font-weight:600; color:{TEXT_PRIMARY}; margin-top:12px;"
        )
        empty_body = QLabel(
            "Run a device scan to visualise your network topology.\n"
            "Nodes are drag-to-arrange with physics-based auto-layout."
        )
        empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_body.setWordWrap(True)
        empty_body.setStyleSheet(f"font-size:13px; color:{TEXT_SECONDARY}; margin:8px 40px;")
        btn_scan = QPushButton("Run Scan")
        btn_scan.setFixedWidth(130)
        btn_scan.setStyleSheet(
            f"QPushButton{{background:{ACCENT};color:{WHITE};border:none;"
            f"border-radius:4px;padding:8px 16px;font-size:13px;font-weight:600;}}"
            f"QPushButton:hover{{background:{ACCENT_LITE};color:{WHITE};}}"
            f"QPushButton:pressed{{background:{ACCENT_DARK};color:{WHITE};}}"
        )
        btn_scan.clicked.connect(self.scan_requested)
        empty_lay.addWidget(empty_icon)
        empty_lay.addWidget(empty_title)
        empty_lay.addWidget(empty_body)
        empty_lay.addSpacing(16)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_scan)
        btn_row.addStretch()
        empty_lay.addLayout(btn_row)
        self._outer_stack.addWidget(empty)

        # ── Page 1: map content ──────────────────────────────────────────────
        content = QWidget()
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(8, 4, 8, 4)
        content_lay.setSpacing(2)

        # Toolbar
        toolbar_layout = self._build_toolbar()
        content_lay.addLayout(toolbar_layout)

        # Inner tab: Interactive | Classic
        self._inner_tab = QTabWidget()
        self._inner_tab.setStyleSheet(
            f"QTabWidget::pane{{border:1px solid {BORDER};background:{BG_CARD};}}"
            f"QTabBar::tab{{padding:4px 14px;font-size:12px;background:{BG_DARK};"
            f"color:{TEXT_SECONDARY};border:1px solid {BORDER};}}"
            f"QTabBar::tab:selected{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"font-weight:600;}}"
        )
        self._inner_tab.currentChanged.connect(self._on_view_tab_changed)

        # Interactive tab: QWebEngineView (lazy)
        self._interactive_container = QWidget()
        ic_lay = QVBoxLayout(self._interactive_container)
        ic_lay.setContentsMargins(0, 0, 0, 0)
        self._web_placeholder = QLabel(
            "Interactive view requires PyQtWebEngine.\n"
            "pip install PyQt6-WebEngine\n\n"
            "The Classic view below works without it."
        )
        self._web_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._web_placeholder.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:12px;")
        ic_lay.addWidget(self._web_placeholder)
        self._web_container_layout = ic_lay
        # QWebEngineView init deferred to showEvent() — see __init__ note.

        # LLDP admin hint for Interactive view — toggled by render()
        self._lldp_hint_label = QLabel(
            "⬡  Run as administrator to discover managed switch topology via LLDP"
        )
        self._lldp_hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lldp_hint_label.setStyleSheet(
            f"color:{TEXT_SECONDARY};font-size:11px;padding:3px 8px;"
        )
        self._lldp_hint_label.setVisible(False)
        self._web_container_layout.addWidget(self._lldp_hint_label)

        # Classic tab: TopologyWidget (matplotlib)
        self._classic_widget = TopologyWidget()
        self._classic_widget.node_clicked.connect(self.node_clicked)

        self._inner_tab.addTab(self._interactive_container, "◆  Interactive")
        self._inner_tab.addTab(self._classic_widget,         "◇  Classic")

        content_lay.addWidget(self._inner_tab, 1)
        self._outer_stack.addWidget(content)

        # Restore last-used view tab; fall back to Classic if WebEngine unavailable
        s = QSettings()
        saved_view = s.value(_SETTINGS_KEY_VIEW, "interactive")
        if saved_view == "classic" or not self._web_available:
            self._inner_tab.setCurrentIndex(1)

        # Traffic overlay is turned on the first time the page is shown (in
        # showEvent) so the bandwidth legend is visible by default.  Deferring
        # to showEvent keeps __init__ safe for headless tests that never call
        # show() — BandwidthOverlayWorker (Scapy sniffer) must not start until
        # the widget is actually on screen.
        self._traffic_overlay_defaulted = False

    def _build_toolbar(self) -> QHBoxLayout:
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 2, 0, 2)
        toolbar.setSpacing(4)

        # Layout selector
        self._layout_combo = QComboBox()
        self._layout_combo.setFixedWidth(116)
        self._layout_combo.setStyleSheet(
            f"QComboBox{{background:{BG_CARD};border:1px solid {BORDER};"
            f"border-radius:4px;padding:3px 8px;font-size:12px;color:{TEXT_PRIMARY};}}"
            f"QComboBox:hover{{border-color:{ACCENT};}}"
            f"QComboBox::drop-down{{border:none;width:18px;}}"
            f"QComboBox QAbstractItemView{{background:{BG_CARD};color:{TEXT_PRIMARY};"
            f"border:1px solid {BORDER};selection-background-color:{BG_HOVER};"
            f"selection-color:{TEXT_PRIMARY};}}"
        )
        for label in LAYOUT_NAMES:
            self._layout_combo.addItem(label)
        s = QSettings()
        saved_layout = s.value(_SETTINGS_KEY_LAYOUT, "Hierarchy")
        idx = self._layout_combo.findText(saved_layout)
        if idx >= 0:
            self._layout_combo.setCurrentIndex(idx)
        self._layout_combo.currentTextChanged.connect(self._on_layout_changed)

        def _btn(label: str, tip: str, w: int = 52) -> QPushButton:
            b = QPushButton(label)
            b.setFixedWidth(w)
            b.setToolTip(tip)
            b.setStyleSheet(_TOOLBAR_BTN_SS)
            return b

        btn_fit  = _btn("Fit",  "Fit topology to window")
        btn_rst  = _btn("Reset Layout", "Clear saved positions and re-layout", 108)
        btn_zin  = _btn("+",   "Zoom in (Classic only)", 32)
        btn_zout = _btn("−",   "Zoom out (Classic only)", 32)

        # Focus Mode toggle
        self._btn_focus = QPushButton("Focus Mode")
        self._btn_focus.setCheckable(True)
        self._btn_focus.setFixedWidth(96)
        self._btn_focus.setToolTip(
            "Highlight only the selected node and its direct neighbours"
        )
        self._btn_focus.setStyleSheet(_TOOLBAR_BTN_SS)

        # Show Changes toggle (exposed as property for scan_wiring compat)
        self._btn_diff = QPushButton("Show Changes")
        self._btn_diff.setCheckable(True)
        self._btn_diff.setFixedWidth(110)
        self._btn_diff.setToolTip(
            "Overlay added/removed devices and links vs. the previous scan"
        )
        self._btn_diff.setStyleSheet(_TOOLBAR_BTN_SS)

        # Diff badge label
        self._diff_label = QLabel()
        self._diff_label.setStyleSheet(
            f"color:{TEAL};font-size:11px;font-weight:600;padding:0 6px;"
        )
        self._diff_label.setVisible(False)

        # Lock Layout toggle — freezes all node positions; disables topology updates
        self._btn_lock = QPushButton("Lock Layout")
        self._btn_lock.setCheckable(True)
        self._btn_lock.setFixedWidth(96)
        self._btn_lock.setToolTip(
            "Freeze all node positions — re-scans update data but cannot move nodes"
        )
        self._btn_lock.setStyleSheet(_TOOLBAR_BTN_SS)

        # Traffic Overlay toggle — live per-MAC bandwidth (requires Scapy + admin)
        self._btn_traffic = QPushButton("Traffic Overlay")
        self._btn_traffic.setCheckable(True)
        self._btn_traffic.setFixedWidth(116)
        self._btn_traffic.setToolTip(
            "Color-code nodes by live bandwidth (requires Scapy + administrator)"
        )
        self._btn_traffic.setStyleSheet(_TOOLBAR_BTN_SS)

        # Bandwidth legend — visible only when Traffic Overlay is on
        self._bw_legend = QLabel(
            f"<span style='color:{GREEN}'>●</span> &lt;0.5 Mbps&nbsp;&nbsp;"
            f"<span style='color:{AMBER}'>●</span> 0.5–5 Mbps&nbsp;&nbsp;"
            f"<span style='color:{RED}'>●</span> &gt;5 Mbps"
        )
        self._bw_legend.setTextFormat(Qt.TextFormat.RichText)
        self._bw_legend.setStyleSheet(
            f"font-size:11px; color:{TEXT_SECONDARY}; padding:0 6px;"
        )
        self._bw_legend.setVisible(False)

        # Export button
        btn_export = _btn("Export PNG", "Export the interactive map as a PNG image", 90)
        btn_export.clicked.connect(self._on_export)

        # Sanitized share button — safe to post publicly (private IPs aliased,
        # MACs/hostnames stripped, public IPs omitted). Renders independently
        # of the on-screen view so a screenshot can never leak real data.
        btn_share = _btn("Share (Sanitized PNG)", "Export a sanitized PNG safe to post publicly", 150)
        btn_share.clicked.connect(self._on_share_export)

        btn_fit.clicked.connect(self.fit_view)
        btn_rst.clicked.connect(self.reset_layout)
        btn_zin.clicked.connect(self.zoom_in)
        btn_zout.clicked.connect(self.zoom_out)
        self._btn_focus.toggled.connect(self._on_focus_toggled)
        self._btn_diff.toggled.connect(self._on_diff_toggled)
        self._btn_lock.toggled.connect(self._on_lock_toggled)
        self._btn_traffic.toggled.connect(self._on_traffic_toggled)

        # Stale-cache indicator — shown when the map is pre-populated from DB,
        # hidden as soon as a live scan completes via render().
        self._stale_label = QLabel("● Cached — run a scan to refresh")
        self._stale_label.setStyleSheet(
            f"color:{TEXT_MUTED};font-size:11px;font-style:italic;padding:0 6px;"
        )
        self._stale_label.setVisible(False)

        toolbar.addWidget(self._layout_combo)
        toolbar.addWidget(btn_fit)
        toolbar.addWidget(btn_zin)
        toolbar.addWidget(btn_zout)
        toolbar.addWidget(self._btn_focus)
        toolbar.addWidget(self._btn_diff)
        toolbar.addWidget(self._diff_label)
        toolbar.addWidget(self._btn_lock)
        toolbar.addWidget(self._btn_traffic)
        toolbar.addWidget(self._bw_legend)
        toolbar.addWidget(self._stale_label)
        toolbar.addStretch()
        toolbar.addWidget(btn_export)
        toolbar.addWidget(btn_share)
        toolbar.addWidget(btn_rst)

        return toolbar

    def _try_init_webengine(self) -> None:
        """Lazy-import QWebEngineView; populate placeholder if unavailable."""
        try:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineScript, QWebEnginePage
            from PyQt6.QtWebChannel import QWebChannel
            from PyQt6.QtCore import QUrl as _QUrl

            # javaScriptConsoleMessage is a virtual method, not a signal —
            # must subclass QWebEnginePage to intercept it.
            class _LogPage(QWebEnginePage):
                def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
                    log.debug("JS [%s:%s] %s", source, line, message)

            self._web_view = QWebEngineView(self._interactive_container)
            self._web_view.setPage(_LogPage(self._web_view))
            self._web_view.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )

            self._bridge = _CytoscapeBridge(parent=self)
            self._bridge.node_clicked_signal.connect(self.node_clicked)
            self._bridge.export_ready.connect(self._on_export_data)

            self._web_channel = QWebChannel(self._web_view.page())
            self._web_channel.registerObject("bridge", self._bridge)
            self._web_view.page().setWebChannel(self._web_channel)

            # Inject qwebchannel.js at document-creation time so QWebChannel is
            # defined before the page's own inline scripts execute.  Using
            # <script src="qrc://..."> inside setHtml() is blocked by Qt6's
            # about:blank origin policy; QWebEngineScript injection bypasses it.
            _qwc = QWebEngineScript()
            _qwc.setName("qwebchannel_init")
            _qwc.setSourceUrl(_QUrl("qrc:///qtwebchannel/qwebchannel.js"))
            _qwc.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            _qwc.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            self._web_view.page().scripts().insert(_qwc)

            # Remove placeholder, add real view
            self._web_placeholder.setParent(None)
            self._web_container_layout.addWidget(self._web_view)
            self._web_available = True

            # Show a light placeholder so the view is never a dark rectangle
            # before the first scan populates it.
            self._web_view.setHtml(
                f"<html><body style='background:{BG_DARK};display:flex;"
                f"align-items:center;justify-content:center;height:100vh;"
                f"font-family:sans-serif;color:{TEXT_SECONDARY};font-size:13px;'>"
                f"Run a scan to populate the interactive map</body></html>"
            )
        except Exception as exc:
            import traceback
            log.warning("WebEngine init failed: %s: %s", type(exc).__name__, exc)
            traceback.print_exc()
            # non-fatal — classic view only; placeholder stays visible

    # ── Public render API (mirrors TopologyWidget) ────────────────────────────

    def render(
        self,
        devices: List[Any],
        gateway_ip: Optional[str] = None,
        gateway_mac: Optional[str] = None,
        mesh_units: Optional[List[Any]] = None,
        mesh_enrichment: Optional[Dict[str, Any]] = None,
        modem_data: Optional[Dict[str, Any]] = None,
        segments: Optional[List[Any]] = None,
        edges: Optional[List[TopologyEdge]] = None,
        down_ips: Optional[set] = None,
        new_ips: Optional[set] = None,
        diff: Optional[Any] = None,
        lldp_neighbors: Optional[List[Any]] = None,
        lldp_admin_needed: bool = False,
        persist_cache: bool = True,
    ) -> None:
        """Update both the Interactive and Classic views with new scan data.

        persist_cache=True (the default, used by every live caller — scan
        results, mesh/hostname enrichment, modem signal updates) saves these
        exact inputs so the next app startup can replay this render verbatim
        instead of a lossy reconstruction. The startup cache-restore path
        itself passes persist_cache=False so it never overwrites a good
        cache with derived/incomplete data.
        """
        self._last_render_kwargs = dict(
            devices=devices,
            gateway_ip=gateway_ip,
            gateway_mac=gateway_mac,
            mesh_units=mesh_units,
            mesh_enrichment=mesh_enrichment,
            modem_data=modem_data,
            segments=segments,
            edges=edges,
            down_ips=down_ips,
            new_ips=new_ips,
            diff=diff,
            lldp_neighbors=lldp_neighbors,
            lldp_admin_needed=lldp_admin_needed,
        )

        # Switch to content view
        if self._outer_stack.currentIndex() == 0:
            self._outer_stack.setCurrentIndex(1)

        # A live scan supersedes any cached view — hide the stale indicator.
        # If we were showing cached data, also reset _topology_loaded so the
        # first live scan builds fresh Cytoscape HTML with a clean layout instead
        # of the incremental-update path which reuses cached node positions.
        if hasattr(self, "_stale_label"):
            if self._stale_label.isVisible():
                self._topology_loaded = False  # force full rebuild on cache→live transition
                self._known_node_ids = set()
            self._stale_label.setVisible(False)

        # Show LLDP admin hint on Interactive tab when rights needed and no neighbors
        self._lldp_hint_label.setVisible(lldp_admin_needed and not lldp_neighbors)

        # Classic view (always rendered)
        try:
            self._classic_widget.render(
                devices, gateway_ip, gateway_mac,
                mesh_units=mesh_units,
                mesh_enrichment=mesh_enrichment,
                modem_data=modem_data,
                segments=segments,
                edges=edges,
                down_ips=down_ips,
                new_ips=new_ips,
                diff=diff,
                lldp_neighbors=lldp_neighbors,
                lldp_admin_needed=lldp_admin_needed,
            )
        except Exception:
            log.debug("network_map_page: classic render failed", exc_info=True)

        # Compute scan_id for position saving — must happen BEFORE
        # _refresh_web_view() below, which reads self._scan_id to load/save
        # positions. Computing it afterwards meant the very first render of
        # each app session (the startup cache render) loaded/saved under the
        # leftover "default" placeholder from __init__ instead of the real
        # subnet-derived key, so it could never find the previous session's
        # saved layout.
        self._scan_id = compute_scan_id(devices)
        if self._bridge is not None:
            self._bridge.set_scan_id(self._layout_storage_key())

        # Interactive view
        if self._web_available and self._web_view is not None:
            self._refresh_web_view(diff=diff if self._diff_mode else None)

        # Auto-fit once the map actually has devices to show — see flag comment
        # in __init__. A short delay lets the just-issued render/layout settle
        # (geometric-layout recompute uses a 250 ms timer of its own) before we
        # snap the viewport to the final node extents.
        if not self._auto_fit_done and devices:
            self._auto_fit_done = True
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self._auto_fit_both_views)
            _t.start(400)

        if persist_cache:
            try:
                from modules.network_map_cache import save_render_cache
                save_render_cache(
                    devices=devices, gateway_ip=gateway_ip, gateway_mac=gateway_mac,
                    modem_data=modem_data, edges=edges,
                )
            except Exception:
                log.debug("network_map_page: render cache save failed", exc_info=True)

    def render_from_cache(self, devices: List[Any], store=None) -> None:
        """Render the last-known topology at startup without a live scan.

        Uses the most recent topology snapshot from MetricStore to infer the
        gateway IP (source with the most edges = gateway).  Falls back to a
        gateway-less render when no snapshot exists.  The stale label in the
        toolbar is shown until a live scan calls render().
        """
        gateway_ip: Optional[str] = None
        if store is not None:
            try:
                from modules.topology_snapshot import load_last_snapshot as _load_snap
                from collections import Counter
                snap = _load_snap(store)
                if snap and snap.edges:
                    src_counts: Counter = Counter(e[0] for e in snap.edges)
                    gateway_ip = src_counts.most_common(1)[0][0] if src_counts else None
            except Exception:
                pass  # non-fatal — render without gateway

        self.render(devices=devices, gateway_ip=gateway_ip, persist_cache=False)

        # Mark the map as stale (live scan will clear this via render())
        if hasattr(self, "_stale_label"):
            self._stale_label.setVisible(True)

    def _compute_geo_positions(self, mode: str) -> Dict[str, Any]:
        """Compute deterministic pixel positions for a geometric layout mode.

        Returns a NodePosition dict (normalised 0-1 coords) ready to pass as
        the ``positions`` argument to build_cytoscape_html().
        """
        from modules.topology_cytoscape import build_cytoscape_elements  # noqa: PLC0415
        from modules.topology_layouts import compute_geometric_positions  # noqa: PLC0415

        kw = self._last_render_kwargs
        result = build_cytoscape_elements(
            devices=kw.get("devices", []),
            gateway_ip=kw.get("gateway_ip"),
            gateway_mac=kw.get("gateway_mac"),
            mesh_units=kw.get("mesh_units"),
            mesh_enrichment=kw.get("mesh_enrichment"),
            modem_data=kw.get("modem_data"),
        )
        pixel_positions = compute_geometric_positions(mode, result["elements"])
        # topology_cytoscape._scale_pos() maps NodePosition 0-1 → pixels.
        # We reverse: pixels → 0-1 to produce NodePosition objects.
        return {
            nid: NodePosition(
                node_id=nid,
                x=pos["x"] / 1400.0,
                y=pos["y"] / 900.0,
                pinned=False,
            )
            for nid, pos in pixel_positions.items()
        }

    def _apply_geometric_layout(self, mode: str) -> None:
        """Compute positions in Python and push them live to the Cytoscape view."""
        if not self._last_render_kwargs:
            return
        try:
            from modules.topology_cytoscape import build_cytoscape_elements  # noqa: PLC0415
            from modules.topology_layouts import compute_geometric_positions  # noqa: PLC0415

            kw     = self._last_render_kwargs
            result = build_cytoscape_elements(
                devices=kw.get("devices", []),
                gateway_ip=kw.get("gateway_ip"),
                gateway_mac=kw.get("gateway_mac"),
                mesh_units=kw.get("mesh_units"),
                mesh_enrichment=kw.get("mesh_enrichment"),
                modem_data=kw.get("modem_data"),
            )
            pos_map = compute_geometric_positions(mode, result["elements"])
            self._run_js(
                f"window.setPresetPositions && "
                f"window.setPresetPositions({json.dumps(pos_map)});"
            )
        except Exception:
            log.debug("network_map_page: geometric layout apply failed", exc_info=True)

    def _layout_storage_key(self, layout_mode: Optional[str] = None) -> str:
        """Composite key namespacing saved positions by layout mode.

        The 4 toolbar layouts (Hierarchy/Physics/Concentric/Grid) compute
        entirely different coordinates for the same devices, so they must not
        share one saved-positions bucket under the same scan_id — otherwise
        switching modes and restarting would apply the wrong mode's (x, y)
        values to the currently selected one.
        """
        mode = layout_mode or LAYOUT_NAMES.get(self._layout_combo.currentText(), "breadthfirst")
        return f"{self._scan_id}::{mode}"

    def _refresh_web_view(self, diff: Optional[Any] = None) -> None:
        """Load or incrementally update the Cytoscape view.

        First call: builds the full self-contained HTML and calls setHtml()
        to create the Cytoscape instance with saved positions and initial layout.

        Subsequent calls: calls window.updateTopology() via runJavaScript() so
        the live Cytoscape instance receives only the changed data — existing
        node positions are fully preserved, preventing layout drift.

        Reset Layout clears _topology_loaded so the next call forces a full
        reload with fresh positions.

        For geometric layout modes (geo_hierarchy, geo_concentric, geo_grid,
        geo_radial), positions are computed in Python and injected as preset
        coordinates so Cytoscape's physics engine is bypassed entirely. The
        computed positions are persisted via topology_layout.py and reused
        verbatim on the next full render (including across an app restart)
        as long as no node id is newly discovered — so the map looks the
        same as when the app was last closed unless a scan finds a new
        device. A node that is merely absent this render (offline device,
        not-yet-reported modem) keeps its saved position rather than being
        dropped.
        """
        if not self._web_available or self._web_view is None:
            return
        kw = self._last_render_kwargs
        if not kw:
            return

        from modules.topology_cytoscape import build_cytoscape_elements  # noqa: PLC0415

        def _node_ids(elements: list) -> set:
            return {
                el["data"]["id"] for el in elements
                if el.get("group") == "nodes" and "id" in el.get("data", {})
            }

        if not self._topology_loaded:
            # ── Full initial render ───────────────────────────────────────────
            layout_label = self._layout_combo.currentText()
            layout_mode  = LAYOUT_NAMES.get(layout_label, "breadthfirst")
            scan_id      = self._layout_storage_key(layout_mode)
            saved        = load_layout(scan_id) if scan_id else {}

            # Determine the node ids in *this* render up front. Only a node id
            # that was never seen before counts as "newly discovered" — a node
            # that is simply absent this time (e.g. a modem whose polling
            # worker hasn't reported yet, or a device that is temporarily
            # offline) keeps its last-known position rather than being treated
            # as removed. This is what makes the map look identical across an
            # app restart: at startup nothing has been "discovered", so the
            # saved layout is reused verbatim instead of recomputed.
            try:
                id_probe = build_cytoscape_elements(
                    devices=kw.get("devices", []),
                    edges=kw.get("edges"),
                    diff=diff,
                    lldp_neighbors=kw.get("lldp_neighbors"),
                    segments=kw.get("segments"),
                    gateway_ip=kw.get("gateway_ip"),
                    gateway_mac=kw.get("gateway_mac"),
                    mesh_units=kw.get("mesh_units"),
                    mesh_enrichment=kw.get("mesh_enrichment"),
                    modem_data=kw.get("modem_data"),
                    down_ips=kw.get("down_ips"),
                    new_ips=kw.get("new_ips"),
                )
                current_ids = _node_ids(id_probe["elements"])
            except Exception:
                current_ids = set()
            new_ids = current_ids - set(saved.keys())

            if layout_mode.startswith("geo_"):
                if saved and current_ids and not new_ids:
                    # Nothing new since the layout was last saved — reuse it
                    # verbatim instead of recomputing. current_ids must be
                    # non-empty here: if the id_probe build above failed,
                    # new_ids would also be empty (set() - X is always
                    # empty), which must NOT be mistaken for "no new
                    # devices" — that would silently produce an empty
                    # positions dict instead of falling back to a recompute.
                    positions_arg = {nid: saved[nid] for nid in current_ids if nid in saved}
                    layout_arg    = "preset"
                else:
                    # New node id(s) discovered (or no saved layout yet):
                    # recompute in Python and merge into the saved baseline,
                    # keeping positions for any node not present in this
                    # render so they aren't lost if they reappear later.
                    try:
                        positions_arg = self._compute_geo_positions(layout_mode)
                        layout_arg    = "preset"
                        if positions_arg:
                            merged = dict(saved)
                            merged.update(positions_arg)
                            save_layout(scan_id, merged)
                    except Exception:
                        log.debug("network_map_page: geo position compute failed", exc_info=True)
                        positions_arg = saved if saved else None
                        layout_arg    = "breadthfirst"
            else:
                positions_arg = saved if saved else None
                layout_arg    = layout_mode

            try:
                html = build_cytoscape_html(
                    devices=kw.get("devices", []),
                    edges=kw.get("edges"),
                    diff=diff,
                    lldp_neighbors=kw.get("lldp_neighbors"),
                    segments=kw.get("segments"),
                    positions=positions_arg,
                    gateway_ip=kw.get("gateway_ip"),
                    gateway_mac=kw.get("gateway_mac"),
                    mesh_units=kw.get("mesh_units"),
                    mesh_enrichment=kw.get("mesh_enrichment"),
                    modem_data=kw.get("modem_data"),
                    down_ips=kw.get("down_ips"),
                    new_ips=kw.get("new_ips"),
                    initial_layout=layout_arg,
                    bw_by_mac=self._bw_by_mac if self._traffic_overlay else None,
                )
                self._web_view.setHtml(html)
                self._topology_loaded = True
                self._known_node_ids = current_ids
            except Exception:
                log.debug("network_map_page: Cytoscape HTML build failed", exc_info=True)
        else:
            # ── Incremental update — preserves all node positions ─────────────
            try:
                elements = build_elements_for_update(
                    devices=kw.get("devices", []),
                    edges=kw.get("edges"),
                    diff=diff,
                    lldp_neighbors=kw.get("lldp_neighbors"),
                    segments=kw.get("segments"),
                    gateway_ip=kw.get("gateway_ip"),
                    gateway_mac=kw.get("gateway_mac"),
                    mesh_units=kw.get("mesh_units"),
                    mesh_enrichment=kw.get("mesh_enrichment"),
                    modem_data=kw.get("modem_data"),
                    down_ips=kw.get("down_ips"),
                    new_ips=kw.get("new_ips"),
                    bw_by_mac=self._bw_by_mac if self._traffic_overlay else None,
                )
                self._run_js(
                    f"window.updateTopology({json.dumps(elements)});"
                )
            except Exception:
                log.debug("network_map_page: incremental update failed", exc_info=True)
                return

            # Scan results, mesh enrichment, and LLDP neighbors each arrive via
            # separate render() calls in no guaranteed order. Whichever group
            # of nodes lands first gets the full geometric layout; whichever
            # lands later only has its node ids spiraled in around the gateway
            # by JS — never re-parented under their real structural parent
            # (mesh node, segment, etc). Detect that growth and force one
            # geometric recompute, matching what manually re-picking a layout
            # from the toolbar already does.
            new_ids = _node_ids(elements)
            grew    = bool(new_ids - self._known_node_ids)
            self._known_node_ids |= new_ids
            if grew:
                layout_label = self._layout_combo.currentText()
                mode = LAYOUT_NAMES.get(layout_label, "geo_hierarchy")
                if mode.startswith("geo_"):
                    self._cycle_geometric_layout(mode)

    def _cycle_geometric_layout(self, mode: str) -> None:
        """Apply ``mode``, but only after first applying a different geo_
        mode — i.e. automate exactly the manual "switch the Layout dropdown
        away, then back" action that reliably fixes Interactive view
        positions after a scan. A single direct reapplication of the same
        mode right after an incremental update was not enough in practice;
        only the away-then-back sequence the user performs by hand
        consistently produced a correct layout, so that is what this
        reproduces rather than a one-shot resync."""
        other_mode = next(
            (m for m in LAYOUT_NAMES.values() if m != mode and m.startswith("geo_")),
            mode,
        )
        self._apply_geometric_layout(other_mode)
        _t = QTimer(self)
        _t.setSingleShot(True)
        _t.timeout.connect(lambda: self._apply_geometric_layout(mode))
        _t.start(250)

    def update_lldp_neighbors(
        self,
        neighbors: List[Any],
        admin_needed: bool = False,
    ) -> None:
        """Re-render with updated LLDP data without requiring a full rescan."""
        if not self._last_render_kwargs:
            return
        kw = dict(self._last_render_kwargs)
        kw["lldp_neighbors"]    = neighbors
        kw["lldp_admin_needed"] = admin_needed
        self.render(**kw)

    # ── Toolbar actions ───────────────────────────────────────────────────────

    def fit_view(self) -> None:
        if self._inner_tab.currentIndex() == 0 and self._web_available:
            self._run_js("window.fitView && window.fitView();")
        else:
            self._classic_widget.fit_view()

    def _auto_fit_both_views(self) -> None:
        """Fit both views regardless of which tab is active.

        Used only for the one-time post-first-scan auto-fit: the Interactive
        view's own post-layout cy.fit() can run against a zero-size container
        if that tab isn't visible yet, so this fits it explicitly here too
        rather than depending on the active-tab check in fit_view().
        """
        self._run_js("window.fitView && window.fitView();")
        self._classic_widget.fit_view()

    def zoom_in(self) -> None:
        self._classic_widget.zoom_in()

    def zoom_out(self) -> None:
        self._classic_widget.zoom_out()

    def reset_layout(self) -> None:
        clear_layout(self._layout_storage_key())
        # Force a full setHtml() on the next render so the layout algorithm
        # runs fresh from scratch, discarding all previous node positions.
        self._topology_loaded = False
        self._known_node_ids = set()
        if self._last_render_kwargs:
            self.render(**self._last_render_kwargs)

    @pyqtSlot(str)
    def _on_layout_changed(self, label: str) -> None:
        mode = LAYOUT_NAMES.get(label, "breadthfirst")
        QSettings().setValue(_SETTINGS_KEY_LAYOUT, label)
        if self._bridge is not None:
            self._bridge.set_scan_id(self._layout_storage_key(mode))
        if not self._web_available or self._inner_tab.currentIndex() != 0:
            return
        if mode.startswith("geo_"):
            # Geometric modes: compute deterministic positions in Python and
            # push them to the live Cytoscape instance via setPresetPositions().
            self._apply_geometric_layout(mode)
        else:
            self._run_js(f"window.setLayout && window.setLayout({json.dumps(mode)});")

    @pyqtSlot(bool)
    def _on_focus_toggled(self, checked: bool) -> None:
        self._run_js(
            f"window.toggleFocus && window.toggleFocus({'true' if checked else 'false'});"
        )

    @pyqtSlot(bool)
    def _on_diff_toggled(self, checked: bool) -> None:
        self._diff_mode = checked
        # Interactive view: toggle hidden class via JS
        self._run_js(
            f"window.toggleChanges && window.toggleChanges({'true' if checked else 'false'});"
        )
        # Classic view: full re-render with/without diff
        if self._last_render_kwargs:
            kw = dict(self._last_render_kwargs)
            # The stored diff is managed by the Dashboard; we toggle here via overlay
            # JS handles interactive view; classic view re-render is below
            try:
                kw_diff = kw.get("diff") if checked else None
                self._classic_widget.render(
                    kw.get("devices", []),
                    kw.get("gateway_ip"),
                    kw.get("gateway_mac"),
                    mesh_units=kw.get("mesh_units"),
                    mesh_enrichment=kw.get("mesh_enrichment"),
                    modem_data=kw.get("modem_data"),
                    segments=kw.get("segments"),
                    edges=kw.get("edges"),
                    down_ips=kw.get("down_ips"),
                    new_ips=kw.get("new_ips"),
                    diff=kw_diff,
                    lldp_neighbors=kw.get("lldp_neighbors"),
                )
            except Exception:
                pass  # non-fatal — diff overlay is best-effort

    @pyqtSlot(bool)
    def _on_lock_toggled(self, checked: bool) -> None:
        """Freeze or unfreeze all node positions in the interactive view."""
        self._run_js(
            f"window.lockLayout && window.lockLayout({'true' if checked else 'false'});"
        )

    @pyqtSlot(bool)
    def _on_traffic_toggled(self, checked: bool) -> None:
        self._traffic_overlay = checked
        self._bw_legend.setVisible(checked)
        if checked:
            if self._bw_worker is None or not self._bw_worker.isRunning():
                self._bw_worker = BandwidthOverlayWorker(interval_s=5.0, parent=self)
                self._bw_worker.snapshot_ready.connect(self._on_bw_snapshot)
                self._bw_worker.error.connect(self._on_bw_error)
                self._bw_worker.start()
        else:
            if self._bw_worker is not None and self._bw_worker.isRunning():
                self._bw_worker.stop()
                self._bw_worker = None
            self._bw_by_mac.clear()
            if self._last_render_kwargs:
                self._refresh_web_view(
                    diff=self._last_render_kwargs.get("diff") if self._diff_mode else None
                )

    @pyqtSlot(object)
    def _on_bw_snapshot(self, snapshot: object) -> None:
        """Receive a BandwidthSnapshot; update the traffic overlay."""
        try:
            self._bw_by_mac = {
                e.mac: e.total_bps
                for e in snapshot.entries  # type: ignore[union-attr]
                if e.total_bps > 0
            }
        except Exception:
            return
        if self._traffic_overlay and self._last_render_kwargs:
            self._refresh_web_view(
                diff=self._last_render_kwargs.get("diff") if self._diff_mode else None
            )

    @pyqtSlot(str)
    def _on_bw_error(self, msg: str) -> None:
        """Handle bandwidth worker errors — untoggle the button and show a hint."""
        log.warning("Traffic Overlay: %s", msg)
        self._btn_traffic.blockSignals(True)
        self._btn_traffic.setChecked(False)
        self._btn_traffic.blockSignals(False)
        self._traffic_overlay = False
        self._bw_legend.setVisible(False)
        self._bw_worker = None
        # Surface the error briefly in the LLDP hint label (already present on the page)
        self._lldp_hint_label.setText(f"Traffic Overlay unavailable: {msg.splitlines()[0]}")
        self._lldp_hint_label.setVisible(True)

    def showEvent(self, event) -> None:  # noqa: N802
        """Fit the active view each time the page becomes visible, and apply
        the traffic-overlay default on first show.

        Cytoscape viewport may be at a stale zoom/scroll position after the
        user navigates away and back; a short-delay fit snaps it to the current
        node extents without requiring a manual "Fit" press.

        Traffic overlay is defaulted to on here (not in __init__) so that
        headless tests which never call show() never spawn a Scapy sniffer
        thread (BandwidthOverlayWorker).
        """
        super().showEvent(event)
        # STARTUP-PERF: build the QWebEngineView the first time the page is
        # actually shown, not during Dashboard construction. If a scan (or the
        # startup cache-restore) already produced render data while we were
        # hidden, replay it into the freshly-built Interactive view.
        if not self._webengine_init_attempted:
            self._webengine_init_attempted = True
            self._try_init_webengine()
            if self._web_available and self._web_view is not None and self._last_render_kwargs:
                self._refresh_web_view(
                    diff=self._last_render_kwargs.get("diff") if self._diff_mode else None
                )
        # Default traffic overlay to checked on first real show — legend helps
        # users understand node colours.  _on_bw_error untoggles it gracefully
        # if Scapy or admin rights are absent.
        if not self._traffic_overlay_defaulted:
            self._traffic_overlay_defaulted = True
            self._btn_traffic.setChecked(True)
        if self._outer_stack.currentIndex() == 1 and self._topology_loaded:
            _t = QTimer(self)
            _t.setSingleShot(True)
            _t.timeout.connect(self.fit_view)
            _t.start(200)

    @pyqtSlot(int)
    def _on_view_tab_changed(self, index: int) -> None:
        QSettings().setValue(_SETTINGS_KEY_VIEW, "interactive" if index == 0 else "classic")
        # Populate the interactive view when switching to it.
        # If already loaded we still call _refresh_web_view so that any data
        # that arrived while the Classic tab was visible is applied as an
        # incremental update (positions are preserved by updateTopology).
        if index == 0 and self._web_available and self._last_render_kwargs:
            self._refresh_web_view(
                diff=self._last_render_kwargs.get("diff") if self._diff_mode else None
            )
            # Fit after switching back — the viewport may be zoomed in or
            # scrolled from the last time Interactive was active.
            if self._topology_loaded:
                _t = QTimer(self)
                _t.setSingleShot(True)
                _t.timeout.connect(self.fit_view)
                _t.start(300)

    def _on_export(self) -> None:
        """Trigger JS to capture a PNG from the Cytoscape view."""
        if self._web_available and self._inner_tab.currentIndex() == 0:
            self._run_js("window.exportPng && window.exportPng();")
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Export",
                "PNG export is only available in the Interactive view.\n"
                "Switch to the Interactive tab and try again.",
            )

    @pyqtSlot(str)
    def _on_export_data(self, data_url: str) -> None:
        """Receive base-64 PNG from JS and save it via file dialog."""
        import base64
        from PyQt6.QtWidgets import QFileDialog
        from modules.utils import get_app_data_dir

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Network Map", str(get_app_data_dir() / "network_map.png"),
            "PNG Image (*.png)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            header, b64 = data_url.split(",", 1)
            img_bytes = base64.b64decode(b64)
            with open(path, "wb") as fh:
                fh.write(img_bytes)
            from ui.widgets.toast import ToastManager
            ToastManager.instance().show_toast(f"Map exported to {path}", "info")
        except Exception as exc:
            log.warning("network_map_page: export failed: %s", exc)

    def _on_share_export(self) -> None:
        """Export a sanitized PNG (private IPs aliased, MACs/hostnames stripped,
        public IPs omitted) — safe to post publicly. Renders independently of
        the on-screen view via modules/topology_share.py."""
        from PyQt6.QtWidgets import QFileDialog
        from modules.utils import get_app_data_dir
        from modules.topology_share import render_sanitized_topology_png
        from ui.widgets.toast import ToastManager

        kwargs = self._last_render_kwargs or {}
        path, _ = QFileDialog.getSaveFileName(
            self, "Share Network Map", str(get_app_data_dir() / "network_map_share.png"),
            "PNG Image (*.png)",
            options=QFileDialog.Option.DontUseNativeDialog,
        )
        if not path:
            return
        try:
            render_sanitized_topology_png(
                kwargs.get("devices") or [],
                gateway_ip=kwargs.get("gateway_ip"),
                gateway_mac=kwargs.get("gateway_mac"),
                edges=kwargs.get("edges") or [],
                output_path=path,
            )
            ToastManager.show(f"Sanitized map exported to {path}", "success")
        except Exception as exc:
            log.warning("network_map_page: sanitized share export failed: %s", exc)
            ToastManager.show(f"Export failed: {exc}", "error")

    def _run_js(self, script: str) -> None:
        """Run a JavaScript snippet in the web view if available."""
        if self._web_available and self._web_view is not None:
            try:
                self._web_view.page().runJavaScript(script)
            except Exception:
                pass  # non-fatal — JS call may fail if page not loaded

    # ── Convenience properties for backward compatibility ─────────────────────

    @property
    def classic_widget(self) -> TopologyWidget:
        return self._classic_widget

    @property
    def btn_diff(self) -> QPushButton:
        return self._btn_diff

    @property
    def diff_label(self) -> QLabel:
        return self._diff_label

    @property
    def _topology_widget(self) -> TopologyWidget:
        """Legacy alias so existing code using self._topology_widget still works."""
        return self._classic_widget
