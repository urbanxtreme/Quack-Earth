from datetime import datetime, timezone

import requests

from ..models.event import Event


class CatalogSyncError(Exception):
    pass


class CatalogService:
    def __init__(self, repository, url: str):
        self.repository = repository
        self.url = url

    def sync(self, start: datetime, end: datetime, min_magnitude: float | None = None):
        params = {
            "format": "geojson", "starttime": start.date().isoformat(),
            "endtime": end.date().isoformat(), "orderby": "time-asc",
            "limit": 5000,
        }
        if min_magnitude is not None:
            params["minmagnitude"] = min_magnitude
        try:
            response = requests.get(self.url, params=params, timeout=15)
            response.raise_for_status()
            payload = response.json()
            features = payload.get("features")
            if not isinstance(features, list):
                raise ValueError("USGS response did not contain a feature list")
            fetched_at = datetime.now(timezone.utc)
            events = [self._normalize(feature, fetched_at) for feature in features]
            events = [event for event in events if event is not None]
            self.repository.upsert_events(events)
            self.repository.set_metadata({
                "last_successful_sync": fetched_at.isoformat(),
                "source": "USGS ComCat",
                "last_sync_error": "",
            })
            return {"events_updated": len(events), "data_as_of": fetched_at.isoformat().replace("+00:00", "Z")}
        except (requests.RequestException, ValueError, TypeError) as error:
            self.repository.set_metadata({"last_sync_error": str(error)})
            raise CatalogSyncError("Catalog synchronization failed; existing cache was preserved") from error

    @staticmethod
    def _normalize(feature, fetched_at):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [])
        event_id = feature.get("id")
        if not event_id or len(coordinates) < 2 or properties.get("time") is None:
            return None
        origin = datetime.fromtimestamp(properties["time"] / 1000, tz=timezone.utc)
        return Event(
            str(event_id), origin, float(coordinates[1]), float(coordinates[0]),
            float(coordinates[2]) if len(coordinates) > 2 and coordinates[2] is not None else None,
            float(properties["mag"]) if properties.get("mag") is not None else None,
            properties.get("magType"), properties.get("status"), "USGS ComCat", fetched_at,
        )
