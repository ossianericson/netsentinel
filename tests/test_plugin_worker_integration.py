"""Worker → health integration for hardware plugins (plan Step 4).

Drives ``PluginPollingWorker`` against a deterministic synthetic plugin (written to
tmp_path, no real device) through one poll, then routes the emitted signal into the
real health helpers exactly as ``HardwareIntegrationPage`` does — proving the
end-to-end accounting:

* a clean poll resets the consecutive-error counter and caches success;
* an offline poll (``extra.error`` set, ``NET:``) increments the counter;
* an ``AUTH:`` failure does NOT count toward the circuit breaker.

The worker's ``_run_once()`` is called directly on the test thread (no QThread
start) so signal delivery is synchronous and there is no timing/teardown race.
RULE-WIN4: the worker is ``deleteLater()``-d and the event queue flushed.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:  # pragma: no cover
    pytest.skip("PyQt6 not available", allow_module_level=True)

from workers.plugin_polling_worker import PluginPollingWorker
from ui.widgets import hub_helpers as hh


# ── Synthetic plugins ──────────────────────────────────────────────────────────

_OK_PLUGIN = '''\
HARDWARE_NAME = "Synthetic Router"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"

def get_info():
    return {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP}

def get_status():
    return {"connected_clients": 3, "mesh_nodes": 1, "extra": {"nodes": []}}

def get_clients():
    return [{"ip": "192.168.1.50", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "pc"}]
'''

_ERR_PLUGIN_TMPL = '''\
HARDWARE_NAME = "Synthetic Router"
HARDWARE_TYPE = "router"
HARDWARE_IP   = "192.168.1.1"

def get_info():
    return {{"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP}}

def get_status():
    return {{"connected_clients": None, "extra": {{"error": "{err}"}}}}

def get_clients():
    return []
'''


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def _run_worker_once(path):
    """Instantiate the worker, capture signals, run one poll synchronously."""
    captured = {"result": None, "error": None}
    w = PluginPollingWorker(path, "router", instance_id="iid-1", instance_ip="192.168.1.1")
    w.result.connect(lambda d: captured.__setitem__("result", d))
    w.error.connect(lambda m: captured.__setitem__("error", m))
    try:
        w._run_once()
        last_run_ok = w._last_run_ok
    finally:
        w.deleteLater()
        app = QApplication.instance()
        if app:
            for _ in range(3):
                app.processEvents()
    return captured, last_run_ok


def _route_into_health(path, captured):
    """Mirror HardwareIntegrationPage: map a worker poll outcome to health state."""
    if captured["error"] is not None:
        return hh._record_error(path, captured["error"])
    data = captured["result"] or {}
    err = (data.get("status") or {}).get("extra", {}).get("error", "")
    if err:
        return hh._record_error(path, err)
    return hh._record_success(path)


# ── Tests ───────────────────────────────────────────────────────────────────────

def test_clean_poll_emits_result_and_records_success(qt_app, isolated_settings, tmp_path):
    path = _write(tmp_path, "synth_ok.py", _OK_PLUGIN)
    captured, last_run_ok = _run_worker_once(path)

    assert captured["error"] is None
    assert captured["result"] is not None
    assert captured["result"]["status"]["connected_clients"] == 3
    assert captured["result"]["clients"][0]["ip"] == "192.168.1.50"
    assert last_run_ok is True

    h = _route_into_health(path, captured)
    assert h["success"] == 1
    assert h["consecutive"] == 0
    assert h["disabled"] is False


def test_clean_poll_resets_prior_consecutive_errors(qt_app, isolated_settings, tmp_path):
    path = _write(tmp_path, "synth_ok2.py", _OK_PLUGIN)
    # Pre-load a degraded health record.
    hh._save_health(path, {"success": 0, "errors": 4, "consecutive": 4,
                           "last_ok": 0.0, "last_err": "NET: x", "disabled": False})
    captured, _ = _run_worker_once(path)
    h = _route_into_health(path, captured)
    assert h["consecutive"] == 0  # backoff cleared by the successful poll


def test_offline_poll_records_net_error_and_increments(qt_app, isolated_settings, tmp_path):
    path = _write(tmp_path, "synth_net.py", _ERR_PLUGIN_TMPL.format(err="NET: connection refused"))
    captured, last_run_ok = _run_worker_once(path)

    # Worker still emits result (error is embedded), and marks the run not-ok.
    assert captured["result"] is not None
    assert last_run_ok is False

    h = _route_into_health(path, captured)
    assert h["errors"] == 1
    assert h["consecutive"] == 1
    assert h["disabled"] is False


def test_auth_error_does_not_trip_circuit_breaker(qt_app, isolated_settings, tmp_path):
    path = _write(tmp_path, "synth_auth.py", _ERR_PLUGIN_TMPL.format(err="AUTH: wrong password"))
    # Even after many AUTH failures the breaker must not disable the plugin.
    h = None
    for _ in range(12):
        captured, _ = _run_worker_once(path)
        h = _route_into_health(path, captured)
    assert h["consecutive"] == 0
    assert h["disabled"] is False
    assert h["errors"] == 12


def test_ten_consecutive_net_errors_disable_plugin(qt_app, isolated_settings, tmp_path):
    path = _write(tmp_path, "synth_net10.py", _ERR_PLUGIN_TMPL.format(err="NET: timed out"))
    h = None
    for _ in range(hh._CIRCUIT_BREAK_THRESHOLD):
        captured, _ = _run_worker_once(path)
        h = _route_into_health(path, captured)
    assert h["consecutive"] == hh._CIRCUIT_BREAK_THRESHOLD
    assert h["disabled"] is True
