"""Long-term rate per cell from earthquakes older than the trigger window."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter

from quack_risk.config import RiskParams
from quack_risk.geo import KM_PER_DEG

# Wide smooth so one historical epicenter does not poke a hole in the
# relative-risk map. The short-term hotspot has to come from the trigger term.
BACKGROUND_SMOOTH_KM = 80.0
FLOOR_FRACTION = 0.05
MIN_FLOOR_PER_DAY = 1e-6
MIN_EXPOSURE_DAYS = 1.0


def baseline_rates(
    catalog: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    bounds: tuple[float, float, float, float],
    resolution_deg: float,
    params: RiskParams,
) -> np.ndarray:
    """Return μ for each cell, flattened in latitude-major order.

    Counts use only events before ``as_of`` minus the recent window, so the
    same earthquake is not both background and a trigger. The result is
    events per day in the cell and is always positive.
    """
    n_lat = len(latitudes)
    n_lon = len(longitudes)
    counts = np.zeros((n_lat, n_lon), dtype=float)
    west, south, east, north = bounds
    times = pd.to_datetime(catalog["time"], utc=True)
    exposure_days = _exposure_days(times, as_of)

    if not catalog.empty:
        window_start = as_of - pd.Timedelta(days=params.recent_window_days)
        magnitudes = catalog["magnitude"].to_numpy(dtype=float)
        background = (times < window_start) & (magnitudes >= params.magnitude_threshold)
        if bool(background.any()):
            lat = catalog.loc[background, "latitude"].to_numpy(dtype=float)
            lon = catalog.loc[background, "longitude"].to_numpy(dtype=float)
            inside = (lat >= south) & (lat <= north) & (lon >= west) & (lon <= east)
            lat_index = np.floor((lat[inside] - south) / resolution_deg).astype(int)
            lon_index = np.floor((lon[inside] - west) / resolution_deg).astype(int)
            np.add.at(counts, (np.clip(lat_index, 0, n_lat - 1), np.clip(lon_index, 0, n_lon - 1)), 1.0)

    cell_km = resolution_deg * KM_PER_DEG
    sigma_cells = max(BACKGROUND_SMOOTH_KM / cell_km, 0.5)
    smoothed = gaussian_filter(counts, sigma=sigma_cells, mode="constant", cval=0.0)
    total_counts = float(counts.sum())
    smoothed_total = float(smoothed.sum())
    if total_counts > 0 and smoothed_total > 0:
        smoothed *= total_counts / smoothed_total

    rates = smoothed / exposure_days
    n_cells = n_lat * n_lon
    mean_rate = float(rates.sum() / n_cells) if n_cells else 0.0
    floor = max(MIN_FLOOR_PER_DAY, FLOOR_FRACTION * mean_rate)
    return (rates + floor).ravel()


def _exposure_days(times: pd.Series, as_of: pd.Timestamp) -> float:
    if times.empty:
        return 365.0
    history = times[times <= as_of]
    if history.empty:
        return 365.0
    span = float((as_of - history.min()) / pd.Timedelta(days=1))
    return max(span, MIN_EXPOSURE_DAYS)
