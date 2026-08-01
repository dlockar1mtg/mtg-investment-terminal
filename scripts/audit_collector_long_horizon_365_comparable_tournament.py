from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_long_horizon_365_comparable_tournament/candidate_v1_0_0"


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

    paths = {
        "summary": OUT / "collector_long_horizon_365_comparable_tournament_summary.json",
        "direct_summary": OUT / "collector_365_direct_tournament_summary.csv",
        "direct_predictions": OUT / "collector_365_direct_tournament_predictions.csv",
        "comparable_summary": OUT / "collector_365_comparable_transfer_summary.csv",
        "comparable_predictions": OUT / "collector_365_comparable_transfer_predictions.csv",
        "matches": OUT / "collector_365_comparable_matches.csv",
    }
    for name, path in paths.items():
        if not path.exists():
            failures.append(f"missing_output:{name}")

    summary = {}
    if paths["summary"].exists():
        try:
            summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            failures.append("summary_unreadable")

    direct = read_csv(paths["direct_summary"])
    comp = read_csv(paths["comparable_predictions"])
    matches = read_csv(paths["matches"])
    if direct.empty:
        failures.append("direct_summary_empty")
    else:
        required_direct = {"variant", "variant_type", "case_count", "cutoff_count", "mae", "signed_bias", "direction_accuracy", "rank_correlation", "top_bottom_spread", "trimmed_95_mae", "outlier_mae_delta"}
        if not required_direct.issubset(direct.columns):
            failures.append("direct_metrics_incomplete")
        if not {"CURRENT_365", "NO_CHANGE", "CATEGORY_MEDIAN"}.issubset(set(direct.get("variant", []))):
            failures.append("required_baselines_missing")
        if not (direct.get("variant_type", pd.Series(dtype=str)).astype(str) == "DIRECT_CHALLENGER").any():
            failures.append("direct_challengers_missing")

    if comp.empty:
        failures.append("comparable_predictions_empty")
    else:
        required_comp = {"forecast_route", "comparable_forecast_return_365", "realized_return_365", "comparable_count", "uncertainty_multiplier", "evidence_grade"}
        if not required_comp.issubset(comp.columns):
            failures.append("comparable_contract_incomplete")
        allowed_routes = {"BLENDED", "COMPARABLE", "BLOCKED"}
        if not set(comp.get("forecast_route", [])).issubset(allowed_routes):
            failures.append("invalid_comparable_route")
        authorized = comp.get("forecast_route", pd.Series(dtype=str)).isin(["BLENDED", "COMPARABLE"])
        if authorized.any() and (pd.to_numeric(comp.loc[authorized, "comparable_count"], errors="coerce") < 3).any():
            failures.append("insufficient_comparable_count")

    if matches.empty:
        failures.append("comparable_matches_empty")
    else:
        if not {"target_product", "comparable_product", "match_distance", "comparable_weight", "decision_cutoff"}.issubset(matches.columns):
            failures.append("comparable_match_contract_incomplete")
        weights = pd.to_numeric(matches.get("comparable_weight"), errors="coerce")
        if weights.isna().any() or (weights < 0).any() or (weights > 1).any():
            failures.append("invalid_comparable_weights")

    for key in [
        "direct_method_authorized", "comparable_transfer_method_authorized",
        "candidate_methodology_change_authorized", "production_projection_authorized",
        "purchase_recommendation_authorized", "automatic_model_update_allowed",
        "technical_freeze_authorized", "uip_acceptance_authorized",
    ]:
        if summary.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")
    if summary.get("owner_review_required") is not True:
        failures.append("owner_review_gate_missing")

    result = {
        "audit_name": "Collector 365-Day Direct and Comparable Transfer Tournament Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
