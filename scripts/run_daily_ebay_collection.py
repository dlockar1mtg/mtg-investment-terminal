"""Governed command-line entry point for daily eBay marketplace collection.

This wrapper reuses the certified eBay matching implementation. It does not
change matching rules, product identity, or credential handling.
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

from terminal2.market_sources.ebay_matching import run_coverage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run governed daily eBay collection")
    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--max-products", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--summary-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.limit_per_product < 1 or args.limit_per_product > 200:
        parser.error("--limit-per-product must be between 1 and 200")
    if args.max_products is not None and args.max_products < 1:
        parser.error("--max-products must be positive")

    if args.dry_run:
        summary = {
            "status": "DRY_RUN",
            "live_api_called": False,
            "limit_per_product": args.limit_per_product,
            "max_products": args.max_products,
        }
    else:
        progress = io.StringIO()
        with redirect_stdout(progress):
            coverage = run_coverage(
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
