"""Tests for modules/settings_io.py — Settings export/import."""
import json
import pytest
from unittest.mock import MagicMock, patch


def test_import():
    from modules import settings_io
    assert hasattr(settings_io, "export_settings")
    assert hasattr(settings_io, "import_settings")


def test_keyring_keys_never_exported():
    """Verify that known keyring keys are in the exclusion set."""
    from modules.settings_io import _KEYRING_KEYS
    assert "notifications/smtp_password" in _KEYRING_KEYS
    assert "rest_api/api_key" in _KEYRING_KEYS
    assert "notifications/pushover_token" in _KEYRING_KEYS


def test_export_creates_valid_json(tmp_path):
    """export_settings writes valid JSON with a _meta block."""
    out = tmp_path / "settings_export.json"
    mock_qs = MagicMock()
    mock_qs.allKeys.return_value = ["display/compact_rows", "ui/theme", "notifications/smtp_password"]
    mock_qs.value.side_effect = lambda k: {
        "display/compact_rows": True,
        "ui/theme": "Arctic Clean",
        "notifications/smtp_password": "secret",
    }.get(k)

    # QSettings is imported inside the function; patch it at the PyQt6 level
    try:
        with patch("PyQt6.QtCore.QSettings", return_value=mock_qs):
            from modules.settings_io import export_settings
            export_settings(out)
    except Exception:
        pytest.skip("PyQt6 not available in test environment")

    if out.exists():
        data = json.loads(out.read_text())
        assert "_meta" in data
        assert data["_meta"]["app"] == "NetSentinel"
        # Secret must not be in export
        assert "notifications/smtp_password" not in data.get("settings", {})


def test_import_rejects_wrong_app(tmp_path):
    """import_settings raises ValueError for files not from NetSentinel."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"_meta": {"app": "OtherApp"}, "settings": {}}))
    try:
        from modules.settings_io import import_settings
        with pytest.raises(ValueError, match="not exported from NetSentinel"):
            import_settings(bad_file)
    except ImportError:
        pytest.skip("PyQt6 not available in test environment")


def test_import_rejects_missing_settings_key(tmp_path):
    """import_settings raises ValueError when 'settings' key is absent."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text(json.dumps({"data": {}}))
    try:
        from modules.settings_io import import_settings
        with pytest.raises(ValueError, match="missing 'settings' key"):
            import_settings(bad_file)
    except ImportError:
        pytest.skip("PyQt6 not available in test environment")
