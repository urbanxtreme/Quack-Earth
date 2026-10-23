# Quack-Earth risk engine

Short-term seismic risk for one grid. This folder is the AI/ML side. Backend fills the cache. Frontend reads the grid. Scoring is not implemented yet; Phase 0 is the file contract.

Run commands from `model/`.

```bash
python -m pytest tests/test_contract.py
```

```python
from quack_risk import load_catalog, load_signals

catalog = load_catalog("data/fixtures/catalog.csv")
signals = load_signals("data/fixtures/signals.json")
```

`load_catalog` accepts the fixture and raises `CatalogSchemaError` if `magnitude` or `time` is missing. `load_signals(None)` returns an empty table.

## Catalog

Backend writes `data/cache/catalog.csv`, or a GeoJSON `FeatureCollection` with the same fields. One row is one earthquake.

| column | required | notes |
| --- | --- | --- |
| id | yes | stable event id |
| time | yes | ISO-8601 UTC, or epoch seconds / milliseconds in GeoJSON |
| latitude | yes | degrees, -90 to 90 |
| longitude | yes | degrees, -180 to 180 |
| depth_km | yes | stored; the v1 rate does not use it |
| magnitude | yes | |
| mag_type | no | |
| source | no | `usgs` or `local`; omitted values become `usgs` |

GeoJSON uses `geometry.coordinates = [longitude, latitude, depth_km]` and properties `mag`, `time`, `magType`. Extra CSV columns are kept. Rows are returned sorted by time, timezone-aware UTC.

The committed fixture `data/fixtures/catalog.csv` is a stand-in until the cache exists:

| id | what it is |
| --- | --- |
| old-55 | M 5.5 on 2022-06-01 at the mainshock, for the long-term baseline |
| quiet-40 | M 4.0 on 2023-01-25, inside the 14-day window and away from the mainshock |
| main-65 | M 6.5 on 2023-02-06T01:17Z at 37.20°N, 37.00°E |
| far-65 | same magnitude and time as `main-65`, at 40.50°N, 40.50°E |
| as-52, as-46 | aftershocks on 2023-02-06, close to the mainshock |
| below-mc | M 3.2, below the default completeness magnitude 4.0 |
| as-41 | M 4.1 on 2023-02-07T01:17Z, after the demo `as_of` |

Demo `as_of` for this fixture is `2023-02-07T00:00:00Z`. Demo bounds are west 35, south 34, east 41, north 41.

## Local signals

Optional file `data/cache/signals.json`: a JSON list, not an object.

| field | required | notes |
| --- | --- | --- |
| id | yes | |
| time | yes | ISO-8601 UTC |
| latitude, longitude | yes | degrees |
| signal_type | yes | `accelerometer` or `report` |
| confidence | yes | 0 to 1 |
| equivalent_magnitude | no | filled in by the scorer when omitted |

`data/fixtures/signals.json` has one accelerometer hit near the mainshock at 2023-02-06T03:00Z, confidence 0.8, equivalent magnitude 3.9.

## Risk grid

Later phases write `outputs/grids/risk_grid.csv` and `.geojson` with these columns, in this order:

`lat, lon, baseline_rate, triggered_rate, total_rate, probability_24h, probability_7d, relative_risk, risk_level`

Rates are expected events per day in that cell at or above `M_c` (default 4.0). `risk_level` is `low` below 1.5, `moderate` below 3, `elevated` below 10, and `high` at 10 or above, using relative risk (`total_rate / baseline_rate`).

## Starting parameters

`RiskParams` in `quack_risk/config.py`:

| name | value | role |
| --- | --- | --- |
| k | 0.01 | productivity; Phase 3 may fit it |
| alpha | 0.9 | magnitude scaling; held fixed |
| c_days | 0.05 | Omori offset in days; Phase 3 may fit it |
| p | 1.1 | Omori exponent; Phase 3 may fit it |
| magnitude_threshold | 4.0 | completeness magnitude `M_c` |
| recent_window_days | 14 | events older than this do not trigger |
| kernel | gaussian | `powerlaw` is the alternate |

Fit bounds when Phase 3 runs: `k` above 0, `c_days` in `[0.001, 1]`, `p` in `[0.8, 1.5]`.

## What this phase does not do

No rate, no map, no plots, and no call to USGS. `data/cache/` is the drop zone for the backend file. Point `load_catalog` at it when the columns above are present.
