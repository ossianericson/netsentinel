"""Tests for modules/isp_vs_router_test.py"""
from __future__ import annotations

from unittest.mock import patch

from modules.isp_vs_router_test import (
    HopResult,
    IspVsRouterResult,
    _build_verdict,
    _detect_gateway,
    run_isp_vs_router_test,
)


# ── Unit tests for _build_verdict ─────────────────────────────────────────────

def _hop(key: str, reachable: bool, rtt: float | None = 1.0) -> HopResult:
    return HopResult(key=key, label=key, ip="1.2.3.4", reachable=reachable, rtt_ms=rtt)


def test_build_verdict_local_fault():
    hops = [
        _hop("router", False),
        _hop("google_dns", False),
        _hop("cloudflare", False),
        _hop("opendns", False),
    ]
    cat, verdict, plain = _build_verdict(hops)
    assert cat == "local"
    assert "router" in verdict.lower() or "local" in verdict.lower()
    assert "router" in plain.lower()


def test_build_verdict_isp_fault_via_isp_dns():
    hops = [
        _hop("router", True),
        _hop("isp_dns", False),
        _hop("google_dns", False),
        _hop("cloudflare", False),
        _hop("opendns", False),
    ]
    cat, verdict, plain = _build_verdict(hops)
    assert cat == "isp"
    assert "isp" in plain.lower() or "wan" in plain.lower() or "modem" in plain.lower()


def test_build_verdict_all_ok():
    hops = [
        _hop("router", True, 2.0),
        _hop("isp_dns", True, 10.0),
        _hop("google_dns", True, 15.0),
        _hop("cloudflare", True, 16.0),
        _hop("opendns", True, 18.0),
    ]
    cat, verdict, plain = _build_verdict(hops)
    assert cat == "all_ok"
    assert "healthy" in plain.lower() or "responding" in plain.lower()


def test_build_verdict_returns_tuple_of_three():
    hops = [_hop("router", True)]
    result = _build_verdict(hops)
    assert isinstance(result, tuple) and len(result) == 3


def test_build_verdict_partial_ext():
    hops = [
        _hop("router", True),
        _hop("google_dns", True),
        _hop("cloudflare", False),
        _hop("opendns", False),
    ]
    cat, verdict, plain = _build_verdict(hops)
    assert cat in ("external", "all_ok", "unknown")


# ── Integration: run_isp_vs_router_test ──────────────────────────────────────

def _fake_check_hop(key, label, ip):
    return HopResult(key=key, label=label, ip=ip, reachable=True, rtt_ms=5.0)


@patch("modules.isp_vs_router_test._check_hop", side_effect=_fake_check_hop)
def test_run_returns_result_object(mock_check):
    result = run_isp_vs_router_test(gateway_ip="192.168.1.1")
    assert isinstance(result, IspVsRouterResult)
    assert result.category in ("local", "isp", "external", "all_ok", "unknown")
    assert isinstance(result.hops, list)
    assert len(result.hops) >= 1
    assert result.elapsed_s >= 0


@patch("modules.isp_vs_router_test._check_hop", side_effect=_fake_check_hop)
def test_run_calls_progress_callback(mock_check):
    calls = []
    run_isp_vs_router_test(gateway_ip="10.0.0.1", progress_cb=calls.append)
    assert len(calls) >= 1
    assert all(isinstance(c, str) for c in calls)


@patch("modules.isp_vs_router_test._check_hop", side_effect=_fake_check_hop)
def test_run_includes_isp_dns_hop_when_provided(mock_check):
    result = run_isp_vs_router_test(gateway_ip="10.0.0.1", isp_dns_ip="8.8.4.4")
    keys = [h.key for h in result.hops]
    assert "isp_dns" in keys


@patch("modules.isp_vs_router_test._check_hop", side_effect=_fake_check_hop)
def test_run_skips_isp_dns_when_not_provided(mock_check):
    result = run_isp_vs_router_test(gateway_ip="10.0.0.1")
    keys = [h.key for h in result.hops]
    assert "isp_dns" not in keys


# ── _detect_gateway ───────────────────────────────────────────────────────────

def test_detect_gateway_returns_none_or_ip():
    result = _detect_gateway()
    assert result is None or (isinstance(result, str) and "." in result)
