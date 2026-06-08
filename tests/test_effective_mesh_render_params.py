"""
Regression tests for _effective_mesh_render_params().

Bug fixed: modem poll handler called topology.render() with
mesh_units/mesh_enrichment from native MeshWorker only — ignoring plugin
enrichment data.  For plugin-only mesh users (Deco plugin, any router/ap/mesh
plugin) this re-rendered a flat topology every ~30 s, losing all node labels.

These tests verify that the helper returns plugin-sourced params when no native
MeshWorker data is present, and that it prefers native data when both are set.
"""
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Minimal stub that satisfies _effective_mesh_render_params()
# ---------------------------------------------------------------------------

class _Stub:
    """Provides just the attributes the helper reads."""
    def __init__(self):
        self._plugin_enrichments: dict = {}
        self._plugin_nodes:       dict = {}
        self._mesh_units        = None
        self._mesh_enrichment   = {}

    # attach the real method
    from ui.scan_enrichment import ScanEnrichmentMixin
    _effective_mesh_render_params = ScanEnrichmentMixin._effective_mesh_render_params


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_data_returns_none_none():
    """With no enrichment at all both values are None / falsy."""
    s = _Stub()
    units, enrich = s._effective_mesh_render_params()
    assert units is None
    assert not enrich


def test_plugin_only_mesh_returns_nodes_and_enrich():
    """Plugin data is used when native MeshWorker data is absent."""
    s = _Stub()
    # Simulate Deco plugin registering one satellite node and two clients
    s._plugin_nodes["inst-1"] = [
        {"name": "Deco-Lounge", "role": "satellite", "mac": "AA:BB:CC:DD:EE:FF"},
    ]
    s._plugin_enrichments["inst-1"] = {
        "aabbccddeeff": {"mac": "AA:BB:CC:DD:EE:FF", "ip": "192.168.1.10",
                         "hostname": "laptop", "band": "5GHz", "unit": "Deco-Lounge"},
        "112233445566": {"mac": "11:22:33:44:55:66", "ip": "192.168.1.11",
                         "hostname": "phone",  "band": "2.4GHz", "unit": ""},
    }

    units, enrich = s._effective_mesh_render_params()

    # Must return at least one node
    assert units and len(units) == 1
    assert units[0].name == "Deco-Lounge"

    # Must return enrichment entries for both clients
    assert "aabbccddeeff" in enrich
    assert enrich["aabbccddeeff"].name == "laptop"
    assert "112233445566" in enrich
    # Single-node fallback: unit_name defaults to node name
    assert enrich["112233445566"].unit_name == "Deco-Lounge"


def test_native_mesh_preferred_over_plugin():
    """Native MeshWorker data takes priority when present."""
    s = _Stub()
    # Native data
    native_unit = SimpleNamespace(name="NativeAP", mac="00:11:22:33:44:55",
                                  online=True, role="primary")
    s._mesh_units      = [native_unit]
    s._mesh_enrichment = {"001122334455": SimpleNamespace(
        mac="00:11:22:33:44:55", ip="192.168.1.1", name="router",
        unit_name="", band="5GHz", upload_kbps=0, download_kbps=0,
    )}
    # Plugin data (should be ignored when native is present)
    s._plugin_nodes["inst-1"] = [
        {"name": "PluginNode", "role": "satellite", "mac": "AA:BB:CC:DD:EE:FF"},
    ]
    s._plugin_enrichments["inst-1"] = {
        "aabbccddeeff": {"mac": "AA:BB:CC:DD:EE:FF", "ip": "10.0.0.5",
                         "hostname": "plugin-device", "band": "2.4GHz", "unit": ""},
    }

    units, enrich = s._effective_mesh_render_params()

    assert units is s._mesh_units
    assert "001122334455" in enrich


def test_multiple_plugin_instances_merged():
    """Client data from multiple plugin instances is merged."""
    s = _Stub()
    s._plugin_nodes["inst-1"] = [
        {"name": "AP-North", "role": "primary", "mac": "AA:BB:CC:00:00:01"},
    ]
    s._plugin_nodes["inst-2"] = [
        {"name": "AP-South", "role": "satellite", "mac": "AA:BB:CC:00:00:02"},
    ]
    s._plugin_enrichments["inst-1"] = {
        "001122334401": {"mac": "00:11:22:33:44:01", "ip": "10.0.0.2",
                         "hostname": "dev-a", "band": "5GHz", "unit": "AP-North"},
    }
    s._plugin_enrichments["inst-2"] = {
        "001122334402": {"mac": "00:11:22:33:44:02", "ip": "10.0.0.3",
                         "hostname": "dev-b", "band": "2.4GHz", "unit": "AP-South"},
    }

    units, enrich = s._effective_mesh_render_params()

    assert len(units) == 2
    assert "001122334401" in enrich
    assert "001122334402" in enrich
