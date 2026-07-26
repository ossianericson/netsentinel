"""Windows named-mutex single-instance gate.

A `QLocalServer`-only single-instance guard (probe a socket, become the
server if nobody answers) has a TOCTOU race: two processes launched close
together can both pass the "nobody answered" probe before either binds the
server, and Qt's `QLocalServer.listen()` has no atomic "only one winner"
guarantee across processes. `CreateMutexW` does — the OS resolves ownership
of a named mutex atomically, so it is the correct primitive to gate "am I
allowed to become the running instance" (RULE-WIN16). `Global\\` is used so
the check is not sensitive to any per-session/per-package object-namespace
redirection a packaged (MSIX/Store) build might be subject to; on Windows,
regular interactive processes hold `SeCreateGlobalPrivilege` by default, but
if creating in the `Global\\` namespace is ever denied, this falls back to
the plain session-local namespace rather than treating denial as
"I'm the first instance".

Per RULE-WIN11: never use the cached `ctypes.windll.<dll>.<func>` function
objects with implicit (32-bit-truncating) argument/return types — always a
local `WinDLL` with explicit `restype`/`argtypes`.
"""

import ctypes
import sys

ERROR_ALREADY_EXISTS = 183
ERROR_ACCESS_DENIED = 5


def _create_mutex(kernel32, name: str):
    handle = kernel32.CreateMutexW(None, False, name)
    return handle, ctypes.get_last_error()  # type: ignore[attr-defined]  # Windows-only ctypes API


def acquire_instance_mutex(name: str) -> "tuple[bool, int | None]":
    """Claim `name` as this process's single-instance mutex.

    Returns `(is_first_instance, handle)`. The caller must keep `handle`
    referenced for the process lifetime and never close it — Windows
    releases it automatically on process exit, including a crash, which is
    exactly the desired self-healing behaviour for a prior instance that
    died without cleaning up.

    On non-Windows platforms this is a no-op that always reports
    `is_first_instance=True` — the existing QLocalServer-based guard is
    left as the only mechanism there.
    """
    if sys.platform != "win32":
        return True, None

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p, ctypes.c_long, ctypes.c_wchar_p,
    ]

    handle, err = _create_mutex(kernel32, f"Global\\{name}")
    if not handle and err == ERROR_ACCESS_DENIED:
        # Global\ namespace denied (unexpected, but not fatal) — retry
        # session-local rather than silently assuming first-instance.
        handle, err = _create_mutex(kernel32, name)

    if not handle:
        # Could not create the mutex at all. Treat as "unknown" rather than
        # "first instance" — the caller falls back to the existing
        # QLocalServer probe/listen path, which is no worse than before.
        return True, None

    return (err != ERROR_ALREADY_EXISTS), handle
