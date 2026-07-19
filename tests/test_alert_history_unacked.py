"""
Regression tests for critical-UX Phase 1.1: Alert History could not reach
what the "Action needed" card showed.

get_unacked_alerts() has no time bound; get_recent_alerts() defaults to a
window (the page's own combo defaults to 72h). An unacked alert older than
the widest window (7d) was unreachable from Alert History by any UI action.
get_alert_history(unacked_only=True) closes that gap: drop the ts>= bound,
add acked_ts IS NULL, so it returns exactly the same set get_unacked_alerts()
does, regardless of the hours argument.

RULE-T3: must fail before the fix (get_alert_history doesn't exist yet).
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    db_path = tmp_path / "test.db"
    s = MetricStore(db_path=db_path)
    yield s
    s.close()


def test_get_alert_history_unacked_only_ignores_time_window(store):
    """An alert older than any selectable window (>7 days) must still be
    returned when unacked_only=True."""
    eight_days_ago = int(time.time()) - 8 * 86400
    old_id = store.record_alert_fired(
        "Host Down", "192.168.1.1", "CRITICAL", "Host DOWN", ts=eight_days_ago
    )

    # A 1-hour window would normally exclude an 8-day-old alert.
    result = store.get_alert_history(hours=1.0, unacked_only=True)

    ids = {a["id"] for a in result}
    assert old_id in ids


def test_get_alert_history_unacked_only_excludes_acked(store):
    id1 = store.record_alert_fired("High RTT", "10.0.0.2", "WARNING", "high rtt")
    id2 = store.record_alert_fired("High RTT", "10.0.0.3", "WARNING", "high rtt")
    store.acknowledge_alert(id1, acked_by="user", comment="")

    result = store.get_alert_history(hours=24.0, unacked_only=True)

    ids = {a["id"] for a in result}
    assert id1 not in ids
    assert id2 in ids


def test_get_alert_history_matches_get_unacked_alerts_row_set(store):
    """Card ('Action needed', via get_unacked_alerts) and History (via the new
    unacked_only path) must return the exact same alerts."""
    eight_days_ago = int(time.time()) - 8 * 86400
    store.record_alert_fired("Old Alert", "10.0.0.5", "WARNING", "old", ts=eight_days_ago)
    store.record_alert_fired("Recent Alert", "10.0.0.6", "INFO", "recent")

    card_ids = {a["id"] for a in store.get_unacked_alerts()}
    history_ids = {a["id"] for a in store.get_alert_history(hours=24.0, unacked_only=True)}

    assert card_ids == history_ids
    assert len(card_ids) == 2


def test_get_alert_history_default_behaves_like_get_recent_alerts(store):
    """unacked_only=False (the default) must not change existing behaviour --
    other callers of get_recent_alerts() depend on its window semantics."""
    eight_days_ago = int(time.time()) - 8 * 86400
    store.record_alert_fired("Old Alert", "10.0.0.5", "WARNING", "old", ts=eight_days_ago)
    recent_id = store.record_alert_fired("Recent Alert", "10.0.0.6", "INFO", "recent")

    result = store.get_alert_history(hours=24.0)

    ids = {a["id"] for a in result}
    assert ids == {recent_id}


def test_get_alert_history_unacked_only_orders_oldest_first(store):
    first_id = store.record_alert_fired(
        "A", "10.0.0.1", "INFO", "a", ts=int(time.time()) - 100
    )
    second_id = store.record_alert_fired(
        "B", "10.0.0.2", "INFO", "b", ts=int(time.time()) - 10
    )

    result = store.get_alert_history(hours=24.0, unacked_only=True)

    result_ids = [a["id"] for a in result]
    assert result_ids.index(first_id) < result_ids.index(second_id)
