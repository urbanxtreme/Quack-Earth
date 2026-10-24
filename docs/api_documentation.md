# Seismic Risk Anticipation API — Complete Documentation

**Version:** 2.0  
**Base URL (local):** `http://localhost:8000`  
*(All endpoints are available at root `/`, with `/api`, `/api/v1`, and `/v1` prefixes, e.g. `http://localhost:8000/status`, `http://localhost:8000/api/status`, `http://localhost:8000/api/v1/status`, and `http://localhost:8000/v1/status`)*  
**Active Risk Model:** `quack-risk-etas-v1` (Omori-style Epidemic-Type Aftershock Sequence model with multimodal corroboration and Civil Defense operational guidance).

---

## Architecture & Edge/Offline Design

- **Offline-First:** All risk calculations (`/risk`, `/risk/grid`, `/risk/heatmap`, `/risk/verdict`) and cached event lookups (`/events`, `/events/<id>`, `/map/events`) operate 100% locally using an embedded SQLite database (`Backend/instance/earthquake_cache.db`) without requiring internet access.
- **Model Cache Sync:** The backend automatically exports and synchronizes `model/data/cache/catalog.csv` and `model/data/cache/signals.json` whenever events or local reports are stored.
- **Multimodal Corroboration:** Ingests citizen reports and accelerometer telemetry via `/local-event`, passing them through a corroboration gate before admission into the active ETAS trigger sequence.
- **CORS Enabled:** Cross-Origin Resource Sharing is enabled for all endpoints and origins, supporting modern frontends (e.g., React/Vite running on `http://localhost:5173`). Preflight `OPTIONS` requests are fully handled.
- **GeoJSON Ready:** Native GeoJSON `FeatureCollection` outputs are provided for map bounding box queries (`/map/events`), event feeds (`/events?format=geojson`), risk point grids (`/risk/grid?format=geojson`), and polygon raster cells (`/risk/heatmap`).
- **Emergency Action Guidance:** Automatically maps continuous probabilistic risk to Civil Defense Operational Zones (`usual`, `stay aware`, `limit work`, `priority`) and Sector Excavation Directives (`continue`, `open-area checks`, `pause`).

---

## Authentication

No authentication is required for prototype and edge operational deployment.

---

## Endpoints Index

| Method | Endpoint | Description |
|---|---|---|
| **System & Health** | | |
| `GET` | `/status` (or `/health`) | System health, operational mode (`online`/`offline`), event counts, and active model |
| **Earthquake Events & Ingestion** | | |
| `GET` | `/events` | Paginated and filtered earthquake event list (JSON or GeoJSON) |
| `GET` | `/events/<event_id>` | Detailed telemetry for a specific earthquake by ID |
| `GET` | `/map/events` | High-performance GeoJSON Point FeatureCollection within bounding box |
| `POST` | `/local-event` | Submit citizen report or accelerometer detection with corroboration evaluation |
| `POST` | `/refresh-catalog` (or `/sync`) | Fetch latest events from USGS Earthquake Hazards API (online only) |
| **Risk & Heatmap Analysis** | | |
| `GET` | `/risk` | Point-and-radius seismic risk evaluation, 24h/7d probabilities, and Civil Defense verdict |
| `GET` | `/risk/grid` | Regular bounding-box grid calculation for risk tables and point heatmaps |
| `GET` | `/risk/heatmap` | GeoJSON Polygon FeatureCollection with computed cell boundaries for map rendering |
| `GET` | `/risk/verdict` | Civil Defense Situation Verdict and Sector Commander Action Guidance |
| **Forecasting & Modeling** | | |
| `POST` | `/forecasts` | Event-triggered aftershock sequence forecast from a specific reference earthquake |
| `GET` | `/model/params` (or `/risk/params`) | Retrieve active ETAS model parameters and decay constants |
| `POST` | `/model/calibrate` (or `/risk/calibrate`) | Fit ETAS model parameters against the catalog sequence via Maximum Likelihood |
| **Scenarios & Benchmarks** | | |
| `GET` | `/scenarios` | List benchmark earthquake scenarios and civil defense drills |
| `GET` | `/scenarios/<scenario_id>` | Detailed metadata and sequenced events for a specific scenario |

---

## 1. System Status & Health

### `GET /status` (or `GET /health`)

Returns current operational health, network connectivity status, cached catalog statistics, and model metadata.

#### URL Aliases
- `GET /status`
- `GET /health`
- `GET /api/status`
- `GET /api/v1/status`
- `GET /v1/status`

#### Response `200 OK`
```json
{
  "status": "ok",
  "mode": "offline",
  "cached_events": 1247,
  "event_count": 1247,
  "local_events_added": 3,
  "last_catalog_update": "2026-10-24T08:00:00Z",
  "source": "USGS ComCat",
  "model": "quack-risk-etas-v1",
  "model_name": "quack-risk-etas-v1"
}
```

| Field | Type | Description |
|---|---|---|
| `status` | string | System status: `"ok"` or `"error"` |
| `mode` | string | `"online"` if USGS network is reachable; otherwise `"offline"` |
| `cached_events` | integer | Total verified catalog events stored in the SQLite cache |
| `event_count` | integer | Total event count in repository (alias of `cached_events`) |
| `local_events_added` | integer | Number of citizen reports and sensor telemetry entries recorded |
| `last_catalog_update` | string / null | ISO-8601 UTC timestamp of last successful catalog synchronization |
| `source` | string | Primary earthquake catalog authority (`"USGS ComCat"`) |
| `model` / `model_name` | string | Identifier of the active calculation engine (`"quack-risk-etas-v1"`) |

---

## 2. Earthquake Events & Ingestion

### `GET /events`

Retrieves earthquakes from the local cache and local reports, ordered chronologically. If the requested query returns zero results and internet is available, the backend automatically triggers an on-demand synchronization with USGS.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `hours` | integer | No | `72` | Look-back window in hours (must be $> 0$) |
| `min_magnitude` | float | No | `2.5` | Minimum magnitude filter |
| `limit` | integer | No | `200` | Maximum number of events returned (must be $> 0$) |
| `start` | string | No | — | Optional ISO-8601 UTC timestamp (overrides `hours`) |
| `end` | string | No | — | Optional ISO-8601 UTC timestamp |
| `format` | string | No | `"json"` | Output format: `"json"` or `"geojson"` |

#### Response `200 OK` (Standard JSON)
```json
{
  "count": 2,
  "events": [
    {
      "id": "us7000m8v5",
      "time": "2026-10-24T06:12:00Z",
      "lat": 37.174,
      "lon": 37.032,
      "magnitude": 7.8,
      "magnitude_type": "mww",
      "depth_km": 17.9,
      "source": "usgs",
      "review_status": "reviewed",
      "place": "26 km E of Nurdağı, Turkey",
      "note": null,
      "corroboration": {
        "status": "usgs_verified",
        "confidence": 1.0,
        "station_count": 82,
        "label": "USGS ComCat Network"
      }
    },
    {
      "id": "local_001",
      "time": "2026-10-24T06:45:00Z",
      "lat": 37.22,
      "lon": 37.08,
      "magnitude": 5.4,
      "magnitude_type": "report",
      "depth_km": null,
      "source": "user_report",
      "review_status": "user_report",
      "place": "Local observation (37.22°, 37.08°)",
      "note": "Severe wall cracks and ceiling collapse",
      "corroboration": {
        "status": "sensor_corroborated",
        "confidence": 0.94,
        "station_count": 14,
        "label": "Multimodal Sensor Clustered"
      }
    }
  ]
}
```

#### Response `200 OK` (GeoJSON Format: `format=geojson`)
```json
{
  "type": "FeatureCollection",
  "count": 2,
  "features": [
    {
      "type": "Feature",
      "id": "us7000m8v5",
      "geometry": {
        "type": "Point",
        "coordinates": [37.032, 37.174, 17.9]
      },
      "properties": {
        "mag": 7.8,
        "time": "2026-10-24T06:12:00Z",
        "source": "usgs",
        "note": null,
        "place": "26 km E of Nurdağı, Turkey"
      }
    }
  ]
}
```

---

### `GET /events/<event_id>`

Retrieves detailed metadata for a single earthquake by its unique identifier.

#### Path Parameters
- `event_id` (string, required): e.g. `"us7000m8v5"` or `"local_001"`

#### Response `200 OK`
```json
{
  "id": "us7000m8v5",
  "time": "2026-10-24T06:12:00Z",
  "lat": 37.174,
  "lon": 37.032,
  "magnitude": 7.8,
  "magnitude_type": "mww",
  "depth_km": 17.9,
  "source": "usgs",
  "review_status": "reviewed",
  "place": "26 km E of Nurdağı, Turkey",
  "note": null,
  "corroboration": {
    "status": "usgs_verified",
    "confidence": 1.0,
    "station_count": 82
  }
}
```

#### Response `404 Not Found`
```json
{
  "error": "Event not found",
  "message": "Event not found",
  "code": "event_not_found"
}
```

---

### `GET /map/events`

Direct GeoJSON endpoint tailored for mapping frameworks (Leaflet, MapLibre, Mapbox). Performs rapid spatial bounding box filtering and returns a `FeatureCollection`.

#### Query Parameters

| Parameter | Type | Required | Default | Range / Constraints |
|---|---|---|---|---|
| `min_lat` | float | **Yes** | — | `[-90.0, 90.0]`, must be $< \text{max\_lat}$ |
| `max_lat` | float | **Yes** | — | `[-90.0, 90.0]` |
| `min_lon` | float | **Yes** | — | `[-180.0, 180.0]`, must be $< \text{max\_lon}$ |
| `max_lon` | float | **Yes** | — | `[-180.0, 180.0]` |
| `hours` | integer | No | `168` | `[1, 8784]` (up to 366 days) |
| `min_magnitude` | float | No | `0.0` | `[-1.0, 10.0]` |
| `limit` | integer | No | `1000` | `[1, 5000]` |

#### Response `200 OK`
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "us7000m8v5",
      "geometry": {
        "type": "Point",
        "coordinates": [37.032, 37.174]
      },
      "properties": {
        "id": "us7000m8v5",
        "time": "2026-10-24T06:12:00Z",
        "lat": 37.174,
        "lon": 37.032,
        "magnitude": 7.8,
        "magnitude_type": "mww",
        "depth_km": 17.9,
        "source": "usgs",
        "place": "26 km E of Nurdağı, Turkey"
      }
    }
  ],
  "count": 1,
  "source": "USGS ComCat",
  "data_as_of": "2026-10-24T08:00:00Z",
  "bounds": {
    "min_lat": 35.0,
    "max_lat": 39.0,
    "min_lon": 35.0,
    "max_lon": 39.0
  }
}
```

---

### `POST /local-event`

Injects a citizen report, local sensor observation, or edge accelerometer detection into the local SQLite database and model cache (`model/data/cache/signals.json`). Evaluates the report through multimodal spatial-temporal corroboration before admitting it into triggered aftershock calculations.

#### Request Body

```json
{
  "lat": 37.22,
  "lon": 37.08,
  "magnitude": 5.4,
  "time": "2026-10-24T06:45:00Z",
  "source": "user_report",
  "signal_type": "report",
  "note": "Severe shaking, structural cracking observed",
  "place": "Kahramanmaraş Sector 2"
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `lat` | float | **Yes** | — | Latitude `[-90.0, 90.0]` |
| `lon` | float | **Yes** | — | Longitude `[-180.0, 180.0]` |
| `magnitude` | float | **Yes** | — | Estimated magnitude `[-1.0, 10.0]` |
| `time` | string | No | Current UTC | ISO-8601 UTC timestamp |
| `source` | string | No | `"user_report"` | Source identifier (`"user_report"`, `"accelerometer"`, etc.) |
| `signal_type` | string | No | `"report"` | `"report"` or `"accelerometer"` |
| `note` | string | No | `null` | Observation text or telemetry notes |
| `place` | string | No | Auto-generated | Descriptive place label |

#### Response `201 Created`
```json
{
  "status": "added",
  "event_id": "local_003",
  "message": "Local event added. Risk will include this event.",
  "nearby_risk_updated": true,
  "corroboration": {
    "admitted": true,
    "status": "corroborated",
    "trigger_weight": 0.85,
    "reason": "Corroborated by report evidence and admitted into risk engine."
  }
}
```

*Note: If single/isolated, `admitted` is `false`, `status` is `"pending_cluster"`, and `message` states `"Local event recorded. Awaiting corroboration cluster."`*

---

### `POST /refresh-catalog` (or `POST /sync`)

Pulls recent earthquake records directly from the USGS Earthquake Hazards API and updates the local SQLite store and ML drop zone.

#### Request Body (Optional)
```json
{
  "min_magnitude": 2.5,
  "days_back": 30
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `min_magnitude` | float | No | `2.5` | Minimum magnitude to fetch (also accepts `minimum_magnitude`) |
| `days_back` | integer | No | `30` | Historical look-back window `[1, 366]` |

#### Responses
- **`200 OK` (Online Success):**
  ```json
  {
    "status": "updated",
    "events_fetched": 342,
    "last_catalog_update": "2026-10-24T08:00:00Z"
  }
  ```
- **`503 Service Unavailable` (Offline Safe Fallback):**
  ```json
  {
    "status": "failed",
    "message": "No internet connection. Using cached catalog."
  }
  ```
- **`502 Bad Gateway`:** USGS remote service returned an HTTP or protocol error.

---

## 3. Probabilistic Risk & Operational Guidance

### `GET /risk`

Calculates localized short-term seismic hazard for a target location. Evaluates background Poisson baseline rates ($\lambda_0$) and triggered Omori-style aftershock sequences ($\lambda_{\text{trig}}$), and produces Civil Defense Situation Verdicts and Excavation Directives.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `lat` | float | **Yes** | — | Center latitude `[-90.0, 90.0]` |
| `lon` | float | **Yes** | — | Center longitude `[-180.0, 180.0]` |
| `radius_km` | float | No | `50.0` | Search radius in kilometers ($> 0$) |
| `time_window` | string | No | `"24h"` | Prediction window: `"24h"` or `"7d"` |
| `min_magnitude` | float | No | `4.0` | Threshold magnitude $M_c$ `[-1.0, 10.0]` |

#### Response `200 OK`
```json
{
  "time_window": "24h",
  "min_magnitude": 4.0,
  "center": {
    "lat": 37.175,
    "lon": 37.025
  },
  "baseline_rate": 0.024,
  "zones": [
    {
      "lat": 37.175,
      "lon": 37.025,
      "risk_score": 0.88,
      "relative_to_baseline": 14.8,
      "expected_events": 0.42,
      "risk_level": "high",
      "probability_24h": 0.3429,
      "probability_7d": 0.9412,
      "public_zone": "priority"
    }
  ],
  "verdict": "In the next 24 hours the highest cell has about a 34.3% chance of a magnitude 4 or larger earthquake. Search and rescue first. Pause excavation and stop debris removal in this sector. A field commander decides any evacuation.",
  "guidance": {
    "as_of": "2026-10-24T08:00:00Z",
    "peak": {
      "lat": 37.175,
      "lon": 37.025,
      "probability_24h": 0.3429,
      "public_zone": "priority"
    },
    "limit": "This is the aftershock chance for the next 24 hours. A field commander decides evacuation.",
    "sectors": [
      {
        "lat": 37.175,
        "lon": 37.025,
        "probability_24h": 0.3429,
        "public_zone": "priority",
        "direction": "at the peak",
        "distance_km": 0.0,
        "place": "at the peak",
        "action": "Search and rescue first. Pause excavation and stop debris removal in this sector.",
        "excavation": "pause",
        "cells": 1
      }
    ]
  },
  "public_zone": "priority",
  "excavation_action": "pause",
  "generated_at": "2026-10-24T08:00:00Z"
}
```

| Field | Type | Description |
|---|---|---|
| `baseline_rate` | float | Background daily Poisson rate ($M \ge M_c$) |
| `zones[].risk_score` | float | Calibrated continuous risk score in `[0.0, 1.0]` |
| `zones[].relative_to_baseline` | float | Activity boost ratio $R = \lambda_{\text{total}} / \lambda_0$ |
| `zones[].expected_events` | float | Expected number of events in specified `time_window` |
| `zones[].risk_level` | string | Classification: `"low"`, `"moderate"`, `"elevated"`, `"high"` |
| `zones[].probability_24h` | float | Probability of $\ge 1$ earthquake in 24 hours ($P = 1 - e^{-\lambda}$) |
| `zones[].probability_7d` | float | Probability of $\ge 1$ earthquake in 7 days |
| `public_zone` | string | Civil defense zone: `"usual"`, `"stay aware"`, `"limit work"`, `"priority"` |
| `excavation_action` | string | SAR engineering directive: `"continue"`, `"open-area checks"`, `"pause"` |
| `verdict` | string | Natural language situational verdict for commanders and field radios |
| `guidance` | object | Structured breakdown of peak sector coordinates and operational directives |

---

### `GET /risk/grid`

Computes seismic risk values across a regular latitude/longitude bounding box grid. Automatically invokes the `quack_risk.engine.score_grid` ETAS implementation when available, and smoothly falls back to a vectorized NumPy implementation.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `min_lat` | float | **Yes** | — | Southern boundary `[-90.0, 90.0]` |
| `max_lat` | float | **Yes** | — | Northern boundary `[-90.0, 90.0]` |
| `min_lon` | float | **Yes** | — | Western boundary `[-180.0, 180.0]` |
| `max_lon` | float | **Yes** | — | Eastern boundary `[-180.0, 180.0]` |
| `resolution` | float | No | `0.1` | Step size in degrees ($> 0$, max 5000 cells) |
| `time_window` | string | No | `"24h"` | Prediction window: `"24h"` or `"7d"` |
| `min_magnitude` | float | No | `4.0` | Threshold magnitude $M_c$ |
| `format` | string | No | `"json"` | `"json"` or `"geojson"` |

#### Response `200 OK` (Standard JSON)
```json
{
  "time_window": "24h",
  "grid": [
    {
      "lat": 37.0,
      "lon": 37.0,
      "risk_score": 0.72,
      "risk_level": "elevated",
      "relative_risk": 8.4,
      "total_rate": 0.082,
      "probability_24h": 0.0787,
      "probability_7d": 0.4371
    }
  ],
  "verdict": "In the next 24 hours the highest cell has about a 15.2% chance...",
  "guidance": { ... },
  "public_zone": "priority",
  "excavation_action": "pause"
}
```

#### Response `200 OK` (GeoJSON: `format=geojson`)
Returns a `FeatureCollection` where each grid point is a `Point` Feature with cell properties (`risk_score`, `risk_level`, `relative_risk`).

---

### `GET /risk/heatmap`

Generates ready-to-render GeoJSON polygons for each cell in the bounding box. Perfect for displaying colored heat layers on MapLibre, Mapbox, or Leaflet without custom client-side grid calculations.

#### Query Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `min_lat` | float | **Yes** | — | Southern boundary latitude |
| `max_lat` | float | **Yes** | — | Northern boundary latitude |
| `min_lon` | float | **Yes** | — | Western boundary longitude |
| `max_lon` | float | **Yes** | — | Eastern boundary longitude |
| `resolution` | float | No | `0.1` | Grid spacing in degrees |
| `time_window` | string | No | `"24h"` | Prediction window: `"24h"` or `"7d"` |
| `min_magnitude` | float | No | `4.0` | Threshold magnitude $M_c$ |

#### Response `200 OK` (GeoJSON FeatureCollection of Polygons)
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Polygon",
        "coordinates": [
          [
            [36.95, 36.95],
            [37.05, 36.95],
            [37.05, 37.05],
            [36.95, 37.05],
            [36.95, 36.95]
          ]
        ]
      },
      "properties": {
        "lat": 37.0,
        "lon": 37.0,
        "risk_score": 0.72,
        "value": 0.72,
        "risk_level": "elevated",
        "relative_risk": 8.4,
        "probability_24h": 0.0787,
        "probability_7d": 0.4371
      }
    }
  ],
  "count": 1,
  "time_window": "24h",
  "min_magnitude": 4.0,
  "resolution": 0.1,
  "bounds": {
    "min_lat": 36.9,
    "max_lat": 37.1,
    "min_lon": 36.9,
    "max_lon": 37.1
  }
}
```

---

### `GET /risk/verdict`

Dedicated lightweight endpoint that generates Civil Defense Operational Verdicts, Public Zone Classifications, and Excavation Instructions. Supports either a point coordinate query or a bounding box query.

#### Query Parameters
- **Point Mode:** `lat`, `lon`, `min_magnitude` (optional, default `4.0`), `time_window` (optional, default `"24h"`)
- **Bounding Box Mode:** `min_lat`, `max_lat`, `min_lon`, `max_lon`, `resolution` (optional, default `0.2`), `min_magnitude`, `time_window`

#### Response `200 OK`
```json
{
  "verdict": "In the next 24 hours the highest cell has about a 28.5% chance of a magnitude 4 or larger earthquake. Search and rescue first. Pause excavation and stop debris removal in this sector. A field commander decides any evacuation.",
  "guidance": {
    "as_of": "2026-10-24T08:00:00Z",
    "peak": {
      "lat": 37.175,
      "lon": 37.025,
      "probability_24h": 0.285,
      "public_zone": "priority"
    },
    "limit": "This is the aftershock chance for the next 24 hours. A field commander decides evacuation.",
    "sectors": [
      {
        "lat": 37.175,
        "lon": 37.025,
        "probability_24h": 0.285,
        "public_zone": "priority",
        "direction": "at the peak",
        "distance_km": 0.0,
        "place": "at the peak",
        "action": "Search and rescue first. Pause excavation and stop debris removal in this sector.",
        "excavation": "pause",
        "cells": 1
      }
    ]
  },
  "public_zone": "priority",
  "excavation_action": "pause",
  "probability_24h": 0.285,
  "as_of": "2026-10-24T08:00:00Z",
  "center": {
    "lat": 37.175,
    "lon": 37.025
  }
}
```

---

## 4. Event-Triggered Aftershock Forecast

### `POST /forecasts`

Computes explicit aftershock rates and Poisson exceedance probabilities triggered by a specific reference event in the local catalog using `ForecastService`.

#### Request Body

```json
{
  "trigger_event_id": "us7000m8v5",
  "target": {
    "latitude": 37.175,
    "longitude": 37.025,
    "radius_km": 50.0
  },
  "window_hours": 24,
  "minimum_magnitude": 4.0
}
```

| Field | Type | Required | Allowed Values / Constraints | Description |
|---|---|---|---|---|
| `trigger_event_id` | string | **Yes** | Non-empty string | ID of the reference event stored in local cache |
| `target.latitude` | float | **Yes** | `[-90.0, 90.0]` | Center latitude of assessment circle |
| `target.longitude` | float | **Yes** | `[-180.0, 180.0]` | Center longitude of assessment circle |
| `target.radius_km` | float | **Yes** | `(0.0, 500.0]` | Radius in kilometers |
| `window_hours` | integer | **Yes** | `24` or `168` | Horizon: `24` (1 day) or `168` (7 days) |
| `minimum_magnitude` | float | **Yes** | `[-1.0, 10.0]` | Minimum threshold magnitude $M_c$ |

#### Response `200 OK`
```json
{
  "target": {
    "latitude": 37.175,
    "longitude": 37.025,
    "radius_km": 50.0
  },
  "window_hours": 24,
  "minimum_magnitude": 4.0,
  "expected_event_count": 0.58,
  "expected_events": 0.58,
  "probability_at_least_one": 0.4402,
  "probability": 0.4402,
  "baseline_rate_per_day": 0.024,
  "baseline_event_count": 3,
  "recent_qualifying_event_count": 8,
  "relative_activity_score": 15.2,
  "data_as_of": "2026-10-24T08:00:00Z",
  "model": "quack-risk-etas-v1",
  "model_name": "quack-risk-etas-v1",
  "assumptions": [
    "Spatial kernel decays with physical rupture width scaling d(M) and Gaussian/powerlaw width",
    "Productivity follows Gutenberg-Richter scaling with alpha = 0.95 and b = 1.0",
    "Temporal rate decay follows modified Omori law (p = 1.1, c = 0.05d)"
  ],
  "limitations": [
    "Assumes isotropic spatial decay within rupture kernel",
    "Requires initialized catalog for background rate determination"
  ]
}
```

---

## 5. Model Parameters & MLE Calibration

### `GET /model/params` (or `GET /risk/params`)

Returns the current ETAS decay parameters, productivity scaling factor, and kernel configuration.

#### Response `200 OK`
```json
{
  "model_name": "quack-risk-etas-v1",
  "params": {
    "k": 0.015,
    "c_days": 0.05,
    "p": 1.1,
    "alpha": 0.95,
    "magnitude_threshold": 4.0,
    "recent_window_days": 14.0,
    "kernel": "powerlaw"
  }
}
```

---

### `POST /model/calibrate` (or `POST /risk/calibrate`)

Fits Omori ETAS parameters against recorded earthquakes using Maximum Likelihood Estimation (MLE), saving the resulting fitted parameters to `model/data/cache/params.json` and reloading the active risk service.

#### Request Body (Optional)
```json
{
  "min_magnitude": 4.0,
  "n_days": 10,
  "maxiter": 15,
  "min_lat": 35.0,
  "max_lat": 39.0,
  "min_lon": 35.0,
  "max_lon": 39.0,
  "resolution": 0.2
}
```

#### Response `200 OK`
```json
{
  "status": "calibrated",
  "model_name": "quack-risk-etas-v1",
  "fitted_params": {
    "k": 0.018241,
    "c_days": 0.048123,
    "p": 1.120451,
    "alpha": 0.941209,
    "magnitude_threshold": 4.0
  },
  "log_likelihood": -142.31,
  "baseline_log_likelihood": -188.45,
  "mainshock_origin": "2023-02-06T01:17:34Z",
  "n_days": 10,
  "n_observed": 48,
  "message": "Omori ETAS parameters successfully calibrated against catalog."
}
```

---

## 6. Earthquake Scenarios & Emergency Drills

### `GET /scenarios`

Lists pre-configured real-world and synthetic earthquake sequences for testing, demonstration, training drills, and edge verification.

#### Response `200 OK`
```json
{
  "count": 4,
  "scenarios": [
    {
      "id": "live_usgs",
      "name": "Live USGS Global Network",
      "short_name": "Live USGS",
      "tag": "REALTIME FEED",
      "tag_color": "emerald",
      "center": { "lat": 20.0, "lon": 0.0 },
      "zoom": 2.0,
      "description": "Streaming real-time global seismic feeds directly from the USGS Earthquake Hazards Program.",
      "incident_date": "Live Streaming",
      "peak_magnitude": 0.0,
      "event_count": 0
    },
    {
      "id": "turkey_2023",
      "name": "2023 Kahramanmaraş Earthquake Doublet (Turkey)",
      "short_name": "Turkey M7.8 Doublet",
      "tag": "CIVIL DEFENSE PRIORITY",
      "tag_color": "red",
      "center": { "lat": 37.175, "lon": 37.025 },
      "zoom": 7.8,
      "description": "Catastrophic strike-slip rupture sequence along the East Anatolian Fault with extreme aftershock rates.",
      "incident_date": "2023-02-06",
      "peak_magnitude": 7.8,
      "event_count": 7
    },
    {
      "id": "tokyo_bay",
      "name": "Tokyo Bay Fault Swarm Scenario (Japan)",
      "short_name": "Tokyo Urban Drill",
      "tag": "URBAN DEFENSE DRILL",
      "tag_color": "amber",
      "center": { "lat": 35.65, "lon": 139.75 },
      "zoom": 9.2,
      "description": "Simulated shallow fault rupture directly beneath Tokyo Bay testing emergency evacuation protocols and bridge checks.",
      "incident_date": "2026-10-24",
      "peak_magnitude": 7.0,
      "event_count": 4
    },
    {
      "id": "ridgecrest_2019",
      "name": "2019 Ridgecrest Sequence (San Andreas / ECSZ)",
      "short_name": "Ridgecrest M7.1",
      "tag": "CONJUGATE FAULT RUPTURE",
      "tag_color": "purple",
      "center": { "lat": 35.77, "lon": -117.59 },
      "zoom": 8.5,
      "description": "Foreshock-mainshock sequence in the Eastern California Shear Zone triggering conjugate orthogonal faults.",
      "incident_date": "2019-07-06",
      "peak_magnitude": 7.1,
      "event_count": 4
    }
  ]
}
```

---

### `GET /scenarios/<scenario_id>`

Retrieves full metadata and all sequenced events for a specific scenario.

#### Path Parameters
- `scenario_id` (string, required): `"live_usgs"`, `"turkey_2023"`, `"tokyo_bay"`, or `"ridgecrest_2019"`

#### Response `200 OK`
```json
{
  "id": "turkey_2023",
  "name": "2023 Kahramanmaraş Earthquake Doublet (Turkey)",
  "short_name": "Turkey M7.8 Doublet",
  "tag": "CIVIL DEFENSE PRIORITY",
  "tag_color": "red",
  "center": { "lat": 37.175, "lon": 37.025 },
  "zoom": 7.8,
  "description": "Catastrophic strike-slip rupture sequence along the East Anatolian Fault with extreme aftershock rates.",
  "incident_date": "2023-02-06",
  "peak_magnitude": 7.8,
  "events": [
    {
      "id": "turkey-main-1",
      "time": "2023-02-06T01:17:34Z",
      "lat": 37.174,
      "lon": 37.032,
      "magnitude": 7.8,
      "depth_km": 17.9,
      "source": "usgs",
      "place": "26 km E of Nurdağı, Turkey",
      "corroboration": {
        "status": "usgs_verified",
        "label": "USGS ComCat Network",
        "confidence": 1.0,
        "station_count": 82
      }
    },
    {
      "id": "turkey-main-2",
      "time": "2023-02-06T10:24:49Z",
      "lat": 38.024,
      "lon": 37.203,
      "magnitude": 7.5,
      "depth_km": 10.0,
      "source": "usgs",
      "place": "4 km SSE of Ekinözü, Turkey",
      "corroboration": {
        "status": "usgs_verified",
        "label": "USGS ComCat Network",
        "confidence": 1.0,
        "station_count": 76
      }
    }
  ]
}
```

---

## 7. Mathematical Formulation & Civil Defense Rules

### Active Model: `quack-risk-etas-v1`

1. **Triggered Aftershock Rate (Modified Omori Law with Spatial Kernel):**
   $$\lambda_{\text{trig}}(t, \mathbf{x}) = \sum_{i} K \cdot 10^{\alpha(M_i - M_c)} \cdot \frac{1}{(t - t_i + c)^p} \cdot K_{\text{spatial}}(\|\mathbf{x} - \mathbf{x}_i\|, M_i)$$
   - Productivity: $K \approx 0.015$ (calibrated via MLE)
   - Magnitude scaling: $\alpha \approx 0.95$
   - Omori offset time: $c \approx 0.05\text{ days}$
   - Omori temporal decay power: $p \approx 1.10$
   - Look-back sequence window: $14.0\text{ days}$

2. **Baseline Background Rate:**
   $$\lambda_0 = \frac{N_{\text{baseline}}(M \ge M_c)}{30\text{ days}}$$

3. **Relative Activity Ratio ($R$):**
   $$R = \frac{\lambda_0 + \lambda_{\text{trig}}}{\max(\lambda_0, 0.01)}$$

4. **Risk Level Classification:**
   | Level | Relative Activity Ratio ($R$) | Operational Description |
   |---|---|---|
   | `low` | $R < 1.5$ | Background baseline rate; no anomalous clustering |
   | `moderate` | $1.5 \le R < 3.0$ | Mild triggering; localized elevated awareness |
   | `elevated` | $3.0 \le R < 10.0$ | Significant aftershock sequence; active cluster |
   | `high` | $R \ge 10.0$ | Severe sequence; rupture zone proximity |

5. **Civil Defense Public Zones & Excavation Directives:**
   | 24h Exceedance Probability | Public Zone | Sector Excavation Action | Commander Action Directive |
   |---|---|---|---|
   | $P_{24h} \ge 0.15$ | `priority` | `pause` | Search and rescue first. Pause excavation and stop debris removal in this sector. |
   | $0.05 \le P_{24h} < 0.15$ | `limit work` | `pause` | Pause excavation and debris removal. Stay out of damaged buildings. |
   | $0.01 \le P_{24h} < 0.05$ | `stay aware` | `open-area checks` | Open-area checks can continue. This chance alone does not call for a wide evacuation. |
   | $P_{24h} < 0.01$ | `usual` | `continue` | No extra short-term action follows from this chance alone. |

6. **Poisson Exceedance Probability:**
   $$P(N \ge 1 \text{ in } \Delta t) = 1 - \exp\left(-\lambda_{\text{total}} \cdot \Delta t\right)$$

---

## 8. Error Handling & HTTP Status Codes

Error payloads adhere to a consistent JSON structure with `error`, `message`, and optional error `code`:

```json
{
  "error": "lat and lon are required",
  "message": "lat and lon are required",
  "code": "invalid_parameters"
}
```

### HTTP Status Code Reference

| Code | Status | Scenario |
|---|---|---|
| `200` | OK | Successful GET or operational POST |
| `201` | Created | Local event successfully ingested into SQLite store |
| `400` | Bad Request | Missing required parameters, invalid JSON, or unparseable query numbers |
| `404` | Not Found | Route, event ID, or scenario ID does not exist |
| `405` | Method Not Allowed | Method not supported on endpoint |
| `422` | Unprocessable Entity | Coordinates out of valid range ($[-90, 90]$, $[-180, 180]$), bounds unordered, or window not `24h`/`7d` |
| `500` | Internal Server Error | Risk engine computation or unexpected runtime failure |
| `502` | Bad Gateway | USGS upstream network connection or HTTP error |
| `503` | Service Unavailable | Remote USGS unreachable in offline mode, or cache empty before initial sync |
