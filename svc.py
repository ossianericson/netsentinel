"""
NetSentinel Logger — Windows Service

Runs the NetworkLogger as a Windows background service so connectivity
monitoring continues even when no user is logged in.

Usage (run PowerShell as Administrator):
    python svc.py install    Install the service (starts automatically at boot)
    python svc.py start      Start the service now
    python svc.py stop       Stop the service
    python svc.py remove     Uninstall the service
    python svc.py restart    Restart the service
    python svc.py status     Show current status (no admin required)
    python svc.py debug      Run in the foreground — Ctrl+C to stop

Requires:
    pip install pywin32
    python -m pywin32_postinstall -install   (run once, as Administrator)

Config file (created automatically on first run):
    %PROGRAMDATA%\\NetSentinel\\netsentinel-svc.ini

Log files:
    %PROGRAMDATA%\\NetSentinel\\logs\\netlog_YYYYMMDD.csv

Config example (all keys optional — defaults shown):
    [logger]
    interval_s        = 60
    targets           = 8.8.8.8, 1.1.1.1, google.com
    slow_threshold_ms = 150
    enable_jitter     = false
    enable_dns        = true
    enable_http       = false
    enable_arp        = true
"""

import configparser
import datetime
import os
import sys
import threading
from pathlib import Path

# Allow running from the project root without installation.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Console-output decoding (RULE-WIN21). NetSentinelSvc.exe is its own PyInstaller
# entry point and never imports app.py. This one runs UNATTENDED as a Windows service,
# so an unhandled UnicodeDecodeError out of NetworkLogger's ping/netsh captures has no
# user present to see it -- the service simply stops logging.
from modules.console_codec import harden_stdio as _harden_stdio  # noqa: E402
from modules.console_codec import install as _install_console_codec  # noqa: E402

_install_console_codec()
_harden_stdio()

# Crash net (A3): faulthandler for native faults, sys.excepthook for the main
# thread, threading.excepthook for plain threads. The service runs UNATTENDED,
# so without a written record a failure is completely invisible.
from modules.crash_net import install as _install_crash_net  # noqa: E402

_install_crash_net()

# ── Bound the logs before anything opens one (A4) ─────────────────────────────
# Nothing rotated anything before this: a real install carried a 4.08 MB
# theme-switch log and ~1 MB each of stderr, shutdown and scan-timing history.
# Only fires above a size threshold, and never touches netsentinel_crash.log --
# monkey_test.py baselines that file's byte size to detect native SEH faults, so
# shrinking it would silently disarm the project's primary stability gate.
# Runs BEFORE any log handle is opened: Windows cannot rename an open file.
from modules.log_rotation import rotate_logs as _rotate_logs  # noqa: E402

_rotate_logs()


# ── Service identity ──────────────────────────────────────────────────────────

_SVC_NAME        = "NetSentinelLogger"
_SVC_DISPLAY     = "NetSentinel Logger"
_SVC_DESCRIPTION = (
    "NetSentinel background connectivity monitor — pings targets on a "
    "configurable interval and writes timestamped CSV logs. "
    "Configure via %PROGRAMDATA%\\NetSentinel\\netsentinel-svc.ini."
)

# ── Paths ─────────────────────────────────────────────────────────────────────

_CONFIG_DIR  = Path(os.environ.get("PROGRAMDATA", "C:\\ProgramData")) / "NetSentinel"
_CONFIG_FILE = _CONFIG_DIR / "netsentinel-svc.ini"
_LOG_DIR     = _CONFIG_DIR / "logs"

# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    """Read config file; return settings dict with sensible defaults."""
    cfg = configparser.ConfigParser()
    if _CONFIG_FILE.exists():
        cfg.read(_CONFIG_FILE, encoding="utf-8")

    sec = cfg["logger"] if "logger" in cfg else {}

    def _bool(key: str, default: bool) -> bool:
        return sec.get(key, str(default)).strip().lower() in ("true", "1", "yes")

    targets_raw = sec.get("targets", "8.8.8.8, 1.1.1.1, google.com")
    targets = [t.strip() for t in targets_raw.split(",") if t.strip()]

    return {
        "interval_s":        int(sec.get("interval_s", "60")),
        "targets":           targets,
        "slow_threshold_ms": float(sec.get("slow_threshold_ms", "150")),
        "enable_jitter":     _bool("enable_jitter", False),
        "enable_dns":        _bool("enable_dns", True),
        "enable_http":       _bool("enable_http", False),
        "enable_arp":        _bool("enable_arp", True),
    }


def _write_default_config() -> None:
    """Create a default config file if none exists."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not _CONFIG_FILE.exists():
        _CONFIG_FILE.write_text(
            "[logger]\n"
            "# Seconds between each ping cycle.\n"
            "interval_s = 60\n\n"
            "# Comma-separated list of hosts to ping each cycle.\n"
            "targets = 8.8.8.8, 1.1.1.1, google.com\n\n"
            "# RTT above this value is flagged SLOW instead of OK.\n"
            "slow_threshold_ms = 150\n\n"
            "# Set to true to measure jitter (3x pings per host per cycle).\n"
            "enable_jitter = false\n\n"
            "# Set to true to measure DNS resolution latency each cycle.\n"
            "enable_dns = true\n\n"
            "# Set to true to run an HTTP connectivity check each cycle.\n"
            "enable_http = false\n\n"
            "# Set to true to snapshot ARP table and alert on changes.\n"
            "enable_arp = true\n",
            encoding="utf-8",
        )


# ── Logger runner ─────────────────────────────────────────────────────────────

def _run_logger(stop_event: threading.Event) -> Path:
    """
    Start NetworkLogger and block until *stop_event* is set.
    Returns the path of the CSV log file that was written.
    """
    from modules.network_logger import NetworkLogger

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = _load_config()

    # Rotate to a new daily file at midnight automatically.
    today    = datetime.date.today().strftime("%Y%m%d")
    log_path = _LOG_DIR / f"netlog_{today}.csv"

    logger = NetworkLogger(
        interval_s=cfg["interval_s"],
        targets=cfg["targets"],
        log_path=log_path,
        slow_threshold_ms=cfg["slow_threshold_ms"],
        enable_jitter=cfg["enable_jitter"],
        enable_dns=cfg["enable_dns"],
        enable_http=cfg["enable_http"],
        enable_arp=cfg["enable_arp"],
    )
    logger.start()

    try:
        while not stop_event.wait(timeout=1):
            # Rotate log file at midnight.
            new_today = datetime.date.today().strftime("%Y%m%d")
            if new_today != today:
                today    = new_today
                log_path = _LOG_DIR / f"netlog_{today}.csv"
                logger.stop()
                logger.log_path = log_path
                logger.start()
    finally:
        logger.stop()

    return log_path


# ── Windows service class (only available when pywin32 is installed) ──────────

try:
    import win32event
    import win32service
    import win32serviceutil
    import servicemanager

    class _NetSentinelLoggerService(win32serviceutil.ServiceFramework):
        _svc_name_         = _SVC_NAME
        _svc_display_name_ = _SVC_DISPLAY
        _svc_description_  = _SVC_DESCRIPTION

        def __init__(self, args):
            win32serviceutil.ServiceFramework.__init__(self, args)
            self._win32_stop  = win32event.CreateEvent(None, 0, 0, None)
            self._thread_stop = threading.Event()

        def GetAcceptedControls(self):
            # Accept pre-shutdown notification so we can flush the CSV on OS shutdown.
            result = win32serviceutil.ServiceFramework.GetAcceptedControls(self)
            result |= win32service.SERVICE_ACCEPT_PRESHUTDOWN
            return result

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._win32_stop)
            self._thread_stop.set()

        SvcOtherEx = SvcStop  # pre-shutdown also routes here

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            _write_default_config()

            # Bridge the win32 stop event to a threading.Event so _run_logger
            # can use a simple Python event without importing win32event.
            def _watch_win32_stop():
                win32event.WaitForSingleObject(self._win32_stop, win32event.INFINITE)
                self._thread_stop.set()

            threading.Thread(target=_watch_win32_stop, daemon=True).start()

            try:
                _run_logger(stop_event=self._thread_stop)
            except Exception as exc:
                servicemanager.LogErrorMsg(
                    f"{_SVC_DISPLAY} encountered an error: {exc}"
                )
            finally:
                servicemanager.LogMsg(
                    servicemanager.EVENTLOG_INFORMATION_TYPE,
                    servicemanager.PYS_SERVICE_STOPPED,
                    (self._svc_name_, ""),
                )

    _WIN32_AVAILABLE = True

except ImportError:
    _WIN32_AVAILABLE          = False
    _NetSentinelLoggerService = None
    # Provide stubs so the module still imports cleanly on non-Windows.
    win32service      = None  # type: ignore[assignment]
    win32serviceutil  = None  # type: ignore[assignment]


# ── CLI: status & debug (no pywin32 required for debug) ──────────────────────

def _cmd_status() -> None:
    if not _WIN32_AVAILABLE:
        print("pywin32 is not installed — cannot query service status.", file=sys.stderr)
        sys.exit(1)

    _labels = {
        win32service.SERVICE_RUNNING:       "RUNNING",
        win32service.SERVICE_STOPPED:       "STOPPED",
        win32service.SERVICE_START_PENDING: "STARTING",
        win32service.SERVICE_STOP_PENDING:  "STOPPING",
        win32service.SERVICE_PAUSED:        "PAUSED",
    }
    try:
        code = win32serviceutil.QueryServiceStatus(_SVC_NAME)[1]
        print(f"{_SVC_DISPLAY}: {_labels.get(code, f'UNKNOWN ({code})')}")
    except Exception as exc:
        print(f"Could not query service: {exc}", file=sys.stderr)
        sys.exit(1)


def _cmd_debug() -> None:
    """Run the logger in the foreground — not as a Windows service."""
    import signal

    _write_default_config()
    cfg = _load_config()

    print(f"{_SVC_DISPLAY} — debug mode (Ctrl+C to stop)")
    print(f"Config:   {_CONFIG_FILE}")
    print(f"Logs:     {_LOG_DIR}")
    print(f"Targets:  {', '.join(cfg['targets'])}")
    print(f"Interval: {cfg['interval_s']}s")
    extras = [n for n, v in [("jitter", cfg["enable_jitter"]),
                              ("dns",    cfg["enable_dns"]),
                              ("http",   cfg["enable_http"]),
                              ("arp",    cfg["enable_arp"])] if v]
    if extras:
        print(f"Extras:   {', '.join(extras)}")
    print()

    stop_event = threading.Event()

    def _on_signal(sig, frame):
        print("\nStopping…")
        stop_event.set()

    signal.signal(signal.SIGINT,  _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    log_path = _run_logger(stop_event=stop_event)
    print(f"Log saved: {log_path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    _USAGE = (
        f"Usage: python svc.py [install|start|stop|remove|restart|status|debug]\n"
        f"       Run as Administrator for install / start / stop / remove.\n\n"
        f"       python svc.py debug   — run in foreground without installing\n"
        f"       python svc.py status  — show current service state\n"
    )

    if len(sys.argv) < 2:
        print(_USAGE)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "status":
        _cmd_status()
        return

    if cmd == "debug":
        _cmd_debug()
        return

    if not _WIN32_AVAILABLE:
        print("pywin32 is not installed.", file=sys.stderr)
        print("Install:  pip install pywin32", file=sys.stderr)
        print("Post-install (run as Administrator): python -m pywin32_postinstall -install",
              file=sys.stderr)
        sys.exit(1)

    # install / start / stop / remove / restart — delegate to win32serviceutil.
    win32serviceutil.HandleCommandLine(_NetSentinelLoggerService)


if __name__ == "__main__":
    main()
