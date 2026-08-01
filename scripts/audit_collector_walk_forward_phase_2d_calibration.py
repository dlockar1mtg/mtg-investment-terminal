from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2d_calibration/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    required = [
        OUT / "collector_walk_forward_phase_2d_oos_predictions.csv",
        OUT / "collector_walk_forward_phase_2d_weight_selections.csv",
        OUT / "collector_walk_forward_phase_2d_horizon_summary.csv",
        OUT / "collector_walk_forward_phase_2d_summary.json",
    ]
    failures: list[str] = []
    for path in required:
        if not path.exists():
            failures.append(f"missing:{path.name}")

    if not failures:
        oos = pd.read_csv(required[0])
        selections = pd.read_csv(required[1])
        horizon = pd.read_csv(required[2])
        summary = json.loads(required[3].read_text(encoding="utf-8"))
        if oos.empty:
            failures.append("no_oos_predictions")
        if selections.empty:
            failures.append("no_weight_selections")
        if horizon.empty:
            failures.append("no_horizon_summary")
        if not oos.empty and oos["future_information_used"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_used")
        if not selections.empty:
            weights = pd.to_numeric(selections["selected_product_weight"], errors="coerce")
            if weights.isna().any() or ((weights < 0) | (weights > 1)).any():
                failures.append("selected_weight_out_of_bounds")
            ready = selections[selections["training_ready"].astype(str).str.lower().eq("true")]
            if ready.empty:
                failures.append("no_training_ready_selection")
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
        if summary.get("shadow_only") is not True:
            failures.append("shadow_only_not_true")

    result = {
        "audit_name": "Collector Walk-Forward Phase 2D Calibration Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
