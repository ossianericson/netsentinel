"""Device Identity — deterministic arbitration + hysteresis (RULE-EXP1, RULE-T3).

The defect these tests pin, measured live on 2026-08-13 against the reference network:

`arbitrate()` groups claims by device_type, scores each group, then does
`scored.sort(key=score, reverse=True)`. Python's sort is *stable*, so an exact score
tie resolves to whichever group was inserted first -- and insertion order follows the
order claims arrived in. The vendor heuristic scores 0.40 and a passive "low" service
announcement also scores 0.40, so these claims tie exactly, and the winner is decided by
which source happened to run first that scan.

Measured consequence on `00:22:61:d8:ee:58` (a Frontier Silicon audio module, hostname
`Barnens-rum`), whose vendor evidence says Smart Speaker / Audio at 0.40:

    2026-08-11 19:08:42  Smart Speaker / Audio -> File / NAS Server
    2026-08-11 19:08:55  File / NAS Server     -> Smart TV
    2026-08-12 07:57:50  Smart Speaker / Audio -> Smart TV
    2026-08-13 11:20:30  Unknown Device        -> File / NAS Server

That is the Phase 0 complaint -- "it converges on whichever writer fired last" -- alive
inside the function written to end it. arbitrate() did not remove the non-determinism; it
moved it from "last writer wins" to "first claim in the list wins on ties".

The tie also drives the confidence collapse: `_CONFLICT_PENALTY` scales by how close the
runner-up scored, so a near-tie loses almost the whole 0.35. The LG TV's stored 0.085 is
exactly the 0.40-vs-0.30 case.
"""
import itertools

import pytest

from modules.device_classification import (
    ClassificationClaim,
    arbitrate,
    arbitrate_stable,
)

AUDIO = "Smart Speaker / Audio"
NAS = "File / NAS Server"
TV = "Smart TV"


def _vendor_claim(device_type=AUDIO, confidence=0.40):
    """What an OUI vendor match produces -- identity evidence."""
    return ClassificationClaim(
        device_type=device_type, confidence=confidence,
        source="heuristic", evidence="vendor",
    )


def _passive_claim(device_type=NAS, confidence=0.40, protocol="mdns", evidence="_smb._tcp"):
    """What a service announcement produces -- capability evidence."""
    return ClassificationClaim(
        device_type=device_type, confidence=confidence,
        source=f"passive-{protocol}", evidence=evidence,
    )


# ── Order independence ───────────────────────────────────────────────────────

def test_the_shipped_arbiter_is_order_dependent_on_a_tie():
    """Characterisation of the defect itself, so the fix has something to beat.

    If this ever starts failing, arbitrate() gained a tie-break of its own and this
    whole module needs rereading -- it is not a test of desired behaviour.
    """
    a, b = _vendor_claim(), _passive_claim()
    assert arbitrate([a, b]).device_type == AUDIO
    assert arbitrate([b, a]).device_type == NAS


@pytest.mark.parametrize("claims", list(itertools.permutations([
    _vendor_claim(AUDIO),
    _passive_claim(NAS),
    _passive_claim(TV, protocol="ssdp", evidence="remoteuiclient"),
])))
def test_verdict_is_independent_of_claim_order(claims):
    """Every permutation of the same claim set must produce the same verdict.

    This is the invariant, not an example: a classifier whose answer depends on
    packet arrival order cannot be stable across scans by construction.
    """
    verdict = arbitrate_stable(list(claims))
    assert verdict.device_type == AUDIO


def test_confidence_is_also_order_independent():
    a, b = _vendor_claim(), _passive_claim()
    assert arbitrate_stable([a, b]).confidence == arbitrate_stable([b, a]).confidence


# ── Identity outranks capability at equal score ──────────────────────────────

def test_identity_evidence_beats_capability_evidence_at_equal_score():
    """A vendor OUI proves who MADE the device; an SMB announcement proves only
    what it can DO. At equal score the identity claim must win."""
    for claims in ([_vendor_claim(), _passive_claim()],
                   [_passive_claim(), _vendor_claim()]):
        assert arbitrate_stable(claims).device_type == AUDIO


def test_registry_still_wins_a_tie_over_the_heuristic():
    """Identity A4 relied on stable-sort order to keep a registry tie on the
    registry's answer. That intent must survive the new tie-break."""
    registry = ClassificationClaim(
        device_type=NAS, confidence=0.40, source="registry",
        evidence="MAC registry model-specific match",
    )
    heuristic = _vendor_claim(AUDIO, 0.40)
    for claims in ([registry, heuristic], [heuristic, registry]):
        assert arbitrate_stable(claims).device_type == NAS


def test_a_genuinely_stronger_capability_claim_still_wins():
    """The tie-break applies to ties only -- it must not become a veto that lets
    a weak vendor guess outrank a high-confidence service fingerprint."""
    strong = _passive_claim(NAS, confidence=0.85, evidence="_afpovertcp._tcp")
    assert arbitrate_stable([_vendor_claim(AUDIO, 0.40), strong]).device_type == NAS


# ── Hysteresis: a challenger must earn the flip ──────────────────────────────

def test_incumbent_survives_an_equally_scored_challenger():
    """Equal-scoring disagreement is not evidence the stored label is wrong."""
    verdict = arbitrate_stable([_passive_claim(NAS, 0.40)], incumbent=AUDIO)
    assert verdict.device_type == AUDIO


def test_incumbent_survives_a_challenger_inside_the_margin():
    verdict = arbitrate_stable(
        [_passive_claim(NAS, 0.45)], incumbent=AUDIO, flip_margin=0.10,
    )
    assert verdict.device_type == AUDIO


def test_clearly_stronger_challenger_still_replaces_the_incumbent():
    """Hysteresis must not freeze a wrong label forever."""
    verdict = arbitrate_stable(
        [_passive_claim(NAS, 0.85)], incumbent=AUDIO, flip_margin=0.10,
    )
    assert verdict.device_type == NAS


def test_an_unevidenced_incumbent_does_not_block_a_real_claim():
    """Hysteresis must defend a WELL-EVIDENCED stored label, not merely a stored
    one -- otherwise it protects exactly the damage the order-dependence bug did.

    Measured on the reference inventory: all 12 rows whose stored label the fix
    disagrees with carry confidence 0.0, the residue of a tie the conflict
    penalty crushed to ~0.05. Defending those at a flat baseline froze the bug in
    place; `00:22:61:d8:ee:58` kept "File / NAS Server" under the very fix
    written to correct it.
    """
    verdict = arbitrate_stable(
        [_vendor_claim(AUDIO, 0.40)], incumbent=NAS, incumbent_confidence=0.0,
    )
    assert verdict.device_type == AUDIO


def test_a_well_evidenced_incumbent_is_still_defended():
    """The other half: a registry-grade stored label must not be displaced by an
    ordinary vendor guess."""
    verdict = arbitrate_stable(
        [_vendor_claim(AUDIO, 0.40)], incumbent=NAS, incumbent_confidence=0.90,
    )
    assert verdict.device_type == NAS


def test_flip_decision_uses_the_pre_penalty_score():
    """The conflict penalty exists to REPORT uncertainty, not to decide the flip.
    Reusing the penalised number as the threshold made a contested winner
    unable to clear even a zero-confidence incumbent (0.40 - 0.35 = 0.05)."""
    verdict = arbitrate_stable(
        [_vendor_claim(AUDIO, 0.40), _passive_claim(NAS, 0.40)],
        incumbent=NAS, incumbent_confidence=0.0,
    )
    assert verdict.device_type == AUDIO
    # ...while the REPORTED confidence still shows the disagreement.
    assert verdict.confidence < 0.40


def test_uninformative_incumbent_never_blocks_a_real_claim():
    """"Unknown Device" is an absence of an answer, not an incumbent to defend."""
    for incumbent in ("", "Unknown Device", "unknown device"):
        verdict = arbitrate_stable([_vendor_claim(AUDIO, 0.30)], incumbent=incumbent)
        assert verdict.device_type == AUDIO


def test_no_informative_claims_keeps_the_incumbent():
    """"This scan learned nothing" is not evidence the stored label is wrong --
    it is the strongest case for leaving it alone.

    This test originally asserted the opposite, and the full-inventory replay is
    what corrected it: the early return for "no informative claims" bypassed
    hysteresis, so 6 rows with a randomized MAC and no hostname -- nothing for
    the heuristic to work from -- had real labels (iPhone / iPad, Smart TV,
    Video Doorbell) blanked to Unknown Device on a scan that observed nothing
    about them at all.
    """
    verdict = arbitrate_stable([], incumbent=AUDIO, incumbent_confidence=0.30)
    assert verdict.device_type == AUDIO
    assert verdict.confidence == 0.30


def test_no_claims_and_no_incumbent_is_unknown():
    verdict = arbitrate_stable([])
    assert verdict.device_type == "Unknown Device"
    assert verdict.confidence == 0.0


# ── The live device this was found on ────────────────────────────────────────

def test_frontier_silicon_audio_device_is_not_a_nas():
    """00:22:61:d8:ee:58 / Barnens-rum, with the ports it really has open (80,
    8080 -- 445 and 548 were probed closed), plus the competing passive claim.

    The whole point of the fix, expressed as the device that exposed it.
    """
    from modules.device_classification import claims_from_scan

    claims = list(claims_from_scan(
        mac="00:22:61:d8:ee:58",
        vendor="Frontier Silicon Ltd",
        hostname="Barnens-rum",
        open_ports={80, 8080},
    ))
    claims.append(_passive_claim(NAS, 0.40))
    for ordering in (claims, list(reversed(claims))):
        assert arbitrate_stable(ordering).device_type == AUDIO


# ── DLNA MediaServer proves a capability, not a product ─────────────────────

def test_dlna_mediaserver_makes_no_product_claim():
    """`urn:schemas-upnp-org:device:mediaserver` claimed "File / NAS Server" at
    0.40 -- exactly tying the vendor-identity tier and feeding the oscillation.

    Phases 1-6 neutralised the media RENDERER announcement (it ships in anything
    that can play a stream) and recorded it as a capability, but left its mirror
    image, the media SERVER, making a product claim. A DLNA MediaServer ships in
    NAS boxes, PCs, TVs, phones and -- measured live on 192.168.68.56 -- in a
    Frontier Silicon internet-radio module, which is not a file server by any
    reading. It proves the device can serve media; that is a capability.

    Real NAS evidence is unaffected: _smb._tcp, _afpovertcp._tcp, _nfs._tcp, the
    synology|qnap|... vendor rule and the {445,548} ports rule all still fire.
    """
    from modules.passive_observer import _CAPABILITY_LABELS, _SSDP_HINTS

    key = "urn:schemas-upnp-org:device:mediaserver"
    hint, _confidence = _SSDP_HINTS[key]
    assert hint == "", "a media server announcement must make no product claim"
    assert _CAPABILITY_LABELS.get(key), "...but must still record the capability"


def test_a_mediaserver_observation_yields_no_classification_claim():
    from modules.device_classification import claim_from_passive
    from modules.passive_observer import PassiveObservation, _CAPABILITY_LABELS

    key = "urn:schemas-upnp-org:device:mediaserver"
    obs = PassiveObservation(
        ip="192.168.68.56", mac="00:22:61:d8:ee:58", protocol="ssdp",
        service_type=key + ":1", device_hint="", confidence="low",
        capability=_CAPABILITY_LABELS[key],
    )
    assert claim_from_passive(obs) is None


# ── classify_with_evidence(): highest-scoring rule, not first-listed ─────────

def test_a_higher_scoring_rule_beats_an_earlier_listed_one():
    """_RULES is a hand-ordered list and classify_with_evidence() returns on the
    FIRST match, so precedence is list position rather than evidence strength.

    Measured: ports {445,548} scores 0.20 and sits in the "Servers" block, ahead
    of the vendor rule that would have scored 0.40 -- so the weaker claim wins and
    the vendor evidence is discarded entirely.
    """
    from modules.device_classifier import classify_with_evidence

    result = classify_with_evidence(
        vendor="Frontier Silicon Ltd",
        hostname="Barnens-rum",
        open_ports={445, 548},
        best_rule=True,
    )
    assert result.device_type == AUDIO
    assert result.confidence >= 0.40
    assert "vendor" in result.evidence


def test_best_rule_defaults_off_so_the_shipped_path_is_byte_identical():
    from modules.device_classifier import classify_with_evidence

    shipped = classify_with_evidence(
        vendor="Frontier Silicon Ltd", hostname="Barnens-rum",
        open_ports={445, 548},
    )
    assert shipped.device_type == NAS
