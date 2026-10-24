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

    def refresh(
        self,
        min_magnitude: float = 2.5,
        days_back: int = 30,
        start: datetime | None = None,
        end: datetime | None = None,
        min_lat: float | None = None,
        max_lat: float | None = None,
        min_lon: float | None = None,
        max_lon: float | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc)
        start_dt = start or (now - timedelta(days=days_back))
        end_dt = end or now
        params = {
            "format": "geojson",
            "starttime": start_dt.date().isoformat() if hasattr(start_dt, "date") else str(start_dt),
            "endtime": end_dt.date().isoformat() if hasattr(end_dt, "date") else str(end_dt),
            "orderby": "time-asc",
            "limit": 5000,
        }
        if min_magnitude is not None:
            params["minmagnitude"] = min_magnitude
        if min_lat is not None:
            params["minlatitude"] = min_lat
        if max_lat is not None:
            params["maxlatitude"] = max_lat
        if min_lon is not None:
            params["minlongitude"] = min_lon
        if max_lon is not None:
            params["maxlongitude"] = max_lon

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
        return self.refresh(min_magnitude=min_magnitude or 2.5, days_back=days_back, start=start, end=end)

    @staticmethod
    def _normalize(feature, fetched_at):
        properties = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [])
        event_id = feature.get("id")
        if not event_id or len(coordinates) < 2 or properties.get("time") is None:
            return None
        origin = datetime.fromtimestamp(properties["time"] / 1000, tz=timezone.utc)

        def _safe_float(val):
            try:
                return float(val) if val is not None else None
            except (ValueError, TypeError):
                return None

        def _safe_int(val):
            try:
                return int(val) if val is not None else None
            except (ValueError, TypeError):
                return None

        h_err = _safe_float(properties.get("horizontalError"))
        d_err = _safe_float(properties.get("depthError"))
        m_err = _safe_float(properties.get("magError"))
        gap = _safe_float(properties.get("gap"))
        dmin = _safe_float(properties.get("dmin"))
        rms = _safe_float(properties.get("rms"))
        nst = _safe_int(properties.get("nst"))
        event_type = properties.get("type", "earthquake")

        return Event(
            event_id=str(event_id),
            origin_time=origin,
            latitude=float(coordinates[1]),
            longitude=float(coordinates[0]),
            depth_km=float(coordinates[2]) if len(coordinates) > 2 and coordinates[2] is not None else None,
            magnitude=float(properties["mag"]) if properties.get("mag") is not None else None,
            magnitude_type=properties.get("magType"),
            review_status=properties.get("status"),
            source="usgs",
            fetched_at=fetched_at,
            note=None,
            place=properties.get("place"),
            horizontal_error_km=h_err,
            depth_error_km=d_err,
            mag_error=m_err,
            azimuthal_gap=gap,
            dmin=dmin,
            rms=rms,
            nst=nst,
            event_type=event_type,
        )
