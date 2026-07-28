from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

GAP_QUEUE = (
    ROOT / "data/operations/mtg_history_gap_resolution/"
    "universal_mtg_history_gap_queue.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation"
)

BATCH_FIELDS = [
    "batch_id",
    "batch_sequence",
    "batch_label",
    "queue_rank",
    "canonical_product_id",
    "canonical_product_name",
    "product_class",
    "priority_tier",
    "priority_score",
    "gap_category",
    "tcgcsv_identity_status",
    "identity_review_required",
    "archive_recheck_required",
    "ebay_accumulation_required",
    "ebay_query",
    "query_strategy",
    "query_review_status",
    "live_collection_allowed",
    "daily_target_observations",
    "accumulation_target_dates",
]

SUMMARY_FIELDS = [
    "batch_id",
    "batch_sequence",
    "batch_label",
    "product_count",
    "product_classes",
    "priority_tiers",
    "identity_review_products",
    "archive_recheck_products",
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


def truthy(value: object) -> bool:
    return clean(value).casefold() in {"1", "true", "yes", "y"}


def build_query(row: dict[str, str]) -> tuple[str, str]:
    name = clean(row.get("canonical_product_name"))
    product_class = clean(row.get("product_class"))

    if product_class == "PRE_COLLECTOR_BOOSTER_BOX":
        return f'"{name}" sealed booster box', "EXACT_NAME_SEALED_BOX"

    return f'"{name}" sealed', "EXACT_NAME_SEALED_SECRET_LAIR"


def assign_batches(
    rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            int(clean(row.get("queue_rank")) or "0"),
            clean(row.get("canonical_product_id")),
        ),
    )

    pre_collector = [
        row for row in ordered
        if clean(row.get("product_class")) == "PRE_COLLECTOR_BOOSTER_BOX"
    ]
    p2_secret = [
        row for row in ordered
        if clean(row.get("product_class")) == "SECRET_LAIR"
        and clean(row.get("priority_tier")) == "P2_MEDIUM"
    ]
    p1_secret = [
        row for row in ordered
        if clean(row.get("product_class")) == "SECRET_LAIR"
        and clean(row.get("priority_tier")) == "P1_HIGH"
    ]
    p0_secret = [
        row for row in ordered
        if clean(row.get("product_class")) == "SECRET_LAIR"
        and clean(row.get("priority_tier")) == "P0_CRITICAL"
    ]

    batch_specs = [
        ("EBAY-HIST-001", "Pre-collector pilot", pre_collector),
        ("EBAY-HIST-002", "P2 Secret Lair batch A", p2_secret[:25]),
        ("EBAY-HIST-003", "P2 Secret Lair batch B", p2_secret[25:]),
        ("EBAY-HIST-004", "P1 Secret Lair batch A", p1_secret[:26]),
        ("EBAY-HIST-005", "P1 Secret Lair batch B", p1_secret[26:]),
        ("EBAY-HIST-006", "P0 Secret Lair batch A", p0_secret[:25]),
        ("EBAY-HIST-007", "P0 Secret Lair batch B", p0_secret[25:]),
    ]

    planned: list[dict[str, Any]] = []
    for sequence, (batch_id, label, products) in enumerate(
        batch_specs,
        start=1,
    ):
        for row in products:
            query, strategy = build_query(row)
            planned.append({
                "batch_id": batch_id,
                "batch_sequence": sequence,
                "batch_label": label,
                "queue_rank": int(clean(row.get("queue_rank")) or "0"),
                "canonical_product_id": clean(
                    row.get("canonical_product_id")
                ),
                "canonical_product_name": clean(
                    row.get("canonical_product_name")
                ),
                "product_class": clean(row.get("product_class")),
                "priority_tier": clean(row.get("priority_tier")),
                "priority_score": int(
                    clean(row.get("priority_score")) or "0"
                ),
                "gap_category": clean(row.get("gap_category")),
                "tcgcsv_identity_status": clean(
                    row.get("tcgcsv_identity_status")
                ),
                "identity_review_required": clean(
                    row.get("identity_review_required")
                ),
                "archive_recheck_required": clean(
                    row.get("archive_recheck_required")
                ),
                "ebay_accumulation_required": clean(
                    row.get("ebay_accumulation_required")
                ),
                "ebay_query": query,
                "query_strategy": strategy,
                "query_review_status": "PENDING_REVIEW",
                "live_collection_allowed": "false",
                "daily_target_observations": 1,
                "accumulation_target_dates": int(
                    clean(row.get("accumulation_target_dates")) or "30"
                ),
            })
    return planned


def summarize(
    planned: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_batch: dict[str, list[dict[str, Any]]] = {}
    for row in planned:
        by_batch.setdefault(str(row["batch_id"]), []).append(row)

    summary_rows: list[dict[str, Any]] = []
    for batch_id, rows in sorted(
        by_batch.items(),
        key=lambda item: int(item[1][0]["batch_sequence"]),
    ):
        summary_rows.append({
            "batch_id": batch_id,
            "batch_sequence": rows[0]["batch_sequence"],
            "batch_label": rows[0]["batch_label"],
            "product_count": len(rows),
            "product_classes": "|".join(sorted({
                str(row["product_class"]) for row in rows
            })),
            "priority_tiers": "|".join(sorted({
                str(row["priority_tier"]) for row in rows
            })),
            "identity_review_products": sum(
                truthy(row["identity_review_required"])
                for row in rows
            ),
            "archive_recheck_products": sum(
                truthy(row["archive_recheck_required"])
                for row in rows
            ),
            "live_collection_allowed": "false",
        })

    batch_counts = Counter(
        str(row["batch_id"]) for row in planned
    )
    expected = {
        "EBAY-HIST-001": 4,
        "EBAY-HIST-002": 25,
        "EBAY-HIST-003": 21,
        "EBAY-HIST-004": 26,
        "EBAY-HIST-005": 26,
        "EBAY-HIST-006": 25,
        "EBAY-HIST-007": 25,
    }

    summary = {
        "status": "PASS",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "planned_products": len(planned),
        "planned_batches": len(summary_rows),
        "batch_counts": dict(sorted(batch_counts.items())),
        "live_collection_enabled": False,
        "query_review_required_products": sum(
            row["query_review_status"] == "PENDING_REVIEW"
            for row in planned
        ),
        "identity_review_products": sum(
            truthy(row["identity_review_required"])
            for row in planned
        ),
        "archive_recheck_products": sum(
            truthy(row["archive_recheck_required"])
            for row in planned
        ),
        "certification_checks": {
            "planned_products_equal_152": len(planned) == 152,
            "planned_batches_equal_7": len(summary_rows) == 7,
            "batch_counts_match_plan": dict(batch_counts) == expected,
            "product_ids_unique": len({
                row["canonical_product_id"] for row in planned
            }) == len(planned),
            "all_queries_present": all(
                clean(row["ebay_query"]) for row in planned
            ),
            "all_queries_pending_review": all(
                row["query_review_status"] == "PENDING_REVIEW"
                for row in planned
            ),
            "live_collection_disabled_for_all": all(
                row["live_collection_allowed"] == "false"
                for row in planned
            ),
            "all_rows_require_ebay_accumulation": all(
                truthy(row["ebay_accumulation_required"])
                for row in planned
            ),
        },
    }
    if not all(summary["certification_checks"].values()):
        summary["status"] = "FAIL"

    return summary_rows, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a governed dry-run batch plan for eBay historical "
            "accumulation. This command never performs live collection."
        )
    )
    parser.add_argument("--gap-queue", type=Path, default=GAP_QUEUE)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    args = parser.parse_args()

    rows = read_csv(args.gap_queue.resolve())
    if len(rows) != 152:
        raise SystemExit(
            f"Expected 152 governed gap rows; found {len(rows)}."
        )

    planned = assign_batches(rows)
    summary_rows, summary = summarize(planned)

    output_root = args.output_root.resolve()
    write_csv(
        output_root / "universal_mtg_ebay_accumulation_batch_plan.csv",
        planned,
        BATCH_FIELDS,
    )
    write_csv(
        output_root / "universal_mtg_ebay_accumulation_batch_summary.csv",
        summary_rows,
        SUMMARY_FIELDS,
    )
    (
        output_root / "universal_mtg_ebay_accumulation_batch_summary.json"
    ).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
