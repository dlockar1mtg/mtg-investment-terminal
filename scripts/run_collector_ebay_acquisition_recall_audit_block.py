"""Run offline Collector eBay acquisition-recall audit and project control."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_acquisition_recall"
SUMMARY = OUT / "collector_ebay_acquisition_recall_summary.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector eBay acquisition recall audit")
    p.add_argument("--strict", action="store_true")
    return p


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def main() -> int:
    args = parser().parse_args()
    command = [sys.executable, "scripts/audit_collector_ebay_acquisition_recall.py"]
    if args.strict:
        command.append("--strict")
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing if existing else "")
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    audit = read_json(SUMMARY)
    passed = completed.returncode == 0 and str(audit.get("status", "")).startswith("PASS_")
    gap_products = int(audit.get("products_with_historical_only_item_ids", 0) or 0)
    zero_with_history = int(audit.get("current_zero_products_with_historical_evidence", 0) or 0)
    canaries = int(audit.get("canary_products", 0) or 0)

    project = {
        "block_name": "Collector eBay Acquisition Recall Audit and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"command": command, "return_code": completed.returncode, "passed": passed}],
        "offline_only": True,
        "quota_calls": 0,
        "audit_passed": passed,
        "governed_products": audit.get("governed_products", 0),
        "current_sample_unique_item_ids": audit.get("current_sample_unique_item_ids", 0),
        "historical_evidence_files_read": audit.get("historical_evidence_files_read", 0),
        "historical_unique_item_ids": audit.get("historical_unique_item_ids", 0),
        "products_with_historical_only_item_ids": gap_products,
        "current_zero_products_with_historical_evidence": zero_with_history,
        "multi_query_contract_rows": audit.get("multi_query_contract_rows", 0),
        "canary_products": canaries,
        "completed": [
            "Governed 50-product Collector universe and source authority",
            "precision-v3-universal matching authority",
            "Current eBay matching-validation sample preserved",
            "Prior local eBay evidence inventory and offline recall comparison",
            "Candidate multi-query recall contracts generated",
            "Representative high-recall canary plan generated",
        ] if passed else [
            "Governed Collector universe and production matching authority preserved",
        ],
        "currently_being_worked_on": [
            "Review offline recall gaps and run only the governed high-recall canary products"
            if passed else "Resolve acquisition-recall audit startup or input failures"
        ],
        "still_outstanding": [
            "Review historical-only item and title evidence by product",
            "Review and refine candidate multi-query contracts",
            "Run representative live high-recall canaries with full pagination",
            "Deduplicate candidates across query variants before production matching",
            "Measure incremental candidates and accepted listings by query variant",
            "Certify result ceilings, pagination completion, and query failures",
            "Promote recall-certified query contracts only after canary review",
            "Run the first recall-certified 50-product collection",
            "Archive the existing August 1 sample as matching-validation evidence",
            "Initialize the true marketplace-supply continuity baseline",
            "Accumulate comparable certified days before trend or scarcity features",
            "Resume forecasting, purchases, and UIP delivery only after later gates pass",
        ],
        "known_blockers": (
            [f"Acquisition recall is not certified; {gap_products} products contain historical-only item evidence and {zero_with_history} current-zero products have prior evidence"]
            if passed else ["Acquisition recall audit did not pass"]
        ),
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "official_release_dates": "COMPLETE",
            "tcgcsv_pricing_and_history": "COMPLETE",
            "mtgjson_structure": "COMPLETE_FOR_RELEASED_PRODUCTS",
            "packaging_normalization": "COMPLETE",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL",
            "ebay_matching_precision": "VALIDATED",
            "ebay_acquisition_mechanics": "FUNCTIONAL",
            "ebay_acquisition_recall": "NOT_CERTIFIED",
            "current_147_listing_pull": "MATCHING_VALIDATION_SAMPLE",
            "current_125_row_ledger": "SAMPLE_ONLY_NOT_RECALL_COMPLETE",
            "current_50_product_supply_snapshot": "COMPLETE_SUPPLY_CLAIM_REVOKED",
            "current_continuity_baseline": "MECHANICAL_TEST_ONLY",
            "multi_query_recall_contracts": "CANDIDATE_OFFLINE",
            "live_high_recall_canary": "READY" if passed and canaries > 0 else "BLOCKED",
            "supply_scarcity_index_v1": "BLOCKED_BY_ACQUISITION_RECALL",
            "feature_certification": "BLOCKED_BY_ACQUISITION_RECALL",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Review the offline recall evidence and execute the governed high-recall canary only; do not run the full daily cycle"
            if passed else "Resolve audit failures and rerun the strict offline acquisition-recall audit"
        ),
        "acquisition_recall_certified": False,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_ACQUISITION_RECALL_AUDIT_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_ebay_acquisition_recall_project_control_summary.json").write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(project, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
