"""Tests for modules/speed_drop_detector.py (TDD-first, RULE-TDD1)."""
from modules.speed_drop_detector import evaluate_speed_drop


def test_severe_drop_is_high_severity():
    # 94 vs typical ~740 -> ~87% drop
    prior = [740.0, 735.0, 742.0, 738.0, 745.0]
    v = evaluate_speed_drop(94.0, prior)
    assert v.is_drop is True
    assert v.severity == "High"
    assert v.typical_mbps == 740.0
    assert v.drop_pct > 75.0
    assert "94" in v.headline
    assert "740" in v.headline
    assert len(v.steps) >= 3


def test_moderate_drop_is_warning_severity():
    # ~55% drop
    prior = [200.0, 195.0, 205.0, 198.0]
    v = evaluate_speed_drop(90.0, prior)
    assert v.is_drop is True
    assert v.severity == "Warning"


def test_small_dip_is_not_a_drop():
    prior = [200.0, 195.0, 205.0, 198.0]
    v = evaluate_speed_drop(180.0, prior)  # ~10% dip
    assert v.is_drop is False
    assert v.severity == ""


def test_insufficient_history_is_not_a_drop():
    prior = [200.0, 195.0]  # below min_samples default of 4
    v = evaluate_speed_drop(10.0, prior)
    assert v.is_drop is False


def test_low_typical_speed_is_guarded_from_noise():
    prior = [10.0, 12.0, 9.0, 11.0]  # median < floor_mbps default 25
    v = evaluate_speed_drop(2.0, prior)
    assert v.is_drop is False


def test_zero_current_speed_is_not_a_drop():
    prior = [200.0, 195.0, 205.0, 198.0]
    v = evaluate_speed_drop(0.0, prior)
    assert v.is_drop is False


def test_median_is_robust_to_outlier():
    # one wild outlier shouldn't wreck the typical calc
    prior = [200.0, 205.0, 195.0, 5000.0]
    v = evaluate_speed_drop(90.0, prior)
    assert v.typical_mbps == 202.5  # median of the two middle values
