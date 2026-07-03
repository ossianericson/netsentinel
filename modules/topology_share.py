"""
Sanitized "share my network" PNG export for the Network Map.

Renders a standalone matplotlib figure (never the live on-screen widget, so
a screenshot can't leak real data) using only sanitized device labels:
private IPs are aliased, public IPs and MACs are never shown, hostnames are
stripped. See modules/report_sanitizer.py.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.colours import (
    CHART_DARK_ACCENT,
    CHART_DARK_LINES,
    EXPORT_BG,
    EXPORT_BORDER,
    EXPORT_META,
    EXPORT_TEXT,
)
from modules.report_sanitizer import mask_ip, vendor_only

_FOOTER = "Generated locally by NetSentinel"


def _field(obj: Any, key: str, default: Any = None) -> Any:
    """Devices may arrive as dicts or DeviceInfo-style objects — duck-type both."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _prepare_render_data(
    devices: List[Any],
    gateway_ip: Optional[str] = None,
    gateway_mac: Optional[str] = None,
    edges: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """
    Build a sanitized, layout-ready node/edge list. Pure function — no
    matplotlib, no I/O — so it can be tested without rendering anything.
    """
    ip_map: Dict[str, str] = {}
    nodes: List[Dict[str, Any]] = []

    gw_key = gateway_ip or "__gateway__"
    gw_alias = mask_ip(gateway_ip, ip_map) if gateway_ip else None
    nodes.append({
        "key": gw_key,
        "label": f"Gateway ({gw_alias})" if gw_alias else "Gateway",
        "is_gateway": True,
    })

    for dev in devices:
        ip = _field(dev, "ip", "") or ""
        vendor = _field(dev, "vendor", None)
        alias = mask_ip(ip, ip_map)
        label = vendor_only(vendor=vendor)
        if alias:
            label = f"{label} ({alias})"
        nodes.append({"key": ip or vendor_only(vendor=vendor), "label": label, "is_gateway": False})

    edge_pairs = []
    for e in edges or []:
        src = mask_ip(_field(e, "src_ip", "") or "", ip_map) or "?"
        dst = mask_ip(_field(e, "dst_ip", "") or "", ip_map) or "?"
        edge_pairs.append((src, dst))

    return {"nodes": nodes, "edges": edge_pairs}


def render_sanitized_topology_png(
    devices: List[Any],
    gateway_ip: Optional[str] = None,
    gateway_mac: Optional[str] = None,
    edges: Optional[List[Any]] = None,
    output_path: Optional[Path] = None,
) -> Path:
    """Render a sanitized dark-themed topology PNG and save it to output_path."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    data = _prepare_render_data(devices, gateway_ip, gateway_mac, edges)
    nodes = data["nodes"]

    fig = Figure(figsize=(8, 6), dpi=120, facecolor=EXPORT_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(EXPORT_BG)
    ax.set_xlim(-1.3, 1.3)
    ax.set_ylim(-1.3, 1.3)
    ax.axis("off")

    gw = next((n for n in nodes if n["is_gateway"]), None)
    others = [n for n in nodes if not n["is_gateway"]]
    n = max(len(others), 1)

    positions: Dict[str, tuple] = {}
    if gw is not None:
        positions[gw["key"]] = (0.0, 0.0)
    for i, node in enumerate(others):
        angle = 2 * math.pi * i / n
        positions[node["key"]] = (math.cos(angle), math.sin(angle))

    # Edges first so they sit behind node markers
    for src, dst in data["edges"]:
        p1 = positions.get(src)
        p2 = positions.get(dst)
        if p1 and p2:
            ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=EXPORT_BORDER, linewidth=1.0, zorder=1)

    for i, node in enumerate(nodes):
        x, y = positions[node["key"]]
        color = CHART_DARK_ACCENT if node["is_gateway"] else CHART_DARK_LINES[i % len(CHART_DARK_LINES)]
        size = 480 if node["is_gateway"] else 260
        ax.scatter([x], [y], s=size, color=color, zorder=2, edgecolors=EXPORT_BG, linewidths=1.5)
        ax.annotate(
            node["label"], (x, y), textcoords="offset points", xytext=(0, -14),
            ha="center", fontsize=8, color=EXPORT_TEXT,
        )

    fig.text(0.5, 0.02, _FOOTER, ha="center", fontsize=8, color=EXPORT_META)

    out = Path(output_path) if output_path else Path("network_map_share.png")
    fig.savefig(out, facecolor=EXPORT_BG)
    return out
