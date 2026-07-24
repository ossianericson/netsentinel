"""
minimize-restore-hwnd-trace.py — decides the mechanism behind the 2026-07-23
black/white-window-after-minimize/restore bug, with ZERO app-code changes.

The canonical repro (minimize-restore-black-window-repro.py) proved the symptom and
found, via UIA, that the stuck window exposes only 6 native-frame controls (Windows'
default TitleBar/System-menu/min-max-close scaffolding) instead of the real Dashboard
tree. The prior session's theory was "the WM_NCCALCSIZE subclass is lost across
minimize/restore." But losing only the subclass would bring the native titlebar back
while leaving the hundreds of Qt controls intact — it would NOT make the whole widget
tree vanish. So the theory is incomplete.

This script tests a sharper hypothesis: **Qt recreates the top-level HWND across the
native minimize/restore, leaving the OLD hwnd as a visible white zombie while the real
Qt content lives on a NEW hwnd** (shown or not). That single mechanism explains all of:
  - the vanished widget tree (UIA on the zombie sees only the native frame),
  - the failure of SWP_FRAMECHANGED / resize-nudge to repaint (Qt no longer renders
    to the zombie),
  - the "lost subclass" appearance (the subclass died with the old handle — exactly
    the QWebEngineView WinIdChange case, just triggered differently).

It answers three questions externally, per cycle:
  1. Does the primary hwnd VALUE change after restore?  (HWND recreation = smoking gun)
  2. How many top-level windows does the PID own, and what are their rects/styles/visibility?
     (a second large window appearing = the new Qt hwnd)
  3. Where did the Dashboard UIA tree go — dump the descendant count of EVERY top-level
     window of the PID, not just the largest.

Run:  python docs/spikes/minimize-restore-hwnd-trace.py
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import subprocess
import sys
import time
from pathlib import Path

from PIL import ImageGrab

REPO = Path(__file__).resolve().parent.parent.parent
SW_MINIMIZE = 6
SW_RESTORE = 9
MIN_W, MIN_H = 400, 300
GWL_STYLE = -16

user32 = ctypes.windll.user32
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowTextW.argtypes = [wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsHungAppWindow.argtypes = [wintypes.HWND]
user32.IsHungAppWindow.restype = wintypes.BOOL
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_long


def responsiveness(hwnd: int) -> str:
    """Is the window's owning thread processing messages? Distinguishes a hung main
    thread from an alive-but-not-repainting one."""
    hung = bool(user32.IsHungAppWindow(wintypes.HWND(hwnd)))
    WM_NULL = 0
    SMTO_ABORTIFHUNG = 0x0002
    res = ctypes.c_size_t(0)
    ok = user32.SendMessageTimeoutW(wintypes.HWND(hwnd), WM_NULL, 0, 0,
                                    SMTO_ABORTIFHUNG, 2000, ctypes.byref(res))
    pumped = ok != 0
    return f"IsHungAppWindow={int(hung)} WM_NULL_ack={int(pumped)}"

# Style bits we care about (native_chrome keeps all of WS_CAPTION|SYSMENU|THICKFRAME)
WS_VISIBLE = 0x10000000
WS_CAPTION = 0x00C00000
WS_MINIMIZE = 0x20000000


def _title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(wintypes.HWND(hwnd), buf, 256)
    return buf.value


def enum_pid_toplevels(target_pid: int) -> list[dict]:
    """Every top-level window owned by target_pid, with details. No size filter."""
    out: list[dict] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != target_pid:
            return True
        r = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(r))
        w, h = r.right - r.left, r.bottom - r.top
        style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
        out.append({
            "hwnd": int(hwnd),
            "rect": (r.left, r.top, r.right, r.bottom),
            "wh": (w, h),
            "visible": bool(user32.IsWindowVisible(hwnd)),
            "iconic": bool(user32.IsIconic(hwnd)),
            "ws_caption": bool(style & WS_CAPTION),
            "ws_visible_bit": bool(style & WS_VISIBLE),
            "title": _title(int(hwnd)),
        })
        return True

    user32.EnumWindows(_enum, 0)
    return out


def largest_visible(wins: list[dict]) -> dict | None:
    cands = [w for w in wins if w["visible"] and w["wh"][0] >= MIN_W and w["wh"][1] >= MIN_H]
    if not cands:
        return None
    cands.sort(key=lambda w: w["wh"][0] * w["wh"][1], reverse=True)
    return cands[0]


def client_rect_screen(hwnd: int) -> tuple[int, int, int, int] | None:
    if not user32.IsWindow(wintypes.HWND(hwnd)):
        return None
    r = wintypes.RECT()
    if not user32.GetClientRect(wintypes.HWND(hwnd), ctypes.byref(r)):
        return None
    pt = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(wintypes.HWND(hwnd), ctypes.byref(pt)):
        return None
    if r.right <= 0 or r.bottom <= 0:
        return None
    return (pt.x, pt.y, pt.x + r.right, pt.y + r.bottom)


def brightness(hwnd: int) -> float | None:
    rect = client_rect_screen(hwnd)
    if rect is None:
        return None
    img = ImageGrab.grab(bbox=rect).convert("L").resize((60, 40))
    px = list(img.getdata())
    return sum(px) / len(px)


def dump_windows(wins: list[dict], label: str) -> None:
    print(f"  [{label}] PID owns {len(wins)} top-level window(s):")
    for w in wins:
        print(f"    hwnd=0x{w['hwnd']:08x} wh={w['wh']} vis={int(w['visible'])} "
              f"iconic={int(w['iconic'])} cap={int(w['ws_caption'])} "
              f"title={w['title']!r}")


def uia_tree_counts(target_pid: int, wins: list[dict]) -> None:
    print("\nUIA descendant counts per top-level window (pixels aside):")
    try:
        from pywinauto import Desktop
        uia_wins = Desktop(backend="uia").windows()
        by_handle = {}
        for uw in uia_wins:
            try:
                by_handle[int(uw.handle)] = uw
            except Exception:
                continue
        for w in wins:
            uw = by_handle.get(w["hwnd"])
            if uw is None:
                print(f"  hwnd=0x{w['hwnd']:08x}: NOT found in UIA window list")
                continue
            try:
                desc = uw.descendants()
                print(f"  hwnd=0x{w['hwnd']:08x}: {len(desc)} UIA descendants "
                      f"(vis={int(w['visible'])} wh={w['wh']})")
                if len(desc) <= 20:
                    for d in desc:
                        try:
                            print(f"      {d.element_info.control_type:14s} "
                                  f"name={d.element_info.name!r}")
                        except Exception as exc:
                            print(f"      <err {exc}>")
            except Exception as exc:
                print(f"  hwnd=0x{w['hwnd']:08x}: UIA descendants() failed: {exc}")
    except Exception as exc:
        print(f"  UIA inspection unavailable: {exc}")


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass  # non-fatal — pre-8.1 only

    print("Launching NetSentinel from source...")
    proc = subprocess.Popen([sys.executable, str(REPO / "app.py")], cwd=str(REPO))

    primary = None
    deadline = time.time() + 60
    while time.time() < deadline and primary is None:
        time.sleep(1.0)
        primary = largest_visible(enum_pid_toplevels(proc.pid))
    if primary is None:
        print("FAILED: window never appeared")
        proc.kill()
        return 1

    print(f"Window found: hwnd=0x{primary['hwnd']:08x} pid={proc.pid}. Settling 8s...")
    time.sleep(8.0)

    wins0 = enum_pid_toplevels(proc.pid)
    dump_windows(wins0, "baseline")
    base = largest_visible(wins0)
    base_hwnd = base["hwnd"]
    b0 = brightness(base_hwnd)
    print(f"  baseline primary hwnd=0x{base_hwnd:08x} brightness={b0}")
    if b0 is None or b0 < 15.0:
        print("ABORT: untrustworthy baseline")
        proc.kill()
        return 3

    for i in range(1, 5):
        gap = 0.5 if i % 2 == 1 else 0.15
        h = base_hwnd
        # Always drive the CURRENT largest-visible window (mirrors the harness which
        # re-resolves foreground each iteration).
        cur = largest_visible(enum_pid_toplevels(proc.pid))
        if cur:
            h = cur["hwnd"]
        user32.ShowWindow(wintypes.HWND(h), SW_MINIMIZE)
        time.sleep(gap)
        user32.ShowWindow(wintypes.HWND(h), SW_RESTORE)
        time.sleep(gap)
        user32.SetForegroundWindow(wintypes.HWND(h))
        time.sleep(0.6)

        wins = enum_pid_toplevels(proc.pid)
        print(f"\n--- cycle {i} (drove hwnd=0x{h:08x}, gap={gap}s) ---")
        dump_windows(wins, f"cycle {i}")
        newp = largest_visible(wins)
        if newp:
            changed = newp["hwnd"] != base_hwnd
            b = brightness(newp["hwnd"])
            print(f"  primary now hwnd=0x{newp['hwnd']:08x} "
                  f"{'*** CHANGED from baseline ***' if changed else '(same handle)'} "
                  f"brightness={b}")

    # Final deep inspection: where did the tree go?
    final = enum_pid_toplevels(proc.pid)
    print("\n=== FINAL STATE ===")
    dump_windows(final, "final")
    fp = largest_visible(final)
    if fp:
        print(f"  responsiveness of primary 0x{fp['hwnd']:08x}: {responsiveness(fp['hwnd'])}")
    uia_tree_counts(proc.pid, final)

    proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
