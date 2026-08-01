from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2c_robustness_v1.json"
PHASE_2B = ROOT / "data/operations/collector_walk_forward_phase_2b_benchmark_lab/candidate_v1_0_0"
OUT = ROOT / "data/operations/collector_walk_forward_phase_2c_robustness/candidate_v1_0_0"


def summarize(frame: pd.DataFrame, test_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horizon, group in frame.groupby("horizon_days"):
        current = group[group["variant_name"] == "MODEL_CURRENT"]
        candidate = group[group["variant_name"] == "CROSS_SECTIONAL_MEDIAN_BLEND_50"]
        if current.empty or candidate.empty:
            continue
        current_mae = float(current["absolute_return_error"].mean())
        candidate_mae = float(candidate["absolute_return_error"].mean())
        rows.append({
            "robustness_test": test_name,
            "horizon_days": int(horizon),
            "case_count": int(candidate.shape[0]),
            "current_model_mae": current_mae,
            "candidate_variant_mae": candidate_mae,
            "mae_improvement": current_mae - candidate_mae,
            "candidate_direction_accuracy": float(candidate["direction_correct"].mean()),
            "candidate_mean_signed_error": float(candidate["signed_return_error"].mean()),
            "candidate_outperforms_current": bool(candidate_mae < current_mae),
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    variants = pd.read_csv(PHASE_2B / "collector_walk_forward_phase_2b_variant_outcomes.csv", parse_dates=["decision_cutoff"])
    variants["absolute_return_error"] = pd.to_numeric(variants["absolute_return_error"], errors="coerce")
    variants["signed_return_error"] = pd.to_numeric(variants["signed_return_error"], errors="coerce")
    variants["direction_correct"] = variants["direction_correct"].astype(str).str.lower().eq("true")

    paired = variants[variants["variant_name"].isin([cfg["comparison_variant"], cfg["candidate_variant"]])].copy()
    current = paired[paired["variant_name"] == cfg["comparison_variant"]].copy()

    product_error = current.groupby("product_name")["absolute_return_error"].mean().sort_values(ascending=False)
    highest_error_product = str(product_error.index[0]) if not product_error.empty else ""
    trim_threshold = float(current["absolute_return_error"].quantile(0.95)) if not current.empty else np.nan
    cutoff_values = sorted(current["decision_cutoff"].dropna().unique())
    midpoint = cutoff_values[len(cutoff_values) // 2] if cutoff_values else None

    frames: dict[str, pd.DataFrame] = {
        "ALL_CASES": paired,
        "EXCLUDE_HIGHEST_ERROR_PRODUCT": paired[paired["product_name"] != highest_error_product],
        "TRIM_TOP_5_PERCENT_CURRENT_MODEL_ERRORS": paired.merge(
            current[["decision_cutoff", "product_key", "product_name", "horizon_days", "absolute_return_error"]],
            on=["decision_cutoff", "product_key", "product_name", "horizon_days"],
            how="left",
            suffixes=("", "_current"),
        ).query("absolute_return_error_current <= @trim_threshold"),
    }
    if midpoint is not None:
        frames["EARLY_CUTOFF_HALF"] = paired[paired["decision_cutoff"] < midpoint]
        frames["LATE_CUTOFF_HALF"] = paired[paired["decision_cutoff"] >= midpoint]

    result_rows: list[dict[str, object]] = []
    for name, frame in frames.items():
        result_rows.extend(summarize(frame, name))

    results = pd.DataFrame(result_rows)
    results.to_csv(OUT / "collector_walk_forward_phase_2c_robustness_results.csv", index=False)

    horizon_summary = results.groupby("horizon_days").agg(
        robustness_test_count=("robustness_test", "nunique"),
        outperform_test_count=("candidate_outperforms_current", "sum"),
        minimum_mae_improvement=("mae_improvement", "min"),
        mean_mae_improvement=("mae_improvement", "mean"),
    ).reset_index()
    horizon_summary["robustness_pass"] = horizon_summary["outperform_test_count"] == horizon_summary["robustness_test_count"]
    horizon_summary.to_csv(OUT / "collector_walk_forward_phase_2c_horizon_summary.csv", index=False)

    failures: list[str] = []
    if results.empty:
        failures.append("no_robustness_results")
    if not results.empty and not set(cfg["robustness_tests"]).issubset(set(results["robustness_test"])):
        failures.append("missing_required_robustness_test")

    summary = {
        "audit_name": "Collector Walk-Forward Phase 2C Robustness Review",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "candidate_variant": cfg["candidate_variant"],
        "comparison_variant": cfg["comparison_variant"],
        "highest_error_product_excluded_test": highest_error_product,
        "robustness_result_count": int(len(results)),
        "horizon_count": int(results["horizon_days"].nunique()) if not results.empty else 0,
        "all_horizons_robust": bool(horizon_summary["robustness_pass"].all()) if not horizon_summary.empty else False,
        "candidate_methodology_change_authorized": False,
        "freeze_suspended_pending_walk_forward": True,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2c_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
