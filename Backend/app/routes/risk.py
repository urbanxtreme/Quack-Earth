from flask import Blueprint, current_app, request

from .common import error

risk_bp = Blueprint("risk", __name__)


@risk_bp.get("/risk/heatmap")
def calculate_heatmap():
    try:
        min_lat = float(request.args["min_lat"])
        max_lat = float(request.args["max_lat"])
        min_lon = float(request.args["min_lon"])
        max_lon = float(request.args["max_lon"])
        resolution = float(request.args.get("resolution", 0.1))
        min_magnitude = float(request.args.get("min_magnitude", 4.0))
        time_window = request.args.get("time_window", "24h")
    except (KeyError, TypeError, ValueError) as exc:
        return error(f"Invalid heatmap query: {exc}", 400)

    if not (-90 <= min_lat < max_lat <= 90 and -180 <= min_lon < max_lon <= 180):
        return error("Coordinates out of range or boundaries are not ordered", 422)
    if resolution <= 0:
        return error("resolution must be positive", 422)
    if time_window not in ("24h", "7d"):
        return error("time_window must be '24h' or '7d'", 422)
    if not -1 <= min_magnitude <= 10:
        return error("min_magnitude must be between -1 and 10", 422)

    try:
        grid = current_app.extensions["risk_service"].calculate_grid(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            resolution=resolution,
            time_window=time_window,
            min_magnitude=min_magnitude,
        )
        features = []
        half = resolution / 2
        for cell in grid["grid"]:
            lat, lon = cell["lat"], cell["lon"]
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [max(-180, lon - half), max(-90, lat - half)],
                        [min(180, lon + half), max(-90, lat - half)],
                        [min(180, lon + half), min(90, lat + half)],
                        [max(-180, lon - half), min(90, lat + half)],
                        [max(-180, lon - half), max(-90, lat - half)],
                    ]],
                },
                "properties": {
                    **cell,
                    "value": cell["risk_score"],
                },
            })
        return {
            "type": "FeatureCollection",
            "features": features,
            "count": len(features),
            "time_window": time_window,
            "min_magnitude": min_magnitude,
            "resolution": resolution,
            "bounds": {
                "min_lat": min_lat, "max_lat": max_lat,
                "min_lon": min_lon, "max_lon": max_lon,
            },
        }, 200
    except ValueError as exc:
        return error(str(exc), 422)
    except Exception:
        return error("Risk engine failed", 500)


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
    if time_window not in ("24h", "72h", "7d"):
        return error("time_window must be '24h' or '7d'", 422)

    min_mag_val = request.args.get("min_magnitude")
    try:
        min_magnitude = float(min_mag_val) if min_mag_val is not None else 4.0
    except (ValueError, TypeError):
        return error("min_magnitude must be a number", 400)

    mainshock_id = request.args.get("mainshock_id") or request.args.get("trigger_event_id")

    try:
        risk_service = current_app.extensions["risk_service"]
        result = risk_service.calculate_risk(
            lat=lat,
            lon=lon,
            radius_km=radius_km,
            time_window=time_window,
            min_magnitude=min_magnitude,
            mainshock_id=mainshock_id,
        )
        return result, 200
    except Exception as exc:
        return error("Risk engine failed", 500)


@risk_bp.get("/risk/verdict")
def get_risk_verdict():
    """Get the Civil Defense Situation Verdict and Emergency Guidance."""
    lat_val = request.args.get("lat")
    lon_val = request.args.get("lon")
    time_window = request.args.get("time_window", "24h")
    min_mag_val = request.args.get("min_magnitude")

    try:
        min_magnitude = float(min_mag_val) if min_mag_val is not None else 4.0
    except (ValueError, TypeError):
        return error("min_magnitude must be a number", 400)

    if lat_val is not None and lon_val is not None:
        try:
            lat = float(lat_val)
            lon = float(lon_val)
        except (ValueError, TypeError):
            return error("lat and lon must be numbers", 400)
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            return error("latitude and longitude out of range", 422)

        risk_service = current_app.extensions["risk_service"]
        res = risk_service.calculate_risk(lat=lat, lon=lon, time_window=time_window, min_magnitude=min_magnitude)
        return {
            "verdict": res.get("verdict"),
            "guidance": res.get("guidance"),
            "public_zone": res.get("public_zone"),
            "excavation_action": res.get("excavation_action"),
            "probability_24h": res.get("zones", [{}])[0].get("probability_24h", 0.0),
            "as_of": res.get("generated_at"),
            "center": {"lat": lat, "lon": lon},
        }, 200

    min_lat_val = request.args.get("min_lat")
    max_lat_val = request.args.get("max_lat")
    min_lon_val = request.args.get("min_lon")
    max_lon_val = request.args.get("max_lon")
    if all(v is not None for v in (min_lat_val, max_lat_val, min_lon_val, max_lon_val)):
        try:
            min_lat = float(min_lat_val)
            max_lat = float(max_lat_val)
            min_lon = float(min_lon_val)
            max_lon = float(max_lon_val)
            resolution = float(request.args.get("resolution", 0.2))
        except (ValueError, TypeError):
            return error("Bounding box coordinates must be numbers", 400)

        risk_service = current_app.extensions["risk_service"]
        res = risk_service.calculate_grid(
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            resolution=resolution,
            time_window=time_window,
            min_magnitude=min_magnitude,
        )
        return {
            "verdict": res.get("verdict"),
            "guidance": res.get("guidance"),
            "public_zone": res.get("public_zone"),
            "excavation_action": res.get("excavation_action"),
            "as_of": res.get("guidance", {}).get("as_of"),
        }, 200

    return error("Either lat/lon or min_lat/max_lat/min_lon/max_lon are required", 400)


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
    if time_window not in ("24h", "7d", "72h"):
        return error("time_window must be '24h', '72h', or '7d'", 422)

    min_mag_val = request.args.get("min_magnitude")
    try:
        min_magnitude = float(min_mag_val) if min_mag_val is not None else 4.0
    except (ValueError, TypeError):
        return error("min_magnitude must be a number", 400)

    mainshock_id = request.args.get("mainshock_id") or request.args.get("trigger_event_id")

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
            mainshock_id=mainshock_id,
        )

        output_format = request.args.get("format", "json").lower()
        if output_format == "geojson":
            features = [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [cell["lon"], cell["lat"]],
                    },
                    "properties": {
                        "risk_score": cell["risk_score"],
                        "risk_level": cell.get("risk_level", "low"),
                        "relative_risk": cell.get("relative_risk", 1.0),
                        "expected_rate": cell.get("expected_rate", 0.0),
                        "expected_rate_unit": cell.get("expected_rate_unit", "events/day"),
                        "expected_events": cell.get("expected_events", 0.0),
                        "probability": cell.get("probability", cell.get("probability_24h", 0.0)),
                        "probability_24h": cell.get("probability_24h", 0.0),
                        "probability_7d": cell.get("probability_7d", 0.0),
                        "data_quality": cell.get("data_quality", "nominal"),
                    },
                }
                for cell in result["grid"]
            ]
            return {
                "type": "FeatureCollection",
                "time_window": time_window,
                "min_magnitude": min_magnitude,
                "mainshock_id": result.get("mainshock_id"),
                "model": result.get("model", "omori-style-v1"),
                "data_source": result.get("data_source", "USGS ComCat & Edge Cache"),
                "catalog_freshness": result.get("catalog_freshness"),
                "generated_at": result.get("generated_at"),
                "limitations": result.get("limitations", []),
                "features": features,
            }, 200

        return result, 200
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return error("Risk engine failed", 500)


@risk_bp.get("/model/params")
@risk_bp.get("/risk/params")
def get_model_params():
    risk_service = current_app.extensions.get("risk_service")
    if not risk_service:
        return error("Risk service not initialized", 500)
    params = getattr(risk_service, "params", None)
    return {
        "model_name": "quack-risk-etas-v1",
        "model": getattr(risk_service, "model_name", "omori-style-v1"),
        "params": {
            "k": getattr(params, "k", risk_service.k),
            "c_days": getattr(params, "c_days", risk_service.c_days),
            "p": getattr(params, "p", risk_service.p),
            "alpha": getattr(params, "alpha", risk_service.alpha),
            "magnitude_threshold": getattr(params, "magnitude_threshold", 4.0),
            "recent_window_days": getattr(params, "recent_window_days", risk_service.recent_window_days),
            "kernel": getattr(params, "kernel", "powerlaw"),
        },
    }, 200


@risk_bp.post("/model/calibrate")
@risk_bp.post("/risk/calibrate")
def calibrate_model():
    body = request.get_json(silent=True) or {}
    try:
        min_magnitude = float(body.get("min_magnitude", 4.0))
        n_days = int(body.get("n_days", 10))
        maxiter = int(body.get("maxiter", 15))

        repository = current_app.extensions["event_repository"]
        all_events = repository.list_events(limit=10000)
        cat_events = [e for e in all_events if e.source != "user_report" and not e.event_id.startswith("local_")]
        if not cat_events:
            return error("No catalog events available for calibration", 400)

        from pathlib import Path
        import pandas as pd
        from quack_risk.calibrate import fit_catalog, write_params

        cat_df = pd.DataFrame([
            {
                "id": e.event_id,
                "time": e.origin_time.isoformat(),
                "latitude": e.latitude,
                "longitude": e.longitude,
                "depth_km": e.depth_km if e.depth_km is not None else 10.0,
                "magnitude": e.magnitude if e.magnitude is not None else 4.0,
                "mag_type": e.magnitude_type or "ml",
                "source": "usgs",
            }
            for e in cat_events
        ])

        min_lat = body.get("min_lat")
        max_lat = body.get("max_lat")
        min_lon = body.get("min_lon")
        max_lon = body.get("max_lon")
        resolution = float(body.get("resolution", 0.2))

        if min_lat is None or max_lat is None or min_lon is None or max_lon is None:
            lats = [e.latitude for e in cat_events]
            lons = [e.longitude for e in cat_events]
            bounds = (
                max(-180.0, min(lons) - 1.0),
                max(-90.0, min(lats) - 1.0),
                min(180.0, max(lons) + 1.0),
                min(90.0, max(lats) + 1.0),
            )
        else:
            bounds = (float(min_lon), float(min_lat), float(max_lon), float(max_lat))

        fit_result = fit_catalog(
            cat_df,
            bounds=bounds,
            resolution_deg=resolution,
            n_days=n_days,
            magnitude_threshold=min_magnitude,
            maxiter=maxiter,
        )

        cache_dir = Path(__file__).resolve().parents[3] / "model" / "data" / "cache"
        params_path = cache_dir / "params.json"
        write_params(fit_result, params_path)

        risk_service = current_app.extensions.get("risk_service")
        if risk_service and hasattr(risk_service, "reload_params"):
            risk_service.reload_params()

        return {
            "status": "calibrated",
            "model_name": "quack-risk-etas-v1",
            "fitted_params": {
                "k": round(fit_result.params.k, 6),
                "c_days": round(fit_result.params.c_days, 6),
                "p": round(fit_result.params.p, 6),
                "alpha": round(fit_result.params.alpha, 6),
                "magnitude_threshold": fit_result.params.magnitude_threshold,
            },
            "log_likelihood": round(fit_result.log_likelihood, 2),
            "baseline_log_likelihood": round(fit_result.baseline_log_likelihood, 2),
            "mainshock_origin": fit_result.origin,
            "n_days": fit_result.n_days,
            "n_observed": fit_result.n_observed,
            "message": "Omori ETAS parameters successfully calibrated against catalog.",
        }, 200
    except Exception as exc:
        return error(f"Calibration failed: {exc}", 500)
