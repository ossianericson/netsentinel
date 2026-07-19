#!/usr/bin/env python3
"""
tools/monkey_test.py - Chaos / monkey harness for NetSentinel
==============================================================
Launches the app, then hammers the live UIA control tree for N iterations,
logging every interaction and detecting crashes, hangs, and memory leaks.

Usage (exe):
    python tools/monkey_test.py "dist\\NetSentinel.exe"

Usage (source - skips build step, faster iteration):
    python tools/monkey_test.py --source

Usage (attach to already-running app):
    python tools/monkey_test.py --connect

Options:
    --source              Launch via "python app.py" instead of an exe
    --connect             Attach to an already-running NetSentinel window
    -n / --iterations N   Iterations (default: 200)
    --duration SECS       Run by wall-clock time instead of a fixed iteration count
                          (overrides -n/--iterations when both are given)
    --chaos LEVEL         mild | moderate | wild (default: moderate)
    --seed N              RNG seed for reproducibility
    --no-screenshots      Skip PIL screenshots on crash
    --mem-limit MB        RSS limit before leak warning (default: 800)
    --log FILE            Log file path (default: netsentinel_monkey.log)
    --max-restarts N      Max app restarts on unexpected exit (default: 3)
    --warmup-secs SECS    Wait after overlay dismissal before first click (default: 5)

Requirements:
    pip install pywinauto psutil Pillow

Exit codes:
    0  All iterations completed, no crash
    1  App crashed or became unresponsive during testing
    2  Could not launch or connect to app
"""

import argparse
import collections
import ctypes
import dataclasses
import json
import logging
import random
import string
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

# ── Dependency checks ──────────────────────────────────────────────────────────

try:
    import psutil
except ImportError:
    if __name__ == "__main__":
        sys.exit("ERROR: psutil required.  pip install psutil")
    raise ImportError("psutil required — pip install psutil")

try:
    from pywinauto import Application, Desktop
    from pywinauto.base_wrapper import ElementNotEnabled, ElementNotVisible
    from pywinauto.findwindows import ElementNotFoundError
except ImportError:
    if __name__ == "__main__":
        sys.exit("ERROR: pywinauto required.  pip install pywinauto")
    raise ImportError("pywinauto required — pip install pywinauto")

try:
    from PIL import ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# ── Constants ──────────────────────────────────────────────────────────────────

_VERSION = "1.6.8"
# Title STARTS with "NetSentinel" — never matches VS Code's
# "monkey_test.py — NetSentinel — Visual Studio Code" title.
_WINDOW_RE = r"^NetSentinel"
_CONNECT_TIMEOUT = 60       # seconds to wait for the window after launch
_CONNECT_POLL = 2.0         # seconds between connection attempts
_HEALTH_INTERVAL = 2.0      # seconds between background health checks
_UNRESPONSIVE_SECS = 45     # seconds without a completed iteration before hang alarm
                            # (raised from 20 — "Update Feeds" on Threat Intel takes ~26 s)


def _crash_log_path() -> Optional[Path]:
    """Path of the crash log app.py's faulthandler writes to (see RULE 23).

    Resolved via the app's own get_app_data_dir() so the harness and the app can
    never disagree about the location.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from modules.utils import get_app_data_dir
        return Path(get_app_data_dir()) / "netsentinel_crash.log"
    except Exception:
        return None  # non-fatal — crash-log watching is best-effort

# ── Windows power management ───────────────────────────────────────────────────
_ES_CONTINUOUS       = 0x80000000
_ES_SYSTEM_REQUIRED  = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

# HWNDs of windows that must never receive WM_CLOSE from the dialog-guard.
# Captured at import time, before the app is launched, so they reflect the
# environment hosting the monkey test (PowerShell console, Windows Terminal,
# VS Code integrated terminal, etc.).
#
# _OWN_CONSOLE_HWND  — classic Win32 console (GetConsoleWindow); NULL in
#                       pseudo-terminals (VS Code, Windows Terminal conpty).
# _OWN_FOREGROUND_HWND — whatever window was in the foreground when the
#                        script was imported.  In VS Code this is the VS Code
#                        Electron window (class "Chrome_WidgetWin_1"); in a
#                        classic console it overlaps with _OWN_CONSOLE_HWND.
try:
    _OWN_CONSOLE_HWND: int = ctypes.windll.kernel32.GetConsoleWindow()
except Exception:
    _OWN_CONSOLE_HWND = 0

try:
    _OWN_FOREGROUND_HWND: int = ctypes.windll.user32.GetForegroundWindow()
except Exception:
    _OWN_FOREGROUND_HWND = 0

# UIA control types the dispatcher knows how to handle.
# Hyperlink is intentionally excluded — clicking UIA Hyperlink controls
# activates their default action (follows the link), which opens Chrome,
# IE, Spotify, or any registered URI-scheme handler outside the app.
_SUPPORTED_TYPES = frozenset({
    "Button", "Edit", "ComboBox", "CheckBox", "RadioButton",
    "ListItem", "TabItem", "Slider", "TreeItem",
    "MenuItem", "SplitButton",
})

# ── NetSentinel-specific blacklist ─────────────────────────────────────────────
#
# Matched case-insensitively against (control_name + " " + automation_id).
# Add patterns here whenever a new page introduces a dangerous button.
#
_BLACKLIST: List[str] = [
    # --- External side effects (notifications, webhooks, email) ---
    "send test",        # "Send Test Email", "Test Send"
    "test email",
    "test webhook",
    "test push",        # Pushover test
    "test ntfy",
    "test telegram",
    "send email",
    "publish",          # MQTT "Publish" button
    # --- Active network scans (long-running, may affect real network) ---
    "run login test",   # credentialed_scan — can lock accounts
    "start scan",
    "launch scan",
    "full discovery",
    "syn scan",
    "port scan",
    "scan ports",        # Port Scanner page "Scan Ports" button — TCP connect scan
    "run diagnostics",  # triggers several network probes
    # --- Destructive data operations ---
    "delete",
    "remove device",
    "clear all",
    "wipe",
    "purge",
    "reset to default",
    # --- External installer triggers (hangs UI waiting for winget) ---
    "install speedtest",
    "install ookla",
    "install npcap",
    # --- Window chrome (frameless titlebar buttons) ---
    # ONLY app-lifecycle controls belong here.  A control may be blacklisted
    # because clicking it kills or hides the app under test -- NEVER because
    # clicking it crashed the app.  A crash is the harness doing its job; the
    # fix is to fix the app, not to stop clicking the button.
    #
    # History: maximize/restore used to be blacklisted here (and the whole top
    # 60px of the window was spatially excluded in _enabled_controls()).  That
    # made the entire header invisible to chaos testing, which is why a broken
    # maximize button -- it called showFullScreen(), covering the taskbar --
    # shipped to users unnoticed.  Maximize/restore are benign and reversible,
    # so they are now exercised; see _act_window_chrome().
    "",   # Close   -- terminates the app under test
    "",   # Minimize -- hides the window, so UIA can no longer see any control
    "close/x",     # accessible-name variant of the close button
    # NOTE: "_chromebutton" (auto_id catch-all) deliberately NOT blacklisted --
    # it also matched maximize/restore.  Close/minimize are caught by glyph above.
    # --- System power / OS lifecycle (initiates Windows restart or shutdown) ---
    # These are the primary source of the "Windows restart dialog" bug — any button
    # containing these words must never be clicked during automated testing.
    "restart",       # "Restart", "Restart Service", "Restart Now", "Restart App"
    "reboot",        # "Reboot Router", "Reboot Device", "Reboot System"
    "shutdown",      # "Shutdown", "Shut Down System"
    "power off",     # "Power Off Device"
    # --- App lifecycle ---
    "quit",
    "exit application",
    # --- File open/save dialogs (Windows native) — must never be opened ---
    # A Windows file picker steals focus from the app and stalls the harness.
    "browse",           # any "Browse…" button for file/folder selection
    "folder",           # "Open Plugins Folder" (tabs_recon.py, settings_cards.py),
                        # "Open Folder ›" (reports_page.py) — spawns a real Windows
                        # Explorer window (subprocess.Popen(["explorer", ...]) or
                        # QDesktopServices.openUrl on a folder path) that steals
                        # foreground focus.  Explorer is not a Win32 dialog (class
                        # #32770) so _dismiss_blocking_dialogs() never catches it, and
                        # it does not match _is_system_hwnd() either — once open, the
                        # tester's coordinate-based click_input() calls can land on
                        # the Explorer window instead of NetSentinel controls
                        # (confirmed cause of "monkey clicking around in File
                        # Explorer" after ~10 min of a chaos run).
    "floor plan",       # WiFi Heatmap — floor plan image import
    "choose file",      # generic file picker label
    "select file",      # generic file picker label
    "load plugin",      # plugin file loader
    "import plugin",    # plugin file loader
    "save as",          # Save As… dialog
    "generate report",  # triggers a file-save dialog
    # --- Export / file creation (clutters disk, may open save dialogs) ---
    "export pdf",
    "export csv",
    "export json",
    "export report",
    "export png",       # Network Map / WiFi Heatmap — opens native OS file save dialog
    "save pdf",
    "save report",
    # --- Log-hub file loaders (opens native OS file open dialog) ---
    "load  analyse",    # Log Hub "⊕  Load  Analyse" (double-space as in UIA name)
    "load analyse",     # variant — single-space normalised form
    # --- Credential / auth dialogs that block automation ---
    "sign in",
    "authenticate",
    # --- Dangerous config actions ---
    "factory reset",
    "restore defaults",
    # --- Active network probes added in v2.0+ ---
    "run probe",        # Service Diagnostics — fires DNS/TCP/HTTPS/ICMP/traceroute
    "diagnose",         # Service Heartbeat "Diagnose →" button → fires probes
    "run health check", # health check probe
    "check connection", # connectivity probe
    "run selected",     # Overview page Security Scan panel "Run Selected" → _advance_security_audit() fires selected tools sequentially
    "rescan",           # Scan Center card "▶  Rescan" → rescan_requested signal → triggers full network scan
    "re-run",           # re-triggers any prior scan/probe
    "run again",        # re-triggers any prior scan/probe
    # --- Packet capture / active monitors (Scapy / Npcap) ---
    # "start capture" only matched "App Traffic" button but NOT "Start STP Capture"
    # or "Start Broadcast Capture" (word between "start" and "capture").
    # Replace with bare "capture" to catch ALL capture-starting buttons regardless
    # of what appears between the words.
    "capture",          # catches: "Start STP Capture", "Start Broadcast Capture",
                        #          "Start App Traffic Capture", etc.
    "start sniff",      # 802.11 monitor — passive frame capture
    "start detection",  # DHCP Rogue — passive ARP/DHCP sniff
    # --- Npcap install/download buttons (open external browser or installer) ---
    # NpcapMissingBanner shows these buttons on all Npcap-required pages.
    # Clicking them opens a browser (focus steal) or a Windows installer dialog.
    "download npcap",   # NpcapMissingBanner "Download Npcap →" (Windows)
    "get npcap",        # NpcapMissingBanner "Get Npcap at npcap.com →" (Store)
    "view download",    # NpcapMissingBanner "View download →" (macOS/Linux)
    # --- Network segment editor (opens blocking inline dialog) ---
    "add segment",      # opens segment name/colour editor dialog
    # --- Scheduled task triggers ---
    "run now",          # fires scheduled report delivery immediately
    "schedule now",     # fires a maintenance window or scheduled task
    # --- Extend / Hardware Hub (file dialogs + blocking modals) ---
    # These buttons open QFileDialog or modal wizard dialogs.  Even with
    # DontUseNativeDialog, the dialog briefly takes foreground; if
    # _post_click_dialog_guard() fires while GetForegroundWindow() transiently
    # returns the Windows Desktop HWND, _dismiss_native_window() sends
    # WM_CLOSE to the Desktop, triggering the Shut Down Windows dialog.
    "add integration",  # HardwareIntegrationPage "＋ Add Integration" → QFileDialog.getOpenFileName
    "import .nspkg",    # HardwareIntegrationPage "⬡ Import .nspkg" → QFileDialog.getOpenFileName
    "nspkg",            # catch any variant of the .nspkg import button
    "save template",    # PluginGuide "💾 Save template as .py…" → QFileDialog.getSaveFileName
    "new plugin",       # HardwareIntegrationPage "⬡ New Plugin" → blocking modal wizard dialog
    # --- HubCard per-plugin action buttons (open file dialogs or credential dialogs) ---
    "re-import",        # HubCard "⤵ Re-import" → QFileDialog.getOpenFileName via _on_browse()
    "re-enter",         # HubCard "🔑 Re-enter Password" → show_credential_dialog() modal
    "install dep",      # HubCard "⬇ Install dependency" → PipInstallDialog modal
    # --- Opens external browser/app on a real file or URL (confirmed by a real-mouse
    # chaos run, 2026-07-05: monkey_mouse_test.py launched Edge + Explorer windows
    # mid-run by real-clicking these) ---
    "open log file",    # Network Logger "Open Log File" (tabs_logger.py) → webbrowser.open()
    "open dashboard",   # Home "Open Dashboard" (home_data_mixin.py) → QDesktopServices.openUrl()
    "open in browser",  # Lab Mode / Overview / Network Doc post-export → webbrowser.open()
    "view on nvd",      # CVE Lookup row context menu → webbrowser.open(nvd.nist.gov/...)
    "open in editor",   # Plugin wizard "Plugin Created" dialog (plugin_wizard_mixin.py) →
                        # os.startfile() on the generated .py template. On a stock Windows
                        # box .py has no editor association, so it opens in Notepad, which
                        # steals foreground focus (not a #32770 dialog, so the dialog-guard
                        # can't catch it by class). "new plugin"/"save template" already
                        # block the entry points; this covers the post-create dialog too.
]

# Safe pages to navigate to via the Ctrl+K command palette.
# Only read-only / lightweight pages are listed.
_SAFE_PAGES: List[str] = [
    # Getting Started — always-safe read-only entry points
    "Overview", "Home",
    # Monitor — read-only aggregated views (no scan buttons)
    "Active Monitors", "Network Timeline", "Availability History",
    "Inventory Changes", "Uptime & SLA",
    # Reports / Analysis — read-only
    "Network Grade", "Trend Forecasts", "IP Calculator", "Network Doc",
    "Root Cause Correlator",
    # Always-on passive logger — read-only display
    "Network Logger",
    # Geolocation / viz — no network calls
    "Geolocation Map", "Protocol Visualizer",
    # Education — fully read-only
    "Lab Mode", "Feature Guide", "Help & Reference",
]

# Keyboard shortcuts that are safe to inject at any time.
_SAFE_SHORTCUTS: List[str] = [
    "^f",       # Ctrl+F — sidebar search
    "{ESC}",    # Esc    — close flyout / dismiss overlay
]

# ── Configuration ──────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Config:
    exe_path: Optional[str] = None   # None when using --source or --connect
    use_source: bool = False
    connect_only: bool = False       # attach to already-running app, do not launch
    iterations: int = 200
    duration_secs: Optional[float] = None  # when set, run by wall-clock time instead of iteration count
    chaos: str = "moderate"          # mild | moderate | wild
    seed: Optional[int] = None
    screenshots: bool = True
    mem_limit_mb: int = 1500
    output_dir: str = "test_output"  # all generated files written here
    log_file: str = ""               # empty = auto-derive from output_dir
    cpu_threshold: float = 35.0      # % CPU — wait below this before acting
    cpu_wait_max: float = 12.0       # max seconds to wait for CPU to settle
    nav_prob: float = 0.15           # probability of a navigation action per iteration
    history_size: int = 15
    focus_interval: float = 1.5     # seconds between focus-heartbeat pulses
    prevent_sleep: bool = True       # suppress Windows sleep/screensaver
    tracemalloc: bool = False        # enable in-process tracemalloc snapshots in app
    max_restarts: int = 3            # auto-restart app when window vanishes unexpectedly
    warmup_secs: float = 5.0        # seconds to wait after overlay dismissal before first click

    def resolved_log_file(self) -> str:
        if self.log_file:
            return self.log_file
        return str(Path(self.output_dir) / "monkey.log")


# ── Statistics ─────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Stats:
    t0: float = dataclasses.field(default_factory=time.time)
    completed: int = 0
    skipped: int = 0
    exceptions: int = 0
    crashes: int = 0
    blacklisted: int = 0
    peak_rss_mb: float = 0.0
    focus_stolen: int = 0   # how many times another window grabbed foreground
    off_window: int = 0     # raw-mouse actions skipped: target point outside live window rect
    restarts: int = 0       # app restart count (auto-restart on unexpected exit)
    by_type: Dict[str, int] = dataclasses.field(default_factory=dict)
    by_action: Dict[str, int] = dataclasses.field(default_factory=dict)

    def record(self, ctype: str, action: str) -> None:
        self.by_type[ctype] = self.by_type.get(ctype, 0) + 1
        key = action.split(":")[0]
        self.by_action[key] = self.by_action.get(key, 0) + 1

    @property
    def elapsed(self) -> float:
        return time.time() - self.t0

    def to_dict(self) -> Dict:
        return {
            "elapsed_s": round(self.elapsed, 1),
            "iterations_completed": self.completed,
            "iterations_skipped": self.skipped,
            "exceptions_caught": self.exceptions,
            "crashes": self.crashes,
            "blacklisted_skipped": self.blacklisted,
            "peak_rss_mb": round(self.peak_rss_mb, 1),
            "focus_stolen_count": self.focus_stolen,
            "off_window_skips": self.off_window,
            "restarts": self.restarts,
            "by_control_type": self.by_type,
            "by_action": self.by_action,
        }


# ── Action history ─────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Action:
    n: int
    ts: str
    ctype: str
    name: str
    auto_id: str
    action: str
    result: str


class History:
    def __init__(self, maxsize: int):
        self._q: collections.deque = collections.deque(maxlen=maxsize)

    def add(self, a: Action) -> None:
        self._q.append(a)

    def dump(self) -> List[Dict]:
        return [dataclasses.asdict(a) for a in self._q]

    def fmt(self) -> str:
        lines = ["Last actions (oldest -> newest):"]
        for a in self._q:
            lines.append(
                f"  [{a.ts}] #{a.n:4d}  {a.ctype:<14} {a.action:<24}  "
                f"name={a.name!r}  -> {a.result}"
            )
        return "\n".join(lines)


# ── Logging ────────────────────────────────────────────────────────────────────

def _setup_log(log_file: str) -> logging.Logger:
    log = logging.getLogger("monkey")
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s", "%H:%M:%S.%f"[:-3])
    # Use errors='replace' so non-cp1252 characters in window titles / control
    # names produce a '?' rather than crashing the entire test run.
    import io as _io
    ch = logging.StreamHandler(_io.TextIOWrapper(
        sys.stdout.buffer, encoding=sys.stdout.encoding or "utf-8", errors="replace"
    ))
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    log.addHandler(ch)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    log.addHandler(fh)
    return log


# ── Helpers ────────────────────────────────────────────────────────────────────

def _safe_name(ctrl) -> str:
    try:
        return (ctrl.window_text() or "").strip()[:80]
    except Exception:
        return ""


def _safe_id(ctrl) -> str:
    try:
        return (ctrl.element_info.automation_id or "").strip()[:80]
    except Exception:
        return ""


def _safe_type(ctrl) -> str:
    try:
        return ctrl.element_info.control_type or "Unknown"
    except Exception:
        return "Unknown"


def _is_main_window(win) -> bool:
    """True when *win* looks like the main app window and not a toast / popup.

    NetSentinel's own toast notifications and Windows system-tray popups are
    small (< 600 × 400 px).  The main app window is always larger.
    """
    try:
        r = win.rectangle()
        return (r.right - r.left) >= 600 and (r.bottom - r.top) >= 400
    except Exception:
        return False


# Process names that are never NetSentinel — prevents connecting to VS Code
# when its window title contains "NetSentinel" (workspace folder name).
_EXCLUDED_PROCESS_NAMES = frozenset({
    "code.exe",       # VS Code
    "code - insiders.exe",
    "devenv.exe",     # Visual Studio
    "msedge.exe",     # Edge
    "chrome.exe",
    "firefox.exe",
    "explorer.exe",   # Windows Explorer
    "notepad.exe",
    "notepad++.exe",
})

# Process names that must NEVER receive a dismiss/close message from
# _is_system_hwnd(), regardless of *which* window handle they present.
#
# _OWN_FOREGROUND_HWND (captured once, at script-import time) only protects
# the ONE specific hwnd that happened to be foreground at that instant. That
# is not reliable: when the monkey test is launched from a background/detached
# shell (no real interactive foreground yet), the captured hwnd may not be
# the IDE window at all — and even when it is, the IDE can open new top-level
# windows (a second workspace, a notification, a quick-pick popup) with a
# different hwnd that the single captured value doesn't cover. VS Code's
# window class ("Chrome_WidgetWin_1") is not in the system-class list either,
# so once the hwnd check misses, _dismiss_native_window()'s escalation ends in
# a real WM_CLOSE against the editor hosting the automation itself.
# Checking by owning PROCESS name protects every window the IDE ever opens,
# not just the one hwnd sampled at import time.
_PROTECTED_APP_PROCESS_NAMES = frozenset({
    "code.exe",       # VS Code
    "code - insiders.exe",
    "cursor.exe",     # Cursor (VS Code fork)
    "devenv.exe",     # Visual Studio
})


def _is_netsentinel_window(win, expected_pid: Optional[int] = None) -> bool:
    """True when *win* is the NetSentinel main window, not an IDE or browser.

    Checks in order: size (fast), process PID match (when we launched the app),
    process name exclusion (blocks VS Code, browsers, etc.).
    """
    if not _is_main_window(win):
        return False
    try:
        win_pid = win.element_info.process_id
        # If we know which PID we launched, the window must belong to it.
        if expected_pid is not None and win_pid != expected_pid:
            return False
        # Reject windows owned by known IDEs / browsers by process name.
        proc_name = psutil.Process(win_pid).name().lower()
        if proc_name in _EXCLUDED_PROCESS_NAMES:
            return False
    except Exception:
        pass  # non-fatal — fall back to size-only check
    return True


def _window_title_ok(win) -> bool:
    """True when the window title matches _WINDOW_RE (used only in --connect fallback)."""
    try:
        import re as _re
        return bool(_re.search(_WINDOW_RE, win.window_text() or ""))
    except Exception:
        return False


def _is_blacklisted(name: str, auto_id: str) -> bool:
    combined = (name + " " + auto_id).lower()
    if combined.strip().startswith(("http://", "https://")):
        # Router quick-link buttons (tabs_network.py "btnRouterLink") use the
        # target URL itself as the accessible name — e.g. "http://192.168.1.1/" —
        # and fire webbrowser.open() on click. No fixed string can match every
        # gateway IP, so match on the URL prefix instead.
        return True
    return any(pat in combined for pat in _BLACKLIST)


def _realistic_text(chaos: str) -> str:
    """Return context-aware input text rather than pure random garbage."""
    ips = ["192.168.1.1", "192.168.0.1", "10.0.0.1", "172.16.0.1",
           "192.168.1.100", "10.0.0.254", "0.0.0.0"]
    hosts = ["gateway", "router", "nas", "desktop-1", "laptop", "raspberrypi", "localhost"]
    ports = ["80", "443", "22", "8080", "3000", "8443", "53"]
    emails = ["test@example.com", "admin@local.net"]

    if chaos == "mild":
        return random.choice(ips + hosts)
    if chaos == "moderate":
        pool = ips + hosts + ports + emails + ["", "255.255.255.0", "subnet"]
        return random.choice(pool)
    # wild — include some genuinely junk inputs
    junk = "".join(random.choices(string.printable[:80], k=random.randint(1, 40)))
    pool = ips + hosts + ports + [junk, "", " " * 8, "'; DROP TABLE devices; --"]
    return random.choice(pool)


def _screenshot(label: str, log: logging.Logger, output_dir: str = ".") -> Optional[str]:
    if not _HAS_PIL:
        return None
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = str(Path(output_dir) / f"monkey_{label}_{ts}.png")
        ImageGrab.grab().save(path)
        log.info("Screenshot: %s", path)
        return path
    except Exception as exc:
        log.debug("Screenshot failed: %s", exc)
        return None


def _wait_cpu(proc: psutil.Process, threshold: float, timeout: float) -> bool:
    """Return when CPU% < threshold, or after timeout. Always returns True (best-effort)."""
    deadline = time.time() + timeout
    try:
        proc.cpu_percent(interval=None)   # prime the counter
    except psutil.NoSuchProcess:
        return False
    while time.time() < deadline:
        try:
            if proc.cpu_percent(interval=0.4) < threshold:
                return True
        except psutil.NoSuchProcess:
            return False
    return True   # proceed even if CPU is still high


def _get_foreground_hwnd() -> int:
    """Return the HWND of the current foreground window, or 0 on error."""
    try:
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return 0


def _is_system_hwnd(hwnd: int) -> bool:
    """Return True when *hwnd* belongs to a Windows shell, system, or console window.

    Sending WM_CLOSE (or WM_COMMAND/IDCANCEL) to the Desktop/Shell window
    triggers the "Shut Down Windows" dialog — the same mechanism as the
    Alt+F4-to-Desktop bug fixed in fac15b5.  This guard must be checked
    before every call to _dismiss_native_window() so we never accidentally
    close-message a system window regardless of which button was last clicked.

    Also protects terminal/console windows:  if the monkey test is running
    inside a PowerShell or Windows Terminal window and that window briefly
    steals focus (e.g. the user clicks it, or a control's tooltip moves it),
    the dialog-guard must NOT send WM_CLOSE to it — that would kill the host
    process and terminate the test.  Bug first seen at interaction ~2709 when
    hwnd=0x1079a (a terminal window) gained focus and the guard dismissed it.

    Covered cases:
      HWND 0 / NULL                  — GetForegroundWindow() returned NULL
      GetDesktopWindow()             — the desktop root window (class "Progman")
      GetShellWindow()               — the Windows shell host
      _OWN_CONSOLE_HWND              — the console window running this script (classic console)
      _OWN_FOREGROUND_HWND           — foreground window at import time (VS Code, Windows Terminal)
      class "Progman"                — desktop icon host
      class "WorkerW"                — behind-the-desktop wallpaper worker
      class "DV2ControlHost"         — Windows taskbar / Start menu host
      class "Shell_TrayWnd"          — primary taskbar window
      class "Shell_SecondaryTrayWnd" — secondary monitor taskbar
      class "ConsoleWindowClass"     — classic Win32 console (cmd, PowerShell)
      class "CASCADIA_HOSTING_WINDOW_CLASS" — Windows Terminal app
      class "PseudoConsoleWindow"    — conhost pseudo-console host
      owning process in _PROTECTED_APP_PROCESS_NAMES — VS Code / Cursor / Visual
        Studio, by PID rather than hwnd, so every window the IDE owns is safe
        (not just the one captured at import time)
    """
    if not hwnd:
        return True
    # Explicitly protect the terminal/IDE window that launched the monkey test.
    # _OWN_CONSOLE_HWND covers classic cmd/PowerShell (GetConsoleWindow).
    # _OWN_FOREGROUND_HWND covers VS Code / Windows Terminal (pseudo-console hosts
    # where GetConsoleWindow() returns NULL but the IDE window is in the foreground
    # at script import time, before the app under test is launched).
    if _OWN_CONSOLE_HWND and hwnd == _OWN_CONSOLE_HWND:
        return True
    if _OWN_FOREGROUND_HWND and hwnd == _OWN_FOREGROUND_HWND:
        return True
    try:
        user32 = ctypes.windll.user32
        if hwnd == user32.GetDesktopWindow():
            return True
        if hwnd == user32.GetShellWindow():
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in (
            "Progman", "WorkerW", "DV2ControlHost",
            "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
            # Terminal / console windows — never send WM_CLOSE to these or
            # the monkey test kills its own host process (seen at iter ~2709).
            "ConsoleWindowClass",           # classic cmd / PowerShell console
            "CASCADIA_HOSTING_WINDOW_CLASS", # Windows Terminal (wt.exe)
            "PseudoConsoleWindow",          # conhost pseudo-console wrapper
        ):
            return True
        # Process-name check — protects EVERY window the IDE owns (any
        # workspace window, notification, popup), not just the single hwnd
        # _OWN_FOREGROUND_HWND happened to capture at import time. See the
        # comment on _PROTECTED_APP_PROCESS_NAMES for why the hwnd-only
        # check above is insufficient on its own.
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value:
            proc_name = psutil.Process(pid.value).name().lower()
            if proc_name in _PROTECTED_APP_PROCESS_NAMES:
                return True
    except Exception:
        pass  # non-fatal — ctypes/psutil call failed; treat hwnd as non-desktop
    return False


def _describe_hwnd(hwnd: int) -> str:
    """Best-effort 'class=... proc=... pid=...' description of a window, for diagnostics.

    Used when a system/desktop window steals foreground so the log records exactly what
    the thief is (class name + owning process) instead of only a bare hwnd — e.g. to tell
    a Progman/WorkerW desktop window apart from a shell or notification host.
    """
    cls = proc = "?"
    pid_val = 0
    try:
        user32 = ctypes.windll.user32
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        cls = buf.value or "?"
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_val = pid.value
        if pid_val:
            proc = psutil.Process(pid_val).name()
    except Exception:
        pass  # non-fatal — diagnostic only; return whatever was resolved
    return f"class={cls!r} proc={proc!r} pid={pid_val}"


def _force_foreground(hwnd: int) -> None:
    """Force a window to the foreground using the AttachThreadInput trick.

    Plain SetForegroundWindow silently fails from background processes after
    Windows engages focus-theft protection.  Attaching to the target thread's
    input queue grants the required permission.
    """
    try:
        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        cur_tid  = kernel32.GetCurrentThreadId()
        tgt_tid  = user32.GetWindowThreadProcessId(hwnd, None)
        attached = (tgt_tid and cur_tid != tgt_tid and
                    bool(user32.AttachThreadInput(cur_tid, tgt_tid, True)))
        try:
            user32.ShowWindow(hwnd, 9)        # SW_RESTORE (un-minimise if needed)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(cur_tid, tgt_tid, False)
    except Exception:
        pass  # non-fatal — best-effort; health monitor catches real window loss


def _prevent_sleep_begin(log: logging.Logger) -> None:
    """Prevent Windows sleep and screensaver while this process runs."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
        )
        log.info("[power] Sleep and screensaver suppressed")
    except Exception as exc:
        log.warning("[power] Could not suppress sleep: %s", exc)


def _prevent_sleep_end(log: logging.Logger) -> None:
    """Restore default Windows sleep/screensaver behaviour."""
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
        log.info("[power] Sleep and screensaver restored")
    except Exception:
        pass  # non-fatal


# ── Control interaction dispatcher ────────────────────────────────────────────

def _act_button(ctrl, chaos: str) -> str:
    ctrl.click_input()
    return "click"


def _act_edit(ctrl, chaos: str) -> str:
    text = _realistic_text(chaos)
    # Strip chars that pywinauto type_keys() treats as key-sequence tokens;
    # leaving them in raises KeySequenceError on controls like port-number fields.
    _PYWINAUTO_SPECIAL = str.maketrans("", "", "+^%~(){}")
    safe_text = text.translate(_PYWINAUTO_SPECIAL)
    try:
        ctrl.set_focus()
        # select-all then overwrite, rather than appending
        ctrl.type_keys("^a", pause=0.05)
    except Exception:
        logging.debug("select-all failed; continuing")
    ctrl.type_keys(safe_text, with_spaces=True, pause=0.02)
    return f"type:{safe_text!r}"


def _act_combobox(ctrl, chaos: str) -> str:
    try:
        count = ctrl.item_count()
        if count and count > 0:
            idx = random.randint(0, min(count - 1, 6))
            ctrl.select(idx)
            return f"select:{idx}"
    except Exception:
        logging.debug("item_count or select failed")
    ctrl.click_input()
    time.sleep(0.15)  # let popup render
    try:
        # Immediately close the dropdown we just opened. Without this, the popup
        # holds focus for the rest of the run and _assert_focus() skips every
        # subsequent iteration (accounts for ~80 % skip rate in mild/wild chaos).
        ctrl.type_keys("{ESCAPE}")
    except Exception:
        pass  # non-fatal — popup may have already closed
    return "click_open"


def _act_checkbox(ctrl, chaos: str) -> str:
    ctrl.toggle()
    return "toggle"


def _act_radio(ctrl, chaos: str) -> str:
    ctrl.click_input()
    return "click"


def _act_listitem(ctrl, chaos: str) -> str:
    ctrl.click_input()
    return "click"


def _act_tabitem(ctrl, chaos: str) -> str:
    ctrl.click_input()
    return "click_tab"


def _act_slider(ctrl, chaos: str) -> str:
    try:
        r = ctrl.rectangle()
        w = r.right - r.left
        x = int(w * random.uniform(0.1, 0.9))
        y = (r.bottom - r.top) // 2
        ctrl.click_input(coords=(x, y))
        return "slide"
    except Exception:
        ctrl.click_input()
        return "click_fallback"


def _act_treeitem(ctrl, chaos: str) -> str:
    ctrl.click_input()
    return "click"


def _act_fallback(ctrl, chaos: str) -> str:
    ctrl.click_input()
    return "click_fallback"


_DISPATCHER: Dict[str, Callable] = {
    "Button":       _act_button,
    "Edit":         _act_edit,
    "ComboBox":     _act_combobox,
    "CheckBox":     _act_checkbox,
    "RadioButton":  _act_radio,
    "ListItem":     _act_listitem,
    "TabItem":      _act_tabitem,
    "Slider":       _act_slider,
    "TreeItem":     _act_treeitem,
    "MenuItem":     _act_button,
    "SplitButton":  _act_button,
}


# ── Navigation actions ─────────────────────────────────────────────────────────

def _nav_shortcut(win, chaos: str) -> str:
    sc = random.choice(_SAFE_SHORTCUTS)
    win.type_keys(sc)
    time.sleep(0.25)
    return f"shortcut:{sc}"


def _nav_command_palette(win, chaos: str) -> str:
    """Open Ctrl+K, type a partial page name, confirm, then close if needed."""
    page = random.choice(_SAFE_PAGES)
    try:
        win.type_keys("^k")
        time.sleep(0.45)
        # Type only first 6 chars for fuzzy match
        win.type_keys(page[:6], with_spaces=True, pause=0.04)
        time.sleep(0.30)
        win.type_keys("{ENTER}")
        time.sleep(0.50)
        return f"palette:{page}"
    except Exception as exc:
        try:
            win.type_keys("{ESC}")
        except Exception:
            logging.debug("ESC after palette error failed")
        return f"palette_err:{exc.__class__.__name__}"


def _nav_escape(win, chaos: str) -> str:
    """Dismiss any overlay / flyout that may have opened."""
    win.type_keys("{ESC}")
    time.sleep(0.2)
    return "esc"


# ── Window-chrome actions ─────────────────────────────────────────────────────
#
# The window chrome was a total blind spot: every chrome button was blacklisted
# AND the whole top 60px of the window was spatially excluded, so no chaos run
# ever touched the header.  That is how a maximize button that actually called
# showFullScreen() (covering the taskbar) reached users.
#
# These also reach what UIA cannot: maximize/restore/snap live in the NON-CLIENT
# area, which is not a UIA control.  They are driven with keystrokes and Win32,
# and they are the surface where the known Snap-Layout COM fault (0x8001010d)
# lives -- so the crash-log watcher (_check_crash_log) is what makes them a net.

def _chrome_maximize_toggle(win, chaos: str) -> str:
    """Win+Up / Win+Down — the OS's own maximize/restore path."""
    key = random.choice(["{VK_UP}", "{VK_DOWN}"])
    win.type_keys(f"{{VK_LWIN down}}{key}{{VK_LWIN up}}")
    time.sleep(0.45)   # let the DWM maximize/restore animation finish
    return f"win+{'up' if 'UP' in key else 'down'}"


def _chrome_snap_side(win, chaos: str) -> str:
    """Win+Left / Win+Right — Aero Snap. Restores afterwards so the run continues
    against a normally-sized window."""
    key = random.choice(["{VK_LEFT}", "{VK_RIGHT}"])
    win.type_keys(f"{{VK_LWIN down}}{key}{{VK_LWIN up}}")
    time.sleep(0.5)
    win.type_keys("{VK_LWIN down}{VK_DOWN}{VK_LWIN up}")  # un-snap
    time.sleep(0.4)
    return f"snap:{'left' if 'LEFT' in key else 'right'}"


def _chrome_snap_layout_flyout(win, chaos: str) -> str:
    """Win+Z — the Windows 11 Snap Layouts flyout.

    This is the exact interaction the gated-off _install_snap_subclass() hook
    exists to support, and the one that produced the 0x8001010d COM-reentrancy
    fault.  ESC dismisses it so the run continues either way.
    """
    win.type_keys("{VK_LWIN down}z{VK_LWIN up}")
    time.sleep(0.7)
    win.type_keys("{ESC}")
    time.sleep(0.3)
    return "snap_layout_flyout"


def _chrome_hover_maximize(win, chaos: str) -> str:
    """Park the cursor over the maximize button.

    Hovering is what triggers the Snap-Layout flyout on a window that reports
    HTMAXBUTTON, so this exercises the WM_NCHITTEST path even with no click.
    The three _ChromeButtons are 46px wide, flush right: close ~23px in from the
    right edge, maximize ~69px, minimize ~115px.
    """
    try:
        r = win.rectangle()
        x, y = r.right - 69, r.top + 21
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.6)   # dwell long enough for the flyout to be offered
        return "hover_maximize"
    except Exception as exc:
        return f"hover_err:{exc.__class__.__name__}"


_CHROME_ACTIONS = [
    _chrome_maximize_toggle,
    _chrome_snap_side,
    _chrome_hover_maximize,
    _chrome_snap_layout_flyout,
]

_NAV_MILD = [_nav_shortcut, _nav_escape, _chrome_maximize_toggle]
_NAV_MODERATE = [_nav_shortcut, _nav_command_palette, _nav_escape,
                 _chrome_maximize_toggle, _chrome_hover_maximize, _chrome_snap_side]
_NAV_WILD = [_nav_shortcut, _nav_command_palette, _nav_escape, _nav_escape,
             _nav_command_palette] + _CHROME_ACTIONS


def _nav_pool(chaos: str) -> List[Callable]:
    return {"mild": _NAV_MILD, "wild": _NAV_WILD}.get(chaos, _NAV_MODERATE)


# ── Main tester ────────────────────────────────────────────────────────────────

class MonkeyTester:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
        self.log = _setup_log(cfg.resolved_log_file())
        random.seed(cfg.seed)

        self.stats = Stats()
        self.hist = History(cfg.history_size)

        self._proc: Optional[psutil.Process] = None
        self._app: Optional[Application] = None
        self._win = None
        self._last_iter_time = time.time()
        self._stop = threading.Event()
        # White-frame/hang investigation (2026-07-19): exit code of the last
        # process _alive() observed disappearing, so a crash report can say
        # HOW it died instead of just that it did.
        self._last_exit_code: Optional[int] = None

        # Baseline the append-only crash log so _check_crash_log() can tell a fault
        # from THIS run apart from the weeks of history already in the file.
        self._crash_log: Optional[Path] = _crash_log_path()
        self._crash_log_size0 = 0
        if self._crash_log is not None:
            try:
                self._crash_log_size0 = self._crash_log.stat().st_size
            except OSError:
                self._crash_log_size0 = 0  # not created yet
            self.log.info("[setup] crash-log baseline: %s (%d bytes)",
                          self._crash_log, self._crash_log_size0)

    # ── Focus heartbeat & power management ───────────────────────────────

    def _focus_heartbeat(self) -> None:
        """Background thread: re-asserts window focus every focus_interval seconds.

        Windows blocks SetForegroundWindow from background processes after a while.
        The AttachThreadInput trick in _force_foreground bypasses this restriction
        so the tested app stays in the foreground between chaos iterations.
        """
        while not self._stop.is_set():
            self._stop.wait(self.cfg.focus_interval)
            try:
                if self._win is not None and self._win.exists():
                    hwnd = getattr(self._win, "handle", 0) or 0
                    if hwnd:
                        _force_foreground(hwnd)
                    else:
                        self._win.set_focus()
            except Exception:
                pass  # non-fatal — health monitor handles real window loss

    def _assert_focus(self) -> bool:
        """Verify NetSentinel is the foreground window and reclaim it if not.

        Called before every single click.  If another window (VSCode, Explorer,
        a browser) stole focus since the last interaction, we reclaim it before
        touching any control.  If reclaim fails, the iteration is skipped — we
        never click into an unknown foreground window.

        Returns True when the app is (or has been restored to) the foreground.
        Returns False only when the hwnd is known and reclaim definitively failed.
        """
        try:
            hwnd = getattr(self._win, "handle", 0) or 0
            if not hwnd:
                # No hwnd available — best-effort fallback
                try:
                    self._win.set_focus()
                except Exception:
                    pass  # non-fatal — window ok check in health monitor
                return True
            fg = _get_foreground_hwnd()
            if fg == hwnd:
                return True  # fast path — already foreground
            # Focus drifted to another window
            self.stats.focus_stolen += 1
            # Screenshot what stole focus (first 5 times to avoid flood)
            if self.cfg.screenshots and self.stats.focus_stolen <= 5:
                _screenshot(
                    f"focus_stolen_{self.stats.focus_stolen:02d}",
                    self.log,
                    self.cfg.output_dir,
                )
            self.log.debug(
                "[focus] stolen by hwnd=0x%x (stolen_count=%d) — reclaiming",
                fg, self.stats.focus_stolen,
            )
            _force_foreground(hwnd)
            time.sleep(0.25)
            fg2 = _get_foreground_hwnd()
            if fg2 != hwnd:
                # Direct reclaim failed — try to dismiss the foreign window before giving up.
                # This recovers from dialogs that the post-click guard and blacklist both
                # missed (e.g. a newly added page that opens a file picker).
                self.log.debug(
                    "[focus] reclaim failed (fg=0x%x) — attempting to dismiss foreign window",
                    fg2,
                )
                # Root guard: same protection as _post_click_dialog_guard — never
                # send WM_CLOSE to the Desktop/Shell (triggers Shut Down Windows dialog).
                if _is_system_hwnd(fg2):
                    # B1 diagnostic: name the thief (class + owning process) so a
                    # persistent system-window hold is identifiable, not a bare hwnd.
                    self.log.warning(
                        "[focus] fg=0x%x is a system/desktop window (%s) — will not "
                        "WM_CLOSE it (triggers Shut Down dialog); escalating app reclaim",
                        fg2, _describe_hwnd(fg2),
                    )
                    # B2 escalation: a single _force_foreground can fail hundreds of
                    # times in a row against a sticky system window (447x / 16.5 min
                    # of controls=0 observed 2026-07-10). Retry harder on the APP side
                    # only — minimize/restore to knock the z-order, re-force foreground.
                    # Never send any message to the thief.
                    if self._escalate_app_reclaim(hwnd):
                        return True
                    self.log.warning(
                        "[focus] escalated reclaim failed against system window 0x%x "
                        "(stolen_count=%d) — skipping iteration", fg2, self.stats.focus_stolen,
                    )
                    return False
                dismissed = self._dismiss_native_window(fg2)
                if dismissed:
                    _force_foreground(hwnd)
                    time.sleep(0.2)
                    fg3 = _get_foreground_hwnd()
                    if fg3 == hwnd:
                        self.log.info(
                            "[focus] recovered after dismissing foreign window 0x%x "
                            "(stolen_count=%d)",
                            fg2, self.stats.focus_stolen,
                        )
                        return True
                self.log.warning(
                    "[focus] reclaim failed: fg=0x%x still not our hwnd=0x%x "
                    "(stolen_count=%d) — skipping iteration",
                    fg2, hwnd, self.stats.focus_stolen,
                )
                return False
            return True
        except Exception:
            return True  # non-fatal; proceed without blocking

    def _escalate_app_reclaim(self, hwnd: int, retries: int = 3) -> bool:
        """Bounded, app-side-only escalation to reclaim foreground from a sticky
        system/desktop window that a single _force_foreground() could not dislodge.

        Each attempt minimizes then restores OUR window (hwnd) to force the window
        manager to re-evaluate z-order — which usually knocks a stuck foreground
        holder off the top — then re-forces our window forward. This NEVER sends any
        message to the thief (WM_CLOSE to a Desktop/Shell window opens the Shut Down
        dialog), so it is safe against system windows. Returns True as soon as our
        window is foreground again, else False after *retries* attempts.
        """
        try:
            user32 = ctypes.windll.user32
        except Exception:
            return False  # non-fatal — ctypes unavailable; caller falls back to skip
        for attempt in range(1, retries + 1):
            try:
                user32.ShowWindow(hwnd, 6)   # SW_MINIMIZE — drop out of the z-order
                time.sleep(0.15)
                user32.ShowWindow(hwnd, 9)   # SW_RESTORE — pop back to the top
            except Exception:
                pass  # non-fatal — proceed to _force_foreground regardless
            _force_foreground(hwnd)
            time.sleep(0.25)
            if _get_foreground_hwnd() == hwnd:
                self.log.info(
                    "[focus] reclaimed foreground after escalation attempt %d/%d",
                    attempt, retries,
                )
                return True
        return False

    def _kill_stale_netsentinel(self) -> None:
        """Terminate any pre-existing NetSentinel processes before launching a new one.

        Prevents the new run from accidentally connecting to a stale instance that
        may be in a degraded state from a previous test run.
        """
        killed = 0
        terminated: list = []
        for proc in psutil.process_iter(["name", "cmdline", "pid"]):
            try:
                name    = (proc.info["name"] or "").lower()
                cmdline = " ".join(proc.info["cmdline"] or []).lower()
                if "netsentinel" in name or ("app.py" in cmdline and "netsentinel" in cmdline):
                    proc.terminate()
                    terminated.append(proc)
                    killed += 1
                    self.log.info("[setup] Killed stale process: %s (PID %d)",
                                  proc.info["name"], proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass  # non-fatal — process may have already exited
        if terminated:
            # White-frame/hang investigation (2026-07-19): terminate() only requests
            # death — TerminateProcess is asynchronous, so confirm the OS actually
            # finished tearing the process down (releasing its NetSentinel.db-shm
            # mapping) before the caller relaunches into the same DB/WAL file.
            # A fixed sleep() here previously just guessed at this instead of checking.
            t0 = time.time()
            gone, alive = psutil.wait_procs(terminated, timeout=5)
            for p in gone:
                self.log.info("[setup] stale PID %d confirmed exited (code=%s) after %.2fs",
                              p.pid, p.returncode, time.time() - t0)
            for p in alive:
                self.log.warning(
                    "[setup] stale PID %d STILL ALIVE %.2fs after terminate() — forcing kill()",
                    p.pid, time.time() - t0,
                )
                try:
                    p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # already gone, or no permission to force-kill — nothing more we can do

    # ── Launch & connect ──────────────────────────────────────────────────

    def _launch_exe(self) -> bool:
        self._kill_stale_netsentinel()
        path = self.cfg.exe_path
        self.log.info("Launching exe: %s", path)
        try:
            raw = subprocess.Popen([path])
            self._proc = psutil.Process(raw.pid)
            self.log.info("PID: %d", raw.pid)
            return True
        except (OSError, FileNotFoundError) as exc:
            self.log.error("Launch failed: %s", exc)
            return False

    def _launch_source(self) -> bool:
        self._kill_stale_netsentinel()
        repo = Path(__file__).parent.parent
        entry = repo / "app.py"
        self.log.info("Launching source: python %s", entry)
        try:
            env = None
            if self.cfg.tracemalloc:
                import os as _os
                env = _os.environ.copy()
                env["NETSENTINEL_TRACEMALLOC"] = "1"
                self.log.info("tracemalloc enabled — snapshots every 60s in app log")
            raw = subprocess.Popen([sys.executable, str(entry)], cwd=str(repo), env=env)
            self._proc = psutil.Process(raw.pid)
            self.log.info("PID: %d", raw.pid)
            return True
        except Exception as exc:
            self.log.error("Source launch failed: %s", exc)
            return False

    def _connect(self) -> bool:
        """
        Poll until the main NetSentinel window appears.
        Uses Desktop.windows() (non-blocking) rather than Application.connect()
        to guarantee the outer deadline is respected regardless of pywinauto version.

        When we launched the process (_proc is set), we match by PID so we never
        accidentally connect to VS Code whose title may contain "NetSentinel".
        Falls back to title-regex + process-exclusion filtering for --connect mode.
        """
        self.log.info("Waiting for window (up to %ds)...", _CONNECT_TIMEOUT)
        deadline = time.time() + _CONNECT_TIMEOUT
        target_pid: Optional[int] = self._proc.pid if self._proc else None

        while time.time() < deadline:
            try:
                all_wins = Desktop(backend="uia").windows()

                # Primary: PID-based match — unambiguous when we launched the process.
                if target_pid is not None:
                    pid_wins = [w for w in all_wins
                                if _is_netsentinel_window(w, target_pid)]
                    if pid_wins:
                        main = pid_wins[0]
                        self._win = main
                        title = ""
                        try:
                            title = main.window_text()
                        except Exception:
                            self.log.debug("window_text() unavailable")
                        self.log.info("Connected via PID %d: %r", target_pid, title)
                        return True

                # Fallback (--connect mode): title regex + process-name exclusion.
                title_wins = [w for w in all_wins
                              if _window_title_ok(w) and _is_netsentinel_window(w)]
                if title_wins:
                    main = title_wins[0]
                    try:
                        pid = main.element_info.process_id
                        self._proc = psutil.Process(pid)
                        self.log.info("PID: %d", pid)
                    except Exception as exc:
                        self.log.warning("Could not get PID from window: %s", exc)
                    self._win = main
                    title = ""
                    try:
                        title = main.window_text()
                    except Exception:
                        self.log.debug("window_text() unavailable")
                    self.log.info("Connected: %r", title)
                    return True
            except Exception:
                self.log.debug("UIA scan error; retrying")
            time.sleep(_CONNECT_POLL)

        self.log.error("Timed out waiting for window")
        return False

    def _attach(self) -> bool:
        """
        Connect to an already-running NetSentinel window without launching.
        Used with --connect flag when the developer has the app open.
        """
        self.log.info("Attaching to running NetSentinel window...")
        try:
            all_wins = Desktop(backend="uia").windows()
            # Title match + process-exclusion (blocks VS Code and other IDEs)
            wins = [w for w in all_wins
                    if _window_title_ok(w) and _is_netsentinel_window(w)]
            main = wins[0] if wins else None
            if not main:
                self.log.error("No NetSentinel main window found on desktop")
                return False
            try:
                pid = main.element_info.process_id
                self._proc = psutil.Process(pid)
                self.log.info("Attached to PID %d", pid)
            except Exception as exc:
                self.log.warning("Could not get PID from window: %s", exc)
            self._win = main
            title = ""
            try:
                title = main.window_text()
            except Exception:
                self.log.debug("window_text() unavailable")
            self.log.info("Attached: %r", title)
            return True
        except Exception as exc:
            self.log.error("Attach failed: %s", exc)
            return False

    def _dismiss_startup_overlays(self) -> None:
        """
        NetSentinel shows an onboarding overlay and/or first-run dialog.
        Try to dismiss them so the main UI is reachable.
        """
        self.log.info("Checking for startup overlays…")
        time.sleep(2.0)   # let splash and first-run animate in

        # Button labels that close overlays / first-run dialogs
        dismiss_labels = [
            "Get Started", "Close", "Skip", "No Thanks", "Later",
            "Continue", "OK",
        ]
        for label in dismiss_labels:
            try:
                btn = self._win.child_window(title=label, control_type="Button")
                if btn.exists(timeout=0.5):
                    btn.click_input()
                    time.sleep(0.4)
                    self.log.info("Dismissed overlay via %r", label)
                    break
            except Exception:
                continue

        # Also handle any blocking modal from Desktop level
        self._dismiss_blocking_dialogs()

    def _dismiss_blocking_dialogs(self) -> None:
        """Close modal error/confirmation windows and Windows system file dialogs."""
        # Cancel-button labels for Windows file pickers (English + Swedish locale)
        _FILE_DLG_CANCEL = ["Cancel", "Avbryt", "Annullera", "Close"]
        app_hwnd = 0
        try:
            app_hwnd = getattr(self._win, "handle", 0) or 0
        except Exception:
            pass  # non-fatal — fall back to title-based skip below
        try:
            for win in Desktop(backend="uia").windows():
                try:
                    title = (win.window_text() or "").lower()
                    cls   = (win.element_info.class_name or "")
                except Exception:
                    continue
                # Skip the main NetSentinel application window by hwnd (precise match).
                # The old check `"netsentinel" in title` also skipped file dialogs whose
                # title the app set to include its own name — those must NOT be skipped.
                try:
                    if app_hwnd and win.handle == app_hwnd:
                        continue
                except Exception:
                    pass  # non-fatal — proceed with content-based check
                # Skip windows with no identifying information at all
                if not title and not cls:
                    continue
                # Skip large windows that look like the main app (≥600×400 px)
                try:
                    if _is_main_window(win):
                        continue
                except Exception:
                    pass  # non-fatal

                # Skip windows owned by a protected IDE/terminal process (VS Code,
                # Cursor, Visual Studio) — reuses the guard _is_system_hwnd() already
                # applies elsewhere. Without this, a title keyword match below (e.g.
                # "crash", "error") can match an open editor tab and WM_CLOSE the IDE
                # itself, which kills this script's own host process tree.
                try:
                    win_handle = getattr(win, "handle", 0) or 0
                    if win_handle and _is_system_hwnd(win_handle):
                        continue
                except Exception:
                    pass  # non-fatal — fall through to keyword-based checks

                # Windows common file dialog (Open/Save As) — class #32770.
                # The monkey gets trapped inside these when Browse… buttons open them;
                # dismiss immediately so stale control references don't accumulate.
                is_file_dialog = cls == "#32770"

                # Windows shutdown/restart dialog — initiated by a blacklisted
                # button that slipped through.  Abort the pending shutdown first,
                # then dismiss the dialog so the test can continue.
                is_shutdown = any(kw in title for kw in [
                    "shut down", "shutting down", "restart", "restarting", "reboot",
                ])
                if is_shutdown:
                    self.log.error(
                        "[shutdown-abort] Windows restart/shutdown dialog detected: %r — "
                        "aborting shutdown via 'shutdown /a'", title
                    )
                    try:
                        subprocess.run(
                            ["shutdown", "/a"],
                            capture_output=True, timeout=5,
                        )
                        self.log.warning("[shutdown-abort] 'shutdown /a' succeeded")
                    except Exception as exc:
                        self.log.warning("[shutdown-abort] 'shutdown /a' failed: %s", exc)

                is_blocking = is_shutdown or any(kw in title for kw in [
                    "error", "exception", "unhandled", "crash",
                    "warning", "confirm", "are you sure",
                ])

                if not (is_file_dialog or is_blocking):
                    continue

                kind = ("shutdown dialog" if is_shutdown
                        else "file dialog" if is_file_dialog
                        else "blocking dialog")
                self.log.warning("Dismissing %s: %r (class=%r)", kind, title, cls)
                btn_names = (_FILE_DLG_CANCEL if is_file_dialog
                             else ["Cancel", "No", "Close", "OK", "Dismiss"])
                for btn_name in btn_names:
                    try:
                        win.child_window(title=btn_name, control_type="Button").click()
                        return
                    except Exception:
                        continue
                try:
                    dlg_hwnd = getattr(win, "handle", 0) or 0
                    if dlg_hwnd:
                        self._dismiss_native_window(dlg_hwnd)
                    else:
                        self.log.debug("no hwnd for %s — skipping WM_CLOSE", kind)
                except Exception:
                    self.log.debug("WM_CLOSE fallback failed for %s", kind)  # non-fatal — dialog may already be closed
        except Exception as exc:
            self.log.debug("Dialog scan: %s", exc)

    def _dismiss_native_window(self, dlg_hwnd: int) -> bool:
        """Try to close a foreign window (file dialog, modal) without needing it focused.

        Tries four escalating Win32 approaches in order:
        1. PostMessage WM_COMMAND/IDCANCEL  — cancels any standard Win32 dialog directly
        2. PostMessage BM_CLICK on IDCANCEL — clicks the Cancel child button by dialog ID 2
        3. PostMessage WM_KEYDOWN VK_ESCAPE — queues an Escape keystroke
        4. PostMessage WM_CLOSE             — asks the window to close itself

        All calls use PostMessage so this method never blocks waiting for a modal loop.
        Returns True if IsWindow() returns False after the attempt (window is gone).
        """
        user32 = ctypes.windll.user32
        try:
            # 1. WM_COMMAND IDCANCEL (0x0111, wParam=2) — closes most Win32 dialogs
            user32.PostMessageW(dlg_hwnd, 0x0111, 2, 0)
            time.sleep(0.25)
            if not user32.IsWindow(dlg_hwnd):
                self.log.debug("[dismiss] WM_COMMAND/IDCANCEL closed hwnd=0x%x", dlg_hwnd)
                return True
            # 2. BM_CLICK on the Cancel button child (IDCANCEL dialog-item ID = 2)
            cancel_hwnd = user32.GetDlgItem(dlg_hwnd, 2)
            if cancel_hwnd:
                user32.PostMessageW(cancel_hwnd, 0x00F5, 0, 0)  # BM_CLICK
                time.sleep(0.2)
                if not user32.IsWindow(dlg_hwnd):
                    self.log.debug("[dismiss] BM_CLICK/Cancel closed hwnd=0x%x", dlg_hwnd)
                    return True
            # 3. VK_ESCAPE via PostMessage (0x0100 WM_KEYDOWN, 0x1B VK_ESCAPE)
            user32.PostMessageW(dlg_hwnd, 0x0100, 0x1B, 0x00010001)
            user32.PostMessageW(dlg_hwnd, 0x0101, 0x1B, 0xC0010001)
            time.sleep(0.25)
            if not user32.IsWindow(dlg_hwnd):
                self.log.debug("[dismiss] VK_ESCAPE closed hwnd=0x%x", dlg_hwnd)
                return True
            # 4. WM_CLOSE (0x0010) — last resort
            user32.PostMessageW(dlg_hwnd, 0x0010, 0, 0)
            time.sleep(0.25)
            closed = not user32.IsWindow(dlg_hwnd)
            if closed:
                self.log.debug("[dismiss] WM_CLOSE closed hwnd=0x%x", dlg_hwnd)
            else:
                self.log.warning("[dismiss] all methods failed for hwnd=0x%x", dlg_hwnd)
            return closed
        except Exception as exc:
            self.log.debug("[dismiss] error on hwnd=0x%x: %s", dlg_hwnd, exc)
            return False  # non-fatal — caller decides how to proceed

    def _post_click_dialog_guard(self) -> None:
        """Called immediately after every Button click to catch native dialogs before they strand the run.

        Native file open/save dialogs steal foreground the instant they open.  Detecting
        them here — within 150 ms of the triggering click — lets us dismiss them via
        _dismiss_native_window() before the next iteration's _assert_focus() check runs,
        keeping the skip count at zero rather than losing the entire remainder of the run.
        """
        time.sleep(0.15)   # let the dialog open and claim foreground
        try:
            hwnd = getattr(self._win, "handle", 0) or 0
            if not hwnd:
                return
            fg = _get_foreground_hwnd()
            if fg == hwnd:
                return  # no dialog appeared — common case, fast path
            # Root guard: never call _dismiss_native_window() on the Windows Desktop,
            # Shell, or Taskbar.  GetForegroundWindow() can transiently return the
            # Desktop HWND during a dialog-open transition (even with DontUseNativeDialog).
            # Sending WM_CLOSE to the Desktop shell triggers the Shut Down Windows dialog.
            if _is_system_hwnd(fg):
                self.log.warning(
                    "[dialog-guard] fg=0x%x is a system/desktop window — skipping dismiss "
                    "(WM_CLOSE to Desktop triggers Shut Down dialog)", fg,
                )
                return
            self.log.info(
                "[dialog-guard] post-click focus stolen by 0x%x — attempting dismiss", fg
            )
            self.stats.focus_stolen += 1
            dismissed = self._dismiss_native_window(fg)
            if dismissed:
                _force_foreground(hwnd)
                time.sleep(0.2)
                if _get_foreground_hwnd() == hwnd:
                    self.log.info("[dialog-guard] focus recovered after dialog dismiss")
            else:
                self.log.warning(
                    "[dialog-guard] could not dismiss 0x%x — next _assert_focus() will retry",
                    fg,
                )
        except Exception:
            pass  # non-fatal — _assert_focus() is the safety net

    # ── Health monitoring (background thread) ─────────────────────────────

    def _health_monitor(self) -> None:
        """
        Background thread: checks process liveness, memory, and hang detection.
        Sets self._stop on any serious problem.
        """
        while not self._stop.is_set():
            self._stop.wait(_HEALTH_INTERVAL)
            if self._stop.is_set():
                return  # signalled to stop during wait (restart or shutdown)

            # Process alive?
            if not self._alive():
                self.log.error("[health] Process died")
                self._stop.set()
                return

            # Memory leak guard
            try:
                rss = self._proc.memory_info().rss / (1024 * 1024)
                if rss > self.stats.peak_rss_mb:
                    self.stats.peak_rss_mb = rss
                if rss > self.cfg.mem_limit_mb:
                    self.log.warning("[health] RSS %.0f MB exceeds limit %d MB",
                                     rss, self.cfg.mem_limit_mb)
            except psutil.NoSuchProcess:
                self._stop.set()
                return

            # Hang detection — main loop must complete an iteration every N seconds
            idle = time.time() - self._last_iter_time
            if idle > _UNRESPONSIVE_SECS:
                self.log.error("[health] No iteration for %.0fs — app may be hung", idle)
                self._stop.set()
                return

            # Native-fault detection — see _check_crash_log()
            if self._check_crash_log():
                self._stop.set()
                return

    def _check_crash_log(self) -> bool:
        """True if the app wrote a NEW entry to netsentinel_crash.log during this run.

        Windows fatal exceptions (e.g. 0x8001010d RPC_E_CANTCALLOUT_ININPUTSYNCCALL,
        the Snap-Layout/COM reentrancy fault) are native SEH faults.  No Python
        try/except can catch them and they never reach netsentinel_exceptions.log --
        app.py's faulthandler.enable() writing to netsentinel_crash.log is the ONLY
        thing that records them.  A fault does not necessarily kill the process, so
        neither _alive() nor the hang check will notice: without this watcher the run
        goes green while the app is faulting.

        The log is append-only and never rotated, so a plain grep/line-count finds
        weeks of unrelated history.  Compare against the size captured at run start.
        """
        if self._crash_log is None:
            return False
        try:
            size = self._crash_log.stat().st_size
        except OSError:
            return False  # not created yet -> nothing has faulted
        if size <= self._crash_log_size0:
            return False
        try:
            with open(self._crash_log, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._crash_log_size0)
                new = f.read()
        except OSError:
            new = "(could not read new crash-log content)"
        self.log.error("[health] NEW crash-log entry — app hit a native fault:\n%s",
                       new.strip()[:2000])
        self._crash_log_size0 = size
        self._crash_report("native fault written to netsentinel_crash.log")
        return True

    def _alive(self) -> bool:
        # When attached without a process handle, fall back to window check only
        if self._proc is None:
            return self._window_ok()
        try:
            if self._proc.is_running() and self._proc.status() != psutil.STATUS_ZOMBIE:
                return True
        except psutil.NoSuchProcess:
            pass
        # Process is gone — capture its exit code once, best-effort, so a crash
        # report says HOW it died (Python exception, native fault code, or a
        # clean 0) instead of just that it did. wait(timeout=0) is non-blocking
        # here since is_running() already returned False above.
        try:
            self._last_exit_code = self._proc.wait(timeout=0)
            self.log.warning("[health] process PID %d is gone — exit code %s",
                              self._proc.pid, self._last_exit_code)
        except Exception:
            self.log.debug("[health] process gone — exit code unavailable")
        return False

    def _window_ok(self, retries: int = 6) -> bool:
        """
        Returns True if the main NetSentinel window is accessible on the desktop.

        PyQt6 windows can briefly disappear from the UIA tree during overlay
        animations or startup sequences without the process dying.  After each
        failed check we do a fresh Desktop scan to pick up a new/re-created
        window handle before giving up.

        Uses PID-based matching when available so that a transient window loss
        never causes self._win to be reassigned to VS Code or another window
        whose title happens to contain "NetSentinel".
        """
        target_pid: Optional[int] = self._proc.pid if self._proc else None
        for i in range(retries):
            # Fast path: cached reference — verify it's still OUR main window
            try:
                if (self._win is not None and self._win.exists()
                        and _is_netsentinel_window(self._win, target_pid)):
                    return True
            except Exception:
                self.log.debug("cached window reference stale")
            # Slow path: re-scan Desktop using PID when available
            try:
                all_wins = Desktop(backend="uia").windows()
                if target_pid is not None:
                    main = next(
                        (w for w in all_wins if _is_netsentinel_window(w, target_pid)),
                        None,
                    )
                else:
                    main = next(
                        (w for w in all_wins
                         if _window_title_ok(w) and _is_netsentinel_window(w)),
                        None,
                    )
                if main:
                    self._win = main
                    return True
            except Exception:
                self.log.debug("UIA desktop scan failed")
            if i < retries - 1:
                time.sleep(0.5)
        return False

    # ── App restart ───────────────────────────────────────────────────────

    def _restart_app(self) -> bool:
        """Kill the current app and relaunch it after an unexpected exit.

        Called when the main window disappears (e.g. the close button slipped
        past the spatial/blacklist filter).  Returns True if relaunch succeeded.
        """
        self.stats.restarts += 1
        self.log.info(
            "[restart] App exited unexpectedly — relaunch attempt %d/%d",
            self.stats.restarts, self.cfg.max_restarts,
        )
        # Signal old background threads to exit; threads using _stop.wait() respond immediately.
        self._stop.set()
        time.sleep(0.3)   # allow focus heartbeat (uses _stop.wait) to notice and exit

        self._kill_stale_netsentinel()
        self._proc = None
        self._win = None

        # Clear stop so new threads can run
        self._stop.clear()

        # Relaunch the app
        ok = self._launch_source() if self.cfg.use_source else self._launch_exe()
        if not ok:
            self.log.error("[restart] Relaunch failed — giving up")
            return False
        if not self._connect():
            self.log.error("[restart] Could not reconnect after restart — giving up")
            return False

        # Start fresh monitoring threads (old ones exited on _stop.set() above)
        _ht = threading.Thread(
            target=self._health_monitor, daemon=True,
            name=f"health_r{self.stats.restarts}",
        )
        _ht.start()
        _ft = threading.Thread(
            target=self._focus_heartbeat, daemon=True,
            name=f"focus_r{self.stats.restarts}",
        )
        _ft.start()

        self._dismiss_startup_overlays()
        time.sleep(2.0)   # additional settle time after restart overlays clear
        try:
            hwnd = self._win.handle
            _force_foreground(hwnd)
            self.log.info("[restart] Foreground claimed (hwnd=0x%x)", hwnd)
        except Exception:
            pass  # non-fatal — main loop will assert focus on next iteration
        self._last_iter_time = time.time()
        self.log.info(
            "[restart] App relaunched — continuing from iteration %d",
            self.stats.completed + 1,
        )
        return True

    # ── Iteration ─────────────────────────────────────────────────────────

    def _get_controls(self) -> List:
        """Return enabled, visible descendants that are not blacklisted.

        pywinauto's UIA backend does NOT accept enabled_only/visible_only
        kwargs to descendants() — they raise TypeError. Filter manually.
        """
        try:
            all_ctrl = self._win.descendants()
        except Exception as exc:
            self.log.debug("descendants() failed: %s", exc)
            return []

        # Get window rectangle for spatial filters
        try:
            win_rect = self._win.rectangle()
        except Exception:
            win_rect = None

        result = []
        for ctrl in all_ctrl:
            try:
                ctype = _safe_type(ctrl)

                if ctype not in _SUPPORTED_TYPES:
                    continue
                # Manual enabled / visible check (UIA backend ignores kwargs)
                try:
                    if not ctrl.is_enabled():
                        continue
                except Exception:
                    self.log.debug("is_enabled() failed")
                try:
                    if not ctrl.is_visible():
                        continue
                except Exception:
                    self.log.debug("is_visible() failed")
                name = _safe_name(ctrl)
                auto_id = _safe_id(ctrl)
                if _is_blacklisted(name, auto_id):
                    self.stats.blacklisted += 1
                    continue
                # Bounds guard: control must be inside (or very close to) the
                # main window rect.  This prevents clicking on NetSentinel toast
                # notifications or any window that accidentally became self._win.
                if win_rect is not None:
                    try:
                        cr = ctrl.rectangle()
                        margin = 50  # allow slight overhang for drop-downs
                        if (cr.right  < win_rect.left   - margin or
                                cr.left   > win_rect.right  + margin or
                                cr.bottom < win_rect.top    - margin or
                                cr.top    > win_rect.bottom + margin):
                            self.stats.blacklisted += 1
                            continue
                    except Exception:
                        self.log.debug("rectangle() failed; skipping bounds check")
                # Spatial filter for the header strip.
                #
                # This used to exclude EVERY Button in the top 60px, which hid the
                # whole header -- window chrome, the settings gear, and the Scan
                # button -- from every chaos run.  That is why a broken maximize
                # button (it called showFullScreen(), covering the taskbar) shipped
                # unnoticed: not one iteration ever clicked it.
                #
                # Close and minimize are blacklisted by glyph above (close kills the
                # app under test; minimize hides it from UIA).  Everything else in
                # the header is safe and reversible, so it is now exercised.  The
                # only remaining guard is positional, and only for a chrome button
                # UIA failed to give a name to: the three _ChromeButtons are 46px
                # wide and flush right, so measuring from the window's right edge,
                #   close ~0px | maximize ~46px (ALLOWED) | minimize ~92px
                if (win_rect is not None and ctype in ("Button", "SplitButton")
                        and not name.strip()):
                    try:
                        cr = ctrl.rectangle()
                        if cr.top - win_rect.top < 60:
                            dist_from_right = win_rect.right - cr.right
                            if dist_from_right < 23 or 70 <= dist_from_right < 115:
                                self.stats.blacklisted += 1
                                continue
                    except Exception:
                        self.log.debug("title-bar check failed")
                # mild chaos: skip Edit boxes to avoid corrupting settings
                if self.cfg.chaos == "mild" and ctype == "Edit":
                    continue
                result.append(ctrl)
            except Exception:
                continue
        return result

    def _do_nav(self, n: int) -> Action:
        pool = _nav_pool(self.cfg.chaos)
        fn = random.choice(pool)
        ts = datetime.now().strftime("%H:%M:%S")
        try:
            action_str = fn(self._win, self.cfg.chaos)
            result = "ok"
        except Exception as exc:
            action_str = fn.__name__
            result = f"err:{exc.__class__.__name__}"
            self.stats.exceptions += 1
        return Action(n=n, ts=ts, ctype="Navigation", name="<win>",
                      auto_id="", action=action_str, result=result)

    def _do_control(self, n: int, ctrl) -> Action:
        ts = datetime.now().strftime("%H:%M:%S")
        name = _safe_name(ctrl)
        auto_id = _safe_id(ctrl)
        ctype = _safe_type(ctrl)
        fn = _DISPATCHER.get(ctype, _act_fallback)

        try:
            action_str = fn(ctrl, self.cfg.chaos)
            result = "ok"
            self.stats.record(ctype, action_str)
            # Immediately after any button click, check whether a native file dialog
            # opened and took focus.  Catching it here prevents cascading skip storms.
            if ctype in ("Button", "SplitButton"):
                self._post_click_dialog_guard()
        except (ElementNotEnabled, ElementNotVisible) as exc:
            action_str = "skip_state"
            result = f"skipped:{exc.__class__.__name__}"
            self.stats.skipped += 1
        except ElementNotFoundError:
            action_str = "skip_gone"
            result = "skipped:ElementNotFound"
            self.stats.skipped += 1
        except Exception as exc:
            action_str = "exception"
            result = f"err:{exc.__class__.__name__}:{str(exc)[:60]}"
            self.stats.exceptions += 1
            self.log.debug("Ctrl error  %r (%s): %s", name, ctype, exc)

        return Action(n=n, ts=ts, ctype=ctype, name=name,
                      auto_id=auto_id, action=action_str, result=result)

    def _run_one(self, n: int) -> bool:
        """
        Execute a single monkey iteration.
        Returns False if a hard failure is detected (crash / window gone).
        """
        # CPU cooldown before interacting
        if self._proc:
            _wait_cpu(self._proc, self.cfg.cpu_threshold, self.cfg.cpu_wait_max)

        # Jitter sleep — wild mode is faster / more abusive
        sleep = random.uniform(
            *{"mild": (0.6, 2.0), "wild": (0.05, 0.6)}.get(self.cfg.chaos, (0.3, 1.5))
        )
        time.sleep(sleep)

        # Liveness checks
        if not self._alive():
            self.log.error("Process died before iteration %d", n)
            return False
        if not self._window_ok():
            self.log.error("Window gone before iteration %d", n)
            return False

        # Dismiss any unexpected modal that appeared since last iteration
        self._dismiss_blocking_dialogs()

        # Verify NetSentinel is the foreground window before touching any control.
        # _assert_focus() reclaims focus when stolen and skips the iteration if
        # reclaim fails — this prevents clicking controls in another app window.
        if not self._assert_focus():
            self.log.warning("[focus] skipping iteration %d (could not reclaim foreground)", n)
            self.stats.skipped += 1
            self.stats.completed += 1
            self._last_iter_time = time.time()
            return True
        time.sleep(0.08)

        # Choose: navigation action or random control
        if random.random() < self.cfg.nav_prob:
            rec = self._do_nav(n)
        else:
            controls = self._get_controls()
            if not controls:
                self.log.debug("No safe controls on iteration %d — skipping", n)
                self.stats.skipped += 1
                self.stats.completed += 1
                self._last_iter_time = time.time()
                return True
            rec = self._do_control(n, random.choice(controls))

        self.hist.add(rec)
        self.log.debug(
            "[%4d] %-14s  %-24s  name=%-30r  %s",
            n, rec.ctype, rec.action, rec.name, rec.result,
        )
        self.stats.completed += 1
        self._last_iter_time = time.time()
        return True

    # ── Crash reporting ───────────────────────────────────────────────────

    def _crash_report(self, reason: str) -> None:
        self.stats.crashes += 1
        sep = "=" * 70
        self.log.error(sep)
        self.log.error("MONKEY TEST FAILURE")
        self.log.error("Reason   : %s", reason)
        if self.cfg.duration_secs:
            self.log.error("Iteration: %d (%.0fs / %.0fs)",
                            self.stats.completed, self.stats.elapsed, self.cfg.duration_secs)
        else:
            self.log.error("Iteration: %d / %d", self.stats.completed, self.cfg.iterations)
        self.log.error("Elapsed  : %.0fs", self.stats.elapsed)
        self.log.error(self.hist.fmt())
        self.log.error(sep)

        if self.cfg.screenshots:
            _screenshot("crash", self.log, self.cfg.output_dir)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report = {
            "reason": reason,
            "iteration": self.stats.completed,
            "last_exit_code": self._last_exit_code,
            "stats": self.stats.to_dict(),
            "last_actions": self.hist.dump(),
        }
        rpath = str(Path(self.cfg.output_dir) / f"monkey_crash_{ts}.json")
        try:
            with open(rpath, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            self.log.info("Crash report: %s", rpath)
        except Exception:
            self.log.debug("could not write crash report")

    # ── Main run ──────────────────────────────────────────────────────────

    def run(self) -> int:
        self.log.info("NetSentinel Monkey Tester v%s", _VERSION)
        if self.cfg.duration_secs:
            self.log.info("chaos=%s  duration=%.0fs  seed=%s  mem_limit=%dMB",
                          self.cfg.chaos, self.cfg.duration_secs, self.cfg.seed,
                          self.cfg.mem_limit_mb)
        else:
            self.log.info("chaos=%s  iterations=%d  seed=%s  mem_limit=%dMB",
                          self.cfg.chaos, self.cfg.iterations, self.cfg.seed,
                          self.cfg.mem_limit_mb)

        # Launch or attach
        if self.cfg.connect_only:
            if not self._attach():
                return 2
        else:
            ok = self._launch_source() if self.cfg.use_source else self._launch_exe()
            if not ok:
                return 2
            if not self._connect():
                return 2

        # Dismiss any startup overlays / onboarding dialogs.
        # Safe to call in --connect mode too: it checks for overlay buttons
        # and silently moves on if none are present.
        self._dismiss_startup_overlays()
        time.sleep(self.cfg.warmup_secs)   # let animations settle before first interaction

        # Claim foreground explicitly before starting chaos — without this,
        # the terminal that launched us (e.g. VS Code) retains focus and the
        # first iteration's _assert_focus() immediately triggers a reclaim cycle.
        try:
            hwnd = self._win.handle
            _force_foreground(hwnd)
            self.log.info("[startup] Foreground claimed (hwnd=0x%x)", hwnd)
        except Exception as exc:
            self.log.warning("[startup] Could not claim foreground: %s", exc)

        # Suppress sleep and start background threads
        if self.cfg.prevent_sleep:
            _prevent_sleep_begin(self.log)
        hthread = threading.Thread(target=self._health_monitor, daemon=True, name="health")
        hthread.start()
        fthread = threading.Thread(target=self._focus_heartbeat, daemon=True, name="focus")
        fthread.start()

        if self.cfg.duration_secs:
            self.log.info("Running for %.0fs (wall-clock)…", self.cfg.duration_secs)
            loop_limit = sys.maxsize
        else:
            self.log.info("Starting %d iterations…", self.cfg.iterations)
            loop_limit = self.cfg.iterations
        crashed = False
        self._last_iter_time = time.time()

        for i in range(1, loop_limit + 1):
            # Wall-clock duration limit reached — stop cleanly, same as running out of iterations.
            if self.cfg.duration_secs and self.stats.elapsed >= self.cfg.duration_secs:
                self.log.info(
                    "Duration limit reached (%.0fs elapsed) after %d iterations",
                    self.stats.elapsed, self.stats.completed,
                )
                break

            # Health monitor signalled a problem — try auto-restart before giving up
            if self._stop.is_set():
                if self.stats.restarts < self.cfg.max_restarts:
                    self.log.warning(
                        "[restart] Health monitor triggered at iter %d — "
                        "restarting app (attempt %d/%d)",
                        i, self.stats.restarts + 1, self.cfg.max_restarts,
                    )
                    if self._restart_app():
                        continue
                self._crash_report("health monitor triggered")
                crashed = True
                break

            # Progress update every 25 iterations
            if i % 25 == 0:
                rss = 0.0
                try:
                    rss = self._proc.memory_info().rss / (1024 * 1024)
                except Exception:
                    self.log.debug("memory_info() unavailable")
                if self.cfg.duration_secs:
                    self.log.info(
                        "Progress iter=%d  elapsed=%.0fs/%.0fs  controls=%d  exceptions=%d  rss=%.0fMB",
                        i, self.stats.elapsed, self.cfg.duration_secs,
                        sum(self.stats.by_type.values()),
                        self.stats.exceptions,
                        rss,
                    )
                else:
                    self.log.info(
                        "Progress %d/%d  controls=%d  exceptions=%d  rss=%.0fMB  elapsed=%.0fs",
                        i, self.cfg.iterations,
                        sum(self.stats.by_type.values()),
                        self.stats.exceptions,
                        rss,
                        self.stats.elapsed,
                    )

            try:
                ok = self._run_one(i)
            except KeyboardInterrupt:
                self.log.info("Interrupted at iteration %d", i)
                break
            except Exception as exc:
                self.log.warning("Unexpected top-level error at iteration %d: %s", i, exc)
                self.stats.exceptions += 1
                ok = self._alive() and self._window_ok()

            if not ok:
                if self.stats.restarts < self.cfg.max_restarts:
                    self.log.warning(
                        "[restart] Window/process gone at iter %d — "
                        "restarting app (attempt %d/%d)",
                        i, self.stats.restarts + 1, self.cfg.max_restarts,
                    )
                    if self._restart_app():
                        continue
                self._crash_report(f"iteration {i}")
                crashed = True
                break

        self._stop.set()
        if self.cfg.prevent_sleep:
            _prevent_sleep_end(self.log)

        # Final summary
        self.log.info("=" * 70)
        self.log.info("MONKEY TEST %s", "FAILED" if crashed else "PASSED")
        for k, v in self.stats.to_dict().items():
            self.log.info("  %-30s %s", k, v)
        self.log.info("=" * 70)

        summary_path = str(Path(self.cfg.output_dir) / "monkey_summary.json")
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(self.stats.to_dict(), f, indent=2)
            self.log.info("Summary JSON: %s", summary_path)
        except Exception:
            self.log.debug("could not write summary JSON")

        # Real-quit phase — skip when in --connect mode (we didn't own the app)
        if not self.cfg.connect_only:
            if self._real_quit_phase():
                crashed = True
                self.log.error("=" * 70)
                self.log.error("MONKEY TEST FAILED — real-quit phase")
                self.log.error("=" * 70)

        return 1 if crashed else 0

    # ── Real-quit phase ────────────────────────────────────────────────────────

    #: Bound on the real shutdown path. Dashboard.closeEvent() drains every worker
    #: against a single 3 s deadline (ui/shutdown.py), so a close that has not
    #: finished well inside this is a hang, not slowness.
    QUIT_DEADLINE_S = 25.0

    def _real_quit_phase(self) -> bool:
        """Drive the REAL quit path and verify the app exits cleanly.

        Returns True on FAILURE (matching this file's `crashed` convention).

        Why this phase exists: every chaos run used to end with `self._win.close()`
        — a native WM_CLOSE, which Dashboard.closeEvent() answers by hiding to the
        tray whenever tray/minimize_to_tray is enabled (it defaults to True). The
        harness then fell through to psutil terminate(). So the shutdown path that
        real users take — titlebar X -> _quit_app -> _tray_quit=True -> the full
        worker drain and hard exit — had NEVER been exercised by automation, in
        any run, which is exactly how a shutdown crash reached the Store.

        Clicking the titlebar X is what makes this faithful: _quit_app bypasses the
        tray branch entirely, so this works without mutating the user's settings.
        The X is in _BLACKLIST for random clicking (RULE-CHAOS2: it ends the run by
        design) — clicking it deliberately, last, is the whole point of this phase.

        Fails on any of: the process not exiting within QUIT_DEADLINE_S (hang), a
        non-zero exit code, or ANY crash-log byte growth (RULE-CHAOS2 — a native
        SEH fault does not kill the process, so the crash log is the only witness).
        """
        if not self._alive():
            self.log.error("[quit] app was already dead before the real-quit phase")
            return True

        self.log.info("=" * 70)
        self.log.info("[quit] real-quit phase: clicking titlebar X (_quit_app path)")

        try:
            self._win.set_focus()
        except Exception:
            pass  # non-fatal — click_input below works on an unfocused window too

        # The three _ChromeButtons are 46px wide, flush right: close ~23px in from
        # the right edge (same geometry _chrome_hover_maximize relies on).
        # coords= is relative to the window rectangle, as at the other
        # click_input(coords=...) call site in this file.
        try:
            r = self._win.rectangle()
            rel_x, rel_y = int(r.width() - 23), 21
            self._win.click_input(coords=(rel_x, rel_y))
            self.log.info("[quit] clicked close button at window-relative (%d, %d)",
                          rel_x, rel_y)
        except Exception as exc:
            self.log.error("[quit] could not click the close button: %s", exc)
            return True

        t0 = time.time()
        while time.time() - t0 < self.QUIT_DEADLINE_S:
            if not self._alive():
                break
            time.sleep(0.25)
        elapsed = time.time() - t0

        failed = False
        if self._alive():
            self.log.error(
                "[quit] app STILL RUNNING %.1fs after close — shutdown hang. "
                "Read netsentinel_shutdown.log for the per-worker drain timings.",
                elapsed,
            )
            self._crash_report(f"shutdown hang: still alive {elapsed:.1f}s after close")
            failed = True
            try:
                self._proc.terminate()
            except Exception:
                self.log.debug("process terminate failed")
        else:
            self.log.info("[quit] app exited %.2fs after close", elapsed)

        # A native fault during teardown does not necessarily kill the process and
        # never reaches netsentinel_exceptions.log — crash-log growth is the only
        # record, so it must be checked even on a clean-looking exit.
        if self._check_crash_log():
            self.log.error("[quit] crash log grew during shutdown — native fault on the quit path")
            failed = True

        if not failed:
            self.log.info("[quit] real-quit phase PASSED (clean exit, no crash-log growth)")
        self.log.info("=" * 70)
        return failed


# ── CLI ────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Monkey / chaos tester for NetSentinel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("exe_path", nargs="?",
                   help="Path to NetSentinel.exe (omit when using --source or --connect)")
    p.add_argument("--source", action="store_true",
                   help="Launch via 'python app.py' from repo root")
    p.add_argument("--connect", action="store_true",
                   help="Attach to an already-running NetSentinel window (do not launch)")
    p.add_argument("-n", "--iterations", type=int, default=200)
    p.add_argument("--duration", type=float, default=None, metavar="SECS",
                   help="Run by wall-clock time instead of a fixed iteration count "
                        "(overrides -n/--iterations when both are given)")
    p.add_argument("--chaos", choices=["mild", "moderate", "wild"], default="moderate")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--no-screenshots", action="store_true")
    p.add_argument("--mem-limit", type=int, default=800, metavar="MB")
    p.add_argument("--log", default="",
                   help="Log file path (default: <output-dir>/monkey.log)")
    p.add_argument("--output-dir", default="test_output",
                   help="Directory for all generated output files (default: test_output)")
    p.add_argument("--focus-interval", type=float, default=1.5, metavar="SECS",
                   help="Seconds between focus-heartbeat pulses (default 1.5)")
    p.add_argument("--no-prevent-sleep", action="store_true",
                   help="Do not suppress Windows sleep/screensaver")
    p.add_argument("--tracemalloc", action="store_true",
                   help="Enable tracemalloc profiling inside the app (sets NETSENTINEL_TRACEMALLOC=1; "
                        "requires --source; writes top-20 allocation snapshots to the app's debug log "
                        "every 60 s so you can identify the retained object type)")
    p.add_argument("--max-restarts", type=int, default=3, metavar="N",
                   help="Max auto-restarts when the app window vanishes unexpectedly (default 3; 0 = disabled)")
    p.add_argument("--warmup-secs", type=float, default=5.0, metavar="SECS",
                   help="Seconds to wait after overlay dismissal before the first click (default 5)")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if not args.source and not args.connect and not args.exe_path:
        print("ERROR: provide an exe path, --source, or --connect", file=sys.stderr)
        sys.exit(2)

    if args.exe_path and not Path(args.exe_path).exists():
        print(f"ERROR: exe not found: {args.exe_path}", file=sys.stderr)
        sys.exit(2)

    if args.tracemalloc and not args.source:
        print("WARNING: --tracemalloc only works with --source (ignored for exe/connect mode)",
              file=sys.stderr)

    cfg = Config(
        exe_path=args.exe_path,
        use_source=args.source,
        connect_only=args.connect,
        iterations=args.iterations,
        duration_secs=args.duration,
        chaos=args.chaos,
        seed=args.seed,
        screenshots=not args.no_screenshots,
        mem_limit_mb=args.mem_limit,
        output_dir=args.output_dir,
        log_file=args.log,
        focus_interval=args.focus_interval,
        prevent_sleep=not args.no_prevent_sleep,
        tracemalloc=args.tracemalloc and args.source,
        max_restarts=args.max_restarts,
        warmup_secs=args.warmup_secs,
    )

    sys.exit(MonkeyTester(cfg).run())


if __name__ == "__main__":
    main()
