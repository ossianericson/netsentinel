"""Tests for modules/name_resolver.py — multi-method hostname resolution."""


def test_name_resolver_import():
    from modules import name_resolver
    assert name_resolver is not None


def test_resolved_name_dataclass():
    from modules.name_resolver import ResolvedName
    rn = ResolvedName(ip="10.0.0.1", display_name="MyDevice", source="rdns")
    assert rn.ip == "10.0.0.1"
    assert rn.display_name == "MyDevice"
    assert rn.source == "rdns"


def test_resolve_returns_resolved_name_type():
    from modules.name_resolver import resolve, ResolvedName
    result = resolve("127.0.0.1", use_netbios=False, use_mdns=False, use_snmp=False)
    assert isinstance(result, ResolvedName)
    assert result.ip == "127.0.0.1"


def test_resolve_batch_returns_iterable():
    from modules.name_resolver import resolve_batch
    results = resolve_batch(["127.0.0.1"])
    assert results is not None


def _encode_dns_labels(name: str) -> bytes:
    out = b""
    for label in name.split("."):
        enc = label.encode()
        out += bytes([len(enc)]) + enc
    return out


def test_mdns_name_ignores_echoed_question_section(monkeypatch):
    """Regression: a real mDNS response can echo the outgoing PTR question
    (".in-addr.arpa" labels) back in the payload. The naive label-sequence
    regex in _mdns_name() previously picked up "in-addr" itself as if it
    were the resolved hostname — seen live against a real Chromecast that
    replied without an answer section, e.g. hostname showed as "in-addr"
    on the DHCP Leases page instead of being left blank.
    """
    from modules import name_resolver

    ip = "192.168.68.60"
    arpa = "60.68.168.192.in-addr.arpa"
    header = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    question = _encode_dns_labels(arpa) + b"\x00\x00\x0c\x00\x01"
    fake_response = header + question  # echoed question only, no real answer

    class _FakeSocket:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): pass
        def sendto(self, data, addr): pass
        def recvfrom(self, n): return (fake_response, ("224.0.0.251", 5353))

    monkeypatch.setattr(name_resolver.socket, "socket", _FakeSocket)

    result = name_resolver._mdns_name(ip)
    assert result != "in-addr", (
        "the echoed .in-addr.arpa question label must not be returned as a hostname"
    )
    assert result == ""


def test_rdns_helper_returns_string():
    from modules.name_resolver import _rdns
    result = _rdns("127.0.0.1", timeout=0.5)
    assert isinstance(result, str)


def test_public_api_signatures():
    from modules import name_resolver
    import inspect
    sig = inspect.signature(name_resolver.resolve)
    params = list(sig.parameters.keys())
    assert "ip" in params


# ── Sprint 1: mac_randomized flag ────────────────────────────────────────────

def test_resolved_name_has_mac_randomized_field():
    from modules.name_resolver import ResolvedName
    r = ResolvedName(ip="192.168.1.1")
    assert hasattr(r, "mac_randomized")
    assert r.mac_randomized is False


def test_resolved_name_mac_randomized_default_false():
    from modules.name_resolver import ResolvedName
    r = ResolvedName(ip="10.0.0.1", mac="f4:f5:d8:00:00:00")
    assert r.mac_randomized is False


def test_resolve_sets_mac_randomized_true(monkeypatch):
    from modules import name_resolver
    monkeypatch.setattr(name_resolver, "_rdns",            lambda ip, timeout=1.0: "")
    monkeypatch.setattr(name_resolver, "_netbios",         lambda ip: "")
    monkeypatch.setattr(name_resolver, "_mdns_name",       lambda ip: "")
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")
    result = name_resolver.resolve(
        "192.168.1.1", mac="02:00:00:00:00:01",
        use_netbios=True, use_mdns=True, use_dhcp=True,
    )
    assert result.mac_randomized is True


def test_resolve_sets_mac_randomized_false(monkeypatch):
    from modules import name_resolver
    monkeypatch.setattr(name_resolver, "_rdns",            lambda ip, timeout=1.0: "")
    monkeypatch.setattr(name_resolver, "_netbios",         lambda ip: "")
    monkeypatch.setattr(name_resolver, "_mdns_name",       lambda ip: "")
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")
    result = name_resolver.resolve(
        "192.168.1.1", mac="f4:f5:d8:aa:bb:cc",
        use_netbios=True, use_mdns=True, use_dhcp=True,
    )
    assert result.mac_randomized is False


def test_resolve_no_mac_sets_mac_randomized_false(monkeypatch):
    from modules import name_resolver
    monkeypatch.setattr(name_resolver, "_rdns",            lambda ip, timeout=1.0: "")
    monkeypatch.setattr(name_resolver, "_netbios",         lambda ip: "")
    monkeypatch.setattr(name_resolver, "_mdns_name",       lambda ip: "")
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")
    result = name_resolver.resolve(
        "192.168.1.1",
        use_netbios=False, use_mdns=False, use_dhcp=False,
    )
    assert result.mac_randomized is False
