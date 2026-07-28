"""
Capture Windows Store screenshots from the running NetSentinel app.

Usage:
    python tools/store_screenshots.py              # all pages
    python tools/store_screenshots.py --page 03_devices  # re-run one page
    python tools/store_screenshots.py --out C:\\path\\to\\dir

Requirements:
    pip install pywinauto pillow pywin32
    The app must already be running: python app.py

Resolution: TARGET_W x TARGET_H (default 2048×1152).
  2048×1152 is the closest clean 16:9 resolution under the 2300×1300 cap.
  The Microsoft Store accepts up to 3840×2160; higher pixel counts stay sharper
  when the Store scales images to the thumbnail grid.
  Drop to 1920×1080 if your monitor cannot fit a 2048-wide window.

Store limit: the Store allows up to 10 screenshots per device family.
  This script captures 12 so you can pick the best 10 for submission.

Screenshot selection rationale (updated for v2.1.12 / UX Sprints 1–10):
  01_home              — landing page: health score ring, session strip, suggestions
  02_troubleshoot      — Sprint 3: 8 symptom tiles → correct tool (zero prior knowledge)
  03_devices           — Sprint 5: segment-grouped inventory, health indicators, naming
  04_app_traffic       — Sprint 6: per-host traffic breakdown (Web/Streaming/Gaming/VPN)
  05_network_map       — Sprint 6: Cytoscape.js interactive topology
  06_service_diag      — v2.0: streaming/gaming service probes + failure-layer verdict
  07_security_overview — aggregate security findings dashboard with letter grade
  08_threat_intel      — threat intelligence: AbuseIPDB lookup + CVE context
  09_speed_test        — speed history + modem signal panel side-by-side
  10_protocol_viz      — animated ARP/DNS/TCP/DHCP/STP diagrams (education angle)
  11_lab_mode          — guided CompTIA N+/CCNA exercises (unique differentiator)
  12_geo_map           — offline MaxMind geolocation map — no API key required
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
# 2048×1152 — closest clean 16:9 resolution under the 2300×1300 Store cap.
# Drop to 1920×1080 if your monitor cannot fit a 2048-wide window.
TARGET_W, TARGET_H = 2048, 1152

_ES_CONTINUOUS       = 0x80000000
_ES_SYSTEM_REQUIRED  = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002

# (page_label_for_ctrl_k, filename_slug, extra_wait_secs_after_nav)
# Labels must be long enough to uniquely resolve in the fuzzy palette.
# TIP: run a full scan before capturing so every page has real data to display.
PAGES = [
    ("Home",                "01_home",              4.0),  # health ring + session strip + suggestions
    ("Troubleshoot",        "02_troubleshoot",      2.5),  # Sprint 3: 8 symptom tiles → correct tool
    ("Devices",             "03_devices",           3.5),  # Sprint 5: segments + health + device naming
    ("App Traffic",         "04_app_traffic",       3.5),  # Sprint 6: per-host traffic breakdown
    ("Network Map",         "05_network_map",       6.0),  # Sprint 6: Cytoscape.js interactive topology
    ("Service Diagnostics", "06_service_diag",      3.5),  # v2.0: streaming/gaming service probes
    ("Security Overview",   "07_security_overview", 3.5),  # aggregate security findings + grade
    ("Threat Intel",        "08_threat_intel",      3.5),  # AbuseIPDB lookup + risk context
    ("Speed Test",          "09_speed_test",        2.5),  # speed history + modem signal panel
    ("Protocol Visualizer", "10_protocol_viz",      3.0),  # animated ARP/DNS/TCP/DHCP/STP diagrams
    ("Lab Mode",            "11_lab_mode",          2.5),  # CompTIA N+ / CCNA guided exercises
    ("Geolocation Map",     "12_geo_map",           3.5),  # offline MaxMind map — no API key needed
]

# NOTE: the Network Map restores whatever layout was last saved, and a
# force-directed one collides and truncates node labels. Set it to Hierarchy +
# Fit by hand before capturing that page — driving those buttons from here was
# tried and reverted: pywinauto's child_window() does not exist on the UIAWrapper
# this script holds, and the failed clicks left focus on the map so the next four
# navigations silently no-opped and captured the map four more times.


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


def capture_window(hwnd: int, path: Path) -> tuple[float, tuple[int, int, int]]:
    rect = win32gui.GetWindowRect(hwnd)
    img = ImageGrab.grab(rect, all_screens=True)
    img.save(str(path))
    flat, colour = _content_uniformity(img)
    print(f"  saved -> {path.name}  ({img.size[0]}x{img.size[1]})")
    return flat, colour


# ── output verification ────────────────────────────────────────────────────────
#
# A screenshot that ships to the Microsoft Store is worth more scrutiny than a
# chaos-test interaction. Two failure modes produced a bad set before and neither
# raised: navigation silently no-opped (leaving the PREVIOUS page on screen, saved
# under the new page's filename), and a QWebEngineView page was captured before its
# renderer had painted (a uniform rectangle saved as a perfectly valid PNG).

# Fraction of the content region occupied by one colour before it reads as unpainted.
# A populated NetSentinel page is dense; even a mostly-empty one carries a table
# grid, card borders and a status bar. Measured on the real pages: ~0.35-0.75.
_BLANK_THRESHOLD = 0.92

_SAMPLE_W, _SAMPLE_H = 256, 144


def _content_uniformity(img) -> tuple[float, tuple[int, int, int]]:
    """Return (fraction occupied by the most common colour, that colour).

    Measures only the content region — right of the activity rail and below the
    header/breadcrumb strip — so chrome that paints correctly cannot mask an
    unpainted page body.
    """
    w, h = img.size
    region = img.convert("RGB").crop((int(w * 0.16), int(h * 0.18), w, h))
    # Downsample before counting: uniformity is scale-invariant and this keeps
    # the check to a few milliseconds on a 2048-wide grab.
    region = region.resize((_SAMPLE_W, _SAMPLE_H))
    counts = region.getcolors(_SAMPLE_W * _SAMPLE_H)
    if not counts:
        return 0.0, (0, 0, 0)
    count, colour = max(counts, key=lambda c: c[0])
    return count / float(_SAMPLE_W * _SAMPLE_H), colour


# Status-bar / hero-card fragments the app shows only while a scan is running.
# Capturing through one of these is what produced the shipped 01_home.png: a
# greyed-out Scan button and a "Devices 0" tile sitting next to a "15 devices"
# status bar, because the tiles had not been populated yet.
_BUSY_MARKERS = ("remaining", "scanning", "in progress", "scan in progress")


def wait_for_idle(app_win, timeout: float = 180.0) -> bool:
    """Block until nothing on screen reports a scan in progress.

    Returns True once idle, False if *timeout* elapsed first (the caller warns
    rather than aborting — a slow probe is not a reason to lose the whole run).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            texts = [t.window_text().lower()
                     for t in app_win.descendants(control_type="Text")]
        except Exception:
            return True  # cannot inspect — proceed rather than block the run
        busy = [t for t in texts if any(m in t for m in _BUSY_MARKERS)]
        if not busy:
            return True
        print(f"  waiting for scan to finish: {busy[0][:60]!r}")
        time.sleep(3.0)
    return False


def verify_page(app_win, label: str) -> str | None:
    """Return the breadcrumb text when it names *label*, else None.

    The breadcrumb strip above the content area reads "Section > Page", so it is
    the one on-screen element that states which page actually rendered. Returning
    None means "could not confirm" — the caller reports it rather than aborting,
    because a UIA read failing is not itself proof the navigation failed.
    """
    try:
        texts = [t.window_text() for t in app_win.descendants(control_type="Text")]
    except Exception as exc:
        print(f"  ! breadcrumb read failed ({exc.__class__.__name__}) — page unverified")
        return None
    crumbs = [t for t in texts if "›" in t]
    for crumb in crumbs:
        if label.lower() in crumb.lower():
            return crumb
    if crumbs:
        print(f"  ! breadcrumb says {crumbs[0]!r} — expected {label!r}")
    else:
        print(f"  ! no breadcrumb found — could not confirm {label!r}")
    return None


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

    # Type the full label — long enough to uniquely resolve in fuzzy match.
    # set_foreground=False from here on: type_keys() defaults to
    # set_foreground=True, which re-focuses app_win (the cached DASHBOARD
    # window) before sending keys. Ctrl+K just opened the command palette as
    # its own top-level window that already took real focus via its own
    # showEvent(); re-asserting focus on the dashboard here steals it
    # straight back, so the typed label and Enter land on the dashboard
    # instead of the palette and navigation silently no-ops.
    app_win.type_keys(label, with_spaces=True, pause=0.05, set_foreground=False)
    time.sleep(0.6)

    # Navigate
    app_win.type_keys("{ENTER}", pause=0.05, set_foreground=False)

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
        pages = [p for p in PAGES if p[1] == args.page]
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

        print("Waiting for any in-flight scan to finish...")
        if not wait_for_idle(main_win):
            print("  ! still busy after 180s — capturing anyway; check 01_home")
        else:
            print("  idle.")

        problems: list[str] = []
        for label, slug, wait in pages:
            print(f"\n-> {label}  (wait {wait}s after nav)")
            navigate(main_win, hwnd, label, wait)

            crumb = verify_page(main_win, label)
            if crumb is None:
                problems.append(f"{slug}: page not confirmed as {label!r}")

            flat, colour = capture_window(hwnd, out_dir / f"{slug}.png")
            if flat >= _BLANK_THRESHOLD:
                print(f"  ! content is {flat:.0%} one colour {colour} — looks unpainted")
                problems.append(
                    f"{slug}: content {flat:.0%} uniform {colour} — likely captured "
                    f"before the page finished painting"
                )

        print(f"\nDone. {len(pages)} screenshot(s) in:")
        print(f"  {out_dir}")

        if problems:
            print(f"\n{len(problems)} PROBLEM(S) — do not submit this set as-is:")
            for p in problems:
                print(f"  - {p}")
            print("\nRe-run the affected pages with --page <slug> once the app is idle.")
            sys.exit(1)
        print("\nAll pages verified: correct page on screen, content painted.")
    finally:
        _prevent_sleep_end()


if __name__ == "__main__":
    main()
