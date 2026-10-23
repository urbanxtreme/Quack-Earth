from flask import Blueprint, current_app

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    metadata = current_app.extensions["event_repository"].metadata()
    return {
        "status": "ok",
        "cache": {
            "has_events": metadata["event_count"] > 0,
            "event_count": metadata["event_count"],
            "last_successful_sync": metadata.get("last_successful_sync"),
            "last_sync_error": metadata.get("last_sync_error") or None,
            "source": metadata.get("source", "USGS ComCat"),
        },
    }
