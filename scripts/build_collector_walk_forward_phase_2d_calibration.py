from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2d_calibration_v1.json"
PHASE_2A = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2d_calibration/candidate_v1_0_0"


def annual_to_horizon(rate: pd.Series | float, years: pd.Series | float):
    return np.power(1.0 + rate, years) - 1.0


def evaluate_weight(train: pd.DataFrame, weight: float) -> float:
    annual = weight * train["base_annual"] + (1.0 - weight) * train["cutoff_median_annual"]
    pred = annual_to_horizon(annual, train["horizon_years"])
    return float((pred - train["realized_return"]).abs().mean())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
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

    weights = [float(x) for x in cfg["blend_weights"]]
    oos_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []

    for horizon, horizon_frame in scored.groupby("horizon_days"):
        cutoffs = sorted(horizon_frame["decision_cutoff"].dropna().unique())
        for cutoff in cutoffs:
            test = horizon_frame[horizon_frame["decision_cutoff"] == cutoff].copy()
            train = horizon_frame[horizon_frame["outcome_maturity_date"] < cutoff].copy()
            train_cutoffs = int(train["decision_cutoff"].nunique())
            training_ready = len(train) >= int(cfg["minimum_training_cases"]) and train_cutoffs >= int(cfg["minimum_training_cutoffs"])
            if training_ready:
                scores = {weight: evaluate_weight(train, weight) for weight in weights}
                selected_weight = min(scores, key=scores.get)
                train_mae = float(scores[selected_weight])
            else:
                selected_weight = float(cfg["fallback_product_weight"])
                train_mae = np.nan

            train_annual = selected_weight * train["base_annual"] + (1.0 - selected_weight) * train["cutoff_median_annual"]
            train_pred = annual_to_horizon(train_annual, train["horizon_years"])
            residuals = train["realized_return"] - train_pred
            lower_q = float(residuals.quantile(float(cfg["residual_lower_quantile"]))) if training_ready and not residuals.empty else np.nan
            upper_q = float(residuals.quantile(float(cfg["residual_upper_quantile"]))) if training_ready and not residuals.empty else np.nan

            selection_rows.append({
                "horizon_days": int(horizon),
                "decision_cutoff": cutoff,
                "training_case_count": int(len(train)),
                "training_cutoff_count": train_cutoffs,
                "training_ready": bool(training_ready),
                "selected_product_weight": selected_weight,
                "selected_median_weight": 1.0 - selected_weight,
                "selected_training_mae": train_mae,
                "residual_lower_quantile": lower_q,
                "residual_upper_quantile": upper_q,
            })

            annual = selected_weight * test["base_annual"] + (1.0 - selected_weight) * test["cutoff_median_annual"]
            pred = annual_to_horizon(annual, test["horizon_years"])
            current = annual_to_horizon(test["base_annual"], test["horizon_years"])
            lower = pred + lower_q if training_ready else np.nan
            upper = pred + upper_q if training_ready else np.nan
            for idx, row in test.iterrows():
                realized = float(row["realized_return"])
                forecast = float(pred.loc[idx])
                current_forecast = float(current.loc[idx])
                oos_rows.append({
                    "horizon_days": int(horizon),
                    "decision_cutoff": cutoff,
                    "product_key": row["product_key"],
                    "product_name": row["product_name"],
                    "training_ready": bool(training_ready),
                    "selected_product_weight": selected_weight,
                    "selected_median_weight": 1.0 - selected_weight,
                    "oos_forecast_return": forecast,
                    "current_model_forecast_return": current_forecast,
                    "realized_return": realized,
                    "oos_signed_error": forecast - realized,
                    "oos_absolute_error": abs(forecast - realized),
                    "current_absolute_error": abs(current_forecast - realized),
                    "oos_beats_current": abs(forecast - realized) < abs(current_forecast - realized),
                    "interval_lower": float(lower.loc[idx]) if training_ready else np.nan,
                    "interval_upper": float(upper.loc[idx]) if training_ready else np.nan,
                    "inside_empirical_interval": bool(lower.loc[idx] <= realized <= upper.loc[idx]) if training_ready else False,
                    "future_information_used": False,
                })

    oos = pd.DataFrame(oos_rows)
    selections = pd.DataFrame(selection_rows)
    ready = oos[oos["training_ready"] == True].copy()

    summaries: list[dict[str, object]] = []
    for horizon, group in ready.groupby("horizon_days"):
        summaries.append({
            "horizon_days": int(horizon),
            "oos_case_count": int(len(group)),
            "decision_cutoff_count": int(group["decision_cutoff"].nunique()),
            "oos_mean_absolute_error": float(group["oos_absolute_error"].mean()),
            "current_model_mean_absolute_error": float(group["current_absolute_error"].mean()),
            "mae_improvement_vs_current": float(group["current_absolute_error"].mean() - group["oos_absolute_error"].mean()),
            "oos_mean_signed_error": float(group["oos_signed_error"].mean()),
            "oos_beats_current_rate": float(group["oos_beats_current"].mean()),
            "empirical_interval_coverage": float(group["inside_empirical_interval"].mean()),
            "mean_selected_product_weight": float(group["selected_product_weight"].mean()),
        })
    horizon_summary = pd.DataFrame(summaries)

    failures: list[str] = []
    if oos.empty:
        failures.append("no_oos_rows")
    if selections.empty:
        failures.append("no_weight_selections")
    if ready.empty:
        failures.append("no_training_ready_oos_rows")
    if not oos.empty and oos["future_information_used"].any():
        failures.append("future_information_used")
    for key in ["candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed"]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    oos.to_csv(OUT / "collector_walk_forward_phase_2d_oos_predictions.csv", index=False)
    selections.to_csv(OUT / "collector_walk_forward_phase_2d_weight_selections.csv", index=False)
    horizon_summary.to_csv(OUT / "collector_walk_forward_phase_2d_horizon_summary.csv", index=False)

    summary = {
        "audit_name": cfg["audit_name"],
        "audit_version": cfg["audit_version"],
        "status": "PASS" if not failures else "FAIL",
        "source_scored_outcome_count": int(len(scored)),
        "oos_prediction_count": int(len(oos)),
        "training_ready_oos_count": int(len(ready)),
        "weight_selection_count": int(len(selections)),
        "horizon_count": int(horizon_summary["horizon_days"].nunique()) if not horizon_summary.empty else 0,
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2d_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
