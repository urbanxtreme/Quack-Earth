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

        max_mag_param = request.args.get("max_magnitude")
        max_magnitude = float(max_mag_param) if max_mag_param is not None else None

        limit_param = request.args.get("limit")
        limit = int(float(limit_param)) if limit_param is not None else 200
        if limit <= 0:
            return error("limit must be a positive integer", 422)

        offset_param = request.args.get("offset")
        offset = int(float(offset_param)) if offset_param is not None else 0
        if offset < 0:
            return error("offset must be non-negative", 422)

        min_lat = float(request.args["min_lat"]) if "min_lat" in request.args else None
        max_lat = float(request.args["max_lat"]) if "max_lat" in request.args else None
        min_lon = float(request.args["min_lon"]) if "min_lon" in request.args else None
        max_lon = float(request.args["max_lon"]) if "max_lon" in request.args else None

        if any(v is not None for v in (min_lat, max_lat, min_lon, max_lon)):
            if not all(v is not None for v in (min_lat, max_lat, min_lon, max_lon)):
                return error("If specifying bounds, all of min_lat, max_lat, min_lon, max_lon are required", 400)
            if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0 and
                    -180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
                return error("Coordinates out of range", 422)
            if min_lat >= max_lat or min_lon >= max_lon:
                return error("min boundaries must be less than max boundaries", 400)

        source = request.args.get("source")

        repository = current_app.extensions["event_repository"]
        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=hours)
        end = now + timedelta(hours=24)  # account for slight future timestamp in local reports

        if request.args.get("end"):
            end = parse_iso(request.args["end"], "end")
        if request.args.get("start"):
            start = parse_iso(request.args["start"], "start")

        records = repository.list_events(
            start=start,
            end=end,
            min_magnitude=min_magnitude,
            max_magnitude=max_magnitude,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            source=source,
            limit=limit,
            offset=offset,
        )

        # If no events exist in the requested window, query live from USGS if available
        if not records and not (request.args.get("start") or request.args.get("end")):
            catalog_service = current_app.extensions.get("catalog_service")
            if catalog_service:
                try:
                    catalog_service.refresh(
                        min_magnitude=min_magnitude,
                        days_back=max(1, int(hours / 24) + 1),
                        min_lat=min_lat,
                        max_lat=max_lat,
                        min_lon=min_lon,
                        max_lon=max_lon,
                    )
                    records = repository.list_events(
                        start=start,
                        end=end,
                        min_magnitude=min_magnitude,
                        max_magnitude=max_magnitude,
                        min_lat=min_lat,
                        max_lat=max_lat,
                        min_lon=min_lon,
                        max_lon=max_lon,
                        source=source,
                        limit=limit,
                        offset=offset,
                    )
                except Exception:
                    pass

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
                    "properties": ev,
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


@events_bp.get("/events/<event_id>/sequence")
def get_event_sequence(event_id: str):
    """Retrieve identified aftershock sequence and spatiotemporal cluster telemetry for an event."""
    repository = current_app.extensions["event_repository"]
    main_event = repository.get_event(event_id)
    if not main_event:
        return error("Event not found", 404, code="event_not_found")

    all_events = repository.list_events(limit=10000)
    try:
        from quack_risk.sequence import identify_sequence
        seq = identify_sequence(all_events, main_event)

        return {
            "mainshock": seq.mainshock,
            "search_radius_km": seq.search_radius_km,
            "search_window_days": seq.search_window_days,
            "foreshock_count": len(seq.foreshocks),
            "aftershock_count": len(seq.aftershocks),
            "confidence": seq.confidence,
            "geometry": {
                "strike_deg": seq.geometry.strike_deg,
                "major_axis_km": seq.geometry.major_axis_km,
                "minor_axis_km": seq.geometry.minor_axis_km,
                "aspect_ratio": seq.geometry.aspect_ratio,
                "is_elongated": seq.geometry.is_elongated,
                "strike_uncertainty_deg": seq.geometry.strike_uncertainty_deg,
                "notes": seq.geometry.notes,
            },
            "omori_fit": {
                "k": seq.omori_fit.k,
                "c_days": seq.omori_fit.c_days,
                "p": seq.omori_fit.p,
                "is_fitted": seq.omori_fit.is_fitted,
                "log_likelihood": seq.omori_fit.log_likelihood,
                "method": seq.omori_fit.method,
                "parameter_uncertainty": seq.omori_fit.parameter_uncertainty,
            },
            "foreshocks": seq.foreshocks[:50],
            "aftershocks": seq.aftershocks[:200],
            "data_quality_notes": seq.data_quality_notes,
        }, 200
    except Exception as exc:
        return error(f"Sequence analysis failed: {exc}", 500)


@events_bp.get("/events/<event_id>/simulate-aftershocks")
def simulate_event_aftershocks(event_id: str):
    """Generate up to 7 days of probabilistic aftershocks combining observed and Omori-projected arrivals."""
    repository = current_app.extensions["event_repository"]
    main_event = repository.get_event(event_id)
    if not main_event:
        return error(f"Event {event_id} not found", 404)

    try:
        days = float(request.args.get("days", 7.0))
        min_mag = float(request.args.get("min_magnitude", 3.0))
        seed = int(request.args.get("seed", 42))

        from quack_risk.sequence import identify_sequence, simulate_aftershock_sequence

        all_events = repository.list_events(limit=5000)
        seq = identify_sequence(all_events, main_event)

        sim_res = simulate_aftershock_sequence(
            mainshock=main_event,
            omori_fit=seq.omori_fit,
            geometry=seq.geometry,
            duration_days=days,
            min_magnitude=min_mag,
            observed_aftershocks=seq.aftershocks,
            random_seed=seed,
        )
        return sim_res, 200
    except Exception as exc:
        return error(f"Aftershock simulation failed: {exc}", 500)


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
    signal_type = body.get("signal_type", "accelerometer" if (note and "accelerometer" in note.lower()) else "report")
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
        magnitude_type=signal_type,
        review_status="user_report",
        source=source,
        fetched_at=now,
        note=note,
        place=place,
    )

    repository.upsert_events([local_event])

    # Multimodal corroboration gate from quack_risk
    corroboration = {
        "admitted": False,
        "status": "pending_cluster",
        "trigger_weight": 0.0,
        "reason": "Single uncorroborated report. Waiting for spatial-temporal cluster or nearby catalog event.",
    }
    try:
        from pathlib import Path
        import pandas as pd
        from quack_risk.config import RiskParams
        from quack_risk.multimodal import signals_to_triggers
        from quack_risk.io import load_signals

        cache_dir = Path(__file__).resolve().parents[3] / "model" / "data" / "cache"
        signals_path = cache_dir / "signals.json"
        catalog_path = cache_dir / "catalog.csv"

        if signals_path.exists():
            sig_df = load_signals(signals_path)
            cat_df = None
            if catalog_path.exists():
                from quack_risk.io import load_catalog
                try:
                    cat_df = load_catalog(catalog_path)
                except Exception:
                    cat_df = None

            triggers = signals_to_triggers(sig_df, as_of=origin_time, params=RiskParams(), catalog=cat_df)
            if not triggers.empty:
                matched = triggers[triggers["id"].str.contains(event_id)]
                if not matched.empty:
                    corroboration = {
                        "admitted": True,
                        "status": "corroborated",
                        "trigger_weight": float(matched.iloc[0]["trigger_weight"]),
                        "reason": f"Corroborated by {matched.iloc[0]['mag_type']} evidence and admitted into risk engine.",
                    }
    except Exception:
        pass

    return {
        "status": "added",
        "event_id": event_id,
        "message": "Local event added. Risk will include this event." if corroboration["admitted"] else "Local event recorded. Awaiting corroboration cluster.",
        "nearby_risk_updated": True,
        "corroboration": corroboration,
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
