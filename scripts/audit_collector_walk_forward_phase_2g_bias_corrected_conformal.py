from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2g_bias_corrected_conformal/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = [
        OUT / "collector_walk_forward_phase_2g_predictions.csv",
        OUT / "collector_walk_forward_phase_2g_selections.csv",
        OUT / "collector_walk_forward_phase_2g_interval_summary.csv",
        OUT / "collector_walk_forward_phase_2g_summary.json",
    ]
    for path in required:
        if not path.exists():
            failures.append(f"missing:{path.name}")

    if not failures:
        predictions = pd.read_csv(required[0])
        selections = pd.read_csv(required[1])
        interval_summary = pd.read_csv(required[2])
        summary = json.loads(required[3].read_text(encoding="utf-8"))

        if predictions.empty:
            failures.append("predictions_empty")
        if selections.empty:
            failures.append("selections_empty")
        if interval_summary.empty:
            failures.append("interval_summary_empty")
        if not predictions.empty and predictions["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_used")
        if not predictions.empty and (predictions["interval_lower"] > predictions["interval_upper"]).any():
            failures.append("invalid_interval_order")
        if not interval_summary.empty and not interval_summary["empirical_coverage"].between(0, 1).all():
            failures.append("coverage_out_of_range")
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
        "audit_name": "Collector Walk-Forward Phase 2G Bias-Corrected Conformal Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
