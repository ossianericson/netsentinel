"""
device_classification.py -- the arbiter for what NetSentinel calls a device.

Device Identity & Classification Program, Phase 3. The classification
pipeline had five independent writers and no arbiter (see the program plan's
root-cause table): rogue_device's scan, scan_enrichment's own re-classify
pass, the mDNS/SSDP passive listener, the DHCP VCI fingerprinter, and
inventory_page's confidence display (the only one that computed a confidence
-- and then discarded it). Whichever fired last silently became the answer.
Measured on the reference network: 232.5 class_changed events/device-day,
47.5% of them literal no-ops, `known_device.device_type` agreeing with the
newest audit-trail entry for only 23.1% of devices
(docs/spikes/device-identity-baseline.md).

This module owns one function -- arbitrate() -- that takes every claim
currently on the table for a device and returns a single verdict: a
device_type, a confidence, and the evidence behind it. A claim two
independent sources agree on outranks one confident source alone; a device
whose sources genuinely disagree keeps the highest-corroborated type but
loses confidence for the disagreement, rather than flipping to whichever
source happened to run last. Same corroboration shape as modules/evidence.py
-- reused rather than reinvented, per that module's own case against a third
copy of this arithmetic living in the tree.

Pure Python -- no PyQt6, no MetricStore access (ARCH RULE 1). Callers own
persistence and display.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

__all__ = [
    "ClassificationClaim",
    "ArbitratedClassification",
    "arbitrate",
    "claim_from_heuristic",
    "claim_from_registry",
    "claim_from_scan",
    "claims_from_scan",
    "claim_from_passive",
    "claim_from_dhcp",
    "ClaimTracker",
]

# Strings that carry no classification information -- the same "I don't know"
# convention device_identity.py already applies to hostname/vendor.
_UNINFORMATIVE = frozenset({"", "unknown device"})

# Mirrors evidence.py's _BASELINE_CONFIDENCE_BONUS shape: corroboration is
# headroom a single source cannot reach alone (best * (1 - bonus) caps a lone
# claim below 1.0), not a flat addition that could push an already-confident
# single claim past where a genuinely corroborated one lands.
_CORROBORATION_BONUS = 0.25

# How much a genuine type conflict costs the winner's reported confidence,
# scaled by how close the runner-up scored. A landslide loses little; a
# near-tie loses almost the whole penalty, because a near-tie is exactly the
# case where "whichever source happened to run last" used to decide silently
# -- the model should say so with a low confidence, not paper over it.
_CONFLICT_PENALTY = 0.35

# DHCP VCI confidence is a coarse "high"/"low" string (dhcp_fingerprint.py);
# mapped onto the same 0.0-1.0 scale every other claim uses so arbitrate()
# can compare them directly.
_DHCP_CONFIDENCE = {"high": 0.75, "low": 0.35}


# ── Types ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ClassificationClaim:
    """One source's opinion about what a device is.

    device_type  Human-readable label, e.g. "Print Server", "Smart TV".
    confidence   0.0-1.0, this source's own confidence in its answer.
    source       Short source tag: "registry" | "heuristic" | "dhcp" |
                 "passive-<protocol>". Two claims count as independent
                 corroboration only when their source tags differ.
    evidence     One-line human-readable reason, for the evidence trail.
    """
    device_type: str
    confidence: float
    source: str
    evidence: str = ""


@dataclass(frozen=True)
class ArbitratedClassification:
    """The arbiter's verdict for one device."""
    device_type: str
    confidence: float
    evidence: List[str] = field(default_factory=list)
    sources: frozenset = field(default_factory=frozenset)


# ── The arbiter ──────────────────────────────────────────────────────────────

def arbitrate(claims: Sequence[ClassificationClaim]) -> ArbitratedClassification:
    """Combine every claim currently on the table into one verdict.

    Claims are grouped by device_type. Within a group, agreement from two or
    more distinct sources earns a corroboration bonus over the group's single
    best claim; repeated claims from the same source do not (that source is
    just restating its own opinion, not independent evidence). The
    highest-scoring type wins. If more than one type was claimed at all, the
    win is a real conflict and the winner's confidence is reduced -- more so
    the closer the runner-up scored -- because the disagreement itself is
    information the caller should see reflected in the number, not just in
    the evidence text.

    A device with no informative claims (empty list, or every claim is blank
    / "Unknown Device") arbitrates to Unknown Device at confidence 0.0.
    """
    informative = [
        c for c in claims
        if c.device_type and c.device_type.strip().lower() not in _UNINFORMATIVE
    ]
    if not informative:
        return ArbitratedClassification("Unknown Device", 0.0, ["no informative claims"], frozenset())

    by_type: Dict[str, List[ClassificationClaim]] = {}
    for c in informative:
        by_type.setdefault(c.device_type, []).append(c)

    scored: List[tuple] = []
    for device_type, group in by_type.items():
        sources = frozenset(c.source for c in group)
        best = max(c.confidence for c in group)
        if len(sources) >= 2:
            score = min(1.0, best * (1.0 - _CORROBORATION_BONUS) + _CORROBORATION_BONUS)
        else:
            score = best
        scored.append((device_type, score, group, sources))

    scored.sort(key=lambda t: t[1], reverse=True)
    winner_type, winner_score, winner_group, winner_sources = scored[0]

    conflicting = len(scored) > 1
    if conflicting:
        runner_up_score = scored[1][1]
        margin = winner_score - runner_up_score
        penalty = _CONFLICT_PENALTY * (1.0 - min(1.0, max(0.0, margin)))
        winner_score = winner_score - penalty

    evidence = [f"{c.source}: {c.evidence}" if c.evidence else c.source for c in winner_group]
    if conflicting:
        losers = ", ".join(
            f"{t} ({s:.2f} from {'+'.join(sorted(srcs))})" for t, s, _, srcs in scored[1:]
        )
        evidence.append(f"conflicts with: {losers}")

    return ArbitratedClassification(
        device_type=winner_type,
        confidence=round(min(1.0, max(0.0, winner_score)), 3),
        evidence=evidence,
        sources=winner_sources,
    )


def _evidence_tier(claim: ClassificationClaim) -> int:
    """How close this claim's evidence comes to proving IDENTITY (who made the
    device) rather than CAPABILITY (what it can do). Higher wins a score tie.

    The distinction is the whole point: an OUI says who built the hardware and
    cannot change while the device exists; an SMB announcement or an open port
    says only what software happens to be listening today, and every laptop,
    phone and TV can advertise the same things. Scoring them identically is why
    the shipped arbiter had ties to break arbitrarily in the first place.
    """
    source = (claim.source or "").lower()
    if source.startswith("registry"):
        return 3                      # model-specific OUI: the strongest identity
    evidence = (claim.evidence or "").lower()
    if source.startswith("dhcp") or "vendor" in evidence or "hostname" in evidence \
            or evidence.startswith("os:") or ", os:" in evidence:
        return 2                      # names the maker or the machine
    return 1                          # ports / service announcements: capability


# A stored label was itself written by some source, so it is not defended for
# free -- but neither is it a coin toss against a fresh claim of equal strength.
# 0.40 is the vendor-identity tier, i.e. "assume the incumbent was at least as
# well evidenced as an OUI match unless this round proves otherwise". Tuned
# against a full-inventory replay rather than chosen a priori; see
# docs/spikes/device-identity-baseline.md.
_UNCLAIMED_INCUMBENT_SCORE = 0.40

# How far a challenger must exceed the incumbent before the label flips.
_DEFAULT_FLIP_MARGIN = 0.10


def arbitrate_stable(
    claims: Sequence[ClassificationClaim],
    *,
    incumbent: str = "",
    incumbent_confidence: Optional[float] = None,
    flip_margin: float = _DEFAULT_FLIP_MARGIN,
) -> ArbitratedClassification:
    """arbitrate(), with the two properties the shipped version lacks.

    **Order independence.** arbitrate() ends in `scored.sort(key=score,
    reverse=True)`, and Python's sort is stable, so an exact score tie resolves
    to whichever group was inserted first -- which follows the order claims
    arrived in. Since the vendor heuristic and a passive "low" announcement both
    score 0.40, real devices tie constantly and the winner is decided by which
    source happened to run first that scan. Measured on the reference network,
    one audio device cycled Smart Speaker / Audio -> File / NAS Server ->
    Smart TV over three days on unchanged evidence. Ties here break on evidence
    tier (identity over capability), then on a stable alphabetical key, so the
    verdict is a pure function of the claim SET, never its ordering.

    **Hysteresis.** A challenger must beat the incumbent by `flip_margin` to
    replace it. Equal-scoring disagreement is not evidence the stored label is
    wrong, and treating it as though it were is precisely what turned a
    disagreement between two 0.40 sources into an endless relabelling loop. A
    genuinely stronger claim still wins, so this damps oscillation without
    freezing a wrong label.

    Pass `incumbent=""` to arbitrate a device with no stored label yet, and
    `incumbent_confidence=` the confidence that label was stored with -- the
    incumbent is defended at its own evidenced strength, so a well-sourced label
    resists an ordinary guess while an unevidenced one (confidence 0.0, the
    residue of a tie) does not block a correction.
    """
    informative = [
        c for c in claims
        if c.device_type and c.device_type.strip().lower() not in _UNINFORMATIVE
    ]
    held = bool(incumbent) and incumbent.strip().lower() not in _UNINFORMATIVE
    if not informative:
        # A scan that observed nothing is not a scan that disproved the stored
        # label. Measured: 6 rows on the reference inventory have a randomized
        # MAC and no hostname, so the heuristic has nothing to work from every
        # time -- returning Unknown Device here blanked real labels (iPhone /
        # iPad, Smart TV, Video Doorbell) on the strength of no evidence at all.
        if held:
            return ArbitratedClassification(
                device_type=incumbent,
                confidence=round(
                    max(0.0, float(incumbent_confidence)), 3
                ) if incumbent_confidence is not None else 0.0,
                evidence=["stored classification: no new evidence this scan"],
                sources=frozenset(),
            )
        return ArbitratedClassification(
            "Unknown Device", 0.0, ["no informative claims"], frozenset()
        )

    by_type: Dict[str, List[ClassificationClaim]] = {}
    for c in informative:
        by_type.setdefault(c.device_type, []).append(c)

    scored: List[tuple] = []
    for device_type, group in by_type.items():
        sources = frozenset(c.source for c in group)
        best = max(c.confidence for c in group)
        if len(sources) >= 2:
            score = min(1.0, best * (1.0 - _CORROBORATION_BONUS) + _CORROBORATION_BONUS)
        else:
            score = best
        tier = max(_evidence_tier(c) for c in group)
        scored.append((device_type, score, group, sources, tier))

    # Total order: score, then identity-over-capability, then a stable key.
    # The final device_type term is what makes this a function of the claim set
    # alone -- without it two equally tiered, equally scored types would fall
    # back on insertion order and reintroduce the whole defect.
    scored.sort(key=lambda t: (-t[1], -t[4], t[0]))
    winner_type, winner_score, winner_group, winner_sources, _ = scored[0]

    # The penalty expresses "the sources disagreed" in the number the caller
    # DISPLAYS. It is deliberately not what the flip decision below compares:
    # a contested winner is discounted by up to 0.35, which would leave it
    # unable to clear even a zero-confidence incumbent and so freeze exactly
    # the rows the old order-dependence had already got wrong.
    undisputed_score = winner_score
    conflicting = len(scored) > 1
    if conflicting:
        runner_up_score = scored[1][1]
        margin = winner_score - runner_up_score
        penalty = _CONFLICT_PENALTY * (1.0 - min(1.0, max(0.0, margin)))
        winner_score = winner_score - penalty

    evidence = [
        f"{c.source}: {c.evidence}" if c.evidence else c.source for c in winner_group
    ]
    if conflicting:
        losers = ", ".join(
            f"{t} ({s:.2f} from {'+'.join(sorted(srcs))})"
            for t, s, _, srcs, _ in scored[1:]
        )
        evidence.append(f"conflicts with: {losers}")

    # Hysteresis -- only ever between two real labels. An absent or
    # "Unknown Device" incumbent is the absence of an answer, not one to defend.
    if held and winner_type != incumbent:
        incumbent_entry = next((t for t in scored if t[0] == incumbent), None)
        # The incumbent is defended at the confidence it was STORED with -- what
        # some source once stood behind -- and nothing else. Measured on the
        # reference inventory, every row the order-dependent path had got wrong
        # carried confidence 0.0, so a flat defence would have preserved the
        # defect under the guise of stability.
        #
        # Deliberately NOT also credited for re-claiming itself this round: that
        # would hand the incumbent two advantages at once and re-invert the
        # identity-over-capability tie-break above, letting a capability source
        # that fires every scan pin a wrong label permanently. A genuinely strong
        # re-claim needs no help here -- it simply wins the scoring outright and
        # never reaches this branch.
        incumbent_score = (
            max(0.0, float(incumbent_confidence))
            if incumbent_confidence is not None
            else _UNCLAIMED_INCUMBENT_SCORE
        )
        # Strict `>`: a challenger that merely equals the bar has not earned a
        # rewrite, which is the whole point of a margin.
        if not undisputed_score > incumbent_score + flip_margin:
            return ArbitratedClassification(
                device_type=incumbent,
                confidence=round(min(1.0, max(0.0, incumbent_score)), 3),
                evidence=(
                    (
                        [f"{c.source}: {c.evidence}" if c.evidence else c.source
                         for c in incumbent_entry[2]]
                        if incumbent_entry is not None else ["stored classification"]
                    )
                    + [
                        f"kept over {winner_type} ({winner_score:.2f}): "
                        f"below the {flip_margin:.2f} margin needed to change a "
                        f"stored label"
                    ]
                ),
                sources=(
                    incumbent_entry[3] if incumbent_entry is not None else frozenset()
                ),
            )

    return ArbitratedClassification(
        device_type=winner_type,
        confidence=round(min(1.0, max(0.0, winner_score)), 3),
        evidence=evidence,
        sources=winner_sources,
    )


# ── Claim constructors ─────────────────────────────────────────────────────────
# Each wraps an existing per-source scorer rather than inventing a new one.

def claim_from_heuristic(
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set] = None,
    os_family: str = "",
    mac: str = "",
    is_gateway: bool = False,
    best_rule: bool = False,
) -> ClassificationClaim:
    """Wrap classify_with_evidence() -- the existing OUI/hostname/ports/os
    scorer -- as a claim. Always returns a claim, even "Unknown Device" at
    confidence 0.0 (arbitrate() is what filters uninformative claims out; a
    caller may still want to know this source was tried and found nothing)."""
    from modules.device_classifier import classify_with_evidence

    result = classify_with_evidence(
        vendor=vendor, hostname=hostname, open_ports=open_ports,
        os_family=os_family, mac=mac, is_gateway=is_gateway,
        best_rule=best_rule,
    )
    return ClassificationClaim(
        device_type=result.device_type,
        confidence=result.confidence,
        source="heuristic",
        evidence=", ".join(result.evidence) if result.evidence else "",
    )


def claim_from_registry(mac: str) -> Optional[ClassificationClaim]:
    """A modules.mac_registry model-specific OUI hit. Product-specific, so
    treated as high confidence when present. None when the MAC has no entry
    -- never a claim of "Unknown Device", which would be a false claim rather
    than an honest absence of one."""
    if not mac:
        return None
    from modules.mac_registry import lookup as _mac_lookup

    device_type = _mac_lookup(mac).get("device_type", "")
    if not device_type:
        return None
    return ClassificationClaim(
        device_type=device_type, confidence=0.9, source="registry",
        evidence="MAC registry model-specific match",
    )


def claim_from_scan(
    mac: str,
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set] = None,
    os_family: str = "",
    is_gateway: bool = False,
) -> ClassificationClaim:
    """The claim a device's initial scan-time classification represents.

    Mirrors classify_registry_first()'s own precedence (registry hit, else
    the OUI/hostname/ports heuristic) so this claim matches whatever that
    function already decided for the device -- it exists to let the arbiter
    remember and corroborate/conflict against that decision, not to
    reclassify. Callers seed this once per device at the start of a scan
    session, before any passive/DHCP claim can arrive.
    """
    registry_claim = claim_from_registry(mac)
    if registry_claim is not None:
        return registry_claim
    return claim_from_heuristic(
        vendor=vendor, hostname=hostname, open_ports=open_ports,
        os_family=os_family, mac=mac, is_gateway=is_gateway,
    )


def claims_from_scan(
    mac: str,
    vendor: str = "",
    hostname: str = "",
    open_ports: Optional[set] = None,
    os_family: str = "",
    is_gateway: bool = False,
    best_rule: bool = False,
) -> List[ClassificationClaim]:
    """Every claim a device's scan-time inputs support, for the arbiter.

    The plural counterpart to claim_from_scan(). That function reproduces
    classify_registry_first()'s precedence -- registry hit *instead of* the
    heuristic -- which means a registry entry that contradicts the
    vendor/hostname/ports evidence wins without arbitrate() ever seeing the
    disagreement, and the user gets a confident-looking label with no sign the
    sources conflicted. This returns both, so corroboration raises the
    verdict's confidence and a genuine conflict lowers it and names the loser
    in the evidence trail.

    Registry claim first: arbitrate() sorts stably, so an exact score tie
    resolves to the first-inserted group -- keeping a tie on the same answer
    the singular short-circuit would have given.

    The heuristic claim is always included, even when it abstains
    ("Unknown Device" at 0.0); arbitrate() is what filters uninformative
    claims, and a caller may still want the record that the source ran.

    One carve-out: when the device IS the gateway *and* the registry knows the
    product, only the registry claim is emitted. classify_with_evidence()
    answers is_gateway at confidence 1.0, so it would outrank every registry
    entry -- but its answer is about the device's ROLE and the registry's is
    about the PRODUCT, which already implies that role. arbitrate() has no
    notion of specificity, so it scores the specialisation as a conflict and
    penalises it. Measured: the reference network's Deco gateway stores no
    hostname, so _MESH_HOSTNAME_RE can never fire for it and the shortcut
    always answers the generic "Router / Gateway" -- emitting it demoted a
    correct "Mesh Network Node" (registry, 0.90) to a generic label at 0.69,
    on the only device the gateway path touches there. A gateway the registry
    has never heard of still gets its heuristic claim as normal.

    `best_rule` is forwarded to the heuristic: with it, classify_with_evidence()
    returns its highest-scoring matching rule instead of the first one listed in
    _RULES. Off by default so the shipped path is unchanged.
    """
    claims: List[ClassificationClaim] = []
    registry_claim = claim_from_registry(mac)
    if registry_claim is not None:
        claims.append(registry_claim)
        if is_gateway:
            return claims
    claims.append(claim_from_heuristic(
        vendor=vendor, hostname=hostname, open_ports=open_ports,
        os_family=os_family, mac=mac, is_gateway=is_gateway,
        best_rule=best_rule,
    ))
    return claims


def claim_from_passive(obs: object) -> Optional[ClassificationClaim]:
    """Wrap classify_from_observation() -- the mDNS/SSDP passive listener --
    as a claim. None when the observation implies no usable label."""
    from modules.device_classifier import classify_from_observation

    result = classify_from_observation(obs)
    if not result.device_type or result.device_type == "Unknown Device":
        return None
    protocol = getattr(obs, "protocol", "") or "passive"
    return ClassificationClaim(
        device_type=result.device_type,
        confidence=result.confidence,
        source=f"passive-{protocol}",
        evidence=", ".join(result.evidence) if result.evidence else "",
    )


def claim_from_dhcp(fp: object) -> Optional[ClassificationClaim]:
    """Wrap a DhcpFingerprint (modules/dhcp_fingerprint.py) as a claim. None
    when there is no fingerprint, or it carries no device_hint."""
    device_hint = getattr(fp, "device_hint", "") if fp is not None else ""
    if not fp or not device_hint:
        return None
    conf_str = getattr(fp, "confidence", "low")
    return ClassificationClaim(
        device_type=device_hint,
        confidence=_DHCP_CONFIDENCE.get(conf_str, _DHCP_CONFIDENCE["low"]),
        source="dhcp",
        evidence=getattr(fp, "evidence", "") or "DHCP VCI fingerprint",
    )


# ── Per-scan claim bookkeeping ─────────────────────────────────────────────────

class ClaimTracker:
    """Per-MAC accumulator of classification claims across one scan session.

    Same shape as evidence.py's EvidenceGate: the pure decision (arbitrate())
    lives at module level; this class is just the bookkeeping a caller needs
    to feed it claims that arrive at different times over one scan (mesh/
    plugin hostname re-classification, passive mDNS/SSDP, DHCP VCI) without
    re-deriving a per-MAC dict inline at every call site.

    Claims persist for the tracker's lifetime -- call reset() when a new scan
    result replaces the device list, or a MAC's classification history from
    the previous scan would silently corroborate or conflict with this one's.

    `stable` selects arbitrate_stable() over arbitrate() -- order-independent
    tie-breaking plus a margin a challenger must clear to flip a stored label.
    The flag is read in the UI layer and passed in, never here: this module is
    pure (ARCH RULE 1) and must not reach for QSettings.
    """

    def __init__(self, stable: bool = False) -> None:
        self._claims: Dict[str, List[ClassificationClaim]] = {}
        self._stable = bool(stable)

    def reset(self) -> None:
        self._claims.clear()

    def add(
        self,
        mac: str,
        claim: Optional[ClassificationClaim],
        *,
        incumbent: str = "",
        incumbent_confidence: Optional[float] = None,
    ) -> Optional[ArbitratedClassification]:
        """Record `claim` for `mac` (a no-op when claim is None) and return
        the resulting verdict. Returns None only when mac is falsy, or no
        claim has ever been recorded for it.

        `incumbent` is the device_type currently stored/displayed for this
        device and `incumbent_confidence` the confidence it carries; together
        they are what arbitrate_stable()'s hysteresis defends. Both are ignored
        entirely when this tracker is not in stable mode."""
        if not mac:
            return None
        if claim is not None:
            self._claims.setdefault(mac, []).append(claim)
        claims = self._claims.get(mac, [])
        if not claims:
            return None
        if self._stable:
            return arbitrate_stable(
                claims,
                incumbent=incumbent,
                incumbent_confidence=incumbent_confidence,
            )
        return arbitrate(claims)

    def claim_count(self, mac: str) -> int:
        """Number of claims recorded for `mac` so far. Test/diagnostic hook."""
        return len(self._claims.get(mac, []))
