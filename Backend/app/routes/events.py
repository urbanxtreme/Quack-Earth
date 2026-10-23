from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, request

from ..models.event import Event
from ..services.catalog import CatalogSyncError, OfflineCatalogError
from .common import error, parse_iso

events_bp = Blueprint("events", __name__)


@events_bp.get("/map/events")
def map_events():
    try:
        min_lat = float(request.args["min_lat"])
        max_lat = float(request.args["max_lat"])
        min_lon = float(request.args["min_lon"])
        max_lon = float(request.args["max_lon"])
        if not (-90 <= min_lat < max_lat <= 90 and -180 <= min_lon < max_lon <= 180):
            return error("Map bounds are out of range or not ordered", 422)

        hours = int(request.args.get("hours", 168))
        min_magnitude = float(request.args.get("min_magnitude", 0))
        limit = int(request.args.get("limit", 1000))
        if hours <= 0 or hours > 366 * 24:
            return error("hours must be between 1 and 8784", 422)
        if not -1 <= min_magnitude <= 10:
            return error("min_magnitude must be between -1 and 10", 422)
        if not 0 < limit <= 5000:
            return error("limit must be between 1 and 5000", 422)

        now = datetime.now(timezone.utc)
        records = current_app.extensions["event_repository"].list_events(
            start=now - timedelta(hours=hours),
            end=now + timedelta(hours=24),
            min_magnitude=min_magnitude,
            limit=5000,
        )
        records = [
            event for event in records
            if min_lat <= event.latitude <= max_lat
            and min_lon <= event.longitude <= max_lon
        ][:limit]
        metadata = current_app.extensions["event_repository"].metadata()
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": event.event_id,
                    "geometry": {
                        "type": "Point",
                        "coordinates": [event.longitude, event.latitude],
                    },
                    "properties": event.to_dict(),
                }
                for event in records
            ],
            "count": len(records),
            "source": metadata.get("source", "USGS ComCat"),
            "data_as_of": metadata.get("last_successful_sync"),
            "bounds": {
                "min_lat": min_lat,
                "max_lat": max_lat,
                "min_lon": min_lon,
                "max_lon": max_lon,
            },
        }, 200
    except (KeyError, TypeError, ValueError) as exc:
        return error(f"Invalid map query: {exc}", 400)


@events_bp.get("/events")
def events():
    try:
        hours_param = request.args.get("hours")
        hours = int(float(hours_param)) if hours_param is not None else 72
        if hours <= 0:
            return error("hours must be a positive integer", 422)

        min_mag_param = request.args.get("min_magnitude")
        min_magnitude = float(min_mag_param) if min_mag_param is not None else 2.5

        limit_param = request.args.get("limit")
        limit = int(float(limit_param)) if limit_param is not None else 200
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

        output_format = request.args.get("format", "json").lower()
        if output_format == "geojson":
            features = [
                {
                    "type": "Feature",
                    "id": ev["id"],
                    "geometry": {
                        "type": "Point",
                        "coordinates": [ev["lon"], ev["lat"]] if ev.get("depth_km") is None else [ev["lon"], ev["lat"], ev["depth_km"]],
                    },
                    "properties": {
                        "mag": ev["magnitude"],
                        "time": ev["time"],
                        "source": ev["source"],
                        "note": ev.get("note"),
                        "place": ev.get("place"),
                    },
                }
                for ev in event_list
            ]
            return {
                "type": "FeatureCollection",
                "count": len(features),
                "features": features,
            }, 200

        return {
            "count": len(event_list),
            "events": event_list,
        }, 200
    except ValueError as exc:
        return error(f"Invalid query parameter: {exc}", 400)


@events_bp.get("/events/<event_id>")
def get_single_event(event_id: str):
    repository = current_app.extensions["event_repository"]
    event = repository.get_event(event_id)
    if not event:
        return error("Event not found", 404, code="event_not_found")
    return event.to_dict(), 200


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

    if not (-1.0 <= magnitude <= 10.0):
        return error("magnitude must be between -1.0 and 10.0", 422)

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
    place = body.get("place") or (f"Report: {note[:30]}" if note else f"Local observation ({lat:.2f}°, {lon:.2f}°)")

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
        place=place,
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
