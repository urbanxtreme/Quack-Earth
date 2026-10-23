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
                    review_status TEXT, source TEXT NOT NULL, fetched_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_origin_time ON events(origin_time);
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY, value TEXT
                );
                """
            )

    def upsert_events(self, events: Iterable[Event]):
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                origin_time=excluded.origin_time, latitude=excluded.latitude,
                longitude=excluded.longitude, depth_km=excluded.depth_km,
                magnitude=excluded.magnitude, magnitude_type=excluded.magnitude_type,
                review_status=excluded.review_status, source=excluded.source,
                fetched_at=excluded.fetched_at""",
                [
                    (
                        e.event_id, e.origin_time.isoformat(), e.latitude, e.longitude,
                        e.depth_km, e.magnitude, e.magnitude_type, e.review_status,
                        e.source, e.fetched_at.isoformat(),
                    )
                    for e in events
                ],
            )

    def list_events(self, start: datetime | None = None, end: datetime | None = None,
                    latitude: float | None = None, longitude: float | None = None,
                    radius_km: float | None = None, limit: int = 5000) -> list[Event]:
        clauses, values = [], []
        if start:
            clauses.append("origin_time >= ?")
            values.append(start.isoformat())
        if end:
            clauses.append("origin_time <= ?")
            values.append(end.isoformat())
        query = "SELECT * FROM events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY origin_time DESC LIMIT ?"
        values.append(limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(query, values).fetchall()
        events = [self._from_row(row) for row in rows]
        if latitude is not None and longitude is not None and radius_km is not None:
            from ..services.forecast import haversine_km
            events = [e for e in events if haversine_km(latitude, longitude, e.latitude, e.longitude) <= radius_km]
        return events

    def get_event(self, event_id: str) -> Event | None:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM events WHERE event_id = ?", (event_id,)).fetchone()
        return self._from_row(row) if row else None

    def metadata(self) -> dict[str, str | int | None]:
        with closing(self._connect()) as connection, connection:
            rows = connection.execute("SELECT key, value FROM cache_metadata").fetchall()
            count = connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        data = {row["key"]: row["value"] for row in rows}
        data["event_count"] = count
        return data

    def set_metadata(self, values: dict[str, str]):
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT INTO cache_metadata(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                values.items(),
            )

    @staticmethod
    def _from_row(row):
        return Event(
            row["event_id"], _timestamp(row["origin_time"]), row["latitude"], row["longitude"],
            row["depth_km"], row["magnitude"], row["magnitude_type"], row["review_status"],
            row["source"], _timestamp(row["fetched_at"]),
        )
