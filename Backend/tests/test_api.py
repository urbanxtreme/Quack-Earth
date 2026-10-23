import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from app import create_app
from app.config import Config


class AppTestConfig(Config):
    TESTING = True

    def __init__(self, db_path):
        self.DATABASE_PATH = db_path


@pytest.fixture
def app(tmp_path):
    db_file = str(tmp_path / "test_earthquake_cache.db")
    test_config = AppTestConfig(db_file)
    app = create_app(test_config)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_status_endpoint(client):
    response = client.get("/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["mode"] in ("online", "offline")
    assert isinstance(data["cached_events"], int)
    assert isinstance(data["local_events_added"], int)
    assert data["model"] == "omori-style-v1"


def test_status_endpoint_v1_alias(client):
    response = client.get("/api/v1/status")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["model"] == "omori-style-v1"


def test_events_endpoint(client):
    response = client.get("/events?hours=72&min_magnitude=2.0")
    assert response.status_code == 200
    data = response.get_json()
    assert "count" in data
    assert "events" in data
    assert isinstance(data["events"], list)
    if data["events"]:
        event = data["events"][0]
        assert "id" in event
        assert "time" in event
        assert "lat" in event
        assert "lon" in event
        assert "magnitude" in event
        assert "source" in event


def test_add_local_event_and_risk(client):
    payload = {
        "lat": 34.05,
        "lon": -118.25,
        "magnitude": 5.2,
        "time": "2026-10-23T14:30:00Z",
        "source": "user_report",
        "note": "Strong shaking felt",
    }
    response = client.post("/local-event", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["status"] == "added"
    assert data["event_id"].startswith("local_")
    assert data["nearby_risk_updated"] is True

    # Status should reflect 1 local event added
    status_res = client.get("/status")
    status_data = status_res.get_json()
    assert status_data["local_events_added"] >= 1

    # /risk should now calculate short term risk for that center
    risk_res = client.get("/risk?lat=34.05&lon=-118.25&radius_km=40&time_window=24h&min_magnitude=4.0")
    assert risk_res.status_code == 200
    risk_data = risk_res.get_json()
    assert risk_data["time_window"] == "24h"
    assert risk_data["min_magnitude"] == 4.0
    assert risk_data["center"] == {"lat": 34.05, "lon": -118.25}
    assert "baseline_rate" in risk_data
    assert len(risk_data["zones"]) == 1
    zone = risk_data["zones"][0]
    assert 0.0 <= zone["risk_score"] <= 1.0
    assert zone["relative_to_baseline"] >= 0.0
    assert zone["expected_events"] >= 0.0


def test_add_local_event_validation(client):
    # Missing required field
    res = client.post("/local-event", json={"lat": 34.05, "lon": -118.25})
    assert res.status_code == 400
    assert "lat, lon, and magnitude are required" in res.get_json()["error"]

    # Out of range coordinates
    res = client.post("/local-event", json={"lat": 134.05, "lon": -118.25, "magnitude": 4.0})
    assert res.status_code == 422
    assert "range" in res.get_json()["error"].lower()


def test_risk_validation(client):
    # Missing lat/lon
    res = client.get("/risk")
    assert res.status_code == 400
    assert "lat and lon are required" in res.get_json()["error"]

    # Invalid time_window
    res = client.get("/risk?lat=34.05&lon=-118.25&time_window=48h")
    assert res.status_code == 422
    assert "time_window must be '24h' or '7d'" in res.get_json()["error"]


def test_risk_grid_endpoint(client):
    res = client.get("/risk/grid?min_lat=33.5&max_lat=34.5&min_lon=-119.0&max_lon=-117.5&resolution=0.5&time_window=24h")
    assert res.status_code == 200
    data = res.get_json()
    assert data["time_window"] == "24h"
    assert "grid" in data
    assert len(data["grid"]) > 0
    cell = data["grid"][0]
    assert "lat" in cell
    assert "lon" in cell
    assert "risk_score" in cell
    assert 0.0 <= cell["risk_score"] <= 1.0


def test_risk_grid_validation(client):
    # Missing bounds
    res = client.get("/risk/grid?min_lat=33.5")
    assert res.status_code == 400
    assert "required" in res.get_json()["error"]

    # Inverted bounds
    res = client.get("/risk/grid?min_lat=35.0&max_lat=34.0&min_lon=-119.0&max_lon=-117.5")
    assert res.status_code == 400
    assert "min boundaries must be less than max boundaries" in res.get_json()["error"]


def test_risk_heatmap_returns_geojson_cells(client):
    response = client.get(
        "/api/v1/risk/heatmap?min_lat=33.5&max_lat=34.5&min_lon=-119&max_lon=-117.5&resolution=0.5"
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["type"] == "FeatureCollection"
    assert data["count"] == len(data["features"])
    feature = data["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert len(feature["geometry"]["coordinates"][0]) == 5
    assert 0.0 <= feature["properties"]["value"] <= 1.0


def test_risk_heatmap_rejects_invalid_window(client):
    response = client.get(
        "/api/v1/risk/heatmap?min_lat=33&max_lat=34&min_lon=-119&max_lon=-118&time_window=48h"
    )

    assert response.status_code == 422
    assert "time_window" in response.get_json()["error"]


def test_map_events_returns_geojson(client):
    response = client.get(
        "/api/v1/map/events?min_lat=-90&max_lat=90&min_lon=-180&max_lon=180&hours=8784"
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["type"] == "FeatureCollection"
    assert data["count"] == len(data["features"])
    if data["features"]:
        feature = data["features"][0]
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"
        assert len(feature["geometry"]["coordinates"]) == 2
        assert "event_id" in feature["properties"]


def test_map_events_rejects_invalid_bounds(client):
    response = client.get(
        "/api/v1/map/events?min_lat=13&max_lat=12&min_lon=77&max_lon=78"
    )

    assert response.status_code == 422
    assert "not ordered" in response.get_json()["error"]


def test_refresh_catalog_offline(client):
    with patch("requests.get", side_effect=requests.ConnectionError("Connection refused")):
        res = client.post("/refresh-catalog", json={"days_back": 7, "min_magnitude": 3.0})
        assert res.status_code == 503
        data = res.get_json()
        assert data["status"] == "failed"
        assert "No internet connection. Using cached catalog." in data["message"]


def test_refresh_catalog_online_mock(client):
    fake_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "id": "mock_event_1",
                "properties": {
                    "mag": 4.5,
                    "time": 1700000000000,
                    "magType": "ml",
                    "status": "reviewed",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [-118.25, 34.05, 10.0],
                },
            }
        ],
    }

    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return fake_geojson

    with patch("requests.get", return_value=MockResponse()):
        res = client.post("/refresh-catalog", json={"days_back": 14, "min_magnitude": 4.0})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "updated"
        assert data["events_fetched"] == 1
        assert "last_catalog_update" in data
