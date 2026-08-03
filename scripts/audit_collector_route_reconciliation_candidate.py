from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_route_reconciliation/candidate_v1_0_0"
SUMMARY = OUT / "collector_route_reconciliation_summary.json"
FORECASTS = OUT / "collector_reconciled_candidate_forecasts.csv"
PEERS = OUT / "collector_reconciled_peer_contributions.csv"
EDGES = OUT / "collector_reconciled_completion_edges.csv"
OWNER = OUT / "collector_route_reconciliation_owner_review.csv"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    for path in [SUMMARY, FORECASTS, PEERS, EDGES, OWNER]:
        if not path.exists():
            failures.append(f"missing_output:{path}")

    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    forecasts = pd.read_csv(FORECASTS, low_memory=False)
    peers = pd.read_csv(PEERS, low_memory=False)
    edges = pd.read_csv(EDGES, low_memory=False)
    owner = pd.read_csv(OWNER, low_memory=False)

    complete = forecasts["candidate_calculation_complete"].map(truthy)
    preserved = forecasts["reconciliation_action"].astype(str) == "PRESERVED_REPAIRED_BASELINE"
    filled = forecasts["reconciliation_action"].astype(str) == "FILLED_INCOMPLETE_ROUTE"
    reverse = forecasts["reverse_pair_candidate_used"].map(truthy)
    override = forecasts["owner_approved_override_used"].map(truthy)

    expected_routes = {
        "DIRECT_HISTORY_CALIBRATED": 19,
        "DIRECT_HISTORY_LIMITED": 7,
        "COMPARABLE_PRODUCT_ADJUSTED": 24,
        "FUNDAMENTAL_COMPARABLE_HYBRID": 1,
    }

    if len(forecasts) != 51:
        failures.append(f"product_count_expected_51_actual_{len(forecasts)}")
    if int(preserved.sum()) != 43:
        failures.append(f"preserved_repaired_baseline_expected_43_actual_{int(preserved.sum())}")
    if int(filled.sum()) != 8:
        failures.append(f"filled_incomplete_routes_expected_8_actual_{int(filled.sum())}")
    if int(complete.sum()) < 43:
        failures.append("completion_regressed_below_repaired_baseline")
    for route, expected in expected_routes.items():
        actual = int((forecasts["forecast_method_route"].astype(str) == route).sum())
        if actual != expected:
            failures.append(f"route_count_{route}_expected_{expected}_actual_{actual}")
    if len(peers) < 624:
        failures.append(f"peer_contribution_regression_below_624_actual_{len(peers)}")
    if not (peers["decision_input_status"].astype(str) == "RETROSPECTIVE_DIAGNOSTIC_ONLY").all():
        failures.append("peer_decision_input_status_violation")
    if int(override.sum()) != 1:
        failures.append(f"japanese_override_expected_1_actual_{int(override.sum())}")
    if "owner_decision_required" not in owner.columns:
        failures.append("owner_decision_required_missing")
    if bool(summary.get("candidate_projection_authorized")):
        failures.append("candidate_projection_unexpectedly_authorized")
    if bool(summary.get("production_projection_authorized")):
        failures.append("production_projection_unexpectedly_authorized")
    if bool(summary.get("purchase_recommendation_authorized")):
        failures.append("purchase_recommendation_unexpectedly_authorized")
    if bool(summary.get("automatic_model_update_allowed")):
        failures.append("automatic_model_update_unexpectedly_allowed")

    if args.strict:
        if int(complete.sum()) != 51:
            failures.append(f"strict_complete_count_expected_51_actual_{int(complete.sum())}")
        if int(reverse.sum()) != 7:
            failures.append(f"strict_reverse_pair_products_expected_7_actual_{int(reverse.sum())}")
        if int(summary.get("limited_history_recomputed_count", 0)) != 7:
            failures.append("strict_limited_history_recomputed_count_not_7")
        if edges.empty:
            failures.append("strict_reconciled_edges_empty")

    result = {
        "audit_name": "Collector Route Reconciliation Candidate Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(forecasts)),
        "preserved_repaired_baseline_count": int(preserved.sum()),
        "filled_incomplete_route_count": int(filled.sum()),
        "candidate_calculation_complete_count": int(complete.sum()),
        "candidate_calculation_incomplete_count": int((~complete).sum()),
        "limited_history_recomputed_count": int(summary.get("limited_history_recomputed_count", 0)),
        "reverse_pair_candidate_product_count": int(reverse.sum()),
        "owner_approved_override_product_count": int(override.sum()),
        "peer_contribution_count": int(len(peers)),
        "future_information_prohibited": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit proves the 43-product repaired baseline is preserved before evaluating the eight reconciled routes. Reverse-pair evidence remains diagnostic and owner approval is still required."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
