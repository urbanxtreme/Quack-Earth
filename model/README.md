# Quack-Earth risk engine

Short-term seismic risk for one grid. This folder is the AI/ML side. Backend fills the cache. Frontend reads the grid. The scorer reads a catalog file and writes the grid. It does not call the network.

Run this from the repo root (`Quack-Earth`):

```bash
python model/scripts/run_score.py --catalog data/fixtures/scenario_m62.csv --as-of 2024-01-15T03:35:00Z --bounds 36.2 36.2 38.2 38.2 --resolution 0.05 --out outputs/grids/scenario_m62.csv
```

That is the outage scenario: an M 6.2 at 03:15 UTC, scored 20 minutes later, while the network is down. Add a phone accelerometer hit at 37.45°N, 37.20°E with:

```bash
python model/scripts/run_score.py --catalog data/fixtures/scenario_m62.csv --signals data/fixtures/scenario_signal.json --as-of 2024-01-15T03:35:00Z --bounds 36.2 36.2 38.2 38.2 --resolution 0.05 --out outputs/grids/scenario_m62_signal.csv
```

The same command with `--as-of 2024-01-15T03:10:00Z` is the map before that mainshock. A cached catalog from the backend is the same command with `--catalog data/cache/catalog.csv`. An accelerometer weight is its confidence. A resident report counts as confidence times 0.3. A missing magnitude becomes `3.0 + 1.5 × confidence`.

```bash
python model/scripts/run_score.py
```

Tests still run from `model/`:

```bash
python -m pytest tests/test_contract.py tests/test_kernels.py tests/test_engine.py tests/test_multimodal.py
```

The default command scores `data/fixtures/catalog.csv` at `2023-02-07T00:00:00Z` over west 35, south 34, east 41, north 41 and writes `outputs/grids/risk_grid.csv` plus `risk_grid.geojson`.

```python
from quack_risk import load_catalog, score_grid

catalog = load_catalog("data/fixtures/scenario_m62.csv")
grid = score_grid(
    catalog,
    as_of="2024-01-15T03:35:00Z",
    bounds=(36.2, 36.2, 38.2, 38.2),
    resolution_deg=0.05,
)
```

Each recent earthquake adds `K × 10^(α (M − M_c)) / (Δt + c)^p`, spread by a magnitude-scaled Gaussian. An M 6.2 has a kernel width of about 20 km, so the bright part of the rate (at least 30% of the peak) covers roughly the surrounding 20–40 km. Farther cells stay above baseline, then fall back to it. Events after `as_of` are ignored. Events older than 14 days stay in the baseline. Local accelerometer reports are accepted on `score_grid` and are not applied yet.

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

Rates are expected events per day in that cell at or above `M_c` (default 4.0). `risk_level` is `low` below 1.5, `moderate` below 3, `elevated` below 10, and `high` at 10 or above, using relative risk (`total_rate / baseline_rate`). Color the map from `total_rate` or `probability_24h`. After a mainshock the relative risk stays above 10 well past the bright core, because the long-term baseline is small. The bright core is the cells whose `total_rate` is at least 30% of the peak.

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

## What is not in this phase

No USGS download, no plots, and no map. `data/cache/` is the drop zone for the backend catalog. Point `--catalog` at it when the columns above are present. Local signals go in `--signals`.
