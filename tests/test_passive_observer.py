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


def test_ssdp_media_renderer_is_a_capability_not_a_product():
    """SSDP MediaRenderer → a recorded capability, and no product claim.

    Anything that can play a stream advertises MediaRenderer -- a TV, a powered
    speaker, an AV receiver, a phone. The observation is still recorded (the
    capability is real), it just no longer names a product.
    """
    from modules.passive_observer import _parse_ssdp

    packet = (
        b"HTTP/1.1 200 OK\r\n"
        b"ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
        b"USN: uuid:tv-1234::urn:schemas-upnp-org:device:MediaRenderer:1\r\n"
        b"\r\n"
    )
    results: list = []
    _parse_ssdp(packet, "192.168.1.55", results.append)
    assert results, "the observation must still be recorded"
    assert results[0].device_hint == ""
    assert results[0].capability == "Media renderer (DLNA)"


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


# ── ARP enrichment at record time ──────────────────────────────────────────────
#
# The observation's `mac` is what ui/scan_enrichment.py::_on_passive_observation()
# attributes the observation by. Every test that hands a MAC straight to
# PassiveObservation(...) asserts the consumer's behaviour *given* a resolved
# MAC, and is structurally incapable of noticing that nothing in production ever
# resolves one -- which is exactly what happened: enrich_mac() shipped with zero
# callers outside this file, so obs.mac was always "" and the MAC-matching path
# was unreachable. These tests drive the real _record() entry point instead.

def _reset_arp_cache(monkeypatch) -> None:
    """Invalidate _record()'s TTL-cached ARP snapshot.

    The cache is module-level, so a snapshot taken by an earlier test in the
    same session is still warm and would swallow this test's lookup entirely.
    monkeypatch (rather than a bare assignment) so the timestamp is restored
    afterwards and the reset cannot leak into the next test.
    """
    monkeypatch.setattr("modules.passive_observer._arp_cache_at", 0.0)


def _patch_arp(monkeypatch, table: dict) -> None:
    """Point the ARP-cache helper at a fixed {ip: mac} map."""
    monkeypatch.setattr("modules.utils_net.get_arp_snapshot", lambda: dict(table))
    _reset_arp_cache(monkeypatch)


def test_recorded_observation_carries_the_arp_resolved_mac(monkeypatch):
    """A recorded observation must reach the callback already carrying the MAC
    the ARP cache maps its source IP to -- not an empty string the consumer
    then has to fall back to IP matching for."""
    from modules.passive_observer import _record, _observations, _obs_lock

    _patch_arp(monkeypatch, {"9.9.9.9": "aa:bb:cc:dd:ee:99"})
    with _obs_lock:
        _observations.clear()

    results: list = []
    _record("9.9.9.9", "mdns", "_arp-test._tcp", "IP Camera", "high",
            "mDNS _arp-test._tcp", results.append)

    assert len(results) == 1
    assert results[0].mac.lower() == "aa:bb:cc:dd:ee:99", (
        "the observation reached its consumer with mac=%r -- the consumer then "
        "attributes it by IP, and on a DHCP network the IP's owner has moved"
        % results[0].mac
    )


def test_replayed_observation_carries_the_arp_resolved_mac(monkeypatch):
    """The buffered copy get_observations() replays after a scan must carry the
    MAC too -- _apply_passive_observations() re-runs the whole buffer, so a MAC
    resolved only for the live callback would be lost on every replay."""
    from modules.passive_observer import (
        _record, _observations, _obs_lock, get_observations,
    )

    _patch_arp(monkeypatch, {"9.9.9.8": "aa:bb:cc:dd:ee:98"})
    with _obs_lock:
        _observations.clear()

    _record("9.9.9.8", "mdns", "_replay-test._tcp", "IP Camera", "high",
            "mDNS _replay-test._tcp", lambda _obs: None)

    buffered = [o for o in get_observations() if o.ip == "9.9.9.8"]
    assert len(buffered) == 1
    assert buffered[0].mac.lower() == "aa:bb:cc:dd:ee:98"


def test_record_leaves_mac_empty_when_arp_cannot_resolve_the_ip(monkeypatch):
    """An unresolvable IP must leave mac empty rather than inventing one -- the
    consumer's own guard is what decides whether an unattributable observation
    may still be matched by IP."""
    from modules.passive_observer import _record, _observations, _obs_lock

    _patch_arp(monkeypatch, {"1.1.1.1": "aa:bb:cc:dd:ee:11"})
    with _obs_lock:
        _observations.clear()

    results: list = []
    _record("9.9.9.7", "mdns", "_missing._tcp", "IP Camera", "high",
            "mDNS _missing._tcp", results.append)

    assert len(results) == 1
    assert results[0].mac == ""


def test_record_does_not_hold_the_observation_lock_across_the_arp_lookup(monkeypatch):
    """The ARP read shells out to `arp -a` (~40 ms measured). Doing that while
    holding _obs_lock would stall both listener threads behind every record."""
    from modules.passive_observer import _record, _observations, _obs_lock

    held: list = []

    def _probe() -> dict:
        held.append(_obs_lock.locked())
        return {"9.9.9.6": "aa:bb:cc:dd:ee:96"}

    monkeypatch.setattr("modules.utils_net.get_arp_snapshot", _probe)
    _reset_arp_cache(monkeypatch)
    with _obs_lock:
        _observations.clear()

    _record("9.9.9.6", "mdns", "_lock-test._tcp", "IP Camera", "high",
            "mDNS _lock-test._tcp", lambda _obs: None)

    assert held == [False], "ARP lookup ran while _obs_lock was held"


def test_arp_snapshot_is_reused_across_a_burst_of_records(monkeypatch):
    """A burst of distinct service types from one device must not spawn one
    `arp -a` subprocess each on the listener thread."""
    from modules.passive_observer import _record, _observations, _obs_lock

    calls: list = []

    def _counting() -> dict:
        calls.append(1)
        return {"9.9.9.5": "aa:bb:cc:dd:ee:95"}

    monkeypatch.setattr("modules.utils_net.get_arp_snapshot", _counting)
    _reset_arp_cache(monkeypatch)
    with _obs_lock:
        _observations.clear()

    for i in range(8):
        _record("9.9.9.5", "mdns", f"_burst{i}._tcp", "IP Camera", "high",
                f"mDNS _burst{i}._tcp", lambda _obs: None)

    assert len(calls) == 1, f"{len(calls)} ARP subprocess reads for 8 records"


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
    # Product-specific services only -- the announcement itself identifies a
    # product class. The media-capability services deliberately have no entry
    # here; see the capability tests below for what they must do instead.
    ("_printer._tcp",    "Print Server",          "high"),
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
    # Product-specific services only -- see test_mdns_hint_table's note.
    ("internetgatewaydevice", "Router / Gateway",       "high"),
    ("printer",               "Print Server",           "high"),
    ("binarylight",           "Smart Plug",             "high"),
    ("digitalsecuritycamera", "IP Camera",              "high"),
    # A DLNA MediaServer is the mirror of MediaRenderer: it proves the device can
    # SERVE media, not that it is a file server. Recorded as a capability instead.
    ("mediaserver",           "",                       "low"),
])
def test_ssdp_hint_table(nt_fragment, expected_hint, expected_conf):
    from modules.passive_observer import _SSDP_HINTS
    matched = [(k, v) for k, v in _SSDP_HINTS.items() if nt_fragment in k]
    assert matched, f"{nt_fragment} not found in _SSDP_HINTS keys"
    _, (hint, conf) = matched[0]
    assert hint == expected_hint
    assert conf == expected_conf


def test_a_capability_service_never_also_claims_a_product():
    """The two are mutually exclusive, by definition.

    A service that only proves what a device can DO cannot simultaneously prove
    what it IS. This is the guard that stops a future edit re-adding a product
    label to a capability entry -- the exact regression this rule exists for.
    """
    from modules.passive_observer import (
        _CAPABILITY_LABELS, _MDNS_HINTS, _SSDP_HINTS,
    )

    offenders = []
    for service_type in _CAPABILITY_LABELS:
        table = _SSDP_HINTS if service_type.startswith("urn:") else _MDNS_HINTS
        hint, conf = table.get(service_type, ("", "low"))
        if hint:
            offenders.append(f"{service_type} -> {hint!r} ({conf})")

    assert not offenders, (
        "these services carry a capability label AND claim a product type: "
        + "; ".join(offenders)
    )


# ── Capability announcements must not assert product identity ──────────────────
#
# A service announcement proves a service is RUNNING. It never proves what the
# device IS. Chromecast-built-in ships in TVs, powered speakers and smart
# displays; AirPlay video in Apple TVs, TVs and Macs; RAOP (AirPlay *audio*) in
# HomePods, AV receivers and speakers; Spotify Connect in all of those plus the
# desktop app; UPnP MediaRenderer in anything that can play a stream.
#
# Mapping any of them to one product type at "high" (0.85) outranks the
# vendor+hostname heuristic's 0.70 ceiling, so the announcement decides the
# label outright -- and a device advertising two of them alternates between two
# answers for as long as it stays on the network.
#
# Measured on the reference network before this fix: 16 of 34 devices carried
# "Smart TV" or "Streaming Stick", every recent class_changed row had
# source='passive', and one Philips audio device (hostname 'Barnens-rum')
# had accumulated 688 x Smart TV + 560 x Smart Speaker / Audio + 11 x Streaming
# Stick -- 1,259 rewrites of one device's identity, not one of them from
# evidence about what the device is.

_MEDIA_CAPABILITY_SERVICES = (
    "_googlecast._tcp",
    "_airplay._tcp",
    "_raop._tcp",
    "_spotify-connect._tcp",
    "urn:schemas-upnp-org:device:mediarenderer",
)


def _observe(service_type: str, monkeypatch, ip: str = "10.9.9.9"):
    """Drive the real _record() for *service_type* and return the observation.

    Resolves hint AND capability from the production tables, exactly as
    _parse_ssdp()/_parse_mdns() do, so the test cannot pass by hand-supplying a
    value production never produces (RULE-DBG5).

    The SSDP branch here uses an exact key, while _parse_ssdp() matches the
    table key as a *substring* of the version-suffixed wire value -- so that
    path additionally has a real-packet test,
    test_ssdp_media_renderer_is_a_capability_not_a_product, which is what
    caught the capability lookup missing "...:mediarenderer:1". The mDNS branch
    needs no equivalent: _parse_mdns() looks up both tables with the same exact
    key, so the two cannot diverge.
    """
    from modules.passive_observer import (
        _CAPABILITY_LABELS, _MDNS_HINTS, _SSDP_HINTS,
        _record, _observations, _obs_lock,
    )
    _patch_arp(monkeypatch, {})
    table = _SSDP_HINTS if service_type.startswith("urn:") else _MDNS_HINTS
    assert service_type in table, f"{service_type} missing from the hint tables"
    hint, conf = table[service_type]
    capability = _CAPABILITY_LABELS.get(service_type, "")
    protocol = "ssdp" if service_type.startswith("urn:") else "mdns"
    out: list = []
    with _obs_lock:
        _observations.clear()
    _record(ip, protocol, service_type, hint, conf, "", out.append,
            capability=capability)
    assert out, f"_record() dropped the {service_type} observation"
    return out[0]


@pytest.mark.parametrize("service_type", _MEDIA_CAPABILITY_SERVICES)
def test_media_capability_service_makes_no_product_claim(service_type, monkeypatch):
    """A media-capability announcement must not name a product type at all.

    Asserts the invariant (no product claim), not one particular remedy -- it
    holds whether the hint is blanked, the confidence demoted, or the whole
    entry removed from the table.
    """
    from modules.device_classification import claim_from_passive

    obs = _observe(service_type, monkeypatch)
    claim = claim_from_passive(obs)
    assert claim is None, (
        f"{service_type} claims device_type={claim.device_type!r} at "
        f"{claim.confidence}. This announcement proves a service is running, "
        f"not what the device is."
    )


def test_a_device_advertising_two_media_capabilities_gets_one_verdict(monkeypatch):
    """The oscillation regression, stated as a property.

    A device that speaks both Chromecast and AirPlay is ordinary (every modern
    TV, every Sonos, every Nest Hub). The claims those two announcements produce
    must not be able to disagree about what the device is.
    """
    from modules.device_classification import claim_from_passive

    claimed_types = set()
    for service_type in _MEDIA_CAPABILITY_SERVICES:
        claim = claim_from_passive(_observe(service_type, monkeypatch))
        if claim is not None:
            claimed_types.add(claim.device_type)

    assert len(claimed_types) <= 1, (
        f"One device advertising these services would be assigned "
        f"{sorted(claimed_types)} -- it flips label every time a different "
        f"announcement arrives."
    )


@pytest.mark.parametrize("service_type", _MEDIA_CAPABILITY_SERVICES)
def test_capability_announcement_cannot_outrank_an_identified_vendor(
    service_type, monkeypatch
):
    """A speaker the vendor rules already identified must stay a speaker.

    One capability at a time, because that is how they arrive -- testing the
    whole set at once lets one service that happens to agree with the vendor
    (Spotify Connect -> Smart Speaker) carry the verdict and hide the others.

    Drives the real arbiter with the real claim constructors: nothing about the
    outcome is hardcoded beyond "the vendor's answer survives".
    """
    from modules.device_classification import (
        arbitrate, claim_from_heuristic, claim_from_passive,
    )

    heuristic = claim_from_heuristic(vendor="Sonos", hostname="Barnens-rum")
    assert heuristic.device_type == "Smart Speaker / Audio", (
        "precondition: the vendor rule must identify this device"
    )

    claims = [heuristic]
    claim = claim_from_passive(_observe(service_type, monkeypatch))
    if claim is not None:
        claims.append(claim)

    verdict = arbitrate(claims)
    assert verdict.device_type == "Smart Speaker / Audio", (
        f"a vendor-identified speaker became {verdict.device_type!r} because it "
        f"announced {service_type}"
    )


@pytest.mark.parametrize("service_type", _MEDIA_CAPABILITY_SERVICES)
def test_capability_announcement_is_recorded_as_a_capability(service_type, monkeypatch):
    """What the announcement DOES prove still has to reach the user.

    Dropping the product claim must not throw the observation away -- the
    capability is real, useful information and belongs in known_device.services.
    """
    obs = _observe(service_type, monkeypatch)
    capability = getattr(obs, "capability", "")
    assert capability, (
        f"{service_type} left no capability label; the observation now carries "
        f"no information at all"
    )


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
