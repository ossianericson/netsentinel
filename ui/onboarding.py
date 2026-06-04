"""
OnboardingOrchestrator — value-first 9-step first-run onboarding (Sprint H11).

Design principle: show value first, explain the shell second.
Steps 1-3 (old shell-orientation steps) deleted — nav rail / breadcrumb / health
badge are self-explanatory once the user has visited real pages with real data.

Step sequence:
  1  Overview       — scan fires here, user watches something happen
  2  Devices        — first "wow" moment: real device list
  3  Overview       — grade ring now populated, user sees a score
  4  Speed Test     — gauge already moving (started 500ms after step 1)
  5  Network Logger — already recording (started 1s after step 1)
  6  Hardware       — spotlight real detected hardware
  7  Home           — GettingStartedCard shows 3-4 ticks already done
  8  Home (stay)    — Ctrl+K spotlight — user has context from 5 pages
  9  Overview       — "Finish ✓", full tile grid with live data

Background scans fire via step 1's auto_action, not a pre-start:
  _start_full_scan()    — fires in step 1
  _auto_speed_test()    — fires 500ms after step 1
  _auto_logger()        — fires 1s after step 1

Steps 2-9 display results of those already-running scans.

Trigger:
  QSettings("ui/onboarding_v2_done") is False or absent.
  Called from dashboard._maybe_start_onboarding() after the window is shown.

Completion:
  Sets QSettings("tour/v1_done") and QSettings("ui/onboarding_v2_done") = True.
  Per-page coach marks (gated on tour/v1_done) become eligible after this.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QObject, QSettings, QTimer

if TYPE_CHECKING:
    from ui.dashboard import Dashboard


_SETTINGS_KEY = "ui/onboarding_v2_done"
_TOUR_KEY     = "tour/v1_done"

# Delay (ms) from step 1 auto_action before background scans fire
_SPEED_TEST_DELAY = 500
_LOGGER_DELAY     = 1000
# Delay (ms) after navigation before spotlight chain starts
_SPOTLIGHT_DELAY  = 350


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class SpotlightSpec:
    title:  str
    body:   str
    target: Callable | None = None   # lambda returning a QWidget; None = centred


@dataclass
class OnboardingStep:
    nav_label:   str | None              # page to navigate to; None = stay put
    tour_title:  str
    tour_body:   str
    spotlights:  list[SpotlightSpec] = field(default_factory=list)
    auto_action: str | None = None       # method name on the orchestrator to call
    next_enabled_immediately: bool = False  # skip spotlight gating for this step


# ── Step definitions ──────────────────────────────────────────────────────────

def _build_steps(d: "Dashboard") -> list[OnboardingStep]:
    """Build the 9-step value-first sequence with widget-resolving lambdas."""

    def _w(attr: str):
        """Safely resolve a dotted attribute path on d; returns None if missing."""
        def _resolve():
            obj = d
            for part in attr.split("."):
                obj = getattr(obj, part, None)
                if obj is None:
                    return None
            return obj
        return _resolve

    return [
        # ── Step 1: Scan starts here ─────────────────────────────────────────
        OnboardingStep(
            nav_label="Overview",
            tour_title="Step 1 of 9  ·  Scanning your network",
            tour_body=(
                "Finding every device right now — routers, phones, smart speakers, "
                "everything. Takes 30–60 seconds. Watch the tiles populate."
            ),
            auto_action="_step1_fire_scans",
            spotlights=[
                SpotlightSpec(
                    title="One-click scan",
                    body=(
                        "Runs full device discovery, grades your network A–F, and "
                        "records a baseline — all at once. Already running."
                    ),
                    target=_w("_header_scan_btn"),
                ),
            ],
        ),

        # ── Step 2: Devices — first tangible result ──────────────────────────
        OnboardingStep(
            nav_label="Devices",
            tour_title="Step 2 of 9  ·  Your network inventory",
            tour_body=(
                "Every device found on your network is listed here. "
                "Unknown devices in red are new arrivals — could be a guest or an intruder."
            ),
            spotlights=[
                SpotlightSpec(
                    title="Device list",
                    body=(
                        "MAC address, OUI vendor, IP, hostname, and risk level. "
                        "Right-click any row to label a device or check its open ports."
                    ),
                    target=_w("_inventory_page._devices_table"),
                ),
                SpotlightSpec(
                    title="Risk filter",
                    body=(
                        "Click 'Unknown' to filter to new, unrecognised devices. "
                        "Connect hardware in step 6 to get real hostnames instead of MACs."
                    ),
                    target=_w("_inventory_page._filter_bar"),
                ),
            ],
        ),

        # ── Step 3: Overview — grade ring now populated ──────────────────────
        OnboardingStep(
            nav_label="Overview",
            tour_title="Step 3 of 9  ·  Your network grade",
            tour_body=(
                "Scored A–F across 8 dimensions. Click the ring to see exactly "
                "which dimension is dragging your score down — and how to fix it."
            ),
            spotlights=[
                SpotlightSpec(
                    title="Grade ring",
                    body=(
                        "Click the ring for the full breakdown: device risk, "
                        "DNS stability, uptime, cert health, CVE exposure, rogue "
                        "detection, speed, and latency."
                    ),
                    target=_w("_overview_page._grade_ring"),
                ),
            ],
        ),

        # ── Step 4: Speed Test — gauge already moving ────────────────────────
        OnboardingStep(
            nav_label="Speed Test",
            tour_title="Step 4 of 9  ·  Speed Test",
            tour_body=(
                "Already running — the gauge is live. "
                "Every result is saved. Build months of history before disputing an ISP bill."
            ),
            spotlights=[
                SpotlightSpec(
                    title="Live gauge",
                    body=(
                        "Watch the needle while you read. Result saves automatically "
                        "with timestamp, server, and engine used."
                    ),
                    target=_w("_speed_test_page._gauge"),
                ),
                SpotlightSpec(
                    title="Test history",
                    body=(
                        "Click any row to see the full result including modem signal "
                        "data if hardware is connected. Export as PDF for ISP tickets."
                    ),
                    target=_w("_speed_test_page._hist_table"),
                ),
            ],
        ),

        # ── Step 5: Network Logger — already recording ───────────────────────
        OnboardingStep(
            nav_label="Network Logger",
            tour_title="Step 5 of 9  ·  Network Logger",
            tour_body=(
                "Recording RTT and DNS every 30 seconds — already running. "
                "Leave it on overnight and come back to see stability trends and any outages."
            ),
            spotlights=[
                SpotlightSpec(
                    title="Log Sources",
                    body=(
                        "Network RTT is on — it's the most valuable source. "
                        "Catches micro-outages your ISP won't admit to. "
                        "Enable DNS Latency to also track name resolution time."
                    ),
                    target=_w("_log_hub_page._sources_bar"),
                ),
                SpotlightSpec(
                    title="Activity Log",
                    body=(
                        "Every ping appears here in real time. Jitter = RTT variance. "
                        "Consecutive failures are grouped as outages with start time "
                        "and duration — exportable as evidence."
                    ),
                    target=_w("_log_hub_page._table"),
                ),
            ],
        ),

        # ── Step 6: Hardware — highest-value optional step ───────────────────
        OnboardingStep(
            nav_label="Hardware",
            tour_title="Step 6 of 9  ·  Hardware Integration",
            tour_body=(
                "Connect your router or modem to unlock real device names and signal data. "
                "Credentials stored in the OS keychain — never in a file."
            ),
            spotlights=[
                SpotlightSpec(
                    title="Detected hardware",
                    body=(
                        "NetSentinel found compatible devices on your network. "
                        "Click Add next to any card — takes 30 seconds. "
                        "You'll get real hostnames, signal strength, and mesh topology."
                    ),
                    target=_w("_hardware_integration_page._hub_scroll"),
                ),
            ],
        ),

        # ── Step 7: Home — GettingStartedCard shows progress ─────────────────
        OnboardingStep(
            nav_label="Home",
            tour_title="Step 7 of 9  ·  Home — your starting point",
            tour_body=(
                "Your daily launching pad. The checklist shows what you've already done "
                "— scan and logger are ticked. Return here after any restart."
            ),
            spotlights=[
                SpotlightSpec(
                    title="Setup checklist",
                    body=(
                        "Steps you've already completed are ticked. "
                        "The card disappears permanently when all 6 are done — "
                        "no clutter after setup."
                    ),
                    target=_w("_home_page._getting_started_card"),
                ),
                SpotlightSpec(
                    title="What to do next",
                    body=(
                        "After each scan, NetSentinel surfaces your 3–4 highest-priority "
                        "actions. Acted-on items won't reappear for 7 days."
                    ),
                    target=_w("_home_page._suggestions_frame"),
                ),
            ],
        ),

        # ── Step 8: Ctrl+K — now the user has context ────────────────────────
        OnboardingStep(
            nav_label=None,   # stay on Home
            tour_title="Step 8 of 9  ·  Find anything instantly",
            tour_body=(
                "You've just visited 5 pages. Press Ctrl+K to jump back to any of them "
                "— or to any of the 60+ pages — without touching the sidebar."
            ),
            next_enabled_immediately=True,
            spotlights=[
                SpotlightSpec(
                    title="Command palette  Ctrl+K",
                    body=(
                        "Type 'Devices', 'Grade', 'Logger' — anything. "
                        "Arrow keys + Enter. Esc to close. "
                        "Right-click any sidebar item to pin it to the top."
                    ),
                    target=_w("_cmd_palette_btn"),
                ),
            ],
        ),

        # ── Step 9: Overview — full tile grid with live data ─────────────────
        OnboardingStep(
            nav_label="Overview",
            tour_title="Step 9 of 9  ·  Overview — your home base",
            tour_body=(
                "All monitors, today's alerts, and your grade in one place. "
                "Drag tiles to reorder. Click Edit Layout to add or remove tiles."
            ),
            spotlights=[
                SpotlightSpec(
                    title="Live tile dashboard",
                    body=(
                        "Each tile updates automatically. Grade tile shows your score. "
                        "Stability tile shows RTT trends from the logger running since step 5."
                    ),
                    target=_w("_overview_page._tile_container"),
                ),
                SpotlightSpec(
                    title="What's Wrong?",
                    body=(
                        "Something not right? Pick a symptom — slow internet, "
                        "dropped connection, unknown device. "
                        "Targeted checks in 30 seconds. No technical knowledge needed."
                    ),
                    target=_w("_overview_page._whats_wrong_btn"),
                ),
            ],
        ),
    ]


# ── Public helpers ────────────────────────────────────────────────────────────

def should_show_onboarding() -> bool:
    qs = QSettings("NetSentinel", "NetSentinel")
    return not qs.value(_SETTINGS_KEY, False, type=bool)


def mark_onboarding_done() -> None:
    qs = QSettings("NetSentinel", "NetSentinel")
    qs.setValue(_SETTINGS_KEY, True)
    qs.setValue(_TOUR_KEY, True)


# ── Main class ────────────────────────────────────────────────────────────────

class OnboardingOrchestrator(QObject):
    """
    Value-first 9-step onboarding: tour bar + per-step spotlight chain.

    Scan fires in step 1. Speed test fires 500ms later. Logger fires 1s later.
    Steps 2–9 show results of those already-running scans.
    No spotlights fire during pre-step setup — every spotlight is tied to real data.

    Usage:
        orchestrator = OnboardingOrchestrator(dashboard)
        orchestrator.start()
    """

    def __init__(self, dashboard: "Dashboard") -> None:
        super().__init__(dashboard)
        self._dashboard = dashboard
        self._step = 0
        self._steps: list[OnboardingStep] = []

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not should_show_onboarding():
            return
        self._steps = _build_steps(self._dashboard)
        self._step = 0
        self._connect_buttons()
        self._advance()

    # ── Background scan triggers ──────────────────────────────────────────────

    def _step1_fire_scans(self) -> None:
        """Called as step 1's auto_action. Fires all background work."""
        try:
            self._dashboard._start_full_scan()
        except Exception:
            pass
        QTimer.singleShot(_SPEED_TEST_DELAY, self._auto_speed_test)
        QTimer.singleShot(_LOGGER_DELAY,     self._auto_logger)

    def _auto_speed_test(self) -> None:
        try:
            st = getattr(self._dashboard, "_speed_test_page", None)
            if st is None:
                return
            worker = getattr(st, "_worker", None)
            if worker and getattr(worker, "isRunning", lambda: False)():
                return   # already running
            if hasattr(st, "_run_test"):
                st._run_test()
        except Exception:
            pass

    def _auto_logger(self) -> None:
        try:
            log = getattr(self._dashboard, "_log_hub_page", None)
            if log and hasattr(log, "show_network_log"):
                log.show_network_log()
        except Exception:
            pass

    # ── Step sequencing ───────────────────────────────────────────────────────

    def _connect_buttons(self) -> None:
        next_btn = getattr(self._dashboard, "_tour_next_btn", None)
        skip_btn = getattr(self._dashboard, "_tour_skip_btn", None)
        if next_btn:
            try:
                next_btn.clicked.disconnect()
            except Exception:
                pass
            next_btn.clicked.connect(self._on_next)
        if skip_btn:
            try:
                skip_btn.clicked.disconnect()
            except Exception:
                pass
            skip_btn.clicked.connect(self._finish)

    def _advance(self) -> None:
        if self._step >= len(self._steps):
            self._finish()
            return

        step = self._steps[self._step]

        # Navigate first so page is loading while we update the bar
        if step.nav_label:
            self._dashboard._nav_rail_go_to(step.nav_label)

        # Fire auto-action (e.g. start scan on step 1)
        if step.auto_action:
            action = getattr(self, step.auto_action, None)
            if callable(action):
                QTimer.singleShot(150, action)

        # Update tour bar text
        self._update_bar(step)

        # Gate Next → until spotlight chain finishes (or skip gating if flagged)
        self._set_next_enabled(False)
        if not step.spotlights or step.next_enabled_immediately:
            self._set_next_enabled(True)
        else:
            QTimer.singleShot(_SPOTLIGHT_DELAY,
                              lambda s=step: self._run_spotlights(s))

    def _update_bar(self, step: OnboardingStep) -> None:
        total   = len(self._steps)
        is_last = self._step == total - 1

        lbl = getattr(self._dashboard, "_tour_step_lbl", None)
        if lbl:
            lbl.setText(step.tour_title)

        body = getattr(self._dashboard, "_tour_body_lbl", None)
        if body:
            body.setText(step.tour_body)

        btn = getattr(self._dashboard, "_tour_next_btn", None)
        if btn:
            btn.setText("Finish  ✓" if is_last else "Next  →")

        bar = getattr(self._dashboard, "_tour_bar", None)
        if bar:
            bar.setVisible(True)

    def _set_next_enabled(self, enabled: bool) -> None:
        btn = getattr(self._dashboard, "_tour_next_btn", None)
        if btn:
            btn.setEnabled(enabled)

    def _run_spotlights(self, step: OnboardingStep) -> None:
        win = self._dashboard.window() if hasattr(self._dashboard, "window") else None
        if not (win and win.isVisible()):
            self._set_next_enabled(True)
            return

        marks = [
            {"target": sp.target, "title": sp.title, "body": sp.body}
            for sp in step.spotlights
        ]

        try:
            from ui.widgets.coach_mark import CoachMarkChain
            chain = CoachMarkChain(
                win,
                marks,
                on_done=lambda: self._set_next_enabled(True),
            )
            chain.start()
        except Exception:
            # If CoachMarkChain fails (e.g. target widget not found), don't block
            self._set_next_enabled(True)

    def _on_next(self) -> None:
        self._step += 1
        self._advance()

    def _finish(self) -> None:
        mark_onboarding_done()
        bar = getattr(self._dashboard, "_tour_bar", None)
        if bar:
            bar.setVisible(False)
        self.deleteLater()
