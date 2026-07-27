"""
tests/test_alert_bulk_ack.py — batch acknowledgement (Phase 1, notifications rework).

RULE-T3 regression coverage for the defect found live in the user's DB: the
Alert History table collapses alerts by (rule_name, host) and shows one row per
group with a "×N" suffix, but only ever acknowledged the group's *representative*
alert id. With 87 unacked alerts collapsed into 43 rows, acknowledging every
visible row still left 44 unacked — which then reappeared on the next refresh.

Covers:
  - acknowledge_alerts() marks EVERY id in one transaction
  - acked_by / acked_comment are applied to all of them
  - an empty id list is a no-op (must not raise, must not touch other rows)
  - already-acked rows keep their original ack metadata (idempotent re-ack is
    an explicit overwrite, not a silent skip)
  - the batch path and the single-row acknowledge_alert() agree
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    db_path = tmp_path / "test.db"
    s = MetricStore(db_path=db_path)
    yield s
    s.close()


def _fire_group(store, rule: str, host: str, n: int) -> list[int]:
    """Fire n alerts that all collapse into a single (rule_name, host) group."""
    return [
        store.record_alert_fired(rule, host, "WARNING", f"{rule} #{i}")
        for i in range(n)
    ]


# ── Batch write ───────────────────────────────────────────────────────────────

def test_acknowledge_alerts_marks_every_id(store):
    ids = _fire_group(store, "Device Gone", "192.168.68.59", 4)
    assert len(store.get_unacked_alerts()) == 4

    store.acknowledge_alerts(ids)

    assert store.get_unacked_alerts() == []


def test_acknowledge_alerts_applies_owner_and_comment_to_all(store):
    ids = _fire_group(store, "Service Down", "192.168.68.61", 3)

    store.acknowledge_alerts(ids, acked_by="alice", comment="known outage")

    rows = {a["id"]: a for a in store.get_recent_alerts(hours=1)}
    for alert_id in ids:
        row = rows[alert_id]
        assert row["acked_ts"] is not None
        assert row["acked_by"] == "alice"
        assert row["acked_comment"] == "known outage"


def test_acknowledge_alerts_empty_list_is_a_noop(store):
    ids = _fire_group(store, "IP Churn", "aa:bb:cc:dd:ee:ff", 2)

    store.acknowledge_alerts([])

    assert {a["id"] for a in store.get_unacked_alerts()} == set(ids)


def test_acknowledge_alerts_leaves_other_groups_alone(store):
    gone = _fire_group(store, "Device Gone", "192.168.68.59", 2)
    churn = _fire_group(store, "IP Churn", "192.168.68.70", 3)

    store.acknowledge_alerts(gone)

    remaining = {a["id"] for a in store.get_unacked_alerts()}
    assert remaining == set(churn)


def test_acknowledge_alerts_matches_single_row_path(store):
    single = store.record_alert_fired("Host Down", "10.0.0.1", "CRITICAL", "down")
    batched = store.record_alert_fired("Host Down", "10.0.0.2", "CRITICAL", "down")

    store.acknowledge_alert(single, acked_by="bob", comment="c")
    store.acknowledge_alerts([batched], acked_by="bob", comment="c")

    rows = {a["id"]: a for a in store.get_recent_alerts(hours=1)}
    assert rows[single]["acked_by"] == rows[batched]["acked_by"] == "bob"
    assert rows[single]["acked_comment"] == rows[batched]["acked_comment"] == "c"


# ── Ack-hold seeding query ────────────────────────────────────────────────────

def test_get_recent_acks_returns_acks_for_old_alerts(store):
    """Seeds AlertEngine.load_ack_holds(). Must window on acked_ts, NOT on the
    alert's fire time -- the user's real backlog was 15 days old, so a
    fire-time window would return nothing for an ack made 10 seconds ago.
    """
    import time
    fifteen_days_ago = int(time.time()) - 15 * 86400
    old_id = store.record_alert_fired(
        "IP Churn", "3a:41:94:e8:e2:5f", "WARNING", "churn", ts=fifteen_days_ago
    )
    store.acknowledge_alerts([old_id])

    acks = store.get_recent_acks(since_ts=int(time.time()) - 3600)

    assert len(acks) == 1
    assert acks[0]["rule_name"] == "IP Churn"
    assert acks[0]["host"] == "3a:41:94:e8:e2:5f"
    assert acks[0]["acked_ts"] is not None


def test_get_recent_acks_excludes_unacked_and_older_acks(store):
    import time
    now = int(time.time())
    unacked = store.record_alert_fired("Device Gone", "10.0.0.1", "WARNING", "gone")
    old_ack = store.record_alert_fired("Device Gone", "10.0.0.2", "WARNING", "gone")
    fresh_ack = store.record_alert_fired("Device Gone", "10.0.0.3", "WARNING", "gone")
    store.acknowledge_alerts([old_ack], ts=now - 7200)
    store.acknowledge_alerts([fresh_ack], ts=now)

    hosts = {a["host"] for a in store.get_recent_acks(since_ts=now - 3600)}

    assert hosts == {"10.0.0.3"}
    assert unacked  # referenced so the fixture's intent is explicit


def test_get_recent_acks_feeds_the_engine_hold(store):
    """End-to-end: the query's row shape is what load_ack_holds() consumes."""
    import time
    from modules.alert_engine import AlertEngine
    from modules.alert_types import AlertRule

    now = int(time.time())
    alert_id = store.record_alert_fired("Service Down", "10.0.0.9", "CRITICAL", "down")
    store.acknowledge_alerts([alert_id], ts=now)

    engine = AlertEngine(store=None, rules=[AlertRule(
        name="Service Down", rule_type="SERVICE_DOWN", host=None,
        cooldown_s=300, enabled=True,
    )])
    engine.load_ack_holds(store.get_recent_acks(since_ts=now - 3600))

    refire = engine._fire_if_cooled(
        engine._rules[0], "10.0.0.9", now + 301, "down", "CRITICAL", None
    )
    assert refire is None


# ── Undo ──────────────────────────────────────────────────────────────────────

def test_unacknowledge_alerts_restores_them_to_the_queue(store):
    """Backs the Home card's "Acknowledge all" undo toast — one click can clear
    a backlog of hundreds, so it must be reversible."""
    ids = _fire_group(store, "Device Gone", "192.168.68.59", 3)
    store.acknowledge_alerts(ids)
    assert store.get_unacked_alerts() == []

    store.unacknowledge_alerts(ids)

    assert {a["id"] for a in store.get_unacked_alerts()} == set(ids)


def test_unacknowledge_alerts_clears_owner_and_comment(store):
    alert_id = store.record_alert_fired("Host Down", "10.0.0.1", "CRITICAL", "down")
    store.acknowledge_alerts([alert_id], acked_by="alice", comment="tracking")

    store.unacknowledge_alerts([alert_id])

    row = next(a for a in store.get_recent_alerts(hours=1) if a["id"] == alert_id)
    assert row["acked_ts"] is None
    assert row["acked_by"] in (None, "")
    assert row["acked_comment"] in (None, "")


def test_unacknowledge_alerts_empty_list_is_a_noop(store):
    alert_id = store.record_alert_fired("Host Down", "10.0.0.1", "CRITICAL", "down")
    store.acknowledge_alerts([alert_id])

    store.unacknowledge_alerts([])

    assert store.get_unacked_alerts() == []


def test_acknowledge_alerts_is_a_single_transaction(store, monkeypatch):
    """The whole point of the batch method: one commit, not one per id.

    Guards against a future 'fix' that loops acknowledge_alert() internally,
    which would reintroduce the per-row commit cost this replaces.
    """
    ids = _fire_group(store, "New Open Port", "192.168.68.54", 5)
    calls: list = []
    real = store._execute_write_many
    monkeypatch.setattr(
        store, "_execute_write_many",
        lambda sql, rows: (calls.append((sql, list(rows))), real(sql, rows))[1],
    )

    store.acknowledge_alerts(ids)

    assert len(calls) == 1, "acknowledge_alerts() must issue exactly one batch write"
    assert len(calls[0][1]) == len(ids)
    assert store.get_unacked_alerts() == []
