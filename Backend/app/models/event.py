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

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "origin_time": self.origin_time.isoformat().replace("+00:00", "Z"),
            "latitude": self.latitude,
            "longitude": self.longitude,
            "depth_km": self.depth_km,
            "magnitude": self.magnitude,
            "magnitude_type": self.magnitude_type,
            "review_status": self.review_status,
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat().replace("+00:00", "Z"),
        }
