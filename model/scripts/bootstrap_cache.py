"""Download the demo-box catalog into ``data/cache/catalog.csv``.

From the repo root:

    python model/scripts/bootstrap_cache.py

The score step does not call the network. Run this once, or when the backend
file is not in the cache yet. A later backend file can replace the same path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from quack_risk.catalog_fetch import download_catalog  # noqa: E402
from quack_risk.io import load_catalog  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download the regional M>=4 catalog into the cache.")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "cache" / "catalog.csv")
    parser.add_argument("--force", action="store_true", help="Replace an existing cache file.")
    args = parser.parse_args(argv)
    destination = args.out if args.out.is_absolute() else ROOT / args.out
    path = download_catalog(destination, force=args.force)
    catalog = load_catalog(path)
    print(f"events: {len(catalog)}")
    print(
        "span: "
        f"{catalog['time'].iloc[0].strftime('%Y-%m-%d')} to {catalog['time'].iloc[-1].strftime('%Y-%m-%d')}"
    )
    print(f"largest: M {float(catalog['magnitude'].max()):.1f}")
    print(f"wrote: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
