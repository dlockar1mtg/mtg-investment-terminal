"""Run Collector packaging normalization and governed eBay supply foundation.

This block always writes a project-control summary with completed, active, outstanding,
blocker, authorization, and next-step sections so execution cannot drift from the goal.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_packaging_ebay_foundation"
PACKAGING_SUMMARY = ROOT / "data/governance/permanence/certification/collector_packaging_normalization/collector_packaging_normalization_summary.json"
EBAY_SUMMARY = ROOT / "data/governance/permanence/certification/collector_ebay_supply_collection/collector_ebay_supply_collection_summary.json"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run Collector packaging and eBay foundation")
    p.add_argument("--ebay-mode", choices=["none", "capability", "diagnostic", "shadow"], default="none")
    p.add_argument("--product-id", default="541238")
    p.add_argument("--strict", action="store_true")
    return p


def run(command: list[str]) -> dict:
    result = subprocess.run(command, cwd=ROOT)
    return {"command": command, "return_code": result.returncode, "passed": result.returncode == 0}


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    args = parser().parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    py = sys.executable
    steps: list[dict] = []

    packaging_cmd = [py, "scripts/build_collector_packaging_normalization.py", "--strict"]
    steps.append(run(packaging_cmd))

    ebay_step = None
    if args.ebay_mode != "none":
        ebay_cmd = [py, "scripts/run_collector_ebay_supply_collection.py", "--mode", args.ebay_mode]
        if args.ebay_mode == "diagnostic":
            ebay_cmd += ["--product-id", args.product_id]
        if args.strict:
            ebay_cmd.append("--strict")
        ebay_step = run(ebay_cmd)
        steps.append(ebay_step)

    packaging = read_json(PACKAGING_SUMMARY)
    ebay = read_json(EBAY_SUMMARY) if args.ebay_mode != "none" else {}
    credentials_present = bool(os.getenv("EBAY_CLIENT_ID", "").strip() and os.getenv("EBAY_CLIENT_SECRET", "").strip())
    packaging_complete = bool(packaging.get("packaging_complete_for_verified_products", False))
    ebay_capability = bool(ebay.get("credential_test_passed", False))
    diagnostic_complete = ebay.get("status") == "PASS_DIAGNOSTIC_SHADOW_COLLECTION"
    shadow_complete = bool(ebay.get("full_shadow_snapshot_complete", False))

    completed = [
        "Immutable source vault and governed Collector universe",
        "Official release-date authority for 50 governed products",
        "TCGCSV current-price and safe monthly historical foundations",
        "Current verified MTGJSON AllPrintings source and released-product structural crosswalk",
        "Governed eBay search contracts for 50 products",
    ]
    if packaging_complete:
        completed.append("Normalized Collector display packaging for all structurally verified products")
    if ebay_capability:
        completed.append("eBay OAuth application-token capability")
    if diagnostic_complete:
        completed.append("One-product eBay diagnostic supply collection")
    if shadow_complete:
        completed.append("First 50-product eBay shadow supply snapshot")

    working_on = []
    if not packaging_complete:
        working_on.append("Resolve Collector packaging normalization review rows")
    if not credentials_present:
        working_on.append("Await local eBay credential environment variables; no secrets may enter Git")
    elif not ebay_capability:
        working_on.append("Certify eBay OAuth and Browse API capability")
    elif not diagnostic_complete:
        working_on.append("Run and review one-product eBay diagnostic")
    elif not shadow_complete:
        working_on.append("Run and review the first 50-product shadow supply snapshot")
    else:
        working_on.append("Adjudicate shadow listing review queue before production supply certification")

    outstanding = [
        "Certify accepted/rejected eBay listing rules against the diagnostic review queue",
        "Create certified daily eBay listing-level ledger and product-level supply snapshot",
        "Accumulate listing entry/exit history and supply trend features",
        "Build and validate the Supply Scarcity Index in shadow mode",
        "Certify feature tables, point-in-time leakage controls, and freshness rules",
        "Run model experiments, historical validation, and shadow forecasts",
        "Approve purchase recommendations and UIP export only after governance gates pass",
    ]

    blockers = []
    if not packaging_complete:
        blockers.append(f"Packaging blockers: {packaging.get('released_product_packaging_blockers', 'unknown')}")
    if not credentials_present:
        blockers.append("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET are not present in the local process environment")
    elif args.ebay_mode != "none" and not ebay_capability:
        blockers.append(f"eBay capability status: {ebay.get('status', 'not run')}")
    if not blockers:
        blockers.append("No current source blocker; shadow listing adjudication remains required before certification")

    result = {
        "block_name": "Collector Packaging and eBay Supply Foundation",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "requested_ebay_mode": args.ebay_mode,
        "steps": steps,
        "all_executed_steps_passed": all(x["passed"] for x in steps),
        "packaging_complete_for_verified_products": packaging_complete,
        "ebay_credentials_present": credentials_present,
        "ebay_capability_certified": ebay_capability,
        "ebay_diagnostic_complete": diagnostic_complete,
        "ebay_shadow_snapshot_complete": shadow_complete,
        "completed": completed,
        "currently_being_worked_on": working_on,
        "still_outstanding": outstanding,
        "known_blockers": blockers,
        "authorization_state": {
            "source_preservation": "COMPLETE",
            "governed_identity": "COMPLETE",
            "official_release_dates": "COMPLETE",
            "tcgcsv_current_price": "COMPLETE",
            "safe_historical_foundation": "COMPLETE",
            "released_product_mtgjson_structure": "COMPLETE",
            "packaging_normalization": "COMPLETE" if packaging_complete else "REVIEW_REQUIRED",
            "ebay_contracts": "COMPLETE",
            "ebay_live_capability": "COMPLETE" if ebay_capability else "NOT_COMPLETE",
            "marketplace_supply_reconstruction": "SHADOW_COMPLETE" if shadow_complete else "NOT_COMPLETE",
            "supply_scarcity_index": "DESIGNED_NOT_BUILT",
            "feature_certification": "NOT_STARTED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Adjudicate the 50-product eBay shadow review queue and certify the first daily supply snapshot"
            if shadow_complete
            else "Provide local eBay environment variables, pass capability, run one-product diagnostic, then run the 50-product shadow snapshot"
        ),
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
    }

    if not packaging_complete:
        result["status"] = "REVIEW_REQUIRED"
    elif args.ebay_mode == "none" or (not credentials_present and ebay.get("status") == "CREDENTIALS_REQUIRED"):
        result["status"] = "PASS_PACKAGING_EBAY_CREDENTIAL_GATE_PENDING"
    elif args.ebay_mode == "capability" and ebay_capability:
        result["status"] = "PASS_PACKAGING_AND_EBAY_CAPABILITY"
    elif args.ebay_mode == "diagnostic" and diagnostic_complete:
        result["status"] = "PASS_PACKAGING_AND_EBAY_DIAGNOSTIC"
    elif args.ebay_mode == "shadow" and shadow_complete:
        result["status"] = "PASS_PACKAGING_AND_EBAY_SHADOW_FOUNDATION"
    else:
        result["status"] = "REVIEW_REQUIRED"

    (OUT / "collector_packaging_ebay_foundation_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if args.strict and result["status"] == "REVIEW_REQUIRED":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
