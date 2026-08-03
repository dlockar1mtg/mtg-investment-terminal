from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2i_finalist_tournament_v1.json"
PHASE_2A = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2i_finalist_tournament/candidate_v1_0_0"


def annual_to_horizon(rate, years):
    return np.power(1.0 + rate, years) - 1.0


def select_window(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    if window <= 0 or frame.empty:
        return frame.copy()
    cutoffs = sorted(frame["decision_cutoff"].dropna().unique())
    keep = set(cutoffs[-window:])
    return frame[frame["decision_cutoff"].isin(keep)].copy()


def slice_frame(frame: pd.DataFrame, name: str) -> pd.DataFrame:
    if frame.empty or name == "FULL_SAMPLE":
        return frame.copy()
    if name in {"EARLY_HALF", "LATE_HALF"}:
        cutoffs = sorted(frame["decision_cutoff"].dropna().unique())
        midpoint = max(1, len(cutoffs) // 2)
        keep = cutoffs[:midpoint] if name == "EARLY_HALF" else cutoffs[midpoint:]
        return frame[frame["decision_cutoff"].isin(keep)].copy()
    if name == "EXCLUDE_WORST_PRODUCT":
        worst = frame.groupby("product_name")["current_absolute_error"].mean().idxmax()
        return frame[frame["product_name"] != worst].copy()
    if name == "TRIM_TOP_5_PERCENT_CURRENT_ERRORS":
        threshold = frame["current_absolute_error"].quantile(0.95)
        return frame[frame["current_absolute_error"] <= threshold].copy()
    return frame.copy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    scored = pd.read_csv(PHASE_2A / "collector_walk_forward_phase_2a_scored_outcomes.csv", parse_dates=["decision_cutoff"], low_memory=False)
    scored["base_annual"] = pd.to_numeric(scored["forecast_return_365_equivalent"], errors="coerce")
    scored["realized_return"] = pd.to_numeric(scored["realized_return"], errors="coerce")
    scored["horizon_days"] = pd.to_numeric(scored["horizon_days"], errors="coerce").astype("Int64")
    scored = scored.dropna(subset=["decision_cutoff", "base_annual", "realized_return", "horizon_days"]).copy()
    scored["horizon_years"] = scored["horizon_days"].astype(float) / 365.0
    scored["cutoff_median_annual"] = scored.groupby(["decision_cutoff", "horizon_days"])["base_annual"].transform("median")
    scored["outcome_maturity_date"] = scored["decision_cutoff"] + pd.to_timedelta(scored["horizon_days"].astype(int), unit="D")
    current_pred = annual_to_horizon(scored["base_annual"], scored["horizon_years"])
    scored["current_absolute_error"] = (current_pred - scored["realized_return"]).abs()

    predictions: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    windows = [int(x) for x in cfg["training_window_cutoffs"]]
    weights = [float(x) for x in cfg["product_weights"]]
    biases = [float(x) for x in cfg["bias_shrinkage_factors"]]
    coverages = [float(x) for x in cfg["target_coverages"]]

    for horizon, hf in scored.groupby("horizon_days"):
        for cutoff in sorted(hf["decision_cutoff"].dropna().unique()):
            test = hf[hf["decision_cutoff"] == cutoff].copy()
            matured = hf[hf["outcome_maturity_date"] < cutoff].copy()
            for window in windows:
                train = select_window(matured, window)
                train_cutoffs = int(train["decision_cutoff"].nunique())
                if len(train) < int(cfg["minimum_training_cases"]) or train_cutoffs < int(cfg["minimum_training_cutoffs"]):
                    continue
                for weight, bias_factor, target in itertools.product(weights, biases, coverages):
                    train_annual = weight * train["base_annual"] + (1.0 - weight) * train["cutoff_median_annual"]
                    train_pred = annual_to_horizon(train_annual, train["horizon_years"])
                    signed_resid = train["realized_return"] - train_pred
                    raw_bias = float(signed_resid.median())
                    applied_bias = bias_factor * raw_bias
                    centered_abs = (signed_resid - applied_bias).abs()
                    radius = float(centered_abs.quantile(target))
                    test_annual = weight * test["base_annual"] + (1.0 - weight) * test["cutoff_median_annual"]
                    forecast = annual_to_horizon(test_annual, test["horizon_years"])
                    center = forecast + applied_bias
                    lower = center - radius
                    upper = center + radius
                    label = "EXPANDING" if window == 0 else f"LAST_{window}_CUTOFFS"
                    selections.append({
                        "horizon_days": int(horizon), "decision_cutoff": cutoff,
                        "training_window_label": label, "training_case_count": int(len(train)),
                        "training_cutoff_count": train_cutoffs, "product_weight": weight,
                        "median_weight": 1.0 - weight, "bias_shrinkage_factor": bias_factor,
                        "target_coverage": target, "raw_bias": raw_bias,
                        "applied_bias": applied_bias, "conformal_radius": radius,
                    })
                    for idx, row in test.iterrows():
                        realized = float(row["realized_return"])
                        pred = float(center.loc[idx])
                        current = float(annual_to_horizon(float(row["base_annual"]), float(row["horizon_years"])))
                        predictions.append({
                            "horizon_days": int(horizon), "decision_cutoff": cutoff,
                            "product_key": row["product_key"], "product_name": row["product_name"],
                            "training_window_label": label, "product_weight": weight,
                            "median_weight": 1.0 - weight, "bias_shrinkage_factor": bias_factor,
                            "target_coverage": target, "forecast_return": pred,
                            "current_model_forecast_return": current, "realized_return": realized,
                            "absolute_error": abs(pred - realized),
                            "current_absolute_error": abs(current - realized),
                            "signed_error": pred - realized,
                            "beats_current": abs(pred - realized) < abs(current - realized),
                            "interval_lower": float(lower.loc[idx]), "interval_upper": float(upper.loc[idx]),
                            "inside_interval": bool(lower.loc[idx] <= realized <= upper.loc[idx]),
                            "below_interval": bool(realized < lower.loc[idx]),
                            "above_interval": bool(realized > upper.loc[idx]),
                            "future_information_used": False,
                        })

    pred = pd.DataFrame(predictions)
    sel = pd.DataFrame(selections)
    config_cols = ["horizon_days", "training_window_label", "product_weight", "bias_shrinkage_factor", "target_coverage"]
    rows: list[dict[str, object]] = []
    robustness_rows: list[dict[str, object]] = []
    if not pred.empty:
        for keys, group in pred.groupby(config_cols):
            record = dict(zip(config_cols, keys))
            coverage = float(group["inside_interval"].mean())
            tail = abs(float(group["below_interval"].mean()) - float(group["above_interval"].mean()))
            record.update({
                "case_count": int(len(group)), "decision_cutoff_count": int(group["decision_cutoff"].nunique()),
                "mean_absolute_error": float(group["absolute_error"].mean()),
                "current_model_mean_absolute_error": float(group["current_absolute_error"].mean()),
                "mae_improvement_vs_current": float(group["current_absolute_error"].mean() - group["absolute_error"].mean()),
                "mean_signed_error": float(group["signed_error"].mean()),
                "beats_current_rate": float(group["beats_current"].mean()),
                "empirical_coverage": coverage,
                "absolute_coverage_gap": abs(coverage - float(record["target_coverage"])),
                "below_interval_rate": float(group["below_interval"].mean()),
                "above_interval_rate": float(group["above_interval"].mean()),
                "tail_imbalance": tail,
            })
            rows.append(record)
            for slice_name in cfg["robustness_slices"]:
                sg = slice_frame(group, slice_name)
                if sg.empty:
                    continue
                robustness_rows.append({**{k: record[k] for k in config_cols},
                    "robustness_slice": slice_name, "case_count": int(len(sg)),
                    "mean_absolute_error": float(sg["absolute_error"].mean()),
                    "current_model_mean_absolute_error": float(sg["current_absolute_error"].mean()),
                    "mae_improvement_vs_current": float(sg["current_absolute_error"].mean() - sg["absolute_error"].mean()),
                    "beats_current_rate": float(sg["beats_current"].mean())})

    summary = pd.DataFrame(rows)
    robust = pd.DataFrame(robustness_rows)
    if not summary.empty and not robust.empty:
        rstats = robust.groupby(config_cols).agg(
            robustness_slice_count=("robustness_slice", "nunique"),
            minimum_slice_mae_improvement=("mae_improvement_vs_current", "min"),
            mean_slice_mae_improvement=("mae_improvement_vs_current", "mean"),
            mean_slice_beats_current_rate=("beats_current_rate", "mean"),
        ).reset_index()
        summary = summary.merge(rstats, on=config_cols, how="left")
        summary["coverage_acceptable"] = summary["absolute_coverage_gap"] <= float(cfg["coverage_tolerance"])
        summary["stability_penalty"] = np.maximum(0.0, -summary["minimum_slice_mae_improvement"])
        summary["tournament_score"] = (
            summary["mean_absolute_error"]
            + float(cfg["coverage_penalty_weight"]) * summary["absolute_coverage_gap"]
            + float(cfg["tail_imbalance_penalty_weight"]) * summary["tail_imbalance"]
            + float(cfg["stability_penalty_weight"]) * summary["stability_penalty"]
        )
        summary["disqualified"] = (
            (~summary["coverage_acceptable"])
            | (summary["minimum_slice_mae_improvement"] < 0)
            | (summary["robustness_slice_count"] < len(cfg["robustness_slices"]))
        )
        summary["selection_rank_within_horizon"] = summary.groupby("horizon_days")["tournament_score"].rank(method="dense")

    finalists = summary[summary["disqualified"] == False].sort_values(["horizon_days", "tournament_score"]).groupby("horizon_days").head(10) if not summary.empty else pd.DataFrame()
    winners = finalists.groupby("horizon_days").head(1) if not finalists.empty else pd.DataFrame()

    failures: list[str] = []
    if pred.empty: failures.append("no_tournament_predictions")
    if summary.empty: failures.append("no_tournament_summary")
    if not pred.empty and pred["future_information_used"].any(): failures.append("future_information_used")
    for key in ["candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed"]:
        if cfg.get(key) is not False: failures.append(f"authorization_not_closed:{key}")

    pred.to_csv(OUT / "collector_walk_forward_phase_2i_predictions.csv", index=False)
    sel.to_csv(OUT / "collector_walk_forward_phase_2i_selections.csv", index=False)
    summary.to_csv(OUT / "collector_walk_forward_phase_2i_configuration_summary.csv", index=False)
    robust.to_csv(OUT / "collector_walk_forward_phase_2i_robustness.csv", index=False)
    finalists.to_csv(OUT / "collector_walk_forward_phase_2i_finalists.csv", index=False)
    winners.to_csv(OUT / "collector_walk_forward_phase_2i_winners.csv", index=False)

    result = {
        "audit_name": cfg["audit_name"], "audit_version": cfg["audit_version"],
        "status": "PASS" if not failures else "FAIL",
        "prediction_count": int(len(pred)), "configuration_count": int(len(summary)),
        "robustness_result_count": int(len(robust)), "finalist_count": int(len(finalists)),
        "winner_count": int(len(winners)), "horizon_count": int(summary["horizon_days"].nunique()) if not summary.empty else 0,
        "shadow_only": True, "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False, "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False, "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures), "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2i_summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
