"""
tests/test_hardware_integration.py

Regression and lifecycle tests for the Hardware Integration feature.

Covers:
  - _validate_script for all bundled plugins
  - Import / remove lifecycle (paths in QSettings)
  - Password save → keyring → plugin reads it
  - Startup crash guard: corrupt last_result (clients / nodes as strings)
  - Type-mismatch guard: meta["type"] != last_result["info"]["type"]
  - QTimer dangling-reference guard (_save_password / _forget_password)
  - Auto-import of bundled plugins on empty QSettings
  - _RouterDetailPanel.update defensive input handling
  - _ModemDetailPanel.update defensive input handling
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Qt bootstrap ───────────────────────────────────────────────────────────────
# Conftest owns the session-scoped QApplication; do NOT create one here.
try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)

# ── Module imports (patch keyring + worker so page constructs cleanly) ─────────

with (
    patch("keyring.get_password", return_value=None),
    patch("workers.plugin_polling_worker.PluginPollingWorker", MagicMock()),
):
    from ui.pages.hardware_integration_page import (
        HardwareIntegrationPage,
        HubCard,
        _ModemDetailPanel,
        _RouterDetailPanel,
        _validate_script,
        _safe_set_text,
    )

# ── Paths ──────────────────────────────────────────────────────────────────────

_REPO  = Path(__file__).parent.parent
_ZTE   = str(_REPO / "plugins" / "zte_plugin.py")
_DECO  = str(_REPO / "plugins" / "deco_plugin.py")

# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_qsettings(monkeypatch):
    """Isolate every test from real QSettings and other tests."""
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page._load_paths", lambda: []
    )
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page._save_paths", lambda _: None
    )
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page._load_last_result", lambda _: None
    )
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page._save_last_result", lambda *_: None
    )
    # Prevent QFileSystemWatcher from starting OS-level file-watching threads
    # (ReadDirectoryChangesW on Windows) that don't clean up reliably in tests.
    # Use a lambda to ignore the parent arg so MagicMock doesn't treat it as spec.
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page.QFileSystemWatcher",
        lambda *a, **kw: MagicMock(),
    )


def _cleanup_page(p):
    """Stop Qt resources on HardwareIntegrationPage before deleting."""
    app = QApplication.instance()
    try:
        # Stop the 30-second tick timer so it cannot fire after deletion
        if hasattr(p, "_tick_timer"):
            p._tick_timer.stop()
    except RuntimeError:
        pass  # non-fatal
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # non-fatal
    if app:
        for _ in range(3):
            app.processEvents()


@pytest.fixture
def page(monkeypatch):
    p = HardwareIntegrationPage()
    yield p
    _cleanup_page(p)


# ─────────────────────────────────────────────────────────────────────────────
# 1. _validate_script — bundled plugins
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_zte_plugin_ok():
    ok, msg, meta = _validate_script(_ZTE)
    assert ok, f"ZTE plugin failed validation: {msg}"


def test_validate_zte_plugin_type_modem():
    _, _, meta = _validate_script(_ZTE)
    assert meta["type"] == "modem"


def test_validate_zte_plugin_ip_nonempty():
    _, _, meta = _validate_script(_ZTE)
    assert meta["ip"]  # has a default IP constant


def test_validate_deco_plugin_ok():
    ok, msg, meta = _validate_script(_DECO)
    assert ok, f"Deco plugin failed validation: {msg}"


def test_validate_deco_plugin_type_router():
    _, _, meta = _validate_script(_DECO)
    assert meta["type"] == "router"


def test_validate_deco_plugin_ip_nonempty():
    _, _, meta = _validate_script(_DECO)
    assert meta["ip"]


def test_validate_all_bundled_plugins():
    """Every *_plugin.py in plugins/ must pass _validate_script."""
    plugins_dir = _REPO / "plugins"
    if not plugins_dir.is_dir():
        pytest.skip("plugins/ directory not found")
    failures = []
    for pyf in sorted(plugins_dir.glob("*_plugin.py")):
        if pyf.name == "template_plugin.py":
            continue  # template intentionally incomplete
        ok, msg, _ = _validate_script(str(pyf))
        if not ok:
            failures.append(f"{pyf.name}: {msg}")
    assert not failures, "Plugins failed validation:\n" + "\n".join(failures)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Import / remove lifecycle
# ─────────────────────────────────────────────────────────────────────────────

def test_import_adds_to_paths(monkeypatch):
    saved = []
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths", lambda: [])
    monkeypatch.setattr("ui.pages.hardware_integration_page._save_paths",
                        lambda p: saved.extend(p))
    # simulate import of ZTE
    from ui.pages.hardware_integration_page import _save_paths as sp
    paths = []
    paths.append(_ZTE)
    sp(paths)
    assert _ZTE in saved


def test_remove_plugin_drops_path(monkeypatch):
    existing = [_ZTE, _DECO]
    saved = []
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths",
                        lambda: list(existing))
    monkeypatch.setattr("ui.pages.hardware_integration_page._save_paths",
                        lambda p: saved.append(list(p)))
    # simulate _remove_plugin logic
    paths = list(existing)
    paths.remove(_ZTE)
    from ui.pages.hardware_integration_page import _save_paths as sp
    sp(paths)
    assert saved and _ZTE not in saved[-1]
    assert _DECO in saved[-1]


def test_page_shows_empty_when_no_paths(page):
    """With no paths, the hub body must not crash (empty label shown)."""
    QApplication.instance().processEvents()  # no exception means pass


# ─────────────────────────────────────────────────────────────────────────────
# 3. Password save → keyring
# ─────────────────────────────────────────────────────────────────────────────

def test_save_password_writes_to_keyring(monkeypatch):
    saved = {}

    def fake_set(service, key, value):
        saved[(service, key)] = value

    monkeypatch.setattr("keyring.set_password", fake_set)
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths",
                        lambda: [_ZTE])

    ok, _, meta = _validate_script(_ZTE)
    hw_ip = meta["ip"]

    card = HubCard(_ZTE, meta, None)
    card._pw_edit.setText("secret123")
    card._save_password(hw_ip, card._pw_edit, card._pw_status)

    assert ("NetSentinel/hardware", hw_ip) in saved
    assert saved[("NetSentinel/hardware", hw_ip)] == "secret123"
    card.deleteLater()
    QApplication.instance().processEvents()


def test_save_password_empty_shows_error(monkeypatch):
    monkeypatch.setattr("keyring.set_password", lambda *_: None)
    _, _, meta = _validate_script(_ZTE)
    card = HubCard(_ZTE, meta, None)
    card._pw_edit.setText("")
    card._save_password(meta["ip"], card._pw_edit, card._pw_status)
    assert card._pw_status.text() != ""  # some error/feedback text set
    card.deleteLater()
    QApplication.instance().processEvents()


def test_forget_password_calls_delete_for_all_services(monkeypatch):
    deleted = []

    def fake_delete(service, key):
        deleted.append((service, key))

    monkeypatch.setattr("keyring.delete_password", fake_delete)

    _, _, meta = _validate_script(_ZTE)
    card = HubCard(_ZTE, meta, None)
    card._forget_password(meta["ip"], card._pw_status)

    services = {s for s, _ in deleted}
    assert "NetSentinel/hardware" in services
    card.deleteLater()
    QApplication.instance().processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Startup crash guard: corrupt last_result (clients / nodes as strings)
# ─────────────────────────────────────────────────────────────────────────────

def test_hubcard_survives_corrupt_clients_strings(monkeypatch):
    """HubCard must not crash when last_result['clients'] is a list of strings."""
    _, _, meta = _validate_script(_DECO)
    corrupt = {
        "info":    {"type": "router", "name": "Deco", "ip": "192.168.68.1"},
        "status":  {"mesh_nodes": 2, "connected_clients": 3, "extra": {"nodes": []}},
        "clients": ["192.168.68.10", "192.168.68.11"],  # strings, not dicts
        "_ts":     time.time(),
    }
    card = HubCard(_DECO, meta, corrupt)  # must not raise
    card.deleteLater()
    QApplication.instance().processEvents()


def test_hubcard_survives_corrupt_nodes_strings(monkeypatch):
    """HubCard must not crash when last_result status.extra.nodes is strings."""
    _, _, meta = _validate_script(_DECO)
    corrupt = {
        "info":    {"type": "router", "name": "Deco", "ip": "192.168.68.1"},
        "status":  {"mesh_nodes": 2, "connected_clients": 1,
                    "extra": {"nodes": ["node1", "node2"]}},  # strings, not dicts
        "clients": [{"ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:ff",
                     "hostname": "phone", "band": "5G", "unit": "Main",
                     "upload_kbps": 100, "download_kbps": 500}],
        "_ts":     time.time(),
    }
    card = HubCard(_DECO, meta, corrupt)  # must not raise
    card.deleteLater()
    QApplication.instance().processEvents()


def test_hubcard_survives_none_last_result():
    """HubCard with last_result=None must construct without error."""
    _, _, meta = _validate_script(_ZTE)
    card = HubCard(_ZTE, meta, None)
    card.deleteLater()
    QApplication.instance().processEvents()


def test_hubcard_survives_non_dict_last_result():
    """HubCard with last_result='garbage' must not crash."""
    _, _, meta = _validate_script(_DECO)
    card = HubCard(_DECO, meta, "garbage")  # type: ignore[arg-type]
    card.deleteLater()
    QApplication.instance().processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# 5. Type-mismatch guard: meta type != last_result info type
# ─────────────────────────────────────────────────────────────────────────────

def test_type_mismatch_meta_unknown_data_modem(monkeypatch):
    """meta['type']='unknown' (validate failed) + last_result info type='modem'
    was the root cause of the startup crash. Must not crash."""
    bad_meta = {"name": "zte_plugin", "type": "unknown", "ip": "192.168.254.1"}
    modem_result = {
        "info":    {"type": "modem", "name": "ZTE", "ip": "192.168.254.1"},
        "status":  {"wan_ip": None, "extra": {"nr5g_band": "n78"}},
        "clients": [],
        "_ts":     time.time(),
    }
    card = HubCard(_ZTE, bad_meta, modem_result)  # must not raise
    card.deleteLater()
    QApplication.instance().processEvents()


def test_type_mismatch_meta_modem_data_router(monkeypatch):
    """meta['type']='modem' but last_result info type='router' must not crash."""
    modem_meta = {"name": "ZTE", "type": "modem", "ip": "192.168.254.1"}
    router_result = {
        "info":    {"type": "router", "name": "Deco", "ip": "192.168.68.1"},
        "status":  {"mesh_nodes": 1, "connected_clients": 0,
                    "extra": {"nodes": []}},
        "clients": [],
        "_ts":     time.time(),
    }
    card = HubCard(_ZTE, modem_meta, router_result)  # must not raise
    card.deleteLater()
    QApplication.instance().processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# 6. QTimer dangling-reference guard
# ─────────────────────────────────────────────────────────────────────────────

def test_safe_set_text_survives_deleted_widget(monkeypatch):
    """_safe_set_text must silently ignore RuntimeError for deleted widgets."""
    label = MagicMock()
    label.setText.side_effect = RuntimeError("wrapped C++ object deleted")
    _safe_set_text(label, "")  # must not raise


def test_safe_set_text_sets_text_on_live_widget():
    from PyQt6.QtWidgets import QLabel
    lbl = QLabel("before")
    _safe_set_text(lbl, "after")
    assert lbl.text() == "after"
    lbl.deleteLater()
    QApplication.instance().processEvents()


def test_delete_card_while_password_save_timer_pending(monkeypatch):
    """Deleting a HubCard while its 3-second feedback timer is pending
    must not crash when the timer fires."""
    monkeypatch.setattr("keyring.set_password", lambda *_: None)
    _, _, meta = _validate_script(_ZTE)
    card = HubCard(_ZTE, meta, None)
    card._pw_edit.setText("pw")
    card._save_password(meta["ip"], card._pw_edit, card._pw_status)
    # Immediately delete the card — timer will fire after deleteLater
    card.deleteLater()
    QApplication.instance().processEvents()
    # Fire all pending timers (forces the lambda to run on deleted widget)
    from PyQt6.QtTest import QTest
    QTest.qWait(50)
    QApplication.instance().processEvents()
    # If we reach here without RuntimeError, the guard works


# ─────────────────────────────────────────────────────────────────────────────
# 7. No auto-import on empty QSettings (regression guard)
# ─────────────────────────────────────────────────────────────────────────────

def test_no_auto_import_when_paths_empty(monkeypatch):
    """When no instances are registered, _rebuild_hub must NOT auto-save anything."""
    saved = []
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths",
                        lambda: [])
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_instances",
                        lambda: [])
    monkeypatch.setattr("ui.pages.hardware_integration_page._save_paths",
                        lambda p: saved.append(list(p)))
    monkeypatch.setattr("ui.pages.hardware_integration_page._save_instances",
                        lambda _: saved.append("instances"))
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_last_result",
                        lambda _: None)

    p = HardwareIntegrationPage()
    QApplication.instance().processEvents()
    try:
        assert not saved, (
            "_save_paths/_save_instances was called — auto-import must not run on first launch"
        )
    finally:
        _cleanup_page(p)


def test_auto_import_skipped_when_paths_already_set(monkeypatch):
    """When instances are already registered, no new _save_instances call expected."""
    saved = []
    _inst = [{"id": "abc123", "path": _ZTE, "ip": "192.168.254.1", "name": "ZTE MC889"}]
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_paths",
                        lambda: [_ZTE])
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_instances",
                        lambda: _inst)
    monkeypatch.setattr("ui.pages.hardware_integration_page._save_paths",
                        lambda p: saved.append(list(p)))
    monkeypatch.setattr("ui.pages.hardware_integration_page._save_instances",
                        lambda _: saved.append("instances"))
    monkeypatch.setattr("ui.pages.hardware_integration_page._load_last_result",
                        lambda _: None)

    p = HardwareIntegrationPage()
    QApplication.instance().processEvents()
    try:
        assert not saved, "_save_paths/_save_instances called unexpectedly when already set"
    finally:
        _cleanup_page(p)


# ─────────────────────────────────────────────────────────────────────────────
# 8. _RouterDetailPanel.update — defensive input handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def router_panel():
    p = _RouterDetailPanel()
    yield p
    p.deleteLater()
    QApplication.instance().processEvents()


def test_router_panel_update_empty(router_panel):
    router_panel.update({}, [])  # must not raise


def test_router_panel_update_valid_clients(router_panel):
    clients = [
        {"ip": "10.0.0.1", "mac": "aa:bb:cc:dd:ee:01", "hostname": "laptop",
         "band": "5G", "unit": "Main", "upload_kbps": 100, "download_kbps": 500},
    ]
    router_panel.update({"connected_clients": 1, "extra": {"nodes": []}}, clients)


def test_router_panel_update_string_clients_ignored(router_panel):
    """String items in clients must be silently skipped — no crash."""
    router_panel.update({}, ["192.168.1.1", "192.168.1.2"])


def test_router_panel_update_string_nodes_ignored(router_panel):
    """String items in nodes must be silently skipped — no crash."""
    status = {"extra": {"nodes": ["node-a", "node-b"]}, "connected_clients": 0}
    router_panel.update(status, [])


def test_router_panel_update_non_dict_status(router_panel):
    """Non-dict status (e.g. string) must be handled gracefully."""
    router_panel.update("bad-status", [])  # type: ignore[arg-type]


def test_router_panel_update_mixed_valid_invalid_clients(router_panel):
    """Mix of dicts and strings: only dicts rendered."""
    clients = [
        "string-item",
        {"ip": "10.0.0.2", "mac": "bb:cc:dd:ee:ff:00", "hostname": "phone",
         "band": "2.4G", "unit": "Main", "upload_kbps": 50, "download_kbps": 200},
    ]
    router_panel.update({"connected_clients": 1, "extra": {"nodes": []}}, clients)
    assert router_panel._client_table.rowCount() == 1  # only the dict rendered


# ─────────────────────────────────────────────────────────────────────────────
# 9. _ModemDetailPanel.update — defensive input handling
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def modem_panel():
    p = _ModemDetailPanel()
    yield p
    p.deleteLater()
    QApplication.instance().processEvents()


def test_modem_panel_update_empty(modem_panel):
    modem_panel.update({})


def test_modem_panel_update_5g_signal(modem_panel):
    extra = {
        "nr5g_band": "n78", "nr5g_rsrp_dbm": -85.5,
        "nr5g_sinr_db": 12.3, "nr5g_rsrq_db": -10.1,
    }
    modem_panel.update(extra)


def test_modem_panel_update_none_values(modem_panel):
    modem_panel.update({"nr5g_rsrp_dbm": None, "lte_rsrp_dbm": None})


# ─────────────────────────────────────────────────────────────────────────────
# 10. update_result on live HubCard
# ─────────────────────────────────────────────────────────────────────────────

def test_hubcard_update_result_router(monkeypatch):
    """update_result with a valid router payload must not crash."""
    _, _, meta = _validate_script(_DECO)
    card = HubCard(_DECO, meta, None)
    data = {
        "info":    {"type": "router", "name": "Deco", "ip": "192.168.68.1"},
        "status":  {"mesh_nodes": 2, "connected_clients": 5,
                    "extra": {"nodes": [
                        {"name": "Main", "role": "master",
                         "mac": "aa:bb:cc:dd:ee:01", "ip": "192.168.68.1"},
                    ]}},
        "clients": [
            {"ip": "10.0.0.5", "mac": "bb:cc:dd:ee:ff:01", "hostname": "laptop",
             "band": "5G", "unit": "Main", "upload_kbps": 200, "download_kbps": 800},
        ],
        "_ts": time.time(),
    }
    card.update_result(data, time.time())  # must not raise
    card.deleteLater()
    QApplication.instance().processEvents()


def test_hubcard_update_result_modem(monkeypatch):
    """update_result with a valid modem payload must not crash."""
    _, _, meta = _validate_script(_ZTE)
    card = HubCard(_ZTE, meta, None)
    data = {
        "info":    {"type": "modem", "name": "ZTE MC889", "ip": "192.168.254.1"},
        "status":  {"wan_ip": "1.2.3.4", "connected_clients": None,
                    "extra": {"nr5g_band": "n78", "nr5g_rsrp_dbm": -88.0,
                              "nr5g_sinr_db": 10.5, "network_type": "NR5G"}},
        "clients": [],
        "_ts": time.time(),
    }
    card.update_result(data, time.time())  # must not raise
    card.deleteLater()
    QApplication.instance().processEvents()


# ─────────────────────────────────────────────────────────────────────────────
# 11. PB-9 — .nspkg import button and Browse tab (page-level integration)
# ─────────────────────────────────────────────────────────────────────────────

def test_hardware_page_has_nspkg_button(page):
    """HardwareIntegrationPage must expose a _btn_nspkg widget (PB-9)."""
    assert hasattr(page, "_btn_nspkg"), "_btn_nspkg button is missing from HardwareIntegrationPage"
    from PyQt6.QtWidgets import QPushButton
    assert isinstance(page._btn_nspkg, QPushButton)


def test_hardware_page_nspkg_button_not_hidden(page):
    """_btn_nspkg must not be explicitly hidden (visible once page is shown)."""
    assert not page._btn_nspkg.isHidden()


def test_hardware_page_has_browse_tab(page):
    """Hardware page must have a 'Browse' tab (PB-8 community index)."""
    assert page._tabs is not None
    tab_labels = [page._tabs.tabText(i) for i in range(page._tabs.count())]
    assert "Browse" in tab_labels, f"Expected 'Browse' tab, got tabs: {tab_labels}"


def test_hardware_page_browse_tab_has_status_label(page):
    """Browse tab must expose _browse_status label for fetch feedback."""
    assert hasattr(page, "_browse_status"), "_browse_status label is missing"
    from PyQt6.QtWidgets import QLabel
    assert isinstance(page._browse_status, QLabel)


def test_on_import_nspkg_cancelled_when_no_file(page, monkeypatch):
    """_on_import_nspkg must silently return when the file dialog is cancelled."""
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page.QFileDialog.getOpenFileName",
        lambda *a, **kw: ("", ""),
    )
    called = []
    monkeypatch.setattr(page, "_import_bundled", lambda p: called.append(p))
    page._on_import_nspkg()
    assert not called, "_import_bundled must not be called when dialog is cancelled"


def test_on_import_nspkg_invalid_bundle_sets_status(page, monkeypatch, tmp_path):
    """_on_import_nspkg must show an error status when unpack_nspkg raises."""
    fake_zip = tmp_path / "bad.nspkg"
    fake_zip.write_bytes(b"not a zip")
    monkeypatch.setattr(
        "ui.pages.hardware_integration_page.QFileDialog.getOpenFileName",
        lambda *a, **kw: (str(fake_zip), ""),
    )
    page._on_import_nspkg()
    # Status label should contain an error message
    assert page._status_lbl.text() != "", "Status label must show an error for invalid bundle"


# ─────────────────────────────────────────────────────────────────────────────
# 12. CONFIG_SCHEMA support — PB-7
# ─────────────────────────────────────────────────────────────────────────────

_PLUGIN_WITH_SCHEMA = (
    "HARDWARE_NAME = 'Schema Plugin'\n"
    "HARDWARE_TYPE = 'router'\n"
    "HARDWARE_IP   = '192.168.1.1'\n"
    "CONFIG_SCHEMA = {\n"
    "    'poll_interval': {'type': 'int',  'default': 60, 'min': 10, 'max': 600},\n"
    "    'verify_ssl':    {'type': 'bool', 'default': True},\n"
    "    'base_url':      {'type': 'str',  'default': 'http://192.168.1.1'},\n"
    "}\n"
    "def get_info(): return {}\n"
    "def get_status(): return {}\n"
)

_PLUGIN_NO_SCHEMA = (
    "HARDWARE_NAME = 'Bare Plugin'\n"
    "HARDWARE_TYPE = 'router'\n"
    "HARDWARE_IP   = '192.168.1.1'\n"
    "def get_info(): return {}\n"
    "def get_status(): return {}\n"
)


def test_validate_script_extracts_config_schema(tmp_path):
    """_validate_script must return a non-empty config_schema when plugin declares it."""
    p = tmp_path / "schema_plugin.py"
    p.write_text(_PLUGIN_WITH_SCHEMA, encoding="utf-8")
    ok, _, meta = _validate_script(str(p))
    assert ok
    cs = meta.get("config_schema", {})
    assert "poll_interval" in cs
    assert cs["poll_interval"]["type"] == "int"
    assert "verify_ssl" in cs
    assert cs["verify_ssl"]["type"] == "bool"


def test_validate_script_no_schema_returns_empty(tmp_path):
    """_validate_script returns an empty config_schema when plugin omits CONFIG_SCHEMA."""
    p = tmp_path / "bare_plugin.py"
    p.write_text(_PLUGIN_NO_SCHEMA, encoding="utf-8")
    ok, _, meta = _validate_script(str(p))
    assert ok
    assert meta.get("config_schema") == {}


def test_hubcard_configure_button_hidden_no_schema():
    """Configure button must be invisible when config_schema is empty (PB-7)."""
    meta = {"name": "T", "type": "router", "ip": "1.2.3.4", "config_schema": {}}
    card = HubCard("dummy.py", meta, None)
    try:
        assert not card._btn_configure.isVisible()
    finally:
        card.deleteLater()
        QApplication.instance().processEvents()


def test_hubcard_configure_button_visible_with_schema():
    """Configure button must NOT be hidden when config_schema is non-empty (PB-7)."""
    schema = {"poll_interval": {"type": "int", "default": 60}}
    meta = {"name": "T", "type": "router", "ip": "1.2.3.4", "config_schema": schema}
    card = HubCard("dummy.py", meta, None)
    try:
        assert not card._btn_configure.isHidden()
    finally:
        card.deleteLater()
        QApplication.instance().processEvents()


def test_build_config_panel_widget_types():
    """int → QSpinBox, bool → QCheckBox, str → QLineEdit (PB-7)."""
    from PyQt6.QtWidgets import QSpinBox, QCheckBox, QLineEdit
    schema = {
        "count":  {"type": "int",  "default": 10},
        "active": {"type": "bool", "default": False},
        "label":  {"type": "str",  "default": "hello"},
    }
    meta = {"name": "T", "type": "router", "ip": "1.2.3.4", "config_schema": schema}
    card = HubCard("dummy.py", meta, None)
    try:
        assert isinstance(card._config_fields["count"],  QSpinBox)
        assert isinstance(card._config_fields["active"], QCheckBox)
        assert isinstance(card._config_fields["label"],  QLineEdit)
    finally:
        card.deleteLater()
        QApplication.instance().processEvents()


def test_apply_config_persists_values(monkeypatch):
    """_apply_config persists field values via _save_instance_config (PB-7)."""
    from PyQt6.QtWidgets import QSpinBox
    saved = {}
    monkeypatch.setattr(
        "ui.widgets.hub_card._save_instance_config",
        lambda iid, cfg: saved.update(cfg),
    )
    schema = {"poll_interval": {"type": "int", "default": 60}}
    meta = {"name": "T", "type": "router", "ip": "1.2.3.4", "config_schema": schema}
    card = HubCard("dummy.py", meta, None)
    try:
        spin = card._config_fields["poll_interval"]
        assert isinstance(spin, QSpinBox)
        spin.setValue(120)
        card._apply_config()
        assert saved.get("poll_interval") == 120
    finally:
        card.deleteLater()
        QApplication.instance().processEvents()


def test_plugin_polling_worker_interval_from_config():
    """poll_interval in config overrides the hardware-type default interval (PB-7)."""
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("dummy.py", "router", config={"poll_interval": 15})
    assert w._interval_s == 15


def test_plugin_polling_worker_passes_config_to_get_status(tmp_path):
    """Worker passes config dict as get_status(config=...) kwarg (PB-7)."""
    out_file = tmp_path / "config_call.json"
    plugin = tmp_path / "spy_hw.py"
    plugin.write_text(
        "HARDWARE_NAME = 'Spy'\n"
        "HARDWARE_TYPE = 'router'\n"
        "HARDWARE_IP   = '1.2.3.4'\n"
        "def get_info(): return {'name': 'Spy', 'type': 'router'}\n"
        "def get_status(config=None):\n"
        "    import json as _j\n"
        "    from pathlib import Path\n"
        f"    Path({str(out_file)!r}).write_text(_j.dumps(config))\n"
        "    return {'connected_clients': 0, 'extra': {}}\n",
        encoding="utf-8",
    )
    from workers.plugin_polling_worker import PluginPollingWorker
    cfg = {"poll_interval": 10, "verify_ssl": True}
    w = PluginPollingWorker(str(plugin), "router", config=cfg)
    w._run_once()
    assert out_file.exists(), "get_status(config=...) was not called by the worker"
    received = json.loads(out_file.read_text())
    assert received == cfg
