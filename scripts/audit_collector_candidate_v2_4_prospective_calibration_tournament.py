from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_v2_4_prospective_calibration_tournament/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    required = [
        "collector_candidate_v2_4_prospective_confidence_predictions.csv",
        "collector_candidate_v2_4_prospective_confidence_summary.csv",
        "collector_candidate_v2_4_prospective_confidence_winners.csv",
        "collector_candidate_v2_4_decision_threshold_predictions.csv",
        "collector_candidate_v2_4_decision_threshold_summary.csv",
        "collector_candidate_v2_4_decision_threshold_winners.csv",
        "collector_candidate_v2_4_prospective_calibration_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists(): failures.append(f"missing_output:{name}")

    if not failures:
        summary = json.loads((OUT / "collector_candidate_v2_4_prospective_calibration_summary.json").read_text(encoding="utf-8"))
        cp = pd.read_csv(OUT / "collector_candidate_v2_4_prospective_confidence_predictions.csv", low_memory=False)
        cs = pd.read_csv(OUT / "collector_candidate_v2_4_prospective_confidence_summary.csv", low_memory=False)
        dp = pd.read_csv(OUT / "collector_candidate_v2_4_decision_threshold_predictions.csv", low_memory=False)
        ds = pd.read_csv(OUT / "collector_candidate_v2_4_decision_threshold_summary.csv", low_memory=False)
        if summary.get("status") != "PASS": failures.append("builder_status_not_pass")
        if cp.empty: failures.append("confidence_predictions_empty")
        if cs.empty: failures.append("confidence_summary_empty")
        if dp.empty: failures.append("decision_predictions_empty")
        if ds.empty: failures.append("decision_summary_empty")
        if not cp.empty and cp["future_information_used"].astype(str).str.lower().eq("true").any(): failures.append("confidence_future_information_used")
        if not dp.empty and dp["future_information_used"].astype(str).str.lower().eq("true").any(): failures.append("decision_future_information_used")
        if not cp.empty and "absolute_error" not in cp.columns: failures.append("confidence_error_outcome_missing")
        if not cs.empty and cs.duplicated(["horizon_days", "confidence_method"]).any(): failures.append("duplicate_confidence_configurations")
        if not ds.empty and ds.duplicated(["horizon_days", "lower_quantile", "upper_quantile"]).any(): failures.append("duplicate_decision_configurations")
        for key in ["prospective_confidence_method_authorized", "decision_state_method_authorized", "candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed", "technical_freeze_authorized", "uip_acceptance_authorized"]:
            if summary.get(key) is not False: failures.append(f"authorization_not_closed:{key}")
        if summary.get("freeze_suspended_pending_walk_forward") is not True: failures.append("freeze_not_suspended")

    result = {"audit_name": "Collector Candidate v2.4 Prospective Calibration Tournament Audit", "status": "PASS" if not failures else "FAIL", "failure_count": len(failures), "failures": failures}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
