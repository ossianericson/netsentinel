"""
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
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout

from ui.styles import (
    ACCENT, AMBER, BG_CARD, BG_DARK, BLUE, BORDER,
    CHART_PURPLE, CHART_TITLE, GREEN, RED,
    TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY,
)

RISK_NODE_COLOR: Dict[str, str] = {
    "HIGH":    RED,
    "MEDIUM":  AMBER,
    "LOW":     BLUE,
    "CLEAN":   GREEN,
    "UNKNOWN": TEXT_MUTED,
}
GATEWAY_COLOR  = ACCENT
INTERNET_COLOR = ACCENT
MESH_SAT_COLOR = CHART_PURPLE   # satellite nodes — distinct from all risk colours
MODEM_COLOR    = GREEN           # WAN modem node


class TopologyWidget(QWidget):
    """Matplotlib-based network topology graph embedded in PyQt6."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._fig    = Figure(figsize=(8, 5), dpi=96, facecolor=BG_DARK)
        self._ax     = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self._style_axes()

    def _style_axes(self) -> None:
        ax = self._ax
        ax.set_facecolor(BG_CARD)
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
    ) -> None:
        ax = self._ax
        ax.cla()
        self._style_axes()

        # Strip noise IPs before layout: multicast (224–239.x.x.x), broadcast,
        # and unresolved addresses add clutter without meaning on the map.
        devices = [d for d in devices if not _is_noise_ip(_attr(d, "ip", ""))]

        if not devices:
            ax.text(0.5, 0.5, "No devices to display.\nRun a scan first.",
                    ha="center", va="center", color=TEXT_MUTED,
                    fontsize=13, transform=ax.transAxes)
            self._canvas.draw()
            return

        if mesh_units and mesh_enrichment:
            self._render_mesh(ax, devices, gateway_ip, mesh_units, mesh_enrichment,
                              modem_data=modem_data)
        else:
            self._render_flat(ax, devices, gateway_ip, gateway_mac, modem_data=modem_data)

        # Extend y-axis below 0 so labels placed at (y - 0.07) near the bottom
        # are never clipped by the axes patch boundary.
        ax.set_xlim(-0.02, 1.02)
        ax.set_ylim(-0.12, 1.02)
        self._canvas.draw()

    def clear(self) -> None:
        self._ax.cla()
        self._style_axes()
        self._canvas.draw()

    # ── flat star layout ──────────────────────────────────────────────────────

    def _render_flat(self, ax, devices, gateway_ip, gateway_mac, modem_data=None) -> None:
        nodes: List[dict] = [
            {"id": "internet", "label": "☁  Internet", "color": INTERNET_COLOR, "size": 1200},
            {"id": "gateway",  "label": f"Gateway\n{gateway_ip or '?'}", "color": GATEWAY_COLOR, "size": 1000},
        ]
        for d in devices:
            ip    = _attr(d, "ip",         "?")
            host  = _attr(d, "hostname",   "") or _attr(d, "vendor", "") or "Device"
            risk  = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
            mac   = _attr(d, "mac",        "")
            nodes.append({
                "id":    mac or ip,
                "label": f"{host[:14]}\n{ip}",
                "color": RISK_NODE_COLOR.get(risk, RISK_NODE_COLOR["UNKNOWN"]),
                "size":  700,
            })

        n = len(nodes) - 2
        # Modem node inserts between Internet and Gateway — compress their y positions
        has_modem = bool(modem_data)
        y_internet = 0.92
        y_modem    = 0.76
        y_gateway  = 0.58 if has_modem else 0.60
        positions: Dict[str, tuple] = {
            "internet": (0.5, y_internet),
            "gateway":  (0.5, y_gateway),
        }
        if has_modem:
            positions["__modem__"] = (0.5, y_modem)

        for i, node in enumerate(nodes[2:]):
            angle  = math.pi + (i / max(n, 1)) * 2 * math.pi
            radius = 0.32 * (1 + 0.3 * (n > 8))
            positions[node["id"]] = (
                0.5  + radius * math.cos(angle),
                0.26 + radius * 0.6 * math.sin(angle),
            )

        gx, gy = positions["gateway"]
        ix, iy = positions["internet"]

        if has_modem:
            mx, my = positions["__modem__"]
            ax.plot([ix, mx], [iy, my], color=BORDER, linewidth=1.5, zorder=1)
            ax.plot([mx, gx], [my, gy], color=BORDER, linewidth=1.5, zorder=1)
        else:
            ax.plot([ix, gx], [iy, gy], color=BORDER, linewidth=1.5, zorder=1)

        for node in nodes[2:]:
            nx, ny = positions[node["id"]]
            ax.plot([gx, nx], [gy, ny], color=BORDER, linewidth=1.0, zorder=1)

        for node in nodes:
            _scatter(ax, positions[node["id"]], node["color"], node["size"], node["label"])

        if has_modem:
            _scatter(ax, positions["__modem__"], MODEM_COLOR, 900,
                     _modem_label(modem_data))

        self._legend(ax, mesh=False, modem=has_modem)
        ax.set_title("Network Topology", color=CHART_TITLE, fontsize=11, fontweight="bold", pad=4)

    # ── mesh 3-tier layout ────────────────────────────────────────────────────

    def _render_mesh(self, ax, devices, gateway_ip, mesh_units, mesh_enrichment,
                     modem_data=None) -> None:
        try:
            from modules.deco_client import _norm_mac
        except ImportError:
            def _norm_mac(m: str) -> str:
                return m.lower().replace("-", ":").strip()

        master     = next((u for u in mesh_units if getattr(u, "role", "") == "master"), None)
        satellites = [u for u in mesh_units if getattr(u, "role", "") != "master"]

        # Build the set of MACs that are already drawn as dedicated infrastructure
        # nodes (gateway + all satellites).  Any ARP-scan device sharing one of
        # these MACs would appear twice on the map — suppress them from the
        # client/unassigned pools.
        infra_macs: set[str] = set()
        for unit in mesh_units:
            m = _norm_mac(getattr(unit, "mac", "") or "")
            if m:
                infra_macs.add(m)
        # Also exclude any device whose IP is the gateway IP (router reachable
        # via ARP but already represented by the __gateway__ node).
        infra_ips: set[str] = {gateway_ip} if gateway_ip else set()

        # Group ARP-scan devices by which mesh satellite they connect to
        by_unit: Dict[str, list] = defaultdict(list)
        unassigned: list = []
        for d in devices:
            if _norm_mac(_attr(d, "mac", "") or "") in infra_macs:
                continue
            if (_attr(d, "ip", "") or "") in infra_ips:
                continue
            mac = _norm_mac(_attr(d, "mac", ""))
            mc  = mesh_enrichment.get(mac)
            if mc:
                by_unit[mc.unit_name].append(d)
            else:
                unassigned.append(d)

        # Inject mesh-only clients (Deco API knows them but ARP scan missed them,
        # e.g. phones that did not respond to ARP on a satellite node)
        covered_macs = {_norm_mac(_attr(d, "mac", "") or "") for d in devices}
        for mc in mesh_enrichment.values():
            mc_mac = _norm_mac(mc.mac)
            if mc_mac in covered_macs or mc_mac in infra_macs:
                continue
            by_unit[mc.unit_name].append({
                "mac":        mc.mac,
                "ip":         mc.ip or "",
                "hostname":   mc.name,
                "risk_level": "CLEAN",
            })

        # ── Y tiers — three clearly separated rows ────────────────────────────
        # Unassigned devices get their own tier between gateway and satellites
        # so their dashed edges never cross through satellite positions.
        has_modem   = bool(modem_data)
        Y_INTERNET  = 0.91
        Y_MODEM     = 0.80    # WAN modem — between internet and gateway (only when present)
        Y_GATEWAY   = 0.68 if has_modem else 0.73
        Y_UNASSIGNED = 0.56   # direct-to-gateway devices — above satellite row
        Y_SATELLITE  = 0.42   # mesh satellite nodes
        Y_CLIENT     = 0.16   # leaf client devices

        # ── X positions for satellites ────────────────────────────────────────
        # Use 0.13–0.87 margins so labels at the edges don't clip.
        # Satellites are always evenly spread across the full width;
        # none will land at x=0.5 unless there is exactly one satellite.
        n_sats = len(satellites)
        X_L, X_R = 0.13, 0.87

        pos: Dict[str, tuple] = {
            "__internet__": (0.5, Y_INTERNET),
            "__gateway__":  (0.5, Y_GATEWAY),
        }
        if has_modem:
            pos["__modem__"] = (0.5, Y_MODEM)

        for i, unit in enumerate(satellites):
            if n_sats == 1:
                sx = 0.5
            else:
                sx = X_L + i * (X_R - X_L) / (n_sats - 1)
            pos[unit.mac] = (sx, Y_SATELLITE)

        # ── Client positions — spread under their satellite ───────────────────
        # Half-spread = 40 % of the inter-satellite gap, capped so no two
        # satellites' client clouds touch each other.
        if n_sats > 1:
            sat_gap   = (X_R - X_L) / (n_sats - 1)
            max_half  = sat_gap * 0.42          # never overlap adjacent satellite
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

        # ── Unassigned devices — centred on gateway, own tier ─────────────────
        nu = len(unassigned)
        u_half = min(0.22, max(0.04, nu * 0.055))
        for j, d in enumerate(unassigned):
            cx = 0.5 if nu == 1 else 0.5 - u_half + j * 2 * u_half / (nu - 1)
            pos[_dev_id(d)] = (cx, Y_UNASSIGNED)

        # ── Draw all edges first (zorder=1) so nodes paint over them ─────────
        gx, gy = pos["__gateway__"]
        ix, iy = pos["__internet__"]
        if has_modem:
            mx, my = pos["__modem__"]
            ax.plot([ix, mx], [iy, my], color=BORDER, linewidth=2.0, zorder=1)
            ax.plot([mx, gx], [my, gy], color=BORDER, linewidth=2.0, zorder=1)
        else:
            ax.plot([ix, gx], [iy, gy], color=BORDER, linewidth=2.0, zorder=1)

        for unit in satellites:
            sx, sy = pos[unit.mac]
            ax.plot([gx, sx], [gy, sy], color=BORDER, linewidth=1.4, zorder=1)
            for d in by_unit.get(unit.name, []):
                did = _dev_id(d)
                if did in pos:
                    cx, cy = pos[did]
                    ax.plot([sx, cx], [sy, cy], color=BORDER, linewidth=0.7, zorder=1)

        for d in unassigned:
            did = _dev_id(d)
            if did in pos:
                cx, cy = pos[did]
                ax.plot([gx, cx], [gy, cy], color=BORDER, linewidth=0.7,
                        linestyle="--", alpha=0.55, zorder=1)

        # ── Draw nodes and labels (zorder=3/4) ───────────────────────────────
        _scatter(ax, pos["__internet__"], INTERNET_COLOR, 1200, "☁  Internet")
        if has_modem:
            _scatter(ax, pos["__modem__"], MODEM_COLOR, 900, _modem_label(modem_data))

        gw_name  = master.name if master else "Gateway"
        gw_label = f"{gw_name}\n{gateway_ip or ''}"
        _scatter(ax, pos["__gateway__"], GATEWAY_COLOR, 1000, gw_label)

        for unit in satellites:
            nc    = len(by_unit.get(unit.name, []))
            label = f"⬡  {unit.name}\n{nc} client{'s' if nc != 1 else ''}"
            _scatter(ax, pos[unit.mac], MESH_SAT_COLOR, 900, label)

        for unit in satellites:
            for d in by_unit.get(unit.name, []):
                _draw_device(ax, d, pos)

        for d in unassigned:
            _draw_device(ax, d, pos)

        self._legend(ax, mesh=True, modem=has_modem)
        ax.set_title("Network Topology — Mesh", color=CHART_TITLE,
                     fontsize=11, fontweight="bold", pad=4)

    # ── shared legend ─────────────────────────────────────────────────────────

    def _legend(self, ax, mesh: bool = False, modem: bool = False) -> None:
        items = [
            (RED,           "HIGH risk"),
            (AMBER,         "MEDIUM risk"),
            (BLUE,          "LOW / known"),
            (GREEN,         "Clean / Modem"),
            (GATEWAY_COLOR, "Gateway"),
        ]
        if mesh:
            items.append((MESH_SAT_COLOR, "Mesh satellite"))
        handles = [plt.scatter([], [], c=c, s=80, label=lbl) for c, lbl in items]
        ax.legend(handles=handles, loc="lower right", fontsize=8,
                  labelcolor=TEXT_SECONDARY, facecolor=BG_CARD,
                  edgecolor=BORDER, framealpha=0.9)


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


def _scatter(ax, pos: tuple, color: str, size: int, label: str) -> None:
    x, y = pos
    ax.scatter(x, y, s=size, c=color, zorder=3, alpha=0.9,
               edgecolors=BG_CARD, linewidths=1.5)
    # Offset in display points so the gap is pixel-constant at any widget size.
    # Marker radius in points = sqrt(area/π); add 4pt (~5px) gap below the edge.
    marker_r = math.sqrt(size / math.pi)
    ax.annotate(label, xy=(x, y), xytext=(0, -(marker_r + 4)),
                textcoords="offset points",
                ha="center", va="top", fontsize=7,
                color=TEXT_PRIMARY, zorder=4, clip_on=False,
                bbox=dict(boxstyle="round,pad=0.2", fc=BG_CARD, ec=BORDER, alpha=0.9))


def _modem_label(data: dict) -> str:
    """Build a two-line label for the WAN modem topology node."""
    nt   = data.get("network_type") or ""
    band = data.get("nr5g_band") or data.get("lte_band") or ""
    bars = data.get("signal_bars")
    bar_str = ("●" * bars + "○" * (5 - bars)) if bars is not None else ""
    line2 = "  ·  ".join(filter(None, [nt, band, bar_str]))
    return f"5G Modem\n{line2}" if line2 else "5G Modem"


def _draw_device(ax, d: Any, pos: Dict[str, tuple]) -> None:
    dev_id = _dev_id(d)
    if dev_id not in pos:
        return
    ip    = _attr(d, "ip",         "?")
    host  = _attr(d, "hostname",   "") or _attr(d, "vendor", "") or "Device"
    risk  = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
    color = RISK_NODE_COLOR.get(risk, RISK_NODE_COLOR["UNKNOWN"])
    _scatter(ax, pos[dev_id], color, 600, f"{host[:13]}\n{ip}")
