"""Tests for modules/report_sanitizer.py (TDD — written before implementation)."""

from modules.report_sanitizer import (
    mask_ip,
    vendor_only,
    sanitize_text,
    strip_hostname,
)


def test_mask_ip_private_returns_stable_alias():
    ip_map: dict = {}
    first = mask_ip("192.168.1.50", ip_map)
    again = mask_ip("192.168.1.50", ip_map)
    assert first == again
    assert first.startswith("192.168.1.")


def test_mask_ip_distinct_ips_get_distinct_aliases():
    ip_map: dict = {}
    a = mask_ip("192.168.1.10", ip_map)
    b = mask_ip("10.0.0.5", ip_map)
    assert a != b


def test_mask_ip_public_ip_returns_none():
    ip_map: dict = {}
    assert mask_ip("8.8.8.8", ip_map) is None


def test_mask_ip_invalid_string_returns_none():
    ip_map: dict = {}
    assert mask_ip("not-an-ip", ip_map) is None


def test_vendor_only_uses_known_vendor():
    assert vendor_only(vendor="TP-Link") == "TP-Link device"


def test_vendor_only_falls_back_to_unknown():
    assert vendor_only(vendor=None, mac="") == "Unknown device"


def test_sanitize_text_replaces_known_ip_with_alias():
    ip_map = {"192.168.1.50": "192.168.1.2"}
    text = "The device at 192.168.1.50 is failing."
    out = sanitize_text(text, ip_map)
    assert "192.168.1.50" not in out
    assert "192.168.1.2" in out


def test_sanitize_text_strips_mac_addresses():
    text = "Offending device MAC aa:bb:cc:dd:ee:ff detected."
    out = sanitize_text(text, {})
    assert "aa:bb:cc:dd:ee:ff" not in out.lower()


def test_sanitize_text_omits_unmapped_public_ip():
    text = "Public IP 8.8.8.8 was contacted."
    out = sanitize_text(text, {})
    assert "8.8.8.8" not in out


def test_strip_hostname_always_empty():
    assert strip_hostname("my-laptop.local") == ""


# ── B2: what a diagnostic report must never carry out of the machine ──────────
#
# The three additions below exist because B2 writes a file the user is expected
# to hand to someone else. `sanitize_text` handled IPv4 and MAC only, and this
# is a network scanner: its logs are full of the user's LAN.


def test_sanitize_text_strips_ipv6_addresses():
    """IPv6 is redacted outright, never aliased like a private IPv4.

    `mask_ip` can alias an IPv4 because RFC 1918 makes "private and therefore
    harmless" a decidable property. IPv6 has no equivalent: a SLAAC address
    embeds the interface MAC in EUI-64 form, and a GUA is globally unique to one
    machine, so the only safe transform is removal.
    """
    text = (
        "Neighbour fe80::1c2d:3e4f:5a6b:7c8d%12 unreachable; "
        "gateway 2001:db8:85a3::8a2e:370:7334 timed out."
    )
    out = sanitize_text(text, {})
    assert "fe80::1c2d:3e4f:5a6b:7c8d" not in out
    assert "2001:db8:85a3::8a2e:370:7334" not in out


def test_sanitize_text_leaves_a_mac_shaped_run_of_hex_to_the_mac_rule():
    """A MAC is six colon-separated hex pairs — an IPv6 candidate by shape.

    Whichever rule claims it, the address must not survive; what must not happen
    is the IPv6 rule matching a *timestamp* instead. `23:59:59` is three groups
    of digits and is not an address, and a report whose log timestamps have been
    eaten is unreadable.
    """
    out = sanitize_text("aa:bb:cc:dd:ee:ff seen at 23:59:59 on port 8080", {})
    assert "aa:bb:cc:dd:ee:ff" not in out.lower()
    assert "23:59:59" in out


def test_sanitize_text_strips_ssid_values_but_keeps_the_label():
    """An SSID names the user's home, and often the user.

    There is no pattern that recognises an SSID by its own text — it is
    arbitrary. What is recognisable is the label in front of it, which is how
    every SSID reaches a log here: `netsh wlan show networks` output, and the
    scanner's own records of it. The label survives so the reader can still see
    that a network was found, and how many.
    """
    blob = "SSID 1 : MyHomeNet\nSSID 2 : Nachbar-WLAN\n"
    out = sanitize_text(blob, {})
    assert "MyHomeNet" not in out
    assert "Nachbar-WLAN" not in out
    assert "SSID 1" in out and "SSID 2" in out


def test_sanitize_text_strips_a_quoted_ssid_in_a_traceback():
    """The other shape an SSID arrives in: a repr inside a Python traceback."""
    out = sanitize_text("KeyError: ssid='Cafe Wifi 5G' not in cache", {})
    assert "Cafe Wifi 5G" not in out


def test_sanitize_text_does_not_treat_bssid_as_an_ssid_label():
    """`BSSID` is a MAC field, and its value is already handled by the MAC rule.

    Matching `ssid` inside `BSSID` would consume the rest of that line — taking
    the signal, radio type and channel with it, which is most of what makes a
    wireless log worth reading.
    """
    out = sanitize_text("BSSID 1 : aa:bb:cc:dd:ee:ff\nSignal : 84%\n", {})
    assert "aa:bb:cc:dd:ee:ff" not in out.lower()
    assert "Signal : 84%" in out


def test_sanitize_text_replaces_the_windows_username_but_keeps_the_path():
    r"""Redact the value, keep the property.

    The account name appears in almost every frame of every traceback, because
    `%LOCALAPPDATA%` is under it. Deleting the whole path would take the shape of
    the path with it — and *whether the path was non-ASCII* is precisely the
    RULE-WIN24 signal the hi-IN case turns on. The shape stays here; the answer
    to "was it representable" is carried separately, as the A2 fingerprint's
    `appdata_path_is_ascii` / `appdata_path_encodable_in_acp` booleans.
    """
    line = r'  File "C:\Users\ossia\AppData\Local\NetSentinel\app.py", line 12'
    out = sanitize_text(line, {})
    assert "ossia" not in out
    assert r"C:\Users\<user>\AppData\Local\NetSentinel\app.py" in out


def test_sanitize_text_replaces_a_non_ascii_username_too():
    """The account name that motivated the rule is the one cp1252 cannot encode."""
    out = sanitize_text("C:\\Users\\\u0928\u092e\u0938\u094d\u0924\u0947\\x.log", {})
    assert "\u0928\u092e\u0938" not in out
    assert "C:\\Users\\<user>\\x.log" in out


def test_sanitize_text_redacts_supplied_device_names():
    """Device and room names are the one leak class with no pattern of its own.

    An IP has a shape, a MAC has a shape, an SSID has a label in front of it. A
    device name is arbitrary text in the middle of prose — `Could not fetch
    clients for Vardagsrum (...)` — so the only false-positive-free way to remove
    one is to already know it. The caller supplies the list; this function does
    not go looking, because guessing which words are names is how a redactor
    starts eating the diagnostic.
    """
    names = ["Vardagsrum", "Google streamer"]
    text = "Could not fetch clients for Vardagsrum: Google streamer timed out"
    out = sanitize_text(text, {}, names=names)
    assert "Vardagsrum" not in out
    assert "Google streamer" not in out
    assert "timed out" in out


def test_sanitize_text_redacts_the_longest_matching_name_first():
    """`Floor2 Kitchen` and `Kitchen` are both real node names on one network.

    Shortest-first would replace the `Kitchen` inside `Floor2 Kitchen`, leaving
    `Floor2 [name redacted]` — which still discloses that there is a Floor2, and
    reads as though a second device were involved.
    """
    out = sanitize_text(
        "node Floor2 Kitchen offline", {}, names=["Kitchen", "Floor2 Kitchen"]
    )
    assert "Floor2" not in out


def test_sanitize_text_matches_a_device_name_case_insensitively():
    """Logs and inventory disagree about case constantly; a leak must not hinge on it."""
    out = sanitize_text("client KONTOR dropped", {}, names=["Kontor"])
    assert "KONTOR" not in out


def test_sanitize_text_does_not_match_a_device_name_inside_a_longer_word():
    """A device called `phone` must not turn `headphones` into a redaction.

    Whole-token matching is what keeps an over-broad denylist from shredding the
    surrounding prose — over-redacting is the safe direction, but not at the cost
    of making the log unreadable.
    """
    out = sanitize_text("headphones reconnected", {}, names=["phone"])
    assert "headphones" in out


def test_sanitize_text_without_names_is_unchanged_for_existing_callers():
    """`diagnostic_card` and `forum_export` call this with two arguments.

    The parameter is optional and defaults to redacting nothing extra, so the two
    already-shipped share-to-public paths keep the behaviour they were verified
    with.
    """
    assert sanitize_text("Vardagsrum is fine", {}) == "Vardagsrum is fine"


def test_sanitize_text_handles_a_forward_slash_windows_path():
    """Python emits either separator; a traceback can carry both in one file."""
    out = sanitize_text("open('C:/Users/ossia/Documents/NetSentinel/log.csv')", {})
    assert "ossia" not in out
    assert "C:/Users/<user>/Documents" in out
