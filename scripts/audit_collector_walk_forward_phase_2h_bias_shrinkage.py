from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2h_bias_shrinkage/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = [
        OUT / "collector_walk_forward_phase_2h_predictions.csv",
        OUT / "collector_walk_forward_phase_2h_selections.csv",
        OUT / "collector_walk_forward_phase_2h_interval_summary.csv",
        OUT / "collector_walk_forward_phase_2h_summary.json",
    ]
    for path in required:
        if not path.exists():
            failures.append(f"missing:{path.name}")

    if not failures:
        predictions = pd.read_csv(required[0], low_memory=False)
        selections = pd.read_csv(required[1], low_memory=False)
        summary_table = pd.read_csv(required[2], low_memory=False)
        summary = json.loads(required[3].read_text(encoding="utf-8"))

        if predictions.empty:
            failures.append("predictions_empty")
        if selections.empty:
            failures.append("selections_empty")
        if summary_table.empty:
            failures.append("interval_summary_empty")
        if predictions["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_used")
        if predictions["bias_shrinkage_factor"].nunique() != 5:
            failures.append("bias_shrinkage_factor_count_not_5")
        if predictions["training_window_label"].nunique() != 5:
            failures.append("training_window_count_not_5")
        if summary_table["target_coverage"].nunique() != 1:
            failures.append("target_coverage_count_not_1")
        if not summary_table["bias_shrinkage_factor"].isin([0.0, 0.25, 0.5, 0.75, 1.0]).all():
            failures.append("unexpected_bias_shrinkage_factor")
        for field in [
            "candidate_methodology_change_authorized",
            "production_projection_authorized",
            "purchase_recommendation_authorized",
            "automatic_model_update_allowed",
        ]:
            if summary.get(field) is not False:
                failures.append(f"authorization_not_closed:{field}")
        if summary.get("freeze_suspended_pending_walk_forward") is not True:
            failures.append("freeze_not_suspended")

    result = {
        "audit_name": "Collector Walk-Forward Phase 2H Bias Shrinkage Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
