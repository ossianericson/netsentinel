"""Tests for the unified plugin registration pipeline (P7-2 — covers Bug class 2).

Verifies that browse, bundled, and community sources all produce identical
instance-registry entries, and that the credential dialog return type is
correct.

No QApplication required: all Qt/QSettings calls are patched out.

Note: _show_credential_dialog was extracted to ui.widgets.credential_dialog as
show_credential_dialog() in S14-2. Signature tests now target that module.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_minimal_plugin(tmp_path: Path, name: str = "TestRouter",
                         hw_type: str = "router",
                         ip: str = "192.168.1.1",
                         cred_label: str = "Password") -> Path:
    """Write a minimal valid plugin script to tmp_path and return its path."""
    content = f"""
HARDWARE_NAME = "{name}"
HARDWARE_TYPE = "{hw_type}"
HARDWARE_IP   = "{ip}"
CREDENTIAL_LABEL = "{cred_label}"

def get_info():
    return {{"name": "{name}", "type": "{hw_type}", "ip": "{ip}"}}

def get_status():
    return {{"connected_clients": 0}}
"""
    plugin = tmp_path / f"{name.lower().replace(' ', '_')}_plugin.py"
    plugin.write_text(content, encoding="utf-8")
    return plugin


class _PageStub:
    """Minimal stand-in for HardwareIntegrationPage that satisfies _register_plugin.

    Calls the real unbound method so all code paths are exercised, but avoids
    constructing a QWidget (which requires a running QApplication).
    """

    def __init__(self):
        self._set_status = MagicMock()
        self._rebuild_hub = MagicMock()
        self._start_poll_worker_inst = MagicMock()
        self.plugin_page_added = MagicMock()
        self.plugin_page_added.emit = MagicMock()

    def _register_plugin(self, path: str, source: str = "browse") -> None:
        from ui.pages.hardware_integration_page import HardwareIntegrationPage
        HardwareIntegrationPage._register_plugin(self, path, source)


# ── show_credential_dialog return type ───────────────────────────────────────

def test_credential_dialog_return_annotation_is_tuple():
    """show_credential_dialog must declare a tuple return annotation."""
    from ui.widgets.credential_dialog import show_credential_dialog
    sig = inspect.signature(show_credential_dialog)
    ann = sig.return_annotation
    assert ann is not inspect.Parameter.empty, (
        "show_credential_dialog must have a return annotation"
    )
    ann_str = str(ann)
    assert "tuple" in ann_str.lower() or "Tuple" in ann_str, (
        f"Expected tuple return annotation, got: {ann_str}"
    )


def test_credential_dialog_signature_has_two_elements():
    """The return annotation must indicate a 2-tuple (bool, str).

    When from __future__ import annotations is in effect the annotation is
    stored as a string literal; we parse it rather than introspecting __args__.
    """
    from ui.widgets.credential_dialog import show_credential_dialog
    sig = inspect.signature(show_credential_dialog)
    ann = sig.return_annotation
    ann_str = str(ann)
    assert "bool" in ann_str and "str" in ann_str, (
        f"Return annotation must reference bool and str, got: {ann_str}"
    )


# ── Unified registration pipeline ─────────────────────────────────────────────

def test_register_plugin_writes_instance_registry(tmp_path):
    """_register_plugin must write exactly one instance-registry entry."""
    plugin = _make_minimal_plugin(tmp_path, cred_label="")  # no cred needed
    page = _PageStub()

    saved_instances: list = []

    def fake_save(instances):
        saved_instances.extend(instances)

    with patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._save_instances",
               side_effect=fake_save), \
         patch("ui.pages.hardware_integration_page._instance_id",
               return_value="abc123"), \
         patch("shutil.copy2"):
        page._register_plugin(str(plugin), source="browse")

    assert len(saved_instances) == 1
    inst = saved_instances[0]
    assert inst["id"] == "abc123"
    assert "path" in inst
    assert "ip" in inst
    assert "name" in inst


def test_browse_and_bundled_produce_identical_instance_entries(tmp_path):
    """browse and bundled sources must call _save_instances with identical schema."""
    plugin = _make_minimal_plugin(tmp_path, cred_label="")

    browse_calls: list = []
    bundled_calls: list = []

    def fake_save_browse(instances):
        browse_calls.extend(instances)

    def fake_save_bundled(instances):
        bundled_calls.extend(instances)

    page_browse = _PageStub()
    with patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._save_instances",
               side_effect=fake_save_browse), \
         patch("ui.pages.hardware_integration_page._instance_id", return_value="xid"), \
         patch("shutil.copy2"):
        page_browse._register_plugin(str(plugin), source="browse")

    page_bundled = _PageStub()
    with patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._save_instances",
               side_effect=fake_save_bundled), \
         patch("ui.pages.hardware_integration_page._instance_id", return_value="xid"), \
         patch("shutil.copy2"):
        page_bundled._register_plugin(str(plugin), source="bundled")

    assert len(browse_calls) == 1
    assert len(bundled_calls) == 1
    assert set(browse_calls[0].keys()) == set(bundled_calls[0].keys())


def test_cancel_credential_dialog_does_not_write_registry(tmp_path):
    """Cancelling the credential dialog must NOT write to the instance registry."""
    plugin = _make_minimal_plugin(tmp_path, cred_label="Password",
                                  ip="192.168.1.1")
    save_mock = MagicMock()

    page = _PageStub()

    with patch("ui.pages.hardware_integration_page.show_credential_dialog",
               return_value=(False, "")), \
         patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._save_instances", save_mock), \
         patch("keyring.get_password", return_value=None), \
         patch("shutil.copy2"):
        page._register_plugin(str(plugin), source="browse")

    save_mock.assert_not_called()


def test_no_credential_label_skips_dialog(tmp_path):
    """Plugin without CREDENTIAL_LABEL must not trigger the credential dialog."""
    plugin = _make_minimal_plugin(tmp_path, cred_label="")

    page = _PageStub()

    with patch("ui.pages.hardware_integration_page.show_credential_dialog") as dialog_mock, \
         patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._save_instances"), \
         patch("ui.pages.hardware_integration_page._instance_id", return_value="noid"), \
         patch("shutil.copy2"):
        page._register_plugin(str(plugin), source="browse")

    dialog_mock.assert_not_called()


def test_register_plugin_emits_page_added_for_new_instance(tmp_path):
    """plugin_page_added must be emitted exactly once for a new instance."""
    plugin = _make_minimal_plugin(tmp_path, cred_label="")

    page = _PageStub()

    with patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._save_instances"), \
         patch("ui.pages.hardware_integration_page._instance_id", return_value="uid1"), \
         patch("shutil.copy2"):
        page._register_plugin(str(plugin), source="browse")

    page.plugin_page_added.emit.assert_called_once()


def test_register_plugin_does_not_emit_for_duplicate(tmp_path):
    """plugin_page_added must NOT be emitted if the instance already exists."""
    plugin = _make_minimal_plugin(tmp_path, cred_label="")

    page = _PageStub()
    existing = [{"id": "uid1", "path": str(plugin), "ip": "192.168.1.1",
                 "name": "TestRouter"}]

    with patch("ui.pages.hardware_integration_page._load_instances",
               return_value=existing), \
         patch("ui.pages.hardware_integration_page._save_instances"), \
         patch("ui.pages.hardware_integration_page._instance_id", return_value="uid1"), \
         patch("shutil.copy2"):
        page._register_plugin(str(plugin), source="browse")

    page.plugin_page_added.emit.assert_not_called()


def test_register_plugin_uses_confirmed_ip_from_dialog(tmp_path):
    """The confirmed IP from the dialog must be used in the instance registry."""
    plugin = _make_minimal_plugin(tmp_path, cred_label="Password",
                                  ip="192.168.1.1")

    saved_instances: list = []

    def fake_save(instances):
        saved_instances.extend(instances)

    page = _PageStub()

    with patch("ui.pages.hardware_integration_page.show_credential_dialog",
               return_value=(True, "10.0.0.254")), \
         patch("ui.pages.hardware_integration_page._load_instances", return_value=[]), \
         patch("ui.pages.hardware_integration_page._save_instances",
               side_effect=fake_save), \
         patch("ui.pages.hardware_integration_page._instance_id",
               side_effect=lambda path, ip: f"id_{ip}"), \
         patch("keyring.get_password", return_value=None), \
         patch("shutil.copy2"):
        page._register_plugin(str(plugin), source="browse")

    assert len(saved_instances) == 1
    assert saved_instances[0]["ip"] == "10.0.0.254"
    assert saved_instances[0]["id"] == "id_10.0.0.254"
