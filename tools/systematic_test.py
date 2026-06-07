#!/usr/bin/env python3
"""
tools/systematic_test.py — Exhaustive UI coverage tester for NetSentinel
=========================================================================
Navigates to every registered page in order, discovers all clickable controls,
and clicks each one once.  Reports full coverage when done.

Unlike monkey_test.py (chaos/random), this script is deterministic:
it visits pages in a fixed order and exercises every visible control exactly
once per page visit.

Usage (source — recommended for dev):
    python tools/systematic_test.py --source

Usage (attach to already-running app):
    python tools/systematic_test.py --connect

Options:
    --source              Launch via "python app.py" from repo root
    --connect             Attach to an already-running NetSentinel window
    --pages PAGE ...      Only test these pages (default: all)
    --pause N             Seconds between clicks (default 0.35)
    --log FILE            Log file (default: systematic_test.log)
    --no-screenshots      Skip failure screenshots

Exit codes:
    0   All pages visited, no crash
    1   App crashed during testing
    2   Could not launch / connect

Requirements:
    pip install pywinauto psutil Pillow
"""

import argparse
import dataclasses
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import psutil
except ImportError:
    sys.exit("ERROR: psutil required.  pip install psutil")

try:
    from pywinauto import Desktop
    from pywinauto.base_wrapper import ElementNotEnabled, ElementNotVisible
    from pywinauto.findwindows import ElementNotFoundError
except ImportError:
    sys.exit("ERROR: pywinauto required.  pip install pywinauto")

try:
    from PIL import ImageGrab
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ── Constants ──────────────────────────────────────────────────────────────────

_VERSION = "1.0.0"
_WINDOW_RE = ".*NetSentinel.*"
_CONNECT_TIMEOUT = 60
_CONNECT_POLL = 1.0

# All pages in nav order (matches _build_pro_nav in dashboard.py).
# The command palette is used for navigation so labels must match exactly.
_ALL_PAGES: List[str] = [
    # Getting Started
    "Overview", "Speed Test", "DNS Monitor", "Home", "What's Wrong?",
    # Discover
    "Devices", "Network Map", "WiFi", "DHCP Leases", "Home Automation",
    # Monitor
    "Log Hub", "Live Bandwidth", "Connections", "Availability", "Service Heartbeat",
    # Reports
    "Network Grade", "Health Report", "Network Doc", "IP Calculator", "Notifications",
    # Analysis
    "Broadcast Storm", "STP / Rogue Bridge", "IoT Baseline", "Monitor Overview",
    "802.11 Monitor", "ARP Watch", "Trace", "SNMP Traps", "Tools",
    "Geo Map", "Trends", "Timeline",
    # Automation
    "Automation Hooks", "Scheduled Scans", "Custom Triggers",
    "MQTT", "REST API", "Config Snapshots", "Maintenance Windows",
    # Security Audit (no admin-required actions clicked)
    "Security Overview",
    # Education
    "Protocol Viz", "Lab Mode", "Feature Guide", "Help",
]

# Shared blacklist — same rules as monkey_test.py: never click destructive controls
_BLACKLIST: List[str] = [
    "send test", "test email", "test webhook", "test push", "test ntfy",
    "test telegram", "send email", "publish",
    "run login test", "start scan", "launch scan", "full discovery",
    "syn scan", "port scan", "run diagnostics",
    "delete", "remove device", "clear all", "wipe", "purge",
    "reset to default", "install speedtest", "install ookla", "install npcap",
    "", "", "", "", "", "",
    "_chromebutton",
    "quit", "exit application",
    "export pdf", "save pdf", "export csv", "save report",
    "sign in", "authenticate",
    "factory reset", "restore defaults",
]

_SUPPORTED_TYPES = frozenset({
    "Button", "CheckBox", "RadioButton", "ComboBox", "Edit",
    "ListItem", "TabItem", "Slider", "Hyperlink", "SplitButton",
})



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


def _is_blacklisted(name: str, auto_id: str) -> bool:
    combined = (name + " " + auto_id).lower()
    return any(pat in combined for pat in _BLACKLIST)


def _is_main_window(win) -> bool:
    """True when win looks like the main app window (not a toast/popup)."""
    try:
        r = win.rectangle()
        return (r.right - r.left) >= 600 and (r.bottom - r.top) >= 400
    except Exception:
        return False


def _screenshot(label: str, log: logging.Logger) -> Optional[str]:
    if not _HAS_PIL:
        return None
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = f"systematic_{label}_{ts}.png"
        ImageGrab.grab().save(path)
        log.info("Screenshot: %s", path)
        return path
    except Exception as exc:
        log.debug("Screenshot failed: %s", exc)
        return None


def _setup_log(log_file: str) -> logging.Logger:
    log = logging.getLogger("systematic")
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s", "%H:%M:%S")
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


# ── Page result dataclass ──────────────────────────────────────────────────────

@dataclasses.dataclass
class PageResult:
    name: str
    navigated: bool = False
    controls_found: int = 0
    controls_clicked: int = 0
    controls_skipped: int = 0
    controls_errored: int = 0
    crashed: bool = False
    note: str = ""

    def summary(self) -> str:
        status = "CRASH" if self.crashed else ("OK" if self.navigated else "SKIP")
        return (f"[{status}] {self.name:<30}  found={self.controls_found:3d}  "
                f"clicked={self.controls_clicked:3d}  "
                f"skipped={self.controls_skipped:3d}  "
                f"errors={self.controls_errored:3d}"
                + (f"  ({self.note})" if self.note else ""))


# ── Tester class ───────────────────────────────────────────────────────────────

class SystematicTester:
    def __init__(self, cfg: "Config"):
        self.cfg = cfg
        Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
        self.log = _setup_log(cfg.resolved_log_file())
        self._proc: Optional[psutil.Process] = None
        self._win = None
        self._results: List[PageResult] = []

    # ── Launch & connect ──────────────────────────────────────────────────

    def _launch_source(self) -> bool:
        repo = Path(__file__).parent.parent
        entry = repo / "app.py"
        self.log.info("Launching: python %s", entry)
        try:
            raw = subprocess.Popen([sys.executable, str(entry)], cwd=str(repo))
            self._proc = psutil.Process(raw.pid)
            self.log.info("PID: %d", raw.pid)
            return True
        except Exception as exc:
            self.log.error("Launch failed: %s", exc)
            return False

    def _connect(self) -> bool:
        self.log.info("Waiting for main window (up to %ds)…", _CONNECT_TIMEOUT)
        deadline = time.time() + _CONNECT_TIMEOUT
        while time.time() < deadline:
            try:
                wins = Desktop(backend="uia").windows(title_re=_WINDOW_RE)
                main = next((w for w in wins if _is_main_window(w)), None)
                if main:
                    try:
                        pid = main.element_info.process_id
                        self._proc = psutil.Process(pid)
                    except Exception:
                        self.log.debug("PID lookup failed")
                    self._win = main
                    self.log.info("Connected: %r", main.window_text())
                    return True
            except Exception:
                self.log.debug("UIA scan error; retrying")
            time.sleep(_CONNECT_POLL)
        self.log.error("Timed out waiting for window")
        return False

    def _attach(self) -> bool:
        self.log.info("Attaching to running NetSentinel…")
        try:
            wins = Desktop(backend="uia").windows(title_re=_WINDOW_RE)
            main = next((w for w in wins if _is_main_window(w)), None)
            if not main:
                self.log.error("No NetSentinel main window found")
                return False
            try:
                pid = main.element_info.process_id
                self._proc = psutil.Process(pid)
                self.log.info("PID: %d", pid)
            except Exception:
                self.log.debug("PID lookup failed")
            self._win = main
            self.log.info("Attached: %r", main.window_text())
            return True
        except Exception as exc:
            self.log.error("Attach failed: %s", exc)
            return False

    def _alive(self) -> bool:
        if self._proc is None:
            return self._win_ok()
        try:
            return self._proc.is_running() and self._proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False

    def _win_ok(self) -> bool:
        try:
            if self._win and self._win.exists() and _is_main_window(self._win):
                return True
        except Exception:
            self.log.debug("cached window reference stale")
        try:
            wins = Desktop(backend="uia").windows(title_re=_WINDOW_RE)
            main = next((w for w in wins if _is_main_window(w)), None)
            if main:
                self._win = main
                return True
        except Exception:
            self.log.debug("UIA desktop scan failed")
        return False

    def _dismiss_startup_overlays(self) -> None:
        self.log.info("Checking for startup overlays…")
        time.sleep(2.5)
        for label in ["Get Started", "Close", "Skip", "Continue", "OK", "No Thanks", "Later"]:
            try:
                btn = self._win.child_window(title=label, control_type="Button")
                if btn.exists(timeout=0.5):
                    btn.click_input()
                    time.sleep(0.4)
                    self.log.info("Dismissed overlay: %r", label)
                    break
            except Exception:
                continue

    def _dismiss_any_overlay(self) -> None:
        """Press ESC to close command palette / flyout / dialogs."""
        try:
            self._win.type_keys("{ESC}")
            time.sleep(0.15)
        except Exception:
            self.log.debug("ESC dismiss failed")

    # ── Navigation ────────────────────────────────────────────────────────

    def _navigate_to(self, page: str) -> bool:
        """Navigate to *page* via the command palette.  Returns True on success."""
        self._dismiss_any_overlay()
        time.sleep(0.2)
        try:
            self._win.type_keys("^k")
            time.sleep(0.5)
            # Type enough of the page name for the fuzzy match to pick it
            query = page[:8] if len(page) > 8 else page
            self._win.type_keys(query, with_spaces=True, pause=0.04)
            time.sleep(0.35)
            self._win.type_keys("{ENTER}")
            time.sleep(0.8)
            return True
        except Exception as exc:
            self.log.warning("Navigation to %r failed: %s", page, exc)
            try:
                self._win.type_keys("{ESC}")
            except Exception:
                self.log.debug("ESC after nav failure failed")
            return False

    # ── Control collection ────────────────────────────────────────────────

    def _get_controls(self) -> List:
        """Return enabled, visible, non-blacklisted descendants within the window."""
        try:
            all_ctrl = self._win.descendants()
        except Exception as exc:
            self.log.debug("descendants() failed: %s", exc)
            return []

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
                    continue
                # Bounds guard: must be within the main window
                if win_rect is not None:
                    try:
                        cr = ctrl.rectangle()
                        margin = 60
                        if (cr.right  < win_rect.left   - margin or
                                cr.left   > win_rect.right  + margin or
                                cr.bottom < win_rect.top    - margin or
                                cr.top    > win_rect.bottom + margin):
                            continue
                    except Exception:
                        self.log.debug("rectangle() failed; skipping bounds check")
                # Skip title-bar chrome (top 38px)
                if win_rect is not None and ctype in ("Button", "SplitButton"):
                    try:
                        if ctrl.rectangle().top - win_rect.top < 38:
                            continue
                    except Exception:
                        self.log.debug("title-bar check failed")
                result.append(ctrl)
            except Exception:
                continue
        return result

    # ── Click one control ─────────────────────────────────────────────────

    def _click_control(self, ctrl) -> Tuple[str, str]:
        """Interact with a control.  Returns (action, result)."""
        ctype = _safe_type(ctrl)
        try:
            if ctype in ("Button", "SplitButton", "Hyperlink"):
                ctrl.click_input()
                return "click", "ok"
            elif ctype == "CheckBox":
                ctrl.toggle()
                return "toggle", "ok"
            elif ctype == "RadioButton":
                ctrl.click_input()
                return "click", "ok"
            elif ctype == "ComboBox":
                try:
                    count = ctrl.item_count()
                    if count and count > 0:
                        ctrl.select(0)
                        return "select:0", "ok"
                except Exception:
                    self.log.debug("ComboBox select failed")
                ctrl.click_input()
                return "click_open", "ok"
            elif ctype == "Edit":
                ctrl.set_focus()
                ctrl.type_keys("^a", pause=0.05)
                return "focus", "ok"
            elif ctype == "Slider":
                try:
                    r = ctrl.rectangle()
                    w = r.right - r.left
                    ctrl.click_input(coords=(w // 2, (r.bottom - r.top) // 2))
                    return "slide", "ok"
                except Exception:
                    ctrl.click_input()
                    return "click", "ok"
            elif ctype in ("ListItem", "TabItem"):
                ctrl.click_input()
                return "click", "ok"
            else:
                ctrl.click_input()
                return "click_fallback", "ok"
        except (ElementNotEnabled, ElementNotVisible):
            return "skip", "not_interactable"
        except ElementNotFoundError:
            return "skip", "gone"
        except Exception as exc:
            return "error", f"{exc.__class__.__name__}:{str(exc)[:60]}"

    # ── Page test ─────────────────────────────────────────────────────────

    def _test_page(self, page: str) -> PageResult:
        res = PageResult(name=page)

        self.log.info("── Page: %s", page)

        if not self._navigate_to(page):
            res.note = "navigation failed"
            return res
        res.navigated = True

        if not self._alive():
            res.crashed = True
            res.note = "crashed after navigation"
            return res

        controls = self._get_controls()
        res.controls_found = len(controls)
        self.log.info("  Found %d controls", len(controls))

        for ctrl in controls:
            if not self._alive():
                res.crashed = True
                res.note = "crashed mid-page"
                break

            name = _safe_name(ctrl)
            ctype = _safe_type(ctrl)
            auto_id = _safe_id(ctrl)
            action, result = self._click_control(ctrl)

            if result == "ok":
                res.controls_clicked += 1
                self.log.debug("  [OK] %-12s %-24s %s  name=%r",
                               ctype, action, auto_id[:40], name)
            elif result == "not_interactable" or result == "gone":
                res.controls_skipped += 1
                self.log.debug("  [--] %-12s skipped  name=%r", ctype, name)
            else:
                res.controls_errored += 1
                self.log.debug("  [!!] %-12s %s  name=%r", ctype, result, name)

            # Dismiss any overlay / dialog the click may have opened
            self._dismiss_any_overlay()
            time.sleep(self.cfg.pause)

        return res

    # ── Main run ──────────────────────────────────────────────────────────

    def run(self) -> int:
        self.log.info("NetSentinel Systematic Tester v%s", _VERSION)
        self.log.info("pages=%d  pause=%.2fs  output=%s",
                      len(self.cfg.pages), self.cfg.pause, self.cfg.output_dir)

        # Launch or attach
        if self.cfg.connect_only:
            if not self._attach():
                return 2
        else:
            if not self._launch_source():
                return 2
            if not self._connect():
                return 2

        self._dismiss_startup_overlays()
        time.sleep(1.5)

        crashed = False
        for page in self.cfg.pages:
            if not self._alive():
                self.log.error("App died before page %r", page)
                crashed = True
                break

            res = self._test_page(page)
            self._results.append(res)

            if res.crashed:
                if self.cfg.screenshots:
                    _screenshot(f"crash_{page.replace(' ', '_')}", self.log)
                crashed = True
                break

            # Brief settle time between pages
            time.sleep(0.5)

        # Print coverage report
        sep = "=" * 70
        self.log.info(sep)
        self.log.info("SYSTEMATIC TEST %s", "FAILED" if crashed else "PASSED")
        self.log.info(sep)

        total_found = total_clicked = total_skipped = total_errored = 0
        pages_ok = pages_crashed = pages_skipped = 0

        for res in self._results:
            self.log.info(res.summary())
            total_found   += res.controls_found
            total_clicked += res.controls_clicked
            total_skipped += res.controls_skipped
            total_errored += res.controls_errored
            if res.crashed:
                pages_crashed += 1
            elif res.navigated:
                pages_ok += 1
            else:
                pages_skipped += 1

        self.log.info(sep)
        self.log.info("Pages tested:  %d  (ok=%d  crashed=%d  skipped=%d)",
                      len(self._results), pages_ok, pages_crashed, pages_skipped)
        self.log.info("Controls found:   %d", total_found)
        self.log.info("Controls clicked: %d", total_clicked)
        self.log.info("Controls skipped: %d", total_skipped)
        self.log.info("Controls errored: %d", total_errored)
        self.log.info(sep)

        # Save JSON report
        report = {
            "version": _VERSION,
            "ts": datetime.now().isoformat(),
            "passed": not crashed,
            "pages": [dataclasses.asdict(r) for r in self._results],
            "totals": {
                "pages_ok": pages_ok,
                "pages_crashed": pages_crashed,
                "pages_skipped": pages_skipped,
                "controls_found": total_found,
                "controls_clicked": total_clicked,
                "controls_skipped": total_skipped,
                "controls_errored": total_errored,
            },
        }
        rpath = str(Path(self.cfg.output_dir) / "systematic_report.json")
        try:
            with open(rpath, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            self.log.info("Report: %s", rpath)
        except Exception:
            self.log.debug("could not write report JSON")

        # Graceful shutdown
        if not self.cfg.connect_only and self._alive():
            try:
                self._win.close()
                time.sleep(2.0)
            except Exception:
                self.log.debug("window close failed")
            if self._alive():
                try:
                    self._proc.terminate()
                except Exception:
                    self.log.debug("process terminate failed")

        return 1 if crashed else 0


# ── Config & CLI ───────────────────────────────────────────────────────────────

@dataclasses.dataclass
class Config:
    connect_only: bool = False
    pages: List[str] = dataclasses.field(default_factory=lambda: list(_ALL_PAGES))
    pause: float = 0.35
    output_dir: str = "test_output"
    log_file: str = ""               # empty = auto-derive from output_dir
    screenshots: bool = True

    def resolved_log_file(self) -> str:
        if self.log_file:
            return self.log_file
        return str(Path(self.output_dir) / "systematic.log")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Exhaustive page-by-page UI coverage tester for NetSentinel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--source", action="store_true",
                   help="Launch via 'python app.py' (default when not --connect)")
    p.add_argument("--connect", action="store_true",
                   help="Attach to an already-running NetSentinel window")
    p.add_argument("--pages", nargs="+", metavar="PAGE",
                   help="Only test these pages (default: all)")
    p.add_argument("--pause", type=float, default=0.35, metavar="N",
                   help="Seconds between clicks (default 0.35)")
    p.add_argument("--log", default="",
                   help="Log file path (default: <output-dir>/systematic.log)")
    p.add_argument("--output-dir", default="test_output",
                   help="Directory for all generated output files (default: test_output)")
    p.add_argument("--no-screenshots", action="store_true")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if not args.source and not args.connect:
        # Default to --source if neither flag is given
        args.source = True

    pages = args.pages if args.pages else list(_ALL_PAGES)

    cfg = Config(
        connect_only=args.connect,
        pages=pages,
        pause=args.pause,
        output_dir=args.output_dir,
        log_file=args.log,
        screenshots=not args.no_screenshots,
    )

    sys.exit(SystematicTester(cfg).run())


if __name__ == "__main__":
    main()
