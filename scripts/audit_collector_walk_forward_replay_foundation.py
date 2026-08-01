from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_replay_foundation/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    required = [
        "collector_walk_forward_source_inventory.csv",
        "collector_walk_forward_decision_schedule.csv",
        "collector_walk_forward_eligibility_matrix.csv",
        "collector_walk_forward_outcome_availability.csv",
        "collector_walk_forward_replay_foundation_summary.json",
    ]
    failures = [f"missing_output:{name}" for name in required if not (OUT / name).exists()]
    summary = {}
    if not failures:
        summary = json.loads((OUT / required[-1]).read_text(encoding="utf-8"))
        matrix = pd.read_csv(OUT / required[2], low_memory=False)
        outcomes = pd.read_csv(OUT / required[3], low_memory=False)
        if summary.get("historical_forecasts_generated") is not False:
            failures.append("foundation_must_not_claim_historical_forecasts")
        if summary.get("freeze_suspended_pending_walk_forward") is not True:
            failures.append("freeze_not_suspended")
        if summary.get("today_candidate_outputs_used_as_historical_inputs") is not False:
            failures.append("today_candidate_output_leakage")
        if not matrix.empty and "future_information_used" in matrix and matrix["future_information_used"].astype(str).str.lower().isin(["true", "1", "yes"]).any():
            failures.append("future_information_used")
        if not outcomes.empty and not outcomes["outcome_held_out_from_decision_inputs"].astype(str).str.lower().isin(["true", "1", "yes"]).all():
            failures.append("held_out_outcome_failure")
        for field in ["production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed"]:
            if summary.get(field) is not False:
                failures.append(f"authorization_open:{field}")
    result = {
        "audit_name": "Collector Leakage-Safe Walk-Forward Replay Foundation Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "source_candidate_count": int(summary.get("source_candidate_count", 0)),
        "decision_cutoff_count": int(summary.get("decision_cutoff_count", 0)),
        "eligible_product_cutoff_count": int(summary.get("eligible_product_cutoff_count", 0)),
        "available_outcome_count": int(summary.get("available_outcome_count", 0)),
        "freeze_suspended_pending_walk_forward": bool(summary.get("freeze_suspended_pending_walk_forward", False)),
        "historical_forecasts_generated": bool(summary.get("historical_forecasts_generated", False)),
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit verifies the leakage-safe replay foundation only. It does not validate model accuracy.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
