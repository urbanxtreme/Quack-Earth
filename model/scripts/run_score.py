"""Score a catalog file and write the risk grid.

From the repo root:

    python model/scripts/run_score.py --catalog data/fixtures/scenario_m62.csv --signals data/fixtures/scenario_signal.json --as-of 2024-01-15T03:35:00Z --bounds 36.2 36.2 38.2 38.2 --resolution 0.05 --out outputs/grids/scenario_m62_signal.csv

Relative --catalog, --signals, and --out paths are read from the ``model`` folder.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quack_risk.calibrate import load_fitted_params  # noqa: E402
from quack_risk.config import DEMO_AS_OF, DEMO_BOUNDS, RiskParams  # noqa: E402
from quack_risk.engine import score_grid  # noqa: E402
from quack_risk.geo import equirectangular_km  # noqa: E402
from quack_risk.guidance import attach_public_zone, build_guidance, write_guidance  # noqa: E402
from quack_risk.io import load_catalog, load_signals, write_risk_grid  # noqa: E402
from quack_risk.multimodal import signals_to_triggers  # noqa: E402
from quack_risk.outlook import attach_outlook  # noqa: E402
from quack_risk.verdict import compose_verdict, write_verdict  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score a cached catalog and write the risk grid.")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "fixtures" / "catalog.csv")
    parser.add_argument("--signals", type=Path, default=None, help="Optional JSON list of local accelerometer hits and reports.")
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
    parser.add_argument("--params", type=Path, default=ROOT / "data" / "cache" / "params.json")
    parser.add_argument(
        "--defaults",
        action="store_true",
        help="Use the built-in K, c, and p even when params.json is present.",
    )
    parser.add_argument(
        "--rewrite-verdict",
        action="store_true",
        help=(
            "If XAI_API_KEY is set, ask SpaceXAI to rephrase the verdict. "
            "The template is kept when the key is missing, the call fails, or the reply changes the numbers."
        ),
    )
    args = parser.parse_args(argv)
    catalog_path = _model_path(args.catalog)
    out_path = _model_path(args.out)
    signals = None if args.signals is None else load_signals(_model_path(args.signals))

    catalog = load_catalog(catalog_path)
    params_path = None if args.params is None else _model_path(args.params)
    fitted = None if args.defaults or params_path is None else load_fitted_params(params_path)
    if fitted is None:
        print("parameters: built-in defaults")
    else:
        print(f"parameters: k={fitted.k:.6g}, c_days={fitted.c_days:.6g}, p={fitted.p:.6g} from {params_path.name}")
    grid = score_grid(
        catalog,
        as_of=args.as_of,
        bounds=tuple(args.bounds),
        resolution_deg=args.resolution,
        magnitude_threshold=args.magnitude_threshold,
        local_signals=signals,
        params=fitted,
    )
    grid = attach_outlook(grid, magnitude_threshold=args.magnitude_threshold)
    grid = attach_public_zone(grid)
    csv_path, geojson_path = write_risk_grid(grid, out_path)
    guidance = build_guidance(grid, as_of=args.as_of)
    guidance_path = write_guidance(guidance, out_path.with_name(f"{out_path.stem}_guidance.json"))
    verdict, verdict_source = compose_verdict(grid, allow_network=args.rewrite_verdict)
    verdict_path = write_verdict(verdict, out_path.with_name(f"{out_path.stem}_verdict.txt"))
    if signals is not None:
        admitted = signals_to_triggers(
            signals,
            as_of=args.as_of,
            params=RiskParams(magnitude_threshold=args.magnitude_threshold),
            catalog=catalog,
        )
        print(f"local signals: {len(signals)} in file, {len(admitted)} admitted")
    _print_summary(grid, args.as_of, csv_path, geojson_path, guidance_path, verdict_path, verdict_source, verdict)
    return 0


def _model_path(path: Path) -> Path:
    """Resolve a relative path from the model folder, so the command works from the repo root."""
    if path.is_absolute():
        return path
    return ROOT / path


def _print_summary(
    grid,
    as_of: str,
    csv_path: Path,
    geojson_path: Path,
    guidance_path: Path,
    verdict_path: Path,
    verdict_source: str,
    verdict: str,
) -> None:
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
    print(f"  probability_m5_24h: {float(peak['probability_m5_24h']):.4f}")
    print(f"  probability_m6_24h: {float(peak['probability_m6_24h']):.4f}")
    print(f"  public_zone:     {peak['public_zone']}")
    print(f"  probability_7d:  {float(peak['probability_7d']):.4f}")
    print(f"bright zone (rate at least 30% of the peak, within 150 km): {radius:.1f} km")
    if remote:
        print(f"other cells above 30% of the peak, beyond 150 km: {remote}")
    levels = ", ".join(f"{name}={int(counts.get(name, 0))}" for name in ("low", "moderate", "elevated", "high"))
    print(f"risk levels: {levels}")
    print(f"wrote: {csv_path}")
    print(f"wrote: {geojson_path}")
    print(f"wrote: {guidance_path}")
    print(f"wrote: {verdict_path} ({verdict_source})")
    print(f"verdict: {verdict}")


if __name__ == "__main__":
    raise SystemExit(main())
