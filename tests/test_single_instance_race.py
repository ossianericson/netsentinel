"""Regression test for the duplicate-instance-launch bug (RULE-WIN16).

Before the fix, app.py's single-instance guard raced a QLocalServer
probe-then-listen dance: two processes launched close together could both
pass the "nobody answered" probe before either bound the server, and the
loser fell back to running as a fully independent second instance instead
of exiting. After the fix, an OS-level named mutex is the sole, atomic gate
checked before a real QApplication is ever built.

This test pre-acquires the mutex itself (cheap, instant, no GUI) to
deterministically simulate "another instance is already running", then
launches the real app.py and asserts it notices and exits quickly — no
need to race two full GUI boots against each other to get a reliable
signal. RED before the fix (app.py ignored the mutex entirely and kept
booting); GREEN after.
"""

import ctypes
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from modules.single_instance import acquire_instance_mutex

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.slow
@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex API")
def test_app_exits_promptly_when_instance_mutex_already_held(tmp_path):
    is_first, handle = acquire_instance_mutex("NetSentinel_SingleInstance_v1")
    if not is_first:
        pytest.skip(
            "the production single-instance mutex is already held — a real "
            "NetSentinel instance is likely running on this machine"
        )

    env = dict(os.environ)
    env["LOCALAPPDATA"] = str(tmp_path)

    proc = subprocess.Popen([sys.executable, "app.py"], cwd=str(REPO), env=env)
    try:
        deadline = time.time() + 10
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        assert proc.poll() is not None, (
            "app.py did not exit within 10s while the single-instance mutex "
            "was already held — it booted as a second, fully independent "
            "instance instead of detecting the running one and exiting "
            "(the exact duplicate-launch bug this test guards against)."
        )
        assert proc.returncode == 0
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
        if handle:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            k32.CloseHandle(handle)
