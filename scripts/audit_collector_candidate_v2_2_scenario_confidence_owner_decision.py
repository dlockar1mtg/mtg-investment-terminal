from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ROOT_OUT = ROOT / "data/operations/collector_candidate_v2_2_scenario_confidence_owner_decision/candidate_v1_0_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    paths = {
        "summary": ROOT_OUT / "collector_scenario_confidence_owner_decision_summary.json",
        "ballot": ROOT_OUT / "collector_scenario_confidence_owner_decision_ballot.csv",
        "routes": ROOT_OUT / "collector_scenario_confidence_route_recommendations.csv",
        "products": ROOT_OUT / "collector_scenario_confidence_product_recommendations.csv",
        "specification": ROOT_OUT / "collector_scenario_confidence_recommended_inactive_specification.json",
    }
    failures = [f"missing_output:{name}:{path}" for name, path in paths.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    ballot = pd.read_csv(paths["ballot"], low_memory=False)
    routes = pd.read_csv(paths["routes"], low_memory=False)
    products = pd.read_csv(paths["products"], low_memory=False)
    specification = json.loads(paths["specification"].read_text(encoding="utf-8"))

    if len(products) != 51:
        failures.append("product_count_not_51")
    if products["forecast_method_route"].nunique() != 4 or len(routes) != 4:
        failures.append("route_count_not_4")
    if len(ballot) != 2:
        failures.append("decision_count_not_2")
    if set(ballot["decision_id"]) != {"COL-SCEN-001", "COL-CONF-001"}:
        failures.append("decision_ids_invalid")
    if not (ballot["owner_decision_status"] == "PENDING_OWNER_DECISION").all():
        failures.append("owner_decisions_not_pending")
    if ballot["activation_authorized"].map(truthy).any():
        failures.append("activation_authorized")
    for key in [
        "scenario_methodology_authorized",
        "confidence_methodology_authorized",
        "candidate_projection_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]:
        if truthy(specification.get(key)):
            failures.append(f"authorization_open:{key}")

    result = {
        "audit_name": "Collector Candidate v2.2 Scenario and Confidence Owner Decision Package Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(products)),
        "route_count": int(products["forecast_method_route"].nunique()),
        "decision_count": int(len(ballot)),
        "pending_owner_decision_count": int((ballot["owner_decision_status"] == "PENDING_OWNER_DECISION").sum()),
        "scenario_methodology_authorized": False,
        "confidence_methodology_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit verifies the inactive decision package and closed authorization boundaries. It does not approve either recommendation.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
