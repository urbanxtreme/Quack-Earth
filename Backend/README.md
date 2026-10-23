# Earthquake risk estimation backend

This is an experimental Flask API for estimating short-term aftershock activity
from a cached USGS ComCat catalog. It is not an earthquake prediction service,
shaking-intensity model, or official warning system.

## Run locally

```powershell
cd Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The SQLite cache is created at `Backend/instance/earthquake_cache.db`. Set
`EARTHQUAKE_DATABASE_PATH` to use a different database.

## API

- `GET /api/v1/health` reports cache state and synchronization freshness.
- `GET /api/v1/events?start=<ISO>&end=<ISO>` reads cached events.
- `POST /api/v1/sync` accepts optional `start`, `end`, and `minimum_magnitude`.
- `POST /api/v1/forecasts` accepts the forecast request described in the project plan.

Forecast windows are limited to 24 or 168 hours. Forecast responses include the
model assumptions, `data_as_of`, and limitations. A cached catalog remains
available when synchronization fails.
