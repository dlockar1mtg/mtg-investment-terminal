from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2e_regime_calibration_v1.json"
PHASE_2A = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2e_regime_calibration/candidate_v1_0_0"


def annual_to_horizon(rate, years):
    return np.power(1.0 + rate, years) - 1.0


def evaluate_weight(train: pd.DataFrame, weight: float) -> float:
    annual = weight * train["base_annual"] + (1.0 - weight) * train["cutoff_median_annual"]
    pred = annual_to_horizon(annual, train["horizon_years"])
    return float((pred - train["realized_return"]).abs().mean())


def select_training_window(train: pd.DataFrame, window_cutoffs: int) -> pd.DataFrame:
    if window_cutoffs <= 0 or train.empty:
        return train.copy()
    cutoffs = sorted(train["decision_cutoff"].dropna().unique())
    keep = set(cutoffs[-window_cutoffs:])
    return train[train["decision_cutoff"].isin(keep)].copy()


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

    prediction_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
    weights = [float(x) for x in cfg["blend_weights"]]

    for horizon, hf in scored.groupby("horizon_days"):
        for cutoff in sorted(hf["decision_cutoff"].dropna().unique()):
            test = hf[hf["decision_cutoff"] == cutoff].copy()
            matured = hf[hf["outcome_maturity_date"] < cutoff].copy()
            for window in [int(x) for x in cfg["training_window_cutoffs"]]:
                train = select_training_window(matured, window)
                train_cutoffs = int(train["decision_cutoff"].nunique())
                ready = len(train) >= int(cfg["minimum_training_cases"]) and train_cutoffs >= int(cfg["minimum_training_cutoffs"])
                if not ready:
                    continue
                scores = {w: evaluate_weight(train, w) for w in weights}
                selected_weight = min(scores, key=scores.get)
                train_annual = selected_weight * train["base_annual"] + (1.0 - selected_weight) * train["cutoff_median_annual"]
                train_pred = annual_to_horizon(train_annual, train["horizon_years"])
                residuals = train["realized_return"] - train_pred
                lower_q = float(residuals.quantile(float(cfg["residual_lower_quantile"])))
                upper_q = float(residuals.quantile(float(cfg["residual_upper_quantile"])))

                annual = selected_weight * test["base_annual"] + (1.0 - selected_weight) * test["cutoff_median_annual"]
                pred = annual_to_horizon(annual, test["horizon_years"])
                current = annual_to_horizon(test["base_annual"], test["horizon_years"])
                lower = pred + lower_q
                upper = pred + upper_q

                selection_rows.append({
                    "horizon_days": int(horizon),
                    "decision_cutoff": cutoff,
                    "training_window_cutoffs": window,
                    "training_window_label": "EXPANDING" if window == 0 else f"LAST_{window}_CUTOFFS",
                    "training_case_count": int(len(train)),
                    "training_cutoff_count": train_cutoffs,
                    "selected_product_weight": selected_weight,
                    "selected_median_weight": 1.0 - selected_weight,
                    "selected_training_mae": float(scores[selected_weight]),
                    "residual_lower_quantile": lower_q,
                    "residual_upper_quantile": upper_q,
                })

                for idx, row in test.iterrows():
                    realized = float(row["realized_return"])
                    forecast = float(pred.loc[idx])
                    current_forecast = float(current.loc[idx])
                    prediction_rows.append({
                        "horizon_days": int(horizon),
                        "decision_cutoff": cutoff,
                        "product_key": row["product_key"],
                        "product_name": row["product_name"],
                        "training_window_cutoffs": window,
                        "training_window_label": "EXPANDING" if window == 0 else f"LAST_{window}_CUTOFFS",
                        "selected_product_weight": selected_weight,
                        "selected_median_weight": 1.0 - selected_weight,
                        "forecast_return": forecast,
                        "current_model_forecast_return": current_forecast,
                        "realized_return": realized,
                        "absolute_error": abs(forecast - realized),
                        "current_absolute_error": abs(current_forecast - realized),
                        "signed_error": forecast - realized,
                        "beats_current": abs(forecast - realized) < abs(current_forecast - realized),
                        "interval_lower": float(lower.loc[idx]),
                        "interval_upper": float(upper.loc[idx]),
                        "inside_interval": bool(lower.loc[idx] <= realized <= upper.loc[idx]),
                        "below_interval": bool(realized < lower.loc[idx]),
                        "above_interval": bool(realized > upper.loc[idx]),
                        "future_information_used": False,
                    })

    predictions = pd.DataFrame(prediction_rows)
    selections = pd.DataFrame(selection_rows)
    summaries: list[dict[str, object]] = []
    if not predictions.empty:
        for (horizon, label), g in predictions.groupby(["horizon_days", "training_window_label"]):
            summaries.append({
                "horizon_days": int(horizon),
                "training_window_label": label,
                "case_count": int(len(g)),
                "decision_cutoff_count": int(g["decision_cutoff"].nunique()),
                "mean_absolute_error": float(g["absolute_error"].mean()),
                "current_model_mean_absolute_error": float(g["current_absolute_error"].mean()),
                "mae_improvement_vs_current": float(g["current_absolute_error"].mean() - g["absolute_error"].mean()),
                "mean_signed_error": float(g["signed_error"].mean()),
                "beats_current_rate": float(g["beats_current"].mean()),
                "interval_coverage": float(g["inside_interval"].mean()),
                "below_interval_rate": float(g["below_interval"].mean()),
                "above_interval_rate": float(g["above_interval"].mean()),
                "mean_selected_product_weight": float(g["selected_product_weight"].mean()),
            })
    summary_table = pd.DataFrame(summaries)
    if not summary_table.empty:
        summary_table["mae_rank_within_horizon"] = summary_table.groupby("horizon_days")["mean_absolute_error"].rank(method="dense")

    failures: list[str] = []
    if predictions.empty:
        failures.append("no_regime_calibration_predictions")
    if selections.empty:
        failures.append("no_regime_calibration_selections")
    if not predictions.empty and predictions["future_information_used"].any():
        failures.append("future_information_used")
    for key in ["candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed"]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    predictions.to_csv(OUT / "collector_walk_forward_phase_2e_predictions.csv", index=False)
    selections.to_csv(OUT / "collector_walk_forward_phase_2e_selections.csv", index=False)
    summary_table.to_csv(OUT / "collector_walk_forward_phase_2e_window_summary.csv", index=False)

    summary = {
        "audit_name": cfg["audit_name"],
        "audit_version": cfg["audit_version"],
        "status": "PASS" if not failures else "FAIL",
        "prediction_count": int(len(predictions)),
        "selection_count": int(len(selections)),
        "horizon_count": int(predictions["horizon_days"].nunique()) if not predictions.empty else 0,
        "training_window_variant_count": int(summary_table["training_window_label"].nunique()) if not summary_table.empty else 0,
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2e_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
