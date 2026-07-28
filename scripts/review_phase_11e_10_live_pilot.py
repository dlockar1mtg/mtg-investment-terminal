from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_history_pipeline import (
    HistoryQuery,
    ReplayListing,
    classify_listing,
)

PLAN = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "normalized_queries/universal_mtg_ebay_normalized_query_plan.csv"
)
DEFAULT_ATTEMPT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "live_pilot/EBAY-HIST-001/attempts/attempt_20260728T120330Z"
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def query_map() -> dict[str, HistoryQuery]:
    rows = [
        row for row in read_csv(PLAN)
        if row.get("batch_id") == "EBAY-HIST-001"
    ]
    return {
        row["canonical_product_id"]: HistoryQuery(
            canonical_product_id=row["canonical_product_id"],
            canonical_product_name=row["canonical_product_name"],
            product_class=row["product_class"],
            query=row["normalized_ebay_query"],
        )
        for row in rows
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt-root", type=Path, default=DEFAULT_ATTEMPT)
    args = parser.parse_args()

    attempt_root = args.attempt_root.resolve()
    source = attempt_root / "classified_listings.csv"
    if not source.is_file():
        raise SystemExit(f"Missing live listing artifact: {source}")

    products = query_map()
    reviewed: list[dict[str, Any]] = []

    for row in read_csv(source):
        product_id = row["canonical_product_id"]
        query = products[product_id]
        classified = classify_listing(
            query,
            ReplayListing(
                item_id=row.get("item_id", ""),
                title=row.get("title", ""),
                price=float(row.get("price", 0.0) or 0.0),
                currency=row.get("currency", ""),
                condition="",
            ),
        )
        reviewed.append({
            "canonical_product_id": product_id,
            "canonical_product_name": query.canonical_product_name,
            "item_id": classified.item_id,
            "title": classified.title,
            "price": classified.price,
            "currency": classified.currency,
            "original_accepted": row.get("accepted", "").lower(),
            "hardened_accepted": str(classified.accepted).lower(),
            "classification": classified.classification,
            "rejection_reason": classified.rejection_reason,
        })

    accepted = [row for row in reviewed if row["hardened_accepted"] == "true"]
    false_positives = [
        row for row in reviewed
        if row["original_accepted"] == "true"
        and row["hardened_accepted"] == "false"
    ]
    accepted_products = {row["canonical_product_id"] for row in accepted}

    reason_counts: Counter[str] = Counter()
    for row in reviewed:
        for reason in row["rejection_reason"].split("|"):
            if reason:
                reason_counts[reason] += 1

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "attempt_root": str(attempt_root),
        "reviewed_listings": len(reviewed),
        "originally_accepted_listings": sum(
            row["original_accepted"] == "true" for row in reviewed
        ),
        "hardened_accepted_listings": len(accepted),
        "false_positive_listings_removed": len(false_positives),
        "hardened_matched_products": len(accepted_products),
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "promotion_eligible": False,
        "promotion_state": "BLOCKED_FALSE_POSITIVE_LIVE_RESULTS",
        "rerun_required": True,
        "rerun_query_policy": "MAGIC_THE_GATHERING_PREFIX_REQUIRED",
        "certification_checks": {
            "all_22_original_accepts_reviewed": len(reviewed) == 22,
            "all_non_mtg_false_positives_removed": len(false_positives) == 22,
            "promotion_remains_blocked": True,
            "live_rerun_not_performed": True,
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    review_root = attempt_root / "manual_review"
    write_csv(
        review_root / "hardened_listing_review.csv",
        reviewed,
        [
            "canonical_product_id",
            "canonical_product_name",
            "item_id",
            "title",
            "price",
            "currency",
            "original_accepted",
            "hardened_accepted",
            "classification",
            "rejection_reason",
        ],
    )
    (review_root / "hardened_review_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
