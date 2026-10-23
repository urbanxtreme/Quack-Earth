"""Write the four evaluation plots from the cached catalog and fitted parameters.

From the repo root:

    python model/scripts/run_eval.py

Plots land in ``outputs/plots/``. If ``params.json`` is missing, the built-in
K, c, and p are used.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quack_risk.calibrate import load_fitted_params  # noqa: E402
from quack_risk.config import RiskParams  # noqa: E402
from quack_risk.evaluate import write_evaluation  # noqa: E402
from quack_risk.io import load_catalog  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write retrospective plots for the cached catalog.")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "cache" / "catalog.csv")
    parser.add_argument("--params", type=Path, default=ROOT / "data" / "cache" / "params.json")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "plots")
    parser.add_argument("--resolution", type=float, default=0.2)
    args = parser.parse_args(argv)
    catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    params_path = args.params if args.params.is_absolute() else ROOT / args.params
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    params = load_fitted_params(params_path) or RiskParams()
    source = params_path if params_path.is_file() else "built-in defaults"
    metrics = write_evaluation(load_catalog(catalog_path), params, out_path, resolution_deg=args.resolution)
    print(f"parameters: {source}")
    print(f"k={metrics['k']:.6g} c_days={metrics['c_days']:.6g} p={metrics['p']:.6g}")
    print(f"log_likelihood full: {metrics['log_likelihood_full']:.1f}")
    print(f"log_likelihood baseline: {metrics['log_likelihood_baseline']:.1f}")
    print(f"fitted rate beats baseline: {metrics['full_beats_baseline']}")
    print(f"top 20% of cells capture: {metrics['top20_capture']:.1%} of M>=4.5 events in the next 24h")
    print(f"mean predicted per day: {metrics['mean_predicted_per_day']:.2f}")
    print(f"mean observed per day: {metrics['mean_observed_per_day']:.2f}")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
