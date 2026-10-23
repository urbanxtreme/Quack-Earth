"""Turn a daily cell rate into relative risk, window probabilities, and a level."""

from __future__ import annotations

import numpy as np

from quack_risk.config import PROBABILITY_WINDOWS_DAYS, RiskParams

_PROBABILITY_CAP = 1.0 - 1e-15


def relative_risk(total_rate: np.ndarray, baseline_rate: np.ndarray) -> np.ndarray:
    """``total / baseline``. Baseline is always positive."""
    return np.asarray(total_rate, dtype=float) / np.maximum(np.asarray(baseline_rate, dtype=float), 1e-30)


def window_probabilities(daily_rate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Chance of at least one event in 24 hours and in 7 days, assuming a Poisson count."""
    rate = np.maximum(np.asarray(daily_rate, dtype=float), 0.0)
    day_24h, day_7d = PROBABILITY_WINDOWS_DAYS
    probability_24h = 1.0 - np.exp(-rate * day_24h)
    probability_7d = 1.0 - np.exp(-rate * day_7d)
    return (
        np.clip(probability_24h, 0.0, _PROBABILITY_CAP),
        np.clip(probability_7d, 0.0, _PROBABILITY_CAP),
    )


def risk_levels(relative: np.ndarray, params: RiskParams) -> np.ndarray:
    """``low`` below 1.5, ``moderate`` below 3, ``elevated`` below 10, else ``high``."""
    values = np.asarray(relative, dtype=float)
    levels = np.full(values.shape, "low", dtype=object)
    levels[values >= params.moderate_at] = "moderate"
    levels[values >= params.elevated_at] = "elevated"
    levels[values >= params.high_at] = "high"
    return levels
