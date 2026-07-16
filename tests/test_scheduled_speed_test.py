"""Tests for modules/scheduled_speed_test.py (Sprint 3)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from modules.speed_tester_backends import SpeedTestResult


def _history_point(download_mbps: float):
    p = MagicMock()
    p.download_mbps = download_mbps
    return p


def test_import():
    from modules.scheduled_speed_test import run_scheduled_speed_test, ScheduledSpeedTestResult
    assert run_scheduled_speed_test is not None
    assert ScheduledSpeedTestResult is not None


def test_run_scheduled_speed_test_persists_and_returns_history():
    from modules.scheduled_speed_test import run_scheduled_speed_test

    store = MagicMock()
    store.query_speed_test_history.return_value = [
        _history_point(740.0), _history_point(735.0), _history_point(742.0), _history_point(745.0),
    ]
    fake_result = SpeedTestResult(
        download_mbps=94.0, upload_mbps=40.0, ping_ms=12.0,
        server_name="Test ISP", server_city="Testville", server_country="US",
        backend="test",
    )

    with patch("modules.scheduled_speed_test.speed_tester.run_test", return_value=fake_result):
        result = run_scheduled_speed_test(store)

    assert result.download_mbps == 94.0
    assert result.prior_downloads == [740.0, 735.0, 742.0, 745.0]
    store.record_speed_test.assert_called_once()
    kwargs = store.record_speed_test.call_args.kwargs
    assert kwargs["download_mbps"] == 94.0
    assert kwargs["upload_mbps"] == 40.0


def _sinr_point(sinr):
    p = MagicMock()
    p.nr5g_sinr = sinr
    return p


def test_run_scheduled_speed_test_returns_modem_sinr_context():
    """V6 Sprint 5.2 — current + prior SINR readings ride along so
    evaluate_baseline_metrics() can distinguish a radio problem from an ISP
    problem."""
    from modules.scheduled_speed_test import run_scheduled_speed_test

    store = MagicMock()
    store.query_speed_test_history.return_value = []
    store.query_modem_signal_log.return_value = [
        _sinr_point(1.0), _sinr_point(18.0), _sinr_point(19.0), _sinr_point(17.5),
    ]
    fake_result = SpeedTestResult(
        download_mbps=94.0, upload_mbps=40.0, ping_ms=12.0,
        server_name="Test ISP", server_city="Testville", server_country="US",
        backend="test",
    )

    with patch("modules.scheduled_speed_test.speed_tester.run_test", return_value=fake_result):
        result = run_scheduled_speed_test(store)

    assert result.current_sinr == 1.0
    assert result.prior_sinr == [18.0, 19.0, 17.5]


def test_run_scheduled_speed_test_handles_no_modem_data():
    """No modem plugin installed → query_modem_signal_log() returns [] →
    current_sinr is None and prior_sinr is empty (no crash)."""
    from modules.scheduled_speed_test import run_scheduled_speed_test

    store = MagicMock()
    store.query_speed_test_history.return_value = []
    store.query_modem_signal_log.return_value = []
    fake_result = SpeedTestResult(
        download_mbps=100.0, upload_mbps=10.0, ping_ms=5.0,
        server_name="", server_city="", server_country="",
        backend="test",
    )
    with patch("modules.scheduled_speed_test.speed_tester.run_test", return_value=fake_result):
        result = run_scheduled_speed_test(store)

    assert result.current_sinr is None
    assert result.prior_sinr == []


def test_run_scheduled_speed_test_forwards_server_id():
    """A resolved server_id (pinned server or location-search result) must reach
    speed_tester.run_test(), so scheduled/background tests benefit from the same
    location correction manual tests do — not silently ignore it (the original bug:
    scheduled tests always called run_test() with no server_id)."""
    from modules.scheduled_speed_test import run_scheduled_speed_test

    store = MagicMock()
    store.query_speed_test_history.return_value = []
    store.query_modem_signal_log.return_value = []
    fake_result = SpeedTestResult(
        download_mbps=94.0, upload_mbps=40.0, ping_ms=12.0,
        server_name="Telia", server_city="Stockholm", server_country="Sweden",
        backend="test",
    )

    with patch(
        "modules.scheduled_speed_test.speed_tester.run_test", return_value=fake_result
    ) as mock_run_test:
        run_scheduled_speed_test(store, server_id="42")

    mock_run_test.assert_called_once_with(server_id="42")


def test_run_scheduled_speed_test_server_id_defaults_to_none():
    """No server_id passed → run_test() still receives None (today's fully-automatic
    behavior) — no regression for callers that don't pass a preference."""
    from modules.scheduled_speed_test import run_scheduled_speed_test

    store = MagicMock()
    store.query_speed_test_history.return_value = []
    store.query_modem_signal_log.return_value = []
    fake_result = SpeedTestResult(
        download_mbps=10.0, upload_mbps=5.0, ping_ms=20.0,
        server_name="", server_city="", server_country="",
        backend="test",
    )

    with patch(
        "modules.scheduled_speed_test.speed_tester.run_test", return_value=fake_result
    ) as mock_run_test:
        run_scheduled_speed_test(store)

    mock_run_test.assert_called_once_with(server_id=None)


def test_prior_downloads_queried_before_persisting():
    """Prior history must not include the just-run test (order matters)."""
    from modules.scheduled_speed_test import run_scheduled_speed_test

    store = MagicMock()
    call_order = []
    store.query_speed_test_history.side_effect = lambda **_: (
        call_order.append("query"), []
    )[1]
    store.record_speed_test.side_effect = lambda **_: call_order.append("record")

    fake_result = SpeedTestResult(
        download_mbps=100.0, upload_mbps=10.0, ping_ms=5.0,
        server_name="", server_city="", server_country="",
        backend="test",
    )
    with patch("modules.scheduled_speed_test.speed_tester.run_test", return_value=fake_result):
        run_scheduled_speed_test(store)

    assert call_order == ["query", "record"]
