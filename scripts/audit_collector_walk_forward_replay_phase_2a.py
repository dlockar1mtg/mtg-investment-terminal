from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_walk_forward_replay_phase_2a/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    forecasts = pd.read_csv(OUT / "collector_walk_forward_phase_2a_forecasts.csv", low_memory=False)
    scored = pd.read_csv(OUT / "collector_walk_forward_phase_2a_scored_outcomes.csv", low_memory=False)
    metrics = pd.read_csv(OUT / "collector_walk_forward_phase_2a_accuracy_by_horizon.csv", low_memory=False)
    summary = json.loads((OUT / "collector_walk_forward_phase_2a_summary.json").read_text(encoding="utf-8"))

    failures: list[str] = []
    if forecasts.empty:
        failures.append("forecasts_empty")
    if not forecasts.empty and forecasts["future_information_used"].astype(str).str.lower().eq("true").any():
        failures.append("future_information_used")
    if not forecasts.empty and forecasts["product_name"].str.contains("Collector Booster Display", case=False, na=False).sum() != len(forecasts):
        failures.append("non_collector_product_in_scored_scope")
    if not forecasts.empty and forecasts.loc[forecasts["historical_route"] == "DIRECT_HISTORY_LIMITED_RECONSTRUCTION_REQUIRED", "forecast_reconstructable"].astype(str).str.lower().eq("true").any():
        failures.append("limited_route_improperly_reconstructed")
    if not scored.empty and not scored["outcome_held_out_from_decision_inputs"].astype(str).str.lower().eq("true").all():
        failures.append("outcome_not_held_out")
    if not scored.empty and scored["production_projection_authorized"].astype(str).str.lower().eq("true").any():
        failures.append("production_authorization_opened")
    if not scored.empty and scored["purchase_recommendation_authorized"].astype(str).str.lower().eq("true").any():
        failures.append("purchase_authorization_opened")
    if not metrics.empty and not set(metrics["horizon_days"].astype(int)).issubset({90, 180, 365}):
        failures.append("unexpected_horizon")
    if summary.get("full_v2_3_replay_complete") is not False:
        failures.append("full_replay_claimed_prematurely")
    if summary.get("freeze_suspended_pending_walk_forward") is not True:
        failures.append("freeze_not_suspended")

    result = {
        "audit_name": "Collector Walk-Forward Replay Phase 2A Audit",
        "audit_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "collector_product_cutoff_count": int(len(forecasts)),
        "reconstructable_forecast_count": int(forecasts["forecast_reconstructable"].astype(str).str.lower().eq("true").sum()) if not forecasts.empty else 0,
        "scored_outcome_count": int(len(scored)),
        "accuracy_horizon_count": int(len(metrics)),
        "full_v2_3_replay_complete": False,
        "production_projection_authorized": False,
        "purchase_recommendation_authorized": False,
        "failure_count": len(failures),
        "failures": failures,
        "governing_note": "This audit verifies leakage-safe partial historical replay. It does not certify the full v2.3 model, comparable routes, limited routes, production forecasts, or purchase decisions.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
