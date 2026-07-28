from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

COMPLETION_STATUS = (
    ROOT / "data/operations/mtg_universal_history_ledger/"
    "universal_mtg_history_completion_status.csv"
)
ROUTING_MATRIX = (
    ROOT / "data/operations/mtg_universal_history_completion/"
    "universal_history_routing_matrix.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_history_gap_resolution"
)

QUEUE_FIELDS = [
    "queue_rank",
    "canonical_product_id",
    "canonical_product_name",
    "product_class",
    "tcgplayer_product_id",
    "tcgcsv_identity_status",
    "tcgcsv_archive_eligible",
    "ebay_history_eligible",
    "primary_history_route",
    "history_completion_route",
    "gap_category",
    "resolution_action",
    "priority_score",
    "priority_tier",
    "identity_review_required",
    "archive_recheck_required",
    "ebay_accumulation_required",
    "accumulation_target_dates",
    "current_distinct_history_dates",
]

SUMMARY_FIELDS = [
    "gap_category",
    "product_class",
    "priority_tier",
    "product_count",
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


def truthy(value: object) -> bool:
    return clean(value).casefold() in {"1", "true", "yes", "y"}


def classify_gap(
    completion: dict[str, str],
    route: dict[str, str],
) -> tuple[str, str, int]:
    completion_route = clean(completion.get("history_completion_route"))
    identity_status = clean(route.get("tcgcsv_identity_status"))
    archive_eligible = truthy(route.get("tcgcsv_archive_eligible"))
    ebay_eligible = truthy(route.get("ebay_history_eligible"))

    if completion_route == "EBAY_ACCUMULATION_REQUIRED":
        if identity_status == "TCGCSV_ID_AMBIGUOUS":
            return (
                "IDENTITY_AMBIGUOUS_EBAY_ACCUMULATION",
                "Review identity while beginning governed eBay accumulation",
                95,
            )
        if identity_status == "TCGCSV_ID_NOT_FOUND":
            return (
                "IDENTITY_NOT_FOUND_EBAY_ACCUMULATION",
                "Begin governed eBay accumulation and retain identity review",
                90,
            )
        return (
            "EBAY_ACCUMULATION_ONLY",
            "Begin governed eBay daily accumulation",
            85,
        )

    if completion_route == "ARCHIVE_HISTORY_NOT_AVAILABLE":
        if archive_eligible:
            return (
                "ARCHIVE_ELIGIBLE_NO_OBSERVATIONS",
                "Recheck archive identity and add eBay fallback accumulation",
                80,
            )
        if ebay_eligible:
            return (
                "ARCHIVE_UNAVAILABLE_EBAY_FALLBACK",
                "Begin governed eBay fallback accumulation",
                75,
            )
        return (
            "NO_SOURCE_ROUTE_AVAILABLE",
            "Manual source and identity research required",
            100,
        )

    return (
        "UNCLASSIFIED_NO_HISTORY",
        "Manual review required",
        70,
    )


def priority_tier(score: int) -> str:
    if score >= 95:
        return "P0_CRITICAL"
    if score >= 85:
        return "P1_HIGH"
    if score >= 75:
        return "P2_MEDIUM"
    return "P3_LOW"


def build_queue(
    completion_rows: list[dict[str, str]],
    routing_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    route_by_id = {
        clean(row.get("universal_mtg_product_id")): row
        for row in routing_rows
        if clean(row.get("universal_mtg_product_id"))
    }

    queue: list[dict[str, Any]] = []
    missing_routes: list[str] = []

    for completion in completion_rows:
        if clean(completion.get("history_verification_status")) != "NO_DIRECT_HISTORY":
            continue

        product_id = clean(completion.get("canonical_product_id"))
        route = route_by_id.get(product_id)
        if route is None:
            missing_routes.append(product_id)
            route = {}

        gap_category, action, score = classify_gap(completion, route)
        archive_eligible = truthy(route.get("tcgcsv_archive_eligible"))
        ebay_eligible = truthy(route.get("ebay_history_eligible"))
        identity_status = clean(route.get("tcgcsv_identity_status"))
        completion_route = clean(completion.get("history_completion_route"))

        queue.append({
            "queue_rank": 0,
            "canonical_product_id": product_id,
            "canonical_product_name": clean(
                completion.get("canonical_product_name")
            ),
            "product_class": clean(completion.get("product_class")),
            "tcgplayer_product_id": clean(
                completion.get("tcgplayer_product_id")
            ),
            "tcgcsv_identity_status": identity_status,
            "tcgcsv_archive_eligible": str(archive_eligible).lower(),
            "ebay_history_eligible": str(ebay_eligible).lower(),
            "primary_history_route": clean(
                route.get("primary_history_route")
            ),
            "history_completion_route": completion_route,
            "gap_category": gap_category,
            "resolution_action": action,
            "priority_score": score,
            "priority_tier": priority_tier(score),
            "identity_review_required": str(
                identity_status in {
                    "TCGCSV_ID_AMBIGUOUS",
                    "TCGCSV_ID_NOT_FOUND",
                    "TCGCSV_ID_GROUP_NOT_RESOLVED",
                    "TCGCSV_ID_AMBIGUOUS_CATEGORY_GROUP",
                }
            ).lower(),
            "archive_recheck_required": str(
                gap_category == "ARCHIVE_ELIGIBLE_NO_OBSERVATIONS"
            ).lower(),
            "ebay_accumulation_required": str(
                completion_route == "EBAY_ACCUMULATION_REQUIRED"
                or gap_category in {
                    "ARCHIVE_ELIGIBLE_NO_OBSERVATIONS",
                    "ARCHIVE_UNAVAILABLE_EBAY_FALLBACK",
                }
            ).lower(),
            "accumulation_target_dates": 30,
            "current_distinct_history_dates": int(
                clean(completion.get("distinct_history_dates")) or "0"
            ),
        })

    queue.sort(
        key=lambda row: (
            -int(row["priority_score"]),
            row["product_class"],
            row["canonical_product_name"].casefold(),
            row["canonical_product_id"],
        )
    )
    for index, row in enumerate(queue, start=1):
        row["queue_rank"] = index

    grouped = Counter(
        (
            row["gap_category"],
            row["product_class"],
            row["priority_tier"],
        )
        for row in queue
    )
    summary_rows = [
        {
            "gap_category": key[0],
            "product_class": key[1],
            "priority_tier": key[2],
            "product_count": count,
        }
        for key, count in sorted(grouped.items())
    ]

    gap_counts = Counter(row["gap_category"] for row in queue)
    class_counts = Counter(row["product_class"] for row in queue)
    priority_counts = Counter(row["priority_tier"] for row in queue)

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "completion_rows": len(completion_rows),
        "routing_rows": len(routing_rows),
        "gap_queue_rows": len(queue),
        "missing_route_rows": len(missing_routes),
        "missing_route_product_ids": sorted(missing_routes),
        "gap_category_counts": dict(sorted(gap_counts.items())),
        "product_class_counts": dict(sorted(class_counts.items())),
        "priority_tier_counts": dict(sorted(priority_counts.items())),
        "identity_review_products": sum(
            row["identity_review_required"] == "true"
            for row in queue
        ),
        "archive_recheck_products": sum(
            row["archive_recheck_required"] == "true"
            for row in queue
        ),
        "ebay_accumulation_products": sum(
            row["ebay_accumulation_required"] == "true"
            for row in queue
        ),
        "certification_checks": {
            "completion_rows_equal_1141": len(completion_rows) == 1141,
            "routing_rows_equal_1141": len(routing_rows) == 1141,
            "gap_queue_rows_equal_152": len(queue) == 152,
            "queue_product_ids_unique": len({
                row["canonical_product_id"] for row in queue
            }) == len(queue),
            "all_gap_rows_have_resolution_action": all(
                clean(row["resolution_action"]) for row in queue
            ),
            "all_gap_rows_have_priority": all(
                clean(row["priority_tier"]) for row in queue
            ),
            "no_missing_route_rows": not missing_routes,
            "all_gap_rows_start_with_zero_history": all(
                int(row["current_distinct_history_dates"]) == 0
                for row in queue
            ),
        },
    }

    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    return queue, summary_rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the governed historical-gap resolution and accumulation "
            "queue for all MTG products without direct dated history."
        )
    )
    parser.add_argument(
        "--completion-status",
        type=Path,
        default=COMPLETION_STATUS,
    )
    parser.add_argument(
        "--routing-matrix",
        type=Path,
        default=ROUTING_MATRIX,
    )
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    queue, summary_rows, summary = build_queue(
        read_csv(args.completion_status.resolve()),
        read_csv(args.routing_matrix.resolve()),
    )

    output_root = args.output_root.resolve()
    write_csv(
        output_root / "universal_mtg_history_gap_queue.csv",
        queue,
        QUEUE_FIELDS,
    )
    write_csv(
        output_root / "universal_mtg_history_gap_summary.csv",
        summary_rows,
        SUMMARY_FIELDS,
    )
    (
        output_root / "universal_mtg_history_gap_summary.json"
    ).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
