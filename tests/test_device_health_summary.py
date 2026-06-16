"""Tests for modules/device_health_summary.py (S5-3)."""

from modules.device_health_summary import (
    STATE_OFFLINE,
    STATE_ONLINE,
    STATE_SLOW,
    STATE_UNUSUAL,
    classify_device,
    summarize_devices,
    summary_counts,
    summary_line,
)


def _dev(**kwargs):
    base = {"mac": "aa:bb:cc:dd:ee:ff", "ip": "192.168.1.10",
            "display_state": "", "risk_level": "CLEAN"}
    base.update(kwargs)
    return base


def test_live_clean_device_is_online():
    result = classify_device(_dev())
    assert result.state == STATE_ONLINE


def test_cached_device_is_offline():
    result = classify_device(_dev(display_state="cached"))
    assert result.state == STATE_OFFLINE


def test_stale_device_is_offline():
    result = classify_device(_dev(display_state="stale"))
    assert result.state == STATE_OFFLINE


def test_warning_risk_is_slow():
    result = classify_device(_dev(risk_level="WARNING"))
    assert result.state == STATE_SLOW


def test_high_risk_is_unusual():
    result = classify_device(_dev(risk_level="HIGH"))
    assert result.state == STATE_UNUSUAL


def test_storm_risk_is_unusual():
    result = classify_device(_dev(risk_level="STORM"))
    assert result.state == STATE_UNUSUAL


def test_unusual_takes_priority_over_offline():
    result = classify_device(_dev(display_state="cached", risk_level="HIGH"))
    assert result.state == STATE_UNUSUAL


def test_recent_alert_marks_unusual():
    result = classify_device(_dev(), alerted_hosts={"192.168.1.10"})
    assert result.state == STATE_UNUSUAL


def test_works_with_object_attributes_not_just_dict():
    class _Obj:
        mac = "aa:bb:cc:dd:ee:ff"
        ip = "192.168.1.10"
        display_state = ""
        risk_level = "CLEAN"

    result = classify_device(_Obj())
    assert result.state == STATE_ONLINE


def test_summary_counts_tally_each_state():
    devices = [_dev(risk_level="CLEAN"), _dev(risk_level="HIGH"), _dev(display_state="stale")]
    results = summarize_devices(devices)
    counts = summary_counts(results)
    assert counts[STATE_ONLINE] == 1
    assert counts[STATE_UNUSUAL] == 1
    assert counts[STATE_OFFLINE] == 1


def test_summary_line_all_healthy():
    devices = [_dev(), _dev()]
    results = summarize_devices(devices)
    assert summary_line(results) == "All 2 devices look healthy"


def test_summary_line_needs_attention():
    devices = [_dev(risk_level="HIGH"), _dev()]
    results = summarize_devices(devices)
    assert summary_line(results) == "1 of your 2 devices need attention"


def test_summary_line_empty():
    assert "run a scan" in summary_line([]).lower()


def test_summarize_devices_uses_recent_alerts_severity_filter():
    devices = [_dev(ip="10.0.0.5")]
    alerts = [{"host": "10.0.0.5", "severity": "Info"}]
    results = summarize_devices(devices, alerts)
    assert results[0].state == STATE_ONLINE
