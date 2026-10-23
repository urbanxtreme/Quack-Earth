"""Phase 3: the daily Poisson fit matches the scorer, and the plots have a home."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quack_risk.calibrate import (
    FitResult,
    load_fitted_params,
    observation_counts,
    prepare_bin,
    select_mainshock,
    total_rate,
    window_log_likelihood,
    write_params,
)
from quack_risk.catalog_fetch import fdsn_demo_url
from quack_risk.config import DEMO_BOUNDS, RiskParams
from quack_risk.engine import score_grid
from quack_risk.evaluate import capture_curve, top_fraction_capture, write_evaluation
from quack_risk.io import validate_catalog

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "data" / "fixtures" / "scenario_m62.csv"
BOX = (36.2, 36.2, 38.2, 38.2)
ORIGIN = "2024-01-15T03:15:00Z"


def _catalog() -> pd.DataFrame:
    return validate_catalog(pd.read_csv(SCENARIO))


def test_demo_query_uses_the_regional_box() -> None:
    url = fdsn_demo_url()
    assert "starttime=2018-01-01" in url
    assert "endtime=2023-02-21" in url
    assert "minmagnitude=4" in url
    assert "minlatitude=34" in url
    assert "minlongitude=35" in url
    assert "maxlatitude=41" in url
    assert "maxlongitude=41" in url


def test_largest_event_is_the_mainshock() -> None:
    mainshock = select_mainshock(_catalog())
    assert mainshock["id"] == "m62"
    assert float(mainshock["magnitude"]) == 6.2


def test_prepared_rate_matches_score_grid() -> None:
    catalog = _catalog()
    params = RiskParams()
    prepared = prepare_bin(
        catalog,
        as_of=ORIGIN,
        bounds=BOX,
        resolution_deg=0.5,
        params=params,
    )
    grid = score_grid(
        catalog,
        as_of=ORIGIN,
        bounds=BOX,
        resolution_deg=0.5,
        params=params,
    )
    scored = total_rate(prepared, k=params.k, c_days=params.c_days, p=params.p)
    assert np.allclose(scored, grid["total_rate"].to_numpy())


def test_the_mainshock_itself_is_not_an_observation() -> None:
    catalog = _catalog()
    origin = pd.Timestamp(ORIGIN)
    counts = observation_counts(
        catalog,
        as_of=origin,
        count_through=origin + pd.Timedelta(days=1),
        bounds=BOX,
        resolution_deg=0.5,
        magnitude_threshold=4.0,
    )
    later = catalog.copy()
    later["time"] = pd.Timestamp("2024-01-15T05:15:00Z")
    later = later.loc[later["id"] == "m62"]
    counted = observation_counts(
        later,
        as_of=origin,
        count_through=origin + pd.Timedelta(days=1),
        bounds=BOX,
        resolution_deg=0.5,
        magnitude_threshold=4.0,
    )
    assert counts.sum() == 0
    assert counted.sum() == 1


def test_a_higher_rate_on_the_occupied_cell_fits_better() -> None:
    occupied = np.array([1.0, 0.0])
    quiet = window_log_likelihood_pair(np.array([1e-6, 1e-6]), occupied)
    placed = window_log_likelihood_pair(np.array([0.4, 1e-6]), occupied)
    assert placed > quiet


def window_log_likelihood_pair(rate: np.ndarray, counts: np.ndarray) -> float:
    from quack_risk.calibrate import poisson_log_likelihood

    return poisson_log_likelihood(rate, counts)


def test_top_fifth_of_cells_can_hold_every_event() -> None:
    rate = np.array([5.0, 4.0, 3.0, 2.0, 1.0])
    counts = np.array([1.0, 1.0, 0.0, 0.0, 0.0])
    share, captured = capture_curve(rate, counts)
    assert share[0] == pytest.approx(0.2)
    assert captured[0] == pytest.approx(0.5)
    assert top_fraction_capture(rate, counts, 0.2) == pytest.approx(0.5)


def test_params_roundtrip(tmp_path: Path) -> None:
    params = RiskParams(k=0.02, c_days=0.08, p=1.2)
    result = FitResult(
        params=params,
        log_likelihood=-10.0,
        baseline_log_likelihood=-12.0,
        origin="2023-02-06T01:17:35Z",
        n_days=10,
        n_observed=4,
    )
    path = write_params(result, tmp_path / "params.json")
    loaded = load_fitted_params(path)
    assert loaded is not None
    assert loaded.k == pytest.approx(0.02)
    assert loaded.c_days == pytest.approx(0.08)
    assert loaded.p == pytest.approx(1.2)
    assert load_fitted_params(tmp_path / "missing.json") is None


def test_evaluation_writes_the_four_plots(tmp_path: Path) -> None:
    metrics = write_evaluation(
        _catalog(),
        RiskParams(),
        tmp_path,
        bounds=BOX,
        resolution_deg=0.5,
        snapshot_as_of="2024-01-15T04:00:00Z",
    )
    for name in ("omori_decay.png", "risk_snapshot_24h.png", "capture_curve.png", "likelihood_bars.png", "metrics.json"):
        assert (tmp_path / name).is_file()
    assert metrics["mainshock_magnitude"] == pytest.approx(6.2)
    assert "log_likelihood_full" in metrics
    assert DEMO_BOUNDS[0] == 35.0
