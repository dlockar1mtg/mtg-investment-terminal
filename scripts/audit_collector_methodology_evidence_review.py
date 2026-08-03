from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_methodology_evidence_review/candidate_v1_0_0"
SUMMARY = OUT / "collector_methodology_evidence_review_summary.json"
PRODUCTS = OUT / "collector_methodology_product_review.csv"
ROUTES = OUT / "collector_route_risk_summary.csv"
PEERS = OUT / "collector_peer_concentration_diagnostics.csv"
DECISIONS = OUT / "collector_owner_methodology_decisions.csv"
LEDGER = ROOT / "data/operations/collector_prospective_snapshot_ledger/collector_prospective_decision_snapshot_ledger.csv"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    for path in [SUMMARY, PRODUCTS, ROUTES, PEERS, DECISIONS, LEDGER]:
        if not path.exists():
            failures.append(f"missing_output:{path}")
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    products = pd.read_csv(PRODUCTS, low_memory=False)
    routes = pd.read_csv(ROUTES, low_memory=False)
    decisions = pd.read_csv(DECISIONS, low_memory=False)
    ledger = pd.read_csv(LEDGER, low_memory=False)

    if len(products) != 51:
        failures.append(f"product_count_expected_51_actual_{len(products)}")
    if int(products["candidate_calculation_complete"].map(truthy).sum()) != 51:
        failures.append("all_51_candidate_calculations_not_complete")
    if set(routes["forecast_method_route"].astype(str)) != {
        "DIRECT_HISTORY_CALIBRATED",
        "DIRECT_HISTORY_LIMITED",
        "COMPARABLE_PRODUCT_ADJUSTED",
        "FUNDAMENTAL_COMPARABLE_HYBRID",
    }:
        failures.append("route_set_incomplete")
    if int(summary.get("reverse_pair_product_count", 0)) != 7:
        failures.append("reverse_pair_product_count_expected_7")
    if "PENDING_OWNER_DECISION" not in set(decisions["current_status"].astype(str)):
        failures.append("pending_owner_decisions_missing")
    if not (decisions["forecast_authorization_granted"].map(truthy) == False).all():
        failures.append("forecast_authorization_unexpectedly_granted")
    if not (decisions["purchase_authorization_granted"].map(truthy) == False).all():
        failures.append("purchase_authorization_unexpectedly_granted")
    if bool(summary.get("candidate_projection_authorized")):
        failures.append("candidate_projection_unexpectedly_authorized")
    if bool(summary.get("production_projection_authorized")):
        failures.append("production_projection_unexpectedly_authorized")
    if bool(summary.get("purchase_recommendation_authorized")):
        failures.append("purchase_recommendation_unexpectedly_authorized")
    key_cols = [c for c in ["decision_date", "canonical_tcgplayer_product_id", "candidate_model_version"] if c in ledger.columns]
    if key_cols and ledger.duplicated(key_cols).any():
        failures.append("prospective_ledger_duplicate_snapshot_key")

    result = {
        "audit_name": "Collector Methodology Evidence Review Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(products)),
        "complete_candidate_count": int(products["candidate_calculation_complete"].map(truthy).sum()),
        "route_count": int(len(routes)),
        "reverse_pair_product_count": int(summary.get("reverse_pair_product_count", 0)),
        "short_history_product_count": int(summary.get("short_history_product_count", 0)),
        "methodology_review_required_product_count": int(summary.get("methodology_review_required_product_count", 0)),
        "prospective_ledger_row_count": int(len(ledger)),
        "future_information_prohibited": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit validates evidence-review outputs and append-safe prospective capture. It does not certify forecast accuracy or authorize production or purchases."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
