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

The same command with `--as-of 2024-01-15T03:10:00Z` is the map before that mainshock. A cached catalog from the backend is the same command with `--catalog data/cache/catalog.csv`. Run the command again when that file, or the signal file, gains a row. That rescore is the real-time update, and it works with the network down.

A measured quake in the catalog is the only magnitude the rate uses. One accelerometer counts only within 40 km and 24 hours of a magnitude 4 or larger catalog quake, and its magnitude is capped at 4.5. A resident report never uses a typed number. One report adds nothing. Phones and reports within 15 km and 10 minutes become one felt-shaking bump once their agreement score reaches 3 (three confident phones, or about ten confident reports). That bump is left out when a catalog quake already covers the same place. The same device id counts once.

```bash
python model/scripts/run_score.py
```

Tests still run from `model/`:

```bash
python -m pytest tests/test_contract.py tests/test_kernels.py tests/test_engine.py tests/test_multimodal.py tests/test_public.py tests/test_calibrate.py
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

Each recent earthquake adds `K × 10^(α (M − M_c)) / (Δt + c)^p`, spread by a magnitude-scaled Gaussian. An M 6.2 has a kernel width of about 20 km, so the bright part of the rate (at least 30% of the peak) covers roughly the surrounding 20–40 km. Farther cells stay above baseline, then fall back to it. Events after `as_of` are ignored. Events older than 14 days stay in the baseline. Local signals go through the corroboration gate above before they join that sum.

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
| equivalent_magnitude | no | ignored on a report. On a phone, capped at 4.5. Omitted values become `3.0 + 1.5 × confidence` |

`data/fixtures/signals.json` has one accelerometer hit near the mainshock at 2023-02-06T03:00Z, confidence 0.8, equivalent magnitude 3.9.

## Risk grid

`score_grid` returns these columns, in this order:

`lat, lon, baseline_rate, triggered_rate, total_rate, probability_24h, probability_7d, relative_risk, risk_level`

`scripts/run_score.py` writes that grid to CSV and GeoJSON and appends three public columns:

`probability_m5_24h, probability_m6_24h, public_zone`

The rate on the grid is the daily rate of magnitude 4 or larger (the completeness cutoff). The magnitude 5 and magnitude 6 chances use a Gutenberg–Richter b-value of 1.0: the rate at or above magnitude m is the magnitude-4 rate times `10^(-(m − 4))`, then `1 − exp(−rate × 1 day)`. That is a spread of chances, not one predicted magnitude.

`public_zone` comes from `probability_24h`:

| 24 h chance of magnitude 4 or larger | zone | excavation |
| --- | --- | --- |
| under 1% | usual | continue |
| 1% to under 5% | stay aware | open-area checks can continue |
| 5% to under 15% | limit work | pause excavation and debris removal |
| 15% or more | priority | search and rescue first; pause excavation |

The same run writes `<grid>_guidance.json` and `<grid>_verdict.txt` beside the CSV. The guidance file lists a few sectors, each with a direction from the peak and an action line. The verdict is a fixed template filled from the peak chance. It does not name a clock time or a single next magnitude. `--rewrite-verdict` asks SpaceXAI (`XAI_API_KEY`, model `grok-4.7`, `https://api.x.ai/v1`) to rephrase that template. If the key is missing, the call fails, or the reply changes a number, the template is kept. The outage path does not need this call.

Rates are expected events per day in that cell at or above `M_c` (default 4.0). `risk_level` is `low` below 1.5, `moderate` below 3, `elevated` below 10, and `high` at 10 or above, using relative risk (`total_rate / baseline_rate`). Color the map from `total_rate` or `probability_24h`. After a mainshock the relative risk stays above 10 well past the bright core, because the long-term baseline is small. The bright core is the cells whose `total_rate` is at least 30% of the peak. Brief residents and rescue leads from `public_zone`, not from `risk_level`.

`probability_24h` is the chance of at least one magnitude 4 or larger earthquake in that cell during the next 24 hours. It is not a clock time, and it is not one predicted magnitude. `probability_m5_24h` and `probability_m6_24h` are the same chance for magnitude 5 and magnitude 6.

## Handoff

`score_grid` and the column order above are frozen. The map reads the CSV. This folder does not draw the map.

These two grids are the 7 February 2023 sequence, about 24 hours after the magnitude 7.8. The second adds one phone about 25 km north of that epicenter, at 37.45°N, 37.01°E, so the nearby cells can rise while the network is down. Both commands use fitted `K`, `c`, and `p` when `data/cache/params.json` is present.

```bash
python model/scripts/run_score.py --catalog data/cache/catalog.csv --as-of 2023-02-07T00:00:00Z --bounds 35 34 41 41 --resolution 0.2 --out outputs/grids/demo_20230207.csv
python model/scripts/run_score.py --catalog data/cache/catalog.csv --signals data/fixtures/handoff_signal.json --as-of 2023-02-07T00:00:00Z --bounds 35 34 41 41 --resolution 0.2 --out outputs/grids/demo_20230207_signal.csv
python model/scripts/run_eval.py
```

The map should read `outputs/grids/demo_20230207.csv` (or the signal file beside it). The columns are the same ones as `risk_grid.csv`. `demo_20230207_guidance.json` and `demo_20230207_verdict.txt` are the plain-language note for the same run.

This engine is for the days after a large earthquake that is already in the catalog. It does not warn of a spontaneous mainshock far from recent activity. A lower magnitude cutoff, or a catalog that is missing earthquakes, changes the baseline and the chance.

## What stays with the other roles

The live USGS poller and the map stay outside this folder. Backend can replace `data/cache/catalog.csv` with the same columns. Run the score command again when that file, or the signal file, changes.

## Starting parameters

`RiskParams` in `quack_risk/config.py`:

| name | value | role |
| --- | --- | --- |
| k | 0.01 | productivity; replaced by `data/cache/params.json` when that file exists |
| alpha | 0.9 | magnitude scaling; held fixed |
| c_days | 0.05 | Omori offset in days; replaced by the fitted file when it exists |
| p | 1.1 | Omori exponent; replaced by the fitted file when it exists |
| magnitude_threshold | 4.0 | completeness magnitude `M_c` |
| recent_window_days | 14 | events older than this do not trigger |
| kernel | gaussian | `powerlaw` is the alternate |

Fit bounds: `k` above 0, `c_days` in `[0.001, 1]`, `p` in `[0.8, 1.5]`. Alpha is not fitted.

## Fitted parameters and plots

The fixture is too small to fit. Download the regional catalog once, or let the backend drop the same file later:

```bash
python model/scripts/bootstrap_cache.py
python model/scripts/run_calibrate.py
python model/scripts/run_eval.py
```

`bootstrap_cache.py` writes `data/cache/catalog.csv` for the demo box, magnitude 4 and above, from 2018-01-01 through 2023-02-20. `run_calibrate.py` fits `K`, `c`, and `p` on the 10 days after the largest event and writes `data/cache/params.json`. The next `run_score.py` uses that file when it is present. `--defaults` keeps the built-in values, which is how the M 6.2 scenario numbers stay fixed.

`run_eval.py` writes four figures in `outputs/plots/`: `omori_decay.png`, `risk_snapshot_24h.png`, `capture_curve.png`, and `likelihood_bars.png`, plus `metrics.json`. The logistic residual stays off.


