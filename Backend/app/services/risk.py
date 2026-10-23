"""Short-term seismic risk calculation service using an Omori-style ETAS aftershock model.

Risk Model Identifier: omori-style-v1

Risk Score Scale:
- Risk scores are normalized continuous values between 0.0 and 1.0.
- Baseline rate lambda_0 is the expected daily rate of M >= M_c in the target area.
- Triggered rate lambda_trig is derived from the modified Omori law:
    boost_i = k * 10^(alpha * (M_i - M_c)) / (Delta t_i + c)^p * exp(-d_i / d_0)
- Relative activity is R = (lambda_0 + lambda_trig) / lambda_0.
- Normalized risk_score is computed using a logistic response calibrated to hazard cutoffs:
    risk_score = 1 - 1 / (1 + (R / 3.5)^1.2)
  where R=1 (baseline) gives ~0.20, R=3 (elevated) gives ~0.45, R=10+ (high) gives 0.75-1.0.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import numpy as np


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points on Earth in kilometers."""
    r_lat1, r_lon1, r_lat2, r_lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(r_lat1) * math.cos(r_lat2) * math.sin(dlon / 2.0) ** 2
    return 6371.0088 * 2.0 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def haversine_vector(lat1: float, lon1: float, lat2_arr: np.ndarray, lon2_arr: np.ndarray) -> np.ndarray:
    """Calculate great-circle distances from scalar (lat1, lon1) to arrays of points."""
    if len(lat2_arr) == 0:
        return np.array([], dtype=float)
    r_lat1 = math.radians(lat1)
    r_lon1 = math.radians(lon1)
    r_lat2 = np.radians(lat2_arr)
    r_lon2 = np.radians(lon2_arr)
    dlat = r_lat2 - r_lat1
    dlon = r_lon2 - r_lon1
    a = np.sin(dlat / 2.0) ** 2 + math.cos(r_lat1) * np.cos(r_lat2) * np.sin(dlon / 2.0) ** 2
    return 6371.0088 * 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


class RiskService:
    def __init__(self, repository):
        self.repository = repository
        self.model_name = "omori-style-v1"
        self.k = 0.01  # productivity parameter
        self.alpha = 0.9  # magnitude scaling exponent
        self.c_days = 0.05  # time offset in days
        self.p = 1.1  # temporal decay exponent
        self.recent_window_days = 14.0  # look-back window for triggered aftershocks
        self.baseline_window_days = 30.0  # window for historical baseline estimation

    def calculate_risk(
        self,
        lat: float,
        lon: float,
        radius_km: float = 50.0,
        time_window: str = "24h",
        min_magnitude: float = 4.0,
    ) -> dict:
        window_days = 1.0 if time_window == "24h" else 7.0
        now = datetime.now(timezone.utc)
        all_events = self.repository.list_events(limit=10000)

        if not all_events:
            return {
                "time_window": time_window,
                "min_magnitude": min_magnitude,
                "center": {"lat": lat, "lon": lon},
                "baseline_rate": 0.0,
                "zones": [
                    {
                        "lat": lat,
                        "lon": lon,
                        "risk_score": 0.0,
                        "relative_to_baseline": 1.0,
                        "expected_events": 0.0,
                    }
                ],
                "generated_at": now.isoformat().replace("+00:00", "Z"),
            }

        # Handle offline historical demo data gracefully
        max_event_time = max(e.origin_time for e in all_events)
        if (now - max_event_time).days > 30:
            ref_time = max_event_time + timedelta(hours=1)
        else:
            ref_time = now

        # Historical baseline: count events with magnitude >= min_magnitude in target radius
        baseline_start = ref_time - timedelta(days=self.baseline_window_days + self.recent_window_days)
        baseline_end = ref_time - timedelta(days=self.recent_window_days)
        baseline_events = [
            e for e in all_events
            if baseline_start <= e.origin_time <= baseline_end
            and e.magnitude is not None and e.magnitude >= min_magnitude
            and haversine_km(lat, lon, e.latitude, e.longitude) <= radius_km
        ]

        if not baseline_events:
            # Fall back to checking 30 days prior to ref_time
            baseline_events = [
                e for e in all_events
                if (ref_time - timedelta(days=self.baseline_window_days)) <= e.origin_time <= ref_time
                and e.magnitude is not None and e.magnitude >= min_magnitude
                and haversine_km(lat, lon, e.latitude, e.longitude) <= radius_km
            ]

        baseline_rate = len(baseline_events) / self.baseline_window_days
        effective_baseline = baseline_rate if baseline_rate > 0 else 0.01

        # Triggered rate: recent events within 14 days
        recent_start = ref_time - timedelta(days=self.recent_window_days)
        recent_events = [
            e for e in all_events
            if recent_start <= e.origin_time <= ref_time
            and e.magnitude is not None
        ]

        triggered_rate = 0.0
        interaction_radius = max(radius_km, 150.0)
        for e in recent_events:
            dist = haversine_km(lat, lon, e.latitude, e.longitude)
            if dist <= interaction_radius:
                age_days = max(0.0, (ref_time - e.origin_time).total_seconds() / 86400.0)
                time_decay = 1.0 / ((age_days + self.c_days) ** self.p)
                spatial_decay = math.exp(-dist / max(radius_km, 25.0))
                mag_boost = 10.0 ** (self.alpha * (e.magnitude - min_magnitude))
                triggered_rate += self.k * mag_boost * time_decay * spatial_decay

        total_rate = baseline_rate + triggered_rate
        expected_events = round(total_rate * window_days, 2)
        relative_to_baseline = round(total_rate / effective_baseline, 1)

        # Compute risk score (0.0 to 1.0 scale)
        if total_rate <= 0:
            risk_score = 0.0
        else:
            rel = max(0.0, relative_to_baseline)
            score = 1.0 - (1.0 / (1.0 + (rel / 3.5) ** 1.2))
            risk_score = round(min(1.0, max(0.0, score)), 2)

        return {
            "time_window": time_window,
            "min_magnitude": min_magnitude,
            "center": {"lat": lat, "lon": lon},
            "baseline_rate": round(baseline_rate, 3),
            "zones": [
                {
                    "lat": lat,
                    "lon": lon,
                    "risk_score": risk_score,
                    "relative_to_baseline": relative_to_baseline,
                    "expected_events": expected_events,
                }
            ],
            "generated_at": now.isoformat().replace("+00:00", "Z"),
        }

    def calculate_grid(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
        resolution: float = 0.1,
        time_window: str = "24h",
        min_magnitude: float = 4.0,
    ) -> dict:
        if resolution <= 0:
            raise ValueError("resolution must be positive")
        if min_lat >= max_lat or min_lon >= max_lon:
            raise ValueError("min boundaries must be less than max boundaries")

        lat_points = np.arange(min_lat, max_lat + resolution * 0.5, resolution)
        lon_points = np.arange(min_lon, max_lon + resolution * 0.5, resolution)
        total_cells = len(lat_points) * len(lon_points)
        if total_cells > 5000:
            raise ValueError("Grid too large, increase resolution or decrease bounding box")

        now = datetime.now(timezone.utc)
        all_events = self.repository.list_events(limit=10000)

        ref_time = now
        if all_events:
            max_event_time = max(e.origin_time for e in all_events)
            if (now - max_event_time).days > 30:
                ref_time = max_event_time + timedelta(hours=1)

        # Pre-filter events around the grid bounding box with a buffer
        buffer_deg = 1.5
        area_events = [
            e for e in all_events
            if (min_lat - buffer_deg) <= e.latitude <= (max_lat + buffer_deg)
            and (min_lon - buffer_deg) <= e.longitude <= (max_lon + buffer_deg)
            and e.magnitude is not None
        ]

        if area_events:
            ev_lats = np.array([e.latitude for e in area_events])
            ev_lons = np.array([e.longitude for e in area_events])
            ev_mags = np.array([e.magnitude for e in area_events])
            ev_times = np.maximum(
                0.0,
                np.array([(ref_time - e.origin_time).total_seconds() / 86400.0 for e in area_events]),
            )

            # Recent events for triggered Omori calculation
            recent_mask = ev_times <= self.recent_window_days
            recent_lats = ev_lats[recent_mask]
            recent_lons = ev_lons[recent_mask]
            recent_mags = ev_mags[recent_mask]
            recent_times = ev_times[recent_mask]

            # Baseline events (within 30 days and M >= min_magnitude)
            baseline_mask = (ev_times <= self.baseline_window_days) & (ev_mags >= min_magnitude)
            baseline_lats = ev_lats[baseline_mask]
            baseline_lons = ev_lons[baseline_mask]
        else:
            recent_lats = np.array([])
            recent_lons = np.array([])
            recent_mags = np.array([])
            recent_times = np.array([])
            baseline_lats = np.array([])
            baseline_lons = np.array([])

        cell_radius_km = max(resolution * 111.0, 30.0)
        grid_cells = []

        for glat in lat_points:
            for glon in lon_points:
                # Baseline calculation for cell
                if len(baseline_lats) > 0:
                    d_base = haversine_vector(glat, glon, baseline_lats, baseline_lons)
                    b_count = np.sum(d_base <= cell_radius_km)
                    baseline_rate = b_count / self.baseline_window_days
                else:
                    baseline_rate = 0.0

                effective_baseline = baseline_rate if baseline_rate > 0 else 0.01

                # Triggered Omori calculation for cell
                if len(recent_lats) > 0:
                    d_recent = haversine_vector(glat, glon, recent_lats, recent_lons)
                    within = d_recent <= max(cell_radius_km, 150.0)
                    if np.any(within):
                        d_w = d_recent[within]
                        t_w = recent_times[within]
                        m_w = recent_mags[within]

                        time_decay = 1.0 / ((t_w + self.c_days) ** self.p)
                        spatial_decay = np.exp(-d_w / max(cell_radius_km, 25.0))
                        mag_boost = 10.0 ** (self.alpha * (m_w - min_magnitude))
                        trig_rate = float(np.sum(self.k * mag_boost * time_decay * spatial_decay))
                    else:
                        trig_rate = 0.0
                else:
                    trig_rate = 0.0

                total_rate = baseline_rate + trig_rate
                relative = total_rate / effective_baseline

                if total_rate <= 0.0:
                    risk_score = 0.0
                else:
                    score = 1.0 - (1.0 / (1.0 + (relative / 3.5) ** 1.2))
                    risk_score = round(float(np.clip(score, 0.0, 1.0)), 2)

                grid_cells.append({
                    "lat": round(float(glat), 4),
                    "lon": round(float(glon), 4),
                    "risk_score": risk_score,
                })

        return {
            "time_window": time_window,
            "grid": grid_cells,
        }
