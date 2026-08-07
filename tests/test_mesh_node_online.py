"""MESH_DEGRADED's missing data source — per-node online state.

`evaluate_mesh_checks()` decides with `online_count < unit_count or
(worst_rssi is not None and worst_rssi < _MESH_WEAK_RSSI)`. Until this change
`MeshUnit` carried only (name, mac, ip, role) and the Deco plugin projected
the same four keys, so `online_count` could only ever equal `unit_count` and
`worst_rssi` was always None — the predicate was permanently False and the
rule could not fire, which is why acceptance criterion 5's mesh clause had no
code path at all.

The payloads below are the real `admin/device?form=device_list` response
captured live on 2026-08-06 from a 5-node Deco XE75 mesh, once with every node
up and once with the "Kitchen" satellite physically unplugged. That capture
settled the open design question: an unplugged node **stays in the list** with
`group_status: "disconnected"` rather than leaving it, so `online_count <
unit_count` is the correct shape and no rule change is needed — only the
projection. Note `signal_level` values are strings while connected and ints
once disconnected; nothing may assume the type.
"""
from __future__ import annotations

import pytest

from modules.deco_client import DecoMeshClient, MeshUnit


def _node(nickname, mac, ip, role, group_status, inet_status, signal_level):
    return {
        "nickname": nickname,
        "custom_nickname": "",
        "mac": mac,
        "device_ip": ip,
        "role": role,
        "group_status": group_status,
        "inet_status": inet_status,
        "signal_level": signal_level,
    }


_ALL_UP = [
    _node("Floor2 Vardagsrum", "60-83-E7-88-A6-C4", "192.168.71.249", "slave",
          "connected", "online", {"band5": "1", "band6": "1", "band2_4": "2"}),
    _node("Floor2 Kitchen", "60-83-E7-88-A0-B1", "192.168.71.250", "slave",
          "connected", "online", {"band5": "1", "band6": "1", "band2_4": "2"}),
    _node("Kontor", "3C-64-CF-E0-27-02", "192.168.68.1", "master",
          "connected", "online", {"band5": "0", "band6": "0", "band2_4": "0"}),
    _node("Vardagsrum", "60-83-E7-88-9F-11", "192.168.71.248", "slave",
          "connected", "online", {"band5": "2", "band6": "2", "band2_4": "2"}),
    _node("Kitchen", "60-83-E7-88-B2-33", "192.168.71.251", "slave",
          "connected", "online", {"band5": "1", "band6": "1", "band2_4": "1"}),
]

# Same mesh, "Kitchen" unplugged. Still five entries; device_ip goes None and
# signal_level flips from strings to ints.
_ONE_DOWN = _ALL_UP[:4] + [
    _node("Kitchen", "60-83-E7-88-B2-33", None, "slave",
          "disconnected", "offline", {"band5": 0, "band2_4": 0}),
]


def _client_returning(nodes):
    c = DecoMeshClient("192.168.68.1", "pw")
    c._request = lambda path, payload: {"device_list": nodes}  # type: ignore[method-assign]
    return c


def test_mesh_unit_carries_an_online_flag():
    """The dataclass must expose `online` — _mesh_field() reads it by name."""
    assert hasattr(MeshUnit("n", "m", "i", "master"), "online")


def test_every_node_online_when_all_are_connected():
    units = _client_returning(_ALL_UP).get_mesh_units()
    assert len(units) == 5
    assert all(u.online for u in units)
    assert sum(1 for u in units if u.online) == len(units)


def test_unplugged_node_is_reported_offline_and_stays_listed():
    units = _client_returning(_ONE_DOWN).get_mesh_units()
    # It must NOT vanish: the rule compares online_count against unit_count.
    assert len(units) == 5
    offline = [u for u in units if not u.online]
    assert len(offline) == 1
    assert offline[0].name == "Kitchen"
    assert sum(1 for u in units if u.online) == 4


def test_online_count_below_unit_count_is_what_mesh_degraded_needs():
    """The exact expression evaluate_mesh_checks() evaluates."""
    units = _client_returning(_ONE_DOWN).get_mesh_units()
    unit_count = len(units)
    online_count = sum(1 for u in units if u.online)
    assert online_count < unit_count

    healthy = _client_returning(_ALL_UP).get_mesh_units()
    assert sum(1 for u in healthy if u.online) == len(healthy)


def test_missing_group_status_is_treated_as_online():
    """A provider that does not report status must not manufacture an outage.

    Absent evidence is not evidence of absence — the whole program is about
    only claiming what is corroborated, and a firmware that omits the field
    would otherwise alert on every poll.
    """
    nodes = [{"nickname": "X", "mac": "AA-BB-CC-DD-EE-FF",
              "device_ip": "192.168.68.1", "role": "master"}]
    units = _client_returning(nodes).get_mesh_units()
    assert units[0].online is True


@pytest.mark.parametrize("status", ["disconnected", "offline", "", None])
def test_any_non_connected_group_status_is_offline(status):
    nodes = [_node("X", "AA-BB-CC-DD-EE-FF", None, "slave", status, "offline", {})]
    units = _client_returning(nodes).get_mesh_units()
    assert units[0].online is False


def test_deco_plugin_projects_online_into_its_node_dicts():
    """The plugin path is the one that actually runs in production.

    `_evaluate_and_log_mesh_health()` is fed from `_on_hardware_plugin_result`,
    i.e. the plugin's `extra["nodes"]` dicts — not MeshUnit objects — so
    projecting `online` on the dataclass alone would leave the live path
    exactly as dead as before.
    """
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "plugins" / "deco_plugin.py"
    spec = importlib.util.spec_from_file_location("_deco_plugin_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)

    units = _client_returning(_ONE_DOWN).get_mesh_units()
    mod._fetch_all = lambda: (units, [])  # type: ignore[attr-defined]

    nodes = mod.get_status()["extra"]["nodes"]
    assert len(nodes) == 5
    assert all("online" in n for n in nodes), "plugin dropped the online flag"
    assert sum(1 for n in nodes if n["online"]) == 4
