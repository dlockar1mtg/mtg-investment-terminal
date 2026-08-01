from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2i_finalist_tournament/candidate_v1_0_0"
CONFIG = ROOT / "config/mtg/governance/collector_walk_forward_phase_2i_finalist_tournament_v1.json"
EPSILON = 1e-12


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    configurations = pd.read_csv(
        OUT / "collector_walk_forward_phase_2i_configuration_summary.csv",
        low_memory=False,
    )

    numeric_columns = [
        "horizon_days",
        "product_weight",
        "bias_shrinkage_factor",
        "target_coverage",
        "mae_improvement_vs_current",
        "minimum_slice_mae_improvement",
        "mean_slice_mae_improvement",
        "beats_current_rate",
        "absolute_coverage_gap",
        "tail_imbalance",
        "tournament_score",
        "robustness_slice_count",
    ]
    for column in numeric_columns:
        configurations[column] = pd.to_numeric(configurations[column], errors="coerce")

    required_slice_count = len(cfg["robustness_slices"])
    configurations["is_baseline_forecast"] = (
        configurations["product_weight"].sub(1.0).abs() <= EPSILON
    ) & (
        configurations["bias_shrinkage_factor"].abs() <= EPSILON
    )

    configurations["challenger_qualified"] = (
        configurations["coverage_acceptable"].astype(str).str.lower().eq("true")
        & (configurations["robustness_slice_count"] >= required_slice_count)
        & (configurations["mae_improvement_vs_current"] > EPSILON)
        & (configurations["minimum_slice_mae_improvement"] > EPSILON)
        & (~configurations["is_baseline_forecast"])
    )

    challenger_rows: list[pd.DataFrame] = []
    winner_rows: list[pd.DataFrame] = []
    fallback_rows: list[pd.DataFrame] = []
    decision_rows: list[dict[str, object]] = []

    for horizon, horizon_frame in configurations.groupby("horizon_days"):
        qualified = horizon_frame[horizon_frame["challenger_qualified"]].copy()
        qualified = qualified.sort_values(
            [
                "tournament_score",
                "mean_absolute_error",
                "absolute_coverage_gap",
                "tail_imbalance",
            ],
            ascending=[True, True, True, True],
        )
        if not qualified.empty:
            qualified["challenger_rank_within_horizon"] = range(1, len(qualified) + 1)
            challenger_rows.append(qualified.head(10))
            winner = qualified.head(1).copy()
            winner["decision_status"] = "CHALLENGER_AVAILABLE_FOR_OWNER_REVIEW"
            winner_rows.append(winner)
            decision_rows.append(
                {
                    "horizon_days": int(horizon),
                    "decision_status": "CHALLENGER_AVAILABLE_FOR_OWNER_REVIEW",
                    "qualified_challenger_count": int(len(qualified)),
                    "selected_training_window_label": winner.iloc[0]["training_window_label"],
                    "selected_product_weight": float(winner.iloc[0]["product_weight"]),
                    "selected_median_weight": 1.0 - float(winner.iloc[0]["product_weight"]),
                    "selected_bias_shrinkage_factor": float(winner.iloc[0]["bias_shrinkage_factor"]),
                    "selected_target_coverage": float(winner.iloc[0]["target_coverage"]),
                    "mae_improvement_vs_current": float(winner.iloc[0]["mae_improvement_vs_current"]),
                    "minimum_slice_mae_improvement": float(winner.iloc[0]["minimum_slice_mae_improvement"]),
                    "owner_approval_required": True,
                    "methodology_change_authorized": False,
                }
            )
        else:
            baseline = horizon_frame[horizon_frame["is_baseline_forecast"]].copy()
            baseline = baseline.sort_values(
                ["absolute_coverage_gap", "tail_imbalance", "tournament_score"],
                ascending=[True, True, True],
            ).head(1)
            if not baseline.empty:
                baseline["decision_status"] = "RETAIN_CURRENT_BASELINE_NO_ROBUST_CHALLENGER"
                fallback_rows.append(baseline)
            decision_rows.append(
                {
                    "horizon_days": int(horizon),
                    "decision_status": "RETAIN_CURRENT_BASELINE_NO_ROBUST_CHALLENGER",
                    "qualified_challenger_count": 0,
                    "selected_training_window_label": None,
                    "selected_product_weight": None,
                    "selected_median_weight": None,
                    "selected_bias_shrinkage_factor": None,
                    "selected_target_coverage": None,
                    "mae_improvement_vs_current": 0.0,
                    "minimum_slice_mae_improvement": 0.0,
                    "owner_approval_required": False,
                    "methodology_change_authorized": False,
                }
            )

    challengers = pd.concat(challenger_rows, ignore_index=True) if challenger_rows else pd.DataFrame()
    winners = pd.concat(winner_rows, ignore_index=True) if winner_rows else pd.DataFrame()
    fallbacks = pd.concat(fallback_rows, ignore_index=True) if fallback_rows else pd.DataFrame()
    decisions = pd.DataFrame(decision_rows)

    failures: list[str] = []
    if configurations.empty:
        failures.append("configuration_summary_empty")
    if decisions.empty:
        failures.append("decision_summary_empty")
    if not winners.empty:
        if winners["is_baseline_forecast"].any():
            failures.append("baseline_selected_as_challenger")
        if not (winners["mae_improvement_vs_current"] > EPSILON).all():
            failures.append("challenger_without_positive_full_sample_improvement")
        if not (winners["minimum_slice_mae_improvement"] > EPSILON).all():
            failures.append("challenger_without_positive_all_slice_improvement")
    for key in [
        "candidate_methodology_change_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]:
        if cfg.get(key) is not False:
            failures.append(f"authorization_not_closed:{key}")

    configurations.to_csv(
        OUT / "collector_walk_forward_phase_2i_configuration_certification.csv",
        index=False,
    )
    challengers.to_csv(
        OUT / "collector_walk_forward_phase_2i_qualified_challengers.csv",
        index=False,
    )
    winners.to_csv(
        OUT / "collector_walk_forward_phase_2i_corrected_winners.csv",
        index=False,
    )
    fallbacks.to_csv(
        OUT / "collector_walk_forward_phase_2i_baseline_fallbacks.csv",
        index=False,
    )
    decisions.to_csv(
        OUT / "collector_walk_forward_phase_2i_owner_decisions.csv",
        index=False,
    )

    summary = {
        "audit_name": "Collector Walk-Forward Phase 2I Owner Decision Finalization",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "horizon_count": int(decisions["horizon_days"].nunique()) if not decisions.empty else 0,
        "qualified_challenger_count": int(configurations["challenger_qualified"].sum()),
        "corrected_winner_count": int(len(winners)),
        "baseline_fallback_count": int(len(fallbacks)),
        "owner_approval_required": bool(not winners.empty),
        "candidate_methodology_change_authorized": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "automatic_model_update_allowed": False,
        "freeze_suspended_pending_walk_forward": True,
        "failure_count": len(failures),
        "failures": failures,
    }
    (OUT / "collector_walk_forward_phase_2i_owner_decision_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
