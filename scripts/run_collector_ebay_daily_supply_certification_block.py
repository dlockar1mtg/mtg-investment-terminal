"""Run Collector eBay downgrade adjudication and daily supply certification."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_daily_supply"


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
    command = [sys.executable, "scripts/certify_collector_ebay_daily_supply.py"]
    if args.strict:
        command.append("--strict")
    env = os.environ.copy()
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(ROOT) if not current else f"{ROOT}{os.pathsep}{current}"
    completed = subprocess.run(command, cwd=ROOT, env=env, check=False)
    result = read_json(OUT / "collector_ebay_daily_supply_summary.json")
    passed = completed.returncode == 0 and str(result.get("status", "")).startswith("PASS_")
    unresolved = int(result.get("downgrades_unresolved", 0) or 0)

    summary = {
        "block_name": "Collector eBay Daily Supply Certification and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"command": command, "return_code": completed.returncode, "passed": passed}],
        "offline_only": True,
        "quota_calls": 0,
        "certification_passed": passed,
        "production_matcher_version": result.get("production_matcher_version", ""),
        "accepted_listing_rows_certified": result.get("accepted_listing_rows_certified", 0),
        "rejected_listing_rows_excluded": result.get("rejected_listing_rows_excluded", 0),
        "downgrade_rows": result.get("downgrade_rows", 0),
        "downgrades_confirmed_rejected": result.get("downgrades_confirmed_rejected", 0),
        "downgrades_unresolved": unresolved,
        "product_supply_snapshot_rows": result.get("product_supply_snapshot_rows", 0),
        "completed": [
            "Immutable source vault and governed Collector universe",
            "Official release, TCGCSV price/history, MTGJSON structure, and packaging foundations",
            "Mature Phase 10 eBay subsystem and precision-v3-universal authority",
            "Current Browse API shadow acquisition and immutable raw payload preservation",
            "Offline replay of all 147 current listing rows with zero failures",
        ] + ([
            "All seven production downgrades adjudicated as confirmed exclusions",
            "First authoritative daily listing ledger written",
            "First certified Collector product-level supply snapshot written",
        ] if passed else []),
        "currently_being_worked_on": [
            "Establish listing entry/exit continuity and begin daily supply-history accumulation"
            if passed else
            "Resolve unresolved downgrade adjudications or supply-ledger integrity failures"
        ],
        "still_outstanding": [
            "Run subsequent daily collections through the same production matcher authority",
            "Create listing first-seen, last-seen, entry, exit, and relist continuity",
            "Accumulate sufficient daily supply history for trend features",
            "Build Supply Scarcity Index v1 in shadow mode",
            "Validate scarcity components and provisional weights",
            "Certify feature freshness, missingness, and point-in-time leakage controls",
            "Run historical validation and shadow forecast experiments",
            "Approve purchase recommendations only after forecast governance gates pass",
            "Export approved Collector outputs to UIP",
        ],
        "known_blockers": (
            [f"{unresolved} downgrade adjudications remain unresolved"]
            if unresolved else
            (["Daily ledger certification failed; inspect certification summary and output integrity"] if not passed else ["No eBay matching blocker; multi-day supply history does not yet exist"])
        ),
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "official_release_dates": "COMPLETE",
            "tcgcsv_current_price": "COMPLETE",
            "safe_historical_foundation": "COMPLETE",
            "released_product_mtgjson_structure": "COMPLETE",
            "packaging_normalization": "COMPLETE",
            "ebay_api_capability": "COMPLETE",
            "ebay_raw_acquisition": "COMPLETE_FOR_CURRENT_SNAPSHOT",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL",
            "ebay_transition_adjudication": "COMPLETE" if passed else "REVIEW_REQUIRED",
            "daily_listing_ledger": "CERTIFIED" if passed else "NOT_CERTIFIED",
            "product_supply_snapshot": "CERTIFIED" if passed else "NOT_CERTIFIED",
            "marketplace_supply_reconstruction": "SINGLE_DAY_CERTIFIED" if passed else "BLOCKED",
            "supply_history": "NOT_ACCUMULATED",
            "supply_scarcity_index": "DESIGNED_NOT_BUILT",
            "feature_certification": "NOT_STARTED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Build listing continuity, accumulate daily supply history, and create Supply Scarcity Index v1 shadow features"
            if passed else
            "Resolve daily supply certification failures and rerun strict certification"
        ),
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_DAILY_SUPPLY_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_ebay_daily_supply_project_control_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
