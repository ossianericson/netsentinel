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
    monkeypatch.setattr(name_resolver, "_netbios",         lambda ip, timeout=3.0: "")
    monkeypatch.setattr(name_resolver, "_mdns_name",       lambda ip, timeout=1.5: "")
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")
    result = name_resolver.resolve(
        "192.168.1.1", mac="02:00:00:00:00:01",
        use_netbios=True, use_mdns=True, use_dhcp=True,
    )
    assert result.mac_randomized is True


def test_resolve_sets_mac_randomized_false(monkeypatch):
    from modules import name_resolver
    monkeypatch.setattr(name_resolver, "_rdns",            lambda ip, timeout=1.0: "")
    monkeypatch.setattr(name_resolver, "_netbios",         lambda ip, timeout=3.0: "")
    monkeypatch.setattr(name_resolver, "_mdns_name",       lambda ip, timeout=1.5: "")
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")
    result = name_resolver.resolve(
        "192.168.1.1", mac="f4:f5:d8:aa:bb:cc",
        use_netbios=True, use_mdns=True, use_dhcp=True,
    )
    assert result.mac_randomized is False


def test_resolve_no_mac_sets_mac_randomized_false(monkeypatch):
    from modules import name_resolver
    monkeypatch.setattr(name_resolver, "_rdns",            lambda ip, timeout=1.0: "")
    monkeypatch.setattr(name_resolver, "_netbios",         lambda ip, timeout=3.0: "")
    monkeypatch.setattr(name_resolver, "_mdns_name",       lambda ip, timeout=1.5: "")
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")
    result = name_resolver.resolve(
        "192.168.1.1",
        use_netbios=False, use_mdns=False, use_dhcp=False,
    )
    assert result.mac_randomized is False


# ── Part 1/C1: resolve_batch progress_cb ─────────────────────────────────────
# Regression coverage for the "progress bar unrelated to the scan" bug — the
# slowest phase (name resolution across the whole ARP table) previously
# reported nothing at all. progress_cb must fire with the real denominator.

def test_resolve_batch_calls_progress_cb_with_real_denominator(monkeypatch):
    from modules import name_resolver

    monkeypatch.setattr(name_resolver, "resolve",
        lambda ip, mac="", **kw: name_resolver.ResolvedName(ip=ip))

    devices = [{"ip": f"192.168.1.{i}", "mac": ""} for i in range(1, 6)]
    messages = []
    name_resolver.resolve_batch(devices, progress_cb=messages.append)

    assert messages, "progress_cb must be called at least once for a non-empty batch"
    assert all("5" in m for m in messages), (
        f"every progress message must carry the real total (5), got: {messages}"
    )


def test_resolve_batch_progress_cb_reaches_completion(monkeypatch):
    from modules import name_resolver

    monkeypatch.setattr(name_resolver, "resolve",
        lambda ip, mac="", **kw: name_resolver.ResolvedName(ip=ip))

    devices = [{"ip": f"192.168.1.{i}", "mac": ""} for i in range(1, 4)]
    messages = []
    name_resolver.resolve_batch(devices, progress_cb=messages.append)

    assert messages[-1].split(":")[-1].strip().startswith("3/3"), (
        f"final progress message must report completion (3/3), got: {messages[-1]!r}"
    )


def test_resolve_batch_without_progress_cb_still_works(monkeypatch):
    from modules import name_resolver

    monkeypatch.setattr(name_resolver, "resolve",
        lambda ip, mac="", **kw: name_resolver.ResolvedName(ip=ip))

    devices = [{"ip": "192.168.1.1", "mac": ""}]
    results = name_resolver.resolve_batch(devices)
    assert "192.168.1.1" in results


# ── Part 2/L7: resolve_batch on_result streaming callback ───────────────────
# Regression coverage for "a 715-device resolve produces nothing on screen for
# minutes and then everything at once" — resolve_batch must be able to notify
# the caller the instant EACH device finishes, not just via the throttled
# progress_cb string (which reports "n/total" but never the individual result).

def test_resolve_batch_calls_on_result_once_per_device(monkeypatch):
    from modules import name_resolver

    monkeypatch.setattr(name_resolver, "resolve",
        lambda ip, mac="", **kw: name_resolver.ResolvedName(ip=ip, hostname=f"host-{ip[-1]}"))

    devices = [{"ip": f"192.168.1.{i}", "mac": ""} for i in range(1, 6)]
    seen = {}
    name_resolver.resolve_batch(devices, on_result=lambda ip, name: seen.__setitem__(ip, name))

    assert set(seen) == {d["ip"] for d in devices}
    assert seen["192.168.1.1"].hostname == "host-1"


def test_resolve_batch_on_result_receives_fallback_resolvedname_on_exception(monkeypatch):
    """A device whose resolve() call raises must still reach on_result — with a
    blank ResolvedName — exactly like it still lands in the returned dict today."""
    from modules import name_resolver

    def _boom(ip, mac="", **kw):
        raise RuntimeError("probe failed")

    monkeypatch.setattr(name_resolver, "resolve", _boom)

    devices = [{"ip": "192.168.1.9", "mac": ""}]
    seen = {}
    name_resolver.resolve_batch(devices, on_result=lambda ip, name: seen.__setitem__(ip, name))

    assert "192.168.1.9" in seen
    assert seen["192.168.1.9"].hostname == ""


def test_resolve_batch_on_result_exception_does_not_abort_batch(monkeypatch):
    """A broken caller-supplied on_result callback must not prevent other
    devices in the batch from resolving -- it is UI-feedback, not load-bearing."""
    from modules import name_resolver

    monkeypatch.setattr(name_resolver, "resolve",
        lambda ip, mac="", **kw: name_resolver.ResolvedName(ip=ip))

    devices = [{"ip": f"192.168.1.{i}", "mac": ""} for i in range(1, 4)]

    def _broken_on_result(ip, name):
        raise RuntimeError("UI callback exploded")

    results = name_resolver.resolve_batch(devices, on_result=_broken_on_result)
    assert set(results) == {d["ip"] for d in devices}


def test_resolve_batch_without_on_result_still_works(monkeypatch):
    """Omitting on_result must reproduce today's behaviour exactly."""
    from modules import name_resolver

    monkeypatch.setattr(name_resolver, "resolve",
        lambda ip, mac="", **kw: name_resolver.ResolvedName(ip=ip))

    devices = [{"ip": "192.168.1.1", "mac": ""}]
    results = name_resolver.resolve_batch(devices)
    assert "192.168.1.1" in results


# ── Part 2/L2a: socket-based NBSTAT (replaces the nbtstat/nmblookup subprocess) ──

def _pad15(name: str) -> bytes:
    b = name.encode("ascii")
    assert len(b) <= 15
    return b + b" " * (15 - len(b))


def _build_fake_nbstat_response(entries) -> bytes:
    """entries: list of (name, suffix, flags) — mirrors a real NODE STATUS response."""
    from modules.name_resolver import _build_nbstat_query

    header = b"\x00\x00" + b"\x84\x00" + b"\x00\x01" + b"\x00\x01" + b"\x00\x00" + b"\x00\x00"
    rr_name = _build_nbstat_query()[12:12 + 34]  # echoes the query's encoded wildcard name
    rr_type_class_ttl = b"\x00\x21" + b"\x00\x01" + b"\x00\x00\x00\x00"
    rdata = bytes([len(entries)])
    for name, suffix, flags in entries:
        rdata += _pad15(name) + bytes([suffix]) + flags.to_bytes(2, "big")
    rdlength = len(rdata).to_bytes(2, "big")
    return header + rr_name + rr_type_class_ttl + rdlength + rdata


def test_build_nbstat_query_has_correct_length_and_header():
    from modules.name_resolver import _build_nbstat_query
    query = _build_nbstat_query()
    assert len(query) == 50
    assert query[4:6]   == b"\x00\x01"  # QDCOUNT = 1
    assert query[6:8]   == b"\x00\x00"  # ANCOUNT = 0
    assert query[8:10]  == b"\x00\x00"  # NSCOUNT = 0
    assert query[10:12] == b"\x00\x00"  # ARCOUNT = 0


def test_build_nbstat_query_encodes_wildcard_name():
    from modules.name_resolver import _build_nbstat_query
    query = _build_nbstat_query()
    name_section = query[12:12 + 34]
    assert name_section[0] == 32   # length byte
    assert name_section[-1] == 0   # zero-length terminator label
    encoded = name_section[1:-1]
    assert encoded[:2] == b"CK"          # '*' first-level-encoded
    assert encoded[2:] == b"AA" * 15     # 15 NUL padding bytes, first-level-encoded


def test_build_nbstat_query_qtype_nbstat_class_in():
    from modules.name_resolver import _build_nbstat_query
    query = _build_nbstat_query()
    assert query[46:48] == b"\x00\x21"  # QTYPE = NBSTAT
    assert query[48:50] == b"\x00\x01"  # QCLASS = IN


def test_parse_nbstat_response_returns_unique_workstation_name():
    from modules.name_resolver import _parse_nbstat_response
    data = _build_fake_nbstat_response([
        ("WORKGROUP", 0x00, 0x8000),   # group name — must be skipped
        ("MYPC", 0x00, 0x0000),        # unique <00> workstation name — this one
    ])
    assert _parse_nbstat_response(data) == "MYPC"


def test_parse_nbstat_response_no_unique_name_returns_empty():
    from modules.name_resolver import _parse_nbstat_response
    data = _build_fake_nbstat_response([("WORKGROUP", 0x00, 0x8000)])
    assert _parse_nbstat_response(data) == ""


def test_parse_nbstat_response_ancount_zero_returns_empty():
    from modules.name_resolver import _parse_nbstat_response
    header = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
    assert _parse_nbstat_response(header) == ""


def test_parse_nbstat_response_truncated_data_returns_empty_no_exception():
    from modules.name_resolver import _parse_nbstat_response
    assert _parse_nbstat_response(b"\x00\x01") == ""
    assert _parse_nbstat_response(b"") == ""


def test_netbios_returns_parsed_name_via_fake_socket(monkeypatch):
    from modules import name_resolver
    data = _build_fake_nbstat_response([("MYPC", 0x00, 0x0000)])

    class _FakeSocket:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): pass
        def sendto(self, pkt, addr): pass
        def recvfrom(self, n): return (data, ("192.168.1.50", 137))

    monkeypatch.setattr(name_resolver.socket, "socket", _FakeSocket)
    assert name_resolver._netbios("192.168.1.50") == "MYPC"


def test_netbios_returns_empty_on_timeout(monkeypatch):
    import socket as _socket
    from modules import name_resolver

    class _FakeSocket:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): pass
        def sendto(self, pkt, addr): pass
        def recvfrom(self, n): raise _socket.timeout()

    monkeypatch.setattr(name_resolver.socket, "socket", _FakeSocket)
    assert name_resolver._netbios("192.168.1.51") == ""


def test_netbios_forwards_timeout_to_socket(monkeypatch):
    from modules import name_resolver
    captured = {}

    class _FakeSocket:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): captured["timeout"] = t
        def sendto(self, pkt, addr): pass
        def recvfrom(self, n): return (b"", ("x", 137))

    monkeypatch.setattr(name_resolver.socket, "socket", _FakeSocket)
    name_resolver._netbios("192.168.1.52", timeout=7.5)
    assert captured["timeout"] == 7.5


# ── Part 2/L1: TimingProfile threaded through resolve() ──────────────────────

def test_resolve_uses_timing_profile_timeouts(monkeypatch):
    from modules import name_resolver
    from modules.adaptive_timing import TimingProfile

    captured = {}

    def fake_rdns(ip, timeout=1.0):
        captured["rdns_timeout"] = timeout
        return ""

    def fake_netbios(ip, timeout=3.0):
        captured["netbios_timeout"] = timeout
        return ""

    def fake_mdns(ip, timeout=1.5):
        captured["mdns_timeout"] = timeout
        return ""

    monkeypatch.setattr(name_resolver, "_rdns", fake_rdns)
    monkeypatch.setattr(name_resolver, "_netbios", fake_netbios)
    monkeypatch.setattr(name_resolver, "_mdns_name", fake_mdns)
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")

    profile = TimingProfile(
        rtt_base_ms=250.0, rdns_timeout=2.0, netbios_timeout=3.0, mdns_timeout=2.5,
        label="Timing: relaxed (gateway RTT 250 ms)",
    )
    name_resolver.resolve(
        "192.168.1.1", use_netbios=True, use_mdns=True, use_dhcp=True,
        timing_profile=profile,
    )
    assert captured["rdns_timeout"] == 2.0
    assert captured["netbios_timeout"] == 3.0
    assert captured["mdns_timeout"] == 2.5


def test_resolve_without_timing_profile_uses_defaults(monkeypatch):
    from modules import name_resolver

    captured = {}

    def fake_rdns(ip, timeout=1.0):
        captured["rdns_timeout"] = timeout
        return ""

    monkeypatch.setattr(name_resolver, "_rdns", fake_rdns)
    monkeypatch.setattr(name_resolver, "_netbios", lambda ip, timeout=3.0: "")
    monkeypatch.setattr(name_resolver, "_mdns_name", lambda ip, timeout=1.5: "")
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", lambda ip: "")

    name_resolver.resolve("192.168.1.1", use_netbios=True, use_mdns=True, use_dhcp=True)
    assert captured["rdns_timeout"] == 1.0


# ── Sprint 2b/A: _rdns retry-once-on-timeout, never on a genuine negative answer ──

def test_rdns_retries_once_on_timeout_and_returns_honest_timing(monkeypatch):
    """Regression: `with ThreadPoolExecutor(...) as ex:` calls shutdown(wait=True) on
    exit even after `.result(timeout=)` already raised TimeoutError, so _rdns silently
    blocked until the real (slow) background call finished instead of returning at the
    stated timeout. That must be fixed for a retry to mean anything, and the retry
    itself must fire on a genuine timeout and return the second attempt's answer.
    """
    import time
    from modules import name_resolver

    calls = []

    def fake_gethostbyaddr(ip):
        calls.append(ip)
        if len(calls) == 1:
            time.sleep(0.6)  # far exceeds the 0.15s timeout below
        return (f"host-{len(calls)}.local", [], [ip])

    monkeypatch.setattr(name_resolver.socket, "gethostbyaddr", fake_gethostbyaddr)

    start = time.monotonic()
    result = name_resolver._rdns("10.0.0.5", timeout=0.15)
    elapsed = time.monotonic() - start

    assert result == "host-2.local", "must return the retried (second) attempt's answer"
    assert len(calls) == 2, "must retry exactly once on a genuine timeout"
    assert elapsed < 0.4, (
        f"_rdns took {elapsed:.2f}s — it must return near the stated timeout, not "
        f"block on shutdown(wait=True) for the abandoned first attempt's real duration"
    )


def test_rdns_does_not_retry_on_genuine_negative_answer(monkeypatch):
    """A real NXDOMAIN (socket.herror) returns fast and must never be retried —
    retrying a negative answer wastes time without changing the outcome."""
    import socket as _socket
    from modules import name_resolver

    calls = []

    def fake_gethostbyaddr(ip):
        calls.append(ip)
        raise _socket.herror("unknown host")

    monkeypatch.setattr(name_resolver.socket, "gethostbyaddr", fake_gethostbyaddr)

    result = name_resolver._rdns("10.0.0.6", timeout=0.5)
    assert result == ""
    assert len(calls) == 1, "a genuine negative answer must not trigger a retry"


def test_rdns_retry_is_bounded_not_infinite(monkeypatch):
    """If the retry also times out, _rdns must give up after exactly one retry —
    never loop indefinitely."""
    import time
    from modules import name_resolver

    calls = []

    def fake_gethostbyaddr(ip):
        calls.append(ip)
        time.sleep(0.3)
        return ("host.local", [], [ip])

    monkeypatch.setattr(name_resolver.socket, "gethostbyaddr", fake_gethostbyaddr)

    result = name_resolver._rdns("10.0.0.7", timeout=0.05)
    assert result == ""
    assert len(calls) == 2, "must attempt exactly twice (original + one retry), never more"


# ── Sprint 2b/B: one shared bounded probe pool for resolve_batch ────────────────
# Regression coverage for "30 outer x 6 inner = up to 180 live threads" — replaced
# with one fixed-size pool shared across every probe of every device in the batch,
# so peak thread load does not scale with device count.

def test_resolve_accepts_shared_executor_without_shutting_it_down():
    """resolve() must accept an externally-owned executor for its probe fan-out
    and never shut it down itself — only the batch caller that created it owns
    its lifecycle."""
    import concurrent.futures
    from modules import name_resolver

    my_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    try:
        result = name_resolver.resolve(
            "127.0.0.1", executor=my_pool,
            use_netbios=False, use_mdns=False, use_snmp=False, use_dhcp=False,
        )
        assert isinstance(result, name_resolver.ResolvedName)

        # The pool must still be usable afterward — resolve() must not have shut it down.
        probe = my_pool.submit(lambda: "still alive")
        assert probe.result(timeout=1.0) == "still alive"
    finally:
        my_pool.shutdown(wait=False)


def test_resolve_batch_caps_peak_concurrent_probes_regardless_of_device_count(monkeypatch):
    """The peak number of concurrently-running probe threads must stay bounded by
    a fixed constant no matter how many devices are in the batch — 60 devices must
    not exert more concurrent thread load than 6 devices would."""
    import threading
    import time
    from modules import name_resolver

    lock = threading.Lock()
    current = [0]
    peak = [0]

    def _track(*_args, **_kwargs):
        with lock:
            current[0] += 1
            peak[0] = max(peak[0], current[0])
        time.sleep(0.02)
        with lock:
            current[0] -= 1
        return ""

    monkeypatch.setattr(name_resolver, "_rdns", _track)
    monkeypatch.setattr(name_resolver, "_netbios", _track)
    monkeypatch.setattr(name_resolver, "_mdns_name", _track)
    monkeypatch.setattr(name_resolver, "_dhcp_lease_name", _track)

    devices = [{"ip": f"192.168.1.{i}", "mac": ""} for i in range(1, 61)]
    name_resolver.resolve_batch(
        devices, use_netbios=True, use_mdns=True, use_snmp=False, use_dhcp=True,
    )

    assert peak[0] <= name_resolver._SHARED_PROBE_POOL_SIZE, (
        f"peak concurrent probe threads ({peak[0]}) exceeded the shared pool cap "
        f"({name_resolver._SHARED_PROBE_POOL_SIZE}) for 60 devices — nested "
        f"per-device pools have reappeared (Part 2/L2b)"
    )
