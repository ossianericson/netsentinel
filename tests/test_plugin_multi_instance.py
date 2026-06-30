"""Per-instance credential isolation for hardware plugins (plan Step 3).

IMPORTANT — how the Deco mesh actually works (corrected):
A TP-Link Deco system is registered as a SINGLE Hub instance pointed at the main
router. The plugin logs in once and ``get_mesh_units()`` returns every node from
that one query — the mesh nodes are NOT separate plugin instances. The
"one instance surfaces all nodes" behaviour is asserted in
``test_bundled_plugins_behavior.py`` (deco happy path: ``mesh_nodes`` and
``extra.nodes``).

What multi-instance support is genuinely for: a user registering *different*
devices as separate instances — e.g. the main Deco router AND a ZTE modem, or two
separate router systems — each holding its own keyring secret under
``NetSentinel/plugin/<instance_id>`` with no cross-talk. That isolation is what
these tests verify.

No real hardware or OS keychain is touched; ``keyring`` is faked in-memory.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.widgets.hub_helpers import _instance_id

DECO = ROOT / "plugins" / "deco_plugin.py"
ZTE = ROOT / "plugins" / "zte_plugin.py"


class _FakeKeyring:
    def __init__(self, store):
        self.store = dict(store)

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


def _exec(path, *, instance_ip, instance_id):
    spec = importlib.util.spec_from_file_location(
        f"_mi_{path.stem}_{instance_id}", str(path)
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod._NETSENTINEL_INSTANCE_IP = instance_ip
    mod._NETSENTINEL_INSTANCE_ID = instance_id
    return mod


def test_instance_id_is_unique_per_path_and_ip():
    """Different (path, ip) pairs hash to different stable IDs."""
    a = _instance_id(str(DECO), "192.168.68.1")
    b = _instance_id(str(ZTE), "192.168.254.1")
    c = _instance_id(str(DECO), "10.0.0.1")  # same plugin, different home/IP
    assert len({a, b, c}) == 3
    # Stable across calls.
    assert a == _instance_id(str(DECO), "192.168.68.1")


def test_two_distinct_device_instances_resolve_their_own_secret(monkeypatch):
    """A Deco router and a ZTE modem registered side by side stay isolated."""
    deco_ip, zte_ip = "192.168.68.1", "192.168.254.1"
    deco_iid = _instance_id(str(DECO), deco_ip)
    zte_iid = _instance_id(str(ZTE), zte_ip)
    _install_fake_keyring(
        monkeypatch,
        {
            ("NetSentinel/plugin", deco_iid): "deco-pw",
            ("NetSentinel/plugin", zte_iid): "zte-pw",
        },
    )

    deco = _exec(DECO, instance_ip=deco_ip, instance_id=deco_iid)
    zte = _exec(ZTE, instance_ip=zte_ip, instance_id=zte_iid)

    dhost, dpw = deco._load_credentials()
    zhost, zpw = zte._load_credentials()
    assert (dhost, dpw) == (deco_ip, "deco-pw")
    assert (zhost, zpw) == (zte_ip, "zte-pw")


def test_two_instances_of_same_plugin_at_different_ips(monkeypatch):
    """Two separate Deco systems (e.g. two homes) keep independent secrets."""
    ip_a, ip_b = "192.168.68.1", "10.0.0.1"
    iid_a = _instance_id(str(DECO), ip_a)
    iid_b = _instance_id(str(DECO), ip_b)
    _install_fake_keyring(
        monkeypatch,
        {
            ("NetSentinel/plugin", iid_a): "home-a",
            ("NetSentinel/plugin", iid_b): "home-b",
        },
    )
    a = _exec(DECO, instance_ip=ip_a, instance_id=iid_a)
    b = _exec(DECO, instance_ip=ip_b, instance_id=iid_b)
    assert a._load_credentials()[1] == "home-a"
    assert b._load_credentials()[1] == "home-b"


def test_per_instance_key_wins_over_generic_and_legacy(monkeypatch):
    """Precedence: NetSentinel/plugin/<iid>  >  mesh/<ip>  >  hardware/<ip>."""
    ip = "192.168.68.1"
    iid = _instance_id(str(DECO), ip)
    _install_fake_keyring(
        monkeypatch,
        {
            ("NetSentinel/plugin", iid): "winner",
            ("NetSentinel/mesh", ip): "legacy-mesh",
            ("NetSentinel/hardware", ip): "generic",
        },
    )
    mod = _exec(DECO, instance_ip=ip, instance_id=iid)
    assert mod._load_credentials()[1] == "winner"


def test_falls_back_to_legacy_mesh_key_when_no_per_instance(monkeypatch):
    """Without a per-instance secret, the legacy Mesh-page key is still honoured."""
    ip = "192.168.68.1"
    iid = _instance_id(str(DECO), ip)
    _install_fake_keyring(monkeypatch, {("NetSentinel/mesh", ip): "legacy-mesh"})
    mod = _exec(DECO, instance_ip=ip, instance_id=iid)
    assert mod._load_credentials()[1] == "legacy-mesh"


def test_missing_secret_raises_without_borrowing_another_instance(monkeypatch):
    """An instance with no stored secret raises — it never reuses another's."""
    populated_iid = _instance_id(str(DECO), "192.168.68.1")
    _install_fake_keyring(
        monkeypatch, {("NetSentinel/plugin", populated_iid): "only-this-one"}
    )
    bare_ip = "10.0.0.1"
    bare_iid = _instance_id(str(DECO), bare_ip)
    mod = _exec(DECO, instance_ip=bare_ip, instance_id=bare_iid)
    with pytest.raises(RuntimeError):
        mod._load_credentials()
