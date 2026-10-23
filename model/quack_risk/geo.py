"""Kilometre distance and cell area on a regional latitude/longitude grid."""

from __future__ import annotations

import numpy as np

KM_PER_DEG = 111.32


def grid_centers(
    bounds: tuple[float, float, float, float],
    resolution_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Cell-center latitudes and longitudes.

    ``bounds`` is ``(west, south, east, north)`` in degrees.
    """
    if resolution_deg <= 0:
        raise ValueError("resolution_deg must be positive.")
    west, south, east, north = (float(value) for value in bounds)
    if not west < east:
        raise ValueError("bounds must have west < east.")
    if not south < north:
        raise ValueError("bounds must have south < north.")
    latitudes = np.arange(south + resolution_deg / 2.0, north, resolution_deg)
    longitudes = np.arange(west + resolution_deg / 2.0, east, resolution_deg)
    if latitudes.size == 0 or longitudes.size == 0:
        raise ValueError("resolution_deg is coarser than the bounds.")
    return latitudes, longitudes


def cell_area_km2(latitude_deg: np.ndarray, resolution_deg: float) -> np.ndarray:
    """Area of a rectangular cell, in km², at each latitude."""
    lat_km = resolution_deg * KM_PER_DEG
    lon_km = resolution_deg * KM_PER_DEG * np.cos(np.radians(latitude_deg))
    return lat_km * np.maximum(lon_km, 1e-6)


def equirectangular_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    """Distance in kilometres. Arguments broadcast like NumPy."""
    lat1 = np.asarray(lat1, dtype=float)
    lon1 = np.asarray(lon1, dtype=float)
    lat2 = np.asarray(lat2, dtype=float)
    lon2 = np.asarray(lon2, dtype=float)
    mean_lat = np.radians((lat1 + lat2) / 2.0)
    dy = (lat1 - lat2) * KM_PER_DEG
    dx = (lon1 - lon2) * KM_PER_DEG * np.cos(mean_lat)
    return np.hypot(dx, dy)
