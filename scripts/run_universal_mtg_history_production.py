from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from terminal2.market_sources.ebay_history_live import (
    LiveBrowseHistoryCollector,
    build_live_query_ladder,
    collect_live_product,
    credentials_present,
    inspect_quota,
)
from terminal2.market_sources.ebay_history_pipeline import HistoryQuery
from terminal2.market_sources.ebay_resilience import estimate_batch_calls

PLAN = ROOT / "data/operations/mtg_ebay_history_accumulation/normalized_queries/universal_mtg_ebay_normalized_query_plan.csv"
LEDGER_ROOT = ROOT / "data/operations/mtg_universal_history_ledger"
OUTPUT = ROOT / "data/operations/mtg_universal_history_production"
ENABLE_ENV = "MTG_EBAY_HISTORY_LIVE_ENABLED"
CONFIRMATION = "EXECUTE-UNIVERSAL-MTG-PRODUCTION"

COVERAGE_FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "batch_id", "query_count", "results_found", "accepted_listing_count",
    "rejected_listing_count", "coverage_state", "source_error",
    "observed_at_utc",
]
LISTING_FIELDS = [
    "canonical_product_id", "canonical_product_name", "product_class",
    "batch_id", "item_id", "title", "price", "currency", "accepted",
    "classification", "rejection_reason", "observed_at_utc",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def append_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def load_queries() -> list[tuple[HistoryQuery, str]]:
    rows = read_csv(PLAN)
    queries: list[tuple[HistoryQuery, str]] = []
    for row in rows:
        if row.get("query_review_status") != "APPROVED_FOR_DRY_RUN":
            continue
        queries.append((
            HistoryQuery(
                canonical_product_id=row["canonical_product_id"],
                canonical_product_name=row["canonical_product_name"],
                product_class=row["product_class"],
                query=row["normalized_ebay_query"],
            ),
            row["batch_id"],
        ))
    if len(queries) != 152:
        raise SystemExit(f"Expected 152 approved eBay-route products; found {len(queries)}")
    return queries


def latest_attempt_root(base: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("attempt_%Y%m%dT%H%M%SZ")
    return base / "current_market" / "attempts" / stamp


def production_readiness(product_count: int, reserve: int) -> dict[str, Any]:
    credentials = credentials_present()
    required = estimate_batch_calls(product_count, maximum_queries_per_product=3)
    payload: dict[str, Any] = {
        "status": "NOT_READY",
        "products": product_count,
        "required_calls": required,
        "reserve_calls": reserve,
        "credentials_present": credentials,
        "environment_enabled": os.environ.get(ENABLE_ENV) == "true",
        "live_execution_performed": False,
    }
    if not credentials:
        payload["error"] = "eBay credentials unavailable"
        return payload
    try:
        quota = inspect_quota()
        supported = quota.supports(required, reserve_calls=reserve)
        payload["quota"] = {
            "limit": quota.limit, "used": quota.count,
            "remaining": quota.remaining, "reset": quota.reset,
            "supported": supported,
        }
        payload["status"] = "READY" if supported else "NOT_READY"
    except Exception as exc:
        payload["error"] = f"{type(exc).__name__}: {exc}"
    return payload


def rebuild_history_ledger() -> dict[str, Any]:
    import subprocess
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_universal_mtg_history_ledger.py")],
        cwd=ROOT, text=True, capture_output=True,
    )
    return {
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def build_universal_coverage(
    current_rows: list[dict[str, str]],
    output_root: Path,
) -> dict[str, Any]:
    history_status = read_csv(LEDGER_ROOT / "universal_mtg_history_completion_status.csv")
    current_by_id = {row["canonical_product_id"]: row for row in current_rows}
    output: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for row in history_status:
        product_id = row["canonical_product_id"]
        current = current_by_id.get(product_id)
        has_history = int(row.get("distinct_history_dates") or 0) > 0
        current_state = current.get("coverage_state", "") if current else ""
        has_current = current_state == "MATCHED"

        if has_history and has_current:
            state = "HISTORY_AND_CURRENT_MARKET"
        elif has_history:
            state = "DIRECT_HISTORY_AVAILABLE"
        elif has_current:
            state = "CURRENT_MARKET_ONLY"
        elif current_state == "SOURCE_ERROR":
            state = "SOURCE_ERROR"
        elif row.get("history_completion_route") == "IDENTITY_REVIEW_REQUIRED":
            state = "IDENTITY_REVIEW_REQUIRED"
        else:
            state = "HISTORY_UNAVAILABLE"

        counts[state] += 1
        output.append({
            "canonical_product_id": product_id,
            "canonical_product_name": row.get("canonical_product_name", ""),
            "product_class": row.get("product_class", ""),
            "distinct_history_dates": row.get("distinct_history_dates", "0"),
            "first_history_date": row.get("first_history_date", ""),
            "latest_history_date": row.get("latest_history_date", ""),
            "history_sources": row.get("history_sources", ""),
            "current_market_state": current_state or "NOT_ROUTED_TO_EBAY",
            "current_results_found": current.get("results_found", "0") if current else "0",
            "current_accepted_listings": current.get("accepted_listing_count", "0") if current else "0",
            "universal_coverage_state": state,
        })

    write_csv(
        output_root / "universal_mtg_product_coverage.csv",
        output,
        list(output[0].keys()),
    )
    unresolved = [
        row for row in output
        if row["universal_coverage_state"] in {
            "HISTORY_UNAVAILABLE", "SOURCE_ERROR", "IDENTITY_REVIEW_REQUIRED"
        }
    ]
    write_csv(
        output_root / "universal_mtg_unresolved_history_gaps.csv",
        unresolved,
        list(output[0].keys()),
    )
    return {"governed_products": len(output), "coverage_counts": dict(counts), "unresolved": len(unresolved)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the complete universal MTG history/current-market production cycle.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--quota-reserve", type=int, default=250)
    parser.add_argument("--limit-per-product", type=int, default=20)
    parser.add_argument("--output-root", type=Path, default=OUTPUT)
    parser.add_argument("--resume-attempt", type=Path)
    args = parser.parse_args()

    queries = load_queries()
    readiness = production_readiness(len(queries), args.quota_reserve)
    if args.inspect:
        print(json.dumps(readiness, indent=2))
        return 0 if readiness["status"] == "READY" else 2

    if readiness["status"] != "READY":
        raise SystemExit("PRODUCTION BLOCKED: readiness inspection failed")
    if os.environ.get(ENABLE_ENV) != "true":
        raise SystemExit(f"PRODUCTION BLOCKED: set {ENABLE_ENV}=true")
    if args.confirmation != CONFIRMATION:
        raise SystemExit(f"PRODUCTION BLOCKED: use --confirmation {CONFIRMATION}")

    output_root = args.output_root.resolve()
    attempt_root = args.resume_attempt.resolve() if args.resume_attempt else latest_attempt_root(output_root)
    attempt_root.mkdir(parents=True, exist_ok=True)
    coverage_path = attempt_root / "current_market_product_coverage.csv"
    listing_path = attempt_root / "current_market_listings.csv"

    existing = read_csv(coverage_path)
    completed_ids = {
        row["canonical_product_id"] for row in existing
        if row.get("coverage_state") != "SOURCE_ERROR"
    }
    collector = LiveBrowseHistoryCollector(limit=args.limit_per_product)
    observed = datetime.now(timezone.utc).isoformat()

    for index, (query, batch_id) in enumerate(queries, start=1):
        if query.canonical_product_id in completed_ids:
            continue
        classified, result = collect_live_product(query, collector)
        coverage_row = {
            "canonical_product_id": query.canonical_product_id,
            "canonical_product_name": query.canonical_product_name,
            "product_class": query.product_class,
            "batch_id": batch_id,
            "query_count": len(build_live_query_ladder(query)),
            "results_found": result.results_found,
            "accepted_listing_count": result.accepted_listing_count,
            "rejected_listing_count": result.rejected_listing_count,
            "coverage_state": result.coverage_state,
            "source_error": result.source_error,
            "observed_at_utc": observed,
        }
        listing_rows = [{
            "canonical_product_id": query.canonical_product_id,
            "canonical_product_name": query.canonical_product_name,
            "product_class": query.product_class,
            "batch_id": batch_id,
            "item_id": row.item_id,
            "title": row.title,
            "price": row.price,
            "currency": row.currency,
            "accepted": str(row.accepted).lower(),
            "classification": row.classification,
            "rejection_reason": row.rejection_reason,
            "observed_at_utc": observed,
        } for row in classified]
        append_csv(coverage_path, [coverage_row], COVERAGE_FIELDS)
        append_csv(listing_path, listing_rows, LISTING_FIELDS)
        print(f"[{index}/152] {query.canonical_product_name}: {result.coverage_state} ({result.accepted_listing_count} accepted)")
        if result.coverage_state == "SOURCE_ERROR":
            break

    current_rows = read_csv(coverage_path)
    ledger_result = rebuild_history_ledger()
    coverage_summary = build_universal_coverage(current_rows, output_root)

    states = Counter(row["coverage_state"] for row in current_rows)
    summary = {
        "status": "PASS" if len(current_rows) == 152 and states.get("SOURCE_ERROR", 0) == 0 and ledger_result["returncode"] == 0 else "INCOMPLETE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "attempt_root": str(attempt_root),
        "routed_products": 152,
        "processed_products": len(current_rows),
        "current_market_state_counts": dict(states),
        "accepted_listings": sum(int(row.get("accepted_listing_count") or 0) for row in current_rows),
        "history_ledger_rebuild": ledger_result,
        "universal_coverage": coverage_summary,
        "live_execution_performed": True,
        "promotion_state": "CURRENT_MARKET_SNAPSHOT_CERTIFIED_NOT_SOLD_HISTORY",
    }
    (output_root / "universal_mtg_production_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (attempt_root / "attempt_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
