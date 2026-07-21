"""Tests for modules/adaptive_timing.py — gateway-RTT-derived timeout profile (Part 2/L1)."""

from modules.adaptive_timing import TimingProfile, derive_profile, measure_gateway_rtt


# ── derive_profile ──────────────────────────────────────────────────────────────

def test_derive_profile_home_rtt_matches_original_constants():
    """On a home LAN (~1ms RTT) every floor wins — byte-identical to pre-Sprint-2 behaviour."""
    profile = derive_profile(1.0)
    assert profile.rdns_timeout == 1.0
    assert profile.netbios_timeout == 3.0
    assert profile.mdns_timeout == 1.5
    assert profile.label.startswith("Timing: normal")


def test_derive_profile_returns_timing_profile_instance():
    assert isinstance(derive_profile(1.0), TimingProfile)


def test_derive_profile_scales_up_for_vpn_rtt():
    profile = derive_profile(250.0)
    assert profile.rdns_timeout > 1.0
    assert profile.mdns_timeout > 1.5
    assert profile.label.startswith("Timing: relaxed")


def test_derive_profile_monotonic_with_rtt():
    p_low = derive_profile(50.0)
    p_high = derive_profile(400.0)
    assert p_high.rdns_timeout >= p_low.rdns_timeout
    assert p_high.netbios_timeout >= p_low.netbios_timeout
    assert p_high.mdns_timeout >= p_low.mdns_timeout


def test_derive_profile_never_below_floor():
    """Even a tiny/zero RTT must never produce a timeout below today's constants."""
    profile = derive_profile(0.0)
    assert profile.rdns_timeout >= 1.0
    assert profile.netbios_timeout >= 3.0
    assert profile.mdns_timeout >= 1.5


def test_derive_profile_capped_at_ceiling_for_extreme_rtt():
    """An extreme/broken RTT measurement must not stall a single host indefinitely."""
    profile = derive_profile(100_000.0)
    assert profile.rdns_timeout <= 5.0
    assert profile.netbios_timeout <= 8.0
    assert profile.mdns_timeout <= 5.0


def test_derive_profile_stores_rtt_base():
    profile = derive_profile(42.0)
    assert profile.rtt_base_ms == 42.0


# ── measure_gateway_rtt ──────────────────────────────────────────────────────────

def test_measure_gateway_rtt_returns_median_of_successful_samples():
    samples = iter([10.0, 30.0, 20.0])
    rtt = measure_gateway_rtt("192.168.1.1", samples=3, ping_fn=lambda ip, timeout=1.0: next(samples))
    assert rtt == 20.0


def test_measure_gateway_rtt_falls_back_to_home_baseline_when_all_fail():
    rtt = measure_gateway_rtt("192.168.1.1", samples=3, ping_fn=lambda ip, timeout=1.0: -1.0)
    assert rtt == 1.0


def test_measure_gateway_rtt_falls_back_when_gateway_unknown():
    calls = []

    def _fake_ping(ip, timeout=1.0):
        calls.append(ip)
        return 5.0

    rtt = measure_gateway_rtt(None, samples=3, ping_fn=_fake_ping)
    assert rtt == 1.0
    assert calls == []  # no ping attempted when there's no gateway to probe


def test_measure_gateway_rtt_ignores_failed_samples_among_successes():
    samples = iter([-1.0, 40.0, 60.0])
    rtt = measure_gateway_rtt("10.0.0.1", samples=3, ping_fn=lambda ip, timeout=1.0: next(samples))
    assert rtt == 50.0  # median of the two successful samples (40, 60)
