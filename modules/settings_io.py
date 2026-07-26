"""
settings_io.py — Export / import NetSentinel settings to/from JSON.

Pure module (ARCH RULE 1): no PyQt import. It owns the JSON shaping and the
keyring-secret filtering; the QSettings read/write lives in the UI caller
(ui/pages/settings_cards.py), which threads a plain {key: value} dict in and out.

Credentials stored in the OS keychain are NEVER written to the export file.
A warning notice is included in the export so importers know secrets are excluded.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


# QSettings keys that map to keyring entries — never exported.
_KEYRING_KEYS: frozenset[str] = frozenset({
    # Legacy plaintext QSettings keys migrated into the OS keychain by
    # NotificationsPage._restore() — never export them even if a stale one
    # survives from a pre-migration install.
    "notif/email_pass", "notif/pushover_token", "notif/pushover_user",
    "notif/ntfy_token", "notif/telegram_token",
    "rest_api/api_key", "snmp/community", "mqtt/password",
})


def export_settings(path: Path, settings: Mapping[str, Any]) -> None:
    """Write `settings` (minus keyring secrets) to a JSON file.

    `settings` is the raw {key: value} mapping the caller read from QSettings.
    None values are dropped; values that aren't JSON-native are stringified.
    """
    data: dict[str, Any] = {}
    for key, val in settings.items():
        if key in _KEYRING_KEYS:
            continue
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


def import_settings(path: Path) -> dict[str, Any]:
    """Read a JSON export file and return its settings dict (minus keyring secrets).

    The caller is responsible for writing the returned dict to QSettings and
    reporting len(...) as the imported count.
    Raises ValueError if the file format is unrecognised.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "settings" not in raw:
        raise ValueError("Unrecognised settings file — missing 'settings' key.")
    meta = raw.get("_meta", {})
    if meta.get("app") != "NetSentinel":
        raise ValueError("This file was not exported from NetSentinel.")

    return {
        key: val
        for key, val in raw["settings"].items()
        if key not in _KEYRING_KEYS
    }
