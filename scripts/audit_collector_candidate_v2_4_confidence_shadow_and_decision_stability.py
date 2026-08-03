from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/operations/collector_candidate_v2_4_confidence_shadow_and_decision_stability/candidate_v1_0_0"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    failures = []
    required = [
        "collector_candidate_v2_4_confidence_shadow_assignments.csv",
        "collector_candidate_v2_4_confidence_shadow_summary.csv",
        "collector_candidate_v2_4_confidence_shadow_cutoff_stability.csv",
        "collector_candidate_v2_4_decision_cutoff_stability.csv",
        "collector_candidate_v2_4_decision_cutoff_stability_summary.csv",
        "collector_candidate_v2_4_confidence_shadow_and_decision_stability_summary.json",
    ]
    for name in required:
        if not (OUT / name).exists(): failures.append(f"missing_output:{name}")

    if not failures:
        summary = json.loads((OUT / required[-1]).read_text(encoding="utf-8"))
        assignments = pd.read_csv(OUT / required[0], low_memory=False)
        confidence = pd.read_csv(OUT / required[1], low_memory=False)
        decision = pd.read_csv(OUT / required[4], low_memory=False)
        if summary.get("status") != "PASS": failures.append("builder_status_not_pass")
        if assignments.empty: failures.append("confidence_assignments_empty")
        if set(assignments["shadow_confidence_tier"].dropna().unique()) - {"STANDARD_CONFIDENCE", "LOW_CONFIDENCE"}:
            failures.append("unexpected_confidence_tier")
        if assignments["future_information_used_for_assignment"].astype(str).str.lower().eq("true").any():
            failures.append("future_information_used")
        if set(confidence["horizon_days"].astype(int)) != {90, 180}:
            failures.append("confidence_horizon_scope_mismatch")
        if (confidence["cutoff_low_worse_than_standard_rate"].astype(float) < 0.7).any():
            failures.append("confidence_cutoff_stability_below_standard")
        if not decision.empty and decision["decision_state_method_authorized"].astype(str).str.lower().eq("true").any():
            failures.append("decision_state_method_authorized")
        for key in ["candidate_methodology_change_authorized", "production_projection_authorized", "purchase_recommendation_authorized", "automatic_model_update_allowed", "technical_freeze_authorized", "uip_acceptance_authorized", "decision_state_method_authorized"]:
            if summary.get(key) is not False: failures.append(f"authorization_not_closed:{key}")
        if summary.get("shadow_confidence_implementation_authorized") is not True:
            failures.append("confidence_shadow_not_authorized")

    result = {
        "audit_name": "Collector Candidate v2.4 Confidence Shadow and Decision Stability Audit",
        "status": "PASS" if not failures else "FAIL",
        "failure_count": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if args.strict and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
