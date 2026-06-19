"""
PluginPollingWorker — persistent hardware plugin poller.

Runs in a QThread, loads each plugin in-process via importlib, and emits
result / error signals.  In-process execution (rather than subprocess) works
correctly in both source-run and PyInstaller frozen builds — in a frozen build
sys.executable is the .exe, not a Python interpreter, so subprocess would fail.

Intervals (tuned by hardware type):
    modem     30 s    — frequent signal updates for Overview page
    router   120 s    — frequent enough for device tracking / enrichment
    ap       120 s
    switch   300 s
    other    300 s

Manual refresh: call trigger_now() to wake the sleep immediately.
Stop: call stop() then wait().
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal


class PluginPollingWorker(QThread):

    result   = pyqtSignal(dict)  # data dict; includes "_instance_id" key
    error    = pyqtSignal(str)   # error message
    log_line = pyqtSignal(str)   # structured log entry "[HH:MM:SS] …" for the card console

    _INTERVALS: dict[str, int] = {
        "modem":  30,
        "router": 60,
        "ap":     60,
        "switch": 300,
    }
    _DEFAULT_INTERVAL = 300

    # Fallback repo-root hint — used only when sys.path has no entry that contains
    # modules/utils.py (rare; in practice sys.path is always correct when running
    # from source or from the frozen bundle).
    _NS_ROOT_FALLBACK = str(Path(__file__).parent.parent)

    def __init__(self, path: str, hw_type: str,
                 instance_id: str = "", instance_ip: str = "",
                 config: "dict | None" = None,
                 parent=None) -> None:
        super().__init__(parent)
        self._path        = path
        self._hw_type     = hw_type
        self._instance_id = instance_id  # unique key for this instance
        self._instance_ip = instance_ip  # IP override for multi-instance
        self._config      = config or {}  # P2-2 CONFIG_SCHEMA values
        self._interval_s  = self._INTERVALS.get(hw_type, self._DEFAULT_INTERVAL)
        # Allow schema-declared poll_interval to override the type default
        if "poll_interval" in self._config:
            try:
                self._interval_s = max(10, int(self._config["poll_interval"]))
            except (TypeError, ValueError):
                pass  # invalid config value — keep the hardware-type default interval
        self._stop              = False
        self._trigger           = threading.Event()
        # P5-1: concurrent poll guard — True while _run_once is executing
        self._poll_in_progress  = False
        # P6-1: exponential backoff state
        self._consecutive_errors = 0
        self._last_run_ok        = False

    # ── Public interface ──────────────────────────────────────────────────────

    def stop(self) -> None:
        """Request graceful shutdown. Call wait() afterwards."""
        self._stop = True
        self._trigger.set()

    def trigger_now(self) -> None:
        """Wake the inter-poll sleep immediately — runs plugin right away.

        No-op while a poll is already in progress to avoid queuing redundant
        back-to-back runs. CPython bool reads/writes are GIL-protected.
        """
        if not self._poll_in_progress:
            self._trigger.set()

    def get_effective_interval(self) -> int:
        """Return the current sleep interval accounting for exponential backoff (P6-1).

        1 error        → base interval (no change)
        3+ consecutive → 2× base, capped at 300 s
        6+ consecutive → 4× base, capped at 300 s
        """
        if self._consecutive_errors >= 6:
            return min(self._interval_s * 4, 300)
        if self._consecutive_errors >= 3:
            return min(self._interval_s * 2, 300)
        return self._interval_s

    # ── Thread body ───────────────────────────────────────────────────────────

    def run(self) -> None:
        while not self._stop:
            self._trigger.clear()
            self._poll_in_progress = True
            self._last_run_ok = False
            self._run_once()
            self._poll_in_progress = False
            # Update backoff counter based on run outcome (P6-1)
            if self._last_run_ok:
                self._consecutive_errors = 0
            else:
                self._consecutive_errors += 1
            if not self._stop:
                self._trigger.wait(timeout=self.get_effective_interval())

    def _run_once(self) -> None:
        """Load the plugin in-process and call get_info() / get_status() directly.

        This works in both source-run and PyInstaller frozen builds.  A subprocess
        approach breaks in frozen builds because sys.executable is the .exe, not a
        Python interpreter.
        """
        import importlib.util

        _ts = datetime.now().strftime("%H:%M:%S")

        def _log(msg: str) -> None:
            self.log_line.emit(f"[{_ts}] {msg}")

        _log("Poll started")

        if not Path(self._path).exists():
            _log(f"✗ File not found: {Path(self._path).name}")
            self.error.emit(f"FILE: plugin file not found at {self._path}")
            return

        # Ensure NetSentinel modules are importable.  Look for the live entry in
        # sys.path that actually contains modules/utils.py (works from source,
        # from AppData copy, and from frozen bundle where modules are compiled in).
        _ns_root = next(
            (p for p in sys.path if p and Path(p, "modules", "utils.py").exists()),
            self._NS_ROOT_FALLBACK,
        )
        if _ns_root not in sys.path:
            sys.path.insert(0, _ns_root)

        try:
            spec = importlib.util.spec_from_file_location(
                f"_ns_hw_{Path(self._path).stem}", self._path
            )
            if spec is None or spec.loader is None:
                _log("✗ Cannot load plugin (spec error)")
                self.error.emit(f"Cannot load plugin: {self._path}")
                return

            mod = importlib.util.module_from_spec(spec)
            # Execute module top-level (defines functions, constants; does NOT run
            # the --netsentinel shim because sys.argv won't contain that flag).
            spec.loader.exec_module(mod)  # type: ignore[union-attr]

            # Inject per-instance identifiers directly into the module namespace
            # (RULE-PL1).  This is thread-safe: each exec_module creates an
            # independent namespace so concurrent instances don't interfere.
            mod._NETSENTINEL_INSTANCE_IP = self._instance_ip or ""
            mod._NETSENTINEL_INSTANCE_ID = self._instance_id or ""

            if self._stop:
                return

            get_info    = getattr(mod, "get_info",    None)
            get_status  = getattr(mod, "get_status",  None)
            get_clients = getattr(mod, "get_clients", None)

            if not callable(get_info) or not callable(get_status):
                _log("✗ Plugin missing get_info() or get_status()")
                self.error.emit("Plugin missing get_info() or get_status()")
                return

            info = get_info()
            _log(f"get_info() → {(info or {}).get('name', '?')}")
            if self._stop:
                return

            # P2-2: pass CONFIG_SCHEMA values to get_status if it accepts kwargs
            if self._config:
                try:
                    status = get_status(config=self._config)
                except TypeError:
                    status = get_status()
            else:
                status = get_status()
            extra   = (status or {}).get("extra", {}) or {}
            err_msg = extra.get("error", "")
            if err_msg:
                _log(f"✗ Plugin error: {str(err_msg)[:80]}")
            else:
                n_cli = (status or {}).get("connected_clients", "?")
                _log(f"get_status() → {n_cli} clients")
            if self._stop:
                return

            clients = get_clients() if callable(get_clients) else []
            if callable(get_clients):
                _log(f"get_clients() → {len(clients)} devices")

            self.result.emit({
                "info": info, "status": status, "clients": clients,
                "_instance_id": self._instance_id,
                "_path": self._path,
            })
            if not err_msg:
                self._last_run_ok = True  # clean result — reset backoff counter
                _log("✓ Result emitted")

        except SystemExit:
            _log("Plugin called sys.exit() — skipped")
            # plugin shim called sys.exit() — harmless, treat as success-less run
        except Exception as exc:
            _log(f"✗ Error: {exc}")
            self.error.emit(str(exc))
