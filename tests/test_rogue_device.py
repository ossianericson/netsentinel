"""Tests for modules/rogue_device.py — rogue device fingerprinter."""
import json
from modules.rogue_device import DeviceInfo, _get_default_gateway, _get_arp_table, scan


def test_import():
    from modules import rogue_device as m
    assert hasattr(m, "scan")
    assert hasattr(m, "DeviceInfo")
    assert hasattr(m, "_get_arp_table")


def test_device_info_fields():
    d = DeviceInfo(
        ip="192.168.1.1",
        mac="aa:bb:cc:dd:ee:ff",
        vendor="Cisco",
        hostname="router.local",
    )
    assert d.ip == "192.168.1.1"
    assert d.mac == "aa:bb:cc:dd:ee:ff"
    assert d.vendor == "Cisco"


def test_device_info_defaults():
    d = DeviceInfo(ip="10.0.0.1", mac="00:11:22:33:44:55")
    assert d.hostname == ""
    assert d.risk_level == "UNKNOWN"
    assert d.known_issues == []


def test_get_default_gateway_returns_str_or_none():
    gw = _get_default_gateway()
    assert gw is None or isinstance(gw, str)


def test_get_arp_table_returns_list():
    result = _get_arp_table()
    assert isinstance(result, list)


def test_scan_with_offenders_path(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([{"ouis": [], "vendor": "Test", "known_issues": []}]))
    result = scan(offenders_path=offenders)
    assert isinstance(result, dict)
    assert "devices" in result


def test_scan_returns_known_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))
    result = scan(offenders_path=offenders)
    assert "plain_verdict" in result
    assert "total_count" in result


# ── Gateway device-type and hostname sanity tests ────────────────────────────

from modules.rogue_device import _CONSUMER_HOSTNAME_RE


def test_consumer_hostname_re_matches_playstation():
    assert _CONSUMER_HOSTNAME_RE.search("Playstation 4")


def test_consumer_hostname_re_matches_xbox():
    assert _CONSUMER_HOSTNAME_RE.search("Xbox Series X")


def test_consumer_hostname_re_matches_iphone():
    assert _CONSUMER_HOSTNAME_RE.search("iPhone-12")


def test_consumer_hostname_re_no_match_for_deco():
    assert not _CONSUMER_HOSTNAME_RE.search("deco-main")


def test_consumer_hostname_re_no_match_for_generic_router():
    assert not _CONSUMER_HOSTNAME_RE.search("gateway.local")


def test_gateway_device_type_is_router(tmp_path, monkeypatch):
    """Gateway IP must be classified as Router / Gateway regardless of OUI."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    gw_ip = "192.168.1.1"
    liteon_mac = "5c:93:a2:11:22:33"

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(gw_ip, liteon_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: gw_ip)
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._resolve_name", None)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)
    devices = result["devices"]
    assert len(devices) == 1
    assert devices[0].device_type == "Router / Gateway"


def test_proxy_arp_ip_detected_and_excluded(tmp_path, monkeypatch):
    """IPs that share the gateway MAC (proxy ARP) must be excluded from results."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    gw_ip  = "192.168.1.1"
    gw_mac = "a8:59:35:11:22:33"
    ps4_ip = "192.168.1.71"

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table",
        lambda: [(gw_ip, gw_mac), (ps4_ip, gw_mac)],
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: gw_ip)
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._resolve_name", None)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)

    # ps4_ip shares the gateway MAC — must land in proxy_arp_ips
    assert ps4_ip in result["proxy_arp_ips"]
    # Only the gateway itself should appear in devices
    assert result["total_count"] == 1
    ips = [d.ip for d in result["devices"]]
    assert gw_ip in ips
    assert ps4_ip not in ips


def test_proxy_arp_ips_empty_when_no_shared_mac(tmp_path, monkeypatch):
    """proxy_arp_ips must be empty when every IP has a unique MAC."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table",
        lambda: [("192.168.1.1", "aa:bb:cc:00:00:01"), ("192.168.1.2", "aa:bb:cc:00:00:02")],
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._resolve_name", None)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)
    assert result["proxy_arp_ips"] == set()


def test_gateway_consumer_hostname_is_cleared(tmp_path, monkeypatch):
    """Gateway IP with a PS4 hostname must have its hostname cleared."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    gw_ip = "192.168.1.1"
    liteon_mac = "5c:93:a2:11:22:33"

    from unittest.mock import MagicMock
    fake_name_info = MagicMock()
    fake_name_info.hostname = "Playstation 4"
    fake_name_info.vendor = ""
    fake_name_info.device_type = ""

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(gw_ip, liteon_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: gw_ip)
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda _ips, **_kw: {gw_ip: fake_name_info})
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)

    result = scan(offenders_path=offenders)
    devices = result["devices"]
    assert len(devices) == 1
    assert devices[0].hostname == ""
    assert devices[0].device_type == "Router / Gateway"


def test_device_info_has_model_field_default_empty():
    """F-51: DeviceInfo had no 'model' field at all -- the OUI registry's
    model string was computed by name_resolver but had nowhere to land."""
    d = DeviceInfo(ip="10.0.0.5", mac="aa:bb:cc:dd:ee:ff")
    assert d.model == ""


def test_scan_copies_model_from_name_resolver_onto_device_info(tmp_path, monkeypatch):
    """F-51: modules.name_resolver.resolve_batch() already computes .model
    from the OUI registry (mac_registry.model_from_mac) -- scan() must copy
    it onto DeviceInfo.model instead of discarding it."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip = "192.168.1.50"
    dev_mac = "b0:34:95:11:22:33"

    from unittest.mock import MagicMock
    fake_name_info = MagicMock()
    fake_name_info.hostname = "kitchen-echo"
    fake_name_info.vendor = "Amazon Technologies Inc."
    fake_name_info.device_type = ""
    fake_name_info.model = "Echo Dot"

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: fake_name_info)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr(
        "modules.name_resolver.resolve_batch",
        lambda entries, **kw: {dev_ip: fake_name_info},
    )

    result = scan(offenders_path=offenders)
    devices = result["devices"]
    assert len(devices) == 1
    assert devices[0].model == "Echo Dot"
    assert devices[0].vendor == "Amazon Technologies Inc."


# ── Part 1/C1: progress_cb forwarding ────────────────────────────────────────

def test_scan_forwards_progress_cb_to_resolve_batch(tmp_path, monkeypatch):
    """scan()'s progress_cb must reach name resolution -- the slowest phase on
    a large ARP table -- so the caller can report real "n/total" progress."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.50", "b0:34:95:11:22:33"
    from unittest.mock import MagicMock
    fake_name_info = MagicMock()
    fake_name_info.hostname = "kitchen-echo"

    captured = {}

    def _fake_resolve_batch(entries, **kw):
        captured["progress_cb"] = kw.get("progress_cb")
        return {dev_ip: fake_name_info}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: fake_name_info)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    messages = []
    scan(offenders_path=offenders, progress_cb=messages.append)

    assert captured["progress_cb"] == messages.append
    captured["progress_cb"]("probe")
    # messages[0] is the adaptive-timing profile label (Part 2/L1), emitted
    # before resolve_batch runs; "probe" is what we appended above.
    assert messages == [messages[0], "probe"]
    assert messages[0].startswith("Timing:")


# ── Part 2/L1: adaptive timing profile forwarded to resolve_batch ───────────

def test_scan_forwards_timing_profile_to_resolve_batch(tmp_path, monkeypatch):
    """scan() must derive a TimingProfile from the measured gateway RTT and pass
    it into resolve_batch(), and surface its label via progress_cb (plan's
    'surface the chosen profile in the UI' requirement)."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.50", "b0:34:95:11:22:33"
    from unittest.mock import MagicMock
    fake_name_info = MagicMock()
    fake_name_info.hostname = "kitchen-echo"

    captured = {}

    def _fake_resolve_batch(entries, **kw):
        captured["timing_profile"] = kw.get("timing_profile")
        return {dev_ip: fake_name_info}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 250.0)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: fake_name_info)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    messages = []
    scan(offenders_path=offenders, progress_cb=messages.append)

    from modules.adaptive_timing import TimingProfile
    profile = captured["timing_profile"]
    assert isinstance(profile, TimingProfile)
    assert profile.rtt_base_ms == 250.0
    assert any(m == profile.label for m in messages), (
        f"the chosen timing profile's label must be surfaced via progress_cb, got: {messages}"
    )


# ── Part 2/L7: stream each device the moment its ARP entry is known ─────────
# Regression coverage for "a 715-device resolve produces nothing on screen for
# minutes and then everything at once" — device_cb must fire the instant an
# ARP entry's skeleton is built (before name resolution), then again once its
# hostname resolves, so a caller can upsert a live-preview table row by row.

def test_scan_calls_device_cb_immediately_per_arp_entry(tmp_path, monkeypatch):
    """device_cb must be called for every ARP entry even before resolve_batch
    is invoked at all -- proves the skeleton doesn't wait on name resolution."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.50", "b0:34:95:11:22:33"

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    # _resolve_name must be non-None to take the resolve_batch code path, but
    # we intercept resolve_batch itself before device_cb assertions run.
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)

    streamed: list = []

    def _device_cb(info):
        streamed.append(info)
        # The critical assertion: this fires from the skeleton phase, which
        # must complete (and call device_cb) BEFORE resolve_batch runs.
        monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})

    scan(offenders_path=offenders, device_cb=_device_cb)

    assert len(streamed) >= 1
    assert streamed[0].ip == dev_ip
    assert streamed[0].hostname == ""  # skeleton call — name not resolved yet


def test_scan_calls_device_cb_again_with_resolved_hostname(tmp_path, monkeypatch):
    """device_cb must fire a second time, in place, once the device's name
    resolves -- so a caller can update the same table row rather than append."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.50", "b0:34:95:11:22:33"

    from modules.name_resolver import ResolvedName
    resolved_name = ResolvedName(ip=dev_ip, hostname="kitchen-echo")

    def _fake_resolve_batch(entries, on_result=None, **kw):
        if on_result:
            on_result(dev_ip, resolved_name)
        return {dev_ip: resolved_name}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    # Snapshot info.hostname at call time -- device_cb receives the SAME mutable
    # DeviceInfo object on both calls (that's the point: "update in place"), so
    # appending the object itself would make both list entries alias the final
    # mutation. Capture the immutable string value instead.
    hostnames_seen: list = []
    scan(offenders_path=offenders, device_cb=lambda info: hostnames_seen.append(info.hostname) if info.ip == dev_ip else None)

    assert hostnames_seen[0] == "", "first call must be the pre-resolution skeleton"
    assert hostnames_seen[-1] == "kitchen-echo", "last call must carry the resolved name"


def test_scan_device_cb_omitted_produces_identical_final_result(tmp_path, monkeypatch):
    """Passing device_cb must never change scan()'s returned dict."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.50", "b0:34:95:11:22:33"
    from modules.name_resolver import ResolvedName
    resolved_name = ResolvedName(ip=dev_ip, hostname="kitchen-echo", vendor="Amazon")

    def _fake_resolve_batch(entries, on_result=None, **kw):
        if on_result:
            on_result(dev_ip, resolved_name)
        return {dev_ip: resolved_name}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    result_without_cb = scan(offenders_path=offenders)
    result_with_cb = scan(offenders_path=offenders, device_cb=lambda info: None)

    def _snapshot(devices):
        return [(d.ip, d.mac, d.vendor, d.hostname, d.device_type, d.risk_level, d.verdict)
                for d in devices]

    assert _snapshot(result_without_cb["devices"]) == _snapshot(result_with_cb["devices"])
    assert result_without_cb["plain_verdict"] == result_with_cb["plain_verdict"]
    assert result_without_cb["total_count"] == result_with_cb["total_count"]


def test_scan_oui_matched_vendor_survives_resolution_phase(tmp_path, monkeypatch):
    """Regression guard: an offenders.json vendor match happens in the skeleton
    phase (before resolution). The later resolved name_info's generic
    mac-registry vendor must NOT clobber it once the name resolves."""
    dev_ip, dev_mac = "192.168.1.60", "aa:bb:cc:11:22:33"
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([
        {"ouis": ["aa:bb:cc"], "vendor": "Known Bad Router Co", "known_issues": ["floods"],
         "risk_level": "MEDIUM"},
    ]))

    from modules.name_resolver import ResolvedName
    resolved_name = ResolvedName(ip=dev_ip, hostname="some-host", vendor="Generic OUI Vendor Inc.")

    def _fake_resolve_batch(entries, on_result=None, **kw):
        if on_result:
            on_result(dev_ip, resolved_name)
        return {dev_ip: resolved_name}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    result = scan(offenders_path=offenders)
    devices = result["devices"]
    assert len(devices) == 1
    assert devices[0].vendor == "Known Bad Router Co", (
        "offenders-matched vendor must survive the resolution phase, not be "
        f"overwritten by the resolved name's generic vendor; got {devices[0].vendor!r}"
    )


def test_scan_device_cb_exception_does_not_abort_scan(tmp_path, monkeypatch):
    """A broken caller-supplied device_cb must not prevent scan() from completing."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.61", "aa:bb:cc:11:22:44"
    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})

    def _broken_cb(info):
        raise RuntimeError("UI callback exploded")

    result = scan(offenders_path=offenders, device_cb=_broken_cb)
    assert result["total_count"] == 1


# ── Part 2/L8: TTL hostname cache ────────────────────────────────────────────

def test_device_info_name_resolved_fresh_defaults_false():
    d = DeviceInfo(ip="10.0.0.1", mac="00:11:22:33:44:55")
    assert d.name_resolved_fresh is False


class _FakeKnownDevice:
    """Minimal duck-typed stand-in for metric_store_schema.KnownDevice --
    scan() must never import KnownDevice/MetricStore directly."""
    def __init__(self, hostname, hostname_resolved_at):
        self.hostname = hostname
        self.hostname_resolved_at = hostname_resolved_at


def test_scan_skips_resolve_batch_for_fresh_cached_mac(tmp_path, monkeypatch):
    """A MAC with a resolved_at timestamp inside the 7-day TTL must not be
    handed to resolve_batch at all -- its cached hostname is applied directly,
    while a MAC with no cache entry still resolves normally in the same scan."""
    import time as _time

    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    cached_ip, cached_mac = "192.168.1.70", "aa:bb:cc:22:33:44"
    fresh_ip, fresh_mac = "192.168.1.71", "aa:bb:cc:22:33:55"
    now = int(_time.time())
    known_devices = {cached_mac: _FakeKnownDevice("cached-host", now - 100)}

    from modules.name_resolver import ResolvedName
    fresh_resolved = ResolvedName(ip=fresh_ip, hostname="freshly-resolved")

    entries_seen: list = []

    def _fake_resolve_batch(entries, on_result=None, **kw):
        entries_seen.extend(entries)
        if on_result:
            on_result(fresh_ip, fresh_resolved)
        return {fresh_ip: fresh_resolved}

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table",
        lambda: [(cached_ip, cached_mac), (fresh_ip, fresh_mac)],
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    result = scan(offenders_path=offenders, known_devices=known_devices)

    resolved_ips = {e["ip"] for e in entries_seen}
    assert cached_ip not in resolved_ips, "cached MAC must be excluded from resolve_batch"
    assert fresh_ip in resolved_ips, "uncached MAC must still be resolved normally"

    by_ip = {d.ip: d for d in result["devices"]}
    assert by_ip[cached_ip].hostname == "cached-host"
    assert by_ip[cached_ip].name_resolved_fresh is False
    assert by_ip[fresh_ip].hostname == "freshly-resolved"
    assert by_ip[fresh_ip].name_resolved_fresh is True


def test_scan_reresolves_expired_cached_mac(tmp_path, monkeypatch):
    """A cache entry older than the 7-day TTL must be treated as stale and
    re-resolved through the normal network path."""
    import time as _time

    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.72", "aa:bb:cc:22:33:66"
    now = int(_time.time())
    stale_ts = now - (8 * 24 * 3600)  # 8 days old -- past the 7-day TTL
    known_devices = {dev_mac: _FakeKnownDevice("stale-cached-host", stale_ts)}

    from modules.name_resolver import ResolvedName
    resolved_name = ResolvedName(ip=dev_ip, hostname="re-resolved-host")

    def _fake_resolve_batch(entries, on_result=None, **kw):
        assert any(e["ip"] == dev_ip for e in entries), (
            "an expired cache entry must still be handed to resolve_batch"
        )
        if on_result:
            on_result(dev_ip, resolved_name)
        return {dev_ip: resolved_name}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    result = scan(offenders_path=offenders, known_devices=known_devices)
    dev = result["devices"][0]
    assert dev.hostname == "re-resolved-host"
    assert dev.name_resolved_fresh is True


def test_scan_cache_hit_honors_blank_cached_hostname(tmp_path, monkeypatch):
    """A device that consistently fails to resolve (blank hostname) but was
    actively probed recently must NOT be re-probed every scan -- this is what
    keeps a scan from hammering a consistently-silent VPN-blocked device."""
    import time as _time

    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.73", "aa:bb:cc:22:33:77"
    now = int(_time.time())
    known_devices = {dev_mac: _FakeKnownDevice("", now - 100)}

    def _resolve_batch_must_not_probe_this_ip(entries, **kw):
        assert not any(e["ip"] == dev_ip for e in entries), (
            "a fresh cache entry -- even with a blank hostname -- must not be re-probed"
        )
        return {}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _resolve_batch_must_not_probe_this_ip)

    result = scan(offenders_path=offenders, known_devices=known_devices)
    dev = result["devices"][0]
    assert dev.hostname == ""
    assert dev.name_resolved_fresh is False


def test_scan_without_known_devices_marks_devices_fresh(tmp_path, monkeypatch):
    """Omitting known_devices entirely (existing callers/tests) must reproduce
    today's behaviour exactly: every device is actively resolved and marked fresh."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    dev_ip, dev_mac = "192.168.1.74", "aa:bb:cc:22:33:88"
    from modules.name_resolver import ResolvedName
    resolved_name = ResolvedName(ip=dev_ip, hostname="normal-host")

    def _fake_resolve_batch(entries, on_result=None, **kw):
        if on_result:
            on_result(dev_ip, resolved_name)
        return {dev_ip: resolved_name}

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", _fake_resolve_batch)

    result = scan(offenders_path=offenders)  # no known_devices arg at all
    dev = result["devices"][0]
    assert dev.hostname == "normal-host"
    assert dev.name_resolved_fresh is True


# ── L5: scan scope (scope_cidr) ───────────────────────────────────────────────

def test_scan_scope_cidr_none_is_byte_identical_to_todays_unfiltered_behaviour(tmp_path, monkeypatch):
    """Default (scope_cidr omitted) must reproduce pre-L5 behaviour exactly: every
    ARP entry is processed regardless of subnet, and out_of_scope_devices is empty."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))
    in_ip, in_mac = "192.168.1.60", "aa:bb:cc:11:22:33"
    foreign_ip, foreign_mac = "10.8.0.5", "aa:bb:cc:11:22:44"

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table", lambda: [(in_ip, in_mac), (foreign_ip, foreign_mac)]
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})

    result = scan(offenders_path=offenders)  # scope_cidr omitted

    assert {d.ip for d in result["devices"]} == {in_ip, foreign_ip}
    assert result["total_count"] == 2
    assert result["out_of_scope_devices"] == []


def test_scan_scope_cidr_excludes_foreign_subnet_arp_entries(tmp_path, monkeypatch):
    """A caller-supplied scope_cidr must bound the ARP-table pass: entries outside
    it are excluded from devices/total_count and reported separately, never
    silently dropped."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))
    in_ip, in_mac = "192.168.1.60", "aa:bb:cc:11:22:33"
    foreign_ip, foreign_mac = "10.8.0.5", "aa:bb:cc:11:22:44"

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table", lambda: [(in_ip, in_mac), (foreign_ip, foreign_mac)]
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})

    result = scan(offenders_path=offenders, scope_cidr="192.168.1.0/24")

    assert [d.ip for d in result["devices"]] == [in_ip]
    assert result["total_count"] == 1
    out_of_scope = result["out_of_scope_devices"]
    assert len(out_of_scope) == 1
    assert out_of_scope[0].ip == foreign_ip
    assert out_of_scope[0].mac == foreign_mac
    assert "192.168.1.0/24" in out_of_scope[0].verdict


def test_scan_scope_cidr_plain_verdict_mentions_out_of_scope_count(tmp_path, monkeypatch):
    """The out-of-scope count must reach the user through the existing
    plain_verdict display channel (ui/monitor_state.py already reads
    _m1_result['plain_verdict']) -- never silently exceed OR silently narrow
    scope without saying so."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))
    in_ip, in_mac = "192.168.1.60", "aa:bb:cc:11:22:33"
    foreign_ip, foreign_mac = "10.8.0.5", "aa:bb:cc:11:22:44"

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table", lambda: [(in_ip, in_mac), (foreign_ip, foreign_mac)]
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})

    result = scan(offenders_path=offenders, scope_cidr="192.168.1.0/24")

    assert "1 device(s) seen in ARP outside your declared scan scope" in result["plain_verdict"]


def test_scan_scope_cidr_out_of_scope_devices_are_not_streamed_via_device_cb(tmp_path, monkeypatch):
    """Out-of-scope devices are reported in the result dict but deliberately not
    pushed through device_cb — they never touch the live-streaming table path."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))
    in_ip, in_mac = "192.168.1.60", "aa:bb:cc:11:22:33"
    foreign_ip, foreign_mac = "10.8.0.5", "aa:bb:cc:11:22:44"

    monkeypatch.setattr(
        "modules.rogue_device._get_arp_table", lambda: [(in_ip, in_mac), (foreign_ip, foreign_mac)]
    )
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})

    seen_ips = []
    scan(offenders_path=offenders, scope_cidr="192.168.1.0/24", device_cb=lambda d: seen_ips.append(d.ip))

    assert foreign_ip not in seen_ips
    assert in_ip in seen_ips


# ── L9: per-phase scan timing telemetry ───────────────────────────────────────

def test_scan_timing_log_failure_is_non_fatal(tmp_path, monkeypatch):
    """A broken logging/filesystem path must never break scan() — timing
    telemetry is diagnostic-only, not load-bearing."""
    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))

    def _boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: None)
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.utils.get_app_data_dir", _boom)

    result = scan(offenders_path=offenders)  # must not raise
    assert isinstance(result, dict)


def test_scan_timing_log_writes_one_line_per_scan(tmp_path, monkeypatch):
    """The timing log line carries the phase breakdown and device count so a
    future 'it was slow' report is diagnosable from a pasted log file."""
    import logging as _logging

    offenders = tmp_path / "offenders.json"
    offenders.write_text(json.dumps([]))
    dev_ip, dev_mac = "192.168.1.60", "aa:bb:cc:11:22:33"

    monkeypatch.setattr("modules.rogue_device._get_arp_table", lambda: [(dev_ip, dev_mac)])
    monkeypatch.setattr("modules.rogue_device._get_default_gateway", lambda: "192.168.1.1")
    monkeypatch.setattr("modules.rogue_device.measure_gateway_rtt", lambda gw, **kw: 1.0)
    monkeypatch.setattr("modules.rogue_device._mac_registry_lookup", None)
    monkeypatch.setattr("modules.rogue_device._resolve_name", lambda ip: None)
    monkeypatch.setattr("modules.name_resolver.resolve_batch", lambda entries, **kw: {})
    monkeypatch.setattr("modules.utils.get_app_data_dir", lambda: tmp_path)

    logger = _logging.getLogger("netsentinel.scan_timing")
    logger.handlers.clear()

    scan(offenders_path=offenders)

    log_path = tmp_path / "netsentinel_scan_timing.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "devices=1" in content
    assert "phase1_skeleton=" in content
    assert "phase2_resolve=" in content
    logger.handlers.clear()
