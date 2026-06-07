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
    --chaos LEVEL         mild | moderate | wild (default: moderate)
    --seed N              RNG seed for reproducibility
    --no-screenshots      Skip PIL screenshots on crash
    --mem-limit MB        RSS limit before leak warning (default: 800)
    --log FILE            Log file path (default: netsentinel_monkey.log)

Requirements:
    pip install pywinauto psutil Pillow

Exit codes:
    0  All iterations completed, no crash
    1  App crashed or became unresponsive during testing
    2  Could not launch or connect to app
"""

import argparse
import collections
import dataclasses
import json
import logging
import os
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
    import pywinauto
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

_VERSION = "1.2.0"
_WINDOW_RE = ".*NetSentinel.*"
_CONNECT_TIMEOUT = 60       # seconds to wait for the window after launch
_CONNECT_POLL = 2.0         # seconds between connection attempts
_HEALTH_INTERVAL = 2.0      # seconds between background health checks
_UNRESPONSIVE_SECS = 20     # seconds without a completed iteration before hang alarm

# UIA control types the dispatcher knows how to handle
_SUPPORTED_TYPES = frozenset({
    "Button", "Edit", "ComboBox", "CheckBox", "RadioButton",
    "ListItem", "TabItem", "Slider", "TreeItem", "Hyperlink",
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
    # --- Window chrome (frameless titlebar close/min/max buttons) ---
    # These are Segoe MDL2 glyphs used in NetSentinel's custom header.
    # The actual text is a private-use Unicode code point, not a word.
    "",   # Cancel / Close  (AppHeaderMixin close button)
    "",   # Close (alternate)
    "",   # Cancel (alternate)
    "",   # Maximize
    "",   # Restore Down
    "",   # Minimize  -- safe to skip clicks here too
    # Catch-all for any _ChromeButton by auto_id (close/min/max that
    # slipped past the 38px spatial filter — confirmed crash cause from seed=99).
    "_chromebutton",   # matches auto_id: QApplication.Dashboard.QWidget.appBar._ChromeButton
    # --- App lifecycle ---
    "quit",
    "exit application",
    # --- Export / file creation (clutters disk) ---
    "export pdf",
    "save pdf",
    "export csv",
    "save report",
    # --- Credential / auth dialogs that block automation ---
    "sign in",
    "authenticate",
    # --- Dangerous config actions ---
    "factory reset",
    "restore defaults",
]

# Safe pages to navigate to via the Ctrl+K command palette.
# Only read-only / lightweight pages are listed.
_SAFE_PAGES: List[str] = [
    "Overview", "Home", "History", "Help", "Feature Guide",
    "Timeline", "Trends", "IP Calculator", "Network Doc",
    "Log Hub", "Geo Map", "Protocol Viz", "Lab Mode",
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
    chaos: str = "moderate"          # mild | moderate | wild
    seed: Optional[int] = None
    screenshots: bool = True
    mem_limit_mb: int = 800
    output_dir: str = "test_output"  # all generated files written here
    log_file: str = ""               # empty = auto-derive from output_dir
    cpu_threshold: float = 35.0      # % CPU — wait below this before acting
    cpu_wait_max: float = 12.0       # max seconds to wait for CPU to settle
    nav_prob: float = 0.15           # probability of a navigation action per iteration
    history_size: int = 15

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


def _is_blacklisted(name: str, auto_id: str) -> bool:
    combined = (name + " " + auto_id).lower()
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


# ── Control interaction dispatcher ────────────────────────────────────────────

def _act_button(ctrl, chaos: str) -> str:
    ctrl.click_input()
    return "click"


def _act_edit(ctrl, chaos: str) -> str:
    text = _realistic_text(chaos)
    try:
        ctrl.set_focus()
        # select-all then overwrite, rather than appending
        ctrl.type_keys("^a", pause=0.05)
    except Exception:
        pass
    ctrl.type_keys(text, with_spaces=True, pause=0.02)
    return f"type:{text!r}"


def _act_combobox(ctrl, chaos: str) -> str:
    try:
        count = ctrl.item_count()
        if count and count > 0:
            idx = random.randint(0, min(count - 1, 6))
            ctrl.select(idx)
            return f"select:{idx}"
    except Exception:
        pass
    ctrl.click_input()
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


def _act_hyperlink(ctrl, chaos: str) -> str:
    # Never follow external links — just verify focusability
    try:
        ctrl.set_focus()
        return "focus"
    except Exception:
        return "skip_hyperlink"


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
    "Hyperlink":    _act_hyperlink,
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
            pass
        return f"palette_err:{exc.__class__.__name__}"


def _nav_escape(win, chaos: str) -> str:
    """Dismiss any overlay / flyout that may have opened."""
    win.type_keys("{ESC}")
    time.sleep(0.2)
    return "esc"


_NAV_MILD = [_nav_shortcut, _nav_escape]
_NAV_MODERATE = [_nav_shortcut, _nav_command_palette, _nav_escape]
_NAV_WILD = [_nav_shortcut, _nav_command_palette, _nav_escape, _nav_escape, _nav_command_palette]


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

    # ── Launch & connect ──────────────────────────────────────────────────

    def _launch_exe(self) -> bool:
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
        repo = Path(__file__).parent.parent
        entry = repo / "app.py"
        self.log.info("Launching source: python %s", entry)
        try:
            raw = subprocess.Popen([sys.executable, str(entry)], cwd=str(repo))
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
        """
        self.log.info("Waiting for window (up to %ds)...", _CONNECT_TIMEOUT)
        deadline = time.time() + _CONNECT_TIMEOUT

        while time.time() < deadline:
            try:
                wins = Desktop(backend="uia").windows(title_re=_WINDOW_RE)
                # Prefer the largest matching window (main app, not toast/popup)
                main = next((w for w in wins if _is_main_window(w)), None)
                if main:
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
                        pass
                    self.log.info("Connected: %r", title)
                    return True
            except Exception:
                pass
            time.sleep(0.5)

        self.log.error("Timed out waiting for window")
        return False

    def _attach(self) -> bool:
        """
        Connect to an already-running NetSentinel window without launching.
        Used with --connect flag when the developer has the app open.
        """
        self.log.info("Attaching to running NetSentinel window...")
        try:
            wins = Desktop(backend="uia").windows(title_re=_WINDOW_RE)
            # Prefer main window over toast/popup (same _WINDOW_RE may match toasts)
            main = next((w for w in wins if _is_main_window(w)), None)
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
                pass
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
        """Close modal error/confirmation windows that would block the test."""
        try:
            for win in Desktop(backend="uia").windows():
                try:
                    title = (win.window_text() or "").lower()
                except Exception:
                    continue
                if not title or "netsentinel" in title:
                    continue
                is_blocking = any(kw in title for kw in [
                    "error", "exception", "unhandled", "crash",
                    "warning", "confirm", "are you sure",
                ])
                if not is_blocking:
                    continue
                self.log.warning("Dismissing dialog: %r", title)
                for btn_name in ["OK", "Close", "Cancel", "No", "Dismiss"]:
                    try:
                        win.child_window(title=btn_name, control_type="Button").click()
                        return
                    except Exception:
                        continue
                try:
                    win.type_keys("%{F4}")
                except Exception:
                    pass
        except Exception as exc:
            self.log.debug("Dialog scan: %s", exc)

    # ── Health monitoring (background thread) ─────────────────────────────

    def _health_monitor(self) -> None:
        """
        Background thread: checks process liveness, memory, and hang detection.
        Sets self._stop on any serious problem.
        """
        while not self._stop.is_set():
            time.sleep(_HEALTH_INTERVAL)

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

    def _alive(self) -> bool:
        # When attached without a process handle, fall back to window check only
        if self._proc is None:
            return self._window_ok()
        try:
            return self._proc.is_running() and self._proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def _window_ok(self, retries: int = 6) -> bool:
        """
        Returns True if the main NetSentinel window is accessible on the desktop.

        PyQt6 windows can briefly disappear from the UIA tree during overlay
        animations or startup sequences without the process dying.  After each
        failed check we do a fresh Desktop scan to pick up a new/re-created
        window handle before giving up.

        The size check (_is_main_window) ensures we never mistake a NetSentinel
        toast notification or system popup for the main window.
        """
        for i in range(retries):
            # Fast path: cached reference — verify it's still the main window
            try:
                if self._win is not None and self._win.exists() and _is_main_window(self._win):
                    return True
            except Exception:
                pass
            # Slow path: re-scan Desktop, picking the largest matching window
            try:
                wins = Desktop(backend="uia").windows(title_re=_WINDOW_RE)
                main = next((w for w in wins if _is_main_window(w)), None)
                if main:
                    self._win = main
                    return True
            except Exception:
                pass
            if i < retries - 1:
                time.sleep(0.5)
        return False

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
            win_top = win_rect.top
        except Exception:
            win_rect = None
            win_top = None

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
                    pass
                try:
                    if not ctrl.is_visible():
                        continue
                except Exception:
                    pass
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
                        pass
                # Spatial filter: skip controls inside the title-bar strip
                # (~top 38px of the frameless window = close/min/max buttons)
                if win_top is not None and ctype in ("Button", "SplitButton"):
                    try:
                        ctrl_top = ctrl.rectangle().top
                        if ctrl_top - win_top < 38:
                            self.stats.blacklisted += 1
                            continue
                    except Exception:
                        pass
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
        except (ElementNotEnabled, ElementNotVisible) as exc:
            action_str = "skip_state"
            result = f"skipped:{exc.__class__.__name__}"
            self.stats.skipped += 1
        except pywinauto.findwindows.ElementNotFoundError:
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
            "stats": self.stats.to_dict(),
            "last_actions": self.hist.dump(),
        }
        rpath = str(Path(self.cfg.output_dir) / f"monkey_crash_{ts}.json")
        try:
            with open(rpath, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            self.log.info("Crash report: %s", rpath)
        except Exception:
            pass

    # ── Main run ──────────────────────────────────────────────────────────

    def run(self) -> int:
        self.log.info("NetSentinel Monkey Tester v%s", _VERSION)
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
        time.sleep(2.0)   # let animations settle before first interaction

        # Start background health monitor
        hthread = threading.Thread(target=self._health_monitor, daemon=True, name="health")
        hthread.start()

        self.log.info("Starting %d iterations…", self.cfg.iterations)
        crashed = False
        self._last_iter_time = time.time()

        for i in range(1, self.cfg.iterations + 1):
            # Health monitor signalled a problem
            if self._stop.is_set():
                self._crash_report("health monitor triggered")
                crashed = True
                break

            # Progress update every 25 iterations
            if i % 25 == 0:
                rss = 0.0
                try:
                    rss = self._proc.memory_info().rss / (1024 * 1024)
                except Exception:
                    pass
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
                self._crash_report(f"iteration {i}")
                crashed = True
                break

        self._stop.set()

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
            pass

        # Graceful shutdown — skip when in --connect mode (we didn't own the app)
        if not self.cfg.connect_only and self._alive():
            self.log.info("Closing app...")
            try:
                self._win.close()
                time.sleep(2.5)
            except Exception:
                pass
            if self._alive():
                try:
                    self._proc.terminate()
                except Exception:
                    pass

        return 1 if crashed else 0


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
    p.add_argument("--chaos", choices=["mild", "moderate", "wild"], default="moderate")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--no-screenshots", action="store_true")
    p.add_argument("--mem-limit", type=int, default=800, metavar="MB")
    p.add_argument("--log", default="",
                   help="Log file path (default: <output-dir>/monkey.log)")
    p.add_argument("--output-dir", default="test_output",
                   help="Directory for all generated output files (default: test_output)")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if not args.source and not args.connect and not args.exe_path:
        print("ERROR: provide an exe path, --source, or --connect", file=sys.stderr)
        sys.exit(2)

    if args.exe_path and not Path(args.exe_path).exists():
        print(f"ERROR: exe not found: {args.exe_path}", file=sys.stderr)
        sys.exit(2)

    cfg = Config(
        exe_path=args.exe_path,
        use_source=args.source,
        connect_only=args.connect,
        iterations=args.iterations,
        chaos=args.chaos,
        seed=args.seed,
        screenshots=not args.no_screenshots,
        mem_limit_mb=args.mem_limit,
        output_dir=args.output_dir,
        log_file=args.log,
    )

    sys.exit(MonkeyTester(cfg).run())


if __name__ == "__main__":
    main()
