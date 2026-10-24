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
                    note TEXT, place TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_events_origin_time ON events(origin_time);
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    key TEXT PRIMARY KEY, value TEXT
                );
                """
            )
            # Ensure note, place, and scientific uncertainty columns exist for existing databases
            cols = [row[1] for row in connection.execute("PRAGMA table_info(events)").fetchall()]
            extra_cols = [
                ("note", "TEXT"),
                ("place", "TEXT"),
                ("horizontal_error_km", "REAL"),
                ("depth_error_km", "REAL"),
                ("mag_error", "REAL"),
                ("azimuthal_gap", "REAL"),
                ("dmin", "REAL"),
                ("rms", "REAL"),
                ("nst", "INTEGER"),
                ("event_type", "TEXT"),
            ]
            for col_name, col_type in extra_cols:
                if col_name not in cols:
                    connection.execute(f"ALTER TABLE events ADD COLUMN {col_name} {col_type}")

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
                            place = row.get("place")
                            if not place:
                                place = f"Kahramanmaras Region, Turkey ({float(row['latitude']):.2f}°N, {float(row['longitude']):.2f}°E)"
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
                                    note=None,
                                    place=place,
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
        self.export_model_cache()

    def clear_cache(self):
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM cache_metadata")

    def export_model_cache(self):
        cache_dir = Path(__file__).resolve().parents[3] / "model" / "data" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            import json
            all_events = self.list_events(limit=50000)
            catalog_path = cache_dir / "catalog.csv"
            signals_path = cache_dir / "signals.json"

            cat_events = [e for e in all_events if e.source != "user_report" and not e.event_id.startswith("local_")]
            if cat_events:
                with open(catalog_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(["id", "time", "latitude", "longitude", "depth_km", "magnitude", "mag_type", "source"])
                    for e in sorted(cat_events, key=lambda x: x.origin_time):
                        writer.writerow([
                            e.event_id,
                            e.origin_time.isoformat().replace("+00:00", "Z"),
                            e.latitude,
                            e.longitude,
                            e.depth_km if e.depth_km is not None else 10.0,
                            e.magnitude if e.magnitude is not None else 4.0,
                            e.magnitude_type or "",
                            "usgs" if "usgs" in e.source.lower() else "local",
                        ])

            # Merge existing signals so no offline signals are lost
            existing_signals = {}
            if signals_path.exists():
                try:
                    loaded = json.loads(signals_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, list):
                        for item in loaded:
                            if isinstance(item, dict) and "id" in item:
                                existing_signals[item["id"]] = item
                except Exception:
                    pass

            local_events = [e for e in all_events if e.source == "user_report" or e.event_id.startswith("local_")]
            for e in sorted(local_events, key=lambda x: x.origin_time):
                sig_type = "accelerometer" if (e.magnitude_type == "accelerometer" or (e.note and "accelerometer" in e.note.lower())) else "report"
                existing_signals[e.event_id] = {
                    "id": e.event_id,
                    "time": e.origin_time.isoformat().replace("+00:00", "Z"),
                    "latitude": e.latitude,
                    "longitude": e.longitude,
                    "signal_type": sig_type,
                    "confidence": 1.0,
                    "equivalent_magnitude": e.magnitude,
                }
            signals_path.write_text(json.dumps(list(existing_signals.values()), indent=2), encoding="utf-8")
        except Exception:
            pass

    def upsert_events(self, events: Iterable[Event]):
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                """INSERT INTO events (
                    event_id, origin_time, latitude, longitude, depth_km, magnitude,
                    magnitude_type, review_status, source, fetched_at, note, place,
                    horizontal_error_km, depth_error_km, mag_error, azimuthal_gap,
                    dmin, rms, nst, event_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id) DO UPDATE SET
                origin_time=excluded.origin_time, latitude=excluded.latitude,
                longitude=excluded.longitude, depth_km=excluded.depth_km,
                magnitude=excluded.magnitude, magnitude_type=excluded.magnitude_type,
                review_status=excluded.review_status, source=excluded.source,
                fetched_at=excluded.fetched_at, note=excluded.note, place=excluded.place,
                horizontal_error_km=excluded.horizontal_error_km, depth_error_km=excluded.depth_error_km,
                mag_error=excluded.mag_error, azimuthal_gap=excluded.azimuthal_gap,
                dmin=excluded.dmin, rms=excluded.rms, nst=excluded.nst, event_type=excluded.event_type""",
                [
                    (
                        e.event_id, e.origin_time.isoformat(), e.latitude, e.longitude,
                        e.depth_km, e.magnitude, e.magnitude_type, e.review_status,
                        e.source, e.fetched_at.isoformat(), getattr(e, "note", None),
                        getattr(e, "place", None),
                        getattr(e, "horizontal_error_km", None),
                        getattr(e, "depth_error_km", None),
                        getattr(e, "mag_error", None),
                        getattr(e, "azimuthal_gap", None),
                        getattr(e, "dmin", None),
                        getattr(e, "rms", None),
                        getattr(e, "nst", None),
                        getattr(e, "event_type", "earthquake"),
                    )
                    for e in events
                ],
            )
        self.export_model_cache()

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
                    min_magnitude: float | None = None, max_magnitude: float | None = None,
                    min_lat: float | None = None, max_lat: float | None = None,
                    min_lon: float | None = None, max_lon: float | None = None,
                    latitude: float | None = None, longitude: float | None = None,
                    radius_km: float | None = None, source: str | None = None,
                    limit: int = 5000, offset: int = 0) -> list[Event]:
        clauses, values = [], []
        if start:
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            clauses.append("origin_time >= ?")
            values.append(start.astimezone(timezone.utc).isoformat())
        if end:
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            clauses.append("origin_time <= ?")
            values.append(end.astimezone(timezone.utc).isoformat())
        if min_magnitude is not None:
            clauses.append("magnitude >= ?")
            values.append(min_magnitude)
        if max_magnitude is not None:
            clauses.append("magnitude <= ?")
            values.append(max_magnitude)
        if min_lat is not None:
            clauses.append("latitude >= ?")
            values.append(min_lat)
        if max_lat is not None:
            clauses.append("latitude <= ?")
            values.append(max_lat)
        if min_lon is not None:
            clauses.append("longitude >= ?")
            values.append(min_lon)
        if max_lon is not None:
            clauses.append("longitude <= ?")
            values.append(max_lon)
        if source:
            if source.lower() == "usgs":
                clauses.append("(source LIKE '%usgs%' AND source != 'user_report' AND event_id NOT LIKE 'local_%')")
            elif source.lower() in ("local", "user_report"):
                clauses.append("(source = 'user_report' OR event_id LIKE 'local_%')")
            else:
                clauses.append("source = ?")
                values.append(source)

        query = "SELECT * FROM events"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY origin_time DESC LIMIT ? OFFSET ?"
        values.extend([limit, offset])
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
        place = row["place"] if "place" in col_keys else None
        h_err = row["horizontal_error_km"] if "horizontal_error_km" in col_keys else None
        d_err = row["depth_error_km"] if "depth_error_km" in col_keys else None
        m_err = row["mag_error"] if "mag_error" in col_keys else None
        gap = row["azimuthal_gap"] if "azimuthal_gap" in col_keys else None
        dmin = row["dmin"] if "dmin" in col_keys else None
        rms = row["rms"] if "rms" in col_keys else None
        nst = row["nst"] if "nst" in col_keys else None
        etype = row["event_type"] if "event_type" in col_keys else "earthquake"

        return Event(
            row["event_id"], _timestamp(row["origin_time"]), row["latitude"], row["longitude"],
            row["depth_km"], row["magnitude"], row["magnitude_type"], row["review_status"],
            row["source"], _timestamp(row["fetched_at"]), note, place,
            horizontal_error_km=h_err, depth_error_km=d_err, mag_error=m_err,
            azimuthal_gap=gap, dmin=dmin, rms=rms, nst=nst, event_type=etype,
        )
