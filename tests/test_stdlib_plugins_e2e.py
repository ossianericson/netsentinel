"""True no-mock transport e2e for the 2 stdlib-only bundled plugins (Plan Phase 3).

ha_plugin.py and synology_plugin.py use ONLY urllib (no third-party HTTP
library), so unlike test_vendor_plugins_transport.py these are driven against
REAL local HTTP servers (tests/fake_device_http.py) instead of faked library
objects -- no mocking of the transport layer at all, just urllib.request.urlopen
redirected to the fake server's actual ephemeral port (both plugins hardcode a
port in the URLs they build, so redirecting avoids ever needing that literal
port free on the test machine).

Marked `integration`: spins up a real background thread + TCP socket per test.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.fake_device_http import FakeHomeAssistantServer, FakeSynologyServer

PLUGINS_DIR = ROOT / "plugins"

pytestmark = pytest.mark.integration


def _exec_plugin(name: str, *, instance_ip: str = "", instance_id: str = ""):
    path = PLUGINS_DIR / name
    spec = importlib.util.spec_from_file_location(f"_stdlibtest_{path.stem}", str(path))
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


def _redirect_urllib(monkeypatch, fake_base_url: str) -> None:
    """Rewrite scheme+host of every urllib.request.urlopen(Request) call to
    *fake_base_url*, preserving path/query/headers/method -- lets a plugin's
    hardcoded port (8123 for HA, 8000 for Synology) transparently hit the
    fake server's real ephemeral port.
    """
    import urllib.request

    real_urlopen = urllib.request.urlopen
    fparts = urlsplit(fake_base_url)

    def _rewrite(url: str) -> str:
        parts = urlsplit(url)
        return urlunsplit((fparts.scheme, fparts.netloc, parts.path, parts.query, parts.fragment))

    def fake_urlopen(req, *a, **kw):
        if isinstance(req, str):
            return real_urlopen(_rewrite(req), *a, **kw)
        new_req = urllib.request.Request(
            _rewrite(req.full_url),
            data=req.data,
            headers=dict(req.header_items()),
            method=req.get_method(),
        )
        return real_urlopen(new_req, *a, **kw)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


# ── ha_plugin.py ────────────────────────────────────────────────────────────────

def test_ha_happy_path(monkeypatch):
    with FakeHomeAssistantServer(token="secret-token") as srv:
        _redirect_urllib(monkeypatch, srv.url)
        mod = _exec_plugin("ha_plugin.py")
        mod.HA_TOKEN = "secret-token"  # ha_plugin reads this module constant directly

        status = mod.get_status()
        assert not status["extra"].get("error")
        assert status["connected_clients"] == 1  # only "phone" is state=="home"
        assert status["extra"]["ha_version"] == "2024.1.0"

        clients = mod.get_clients()
        assert len(clients) == 1
        assert clients[0]["mac"] == "aa:bb:cc:dd:ee:01"
        assert clients[0]["hostname"] == "Phone"


def test_ha_wrong_token_classified_auth(monkeypatch):
    with FakeHomeAssistantServer(token="secret-token") as srv:
        _redirect_urllib(monkeypatch, srv.url)
        mod = _exec_plugin("ha_plugin.py")
        mod.HA_TOKEN = "wrong-token"

        status = mod.get_status()
        err = status["extra"].get("error", "")
        assert err.startswith("AUTH:"), f"expected AUTH:, got {err!r}"


def test_ha_offline_classified_net(monkeypatch):
    _redirect_urllib(monkeypatch, "http://127.0.0.1:1")  # nothing listens here
    mod = _exec_plugin("ha_plugin.py")
    mod.HA_TOKEN = "secret-token"

    status = mod.get_status()
    err = status["extra"].get("error", "")
    assert err.startswith("NET:"), f"expected NET:, got {err!r}"


def test_ha_no_token_raises_before_network(monkeypatch):
    """With no HA_TOKEN and empty keyring, _load_token() must raise before any
    network call -- not silently send an empty Authorization header.
    """
    with FakeHomeAssistantServer(token="secret-token") as srv:
        _redirect_urllib(monkeypatch, srv.url)
        _install_fake_keyring(monkeypatch, {})
        mod = _exec_plugin("ha_plugin.py")
        mod.HA_TOKEN = ""

        status = mod.get_status()
        err = status["extra"].get("error", "")
        assert err, "expected a classified error when no token is configured"


# ── synology_plugin.py ─────────────────────────────────────────────────────────

def test_synology_happy_path(monkeypatch):
    with FakeSynologyServer(password="correct-horse") as srv:
        host, port = srv.server_address
        _redirect_urllib(monkeypatch, srv.url)
        _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", f"{host}:{port}"): "correct-horse"})
        mod = _exec_plugin("synology_plugin.py", instance_ip=f"{host}:{port}")

        status = mod.get_status()
        assert not status["extra"].get("error")
        assert status["uptime_sec"] == 246810
        assert status["extra"]["model"] == "RT6600ax"

        clients = mod.get_clients()
        assert clients[0]["mac"] == "aa:bb:cc:dd:ee:09"
        assert clients[0]["band"] == "5G"  # fake device reports band="1" -> synology_plugin's _BAND["1"]


def test_synology_wrong_password_classified_auth(monkeypatch):
    with FakeSynologyServer(password="correct-horse") as srv:
        host, port = srv.server_address
        _redirect_urllib(monkeypatch, srv.url)
        _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", f"{host}:{port}"): "wrong-password"})
        mod = _exec_plugin("synology_plugin.py", instance_ip=f"{host}:{port}")

        status = mod.get_status()
        err = status["extra"].get("error", "")
        assert err.startswith("AUTH:"), f"expected AUTH:, got {err!r}"


def test_synology_offline_classified_net(monkeypatch):
    _redirect_urllib(monkeypatch, "http://127.0.0.1:1")  # nothing listens here
    _install_fake_keyring(monkeypatch, {("NetSentinel/hardware", "10.0.0.9"): "correct-horse"})
    mod = _exec_plugin("synology_plugin.py", instance_ip="10.0.0.9")

    status = mod.get_status()
    err = status["extra"].get("error", "")
    assert err.startswith("NET:"), f"expected NET:, got {err!r}"
