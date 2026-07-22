r"""
Network topology graph widget.

Flat star (no mesh data):
  [Internet] ── [Gateway] ── [Device …]

Three-tier mesh (when Deco data is present):
  [Internet]
      │
  [Gateway / master node]
   /     │      \
[Sat1] [Sat2] [Sat3]   ← mesh satellites (blue hexagons)
 /│\    │      │\
…  …    …      …       ← client devices grouped under their satellite

Devices not in Deco data attach directly to the gateway (dashed edge).
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QMenu, QSizePolicy, QWidget, QVBoxLayout

from ui import styles as _s
from modules.topology_layout import (
    NodePosition, TopologyEdge, clear_layout, compute_scan_id, load_layout, save_layout,
)


def _risk_node_color(risk: str) -> str:
    """Node fill for a device risk level — read live so a theme switch recolours."""
    return {
        "HIGH":    _s.RED,
        "MEDIUM":  _s.AMBER,
        "LOW":     _s.BLUE,
        "CLEAN":   _s.GREEN,
        "UNKNOWN": _s.TEXT_MUTED,
    }.get(risk, _s.TEXT_MUTED)


# Semantic node-colour roles — thin live accessors over ui.styles tokens so an
# Arctic <-> Midnight switch recolours the map on the next render.
def _gateway_color() -> str:   return _s.ACCENT
def _internet_color() -> str:  return _s.ACCENT
def _mesh_sat_color() -> str:  return _s.CHART_PURPLE   # distinct from all risk colours
def _modem_color() -> str:     return _s.GREEN          # WAN modem node
def _lldp_node_color() -> str: return _s.TEAL           # LLDP infrastructure nodes

_PIN_LINEWIDTH = 3.0    # border width for pinned nodes
_SEG_LINEWIDTH = 2.0    # border width when a segment colour is applied
_DEF_LINEWIDTH = 1.5    # default border width


class TopologyWidget(QWidget):
    """Matplotlib-based network topology graph embedded in PyQt6."""

    node_clicked = pyqtSignal(str)  # emits device IP on node click

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._fig    = Figure(figsize=(8, 5), dpi=96, facecolor=_s.BG_DARK)
        self._ax     = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        _s.themed_ss(self._canvas, "background:{BG_DARK}; border:none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self._style_axes()

        self._pos_map: dict = {}       # node_key → (x, y) data coords
        self._ip_map: dict = {}        # node_key → device IP string
        self._tooltip_map: dict = {}   # node_key → tooltip text (hostname/IP/risk)
        self._parent_pos: dict = {}    # node_key → (x, y) of the node's immediate
                                        # parent in the drawn tree (gateway for flat
                                        # layout / direct devices, satellite for mesh
                                        # clients) — health overlay edges must follow
                                        # this same parent, not always the gateway
        self._hover_ann = None

        # Sprint 2 — layout persistence
        self._scan_id: str = "default"
        self._pinned: set[str] = set()       # node_keys the user has pinned
        self._segments: list = []            # list[NetworkSegment] for border colours
        self._last_render_kwargs: dict = {}  # cached args for reset_layout()

        # Sprint 3 — edge health overlays
        self._gw_pos: Optional[tuple] = None  # gateway (x, y) for health overlay lines

        # Sprint 4 — diff overlay: cache prev render positions for ghost nodes
        self._prev_pos_map: dict = {}   # node positions from the previous render call
        self._prev_ip_map:  dict = {}   # node IPs from the previous render call

        # Sprint 5 — LLDP overlay
        self._lldp_neighbors: list = []  # list[LldpNeighbor] from last render

        self._canvas.mpl_connect("button_press_event",  self._on_button_press)
        self._canvas.mpl_connect("motion_notify_event", self._on_motion)

    def _style_axes(self) -> None:
        ax = self._ax
        ax.set_facecolor(_s.BG_CARD)
        ax.axis("off")
        # Small fixed margins so nodes and labels near the canvas edge aren't clipped.
        # Do NOT call tight_layout after this — it fights these values.
        self._fig.subplots_adjust(left=0.01, right=0.99, top=0.96, bottom=0.04)

    # ── public API ────────────────────────────────────────────────────────────

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
        diff: Optional[Any] = None,         # TopologyDiff | None
        lldp_neighbors: Optional[List[Any]] = None,  # list[LldpNeighbor] | None
        lldp_admin_needed: bool = False,    # show "run as admin" info banner
    ) -> None:
        # Cache args so reset_layout() can replay the last render.
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
        self._lldp_neighbors = lldp_neighbors or []
        # Sprint 4 — save previous positions before clearing so ghost nodes
        # have coordinates during diff overlay rendering.
        self._prev_pos_map = dict(self._pos_map)
        self._prev_ip_map  = dict(self._ip_map)
        self._segments = segments or []
        self._pos_map = {}
        self._ip_map = {}
        self._tooltip_map = {}
        self._parent_pos = {}
        self._hover_ann = None
        ax = self._ax
        ax.cla()
        self._style_axes()

        # Strip noise IPs before layout: multicast (224–239.x.x.x), broadcast,
        # and unresolved addresses add clutter without meaning on the map.
        devices = [d for d in devices if not _is_noise_ip(_attr(d, "ip", ""))]

        if not devices:
            ax.text(0.5, 0.5, "No devices to display.\nRun a scan first.",
                    ha="center", va="center", color=_s.TEXT_MUTED,
                    fontsize=13, transform=ax.transAxes)
            self._canvas.draw()
            return

        # Compute scan signature and load any saved positions.
        self._scan_id = compute_scan_id(devices)
        saved = load_layout(self._scan_id)
        # Rebuild pinned set from saved layout (covers nodes from this scan_id only).
        self._pinned = {k for k, v in saved.items() if v.pinned}

        if mesh_units:
            # mesh_enrichment may be {} when devices carry d.mesh_unit already
            # (set by _apply_mesh_enrichment); pass {} not None to avoid AttributeError
            self._render_mesh(ax, devices, gateway_ip, mesh_units, mesh_enrichment or {},
                              modem_data=modem_data, saved=saved)
        else:
            self._render_flat(ax, devices, gateway_ip, gateway_mac,
                              modem_data=modem_data, saved=saved)

        # Save current positions now that they've been finalised.
        self._save_current_positions()

        # Sprint 3 — edge health overlays and node status dots
        if edges or down_ips or new_ips:
            self._draw_health_overlays(
                ax,
                edges or [],
                down_ips or set(),
                new_ips or set(),
            )

        # Sprint 4 — topology diff overlay (added/removed nodes and edges)
        if diff is not None and not diff.is_empty:
            self._draw_diff_overlays(ax, diff)

        # Sprint 5 — LLDP neighbor overlay
        if lldp_neighbors:
            self._draw_lldp_overlays(ax, lldp_neighbors)
        elif lldp_admin_needed:
            ax.text(
                0.5, 0.01,
                "⬡  Run as administrator to discover managed switch topology via LLDP",
                ha="center", va="bottom", fontsize=8,
                color=_s.TEAL, transform=ax.transAxes, alpha=0.80,
            )

        # Extend y-axis below 0 so labels placed at (y - 0.07) near the bottom
        # are never clipped by the axes patch boundary.
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.12, 1.02)
        self._canvas.draw()
        if self._pos_map:
            self._hover_ann = self._ax.annotate(
                "", xy=(0.5, 0.5), xytext=(0, 14),
                textcoords="offset points",
                ha="center", va="bottom", fontsize=8, zorder=6,
                color=_s.TEXT_PRIMARY,
                bbox=dict(boxstyle="round,pad=0.3", fc=_s.BG_CARD, ec=_s.CHART_SPINE, alpha=0.95),
            )
            self._hover_ann.set_visible(False)

    def clear(self) -> None:
        self._pos_map = {}
        self._ip_map = {}
        self._tooltip_map = {}
        self._hover_ann = None
        self._ax.cla()
        self._style_axes()
        self._canvas.draw()

    def refresh_theme(self) -> None:
        """Re-read theme colours and repaint after a live theme switch.

        The canvas widget background re-applies automatically (themed_ss
        registry).  All node/edge/legend colours are read live at draw time, so
        replaying the last render restyles the whole map; if nothing has been
        rendered yet we just restyle the empty axes.
        """
        self._fig.set_facecolor(_s.BG_DARK)
        if self._last_render_kwargs:
            self.render(**self._last_render_kwargs)
        else:
            self._ax.cla()
            self._style_axes()
            self._canvas.draw_idle()

    # ── toolbar actions ───────────────────────────────────────────────────────

    def fit_view(self) -> None:
        """Fit topology to the visible axes bounds."""
        self._ax.autoscale()
        self._canvas.draw()

    def zoom_in(self) -> None:
        """Zoom in 20% on both axes."""
        self._zoom(0.8)

    def zoom_out(self) -> None:
        """Zoom out 20% on both axes."""
        self._zoom(1.25)

    def reset_layout(self) -> None:
        """Clear saved positions for the current scan and re-render."""
        clear_layout(self._scan_id)
        self._pinned.clear()
        if self._last_render_kwargs:
            self.render(**self._last_render_kwargs)

    def _zoom(self, factor: float) -> None:
        ax = self._ax
        xl = ax.get_xlim()
        yl = ax.get_ylim()
        xc = (xl[0] + xl[1]) / 2
        yc = (yl[0] + yl[1]) / 2
        xh = (xl[1] - xl[0]) / 2 * factor
        yh = (yl[1] - yl[0]) / 2 * factor
        ax.set_xlim(xc - xh, xc + xh)
        ax.set_ylim(yc - yh, yc + yh)
        self._canvas.draw()

    # ── layout persistence helpers ────────────────────────────────────────────

    def _save_current_positions(self) -> None:
        """Persist _pos_map (device nodes only) to the layout file."""
        if not self._pos_map:
            return
        positions: Dict[str, NodePosition] = {}
        for nk, (x, y) in self._pos_map.items():
            positions[nk] = NodePosition(
                node_id=nk,
                x=x,
                y=y,
                pinned=(nk in self._pinned),
            )
        save_layout(self._scan_id, positions)

    def _apply_saved_positions(
        self, positions: dict, saved: Dict[str, NodePosition]
    ) -> None:
        """Override computed positions with saved pinned-node positions."""
        for nk, np in saved.items():
            if np.pinned and nk in positions:
                positions[nk] = (np.x, np.y)

    def _segment_edge_color(self, ip: str) -> tuple[str, float]:
        """Return (edge_hex_colour, linewidth) for a device node at *ip*."""
        if not self._segments or not ip:
            return _s.BG_CARD, _DEF_LINEWIDTH
        try:
            from modules.network_segments import classify_device_segment
            seg = classify_device_segment(ip, self._segments)
            if seg:
                lw = _PIN_LINEWIDTH if (
                    # use the node_key — try both mac and ip variants
                    ip in self._pinned
                ) else _SEG_LINEWIDTH
                return seg.color, lw
        except Exception:
            pass  # non-fatal — fall back to default
        return _s.BG_CARD, _DEF_LINEWIDTH

    # ── flat star layout ──────────────────────────────────────────────────────

    def _render_flat(self, ax, devices, gateway_ip, gateway_mac,
                     modem_data=None, saved=None) -> None:
        if saved is None:
            saved = {}

        nodes: List[dict] = [
            {"id": "internet", "label": "☁  Internet", "color": _internet_color(), "size": 1200},
            {"id": "gateway",  "label": f"Gateway\n{gateway_ip or '?'}", "color": _gateway_color(), "size": 1000},
        ]
        for d in devices:
            ip    = _attr(d, "ip",         "?")
            host  = _attr(d, "hostname",   "") or _attr(d, "vendor", "") or "Device"
            risk  = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
            mac   = _attr(d, "mac",        "")
            nodes.append({
                "id":    mac or ip,
                "label": f"{host[:14]}\n{ip}",
                "color": _risk_node_color(risk),
                "size":  700,
                "ip":    ip,
            })

        n = len(nodes) - 2
        has_modem = bool(modem_data)
        y_internet = 0.92
        y_modem    = 0.76
        y_gateway  = 0.58 if has_modem else 0.60
        positions: Dict[str, tuple] = {
            "internet": (0.5, y_internet),
            "gateway":  (0.5, y_gateway),
        }
        self._gw_pos = (0.5, y_gateway)  # Sprint 3 — used by health overlays
        if has_modem:
            positions["__modem__"] = (0.5, y_modem)

        for i, node in enumerate(nodes[2:]):
            angle  = math.pi + (i / max(n, 1)) * 2 * math.pi
            radius = 0.32 * (1 + 0.3 * (n > 8))
            positions[node["id"]] = (
                0.5  + radius * math.cos(angle),
                0.26 + radius * 0.6 * math.sin(angle),
            )

        # Apply pinned saved positions before populating _pos_map
        self._apply_saved_positions(positions, saved)

        # Populate interactive node maps for click/hover
        for d, node in zip(devices, nodes[2:]):
            nk  = node["id"]
            ip  = _attr(d, "ip", "?")
            if ip and ip != "?" and nk in positions:
                host = _attr(d, "hostname", "") or _attr(d, "vendor", "") or "Device"
                risk = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
                self._pos_map[nk] = positions[nk]
                self._ip_map[nk] = ip
                self._tooltip_map[nk] = f"{host[:20]}\n{ip}\nRisk: {risk}"
                self._parent_pos[nk] = positions["gateway"]

        gx, gy = positions["gateway"]
        ix, iy = positions["internet"]

        if has_modem:
            mx, my = positions["__modem__"]
            ax.plot([ix, mx], [iy, my], color=_s.CHART_SPINE, linewidth=1.5, zorder=1)
            ax.plot([mx, gx], [my, gy], color=_s.CHART_SPINE, linewidth=1.5, zorder=1)
        else:
            ax.plot([ix, gx], [iy, gy], color=_s.CHART_SPINE, linewidth=1.5, zorder=1)

        for node in nodes[2:]:
            nx, ny = positions[node["id"]]
            ax.plot([gx, nx], [gy, ny], color=_s.CHART_SPINE, linewidth=1.0, zorder=1)

        # Draw infrastructure nodes (no segment colouring)
        for node in nodes[:2]:
            _scatter(ax, positions[node["id"]], node["color"], node["size"],
                     node["label"], edge_color=_s.BG_CARD, linewidth=_DEF_LINEWIDTH)

        if has_modem:
            _scatter(ax, positions["__modem__"], _modem_color(), 900,
                     _modem_label(modem_data), edge_color=_s.BG_CARD, linewidth=_DEF_LINEWIDTH)

        # Draw device nodes with segment edge colours
        for d, node in zip(devices, nodes[2:]):
            ip = node.get("ip", _attr(d, "ip", "?"))
            nk = node["id"]
            ec, lw = self._segment_edge_color(ip)
            # Pinned nodes get thicker border regardless of segment colour
            if nk in self._pinned:
                lw = _PIN_LINEWIDTH
                ec = ec if ec != _s.BG_CARD else _s.ACCENT
            _scatter(ax, positions[node["id"]], node["color"], node["size"],
                     node["label"], edge_color=ec, linewidth=lw)

        self._legend(ax, mesh=False, modem=has_modem)
        ax.set_title("Network Topology", color=_s.CHART_TITLE, fontsize=11, fontweight="bold", pad=4)

    # ── mesh 3-tier layout ────────────────────────────────────────────────────

    def _render_mesh(self, ax, devices, gateway_ip, mesh_units, mesh_enrichment,
                     modem_data=None, saved=None) -> None:
        if saved is None:
            saved = {}

        try:
            from modules.deco_client import _norm_mac
        except ImportError:
            def _norm_mac(m: str) -> str:
                return m.lower().replace("-", ":").strip()

        master     = next((u for u in mesh_units if getattr(u, "role", "") == "master"), None)
        satellites = [u for u in mesh_units if getattr(u, "role", "") != "master"]

        infra_macs: set[str] = set()
        for unit in mesh_units:
            m = _norm_mac(getattr(unit, "mac", "") or "")
            if m:
                infra_macs.add(m)
        infra_ips: set[str] = {gateway_ip} if gateway_ip else set()

        known_unit_names = {getattr(u, "name", "") for u in satellites}
        by_unit: Dict[str, list] = defaultdict(list)
        unassigned: list = []
        for d in devices:
            if _norm_mac(_attr(d, "mac", "") or "") in infra_macs:
                continue
            if (_attr(d, "ip", "") or "") in infra_ips:
                continue
            # Prefer d.mesh_unit (pre-computed by _apply_mesh_enrichment so it
            # matches the Devices table) and fall back to a live lookup.
            _munit = _attr(d, "mesh_unit", "") or ""
            if not _munit:
                mac = _norm_mac(_attr(d, "mac", ""))
                mc  = mesh_enrichment.get(mac)
                if mc:
                    _munit = mc.unit_name
            if _munit and _munit in known_unit_names:
                by_unit[_munit].append(d)
            else:
                unassigned.append(d)

        covered_macs = {_norm_mac(_attr(d, "mac", "") or "") for d in devices}
        for mc in mesh_enrichment.values():
            mc_mac = _norm_mac(mc.mac)
            if mc_mac in covered_macs or mc_mac in infra_macs:
                continue
            stub = {
                "mac":        mc.mac,
                "ip":         mc.ip or "",
                "hostname":   mc.name,
                "risk_level": "CLEAN",
            }
            if mc.unit_name in known_unit_names:
                by_unit[mc.unit_name].append(stub)
            else:
                unassigned.append(stub)

        has_modem   = bool(modem_data)
        Y_INTERNET  = 0.91
        Y_MODEM     = 0.80
        Y_GATEWAY   = 0.68 if has_modem else 0.73
        Y_UNASSIGNED = 0.56
        Y_SATELLITE  = 0.42
        Y_CLIENT     = 0.16

        n_sats = len(satellites)
        X_L, X_R = 0.13, 0.87

        pos: Dict[str, tuple] = {
            "__internet__": (0.5, Y_INTERNET),
            "__gateway__":  (0.5, Y_GATEWAY),
        }
        self._gw_pos = (0.5, Y_GATEWAY)  # Sprint 3 — used by health overlays
        if has_modem:
            pos["__modem__"] = (0.5, Y_MODEM)

        for i, unit in enumerate(satellites):
            if n_sats == 1:
                sx = 0.5
            else:
                sx = X_L + i * (X_R - X_L) / (n_sats - 1)
            pos[unit.mac] = (sx, Y_SATELLITE)

        if n_sats > 1:
            sat_gap   = (X_R - X_L) / (n_sats - 1)
            max_half  = sat_gap * 0.42
        else:
            max_half  = 0.30

        for unit in satellites:
            sx, _ = pos[unit.mac]
            clients = by_unit.get(unit.name, [])
            nc      = len(clients)
            half    = min(max_half, max(0.04, nc * 0.045))
            for j, d in enumerate(clients):
                cx = sx if nc == 1 else sx - half + j * 2 * half / (nc - 1)
                pos[_dev_id(d)] = (cx, Y_CLIENT)

        nu = len(unassigned)
        u_half = min(0.22, max(0.04, nu * 0.055))
        for j, d in enumerate(unassigned):
            cx = 0.5 if nu == 1 else 0.5 - u_half + j * 2 * u_half / (nu - 1)
            pos[_dev_id(d)] = (cx, Y_UNASSIGNED)

        # Apply pinned saved positions before populating _pos_map
        self._apply_saved_positions(pos, saved)

        # Populate interactive node maps for click/hover
        for unit in satellites:
            for d in by_unit.get(unit.name, []):
                did = _dev_id(d)
                ip  = _attr(d, "ip", "") or ""
                if ip and did in pos:
                    host = _attr(d, "hostname", "") or _attr(d, "vendor", "") or "Device"
                    risk = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
                    self._pos_map[did] = pos[did]
                    self._ip_map[did] = ip
                    self._tooltip_map[did] = f"{host[:20]}\n{ip}\nRisk: {risk}"
                    # Client's drawn parent is its satellite, not the gateway —
                    # health overlay edges must originate there (see _draw_health_overlays).
                    self._parent_pos[did] = pos[unit.mac]
        for d in unassigned:
            did = _dev_id(d)
            ip  = _attr(d, "ip", "") or ""
            if ip and did in pos:
                host = _attr(d, "hostname", "") or _attr(d, "vendor", "") or "Device"
                risk = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
                self._pos_map[did] = pos[did]
                self._ip_map[did] = ip
                self._tooltip_map[did] = f"{host[:20]}\n{ip}\nRisk: {risk}"
                self._parent_pos[did] = pos["__gateway__"]

        # ── Draw all edges first (zorder=1) so nodes paint over them ─────────
        gx, gy = pos["__gateway__"]
        ix, iy = pos["__internet__"]
        if has_modem:
            mx, my = pos["__modem__"]
            ax.plot([ix, mx], [iy, my], color=_s.CHART_SPINE, linewidth=2.0, zorder=1)
            ax.plot([mx, gx], [my, gy], color=_s.CHART_SPINE, linewidth=2.0, zorder=1)
        else:
            ax.plot([ix, gx], [iy, gy], color=_s.CHART_SPINE, linewidth=2.0, zorder=1)

        for unit in satellites:
            sx, sy = pos[unit.mac]
            ax.plot([gx, sx], [gy, sy], color=_s.CHART_SPINE, linewidth=1.4, zorder=1)
            for d in by_unit.get(unit.name, []):
                did = _dev_id(d)
                if did in pos:
                    cx, cy = pos[did]
                    ax.plot([sx, cx], [sy, cy], color=_s.CHART_SPINE, linewidth=0.7, zorder=1)

        for d in unassigned:
            did = _dev_id(d)
            if did in pos:
                cx, cy = pos[did]
                ax.plot([gx, cx], [gy, cy], color=_s.CHART_SPINE, linewidth=0.7,
                        linestyle="--", alpha=0.55, zorder=1)

        # ── Draw infrastructure nodes ─────────────────────────────────────────
        _scatter(ax, pos["__internet__"], _internet_color(), 1200, "☁  Internet",
                 edge_color=_s.BG_CARD, linewidth=_DEF_LINEWIDTH)
        if has_modem:
            _scatter(ax, pos["__modem__"], _modem_color(), 900, _modem_label(modem_data),
                     edge_color=_s.BG_CARD, linewidth=_DEF_LINEWIDTH)

        gw_name  = master.name if master else "Gateway"
        gw_label = f"{gw_name}\n{gateway_ip or ''}"
        _scatter(ax, pos["__gateway__"], _gateway_color(), 1000, gw_label,
                 edge_color=_s.BG_CARD, linewidth=_DEF_LINEWIDTH)

        for unit in satellites:
            nc    = len(by_unit.get(unit.name, []))
            label = f"⬡  {unit.name}\n{nc} client{'s' if nc != 1 else ''}"
            _scatter(ax, pos[unit.mac], _mesh_sat_color(), 900, label,
                     edge_color=_s.BG_CARD, linewidth=_DEF_LINEWIDTH)

        # ── Draw device nodes with segment edge colours ───────────────────────
        def _draw_device_seg(d: Any) -> None:
            dev_id = _dev_id(d)
            if dev_id not in pos:
                return
            ip    = _attr(d, "ip",         "?")
            host  = _attr(d, "hostname",   "") or _attr(d, "vendor", "") or "Device"
            risk  = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
            color = _risk_node_color(risk)
            ec, lw = self._segment_edge_color(ip)
            if dev_id in self._pinned:
                lw = _PIN_LINEWIDTH
                ec = ec if ec != _s.BG_CARD else _s.ACCENT
            _scatter(ax, pos[dev_id], color, 600, f"{host[:13]}\n{ip}",
                     edge_color=ec, linewidth=lw)

        for unit in satellites:
            for d in by_unit.get(unit.name, []):
                _draw_device_seg(d)
        for d in unassigned:
            _draw_device_seg(d)

        self._legend(ax, mesh=True, modem=has_modem)
        ax.set_title("Network Topology — Mesh", color=_s.CHART_TITLE,
                     fontsize=11, fontweight="bold", pad=4)

    # ── Sprint 3: edge health overlays + node status dots ─────────────────────

    def _edge_health_style(self, edge: TopologyEdge) -> tuple:
        """Return (colour, linewidth) for a health-coloured edge."""
        bw = edge.bandwidth_mbps
        if bw is not None:
            lw = max(0.8, min(3.0, bw / 100.0 * 3.0))
        else:
            lw = 1.4
        if edge.status == "down":
            return _s.RED, max(lw, 1.8)
        if edge.status == "degraded":
            return _s.AMBER, max(lw, 1.4)
        if edge.status == "up":
            return _s.GREEN, lw
        return _s.CHART_SPINE, 1.0  # unknown — let the base grey line show through

    def _draw_health_overlays(
        self,
        ax,
        edges: List[TopologyEdge],
        down_ips: set,
        new_ips: set,
    ) -> None:
        """Draw coloured edge lines and node status dots after the base layout."""
        import matplotlib.patches as _mp

        gw_pos = self._gw_pos

        # ── Edge health lines ──────────────────────────────────────────────
        # Each overlay line must follow the same parent the base grey tree line
        # uses (gateway for flat/unassigned devices, satellite for mesh clients).
        # Edges are always recorded gateway→device by the scan pipeline, but in
        # mesh mode most devices are visually parented to a satellite — drawing
        # every overlay line from the gateway produced spurious criss-crossing
        # lines straight through the satellite nodes.
        if edges and gw_pos:
            edge_by_dst = {e.dst_ip: e for e in edges}
            for nk, (nx, ny) in self._pos_map.items():
                ip = self._ip_map.get(nk, "")
                if not ip or ip not in edge_by_dst:
                    continue
                edge = edge_by_dst[ip]
                if edge.status == "unknown":
                    continue  # grey base line already conveys unknown state
                px, py = self._parent_pos.get(nk, gw_pos)
                color, lw = self._edge_health_style(edge)
                ax.plot([px, nx], [py, ny], color=color, linewidth=lw,
                        zorder=2, alpha=0.85, solid_capstyle="round")
                if edge.latency_ms is not None:
                    mx, my = (px + nx) / 2, (py + ny) / 2
                    ax.annotate(
                        f"{edge.latency_ms:.0f} ms",
                        xy=(mx, my), fontsize=7, ha="center", va="center",
                        zorder=5, color=_s.TEXT_PRIMARY,
                        bbox=dict(boxstyle="round,pad=0.15", fc=_s.BG_CARD,
                                  ec=_s.CHART_SPINE, alpha=0.92, linewidth=0.8),
                    )

        # ── Node status dots ───────────────────────────────────────────────
        for nk, (nx, ny) in self._pos_map.items():
            ip = self._ip_map.get(nk, "")
            if ip in down_ips:
                ax.scatter(nx, ny, s=65, c=_s.RED, zorder=5,
                           marker="o", edgecolors=_s.BG_CARD, linewidths=1.5)
            if ip in new_ips:
                ring = _mp.Circle(
                    (nx, ny), radius=0.036, fill=False,
                    edgecolor=_s.BLUE, linewidth=2.2, alpha=0.45, zorder=5,
                )
                ax.add_patch(ring)

    # ── Sprint 4: topology diff overlay ──────────────────────────────────────

    def _draw_diff_overlays(self, ax, diff: Any) -> None:
        """Draw added/removed node badges and ghost edges on top of the base layout."""
        import matplotlib.patches as _mp
        from matplotlib.lines import Line2D as _L2D

        # Build reverse lookups
        ip_to_nk      = {ip: nk for nk, ip in self._ip_map.items()}
        prev_ip_to_nk = {ip: nk for nk, ip in self._prev_ip_map.items()}

        # ── Added nodes — cyan "+" badge centred on the node ──────────────
        for ip in diff.added_ips:
            nk = ip_to_nk.get(ip)
            if nk and nk in self._pos_map:
                nx, ny = self._pos_map[nk]
                ax.annotate(
                    "+",
                    xy=(nx, ny),
                    ha="center", va="center",
                    fontsize=9, fontweight="bold",
                    color=_s.BG_CARD, zorder=7,
                    bbox=dict(
                        boxstyle="circle,pad=0.3",
                        fc=_s.TEAL, ec=_s.TEAL, linewidth=0,
                    ),
                )

        # ── Removed nodes — faded ghost circle at previous position ───────
        for ip in diff.removed_ips:
            nk = prev_ip_to_nk.get(ip)
            if nk and nk in self._prev_pos_map:
                gx, gy = self._prev_pos_map[nk]
                ghost = _mp.Circle(
                    (gx, gy), radius=0.034,
                    fill=True,
                    facecolor=_s.TEXT_MUTED, edgecolor=_s.TEXT_MUTED,
                    linewidth=1.5, linestyle="--",
                    alpha=0.25, zorder=3,
                )
                ax.add_patch(ghost)
                ax.annotate(
                    f"gone\n{ip}",
                    xy=(gx, gy), xytext=(0, -18),
                    textcoords="offset points",
                    ha="center", va="top",
                    fontsize=7, color=_s.TEXT_MUTED,
                    alpha=0.55, zorder=4,
                )

        gw_pos = self._gw_pos

        # ── New edges — GREEN dashed line ─────────────────────────────────
        if gw_pos:
            for src_ip, dst_ip in diff.added_edges:
                nk = ip_to_nk.get(dst_ip)
                if nk and nk in self._pos_map:
                    gx, gy = gw_pos
                    nx, ny = self._pos_map[nk]
                    ax.plot([gx, nx], [gy, ny],
                            color=_s.GREEN, linewidth=1.8,
                            linestyle="--", alpha=0.75, zorder=2)

        # ── Removed edges — RED dotted line at previous positions ─────────
        if gw_pos and self._prev_pos_map:
            for src_ip, dst_ip in diff.removed_edges:
                nk = prev_ip_to_nk.get(dst_ip)
                if nk and nk in self._prev_pos_map:
                    gx, gy = gw_pos
                    nx, ny = self._prev_pos_map[nk]
                    ax.plot([gx, nx], [gy, ny],
                            color=_s.RED, linewidth=1.8,
                            linestyle=":", alpha=0.5, zorder=2)

        # ── Diff legend (upper-left, alongside the existing risk legend) ──
        legend_items = []
        if diff.added_ips:
            legend_items.append(
                _L2D([0], [0], marker="o", color=_s.TEXT_SECONDARY,
                     markerfacecolor=_s.TEAL, markersize=8, label="New device")
            )
        if diff.removed_ips:
            legend_items.append(
                _L2D([0], [0], marker="o", color=_s.TEXT_SECONDARY,
                     markerfacecolor=_s.TEXT_MUTED, markersize=8,
                     alpha=0.4, label="Device gone")
            )
        if diff.added_edges:
            legend_items.append(
                _L2D([0], [0], color=_s.GREEN, linewidth=2,
                     linestyle="--", label="New link")
            )
        if diff.removed_edges:
            legend_items.append(
                _L2D([0], [0], color=_s.RED, linewidth=2,
                     linestyle=":", label="Link gone")
            )
        if legend_items:
            ax.legend(
                handles=legend_items, loc="upper left", fontsize=8,
                labelcolor=_s.TEXT_SECONDARY, facecolor=_s.BG_CARD,
                edgecolor=_s.CHART_SPINE, framealpha=0.9,
                title="Changes", title_fontsize=8,
            )

    # ── Sprint 5: LLDP neighbor overlay ──────────────────────────────────────

    def update_lldp_neighbors(
        self,
        neighbors: List[Any],
        admin_needed: bool = False,
    ) -> None:
        """Re-render the topology with LLDP neighbor data added as an overlay.

        Calling this after render() overlays LLDP-discovered switches/routers
        without requiring a full re-scan.  The updated kwargs are stored in
        _last_render_kwargs so reset_layout() preserves them.
        """
        if not self._last_render_kwargs:
            return
        kw = dict(self._last_render_kwargs)
        kw["lldp_neighbors"]    = neighbors
        kw["lldp_admin_needed"] = admin_needed
        self.render(**kw)

    def _draw_lldp_overlays(self, ax, neighbors: List[Any]) -> None:
        """Draw LLDP-discovered nodes and their uplink edges onto *ax*.

        Visual rules (per Sprint 5 spec):
          • All LLDP nodes:              diamond marker ("D"), TEAL fill
          • Infrastructure nodes         (bridge / router capability):
                                         square marker ("s"), TEAL fill
          • Gateway → LLDP edge:         solid, linewidth=2.5, TEAL
          • ARP leaf edges:              dashed, linewidth=1.0, BORDER (unchanged)
        """
        from matplotlib.lines import Line2D as _L2D

        if not neighbors or self._gw_pos is None:
            return

        gx, gy = self._gw_pos
        # Spread LLDP nodes just above the device row (y ≈ 0.44)
        n_lldp   = len(neighbors)
        lldp_y   = 0.44
        x_spread = min(0.35, 0.08 * n_lldp)

        infra_nodes = []   # (x, y, label) for square-marker nodes
        leaf_nodes  = []   # (x, y, label) for diamond-marker nodes

        for idx, nb in enumerate(neighbors):
            if n_lldp == 1:
                nx = 0.5
            else:
                nx = (0.5 - x_spread) + idx * (2 * x_spread / (n_lldp - 1))
            ny = lldp_y

            # Edge: gateway → LLDP node
            ax.plot(
                [gx, nx], [gy, ny],
                color=_lldp_node_color(), linewidth=2.5,
                zorder=2, alpha=0.85, solid_capstyle="round",
            )

            is_infra = bool(
                {"bridge", "router"} & set(getattr(nb, "capabilities", []))
            )
            name    = (getattr(nb, "neighbor_hostname", "") or
                       getattr(nb, "chassis_id", "") or "Switch")
            chassis = getattr(nb, "chassis_id", "")
            label   = f"{name[:14]}\n{chassis[:17]}"

            if is_infra:
                infra_nodes.append((nx, ny, label))
            else:
                leaf_nodes.append((nx, ny, label))

        # Draw square-marker infrastructure nodes
        for nx, ny, label in infra_nodes:
            ax.scatter(
                nx, ny, s=700, c=_lldp_node_color(),
                marker="s", zorder=3, alpha=0.90,
                edgecolors=_s.BG_CARD, linewidths=1.5,
            )
            ax.annotate(
                label, xy=(nx, ny), xytext=(0, -18),
                textcoords="offset points",
                ha="center", va="top", fontsize=7,
                color=_s.TEXT_PRIMARY, zorder=4, clip_on=False,
                bbox=dict(boxstyle="round,pad=0.2", fc=_s.BG_CARD, ec=_s.CHART_SPINE, alpha=0.90),
            )

        # Draw diamond-marker leaf LLDP nodes
        for nx, ny, label in leaf_nodes:
            ax.scatter(
                nx, ny, s=600, c=_lldp_node_color(),
                marker="D", zorder=3, alpha=0.90,
                edgecolors=_s.BG_CARD, linewidths=1.5,
            )
            ax.annotate(
                label, xy=(nx, ny), xytext=(0, -16),
                textcoords="offset points",
                ha="center", va="top", fontsize=7,
                color=_s.TEXT_PRIMARY, zorder=4, clip_on=False,
                bbox=dict(boxstyle="round,pad=0.2", fc=_s.BG_CARD, ec=_s.CHART_SPINE, alpha=0.90),
            )

        # LLDP legend items (appended below the main risk legend)
        lldp_items = []
        if infra_nodes:
            lldp_items.append(
                _L2D([0], [0], marker="s", color=_s.TEXT_SECONDARY,
                     markerfacecolor=_lldp_node_color(), markersize=8,
                     label="LLDP switch/router")
            )
        if leaf_nodes:
            lldp_items.append(
                _L2D([0], [0], marker="D", color=_s.TEXT_SECONDARY,
                     markerfacecolor=_lldp_node_color(), markersize=8,
                     label="LLDP device")
            )
        if lldp_items:
            ax.legend(
                handles=lldp_items, loc="lower left", fontsize=8,
                labelcolor=_s.TEXT_SECONDARY, facecolor=_s.BG_CARD,
                edgecolor=_s.CHART_SPINE, framealpha=0.9,
                title="LLDP", title_fontsize=8,
            )

    # ── shared legend ─────────────────────────────────────────────────────────

    def _legend(self, ax, mesh: bool = False, modem: bool = False) -> None:
        from matplotlib.lines import Line2D as _L2D
        items = [
            (_s.RED,           "HIGH risk"),
            (_s.AMBER,         "MEDIUM risk"),
            (_s.BLUE,          "LOW / known"),
            (_s.GREEN,         "Clean / Modem"),
            (_gateway_color(), "Gateway"),
        ]
        if mesh:
            items.append((_mesh_sat_color(), "Mesh satellite"))
        handles = [
            _L2D([0], [0], marker="o", color=_s.TEXT_SECONDARY, markerfacecolor=c,
                 markersize=9, label=lbl)
            for c, lbl in items
        ]
        ax.legend(handles=handles, loc="lower right", fontsize=8,
                  labelcolor=_s.TEXT_SECONDARY, facecolor=_s.BG_CARD,
                  edgecolor=_s.CHART_SPINE, framealpha=0.9)

    # ── interactive event handlers ────────────────────────────────────────────

    def _nearest_node(self, event) -> Optional[str]:
        """Return the node_key nearest to the mouse event, or None if >20 px away."""
        if event.inaxes is None or not self._ip_map:
            return None
        best_dist = float("inf")
        best_key = None
        for node_key, (nx, ny) in self._pos_map.items():
            if node_key not in self._ip_map:
                continue
            node_disp = self._ax.transData.transform((nx, ny))
            dist = math.hypot(event.x - node_disp[0], event.y - node_disp[1])
            if dist < best_dist:
                best_dist = dist
                best_key = node_key
        return best_key if best_dist <= 20 else None

    def _on_button_press(self, event) -> None:
        """Left-click emits node_clicked(ip). Right-click shows Pin context menu."""
        if event.inaxes is None or not self._ip_map:
            return
        best_key = self._nearest_node(event)
        if best_key is None:
            return

        if event.button == 1:
            # Left click — open device drawer
            self.node_clicked.emit(self._ip_map[best_key])

        elif event.button == 3:
            # Right click — pin/unpin context menu
            menu = QMenu(self)
            if best_key in self._pinned:
                action = menu.addAction("Unpin node")
            else:
                action = menu.addAction("Pin node")
            chosen = menu.exec(self._canvas.cursor().pos())
            if chosen is action:
                if best_key in self._pinned:
                    self._pinned.discard(best_key)
                else:
                    self._pinned.add(best_key)
                self._save_current_positions()

    def _on_motion(self, event) -> None:
        """Show tooltip annotation and PointingHandCursor when hovering over a node."""
        if self._hover_ann is None:
            return
        if event.inaxes is None or not self._ip_map:
            if self._hover_ann.get_visible():
                self._hover_ann.set_visible(False)
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
            return
        best_key = self._nearest_node(event)
        if best_key is not None:
            nx, ny = self._pos_map[best_key]
            new_text = self._tooltip_map.get(best_key, "")
            self._hover_ann.xy = (nx, ny)
            if self._hover_ann.get_text() != new_text or not self._hover_ann.get_visible():
                self._hover_ann.set_text(new_text)
                self._hover_ann.set_visible(True)
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            if self._hover_ann.get_visible():
                self._hover_ann.set_visible(False)
                self._canvas.draw_idle()
            self._canvas.setCursor(Qt.CursorShape.ArrowCursor)


# ── module-level helpers ──────────────────────────────────────────────────────

def _attr(d: Any, key: str, default: Any = "") -> Any:
    return d.get(key, default) if isinstance(d, dict) else getattr(d, key, default)


def _is_noise_ip(ip: str) -> bool:
    """Return True for IPs that add clutter but carry no topology meaning.

    Filtered classes:
      - Multicast:  224.0.0.0/4  (224–239.x.x.x) — mDNS, SSDP, IGMP probes
      - Broadcast:  255.255.255.255
      - Unresolved: 0.0.0.0 / empty / '?'
    """
    if not ip or ip in ("?", "0.0.0.0", "255.255.255.255"):
        return True
    try:
        first = int(ip.split(".")[0])
    except (ValueError, IndexError):
        return False
    return 224 <= first <= 239


def _dev_id(d: Any) -> str:
    mac = _attr(d, "mac", "")
    ip  = _attr(d, "ip",  "")
    return (mac or ip or str(id(d))).lower()


def _scatter(ax, pos: tuple, color: str, size: int, label: str,
             edge_color: str = _s.BG_CARD, linewidth: float = _DEF_LINEWIDTH) -> None:
    x, y = pos
    ax.scatter(x, y, s=size, c=color, zorder=3, alpha=0.9,
               edgecolors=edge_color, linewidths=linewidth)
    marker_r = math.sqrt(size / math.pi)
    ax.annotate(label, xy=(x, y), xytext=(0, -(marker_r + 4)),
                textcoords="offset points",
                ha="center", va="top", fontsize=7,
                color=_s.TEXT_PRIMARY, zorder=4, clip_on=False,
                bbox=dict(boxstyle="round,pad=0.2", fc=_s.BG_CARD, ec=_s.CHART_SPINE, alpha=0.9))


def _modem_label(data: dict) -> str:
    """Build a two-line label for the WAN modem topology node."""
    nt   = data.get("network_type") or ""
    band = data.get("nr5g_band") or data.get("lte_band") or ""
    bars = data.get("signal_bars")
    bar_str = ("●" * bars + "○" * (5 - bars)) if bars is not None else ""
    line2 = "  ·  ".join(filter(None, [nt, band, bar_str]))
    return f"5G Modem\n{line2}" if line2 else "5G Modem"
