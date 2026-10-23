import math
from datetime import datetime, timedelta, timezone

import numpy as np

from ..models.forecast import Forecast, Target


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


class ForecastService:
    def __init__(self, repository):
        self.repository = repository

    def calculate(self, trigger_event, target, window_hours, minimum_magnitude):
        now = trigger_event.origin_time
        historical_start = now - timedelta(days=30)
        historical = self.repository.list_events(start=historical_start, end=now)
        relevant = [
            event for event in historical
            if event.magnitude is not None and event.magnitude >= minimum_magnitude
            and haversine_km(target.latitude, target.longitude, event.latitude, event.longitude) <= target.radius_km
        ]
        baseline_rate = len(relevant) / 30.0
        recent = self.repository.list_events(start=now, end=now + timedelta(days=7))
        contributions = []
        for event in recent:
            if event.event_id == trigger_event.event_id or event.magnitude is None or event.magnitude < minimum_magnitude:
                continue
            distance = haversine_km(target.latitude, target.longitude, event.latitude, event.longitude)
            if distance <= target.radius_km:
                age_days = max((now - event.origin_time).total_seconds() / 86400, 0)
                contributions.append(math.exp(-age_days / 3.0) * math.exp(-distance / max(target.radius_km, 1.0)))
        boost = float(np.sum(contributions)) if contributions else 0.0
        expected = max(0.0, (baseline_rate + boost / 7.0) * window_hours / 24.0)
        probability = 1 - math.exp(-expected)
        relative = (baseline_rate + boost / 7.0) / baseline_rate if baseline_rate > 0 else (1.0 + boost)
        metadata = self.repository.metadata()
        return Forecast(
            target, window_hours, minimum_magnitude, round(expected, 6), round(probability, 6),
            round(baseline_rate, 6), round(relative, 6),
            metadata.get("last_successful_sync"),
            "prototype-aftershock-v1",
            ["Events are modeled as a Poisson process.", "Baseline uses the previous 30 days in the target region.",
             "Recent-event influence decays exponentially with age and distance."],
            ["Experimental statistical estimate; not an official alert.",
             "The model is not calibrated or validated for operational decisions.",
             "It does not estimate shaking intensity or building impact."],
        )
