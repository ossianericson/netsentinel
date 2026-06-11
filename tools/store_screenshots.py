"""
Capture 10 Windows Store screenshots from the running NetSentinel app.

Usage:
    python tools/store_screenshots.py              # all pages
    python tools/store_screenshots.py --page 03_devices  # re-run one page
    python tools/store_screenshots.py --out C:\\path\\to\\dir

Requirements:
    pip install pywinauto pillow pywin32
    The app must already be running: python app.py
"""
import argparse
import ctypes
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import win32gui
    import win32con
    from PIL import ImageGrab
    from pywinauto import Desktop
except ImportError as e:
    sys.exit(f"Missing dependency: {e}\nRun: pip install pywinauto pillow pywin32")

# ── constants ──────────────────────────────────────────────────────────────────
TARGET_W, TARGET_H = 1920, 1080

_ES_CONTINUOUS       = 0x80000000
_ES_SYSTEM_REQUIRED  = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

# (page_label_for_ctrl_k, filename_slug, extra_wait_secs_after_nav)
# Labels must be long enough to uniquely resolve in the fuzzy palette.
# TIP: run a full scan before capturing so every page has real data to display.
# Note: "What's Wrong" omits the trailing ? — special chars can confuse type_keys.
PAGES = [
    ("Overview",            "01_overview",         3.0),  # grade ring + KPI tiles — best thumbnail
    ("Devices",             "02_devices",           3.5),  # OUI / risk-classified device inventory
    ("What's Wrong",        "03_diagnosis",         3.5),  # plain-English one-click diagnosis
    ("Network Map",         "04_network_map",       3.5),  # topology graph
    ("Speed Test",          "05_speed_test",        2.5),  # speed + modem signal panel
    ("Network Logger",      "06_network_logger",    2.5),  # continuous RTT / modem / mesh log
    ("Security Overview",   "07_security_overview", 3.5),  # aggregate security findings
    ("Protocol Visualizer", "08_protocol_viz",      3.0),  # animated ARP/DNS/TCP/DHCP/STP
    ("Lab Mode",            "09_lab_mode",          2.5),  # guided CompTIA / CCNA exercises
    ("Geolocation Map",     "10_geo_map",           3.5),  # offline MaxMind IP geolocation map
]


# ── focus / sleep helpers ──────────────────────────────────────────────────────

def _force_foreground(hwnd: int) -> None:
    """Bring hwnd to foreground using AttachThreadInput to bypass Windows focus-theft blocking."""
    try:
        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        cur_tid  = kernel32.GetCurrentThreadId()
        tgt_tid  = user32.GetWindowThreadProcessId(hwnd, None)
        attached = (bool(tgt_tid) and cur_tid != tgt_tid and
                    bool(user32.AttachThreadInput(cur_tid, tgt_tid, True)))
        try:
            user32.ShowWindow(hwnd, 9)       # SW_RESTORE
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(cur_tid, tgt_tid, False)
    except Exception:
        pass  # non-fatal — window may still become foreground via BringWindowToTop


def _prevent_sleep_begin() -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
        )
    except Exception:
        pass  # non-fatal — no sleep suppression on this platform


def _prevent_sleep_end() -> None:
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(_ES_CONTINUOUS)
    except Exception:
        pass  # non-fatal


# ── window helpers ─────────────────────────────────────────────────────────────

def find_hwnd() -> int | None:
    results: list[int] = []

    def _cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if "NetSentinel" in t and "Visual Studio Code" not in t:
                results.append(hwnd)

    win32gui.EnumWindows(_cb, None)
    return results[0] if results else None


def find_main_window():
    """Return the pywinauto wrapper for the NetSentinel main window."""
    wins = Desktop(backend="uia").windows(title_re=".*NetSentinel.*")
    wins = [w for w in wins if "Visual Studio Code" not in w.window_text()]
    if not wins:
        return None
    wins.sort(key=lambda w: w.rectangle().width() * w.rectangle().height(), reverse=True)
    return wins[0]


def resize_window(hwnd: int, w: int, h: int) -> None:
    rect = win32gui.GetWindowRect(hwnd)
    x, y = max(rect[0], 0), max(rect[1], 0)
    placement = win32gui.GetWindowPlacement(hwnd)
    if placement[1] == win32con.SW_SHOWMAXIMIZED:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.5)
    win32gui.SetWindowPos(
        hwnd, win32con.HWND_TOP,
        x, y, w, h,
        win32con.SWP_NOZORDER | win32con.SWP_SHOWWINDOW,
    )
    time.sleep(0.6)


def capture_window(hwnd: int, path: Path) -> None:
    rect = win32gui.GetWindowRect(hwnd)
    img = ImageGrab.grab(rect, all_screens=True)
    img.save(str(path))
    print(f"  saved -> {path.name}  ({img.size[0]}x{img.size[1]})")


# ── navigation ─────────────────────────────────────────────────────────────────

def navigate(app_win, hwnd: int, label: str, wait: float) -> None:
    """Open Ctrl+K, type the full page label, press Enter, wait for render."""
    # Ensure the window has focus before sending keys
    _force_foreground(hwnd)
    time.sleep(0.25)

    # Dismiss any open palette / flyout / dialog
    app_win.type_keys("{ESC}", pause=0.05)
    time.sleep(0.35)

    # Open the command palette
    app_win.type_keys("^k", pause=0.05)
    time.sleep(0.7)

    # Type the full label — long enough to uniquely resolve in fuzzy match
    app_win.type_keys(label, with_spaces=True, pause=0.05)
    time.sleep(0.6)

    # Navigate
    app_win.type_keys("{ENTER}", pause=0.05)

    # Wait for 160 ms crossfade + page render + any data population
    time.sleep(wait)

    # Re-acquire focus in case something (toast, system notification) stole it
    _force_foreground(hwnd)
    time.sleep(0.3)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Capture NetSentinel Store screenshots")
    parser.add_argument(
        "--page", metavar="SLUG",
        help="Capture only this slug, e.g. --page 03_devices"
    )
    parser.add_argument(
        "--out", metavar="DIR",
        help="Output directory (default: store_screenshots/<timestamp>)"
    )
    args = parser.parse_args()

    main_win = find_main_window()
    if not main_win:
        sys.exit("NetSentinel window not found — start  python app.py  first.")

    hwnd = main_win.handle
    print(f"Found window: hwnd={hwnd}  title={main_win.window_text()!r}")

    # Resolve output directory
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = Path(__file__).parent.parent / "store_screenshots" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output : {out_dir}")

    pages = PAGES
    if args.page:
        pages = [(lbl, slug, w) for lbl, slug, w in PAGES if slug == args.page]
        if not pages:
            slugs = [s for _, s, _ in PAGES]
            sys.exit(f"Unknown slug {args.page!r}. Available: {slugs}")

    _prevent_sleep_begin()
    try:
        print(f"Resizing to {TARGET_W}x{TARGET_H}...")
        resize_window(hwnd, TARGET_W, TARGET_H)
        _force_foreground(hwnd)
        time.sleep(0.5)

        # Dismiss any startup overlay or open flyout
        main_win.type_keys("{ESC}", pause=0.05)
        time.sleep(0.4)

        for label, slug, wait in pages:
            print(f"\n-> {label}  (wait {wait}s after nav)")
            navigate(main_win, hwnd, label, wait)
            capture_window(hwnd, out_dir / f"{slug}.png")

        print(f"\nDone. {len(pages)} screenshot(s) in:")
        print(f"  {out_dir}")
    finally:
        _prevent_sleep_end()


if __name__ == "__main__":
    main()
