"""Phase 1 rate engine, checked against the offline aftershock scenario."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quack_risk.baseline import FLOOR_FRACTION, MIN_FLOOR_PER_DAY
from quack_risk.config import RiskParams
from quack_risk.engine import score_grid
from quack_risk.geo import equirectangular_km
from quack_risk.io import validate_catalog
from quack_risk.schema import CATALOG_COLUMNS, GRID_COLUMNS
import quack_risk.engine as engine_module

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "data" / "fixtures" / "scenario_m62.csv"
FIXTURE = ROOT / "data" / "fixtures" / "catalog.csv"
BOX = (36.2, 36.2, 38.2, 38.2)
MAIN_TIME = "2024-01-15T03:15:00Z"
AFTER = "2024-01-15T03:35:00Z"
BEFORE = "2024-01-15T03:10:00Z"


def _catalog(rows: list[dict]) -> pd.DataFrame:
    return validate_catalog(pd.DataFrame(rows))


def _event(event_id: str, time: str, lat: float, lon: float, magnitude: float) -> dict:
    return {
        "id": event_id,
        "time": time,
        "latitude": lat,
        "longitude": lon,
        "depth_km": 10.0,
        "magnitude": magnitude,
        "mag_type": "mww",
        "source": "usgs",
    }


def _nearest(grid: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    distance = equirectangular_km(grid["lat"], grid["lon"], lat, lon)
    return grid.iloc[int(np.argmin(distance))]


def test_empty_catalog_is_baseline_only() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    grid = score_grid(empty, as_of=AFTER, bounds=BOX, resolution_deg=0.2)
    assert list(grid.columns) == list(GRID_COLUMNS)
    assert np.allclose(grid["total_rate"], grid["baseline_rate"])
    assert np.allclose(grid["triggered_rate"], 0.0)
    assert np.allclose(grid["relative_risk"], 1.0)
    assert set(grid["risk_level"]) == {"low"}


def test_future_event_does_not_change_the_score() -> None:
    past = _catalog([_event("m62", MAIN_TIME, 37.2, 37.0, 6.2)])
    future = _catalog(
        [
            _event("m62", MAIN_TIME, 37.2, 37.0, 6.2),
            _event("later", "2024-01-16T00:00:00Z", 37.2, 37.0, 7.0),
        ]
    )
    before = score_grid(past, as_of=AFTER, bounds=BOX, resolution_deg=0.2)
    after = score_grid(future, as_of=AFTER, bounds=BOX, resolution_deg=0.2)
    pd.testing.assert_frame_equal(before, after)


def test_event_older_than_the_window_does_not_trigger() -> None:
    as_of = pd.Timestamp("2024-01-15T00:00:00Z")
    old = _catalog([_event("old", "2023-10-07T00:00:00Z", 37.0, 37.0, 6.5)])
    grid = score_grid(old, as_of=as_of, bounds=(36.5, 36.5, 37.5, 37.5), resolution_deg=0.2)
    assert np.allclose(grid["triggered_rate"], 0.0)
    assert np.allclose(grid["total_rate"], grid["baseline_rate"])
    exposure_days = 100.0
    mean_rate = (1.0 / exposure_days) / len(grid)
    floor = max(MIN_FLOOR_PER_DAY, FLOOR_FRACTION * mean_rate)
    expected = 1.0 / exposure_days + floor * len(grid)
    assert grid["baseline_rate"].sum() == pytest.approx(expected, rel=1e-5)


def test_below_completeness_does_not_trigger() -> None:
    small = _catalog([_event("tiny", MAIN_TIME, 37.2, 37.0, 3.5)])
    grid = score_grid(small, as_of=AFTER, bounds=BOX, resolution_deg=0.2)
    assert np.allclose(grid["triggered_rate"], 0.0)


def test_larger_magnitude_raises_the_epicentral_and_total_rate() -> None:
    small = _catalog([_event("m", MAIN_TIME, 37.2, 37.0, 4.5)])
    large = _catalog([_event("m", MAIN_TIME, 37.2, 37.0, 6.5)])
    kwargs = {"as_of": AFTER, "bounds": BOX, "resolution_deg": 0.1}
    small_grid = score_grid(small, **kwargs)
    large_grid = score_grid(large, **kwargs)
    assert large_grid["triggered_rate"].sum() > small_grid["triggered_rate"].sum()
    assert _nearest(large_grid, 37.2, 37.0)["total_rate"] > _nearest(small_grid, 37.2, 37.0)["total_rate"]


def test_rate_decays_over_the_next_day_and_week() -> None:
    catalog = _catalog([_event("m62", MAIN_TIME, 37.2, 37.0, 6.2)])
    kwargs = {"bounds": BOX, "resolution_deg": 0.1}
    soon = score_grid(catalog, as_of=AFTER, **kwargs)
    day = score_grid(catalog, as_of="2024-01-16T03:15:00Z", **kwargs)
    week = score_grid(catalog, as_of="2024-01-22T03:15:00Z", **kwargs)
    soon_rate = _nearest(soon, 37.2, 37.0)["triggered_rate"]
    day_rate = _nearest(day, 37.2, 37.0)["triggered_rate"]
    week_rate = _nearest(week, 37.2, 37.0)["triggered_rate"]
    assert soon_rate > day_rate > week_rate


def test_closer_cell_is_higher_than_a_far_cell() -> None:
    catalog = _catalog([_event("m62", MAIN_TIME, 37.2, 37.0, 6.2)])
    grid = score_grid(catalog, as_of=AFTER, bounds=BOX, resolution_deg=0.1)
    near = _nearest(grid, 37.2, 37.0)["total_rate"]
    far = _nearest(grid, 38.1, 38.1)["total_rate"]
    assert near > far


def test_m62_bright_zone_and_decay_match_the_outage_scenario() -> None:
    catalog = validate_catalog(pd.read_csv(SCENARIO))
    before = score_grid(catalog, as_of=BEFORE, bounds=BOX, resolution_deg=0.05)
    after = score_grid(catalog, as_of=AFTER, bounds=BOX, resolution_deg=0.05)

    assert after["total_rate"].max() > 10.0 * before["total_rate"].max()

    peak = after.loc[after["total_rate"].idxmax()]
    assert equirectangular_km(peak["lat"], peak["lon"], 37.2, 37.0) < 15.0
    assert peak["risk_level"] == "high"
    assert 0.0 <= peak["probability_24h"] < 1.0
    assert peak["probability_7d"] >= peak["probability_24h"]

    distance = equirectangular_km(after["lat"], after["lon"], peak["lat"], peak["lon"])
    bright = distance[after["total_rate"] >= 0.3 * peak["total_rate"]]
    assert bright.max() > 18.0
    assert bright.max() < 45.0

    edge = after.loc[distance >= 120.0, "relative_risk"]
    assert not edge.empty
    assert edge.max() < 1.5
    assert set(after.loc[distance >= 120.0, "risk_level"]) == {"low"}
    assert ((after["probability_24h"] >= 0) & (after["probability_24h"] < 1)).all()
    assert ((after["probability_7d"] >= 0) & (after["probability_7d"] < 1)).all()


def test_another_aftershock_raises_the_rate_near_its_epicenter() -> None:
    main = _catalog([_event("m62", MAIN_TIME, 37.2, 37.0, 6.2)])
    both = _catalog(
        [
            _event("m62", MAIN_TIME, 37.2, 37.0, 6.2),
            _event("as", "2024-01-15T04:15:00Z", 37.45, 37.15, 5.2),
        ]
    )
    as_of = "2024-01-15T05:00:00Z"
    kwargs = {"as_of": as_of, "bounds": BOX, "resolution_deg": 0.05}
    main_only = score_grid(main, **kwargs)
    with_aftershock = score_grid(both, **kwargs)
    assert _nearest(with_aftershock, 37.45, 37.15)["total_rate"] > _nearest(main_only, 37.45, 37.15)["total_rate"]


def test_event_chunks_do_not_change_the_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog = validate_catalog(pd.read_csv(SCENARIO))
    kwargs = {"as_of": AFTER, "bounds": BOX, "resolution_deg": 0.2}
    full = score_grid(catalog, **kwargs)
    monkeypatch.setattr(engine_module, "EVENT_CHUNK", 1)
    split = score_grid(catalog, **kwargs)
    pd.testing.assert_frame_equal(full, split)


def test_fixture_hotspot_sits_on_the_mainshock_not_the_far_twin() -> None:
    catalog = validate_catalog(pd.read_csv(FIXTURE))
    grid = score_grid(
        catalog,
        as_of="2023-02-07T00:00:00Z",
        bounds=(35.0, 34.0, 41.0, 41.0),
        resolution_deg=0.25,
    )
    peak = grid.loc[grid["total_rate"].idxmax()]
    distance_main = equirectangular_km(peak["lat"], peak["lon"], 37.20, 37.00)
    distance_far = equirectangular_km(peak["lat"], peak["lon"], 40.50, 40.50)
    assert distance_main < distance_far
    assert _nearest(grid, 37.20, 37.00)["total_rate"] > _nearest(grid, 34.2, 35.2)["total_rate"]


def test_ml_adjustment_is_not_available_yet() -> None:
    catalog = _catalog([_event("m62", MAIN_TIME, 37.2, 37.0, 6.2)])
    with pytest.raises(NotImplementedError):
        score_grid(
            catalog,
            as_of=AFTER,
            bounds=BOX,
            use_ml_adjustment=True,
            params=RiskParams(),
        )
