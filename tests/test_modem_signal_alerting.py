"""Phase 4 C2 — MODEM_SIGNAL_DROP must not be gated on the Monitor logging toggle.

Both the log write *and* `evaluate_modem_checks()` used to sit inside
`if logging/modem_enabled` **and** inside the 5-minute write throttle, and the
prior-SINR baseline was read back out of `modem_signal_log`. With logging off —
the default — no rows were ever written, so there was no history, so the rule
could never fire: the toggle silently disabled the alert, not just the log.

These exercise the real `Dashboard._on_modem_signal` against a lightweight
double rather than constructing the widget tree (RULE-TP4-DASH forbids building
a real Dashboard in-process; RULE-T7 allows "a mock of the dashboard").
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

try:
    from ui.dashboard import Dashboard
    from modules.alert_baseline import RollingSeries
    from modules.alert_engine import AlertEngine, AlertRule
except ImportError:
    pytest.skip("PyQt6 not available", allow_module_level=True)


class _FakeRow:
    """One `modem_signal_log` row as `query_modem_signal_log()` returns it."""

    def __init__(self, network_type="LTE", lte_snr=None, nr5g_sinr=None):
        self.network_type = network_type
        self.lte_snr = lte_snr
        self.nr5g_sinr = nr5g_sinr


def _fake_dashboard(engine=None, store=None, history=None):
    """A Dashboard double wired for _on_modem_signal.

    `_modem_signal_history` is bound explicitly: `self.foo()` inside the real
    method resolves against the double's own type (MagicMock), so without this
    the helper under test would never run.
    """
    fake = MagicMock()
    fake._m1_result = None                 # skip the topology re-render branch
    fake._alert_engine = engine
    fake._alerts_seen = []
    fake._surface_alert_in_app = fake._alerts_seen.append

    if store is None:
        store = MagicMock()
        store.query_modem_signal_log.return_value = history or []
    fake._store = store

    fake._last_modem_log_ts = 0.0
    fake._modem_sinr_series = RollingSeries(maxlen=240)
    fake._modem_prev_network_type = None
    fake._modem_hist_cache = None
    fake._modem_signal_history = lambda: Dashboard._modem_signal_history(fake)
    return fake


def _lte(snr):
    return {"network_type": "LTE", "lte_snr_db": snr}


def _modem_rule():
    return AlertEngine(rules=[
        AlertRule(name="modem", rule_type="MODEM_SIGNAL_DROP", cooldown_s=0)
    ])


def _poll(fake, data):
    Dashboard._on_modem_signal(fake, data)


# ── The defect: the rule could never fire with logging off ───────────────────

def test_modem_signal_drop_fires_with_monitor_logging_off():
    """25 stable polls then a cliff must alert, with logging/modem_enabled unset.

    Fails before fix: evaluate_modem_checks() is inside the toggle + throttle and
    the baseline comes from a DB table nothing ever writes, so fired stays empty.
    """
    fake = _fake_dashboard(engine=_modem_rule())

    for _ in range(24):
        _poll(fake, _lte(20.0))
    _poll(fake, _lte(10.0))          # widens stddev; prior stddev is still 0 here
    assert fake._alerts_seen == [], "a single dip must not fire on a zero-variance baseline"

    _poll(fake, _lte(2.0))           # well below mean - 2*sigma

    assert len(fake._alerts_seen) == 1, (
        "MODEM_SIGNAL_DROP must fire from the in-memory rolling baseline when "
        "Monitor logging is off; got no alert"
    )
    assert fake._alerts_seen[0].rule_type == "MODEM_SIGNAL_DROP"


def test_modem_band_downgrade_fires_with_monitor_logging_off():
    """A 5G -> LTE downgrade needs no history at all, only the previous poll."""
    fake = _fake_dashboard(engine=_modem_rule())

    _poll(fake, {"network_type": "5G-NSA", "nr5g_sinr_db": 18.0})
    _poll(fake, _lte(15.0))

    assert len(fake._alerts_seen) == 1, (
        "the 5G->LTE downgrade branch must see the prior network_type from the "
        "in-memory series when no logged history exists"
    )


def test_modem_evaluation_runs_on_every_poll_not_only_on_the_write_throttle():
    """The rule is evaluated per poll (30 s), not per log write (5 min)."""
    fake = _fake_dashboard(engine=_modem_rule())
    for _ in range(25):
        _poll(fake, _lte(20.0))

    fake._alert_engine = MagicMock()
    fake._alert_engine.evaluate_modem_checks.return_value = []
    _poll(fake, _lte(20.0))
    _poll(fake, _lte(20.0))

    assert fake._alert_engine.evaluate_modem_checks.call_count == 2


# ── The log write stays gated; only the evaluation was ungated ───────────────

def test_modem_log_write_still_gated_on_the_toggle(monkeypatch):
    """Ungating the alert must not start writing modem_signal_log rows."""
    writes: list = []
    monkeypatch.setattr("ui.dashboard.record_modem_signal", lambda store, **kw: writes.append(kw))

    fake = _fake_dashboard(engine=_modem_rule())
    for _ in range(26):
        _poll(fake, _lte(20.0))

    assert writes == [], "logging/modem_enabled is off — no row may be written"
    fake._log_hub_page.add_modem_entry.assert_not_called()


def test_modem_log_write_happens_when_the_toggle_is_on(monkeypatch):
    """Regression guard: the logging-on path still logs and still throttles."""
    from PyQt6.QtCore import QSettings

    QSettings().setValue("logging/modem_enabled", True)
    writes: list = []
    monkeypatch.setattr("ui.dashboard.record_modem_signal", lambda store, **kw: writes.append(kw))

    fake = _fake_dashboard(engine=_modem_rule())
    _poll(fake, _lte(20.0))
    _poll(fake, _lte(20.0))

    assert len(writes) == 1, "the 5-minute write throttle must still apply"
    assert fake._log_hub_page.add_modem_entry.call_count == 2


# ── Baseline source preference + the DB-history cache ────────────────────────

def test_persisted_history_is_preferred_over_the_shorter_in_memory_series():
    """With a real logged history, the baseline is the DB series, as before."""
    history = [_FakeRow("LTE", lte_snr=20.0) for _ in range(24)]
    history.append(_FakeRow("LTE", lte_snr=10.0))
    fake = _fake_dashboard(engine=_modem_rule(), history=history)

    prior_type, prior_sinr = fake._modem_signal_history()

    assert prior_type == "LTE"
    assert len(prior_sinr) == 25, "the 25-row logged history must win over an empty series"

    _poll(fake, _lte(2.0))
    assert len(fake._alerts_seen) == 1, "the persisted baseline must still drive the rule"


def test_in_memory_series_wins_once_it_is_longer_than_the_logged_history():
    """A stale one-row log must not starve the rule of a usable baseline."""
    fake = _fake_dashboard(engine=_modem_rule(), history=[_FakeRow("LTE", lte_snr=20.0)])

    for _ in range(24):
        _poll(fake, _lte(20.0))
    _poll(fake, _lte(10.0))

    _, prior_sinr = fake._modem_signal_history()
    assert len(prior_sinr) == 25, (
        "with 25 in-memory samples against 1 logged row, the in-memory series "
        f"must be preferred; got {len(prior_sinr)} samples"
    )


def test_logged_history_is_read_once_and_cached_between_writes():
    """This handler is the only writer, so re-querying every 30 s buys nothing."""
    fake = _fake_dashboard(engine=_modem_rule(),
                           history=[_FakeRow("LTE", lte_snr=20.0) for _ in range(30)])

    for _ in range(5):
        _poll(fake, _lte(20.0))

    assert fake._store.query_modem_signal_log.call_count == 1, (
        "modem_signal_log must be read once per session while unchanged, not on "
        f"every 30 s poll; got {fake._store.query_modem_signal_log.call_count} queries"
    )


def test_history_cache_is_invalidated_after_a_write(monkeypatch):
    """A newly written row must be visible to the next poll's baseline."""
    from PyQt6.QtCore import QSettings

    QSettings().setValue("logging/modem_enabled", True)
    monkeypatch.setattr("ui.dashboard.record_modem_signal", lambda store, **kw: None)

    fake = _fake_dashboard(engine=_modem_rule(),
                           history=[_FakeRow("LTE", lte_snr=20.0) for _ in range(30)])

    _poll(fake, _lte(20.0))          # writes a row -> cache must drop
    assert fake._modem_hist_cache is None
    _poll(fake, _lte(20.0))          # re-reads, then caches again

    assert fake._store.query_modem_signal_log.call_count == 2


def test_history_query_failure_falls_back_to_the_in_memory_series():
    """A DB error must not stop the rule — it degrades to the in-memory window."""
    store = MagicMock()
    store.query_modem_signal_log.side_effect = RuntimeError("db locked")
    fake = _fake_dashboard(engine=_modem_rule(), store=store)

    for _ in range(24):
        _poll(fake, _lte(20.0))
    _poll(fake, _lte(10.0))
    _poll(fake, _lte(2.0))

    assert len(fake._alerts_seen) == 1
