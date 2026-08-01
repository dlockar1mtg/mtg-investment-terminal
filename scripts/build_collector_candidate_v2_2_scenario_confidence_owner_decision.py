from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_candidate_v2_2_scenario_confidence_owner_decision_v1.json"


def truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    review_root = ROOT / cfg["inputs"]["scenario_review_root"]
    out = ROOT / cfg["output_directory"]
    source = review_root / "collector_candidate_v2_2_scenario_confidence_product_review.csv"
    if not source.exists():
        result = {"status": "FAIL", "failure_count": 1, "failures": [f"missing_input:{source}"]}
        print(json.dumps(result, indent=2))
        return 1 if args.strict else 0

    products = pd.read_csv(source, low_memory=False)
    decisions = []
    for decision_id, rec in cfg["recommendations"].items():
        decisions.append({
            "decision_id": decision_id,
            "topic": rec["topic"],
            "nonbinding_recommendation": rec["recommendation"],
            "owner_decision_status": "PENDING_OWNER_DECISION",
            "owner_selected_option": "",
            "owner_rationale": "",
            "activation_authorized": False,
        })
    decision_frame = pd.DataFrame(decisions)

    scenario_rec = cfg["recommendations"]["COL-SCEN-001"]
    confidence_rec = cfg["recommendations"]["COL-CONF-001"]
    route_rows = []
    for route, group in products.groupby("forecast_method_route", dropna=False):
        route_rows.append({
            "forecast_method_route": route,
            "product_count": int(len(group)),
            "mean_inherited_width": pd.to_numeric(group["inherited_uncertainty_width"], errors="coerce").mean(),
            "mean_diagnostic_width": pd.to_numeric(group["diagnostic_loss_bounded_width"], errors="coerce").mean(),
            "mean_diagnostic_confidence_internal": pd.to_numeric(group["diagnostic_confidence_score"], errors="coerce").mean(),
            "mean_diagnostic_confidence_export_0_to_100": 100 * pd.to_numeric(group["diagnostic_confidence_score"], errors="coerce").mean(),
            "recommended_minimum_width": scenario_rec["route_minimum_widths"].get(str(route)),
            "recommended_maximum_width": scenario_rec["route_maximum_widths"].get(str(route)),
            "recommended_loss_floor": scenario_rec["downside_annual_rate_floor"],
            "recommendation_status": "INACTIVE_OWNER_DECISION_REQUIRED",
        })
    route_frame = pd.DataFrame(route_rows)

    product_review = products.copy()
    product_review["recommended_scenario_methodology"] = scenario_rec["recommendation"]
    product_review["recommended_confidence_methodology"] = confidence_rec["recommendation"]
    product_review["diagnostic_confidence_export_0_to_100"] = 100 * pd.to_numeric(product_review["diagnostic_confidence_score"], errors="coerce")
    product_review["scenario_methodology_authorized"] = False
    product_review["confidence_methodology_authorized"] = False
    product_review["candidate_projection_authorized"] = False
    product_review["production_projection_authorized"] = False
    product_review["purchase_recommendation_authorized"] = False

    out.mkdir(parents=True, exist_ok=True)
    decision_frame.to_csv(out / "collector_scenario_confidence_owner_decision_ballot.csv", index=False)
    route_frame.to_csv(out / "collector_scenario_confidence_route_recommendations.csv", index=False)
    product_review.to_csv(out / "collector_scenario_confidence_product_recommendations.csv", index=False)
    (out / "collector_scenario_confidence_recommended_inactive_specification.json").write_text(
        json.dumps({
            "status": "INACTIVE_OWNER_DECISION_REQUIRED",
            "scenario_recommendation": scenario_rec,
            "confidence_recommendation": confidence_rec,
            "scenario_methodology_authorized": False,
            "confidence_methodology_authorized": False,
            "candidate_projection_authorized": False,
            "production_projection_authorized": False,
            "purchase_recommendation_authorized": False,
            "automatic_model_update_allowed": False,
        }, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = {
        "audit_name": "Collector Candidate v2.2 Scenario and Confidence Owner Decision Package",
        "audit_version": "1.0.0",
        "status": "PASS",
        "product_count": int(len(products)),
        "route_count": int(products["forecast_method_route"].nunique()),
        "decision_count": int(len(decision_frame)),
        "pending_owner_decision_count": int((decision_frame["owner_decision_status"] == "PENDING_OWNER_DECISION").sum()),
        "scenario_width_review_count": int(products["scenario_width_review_required"].map(truthy).sum()),
        "confidence_review_count": int(products["confidence_review_required"].map(truthy).sum()),
        "scenario_methodology_authorized": False,
        "confidence_methodology_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": 0,
        "failures": [],
        "governing_note": "This package presents two nonbinding owner decisions. It does not activate scenario widths, confidence scores, production forecasts, or purchases.",
    }
    if len(products) != 51 or summary["route_count"] != 4 or len(decision_frame) != 2:
        summary["status"] = "FAIL"
        summary["failure_count"] = 1
        summary["failures"] = ["structural_expectation_failed"]
    (out / "collector_scenario_confidence_owner_decision_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and summary["status"] != "PASS" else 0


if __name__ == "__main__":
    raise SystemExit(main())
