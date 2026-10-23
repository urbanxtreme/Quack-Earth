"""Fit K, c, and p on the cached catalog and write ``params.json``.

From the repo root:

    python model/scripts/run_calibrate.py

The catalog must already be at ``data/cache/catalog.csv``. Alpha and the
spatial kernel stay at their built-in values.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quack_risk.calibrate import fit_catalog, write_params  # noqa: E402
from quack_risk.config import DEMO_BOUNDS  # noqa: E402
from quack_risk.io import load_catalog  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fit K, c, and p on the cached catalog.")
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "cache" / "catalog.csv")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "cache" / "params.json")
    parser.add_argument("--resolution", type=float, default=0.2)
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--maxiter", type=int, default=20)
    args = parser.parse_args(argv)
    catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    out_path = args.out if args.out.is_absolute() else ROOT / args.out
    catalog = load_catalog(catalog_path)

    def progress(k: float, c_days: float, p: float) -> None:
        print(f"  candidate k={k:.6g} c_days={c_days:.4g} p={p:.3f}")

    result = fit_catalog(
        catalog,
        bounds=DEMO_BOUNDS,
        resolution_deg=args.resolution,
        n_days=args.days,
        maxiter=args.maxiter,
        progress=progress,
    )
    write_params(result, out_path)
    print(f"origin: {result.origin}")
    print(f"observed M>=4 events in the {result.n_days} days: {result.n_observed}")
    print(f"k={result.params.k:.6g} c_days={result.params.c_days:.6g} p={result.params.p:.6g}")
    print(f"log_likelihood: {result.log_likelihood:.1f}")
    print(f"baseline_log_likelihood: {result.baseline_log_likelihood:.1f}")
    print(f"fitted rate beats baseline: {result.log_likelihood > result.baseline_log_likelihood}")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
