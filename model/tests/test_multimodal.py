"""Local accelerometer hits and resident reports raise the nearby rate."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quack_risk.config import RiskParams
from quack_risk.engine import score_grid
from quack_risk.geo import equirectangular_km
from quack_risk.io import load_signals, validate_catalog
from quack_risk.multimodal import signals_to_triggers
from quack_risk.schema import CATALOG_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "data" / "fixtures" / "scenario_m62.csv"
BOX = (36.2, 36.2, 38.2, 38.2)
AS_OF = "2024-01-15T03:35:00Z"
QUIET_BOX = (36.0, 36.0, 41.0, 38.0)


def _signal(signal_id: str, time: str, lat: float, lon: float, signal_type: str, confidence: float, magnitude: float | None) -> dict:
    row = {
        "id": signal_id,
        "time": time,
        "latitude": lat,
        "longitude": lon,
        "signal_type": signal_type,
        "confidence": confidence,
    }
    if magnitude is not None:
        row["equivalent_magnitude"] = magnitude
    return row


def load_signals_frame(rows) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _nearest(grid: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    distance = equirectangular_km(grid["lat"], grid["lon"], lat, lon)
    return grid.iloc[int(np.argmin(distance))]


def test_missing_magnitude_is_filled_from_confidence() -> None:
    frame = load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "accelerometer", 0.8, None)])
    triggers = signals_to_triggers(frame, as_of=pd.Timestamp(AS_OF), params=RiskParams())
    assert len(triggers) == 1
    assert triggers.loc[0, "magnitude"] == pytest.approx(3.0 + 1.5 * 0.8)
    assert triggers.loc[0, "trigger_weight"] == pytest.approx(0.8)
    assert triggers.loc[0, "source"] == "local"


def test_confidence_zero_matches_the_catalog_only_grid() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    silent = load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "accelerometer", 0.0, 4.5)])
    plain = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2)
    with_zero = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2, local_signals=silent)
    pd.testing.assert_frame_equal(plain, with_zero)


def test_signal_raises_the_nearby_cell_more_than_a_distant_one() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    hit = load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.0, 37.0, "accelerometer", 1.0, 4.5)])
    grid = score_grid(empty, as_of=AS_OF, bounds=QUIET_BOX, resolution_deg=0.2, local_signals=hit)
    near = _nearest(grid, 37.0, 37.0)
    far = _nearest(grid, 37.0, 40.5)
    assert equirectangular_km(far["lat"], far["lon"], 37.0, 37.0) > 250.0
    assert near["triggered_rate"] > far["triggered_rate"]
    assert near["total_rate"] > far["total_rate"]


def test_report_adds_less_than_the_same_accelerometer_hit() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    kwargs = {"as_of": AS_OF, "bounds": BOX, "resolution_deg": 0.2}
    base = score_grid(empty, **kwargs)
    accel = score_grid(
        empty,
        local_signals=load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "accelerometer", 0.8, 4.2)]),
        **kwargs,
    )
    report = score_grid(
        empty,
        local_signals=load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "report", 0.8, 4.2)]),
        **kwargs,
    )
    accel_added = accel["triggered_rate"].to_numpy() - base["triggered_rate"].to_numpy()
    report_added = report["triggered_rate"].to_numpy() - base["triggered_rate"].to_numpy()
    assert accel_added.sum() > 0
    assert np.allclose(report_added, 0.3 * accel_added)


def test_future_signal_is_ignored() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    later = load_signals_frame([_signal("s", "2024-01-15T04:00:00Z", 37.2, 37.0, "accelerometer", 1.0, 5.0)])
    plain = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2)
    scored = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2, local_signals=later)
    pd.testing.assert_frame_equal(plain, scored)


def test_scenario_signal_raises_nearby_cells_and_leaves_the_far_edge() -> None:
    catalog = validate_catalog(pd.read_csv(SCENARIO))
    hit = load_signals(ROOT / "data" / "fixtures" / "scenario_signal.json")
    kwargs = {"as_of": AS_OF, "bounds": BOX, "resolution_deg": 0.1}
    before = score_grid(catalog, **kwargs)
    after = score_grid(catalog, local_signals=hit, **kwargs)

    pd.testing.assert_series_equal(before["baseline_rate"], after["baseline_rate"])
    near = _nearest(after, 37.45, 37.20)
    near_before = _nearest(before, 37.45, 37.20)
    assert near["total_rate"] > near_before["total_rate"]

    distance = equirectangular_km(after["lat"], after["lon"], 37.45, 37.20)
    far = distance >= 120.0
    assert far.any()
    assert np.allclose(after.loc[far, "total_rate"], before.loc[far, "total_rate"])
