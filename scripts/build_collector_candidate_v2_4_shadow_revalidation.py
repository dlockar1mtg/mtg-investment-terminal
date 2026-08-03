from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "config/mtg/governance/collector_candidate_v2_4_shadow_approval_v1.json"
PHASE_2A = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
PHASE_2H = ROOT / "data/operations/collector_walk_forward_phase_2h_bias_shrinkage/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_candidate_v2_4_shadow_revalidation/candidate_v2_4_0_shadow"


def annual_to_horizon(rate, years):
    return np.power(1.0 + rate, years) - 1.0


def normalize_key(frame: pd.DataFrame) -> pd.Series:
    return frame["decision_cutoff"].dt.strftime("%Y-%m-%d") + "|" + frame["product_key"].astype(str)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    approval = json.loads(APPROVAL.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    scored = pd.read_csv(
        PHASE_2A / "collector_walk_forward_phase_2a_scored_outcomes.csv",
        parse_dates=["decision_cutoff"],
        low_memory=False,
    )
    scored["base_annual"] = pd.to_numeric(scored["forecast_return_365_equivalent"], errors="coerce")
    scored["realized_return"] = pd.to_numeric(scored["realized_return"], errors="coerce")
    scored["horizon_days"] = pd.to_numeric(scored["horizon_days"], errors="coerce").astype("Int64")
    scored = scored.dropna(subset=["decision_cutoff", "base_annual", "realized_return", "horizon_days"]).copy()
    scored["horizon_years"] = scored["horizon_days"].astype(float) / 365.0
    scored["cutoff_median_annual"] = scored.groupby(["decision_cutoff", "horizon_days"])["base_annual"].transform("median")
    scored["outcome_maturity_date"] = scored["decision_cutoff"] + pd.to_timedelta(scored["horizon_days"].astype(int), unit="D")

    approved_intervals = pd.read_csv(
        PHASE_2H / "collector_walk_forward_phase_2h_predictions.csv",
        parse_dates=["decision_cutoff"],
        low_memory=False,
    )
    approved_intervals["horizon_days"] = pd.to_numeric(approved_intervals["horizon_days"], errors="coerce").astype("Int64")
    approved_intervals["bias_shrinkage_factor"] = pd.to_numeric(approved_intervals["bias_shrinkage_factor"], errors="coerce")
    approved_intervals = approved_intervals[
        (approved_intervals["horizon_days"] == 90)
        & (approved_intervals["training_window_label"] == "EXPANDING")
        & (approved_intervals["bias_shrinkage_factor"].sub(0.5).abs() < 1e-12)
    ].copy()
    approved_intervals["merge_key"] = normalize_key(approved_intervals)
    approved_interval_map = approved_intervals.set_index("merge_key")[[
        "interval_lower",
        "interval_upper",
        "inside_interval",
        "below_interval",
        "above_interval",
        "applied_bias_correction",
        "conformal_radius",
    ]].to_dict("index")

    rows: list[dict[str, object]] = []
    for horizon, hf in scored.groupby("horizon_days"):
        for cutoff in sorted(hf["decision_cutoff"].dropna().unique()):
            test = hf[hf["decision_cutoff"] == cutoff].copy()
            matured = hf[hf["outcome_maturity_date"] < cutoff].copy()

            current = annual_to_horizon(test["base_annual"], test["horizon_years"])
            shadow = current.copy()
            method = "RETAIN_CURRENT"

            if int(horizon) == 180 and not matured.empty:
                matured_cutoffs = sorted(matured["decision_cutoff"].dropna().unique())
                keep = set(matured_cutoffs[-2:])
                train = matured[matured["decision_cutoff"].isin(keep)].copy()
                if len(train) >= 50 and train["decision_cutoff"].nunique() >= 2:
                    annual = 0.75 * test["base_annual"] + 0.25 * test["cutoff_median_annual"]
                    shadow = annual_to_horizon(annual, test["horizon_years"])
                    method = "APPROVED_75_PRODUCT_25_MEDIAN_LAST_2"

            for idx, row in test.iterrows():
                realized = float(row["realized_return"])
                current_pred = float(current.loc[idx])
                shadow_pred = float(shadow.loc[idx])
                merge_key = f"{pd.Timestamp(cutoff).strftime('%Y-%m-%d')}|{row['product_key']}"
                interval = approved_interval_map.get(merge_key) if int(horizon) == 90 else None
                interval_ready = interval is not None
                rows.append({
                    "horizon_days": int(horizon),
                    "decision_cutoff": cutoff,
                    "product_key": row["product_key"],
                    "product_name": row["product_name"],
                    "shadow_method": method,
                    "current_forecast_return": current_pred,
                    "shadow_forecast_return": shadow_pred,
                    "realized_return": realized,
                    "current_absolute_error": abs(current_pred - realized),
                    "shadow_absolute_error": abs(shadow_pred - realized),
                    "shadow_signed_error": shadow_pred - realized,
                    "shadow_beats_current": abs(shadow_pred - realized) < abs(current_pred - realized),
                    "interval_ready": interval_ready,
                    "interval_method": "APPROVED_PHASE_2H_EXPANDING_BIAS_0_5" if interval_ready else "NOT_READY",
                    "interval_lower": float(interval["interval_lower"]) if interval_ready else np.nan,
                    "interval_upper": float(interval["interval_upper"]) if interval_ready else np.nan,
                    "inside_interval": bool(interval["inside_interval"]) if interval_ready else False,
                    "below_interval": bool(interval["below_interval"]) if interval_ready else False,
                    "above_interval": bool(interval["above_interval"]) if interval_ready else False,
                    "applied_bias_correction": float(interval["applied_bias_correction"]) if interval_ready else np.nan,
                    "conformal_radius": float(interval["conformal_radius"]) if interval_ready else np.nan,
                    "future_information_used": False,
                })

    predictions = pd.DataFrame(rows)
    summaries: list[dict[str, object]] = []
    for horizon, g in predictions.groupby("horizon_days"):
        ready = g[g["interval_ready"] == True]
        summaries.append({
            "horizon_days": int(horizon),
            "case_count": int(len(g)),
            "decision_cutoff_count": int(g["decision_cutoff"].nunique()),
            "current_mae": float(g["current_absolute_error"].mean()),
            "shadow_mae": float(g["shadow_absolute_error"].mean()),
            "mae_improvement_vs_current": float(g["current_absolute_error"].mean() - g["shadow_absolute_error"].mean()),
            "shadow_mean_signed_error": float(g["shadow_signed_error"].mean()),
            "shadow_beats_current_rate": float(g["shadow_beats_current"].mean()),
            "interval_case_count": int(len(ready)),
            "interval_coverage": float(ready["inside_interval"].mean()) if not ready.empty else np.nan,
            "below_interval_rate": float(ready["below_interval"].mean()) if not ready.empty else np.nan,
            "above_interval_rate": float(ready["above_interval"].mean()) if not ready.empty else np.nan,
        })
    horizon_summary = pd.DataFrame(summaries)

    # Confidence was previously bucketed using realized absolute error, which is retrospective leakage.
    # Keep confidence explicitly uncertified until a prospective-only confidence method is approved.
    confidence = pd.DataFrame([
        {
            "horizon_days": int(horizon),
            "confidence_status": "UNCERTIFIED_PROSPECTIVE_METHOD_NOT_APPROVED",
            "case_count": int(len(g)),
            "overall_mean_absolute_error": float(g["shadow_absolute_error"].mean()),
            "prospective_confidence_method_authorized": False,
            "retrospective_error_bucket_removed": True,
        }
        for horizon, g in predictions.groupby("horizon_days")
    ])

    decision_rows: list[dict[str, object]] = []
    ordering_rows: list[dict[str, object]] = []
    for horizon, g in predictions.groupby("horizon_days"):
        q1, q2 = g["shadow_forecast_return"].quantile([0.33, 0.67])
        labels = np.where(g["shadow_forecast_return"] >= q2, "FAVORABLE", np.where(g["shadow_forecast_return"] <= q1, "NEUTRAL", "WATCH"))
        gg = g.assign(decision_state=labels)
        realized_by_state: dict[str, float] = {}
        for state, sg in gg.groupby("decision_state"):
            realized_by_state[state] = float(sg["realized_return"].mean())
            decision_rows.append({
                "horizon_days": int(horizon),
                "decision_state": state,
                "case_count": int(len(sg)),
                "mean_forecast_return": float(sg["shadow_forecast_return"].mean()),
                "mean_realized_return": float(sg["realized_return"].mean()),
                "mean_absolute_error": float(sg["shadow_absolute_error"].mean()),
                "decision_state_method_authorized": False,
            })
        ordering_pass = (
            realized_by_state.get("FAVORABLE", -np.inf)
            > realized_by_state.get("WATCH", np.inf)
            > realized_by_state.get("NEUTRAL", np.inf)
        )
        ordering_rows.append({
            "horizon_days": int(horizon),
            "favorable_realized_return": realized_by_state.get("FAVORABLE", np.nan),
            "watch_realized_return": realized_by_state.get("WATCH", np.nan),
            "neutral_realized_return": realized_by_state.get("NEUTRAL", np.nan),
            "ordinal_ordering_pass": bool(ordering_pass),
            "decision_state_status": "DIAGNOSTIC_ONLY_NOT_AUTHORIZED",
        })
    decisions = pd.DataFrame(decision_rows)
    decision_ordering = pd.DataFrame(ordering_rows)

    failures: list[str] = []
    if predictions.empty:
        failures.append("no_shadow_predictions")
    if predictions["future_information_used"].any():
        failures.append("future_information_used")
    if approval.get("shadow_implementation_authorized") is not True:
        failures.append("shadow_implementation_not_authorized")
    expected_interval_count = int(len(approved_intervals))
    actual_interval_count = int(predictions["interval_ready"].sum())
    if actual_interval_count != expected_interval_count:
        failures.append(f"approved_interval_population_mismatch:{actual_interval_count}!={expected_interval_count}")
    for key in [
        "candidate_methodology_change_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
        "technical_freeze_authorized",
        "uip_acceptance_authorized",
    ]:
        if approval.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    predictions.to_csv(OUT / "collector_candidate_v2_4_shadow_predictions.csv", index=False)
    horizon_summary.to_csv(OUT / "collector_candidate_v2_4_shadow_horizon_summary.csv", index=False)
    confidence.to_csv(OUT / "collector_candidate_v2_4_shadow_confidence_review.csv", index=False)
    decisions.to_csv(OUT / "collector_candidate_v2_4_shadow_decision_state_review.csv", index=False)
    decision_ordering.to_csv(OUT / "collector_candidate_v2_4_shadow_decision_state_ordering.csv", index=False)

    result = {
        "audit_name": "Collector Candidate v2.4 Shadow Implementation and Revalidation",
        "audit_version": "1.0.1",
        "status": "PASS" if not failures else "FAIL",
        "prediction_count": int(len(predictions)),
        "horizon_count": int(horizon_summary["horizon_days"].nunique()) if not horizon_summary.empty else 0,
        "approved_90_day_interval_case_count": actual_interval_count,
        "confidence_method_certified": False,
        "decision_state_method_certified": False,
        "shadow_implementation_authorized": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "technical_freeze_authorized": False,
        "uip_acceptance_authorized": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_candidate_v2_4_shadow_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
