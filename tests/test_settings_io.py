"""Tests for modules/settings_io.py — pure settings export/import (no PyQt).

Contract (ARCH RULE 1, D#13 — module layer is PyQt-free):
  - export_settings(path, settings) : filter keyring keys, JSON-coerce, write file.
  - import_settings(path) -> dict   : validate + return the settings dict (caller
                                      writes it to QSettings).
The QSettings read/write lives in the UI caller (ui/pages/settings_cards.py),
not here.
"""
import json
import pytest


def test_import():
    from modules import settings_io
    assert hasattr(settings_io, "export_settings")
    assert hasattr(settings_io, "import_settings")


def test_keyring_keys_never_exported():
    """Verify that the REAL keyring keys are in the exclusion set.

    Phase 3.3 regression guard: _KEYRING_KEYS previously listed
    notifications/smtp_password, notifications/pushover_token, and
    notifications/telegram_token -- QSettings keys nothing in the app has
    ever written (NotificationsPage uses notif/* via the keyring, not
    notifications/*). The real secret-bearing keys were never in this set at
    all, so a stale pre-migration notif/email_pass value was exportable."""
    from modules.settings_io import _KEYRING_KEYS
    assert "notif/email_pass" in _KEYRING_KEYS
    assert "notif/pushover_token" in _KEYRING_KEYS
    assert "notif/pushover_user" in _KEYRING_KEYS
    assert "notif/ntfy_token" in _KEYRING_KEYS
    assert "notif/telegram_token" in _KEYRING_KEYS
    assert "rest_api/api_key" in _KEYRING_KEYS
    assert "snmp/community" in _KEYRING_KEYS
    assert "mqtt/password" in _KEYRING_KEYS
    # The old orphan names are gone -- nothing in the app ever wrote them.
    assert "notifications/smtp_password" not in _KEYRING_KEYS
    assert "notifications/pushover_token" not in _KEYRING_KEYS
    assert "notifications/telegram_token" not in _KEYRING_KEYS


def test_real_email_pass_key_never_exported(tmp_path):
    """A stale pre-migration notif/email_pass surviving in QSettings must
    never be exportable, even though the migration (NotificationsPage._restore())
    normally moves it into the keychain and removes it."""
    from modules.settings_io import export_settings
    out = tmp_path / "settings_export.json"
    export_settings(out, {"notif/email_pass": "hunter2", "ui/theme": "Midnight Pro"})
    text = out.read_text(encoding="utf-8")
    assert "hunter2" not in text


def test_export_creates_valid_json(tmp_path):
    """export_settings writes valid JSON with a _meta block, excluding secrets."""
    from modules.settings_io import export_settings
    out = tmp_path / "settings_export.json"
    raw = {
        "display/compact_rows": True,
        "ui/theme": "Arctic Clean",
        "notif/email_pass": "secret",
    }
    export_settings(out, raw)

    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["_meta"]["app"] == "NetSentinel"
    assert data["_meta"]["format_version"] == 1
    # Non-secret keys round-trip
    assert data["settings"]["display/compact_rows"] is True
    assert data["settings"]["ui/theme"] == "Arctic Clean"
    # Secret must NOT be in the export file
    assert "notif/email_pass" not in data["settings"]


def test_export_skips_none_and_coerces_types(tmp_path):
    """None values are dropped; non-JSON-native values are stringified."""
    from modules.settings_io import export_settings
    out = tmp_path / "settings_export.json"

    class _Weird:
        def __str__(self):
            return "weird-value"

    raw = {
        "a/none": None,          # dropped
        "a/int": 5,              # kept as int
        "a/list": ["x", "y"],    # kept as list
        "a/obj": _Weird(),       # stringified
    }
    export_settings(out, raw)
    settings = json.loads(out.read_text(encoding="utf-8"))["settings"]
    assert "a/none" not in settings
    assert settings["a/int"] == 5
    assert settings["a/list"] == ["x", "y"]
    assert settings["a/obj"] == "weird-value"


def test_import_returns_dict_without_keyring(tmp_path):
    """import_settings returns the settings dict, minus any keyring keys."""
    from modules.settings_io import import_settings, export_settings
    out = tmp_path / "s.json"
    export_settings(out, {"ui/theme": "Midnight Pro", "display/compact_rows": False})
    data = import_settings(out)
    assert isinstance(data, dict)
    assert data == {"ui/theme": "Midnight Pro", "display/compact_rows": False}


def test_import_drops_keyring_keys_if_present(tmp_path):
    """A hand-crafted file containing a keyring key must not leak it back."""
    from modules.settings_io import import_settings
    f = tmp_path / "s.json"
    f.write_text(json.dumps({
        "_meta": {"app": "NetSentinel"},
        "settings": {"ui/theme": "Arctic Clean", "rest_api/api_key": "leaked"},
    }), encoding="utf-8")
    data = import_settings(f)
    assert data == {"ui/theme": "Arctic Clean"}
    assert "rest_api/api_key" not in data


def test_roundtrip(tmp_path):
    """export then import returns the same non-secret settings."""
    from modules.settings_io import export_settings, import_settings
    out = tmp_path / "rt.json"
    original = {"ui/theme": "Arctic Clean", "scan/interval": 300, "flag": True}
    export_settings(out, original)
    assert import_settings(out) == original


def test_import_rejects_wrong_app(tmp_path):
    """import_settings raises ValueError for files not from NetSentinel."""
    from modules.settings_io import import_settings
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"_meta": {"app": "OtherApp"}, "settings": {}}))
    with pytest.raises(ValueError, match="not exported from NetSentinel"):
        import_settings(bad_file)


def test_import_rejects_missing_settings_key(tmp_path):
    """import_settings raises ValueError when 'settings' key is absent."""
    from modules.settings_io import import_settings
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"data": {}}))
    with pytest.raises(ValueError, match="missing 'settings' key"):
        import_settings(bad_file)
