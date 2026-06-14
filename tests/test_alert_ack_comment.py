"""
tests/test_alert_ack_comment.py — O2: per-alert acknowledgement with owner + comment.

Covers:
  - acknowledge_alert() writes acked_by and acked_comment to the DB
  - get_recent_alerts() returns acked_comment field
  - get_unacked_alerts() excludes acked rows
  - schema migration: acked_comment column exists on a fresh DB
"""
from __future__ import annotations

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path):
    from modules.metric_store import MetricStore
    db_path = tmp_path / "test.db"
    s = MetricStore(db_path=db_path)
    yield s
    s.close()


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_acknowledge_alert_writes_comment(store):
    alert_id = store.record_alert_fired("Host Down", "192.168.1.1", "CRITICAL", "Host DOWN")
    assert alert_id > 0

    store.acknowledge_alert(alert_id, acked_by="alice", comment="tracking JIRA-42")

    alerts = store.get_recent_alerts(hours=1)
    row = next((a for a in alerts if a["id"] == alert_id), None)
    assert row is not None
    assert row["acked_ts"] is not None
    assert row["acked_by"] == "alice"
    assert row["acked_comment"] == "tracking JIRA-42"


def test_acknowledge_alert_empty_comment(store):
    alert_id = store.record_alert_fired("Host Down", "10.0.0.1", "CRITICAL", "DOWN")
    store.acknowledge_alert(alert_id, acked_by="bob")

    alerts = store.get_recent_alerts(hours=1)
    row = next((a for a in alerts if a["id"] == alert_id), None)
    assert row is not None
    assert row["acked_by"] == "bob"
    assert row.get("acked_comment") in (None, "")


def test_get_unacked_excludes_acked(store):
    id1 = store.record_alert_fired("High RTT", "10.0.0.2", "WARNING", "high rtt")
    id2 = store.record_alert_fired("High RTT", "10.0.0.3", "WARNING", "high rtt")
    store.acknowledge_alert(id1, acked_by="user", comment="")

    unacked = store.get_unacked_alerts()
    unacked_ids = {a["id"] for a in unacked}
    assert id1 not in unacked_ids
    assert id2 in unacked_ids


def test_acked_comment_field_in_recent_alerts(store):
    alert_id = store.record_alert_fired("Service Down", "svc1", "CRITICAL", "svc down")
    store.acknowledge_alert(alert_id, acked_by="carol", comment="expected maintenance")

    recent = store.get_recent_alerts(hours=1)
    row = next((a for a in recent if a["id"] == alert_id), None)
    assert row is not None
    assert "acked_comment" in row
    assert row["acked_comment"] == "expected maintenance"


def test_default_acked_by_is_user(store):
    alert_id = store.record_alert_fired("Host Down", "10.0.0.5", "CRITICAL", "down")
    store.acknowledge_alert(alert_id)

    recent = store.get_recent_alerts(hours=1)
    row = next((a for a in recent if a["id"] == alert_id), None)
    assert row is not None
    assert row["acked_by"] == "user"
