"""Tests for ui/pages/lab_mode_page.py"""
from __future__ import annotations

import pytest

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _make_store(tmp_path):
    from modules.metric_store import MetricStore
    return MetricStore(db_path=tmp_path / "test.db")


@pytest.fixture
def page(tmp_path):
    from ui.pages.lab_mode_page import LabModePage
    store = _make_store(tmp_path)
    p = LabModePage(store=store)
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
    store.close()


_NET_INFO = {
    "gateway": "192.168.1.1",
    "gateway_mac": "aa:bb:cc:dd:ee:ff",
    "local_ips": [{"ip": "192.168.1.100"}],
    "dns_servers": ["8.8.8.8"],
}


@pytest.fixture
def visuals_page(tmp_path):
    """A page built with experimental/lab_visuals already on (RULE-EXP1)."""
    from PyQt6.QtCore import QSettings
    from ui.pages.lab_mode_page import LabModePage, _LAB_VISUALS_FLAG_KEY
    QSettings().setValue(_LAB_VISUALS_FLAG_KEY, True)
    store = _make_store(tmp_path)
    p = LabModePage(store=store)
    p.set_context(net_info=_NET_INFO, devices=[])
    yield p
    try:
        p.deleteLater()
    except RuntimeError:
        pass  # already deleted
    app = QApplication.instance()
    if app:
        for _ in range(3):
            app.processEvents()
    store.close()


def test_import():
    from ui.pages.lab_mode_page import LabModePage  # noqa: F401


def test_set_context_stores_values(page):
    diag = object()
    m2 = {"bpdus": []}
    page.set_context(net_info=_NET_INFO, devices=[{"ip": "192.168.1.5"}], diag_result=diag, m2_result=m2)
    assert page._net_info == _NET_INFO
    assert page._devices == [{"ip": "192.168.1.5"}]
    assert page._diag_result is diag
    assert page._m2_result is m2


def test_canvas_not_built_when_flag_off(page):
    """Default (flag off) runner must not build the canvas card at all."""
    assert getattr(page, "_lab_canvas", None) is None


def test_canvas_visible_on_scan_step_with_flag_on(visuals_page):
    from modules.lab_scenarios import get_scenario
    scenario = get_scenario("rogue_device")   # protocol="ARP", 2 steps
    assert scenario is not None
    visuals_page.show()
    visuals_page._start_scenario(scenario)
    assert visuals_page._lab_canvas is not None
    assert visuals_page._lab_canvas.isVisible()
    scene = visuals_page._lab_canvas._canvas._scene
    assert scene is not None
    assert len(scene.nodes) >= 1


def test_canvas_hidden_on_review_step_with_flag_on(visuals_page):
    from modules.lab_scenarios import get_scenario
    scenario = get_scenario("rogue_device")
    visuals_page.show()
    visuals_page._start_scenario(scenario)
    visuals_page._step_idx = 1   # review step: scan_type is None
    visuals_page._load_step()
    assert visuals_page._lab_canvas.isHidden()


def test_finishing_scenario_flips_picker_completion_state(page):
    """RULE-T7: finishing a lab must persist progress and update the picker
    card's completion badge + the overall 'N of total' strip (Phase L2)."""
    from PyQt6.QtCore import QSettings
    import json
    from modules.lab_scenarios import SCENARIOS, get_scenario

    scenario = get_scenario("rogue_device")
    page.show()
    assert page._picker is not None
    assert page._picker._badges[scenario.id].isHidden()

    page._on_start_requested(scenario)
    page._step_idx = len(scenario.steps) - 1
    page._load_step()
    page._finish_exercise()
    page._go_picker()   # QStackedWidget only reports isVisible() for the current page

    assert page._progress[scenario.id]["verdict"] == "PASS"
    assert page._picker._badges[scenario.id].isVisible()
    assert page._picker._progress_strip.text() == f"1 of {len(SCENARIOS)} complete"

    persisted = json.loads(QSettings().value("lab/progress", "{}", type=str))
    assert scenario.id in persisted


def test_scoreboard_panel_is_reachable(page):
    """The Scoreboard is panel index 3 inside the existing QStackedWidget —
    no new nav page, so reachability is proven by the stack's panel count."""
    assert page._stack.count() == 4
    assert page._scoreboard is not None


def test_finishing_scenario_refreshes_scoreboard(page):
    """RULE-T7: _finish_exercise() on a PASS must push the new state into the
    Scoreboard panel too, not just the picker (both read the same self._progress)."""
    from modules.lab_scenarios import get_scenario

    scenario = get_scenario("rogue_device")
    page.show()
    assert not page._scoreboard._medallions[scenario.id].is_earned()

    page._on_start_requested(scenario)
    page._step_idx = len(scenario.steps) - 1
    page._load_step()
    page._finish_exercise()

    assert page._scoreboard._medallions[scenario.id].is_earned()


def test_result_screen_shows_protocol_cross_sell_button(page):
    """Phase L3 — a completed lab with a protocol offers a one-click jump to
    its Protocol Visualizer animation via the existing explore_protocol signal."""
    from modules.lab_scenarios import get_scenario

    scenario = get_scenario("rogue_device")   # protocol="ARP"
    page.show()
    page._on_start_requested(scenario)
    page._step_idx = len(scenario.steps) - 1
    page._load_step()
    page._finish_exercise()

    assert page._result_viz_btn.isVisible()
    assert page._result_viz_btn.text() == "See how ARP works →"

    received = []
    page.explore_protocol.connect(received.append)
    page._result_viz_btn.click()
    assert received == ["ARP"]


def test_instantiation(page):
    assert page is not None


def test_has_inject_live_challenge(page):
    """Lab mode page must expose inject_live_challenge() for the Logger integration."""
    assert hasattr(page, "inject_live_challenge")
    assert callable(page.inject_live_challenge)


def test_inject_live_challenge_is_callable(page):
    """inject_live_challenge() must exist and be callable (Lab Mode ↔ Logger contract)."""
    assert callable(page.inject_live_challenge)
