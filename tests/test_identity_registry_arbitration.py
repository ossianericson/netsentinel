"""Identity A4 — the MAC registry is arbitrated against the heuristic (RULE-T7).

`claim_from_scan()` returned the MAC-registry claim INSTEAD of the heuristic
claim whenever the registry had an entry, so `arbitrate()` — the one mechanism
built to catch "sources disagree" — was structurally bypassed for exactly the
source most likely to be wrong. The registry won in silence and the user saw a
confident label with no sign anything else had been claimed.

`claims_from_scan()` (plural) emits both, and every seeding site now uses it.

**Shipped behind `experimental/identity_arbitrate_registry`, then promoted and
the flag REMOVED** — the native_chrome precedent, not defaulted True: a
permanently-on flag is a branch nobody tests. The promotion measurement, across
both reference databases (71 known_device rows), driving the real shipped
functions with the live gateway MAC resolved:

    device_type changed        0    (both DBs)
    confidence changed         3    (both DBs, all UPWARD 0.90 -> 0.925)

Zero type flips because the heuristic caps at vendor 0.40 + hostname 0.30
without open_ports/os_family, so a registry hit at 0.90 wins every conflict on
the type axis. A4 changes what the verdict REPORTS, not who wins.

`claim_from_scan()` (singular) is deliberately still exported and unchanged:
`device_tracker._scan_confidence()` depends on it reproducing
`classify_registry_first()` exactly and returns None on any mismatch, so an
arbitrated verdict there would silently zero confidence coverage. An AST guard
in tests/test_device_tracker.py fails if device_tracker.py ever imports or calls
the plural form.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytest.importorskip("PyQt6.QtWidgets")

from ui.scan_wiring import ScanResultMixin  # noqa: E402
from modules.device_classification import ClaimTracker  # noqa: E402

# The one genuinely-conflicting device on the reference network: a Raspberry Pi
# named for the job it does, so the registry (Single Board Computer) and the
# hostname heuristic (File / NAS Server) disagree.
#
# The row's real hostname is "PINAS". That spelling no longer reaches the NAS
# rule -- the hostname alternatives were anchored so "nas" stops matching inside
# "Jonas" and "Nasrin", and "PINAS" is structurally identical to those, so no
# pattern can accept one and reject the others. The conflict under test is
# unchanged; only the hostname that triggers it.
_PINAS = {
    "mac": "d8:3a:dd:de:11:a7", "ip": "192.168.68.70",
    "hostname": "nas-01", "vendor": "Raspberry Pi", "open_ports": [],
}
_REGISTRY_SAYS = "Single Board Computer"
_HOSTNAME_SAYS = "File / NAS Server"


@pytest.fixture
def registry_hit(monkeypatch):
    """Pin the curated OUI table's answer so the test does not depend on the
    live table (whose entries are dropped at runtime when they contradict
    scapy's bundled IEEE data -- modules/mac_registry.py::_validate_against_ieee)."""
    monkeypatch.setattr(
        "modules.mac_registry.lookup",
        lambda mac: {"device_type": _REGISTRY_SAYS},
    )


def _seeder():
    """A minimal ScanResultMixin wired to a real ClaimTracker."""
    class _Stub(ScanResultMixin):
        pass

    stub = _Stub()
    stub._classification_claims = ClaimTracker()
    return stub


class TestBothClaimsReachTheArbiter:
    def test_seeds_both_claims(self, registry_hit):
        stub = _seeder()
        stub._m1_seed_classification_claims([dict(_PINAS)])
        assert stub._classification_claims.claim_count(_PINAS["mac"]) == 2

    def test_registry_still_wins_the_type(self, registry_hit):
        """A product-specific OUI hit outranks a generic hostname match. A4
        changes what the verdict REPORTS, not who wins -- 0 of 71 reference
        devices change device_type."""
        stub = _seeder()
        stub._m1_seed_classification_claims([dict(_PINAS)])
        verdict = stub._classification_claims.add(_PINAS["mac"], None)
        assert verdict.device_type == _REGISTRY_SAYS

    def test_confidence_drops_and_the_loser_is_named(self, registry_hit):
        """The whole point: the disagreement becomes something the panel says.

        Before, the percentage described the claim that won while the evidence
        line described the claim that lost, with nothing saying they differed.
        """
        stub = _seeder()
        stub._m1_seed_classification_claims([dict(_PINAS)])
        verdict = stub._classification_claims.add(_PINAS["mac"], None)
        assert verdict.confidence < 0.9
        assert any("conflicts with" in e for e in verdict.evidence)
        assert any(_HOSTNAME_SAYS in e for e in verdict.evidence)

    def test_agreement_raises_confidence_instead(self, monkeypatch):
        """The other measured shape, and the only one that moves on a healthy
        network: registry and heuristic independently agree (78:c8:81:d7:9f:fe,
        a PS5), which should read as MORE certain than the registry alone."""
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Games Console"},
        )
        stub = _seeder()
        stub._m1_seed_classification_claims([{
            "mac": "78:c8:81:d7:9f:fe", "ip": "192.168.68.71",
            "hostname": "PS5-D79FFE", "vendor": "Sony Interactive Entertainment",
        }])
        verdict = stub._classification_claims.add("78:c8:81:d7:9f:fe", None)
        assert verdict.device_type == "Games Console"
        assert verdict.confidence > 0.9

    def test_the_gateway_keeps_its_registry_product_label(self, monkeypatch):
        """Decision D1, revised after measurement. The gateway shortcut answers
        the generic 'Router / Gateway' at confidence 1.0 and would outrank any
        registry entry -- but that is a ROLE claim against a PRODUCT claim that
        already implies the role, not a real disagreement.

        This network's Deco gateway stores no hostname, so the mesh regex can
        never fire for it; emitting the gateway claim would demote a correct
        'Mesh Network Node' to a generic label at 0.69.
        """
        monkeypatch.setattr(
            "modules.mac_registry.lookup",
            lambda mac: {"device_type": "Mesh Network Node"},
        )
        stub = _seeder()
        stub._m1_seed_classification_claims([{
            "mac": "3c:64:cf:e0:27:02", "ip": "192.168.68.1",
            "hostname": "", "vendor": "TP-Link", "is_gateway": True,
        }])
        verdict = stub._classification_claims.add("3c:64:cf:e0:27:02", None)
        assert verdict.device_type == "Mesh Network Node"
        assert verdict.confidence == pytest.approx(0.9)


class TestTheFlagIsGone:
    """The promotion is only real if no code path still consults the key."""

    def test_no_source_file_reads_the_experimental_key(self):
        root = Path(__file__).resolve().parent.parent
        offenders = []
        for sub in ("ui", "modules", "workers"):
            for path in (root / sub).rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="strict")
                if "identity_arbitrate_registry_enabled" in text:
                    offenders.append(str(path.relative_to(root)))
        assert not offenders, (
            "the A4 flag helper was removed, but these still call it: "
            + ", ".join(offenders)
        )
