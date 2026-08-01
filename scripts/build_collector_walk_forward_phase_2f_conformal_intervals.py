from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2f_conformal_intervals_v1.json"
PHASE_2E = ROOT / "data/operations/collector_walk_forward_phase_2e_regime_calibration/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2f_conformal_intervals/candidate_v1_0_0"


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
    for column in ["forecast_return", "realized_return", "absolute_error"]:
        source[column] = pd.to_numeric(source[column], errors="coerce")
    source = source.dropna(subset=["decision_cutoff", "forecast_return", "realized_return", "absolute_error"]).copy()

    rows: list[dict[str, object]] = []
    selections: list[dict[str, object]] = []
    for (horizon, window), frame in source.groupby(["horizon_days", "training_window_label"]):
        if window not in set(cfg["source_training_windows"]):
            continue
        for cutoff in sorted(frame["decision_cutoff"].dropna().unique()):
            test = frame[frame["decision_cutoff"] == cutoff].copy()
            calibration = frame[
                (frame["decision_cutoff"] < cutoff)
                & ((frame["decision_cutoff"] + pd.to_timedelta(frame["horizon_days"].astype(int), unit="D")) < cutoff)
            ].copy()
            cutoff_count = int(calibration["decision_cutoff"].nunique())
            ready = len(calibration) >= int(cfg["minimum_calibration_cases"]) and cutoff_count >= int(cfg["minimum_calibration_cutoffs"])
            if not ready:
                continue
            for target in [float(x) for x in cfg["target_coverages"]]:
                radius = float(calibration["absolute_error"].quantile(target, interpolation="higher"))
                selections.append({
                    "horizon_days": int(horizon),
                    "training_window_label": window,
                    "decision_cutoff": cutoff,
                    "target_coverage": target,
                    "calibration_case_count": int(len(calibration)),
                    "calibration_cutoff_count": cutoff_count,
                    "conformal_radius": radius,
                })
                lower = test["forecast_return"] - radius
                upper = test["forecast_return"] + radius
                for idx, row in test.iterrows():
                    realized = float(row["realized_return"])
                    rows.append({
                        "horizon_days": int(horizon),
                        "training_window_label": window,
                        "decision_cutoff": cutoff,
                        "product_key": row["product_key"],
                        "product_name": row["product_name"],
                        "target_coverage": target,
                        "forecast_return": float(row["forecast_return"]),
                        "realized_return": realized,
                        "conformal_radius": radius,
                        "interval_lower": float(lower.loc[idx]),
                        "interval_upper": float(upper.loc[idx]),
                        "inside_interval": bool(lower.loc[idx] <= realized <= upper.loc[idx]),
                        "below_interval": bool(realized < lower.loc[idx]),
                        "above_interval": bool(realized > upper.loc[idx]),
                        "future_information_used": False,
                    })

    predictions = pd.DataFrame(rows)
    selection_table = pd.DataFrame(selections)
    summary_rows: list[dict[str, object]] = []
    if not predictions.empty:
        for (horizon, window, target), group in predictions.groupby(["horizon_days", "training_window_label", "target_coverage"]):
            coverage = float(group["inside_interval"].mean())
            summary_rows.append({
                "horizon_days": int(horizon),
                "training_window_label": window,
                "target_coverage": float(target),
                "case_count": int(len(group)),
                "decision_cutoff_count": int(group["decision_cutoff"].nunique()),
                "empirical_coverage": coverage,
                "coverage_gap": coverage - float(target),
                "absolute_coverage_gap": abs(coverage - float(target)),
                "below_interval_rate": float(group["below_interval"].mean()),
                "above_interval_rate": float(group["above_interval"].mean()),
                "tail_imbalance": abs(float(group["below_interval"].mean()) - float(group["above_interval"].mean())),
                "mean_conformal_radius": float(group["conformal_radius"].mean()),
            })
    summary_table = pd.DataFrame(summary_rows)
    if not summary_table.empty:
        summary_table["calibration_rank_within_horizon_target"] = summary_table.groupby(
            ["horizon_days", "target_coverage"]
        )["absolute_coverage_gap"].rank(method="dense")

    failures: list[str] = []
    if predictions.empty:
        failures.append("no_conformal_predictions")
    if selection_table.empty:
        failures.append("no_conformal_selections")
    if not predictions.empty and predictions["future_information_used"].any():
        failures.append("future_information_used")
    for key in ["candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed"]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    predictions.to_csv(OUT / "collector_walk_forward_phase_2f_predictions.csv", index=False)
    selection_table.to_csv(OUT / "collector_walk_forward_phase_2f_selections.csv", index=False)
    summary_table.to_csv(OUT / "collector_walk_forward_phase_2f_interval_summary.csv", index=False)

    summary = {
        "audit_name": cfg["audit_name"],
        "audit_version": cfg["audit_version"],
        "status": "PASS" if not failures else "FAIL",
        "prediction_count": int(len(predictions)),
        "selection_count": int(len(selection_table)),
        "horizon_count": int(predictions["horizon_days"].nunique()) if not predictions.empty else 0,
        "target_coverage_count": int(predictions["target_coverage"].nunique()) if not predictions.empty else 0,
        "training_window_count": int(predictions["training_window_label"].nunique()) if not predictions.empty else 0,
        "shadow_only": True,
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2f_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
