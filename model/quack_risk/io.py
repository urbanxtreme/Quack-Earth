"""Load catalog and local-signal files into the Phase 0 contract."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from quack_risk.schema import (
    CATALOG_COLUMNS,
    CATALOG_REQUIRED_COLUMNS,
    CATALOG_SOURCES,
    GRID_COLUMNS,
    PUBLIC_COLUMNS,
    CatalogSchemaError,
    SIGNAL_COLUMNS,
    SIGNAL_REQUIRED_COLUMNS,
    SIGNAL_TYPES,
    SignalSchemaError,
)


def load_catalog(path: str | Path) -> pd.DataFrame:
    """Read a catalog CSV or USGS-style GeoJSON file and validate it.

    Times come back as timezone-aware UTC. Rows are sorted by time.
    Extra columns from the backend are kept after the contract columns.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    if file_path.suffix.lower() in {".geojson", ".json"}:
        frame = _read_geojson_catalog(file_path)
    else:
        frame = pd.read_csv(file_path)
    return validate_catalog(frame)


def load_signals(path: str | Path | None) -> pd.DataFrame:
    """Read a JSON list of local signals. ``None`` and ``[]`` yield an empty table."""
    if path is None:
        return _empty_signals()
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if payload is None:
        payload = []
    if not isinstance(payload, list):
        raise SignalSchemaError("Signals file must be a JSON list.")
    if len(payload) == 0:
        return _empty_signals()
    return validate_signals(pd.DataFrame(payload))


def validate_catalog(frame: pd.DataFrame) -> pd.DataFrame:
    """Check required columns and coerce types. Raises ``CatalogSchemaError``."""
    missing = [name for name in CATALOG_REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise CatalogSchemaError(f"Catalog is missing required columns: {joined}.")

    out = frame.copy()
    out["id"] = out["id"].map(_as_id)
    out["time"] = _parse_times(out["time"])
    for name in ("latitude", "longitude", "depth_km", "magnitude"):
        out[name] = pd.to_numeric(out[name], errors="coerce")

    if out["id"].isna().any():
        raise CatalogSchemaError("Catalog has rows with missing id.")
    if out["time"].isna().any():
        raise CatalogSchemaError("Catalog has rows with missing or unparseable time.")
    if out["magnitude"].isna().any():
        raise CatalogSchemaError("Catalog has rows with missing magnitude.")
    if out["depth_km"].isna().any():
        raise CatalogSchemaError("Catalog has rows with missing depth_km.")
    if out["latitude"].isna().any() or not out["latitude"].between(-90, 90).all():
        raise CatalogSchemaError("Catalog latitudes must be numbers from -90 to 90.")
    if out["longitude"].isna().any() or not out["longitude"].between(-180, 180).all():
        raise CatalogSchemaError("Catalog longitudes must be numbers from -180 to 180.")

    if "mag_type" not in out.columns:
        out["mag_type"] = pd.Series(pd.NA, index=out.index, dtype="string")
    else:
        out["mag_type"] = out["mag_type"].astype("string")

    if "source" not in out.columns:
        out["source"] = "usgs"
    else:
        out["source"] = out["source"].astype("string").fillna("usgs")
        unknown = sorted(set(out["source"]) - CATALOG_SOURCES)
        if unknown:
            joined = ", ".join(unknown)
            raise CatalogSchemaError(f"Catalog source must be 'usgs' or 'local'. Found: {joined}.")

    extras = [name for name in out.columns if name not in CATALOG_COLUMNS]
    out = out[list(CATALOG_COLUMNS) + extras]
    return out.sort_values("time", kind="mergesort").reset_index(drop=True)


def validate_signals(frame: pd.DataFrame) -> pd.DataFrame:
    """Check required signal columns and coerce types. Raises ``SignalSchemaError``."""
    missing = [name for name in SIGNAL_REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise SignalSchemaError(f"Signals are missing required fields: {joined}.")

    out = frame.copy()
    out["id"] = out["id"].map(_as_id)
    out["time"] = _parse_times(out["time"])
    for name in ("latitude", "longitude", "confidence"):
        out[name] = pd.to_numeric(out[name], errors="coerce")
    out["signal_type"] = out["signal_type"].astype("string")

    if out["id"].isna().any():
        raise SignalSchemaError("Signals have rows with missing id.")
    if out["time"].isna().any():
        raise SignalSchemaError("Signals have rows with missing or unparseable time.")
    if out["latitude"].isna().any() or not out["latitude"].between(-90, 90).all():
        raise SignalSchemaError("Signal latitudes must be numbers from -90 to 90.")
    if out["longitude"].isna().any() or not out["longitude"].between(-180, 180).all():
        raise SignalSchemaError("Signal longitudes must be numbers from -180 to 180.")
    if out["confidence"].isna().any() or not out["confidence"].between(0.0, 1.0).all():
        raise SignalSchemaError("Signal confidence must be a number from 0 to 1.")

    unknown = sorted(set(out["signal_type"].dropna()) - SIGNAL_TYPES)
    if unknown or out["signal_type"].isna().any():
        joined = ", ".join(unknown) if unknown else "missing"
        raise SignalSchemaError(
            f"signal_type must be 'accelerometer' or 'report'. Found: {joined}."
        )

    if "equivalent_magnitude" not in out.columns:
        out["equivalent_magnitude"] = float("nan")
    else:
        out["equivalent_magnitude"] = pd.to_numeric(out["equivalent_magnitude"], errors="coerce")
        present = frame["equivalent_magnitude"].notna()
        parsed = out["equivalent_magnitude"].notna()
        if bool((present & ~parsed).any()):
            raise SignalSchemaError("equivalent_magnitude must be a number when it is provided.")

    extras = [name for name in out.columns if name not in SIGNAL_COLUMNS]
    out = out[list(SIGNAL_COLUMNS) + extras]
    return out.sort_values("time", kind="mergesort").reset_index(drop=True)


def _empty_signals() -> pd.DataFrame:
    return pd.DataFrame(columns=list(SIGNAL_COLUMNS))


def _read_geojson_catalog(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise CatalogSchemaError("GeoJSON catalog must be a FeatureCollection.")
    rows: list[dict] = []
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None, None]
        longitude = coords[0] if len(coords) > 0 else None
        latitude = coords[1] if len(coords) > 1 else None
        depth = coords[2] if len(coords) > 2 else props.get("depth_km", props.get("depth"))
        rows.append(
            {
                "id": feature.get("id") or props.get("id") or props.get("code"),
                "time": props.get("time"),
                "latitude": latitude,
                "longitude": longitude,
                "depth_km": depth,
                "magnitude": props.get("magnitude", props.get("mag")),
                "mag_type": props.get("mag_type", props.get("magType")),
                "source": props.get("source", "usgs"),
            }
        )
    if not rows:
        return pd.DataFrame(columns=list(CATALOG_COLUMNS))
    return pd.DataFrame(rows)


def _parse_times(values: pd.Series) -> pd.Series:
    """Parse ISO-8601 strings, or numeric epoch seconds / milliseconds, as UTC."""
    if pd.api.types.is_numeric_dtype(values):
        observed = values.dropna()
        unit = "ms" if not observed.empty and float(observed.abs().median()) > 1e11 else "s"
        return pd.to_datetime(values, unit=unit, utc=True, errors="coerce")
    try:
        return pd.to_datetime(values, format="ISO8601", utc=True, errors="coerce")
    except Exception:
        return pd.to_datetime(values, utc=True, errors="coerce")


def write_risk_grid(frame: pd.DataFrame, csv_path: str | Path) -> tuple[Path, Path]:
    """Write the frontend grid as CSV and a GeoJSON FeatureCollection of points."""
    missing = [name for name in GRID_COLUMNS if name not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Risk grid is missing columns: {joined}.")
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = [name for name in PUBLIC_COLUMNS if name in frame.columns]
    ordered = frame.loc[:, list(GRID_COLUMNS) + extra].sort_values(["lat", "lon"], kind="mergesort")
    ordered.to_csv(path, index=False)

    records = json.loads(ordered.to_json(orient="records"))
    features = []
    for record in records:
        latitude = record.pop("lat")
        longitude = record.pop("lon")
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                "properties": record,
            }
        )
    geojson_path = path.with_suffix(".geojson")
    payload = {"type": "FeatureCollection", "features": features}
    geojson_path.write_text(json.dumps(payload), encoding="utf-8")
    return path, geojson_path


def _as_id(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "<na>", "none"}:
        return None
    return text
