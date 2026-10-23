from flask import Blueprint, current_app, request

from .common import error

risk_bp = Blueprint("risk", __name__)


@risk_bp.get("/risk")
def calculate_risk():
    lat_val = request.args.get("lat")
    lon_val = request.args.get("lon")

    if lat_val is None or lon_val is None:
        return error("lat and lon are required", 400)

    try:
        lat = float(lat_val)
        lon = float(lon_val)
    except (ValueError, TypeError):
        return error("lat and lon must be numbers", 400)

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return error("latitude and longitude out of range", 422)

    radius_val = request.args.get("radius_km")
    try:
        radius_km = float(radius_val) if radius_val is not None else 50.0
    except (ValueError, TypeError):
        return error("radius_km must be a number", 400)

    if radius_km <= 0:
        return error("radius_km must be positive", 422)

    time_window = request.args.get("time_window", "24h")
    if time_window not in ("24h", "7d"):
        return error("time_window must be '24h' or '7d'", 422)

    min_mag_val = request.args.get("min_magnitude")
    try:
        min_magnitude = float(min_mag_val) if min_mag_val is not None else 4.0
    except (ValueError, TypeError):
        return error("min_magnitude must be a number", 400)

    try:
        risk_service = current_app.extensions["risk_service"]
        result = risk_service.calculate_risk(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            time_window=time_window,
            min_magnitude=min_magnitude,
        )
        return result, 200
    except Exception as exc:
        return error("Risk engine failed", 500)


@risk_bp.get("/risk/grid")
def calculate_grid():
    min_lat_val = request.args.get("min_lat")
    max_lat_val = request.args.get("max_lat")
    min_lon_val = request.args.get("min_lon")
    max_lon_val = request.args.get("max_lon")

    if min_lat_val is None or max_lat_val is None or min_lon_val is None or max_lon_val is None:
        return error("min_lat, max_lat, min_lon, and max_lon are required", 400)

    try:
        min_lat = float(min_lat_val)
        max_lat = float(max_lat_val)
        min_lon = float(min_lon_val)
        max_lon = float(max_lon_val)
    except (ValueError, TypeError):
        return error("Coordinates must be valid numbers", 400)

    if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0 and
            -180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
        return error("Coordinates out of range", 422)

    if min_lat >= max_lat or min_lon >= max_lon:
        return error("min boundaries must be less than max boundaries", 400)

    resolution_val = request.args.get("resolution")
    try:
        resolution = float(resolution_val) if resolution_val is not None else 0.1
    except (ValueError, TypeError):
        return error("resolution must be a number", 400)

    if resolution <= 0:
        return error("resolution must be positive", 422)

    time_window = request.args.get("time_window", "24h")
    if time_window not in ("24h", "7d"):
        return error("time_window must be '24h' or '7d'", 422)

    min_mag_val = request.args.get("min_magnitude")
    try:
        min_magnitude = float(min_mag_val) if min_mag_val is not None else 4.0
    except (ValueError, TypeError):
        return error("min_magnitude must be a number", 400)

    try:
        risk_service = current_app.extensions["risk_service"]
        result = risk_service.calculate_grid(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            resolution=resolution,
            time_window=time_window,
            min_magnitude=min_magnitude,
        )
        return result, 200
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return error("Risk engine failed", 500)
