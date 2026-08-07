"""An unreachable Deco must not be reported as a password problem.

Found live on 2026-08-06 while verifying acceptance criterion 5. With the
gateway blocked at the firewall, `HOST_DOWN` fired at +94 s but
`INFRA_UNREACHABLE` never fired at all, and the plugin health record showed
why:

    AUTH: Deco login failed for 192.168.68.1: HTTPConnectionPool(host=...,
    port=80): Max retries exceeded ... [WinError 10013] ...

`DecoMeshClient._ensure_client()` catches *every* exception from
`authorize()` — including a transport-level `requests.ConnectionError` — and
re-raises it as `MeshAuthError` with the text "Deco login failed … Check that
the password is correct". `_fmt_err()` then matches the word "login" and
returns an `AUTH:` prefix, and `hardware_integration_page._emit_reachability()`
deliberately treats `AUTH:` as *reachable* (the device answered and rejected
us). So a router that is completely off the network is reported as a
credentials problem and raises nothing.

The existing "network before auth" keyword guard in `_fmt_err()` could not
catch it: urllib3's message says "Max retries exceeded", not "refused" or
"timed out", and the trailing OS strerror is localised (Swedish on the machine
where this was found), so no English network keyword appears anywhere.

Two independent defences, because either alone leaves the hole open for the
next differently-worded wrapper:
  1. the client stops calling a transport failure an auth failure;
  2. the classifier inspects the exception chain, not just the message text.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest
import requests

from modules.deco_client import DecoMeshClient, MeshApiError, MeshAuthError


def _load_plugin():
    path = Path(__file__).resolve().parent.parent / "plugins" / "deco_plugin.py"
    spec = importlib.util.spec_from_file_location("_deco_plugin_fmt_err", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# The exact urllib3/requests wording, with the localised OS tail that defeated
# every English keyword in the original classifier.
_REAL_CONNECTION_ERROR_TEXT = (
    "HTTPConnectionPool(host='192.168.68.1', port=80): Max retries exceeded "
    "with url: /cgi-bin/luci/;stok=/login?form=keys&operation=read "
    "(Caused by NewConnectionError(\"HTTPConnection(host='192.168.68.1', "
    "port=80): Failed to establish a new connection: [WinError 10013] Ett "
    "försök gjordes att få åtkomst till en socket på "
    "ett sätt som är förbjudet av "
    "åtkomstbehörigheterna\")"
)


@pytest.fixture
def fake_tplink(monkeypatch):
    """Install a fake tplinkrouterc6u whose authorize() raises what we choose."""
    def _install(exc):
        mod = types.ModuleType("tplinkrouterc6u")

        class _FakeClient:
            def __init__(self, *a, **kw):
                self._stok = "x" * 16

            def authorize(self):
                raise exc

        mod.TPLinkDecoClient = _FakeClient
        monkeypatch.setitem(sys.modules, "tplinkrouterc6u", mod)
    return _install


def test_connection_failure_is_not_raised_as_an_auth_error(fake_tplink):
    fake_tplink(requests.exceptions.ConnectionError(_REAL_CONNECTION_ERROR_TEXT))
    c = DecoMeshClient("192.168.68.1", "pw")
    with pytest.raises(MeshApiError) as ei:
        c._ensure_client()
    assert not isinstance(ei.value, MeshAuthError)
    assert "password" not in str(ei.value).lower(), (
        "an unreachable device must not be described as a credentials problem"
    )


def test_wrong_password_is_still_an_auth_error(fake_tplink):
    """The carve-out must keep working — this is the case it exists for."""
    fake_tplink(Exception("Response with error; wrong credential"))
    c = DecoMeshClient("192.168.68.1", "pw")
    with pytest.raises(MeshAuthError):
        c._ensure_client()


def test_fmt_err_classifies_the_real_connection_failure_as_net():
    mod = _load_plugin()
    exc = MeshApiError(
        f"Cannot reach Deco at 192.168.68.1: {_REAL_CONNECTION_ERROR_TEXT}"
    )
    assert mod._fmt_err(exc).startswith("NET:")


def test_fmt_err_follows_the_exception_chain_past_an_auth_shaped_message():
    """Defence 2: even if some wrapper still says "login failed", a chained
    ConnectionError is decisive — the message is not the only evidence."""
    mod = _load_plugin()
    cause = requests.exceptions.ConnectionError(_REAL_CONNECTION_ERROR_TEXT)
    exc = MeshAuthError(
        "Deco login failed for 192.168.68.1: boom\n"
        "Check that the password is correct (local admin password, "
        "not TP-Link cloud account)."
    )
    exc.__cause__ = cause
    assert mod._fmt_err(exc).startswith("NET:")


def test_fmt_err_still_returns_auth_for_a_genuine_credentials_failure():
    mod = _load_plugin()
    exc = MeshAuthError(
        "Deco login failed for 192.168.68.1: wrong credential\n"
        "Check that the password is correct."
    )
    assert mod._fmt_err(exc).startswith("AUTH:")


def test_unreachable_deco_would_be_reported_unreachable():
    """The predicate hardware_integration_page actually applies.

    `_emit_reachability(instance_id, not err.startswith("AUTH:"), err)` — so
    the classification *is* the reachability decision.
    """
    mod = _load_plugin()
    err = mod._fmt_err(MeshApiError(
        f"Cannot reach Deco at 192.168.68.1: {_REAL_CONNECTION_ERROR_TEXT}"))
    assert not err.startswith("AUTH:"), "would suppress INFRA_UNREACHABLE"
