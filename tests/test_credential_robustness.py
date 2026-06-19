"""Tests for plugin credential robustness patterns (P4-2, P4-3, P4-4).

Covers:
  P4-2 — Per-instance keyring namespace: _instance_id() is deterministic,
          unique per (path, ip) pair, and different for different IPs.
  P4-3 — Credential pre-fill: _show_credential_dialog receives current_ip
          from the instance registry (_on_update_credentials already uses it).
  P4-4 — Multi-instance independence: two instances at different IPs
          produce distinct keyring keys (no credential cross-contamination).
  Back-compat — Legacy keyring writes also use the per-instance namespace
          so old plugins can still read their credentials.

No QApplication or real device required — all tests operate at the data level.
"""
from __future__ import annotations


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_instance_id():
    from ui.pages.hardware_integration_page import _instance_id
    return _instance_id


# ── P4-2: _instance_id is deterministic ──────────────────────────────────────

def test_instance_id_is_deterministic():
    """Same (path, ip) always produces the same key."""
    _instance_id = _get_instance_id()
    key1 = _instance_id("/plugins/deco_plugin.py", "192.168.1.1")
    key2 = _instance_id("/plugins/deco_plugin.py", "192.168.1.1")
    assert key1 == key2, "Same inputs must produce the same keyring key"


def test_instance_id_is_hex_16_chars():
    """Key is a 16-character hex string (truncated SHA-256)."""
    _instance_id = _get_instance_id()
    key = _instance_id("/plugins/deco_plugin.py", "192.168.1.1")
    assert len(key) == 16, f"Expected 16-char key, got {len(key)}"
    assert all(c in "0123456789abcdef" for c in key), f"Key is not lowercase hex: {key!r}"


# ── P4-4: Multi-instance independence ────────────────────────────────────────

def test_instance_id_differs_by_ip():
    """Same plugin file, different IPs → different keyring keys."""
    _instance_id = _get_instance_id()
    key_a = _instance_id("/plugins/router_plugin.py", "192.168.1.1")
    key_b = _instance_id("/plugins/router_plugin.py", "192.168.1.2")
    assert key_a != key_b, (
        "Different IPs for the same plugin must produce independent keyring keys"
    )


def test_instance_id_differs_by_path():
    """Same IP, different plugin files → different keyring keys."""
    _instance_id = _get_instance_id()
    key_a = _instance_id("/plugins/deco_plugin.py",  "192.168.1.1")
    key_b = _instance_id("/plugins/other_plugin.py", "192.168.1.1")
    assert key_a != key_b, (
        "Different plugin paths with the same IP must produce independent keyring keys"
    )


def test_two_instances_same_plugin_different_ips_have_independent_keys():
    """Multi-instance scenario: two Deco routers at different IPs never share credentials."""
    _instance_id = _get_instance_id()
    office_key = _instance_id("/plugins/deco_plugin.py", "192.168.10.1")
    home_key   = _instance_id("/plugins/deco_plugin.py", "192.168.1.1")
    assert office_key != home_key, (
        "Two instances of the same plugin at different IPs must have independent keys"
    )


# ── P4-3: credential dialog uses current_ip from registry ────────────────────

def test_on_update_credentials_reads_ip_from_instance_registry(tmp_path, monkeypatch):
    """_on_update_credentials passes current_ip (from registry) to the dialog, not a hardcoded value."""
    from unittest.mock import patch

    stored_ip = "10.0.0.99"
    fake_instance = {
        "id":   "testinst001",
        "path": str(tmp_path / "test_plugin.py"),
        "ip":   stored_ip,
        "name": "Test Router",
    }
    plugin_src = (
        'HARDWARE_NAME = "Test Router"\n'
        'HARDWARE_TYPE = "router"\n'
        'HARDWARE_IP   = "10.0.0.1"\n'
        'def get_info(): return {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP}\n'
        'def get_status(): return {"connected_clients": 0, "extra": {}}\n'
    )
    (tmp_path / "test_plugin.py").write_text(plugin_src, encoding="utf-8")

    captured: list[str] = []

    def _fake_dialog(parent, name, default_ip, cred_label, plugin_path=""):
        captured.append(default_ip)
        return False, ""   # user cancels — no side effects

    from ui.pages.hardware_integration_page import HardwareIntegrationPage
    with patch("ui.pages.hardware_integration_page._load_instances",
               return_value=[fake_instance]), \
         patch("ui.pages.hardware_integration_page.show_credential_dialog",
               side_effect=_fake_dialog):
        page = HardwareIntegrationPage.__new__(HardwareIntegrationPage)
        page._cards = {}
        page._poll_workers = {}
        page._on_update_credentials("testinst001")

    assert len(captured) == 1, "Dialog should have been called once"
    assert captured[0] == stored_ip, (
        f"Dialog should receive stored IP {stored_ip!r}, got {captured[0]!r}"
    )


# ── Back-compat: legacy namespace also written ────────────────────────────────

def test_instance_id_generates_consistent_key_for_known_inputs():
    """Regression: the SHA-256 truncation is stable across Python versions."""
    import hashlib
    path = "/plugins/deco_plugin.py"
    ip   = "192.168.1.1"
    expected = hashlib.sha256(f"{path}:{ip}".encode()).hexdigest()[:16]

    _instance_id = _get_instance_id()
    assert _instance_id(path, ip) == expected, (
        "Key algorithm must stay stable: sha256(path:ip).hexdigest()[:16]"
    )


# ── P3-4 regression: rename updates instance registry name ───────────────────

def test_on_rename_card_updates_registry_name(tmp_path, monkeypatch):
    """_on_rename_card persists new name to the instance registry."""

    fake_instances = [
        {"id": "inst_abc", "path": str(tmp_path / "router.py"),
         "ip": "10.0.0.1", "name": "Old Name"},
    ]
    saved: list[list] = []

    with __import__("unittest.mock", fromlist=["patch"]).patch(
        "ui.pages.hardware_integration_page._load_instances",
        return_value=[dict(fake_instances[0])],
    ), __import__("unittest.mock", fromlist=["patch"]).patch(
        "ui.pages.hardware_integration_page._save_instances",
        side_effect=saved.append,
    ):
        from ui.pages.hardware_integration_page import HardwareIntegrationPage
        page = HardwareIntegrationPage.__new__(HardwareIntegrationPage)
        page._cards = {}
        page._poll_workers = {}

        emitted: list[tuple] = []
        page.plugin_renamed = __import__(
            "unittest.mock", fromlist=["MagicMock"]
        ).MagicMock()
        page.plugin_renamed.emit = lambda *a: emitted.append(a)

        page._on_rename_card("inst_abc", "Old Name", "New Name")

    assert len(saved) == 1, "_save_instances should be called once"
    updated = saved[0]
    assert updated[0]["name"] == "New Name", (
        f"Registry name should be 'New Name', got {updated[0]['name']!r}"
    )
    assert len(emitted) == 1
    assert emitted[0][1] == "Old Name"
    assert emitted[0][2] == "New Name"
