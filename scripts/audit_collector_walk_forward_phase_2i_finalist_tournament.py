from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2i_finalist_tournament/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    required = [
        "collector_walk_forward_phase_2i_predictions.csv",
        "collector_walk_forward_phase_2i_selections.csv",
        "collector_walk_forward_phase_2i_configuration_summary.csv",
        "collector_walk_forward_phase_2i_robustness.csv",
        "collector_walk_forward_phase_2i_finalists.csv",
        "collector_walk_forward_phase_2i_winners.csv",
        "collector_walk_forward_phase_2i_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists(): failures.append(f"missing_output:{name}")
    if not failures:
        summary = json.loads((OUT / "collector_walk_forward_phase_2i_summary.json").read_text(encoding="utf-8"))
        configs = pd.read_csv(OUT / "collector_walk_forward_phase_2i_configuration_summary.csv", low_memory=False)
        robust = pd.read_csv(OUT / "collector_walk_forward_phase_2i_robustness.csv", low_memory=False)
        winners = pd.read_csv(OUT / "collector_walk_forward_phase_2i_winners.csv", low_memory=False)
        predictions = pd.read_csv(OUT / "collector_walk_forward_phase_2i_predictions.csv", low_memory=False)
        if summary.get("status") != "PASS": failures.append("builder_status_not_pass")
        if configs.empty: failures.append("configuration_summary_empty")
        if robust.empty: failures.append("robustness_output_empty")
        if predictions.empty: failures.append("predictions_empty")
        if not predictions.empty and predictions["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_used")
        if not configs.empty:
            required_cols = {"tournament_score", "disqualified", "minimum_slice_mae_improvement", "absolute_coverage_gap", "tail_imbalance"}
            missing = required_cols - set(configs.columns)
            if missing: failures.append("missing_configuration_columns:" + ",".join(sorted(missing)))
            if configs.duplicated(["horizon_days", "training_window_label", "product_weight", "bias_shrinkage_factor", "target_coverage"]).any():
                failures.append("duplicate_configuration_rows")
        if not winners.empty:
            if winners["disqualified"].astype(str).str.lower().eq("true").any(): failures.append("winner_is_disqualified")
            if winners["horizon_days"].duplicated().any(): failures.append("multiple_winners_per_horizon")
        for key in ["candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed"]:
            if summary.get(key) is not False: failures.append(f"authorization_not_closed:{key}")
        if summary.get("freeze_suspended_pending_walk_forward") is not True:
            failures.append("freeze_not_suspended")
    result = {"audit_name": "Collector Walk-Forward Phase 2I Finalist Tournament Audit", "status": "PASS" if not failures else "FAIL", "failure_count": len(failures), "failures": failures}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
