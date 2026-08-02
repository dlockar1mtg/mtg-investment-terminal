"""Run Collector eBay daily supply certification plus identity-integrity repair."""
from __future__ import annotations

import argparse
import json
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
    commands = [
        [sys.executable, "scripts/certify_collector_ebay_daily_supply.py"],
        [sys.executable, "scripts/repair_collector_ebay_daily_supply_identity.py"],
    ]
    if args.strict:
        for command in commands:
            command.append("--strict")

    steps = []
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        steps.append({"command": command, "return_code": completed.returncode, "passed": completed.returncode == 0})
        if completed.returncode != 0:
            break

    cert = read_json(OUT / "collector_ebay_daily_supply_summary.json")
    repair = read_json(OUT / "collector_ebay_daily_supply_identity_repair_summary.json")
    passed = len(steps) == 2 and all(step["passed"] for step in steps) and str(repair.get("status", "")).startswith("PASS_")

    summary = {
        "block_name": "Collector eBay Daily Supply Integrity and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "offline_only": True,
        "quota_calls": 0,
        "certification_passed": str(cert.get("status", "")).startswith("PASS_"),
        "identity_integrity_passed": str(repair.get("status", "")).startswith("PASS_"),
        "accepted_listing_rows_certified": cert.get("accepted_listing_rows_certified", 0),
        "product_supply_snapshot_rows": cert.get("product_supply_snapshot_rows", 0),
        "ledger_blank_names_after": repair.get("ledger_blank_names_after", -1),
        "snapshot_blank_names_after": repair.get("snapshot_blank_names_after", -1),
        "adjudication_blank_names_after": repair.get("adjudication_blank_names_after", -1),
        "multi_display_adjudications_corrected": repair.get("multi_display_adjudications_corrected", 0),
        "completed": [
            "First certified Collector eBay daily listing ledger",
            "First certified Collector product-level supply snapshot",
            "Governed product names propagated into all supply outputs",
            "All seven downgrade adjudications retained as confirmed rejections",
            "4x multi-display edge case correctly classified",
        ] if passed else ["Daily supply certification attempted; identity integrity remains unresolved"],
        "currently_being_worked_on": [
            "Build full-universe zero-observation rows and listing continuity"
            if passed else "Resolve daily supply identity-integrity failures"
        ],
        "still_outstanding": [
            "Add explicit zero-observation rows for governed products without accepted listings",
            "Create listing first-seen, last-seen, entry, exit, and relist continuity",
            "Run subsequent daily collections through precision-v3-universal",
            "Accumulate multi-day supply history",
            "Build Supply Scarcity Index v1 shadow features",
            "Certify feature freshness, missingness, and point-in-time leakage controls",
            "Run historical validation and shadow forecast experiments",
            "Approve purchase recommendations and UIP export only after governance gates pass",
        ],
        "known_blockers": [
            "Only one certified day of marketplace supply exists"
            if passed else "Blank governed identities or incorrect adjudication labels remain"
        ],
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "official_release_dates": "COMPLETE",
            "tcgcsv_current_price": "COMPLETE",
            "safe_historical_foundation": "COMPLETE",
            "released_product_mtgjson_structure": "COMPLETE",
            "packaging_normalization": "COMPLETE",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL",
            "ebay_transition_adjudication": "COMPLETE" if passed else "REPAIR_REQUIRED",
            "daily_listing_ledger": "CERTIFIED_IDENTITY_COMPLETE" if passed else "IDENTITY_INCOMPLETE",
            "product_supply_snapshot": "CERTIFIED_IDENTITY_COMPLETE" if passed else "IDENTITY_INCOMPLETE",
            "marketplace_supply_reconstruction": "SINGLE_DAY_CERTIFIED" if passed else "BLOCKED_BY_IDENTITY_INTEGRITY",
            "supply_history": "NOT_ACCUMULATED",
            "supply_scarcity_index": "DESIGNED_NOT_BUILT",
            "feature_certification": "NOT_STARTED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Build full-universe zero-observation rows, listing continuity, and Supply Scarcity Index v1 shadow features"
            if passed else "Repair governed identity propagation and rerun strict integrity certification"
        ),
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_COLLECTOR_EBAY_DAILY_SUPPLY_INTEGRITY" if passed else "REVIEW_REQUIRED",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_ebay_daily_supply_integrity_project_control_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
