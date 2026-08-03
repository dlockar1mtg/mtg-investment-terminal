from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2g_bias_corrected_conformal_v1.json"
SOURCE = ROOT / "data/operations/collector_walk_forward_phase_2e_regime_calibration/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2g_bias_corrected_conformal/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(
        SOURCE / "collector_walk_forward_phase_2e_predictions.csv",
        parse_dates=["decision_cutoff"],
        low_memory=False,
    )
    source = source[source["training_window_label"].isin(cfg["source_training_windows"])].copy()
    source["horizon_days"] = pd.to_numeric(source["horizon_days"], errors="coerce").astype("Int64")
    source["forecast_return"] = pd.to_numeric(source["forecast_return"], errors="coerce")
    source["realized_return"] = pd.to_numeric(source["realized_return"], errors="coerce")
    source = source.dropna(subset=["decision_cutoff", "horizon_days", "forecast_return", "realized_return"])
    source["outcome_maturity_date"] = source["decision_cutoff"] + pd.to_timedelta(source["horizon_days"].astype(int), unit="D")
    source["signed_residual"] = source["realized_return"] - source["forecast_return"]

    prediction_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []

    for (horizon, window), frame in source.groupby(["horizon_days", "training_window_label"]):
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

            bias = float(calibration["signed_residual"].median())
            centered_abs = (calibration["signed_residual"] - bias).abs()

            for target in [float(x) for x in cfg["target_coverages"]]:
                radius = float(centered_abs.quantile(target))
                center = test["forecast_return"] + bias
                lower = center - radius
                upper = center + radius

                selection_rows.append({
                    "horizon_days": int(horizon),
                    "training_window_label": window,
                    "decision_cutoff": cutoff,
                    "calibration_case_count": int(len(calibration)),
                    "calibration_cutoff_count": calibration_cutoffs,
                    "target_coverage": target,
                    "bias_correction": bias,
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
                        "forecast_return": float(row["forecast_return"]),
                        "bias_correction": bias,
                        "bias_corrected_center": float(center.loc[idx]),
                        "conformal_radius": radius,
                        "realized_return": realized,
                        "interval_lower": lo,
                        "interval_upper": hi,
                        "inside_interval": bool(lo <= realized <= hi),
                        "below_interval": bool(realized < lo),
                        "above_interval": bool(realized > hi),
                        "future_information_used": False,
                    })

    predictions = pd.DataFrame(prediction_rows)
    selections = pd.DataFrame(selection_rows)

    summaries: list[dict[str, object]] = []
    if not predictions.empty:
        for (horizon, target, window), group in predictions.groupby(
            ["horizon_days", "target_coverage", "training_window_label"]
        ):
            coverage = float(group["inside_interval"].mean())
            below = float(group["below_interval"].mean())
            above = float(group["above_interval"].mean())
            summaries.append({
                "horizon_days": int(horizon),
                "target_coverage": float(target),
                "training_window_label": window,
                "case_count": int(len(group)),
                "decision_cutoff_count": int(group["decision_cutoff"].nunique()),
                "empirical_coverage": coverage,
                "coverage_gap": coverage - float(target),
                "absolute_coverage_gap": abs(coverage - float(target)),
                "below_interval_rate": below,
                "above_interval_rate": above,
                "tail_imbalance": abs(below - above),
                "mean_bias_correction": float(group["bias_correction"].mean()),
                "mean_conformal_radius": float(group["conformal_radius"].mean()),
            })
    summary_table = pd.DataFrame(summaries)
    if not summary_table.empty:
        summary_table["calibration_rank_within_horizon_target"] = summary_table.groupby(
            ["horizon_days", "target_coverage"]
        )["absolute_coverage_gap"].rank(method="dense")

    failures: list[str] = []
    if predictions.empty:
        failures.append("no_bias_corrected_predictions")
    if selections.empty:
        failures.append("no_bias_corrected_selections")
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

    predictions.to_csv(OUT / "collector_walk_forward_phase_2g_predictions.csv", index=False)
    selections.to_csv(OUT / "collector_walk_forward_phase_2g_selections.csv", index=False)
    summary_table.to_csv(OUT / "collector_walk_forward_phase_2g_interval_summary.csv", index=False)

    summary = {
        "audit_name": cfg["audit_name"],
        "audit_version": cfg["audit_version"],
        "status": "PASS" if not failures else "FAIL",
        "prediction_count": int(len(predictions)),
        "selection_count": int(len(selections)),
        "horizon_count": int(predictions["horizon_days"].nunique()) if not predictions.empty else 0,
        "training_window_count": int(predictions["training_window_label"].nunique()) if not predictions.empty else 0,
        "target_coverage_count": int(predictions["target_coverage"].nunique()) if not predictions.empty else 0,
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2g_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
