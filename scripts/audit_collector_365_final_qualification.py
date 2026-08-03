from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_365_final_qualification/candidate_v1_0_0"


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False)
    except (OSError, UnicodeDecodeError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    summary_path = OUT / "collector_365_final_qualification_summary.json"
    table_path = OUT / "collector_365_final_qualification_summary.csv"
    pred_path = OUT / "collector_365_final_qualification_predictions.csv"
    cutoff_path = OUT / "collector_365_final_qualification_cutoff_stability.csv"
    route_path = OUT / "collector_365_final_qualification_route_stability.csv"

    for path in [summary_path, table_path, pred_path, cutoff_path, route_path]:
        if not path.exists():
            failures.append(f"missing_output:{path.name}")

    summary = {}
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append("summary_unreadable")

    table = read_csv(table_path)
    pred = read_csv(pred_path)
    cutoff = read_csv(cutoff_path)
    route = read_csv(route_path)

    if table.empty:
        failures.append("qualification_summary_empty")
    else:
        required = {"method", "bias_shrinkage", "case_count", "cutoff_count", "mae", "signed_bias", "rank_correlation", "top_bottom_spread", "qualified"}
        if not required.issubset(table.columns):
            failures.append("qualification_metrics_incomplete")
        if not {"DIRECT", "COMPARABLE"}.issubset(set(table.get("method", []))):
            failures.append("required_methods_missing")

    if pred.empty:
        failures.append("qualification_predictions_empty")
    else:
        if not {"forecast", "realized_return_365", "prior_median_bias", "bias_shrinkage", "method", "decision_cutoff"}.issubset(pred.columns):
            failures.append("prediction_contract_incomplete")

    if cutoff.empty:
        failures.append("cutoff_stability_empty")
    if route.empty:
        failures.append("route_stability_empty")
    elif "product_age_route" not in route.columns:
        failures.append("route_dimension_missing")

    if int(summary.get("common_case_count", 0)) < 100:
        failures.append("common_case_gate_failed")
    if int(summary.get("common_cutoff_count", 0)) < 4:
        failures.append("common_cutoff_gate_failed")
    if summary.get("owner_review_required") is not True:
        failures.append("owner_review_gate_missing")

    for key in [
        "direct_method_authorized", "comparable_transfer_method_authorized",
        "candidate_methodology_change_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    result = {
        "audit_name": "Collector 365-Day Final Qualification Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
