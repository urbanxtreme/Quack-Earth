"""Fit K, c, and p by Poisson likelihood on the days after a mainshock.

The spatial kernel and alpha stay fixed. Each day is scored only with
earthquakes at or before that day's start, then compared with the events
that actually occur during the day.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import differential_evolution

from quack_risk.config import PARAM_BOUNDS, RiskParams
from quack_risk.baseline import baseline_rates
from quack_risk.engine import EVENT_CHUNK
from quack_risk.geo import cell_area_km2, equirectangular_km, grid_centers
from quack_risk.io import validate_catalog
from quack_risk.kernels import spatial_weights

FIT_DAYS = 10
_LOG_K_BOUNDS = (np.log10(PARAM_BOUNDS["k"][0]), np.log10(PARAM_BOUNDS["k"][1]))


@dataclass(frozen=True)
class PreparedBin:
    """One day of the fit, with the spatial weights already built."""

    as_of: pd.Timestamp
    baseline: np.ndarray
    weights: np.ndarray
    scale: np.ndarray
    age_days: np.ndarray
    counts: np.ndarray


@dataclass(frozen=True)
class FitResult:
    """Best K, c, and p, plus the likelihood they scored."""

    params: RiskParams
    log_likelihood: float
    baseline_log_likelihood: float
    origin: str
    n_days: int
    n_observed: int


def select_mainshock(catalog: pd.DataFrame) -> pd.Series:
    """Largest event. The earlier one wins a magnitude tie."""
    frame = validate_catalog(catalog)
    if frame.empty:
        raise ValueError("Cannot choose a mainshock from an empty catalog.")
    order = frame.sort_values(["magnitude", "time"], ascending=[False, True], kind="mergesort")
    return order.iloc[0]


def poisson_log_likelihood(rate: np.ndarray, counts: np.ndarray) -> float:
    """Sum of ``n log λ − λ``. The factorial term does not depend on the parameters."""
    safe = np.maximum(np.asarray(rate, dtype=float), 1e-30)
    observed = np.asarray(counts, dtype=float)
    scored = np.where(observed > 0.0, observed * np.log(safe), 0.0)
    return float(np.sum(scored - safe))


def prepare_bin(
    catalog: pd.DataFrame,
    *,
    as_of,
    bounds: tuple[float, float, float, float],
    resolution_deg: float,
    params: RiskParams,
    count_through=None,
) -> PreparedBin:
    """Build one day.

    Triggers are events in the recent window at or before ``as_of``. When
    ``count_through`` is set, counts are events after ``as_of`` up to that
    time. The mainshock at exactly ``as_of`` is a trigger and not a count.
    """
    events = validate_catalog(catalog)
    as_of_utc = _as_utc(as_of)
    west, south, east, north = (float(value) for value in bounds)
    box = (west, south, east, north)
    latitudes, longitudes = grid_centers(box, resolution_deg)
    lat_grid, lon_grid = np.meshgrid(latitudes, longitudes, indexing="ij")
    flat_lat = lat_grid.ravel()
    flat_lon = lon_grid.ravel()
    flat_area = cell_area_km2(flat_lat, resolution_deg)
    baseline = baseline_rates(
        events,
        as_of=as_of_utc,
        latitudes=latitudes,
        longitudes=longitudes,
        bounds=box,
        resolution_deg=resolution_deg,
        params=params,
    )
    weights, scale, age_days = _trigger_design(events, as_of_utc, flat_lat, flat_lon, flat_area, params)
    if count_through is None:
        counts = np.zeros(flat_lat.shape[0], dtype=float)
    else:
        counts = observation_counts(
            events,
            as_of=as_of_utc,
            count_through=_as_utc(count_through),
            bounds=box,
            resolution_deg=resolution_deg,
            magnitude_threshold=params.magnitude_threshold,
        )
    return PreparedBin(
        as_of=as_of_utc,
        baseline=baseline,
        weights=weights,
        scale=scale,
        age_days=age_days,
        counts=counts,
    )


def prepare_bins(
    catalog: pd.DataFrame,
    *,
    origin,
    bounds: tuple[float, float, float, float],
    resolution_deg: float,
    params: RiskParams,
    n_days: int = FIT_DAYS,
) -> list[PreparedBin]:
    """One prepared day for each of the ``n_days`` after ``origin``."""
    if n_days < 1:
        raise ValueError("n_days must be at least 1.")
    start = _as_utc(origin)
    bins = []
    for day in range(n_days):
        as_of = start + pd.Timedelta(days=day)
        bins.append(
            prepare_bin(
                catalog,
                as_of=as_of,
                bounds=bounds,
                resolution_deg=resolution_deg,
                params=params,
                count_through=as_of + pd.Timedelta(days=1),
            )
        )
    return bins


def total_rate(prepared: PreparedBin, *, k: float, c_days: float, p: float) -> np.ndarray:
    """Baseline plus the triggered rate for one parameter set."""
    return prepared.baseline + triggered_rate(prepared, k=k, c_days=c_days, p=p)


def triggered_rate(prepared: PreparedBin, *, k: float, c_days: float, p: float) -> np.ndarray:
    """Triggered events per day. ``K``, ``c``, and ``p`` are the only moving parts."""
    if prepared.weights.shape[1] == 0:
        return np.zeros(prepared.baseline.shape[0], dtype=float)
    productivity = k * prepared.scale / (prepared.age_days + c_days) ** p
    return prepared.weights @ productivity


def window_log_likelihood(bins: list[PreparedBin], *, k: float, c_days: float, p: float) -> float:
    """Poisson log-likelihood over every cell of every prepared day."""
    total = 0.0
    for prepared in bins:
        total += poisson_log_likelihood(total_rate(prepared, k=k, c_days=c_days, p=p), prepared.counts)
    return total


def baseline_log_likelihood(bins: list[PreparedBin]) -> float:
    """Same window with the trigger term removed."""
    return float(sum(poisson_log_likelihood(prepared.baseline, prepared.counts) for prepared in bins))


def fit_catalog(
    catalog: pd.DataFrame,
    *,
    bounds: tuple[float, float, float, float],
    resolution_deg: float = 0.2,
    n_days: int = FIT_DAYS,
    magnitude_threshold: float = 4.0,
    maxiter: int = 20,
    seed: int = 7,
    progress=None,
) -> FitResult:
    """Search ``K``, ``c``, and ``p`` and keep the best likelihood, including the start values."""
    events = validate_catalog(catalog)
    mainshock = select_mainshock(events)
    origin = _as_utc(mainshock["time"])
    base = replace(RiskParams(), magnitude_threshold=magnitude_threshold)
    design = prepare_bins(
        events,
        origin=origin,
        bounds=bounds,
        resolution_deg=resolution_deg,
        params=base,
        n_days=n_days,
    )
    found = _search(design, base, maxiter=maxiter, seed=seed, progress=progress)
    start = window_log_likelihood(design, k=base.k, c_days=base.c_days, p=base.p)
    if start > found[0]:
        chosen = (start, base.k, base.c_days, base.p)
    else:
        chosen = found
    params = replace(base, k=float(chosen[1]), c_days=float(chosen[2]), p=float(chosen[3]))
    return FitResult(
        params=params,
        log_likelihood=float(chosen[0]),
        baseline_log_likelihood=baseline_log_likelihood(design),
        origin=origin.strftime("%Y-%m-%dT%H:%M:%SZ"),
        n_days=n_days,
        n_observed=int(sum(float(prepared.counts.sum()) for prepared in design)),
    )


def write_params(result: FitResult, path: str | Path) -> Path:
    """Write the fitted ``K``, ``c``, and ``p`` next to the cache catalog."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "k": result.params.k,
        "c_days": result.params.c_days,
        "p": result.params.p,
        "alpha": result.params.alpha,
        "magnitude_threshold": result.params.magnitude_threshold,
        "origin": result.origin,
        "n_days": result.n_days,
        "n_observed": result.n_observed,
        "log_likelihood": result.log_likelihood,
        "baseline_log_likelihood": result.baseline_log_likelihood,
    }
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def load_fitted_params(path: str | Path) -> RiskParams | None:
    """Read ``K``, ``c``, and ``p``. A missing file returns ``None``. Alpha stays at its fixed value."""
    file_path = Path(path)
    if not file_path.is_file():
        return None
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    return replace(
        RiskParams(),
        k=float(payload["k"]),
        c_days=float(payload["c_days"]),
        p=float(payload["p"]),
        magnitude_threshold=float(payload.get("magnitude_threshold", RiskParams().magnitude_threshold)),
    )


def observation_counts(
    catalog: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    count_through: pd.Timestamp,
    bounds: tuple[float, float, float, float],
    resolution_deg: float,
    magnitude_threshold: float,
) -> np.ndarray:
    """Count events in ``(as_of, count_through]`` into latitude-major cells."""
    latitudes, longitudes = grid_centers(bounds, resolution_deg)
    n_lat = len(latitudes)
    n_lon = len(longitudes)
    counts = np.zeros(n_lat * n_lon, dtype=float)
    if catalog.empty:
        return counts
    west, south, east, north = bounds
    times = pd.to_datetime(catalog["time"], utc=True)
    keep = (times > as_of) & (times <= count_through)
    keep = keep & (catalog["magnitude"].to_numpy(dtype=float) >= magnitude_threshold)
    if not bool(keep.any()):
        return counts
    latitude = catalog.loc[keep, "latitude"].to_numpy(dtype=float)
    longitude = catalog.loc[keep, "longitude"].to_numpy(dtype=float)
    inside = (latitude >= south) & (latitude <= north) & (longitude >= west) & (longitude <= east)
    if not bool(inside.any()):
        return counts
    lat_index = np.floor((latitude[inside] - south) / resolution_deg).astype(int)
    lon_index = np.floor((longitude[inside] - west) / resolution_deg).astype(int)
    lat_index = np.clip(lat_index, 0, n_lat - 1)
    lon_index = np.clip(lon_index, 0, n_lon - 1)
    np.add.at(counts, lat_index * n_lon + lon_index, 1.0)
    return counts


def cell_index(
    latitude: float,
    longitude: float,
    bounds: tuple[float, float, float, float],
    resolution_deg: float,
) -> int:
    """Flat latitude-major index of the cell that contains one epicenter."""
    latitudes, longitudes = grid_centers(bounds, resolution_deg)
    west, south, _, _ = bounds
    lat_index = int(np.clip(np.floor((latitude - south) / resolution_deg), 0, len(latitudes) - 1))
    lon_index = int(np.clip(np.floor((longitude - west) / resolution_deg), 0, len(longitudes) - 1))
    return lat_index * len(longitudes) + lon_index


def _trigger_design(
    catalog: pd.DataFrame,
    as_of: pd.Timestamp,
    flat_lat: np.ndarray,
    flat_lon: np.ndarray,
    flat_area: np.ndarray,
    params: RiskParams,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n_cells = flat_lat.shape[0]
    if catalog.empty:
        return np.zeros((n_cells, 0)), np.zeros(0), np.zeros(0)
    times = pd.to_datetime(catalog["time"], utc=True)
    delta_days = ((as_of - times) / pd.Timedelta(days=1)).to_numpy(dtype=float)
    magnitudes = catalog["magnitude"].to_numpy(dtype=float)
    recent = (delta_days >= 0.0) & (delta_days <= params.recent_window_days)
    recent = recent & (magnitudes >= params.magnitude_threshold)
    if not bool(recent.any()):
        return np.zeros((n_cells, 0)), np.zeros(0), np.zeros(0)

    chosen = catalog.loc[recent]
    event_lat = chosen["latitude"].to_numpy(dtype=float)
    event_lon = chosen["longitude"].to_numpy(dtype=float)
    event_mag = chosen["magnitude"].to_numpy(dtype=float)
    age_days = delta_days[recent]
    scale = 10 ** (params.alpha * (event_mag - params.magnitude_threshold))
    if "trigger_weight" in chosen.columns:
        scale = scale * chosen["trigger_weight"].to_numpy(dtype=float)
    weights = np.zeros((n_cells, len(chosen)), dtype=float)
    for start in range(0, len(chosen), EVENT_CHUNK):
        stop = start + EVENT_CHUNK
        distance = equirectangular_km(
            flat_lat[:, None],
            flat_lon[:, None],
            event_lat[start:stop][None, :],
            event_lon[start:stop][None, :],
        )
        weights[:, start:stop] = spatial_weights(distance, event_mag[start:stop], flat_area, params)
    return weights, scale, age_days


def _search(bins: list[PreparedBin], base: RiskParams, *, maxiter: int, seed: int, progress) -> tuple[float, float, float, float]:
    bounds = [_LOG_K_BOUNDS, PARAM_BOUNDS["c_days"], PARAM_BOUNDS["p"]]

    def negative(theta: np.ndarray) -> float:
        return -window_log_likelihood(bins, k=10 ** float(theta[0]), c_days=float(theta[1]), p=float(theta[2]))

    def callback(theta: np.ndarray, *_) -> None:
        if progress is not None:
            progress(10 ** float(theta[0]), float(theta[1]), float(theta[2]))

    found = differential_evolution(
        negative,
        bounds=bounds,
        maxiter=maxiter,
        popsize=8,
        seed=seed,
        polish=True,
        atol=0.0,
        tol=0.01,
        workers=1,
        callback=callback,
    )
    k = float(10 ** found.x[0])
    c_days = float(found.x[1])
    p = float(found.x[2])
    return window_log_likelihood(bins, k=k, c_days=c_days, p=p), k, c_days, p


def _as_utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")
