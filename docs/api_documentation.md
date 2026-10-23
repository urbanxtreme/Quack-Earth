# Seismic Risk Anticipation API — Documentation

**Version:** 1.0  
**Base URL (local):** `http://localhost:8000`  
*(All endpoints are also available with the `/api/v1` prefix, e.g. `http://localhost:8000/api/v1/status`)*  
**Description:** Lightweight Flask API for short-term probabilistic seismic risk estimation (`omori-style-v1`). Designed for edge and offline operation with a cached SQLite catalog, automatic synchronization with the ML model drop zone, and local user/sensor event inputs.

---

## Architecture & Edge/Offline Design

- **Offline-First:** All risk calculations (`/risk` and `/risk/grid`) and cached event lookups (`/events`) operate 100% locally using the cached SQLite database and local reports without requiring internet access.
- **Model Cache Sync:** The backend automatically exports and updates `model/data/cache/catalog.csv` and `model/data/cache/signals.json` whenever events or local reports are stored.
- **CORS Enabled:** Cross-Origin Resource Sharing is enabled for all endpoints to allow direct consumption by the frontend (e.g. running on `http://localhost:5173`). Preflight `OPTIONS` requests are fully supported.
- **GeoJSON Ready:** In addition to standard JSON payloads, endpoints like `/events` and `/risk/grid` support `format=geojson` for direct mapping with Leaflet, Mapbox, or MapLibre.

---

## Authentication

No authentication is required for prototype development.

---

## Endpoints Overview

| Method | Endpoint              | Description                                             |
|--------|-----------------------|---------------------------------------------------------|
| GET    | `/status`             | System operational status, mode, and cache metadata     |
| GET    | `/risk`               | Calculate short-term risk scores for a circular area    |
| GET    | `/events`             | Retrieve recent earthquakes from the local cache        |
| POST   | `/local-event`        | Add a local event/report and update risk evaluations    |
| POST   | `/refresh-catalog`    | Download latest catalog from USGS (online only)         |
| GET    | `/risk/grid`          | Get risk values on a regular grid (for heatmaps)        |
| POST   | `/forecasts`          | Compute aftershock hazard triggered by a specific event |

---

## 1. System Status

### `GET /status` (or `GET /health`)

Returns current operational status, whether the system is online or in offline mode, and cache counts.

#### Response `200 OK`
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

| Field                 | Type    | Description                                             |
|-----------------------|---------|---------------------------------------------------------|
| `status`              | string  | `"ok"` or `"error"`                                     |
| `mode`                | string  | `"online"` if internet is reachable, otherwise `"offline"` |
| `cached_events`       | integer | Number of verified catalog events in the local cache    |
| `local_events_added`  | integer | Number of user/local reports added                      |
| `last_catalog_update` | string  | ISO-8601 UTC timestamp of last USGS catalog sync       |
| `model`               | string  | Identifier of the risk model (`"omori-style-v1"`)       |

---

## 2. Risk Calculation

### `GET /risk`

Calculates short-term seismic risk for a given geographic area using historical baseline activity and recent Omori-style aftershock triggering.

#### Query Parameters

| Parameter       | Type   | Required | Default | Description                                   |
|-----------------|--------|----------|---------|-----------------------------------------------|
| `lat`           | float  | **Yes**  | —       | Center latitude (-90.0 to 90.0)               |
| `lon`           | float  | **Yes**  | —       | Center longitude (-180.0 to 180.0)            |
| `radius_km`     | float  | No       | `50.0`  | Radius around center in kilometers            |
| `time_window`   | string | No       | `"24h"` | Forecasting window: `"24h"` or `"7d"`         |
| `min_magnitude` | float  | No       | `4.0`   | Minimum magnitude threshold ($M_c$)           |

#### Example Request
```http
GET /risk?lat=34.05&lon=-118.25&radius_km=40&time_window=24h&min_magnitude=4.0
```

#### Response `200 OK`
```json
{
  "time_window": "24h",
  "min_magnitude": 4.0,
  "center": {
    "lat": 34.05,
    "lon": -118.25
  },
  "baseline_rate": 0.018,
  "zones": [
    {
      "lat": 34.05,
      "lon": -118.25,
      "risk_score": 0.76,
      "relative_to_baseline": 11.2,
      "expected_events": 0.21,
      "risk_level": "high"
    }
  ],
  "generated_at": "2026-10-23T14:32:00Z"
}
```

| Field                  | Type    | Description                                                     |
|------------------------|---------|-----------------------------------------------------------------|
| `baseline_rate`        | float   | Background rate (expected events/day at or above $M_c$)         |
| `zones[].risk_score`   | float   | Continuous normalized risk index in $[0.0, 1.0]$                |
| `zones[].relative_to_baseline` | float | Ratio of total expected rate to baseline rate ($\lambda / \lambda_0$) |
| `zones[].expected_events` | float | Expected number of events in the specified time window          |
| `zones[].risk_level`   | string  | Hazard classification: `"low"`, `"moderate"`, `"elevated"`, `"high"` |

---

## 3. Recent Events

### `GET /events`

Returns recent earthquakes from the cached catalog and any local user reports.

#### Query Parameters

| Parameter       | Type   | Required | Default  | Description                                        |
|-----------------|--------|----------|----------|----------------------------------------------------|
| `hours`         | int    | No       | `72`     | Look-back window in hours from current time        |
| `min_magnitude` | float  | No       | `2.5`    | Minimum magnitude filter                           |
| `limit`         | int    | No       | `200`    | Maximum number of events returned                  |
| `start`         | string | No       | —        | Optional ISO-8601 UTC start time (overrides hours) |
| `end`           | string | No       | —        | Optional ISO-8601 UTC end time                     |
| `format`        | string | No       | `"json"` | Output format: `"json"` or `"geojson"`             |

#### Example Request (Standard JSON)
```http
GET /events?hours=48&min_magnitude=3.5
```

#### Response `200 OK` (Standard JSON)
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
      "source": "user_report",
      "note": "Felt violent shaking"
    }
  ]
}
```

#### Example Request (GeoJSON Format)
```http
GET /events?hours=48&format=geojson
```

#### Response `200 OK` (GeoJSON)
```json
{
  "type": "FeatureCollection",
  "count": 2,
  "features": [
    {
      "type": "Feature",
      "id": "us7000abcd",
      "geometry": {
        "type": "Point",
        "coordinates": [-118.31, 34.12, 12.4]
      },
      "properties": {
        "mag": 4.8,
        "time": "2026-10-23T10:15:00Z",
        "source": "usgs"
      }
    }
  ]
}
```

---

## 4. Add Local Event

### `POST /local-event`

Adds a local observation, resident report, or accelerometer detection. The event is stored in the local SQLite database, synced to the model signals cache, and immediately incorporated into subsequent risk calculations.

#### Request Body

```json
{
  "lat": 34.05,
  "lon": -118.25,
  "magnitude": 5.2,
  "time": "2026-10-23T14:30:00Z",
  "source": "user_report",
  "note": "Strong shaking felt downtown"
}
```

| Field         | Type   | Required | Description                                                  |
|---------------|--------|----------|--------------------------------------------------------------|
| `lat`         | float  | **Yes**  | Latitude (-90.0 to 90.0)                                     |
| `lon`         | float  | **Yes**  | Longitude (-180.0 to 180.0)                                  |
| `magnitude`   | float  | **Yes**  | Estimated or reported magnitude                              |
| `time`        | string | No       | ISO-8601 UTC timestamp (defaults to current server UTC time) |
| `source`      | string | No       | `"user_report"` (default), `"accelerometer"`, etc.           |
| `note`        | string | No       | Free-text observation or damage note                         |

#### Response `201 Created`
```json
{
  "status": "added",
  "event_id": "local_002",
  "message": "Local event added. Risk will include this event.",
  "nearby_risk_updated": true
}
```

---

## 5. Refresh Catalog

### `POST /refresh-catalog` (or `POST /sync`)

Attempts to download the latest earthquake catalog from the USGS Earthquake Hazards Program API and updates the local SQLite cache and ML drop zone.

#### Request Body (Optional)

```json
{
  "min_magnitude": 2.5,
  "days_back": 30
}
```

| Field           | Type  | Required | Default | Description                         |
|-----------------|-------|----------|---------|-------------------------------------|
| `min_magnitude` | float | No       | `2.5`   | Minimum magnitude to fetch          |
| `days_back`     | int   | No       | `30`    | Number of historical days to fetch  |

#### Response `200 OK` (Online Success)
```json
{
  "status": "updated",
  "events_fetched": 342,
  "last_catalog_update": "2026-10-23T15:01:00Z"
}
```

#### Response `503 Service Unavailable` (Offline Fallback)
When no internet connection is available or the remote USGS endpoint is unreachable, existing cached data is preserved safely.
```json
{
  "status": "failed",
  "message": "No internet connection. Using cached catalog."
}
```

---

## 6. Risk Grid (Heatmap)

### `GET /risk/grid`

Computes seismic risk values across a regular latitude/longitude bounding box grid. Uses `quack_risk` model scoring when available, with vectorized NumPy calculation as fallback.

#### Query Parameters

| Parameter       | Type   | Required | Default  | Description                                       |
|-----------------|--------|----------|----------|---------------------------------------------------|
| `min_lat`       | float  | **Yes**  | —        | Southern boundary latitude                        |
| `max_lat`       | float  | **Yes**  | —        | Northern boundary latitude                        |
| `min_lon`       | float  | **Yes**  | —        | Western boundary longitude                        |
| `max_lon`       | float  | **Yes**  | —        | Eastern boundary longitude                        |
| `resolution`    | float  | No       | `0.1`    | Grid spacing in degrees                           |
| `time_window`   | string | No       | `"24h"`  | Prediction window: `"24h"` or `"7d"`              |
| `min_magnitude` | float  | No       | `4.0`    | Threshold magnitude $M_c$                         |
| `format`        | string | No       | `"json"` | Output format: `"json"` or `"geojson"`            |

#### Example Request (Standard JSON)
```http
GET /risk/grid?min_lat=33.5&max_lat=34.5&min_lon=-119.0&max_lon=-117.5&resolution=0.15&time_window=24h
```

#### Response `200 OK` (Standard JSON)
```json
{
  "time_window": "24h",
  "grid": [
    {
      "lat": 33.5,
      "lon": -119.0,
      "risk_score": 0.12,
      "risk_level": "low",
      "relative_risk": 1.2
    },
    {
      "lat": 33.5,
      "lon": -118.85,
      "risk_score": 0.31,
      "risk_level": "moderate",
      "relative_risk": 2.4
    },
    {
      "lat": 33.65,
      "lon": -118.7,
      "risk_score": 0.68,
      "risk_level": "elevated",
      "relative_risk": 7.1
    }
  ]
}
```

#### Example Request (GeoJSON Format)
```http
GET /risk/grid?min_lat=33.5&max_lat=34.5&min_lon=-119.0&max_lon=-117.5&resolution=0.15&format=geojson
```

#### Response `200 OK` (GeoJSON)
```json
{
  "type": "FeatureCollection",
  "time_window": "24h",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [-119.0, 33.5]
      },
      "properties": {
        "risk_score": 0.12,
        "risk_level": "low",
        "relative_risk": 1.2
      }
    }
  ]
}
```

---

## 7. Event-Triggered Aftershock Forecast

### `POST /forecasts`

Calculates localized aftershock probability and expected event rates explicitly triggered by a specific reference earthquake in the local cache, computed via the `ForecastService`.

#### Request Body

```json
{
  "trigger_event_id": "us7000abcd",
  "target": {
    "latitude": 34.05,
    "longitude": -118.25,
    "radius_km": 50.0
  },
  "window_hours": 24,
  "minimum_magnitude": 4.0
}
```

| Field                  | Type    | Required | Allowed Values / Constraints                  | Description                                                |
|------------------------|---------|----------|-----------------------------------------------|------------------------------------------------------------|
| `trigger_event_id`     | string  | **Yes**  | Non-empty string                              | ID of the reference earthquake present in local cache       |
| `target.latitude`      | float   | **Yes**  | `[-90.0, 90.0]`                               | Center latitude of the forecast assessment zone            |
| `target.longitude`     | float   | **Yes**  | `[-180.0, 180.0]`                             | Center longitude of the forecast assessment zone           |
| `target.radius_km`     | float   | **Yes**  | `(0.0, 500.0]`                                | Radius in kilometers around target coordinates             |
| `window_hours`         | integer | **Yes**  | `24` or `168`                                 | Forecast horizon: `24` (1 day) or `168` (7 days)           |
| `minimum_magnitude`    | float   | **Yes**  | `[-1.0, 10.0]`                                | Threshold magnitude $M_c$ for anticipated events           |

#### Response `200 OK`

```json
{
  "target": {
    "latitude": 34.05,
    "longitude": -118.25,
    "radius_km": 50.0
  },
  "window_hours": 24,
  "minimum_magnitude": 4.0,
  "expected_event_count": 0.42,
  "probability_at_least_one": 0.34,
  "baseline_rate_per_day": 0.018,
  "relative_activity_score": 6.8,
  "data_as_of": "2026-10-23T14:30:00Z",
  "model": "omori-style-v1",
  "assumptions": [
    "Spatial kernel decays exponentially with distance d0 = 40 km",
    "Productivity follows Gutenberg-Richter scaling with alpha = 0.9",
    "Temporal rate decay follows modified Omori p = 1.1, c = 0.05d"
  ],
  "limitations": [
    "Assumes isotropic circular spatial distribution",
    "Requires non-empty catalog synchronization for baseline determination"
  ]
}
```

| Field                       | Type    | Description                                                         |
|-----------------------------|---------|---------------------------------------------------------------------|
| `expected_event_count`      | float   | Integrated expected number of events $\ge M_c$ in the window        |
| `probability_at_least_one`  | float   | Poisson probability $P(N \ge 1) = 1 - \exp(-\lambda_{\text{total}})$ |
| `baseline_rate_per_day`     | float   | Background daily event rate for the targeted circle                 |
| `relative_activity_score`   | float   | Ratio of forecast rate to baseline rate                             |
| `data_as_of`                | string  | ISO-8601 UTC timestamp of latest catalog event considered           |
| `assumptions`               | array   | List of mathematical and physical model assumptions                 |
| `limitations`               | array   | Operational boundary limitations of the forecast output             |

---

## 8. Planned Edge Endpoints (Frontend Feature Roadmap)

To achieve 100% autonomous edge and offline operation in the frontend UI, the following complementary endpoints are planned:

### 8.1 Offline Place Geocoding (`GET /geocode`)
* **Endpoint:** `GET /geocode?q=<place_name>&limit=5`
* **Description:** Resolves place names to `(lat, lon)` using a bundled SQLite gazetteer when disconnected from external geocoding providers (Nominatim/OSM).
* **Sample Response:**
  ```json
  [
    { "name": "Tokyo, Japan", "lat": 35.6762, "lon": 139.6503, "country": "JP" },
    { "name": "San Francisco, USA", "lat": 37.7749, "lon": -122.4194, "country": "US" }
  ]
  ```

### 8.2 Regional Alert Feed (`GET /risk/alerts`)
* **Endpoint:** `GET /risk/alerts?min_risk=0.7&limit=10`
* **Description:** Returns ranked geographic clusters currently experiencing elevated or critical seismic risk scores without requiring manual coordinate inputs.
* **Sample Response:**
  ```json
  {
    "count": 1,
    "alerts": [
      {
        "region": "Greater Tokyo Area",
        "center": { "lat": 35.68, "lon": 139.70 },
        "peak_risk_score": 0.88,
        "hazard_category": "critical",
        "relative_baseline": 14.2
      }
    ]
  }
  ```

### 8.3 Local Report Management (`GET /local-events`, `DELETE /local-event/{id}`)
* **Endpoints:**
  * `GET /local-events`: Retrieves a list of user/sensor reports submitted via `POST /local-event`.
  * `DELETE /local-event/<event_id>`: Removes an erroneous or obsolete local report from the database and triggers catalog cache recalculation.

### 8.4 Single Event Metadata (`GET /events/{event_id}`)
* **Endpoint:** `GET /events/<event_id>`
* **Description:** Retrieves detailed telemetry for a single earthquake, including recording stations, azimuthal gap, depth uncertainty, and linked aftershocks.

---

### Model Identifier: `omori-style-v1`

1. **Triggered Aftershock Rate (Modified Omori Law):**
   $$\lambda_{\text{trig}}(t, \mathbf{x}) = \sum_{i} K \cdot 10^{\alpha(M_i - M_c)} \cdot \frac{1}{(t - t_i + c)^p} \cdot \exp\left(-\frac{\|\mathbf{x} - \mathbf{x}_i\|}{d_0}\right)$$
   - Productivity: $K = 0.01$
   - Magnitude scaling: $\alpha = 0.9$
   - Omori offset: $c = 0.05\text{ days}$
   - Omori decay: $p = 1.1$
   - Look-back window: $14.0\text{ days}$

2. **Baseline Rate:**
   $$\lambda_0 = \frac{N_{\text{baseline}}(M \ge M_c)}{30\text{ days}}$$

3. **Relative Activity:**
   $$R = \frac{\lambda_0 + \lambda_{\text{trig}}}{\max(\lambda_0, 0.01)}$$

4. **Risk Levels & Score Mapping:**
   | Level       | Relative Risk ($R$) | Description                       | Color Indicator |
   |-------------|---------------------|-----------------------------------|-----------------|
   | `low`       | $R < 1.5$           | At or near background activity    | Green           |
   | `moderate`  | $1.5 \le R < 3.0$   | Mild aftershock activity          | Yellow          |
   | `elevated`  | $3.0 \le R < 10.0$  | Significant aftershock sequence   | Orange          |
   | `high`      | $R \ge 10.0$        | Intense sequence near mainshock   | Red             |

   Continuous `risk_score` is mapped to $[0.0, 1.0]$ using a calibrated response curve:
   $$\text{risk\_score} = 1.0 - \frac{1.0}{1.0 + (R / 3.5)^{1.2}}$$

---

## Error Handling

Standard error responses return an `error` key containing a human-readable explanation:

```json
{
  "error": "lat and lon are required",
  "message": "lat and lon are required"
}
```

### HTTP Status Codes

| Code | Status                 | Typical Scenario                                           |
|------|------------------------|------------------------------------------------------------|
| 400  | Bad Request            | Missing query parameters or invalid coordinate numbers     |
| 404  | Not Found              | `trigger_event_id` does not exist in the local cache       |
| 422  | Unprocessable Entity   | Coordinates out of range, or invalid window / magnitude   |
| 500  | Internal Server Error  | Risk or forecast engine calculation failure                |
| 503  | Service Unavailable    | Catalog sync requires internet, or cache empty before sync |
