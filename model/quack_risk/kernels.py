"""Omori–Utsu productivity and spatial kernels for one earthquake."""

from __future__ import annotations

import numpy as np

from quack_risk.config import RiskParams

POWERLAW_Q = 1.5


def kernel_width_km(magnitude: np.ndarray, params: RiskParams) -> np.ndarray:
    """Kernel width in kilometres.

    The width follows a rupture-length scaling, ``10^(0.5 M − 1.8)``, and
    never drops below ``params.min_length_km``. An M 6.2 is about 20 km, so
    the bright zone sits in the 20–40 km range the response scenario asks for.
    """
    raw = 10 ** (0.5 * np.asarray(magnitude, dtype=float) - 1.8)
    return np.maximum(raw, params.min_length_km)


def omori_productivity(magnitude, delta_days, params: RiskParams) -> np.ndarray:
    """Expected triggered events per day, before they are spread over space.

    ``K × 10^(α (M − M_c)) / (Δt + c)^p``
    """
    magnitude = np.asarray(magnitude, dtype=float)
    delta_days = np.maximum(np.asarray(delta_days, dtype=float), 0.0)
    scale = 10 ** (params.alpha * (magnitude - params.magnitude_threshold))
    return params.k * scale / (delta_days + params.c_days) ** params.p


def spatial_weights(
    distance_km: np.ndarray,
    magnitude: np.ndarray,
    area_km2: np.ndarray,
    params: RiskParams,
) -> np.ndarray:
    """Fraction of one event's triggered rate that lands in each cell.

    ``distance_km`` has shape ``(n_cells, n_events)``. Each column sums to 1,
    so a larger grid does not create extra probability: mass that falls
    outside the box is dropped and the rest is renormalized.
    """
    distance_km = np.asarray(distance_km, dtype=float)
    width = kernel_width_km(magnitude, params).reshape(1, -1)
    area = np.asarray(area_km2, dtype=float).reshape(-1, 1)
    density = _density(distance_km, width, params.kernel)
    raw = density * area
    column_sum = raw.sum(axis=0, keepdims=True)
    return raw / np.maximum(column_sum, 1e-30)


def _density(distance_km: np.ndarray, width_km: np.ndarray, kernel: str) -> np.ndarray:
    if kernel == "gaussian":
        scale = 2.0 * np.pi * width_km**2
        return np.exp(-0.5 * (distance_km / width_km) ** 2) / scale
    if kernel == "powerlaw":
        # (q − 1) / (π d²) (1 + (r/d)²)^(−q), which integrates to 1 over the plane.
        q = POWERLAW_Q
        ratio = (distance_km / width_km) ** 2
        return (q - 1.0) / (np.pi * width_km**2) * (1.0 + ratio) ** (-q)
    raise ValueError("kernel must be 'gaussian' or 'powerlaw'.")
