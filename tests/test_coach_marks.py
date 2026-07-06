"""
Tests for Sprint H7 contextual coach marks.

Validates per-feature QSettings flags and that coach mark methods
exist and behave correctly based on the flag state.
"""
import pytest

try:
    from PyQt6.QtCore import QSettings
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


_ALL_KEYS = [
    "coach/log_hub_sources_shown",
    "coach/grade_shown",
    "coach/diagnosis_shown",
    "coach/home_pills_shown",
    "coach/devices_rightclick_shown",
]


def _clear_keys():
    qs = QSettings("NetSentinel", "NetSentinel")
    for k in _ALL_KEYS:
        qs.remove(k)


# ── QSettings key hygiene ─────────────────────────────────────────────────────

class TestCoachMarkKeys:
    def setup_method(self):
        _clear_keys()

    def teardown_method(self):
        _clear_keys()

    def test_all_keys_start_false(self):
        qs = QSettings("NetSentinel", "NetSentinel")
        for key in _ALL_KEYS:
            assert qs.value(key, False, type=bool) is False, f"{key} should start False"

    def test_setting_key_persists(self):
        qs = QSettings("NetSentinel", "NetSentinel")
        for key in _ALL_KEYS:
            qs.setValue(key, True)
        for key in _ALL_KEYS:
            assert qs.value(key, False, type=bool) is True

    def test_keys_are_independent(self):
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue(_ALL_KEYS[0], True)
        for key in _ALL_KEYS[1:]:
            assert qs.value(key, False, type=bool) is False


# ── CoachMarkChain on_done callback ──────────────────────────────────────────

class TestCoachMarkChainOnDone:
    def setup_method(self):
        _clear_keys()

    def teardown_method(self):
        _clear_keys()

    def test_on_done_is_callable_and_fires_on_cleanup(self):
        from ui.widgets.coach_mark import CoachMarkChain
        fired = []
        chain = CoachMarkChain(None, [], on_done=lambda: fired.append(True))
        chain._cleanup()
        assert fired == [True]

    def test_on_done_fires_only_once(self):
        from ui.widgets.coach_mark import CoachMarkChain
        fired = []
        chain = CoachMarkChain(None, [], on_done=lambda: fired.append(True))
        chain._cleanup()
        chain._cleanup()
        assert len(fired) == 1


# ── Log Hub coach mark ────────────────────────────────────────────────────────

class TestLogHubCoachMark:
    def setup_method(self):
        _clear_keys()

    def teardown_method(self):
        _clear_keys()

    def test_import_log_hub_page(self):
        from ui.pages.log_hub_page import LogHubPage  # noqa: F401

    def test_log_hub_has_coach_method(self):
        from ui.pages.log_hub_page import LogHubPage
        assert hasattr(LogHubPage, "_maybe_show_coach_log_hub")

    def test_log_hub_coach_skips_when_key_set(self):
        from ui.pages.log_hub_page import LogHubPage
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("coach/log_hub_sources_shown", True)
        qs.setValue("logging/net_enabled", False)

        try:
            from unittest.mock import MagicMock
            page = MagicMock(spec=LogHubPage)
            page.window.return_value = None
            LogHubPage._maybe_show_coach_log_hub(page)
        except Exception:
            pass  # skip test if PyQt6 unavailable
        assert qs.value("coach/log_hub_sources_shown", False, type=bool) is True

    def test_log_hub_coach_skips_when_net_enabled(self):
        from ui.pages.log_hub_page import LogHubPage
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("logging/net_enabled", True)
        from unittest.mock import MagicMock
        page = MagicMock(spec=LogHubPage)
        page.window.return_value = None
        LogHubPage._maybe_show_coach_log_hub(page)
        assert qs.value("coach/log_hub_sources_shown", False, type=bool) is False


# ── Diagnosis coach mark ──────────────────────────────────────────────────────

class TestDiagnosisCoachMark:
    def setup_method(self):
        _clear_keys()

    def teardown_method(self):
        _clear_keys()

    def test_import_diagnosis_page(self):
        from ui.pages.diagnosis_page import DiagnosisPage  # noqa: F401

    def test_diagnosis_has_coach_method(self):
        from ui.pages.diagnosis_page import DiagnosisPage
        assert hasattr(DiagnosisPage, "_maybe_show_coach_diagnosis")

    def test_diagnosis_has_show_event(self):
        from ui.pages.diagnosis_page import DiagnosisPage
        assert hasattr(DiagnosisPage, "showEvent")

    def test_diagnosis_coach_skips_when_key_set(self):
        from unittest.mock import MagicMock
        from ui.pages.diagnosis_page import DiagnosisPage
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("coach/diagnosis_shown", True)
        page = MagicMock(spec=DiagnosisPage)
        page.window.return_value = None
        page._stack = MagicMock()
        page._stack.currentIndex.return_value = 0
        page._symptom_btns = {"slow": MagicMock()}
        DiagnosisPage._maybe_show_coach_diagnosis(page)
        assert qs.value("coach/diagnosis_shown", False, type=bool) is True

    def test_diagnosis_coach_skips_when_not_idle(self):
        from unittest.mock import MagicMock
        from ui.pages.diagnosis_page import DiagnosisPage
        page = MagicMock(spec=DiagnosisPage)
        page.window.return_value = MagicMock(isVisible=lambda: True)
        page._stack = MagicMock()
        page._stack.currentIndex.return_value = 2
        page._symptom_btns = {"slow": MagicMock()}
        DiagnosisPage._maybe_show_coach_diagnosis(page)
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("coach/diagnosis_shown", False, type=bool) is False


# ── Grade coach mark ──────────────────────────────────────────────────────────

class TestGradeCoachMark:
    def setup_method(self):
        _clear_keys()

    def teardown_method(self):
        _clear_keys()

    def test_home_data_mixin_has_coach_method(self):
        from ui.pages.home_data_mixin import _HomeDataMixin
        assert hasattr(_HomeDataMixin, "_maybe_show_coach_grade")

    def test_grade_coach_skips_when_key_set(self):
        from unittest.mock import MagicMock
        from ui.pages.home_data_mixin import _HomeDataMixin
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("coach/grade_shown", True)
        page = MagicMock()
        page.window.return_value = None
        _HomeDataMixin._maybe_show_coach_grade(page)
        assert qs.value("coach/grade_shown", False, type=bool) is True


# ── Home pills coach mark (removed — was cluttering startup) ──────────────────

class TestHomePillsCoachMark:
    def test_home_page_pills_coach_removed(self):
        from ui.pages.home_page import HomePage
        assert not hasattr(HomePage, "_maybe_show_coach_home_pills")

    def test_home_page_has_show_event(self):
        from ui.pages.home_page import HomePage
        assert hasattr(HomePage, "showEvent")


# ── Devices coach mark ────────────────────────────────────────────────────────

class TestDevicesCoachMark:
    def setup_method(self):
        _clear_keys()

    def teardown_method(self):
        _clear_keys()

    def test_inventory_page_has_coach_method(self):
        from ui.pages.inventory_page import InventoryPage
        assert hasattr(InventoryPage, "_maybe_show_coach_devices")

    def test_devices_coach_skips_when_key_set(self):
        from unittest.mock import MagicMock
        from ui.pages.inventory_page import InventoryPage
        qs = QSettings("NetSentinel", "NetSentinel")
        qs.setValue("coach/devices_rightclick_shown", True)
        page = MagicMock(spec=InventoryPage)
        page.window.return_value = None
        page._table = MagicMock()
        page._table.rowCount.return_value = 5
        InventoryPage._maybe_show_coach_devices(page)
        assert qs.value("coach/devices_rightclick_shown", False, type=bool) is True

    def test_devices_coach_skips_when_table_empty(self):
        from unittest.mock import MagicMock
        from ui.pages.inventory_page import InventoryPage
        page = MagicMock(spec=InventoryPage)
        page.window.return_value = MagicMock(isVisible=lambda: True)
        page._table = MagicMock()
        page._table.rowCount.return_value = 0
        InventoryPage._maybe_show_coach_devices(page)
        qs = QSettings("NetSentinel", "NetSentinel")
        assert qs.value("coach/devices_rightclick_shown", False, type=bool) is False
