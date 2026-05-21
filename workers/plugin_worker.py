"""
Hardware plugin worker.

Runs a user-supplied integration script as a subprocess with the
``--netsentinel`` flag, parses stdout as a single JSON object, and emits
the result dict upward.

Output contract (plugin stdout when called with --netsentinel):
    {
        "info":    {"name": str, "type": str, "ip": str, "firmware": str, ...},
        "status":  {"wan_ip": str|None, "uptime_sec": int|None,
                    "download_mbps": float|None, "upload_mbps": float|None, ...},
        "clients": [{"ip": str, "mac": str, "hostname": str}, ...]
    }

The --netsentinel shim is injected at the bottom of every plugin template
so scripts never need to implement this protocol manually.  Existing
``if __name__ == '__main__'`` blocks are left intact.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


class PluginWorker(QThread):
    """Run a plugin script with --netsentinel, parse its stdout as JSON.

    Signals
    -------
    result(dict)  — parsed {info, status, clients} on success
    error(str)    — human-readable error message on failure
    """

    result = pyqtSignal(dict)
    error  = pyqtSignal(str)

    def __init__(self, script_path: str, timeout: int = 20,
                 parent=None) -> None:
        super().__init__(parent)
        self._path    = script_path
        self._timeout = timeout

    def run(self) -> None:
        try:
            proc = subprocess.run(
                [sys.executable, self._path, "--netsentinel"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            self.error.emit(
                f"Plugin timed out after {self._timeout}s — "
                "check for blocking network calls."
            )
            return
        except Exception as exc:
            self.error.emit(f"Failed to launch plugin: {exc}")
            return

        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "Script exited with an error.").strip()
            self.error.emit(msg)
            return

        stdout = proc.stdout.strip()
        if not stdout:
            self.error.emit("Plugin produced no output with --netsentinel flag.")
            return

        # Find the last line that looks like JSON — the shim always prints one
        # JSON line; any earlier print() in the script is ignored.
        json_line: Optional[str] = None
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                json_line = line
                break

        if json_line is None:
            self.error.emit(
                "Plugin output did not contain a JSON object.\n\n"
                f"Raw output:\n{stdout[:800]}"
            )
            return

        try:
            data = json.loads(json_line)
        except json.JSONDecodeError as exc:
            self.error.emit(
                f"Plugin JSON parse error: {exc}\n\nRaw line:\n{json_line[:400]}"
            )
            return

        # Minimal shape check — callers rely on these keys existing
        for key in ("info", "status", "clients"):
            if key not in data:
                self.error.emit(
                    f"Plugin JSON missing required key '{key}'. "
                    f"Keys present: {list(data.keys())}"
                )
                return

        self.result.emit(data)
