"""
tests/test_passive_observer.py — Unit tests for modules/passive_observer.py.
"""
from __future__ import annotations

import time
import pytest


# ── Import tests ───────────────────────────────────────────────────────────────

def test_import_passive_observer():
    from modules.passive_observer import (
        PassiveObservation, start_passive_observation,
        stop_passive_observation, get_observations, enrich_mac,
    )
    assert PassiveObservation is not None
    assert start_passive_observation is not None
    assert stop_passive_observation is not None
    assert get_observations is not None
    assert enrich_mac is not None


def test_import_passive_observer_worker():
    from workers.passive_observer_worker import PassiveObserverWorker
    assert PassiveObserverWorker is not None


# ── PassiveObservation dataclass ───────────────────────────────────────────────

def test_passive_observation_defaults():
    from modules.passive_observer import PassiveObservation
    obs = PassiveObservation(ip="192.168.1.10")
    assert obs.ip == "192.168.1.10"
    assert obs.mac == ""
    assert obs.protocol == ""
    assert obs.device_hint == ""
    assert obs.confidence == ""
    assert obs.raw_summary == ""
    assert obs.observed_at > 0


def test_passive_observation_full():
    from modules.passive_observer import PassiveObservation
    obs = PassiveObservation(
        ip="10.0.0.1",
        mac="AA:BB:CC:DD:EE:FF",
        protocol="ssdp",
        service_type="urn:schemas-upnp-org:device:internetgatewaydevice",
        device_hint="Router / Gateway",
        confidence="high",
        raw_summary="UPnP/SSDP InternetGatewayDevice",
        observed_at=1234567.0,
    )
    assert obs.device_hint == "Router / Gateway"
    assert obs.confidence == "high"
    assert obs.observed_at == 1234567.0


# ── SSDP parsing ───────────────────────────────────────────────────────────────

def test_ssdp_notify_router():
    """SSDP NOTIFY with IGD type → Router / Gateway (high confidence)."""
    from modules.passive_observer import _parse_ssdp

    packet = (
        b"NOTIFY * HTTP/1.1\r\n"
        b"HOST: 239.255.255.250:1900\r\n"
        b"NT: urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
        b"NTS: ssdp:alive\r\n"
        b"USN: uuid:abc123::urn:schemas-upnp-org:device:InternetGatewayDevice:1\r\n"
        b"\r\n"
    )
    results: list = []
    _parse_ssdp(packet, "192.168.1.1", results.append)
    assert len(results) == 1
    assert results[0].device_hint == "Router / Gateway"
    assert results[0].confidence == "high"
    assert results[0].ip == "192.168.1.1"
    assert results[0].protocol == "ssdp"


def test_ssdp_media_renderer_tv():
    """SSDP MediaRenderer → Smart TV."""
    from modules.passive_observer import _parse_ssdp

    packet = (
        b"HTTP/1.1 200 OK\r\n"
        b"ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
        b"USN: uuid:tv-1234::urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
        b"\r\n"
    )
    results: list = []
    _parse_ssdp(packet, "192.168.1.55", results.append)
    assert results and results[0].device_hint == "Smart TV"


def test_ssdp_printer():
    """SSDP printer service type → Print Server."""
    from modules.passive_observer import _parse_ssdp

    packet = (
        b"NOTIFY * HTTP/1.1\r\n"
        b"NT: urn:schemas-upnp-org:device:Printer:1\r\n"
        b"NTS: ssdp:alive\r\n"
        b"\r\n"
    )
    results: list = []
    _parse_ssdp(packet, "10.0.0.5", results.append)
    assert results and results[0].device_hint == "Print Server"
    assert results[0].confidence == "high"


def test_ssdp_unknown_type_no_result():
    """SSDP with an unknown NT produces no observation."""
    from modules.passive_observer import _parse_ssdp

    packet = (
        b"NOTIFY * HTTP/1.1\r\n"
        b"NT: urn:example-vendor:device:WeirdWidget:1\r\n"
        b"\r\n"
    )
    results: list = []
    _parse_ssdp(packet, "10.0.0.9", results.append)
    assert results == []


def test_ssdp_empty_packet_no_result():
    """Empty or malformed SSDP packet does not crash."""
    from modules.passive_observer import _parse_ssdp
    results: list = []
    _parse_ssdp(b"", "10.0.0.1", results.append)
    assert results == []


# ── _record deduplication and confidence upgrade ───────────────────────────────

def test_record_deduplication():
    """Same ip+service_type recorded twice → only one observation kept."""
    from modules.passive_observer import _record, _observations, _obs_lock

    with _obs_lock:
        _observations.clear()

    results: list = []
    _record("1.2.3.4", "ssdp", "_test._svc", "Smart TV", "high",
            "UPnP test", results.append)
    _record("1.2.3.4", "ssdp", "_test._svc", "Smart TV", "high",
            "UPnP test", results.append)

    with _obs_lock:
        count = sum(1 for k in _observations if k.startswith("1.2.3.4|"))
    assert count == 1
    assert len(results) == 1  # callback fired only once for the new entry


def test_record_confidence_upgrade_fires_callback():
    """Low→high confidence upgrade on same key fires the callback again."""
    from modules.passive_observer import _record, _observations, _obs_lock

    with _obs_lock:
        _observations.clear()

    results: list = []
    _record("5.5.5.5", "ssdp", "_upgrade._tcp", "IoT Device", "low",
            "low-conf", results.append)
    _record("5.5.5.5", "ssdp", "_upgrade._tcp", "IoT Device", "high",
            "high-conf", results.append)

    assert len(results) == 2  # both fired: new entry + upgrade
    with _obs_lock:
        obs = _observations.get("5.5.5.5|_upgrade._tcp")
    assert obs is not None and obs.confidence == "high"


# ── get_observations ───────────────────────────────────────────────────────────

def test_get_observations_returns_list():
    from modules.passive_observer import get_observations, _observations, _obs_lock
    with _obs_lock:
        _observations.clear()
    result = get_observations()
    assert isinstance(result, list)


# ── classify_from_observation ──────────────────────────────────────────────────

def test_classify_from_observation_high():
    from modules.passive_observer import PassiveObservation
    from modules.device_classifier import classify_from_observation

    obs = PassiveObservation(
        ip="192.168.1.20",
        protocol="ssdp",
        service_type="urn:schemas-upnp-org:device:internetgatewaydevice",
        device_hint="Router / Gateway",
        confidence="high",
    )
    result = classify_from_observation(obs)
    assert result.device_type == "Router / Gateway"
    assert result.confidence >= 0.80
    assert any("ssdp" in e for e in result.evidence)


def test_classify_from_observation_low():
    from modules.passive_observer import PassiveObservation
    from modules.device_classifier import classify_from_observation

    obs = PassiveObservation(
        ip="192.168.1.21",
        protocol="mdns",
        service_type="_smb._tcp",
        device_hint="File / NAS Server",
        confidence="low",
    )
    result = classify_from_observation(obs)
    assert result.device_type == "File / NAS Server"
    assert result.confidence < 0.80


def test_classify_from_observation_no_hint():
    from modules.passive_observer import PassiveObservation
    from modules.device_classifier import classify_from_observation

    obs = PassiveObservation(ip="192.168.1.99", device_hint="", confidence="low")
    result = classify_from_observation(obs)
    assert result.device_type == "Unknown Device"
    assert result.confidence == 0.0


# ── mDNS classification table ──────────────────────────────────────────────────

@pytest.mark.parametrize("svc_type,expected_hint,expected_conf", [
    ("_printer._tcp",    "Print Server",          "high"),
    ("_googlecast._tcp", "Streaming Stick",       "high"),
    ("_airplay._tcp",    "Smart TV",              "high"),
    ("_homekit._tcp",    "IoT Device",            "high"),
    ("_ssh._tcp",        "Linux / Unix Host",     "low"),
    ("_smb._tcp",        "File / NAS Server",     "low"),
    ("_rdp._tcp",        "Windows PC",            "high"),
])
def test_mdns_hint_table(svc_type, expected_hint, expected_conf):
    from modules.passive_observer import _MDNS_HINTS
    assert svc_type in _MDNS_HINTS, f"{svc_type} missing from _MDNS_HINTS"
    hint, conf = _MDNS_HINTS[svc_type]
    assert hint == expected_hint
    assert conf == expected_conf


# ── SSDP classification table ──────────────────────────────────────────────────

@pytest.mark.parametrize("nt_fragment,expected_hint,expected_conf", [
    ("internetgatewaydevice", "Router / Gateway",       "high"),
    ("mediarenderer",         "Smart TV",               "high"),
    ("printer",               "Print Server",           "high"),
    ("binarylight",           "IoT Device",             "high"),
    ("digitalsecuritycamera", "IP Camera",              "high"),
    ("mediaserver",           "File / NAS Server",      "low"),
])
def test_ssdp_hint_table(nt_fragment, expected_hint, expected_conf):
    from modules.passive_observer import _SSDP_HINTS
    matched = [(k, v) for k, v in _SSDP_HINTS.items() if nt_fragment in k]
    assert matched, f"{nt_fragment} not found in _SSDP_HINTS keys"
    _, (hint, conf) = matched[0]
    assert hint == expected_hint
    assert conf == expected_conf


# ── Worker lifecycle ───────────────────────────────────────────────────────────

def test_passive_observer_worker_starts_and_stops():
    """Worker must start, run briefly, and stop cleanly (RULE-T2)."""
    _qtw = pytest.importorskip("PyQt6.QtWidgets")
    QApplication = _qtw.QApplication

    from workers.passive_observer_worker import PassiveObserverWorker

    app = QApplication.instance()
    w = PassiveObserverWorker()
    w.start()
    time.sleep(0.2)
    w.stop()
    w.wait(3000)
    assert not w.isRunning()
    try:
        w.deleteLater()
    except RuntimeError:
        pass  # already deleted — non-fatal
    if app:
        for _ in range(3):
            app.processEvents()
