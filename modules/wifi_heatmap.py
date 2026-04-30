"""
WiFi Signal Strength Heatmap — data model, persistence, and interpolation.

Workflow
────────
  1. User imports a floor-plan image.
  2. User walks around and clicks spots on the image.
  3. Each click triggers a WiFi scan; the (x_frac, y_frac, {bssid: dbm})
     reading is stored in a HeatmapSurvey.
  4. `interpolate_heatmap()` uses IDW (Inverse Distance Weighting) to
     produce a smooth grid suitable for matplotlib pcolormesh/imshow.

Persistence
───────────
  Surveys are saved as JSON under get_app_data_dir() / "heatmap_surveys/".
  No scipy dependency — pure numpy IDW interpolation.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from modules.utils import get_app_data_dir


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class HeatmapReading:
    """One sample point: a position on the floor plan + RSSI readings."""
    x_frac: float                    # 0.0 – 1.0  (fraction of image width)
    y_frac: float                    # 0.0 – 1.0  (fraction of image height)
    readings: Dict[str, int]         # {bssid_lower: signal_dbm}
    timestamp: str = ""              # ISO-8601

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(tz=timezone.utc).isoformat()


@dataclass
class HeatmapSurvey:
    """A named survey: one floor plan + a list of signal samples."""
    name: str
    floor_plan_path: str             # absolute path to PNG/JPG
    readings: List[HeatmapReading] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(tz=timezone.utc).isoformat()

    def ap_bssids(self) -> List[str]:
        """Sorted list of all BSSIDs seen across all readings."""
        seen: set[str] = set()
        for r in self.readings:
            seen.update(r.readings.keys())
        return sorted(seen)

    def add_reading(self, x_frac: float, y_frac: float, scan_result) -> None:
        """Append a reading from a WifiScanResult (or any list of NetworkInfo)."""
        networks = getattr(scan_result, "networks", [])
        dbm_map: Dict[str, int] = {}
        for net in networks:
            if net.bssid and net.signal_dbm is not None:
                dbm_map[net.bssid.lower()] = net.signal_dbm
        if dbm_map:
            self.readings.append(HeatmapReading(x_frac=x_frac, y_frac=y_frac,
                                                readings=dbm_map))

    def add_reading_raw(self, x_frac: float, y_frac: float,
                        dbm_map: Dict[str, int]) -> None:
        """Append a reading from a raw {bssid: dbm} dict."""
        if dbm_map:
            self.readings.append(HeatmapReading(x_frac=x_frac, y_frac=y_frac,
                                                readings={k.lower(): v
                                                          for k, v in dbm_map.items()}))


# ── Persistence ───────────────────────────────────────────────────────────────

def surveys_dir() -> Path:
    d = get_app_data_dir() / "heatmap_surveys"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_survey(survey: HeatmapSurvey, path: Optional[Path] = None) -> Path:
    """Serialise survey to JSON.  Returns the saved path."""
    if path is None:
        safe = re.sub(r'[^A-Za-z0-9_-]', '_', survey.name) or "survey"
        path = surveys_dir() / f"{safe}.json"
    data = asdict(survey)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def load_survey(path: Path) -> HeatmapSurvey:
    """Deserialise a JSON survey file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    readings = [HeatmapReading(**r) for r in data.get("readings", [])]
    return HeatmapSurvey(
        name=data.get("name", path.stem),
        floor_plan_path=data.get("floor_plan_path", ""),
        readings=readings,
        created_at=data.get("created_at", ""),
    )


def list_surveys() -> List[Path]:
    """Return sorted list of .json survey files in the surveys directory."""
    return sorted(surveys_dir().glob("*.json"))


# ── Interpolation ─────────────────────────────────────────────────────────────

def interpolate_heatmap(
    readings: List[HeatmapReading],
    bssid: Optional[str],
    resolution: int = 80,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    IDW (Inverse Distance Weighting) interpolation of RSSI readings.

    Parameters
    ----------
    readings   : list of HeatmapReading
    bssid      : lowercase BSSID string, or None / "all" for average of all APs
    resolution : grid size (pixels per side)

    Returns
    -------
    (xx, yy, zz) — each is a (resolution x resolution) array.
    xx and yy are grid coordinate fractions (0–1).
    zz contains dBm values; NaN where no coverage.
    """
    if not readings:
        g = np.linspace(0.0, 1.0, resolution)
        xx, yy = np.meshgrid(g, g)
        return xx, yy, np.full_like(xx, np.nan)

    # Build arrays of (x, y, dbm) for the chosen AP
    pts_x: List[float] = []
    pts_y: List[float] = []
    pts_z: List[float] = []

    use_all = (bssid is None or bssid.lower() in ("all", ""))

    for r in readings:
        if use_all:
            if r.readings:
                z = float(np.mean(list(r.readings.values())))
            else:
                continue
        else:
            key = bssid.lower()
            if key not in r.readings:
                continue
            z = float(r.readings[key])
        pts_x.append(r.x_frac)
        pts_y.append(r.y_frac)
        pts_z.append(z)

    if not pts_x:
        g = np.linspace(0.0, 1.0, resolution)
        xx, yy = np.meshgrid(g, g)
        return xx, yy, np.full_like(xx, np.nan)

    pts_x_arr = np.array(pts_x)
    pts_y_arr = np.array(pts_y)
    pts_z_arr = np.array(pts_z)

    g = np.linspace(0.0, 1.0, resolution)
    gx, gy = np.meshgrid(g, g)

    zz = _idw(pts_x_arr, pts_y_arr, pts_z_arr, gx, gy, power=2)
    return gx, gy, zz


def _idw(
    px: np.ndarray, py: np.ndarray, pz: np.ndarray,
    gx: np.ndarray, gy: np.ndarray,
    power: float = 2,
) -> np.ndarray:
    """Pure-numpy Inverse Distance Weighting on a 2D grid."""
    shape = gx.shape
    gx_flat = gx.ravel()
    gy_flat = gy.ravel()

    # Distance from each grid point to each sample point
    dx = gx_flat[:, None] - px[None, :]   # (N_grid, N_pts)
    dy = gy_flat[:, None] - py[None, :]
    dist = np.sqrt(dx ** 2 + dy ** 2)

    # If a grid point coincides exactly with a sample, return that sample's value
    min_dist = dist.min(axis=1)
    exact = min_dist < 1e-10
    nearest_idx = dist.argmin(axis=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        w = 1.0 / (dist ** power)
        w_sum = w.sum(axis=1, keepdims=True)
        zz_flat = (w * pz[None, :]).sum(axis=1) / w_sum[:, 0]

    zz_flat[exact] = pz[nearest_idx[exact]]
    return zz_flat.reshape(shape)


# ── Signal quality helpers ────────────────────────────────────────────────────

def dbm_to_quality(dbm: float) -> str:
    """Human-readable quality label for a dBm value."""
    if dbm >= -50:
        return "Excellent"
    if dbm >= -60:
        return "Good"
    if dbm >= -70:
        return "Fair"
    if dbm >= -80:
        return "Weak"
    return "Very Weak"


# dBm range for the colour scale (full colour = -40 dBm, faded = -90 dBm)
HEATMAP_VMIN = -90
HEATMAP_VMAX = -40
