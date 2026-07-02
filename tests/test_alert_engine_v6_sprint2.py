"""
Tests for the V6 Sprint 2 alert rule types — RTT_ANOMALY, IOT_BEHAVIOR,
TREND_FORECAST — added to modules/alert_engine_checks2.py (_AlertChecksMixin2).

See BACKLOG-V6.md Sprint 2 for the acceptance criteria these encode.
"""
from modules.alert_baseline import Baseline, BaselineMetric
from modules.alert_engine import AlertEngine, AlertRule


class _StubLearner:
    """Minimal stand-in for BaselineLearner — returns a fixed Baseline per host."""

    def __init__(self, baselines: dict):
        self._baselines = baselines

    def get_host_baseline(self, host):
        return self._baselines.get(host)


def _mature_baseline(mean=20.0, stddev=5.0, sample_count=40, days_covered=8.0):
    return Baseline(
        host="192.168.1.1",
        rtt_ms=BaselineMetric(mean=mean, stddev=stddev, sample_count=sample_count, days_covered=days_covered),
    )


# ── RTT_ANOMALY ──────────────────────────────────────────────────────────────

def test_rtt_anomaly_fires_above_baseline_threshold():
    engine = AlertEngine(rules=[
        AlertRule(name="rtt-anom", rule_type="RTT_ANOMALY", sigma=2.0, cooldown_s=0)
    ])
    learner = _StubLearner({"192.168.1.1": _mature_baseline(mean=20.0, stddev=5.0)})
    # mean+2sigma = 30; 45 is well above
    fired = engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 45.0}, learner)
    assert len(fired) == 1
    assert fired[0].rule_type == "RTT_ANOMALY"
    assert fired[0].host == "192.168.1.1"
    assert fired[0].cta_page == "DNS & Stability"


def test_rtt_anomaly_no_fire_below_threshold():
    engine = AlertEngine(rules=[
        AlertRule(name="rtt-anom", rule_type="RTT_ANOMALY", sigma=2.0, cooldown_s=0)
    ])
    learner = _StubLearner({"192.168.1.1": _mature_baseline(mean=20.0, stddev=5.0)})
    fired = engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 22.0}, learner)
    assert fired == []


def test_rtt_anomaly_gated_on_immature_baseline():
    """A baseline with < 30 samples / < 7 days must not fire — kills false
    positives during the learning period (Sprint 2 acceptance criterion)."""
    engine = AlertEngine(rules=[
        AlertRule(name="rtt-anom", rule_type="RTT_ANOMALY", sigma=2.0, cooldown_s=0)
    ])
    immature = Baseline(
        host="192.168.1.1",
        rtt_ms=BaselineMetric(mean=20.0, stddev=5.0, sample_count=5, days_covered=1.0),
    )
    learner = _StubLearner({"192.168.1.1": immature})
    fired = engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 999.0}, learner)
    assert fired == []


def test_rtt_anomaly_no_fire_when_no_baseline():
    engine = AlertEngine(rules=[
        AlertRule(name="rtt-anom", rule_type="RTT_ANOMALY", sigma=2.0, cooldown_s=0)
    ])
    learner = _StubLearner({})
    fired = engine.evaluate_rtt_anomaly_checks({"10.0.0.9": 500.0}, learner)
    assert fired == []


def test_rtt_anomaly_resolution_when_back_to_normal():
    engine = AlertEngine(rules=[
        AlertRule(name="rtt-anom", rule_type="RTT_ANOMALY", sigma=2.0, cooldown_s=0)
    ])
    learner = _StubLearner({"192.168.1.1": _mature_baseline(mean=20.0, stddev=5.0)})
    engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 45.0}, learner)
    fired = engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 21.0}, learner)
    assert len(fired) == 1
    assert fired[0].is_resolution is True
    assert fired[0].severity == "HEALTHY"


def test_rtt_anomaly_disabled_rule_does_not_fire():
    engine = AlertEngine(rules=[
        AlertRule(name="rtt-anom", rule_type="RTT_ANOMALY", sigma=2.0, cooldown_s=0, enabled=False)
    ])
    learner = _StubLearner({"192.168.1.1": _mature_baseline(mean=20.0, stddev=5.0)})
    fired = engine.evaluate_rtt_anomaly_checks({"192.168.1.1": 999.0}, learner)
    assert fired == []


# ── IOT_BEHAVIOR ─────────────────────────────────────────────────────────────

class _StubIoTAlert:
    def __init__(self, mac, ip, device_label, alert_type, severity, detail):
        self.mac = mac
        self.ip = ip
        self.device_label = device_label
        self.alert_type = alert_type
        self.severity = severity
        self.detail = detail


def test_iot_behavior_fires_for_critical_signal():
    engine = AlertEngine(rules=[
        AlertRule(name="iot", rule_type="IOT_BEHAVIOR", cooldown_s=0)
    ])
    alert = _StubIoTAlert(
        mac="aa:bb:cc:00:00:01", ip="192.168.1.50", device_label="Camera [192.168.1.50]",
        alert_type="METADATA_PROBE", severity="CRITICAL",
        detail="Device contacted cloud-metadata endpoint 169.254.169.254.",
    )
    fired = engine.evaluate_iot_behavior_checks([alert])
    assert len(fired) == 1
    assert fired[0].rule_type == "IOT_BEHAVIOR"
    assert fired[0].host == "192.168.1.50"
    assert fired[0].severity == "CRITICAL"
    assert fired[0].cta_page == "IoT Behaviour"


def test_iot_behavior_severity_maps_medium_to_warning():
    engine = AlertEngine(rules=[
        AlertRule(name="iot", rule_type="IOT_BEHAVIOR", cooldown_s=0)
    ])
    alert = _StubIoTAlert(
        mac="aa:bb:cc:00:00:02", ip="192.168.1.51", device_label="Thermostat [192.168.1.51]",
        alert_type="NEW_DEST", severity="MEDIUM",
        detail="Device contacted new IP.",
    )
    fired = engine.evaluate_iot_behavior_checks([alert])
    assert len(fired) == 1
    assert fired[0].severity == "WARNING"


def test_iot_behavior_no_fire_when_empty():
    engine = AlertEngine(rules=[
        AlertRule(name="iot", rule_type="IOT_BEHAVIOR", cooldown_s=0)
    ])
    assert engine.evaluate_iot_behavior_checks([]) == []


def test_iot_behavior_disabled_rule_does_not_fire():
    engine = AlertEngine(rules=[
        AlertRule(name="iot", rule_type="IOT_BEHAVIOR", cooldown_s=0, enabled=False)
    ])
    alert = _StubIoTAlert(
        mac="aa:bb:cc:00:00:01", ip="192.168.1.50", device_label="Camera",
        alert_type="SYN_SCAN", severity="HIGH", detail="Port scan detected.",
    )
    assert engine.evaluate_iot_behavior_checks([alert]) == []


# ── TREND_FORECAST ───────────────────────────────────────────────────────────

class _StubTrendResult:
    def __init__(self, host, metric, current_value, threshold, eta_hours, severity, summary):
        self.host = host
        self.metric = metric
        self.current_value = current_value
        self.threshold = threshold
        self.eta_hours = eta_hours
        self.severity = severity
        self.summary = summary


class _StubTrendReport:
    def __init__(self, results):
        self.results = results


def test_trend_forecast_fires_for_early_warning():
    engine = AlertEngine(rules=[
        AlertRule(name="trend", rule_type="TREND_FORECAST", cooldown_s=0)
    ])
    report = _StubTrendReport([
        _StubTrendResult(
            host="192.168.1.1", metric="rtt_ms", current_value=80.0, threshold=100.0,
            eta_hours=3.0, severity="CRITICAL",
            summary="192.168.1.1 — RTT rising at 80.0ms; projected to reach 100ms in ~3.0 h",
        ),
    ])
    fired = engine.evaluate_trend_checks(report)
    assert len(fired) == 1
    assert fired[0].rule_type == "TREND_FORECAST"
    assert fired[0].host == "192.168.1.1"
    assert fired[0].cta_page == "Trend Forecasts"


def test_trend_forecast_skips_already_crossed_values():
    """Already-crossed thresholds are RTT_THRESHOLD/LOSS_THRESHOLD's job —
    TREND_FORECAST is early-warning only, to avoid duplicate alerts."""
    engine = AlertEngine(rules=[
        AlertRule(name="trend", rule_type="TREND_FORECAST", cooldown_s=0)
    ])
    report = _StubTrendReport([
        _StubTrendResult(
            host="192.168.1.1", metric="rtt_ms", current_value=150.0, threshold=100.0,
            eta_hours=None, severity="CRITICAL",
            summary="192.168.1.1 — RTT is 150.0ms, already above threshold (100ms)",
        ),
    ])
    fired = engine.evaluate_trend_checks(report)
    assert fired == []


def test_trend_forecast_skips_clean_results():
    engine = AlertEngine(rules=[
        AlertRule(name="trend", rule_type="TREND_FORECAST", cooldown_s=0)
    ])
    report = _StubTrendReport([
        _StubTrendResult(
            host="192.168.1.1", metric="rtt_ms", current_value=20.0, threshold=100.0,
            eta_hours=None, severity="CLEAN",
            summary="192.168.1.1 — RTT stable at 20.0ms",
        ),
    ])
    assert engine.evaluate_trend_checks(report) == []


def test_trend_forecast_no_fire_when_empty():
    engine = AlertEngine(rules=[
        AlertRule(name="trend", rule_type="TREND_FORECAST", cooldown_s=0)
    ])
    assert engine.evaluate_trend_checks(_StubTrendReport([])) == []


def test_trend_forecast_disabled_rule_does_not_fire():
    engine = AlertEngine(rules=[
        AlertRule(name="trend", rule_type="TREND_FORECAST", cooldown_s=0, enabled=False)
    ])
    report = _StubTrendReport([
        _StubTrendResult(
            host="192.168.1.1", metric="rtt_ms", current_value=80.0, threshold=100.0,
            eta_hours=3.0, severity="CRITICAL", summary="rising",
        ),
    ])
    assert engine.evaluate_trend_checks(report) == []
