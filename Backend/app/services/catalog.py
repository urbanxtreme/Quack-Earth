import socket
import time
from datetime import datetime, timedelta, timezone

import requests

from ..models.event import Event


class CatalogSyncError(Exception):
    pass


class OfflineCatalogError(CatalogSyncError):
    pass


_LAST_ONLINE_CHECK_TIME = 0.0
_LAST_ONLINE_STATUS = False


def check_online(timeout: float = 1.0, cache_seconds: float = 5.0) -> bool:
    global _LAST_ONLINE_CHECK_TIME, _LAST_ONLINE_STATUS
    now = time.time()
    if now - _LAST_ONLINE_CHECK_TIME < cache_seconds:
        return _LAST_ONLINE_STATUS
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        # Check standard external DNS / HTTP port
        sock.connect(("8.8.8.8", 53))
        sock.close()
        _LAST_ONLINE_STATUS = True
    except OSError:
        _LAST_ONLINE_STATUS = False
    _LAST_ONLINE_CHECK_TIME = now
    return _LAST_ONLINE_STATUS


def set_online_status(status: bool) -> None:
    global _LAST_ONLINE_CHECK_TIME, _LAST_ONLINE_STATUS
    _LAST_ONLINE_STATUS = status
    _LAST_ONLINE_CHECK_TIME = time.time()


class CatalogService:
    def __init__(self, repository, url: str):
        self.repository = repository
        self.url = url

    def refresh(self, min_magnitude: float = 2.5, days_back: int = 30) -> dict:
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days_back)
        params = {
            "format": "geojson",
            "starttime": start.date().isoformat(),
            "endtime": now.date().isoformat(),
            "orderby": "time-asc",
            "limit": 5000,
        }
        if min_magnitude is not None:
            params["minmagnitude"] = min_magnitude

        try:
            response = requests.get(self.url, params=params, timeout=12)
            response.raise_for_status()
            payload = response.json()
            features = payload.get("features")
            if not isinstance(features, list):
                raise ValueError("USGS response did not contain a feature list")
            fetched_at = datetime.now(timezone.utc)
            events = [self._normalize(feature, fetched_at) for feature in features]
            events = [event for event in events if event is not None]
            self.repository.upsert_events(events)
            fetched_iso = fetched_at.isoformat().replace("+00:00", "Z")
            self.repository.set_metadata({
                "last_successful_sync": fetched_iso,
                "source": "usgs",
                "last_sync_error": "",
            })
            set_online_status(True)
            return {
                "status": "updated",
                "events_fetched": len(events),
                "last_catalog_update": fetched_iso,
            }
        except (requests.RequestException, socket.error) as error:
            set_online_status(False)
            self.repository.set_metadata({"last_sync_error": str(error)})
            raise OfflineCatalogError("No internet connection. Using cached catalog.") from error
        except Exception as error:
            self.repository.set_metadata({"last_sync_error": str(error)})
            raise CatalogSyncError(f"Catalog synchronization failed: {error}") from error

    # Keep backward-compatible sync alias
    def sync(self, start: datetime, end: datetime, min_magnitude: float | None = None) -> dict:
        days_back = max(1, (end - start).days)
        return self.refresh(min_magnitude=min_magnitude or 2.5, days_back=days_back)

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
            str(event_id),
            origin,
            float(coordinates[1]),
            float(coordinates[0]),
            float(coordinates[2]) if len(coordinates) > 2 and coordinates[2] is not None else None,
            float(properties["mag"]) if properties.get("mag") is not None else None,
            properties.get("magType"),
            properties.get("status"),
            "usgs",
            fetched_at,
        )
