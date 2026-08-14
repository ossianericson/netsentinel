"""
device_reenrichment.py — heal existing known_device rows after an identity fix.

Every classifier, vendor-lookup and MAC-registry fix only affects what is
written NEXT. The rows a user already has keep whatever an earlier build
decided, so the install that most needed the fix is the one that does not get
it — a device mislabelled a year ago stays mislabelled until something happens
to rewrite that particular row.

Measured on the reference network at the time this was written: 8 of 34 rows
carried a vendor that disagreed with what `lookup_vendor()` answers today (one
stored "Sonos" for a device whose IEEE vendor is "Frontier Silicon Ltd", another
stored "Microsoft" for a Raspberry Pi), and 3 rows had a NULL device_type.

Two deliberate limits:

* **It upgrades, it never blanks.** A row can carry a real label derived from a
  source this pass cannot see — a printer known only from an `_ipp._tcp`
  announcement, with no vendor and no hostname to re-derive it from. Replacing
  that with "Unknown Device" on upgrade would read as data loss, and the next
  scan re-derives it properly anyway.
* **It never touches a user override.** A pinned classification is the user's
  answer, not a guess to be improved on.

Pure module: no PyQt import, no raw SQL — every write goes through a
MetricStore method (ARCH RULE 1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from modules.device_classification import arbitrate, arbitrate_stable, claims_from_scan
from modules.utils import lookup_vendor

# Bumped when a change makes a re-run worthwhile. The marker stores the value
# that last ran, so an upgrade to a higher generation re-runs exactly once.
_REENRICH_GENERATION = 1
_META_KEY = "identity_reenrich_generation"

_UNINFORMATIVE = {"", "unknown device"}


@dataclass
class ReenrichmentResult:
    """What the pass did, for logging and for the tests to assert on."""
    ran: bool = False
    rows_examined: int = 0
    vendors_corrected: int = 0
    types_corrected: int = 0
    changed: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.changed is None:
            self.changed = []


def _is_informative(device_type: str) -> bool:
    return (device_type or "").strip().lower() not in _UNINFORMATIVE


def reenrich_known_devices(
    store: Any, *, force: bool = False, stable: bool = False
) -> ReenrichmentResult:
    """Re-run vendor lookup and classification over every known_device row.

    Returns a ReenrichmentResult; a no-op run (already done at this generation)
    returns ``ran=False`` and examines nothing.

    `stable` selects arbitrate_stable() + best_rule scoring. The caller reads
    the QSettings flag and passes it; this module stays pure (ARCH RULE 1).
    Hysteresis matters especially here: this pass runs over the whole stored
    inventory, so without an incumbent to defend it would rewrite every row on
    the strength of a tie.
    """
    result = ReenrichmentResult()

    if not force:
        try:
            seen = store.get_meta(_META_KEY)
        except Exception:
            seen = None  # pre-v23 database or unavailable — treat as never run
        if seen is not None and str(seen) == str(_REENRICH_GENERATION):
            return result

    result.ran = True

    try:
        devices = store.get_known_devices()
    except Exception:
        return result

    for mac, kd in devices.items():
        if not mac:
            continue
        result.rows_examined += 1

        # A pinned classification is the user's answer. Skip the row entirely:
        # correcting its vendor would change what the Devices page shows next
        # to a label the user deliberately fixed in place.
        try:
            if store.get_classification_override(mac):
                continue
        except Exception:
            pass  # no override support — treat as not overridden

        stored_vendor = (getattr(kd, "vendor", "") or "").strip()
        stored_type = (getattr(kd, "device_type", "") or "").strip()
        hostname = (getattr(kd, "hostname", "") or "").strip()

        # An empty IEEE answer means "this OUI is not in the table" (a
        # randomized MAC, most often), never "the stored vendor is wrong".
        ieee_vendor = (lookup_vendor(mac) or "").strip()
        vendor_fix = bool(ieee_vendor) and ieee_vendor != stored_vendor
        effective_vendor = ieee_vendor or stored_vendor

        _claims = claims_from_scan(
            mac=mac,
            vendor=effective_vendor,
            hostname=hostname,
            open_ports=set(),      # known_device stores neither, so this is the
            os_family="",          # vendor+hostname axis only
            is_gateway=False,
            best_rule=stable,
        )
        verdict = (
            arbitrate_stable(
                _claims, incumbent=stored_type,
                incumbent_confidence=getattr(kd, "confidence", None),
            )
            if stable else arbitrate(_claims)
        )

        # Upgrade only. An uninformative verdict never displaces a real label.
        type_fix = (
            _is_informative(verdict.device_type)
            and verdict.device_type != stored_type
        )

        if not vendor_fix and not type_fix:
            continue

        kwargs: dict = {}
        if vendor_fix:
            kwargs["vendor"] = ieee_vendor
            result.vendors_corrected += 1
        if type_fix:
            kwargs["device_type"] = verdict.device_type
            kwargs["confidence"] = verdict.confidence
            result.types_corrected += 1
            result.changed.append(
                f"{mac}: {stored_type or 'None'} -> {verdict.device_type}"
            )

        # Preserve last_seen. upsert_known_device() stamps it to now by
        # default, which would report every corrected device as just-seen --
        # including ones offline for days -- and that feeds presence episodes
        # and the LEFT/RECOVERED edge triggers. This is a data repair, not an
        # observation, so it must leave the timeline exactly as it found it.
        try:
            _seen = int(getattr(kd, "last_seen", 0) or 0)
        except (TypeError, ValueError):
            _seen = 0
        if _seen:
            kwargs["ts"] = _seen

        try:
            store.upsert_known_device(mac, **kwargs)
        except Exception:
            continue  # one bad row must not abort the whole pass

    try:
        store.set_meta(_META_KEY, str(_REENRICH_GENERATION))
    except Exception:
        pass  # marker unavailable — the pass is idempotent, so a re-run is safe

    return result
