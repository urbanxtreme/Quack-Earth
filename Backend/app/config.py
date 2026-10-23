import os
from pathlib import Path


class Config:
    DATABASE_PATH = os.getenv(
        "EARTHQUAKE_DATABASE_PATH",
        str(Path(__file__).resolve().parents[1] / "instance" / "earthquake_cache.db"),
    )
    USGS_EVENT_URL = os.getenv(
        "USGS_EVENT_URL", "https://earthquake.usgs.gov/fdsnws/event/1/query"
    )
    MAX_EVENTS = 5_000
    MIN_MAGNITUDE = -1.0
    MAX_MAGNITUDE = 10.0
    MAX_QUERY_DAYS = 366
