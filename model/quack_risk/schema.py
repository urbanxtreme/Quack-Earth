"""Catalog, signal, and grid contracts shared with backend and frontend."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

CATALOG_REQUIRED_COLUMNS: tuple[str, ...] = (
    "id",
    "time",
    "latitude",
    "longitude",
    "depth_km",
    "magnitude",
)
CATALOG_OPTIONAL_COLUMNS: tuple[str, ...] = ("mag_type", "source")
CATALOG_COLUMNS: tuple[str, ...] = CATALOG_REQUIRED_COLUMNS + CATALOG_OPTIONAL_COLUMNS
CATALOG_SOURCES: frozenset[str] = frozenset({"usgs", "local"})

SIGNAL_REQUIRED_COLUMNS: tuple[str, ...] = (
    "id",
    "time",
    "latitude",
    "longitude",
    "signal_type",
    "confidence",
)
SIGNAL_OPTIONAL_COLUMNS: tuple[str, ...] = ("equivalent_magnitude",)
SIGNAL_COLUMNS: tuple[str, ...] = SIGNAL_REQUIRED_COLUMNS + SIGNAL_OPTIONAL_COLUMNS
SIGNAL_TYPES: frozenset[str] = frozenset({"accelerometer", "report"})

GRID_COLUMNS: tuple[str, ...] = (
    "lat",
    "lon",
    "baseline_rate",
    "triggered_rate",
    "total_rate",
    "probability_24h",
    "probability_7d",
    "relative_risk",
    "risk_level",
)
RISK_LEVELS: tuple[str, ...] = ("low", "moderate", "elevated", "high")
# Written by the scoring script after score_grid. The nine GRID_COLUMNS stay first.
PUBLIC_COLUMNS: tuple[str, ...] = (
    "probability_m5_24h",
    "probability_m6_24h",
    "public_zone",
)
PUBLIC_ZONES: tuple[str, ...] = ("usual", "stay aware", "limit work", "priority")


class CatalogSchemaError(ValueError):
    """Raised when a catalog file does not match the contract."""


class SignalSchemaError(ValueError):
    """Raised when a local-signal file does not match the contract."""


@dataclass(frozen=True)
class CatalogEvent:
    """One earthquake. Loaders return a table of these columns, not a list of objects."""

    id: str
    time: datetime
    latitude: float
    longitude: float
    depth_km: float
    magnitude: float
    mag_type: str | None = None
    source: str = "usgs"


@dataclass(frozen=True)
class LocalSignal:
    """One accelerometer hit or user report. ``equivalent_magnitude`` may be omitted."""

    id: str
    time: datetime
    latitude: float
    longitude: float
    signal_type: str
    confidence: float
    equivalent_magnitude: float | None = None


@dataclass(frozen=True)
class GridSpec:
    """Regional grid. Bounds are west, south, east, north in degrees."""

    west: float
    south: float
    east: float
    north: float
    resolution_deg: float = 0.2

    def __post_init__(self) -> None:
        if not self.west < self.east:
            raise ValueError("Grid bounds must have west < east.")
        if not self.south < self.north:
            raise ValueError("Grid bounds must have south < north.")
        if self.resolution_deg <= 0:
            raise ValueError("resolution_deg must be positive.")
