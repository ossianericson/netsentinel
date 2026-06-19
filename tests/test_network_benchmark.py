"""
Tests for modules/network_benchmark.py

Verifies grading logic, dimension scoring, weighted aggregation,
and graceful handling of missing/partial data.

No network, no file I/O, no GUI required.
"""

import sys
import os
import types
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from modules.network_benchmark import grade, _letter, BenchmarkResult


# ── _letter() ─────────────────────────────────────────────────────────────────

class TestLetterGrade:
    @pytest.mark.parametrize("score,expected", [
        (100, "A"), (90, "A"), (89, "B"), (80, "B"),
        (79, "C"), (65, "C"), (64, "D"), (50, "D"),
        (49, "F"), (0, "F"),
    ])
    def test_boundaries(self, score, expected):
        assert _letter(score) == expected


# ── grade() with no data ──────────────────────────────────────────────────────

class TestGradeNoData:
    def test_returns_benchmark_result(self):
        result = grade()
        assert isinstance(result, BenchmarkResult)

    def test_no_data_grade_na(self):
        result = grade()
        assert result.overall_grade == "N/A"

    def test_no_data_has_verdict(self):
        result = grade()
        assert len(result.overall_verdict) > 0

    def test_no_data_empty_dimensions(self):
        result = grade()
        assert result.dimensions == []


# ── Helpers to build mock data objects ───────────────────────────────────────

def _log_summary(uptime=99.5, avg_rtt=15.0, avg_jitter=3.0, avg_dns=25.0):
    obj = types.SimpleNamespace(
        uptime_pct=uptime,
        avg_rtt_ms=avg_rtt,
        avg_jitter_ms=avg_jitter,
        avg_dns_ms=avg_dns,
        outages=[],
    )
    return obj


def _diag_result(download_mbps=100.0):
    return types.SimpleNamespace(
        download_mbps=download_mbps,
        ping_results=[],
        dns_results=[],
        trace_hops=[],
    )


def _m1_result(high_risk_count=0):
    return {"high_risk_count": high_risk_count, "devices": []}


def _m2_result(rogue_bpdus=0):
    bpdus = []
    for _ in range(rogue_bpdus):
        bpdus.append(types.SimpleNamespace(is_rogue=True))
    return {"bpdus": bpdus}


def _m3_result(level="CLEAN", bcast_pps=10.0):
    return types.SimpleNamespace(storm_level=level, bcast_per_sec=bcast_pps)


# ── Perfect network → grade A ─────────────────────────────────────────────────

class TestPerfectNetwork:
    def setup_method(self):
        self.result = grade(
            log_summary=_log_summary(uptime=99.9, avg_rtt=10.0, avg_jitter=2.0, avg_dns=20.0),
            diag_result=_diag_result(download_mbps=200.0),
            m1_result=_m1_result(high_risk_count=0),
            m2_result=_m2_result(rogue_bpdus=0),
            m3_result=_m3_result(level="CLEAN", bcast_pps=5.0),
        )

    def test_grade_is_a(self):
        assert self.result.overall_grade == "A"

    def test_score_above_90(self):
        assert self.result.overall_score >= 90

    def test_has_dimensions(self):
        assert len(self.result.dimensions) > 0

    def test_all_dimensions_are_a_or_b(self):
        for d in self.result.dimensions:
            assert d.grade in ("A", "B"), f"{d.name} got {d.grade}"


# ── Degraded network → lower grades ──────────────────────────────────────────

class TestDegradedNetwork:
    def test_high_packet_loss_degrades_grade(self):
        result = grade(log_summary=_log_summary(uptime=80.0))
        uptime_dim = next(d for d in result.dimensions if d.name == "Connection Uptime")
        assert uptime_dim.grade in ("D", "F")

    def test_high_latency_degrades_grade(self):
        result = grade(log_summary=_log_summary(avg_rtt=250.0))
        latency_dim = next(d for d in result.dimensions if d.name == "Average Latency")
        assert latency_dim.grade in ("D", "F")

    def test_rogue_device_degrades_grade(self):
        result = grade(m1_result=_m1_result(high_risk_count=2))
        safety_dim = next(d for d in result.dimensions if d.name == "Network Device Safety")
        assert safety_dim.grade in ("D", "F")

    def test_rogue_bpdu_gets_low_score(self):
        result = grade(m2_result=_m2_result(rogue_bpdus=1))
        stp_dim = next(d for d in result.dimensions if "STP" in d.name)
        assert stp_dim.score <= 25

    def test_broadcast_storm_degrades_grade(self):
        result = grade(m3_result=_m3_result(level="STORM", bcast_pps=5000.0))
        storm_dim = next(d for d in result.dimensions if "Storm" in d.name)
        assert storm_dim.grade in ("D", "F")

    def test_slow_dns_degrades_grade(self):
        result = grade(log_summary=_log_summary(avg_dns=300.0))
        dns_dim = next(d for d in result.dimensions if "DNS" in d.name)
        assert dns_dim.grade in ("D", "F")

    def test_slow_download_degrades_grade(self):
        result = grade(diag_result=_diag_result(download_mbps=2.0))
        dl_dim = next(d for d in result.dimensions if "Download" in d.name)
        assert dl_dim.grade in ("D", "F")


# ── DimensionResult fields ────────────────────────────────────────────────────

class TestDimensionFields:
    def test_each_dimension_has_all_fields(self):
        result = grade(
            log_summary=_log_summary(),
            diag_result=_diag_result(),
            m1_result=_m1_result(),
        )
        for d in result.dimensions:
            assert d.name
            assert d.grade in ("A", "B", "C", "D", "F")
            assert 0 <= d.score <= 100
            assert d.color.startswith("#")
            assert d.value_label
            assert d.ideal_label
            assert d.verdict

    def test_tip_empty_for_good_grades(self):
        result = grade(
            log_summary=_log_summary(uptime=99.9, avg_rtt=10.0, avg_jitter=2.0, avg_dns=20.0),
            diag_result=_diag_result(download_mbps=200.0),
        )
        for d in result.dimensions:
            if d.grade in ("A", "B"):
                assert d.tip == "", f"{d.name} grade {d.grade} should have empty tip"


# ── Partial data (only some modules run) ─────────────────────────────────────

class TestPartialData:
    def test_only_log_summary(self):
        result = grade(log_summary=_log_summary())
        assert len(result.dimensions) >= 3  # uptime, latency, jitter, dns
        assert result.overall_grade != "N/A"

    def test_only_m1_result(self):
        result = grade(m1_result=_m1_result(high_risk_count=0))
        assert len(result.dimensions) == 1
        assert result.dimensions[0].name == "Network Device Safety"

    def test_overall_score_is_float(self):
        result = grade(log_summary=_log_summary())
        assert isinstance(result.overall_score, float)
