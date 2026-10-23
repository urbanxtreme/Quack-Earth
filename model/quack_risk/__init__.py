"""Short-term seismic risk engine.

Phase 0 exposes the file contract only. Scoring arrives in later phases.
"""

from quack_risk.config import RiskParams
from quack_risk.io import load_catalog, load_signals
from quack_risk.schema import (
    CATALOG_COLUMNS,
    GRID_COLUMNS,
    SIGNAL_COLUMNS,
    CatalogSchemaError,
    SignalSchemaError,
)

__all__ = [
    "CATALOG_COLUMNS",
    "GRID_COLUMNS",
    "SIGNAL_COLUMNS",
    "CatalogSchemaError",
    "RiskParams",
    "SignalSchemaError",
    "load_catalog",
    "load_signals",
]
