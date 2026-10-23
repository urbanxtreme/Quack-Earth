from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Event:
    event_id: str
    origin_time: datetime
    latitude: float
    longitude: float
    depth_km: float | None
    magnitude: float | None
    magnitude_type: str | None
    review_status: str | None
    source: str
    fetched_at: datetime
    note: str | None = None
    place: str | None = None

    @property
    def id(self) -> str:
        return self.event_id

    @property
    def time(self) -> datetime:
        return self.origin_time

    @property
    def lat(self) -> float:
        return self.latitude

    @property
    def lon(self) -> float:
        return self.longitude

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.event_id,
            "time": self.origin_time.isoformat().replace("+00:00", "Z"),
            "lat": self.latitude,
            "lon": self.longitude,
            "magnitude": self.magnitude,
            "source": "usgs" if "usgs" in self.source.lower() else self.source,
            "place": self.place or (self.note if self.note else f"Region near {self.latitude:.2f}°, {self.longitude:.2f}°"),
        }
        if self.depth_km is not None:
            data["depth_km"] = self.depth_km
        if self.note:
            data["note"] = self.note
        return data
