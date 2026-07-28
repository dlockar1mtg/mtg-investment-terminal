from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_resilience import estimate_batch_calls
from terminal2.market_sources.ebay_resume import build_resume_plan

NORMALIZED_PLAN = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "normalized_queries/universal_mtg_ebay_normalized_query_plan.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/preflight"
)
DEFAULT_BATCH_ROOT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/live_batches"
)

DETAIL_FIELDS = [
    "batch_id",
    "batch_sequence",
    "batch_label",
    "canonical_product_id",
    "canonical_product_name",
    "product_class",
    "priority_tier",
    "normalized_ebay_query",
    "query_review_status",
    "resume_state",
    "estimated_maximum_calls",
    "quota_reserve",
    "simulated_quota_remaining",
    "quota_supported",
    "dry_run_allowed",
    "live_collection_allowed",
]

BATCH_FIELDS = [
    "batch_id",
    "batch_sequence",
    "batch_label",
    "planned_products",
    "completed_products",
    "source_error_products",
    "pending_products",
    "estimated_maximum_calls",
    "quota_reserve",
    "simulated_quota_remaining",
    "quota_supported",
    "query_approval_complete",
    "dry_run_allowed",
    "live_collection_allowed",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path,
    rows: list[dict[str, Any]],
    fields: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def clean(value: object) -> str:
    return str(value or "").strip()


def group_batches(
    rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(clean(row.get("batch_id")), []).append(row)
    return grouped


def build_preflight(
    rows: list[dict[str, str]],
    batch_root: Path,
    simulated_quota_remaining: int,
    quota_reserve: int,
    maximum_queries_per_product: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    if simulated_quota_remaining < 0:
        raise ValueError("simulated_quota_remaining must be nonnegative")
    if quota_reserve < 0:
        raise ValueError("quota_reserve must be nonnegative")
    if maximum_queries_per_product < 1:
        raise ValueError("maximum_queries_per_product must be at least 1")

    detail_rows: list[dict[str, Any]] = []
    batch_rows: list[dict[str, Any]] = []

    grouped = group_batches(rows)
    for batch_id, products in sorted(
        grouped.items(),
        key=lambda item: int(clean(item[1][0].get("batch_sequence")) or "0"),
    ):
        expected_ids = [
            clean(row.get("canonical_product_id"))
            for row in products
        ]
        resume = build_resume_plan(
            batch_root / batch_id,
            expected_ids,
        )
        completed = set(resume.completed_product_ids)
        source_errors = set(resume.source_error_product_ids)
        pending = set(resume.pending_product_ids)

        estimated_calls = estimate_batch_calls(
            len(pending),
            maximum_queries_per_product=maximum_queries_per_product,
        )
        quota_supported = (
            simulated_quota_remaining
            >= estimated_calls + quota_reserve
        )
        query_complete = all(
            clean(row.get("query_review_status"))
            == "APPROVED_FOR_DRY_RUN"
            and clean(row.get("normalized_ebay_query"))
            for row in products
        )
        dry_run_allowed = quota_supported and query_complete

        batch_rows.append({
            "batch_id": batch_id,
            "batch_sequence": clean(
                products[0].get("batch_sequence")
            ),
            "batch_label": clean(products[0].get("batch_label")),
            "planned_products": len(products),
            "completed_products": len(completed),
            "source_error_products": len(source_errors),
            "pending_products": len(pending),
            "estimated_maximum_calls": estimated_calls,
            "quota_reserve": quota_reserve,
            "simulated_quota_remaining": simulated_quota_remaining,
            "quota_supported": str(quota_supported).lower(),
            "query_approval_complete": str(query_complete).lower(),
            "dry_run_allowed": str(dry_run_allowed).lower(),
            "live_collection_allowed": "false",
        })

        for row in products:
            product_id = clean(row.get("canonical_product_id"))
            if product_id in completed:
                resume_state = "COMPLETED"
            elif product_id in source_errors:
                resume_state = "SOURCE_ERROR_RETRY"
            else:
                resume_state = "PENDING"

            detail_rows.append({
                "batch_id": batch_id,
                "batch_sequence": clean(row.get("batch_sequence")),
                "batch_label": clean(row.get("batch_label")),
                "canonical_product_id": product_id,
                "canonical_product_name": clean(
                    row.get("canonical_product_name")
                ),
                "product_class": clean(row.get("product_class")),
                "priority_tier": clean(row.get("priority_tier")),
                "normalized_ebay_query": clean(
                    row.get("normalized_ebay_query")
                ),
                "query_review_status": clean(
                    row.get("query_review_status")
                ),
                "resume_state": resume_state,
                "estimated_maximum_calls": estimated_calls,
                "quota_reserve": quota_reserve,
                "simulated_quota_remaining": simulated_quota_remaining,
                "quota_supported": str(quota_supported).lower(),
                "dry_run_allowed": str(dry_run_allowed).lower(),
                "live_collection_allowed": "false",
            })

    batch_counts = Counter(
        row["batch_id"] for row in detail_rows
    )
    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "planned_products": len(detail_rows),
        "planned_batches": len(batch_rows),
        "simulated_quota_remaining": simulated_quota_remaining,
        "quota_reserve": quota_reserve,
        "maximum_queries_per_product": maximum_queries_per_product,
        "completed_products": sum(
            row["resume_state"] == "COMPLETED"
            for row in detail_rows
        ),
        "source_error_products": sum(
            row["resume_state"] == "SOURCE_ERROR_RETRY"
            for row in detail_rows
        ),
        "pending_products": sum(
            row["resume_state"] == "PENDING"
            for row in detail_rows
        ),
        "dry_run_allowed_batches": sum(
            row["dry_run_allowed"] == "true"
            for row in batch_rows
        ),
        "live_collection_enabled": False,
        "batch_counts": dict(sorted(batch_counts.items())),
        "certification_checks": {
            "planned_products_equal_152": len(detail_rows) == 152,
            "planned_batches_equal_7": len(batch_rows) == 7,
            "product_ids_unique": len({
                row["canonical_product_id"] for row in detail_rows
            }) == len(detail_rows),
            "all_queries_approved": all(
                row["query_review_status"] == "APPROVED_FOR_DRY_RUN"
                for row in detail_rows
            ),
            "all_queries_present": all(
                clean(row["normalized_ebay_query"])
                for row in detail_rows
            ),
            "resume_states_valid": all(
                row["resume_state"] in {
                    "COMPLETED",
                    "SOURCE_ERROR_RETRY",
                    "PENDING",
                }
                for row in detail_rows
            ),
            "live_collection_disabled_for_all": all(
                row["live_collection_allowed"] == "false"
                for row in detail_rows
            ),
        },
    }

    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    return detail_rows, batch_rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build an offline eBay history dry-run preflight with quota "
            "simulation and resume planning. No live eBay calls are made."
        )
    )
    parser.add_argument(
        "--normalized-plan",
        type=Path,
        default=NORMALIZED_PLAN,
    )
    parser.add_argument(
        "--batch-root",
        type=Path,
        default=DEFAULT_BATCH_ROOT,
    )
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument(
        "--simulated-quota-remaining",
        type=int,
        default=5000,
    )
    parser.add_argument("--quota-reserve", type=int, default=100)
    parser.add_argument(
        "--maximum-queries-per-product",
        type=int,
        default=3,
    )
    args = parser.parse_args()

    rows = read_csv(args.normalized_plan.resolve())
    if len(rows) != 152:
        raise SystemExit(
            f"Expected 152 normalized plan rows; found {len(rows)}."
        )

    detail_rows, batch_rows, summary = build_preflight(
        rows=rows,
        batch_root=args.batch_root.resolve(),
        simulated_quota_remaining=args.simulated_quota_remaining,
        quota_reserve=args.quota_reserve,
        maximum_queries_per_product=args.maximum_queries_per_product,
    )

    output_root = args.output_root.resolve()
    write_csv(
        output_root / "universal_mtg_ebay_preflight_products.csv",
        detail_rows,
        DETAIL_FIELDS,
    )
    write_csv(
        output_root / "universal_mtg_ebay_preflight_batches.csv",
        batch_rows,
        BATCH_FIELDS,
    )
    (
        output_root / "universal_mtg_ebay_preflight_summary.json"
    ).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
