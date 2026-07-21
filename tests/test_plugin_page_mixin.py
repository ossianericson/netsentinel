"""
Regression tests for ui/plugin_page_mixin.py::_PluginPageMixin._check_hw_autodetect.

RULE-NET1: get_network_info() (modules/utils_net.py) initializes both "gateway"
and "gateway_mac" to None and only overwrites them on successful resolution --
a legitimate runtime state (VPN, flushed ARP cache, DHCP not yet leased), not a
bug. `_net_info.get(key, "")` still returns None when the key is present with an
explicit None value, so the original `.strip()` chained directly on the .get()
result raised AttributeError the moment gateway/gateway_mac hadn't resolved yet
-- the same bug shape that crashed ui/scan_enrichment.py in a live wild-chaos
monkey run (2026-07-21), see tests/test_scan_enrichment.py::
test_plugin_enrichment_handles_unresolved_gateway_mac.
"""
from ui.plugin_page_mixin import _PluginPageMixin


class _Stub(_PluginPageMixin):
    def __init__(self, net_info):
        self._net_info = net_info


def test_check_hw_autodetect_handles_unresolved_gateway_and_mac():
    """Both gateway and gateway_mac are None (fresh boot / not yet resolved) --
    must return cleanly instead of raising AttributeError on .strip()."""
    stub = _Stub({"gateway": None, "gateway_mac": None})
    stub._check_hw_autodetect()  # must not raise
    assert getattr(stub, "_hw_detect_last_gw", None) is None, \
        "gw_ip was falsy -- autodetect must bail out before touching the worker"


def test_check_hw_autodetect_handles_resolved_gateway_unresolved_mac(monkeypatch):
    """gateway resolved but gateway_mac still None (route known, ARP not yet
    resolved) -- the exact live-crash scenario. Must not raise on the
    gw_mac = ...strip() line, and must pass gateway_mac=None (not the string
    "None") on to the worker once gw_ip is truthy and detection proceeds.

    HwDetectWorker is a real QThread -- swap in a lightweight fake so this
    test exercises the None-guard without spinning a background thread.
    """
    class _FakeSignal:
        def connect(self, *_a, **_kw):
            pass

    class _FakeWorker:
        def __init__(self, ip, gateway_mac, parent=None):
            self.ip = ip
            self.gateway_mac = gateway_mac
            self.detected = _FakeSignal()
            self.error = _FakeSignal()

        def isRunning(self):
            return False

        def start(self):
            pass

    monkeypatch.setattr("workers.hw_detect_worker.HwDetectWorker", _FakeWorker)

    stub = _Stub({"gateway": "192.168.1.1", "gateway_mac": None})
    stub._check_hw_autodetect()  # must not raise on the gw_mac = ...strip() line

    assert stub._hw_detect_worker.gateway_mac is None
