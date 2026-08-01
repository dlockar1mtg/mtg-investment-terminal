from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2i_finalist_tournament/candidate_v1_0_0"
EPSILON = 1e-12


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    failures: list[str] = []
    required = [
        "collector_walk_forward_phase_2i_configuration_certification.csv",
        "collector_walk_forward_phase_2i_qualified_challengers.csv",
        "collector_walk_forward_phase_2i_corrected_winners.csv",
        "collector_walk_forward_phase_2i_baseline_fallbacks.csv",
        "collector_walk_forward_phase_2i_owner_decisions.csv",
        "collector_walk_forward_phase_2i_owner_decision_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists():
            failures.append(f"missing_output:{name}")

    if not failures:
        summary = json.loads(
            (OUT / "collector_walk_forward_phase_2i_owner_decision_summary.json").read_text(
                encoding="utf-8"
            )
        )
        certified = pd.read_csv(
            OUT / "collector_walk_forward_phase_2i_configuration_certification.csv",
            low_memory=False,
        )
        decisions = pd.read_csv(
            OUT / "collector_walk_forward_phase_2i_owner_decisions.csv",
            low_memory=False,
        )
        winners_path = OUT / "collector_walk_forward_phase_2i_corrected_winners.csv"
        winners = pd.read_csv(winners_path, low_memory=False) if winners_path.stat().st_size > 1 else pd.DataFrame()

        if summary.get("status") != "PASS":
            failures.append("finalizer_status_not_pass")
        if certified.empty:
            failures.append("certification_output_empty")
        if decisions.empty:
            failures.append("owner_decisions_empty")
        if decisions["horizon_days"].duplicated().any():
            failures.append("multiple_owner_decisions_per_horizon")
        if not winners.empty:
            if winners["is_baseline_forecast"].astype(str).str.lower().eq("true").any():
                failures.append("baseline_selected_as_challenger")
            if not (pd.to_numeric(winners["mae_improvement_vs_current"], errors="coerce") > EPSILON).all():
                failures.append("winner_lacks_positive_full_sample_improvement")
            if not (pd.to_numeric(winners["minimum_slice_mae_improvement"], errors="coerce") > EPSILON).all():
                failures.append("winner_lacks_positive_all_slice_improvement")
            if winners["horizon_days"].duplicated().any():
                failures.append("multiple_corrected_winners_per_horizon")
        for key in [
            "candidate_methodology_change_authorized",
            "production_projection_authorized",
            "purchase_recommendation_authorized",
            "automatic_model_update_allowed",
        ]:
            if summary.get(key) is not False:
                failures.append(f"authorization_not_closed:{key}")
        if summary.get("freeze_suspended_pending_walk_forward") is not True:
            failures.append("freeze_not_suspended")

    result = {
        "audit_name": "Collector Walk-Forward Phase 2I Owner Decision Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
