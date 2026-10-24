from flask import Blueprint, current_app

from ..services.catalog import check_online

status_bp = Blueprint("status", __name__)


@status_bp.get("/status")
@status_bp.get("/health")
def status():
    repository = current_app.extensions["event_repository"]
    meta = repository.metadata()
    online = check_online()
    mode = "online" if online else "offline"
    last_update = meta.get("last_successful_sync")
    risk_service = current_app.extensions.get("risk_service")
    model_name = getattr(risk_service, "model_name", "quack-risk-etas-v1") if risk_service else "quack-risk-etas-v1"

    return {
        "status": "ok",
        "mode": mode,
        "cached_events": meta.get("cached_events", 0),
        "event_count": meta.get("cached_events", 0),
        "local_events_added": meta.get("local_events_added", 0),
        "last_catalog_update": last_update or None,
        "source": "USGS ComCat",
        "model": "omori-style-v1",
        "model_name": model_name,
    }, 200
