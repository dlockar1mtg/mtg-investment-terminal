"""Run historical eBay schema recovery and write project control.

Offline-only. This block prevents live canary execution until historical product
linkage is reconstructed and the offline recall comparison becomes valid.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_historical_schema_recovery"
SUMMARY = OUT / "collector_ebay_historical_schema_recovery_summary.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector eBay historical schema recovery")
    p.add_argument("--strict", action="store_true")
    return p


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "scripts/profile_collector_ebay_historical_schemas.py", "--strict"]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    profile = read_json(SUMMARY)
    passed = completed.returncode == 0 and str(profile.get("status", "")).startswith("PASS_")

    control = {
        "block_name": "Collector eBay Historical Schema Recovery and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}],
        "offline_only": True,
        "quota_calls": 0,
        "schema_profile_passed": passed,
        "historical_result_files_discovered": profile.get("historical_result_files_discovered", 0),
        "historical_result_files_read": profile.get("historical_result_files_read", 0),
        "distinct_schema_signatures": profile.get("distinct_schema_signatures", 0),
        "reconstruction_strategy_counts": profile.get("reconstruction_strategy_counts", {}),
        "completed": [
            "Governed Collector universe and precision-v3-universal matching authority",
            "Current 147-listing matching-validation sample preserved",
            "Initial offline recall audit limitations identified",
            "Historical result schema and column profiling implemented",
        ],
        "currently_being_worked_on": [
            "Recover governed product linkage for historical eBay result rows"
        ],
        "still_outstanding": [
            "Review historical schema signatures and product-linkage candidates",
            "Map direct TCGplayer IDs where present",
            "Map canonical or matched product names to governed authority",
            "Use sibling coverage and batch metadata where direct identity is absent",
            "Replay titles through production identity only where necessary",
            "Rebuild historical listing evidence with provenance and mapping confidence",
            "Rerun the offline acquisition recall comparison",
            "Select live high-recall canaries only after offline evidence is valid",
            "Certify multi-query pagination and result ceilings",
            "Create the true recall-certified day-one marketplace baseline",
            "Resume continuity, scarcity, forecasting, purchasing, and UIP only after later gates pass",
        ],
        "known_blockers": [
            "Most historical listing files lack the product-ID column expected by the first audit; their rows are not yet linked to governed products"
        ],
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL",
            "ebay_matching_precision": "VALIDATED",
            "historical_schema_recovery": "PROFILED" if passed else "REVIEW_REQUIRED",
            "historical_product_linkage": "NOT_RECONSTRUCTED",
            "offline_recall_comparison": "INVALID_PENDING_LINKAGE_RECOVERY",
            "multi_query_recall_contracts": "CANDIDATE_ONLY",
            "live_high_recall_canary": "BLOCKED_PENDING_VALID_OFFLINE_AUDIT",
            "current_147_listing_pull": "MATCHING_VALIDATION_SAMPLE",
            "current_supply_baseline": "NOT_AUTHORIZED",
            "continuity_accumulation": "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": "Use the schema profile to reconstruct historical governed-product linkage and rerun the offline recall audit",
        "live_canary_authorized": False,
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_HISTORICAL_SCHEMA_RECOVERY_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    path = OUT / "collector_ebay_historical_schema_recovery_project_control_summary.json"
    path.write_text(json.dumps(control, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(control, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
