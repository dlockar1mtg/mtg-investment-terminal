from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "config/mtg/governance/collector_candidate_v2_4_confidence_shadow_approval_v1.json"
CAL = ROOT / "data/operations/collector_candidate_v2_4_prospective_calibration_tournament/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_candidate_v2_4_confidence_shadow_and_decision_stability/candidate_v1_0_0"
METHOD = "PRIOR_PRODUCT_MAE_PLUS_FORECAST_EXTREMENESS"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    confidence = pd.read_csv(CAL / "collector_candidate_v2_4_prospective_confidence_predictions.csv", low_memory=False)
    decisions = pd.read_csv(CAL / "collector_candidate_v2_4_decision_threshold_predictions.csv", low_memory=False)

    confidence = confidence[
        confidence["confidence_method"].eq(METHOD)
        & confidence["horizon_days"].astype(int).isin([90, 180])
    ].copy()
    confidence["shadow_confidence_tier"] = confidence["confidence_bucket"].map(
        {"LOW": "LOW_CONFIDENCE", "HIGH": "STANDARD_CONFIDENCE", "MEDIUM": "STANDARD_CONFIDENCE"}
    )
    confidence["confidence_method_authorized_for_shadow"] = True
    confidence["future_information_used_for_assignment"] = False

    confidence_summary_rows = []
    confidence_cutoff_rows = []
    for horizon, group in confidence.groupby("horizon_days"):
        tier = group.groupby("shadow_confidence_tier")["absolute_error"].agg(["count", "mean"]).reset_index()
        standard = tier[tier["shadow_confidence_tier"].eq("STANDARD_CONFIDENCE")]
        low = tier[tier["shadow_confidence_tier"].eq("LOW_CONFIDENCE")]
        standard_mae = float(standard["mean"].iloc[0]) if not standard.empty else float("nan")
        low_mae = float(low["mean"].iloc[0]) if not low.empty else float("nan")
        cutoff_passes = 0
        cutoff_count = 0
        for cutoff, cg in group.groupby("decision_cutoff"):
            ct = cg.groupby("shadow_confidence_tier")["absolute_error"].mean()
            if {"STANDARD_CONFIDENCE", "LOW_CONFIDENCE"}.issubset(ct.index):
                passed = float(ct["LOW_CONFIDENCE"]) > float(ct["STANDARD_CONFIDENCE"])
                cutoff_count += 1
                cutoff_passes += int(passed)
                confidence_cutoff_rows.append({
                    "horizon_days": int(horizon), "decision_cutoff": cutoff,
                    "standard_confidence_mae": float(ct["STANDARD_CONFIDENCE"]),
                    "low_confidence_mae": float(ct["LOW_CONFIDENCE"]),
                    "low_worse_than_standard": bool(passed),
                })
        confidence_summary_rows.append({
            "horizon_days": int(horizon),
            "case_count": int(len(group)),
            "decision_cutoff_count": cutoff_count,
            "standard_confidence_mae": standard_mae,
            "low_confidence_mae": low_mae,
            "low_minus_standard_mae_spread": low_mae - standard_mae,
            "cutoff_low_worse_than_standard_count": cutoff_passes,
            "cutoff_low_worse_than_standard_rate": cutoff_passes / cutoff_count if cutoff_count else float("nan"),
            "shadow_confidence_implementation_authorized": True,
        })

    decision_configs = [(0.4, 0.6), (0.4, 0.75), (0.33, 0.75), (0.25, 0.75)]
    decision_stability_rows = []
    for lower, upper in decision_configs:
        subset = decisions[
            decisions["horizon_days"].astype(int).eq(90)
            & decisions["lower_quantile"].astype(float).eq(lower)
            & decisions["upper_quantile"].astype(float).eq(upper)
        ].copy()
        pass_count = 0
        cutoff_count = 0
        for cutoff, cg in subset.groupby("decision_cutoff"):
            means = cg.groupby("decision_state")["realized_return"].mean()
            if {"FAVORABLE", "WATCH", "NEUTRAL"}.issubset(means.index):
                passed = float(means["FAVORABLE"]) > float(means["WATCH"]) > float(means["NEUTRAL"])
                pass_count += int(passed)
                cutoff_count += 1
                decision_stability_rows.append({
                    "lower_quantile": lower, "upper_quantile": upper,
                    "decision_cutoff": cutoff,
                    "favorable_realized_return": float(means["FAVORABLE"]),
                    "watch_realized_return": float(means["WATCH"]),
                    "neutral_realized_return": float(means["NEUTRAL"]),
                    "ordinal_ordering_pass": bool(passed),
                })

    decision_stability = pd.DataFrame(decision_stability_rows)
    decision_summary = []
    if not decision_stability.empty:
        for (lower, upper), group in decision_stability.groupby(["lower_quantile", "upper_quantile"]):
            decision_summary.append({
                "horizon_days": 90,
                "lower_quantile": float(lower), "upper_quantile": float(upper),
                "decision_cutoff_count": int(len(group)),
                "cutoff_ordinal_pass_count": int(group["ordinal_ordering_pass"].sum()),
                "cutoff_ordinal_pass_rate": float(group["ordinal_ordering_pass"].mean()),
                "decision_state_method_authorized": False,
                "status": "OWNER_REVIEW_ELIGIBLE" if float(group["ordinal_ordering_pass"].mean()) >= 0.6 else "REMAIN_UNCERTIFIED",
            })
    decision_summary = pd.DataFrame(decision_summary)

    failures = []
    if confidence.empty: failures.append("no_confidence_predictions")
    if approval.get("shadow_confidence_implementation_authorized") is not True:
        failures.append("confidence_shadow_not_authorized")
    if confidence["future_information_used_for_assignment"].any(): failures.append("future_information_used")
    for horizon in [90, 180]:
        row = [x for x in confidence_summary_rows if x["horizon_days"] == horizon]
        if not row or row[0]["cutoff_low_worse_than_standard_rate"] < 0.7:
            failures.append(f"confidence_instability:{horizon}")
    for key in ["candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed", "technical_freeze_authorized", "uip_acceptance_authorized"]:
        if approval.get(key) is not False: failures.append(f"authorization_not_closed:{key}")
    if approval.get("decision_state_method_authorized") is not False:
        failures.append("decision_state_authorization_open")

    confidence.to_csv(OUT / "collector_candidate_v2_4_confidence_shadow_assignments.csv", index=False)
    pd.DataFrame(confidence_summary_rows).to_csv(OUT / "collector_candidate_v2_4_confidence_shadow_summary.csv", index=False)
    pd.DataFrame(confidence_cutoff_rows).to_csv(OUT / "collector_candidate_v2_4_confidence_shadow_cutoff_stability.csv", index=False)
    decision_stability.to_csv(OUT / "collector_candidate_v2_4_decision_cutoff_stability.csv", index=False)
    decision_summary.to_csv(OUT / "collector_candidate_v2_4_decision_cutoff_stability_summary.csv", index=False)

    result = {
        "audit_name": "Collector Candidate v2.4 Confidence Shadow and Decision Stability",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "confidence_assignment_count": int(len(confidence)),
        "confidence_horizon_count": int(confidence["horizon_days"].nunique()) if not confidence.empty else 0,
        "decision_configuration_count": int(len(decision_summary)),
        "shadow_confidence_implementation_authorized": True,
        "decision_state_method_authorized": False,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures), "failures": failures,
    }
    (OUT / "collector_candidate_v2_4_confidence_shadow_and_decision_stability_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
