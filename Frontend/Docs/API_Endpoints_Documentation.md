# Seismic Risk Anticipation API — Endpoints Documentation

**Version:** 1.0  
**Base URL (local):** `http://localhost:8000`  
**Description:** Lightweight API for short-term probabilistic seismic risk estimation. Designed for edge/offline operation with cached catalog data and local event inputs.

---

## Authentication
No authentication required for the hackathon prototype.

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
| POST   | `/forecasts`          | Compute aftershock hazard triggered by an event  |

---

## 1. System Status

### `GET /status`

Returns current operational status, whether the system is in offline mode, and basic cache information.

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

| Field                | Type    | Description                              |
|----------------------|---------|------------------------------------------|
| status               | string  | `"ok"` or `"error"`                      |
| mode                 | string  | `"online"` or `"offline"`                |
| cached_events        | integer | Number of events in the local catalog    |
| local_events_added   | integer | Number of user/local reports added       |
| last_catalog_update  | string  | ISO timestamp of last USGS fetch         |
| model                | string  | Identifier of the risk model in use      |

---

## 2. Risk Calculation

### `GET /risk`

Calculates short-term seismic risk for a location or area.

**Query Parameters:**

| Parameter       | Type   | Required | Default | Description                              |
|-----------------|--------|----------|---------|------------------------------------------|
| lat             | float  | No       | —       | Center latitude                          |
| lon             | float  | No       | —       | Center longitude                         |
| radius_km       | float  | No       | 50      | Radius around center (km)                |
| time_window     | string | No       | `24h`   | `24h` or `7d`                            |
| min_magnitude   | float  | No       | 4.0     | Minimum magnitude threshold              |

**Example Request:**
```
GET /risk?lat=34.05&lon=-118.25&radius_km=40&time_window=24h&min_magnitude=4.0
```

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

## 3. Recent Events

### `GET /events`

Returns recent earthquakes from the cached catalog (and any local events).

**Query Parameters:**

| Parameter       | Type   | Required | Default | Description                    |
|-----------------|--------|----------|---------|--------------------------------|
| hours           | int    | No       | 72      | Look-back window in hours      |
| min_magnitude   | float  | No       | 2.5     | Minimum magnitude              |
| limit           | int    | No       | 200     | Maximum number of events       |

**Example Request:**
```
GET /events?hours=48&min_magnitude=3.5
```

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

## 4. Add Local Event

### `POST /local-event`

Adds a local observation or user report. The event is included in subsequent risk calculations (useful when the network is down).

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

| Field      | Type   | Required | Description                              |
|------------|--------|----------|------------------------------------------|
| lat        | float  | Yes      | Latitude                                 |
| lon        | float  | Yes      | Longitude                                |
| magnitude  | float  | Yes      | Estimated or reported magnitude          |
| time       | string | No       | ISO timestamp (defaults to now)          |
| source     | string | No       | `"user_report"`, `"accelerometer"`, etc. |
| note       | string | No       | Optional free-text note                  |

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

## 5. Refresh Catalog

### `POST /refresh-catalog`

Attempts to download the latest earthquake catalog from USGS and update the local cache.  
Only succeeds when internet connectivity is available.

**Request Body (optional):**
```json
{
  "min_magnitude": 2.5,
  "days_back": 30
}
```

**Response 200 (success):**
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

## 6. Risk Grid (Heatmap)

### `GET /risk/grid`

Returns risk scores on a regular latitude/longitude grid. Useful for generating a heatmap.

**Query Parameters:**

| Parameter     | Type  | Required | Default | Description                    |
|---------------|-------|----------|---------|--------------------------------|
| min_lat       | float | Yes      | —       | Southern boundary              |
| max_lat       | float | Yes      | —       | Northern boundary              |
| min_lon       | float | Yes      | —       | Western boundary               |
| max_lon       | float | Yes      | —       | Eastern boundary               |
| resolution    | float | No       | 0.1     | Grid step in degrees           |
| time_window   | string| No       | `24h`   | `24h` or `7d`                  |
| min_magnitude | float | No       | 4.0     | Magnitude threshold            |

**Example Request:**
```
GET /risk/grid?min_lat=33.5&max_lat=34.5&min_lon=-119&max_lon=-117.5&resolution=0.15&time_window=24h
```

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

## 7. Event-Triggered Aftershock Forecast

### `POST /forecasts`

Calculates localized aftershock probability and expected event rates explicitly triggered by a specific reference earthquake in the local cache.

#### Request Body:
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

| Field                  | Type    | Required | Constraints                | Description                                                |
|------------------------|---------|----------|----------------------------|------------------------------------------------------------|
| `trigger_event_id`     | string  | Yes      | Non-empty string           | ID of the reference earthquake present in local cache       |
| `target.latitude`      | float   | Yes      | -90.0 to 90.0              | Center latitude of the forecast assessment zone            |
| `target.longitude`     | float   | Yes      | -180.0 to 180.0            | Center longitude of the forecast assessment zone           |
| `target.radius_km`     | float   | Yes      | 0 < radius <= 500          | Radius in kilometers around target coordinates             |
| `window_hours`         | integer | Yes      | 24 or 168                  | Forecast horizon: `24` (1 day) or `168` (7 days)           |
| `minimum_magnitude`    | float   | Yes      | -1.0 to 10.0               | Threshold magnitude $M_c$ for anticipated events           |

#### Response 200:
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

---

## 8. Planned Edge Endpoints (Frontend Roadmap)

1. **`GET /geocode?q=<place>`**: Offline place-to-coordinate lookup using a local SQLite gazetteer.
2. **`GET /risk/alerts?min_risk=0.7`**: Active high-risk regional clusters feed.
3. **`GET /local-events` & `DELETE /local-event/<id>`**: Local observation reports listing and deletion.
4. **`GET /events/<event_id>`**: Detailed single event metadata and station records.

---

## Error Responses

| Status | Meaning                          | Example Message                          |
|--------|----------------------------------|------------------------------------------|
| 400    | Bad request / missing parameters | `"lat and lon are required"`             |
| 422    | Validation error                 | `"time_window must be '24h' or '7d'"`    |
| 500    | Internal calculation error       | `"Risk engine failed"`                   |
| 503    | Service unavailable (offline)    | `"Catalog refresh requires internet"`    |

---

## Notes for Implementation

- All timestamps are in UTC (ISO 8601).
- Risk scores are relative (0–1 scale or raw rate). Document the exact scale used in your model.
- Local events added via `POST /local-event` should persist only for the current session or be stored in a temporary local file.
- The `/risk` and `/risk/grid` endpoints must work fully offline using the cached catalog + any local events.
- CORS should be enabled if the frontend runs on a different port.

---

**End of documentation**
