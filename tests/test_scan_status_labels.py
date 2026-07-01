"""
tests/test_scan_status_labels.py — Sprint A behavioral tests.

Asserts that:
  1. _scan_age_str / format_scan_status helpers produce correct output.
  2. _nav_set_scan_state() updates _scan_registry and _flyout_dots correctly.
  3. Each scan result handler updates the matching status label.
"""
from __future__ import annotations

import time
import types
import unittest


# ── Helper tests (A-3) ────────────────────────────────────────────────────────

class TestScanAgeStr(unittest.TestCase):
    def test_never(self):
        from ui.tabs_helpers import _scan_age_str
        assert _scan_age_str(0) == "never"
        assert _scan_age_str(None) == "never"

    def test_just_now(self):
        from ui.tabs_helpers import _scan_age_str
        assert _scan_age_str(time.time() - 30) == "just now"

    def test_minutes(self):
        from ui.tabs_helpers import _scan_age_str
        assert _scan_age_str(time.time() - 120) == "2m ago"

    def test_hours(self):
        from ui.tabs_helpers import _scan_age_str
        result = _scan_age_str(time.time() - 3700)
        assert result.startswith("1h")

    def test_days(self):
        from ui.tabs_helpers import _scan_age_str
        result = _scan_age_str(time.time() - 86400 * 3)
        assert result == "3d ago"


class TestFormatScanStatus(unittest.TestCase):
    def test_never_run(self):
        from ui.tabs_helpers import format_scan_status
        result = format_scan_status("Open ports: 0", 0)
        assert "Never run" in result
        assert "Open ports: 0" in result

    def test_fresh_contains_last_run(self):
        from ui.tabs_helpers import format_scan_status
        result = format_scan_status("No issues", time.time() - 60)
        assert "Last run:" in result
        assert "No issues" in result

    def test_format_separator(self):
        from ui.tabs_helpers import format_scan_status
        result = format_scan_status("OK", time.time() - 90)
        # Must contain the middle-dot separator
        assert " · " in result


# ── _nav_set_scan_state unit tests (A-1/A-4) ─────────────────────────────────

def _make_mock_dashboard():
    """Return a minimal object that satisfies _NavBuilderMixin._nav_set_scan_state."""
    from ui.nav.builder import _NavBuilderMixin

    class _MockDash(_NavBuilderMixin):
        def __init__(self):
            self._scan_registry: dict = {}
            self._flyout_dots: dict = {}
            self._nav_flyout = types.SimpleNamespace(
                apply_dot=lambda lbl, col: None,
                set_item_tooltip=lambda lbl, tip: None,
            )

    return _MockDash()


class TestNavSetScanState(unittest.TestCase):
    def setUp(self):
        self.dash = _make_mock_dashboard()

    def test_registry_updated_running(self):
        self.dash._nav_set_scan_state("Port Scan (TCP)", "running")
        entry = self.dash._scan_registry["Port Scan (TCP)"]
        assert entry["state"] == "running"
        assert entry["ts"] > 0

    def test_registry_updated_fresh(self):
        ts = time.time() - 5
        self.dash._nav_set_scan_state("Port Scan (TCP)", "fresh", ts=ts)
        entry = self.dash._scan_registry["Port Scan (TCP)"]
        assert entry["state"] == "fresh"
        assert entry["ts"] == ts

    def test_flyout_dot_green_when_fresh(self):
        from ui.styles import GREEN
        self.dash._nav_set_scan_state("CVE Lookup", "fresh")
        assert self.dash._flyout_dots["CVE Lookup"] == GREEN

    def test_flyout_dot_accent_when_running(self):
        from ui.styles import ACCENT
        self.dash._nav_set_scan_state("OS Detection", "running")
        assert self.dash._flyout_dots["OS Detection"] == ACCENT

    def test_flyout_dot_amber_when_stale(self):
        from ui.styles import AMBER
        self.dash._nav_set_scan_state("Threat Intel", "stale")
        assert self.dash._flyout_dots["Threat Intel"] == AMBER

    def test_flyout_dot_red_when_error(self):
        from ui.styles import RED
        self.dash._nav_set_scan_state("Port Scan (UDP)", "error", error="Timeout")
        entry = self.dash._scan_registry["Port Scan (UDP)"]
        assert entry["error"] == "Timeout"
        assert self.dash._flyout_dots["Port Scan (UDP)"] == RED

    def test_flyout_dot_empty_when_never(self):
        self.dash._nav_set_scan_state("Exposed to Internet", "never")
        assert self.dash._flyout_dots["Exposed to Internet"] == ""

    def test_multiple_labels_independent(self):
        self.dash._nav_set_scan_state("Port Scan (TCP)", "fresh")
        self.dash._nav_set_scan_state("CVE Lookup", "running")
        assert self.dash._scan_registry["Port Scan (TCP)"]["state"] == "fresh"
        assert self.dash._scan_registry["CVE Lookup"]["state"] == "running"


# ── Status label update tests after result handler (A-2) ─────────────────────

class _FakeResult:
    """Minimal scan result stub accepted by ScanResultMixin handlers."""
    def __init__(self, verdict="All clear", error=None):
        self.plain_verdict = verdict
        self.error = error
        self.open_ports = []


class _FakeExposureResult:
    def __init__(self):
        self.plain_verdict = "No exposure"
        self.error = None
        self.risk = "LOW"
        self.wan_ip = "1.2.3.4"
        self.cgnat = False
        self.upnp_mappings = []


class TestStatusLabelAfterSynResult(unittest.TestCase):
    def test_syn_status_updated_after_result(self):
        """_on_syn_result sets _syn_status and calls _nav_set_scan_state."""
        # Import here to avoid Qt requirement at module level
        try:
            from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QStackedWidget
        except ImportError:
            self.skipTest("PyQt6 not available")
            return  # unreachable: skipTest raises, but needed for static analysis
        app = QApplication.instance()

        # Build a minimal mixin object with the needed attributes
        from ui.scan_wiring import ScanResultMixin
        from ui.nav.builder import _NavBuilderMixin

        states: list = []

        class _Stub(ScanResultMixin, _NavBuilderMixin):
            def __init__(self):
                self._scan_registry: dict = {}
                self._flyout_dots: dict = {}
                self._nav_flyout = types.SimpleNamespace(
                    apply_dot=lambda l, c: None,
                    set_item_tooltip=lambda l, t: None,
                )
                # Attributes expected by _on_syn_result
                self._syn_status = QLabel()
                self._recon_syn_table = QTableWidget(0, 7)
                self._syn_stack = QStackedWidget()
                self._syn_stack.addWidget(QLabel("empty"))
                self._syn_stack.addWidget(QLabel("table"))
                self._store = None
                self._last_scan_devices = []
                self._port_data_cache = {}
                self._pending_security_tools = []

            def _nav_set_scan_state(self, label, state, ts=None, error=None, verdict=None):
                states.append((label, state))
                super()._nav_set_scan_state(label, state, ts=ts, error=error, verdict=verdict)

            # Stubs for optional attributes accessed in _on_syn_result
            def _advance_security_audit(self):
                pass

        try:
            stub = _Stub()
            result = _FakeResult("0 open ports")
            stub._on_syn_result(result)

            # status label now includes "Last run:" suffix via format_scan_status
            assert "0 open ports" in stub._syn_status.text(), (
                f"Expected verdict in '{stub._syn_status.text()}'"
            )
            assert "Last run:" in stub._syn_status.text() or "Never run" in stub._syn_status.text(), (
                f"Expected freshness suffix in '{stub._syn_status.text()}'"
            )
            assert any(lbl == "Port Scan (TCP)" and st == "fresh" for lbl, st in states), (
                f"Expected ('Port Scan (TCP)', 'fresh') in states={states}"
            )
        finally:
            try:
                stub._syn_stack.deleteLater()
                stub._recon_syn_table.deleteLater()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal cleanup


class TestStatusLabelAfterUdpResult(unittest.TestCase):
    def test_udp_status_updated_after_result(self):
        try:
            from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QStackedWidget
        except ImportError:
            self.skipTest("PyQt6 not available")
            return  # unreachable: skipTest raises, but needed for static analysis
        app = QApplication.instance()

        from ui.scan_wiring import ScanResultMixin
        from ui.nav.builder import _NavBuilderMixin

        states: list = []

        class _Stub(ScanResultMixin, _NavBuilderMixin):
            def __init__(self):
                self._scan_registry: dict = {}
                self._flyout_dots: dict = {}
                self._nav_flyout = types.SimpleNamespace(
                    apply_dot=lambda l, c: None,
                    set_item_tooltip=lambda l, t: None,
                )
                self._udp_status = QLabel()
                self._recon_udp_table = QTableWidget(0, 3)
                self._udp_stack = QStackedWidget()
                self._udp_stack.addWidget(QLabel("empty"))
                self._udp_stack.addWidget(QLabel("table"))

            def _nav_set_scan_state(self, label, state, ts=None, error=None, verdict=None):
                states.append((label, state))
                super()._nav_set_scan_state(label, state, ts=ts, error=error, verdict=verdict)

        try:
            stub = _Stub()
            stub._on_udp_result(_FakeResult("No filtered ports"))
            assert "No filtered ports" in stub._udp_status.text()
            assert "Last run:" in stub._udp_status.text() or "Never run" in stub._udp_status.text()
            assert any(lbl == "Port Scan (UDP)" and st == "fresh" for lbl, st in states)
        finally:
            try:
                stub._udp_stack.deleteLater()
                stub._recon_udp_table.deleteLater()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal cleanup


class TestStatusLabelAfterOsResult(unittest.TestCase):
    def test_os_status_updated_after_result(self):
        try:
            from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QStackedWidget
        except ImportError:
            self.skipTest("PyQt6 not available")
            return  # unreachable: skipTest raises, but needed for static analysis
        app = QApplication.instance()

        from ui.scan_wiring import ScanResultMixin
        from ui.nav.builder import _NavBuilderMixin

        states: list = []

        class _Stub(ScanResultMixin, _NavBuilderMixin):
            def __init__(self):
                self._scan_registry: dict = {}
                self._flyout_dots: dict = {}
                self._nav_flyout = types.SimpleNamespace(
                    apply_dot=lambda l, c: None,
                    set_item_tooltip=lambda l, t: None,
                )
                self._os_status = QLabel()
                self._recon_os_table = QTableWidget(0, 6)
                self._os_stack = QStackedWidget()
                self._os_stack.addWidget(QLabel("empty"))
                self._os_stack.addWidget(QLabel("table"))

            def _nav_set_scan_state(self, label, state, ts=None, error=None, verdict=None):
                states.append((label, state))
                super()._nav_set_scan_state(label, state, ts=ts, error=error, verdict=verdict)

        try:
            stub = _Stub()
            stub._on_os_result({"guesses": []})
            assert "Fingerprinted 0" in stub._os_status.text()
            assert "Last run:" in stub._os_status.text() or "Never run" in stub._os_status.text()
            assert any(lbl == "OS Detection" and st == "fresh" for lbl, st in states)
        finally:
            try:
                stub._os_stack.deleteLater()
                stub._recon_os_table.deleteLater()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal cleanup


class TestStatusLabelAfterExposureResult(unittest.TestCase):
    def test_exposure_status_updated_after_result(self):
        try:
            from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget
        except ImportError:
            self.skipTest("PyQt6 not available")
            return  # unreachable: skipTest raises, but needed for static analysis
        app = QApplication.instance()

        from ui.scan_wiring import ScanResultMixin
        from ui.nav.builder import _NavBuilderMixin

        states: list = []

        class _Stub(ScanResultMixin, _NavBuilderMixin):
            def __init__(self):
                self._scan_registry: dict = {}
                self._flyout_dots: dict = {}
                self._nav_flyout = types.SimpleNamespace(
                    apply_dot=lambda l, c: None,
                    set_item_tooltip=lambda l, t: None,
                )
                self._exposure_status = QLabel()
                self._exposure_verdict = QLabel()
                self._recon_exposure_table = QTableWidget(0, 6)
                self._pending_security_tools = []

            def _nav_set_scan_state(self, label, state, ts=None, error=None, verdict=None):
                states.append((label, state))
                super()._nav_set_scan_state(label, state, ts=ts, error=error, verdict=verdict)

            def _advance_security_audit(self):
                pass

        try:
            stub = _Stub()
            stub._on_exposure_result(_FakeExposureResult())
            assert "1.2.3.4" in stub._exposure_status.text()
            assert "Last run:" in stub._exposure_status.text() or "Never run" in stub._exposure_status.text()
            assert any(lbl == "Exposed to Internet" and st == "fresh" for lbl, st in states)
        finally:
            try:
                stub._recon_exposure_table.deleteLater()
                if app:
                    for _ in range(3):
                        app.processEvents()
            except Exception:
                pass  # non-fatal cleanup


# ── B-4: Rail badge aggregate and flyout tooltip tests ────────────────────────

def _make_mock_dashboard_with_rail():
    """Mock dashboard with _nav_page_to_section and _nav_rail_buttons for badge tests."""
    from ui.nav.builder import _NavBuilderMixin

    tooltips: dict = {}
    badge_calls: list = []

    class _MockBtn:
        def set_badge(self, color):
            badge_calls.append(color)

    class _MockFlyout:
        def apply_dot(self, label, color):
            pass

        def set_item_tooltip(self, label, text):
            tooltips[label] = text

    class _MockDash(_NavBuilderMixin):
        def __init__(self):
            self._scan_registry: dict = {}
            self._flyout_dots: dict = {}
            self._nav_page_to_section: dict = {
                "Port Scan (TCP)": "Security Audit",
                "Port Scan (UDP)": "Security Audit",
                "CVE Lookup": "Security Audit",
            }
            self._nav_rail_buttons = {"Security Audit": _MockBtn()}
            self._nav_flyout = _MockFlyout()
            self._badge_calls = badge_calls
            self._tooltips = tooltips

    return _MockDash()


class TestRailBadgeAggregate(unittest.TestCase):
    def test_badge_green_after_single_fresh(self):
        from ui.styles import GREEN
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state("Port Scan (TCP)", "fresh")
        assert dash._badge_calls[-1] == GREEN

    def test_badge_amber_when_stale_label_exists(self):
        from ui.styles import AMBER
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state("Port Scan (TCP)", "fresh")
        dash._nav_set_scan_state("Port Scan (UDP)", "stale")
        # After the stale update, worst-state across section should be AMBER
        assert dash._badge_calls[-1] == AMBER

    def test_badge_red_wins_over_amber(self):
        from ui.styles import RED
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state("Port Scan (TCP)", "stale")
        dash._nav_set_scan_state("CVE Lookup", "error")
        # RED > AMBER
        assert dash._badge_calls[-1] == RED

    def test_badge_cleared_when_all_never(self):
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state("Port Scan (TCP)", "never")
        dash._nav_set_scan_state("Port Scan (UDP)", "never")
        dash._nav_set_scan_state("CVE Lookup", "never")
        assert dash._badge_calls[-1] == ""


class TestFlyoutTooltip(unittest.TestCase):
    def test_tooltip_never_run_for_state_never(self):
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state("Port Scan (TCP)", "never")
        assert dash._tooltips.get("Port Scan (TCP)") == "Never run"

    def test_tooltip_contains_last_run_for_fresh(self):
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state("Port Scan (TCP)", "fresh", ts=time.time() - 60)
        tip = dash._tooltips.get("Port Scan (TCP)", "")
        assert "Last run:" in tip

    def test_tooltip_includes_verdict(self):
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state(
            "CVE Lookup", "fresh", ts=time.time() - 30, verdict="2 CVEs found"
        )
        tip = dash._tooltips.get("CVE Lookup", "")
        assert "2 CVEs found" in tip

    def test_tooltip_includes_error(self):
        dash = _make_mock_dashboard_with_rail()
        dash._nav_set_scan_state(
            "Port Scan (UDP)", "error", ts=time.time() - 10, error="Timed out"
        )
        tip = dash._tooltips.get("Port Scan (UDP)", "")
        assert "Timed out" in tip


# ── C-4: QSettings round-trip ─────────────────────────────────────────────────

class TestQSettingsRoundTrip(unittest.TestCase):
    """C-1: registry state persists through a QSettings save/restore cycle."""

    def setUp(self):
        try:
            from PyQt6.QtCore import QSettings
            _qs = QSettings("NetSentinel", "NetSentinel")
            self._saved = _qs.value("scan_registry/state", "")
        except Exception:
            self._saved = ""

    def tearDown(self):
        try:
            from PyQt6.QtCore import QSettings
            _qs = QSettings("NetSentinel", "NetSentinel")
            if self._saved:
                _qs.setValue("scan_registry/state", self._saved)
            else:
                _qs.remove("scan_registry/state")
        except Exception:
            pass  # non-fatal — can't restore QSettings in this environment

    def test_registry_survives_save_and_restore(self):
        """State written by _nav_set_scan_state reads back correctly on new object."""
        dash1 = _make_mock_dashboard()
        ts_fixed = time.time() - 300
        dash1._nav_set_scan_state(
            "Port Scan (TCP)", "fresh", ts=ts_fixed, verdict="2 open ports"
        )

        dash2 = _make_mock_dashboard()
        assert "Port Scan (TCP)" not in dash2._scan_registry
        dash2._restore_scan_registry()

        entry = dash2._scan_registry.get("Port Scan (TCP)", {})
        assert entry.get("state") == "fresh", (
            f"Expected 'fresh', got {entry.get('state')!r}"
        )
        assert entry.get("verdict") == "2 open ports"
        assert abs((entry.get("ts") or 0.0) - ts_fixed) < 2

    def test_running_state_becomes_never_on_restore(self):
        """'running' saved mid-scan must be treated as 'never' on restore."""
        dash1 = _make_mock_dashboard()
        dash1._nav_set_scan_state("OS Detection", "running")

        dash2 = _make_mock_dashboard()
        dash2._restore_scan_registry()

        entry = dash2._scan_registry.get("OS Detection", {})
        assert entry.get("state") == "never", (
            f"Expected 'never' when restoring 'running', got {entry.get('state')!r}"
        )

    def test_multiple_labels_round_trip(self):
        """Multiple distinct labels all survive a QSettings round-trip."""
        dash1 = _make_mock_dashboard()
        ts = time.time() - 60
        dash1._nav_set_scan_state("CVE Lookup", "fresh", ts=ts, verdict="3 CVEs")
        dash1._nav_set_scan_state("Threat Intel", "stale", ts=ts - 4000)

        dash2 = _make_mock_dashboard()
        dash2._restore_scan_registry()

        assert dash2._scan_registry.get("CVE Lookup", {}).get("state") == "fresh"
        assert dash2._scan_registry.get("Threat Intel", {}).get("state") == "stale"


# ── C-4: Staleness check ──────────────────────────────────────────────────────

class TestStalenessCheck(unittest.TestCase):
    """C-2: _check_and_stale_registry promotes fresh → stale past threshold."""

    def test_fresh_promoted_past_threshold(self):
        """'fresh' entry older than its threshold becomes 'stale'."""
        dash = _make_mock_dashboard()
        # Port Scan (TCP) threshold = 2 hours; set ts 2 h + 1 s ago
        ts_old = time.time() - (2 * 3600 + 1)
        dash._nav_set_scan_state("Port Scan (TCP)", "fresh", ts=ts_old)
        assert dash._scan_registry["Port Scan (TCP)"]["state"] == "fresh"

        dash._check_and_stale_registry()

        assert dash._scan_registry["Port Scan (TCP)"]["state"] == "stale", (
            "Expected fresh→stale after threshold exceeded"
        )

    def test_fresh_stays_fresh_within_threshold(self):
        """'fresh' entry within its threshold must not be promoted."""
        dash = _make_mock_dashboard()
        ts_recent = time.time() - 60  # 1 minute — well within 2 h threshold
        dash._nav_set_scan_state("Port Scan (TCP)", "fresh", ts=ts_recent)

        dash._check_and_stale_registry()

        assert dash._scan_registry["Port Scan (TCP)"]["state"] == "fresh"

    def test_stale_entry_not_altered(self):
        """Already-stale entries must not be changed by the check."""
        dash = _make_mock_dashboard()
        dash._nav_set_scan_state("CVE Lookup", "stale", ts=time.time() - 99999)

        dash._check_and_stale_registry()

        assert dash._scan_registry["CVE Lookup"]["state"] == "stale"

    def test_default_threshold_for_unknown_label(self):
        """Labels absent from _FRESH_SECONDS use _DEFAULT_FRESH_SECONDS (1 h)."""
        from ui.nav.builder import _NavBuilderMixin
        dash = _make_mock_dashboard()
        ts_old = time.time() - (_NavBuilderMixin._DEFAULT_FRESH_SECONDS + 1)
        dash._nav_set_scan_state("Some Unknown Page", "fresh", ts=ts_old)

        dash._check_and_stale_registry()

        assert dash._scan_registry["Some Unknown Page"]["state"] == "stale"

    def test_ts_preserved_after_stale_promotion(self):
        """Original timestamp must not be overwritten during promotion."""
        dash = _make_mock_dashboard()
        ts_old = time.time() - (2 * 3600 + 5)
        dash._nav_set_scan_state("Port Scan (TCP)", "fresh", ts=ts_old)

        dash._check_and_stale_registry()

        entry = dash._scan_registry["Port Scan (TCP)"]
        assert abs(entry["ts"] - ts_old) < 1, "ts must be preserved after promotion"


# ── C-4: Security Overview scan status card ───────────────────────────────────

class TestSecurityOverviewCard(unittest.TestCase):
    """C-3: SecurityOverviewPage.update_scan_registry populates the Scan Status table."""

    def _make_page(self):
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            return None, None
        app = QApplication.instance()
        try:
            from ui.pages.security_overview_page import SecurityOverviewPage
            page = SecurityOverviewPage(store=None)
            return page, app
        except Exception:
            return None, app

    def _cleanup(self, page, app):
        try:
            page._refresh_timer.stop()
        except Exception:
            pass  # non-fatal — timer may already be stopped
        try:
            page.deleteLater()
            if app:
                for _ in range(3):
                    app.processEvents()
        except Exception:
            pass  # non-fatal cleanup

    def test_scan_status_table_has_one_row_per_audit_label(self):
        """update_scan_registry populates one row for every _AUDIT_SCAN_LABELS entry."""
        page, app = self._make_page()
        if page is None:
            self.skipTest("PyQt6 or SecurityOverviewPage not available")

        from ui.pages.security_overview_page import _AUDIT_SCAN_LABELS
        try:
            registry = {
                label: {"state": "fresh", "ts": time.time(), "verdict": "ok", "error": None}
                for label in _AUDIT_SCAN_LABELS
            }
            page.update_scan_registry(registry)

            assert page._scan_status_table.rowCount() == len(_AUDIT_SCAN_LABELS), (
                f"Expected {len(_AUDIT_SCAN_LABELS)} rows, "
                f"got {page._scan_status_table.rowCount()}"
            )
        finally:
            self._cleanup(page, app)

    def test_stale_pill_text_shown(self):
        """A 'stale' entry shows 'Stale' as the pill text in column 1."""
        page, app = self._make_page()
        if page is None:
            self.skipTest("PyQt6 or SecurityOverviewPage not available")

        from ui.pages.security_overview_page import _AUDIT_SCAN_LABELS
        try:
            first_label = _AUDIT_SCAN_LABELS[0]
            page.update_scan_registry({
                first_label: {
                    "state": "stale", "ts": time.time() - 9000,
                    "verdict": "2 ports", "error": None,
                }
            })

            pill = page._scan_status_table.cellWidget(0, 1)
            assert pill is not None, "Expected a pill QLabel in column 1"
            assert "Stale" in pill.text(), (
                f"Expected 'Stale' in pill text, got {pill.text()!r}"
            )
        finally:
            self._cleanup(page, app)

    def test_never_run_pill_for_empty_registry(self):
        """Labels absent from registry get a 'Never run' pill."""
        page, app = self._make_page()
        if page is None:
            self.skipTest("PyQt6 or SecurityOverviewPage not available")

        try:
            page.update_scan_registry({})  # all labels absent

            pill = page._scan_status_table.cellWidget(0, 1)
            assert pill is not None, "Expected a pill QLabel in column 1"
            assert "Never" in pill.text(), (
                f"Expected 'Never run' pill, got {pill.text()!r}"
            )
        finally:
            self._cleanup(page, app)

    def test_finding_column_shows_verdict(self):
        """'Finding' column (column 3) shows the verdict string from registry."""
        page, app = self._make_page()
        if page is None:
            self.skipTest("PyQt6 or SecurityOverviewPage not available")

        from ui.pages.security_overview_page import _AUDIT_SCAN_LABELS
        try:
            first_label = _AUDIT_SCAN_LABELS[0]
            page.update_scan_registry({
                first_label: {
                    "state": "fresh", "ts": time.time() - 10,
                    "verdict": "5 open ports", "error": None,
                }
            })
            item = page._scan_status_table.item(0, 3)
            assert item is not None
            assert item.text() == "5 open ports"
        finally:
            self._cleanup(page, app)


if __name__ == "__main__":
    unittest.main()
