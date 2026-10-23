"""Phase 0 contract: the fixture loads, and a bad catalog is rejected."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quack_risk import CATALOG_COLUMNS, GRID_COLUMNS, RiskParams, load_catalog, load_signals
from quack_risk.config import DEMO_AS_OF, DEMO_BOUNDS, PARAM_BOUNDS
from quack_risk.schema import CatalogSchemaError, GridSpec, SignalSchemaError

FIXTURES = Path(__file__).resolve().parents[1] / "data" / "fixtures"
VALID_HEADER = "id,time,latitude,longitude,depth_km,magnitude,mag_type,source\n"
VALID_ROW = "e1,2023-02-06T01:17:00Z,37.2,37.0,10,6.5,mww,usgs\n"


def test_fixture_catalog_loads() -> None:
    catalog = load_catalog(FIXTURES / "catalog.csv")

    assert list(catalog.columns[: len(CATALOG_COLUMNS)]) == list(CATALOG_COLUMNS)
    assert len(catalog) == 8
    assert str(catalog["time"].dt.tz) == "UTC"
    assert list(catalog["time"].sort_values()) == list(catalog["time"])
    assert catalog.loc[catalog["id"] == "main-65", "magnitude"].iloc[0] == 6.5
    assert catalog.loc[catalog["id"] == "far-65", "magnitude"].iloc[0] == 6.5
    assert catalog.loc[catalog["id"] == "below-mc", "magnitude"].iloc[0] == 3.2
    assert set(catalog["source"]) == {"usgs"}


def test_fixture_signals_load() -> None:
    signals = load_signals(FIXTURES / "signals.json")

    assert len(signals) == 1
    row = signals.iloc[0]
    assert row["id"] == "sig-accel-1"
    assert row["signal_type"] == "accelerometer"
    assert row["confidence"] == 0.8
    assert row["equivalent_magnitude"] == 3.9
    assert str(signals["time"].dt.tz) == "UTC"


def test_missing_magnitude_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(
        "id,time,latitude,longitude,depth_km\n"
        "e1,2023-02-06T01:17:00Z,37.2,37.0,10\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogSchemaError, match="magnitude"):
        load_catalog(path)


def test_missing_time_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(
        "id,latitude,longitude,depth_km,magnitude\n"
        "e1,37.2,37.0,10,6.5\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogSchemaError, match="time"):
        load_catalog(path)


def test_blank_magnitude_value_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(VALID_HEADER + "e1,2023-02-06T01:17:00Z,37.2,37.0,10,,mww,usgs\n", encoding="utf-8")
    with pytest.raises(CatalogSchemaError, match="magnitude"):
        load_catalog(path)


def test_blank_time_value_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(VALID_HEADER + "e1,,37.2,37.0,10,6.5,mww,usgs\n", encoding="utf-8")
    with pytest.raises(CatalogSchemaError, match="time"):
        load_catalog(path)


def test_header_only_catalog_is_empty_and_valid(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(VALID_HEADER, encoding="utf-8")
    catalog = load_catalog(path)
    assert catalog.empty
    assert list(catalog.columns[: len(CATALOG_COLUMNS)]) == list(CATALOG_COLUMNS)


def test_optional_catalog_columns_are_filled(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(
        "id,time,latitude,longitude,depth_km,magnitude\n"
        "e1,2023-02-06T01:17:00Z,37.2,37.0,10,4.2\n",
        encoding="utf-8",
    )
    catalog = load_catalog(path)
    assert catalog.loc[0, "source"] == "usgs"
    assert pd.isna(catalog.loc[0, "mag_type"])


def test_geojson_catalog_loads(tmp_path: Path) -> None:
    path = tmp_path / "catalog.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "us100",
                        "geometry": {"type": "Point", "coordinates": [37.0, 37.2, 10.0]},
                        "properties": {
                            "mag": 6.5,
                            "time": 1675646220000,
                            "magType": "mww",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = load_catalog(path)
    assert catalog.loc[0, "id"] == "us100"
    assert catalog.loc[0, "latitude"] == 37.2
    assert catalog.loc[0, "longitude"] == 37.0
    assert catalog.loc[0, "magnitude"] == 6.5
    assert catalog.loc[0, "source"] == "usgs"
    assert str(catalog["time"].dt.tz) == "UTC"


def test_unknown_source_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catalog.csv"
    path.write_text(VALID_HEADER + VALID_ROW.replace(",usgs", ",twitter"), encoding="utf-8")
    with pytest.raises(CatalogSchemaError, match="source"):
        load_catalog(path)


def test_report_may_omit_equivalent_magnitude(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "sig-report-1",
                    "time": "2023-02-06T04:00:00Z",
                    "latitude": 36.5,
                    "longitude": 36.2,
                    "signal_type": "report",
                    "confidence": 0.4,
                }
            ]
        ),
        encoding="utf-8",
    )
    signals = load_signals(path)
    assert signals.loc[0, "signal_type"] == "report"
    assert pd.isna(signals.loc[0, "equivalent_magnitude"])


def test_empty_signal_list_is_valid(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text("[]", encoding="utf-8")
    signals = load_signals(path)
    assert signals.empty
    assert "confidence" in signals.columns
    assert load_signals(None).empty


def test_confidence_outside_unit_interval_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "sig-bad",
                    "time": "2023-02-06T04:00:00Z",
                    "latitude": 36.5,
                    "longitude": 36.2,
                    "signal_type": "accelerometer",
                    "confidence": 1.2,
                }
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(SignalSchemaError, match="confidence"):
        load_signals(path)


def test_signal_file_must_be_a_list(tmp_path: Path) -> None:
    path = tmp_path / "signals.json"
    path.write_text('{"id": "sig-bad"}', encoding="utf-8")
    with pytest.raises(SignalSchemaError, match="JSON list"):
        load_signals(path)


def test_grid_contract_and_default_parameters() -> None:
    assert GRID_COLUMNS == (
        "lat",
        "lon",
        "baseline_rate",
        "triggered_rate",
        "total_rate",
        "probability_24h",
        "probability_7d",
        "relative_risk",
        "risk_level",
    )
    params = RiskParams()
    assert params.alpha == 0.9
    assert params.p == 1.1
    assert params.c_days == 0.05
    assert params.k == 0.01
    assert params.magnitude_threshold == 4.0
    assert PARAM_BOUNDS["c_days"] == (0.001, 1.0)
    assert PARAM_BOUNDS["p"] == (0.8, 1.5)
    assert PARAM_BOUNDS["k"][0] > 0
    assert DEMO_BOUNDS == (35.0, 34.0, 41.0, 41.0)
    assert DEMO_AS_OF == "2023-02-07T00:00:00Z"
    grid = GridSpec(*DEMO_BOUNDS)
    assert grid.resolution_deg == 0.2
    with pytest.raises(ValueError):
        GridSpec(41.0, 34.0, 35.0, 41.0)
