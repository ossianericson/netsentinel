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
  • Stylesheet extracted to modules/topology_cytoscape_style.py (Audit Cleanup sprint).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from modules.topology_cytoscape_style import _build_style

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

# Layout modes exposed in the toolbar dropdown.
# "geo_*" modes are computed in Python (topology_layouts.py) and injected as
# preset positions — Cytoscape receives layout: "preset" for those.
# "cose" is the only mode that delegates to Cytoscape's physics engine.
LAYOUT_NAMES: Dict[str, str] = {
    "Hierarchy":  "geo_hierarchy",
    "Physics":    "geo_radial",
    "Concentric": "geo_concentric",
    "Grid":       "geo_grid",
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


# ── element builder ───────────────────────────────────────────────────────────

def _bw_class(bps: float) -> str:
    """Return a traffic CSS class based on bits-per-second value."""
    mbps = bps / 1_000_000
    if mbps >= 5.0:
        return "traffic-high"
    if mbps >= 0.5:
        return "traffic-medium"
    if bps > 0:
        return "traffic-low"
    return ""


def _bw_label(bps: float) -> str:
    """Format bps as a compact string for node tooltip / label."""
    mbps = bps / 1_000_000
    if mbps >= 0.1:
        return f"{mbps:.1f} Mbps"
    return f"{bps / 1000:.0f} Kbps"


def synthesize_mesh_only_clients(
    devices: list,
    mesh_enrichment: Optional[dict],
    mesh_units: Optional[list],
    gateway_ip: Optional[str] = None,
) -> list:
    """Return devices + stub dicts for mesh clients the ARP scan never saw.

    A mesh Wi-Fi client (e.g. the scanning PC itself) does not answer ARP, so it
    is absent from `devices` but present in `mesh_enrichment`. This makes it a
    real device node in BOTH map builders. Returns `devices` unchanged when there
    is no mesh data.
    """
    if not mesh_enrichment or not mesh_units:
        return devices
    try:
        from modules.deco_client import _norm_mac  # type: ignore[attr-defined]
    except ImportError:
        def _norm_mac(mac: str) -> str:
            return mac.lower().replace("-", ":").strip()

    infra_macs = {_norm_mac(getattr(u, "mac", "") or "") for u in mesh_units}
    covered = {_norm_mac(_attr(d, "mac", "") or "") for d in devices}
    out = list(devices)
    for mc in mesh_enrichment.values():
        m = _norm_mac(mc.mac)
        if not m or m in covered or m in infra_macs:
            continue
        out.append({
            "mac": mc.mac, "ip": mc.ip or "", "hostname": mc.name,
            "risk_level": "CLEAN", "mesh_unit": mc.unit_name,
        })
        covered.add(m)
    return out


_COLLAPSE_THRESHOLD_DEFAULT = 150


def collapse_to_segments(
    devices: list,
    gateway_ip: str = "",
    expanded: Optional[set] = None,
    threshold: int = _COLLAPSE_THRESHOLD_DEFAULT,
) -> list:
    """
    Collapse *devices* to one synthetic placeholder per /24 subnet once the
    total device count exceeds *threshold* — so a large corporate ARP table
    (hundreds of devices) renders as a readable handful of segment nodes
    instead of an unreadable single-row wall (Part 1/D). Below the threshold,
    *devices* is returned unchanged — the home-network render path is untouched.

    Any CIDR in *expanded* is left un-collapsed (its real devices are returned
    individually) — this is how double-clicking a segment node expands it.

    Each placeholder is a plain dict shaped enough like a device (ip/mac/
    hostname/device_type/risk_level) to flow through build_cytoscape_elements()
    and the classic matplotlib view with no further changes. Its "ip" is the
    CIDR string itself — unique, never collides with a real dotted-quad IP,
    and is what a click on the node reports back (so the caller can toggle it
    into *expanded* and re-render).

    A device with no usable IPv4 address is always returned individually —
    there is nothing to group it by.
    """
    devices = list(devices)
    if len(devices) <= threshold:
        return devices

    expanded = expanded or set()
    from modules.network_segments import auto_detect_segments, classify_device_segment

    segments = auto_detect_segments(devices, gateway_ip)
    result: List[dict] = []
    counts: Dict[str, int] = {}

    for d in devices:
        ip = _attr(d, "ip", "") or ""
        seg = classify_device_segment(ip, segments) if ip else None
        if seg is None or seg.cidr in expanded:
            result.append(d)
            continue
        counts[seg.cidr] = counts.get(seg.cidr, 0) + 1

    for seg in segments:
        n = counts.get(seg.cidr, 0)
        if n == 0:
            continue
        result.append({
            "ip": seg.cidr,
            "mac": "",
            "hostname": f"{seg.cidr} — {n} devices",
            "vendor": "",
            "risk_level": "UNKNOWN",
            "device_type": "segment",
            "segment_cidr": seg.cidr,
            "segment_count": n,
        })

    return result


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
    bw_by_mac: Optional[Dict[str, float]] = None,  # mac → total_bps (traffic overlay)
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

    # Pre-detect mesh master name so the gateway node label matches the classic
    # view (which merges the master unit into the gateway node rather than
    # creating a separate node for it).
    _gw_display_name = "Gateway"
    if mesh_units:
        try:
            _master_unit = next(
                (u for u in mesh_units if getattr(u, "role", "") == "master"), None
            )
            if _master_unit:
                _gw_display_name = getattr(_master_unit, "name", None) or "Gateway"
        except Exception:
            pass  # non-fatal — fall back to "Gateway"

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

    # Gateway node — when a mesh master unit exists its name is shown here
    # (matching the classic view) instead of creating a duplicate node.
    gw_pos = positions.get(gw_id) or positions.get(gateway_mac or "")
    gw_classes = "gateway"
    if gateway_ip in down_ips:
        gw_classes += " status-down"
    nodes.append({
        "group": "nodes",
        "data": {
            "id":    gw_id,
            "label": f"{_gw_display_name}\n{gateway_ip or '?'}",
            "ip":    gateway_ip or "",
            "mac":   gateway_mac or "",
            "tip":   f"Gateway  {_gw_display_name}  {gateway_ip or '?'}",
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
            def _norm_mac(mac: str) -> str:
                return mac.lower().replace("-", ":").strip()

        for unit in mesh_units:
            u_mac = _norm_mac(getattr(unit, "mac", "") or "")
            if u_mac:
                mesh_mac_set.add(u_mac)
            u_role = getattr(unit, "role", "")
            if u_role == "master":
                # Master unit is already represented by the gateway node;
                # adding it again would create a duplicate node.
                continue
            u_id = u_mac or getattr(unit, "name", "") or str(id(unit))
            u_pos = positions.get(u_id)
            nodes.append({
                "group": "nodes",
                "data": {
                    "id":    u_id,
                    "label": getattr(unit, "name", "Satellite"),
                    "ip":    getattr(unit, "ip", "") or "",
                    "tip":   f"Mesh  {getattr(unit, 'name', '')}  (satellite)",
                },
                "classes": "mesh-sat",
                **({"position": _scale_pos(u_pos.x, u_pos.y)} if u_pos else {}),
            })
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
        # Prefer d.mesh_unit (pre-computed by _apply_mesh_enrichment so it matches the
        # Devices table) and fall back to a live lookup in mesh_enrichment.
        parent_id = ""
        if mesh_units:
            try:
                from modules.deco_client import _norm_mac as _nm  # type: ignore[attr-defined]
                _munit = _attr(d, "mesh_unit", "") or ""
                if not _munit and mesh_enrichment:
                    mc = mesh_enrichment.get(_nm(mac))
                    if mc:
                        _munit = mc.unit_name
                if _munit:
                    for unit in mesh_units:
                        if getattr(unit, "name", "") == _munit:
                            if getattr(unit, "role", "") == "master":
                                # Master is merged into the gateway node (no separate
                                # Cytoscape node exists for it), so route to gw_id.
                                parent_id = gw_id
                            else:
                                parent_id = _nm(getattr(unit, "mac", "") or "") or getattr(unit, "name", "")
                            break
            except Exception:
                pass  # non-fatal

        # ── Traffic overlay ──────────────────────────────────────────────────
        bps = (bw_by_mac or {}).get(mac, 0.0)
        tc  = _bw_class(bps) if bw_by_mac is not None else ""
        if tc:
            classes += f" {tc}"
        bw_str = _bw_label(bps) if bps > 0 else ""

        node_label = f"{host[:16]}\n{ip}"
        if bw_str:
            node_label += f"\n{bw_str}"

        tip_text = f"{host}\n{ip}\n{mac or ''}\nRisk: {risk}"
        if bw_str:
            tip_text += f"\nTraffic: {bw_str}"

        node_pos = positions.get(dev_id) or positions.get(ip)
        nodes.append({
            "group": "nodes",
            "data": {
                "id":        dev_id,
                "label":     node_label,
                "ip":        ip,
                "mac":       mac,
                "risk":      risk,
                "vendor":    vendor,
                "tip":       tip_text,
                "seg_color": seg_color,
                "bw_mbps":   round(bps / 1_000_000, 3),
            },
            "classes": classes.strip(),
            **({"position": _scale_pos(node_pos.x, node_pos.y)} if node_pos else {}),
        })

        # Edge to gateway (or satellite parent when in a mesh).
        # ID encodes the *actual* source so incremental updateTopology() removes
        # the old flat edge (id="e-{gw_id}-…") and inserts the new satellite
        # edge (id="e-{sat_id}-…") — Cytoscape edges are source/target-immutable.
        src_id = parent_id if parent_id else gw_id
        cyto_edges.append({
            "group": "edges",
            "data": {
                "id":     f"e-{src_id}-{dev_id}",
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

