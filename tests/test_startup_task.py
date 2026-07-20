"""
Unmocked ctypes/WinRT tests for modules/startup_task.py (RULE-SPIKE1, RULE-WIN11).

Real HSTRING / RoInitialize / RoGetActivationFactory calls against the OS -
no mocking. Mirrors test_store_update_flow.py's approach: a suite that mocks
the only unmockable link tests nothing about it. Windows-only; skipped
everywhere else.

All WinRT calls run on a background thread, never the pytest main thread -
modules.startup_task hard-guards against main-thread use (RULE 4: no
blocking I/O on the main thread; a real StartupTask call blocks on RPC).
"""
import sys
import threading

import pytest

if sys.platform != "win32":
    pytest.skip("WinRT StartupTask is Windows-only", allow_module_level=True)

from modules import startup_task


def _run_off_main_thread(fn):
    box = {}

    def _target():
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread below
            box["exc"] = exc

    t = threading.Thread(target=_target)
    t.start()
    t.join(timeout=15)
    assert not t.is_alive(), "WinRT call did not return within 15s"
    if "exc" in box:
        raise box["exc"]
    return box.get("value")


def test_main_thread_guard_raises():
    """RULE 4 / plan 5.3: raw accessors must refuse to run on the main thread."""
    assert threading.current_thread() is threading.main_thread()
    with pytest.raises(RuntimeError):
        startup_task.get_task_state("AnyTaskId")


def test_hstring_roundtrip_survives_64bit_pointer():
    """RULE-WIN11: a truncated 32-bit handle is the classic silent-failure shape."""
    def _do():
        hr = startup_task.ro_initialize()
        try:
            hs = startup_task._create_hstring("Windows.ApplicationModel.StartupTask")
            try:
                value = startup_task._hstring_value(hs)
                assert value is not None
                readback = startup_task._read_hstring(hs)
                assert readback == "Windows.ApplicationModel.StartupTask"
                return value
            finally:
                startup_task._delete_hstring(hs)
        finally:
            if hr in (startup_task.S_OK, startup_task.S_FALSE):
                startup_task.ro_uninitialize()

    pointer_value = _run_off_main_thread(_do)
    assert pointer_value > 0xFFFFFFFF, "HSTRING pointer looks truncated to 32 bits"


def test_ro_initialize_never_returns_changed_mode_off_thread():
    """A genuinely fresh thread's COM apartment is never pre-claimed as STA."""
    def _do():
        hr = startup_task.ro_initialize()
        if hr in (startup_task.S_OK, startup_task.S_FALSE):
            startup_task.ro_uninitialize()
        return hr

    hr = _run_off_main_thread(_do)
    assert hr != startup_task.RPC_E_CHANGED_MODE
    assert hr in (startup_task.S_OK, startup_task.S_FALSE)


def test_activation_hresult_is_known_value_never_truncation_code():
    """RULE-WIN11: E_INVALIDARG/E_POINTER are the truncated-handle symptom codes."""
    def _do():
        hr = startup_task.ro_initialize()
        try:
            _factory, activation_hr = startup_task._get_statics_factory()
            return activation_hr
        finally:
            if hr in (startup_task.S_OK, startup_task.S_FALSE):
                startup_task.ro_uninitialize()

    activation_hr = _run_off_main_thread(_do)
    assert activation_hr not in (startup_task.E_INVALIDARG, startup_task.E_POINTER)


def test_raw_accessor_reports_hresult_and_state_not_a_bool():
    """RULE-WIN11 corollary: a boolean wrapper hides 'answered no' from 'never ran'.

    Unpackaged (no uap5:StartupTask manifest entry, no package identity),
    the task lookup fails - the raw accessor must surface the real HRESULT
    and None, not silently coerce to a default state.
    """
    def _do():
        hr = startup_task.ro_initialize()
        try:
            return startup_task.get_task_state("NetSentinelStartupTask")
        finally:
            if hr in (startup_task.S_OK, startup_task.S_FALSE):
                startup_task.ro_uninitialize()

    result_hr, state = _run_off_main_thread(_do)
    assert isinstance(result_hr, int)
    assert result_hr != startup_task.S_OK
    assert state is None
