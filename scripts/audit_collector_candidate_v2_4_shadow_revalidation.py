from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_v2_4_shadow_revalidation/candidate_v2_4_0_shadow"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    required = [
        "collector_candidate_v2_4_shadow_predictions.csv",
        "collector_candidate_v2_4_shadow_horizon_summary.csv",
        "collector_candidate_v2_4_shadow_confidence_review.csv",
        "collector_candidate_v2_4_shadow_decision_state_review.csv",
        "collector_candidate_v2_4_shadow_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists():
            failures.append(f"missing_output:{name}")

    if not failures:
        summary = json.loads((OUT / "collector_candidate_v2_4_shadow_summary.json").read_text(encoding="utf-8"))
        pred = pd.read_csv(OUT / "collector_candidate_v2_4_shadow_predictions.csv", low_memory=False)
        horizons = pd.read_csv(OUT / "collector_candidate_v2_4_shadow_horizon_summary.csv", low_memory=False)
        if summary.get("status") != "PASS": failures.append("builder_status_not_pass")
        if pred.empty: failures.append("predictions_empty")
        if horizons.empty: failures.append("horizon_summary_empty")
        if pred["future_information_used"].astype(str).str.lower().eq("true").any(): failures.append("future_information_used")
        if 90 in set(horizons["horizon_days"].astype(int)):
            g90 = pred[pred["horizon_days"].astype(int) == 90]
            if not (g90["shadow_forecast_return"] == g90["current_forecast_return"]).all():
                failures.append("90_day_point_forecast_changed")
        if 365 in set(horizons["horizon_days"].astype(int)):
            g365 = pred[pred["horizon_days"].astype(int) == 365]
            if not (g365["shadow_forecast_return"] == g365["current_forecast_return"]).all():
                failures.append("365_day_methodology_changed")
        if 180 in set(horizons["horizon_days"].astype(int)):
            g180 = pred[pred["horizon_days"].astype(int) == 180]
            if not g180["shadow_method"].astype(str).str.contains("APPROVED_75_PRODUCT_25_MEDIAN").any():
                failures.append("approved_180_day_shadow_method_missing")
        for key in [
            "candidate_methodology_change_authorized",
            "production_projection_authorized",
            "purchase_recommendation_authorized",
            "automatic_model_update_allowed",
            "technical_freeze_authorized",
            "uip_acceptance_authorized",
        ]:
            if summary.get(key) is not False: failures.append(f"authorization_not_closed:{key}")
        if summary.get("shadow_implementation_authorized") is not True:
            failures.append("shadow_implementation_not_authorized")

    result = {
        "audit_name": "Collector Candidate v2.4 Shadow Revalidation Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
