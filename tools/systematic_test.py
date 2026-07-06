#!/usr/bin/env python3
"""
tools/systematic_test.py — Exhaustive UI coverage tester for NetSentinel
=========================================================================
Navigates to every registered page in order, discovers all clickable controls,
and clicks each one once.  Reports full coverage when done.

Unlike monkey_test.py (chaos/random), this script is deterministic:
it visits pages in a fixed order and exercises every visible control exactly
once per page visit.

De-forked (P2): this tool no longer carries its own copy of the launch /
connect / attach / dialog-guard / focus / blacklist machinery.  It subclasses
`monkey_test.MonkeyTester` (and its `Config`) — exactly as
`monkey_mouse_test.py` and `scan_navigate_test.py` already do — and reuses that
one battle-tested implementation.  The blacklist (`_mt._BLACKLIST` /
`_mt._is_blacklisted`), window attach/connect loop, and file-dialog / shutdown
guard therefore have a single source of truth: fix them once in monkey_test.py
and every tester inherits the fix (this is what ends the recurring per-tool
"whack-a-mole" of duplicated fixes).  Only the deterministic page-by-page
sweep — navigation, per-page control collection, and the click dispatcher —
lives here.

Usage (source — recommended for dev):
    python tools/systematic_test.py --source

Usage (attach to already-running app):
    python tools/systematic_test.py --connect

Options:
    --source              Launch via "python app.py" from repo root
    --connect             Attach to an already-running NetSentinel window
    --pages PAGE ...      Only test these pages (default: all)
    --pause N             Seconds between clicks (default 0.35)
    --log FILE            Log file (default: <output-dir>/systematic.log)
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
import re
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).parent))
try:
    import monkey_test as _mt
except ImportError:
    if __name__ == "__main__":
        sys.exit("ERROR: pywinauto/psutil required.  pip install pywinauto psutil")
    raise


# ── Constants ──────────────────────────────────────────────────────────────────

_VERSION = "1.3.0"


def _discover_pages(skip_admin: bool = True) -> List[str]:
    """Parse ui/nav/builder.py at runtime to get the live registered page list.

    This ensures systematic_test.py never lags behind _build_pro_nav().
    Pages with admin_required=True are excluded by default (require elevation).
    """
    builder = Path(__file__).parent.parent / "ui" / "nav" / "builder.py"
    src = builder.read_text(encoding="utf-8")
    labels: List[str] = []
    # Match: _nav_add_rail_item("Label", <anything up to closing paren>)
    for m in re.finditer(
        r'_nav_add_rail_item\(\s*"([^"]+)"([^)]*)\)', src, re.DOTALL
    ):
        label = m.group(1)
        args = m.group(2)
        if skip_admin and "admin_required=True" in args:
            continue
        labels.append(label)
    if not labels:
        raise RuntimeError(
            "systematic_test: _discover_pages() found 0 pages — "
            "check that ui/nav/builder.py still uses _nav_add_rail_item()"
        )
    return labels


# Auto-derived from ui/nav/builder.py — never edit this manually.
# To exclude a page from testing, add it to _SKIP_PAGES below.
_SKIP_PAGES: List[str] = []   # e.g. pages that require hardware not present in CI

_ALL_PAGES: List[str] = [p for p in _discover_pages() if p not in _SKIP_PAGES]

# Control types this deterministic sweep interacts with.  Intentionally a subset
# of monkey_test._SUPPORTED_TYPES: TreeItem/MenuItem are excluded so a page sweep
# never expands a tree or fires a menu command while walking controls in order.
# Hyperlink is excluded for the same reason monkey_test excludes it — clicking a
# UIA Hyperlink follows the link out of the app (Chrome/IE/URI handler).
_SUPPORTED_TYPES = frozenset({
    "Button", "CheckBox", "RadioButton", "ComboBox", "Edit",
    "ListItem", "TabItem", "Slider", "SplitButton",
})


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


# ── Config ─────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class SystematicConfig(_mt.Config):
    """Extends monkey_test.Config with the two page-sweep-only knobs.

    Every launch / connect / focus / screenshot / sleep-suppression field is
    inherited unchanged, so MonkeyTester's __init__ and reused methods work
    without modification.
    """
    pages: List[str] = dataclasses.field(default_factory=lambda: list(_ALL_PAGES))
    pause: float = 0.35              # seconds between clicks
    focus_interval: float = 5.0     # slower heartbeat than chaos (page sweep is calm)

    def resolved_log_file(self) -> str:
        if self.log_file:
            return self.log_file
        return str(Path(self.output_dir) / "systematic.log")


# ── Tester class ───────────────────────────────────────────────────────────────

class SystematicTester(_mt.MonkeyTester):
    """Reuses MonkeyTester's launch/connect/attach/dialog-guard/focus-heartbeat
    machinery unchanged; overrides only the run loop — a deterministic
    page-by-page control sweep instead of random chaos iterations."""

    def __init__(self, cfg: SystematicConfig):
        super().__init__(cfg)
        self.cfg: SystematicConfig = cfg
        self._results: List[PageResult] = []

    # ── Overlay handling ──────────────────────────────────────────────────

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
            hwnd = getattr(self._win, "handle", 0) or 0
            if hwnd:
                _mt._force_foreground(hwnd)
            else:
                self._win.set_focus()
            time.sleep(0.1)
            self._win.type_keys("^k")
            time.sleep(0.5)
            # Type enough of the page name for the fuzzy match to pick it
            query = page[:12] if len(page) > 12 else page
            self._win.type_keys(query, with_spaces=True, pause=0.04)
            time.sleep(0.35)
            self._win.type_keys("{ENTER}")
            time.sleep(2.0)   # allow 160ms palette animation + page render + skeleton loaders
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
            hwnd = getattr(self._win, "handle", 0) or 0
            if hwnd:
                _mt._force_foreground(hwnd)
            else:
                self._win.set_focus()
            time.sleep(0.5)
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
                ctype = _mt._safe_type(ctrl)
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
                name = _mt._safe_name(ctrl)
                auto_id = _mt._safe_id(ctrl)
                if _mt._is_blacklisted(name, auto_id):
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
                # Skip title-bar chrome (top 60px — AppHeaderMixin header is ~40px)
                if win_rect is not None and ctype in ("Button", "SplitButton"):
                    try:
                        if ctrl.rectangle().top - win_rect.top < 60:
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
        ctype = _mt._safe_type(ctrl)
        try:
            if ctype in ("Button", "SplitButton"):
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
        except (_mt.ElementNotEnabled, _mt.ElementNotVisible):
            return "skip", "not_interactable"
        except _mt.ElementNotFoundError:
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

        # Dismiss any dialog that surfaced during navigation (e.g. onboarding overlays)
        self._dismiss_blocking_dialogs()

        if not self._alive():
            res.crashed = True
            res.note = "crashed after navigation"
            return res

        controls = self._get_controls()
        if not controls:
            for _retry in range(3):
                self.log.debug("  0 controls on %r — retry %d/3 (waiting 1.5s)", page, _retry + 1)
                time.sleep(1.5)
                controls = self._get_controls()
                if controls:
                    break
        res.controls_found = len(controls)
        self.log.info("  Found %d controls", len(controls))

        for ctrl in controls:
            if not self._alive():
                res.crashed = True
                res.note = "crashed mid-page"
                break

            name = _mt._safe_name(ctrl)
            ctype = _mt._safe_type(ctrl)
            auto_id = _mt._safe_id(ctrl)
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

            # Close any Windows file dialog or blocking modal the click opened.
            # Call this before ESC so a file picker gets a proper Cancel click
            # rather than being left open (ESC doesn't always close them).
            self._dismiss_blocking_dialogs()
            self._dismiss_any_overlay()
            time.sleep(self.cfg.pause)

        return res

    # ── Main run ──────────────────────────────────────────────────────────

    def run(self) -> int:
        self.log.info("NetSentinel Systematic Tester v%s", _VERSION)
        self.log.info("pages=%d  pause=%.2fs  output=%s",
                      len(self.cfg.pages), self.cfg.pause, self.cfg.output_dir)

        # Launch or attach — inherited from MonkeyTester.
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

        # Suppress sleep and start focus heartbeat
        if self.cfg.prevent_sleep:
            _mt._prevent_sleep_begin(self.log)
        self._stop.clear()
        hb = threading.Thread(target=self._focus_heartbeat, daemon=True, name="sys_focus")
        hb.start()

        crashed = False
        try:
            for page in self.cfg.pages:
                if not self._alive():
                    self.log.error("App died before page %r", page)
                    crashed = True
                    break

                res = self._test_page(page)
                self._results.append(res)

                if res.crashed:
                    if self.cfg.screenshots:
                        _mt._screenshot(f"crash_{page.replace(' ', '_')}", self.log,
                                        self.cfg.output_dir)
                    crashed = True
                    break

                # Brief settle time between pages
                time.sleep(0.5)
        finally:
            self._stop.set()
            if self.cfg.prevent_sleep:
                _mt._prevent_sleep_end(self.log)

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


# ── CLI ─────────────────────────────────────────────────────────────────────────

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
    p.add_argument("--focus-interval", type=float, default=5.0, metavar="SECS",
                   help="Seconds between focus-heartbeat pulses (default 5)")
    p.add_argument("--no-prevent-sleep", action="store_true",
                   help="Do not suppress Windows sleep/screensaver")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    if not args.source and not args.connect:
        # Default to --source if neither flag is given
        args.source = True

    pages = args.pages if args.pages else list(_ALL_PAGES)

    cfg = SystematicConfig(
        use_source=args.source,
        connect_only=args.connect,
        pages=pages,
        pause=args.pause,
        output_dir=args.output_dir,
        log_file=args.log,
        screenshots=not args.no_screenshots,
        prevent_sleep=not args.no_prevent_sleep,
        focus_interval=args.focus_interval,
    )

    sys.exit(SystematicTester(cfg).run())


if __name__ == "__main__":
    main()
