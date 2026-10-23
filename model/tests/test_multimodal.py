"""Local accelerometer hits and resident reports raise the nearby rate only when corroborated."""

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


def _signal(
    signal_id: str,
    time: str,
    lat: float,
    lon: float,
    signal_type: str,
    confidence: float,
    magnitude: float | None,
) -> dict:
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


def _quake(time: str, lat: float, lon: float, magnitude: float) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "id": "q",
                "time": time,
                "latitude": lat,
                "longitude": lon,
                "depth_km": 10.0,
                "magnitude": magnitude,
                "mag_type": "ml",
                "source": "usgs",
            }
        ]
    )


def _nearest(grid: pd.DataFrame, lat: float, lon: float) -> pd.Series:
    distance = equirectangular_km(grid["lat"], grid["lon"], lat, lon)
    return grid.iloc[int(np.argmin(distance))]


def test_missing_magnitude_is_filled_from_confidence() -> None:
    frame = load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "accelerometer", 0.8, None)])
    catalog = _quake("2024-01-15T03:15:00Z", 37.2, 37.0, 5.0)
    triggers = signals_to_triggers(frame, as_of=pd.Timestamp(AS_OF), params=RiskParams(), catalog=catalog)
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


def test_lone_signal_on_a_quiet_catalog_adds_nothing() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    hit = load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.0, 37.0, "accelerometer", 1.0, 6.5)])
    report = load_signals_frame([_signal("r", "2024-01-15T03:30:00Z", 37.0, 37.0, "report", 1.0, 8.0)])
    plain = score_grid(empty, as_of=AS_OF, bounds=QUIET_BOX, resolution_deg=0.2)
    phone = score_grid(empty, as_of=AS_OF, bounds=QUIET_BOX, resolution_deg=0.2, local_signals=hit)
    typed = score_grid(empty, as_of=AS_OF, bounds=QUIET_BOX, resolution_deg=0.2, local_signals=report)
    pd.testing.assert_frame_equal(plain, phone)
    pd.testing.assert_frame_equal(plain, typed)


def test_repeated_device_does_not_become_a_cluster() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    copies = load_signals_frame(
        [
            _signal("same", "2024-01-15T03:30:00Z", 37.0, 37.0, "accelerometer", 1.0, 4.5),
            _signal("same", "2024-01-15T03:31:00Z", 37.01, 37.01, "accelerometer", 1.0, 4.5),
            _signal("same", "2024-01-15T03:32:00Z", 37.02, 37.0, "accelerometer", 1.0, 4.5),
        ]
    )
    plain = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2)
    scored = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2, local_signals=copies)
    pd.testing.assert_frame_equal(plain, scored)


def test_agreeing_phones_raise_the_nearby_cell_more_than_a_distant_one() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    phones = load_signals_frame(
        [
            _signal("a", "2024-01-15T03:30:00Z", 37.00, 37.00, "accelerometer", 1.0, 4.5),
            _signal("b", "2024-01-15T03:31:00Z", 37.02, 37.01, "accelerometer", 1.0, 4.5),
            _signal("c", "2024-01-15T03:32:00Z", 37.01, 37.02, "accelerometer", 1.0, 4.5),
        ]
    )
    grid = score_grid(empty, as_of=AS_OF, bounds=QUIET_BOX, resolution_deg=0.2, local_signals=phones)
    near = _nearest(grid, 37.0, 37.0)
    far = _nearest(grid, 37.0, 40.5)
    assert equirectangular_km(far["lat"], far["lon"], 37.0, 37.0) > 250.0
    assert near["triggered_rate"] > far["triggered_rate"]
    assert near["total_rate"] > far["total_rate"]


def test_two_phones_do_not_clear_the_agreement_bar() -> None:
    empty = pd.DataFrame(columns=list(CATALOG_COLUMNS))
    phones = load_signals_frame(
        [
            _signal("a", "2024-01-15T03:30:00Z", 37.00, 37.00, "accelerometer", 1.0, 4.5),
            _signal("b", "2024-01-15T03:31:00Z", 37.02, 37.01, "accelerometer", 1.0, 4.5),
        ]
    )
    plain = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2)
    scored = score_grid(empty, as_of=AS_OF, bounds=BOX, resolution_deg=0.2, local_signals=phones)
    pd.testing.assert_frame_equal(plain, scored)


def test_phone_beside_a_catalog_quake_is_one_capped_bump() -> None:
    catalog = _quake("2024-01-15T03:15:00Z", 37.2, 37.0, 6.2)
    claimed = load_signals_frame(
        [_signal(f"p{index}", "2024-01-15T03:30:00Z", 37.2 + 0.01 * index, 37.0, "accelerometer", 0.4 + 0.1 * index, 8.0) for index in range(5)]
    )
    triggers = signals_to_triggers(claimed, as_of=pd.Timestamp(AS_OF), params=RiskParams(), catalog=catalog)
    assert len(triggers) == 1
    assert triggers.loc[0, "magnitude"] == pytest.approx(4.5)
    assert triggers.loc[0, "trigger_weight"] == pytest.approx(0.8)

    kwargs = {"as_of": AS_OF, "bounds": BOX, "resolution_deg": 0.2}
    honest = score_grid(
        catalog,
        local_signals=load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "accelerometer", 1.0, 4.5)]),
        **kwargs,
    )
    inflated = score_grid(
        catalog,
        local_signals=load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "accelerometer", 1.0, 8.0)]),
        **kwargs,
    )
    pd.testing.assert_frame_equal(honest, inflated)


def test_report_beside_a_quake_adds_nothing_and_a_typed_magnitude_is_ignored() -> None:
    catalog = _quake("2024-01-15T03:15:00Z", 37.2, 37.0, 5.0)
    kwargs = {"as_of": AS_OF, "bounds": BOX, "resolution_deg": 0.2}
    base = score_grid(catalog, **kwargs)
    report = score_grid(
        catalog,
        local_signals=load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "report", 1.0, 8.0)]),
        **kwargs,
    )
    phone = score_grid(
        catalog,
        local_signals=load_signals_frame([_signal("s", "2024-01-15T03:30:00Z", 37.2, 37.0, "accelerometer", 0.8, 4.2)]),
        **kwargs,
    )
    pd.testing.assert_frame_equal(base, report)
    assert phone["triggered_rate"].sum() > base["triggered_rate"].sum()

    reports = [
        _signal(f"r{index}", "2024-01-15T03:30:00Z", 38.5, 39.5, "report", 1.0, 8.0)
        for index in range(10)
    ]
    triggers = signals_to_triggers(
        load_signals_frame(reports),
        as_of=pd.Timestamp(AS_OF),
        params=RiskParams(),
        catalog=catalog,
    )
    assert len(triggers) == 1
    assert triggers.loc[0, "magnitude"] == pytest.approx(4.5)
    assert float(triggers.loc[0, "magnitude"]) < 8.0


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
