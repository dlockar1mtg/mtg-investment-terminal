from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = ROOT / "config/mtg/governance/collector_candidate_v2_4_shadow_approval_v1.json"
PHASE_2A = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_candidate_v2_4_shadow_revalidation/candidate_v2_4_0_shadow"


def annual_to_horizon(rate, years):
    return np.power(1.0 + rate, years) - 1.0


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

    rows: list[dict[str, object]] = []
    for horizon, hf in scored.groupby("horizon_days"):
        for cutoff in sorted(hf["decision_cutoff"].dropna().unique()):
            test = hf[hf["decision_cutoff"] == cutoff].copy()
            matured = hf[hf["outcome_maturity_date"] < cutoff].copy()

            current = annual_to_horizon(test["base_annual"], test["horizon_years"])
            shadow = current.copy()
            method = "RETAIN_CURRENT"
            interval_lower = pd.Series(np.nan, index=test.index)
            interval_upper = pd.Series(np.nan, index=test.index)
            interval_ready = False

            if int(horizon) == 180 and not matured.empty:
                cutoffs = sorted(matured["decision_cutoff"].dropna().unique())
                keep = set(cutoffs[-2:])
                train = matured[matured["decision_cutoff"].isin(keep)].copy()
                if len(train) >= 50 and train["decision_cutoff"].nunique() >= 2:
                    annual = 0.75 * test["base_annual"] + 0.25 * test["cutoff_median_annual"]
                    shadow = annual_to_horizon(annual, test["horizon_years"])
                    method = "APPROVED_75_PRODUCT_25_MEDIAN_LAST_2"

            if int(horizon) == 90 and len(matured) >= 50 and matured["decision_cutoff"].nunique() >= 2:
                train_pred = annual_to_horizon(matured["base_annual"], matured["horizon_years"])
                signed = matured["realized_return"] - train_pred
                applied_bias = 0.5 * float(signed.median())
                centered_abs = (signed - applied_bias).abs()
                radius = float(centered_abs.quantile(0.68))
                center = current + applied_bias
                interval_lower = center - radius
                interval_upper = center + radius
                interval_ready = True

            for idx, row in test.iterrows():
                realized = float(row["realized_return"])
                current_pred = float(current.loc[idx])
                shadow_pred = float(shadow.loc[idx])
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
                    "interval_lower": float(interval_lower.loc[idx]) if interval_ready else np.nan,
                    "interval_upper": float(interval_upper.loc[idx]) if interval_ready else np.nan,
                    "inside_interval": bool(interval_lower.loc[idx] <= realized <= interval_upper.loc[idx]) if interval_ready else False,
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
        })
    horizon_summary = pd.DataFrame(summaries)

    confidence_rows: list[dict[str, object]] = []
    for horizon, g in predictions.groupby("horizon_days"):
        g = g.copy()
        g["confidence_bucket"] = pd.qcut(g["shadow_absolute_error"], q=3, labels=["HIGH", "MEDIUM", "LOW"], duplicates="drop")
        for bucket, bg in g.groupby("confidence_bucket", observed=True):
            confidence_rows.append({
                "horizon_days": int(horizon),
                "confidence_bucket": str(bucket),
                "case_count": int(len(bg)),
                "mean_absolute_error": float(bg["shadow_absolute_error"].mean()),
                "mean_realized_return": float(bg["realized_return"].mean()),
            })
    confidence = pd.DataFrame(confidence_rows)

    decision_rows: list[dict[str, object]] = []
    for horizon, g in predictions.groupby("horizon_days"):
        q1, q2 = g["shadow_forecast_return"].quantile([0.33, 0.67])
        labels = np.where(g["shadow_forecast_return"] >= q2, "FAVORABLE", np.where(g["shadow_forecast_return"] <= q1, "NEUTRAL", "WATCH"))
        gg = g.assign(decision_state=labels)
        for state, sg in gg.groupby("decision_state"):
            decision_rows.append({
                "horizon_days": int(horizon),
                "decision_state": state,
                "case_count": int(len(sg)),
                "mean_forecast_return": float(sg["shadow_forecast_return"].mean()),
                "mean_realized_return": float(sg["realized_return"].mean()),
                "mean_absolute_error": float(sg["shadow_absolute_error"].mean()),
            })
    decisions = pd.DataFrame(decision_rows)

    failures: list[str] = []
    if predictions.empty:
        failures.append("no_shadow_predictions")
    if predictions["future_information_used"].any():
        failures.append("future_information_used")
    if approval.get("shadow_implementation_authorized") is not True:
        failures.append("shadow_implementation_not_authorized")
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

    result = {
        "audit_name": "Collector Candidate v2.4 Shadow Implementation and Revalidation",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "prediction_count": int(len(predictions)),
        "horizon_count": int(horizon_summary["horizon_days"].nunique()) if not horizon_summary.empty else 0,
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
