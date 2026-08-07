"""
modules/relevance.py — one ranking function for every surface that makes a claim.

Written test-first (RULE-TDD1). The load-bearing constraints, which is what most
of these tests are about:

  * **Ordering only.** score() must never become a severity. RULE-A3's
    Info/Warning/High/Critical and the internal RISK_COLORS scale both stay
    exactly as they are, and relevance must accept BOTH vocabularies without
    inventing a third.
  * **Over-suppression is the failure mode**, per the program plan's own risk
    section. Unknown tier, unknown confidence and unknown severity must all
    behave neutrally — never as "low". A fresh install knows none of them.
"""
from __future__ import annotations

import time

import pytest

from modules.relevance import (
    Claim,
    claim_from_alert_row,
    claim_from_device_event,
    rank,
    score,
)


NOW = 1_800_000_000


def _claim(**kw) -> Claim:
    base = dict(ts=NOW, severity="WARNING")
    base.update(kw)
    return Claim(**base)


# ── Range and vocabulary ─────────────────────────────────────────────────────

class TestScoreRange:
    @pytest.mark.parametrize("severity", [
        "CRITICAL", "HIGH", "WARNING", "MEDIUM", "INFO", "HEALTHY",
        "Critical", "High", "Warning", "Info", "", "NONSENSE",
    ])
    @pytest.mark.parametrize("tier", [None, "critical", "infrastructure",
                                      "personal", "transient", "bogus"])
    def test_score_is_always_a_unit_interval_float(self, severity, tier):
        s = score(_claim(severity=severity, tier=tier), now=NOW)
        assert isinstance(s, float)
        assert 0.0 <= s <= 1.0

    def test_both_severity_vocabularies_are_accepted(self):
        """RULE-A3's UI labels and the engine's own strings must both work —
        relevance sits between the two and may not introduce a third."""
        assert score(_claim(severity="Critical"), now=NOW) == score(
            _claim(severity="CRITICAL"), now=NOW
        )
        assert score(_claim(severity="Warning"), now=NOW) == score(
            _claim(severity="WARNING"), now=NOW
        )

    def test_unknown_severity_does_not_zero_the_claim(self):
        """A severity relevance has never seen must still rank somewhere — a
        zero would silently drop the claim off every surface."""
        assert score(_claim(severity="WAT"), now=NOW) > 0.0

    def test_score_does_not_mutate_the_claim(self):
        c = _claim(severity="CRITICAL")
        score(c, now=NOW)
        assert c.severity == "CRITICAL", "score() must not rewrite severity"


# ── The ordering that matters ────────────────────────────────────────────────

class TestOrdering:
    def test_critical_on_the_gateway_outranks_warning_on_a_transient_device(self):
        """The program's one-sentence goal: quieter about sleeping Chromecasts,
        louder about the router being down."""
        gateway = _claim(severity="CRITICAL", tier="critical", rule_type="HOST_DOWN")
        chromecast = _claim(severity="WARNING", tier="transient",
                            rule_type="HOST_DEGRADED")
        assert score(gateway, now=NOW) > score(chromecast, now=NOW)

    def test_same_severity_ranks_by_tier(self):
        higher = _claim(severity="CRITICAL", tier="critical")
        lower = _claim(severity="CRITICAL", tier="personal")
        assert score(higher, now=NOW) > score(lower, now=NOW)

    def test_same_everything_ranks_by_recency(self):
        recent = _claim(ts=NOW - 60)
        old = _claim(ts=NOW - 86_400 * 3)
        assert score(recent, now=NOW) > score(old, now=NOW)

    def test_an_ancient_claim_still_outranks_nothing_but_keeps_its_order(self):
        older = _claim(ts=NOW - 86_400 * 365)
        newer = _claim(ts=NOW - 86_400 * 300)
        assert score(newer, now=NOW) > score(older, now=NOW) > 0.0

    def test_a_future_timestamp_is_treated_as_now(self):
        """Clock skew between a producer and the renderer must not let a claim
        score above a genuinely current one."""
        assert score(_claim(ts=NOW + 9_999), now=NOW) == score(
            _claim(ts=NOW), now=NOW
        )

    def test_corroborated_outranks_uncorroborated(self):
        assert score(_claim(confidence=0.95), now=NOW) > score(
            _claim(confidence=0.1), now=NOW
        )

    def test_actionable_outranks_unactionable(self):
        assert score(_claim(actionable=True), now=NOW) > score(
            _claim(actionable=False), now=NOW
        )

    def test_acknowledged_ranks_below_unacknowledged(self):
        assert score(_claim(acknowledged=True), now=NOW) < score(
            _claim(acknowledged=False), now=NOW
        )

    def test_a_resolution_ranks_below_the_alert_it_closes(self):
        outage = _claim(severity="CRITICAL", tier="critical", rule_type="HOST_DOWN")
        recovery = _claim(severity="HEALTHY", tier="critical", rule_type="HOST_DOWN")
        assert score(recovery, now=NOW) < score(outage, now=NOW)


# ── Never suppress on absence of information ─────────────────────────────────

class TestNeutralDefaults:
    def test_unknown_tier_is_neutral_not_lowest(self):
        """A device with no known_device row — every device on a fresh install
        — must not be ranked below one explicitly known to be transient."""
        unknown = _claim(tier=None)
        transient = _claim(tier="transient")
        assert score(unknown, now=NOW) > score(transient, now=NOW)

    def test_unparseable_tier_is_treated_as_unknown(self):
        assert score(_claim(tier="bogus"), now=NOW) == score(
            _claim(tier=None), now=NOW
        )

    def test_absent_confidence_does_not_penalise(self):
        """confidence=None means 'no evidence gate on this path', not 'weak'.
        Most rule types have no gate at all."""
        assert score(_claim(confidence=None), now=NOW) >= score(
            _claim(confidence=1.0), now=NOW
        )

    def test_absent_confidence_outranks_low_confidence(self):
        assert score(_claim(confidence=None), now=NOW) > score(
            _claim(confidence=0.1), now=NOW
        )


# ── Dismissal history ────────────────────────────────────────────────────────

class TestDismissalHistory:
    def test_a_repeatedly_dismissed_class_ranks_lower(self):
        c = _claim(rule_type="NEW_DEVICE")
        assert score(c, now=NOW, dismissals={"NEW_DEVICE": 20}) < score(c, now=NOW)

    def test_dismissals_of_another_class_do_not_affect_this_one(self):
        c = _claim(rule_type="HOST_DOWN")
        assert score(c, now=NOW, dismissals={"NEW_DEVICE": 20}) == score(c, now=NOW)

    def test_dismissal_penalty_has_a_floor(self):
        """A class the user always dismisses must still be rankable against its
        own peers — it may sink, never vanish."""
        c = _claim(rule_type="NEW_DEVICE")
        assert score(c, now=NOW, dismissals={"NEW_DEVICE": 10_000}) > 0.0

    def test_dismissal_cannot_reorder_a_critical_below_an_info(self):
        """The user dismissing HOST_DOWN twenty times does not make the router
        going down less important than a speed test finishing."""
        critical = _claim(severity="CRITICAL", tier="critical", rule_type="HOST_DOWN")
        info = _claim(severity="INFO", tier="transient", rule_type="NEW_DEVICE")
        d = {"HOST_DOWN": 50}
        assert score(critical, now=NOW, dismissals=d) > score(info, now=NOW, dismissals=d)


# ── rank() ───────────────────────────────────────────────────────────────────

class TestRank:
    def test_returns_descending_order(self):
        claims = [
            _claim(severity="INFO", tier="transient", host="a"),
            _claim(severity="CRITICAL", tier="critical", host="b"),
            _claim(severity="WARNING", tier="personal", host="c"),
        ]
        assert [c.host for c in rank(claims, now=NOW)] == ["b", "c", "a"]

    def test_is_stable_for_equal_scores(self):
        claims = [_claim(host=str(i)) for i in range(5)]
        assert [c.host for c in rank(claims, now=NOW)] == ["0", "1", "2", "3", "4"]

    def test_empty_input_returns_empty(self):
        assert rank([], now=NOW) == []

    def test_does_not_mutate_the_input_list(self):
        claims = [
            _claim(severity="INFO", host="a"),
            _claim(severity="CRITICAL", host="b"),
        ]
        rank(claims, now=NOW)
        assert [c.host for c in claims] == ["a", "b"]


# ── Adapters ─────────────────────────────────────────────────────────────────

class TestAlertRowAdapter:
    def test_maps_an_alert_fired_row(self):
        row = {
            "ts": NOW - 30, "rule_name": "Host Down", "host": "192.168.68.1",
            "severity": "CRITICAL", "message": "gateway offline",
            "rule_type": "HOST_DOWN", "acked_ts": None, "confidence": 0.75,
        }
        c = claim_from_alert_row(row, tiers={"192.168.68.1": "critical"})
        assert c.ts == NOW - 30
        assert c.severity == "CRITICAL"
        assert c.rule_type == "HOST_DOWN"
        assert c.tier == "critical"
        assert c.confidence == 0.75
        assert c.acknowledged is False

    def test_acked_row_is_marked_acknowledged(self):
        row = {"ts": NOW, "host": "h", "severity": "WARNING",
               "rule_type": "HOST_DOWN", "acked_ts": NOW}
        assert claim_from_alert_row(row).acknowledged is True

    def test_a_rule_type_with_a_cta_is_actionable(self):
        """Actionability is 'does the app know where to send the user', which
        is exactly what the CTA routing table answers."""
        row = {"ts": NOW, "host": "h", "severity": "CRITICAL",
               "rule_type": "HOST_DOWN"}
        assert claim_from_alert_row(row).actionable is True

    def test_survives_a_pre_v22_row_with_no_new_columns(self):
        """Rows written before schema v22 have no confidence/dedup_key. The
        adapter must read them, not raise."""
        row = {"ts": NOW, "rule_name": "Host Down", "host": "h",
               "severity": "CRITICAL", "message": "m", "rule_type": "HOST_DOWN"}
        c = claim_from_alert_row(row)
        assert c.confidence is None
        assert c.acknowledged is False

    def test_unknown_host_gets_no_tier_rather_than_transient(self):
        row = {"ts": NOW, "host": "10.9.9.9", "severity": "WARNING",
               "rule_type": "HOST_DOWN"}
        assert claim_from_alert_row(row, tiers={}).tier is None

    def test_a_malformed_ts_does_not_raise(self):
        row = {"ts": None, "host": "h", "severity": "WARNING", "rule_type": "X"}
        assert isinstance(claim_from_alert_row(row).ts, int)


class TestDeviceEventAdapter:
    def test_maps_a_device_event(self):
        ev = type("Ev", (), {"ts": NOW - 5, "ip": "10.0.0.4",
                             "mac": "aa:bb:cc:dd:ee:ff",
                             "event_type": "JOINED", "detail": "New device"})()
        c = claim_from_device_event(ev, tiers={"10.0.0.4": "personal"})
        assert c.ts == NOW - 5
        assert c.host == "10.0.0.4"
        assert c.tier == "personal"

    def test_event_types_map_onto_the_existing_severity_vocabulary(self):
        """device_event carries no severity column, so the adapter derives one —
        and it must come from RULE-A3's set, not a new one."""
        def _ev(kind):
            return type("Ev", (), {"ts": NOW, "ip": "h", "mac": None,
                                   "event_type": kind, "detail": ""})()
        assert score(claim_from_device_event(_ev("DOWN")), now=NOW) > score(
            claim_from_device_event(_ev("RECOVERED")), now=NOW
        )
        for kind in ("JOINED", "LEFT", "UP", "DOWN", "DEGRADED", "RECOVERED"):
            c = claim_from_device_event(_ev(kind))
            assert c.severity in {"INFO", "WARNING", "HIGH", "CRITICAL", "HEALTHY"}

    def test_falls_back_to_mac_when_the_event_has_no_ip(self):
        ev = type("Ev", (), {"ts": NOW, "ip": "", "mac": "aa:bb:cc:dd:ee:ff",
                             "event_type": "LEFT", "detail": ""})()
        c = claim_from_device_event(ev, tiers={"aa:bb:cc:dd:ee:ff": "personal"})
        assert c.host == "aa:bb:cc:dd:ee:ff"
        assert c.tier == "personal"

    def test_accepts_a_dict_shaped_event(self):
        c = claim_from_device_event(
            {"ts": NOW, "ip": "10.0.0.9", "event_type": "JOINED"}
        )
        assert c.host == "10.0.0.9"


# ── Mixed-surface behaviour ──────────────────────────────────────────────────

def test_a_timeline_mixing_events_and_alerts_puts_the_outage_first():
    """The integration shape every routed surface uses: two source tables, one
    ordering."""
    tiers = {"192.168.68.1": "critical", "10.0.0.4": "transient"}
    alert = claim_from_alert_row(
        {"ts": NOW - 600, "host": "192.168.68.1", "severity": "CRITICAL",
         "rule_type": "HOST_DOWN", "acked_ts": None},
        tiers=tiers,
    )
    joined = claim_from_device_event(
        type("Ev", (), {"ts": NOW - 10, "ip": "10.0.0.4", "mac": None,
                        "event_type": "JOINED", "detail": ""})(),
        tiers=tiers,
    )
    assert rank([joined, alert], now=NOW)[0] is alert, (
        "a 10-minute-old gateway outage must outrank a 10-second-old "
        "transient device joining"
    )


def test_scoring_a_realistic_list_is_not_quadratic():
    """rank() runs on every Timeline/Home render against up to 500 rows."""
    claims = [_claim(host=str(i), ts=NOW - i) for i in range(2000)]
    t0 = time.perf_counter()
    rank(claims, now=NOW)
    assert time.perf_counter() - t0 < 0.5
