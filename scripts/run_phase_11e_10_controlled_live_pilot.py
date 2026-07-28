from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_history_live import (
    LiveBrowseHistoryCollector,
    collect_live_product,
    credentials_present,
    inspect_quota,
    serialize_product_result,
)
from terminal2.market_sources.ebay_history_pipeline import HistoryQuery
from terminal2.market_sources.ebay_resilience import estimate_batch_calls

PLAN = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "normalized_queries/universal_mtg_ebay_normalized_query_plan.csv"
)
OUTPUT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "live_pilot/EBAY-HIST-001"
)
ENABLE_ENV = "MTG_EBAY_HISTORY_LIVE_ENABLED"
CONFIRMATION = "EXECUTE-EBAY-HIST-001"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def pilot_queries(path: Path = PLAN) -> list[HistoryQuery]:
    rows = [
        row for row in read_csv(path)
        if row.get("batch_id") == "EBAY-HIST-001"
    ]
    return [
        HistoryQuery(
            canonical_product_id=row["canonical_product_id"],
            canonical_product_name=row["canonical_product_name"],
            product_class=row["product_class"],
            query=row["normalized_ebay_query"],
        )
        for row in rows
    ]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def readiness(queries: list[HistoryQuery], quota_reserve: int) -> dict[str, Any]:
    credential_ready = credentials_present()
    quota_payload: dict[str, Any]
    quota_ready = False
    if credential_ready:
        try:
            quota = inspect_quota()
            required = estimate_batch_calls(len(queries), maximum_queries_per_product=3)
            quota_ready = quota.supports(required, reserve_calls=quota_reserve)
            quota_payload = {
                "limit": quota.limit,
                "used": quota.count,
                "remaining": quota.remaining,
                "reset": quota.reset,
                "required_calls": required,
                "reserve_calls": quota_reserve,
                "supported": quota_ready,
            }
        except Exception as exc:
            quota_payload = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        quota_payload = {"error": "EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are unavailable"}

    return {
        "status": "READY" if credential_ready and quota_ready else "NOT_READY",
        "pilot_products": len(queries),
        "credentials_present": credential_ready,
        "quota": quota_payload,
        "environment_enabled": os.environ.get(ENABLE_ENV) == "true",
        "live_execution_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or execute the controlled four-product eBay history pilot."
    )
    parser.add_argument("--quota-reserve", type=int, default=100)
    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--confirmation", default="")
    args = parser.parse_args()

    if args.quota_reserve < 0:
        raise SystemExit("--quota-reserve must be nonnegative")

    queries = pilot_queries()
    if len(queries) != 4:
        raise SystemExit(f"Expected four pilot queries; found {len(queries)}")

    report = readiness(queries, args.quota_reserve)
    if args.inspect:
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "READY" else 2

    if report["status"] != "READY":
        raise SystemExit("LIVE PILOT BLOCKED: readiness inspection did not pass.")
    if os.environ.get(ENABLE_ENV) != "true":
        raise SystemExit(f"LIVE PILOT BLOCKED: set {ENABLE_ENV}=true explicitly.")
    if args.confirmation != CONFIRMATION:
        raise SystemExit(
            f"LIVE PILOT BLOCKED: use --confirmation {CONFIRMATION}"
        )

    attempt_key = datetime.now(timezone.utc).strftime("attempt_%Y%m%dT%H%M%SZ")
    attempt_root = args.output_root.resolve() / "attempts" / attempt_key
    attempt_root.mkdir(parents=True, exist_ok=False)

    collector = LiveBrowseHistoryCollector(limit=args.limit_per_product)
    classified_rows: list[dict[str, Any]] = []
    product_rows: list[dict[str, Any]] = []

    for query in queries:
        classified, result = collect_live_product(query, collector)
        product_rows.append(serialize_product_result(result))
        for row in classified:
            classified_rows.append({
                "canonical_product_id": row.canonical_product_id,
                "item_id": row.item_id,
                "title": row.title,
                "price": row.price,
                "currency": row.currency,
                "accepted": str(row.accepted).lower(),
                "classification": row.classification,
                "rejection_reason": row.rejection_reason,
            })
        if result.coverage_state == "SOURCE_ERROR":
            break

    write_csv(
        attempt_root / "product_coverage.csv",
        product_rows,
        [
            "canonical_product_id",
            "canonical_product_name",
            "query",
            "queries_used",
            "results_found",
            "accepted_listing_count",
            "rejected_listing_count",
            "coverage_state",
            "source_error",
        ],
    )
    write_csv(
        attempt_root / "classified_listings.csv",
        classified_rows,
        [
            "canonical_product_id",
            "item_id",
            "title",
            "price",
            "currency",
            "accepted",
            "classification",
            "rejection_reason",
        ],
    )

    completed = sum(row["coverage_state"] != "SOURCE_ERROR" for row in product_rows)
    summary = {
        "status": "COMPLETE" if completed == len(queries) else "INCOMPLETE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "attempt_root": str(attempt_root),
        "pilot_products": len(queries),
        "processed_products": len(product_rows),
        "source_errors": sum(
            row["coverage_state"] == "SOURCE_ERROR" for row in product_rows
        ),
        "matched_products": sum(
            row["coverage_state"] == "MATCHED" for row in product_rows
        ),
        "accepted_listings": sum(
            int(row["accepted_listing_count"]) for row in product_rows
        ),
        "promotion_state": "PENDING_MANUAL_REVIEW",
        "live_execution_performed": True,
    }
    (attempt_root / "live_pilot_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "COMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
