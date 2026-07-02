"""Tests for modules/root_cause_types.py (data types shared by the
Root Cause Correlator family, extracted to break an import cycle)."""

from modules.root_cause_types import (
    CRITICAL, HIGH, MEDIUM, LOW, INFO,
    CorrelatedFinding, CorrelationResult,
)


def test_import():
    assert CorrelatedFinding is not None
    assert CorrelationResult is not None


def test_correlation_result_defaults():
    result = CorrelationResult()
    assert result.findings == []
    assert result.global_severity == INFO
    assert result.metrics == {}
    assert result.finding_count == 0


def test_correlation_result_finding_count():
    finding = CorrelatedFinding(
        source="Test", category="Test Category", severity=HIGH,
        headline="Test headline", detail="", remediation="Do this.",
    )
    result = CorrelationResult(findings=[finding], global_severity=HIGH)
    assert result.finding_count == 1


def test_severity_constants():
    assert {CRITICAL, HIGH, MEDIUM, LOW, INFO} == {
        "CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO",
    }
