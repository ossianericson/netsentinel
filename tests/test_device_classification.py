"""
Tests for modules/device_classification.py -- the Device Identity Program
Phase 3 arbiter.

Written before the implementation (RULE-TDD1): these pin the corroboration
and conflict-resolution shape described in the program plan --
"a claim that two independent sources agree on outranks one high-confidence
source alone" and "a device whose sources genuinely conflict resolves to the
highest-corroborated type and a *lower* confidence, not whichever fired last."
"""
from __future__ import annotations

import pytest

from modules.device_classification import (
    ClassificationClaim,
    ClaimTracker,
    arbitrate,
    claim_from_dhcp,
    claim_from_heuristic,
    claim_from_passive,
    claim_from_registry,
    claim_from_scan,
    claims_from_scan,
)


def _claim(device_type, confidence, source, evidence="") -> ClassificationClaim:
    return ClassificationClaim(device_type=device_type, confidence=confidence,
                                source=source, evidence=evidence)


# ── arbitrate(): base cases ───────────────────────────────────────────────────

class TestArbitrateBaseCases:
    def test_no_claims_is_unknown_device(self):
        result = arbitrate([])
        assert result.device_type == "Unknown Device"
        assert result.confidence == 0.0

    def test_only_uninformative_claims_is_unknown_device(self):
        result = arbitrate([_claim("", 0.9, "heuristic"), _claim("Unknown Device", 0.5, "dhcp")])
        assert result.device_type == "Unknown Device"
        assert result.confidence == 0.0

    def test_unknown_device_is_case_insensitive(self):
        result = arbitrate([_claim("unknown device", 0.9, "heuristic")])
        assert result.device_type == "Unknown Device"

    def test_single_claim_reports_its_own_confidence_unchanged(self):
        result = arbitrate([_claim("Printer", 0.6, "heuristic", "vendor+ports")])
        assert result.device_type == "Printer"
        assert result.confidence == 0.6
        assert "heuristic" in result.sources


# ── arbitrate(): corroboration ────────────────────────────────────────────────

class TestArbitrateCorroboration:
    def test_two_independent_sources_agreeing_score_higher_than_either_alone(self):
        agree = arbitrate([
            _claim("Android Device", 0.5, "dhcp"),
            _claim("Android Device", 0.6, "passive-mdns"),
        ])
        alone = arbitrate([_claim("Android Device", 0.6, "passive-mdns")])
        assert agree.confidence > alone.confidence

    def test_corroboration_score_matches_the_documented_formula(self):
        """score = best*(1 - BONUS) + BONUS when >=2 distinct sources agree.
        Pins the exact constant so a change to it is a deliberate test edit."""
        result = arbitrate([
            _claim("Android Device", 0.5, "dhcp"),
            _claim("Android Device", 0.6, "passive-mdns"),
        ])
        assert result.confidence == pytest.approx(0.6 * 0.75 + 0.25, abs=1e-6)

    def test_same_source_repeated_does_not_corroborate(self):
        """Two claims from the SAME source name are not independent -- the
        whole point of corroboration is agreement across different sources."""
        result = arbitrate([
            _claim("Android Device", 0.5, "dhcp", "first VCI read"),
            _claim("Android Device", 0.6, "dhcp", "second VCI read"),
        ])
        assert result.confidence == 0.6  # just the best of the one source, no bonus

    def test_corroboration_bonus_never_exceeds_1(self):
        result = arbitrate([
            _claim("Router / Gateway", 1.0, "registry"),
            _claim("Router / Gateway", 1.0, "heuristic"),
        ])
        assert result.confidence <= 1.0


# ── arbitrate(): conflict ──────────────────────────────────────────────────────

class TestArbitrateConflict:
    def test_conflicting_claims_resolve_to_the_highest_corroborated_type(self):
        result = arbitrate([
            _claim("Games Console", 0.9, "heuristic"),
            _claim("Smart Speaker / Audio", 0.3, "passive-mdns"),
        ])
        assert result.device_type == "Games Console"

    def test_conflict_reduces_winner_confidence_below_its_own_claim(self):
        """The winning type's OWN claimed confidence (0.9) must not survive a
        genuine conflict unscathed -- the disagreement itself is information."""
        result = arbitrate([
            _claim("Games Console", 0.9, "heuristic"),
            _claim("Smart Speaker / Audio", 0.3, "passive-mdns"),
        ])
        assert result.confidence < 0.9

    def test_conflict_penalty_is_worse_the_closer_the_runner_up(self):
        landslide = arbitrate([
            _claim("Games Console", 0.9, "heuristic"),
            _claim("Smart Speaker / Audio", 0.1, "passive-mdns"),
        ])
        near_tie = arbitrate([
            _claim("Games Console", 0.55, "heuristic"),
            _claim("Smart Speaker / Audio", 0.50, "passive-mdns"),
        ])
        # Landslide keeps a larger share of its original confidence than a near-tie.
        assert (landslide.confidence / 0.9) > (near_tie.confidence / 0.55)

    def test_conflict_confidence_never_goes_negative(self):
        result = arbitrate([
            _claim("Games Console", 0.51, "heuristic"),
            _claim("Smart Speaker / Audio", 0.50, "passive-mdns"),
        ])
        assert result.confidence >= 0.0

    def test_this_is_the_lexmark_scenario_from_the_baseline(self):
        """The reference network's Lexmark printer oscillated Print Server <->
        Streaming Stick <-> Unknown Device. A vendor-backed heuristic claim
        must beat a single weaker passive guess."""
        result = arbitrate([
            _claim("Print Server", 0.6, "heuristic", "vendor:lexmark, any-ports:[9100]"),
            _claim("Streaming Stick", 0.4, "passive-ssdp"),
        ])
        assert result.device_type == "Print Server"


# ── Claim constructors ────────────────────────────────────────────────────────

class TestClaimFromHeuristic:
    def test_wraps_classify_with_evidence(self):
        claim = claim_from_heuristic(vendor="Lexmark", hostname="", open_ports={9100})
        assert claim.device_type == "Print Server"
        assert claim.source == "heuristic"
        assert claim.confidence > 0.0

    def test_unknown_device_still_returns_a_claim(self):
        """Heuristic claims are always returned, even Unknown Device with 0
        confidence -- arbitrate() is what filters uninformative claims, not
        the constructor (a caller may still want to know a source was tried)."""
        claim = claim_from_heuristic(vendor="", hostname="", open_ports=set())
        assert claim.device_type == "Unknown Device"
        assert claim.confidence == 0.0


class TestClaimFromRegistry:
    def test_returns_none_for_empty_mac(self):
        assert claim_from_registry("") is None

    def test_returns_none_when_no_registry_hit(self, monkeypatch):
        monkeypatch.setattr(
            "modules.mac_registry.lookup", lambda mac: {}
        )
        assert claim_from_registry("aa:bb:cc:00:00:01") is None

    def test_returns_a_high_confidence_claim_on_a_hit(self, monkeypatch):
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Streaming Stick"},
        )
        claim = claim_from_registry("aa:bb:cc:00:00:01")
        assert claim.device_type == "Streaming Stick"
        assert claim.source == "registry"
        assert claim.confidence >= 0.8


class TestClaimFromPassive:
    def test_wraps_classify_from_observation(self):
        class _Obs:
            device_hint = "Smart TV"
            confidence = "high"
            protocol = "ssdp"
            service_type = "MediaRenderer"

        claim = claim_from_passive(_Obs())
        assert claim.device_type == "Smart TV"
        assert claim.source == "passive-ssdp"
        assert claim.confidence == 0.85

    def test_returns_none_for_no_hint(self):
        class _Obs:
            device_hint = ""
            confidence = "low"
            protocol = "mdns"
            service_type = ""

        assert claim_from_passive(_Obs()) is None


class TestClaimFromDhcp:
    def test_returns_none_for_no_fingerprint(self):
        assert claim_from_dhcp(None) is None

    def test_maps_high_confidence_string_to_a_float(self):
        from modules.dhcp_fingerprint import DhcpFingerprint
        fp = DhcpFingerprint(device_hint="Windows PC", confidence="high", evidence="VCI: MSFT 5.0")
        claim = claim_from_dhcp(fp)
        assert claim.device_type == "Windows PC"
        assert claim.source == "dhcp"
        assert 0.0 < claim.confidence < 1.0

    def test_high_confidence_scores_above_low(self):
        from modules.dhcp_fingerprint import DhcpFingerprint
        high = claim_from_dhcp(DhcpFingerprint(device_hint="X", confidence="high", evidence=""))
        low = claim_from_dhcp(DhcpFingerprint(device_hint="X", confidence="low", evidence=""))
        assert high.confidence > low.confidence

    def test_returns_none_for_empty_device_hint(self):
        from modules.dhcp_fingerprint import DhcpFingerprint
        fp = DhcpFingerprint(device_hint="", confidence="high", evidence="VCI: unknown")
        assert claim_from_dhcp(fp) is None


class TestClaimFromScan:
    def test_prefers_a_registry_hit_over_the_heuristic(self, monkeypatch):
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Streaming Stick"},
        )
        claim = claim_from_scan("aa:bb:cc:00:00:01", vendor="Lexmark", open_ports={9100})
        assert claim.device_type == "Streaming Stick"
        assert claim.source == "registry"

    def test_falls_back_to_the_heuristic_with_no_registry_hit(self, monkeypatch):
        monkeypatch.setattr("modules.mac_registry.lookup", lambda mac: {})
        claim = claim_from_scan("aa:bb:cc:00:00:01", vendor="Lexmark", open_ports={9100})
        assert claim.device_type == "Print Server"
        assert claim.source == "heuristic"

    def test_empty_mac_skips_registry_and_still_returns_a_claim(self):
        claim = claim_from_scan("", vendor="Lexmark", open_ports={9100})
        assert claim.device_type == "Print Server"
        assert claim.source == "heuristic"


# ── claims_from_scan(): A4 -- both claims reach the arbiter ──────────────────

class TestClaimsFromScan:
    """A4. claim_from_scan() short-circuits on a registry hit and never emits
    the heuristic claim, so arbitrate() -- the one mechanism built to catch
    "sources disagree" -- is bypassed for exactly the source most likely to be
    wrong. claims_from_scan() emits both, so a conflict becomes visible in the
    verdict's confidence and evidence instead of the registry winning in
    silence. Measured on the reference network: 10 of 34 rows carry a registry
    hit, 1 of those genuinely conflicts (docs/spikes/device-identity-baseline.md).
    """

    def test_emits_both_the_registry_and_the_heuristic_claim(self, monkeypatch):
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Streaming Stick"},
        )
        claims = claims_from_scan("aa:bb:cc:00:00:01", vendor="Lexmark", open_ports={9100})
        assert [c.source for c in claims] == ["registry", "heuristic"]
        assert [c.device_type for c in claims] == ["Streaming Stick", "Print Server"]

    def test_registry_claim_is_first_so_ties_resolve_to_it(self, monkeypatch):
        """arbitrate() sorts stably, so an exact score tie goes to whichever
        group was inserted first. Registry-first keeps a tie behaving exactly
        as the pre-A4 short-circuit did."""
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Streaming Stick"},
        )
        claims = claims_from_scan("aa:bb:cc:00:00:01", vendor="Lexmark")
        assert claims[0].source == "registry"

    def test_no_registry_hit_yields_the_heuristic_claim_alone(self, monkeypatch):
        monkeypatch.setattr("modules.mac_registry.lookup", lambda mac: {})
        claims = claims_from_scan("aa:bb:cc:00:00:01", vendor="Lexmark", open_ports={9100})
        assert len(claims) == 1
        assert claims[0].source == "heuristic"

    def test_empty_mac_yields_the_heuristic_claim_alone(self):
        claims = claims_from_scan("", vendor="Lexmark", open_ports={9100})
        assert len(claims) == 1
        assert claims[0].source == "heuristic"

    def test_heuristic_claim_is_emitted_even_when_it_abstains(self, monkeypatch):
        """arbitrate() filters uninformative claims; claims_from_scan() must
        not pre-filter, or a caller loses the record that the source ran."""
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Streaming Stick"},
        )
        claims = claims_from_scan("aa:bb:cc:00:00:01")
        assert len(claims) == 2
        assert claims[1].device_type == "Unknown Device"

    def test_conflict_lowers_confidence_and_names_the_loser(self, monkeypatch):
        """A Raspberry Pi named for the job it does: the registry says Single
        Board Computer at 0.90, the hostname heuristic says File / NAS Server at
        0.30. Pre-A4 the user saw "Single Board Computer, 90%" with no sign the
        sources disagreed.

        Originally written against the reference network's own row,
        d8:3a:dd:de:11:a7 / hostname "PINAS". That spelling no longer reaches
        the NAS rule: the hostname alternatives were anchored so "nas" stops
        matching inside "Jonas" and "Nasrin", and "PINAS" is structurally
        identical to those. The conflict this test exists to demonstrate is
        unchanged -- only the hostname that triggers it.
        """
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Single Board Computer"},
        )
        verdict = arbitrate(claims_from_scan("d8:3a:dd:de:11:a7", hostname="nas-01"))
        assert verdict.device_type == "Single Board Computer"
        assert verdict.confidence < 0.9
        assert any("conflicts with" in e for e in verdict.evidence)
        assert any("File / NAS Server" in e for e in verdict.evidence)

    def test_agreement_raises_confidence_above_a_lone_registry_hit(self, monkeypatch):
        """78:c8:81:d7:9f:fe (PS5-D79FFE, Sony) -- registry and the vendor
        heuristic independently agree on Games Console, which should read as
        MORE certain than the registry alone, not identical to it."""
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Games Console"},
        )
        verdict = arbitrate(claims_from_scan(
            "78:c8:81:d7:9f:fe", vendor="Sony Interactive Entertainment",
        ))
        assert verdict.device_type == "Games Console"
        assert verdict.confidence > 0.9
        assert verdict.sources == frozenset({"registry", "heuristic"})

    def test_gateway_claim_is_withheld_when_the_registry_knows_the_product(self, monkeypatch):
        """Decision D1 (revised after measurement). classify_with_evidence()
        answers is_gateway at confidence 1.0, which would outrank any registry
        entry -- but its answer is about the device's ROLE, and the registry's
        is about the PRODUCT, which already implies that role. They are not
        competing claims, and arbitrate() has no notion of specificity, so it
        would score the specialisation as a conflict and penalise it.

        Measured on the reference network: the Deco gateway
        3c:64:cf:e0:27:02 stores no hostname, so the mesh regex can never fire
        for it and the gateway shortcut always answers the generic
        'Router / Gateway'. Emitting it would demote a correct
        'Mesh Network Node' (registry, 0.90) to a generic label at 0.69 -- on
        the ONLY device the gateway path affects here.
        """
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Mesh Network Node"},
        )
        claims = claims_from_scan(
            "3c:64:cf:e0:27:02", vendor="TP-Link", hostname="", is_gateway=True,
        )
        assert [c.source for c in claims] == ["registry"]
        verdict = arbitrate(claims)
        assert verdict.device_type == "Mesh Network Node"
        assert verdict.confidence == pytest.approx(0.9)

    def test_gateway_with_no_registry_entry_still_gets_its_claim(self, monkeypatch):
        """The withholding above is narrow: a gateway the registry has never
        heard of must still classify as a router, at the heuristic's own
        confidence."""
        monkeypatch.setattr("modules.mac_registry.lookup", lambda mac: {})
        claims = claims_from_scan(
            "aa:bb:cc:00:00:09", vendor="NoName", hostname="", is_gateway=True,
        )
        assert [c.source for c in claims] == ["heuristic"]
        verdict = arbitrate(claims)
        assert verdict.device_type == "Router / Gateway"
        assert verdict.confidence == 1.0

    def test_a_non_gateway_registry_hit_still_emits_both_claims(self, monkeypatch):
        """The gateway carve-out must not leak into the ordinary path -- that
        path is the entire point of A4."""
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Mesh Network Node"},
        )
        claims = claims_from_scan(
            "3c:64:cf:e0:27:02", vendor="TP-Link", hostname="", is_gateway=False,
        )
        assert [c.source for c in claims] == ["registry", "heuristic"]

    def test_singular_claim_from_scan_is_unchanged(self, monkeypatch):
        """claim_from_scan() must keep short-circuiting on the registry hit --
        modules/device_tracker.py::_scan_confidence() depends on it reproducing
        classify_registry_first() exactly, and returns None on any mismatch."""
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Streaming Stick"},
        )
        claim = claim_from_scan("aa:bb:cc:00:00:01", vendor="Lexmark", open_ports={9100})
        assert claim.source == "registry"
        assert claim.device_type == "Streaming Stick"
        assert claim.confidence == 0.9


# ── ClaimTracker ────────────────────────────────────────────────────────────

class TestClaimTracker:
    def test_add_returns_none_for_empty_mac(self):
        tracker = ClaimTracker()
        assert tracker.add("", _claim("Router / Gateway", 0.9, "registry")) is None

    def test_add_none_claim_still_returns_current_verdict(self):
        tracker = ClaimTracker()
        tracker.add("aa:bb:cc:00:00:01", _claim("Printer", 0.6, "heuristic"))
        result = tracker.add("aa:bb:cc:00:00:01", None)
        assert result.device_type == "Printer"

    def test_add_with_no_prior_claims_and_none_returns_none(self):
        tracker = ClaimTracker()
        assert tracker.add("aa:bb:cc:00:00:99", None) is None

    def test_claims_accumulate_and_corroborate_across_calls(self):
        tracker = ClaimTracker()
        mac = "aa:bb:cc:00:00:02"
        first = tracker.add(mac, _claim("Android Device", 0.5, "dhcp"))
        second = tracker.add(mac, _claim("Android Device", 0.6, "passive-mdns"))
        assert second.confidence > first.confidence
        assert tracker.claim_count(mac) == 2

    def test_reset_clears_all_macs(self):
        tracker = ClaimTracker()
        mac = "aa:bb:cc:00:00:03"
        tracker.add(mac, _claim("Printer", 0.6, "heuristic"))
        tracker.reset()
        assert tracker.claim_count(mac) == 0
        assert tracker.add(mac, None) is None

    def test_different_macs_do_not_share_claims(self):
        tracker = ClaimTracker()
        tracker.add("aa:bb:cc:00:00:04", _claim("Printer", 0.9, "heuristic"))
        result = tracker.add("aa:bb:cc:00:00:05", _claim("Smart TV", 0.7, "passive-ssdp"))
        assert result.device_type == "Smart TV"
