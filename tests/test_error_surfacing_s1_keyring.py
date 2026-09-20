"""S1.4 — a password that could not be saved must say so (finding F2-KEY).

``mqtt_page._set_secret`` swallowed every keyring failure with
``pass  # no keyring backend — silently skip persisting the secret``. The write
was skipped, ``_get_secret()`` then returned ``""``, and ``""`` is also what a
never-set password returns — so the UI could not tell "not configured" from
"we tried to save it and failed". The user saw a normal "Settings saved" and
lost the password at next launch.

Scope note: the same silent ``pass`` exists in ``notif_channel_panels``,
``threat_intel_page``, ``plugin_device_page`` and ``hub_card``. Those are
deferred to S6 by owner decision; only MQTT is covered here.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PyQt6")
keyring = pytest.importorskip("keyring")

from keyring.errors import KeyringError  # noqa: E402

from ui.pages import mqtt_page as mqtt_mod  # noqa: E402


def test_set_secret_reports_failure_instead_of_swallowing_it(monkeypatch):
    """The helper must tell its caller whether the secret actually persisted."""
    def _boom(*_a, **_k):
        raise KeyringError("no recommended backend was available")

    monkeypatch.setattr(mqtt_mod.keyring, "set_password", _boom)

    assert mqtt_mod._set_secret("hunter2") is False, (
        "_set_secret swallowed the keyring failure and returned None — the "
        "caller cannot tell the password was never stored"
    )


def test_set_secret_reports_success(monkeypatch):
    stored: dict = {}
    monkeypatch.setattr(
        mqtt_mod.keyring, "set_password",
        lambda svc, key, pw: stored.__setitem__((svc, key), pw),
    )
    assert mqtt_mod._set_secret("hunter2") is True
    assert stored


def test_get_secret_distinguishes_unset_from_unreadable(monkeypatch):
    """A read failure is not the same fact as 'the user never set one'."""
    def _boom(*_a, **_k):
        raise KeyringError("backend locked")

    monkeypatch.setattr(mqtt_mod.keyring, "get_password", _boom)
    assert mqtt_mod._secret_is_readable() is False, (
        "a keyring read failure is indistinguishable from an unset password"
    )

    monkeypatch.setattr(mqtt_mod.keyring, "get_password", lambda *_a, **_k: None)
    assert mqtt_mod._secret_is_readable() is True
