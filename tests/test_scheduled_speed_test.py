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
