"""Gutenberg–Richter chances of larger magnitudes from the M >= Mc daily rate."""

from __future__ import annotations

import numpy as np
import pandas as pd

_PROBABILITY_CAP = 1.0 - 1e-15
B_VALUE = 1.0


def rate_at_least(
    daily_rate: np.ndarray,
    magnitude: float,
    *,
    magnitude_threshold: float = 4.0,
    b_value: float = B_VALUE,
) -> np.ndarray:
    """Daily rate of events at or above ``magnitude``.

    The grid rate is the rate at or above ``magnitude_threshold``. With a
    fixed b-value the larger-magnitude rate is that rate times
    ``10^(-b (magnitude - threshold))``.
    """
    if magnitude < magnitude_threshold:
        raise ValueError("outlook magnitude must be at or above the completeness threshold.")
    rate = np.maximum(np.asarray(daily_rate, dtype=float), 0.0)
    scale = 10 ** (-b_value * (magnitude - magnitude_threshold))
    return rate * scale


def probability_at_least(
    daily_rate: np.ndarray,
    magnitude: float,
    *,
    window_days: float = 1.0,
    magnitude_threshold: float = 4.0,
    b_value: float = B_VALUE,
) -> np.ndarray:
    """Poisson chance of at least one event at or above ``magnitude`` in the window."""
    scaled = rate_at_least(
        daily_rate,
        magnitude,
        magnitude_threshold=magnitude_threshold,
        b_value=b_value,
    )
    probability = 1.0 - np.exp(-scaled * window_days)
    return np.clip(probability, 0.0, _PROBABILITY_CAP)


def attach_outlook(
    grid: pd.DataFrame,
    *,
    magnitude_threshold: float = 4.0,
    b_value: float = B_VALUE,
) -> pd.DataFrame:
    """Add the 24-hour chance of magnitude 5 or larger and magnitude 6 or larger."""
    out = grid.copy()
    rate = out["total_rate"].to_numpy(dtype=float)
    out["probability_m5_24h"] = probability_at_least(
        rate,
        5.0,
        magnitude_threshold=magnitude_threshold,
        b_value=b_value,
    )
    out["probability_m6_24h"] = probability_at_least(
        rate,
        6.0,
        magnitude_threshold=magnitude_threshold,
        b_value=b_value,
    )
    return out
