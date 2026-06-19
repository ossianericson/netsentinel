"""
topology_layouts.py — Deterministic geometric position engines for the Network Map.

Computes exact pixel (x, y) positions for all nodes so Cytoscape.js can use
layout: "preset" instead of a physics simulation.  Eliminates hairballs and
guarantees symmetric, equidistant spacing regardless of network size.

Three modes:
  geo_hierarchy  — strict top-down tree: Internet → Modem → Gateway → Mesh → Devices
  geo_concentric — rigid radial cluster: core at centre, inner ring (mesh),
                   outer ring (devices constrained to parent's angular slice)
  geo_grid       — uniform containment matrix: all nodes on a regular grid,
                   infrastructure-first ordering, 120 px centre-to-centre spacing

All functions accept the Cytoscape elements list produced by
topology_cytoscape.build_cytoscape_elements() and return a plain dict:
  { node_id: {"x": float, "y": float}, ... }  — pixel coords in Cytoscape canvas space

Architecture rules:
  • Pure Python — no PyQt imports.
  • No direct DB writes.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

# Reference canvas dimensions — must match _CANVAS_W/_CANVAS_H in topology_cytoscape.py
_CANVAS_W = 1400.0
_CANVAS_H = 900.0


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_graph(
    elements: List[dict],
) -> tuple:
    """Return (node_map, children_of) from a Cytoscape elements list.

    node_map:     { node_id: {"data": {...}, "classes": str} }
    children_of:  { parent_id: [child_id, ...] }  (derived from edge source→target)
    Ghost and hidden nodes are excluded from node_map.
    """
    node_map: Dict[str, dict] = {}
    for e in elements:
        if e.get("group") != "nodes":
            continue
        nid     = e["data"]["id"]
        classes = e.get("classes", "") or ""
        if "ghost" in classes or "hidden" in classes:
            continue
        node_map[nid] = {"data": e["data"], "classes": classes}

    children_of: Dict[str, List[str]] = {}
    for e in elements:
        if e.get("group") != "edges":
            continue
        src = e["data"].get("source", "")
        dst = e["data"].get("target", "")
        if dst in node_map:
            children_of.setdefault(src, []).append(dst)

    return node_map, children_of


def _node_label(node_map: dict, nid: str) -> str:
    return (node_map.get(nid) or {}).get("data", {}).get("label", nid) or nid


def _find_by_class(node_map: dict, css_class: str) -> Optional[str]:
    for nid, n in node_map.items():
        if css_class in n["classes"]:
            return nid
    return None


# ── Mode: Strict Hierarchical Tree ───────────────────────────────────────────

def _geo_hierarchy(
    elements: List[dict],
    canvas_w: float,
    canvas_h: float,
) -> Dict[str, Dict[str, float]]:
    """
    Level 0: Internet node            (centred)
    Level 1: Modem node if present    (centred)
    Level 2: Gateway / router         (centred)
    Level 3: Mesh satellites + devices directly attached to gateway (alphabetical)
    Level 4: Leaf devices grouped under their Level-3 parent (alphabetical, centred)

    H_PAD = 80 px between device centres at the same level.
    V_PAD = 150 px between successive levels.
    GRP_GAP = 30 px extra horizontal gap between distinct sub-trees.
    """
    H_PAD   = 80
    V_PAD   = 150
    GRP_GAP = 30

    node_map, children_of = _parse_graph(elements)
    if not node_map:
        return {}

    inet_id  = _find_by_class(node_map, "internet")
    modem_id = _find_by_class(node_map, "modem")
    gw_id    = _find_by_class(node_map, "gateway")

    def _lbl(nid: str) -> str:
        return _node_label(node_map, nid)

    # Level-3 nodes: children of the gateway, alphabetical
    level3 = sorted(children_of.get(gw_id or "", []), key=_lbl) if gw_id else []

    # Level-4 nodes: children of each level-3 node, alphabetical within parent group
    level4_by_parent: Dict[str, List[str]] = {}
    all_placed: set = set()
    if inet_id:  all_placed.add(inet_id)
    if modem_id: all_placed.add(modem_id)
    if gw_id:    all_placed.add(gw_id)
    all_placed.update(level3)

    for pid in level3:
        ch = [c for c in children_of.get(pid, []) if c in node_map and c not in all_placed]
        level4_by_parent[pid] = sorted(ch, key=_lbl)
        all_placed.update(ch)

    # Sub-tree width for a level-3 parent (drives horizontal span)
    def _subtree_w(pid: str) -> float:
        n = len(level4_by_parent.get(pid, []))
        return float(max(H_PAD, n * H_PAD))

    total_l3_span = sum(_subtree_w(p) for p in level3)
    if len(level3) > 1:
        total_l3_span += GRP_GAP * (len(level3) - 1)

    # Vertical layout: determine how many discrete levels exist
    fixed = [n for n in (inet_id, modem_id, gw_id) if n]
    has_l3 = bool(level3)
    has_l4 = any(level4_by_parent.values())
    n_levels = len(fixed) + (1 if has_l3 else 0) + (1 if has_l4 else 0)
    total_h  = (n_levels - 1) * V_PAD

    cx      = canvas_w / 2
    y_start = max(80.0, (canvas_h - total_h) / 2)

    positions: Dict[str, Dict[str, float]] = {}

    # Fixed top levels centred on canvas
    for i, nid in enumerate(fixed):
        positions[nid] = {"x": cx, "y": y_start + i * V_PAD}

    if not has_l3:
        return positions

    level3_y = y_start + len(fixed) * V_PAD

    # Assign level-3 x coords by sub-tree width
    x_cursor   = cx - total_l3_span / 2
    level3_x: Dict[str, float] = {}
    for pid in level3:
        sw = _subtree_w(pid)
        level3_x[pid] = x_cursor + sw / 2
        x_cursor += sw + GRP_GAP
        positions[pid] = {"x": level3_x[pid], "y": level3_y}

    if not has_l4:
        return positions

    level4_y = level3_y + V_PAD
    for pid in level3:
        ch = level4_by_parent[pid]
        if not ch:
            continue
        n   = len(ch)
        px  = level3_x[pid]
        x0  = px - (n - 1) * H_PAD / 2
        for j, cid in enumerate(ch):
            positions[cid] = {"x": x0 + j * H_PAD, "y": level4_y}

    return positions


# ── Mode: Balanced Concentric ─────────────────────────────────────────────────

def _geo_concentric(
    elements: List[dict],
    canvas_w: float,
    canvas_h: float,
) -> Dict[str, Dict[str, float]]:
    """
    Core (Internet → Modem → Gateway) stacked vertically at canvas centre.
    Inner ring (r = 220 px): Level-3 nodes (mesh + direct devices) at equal angular steps.
    Outer ring (r = 420 px): Leaf devices constrained to their parent's angular slice.
    Angular spread uses the full 360 / n_level3 slice per parent minus a 15% margin
    to prevent overlap with adjacent slices.
    """
    R1       = 220    # inner ring radius
    R2       = 420    # outer ring radius
    CORE_GAP = 50     # vertical gap between stacked core nodes

    node_map, children_of = _parse_graph(elements)
    if not node_map:
        return {}

    inet_id  = _find_by_class(node_map, "internet")
    modem_id = _find_by_class(node_map, "modem")
    gw_id    = _find_by_class(node_map, "gateway")

    def _lbl(nid: str) -> str:
        return _node_label(node_map, nid)

    cx, cy = canvas_w / 2, canvas_h / 2
    positions: Dict[str, Dict[str, float]] = {}

    # Core stack — vertically centred at canvas centre
    core = [n for n in (inet_id, modem_id, gw_id) if n]
    n_core = len(core)
    for i, nid in enumerate(core):
        offset = (i - (n_core - 1) / 2) * CORE_GAP
        positions[nid] = {"x": cx, "y": cy + offset}

    # Level-3 nodes on inner ring, alphabetical, equal angular spacing
    level3 = sorted(children_of.get(gw_id or "", []), key=_lbl) if gw_id else []
    n3 = len(level3)
    if n3 == 0:
        return positions

    angle_step  = 2 * math.pi / n3
    start_angle = -math.pi / 2   # top of circle

    level3_angles: Dict[str, float] = {}
    for i, pid in enumerate(level3):
        angle = start_angle + i * angle_step
        level3_angles[pid] = angle
        positions[pid] = {
            "x": cx + R1 * math.cos(angle),
            "y": cy + R1 * math.sin(angle),
        }

    # Level-4 nodes on outer ring, restricted to parent's angular slice
    half_slice = angle_step / 2
    for pid in level3:
        ch = sorted(
            [c for c in children_of.get(pid, []) if c in node_map],
            key=_lbl,
        )
        n_ch = len(ch)
        if not ch:
            continue
        parent_angle = level3_angles[pid]
        if n_ch == 1:
            angles = [parent_angle]
        else:
            # Distribute within 85% of the available angular slice
            spread = half_slice * 0.85
            angles = [
                parent_angle - spread + j * (2 * spread / (n_ch - 1))
                for j in range(n_ch)
            ]
        for j, cid in enumerate(ch):
            a = angles[j]
            positions[cid] = {
                "x": cx + R2 * math.cos(a),
                "y": cy + R2 * math.sin(a),
            }

    return positions


# ── Mode: Structured Grid Matrix ─────────────────────────────────────────────

def _geo_grid(
    elements: List[dict],
    canvas_w: float,
    canvas_h: float,
) -> Dict[str, Dict[str, float]]:
    """
    All nodes arranged in a uniform grid — infrastructure first, then alphabetical.
    Columns = ceil(sqrt(n)), rows = ceil(n / cols).
    H_GAP = V_GAP = 120 px (centre-to-centre), centred on the canvas.
    """
    H_GAP = 120
    V_GAP = 120

    _INFRA_RANK: Dict[str, int] = {
        "internet": 0,
        "modem":    1,
        "gateway":  2,
        "mesh-sat": 3,
    }

    node_map, _ = _parse_graph(elements)
    if not node_map:
        return {}

    def _rank(nid: str) -> int:
        classes = node_map[nid]["classes"]
        for key, rank in _INFRA_RANK.items():
            if key in classes:
                return rank
        return 10

    def _lbl(nid: str) -> str:
        return _node_label(node_map, nid)

    sorted_ids = sorted(node_map.keys(), key=lambda nid: (_rank(nid), _lbl(nid)))

    n    = len(sorted_ids)
    cols = max(1, math.ceil(math.sqrt(n)))
    rows = math.ceil(n / cols)

    total_w = (cols - 1) * H_GAP
    total_h = (rows - 1) * V_GAP
    x0      = (canvas_w - total_w) / 2
    y0      = (canvas_h - total_h) / 2

    positions: Dict[str, Dict[str, float]] = {}
    for i, nid in enumerate(sorted_ids):
        col = i % cols
        row = i // cols
        positions[nid] = {
            "x": x0 + col * H_GAP,
            "y": y0 + row  * V_GAP,
        }

    return positions


# ── Mode: Radial BFS Rings (Physics replacement) ──────────────────────────────

def _geo_radial(
    elements: List[dict],
    canvas_w: float,
    canvas_h: float,
) -> Dict[str, Dict[str, float]]:
    """
    BFS-ring layout — deterministic replacement for the force-directed Physics mode.

    Each node is placed on a ring whose radius corresponds to its graph distance
    (hop count) from the Internet node.  Nodes within a ring are distributed
    equidistantly around the full circle (no parent-slice constraint), giving an
    organic, spread-out appearance without physics simulation or hairballs.

    Ring radii (px): 0 (center/Internet), 130 (Modem), 240 (Gateway),
                     360 (mesh/direct), 480 (leaf devices), +120 per extra hop.
    """
    from collections import deque

    RING_RADII = [0, 130, 240, 360, 480]   # radius per BFS level
    EXTRA_STEP = 120                        # radius increment for deeper hops
    CORE_STACK = 45                         # vertical gap for stacked single-node levels

    node_map, children_of = _parse_graph(elements)
    if not node_map:
        return {}

    # BFS from Internet (or fallback to any root) to assign hop levels
    inet_id = _find_by_class(node_map, "internet")
    root    = inet_id or next(iter(node_map), None)
    if root is None:
        return {}

    level_of: Dict[str, int] = {root: 0}
    queue: deque = deque([root])
    while queue:
        cur = queue.popleft()
        for child in children_of.get(cur, []):
            if child not in level_of:
                level_of[child] = level_of[cur] + 1
                queue.append(child)

    # Any node not reachable from root (disconnected) goes one level past the deepest
    max_lvl = max(level_of.values()) if level_of else 0
    for nid in node_map:
        if nid not in level_of:
            level_of[nid] = max_lvl + 1

    # Group nodes by level, alphabetical within each level
    from collections import defaultdict
    level_groups: Dict[int, List[str]] = defaultdict(list)
    for nid, lvl in level_of.items():
        level_groups[lvl].append(nid)
    for lvl in level_groups:
        level_groups[lvl].sort(key=lambda n: _node_label(node_map, n))

    # Determine the maximum ring radius that will be used, then scale all radii
    # so the outermost ring stays within the canvas with a small margin.
    _MARGIN = 30.0
    max_r_used = 0.0
    for lvl in level_groups:
        if lvl == 0:
            continue
        if lvl < len(RING_RADII):
            _r = RING_RADII[lvl]
        else:
            _r = RING_RADII[-1] + (lvl - len(RING_RADII) + 1) * EXTRA_STEP
        max_r_used = max(max_r_used, float(_r))

    available_r = min(canvas_w / 2, canvas_h / 2) - _MARGIN
    _scale = (available_r / max_r_used) if max_r_used > available_r else 1.0

    cx, cy = canvas_w / 2, canvas_h / 2
    positions: Dict[str, Dict[str, float]] = {}

    for lvl, nodes_at_lvl in sorted(level_groups.items()):
        n = len(nodes_at_lvl)
        if n == 0:
            continue

        # Determine ring radius for this BFS level, scaled to fit canvas
        if lvl < len(RING_RADII):
            r = RING_RADII[lvl] * _scale
        else:
            r = (RING_RADII[-1] + (lvl - len(RING_RADII) + 1) * EXTRA_STEP) * _scale

        if r == 0 or n == 1:
            # Centre point or single node: stack vertically with small offset so
            # Internet / Modem / Gateway form a clean vertical column at the top.
            for i, nid in enumerate(nodes_at_lvl):
                if r == 0:
                    positions[nid] = {"x": cx, "y": cy}
                else:
                    # Single node on a non-zero ring: place at the top (−π/2)
                    positions[nid] = {
                        "x": cx,
                        "y": cy - r + i * CORE_STACK,
                    }
        else:
            # Multiple nodes: distribute equidistantly around the full ring
            start_angle = -math.pi / 2
            step        = 2 * math.pi / n
            for i, nid in enumerate(nodes_at_lvl):
                angle = start_angle + i * step
                positions[nid] = {
                    "x": cx + r * math.cos(angle),
                    "y": cy + r * math.sin(angle),
                }

    return positions


# ── Public entry point ────────────────────────────────────────────────────────

_MODE_FN: Dict[str, Any] = {
    "geo_hierarchy":  _geo_hierarchy,
    "geo_concentric": _geo_concentric,
    "geo_grid":       _geo_grid,
    "geo_radial":     _geo_radial,
}


def compute_geometric_positions(
    mode: str,
    elements: List[dict],
    canvas_w: float = _CANVAS_W,
    canvas_h: float = _CANVAS_H,
) -> Dict[str, Dict[str, float]]:
    """Compute deterministic pixel positions for all nodes.

    Args:
        mode:      One of "geo_hierarchy", "geo_concentric", "geo_grid", "geo_radial".
        elements:  List of Cytoscape element dicts from build_cytoscape_elements().
        canvas_w:  Reference canvas width in Cytoscape pixel space (default 1400).
        canvas_h:  Reference canvas height in Cytoscape pixel space (default 900).

    Returns:
        { node_id: {"x": float, "y": float} } — pixel coordinates.
        Nodes not present in the returned dict are left at their current position.
    """
    fn = _MODE_FN.get(mode)
    if fn is None:
        return {}
    try:
        return fn(elements, canvas_w, canvas_h)
    except Exception:
        return {}
