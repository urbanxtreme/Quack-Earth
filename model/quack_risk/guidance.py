"""Plain zones and the excavation card read from the 24-hour chance."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from quack_risk.geo import KM_PER_DEG, equirectangular_km

# Briefing cutoffs on probability_24h. They keep the words stable. They are not a physical law.
STAY_AWARE_AT = 0.01
LIMIT_WORK_AT = 0.05
PRIORITY_AT = 0.15
SECTOR_RADIUS_KM = 20.0
MAX_SECTORS = 5
PEAK_PLACE_KM = 5.0
LIMIT_LINE = (
    "This is the aftershock chance for the next 24 hours. A field commander decides evacuation."
)

_ACTIONS = {
    "usual": "No extra short-term action.",
    "stay aware": "Open-area checks can continue. This chance alone does not call for a wide evacuation.",
    "limit work": "Pause excavation and debris removal. Stay out of damaged buildings.",
    "priority": "Search and rescue first. Pause excavation and stop debris removal in this sector.",
}
_EXCAVATION = {
    "usual": "continue",
    "stay aware": "open-area checks",
    "limit work": "pause",
    "priority": "pause",
}
_DIRECTIONS = (
    "north",
    "northeast",
    "east",
    "southeast",
    "south",
    "southwest",
    "west",
    "northwest",
)


def public_zones(probability_24h: np.ndarray) -> np.ndarray:
    """Map the 24-hour chance of magnitude 4 or larger onto a plain zone."""
    chance = np.asarray(probability_24h, dtype=float)
    zones = np.full(chance.shape, "usual", dtype=object)
    zones[chance >= STAY_AWARE_AT] = "stay aware"
    zones[chance >= LIMIT_WORK_AT] = "limit work"
    zones[chance >= PRIORITY_AT] = "priority"
    return zones


def attach_public_zone(grid: pd.DataFrame) -> pd.DataFrame:
    """Add ``public_zone`` from ``probability_24h``."""
    out = grid.copy()
    out["public_zone"] = public_zones(out["probability_24h"].to_numpy(dtype=float))
    return out


def bright_radius_km(grid: pd.DataFrame, *, fraction: float = 0.3, within_km: float = 150.0) -> float:
    """Distance from the peak to the farthest nearby cell at or above ``fraction`` of the peak rate."""
    peak = grid.loc[grid["total_rate"].idxmax()]
    distance = equirectangular_km(
        grid["lat"].to_numpy(),
        grid["lon"].to_numpy(),
        float(peak["lat"]),
        float(peak["lon"]),
    )
    bright = grid["total_rate"].to_numpy() >= fraction * float(peak["total_rate"])
    local = bright & (np.asarray(distance) <= within_km)
    if not bool(np.any(local)):
        return 0.0
    return float(np.asarray(distance)[local].max())


def build_guidance(grid: pd.DataFrame, *, as_of: str) -> dict:
    """Rank a few sectors and give each one an excavation action."""
    frame = grid.reset_index(drop=True)
    if "public_zone" not in frame.columns:
        frame = attach_public_zone(frame)
    peak_index = int(frame["probability_24h"].idxmax())
    peak = frame.loc[peak_index]
    peak_lat = float(peak["lat"])
    peak_lon = float(peak["lon"])

    remaining = set(frame.index[frame["public_zone"].to_numpy() != "usual"].tolist())
    sectors = []
    while remaining and len(sectors) < MAX_SECTORS:
        seed_index = max(remaining, key=lambda index: float(frame.at[index, "probability_24h"]))
        seed = frame.loc[seed_index]
        members = [
            index
            for index in remaining
            if float(
                equirectangular_km(
                    frame.at[index, "lat"],
                    frame.at[index, "lon"],
                    float(seed["lat"]),
                    float(seed["lon"]),
                )
            )
            <= SECTOR_RADIUS_KM
        ]
        remaining.difference_update(members)
        sectors.append(_sector(frame, members, peak_lat, peak_lon))
    if not sectors:
        sectors.append(_sector(frame, [peak_index], peak_lat, peak_lon))

    return {
        "as_of": str(as_of),
        "peak": _cell_summary(peak),
        "limit": LIMIT_LINE,
        "sectors": sectors,
    }


def write_guidance(payload: dict, path: str | Path) -> Path:
    """Write the authority card as JSON."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return destination


def _sector(frame: pd.DataFrame, members: list[int], peak_lat: float, peak_lon: float) -> dict:
    seed_index = max(members, key=lambda index: float(frame.at[index, "probability_24h"]))
    seed = frame.loc[seed_index]
    summary = _cell_summary(seed)
    direction, distance = _place(summary["lat"], summary["lon"], peak_lat, peak_lon)
    zone = summary["public_zone"]
    summary.update(
        {
            "direction": direction,
            "distance_km": round(distance, 1),
            "place": "at the peak" if direction == "at the peak" else f"{distance:.0f} km {direction} of the peak",
            "action": _ACTIONS[zone],
            "excavation": _EXCAVATION[zone],
            "cells": len(members),
        }
    )
    return summary


def _cell_summary(row: pd.Series) -> dict:
    summary = {
        "lat": round(float(row["lat"]), 3),
        "lon": round(float(row["lon"]), 3),
        "probability_24h": round(float(row["probability_24h"]), 4),
        "public_zone": str(row["public_zone"]),
    }
    for name in ("probability_m5_24h", "probability_m6_24h"):
        if name in row.index and pd.notna(row[name]):
            summary[name] = round(float(row[name]), 4)
    return summary


def _place(lat: float, lon: float, peak_lat: float, peak_lon: float) -> tuple[str, float]:
    distance = float(equirectangular_km(lat, lon, peak_lat, peak_lon))
    if distance < PEAK_PLACE_KM:
        return "at the peak", distance
    north_km = (lat - peak_lat) * KM_PER_DEG
    east_km = (lon - peak_lon) * KM_PER_DEG * np.cos(np.radians((lat + peak_lat) / 2.0))
    angle = np.degrees(np.arctan2(east_km, north_km))
    index = int(np.round(angle / 45.0)) % 8
    return _DIRECTIONS[index], distance
