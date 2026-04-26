"""
Network topology graph widget.

Renders a simple node graph:
  [Internet] ── [Gateway] ── [Device 1]
                           ── [Device 2]
                           ── ...

Uses matplotlib with a spring layout.  Nodes are colour-coded by risk level.
No extra packages — matplotlib is already a project dependency.
"""

from typing import Dict, List, Optional

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import FancyBboxPatch
from PyQt6.QtWidgets import QSizePolicy, QWidget, QVBoxLayout

from ui.styles import (
    BG_DARK, BG_CARD, TEXT_PRIMARY, TEXT_SECONDARY,
    ACCENT_LITE, RED, AMBER, GREEN, BLUE,
)

RISK_NODE_COLOR = {
    "HIGH":    RED,
    "MEDIUM":  AMBER,
    "LOW":     BLUE,
    "CLEAN":   GREEN,
    "UNKNOWN": "#555570",
}

GATEWAY_COLOR  = ACCENT_LITE
INTERNET_COLOR = "#3b82f6"


class TopologyWidget(QWidget):
    """Matplotlib-based network topology graph embedded in PyQt6."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._fig = Figure(figsize=(8, 5), dpi=96, facecolor=BG_DARK)
        self._ax  = self._fig.add_subplot(111)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)
        self._style_axes()

    def _style_axes(self):
        ax = self._ax
        ax.set_facecolor(BG_DARK)
        ax.axis("off")
        self._fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    def render(
        self,
        devices: List[dict],
        gateway_ip: Optional[str] = None,
        gateway_mac: Optional[str] = None,
    ) -> None:
        """
        Render topology from a list of device dicts with keys:
            ip, mac, hostname, vendor, risk_level
        """
        ax = self._ax
        ax.cla()
        self._style_axes()

        if not devices:
            ax.text(0.5, 0.5, "No devices to display.\nRun a scan first.",
                    ha="center", va="center", color=TEXT_SECONDARY,
                    fontsize=13, transform=ax.transAxes)
            self._canvas.draw()
            return

        # Build node list
        nodes: List[dict] = []

        # Internet cloud
        nodes.append({"id": "internet", "label": "☁ Internet", "color": INTERNET_COLOR, "size": 1200})

        # Gateway
        gw_label = f"Gateway\n{gateway_ip or '?'}"
        nodes.append({"id": "gateway", "label": gw_label, "color": GATEWAY_COLOR, "size": 1000})

        # Devices — accept both plain dicts and DeviceInfo dataclass objects
        for d in devices:
            if isinstance(d, dict):
                ip   = d.get("ip", "?")
                host = d.get("hostname") or d.get("vendor") or "Device"
                risk = d.get("risk_level", "UNKNOWN")
                mac  = d.get("mac", "")
            else:
                ip   = getattr(d, "ip", "?") or "?"
                host = getattr(d, "hostname", "") or getattr(d, "vendor", "") or "Device"
                risk = getattr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
                mac  = getattr(d, "mac", "") or ""
            label = f"{host[:14]}\n{ip}"
            color = RISK_NODE_COLOR.get(risk, RISK_NODE_COLOR["UNKNOWN"])
            nodes.append({"id": mac or ip, "label": label, "color": color, "size": 700})

        # Simple radial layout: internet top, gateway center, devices in circle
        import math
        n = len(nodes) - 2   # device count
        positions: Dict[str, tuple] = {
            "internet": (0.5, 0.92),
            "gateway":  (0.5, 0.60),
        }
        for i, node in enumerate(nodes[2:]):
            angle = math.pi + (i / max(n, 1)) * 2 * math.pi
            radius = 0.32
            x = 0.5 + radius * math.cos(angle) * (1 + 0.3 * (n > 8))
            y = 0.28 + radius * 0.6 * math.sin(angle)
            positions[node["id"]] = (x, y)

        # Draw edges
        gx, gy = positions["gateway"]
        ix, iy = positions["internet"]
        ax.plot([ix, gx], [iy, gy], color="#333355", linewidth=1.5, zorder=1)
        for node in nodes[2:]:
            nx, ny = positions[node["id"]]
            ax.plot([gx, nx], [gy, ny], color="#2a2a4a", linewidth=1.0, zorder=1)

        # Draw nodes
        for node in nodes:
            x, y = positions[node["id"]]
            ax.scatter(x, y, s=node["size"], c=node["color"],
                       zorder=3, alpha=0.9, edgecolors="#1a1a35", linewidths=1.5)
            ax.text(x, y - 0.07, node["label"],
                    ha="center", va="top", fontsize=7,
                    color=TEXT_PRIMARY, zorder=4,
                    bbox=dict(boxstyle="round,pad=0.2", fc=BG_CARD, ec="none", alpha=0.7))

        # Legend
        legend_items = [
            (RED,          "HIGH risk"),
            (AMBER,        "MEDIUM risk"),
            (BLUE,         "LOW / known"),
            (GREEN,        "Clean"),
            (GATEWAY_COLOR,"Gateway"),
        ]
        handles = [
            plt.scatter([], [], c=c, s=80, label=lbl)
            for c, lbl in legend_items
        ]
        ax.legend(handles=handles, loc="lower right",
                  fontsize=8, labelcolor=TEXT_SECONDARY,
                  facecolor=BG_CARD, edgecolor="#2a2a4a", framealpha=0.8)

        ax.set_title("Network Topology", color=ACCENT_LITE, fontsize=11, pad=6)
        self._fig.tight_layout(pad=0.5)
        self._canvas.draw()

    def clear(self):
        self._ax.cla()
        self._style_axes()
        self._canvas.draw()
