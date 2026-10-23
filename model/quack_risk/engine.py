"""Short-term rate on a grid: baseline plus every recent earthquake."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from quack_risk.baseline import baseline_rates
from quack_risk.config import RiskParams
from quack_risk.geo import cell_area_km2, equirectangular_km, grid_centers
from quack_risk.io import validate_catalog
from quack_risk.kernels import omori_productivity, spatial_weights
from quack_risk.probability import relative_risk, risk_levels, window_probabilities
from quack_risk.schema import GRID_COLUMNS

EVENT_CHUNK = 64


def score_grid(
    catalog: pd.DataFrame,
    *,
    as_of,
    bounds: tuple[float, float, float, float],
    resolution_deg: float = 0.2,
    magnitude_threshold: float = 4.0,
    local_signals: pd.DataFrame | None = None,
    params: RiskParams | None = None,
    use_ml_adjustment: bool = False,
) -> pd.DataFrame:
    """Score every cell from a cached catalog. No network calls.

    ``λ = μ + Σ K × 10^(α (M − M_c)) / (Δt + c)^p × spatial_weight``

    Events after ``as_of`` are ignored. Events older than the recent window
    stay in the baseline and do not trigger. ``local_signals`` is accepted so
    the signature stays stable; accelerometer and report rows are applied in
    the next phase and do not change this grid. ``use_ml_adjustment`` is the
    Phase 3 residual and raises if turned on.

    Rates are expected events per day in the cell at or above ``M_c``.
    """
    if use_ml_adjustment:
        raise NotImplementedError(
            "use_ml_adjustment is reserved for Phase 3. "
            "Call score_grid with use_ml_adjustment=False."
        )
    if local_signals is not None and len(local_signals) > 0:
        # Kept on the signature for the offline report flow. Not applied yet.
        pass

    params = replace(params or RiskParams(), magnitude_threshold=magnitude_threshold)
    if params.k < 0 or params.c_days <= 0 or params.p <= 0:
        raise ValueError("k must be >= 0, and c_days and p must be positive.")

    as_of_utc = _as_utc(as_of)
    west, south, east, north = (float(value) for value in bounds)
    box = (west, south, east, north)
    latitudes, longitudes = grid_centers(box, resolution_deg)
    lat_grid, lon_grid = np.meshgrid(latitudes, longitudes, indexing="ij")
    flat_lat = lat_grid.ravel()
    flat_lon = lon_grid.ravel()
    flat_area = cell_area_km2(flat_lat, resolution_deg)

    events = validate_catalog(catalog)
    baseline = baseline_rates(
        events,
        as_of=as_of_utc,
        latitudes=latitudes,
        longitudes=longitudes,
        bounds=box,
        resolution_deg=resolution_deg,
        params=params,
    )
    triggered = _triggered_rates(
        events,
        as_of=as_of_utc,
        flat_lat=flat_lat,
        flat_lon=flat_lon,
        flat_area=flat_area,
        params=params,
    )
    total = baseline + triggered
    probability_24h, probability_7d = window_probabilities(total)
    comparison = relative_risk(total, baseline)
    frame = pd.DataFrame(
        {
            "lat": flat_lat,
            "lon": flat_lon,
            "baseline_rate": baseline,
            "triggered_rate": triggered,
            "total_rate": total,
            "probability_24h": probability_24h,
            "probability_7d": probability_7d,
            "relative_risk": comparison,
            "risk_level": risk_levels(comparison, params),
        }
    )
    frame = frame.loc[:, list(GRID_COLUMNS)]
    return frame.sort_values(["lat", "lon"], kind="mergesort").reset_index(drop=True)


def _triggered_rates(
    catalog: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    flat_lat: np.ndarray,
    flat_lon: np.ndarray,
    flat_area: np.ndarray,
    params: RiskParams,
) -> np.ndarray:
    total = np.zeros(flat_lat.shape[0], dtype=float)
    if catalog.empty:
        return total

    times = pd.to_datetime(catalog["time"], utc=True)
    delta_days = (as_of - times) / pd.Timedelta(days=1)
    magnitudes = catalog["magnitude"].to_numpy(dtype=float)
    recent = (
        (delta_days >= 0)
        & (delta_days <= params.recent_window_days)
        & (magnitudes >= params.magnitude_threshold)
    )
    if not bool(recent.any()):
        return total

    chosen = catalog.loc[recent]
    event_lat = chosen["latitude"].to_numpy(dtype=float)
    event_lon = chosen["longitude"].to_numpy(dtype=float)
    event_mag = chosen["magnitude"].to_numpy(dtype=float)
    event_age = delta_days.loc[recent].to_numpy(dtype=float)
    productivity = omori_productivity(event_mag, event_age, params)

    for start in range(0, len(chosen), EVENT_CHUNK):
        stop = start + EVENT_CHUNK
        distance = equirectangular_km(
            flat_lat[:, None],
            flat_lon[:, None],
            event_lat[start:stop][None, :],
            event_lon[start:stop][None, :],
        )
        weights = spatial_weights(distance, event_mag[start:stop], flat_area, params)
        total += weights @ productivity[start:stop]
    return total


def _as_utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")
