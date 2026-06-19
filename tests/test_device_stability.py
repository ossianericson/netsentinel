"""
Tests for modules/device_stability.py — stability scoring and role inference.
"""
from unittest.mock import MagicMock

from modules.device_stability import (
    compute_ip_stability,
    infer_role,
    is_static_candidate,
    update_stability_for_device,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_store(ip_history_rows):
    """Return a minimal mock MetricStore with a given device_ip_history dataset."""
    store = MagicMock()
    store._execute_read.return_value = ip_history_rows
    store._execute_write.return_value = None
    store.get_known_devices.return_value = {}
    return store


# ── compute_ip_stability ──────────────────────────────────────────────────────

def test_stability_unknown_mac_returns_zero():
    store = _make_store([])
    assert compute_ip_stability("aa:bb:cc:dd:ee:ff", store) == 0.0


def test_stability_single_ip_returns_one():
    store = _make_store([("192.168.1.1", 10)])
    assert compute_ip_stability("aa:bb:cc:dd:ee:ff", store) == 1.0


def test_stability_two_ips_dominant():
    # 8 at .1, 2 at .50 → stability = 8/10 = 0.8
    store = _make_store([("192.168.1.1", 8), ("192.168.1.50", 2)])
    result = compute_ip_stability("aa:bb:cc:dd:ee:ff", store)
    assert abs(result - 0.8) < 1e-9


def test_stability_equal_ips():
    store = _make_store([("10.0.0.1", 5), ("10.0.0.2", 5)])
    result = compute_ip_stability("aa:bb:cc:dd:ee:ff", store)
    assert abs(result - 0.5) < 1e-9


def test_stability_zero_seen_count():
    store = _make_store([("192.168.1.1", 0)])
    assert compute_ip_stability("aa:bb:cc:dd:ee:ff", store) == 0.0


# ── infer_role ────────────────────────────────────────────────────────────────

def test_role_gateway_last_octet_1():
    assert infer_role("192.168.1.1", "Unknown", None, 1, 0.5) == "gateway"


def test_role_gateway_last_octet_254():
    assert infer_role("10.0.0.254", "router", None, 1, 0.5) == "gateway"


def test_role_infrastructure_by_type():
    assert infer_role("192.168.1.5", "router", None, 1, 0.3) == "infrastructure"
    assert infer_role("192.168.1.6", "Access Point", None, 1, 0.3) == "infrastructure"
    assert infer_role("192.168.1.7", "switch", None, 1, 0.3) == "infrastructure"


def test_role_server_requires_threshold():
    # Below threshold — should not infer server
    assert infer_role("192.168.1.10", "server", None, 3, 0.8) != "server"
    # At threshold
    assert infer_role("192.168.1.10", "server", None, 5, 0.9) == "server"


def test_role_always_on_unknown_device():
    # 10+ scans, 90%+ stability, unknown type → infrastructure
    result = infer_role("192.168.1.20", "Unknown Device", None, 10, 0.92)
    assert result == "infrastructure"


def test_role_workstation():
    assert infer_role("192.168.1.50", "laptop", None, 2, 0.5) == "workstation"
    assert infer_role("192.168.1.51", "Phone", None, 2, 0.5) == "workstation"


def test_role_iot():
    assert infer_role("192.168.1.100", "IoT", None, 2, 0.5) == "iot"
    assert infer_role("192.168.1.101", "IP Camera", None, 2, 0.5) == "iot"


def test_role_custom_name_suppresses_inference():
    # Even .1 IP should not get gateway role when user has set a custom name
    assert infer_role("192.168.1.1", "router", "My Router", 20, 1.0) is None


def test_role_none_for_unknown():
    assert infer_role("192.168.1.200", "Unknown Device", None, 1, 0.5) is None


# ── is_static_candidate ───────────────────────────────────────────────────────

def test_static_candidate_pinned_always_true():
    assert is_static_candidate(0.0, 0, None, is_pinned=True) is True


def test_static_candidate_gateway_role():
    assert is_static_candidate(0.5, 1, "gateway") is True


def test_static_candidate_high_stability():
    assert is_static_candidate(0.9, 5, None) is True


def test_static_candidate_low_stability_not_static():
    assert is_static_candidate(0.5, 2, None) is False


def test_static_candidate_enough_scans_but_low_stability():
    assert is_static_candidate(0.6, 10, None) is False


# ── update_stability_for_device ───────────────────────────────────────────────

def test_update_writes_to_store():
    store = MagicMock()
    # ip_history: 8 at .1, 2 at .50 (total 10)
    store._execute_read.side_effect = [
        [("192.168.1.1", 8), ("192.168.1.50", 2)],  # compute_ip_stability
        [(10,)],                                       # SUM(seen_count)
    ]
    store._execute_write.return_value = None

    update_stability_for_device(
        mac="aa:bb:cc:dd:ee:ff",
        ip="192.168.1.1",
        device_type="router",
        custom_name=None,
        store=store,
    )

    store._execute_write.assert_called_once()
    call_args = store._execute_write.call_args
    sql, params = call_args[0]
    assert "scan_count" in sql
    assert "ip_stability" in sql
    # scan_count = 10, ip_stability = 0.8, role = "infrastructure" (router type)
    assert params[0] == 10
    assert abs(params[1] - 0.8) < 1e-9


def test_update_preserves_role_when_none_inferred():
    """When role inference returns None, inferred_role column must NOT be updated."""
    store = MagicMock()
    store._execute_read.side_effect = [
        [("192.168.1.200", 1)],  # single observation
        [(1,)],
    ]
    store._execute_write.return_value = None

    update_stability_for_device(
        mac="aa:bb:cc:dd:ee:ff",
        ip="192.168.1.200",
        device_type="Unknown Device",
        custom_name=None,
        store=store,
    )

    call_args = store._execute_write.call_args
    sql, _params = call_args[0]
    # The UPDATE without role inference should NOT touch inferred_role
    assert "inferred_role" not in sql
