"""Orchestrate the governed Collector eBay full-universe acquisition certification."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_full_universe_acquisition"
SUMMARY = OUT / "collector_ebay_full_universe_acquisition_summary.json"
CONTROL = OUT / "collector_ebay_full_universe_acquisition_project_control_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--limit-per-product", type=int, default=200)
    args = parser.parse_args()

    command = [
        sys.executable,
        "scripts/run_collector_ebay_full_universe_acquisition_certification.py",
        "--limit-per-product",
        str(args.limit_per_product),
    ]
    if args.strict:
        command.append("--strict")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.is_file() else {}
    certified = result.returncode == 0 and bool(summary.get("acquisition_recall_certified"))

    control = {
        "block_name": "Collector eBay Full-Universe Acquisition Certification and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"command": command, "return_code": result.returncode, "passed": result.returncode == 0}],
        "live_collection_executed": bool(summary.get("live_collection_executed")),
        "governed_products": summary.get("governed_products", 0),
        "coverage_rows": summary.get("coverage_rows", 0),
        "raw_listing_rows": summary.get("raw_listing_rows", 0),
        "deduplicated_listing_rows": summary.get("deduplicated_listing_rows", 0),
        "accepted_rows": summary.get("accepted_rows", 0),
        "review_rows": summary.get("review_rows", 0),
        "rejected_rows": summary.get("rejected_rows", 0),
        "source_errors": summary.get("source_errors", -1),
        "candidate_ceiling_products": summary.get("candidate_ceiling_products", []),
        "acquisition_recall_certified": certified,
        "completed": [
            "601-row hardened matcher replay certified",
            "One governed 50-product live acquisition authorized",
            "Existing targeted query ladder and precision-v3-universal matcher reused",
            "Product-level coverage, deduplication, ceiling, and matcher evidence captured",
        ],
        "currently_being_worked_on": [
            "Certify whether the 50-product acquisition is structurally complete and free of candidate ceilings"
        ],
        "still_outstanding": [
            "Review any source errors, missing product coverage, candidate ceilings, or manual-review rows",
            "Promote the successful acquisition into the true day-one marketplace-supply baseline",
            "Start comparable continuity only after baseline promotion",
            "Build scarcity, forecasting, purchasing, and UIP outputs only after later gates pass",
        ],
        "known_blockers": [] if certified else [
            "Full-universe acquisition did not certify; inspect source errors, coverage gaps, or candidate ceilings"
        ],
        "authorization_state": {
            "matcher_precision_hardening": "COMPLETE",
            "full_universe_acquisition": "CERTIFIED" if certified else "REVIEW_REQUIRED",
            "current_supply_baseline": "AUTHORIZED_FOR_PROMOTION" if certified else "NOT_AUTHORIZED",
            "continuity_accumulation": "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Promote this certified acquisition into the true day-one supply baseline"
            if certified
            else "Resolve acquisition coverage gaps or candidate ceilings, then rerun certification"
        ),
        "status": (
            "PASS_COLLECTOR_EBAY_FULL_UNIVERSE_ACQUISITION_PROJECT_CONTROL"
            if certified
            else "REVIEW_COLLECTOR_EBAY_FULL_UNIVERSE_ACQUISITION_PROJECT_CONTROL"
        ),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    CONTROL.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(control, indent=2))
    return 0 if certified else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
