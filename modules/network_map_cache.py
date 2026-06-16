"""
network_map_cache.py — Persists the inputs of the last live Network Map
render so the map looks identical across an app restart.

Without this cache, the startup "cache render" path (ui/scan_wiring.py
_restore_cached_scan) reconstructs a device list from DeviceTracker's known
devices with risk_level hard-reset to "UNKNOWN" and no mesh_unit/edge data —
so every node renders with the risk-unknown (grey) style and some devices
are mis-parented under the gateway instead of their mesh satellite, even
though the saved node *positions* (modules/topology_layout.py) already
survive a restart correctly. Caching the literal devices/gateway/modem/edges
last passed to NetworkMapPage.render() and replaying them verbatim at
startup closes that gap — same inputs in, same Cytoscape elements out.

Architecture rules:
  • Pure Python — no PyQt imports.
  • No direct DB writes — JSON file only, under get_app_data_dir() (ARCH RULE 23).
"""
from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any, Dict, List, Optional

from modules.topology_layout import TopologyEdge
from modules.utils import get_app_data_dir

log = logging.getLogger(__name__)

_CACHE_FILE = "network_map_render_cache.json"


def _to_dict(obj: Any) -> Dict[str, Any]:
    """Best-effort conversion of a device/edge entry to a plain JSON-safe dict."""
    if isinstance(obj, dict):
        return dict(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    # Generic object fallback (e.g. SimpleNamespace) — capture public attrs.
    return {k: v for k, v in vars(obj).items() if not k.startswith("_")}


def save_render_cache(
    devices: List[Any],
    gateway_ip: Optional[str],
    gateway_mac: Optional[str],
    modem_data: Optional[Dict[str, Any]],
    edges: Optional[List[Any]],
) -> None:
    """Persist the inputs of a live Network Map render.

    Called after every genuine live-scan render (ui/scan_wiring.py
    _on_m1_result). Never called from the startup cache-restore path itself,
    so a stale/degraded render can never get re-saved and propagate forward.
    """
    try:
        data = {
            "devices":     [_to_dict(d) for d in devices],
            "gateway_ip":  gateway_ip,
            "gateway_mac": gateway_mac,
            "modem_data":  modem_data if isinstance(modem_data, dict) else None,
            "edges":       [_to_dict(e) for e in edges] if edges else [],
        }
        (get_app_data_dir() / _CACHE_FILE).write_text(
            json.dumps(data), encoding="utf-8"
        )
    except Exception:
        log.debug("network_map_cache: save failed", exc_info=True)


def load_render_cache() -> Optional[Dict[str, Any]]:
    """Return the last saved live render inputs, or None if none/corrupt/empty.

    ``edges`` are reconstructed as real TopologyEdge instances because
    modules/topology_cytoscape.py reads edge fields via direct attribute
    access (e.g. ``e.dst_ip``), not the dict-or-getattr helper used for
    devices. ``devices`` are returned as plain dicts — topology_cytoscape.py
    reads every device field through its dict-or-getattr ``_attr()`` helper,
    so dicts round-trip through JSON with no loss of behaviour.
    """
    path = get_app_data_dir() / _CACHE_FILE
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.debug("network_map_cache: load failed", exc_info=True)
        return None

    devices = raw.get("devices") or []
    if not devices:
        return None

    edges = []
    for e in raw.get("edges") or []:
        try:
            edges.append(TopologyEdge(
                src_ip=e.get("src_ip", ""),
                dst_ip=e.get("dst_ip", ""),
                latency_ms=e.get("latency_ms"),
                packet_loss=e.get("packet_loss"),
                bandwidth_mbps=e.get("bandwidth_mbps"),
                status=e.get("status", "unknown"),
            ))
        except (TypeError, AttributeError):
            continue  # non-fatal — skip a malformed edge entry

    return {
        "devices":     devices,
        "gateway_ip":  raw.get("gateway_ip"),
        "gateway_mac": raw.get("gateway_mac"),
        "modem_data":  raw.get("modem_data"),
        "edges":       edges or None,
    }
