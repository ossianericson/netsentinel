"""
Tests for tools/alert_replay.py — the Signal Quality Program's measurement harness.

The harness is what makes "is the app noisy?" a number instead of an opinion, so
its own arithmetic has to be trustworthy. These tests run against a synthetic
database built from the real schema (`_DDL`), reproducing the defect patterns
found in the live database so the counts are meaningful rather than arbitrary.

Several assertions here are *characterization* tests: they pin current, defective
behaviour (level-triggered HOST_DOWN, duplicate reporting of one outage) so that a
later phase changing it produces a visible, deliberate test update rather than a
silent drift. Each is labelled.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.metric_store_schema import _DDL  # noqa: E402
from tools import alert_replay  # noqa: E402

# A fixed base timestamp keeps every count in this file deterministic.
BASE_TS = 1_780_000_000
CYCLE_S = 60


def _add_cycle(conn, ts, devices):
    """devices: {ip: (state, rtt_ms)} — one availability cycle sharing one ts."""
    for ip, (state, rtt) in devices.items():
        conn.execute(
            "INSERT INTO device_state (ts, ip, mac, hostname, state, rtt_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ts, ip, f"aa:bb:cc:00:00:{ip.split('.')[-1]:0>2}", None, state, rtt),
        )


@pytest.fixture
def replay_db(tmp_path):
    """A synthetic NetSentinel.db carrying the live database's defect patterns."""
    path = tmp_path / "NetSentinel.db"
    conn = sqlite3.connect(path)
    conn.executescript(_DDL)

    # ── known_device: covers every branch of the scope gate ──────────────────
    rows = [
        # mac,                ip,              role,             opt_in
        ("aa:bb:cc:00:00:10", "192.168.1.10", "infrastructure", 0),  # in scope by role
        ("aa:bb:cc:00:00:11", "192.168.1.11", None, 1),              # in scope by opt-in
        ("aa:bb:cc:00:00:12", "192.168.1.12", None, 0),              # out of scope
        ("aa:bb:cc:00:00:13", "192.168.1.13", "gateway", 0),         # in scope by role
        # A second, roleless MAC sharing .11's address. Several devices at one
        # IP is normal (the reference network has three at 192.168.68.64), and
        # a gate that reads only the first row lets row order decide.
        ("aa:bb:cc:00:00:99", "192.168.1.11", None, 0),
    ]
    for mac, ip, role, opt_in in rows:
        conn.execute(
            "INSERT INTO known_device (mac, ip, hostname, vendor, device_type, "
            "first_seen, last_seen, inferred_role, alert_opt_in) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mac, ip, f"host-{ip}", "TestVendor", "Unknown Device",
             BASE_TS, BASE_TS, role, opt_in),
        )

    # ── device_state: 20 cycles ──────────────────────────────────────────────
    # .10 stays UP the whole time            -> must produce no alerts
    # .11 goes DOWN at cycle 5, back UP at 15 -> one real outage episode
    # .12 is DOWN throughout                  -> out of scope, gate must drop it
    # .13 is slow (400 ms, over the 200 ms RTT_THRESHOLD default)
    for i in range(20):
        ts = BASE_TS + i * CYCLE_S
        down = 5 <= i < 15
        _add_cycle(conn, ts, {
            "192.168.1.10": ("UP", 5.0),
            "192.168.1.11": ("DOWN", -1.0) if down else ("UP", 8.0),
            "192.168.1.12": ("DOWN", -1.0),
            "192.168.1.13": ("UP", 400.0),
        })

    # ── device_event: the observed-claim stream ──────────────────────────────
    # One LEFT per hour for the same MAC — the hourly re-fire defect.
    for i in range(6):
        conn.execute(
            "INSERT INTO device_event (ts, ip, mac, event_type, detail) "
            "VALUES (?, ?, ?, 'LEFT', '')",
            (BASE_TS + i * 3600, "192.168.1.12", "aa:bb:cc:00:00:12"),
        )
    conn.execute(
        "INSERT INTO device_event (ts, ip, mac, event_type, detail) "
        "VALUES (?, ?, ?, 'DOWN', '')",
        (BASE_TS + 5 * CYCLE_S, "192.168.1.11", "aa:bb:cc:00:00:11"),
    )
    conn.execute(
        "INSERT INTO device_event (ts, ip, mac, event_type, detail) "
        "VALUES (?, ?, ?, 'RECOVERED', '')",
        (BASE_TS + 15 * CYCLE_S, "192.168.1.11", "aa:bb:cc:00:00:11"),
    )
    conn.execute(
        "INSERT INTO alert_fired (ts, rule_name, host, severity, message, rule_type) "
        "VALUES (?, 'Device Gone', '192.168.1.12', 'WARNING', 'gone', 'DEVICE_GONE')",
        (BASE_TS,),
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def conn(replay_db):
    c = alert_replay.open_db(replay_db)
    yield c
    c.close()


# ── open_db / window resolution ──────────────────────────────────────────────

def test_open_db_is_read_only(conn):
    """The harness must never be able to mutate a live database."""
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO device_event (ts, ip, event_type) VALUES (1, 'x', 'y')")


def test_open_db_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        alert_replay.open_db(tmp_path / "nope.db")


def test_resolve_window_full_history_spans_all_events(conn):
    since, span = alert_replay.resolve_window(conn, None)
    assert since == BASE_TS
    # Events run from BASE_TS to BASE_TS + 5*3600.
    assert span == pytest.approx(5 * 3600 / 86400.0, rel=1e-3)


def test_resolve_window_is_clamped_to_available_history(conn):
    """Asking for more days than exist must not deflate the per-day rate."""
    _, span = alert_replay.resolve_window(conn, days=365)
    assert span == pytest.approx(5 * 3600 / 86400.0, rel=1e-3)


def test_resolve_window_bounded_request_moves_the_floor(conn):
    since_all, _ = alert_replay.resolve_window(conn, None)
    since_short, _ = alert_replay.resolve_window(conn, days=0.05)  # 72 min
    assert since_short > since_all


# ── Observed claims ──────────────────────────────────────────────────────────

def test_observed_claims_counts_device_events_by_type(conn):
    observed = alert_replay.observed_claims(conn, 0)
    assert observed["device_event"]["LEFT"] == 6
    assert observed["device_event"]["DOWN"] == 1
    assert observed["device_event"]["RECOVERED"] == 1


def test_observed_claims_keys_alerts_by_type_and_severity(conn):
    observed = alert_replay.observed_claims(conn, 0)
    assert observed["alert_fired"]["DEVICE_GONE/WARNING"] == 1


def test_observed_claims_respects_the_since_cutoff(conn):
    observed = alert_replay.observed_claims(conn, BASE_TS + 3 * 3600)
    assert observed["device_event"]["LEFT"] == 3  # hours 3, 4, 5 only


def test_hotspots_rank_the_repeating_mac_first(conn):
    hotspots = alert_replay.noise_hotspots(conn, 0)
    top_mac, count, _desc = hotspots["left_repeats"][0]
    assert top_mac == "aa:bb:cc:00:00:12"
    assert count == 6


# ── Scope gate simulation ────────────────────────────────────────────────────

def test_scope_admits_mirrors_is_device_alert_in_scope(conn):
    """Must match metric_store_writes_device.is_device_alert_in_scope exactly:
    infrastructure/gateway role OR explicit opt-in; unknown host is out."""
    admits = alert_replay.scope_admits(conn)
    assert admits["192.168.1.10"] is True   # role=infrastructure
    assert admits["192.168.1.11"] is True   # alert_opt_in=1
    assert admits["192.168.1.12"] is False  # neither
    assert admits["192.168.1.13"] is True   # role=gateway
    assert admits.get("10.0.0.99", False) is False  # no row


def test_scope_admits_is_keyed_by_both_mac_and_ip(conn):
    admits = alert_replay.scope_admits(conn)
    assert admits["aa:bb:cc:00:00:10"] is True
    assert admits["192.168.1.10"] is True


def test_scope_admits_answers_across_every_mac_at_one_ip(conn):
    """Mirrors the same fix in is_device_alert_in_scope: the IP key must not
    depend on which of several MACs at that address the database returned
    first. .11 is opted in; the roleless .99 MAC shares its IP and sorts last."""
    admits = alert_replay.scope_admits(conn)
    assert admits["192.168.1.11"] is True
    assert admits["aa:bb:cc:00:00:99"] is False   # the MAC itself is not in scope
    assert admits["192.168.1.12"] is False


# ── Tier gate simulation (Signal Quality Phase 2) ────────────────────────────

def test_tier_admits_recomputes_the_role_rather_than_trusting_it(conn):
    """.10 and .13 hold infrastructure/gateway in the fixture, exactly as 9 of
    30 devices did in the live database. The stored value is what Phase 2
    replaces, so the tier gate must re-derive it — otherwise the harness would
    measure the old defect and call it the new gate."""
    admits = alert_replay.tier_admits(conn)
    assert admits["192.168.1.10"] is False   # stale infrastructure, no evidence
    assert admits["192.168.1.13"] is False   # stale gateway, .13 is not .1/.254


def test_tier_admits_honours_an_explicit_opt_in(conn):
    """A user opt-in is intent, not inference — it survives the tier gate."""
    assert alert_replay.tier_admits(conn)["192.168.1.11"] is True


def test_tier_admits_is_keyed_by_both_mac_and_ip(conn):
    admits = alert_replay.tier_admits(conn)
    assert admits["aa:bb:cc:00:00:11"] is True
    assert admits["192.168.1.11"] is True


def test_tier_gate_is_at_least_as_quiet_as_the_role_gate(conn):
    """ACCEPTANCE CRITERION 3, in harness form."""
    role_gated, _ = alert_replay.replay(conn, 0, scope_checker=alert_replay.scope_admits(conn))
    tier_gated, _ = alert_replay.replay(conn, 0, scope_checker=alert_replay.tier_admits(conn))
    assert sum(tier_gated.values()) < sum(role_gated.values())


# ── Cycle reconstruction ─────────────────────────────────────────────────────

def test_reconstruct_cycles_groups_rows_sharing_a_timestamp(conn):
    cycles = list(alert_replay.reconstruct_cycles(conn, 0))
    assert len(cycles) == 20
    assert all(len(c["states"]) == 4 for c in cycles)


def test_reconstruct_cycles_preserves_state_and_rtt(conn):
    cycles = list(alert_replay.reconstruct_cycles(conn, 0))
    first, mid = cycles[0], cycles[10]
    assert first["states"]["192.168.1.11"] == "UP"
    assert mid["states"]["192.168.1.11"] == "DOWN"
    assert mid["rtts"]["192.168.1.13"] == 400.0


def test_reconstruct_cycles_emits_the_final_partial_group(conn):
    """The loop yields on timestamp change, so the last group needs its own flush."""
    cycles = list(alert_replay.reconstruct_cycles(conn, 0))
    assert cycles[-1]["ts"] == BASE_TS + 19 * CYCLE_S


# ── Replay ───────────────────────────────────────────────────────────────────

def test_replay_ungated_fires_for_out_of_scope_hosts(conn):
    by_type, by_host = alert_replay.replay(conn, 0, scope_checker=None)
    assert by_type["HOST_DOWN"] > 0
    assert by_host["192.168.1.12"] > 0


def test_replay_scope_gate_drops_out_of_scope_hosts(conn):
    admits = alert_replay.scope_admits(conn)
    _, by_host = alert_replay.replay(conn, 0, scope_checker=admits)
    assert by_host["192.168.1.12"] == 0    # no role, no opt-in
    assert by_host["192.168.1.11"] > 0     # opted in


def test_replay_gate_reduces_total_volume(conn):
    ungated, _ = alert_replay.replay(conn, 0, scope_checker=None)
    gated, _ = alert_replay.replay(conn, 0, scope_checker=alert_replay.scope_admits(conn))
    assert sum(gated.values()) < sum(ungated.values())


def test_replay_never_alerts_on_a_permanently_healthy_host(conn):
    _, by_host = alert_replay.replay(conn, 0, scope_checker=None)
    assert by_host["192.168.1.10"] == 0


def test_replay_counts_slow_host_against_rtt_threshold(conn):
    by_type, _ = alert_replay.replay(conn, 0, scope_checker=None)
    assert by_type["RTT_THRESHOLD"] > 0


def test_replay_separates_resolutions_from_firings(conn):
    by_type, _ = alert_replay.replay(conn, 0, scope_checker=None)
    assert by_type["HOST_DOWN/resolved"] >= 1


# ── Characterization: defects the program exists to fix ──────────────────────
# These pin CURRENT behaviour so a later phase changing it is visible and
# deliberate. When Phase 3 makes HOST_DOWN edge-triggered, these must be updated
# to assert the new one-per-episode contract.

def test_characterizes_level_triggered_host_down(conn):
    """DEFECT: HOST_DOWN re-fires every cooldown while a host stays down.

    .11 has exactly ONE outage episode (10 cycles at 60 s). With a 120 s cooldown
    the engine fires repeatedly for that single episode instead of once.
    Phase 3 must reduce this to 1.
    """
    _, by_host = alert_replay.replay(conn, 0, scope_checker=None)
    assert by_host["192.168.1.11"] > 1


def test_characterizes_one_outage_reported_under_two_rule_types(conn):
    """DEFECT: an unreachable host trips HOST_DOWN (state) and LOSS_THRESHOLD
    (rtt < 0) from the same cycle — one fact, two alert types."""
    by_type, _ = alert_replay.replay(conn, 0, scope_checker=None)
    assert by_type["HOST_DOWN"] > 0
    assert by_type["LOSS_THRESHOLD"] > 0


# ── Summary / CLI ────────────────────────────────────────────────────────────

def test_build_summary_exposes_the_ratchet_keys(conn):
    observed = alert_replay.observed_claims(conn, 0)
    ungated, _ = alert_replay.replay(conn, 0, scope_checker=None)
    gated, _ = alert_replay.replay(conn, 0, scope_checker=alert_replay.scope_admits(conn))
    tiered, _ = alert_replay.replay(conn, 0, scope_checker=alert_replay.tier_admits(conn))
    summary = alert_replay.build_summary(observed, ungated, gated, tiered, span_days=2.0)

    for key in (
        "span_days", "observed_total", "observed_per_day", "observed_by_type",
        "replay_gated_total", "replay_ungated_total", "replay_gated_per_day",
        "replay_by_rule_type",
        "replay_tier_gated_total", "replay_tier_gated_per_day",
        "replay_tier_by_rule_type",
    ):
        assert key in summary
    assert summary["observed_per_day"] == pytest.approx(summary["observed_total"] / 2.0)
    assert summary["replay_tier_gated_total"] <= summary["replay_gated_total"]


def test_main_runs_end_to_end_and_writes_json(replay_db, tmp_path, capsys):
    out = tmp_path / "summary.json"
    rc = alert_replay.main(["--db", str(replay_db), "--json", str(out)])
    assert rc == 0

    printed = capsys.readouterr().out
    assert "OBSERVED CLAIMS" in printed
    assert "REPLAY" in printed

    summary = json.loads(out.read_text(encoding="utf-8"))
    assert summary["observed_total"] > 0
    assert summary["replay_gated_total"] <= summary["replay_ungated_total"]


def test_main_reports_a_missing_database_without_traceback(tmp_path, capsys):
    rc = alert_replay.main(["--db", str(tmp_path / "absent.db")])
    assert rc == 2
    assert "error" in capsys.readouterr().err


def test_report_output_is_ascii_safe(replay_db, tmp_path, capsys):
    """The tool prints to a Windows console (cp1252); non-ASCII output raises
    UnicodeEncodeError there and aborts the run mid-report."""
    alert_replay.main(["--db", str(replay_db)])
    printed = capsys.readouterr().out
    printed.encode("ascii")  # raises UnicodeEncodeError on regression
