from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_matching import run_coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="Run governed MTG product matching against eBay Browse API.")
    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--max-products", type=int, default=None)
    args = parser.parse_args()
    summary = run_coverage(args.limit_per_product, args.max_products)
    print("\nEBAY MATCHING COVERAGE: COMPLETE")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
