# Seismic Risk Anticipation API — Backend

Lightweight Flask API for short-term probabilistic seismic risk estimation (`omori-style-v1`). Designed for edge/offline operation with cached catalog data and local event inputs.

**Base URL (local):** `http://localhost:8000`

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

| Method | Endpoint              | Description                                      |
|--------|-----------------------|--------------------------------------------------|
| GET    | `/status`             | System health and cache status                   |
| GET    | `/risk`               | Calculate short-term risk scores for an area     |
| GET    | `/events`             | Retrieve recent earthquakes from cache           |
| POST   | `/local-event`        | Add a local event/report and update risk         |
| POST   | `/refresh-catalog`    | Download latest catalog from USGS (online only)  |
| GET    | `/risk/grid`          | Get risk values on a regular grid (for heatmap)  |

*(Note: Routes are also available under `/api/v1/` for compatibility).*

---

## 1. System Status (`GET /status`)

Returns operational status, online/offline mode, and cache metadata.

**Response 200:**
```json
{
  "status": "ok",
  "mode": "offline",
  "cached_events": 1247,
  "local_events_added": 2,
  "last_catalog_update": "2026-10-23T08:00:00Z",
  "model": "omori-style-v1"
}
```

---

## 2. Risk Calculation (`GET /risk`)

Calculates short-term seismic risk for a given location or area.

**Query Parameters:**
- `lat` (float, required): Center latitude (-90 to 90)
- `lon` (float, required): Center longitude (-180 to 180)
- `radius_km` (float, optional, default: 50.0): Search radius around center
- `time_window` (string, optional, default: `"24h"`): `"24h"` or `"7d"`
- `min_magnitude` (float, optional, default: 4.0): Minimum magnitude threshold

**Response 200:**
```json
{
  "time_window": "24h",
  "min_magnitude": 4.0,
  "center": { "lat": 34.05, "lon": -118.25 },
  "baseline_rate": 0.018,
  "zones": [
    {
      "lat": 34.05,
      "lon": -118.25,
      "risk_score": 0.76,
      "relative_to_baseline": 11.2,
      "expected_events": 0.21
    }
  ],
  "generated_at": "2026-10-23T14:32:00Z"
}
```

---

## 3. Recent Events (`GET /events`)

Returns recent earthquakes from the cached catalog and local reports.

**Query Parameters:**
- `hours` (int, default: 72): Look-back window in hours
- `min_magnitude` (float, default: 2.5): Minimum magnitude
- `limit` (int, default: 200): Maximum number of events returned

**Response 200:**
```json
{
  "count": 2,
  "events": [
    {
      "id": "us7000abcd",
      "time": "2026-10-23T10:15:00Z",
      "lat": 34.12,
      "lon": -118.31,
      "magnitude": 4.8,
      "depth_km": 12.4,
      "source": "usgs"
    },
    {
      "id": "local_001",
      "time": "2026-10-23T14:20:00Z",
      "lat": 34.05,
      "lon": -118.25,
      "magnitude": 5.1,
      "source": "user_report"
    }
  ]
}
```

---

## 4. Add Local Event (`POST /local-event`)

Adds a local observation or user report. The event is persisted and factored into subsequent risk calculations.

**Request Body:**
```json
{
  "lat": 34.05,
  "lon": -118.25,
  "magnitude": 5.2,
  "time": "2026-10-23T14:30:00Z",
  "source": "user_report",
  "note": "Strong shaking felt"
}
```

**Response 201:**
```json
{
  "status": "added",
  "event_id": "local_002",
  "message": "Local event added. Risk will include this event.",
  "nearby_risk_updated": true
}
```

---

## 5. Refresh Catalog (`POST /refresh-catalog`)

Downloads the latest catalog from USGS and updates the local cache. If offline, returns HTTP 503 while preserving cache.

**Request Body (optional):**
```json
{
  "min_magnitude": 2.5,
  "days_back": 30
}
```

**Response 200 (online):**
```json
{
  "status": "updated",
  "events_fetched": 342,
  "last_catalog_update": "2026-10-23T15:01:00Z"
}
```

**Response 503 (offline):**
```json
{
  "status": "failed",
  "message": "No internet connection. Using cached catalog."
}
```

---

## 6. Risk Grid (`GET /risk/grid`)

Calculates risk scores on a regular latitude/longitude grid for heatmaps.

**Query Parameters:**
- `min_lat` (float, required): Southern boundary
- `max_lat` (float, required): Northern boundary
- `min_lon` (float, required): Western boundary
- `max_lon` (float, required): Eastern boundary
- `resolution` (float, default: 0.1): Grid step in degrees
- `time_window` (string, default: `"24h"`): `"24h"` or `"7d"`
- `min_magnitude` (float, default: 4.0): Magnitude threshold

**Response 200:**
```json
{
  "time_window": "24h",
  "grid": [
    { "lat": 33.5, "lon": -119.0, "risk_score": 0.12 },
    { "lat": 33.5, "lon": -118.85, "risk_score": 0.31 },
    { "lat": 33.65, "lon": -118.7, "risk_score": 0.68 }
  ]
}
```

---

## Running Tests

```powershell
python -m pytest
```
