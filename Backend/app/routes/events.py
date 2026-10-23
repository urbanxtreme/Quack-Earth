from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, request

from ..services.catalog import CatalogSyncError
from .common import error, parse_iso

events_bp = Blueprint("events", __name__)


@events_bp.get("/events")
def events():
    try:
        end = parse_iso(request.args["end"], "end") if request.args.get("end") else datetime.now(timezone.utc)
        start = parse_iso(request.args["start"], "start") if request.args.get("start") else end - timedelta(days=30)
        if start > end or (end - start).days > 366:
            return error("invalid_date_range", "Date range must be ordered and no longer than 366 days")
        repository = current_app.extensions["event_repository"]
        records = repository.list_events(start=start, end=end, limit=5000)
        metadata = repository.metadata()
        if not records and metadata["event_count"] == 0:
            return error("cache_empty", "No cached events exist; run an initial sync", 503)
        return {"events": [event.to_dict() for event in records], "count": len(records),
                "source": metadata.get("source", "USGS ComCat"),
                "data_as_of": metadata.get("last_successful_sync")}
    except ValueError as exc:
        return error("invalid_parameter", str(exc))


@events_bp.post("/sync")
def sync():
    body = request.get_json(silent=True) or {}
    try:
        end = parse_iso(body.get("end"), "end") if body.get("end") else datetime.now(timezone.utc)
        start = parse_iso(body.get("start"), "start") if body.get("start") else end - timedelta(days=30)
        if start > end or (end - start).days > 366:
            return error("invalid_date_range", "Date range must be ordered and no longer than 366 days")
        magnitude = body.get("minimum_magnitude")
        if magnitude is not None:
            magnitude = float(magnitude)
            if not -1 <= magnitude <= 10:
                return error("invalid_magnitude", "minimum_magnitude must be between -1 and 10")
        result = current_app.extensions["catalog_service"].sync(start, end, magnitude)
        return result, 200
    except (ValueError, TypeError) as exc:
        return error("invalid_parameter", str(exc))
    except CatalogSyncError as exc:
        return error("catalog_unavailable", str(exc), 502)
