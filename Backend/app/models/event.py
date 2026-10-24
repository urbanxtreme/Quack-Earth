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
    horizontal_error_km: float | None = None
    depth_error_km: float | None = None
    mag_error: float | None = None
    azimuthal_gap: float | None = None
    dmin: float | None = None
    rms: float | None = None
    nst: int | None = None
    event_type: str | None = "earthquake"

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
        is_usgs = "usgs" in self.source.lower() or not (self.source == "user_report" or self.event_id.startswith("local_"))
        corroboration = {
            "status": "usgs_verified" if is_usgs else ("sensor_corroborated" if (self.magnitude or 0) >= 4.0 else "crowd_report"),
            "label": "USGS ComCat Network" if is_usgs else ("Edge Multimodal Node" if (self.magnitude or 0) >= 4.0 else "Citizen Felt Report"),
            "confidence": 1.0 if is_usgs else (0.88 if (self.magnitude or 0) >= 4.0 else 0.65),
            "station_count": self.nst if (self.nst and is_usgs) else (28 if is_usgs else (4 if (self.magnitude or 0) >= 4.0 else 1)),
        }
        data: dict[str, Any] = {
            "id": self.event_id,
            "time": self.origin_time.isoformat().replace("+00:00", "Z"),
            "lat": self.latitude,
            "lon": self.longitude,
            "magnitude": self.magnitude if self.magnitude is not None else 0.0,
            "magnitude_type": self.magnitude_type,
            "source": "usgs" if is_usgs else self.source,
            "event_type": self.event_type or "earthquake",
            "review_status": self.review_status,
            "place": self.place or (self.note if self.note else f"Region near {self.latitude:.2f}°, {self.longitude:.2f}°"),
            "corroboration": corroboration,
        }
        if self.depth_km is not None:
            data["depth_km"] = self.depth_km
        if self.note:
            data["note"] = self.note

        # Scientific uncertainty and telemetry metadata
        uncertainty: dict[str, Any] = {}
        if self.horizontal_error_km is not None:
            uncertainty["horizontal_error_km"] = self.horizontal_error_km
        if self.depth_error_km is not None:
            uncertainty["depth_error_km"] = self.depth_error_km
        if self.mag_error is not None:
            uncertainty["mag_error"] = self.mag_error
        if self.azimuthal_gap is not None:
            uncertainty["azimuthal_gap"] = self.azimuthal_gap
        if self.dmin is not None:
            uncertainty["dmin"] = self.dmin
        if self.rms is not None:
            uncertainty["rms"] = self.rms
        if self.nst is not None:
            uncertainty["nst"] = self.nst

        if uncertainty:
            data["uncertainty"] = uncertainty

        return data
