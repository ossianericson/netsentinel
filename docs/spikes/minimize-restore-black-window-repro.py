"""
minimize-restore-black-window-repro.py — live repro for the 2026-07-23 black-window report.

Hypothesis under test (see /debug session, 2026-07-23 evening):
  monkey_test.py's "win+down" chaos action (real Win+Down keystroke) minimizes the
  main window whenever it is NOT currently maximized (native OS behaviour). The
  harness's own focus-reclaim path (_force_foreground / _escalate_app_reclaim) then
  calls ShowWindow(hwnd, SW_RESTORE) -- sometimes preceded by its own
  ShowWindow(SW_MINIMIZE) -- to bring the window back. On this app's real-but-custom-
  chrome window (ui/native_chrome.py, WM_NCCALCSIZE-based), we suspect the client
  area does not get a full repaint across that iconic -> restored transition, so it
  comes back showing a stale/black backbuffer until some unrelated later repaint
  (e.g. opening the Ctrl+K command palette) forces one.

This script drives ONLY the minimize/restore transition directly via ctypes
ShowWindow, isolated from every other wild-mode action, and measures how dark the
window's client area is before vs. after each cycle.

Gotcha fixed after the first two attempts: EnumWindows found a match by title prefix
alone, which briefly matches a transient window during startup (dead by the time it
was measured -- IsWindow() == False, GetLastError() == 1400
ERROR_INVALID_WINDOW_HANDLE). Fixed by matching on the launched subprocess's PID and
a minimum size, and by re-resolving fresh via PID before every measurement instead of
trusting a cached handle.
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
MIN_W, MIN_H = 400, 300   # excludes splash/tooltip transients

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
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL


def find_window_by_pid(target_pid: int) -> int:
    """Return the largest visible top-level window owned by target_pid, or 0."""
    candidates: list[tuple[int, int, int]] = []   # (area, hwnd)

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != target_pid:
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w >= MIN_W and h >= MIN_H:
            candidates.append((w * h, int(hwnd)))
        return True

    user32.EnumWindows(_enum, 0)
    if not candidates:
        return 0
    candidates.sort(reverse=True)
    return candidates[0][1]


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


def mean_brightness(rect: tuple[int, int, int, int]) -> float:
    img = ImageGrab.grab(bbox=rect)
    img = img.convert("L").resize((60, 40))
    pixels = list(img.getdata())
    return sum(pixels) / len(pixels)


def main() -> int:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        pass  # non-fatal — pre-8.1 systems only; coords fall back to virtualized

    print("Launching NetSentinel from source...")
    proc = subprocess.Popen([sys.executable, str(REPO / "app.py")], cwd=str(REPO))

    hwnd = 0
    deadline = time.time() + 60
    while time.time() < deadline and not hwnd:
        time.sleep(1.0)
        hwnd = find_window_by_pid(proc.pid)
    if not hwnd:
        print("FAILED: window never appeared")
        proc.kill()
        return 1

    print(f"Window found: hwnd=0x{hwnd:x} (pid={proc.pid}). Settling 8s for startup paint...")
    time.sleep(8.0)

    def measure(label: str) -> float | None:
        # Re-resolve by PID every time -- never trust a cached handle across a
        # minimize/restore cycle (the whole point of this rewrite).
        h = find_window_by_pid(proc.pid)
        if not h:
            print(f"  [{label}] window not found by PID re-scan")
            return None
        rect = client_rect_screen(h)
        if rect is None:
            print(f"  [{label}] hwnd=0x{h:x} client_rect_screen failed")
            return None
        b = mean_brightness(rect)
        print(f"  [{label}] hwnd=0x{h:x} rect={rect} brightness={b:.1f}")
        return b

    baseline = measure("baseline")
    if baseline is None or baseline < 15.0:
        print("ABORT: could not get a trustworthy non-black baseline reading — "
              "the window-finding logic itself is still not reliable; not safe "
              "to interpret any 'black' result below as real.")
        proc.kill()
        return 3

    results = []
    for i in range(1, 9):
        h = find_window_by_pid(proc.pid)
        if not h:
            print(f"cycle {i}: window not found, skipping")
            continue
        if i % 2 == 1:
            mode = "slow (0.5s gap, like win+down -> later restore)"
            gap = 0.5
        else:
            mode = "fast (0.15s gap, like _escalate_app_reclaim)"
            gap = 0.15
        user32.ShowWindow(wintypes.HWND(h), SW_MINIMIZE)
        time.sleep(gap)
        user32.ShowWindow(wintypes.HWND(h), SW_RESTORE)
        time.sleep(gap)
        user32.SetForegroundWindow(wintypes.HWND(h))
        time.sleep(0.6)   # let any repaint settle before measuring

        brightness = measure(f"cycle {i} [{mode}]")
        is_black = brightness is not None and brightness < 15.0
        is_notable = is_black or (brightness is not None and brightness > 200.0)
        results.append((i, mode, brightness, is_black))
        if is_notable:
            shot = REPO / "docs" / "spikes" / f"black-window-repro-cycle{i}.png"
            ImageGrab.grab().save(str(shot))
            tag = "BLACK" if is_black else "WHITE/BRIGHT"
            print(f"  *** {tag} *** screenshot saved: {shot}")

    black_count = sum(1 for _, _, _, b in results if b)
    print(f"\n{black_count}/{len(results)} cycles produced a black client area "
          f"(baseline was {baseline:.1f}).")

    # If still stuck (blank/white/black), try recovery techniques one at a time
    # against the SAME stuck window, to find what actually forces a real redraw.
    last_brightness = results[-1][2] if results else None
    stuck = last_brightness is not None and (last_brightness < 15.0 or last_brightness > 200.0)
    if stuck:
        h = find_window_by_pid(proc.pid)
        print(f"\nStill stuck (brightness={last_brightness:.1f}). Trying recovery techniques...")

        print("Recovery attempt 1: SetWindowPos(SWP_FRAMECHANGED)")
        SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x2, 0x1, 0x4, 0x20
        user32.SetWindowPos(wintypes.HWND(h), None, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        time.sleep(0.6)
        b = measure("after SWP_FRAMECHANGED")
        if b is not None and 15.0 <= b <= 200.0:
            print(f"  RECOVERED (brightness={b:.1f})")
        else:
            print(f"  still stuck (brightness={b})")

            print("Recovery attempt 2: tiny resize nudge (w-1, w) via SetWindowPos")
            r = wintypes.RECT()
            user32.GetWindowRect(wintypes.HWND(h), ctypes.byref(r))
            w, ht = r.right - r.left, r.bottom - r.top
            user32.SetWindowPos(wintypes.HWND(h), None, 0, 0, w - 1, ht,
                                 SWP_NOMOVE | SWP_NOZORDER)
            time.sleep(0.2)
            user32.SetWindowPos(wintypes.HWND(h), None, 0, 0, w, ht,
                                 SWP_NOMOVE | SWP_NOZORDER)
            time.sleep(0.6)
            b2 = measure("after resize nudge")
            if b2 is not None and 15.0 <= b2 <= 200.0:
                print(f"  RECOVERED (brightness={b2:.1f})")
            else:
                print(f"  still stuck (brightness={b2})")

        # Distinguish "widgets alive, just not painting" from "widget tree
        # actually collapsed" -- UIA reads the accessible tree, not pixels, so
        # it sees real structure even on a visually blank window.
        print("\nInspecting UIA tree of the stuck window (pixels aside)...")
        try:
            from pywinauto import Desktop
            wins = Desktop(backend="uia").windows()
            target = None
            for w in wins:
                try:
                    if int(w.handle) == h:
                        target = w
                        break
                except Exception:
                    continue
            if target is None:
                print("  UIA could not find the window at all")
            else:
                descendants = target.descendants()
                print(f"  UIA descendant count: {len(descendants)}")
                for d in descendants[:15]:
                    try:
                        r = d.rectangle()
                        print(f"    {d.element_info.control_type:15s} "
                              f"name={d.element_info.name!r:30s} rect={r}")
                    except Exception as exc:
                        print(f"    <error reading control: {exc}>")
        except Exception as exc:
            print(f"  UIA inspection failed: {exc}")

    proc.kill()
    return 0 if black_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
