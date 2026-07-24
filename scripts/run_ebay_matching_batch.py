from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources import ebay_matching as base
from terminal2.market_sources.ebay_matching import EbayBrowseClient
from terminal2.market_sources.ebay_precision import run_coverage
from terminal2.market_sources.ebay_resilience import (
    estimate_batch_calls,
    format_reset_local,
    get_browse_quota,
)
from terminal2.market_sources.ebay_resume import build_resume_plan, select_pending_products
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
    parser.add_argument("--skip-quota-check", action="store_true")
    parser.add_argument("--quota-reserve", type=int, default=100)
    parser.add_argument(
        "--resume-plan",
        action="store_true",
        help="Inspect prior attempts and report which selected products remain unfinished.",
    )
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

    if args.quota_reserve < 0:
        raise SystemExit("--quota-reserve must be zero or greater")

    if not args.skip_quota_check:
        client = EbayBrowseClient()
        quota = get_browse_quota(client)
        estimated_calls = estimate_batch_calls(len(subset))
        print("EBAY BROWSE QUOTA PREFLIGHT")
        print(f"  limit: {quota.limit}")
        print(f"  used: {quota.count}")
        print(f"  remaining: {quota.remaining}")
        print(f"  estimated maximum calls: {estimated_calls}")
        print(f"  reserve: {args.quota_reserve}")
        print(f"  reset UTC: {quota.reset or 'unknown'}")
        print(f"  reset local: {format_reset_local(quota.reset)}")
        if not quota.supports(estimated_calls, reserve_calls=args.quota_reserve):
            raise SystemExit(
                "INSUFFICIENT EBAY BROWSE QUOTA: "
                f"remaining={quota.remaining}, required={estimated_calls}, "
                f"reserve={args.quota_reserve}, reset={quota.reset or 'unknown'}"
            )

    end = args.offset + len(subset) - 1
    batch_key = f"{args.product_class.lower()}_{args.offset:04d}_{end:04d}"
    batch_root = base.OUTPUT_ROOT / "batches" / batch_key

    if args.resume_plan:
        plan = build_resume_plan(
            batch_root,
            [product.canonical_product_id for product in subset],
        )
        print("EBAY BATCH RESUME PLAN")
        print(f"  batch: {batch_key}")
        print(f"  expected products: {len(plan.expected_product_ids)}")
        print(f"  completed products: {len(plan.completed_product_ids)}")
        print(f"  pending products: {len(plan.pending_product_ids)}")
        print(f"  prior source errors: {len(plan.source_error_product_ids)}")
        print(f"  coverage files inspected: {len(plan.coverage_files)}")
        print(f"  estimated maximum resume calls: {estimate_batch_calls(len(plan.pending_product_ids))}")
        if plan.pending_product_ids:
            print("  pending product IDs:")
            for product_id in plan.pending_product_ids:
                print(f"    {product_id}")
        return 0

    attempt_key = datetime.now(timezone.utc).strftime("attempt_%Y%m%dT%H%M%SZ")
    attempt_root = batch_root / "attempts" / attempt_key
    existing = sorted(batch_root.glob("ebay_matching_summary_*.json"))
    if existing and not args.force:
        print(f"BATCH ALREADY COMPLETE: {batch_key}")
        print(existing[-1])
        return 0

    original_output = base.OUTPUT_ROOT
    base.OUTPUT_ROOT = attempt_root
    try:
        summary = run_coverage(
            limit_per_product=args.limit_per_product,
            max_products=None,
            universe_override=subset,
        )
    finally:
        base.OUTPUT_ROOT = original_output

    processed = int(summary.get("products", -1))
    source_errors = int(summary.get("coverage_states", {}).get("SOURCE_ERROR", 0))
    aborted_early = bool(summary.get("aborted_early", False))
    if processed != len(subset) or source_errors or aborted_early:
        print("\nEBAY MATCHING BATCH: INCOMPLETE")
        print(f"Attempt preserved at: {attempt_root}")
        print(
            f"selected={len(subset)} processed={processed} "
            f"source_errors={source_errors} aborted_early={aborted_early}"
        )
        raise SystemExit(2)

    batch_root.mkdir(parents=True, exist_ok=True)
    for path in attempt_root.iterdir():
        if path.is_file():
            shutil.copy2(path, batch_root / path.name)

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
