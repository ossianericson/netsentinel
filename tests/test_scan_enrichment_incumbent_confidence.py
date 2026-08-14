"""_dev_conf() must report the STORED label's confidence, not the scan object's.

Found by live verification, not by the unit tests: with the stable-arbitration flag
on, the reference network's Deco gateway was demoted from "Mesh Network Node" (MAC
registry, 0.90) to the generic "Router / Gateway" (0.85) — the exact regression
Identity A4's gateway carve-out exists to prevent.

Mechanism: `DeviceInfo.confidence` is a scan-time field that defaults to 0.0 and is
only filled once this scan's enrichment arbitrates that device. Feeding it to
arbitrate_stable() as `incumbent_confidence` therefore claims a stored, registry-grade
0.90 label is evidenced at 0.0 — so hysteresis defended it at 0.10 instead of 1.00 and
a passive SSDP InternetGatewayDevice announcement at 0.85 walked straight over it.

The incumbent is the row in known_device. Its strength is known_device.confidence.
"""
import pytest

from ui.scan_enrichment import _dev_conf


class _Store:
    """Minimal MetricStore stand-in exposing only get_known_devices()."""

    def __init__(self, rows):
        self._rows = rows
        self.calls = 0

    def get_known_devices(self):
        self.calls += 1
        return self._rows


class _KD:
    def __init__(self, confidence):
        self.confidence = confidence


GW = "3c:64:cf:e0:27:02"


def test_falls_back_to_the_stored_confidence_when_the_scan_object_has_none():
    """The live gateway case: DeviceInfo.confidence is the 0.0 default."""
    store = _Store({GW: _KD(0.90)})
    dev = {"mac": GW, "device_type": "Mesh Network Node", "confidence": 0.0}
    assert _dev_conf(dev, store, GW) == 0.90


def test_a_real_scan_confidence_is_preferred_over_the_stored_one():
    """A non-zero value means this scan actually arbitrated the device, so it is
    fresher than whatever the row was last written with."""
    store = _Store({GW: _KD(0.90)})
    dev = {"mac": GW, "device_type": "Router / Gateway", "confidence": 0.42}
    assert _dev_conf(dev, store, GW) == 0.42


def test_returns_none_when_neither_source_knows():
    store = _Store({})
    dev = {"mac": GW, "device_type": "Mesh Network Node", "confidence": 0.0}
    assert _dev_conf(dev, store, GW) is None


def test_missing_store_degrades_to_none_rather_than_zero():
    """None means "unknown" to arbitrate_stable(); 0.0 would mean "evidenced at
    zero", which is a much weaker defence and is exactly the bug."""
    dev = {"mac": GW, "device_type": "Mesh Network Node", "confidence": 0.0}
    assert _dev_conf(dev, None, GW) is None


def test_store_failure_is_not_fatal():
    class _Broken:
        def get_known_devices(self):
            raise RuntimeError("db gone")

    dev = {"mac": GW, "device_type": "Mesh Network Node", "confidence": 0.0}
    assert _dev_conf(dev, _Broken(), GW) is None


def test_dataclass_style_device_objects_work_too():
    class _Dev:
        mac = GW
        device_type = "Mesh Network Node"
        confidence = 0.0

    store = _Store({GW: _KD(0.90)})
    assert _dev_conf(_Dev(), store, GW) == 0.90


@pytest.mark.parametrize("stored", [0.0, None, "not-a-number"])
def test_unusable_stored_values_degrade_to_none(stored):
    store = _Store({GW: _KD(stored)})
    dev = {"mac": GW, "device_type": "Mesh Network Node", "confidence": 0.0}
    assert _dev_conf(dev, store, GW) is None


def test_the_gateway_regression_end_to_end():
    """The whole point, expressed as the device that exposed it: a passive
    InternetGatewayDevice announcement must not displace the registry's more
    specific product label."""
    from modules.device_classification import ClassificationClaim, arbitrate_stable

    store = _Store({GW: _KD(0.90)})
    dev = {"mac": GW, "device_type": "Mesh Network Node", "confidence": 0.0}
    passive = ClassificationClaim(
        device_type="Router / Gateway", confidence=0.85, source="passive-ssdp",
        evidence="urn:schemas-upnp-org:device:internetgatewaydevice",
    )
    verdict = arbitrate_stable(
        [passive],
        incumbent="Mesh Network Node",
        incumbent_confidence=_dev_conf(dev, store, GW),
    )
    assert verdict.device_type == "Mesh Network Node"
