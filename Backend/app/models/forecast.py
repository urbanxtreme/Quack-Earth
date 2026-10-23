from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Target:
    latitude: float
    longitude: float
    radius_km: float

    def to_dict(self) -> dict[str, float]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "radius_km": self.radius_km,
        }


@dataclass(frozen=True)
class Forecast:
    target: Target
    window_hours: int
    minimum_magnitude: float
    expected_event_count: float
    probability_at_least_one: float
    baseline_rate_per_day: float
    baseline_event_count: int
    recent_qualifying_event_count: int
    relative_activity_score: float
    data_as_of: str
    model: str
    assumptions: list[str]
    limitations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "window_hours": self.window_hours,
            "minimum_magnitude": self.minimum_magnitude,
            "expected_event_count": self.expected_event_count,
            "probability_at_least_one": self.probability_at_least_one,
            "baseline_rate_per_day": self.baseline_rate_per_day,
            "baseline_event_count": self.baseline_event_count,
            "recent_qualifying_event_count": self.recent_qualifying_event_count,
            "relative_activity_score": self.relative_activity_score,
            "data_as_of": self.data_as_of,
            "model": self.model,
            "assumptions": self.assumptions,
            "limitations": self.limitations,
        }
