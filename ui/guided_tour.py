"""
GuidedTour — non-modal 5-step first-run tour bar.

Fires automatically on first launch (tour/v2_done QSettings key).
Can be restarted from Settings → Advanced → "Restart guided tour".

Steps:
  1. What NetSentinel does — header bar
  2. Run your first scan — Scan button in header
  3. Understand results — Devices page
  4. Set up monitoring — Network Logger nav item
  5. Configure an alert — Notifications nav item
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMainWindow

_SETTINGS_KEY = "tour/v2_done"


class GuidedTour:
    """5-step introductory tour for first-time users."""

    @staticmethod
    def should_show() -> bool:
        return not QSettings("NetSentinel", "NetSentinel").value(
            _SETTINGS_KEY, False, type=bool
        )

    @staticmethod
    def mark_done() -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(_SETTINGS_KEY, True)

    @staticmethod
    def reset() -> None:
        QSettings("NetSentinel", "NetSentinel").setValue(_SETTINGS_KEY, False)

    def __init__(self, dashboard: QMainWindow) -> None:
        self._dash = dashboard

    def start(self) -> None:
        """Start the tour only if it has not been shown before."""
        if not self.should_show():
            return
        self._launch()

    def restart(self) -> None:
        """Force-restart the tour regardless of whether it was already shown."""
        self.reset()
        self._launch()

    def _launch(self) -> None:
        from ui.widgets.coach_mark import CoachMarkChain

        dash = self._dash

        def _done() -> None:
            self.mark_done()

        def _skipped() -> None:
            self.mark_done()

        def _header_target():
            return getattr(dash, "_header_bar", None) or dash

        def _scan_btn_target():
            return getattr(dash, "_header_scan_btn", None)

        def _devices_target():
            items = getattr(getattr(dash, "_nav_flyout", None), "_items", {})
            return items.get("Devices") or items.get("Network Map")

        def _logger_target():
            items = getattr(getattr(dash, "_nav_flyout", None), "_items", {})
            return items.get("Network Logger")

        def _notif_target():
            items = getattr(getattr(dash, "_nav_flyout", None), "_items", {})
            return items.get("Notifications")

        dash._guided_tour_chain = CoachMarkChain(
            dash,
            [
                {
                    "target":   _header_target,
                    "title":    "Step 1 of 5 — Welcome to NetSentinel",
                    "body":     "This is your network control centre. It scans every device, monitors uptime, and tells you when something is wrong — in plain English. Let's take a 60-second tour.",
                    "prefer_side": "bottom",
                },
                {
                    "target":   _scan_btn_target,
                    "title":    "Step 2 of 5 — Run your first scan",
                    "body":     "Click '▶ Scan' to discover every device on your network. NetSentinel checks for rogue devices, open ports, and security risks automatically.",
                    "prefer_side": "bottom",
                },
                {
                    "on_show":  lambda: dash._nav_rail_go_to("Devices"),
                    "delay_ms": 200,
                    "target":   _devices_target,
                    "title":    "Step 3 of 5 — Understand your results",
                    "body":     "Each row is a device. Colour-coded risk levels (red = high, amber = medium, green = clean) let you spot problems at a glance. Right-click any row for actions.",
                    "prefer_side": "right",
                },
                {
                    "on_show":  lambda: (
                        getattr(dash, "_nav_rail_toggle", lambda _: None)("Monitor"),
                    ),
                    "delay_ms": 300,
                    "target":   _logger_target,
                    "title":    "Step 4 of 5 — Set up continuous monitoring",
                    "body":     "The Network Logger records RTT, DNS latency, and outages in the background — even when you're not looking. Open it to enable sources and see the live activity log.",
                    "prefer_side": "right",
                },
                {
                    "on_show":  lambda: (
                        getattr(dash, "_nav_rail_toggle", lambda _: None)("Reports"),
                    ),
                    "delay_ms": 300,
                    "target":   _notif_target,
                    "title":    "Step 5 of 5 — Configure an alert",
                    "body":     "Go to Notifications to set up toast alerts, email, or a webhook. You'll be notified the moment a new device joins or an outage is detected.",
                    "prefer_side": "right",
                },
            ],
            on_done=_done,
            on_skip=_skipped,
        )
        dash._guided_tour_chain.start()
