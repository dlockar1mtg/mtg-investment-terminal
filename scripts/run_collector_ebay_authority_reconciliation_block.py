"""Run Collector eBay authority reconciliation and emit permanent project control."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/governance/permanence/certification/collector_ebay_authority_reconciliation"


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
    command = [sys.executable, "scripts/reconcile_collector_ebay_authority.py"]
    if args.strict:
        command.append("--strict")
    completed = subprocess.run(command, cwd=ROOT, check=False)
    result = read_json(OUT / "collector_ebay_authority_reconciliation_summary.json")

    passed = completed.returncode == 0 and str(result.get("status", "")).startswith("PASS_")
    changes = int(result.get("classification_changes", 0) or 0)
    reviews = int(result.get("production_review", 0) or 0)

    summary = {
        "block_name": "Collector eBay Authority Reconciliation and Project Control",
        "block_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": [{"command": command, "return_code": completed.returncode, "passed": passed}],
        "offline_only": True,
        "quota_calls": 0,
        "reconciliation_passed": passed,
        "production_matcher_version": result.get("production_matcher_version", ""),
        "shadow_rows_replayed": result.get("shadow_rows_replayed", 0),
        "classification_changes": changes,
        "production_review_rows": reviews,
        "completed": [
            "Immutable source vault and governed 50-product Collector universe",
            "Official release, TCGCSV price/history, MTGJSON structure, and packaging foundations",
            "Existing mature Phase 10 eBay subsystem recovered",
            "Production matcher explicitly identified as precision-v3-universal",
            "Current 50-product Browse API shadow payloads preserved",
        ] + (["All current shadow listing rows replayed through the production matcher with zero eBay quota calls"] if passed else []),
        "currently_being_worked_on": [
            "Review classification transitions and production REVIEW rows before supply certification"
            if passed and (changes > 0 or reviews > 0)
            else "Resolve reconciliation input or replay failures"
            if not passed
            else "Design the authoritative daily listing ledger and product supply snapshot"
        ],
        "still_outstanding": [
            "Review all shadow-to-production classification changes and reason codes",
            "Resolve production REVIEW rows or preserve them as excluded from certified supply",
            "Integrate authoritative matcher decisions with seller and quantity enrichment",
            "Create certified daily listing-level ledger and product-level supply snapshot",
            "Accumulate listing entry/exit history and supply trend features",
            "Build and validate Supply Scarcity Index v1 in shadow mode",
            "Certify feature tables, freshness, missingness, and point-in-time leakage controls",
            "Run historical validation and shadow forecast experiments",
            "Approve purchase recommendations and UIP export only after governance gates pass",
        ],
        "known_blockers": (
            ["Authority reconciliation did not pass; inspect replay failures and missing prior evidence"]
            if not passed
            else ([f"{changes} classification transitions and {reviews} production REVIEW rows require adjudication"] if changes > 0 or reviews > 0 else ["No eBay authority blocker; daily ledger design remains outstanding"])
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
            "ebay_raw_acquisition": "SHADOW_COMPLETE",
            "ebay_matching_authority": "PRECISION_V3_UNIVERSAL" if passed else "RECONCILIATION_REQUIRED",
            "current_shadow_classification": "REPLAYED_REVIEW_REQUIRED" if passed and (changes > 0 or reviews > 0) else "RECONCILED" if passed else "UNRECONCILED",
            "marketplace_supply_reconstruction": "BLOCKED_BY_TRANSITION_REVIEW" if passed and (changes > 0 or reviews > 0) else "READY_FOR_LEDGER_BUILD" if passed else "BLOCKED_BY_RECONCILIATION",
            "supply_scarcity_index": "DESIGNED_NOT_BUILT",
            "feature_certification": "NOT_STARTED",
            "forecasting": "BLOCKED",
            "purchase_recommendations": "BLOCKED",
            "uip_delivery": "BLOCKED",
        },
        "next_large_step": (
            "Adjudicate classification transitions, bind production decisions to quantity/seller enrichment, and certify the first daily listing ledger"
            if passed
            else "Resolve missing evidence or replay failures, then rerun strict authority reconciliation"
        ),
        "forecasting_resume_authorized": False,
        "purchase_recommendation_authorized": False,
        "uip_delivery_authorized": False,
        "status": "PASS_EBAY_AUTHORITY_RECONCILIATION_PROJECT_CONTROL" if passed else "REVIEW_REQUIRED",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "collector_ebay_project_control_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if passed else (1 if args.strict else 0)


if __name__ == "__main__":
    raise SystemExit(main())
