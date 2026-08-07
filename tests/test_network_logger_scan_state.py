"""
tests/test_network_logger_scan_state.py — regression coverage (RULE-T3) for
"Scan Center shows Network Logger as Never even when it is actively running."

Two independent gaps caused the bug:
  1. ui/pages/home_data_mixin.py._refresh_scan_center() hardcoded the
     "_logger" row to state="never"/ts=0.0 instead of reading the scan
     registry like every other row.
  2. Nothing ever called _nav_set_scan_state("Network Logger", ...) from
     ui/tabs_logger.py._toggle_logger(), so the registry had no entry for
     it in the first place even after gap 1 was fixed.
"""
from __future__ import annotations

import time
import types


def _make_home_mock(qsettings_cls, registry: dict):
    from ui.pages.home_data_mixin import _HomeDataMixin

    class _Label:
        def __init__(self):
            self.style = ""
            self.text = ""

        def setStyleSheet(self, s):
            self.style = s

        def setText(self, t):
            self.text = t

    class _MockHome(_HomeDataMixin):
        pass

    home = _MockHome()
    home._scan_center_row_configs = [
        ("Network Logger", "_logger", "View →", "Network Logger"),
    ]
    home._scan_center_dot_labels = [_Label()]
    home._scan_center_age_labels = [_Label()]

    import json as _json
    qsettings_cls._store["scan_registry/state"] = _json.dumps(registry)
    return home


class _FakeQSettings:
    """In-memory QSettings stand-in shared across the modules under test."""
    _store: dict = {}

    def __init__(self, *a, **k):
        pass

    def value(self, key, default=None, type=None):  # noqa: A002 - matches QSettings signature
        v = self._store.get(key, default)
        if type is bool and isinstance(v, str):
            return v.lower() == "true"
        return v

    def setValue(self, key, value):
        self._store[key] = value


def test_refresh_scan_center_shows_running_for_active_logger(monkeypatch):
    """Gap 1: the hardcoded "_logger" -> never bypass must be removed."""
    monkeypatch.setattr("ui.pages.home_data_mixin.QSettings", _FakeQSettings)
    now = time.time()
    home = _make_home_mock(_FakeQSettings, {
        "Network Logger": {"state": "running", "ts": now, "verdict": None, "error": None},
    })

    home._refresh_scan_center()

    from ui.styles import ACCENT
    dot = home._scan_center_dot_labels[0]
    age = home._scan_center_age_labels[0]
    assert ACCENT in dot.style, "an actively-running logger must show the accent (running) dot"
    assert age.text == "Running"


def test_refresh_scan_center_shows_fresh_after_logger_stopped(monkeypatch):
    monkeypatch.setattr("ui.pages.home_data_mixin.QSettings", _FakeQSettings)
    now = time.time()
    home = _make_home_mock(_FakeQSettings, {
        "Network Logger": {"state": "fresh", "ts": now, "verdict": None, "error": None},
    })

    home._refresh_scan_center()

    from ui.styles import GREEN
    dot = home._scan_center_dot_labels[0]
    age = home._scan_center_age_labels[0]
    assert GREEN in dot.style
    assert age.text != "Never"


def test_refresh_scan_center_still_shows_never_with_empty_registry(monkeypatch):
    """No regression for a fresh install with no registry entry at all."""
    monkeypatch.setattr("ui.pages.home_data_mixin.QSettings", _FakeQSettings)
    home = _make_home_mock(_FakeQSettings, {})

    home._refresh_scan_center()

    age = home._scan_center_age_labels[0]
    assert age.text == "Never"


def test_toggle_logger_start_sets_running_scan_state(monkeypatch):
    """Gap 2: starting the logger must call _nav_set_scan_state("Network Logger", "running")."""
    from ui.tabs_logger import _LoggerTabMixin

    class _FakeSignal:
        def connect(self, *a, **k):
            pass

    class _FakeLoggerWorker:
        def __init__(self, **kw):
            self._running = False
            self.entry_received = _FakeSignal()
            self.status = _FakeSignal()
            self.rotated = _FakeSignal()
            self.error = _FakeSignal()
            self.dns_sample = _FakeSignal()   # DNS_LATENCY (Phase 4 C5)

        def start(self):
            self._running = True

        def isRunning(self):
            return self._running

        def stop_logger(self):
            self._running = False

        def get_summary(self):
            return types.SimpleNamespace(outages=[])

    monkeypatch.setattr("workers.scan_worker.LoggerWorker", _FakeLoggerWorker)
    monkeypatch.setattr("ui.widgets.toast.ToastManager.show", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr("ui.tabs_logger.QSettings", _FakeQSettings)
    _FakeQSettings._store.clear()

    calls = []

    class _MockDash(_LoggerTabMixin):
        def __init__(self):
            self._logger_worker = None
            self._log_interval = types.SimpleNamespace(value=lambda: 5)
            self._log_rotation_vals = [1, 2, 4]
            self._log_rotation = types.SimpleNamespace(currentIndex=lambda: 0)
            self._log_chk_jitter = types.SimpleNamespace(isChecked=lambda: False)
            self._log_chk_dns = types.SimpleNamespace(isChecked=lambda: False)
            self._log_chk_http = types.SimpleNamespace(isChecked=lambda: False)
            self._log_chk_arp = types.SimpleNamespace(isChecked=lambda: False)
            self._btn_log_start = types.SimpleNamespace(setText=lambda t: None)
            self._btn_log_open = types.SimpleNamespace(setEnabled=lambda v: None)
            self._log_status_lbl = types.SimpleNamespace(setText=lambda t: None)
            self._log_live_table = types.SimpleNamespace(setRowCount=lambda n: None)
            self._log_outage_table = types.SimpleNamespace(setRowCount=lambda n: None)
            self._home_page = types.SimpleNamespace(set_monitoring_status=lambda *a, **k: None)

        def _nav_set_scan_state(self, label, state, ts=None, error=None, verdict=None):
            calls.append((label, state))

        def _on_dns_sample(self, dns_ms):
            """Dashboard-level DNS_LATENCY handler (Phase 4 C5) — the mixin
            connects to it, so the stand-in has to carry it too."""

    dash = _MockDash()
    dash._toggle_logger()  # start
    assert ("Network Logger", "running") in calls

    dash._toggle_logger()  # stop
    assert ("Network Logger", "fresh") in calls
