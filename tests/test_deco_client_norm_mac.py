"""
Regression test for modules/deco_client.py::_norm_mac.

_norm_mac() must tolerate a None MAC. get_network_info() (modules/utils_net.py)
initializes both "gateway" and "gateway_mac" to None and only overwrites them on
a successful ARP resolution -- a legitimate runtime state, not a bug -- so any
caller that does `net_info.get("gateway_mac", "")` still gets None back when the
key is present with an explicit None value (dict.get's default only applies when
the key is absent). This crashed a live wild-chaos monkey run (2026-07-21) via
ui/scan_enrichment.py's _on_hardware_plugin_result -> _norm_mac(None).

Kept separate from tests/test_deco_client.py, which is fully skipped unless a
real Deco router is reachable (module-level pytestmark) -- this test must
always run in CI.
"""
from modules.deco_client import _norm_mac


def test_norm_mac_handles_none():
    assert _norm_mac(None) == ""


def test_norm_mac_handles_empty_string():
    assert _norm_mac("") == ""


def test_norm_mac_normalizes_real_mac():
    assert _norm_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"
