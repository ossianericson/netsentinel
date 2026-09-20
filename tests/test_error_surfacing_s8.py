"""S8 — UI refresh paths and grading inputs: a reader that cannot read must not report health.

Behavioural counterparts to the (b) verdicts of the S8 triage
(``docs/internal/error-surfacing-audit-2026-09-15.md`` §6 S8). The grading tests run against a
real ``MetricStore`` rather than a mock, because every one of these defects was a disagreement
between what the store emits and what the reader asks for — the exact class of bug a mock
cannot expose, and the class that ``tests/test_health_score.py`` hid for as long as its fixture
returned the key the real store never emits.

  * B8  — ``health_score``: ``_availability_score`` read ``row["24h"]`` while
    ``query_uptime_table`` keys windows by ``str(hours)``, so the heaviest input (weight 0.45)
    was never read and silently took its optimistic 80.0 default.
  * B9  — ``digest_builder``: the Grade tile called ``store.get_grade_result()``, a method that
    has never existed on MetricStore, and the AttributeError was swallowed.
  * B10 — ``digest_builder``: the new-device tile and table filtered ``("join", "new")``; the
    persisted vocabulary is ``JOINED``.
  * B11 — ``digest_builder``: a window key is *present and None* for a device with no samples
    in it, so ``.get(key, default)`` returned that None and the comparison raised, collapsing
    the whole uptime table into "unavailable".
  * B12 — ``home_data_mixin``: a refused acknowledgement cleared the row anyway, and Undo
    silently did nothing.
  * B13 — ``inventory_page``: a device annotation that failed to save was discarded silently.
  * B14 — ``dashboard``: ``next_ts`` is advanced before the scan is attempted, so a scan that
    could not start left no trace at all.
"""
from __future__ import annotations

import time

import pytest

from modules import digest_builder as db
from modules.health_score import HealthScoreCalculator
from modules.metric_store import MetricStore


@pytest.fixture()
def store(tmp_path):
    """A real MetricStore holding the rows these readers claim to read.

    ``nas`` is DOWN for half of the last 24 h. ``old-tv`` was last seen 10 days ago, so its
    24 h and 168 h windows are present-and-None while 720 h has a value — the shape B11 is
    about. One grade and one JOINED event are recorded.
    """
    st = MetricStore(db_path=tmp_path / "s8.db", prune_on_init=False)
    now = int(time.time())
    for i in range(20):
        st.record_device_state("192.168.1.10", "aa:bb:cc:00:00:10", "nas",
                               "UP" if i % 2 else "DOWN", 5.0, ts=now - i * 300)
    st.record_device_state("192.168.1.20", None, "old-tv", "UP", 4.0, ts=now - 10 * 86400)
    st.record_device_event("192.168.1.50", "JOINED", mac="aa:bb:cc:00:00:50", ts=now - 3600)
    st.record_grade("B", 82.0, "measured")
    yield st
    st.close()


# ── B8: availability must actually reach the score ───────────────────────────

def test_b8_availability_key_matches_what_the_store_emits(store):
    """The contract, asserted directly: the key the reader asks for is the key emitted.

    This is the assertion whose absence let B8 live. Both sides derive from
    ``_AVAIL_WINDOW_HOURS``, so the request and the read cannot drift apart again.
    """
    hours = HealthScoreCalculator._AVAIL_WINDOW_HOURS
    row = store.query_uptime_table(hours_list=[hours])[0]
    assert str(hours) in row, f"store emits {sorted(row)}, reader asks for {str(hours)!r}"


def test_b8_half_down_device_is_scored_not_defaulted(store):
    """A device down half the window scores ~50, not the optimistic 80.0 default."""
    avail = HealthScoreCalculator()._availability_score(store)
    assert avail is not None, "availability never reached the score"
    assert 45.0 <= avail <= 55.0, avail


def test_b8_device_with_no_samples_in_window_is_excluded_not_counted(store):
    """old-tv has no 24 h samples; it must not be read as 100 % (nor crash the average)."""
    avail = HealthScoreCalculator()._availability_score(store)
    assert avail is not None
    # Were old-tv counted as a perfect 100.0, the mean of (50, 100) would be 75.
    assert avail < 60.0, avail


def test_b8_unreachable_devices_headline_is_reachable(store):
    """The red-state copy branch guarded by `avail_score is not None` was dead code."""
    calc = HealthScoreCalculator()
    headline, sub = calc._generate_copy("red", store, avail_score=20.0, alert_score=0.0, stable=0.0)
    assert "unreachable" in headline.lower()
    assert sub


# ── B9 / B10 / B11: the weekly digest ────────────────────────────────────────

def test_b9_grade_tile_shows_the_recorded_grade(store):
    """The tile read a method that never existed, so it was permanently '—'."""
    assert store.query_last_grade()["grade"] == "B"
    assert ">B<" in db._grade_kpi(store)


def test_b9_grade_accessor_exists_on_the_store(store):
    """A guard for the shape of the defect: the reader must call a real method."""
    assert not hasattr(store, "get_grade_result")
    assert callable(store.query_last_grade)


def test_b10_new_device_tile_counts_joined_events(store):
    """`record_device_event` only accepts JOINED/LEFT/UP/DOWN/DEGRADED/RECOVERED."""
    assert ">1<" in db._new_device_kpi(store)


def test_b10_new_device_table_lists_the_join(store):
    table = db._new_devices_table(store)
    assert "192.168.1.50" in table
    assert "No new devices" not in table


def test_b10_join_vocabulary_is_rejected_by_the_store(store):
    """Why the old filter could never match: 'join' is not a legal event type."""
    with pytest.raises(ValueError):
        store.record_device_event("192.168.1.99", "join")


def test_b11_uptime_table_survives_a_device_outside_the_window(store):
    """One device with no 7-day samples collapsed the entire table."""
    table = db._uptime_table(store)
    assert "unavailable" not in table
    assert "192.168.1.10" in table and "192.168.1.20" in table


def test_b11_missing_measurement_renders_as_em_dash_not_a_number(store):
    """A device with no samples in the window has no uptime — inventing 100 % is a lie."""
    table = db._uptime_table(store)
    row = [seg for seg in table.split("<tr>") if "192.168.1.20" in seg][0]
    assert "—" in row
    assert "100.0%" not in row


def test_b11_present_but_none_is_not_a_missing_key(store):
    """The mechanism behind B11, asserted directly: `.get` does not fall back on a None value."""
    row = [r for r in store.query_uptime_table() if r["ip"] == "192.168.1.20"][0]
    assert "168.0" in row and row["168.0"] is None
    assert row.get("168.0", 100.0) is None


# ── B12: an acknowledgement that did not happen ──────────────────────────────

class _RefusingStore:
    """Every acknowledgement write raises, as a locked database would."""

    def acknowledge_alert(self, _id):
        raise RuntimeError("database is locked")

    def acknowledge_alerts(self, _ids):
        raise RuntimeError("database is locked")

    def unacknowledge_alerts(self, _ids):
        raise RuntimeError("database is locked")

    def get_unacked_alerts(self):
        return [{"id": 1}, {"id": 2}]


def _ack_host(qtbot_widget_cls, store):
    """A minimal concrete host for the real _HomeDataMixin acknowledgement methods."""
    from PyQt6.QtCore import pyqtSignal
    from PyQt6.QtWidgets import QVBoxLayout, QWidget

    from ui.pages.home_data_mixin import _HomeDataMixin

    class _Host(QWidget, _HomeDataMixin):
        alerts_acknowledged = pyqtSignal()

        def __init__(self):
            super().__init__()
            self._store = store
            self._ac_alert_rows_lay = QVBoxLayout(self)
            self.pending_set_to = None
            for name in ("_ac_alert_rows_widget", "_ac_view_all_btn", "_ac_count_lbl",
                         "_ac_ack_all_btn", "_action_card"):
                setattr(self, name, QWidget(self))

        def set_pending_alert_rows(self, alerts):
            self.pending_set_to = alerts

    return _Host()


@pytest.fixture()
def toasts(monkeypatch):
    """Collect the toasts a real code path raises."""
    from ui.widgets.toast import ToastManager

    shown: list = []
    monkeypatch.setattr(
        ToastManager, "show",
        classmethod(lambda _cls, message, kind="info", *a, **k: shown.append((message, kind))),
    )
    return shown


def test_b12_refused_row_ack_keeps_the_row_and_says_why(toasts):
    """Hiding the row would assert a success the store refused; it returns at the next refresh."""
    from PyQt6.QtWidgets import QWidget

    host = _ack_host(QWidget, _RefusingStore())
    row_w = QWidget(host)
    host._ac_alert_rows_lay.addWidget(row_w)
    host._ack_alert_row(7, row_w)

    assert not row_w.isHidden(), "the row was cleared although the write failed"
    assert toasts and toasts[-1][1] == "warning"
    assert "acknowledge" in toasts[-1][0].lower()


def test_b12_refused_undo_says_the_alerts_stay_acknowledged(toasts):
    """The affordance said 'Undo', so silence reported a reversal that did not happen."""
    from PyQt6.QtWidgets import QWidget

    host = _ack_host(QWidget, _RefusingStore())
    host._undo_ack_all([1, 2, 3])

    assert toasts and toasts[-1][1] == "warning"
    assert "undo" in toasts[-1][0].lower()


def test_b12_refused_ack_all_does_not_clear_the_card(toasts):
    from PyQt6.QtWidgets import QWidget

    host = _ack_host(QWidget, _RefusingStore())
    host._ack_all_alerts()

    assert host.pending_set_to is None, "the card was emptied although nothing was acknowledged"
    assert toasts and toasts[-1][1] == "warning"


def test_b12_successful_ack_still_clears_the_row(toasts):
    """The guard must not break the path that works."""
    from PyQt6.QtWidgets import QWidget

    class _OkStore(_RefusingStore):
        def acknowledge_alert(self, _id):
            return None

    host = _ack_host(QWidget, _OkStore())
    row_w = QWidget(host)
    host._ac_alert_rows_lay.addWidget(row_w)
    host._ack_alert_row(7, row_w)

    assert row_w.isHidden()
    assert not [t for t in toasts if t[1] == "warning"]


# ── B13: a user edit that was not stored ─────────────────────────────────────

def test_b13_failed_annotation_save_tells_the_user(toasts, monkeypatch):
    """Label / location / owner / asset tag / notes are the user's own input."""
    from PyQt6.QtWidgets import QWidget

    import modules.device_tracker as dt
    from ui.pages.inventory_page import _DeviceDrawer

    def _boom(*_a, **_kw):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(dt, "save_annotations", _boom)
    parent = QWidget()  # held: an unreferenced parent is collected with its children
    drawer = _DeviceDrawer(parent)
    drawer._current_mac = "aa:bb:cc:00:00:10"
    drawer._current_store = object()
    drawer._ann_label.setText("Living Room TV")
    drawer._save_annotations()

    assert toasts and toasts[-1][1] == "warning"
    assert "save" in toasts[-1][0].lower()


def test_b13_message_carries_no_raw_exception_text(toasts, monkeypatch):
    """RULE-A2: the sink is user-visible, so the exception's own words must not reach it."""
    from PyQt6.QtWidgets import QWidget

    import modules.device_tracker as dt
    from ui.pages.inventory_page import _DeviceDrawer

    def _boom(*_a, **_kw):
        raise RuntimeError("no such table: device_annotation")

    monkeypatch.setattr(dt, "save_annotations", _boom)
    parent = QWidget()  # held: an unreferenced parent is collected with its children
    drawer = _DeviceDrawer(parent)
    drawer._current_mac = "aa:bb:cc:00:00:10"
    drawer._current_store = object()
    drawer._save_annotations()

    assert toasts
    assert "no such table" not in toasts[-1][0]


# ── B14: a scheduled scan that never ran ─────────────────────────────────────

class _FakeQSettings:
    """QSettings("NetSentinel", "NetSentinel") reads the developer's real registry."""

    store: dict = {}

    def __init__(self, *_a, **_kw):
        pass

    def value(self, key, default=None, *_a, **_kw):
        return type(self).store.get(key, default)

    def setValue(self, key, value):  # noqa: N802
        type(self).store[key] = value


class _RecordingHealth:
    def __init__(self):
        self.failures: list = []
        self.oks: list = []

    def report_failure(self, spec, detail=""):
        self.failures.append((spec.key, detail))

    def report_ok(self, key):
        self.oks.append(key)


def _sched_settings(monkeypatch):
    import ui.dashboard as dash

    _FakeQSettings.store = {
        "sched_scan/enabled": True,
        "sched_scan/next_ts": time.time() - 60,
        "sched_scan/hour": 2,
        "sched_scan/minute": 0,
        "sched_scan/interval_hours": 24,
    }
    monkeypatch.setattr(dash, "QSettings", _FakeQSettings)
    return dash


def test_b14_scan_that_cannot_start_raises_a_condition(monkeypatch):
    """next_ts advances either way, so the condition is the only trace a missed run leaves."""
    from modules.app_health_catalogue import SCHEDULED_SCAN

    dash = _sched_settings(monkeypatch)
    health = _RecordingHealth()

    class _Self:
        _app_health = health

        def _start_scan(self):
            raise RuntimeError("scan worker could not start")

    dash.Dashboard._check_scheduled_scan(_Self())
    assert [k for k, _ in health.failures] == [SCHEDULED_SCAN.key]


def test_b14_condition_detail_is_classified_not_raw(monkeypatch):
    """RULE-A2: `Condition.detail` is rendered in the app-health strip tooltip."""
    dash = _sched_settings(monkeypatch)
    health = _RecordingHealth()

    class _Self:
        _app_health = health

        def _start_scan(self):
            raise RuntimeError("worker thread 0x7ffe died")

    dash.Dashboard._check_scheduled_scan(_Self())
    assert health.failures
    assert "0x7ffe" not in health.failures[0][1]


def test_b14_successful_scan_resolves_the_condition(monkeypatch):
    """A schedule that recovered must not keep showing a warning."""
    from modules.app_health_catalogue import SCHEDULED_SCAN

    dash = _sched_settings(monkeypatch)
    health = _RecordingHealth()
    started: list = []

    class _Self:
        _app_health = health

        def _start_scan(self):
            started.append(1)

    dash.Dashboard._check_scheduled_scan(_Self())
    assert started == [1]
    assert health.oks == [SCHEDULED_SCAN.key]
    assert not health.failures


def test_b14_schedule_still_advances_so_a_failing_scan_cannot_spin(monkeypatch):
    """Not advancing would retry on every timer tick."""
    dash = _sched_settings(monkeypatch)
    before = _FakeQSettings.store["sched_scan/next_ts"]

    class _Self:
        _app_health = _RecordingHealth()

        def _start_scan(self):
            raise RuntimeError("scan worker could not start")

    dash.Dashboard._check_scheduled_scan(_Self())
    assert _FakeQSettings.store["sched_scan/next_ts"] != before


def test_b14_condition_is_registered_in_the_catalogue():
    """ALL_STATIC is what the app-health page enumerates."""
    from modules.app_health_catalogue import ALL_STATIC, SCHEDULED_SCAN

    assert SCHEDULED_SCAN in ALL_STATIC
    assert len({spec.key for spec in ALL_STATIC}) == len(ALL_STATIC)
