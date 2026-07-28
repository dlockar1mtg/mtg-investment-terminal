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

from terminal2.market_sources.ebay_resilience import estimate_batch_calls
from terminal2.market_sources.ebay_resume import build_resume_plan

NORMALIZED_PLAN = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "normalized_queries/universal_mtg_ebay_normalized_query_plan.csv"
)
PREFLIGHT_BATCHES = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "preflight/universal_mtg_ebay_preflight_batches.csv"
)
EXECUTION_ROOT = (
    ROOT / "data/operations/mtg_ebay_history_accumulation/"
    "pilot_execution"
)
DEFAULT_BATCH_ID = "EBAY-HIST-001"
LIVE_ENABLE_ENV = "MTG_EBAY_HISTORY_LIVE_ENABLED"

MANIFEST_FIELDS = [
    "batch_id",
    "canonical_product_id",
    "canonical_product_name",
    "product_class",
    "normalized_ebay_query",
    "resume_state",
    "execution_action",
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


def select_batch(
    rows: list[dict[str, str]],
    batch_id: str,
) -> list[dict[str, str]]:
    selected = [
        row for row in rows
        if clean(row.get("batch_id")) == batch_id
    ]
    return sorted(
        selected,
        key=lambda row: int(clean(row.get("queue_rank")) or "0"),
    )


def preflight_record(
    rows: list[dict[str, str]],
    batch_id: str,
) -> dict[str, str] | None:
    return next(
        (
            row for row in rows
            if clean(row.get("batch_id")) == batch_id
        ),
        None,
    )


def build_execution_manifest(
    products: list[dict[str, str]],
    batch_root: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    expected_ids = [
        clean(row.get("canonical_product_id"))
        for row in products
    ]
    resume = build_resume_plan(batch_root, expected_ids)
    completed = set(resume.completed_product_ids)
    source_errors = set(resume.source_error_product_ids)

    detail: list[dict[str, Any]] = []
    for row in products:
        product_id = clean(row.get("canonical_product_id"))
        if product_id in completed:
            state = "COMPLETED"
            action = "SKIP_REUSE_COMPLETED"
        elif product_id in source_errors:
            state = "SOURCE_ERROR_RETRY"
            action = "DRY_RUN_RETRY"
        else:
            state = "PENDING"
            action = "DRY_RUN_COLLECT"

        detail.append({
            "batch_id": clean(row.get("batch_id")),
            "canonical_product_id": product_id,
            "canonical_product_name": clean(
                row.get("canonical_product_name")
            ),
            "product_class": clean(row.get("product_class")),
            "normalized_ebay_query": clean(
                row.get("normalized_ebay_query")
            ),
            "resume_state": state,
            "execution_action": action,
            "live_collection_allowed": "false",
        })

    pending = [
        row for row in detail
        if row["resume_state"] != "COMPLETED"
    ]
    summary = {
        "batch_id": clean(products[0].get("batch_id")) if products else "",
        "planned_products": len(products),
        "completed_products": len(completed),
        "source_error_products": len(source_errors),
        "pending_products": len(pending),
        "estimated_maximum_calls": estimate_batch_calls(len(pending)),
        "coverage_files_inspected": len(resume.coverage_files),
        "dry_run_mode": True,
        "live_collection_enabled": False,
        "certification_checks": {
            "pilot_contains_four_products": len(products) == 4,
            "product_ids_unique": len(set(expected_ids)) == len(expected_ids),
            "all_queries_present": all(
                clean(row.get("normalized_ebay_query"))
                for row in products
            ),
            "all_queries_approved": all(
                clean(row.get("query_review_status"))
                == "APPROVED_FOR_DRY_RUN"
                for row in products
            ),
            "all_products_pre_collector": all(
                clean(row.get("product_class"))
                == "PRE_COLLECTOR_BOOSTER_BOX"
                for row in products
            ),
            "live_collection_disabled_for_all": all(
                row["live_collection_allowed"] == "false"
                for row in detail
            ),
        },
    }
    summary["status"] = (
        "PASS"
        if all(summary["certification_checks"].values())
        else "FAIL"
    )
    return detail, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare the governed four-product eBay history pilot. "
            "Dry-run creates manifests only; live execution is fail-closed."
        )
    )
    parser.add_argument(
        "--normalized-plan",
        type=Path,
        default=NORMALIZED_PLAN,
    )
    parser.add_argument(
        "--preflight-batches",
        type=Path,
        default=PREFLIGHT_BATCHES,
    )
    parser.add_argument("--execution-root", type=Path, default=EXECUTION_ROOT)
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Required with --live, but Phase 11E.8.6 still blocks live calls.",
    )
    args = parser.parse_args()

    if args.live:
        if not args.confirm_live:
            raise SystemExit(
                "LIVE EXECUTION BLOCKED: --confirm-live was not provided."
            )
        if os.environ.get(LIVE_ENABLE_ENV) != "true":
            raise SystemExit(
                f"LIVE EXECUTION BLOCKED: set {LIVE_ENABLE_ENV}=true "
                "only after production certification."
            )
        raise SystemExit(
            "LIVE EXECUTION BLOCKED: Phase 11E.8.6 is harness-only. "
            "No live collector is connected."
        )

    plan_rows = read_csv(args.normalized_plan.resolve())
    products = select_batch(plan_rows, args.batch_id)
    if not products:
        raise SystemExit(f"No normalized products found for {args.batch_id}.")

    preflight_rows = read_csv(args.preflight_batches.resolve())
    preflight = preflight_record(preflight_rows, args.batch_id)
    if preflight is None:
        raise SystemExit(
            f"No certified preflight record found for {args.batch_id}."
        )
    if clean(preflight.get("dry_run_allowed")).lower() != "true":
        raise SystemExit(
            f"DRY RUN BLOCKED: preflight did not approve {args.batch_id}."
        )
    if clean(preflight.get("live_collection_allowed")).lower() != "false":
        raise SystemExit(
            "DRY RUN BLOCKED: preflight live-collection invariant failed."
        )

    execution_root = args.execution_root.resolve()
    batch_root = execution_root / args.batch_id
    detail, summary = build_execution_manifest(products, batch_root)

    attempt_key = datetime.now(timezone.utc).strftime(
        "attempt_%Y%m%dT%H%M%SZ"
    )
    attempt_root = batch_root / "attempts" / attempt_key
    attempt_root.mkdir(parents=True, exist_ok=False)

    summary.update({
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "DRY_RUN",
        "attempt_root": str(attempt_root),
        "preflight_dry_run_allowed": True,
        "preflight_live_collection_allowed": False,
    })

    write_csv(
        attempt_root / "pilot_execution_manifest.csv",
        detail,
        MANIFEST_FIELDS,
    )
    (
        attempt_root / "pilot_execution_summary.json"
    ).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    latest = batch_root / "latest_dry_run.json"
    batch_root.mkdir(parents=True, exist_ok=True)
    latest.write_text(
        json.dumps(
            {
                "attempt_root": str(attempt_root),
                "summary_file": str(
                    attempt_root / "pilot_execution_summary.json"
                ),
                "manifest_file": str(
                    attempt_root / "pilot_execution_manifest.csv"
                ),
            },
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
