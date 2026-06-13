"""
topology_cytoscape.py — Cytoscape.js element and HTML builder for the Network Map page.

Converts the unified topology data model (devices, TopologyEdges, TopologyDiff,
LldpNeighbors, NetworkSegments, saved NodePositions) into:
  1. A Cytoscape.js element list + stylesheet dict (for testing / server-side use).
  2. A self-contained HTML string that embeds Cytoscape.js and a QWebChannel
     bridge, ready to be loaded into QWebEngineView.

Architecture rules:
  • Pure Python — no PyQt imports.
  • No direct DB writes.
  • Colours are passed in from the caller (ui/styles.py tokens) so this module
    has no dependency on ui/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── constants ─────────────────────────────────────────────────────────────────

_CANVAS_W = 1400.0   # reference canvas width (Cytoscape pixel space)
_CANVAS_H = 900.0    # reference canvas height

# Vendor keyword → CSS class for branded node tinting
_VENDOR_CLASS_MAP: Dict[str, str] = {
    "cisco":    "vendor-cisco",
    "ubiquiti": "vendor-ubiquiti",
    "tp-link":  "vendor-tp-link",
    "tplink":   "vendor-tp-link",
    "apple":    "vendor-apple",
    "netgear":  "vendor-netgear",
    "asus":     "vendor-asus",
    "eero":     "vendor-eero",
    "google":   "vendor-google",
}

# Cytoscape built-in layout names exposed in the toolbar dropdown
LAYOUT_NAMES: Dict[str, str] = {
    "Hierarchy":    "breadthfirst",
    "Physics":      "cose",
    "Breadthfirst": "breadthfirst",
    "Concentric":   "concentric",
    "Grid":         "grid",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _attr(d: Any, key: str, default: Any = "") -> Any:
    return d.get(key, default) if isinstance(d, dict) else getattr(d, key, default)


def _dev_id(d: Any) -> str:
    mac = _attr(d, "mac", "") or ""
    ip  = _attr(d, "ip",  "") or ""
    return (mac or ip or str(id(d))).lower()


def _vendor_class(vendor: str) -> str:
    v = (vendor or "").lower()
    for keyword, cls in _VENDOR_CLASS_MAP.items():
        if keyword in v:
            return cls
    return ""


def _risk_class(risk: str) -> str:
    return {
        "HIGH":    "risk-high",
        "STORM":   "risk-high",
        "MEDIUM":  "risk-medium",
        "WARNING": "risk-medium",
        "LOW":     "risk-low",
        "CLEAN":   "risk-clean",
    }.get((risk or "").upper(), "risk-unknown")


def _scale_pos(x: float, y: float) -> Dict[str, float]:
    """Convert 0–1 saved coordinates to Cytoscape canvas pixel coords."""
    return {"x": round(x * _CANVAS_W, 1), "y": round(y * _CANVAS_H, 1)}


def _cytoscape_script_tag() -> str:
    """Return an inline <script> block with the Cytoscape.js library.

    Checks for the bundled file at assets/js/cytoscape.min.js first.
    Falls back to the CDN for development use when the file is absent.
    """
    candidates = [
        Path(__file__).parent.parent / "assets" / "js" / "cytoscape.min.js",
    ]
    if getattr(sys, "frozen", False):
        candidates.insert(
            0,
            Path(sys._MEIPASS) / "assets" / "js" / "cytoscape.min.js",  # type: ignore[attr-defined]
        )
    for path in candidates:
        if path.exists():
            try:
                src = path.read_text(encoding="utf-8")
                return f"<script>{src}</script>"
            except OSError:
                pass  # non-fatal — fall through to CDN
    # CDN fallback (development only — production should always bundle the file)
    return (
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/'
        'cytoscape/3.30.4/cytoscape.min.js"></script>'
    )


# ── element builder ───────────────────────────────────────────────────────────

def build_cytoscape_elements(
    devices: list,
    edges: Optional[list] = None,                  # list[TopologyEdge]
    diff: Optional[Any] = None,                    # TopologyDiff | None
    lldp_neighbors: Optional[list] = None,         # list[LldpNeighbor] | None
    segments: Optional[list] = None,               # list[NetworkSegment]
    positions: Optional[Dict[str, Any]] = None,    # dict[str, NodePosition]
    gateway_ip: Optional[str] = None,
    gateway_mac: Optional[str] = None,
    mesh_units: Optional[list] = None,
    mesh_enrichment: Optional[dict] = None,
    modem_data: Optional[dict] = None,
    down_ips: Optional[set] = None,
    new_ips: Optional[set] = None,
) -> Dict[str, list]:
    """Convert scan data into a Cytoscape.js elements list and stylesheet.

    Returns {"elements": [...], "style": [...]}.
    """
    nodes: List[dict] = []
    cyto_edges: List[dict] = []
    down_ips = down_ips or set()
    new_ips  = new_ips  or set()
    positions = positions or {}

    # ── Infrastructure nodes ────────────────────────────────────────────────
    inet_id  = "__internet__"
    gw_id    = gateway_ip or "__gateway__"
    modem_id = "__modem__"

    # Internet cloud
    inet_pos = positions.get(inet_id)
    nodes.append({
        "group": "nodes",
        "data": {
            "id":    inet_id,
            "label": "Internet",
            "ip":    "",
            "tip":   "Internet / WAN uplink",
        },
        "classes": "internet",
        **({"position": _scale_pos(inet_pos.x, inet_pos.y)} if inet_pos else {}),
    })

    # WAN modem (optional)
    if modem_data:
        m_pos = positions.get(modem_id)
        nt    = modem_data.get("network_type") or ""
        band  = modem_data.get("nr5g_band") or modem_data.get("lte_band") or ""
        tip_parts = [x for x in [nt, band] if x]
        nodes.append({
            "group": "nodes",
            "data": {
                "id":    modem_id,
                "label": "5G Modem",
                "ip":    "",
                "tip":   "  ·  ".join(tip_parts) or "5G Modem",
            },
            "classes": "modem",
            **({"position": _scale_pos(m_pos.x, m_pos.y)} if m_pos else {}),
        })
        cyto_edges.append({
            "group": "edges",
            "data": {"id": "e-inet-modem", "source": inet_id, "target": modem_id},
            "classes": "arp-edge",
        })
        cyto_edges.append({
            "group": "edges",
            "data": {"id": "e-modem-gw", "source": modem_id, "target": gw_id},
            "classes": "arp-edge",
        })
    else:
        cyto_edges.append({
            "group": "edges",
            "data": {"id": "e-inet-gw", "source": inet_id, "target": gw_id},
            "classes": "arp-edge",
        })

    # Gateway node
    gw_pos = positions.get(gw_id) or positions.get(gateway_mac or "")
    gw_classes = "gateway"
    if gateway_ip in down_ips:
        gw_classes += " status-down"
    nodes.append({
        "group": "nodes",
        "data": {
            "id":    gw_id,
            "label": f"Gateway\n{gateway_ip or '?'}",
            "ip":    gateway_ip or "",
            "mac":   gateway_mac or "",
            "tip":   f"Gateway  {gateway_ip or '?'}",
        },
        "classes": gw_classes,
        **({"position": _scale_pos(gw_pos.x, gw_pos.y)} if gw_pos else {}),
    })

    # ── Mesh satellites ─────────────────────────────────────────────────────
    mesh_mac_set: set = set()
    if mesh_units:
        try:
            from modules.deco_client import _norm_mac  # type: ignore[attr-defined]
        except ImportError:
            def _norm_mac(m: str) -> str:
                return m.lower().replace("-", ":").strip()

        for unit in mesh_units:
            u_mac = _norm_mac(getattr(unit, "mac", "") or "")
            if u_mac:
                mesh_mac_set.add(u_mac)
            u_id = u_mac or getattr(unit, "name", "") or str(id(unit))
            u_pos = positions.get(u_id)
            u_role = getattr(unit, "role", "")
            u_cls = "gateway" if u_role == "master" else "mesh-sat"
            nodes.append({
                "group": "nodes",
                "data": {
                    "id":    u_id,
                    "label": getattr(unit, "name", "Satellite"),
                    "ip":    getattr(unit, "ip", "") or "",
                    "tip":   f"Mesh  {getattr(unit, 'name', '')}  ({u_role})",
                },
                "classes": u_cls,
                **({"position": _scale_pos(u_pos.x, u_pos.y)} if u_pos else {}),
            })
            if u_role != "master":
                cyto_edges.append({
                    "group": "edges",
                    "data": {
                        "id":     f"e-gw-{u_id}",
                        "source": gw_id,
                        "target": u_id,
                    },
                    "classes": "mesh-edge",
                })

    # ── Device nodes ────────────────────────────────────────────────────────
    diff_added = set(getattr(diff, "added_ips", []) if diff else [])

    for d in devices:
        ip   = _attr(d, "ip",         "") or ""
        mac  = (_attr(d, "mac",        "") or "").lower()
        host = _attr(d, "hostname",   "") or _attr(d, "vendor", "") or "Device"
        risk = _attr(d, "risk_level", "UNKNOWN") or "UNKNOWN"
        vendor = _attr(d, "vendor", "") or ""

        if not ip or ip in ("?", "0.0.0.0", "255.255.255.255"):
            continue
        try:
            first = int(ip.split(".")[0])
            if 224 <= first <= 239:  # multicast
                continue
        except (ValueError, IndexError):
            pass  # non-fatal — include the device

        dev_id = mac or ip
        if mac in mesh_mac_set:
            continue

        classes = _risk_class(risk)
        if ip in diff_added or ip in new_ips:
            classes += " new-device"
        if ip in down_ips:
            classes += " status-down"
        vc = _vendor_class(vendor)
        if vc:
            classes += f" {vc}"

        # Segment colour stored as data for the stylesheet label
        seg_color = ""
        if segments:
            try:
                from modules.network_segments import classify_device_segment  # type: ignore[attr-defined]
                seg = classify_device_segment(ip, segments)
                if seg:
                    seg_color = seg.color
            except Exception:
                pass  # non-fatal — no segment colouring

        # Parent: which mesh satellite is this client under?
        parent_id = ""
        if mesh_units and mesh_enrichment:
            try:
                from modules.deco_client import _norm_mac as _nm  # type: ignore[attr-defined]
                mc = mesh_enrichment.get(_nm(mac))
                if mc:
                    for unit in mesh_units:
                        if getattr(unit, "name", "") == mc.unit_name:
                            parent_id = _nm(getattr(unit, "mac", "") or "") or getattr(unit, "name", "")
                            break
            except Exception:
                pass  # non-fatal

        node_pos = positions.get(dev_id) or positions.get(ip)
        nodes.append({
            "group": "nodes",
            "data": {
                "id":       dev_id,
                "label":    f"{host[:16]}\n{ip}",
                "ip":       ip,
                "mac":      mac,
                "risk":     risk,
                "vendor":   vendor,
                "tip":      f"{host}\n{ip}\n{mac or ''}\nRisk: {risk}",
                "seg_color": seg_color,
                **({"parent": parent_id} if parent_id else {}),
            },
            "classes": classes.strip(),
            **({"position": _scale_pos(node_pos.x, node_pos.y)} if node_pos else {}),
        })

        # Edge to gateway (or satellite parent when in a mesh)
        src_id = parent_id if parent_id else gw_id
        cyto_edges.append({
            "group": "edges",
            "data": {
                "id":     f"e-{gw_id}-{dev_id}",
                "source": src_id,
                "target": dev_id,
            },
            "classes": "arp-edge",
        })

    # ── Health overlay on edges ──────────────────────────────────────────────
    if edges:
        edge_by_dst = {e.dst_ip: e for e in edges}
        for cyto_e in cyto_edges:
            dst_id = cyto_e["data"].get("target", "")
            # match by node IP field
            for n in nodes:
                if n["data"].get("id") == dst_id:
                    ip = n["data"].get("ip", "")
                    if ip in edge_by_dst:
                        h = edge_by_dst[ip]
                        cyto_e["data"]["latency"]   = h.latency_ms
                        cyto_e["data"]["loss"]       = h.packet_loss
                        cyto_e["data"]["bw"]         = h.bandwidth_mbps
                        cyto_e["data"]["edge_status"] = h.status
                        cyto_e["classes"] = (
                            cyto_e.get("classes", "arp-edge")
                            + f" status-{h.status}"
                        )
                    break

    # ── LLDP neighbor nodes ─────────────────────────────────────────────────
    if lldp_neighbors:
        for nb in lldp_neighbors:
            nb_ip      = getattr(nb, "neighbor_ip",       "") or ""
            nb_host    = getattr(nb, "neighbor_hostname",  "") or getattr(nb, "chassis_id", "Switch")
            nb_chassis = getattr(nb, "chassis_id",         "") or ""
            nb_id      = f"lldp-{nb_chassis or nb_ip or nb_host}"
            caps       = getattr(nb, "capabilities", []) or []
            is_infra   = bool({"bridge", "router"} & set(caps))
            lldp_cls   = "infrastructure" if is_infra else "lldp-leaf"
            lldp_pos   = positions.get(nb_id)
            nodes.append({
                "group": "nodes",
                "data": {
                    "id":    nb_id,
                    "label": f"{nb_host[:16]}\n{nb_chassis[:17]}",
                    "ip":    nb_ip,
                    "tip":   f"LLDP: {nb_host}\n{nb_ip}\nCaps: {', '.join(caps)}",
                },
                "classes": lldp_cls,
                **({"position": _scale_pos(lldp_pos.x, lldp_pos.y)} if lldp_pos else {}),
            })
            cyto_edges.append({
                "group": "edges",
                "data": {
                    "id":     f"e-gw-{nb_id}",
                    "source": gw_id,
                    "target": nb_id,
                },
                "classes": "lldp-edge",
            })

    # ── Diff removed nodes (ghosts) ─────────────────────────────────────────
    if diff and diff.removed_ips:
        for ip in diff.removed_ips:
            ghost_id = f"ghost-{ip}"
            nodes.append({
                "group": "nodes",
                "data": {
                    "id":    ghost_id,
                    "label": f"(gone)\n{ip}",
                    "ip":    ip,
                    "tip":   f"Removed device: {ip}",
                },
                "classes": "ghost hidden",
            })

    # ── Diff edge overlays ───────────────────────────────────────────────────
    if diff:
        for src_ip, dst_ip in getattr(diff, "added_edges", []):
            cyto_edges.append({
                "group": "edges",
                "data": {
                    "id":     f"new-edge-{src_ip}-{dst_ip}",
                    "source": gw_id,
                    "target": dst_ip.lower(),
                },
                "classes": "new-edge hidden",
            })
        for src_ip, dst_ip in getattr(diff, "removed_edges", []):
            cyto_edges.append({
                "group": "edges",
                "data": {
                    "id":     f"rem-edge-{src_ip}-{dst_ip}",
                    "source": gw_id,
                    "target": f"ghost-{dst_ip}",
                },
                "classes": "removed-edge hidden",
            })

    return {"elements": nodes + cyto_edges, "style": _build_style()}


def _build_style() -> list:
    """Return the Cytoscape.js stylesheet list."""
    return [
        # ── Base node ─────────────────────────────────────────────────────────
        {
            "selector": "node",
            "style": {
                "label":            "data(label)",
                "text-valign":      "bottom",
                "text-halign":      "center",
                "text-wrap":        "wrap",
                "text-max-width":   "100px",
                "font-size":        "10px",
                "color":            "#1A1A2E",
                "background-color": "#5A6A7A",
                "width":            "36px",
                "height":           "36px",
                "border-width":     "2px",
                "border-color":     "#D4D4D4",
            },
        },
        # ── Risk levels ───────────────────────────────────────────────────────
        {"selector": "node.risk-high",    "style": {"background-color": "#D93025"}},
        {"selector": "node.risk-medium",  "style": {"background-color": "#F59E0B"}},
        {"selector": "node.risk-low",     "style": {"background-color": "#0078D4"}},
        {"selector": "node.risk-clean",   "style": {"background-color": "#2E7D32"}},
        {"selector": "node.risk-unknown", "style": {"background-color": "#5A6A7A"}},
        # ── Infrastructure nodes ──────────────────────────────────────────────
        {
            "selector": "node.internet",
            "style": {
                "background-color": "#0078D4",
                "shape":            "round-rectangle",
                "width":            "60px",
                "height":           "60px",
                "font-size":        "11px",
                "font-weight":      "bold",
                "color":            "#1A1A2E",
            },
        },
        {
            "selector": "node.gateway",
            "style": {
                "background-color": "#0078D4",
                "shape":            "round-rectangle",
                "width":            "50px",
                "height":           "50px",
                "border-color":     "#005A9E",
                "border-width":     "3px",
                "font-weight":      "bold",
                "color":            "#1A1A2E",
            },
        },
        {
            "selector": "node.mesh-sat",
            "style": {
                "background-color": "#7C3AED",
                "shape":            "pentagon",
                "width":            "44px",
                "height":           "44px",
                "color":            "#1A1A2E",
            },
        },
        {
            "selector": "node.modem",
            "style": {
                "background-color": "#2E7D32",
                "shape":            "round-rectangle",
                "width":            "44px",
                "height":           "44px",
                "color":            "#1A1A2E",
            },
        },
        {
            "selector": "node.infrastructure",
            "style": {
                "background-color": "#0E7490",
                "shape":            "rectangle",
                "width":            "40px",
                "height":           "40px",
                "color":            "#1A1A2E",
            },
        },
        {
            "selector": "node.lldp-leaf",
            "style": {
                "background-color": "#0E7490",
                "shape":            "diamond",
                "width":            "36px",
                "height":           "36px",
                "color":            "#1A1A2E",
            },
        },
        # ── Status overlays ───────────────────────────────────────────────────
        {
            "selector": "node.status-down",
            "style": {"border-color": "#D93025", "border-width": "3px"},
        },
        {
            "selector": "node.new-device",
            "style": {"border-color": "#0E7490", "border-width": "3px"},
        },
        # ── Diff: ghost (removed) nodes ───────────────────────────────────────
        {
            "selector": "node.ghost",
            "style": {
                "background-color": "#5A6A7A",
                "opacity":          "0.3",
                "border-style":     "dashed",
                "border-color":     "#5A6A7A",
            },
        },
        # ── Focus mode (faded) ────────────────────────────────────────────────
        {
            "selector": "node.faded, edge.faded",
            "style": {"opacity": "0.15"},
        },
        # ── Selected node highlight ───────────────────────────────────────────
        {
            "selector": "node:selected",
            "style": {
                "border-color":     "#0078D4",
                "border-width":     "3px",
                "overlay-color":    "#0078D4",
                "overlay-padding":  "6px",
                "overlay-opacity":  "0.1",
            },
        },
        # ── Hidden (Show Changes toggle) ──────────────────────────────────────
        {"selector": ".hidden", "style": {"display": "none"}},
        # ── Base edge ─────────────────────────────────────────────────────────
        {
            "selector": "edge",
            "style": {
                "width":              "1.5px",
                "line-color":         "#D4D4D4",
                "curve-style":        "bezier",
                "target-arrow-shape": "none",
            },
        },
        # ── Edge status / type classes ────────────────────────────────────────
        {"selector": "edge.status-up",      "style": {"line-color": "#2E7D32", "width": "2px"}},
        {"selector": "edge.status-degraded","style": {"line-color": "#F59E0B", "width": "2.5px"}},
        {"selector": "edge.status-down",    "style": {"line-color": "#D93025", "width": "2.5px"}},
        {
            "selector": "edge.lldp-edge",
            "style": {"line-color": "#0E7490", "width": "2.5px"},
        },
        {
            "selector": "edge.mesh-edge",
            "style": {"line-color": "#7C3AED", "width": "2px", "line-style": "dashed"},
        },
        {
            "selector": "edge.new-edge",
            "style": {
                "line-color": "#2E7D32", "width": "2px",
                "line-style": "dashed",
            },
        },
        {
            "selector": "edge.removed-edge",
            "style": {
                "line-color": "#D93025", "width": "2px",
                "line-style": "dotted",
            },
        },
    ]


# ── HTML builder ──────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:#F4F4F4; font-family:-apple-system,BlinkMacSystemFont,sans-serif; overflow:hidden; }}
#cy {{ width:100vw; height:100vh; }}
#tip {{
  position:absolute; display:none; z-index:999; pointer-events:none;
  background:#FFFFFF; border:1px solid #D4D4D4; border-radius:4px;
  padding:6px 10px; font-size:12px; color:#1A1A2E; max-width:220px;
  box-shadow:0 2px 8px rgba(0,0,0,.15); white-space:pre-wrap;
}}
</style>
</head>
<body>
<div id="cy"></div>
<div id="tip"></div>
{cytoscape_script}
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
"use strict";
var cy, qtBridge, focusMode = false, changesVisible = false;
var elements = {elements_json};
var layoutName = {layout_json};

// QWebChannel bridge
new QWebChannel(qt.webChannelTransport, function(channel) {{
  qtBridge = channel.objects.bridge;
}});

// Initialize Cytoscape
cy = cytoscape({{
  container: document.getElementById('cy'),
  elements:  elements,
  style:     {style_json},
  layout:    {{ name: layoutName, animate: false, padding: 60 }},
  minZoom:   0.08,
  maxZoom:   5.0,
  wheelSensitivity: 0.25,
}});

// ── Tap (click) on node with IP → emit nodeClicked ───────────────────────────
cy.on('tap', 'node[ip]', function(evt) {{
  var ip = evt.target.data('ip');
  if (ip && qtBridge) qtBridge.nodeClicked(ip);
}});

// ── Drag free → persist position ──────────────────────────────────────────────
cy.on('dragfree', 'node', function(evt) {{
  var node = evt.target;
  var pos  = node.position();
  var cw   = cy.width()  || {canvas_w};
  var ch   = cy.height() || {canvas_h};
  if (qtBridge) {{
    qtBridge.savePosition(
      node.id(),
      (pos.x / cw).toFixed(4),
      (pos.y / ch).toFixed(4)
    );
  }}
}});

// ── Hover tooltip ─────────────────────────────────────────────────────────────
var tip = document.getElementById('tip');
cy.on('mouseover', 'node', function(evt) {{
  var d = evt.target.data();
  tip.textContent = d.tip || d.label || '';
  tip.style.display = 'block';
}});
cy.on('mouseout', 'node', function() {{ tip.style.display = 'none'; }});
document.getElementById('cy').addEventListener('mousemove', function(e) {{
  tip.style.left = (e.clientX + 16) + 'px';
  tip.style.top  = (e.clientY - 10) + 'px';
}});

// ── Selection → Focus Mode update ─────────────────────────────────────────────
cy.on('tap', function() {{ if (focusMode) window._applyFocus(); }});

// ── Python-callable global functions ──────────────────────────────────────────
window.setLayout = function(name) {{
  cy.layout({{ name: name, animate: true, animationDuration: 350, padding: 60 }}).run();
}};

window.fitView = function() {{ cy.fit(undefined, 50); }};

window.resetLayout = function() {{
  cy.layout({{ name: layoutName, animate: true, animationDuration: 350, padding: 60 }}).run();
}};

window.toggleFocus = function(enabled) {{
  focusMode = enabled;
  window._applyFocus();
}};

window._applyFocus = function() {{
  cy.elements().removeClass('faded');
  if (!focusMode) return;
  var sel = cy.nodes(':selected');
  if (!sel.length) return;
  var hood = sel.closedNeighborhood();
  cy.elements().not(hood).addClass('faded');
}};

window.toggleChanges = function(show) {{
  changesVisible = show;
  var ghosts = cy.elements('.ghost, .removed-edge, .new-edge');
  if (show) {{ ghosts.removeClass('hidden'); }}
  else      {{ ghosts.addClass('hidden'); }}
}};

window.exportPng = function() {{
  var data = cy.png({{ full: true, scale: 2, bg: '#F4F4F4' }});
  if (qtBridge) qtBridge.exportPng(data);
}};
</script>
</body>
</html>
"""


def build_cytoscape_html(
    devices: list,
    edges: Optional[list] = None,
    diff: Optional[Any] = None,
    lldp_neighbors: Optional[list] = None,
    segments: Optional[list] = None,
    positions: Optional[Dict[str, Any]] = None,
    gateway_ip: Optional[str] = None,
    gateway_mac: Optional[str] = None,
    mesh_units: Optional[list] = None,
    mesh_enrichment: Optional[dict] = None,
    modem_data: Optional[dict] = None,
    down_ips: Optional[set] = None,
    new_ips: Optional[set] = None,
    initial_layout: str = "breadthfirst",
) -> str:
    """Return a complete self-contained HTML string for QWebEngineView.

    The HTML embeds Cytoscape.js (from the local bundle when available),
    a QWebChannel bridge, and all interaction logic.
    """
    result = build_cytoscape_elements(
        devices=devices,
        edges=edges,
        diff=diff,
        lldp_neighbors=lldp_neighbors,
        segments=segments,
        positions=positions,
        gateway_ip=gateway_ip,
        gateway_mac=gateway_mac,
        mesh_units=mesh_units,
        mesh_enrichment=mesh_enrichment,
        modem_data=modem_data,
        down_ips=down_ips,
        new_ips=new_ips,
    )

    # Determine layout: if we have saved positions, use preset layout
    layout = "preset" if positions else initial_layout

    return _HTML_TEMPLATE.format(
        cytoscape_script=_cytoscape_script_tag(),
        elements_json=json.dumps(result["elements"]),
        style_json=json.dumps(result["style"]),
        layout_json=json.dumps(layout),
        canvas_w=_CANVAS_W,
        canvas_h=_CANVAS_H,
    )
