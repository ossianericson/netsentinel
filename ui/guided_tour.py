"""
GuidedTour — non-modal guided first-run tour bar.

Shown after the first scan completes when both conditions are true:
  - QSettings("ui/first_run_done") is True (welcome overlay was completed)
  - QSettings("tour/v1_done") is False or absent

The tour attaches to the Dashboard instance and drives the pre-built
_tour_bar / _tour_step_lbl / _tour_body_lbl / _tour_next_btn / _tour_skip_btn
widgets created in ui/tabs.py.

Four steps:
  1  Devices    — Your inventory
  2  Overview   — Your network score
  3  Log Hub    — Leave this running  (auto-enables Network RTT source)
  4  Overview   — The full picture    (final step)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QSettings

if TYPE_CHECKING:
    from ui.dashboard import Dashboard   # avoid circular import at runtime


_TOUR_KEY      = "tour/v1_done"
_FIRST_RUN_KEY = "ui/first_run_done"


# ── Step definitions ──────────────────────────────────────────────────────────

@dataclass
class _TourStep:
    nav_label: str
    title:     str
    body:      str


_STEPS: list[_TourStep] = [
    _TourStep(
        nav_label="Devices",
        title="Your inventory",
        body=(
            "Every device on your network is listed here. "
            "Look for Unknown devices — they are new arrivals."
        ),
    ),
    _TourStep(
        nav_label="Overview",
        title="Your network score",
        body=(
            "NetSentinel grades your network A–F across 8 dimensions. "
            "Low scores have one-click remediation."
        ),
    ),
    _TourStep(
        nav_label="Log Hub",
        title="Leave this running",
        body=(
            "The Network Logger records RTT, jitter and DNS every 30 seconds. "
            "Leave it on and come back tomorrow for stability insights."
        ),
    ),
    _TourStep(
        nav_label="Overview",
        title="The full picture",
        body=(
            "Overview shows all active monitors, today’s alerts, "
            "and your running grade. This is your home base."
        ),
    ),
]


# ── Public helpers ────────────────────────────────────────────────────────────

def should_show_tour() -> bool:
    """Return True if the guided tour should run on next scan completion."""
    qs = QSettings("NetSentinel", "NetSentinel")
    return (
        qs.value(_FIRST_RUN_KEY, False, type=bool)
        and not qs.value(_TOUR_KEY, False, type=bool)
    )


def mark_tour_done() -> None:
    """Persist that the guided tour has been completed or skipped."""
    QSettings("NetSentinel", "NetSentinel").setValue(_TOUR_KEY, True)


# ── Main class ────────────────────────────────────────────────────────────────

class GuidedTour(QObject):
    """
    Drives the first-run guided tour.

    Attach to a Dashboard instance; call start() after the first scan returns
    devices.  The tour bar widgets must already exist on the dashboard (built by
    TabBuilderMixin._build_content_area() in ui/tabs.py).
    """

    def __init__(self, dashboard: "Dashboard") -> None:
        super().__init__(dashboard)
        self._dashboard = dashboard
        self._step: int = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not should_show_tour():
            return
        self._step = 0
        self._connect_buttons()
        self._navigate_and_show()

    # ── Internal ───────────────────────────────────────────────────────────────

    def _connect_buttons(self) -> None:
        """Connect tour bar buttons, clearing any previous connections first."""
        next_btn = getattr(self._dashboard, "_tour_next_btn", None)
        skip_btn = getattr(self._dashboard, "_tour_skip_btn", None)
        if next_btn is not None:
            try:
                next_btn.clicked.disconnect()
            except Exception:
                pass
            next_btn.clicked.connect(self._on_next)
        if skip_btn is not None:
            try:
                skip_btn.clicked.disconnect()
            except Exception:
                pass
            skip_btn.clicked.connect(self._on_skip)

    def _navigate_and_show(self) -> None:
        step = _STEPS[self._step]
        self._dashboard._nav_rail_go_to(step.nav_label)
        if step.nav_label == "Log Hub":
            self._auto_enable_rtt()
        self._update_bar()

    def _update_bar(self) -> None:
        step  = _STEPS[self._step]
        total = len(_STEPS)
        is_last = self._step == total - 1

        lbl = getattr(self._dashboard, "_tour_step_lbl", None)
        if lbl is not None:
            lbl.setText(f"Step {self._step + 1} of {total}  ·  {step.title}")

        body = getattr(self._dashboard, "_tour_body_lbl", None)
        if body is not None:
            body.setText(step.body)

        btn = getattr(self._dashboard, "_tour_next_btn", None)
        if btn is not None:
            btn.setText("Finish  ✓" if is_last else "Next  →")

        bar = getattr(self._dashboard, "_tour_bar", None)
        if bar is not None:
            bar.setVisible(True)

    def _on_next(self) -> None:
        self._step += 1
        if self._step >= len(_STEPS):
            self._finish()
        else:
            self._navigate_and_show()

    def _on_skip(self) -> None:
        self._finish()

    def _finish(self) -> None:
        mark_tour_done()
        bar = getattr(self._dashboard, "_tour_bar", None)
        if bar is not None:
            bar.setVisible(False)
        self.deleteLater()

    def _auto_enable_rtt(self) -> None:
        """Auto-enable Network RTT source on the Log Hub page."""
        try:
            log_page = getattr(self._dashboard, "_log_hub_page", None)
            if log_page is None:
                return
            if hasattr(log_page, "show_network_log"):
                log_page.show_network_log()
        except Exception:
            pass
