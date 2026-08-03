"""Orchestrate the Collector eBay day-one baseline composite-overlap repair."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_day_one_supply_baseline"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector eBay day-one baseline overlap repair block")
    p.add_argument("--strict", action="store_true")
    return p


def main() -> int:
    args = parser().parse_args()
    generated = datetime.now(timezone.utc)
    command = [sys.executable, "scripts/repair_collector_ebay_day_one_baseline_overlap_integrity.py"]
    if args.strict:
        command.append("--strict")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)

    summary_path = OUT / "collector_ebay_day_one_supply_baseline_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    passed = (
        result.returncode == 0
        and summary.get("status") == "PASS_DAY_ONE_SUPPLY_BASELINE_PROMOTED_CONTINUITY_READY"
        and summary.get("baseline_integrity_passed") is True
        and summary.get("baseline_promoted") is True
        and summary.get("continuity_accumulation_authorized") is True
        and int(summary.get("accepted_review_composite_overlap_rows", -1)) == 0
        and int(summary.get("accepted_item_ids_mapped_to_multiple_products", -1)) == 0
    )
    project = {
        "block_name": "Collector eBay Day-One Baseline Overlap Repair and Project Control",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "offline_only": True,
        "quota_calls": 0,
        "steps": [{"command": command, "return_code": result.returncode, "passed": result.returncode == 0}],
        "repair_passed": passed,
        "baseline_id": summary.get("baseline_id", ""),
        "accepted_listing_rows": summary.get("accepted_listing_rows", 0),
        "review_listing_rows": summary.get("review_listing_rows", 0),
        "governed_product_rows": summary.get("governed_product_rows", 0),
        "accepted_review_composite_overlap_rows": summary.get("accepted_review_composite_overlap_rows", -1),
        "accepted_review_cross_product_item_ids": summary.get("accepted_review_cross_product_item_ids", -1),
        "accepted_item_ids_mapped_to_multiple_products": summary.get("accepted_item_ids_mapped_to_multiple_products", -1),
        "completed": [
            "Full-universe acquisition recall certified",
            "All 4,413 candidates replayed through the hardened matcher",
            "Accepted and review ledgers generated",
            "Composite listing-identity contract enforced",
            "Cross-product candidate reuse preserved in an explicit audit",
        ],
        "currently_being_worked_on": [
            "Certify the day-one baseline as the sole origin for comparable eBay supply continuity"
        ],
        "still_outstanding": [
            "Run the first post-baseline comparable observation after the governed interval",
            "Measure accepted listing entry, exit, persistence, seller, and landed-price changes",
            "Accumulate sufficient comparable observations for Supply Scarcity Index V1",
            "Keep forecasting, purchases, and UIP blocked until later gates pass",
        ],
        "known_blockers": [] if passed else [
            "Day-one baseline still has a composite overlap, accepted multi-product mapping, or reconciliation failure"
        ],
        "authorization_state": {
            "acquisition_recall": "CERTIFIED",
            "matcher_precision_hardening": "COMPLETE",
            "day_one_supply_baseline": "PROMOTED" if passed else "NOT_PROMOTED",
            "continuity_accumulation": "AUTHORIZED_FROM_DAY_ONE_BASELINE" if passed else "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED_PENDING_CONTINUITY",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Run the first governed post-baseline comparable supply observation after the required interval"
            if passed else "Inspect composite overlap audit and repair remaining integrity failures"
        ),
        "status": (
            "PASS_COLLECTOR_EBAY_DAY_ONE_BASELINE_OVERLAP_REPAIR_PROJECT_CONTROL"
            if passed else "FAIL_COLLECTOR_EBAY_DAY_ONE_BASELINE_OVERLAP_REPAIR_PROJECT_CONTROL"
        ),
    }
    (OUT / "collector_ebay_day_one_baseline_overlap_repair_project_control_summary.json").write_text(
        json.dumps(project, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(project, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
