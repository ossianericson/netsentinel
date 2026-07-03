"""Tests for modules/cert_auto_enroll.py (V6 Sprint 3.3 — auto-TLS enrolment)."""
from __future__ import annotations

from modules.cert_monitor import CertTarget
from modules.config_baseline import DeviceEntry


def test_import():
    from modules.cert_auto_enroll import auto_enroll_from_sweep
    assert auto_enroll_from_sweep is not None


def test_host_with_443_open_gets_auto_enrolled():
    from modules.cert_auto_enroll import auto_enroll_from_sweep

    entries = [DeviceEntry(ip="192.168.1.50", open_ports=[80, 443])]
    result = auto_enroll_from_sweep(entries, existing=[])

    assert len(result) == 1
    assert result[0].host == "192.168.1.50"
    assert result[0].ports == [443]
    assert result[0].label == "auto"


def test_host_with_8443_open_gets_auto_enrolled():
    from modules.cert_auto_enroll import auto_enroll_from_sweep

    entries = [DeviceEntry(ip="192.168.1.51", open_ports=[8443])]
    result = auto_enroll_from_sweep(entries, existing=[])

    assert result[0].ports == [8443]


def test_host_without_tls_port_is_skipped():
    from modules.cert_auto_enroll import auto_enroll_from_sweep

    entries = [DeviceEntry(ip="192.168.1.52", open_ports=[22, 80])]
    result = auto_enroll_from_sweep(entries, existing=[])

    assert result == []


def test_existing_manual_targets_are_preserved_and_not_duplicated():
    from modules.cert_auto_enroll import auto_enroll_from_sweep

    existing = [CertTarget(host="192.168.1.50", ports=[443], label="my router")]
    entries = [DeviceEntry(ip="192.168.1.50", open_ports=[443]), DeviceEntry(ip="192.168.1.60", open_ports=[443])]
    result = auto_enroll_from_sweep(entries, existing=existing)

    hosts = [t.host for t in result]
    assert hosts.count("192.168.1.50") == 1  # not duplicated
    assert "192.168.1.60" in hosts
    assert len(result) == 2


def test_excluded_host_is_not_re_enrolled():
    """A host the user manually removed from the cert targets list must be
    tracked in `excluded` (persisted separately from `existing`) so a later
    sweep does not silently re-add it."""
    from modules.cert_auto_enroll import auto_enroll_from_sweep

    entries = [DeviceEntry(ip="192.168.1.70", open_ports=[443])]
    result = auto_enroll_from_sweep(entries, existing=[], excluded={"192.168.1.70"})
    assert result == []
