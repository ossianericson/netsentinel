"""
Tests for ui/device_labels.py — shared MAC → display-name resolution.

Regression context: App Traffic, Live Bandwidth and Timeline all showed raw MAC
addresses for devices the persistent device map already had names for. Their only
name source was a label map fed from `_apply_mesh_enrichment()`, so with no scan
this session (or a snapshot captured before the feed arrived) every row rendered
as a bare MAC. The resolver adds the two missing fallbacks — known_device and the
OUI registry — and re-resolves at render time instead of trusting the label baked
into the snapshot.

Covers:
  • Resolution order: fed label map → known_device → OUI vendor → MAC
  • A label-map entry that is just the MAC is treated as "no name"
  • Placeholder vendor strings ("Unknown") never reach the UI
  • MAC normalisation (case, dash separators)
  • Store reads are cached, and a store failure is non-fatal
  • OUI lookup never hits the network (RULE 4 — resolver runs on the GUI thread)
"""
from __future__ import annotations

import pytest

from ui.device_labels import DeviceLabelResolver


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _KD:
    """Stand-in for modules.metric_store.KnownDevice (only the fields used)."""

    def __init__(self, custom_name=None, hostname=None, vendor=None, ip=None):
        self.custom_name = custom_name
        self.hostname = hostname
        self.vendor = vendor
        self.ip = ip


class _Store:
    def __init__(self, devices: dict):
        self._devices = devices
        self.calls = 0

    def get_known_devices(self):
        self.calls += 1
        return dict(self._devices)


class _BrokenStore:
    def get_known_devices(self):
        raise RuntimeError("database is locked")


@pytest.fixture(autouse=True)
def _no_oui(monkeypatch):
    """Default: OUI registry knows nothing, so tests assert the other tiers."""
    monkeypatch.setattr("modules.utils.lookup_vendor", lambda *a, **k: None)


# ── Resolution order ──────────────────────────────────────────────────────────

def test_fed_label_map_wins_over_store():
    store = _Store({"aa:bb:cc:dd:ee:ff": _KD(hostname="from-store")})
    r = DeviceLabelResolver(store=store)
    r.set_label_map({"aa:bb:cc:dd:ee:ff": "Musik Barnens Rum"})
    assert r.label_for("aa:bb:cc:dd:ee:ff") == "Musik Barnens Rum"


def test_label_map_entry_equal_to_the_mac_is_ignored():
    """`_hn or _vendor or _mac` in scan_enrichment stores the MAC as its own
    label when a device has neither hostname nor vendor — that is 'no name',
    not a name, and must fall through to the store."""
    store = _Store({"aa:bb:cc:dd:ee:ff": _KD(hostname="Real Name")})
    r = DeviceLabelResolver(store=store)
    r.set_label_map({"aa:bb:cc:dd:ee:ff": "aa:bb:cc:dd:ee:ff"})
    assert r.label_for("aa:bb:cc:dd:ee:ff") == "Real Name"


def test_store_custom_name_beats_hostname_and_vendor():
    store = _Store({"aa:bb:cc:dd:ee:ff": _KD(
        custom_name="Kitchen TV", hostname="host-1", vendor="Sony")})
    r = DeviceLabelResolver(store=store)
    assert r.label_for("aa:bb:cc:dd:ee:ff") == "Kitchen TV"


def test_store_hostname_used_when_no_custom_name():
    store = _Store({"78:c8:81:d7:9f:fe": _KD(hostname="PS5-D79FFE", vendor="Sony")})
    r = DeviceLabelResolver(store=store)
    assert r.label_for("78:c8:81:d7:9f:fe") == "PS5-D79FFE"


def test_store_vendor_used_when_no_hostname():
    store = _Store({"3c:64:cf:e0:27:02": _KD(vendor="TP-Link (Deco mesh)")})
    r = DeviceLabelResolver(store=store)
    assert r.label_for("3c:64:cf:e0:27:02") == "TP-Link (Deco mesh)"


def test_placeholder_vendor_is_not_shown_as_a_name():
    """known_device stores 'Unknown' for unresolvable OUIs — showing that as a
    device name is worse than showing the MAC."""
    store = _Store({"02:a8:f1:3b:93:40": _KD(vendor="Unknown")})
    r = DeviceLabelResolver(store=store)
    assert r.label_for("02:a8:f1:3b:93:40") == "02:a8:f1:3b:93:40"


def test_oui_fallback_when_mac_is_not_in_the_store(monkeypatch):
    monkeypatch.setattr("modules.utils.lookup_vendor", lambda *a, **k: "TP-Link")
    r = DeviceLabelResolver(store=_Store({}))
    assert r.label_for("60:83:e7:88:a0:b1") == "TP-Link"


def test_unknown_mac_falls_back_to_the_mac_itself():
    r = DeviceLabelResolver(store=_Store({}))
    assert r.label_for("de:ad:be:ef:ca:fe") == "de:ad:be:ef:ca:fe"


def test_resolver_works_with_no_store_at_all():
    r = DeviceLabelResolver(store=None)
    r.set_label_map({"aa:bb:cc:dd:ee:ff": "Laptop"})
    assert r.label_for("aa:bb:cc:dd:ee:ff") == "Laptop"
    assert r.label_for("11:22:33:44:55:66") == "11:22:33:44:55:66"


# ── Normalisation ─────────────────────────────────────────────────────────────

def test_mac_lookup_is_case_and_separator_insensitive():
    store = _Store({"aa:bb:cc:dd:ee:ff": _KD(hostname="Printer")})
    r = DeviceLabelResolver(store=store)
    assert r.label_for("AA:BB:CC:DD:EE:FF") == "Printer"
    assert r.label_for("AA-BB-CC-DD-EE-FF") == "Printer"
    assert r.label_for("  aa:bb:cc:dd:ee:ff  ") == "Printer"


def test_empty_mac_returns_empty_string():
    r = DeviceLabelResolver(store=_Store({}))
    assert r.label_for("") == ""
    assert r.label_for(None) == ""


# ── label_for_entry: never worse than the label already on the snapshot ───────

def test_label_for_entry_prefers_resolved_name():
    store = _Store({"aa:bb:cc:dd:ee:ff": _KD(hostname="Resolved")})
    r = DeviceLabelResolver(store=store)
    assert r.label_for_entry("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff") == "Resolved"


def test_label_for_entry_keeps_snapshot_label_when_nothing_resolves():
    """A capture-time label from a richer source (Deco client names) must never
    be thrown away just because the resolver has no opinion."""
    r = DeviceLabelResolver(store=_Store({}))
    assert r.label_for_entry("aa:bb:cc:dd:ee:ff", "Musik Barnens Rum") == "Musik Barnens Rum"


def test_label_for_entry_falls_back_to_mac_when_label_is_blank():
    r = DeviceLabelResolver(store=_Store({}))
    assert r.label_for_entry("aa:bb:cc:dd:ee:ff", "") == "aa:bb:cc:dd:ee:ff"


# ── Caching / robustness ──────────────────────────────────────────────────────

def test_store_is_not_re_read_on_every_lookup():
    store = _Store({"aa:bb:cc:dd:ee:ff": _KD(hostname="A")})
    r = DeviceLabelResolver(store=store)
    for _ in range(10):
        r.label_for("aa:bb:cc:dd:ee:ff")
        r.label_for("11:22:33:44:55:66")
    assert store.calls == 1, "known_device should be read once per TTL window"


def test_set_label_map_invalidates_the_cache():
    store = _Store({"aa:bb:cc:dd:ee:ff": _KD(hostname="Old")})
    r = DeviceLabelResolver(store=store)
    assert r.label_for("aa:bb:cc:dd:ee:ff") == "Old"
    r.set_label_map({"aa:bb:cc:dd:ee:ff": "New Name"})
    assert r.label_for("aa:bb:cc:dd:ee:ff") == "New Name"


def test_store_failure_is_non_fatal():
    r = DeviceLabelResolver(store=_BrokenStore())
    assert r.label_for("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"


def test_oui_lookup_never_goes_online(monkeypatch):
    """RULE 4 — the resolver runs on the GUI thread; an online OUI lookup would
    block it for up to `timeout` seconds per unknown MAC."""
    seen = {}

    def _spy(mac, *a, **kw):
        seen["allow_online"] = kw.get("allow_online", True)
        return None

    monkeypatch.setattr("modules.utils.lookup_vendor", _spy)
    DeviceLabelResolver(store=_Store({})).label_for("60:83:e7:88:a0:b1")
    assert seen["allow_online"] is False


def test_oui_failure_is_non_fatal(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("registry file missing")

    monkeypatch.setattr("modules.utils.lookup_vendor", _boom)
    r = DeviceLabelResolver(store=_Store({}))
    assert r.label_for("60:83:e7:88:a0:b1") == "60:83:e7:88:a0:b1"


# ── label_for_host (S4 — alert surfaces are host=IP for most rule types) ──────

class TestLabelForHost:
    def test_resolves_an_ip_keyed_host_from_known_device(self):
        store = _Store({"f8:7d:76:d1:2c:84": _KD(hostname="Lovisas-ny-iphone", ip="192.168.68.51")})
        r = DeviceLabelResolver(store=store)
        assert r.label_for_host("192.168.68.51") == "Lovisas-ny-iphone"

    def test_falls_back_to_the_bare_ip_when_unknown(self):
        r = DeviceLabelResolver(store=_Store({}))
        assert r.label_for_host("192.168.68.99") == "192.168.68.99"

    def test_a_mac_shaped_host_goes_through_the_mac_path(self):
        store = _Store({"6a:34:64:72:f8:f0": _KD(hostname="known-by-mac")})
        r = DeviceLabelResolver(store=store)
        assert r.label_for_host("6a:34:64:72:f8:f0") == "known-by-mac"

    def test_empty_host_returns_empty_string(self):
        r = DeviceLabelResolver(store=_Store({}))
        assert r.label_for_host("") == ""

    def test_placeholder_ip_name_falls_back_to_the_ip(self):
        store = _Store({"f8:7d:76:d1:2c:84": _KD(vendor="Unknown", ip="192.168.68.51")})
        r = DeviceLabelResolver(store=store)
        assert r.label_for_host("192.168.68.51") == "192.168.68.51"


# ── resolve_alert_message (S4) ─────────────────────────────────────────────────

class TestResolveAlertMessage:
    def test_replaces_the_host_token_with_the_resolved_name(self):
        from ui.device_labels import resolve_alert_message

        store = _Store({"f8:7d:76:d1:2c:84": _KD(hostname="Lovisas-ny-iphone", ip="192.168.68.51")})
        r = DeviceLabelResolver(store=store)
        msg = "Port 8443/HTTPS Alternate opened on 192.168.68.51 since the last sweep."
        resolved = resolve_alert_message(r, "192.168.68.51", msg)
        assert resolved == "Port 8443/HTTPS Alternate opened on Lovisas-ny-iphone since the last sweep."

    def test_leaves_the_message_unchanged_when_nothing_better_is_known(self):
        from ui.device_labels import resolve_alert_message

        r = DeviceLabelResolver(store=_Store({}))
        msg = "Port 22 opened on 192.168.68.99 since the last sweep."
        assert resolve_alert_message(r, "192.168.68.99", msg) == msg

    def test_a_later_learned_name_corrects_an_already_built_message(self):
        """The core render-time promise: resolving is not cached against the
        message string itself, so a name learned after the message was
        first rendered still corrects the next render."""
        from ui.device_labels import resolve_alert_message

        store = _Store({})
        r = DeviceLabelResolver(store=store)
        msg = "Host 192.168.68.51 has gone offline."
        assert resolve_alert_message(r, "192.168.68.51", msg) == msg

        store._devices["f8:7d:76:d1:2c:84"] = _KD(hostname="Lovisas-ny-iphone", ip="192.168.68.51")
        r.invalidate()
        assert resolve_alert_message(r, "192.168.68.51", msg) == "Host Lovisas-ny-iphone has gone offline."

    def test_empty_host_or_message_is_a_noop(self):
        from ui.device_labels import resolve_alert_message

        r = DeviceLabelResolver(store=_Store({}))
        assert resolve_alert_message(r, "", "some message") == "some message"
        assert resolve_alert_message(r, "192.168.68.51", "") == ""
