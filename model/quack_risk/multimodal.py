"""Turn accelerometer hits and resident reports into extra triggers.

A catalog earthquake is the only magnitude the rate formula treats as measured.
Phones and resident reports are felt-shaking evidence. One of them cannot open
a new high-risk patch, and a typed magnitude cannot widen the kernel.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quack_risk.config import RiskParams
from quack_risk.geo import equirectangular_km
from quack_risk.io import validate_catalog, validate_signals

# A missing magnitude maps confidence 0–1 onto 3.0–4.5.
EQUIVALENT_MAGNITUDE_FLOOR = 3.0
EQUIVALENT_MAGNITUDE_SPAN = 1.5
# A phone cannot separate an M5 from an M7. The kernel width uses this number.
ACCEL_MAGNITUDE_CAP = 4.5
# Reports are noisier than a phone accelerometer, so they count less.
REPORT_WEIGHT = 0.3
# One accelerometer may add a bump only beside a measured quake.
CONFIRM_RADIUS_KM = 40.0
CONFIRM_WINDOW = pd.Timedelta(hours=24)
CONFIRM_SKEW = pd.Timedelta(minutes=2)
# Several signals in one place and a few minutes are one felt-shaking bump.
CLUSTER_RADIUS_KM = 15.0
CLUSTER_WINDOW = pd.Timedelta(minutes=10)
# Three confident phones, or ten confident reports, clear this bar.
CLUSTER_SCORE_MIN = 3.0


def signals_to_triggers(
    signals: pd.DataFrame | None,
    *,
    as_of: pd.Timestamp,
    params: RiskParams,
    catalog: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return catalog-shaped rows for signals that count at ``as_of``.

    Each row has ``source='local'`` and a ``trigger_weight``. An accelerometer
    within 40 km and 24 hours of a catalog event at or above ``M_c`` becomes
    one confirmation, weighted by its confidence, with magnitude capped at 4.5.
    A resident report never uses a typed magnitude. A lone report adds nothing.
    Signals that are not beside a measured quake count only as one cluster:
    phones and reports within 15 km and 10 minutes must reach an agreement
    score of 3. That cluster is one bump, and it is left out when a catalog
    quake already covers the same place. Confidence 0, future signals, and
    signals older than the recent window are left out.
    """
    if signals is None or len(signals) == 0:
        return _empty_triggers()

    frame = validate_signals(signals)
    if frame.empty:
        return _empty_triggers()

    as_of_utc = _as_utc(as_of)
    prepared = _prepare(frame, as_of_utc, params)
    if not prepared:
        return _empty_triggers()

    quakes = _recent_quakes(catalog, as_of_utc, params)
    triggers = []
    for group in _cluster(prepared):
        trigger = _admit(group, quakes)
        if trigger is not None:
            triggers.append(trigger)
    if not triggers:
        return _empty_triggers()
    return pd.DataFrame(triggers)


def _prepare(frame: pd.DataFrame, as_of: pd.Timestamp, params: RiskParams) -> list[dict]:
    times = pd.to_datetime(frame["time"], utc=True)
    age_days = (as_of - times) / pd.Timedelta(days=1)
    keep = (age_days.to_numpy() >= 0) & (age_days.to_numpy() <= params.recent_window_days)
    chosen = frame.loc[keep]
    times = times.loc[keep]
    rows: dict[str, dict] = {}
    for index, record in chosen.iterrows():
        confidence = float(record["confidence"])
        if confidence <= 0:
            continue
        signal_type = str(record["signal_type"])
        if signal_type == "report" or pd.isna(record["equivalent_magnitude"]):
            magnitude = EQUIVALENT_MAGNITUDE_FLOOR + EQUIVALENT_MAGNITUDE_SPAN * confidence
        else:
            magnitude = float(record["equivalent_magnitude"])
        magnitude = min(magnitude, ACCEL_MAGNITUDE_CAP)
        weight = confidence * (REPORT_WEIGHT if signal_type == "report" else 1.0)
        row = {
            "id": str(record["id"]),
            "time": times.loc[index],
            "latitude": float(record["latitude"]),
            "longitude": float(record["longitude"]),
            "signal_type": signal_type,
            "confidence": confidence,
            "magnitude": magnitude,
            "trigger_weight": weight,
        }
        current = rows.get(row["id"])
        if current is None or row["confidence"] > current["confidence"]:
            rows[row["id"]] = row
    return list(rows.values())


def _recent_quakes(catalog: pd.DataFrame | None, as_of: pd.Timestamp, params: RiskParams) -> list[tuple[float, float, pd.Timestamp]]:
    if catalog is None or len(catalog) == 0:
        return []
    frame = validate_catalog(catalog)
    if frame.empty:
        return []
    times = pd.to_datetime(frame["time"], utc=True)
    age_days = (as_of - times) / pd.Timedelta(days=1)
    magnitudes = frame["magnitude"].to_numpy(dtype=float)
    keep = (age_days.to_numpy() >= 0) & (age_days.to_numpy() <= params.recent_window_days)
    keep = keep & (magnitudes >= params.magnitude_threshold)
    kept = frame.loc[keep]
    kept_times = times.loc[keep]
    return [
        (float(latitude), float(longitude), timestamp)
        for latitude, longitude, timestamp in zip(
            kept["latitude"].to_numpy(dtype=float),
            kept["longitude"].to_numpy(dtype=float),
            kept_times.to_list(),
        )
    ]


def _cluster(rows: list[dict]) -> list[list[dict]]:
    unused = sorted(rows, key=lambda row: (row["time"], row["id"]))
    groups: list[list[dict]] = []
    while unused:
        seed = unused.pop(0)
        group = [seed]
        rest = []
        for row in unused:
            same_time = abs(row["time"] - seed["time"]) <= CLUSTER_WINDOW
            same_place = float(
                equirectangular_km(row["latitude"], row["longitude"], seed["latitude"], seed["longitude"])
            ) <= CLUSTER_RADIUS_KM
            if same_time and same_place:
                group.append(row)
            else:
                rest.append(row)
        unused = rest
        groups.append(group)
    return groups


def _admit(group: list[dict], quakes: list[tuple[float, float, pd.Timestamp]]) -> dict | None:
    beside_quake = _beside_catalog_quake(group, quakes)
    accelerometers = [row for row in group if row["signal_type"] == "accelerometer"]
    if beside_quake:
        if not accelerometers:
            return None
        best = max(accelerometers, key=lambda row: row["confidence"])
        return _as_trigger(group, best, weight=best["confidence"])
    agreement = float(sum(row["trigger_weight"] for row in group))
    # 0.3 * 10 is just under 3 in binary. A group that lands on the bar still counts.
    if agreement + 1e-6 < CLUSTER_SCORE_MIN:
        return None
    pool = accelerometers or group
    best = max(pool, key=lambda row: (row["confidence"], -row["magnitude"]))
    return _as_trigger(group, best, weight=min(1.0, agreement / CLUSTER_SCORE_MIN))


def _beside_catalog_quake(group: list[dict], quakes: list[tuple[float, float, pd.Timestamp]]) -> bool:
    if not quakes:
        return False
    for row in group:
        for latitude, longitude, quake_time in quakes:
            distance = float(equirectangular_km(row["latitude"], row["longitude"], latitude, longitude))
            if distance > CONFIRM_RADIUS_KM:
                continue
            gap = row["time"] - quake_time
            if -CONFIRM_SKEW <= gap <= CONFIRM_WINDOW:
                return True
    return False


def _as_trigger(group: list[dict], best: dict, *, weight: float) -> dict:
    earliest = min(row["time"] for row in group)
    return {
        "id": f"felt-{best['id']}",
        "time": earliest,
        "latitude": float(np.mean([row["latitude"] for row in group])),
        "longitude": float(np.mean([row["longitude"] for row in group])),
        "depth_km": 0.0,
        "magnitude": float(best["magnitude"]),
        "mag_type": best["signal_type"] if len(group) == 1 else "cluster",
        "source": "local",
        "trigger_weight": float(weight),
    }


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


def _as_utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    if stamp.tzinfo is None:
        return stamp.tz_localize("UTC")
    return stamp.tz_convert("UTC")
