"""
Regression test for _restore_cached_scan() feeding the Network Map.

Bug fixed: at startup, _restore_cached_scan() fed NetworkMapPage.render()
with a device list reconstructed from DeviceTracker's known devices, where
risk_level is intentionally hard-reset to "UNKNOWN" (correct for the
Inventory table — stale risk shouldn't look current) and mesh_unit is never
set. Because Network Map node colour/shape and mesh-satellite parenting both
read risk_level/mesh_unit, the map rendered every node grey and some devices
flat off the gateway instead of matching how the map looked when the app was
last closed — even though saved node *positions* already survived a restart.

These tests verify _restore_cached_scan() prefers a cached live-render
(modules/network_map_cache.py) when one exists, and falls back to the
existing DeviceTracker reconstruction when it does not (e.g. first run).

Also covers a second bug found by live end-to-end verification (screenshots
before/after a real app restart): self._m1_result["devices"] itself kept the
UNKNOWN-risk reconstruction even when a render cache was used for the first
Network Map render, so a *later* re-render triggered from self._m1_result
(e.g. _on_modem_signal in ui/dashboard.py, mesh-enrichment updates in
ui/scan_enrichment.py) silently reverted the map to the grey/flat appearance
a few seconds after startup. self._m1_result["devices"] must also prefer the
cached classification.
"""
from types import SimpleNamespace

from ui.scan_wiring import ScanResultMixin


class _NetworkMapStub:
    """Records every render() call so tests can inspect what was fed in."""

    def __init__(self):
        self.render_calls: list = []
        self._stale_label = SimpleNamespace(setVisible=lambda *_a, **_kw: None)

    def render(self, **kwargs):
        self.render_calls.append(kwargs)


class _WidgetStub:
    """Weakref-able stub — themed_ss registers the status label in a
    WeakKeyDictionary, and SimpleNamespace cannot be weakly referenced."""

    def __init__(self, **methods):
        self.__dict__.update(methods)


class _Stub:
    """Minimal object satisfying _restore_cached_scan()'s attribute reads."""

    _restore_cached_scan = ScanResultMixin._restore_cached_scan

    def __init__(self, store):
        self._store = store
        self._m1_table = SimpleNamespace(
            setRowCount=lambda *_a: None,
            setColumnHidden=lambda *_a: None,
        )
        self._m1_status = _WidgetStub(
            setText=lambda *_a: None, setStyleSheet=lambda *_a: None,
        )
        self._network_map_page = _NetworkMapStub()

    def _cached_scan_age_str(self, _store) -> str:
        return "2 hours ago"


def _make_known_device(ip: str) -> SimpleNamespace:
    return SimpleNamespace(
        ip=ip, custom_name="", hostname="laptop", mac=f"aa:bb:cc:dd:ee:{ip[-2:]}",
        vendor="Dell", last_seen=10_000_000_000, is_pinned=True,
        device_type="Workstation", inferred_role="client", scan_count=5,
        ip_stability=1.0,
    )


def _fake_store(known: dict):
    return SimpleNamespace(get_known_devices=lambda: known)


def _patch_app_data_dir(monkeypatch, tmp_path):
    """Both the inline mesh-cache lookup and modules.network_map_cache
    resolve get_app_data_dir() independently — redirect both."""
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr("modules.network_map_cache.get_app_data_dir", lambda: tmp_path)


def test_falls_back_to_unknown_risk_when_no_render_cache(tmp_path, monkeypatch):
    """First run / pre-fix behaviour: no network_map_render_cache.json yet."""
    _patch_app_data_dir(monkeypatch, tmp_path)
    monkeypatch.setattr("ui.scan_wiring._add_row", lambda *_a, **_kw: None)
    known = {"192.168.1.10": _make_known_device("192.168.1.10")}
    stub = _Stub(_fake_store(known))

    stub._restore_cached_scan()

    calls = stub._network_map_page.render_calls
    assert len(calls) == 1
    rendered_devices = calls[0]["devices"]
    assert rendered_devices[0]["risk_level"] == "UNKNOWN"
    assert "mesh_unit" not in rendered_devices[0]
    # self._m1_result must match what the Inventory table shows when no
    # render cache exists — both are the UNKNOWN-risk reconstruction.
    assert stub._m1_result["devices"][0]["risk_level"] == "UNKNOWN"


def test_uses_cached_live_render_when_present(tmp_path, monkeypatch):
    """With a saved live render, the Network Map gets the real classification
    (risk_level, mesh_unit) instead of the lossy UNKNOWN reconstruction."""
    _patch_app_data_dir(monkeypatch, tmp_path)
    monkeypatch.setattr("ui.scan_wiring._add_row", lambda *_a, **_kw: None)
    from modules.network_map_cache import save_render_cache

    save_render_cache(
        devices=[{
            "ip": "192.168.1.10", "mac": "aa:bb:cc:dd:ee:10", "risk_level": "HIGH",
            "device_type": "IP Camera", "mesh_unit": "Kitchen",
        }],
        gateway_ip="192.168.1.1", gateway_mac="aa:bb:cc:dd:ee:01",
        modem_data=None, edges=None,
    )

    known = {"192.168.1.10": _make_known_device("192.168.1.10")}
    stub = _Stub(_fake_store(known))

    stub._restore_cached_scan()

    calls = stub._network_map_page.render_calls
    assert len(calls) == 1
    rendered_devices = calls[0]["devices"]
    assert rendered_devices[0]["risk_level"] == "HIGH"
    assert rendered_devices[0]["mesh_unit"] == "Kitchen"
    assert calls[0]["gateway_ip"] == "192.168.1.1"
    assert calls[0]["gateway_mac"] == "aa:bb:cc:dd:ee:01"

    # self._m1_result must ALSO carry the cached classification — any later
    # re-render path that reads self._m1_result["devices"] (modem signal,
    # mesh enrichment) must not regress back to UNKNOWN-risk grey nodes.
    m1_devices = stub._m1_result["devices"]
    assert m1_devices[0]["risk_level"] == "HIGH"
    assert m1_devices[0]["mesh_unit"] == "Kitchen"


def test_inventory_gets_map_cache_data_on_startup(tmp_path, monkeypatch):
    """Regression: Inventory page must receive map-cache rich data on restart.

    Bug: Inventory page received the DB reconstruction (hostname/vendor/device_type
    often NULL) while the Network Map correctly received _map_cache["devices"].
    Fix: Inventory page now also prefers _map_cache["devices"] when available.
    """
    _patch_app_data_dir(monkeypatch, tmp_path)
    monkeypatch.setattr("ui.scan_wiring._add_row", lambda *_a, **_kw: None)
    from modules.network_map_cache import save_render_cache

    save_render_cache(
        devices=[{
            "ip": "192.168.1.20", "mac": "aa:bb:cc:dd:ee:20",
            "hostname": "my-laptop", "vendor": "Dell Inc.",
            "device_type": "Workstation", "risk_level": "LOW",
        }],
        gateway_ip="192.168.1.1", gateway_mac="aa:bb:cc:dd:ee:01",
        modem_data=None, edges=None,
    )

    # DB reconstruction has NULL hostname/vendor (common on first-seen devices)
    known = {"192.168.1.20": SimpleNamespace(
        ip="192.168.1.20", custom_name="", hostname=None, mac="aa:bb:cc:dd:ee:20",
        vendor=None, last_seen=10_000_000_000, is_pinned=False,
        device_type=None, inferred_role="client", scan_count=1, ip_stability=0.5,
    )}
    inv_calls: list = []
    stub = _Stub(_fake_store(known))
    stub._inventory_page = SimpleNamespace(
        set_scan_devices=lambda devs: inv_calls.append(devs)
    )

    stub._restore_cached_scan()

    assert inv_calls, "set_scan_devices was never called"
    inv_devices = inv_calls[0]
    assert len(inv_devices) == 1
    d = inv_devices[0]
    assert d["hostname"] == "my-laptop", "Inventory must show hostname from map cache"
    assert d["vendor"]   == "Dell Inc.", "Inventory must show vendor from map cache"
    assert d["device_type"] == "Workstation", "Inventory must show device_type from map cache"
    # Freshness dot must be injected (device seen recently → cached)
    assert d.get("display_state") in ("cached", "pinned", "stale"), (
        "display_state must be injected so Inventory freshness dots work"
    )
