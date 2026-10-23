from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, request

from ..models.event import Event
from ..services.catalog import CatalogSyncError, OfflineCatalogError
from .common import error, parse_iso

events_bp = Blueprint("events", __name__)


@events_bp.get("/events")
def events():
    try:
        hours_param = request.args.get("hours")
        hours = int(hours_param) if hours_param is not None else 72
        if hours <= 0:
            return error("hours must be a positive integer", 422)

        min_mag_param = request.args.get("min_magnitude")
        min_magnitude = float(min_mag_param) if min_mag_param is not None else 2.5

        limit_param = request.args.get("limit")
        limit = int(limit_param) if limit_param is not None else 200
        if limit <= 0:
            return error("limit must be a positive integer", 422)

        repository = current_app.extensions["event_repository"]
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)
        end = now + timedelta(hours=24)  # account for slight future timestamp in local reports

        # Also support explicit start/end query parameters if provided
        if request.args.get("end"):
            end = parse_iso(request.args["end"], "end")
        if request.args.get("start"):
            start = parse_iso(request.args["start"], "start")

        records = repository.list_events(start=start, end=end, min_magnitude=min_magnitude, limit=limit)

        # Fall back to looking back from the newest event if catalog is historical/offline demo
        if not records:
            all_cached = repository.list_events(min_magnitude=min_magnitude, limit=limit)
            if all_cached:
                latest_origin = max(e.origin_time for e in all_cached)
                if (now - latest_origin).days > 30 and not (request.args.get("start") or request.args.get("end")):
                    hist_start = latest_origin - timedelta(hours=hours)
                    hist_end = latest_origin + timedelta(hours=1)
                    records = repository.list_events(
                        start=hist_start, end=hist_end, min_magnitude=min_magnitude, limit=limit
                    )

        event_list = [event.to_dict() for event in records]
        return {
            "count": len(event_list),
            "events": event_list,
        }, 200
    except ValueError as exc:
        return error(f"Invalid query parameter: {exc}", 400)


@events_bp.post("/local-event")
def add_local_event():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("Invalid JSON body", 400)

    # Required fields
    if "lat" not in body or "lon" not in body or "magnitude" not in body:
        return error("lat, lon, and magnitude are required", 400)

    try:
        lat = float(body["lat"])
        lon = float(body["lon"])
        magnitude = float(body["magnitude"])
    except (TypeError, ValueError):
        return error("lat, lon, and magnitude must be numbers", 400)

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return error("latitude and longitude out of range", 422)

    time_str = body.get("time")
    if time_str:
        try:
            origin_time = parse_iso(time_str, "time")
        except ValueError as exc:
            return error(str(exc), 422)
    else:
        origin_time = datetime.now(timezone.utc)

    source = body.get("source") or "user_report"
    note = body.get("note")

    repository = current_app.extensions["event_repository"]
    event_id = repository.get_next_local_event_id()
    now = datetime.now(timezone.utc)

    local_event = Event(
        event_id=event_id,
        origin_time=origin_time,
        latitude=lat,
        longitude=lon,
        depth_km=None,
        magnitude=magnitude,
        magnitude_type="local",
        review_status="user_report",
        source=source,
        fetched_at=now,
        note=note,
    )

    repository.upsert_events([local_event])

    return {
        "status": "added",
        "event_id": event_id,
        "message": "Local event added. Risk will include this event.",
        "nearby_risk_updated": True,
    }, 201


@events_bp.post("/refresh-catalog")
@events_bp.post("/sync")
def refresh_catalog():
    body = request.get_json(silent=True) or {}
    try:
        min_mag = body.get("min_magnitude", body.get("minimum_magnitude", 2.5))
        if min_mag is not None:
            min_mag = float(min_mag)
        days_back = int(body.get("days_back", 30))
        if days_back <= 0 or days_back > 366:
            return error("days_back must be between 1 and 366", 422)

        catalog_service = current_app.extensions["catalog_service"]
        result = catalog_service.refresh(min_magnitude=min_mag, days_back=days_back)
        return result, 200
    except (ValueError, TypeError) as exc:
        return error(str(exc), 400)
    except OfflineCatalogError:
        return {
            "status": "failed",
            "message": "No internet connection. Using cached catalog.",
        }, 503
    except CatalogSyncError as exc:
        return error(str(exc), 502)
