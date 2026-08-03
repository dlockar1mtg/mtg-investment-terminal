"""Orchestrate historical Collector eBay reconstruction and valid offline recall comparison."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECON_SUMMARY = ROOT / "data/governance/permanence/certification/collector_ebay_historical_reconstruction/collector_ebay_historical_reconstruction_summary.json"
RECALL_SUMMARY = ROOT / "data/governance/permanence/certification/collector_ebay_reconstructed_recall/collector_ebay_reconstructed_recall_summary.json"
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_reconstructed_recall"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector historical reconstruction and recall validation")
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


def run(command: list[str], env: dict[str, str]) -> dict[str, object]:
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    return {"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0}


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    commands = [
        [sys.executable, "scripts/reconstruct_collector_ebay_historical_evidence.py", "--strict"],
        [sys.executable, "scripts/validate_collector_ebay_recall_from_reconstructed_history.py", "--strict"],
    ]
    steps = []
    for command in commands:
        result = run(command, env)
        steps.append(result)
        if not result["passed"]:
            break
    recon = read_json(RECON_SUMMARY)
    recall = read_json(RECALL_SUMMARY)
    passed = len(steps) == 2 and all(bool(step["passed"]) for step in steps)
    payload = {
        "block_name": "Collector eBay Historical Reconstruction and Valid Recall Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "offline_only": True,
        "quota_calls": 0,
        "reconstruction_passed": bool(recon.get("historical_product_linkage_reconstructed", False)),
        "reconstructed_rows": recon.get("reconstructed_rows", 0),
        "reconstructed_unique_item_ids": recon.get("reconstructed_unique_item_ids", 0),
        "reconstructed_governed_products": recon.get("reconstructed_governed_products", 0),
        "valid_recall_comparison_passed": bool(recall.get("historical_recall_comparison_valid", False)),
        "products_with_historical_only_item_ids": recall.get("products_with_historical_only_item_ids", 0),
        "current_zero_products_with_historical_evidence": recall.get("current_zero_products_with_historical_evidence", 0),
        "valid_canary_products": recall.get("valid_canary_products", 0),
        "completed": [
            "Historical eBay result schemas profiled",
            "canonical_product_name mapped to governed Collector authority",
            "Historical listing evidence reconstructed with provenance",
            "Valid offline current-versus-historical recall comparison produced",
        ],
        "currently_being_worked_on": [
            "Review reconstructed recall gaps and the evidence-based live canary plan"
        ],
        "still_outstanding": [
            "Review historical-only listings and query patterns by product",
            "Execute only the evidence-based high-recall canary products",
            "Certify pagination completion, result ceilings, and query failures",
            "Measure incremental candidates and production-accepted listings by query variant",
            "Promote governed multi-query contracts after canary review",
            "Run the first recall-certified 50-product acquisition",
            "Initialize the true marketplace-supply baseline",
            "Resume continuity, scarcity, forecasting, purchasing, and UIP only after later gates pass",
        ],
        "known_blockers": [
            "Acquisition recall remains uncertified until live high-recall canaries validate the reconstructed query gaps"
        ],
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL",
            "historical_schema_recovery": "COMPLETE",
            "historical_product_linkage": "RECONSTRUCTED" if recon.get("historical_product_linkage_reconstructed") else "FAILED",
            "offline_recall_comparison": "VALID" if recall.get("historical_recall_comparison_valid") else "INVALID",
            "live_high_recall_canary": "AUTHORIZED_LIMITED" if recall.get("live_canary_authorized") else "BLOCKED",
            "acquisition_recall": "NOT_CERTIFIED",
            "current_supply_baseline": "NOT_AUTHORIZED",
            "continuity_accumulation": "NOT_AUTHORIZED",
            "supply_scarcity_index_v1": "BLOCKED",
            "feature_certification": "BLOCKED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": "Review reconstructed historical-only evidence, then run only the evidence-based high-recall canary products",
        "live_canary_authorized": bool(recall.get("live_canary_authorized", False)),
        "continuity_accumulation_authorized": False,
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_RECONSTRUCTED_RECALL_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    path = OUT / "collector_ebay_reconstructed_recall_project_control_summary.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
