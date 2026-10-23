from pathlib import Path

from flask import Flask
from flask_cors import CORS

from .config import Config
from .repositories.events import EventRepository
from .routes.events import events_bp
from .routes.forecasts import forecasts_bp
from .routes.health import status_bp
from .routes.risk import risk_bp
from .routes.scenarios import scenarios_bp
from .services.catalog import CatalogService
from .services.forecast import ForecastService
from .services.risk import RiskService


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    CORS(app)

    repository = EventRepository(app.config["DATABASE_PATH"])
    repository.initialize()
    catalog = CatalogService(repository, app.config["USGS_EVENT_URL"])
    forecast = ForecastService(repository)
    risk = RiskService(repository)

    app.extensions["event_repository"] = repository
    app.extensions["catalog_service"] = catalog
    app.extensions["forecast_service"] = forecast
    app.extensions["risk_service"] = risk

    if not app.config.get("TESTING"):
        import threading

        def _initial_usgs_sync():
            try:
                from .services.catalog import check_online
                if check_online():
                    catalog.refresh(min_magnitude=2.5, days_back=30)
            except Exception:
                pass

        threading.Thread(target=_initial_usgs_sync, daemon=True).start()

    # Register root routes (/status, /risk, /events, /local-event, /refresh-catalog, /risk/grid, /scenarios)
    app.register_blueprint(status_bp)
    app.register_blueprint(risk_bp)
    app.register_blueprint(events_bp)
    app.register_blueprint(forecasts_bp)
    app.register_blueprint(scenarios_bp)

    # Register with /api prefix for direct frontend calls
    app.register_blueprint(status_bp, url_prefix="/api", name="status_api")
    app.register_blueprint(risk_bp, url_prefix="/api", name="risk_api")
    app.register_blueprint(events_bp, url_prefix="/api", name="events_api")
    app.register_blueprint(forecasts_bp, url_prefix="/api", name="forecasts_api")
    app.register_blueprint(scenarios_bp, url_prefix="/api", name="scenarios_api")

    # Also register with /api/v1 and /v1 prefix for compatibility
    app.register_blueprint(status_bp, url_prefix="/api/v1", name="status_v1")
    app.register_blueprint(risk_bp, url_prefix="/api/v1", name="risk_v1")
    app.register_blueprint(events_bp, url_prefix="/api/v1", name="events_v1")
    app.register_blueprint(forecasts_bp, url_prefix="/api/v1", name="forecasts_v1")
    app.register_blueprint(scenarios_bp, url_prefix="/api/v1", name="scenarios_v1")

    app.register_blueprint(status_bp, url_prefix="/v1", name="status_v1_short")
    app.register_blueprint(risk_bp, url_prefix="/v1", name="risk_v1_short")
    app.register_blueprint(events_bp, url_prefix="/v1", name="events_v1_short")
    app.register_blueprint(forecasts_bp, url_prefix="/v1", name="forecasts_v1_short")
    app.register_blueprint(scenarios_bp, url_prefix="/v1", name="scenarios_v1_short")

    @app.errorhandler(404)
    def not_found(_error):
        return {"error": "Endpoint not found", "message": "Endpoint not found"}, 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return {"error": "Method not allowed", "message": "Method not allowed"}, 405

    @app.errorhandler(500)
    def server_error(_error):
        return {"error": "Risk engine failed", "message": "Risk engine failed"}, 500

    return app
