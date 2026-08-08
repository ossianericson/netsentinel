"""
Tests for tools/identity_replay.py -- the Device Identity & Classification
Program's measurement harness (Phase 0), sibling to tests/test_alert_replay.py.

These run against a synthetic database built from the real schema (`_DDL`),
reproducing the defect patterns found in the live database (churn, no-op
audit rows, a device_type that disagrees with its own audit trail, an IP
claimed by two MACs) so the counts are meaningful rather than arbitrary.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.metric_store_schema import _DDL, _MIGRATIONS  # noqa: E402
from tools import identity_replay  # noqa: E402

BASE = "2026-01-01 00:00:00"


def _known_device(conn, mac, ip, hostname, vendor, device_type, confidence=0.0):
    conn.execute(
        "INSERT INTO known_device (mac, ip, hostname, vendor, device_type, "
        "first_seen, last_seen, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (mac, ip, hostname, vendor, device_type, 1_780_000_000, 1_780_000_000, confidence),
    )


def _event(conn, mac, old_value, new_value, ts):
    conn.execute(
        "INSERT INTO device_events (mac, event_type, old_value, new_value, source, ts) "
        "VALUES (?, 'class_changed', ?, ?, 'test', ?)",
        (mac, old_value, new_value, ts),
    )


@pytest.fixture
def replay_db(tmp_path):
    """A synthetic NetSentinel.db carrying the live database's identity defects.

    mac1 (Lexmark printer): 4 class_changed events, 1 a pure no-op, ends on
        "Print Server" in the audit trail while known_device.device_type still
        reads "Unknown Device" -- the exact split the baseline measured.
    mac2 (router): 1 class_changed event, agrees with known_device, confident.
    mac3: a non-randomised OUI MAC sharing mac2's IP (the IP-collision case),
        no audit events, no hostname/vendor either.
    mac4: a locally-administered (randomised) MAC with no hostname/vendor --
        a real device the app cannot name (ANONYMOUS). mac1/mac2 also carry
        the U/L bit (the "aa:bb:cc" test prefix sets it) but stay IDENTIFIED
        because each has a hostname or vendor to be named by.
    mac5: the SSDP multicast group -- not an endpoint at all (NOT_A_DEVICE).
    """
    path = tmp_path / "NetSentinel.db"
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)
    # confidence/mac_randomized/etc. arrive via ALTER TABLE migrations, not the
    # base DDL (they postdate the original known_device CREATE TABLE) -- apply
    # them so a fresh test database has the same columns a real one does.
    for col_def in _MIGRATIONS:
        try:
            conn.execute(col_def)
        except sqlite3.OperationalError:
            pass  # column already exists

    _known_device(conn, "aa:bb:cc:00:00:01", "192.168.1.10", "printer1", "Lexmark",
                   "Unknown Device", confidence=0.0)
    _known_device(conn, "aa:bb:cc:00:00:02", "192.168.1.11", "", "TP-Link",
                   "Router / Gateway", confidence=0.9)
    # A non-randomised (globally-administered) OUI MAC with no hostname/vendor
    # at all -- still IDENTIFIED unconditionally by classify_identity(), unlike
    # mac1/mac2 above whose "aa:bb:cc" prefix actually has the U/L bit set.
    _known_device(conn, "00:11:22:00:00:03", "192.168.1.11", "", "", "", confidence=0.0)
    _known_device(conn, "02:bb:cc:00:00:04", "192.168.1.12", "", "", "Unknown Device",
                   confidence=0.0)
    _known_device(conn, "01:00:5e:7f:ff:fa", "239.255.255.250", "", "", "",
                   confidence=0.0)

    _event(conn, "aa:bb:cc:00:00:01", "", "Print Server", "2026-01-01 00:00:00")
    _event(conn, "aa:bb:cc:00:00:01", "Print Server", "Print Server", "2026-01-01 01:00:00")
    _event(conn, "aa:bb:cc:00:00:01", "Print Server", "Streaming Stick", "2026-01-02 00:00:00")
    _event(conn, "aa:bb:cc:00:00:01", "Streaming Stick", "Print Server", "2026-01-03 00:00:00")
    _event(conn, "aa:bb:cc:00:00:02", "", "Router / Gateway", "2026-01-04 00:00:00")

    conn.commit()
    conn.close()
    return path


@pytest.fixture
def conn(replay_db):
    c = identity_replay.open_db(replay_db)
    yield c
    c.close()


# ── open_db / window resolution ──────────────────────────────────────────────

def test_open_db_is_read_only(conn):
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO device_events (mac, event_type) VALUES ('x', 'y')")


def test_open_db_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        identity_replay.open_db(tmp_path / "nope.db")


def test_resolve_window_full_history_spans_all_events(conn):
    since, span = identity_replay.resolve_window(conn, None)
    assert since == BASE
    assert span == pytest.approx(3.0, rel=1e-6)


def test_resolve_window_is_clamped_to_available_history(conn):
    _, span = identity_replay.resolve_window(conn, days=365)
    assert span == pytest.approx(3.0, rel=1e-6)


def test_resolve_window_bounded_request_moves_the_floor(conn):
    since_all, _ = identity_replay.resolve_window(conn, None)
    since_short, _ = identity_replay.resolve_window(conn, days=1)
    assert since_short > since_all


# ── class-change churn ────────────────────────────────────────────────────────

def test_class_change_totals_counts_events_and_noops(conn):
    since, _ = identity_replay.resolve_window(conn, None)
    totals = identity_replay.class_change_totals(conn, since)
    assert totals["total"] == 5
    assert totals["noop"] == 1


def test_class_change_totals_respects_the_since_cutoff(conn):
    totals = identity_replay.class_change_totals(conn, "2026-01-02 00:00:00")
    assert totals["total"] == 3  # 2026-01-02, 01-03, 01-04 events


def test_hotspots_rank_the_churning_mac_first(conn):
    since, _ = identity_replay.resolve_window(conn, None)
    hot = identity_replay.hotspots(conn, since)
    assert hot[0]["mac"] == "aa:bb:cc:00:00:01"
    assert hot[0]["n"] == 4
    assert hot[0]["distinct_types"] == 2


def test_max_distinct_types_is_the_worst_offender(conn):
    since, _ = identity_replay.resolve_window(conn, None)
    assert identity_replay.max_distinct_types(conn, since) == 2


# ── disagreement ──────────────────────────────────────────────────────────────

def test_disagreement_finds_the_lexmark_split(conn):
    result = identity_replay.disagreement(conn)
    assert result["compared"] == 2  # mac1 and mac2 both have events + a known_device row
    macs = {m["mac"] for m in result["mismatches"]}
    assert macs == {"aa:bb:cc:00:00:01"}
    mismatch = result["mismatches"][0]
    assert mismatch["known_device.device_type"] == "Unknown Device"
    assert mismatch["newest_class_changed"] == "Print Server"


def test_disagreement_uses_the_newest_event_not_the_first(conn):
    """mac1's audit trail visits Print Server -> Print Server -> Streaming Stick
    -> Print Server; the newest (by insertion order) must win, not the first."""
    result = identity_replay.disagreement(conn)
    mismatch = next(m for m in result["mismatches"] if m["mac"] == "aa:bb:cc:00:00:01")
    assert mismatch["newest_class_changed"] == "Print Server"


# ── confidence coverage ────────────────────────────────────────────────────────

def test_confidence_coverage_only_counts_nameable_rows(conn):
    cov = identity_replay.confidence_coverage(conn)
    # eligible: mac1 (hostname+vendor) and mac2 (vendor) -- mac3/mac4/mac5 have neither
    assert cov["eligible"] == 2
    # covered: only mac2 has confidence > 0
    assert cov["covered"] == 1


# ── identity breakdown ──────────────────────────────────────────────────────────

def test_identity_breakdown_classifies_every_known_device_row(conn):
    breakdown = identity_replay.identity_breakdown(conn)
    assert breakdown["identified"] == 3    # mac1/mac2 (named), mac3 (OUI-backed)
    assert breakdown["anonymous"] == 1     # mac4: randomised, no hostname/vendor
    assert breakdown["not_a_device"] == 1  # mac5: SSDP multicast group


# ── IP collisions ────────────────────────────────────────────────────────────

def test_ip_collisions_finds_the_shared_address(conn):
    collisions = identity_replay.ip_collisions(conn)
    assert collisions == [("192.168.1.11", 2)]


def test_device_count_matches_known_device_row_count(conn):
    assert identity_replay.device_count(conn) == 5


# ── Summary / CLI ────────────────────────────────────────────────────────────

def test_build_summary_exposes_the_ratchet_keys(conn):
    since, span = identity_replay.resolve_window(conn, None)
    class_totals = identity_replay.class_change_totals(conn, since)
    hot = identity_replay.hotspots(conn, since)
    max_types = identity_replay.max_distinct_types(conn, since)
    disagree = identity_replay.disagreement(conn)
    confidence = identity_replay.confidence_coverage(conn)
    identity = identity_replay.identity_breakdown(conn)
    collisions = identity_replay.ip_collisions(conn)
    n_devices = identity_replay.device_count(conn)

    summary = identity_replay.build_summary(
        class_totals, hot, disagree, confidence, identity, collisions,
        n_devices, span, max_types,
    )
    for key in (
        "span_days", "device_count", "class_changed_total", "class_changed_noop_total",
        "class_changed_noop_share", "class_changed_per_day", "class_changed_per_device_day",
        "max_distinct_types_by_mac", "hotspots", "device_type_agreement_total",
        "device_type_agreement_count", "device_type_agreement_share",
        "device_type_mismatches", "confidence_eligible", "confidence_covered",
        "confidence_coverage_share", "identity_breakdown", "ip_collision_count",
        "ip_collisions",
    ):
        assert key in summary
    assert summary["class_changed_noop_share"] == pytest.approx(0.2)
    assert summary["max_distinct_types_by_mac"] == 2


def test_main_runs_end_to_end_and_writes_json(replay_db, tmp_path, capsys):
    out = tmp_path / "summary.json"
    rc = identity_replay.main(["--db", str(replay_db), "--json", str(out)])
    assert rc == 0

    printed = capsys.readouterr().out
    assert "CLASS-CHANGE CHURN" in printed
    assert "DISAGREEMENT" in printed

    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["class_changed_total"] == 5
    assert summary["ip_collision_count"] == 1


def test_main_reports_a_missing_database_without_traceback(tmp_path, capsys):
    rc = identity_replay.main(["--db", str(tmp_path / "absent.db")])
    assert rc == 2
    assert "error" in capsys.readouterr().err


def test_report_output_is_ascii_safe(replay_db, capsys):
    """The tool prints to a Windows console (cp1252); non-ASCII output raises
    UnicodeEncodeError there and aborts the run mid-report."""
    identity_replay.main(["--db", str(replay_db)])
    printed = capsys.readouterr().out
    printed.encode("ascii")  # raises UnicodeEncodeError on regression
