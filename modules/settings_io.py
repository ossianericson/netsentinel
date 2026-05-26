"""
settings_io.py — Export / import NetSentinel QSettings to/from JSON.

Credentials stored in the OS keychain are NEVER written to the export file.
A warning notice is included in the export so importers know secrets are excluded.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# QSettings keys that map to keyring entries — never exported.
_KEYRING_KEYS: frozenset[str] = frozenset({
    "notifications/smtp_password",
    "notifications/pushover_token",
    "notifications/telegram_token",
    "rest_api/api_key",
    "snmp/community",
    "mqtt/password",
})


def export_settings(path: Path) -> None:
    """Dump all QSettings values (except keyring secrets) to a JSON file."""
    from PyQt6.QtCore import QSettings
    qs = QSettings("NetSentinel", "NetSentinel")

    data: dict[str, Any] = {}
    for key in qs.allKeys():
        if key in _KEYRING_KEYS:
            continue
        val = qs.value(key)
        # QSettings may return None for some keys — skip them
        if val is None:
            continue
        # Convert types that aren't JSON-serialisable
        if isinstance(val, bool):
            data[key] = val
        elif isinstance(val, (int, float, str, list, dict)):
            data[key] = val
        else:
            data[key] = str(val)

    output = {
        "_meta": {
            "app": "NetSentinel",
            "format_version": 1,
            "note": (
                "Secrets (SMTP password, API keys, tokens) are stored in the OS keychain "
                "and are NOT included in this export. You must re-enter them after import."
            ),
        },
        "settings": data,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")


def import_settings(path: Path) -> int:
    """Read a JSON export file and write all settings back to QSettings.

    Returns the number of keys imported.
    Raises ValueError if the file format is unrecognised.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "settings" not in raw:
        raise ValueError("Unrecognised settings file — missing 'settings' key.")
    meta = raw.get("_meta", {})
    if meta.get("app") != "NetSentinel":
        raise ValueError("This file was not exported from NetSentinel.")

    from PyQt6.QtCore import QSettings
    qs = QSettings("NetSentinel", "NetSentinel")

    count = 0
    for key, val in raw["settings"].items():
        if key in _KEYRING_KEYS:
            continue
        qs.setValue(key, val)
        count += 1
    qs.sync()
    return count
