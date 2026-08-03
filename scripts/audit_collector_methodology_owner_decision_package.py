from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_methodology_owner_decision_package/candidate_v1_0_0"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    paths = {
        "summary": OUT / "collector_methodology_owner_decision_package_summary.json",
        "products": OUT / "collector_methodology_owner_product_recommendations.csv",
        "routes": OUT / "collector_methodology_owner_route_recommendations.csv",
        "decisions": OUT / "collector_methodology_owner_decision_register.csv",
        "spec": OUT / "collector_recommended_candidate_methodology.json",
    }
    failures = [f"missing_output:{name}:{path}" for name, path in paths.items() if not path.exists()]
    if failures:
        result = {"status": "FAIL", "failure_count": len(failures), "failures": failures}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    products = pd.read_csv(paths["products"], low_memory=False)
    routes = pd.read_csv(paths["routes"], low_memory=False)
    decisions = pd.read_csv(paths["decisions"], low_memory=False)
    spec = json.loads(paths["spec"].read_text(encoding="utf-8"))

    if len(products) != 51:
        failures.append(f"product_count_expected_51_actual_{len(products)}")
    if routes["forecast_method_route"].nunique() != 4:
        failures.append("route_count_expected_4")
    if len(decisions) != 6:
        failures.append(f"decision_count_expected_6_actual_{len(decisions)}")
    if spec.get("status") != "RECOMMENDED_INACTIVE_OWNER_REVIEW_REQUIRED":
        failures.append("recommended_specification_status_invalid")
    if not (products["recommendation_status"] == "NONBINDING_CANDIDATE_REQUIRES_OWNER_APPROVAL").all():
        failures.append("product_recommendation_status_violation")
    if not (routes["recommendation_status"] == "NONBINDING_CANDIDATE_REQUIRES_OWNER_APPROVAL").all():
        failures.append("route_recommendation_status_violation")
    for field in [
        "candidate_projection_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]:
        if truthy(summary.get(field)) or truthy(spec.get(field)):
            failures.append(f"authorization_unexpectedly_enabled:{field}")
    if not bool(summary.get("future_information_prohibited", False)):
        failures.append("future_information_not_prohibited")

    result = {
        "audit_name": "Collector Methodology Owner Decision Package Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "product_count": int(len(products)),
        "route_count": int(routes["forecast_method_route"].nunique()),
        "decision_count": int(len(decisions)),
        "recommended_specification_status": spec.get("status"),
        "candidate_projection_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "future_information_prohibited": True,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit validates the completeness and authorization boundaries of the nonbinding owner decision package. It does not approve or activate the recommendations."
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
