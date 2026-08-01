from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_phase_2b_benchmark_lab/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    required = [
        "collector_walk_forward_phase_2b_variant_outcomes.csv",
        "collector_walk_forward_phase_2b_variant_summary.csv",
        "collector_walk_forward_phase_2b_scenario_coverage.csv",
        "collector_walk_forward_phase_2b_horizon_recommendations.csv",
        "collector_walk_forward_phase_2b_decision_state_summary.csv",
        "collector_walk_forward_phase_2b_summary.json",
    ]
    failures: list[str] = []
    for name in required:
        if not (OUT / name).exists():
            failures.append(f"missing_output:{name}")

    if failures:
        print(json.dumps({"status": "FAIL", "failures": failures}, indent=2))
        return 1 if args.strict else 0

    summary = json.loads((OUT / "collector_walk_forward_phase_2b_summary.json").read_text(encoding="utf-8"))
    variants = pd.read_csv(OUT / "collector_walk_forward_phase_2b_variant_summary.csv")
    scenarios = pd.read_csv(OUT / "collector_walk_forward_phase_2b_scenario_coverage.csv")
    recommendations = pd.read_csv(OUT / "collector_walk_forward_phase_2b_horizon_recommendations.csv")

    if int(summary.get("source_scored_outcome_count", 0)) <= 0:
        failures.append("no_source_scored_outcomes")
    if int(summary.get("forecast_variant_count", 0)) < 2:
        failures.append("insufficient_forecast_variants")
    if set(pd.to_numeric(variants["horizon_days"], errors="coerce").dropna().astype(int)) != {90, 180, 365}:
        failures.append("missing_required_horizons")
    if variants["mean_absolute_error"].isna().any():
        failures.append("variant_mae_missing")
    if not ((pd.to_numeric(scenarios["coverage_rate"], errors="coerce") >= 0) & (pd.to_numeric(scenarios["coverage_rate"], errors="coerce") <= 1)).all():
        failures.append("scenario_coverage_out_of_bounds")
    if len(recommendations) != 3:
        failures.append("expected_three_horizon_recommendations")
    for field in [
        "candidate_methodology_change_authorized",
        "production_projection_authorized",
        "purchase_recommendation_authorized",
        "automatic_model_update_allowed",
    ]:
        if bool(summary.get(field)):
            failures.append(f"authorization_violation:{field}")
    if not bool(summary.get("freeze_suspended_pending_walk_forward")):
        failures.append("freeze_must_remain_suspended")

    result = {
        "audit_name": "Collector Walk-Forward Phase 2B Benchmark Lab Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
