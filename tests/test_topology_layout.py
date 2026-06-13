"""Tests for modules/topology_layout.py — layout persistence for the topology map."""

import json
import pytest


# ── Import test ───────────────────────────────────────────────────────────────

def test_module_imports():
    import modules.topology_layout as _m
    assert hasattr(_m, "NodePosition")
    assert hasattr(_m, "load_layout")
    assert hasattr(_m, "save_layout")
    assert hasattr(_m, "clear_layout")
    assert hasattr(_m, "compute_scan_id")


# ── NodePosition dataclass ────────────────────────────────────────────────────

def test_node_position_defaults():
    from modules.topology_layout import NodePosition
    np = NodePosition(node_id="aa:bb:cc:dd:ee:ff", x=0.5, y=0.3)
    assert np.pinned is False


def test_node_position_pinned():
    from modules.topology_layout import NodePosition
    np = NodePosition(node_id="192.168.1.10", x=0.1, y=0.9, pinned=True)
    assert np.pinned is True


# ── compute_scan_id ───────────────────────────────────────────────────────────

def test_compute_scan_id_consistent():
    from modules.topology_layout import compute_scan_id
    devices = [
        {"ip": "192.168.1.10"},
        {"ip": "192.168.1.20"},
        {"ip": "10.0.0.5"},
    ]
    id1 = compute_scan_id(devices)
    id2 = compute_scan_id(list(reversed(devices)))
    assert id1 == id2, "scan_id must be order-independent"


def test_compute_scan_id_empty():
    from modules.topology_layout import compute_scan_id
    assert compute_scan_id([]) == "default"


def test_compute_scan_id_noise_ips():
    from modules.topology_layout import compute_scan_id
    devices = [{"ip": "0.0.0.0"}, {"ip": "?"}, {"ip": ""}]
    assert compute_scan_id(devices) == "default"


def test_compute_scan_id_groups_by_subnet():
    from modules.topology_layout import compute_scan_id
    few = [{"ip": "192.168.1.1"}, {"ip": "192.168.1.2"}]
    many = [{"ip": "192.168.1.1"}, {"ip": "192.168.1.200"}, {"ip": "192.168.1.99"}]
    # All on the same /24 — same signature regardless of host count
    assert compute_scan_id(few) == compute_scan_id(many)


# ── save_layout / load_layout round-trip ─────────────────────────────────────

@pytest.fixture
def tmp_layout_path(tmp_path, monkeypatch):
    """Redirect layout file to a temp directory."""
    layout_file = tmp_path / "topology_layout.json"
    monkeypatch.setattr(
        "modules.topology_layout._layout_path",
        lambda: layout_file,
    )
    return layout_file


def test_save_and_load_roundtrip(tmp_layout_path):
    from modules.topology_layout import NodePosition, load_layout, save_layout
    positions = {
        "aa:bb:cc:dd:ee:ff": NodePosition("aa:bb:cc:dd:ee:ff", 0.5, 0.3, pinned=False),
        "192.168.1.20":      NodePosition("192.168.1.20",      0.7, 0.8, pinned=True),
    }
    save_layout("test_id", positions)
    loaded = load_layout("test_id")
    assert set(loaded) == {"aa:bb:cc:dd:ee:ff", "192.168.1.20"}
    assert loaded["192.168.1.20"].pinned is True
    assert abs(loaded["aa:bb:cc:dd:ee:ff"].x - 0.5) < 1e-9


def test_load_missing_scan_id_returns_empty(tmp_layout_path):
    from modules.topology_layout import load_layout
    assert load_layout("nonexistent_id") == {}


def test_load_missing_file_returns_empty(tmp_layout_path):
    from modules.topology_layout import load_layout
    # tmp_layout_path doesn't exist yet → should return {}
    assert not tmp_layout_path.exists()
    assert load_layout("any") == {}


def test_multiple_scan_ids_coexist(tmp_layout_path):
    from modules.topology_layout import NodePosition, load_layout, save_layout
    pos_a = {"a": NodePosition("a", 0.1, 0.2)}
    pos_b = {"b": NodePosition("b", 0.9, 0.8)}
    save_layout("scan_a", pos_a)
    save_layout("scan_b", pos_b)
    assert "a" in load_layout("scan_a")
    assert "b" in load_layout("scan_b")
    assert "a" not in load_layout("scan_b")


def test_save_overwrites_existing_scan_id(tmp_layout_path):
    from modules.topology_layout import NodePosition, load_layout, save_layout
    pos1 = {"n1": NodePosition("n1", 0.1, 0.2)}
    pos2 = {"n2": NodePosition("n2", 0.8, 0.9)}
    save_layout("sid", pos1)
    save_layout("sid", pos2)
    loaded = load_layout("sid")
    assert "n1" not in loaded
    assert "n2" in loaded


# ── clear_layout ──────────────────────────────────────────────────────────────

def test_clear_layout_removes_entry(tmp_layout_path):
    from modules.topology_layout import NodePosition, clear_layout, load_layout, save_layout
    save_layout("to_clear", {"n": NodePosition("n", 0.5, 0.5)})
    save_layout("to_keep",  {"n": NodePosition("n", 0.1, 0.1)})
    clear_layout("to_clear")
    assert load_layout("to_clear") == {}
    assert "n" in load_layout("to_keep")  # other entry untouched


def test_clear_layout_noop_when_absent(tmp_layout_path):
    """clear_layout on a nonexistent id must not raise."""
    from modules.topology_layout import clear_layout
    clear_layout("does_not_exist")  # should not raise


# ── pruning behaviour ─────────────────────────────────────────────────────────

def test_pruning_keeps_recent_entries(tmp_layout_path):
    from modules.topology_layout import NodePosition, _MAX_SCAN_IDS, save_layout
    pos = {"n": NodePosition("n", 0.5, 0.5)}
    # Fill beyond the limit
    for i in range(_MAX_SCAN_IDS + 5):
        save_layout(f"scan_{i:04d}", pos)
    # File must not have more than _MAX_SCAN_IDS entries
    raw = json.loads(tmp_layout_path.read_text())
    assert len(raw) <= _MAX_SCAN_IDS
