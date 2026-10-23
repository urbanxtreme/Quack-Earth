"""Default ETAS-style parameters and the bounds used when they are fitted."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskParams:
    """Starting values for the short-term rate.

    ``k``, ``c_days``, and ``p`` are the ones Phase 3 is allowed to fit.
    ``alpha`` stays fixed. ``k`` is a productivity weight: an isolated M 6.0
    at age 0.1 day should lift the epicentral cell well above its baseline.
    The fitted value in ``data/cache/params.json`` replaces this default.
    """

    k: float = 0.01
    alpha: float = 0.9
    c_days: float = 0.05
    p: float = 1.1
    magnitude_threshold: float = 4.0
    recent_window_days: float = 14.0
    kernel: str = "gaussian"
    min_length_km: float = 8.0
    moderate_at: float = 1.5
    elevated_at: float = 3.0
    high_at: float = 10.0

    def __post_init__(self) -> None:
        if self.kernel not in {"gaussian", "powerlaw"}:
            raise ValueError("kernel must be 'gaussian' or 'powerlaw'.")
        if self.magnitude_threshold <= 0:
            raise ValueError("magnitude_threshold must be positive.")
        if not self.moderate_at < self.elevated_at < self.high_at:
            raise ValueError("Risk-level cutoffs must increase.")


# k > 0. c and p use the published ranges from the plan.
PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "k": (1e-8, 10.0),
    "c_days": (0.001, 1.0),
    "p": (0.8, 1.5),
}

# Demo box for the 2023 Kahramanmaraş sequence: (west, south, east, north).
DEMO_BOUNDS: tuple[float, float, float, float] = (35.0, 34.0, 41.0, 41.0)
DEMO_AS_OF: str = "2023-02-07T00:00:00Z"
RESOLUTION_DEG: float = 0.2
PROBABILITY_WINDOWS_DAYS: tuple[float, float] = (1.0, 7.0)
