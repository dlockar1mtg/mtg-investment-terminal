from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2h_bias_shrinkage_v1.json"
PHASE_2E = ROOT / "data/operations/collector_walk_forward_phase_2e_regime_calibration/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2h_bias_shrinkage/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(
        PHASE_2E / "collector_walk_forward_phase_2e_predictions.csv",
        parse_dates=["decision_cutoff"],
        low_memory=False,
    )
    for col in ["forecast_return", "realized_return"]:
        source[col] = pd.to_numeric(source[col], errors="coerce")
    source["horizon_days"] = pd.to_numeric(source["horizon_days"], errors="coerce").astype("Int64")
    source = source.dropna(subset=["decision_cutoff", "forecast_return", "realized_return", "horizon_days"]).copy()
    source["outcome_maturity_date"] = source["decision_cutoff"] + pd.to_timedelta(source["horizon_days"].astype(int), unit="D")

    target = float(cfg["target_coverage"])
    factors = [float(x) for x in cfg["bias_shrinkage_factors"]]
    windows = list(cfg["source_training_windows"])

    prediction_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []

    for (horizon, window), frame in source.groupby(["horizon_days", "training_window_label"]):
        if window not in windows:
            continue
        for cutoff in sorted(frame["decision_cutoff"].dropna().unique()):
            test = frame[frame["decision_cutoff"] == cutoff].copy()
            calibration = frame[frame["outcome_maturity_date"] < cutoff].copy()
            calibration_cutoffs = int(calibration["decision_cutoff"].nunique())
            ready = (
                len(calibration) >= int(cfg["minimum_calibration_cases"])
                and calibration_cutoffs >= int(cfg["minimum_calibration_cutoffs"])
            )
            if not ready:
                continue

            signed = calibration["realized_return"] - calibration["forecast_return"]
            median_bias = float(signed.median())

            for factor in factors:
                applied_bias = factor * median_bias
                centered_errors = calibration["realized_return"] - (calibration["forecast_return"] + applied_bias)
                radius = float(centered_errors.abs().quantile(target))

                lower = test["forecast_return"] + applied_bias - radius
                upper = test["forecast_return"] + applied_bias + radius

                selection_rows.append({
                    "horizon_days": int(horizon),
                    "training_window_label": window,
                    "decision_cutoff": cutoff,
                    "calibration_case_count": int(len(calibration)),
                    "calibration_cutoff_count": calibration_cutoffs,
                    "target_coverage": target,
                    "bias_shrinkage_factor": factor,
                    "raw_median_bias": median_bias,
                    "applied_bias_correction": applied_bias,
                    "conformal_radius": radius,
                })

                for idx, row in test.iterrows():
                    realized = float(row["realized_return"])
                    lo = float(lower.loc[idx])
                    hi = float(upper.loc[idx])
                    prediction_rows.append({
                        "horizon_days": int(horizon),
                        "training_window_label": window,
                        "decision_cutoff": cutoff,
                        "product_key": row["product_key"],
                        "product_name": row["product_name"],
                        "target_coverage": target,
                        "bias_shrinkage_factor": factor,
                        "raw_forecast_return": float(row["forecast_return"]),
                        "applied_bias_correction": applied_bias,
                        "corrected_center": float(row["forecast_return"] + applied_bias),
                        "conformal_radius": radius,
                        "interval_lower": lo,
                        "interval_upper": hi,
                        "realized_return": realized,
                        "inside_interval": bool(lo <= realized <= hi),
                        "below_interval": bool(realized < lo),
                        "above_interval": bool(realized > hi),
                        "future_information_used": False,
                    })

    predictions = pd.DataFrame(prediction_rows)
    selections = pd.DataFrame(selection_rows)

    summaries: list[dict[str, object]] = []
    if not predictions.empty:
        grouped = predictions.groupby(["horizon_days", "training_window_label", "bias_shrinkage_factor"])
        for (horizon, window, factor), group in grouped:
            coverage = float(group["inside_interval"].mean())
            below = float(group["below_interval"].mean())
            above = float(group["above_interval"].mean())
            summaries.append({
                "horizon_days": int(horizon),
                "training_window_label": window,
                "bias_shrinkage_factor": float(factor),
                "case_count": int(len(group)),
                "decision_cutoff_count": int(group["decision_cutoff"].nunique()),
                "target_coverage": target,
                "empirical_coverage": coverage,
                "coverage_gap": coverage - target,
                "absolute_coverage_gap": abs(coverage - target),
                "below_interval_rate": below,
                "above_interval_rate": above,
                "tail_imbalance": abs(below - above),
                "mean_applied_bias_correction": float(group["applied_bias_correction"].mean()),
                "mean_conformal_radius": float(group["conformal_radius"].mean()),
            })

    summary_table = pd.DataFrame(summaries)
    if not summary_table.empty:
        tolerance = float(cfg["selection_coverage_tolerance"])
        summary_table["coverage_acceptable"] = summary_table["absolute_coverage_gap"] <= tolerance
        summary_table["selection_score"] = (
            summary_table["absolute_coverage_gap"] * 10.0
            + summary_table["tail_imbalance"]
            + np.where(summary_table["coverage_acceptable"], 0.0, 1.0)
        )
        summary_table["selection_rank_within_horizon"] = summary_table.groupby("horizon_days")["selection_score"].rank(method="dense")

    failures: list[str] = []
    if predictions.empty:
        failures.append("no_bias_shrinkage_predictions")
    if selections.empty:
        failures.append("no_bias_shrinkage_selections")
    if not predictions.empty and predictions["future_information_used"].any():
        failures.append("future_information_used")
    for key in [
        "candidate_methodology_change_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    predictions.to_csv(OUT / "collector_walk_forward_phase_2h_predictions.csv", index=False)
    selections.to_csv(OUT / "collector_walk_forward_phase_2h_selections.csv", index=False)
    summary_table.to_csv(OUT / "collector_walk_forward_phase_2h_interval_summary.csv", index=False)

    summary = {
        "audit_name": cfg["audit_name"],
        "audit_version": cfg["audit_version"],
        "status": "PASS" if not failures else "FAIL",
        "prediction_count": int(len(predictions)),
        "selection_count": int(len(selections)),
        "horizon_count": int(predictions["horizon_days"].nunique()) if not predictions.empty else 0,
        "training_window_count": int(predictions["training_window_label"].nunique()) if not predictions.empty else 0,
        "bias_shrinkage_factor_count": int(predictions["bias_shrinkage_factor"].nunique()) if not predictions.empty else 0,
        "target_coverage": target,
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2h_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
