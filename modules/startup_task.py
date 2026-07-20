"""
modules/startup_task.py — WinRT Windows.ApplicationModel.StartupTask ctypes layer
====================================================================================
Pure Python, no PyQt (ARCH RULE 1). Raw ctypes/WinRT interop against combase.dll -
no third-party WinRT projection package (no new dependency, session-workflow.md).

Every IID and vtable slot index below is transcribed from the installed Windows
SDK, not guessed - see docs/spikes/startup-task-winrt.md for the full
measurement (SDK 10.0.26100.0):
    winrt/windows.applicationmodel.h  - IStartupTask, IStartupTaskStatics,
                                         IAsyncOperation<StartupTask>, StartupTaskState
    winrt/asyncinfo.h                 - IAsyncInfo (well-known, non-parameterized IID)

Await strategy: poll IAsyncInfo::get_Status, never put_Completed. Polling only
needs the well-known IID_IAsyncInfo; put_Completed would require synthesising
an AsyncOperationCompletedHandler<StartupTask> vtable that Windows calls BACK
INTO - a parameterized IID with no header literal, and the exact "native
callback invoked reentrantly" shape RULE-WIN9 documents as this codebase's
recurring fault source. Confirmed live in the spike: GetAsync/GetResults never
need a QueryInterface at all (the operation object is handed back as a typed
out-param), so the only IID ever computed at runtime is the well-known one.

RULE-WIN11: every ctypes call that passes/returns a HANDLE or pointer declares
restype/argtypes on a LOCAL ctypes.WinDLL("combase.dll") handle - never
ctypes.windll.combase.X, which mutates process-global cached function objects.

Raw accessors return (hresult, state_or_None) - never a bool. A boolean wrapper
hides "answered no" (a real, packaged Disabled state) from "never ran" (a
failed activation) - exactly the failure class RULE-WIN11's postmortem
documents. Callers must inspect the HRESULT.

RULE 4: WinRT calls block on RPC and must never run on the GUI thread. Every
public function here hard-guards via _require_worker_thread() and raises
RuntimeError if called from threading.main_thread() - workers/autostart_worker.py
is the only intended caller in the running app; tests call from a spawned thread.
"""
from __future__ import annotations

import ctypes
import threading
import time
from typing import Optional, Tuple

# ── HRESULT / status constants ──────────────────────────────────────────────
S_OK = 0
S_FALSE = 1
RPC_E_CHANGED_MODE = ctypes.c_long(0x80010106).value
E_INVALIDARG = ctypes.c_long(0x80070057).value
E_POINTER = ctypes.c_long(0x80004003).value

# StartupTaskState (winrt/windows.applicationmodel.h)
STATE_DISABLED = 0
STATE_DISABLED_BY_USER = 1
STATE_ENABLED = 2
STATE_DISABLED_BY_POLICY = 3   # StartupTaskContract v2
STATE_ENABLED_BY_POLICY = 4    # StartupTaskContract v3

_RO_INIT_MULTITHREADED = 1

# AsyncStatus (winrt/asyncinfo.h)
_ASYNC_STARTED = 0
_ASYNC_COMPLETED = 1
_ASYNC_CANCELED = 2
_ASYNC_ERROR = 3

_POLL_INTERVAL_S = 0.01
_SHORT_DEADLINE_S = 2.0    # GetAsync: a manifest lookup, no I/O
_LONG_DEADLINE_S = 60.0    # RequestEnableAsync: a consent dialog may show

_STARTUP_TASK_CLASS_ID = "Windows.ApplicationModel.StartupTask"

# IIDs transcribed from the SDK headers cited in the module docstring.
_IID_IStartupTaskStatics = "ee5b60bd-a148-41a7-b26e-e8b88a1e62f8"
_IID_IAsyncInfo = "00000036-0000-0000-C000-000000000046"

# Vtable slot indices (0-based, IUnknown+IInspectable already consumed slots 0-5).
_VTBL_QUERY_INTERFACE = 0
_VTBL_STATICS_GET_ASYNC = 7
_VTBL_ASYNC_OP_GET_RESULTS = 8
_VTBL_ASYNC_INFO_GET_STATUS = 7
_VTBL_ASYNC_INFO_GET_ERROR_CODE = 8
_VTBL_STARTUP_TASK_REQUEST_ENABLE_ASYNC = 6
_VTBL_STARTUP_TASK_DISABLE = 7
_VTBL_STARTUP_TASK_GET_STATE = 8

HRESULT = ctypes.c_long
_HSTRING = ctypes.c_void_p
_IID_BUFFER = ctypes.c_byte * 16


def _require_worker_thread() -> None:
    if threading.current_thread() is threading.main_thread():
        raise RuntimeError(
            "modules.startup_task calls block on RPC (RULE 4) and must run on "
            "a worker thread - use workers.autostart_worker.AutostartWorker, "
            "never call this module from the GUI thread."
        )


def _combase() -> ctypes.WinDLL:  # type: ignore[name-defined]
    # A LOCAL WinDLL handle every call - RULE-WIN11: never ctypes.windll.combase.X.
    # ctypes.WinDLL/WINFUNCTYPE are Windows-only and absent from the Linux stubs CI
    # type-checks against; this module is never imported off Windows.
    dll = ctypes.WinDLL("combase.dll", use_last_error=True)  # type: ignore[attr-defined]
    dll.RoInitialize.restype = HRESULT
    dll.RoInitialize.argtypes = [ctypes.c_int]
    dll.RoUninitialize.restype = None
    dll.RoUninitialize.argtypes = []
    dll.WindowsCreateString.restype = HRESULT
    dll.WindowsCreateString.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.POINTER(_HSTRING)]
    dll.WindowsDeleteString.restype = HRESULT
    dll.WindowsDeleteString.argtypes = [_HSTRING]
    dll.WindowsGetStringRawBuffer.restype = ctypes.c_wchar_p
    dll.WindowsGetStringRawBuffer.argtypes = [_HSTRING, ctypes.POINTER(ctypes.c_uint32)]
    dll.RoGetActivationFactory.restype = HRESULT
    dll.RoGetActivationFactory.argtypes = [_HSTRING, ctypes.POINTER(_IID_BUFFER), ctypes.POINTER(ctypes.c_void_p)]
    return dll


def _iid_buffer(guid_str: str) -> "ctypes.Array[ctypes.c_byte]":
    import uuid
    # bytes_le is the Windows GUID wire layout: first three fields
    # little-endian, matching what RoGetActivationFactory/QueryInterface expect.
    return _IID_BUFFER.from_buffer_copy(uuid.UUID(guid_str).bytes_le)


def _create_hstring(value: str) -> _HSTRING:
    hs = _HSTRING()
    hr = _combase().WindowsCreateString(value, len(value), ctypes.byref(hs))
    if hr != S_OK:
        raise OSError(f"WindowsCreateString failed: hr=0x{hr & 0xFFFFFFFF:08X}")
    return hs


def _read_hstring(hs: _HSTRING) -> Optional[str]:
    if not hs or not hs.value:
        return None
    length = ctypes.c_uint32()
    buf_ptr = _combase().WindowsGetStringRawBuffer(hs, ctypes.byref(length))
    if not buf_ptr:
        return None
    return ctypes.wstring_at(buf_ptr, length.value)


def _hstring_value(hs: _HSTRING) -> Optional[int]:
    return hs.value if hs else None


def _delete_hstring(hs: _HSTRING) -> None:
    if hs and hs.value:
        _combase().WindowsDeleteString(hs)


def _vtbl_call(this: ctypes.c_void_p, index: int, restype, argtypes, *args):
    """
    Raw vtable dispatch - calls INTO an interface Windows already implemented
    (IStartupTaskStatics/IAsyncOperation/IAsyncInfo/IStartupTask). This is not
    the "synthesise a vtable Windows calls back into" shape the await strategy
    deliberately avoids (see module docstring) - it is an ordinary outgoing
    COM call, the same category as every other ctypes call in this module.
    """
    vtable_addr = ctypes.cast(this, ctypes.POINTER(ctypes.c_void_p)).contents.value
    slot_addr = vtable_addr + index * ctypes.sizeof(ctypes.c_void_p)
    func_addr = ctypes.cast(slot_addr, ctypes.POINTER(ctypes.c_void_p)).contents.value
    func = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(func_addr)  # type: ignore[attr-defined]
    return func(this, *args)


def ro_initialize() -> int:
    """RoInitialize(RO_INIT_MULTITHREADED) on the calling (worker) thread."""
    _require_worker_thread()
    return _combase().RoInitialize(_RO_INIT_MULTITHREADED)


def ro_uninitialize() -> None:
    _require_worker_thread()
    _combase().RoUninitialize()


def _get_statics_factory() -> Tuple[Optional[ctypes.c_void_p], int]:
    hs = _create_hstring(_STARTUP_TASK_CLASS_ID)
    try:
        factory = ctypes.c_void_p()
        hr = _combase().RoGetActivationFactory(hs, ctypes.byref(_iid_buffer(_IID_IStartupTaskStatics)), ctypes.byref(factory))
        return (factory if hr == S_OK and factory.value else None), hr
    finally:
        _delete_hstring(hs)


def _poll_async_status(async_op: ctypes.c_void_p, deadline_s: float) -> Tuple[int, int]:
    """
    QueryInterface(IID_IAsyncInfo) off the operation object, then poll
    get_Status. Returns (final_async_status, hresult). hresult is S_OK unless
    the QueryInterface itself failed.
    """
    async_info = ctypes.c_void_p()
    qi_hr = _vtbl_call(
        async_op, _VTBL_QUERY_INTERFACE, HRESULT,
        [ctypes.POINTER(_IID_BUFFER), ctypes.POINTER(ctypes.c_void_p)],
        ctypes.byref(_iid_buffer(_IID_IAsyncInfo)), ctypes.byref(async_info),
    )
    if qi_hr != S_OK or not async_info.value:
        return _ASYNC_ERROR, qi_hr

    status = ctypes.c_int(_ASYNC_STARTED)
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        _vtbl_call(async_info, _VTBL_ASYNC_INFO_GET_STATUS, HRESULT, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(status))
        if status.value in (_ASYNC_COMPLETED, _ASYNC_CANCELED, _ASYNC_ERROR):
            break
        time.sleep(_POLL_INTERVAL_S)

    if status.value == _ASYNC_ERROR:
        err = HRESULT(0)
        _vtbl_call(async_info, _VTBL_ASYNC_INFO_GET_ERROR_CODE, HRESULT, [ctypes.POINTER(HRESULT)], ctypes.byref(err))
        return status.value, err.value
    return status.value, S_OK


def get_task_state(task_id: str) -> Tuple[int, Optional[int]]:
    """Raw accessor: (hresult, StartupTaskState) - state is None on any failure."""
    _require_worker_thread()
    factory, hr = _get_statics_factory()
    if hr != S_OK or factory is None:
        return hr, None

    hs = _create_hstring(task_id)
    async_op = ctypes.c_void_p()
    try:
        hr = _vtbl_call(
            factory, _VTBL_STATICS_GET_ASYNC, HRESULT,
            [_HSTRING, ctypes.POINTER(ctypes.c_void_p)],
            hs, ctypes.byref(async_op),
        )
    finally:
        _delete_hstring(hs)
    if hr != S_OK or not async_op.value:
        return hr, None

    status, hr = _poll_async_status(async_op, _SHORT_DEADLINE_S)
    if status != _ASYNC_COMPLETED:
        return hr, None

    startup_task = ctypes.c_void_p()
    hr = _vtbl_call(async_op, _VTBL_ASYNC_OP_GET_RESULTS, HRESULT, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(startup_task))
    if hr != S_OK or not startup_task.value:
        return hr, None

    state = ctypes.c_int(-1)
    hr = _vtbl_call(startup_task, _VTBL_STARTUP_TASK_GET_STATE, HRESULT, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(state))
    return hr, (state.value if hr == S_OK else None)


def _resolve_startup_task(task_id: str) -> Tuple[Optional[ctypes.c_void_p], int]:
    """Shared GetAsync -> poll -> GetResults chain for request_enable/disable_task."""
    factory, hr = _get_statics_factory()
    if hr != S_OK or factory is None:
        return None, hr

    hs = _create_hstring(task_id)
    async_op = ctypes.c_void_p()
    try:
        hr = _vtbl_call(
            factory, _VTBL_STATICS_GET_ASYNC, HRESULT,
            [_HSTRING, ctypes.POINTER(ctypes.c_void_p)],
            hs, ctypes.byref(async_op),
        )
    finally:
        _delete_hstring(hs)
    if hr != S_OK or not async_op.value:
        return None, hr

    status, hr = _poll_async_status(async_op, _SHORT_DEADLINE_S)
    if status != _ASYNC_COMPLETED:
        return None, hr

    startup_task = ctypes.c_void_p()
    hr = _vtbl_call(async_op, _VTBL_ASYNC_OP_GET_RESULTS, HRESULT, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(startup_task))
    if hr != S_OK or not startup_task.value:
        return None, hr
    return startup_task, S_OK


def request_enable(task_id: str) -> Tuple[int, Optional[int]]:
    """
    Raw accessor: (hresult, StartupTaskState resulting from the request).
    RequestEnableAsync may show a Windows consent dialog - deliberately given
    a long deadline, safe only because this must never run on the GUI thread
    (RULE 4, enforced by _require_worker_thread()).
    """
    _require_worker_thread()
    startup_task, hr = _resolve_startup_task(task_id)
    if hr != S_OK or startup_task is None:
        return hr, None

    enable_op = ctypes.c_void_p()
    hr = _vtbl_call(startup_task, _VTBL_STARTUP_TASK_REQUEST_ENABLE_ASYNC, HRESULT, [ctypes.POINTER(ctypes.c_void_p)], ctypes.byref(enable_op))
    if hr != S_OK or not enable_op.value:
        return hr, None

    status, hr = _poll_async_status(enable_op, _LONG_DEADLINE_S)
    if status != _ASYNC_COMPLETED:
        return hr, None

    state = ctypes.c_int(-1)
    hr = _vtbl_call(enable_op, _VTBL_ASYNC_OP_GET_RESULTS, HRESULT, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(state))
    return hr, (state.value if hr == S_OK else None)


def disable_task(task_id: str) -> Tuple[int, Optional[int]]:
    """Raw accessor: (hresult, StartupTaskState) after calling IStartupTask::Disable."""
    _require_worker_thread()
    startup_task, hr = _resolve_startup_task(task_id)
    if hr != S_OK or startup_task is None:
        return hr, None

    hr = _vtbl_call(startup_task, _VTBL_STARTUP_TASK_DISABLE, HRESULT, [])
    if hr != S_OK:
        return hr, None

    state = ctypes.c_int(-1)
    hr = _vtbl_call(startup_task, _VTBL_STARTUP_TASK_GET_STATE, HRESULT, [ctypes.POINTER(ctypes.c_int)], ctypes.byref(state))
    return hr, (state.value if hr == S_OK else None)
