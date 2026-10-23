"""Score a catalog file and write the risk grid.

From the repo root:

    python model/scripts/run_score.py --catalog data/fixtures/scenario_m62.csv --as-of 2024-01-15T03:35:00Z --bounds 36.2 36.2 38.2 38.2 --resolution 0.05 --out outputs/grids/scenario_m62.csv

Relative --catalog and --out paths are read from the ``model`` folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quack_risk.config import DEMO_AS_OF, DEMO_BOUNDS  # noqa: E402
from quack_risk.engine import score_grid  # noqa: E402
from quack_risk.geo import equirectangular_km  # noqa: E402
from quack_risk.io import load_catalog, write_risk_grid  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a cached catalog and write the risk grid.")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "fixtures" / "catalog.csv")
    parser.add_argument("--as-of", default=DEMO_AS_OF, help="UTC time the score is valid at. Later events are ignored.")
    parser.add_argument(
        "--bounds",
        type=float,
        nargs=4,
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
        default=DEMO_BOUNDS,
    )
    parser.add_argument("--resolution", type=float, default=0.2, help="Cell size in degrees.")
    parser.add_argument("--magnitude-threshold", type=float, default=4.0)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "grids" / "risk_grid.csv")
    args = parser.parse_args(argv)
    catalog_path = _model_path(args.catalog)
    out_path = _model_path(args.out)

    catalog = load_catalog(catalog_path)
    grid = score_grid(
        catalog,
        as_of=args.as_of,
        bounds=tuple(args.bounds),
        resolution_deg=args.resolution,
        magnitude_threshold=args.magnitude_threshold,
    )
    csv_path, geojson_path = write_risk_grid(grid, out_path)
    _print_summary(grid, args.as_of, csv_path, geojson_path)
    return 0


def _model_path(path: Path) -> Path:
    """Resolve a relative path from the model folder, so the command works from the repo root."""
    if path.is_absolute():
        return path
    return ROOT / path


def _print_summary(grid, as_of: str, csv_path: Path, geojson_path: Path) -> None:
    peak = grid.loc[grid["total_rate"].idxmax()]
    distance = equirectangular_km(
        grid["lat"].to_numpy(),
        grid["lon"].to_numpy(),
        float(peak["lat"]),
        float(peak["lon"]),
    )
    peak_rate = float(peak["total_rate"])
    bright = grid["total_rate"].to_numpy() >= 0.3 * peak_rate
    local = bright & (distance <= 150.0)
    radius = float(distance[local].max()) if local.any() else 0.0
    remote = int((bright & (distance > 150.0)).sum())
    counts = grid["risk_level"].value_counts()

    print(f"as_of: {as_of}")
    print(f"cells: {len(grid)}")
    print(
        "peak: "
        f"{float(peak['lat']):.3f} N, {float(peak['lon']):.3f} E, "
        f"level {peak['risk_level']}"
    )
    print(f"  total_rate:      {peak_rate:.6g} events/day in the cell")
    print(f"  baseline_rate:   {float(peak['baseline_rate']):.6g}")
    print(f"  triggered_rate:  {float(peak['triggered_rate']):.6g}")
    print(f"  relative_risk:   {float(peak['relative_risk']):.6g}")
    print(f"  probability_24h: {float(peak['probability_24h']):.4f}")
    print(f"  probability_7d:  {float(peak['probability_7d']):.4f}")
    print(f"bright zone (rate at least 30% of the peak, within 150 km): {radius:.1f} km")
    if remote:
        print(f"other cells above 30% of the peak, beyond 150 km: {remote}")
    levels = ", ".join(f"{name}={int(counts.get(name, 0))}" for name in ("low", "moderate", "elevated", "high"))
    print(f"risk levels: {levels}")
    print(f"wrote: {csv_path}")
    print(f"wrote: {geojson_path}")


if __name__ == "__main__":
    raise SystemExit(main())
