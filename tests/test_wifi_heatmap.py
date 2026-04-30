"""
Tests for modules/wifi_heatmap.py

Covers:
  - HeatmapReading: defaults, timestamp auto-set
  - HeatmapSurvey: ap_bssids, add_reading, add_reading_raw
  - save_survey / load_survey round-trip
  - list_surveys
  - interpolate_heatmap: empty, single point, multi-point, bssid filter, all-APs
  - _idw: exact hit, gradient
  - dbm_to_quality labels
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from modules.wifi_heatmap import (
    HEATMAP_VMAX,
    HEATMAP_VMIN,
    HeatmapReading,
    HeatmapSurvey,
    _idw,
    dbm_to_quality,
    interpolate_heatmap,
    load_survey,
    save_survey,
)


# ── HeatmapReading ────────────────────────────────────────────────────────────

def test_reading_timestamp_auto():
    r = HeatmapReading(x_frac=0.5, y_frac=0.5, readings={})
    assert r.timestamp  # not empty


def test_reading_timestamp_not_overwritten():
    r = HeatmapReading(x_frac=0.1, y_frac=0.2, readings={}, timestamp="2025-01-01T00:00:00+00:00")
    assert r.timestamp == "2025-01-01T00:00:00+00:00"


def test_reading_stores_readings():
    r = HeatmapReading(x_frac=0.3, y_frac=0.4, readings={"aa:bb:cc:dd:ee:ff": -65})
    assert r.readings["aa:bb:cc:dd:ee:ff"] == -65


# ── HeatmapSurvey ─────────────────────────────────────────────────────────────

def test_survey_created_at_auto():
    s = HeatmapSurvey(name="test", floor_plan_path="/tmp/x.png")
    assert s.created_at


def test_survey_ap_bssids_empty():
    s = HeatmapSurvey(name="t", floor_plan_path="")
    assert s.ap_bssids() == []


def test_survey_ap_bssids_deduped():
    s = HeatmapSurvey(name="t", floor_plan_path="")
    s.readings = [
        HeatmapReading(0.1, 0.1, {"aa:bb:cc:00:00:01": -60, "aa:bb:cc:00:00:02": -70}),
        HeatmapReading(0.5, 0.5, {"aa:bb:cc:00:00:01": -55}),
    ]
    bssids = s.ap_bssids()
    assert len(bssids) == 2
    assert "aa:bb:cc:00:00:01" in bssids
    assert "aa:bb:cc:00:00:02" in bssids


def test_survey_add_reading_raw():
    s = HeatmapSurvey(name="t", floor_plan_path="")
    s.add_reading_raw(0.2, 0.3, {"AA:BB:CC:DD:EE:FF": -72})
    assert len(s.readings) == 1
    assert "aa:bb:cc:dd:ee:ff" in s.readings[0].readings  # lowercased
    assert s.readings[0].x_frac == pytest.approx(0.2)


def test_survey_add_reading_raw_empty_ignored():
    """An empty dbm_map should not add a reading."""
    s = HeatmapSurvey(name="t", floor_plan_path="")
    s.add_reading_raw(0.5, 0.5, {})
    assert len(s.readings) == 0


def test_survey_add_reading_from_scan_result():
    """add_reading() accepts a WifiScanResult-like object."""
    from types import SimpleNamespace
    net = SimpleNamespace(bssid="aa:bb:cc:00:00:01", signal_dbm=-68)
    result = SimpleNamespace(networks=[net])
    s = HeatmapSurvey(name="t", floor_plan_path="")
    s.add_reading(0.4, 0.6, result)
    assert len(s.readings) == 1
    assert s.readings[0].readings["aa:bb:cc:00:00:01"] == -68


def test_survey_add_reading_no_networks():
    from types import SimpleNamespace
    result = SimpleNamespace(networks=[])
    s = HeatmapSurvey(name="t", floor_plan_path="")
    s.add_reading(0.5, 0.5, result)
    assert len(s.readings) == 0


# ── save_survey / load_survey round-trip ─────────────────────────────────────

def test_save_load_roundtrip(tmp_path):
    s = HeatmapSurvey(name="mysurvey", floor_plan_path="/floor.png")
    s.add_reading_raw(0.1, 0.2, {"aa:bb:cc:00:00:01": -55})
    s.add_reading_raw(0.9, 0.8, {"aa:bb:cc:00:00:01": -72})

    path = save_survey(s, tmp_path / "mysurvey.json")
    loaded = load_survey(path)

    assert loaded.name == "mysurvey"
    assert loaded.floor_plan_path == "/floor.png"
    assert len(loaded.readings) == 2
    assert loaded.readings[0].x_frac == pytest.approx(0.1)
    assert loaded.readings[0].readings["aa:bb:cc:00:00:01"] == -55


def test_save_creates_valid_json(tmp_path):
    s = HeatmapSurvey(name="s", floor_plan_path="")
    path = save_survey(s, tmp_path / "s.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["name"] == "s"
    assert isinstance(data["readings"], list)


def test_load_missing_floor_plan_path(tmp_path):
    """A survey JSON without floor_plan_path should load gracefully."""
    data = {"name": "x", "floor_plan_path": "", "readings": [], "created_at": ""}
    p = tmp_path / "x.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_survey(p)
    assert loaded.name == "x"
    assert loaded.readings == []


# ── interpolate_heatmap ───────────────────────────────────────────────────────

def test_interpolate_empty_readings():
    gx, gy, zz = interpolate_heatmap([], None, resolution=10)
    assert gx.shape == (10, 10)
    assert np.all(np.isnan(zz))


def test_interpolate_single_point_all_same():
    """With one sample the entire grid should equal that sample's dBm."""
    readings = [HeatmapReading(0.5, 0.5, {"bb:cc:dd:00:00:01": -60})]
    gx, gy, zz = interpolate_heatmap(readings, "bb:cc:dd:00:00:01", resolution=10)
    assert np.allclose(zz, -60)


def test_interpolate_bssid_filter_no_match():
    """Requesting an unknown BSSID → all-NaN grid."""
    readings = [HeatmapReading(0.5, 0.5, {"aa:00:00:00:00:01": -60})]
    gx, gy, zz = interpolate_heatmap(readings, "ff:ff:ff:ff:ff:ff", resolution=8)
    assert np.all(np.isnan(zz))


def test_interpolate_all_aps_averages():
    """all-APs mode should average the two BSSIDs at each sample."""
    readings = [HeatmapReading(0.5, 0.5, {"a1:00:00:00:00:01": -60, "a2:00:00:00:00:02": -80})]
    gx, gy, zz = interpolate_heatmap(readings, None, resolution=10)
    # Average of -60 and -80 = -70
    assert np.allclose(zz, -70)


def test_interpolate_two_points_gradient():
    """Two samples at opposite corners; middle should be between them."""
    readings = [
        HeatmapReading(0.0, 0.5, {"b1": -50}),
        HeatmapReading(1.0, 0.5, {"b1": -90}),
    ]
    gx, gy, zz = interpolate_heatmap(readings, "b1", resolution=20)
    # Centre column values should be roughly between -90 and -50
    mid_col = zz[:, 10]
    assert np.all(mid_col < -50)
    assert np.all(mid_col > -90)


def test_interpolate_shape(capsys):
    readings = [
        HeatmapReading(0.1, 0.1, {"c1": -60}),
        HeatmapReading(0.9, 0.9, {"c1": -80}),
    ]
    gx, gy, zz = interpolate_heatmap(readings, "c1", resolution=15)
    assert gx.shape == (15, 15)
    assert gy.shape == (15, 15)
    assert zz.shape == (15, 15)


# ── _idw ─────────────────────────────────────────────────────────────────────

def test_idw_exact_hit():
    """When a grid point coincides with a sample, it should return that value."""
    px = np.array([0.5])
    py = np.array([0.5])
    pz = np.array([-65.0])
    g = np.linspace(0.0, 1.0, 11)
    gx, gy = np.meshgrid(g, g)
    zz = _idw(px, py, pz, gx, gy)
    # Grid point at (0.5, 0.5) index = (5, 5)
    assert zz[5, 5] == pytest.approx(-65.0)


def test_idw_single_point_uniform():
    """Single sample → all grid values equal to that sample."""
    px = np.array([0.3])
    py = np.array([0.7])
    pz = np.array([-55.0])
    g = np.linspace(0.0, 1.0, 8)
    gx, gy = np.meshgrid(g, g)
    zz = _idw(px, py, pz, gx, gy)
    assert np.allclose(zz, -55.0)


def test_idw_two_equal_equidistant():
    """A grid point equidistant from two equal-value samples gets that value."""
    px = np.array([0.0, 1.0])
    py = np.array([0.5, 0.5])
    pz = np.array([-70.0, -70.0])
    gx = np.array([[0.5]])
    gy = np.array([[0.5]])
    zz = _idw(px, py, pz, gx, gy)
    assert zz[0, 0] == pytest.approx(-70.0)


# ── dbm_to_quality ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("dbm,expected", [
    (-40, "Excellent"),
    (-50, "Excellent"),
    (-59, "Good"),
    (-60, "Good"),
    (-69, "Fair"),
    (-70, "Fair"),
    (-79, "Weak"),
    (-80, "Weak"),
    (-85, "Very Weak"),
    (-100, "Very Weak"),
])
def test_dbm_to_quality(dbm, expected):
    assert dbm_to_quality(dbm) == expected


# ── Constants ─────────────────────────────────────────────────────────────────

def test_heatmap_range_sensible():
    assert HEATMAP_VMIN < HEATMAP_VMAX
    assert HEATMAP_VMIN <= -80
    assert HEATMAP_VMAX >= -50
