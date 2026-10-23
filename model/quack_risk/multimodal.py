"""Turn accelerometer hits and resident reports into extra triggers."""

from __future__ import annotations

import pandas as pd

from quack_risk.config import RiskParams
from quack_risk.io import validate_signals

# A missing magnitude maps confidence 0–1 onto 3.0–4.5.
EQUIVALENT_MAGNITUDE_FLOOR = 3.0
EQUIVALENT_MAGNITUDE_SPAN = 1.5
# Reports are noisier than a phone accelerometer, so they count less.
REPORT_WEIGHT = 0.3


def signals_to_triggers(
    signals: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    params: RiskParams,
) -> pd.DataFrame:
    """Return catalog-shaped rows for signals that count at ``as_of``.

    Each row has ``source='local'`` and a ``trigger_weight``. An accelerometer
    weight is its confidence. A report weight is confidence times 0.3.
    Confidence 0, future signals, and signals older than the recent window
    are left out. The magnitude used for the rate exponent is filled in later
    with ``max(M, M_c)`` so a local hit below completeness still adds a
    small, nearby bump.
    """
    if signals is None or len(signals) == 0:
        return _empty_triggers()

    frame = validate_signals(signals)
    if frame.empty:
        return _empty_triggers()

    magnitude = frame["equivalent_magnitude"].copy()
    missing = magnitude.isna()
    magnitude.loc[missing] = EQUIVALENT_MAGNITUDE_FLOOR + EQUIVALENT_MAGNITUDE_SPAN * frame.loc[missing, "confidence"]

    times = pd.to_datetime(frame["time"], utc=True)
    age_days = (as_of - times) / pd.Timedelta(days=1)
    weight = frame["confidence"].to_numpy(dtype=float).copy()
    weight[frame["signal_type"].to_numpy() == "report"] *= REPORT_WEIGHT
    keep = (age_days.to_numpy() >= 0) & (age_days.to_numpy() <= params.recent_window_days) & (weight > 0)
    if not bool(keep.any()):
        return _empty_triggers()

    chosen = frame.loc[keep]
    return pd.DataFrame(
        {
            "id": chosen["id"].to_numpy(),
            "time": times.loc[keep].to_numpy(),
            "latitude": chosen["latitude"].to_numpy(dtype=float),
            "longitude": chosen["longitude"].to_numpy(dtype=float),
            "depth_km": 0.0,
            "magnitude": magnitude.loc[keep].to_numpy(dtype=float),
            "mag_type": chosen["signal_type"].to_numpy(),
            "source": "local",
            "trigger_weight": weight[keep],
        }
    )


def _empty_triggers() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "id",
            "time",
            "latitude",
            "longitude",
            "depth_km",
            "magnitude",
            "mag_type",
            "source",
            "trigger_weight",
        ]
    )
