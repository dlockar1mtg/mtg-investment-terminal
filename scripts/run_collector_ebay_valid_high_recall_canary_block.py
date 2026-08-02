"""Orchestrate the limited live Collector eBay high-recall canary."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_valid_high_recall_canary"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run governed Collector eBay high-recall canary block")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--limit-per-product", type=int, default=200)
    return p


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc)
    command = [sys.executable, "scripts/run_collector_ebay_valid_high_recall_canary.py", "--limit-per-product", str(args.limit_per_product)]
    if args.strict:
        command.append("--strict")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)

    summary_path = OUT / "collector_ebay_valid_high_recall_canary_summary.json"
    canary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
    passed = result.returncode == 0 and canary.get("status") == "PASS_LIMITED_HIGH_RECALL_CANARY_REVIEW_REQUIRED"
    project = {
        "block_name": "Collector eBay Valid High-Recall Canary and Project Control",
        "block_version": "1.0.0",
        "generated_at": generated.isoformat(),
        "steps": [{"command": command, "return_code": result.returncode, "passed": result.returncode == 0}],
        "canary_passed": passed,
        "canary_products": canary.get("canary_products", 0),
        "queries_used": canary.get("queries_used", 0),
        "candidate_listing_rows": canary.get("candidate_listing_rows", 0),
        "accepted_rows": canary.get("accepted_rows", 0),
        "review_rows": canary.get("review_rows", 0),
        "rejected_rows": canary.get("rejected_rows", 0),
        "products_with_candidate_recall_improvement": canary.get("products_with_candidate_recall_improvement", 0),
        "total_incremental_candidates_vs_current": canary.get("total_incremental_candidates_vs_current", 0),
        "completed": [
            "Historical Collector eBay evidence reconstructed across 49 governed products",
            "Valid offline recall comparison completed",
            "Six-product evidence-based canary plan authorized",
            "Existing targeted acquisition and precision-v3-universal pipeline reused",
        ],
        "currently_being_worked_on": ["Review candidate-recall improvement and production match outcomes from the limited live canary"],
        "still_outstanding": [
            "Review canary product and listing-level outputs",
            "Resolve any source errors or manual-review rows",
            "Evaluate query-ladder incremental yield and historical pattern recovery",
            "Promote governed acquisition contracts only after canary review",
            "Run the first recall-certified 50-product acquisition",
            "Initialize the true marketplace-supply baseline",
            "Resume continuity, scarcity, forecasting, purchasing, and UIP only after later gates pass",
        ],
        "known_blockers": [] if passed else ["Limited live canary did not pass; inspect credentials, source errors, and output artifacts"],
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL",
            "historical_product_linkage": "RECONSTRUCTED",
            "offline_recall_comparison": "VALID",
            "live_high_recall_canary": "COMPLETE_REVIEW_REQUIRED" if passed else "FAILED_OR_NOT_RUN",
            "acquisition_recall": "NOT_CERTIFIED",
            "full_universe_collection": "REVIEW_CANARY_BEFORE_AUTHORIZATION",
            "current_supply_baseline": "NOT_AUTHORIZED",
            "continuity_accumulation": "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": "Review canary recall gains and matcher outcomes, then either refine query contracts or authorize one recall-certified 50-product acquisition",
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_VALID_HIGH_RECALL_CANARY_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    (OUT / "collector_ebay_valid_high_recall_canary_project_control_summary.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(project, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
