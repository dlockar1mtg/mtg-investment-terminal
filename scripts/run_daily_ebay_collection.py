"""Governed command-line entry point for daily eBay marketplace collection.

The production entry point is fail-closed on the certified precision-v2 matcher.
Dry runs make no network calls and still report the matcher that a live run would
use.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_precision_production import (
    MATCHER_VERSION,
    run_precision_coverage,
    run_precision_targeted_coverage,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed daily eBay collection")
    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--max-products", type=int)
    parser.add_argument("--product-map", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument(
        "--matcher-version",
        choices=(MATCHER_VERSION,),
        default=MATCHER_VERSION,
        help="Certified matcher version. Legacy fallback is intentionally unavailable.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.limit_per_product < 1 or args.limit_per_product > 200:
        parser.error("--limit-per-product must be between 1 and 200")
    if args.max_products is not None and args.max_products < 1:
        parser.error("--max-products must be positive")
    if args.product_map is not None and not args.product_map.is_file():
        parser.error("--product-map must reference an existing CSV file")

    if args.dry_run:
        summary = {
            "status": "DRY_RUN",
            "live_api_called": False,
            "limit_per_product": args.limit_per_product,
            "max_products": args.max_products,
            "product_map": str(args.product_map.resolve()) if args.product_map else "",
            "selection_mode": "PRODUCT_MAP_TARGETED" if args.product_map else "UNIVERSE_PREFIX",
            "matcher_version": MATCHER_VERSION,
            "matcher_entrypoint": "terminal2.market_sources.ebay_precision_v2.identity_match_listing",
            "matcher_fail_closed": True,
        }
    else:
        progress = io.StringIO()
        with redirect_stdout(progress):
            if args.product_map:
                coverage = run_precision_targeted_coverage(
                    product_map=args.product_map.resolve(),
                    limit_per_product=args.limit_per_product,
                )
            else:
                coverage = run_precision_coverage(
                    limit_per_product=args.limit_per_product,
                    max_products=args.max_products,
                )
        progress_lines = [line for line in progress.getvalue().splitlines() if line.strip()]
        summary = {
            "status": "PASS",
            "live_api_called": True,
            **coverage,
            "progress_log": progress_lines,
        }

    rendered = json.dumps(summary, indent=2)
    if args.summary_output:
        args.summary_output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
