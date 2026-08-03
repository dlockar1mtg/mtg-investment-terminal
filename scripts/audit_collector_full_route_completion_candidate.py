from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_full_route_completion/candidate_v1_0_0"
SUMMARY = OUT / "collector_full_route_completion_summary.json"
FORECASTS = OUT / "collector_full_route_candidate_forecasts.csv"
PEERS = OUT / "collector_full_route_peer_contributions.csv"
OWNER = OUT / "collector_full_route_owner_review.csv"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    for path in [SUMMARY, FORECASTS, PEERS, OWNER]:
        if not path.exists():
            failures.append(f"missing_output:{path}")

    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    forecasts = pd.read_csv(FORECASTS, low_memory=False)
    peers = pd.read_csv(PEERS, low_memory=False)
    owner = pd.read_csv(OWNER, low_memory=False)

    if len(forecasts) != 51:
        failures.append(f"product_count_expected_51_actual_{len(forecasts)}")
    if int(summary.get("candidate_calculation_complete_count", 0)) < 43:
        failures.append("completion_regressed_below_repaired_baseline")
    if len(peers) == 0:
        failures.append("peer_contributions_empty")
    if not (peers["decision_input_status"].astype(str) == "RETROSPECTIVE_DIAGNOSTIC_ONLY").all():
        failures.append("peer_decision_input_status_violation")
    if bool(summary.get("candidate_projection_authorized")):
        failures.append("candidate_projection_unexpectedly_authorized")
    if bool(summary.get("production_projection_authorized")):
        failures.append("production_projection_unexpectedly_authorized")
    if bool(summary.get("purchase_recommendation_authorized")):
        failures.append("purchase_recommendation_unexpectedly_authorized")
    if bool(summary.get("automatic_model_update_allowed")):
        failures.append("automatic_model_update_unexpectedly_allowed")
    if "owner_decision_required" not in owner.columns:
        failures.append("owner_decision_column_missing")
    if int(summary.get("owner_approved_override_product_count", 0)) != 1:
        failures.append("japanese_override_expected_once")

    result = {
        "audit_name": "Collector Full-Route Completion Candidate Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(forecasts)),
        "candidate_calculation_complete_count": int(summary.get("candidate_calculation_complete_count", 0)),
        "candidate_calculation_incomplete_count": int(summary.get("candidate_calculation_incomplete_count", 0)),
        "limited_history_recomputed_count": int(summary.get("limited_history_recomputed_count", 0)),
        "reverse_pair_candidate_product_count": int(summary.get("reverse_pair_candidate_product_count", 0)),
        "owner_approved_override_product_count": int(summary.get("owner_approved_override_product_count", 0)),
        "peer_contribution_count": int(len(peers)),
        "future_information_prohibited": True,
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit validates route-completion diagnostics and disclosure. Symmetric reverse-pair use remains a candidate owner decision and no forecast or purchase authorization is granted."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
