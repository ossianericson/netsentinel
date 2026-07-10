"""Regression: MqttPage must construct even when no keyring backend exists.

CI (Linux, no keyring backend) failed the three `test_lazy_pages.py` Dashboard
tests because `MqttPage.__init__` → `_load_settings()` called
`keyring.get_password()` unguarded, which raises `keyring.errors.NoKeyringError`
on a host with no backend, aborting the whole Dashboard build. The other
secret-reading pages (notif_channel_panels, threat_intel_page) already swallow
this; MqttPage was the outlier. This test forces the failure mode directly.
"""
import pytest

pytest.importorskip("PyQt6")
keyring = pytest.importorskip("keyring")
from keyring.errors import NoKeyringError  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.pages.mqtt_page import MqttPage  # noqa: E402


def _pump():
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()


def test_mqtt_page_constructs_without_keyring_backend(qt_app, monkeypatch):
    def _boom(*_a, **_k):
        raise NoKeyringError("No recommended backend was available")

    # Simulate a headless host with no keyring backend for both read and write.
    monkeypatch.setattr("ui.pages.mqtt_page.keyring.get_password", _boom)
    monkeypatch.setattr("ui.pages.mqtt_page.keyring.set_password", _boom)

    page = MqttPage(parent=None)  # must NOT raise NoKeyringError
    try:
        # Save path must also degrade gracefully (user clicks Connect/Save).
        page._save_settings()
    finally:
        try:
            page.deleteLater()
        except RuntimeError:
            pass  # non-fatal — page may already be torn down
        _pump()
