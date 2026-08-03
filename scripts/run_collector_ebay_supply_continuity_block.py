"""Run Collector eBay full-universe continuity and shadow scarcity baseline."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_supply_continuity"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
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
    command = [sys.executable, "scripts/build_collector_ebay_supply_continuity.py"]
    if args.strict:
        command.append("--strict")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    result = read_json(OUT / "collector_ebay_supply_continuity_summary.json")
    passed = completed.returncode == 0 and str(result.get("status", "")).startswith("PASS_")
    trend_available = bool(result.get("trend_features_available", False))

    summary = {
        "block_name": "Collector eBay Supply Continuity and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"command": command, "return_code": completed.returncode, "passed": passed}],
        "offline_only": True,
        "quota_calls": 0,
        "continuity_baseline_passed": passed,
        "governed_products": result.get("governed_products", 0),
        "full_universe_snapshot_rows": result.get("full_universe_snapshot_rows", 0),
        "products_with_observed_accepted_supply": result.get("products_with_observed_accepted_supply", 0),
        "products_with_zero_accepted_listings": result.get("products_with_zero_accepted_listings", 0),
        "products_missing_query_completion_evidence": result.get("products_missing_query_completion_evidence", 0),
        "certified_snapshot_days": result.get("certified_snapshot_days", 0),
        "trend_features_available": trend_available,
        "completed": [
            "Identity-complete certified Collector eBay daily ledger",
            "Full governed-universe daily supply coverage",
            "Explicit zero-accepted-listing observations separated from missing query evidence",
            "Listing continuity history initialized with first-seen and last-seen fields",
            "Static scarcity baseline features written in shadow mode",
        ] if passed else [
            "Identity-complete certified Collector eBay daily ledger",
        ],
        "currently_being_worked_on": [
            "Accumulate additional certified daily snapshots for entry, exit, relist, trend, and turnover features"
            if passed and not trend_available
            else "Validate multi-day continuity and Supply Scarcity Index v1 components"
            if passed
            else "Resolve full-universe coverage or continuity integrity failures"
        ],
        "still_outstanding": [
            "Run future daily eBay acquisition through precision-v3-universal",
            "Append each certified day to the immutable listing history",
            "Confirm listing exits only after a later completed query no longer returns the item",
            "Detect relists without conflating seller changes or new item IDs",
            "Accumulate enough certified days for supply trend and turnover features",
            "Complete and validate Supply Scarcity Index v1",
            "Certify feature freshness, missingness, and point-in-time leakage controls",
            "Run governed historical validation and shadow forecast experiments",
            "Approve purchase recommendations only after forecast governance gates pass",
            "Export approved Collector outputs to UIP",
        ],
        "known_blockers": (
            ["Only one certified marketplace-supply day exists; trend and turnover components remain unavailable"]
            if passed and not trend_available
            else ["No continuity blocker; multi-day feature validation remains outstanding"]
            if passed
            else ["Full-universe continuity baseline did not pass; inspect missing query evidence or identity integrity"]
        ),
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "official_release_dates": "COMPLETE",
            "tcgcsv_current_price": "COMPLETE",
            "safe_historical_foundation": "COMPLETE",
            "released_product_mtgjson_structure": "COMPLETE",
            "packaging_normalization": "COMPLETE",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL",
            "daily_listing_ledger": "CERTIFIED_IDENTITY_COMPLETE",
            "full_universe_supply_snapshot": "CERTIFIED" if passed else "REVIEW_REQUIRED",
            "listing_continuity": "BASELINE_INITIALIZED" if passed else "NOT_INITIALIZED",
            "supply_history": "ONE_CERTIFIED_DAY" if passed and not trend_available else "MULTI_DAY_AVAILABLE" if passed else "NOT_ACCUMULATED",
            "static_scarcity_baseline": "SHADOW_AVAILABLE" if passed else "NOT_AVAILABLE",
            "supply_scarcity_index_v1": "BLOCKED_BY_INSUFFICIENT_DAYS" if passed and not trend_available else "SHADOW_VALIDATION_REQUIRED" if passed else "NOT_BUILT",
            "feature_certification": "NOT_STARTED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Run the next certified daily collection, append continuity history, and activate trend/turnover calculations"
            if passed and not trend_available
            else "Validate Supply Scarcity Index v1 and certify the marketplace-supply feature layer"
            if passed
            else "Resolve continuity baseline failures and rerun strict certification"
        ),
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_SUPPLY_CONTINUITY_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_ebay_supply_continuity_project_control_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
