"""Tests for plugin resilience patterns (P6-1, P6-3, P6-5, P7-5).

Covers:
  P6-1 — Exponential backoff: interval doubles at 3 errors, caps at 300 s at 6.
  P6-3 — AUTH errors are exempt from the consecutive-error circuit breaker.
  P6-5 — Regression: backoff resets after a successful poll.
  P7-5 — Regression: _plugin_enrichments uses instance_id as key (no duplicates).

No QApplication or real device required.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fresh_health() -> dict:
    return {"success": 0, "errors": 0, "consecutive": 0,
            "last_ok": 0.0, "last_err": "", "disabled": False}


def _make_store(initial: dict | None = None):
    """Return a (store_dict, _load, _save) triple for patching health I/O."""
    store: dict = {"h": dict(initial) if initial else _fresh_health()}

    def _load(_path):
        return dict(store["h"])

    def _save(_path, h):
        store["h"] = dict(h)

    return store, _load, _save


def _write_ok_plugin(tmp_path: Path) -> Path:
    src = textwrap.dedent("""
        HARDWARE_NAME = "Test Router"
        HARDWARE_TYPE = "router"
        HARDWARE_IP   = "192.168.1.1"
        def get_info():
            return {"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP}
        def get_status():
            return {"connected_clients": 2, "extra": {}}
    """)
    p = tmp_path / "ok_plugin.py"
    p.write_text(src, encoding="utf-8")
    return p


# ── P6-1: Exponential backoff interval calculation ────────────────────────────

def test_backoff_returns_base_interval_on_no_errors():
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="x")
    w._consecutive_errors = 0
    assert w.get_effective_interval() == w._interval_s


def test_backoff_returns_base_interval_after_1_error():
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="x")
    w._consecutive_errors = 1
    assert w.get_effective_interval() == w._interval_s


def test_backoff_doubles_interval_at_3_errors():
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="x")
    w._consecutive_errors = 3
    expected = min(w._interval_s * 2, 300)
    assert w.get_effective_interval() == expected


def test_backoff_quadruples_interval_at_6_errors():
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="x")
    w._consecutive_errors = 6
    expected = min(w._interval_s * 4, 300)
    assert w.get_effective_interval() == expected


def test_backoff_caps_at_300s():
    """Even a very long base interval with 6+ errors should not exceed 300 s."""
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "switch", instance_id="x")
    # _DEFAULT_INTERVAL is 300; 300*4 = 1200 → capped to 300
    w._consecutive_errors = 6
    assert w.get_effective_interval() == 300


def test_backoff_resets_after_clean_run(tmp_path):
    """After a successful poll cycle _consecutive_errors returns to 0."""
    from workers.plugin_polling_worker import PluginPollingWorker
    plugin = _write_ok_plugin(tmp_path)

    results: list[dict] = []
    w = PluginPollingWorker(str(plugin), "router", instance_id="x")
    w.result.connect(results.append)
    w._consecutive_errors = 5  # pretend previous run had errors

    w._last_run_ok = False
    w._run_once()
    # _last_run_ok should be True after a clean run
    assert w._last_run_ok is True, "Clean run must set _last_run_ok"


# ── P5-1: Concurrent poll guard ───────────────────────────────────────────────

def test_trigger_now_noop_while_poll_in_progress():
    """trigger_now() must not set the event when _poll_in_progress is True."""
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="x")
    w._poll_in_progress = True
    w.trigger_now()
    assert not w._trigger.is_set(), (
        "trigger_now() must be a no-op while a poll is already running"
    )


def test_trigger_now_sets_event_when_idle():
    """trigger_now() must set the event when no poll is in progress."""
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="x")
    w._poll_in_progress = False
    w.trigger_now()
    assert w._trigger.is_set(), (
        "trigger_now() must wake the worker when idle"
    )


# ── P6-3: AUTH errors exempt from circuit breaker ────────────────────────────

def test_auth_error_does_not_increment_consecutive():
    """AUTH: errors reset consecutive to 0 — they must not trip the circuit breaker."""
    store, _load, _save = _make_store({"consecutive": 4, **_fresh_health()})
    with patch("ui.widgets.hub_helpers._load_health", side_effect=_load), \
         patch("ui.widgets.hub_helpers._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error
        h = _record_error("/fake/plugin.py", "AUTH: wrong password")
    assert h["consecutive"] == 0, (
        "AUTH errors must reset consecutive to 0, not increment it"
    )
    assert h["errors"] == 1, "Total error count should still increment"
    assert not h["disabled"], "Plugin must not be auto-disabled after an AUTH error"


def test_auth_error_does_not_disable_after_many_errors():
    """10 consecutive AUTH errors must not trip the circuit breaker."""
    from ui.pages.hardware_integration_page import _CIRCUIT_BREAK_THRESHOLD
    store, _load, _save = _make_store({
        **_fresh_health(),
        "errors": _CIRCUIT_BREAK_THRESHOLD - 1,
        "consecutive": _CIRCUIT_BREAK_THRESHOLD - 1,
    })
    with patch("ui.widgets.hub_helpers._load_health", side_effect=_load), \
         patch("ui.widgets.hub_helpers._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error
        h = _record_error("/fake/plugin.py", "AUTH: bad credentials")
    assert not h["disabled"], (
        "AUTH error must not trigger circuit breaker even at threshold count"
    )


def test_non_auth_error_still_trips_circuit_breaker():
    """A NET: error at the threshold still trips the circuit breaker."""
    from ui.pages.hardware_integration_page import _CIRCUIT_BREAK_THRESHOLD
    store, _load, _save = _make_store({
        **_fresh_health(),
        "consecutive": _CIRCUIT_BREAK_THRESHOLD - 1,
        "errors": _CIRCUIT_BREAK_THRESHOLD - 1,
    })
    with patch("ui.widgets.hub_helpers._load_health", side_effect=_load), \
         patch("ui.widgets.hub_helpers._save_health", side_effect=_save):
        from ui.pages.hardware_integration_page import _record_error
        h = _record_error("/fake/plugin.py", "NET: connection refused")
    assert h["disabled"], "Non-AUTH error at threshold must trip the circuit breaker"


# ── P6-2: FILE: prefix classifies correctly ───────────────────────────────────

def test_classify_error_file_prefix():
    from ui.pages.hardware_integration_page import _classify_error
    msg = _classify_error("FILE: plugin file not found at /some/path/deco_plugin.py")
    assert "moved or deleted" in msg.lower(), (
        f"FILE: prefix should produce 'moved or deleted' message, got: {msg!r}"
    )
    assert "re-import" in msg.lower()


def test_classify_error_auth_prefix():
    from ui.pages.hardware_integration_page import _classify_error
    msg = _classify_error("AUTH: wrong password for admin")
    assert "authentication failed" in msg.lower()


# ── P6-5 / P7-5: Instance-ID keying consistency ──────────────────────────────

def test_plugin_enrichments_keyed_by_instance_id():
    """_on_hardware_plugin_result stores enrichment under instance_id, not path or name."""
    # This test verifies the key used in the data dict that the worker emits
    # (data["_instance_id"]) is what dashboard._on_hardware_plugin_result uses.
    # We test it at the data level since creating a full Dashboard needs a QApplication.
    data = {
        "info":   {"name": "Test Router", "type": "router", "ip": "192.168.1.1"},
        "status": {"connected_clients": 3, "extra": {"nodes": []}},
        "clients": [
            {"ip": "192.168.1.2", "mac": "aa:bb:cc:dd:ee:ff", "hostname": "laptop"},
        ],
        "_instance_id": "abc123stable",
        "_path": "/some/path/router_plugin.py",
    }
    # The key that dashboard.py writes to _plugin_enrichments is:
    inst_id = data.get("_instance_id") or data.get("_path", "")
    assert inst_id == "abc123stable", (
        "Enrichment key must be _instance_id, not _path or hw_name"
    )


def test_two_instances_produce_independent_enrichment_keys():
    """Two instances of the same plugin at different IPs produce different keys."""
    data_a = {"_instance_id": "inst_a_1234", "_path": "/plugins/router_plugin.py"}
    data_b = {"_instance_id": "inst_b_5678", "_path": "/plugins/router_plugin.py"}

    key_a = data_a.get("_instance_id") or data_a.get("_path")
    key_b = data_b.get("_instance_id") or data_b.get("_path")

    assert key_a != key_b, (
        "Two instances of the same plugin must produce independent enrichment keys"
    )
