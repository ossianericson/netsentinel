"""Transport tests for the 6 PyPI-library-backed hardware plugins (Plan Phase 3).

Unlike deco_plugin.py/zte_plugin.py (the author's own hardware, already covered
by tests/test_bundled_plugins_behavior.py), these 6 plugins wrap third-party
libraries that are not installed in CI: asusrouter, routeros-api, pyunifi,
pynetgear, openwrt-luci-rpc, fritzconnection. Each library's exact class/
method surface is faked via ``monkeypatch.setitem(sys.modules, ...)``, mirroring
the pattern in test_bundled_plugins_behavior.py, and each plugin is exec'd in a
fresh namespace exactly like PluginPollingWorker._run_once() does.

While building this coverage, all 6 plugins turned out to have the same defect
already fixed in Plan Phase 2 for deco/zte and the AI-prompt templates:
get_status()/get_clients() did not catch their own exceptions at all --
_fmt_err() existed only in the unused standalone --netsentinel shim. Phase 3
fixed all 6 (wrapped get_status()/get_clients() in try/except, hardened
_fmt_err() with the type/status-code-first check). These tests prove that fix:
happy path, AUTH: classification, NET: classification, DEPS: classification.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLUGINS_DIR = ROOT / "plugins"


# ── Shared helpers (same pattern as test_bundled_plugins_behavior.py) ─────────

def _exec_plugin(name: str, *, instance_ip: str = "", instance_id: str = ""):
    path = PLUGINS_DIR / name
    spec = importlib.util.spec_from_file_location(f"_vtest_{path.stem}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if instance_ip:
        mod._NETSENTINEL_INSTANCE_IP = instance_ip
    if instance_id:
        mod._NETSENTINEL_INSTANCE_ID = instance_id
    return mod


def _install_fake_keyring(monkeypatch, store: dict) -> None:
    fake = types.ModuleType("keyring")
    fake.get_password = lambda service, key: store.get((service, key))
    fake.set_password = lambda service, key, value: store.__setitem__((service, key), value)
    monkeypatch.setitem(sys.modules, "keyring", fake)


def _hide_module(monkeypatch, name: str) -> None:
    """Force `import name` to raise ImportError regardless of what's installed.

    Setting sys.modules[name] = None is the documented Python mechanism for
    this (PEP 328 / importlib docs) -- more portable than relying on the dev
    machine not having the real package installed (fritzconnection IS
    installed here).
    """
    monkeypatch.setitem(sys.modules, name, None)


_HOST = "10.0.0.5"


# ── asus_plugin.py (asusrouter, async) ─────────────────────────────────────────

class _FakeAsusRouter:
    _raise: Exception | None = None

    def __init__(self, host, username, password, use_ssl):
        self.host = host

    async def async_connect(self):
        if self._raise:
            raise self._raise

    async def async_get_connected_devices(self):
        return {"aa:bb:cc:dd:ee:01": {"ip": "192.168.50.50", "name": "laptop", "connection_type": "5ghz"}}

    async def async_get_network(self):
        return {}

    async def async_disconnect(self):
        pass


def _install_fake_asusrouter(monkeypatch, *, raise_exc=None):
    cls = type("FakeAsusRouter", (_FakeAsusRouter,), {"_raise": raise_exc})
    mod = types.ModuleType("asusrouter")
    mod.AsusRouter = cls
    monkeypatch.setitem(sys.modules, "asusrouter", mod)


def test_asus_happy_path(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_asusrouter(monkeypatch)
    mod = _exec_plugin("asus_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert not status["extra"].get("error")
    assert status["connected_clients"] == 1
    clients = mod.get_clients()
    assert clients[0]["ip"] == "192.168.50.50"
    assert clients[0]["band"] == "5G"


def test_asus_auth_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_asusrouter(monkeypatch, raise_exc=Exception("invalid credentials, auth failed"))
    mod = _exec_plugin("asus_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("AUTH:")
    assert mod.get_clients() == []


def test_asus_net_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_asusrouter(monkeypatch, raise_exc=ConnectionError("refused"))
    mod = _exec_plugin("asus_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("NET:")


def test_asus_missing_library_classified_deps(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _hide_module(monkeypatch, "asusrouter")
    mod = _exec_plugin("asus_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("DEPS:")


# ── mikrotik_plugin.py (routeros_api) ──────────────────────────────────────────

class _FakeMikrotikResource:
    _raise: Exception | None = None

    def __init__(self, path):
        self.path = path

    def get(self):
        if self._raise:
            raise self._raise
        if self.path == "/ip/address":
            return [{"address": "203.0.113.5/32"}]
        if self.path == "/ip/dhcp-server/lease":
            return [{"status": "bound", "mac-address": "AA:BB:CC:DD:EE:02",
                      "address": "192.168.88.50", "host-name": "phone"}]
        if self.path == "/ip/arp":
            return []
        return []


class _FakeMikrotikApi:
    _raise: Exception | None = None

    def get_resource(self, path):
        return type("R", (_FakeMikrotikResource,), {"_raise": self._raise})(path)


def _install_fake_routeros_api(monkeypatch, *, raise_exc=None):
    api_cls = type("FakeApi", (_FakeMikrotikApi,), {"_raise": raise_exc})

    class FakePool:
        def __init__(self, host, username, password, port, plaintext_login):
            pass

        def get_api(self):
            return api_cls()

    mod = types.ModuleType("routeros_api")
    mod.RouterOsApiPool = FakePool
    monkeypatch.setitem(sys.modules, "routeros_api", mod)


def test_mikrotik_happy_path(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_routeros_api(monkeypatch)
    mod = _exec_plugin("mikrotik_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert not status["extra"].get("error")
    assert status["wan_ip"] == "203.0.113.5"
    assert status["connected_clients"] == 1
    clients = mod.get_clients()
    assert clients[0]["mac"] == "AA:BB:CC:DD:EE:02"


def test_mikrotik_auth_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_routeros_api(monkeypatch, raise_exc=Exception("login failed: wrong password"))
    mod = _exec_plugin("mikrotik_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("AUTH:")


def test_mikrotik_net_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_routeros_api(monkeypatch, raise_exc=TimeoutError("timed out"))
    mod = _exec_plugin("mikrotik_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("NET:")


def test_mikrotik_missing_library_classified_deps(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _hide_module(monkeypatch, "routeros_api")
    mod = _exec_plugin("mikrotik_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("DEPS:")


# ── fritzbox_plugin.py (fritzconnection — installed; patch its classes) ───────

class _FakeFritzStatus:
    _raise: Exception | None = None

    def __init__(self, address, password):
        if self._raise:
            raise self._raise
        self.external_ip = "203.0.113.9"
        self.uptime = 54321
        self.is_connected = True


class _FakeFritzHosts:
    _raise: Exception | None = None

    def __init__(self, address, password):
        if self._raise:
            raise self._raise

    def get_active_hosts(self):
        return [{"ip": "192.168.178.50", "mac": "AA:BB:CC:DD:EE:03",
                 "name": "tablet", "interface_type": "WLAN"}]


def _install_fake_fritzconnection(monkeypatch, *, raise_exc=None):
    status_cls = type("FakeFritzStatus", (_FakeFritzStatus,), {"_raise": raise_exc})
    hosts_cls = type("FakeFritzHosts", (_FakeFritzHosts,), {"_raise": raise_exc})

    pkg = types.ModuleType("fritzconnection")
    lib_pkg = types.ModuleType("fritzconnection.lib")
    fs_mod = types.ModuleType("fritzconnection.lib.fritzstatus")
    fh_mod = types.ModuleType("fritzconnection.lib.fritzhosts")
    fs_mod.FritzStatus = status_cls
    fh_mod.FritzHosts = hosts_cls
    lib_pkg.fritzstatus = fs_mod
    lib_pkg.fritzhosts = fh_mod
    pkg.lib = lib_pkg

    monkeypatch.setitem(sys.modules, "fritzconnection", pkg)
    monkeypatch.setitem(sys.modules, "fritzconnection.lib", lib_pkg)
    monkeypatch.setitem(sys.modules, "fritzconnection.lib.fritzstatus", fs_mod)
    monkeypatch.setitem(sys.modules, "fritzconnection.lib.fritzhosts", fh_mod)


def test_fritzbox_happy_path(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_fritzconnection(monkeypatch)
    mod = _exec_plugin("fritzbox_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert not status["extra"].get("error")
    assert status["wan_ip"] == "203.0.113.9"
    clients = mod.get_clients()
    assert clients[0]["mac"] == "AA:BB:CC:DD:EE:03"


def test_fritzbox_auth_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_fritzconnection(monkeypatch, raise_exc=Exception("401 Unauthorized: wrong password"))
    mod = _exec_plugin("fritzbox_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("AUTH:")


def test_fritzbox_net_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_fritzconnection(monkeypatch, raise_exc=ConnectionRefusedError("refused"))
    mod = _exec_plugin("fritzbox_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("NET:")


def test_fritzbox_missing_library_classified_deps(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _hide_module(monkeypatch, "fritzconnection")
    mod = _exec_plugin("fritzbox_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("DEPS:")


# ── unifi_plugin.py (pyunifi.controller.Controller) ────────────────────────────

class _FakeUnifiController:
    _raise: Exception | None = None

    def __init__(self, host, username, password, version, ssl_verify):
        if self._raise:
            raise self._raise

    def get_sites(self):
        return [{"desc": "Default"}]

    def get_clients(self):
        return [{"ip": "192.168.1.50", "mac": "AA:BB:CC:DD:EE:04",
                  "hostname": "tv", "radio": "na", "ap_mac": "unit-1"}]


def _install_fake_pyunifi(monkeypatch, *, raise_exc=None):
    ctrl_cls = type("FakeController", (_FakeUnifiController,), {"_raise": raise_exc})
    pkg = types.ModuleType("pyunifi")
    submod = types.ModuleType("pyunifi.controller")
    submod.Controller = ctrl_cls
    pkg.controller = submod
    monkeypatch.setitem(sys.modules, "pyunifi", pkg)
    monkeypatch.setitem(sys.modules, "pyunifi.controller", submod)


def test_unifi_happy_path(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_pyunifi(monkeypatch)
    mod = _exec_plugin("unifi_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert not status["extra"].get("error")
    assert status["connected_clients"] == 1
    clients = mod.get_clients()
    assert clients[0]["band"] == "5G"


def test_unifi_auth_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_pyunifi(monkeypatch, raise_exc=Exception("api.err.Invalid — wrong credential"))
    mod = _exec_plugin("unifi_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("AUTH:")


def test_unifi_net_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_pyunifi(monkeypatch, raise_exc=ConnectionError("connection refused"))
    mod = _exec_plugin("unifi_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("NET:")


def test_unifi_missing_library_classified_deps(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _hide_module(monkeypatch, "pyunifi")
    mod = _exec_plugin("unifi_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("DEPS:")


# ── netgear_plugin.py (pynetgear.Netgear) ──────────────────────────────────────

class _FakeNetgearDevice:
    def __init__(self, ip, mac, name, connection_type):
        self.ip, self.mac, self.name, self.connection_type = ip, mac, name, connection_type


class _FakeNetgear:
    _raise: Exception | None = None

    def __init__(self, password, host):
        pass

    def get_info(self):
        if self._raise:
            raise self._raise
        return {"ExternalIPAddress": "203.0.113.20", "Firmwareversion": "1.2.3", "ModelName": "RAX200"}

    def get_attached_devices_v2(self):
        if self._raise:
            raise self._raise
        return [_FakeNetgearDevice("192.168.1.60", "AA:BB:CC:DD:EE:05", "console", "3")]


def _install_fake_pynetgear(monkeypatch, *, raise_exc=None):
    cls = type("FakeNetgear", (_FakeNetgear,), {"_raise": raise_exc})
    mod = types.ModuleType("pynetgear")
    mod.Netgear = cls
    monkeypatch.setitem(sys.modules, "pynetgear", mod)


def test_netgear_happy_path(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_pynetgear(monkeypatch)
    mod = _exec_plugin("netgear_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert not status["extra"].get("error")
    assert status["wan_ip"] == "203.0.113.20"
    clients = mod.get_clients()
    assert clients[0]["band"] == "5G"


def test_netgear_auth_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_pynetgear(monkeypatch, raise_exc=Exception("401 Forbidden: bad password"))
    mod = _exec_plugin("netgear_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("AUTH:")


def test_netgear_net_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_pynetgear(monkeypatch, raise_exc=ConnectionError("unreachable"))
    mod = _exec_plugin("netgear_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("NET:")


def test_netgear_missing_library_classified_deps(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _hide_module(monkeypatch, "pynetgear")
    mod = _exec_plugin("netgear_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("DEPS:")


# ── openwrt_plugin.py (openwrt_luci_rpc.OpenWrtRpc) ────────────────────────────

class _FakeOpenWrtRpc:
    _raise: Exception | None = None

    def __init__(self, host, username, password):
        pass

    def get_status(self):
        if self._raise:
            raise self._raise
        return {"uptime": 99999, "load": [0.1, 0.2, 0.3]}

    def get_arp_table(self):
        if self._raise:
            raise self._raise
        return [{"macaddr": "aa:bb:cc:dd:ee:06", "ipaddr": "192.168.1.70"}]

    def get_wireless_devices(self):
        return {}


def _install_fake_openwrt_luci_rpc(monkeypatch, *, raise_exc=None):
    cls = type("FakeOpenWrtRpc", (_FakeOpenWrtRpc,), {"_raise": raise_exc})
    mod = types.ModuleType("openwrt_luci_rpc")
    mod.OpenWrtRpc = cls
    monkeypatch.setitem(sys.modules, "openwrt_luci_rpc", mod)


def test_openwrt_happy_path(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_openwrt_luci_rpc(monkeypatch)
    mod = _exec_plugin("openwrt_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert not status["extra"].get("error")
    assert status["uptime_sec"] == 99999
    clients = mod.get_clients()
    assert clients[0]["mac"] == "AA:BB:CC:DD:EE:06"
    assert clients[0]["band"] == "Wired"


def test_openwrt_auth_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_openwrt_luci_rpc(monkeypatch, raise_exc=Exception("login failed"))
    mod = _exec_plugin("openwrt_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("AUTH:")


def test_openwrt_net_failure_classified(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _install_fake_openwrt_luci_rpc(monkeypatch, raise_exc=TimeoutError("timed out"))
    mod = _exec_plugin("openwrt_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("NET:")


def test_openwrt_missing_library_classified_deps(monkeypatch):
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", _HOST): "pw"})
    _hide_module(monkeypatch, "openwrt_luci_rpc")
    mod = _exec_plugin("openwrt_plugin.py", instance_ip=_HOST)
    status = mod.get_status()
    assert status["extra"]["error"].startswith("DEPS:")
