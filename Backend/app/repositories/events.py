import csv
import sqlite3
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path
from typing import Iterable

from ..models.event import Event


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class EventRepository:
    def __init__(self, database_path: str):
        self.database_path = database_path

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self):
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, origin_time TEXT NOT NULL,
                    latitude REAL NOT NULL, longitude REAL NOT NULL,
                    depth_km REAL, magnitude REAL, magnitude_type TEXT,
                    review_status TEXT, source TEXT NOT NULL, fetched_at TEXT NOT NULL,
                    note TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_origin_time ON events(origin_time);
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY, value TEXT
                );
                """
            )
            # Ensure note column exists for existing databases
            cols = [row[1] for row in connection.execute("PRAGMA table_info(events)").fetchall()]
            if "note" not in cols:
                connection.execute("ALTER TABLE events ADD COLUMN note TEXT")

        self._seed_if_empty()

    def _seed_if_empty(self):
        # If database is empty, seed with the repository fixture if available
        meta = self.metadata()
        if meta["event_count"] == 0:
            fixture_path = Path(__file__).resolve().parents[3] / "model" / "data" / "fixtures" / "catalog.csv"
            if fixture_path.exists():
                try:
                    events = []
                    now = datetime.now(timezone.utc)
                    with open(fixture_path, mode="r", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            events.append(
                                Event(
                                    event_id=row["id"],
                                    origin_time=_timestamp(row["time"]),
                                    latitude=float(row["latitude"]),
                                    longitude=float(row["longitude"]),
                                    depth_km=float(row["depth_km"]) if row.get("depth_km") else None,
                                    magnitude=float(row["magnitude"]) if row.get("magnitude") else None,
                                    magnitude_type=row.get("mag_type"),
                                    review_status="reviewed",
                                    source=row.get("source", "usgs"),
                                    fetched_at=now,
                                )
                            )
                    if events:
                        self.upsert_events(events)
                        self.set_metadata({
                            "last_successful_sync": now.isoformat().replace("+00:00", "Z"),
                            "source": "usgs",
                        })
                except Exception:
                    pass

    def upsert_events(self, events: Iterable[Event]):
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                origin_time=excluded.origin_time, latitude=excluded.latitude,
                longitude=excluded.longitude, depth_km=excluded.depth_km,
                magnitude=excluded.magnitude, magnitude_type=excluded.magnitude_type,
                review_status=excluded.review_status, source=excluded.source,
                fetched_at=excluded.fetched_at, note=excluded.note""",
                [
                    (
                        e.event_id, e.origin_time.isoformat(), e.latitude, e.longitude,
                        e.depth_km, e.magnitude, e.magnitude_type, e.review_status,
                        e.source, e.fetched_at.isoformat(), getattr(e, "note", None),
                    )
                    for e in events
                ],
            )

    def get_next_local_event_id(self) -> str:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT event_id FROM events WHERE event_id LIKE 'local_%'"
            ).fetchall()
            max_num = 0
            for r in rows:
                eid = r["event_id"]
                parts = eid.split("_", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    max_num = max(max_num, int(parts[1]))
            return f"local_{max_num + 1:03d}"

    def list_events(self, start: datetime | None = None, end: datetime | None = None,
                    min_magnitude: float | None = None,
                    latitude: float | None = None, longitude: float | None = None,
                    radius_km: float | None = None, limit: int = 5000) -> list[Event]:
        clauses, values = [], []
        if start:
            clauses.append("origin_time >= ?")
            values.append(start.isoformat())
        if end:
            clauses.append("origin_time <= ?")
            values.append(end.isoformat())
        if min_magnitude is not None:
            clauses.append("magnitude >= ?")
            values.append(min_magnitude)
        query = "SELECT * FROM events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY origin_time DESC LIMIT ?"
        values.append(limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        events = [self._from_row(row) for row in rows]
        if latitude is not None and longitude is not None and radius_km is not None:
            from ..services.risk import haversine_km
            events = [e for e in events if haversine_km(latitude, longitude, e.latitude, e.longitude) <= radius_km]
        return events

    def get_event(self, event_id: str) -> Event | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return self._from_row(row) if row else None

    def metadata(self) -> dict[str, str | int | None]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT key, value FROM cache_metadata").fetchall()
            total_count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            local_count = connection.execute(
                "SELECT COUNT(*) FROM events WHERE source = 'user_report' OR event_id LIKE 'local_%'"
            ).fetchone()[0]
            cached_count = total_count - local_count
        data = {row["key"]: row["value"] for row in rows}
        data["event_count"] = total_count
        data["cached_events"] = cached_count
        data["local_events_added"] = local_count
        return data

    def set_metadata(self, values: dict[str, str]):
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT INTO cache_metadata(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values.items(),
            )

    @staticmethod
    def _from_row(row):
        col_keys = row.keys() if hasattr(row, "keys") else []
        note = row["note"] if "note" in col_keys else None
        return Event(
            row["event_id"], _timestamp(row["origin_time"]), row["latitude"], row["longitude"],
            row["depth_km"], row["magnitude"], row["magnitude_type"], row["review_status"],
            row["source"], _timestamp(row["fetched_at"]), note,
        )
