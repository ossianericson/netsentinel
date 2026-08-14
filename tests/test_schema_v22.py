"""
Schema v22 — the six alert_fired fields record_alert_fired() used to drop, and
the four known_device columns the Signal Quality program needs.

Before this, `record_alert_fired()` persisted 6 of AlertFired's 12 fields, so
alert history could not tell a resolution from an alert except by inferring it
from `severity == 'HEALTHY'`, and nothing recorded the evidence or confidence
behind a claim. `known_device` likewise had nowhere to record presence-episode
state (the LEFT edge trigger re-derived it with a query per absent device per
scan) or a materialised importance tier for ranking.
"""
from __future__ import annotations

import json
import time

import pytest

from modules.alert_types import AlertFired
from modules.metric_store import MetricStore
from modules.scan_persistence import persist_alert


@pytest.fixture
def store(tmp_path):
    s = MetricStore(db_path=tmp_path / "v22.db")
    yield s
    s.close()


def _columns(store: MetricStore, table: str) -> set:
    return {r[1] for r in store._execute_read(f"PRAGMA table_info({table})", ())}


# ── Schema shape ─────────────────────────────────────────────────────────────

class TestSchemaShape:
    def test_schema_is_at_least_v22(self):
        """This file asserts v22's SHAPE survives, not that v22 is current.

        Pinned to `== 22` originally, which turns every later schema bump into
        an unrelated failure in a file that has nothing to say about it -- the
        column assertions below are the real subject. tests/
        test_metric_store_schema.py owns the current-version pin.
        """
        from modules.metric_store_schema import _SCHEMA_VERSION
        assert _SCHEMA_VERSION >= 22

    def test_alert_fired_carries_the_six_dropped_fields(self, store):
        cols = _columns(store, "alert_fired")
        missing = {
            "confidence", "evidence_json", "dedup_key",
            "resolved_ts", "is_resolution", "value",
        } - cols
        assert not missing, f"alert_fired is missing {sorted(missing)}"

    def test_known_device_carries_the_four_new_columns(self, store):
        cols = _columns(store, "known_device")
        missing = {
            "presence_state", "gone_notified_ts",
            "importance_tier", "importance_source",
        } - cols
        assert not missing, f"known_device is missing {sorted(missing)}"

    def test_migration_is_additive_on_a_v21_database(self, tmp_path):
        """A database created before v22 gains the columns without losing rows.

        The whole migration framework here is ALTER TABLE ADD COLUMN, so the
        risk is not data loss but a migration that silently fails and leaves
        the reader selecting a column that does not exist.
        """
        import sqlite3
        db = tmp_path / "legacy.db"
        # Recent, not epoch 1: MetricStore prunes on init, so a 1970 row would
        # be legitimately deleted and the test would measure retention, not
        # the migration.
        legacy_ts = int(time.time()) - 3600
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE alert_fired (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, "
            "rule_name TEXT NOT NULL, host TEXT NOT NULL DEFAULT '', "
            "severity TEXT NOT NULL DEFAULT 'WARNING', message TEXT NOT NULL DEFAULT '', "
            "acked_ts INTEGER, acked_by TEXT, escalated INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO alert_fired (ts, rule_name, host, severity, message) "
            "VALUES (?, 'Legacy', '10.0.0.1', 'CRITICAL', 'from before v22')",
            (legacy_ts,),
        )
        conn.commit()
        conn.close()

        s = MetricStore(db_path=db)
        try:
            assert {"confidence", "dedup_key", "is_resolution"} <= _columns(s, "alert_fired")
            rows = s.get_recent_alerts(hours=24, limit=10)
            assert [r["message"] for r in rows] == ["from before v22"]
            # Pre-v22 rows have no dedup_key; the reload path must reconstruct
            # it rather than dropping them.
            assert "Legacy::10.0.0.1" in s.get_last_fired_by_rule_host(max_age_s=86400)
        finally:
            s.close()


# ── record_alert_fired / persist_alert round-trip ────────────────────────────

class TestAlertRoundTrip:
    def test_record_alert_fired_persists_confidence_value_and_evidence(self, store):
        now = int(time.time())
        store.record_alert_fired(
            "Host Down", "192.168.68.1", "CRITICAL", "gateway is unreachable",
            ts=now, rule_type="HOST_DOWN",
            value=-1.0, confidence=0.75,
            evidence_json=json.dumps({"consecutive": 1, "basis": "1 observation"}),
            dedup_key="Host Down::192.168.68.1",
        )
        row = store.get_recent_alerts(hours=1)[0]
        assert row["value"] == -1.0
        assert row["confidence"] == 0.75
        assert json.loads(row["evidence_json"])["consecutive"] == 1
        assert row["dedup_key"] == "Host Down::192.168.68.1"
        assert row["is_resolution"] == 0

    def test_persist_alert_carries_every_alertfired_field(self, store):
        alert = AlertFired(
            rule_name="Infrastructure Unreachable",
            rule_type="INFRA_UNREACHABLE",
            host="192.168.254.1",
            message="the modem stopped answering",
            severity="CRITICAL",
            ts=int(time.time()),
            value=90.0,
            confidence=0.9,
            evidence_json='{"consecutive": 2}',
        )
        persist_alert(store, alert)
        row = store.get_recent_alerts(hours=1)[0]
        assert row["value"] == 90.0
        assert row["confidence"] == 0.9
        assert row["evidence_json"] == '{"consecutive": 2}'
        assert row["dedup_key"] == "Infrastructure Unreachable::192.168.254.1"

    def test_resolution_is_flagged_without_inferring_it_from_severity(self, store):
        """`severity == 'HEALTHY'` was the only way to tell these apart."""
        alert = AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="back online", severity="HEALTHY", ts=int(time.time()),
            is_resolution=True, downtime_s=94,
        )
        persist_alert(store, alert)
        row = store.get_recent_alerts(hours=1)[0]
        assert row["is_resolution"] == 1

    def test_resolution_stamps_resolved_ts_on_the_opening_row(self, store):
        now = int(time.time())
        opened = AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="unreachable", severity="CRITICAL", ts=now - 94,
        )
        persist_alert(store, opened)
        closed = AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="back online", severity="HEALTHY", ts=now,
            is_resolution=True, downtime_s=94,
        )
        persist_alert(store, closed)

        rows = {r["message"]: r for r in store.get_recent_alerts(hours=1)}
        assert rows["unreachable"]["resolved_ts"] == now, (
            "the opening row should carry when it was closed, so history can "
            "measure an outage without pairing rows by hand"
        )
        assert rows["back online"]["resolved_ts"] is None

    def test_resolution_only_closes_its_own_dedup_key(self, store):
        now = int(time.time())
        for host in ("10.0.0.5", "10.0.0.6"):
            persist_alert(store, AlertFired(
                rule_name="Host Down", rule_type="HOST_DOWN", host=host,
                message=f"down {host}", severity="CRITICAL", ts=now - 60,
            ))
        persist_alert(store, AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="up again", severity="HEALTHY", ts=now, is_resolution=True,
        ))
        rows = {r["message"]: r for r in store.get_recent_alerts(hours=1)}
        assert rows["down 10.0.0.5"]["resolved_ts"] == now
        assert rows["down 10.0.0.6"]["resolved_ts"] is None

    def test_resolution_closes_only_the_most_recent_open_episode(self, store):
        """Two outages, two closures — the first must not be re-stamped."""
        now = int(time.time())
        persist_alert(store, AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="outage one", severity="CRITICAL", ts=now - 400))
        persist_alert(store, AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="closed one", severity="HEALTHY", ts=now - 300,
            is_resolution=True))
        persist_alert(store, AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="outage two", severity="CRITICAL", ts=now - 200))
        persist_alert(store, AlertFired(
            rule_name="Host Down", rule_type="HOST_DOWN", host="10.0.0.5",
            message="closed two", severity="HEALTHY", ts=now,
            is_resolution=True))

        rows = {r["message"]: r for r in store.get_recent_alerts(hours=1)}
        assert rows["outage one"]["resolved_ts"] == now - 300
        assert rows["outage two"]["resolved_ts"] == now


# ── Restart-safe dedup ───────────────────────────────────────────────────────

class TestLastFiredReload:
    def test_returns_newest_ts_per_dedup_key(self, store):
        now = int(time.time())
        for offset in (300, 120, 30):
            store.record_alert_fired(
                "Host Down", "10.0.0.9", "CRITICAL", "down",
                ts=now - offset, rule_type="HOST_DOWN",
                dedup_key="Host Down::10.0.0.9",
            )
        store.record_alert_fired(
            "Mesh Degraded", "mesh", "WARNING", "node offline",
            ts=now - 10, rule_type="MESH_DEGRADED", dedup_key="Mesh Degraded::mesh",
        )
        last = store.get_last_fired_by_rule_host(max_age_s=3600)
        assert last["Host Down::10.0.0.9"] == now - 30
        assert last["Mesh Degraded::mesh"] == now - 10

    def test_ignores_rows_older_than_the_window(self, store):
        now = int(time.time())
        store.record_alert_fired(
            "Host Down", "10.0.0.9", "CRITICAL", "ancient",
            ts=now - 100_000, rule_type="HOST_DOWN",
            dedup_key="Host Down::10.0.0.9",
        )
        assert store.get_last_fired_by_rule_host(max_age_s=3600) == {}

    def test_resolutions_do_not_seed_the_cooldown(self, store):
        """A resolution is not a firing — seeding it would mute the next real
        alert for a whole cooldown after every recovery."""
        now = int(time.time())
        store.record_alert_fired(
            "Host Down", "10.0.0.9", "HEALTHY", "back online",
            ts=now - 5, rule_type="HOST_DOWN",
            dedup_key="Host Down::10.0.0.9", is_resolution=True,
        )
        assert store.get_last_fired_by_rule_host(max_age_s=3600) == {}


# ── Importance tier cache ────────────────────────────────────────────────────

class TestImportanceTierCache:
    def test_refresh_recomputes_rather_than_trusting_the_stored_value(self, store):
        """The migration must RECOMPUTE. A row carrying a wrong stored tier is
        exactly the state this cache is introduced into — the reference
        database's `inferred_role` was wrong for 8 of 13 devices."""
        store.upsert_known_device(
            mac="01:00:5e:7f:ff:fa", ip="239.255.255.250", vendor=None,
        )
        store._execute_write(
            "UPDATE known_device SET importance_tier = 'critical', "
            "importance_source = 'inferred' WHERE mac = ?",
            ("01:00:5e:7f:ff:fa",),
        )
        store.refresh_importance_tiers()
        tiers = store.get_importance_tiers()
        assert tiers["01:00:5e:7f:ff:fa"] == "transient", (
            "a multicast group must not keep a stored 'critical' tier"
        )

    def test_tiers_are_keyed_by_both_ip_and_mac(self, store):
        store.upsert_known_device(
            mac="f4:f5:d8:aa:bb:cc", ip="192.168.68.64",
            vendor="Google Nest / Nest Wifi / Google Wifi Router",
            hostname="nestwifi",
        )
        store.refresh_importance_tiers()
        tiers = store.get_importance_tiers()
        assert tiers["f4:f5:d8:aa:bb:cc"] == "critical"
        assert tiers["192.168.68.64"] == "critical"

    def test_highest_tier_wins_when_one_ip_has_several_macs(self, store):
        """Mirrors get_device_importance_tier(): the reference network has three
        MACs at 192.168.68.64, one of them the mesh AP."""
        store.upsert_known_device(
            mac="f4:f5:d8:aa:bb:cc", ip="192.168.68.64",
            vendor="Google Nest / Nest Wifi / Google Wifi Router",
            hostname="nestwifi",
        )
        store.upsert_known_device(
            mac="7a:11:22:33:44:55", ip="192.168.68.64", vendor=None,
        )
        store.refresh_importance_tiers()
        assert store.get_importance_tiers()["192.168.68.64"] == "critical"

    def test_cache_agrees_with_the_live_gate(self, store):
        """The gate never reads the cache, so they can drift. If they ever
        disagree the cache is misinforming the ranking layer."""
        store.upsert_known_device(
            mac="f4:f5:d8:aa:bb:cc", ip="192.168.68.64",
            vendor="Google Nest / Nest Wifi / Google Wifi Router",
            hostname="nestwifi",
        )
        store.refresh_importance_tiers()
        assert (
            store.get_importance_tiers()["192.168.68.64"]
            == store.get_device_importance_tier("192.168.68.64")
        )


# ── Presence episodes ────────────────────────────────────────────────────────

class TestPresenceState:
    def test_presence_state_round_trips(self, store):
        store.upsert_known_device(mac="aa:bb:cc:dd:ee:ff", ip="10.0.0.4")
        store.set_presence_state("aa:bb:cc:dd:ee:ff", "absent", gone_notified_ts=1234)
        row = store.get_known_devices()["aa:bb:cc:dd:ee:ff"]
        assert row.presence_state == "absent"
        assert row.gone_notified_ts == 1234

    def test_returning_clears_the_gone_notification_stamp(self, store):
        store.upsert_known_device(mac="aa:bb:cc:dd:ee:ff", ip="10.0.0.4")
        store.set_presence_state("aa:bb:cc:dd:ee:ff", "absent", gone_notified_ts=1234)
        store.set_presence_state("aa:bb:cc:dd:ee:ff", "present", gone_notified_ts=None)
        row = store.get_known_devices()["aa:bb:cc:dd:ee:ff"]
        assert row.presence_state == "present"
        assert row.gone_notified_ts is None, (
            "a stale stamp would suppress the LEFT for the device's NEXT absence"
        )
