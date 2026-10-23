"""Omori productivity and spatial kernels."""

from __future__ import annotations

import numpy as np
import pytest

from quack_risk.config import RiskParams
from quack_risk.kernels import kernel_width_km, omori_productivity, spatial_weights


def test_larger_magnitude_has_higher_productivity() -> None:
    params = RiskParams()
    productivity = omori_productivity(np.array([4.5, 5.5, 6.5]), np.full(3, 0.1), params)
    assert productivity[0] < productivity[1] < productivity[2]


def test_older_event_has_lower_productivity() -> None:
    params = RiskParams()
    productivity = omori_productivity(np.full(3, 6.2), np.array([0.01, 1.0, 7.0]), params)
    assert productivity[0] > productivity[1] > productivity[2]


def test_productivity_matches_the_omori_formula() -> None:
    params = RiskParams()
    expected = 0.01 * 10 ** (0.9 * (6.0 - 4.0)) / (0.1 + 0.05) ** 1.1
    got = omori_productivity(np.array([6.0]), np.array([0.1]), params)
    assert got[0] == pytest.approx(expected)


def test_kernel_width_is_floored_and_scales_with_magnitude() -> None:
    width = kernel_width_km(np.array([2.0, 6.2]), RiskParams())
    assert width[0] == 8.0
    assert width[1] == pytest.approx(10 ** (0.5 * 6.2 - 1.8))
    assert width[1] == pytest.approx(20.0, abs=0.2)


@pytest.mark.parametrize("kernel", ["gaussian", "powerlaw"])
def test_spatial_weight_falls_with_distance_and_sums_to_one(kernel: str) -> None:
    params = RiskParams(kernel=kernel)
    distance = np.array([[0.0], [20.0], [60.0]])
    weights = spatial_weights(distance, np.array([6.2]), np.full(3, 25.0), params)
    assert weights[0, 0] > weights[1, 0] > weights[2, 0]
    assert weights.sum() == pytest.approx(1.0)
