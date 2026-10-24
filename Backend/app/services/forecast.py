import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

# Ensure model directory is in sys.path
_MODEL_DIR = str(Path(__file__).resolve().parents[3] / "model")
if _MODEL_DIR not in sys.path:
    sys.path.insert(0, _MODEL_DIR)

from ..models.forecast import Forecast, Target


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


class ForecastService:
    def __init__(self, repository):
        self.repository = repository
        self.model_name = "quack-risk-etas-v1"

    def _get_params(self):
        try:
            from quack_risk.calibrate import load_fitted_params
            from quack_risk.config import RiskParams
            params_path = Path(_MODEL_DIR) / "data" / "cache" / "params.json"
            params = load_fitted_params(params_path)
            return params or RiskParams()
        except Exception:
            from quack_risk.config import RiskParams
            return RiskParams()

    def calculate(self, trigger_event, target: Target, window_hours: int, minimum_magnitude: float) -> Forecast:
        now = trigger_event.origin_time
        params = self._get_params()

        # Historical baseline estimation over baseline_window_days
        baseline_days = 30.0
        historical_start = now - timedelta(days=baseline_days)
        historical = self.repository.list_events(start=historical_start, end=now)
        relevant = [
            event for event in historical
            if event.magnitude is not None and event.magnitude >= minimum_magnitude
            and haversine_km(target.latitude, target.longitude, event.latitude, event.longitude) <= target.radius_km
        ]
        baseline_rate = len(relevant) / baseline_days

        # Recent triggering sequence within recent_window_days (14 days)
        recent_start = now - timedelta(days=params.recent_window_days)
        recent = self.repository.list_events(start=recent_start, end=now + timedelta(hours=24))

        try:
            from quack_risk.kernels import kernel_width_km, omori_productivity

            triggered_rates = []
            qualifying_count = 0

            for event in recent:
                if event.magnitude is None or event.magnitude < params.magnitude_threshold:
                    continue

                distance = haversine_km(target.latitude, target.longitude, event.latitude, event.longitude)
                width = float(kernel_width_km(np.array([event.magnitude]), params)[0])
                max_influence_dist = max(target.radius_km + width * 2.0, 150.0)

                if distance <= max_influence_dist:
                    age_days = max((now - event.origin_time).total_seconds() / 86400.0, 0.0)
                    prod = float(omori_productivity(event.magnitude, age_days, params))

                    spatial_factor = math.exp(-0.5 * (distance / max(width, target.radius_km, 5.0)) ** 2)
                    target_area = math.pi * (target.radius_km ** 2)
                    kernel_area = 2.0 * math.pi * (width ** 2)
                    area_ratio = min(1.0, max(0.01, target_area / max(kernel_area, 1.0)))

                    b_value = 1.0
                    gr_factor = 10.0 ** (-b_value * (minimum_magnitude - params.magnitude_threshold))

                    event_rate = prod * spatial_factor * area_ratio * gr_factor
                    triggered_rates.append(event_rate)
                    qualifying_count += 1

            triggered_rate = sum(triggered_rates)
        except Exception:
            triggered_rate = 0.0
            qualifying_count = 0

        total_rate = baseline_rate + triggered_rate
        expected = max(0.0, total_rate * (window_hours / 24.0))
        probability = min(1.0, max(0.0, 1.0 - math.exp(-expected)))
        relative = (total_rate / baseline_rate) if baseline_rate > 0 else (1.0 + triggered_rate)

        metadata = self.repository.metadata()

        return Forecast(
            target=target,
            window_hours=window_hours,
            minimum_magnitude=minimum_magnitude,
            expected_event_count=round(expected, 6),
            probability_at_least_one=round(probability, 6),
            baseline_rate_per_day=round(baseline_rate, 6),
            baseline_event_count=len(relevant),
            recent_qualifying_event_count=qualifying_count,
            relative_activity_score=round(relative, 6),
            data_as_of=metadata.get("last_successful_sync", now.isoformat().replace("+00:00", "Z")),
            model=self.model_name,
            assumptions=[
                "Omori-Utsu law governs temporal aftershock decay rate: K * 10^(alpha*(M - Mc)) / (dt + c)^p.",
                "Spatial kernel scales with magnitude-dependent rupture length: W = 10^(0.5M - 1.8).",
                "Gutenberg-Richter magnitude-frequency relation applies across target thresholds.",
                "Events occur as an inhomogeneous Poisson process conditional on parent earthquakes.",
            ],
            limitations=[
                "Physics-based statistical estimate for situational awareness; not an official alert.",
                "Model parameters (K, c, p) should be calibrated against the specific tectonic sequence.",
                "Does not account for 3D subsurface fault geometries or dynamic rupture propagation.",
            ],
        )
