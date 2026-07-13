"""One-time UI Automation provider warmup — prevents the 0x8001010d COM fault.

THE BUG (RULE-WIN10; proved with procdump + cdb, docs/spikes/splash-uia-com-fault.md)

The first ``WM_GETOBJECT`` a process ever answers makes Qt's windows plugin call
``UiaReturnRawElementProvider``. On that first call — and only the first —
UIAutomationCore lazily initialises itself::

    UiaReturnRawElementProvider
      -> UIAutomationCore!CheckInit -> DoInit -> CUIAutomation7::FinalConstruct
        -> BlockingCoreDispatcher::CreateAndRegisterBlockingCore
          -> combase!CoCreateInstance          <-- an OUTGOING COM call

``WM_GETOBJECT`` is always delivered as an input-synchronous, cross-process
``SendMessage``, and COM refuses outgoing calls from a thread that is dispatching
one. It returns ``RPC_E_CANTCALLOUT_ININPUTSYNCCALL`` (0x8001010d) and raises it
as an SEH exception. ``faulthandler`` installs a *vectored* (first-chance)
handler, so it logs the exception to ``netsentinel_crash.log`` and then returns
``EXCEPTION_CONTINUE_SEARCH``; UIA handles the HRESULT and the process carries on.
Nothing crashes — but the chaos harness fails any run that appends a new
crash-log entry (RULE-CHAOS2, correctly), so every launch aborted its phase.

It fires exactly once per process, whenever the first UIA client happens to
connect. The splash screen is NOT involved: it was only ever *where the Python
stack happened to be* when the harness connected. Restructuring the splash moves
the fault into ``app.exec()``; it does not remove it.

THE FIX

Do that one-time initialisation ourselves, from a context where the outgoing COM
call is legal. A **same-thread** ``SendMessage`` is a direct WndProc call — the
thread is not inside an input-synchronous call (``InSendMessage()`` is false) —
so the ``CoCreateInstance`` succeeds. Afterwards ``CheckInit`` is satisfied and
the first real client ``WM_GETOBJECT`` never needs to call out to COM.

Costs ~3 ms, once, at startup. Benefits every UIA client, not just the test
harness: Narrator and NVDA trip the identical path.

This mirrors the existing precedent in ``app.py``, which pre-warms
``tplinkrouterc6u``'s COM-based crypto on the main thread for the same reason.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import logging
import sys

log = logging.getLogger(__name__)

# WM_GETOBJECT: the message a UIA/MSAA client sends to ask a window for its
# accessibility provider. UIA_ROOT_OBJECT_ID: the lParam that means "give me the
# UI Automation provider" (as opposed to an MSAA object).  Both are Win32
# constants — wrong values make this a silent no-op, so they are asserted in
# tests/test_uia_warmup.py.
WM_GETOBJECT = 0x003D
UIA_ROOT_OBJECT_ID = -25

_IS_WINDOWS = sys.platform == "win32"

if _IS_WINDOWS:
    # A PRIVATE WinDLL instance — deliberately NOT ctypes.windll.user32. That one is
    # a process-global cache (the LibraryLoader caches the WinDLL; the WinDLL caches
    # each function pointer), so pinning argtypes on its SendMessageW would pin the
    # prototype for every other caller in the process — and a caller passing a pointer
    # LPARAM (byref(...) for WM_COPYDATA, WM_GETMINMAXINFO, …) would then get an
    # ArgumentError. Our own handle keeps the prototype local to this module.
    _user32 = ctypes.WinDLL("user32")
    # Explicit argtypes: LPARAM is a signed pointer-width int. Without this,
    # ctypes truncates the negative UIA_ROOT_OBJECT_ID and Qt sees a request for
    # some other object id, silently skipping the UIA path we need to warm.
    _user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
    _user32.SendMessageW.restype = ctypes.c_ssize_t
else:  # pragma: no cover - non-Windows has no UIA and cannot hit the fault
    _user32 = None

# Latches True only on a *successful* warmup, so a caller whose window was not
# yet able to serve a provider can retry on a later one.
_warmed = False


def _reset_for_tests() -> None:
    """Clear the one-shot latch. Test-only."""
    global _warmed
    _warmed = False


def warm_up_uia_provider(hwnd: int) -> bool:
    """Force UIAutomationCore's one-time init from a safe (non-input-sync) context.

    Returns True if UIA core is initialised (now or by an earlier call), False if
    this window could not serve a provider — in which case the caller should try
    again on a later window rather than leaving the process cold.

    Never raises: a failed warmup must not take startup down with it. The app is
    fully functional without it; the only consequence is that the fault it
    prevents gets logged once.
    """
    global _warmed
    if _warmed or not _IS_WINDOWS:
        return _warmed

    try:
        # Same-thread SendMessage -> Qt's WndProc runs inline, on this thread, and
        # is NOT in an input-synchronous call, so UiaReturnRawElementProvider's
        # first-use CoCreateInstance is permitted.
        lresult = _user32.SendMessageW(hwnd, WM_GETOBJECT, 0, UIA_ROOT_OBJECT_ID)
    except Exception as exc:  # noqa: BLE001 - best-effort; see docstring
        log.debug("UIA provider warmup failed on hwnd=%s: %s", hwnd, exc)
        return False

    # A non-zero LRESULT means Qt handed UIA a provider, so UiaReturnRawElementProvider
    # ran and CheckInit is now satisfied. Zero means Qt declined (e.g. the window has
    # no accessible root yet) — the init did NOT happen, so do not latch.
    if lresult == 0:
        log.debug("UIA provider warmup: hwnd=%s returned no provider", hwnd)
        return False

    _warmed = True
    log.debug("UIA provider warmed up on hwnd=%s (lresult=%s)", hwnd, lresult)
    return True
