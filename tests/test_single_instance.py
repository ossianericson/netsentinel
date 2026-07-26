"""Tests for modules/single_instance.py (RULE-WIN16).

The Windows-only behavioral tests exercise the real, unmocked CreateMutexW
syscall (RULE-WIN11: at least one test must hit the real path) — a named
mutex is one of the most basic Win32 primitives and is safe to acquire twice
from the same test process to observe the ERROR_ALREADY_EXISTS round-trip.
"""

import ctypes
import sys

import pytest

from modules.single_instance import (
    ERROR_ACCESS_DENIED,
    acquire_instance_mutex,
)


def test_import():
    from modules import single_instance  # noqa: F401


def test_non_windows_is_always_first_instance(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    is_first, handle = acquire_instance_mutex("NetSentinel_pytest_nonwin")
    assert is_first is True
    assert handle is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex API")
def test_second_acquire_in_same_process_reports_not_first():
    name = "NetSentinel_SingleInstance_pytest_real"
    is_first_1, h1 = acquire_instance_mutex(name)
    is_first_2, h2 = acquire_instance_mutex(name)
    try:
        assert is_first_1 is True
        assert is_first_2 is False
        assert h1 and h2
    finally:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        if h1:
            k32.CloseHandle(h1)
        if h2:
            k32.CloseHandle(h2)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex API")
def test_global_namespace_access_denied_falls_back_to_local(monkeypatch):
    calls = []

    def _fake_create_mutex_w(_sec, _initial, name):
        calls.append(name)
        if name.startswith("Global\\"):
            ctypes.set_last_error(ERROR_ACCESS_DENIED)
            return 0
        ctypes.set_last_error(0)
        return 12345  # fake non-null handle

    class _FakeKernel32:
        pass

    fake = _FakeKernel32()
    fake.CreateMutexW = _fake_create_mutex_w  # plain function -> attr-assignable
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: fake)

    is_first, handle = acquire_instance_mutex("NetSentinel_pytest_fallback")

    assert is_first is True
    assert handle == 12345
    assert calls == [
        "Global\\NetSentinel_pytest_fallback",
        "NetSentinel_pytest_fallback",
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex API")
def test_creation_failure_treated_as_unknown_not_first(monkeypatch):
    def _fake_create_mutex_w(_sec, _initial, _name):
        ctypes.set_last_error(0)
        return 0  # every attempt fails to create a handle

    class _FakeKernel32:
        pass

    fake = _FakeKernel32()
    fake.CreateMutexW = _fake_create_mutex_w
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **kw: fake)

    is_first, handle = acquire_instance_mutex("NetSentinel_pytest_nohandle")

    # Ambiguous outcome: no crash, caller falls back to the QLocalServer
    # probe/listen path rather than skipping the guard outright.
    assert is_first is True
    assert handle is None
