"""Tests for modules/topology_layouts.py — geometric layout position engines."""
import math

from modules.topology_layouts import compute_geometric_positions, _CANVAS_W, _CANVAS_H


# ── Shared fixture builders ───────────────────────────────────────────────────

def _node(nid: str, classes: str, label: str = "") -> dict:
    return {
        "group": "nodes",
        "data": {"id": nid, "label": label or nid, "ip": ""},
        "classes": classes,
    }


def _edge(src: str, dst: str) -> dict:
    return {
        "group": "edges",
        "data": {"id": f"e-{src}-{dst}", "source": src, "target": dst},
        "classes": "arp-edge",
    }


def _minimal_topology():
    """Internet → Gateway → 2 leaf devices."""
    return [
        _node("__internet__", "internet",   "Internet"),
        _node("192.168.1.1",  "gateway",    "Gateway"),
        _node("192.168.1.10", "risk-clean", "DeviceA"),
        _node("192.168.1.11", "risk-clean", "DeviceB"),
        _edge("__internet__", "192.168.1.1"),
        _edge("192.168.1.1",  "192.168.1.10"),
        _edge("192.168.1.1",  "192.168.1.11"),
    ]


def _mesh_topology():
    """Internet → Modem → Gateway → 2 Mesh Satellites → 2 devices each."""
    elements = [
        _node("__internet__", "internet",  "Internet"),
        _node("__modem__",    "modem",     "5G Modem"),
        _node("192.168.1.1",  "gateway",   "Gateway"),
        _node("sat-a",        "mesh-sat",  "Mesh-A"),
        _node("sat-b",        "mesh-sat",  "Mesh-B"),
        _node("192.168.1.10", "risk-clean", "Client1"),
        _node("192.168.1.11", "risk-clean", "Client2"),
        _node("192.168.1.20", "risk-clean", "Client3"),
        _node("192.168.1.21", "risk-clean", "Client4"),
        _edge("__internet__", "__modem__"),
        _edge("__modem__",    "192.168.1.1"),
        _edge("192.168.1.1",  "sat-a"),
        _edge("192.168.1.1",  "sat-b"),
        _edge("sat-a",        "192.168.1.10"),
        _edge("sat-a",        "192.168.1.11"),
        _edge("sat-b",        "192.168.1.20"),
        _edge("sat-b",        "192.168.1.21"),
    ]
    return elements


# ── Unknown mode ──────────────────────────────────────────────────────────────

def test_unknown_mode_returns_empty_all_four():
    for mode in ("geo_hierarchy", "geo_concentric", "geo_grid", "geo_radial"):
        pos = compute_geometric_positions(mode, _mesh_topology())
        assert pos, f"{mode} returned empty on valid topology"


def test_unknown_mode_returns_empty():
    positions = compute_geometric_positions("unknown_mode", _minimal_topology())
    assert positions == {}


def test_empty_elements_returns_empty():
    for mode in ("geo_hierarchy", "geo_concentric", "geo_grid"):
        assert compute_geometric_positions(mode, []) == {}


# ── geo_hierarchy ─────────────────────────────────────────────────────────────

class TestHierarchy:
    def test_all_nodes_positioned(self):
        elems = _mesh_topology()
        node_ids = {e["data"]["id"] for e in elems if e["group"] == "nodes"}
        pos = compute_geometric_positions("geo_hierarchy", elems)
        assert node_ids == set(pos.keys())

    def test_within_canvas(self):
        pos = compute_geometric_positions("geo_hierarchy", _mesh_topology())
        for nid, p in pos.items():
            assert 0 <= p["x"] <= _CANVAS_W, f"{nid} x={p['x']} out of range"
            assert 0 <= p["y"] <= _CANVAS_H, f"{nid} y={p['y']} out of range"

    def test_vertical_level_ordering(self):
        """Internet < Modem < Gateway < Mesh < Leaves (by y coordinate)."""
        pos = compute_geometric_positions("geo_hierarchy", _mesh_topology())
        assert pos["__internet__"]["y"] < pos["__modem__"]["y"]
        assert pos["__modem__"]["y"]    < pos["192.168.1.1"]["y"]
        assert pos["192.168.1.1"]["y"]  < pos["sat-a"]["y"]
        # At least one leaf must be below a satellite
        assert pos["sat-a"]["y"] < pos["192.168.1.10"]["y"]

    def test_internet_modem_gateway_centred_x(self):
        """Top-level fixed nodes should be on the horizontal centre line."""
        pos = compute_geometric_positions("geo_hierarchy", _mesh_topology())
        cx = _CANVAS_W / 2
        assert abs(pos["__internet__"]["x"] - cx) < 1.0
        assert abs(pos["__modem__"]["x"]    - cx) < 1.0
        assert abs(pos["192.168.1.1"]["x"]  - cx) < 1.0

    def test_leaves_centred_under_parent(self):
        """Client1 and Client2 should be symmetric around sat-a's x."""
        pos = compute_geometric_positions("geo_hierarchy", _mesh_topology())
        sat_a_x = pos["sat-a"]["x"]
        c1_x = pos["192.168.1.10"]["x"]
        c2_x = pos["192.168.1.11"]["x"]
        # midpoint of the two children should equal parent x (within 1 px)
        midpoint = (c1_x + c2_x) / 2
        assert abs(midpoint - sat_a_x) < 1.0

    def test_no_modem_still_works(self):
        """Topology without a modem should still place all nodes."""
        elems = _minimal_topology()
        node_ids = {e["data"]["id"] for e in elems if e["group"] == "nodes"}
        pos = compute_geometric_positions("geo_hierarchy", elems)
        assert node_ids == set(pos.keys())

    def test_ghost_nodes_excluded(self):
        elems = _minimal_topology() + [
            _node("ghost-192.168.1.99", "ghost hidden", "(gone)")
        ]
        pos = compute_geometric_positions("geo_hierarchy", elems)
        assert "ghost-192.168.1.99" not in pos

    def test_leaf_horizontal_spacing(self):
        """H_PAD = 80: two leaves under a parent must be exactly 80 px apart."""
        pos = compute_geometric_positions("geo_hierarchy", _mesh_topology())
        c1_x = pos["192.168.1.10"]["x"]
        c2_x = pos["192.168.1.11"]["x"]
        assert abs(abs(c2_x - c1_x) - 80.0) < 1.0


# ── geo_concentric ────────────────────────────────────────────────────────────

class TestConcentric:
    def test_all_nodes_positioned(self):
        elems = _mesh_topology()
        node_ids = {e["data"]["id"] for e in elems if e["group"] == "nodes"}
        pos = compute_geometric_positions("geo_concentric", elems)
        assert node_ids == set(pos.keys())

    def test_within_canvas(self):
        pos = compute_geometric_positions("geo_concentric", _mesh_topology())
        for nid, p in pos.items():
            assert 0 <= p["x"] <= _CANVAS_W, f"{nid} x={p['x']} out of range"
            assert 0 <= p["y"] <= _CANVAS_H, f"{nid} y={p['y']} out of range"

    def test_core_near_centre(self):
        """Internet, Modem, Gateway should be within 200 px of canvas centre."""
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        pos = compute_geometric_positions("geo_concentric", _mesh_topology())
        for nid in ("__internet__", "__modem__", "192.168.1.1"):
            d = math.hypot(pos[nid]["x"] - cx, pos[nid]["y"] - cy)
            assert d < 200, f"{nid} is too far from centre: {d:.1f} px"

    def test_mesh_nodes_on_inner_ring(self):
        """Mesh satellites must be at radius ≈ 220 from the canvas centre."""
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        pos = compute_geometric_positions("geo_concentric", _mesh_topology())
        r_target = 220
        for nid in ("sat-a", "sat-b"):
            r = math.hypot(pos[nid]["x"] - cx, pos[nid]["y"] - cy)
            assert abs(r - r_target) < 5.0, f"{nid} inner radius {r:.1f} != {r_target}"

    def test_leaves_on_outer_ring(self):
        """Leaf devices must be at radius ≈ 420 from the canvas centre."""
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        pos = compute_geometric_positions("geo_concentric", _mesh_topology())
        r_target = 420
        for nid in ("192.168.1.10", "192.168.1.11", "192.168.1.20", "192.168.1.21"):
            r = math.hypot(pos[nid]["x"] - cx, pos[nid]["y"] - cy)
            assert abs(r - r_target) < 5.0, f"{nid} outer radius {r:.1f} != {r_target}"

    def test_children_within_parent_slice(self):
        """Each leaf's angle must lie within its parent satellite's angular slice."""
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        pos = compute_geometric_positions("geo_concentric", _mesh_topology())

        n3         = 2  # sat-a and sat-b
        slice_half = math.pi / n3  # 180° total slice per parent; half = 90°

        for sat, children in [
            ("sat-a", ["192.168.1.10", "192.168.1.11"]),
            ("sat-b", ["192.168.1.20", "192.168.1.21"]),
        ]:
            parent_angle = math.atan2(pos[sat]["y"] - cy, pos[sat]["x"] - cx)
            for cid in children:
                child_angle = math.atan2(pos[cid]["y"] - cy, pos[cid]["x"] - cx)
                delta = abs(child_angle - parent_angle)
                # wrap-around: pick the smaller angular difference
                delta = min(delta, 2 * math.pi - delta)
                assert delta <= slice_half + 0.01, (
                    f"{cid} angle delta {math.degrees(delta):.1f}° "
                    f"exceeds parent slice {math.degrees(slice_half):.1f}°"
                )

    def test_equal_angular_spacing_on_inner_ring(self):
        """Two mesh satellites must be 180° apart (360°/2 = 180°)."""
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        pos = compute_geometric_positions("geo_concentric", _mesh_topology())
        a_a = math.atan2(pos["sat-a"]["y"] - cy, pos["sat-a"]["x"] - cx)
        a_b = math.atan2(pos["sat-b"]["y"] - cy, pos["sat-b"]["x"] - cx)
        delta = abs(a_b - a_a)
        delta = min(delta, 2 * math.pi - delta)
        assert abs(math.degrees(delta) - 180.0) < 1.0


# ── geo_grid ──────────────────────────────────────────────────────────────────

class TestGrid:
    def test_all_nodes_positioned(self):
        elems = _mesh_topology()
        node_ids = {e["data"]["id"] for e in elems if e["group"] == "nodes"}
        pos = compute_geometric_positions("geo_grid", elems)
        assert node_ids == set(pos.keys())

    def test_within_canvas(self):
        pos = compute_geometric_positions("geo_grid", _mesh_topology())
        for nid, p in pos.items():
            assert 0 <= p["x"] <= _CANVAS_W, f"{nid} x={p['x']} out of range"
            assert 0 <= p["y"] <= _CANVAS_H, f"{nid} y={p['y']} out of range"

    def test_uniform_spacing(self):
        """All adjacent nodes in the same row must share the same H_GAP."""
        elems = _mesh_topology()
        pos = compute_geometric_positions("geo_grid", elems)
        n = len(pos)
        cols = max(1, math.ceil(math.sqrt(n)))
        # Collect unique x values (there should be exactly `cols` of them)
        x_vals = sorted({round(p["x"], 1) for p in pos.values()})
        assert len(x_vals) == cols
        # All x gaps must be equal
        gaps = [x_vals[i + 1] - x_vals[i] for i in range(len(x_vals) - 1)]
        if gaps:
            assert all(abs(g - gaps[0]) < 1.0 for g in gaps), f"Unequal x gaps: {gaps}"

    def test_infrastructure_ordered_first(self):
        """Internet must appear in the first row/column of the grid."""
        pos = compute_geometric_positions("geo_grid", _mesh_topology())
        # Internet should have the smallest y value (first row) or at least
        # a y value equal to the minimum y across all nodes.
        min_y = min(p["y"] for p in pos.values())
        assert abs(pos["__internet__"]["y"] - min_y) < 1.0

    def test_no_node_overlap(self):
        """No two nodes should occupy the same grid cell (position)."""
        pos = compute_geometric_positions("geo_grid", _mesh_topology())
        seen: set = set()
        for nid, p in pos.items():
            cell = (round(p["x"], 1), round(p["y"], 1))
            assert cell not in seen, f"Overlap at {cell}: {nid}"
            seen.add(cell)

    def test_ghost_nodes_excluded(self):
        elems = _mesh_topology() + [
            _node("ghost-192.168.1.99", "ghost hidden", "(gone)")
        ]
        pos = compute_geometric_positions("geo_grid", elems)
        assert "ghost-192.168.1.99" not in pos


# ── geo_radial ────────────────────────────────────────────────────────────────

class TestRadial:
    def test_all_nodes_positioned(self):
        elems = _mesh_topology()
        node_ids = {e["data"]["id"] for e in elems if e["group"] == "nodes"}
        pos = compute_geometric_positions("geo_radial", elems)
        assert node_ids == set(pos.keys())

    def test_within_canvas(self):
        pos = compute_geometric_positions("geo_radial", _mesh_topology())
        for nid, p in pos.items():
            assert 0 <= p["x"] <= _CANVAS_W, f"{nid} x={p['x']} out of range"
            assert 0 <= p["y"] <= _CANVAS_H, f"{nid} y={p['y']} out of range"

    def test_internet_at_centre(self):
        pos = compute_geometric_positions("geo_radial", _mesh_topology())
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        assert abs(pos["__internet__"]["x"] - cx) < 1.0
        assert abs(pos["__internet__"]["y"] - cy) < 1.0

    def test_bfs_ring_ordering(self):
        """Nodes farther from Internet must be on larger-radius rings."""
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        pos = compute_geometric_positions("geo_radial", _mesh_topology())
        r_inet  = math.hypot(pos["__internet__"]["x"] - cx, pos["__internet__"]["y"] - cy)
        r_modem = math.hypot(pos["__modem__"]["x"]    - cx, pos["__modem__"]["y"]    - cy)
        r_gw    = math.hypot(pos["192.168.1.1"]["x"]  - cx, pos["192.168.1.1"]["y"]  - cy)
        r_sat   = math.hypot(pos["sat-a"]["x"]        - cx, pos["sat-a"]["y"]        - cy)
        r_leaf  = math.hypot(pos["192.168.1.10"]["x"] - cx, pos["192.168.1.10"]["y"] - cy)
        assert r_inet  < r_modem
        assert r_modem < r_gw
        assert r_gw    < r_sat
        assert r_sat   < r_leaf

    def test_no_node_overlap(self):
        """No two nodes should land on the exact same position."""
        pos = compute_geometric_positions("geo_radial", _mesh_topology())
        seen: set = set()
        for nid, p in pos.items():
            cell = (round(p["x"], 1), round(p["y"], 1))
            assert cell not in seen, f"Overlap at {cell}: {nid}"
            seen.add(cell)

    def test_leaf_nodes_equidistant_on_ring(self):
        """All 4 leaf devices are on the same ring; angular spacing must be equal."""
        cx, cy = _CANVAS_W / 2, _CANVAS_H / 2
        pos    = compute_geometric_positions("geo_radial", _mesh_topology())
        leaf_ids = ["192.168.1.10", "192.168.1.11", "192.168.1.20", "192.168.1.21"]
        angles = [
            math.atan2(pos[nid]["y"] - cy, pos[nid]["x"] - cx)
            for nid in leaf_ids
        ]
        angles_sorted = sorted(angles)
        # All 4 nodes should be at 90° intervals (4 nodes on full ring)
        expected_step = 2 * math.pi / len(leaf_ids)
        gaps = [
            (angles_sorted[i + 1] - angles_sorted[i]) % (2 * math.pi)
            for i in range(len(angles_sorted) - 1)
        ]
        for gap in gaps:
            assert abs(gap - expected_step) < 0.05, f"Non-uniform angular gap: {math.degrees(gap):.1f}°"

    def test_ghost_nodes_excluded(self):
        elems = _mesh_topology() + [
            _node("ghost-192.168.1.99", "ghost hidden", "(gone)")
        ]
        pos = compute_geometric_positions("geo_radial", elems)
        assert "ghost-192.168.1.99" not in pos

    def test_minimal_topology(self):
        """Works without modem and with direct devices only."""
        elems = _minimal_topology()
        node_ids = {e["data"]["id"] for e in elems if e["group"] == "nodes"}
        pos = compute_geometric_positions("geo_radial", elems)
        assert node_ids == set(pos.keys())
