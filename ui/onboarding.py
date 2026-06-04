"""
OnboardingOrchestrator — single-format, 9-step first-run onboarding.

Replaces WelcomeOverlay (modal slides) + GuidedTour (separate bar) with one
seamless experience:

  Layer 1 — Tour bar  : "Step N of 9 · [title] · [body]  [Next →]  [Skip]"
  Layer 2 — Spotlights: CoachMarkChain highlights specific widgets per step

All background scans (device scan, speed test, logger, grade) fire immediately
when the orchestrator starts so the user sees live data at every step.

Trigger:
  QSettings("ui/onboarding_v2_done") is False or absent.
  Called from dashboard._maybe_start_onboarding() after the window is shown.

Completion:
  Sets QSettings("tour/v1_done") and QSettings("ui/onboarding_v2_done") = True.
  Coach marks (home_pills, diagnosis, log_hub, devices, grade) then become eligible.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import QObject, QSettings, QTimer

if TYPE_CHECKING:
    from ui.dashboard import Dashboard


_SETTINGS_KEY = "ui/onboarding_v2_done"
_TOUR_KEY     = "tour/v1_done"


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class SpotlightSpec:
    title:  str
    body:   str
    target: Callable | None = None   # lambda returning a QWidget; None = centred


@dataclass
class OnboardingStep:
    nav_label:  str | None           # page to navigate to; None = stay put
    tour_title: str
    tour_body:  str
    spotlights: list[SpotlightSpec] = field(default_factory=list)
    auto_action: str | None = None   # method name on the orchestrator to call


# ── Step definitions ──────────────────────────────────────────────────────────

def _build_steps(d: "Dashboard") -> list[OnboardingStep]:
    """Build the 9-step sequence with widget-resolving lambdas bound to dashboard d."""

    def _w(attr: str):
        """Safely get an attribute from d; return None if absent or invisible."""
        def _resolve():
            w = d
            for part in attr.split("."):
                w = getattr(w, part, None)
                if w is None:
                    return None
            return w
        return _resolve

    return [
        # ── PHASE 1: App shell orientation (steps 1–4, no navigation) ─────────

        OnboardingStep(
            nav_label=None,
            tour_title="Step 1 of 9  ·  The navigation rail",
            tour_body="9 sections on the left — click any icon to expand its pages.",
            spotlights=[
                SpotlightSpec(
                    title="9 sections, all your tools",
                    body="Getting Started, Discover, Monitor, Reports, Analysis, "
                         "Automation, Security, Education, Extend — everything is here.",
                    target=_w("_nav_rail_panel"),
                ),
                SpotlightSpec(
                    title="Click to expand",
                    body="Each icon opens a flyout listing every page in that section. "
                         "Right-click any item to pin it to the top of the rail.",
                    target=_w("_nav_flyout"),
                ),
            ],
        ),

        OnboardingStep(
            nav_label=None,
            tour_title="Step 2 of 9  ·  Find anything instantly",
            tour_body="Press Ctrl+K to open the command palette — fuzzy-search all 60+ pages.",
            spotlights=[
                SpotlightSpec(
                    title="Command palette",
                    body="Type any page name, feature, or action. "
                         "Arrow keys to move, Enter to go. Esc to close.",
                    target=_w("_cmd_palette_btn"),
                ),
                SpotlightSpec(
                    title="Always know where you are",
                    body="The breadcrumb strip shows Section › Page. "
                         "Click the section name to jump back.",
                    target=_w("_breadcrumb_lbl"),
                ),
            ],
        ),

        OnboardingStep(
            nav_label=None,
            tour_title="Step 3 of 9  ·  Your live health indicator",
            tour_body="The status badge in the header reflects your network grade at a glance.",
            spotlights=[
                SpotlightSpec(
                    title="Live verdict",
                    body="Updates after every scan: Network Healthy, Issues Found, or No Data. "
                         "Click to jump straight to the diagnostic details.",
                    target=_w("_verdict_panel"),
                ),
                SpotlightSpec(
                    title="One-click scan",
                    body="Runs a full device discovery and grades your network in 60–90 seconds. "
                         "We already started one for you.",
                    target=_w("_header_scan_btn"),
                ),
            ],
        ),

        OnboardingStep(
            nav_label="Home",
            tour_title="Step 4 of 9  ·  Your home page",
            tour_body="Daily starting point — scan status, monitors, and what to do next.",
            spotlights=[
                SpotlightSpec(
                    title="Setup checklist",
                    body="Complete these steps once. The card disappears permanently "
                         "when all 6 are done — no clutter after setup.",
                    target=_w("_home_page._getting_started_card"),
                ),
                SpotlightSpec(
                    title="What to do next",
                    body="After each scan NetSentinel surfaces your 3–4 highest-priority "
                         "actions. Acted-on items don't reappear for 7 days.",
                    target=_w("_home_page._suggestions_frame"),
                ),
                SpotlightSpec(
                    title="Background monitors",
                    body="ARP Watch, Logger, DHCP, Storm — run silently in the background. "
                         "Green dot = active. Grey = off. Click to start.",
                    target=_w("_home_page._freshness_strip"),
                ),
            ],
        ),

        # ── PHASE 2: Feature pages (steps 5–9, live data already loading) ─────

        OnboardingStep(
            nav_label="Speed Test",
            tour_title="Step 5 of 9  ·  Speed Test",
            tour_body="Already running — every result is logged for ISP accountability.",
            auto_action="_auto_speed_test",
            spotlights=[
                SpotlightSpec(
                    title="Live gauge",
                    body="Shows download speed in real time as the test runs. "
                         "The needle moves — watch it while you read.",
                    target=_w("_speed_test_page._gauge"),
                ),
                SpotlightSpec(
                    title="Test history",
                    body="Every result is saved. Run weekly — build months of data "
                         "before disputing an ISP bill. Export as PDF.",
                    target=_w("_speed_test_page._hist_table"),
                ),
                SpotlightSpec(
                    title="Engine indicator",
                    body="Uses Ookla CLI if installed, then speedtest-cli, then "
                         "pure-Python. All three produce the same logged data.",
                    target=_w("_speed_test_page._engine_lbl"),
                ),
            ],
        ),

        OnboardingStep(
            nav_label="Network Grade",
            tour_title="Step 6 of 9  ·  Network Grade",
            tour_body="Your A–F score across 8 security and stability dimensions — already computing.",
            auto_action="_auto_grade",
            spotlights=[
                SpotlightSpec(
                    title="Your grade",
                    body="Click the ring to see the 8-dimension breakdown. "
                         "Low scores link directly to the page where you fix them.",
                    target=_w("_overview_page._grade_ring"),
                ),
                SpotlightSpec(
                    title="How is it calculated?",
                    body="Device risk, DNS stability, uptime, cert health, CVE exposure, "
                         "rogue detection, speed, and latency — all weighted.",
                    target=_w("_overview_page._grade_how_lbl"),
                ),
            ],
        ),

        OnboardingStep(
            nav_label="Network Logger",
            tour_title="Step 7 of 9  ·  Network Logger",
            tour_body="Already recording every 30 seconds — leave this running overnight.",
            auto_action="_auto_logger",
            spotlights=[
                SpotlightSpec(
                    title="Log Sources",
                    body="Toggle what gets recorded: RTT, jitter, DNS latency, "
                         "ARP events. Network RTT is the most valuable — already on.",
                    target=_w("_log_hub_page._sources_bar"),
                ),
                SpotlightSpec(
                    title="Activity Log",
                    body="Every logged event appears here in real time. "
                         "Filter by source or switch to History mode to review past sessions. "
                         "Outages are logged with start time and duration.",
                    target=_w("_log_hub_page._table"),
                ),
            ],
        ),

        OnboardingStep(
            nav_label="Hardware",
            tour_title="Step 8 of 9  ·  Hardware Integration",
            tour_body="The highest-value step — connect your router or modem for real device names and signal data.",
            spotlights=[
                SpotlightSpec(
                    title="Detected devices",
                    body="NetSentinel found compatible hardware on your network. "
                         "Click Add to connect it — takes 30 seconds.",
                    target=_w("_hardware_integration_page._hub_scroll"),
                ),
                SpotlightSpec(
                    title="What you get",
                    body="Real hostnames in Devices, live signal strength in Speed Test, "
                         "mesh topology in Network Map. Credentials stored in OS keychain.",
                    target=None,
                ),
            ],
        ),

        OnboardingStep(
            nav_label="Overview",
            tour_title="Step 9 of 9  ·  Overview",
            tour_body="Your home base — all monitors, today's alerts, and your grade in one place.",
            spotlights=[
                SpotlightSpec(
                    title="Your dashboard",
                    body="Each tile is a live monitor. Drag to reorder. "
                         "Click Edit Layout to add or remove tiles.",
                    target=_w("_overview_page._tile_container"),
                ),
                SpotlightSpec(
                    title="What's Wrong?",
                    body="Pick a symptom, get targeted findings in 30 seconds — "
                         "no need to know what ARP or STP mean.",
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
    Single-format first-run onboarding: tour bar + spotlight chain per step.

    Usage:
        orchestrator = OnboardingOrchestrator(dashboard)
        orchestrator.start()   # fires all background scans, shows step 1
    """

    def __init__(self, dashboard: "Dashboard") -> None:
        super().__init__(dashboard)
        self._dashboard = dashboard
        self._step = 0
        self._steps: list[OnboardingStep] = []
        self._chain_active = False

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self) -> None:
        if not should_show_onboarding():
            return
        self._steps = _build_steps(self._dashboard)
        self._step = 0
        self._fire_background_scans()
        self._connect_buttons()
        self._advance()

    # ── Background scans ──────────────────────────────────────────────────────

    def _fire_background_scans(self) -> None:
        """Start all scans immediately so data is ready by the time steps 5–9 show."""
        try:
            self._dashboard._start_full_scan()
        except Exception:
            pass
        QTimer.singleShot(500, self._auto_speed_test)
        QTimer.singleShot(1000, self._auto_logger)

    def _auto_speed_test(self) -> None:
        try:
            st = getattr(self._dashboard, "_speed_test_page", None)
            if st is None:
                return
            worker = getattr(st, "_worker", None)
            if worker and getattr(worker, "isRunning", lambda: False)():
                return
            if hasattr(st, "_run_test"):
                st._run_test()
        except Exception:
            pass

    def _auto_grade(self) -> None:
        try:
            overview = getattr(self._dashboard, "_overview_page", None)
            if overview:
                # Switch to tile grid immediately so user sees results, not the CTA
                if hasattr(overview, "_show_tiles"):
                    overview._show_tiles()
                if hasattr(overview, "set_scanning"):
                    overview.set_scanning(True)
                if hasattr(overview, "scan_requested"):
                    overview.scan_requested.emit()
                    return
            self._dashboard._start_full_scan()
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

        # Navigate
        if step.nav_label:
            self._dashboard._nav_rail_go_to(step.nav_label)

        # Auto-action (e.g. start speed test)
        if step.auto_action:
            action = getattr(self, step.auto_action, None)
            if callable(action):
                QTimer.singleShot(250, action)

        # Update tour bar
        self._update_bar(step)

        # Disable Next until spotlights complete (or immediately enable if none)
        self._set_next_enabled(False)
        if step.spotlights:
            # Small delay so navigation crossfade completes before spotlights show
            QTimer.singleShot(300, lambda s=step: self._run_spotlights(s))
        else:
            self._set_next_enabled(True)

    def _update_bar(self, step: OnboardingStep) -> None:
        total = len(self._steps)
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
            btn.setStyleSheet(
                btn.styleSheet()  # preserve existing style
            )
            opacity = "1.0" if enabled else "0.4"
            btn.setProperty("opacity", opacity)

    def _run_spotlights(self, step: OnboardingStep) -> None:
        win = self._dashboard.window()
        if not (win and win.isVisible()):
            self._set_next_enabled(True)
            return

        marks = []
        for i, sp in enumerate(step.spotlights):
            marks.append({
                "target": sp.target,
                "title":  sp.title,
                "body":   sp.body,
            })

        from ui.widgets.coach_mark import CoachMarkChain
        chain = CoachMarkChain(
            win,
            marks,
            on_done=lambda: self._set_next_enabled(True),
        )
        chain.start()

    def _on_next(self) -> None:
        self._step += 1
        self._advance()

    def _finish(self) -> None:
        mark_onboarding_done()
        bar = getattr(self._dashboard, "_tour_bar", None)
        if bar:
            bar.setVisible(False)
        self.deleteLater()
