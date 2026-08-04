"""RULE-T3 regression: the ZTE plugin must not re-authenticate on every poll.

Mechanism (found live 2026-08-03 via py-spy, see session notes):
`PluginPollingWorker` polls a "modem"-type plugin every 30 s. `get_status()`
constructed a brand-new `ZteMC889Client` and called `login()` on every single
call. `login()` builds a fresh `requests.Session()`, and constructing a Session's
HTTPS adapter creates a new `SSLContext` whose `load_default_certs()` enumerates
the ENTIRE Windows certificate store — `_load_windows_store_certs` was 24% of all
Python samples on an idle Dashboard, plus two extra HTTPS round-trips per poll.

`ZteMC889Client.get_signal_data()` already re-authenticates itself when the
session goes stale (it retains the password for exactly that purpose), so
caching the client across polls is what the client was designed for.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[1] / "plugins" / "zte_plugin.py"


def _load_plugin():
    """Fresh module instance per test — the fix adds module-level cache state."""
    spec = importlib.util.spec_from_file_location("_ztetest_plugin", str(_PLUGIN))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeSignalData:
    """get_status() reads ~20 attributes; default the rest to None."""

    wan_ip = "10.0.0.2"
    wan_status = "Connected"
    nr5g_rsrp_dbm = -80
    lte_rsrp_dbm = None
    network_type = "5G"

    def __getattr__(self, name):    # only called for attrs not set above
        return None


class _CountingClient:
    """Stand-in for ZteMC889Client that records how often login() runs."""

    login_calls = 0
    instances = 0

    def __init__(self, host="192.168.254.1", timeout=10.0):
        self.host = host
        type(self).instances += 1

    def login(self, password, username="admin"):
        type(self).login_calls += 1

    def get_signal_data(self):
        return _FakeSignalData()


@pytest.fixture
def plugin(monkeypatch):
    mod = _load_plugin()
    monkeypatch.setattr(mod, "_load_credentials", lambda: ("192.168.254.1", "pw"))
    _CountingClient.login_calls = 0
    _CountingClient.instances = 0

    import modules.zte_client as zc
    monkeypatch.setattr(zc, "ZteMC889Client", _CountingClient)
    return mod


def test_repeated_polls_reuse_one_authenticated_session(plugin):
    """Three polls must cost ONE login, not three.

    At a 30 s modem poll interval, one login per poll is 120 Windows
    certificate-store loads per hour on an otherwise idle app.
    """
    for _ in range(3):
        plugin.get_status()

    assert _CountingClient.login_calls == 1, (
        f"expected 1 login across 3 polls, got {_CountingClient.login_calls} — "
        f"each login builds a new requests.Session and reloads the whole "
        f"Windows cert store"
    )
    assert _CountingClient.instances == 1, (
        f"expected the client to be cached across polls, got "
        f"{_CountingClient.instances} instances"
    )


def test_status_payload_is_unchanged_by_caching(plugin):
    """The cache must not alter what the plugin reports."""
    first = plugin.get_status()
    second = plugin.get_status()

    assert first.get("wan_ip") == "10.0.0.2"
    assert first.get("signal_dbm") == -80
    assert first == second, "cached poll returned a different payload shape"


def test_auth_failure_invalidates_the_cache(plugin, monkeypatch):
    """A dead session must not be cached forever.

    If the modem reboots or the cookie is revoked, the cached client starts
    failing; the next poll has to build a fresh one rather than re-using a
    client that can never succeed again.
    """
    import modules.zte_client as zc

    class _AuthFailingClient(_CountingClient):
        def get_signal_data(self):
            raise zc.ZteAuthError("session revoked")

    monkeypatch.setattr(zc, "ZteMC889Client", _AuthFailingClient)
    _AuthFailingClient.login_calls = 0
    _AuthFailingClient.instances = 0

    first = plugin.get_status()
    assert first["extra"].get("error"), "auth failure must surface as an error payload"

    # Recovery: a healthy client on the next poll must be constructed afresh.
    monkeypatch.setattr(zc, "ZteMC889Client", _CountingClient)
    _CountingClient.login_calls = 0
    _CountingClient.instances = 0

    recovered = plugin.get_status()
    assert recovered.get("wan_ip") == "10.0.0.2", "plugin never recovered after auth failure"
    assert _CountingClient.login_calls == 1, (
        "a failed session was cached — the plugin must re-login after ZteAuthError"
    )
