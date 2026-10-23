from pathlib import Path

from flask import Flask

from .config import Config
from .repositories.events import EventRepository
from .routes.events import events_bp
from .routes.forecasts import forecasts_bp
from .routes.health import health_bp
from .services.catalog import CatalogService
from .services.forecast import ForecastService


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or Config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    repository = EventRepository(app.config["DATABASE_PATH"])
    repository.initialize()
    catalog = CatalogService(repository, app.config["USGS_EVENT_URL"])
    forecast = ForecastService(repository)
    app.extensions["event_repository"] = repository
    app.extensions["catalog_service"] = catalog
    app.extensions["forecast_service"] = forecast

    app.register_blueprint(health_bp, url_prefix="/api/v1")
    app.register_blueprint(events_bp, url_prefix="/api/v1")
    app.register_blueprint(forecasts_bp, url_prefix="/api/v1")

    @app.errorhandler(404)
    def not_found(_error):
        return {"error": {"code": "not_found", "message": "The requested endpoint does not exist"}}, 404

    @app.errorhandler(405)
    def method_not_allowed(_error):
        return {"error": {"code": "method_not_allowed", "message": "The HTTP method is not supported"}}, 405

    return app
