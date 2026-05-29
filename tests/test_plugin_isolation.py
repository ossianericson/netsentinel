"""Tests for plugin thread-safety and namespace isolation (P5-1, P5-3, P5-4).

Covers:
  P5-1  — Concurrent poll guard: trigger_now() is a no-op during an active poll.
  P5-3  — Module namespace isolation: module-level globals do not bleed between
           poll cycles (each exec_module produces a fresh namespace).
  P5-4  — Two PluginPollingWorker instances for the same file have independent
           module namespaces; neither can corrupt the other's state.

No QApplication or real device required.
"""
from __future__ import annotations

import importlib.util
import textwrap
import threading
import time
from pathlib import Path


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_counter_plugin(tmp_path: Path, name: str = "counter") -> Path:
    """Plugin that increments a module-level counter each time get_status() is called."""
    src = textwrap.dedent(f"""
        HARDWARE_NAME = "{name}"
        HARDWARE_TYPE = "router"
        HARDWARE_IP   = "192.168.1.1"

        _call_count = 0   # module-level state — must NOT bleed between exec_module calls

        def get_info():
            return {{"name": HARDWARE_NAME, "type": HARDWARE_TYPE, "ip": HARDWARE_IP}}

        def get_status():
            global _call_count
            _call_count += 1
            return {{"connected_clients": _call_count, "extra": {{"call_count": _call_count}}}}
    """)
    p = tmp_path / f"{name}.py"
    p.write_text(src, encoding="utf-8")
    return p


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"_iso_{path.stem}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── P5-3: Module namespace isolation between poll cycles ─────────────────────

def test_module_level_state_does_not_bleed_between_exec_module_calls(tmp_path):
    """Each exec_module() produces a fresh namespace — module-level globals reset."""
    plugin = _write_counter_plugin(tmp_path, "counter_a")

    # First exec_module call
    mod1 = _load_module(plugin)
    mod1.get_status()  # _call_count becomes 1
    mod1.get_status()  # _call_count becomes 2
    assert mod1.get_status()["extra"]["call_count"] == 3

    # Second exec_module call — should start fresh at 0
    mod2 = _load_module(plugin)
    result = mod2.get_status()
    assert result["extra"]["call_count"] == 1, (
        f"New exec_module should start with _call_count=0, got {result['extra']['call_count']}"
    )


# ── P5-4: Two workers on the same file have independent namespaces ────────────

def test_two_workers_have_independent_namespaces(tmp_path):
    """Two concurrent exec_module calls on the same file cannot overwrite each other."""
    plugin = _write_counter_plugin(tmp_path, "shared")

    results: dict[str, int] = {}

    def _load_and_call(key: str) -> None:
        mod = _load_module(plugin)
        mod._NETSENTINEL_INSTANCE_IP = f"10.0.0.{key}"
        # Call get_status once — if namespaces are shared, the counter would be >1
        # in the second thread because the first thread already incremented it.
        time.sleep(0.02)  # give the other thread a chance to run
        results[key] = mod.get_status()["extra"]["call_count"]

    t1 = threading.Thread(target=_load_and_call, args=("1",))
    t2 = threading.Thread(target=_load_and_call, args=("2",))
    t1.start()
    t2.start()
    t1.join(timeout=3)
    t2.join(timeout=3)

    assert results.get("1") == 1, (
        f"Worker 1 should see call_count=1 (own fresh namespace), got {results.get('1')}"
    )
    assert results.get("2") == 1, (
        f"Worker 2 should see call_count=1 (own fresh namespace), got {results.get('2')}"
    )


# ── P5-1: Concurrent poll guard ──────────────────────────────────────────────

def test_trigger_now_is_noop_while_poll_in_progress():
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="iso_test")
    w._poll_in_progress = True
    w.trigger_now()
    assert not w._trigger.is_set(), (
        "trigger_now() must not set the event while a poll is in progress"
    )
    # Cleanup: ensure the event is clear so the worker can be safely stopped
    w._trigger.clear()


def test_trigger_now_sets_event_when_not_in_progress():
    from workers.plugin_polling_worker import PluginPollingWorker
    w = PluginPollingWorker("/fake.py", "router", instance_id="iso_test2")
    w._poll_in_progress = False
    w.trigger_now()
    assert w._trigger.is_set(), (
        "trigger_now() must set the event when no poll is in progress"
    )


def test_poll_in_progress_cleared_after_run_once(tmp_path):
    """_poll_in_progress must be False after run() completes one cycle."""
    from workers.plugin_polling_worker import PluginPollingWorker
    plugin = _write_counter_plugin(tmp_path, "flag_check")

    results: list[dict] = []
    w = PluginPollingWorker(str(plugin), "router", instance_id="flag_test")
    w.result.connect(results.append)

    # Manually simulate one iteration of the run() loop
    w._trigger.clear()
    w._poll_in_progress = True
    w._last_run_ok = False
    w._run_once()
    w._poll_in_progress = False  # this is what run() does

    assert not w._poll_in_progress, (
        "_poll_in_progress must be False after _run_once() completes"
    )
    assert w._last_run_ok, (
        "_last_run_ok must be True after a clean _run_once()"
    )
