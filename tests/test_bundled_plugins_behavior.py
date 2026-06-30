"""Mock-device behavioral tests for bundled hardware plugins (plan Step 2).

No real hardware is touched. Each plugin is exec'd in a fresh namespace the same
way ``PluginPollingWorker._run_once()`` does, with ``_NETSENTINEL_INSTANCE_IP`` /
``_NETSENTINEL_INSTANCE_ID`` injected (RULE-PL1) and ``keyring`` faked.

Coverage tiers (kept honest so the gap is visible, not hidden):

* **Credential resolution — ALL plugins with a loader.** With a faked keyring that
  returns a known secret, the plugin's ``_load_password`` / ``_load_credentials`` /
  ``_load_token`` must return it. This catches the ``_ip``-NameError class of bug
  where a plugin can never authenticate even with a saved password.
* **Per-instance keyring precedence.** A secret stored under
  ``NetSentinel/plugin/<instance_id>`` must win over the generic
  ``NetSentinel/hardware/<ip>`` key.
* **Transport happy + offline — deco & zte** (the author's own hardware; clean
  ``modules.deco_client`` / ``modules.zte_client`` seams). ``get_status()`` returns
  the documented shape on success and a classified ``extra.error`` on a device
  failure.

Library-backed plugins (fritzbox→fritzconnection, asus→asusrouter, …) are covered
only at the credential layer here — faking each third-party client is out of scope;
their transport is exercised manually by owners.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLUGINS_DIR = ROOT / "plugins"

# Plugin → name of its credential-loader function.
_LOADERS = {
    "asus_plugin.py": "_load_password",
    "deco_plugin.py": "_load_credentials",
    "fritzbox_plugin.py": "_load_password",
    "ha_plugin.py": "_load_token",
    "mikrotik_plugin.py": "_load_password",
    "netgear_plugin.py": "_load_password",
    "openwrt_plugin.py": "_load_password",
    "synology_plugin.py": "_load_password",
    "unifi_plugin.py": "_load_password",
    "zte_plugin.py": "_load_credentials",
}


def _exec_plugin(name: str, *, instance_ip: str = "", instance_id: str = ""):
    """Exec a bundled plugin in a fresh namespace, mirroring the polling worker."""
    path = PLUGINS_DIR / name
    spec = importlib.util.spec_from_file_location(f"_btest_{path.stem}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if instance_ip:
        mod._NETSENTINEL_INSTANCE_IP = instance_ip
    if instance_id:
        mod._NETSENTINEL_INSTANCE_ID = instance_id
    return mod


class _FakeKeyring:
    """In-memory keyring: store is {(service, key): secret}."""

    def __init__(self, store=None):
        self.store = dict(store or {})

    def get_password(self, service, key):
        return self.store.get((service, key))

    def set_password(self, service, key, value):
        self.store[(service, key)] = value


def _install_fake_keyring(monkeypatch, store):
    fake = types.ModuleType("keyring")
    kr = _FakeKeyring(store)
    fake.get_password = kr.get_password
    fake.set_password = kr.set_password
    monkeypatch.setitem(sys.modules, "keyring", fake)
    return kr


def _call_loader(mod, name):
    """Call the loader and normalise its return to the secret string."""
    fn = getattr(mod, _LOADERS[name])
    result = fn()
    # _load_credentials returns (host, secret); the others return the secret.
    return result[1] if isinstance(result, tuple) else result


# ── Credential resolution — the core regression for the _ip NameError ──────────

@pytest.mark.parametrize("name", sorted(_LOADERS), ids=sorted(_LOADERS))
def test_loader_returns_secret_from_generic_hardware_key(monkeypatch, name):
    """A secret saved under NetSentinel/hardware/<ip> must be returned.

    This is the path the Hub uses when the user types a password into the card.
    A plugin that references an undefined ``_ip`` swallows the NameError and
    always raises "No password saved" — this test fails for exactly that bug.
    """
    mod = _exec_plugin(name)
    ip = mod.HARDWARE_IP
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", ip): "s3cr3t"})
    assert _call_loader(mod, name) == "s3cr3t"


@pytest.mark.parametrize(
    "name",
    [n for n in sorted(_LOADERS) if n not in ("ha_plugin.py",)],
    ids=[n for n in sorted(_LOADERS) if n not in ("ha_plugin.py",)],
)
def test_loader_resolves_injected_instance_ip(monkeypatch, name):
    """With a per-instance IP injected, the loader looks up keyring at THAT host.

    ha_plugin is excluded: its keyring fallback is token-via-HA_TOKEN first and it
    is a single-instance enrichment source, not a per-device router.
    """
    mod = _exec_plugin(name, instance_ip="10.20.30.40")
    _install_fake_keyring(
        monkeypatch, {("NetSentinel/hardware", "10.20.30.40"): "byhost"}
    )
    assert _call_loader(mod, name) == "byhost"


@pytest.mark.parametrize(
    "name",
    ["deco_plugin.py", "zte_plugin.py"],
    ids=["deco", "zte"],
)
def test_per_instance_key_wins_over_generic(monkeypatch, name):
    """NetSentinel/plugin/<instance_id> takes precedence over the generic key."""
    mod = _exec_plugin(name, instance_ip="10.0.0.5", instance_id="iid-abc")
    _install_fake_keyring(
        monkeypatch,
        {
            ("NetSentinel/plugin", "iid-abc"): "per-instance",
            ("NetSentinel/hardware", "10.0.0.5"): "generic",
        },
    )
    assert _call_loader(mod, name) == "per-instance"


@pytest.mark.parametrize("name", sorted(_LOADERS), ids=sorted(_LOADERS))
def test_loader_raises_when_no_secret(monkeypatch, name):
    """With an empty keyring the loader must raise (not return None/empty)."""
    mod = _exec_plugin(name)
    _install_fake_keyring(monkeypatch, {})
    # ha_plugin returns HA_TOKEN if set, but bundled HA_TOKEN == "" so it raises too.
    with pytest.raises(RuntimeError):
        _call_loader(mod, name)


# ── deco transport: happy + offline ────────────────────────────────────────────

class _FakeUnit:
    def __init__(self, name, mac, ip, role):
        self.name, self.mac, self.ip, self.role = name, mac, ip, role


class _FakeClient:
    def __init__(self, name, mac, ip, band, unit):
        self.name, self.mac, self.ip, self.band, self.unit_name = name, mac, ip, band, unit
        self.upload_kbps = 10
        self.download_kbps = 20


def _patch_deco_client(monkeypatch, *, raise_exc=None):
    import modules.deco_client as dc

    class FakeDeco:
        def __init__(self, host, password):
            self._host = host

        def login(self):
            if raise_exc is not None:
                raise raise_exc

        def get_mesh_units(self):
            return [_FakeUnit("Main", "aa:bb", "192.168.68.1", "primary")]

        def get_all_clients(self, units=None):
            return [_FakeClient("laptop", "11:22", "192.168.68.50", "5G", "Main")]

    monkeypatch.setattr(dc, "DecoMeshClient", FakeDeco)
    return dc


def test_deco_status_happy_path(monkeypatch):
    _install_fake_keyring(
        monkeypatch, {("NetSentinel/hardware", "192.168.68.1"): "pw"}
    )
    mod = _exec_plugin("deco_plugin.py", instance_ip="192.168.68.1")
    _patch_deco_client(monkeypatch)
    status = mod.get_status()
    assert "extra" in status
    assert not status["extra"].get("error")
    assert status["connected_clients"] == 1
    assert status["mesh_nodes"] == 1
    assert status["extra"]["nodes"][0]["name"] == "Main"
    clients = mod.get_clients()
    assert clients and clients[0]["ip"] == "192.168.68.50"
    assert clients[0]["mac"] == "11:22"


def test_deco_status_offline_sets_classified_error(monkeypatch):
    import modules.deco_client as dc

    _install_fake_keyring(
        monkeypatch, {("NetSentinel/hardware", "192.168.68.1"): "pw"}
    )
    mod = _exec_plugin("deco_plugin.py", instance_ip="192.168.68.1")
    _patch_deco_client(monkeypatch, raise_exc=dc.MeshApiError("connection refused"))
    status = mod.get_status()
    err = status["extra"].get("error")
    assert err and err.startswith("NET:"), err
    # get_clients() swallows the same failure and returns []
    assert mod.get_clients() == []


# ── zte transport: happy + offline ─────────────────────────────────────────────

class _FakeSignal:
    def __init__(self):
        self.wan_ip = "1.2.3.4"
        self.wan_status = "connected"
        self.nr5g_rsrp_dbm = -80
        self.lte_rsrp_dbm = -90
        self.firmware_version = "1.0"
        self.network_type = "5G"
        self.signal_bars = 4
        for attr in (
            "nr5g_band", "nr5g_sinr_db", "nr5g_rsrq_db", "nr5g_pci", "nr5g_arfcn",
            "lte_band", "lte_snr_db", "lte_rsrq_db", "lte_pci", "lte_earfcn",
            "cell_id", "enb_id", "mcc", "mnc", "endc_info",
        ):
            setattr(self, attr, None)


def _patch_zte_client(monkeypatch, *, raise_exc=None):
    import modules.zte_client as zc

    class FakeZte:
        def __init__(self, host):
            self._host = host

        def login(self, pw):
            if raise_exc is not None:
                raise raise_exc

        def get_signal_data(self):
            return _FakeSignal()

    monkeypatch.setattr(zc, "ZteMC889Client", FakeZte)
    return zc


def test_zte_status_happy_path(monkeypatch):
    _install_fake_keyring(
        monkeypatch, {("NetSentinel/hardware", "192.168.254.1"): "pw"}
    )
    mod = _exec_plugin("zte_plugin.py", instance_ip="192.168.254.1")
    _patch_zte_client(monkeypatch)
    status = mod.get_status()
    assert not status["extra"].get("error")
    assert status["wan_ip"] == "1.2.3.4"
    assert status["signal_dbm"] == -80
    assert mod.get_clients() == []  # modem tracks no LAN clients


def test_zte_status_offline_sets_classified_error(monkeypatch):
    import modules.zte_client as zc

    _install_fake_keyring(
        monkeypatch, {("NetSentinel/hardware", "192.168.254.1"): "pw"}
    )
    mod = _exec_plugin("zte_plugin.py", instance_ip="192.168.254.1")
    _patch_zte_client(monkeypatch, raise_exc=zc.ZteAuthError("login failed: wrong credential"))
    status = mod.get_status()
    err = status["extra"].get("error")
    assert err and err.startswith("AUTH:"), err
