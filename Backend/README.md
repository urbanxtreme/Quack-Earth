# Seismic Risk Anticipation API — Backend

Lightweight Flask API for short-term probabilistic seismic risk estimation (`quack-risk-etas-v1`). Designed for edge/offline operation with cached catalog data, multimodal citizen reports/sensors, and Civil Defense emergency decision support.

**Base URL (local):** `http://localhost:8000`  
*(All endpoints are also available with `/api`, `/api/v1`, and `/v1` prefixes, e.g. `http://localhost:8000/api/v1/risk`).*

---

## Run Locally

```powershell
cd Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The SQLite cache is created at `Backend/instance/earthquake_cache.db`. Set `EARTHQUAKE_DATABASE_PATH` to use a custom database path.

---

## Endpoints Overview

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/status` (or `/health`) | System health, offline/online mode, and cache metadata |
| `GET` | `/events` | Paginated recent earthquakes with time, mag, and geojson support |
| `GET` | `/events/<event_id>` | Detailed metadata for a single earthquake |
| `GET` | `/map/events` | High-performance GeoJSON Point FeatureCollection within bounding box |
| `POST` | `/local-event` | Ingest local observation with multimodal corroboration check |
| `POST` | `/refresh-catalog` (or `/sync`) | Fetch latest events from USGS ComCat (online only) |
| `GET` | `/risk` | Short-term seismic risk scores, 24h/7d probabilities & Civil Defense verdict |
| `GET` | `/risk/grid` | Risk calculation on a regular bounding box grid |
| `GET` | `/risk/heatmap` | GeoJSON Polygon FeatureCollection for direct map polygon rendering |
| `GET` | `/risk/verdict` | Civil Defense Situation Verdict and Emergency Guidance |
| `POST` | `/forecasts` | Aftershock hazard calculation triggered by a specific reference event |
| `GET` | `/model/params` (or `/risk/params`) | Retrieve active ETAS model parameters |
| `POST` | `/model/calibrate` (or `/risk/calibrate`) | MLE fitting of ETAS parameters against catalog |
| `GET` | `/scenarios` | List benchmark earthquake scenarios and drill presets |
| `GET` | `/scenarios/<scenario_id>` | Detailed metadata and sequence events for a scenario |

For full request/response schemas, field types, and mathematical formulas, see the comprehensive [API Documentation](../docs/api_documentation.md).

---

## Key Highlights & Features

### 1. Offline-First Operation
All endpoints (`/risk`, `/risk/grid`, `/risk/heatmap`, `/events`, `/scenarios`) function completely offline without internet connectivity, relying on the local SQLite catalog cache.

### 2. Civil Defense Verdict & Guidance
Endpoints `/risk`, `/risk/grid`, and `/risk/verdict` automatically generate:
- `verdict`: Plain-language situational report for field radios.
- `public_zone`: Operational zone (`usual`, `stay aware`, `limit work`, `priority`).
- `excavation_action`: SAR engineering directive (`continue`, `open-area checks`, `pause`).
- `guidance`: Structured sector-level breakdown for incident commanders.

### 3. Multimodal Corroboration Gate
Submissions to `POST /local-event` are cross-referenced against the local catalog and sensor cluster to evaluate corroboration status (`corroborated` vs `pending_cluster`).

### 4. Direct GeoJSON Support
- `/events?format=geojson`
- `/risk/grid?format=geojson`
- `/map/events` (Point FeatureCollection)
- `/risk/heatmap` (Polygon FeatureCollection)

---

## Running Tests

Execute the complete backend test suite:

```powershell
python -m pytest
```
