from flask import Blueprint, request

from ..data.faults import VERIFIED_FAULTS_GEOJSON, get_faults_in_bounds
from .common import error

faults_bp = Blueprint("faults", __name__)


@faults_bp.get("/faults")
@faults_bp.get("/map/faults")
def get_faults():
    """Retrieve verified tectonic fault geometry GeoJSON."""
    min_lat_val = request.args.get("min_lat")
    max_lat_val = request.args.get("max_lat")
    min_lon_val = request.args.get("min_lon")
    max_lon_val = request.args.get("max_lon")

    if any(v is not None for v in (min_lat_val, max_lat_val, min_lon_val, max_lon_val)):
        try:
            min_lat = float(min_lat_val)
            max_lat = float(max_lat_val)
            min_lon = float(min_lon_val)
            max_lon = float(max_lon_val)
        except (ValueError, TypeError):
            return error("Bounding box coordinates must be numbers", 400)

        if not (-90.0 <= min_lat <= 90.0 and -90.0 <= max_lat <= 90.0 and
                -180.0 <= min_lon <= 180.0 and -180.0 <= max_lon <= 180.0):
            return error("Coordinates out of range", 422)

        if min_lat >= max_lat or min_lon >= max_lon:
            return error("min boundaries must be less than max boundaries", 400)

        return get_faults_in_bounds(min_lat, max_lat, min_lon, max_lon), 200

    return VERIFIED_FAULTS_GEOJSON, 200
