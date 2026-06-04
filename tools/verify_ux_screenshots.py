"""
verify_ux_screenshots.py — Captures screenshots of key pages for H1-H10 UX verification.
Run: python tools/verify_ux_screenshots.py
Saves PNGs to tools/verify_screenshots/
"""
import sys
import os
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, QSettings
from PyQt6.QtGui import QPixmap

OUT_DIR = Path(__file__).parent / "verify_screenshots"
OUT_DIR.mkdir(exist_ok=True)

app = QApplication.instance() or QApplication(sys.argv)

# Mark first-run as done so welcome dialog doesn't block pages
qs = QSettings("NetSentinel", "NetSentinel")
qs.setValue("ui/first_run_done", True)
qs.setValue("tour/v1_done", True)
# Pre-dismiss all coach marks so they don't block page content in screenshots
for key in [
    "coach/home_pills_shown", "coach/log_hub_sources_shown",
    "coach/grade_shown", "coach/diagnosis_shown", "coach/devices_rightclick_shown",
]:
    qs.setValue(key, True)

print("Importing Dashboard...")
from ui.dashboard import Dashboard

print("Creating Dashboard...")
window = Dashboard()
window.resize(1400, 900)
window.show()

# Dismiss any lingering modal dialogs
app.processEvents()
for w in app.topLevelWidgets():
    if w is not window and w.isVisible():
        w.hide()

def grab(label: str):
    # Let the 80ms fade-out + 80ms fade-in crossfade animations complete
    for _ in range(5):
        app.processEvents()
    time.sleep(0.4)   # > 160ms animation total, with margin
    for _ in range(10):
        app.processEvents()
    px = window.grab()
    path = OUT_DIR / f"{label}.png"
    px.save(str(path))
    print(f"  Saved: {path}")

def run_checks():
    print("\n=== Available nav labels ===")
    labels = sorted(window._nav_label_to_widget.keys())
    for lbl in labels:
        print(f"  '{lbl}'")

    def go(label):
        window._nav_rail_go_to(label)

    print("\n=== Capturing screenshots ===")

    # 1. Home page
    print("1. Home page")
    # Find the Home label (strip flyout prefix chars)
    home_lbl = next((l for l in labels if "Home" in l and "Automation" not in l), "Home")
    go(home_lbl)
    app.processEvents()
    grab("01_home")

    def go_exact(label, n, shot):
        if label in labels:
            print(f"{n}. {label!r}")
            go(label)
        else:
            print(f"{n}. NOT FOUND: {label!r}")
        grab(shot)

    go_exact("Network Logger",   2, "02_log_hub")
    go_exact("What's Wrong?",    3, "03_diagnosis")
    go_exact("Overview",         4, "04_overview")
    go_exact("Devices",          5, "05_devices")
    go_exact("Speed Test",       6, "06_speed_test")
    go_exact("Network Timeline", 7, "07_timeline")
    go_exact("Geolocation Map",  8, "08_geo_map")

    print(f"\n✓ All screenshots saved to {OUT_DIR}")
    app.quit()

QTimer.singleShot(800, run_checks)
app.exec()
