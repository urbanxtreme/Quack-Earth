from flask import Blueprint, current_app, request

from ..models.forecast import Target
from .common import error

forecasts_bp = Blueprint("forecasts", __name__)


@forecasts_bp.post("/forecasts")
def forecasts():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("invalid_json", "Request body must be a JSON object")
    target = body.get("target")
    try:
        if not isinstance(body.get("trigger_event_id"), str) or not body["trigger_event_id"]:
            return error("invalid_trigger_event", "trigger_event_id is required")
        if not isinstance(target, dict):
            return error("invalid_target", "target is required")
        latitude, longitude, radius = float(target["latitude"]), float(target["longitude"]), float(target["radius_km"])
        window = int(body["window_hours"])
        magnitude = float(body["minimum_magnitude"])
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            return error("invalid_coordinates", "latitude or longitude is out of range")
        if not 0 < radius <= 500:
            return error("invalid_radius", "radius_km must be greater than 0 and no more than 500")
        if window not in (24, 168):
            return error("invalid_window", "window_hours must be 24 or 168")
        if not -1 <= magnitude <= 10:
            return error("invalid_magnitude", "minimum_magnitude must be between -1 and 10")
        repository = current_app.extensions["event_repository"]
        trigger = repository.get_event(body["trigger_event_id"])
        if trigger is None:
            return error("trigger_event_not_found", "trigger_event_id does not exist in the local cache", 404)
        metadata = repository.metadata()
        if metadata["event_count"] == 0 or not metadata.get("last_successful_sync"):
            return error("cache_empty", "An initial catalog sync is required before forecasting", 503)
        result = current_app.extensions["forecast_service"].calculate(
            trigger, Target(latitude, longitude, radius), window, magnitude
        )
        return result.to_dict()
    except (KeyError, TypeError, ValueError):
        return error("invalid_parameter", "Forecast fields must contain valid numeric values")
