"""
tests/test_autostart.py — modules/autostart.py backend selector + state contract.

Real WinRT calls are exercised (unmocked) in test_startup_task.py per
RULE-WIN11's corollary; this file mocks modules.startup_task to test the
backend-selection and state-translation LOGIC in isolation.
"""
import pytest

from modules import autostart, startup_task


def test_backend_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "linux")
    assert autostart.autostart_backend() == "none"


def test_backend_follows_is_store_app(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setattr(autostart, "is_store_app", lambda: True)
    assert autostart.autostart_backend() == "startup_task"

    monkeypatch.setattr(autostart, "is_store_app", lambda: False)
    assert autostart.autostart_backend() == "run_key"


def test_run_key_path_never_touches_startup_task(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setattr(autostart, "is_store_app", lambda: False)

    def _boom(*a, **kw):
        raise AssertionError("run_key backend must never call modules.startup_task")

    monkeypatch.setattr(startup_task, "get_task_state", _boom)
    monkeypatch.setattr(startup_task, "request_enable", _boom)
    monkeypatch.setattr(startup_task, "disable_task", _boom)
    monkeypatch.setattr(autostart, "get_run_on_startup", lambda: True)
    monkeypatch.setattr(autostart, "set_run_on_startup", lambda enabled: None)

    state = autostart.autostart_state()
    assert state.backend == "run_key"
    assert state.enabled is True

    state = autostart.set_autostart(False)
    assert state.backend == "run_key"


@pytest.mark.parametrize("raw_state,expected_can_change", [
    (startup_task.STATE_DISABLED, True),
    (startup_task.STATE_ENABLED, True),
    (startup_task.STATE_DISABLED_BY_USER, False),
    (startup_task.STATE_DISABLED_BY_POLICY, False),
    (startup_task.STATE_ENABLED_BY_POLICY, False),
    (None, True),
])
def test_can_user_change_autostart_truth_table(raw_state, expected_can_change):
    can_change, reason = autostart.can_user_change_autostart(raw_state)
    assert can_change is expected_can_change
    if not expected_can_change:
        assert reason  # a user-facing explanation must be given whenever locked out
    else:
        assert reason == ""


def test_set_autostart_returns_actual_not_requested_state(monkeypatch):
    """RULE-T3 regression: the caller asked for enabled=True but Windows reports
    DisabledByUser (the user turned it off in Settings) - the returned state
    must reflect what actually resulted, not echo the request back. This is
    the exact structural fix for the "lying checkbox" (docs/spikes/
    startup-task-winrt.md's RULE-REQ2 paragraph)."""
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setattr(autostart, "is_store_app", lambda: True)
    monkeypatch.setattr(startup_task, "request_enable", lambda task_id: (0, startup_task.STATE_DISABLED_BY_USER))

    result = autostart.set_autostart(True)

    assert result.backend == "startup_task"
    assert result.enabled is False
    assert result.raw_state == startup_task.STATE_DISABLED_BY_USER
    assert result.can_change is False
    assert result.reason


def test_set_autostart_disable_calls_disable_task(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "win32")
    monkeypatch.setattr(autostart, "is_store_app", lambda: True)
    calls = []
    monkeypatch.setattr(startup_task, "disable_task", lambda task_id: (calls.append(task_id), (0, startup_task.STATE_DISABLED))[1])
    monkeypatch.setattr(startup_task, "request_enable", lambda task_id: pytest.fail("should not enable"))

    result = autostart.set_autostart(False)

    assert calls == [autostart.STARTUP_TASK_ID]
    assert result.enabled is False


def test_autostart_backend_none_short_circuits_before_startup_task(monkeypatch):
    monkeypatch.setattr(autostart.sys, "platform", "linux")

    def _boom(*a, **kw):
        raise AssertionError("none backend must never call modules.startup_task")

    monkeypatch.setattr(startup_task, "get_task_state", _boom)
    state = autostart.autostart_state()
    assert state.backend == "none"
    assert state.can_change is False
