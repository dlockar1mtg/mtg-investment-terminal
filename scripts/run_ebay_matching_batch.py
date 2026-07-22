from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_precision import run_coverage
from terminal2.market_sources.ebay_universe import build_complete_universe


ALLOWED_CLASSES = {
    "COLLECTOR_BOOSTER_BOX",
    "PRE_COLLECTOR_BOOSTER_BOX",
    "SEALED_SECRET_LAIR",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a resumable governed eBay matching batch."
    )
    parser.add_argument("--product-class", choices=sorted(ALLOWED_CLASSES), required=True)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.offset < 0:
        raise SystemExit("--offset must be zero or greater")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1")

    full_universe = [
        product
        for product in build_complete_universe()
        if product.product_class == args.product_class
    ]
    subset = full_universe[args.offset : args.offset + args.batch_size]
    if not subset:
        print("No products remain for this batch selection.")
        return 0

    end = args.offset + len(subset) - 1
    batch_key = f"{args.product_class.lower()}_{args.offset:04d}_{end:04d}"
    batch_root = base.OUTPUT_ROOT / "batches" / batch_key
    existing = sorted(batch_root.glob("ebay_matching_summary_*.json"))
    if existing and not args.force:
        print(f"BATCH ALREADY COMPLETE: {batch_key}")
        print(existing[-1])
        return 0

    original_output = base.OUTPUT_ROOT
    base.OUTPUT_ROOT = batch_root
    try:
        summary = run_coverage(
            limit_per_product=args.limit_per_product,
            max_products=None,
            universe_override=subset,
        )
    finally:
        base.OUTPUT_ROOT = original_output

    if int(summary.get("products", -1)) != len(subset):
        raise RuntimeError(
            "Batch universe mismatch: "
            f"selected={len(subset)} processed={summary.get('products')}"
        )

    manifest = {
        "batch_key": batch_key,
        "product_class": args.product_class,
        "offset": args.offset,
        "end_offset": end,
        "batch_size": len(subset),
        "class_universe_size": len(full_universe),
        "product_ids": [product.canonical_product_id for product in subset],
        "summary": summary,
    }
    batch_root.mkdir(parents=True, exist_ok=True)
    (batch_root / "batch_manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print("\nEBAY MATCHING BATCH: COMPLETE")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
