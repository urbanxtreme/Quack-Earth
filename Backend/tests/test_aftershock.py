import pytest
from datetime import datetime, timezone, timedelta
from app import create_app
from app.config import Config
from app.models.event import Event


class AppTestConfig(Config):
    TESTING = True

    def __init__(self, db_path):
        self.DATABASE_PATH = db_path


@pytest.fixture
def app(tmp_path):
    db_file = str(tmp_path / "test_aftershock_cache.db")
    test_config = AppTestConfig(db_file)
    app = create_app(test_config)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_faults_endpoint(client):
    """Test /faults and /map/faults endpoints return verified active faults."""
    res = client.get("/faults")
    assert res.status_code == 200
    data = res.get_json()
    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert len(data["features"]) > 0

    # Test bounding box query on Turkey region
    res_bbox = client.get("/faults?min_lat=35&max_lat=40&min_lon=34&max_lon=40")
    assert res_bbox.status_code == 200
    bbox_data = res_bbox.get_json()
    assert len(bbox_data["features"]) > 0
    fault_names = [f["properties"]["name"] for f in bbox_data["features"]]
    assert any("Anatolian" in name for name in fault_names)

    # Test /map/faults alias
    res_map = client.get("/map/faults")
    assert res_map.status_code == 200


def test_sequence_endpoint_with_populated_events(app, client):
    """Test /events/<event_id>/sequence endpoint."""
    now = datetime.now(timezone.utc)
    mainshock_time = now - timedelta(days=2)

    events = [
        Event(
            event_id="mainshock-1",
            origin_time=mainshock_time,
            latitude=37.2,
            longitude=37.0,
            magnitude=7.8,
            depth_km=10.0,
            magnitude_type="mw",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
            place="Kahramanmaras, Turkey",
        ),
        # Foreshock 1 hour before
        Event(
            event_id="foreshock-1",
            origin_time=mainshock_time - timedelta(hours=1),
            latitude=37.15,
            longitude=36.95,
            magnitude=4.5,
            depth_km=12.0,
            magnitude_type="ml",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
            place="Kahramanmaras Foreshock",
        ),
        # Aftershock 1: 2 hours after
        Event(
            event_id="aftershock-1",
            origin_time=mainshock_time + timedelta(hours=2),
            latitude=37.3,
            longitude=37.1,
            magnitude=6.7,
            depth_km=11.0,
            magnitude_type="mw",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
            place="Aftershock 1",
        ),
        # Aftershock 2: 12 hours after
        Event(
            event_id="aftershock-2",
            origin_time=mainshock_time + timedelta(hours=12),
            latitude=37.4,
            longitude=37.2,
            magnitude=5.8,
            depth_km=8.0,
            magnitude_type="mb",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
            place="Aftershock 2",
        ),
        # Far background event
        Event(
            event_id="bg-far-1",
            origin_time=mainshock_time + timedelta(hours=5),
            latitude=10.0,
            longitude=10.0,
            magnitude=5.0,
            depth_km=15.0,
            magnitude_type="mb",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
            place="Distant Atlantic Event",
        ),
    ]

    with app.app_context():
        repo = app.extensions["event_repository"]
        repo.upsert_events(events)

    res = client.get("/events/mainshock-1/sequence")
    assert res.status_code == 200
    data = res.get_json()
    assert data["mainshock"]["id"] == "mainshock-1"
    assert data["foreshock_count"] == 1
    assert data["aftershock_count"] == 2
    assert "omori_fit" in data
    assert data["omori_fit"]["k"] > 0
    assert "geometry" in data
    assert "strike_deg" in data["geometry"]


def test_omori_temporal_decay_in_risk_service(app):
    """Test that Omori risk decays over elapsed time t from mainshock."""
    with app.app_context():
        risk_service = app.extensions["risk_service"]
        repo = app.extensions["event_repository"]

        now = datetime.now(timezone.utc)
        # Sequence A: Mainshock occurred 3 hours ago
        recent_mainshock = Event(
            event_id="recent-ms",
            origin_time=now - timedelta(hours=3),
            latitude=35.0,
            longitude=139.0,
            magnitude=7.0,
            depth_km=10.0,
            magnitude_type="mw",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
        )
        # Sequence B: Mainshock occurred 10 days ago
        old_mainshock = Event(
            event_id="old-ms",
            origin_time=now - timedelta(days=10),
            latitude=35.0,
            longitude=139.0,
            magnitude=7.0,
            depth_km=10.0,
            magnitude_type="mw",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
        )

        # Clear repo and evaluate recent
        repo.clear_cache()
        repo.upsert_events([recent_mainshock])
        risk_recent = risk_service.calculate_risk(lat=35.0, lon=139.0, time_window="24h", min_magnitude=4.0)

        # Clear repo and evaluate old
        repo.clear_cache()
        repo.upsert_events([old_mainshock])
        risk_old = risk_service.calculate_risk(lat=35.0, lon=139.0, time_window="24h", min_magnitude=4.0)

        rate_recent = risk_recent["zones"][0]["expected_events"]
        rate_old = risk_old["zones"][0]["expected_events"]
        # Expected rate for recent mainshock must be higher than rate 10 days later
        assert rate_recent > rate_old


def test_spatial_distance_attenuation_in_risk_service(app):
    """Test that expected risk decreases with distance from rupture / mainshock."""
    with app.app_context():
        risk_service = app.extensions["risk_service"]
        repo = app.extensions["event_repository"]

        now = datetime.now(timezone.utc)
        ms = Event(
            event_id="ms-spatial",
            origin_time=now - timedelta(hours=6),
            latitude=36.0,
            longitude=139.0,
            magnitude=7.2,
            depth_km=12.0,
            magnitude_type="mw",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
        )
        repo.upsert_events([ms])

        # Point near epicenter (~5 km away)
        risk_near = risk_service.calculate_risk(lat=36.04, lon=139.0, time_window="24h", min_magnitude=4.0)
        # Point far from epicenter (~200 km away)
        risk_far = risk_service.calculate_risk(lat=37.8, lon=139.0, time_window="24h", min_magnitude=4.0)

        rate_near = risk_near["zones"][0]["expected_events"]
        rate_far = risk_far["zones"][0]["expected_events"]
        assert rate_near > rate_far


def test_magnitude_threshold_scaling(app):
    """Test that higher min_magnitude threshold yields strictly lower or equal expected event counts."""
    with app.app_context():
        risk_service = app.extensions["risk_service"]
        repo = app.extensions["event_repository"]

        now = datetime.now(timezone.utc)
        ms = Event(
            event_id="ms-mag-scaling",
            origin_time=now - timedelta(hours=6),
            latitude=36.0,
            longitude=139.0,
            magnitude=7.5,
            depth_km=10.0,
            magnitude_type="mw",
            review_status="reviewed",
            source="usgs",
            fetched_at=now,
        )
        repo.upsert_events([ms])

        risk_m4 = risk_service.calculate_risk(lat=36.0, lon=139.0, time_window="24h", min_magnitude=4.0)
        risk_m5 = risk_service.calculate_risk(lat=36.0, lon=139.0, time_window="24h", min_magnitude=5.0)
        risk_m6 = risk_service.calculate_risk(lat=36.0, lon=139.0, time_window="24h", min_magnitude=6.0)

        rate_m4 = risk_m4["zones"][0]["expected_events"]
        rate_m5 = risk_m5["zones"][0]["expected_events"]
        rate_m6 = risk_m6["zones"][0]["expected_events"]

        assert rate_m4 >= rate_m5 >= rate_m6


def test_empty_catalog_edge_case(app, client):
    """Test that risk calculation handles empty catalog gracefully without crashing."""
    with app.app_context():
        repo = app.extensions["event_repository"]
        repo.clear_cache()

    res = client.get("/risk?lat=35.0&lon=139.0&time_window=24h&min_magnitude=4.0")
    assert res.status_code == 200
    data = res.get_json()
    assert "zones" in data
    assert len(data["zones"]) == 1
    assert data["zones"][0]["risk_score"] >= 0.0

    res_grid = client.get("/risk/grid?min_lat=34&max_lat=36&min_lon=138&max_lon=140&resolution=1.0&format=geojson")
    assert res_grid.status_code == 200
    grid_data = res_grid.get_json()
    assert grid_data["type"] == "FeatureCollection"
    assert len(grid_data["features"]) > 0
