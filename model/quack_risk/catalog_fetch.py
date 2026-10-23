"""One-shot USGS download for the demo box. Scoring itself stays offline."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from quack_risk.config import DEMO_BOUNDS
from quack_risk.io import load_catalog
from quack_risk.schema import CATALOG_COLUMNS

FDSN_QUERY = "https://earthquake.usgs.gov/fdsnws/event/1/query"
CATALOG_START = "2018-01-01"
# The FDSN end is exclusive enough in practice; a day past 20 Feb keeps that date.
CATALOG_END = "2023-02-21"
USER_AGENT = "quack-earth-risk-engine/1.0"


def fdsn_demo_url(*, limit: int = 20000) -> str:
    """Regional M >= 4 query for the Kahramanmaraş demo box, 2018 through 20 Feb 2023."""
    west, south, east, north = DEMO_BOUNDS
    query = urllib.parse.urlencode(
        {
            "format": "geojson",
            "starttime": CATALOG_START,
            "endtime": CATALOG_END,
            "minlatitude": south,
            "maxlatitude": north,
            "minlongitude": west,
            "maxlongitude": east,
            "minmagnitude": 4,
            "orderby": "time-asc",
            "limit": limit,
        }
    )
    return f"{FDSN_QUERY}?{query}"


def download_catalog(csv_path: str | Path, *, force: bool = False, timeout: float = 120.0) -> Path:
    """Download the demo catalog and write it as the cache CSV. Returns the CSV path."""
    destination = Path(csv_path)
    if destination.is_file() and not force:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_path = destination.with_suffix(".geojson")
    request = urllib.request.Request(fdsn_demo_url(), headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError("USGS catalog download failed.") from exc
    raw_path.write_bytes(payload)
    # Reject an error document before the catalog parser sees it.
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict) or document.get("type") != "FeatureCollection":
        raw_path.unlink(missing_ok=True)
        raise RuntimeError("USGS did not return an earthquake catalog.")
    frame = load_catalog(raw_path)
    raw_path.unlink(missing_ok=True)
    keep = frame["magnitude"] >= 4.0
    frame = frame.loc[keep, list(CATALOG_COLUMNS)].copy()
    frame["time"] = frame["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    temporary = destination.with_suffix(".csv.part")
    frame.to_csv(temporary, index=False)
    temporary.replace(destination)
    return destination
